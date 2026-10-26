from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import UploadFile

from backend.app.config import Settings
from backend.app.schemas import DocumentResponse, UploadResponse

DEFAULT_CATEGORIES = [
    "exams",
    "master_phd",
    "phd",
    "regulations",
    "transfer",
    "tuition",
    "undergraduate",
]


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if value is None or pd.isna(value):
        return None
    return bool(value)


def _optional_str(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


class DocumentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def categories(self) -> list[str]:
        existing = []
        if self.settings.raw_data_path.exists():
            existing = sorted(
                path.name
                for path in self.settings.raw_data_path.iterdir()
                if path.is_dir()
            )
        return sorted(set(DEFAULT_CATEGORIES) | set(existing))

    def list_documents(self) -> list[DocumentResponse]:
        if self.settings.documents_path.exists():
            frame = pd.read_parquet(self.settings.documents_path)
        elif self.settings.chunks_path.exists():
            chunks = pd.read_parquet(self.settings.chunks_path)
            aggregations: dict[str, Any] = {
                "title": ("title", "first"),
                "category": ("category", "first"),
                "chunk_count": ("chunk_id", "count"),
            }
            if "page_end" in chunks.columns:
                aggregations["page_count"] = ("page_end", "max")
            frame = (
                chunks.groupby("document_id", as_index=False)
                .agg(**aggregations)
            )
        else:
            return []

        results: list[DocumentResponse] = []
        for _, row in frame.iterrows():
            document_id = str(row.get("document_id", "") or "")
            if not document_id:
                continue
            results.append(
                DocumentResponse(
                    document_id=document_id,
                    title=str(row.get("title", "") or row.get("filename", "") or document_id),
                    category=_optional_str(row.get("category")),
                    filename=_optional_str(row.get("filename")),
                    page_count=_optional_int(row.get("page_count")),
                    chunk_count=_optional_int(row.get("chunk_count")),
                    validation_status=_optional_str(row.get("validation_status")),
                    ready_for_retrieval=_optional_bool(row.get("ready_for_retrieval")),
                    document_type=_optional_str(row.get("document_type")),
                    publication_year=_optional_int(row.get("publication_year")),
                )
            )
        return results

    @staticmethod
    def _safe_filename(filename: str) -> str:
        base = Path(filename).name
        stem = re.sub(r"[^\wآ-ی\-(). ]+", "_", Path(base).stem, flags=re.UNICODE)
        stem = re.sub(r"\s+", "_", stem).strip("._")
        return f"{stem or 'document'}.pdf"

    async def save_upload(
        self,
        upload: UploadFile,
        category: str,
    ) -> UploadResponse:
        if not self.settings.enable_document_upload:
            raise PermissionError("Document upload is disabled.")

        normalized_category = category.strip().lower()
        if normalized_category not in self.categories():
            raise ValueError(
                f"Unknown category: {normalized_category}. "
                f"Allowed: {', '.join(self.categories())}"
            )

        original_name = upload.filename or "document.pdf"
        if Path(original_name).suffix.lower() != ".pdf":
            raise ValueError("Only PDF files are accepted.")

        content = await upload.read()
        maximum_bytes = self.settings.maximum_upload_mb * 1024 * 1024
        if not content:
            raise ValueError("Uploaded file is empty.")
        if len(content) > maximum_bytes:
            raise ValueError(
                f"File is larger than {self.settings.maximum_upload_mb} MB."
            )
        if not content.startswith(b"%PDF"):
            raise ValueError("The uploaded file does not have a valid PDF header.")

        target_dir = self.settings.raw_data_path / normalized_category
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = self._safe_filename(original_name)
        target = target_dir / filename

        counter = 1
        while target.exists():
            target = target_dir / f"{Path(filename).stem}_{counter}.pdf"
            counter += 1

        target.write_bytes(content)
        relative = target.relative_to(self.settings.university_rag_root).as_posix()

        return UploadResponse(
            filename=target.name,
            category=normalized_category,
            stored_path=relative,
            size_bytes=len(content),
            status="uploaded_pending_rebuild",
            message=(
                "فایل ذخیره شد. برای ورود به سامانه باید Data Preparation و "
                "Retrieval Index دوباره اجرا شوند."
            ),
        )
