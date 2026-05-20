"""Core models — user profiles, LLM service config, and access control."""
import os

from django.conf import settings
from django.db import models

class UserProfile(models.Model):
    """Extended settings for Django auth users."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="When True, user must set a new password before using the app.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profile: {self.user.username}"


class ServiceLLMConfig(models.Model):
    """
    Singleton service-wide LLM defaults (switch OpenAI ↔ Ollama without code changes).
    API keys stay in environment variables (.env); this stores provider and model IDs.
    """

    class Provider(models.TextChoices):
        OLLAMA = "ollama", "Ollama (local)"
        OPENAI = "openai", "OpenAI"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    default_provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        default=Provider.OLLAMA,
    )
    ollama_host = models.CharField(
        max_length=255,
        default="http://localhost:11434",
    )
    ollama_model_id = models.CharField(
        max_length=100,
        default="gpt-oss:20b",
        help_text="Tool-capable Ollama model",
    )
    openai_model_id = models.CharField(
        max_length=100,
        default="gpt-4o-mini",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "LLM service configuration"
        verbose_name_plural = "LLM service configuration"

    def __str__(self) -> str:
        return f"LLM: {self.get_default_provider_display()}"

    def save(self, *args, **kwargs) -> None:
        from apps.agents.llm_settings import normalize_provider

        self.id = 1
        self.default_provider = normalize_provider(self.default_provider)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "ServiceLLMConfig":
        """Load or create the singleton row (seeded from .env on first run)."""
        from apps.agents.llm_settings import normalize_provider

        defaults = {
            "default_provider": normalize_provider(os.environ.get("LLM_PROVIDER")),
            "ollama_host": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            "ollama_model_id": os.environ.get("OLLAMA_MODEL_ID", "gpt-oss:20b"),
            "openai_model_id": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        }
        obj, _ = cls.objects.get_or_create(id=1, defaults=defaults)
        return obj
