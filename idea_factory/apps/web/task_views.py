"""Views for human-assigned tasks across companies."""
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.core.access import (
    assigned_tasks_queryset_for_user,
    companies_queryset_for_user,
    team_members_queryset_for_user,
)
from apps.ideas.models import CompanyTask


@login_required
@require_http_methods(["GET"])
def my_tasks(request: HttpRequest) -> HttpResponse:
    """Tasks assigned to the logged-in user's linked team member records."""
    status_filter = request.GET.get("status", "").strip()
    qs = assigned_tasks_queryset_for_user(request.user)
    if status_filter and status_filter in dict(CompanyTask.Status.choices):
        qs = qs.filter(status=status_filter)

    memberships = list(team_members_queryset_for_user(request.user))
    companies = companies_queryset_for_user(request.user)[:50]

    return render(
        request,
        "web/my_tasks.html",
        {
            "tasks": list(qs),
            "memberships": memberships,
            "companies": companies,
            "status_filter": status_filter,
            "status_choices": CompanyTask.Status.choices,
        },
    )
