from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)

from backend.app.container import AppContainer
from backend.app.schemas import (
    ClientConfigResponse,
    DocumentResponse,
    HealthResponse,
    IndexStatusResponse,
    LLMConnectionTestRequest,
    LLMConnectionTestResponse,
    LLMModelsRequest,
    LLMModelsResponse,
    LLMSettingsResponse,
    LLMSettingsSaveRequest,
    QueryRequest,
    QueryResponse,
    QuestionSuggestionResponse,
    QuestionSuggestionsResponse,
    RetrievalModeOption,
    RebuildRequest,
    RebuildResponse,
    UploadResponse,
)

router = APIRouter(prefix="/api")


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_session_id(request: Request) -> str:
    session_id = getattr(request.state, "session_id", None)
    if not session_id:
        raise HTTPException(status_code=500, detail="Local session is unavailable.")
    return str(session_id)


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    container = get_container(request)
    session_id = get_session_id(request)
    retriever_status = container.retriever.status()
    llm_status = container.llm_settings.status(session_id)
    active = next(
        item for item in llm_status.providers if item.provider == llm_status.active_provider
    )
    generator_ready = bool(active.configured)

    if retriever_status["ready"] and generator_ready:
        overall = "ok"
    elif retriever_status["ready"]:
        overall = "degraded"
    else:
        overall = "unavailable"

    warnings = list(retriever_status.get("warnings", []))
    if retriever_status.get("error"):
        warnings.append(str(retriever_status["error"]))
    if not generator_ready:
        warnings.append(
            "مدل مولد هنوز در صفحه تنظیمات پیکربندی نشده است."
        )

    return HealthResponse(
        status=overall,
        version=container.settings.app_version,
        retriever_ready=bool(retriever_status["ready"]),
        generator_ready=generator_ready,
        provider=llm_status.active_provider,
        selected_retriever=retriever_status.get("method"),
        chunks=retriever_status.get("chunks"),
        documents=retriever_status.get("documents"),
        warnings=warnings,
        checked_at=datetime.now(timezone.utc),
    )


@router.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest, request: Request) -> QueryResponse:
    container = get_container(request)
    if not container.retriever.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=container.retriever.load_error or "Retriever is not ready.",
        )
    try:
        return container.rag.ask(
            session_id=get_session_id(request),
            question=payload.question,
            top_k=payload.top_k,
            category=payload.category,
            provider=payload.provider,
            model=payload.model,
            retrieval_mode=payload.retrieval_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"RAG request failed: {type(exc).__name__}: {exc}",
        ) from exc


@router.get("/questions/suggest", response_model=QuestionSuggestionsResponse)
def suggest_questions(
    request: Request,
    q: str = Query(min_length=2, max_length=300),
    limit: int = Query(default=5, ge=1, le=10),
) -> QuestionSuggestionsResponse:
    query_text = q.strip()
    if len(query_text) < 2:
        return QuestionSuggestionsResponse(query=query_text, count=0, suggestions=[])

    results = get_container(request).question_suggestions.suggest(
        query=query_text,
        limit=limit,
    )
    suggestions = [
        QuestionSuggestionResponse(
            id=item.id,
            question=item.question,
            source=item.source,
            difficulty=item.difficulty,
            question_type=item.question_type,
            score=item.score,
            match_type=item.match_type,
        )
        for item in results
    ]
    return QuestionSuggestionsResponse(
        query=query_text,
        count=len(suggestions),
        suggestions=suggestions,
    )


@router.get("/settings/llm", response_model=LLMSettingsResponse)
def get_llm_settings(request: Request) -> LLMSettingsResponse:
    return get_container(request).llm_settings.status(get_session_id(request))


