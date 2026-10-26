from backend.app.services.generator import NO_ANSWER_MESSAGE, parse_and_validate


def test_valid_grounded_json() -> None:
    raw = (
        '{"answer":"طبق سند، این شرط برقرار است [S1].",'
        '"citations":["S1"],"no_answer":false,"confidence":0.8}'
    )
    answer, citations, no_answer, confidence, metadata = parse_and_validate(
        raw, {"S1"}
    )
    assert no_answer is False
    assert citations == ["S1"]
    assert confidence == 0.8


def test_invalid_citation_fails_closed() -> None:
    raw = (
        '{"answer":"پاسخ ساختگی [S9].","citations":["S9"],'
        '"no_answer":false,"confidence":0.9}'
    )
    answer, citations, no_answer, confidence, metadata = parse_and_validate(
        raw, {"S1"}
    )
    assert answer == NO_ANSWER_MESSAGE
    assert citations == []
    assert no_answer is True
