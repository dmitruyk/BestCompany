"""Web views for multi-agent panel discussions."""
from __future__ import annotations

import subprocess

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.access import get_company_for_user
from apps.ideas.models import AgentPanelDiscussion, AgentPanelMessage, AgentPanelParticipant
from apps.web.company_workspace import build_company_workspace_context
from apps.web.subprocess_utils import get_project_root, get_subprocess_env, manage_py_argv

MIN_PANEL_AGENTS = 2


def _spawn_agent_panel_process(discussion_pk: str) -> None:
    subprocess.Popen(
        manage_py_argv("run_agent_panel", discussion_pk),
        cwd=get_project_root(),
        env=get_subprocess_env(),
        start_new_session=True,
    )


@login_required
@require_http_methods(["GET", "POST"])
def start_agent_panel(request: HttpRequest, company_pk: str) -> HttpResponse:
    """Start a panel discussion with selected agents."""
    company = get_company_for_user(request.user, company_pk)
    agents = list(company.agents.order_by("-priority", "name"))

    if request.method == "POST":
        question = request.POST.get("question", "").strip()
        selected_ids = request.POST.getlist("agent_ids")
        if not question:
            messages.error(request, "Please enter a question for the panel.")
            return redirect("start_agent_panel", company_pk=company_pk)
        if len(selected_ids) < MIN_PANEL_AGENTS:
            messages.error(request, f"Select at least {MIN_PANEL_AGENTS} agents for a panel discussion.")
            return redirect("start_agent_panel", company_pk=company_pk)

        valid_agents = {
            str(a.pk): a
            for a in agents
            if str(a.pk) in selected_ids
        }
        if len(valid_agents) < MIN_PANEL_AGENTS:
            messages.error(request, f"Select at least {MIN_PANEL_AGENTS} valid agents.")
            return redirect("start_agent_panel", company_pk=company_pk)

        discussion = AgentPanelDiscussion.objects.create(
            company=company,
            user=request.user,
            question=question,
            status=AgentPanelDiscussion.Status.ACTIVE,
        )
        for order, agent_id in enumerate(selected_ids):
            agent = valid_agents.get(agent_id)
            if agent is None:
                continue
            AgentPanelParticipant.objects.create(
                discussion=discussion,
                agent=agent,
                sort_order=order,
            )
        _spawn_agent_panel_process(str(discussion.pk))
        return redirect(
            "agent_panel_detail",
            company_pk=company_pk,
            discussion_pk=str(discussion.pk),
        )

    ctx = build_company_workspace_context(company, active_tab="overview")
    ctx.update({"agents": agents, "min_panel_agents": MIN_PANEL_AGENTS})
    return render(request, "web/start_agent_panel.html", ctx)


@login_required
@require_http_methods(["GET"])
def agent_panel_detail(
    request: HttpRequest, company_pk: str, discussion_pk: str
) -> HttpResponse:
    """Panel discussion detail with agent messages and synthesis."""
    company = get_company_for_user(request.user, company_pk)
    discussion = get_object_or_404(
        AgentPanelDiscussion,
        pk=discussion_pk,
        company=company,
        user=request.user,
    )
    ctx = build_company_workspace_context(company, active_tab="overview")
    ctx.update(
        {
            "discussion": discussion,
            "panel_messages": discussion.messages.select_related("agent"),
            "participants": discussion.participants.select_related("agent"),
        }
    )
    return render(request, "web/agent_panel_detail.html", ctx)


@login_required
@require_http_methods(["GET"])
def agent_panel_status(
    request: HttpRequest, company_pk: str, discussion_pk: str
) -> JsonResponse:
    """JSON status for panel polling while ACTIVE."""
    company = get_company_for_user(request.user, company_pk)
    discussion = get_object_or_404(
        AgentPanelDiscussion,
        pk=discussion_pk,
        company=company,
        user=request.user,
    )
    messages_count = discussion.messages.count()
    participants_count = discussion.participants.count()
    last_msg = discussion.messages.select_related("agent").order_by("-created_at").first()
    last_agent = last_msg.agent.name if last_msg else None
    return JsonResponse(
        {
            "status": discussion.status,
            "messages_count": messages_count,
            "participants_count": participants_count,
            "last_agent": last_agent,
            "has_synthesis": bool(discussion.synthesis),
        }
    )


@login_required
@require_POST
def rerun_agent_panel(
    request: HttpRequest, company_pk: str, discussion_pk: str
) -> HttpResponse:
    """Re-run a panel discussion from scratch."""
    company = get_company_for_user(request.user, company_pk)
    discussion = get_object_or_404(
        AgentPanelDiscussion,
        pk=discussion_pk,
        company=company,
        user=request.user,
    )
    discussion.cancelled = True
    discussion.save(update_fields=["cancelled", "updated_at"])
    AgentPanelMessage.objects.filter(discussion=discussion).delete()
    discussion.cancelled = False
    discussion.synthesis = ""
    discussion.status = AgentPanelDiscussion.Status.ACTIVE
    discussion.save(update_fields=["cancelled", "synthesis", "status", "updated_at"])
    _spawn_agent_panel_process(str(discussion.pk))
    return redirect(
        "agent_panel_detail",
        company_pk=company_pk,
        discussion_pk=discussion_pk,
    )
