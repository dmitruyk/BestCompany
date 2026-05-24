"""Shared LLM provider and model choices for forms and admin."""

OLLAMA_MODELS = [
    ("gpt-oss:20b", "gpt-oss:20b"),
    ("qwen3", "qwen3"),
    ("mistral-small3.2", "mistral-small3.2"),
    ("qwen3-coder", "qwen3-coder"),
]

OPENAI_MODELS = [
    ("gpt-4o-mini", "gpt-4o-mini (recommended)"),
    ("gpt-4o", "gpt-4o (higher quality, higher cost)"),
]

ASSISTANT_PROVIDER_INHERIT = ("", "Same as default provider")
