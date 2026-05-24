"""Calendar slice for LLM context (agents and company assistant)."""
from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone

from apps.ideas.models import Company, CompanyCalendarAction


def get_company_start_date(company: Company) -> date:
    """Date when company was created — calendar context starts from this day."""
    created = company.created_at
    if timezone.is_naive(created):
        return created.date()
    return timezone.localtime(created).date()


def build_calendar_context(company: Company, *, horizon_days: int = 30, max_entries: int = 60) -> str:
    """Build calendar/action context from company start through the near future."""
    start_date = get_company_start_date(company)
    today = timezone.localdate()
    end = today + timedelta(days=horizon_days)
    entries = CompanyCalendarAction.objects.filter(
        company=company, action_date__gte=start_date, action_date__lte=end
    ).order_by("action_date", "title")[:max_entries]
    if not entries:
        return "No calendar actions on record yet."
    lines = [f"Calendar from {start_date} (company start) through {end}:"]
    for entry in entries:
        date_str = entry.action_date.isoformat()
        lines.append(f"- {date_str}: {entry.title} [{entry.get_status_display()}]")
        if entry.description:
            desc = entry.description[:100] + ("..." if len(entry.description) > 100 else "")
            lines.append(f"  {desc}")
        if (
            entry.completion_notes
            and entry.status == CompanyCalendarAction.ActionStatus.DONE
        ):
            notes = entry.completion_notes[:80] + (
                "..." if len(entry.completion_notes) > 80 else ""
            )
            lines.append(f"  Done: {notes}")
    return "\n".join(lines)
