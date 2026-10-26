from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from tenacity import retry, stop_after_attempt, wait_exponential

from backend.app.config import Settings
from backend.app.services.llm_settings import ResolvedProviderConfig
from backend.app.utils.text import (
    extract_first_json_object,
    inline_citations,
    lexical_relevance_features,
    safe_float,
)

logger = logging.getLogger(__name__)

NO_ANSWER_MESSAGE = "پاسخ این سؤال در اسناد موجود یافت نشد."

SYSTEM_PROMPT = f"""
شما دستیار دقیق آیین‌نامه‌ها و اسناد دانشگاهی هستید.

قواعد قطعی:
1. فقط از شواهد داده‌شده استفاده کن و از دانش بیرونی یا حدس استفاده نکن.
2. هر ادعای واقعی باید ارجاع درون‌متنی مثل [S1] یا [S2] داشته باشد.
3. فقط شناسه‌های منبعی را استفاده کن که در شواهد وجود دارند.
4. عنوان، شماره ماده، تاریخ، شرط یا استثنا را اختراع نکن.
5. اگر شواهد برای پاسخ کافی نیست، دقیقاً بنویس:
{NO_ANSWER_MESSAGE}
6. پاسخ باید فارسی طبیعی، روشن و تا حد ممکن کوتاه باشد.
7. برای سؤال‌های عمومی درباره حکم آیین‌نامه، «مقررات ابلاغی مستقیم» یا «آیین‌نامه یکپارچه مستقیم» بر شیوه‌نامه اجرایی و مجموعه‌های گردآوری‌شده اولویت قطعی دارد؛ حتی اگر هر دو مربوط به یک سال باشند.
8. عبارت‌هایی مانند تمدید نیمسال پنجم یا ششم در یک شیوه‌نامه اجرایی، لزوماً تعریف «حداکثر مدت مجاز پایه» نیستند. آن‌ها را فقط وقتی به‌عنوان پاسخ اصلی استفاده کن که سؤال صریحاً درباره فرایند تمدید، شیوه‌نامه دانشگاه یا سنوات اضافی باشد.
9. اگر چند نسخه مستقیم درباره یک موضوع تعارض دارند، حکم سند جدیدتر را ملاک قرار بده؛ مگر اینکه سؤال صریحاً درباره سال قدیمی باشد.
10. منبع قدیمی‌تر یا اجرایی فقط می‌تواند برای بخشی استفاده شود که با متن مستقیم جدیدتر تعارض ندارد و در شواهد مستقیم ناقص یا ناخواناست.
11. فقط یک JSON معتبر و بدون Markdown برگردان.
""".strip()


@dataclass(slots=True)
class GenerationOutput:
    answer: str
    citations: list[str]
    no_answer: bool
    confidence: float
    provider_alias: str
    model: str
    latency_seconds: float
    raw_output: str
    error: str | None = None
    metadata: dict[str, Any] | None = None


class Generator(Protocol):
    alias: str
    model: str

    def generate(
        self,
        question: str,
        context: str,
        valid_source_ids: set[str],
    ) -> GenerationOutput: ...


def build_user_prompt(question: str, context: str) -> str:
    return f"""
سؤال کاربر:
{question}

شواهد بازیابی‌شده:
{context}

فقط JSON زیر را برگردان:
{{
  "answer": "پاسخ فارسی همراه با ارجاع‌های درون‌متنی مانند [S1]",
  "citations": ["S1"],
  "no_answer": false,
  "confidence": 0.0,
  "reason": "توضیح بسیار کوتاه درباره کافی بودن شواهد"
}}

اگر پاسخ در شواهد نیست:
{{
  "answer": "{NO_ANSWER_MESSAGE}",
  "citations": [],
  "no_answer": true,
  "confidence": 0.0,
  "reason": "شواهد کافی نیست"
}}
""".strip()


