from __future__ import annotations

from backend.app.config import Settings
from backend.app.services.question_suggestions import QuestionSuggestionService


def build_service(tmp_path):
    settings = Settings(_env_file=None, university_rag_root=tmp_path)
    return QuestionSuggestionService(settings)


def test_prefix_suggestions(tmp_path):
    service = build_service(tmp_path)
    results = service.suggest("حداکثر مدت مجاز تحصیل در دوره کارشناسی ارشد", limit=5)
    assert results
    assert results[0].id == 1
    assert "کارشناسی ارشد" in results[0].question


def test_topic_suggestions(tmp_path):
    service = build_service(tmp_path)
    results = service.suggest("حذف اضطراری درس", limit=5)
    assert any(item.id == 20 for item in results)


def test_typo_tolerant_suggestions(tmp_path):
    service = build_service(tmp_path)
    results = service.suggest("چند نیمسال مشروتی ارشد", limit=5)
    assert any(item.id == 3 for item in results)


def test_ground_truth_is_not_packaged(tmp_path):
    service = build_service(tmp_path)
    service.suggest("حداکثر", limit=1)
    path = service.source_path
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "ground_truth" not in text
