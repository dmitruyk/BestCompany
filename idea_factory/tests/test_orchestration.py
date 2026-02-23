"""Orchestration smoke test with mocked model."""
from unittest.mock import patch

import pytest

from apps.ideas.models import IdeaRequest


@pytest.mark.django_db
def test_run_pipeline_with_mock_fails_gracefully() -> None:
    """Pipeline handles provider errors without crashing."""
    from apps.agents.orchestration import run_pipeline

    idea = IdeaRequest.objects.create(
        title="Test",
        prompt="Test prompt",
        status=IdeaRequest.Status.PENDING,
        provider="openai",
    )
    with patch("apps.agents.orchestration.get_model") as mock_get:
        mock_get.side_effect = ValueError("OPENAI_API_KEY required")
        run_pipeline(idea)
    idea.refresh_from_db()
    assert idea.status == IdeaRequest.Status.FAILED
