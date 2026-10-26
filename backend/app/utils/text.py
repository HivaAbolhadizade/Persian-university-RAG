from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from typing import Any

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
LATIN_DIGITS = "0123456789"

DIGIT_TRANSLATION = str.maketrans(
    PERSIAN_DIGITS + ARABIC_DIGITS,
    LATIN_DIGITS + LATIN_DIGITS,
)

ARABIC_TO_PERSIAN = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
    }
)

# Query expansion is intentionally limited to university terminology.  The
# variants are used both by BM25 and by the runtime relevance guard.
QUERY_EXPANSION_MAP: dict[str, list[str]] = {
    "حذف و اضافه": [
        "اصلاح انتخاب واحد",
        "حذف و اخذ درس",
        "حذف اضافه",
        "تغییر انتخاب واحد",
        "بازه حذف و اضافه",
    ],
    "اصلاح انتخاب واحد": [
        "حذف و اضافه",
        "تغییر انتخاب واحد",
        "حذف و اخذ درس",
    ],
    "انتخاب واحد": ["اخذ واحد", "ثبت نام دروس", "اخذ درس"],
    "حذف درس": ["حذف واحد", "حذف آموزشی", "حذف اضطراری"],
    "کارشناسی ارشد": ["ارشد", "مقطع ارشد"],
    "مهمانی": ["میهمانی", "مهمان شدن", "دانشجوی مهمان"],
    "میهمانی": ["مهمانی", "مهمان شدن", "دانشجوی مهمان"],
    "انتقالی": ["انتقال", "جابجایی دانشگاه"],
    "انتقال": ["انتقالی", "جابجایی دانشگاه"],
    "شهریه": ["هزینه تحصیل", "هزینه آموزشی"],
    "غیبت": ["عدم حضور", "غایب بودن"],
    "امتحانات": ["آزمون", "امتحان"],
    "امتحان": ["آزمون", "امتحانات"],
    "مرخصی": ["مرخصی تحصیلی", "وقفه تحصیلی"],
    "سنوات": ["مدت مجاز تحصیل", "طول دوره"],
    "مدت مجاز تحصیل": ["سنوات مجاز", "طول دوره", "مدت تحصیل"],
    "نمره قبولی": ["حداقل نمره", "نمره لازم برای قبولی"],
    "پروپوزال": ["پیشنهاده", "پیشنهاد پژوهش", "طرح پیشنهادی"],
    "پایان نامه": ["پایان‌نامه", "رساله کارشناسی ارشد"],
    "پایان‌نامه": ["پایان نامه", "رساله کارشناسی ارشد"],
    "گواهی اشتغال به تحصیل": ["گواهی اشتغال", "اشتغال به تحصیل"],
    "بازگشت به تحصیل": ["ادامه تحصیل", "بازگشت دانشجو"],
}

# Stop words are removed only from matching/ranking features.  They are never
# removed from the text shown to the model or user.
PERSIAN_STOPWORDS: set[str] = {
    "از",
    "به",
    "با",
    "برای",
    "در",
    "بر",
    "تا",
    "را",
    "و",
    "یا",
    "که",
    "این",
    "آن",
    "یک",
    "هر",
    "هم",
    "چه",
    "چی",
    "چیست",
    "چیه",
    "چطور",
    "چگونه",
    "چقدر",
    "کدام",
    "آیا",
    "اگر",
    "می",
    "شود",
    "شده",
    "است",
    "هست",
    "باشد",
    "باشند",
    "کرد",
    "کردن",
    "کنم",
    "کنند",
    "دارد",
    "دارند",
    "میتوان",
    "می‌توان",
    "لطفا",
    "لطفاً",
    "من",
    "ما",
    "شما",
    "او",
    "خود",
}

# These words are common across university documents and should not by
# themselves make a chunk pass the relevance gate.
DOMAIN_GENERIC_TOKENS: set[str] = {
    "دانشگاه",
    "دانشجو",
    "دانشجویان",
    "تحصیل",
    "تحصیلی",
    "آموزشی",
    "مقطع",
    "دوره",
    "درس",
    "دروس",
    "شرایط",
    "شرط",
    "نحوه",
    "مراحل",
    "مورد",
    "موارد",
    "قانون",
    "قوانین",
    "آیین",
    "نامه",
    "آییننامه",
    "آیین‌نامه",
}


