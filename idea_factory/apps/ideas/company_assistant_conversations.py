"""Conversation list, create/delete, and transcript for the company assistant."""
from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from apps.ideas.models import (
    Company,
    CompanyAssistantConversation,
    CompanyAssistantMessage,
)

MAX_HISTORY_TURNS = 24
MAX_HISTORY_CHARS = 14_000
TITLE_MAX_LEN = 120


def default_conversation_title() -> str:
    return f"Chat {timezone.localtime().strftime('%b %d, %H:%M')}"


def list_conversations(
    company: Company,
    user: AbstractBaseUser,
) -> list[CompanyAssistantConversation]:
    return list(
        CompanyAssistantConversation.objects.filter(company=company, user=user).order_by(
            "-updated_at"
        )[:50]
    )


def get_conversation(
    company: Company,
    user: AbstractBaseUser,
    conversation_pk,
) -> CompanyAssistantConversation:
    from django.shortcuts import get_object_or_404

    return get_object_or_404(
        CompanyAssistantConversation,
        pk=conversation_pk,
        company=company,
        user=user,
    )


def get_active_conversation(
    company: Company,
    user: AbstractBaseUser,
    conversation_pk: str | None,
) -> CompanyAssistantConversation:
    """Resolve conversation from query param or use the most recently updated."""
    if conversation_pk:
        return get_conversation(company, user, conversation_pk)
    existing = (
        CompanyAssistantConversation.objects.filter(company=company, user=user)
        .order_by("-updated_at")
        .first()
    )
    if existing:
        return existing
    return create_conversation(company, user)


@transaction.atomic
def create_conversation(
    company: Company,
    user: AbstractBaseUser,
    *,
    title: str = "",
) -> CompanyAssistantConversation:
    return CompanyAssistantConversation.objects.create(
        company=company,
        user=user,
        title=(title or default_conversation_title())[:TITLE_MAX_LEN],
    )


@transaction.atomic
def delete_conversation(conversation: CompanyAssistantConversation) -> None:
    conversation.delete()


def conversation_has_pending_message(
    conversation: CompanyAssistantConversation,
) -> bool:
    return conversation.messages.filter(assistant_response="").exists()


def maybe_set_conversation_title_from_first_message(
    conversation: CompanyAssistantConversation,
    user_content: str,
) -> None:
    """Use the first question as the conversation title when it is still the default."""
    if conversation.messages.count() != 1:
        return
    snippet = user_content.strip().replace("\n", " ")[:TITLE_MAX_LEN]
    if snippet:
        conversation.title = snippet
        conversation.save(update_fields=["title", "updated_at"])


def touch_conversation(conversation: CompanyAssistantConversation) -> None:
    CompanyAssistantConversation.objects.filter(pk=conversation.pk).update(
        updated_at=timezone.now()
    )


def build_conversation_transcript(
    conversation: CompanyAssistantConversation,
    *,
    exclude_message_id=None,
    max_turns: int = MAX_HISTORY_TURNS,
) -> str:
    """
    Prior Q&A turns in this conversation (for follow-up questions).
    Excludes the current in-flight message by id.
    """
    qs = conversation.messages.order_by("created_at")
    if exclude_message_id:
        qs = qs.exclude(pk=exclude_message_id)
    turns = list(qs)
    if not turns:
        return ""

    # Only completed turns (both sides) except we may include last user msg without reply yet — skip incomplete tail
    completed: list[CompanyAssistantMessage] = []
    for msg in turns:
        if msg.assistant_response:
            completed.append(msg)
    if not completed:
        return ""

    completed = completed[-max_turns:]
    lines = ["--- Prior conversation in this thread ---"]
    total = 0
    for msg in completed:
        block = (
            f"User: {msg.user_content.strip()}\n"
            f"Assistant: {msg.assistant_response.strip()}"
        )
        if total + len(block) > MAX_HISTORY_CHARS:
            lines.append("...[older turns omitted]")
            break
        lines.append(block)
        total += len(block)
    lines.append("--- End prior conversation ---")
    return "\n\n".join(lines)
