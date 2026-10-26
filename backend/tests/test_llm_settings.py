from pathlib import Path

from backend.app.config import Settings
from backend.app.services.llm_settings import LLMSettingsManager


def make_settings(tmp_path: Path) -> Settings:
    root = tmp_path / "University_RAG"
    (root / "data" / "backend_runtime").mkdir(parents=True)
    (root / "backend").mkdir(parents=True)
    return Settings(
        university_rag_root=root,
        llm_provider="mock",
        openai_api_key=None,
        gemini_api_key=None,
    )


def test_mock_is_available_without_key(tmp_path: Path) -> None:
    manager = LLMSettingsManager(make_settings(tmp_path))
    manager._keyring_get = lambda provider: None  # type: ignore[method-assign]
    status = manager.status("session_abcdefghijklmnopqrstuvwxyz123456")
    assert status.active_provider == "mock"
    mock = next(item for item in status.providers if item.provider == "mock")
    assert mock.configured is True


def test_api_key_is_masked_and_not_returned(tmp_path: Path) -> None:
    manager = LLMSettingsManager(make_settings(tmp_path))
    manager._keyring_get = lambda provider: None  # type: ignore[method-assign]
    manager._keyring_delete = lambda provider: None  # type: ignore[method-assign]

    status = manager.save(
        session_id="session_abcdefghijklmnopqrstuvwxyz123456",
        provider="gemini",
        model="gemini-test-model",
        api_key="AIzaExampleSecretKey1234",
        remember_on_device=False,
    )

    gemini = next(item for item in status.providers if item.provider == "gemini")
    assert gemini.configured is True
    assert gemini.key_preview is not None
    assert "AIzaExampleSecretKey1234" not in status.model_dump_json()
    assert status.key_is_returned_to_frontend is False


def test_delete_returns_to_mock(tmp_path: Path) -> None:
    manager = LLMSettingsManager(make_settings(tmp_path))
    manager._keyring_get = lambda provider: None  # type: ignore[method-assign]
    manager._keyring_delete = lambda provider: None  # type: ignore[method-assign]

    session = "session_abcdefghijklmnopqrstuvwxyz123456"
    manager.save(
        session_id=session,
        provider="openai",
        model="gpt-test-model",
        api_key="sk-example-secret-value",
        remember_on_device=False,
    )
    status = manager.delete(session, "openai")
    assert status.active_provider == "mock"
    openai = next(item for item in status.providers if item.provider == "openai")
    assert openai.configured is False
