from __future__ import annotations

import json
import logging
import math
import pickle
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd
import yaml
from rank_bm25 import BM25Okapi

from backend.app.config import Settings
from backend.app.utils.text import (
    bm25_tokenize,
    expand_query,
    extract_article_number,
    lexical_relevance_features,
    local_lexical_relevance_features,
    normalize_persian_query,
    extract_solar_years,
    regulation_title_authority,
    regulation_source_profile,
    query_prefers_implementation,
    text_jaccard,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    row_id: int
    rank: int
    raw_score: float
    display_score: float
    method: str
    text: str
    title: str
    category: str | None
    page_start: int | None
    page_end: int | None
    article: str | None
    note: str | None
    chunk_order: int | None
    metadata: dict[str, Any] = field(default_factory=dict)


class RetrievalEngine:
    """Loads Notebook 02 artifacts once and serves thread-safe retrieval."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self.ready = False
        self.load_error: str | None = None
        self.warnings: list[str] = []

        self.chunks_df = pd.DataFrame()
        self.retrieval_config: dict[str, Any] = {}
        self.manifest: dict[str, Any] = {}
        self.best_config: dict[str, Any] = {}

        # ``method`` remains the scientifically selected Notebook 02 method.
        self.method = "bm25"
        self.best_method = "bm25"
        self.best_dense_alias = ""
        self.hybrid_dense_alias = ""
        self.hybrid_available = False
        self.benchmark_label = ""
        self.selection_status = ""
        self.score_threshold: float | None = None
        self.latest_regulation_year: int | None = None

        self.bm25_model: Any = None
        # Dense assets are cached by alias so per-request retrieval choices are
        # thread-safe and never mutate a global active retriever.
        self.dense_models: dict[str, Any] = {}
        self.dense_indexes: dict[str, Any] = {}
        self.document_embeddings: dict[str, np.ndarray] = {}
        self.dense_query_prefixes: dict[str, str] = {}
        self.reranker: Any = None
        self.reranker_model_name = ""
        self._reranker_load_attempted = False

    @property
    def chunk_count(self) -> int:
        return int(len(self.chunks_df))

    @property
    def document_count(self) -> int:
        if self.chunks_df.empty:
            return 0
        return int(self.chunks_df["document_id"].astype(str).nunique())

    def _absolute_path(self, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.settings.university_rag_root / path
        return path.resolve()

    def load(self) -> None:
        with self._lock:
            self.ready = False
            self.load_error = None
            self.warnings.clear()
            try:
                self._load_impl()
                self.ready = True
                logger.info(
                    "Retriever loaded: method=%s chunks=%s documents=%s",
                    self.method,
                    self.chunk_count,
                    self.document_count,
                )
            except Exception as exc:
                self.load_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Retriever failed to load.")
                raise

    def _load_impl(self) -> None:
        required = [
            self.settings.chunks_path,
            self.settings.retrieval_config_path,
            self.settings.index_manifest_path,
            self.settings.best_retriever_path,
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "Required Notebook 02 outputs are missing: " + ", ".join(missing)
            )

        self.chunks_df = pd.read_parquet(self.settings.chunks_path).reset_index(drop=True)
        self.chunks_df["row_id"] = np.arange(len(self.chunks_df), dtype=np.int64)
        self.retrieval_config = yaml.safe_load(
            self.settings.retrieval_config_path.read_text(encoding="utf-8")
        ) or {}
        self.manifest = json.loads(
            self.settings.index_manifest_path.read_text(encoding="utf-8")
        )
        self.best_config = yaml.safe_load(
            self.settings.best_retriever_path.read_text(encoding="utf-8")
        ) or {}

        required_columns = {
            "chunk_id",
            "document_id",
            "text",
            "title",
            "category",
            "page_start",
            "page_end",
        }
        missing_columns = sorted(required_columns - set(self.chunks_df.columns))
        if missing_columns:
            raise ValueError(f"chunks.parquet is missing columns: {missing_columns}")

        chunk_ids = self.chunks_df["chunk_id"].astype(str).tolist()
        manifest_ids = list(map(str, self.manifest.get("chunk_id_order", [])))
        if chunk_ids != manifest_ids:
            raise ValueError(
                "chunks.parquet order does not match index_manifest.json. "
                "Run corrected Notebook 02 again."
            )

        self.selection_status = str(self.best_config.get("selection_status", ""))
        if self.selection_status not in {"provisional_silver", "final_gold"}:
            raise RuntimeError(
                "best_retriever_config.yaml was not produced by the corrected Notebook 02."
            )

        self.best_method = str(self.best_config.get("method", "bm25")).lower()
        self.method = self.best_method
        self.best_dense_alias = str(self.best_config.get("dense_alias") or "")
        self.hybrid_dense_alias = self._resolve_hybrid_dense_alias()
        self.hybrid_available = self._dense_alias_is_available(
            self.hybrid_dense_alias
        )
        self.benchmark_label = str(self.best_config.get("benchmark_label", ""))
        self._load_bm25()
        # Keep startup light when the evaluated best method is BM25. Dense
        # assets for Hybrid mode are loaded lazily on its first request.
        if self._requires_dense(self.best_method):
            self._load_dense_alias(self.best_dense_alias)
        self._configure_reranker()
        self.score_threshold = self._load_threshold()
        self.latest_regulation_year = self._resolve_latest_regulation_year()

    def _load_bm25(self) -> None:
        manifest_bm25 = self.manifest.get("bm25", {})
        index_path = self._absolute_path(manifest_bm25.get("index_path", ""))
        corpus_path = self._absolute_path(manifest_bm25.get("corpus_path", ""))

        try:
            with index_path.open("rb") as handle:
                self.bm25_model = pickle.load(handle)
        except Exception as exc:
            self.warnings.append(
                f"BM25 pickle could not be loaded; rebuilt in memory: {exc}"
            )
            corpus_text = self._retrieval_text_series().tolist()
            bm25_cfg = self.retrieval_config.get("bm25", {})
            self.bm25_model = BM25Okapi(
                [bm25_tokenize(text) for text in corpus_text],
                k1=float(bm25_cfg.get("k1", 1.5)),
                b=float(bm25_cfg.get("b", 0.75)),
            )

        if corpus_path.exists():
            try:
                bundle = joblib.load(corpus_path)
                saved_ids = list(map(str, bundle.get("chunk_ids", [])))
                if saved_ids and saved_ids != self.chunks_df["chunk_id"].astype(str).tolist():
                    raise ValueError("BM25 corpus chunk order mismatch.")
            except Exception as exc:
                self.warnings.append(f"BM25 corpus validation warning: {exc}")

    def _retrieval_text_series(self) -> pd.Series:
        if "retrieval_text" in self.chunks_df.columns:
            return self.chunks_df["retrieval_text"].fillna("").astype(str)
        return self.chunks_df.apply(
            lambda row: " | ".join(
                value
                for value in [
                    str(row.get("title", "") or ""),
                    str(row.get("category", "") or ""),
                    (
                        f"ماده {row.get('article')}"
                        if pd.notna(row.get("article")) and str(row.get("article")).strip()
                        else ""
                    ),
                    str(row.get("text", "") or ""),
                ]
                if value
            ),
            axis=1,
        )

    @staticmethod
    def _requires_dense(method: str) -> bool:
        normalized = str(method or "").lower()
        return any(
            token in normalized for token in ("dense", "hybrid", "rrf", "mmr")
        )

    def _resolve_hybrid_dense_alias(self) -> str:
        candidates = [
            self.settings.hybrid_dense_alias,
            self.retrieval_config.get("dense", {}).get("default_model_alias"),
            self.best_config.get("dense_alias"),
        ]
        candidates.extend(
            self.manifest.get("embedding_models", {}).keys()
        )
        for candidate in candidates:
            alias = str(candidate or "").strip()
            if alias and self._dense_alias_is_available(alias):
                return alias
        return ""

    def _dense_alias_is_available(self, alias: str) -> bool:
        if not alias:
            return False
        dense_manifest = self.manifest.get("embedding_models", {}).get(alias)
        if not dense_manifest:
            return False
        embedding_path = dense_manifest.get("embedding_path")
        faiss_path = dense_manifest.get("faiss_index_path")
        if not embedding_path or not faiss_path:
            return False
        return (
            self._absolute_path(embedding_path).exists()
            and self._absolute_path(faiss_path).exists()
        )

    def _load_dense_alias(self, alias: str) -> None:
        alias = str(alias or "").strip()
        if not alias:
            raise ValueError("A dense model alias is required for this retriever.")
        if alias in self.dense_models:
            return

        dense_manifest = self.manifest.get("embedding_models", {}).get(alias)
        if not dense_manifest:
            raise KeyError(f"Dense model alias is missing from manifest: {alias}")

        try:
            import faiss
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RuntimeError(
                "Selected retriever needs sentence-transformers and faiss-cpu."
            ) from exc

        model_name = str(dense_manifest["model_name"])
        config_candidates = [
            item
            for item in self.retrieval_config.get("embedding_models", [])
            if str(item.get("alias")) == alias
        ]
        model_cfg = config_candidates[0] if config_candidates else {}
        query_prefix = str(model_cfg.get("query_prefix", ""))

        model = SentenceTransformer(model_name)
        faiss_path = self._absolute_path(dense_manifest["faiss_index_path"])
        index = faiss.read_index(str(faiss_path))
        if int(index.ntotal) != len(self.chunks_df):
            raise ValueError("FAISS index row count does not match chunks.parquet.")

        embedding_path = self._absolute_path(dense_manifest["embedding_path"])
        embeddings = np.load(embedding_path, mmap_mode="r")
        if embeddings.shape[0] != len(self.chunks_df):
            raise ValueError("Embedding row count does not match chunks.parquet.")

        self.dense_models[alias] = model
        self.dense_indexes[alias] = index
        self.document_embeddings[alias] = embeddings
        self.dense_query_prefixes[alias] = query_prefix

    def _configure_reranker(self) -> None:
        self.reranker = None
        self._reranker_load_attempted = False
        reranker_cfg = self.retrieval_config.get("reranker", {})
        model_name = (
            self.best_config.get("reranker_model_name")
            or reranker_cfg.get("model_name")
        )
        self.reranker_model_name = str(model_name or "").strip()
        if not (self.settings.use_reranker and self.reranker_model_name):
            return

        # Keep startup fast.  Load only when the scientifically selected method
        # needs it immediately; Hybrid mode loads it lazily on first use.
        if "reranker" in self.best_method:
            self._ensure_reranker()

    def _ensure_reranker(self) -> bool:
        if self.reranker is not None:
            return True
        if self._reranker_load_attempted:
            return False
        if not (self.settings.use_reranker and self.reranker_model_name):
            return False

        self._reranker_load_attempted = True
        try:
            from sentence_transformers import CrossEncoder

            reranker_cfg = self.retrieval_config.get("reranker", {})
            kwargs: dict[str, Any] = {}
            if reranker_cfg.get("max_length"):
                kwargs["max_length"] = int(reranker_cfg["max_length"])
            self.reranker = CrossEncoder(self.reranker_model_name, **kwargs)
            return True
        except Exception as exc:
            warning = f"Reranker could not be loaded; continuing without it: {exc}"
            self.warnings.append(warning)
            logger.warning(warning)
            return False

    def _load_threshold(self) -> float | None:
        if not self.settings.use_retrieval_threshold:
            return None
        if not self.settings.threshold_path.exists():
            return None
        try:
            frame = pd.read_csv(self.settings.threshold_path)
            matching = frame[
                frame["benchmark_label"].astype(str) == self.benchmark_label
            ]
            if matching.empty:
                return None
            value = matching.iloc[0].get("threshold")
            return float(value) if pd.notna(value) else None
        except Exception as exc:
            self.warnings.append(f"Threshold could not be loaded: {exc}")
            return None


    @staticmethod
    def _row_document_label(row: pd.Series | dict[str, Any]) -> str:
        values: list[str] = []
        for key in (
            "title",
            "document_title",
            "source_filename",
            "filename",
            "file_name",
            "source_path",
            "path",
        ):
            try:
                value = row.get(key)
            except AttributeError:
                value = None
            if value is not None and not pd.isna(value):
                text = str(value).strip()
                if text:
                    values.append(text)
        return " | ".join(values)

    def _resolve_latest_regulation_year(self) -> int | None:
        configured = self.settings.preferred_regulation_year
        if configured is not None:
            return int(configured)

        years: list[int] = []
        seen_documents: set[str] = set()
        for _, row in self.chunks_df.iterrows():
            document_id = str(row.get("document_id", ""))
            if document_id in seen_documents:
                continue
            seen_documents.add(document_id)
            label = self._row_document_label(row)
            normalized = normalize_persian_query(label).lower()
            if not any(
                token in normalized
                for token in (
                    "مقررات آموزشی",
                    "آیین نامه",
                    "آیین‌نامه",
                    "شیوه نامه",
                    "شیوه‌نامه",
                )
            ):
                continue
            years.extend(extract_solar_years(label))

        return max(years) if years else None

    @staticmethod
    def _item_document_year(item: RetrievedChunk) -> int | None:
        label_parts = [item.title]
        for key in (
            "document_title",
            "source_filename",
            "filename",
            "file_name",
            "source_path",
            "path",
        ):
            value = item.metadata.get(key)
            if value is not None and not pd.isna(value):
                label_parts.append(str(value))
        years = extract_solar_years(" | ".join(label_parts))
        return max(years) if years else None

    @staticmethod
    def _query_requested_year(query: str) -> int | None:
        years = extract_solar_years(query)
        return max(years) if years else None

    def _chunk_scope_penalty(self, item: RetrievedChunk) -> float:
        preferred_chars = max(int(self.settings.preferred_chunk_characters), 500)
        text_length = len(item.text)
        char_excess = max(text_length - preferred_chars, 0)
        char_penalty = min(
            char_excess / max(preferred_chars * 5.0, 1.0),
            float(self.settings.long_chunk_penalty_max),
        )

        page_penalty = 0.0
        if item.page_start is not None and item.page_end is not None:
            page_span = max(item.page_end - item.page_start + 1, 1)
            preferred_span = max(int(self.settings.preferred_page_span), 1)
            if page_span > preferred_span:
                page_penalty = min(
                    (page_span - preferred_span) / (preferred_span * 12.0),
                    float(self.settings.long_chunk_penalty_max),
                )

        article_markers = len(
            set(
                re.findall(
                    r"(?:ماده|تبصره|بند)\s*([0-9۰-۹]+)",
                    str(item.text or ""),
                )
            )
        )
        multi_article_penalty = min(max(article_markers - 3, 0) * 0.012, 0.10)
        return float(
            min(
                max(char_penalty, page_penalty) + multi_article_penalty,
                float(self.settings.long_chunk_penalty_max),
            )
        )

    def _source_policy_profile(
        self,
        query: str,
        item: RetrievedChunk,
    ) -> dict[str, Any]:
        guard = item.metadata.get("relevance_guard") or {}
        local_window = str(guard.get("local_window") or item.text or "")
        profile = regulation_source_profile(item.title, local_window)
        implementation_intent = query_prefers_implementation(query)

        if implementation_intent:
            type_adjustment = {
                "official_circular": 0.08,
                "unified_regulation": 0.08,
                "regulation_document": 0.06,
                "regulation_compilation": 0.08,
                "implementation_guide": 0.18,
                "other": 0.0,
            }.get(str(profile["source_type"]), 0.0)
        else:
            type_adjustment = {
                "official_circular": 0.28,
                "unified_regulation": 0.24,
                "regulation_document": 0.14,
                "regulation_compilation": 0.07,
                "implementation_guide": -0.16,
                "other": -0.04,
            }.get(str(profile["source_type"]), 0.0)
            if profile.get("derivative"):
                type_adjustment -= 0.24
            if profile.get("direct_rule"):
                type_adjustment += 0.06

        return {
            **profile,
            "implementation_intent": implementation_intent,
            "adjustment": round(float(type_adjustment), 4),
        }

    def _temporal_authority_adjustment(
        self,
        query: str,
        item: RetrievedChunk,
    ) -> tuple[float, dict[str, Any]]:
        document_year = self._item_document_year(item)
        requested_year = self._query_requested_year(query)
        latest_year = self.latest_regulation_year
        title_authority = regulation_title_authority(item.title)
        source_policy = self._source_policy_profile(query, item)
        scope_penalty = self._chunk_scope_penalty(item)

        adjustment = float(source_policy["adjustment"]) - scope_penalty
        stale = False
        explicit_year_match: bool | None = None

        if requested_year is not None:
            explicit_year_match = document_year == requested_year
            if document_year == requested_year:
                adjustment += 0.24
            elif document_year is not None:
                adjustment -= 0.32
        elif (
            self.settings.prefer_latest_regulations
            and latest_year is not None
            and document_year is not None
        ):
            gap = latest_year - document_year
            if gap <= 0:
                adjustment += float(self.settings.latest_document_bonus)
            elif gap >= int(self.settings.stale_year_gap):
                stale = True
                scaled_penalty = min(
                    float(self.settings.stale_document_penalty)
                    * (1.0 + 0.12 * max(gap - int(self.settings.stale_year_gap), 0)),
                    0.48,
                )
                adjustment -= scaled_penalty
            else:
                adjustment -= 0.05

        return float(adjustment), {
            "document_year": document_year,
            "requested_year": requested_year,
            "latest_regulation_year": latest_year,
            "title_authority": round(float(title_authority), 4),
            "source_policy": source_policy,
            "scope_penalty": round(float(scope_penalty), 4),
            "stale": stale,
            "explicit_year_match": explicit_year_match,
            "adjustment": round(float(adjustment), 4),
        }

    def _apply_temporal_authority_policy(
        self,
        query: str,
        candidates: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        requested_year = self._query_requested_year(query)
        enriched: list[RetrievedChunk] = []
        for item in candidates:
            adjustment, policy = self._temporal_authority_adjustment(query, item)
            relevance = float(item.metadata.get("relevance_score", 0.0))
            final_score = float(np.clip(relevance + adjustment, 0.0, 1.0))
            item.metadata = {
                **item.metadata,
                "temporal_authority": policy,
                "ranking_score": final_score,
            }
            enriched.append(item)

        # If the user did not request a historical year, remove an older
        # regulation only when it is clearly weaker than an available newer
        # candidate. Comparable old evidence is retained at most once and is
        # labelled as stale so generation can resolve conflicts safely.
        if requested_year is None and self.settings.prefer_latest_regulations:
            non_stale = [
                item
                for item in enriched
                if not bool(
                    (item.metadata.get("temporal_authority") or {}).get("stale")
                )
                and (item.metadata.get("temporal_authority") or {}).get("document_year")
                is not None
            ]
            if non_stale:
                strongest_new = max(
                    float(item.metadata.get("relevance_score", 0.0))
                    for item in non_stale
                )
                margin = float(self.settings.stale_filter_relevance_margin)
                filtered: list[RetrievedChunk] = []
                for item in enriched:
                    policy = item.metadata.get("temporal_authority") or {}
                    relevance = float(item.metadata.get("relevance_score", 0.0))
                    if bool(policy.get("stale")) and relevance + margin < strongest_new:
                        item.metadata = {
                            **item.metadata,
                            "temporal_authority": {
                                **policy,
                                "excluded_as_clearly_weaker_stale_source": True,
                            },
                        }
                        continue
                    filtered.append(item)
                enriched = filtered

        # For general legal/factoid questions, a directly issued regulation
        # outranks a same-year university implementation or compilation clause
        # that merely cites it.  Keep implementation documents for operational
        # questions (forms, systems, steps, fees) or when no direct source exists.
        if requested_year is None and not query_prefers_implementation(query):
            direct_candidates = [
                item
                for item in enriched
                if bool(
                    ((item.metadata.get("temporal_authority") or {})
                     .get("source_policy") or {})
                    .get("direct_rule")
                )
                and str(
                    (((item.metadata.get("temporal_authority") or {})
                      .get("source_policy") or {})
                     .get("source_type", ""))
                ) in {"official_circular", "unified_regulation", "regulation_document"}
            ]
            if direct_candidates:
                strongest_direct = max(
                    float(item.metadata.get("relevance_score", 0.0))
                    for item in direct_candidates
                )
                filtered: list[RetrievedChunk] = []
                for item in enriched:
                    policy = (item.metadata.get("temporal_authority") or {}).get(
                        "source_policy"
                    ) or {}
                    relevance = float(item.metadata.get("relevance_score", 0.0))
                    if (
                        bool(policy.get("derivative"))
                        and relevance <= strongest_direct + 0.25
                    ):
                        continue
                    filtered.append(item)
                enriched = filtered

        enriched.sort(
            key=lambda item: (
                float(item.metadata.get("ranking_score", 0.0)),
                float(item.metadata.get("relevance_score", 0.0)),
                -item.rank,
            ),
            reverse=True,
        )
        for rank, item in enumerate(enriched, start=1):
            item.rank = rank
            if "temporal_authority" not in item.method:
                item.method = f"{item.method}+temporal_authority"
        return enriched

    def _category_mask(self, category: str | None) -> np.ndarray:
        if not category:
            return np.ones(len(self.chunks_df), dtype=bool)
        normalized = normalize_persian_query(category).lower()
        values = (
            self.chunks_df["category"]
            .fillna("")
            .astype(str)
            .map(normalize_persian_query)
            .str.lower()
        )
        return values.eq(normalized).to_numpy()

    def _article_boost(self, scores: np.ndarray, query: str) -> np.ndarray:
        article_number = extract_article_number(query)
        if not article_number or "article" not in self.chunks_df.columns:
            return scores
        article_values = (
            self.chunks_df["article"]
            .fillna("")
            .astype(str)
            .str.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
        )
        exact = article_values.str.extract(r"(\d+)", expand=False).fillna("").eq(
            article_number
        )
        boosted = scores.copy()
        finite = boosted[np.isfinite(boosted)]
        scale = float(np.max(np.abs(finite))) if finite.size else 1.0
        boosted[exact.to_numpy()] += max(scale * 0.20, 0.25)
        return boosted


    def _apply_first_stage_document_policy(
        self,
        scores: np.ndarray,
        query: str,
    ) -> np.ndarray:
        """Apply a corpus-wide year/authority prior before top-k truncation."""
        adjusted = scores.copy()
        finite_mask = np.isfinite(adjusted)
        if not finite_mask.any():
            return adjusted

        finite_values = np.abs(adjusted[finite_mask])
        scale = float(np.percentile(finite_values, 90)) if finite_values.size else 1.0
        scale = max(scale, 1.0)
        requested_year = self._query_requested_year(query)
        latest_year = self.latest_regulation_year

        for index in np.flatnonzero(finite_mask):
            row = self.chunks_df.iloc[int(index)]
            label = self._row_document_label(row)
            years = extract_solar_years(label)
            document_year = max(years) if years else None
            title = str(row.get("title", "") or "")
            row_text = str(row.get("text", "") or "")
            profile = regulation_source_profile(title, "")
            implementation_intent = query_prefers_implementation(query)
            if implementation_intent:
                source_prior = {
                    "official_circular": 0.18,
                    "unified_regulation": 0.16,
                    "regulation_document": 0.12,
                    "regulation_compilation": 0.14,
                    "implementation_guide": 0.28,
                    "other": 0.0,
                }.get(str(profile["source_type"]), 0.0)
            else:
                source_prior = {
                    "official_circular": 0.62,
                    "unified_regulation": 0.52,
                    "regulation_document": 0.34,
                    "regulation_compilation": 0.16,
                    "implementation_guide": -0.12,
                    "other": -0.04,
                }.get(str(profile["source_type"]), 0.0)
            adjusted[int(index)] += scale * float(source_prior)

            if requested_year is not None:
                if document_year == requested_year:
                    adjusted[int(index)] += scale * 0.80
                elif document_year is not None:
                    adjusted[int(index)] -= scale * 0.65
                continue

            if (
                not self.settings.prefer_latest_regulations
                or latest_year is None
                or document_year is None
            ):
                continue
            gap = latest_year - document_year
            if gap <= 0:
                adjusted[int(index)] += scale * 0.72
            elif gap >= int(self.settings.stale_year_gap):
                adjusted[int(index)] -= scale * 0.45
            else:
                adjusted[int(index)] -= scale * 0.08

        return adjusted

    def _bm25_rank(self, query: str, category: str | None, top_n: int) -> list[tuple[int, float]]:
        variants = expand_query(query)
        aggregate = np.full(len(self.chunks_df), -np.inf, dtype=np.float32)
        for variant in variants:
            tokens = bm25_tokenize(variant)
            if not tokens:
                continue
            scores = np.asarray(self.bm25_model.get_scores(tokens), dtype=np.float32)
            aggregate = np.maximum(aggregate, scores)

        aggregate = self._article_boost(aggregate, query)
        aggregate = self._apply_first_stage_document_policy(aggregate, query)
        aggregate[~self._category_mask(category)] = -np.inf
        valid = np.flatnonzero(np.isfinite(aggregate))
        if valid.size == 0:
            return []
        order = valid[np.argsort(-aggregate[valid])[: min(top_n, valid.size)]]
        return [(int(index), float(aggregate[index])) for index in order]

    def _encode_query(self, query: str, dense_alias: str) -> np.ndarray:
        self._load_dense_alias(dense_alias)
        model = self.dense_models[dense_alias]
        prefix = self.dense_query_prefixes.get(dense_alias, "")
        vector = model.encode(
            [prefix + normalize_persian_query(query)],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vector, dtype=np.float32)

    def _dense_rank(
        self,
        query: str,
        category: str | None,
        top_n: int,
        dense_alias: str,
    ) -> list[tuple[int, float]]:
        vector = self._encode_query(query, dense_alias)
        index = self.dense_indexes[dense_alias]
        search_k = min(max(top_n * 5, top_n), len(self.chunks_df))
        distances, indices = index.search(vector, search_k)
        category_mask = self._category_mask(category)

        ranked: list[tuple[int, float]] = []
        for index_value, score in zip(indices[0], distances[0]):
            if index_value < 0 or not category_mask[int(index_value)]:
                continue
            ranked.append((int(index_value), float(score)))
            if len(ranked) >= top_n:
                break
        return ranked

    @staticmethod
    def _rrf(
        rankings: Sequence[list[tuple[int, float]]],
        rrf_k: int,
        weights: Sequence[float],
    ) -> list[tuple[int, float]]:
        scores: defaultdict[int, float] = defaultdict(float)
        for ranking, weight in zip(rankings, weights):
            for rank, (index, _) in enumerate(ranking, start=1):
                scores[index] += float(weight) / (rrf_k + rank)
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)

    def _first_stage(
        self,
        query: str,
        category: str | None,
        candidate_k: int,
        method: str,
        dense_alias: str,
    ) -> list[tuple[int, float, str, dict[str, float]]]:
        if "hybrid" in method or "rrf" in method:
            bm25 = self._bm25_rank(query, category, candidate_k)
            dense = self._dense_rank(
                query, category, candidate_k, dense_alias=dense_alias
            )
            bm25_scores = dict(bm25)
            dense_scores = dict(dense)
            cfg = self.retrieval_config.get("retrieval", {})
            fused = self._rrf(
                [bm25, dense],
                rrf_k=int(cfg.get("rrf_k", 60)),
                weights=[
                    float(cfg.get("bm25_weight", 1.0)),
                    float(cfg.get("dense_weight", 1.0)),
                ],
            )
            return [
                (
                    index,
                    score,
                    f"hybrid_rrf:{dense_alias}",
                    {
                        "rrf_score": float(score),
                        "bm25_score": float(bm25_scores.get(index, 0.0)),
                        "dense_score": float(dense_scores.get(index, 0.0)),
                    },
                )
                for index, score in fused[:candidate_k]
            ]

        if "dense" in method or "mmr" in method:
            return [
                (
                    index,
                    score,
                    f"dense:{dense_alias}",
                    {"dense_score": float(score)},
                )
                for index, score in self._dense_rank(
                    query, category, candidate_k, dense_alias=dense_alias
                )
            ]

        return [
            (index, score, "bm25", {"bm25_score": float(score)})
            for index, score in self._bm25_rank(query, category, candidate_k)
        ]

    def _row_to_chunk(
        self,
        index: int,
        raw_score: float,
        method: str,
        rank: int,
        score_components: dict[str, float] | None = None,
    ) -> RetrievedChunk:
        row = self.chunks_df.iloc[index]

        def optional_int(value: Any) -> int | None:
            if value is None or pd.isna(value):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def optional_str(value: Any) -> str | None:
            if value is None or pd.isna(value):
                return None
            text = str(value).strip()
            return text or None

        return RetrievedChunk(
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            row_id=int(index),
            rank=rank,
            raw_score=float(raw_score),
            display_score=0.0,
            method=method,
            text=str(row.get("text", "") or ""),
            title=str(row.get("title", "") or ""),
            category=optional_str(row.get("category")),
            page_start=optional_int(row.get("page_start")),
            page_end=optional_int(row.get("page_end")),
            article=optional_str(row.get("article")),
            note=optional_str(row.get("note")),
            chunk_order=optional_int(row.get("chunk_order")),
            metadata={
                **row.to_dict(),
                "score_components": dict(score_components or {}),
            },
        )

    def _rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []
        if not self._ensure_reranker():
            return candidates[:top_k]

        pairs = [(query, item.text) for item in candidates]
        reranker_cfg = self.retrieval_config.get("reranker", {})
        predict_kwargs: dict[str, Any] = {}
        if reranker_cfg.get("batch_size"):
            predict_kwargs["batch_size"] = int(reranker_cfg["batch_size"])
        try:
            scores = np.asarray(
                self.reranker.predict(
                    pairs,
                    show_progress_bar=False,
                    **predict_kwargs,
                ),
                dtype=np.float32,
            ).reshape(-1)
        except TypeError:
            scores = np.asarray(
                self.reranker.predict(pairs, **predict_kwargs),
                dtype=np.float32,
            ).reshape(-1)
        order = np.argsort(-scores)
        reranked: list[RetrievedChunk] = []
        for rank, position in enumerate(order[:top_k], start=1):
            item = candidates[int(position)]
            raw_reranker = float(scores[int(position)])
            reranker_probability = float(
                1.0 / (1.0 + math.exp(-max(min(raw_reranker, 30.0), -30.0)))
            )
            item.metadata = {
                **item.metadata,
                "first_stage_rank": item.rank,
                "first_stage_score": item.raw_score,
                "reranker_score": raw_reranker,
                "reranker_probability": reranker_probability,
            }
            item.rank = rank
            item.raw_score = raw_reranker
            item.method = f"{item.method}+reranker"
            reranked.append(item)
        return reranked

    @staticmethod
    def _bounded_dense_score(value: float) -> float:
        # E5 cosine scores for short Persian regulations commonly occupy a
        # relatively narrow positive range.  Values below 0.35 carry little
        # evidence; values around 0.80 or higher are strong.
        return float(np.clip((float(value) - 0.35) / 0.45, 0.0, 1.0))

    @staticmethod
    def _bounded_bm25_score(value: float) -> float:
        value = max(float(value), 0.0)
        return float(1.0 - math.exp(-value / 4.0))

    def _apply_relevance_guard(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        retrieval_mode: str,
    ) -> list[RetrievedChunk]:
        """Reject chunks that are highly ranked but do not answer the query.

        RRF and rank-based normalization always produce a winner, even for an
        out-of-domain query.  This guard uses query concepts, original-token
        overlap, dense similarity, and optional cross-encoder evidence.  It is
        deliberately fail-closed: no plausible evidence means no answer.
        """

        article_number = extract_article_number(query)
        guarded: list[RetrievedChunk] = []

        for item in candidates:
            combined_text = " | ".join(
                value
                for value in (
                    item.title,
                    item.category or "",
                    f"ماده {item.article}" if item.article else "",
                    item.text,
                )
                if value
            )
            lexical = local_lexical_relevance_features(
                query=query,
                candidate_text=item.text,
                title=item.title,
            )
            components = dict(item.metadata.get("score_components") or {})
            dense_raw = float(components.get("dense_score", 0.0) or 0.0)
            bm25_raw = float(components.get("bm25_score", 0.0) or 0.0)
            reranker_probability = float(
                item.metadata.get("reranker_probability", 0.0) or 0.0
            )

            dense_quality = self._bounded_dense_score(dense_raw)
            bm25_quality = self._bounded_bm25_score(bm25_raw)
            anchor_coverage = float(lexical["anchor_coverage"])
            title_coverage = float(lexical["title_anchor_coverage"])
            overlap_count = int(lexical["anchor_overlap_count"])
            anchor_count = int(lexical["anchor_count"])
            original_overlap = int(lexical["original_anchor_overlap_count"])
            phrase_match = bool(lexical["phrase_match"])
            scope_required = bool(lexical.get("scope_required", False))
            scope_match = bool(lexical.get("scope_match", True))
            article_match = bool(
                article_number
                and item.article
                and str(item.article).translate(
                    str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
                ).find(article_number)
                >= 0
            )

            semantic_quality = max(dense_quality, reranker_probability)
            relevance_score = (
                0.48 * anchor_coverage
                + 0.12 * title_coverage
                + 0.16 * bm25_quality
                + 0.24 * semantic_quality
            )
            if phrase_match:
                relevance_score += 0.20
            if original_overlap > 0:
                relevance_score += 0.06
            if scope_required and scope_match:
                relevance_score += 0.12
            elif scope_required and not scope_match:
                relevance_score -= 0.28
            if article_match:
                relevance_score = max(relevance_score, 0.92)
            relevance_score = float(np.clip(relevance_score, 0.0, 1.0))

            lexical_pass = bool(
                phrase_match
                or article_match
                or (
                    overlap_count >= 1
                    and anchor_coverage >= 0.50
                    and original_overlap >= 1
                )
                or (overlap_count >= 2 and anchor_coverage >= 0.34)
                or (anchor_count == 1 and overlap_count == 1)
            )
            semantic_pass = bool(
                reranker_probability >= 0.72
                and dense_raw >= 0.50
            )
            dense_only_pass = bool(
                retrieval_mode == "hybrid"
                and dense_raw >= 0.80
                and anchor_coverage > 0.0
            )
            passed = lexical_pass or semantic_pass or dense_only_pass
            if scope_required and not scope_match and not article_match:
                passed = False

            item.metadata = {
                **item.metadata,
                "relevance_guard": {
                    **lexical,
                    "article_match": article_match,
                    "bm25_score": bm25_raw,
                    "dense_score": dense_raw,
                    "dense_quality": dense_quality,
                    "reranker_probability": reranker_probability,
                    "relevance_score": relevance_score,
                    "passed": passed,
                },
                "relevance_score": relevance_score,
                "relevance_passed": passed,
            }
            if passed:
                if "relevance_guard" not in item.method:
                    item.method = f"{item.method}+relevance_guard"
                guarded.append(item)

        # Preserve cross-encoder order where available, but use the guarded
        # relevance score to break weak ties and to rank the deterministic
        # fallback when the reranker cannot be loaded.
        if self.reranker is None:
            guarded.sort(
                key=lambda item: (
                    float(item.metadata.get("relevance_score", 0.0)),
                    -item.rank,
                ),
                reverse=True,
            )
        return guarded

    def _deduplicate(
        self,
        candidates: list[RetrievedChunk],
        limit: int,
    ) -> list[RetrievedChunk]:
        selected: list[RetrievedChunk] = []
        per_document: defaultdict[str, int] = defaultdict(int)
        seen_chunks: set[str] = set()
        stale_selected = 0
        threshold = float(
            self.retrieval_config.get("retrieval", {}).get(
                "deduplication_threshold", 0.92
            )
        )

        for candidate in candidates:
            if candidate.chunk_id in seen_chunks:
                continue
            temporal = candidate.metadata.get("temporal_authority") or {}
            if temporal.get("stale") and stale_selected >= 1:
                continue
            if (
                per_document[candidate.document_id]
                >= self.settings.maximum_chunks_per_document
            ):
                continue
            if any(
                text_jaccard(candidate.text, existing.text) >= threshold
                for existing in selected
            ):
                continue

            selected.append(candidate)
            seen_chunks.add(candidate.chunk_id)
            per_document[candidate.document_id] += 1
            if temporal.get("stale"):
                stale_selected += 1
            if len(selected) >= limit:
                break

        return selected

    @staticmethod
    def _normalize_display_scores(items: list[RetrievedChunk]) -> None:
        if not items:
            return
        for item in items:
            relevance = item.metadata.get("ranking_score")
            if relevance is None:
                relevance = item.metadata.get("relevance_score")
            if relevance is None:
                relevance = 1.0 / max(item.rank, 1)
            item.display_score = round(float(np.clip(relevance, 0.0, 1.0)), 4)

    def resolve_retrieval_mode(self, retrieval_mode: str) -> tuple[str, str]:
        mode = str(retrieval_mode or "best").lower()
        if mode == "best":
            return self.best_method, self.best_dense_alias
        if mode == "hybrid":
            if not self.hybrid_available:
                raise ValueError(
                    "Hybrid retrieval is unavailable because its E5/FAISS "
                    "artifacts were not found. Run Notebook 02 first."
                )
            return "hybrid_reranker", self.hybrid_dense_alias
        raise ValueError(f"Unknown retrieval mode: {retrieval_mode}")

    def describe_retrieval_mode(self, retrieval_mode: str) -> str:
        method, dense_alias = self.resolve_retrieval_mode(retrieval_mode)
        if "hybrid" in method or "rrf" in method:
            label = f"hybrid_rrf:{dense_alias}"
        elif "dense" in method or "mmr" in method:
            label = f"dense:{dense_alias}"
        else:
            label = "bm25"
        if "reranker" in method:
            label = f"{label}+reranker"
        return f"{label}+relevance_guard+source_authority"

    def retrieve(
        self,
        query: str,
        top_k: int,
        category: str | None = None,
        retrieval_mode: str = "best",
    ) -> list[RetrievedChunk]:
        if not self.ready:
            raise RuntimeError(self.load_error or "Retriever is not ready.")

        method, dense_alias = self.resolve_retrieval_mode(retrieval_mode)
        top_k = max(1, min(int(top_k), self.settings.maximum_top_k))
        if retrieval_mode == "best":
            configured_candidate_k = self.best_config.get("candidate_k")
        else:
            configured_candidate_k = self.retrieval_config.get(
                "retrieval", {}
            ).get("candidate_k")
        candidate_k = max(
            top_k,
            int(configured_candidate_k or self.settings.retrieval_candidate_k),
        )

        with self._lock:
            first_stage = self._first_stage(
                query,
                category,
                candidate_k,
                method=method,
                dense_alias=dense_alias,
            )
            candidates = [
                self._row_to_chunk(
                    index,
                    score,
                    result_method,
                    rank,
                    score_components,
                )
                for rank, (
                    index,
                    score,
                    result_method,
                    score_components,
                ) in enumerate(first_stage, start=1)
            ]
            if "reranker" in method:
                ranked = self._rerank(
                    query,
                    candidates,
                    max(
                        top_k * 4,
                        int(
                            self.retrieval_config.get("reranker", {}).get(
                                "candidate_k", top_k * 4
                            )
                        ),
                    ),
                )
            else:
                ranked = candidates[: max(top_k * 3, top_k)]
            guarded = self._apply_relevance_guard(
                query,
                ranked,
                retrieval_mode=retrieval_mode,
            )
            policy_ranked = self._apply_temporal_authority_policy(
                query,
                guarded,
            )
            selected = self._deduplicate(policy_ranked, top_k)
            for rank, item in enumerate(selected, start=1):
                item.rank = rank
            self._normalize_display_scores(selected)
            return selected

    def below_threshold(
        self,
        results: Sequence[RetrievedChunk],
        retrieval_mode: str = "best",
    ) -> bool:
        if not results:
            return True
        top_relevance = float(
            results[0].metadata.get(
                "ranking_score",
                results[0].metadata.get("relevance_score", 0.0),
            )
        )
        minimum = (
            self.settings.hybrid_minimum_relevance_score
            if retrieval_mode == "hybrid"
            else self.settings.minimum_relevance_score
        )
        if top_relevance < float(minimum):
            return True

        # The calibrated raw-score threshold belongs only to the Notebook
        # selected method.  A strong guarded match may override a weak raw
        # score because query expansion changes runtime wording.
        if (
            retrieval_mode == "best"
            and self.score_threshold is not None
            and float(results[0].raw_score) < float(self.score_threshold)
            and top_relevance < 0.60
        ):
            return True
        return False

    def status(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "error": self.load_error,
            "method": self.best_method,
            "best_method": self.best_method,
            "best_dense_alias": self.best_dense_alias,
            "hybrid_method": (
                f"hybrid_rrf:{self.hybrid_dense_alias}+reranker+relevance_guard"
                if self.hybrid_dense_alias
                else "hybrid_rrf+reranker+relevance_guard"
            ),
            "hybrid_dense_alias": self.hybrid_dense_alias,
            "hybrid_available": self.hybrid_available,
            "loaded_dense_aliases": sorted(self.dense_models),
            "benchmark_label": self.benchmark_label,
            "selection_status": self.selection_status,
            "score_threshold": self.score_threshold,
            "latest_regulation_year": self.latest_regulation_year,
            "prefer_latest_regulations": self.settings.prefer_latest_regulations,
            "chunks": self.chunk_count,
            "documents": self.document_count,
            "reranker_ready": self.reranker is not None,
            "reranker_model_name": self.reranker_model_name,
            "relevance_guard_enabled": True,
            "source_authority_policy": True,
            "warnings": list(self.warnings),
        }

