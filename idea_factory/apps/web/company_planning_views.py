"""Views for company planning, tasks, direction, and history."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.access import get_company_for_user
from apps.ideas.company_history import record_history
from apps.ideas.models import (
    Company,
    CompanyAgent,
    CompanyHistoryEntry,
    CompanyStrategicDirection,
    CompanyTask,
    CompanyTaskDependency,
    CompanyTeamMember,
    PlanningSession,
)
from apps.ideas.planning import monday_of_week, spawn_planning_process, start_planning_session
from apps.ideas.planning_context import (
    build_strategic_planning_context,
    compute_progress_metrics,
    get_active_direction,
)

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def company_tasks(request: HttpRequest, company_pk: str) -> HttpResponse:
    """Task board: assignees, status, progress, dependencies."""
    company = get_company_for_user(request.user, company_pk)
    status_filter = request.GET.get("status", "").strip()
    qs = (
        company.tasks.select_related("assigned_agent", "assigned_human", "planning_session")
        .prefetch_related(
            Prefetch(
                "dependencies",
                queryset=CompanyTaskDependency.objects.select_related("depends_on"),
            )
        )
        .order_by("sort_order", "created_at")
    )
    if status_filter and status_filter in dict(CompanyTask.Status.choices):
        qs = qs.filter(status=status_filter)

    progress = compute_progress_metrics(company)
    direction = get_active_direction(company)
    agents = company.agents.all()
    humans = company.team_members.filter(is_active=True)

    return render(
        request,
        "web/company_tasks.html",
        {
            "company": company,
            "tasks": qs,
            "progress": progress,
            "direction": direction,
            "status_filter": status_filter,
            "status_choices": CompanyTask.Status.choices,
            "agents": agents,
            "humans": humans,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def company_task_detail(
    request: HttpRequest, company_pk: str, task_pk: str
) -> HttpResponse:
    company = get_company_for_user(request.user, company_pk)
    task = get_object_or_404(
        CompanyTask.objects.select_related(
            "assigned_agent", "assigned_human", "planning_session", "calendar_action"
        ),
        pk=task_pk,
        company=company,
    )
    dependencies = task.dependencies.select_related("depends_on").all()
    dependents = task.dependents.select_related("task").all()

    if request.method == "POST":
        _apply_task_update(request, company, task)
        return redirect("company_task_detail", company_pk=company_pk, task_pk=task_pk)

    return render(
        request,
        "web/company_task_detail.html",
        {
            "company": company,
            "task": task,
            "dependencies": dependencies,
            "dependents": dependents,
            "status_choices": CompanyTask.Status.choices,
            "agents": company.agents.all(),
            "humans": company.team_members.filter(is_active=True),
        },
    )


def _apply_task_update(request: HttpRequest, company: Company, task: CompanyTask) -> None:
    new_status = request.POST.get("status", "").strip()
    progress = request.POST.get("progress_percent", "").strip()
    result_summary = request.POST.get("result_summary", "").strip()
    result_notes = request.POST.get("result_notes", "").strip()
    agent_id = request.POST.get("assigned_agent_id", "").strip()
    human_id = request.POST.get("assigned_human_id", "").strip()

    update_fields = ["updated_at"]
    if new_status in dict(CompanyTask.Status.choices):
        task.status = new_status
        update_fields.append("status")
        if new_status == CompanyTask.Status.DONE:
            task.completed_at = timezone.now()
            task.progress_percent = 100
            update_fields.extend(["completed_at", "progress_percent"])
    if progress.isdigit():
        task.progress_percent = min(100, max(0, int(progress)))
        update_fields.append("progress_percent")
    if result_summary:
        task.result_summary = result_summary
        update_fields.append("result_summary")
    if result_notes:
        task.result_notes = result_notes
        update_fields.append("result_notes")

    if agent_id:
        agent = get_object_or_404(CompanyAgent, pk=agent_id, company=company)
        task.assigned_agent = agent
        task.assigned_human = None
        task.assignee_type = CompanyTask.AssigneeType.AGENT
        update_fields.extend(["assigned_agent", "assigned_human", "assignee_type"])
    elif human_id:
        human = get_object_or_404(CompanyTeamMember, pk=human_id, company=company)
        task.assigned_human = human
        task.assigned_agent = None
        task.assignee_type = CompanyTask.AssigneeType.HUMAN
        update_fields.extend(["assigned_agent", "assigned_human", "assignee_type"])

    task.save(update_fields=list(set(update_fields)))

    if task.status == CompanyTask.Status.DONE and task.result_summary:
        record_history(
            company,
            CompanyHistoryEntry.EntryType.TASK_COMPLETED,
            task.title,
            summary=task.result_summary[:500],
            related_task=task,
        )
    else:
        record_history(
            company,
            CompanyHistoryEntry.EntryType.TASK_UPDATED,
            task.title,
            summary=f"{task.get_status_display()} · {task.progress_percent}%",
            related_task=task,
        )
    messages.success(request, "Task updated.")


@login_required
@require_POST
def company_task_escalate(
    request: HttpRequest, company_pk: str, task_pk: str
) -> HttpResponse:
    """Mark task as needing human when agent cannot complete."""
    company = get_company_for_user(request.user, company_pk)
    task = get_object_or_404(CompanyTask, pk=task_pk, company=company)
    human_id = request.POST.get("assigned_human_id", "").strip()
    task.escalated_to_human = True
    task.status = CompanyTask.Status.BLOCKED
    task.assigned_agent = None
    task.assignee_type = CompanyTask.AssigneeType.HUMAN
    if human_id:
        task.assigned_human = get_object_or_404(
            CompanyTeamMember, pk=human_id, company=company
        )
    else:
        founder = company.team_members.filter(
            is_active=True, role=CompanyTeamMember.Role.FOUNDER
        ).first()
        task.assigned_human = founder
    task.save()
    record_history(
        company,
        CompanyHistoryEntry.EntryType.TASK_ESCALATED,
        task.title,
        summary="Escalated to human — agent could not complete.",
        related_task=task,
    )
    messages.warning(request, f"Task «{task.title}» escalated to human.")
    return redirect("company_task_detail", company_pk=company_pk, task_pk=task_pk)


@login_required
@require_http_methods(["GET"])
def company_planning(request: HttpRequest, company_pk: str) -> HttpResponse:
    company = get_company_for_user(request.user, company_pk)
    sessions = company.planning_sessions.all()[:15]
    direction = get_active_direction(company)
    progress = compute_progress_metrics(company)
    return render(
        request,
        "web/company_planning.html",
        {
            "company": company,
            "sessions": sessions,
            "direction": direction,
            "progress": progress,
            "week_start": monday_of_week(),
        },
    )


@login_required
@require_POST
def company_planning_start(request: HttpRequest, company_pk: str) -> HttpResponse:
    company = get_company_for_user(request.user, company_pk)
    if company.status != Company.Status.ACTIVE:
        messages.error(request, "Company must be active to run planning.")
        return redirect("company_planning", company_pk=company_pk)

    session = start_planning_session(
        company,
        trigger=PlanningSession.Trigger.MANUAL,
        user=request.user,
    )
    spawn_planning_process(str(session.pk))
    messages.success(request, "Planning session started. Refresh when complete.")
    return redirect("company_planning_detail", company_pk=company_pk, session_pk=session.pk)


@login_required
@require_http_methods(["GET"])
def company_planning_detail(
    request: HttpRequest, company_pk: str, session_pk: str
) -> HttpResponse:
    company = get_company_for_user(request.user, company_pk)
    session = get_object_or_404(PlanningSession, pk=session_pk, company=company)
    tasks = session.tasks.select_related("assigned_agent", "assigned_human").prefetch_related(
        Prefetch(
            "dependencies",
            queryset=CompanyTaskDependency.objects.select_related("depends_on"),
        )
    )
    return render(
        request,
        "web/company_planning_detail.html",
        {
            "company": company,
            "session": session,
            "tasks": tasks,
        },
    )


@login_required
@require_http_methods(["GET"])
def planning_session_status(
    request: HttpRequest, company_pk: str, session_pk: str
) -> JsonResponse:
    company = get_company_for_user(request.user, company_pk)
    session = get_object_or_404(PlanningSession, pk=session_pk, company=company)
    return JsonResponse(
        {
            "status": session.status,
            "summary": session.summary[:500] if session.summary else "",
            "task_count": session.tasks.count(),
        }
    )


@login_required
@require_http_methods(["GET", "POST"])
def company_direction(request: HttpRequest, company_pk: str) -> HttpResponse:
    """Set or verify strategic direction with founders."""
    company = get_company_for_user(request.user, company_pk)
    direction = get_active_direction(company)

    if request.method == "POST":
        action = request.POST.get("action", "save")
        statement = request.POST.get("statement", "").strip()
        if action == "verify" and direction:
            direction.founder_verified = True
            direction.verified_at = timezone.now()
            direction.verified_by = request.user
            direction.save(
                update_fields=["founder_verified", "verified_at", "verified_by"]
            )
            record_history(
                company,
                CompanyHistoryEntry.EntryType.DIRECTION_VERIFIED,
                "Direction verified with founders",
                summary=direction.statement[:500],
            )
            messages.success(request, "Direction marked as founder-verified.")
        elif statement:
            if direction:
                direction.is_active = False
                direction.save(update_fields=["is_active"])
            new_dir = CompanyStrategicDirection.objects.create(
                company=company,
                statement=statement,
                is_active=True,
            )
            record_history(
                company,
                CompanyHistoryEntry.EntryType.DIRECTION_CREATED,
                "Strategic direction set",
                summary=statement[:500],
            )
            messages.success(request, "Strategic direction saved.")
        return redirect("company_direction", company_pk=company_pk)

    directions = company.strategic_directions.all()[:10]
    return render(
        request,
        "web/company_direction.html",
        {
            "company": company,
            "direction": direction,
            "directions": directions,
        },
    )


@login_required
@require_http_methods(["GET"])
def company_history(request: HttpRequest, company_pk: str) -> HttpResponse:
    company = get_company_for_user(request.user, company_pk)
    entries = (
        company.history_entries.select_related("related_task", "related_planning_session")
        .order_by("-created_at")[:80]
    )
    progress = compute_progress_metrics(company)
    return render(
        request,
        "web/company_history.html",
        {
            "company": company,
            "entries": entries,
            "progress": progress,
            "context_preview": build_strategic_planning_context(company)[:1200],
        },
    )
