from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def discover_project_root() -> Path:
    """Resolve the University_RAG root without depending on the launch directory."""
    configured = os.getenv("UNIVERSITY_RAG_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    current_file = Path(__file__).resolve()
    candidates = [
        current_file.parents[2],
        Path.cwd().resolve(),
        *Path.cwd().resolve().parents,
    ]
    for candidate in candidates:
        if (candidate / "data").exists() and (
            (candidate / "backend").exists() or (candidate / "notebooks").exists()
        ):
            return candidate

    return current_file.parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "University RAG API"
    app_version: str = "2.4.0"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False

    university_rag_root: Path = Field(default_factory=discover_project_root)

    # Use the same hostname for frontend and backend (recommended: 127.0.0.1)
    # so the HttpOnly cookie remains same-site.
    cors_origins: str = (
        "http://127.0.0.1:5173,http://127.0.0.1:4173,"
        "http://localhost:5173,http://localhost:4173"
    )
    trusted_hosts: str = "127.0.0.1,localhost,testserver"

    session_cookie_name: str = "university_rag_session"
    session_cookie_max_age_seconds: int = 60 * 60 * 24 * 30
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "strict"

    # The default is only used before the user saves settings in the UI.
    llm_provider: Literal["mock", "openai", "gemini"] = "mock"
    # A failed real provider must never silently turn into an extractive mock
    # answer.  The mock provider remains available when the user explicitly
    # selects it from Settings.
    allow_mock_fallback: bool = False
    openai_api_key: str | None = None
    openai_model: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None

    maximum_output_tokens: int = 900
    generation_temperature: float = 0.0
    request_timeout_seconds: float = 90.0
    api_retry_attempts: int = 3

    keyring_service_name: str = "University_RAG_Local"
    persisted_llm_metadata_file: str = "llm_settings.json"

    default_top_k: int = 5
    maximum_top_k: int = 10
    retrieval_candidate_k: int = 30
    maximum_chunks_per_document: int = 3
    use_retrieval_threshold: bool = True
    use_reranker: bool = True
    minimum_relevance_score: float = 0.28
    hybrid_minimum_relevance_score: float = 0.32
    default_retrieval_mode: Literal["best", "hybrid"] = "hybrid"
    hybrid_dense_alias: str | None = None

    # Question autocomplete uses question text/metadata only; answers are never exposed.
    question_suggestions_path: str | None = None

    # Runtime policy for overlapping regulations.  When a newer, equally
    # relevant regulation is present, older versions are demoted or excluded
    # unless the user explicitly asks for a historical year.
    prefer_latest_regulations: bool = True
    preferred_regulation_year: int | None = None
    latest_document_bonus: float = 0.18
    stale_document_penalty: float = 0.30
    stale_year_gap: int = 2
    stale_filter_relevance_margin: float = 0.18
    long_chunk_penalty_max: float = 0.22
    preferred_chunk_characters: int = 3_500
    preferred_page_span: int = 8

    maximum_context_characters: int = 24_000
    maximum_source_characters: int = 5_000
    context_excerpt_characters: int = 2_400

    maximum_upload_mb: int = 40
    enable_document_upload: bool = True
    enable_index_rebuild: bool = False
    rebuild_notebook_01: str = "notebooks/01_Data_Preparation.ipynb"
    rebuild_notebook_02: str = "notebooks/02_Retrieval_Pipeline.ipynb"

    @field_validator("university_rag_root", mode="before")
    @classmethod
    def normalize_root(cls, value: object) -> Path:
        return Path(str(value)).expanduser().resolve()

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

    @property
    def chunks_path(self) -> Path:
        return self.university_rag_root / "data" / "processed" / "chunks.parquet"

    @property
    def documents_path(self) -> Path:
        return self.university_rag_root / "data" / "processed" / "documents.parquet"

    @property
    def retrieval_config_path(self) -> Path:
        return self.university_rag_root / "retrieval_config.yaml"

    @property
    def index_manifest_path(self) -> Path:
        return (
            self.university_rag_root
            / "data"
            / "retrieval"
            / "indexes"
            / "index_manifest.json"
        )

    @property
    def best_retriever_path(self) -> Path:
        return (
            self.university_rag_root
            / "data"
            / "retrieval"
            / "reports"
            / "best_retriever_config.yaml"
        )

    @property
    def threshold_path(self) -> Path:
        return (
            self.university_rag_root
            / "data"
            / "retrieval"
            / "reports"
            / "threshold_calibration.csv"
        )

    @property
    def raw_data_path(self) -> Path:
        return self.university_rag_root / "data" / "raw"

    @property
    def backend_runtime_path(self) -> Path:
        return self.university_rag_root / "data" / "backend_runtime"

    @property
    def persisted_llm_metadata_path(self) -> Path:
        return self.backend_runtime_path / self.persisted_llm_metadata_file


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
