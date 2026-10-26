#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
University_RAG automatic evaluator

Runs the official rag_eval_100.json benchmark against one or more retrieval
modes (best / hybrid), calls the live FastAPI backend, and writes:

- per_question_results.csv
- raw_results.jsonl
- summary.json
- evaluation_report.md

Default usage (from the University_RAG project root):

    .\.venv\Scripts\python.exe .\evaluation\evaluate_rag.py

Useful quick test:

    .\.venv\Scripts\python.exe .\evaluation\evaluate_rag.py --limit 3

Resume an interrupted run:

    .\.venv\Scripts\python.exe .\evaluation\evaluate_rag.py --resume

Important:
- The backend must already be running at http://127.0.0.1:8000.
- This script uses a requests.Session so the backend LLM session remains
  consistent for the whole evaluation.
- Automatic "correctness" is a transparent lexical heuristic, not a substitute
  for manual review. Retrieval source recall and all raw answers are also saved.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import math
import os
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import requests
    from requests import Response, Session
except ImportError as exc:
    raise SystemExit(
        "پکیج requests نصب نیست.\n"
        "این دستور را اجرا کنید:\n"
        r"  .\.venv\Scripts\python.exe -m pip install requests"
    ) from exc


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_MODEL = "gemini-3.1-flash-lite"
DEFAULT_MODES = ("best", "hybrid")
NO_ANSWER_PHRASES = (
    "پاسخ این سؤال در اسناد موجود یافت نشد",
    "اطلاعات کافی در اسناد",
    "پاسخی یافت نشد",
)

ARABIC_TO_PERSIAN = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ئ": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "أ": "ا",
        "إ": "ا",
        "ٱ": "ا",
        "ـ": "",
        "\u200c": " ",
        "\u200f": " ",
        "\u200e": " ",
    }
)

DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

PERSIAN_STOPWORDS = {
    "از", "به", "در", "با", "برای", "که", "و", "یا", "را", "این", "آن",
    "است", "هست", "باشد", "شود", "می", "چه", "چقدر", "چند", "آیا",
    "اگر", "یک", "هر", "تا", "پس", "بر", "طبق", "مورد", "درباره",
}

SOURCE_STOPWORDS = {
    "از", "به", "در", "با", "برای", "که", "و", "یا", "را", "این", "آن",
}


NUMBER_WORDS = {
    "صفر": "0", "یک": "1", "اول": "1", "دو": "2", "دوم": "2",
    "سه": "3", "سوم": "3", "چهار": "4", "چهارم": "4",
    "پنج": "5", "پنجم": "5", "شش": "6", "ششم": "6",
    "هفت": "7", "هفتم": "7", "هشت": "8", "هشتم": "8",
    "نه": "9", "نهم": "9", "ده": "10", "دهم": "10",
    "یازده": "11", "یازدهم": "11", "دوازده": "12", "دوازدهم": "12",
    "سیزده": "13", "سیزدهم": "13", "چهارده": "14", "چهاردهم": "14",
    "پانزده": "15", "پانزدهم": "15", "شانزده": "16", "شانزدهم": "16",
    "هفده": "17", "هفدهم": "17", "هجده": "18", "هجدهم": "18",
    "نوزده": "19", "نوزدهم": "19", "بیست": "20", "بیستم": "20",
}

FRACTION_DENOMINATORS = {
    "دوم": "2", "سوم": "3", "چهارم": "4", "پنجم": "5",
    "ششم": "6", "هفتم": "7", "هشتم": "8", "نهم": "9",
    "دهم": "10", "یازدهم": "11", "دوازدهم": "12",
    "سیزدهم": "13", "چهاردهم": "14", "پانزدهم": "15",
    "شانزدهم": "16",
}

# Tokens that do not carry the factual content of an answer.
CONTENT_STOPWORDS = PERSIAN_STOPWORDS | {
    "طبق", "برابر", "اساس", "ماده", "تبصره", "آیین", "نامه", "مقررات",
    "حد", "مجاز", "مقرر", "دوره", "دانشجو", "دانشجوی", "دانشگاه",
    "مقدار", "زمان", "صورت", "عنوان", "لازم", "امکان", "دارد", "تواند",
    "قابل", "خواهد", "گردد", "یابد", "کرد", "کند", "کرده", "شده",
}

GENERIC_SOURCE_TOKENS = SOURCE_STOPWORDS | {
    "ماده", "تبصره", "بند", "پیوست", "شماره",
}


@dataclass(frozen=True)
class EvalItem:
    id: int
    question: str
    ground_truth: str
    source: str
    difficulty: str
    question_type: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def discover_project_root() -> Path:
    """Find the University_RAG project root."""
    candidates = [Path.cwd().resolve(), Path(__file__).resolve().parent]
    checked: set[Path] = set()

    for base in candidates:
        for candidate in (base, *base.parents):
            if candidate in checked:
                continue
            checked.add(candidate)
            if (
                (candidate / "backend").exists()
                and (candidate / "data").exists()
            ):
                return candidate

    return Path.cwd().resolve()


def _replace_number_words(text: str) -> str:
    """Normalize common Persian number words and simple fractions to digits."""
    words = text.split()
    converted: list[str] = []
    i = 0
    while i < len(words):
        current = words[i]
        if i + 1 < len(words):
            numerator = NUMBER_WORDS.get(current)
            denominator = FRACTION_DENOMINATORS.get(words[i + 1])
            if numerator is not None and denominator is not None:
                converted.append(f"{numerator}/{denominator}")
                i += 2
                continue
        converted.append(NUMBER_WORDS.get(current, current))
        i += 1
    return " ".join(converted)


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(ARABIC_TO_PERSIAN)
    text = text.translate(DIGIT_TRANSLATION)
    text = re.sub(r"\[S\d+(?:\s*,\s*S\d+)*\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[\u064b-\u065f\u0670\u06d6-\u06ed]", "", text)
    text = re.sub(r"[^\w\s/.-]", " ", text, flags=re.UNICODE)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return _replace_number_words(text)


