"""Strands @tool wrappers for read-only company assistant context loading."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from django.contrib.auth.models import AbstractBaseUser
from django.db import close_old_connections

from apps.ideas.company_assistant_config import (
    CORE_TOOL_NAMES,
    DEFAULT_TOOL_OUTPUT_MAX_CHARS,
    MAX_TOOL_CONTEXT_CHARS,
    MAX_TOOL_WORKERS,
    TOOL_OUTPUT_MAX_CHARS,
)
from apps.ideas.company_assistant_data import (
    _truncate,
    fetch_asking_user,
    fetch_calendar,
    fetch_company_overview,
    fetch_director_discussions,
    fetch_idea_pipeline_summary,
    fetch_navigation_links,
    fetch_open_tasks,
    fetch_planning_sessions,
    fetch_readiness_report,
    fetch_recent_history,
    fetch_strategic_direction,
    fetch_strategic_planning_snapshot,
    fetch_tasks_for_current_user,
    fetch_team_roster,
)
from apps.ideas.models import Company
from strands import tool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolRunResult:
    name: str
    body: str
    duration_ms: float
    char_count: int
    error: str | None = None


def _budget_for_tool(tool_name: str) -> int:
    return TOOL_OUTPUT_MAX_CHARS.get(tool_name, DEFAULT_TOOL_OUTPUT_MAX_CHARS)


def execute_assistant_tool(
    tool_name: str,
    company: Company,
    user: AbstractBaseUser,
    *,
    status_filter: str = "",
) -> str:
    """Run one read-only context tool by name (Ollama / server-side path)."""
    if tool_name == "get_company_overview":
        return fetch_company_overview(company)
    if tool_name == "get_asking_user":
        return fetch_asking_user(company, user)
    if tool_name == "get_team_roster":
        return fetch_team_roster(company)
    if tool_name == "get_tasks_for_current_user":
        return fetch_tasks_for_current_user(company, user, status_filter=status_filter)
    if tool_name == "get_open_tasks":
        return fetch_open_tasks(company, status_filter=status_filter)
    if tool_name == "get_strategic_direction":
        return fetch_strategic_direction(company)
    if tool_name == "get_planning_sessions":
        return fetch_planning_sessions(company)
    if tool_name == "get_director_discussions":
        return fetch_director_discussions(company)
    if tool_name == "get_calendar":
        return fetch_calendar(company)
    if tool_name == "get_recent_history":
        return fetch_recent_history(company)
    if tool_name == "get_readiness_report":
        return fetch_readiness_report(company)
    if tool_name == "get_strategic_planning_snapshot":
        return fetch_strategic_planning_snapshot(company)
    if tool_name == "get_idea_pipeline_summary":
        return fetch_idea_pipeline_summary(
            company, max_chars=_budget_for_tool(tool_name)
        )
    if tool_name == "get_navigation_links":
        return fetch_navigation_links(company)
    return f"Unknown tool: {tool_name}"


def _run_tool_instrumented(
    tool_name: str,
    company: Company,
    user: AbstractBaseUser,
) -> ToolRunResult:
    """Execute one tool in a worker thread (closes DB connections per Django guidance)."""
    close_old_connections()
    started = time.perf_counter()
    try:
        raw = execute_assistant_tool(tool_name, company, user)
        budget = _budget_for_tool(tool_name)
        body = _truncate(raw, budget)
        duration_ms = (time.perf_counter() - started) * 1000
        return ToolRunResult(
            name=tool_name,
            body=body,
            duration_ms=duration_ms,
            char_count=len(body),
        )
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        logger.exception(
            "company_assistant tool failed company=%s tool=%s",
            company.pk,
            tool_name,
        )
        return ToolRunResult(
            name=tool_name,
            body=f"(tool error: {type(exc).__name__})",
            duration_ms=duration_ms,
            char_count=0,
            error=str(exc),
        )
    finally:
        close_old_connections()


def _dedupe_preserve_order(names: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _refine_tool_selection(question: str, selected: list[str]) -> list[str]:
    """Drop redundant heavy tools when a lighter tool already covers the topic."""
    q = question.lower()
    names = list(selected)

    if (
        "get_strategic_planning_snapshot" in names
        and "get_strategic_direction" in names
        and not any(w in q for w in ("direction page", "founder-verified", "statement"))
    ):
        names.remove("get_strategic_direction")

    if "get_company_overview" in names and "get_readiness_report" in names:
        if not any(w in q for w in ("readiness", "phase", "checklist", "best practice")):
            names.remove("get_readiness_report")

    return names


def select_tools_for_question(question: str) -> list[str]:
    """
    Choose which context tools to run server-side before the LLM call.

    Core tools always run; additional tools match keywords; vague questions get a
    small default slice (not the full workspace dump).
    """
    q = question.lower()
    selected: list[str] = list(CORE_TOOL_NAMES)

    task_words = (
        "task",
        "assigned",
        "blocked",
        "todo",
        "to-do",
        "my work",
        "do i have",
        "any tasks",
    )
    if any(w in q for w in task_words):
        selected.extend(["get_tasks_for_current_user", "get_open_tasks"])

    team_words = ("team", "member", "who is", "agent", "fleet", "assignee", "human")
    if any(w in q for w in team_words):
        selected.append("get_team_roster")

    if any(w in q for w in ("calendar", "schedule", "overdue", "due", "this week")):
        selected.append("get_calendar")

    if any(
        w in q
        for w in (
            "discussion",
            "director",
            "recommend",
            "proposal",
            "action",
            "approve",
            "select",
        )
    ):
        selected.append("get_director_discussions")

    if any(w in q for w in ("plan", "planning", "weekly", "session", "milestone")):
        selected.extend(["get_planning_sessions", "get_strategic_planning_snapshot"])

    if any(w in q for w in ("direction", "strategy", "strategic", "founder")):
        selected.append("get_strategic_direction")

    if any(w in q for w in ("history", "audit", "what happened", "recent")):
        selected.append("get_recent_history")

    if any(
        w in q
        for w in (
            "readiness",
            "going on",
            "overview",
            "summary",
            "state",
            "attention",
            "priority",
        )
    ):
        selected.append("get_readiness_report")
    elif any(w in q for w in ("status",)):
        selected.extend(["get_open_tasks", "get_readiness_report"])

    if any(w in q for w in ("idea", "pipeline", "go/no-go", "go no go", "kpi", "mvp")):
        selected.append("get_idea_pipeline_summary")

    if any(
        w in q
        for w in (
            "fix",
            "address",
            "resolve",
            "readiness",
            "fail",
            "failed",
            "development plan",
            "remediate",
        )
    ):
        selected.append("get_readiness_report")
        if "get_idea_pipeline_summary" not in selected:
            selected.append("get_idea_pipeline_summary")

    # Vague / broad question: small extra slice (avoid calendar + discussions + planning dump).
    if len(selected) == len(CORE_TOOL_NAMES):
        selected.extend(["get_open_tasks", "get_readiness_report"])

    selected = _refine_tool_selection(question, selected)
    return _dedupe_preserve_order(selected)


def execute_assistant_tools(
    company: Company,
    user: AbstractBaseUser,
    tool_names: list[str],
) -> str:
    """Run tools in parallel, apply per-tool budgets, merge for the LLM prompt."""
    tool_names = _dedupe_preserve_order(tool_names)
    if not tool_names:
        return ""

    workers = min(MAX_TOOL_WORKERS, len(tool_names))
    results_by_name: dict[str, ToolRunResult] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_run_tool_instrumented, name, company, user): name
            for name in tool_names
        }
        for future in as_completed(futures):
            name = futures[future]
            results_by_name[name] = future.result()

    durations = {
        name: round(results_by_name[name].duration_ms, 1) for name in tool_names
    }
    total_chars = sum(results_by_name[n].char_count for n in tool_names)
    errors = [n for n in tool_names if results_by_name[n].error]
    logger.info(
        "company_assistant tools company=%s user=%s tools=%s total_chars=%s "
        "durations_ms=%s errors=%s",
        company.pk,
        user.pk,
        tool_names,
        total_chars,
        durations,
        errors or None,
    )

    sections: list[str] = []
    merged_len = 0
    for name in tool_names:
        result = results_by_name[name]
        section = f"### {name}\n{result.body}"
        if merged_len + len(section) > MAX_TOOL_CONTEXT_CHARS:
            sections.append("...[remaining tool sections omitted — use data above]")
            break
        sections.append(section)
        merged_len += len(section) + 2

    text = "\n\n".join(sections)
    if len(text) > MAX_TOOL_CONTEXT_CHARS:
        return (
            text[:MAX_TOOL_CONTEXT_CHARS]
            + "\n\n...[tool context truncated; answer from available data only]"
        )
    return text


def create_company_assistant_tools(
    company: Company,
    user: AbstractBaseUser,
) -> list:
    """Build strands tools bound to this company and user (read-only)."""

    @tool
    def get_company_overview() -> str:
        """
        Company status, progress counts, GO/NO-GO, executive summary,
        discussions awaiting selection, and unscheduled actions.
        """
        return fetch_company_overview(company)

    @tool
    def get_asking_user() -> str:
        """Who is asking (owner vs team member) — use before answering 'my tasks'."""
        return fetch_asking_user(company, user)

    @tool
    def get_team_roster() -> str:
        """Human team members and AI agents (who can be assigned work)."""
        return fetch_team_roster(company)

    @tool
    def get_tasks_for_current_user(status_filter: str = "") -> str:
        """
        Tasks assigned to the human asking (not the full company board).
        status_filter: optional TODO, IN_PROGRESS, BLOCKED, DONE, or empty for all.
        """
        return fetch_tasks_for_current_user(company, user, status_filter=status_filter)

    @tool
    def get_open_tasks(status_filter: str = "") -> str:
        """
        Company task board (open work by default).
        status_filter: optional status or empty for TODO/IN_PROGRESS/BLOCKED.
        """
        return fetch_open_tasks(company, status_filter=status_filter)

    @tool
    def get_strategic_direction() -> str:
        """Active strategic direction statement and verification status."""
        return fetch_strategic_direction(company)

    @tool
    def get_planning_sessions() -> str:
        """Recent planning sessions with summaries and links."""
        return fetch_planning_sessions(company)

    @tool
    def get_director_discussions() -> str:
        """Director discussions and action proposals (recommendations)."""
        return fetch_director_discussions(company)

    @tool
    def get_calendar() -> str:
        """Calendar actions from company start through the next ~30 days."""
        return fetch_calendar(company)

    @tool
    def get_recent_history() -> str:
        """Audit trail: direction, planning, tasks, escalations (recent)."""
        return fetch_recent_history(company)

    @tool
    def get_readiness_report() -> str:
        """Best-practice readiness checks and phase (Discovery / Validation / etc.)."""
        return fetch_readiness_report(company)

    @tool
    def get_strategic_planning_snapshot() -> str:
        """High-level planning context: direction, milestones, open/done task summaries."""
        return fetch_strategic_planning_snapshot(company)

    @tool
    def get_idea_pipeline_summary() -> str:
        """Original idea request and pipeline outputs (may be long)."""
        return fetch_idea_pipeline_summary(company)

    @tool
    def get_navigation_links() -> str:
        """Workspace URLs for markdown links in your answer."""
        return fetch_navigation_links(company)

    return [
        get_company_overview,
        get_asking_user,
        get_team_roster,
        get_tasks_for_current_user,
        get_open_tasks,
        get_strategic_direction,
        get_planning_sessions,
        get_director_discussions,
        get_calendar,
        get_recent_history,
        get_readiness_report,
        get_strategic_planning_snapshot,
        get_idea_pipeline_summary,
        get_navigation_links,
    ]


ALL_ASSISTANT_TOOL_NAMES = [
    "get_company_overview",
    "get_asking_user",
    "get_team_roster",
    "get_tasks_for_current_user",
    "get_open_tasks",
    "get_strategic_direction",
    "get_planning_sessions",
    "get_director_discussions",
    "get_calendar",
    "get_recent_history",
    "get_readiness_report",
    "get_strategic_planning_snapshot",
    "get_idea_pipeline_summary",
    "get_navigation_links",
]
