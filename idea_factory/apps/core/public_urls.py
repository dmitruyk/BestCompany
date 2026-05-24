"""Build public absolute URLs for links in emails, calendar, and assistant context."""
from __future__ import annotations

from django.conf import settings


def public_site_base() -> str:
    """https://manage.example.com when DJANGO_PUBLIC_HOST is set, else empty."""
    host = getattr(settings, "DJANGO_PUBLIC_HOST", "").strip()
    if not host:
        return ""
    return f"https://{host}"


def public_absolute_url(path: str) -> str:
    """Absolute URL for a site path, or the path unchanged when no public host is configured."""
    base = public_site_base()
    if not base:
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"
