"""Tests for company readiness and best-practice checks."""
import json
from datetime import date

import pytest

from apps.ideas.best_practices import assess_company_readiness
from apps.ideas.models import (
    ActionProposal,
    Company,
    CompanyAgent,
    CompanyCalendarAction,
    CompanyTeamMember,
    DirectorDiscussion,
    IdeaConclusion,
    IdeaRequest,
)


@pytest.mark.django_db
def test_readiness_fails_without_pipeline(company) -> None:
    company.idea_request.status = IdeaRequest.Status.PENDING
    company.idea_request.save()
    report = assess_company_readiness(company)
    by_id = {c.check_id: c.status for c in report.checks}
    assert by_id["idea_pipeline"] == "fail"
    assert report.phase == "Discovery"


@pytest.mark.django_db
def test_readiness_passes_with_full_setup(
    company, full_agent_fleet, idea_conclusion
) -> None:
    del full_agent_fleet, idea_conclusion
    CompanyTeamMember.objects.create(
        company=company,
        name="Jane Founder",
        role=CompanyTeamMember.Role.FOUNDER,
    )
    disc = DirectorDiscussion.objects.create(
        company=company, topic="Launch plan", status=DirectorDiscussion.Status.COMPLETED
    )
    action = ActionProposal.objects.create(
        discussion=disc,
        action_type="mvp",
        description="Build MVP",
        status=ActionProposal.ActionStatus.SELECTED,
    )
    CompanyCalendarAction.objects.create(
        company=company,
        action_proposal=action,
        action_date=date.today(),
        title="MVP sprint",
        status=CompanyCalendarAction.ActionStatus.DONE,
        completion_notes="Done",
    )
    report = assess_company_readiness(company)
    assert report.fail_count == 0
    assert report.pass_count >= 10
    by_id = {c.check_id: c.status for c in report.checks}
    assert by_id["development_plan"] == "pass"
    assert by_id["go_no_go_decision"] == "pass"
    assert by_id["human_founders"] == "pass"
    assert by_id["qa_coverage"] == "pass"


@pytest.mark.django_db
def test_qa_warns_without_coverage(company, idea_conclusion) -> None:
    del idea_conclusion
    CompanyAgent.objects.create(
        company=company,
        role=CompanyAgent.Role.CPA,
        name="CPA",
        system_prompt="Finance",
    )
    report = assess_company_readiness(company)
    qa = next(c for c in report.checks if c.check_id == "qa_coverage")
    assert qa.status in ("warn", "fail")


@pytest.mark.django_db
def test_practice_check_icons() -> None:
    from apps.ideas.best_practices import PracticeCheck

    assert PracticeCheck("a", "b", "pass", "ok").icon == "🟢"
    assert PracticeCheck("a", "b", "warn", "ok").icon == "🟡"
    assert PracticeCheck("a", "b", "fail", "ok").icon == "🔴"
