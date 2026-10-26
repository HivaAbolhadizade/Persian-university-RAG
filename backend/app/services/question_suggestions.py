from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from threading import RLock
from typing import Any

from backend.app.config import Settings
from backend.app.utils.text import (
    expand_query,
    meaningful_tokens,
    normalize_persian_query,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuestionSuggestion:
    id: int
    question: str
    source: str | None
    difficulty: str | None
    question_type: str | None
    score: float
    match_type: str


class QuestionSuggestionService:
    """Fast autocomplete over the approved 100-question benchmark list.

    Only question metadata is loaded. Ground-truth answers are deliberately not
    exposed to the runtime API, so autocomplete cannot leak evaluation answers
    into the RAG pipeline.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = RLock()
        self._items: list[dict[str, Any]] | None = None
        self._source_path: Path | None = None

    @property
    def source_path(self) -> Path | None:
        self._ensure_loaded()
        return self._source_path

    def _candidate_paths(self) -> list[Path]:
        packaged = Path(__file__).resolve().parents[1] / "data" / "question_suggestions.json"
        project_benchmark = self.settings.university_rag_root / "rag_eval_100.json"
        configured = getattr(self.settings, "question_suggestions_path", None)

        candidates: list[Path] = []
        if configured:
            configured_path = Path(configured)
            if not configured_path.is_absolute():
                configured_path = self.settings.university_rag_root / configured_path
            candidates.append(configured_path)
        candidates.extend([packaged, project_benchmark])

        unique: list[Path] = []
        seen: set[Path] = set()
        for path in candidates:
            resolved = path.expanduser().resolve()
            if resolved not in seen:
                seen.add(resolved)
                unique.append(resolved)
        return unique

    def _ensure_loaded(self) -> None:
        if self._items is not None:
            return
        with self._lock:
            if self._items is not None:
                return

            for path in self._candidate_paths():
                if not path.exists():
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(payload, list):
                        continue
                    parsed: list[dict[str, Any]] = []
                    for row in payload:
                        if not isinstance(row, dict):
                            continue
                        question = str(row.get("question", "")).strip()
                        if len(question) < 2:
                            continue
                        parsed.append(
                            {
                                "id": int(row.get("id", len(parsed) + 1)),
                                "question": question,
                                "source": self._clean_optional(row.get("source")),
                                "difficulty": self._clean_optional(row.get("difficulty")),
                                "question_type": self._clean_optional(row.get("question_type")),
                                "normalized": normalize_persian_query(question).lower(),
                                "tokens": set(meaningful_tokens(question, drop_domain_generic=False)),
                                "compact_tokens": set(meaningful_tokens(question, drop_domain_generic=True)),
                                "trigrams": self._character_ngrams(question),
                            }
                        )
                    if parsed:
                        self._items = parsed
                        self._source_path = path
                        logger.info(
                            "Question autocomplete loaded: questions=%s source=%s",
                            len(parsed),
                            path,
                        )
                        return
                except Exception as exc:  # pragma: no cover - logged fallback path
                    logger.warning("Could not load autocomplete questions from %s: %s", path, exc)

            self._items = []
            self._source_path = None
            logger.warning("Question autocomplete is unavailable: no question bank found.")

    @staticmethod
    def _clean_optional(value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _character_ngrams(text: str, n: int = 3) -> set[str]:
        normalized = normalize_persian_query(text).lower().replace(" ", "")
        if not normalized:
            return set()
        if len(normalized) <= n:
            return {normalized}
        return {normalized[index : index + n] for index in range(len(normalized) - n + 1)}

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    @staticmethod
    def _coverage(query_tokens: set[str], candidate_tokens: set[str]) -> float:
        if not query_tokens:
            return 0.0
        return len(query_tokens & candidate_tokens) / len(query_tokens)

    @staticmethod
    def _token_prefix_coverage(query_tokens: set[str], candidate_tokens: set[str]) -> float:
        if not query_tokens or not candidate_tokens:
            return 0.0
        matched = 0
        for query_token in query_tokens:
            if any(
                candidate.startswith(query_token) or query_token.startswith(candidate)
                for candidate in candidate_tokens
                if len(candidate) >= 2
            ):
                matched += 1
        return matched / len(query_tokens)

    def _score_variant(
        self,
        query: str,
        query_tokens: set[str],
        compact_query_tokens: set[str],
        query_trigrams: set[str],
        item: dict[str, Any],
    ) -> tuple[float, str]:
        candidate = str(item["normalized"])
        candidate_tokens = set(item["tokens"])
        compact_candidate_tokens = set(item["compact_tokens"])

        exact = float(query == candidate)
        prefix = float(candidate.startswith(query))
        contains = float(query in candidate)
        reverse_contains = float(candidate in query and len(candidate) >= 8)

        token_coverage = max(
            self._coverage(query_tokens, candidate_tokens),
            self._coverage(compact_query_tokens, compact_candidate_tokens),
        )
        token_jaccard = max(
            self._jaccard(query_tokens, candidate_tokens),
            self._jaccard(compact_query_tokens, compact_candidate_tokens),
        )
        token_prefix = max(
            self._token_prefix_coverage(query_tokens, candidate_tokens),
            self._token_prefix_coverage(compact_query_tokens, compact_candidate_tokens),
        )
        character_jaccard = self._jaccard(query_trigrams, set(item["trigrams"]))
        sequence_ratio = SequenceMatcher(None, query, candidate).ratio()

        # Prefix/substring matches dominate autocomplete. Fuzzy and token
        # features make misspellings and differently worded queries useful.
        score = (
            1.00 * exact
            + 0.62 * prefix
            + 0.26 * contains
            + 0.08 * reverse_contains
            + 0.34 * token_coverage
            + 0.16 * token_jaccard
            + 0.18 * token_prefix
            + 0.13 * character_jaccard
            + 0.12 * sequence_ratio
        )

        if exact:
            match_type = "exact"
        elif prefix:
            match_type = "prefix"
        elif contains:
            match_type = "contains"
        elif token_coverage >= 0.75:
            match_type = "token"
        else:
            match_type = "fuzzy"
        return score, match_type

    def suggest(self, query: str, limit: int = 5) -> list[QuestionSuggestion]:
        self._ensure_loaded()
        assert self._items is not None

        normalized = normalize_persian_query(query).lower()
        if len(normalized) < 2 or not self._items:
            return []

        variants = expand_query(normalized, maximum_variants=6)
        if normalized not in variants:
            variants.insert(0, normalized)

        scored: list[QuestionSuggestion] = []
        for item in self._items:
            best_score = 0.0
            best_match_type = "fuzzy"
            for variant in variants:
                variant_normalized = normalize_persian_query(variant).lower()
                query_tokens = set(
                    meaningful_tokens(variant_normalized, drop_domain_generic=False)
                )
                compact_query_tokens = set(
                    meaningful_tokens(variant_normalized, drop_domain_generic=True)
                )
                query_trigrams = self._character_ngrams(variant_normalized)
                score, match_type = self._score_variant(
                    variant_normalized,
                    query_tokens,
                    compact_query_tokens,
                    query_trigrams,
                    item,
                )
                # Expanded variants are useful but must not outrank a strong
                # direct match to what the user actually typed.
                if variant_normalized != normalized:
                    score *= 0.93
                if score > best_score:
                    best_score = score
                    best_match_type = match_type

            # A short prefix such as "حداکثر" should still produce results,
            # while unrelated two-character noise should not.
            minimum_score = 0.22 if len(normalized) >= 4 else 0.30
            if best_score < minimum_score:
                continue

            scored.append(
                QuestionSuggestion(
                    id=int(item["id"]),
                    question=str(item["question"]),
                    source=item.get("source"),
                    difficulty=item.get("difficulty"),
                    question_type=item.get("question_type"),
                    score=round(min(best_score, 1.0), 4),
                    match_type=best_match_type,
                )
            )

        scored.sort(
            key=lambda item: (
                -item.score,
                len(item.question),
                item.id,
            )
        )
        return scored[: max(1, min(int(limit), 10))]

    def status(self) -> dict[str, Any]:
        self._ensure_loaded()
        assert self._items is not None
        return {
            "ready": bool(self._items),
            "questions": len(self._items),
            "source": str(self._source_path) if self._source_path else None,
        }