def normalize_persian_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = text.translate(ARABIC_TO_PERSIAN)
    text = text.translate(DIGIT_TRANSLATION)
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    text = text.replace("\u200c", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_persian_query(text: str) -> str:
    text = normalize_persian_text(text)
    text = re.sub(r"[^\wآ-ی\s؟?.,:؛\-()]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _surface_tokens(text: str) -> list[str]:
    normalized = normalize_persian_query(text).lower()
    return re.findall(r"[\wآ-ی]+", normalized, flags=re.UNICODE)


def _light_normalize_token(token: str) -> str:
    token = token.strip().lower()
    # Very conservative Persian suffix normalization.  We avoid aggressive
    # stemming because legal terms and article names must remain recognizable.
    for suffix in ("هایی", "های", "ها"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    return token


def meaningful_tokens(
    text: str,
    *,
    drop_domain_generic: bool = False,
) -> list[str]:
    tokens: list[str] = []
    for raw in _surface_tokens(text):
        token = _light_normalize_token(raw)
        if not token or token in PERSIAN_STOPWORDS:
            continue
        if drop_domain_generic and token in DOMAIN_GENERIC_TOKENS:
            continue
        if len(token) == 1 and not token.isdigit():
            continue
        tokens.append(token)
    return tokens


def bm25_tokenize(text: str) -> list[str]:
    # Keeping generic university words in the corpus/query is useful for BM25,
    # while grammatical and question words are noise.
    return meaningful_tokens(text, drop_domain_generic=True)


def replace_complete_term(text: str, source: str, replacement: str) -> str:
    pattern = re.compile(
        rf"(?<![\w\u200c]){re.escape(source)}(?![\w\u200c])",
        flags=re.UNICODE,
    )
    return pattern.sub(replacement, text)


def expand_query(query: str, maximum_variants: int = 10) -> list[str]:
    normalized = normalize_persian_query(query)
    variants = [normalized]

    # Longer terms first prevents "انتقال" from changing the inside of "انتقالی".
    for source in sorted(QUERY_EXPANSION_MAP, key=len, reverse=True):
        if not re.search(
            rf"(?<![\w\u200c]){re.escape(source)}(?![\w\u200c])",
            normalized,
        ):
            continue
        for alternative in QUERY_EXPANSION_MAP[source]:
            candidate = replace_complete_term(normalized, source, alternative)
            if candidate and candidate not in variants:
                variants.append(candidate)
            if len(variants) >= maximum_variants:
                return variants
    return variants


def query_anchor_variants(query: str) -> list[set[str]]:
    variants: list[set[str]] = []
    for variant in expand_query(query):
        anchors = set(meaningful_tokens(variant, drop_domain_generic=True))
        if not anchors:
            anchors = set(meaningful_tokens(variant, drop_domain_generic=False))
        if anchors and anchors not in variants:
            variants.append(anchors)
    return variants


def lexical_relevance_features(
    query: str,
    candidate_text: str,
    title: str = "",
) -> dict[str, Any]:
    candidate_normalized = normalize_persian_query(candidate_text).lower()
    title_normalized = normalize_persian_query(title).lower()
    candidate_tokens = set(meaningful_tokens(candidate_normalized))
    title_tokens = set(meaningful_tokens(title_normalized))
    variants = expand_query(query)
    anchor_variants = query_anchor_variants(query)

    best_coverage = 0.0
    best_title_coverage = 0.0
    best_overlap_count = 0
    best_anchor_count = 0

    for anchors in anchor_variants:
        overlap = anchors & candidate_tokens
        title_overlap = anchors & title_tokens
        coverage = len(overlap) / max(len(anchors), 1)
        title_coverage = len(title_overlap) / max(len(anchors), 1)
        if coverage > best_coverage or (
            coverage == best_coverage and len(overlap) > best_overlap_count
        ):
            best_coverage = coverage
            best_overlap_count = len(overlap)
            best_anchor_count = len(anchors)
        best_title_coverage = max(best_title_coverage, title_coverage)

    phrase_match = False
    matched_phrase: str | None = None
    for variant in variants:
        phrase = normalize_persian_query(variant).lower()
        phrase_tokens = meaningful_tokens(phrase, drop_domain_generic=True)
        if len(phrase_tokens) < 2:
            continue
        compact_phrase = " ".join(phrase_tokens)
        compact_candidate = " ".join(meaningful_tokens(candidate_normalized, drop_domain_generic=True))
        if compact_phrase and compact_phrase in compact_candidate:
            phrase_match = True
            matched_phrase = variant
            break

    original_anchors = set(
        meaningful_tokens(query, drop_domain_generic=True)
        or meaningful_tokens(query, drop_domain_generic=False)
    )
    original_overlap = original_anchors & candidate_tokens

    return {
        "anchor_coverage": round(float(best_coverage), 6),
        "title_anchor_coverage": round(float(best_title_coverage), 6),
        "anchor_overlap_count": int(best_overlap_count),
        "anchor_count": int(best_anchor_count),
        "original_anchor_overlap_count": int(len(original_overlap)),
        "phrase_match": bool(phrase_match),
        "matched_phrase": matched_phrase,
        "query_anchors": sorted(original_anchors),
    }




QUERY_SCOPE_TOKEN_GROUPS: tuple[tuple[str, ...], ...] = (
    ("کارشناسی", "ارشد"),
    ("دکتری", "تخصصی"),
    ("کارشناسی", "پیوسته"),
    ("کارشناسی", "ناپیوسته"),
    ("کاردانی",),
    ("پایان", "نامه"),
    ("رساله",),
)


def scope_phrase_features(query: str, candidate_text: str) -> dict[str, Any]:
    query_tokens = set(meaningful_tokens(query, drop_domain_generic=False))
    candidate_tokens = set(
        meaningful_tokens(candidate_text, drop_domain_generic=False)
    )
    required = [
        group for group in QUERY_SCOPE_TOKEN_GROUPS if set(group).issubset(query_tokens)
    ]
    if not required:
        return {"scope_required": False, "scope_match": True, "scope_terms": []}
    matched = [group for group in required if set(group).issubset(candidate_tokens)]
    return {
        "scope_required": True,
        "scope_match": len(matched) == len(required),
        "scope_terms": [" ".join(group) for group in required],
    }

def local_lexical_relevance_features(
    query: str,
    candidate_text: str,
    title: str = "",
    *,
    maximum_window_characters: int = 900,
) -> dict[str, Any]:
    """Measure relevance in a local sentence window instead of a whole chunk.

    Oversized OCR chunks can contain all query words on unrelated pages.  This
    function finds the strongest local sentence or adjacent-sentence window so
    widely separated terms do not create a false match.
    """
    segments = _sentence_segments(candidate_text)
    if not segments:
        return lexical_relevance_features(query, candidate_text, title)

    # Use single local clauses for relevance gating.  Combining neighbouring
    # clauses can falsely join an undergraduate rule with an unrelated master
    # heading in OCR-heavy documents.  Neighbours are still included later in
    # the context excerpt, after the best clause has been selected.
    windows: list[str] = [
        segment[:maximum_window_characters] for segment in segments
    ]

    best: dict[str, Any] | None = None
    best_key: tuple[float, int, int, int] | None = None
    for window in windows:
        features = lexical_relevance_features(query, window, title)
        scope = scope_phrase_features(query, f"{title} {window}")
        key = (
            1.0 if scope["scope_match"] else 0.0,
            float(features["anchor_coverage"])
            + (0.35 if features["phrase_match"] else 0.0),
            int(features["original_anchor_overlap_count"]),
            int(features["anchor_overlap_count"]),
            -len(window),
        )
        if best_key is None or key > best_key:
            best_key = key
            best = {**features, **scope, "local_window": window}

    return best or lexical_relevance_features(query, candidate_text, title)

def extract_article_number(query: str) -> str | None:
    normalized = normalize_persian_query(query)
    match = re.search(r"(?:ماده|بند)\s*(\d+)", normalized)
    return match.group(1) if match else None


def text_jaccard(left: str, right: str) -> float:
    left_tokens = set(bm25_tokenize(left))
    right_tokens = set(bm25_tokenize(right))
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def extract_first_json_object(text: str) -> dict[str, Any] | None:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    decoder = json.JSONDecoder()
    for index, character in enumerate(cleaned):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned[index:])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def inline_citations(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\[(S\d+)\]", str(text or ""))))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result:  # NaN
        return default
    return result


REGULATION_TITLE_TERMS: tuple[str, ...] = (
    "مجموعه مقررات آموزشی",
    "آیین نامه یکپارچه",
    "آیین‌نامه یکپارچه",
    "آیین نامه",
    "آیین‌نامه",
    "شیوه نامه",
    "شیوه‌نامه",
    "مقررات آموزشی",
)


def extract_solar_years(text: str) -> list[int]:
    """Extract plausible Solar Hijri years from Persian/Arabic/Latin digits."""
    normalized = normalize_persian_text(text)
    values: list[int] = []
    for match in re.findall(r"(?<!\d)(1[34]\d{2})(?!\d)", normalized):
        year = int(match)
        if 1300 <= year <= 1499 and year not in values:
            values.append(year)
    return values


IMPLEMENTATION_QUERY_TERMS: tuple[str, ...] = (
    "شیوه نامه",
    "شیوه‌نامه",
    "سامانه",
    "فرم",
    "مراحل",
    "فرایند",
    "فرآیند",
    "نحوه ثبت",
    "چگونه ثبت",
    "کجا ثبت",
    "درخواست را",
    "شهریه",
    "هزینه تمدید",
)


def query_prefers_implementation(query: str) -> bool:
    """Return True only when the user asks for an operational procedure.

    General legal/factoid questions should be answered from the directly
    issued regulation, not from a university implementation guide that merely
    cites the regulation and may describe extra local semesters or workflow.
    """
    normalized = normalize_persian_query(query).lower()
    return any(term in normalized for term in IMPLEMENTATION_QUERY_TERMS)


def regulation_source_profile(title: str, text: str = "") -> dict[str, Any]:
    """Classify a regulation source by authority and directness.

    A year alone is not enough.  In the real corpus, a 1402 university
    compilation contains local implementation clauses that cite the 1402
    unified regulation.  Those clauses must not outrank the directly issued
    regulation for a general legal question.
    """
    normalized_title = normalize_persian_query(title).lower()
    normalized_text = normalize_persian_query(text).lower()

    if "مقررات آموزشی ابلاغی" in normalized_title or (
        "ابلاغی" in normalized_title and "مقررات" in normalized_title
    ):
        source_type = "official_circular"
        authority = 1.0
        label = "مقررات ابلاغی مستقیم"
    elif "آیین نامه یکپارچه" in normalized_title or "آیین‌نامه یکپارچه" in title:
        source_type = "unified_regulation"
        authority = 0.96
        label = "آیین‌نامه یکپارچه مستقیم"
    elif "مجموعه مقررات آموزشی" in normalized_title:
        source_type = "regulation_compilation"
        authority = 0.70
        label = "مجموعه گردآوری‌شده مقررات"
    elif "شیوه نامه" in normalized_title or "شیوه‌نامه" in title:
        source_type = "implementation_guide"
        authority = 0.48
        label = "شیوه‌نامه اجرایی"
    elif "مقررات آموزشی" in normalized_title:
        source_type = "regulation_document"
        authority = 0.82
        label = "سند مقررات آموزشی"
    elif "آیین نامه" in normalized_title or "آیین‌نامه" in title:
        source_type = "regulation_document"
        authority = 0.80
        label = "آیین‌نامه"
    else:
        source_type = "other"
        authority = 0.40
        label = "سند دیگر"

    # Persian OCR sometimes reverses short phrases ("استناد با" instead of
    # "با استناد").  Count both orientations.
    reference_markers = len(
        re.findall(
            r"(?:به\s*استناد|با\s*استناد|استناد\s*با|بر\s*اساس|براساس|اساس\s*بر)",
            normalized_text,
        )
    )
    article_markers = len(
        re.findall(r"(?:ماده\s*\d+|\d+\s*ماده)", normalized_text)
    )

    derivative = source_type == "implementation_guide" or (
        source_type == "regulation_compilation" and reference_markers >= 1
    )
    direct_rule = source_type in {"official_circular", "unified_regulation"} or (
        source_type in {"regulation_compilation", "regulation_document"}
        and article_markers >= 1
        and reference_markers == 0
    )

    return {
        "source_type": source_type,
        "source_label": label,
        "authority": float(authority),
        "reference_markers": int(reference_markers),
        "article_markers": int(article_markers),
        "derivative": bool(derivative),
        "direct_rule": bool(direct_rule),
    }


def regulation_title_authority(title: str) -> float:
    """Authority prior derived from source type, not recency alone."""
    return float(regulation_source_profile(title)["authority"])


def _sentence_segments(text: str) -> list[str]:
    normalized = normalize_persian_text(text)
    if not normalized:
        return []
    # Legal PDFs often lose punctuation during extraction.  Splitting before
    # article markers keeps local article text together even in noisy OCR.
    normalized = re.sub(r"\s+(?=(?:ماده|تبصره|بند)\s*\d+)", "\n", normalized)
    parts = re.split(r"(?<=[.؟!؛])\s+|\n+", normalized)
    return [part.strip() for part in parts if part.strip()]


def extract_relevant_excerpt(
    text: str,
    query: str,
    *,
    maximum_characters: int = 2400,
    maximum_segments: int = 6,
) -> str:
    """Return a query-centred excerpt from a potentially oversized chunk.

    This is intentionally lexical and deterministic.  It does not call an LLM,
    so it is safe to use before generation and keeps the original source text
    unchanged in API responses.
    """
    raw = str(text or "").strip()
    if len(raw) <= maximum_characters:
        return raw

    segments = _sentence_segments(raw)
    if not segments:
        return raw[:maximum_characters].strip()

    scored: list[tuple[float, int]] = []
    query_numbers = set(re.findall(r"\d+", normalize_persian_text(query)))
    for index, segment in enumerate(segments):
        features = lexical_relevance_features(query, segment)
        score = float(features["anchor_coverage"])
        score += 0.08 * min(int(features["original_anchor_overlap_count"]), 3)
        if features["phrase_match"]:
            score += 0.45
        segment_numbers = set(re.findall(r"\d+", normalize_persian_text(segment)))
        if query_numbers and query_numbers & segment_numbers:
            score += 0.16
        # Prefer compact, locally focused legal clauses over OCR mega-lines.
        if len(segment) > 900:
            score -= min((len(segment) - 900) / 6000.0, 0.18)
        scored.append((score, index))

    best_indices = [
        index
        for score, index in sorted(scored, key=lambda item: (-item[0], item[1]))
        if score > 0
    ][: max(1, maximum_segments // 2)]
    if not best_indices:
        return raw[:maximum_characters].strip()

    selected: set[int] = set()
    for index in best_indices:
        selected.add(index)
        if index > 0:
            selected.add(index - 1)
        if index + 1 < len(segments):
            selected.add(index + 1)

    pieces: list[str] = []
    used = 0
    for index in sorted(selected):
        segment = segments[index]
        if pieces and used + len(segment) + 1 > maximum_characters:
            continue
        remaining = maximum_characters - used
        if remaining <= 0:
            break
        piece = segment[:remaining].strip()
        if piece:
            pieces.append(piece)
            used += len(piece) + 1
        if len(pieces) >= maximum_segments:
            break

    excerpt = " ".join(pieces).strip()
    return excerpt or raw[:maximum_characters].strip()
