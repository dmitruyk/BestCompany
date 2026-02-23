"""LLM provider abstraction - Ollama and OpenAI via env vars."""
import os
from typing import Any

from strands.models.model import Model


def get_provider() -> str:
    """Return LLM_PROVIDER (ollama|openai), default ollama."""
    return os.environ.get("LLM_PROVIDER", "ollama").lower()


def get_model() -> Model:
    """Return Strands model instance based on LLM_PROVIDER and env vars."""
    provider = get_provider()

    if provider == "openai":
        return _get_openai_model()
    return _get_ollama_model()


def _get_ollama_model() -> Model:
    """Create Ollama model instance."""
    try:
        from strands.models.ollama import OllamaModel
    except ImportError as e:
        raise ImportError(
            "Ollama support requires: pip install 'strands-agents[ollama]'"
        ) from e

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model_id = os.environ.get("OLLAMA_MODEL_ID", "gpt-oss:20b")

    return OllamaModel(host=host, model_id=model_id)


def is_ollama_model(model: Model) -> bool:
    """Return True if model is Ollama (local); use for Ollama-specific workarounds."""
    try:
        from strands.models.ollama import OllamaModel

        return isinstance(model, OllamaModel)
    except ImportError:
        return False


def _get_openai_model() -> Model:
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

    model_id = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    return OpenAIModel(
        client_args={"api_key": api_key},
        model_id=model_id,
        params={"max_tokens": 4096, "temperature": 0.7},
    )
