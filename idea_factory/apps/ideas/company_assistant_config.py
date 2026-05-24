"""Token budgets and tool tiers for the company assistant."""
from __future__ import annotations

# Always loaded for every question (small, high-signal).
CORE_TOOL_NAMES: tuple[str, ...] = (
    "get_company_overview",
    "get_asking_user",
    "get_navigation_links",
)

# Large dumps — only when the question clearly needs them.
HEAVY_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "get_idea_pipeline_summary",
        "get_strategic_planning_snapshot",
    }
)

# Per-tool output caps before merge (chars). Default applies when not listed.
DEFAULT_TOOL_OUTPUT_MAX_CHARS = 2_500

TOOL_OUTPUT_MAX_CHARS: dict[str, int] = {
    "get_company_overview": 1_200,
    "get_asking_user": 400,
    "get_navigation_links": 800,
    "get_tasks_for_current_user": 3_000,
    "get_open_tasks": 4_000,
    "get_team_roster": 1_500,
    "get_strategic_direction": 2_000,
    "get_planning_sessions": 2_500,
    "get_director_discussions": 3_500,
    "get_calendar": 3_000,
    "get_recent_history": 3_000,
    "get_readiness_report": 2_000,
    "get_strategic_planning_snapshot": 4_000,
    "get_idea_pipeline_summary": 6_000,
}

# Total merged tool context sent to the LLM.
MAX_TOOL_CONTEXT_CHARS = 36_000

# Parallel DB reads (I/O-bound); cap workers to avoid connection storms.
MAX_TOOL_WORKERS = 6
