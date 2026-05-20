"""Tests for development plan extraction from conclusions."""
import json

import pytest

from apps.ideas.development_plan import get_development_plan_summary
from apps.ideas.models import IdeaConclusion, IdeaRequest


@pytest.mark.django_db
def test_development_plan_from_conclusion(idea_request) -> None:
    IdeaConclusion.objects.create(
        idea_request=idea_request,
        final_summary="Summary",
        result_json=json.dumps(
            {
                "agent_outputs": {
                    "executor": {"milestones": ["M1", "M2"], "mvp_backlog": ["A"]},
                    "estimator": {"kpis": ["KPI1"]},
                    "overviewer": {"go_no_go": "GO", "executive_summary": "Go ahead"},
                }
            }
        ),
    )
    plan = get_development_plan_summary(idea_request)
    assert plan["has_plan"] is True
    assert len(plan["milestones"]) == 2
    assert plan["go_no_go"] == "GO"
    assert "KPI1" in plan["kpis"]


@pytest.mark.django_db
def test_development_plan_empty_without_conclusion(idea_request) -> None:
    plan = get_development_plan_summary(idea_request)
    assert plan["has_plan"] is False
    assert plan["milestones"] == []
