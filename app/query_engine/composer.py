from app.query_engine.result import (
    QueryEngineResult,
    AnswerBlock,
    SourceRef,
)


def compose_answer(
    tool_results: dict,
):

    blocks = []

    sources = []

    products = tool_results.get(
        "product_search"
    )

    if isinstance(products, list) and products:

        blocks.append(
            AnswerBlock(
                type="product_cards",
                items=products,
            )
        )

    knowledge = tool_results.get(
        "knowledge_search"
    )

    if isinstance(knowledge, dict):

        text = knowledge.get("answer")

        if text:

            blocks.append(
                AnswerBlock(
                    type="text",
                    text=text,
                )
            )

        source = knowledge.get("source")

        if source:

            sources.append(
                SourceRef(
                    title=source.get("title", ""),
                    url=source.get("url"),
                )
            )

    message = (
        "এখানে আপনার প্রশ্নের উত্তর।"
        if blocks
        else "দুঃখিত, আমি এই তথ্য খুঁজে পাইনি।"
    )

    return QueryEngineResult(
        message=message,
        blocks=blocks,
        sources=sources,
    )
