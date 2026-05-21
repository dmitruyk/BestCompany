"""Tests for company workspace UI context."""
import pytest

from apps.ideas.models import CompanyTask, DirectorDiscussion
from apps.web.company_workspace import build_attention_items, build_company_workspace_context


@pytest.mark.django_db
def test_workspace_context_includes_kpis(company):
    ctx = build_company_workspace_context(company, active_tab="overview")
    assert ctx["active_tab"] == "overview"
    assert "progress" in ctx
    assert "readiness" in ctx
    assert ctx["dev_plan"]["kpis"]
    assert ctx["counts"]["open_tasks"] >= 0


@pytest.mark.django_db
def test_attention_items_awaiting_selection(company):
    DirectorDiscussion.objects.create(
        company=company,
        topic="Budget",
        status=DirectorDiscussion.Status.AWAITING_SELECTION,
    )
    counts = {"awaiting_selection": 1, "unscheduled_selected": 0, "calendar_overdue": 0,
              "blocked_tasks": 0, "runnable_tasks": 0, "open_tasks": 0, "readiness_fails": 0}
    items = build_attention_items(company, counts=counts)
    assert any("discussion" in i.label.lower() for i in items)


@pytest.mark.django_db
def test_annotate_task_execution_hints(company, full_agent_fleet):
    agent = full_agent_fleet[0]
    task = CompanyTask.objects.create(
        company=company,
        title="Blocked task",
        status=CompanyTask.Status.TODO,
        assigned_agent=agent,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        progress_percent=0,
    )
    from apps.web.company_workspace import annotate_task_execution_hints

    annotate_task_execution_hints([task])
    assert task.execution_hint is None or isinstance(task.execution_hint, str)
