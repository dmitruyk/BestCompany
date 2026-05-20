"""Record compact company history entries."""
from __future__ import annotations

import json
from typing import Any

from apps.ideas.models import (
    Company,
    CompanyHistoryEntry,
    CompanyTask,
    PlanningSession,
)


def record_history(
    company: Company,
    entry_type: str,
    title: str,
    summary: str = "",
    *,
    related_task: CompanyTask | None = None,
    related_planning_session: PlanningSession | None = None,
    metadata: dict[str, Any] | None = None,
) -> CompanyHistoryEntry:
    return CompanyHistoryEntry.objects.create(
        company=company,
        entry_type=entry_type,
        title=title,
        summary=summary[:2000] if summary else "",
        related_task=related_task,
        related_planning_session=related_planning_session,
        metadata_json=json.dumps(metadata or {}),
    )
