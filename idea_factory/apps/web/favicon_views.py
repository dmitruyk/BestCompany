"""Serve favicons from app static files (no collectstatic / WhiteNoise required)."""
from __future__ import annotations

from pathlib import Path

from django.http import FileResponse, Http404, HttpRequest, HttpResponse

_STATIC_DIR = Path(__file__).resolve().parent / "static"

_FAVICON_FILES = {
    "favicon.ico": ("image/x-icon", "favicon.ico"),
    "favicon.svg": ("image/svg+xml", "favicon.svg"),
    "apple-touch-icon.png": ("image/png", "apple-touch-icon.png"),
}


def _serve_favicon(request: HttpRequest, name: str) -> HttpResponse:
    meta = _FAVICON_FILES.get(name)
    if not meta:
        raise Http404
    content_type, filename = meta
    path = _STATIC_DIR / filename
    if not path.is_file():
        raise Http404(f"Favicon file missing: {path}")
    response = FileResponse(path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "public, max-age=86400"
    return response


def favicon_ico(request: HttpRequest) -> HttpResponse:
    return _serve_favicon(request, "favicon.ico")


def favicon_svg(request: HttpRequest) -> HttpResponse:
    return _serve_favicon(request, "favicon.svg")


def apple_touch_icon(request: HttpRequest) -> HttpResponse:
    return _serve_favicon(request, "apple-touch-icon.png")
