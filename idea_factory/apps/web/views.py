"""Views for idea_factory web UI."""
import json
import logging
import os
import subprocess
import sys
from typing import Optional
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from django.utils.dateparse import parse_date

from apps.core.access import (
    companies_queryset_for_user,
    get_company_for_user,
    get_idea_for_user,
    ideas_queryset_for_user,
    user_can_create_companies,
    user_can_create_ideas,
)
from apps.ideas.attachments import save_idea_attachments
from apps.ideas.context import build_idea_request_prompt
from apps.ideas.autonomous_loop import count_unscheduled_selected, process_company
from apps.web.company_workspace import build_company_workspace_context
from apps.ideas.models import (
    ActionProposal,
    AgentRun,
    Company,
    CompanyAgent,
    CompanyCalendarAction,
    CompanyTask,
    CompanyTeamMember,
    IdeaConclusion,
    IdeaRequest,
)

logger = logging.getLogger(__name__)


# Ollama models that support tools (required for structured output).
# See https://ollama.com/search?c=tools - llama3, llama3:70b do NOT support tools.
OLLAMA_MODELS = [
    ("gpt-oss:20b", "gpt-oss:20b"),
    ("qwen3", "qwen3"),
    ("mistral-small3.2", "mistral-small3.2"),
    ("qwen3-coder", "qwen3-coder"),
]

# OpenAI models — gpt-4o-mini is the default (best cost vs quality for structured agents).
OPENAI_MODELS = [
    ("gpt-4o-mini", "gpt-4o-mini (recommended)"),
    ("gpt-4o", "gpt-4o (higher quality, higher cost)"),
]


def _provider_error() -> Optional[str]:
    """Return error message if active service LLM provider is misconfigured."""
    from apps.agents.providers import validate_provider_config

    return validate_provider_config()


def _new_idea_form_context(request: HttpRequest, **extra) -> dict:
    """Shared template context for the new-idea form."""
    from apps.agents.llm_settings import get_service_llm_settings

    svc = get_service_llm_settings()
    return {
        "provider_error": _provider_error(),
        "service_llm": svc,
        "providers": IdeaRequest.Provider.choices,
        "ollama_models": OLLAMA_MODELS,
        "openai_models": OPENAI_MODELS,
        "default_provider": svc.provider,
        **extra,
    }