@router.put("/settings/llm", response_model=LLMSettingsResponse)
def save_llm_settings(
    payload: LLMSettingsSaveRequest,
    request: Request,
) -> LLMSettingsResponse:
    try:
        return get_container(request).llm_settings.save(
            session_id=get_session_id(request),
            provider=payload.provider,
            model=payload.model,
            api_key=payload.api_key,
            remember_on_device=payload.remember_on_device,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/settings/llm", response_model=LLMSettingsResponse)
def delete_llm_settings(
    request: Request,
    provider: str | None = Query(default=None),
) -> LLMSettingsResponse:
    try:
        return get_container(request).llm_settings.delete(
            session_id=get_session_id(request),
            provider=provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/settings/llm/models", response_model=LLMModelsResponse)
def list_llm_models(
    payload: LLMModelsRequest,
    request: Request,
) -> LLMModelsResponse:
    try:
        return get_container(request).llm_settings.list_models(
            session_id=get_session_id(request),
            provider=payload.provider,
            api_key=payload.api_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"دریافت مدل‌ها ناموفق بود: {type(exc).__name__}: {exc}",
        ) from exc


@router.post("/settings/llm/test", response_model=LLMConnectionTestResponse)
def test_llm_connection(
    payload: LLMConnectionTestRequest,
    request: Request,
) -> LLMConnectionTestResponse:
    try:
        return get_container(request).llm_settings.test_connection(
            session_id=get_session_id(request),
            provider=payload.provider,
            model=payload.model,
            api_key=payload.api_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"آزمایش اتصال ناموفق بود: {type(exc).__name__}: {exc}",
        ) from exc


@router.get("/documents", response_model=list[DocumentResponse])
def documents(request: Request) -> list[DocumentResponse]:
    return get_container(request).documents.list_documents()


@router.get("/categories", response_model=list[str])
def categories(request: Request) -> list[str]:
    return get_container(request).documents.categories()


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
) -> UploadResponse:
    try:
        return await get_container(request).documents.save_upload(file, category)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/index/rebuild", response_model=RebuildResponse)
def rebuild_index(
    payload: RebuildRequest,
    request: Request,
) -> RebuildResponse:
    manager = get_container(request).indexing
    try:
        accepted = manager.start(
            run_data_preparation=payload.run_data_preparation,
            run_retrieval=payload.run_retrieval,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RebuildResponse(
        accepted=accepted,
        status="running" if accepted else "already_running",
        message=(
            "بازسازی ایندکس در پس‌زمینه شروع شد."
            if accepted
            else "یک بازسازی دیگر هم‌اکنون در حال اجراست."
        ),
    )


@router.get("/index/status", response_model=IndexStatusResponse)
def index_status(request: Request) -> IndexStatusResponse:
    return IndexStatusResponse(**get_container(request).indexing.status())


@router.get("/config/client", response_model=ClientConfigResponse)
def client_config(request: Request) -> ClientConfigResponse:
    container = get_container(request)
    llm_status = container.llm_settings.status(get_session_id(request))
    selected = next(
        item for item in llm_status.providers if item.provider == llm_status.active_provider
    )

    retriever_status = container.retriever.status()
    best_method = str(retriever_status.get("best_method") or "bm25")
    hybrid_available = bool(retriever_status.get("hybrid_available"))

    return ClientConfigResponse(
        provider=llm_status.active_provider,
        model=selected.model or "",
        default_top_k=container.settings.default_top_k,
        maximum_top_k=container.settings.maximum_top_k,
        categories=container.documents.categories(),
        upload_enabled=container.settings.enable_document_upload,
        rebuild_enabled=container.settings.enable_index_rebuild,
        llm_settings_enabled=True,
        default_retrieval_mode=(
            "hybrid"
            if hybrid_available
            else container.settings.default_retrieval_mode
        ),
        best_retriever_method=best_method,
        hybrid_available=hybrid_available,
        retrieval_modes=[
            RetrievalModeOption(
                value="best",
                label="روش مبنا (BM25)",
                description=(
                    "روش برتر مرحله بازیابی در Notebook 02 "
                    f"({best_method}) برای مقایسه با روش نهایی."
                ),
                resolved_method=best_method,
                available=True,
            ),
            RetrievalModeOption(
                value="hybrid",
                label="روش برتر ارزیابی نهایی",
                description=(
                    "Hybrid منتخب آزمون ۱۰۰ سؤالی: ترکیب BM25 و E5/FAISS "
                    "با RRF، Cross-Encoder و فیلتر ارتباط."
                ),
                resolved_method=str(
                    retriever_status.get("hybrid_method") or "hybrid"
                ),
                available=hybrid_available,
            ),
        ],
    )


@router.get("/evaluation/summary")
def evaluation_summary(request: Request) -> dict[str, Any]:
    root = get_container(request).settings.university_rag_root
    retrieval_report = (
        root / "data" / "retrieval" / "reports" / "model_comparison.csv"
    )
    generation_report = (
        root / "data" / "generation" / "reports" / "experiment_comparison.csv"
    )

    result: dict[str, Any] = {
        "retrieval": None,
        "generation": None,
        "note": (
            "Silver benchmark results are development-only until a manually "
            "reviewed gold benchmark is available."
        ),
    }

    if retrieval_report.exists():
        frame = pd.read_csv(retrieval_report)
        result["retrieval"] = frame.replace({float("nan"): None}).to_dict(
            orient="records"
        )
    if generation_report.exists():
        frame = pd.read_csv(generation_report)
        result["generation"] = frame.replace({float("nan"): None}).to_dict(
            orient="records"
        )

    return result
