from app.search.learning import normalize_learning_query, normalize_learning_term


def test_learning_query_is_stable_and_bounded():
    assert normalize_learning_query("  Laptpo   ER   DAM  ") == "laptpo er dam"
    assert len(normalize_learning_query("x" * 500)) == 255


def test_learning_term_is_cleaned_and_bounded():
    assert normalize_learning_term("  laptop!!! ") == "laptop"
    assert len(normalize_learning_term("x" * 500)) == 255
