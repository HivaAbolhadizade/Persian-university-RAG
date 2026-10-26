from __future__ import annotations

import logging
import time
from typing import Any

from backend.app.config import Settings
from backend.app.schemas import QueryResponse, SourceResponse
from backend.app.services.generator import (
    GeneratorFactory,
    MockExtractiveGenerator,
    NO_ANSWER_MESSAGE,
)
from backend.app.services.llm_settings import LLMSettingsManager
from backend.app.services.retriever import RetrievalEngine, RetrievedChunk
from backend.app.utils.text import extract_relevant_excerpt

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(
        self,
        settings: Settings,
        retriever: RetrievalEngine,
        generator_factory: GeneratorFactory,
        llm_settings: LLMSettingsManager,
    ) -> None:
        self.settings = settings
        self.retriever = retriever
        self.generator_factory = generator_factory
        self.llm_settings = llm_settings

    def _build_context(
        self,
        question: str,
        results: list[RetrievedChunk],
    ) -> tuple[str, dict[str, RetrievedChunk]]:
        blocks: list[str] = []
        source_lookup: dict[str, RetrievedChunk] = {}
        total_characters = 0

        for index, item in enumerate(results, start=1):
            source_id = f"S{index}"
            metadata = [f"عنوان: {item.title}"]
            if item.category:
                metadata.append(f"دسته: {item.category}")
            if item.page_start is not None:
                if item.page_end is not None and item.page_end != item.page_start:
                    metadata.append(f"صفحه: {item.page_start}-{item.page_end}")
                else:
                    metadata.append(f"صفحه: {item.page_start}")
            if item.article:
                metadata.append(f"ماده/بند: {item.article}")
            temporal = item.metadata.get("temporal_authority") or {}
            source_policy = temporal.get("source_policy") or {}
            if source_policy.get("source_label"):
                metadata.append(f"نوع منبع: {source_policy['source_label']}")
            if source_policy.get("derivative"):
                metadata.append("ماهیت حکم: اجرایی/ارجاعی، نه متن مستقیم حکم پایه")
            elif source_policy.get("direct_rule"):
                metadata.append("ماهیت حکم: متن مستقیم مقرره")
            if temporal.get("document_year") is not None:
                metadata.append(f"سال سند: {temporal['document_year']}")
            if temporal.get("latest_regulation_year") is not None:
                metadata.append(
                    f"جدیدترین سال مقررات موجود: {temporal['latest_regulation_year']}"
                )
            if temporal.get("stale"):
                metadata.append("وضعیت: نسخه قدیمی‌تر")
            elif temporal.get("document_year") is not None:
                metadata.append("وضعیت: نسخه جدیدتر/ترجیحی")

            source_text = extract_relevant_excerpt(
                item.text,
                question,
                maximum_characters=min(
                    self.settings.context_excerpt_characters,
                    self.settings.maximum_source_characters,
                ),
            ).strip()
            block = f"[{source_id}]\n{' | '.join(metadata)}\n{source_text}"
            if (
                blocks
                and total_characters + len(block)
                > self.settings.maximum_context_characters
            ):
                break

            blocks.append(block)
            source_lookup[source_id] = item
            total_characters += len(block)

        return "\n\n".join(blocks), source_lookup

    @staticmethod
    def _source_responses(
        source_lookup: dict[str, RetrievedChunk],
    ) -> list[SourceResponse]:
        return [
            SourceResponse(
                source_id=source_id,
                title=item.title,
                category=item.category,
                page_start=item.page_start,
                page_end=item.page_end,
                article=item.article,
                note=item.note,
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                score=item.display_score,
                text=item.text,
            )
            for source_id, item in source_lookup.items()
        ]

    def ask(
        self,
        session_id: str,
        question: str,
        top_k: int | None = None,
        category: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        retrieval_mode: str = "best",
    ) -> QueryResponse:
        started = time.perf_counter()
        requested_top_k = int(top_k or self.settings.default_top_k)
        requested_top_k = min(requested_top_k, self.settings.maximum_top_k)

        retrieval_results = self.retriever.retrieve(
            question,
            top_k=requested_top_k,
            category=category,
            retrieval_mode=retrieval_mode,
        )
        context, source_lookup = self._build_context(question, retrieval_results)
        valid_source_ids = set(source_lookup)

        runtime_provider = self.llm_settings.resolve_for_query(
            session_id=session_id,
            provider_override=provider,
            model_override=model,
        )

        retrieval_gate = (
            not retrieval_results
            or not context
            or self.retriever.below_threshold(
                retrieval_results, retrieval_mode=retrieval_mode
            )
        )

        fallback_used = False

        if retrieval_gate:
            generation_answer = NO_ANSWER_MESSAGE
            citations: list[str] = []
            no_answer = True
            generation_confidence = 0.0
            provider_alias = runtime_provider.provider
            selected_model = "retrieval-gate"
            generation_error = None
            generation_latency = 0.0
        else:
            generator = self.generator_factory.get(runtime_provider)
            generated = generator.generate(
                question=question,
                context=context,
                valid_source_ids=valid_source_ids,
            )

            if generated.error and self.settings.allow_mock_fallback:
                logger.warning(
                    "Provider %s failed; using mock fallback: %s",
                    runtime_provider.provider,
                    generated.error,
                )
                fallback = MockExtractiveGenerator().generate(
                    question=question,
                    context=context,
                    valid_source_ids=valid_source_ids,
                )
                fallback_used = True
                generation_error = generated.error
                generated = fallback
            else:
                generation_error = generated.error

            generation_answer = generated.answer
            citations = generated.citations
            no_answer = generated.no_answer
            generation_confidence = generated.confidence
            provider_alias = generated.provider_alias
            selected_model = generated.model
            generation_latency = generated.latency_seconds

        retrieval_confidence = (
            float(retrieval_results[0].display_score) if retrieval_results else 0.0
        )

        confidence = (
            0.0
            if no_answer
            else round(
                max(
                    0.0,
                    min(
                        1.0,
                        0.60 * generation_confidence
                        + 0.40 * retrieval_confidence,
                    ),
                ),
                4,
            )
        )

        sources = self._source_responses(source_lookup)
        retriever_method = (
            retrieval_results[0].method
            if retrieval_results
            else self.retriever.describe_retrieval_mode(retrieval_mode)
        )

        diagnostics: dict[str, Any] = {
            "retrieval_gate_triggered": retrieval_gate,
            "retrieval_threshold": (
                self.retriever.score_threshold
                if retrieval_mode == "best"
                else self.settings.hybrid_minimum_relevance_score
            ),
            "minimum_relevance_score": (
                self.settings.hybrid_minimum_relevance_score
                if retrieval_mode == "hybrid"
                else self.settings.minimum_relevance_score
            ),
            "retriever_selection_status": self.retriever.selection_status,
            "requested_provider": runtime_provider.provider,
            "requested_model": runtime_provider.model,
            "fallback_used": fallback_used,
            "generation_error": generation_error,
            "generation_latency_seconds": generation_latency,
            "retrieved_count": len(retrieval_results),
            "category_filter": category,
            "requested_retrieval_mode": retrieval_mode,
            "resolved_retriever_method": retriever_method,
            "latest_regulation_year": self.retriever.latest_regulation_year,
            "temporal_authority_policy": self.settings.prefer_latest_regulations,
            "source_authority_policy": True,
        }

        return QueryResponse(
            question=question,
            answer=generation_answer,
            citations=citations,
            no_answer=no_answer,
            confidence=confidence,
            provider_alias=provider_alias,
            model=selected_model,
            retriever_method=retriever_method,
            latency_seconds=round(time.perf_counter() - started, 3),
            sources=sources,
            diagnostics=diagnostics,
        )
