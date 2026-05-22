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
from apps.ideas.planning_context import build_strategic_planning_context, get_active_direction
from apps.ideas.task_execution import get_runnable_tasks, run_task_execution_for_company
from apps.web.company_workspace import (
    annotate_task_execution_hints,
    build_company_workspace_context,
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

    tasks = list(qs)
    annotate_task_execution_hints(tasks)
    ctx = build_company_workspace_context(company, active_tab="tasks")
    ctx.update(
        {
            "tasks": tasks,
            "status_filter": status_filter,
            "status_choices": CompanyTask.Status.choices,
            "runnable_count": ctx["counts"]["runnable_tasks"],
        }
    )
    return render(request, "web/company_tasks.html", ctx)


@login_required
@require_POST
def company_tasks_run_now(request: HttpRequest, company_pk: str) -> HttpResponse:
    """Run eligible agent tasks immediately (same logic as the background ticker)."""
    company = get_company_for_user(request.user, company_pk)
    if company.status != Company.Status.ACTIVE:
        messages.error(request, "Company must be active to run tasks.")
        return redirect("company_tasks", company_pk=company_pk)

    runnable = get_runnable_tasks(company, limit=10)
    if not runnable:
        messages.warning(
            request,
            "No agent tasks are ready. Tasks must be To Do, assigned to an AI agent, "
            "and not blocked by dependencies. "
            "Human-assigned tasks must be completed manually.",
        )
        return redirect("company_tasks", company_pk=company_pk)

    max_tasks = min(10, max(1, len(runnable)))
    try:
        result = run_task_execution_for_company(
            company, max_tasks=max_tasks, manual_trigger=True
        )
    except Exception:
        logger.exception("Manual task execution failed for company %s", company.pk)
        messages.error(
            request,
            "Task execution failed. Check LLM settings and server logs.",
        )
        return redirect("company_tasks", company_pk=company_pk)

    parts: list[str] = []
    if result.tasks_completed:
        parts.append(f"Completed {result.tasks_completed} task(s).")
    if result.tasks_partial:
        parts.append(f"{result.tasks_partial} task(s) in progress with partial results.")
    if result.tasks_escalated:
        parts.append(f"Escalated {result.tasks_escalated} task(s) to human.")
    if result.tasks_failed:
        parts.append(f"{result.tasks_failed} task(s) failed (reverted to To Do).")
    if not parts:
        parts.append("No tasks were executed.")
    messages.success(request, " ".join(parts))
    return redirect("company_tasks", company_pk=company_pk)


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

    from apps.ideas.task_execution import explain_task_skip

    ctx = build_company_workspace_context(company, active_tab="tasks")
    ctx.update(
        {
            "task": task,
            "dependencies": dependencies,
            "dependents": dependents,
            "status_choices": CompanyTask.Status.choices,
            "agents": company.agents.all(),
            "humans": company.team_members.filter(is_active=True),
            "execution_hint": (
                explain_task_skip(task)
                if task.status == CompanyTask.Status.TODO
                else None
            ),
        }
    )
    if ctx["execution_hint"] == "eligible":
        ctx["execution_hint"] = None
    return render(request, "web/company_task_detail.html", ctx)


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
    ctx = build_company_workspace_context(company, active_tab="planning")
    ctx.update({"sessions": sessions, "week_start": monday_of_week()})
    return render(request, "web/company_planning.html", ctx)


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
    ctx = build_company_workspace_context(company, active_tab="planning")
    ctx.update({"session": session, "tasks": tasks})
    return render(request, "web/company_planning_detail.html", ctx)


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
    ctx = build_company_workspace_context(company, active_tab="direction")
    ctx.update({"directions": directions})
    return render(request, "web/company_direction.html", ctx)


@login_required
@require_http_methods(["GET"])
def company_history(request: HttpRequest, company_pk: str) -> HttpResponse:
    company = get_company_for_user(request.user, company_pk)
    entries = (
        company.history_entries.select_related("related_task", "related_planning_session")
        .order_by("-created_at")[:80]
    )
    ctx = build_company_workspace_context(company, active_tab="history")
    ctx.update(
        {
            "entries": entries,
            "context_preview": build_strategic_planning_context(company)[:1200],
        }
    )
    return render(request, "web/company_history.html", ctx)
