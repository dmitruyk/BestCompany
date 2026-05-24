"""LLM provider abstraction - Ollama and OpenAI."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from strands.models.model import Model

from .llm_settings import (
    LLMSettings,
    PROVIDER_OPENAI,
    get_llm_settings_for_assistant,
    get_llm_settings_for_idea,
    get_service_llm_settings,
    llm_env,
    normalize_provider,
    validate_llm_settings,
)


def get_provider() -> str:
    """Return active service provider (ollama|openai)."""
    return get_service_llm_settings().provider


def get_model(settings: LLMSettings | None = None) -> Model:
    """Return Strands model for given or service-wide settings."""
    cfg = settings or get_service_llm_settings()
    err = validate_llm_settings(cfg)
    if err:
        raise ValueError(err)
    if cfg.provider == PROVIDER_OPENAI:
        return _get_openai_model(cfg.openai_model_id)
    return _get_ollama_model(cfg.ollama_host, cfg.ollama_model_id)


def get_model_for_idea(idea_request) -> Model:
    """Return model configured for a specific idea request."""
    cfg = get_llm_settings_for_idea(idea_request)
    with llm_env(cfg):
        return get_model(cfg)


def get_model_for_assistant(idea_request=None) -> Model:
    """Return model for company Assistant (service assistant_* config in admin)."""
    cfg = get_llm_settings_for_assistant(idea_request)
    with llm_env(cfg):
        return get_model(cfg)


@contextmanager
def idea_llm_context(idea_request) -> Iterator[LLMSettings]:
    """Context manager applying per-idea LLM env for a block of agent calls."""
    cfg = get_llm_settings_for_idea(idea_request)
    with llm_env(cfg):
        yield cfg


def validate_provider_config(provider: str | None = None) -> Optional[str]:
    """Validate provider; uses service settings if provider is None."""
    if provider is None:
        cfg = get_service_llm_settings()
    else:
        base = get_service_llm_settings()
        cfg = LLMSettings(
            provider=normalize_provider(provider),
            ollama_host=base.ollama_host,
            ollama_model_id=base.ollama_model_id,
            openai_model_id=base.openai_model_id,
        )
    return validate_llm_settings(cfg)


def _get_ollama_model(host: str, model_id: str) -> Model:
    """Create Ollama model instance."""
    try:
        from strands.models.ollama import OllamaModel
    except ImportError as e:
        raise ImportError(
            "Ollama support requires: pip install 'strands-agents[ollama]'"
        ) from e
    return OllamaModel(host=host, model_id=model_id)


def is_ollama_model(model: Model) -> bool:
    """Return True if model is Ollama (local)."""
    try:
        from strands.models.ollama import OllamaModel

        return isinstance(model, OllamaModel)
    except ImportError:
        return False


def _get_openai_model(model_id: str) -> Model:
    """Create OpenAI model instance."""
    try:
        from strands.models.openai import OpenAIModel
    except ImportError as e:
        raise ImportError(
            "OpenAI support requires: pip install 'strands-agents[openai]'"
        ) from e

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY must be set when LLM_PROVIDER=openai. "
            "Set it in .env or export OPENAI_API_KEY=sk-..."
        )

    return OpenAIModel(
        client_args={
            "api_key": api_key,
            # Fail fast on 429 — default SDK retries hammer the same RPM window.
            "max_retries": 0,
        },
        model_id=model_id,
        params={"max_tokens": 4096, "temperature": 0.7},
    )
