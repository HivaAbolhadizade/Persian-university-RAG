from backend.app.utils.text import (
    expand_query,
    extract_article_number,
    normalize_persian_query,
)


def test_persian_normalization() -> None:
    assert normalize_persian_query("شرايط  مهماني  دانشجو") == "شرایط مهمانی دانشجو"


def test_query_expansion_does_not_create_invalid_suffix() -> None:
    variants = expand_query("شرایط انتقالی دانشجو")
    assert all("انتقالیی" not in item for item in variants)


def test_article_number_normalization() -> None:
    assert extract_article_number("ماده ۱۲ آیین‌نامه") == "12"