def parse_and_validate(
    raw_text: str,
    valid_source_ids: set[str],
) -> tuple[str, list[str], bool, float, dict[str, Any]]:
    parsed = extract_first_json_object(raw_text) or {}

    answer = str(parsed.get("answer", "") or "").strip()
    listed = parsed.get("citations", [])
    if not isinstance(listed, list):
        listed = [listed]
    listed_ids = [
        str(value).strip().strip("[]") for value in listed if str(value).strip()
    ]
    inline_ids = inline_citations(answer)
    citations = list(dict.fromkeys([*inline_ids, *listed_ids]))

    invalid = sorted(set(citations) - valid_source_ids)
    valid = [citation for citation in citations if citation in valid_source_ids]

    no_answer_value = parsed.get("no_answer", False)
    no_answer = (
        no_answer_value
        if isinstance(no_answer_value, bool)
        else str(no_answer_value).strip().lower() in {"true", "1", "yes"}
    )
    if answer == NO_ANSWER_MESSAGE:
        no_answer = True

    confidence = float(
        min(max(safe_float(parsed.get("confidence"), 0.0), 0.0), 1.0)
    )

    # Fail closed: unsupported or structurally invalid answers are not shown as facts.
    if invalid:
        return (
            NO_ANSWER_MESSAGE,
            [],
            True,
            0.0,
            {"parse_success": bool(parsed), "invalid_citations": invalid},
        )

    if no_answer:
        return (
            NO_ANSWER_MESSAGE,
            [],
            True,
            min(confidence, 0.5),
            {"parse_success": bool(parsed), "invalid_citations": []},
        )

    if not answer or not valid:
        return (
            NO_ANSWER_MESSAGE,
            [],
            True,
            0.0,
            {
                "parse_success": bool(parsed),
                "invalid_citations": [],
                "validation_reason": "empty_answer_or_missing_valid_citation",
            },
        )

    return (
        answer,
        valid,
        False,
        confidence,
        {"parse_success": True, "invalid_citations": []},
    )


class MockExtractiveGenerator:
    alias = "mock_extractive"
    model = "extractive-baseline-v1"

    def generate(
        self,
        question: str,
        context: str,
        valid_source_ids: set[str],
    ) -> GenerationOutput:
        started = time.perf_counter()
        blocks = re.split(r"\n(?=\[S\d+\])", context.strip())
        sentences: list[str] = []
        citations: list[str] = []

        ranked_sentences: list[tuple[float, str, str]] = []
        for block in blocks:
            source_match = re.match(r"\[(S\d+)\]", block)
            if not source_match:
                continue
            source_id = source_match.group(1)
            body = block.split("\n", 2)[-1].strip()
            for sentence in re.split(r"(?<=[.؟!])\s+|\n+", body):
                sentence = sentence.strip()
                if not sentence:
                    continue
                features = lexical_relevance_features(question, sentence)
                relevance = float(features["anchor_coverage"])
                if features["phrase_match"]:
                    relevance += 0.35
                if int(features["original_anchor_overlap_count"]) > 0:
                    relevance += 0.10
                ranked_sentences.append((relevance, sentence, source_id))

        ranked_sentences.sort(key=lambda item: item[0], reverse=True)
        for relevance, sentence, source_id in ranked_sentences:
            if relevance < 0.50:
                continue
            if source_id in citations:
                continue
            sentences.append(f"{sentence} [{source_id}]")
            citations.append(source_id)
            if len(sentences) >= 2:
                break

        if not sentences:
            return GenerationOutput(
                answer=NO_ANSWER_MESSAGE,
                citations=[],
                no_answer=True,
                confidence=0.0,
                provider_alias=self.alias,
                model=self.model,
                latency_seconds=round(time.perf_counter() - started, 4),
                raw_output="",
            )

        return GenerationOutput(
            answer=" ".join(sentences),
            citations=list(dict.fromkeys(citations)),
            no_answer=False,
            confidence=0.35,
            provider_alias=self.alias,
            model=self.model,
            latency_seconds=round(time.perf_counter() - started, 4),
            raw_output="",
            metadata={"baseline": True},
        )


