from backend.app.schemas import (
    LLMSettingsSaveRequest,
    QueryRequest,
    QueryResponse,
    SourceResponse,
)


def test_frontend_query_contract() -> None:
    request = QueryRequest(
        question="شرایط مهمانی دانشجو چیست؟",
        top_k=5,
        category=None,
    )
    assert request.top_k == 5
    assert request.retrieval_mode == "best"

    hybrid_request = QueryRequest(
        question="شرایط مهمانی دانشجو چیست؟",
        retrieval_mode="hybrid",
    )
    assert hybrid_request.retrieval_mode == "hybrid"


def test_frontend_response_contract() -> None:
    response = QueryResponse(
        question="سؤال",
        answer="پاسخ [S1]",
        citations=["S1"],
        no_answer=False,
        confidence=0.8,
        provider_alias="mock_extractive",
        model="extractive-baseline-v1",
        retriever_method="bm25",
        latency_seconds=0.1,
        sources=[
            SourceResponse(
                source_id="S1",
                title="آیین‌نامه",
                category="regulations",
                page_start=1,
                page_end=1,
                article="2",
                note=None,
                chunk_id="chunk_1",
                document_id="doc_1",
                score=0.9,
                text="متن",
            )
        ],
    )
    payload = response.model_dump()
    assert payload["sources"][0]["source_id"] == "S1"


def test_runtime_settings_contract() -> None:
    payload = LLMSettingsSaveRequest(
        provider="gemini",
        model="gemini-model-id",
        api_key="secret",
        remember_on_device=True,
    )
    assert payload.provider == "gemini"
    assert payload.remember_on_device is True
