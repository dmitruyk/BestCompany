"""Resolve LLM provider settings from service config, env, and per-idea overrides."""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, MutableMapping, Optional

PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI = "openai"
VALID_PROVIDERS = frozenset({PROVIDER_OLLAMA, PROVIDER_OPENAI})

_PROVIDER_ALIASES = {
    "llama": PROVIDER_OLLAMA,
    "ollama": PROVIDER_OLLAMA,
    "openai": PROVIDER_OPENAI,
}


def normalize_provider(value: str | None) -> str:
    """Map provider string to ollama or openai."""
    if not value:
        return PROVIDER_OLLAMA
    key = value.strip().lower()
    return _PROVIDER_ALIASES.get(key, key)


@dataclass(frozen=True)
class LLMSettings:
    """Resolved LLM configuration for one run."""

    provider: str
    ollama_host: str
    ollama_model_id: str
    openai_model_id: str

    def model_id_for_provider(self, provider: str | None = None) -> str:
        p = normalize_provider(provider or self.provider)
        if p == PROVIDER_OPENAI:
            return self.openai_model_id
        return self.ollama_model_id

    def as_env(self) -> dict[str, str]:
        """Environment variables for subprocess workers."""
        env = {
            "LLM_PROVIDER": self.provider,
            "OLLAMA_HOST": self.ollama_host,
            "OLLAMA_MODEL_ID": self.ollama_model_id,
            "OPENAI_MODEL": self.openai_model_id,
        }
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            env["OPENAI_API_KEY"] = api_key
        return env


def _env_defaults() -> LLMSettings:
    return LLMSettings(
        provider=normalize_provider(os.environ.get("LLM_PROVIDER")),
        ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model_id=os.environ.get("OLLAMA_MODEL_ID", "gpt-oss:20b"),
        openai_model_id=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
    )


def get_service_llm_settings() -> LLMSettings:
    """Service-wide default from database (bootstrapped from .env on first use)."""
    from apps.core.models import ServiceLLMConfig

    cfg = ServiceLLMConfig.load()
    return LLMSettings(
        provider=normalize_provider(cfg.default_provider),
        ollama_host=cfg.ollama_host,
        ollama_model_id=cfg.ollama_model_id,
        openai_model_id=cfg.openai_model_id,
    )


def get_llm_settings_for_idea(idea_request) -> LLMSettings:
    """Per-idea settings: idea fields override service defaults."""
    base = get_service_llm_settings()
    provider = normalize_provider(idea_request.provider or base.provider)
    if idea_request.model_id:
        if provider == PROVIDER_OPENAI:
            return LLMSettings(
                provider=provider,
                ollama_host=base.ollama_host,
                ollama_model_id=base.ollama_model_id,
                openai_model_id=idea_request.model_id,
            )
        return LLMSettings(
            provider=provider,
            ollama_host=base.ollama_host,
            ollama_model_id=idea_request.model_id,
            openai_model_id=base.openai_model_id,
        )
    return LLMSettings(
        provider=provider,
        ollama_host=base.ollama_host,
        ollama_model_id=base.ollama_model_id,
        openai_model_id=base.openai_model_id,
    )


def get_llm_settings_for_assistant(idea_request=None) -> LLMSettings:
    """
    LLM settings for the company Assistant tab (staff-configured in LLM settings / admin).

    Uses ServiceLLMConfig assistant_* fields when set; does not use per-idea overrides.
    idea_request is accepted for API compatibility but ignored.
    """
    del idea_request
    base = get_service_llm_settings()
    from apps.core.models import ServiceLLMConfig

    cfg = ServiceLLMConfig.load()
    provider = normalize_provider(cfg.assistant_provider or cfg.default_provider)
    if provider == PROVIDER_OPENAI:
        openai_model = cfg.assistant_openai_model_id or cfg.openai_model_id
        return LLMSettings(
            provider=provider,
            ollama_host=base.ollama_host,
            ollama_model_id=base.ollama_model_id,
            openai_model_id=openai_model,
        )
    ollama_model = cfg.assistant_ollama_model_id or cfg.ollama_model_id
    return LLMSettings(
        provider=provider,
        ollama_host=base.ollama_host,
        ollama_model_id=ollama_model,
        openai_model_id=base.openai_model_id,
    )


def validate_llm_settings(settings: LLMSettings) -> Optional[str]:
    """Return error message if provider cannot run, else None."""
    if settings.provider not in VALID_PROVIDERS:
        return f"Unknown LLM provider: {settings.provider}"
    if settings.provider == PROVIDER_OPENAI:
        if not os.environ.get("OPENAI_API_KEY"):
            return (
                "OPENAI_API_KEY is not set. Add it to .env or switch provider to Ollama."
            )
        return None
    if not settings.ollama_host:
        return "OLLAMA_HOST is not configured."
    if not settings.ollama_model_id:
        return "OLLAMA_MODEL_ID is not configured."
    return None


@contextmanager
def llm_env(settings: LLMSettings) -> Iterator[None]:
    """Temporarily apply LLM settings to os.environ."""
    keys = (
        "LLM_PROVIDER",
        "OLLAMA_HOST",
        "OLLAMA_MODEL_ID",
        "OPENAI_MODEL",
    )
    previous = {k: os.environ.get(k) for k in keys}
    try:
        for key, value in settings.as_env().items():
            if key in keys or key == "OPENAI_API_KEY":
                os.environ[key] = value
        yield
    finally:
        for key in keys:
            old = previous.get(key)
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def apply_llm_env_to_mapping(
    settings: LLMSettings, env: MutableMapping[str, str]
) -> dict[str, str]:
    """Merge LLM settings into an env dict for subprocesses."""
    result = dict(env)
    result.update(settings.as_env())
    return result
