"""App config for ideas."""
from django.apps import AppConfig


class IdeasConfig(AppConfig):
    """Configuration for the ideas app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ideas"
    verbose_name = "Ideas"
