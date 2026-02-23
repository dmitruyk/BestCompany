"""Tests for LLM provider selection."""
import os

import pytest


@pytest.fixture(autouse=True)
def clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear provider-related env before each test."""
    for key in ("LLM_PROVIDER", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_get_provider_default() -> None:
    """Provider defaults to ollama when not set."""
    from apps.agents.providers import get_provider
    assert get_provider() == "ollama"


def test_get_provider_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider can be set via LLM_PROVIDER."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    from apps.agents.providers import get_provider
    assert get_provider() == "openai"


def test_get_ollama_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama model is created with env defaults."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    from apps.agents.providers import get_model, is_ollama_model
    model = get_model()
    assert model is not None
    assert is_ollama_model(model) is True


def test_is_ollama_model_openai_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_ollama_model returns False for OpenAI model."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    from apps.agents.providers import get_model, is_ollama_model
    model = get_model()
    assert is_ollama_model(model) is False


def test_get_openai_model_raises_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI model raises when OPENAI_API_KEY is missing."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from apps.agents.providers import get_model
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        get_model()