def light_stem(token: str) -> str:
    """Very conservative Persian normalization for evaluation only."""
    aliases = {
        "تائید": "تایید",
        "تایید": "تایید",
        "تحصیلی": "تحصیل",
        "دانش‌آموختگی": "دانش آموختگی",
        "ممنوع": "ممنوع",
        "افزایش": "افزایش",
        "کاهش": "کاهش",
        "محرومیت": "محروم",
        "محروم": "محروم",
        "مردودی": "مردود",
        "قبولی": "قبول",
        "پذیرفته": "پذیرش",
    }
    token = aliases.get(token, token)
    if token.isdigit() or "/" in token:
        return token
    for suffix in ("هایی", "های", "ها", "ترین", "تر"):
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            token = token[: -len(suffix)]
            break
    return aliases.get(token, token)


def tokens(
    value: Any,
    *,
    remove_stopwords: bool = False,
    content_only: bool = False,
) -> list[str]:
    items = [
        light_stem(token)
        for token in re.findall(r"[آ-یa-z0-9]+(?:/[0-9]+)?", normalize_text(value))
    ]
    if content_only:
        return [token for token in items if token not in CONTENT_STOPWORDS]
    if remove_stopwords:
        return [token for token in items if token not in PERSIAN_STOPWORDS]
    return items


def _counter_overlap(left: list[str], right: list[str]) -> int:
    return sum((Counter(left) & Counter(right)).values())


def token_f1(prediction: str, truth: str) -> tuple[float, float, float]:
    pred_tokens = tokens(prediction)
    truth_tokens = tokens(truth)

    if not pred_tokens and not truth_tokens:
        return 1.0, 1.0, 1.0
    if not pred_tokens or not truth_tokens:
        return 0.0, 0.0, 0.0

    overlap = _counter_overlap(pred_tokens, truth_tokens)
    precision = overlap / len(pred_tokens)
    recall = overlap / len(truth_tokens)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def content_recall(prediction: str, truth: str) -> float:
    pred_tokens = tokens(prediction, content_only=True)
    truth_tokens = tokens(truth, content_only=True)
    if not truth_tokens:
        return 1.0
    if not pred_tokens:
        return 0.0
    return _counter_overlap(pred_tokens, truth_tokens) / len(truth_tokens)


def best_window_metrics(candidate: str, truth: str) -> dict[str, Any]:
    """Compare gold answer with the best local window of a long candidate."""
    candidate_tokens = tokens(candidate, remove_stopwords=True)
    truth_tokens = tokens(truth, remove_stopwords=True)
    if not candidate_tokens or not truth_tokens:
        return {
            "best_window_f1": 0.0,
            "best_window_recall": 0.0,
            "best_window_numbers": set(),
        }

    target = len(truth_tokens)
    min_size = max(1, target)
    max_size = min(len(candidate_tokens), max(target + 8, target * 3))

    best_f1 = 0.0
    best_recall = 0.0
    best_numbers: set[str] = set()
    best_score = -1.0

    # If the candidate is short, evaluate it as one window.
    sizes = range(min_size, max_size + 1) if len(candidate_tokens) >= min_size else [len(candidate_tokens)]
    for size in sizes:
        if size <= 0:
            continue
        for start in range(0, len(candidate_tokens) - size + 1):
            window = candidate_tokens[start : start + size]
            overlap = _counter_overlap(window, truth_tokens)
            precision = overlap / len(window)
            recall = overlap / len(truth_tokens)
            f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
            # Recall matters more than precision because generated answers may be explanatory.
            score = 0.65 * recall + 0.35 * f1
            if score > best_score:
                best_score = score
                best_f1 = f1
                best_recall = recall
                best_numbers = {token for token in window if re.fullmatch(r"\d+(?:/\d+)?", token)}

    return {
        "best_window_f1": round(best_f1, 4),
        "best_window_recall": round(best_recall, 4),
        "best_window_numbers": best_numbers,
    }


def extract_numbers(value: Any) -> set[str]:
    return set(re.findall(r"\d+(?:[./-]\d+)*", normalize_text(value)))


def has_no_answer_text(answer: str) -> bool:
    normalized = normalize_text(answer)
    return any(normalize_text(phrase) in normalized for phrase in NO_ANSWER_PHRASES)


def yes_no_polarity(value: Any) -> str | None:
    normalized = normalize_text(value)
    positive = bool(
        re.search(
            r"(^|\s)(بله|مجاز است|امکان دارد|می تواند|میتواند|مجاز می باشد)(\s|$)",
            normalized,
        )
    )
    negative = bool(
        re.search(
            r"(^|\s)(خیر|نه|مجاز نیست|ممنوع است|نمی تواند|نمیتواند)(\s|$)",
            normalized,
        )
    )
    if positive and not negative:
        return "yes"
    if negative and not positive:
        return "no"
    return None


