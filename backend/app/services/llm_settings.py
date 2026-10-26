from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from backend.app.config import Settings
from backend.app.schemas import (
    LLMConnectionTestResponse,
    LLMModelInfo,
    LLMModelsResponse,
    LLMSettingsResponse,
    ProviderStatus,
)

logger = logging.getLogger(__name__)

Provider = Literal["mock", "openai", "gemini"]
REAL_PROVIDERS = ("openai", "gemini")


@dataclass(slots=True)
class SessionLLMState:
    active_provider: Provider = "mock"
    models: dict[str, str] = field(
        default_factory=lambda: {"openai": "", "gemini": ""}
    )
    api_keys: dict[str, str | None] = field(
        default_factory=lambda: {"openai": None, "gemini": None}
    )
    remembered: dict[str, bool] = field(
        default_factory=lambda: {"openai": False, "gemini": False}
    )
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(slots=True)
class ResolvedProviderConfig:
    provider: Provider
    model: str
    api_key: str | None


class LLMSettingsManager:
    """
    Keeps API keys out of browser storage.

    - Session-only keys live in backend RAM.
    - Optional persistent keys live in the OS keyring (Windows Credential Manager).
    - Browser receives only an HttpOnly session cookie and masked status.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._sessions: dict[str, SessionLLMState] = {}
        self.settings.backend_runtime_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def new_session_id() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def valid_session_id(value: str | None) -> bool:
        if not value:
            return False
        return bool(re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value))

    def _load_metadata(self) -> dict[str, Any]:
        path = self.settings.persisted_llm_metadata_path
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {}
        except Exception as exc:
            logger.warning("Could not read persisted LLM metadata: %s", exc)
            return {}

    def _save_metadata(self, state: SessionLLMState) -> None:
        payload = {
            "active_provider": state.active_provider,
            "models": state.models,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "note": "No API key is stored in this JSON file.",
        }
        self.settings.persisted_llm_metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _keyring_get(self, provider: str) -> str | None:
        try:
            import keyring

            return keyring.get_password(
                self.settings.keyring_service_name,
                f"{provider}_api_key",
            )
        except Exception as exc:
            logger.info("Keyring read unavailable for %s: %s", provider, exc)
            return None

    def _keyring_set(self, provider: str, api_key: str) -> None:
        try:
            import keyring

            keyring.set_password(
                self.settings.keyring_service_name,
                f"{provider}_api_key",
                api_key,
            )
        except Exception as exc:
            raise RuntimeError(
                "ذخیره دائمی کلید در Windows Credential Manager انجام نشد. "
                "پکیج keyring و Credential Manager ویندوز را بررسی کنید."
            ) from exc

    def _keyring_delete(self, provider: str) -> None:
        try:
            import keyring
            from keyring.errors import PasswordDeleteError

            try:
                keyring.delete_password(
                    self.settings.keyring_service_name,
                    f"{provider}_api_key",
                )
            except PasswordDeleteError:
                pass
        except Exception as exc:
            logger.info("Keyring delete unavailable for %s: %s", provider, exc)

    def _initial_state(self) -> SessionLLMState:
        metadata = self._load_metadata()
        state = SessionLLMState()

        configured_provider = str(
            metadata.get("active_provider") or self.settings.llm_provider or "mock"
        ).lower()
        if configured_provider in {"mock", "openai", "gemini"}:
            state.active_provider = configured_provider  # type: ignore[assignment]

        models = metadata.get("models") if isinstance(metadata.get("models"), dict) else {}
        state.models["openai"] = str(
            models.get("openai") or self.settings.openai_model or ""
        )
        state.models["gemini"] = str(
            models.get("gemini") or self.settings.gemini_model or ""
        )

        env_keys = {
            "openai": self.settings.openai_api_key,
            "gemini": self.settings.gemini_api_key,
        }
        for provider in REAL_PROVIDERS:
            persisted = self._keyring_get(provider)
            state.api_keys[provider] = persisted or env_keys[provider]
            state.remembered[provider] = bool(persisted)

        if state.active_provider != "mock":
            if not state.api_keys[state.active_provider]:
                state.active_provider = "mock"

        return state

    def get_state(self, session_id: str) -> SessionLLMState:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                state = self._initial_state()
                self._sessions[session_id] = state
            return state

    @staticmethod
    def _mask_key(api_key: str | None) -> str | None:
        if not api_key:
            return None
        if len(api_key) <= 8:
            return "••••••••"
        return f"{api_key[:4]}••••••••{api_key[-4:]}"

    def status(self, session_id: str) -> LLMSettingsResponse:
        state = self.get_state(session_id)
        providers = []
        for provider in ("mock", "openai", "gemini"):
            if provider == "mock":
                configured = True
                model = "extractive-baseline-v1"
                key_preview = None
                remembered = False
            else:
                configured = bool(
                    state.api_keys[provider] and state.models[provider]
                )
                model = state.models[provider] or None
                key_preview = self._mask_key(state.api_keys[provider])
                remembered = state.remembered[provider]

            providers.append(
                ProviderStatus(
                    provider=provider,  # type: ignore[arg-type]
                    configured=configured,
                    selected=state.active_provider == provider,
                    model=model,
                    key_preview=key_preview,
                    remembered_on_device=remembered,
                )
            )

        return LLMSettingsResponse(
            active_provider=state.active_provider,
            providers=providers,
        )

    def save(
        self,
        session_id: str,
        provider: Provider,
        model: str | None,
        api_key: str | None,
        remember_on_device: bool,
    ) -> LLMSettingsResponse:
        with self._lock:
            state = self.get_state(session_id)

            if provider == "mock":
                state.active_provider = "mock"
                state.updated_at = datetime.now(timezone.utc).isoformat()
                self._save_metadata(state)
                return self.status(session_id)

            if api_key:
                state.api_keys[provider] = api_key
            if model:
                state.models[provider] = model

            if not state.api_keys[provider]:
                raise ValueError("API Key وارد نشده است.")
            if not state.models[provider]:
                raise ValueError("مدل انتخاب نشده است.")

            state.active_provider = provider
            state.remembered[provider] = bool(remember_on_device)
            state.updated_at = datetime.now(timezone.utc).isoformat()

            if remember_on_device:
                self._keyring_set(provider, str(state.api_keys[provider]))
            else:
                self._keyring_delete(provider)

            self._save_metadata(state)
            return self.status(session_id)

    def delete(self, session_id: str, provider: str | None = None) -> LLMSettingsResponse:
        with self._lock:
            state = self.get_state(session_id)
            targets = REAL_PROVIDERS if provider is None else (provider,)

            for target in targets:
                if target not in REAL_PROVIDERS:
                    raise ValueError(f"Unsupported provider: {target}")
                state.api_keys[target] = None
                state.remembered[target] = False
                self._keyring_delete(target)

            if state.active_provider in targets:
                state.active_provider = "mock"
            state.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_metadata(state)
            return self.status(session_id)

    def _resolve_api_key(
        self,
        session_id: str,
        provider: str,
        supplied_api_key: str | None,
    ) -> str:
        if supplied_api_key:
            return supplied_api_key
        state = self.get_state(session_id)
        stored = state.api_keys.get(provider)
        if not stored:
            raise ValueError("برای این Provider هنوز API Key ثبت نشده است.")
        return stored

    @staticmethod
    def _openai_model_allowed(model_id: str) -> bool:
        lowered = model_id.lower()
        blocked = (
            "audio",
            "realtime",
            "transcribe",
            "tts",
            "image",
            "embedding",
            "moderation",
            "search",
            "whisper",
            "dall-e",
        )
        return (
            model_id.startswith("gpt-") or re.match(r"^o\d", model_id) is not None
        ) and not any(token in lowered for token in blocked)

    def list_models(
        self,
        session_id: str,
        provider: Literal["openai", "gemini"],
        api_key: str | None = None,
    ) -> LLMModelsResponse:
        key = self._resolve_api_key(session_id, provider, api_key)
        models: list[LLMModelInfo] = []

        if provider == "openai":
            from openai import OpenAI

            client = OpenAI(api_key=key, timeout=self.settings.request_timeout_seconds)
            response = client.models.list()
            ids = sorted(
                {
                    str(item.id)
                    for item in response.data
                    if self._openai_model_allowed(str(item.id))
                }
            )
            models = [
                LLMModelInfo(id=model_id, display_name=model_id, provider="openai")
                for model_id in ids
            ]
        else:
            from google import genai

            client = genai.Client(api_key=key)
            discovered: list[LLMModelInfo] = []
            for item in client.models.list():
                raw_name = str(getattr(item, "name", "") or "")
                if not raw_name:
                    continue
                model_id = raw_name.removeprefix("models/")
                actions = getattr(item, "supported_actions", None) or []
                action_text = " ".join(map(str, actions)).lower()
                if actions and not (
                    "generatecontent" in action_text
                    or "generate_content" in action_text
                ):
                    continue
                lowered = model_id.lower()
                if "gemini" not in lowered or any(
                    token in lowered
                    for token in ("embedding", "image", "tts", "audio", "live")
                ):
                    continue
                display_name = str(
                    getattr(item, "display_name", "") or model_id
                )
                discovered.append(
                    LLMModelInfo(
                        id=model_id,
                        display_name=display_name,
                        provider="gemini",
                    )
                )
            models = sorted(discovered, key=lambda item: item.id)

        return LLMModelsResponse(provider=provider, models=models)

    def test_connection(
        self,
        session_id: str,
        provider: Literal["openai", "gemini"],
        model: str,
        api_key: str | None = None,
    ) -> LLMConnectionTestResponse:
        key = self._resolve_api_key(session_id, provider, api_key)
        started = time.perf_counter()

        if provider == "openai":
            from openai import OpenAI

            client = OpenAI(api_key=key, timeout=self.settings.request_timeout_seconds)
            response = client.responses.create(
                model=model,
                input="Reply with exactly OK.",
                max_output_tokens=16,
            )
            text = str(getattr(response, "output_text", "") or "").strip()
        else:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=model,
                contents="Reply with exactly OK.",
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=16,
                ),
            )
            text = str(getattr(response, "text", "") or "").strip()

        latency = round(time.perf_counter() - started, 3)
        return LLMConnectionTestResponse(
            ok=bool(text),
            provider=provider,
            model=model,
            latency_seconds=latency,
            message="اتصال با موفقیت آزمایش شد." if text else "پاسخ خالی دریافت شد.",
        )

    def resolve_for_query(
        self,
        session_id: str,
        provider_override: str | None = None,
        model_override: str | None = None,
    ) -> ResolvedProviderConfig:
        state = self.get_state(session_id)
        provider = str(provider_override or state.active_provider or "mock").lower()
        if provider not in {"mock", "openai", "gemini"}:
            raise ValueError(f"Unsupported provider: {provider}")

        if provider == "mock":
            return ResolvedProviderConfig(
                provider="mock",
                model="extractive-baseline-v1",
                api_key=None,
            )

        model = str(model_override or state.models.get(provider) or "").strip()
        api_key = state.api_keys.get(provider)
        if not api_key:
            raise ValueError(
                f"API Key برای {provider} تنظیم نشده است. از صفحه تنظیمات وارد کنید."
            )
        if not model:
            raise ValueError(
                f"مدل برای {provider} انتخاب نشده است. از صفحه تنظیمات انتخاب کنید."
            )

        return ResolvedProviderConfig(
            provider=provider,  # type: ignore[arg-type]
            model=model,
            api_key=api_key,
        )
