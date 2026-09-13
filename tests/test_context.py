from app.ai.context_builder import (
    ContextBuilder,
)


def test_unified_context():

    builder = ContextBuilder()

    context = builder.build(
        query="Nike Air Max return policy",
        products=[],
        knowledge=[],
    )

    assert (
        context.query
        == "Nike Air Max return policy"
    )

    assert context.items == []
