from types import SimpleNamespace

from backend.app.services.retriever import RetrievalEngine, RetrievedChunk
from backend.app.utils.text import (
    extract_relevant_excerpt,
    extract_solar_years,
    local_lexical_relevance_features,
)


def _engine() -> RetrievalEngine:
    engine = RetrievalEngine.__new__(RetrievalEngine)
    engine.latest_regulation_year = 1402
    engine.retrieval_config = {"retrieval": {"deduplication_threshold": 0.99}}
    engine.settings = SimpleNamespace(
        preferred_regulation_year=None,
        prefer_latest_regulations=True,
        latest_document_bonus=0.18,
        stale_document_penalty=0.30,
        stale_year_gap=2,
        stale_filter_relevance_margin=0.18,
        long_chunk_penalty_max=0.22,
        preferred_chunk_characters=3500,
        preferred_page_span=8,
        maximum_chunks_per_document=3,
    )
    return engine


def _chunk(title: str, relevance: float, rank: int, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"c{rank}",
        document_id=f"d{rank}",
        row_id=rank,
        rank=rank,
        raw_score=relevance,
        display_score=0.0,
        method="bm25",
        text=text,
        title=title,
        category="regulations",
        page_start=1,
        page_end=2,
        article=None,
        note=None,
        chunk_order=rank,
        metadata={"relevance_score": relevance},
    )


def test_extract_solar_years_normalizes_persian_digits() -> None:
    assert extract_solar_years("مقررات ۱۴۰۲ و آیین نامه 1397") == [1402, 1397]


def test_local_scope_rejects_undergraduate_window_for_master_question() -> None:
    query = "حداکثر مدت مجاز تحصیل در دوره کارشناسی ارشد چند نیمسال است؟"
    wrong = "مدت مجاز دوره کارشناسی پیوسته هشت نیمسال است. شرایط پذیرش کارشناسی ارشد اعلام شد."
    right = "مدت مجاز تحصیل در دوره کارشناسی ارشد چهار نیمسال است."

    wrong_features = local_lexical_relevance_features(query, wrong)
    right_features = local_lexical_relevance_features(query, right)

    assert right_features["anchor_coverage"] > wrong_features["anchor_coverage"]
    assert right_features["scope_match"] is True


def test_newer_regulation_ranks_above_old_conflicting_version() -> None:
    engine = _engine()
    query = "حداکثر مدت مجاز تحصیل در دوره کارشناسی ارشد چند نیمسال است؟"
    old = _chunk(
        "آیین نامه کارشناسی ارشد 1397",
        0.86,
        1,
        "مدت مجاز تحصیل در دوره کارشناسی ارشد چهار نیمسال است و تا دو نیمسال افزایش می یابد.",
    )
    new = _chunk(
        "مجموعه مقررات آموزشی 1402",
        0.74,
        2,
        "مدت مجاز تحصیل چهار نیمسال است و با تایید دانشگاه حداکثر یک نیمسال افزایش می یابد.",
    )

    ranked = engine._apply_temporal_authority_policy(query, [old, new])

    assert ranked[0].title.endswith("1402")
    assert ranked[0].metadata["temporal_authority"]["stale"] is False
    assert any(item.metadata["temporal_authority"]["stale"] for item in ranked)


def test_explicit_historical_year_keeps_requested_version_first() -> None:
    engine = _engine()
    query = "طبق آیین نامه ۱۳۹۷ مدت مجاز کارشناسی ارشد چقدر بود؟"
    old = _chunk("آیین نامه کارشناسی ارشد 1397", 0.70, 1, "چهار نیمسال")
    new = _chunk("مجموعه مقررات آموزشی 1402", 0.82, 2, "چهار نیمسال")

    ranked = engine._apply_temporal_authority_policy(query, [new, old])

    assert ranked[0].title.endswith("1397")


def test_excerpt_finds_relevant_clause_in_long_chunk() -> None:
    query = "حداقل نمره قبولی هر درس در کارشناسی ارشد چقدر است؟"
    text = ("متن نامرتبط درباره شهریه. " * 300) + (
        "ماده ۲۹. حداقل نمره قبولی هر درس در کارشناسی ارشد ۱۲ از ۲۰ است."
    )
    excerpt = extract_relevant_excerpt(text, query, maximum_characters=500)
    assert "12 از 20" in excerpt
    assert len(excerpt) <= 500
