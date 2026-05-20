"""Extract development plan artifacts from idea pipeline conclusions."""
from __future__ import annotations

import json
from typing import Any

from apps.ideas.models import IdeaRequest


def get_conclusion_data(idea_request: IdeaRequest) -> dict[str, Any]:
    """Parse conclusion result_json, or empty dict."""
    if not hasattr(idea_request, "conclusion"):
        return {}
    try:
        return json.loads(idea_request.conclusion.result_json)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {}


def get_development_plan_summary(idea_request: IdeaRequest) -> dict[str, Any]:
    """
    Return milestones, backlog, KPIs, and go/no-go from pipeline outputs.
    Keys: milestones, mvp_backlog, kpis, go_no_go, executive_summary, has_plan.
    """
    data = get_conclusion_data(idea_request)
    outputs = data.get("agent_outputs") or data
    executor = outputs.get("executor") or {}
    estimator = outputs.get("estimator") or {}
    overview = outputs.get("overviewer") or {}

    milestones = list(executor.get("milestones") or [])
    mvp_backlog = list(executor.get("mvp_backlog") or [])
    if not milestones and estimator.get("mvp_plan_summary"):
        milestones = [estimator["mvp_plan_summary"]]

    kpis = list(estimator.get("kpis") or overview.get("key_metrics") or [])
    go_no_go = (overview.get("go_no_go") or "").strip()
    executive_summary = (overview.get("executive_summary") or data.get("final_summary") or "").strip()

    has_plan = bool(milestones or mvp_backlog or estimator.get("mvp_plan_summary"))
    return {
        "milestones": milestones,
        "mvp_backlog": mvp_backlog,
        "kpis": kpis,
        "go_no_go": go_no_go,
        "executive_summary": executive_summary,
        "has_plan": has_plan,
    }
