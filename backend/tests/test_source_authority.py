from types import SimpleNamespace

from backend.app.services.retriever import RetrievalEngine, RetrievedChunk
from backend.app.utils.text import (
    query_prefers_implementation,
    regulation_source_profile,
    regulation_title_authority,
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


def _chunk(
    *,
    title: str,
    text: str,
    relevance: float,
    rank: int,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"c{rank}",
        document_id=f"d{rank}",
        row_id=rank,
        rank=rank,
        raw_score=relevance,
        display_score=0.0,
        method="bm25+relevance_guard",
        text=text,
        title=title,
        category="regulations",
        page_start=1,
        page_end=2,
        article=None,
        note=None,
        chunk_order=rank,
        metadata={
            "relevance_score": relevance,
            "relevance_guard": {"local_window": text},
        },
    )


def test_direct_official_title_has_more_authority_than_compilation() -> None:
    assert regulation_title_authority("مقررات آموزشی ابلاغی 1402") > regulation_title_authority(
        "مجموعه مقررات آموزشی 1402"
    )


def test_derivative_compilation_is_detected_even_with_reversed_ocr_phrase() -> None:
    profile = regulation_source_profile(
        "مجموعه مقررات آموزشی 1402",
        "ماده 13 با استناد به ماده 26 آیین نامه، تمدید نیمسال ششم انجام می شود.",
    )
    reversed_profile = regulation_source_profile(
        "مجموعه مقررات آموزشی 1402",
        "26 ماده استناد با .13 ماده تمدید ششم نیمسال",
    )
    assert profile["derivative"] is True
    assert reversed_profile["derivative"] is True


def test_general_rule_prefers_direct_issued_regulation_over_local_extension_clause() -> None:
    engine = _engine()
    query = "حداکثر مدت مجاز تحصیل در دوره کارشناسی ارشد چند نیمسال است؟"
    local = _chunk(
        title="مجموعه مقررات آموزشی 1402",
        relevance=0.90,
        rank=1,
        text=(
            "ماده 13 با استناد به ماده 26 آیین نامه یکپارچه، تمدید سنوات "
            "در نیمسال پنجم و ششم با تصویب دانشگاه انجام می شود."
        ),
    )
    direct = _chunk(
        title="مقررات آموزشی ابلاغی 1402",
        relevance=0.72,
        rank=2,
        text=(
            "دوره کارشناسی ارشد ماده 26. مدت مجاز تحصیل در دوره کارشناسی ارشد "
            "4 نیمسال تحصیلی است. تبصره 1 مدت مجاز با تایید دانشگاه حداکثر "
            "1 نیمسال افزایش می یابد."
        ),
    )

    ranked = engine._apply_temporal_authority_policy(query, [local, direct])

    assert ranked[0].title == "مقررات آموزشی ابلاغی 1402"
    assert all(item.title != local.title for item in ranked)


def test_operational_question_can_prefer_implementation_guide() -> None:
    assert query_prefers_implementation(
        "درخواست تمدید سنوات را در کدام سامانه و طی چه مراحلی ثبت کنم؟"
    ) is True
    assert query_prefers_implementation(
        "حداکثر مدت مجاز تحصیل در کارشناسی ارشد چند نیمسال است؟"
    ) is False