@login_required
@require_http_methods(["GET"])
def home(request: HttpRequest) -> HttpResponse:
    """List all idea requests."""
    from apps.agents.llm_settings import get_service_llm_settings

    requests = ideas_queryset_for_user(request.user)[:50]
    return render(
        request,
        "web/home.html",
        {
            "idea_requests": requests,
            "provider_error": _provider_error(),
            "service_llm": get_service_llm_settings(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def new_idea(request: HttpRequest) -> HttpResponse:
    """Create new idea request form and handle run now."""
    if not user_can_create_ideas(request.user):
        messages.error(request, "You do not have permission to create idea requests.")
        return redirect("home")
    if request.method == "POST":
        title = request.POST.get("title", "").strip() or "Untitled"
        prompt = request.POST.get("prompt", "").strip()
        from apps.agents.llm_settings import get_service_llm_settings

        provider = request.POST.get("provider", get_service_llm_settings().provider)
        model_id = request.POST.get("model_id", "").strip()
        if not prompt:
            return render(
                request,
                "web/new_idea.html",
                _new_idea_form_context(request, error="Prompt is required."),
            )
        provider_error = _provider_error()
        if provider_error:
            return render(
                request,
                "web/new_idea.html",
                _new_idea_form_context(
                    request, error=f"Provider error: {provider_error}"
                ),
            )
        idea = IdeaRequest.objects.create(
            title=title,
            prompt=prompt,
            status=IdeaRequest.Status.PENDING,
            provider=provider,
            model_id=model_id,
            owner=request.user,
        )
        uploads = request.FILES.getlist("pdf_documents")
        attachment_errors = save_idea_attachments(idea, uploads) if uploads else []
        idea_pk = str(idea.pk)
        _spawn_pipeline_process(idea_pk)
        if attachment_errors:
            request.session[f"idea_{idea_pk}_attachment_warnings"] = attachment_errors
        return redirect("idea_detail", pk=idea_pk)
    return render(request, "web/new_idea.html", _new_idea_form_context(request))


def _build_result_bundle(idea: IdeaRequest) -> dict:
    """Build JSON result bundle from idea and runs."""
    agent_outputs = {}
    for r in idea.agent_runs.all():
        if r.output_json:
            try:
                agent_outputs[r.agent_name] = json.loads(r.output_json)
            except json.JSONDecodeError:
                agent_outputs[r.agent_name] = {"raw": r.output_json}
    conclusion = getattr(idea, "conclusion", None)
    final_summary = conclusion.final_summary if conclusion else ""
    if not final_summary and idea.status == IdeaRequest.Status.SUCCEEDED:
        ov = idea.agent_runs.filter(role="overviewer").first()
        if ov and ov.output_json:
            try:
                data = json.loads(ov.output_json)
                final_summary = data.get("executive_summary", "")
            except json.JSONDecodeError:
                pass
    agents_involved = list(idea.agent_runs.values_list("agent_name", flat=True))
    return {
        "final_summary": final_summary,
        "agents_involved": agents_involved,
        "agent_outputs": agent_outputs,
        "request": {"title": idea.title, "prompt": idea.prompt},
    }


@login_required
@require_http_methods(["GET"])
def idea_detail(request: HttpRequest, pk: str) -> HttpResponse:
    """Detail page for idea request with agent runs."""
    idea = get_idea_for_user(request.user, pk)
    runs = idea.agent_runs.all()
    conclusion = getattr(idea, "conclusion", None)
    result_bundle = _build_result_bundle(idea)
    result_json_str = json.dumps(result_bundle)
    has_failed_runs = idea.agent_runs.filter(status=AgentRun.RunStatus.FAILED).exists()
    session_key = f"idea_{pk}_attachment_warnings"
    attachment_warnings = request.session.pop(session_key, [])
    return render(
        request,
        "web/idea_detail.html",
        {
            "idea": idea,
            "attachments": idea.attachments.all(),
            "attachment_warnings": attachment_warnings,
            "runs": runs,
            "conclusion": conclusion,
            "result_bundle": result_bundle,
            "result_json_str": result_json_str,
            "has_failed_runs": has_failed_runs,
            "can_add_attachments": idea.status != IdeaRequest.Status.RUNNING,
        },
    )


@login_required
@require_POST
def add_idea_attachment(request: HttpRequest, pk: str) -> HttpResponse:
    """Upload additional PDF context documents to an existing idea."""
    idea = get_idea_for_user(request.user, pk)
    if idea.status == IdeaRequest.Status.RUNNING:
        return redirect("idea_detail", pk=pk)
    uploads = request.FILES.getlist("pdf_documents")
    if uploads:
        errors = save_idea_attachments(idea, uploads)
        if errors:
            request.session[f"idea_{pk}_attachment_warnings"] = errors
    return redirect("idea_detail", pk=pk)


def _get_project_root() -> str:
    """Return absolute path to project root (idea_factory/)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_subprocess_env() -> dict:
    """Build env for subprocess - same database and PYTHONPATH as Django server."""
    from apps.core.subprocess_env import enrich_subprocess_env

    root = _get_project_root()
    env = enrich_subprocess_env()
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _spawn_pipeline_process(idea_pk: str) -> None:
    """Spawn pipeline via manage.py in a separate Python process."""
    root = _get_project_root()
    subprocess.Popen(
        [sys.executable, os.path.join(root, "manage.py"), "run_pipeline", idea_pk],
        cwd=root,
        env=_get_subprocess_env(),
        start_new_session=True,
    )


def _spawn_rerun_process(idea_pk: str) -> None:
    """Spawn rerun via manage.py in a separate Python process."""
    root = _get_project_root()
    subprocess.Popen(
        [sys.executable, os.path.join(root, "manage.py"), "run_pipeline", idea_pk, "--rerun"],
        cwd=root,
        env=_get_subprocess_env(),
        start_new_session=True,
    )


def _spawn_rerun_from_scratch_process(idea_pk: str) -> None:
    """Spawn full pipeline rerun from scratch (delete all runs, start over)."""
    root = _get_project_root()
    subprocess.Popen(
        [sys.executable, os.path.join(root, "manage.py"), "run_pipeline", idea_pk, "--from-scratch"],
        cwd=root,
        env=_get_subprocess_env(),
        start_new_session=True,
    )


def _spawn_fleet_process(idea_pk: str) -> None:
    """Spawn fleet generation via manage.py in a separate Python process."""
    root = _get_project_root()
    subprocess.Popen(
        [sys.executable, os.path.join(root, "manage.py"), "run_fleet", idea_pk],
        cwd=root,
        env=_get_subprocess_env(),
        start_new_session=True,
    )


def _spawn_regenerate_agents_process(company_pk: str) -> None:
    """Spawn agent regeneration via manage.py in a separate Python process."""
    root = _get_project_root()
    subprocess.Popen(
        [sys.executable, os.path.join(root, "manage.py"), "run_regenerate_agents", company_pk],
        cwd=root,
        env=_get_subprocess_env(),
        start_new_session=True,
    )


@login_required
@require_POST
def stop_pipeline(request: HttpRequest, pk: str) -> HttpResponse:
    """Stop a running pipeline. Sets status to CANCELLED so the pipeline process exits at next check."""
    idea = get_idea_for_user(request.user, pk)
    if idea.status == IdeaRequest.Status.RUNNING:
        idea.status = IdeaRequest.Status.CANCELLED
        idea.save(update_fields=["status", "updated_at"])
    return redirect("idea_detail", pk=pk)


@login_required
@require_POST
def rerun_failed_steps(request: HttpRequest, pk: str) -> HttpResponse:
    """Rerun failed pipeline steps for idea request (async)."""
    idea = get_idea_for_user(request.user, pk)
    _spawn_rerun_process(str(idea.pk))
    return redirect("idea_detail", pk=pk)


@login_required
@require_POST
def rerun_from_scratch(request: HttpRequest, pk: str) -> HttpResponse:
    """Delete all runs and rerun pipeline from scratch (async)."""
    idea = get_idea_for_user(request.user, pk)
    if idea.status == IdeaRequest.Status.RUNNING:
        return redirect("idea_detail", pk=pk)
    _spawn_rerun_from_scratch_process(str(idea.pk))
    return redirect("idea_detail", pk=pk)


@login_required
@require_POST
def accept_idea(request: HttpRequest, pk: str) -> HttpResponse:
    """Accept idea and start development - spawns fleet generation."""
    idea = get_idea_for_user(request.user, pk)
    if not user_can_create_companies(request.user):
        messages.error(request, "You do not have permission to create companies.")
        return redirect("idea_detail", pk=pk)
    if idea.status != IdeaRequest.Status.SUCCEEDED:
        return redirect("idea_detail", pk=pk)
    if idea.development_status == IdeaRequest.DevelopmentStatus.GENERATING_FLEET:
        return redirect("idea_detail", pk=pk)
    company = getattr(idea, "company", None)
    if company:
        return redirect("company_detail", pk=company.pk)
    idea.accepted_at = timezone.now()
    idea.owner = idea.owner or request.user
    idea.development_status = IdeaRequest.DevelopmentStatus.GENERATING_FLEET
    idea.save(update_fields=["accepted_at", "owner", "development_status", "updated_at"])
    _spawn_fleet_process(str(idea.pk))
    return redirect("idea_detail", pk=pk)


@login_required
@require_http_methods(["GET"])
def delete_idea_confirm(request: HttpRequest, pk: str) -> HttpResponse:
    """Confirmation page before deleting an idea request."""
    idea = get_idea_for_user(request.user, pk)
    return render(request, "web/delete_confirm.html", {"idea": idea})


@login_required
@require_POST
def delete_idea(request: HttpRequest, pk: str) -> HttpResponse:
    """Delete an idea request and all related data."""
    idea = get_idea_for_user(request.user, pk)
    idea.delete()
    return redirect("home")


@login_required
@require_POST
def save_conclusion(request: HttpRequest, pk: str) -> HttpResponse:
    """Save or update IdeaConclusion for idea request."""
    idea = get_idea_for_user(request.user, pk)
    summary = request.POST.get("final_summary", "").strip()
    result_json = request.POST.get("result_json", "{}")
    if not summary:
        conclusion = getattr(idea, "conclusion", None)
        summary = conclusion.final_summary if conclusion else "No summary."
    try:
        json.loads(result_json)
    except json.JSONDecodeError:
        result_json = "{}"
    IdeaConclusion.objects.update_or_create(
        idea_request=idea,
        defaults={"final_summary": summary, "result_json": result_json},
    )
    return redirect("idea_detail", pk=pk)


PIPELINE_AGENT_NAMES = [
    "Internet Explorer",
    "Idea Generator",
    "Estimator",
    "Critic",
    "Executor",
    "Overviewer",
]

PRIMARY_ROLES = {
    "internet_explorer",
    "idea_generator",
    "estimator",
    "critic",
    "executor",
    "overviewer",
}


@login_required
@require_http_methods(["GET"])
def idea_status(request: HttpRequest, pk: str) -> JsonResponse:
    """JSON status for polling - returns status, run count, current/next step."""
    idea = get_idea_for_user(request.user, pk)
    runs = idea.agent_runs.all().order_by("started_at")
    runs_count = runs.count()
    last_run = runs.last()
    primary_done = sum(1 for r in runs if r.role in PRIMARY_ROLES)
    next_step = (
        PIPELINE_AGENT_NAMES[primary_done]
        if primary_done < len(PIPELINE_AGENT_NAMES)
        else None
    )
    company = getattr(idea, "company", None)
    return JsonResponse(
        {
            "status": idea.status,
            "development_status": idea.development_status,
            "runs_count": runs_count,
            "primary_done": primary_done,
            "last_agent": last_run.agent_name if last_run else None,
            "last_agent_status": last_run.status if last_run else None,
            "next_step": next_step,
            "company_id": str(company.pk) if company else None,
        }
    )


@login_required
@require_http_methods(["GET"])
def company_list(request: HttpRequest) -> HttpResponse:
    """List user's companies (from accepted ideas)."""
    companies = companies_queryset_for_user(request.user)[:50]
    return render(request, "web/company_list.html", {"companies": companies})


@login_required
@require_http_methods(["GET"])
def company_detail(request: HttpRequest, pk: str) -> HttpResponse:
    """Company detail: command center with KPIs, readiness, agents, discussions."""
    company = get_company_for_user(request.user, pk)
    ctx = build_company_workspace_context(company, active_tab="overview")
    ctx.update(
        {
            "agents": company.agents.all(),
            "discussions": company.discussions.all()[:15],
            "team_members": company.team_members.filter(is_active=True),
            "human_roles": CompanyTeamMember.Role.choices,
        }
    )
    return render(request, "web/company_detail.html", ctx)


@login_required
@require_POST
def add_team_member(request: HttpRequest, pk: str) -> HttpResponse:
    """Add a human team member to the company."""
    company = get_company_for_user(request.user, pk)
    name = request.POST.get("name", "").strip()
    role = request.POST.get("role", CompanyTeamMember.Role.OTHER)
    email = request.POST.get("email", "").strip()
    if name and role in dict(CompanyTeamMember.Role.choices):
        CompanyTeamMember.objects.create(
            company=company,
            name=name,
            role=role,
            email=email,
        )
    return redirect("company_detail", pk=pk)


@login_required
@require_POST
def run_autonomous_loop_now(request: HttpRequest, pk: str) -> HttpResponse:
    """Manually run schedule/execute loop when selected actions are not on the calendar yet."""
    company = get_company_for_user(request.user, pk)
    if company.status != Company.Status.ACTIVE:
        messages.error(request, "Company must be active to run the autonomous loop.")
        return redirect("company_detail", pk=pk)
    pending = count_unscheduled_selected(company)
    if pending == 0:
        messages.warning(request, "No selected actions waiting to be scheduled.")
        return redirect("company_detail", pk=pk)
    schedule_only = not company.autonomous_mode
    try:
        result = process_company(company, schedule_and_execute_only=schedule_only)
    except Exception:
        logger.exception("Manual autonomous loop failed for company %s", company.pk)
        messages.error(
            request,
            "Autonomous loop failed. Check LLM settings and server logs.",
        )
        return redirect("company_detail", pk=pk)
    parts: list[str] = []
    if result.actions_scheduled:
        parts.append(f"Scheduled {result.actions_scheduled} action(s) on the calendar.")
    if result.actions_executed:
        parts.append(f"Executed {result.actions_executed} action(s) due today.")
    if result.improvement_discussion_started:
        parts.append("Started a follow-up director discussion.")
    if result.next_steps_discussion_started:
        parts.append('Started a new "Next steps" discussion.')
    if not parts:
        parts.append(
            "Loop finished but no calendar entries were added. "
            "Verify OpenAI/Ollama settings under LLM Settings."
        )
    messages.success(request, " ".join(parts))
    return redirect("company_detail", pk=pk)


@login_required
@require_POST
def toggle_autonomous_mode(request: HttpRequest, pk: str) -> HttpResponse:
    """Toggle autonomous mode - agents select, schedule, execute without user action."""
    company = get_company_for_user(request.user, pk)
    company.autonomous_mode = not company.autonomous_mode
    company.save(update_fields=["autonomous_mode", "updated_at"])
    return redirect("company_detail", pk=pk)


@login_required
@require_POST
def regenerate_agents(request: HttpRequest, pk: str) -> HttpResponse:
    """Regenerate agent fleet based on current company state."""
    company = get_company_for_user(request.user, pk)
    if company.status == Company.Status.REGENERATING_AGENTS:
        return redirect("company_detail", pk=pk)
    _spawn_regenerate_agents_process(str(company.pk))
    company.status = Company.Status.REGENERATING_AGENTS
    company.save(update_fields=["status", "updated_at"])
    return redirect("company_detail", pk=pk)


@login_required
@require_http_methods(["GET"])
def company_status(request: HttpRequest, pk: str) -> JsonResponse:
    """JSON status for company polling (e.g. when regenerating agents)."""
    company = get_company_for_user(request.user, pk)
    return JsonResponse({"status": company.status})


@login_required
@require_http_methods(["GET"])
def company_agent_chat(request: HttpRequest, company_pk: str, agent_pk: str) -> HttpResponse:
    """Chat with a company agent."""
    company = get_company_for_user(request.user, company_pk)
    agent = get_object_or_404(CompanyAgent, pk=agent_pk, company=company)
    messages = agent.user_messages.filter(user=request.user).order_by("created_at")[:50]
    chat_pending = _agent_has_pending_message(agent, request.user)
    ctx = build_company_workspace_context(company, active_tab="overview")
    ctx.update({"agent": agent, "messages": messages, "chat_pending": chat_pending})
    return render(request, "web/agent_chat.html", ctx)


def _agent_has_pending_message(agent: CompanyAgent, user) -> bool:
    from apps.ideas.models import UserAgentMessage

    return UserAgentMessage.objects.filter(
        agent=agent, user=user, agent_response=""
    ).exists()


def _spawn_agent_chat_process(message_pk: str) -> None:
    """Spawn agent chat response generation in a separate Python process."""
    root = _get_project_root()
    subprocess.Popen(
        [sys.executable, os.path.join(root, "manage.py"), "run_agent_chat", message_pk],
        cwd=root,
        env=_get_subprocess_env(),
        start_new_session=True,
    )


def _run_agent_chat_message(message) -> None:
    """Generate and save agent response for a pending user message."""
    from apps.ideas.models import UserAgentMessage

    message.refresh_from_db()
    if message.agent_response:
        return
    company = message.agent.company
    response_text = _get_agent_response(
        message.agent, message.user_content, message.user, company
    )
    UserAgentMessage.objects.filter(pk=message.pk, agent_response="").update(
        agent_response=response_text
    )


@login_required
@require_POST
def agent_chat_send(request: HttpRequest, company_pk: str, agent_pk: str) -> HttpResponse:
    """Queue user message and generate agent response asynchronously."""
    from apps.ideas.models import UserAgentMessage

    company = get_company_for_user(request.user, company_pk)
    agent = get_object_or_404(CompanyAgent, pk=agent_pk, company=company)
    user_content = request.POST.get("content", "").strip()
    if not user_content:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Message cannot be empty."}, status=400)
        return redirect("company_agent_chat", company_pk=company_pk, agent_pk=agent_pk)
    if _agent_has_pending_message(agent, request.user):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {"ok": False, "error": "Please wait for the agent to finish responding."},
                status=409,
            )
        messages.error(request, "Please wait for the agent to finish responding.")
        return redirect("company_agent_chat", company_pk=company_pk, agent_pk=agent_pk)
    msg = UserAgentMessage.objects.create(
        user=request.user,
        agent=agent,
        user_content=user_content,
        agent_response="",
    )
    _spawn_agent_chat_process(str(msg.pk))
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {"ok": True, "message_id": str(msg.pk), "user_content": user_content}
        )
    return redirect("company_agent_chat", company_pk=company_pk, agent_pk=agent_pk)


@login_required
@require_http_methods(["GET"])
def agent_chat_message_status(
    request: HttpRequest, company_pk: str, agent_pk: str, message_pk: str
) -> JsonResponse:
    """Poll for agent response on a single chat message."""
    from apps.ideas.models import UserAgentMessage

    company = get_company_for_user(request.user, company_pk)
    agent = get_object_or_404(CompanyAgent, pk=agent_pk, company=company)
    msg = get_object_or_404(
        UserAgentMessage, pk=message_pk, agent=agent, user=request.user
    )
    return JsonResponse(
        {
            "id": str(msg.pk),
            "pending": not msg.agent_response,
            "agent_response": msg.agent_response,
        }
    )


def _get_calendar_context(company: Company) -> str:
    """Build calendar/action context for agents - actions from company start date onward."""
    from datetime import timedelta

    start_date = _company_start_date(company)
    today = timezone.localdate()
    end = today + timedelta(days=30)
    entries = CompanyCalendarAction.objects.filter(
        company=company, action_date__gte=start_date, action_date__lte=end
    ).order_by("action_date", "title")[:60]
    if not entries:
        return "No calendar actions on record yet."
    lines = [f"Calendar from {start_date} (company start) through {end}:"]
    for e in entries:
        date_str = e.action_date.isoformat()
        lines.append(f"- {date_str}: {e.title} [{e.get_status_display}]")
        if e.description:
            desc = e.description[:100] + ("..." if len(e.description) > 100 else "")
            lines.append(f"  {desc}")
        if e.completion_notes and e.status == CompanyCalendarAction.ActionStatus.DONE:
            notes = e.completion_notes[:80] + ("..." if len(e.completion_notes) > 80 else "")
            lines.append(f"  Done: {notes}")
    return "\n".join(lines)


def _get_agent_response(
    agent: CompanyAgent, user_content: str, user, company: Company
) -> str:
    """Get LLM response for agent given user message."""
    try:
        from apps.agents.agents import _run_agent
        from apps.agents.schemas import ChatResponse

        idea = company.idea_request
        model = _get_provider_model_for_idea(idea)
        if model is None:
            return "Unable to connect to AI. Check provider configuration."
        calendar_ctx = _get_calendar_context(company)
        context = f"""Company: {company.name}
Idea:
{build_idea_request_prompt(idea)}

{calendar_ctx}

You are {agent.name}, {agent.get_role_display()}. {agent.system_prompt}

The user is the owner and main investor. You have access to the company calendar (agreed actions by date and status). Use it to verify what's done, what's planned, and to suggest roadmap updates. Answer their question about company state, plans, or tasks. Be concise and actionable."""
        user_msg = f"Owner's question: {user_content}"
        out, _ = _run_agent(
            model,
            agent.name,
            context,
            user_msg,
            ChatResponse,
            tools=None,
        )
        if out and hasattr(out, "response"):
            return out.response
        return str(out) if out else "No response generated."
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Agent chat failed: %s", e)
        return f"Error: {e}"


def _get_provider_model_for_idea(idea: IdeaRequest):
    """Get LLM model for idea's provider settings."""
    from apps.agents.providers import get_model_for_idea, validate_provider_config

    if validate_provider_config(idea.provider):
        return None
    return get_model_for_idea(idea)


@login_required
@require_POST
def rerun_discussion(request: HttpRequest, company_pk: str, discussion_pk: str) -> HttpResponse:
    """Re-run a director discussion - interrupt if running, clear messages/actions, spawn fresh."""
    company = get_company_for_user(request.user, company_pk)
    from apps.ideas.models import ActionProposal, DirectorDiscussion, DiscussionMessage

    discussion = get_object_or_404(DirectorDiscussion, pk=discussion_pk, company=company)
    discussion.cancelled = True
    discussion.save(update_fields=["cancelled", "updated_at"])
    DiscussionMessage.objects.filter(discussion=discussion).delete()
    ActionProposal.objects.filter(discussion=discussion).delete()
    discussion.cancelled = False
    discussion.status = DirectorDiscussion.Status.ACTIVE
    discussion.save(update_fields=["cancelled", "status", "updated_at"])
    _spawn_discussion_process(str(discussion.pk))
    return redirect(
        "director_discussion_detail",
        company_pk=company_pk,
        discussion_pk=discussion_pk,
    )


@login_required
@require_http_methods(["GET"])
def discussion_status(request: HttpRequest, company_pk: str, discussion_pk: str) -> JsonResponse:
    """JSON status for discussion polling - progress visible while ACTIVE."""
    company = get_company_for_user(request.user, company_pk)
    from apps.ideas.models import DirectorDiscussion

    discussion = get_object_or_404(DirectorDiscussion, pk=discussion_pk, company=company)
    messages_count = discussion.messages.count()
    actions_count = discussion.actions.count()
    last_msg = discussion.messages.order_by("-created_at").first()
    last_director = last_msg.sender_agent.name if last_msg and last_msg.sender_agent else None
    directors_count = company.agents.filter(role=CompanyAgent.Role.DIRECTOR).count()
    return JsonResponse({
        "status": discussion.status,
        "messages_count": messages_count,
        "actions_count": actions_count,
        "last_director": last_director,
        "directors_count": directors_count,
    })


@login_required
@require_http_methods(["GET"])
def director_discussion_detail(request: HttpRequest, company_pk: str, discussion_pk: str) -> HttpResponse:
    """Director discussion with action proposals."""
    company = get_company_for_user(request.user, company_pk)
    from apps.ideas.models import DirectorDiscussion

    discussion = get_object_or_404(DirectorDiscussion, pk=discussion_pk, company=company)
    discussion.try_complete_selection()
    actions = discussion.actions.all()
    ctx = build_company_workspace_context(company, active_tab="discussions")
    ctx.update(
        {
            "discussion": discussion,
            "actions": actions,
            "unscheduled_selected_count": ctx["counts"]["unscheduled_selected"],
        }
    )
    return render(request, "web/discussion_detail.html", ctx)


@login_required
@require_POST
def action_select(request: HttpRequest, company_pk: str, action_pk: str) -> HttpResponse:
    """Select an action proposal (user approves)."""
    company = get_company_for_user(request.user, company_pk)
    action = get_object_or_404(ActionProposal, pk=action_pk, discussion__company=company)
    action.status = ActionProposal.ActionStatus.SELECTED
    action.save(update_fields=["status"])
    action.discussion.try_complete_selection()
    return redirect(
        "action_schedule",
        company_pk=company_pk,
        action_pk=action_pk,
    )


@login_required
@require_http_methods(["GET", "POST"])
def action_schedule(request: HttpRequest, company_pk: str, action_pk: str) -> HttpResponse:
    """Schedule a selected action for a calendar date."""
    company = get_company_for_user(request.user, company_pk)
    action = get_object_or_404(ActionProposal, pk=action_pk, discussion__company=company)
    if action.status != ActionProposal.ActionStatus.SELECTED:
        action.status = ActionProposal.ActionStatus.SELECTED
        action.save(update_fields=["status"])
    if request.method == "POST":
        date_str = request.POST.get("action_date", "").strip()
        action_date = parse_date(date_str) if date_str else timezone.localdate()
        start_date = _company_start_date(company)
        if action_date < start_date:
            action_date = start_date
        entry, created = CompanyCalendarAction.objects.get_or_create(
            action_proposal=action,
            company=company,
            defaults={
                "action_date": action_date,
                "title": action.action_type,
                "description": action.description,
            },
        )
        if not created:
            entry.action_date = action_date
            entry.save(update_fields=["action_date", "updated_at"])
        return redirect(
            "director_discussion_detail",
            company_pk=company_pk,
            discussion_pk=str(action.discussion_id),
        )
    today = timezone.localdate()
    start_date = _company_start_date(company)
    if today < start_date:
        today = start_date
    return render(
        request,
        "web/action_schedule.html",
        {"company": company, "action": action, "today": today.isoformat(), "min_date": start_date.isoformat()},
    )


@login_required
@require_POST
def action_reject(request: HttpRequest, company_pk: str, action_pk: str) -> HttpResponse:
    """Reject an action proposal."""
    company = get_company_for_user(request.user, company_pk)
    action = get_object_or_404(ActionProposal, pk=action_pk, discussion__company=company)
    action.status = ActionProposal.ActionStatus.REJECTED
    action.save(update_fields=["status"])
    action.discussion.try_complete_selection()
    return redirect(
        "director_discussion_detail",
        company_pk=company_pk,
        discussion_pk=str(action.discussion_id),
    )


def _company_start_date(company: Company):
    """Date when company was created - calendar starts from this day."""
    from datetime import date

    created = company.created_at
    if timezone.is_naive(created):
        return created.date()
    return timezone.localtime(created).date()


@login_required
@require_http_methods(["GET"])
def company_calendar(request: HttpRequest, company_pk: str) -> HttpResponse:
    """Calendar month view - actions per day. Starts from company creation date."""
    import calendar as cal_module
    from datetime import date

    company = get_company_for_user(request.user, company_pk)
    start_date = _company_start_date(company)
    today = timezone.localdate()
    if today >= start_date:
        default_year, default_month = today.year, today.month
    else:
        default_year, default_month = start_date.year, start_date.month
    year = int(request.GET.get("year", default_year))
    month = int(request.GET.get("month", default_month))
    shown_first = date(year, month, 1)
    if shown_first < date(start_date.year, start_date.month, 1):
        year, month = default_year, default_month
        shown_first = date(year, month, 1)
    cal = cal_module.Calendar(firstweekday=0)
    weeks = list(cal.monthdatescalendar(year, month))
    first = date(year, month, 1)
    last = date(year, month, cal_module.monthrange(year, month)[1])
    qs = CompanyCalendarAction.objects.filter(
        company=company, action_date__gte=first, action_date__lte=last
    ).order_by("action_date")
    actions_by_date = {}
    for entry in qs:
        d = entry.action_date
        if d not in actions_by_date:
            actions_by_date[d] = []
        actions_by_date[d].append(entry)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    has_prev = (prev_year, prev_month) >= (start_date.year, start_date.month)
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    is_current_month = year == today.year and month == today.month
    can_go_today = today >= start_date
    ctx = build_company_workspace_context(company, active_tab="calendar")
    ctx.update(
        {
            "year": year,
            "month": month,
            "month_name": cal_module.month_name[month],
            "weeks": weeks,
            "actions_by_date": actions_by_date,
            "start_date": start_date,
            "today": today,
            "is_current_month": is_current_month,
            "can_go_today": can_go_today,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "has_prev": has_prev,
        }
    )
    return render(request, "web/company_calendar.html", ctx)


@login_required
@require_http_methods(["GET"])
def company_calendar_date(
    request: HttpRequest, company_pk: str, year: int, month: int, day: int
) -> HttpResponse:
    """Actions for a specific date. Only valid from company creation date onward."""
    from datetime import date

    company = get_company_for_user(request.user, company_pk)
    start_date = _company_start_date(company)
    action_date = date(year, month, day)
    if action_date < start_date:
        return redirect(
            "company_calendar_date",
            company_pk=company_pk,
            year=start_date.year,
            month=start_date.month,
            day=start_date.day,
        )
    actions = CompanyCalendarAction.objects.filter(
        company=company, action_date=action_date
    ).order_by("status", "title")
    status_choices = CompanyCalendarAction.ActionStatus.choices
    today = timezone.localdate()
    return render(
        request,
        "web/company_calendar_date.html",
        {
            "company": company,
            "action_date": action_date,
            "actions": actions,
            "status_choices": status_choices,
            "today": today,
            "is_today": action_date == today,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def calendar_action_add(request: HttpRequest, company_pk: str) -> HttpResponse:
    """Add a manual action to a date."""
    company = get_company_for_user(request.user, company_pk)
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        date_str = request.POST.get("action_date", "").strip()
        action_date = parse_date(date_str) if date_str else timezone.localdate()
        start_date = _company_start_date(company)
        if action_date < start_date:
            action_date = start_date
        if title:
            CompanyCalendarAction.objects.create(
                company=company,
                action_date=action_date,
                title=title,
                description=description,
            )
        return redirect("company_calendar", company_pk=company_pk)
    start_date = _company_start_date(company)
    date_str = request.GET.get("date", "")
    parsed = parse_date(date_str) if date_str else None
    if parsed and parsed >= start_date:
        today = parsed.isoformat()
    else:
        today = max(timezone.localdate(), start_date).isoformat()
    return render(
        request,
        "web/calendar_action_add.html",
        {"company": company, "today": today, "min_date": start_date.isoformat()},
    )


@login_required
@require_POST
def calendar_action_update_status(
    request: HttpRequest, company_pk: str, entry_pk: str
) -> HttpResponse:
    """Update status of a calendar action."""
    company = get_company_for_user(request.user, company_pk)
    entry = get_object_or_404(CompanyCalendarAction, pk=entry_pk, company=company)
    new_status = request.POST.get("status", "").strip()
    completion_notes = request.POST.get("completion_notes", "").strip()
    if new_status in dict(CompanyCalendarAction.ActionStatus.choices):
        entry.status = new_status
    if completion_notes:
        entry.completion_notes = completion_notes
    entry.save(update_fields=["status", "completion_notes", "updated_at"])
    return redirect(
        "company_calendar_date",
        company_pk=company_pk,
        year=entry.action_date.year,
        month=entry.action_date.month,
        day=entry.action_date.day,
    )


@login_required
@require_http_methods(["GET", "POST"])
def start_discussion(request: HttpRequest, company_pk: str) -> HttpResponse:
    """Start a new director discussion (spawns directors to propose actions in background)."""
    company = get_company_for_user(request.user, company_pk)
    from apps.ideas.models import DirectorDiscussion

    if request.method == "POST":
        topic = request.POST.get("topic", "").strip() or "Next steps"
        discussion = DirectorDiscussion.objects.create(
            company=company, topic=topic, status=DirectorDiscussion.Status.ACTIVE
        )
        _spawn_discussion_process(str(discussion.pk))
        return redirect(
            "director_discussion_detail",
            company_pk=company_pk,
            discussion_pk=str(discussion.pk),
        )
    ctx = build_company_workspace_context(company, active_tab="overview")
    return render(request, "web/start_discussion.html", ctx)


def _spawn_discussion_process(discussion_pk: str) -> None:
    """Spawn director discussion via manage.py in a separate Python process."""
    root = _get_project_root()
    subprocess.Popen(
        [sys.executable, os.path.join(root, "manage.py"), "run_discussion", discussion_pk],
        cwd=root,
        env=_get_subprocess_env(),
        start_new_session=True,
    )


def _run_director_discussion(discussion) -> None:
    """Run director discussion - directors discuss topic and propose actions (each sees prior messages)."""
    import logging

    from apps.ideas.models import ActionProposal, DirectorDiscussion, DiscussionMessage

    logger = logging.getLogger(__name__)
    discussion.refresh_from_db()
    if discussion.cancelled:
        logger.info("Discussion %s cancelled before start", discussion.pk)
        return
    directors = discussion.company.agents.filter(role=CompanyAgent.Role.DIRECTOR).order_by("-priority")
    if not directors.exists():
        discussion.status = DirectorDiscussion.Status.FAILED
        discussion.save(update_fields=["status"])
        logger.warning("No directors in company %s, discussion %s cannot run", discussion.company_id, discussion.pk)
        return
    try:
        from apps.agents.agents import _run_agent
        from apps.agents.schemas import DirectorDiscussionOutput

        idea = discussion.company.idea_request
        model = _get_provider_model_for_idea(idea)
        if model is None:
            discussion.status = DirectorDiscussion.Status.FAILED
            discussion.save(update_fields=["status"])
            logger.error("Provider setup failed for discussion %s", discussion.pk)
            return
        base_context = (
            f"Company: {discussion.company.name}\n"
            f"Topic: {discussion.topic}\n"
            f"Idea:\n{build_idea_request_prompt(idea)}\n\n"
        )
        prior_messages: list[str] = []
        for director in directors:
            discussion.refresh_from_db()
            if discussion.cancelled:
                logger.info("Discussion %s cancelled, stopping", discussion.pk)
                return
            context = base_context
            if prior_messages:
                context += "Prior director contributions:\n" + "\n".join(prior_messages) + "\n\n"
            context += "Now give your contribution and proposed actions."
            system = (
                f"You are {director.name}. {director.system_prompt}\n"
                f"Discuss the topic. If others have spoken, respond to their points. "
                f"Propose 1-2 concrete actions. Output valid JSON with message (your discussion text) "
                f"and proposed_actions array (each: action_type, description, rationale)."
            )
            out, _ = _run_agent(
                model, director.name, system, context, DirectorDiscussionOutput, tools=None
            )
            msg_text = out.message if out else ""
            DiscussionMessage.objects.create(
                discussion=discussion,
                sender_type=DiscussionMessage.SenderType.AGENT,
                sender_agent=director,
                content=msg_text,
            )
            if msg_text:
                prior_messages.append(f"{director.name}: {msg_text}")
            if out and out.proposed_actions:
                for a in out.proposed_actions:
                    ActionProposal.objects.create(
                        discussion=discussion,
                        proposed_by=director,
                        action_type=a.action_type,
                        description=a.description,
                        rationale=a.rationale,
                    )
        discussion.status = DirectorDiscussion.Status.AWAITING_SELECTION
        discussion.save(update_fields=["status"])
        if discussion.company.autonomous_mode:
            from apps.agents.autonomous import agent_select_actions
            agent_select_actions(discussion)
        discussion.try_complete_selection()
    except Exception as e:
        logger.exception("Director discussion failed: %s", e)
        discussion.status = DirectorDiscussion.Status.FAILED
        discussion.save(update_fields=["status"])


@login_required
@require_http_methods(["GET"])
def download_json(request: HttpRequest, pk: str) -> HttpResponse:
    """Download idea result as JSON file."""
    idea = get_idea_for_user(request.user, pk)
    data = {
        "id": str(idea.pk),
        "title": idea.title,
        "prompt": idea.prompt,
        "status": idea.status,
        "provider": idea.provider,
        "created_at": idea.created_at.isoformat(),
        "agent_runs": [],
    }
    for r in idea.agent_runs.all():
        data["agent_runs"].append(
            {
                "agent_name": r.agent_name,
                "role": r.role,
                "confidence": r.confidence,
                "cycles": r.cycles,
                "duration_ms": r.duration_ms,
                "status": r.status,
                "output": json.loads(r.output_json) if r.output_json else None,
            }
        )
    conclusion = getattr(idea, "conclusion", None)
    if conclusion:
        data["conclusion"] = {
            "final_summary": conclusion.final_summary,
            "result_json": json.loads(conclusion.result_json)
            if conclusion.result_json
            else {},
        }
    response = HttpResponse(
        json.dumps(data, indent=2),
        content_type="application/json",
    )
    response["Content-Disposition"] = f'attachment; filename="idea_{idea.pk}.json"'
    return response
