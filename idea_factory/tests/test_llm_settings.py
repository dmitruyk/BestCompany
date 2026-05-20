"""Tests for service LLM configuration."""
import pytest

from apps.agents.llm_settings import (
    LLMSettings,
    get_llm_settings_for_idea,
    get_service_llm_settings,
    normalize_provider,
    validate_llm_settings,
)
from apps.core.models import ServiceLLMConfig
from apps.ideas.models import IdeaRequest


def test_normalize_provider_aliases() -> None:
    assert normalize_provider("llama") == "ollama"
    assert normalize_provider("OLLAMA") == "ollama"
    assert normalize_provider("openai") == "openai"


@pytest.mark.django_db
def test_service_llm_config_singleton() -> None:
    cfg = ServiceLLMConfig.load()
    assert cfg.id == 1
    cfg.default_provider = "openai"
    cfg.openai_model_id = "gpt-4o-mini"
    cfg.save()
    again = ServiceLLMConfig.load()
    assert again.default_provider == "openai"


@pytest.mark.django_db
def test_get_service_llm_settings_from_db(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = ServiceLLMConfig.load()
    cfg.default_provider = "openai"
    cfg.openai_model_id = "gpt-4o"
    cfg.save()
    settings = get_service_llm_settings()
    assert settings.provider == "openai"
    assert settings.openai_model_id == "gpt-4o"


@pytest.mark.django_db
def test_idea_overrides_provider(user) -> None:
    ServiceLLMConfig.load()
    idea = IdeaRequest.objects.create(
        title="T",
        prompt="P",
        provider="ollama",
        model_id="qwen3",
        owner=user,
    )
    settings = get_llm_settings_for_idea(idea)
    assert settings.provider == "ollama"
    assert settings.ollama_model_id == "qwen3"


@pytest.mark.django_db
def test_validate_openai_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    err = validate_llm_settings(
        LLMSettings("openai", "http://localhost:11434", "m", "gpt-4o-mini")
    )
    assert err is not None
    assert "OPENAI_API_KEY" in err


@pytest.mark.django_db
def test_subprocess_env_includes_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.core.subprocess_env import enrich_subprocess_env

    cfg = ServiceLLMConfig.load()
    cfg.default_provider = "ollama"
    cfg.ollama_model_id = "qwen3"
    cfg.save()
    env = enrich_subprocess_env({})
    assert env["LLM_PROVIDER"] == "ollama"
    assert env["OLLAMA_MODEL_ID"] == "qwen3"
