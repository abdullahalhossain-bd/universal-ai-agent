import json
import logging
import re
import uuid

from fastapi import HTTPException

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger("app.chat")

from app.chat.models import (
    ChatMessage,
    ChatSession,
)

from app.db.models import Product
from app.planner.rule_planner import plan
from app.search.synonyms import expand_terms
from app.core.config import settings
from app.knowledge.search import KnowledgeSearchEngine

from app.chat.context_builder import (
    ContextBuilder,
)

from app.chat.response_service import (
    ChatResponseService,
)

from app.ai.provider_router import (
    LLMProviderRouter,
)

from app.ai.response_generator import (
    ResponseGenerator,
)

from app.ai.context_formatter import (
    ContextFormatter,
)

from app.llm.groq import (
    load_groq_provider,
)

from app.usage.repository import (
    UsageRepository,
)

from app.ai.cost_engine import (
    estimate_cost,
    estimate_messages_tokens,
)

from app.query_engine.tools.stock_tool import (
    StockService,
)


# Shared formatter for pre-call cost estimation. Kept at module
# level so estimation cannot drift from per-request state.
_preflight_formatter = ContextFormatter()


class ChatService:

    # ---------------------------------
    # Shared expensive components
    # ---------------------------------
    #
    # The knowledge search engine, Groq provider pool and
    # response pipeline are process-wide singletons: they hold
    # connection pools and an HTTP client that must not be
    # rebuilt on every request.

    _knowledge_search: KnowledgeSearchEngine | None = None

    _context_builder: ContextBuilder | None = None

    _response_service: ChatResponseService | None = None

    _llm_stack_ready: bool = False

    @classmethod
    def _shared_llm_stack(cls):
        """
        Lazily build the LLM pipeline (Groq provider -> router ->
        generator -> response service).

        Lazy construction keeps deterministic product/knowledge
        queries working even when no GROQ_API_KEY_* is configured;
        only mixed (LLM-composed) queries require keys.
        """

        if not cls._llm_stack_ready:

            groq_provider = load_groq_provider()

            llm_router = LLMProviderRouter(
                providers={
                    "groq": groq_provider,
                }
            )

            response_generator = ResponseGenerator(
                provider_router=llm_router
            )

            cls._response_service = (
                ChatResponseService(
                    llm_generator=response_generator
                )
            )

            cls._llm_stack_ready = True

        return cls._response_service

    @classmethod
    def _shared_knowledge_search(cls):

        if cls._knowledge_search is None:

            cls._knowledge_search = (
                KnowledgeSearchEngine(
                    settings.database_url
                )
            )

        return cls._knowledge_search

    @classmethod
    def _shared_context_builder(cls):

        if cls._context_builder is None:

            cls._context_builder = ContextBuilder()

        return cls._context_builder

    def __init__(
        self,
        db: Session,
    ):
        self.db = db

        self.knowledge_search = (
            self._shared_knowledge_search()
        )

        self.context_builder = (
            self._shared_context_builder()
        )

        self.usage_repo = UsageRepository(
            self.db
        )

        # Freshness-aware stock lookup (never invents a stock
        # number; signals cache/cache_stale/unavailable). See
        # app/query_engine/tools/stock_tool.py.
        self.stock_service = StockService(
            self.db
        )

    # ---------------------------------
    # Conversation helpers
    # ---------------------------------

    def _get_or_create_session(
        self,
        store_id: str,
        conversation_id: str,
    ) -> ChatSession:

        session = (
            self.db.query(ChatSession)
            .filter(
                ChatSession.store_id == store_id,
                ChatSession.conversation_key
                == conversation_id,
            )
            .first()
        )

        if session:
            return session

        session = ChatSession(
            id=str(uuid.uuid4()),
            store_id=store_id,
            conversation_key=conversation_id,
            visitor_id="anonymous",
        )

        self.db.add(session)

        try:
            self.db.commit()
        except IntegrityError:
            # Two concurrent requests for the same
            # (store_id, conversation_key) raced past the
            # SELECT. The DB-level unique constraint
            # (uq_chat_sessions_store_conversation) rejected
            # the second INSERT — roll back and return the
            # winner's row instead of raising a 500.
            self.db.rollback()

            session = (
                self.db.query(ChatSession)
                .filter(
                    ChatSession.store_id == store_id,
                    ChatSession.conversation_key
                    == conversation_id,
                )
                .first()
            )

            if session is None:
                raise

            return session

        self.db.refresh(session)

        return session

    def _load_history(
        self,
        session_id: str,
    ) -> list[dict]:

        # Latest 20 messages, returned in chronological
        # order. Querying ASC + LIMIT would keep the FIRST
        # 20 messages of the conversation and silently lose
        # recent context.
        messages = (
            self.db.query(ChatMessage)
            .filter(
                ChatMessage.session_id
                == session_id,
                ChatMessage.role.in_(
                    ["user", "assistant"]
                ),
            )
            .order_by(
                ChatMessage.created_at.desc()
            )
            .limit(20)
            .all()
        )

        messages.reverse()

        return [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ]

    def _save_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:

        self.db.add(
            ChatMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role=role,
                content=content,
            )
        )

        self.db.commit()

    # ---------------------------------
    # Product context persistence
    # ---------------------------------

    def _save_product_context(
        self,
        session_id: str,
        products: list[Product],
        query: str,
        filters=None,
        offset: int = 0,
    ) -> None:

        product_ids = [
            str(product.id)
            for product in products
        ]

        filter_data = {}

        if filters:

            if isinstance(
                filters,
                dict,
            ):

                filter_data = filters.copy()

            else:

                filter_data = {
                    "min_price": filters.min_price,
                    "max_price": filters.max_price,
                    "in_stock": filters.in_stock,
                    "product_name": filters.product_name,
                }

        # Remove previous context records for this session.
        self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "product_context",
        ).delete(
            synchronize_session=False
        )

        self.db.add(
            ChatMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role="product_context",
                content=json.dumps(
                    {
                        "query": query,
                        "product_ids": product_ids,
                        "offset": offset,
                        "filters": filter_data,
                    },
                    ensure_ascii=False,
                ),
            )
        )

        self.db.commit()

    def _load_product_context(
        self,
        session_id: str,
    ) -> dict:

        context_message = (
            self.db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "product_context",
            )
            .order_by(
                ChatMessage.created_at.desc()
            )
            .first()
        )

        if not context_message:

            return {
                "query": None,
                "product_ids": [],
                "offset": 0,
                "filters": {},
            }

        try:

            data = json.loads(
                context_message.content
            )

            product_ids = data.get(
                "product_ids",
                [],
            )

            offset = data.get(
                "offset",
                0,
            )

            query = data.get(
                "query"
            )

            filters = data.get(
                "filters",
                {},
            )

            if not isinstance(
                product_ids,
                list,
            ):
                product_ids = []

            if not isinstance(
                offset,
                int,
            ):
                offset = 0

            if not isinstance(
                filters,
                dict,
            ):
                filters = {}

            return {
                "query": query,
                "product_ids": [
                    str(product_id)
                    for product_id in product_ids
                ],
                "offset": offset,
                "filters": filters,
            }

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):

            return {
                "query": None,
                "product_ids": [],
                "offset": 0,
                "filters": {},
            }

    # ---------------------------------
    # Reference detection
    # ---------------------------------

    def _is_reference_query(
        self,
        message: str,
    ) -> bool:

        normalized = (
            message.lower().strip()
        )

        reference_words = {
            "এটা",
            "এইটা",
            "ওটা",
            "ওইটা",
            "এটির",
            "এটার",
            "এইটির",
            "এই জুতাটা",
            "ওই product",
            "এই product",
            "this",
            "that",
            "it",
            "this one",
            "that one",
        }

        return any(
            word in normalized
            for word in reference_words
        )

    def _is_price_question(
        self,
        message: str,
    ) -> bool:

        normalized = (
            message.lower()
        )

        return any(
            word in normalized
            for word in [
                "দাম",
                "মূল্য",
                "price",
                "cost",
                "কত",
            ]
        )

    def _is_stock_question(
        self,
        message: str,
    ) -> bool:

        normalized = (
            message.lower()
        )

        return any(
            word in normalized
            for word in [
                "স্টক",
                "stock",
                "available",
                "availability",
                "আছে",
            ]
        )

    def _is_image_question(
        self,
        message: str,
    ) -> bool:

        normalized = (
            message.lower()
        )

        return any(
            word in normalized
            for word in [
                "ছবি",
                "image",
                "photo",
                "picture",
            ]
        )

    def _is_next_query(
        self,
        message: str,
    ) -> bool:

        normalized = (
            message.lower().strip()
        )

        phrases = {
            "আরেকটা দেখাও",
            "আরও দেখাও",
            "আরেকটি দেখাও",
            "আরো দেখাও",
            "পরেরটা দেখাও",
            "পরেরটা",
            "next",
            "show more",
            "more",
            "more products",
            "আরেকটা",
            "আরও",
            "আরো",
        }

        return any(
            phrase in normalized
            for phrase in phrases
        )

    # Bengali digits (০-৯) mapped to their ASCII equivalents so
    # index queries like "২ নম্বরটার দাম কত?" (Bengali numeral)
    # match the same patterns as "2 নম্বরটার দাম কত?" (ASCII digit).
    _BENGALI_DIGIT_MAP = str.maketrans(
        "০১২৩৪৫৬৭৮৯",
        "0123456789",
    )

    def _extract_product_index(
        self,
        message: str,
    ) -> int | None:

        text = message.lower().strip()

        text = text.translate(
            self._BENGALI_DIGIT_MAP
        )

        patterns = [
            (r"(?:^|\s)1(?:ম|মে|নম্বর|নং)?", 1),
            (r"(?:^|\s)2(?:য়|য়?া|নম্বর|নং)?", 2),
            (r"(?:^|\s)3(?:য়|রা|নম্বর|নং)?", 3),
            (r"(?:^|\s)4(?:র্থ|নম্বর|নং)?", 4),
            (r"(?:^|\s)5(?:ম|নম্বর|নং)?", 5),
        ]

        for pattern, index in patterns:

            if re.search(
                pattern,
                text,
            ):
                return index

        ordinal_map = {
            "প্রথম": 1,
            "প্রথমটা": 1,
            "প্রথমটির": 1,
            "দ্বিতীয়": 2,
            "দ্বিতীয়টা": 2,
            "দ্বিতীয়টির": 2,
            "তৃতীয়": 3,
            "তৃতীয়টা": 3,
            "তৃতীয়টির": 3,
            "first": 1,
            "first one": 1,
            "second": 2,
            "second one": 2,
            "third": 3,
            "third one": 3,
        }

        for phrase, index in ordinal_map.items():

            if phrase in text:
                return index

        return None

    def _is_index_reference(
        self,
        message: str,
    ) -> bool:

        return (
            self._extract_product_index(
                message
            )
            is not None
        )

    def _get_referenced_product(
        self,
        store_id: str,
        session_id: str,
        message: str,
    ):
        context_data = (
            self._load_product_context(
                session_id
            )
        )

        product_ids = context_data[
            "product_ids"
        ]

        if not product_ids:
            return None

        # ---------------------------------
        # Indexed reference
        # ---------------------------------
        #
        # Example:
        # "২ নম্বরটা"
        # "3rd one"
        #

        index = self._extract_product_index(
            message
        )

        if index is not None:

            position = index - 1

            if (
                position < 0
                or position >= len(product_ids)
            ):
                return None

            product_id = (
                product_ids[position]
            )

            products = (
                self._get_products_by_ids(
                    store_id=store_id,
                    product_ids=[product_id],
                )
            )

            if not products:
                return None

            return products[0]

        # ---------------------------------
        # Generic reference
        # ---------------------------------
        #
        # Examples:
        # "এটা কত টাকা?"
        # "এটার stock কত?"
        # "এইটা কেমন?"
        # "this one"
        # "that product"
        #

        if self._is_reference_query(
            message
        ):

            product_id = product_ids[0]

            products = (
                self._get_products_by_ids(
                    store_id=store_id,
                    product_ids=[product_id],
                )
            )

            if not products:
                return None

            return products[0]

        return None
    # ---------------------------------
    # Product search
    # ---------------------------------

    def _search_products(
        self,
        store_id: str,
        message: str,
        filters,
    ) -> list[Product]:

        query = (
            self.db.query(Product)
            .filter(
                Product.store_id == store_id
            )
        )

        # Price filters
        if filters:

            if filters.min_price is not None:

                query = query.filter(
                    Product.price
                    >= filters.min_price
                )

            if filters.max_price is not None:

                query = query.filter(
                    Product.price
                    <= filters.max_price
                )

            if filters.in_stock:

                query = query.filter(
                    Product.stock > 0
                )

        # Planner-cleaned search text
        if (
            filters
            and filters.product_name
        ):

            search_text = (
                filters.product_name
            )

        else:

            search_text = message

        # ---------------------------------
        # Stop words
        # ---------------------------------

        stop_words = {
            # English
            "show",
            "find",
            "product",
            "products",
            "please",
            "available",
            "in",
            "stock",
            "under",
            "below",
            "less",
            "than",
            "within",
            "price",
            "taka",
            "tk",
            "me",
            "my",
            "the",
            "a",
            "an",
            "of",
            "for",
            "to",
            "with",
            "is",
            "are",
            "and",
            "or",

            # Bangla
            "দেখাও",
            "দেখান",
            "চাই",
            "আছে",
            "স্টকে",
            "স্টক",
            "এর",
            "মধ্যে",
            "টাকার",
            "টাকা",
            "জন্য",
            "ও",
            "আর",
        }

        raw_terms = []

        for term in search_text.split():

            cleaned = term.strip(
                ".,!?;:()[]{}\"'"
            )

            if not cleaned:
                continue

            lowered = cleaned.lower()

            if len(cleaned) < 2:
                continue

            if lowered in stop_words:
                continue

            if cleaned.isdigit():
                continue

            raw_terms.append(cleaned)

        # ---------------------------------
        # Synonym groups
        # ---------------------------------

        group_conditions = []

        for raw_term in raw_terms:

            term_group = expand_terms(
                [raw_term]
            )

            if not term_group:
                continue

            condition = or_(
                *[
                    Product.name.ilike(
                        f"%{synonym}%"
                    )
                    for synonym in term_group
                ]
            )

            group_conditions.append(
                condition
            )

        if group_conditions:

            query = query.filter(
                and_(*group_conditions)
            )

        return (
            query
            .order_by(Product.name.asc())
            .limit(10)
            .all()
        )

    # ---------------------------------
    # Pagination ("আরেকটা দেখাও")
    # ---------------------------------

    def _get_next_products(
        self,
        store_id: str,
        query_text: str,
        filters_data: dict,
        previous_ids: list[str],
        batch_size: int = 5,
    ) -> list[Product]:

        query = (
            self.db.query(Product)
            .filter(
                Product.store_id == store_id
            )
        )

        # -----------------------------
        # Restore original price filter
        # -----------------------------

        min_price = filters_data.get(
            "min_price"
        )

        max_price = filters_data.get(
            "max_price"
        )

        in_stock = filters_data.get(
            "in_stock",
            False,
        )

        if min_price is not None:

            query = query.filter(
                Product.price >= min_price
            )

        if max_price is not None:

            query = query.filter(
                Product.price <= max_price
            )

        if in_stock:

            query = query.filter(
                Product.stock > 0
            )

        # -----------------------------
        # Restore search terms
        # -----------------------------

        product_name = filters_data.get(
            "product_name"
        )

        search_text = (
            product_name
            or query_text
            or ""
        )

        stop_words = {
            "show",
            "find",
            "product",
            "products",
            "please",
            "available",
            "in",
            "stock",
            "under",
            "below",
            "less",
            "than",
            "within",
            "price",
            "taka",
            "tk",
            "me",
            "my",
            "the",
            "a",
            "an",
            "of",
            "for",
            "to",
            "with",
            "is",
            "are",
            "and",
            "or",
            "দেখাও",
            "দেখান",
            "চাই",
            "আছে",
            "স্টকে",
            "স্টক",
            "এর",
            "মধ্যে",
            "টাকার",
            "টাকা",
            "জন্য",
            "ও",
            "আর",
        }

        raw_terms = []

        for term in search_text.split():

            cleaned = term.strip(
                ".,!?;:()[]{}\"'"
            )

            if not cleaned:
                continue

            lowered = cleaned.lower()

            if len(cleaned) < 2:
                continue

            if lowered in stop_words:
                continue

            if cleaned.isdigit():
                continue

            raw_terms.append(
                cleaned
            )

        # -----------------------------
        # Same synonym grouping
        # -----------------------------

        group_conditions = []

        for raw_term in raw_terms:

            synonyms = expand_terms(
                [raw_term]
            )

            if not synonyms:
                continue

            group_conditions.append(
                or_(
                    *[
                        Product.name.ilike(
                            f"%{synonym}%"
                        )
                        for synonym in synonyms
                    ]
                )
            )

        if group_conditions:

            query = query.filter(
                and_(*group_conditions)
            )

        # -----------------------------
        # Exclude previously shown
        # -----------------------------

        if previous_ids:

            query = query.filter(
                ~Product.id.in_(
                    previous_ids
                )
            )

        return (
            query
            .order_by(Product.name.asc())
            .limit(batch_size)
            .all()
        )

    # ---------------------------------
    # Website knowledge search
    # ---------------------------------

    def _search_knowledge(
        self,
        store_id: str,
        message: str,
    ):
        return self.knowledge_search.search(
            store_id=store_id,
            query=message,
            limit=5,
        )

    # ---------------------------------
    # Direct product lookup
    # ---------------------------------

    def _get_products_by_ids(
        self,
        store_id: str,
        product_ids: list[str],
    ) -> list[Product]:

        if not product_ids:
            return []

        products = (
            self.db.query(Product)
            .filter(
                Product.store_id == store_id,
                Product.id.in_(product_ids),
            )
            .all()
        )

        by_id = {
            str(product.id): product
            for product in products
        }

        # Preserve previous result order.
        return [
            by_id[product_id]
            for product_id in product_ids
            if product_id in by_id
        ]

    # ---------------------------------
    # Response serialization
    # ---------------------------------

    def _serialize_products(
        self,
        products: list[Product],
    ) -> list[dict]:

        result = []

        for product in products:

            result.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "price": (
                        float(product.price)
                        if product.price is not None
                        else None
                    ),
                    "stock": (
                        float(product.stock)
                        if product.stock is not None
                        else None
                    ),
                    "image_url": (
                        product.image_url
                    ),
                    "product_url": (
                        product.product_url
                    ),
                }
            )

        return result

    # ---------------------------------
    # Product message
    # ---------------------------------

    def _product_message(
        self,
        products: list[dict],
    ) -> str:

        if len(products) == 1:

            product = products[0]

            text = product["name"]

            if product["price"] is not None:

                text += (
                    f" — ৳"
                    f"{product['price']:,.0f}"
                )

            if product["stock"] is not None:

                if product["stock"] > 0:

                    text += (
                        f" | Stock: "
                        f"{product['stock']:g}"
                    )

                else:

                    text += (
                        " | Out of stock"
                    )

            return text

        return (
            f"{len(products)}টি "
            "matching product পাওয়া গেছে।"
        )

    # ---------------------------------
    # Live stock answer
    # ---------------------------------
    #
    # Shared by both the "reference" path (এটার stock আছে?) and the
    # fresh-search path (blue shirt-এর stock আছে?). Both must go
    # through StockService.check() instead of the value already sat
    # in `product.stock` from `_serialize_products`, because that
    # field is only as fresh as the last sync and StockService is the
    # single place that turns "stale" into an explicit caveat instead
    # of presenting an old number as current.

    def _stock_message(
        self,
        product: Product,
    ) -> str:

        stock_result = (
            self.stock_service.check(
                product.store_id,
                product.id,
            )
        )

        if stock_result.stock is None:

            return (
                "এই productটির stock "
                "তথ্য পাওয়া যাচ্ছে না।"
            )

        freshness_note = ""

        if (
            stock_result.source
            == "cache_stale"
            and stock_result.freshness_seconds
        ):

            minutes = int(
                stock_result.freshness_seconds
                // 60
            )

            if minutes >= 1:

                freshness_note = (
                    f" (সর্বশেষ sync "
                    f"{minutes} মিনিট আগে, "
                    "তাই সামান্য পরিবর্তন "
                    "হতে পারে)"
                )

        if stock_result.in_stock:

            return (
                f"{product.name}-এর "
                f"{stock_result.stock:g}টি "
                f"stock আছে।{freshness_note}"
            )

        return (
            f"{product.name} "
            f"out of stock।{freshness_note}"
        )

    # ---------------------------------
    # Reference response
    # ---------------------------------

    def _reference_message(
        self,
        message: str,
        products: list[Product],
    ) -> str:

        if not products:

            return (
                "আগের productটি আর "
                "পাওয়া যাচ্ছে না।"
            )

        # For "এটা" we use the first referenced
        # product. Multi-product reference handling
        # can be added later.
        product = products[0]

        normalized = (
            message.lower()
        )

        if self._is_price_question(
            normalized
        ):

            if product.price is None:

                return (
                    "এই productটির দাম "
                    "বর্তমানে পাওয়া যাচ্ছে না।"
                )

            return (
                f"{product.name}-এর দাম "
                f"৳{float(product.price):,.0f}।"
            )

        if self._is_stock_question(
            normalized
        ):

            return self._stock_message(
                product
            )

        if self._is_image_question(
            normalized
        ):

            if product.image_url:

                return (
                    f"{product.name}-এর ছবি: "
                    f"{product.image_url}"
                )

            return (
                "এই productটির কোনো "
                "ছবি পাওয়া যাচ্ছে না।"
            )

        return self._product_message(
            self._serialize_products(
                [product]
            )
        )

    # ---------------------------------
    # Main chat handler
    # ---------------------------------

    async def handle(
        self,
        store_id: str,
        request,
    ):

        conversation_id = (
            request.conversation_id
            or str(uuid.uuid4())
        )

        message = (
            request.message.strip()
        )

        session = (
            self._get_or_create_session(
                store_id=store_id,
                conversation_id=conversation_id,
            )
        )

        history = self._load_history(
            session.id
        )

        planned = plan(message)

        # ---------------------------------
        # Pagination ("আরেকটা দেখাও")
        # ---------------------------------

        if self._is_next_query(message):

            context_data = (
                self._load_product_context(
                    session.id
                )
            )

            previous_ids = (
                context_data["product_ids"]
            )

            original_query = (
                context_data["query"]
                or ""
            )

            filters_data = (
                context_data["filters"]
            )

            next_products = (
                self._get_next_products(
                    store_id=store_id,
                    query_text=original_query,
                    filters_data=filters_data,
                    previous_ids=previous_ids,
                    batch_size=5,
                )
            )

            self._save_message(
                session_id=session.id,
                role="user",
                content=message,
            )

            if not next_products:

                response_message = (
                    "এই search-এর আর কোনো "
                    "matching product পাওয়া যায়নি।"
                )

                self._save_message(
                    session_id=session.id,
                    role="assistant",
                    content=response_message,
                )

                return {
                    "conversation_id": conversation_id,
                    "type": "product_search",
                    "message": response_message,
                    "products": [],
                    "sources": [],
                }

            response_products = (
                self._serialize_products(
                    next_products
                )
            )

            self._save_product_context(
                session_id=session.id,
                products=next_products,
                query=original_query,
                filters=filters_data,
                offset=(
                    context_data["offset"]
                    + len(next_products)
                ),
            )

            response_message = (
                f"{len(response_products)}টি "
                "আরও product পাওয়া গেছে।"
            )

            self._save_message(
                session_id=session.id,
                role="assistant",
                content=response_message,
            )

            return {
                "conversation_id": conversation_id,
                "type": "product_search",
                "message": response_message,
                "products": response_products,
                "sources": [],
            }

        # ---------------------------------
        # Reference product lookup
        # ---------------------------------

        reference_product = None

        if (
            self._is_reference_query(message)
            or self._is_index_reference(message)
        ):

            reference_product = (
                self._get_referenced_product(
                    store_id=store_id,
                    session_id=session.id,
                    message=message,
                )
            )

        # ---------------------------------
        # Normal product search
        # ---------------------------------

        products = []

        knowledge_results = []

        if reference_product:

            products = [reference_product]

        elif planned.intent.value in {
            "product_search",
            "mixed",
        }:

            products = self._search_products(
                store_id=store_id,
                message=message,
                filters=planned.product_filters,
            )

        if planned.intent.value == "mixed":

            knowledge_query = (
                getattr(
                    planned,
                    "knowledge_query",
                    None,
                )
                or message
            )

            knowledge_results = (
                self._search_knowledge(
                    store_id=store_id,
                    message=knowledge_query,
                )
            )

        # ---------------------------------
        # Save user message
        # ---------------------------------

        self._save_message(
            session_id=session.id,
            role="user",
            content=message,
        )

        # ---------------------------------
        # Mixed query -> LLM-composed answer
        # ---------------------------------

        if planned.intent.value == "mixed":

            chat_context = self.context_builder.build(
                tenant_id=store_id,
                session_id=session.id,
                message=message,
                history=history,
                products=products,
                knowledge=knowledge_results,
            )

            # ---------------------------------
            # Build conservative pre-call estimate
            # ---------------------------------

            formatted_context = (
                _preflight_formatter.format(
                    chat_context
                )
            )

            history_text = "\n".join(
                f"{item['role']}: {item['content']}"
                for item in history
            )

            estimated_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an ecommerce "
                        "customer assistant. "
                        "Use only the provided context."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"USER QUESTION:\n"
                        f"{message}\n\n"
                        f"AVAILABLE PRODUCT / WEBSITE CONTEXT:\n"
                        f"{formatted_context}\n\n"
                        f"RECENT CONVERSATION:\n"
                        f"{history_text}"
                    ),
                },
            ]

            estimated_input_tokens = (
                estimate_messages_tokens(
                    estimated_messages
                )
            )

            max_output_tokens = 500

            preflight_cost = estimate_cost(
                input_tokens=estimated_input_tokens,
                output_tokens=max_output_tokens,
                input_price=(
                    settings.groq_input_cost_per_1m
                ),
                output_price=(
                    settings.groq_output_cost_per_1m
                ),
            )

            request_id = str(
                uuid.uuid4()
            )

            # ---------------------------------
            # Atomic budget reservation
            # ---------------------------------

            reservation = (
                self.usage_repo.reserve_budget(
                    store_id=store_id,
                    conversation_id=conversation_id,
                    request_id=request_id,
                    route="groq",
                    model=settings.groq_model,
                    estimated_cost=preflight_cost,
                )
            )

            if reservation is None:

                response_message = (
                    "দুঃখিত, এই মাসের AI usage "
                    "limit অতিক্রম হয়ে গেছে।"
                )

                self._save_message(
                    session_id=session.id,
                    role="assistant",
                    content=response_message,
                )

                return {
                    "conversation_id": conversation_id,
                    "type": "mixed",
                    "message": response_message,
                    "products": self._serialize_products(
                        products
                    ),
                    "sources": [
                        {
                            "type": "website",
                            "title": item.title,
                            "url": item.url,
                        }
                        for item in knowledge_results
                    ],
                }

            # ---------------------------------
            # LLM request
            # ---------------------------------

            response_service = (
                self._shared_llm_stack()
            )

            try:

                ai_response = (
                    await response_service.generate(
                        query=message,
                        context=chat_context,
                        plan=planned,
                    )
                )

            except Exception as exc:

                # Provider outage / exhausted key pool / bad key.
                # The hold is released and the client receives a
                # retryable 503 — never a raw 500 with internal
                # details. Full diagnostics stay in server logs.
                self.usage_repo.fail_budget_reservation(
                    request_id=request_id,
                )

                logger.error(
                    "LLM generation failed for store %s "
                    "request %s: %s: %s",
                    store_id,
                    request_id,
                    type(exc).__name__,
                    exc,
                )

                raise HTTPException(
                    status_code=503,
                    detail=(
                        "AI service is temporarily unavailable. "
                        "Please try again shortly. "
                        "(এআই সেবা সাময়িকভাবে বন্ধ আছে, "
                        "কিছুক্ষণ পরে আবার চেষ্টা করুন।)"
                    ),
                ) from exc

            # ---------------------------------
            # Reservation outcome
            # ---------------------------------
            #
            # used_llm=True  -> finalize with actual usage.
            # used_llm=False -> the deterministic path answered
            #    without any provider call; the hold must be
            #    released immediately or it counts against the
            #    store budget until the TTL expires.

            if ai_response.get(
                "used_llm",
                False,
            ):

                usage = ai_response.get(
                    "usage",
                    {},
                )

                actual_input_tokens = int(
                    usage.get(
                        "input_tokens",
                        0,
                    )
                )

                actual_output_tokens = int(
                    usage.get(
                        "output_tokens",
                        0,
                    )
                )

                actual_cost = estimate_cost(
                    input_tokens=actual_input_tokens,
                    output_tokens=actual_output_tokens,
                    input_price=(
                        settings
                        .groq_input_cost_per_1m
                    ),
                    output_price=(
                        settings
                        .groq_output_cost_per_1m
                    ),
                )

                self.usage_repo.finalize_budget_reservation(
                    request_id=request_id,
                    input_tokens=actual_input_tokens,
                    output_tokens=actual_output_tokens,
                    actual_cost=actual_cost,
                    latency_ms=0,
                    cache_hit=False,
                )

            else:

                # Deterministic answer: release the hold.
                self.usage_repo.fail_budget_reservation(
                    request_id=request_id,
                )

            message_text = ai_response[
                "message"
            ]

            self._save_message(
                session_id=session.id,
                role="assistant",
                content=message_text,
            )

            return {
                "conversation_id": conversation_id,
                "type": "mixed",
                "message": message_text,
                "products": self._serialize_products(
                    products
                ),
                "sources": [
                    {
                        "type": "website",
                        "title": item.title,
                        "url": item.url,
                    }
                    for item in knowledge_results
                ],
            }

        # ---------------------------------
        # Knowledge
        # ---------------------------------

        if (
            planned.intent.value
            == "knowledge_search"
            and not reference_product
        ):

            knowledge_results = self._search_knowledge(
                store_id=store_id,
                message=message,
            )

            if knowledge_results:

                top = knowledge_results[0]

                response_message = (
                    top.content
                )

                sources = [
                    {
                        "type": "website",
                        "title": result.title,
                        "url": result.url,
                    }
                    for result in knowledge_results
                ]

            else:

                response_message = (
                    "দুঃখিত, website-এ এই তথ্যটি "
                    "পাওয়া যায়নি।"
                )

                sources = []

            self._save_message(
                session_id=session.id,
                role="assistant",
                content=response_message,
            )

            return {
                "conversation_id": conversation_id,
                "type": "knowledge",
                "message": response_message,
                "products": [],
                "sources": sources,
            }

        # ---------------------------------
        # General
        # ---------------------------------

        if (
            planned.intent.value == "unknown"
            and not reference_product
        ):

            response_message = (
                "হ্যালো! কীভাবে সাহায্য "
                "করতে পারি?"
            )

            self._save_message(
                session_id=session.id,
                role="assistant",
                content=response_message,
            )

            return {
                "conversation_id": conversation_id,
                "type": "general",
                "message": response_message,
                "products": [],
                "sources": [],
            }

        # ---------------------------------
        # Mixed response (product + knowledge)
        # ---------------------------------

        if (
            planned.intent.value == "mixed"
            and (
                products
                or knowledge_results
            )
        ):

            response_products = (
                self._serialize_products(
                    products
                )
            )

            parts = []

            if response_products:

                parts.append(
                    self._product_message(
                        response_products
                    )
                )

            sources = []

            if knowledge_results:

                parts.append(
                    knowledge_results[0].content
                )

                sources = [
                    {
                        "type": "website",
                        "title": result.title,
                        "url": result.url,
                    }
                    for result in knowledge_results
                ]

            response_message = "\n\n".join(parts)

            self._save_message(
                session_id=session.id,
                role="assistant",
                content=response_message,
            )

            return {
                "conversation_id": conversation_id,
                "type": "mixed",
                "message": response_message,
                "products": response_products,
                "sources": sources,
            }

        # ---------------------------------
        # No product result
        # ---------------------------------

        if not products:

            response_message = (
                "দুঃখিত, matching কোনো "
                "product পাওয়া যায়নি।"
            )

            self._save_message(
                session_id=session.id,
                role="assistant",
                content=response_message,
            )

            return {
                "conversation_id": conversation_id,
                "type": "product_search",
                "message": response_message,
                "products": [],
                "sources": [],
            }

        # ---------------------------------
        # Persist last shown product context
        # ---------------------------------

        self._save_product_context(
            session_id=session.id,
            products=products,
            query=message,
            filters=planned.product_filters,
            offset=len(products),
        )

        # ---------------------------------
        # Serialize
        # ---------------------------------

        response_products = (
            self._serialize_products(
                products
            )
        )

        # ---------------------------------
        # Reference answer
        # ---------------------------------

        if reference_product:

            message_text = (
                self._reference_message(
                    message=message,
                    products=[reference_product],
                )
            )

        elif (
            len(products) == 1
            and self._is_stock_question(
                message
            )
        ):

            # A fresh search ("blue shirt-এর stock
            # আছে?") that happens to resolve to a
            # single product deserves the same
            # freshness-checked answer as an explicit
            # "এটার" reference — not the raw
            # `product.stock` column from
            # `_serialize_products`.
            message_text = (
                self._stock_message(
                    products[0]
                )
            )

        else:

            message_text = (
                self._product_message(
                    response_products
                )
            )

        # ---------------------------------
        # Save assistant response
        # ---------------------------------

        self._save_message(
            session_id=session.id,
            role="assistant",
            content=message_text,
        )

        return {
            "conversation_id": conversation_id,
            "type": "product_search",
            "message": message_text,
            "products": response_products,
            "sources": [],
        }

    # ---------------------------------
    # Image chat
    # ---------------------------------
    #
    # Separate entry point rather than folded into `handle()` above:
    # `handle()` is already a large, delicate state machine keyed
    # off free-text intent detection, and an uploaded image arrives
    # with an explicit `image_id` — there's no ambiguity to resolve,
    # so this skips straight to vision analysis + product matching
    # instead of forcing it through the text planner. It still
    # reuses the same session/history/persistence helpers so an
    # image turn shows up in the conversation like any other
    # message, and pagination ("আরেকটা দেখাও") on its results works
    # via the same `_save_product_context` mechanism as a text
    # product search.

    async def handle_image(
        self,
        store,
        image_id: str,
        conversation_id: str | None = None,
        question: str | None = None,
    ) -> dict:

        from app.images.repository import ImageRepository
        from app.vision.vision_service import (
            VisionService,
            VisionBudgetExceededError,
        )
        from app.vision.vision_router import VisionAnalysisError
        from app.vision.product_matcher import ProductMatcher

        conversation_id = (
            conversation_id or str(uuid.uuid4())
        )

        session = self._get_or_create_session(
            store_id=store.id,
            conversation_id=conversation_id,
        )

        image_record = ImageRepository(self.db).get(
            store_id=store.id,
            image_id=image_id,
        )

        if image_record is None:

            raise HTTPException(
                status_code=404,
                detail="Image not found",
            )

        user_note = (
            question.strip()
            if question and question.strip()
            else "[uploaded a photo]"
        )

        self._save_message(
            session_id=session.id,
            role="user",
            content=user_note,
        )

        task = "image_question" if question else "product_match"

        service = VisionService(db=self.db, usage_repo=self.usage_repo)

        try:
            analysis = await service.analyze(
                store=store,
                image_record=image_record,
                task=task,
                question=question,
            )

        except VisionBudgetExceededError:

            response_message = (
                "দুঃখিত, এই মাসের AI usage "
                "limit অতিক্রম হয়ে গেছে।"
            )

            self._save_message(
                session_id=session.id,
                role="assistant",
                content=response_message,
            )

            return {
                "conversation_id": conversation_id,
                "type": "image_chat",
                "message": response_message,
                "products": [],
                "sources": [],
            }

        except VisionAnalysisError as exc:

            logger.error(
                "Vision analysis failed for store %s image %s: %s",
                store.id,
                image_id,
                exc,
            )

            raise HTTPException(
                status_code=503,
                detail=(
                    "Image analysis is temporarily unavailable. "
                    "Please try again shortly. (ছবি বিশ্লেষণ সাময়িকভাবে "
                    "বন্ধ আছে, কিছুক্ষণ পরে আবার চেষ্টা করুন।)"
                ),
            ) from exc

        # ---------------------------------
        # image_question: plain-text visual Q&A, no product search
        # ---------------------------------

        if task == "image_question":

            message_text = analysis.get(
                "answer",
                "দুঃখিত, ছবিটি নিয়ে উত্তর দেওয়া যায়নি।",
            )

            self._save_message(
                session_id=session.id,
                role="assistant",
                content=message_text,
            )

            return {
                "conversation_id": conversation_id,
                "type": "image_chat",
                "message": message_text,
                "products": [],
                "sources": [],
            }

        # ---------------------------------
        # product_match: analysis + ranked catalog matches
        # ---------------------------------

        matched_products = ProductMatcher(self.db).match(
            store_id=store.id,
            analysis=analysis,
            limit=settings.vision_max_matched_products,
        )

        response_products = self._serialize_products(
            matched_products
        )

        description = analysis.get("description")

        if response_products:

            message_text = (
                f"{description}। এর সাথে মিলে যাওয়া কিছু প্রোডাক্ট:"
                if description
                else "এই ছবির সাথে মিলে যাওয়া কিছু প্রোডাক্ট:"
            )

        elif description:

            message_text = (
                f"{description} — দুঃখিত, দোকানে এর সাথে মিলে "
                "এমন কোনো প্রোডাক্ট পাওয়া যায়নি।"
            )

        else:

            message_text = (
                "দুঃখিত, ছবিটি বিশ্লেষণ করা গেলেও দোকানে মিলে যাওয়া "
                "কোনো প্রোডাক্ট পাওয়া যায়নি।"
            )

        self._save_message(
            session_id=session.id,
            role="assistant",
            content=message_text,
        )

        if matched_products:

            self._save_product_context(
                session_id=session.id,
                products=matched_products,
                query=" ".join(
                    analysis.get("keywords") or []
                ),
            )

        return {
            "conversation_id": conversation_id,
            "type": "image_chat",
            "message": message_text,
            "products": response_products,
            "sources": [],
            "analysis": analysis,
        }