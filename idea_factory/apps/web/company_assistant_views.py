"""Read-only company assistant tab — conversations and tool-gathered Q&A."""
from __future__ import annotations

import logging
import subprocess

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.agents.llm_settings import get_llm_settings_for_assistant, validate_llm_settings
from apps.core.access import get_company_for_user, is_app_admin, user_can_manage_company
from apps.ideas.company_assistant_actions import (
    approve_proposed_action,
    propose_actions_for_message,
    reject_proposed_action,
    serialize_proposed_action,
)
from apps.ideas.company_assistant_conversations import (
    build_conversation_transcript,
    conversation_has_pending_message,
    create_conversation,
    delete_conversation,
    get_active_conversation,
    get_conversation,
    list_conversations,
    maybe_set_conversation_title_from_first_message,
    touch_conversation,
)
from apps.ideas.company_assistant_runner import run_company_assistant_response
from apps.ideas.models import (
    Company,
    CompanyAssistantConversation,
    CompanyAssistantMessage,
)
from apps.core.assistant_markdown import render_assistant_markdown
from apps.web.company_workspace import build_company_workspace_context
from apps.web.subprocess_utils import get_project_root, get_subprocess_env, manage_py_argv

logger = logging.getLogger(__name__)

MAX_USER_QUESTION_CHARS = 2_000


def _assistant_url(company_pk, conversation_pk) -> str:
    return (
        reverse("company_assistant", kwargs={"company_pk": company_pk})
        + f"?conversation={conversation_pk}"
    )


def _spawn_company_assistant_process(message_pk: str) -> None:
    """Non-blocking: HTTP returns immediately; child process runs LLM + tools."""
    subprocess.Popen(
        manage_py_argv("run_company_assistant", message_pk),
        cwd=get_project_root(),
        env=get_subprocess_env(),
        start_new_session=True,
    )
    logger.info("company_assistant spawned subprocess message_id=%s", message_pk)


def _run_company_assistant_message(message: CompanyAssistantMessage) -> None:
    message.refresh_from_db()
    if message.assistant_response:
        return
    conversation = message.conversation
    history = build_conversation_transcript(
        conversation, exclude_message_id=message.pk
    )
    response_text = run_company_assistant_response(
        message.company,
        message.user,
        message.user_content,
        conversation_history=history,
    )
    message.refresh_from_db()
    message.assistant_response = response_text
    message.save(update_fields=["assistant_response"])
    proposals = propose_actions_for_message(message)
    if proposals:
        suffix = (
            "\n\n---\n\n**Suggested actions** — approve or reject below. "
            "Nothing runs until you confirm."
        )
        if suffix.strip() not in response_text:
            message.assistant_response = response_text + suffix
            message.save(update_fields=["assistant_response"])
    touch_conversation(conversation)


@login_required
@require_http_methods(["GET"])
def company_assistant(request: HttpRequest, company_pk: str) -> HttpResponse:
    company = get_company_for_user(request.user, company_pk)
    conversation_pk = request.GET.get("conversation", "").strip() or None
    conversation = get_active_conversation(
        company, request.user, conversation_pk
    )
    chat_messages = conversation.messages.prefetch_related(
        "proposed_actions"
    ).order_by("created_at")
    chat_pending = conversation_has_pending_message(conversation)
    conversations = list_conversations(company, request.user)
    assistant_llm = get_llm_settings_for_assistant(company.idea_request)
    ctx = build_company_workspace_context(company, active_tab="assistant")
    ctx.update(
        {
            "conversation": conversation,
            "conversations": conversations,
            "chat_messages": chat_messages,
            "chat_pending": chat_pending,
            "assistant_llm": assistant_llm,
            "assistant_llm_error": validate_llm_settings(assistant_llm),
            "show_llm_settings_link": is_app_admin(request.user),
            "can_manage_company": user_can_manage_company(request.user, company),
        }
    )
    return render(request, "web/company_assistant.html", ctx)


@login_required
@require_POST
def company_assistant_new(request: HttpRequest, company_pk: str) -> HttpResponse:
    company = get_company_for_user(request.user, company_pk)
    conversation = create_conversation(company, request.user)
    return redirect(_assistant_url(company.pk, conversation.pk))


