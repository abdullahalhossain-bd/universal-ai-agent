from dataclasses import (
    dataclass,
    field,
)


@dataclass
class ChatContext:

    tenant_id: str

    session_id: str

    user_message: str

    history: list[dict] = field(
        default_factory=list
    )

    products: list = field(
        default_factory=list
    )

    knowledge: list = field(
        default_factory=list
    )

    metadata: dict = field(
        default_factory=dict
    )

    @property
    def items(self):

        return [
            *self.products,
            *self.knowledge,
        ]

    @property
    def product_count(self):

        return len(
            self.products
        )

    @property
    def knowledge_count(self):

        return len(
            self.knowledge
        )