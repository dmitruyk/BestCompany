"""Build prompt/context strings for ideas, including PDF attachments."""
from __future__ import annotations

from apps.ideas.models import IdeaRequest

MAX_ATTACHMENT_CHARS_IN_PROMPT = 40_000


def build_attachment_context_section(
    idea_request: IdeaRequest,
    *,
    max_chars: int = MAX_ATTACHMENT_CHARS_IN_PROMPT,
) -> str:
    """Format extracted PDF text as a context section, or empty string."""
    attachments = list(
        idea_request.attachments.order_by("created_at").only(
            "original_filename", "extracted_text"
        )
    )
    if not attachments:
        return ""

    parts = ["--- Attached documents (PDF) ---"]
    remaining = max_chars
    for att in attachments:
        if not att.extracted_text.strip():
            continue
        header = f"\n### {att.original_filename}\n"
        text = att.extracted_text
        if len(text) > remaining:
            text = text[:remaining] + "\n...[truncated]"
            remaining = 0
        else:
            remaining -= len(text)
        parts.append(header + text)
        if remaining <= 0:
            break
    if len(parts) == 1:
        return ""
    return "\n".join(parts)


def build_idea_request_prompt(idea_request: IdeaRequest) -> str:
    """Full user request text for agent pipeline (title, prompt, PDF context)."""
    parts = [idea_request.title, "", idea_request.prompt]
    attachment_section = build_attachment_context_section(idea_request)
    if attachment_section:
        parts.extend(["", attachment_section])
    return "\n".join(parts)


def build_idea_context_text(idea_request: IdeaRequest) -> str:
    """Context for fleet generation (idea + conclusion + PDF attachments)."""
    import json

    parts = [
        f"Title: {idea_request.title}",
        f"Prompt: {idea_request.prompt}",
    ]
    attachment_section = build_attachment_context_section(idea_request)
    if attachment_section:
        parts.append(attachment_section)

    conclusion = idea_request.conclusion if hasattr(idea_request, "conclusion") else None
    if conclusion:
        parts.append(f"Summary: {conclusion.final_summary}")
        try:
            data = json.loads(conclusion.result_json)
            parts.append(f"Full analysis: {json.dumps(data, indent=2)[:3000]}")
        except json.JSONDecodeError:
            pass
    return "\n\n".join(parts)