def score_answer(answer: str, ground_truth: str, no_answer: bool) -> dict[str, Any]:
    answer_norm = normalize_text(answer)
    truth_norm = normalize_text(ground_truth)

    exact_match = bool(answer_norm and answer_norm == truth_norm)
    containment = bool(
        answer_norm
        and truth_norm
        and (truth_norm in answer_norm or answer_norm in truth_norm)
    )

    precision, recall, f1 = token_f1(answer, ground_truth)
    key_recall = content_recall(answer, ground_truth)
    window = best_window_metrics(answer, ground_truth)

    truth_numbers = extract_numbers(ground_truth)
    answer_numbers = extract_numbers(answer)
    number_match = not truth_numbers or truth_numbers.issubset(answer_numbers)

    truth_polarity = yes_no_polarity(ground_truth)
    answer_polarity = yes_no_polarity(answer)
    polarity_match = truth_polarity is None or answer_polarity == truth_polarity

    effective_no_answer = bool(no_answer or has_no_answer_text(answer))

    truth_content_tokens = tokens(ground_truth, content_only=True)
    short_gold = len(truth_content_tokens) <= 3
    polarity_only = truth_polarity is not None and len(truth_content_tokens) <= 1

    semantic_match = bool(
        exact_match
        or containment
        or key_recall >= 0.72
        or window["best_window_recall"] >= 0.78
        or window["best_window_f1"] >= 0.72
    )
    if short_gold and truth_content_tokens:
        semantic_match = key_recall >= 0.99 or containment
    if polarity_only:
        semantic_match = polarity_match

    answer_key_score = (
        0.45 * key_recall
        + 0.35 * float(window["best_window_recall"])
        + 0.20 * float(window["best_window_f1"])
    )

    heuristic_correct = bool(
        not effective_no_answer
        and semantic_match
        and number_match
        and polarity_match
    )

    return {
        "exact_match": exact_match,
        "containment_match": containment,
        "token_precision": round(precision, 4),
        "token_recall": round(recall, 4),
        "token_f1": round(f1, 4),
        "answer_key_recall": round(key_recall, 4),
        "best_window_recall": window["best_window_recall"],
        "best_window_f1": window["best_window_f1"],
        "answer_key_score": round(answer_key_score, 4),
        "number_match": number_match,
        "polarity_match": polarity_match,
        "effective_no_answer": effective_no_answer,
        "heuristic_correct": heuristic_correct,
    }


def source_blob(source: dict[str, Any]) -> str:
    parts = [
        source.get("source_id"),
        source.get("title"),
        source.get("category"),
        source.get("article"),
        source.get("note"),
        source.get("text"),
    ]
    return " ".join(str(part) for part in parts if part is not None)


def _reference_tokens(expected_source: str) -> list[str]:
    return [
        token
        for token in tokens(expected_source)
        if token not in GENERIC_SOURCE_TOKENS
    ]


