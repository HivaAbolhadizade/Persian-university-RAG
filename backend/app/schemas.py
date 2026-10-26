from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ProviderName = Literal["mock", "openai", "gemini"]
RetrievalMode = Literal["best", "hybrid"]


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    category: str | None = Field(default=None, max_length=100)
    provider: ProviderName | None = None
    model: str | None = Field(default=None, max_length=200)
    retrieval_mode: RetrievalMode = "best"
    force_refresh: bool = False

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question cannot be empty.")
        return value

    @field_validator("category", "model")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class QuestionSuggestionResponse(BaseModel):
    id: int
    question: str
    source: str | None = None
    difficulty: str | None = None
    question_type: str | None = None
    score: float = Field(ge=0.0, le=1.0)
    match_type: Literal["exact", "prefix", "contains", "token", "fuzzy"]


class QuestionSuggestionsResponse(BaseModel):
    query: str
    count: int
    suggestions: list[QuestionSuggestionResponse] = Field(default_factory=list)


class SourceResponse(BaseModel):
    source_id: str
    title: str
    category: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    article: str | None = None
    note: str | None = None
    chunk_id: str
    document_id: str | None = None
    score: float
    text: str


class QueryResponse(BaseModel):
    question: str
    answer: str
    citations: list[str]
    no_answer: bool
    confidence: float = Field(ge=0.0, le=1.0)
    provider_alias: str
    model: str
    retriever_method: str
    latency_seconds: float
    sources: list[SourceResponse]
    diagnostics: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    retriever_ready: bool
    generator_ready: bool
    provider: str
    selected_retriever: str | None = None
    chunks: int | None = None
    documents: int | None = None
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime


class DocumentResponse(BaseModel):
    document_id: str
    title: str
    category: str | None = None
    filename: str | None = None
    page_count: int | None = None
    chunk_count: int | None = None
    validation_status: str | None = None
    ready_for_retrieval: bool | None = None
    document_type: str | None = None
    publication_year: int | None = None


class UploadResponse(BaseModel):
    filename: str
    category: str
    stored_path: str
    size_bytes: int
    status: str
    message: str


class RebuildRequest(BaseModel):
    run_data_preparation: bool = True
    run_retrieval: bool = True


class RebuildResponse(BaseModel):
    accepted: bool
    status: str
    message: str


class IndexStatusResponse(BaseModel):
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    current_stage: str | None = None
    error: str | None = None
    log_path: str | None = None


class RetrievalModeOption(BaseModel):
    value: RetrievalMode
    label: str
    description: str
    resolved_method: str
    available: bool = True


class ClientConfigResponse(BaseModel):
    provider: str
    model: str
    default_top_k: int
    maximum_top_k: int
    categories: list[str]
    upload_enabled: bool
    rebuild_enabled: bool
    llm_settings_enabled: bool = True
    default_retrieval_mode: RetrievalMode = "best"
    retrieval_modes: list[RetrievalModeOption] = Field(default_factory=list)
    best_retriever_method: str = "bm25"
    hybrid_available: bool = False


class ProviderStatus(BaseModel):
    provider: ProviderName
    configured: bool
    selected: bool
    model: str | None = None
    key_preview: str | None = None
    remembered_on_device: bool = False


class LLMSettingsResponse(BaseModel):
    active_provider: ProviderName
    providers: list[ProviderStatus]
    session_storage: str = "http_only_cookie_plus_backend_memory"
    persistent_storage: str = "windows_credential_manager_when_enabled"
    key_is_returned_to_frontend: bool = False


class LLMSettingsSaveRequest(BaseModel):
    provider: ProviderName
    model: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=500)
    remember_on_device: bool = False

    @field_validator("model", "api_key")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class LLMModelsRequest(BaseModel):
    provider: Literal["openai", "gemini"]
    api_key: str | None = Field(default=None, max_length=500)

    @field_validator("api_key")
    @classmethod
    def clean_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class LLMModelInfo(BaseModel):
    id: str
    display_name: str
    provider: Literal["openai", "gemini"]


class LLMModelsResponse(BaseModel):
    provider: Literal["openai", "gemini"]
    models: list[LLMModelInfo]


class LLMConnectionTestRequest(BaseModel):
    provider: Literal["openai", "gemini"]
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=500)

    @field_validator("model")
    @classmethod
    def clean_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Model is required.")
        return value

    @field_validator("api_key")
    @classmethod
    def clean_test_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class LLMConnectionTestResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    latency_seconds: float
    message: str
