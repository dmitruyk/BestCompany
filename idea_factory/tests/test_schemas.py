"""Tests for Pydantic output schemas."""
import pytest

from apps.agents.schemas import (
    CritiqueOutput,
    EstimateOutput,
    IdeaItem,
    IdeaSetOutput,
    OverviewOutput,
)


def test_idea_item_valid() -> None:
    """IdeaItem validates correctly."""
    item = IdeaItem(
        name="Test Idea",
        description="A test",
        target_users="Developers",
        differentiation="Unique",
        feasibility_score=0.8,
    )
    assert item.name == "Test Idea"
    assert item.feasibility_score == 0.8


def test_idea_set_output_valid() -> None:
    """IdeaSetOutput validates with ideas and top_3_indices."""
    output = IdeaSetOutput(
        ideas=[
            IdeaItem(
                name=f"Idea {i}",
                description="",
                target_users="",
                differentiation="",
                feasibility_score=0.5,
            )
            for i in range(5)
        ],
        top_3_indices=[0, 1, 2],
        target_users_summary="Developers",
        differentiation_summary="Tech",
        confidence=0.7,
    )
    assert len(output.ideas) == 5
    assert output.top_3_indices == [0, 1, 2]
    assert output.confidence == 0.7


def test_estimate_output_valid() -> None:
    """EstimateOutput validates."""
    output = EstimateOutput(
        cost_range_min_usd=1000,
        cost_range_max_usd=5000,
        timeline_weeks=12,
        risks=["Market risk"],
        assumptions=[],
        mvp_plan_summary="Phase 1...",
        kpis=["MRR"],
        confidence=0.75,
    )
    assert output.cost_range_min_usd == 1000
    assert output.confidence == 0.75


def test_critique_output_valid() -> None:
    """CritiqueOutput validates."""
    output = CritiqueOutput(
        weak_points=["A"],
        failure_modes=["B"],
        missing_assumptions=["C"],
        legal_ops_risks=[],
        improvements=["D"],
        confidence=0.6,
    )
    assert output.confidence == 0.6


def test_overview_output_valid() -> None:
    """OverviewOutput validates."""
    output = OverviewOutput(
        executive_summary="Summary",
        go_no_go="GO",
        key_metrics=["Metric"],
        confidence=0.8,
    )
    assert output.go_no_go == "GO"