@login_required
@require_POST
def company_assistant_delete(
    request: HttpRequest, company_pk: str, conversation_pk: str
) -> HttpResponse:
    company = get_company_for_user(request.user, company_pk)
    conversation = get_conversation(company, request.user, conversation_pk)
    delete_conversation(conversation)
    messages.success(request, "Conversation deleted.")
    remaining = (
        CompanyAssistantConversation.objects.filter(
            company=company, user=request.user
        )
        .order_by("-updated_at")
        .first()
    )
    if remaining:
        return redirect(_assistant_url(company.pk, remaining.pk))
    return redirect("company_assistant", company_pk=company.pk)


@login_required
@require_POST
def company_assistant_send(request: HttpRequest, company_pk: str) -> HttpResponse:
    company = get_company_for_user(request.user, company_pk)
    user_content = request.POST.get("content", "").strip()
    conversation_pk = request.POST.get("conversation_id", "").strip()

    if not user_content:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Message cannot be empty."}, status=400)
        return redirect("company_assistant", company_pk=company_pk)

    if len(user_content) > MAX_USER_QUESTION_CHARS:
        err = f"Question is too long (max {MAX_USER_QUESTION_CHARS} characters)."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": err}, status=400)
        messages.error(request, err)
        return redirect("company_assistant", company_pk=company_pk)

    if not conversation_pk:
        conversation = get_active_conversation(company, request.user, None)
    else:
        conversation = get_conversation(company, request.user, conversation_pk)

    if conversation_has_pending_message(conversation):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {"ok": False, "error": "Please wait for the assistant to finish responding."},
                status=409,
            )
        messages.error(request, "Please wait for the assistant to finish responding.")
        return redirect(_assistant_url(company.pk, conversation.pk))

    msg = CompanyAssistantMessage.objects.create(
        conversation=conversation,
        company=company,
        user=request.user,
        user_content=user_content,
        assistant_response="",
    )
    maybe_set_conversation_title_from_first_message(conversation, user_content)
    touch_conversation(conversation)
    _spawn_company_assistant_process(str(msg.pk))

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": True,
                "message_id": str(msg.pk),
                "user_content": user_content,
                "conversation_id": str(conversation.pk),
            }
        )
    return redirect(_assistant_url(company.pk, conversation.pk))


@login_required
@require_http_methods(["GET"])
def company_assistant_message_status(
    request: HttpRequest, company_pk: str, message_pk: str
) -> JsonResponse:
    company = get_company_for_user(request.user, company_pk)
    msg = get_object_or_404(
        CompanyAssistantMessage,
        pk=message_pk,
        company=company,
        user=request.user,
    )
    response_text = msg.assistant_response
    actions = [
        serialize_proposed_action(a)
        for a in msg.proposed_actions.order_by("created_at")
    ]
    return JsonResponse(
        {
            "id": str(msg.pk),
            "pending": not response_text,
            "assistant_response": response_text,
            "assistant_response_html": str(render_assistant_markdown(response_text))
            if response_text
            else "",
            "proposed_actions": actions,
            "can_manage_company": user_can_manage_company(request.user, company),
        }
    )


@login_required
@require_POST
def company_assistant_action_approve(
    request: HttpRequest, company_pk: str, action_pk: str
) -> JsonResponse:
    company = get_company_for_user(request.user, company_pk)
    from apps.ideas.models import CompanyAssistantProposedAction

    action = get_object_or_404(
        CompanyAssistantProposedAction,
        pk=action_pk,
        company=company,
        user=request.user,
    )
    try:
        approve_proposed_action(action, approved_by=request.user)
    except PermissionError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=403)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Approve assistant action failed")
        action.refresh_from_db()
        return JsonResponse(
            {
                "ok": False,
                "error": action.result_message or str(exc),
                "action": serialize_proposed_action(action),
            },
            status=500,
        )
    action.refresh_from_db()
    return JsonResponse(
        {"ok": True, "action": serialize_proposed_action(action)}
    )


@login_required
@require_POST
def company_assistant_action_reject(
    request: HttpRequest, company_pk: str, action_pk: str
) -> JsonResponse:
    company = get_company_for_user(request.user, company_pk)
    from apps.ideas.models import CompanyAssistantProposedAction

    action = get_object_or_404(
        CompanyAssistantProposedAction,
        pk=action_pk,
        company=company,
        user=request.user,
    )
    try:
        reject_proposed_action(action, rejected_by=request.user)
    except (PermissionError, ValueError) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=403)
    action.refresh_from_db()
    return JsonResponse(
        {"ok": True, "action": serialize_proposed_action(action)}
    )