def source_match_details(
    expected_source: str,
    ground_truth: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    expected_norm = normalize_text(expected_source)
    blob = source_blob(source)
    blob_norm = normalize_text(blob)

    direct_reference = bool(expected_norm and expected_norm in blob_norm)

    expected_tokens = _reference_tokens(expected_source)
    blob_tokens = set(tokens(blob))
    token_reference = bool(expected_tokens) and all(
        token in blob_tokens for token in expected_tokens
    )

    evidence = best_window_metrics(str(source.get("text") or blob), ground_truth)
    truth_numbers = extract_numbers(ground_truth)
    local_numbers = set(evidence["best_window_numbers"])
    local_number_match = not truth_numbers or truth_numbers.issubset(local_numbers)

    # OCR-tolerant evidence match: the expected article number may lose a digit
    # (e.g. ماده ۲۶ -> ماده ۶), but the local passage still states the gold rule.
    evidence_match = bool(
        local_number_match
        and (
            evidence["best_window_recall"] >= 0.78
            or evidence["best_window_f1"] >= 0.72
        )
    )

    matched = direct_reference or token_reference or evidence_match
    if direct_reference:
        reason = "exact_reference"
    elif token_reference:
        reason = "reference_tokens"
    elif evidence_match:
        reason = "gold_evidence_ocr_tolerant"
    else:
        reason = "no_match"

    evidence_score = (
        0.65 * float(evidence["best_window_recall"])
        + 0.35 * float(evidence["best_window_f1"])
    )

    return {
        "matched": matched,
        "reason": reason,
        "direct_reference": direct_reference,
        "token_reference": token_reference,
        "evidence_score": round(evidence_score, 4),
        "evidence_recall": evidence["best_window_recall"],
        "evidence_f1": evidence["best_window_f1"],
        "evidence_number_match": local_number_match,
    }


def source_metrics(
    expected_source: str,
    ground_truth: str,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    hit_rank: int | None = None
    hit_details: dict[str, Any] | None = None
    best_evidence_score = 0.0

    for rank, source in enumerate(sources, start=1):
        details = source_match_details(expected_source, ground_truth, source)
        best_evidence_score = max(best_evidence_score, float(details["evidence_score"]))
        if details["matched"] and hit_rank is None:
            hit_rank = rank
            hit_details = details

    return {
        "source_hit": hit_rank is not None,
        "source_hit_rank": hit_rank,
        "source_hit_reason": hit_details["reason"] if hit_details else "no_match",
        "source_reference_match": bool(
            hit_details
            and (hit_details["direct_reference"] or hit_details["token_reference"])
        ),
        "source_evidence_score": (
            hit_details["evidence_score"] if hit_details else round(best_evidence_score, 4)
        ),
        "reciprocal_rank": round(1.0 / hit_rank, 4) if hit_rank else 0.0,
        "source_hit_at_1": bool(hit_rank and hit_rank <= 1),
        "source_hit_at_3": bool(hit_rank and hit_rank <= 3),
        "source_hit_at_5": bool(hit_rank and hit_rank <= 5),
    }

def request_json(
    session: Session,
    method: str,
    url: str,
    *,
    timeout: float,
    retries: int,
    **kwargs: Any,
) -> dict[str, Any]:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response: Response = session.request(
                method,
                url,
                timeout=timeout,
                **kwargs,
            )
            if response.status_code >= 400:
                detail: Any
                try:
                    detail = response.json()
                except Exception:
                    detail = response.text
                raise RuntimeError(
                    f"HTTP {response.status_code} for {url}: {detail}"
                )
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError(f"Expected JSON object from {url}.")
            return data
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            wait_seconds = min(2 ** (attempt - 1), 8)
            print(
                f"  Retry {attempt}/{retries - 1} after error: {exc}",
                file=sys.stderr,
            )
            time.sleep(wait_seconds)

    assert last_error is not None
    raise last_error


def ensure_backend_ready(
    session: Session,
    base_url: str,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    health = request_json(
        session,
        "GET",
        f"{base_url}/api/health",
        timeout=timeout,
        retries=retries,
    )
    if not health.get("retriever_ready"):
        raise RuntimeError(
            f"Retriever is not ready: {health.get('warnings') or health}"
        )
    return health


def get_llm_settings(
    session: Session,
    base_url: str,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    return request_json(
        session,
        "GET",
        f"{base_url}/api/settings/llm",
        timeout=timeout,
        retries=retries,
    )


def configure_provider(
    session: Session,
    *,
    base_url: str,
    provider: str,
    model: str | None,
    api_key: str | None,
    timeout: float,
    retries: int,
    no_prompt: bool,
    allow_mock: bool,
) -> dict[str, Any]:
    if provider == "current":
        settings = get_llm_settings(session, base_url, timeout, retries)
        active = str(settings.get("active_provider", "mock"))
        if active == "mock" and not allow_mock:
            raise RuntimeError(
                "این Session روی mock است. برای ارزیابی واقعی، "
                "--provider gemini را استفاده کنید یا --allow-mock بزنید."
            )
        return settings

    if provider == "mock" and not allow_mock:
        raise RuntimeError(
            "ارزیابی با mock به‌صورت پیش‌فرض مسدود است. "
            "در صورت نیاز صریحاً --allow-mock را اضافه کنید."
        )

    payload = {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "remember_on_device": False,
    }

    try:
        return request_json(
            session,
            "PUT",
            f"{base_url}/api/settings/llm",
            json=payload,
            timeout=timeout,
            retries=1,
        )
    except Exception as first_error:
        if provider in {"gemini", "openai"} and not api_key and not no_prompt:
            print(
                f"کلید {provider} در Session ارزیاب پیدا نشد.",
                file=sys.stderr,
            )
            entered_key = getpass.getpass(
                f"{provider.upper()} API Key را وارد کنید "
                "(در صفحه نمایش داده نمی‌شود): "
            ).strip()
            if entered_key:
                payload["api_key"] = entered_key
                return request_json(
                    session,
                    "PUT",
                    f"{base_url}/api/settings/llm",
                    json=payload,
                    timeout=timeout,
                    retries=retries,
                )
        raise RuntimeError(
            "تنظیم Provider برای ارزیابی ناموفق بود. "
            "API Key را در متغیر محیطی قرار دهید یا اجازه Prompt بدهید.\n"
            f"Original error: {first_error}"
        ) from first_error


def load_benchmark(path: Path) -> list[EvalItem]:
    if not path.exists():
        raise FileNotFoundError(f"Benchmark not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Benchmark root must be a JSON list.")

    items: list[EvalItem] = []
    required = {
        "id", "question", "ground_truth", "source",
        "difficulty", "question_type",
    }

    for index, row in enumerate(raw, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Benchmark row {index} is not an object.")
        missing = required - set(row)
        if missing:
            raise ValueError(
                f"Benchmark row {index} is missing fields: {sorted(missing)}"
            )
        items.append(
            EvalItem(
                id=int(row["id"]),
                question=str(row["question"]).strip(),
                ground_truth=str(row["ground_truth"]).strip(),
                source=str(row["source"]).strip(),
                difficulty=str(row["difficulty"]).strip(),
                question_type=str(row["question_type"]).strip(),
            )
        )

    return sorted(items, key=lambda item: item.id)


def load_completed_keys(raw_jsonl: Path) -> set[tuple[str, int]]:
    completed: set[tuple[str, int]] = set()
    if not raw_jsonl.exists():
        return completed

    with raw_jsonl.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                completed.add((str(row["mode"]), int(row["id"])))
            except Exception:
                continue
    return completed


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def citation_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    citations = [str(value) for value in payload.get("citations", [])]
    sources = payload.get("sources") or []
    valid_ids = {
        str(source.get("source_id"))
        for source in sources
        if isinstance(source, dict)
    }
    valid = bool(citations) and all(citation in valid_ids for citation in citations)
    return {
        "citation_count": len(citations),
        "has_citation": bool(citations),
        "citations_valid": valid,
    }


def evaluate_one(
    session: Session,
    *,
    base_url: str,
    item: EvalItem,
    mode: str,
    top_k: int,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    payload = request_json(
        session,
        "POST",
        f"{base_url}/api/query",
        json={
            "question": item.question,
            "top_k": top_k,
            "retrieval_mode": mode,
            "force_refresh": False,
        },
        timeout=timeout,
        retries=retries,
    )
    wall_latency = time.perf_counter() - started

    answer = str(payload.get("answer", ""))
    answer_scores = score_answer(
        answer,
        item.ground_truth,
        bool(payload.get("no_answer")),
    )
    sources = [
        source for source in (payload.get("sources") or [])
        if isinstance(source, dict)
    ]
    retrieval_scores = source_metrics(item.source, item.ground_truth, sources)
    citations = citation_metrics(payload)

    result: dict[str, Any] = {
        "id": item.id,
        "mode": mode,
        "question": item.question,
        "ground_truth": item.ground_truth,
        "expected_source": item.source,
        "difficulty": item.difficulty,
        "question_type": item.question_type,
        "answer": answer,
        "api_no_answer": bool(payload.get("no_answer")),
        "confidence": payload.get("confidence"),
        "provider_alias": payload.get("provider_alias"),
        "model": payload.get("model"),
        "retriever_method": payload.get("retriever_method"),
        "api_latency_seconds": payload.get("latency_seconds"),
        "wall_latency_seconds": round(wall_latency, 3),
        "citations": payload.get("citations") or [],
        "sources": sources,
        "diagnostics": payload.get("diagnostics"),
        "evaluated_at": now_iso(),
        **answer_scores,
        **retrieval_scores,
        **citations,
    }
    return result


def safe_mean(values: Iterable[float]) -> float:
    values_list = list(values)
    return round(statistics.fmean(values_list), 4) if values_list else 0.0


def percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return round(ordered[0], 4)

    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 4)
    weight = position - lower
    value = ordered[lower] * (1 - weight) + ordered[upper] * weight
    return round(value, 4)


def summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {
            "total": 0,
            "heuristic_accuracy": 0.0,
            "exact_match_rate": 0.0,
            "source_recall_at_1": 0.0,
            "source_recall_at_3": 0.0,
            "source_recall_at_5": 0.0,
            "source_recall_at_k": 0.0,
            "mean_reciprocal_rank": 0.0,
            "no_answer_rate": 0.0,
            "citation_rate": 0.0,
            "valid_citation_rate": 0.0,
            "mean_token_f1": 0.0,
            "mean_answer_key_recall": 0.0,
            "mean_answer_key_score": 0.0,
            "provider_success_rate": 0.0,
            "fallback_rate": 0.0,
            "mean_latency_seconds": 0.0,
            "p95_latency_seconds": 0.0,
        }

    correct_count = sum(bool(row.get("heuristic_correct")) for row in rows)
    source_hit_count = sum(bool(row.get("source_hit")) for row in rows)
    fallback_count = sum(
        bool((row.get("diagnostics") or {}).get("fallback_used")) for row in rows
    )
    provider_success_count = sum(
        not bool((row.get("diagnostics") or {}).get("fallback_used"))
        and not bool((row.get("diagnostics") or {}).get("generation_error"))
        for row in rows
    )

    return {
        "total": total,
        "heuristic_correct_count": correct_count,
        "heuristic_accuracy": round(correct_count / total, 4),
        "exact_match_rate": round(
            sum(bool(row.get("exact_match")) for row in rows) / total, 4
        ),
        "source_hit_count": source_hit_count,
        "source_recall_at_1": round(
            sum(bool(row.get("source_hit_at_1")) for row in rows) / total, 4
        ),
        "source_recall_at_3": round(
            sum(bool(row.get("source_hit_at_3")) for row in rows) / total, 4
        ),
        "source_recall_at_5": round(
            sum(bool(row.get("source_hit_at_5")) for row in rows) / total, 4
        ),
        # Backward-compatible alias: current API asks top-k sources.
        "source_recall_at_k": round(source_hit_count / total, 4),
        "mean_reciprocal_rank": safe_mean(
            float(row.get("reciprocal_rank", 0.0)) for row in rows
        ),
        "no_answer_count": sum(bool(row.get("effective_no_answer")) for row in rows),
        "no_answer_rate": round(
            sum(bool(row.get("effective_no_answer")) for row in rows) / total, 4
        ),
        "citation_rate": round(
            sum(bool(row.get("has_citation")) for row in rows) / total, 4
        ),
        "valid_citation_rate": round(
            sum(bool(row.get("citations_valid")) for row in rows) / total, 4
        ),
        "mean_token_f1": safe_mean(float(row.get("token_f1", 0.0)) for row in rows),
        "mean_answer_key_recall": safe_mean(
            float(row.get("answer_key_recall", 0.0)) for row in rows
        ),
        "mean_answer_key_score": safe_mean(
            float(row.get("answer_key_score", 0.0)) for row in rows
        ),
        "provider_success_rate": round(provider_success_count / total, 4),
        "fallback_rate": round(fallback_count / total, 4),
        "mean_latency_seconds": safe_mean(
            float(row.get("wall_latency_seconds", 0.0)) for row in rows
        ),
        "p95_latency_seconds": percentile(
            (float(row.get("wall_latency_seconds", 0.0)) for row in rows),
            0.95,
        ),
    }

def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, Any] = {}
    mode_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        mode_rows[str(row["mode"])].append(row)

    for mode, current_rows in sorted(mode_rows.items()):
        by_difficulty: dict[str, Any] = {}
        difficulty_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in current_rows:
            difficulty_rows[str(row["difficulty"])].append(row)
        for difficulty, subset in sorted(difficulty_rows.items()):
            by_difficulty[difficulty] = summarize_group(subset)

        by_type: dict[str, Any] = {}
        type_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in current_rows:
            type_rows[str(row["question_type"])].append(row)
        for question_type, subset in sorted(type_rows.items()):
            by_type[question_type] = summarize_group(subset)

        by_mode[mode] = {
            "overall": summarize_group(current_rows),
            "by_difficulty": by_difficulty,
            "by_question_type": by_type,
        }

    winner: str | None = None
    if by_mode:
        winner = max(
            by_mode,
            key=lambda mode: (
                by_mode[mode]["overall"]["heuristic_accuracy"],
                by_mode[mode]["overall"]["source_recall_at_k"],
                by_mode[mode]["overall"]["mean_reciprocal_rank"],
                -by_mode[mode]["overall"]["mean_latency_seconds"],
            ),
        )

    return {
        "generated_at": now_iso(),
        "automatic_scoring_note": (
            "heuristic_accuracy uses OCR-tolerant Persian normalization, answer-key "
            "coverage, best local-window matching, numeric consistency and "
            "yes/no polarity. It remains an automatic estimate; manually "
            "review borderline cases before final scientific reporting."
        ),
        "modes": by_mode,
        "automatic_winner": winner,
    }


CSV_FIELDS = [
    "id",
    "mode",
    "difficulty",
    "question_type",
    "question",
    "ground_truth",
    "expected_source",
    "answer",
    "heuristic_correct",
    "exact_match",
    "containment_match",
    "token_precision",
    "token_recall",
    "token_f1",
    "answer_key_recall",
    "best_window_recall",
    "best_window_f1",
    "answer_key_score",
    "number_match",
    "polarity_match",
    "effective_no_answer",
    "source_hit",
    "source_hit_rank",
    "source_hit_reason",
    "source_reference_match",
    "source_evidence_score",
    "source_hit_at_1",
    "source_hit_at_3",
    "source_hit_at_5",
    "reciprocal_rank",
    "has_citation",
    "citations_valid",
    "citation_count",
    "confidence",
    "provider_alias",
    "model",
    "retriever_method",
    "api_latency_seconds",
    "wall_latency_seconds",
    "citations",
    "source_titles",
    "evaluated_at",
]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for row in sorted(rows, key=lambda item: (str(item["mode"]), int(item["id"]))):
            flattened = dict(row)
            flattened["citations"] = " | ".join(str(x) for x in row.get("citations", []))
            flattened["source_titles"] = " | ".join(
                str(source.get("title", ""))
                for source in row.get("sources", [])
            )
            writer.writerow(
                {field: flattened.get(field) for field in CSV_FIELDS}
            )


def percent(value: float) -> str:
    return f"{100 * float(value):.1f}%"


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(value).replace("|", r"\|") for value in row)
            + " |"
        )
    return "\n".join(lines)


def write_report(
    path: Path,
    *,
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    benchmark_path: Path,
    base_url: str,
    top_k: int,
) -> None:
    mode_table_rows: list[list[Any]] = []
    for mode, data in summary["modes"].items():
        overall = data["overall"]
        mode_table_rows.append(
            [
                mode,
                overall["total"],
                percent(overall["heuristic_accuracy"]),
                percent(overall["source_recall_at_1"]),
                percent(overall["source_recall_at_3"]),
                percent(overall["source_recall_at_5"]),
                f'{overall["mean_reciprocal_rank"]:.3f}',
                percent(overall["no_answer_rate"]),
                percent(overall["valid_citation_rate"]),
                f'{overall["mean_token_f1"]:.3f}',
                f'{overall["mean_answer_key_score"]:.3f}',
                percent(overall["provider_success_rate"]),
                f'{overall["mean_latency_seconds"]:.2f}s',
                f'{overall["p95_latency_seconds"]:.2f}s',
            ]
        )

    difficulty_rows: list[list[Any]] = []
    for mode, data in summary["modes"].items():
        for difficulty, metrics in data["by_difficulty"].items():
            difficulty_rows.append(
                [
                    mode,
                    difficulty,
                    metrics["total"],
                    percent(metrics["heuristic_accuracy"]),
                    percent(metrics["source_recall_at_k"]),
                    percent(metrics["no_answer_rate"]),
                ]
            )

    type_rows: list[list[Any]] = []
    for mode, data in summary["modes"].items():
        for question_type, metrics in data["by_question_type"].items():
            type_rows.append(
                [
                    mode,
                    question_type,
                    metrics["total"],
                    percent(metrics["heuristic_accuracy"]),
                    percent(metrics["source_recall_at_k"]),
                    percent(metrics["no_answer_rate"]),
                ]
            )

    failures = [
        row for row in rows
        if not row["heuristic_correct"] or not row["source_hit"]
    ]
    failures = sorted(
        failures,
        key=lambda row: (
            str(row["mode"]),
            bool(row["heuristic_correct"]),
            bool(row["source_hit"]),
            int(row["id"]),
        ),
    )

    failure_rows: list[list[Any]] = []
    for row in failures[:30]:
        answer_preview = re.sub(r"\s+", " ", str(row["answer"])).strip()
        if len(answer_preview) > 120:
            answer_preview = answer_preview[:117] + "..."
        failure_rows.append(
            [
                row["mode"],
                row["id"],
                row["difficulty"],
                "✅" if row["heuristic_correct"] else "❌",
                "✅" if row["source_hit"] else "❌",
                f'{float(row.get("token_f1", 0.0)):.2f}',
                f'{float(row.get("answer_key_score", 0.0)):.2f}',
                row["expected_source"],
                answer_preview,
            ]
        )

    report = f"""# University_RAG Evaluation Report

- Generated: `{summary["generated_at"]}`
- Benchmark: `{benchmark_path}`
- Backend: `{base_url}`
- Top-k: `{top_k}`
- Automatic winner: **{summary.get("automatic_winner") or "N/A"}**

> **Important:** `heuristic_accuracy` is an OCR-tolerant automatic estimate
> based on answer-key coverage, local-window similarity, required numbers and
> yes/no polarity. It is more suitable for explanatory Persian answers than raw
> token F1, but final scientific reporting should still include manual review.

## Overall comparison

{markdown_table(
    [
        "Mode", "N", "Answer accuracy", "Recall@1", "Recall@3", "Recall@5", "MRR",
        "No-answer", "Valid citations", "Mean token F1", "Answer-key score",
        "Provider success", "Mean latency", "P95 latency",
    ],
    mode_table_rows,
)}

## Results by difficulty

{markdown_table(
    ["Mode", "Difficulty", "N", "Accuracy", "Source recall@k", "No-answer"],
    difficulty_rows,
)}

## Results by question type

{markdown_table(
    ["Mode", "Question type", "N", "Accuracy", "Source recall@k", "No-answer"],
    type_rows,
)}

## First cases needing review

{markdown_table(
    [
        "Mode", "ID", "Difficulty", "Answer OK", "Source OK", "Token F1",
        "Key score", "Expected source", "Answer preview",
    ],
    failure_rows,
)}

## Output files

- `per_question_results.csv`: one row per question/mode
- `raw_results.jsonl`: complete backend responses, resume-safe
- `raw_results_rescored.jsonl`: regenerated metrics when using `--recalculate-only`
- `summary.json`: machine-readable aggregate metrics
- `evaluation_report.md`: this report
"""
    path.write_text(report, encoding="utf-8")



def rescore_saved_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recompute metrics from saved answers/sources without any API calls."""
    rescored: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        answer_scores = score_answer(
            str(row.get("answer", "")),
            str(row.get("ground_truth", "")),
            bool(row.get("api_no_answer")),
        )
        sources = [
            source for source in (row.get("sources") or [])
            if isinstance(source, dict)
        ]
        retrieval_scores = source_metrics(
            str(row.get("expected_source", "")),
            str(row.get("ground_truth", "")),
            sources,
        )
        payload_like = {
            "citations": row.get("citations") or [],
            "sources": sources,
        }
        row.update(answer_scores)
        row.update(retrieval_scores)
        row.update(citation_metrics(payload_like))
        row["rescored_at"] = now_iso()
        rescored.append(row)
    return rescored


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

def parse_args() -> argparse.Namespace:
    project_root = discover_project_root()

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate University_RAG on rag_eval_100.json using Best and Hybrid."
        )
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("RAG_BASE_URL", DEFAULT_BASE_URL),
        help=f"Backend base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=project_root / "evaluation" / "rag_eval_100.json",
        help="Path to rag_eval_100.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "reports" / "rag_evaluation",
        help="Directory for CSV/JSON/Markdown outputs",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=["best", "hybrid"],
        default=list(DEFAULT_MODES),
        help="Retrieval modes to evaluate",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only evaluate the first N benchmark questions",
    )
    parser.add_argument(
        "--start-id",
        type=int,
        default=None,
        help="Only evaluate questions with id >= this value",
    )
    parser.add_argument(
        "--end-id",
        type=int,
        default=None,
        help="Only evaluate questions with id <= this value",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of sources requested from the backend (default: 5)",
    )
    parser.add_argument(
        "--provider",
        choices=["current", "gemini", "openai", "mock"],
        default="gemini",
        help="LLM provider for this evaluation Session (default: gemini)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("RAG_EVAL_MODEL", DEFAULT_MODEL),
        help=f"Model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help=(
            "Environment variable containing the API key. Defaults to "
            "GEMINI_API_KEY or OPENAI_API_KEY based on provider."
        ),
    )
    parser.add_argument(
        "--allow-mock",
        action="store_true",
        help="Explicitly allow evaluation with the mock provider",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not securely prompt for a missing API key",
    )
    parser.add_argument(
        "--recalculate-only",
        action="store_true",
        help=(
            "Recalculate all metrics from an existing raw_results.jsonl "
            "without calling the backend or Gemini"
        ),
    )
    parser.add_argument(
        "--raw-results",
        type=Path,
        default=None,
        help=(
            "Path to an existing raw_results.jsonl for --recalculate-only; "
            "defaults to OUTPUT_DIR/raw_results.jsonl"
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue an interrupted run using raw_results.jsonl",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete previous evaluation outputs before running",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="Delay between requests in seconds (default: 0.35)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="HTTP timeout per request in seconds (default: 180)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retries for transient request failures (default: 3)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = str(args.base_url).rstrip("/")
    benchmark_path = args.benchmark.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    raw_jsonl = output_dir / "raw_results.jsonl"
    csv_path = output_dir / "per_question_results.csv"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "evaluation_report.md"

    if args.top_k < 1 or args.top_k > 20:
        raise SystemExit("--top-k must be between 1 and 20.")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive.")
    if args.delay < 0:
        raise SystemExit("--delay cannot be negative.")

    output_dir.mkdir(parents=True, exist_ok=True)

    if args.recalculate_only:
        existing_raw = (
            args.raw_results.expanduser().resolve()
            if args.raw_results is not None
            else raw_jsonl
        )
        if not existing_raw.exists():
            raise SystemExit(f"Raw results not found: {existing_raw}")
        rows = rescore_saved_rows(read_jsonl(existing_raw))
        if not rows:
            raise SystemExit("No rows found in the supplied raw results file.")

        rescored_jsonl = output_dir / "raw_results_rescored.jsonl"
        write_jsonl(rescored_jsonl, rows)
        summary = build_summary(rows)
        summary["run_configuration"] = {
            "recalculate_only": True,
            "source_raw_results": str(existing_raw),
            "completed_rows": len(rows),
            "modes": sorted({str(row.get("mode")) for row in rows}),
        }
        write_csv(csv_path, rows)
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_report(
            report_path,
            summary=summary,
            rows=rows,
            benchmark_path=benchmark_path,
            base_url=base_url,
            top_k=args.top_k,
        )
        print("Metrics recalculated without backend/Gemini calls.")
        print(f"Rescored JSON: {rescored_jsonl}")
        print(f"CSV:           {csv_path}")
        print(f"Summary:       {summary_path}")
        print(f"Report:        {report_path}")
        return 0

    if args.reset:
        for path in (raw_jsonl, csv_path, summary_path, report_path):
            path.unlink(missing_ok=True)

    if raw_jsonl.exists() and not args.resume and not args.reset:
        raise SystemExit(
            f"Previous results exist at:\n  {raw_jsonl}\n"
            "Use --resume to continue or --reset to start over."
        )

    benchmark = load_benchmark(benchmark_path)
    if args.start_id is not None:
        benchmark = [item for item in benchmark if item.id >= args.start_id]
    if args.end_id is not None:
        benchmark = [item for item in benchmark if item.id <= args.end_id]
    if args.limit is not None:
        benchmark = benchmark[: args.limit]

    if not benchmark:
        raise SystemExit("No benchmark questions selected.")

    api_key_env = args.api_key_env
    if api_key_env is None:
        if args.provider == "gemini":
            api_key_env = "GEMINI_API_KEY"
        elif args.provider == "openai":
            api_key_env = "OPENAI_API_KEY"

    api_key = os.getenv(api_key_env, "").strip() if api_key_env else None

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "University-RAG-Evaluator/1.0",
        }
    )

    print("=" * 72)
    print("University_RAG evaluator")
    print(f"Backend:   {base_url}")
    print(f"Benchmark: {benchmark_path}")
    print(f"Questions: {len(benchmark)}")
    print(f"Modes:     {', '.join(args.modes)}")
    print(f"Top-k:     {args.top_k}")
    print(f"Output:    {output_dir}")
    print("=" * 72)

    health = ensure_backend_ready(
        session,
        base_url,
        args.timeout,
        args.retries,
    )
    print(
        "Backend OK | "
        f"retriever={health.get('selected_retriever')} | "
        f"chunks={health.get('chunks')} | documents={health.get('documents')}"
    )

    llm_settings = configure_provider(
        session,
        base_url=base_url,
        provider=args.provider,
        model=args.model,
        api_key=api_key,
        timeout=args.timeout,
        retries=args.retries,
        no_prompt=args.no_prompt,
        allow_mock=args.allow_mock,
    )
    print(
        "LLM session | "
        f"provider={llm_settings.get('active_provider')} | model={args.model}"
    )

    completed = load_completed_keys(raw_jsonl) if args.resume else set()
    planned = [
        (mode, item)
        for mode in args.modes
        for item in benchmark
        if (mode, item.id) not in completed
    ]

    total_planned = len(planned)
    print(
        f"Requests remaining: {total_planned} "
        f"(completed from resume: {len(completed)})"
    )

    failures: list[dict[str, Any]] = []

    for sequence, (mode, item) in enumerate(planned, start=1):
        print(
            f"[{sequence:03d}/{total_planned:03d}] "
            f"{mode:<6} | Q{item.id:03d} | {item.question}"
        )
        try:
            row = evaluate_one(
                session,
                base_url=base_url,
                item=item,
                mode=mode,
                top_k=args.top_k,
                timeout=args.timeout,
                retries=args.retries,
            )
            append_jsonl(raw_jsonl, row)
            print(
                "  "
                f"answer={'OK' if row['heuristic_correct'] else 'REVIEW'} | "
                f"source={'HIT' if row['source_hit'] else 'MISS'} | "
                f"f1={row['token_f1']:.2f} | "
                f"latency={row['wall_latency_seconds']:.2f}s"
            )
        except KeyboardInterrupt:
            print("\nInterrupted. Partial results are already saved.")
            break
        except Exception as exc:
            failure = {
                "id": item.id,
                "mode": mode,
                "question": item.question,
                "error": f"{type(exc).__name__}: {exc}",
                "evaluated_at": now_iso(),
            }
            failures.append(failure)
            print(f"  ERROR: {failure['error']}", file=sys.stderr)

        if args.delay:
            time.sleep(args.delay)

    rows = read_jsonl(raw_jsonl)
    selected_ids = {item.id for item in benchmark}
    selected_modes = set(args.modes)
    rows = [
        row
        for row in rows
        if int(row.get("id", -1)) in selected_ids
        and str(row.get("mode")) in selected_modes
    ]

    if not rows:
        raise SystemExit("No successful results were produced.")

    summary = build_summary(rows)
    summary["run_configuration"] = {
        "base_url": base_url,
        "benchmark": str(benchmark_path),
        "modes": list(args.modes),
        "top_k": args.top_k,
        "question_count": len(benchmark),
        "provider": args.provider,
        "model": args.model,
        "completed_rows": len(rows),
        "request_failures": failures,
    }

    write_csv(csv_path, rows)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(
        report_path,
        summary=summary,
        rows=rows,
        benchmark_path=benchmark_path,
        base_url=base_url,
        top_k=args.top_k,
    )

    print("\n" + "=" * 72)
    print("Evaluation finished")
    for mode, data in summary["modes"].items():
        overall = data["overall"]
        print(
            f"{mode:<6} | "
            f"accuracy={percent(overall['heuristic_accuracy'])} | "
            f"source_recall@{args.top_k}={percent(overall['source_recall_at_k'])} | "
            f"no_answer={percent(overall['no_answer_rate'])} | "
            f"mean_latency={overall['mean_latency_seconds']:.2f}s"
        )
    print(f"Automatic winner: {summary.get('automatic_winner')}")
    print(f"CSV:      {csv_path}")
    print(f"Summary:  {summary_path}")
    print(f"Report:   {report_path}")
    print(f"Raw JSON: {raw_jsonl}")
    if failures:
        print(f"Request failures: {len(failures)} (see summary.json)")
    print("=" * 72)

    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
