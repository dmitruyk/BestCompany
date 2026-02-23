"""App config for web."""
from django.apps import AppConfig


class WebConfig(AppConfig):
    """Configuration for the web app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.web"
    verbose_name = "Web"
