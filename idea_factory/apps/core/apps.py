"""App config for core."""
import logging

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuration for the core app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self) -> None:
        """Capture Python warnings into logging (e.g. ResourceWarning, structured output validation)."""
        logging.captureWarnings(capture=True)
        import apps.core.signals  # noqa: F401
        from django.contrib import admin
        from django.contrib.auth.models import User

        from apps.core.admin import CustomUserAdmin

        admin.site.unregister(User)
        admin.site.register(User, CustomUserAdmin)