class OpenAIGenerator:
    alias = "openai"

    def __init__(
        self,
        settings: Settings,
        model: str,
        api_key: str,
    ) -> None:
        from openai import OpenAI

        self.settings = settings
        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            timeout=settings.request_timeout_seconds,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def _call(self, question: str, context: str) -> Any:
        return self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_PROMPT,
            input=build_user_prompt(question, context),
            max_output_tokens=self.settings.maximum_output_tokens,
        )

    def generate(
        self,
        question: str,
        context: str,
        valid_source_ids: set[str],
    ) -> GenerationOutput:
        started = time.perf_counter()
        try:
            response = self._call(question, context)
            raw = str(getattr(response, "output_text", "") or "")
            answer, citations, no_answer, confidence, metadata = parse_and_validate(
                raw, valid_source_ids
            )
            usage = getattr(response, "usage", None)
            metadata["usage"] = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
            return GenerationOutput(
                answer=answer,
                citations=citations,
                no_answer=no_answer,
                confidence=confidence,
                provider_alias=self.alias,
                model=self.model,
                latency_seconds=round(time.perf_counter() - started, 3),
                raw_output=raw,
                metadata=metadata,
            )
        except Exception as exc:
            return GenerationOutput(
                answer=NO_ANSWER_MESSAGE,
                citations=[],
                no_answer=True,
                confidence=0.0,
                provider_alias=self.alias,
                model=self.model,
                latency_seconds=round(time.perf_counter() - started, 3),
                raw_output="",
                error=f"{type(exc).__name__}: {exc}",
            )


class GeminiGenerator:
    alias = "gemini"

    def __init__(
        self,
        settings: Settings,
        model: str,
        api_key: str,
    ) -> None:
        from google import genai

        self.settings = settings
        self.model = model
        self.client = genai.Client(api_key=api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def _call(self, question: str, context: str) -> Any:
        from google.genai import types

        return self.client.models.generate_content(
            model=self.model,
            contents=build_user_prompt(question, context),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=self.settings.generation_temperature,
                max_output_tokens=self.settings.maximum_output_tokens,
                response_mime_type="application/json",
            ),
        )

    def generate(
        self,
        question: str,
        context: str,
        valid_source_ids: set[str],
    ) -> GenerationOutput:
        started = time.perf_counter()
        try:
            response = self._call(question, context)
            raw = str(getattr(response, "text", "") or "")
            answer, citations, no_answer, confidence, metadata = parse_and_validate(
                raw, valid_source_ids
            )
            usage = getattr(response, "usage_metadata", None)
            metadata["usage"] = {
                "input_tokens": getattr(usage, "prompt_token_count", None),
                "output_tokens": getattr(usage, "candidates_token_count", None),
            }
            return GenerationOutput(
                answer=answer,
                citations=citations,
                no_answer=no_answer,
                confidence=confidence,
                provider_alias=self.alias,
                model=self.model,
                latency_seconds=round(time.perf_counter() - started, 3),
                raw_output=raw,
                metadata=metadata,
            )
        except Exception as exc:
            return GenerationOutput(
                answer=NO_ANSWER_MESSAGE,
                citations=[],
                no_answer=True,
                confidence=0.0,
                provider_alias=self.alias,
                model=self.model,
                latency_seconds=round(time.perf_counter() - started, 3),
                raw_output="",
                error=f"{type(exc).__name__}: {exc}",
            )


class GeneratorFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get(self, runtime: ResolvedProviderConfig) -> Generator:
        if runtime.provider == "openai":
            if not runtime.api_key:
                raise ValueError("OpenAI API key is missing.")
            return OpenAIGenerator(
                settings=self.settings,
                model=runtime.model,
                api_key=runtime.api_key,
            )
        if runtime.provider == "gemini":
            if not runtime.api_key:
                raise ValueError("Gemini API key is missing.")
            return GeminiGenerator(
                settings=self.settings,
                model=runtime.model,
                api_key=runtime.api_key,
            )
        if runtime.provider == "mock":
            return MockExtractiveGenerator()
        raise ValueError(f"Unsupported LLM provider: {runtime.provider}")
