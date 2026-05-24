"""Safe subset of Markdown for company assistant replies."""
from __future__ import annotations

import re
from html import escape

from django.conf import settings
from django.utils.safestring import SafeString, mark_safe

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

_LINK_CLASS = "text-indigo-600 hover:text-indigo-800 underline font-medium"
_UL_CLASS = "list-disc pl-5 my-2 space-y-1"
_P_CLASS = "my-2 leading-relaxed"
_LI_CLASS = "leading-relaxed"


def is_safe_assistant_link_url(url: str) -> bool:
    """Allow site-relative paths and https URLs for the configured public host."""
    url = url.strip()
    if not url:
        return False
    lower = url.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")) or url.startswith("//"):
        return False
    if url.startswith("/"):
        return "://" not in url

    public_host = getattr(settings, "DJANGO_PUBLIC_HOST", "").strip().lower()
    if url.startswith("https://") and public_host:
        prefix = f"https://{public_host}"
        return lower == prefix or lower.startswith(prefix + "/")

    if settings.DEBUG:
        if url.startswith("https://") and any(
            h in lower for h in ("localhost", "127.0.0.1")
        ):
            return True
        if url.startswith("http://") and any(
            h in lower for h in ("localhost", "127.0.0.1")
        ):
            return True
    return False


def _format_inline(text: str) -> str:
    """Escape HTML, then apply **bold** and [label](url) links."""
    parts: list[str] = []
    last = 0
    for match in _LINK_RE.finditer(text):
        parts.append(_format_bold_only(escape(text[last : match.start()])))
        label = match.group(1)
        url = match.group(2).strip()
        if is_safe_assistant_link_url(url):
            safe_url = escape(url)
            safe_label = escape(label)
            parts.append(
                f'<a href="{safe_url}" class="{_LINK_CLASS}">{safe_label}</a>'
            )
        else:
            parts.append(escape(match.group(0)))
        last = match.end()
    parts.append(_format_bold_only(escape(text[last:])))
    return "".join(parts)


def _format_bold_only(escaped_text: str) -> str:
    out: list[str] = []
    last = 0
    for match in _BOLD_RE.finditer(escaped_text):
        out.append(escaped_text[last : match.start()])
        out.append(
            f'<strong class="font-semibold text-slate-900">{match.group(1)}</strong>'
        )
        last = match.end()
    out.append(escaped_text[last:])
    return "".join(out)


def render_assistant_markdown(text: str) -> SafeString:
    """
    Render assistant markdown: paragraphs, bullet lists, **bold**, [text](url) links.
    """
    if not text:
        return mark_safe("")

    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    list_items: list[str] = []
    para_lines: list[str] = []

    def flush_paragraph() -> None:
        if not para_lines:
            return
        body = " ".join(line.strip() for line in para_lines if line.strip())
        para_lines.clear()
        if body:
            blocks.append(f'<p class="{_P_CLASS}">{_format_inline(body)}</p>')

    def flush_list() -> None:
        if not list_items:
            return
        items = "".join(
            f'<li class="{_LI_CLASS}">{_format_inline(item)}</li>' for item in list_items
        )
        list_items.clear()
        blocks.append(f'<ul class="{_UL_CLASS}">{items}</ul>')

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            flush_paragraph()
            list_items.append(stripped[2:].strip())
            continue
        if not stripped:
            flush_paragraph()
            flush_list()
            continue
        if list_items:
            flush_list()
        para_lines.append(stripped)

    flush_paragraph()
    flush_list()
    return mark_safe("".join(blocks))
