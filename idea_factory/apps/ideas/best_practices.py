"""
Company readiness and best-practice checks for idea → company success path.

Each check returns pass (green), warn (yellow), or fail (red) per user workflow rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from apps.ideas.development_plan import get_development_plan_summary
from apps.ideas.models import (
    ActionProposal,
    Company,
    CompanyAgent,
    CompanyCalendarAction,
    CompanyTeamMember,
    DirectorDiscussion,
    IdeaRequest,
)

CheckStatus = Literal["pass", "warn", "fail"]
Phase = Literal["Discovery", "Optimization", "Validation", "Production"]


@dataclass(frozen=True)
class PracticeCheck:
    """Single best-practice assessment item."""

    check_id: str
    label: str
    status: CheckStatus
    message: str
    owner_hint: str = ""
    target_date_hint: str = ""

    @property
    def icon(self) -> str:
        return {"pass": "🟢", "warn": "🟡", "fail": "🔴"}[self.status]


@dataclass(frozen=True)
class CompanyReadinessReport:
    """Aggregated readiness for a company."""

    company_id: str
    phase: Phase
    checks: tuple[PracticeCheck, ...]
    pass_count: int
    warn_count: int
    fail_count: int
    score_percent: int

    @property
    def is_ready_for_production(self) -> bool:
        return self.fail_count == 0 and self.phase == "Production"


def _check(
    check_id: str,
    label: str,
    ok: bool,
    *,
    warn: bool = False,
    message: str = "",
    owner_hint: str = "",
) -> PracticeCheck:
    if ok:
        status: CheckStatus = "pass"
        msg = message or "OK"
    elif warn:
        status = "warn"
        msg = message or "Needs attention"
    else:
        status = "fail"
        msg = message or "Not met"
    return PracticeCheck(
        check_id=check_id,
        label=label,
        status=status,
        message=msg,
        owner_hint=owner_hint,
    )


def assess_company_readiness(company: Company) -> CompanyReadinessReport:
    """Run all best-practice checks for a company."""
    idea: IdeaRequest = company.idea_request
    agents = list(company.agents.all())
    humans = list(company.team_members.filter(is_active=True))
    plan = get_development_plan_summary(idea)

    agent_roles = {a.role for a in agents}
    human_roles = {h.role for h in humans}

    checks: list[PracticeCheck] = []

    pipeline_ok = idea.status == IdeaRequest.Status.SUCCEEDED
    checks.append(
        _check(
            "idea_pipeline",
            "Idea analysis pipeline completed",
            pipeline_ok,
            message="Pipeline succeeded" if pipeline_ok else f"Status: {idea.status}",
            owner_hint="Owner",
        )
    )

    has_conclusion = hasattr(idea, "conclusion")
    checks.append(
        _check(
            "conclusion_saved",
            "Final conclusion saved",
            has_conclusion,
            owner_hint="Owner",
        )
    )

    go_no_go = plan["go_no_go"].upper()
    has_go = go_no_go in ("GO", "NO-GO", "NO GO")
    checks.append(
        _check(
            "go_no_go_decision",
            "Go / no-go decision recorded",
            has_go,
            warn=bool(plan["executive_summary"]) and not has_go,
            message=plan["go_no_go"] or "Missing from overview",
            owner_hint="Directors + Owner",
        )
    )

    checks.append(
        _check(
            "development_plan",
            "Development plan (milestones / backlog)",
            plan["has_plan"],
            message="Milestones or MVP backlog present"
            if plan["has_plan"]
            else "Run pipeline or add calendar milestones",
            owner_hint="Planner / Product",
        )
    )

    checks.append(
        _check(
            "kpis_defined",
            "KPIs / success metrics defined",
            bool(plan["kpis"]),
            warn=pipeline_ok and not plan["kpis"],
            message=f"{len(plan['kpis'])} KPI(s)" if plan["kpis"] else "No KPIs in estimate",
            owner_hint="CPA / Product",
        )
    )

    director_count = sum(1 for a in agents if a.role == CompanyAgent.Role.DIRECTOR)
    checks.append(
        _check(
            "min_directors",
            "At least 3 director agents",
            director_count >= 3,
            message=f"{director_count} director(s)",
            owner_hint="Fleet generator",
        )
    )

    checks.append(
        _check(
            "finance_agent",
            "Finance agent (CPA)",
            CompanyAgent.Role.CPA in agent_roles,
            owner_hint="CPA agent",
        )
    )

    checks.append(
        _check(
            "marketing_coverage",
            "Marketing agent",
            CompanyAgent.Role.MARKETER in agent_roles,
            owner_hint="Marketer agent",
        )
    )

    has_planner = (
        CompanyAgent.Role.PLANNER in agent_roles
        or CompanyAgent.Role.PRODUCT in agent_roles
    )
    checks.append(
        _check(
            "planning_coverage",
            "Planner or product agent",
            has_planner,
            owner_hint="Planner / Product",
        )
    )

    has_qa = (
        CompanyAgent.Role.QA in agent_roles
        or CompanyTeamMember.Role.QA in human_roles
    )
    checks.append(
        _check(
            "qa_coverage",
            "QA agent or human",
            has_qa,
            warn=company.status == Company.Status.ACTIVE and not has_qa,
            message="QA role assigned" if has_qa else "Add QA agent or human member",
            owner_hint="QA",
        )
    )

    has_founder_human = CompanyTeamMember.Role.FOUNDER in human_roles
    checks.append(
        _check(
            "human_founders",
            "Human founder(s) on team",
            has_founder_human,
            warn=not has_founder_human,
            message="Founder(s) registered"
            if has_founder_human
            else "Optional: add founders to involve humans",
            owner_hint="Owner",
        )
    )

    discussion_count = DirectorDiscussion.objects.filter(company=company).count()
    checks.append(
        _check(
            "director_discussions",
            "Director discussions started",
            discussion_count > 0,
            message=f"{discussion_count} discussion(s)",
            owner_hint="Directors",
        )
    )

    calendar_count = CompanyCalendarAction.objects.filter(company=company).count()
    checks.append(
        _check(
            "calendar_plan",
            "Actions on company calendar",
            calendar_count > 0,
            warn=discussion_count > 0 and calendar_count == 0,
            message=f"{calendar_count} calendar entry(ies)",
            owner_hint="Planner / Scheduler",
        )
    )

    done_count = CompanyCalendarAction.objects.filter(
        company=company, status=CompanyCalendarAction.ActionStatus.DONE
    ).count()
    checks.append(
        _check(
            "executed_actions",
            "Completed calendar actions (results checked)",
            done_count > 0,
            warn=calendar_count > 0 and done_count == 0,
            message=f"{done_count} completed",
            owner_hint="Operations / Executor",
        )
    )

    selected_count = ActionProposal.objects.filter(
        discussion__company=company,
        status=ActionProposal.ActionStatus.SELECTED,
    ).count()
    checks.append(
        _check(
            "actions_selected",
            "Actions selected from discussions",
            selected_count > 0,
            warn=discussion_count > 0 and selected_count == 0,
            owner_hint="Owner or autonomous selector",
        )
    )

    phase = _infer_phase(checks, company)
    pass_count = sum(1 for c in checks if c.status == "pass")
    warn_count = sum(1 for c in checks if c.status == "warn")
    fail_count = sum(1 for c in checks if c.status == "fail")
    total = len(checks) or 1
    score = int(round(100 * pass_count / total))

    return CompanyReadinessReport(
        company_id=str(company.pk),
        phase=phase,
        checks=tuple(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        score_percent=score,
    )


def _infer_phase(checks: list[PracticeCheck], company: Company) -> Phase:
    by_id = {c.check_id: c.status for c in checks}
    if by_id.get("idea_pipeline") != "pass":
        return "Discovery"
    if by_id.get("development_plan") != "pass" or company.status == Company.Status.INITIALIZING:
        return "Discovery"
    if by_id.get("calendar_plan") != "pass" or by_id.get("director_discussions") != "pass":
        return "Optimization"
    if by_id.get("executed_actions") != "pass" or by_id.get("qa_coverage") == "fail":
        return "Validation"
    if by_id.get("go_no_go_decision") == "pass" and by_id.get("executed_actions") == "pass":
        return "Production"
    return "Validation"
