"""Access control helpers for ideas, companies, and permissions."""
from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import Q, QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.ideas.models import Company, CompanyTask, CompanyTeamMember, IdeaRequest


def is_app_admin(user: AbstractBaseUser | AnonymousUser) -> bool:
    """Staff users are application admins (see all data, manage users)."""
    return bool(user.is_authenticated and user.is_staff)


def _profile(user: AbstractBaseUser | AnonymousUser):
    return getattr(user, "profile", None) if user.is_authenticated else None


def user_can_create_ideas(user: AbstractBaseUser | AnonymousUser) -> bool:
    if not user.is_authenticated:
        return False
    if is_app_admin(user):
        return True
    profile = _profile(user)
    if profile is None:
        return True
    return profile.can_create_ideas


def user_can_create_companies(user: AbstractBaseUser | AnonymousUser) -> bool:
    if not user.is_authenticated:
        return False
    if is_app_admin(user):
        return True
    profile = _profile(user)
    if profile is None:
        return True
    return profile.can_create_companies


def team_members_queryset_for_user(
    user: AbstractBaseUser | AnonymousUser,
) -> QuerySet[CompanyTeamMember]:
    if not user.is_authenticated:
        return CompanyTeamMember.objects.none()
    return CompanyTeamMember.objects.filter(user=user, is_active=True).select_related(
        "company"
    )


def user_has_team_memberships(user: AbstractBaseUser | AnonymousUser) -> bool:
    return team_members_queryset_for_user(user).exists()


def is_company_owner(
    user: AbstractBaseUser | AnonymousUser, company: Company
) -> bool:
    return bool(user.is_authenticated and company.owner_id == user.pk)


def user_can_manage_company(
    user: AbstractBaseUser | AnonymousUser, company: Company
) -> bool:
    """Owners and app admins can change company settings, roster, and task assignment."""
    if is_app_admin(user):
        return True
    return is_company_owner(user, company)


def user_is_team_member_only(user: AbstractBaseUser | AnonymousUser) -> bool:
    """
    User accesses companies only via linked team membership (not owner, not staff).
    Used for login redirect and simplified navigation.
    """
    if not user.is_authenticated or is_app_admin(user):
        return False
    if Company.objects.filter(owner=user).exists():
        return False
    return user_has_team_memberships(user)


def ideas_queryset_for_user(user: AbstractBaseUser | AnonymousUser):
    qs = IdeaRequest.objects.all().order_by("-created_at")
    if is_app_admin(user):
        return qs
    return qs.filter(owner=user)


def companies_queryset_for_user(user: AbstractBaseUser | AnonymousUser):
    qs = Company.objects.all().order_by("-created_at")
    if is_app_admin(user):
        return qs
    if not user.is_authenticated:
        return qs.none()
    return qs.filter(
        Q(owner=user)
        | Q(team_members__user=user, team_members__is_active=True)
    ).distinct()


def assigned_tasks_queryset_for_user(
    user: AbstractBaseUser | AnonymousUser,
) -> QuerySet[CompanyTask]:
    """Human tasks assigned to this user's linked team member records."""
    if not user.is_authenticated:
        return CompanyTask.objects.none()
    member_ids = team_members_queryset_for_user(user).values_list("pk", flat=True)
    return (
        CompanyTask.objects.filter(
            assignee_type=CompanyTask.AssigneeType.HUMAN,
            assigned_human_id__in=member_ids,
            company__in=companies_queryset_for_user(user),
        )
        .select_related("company", "assigned_human", "planning_session")
        .order_by("company__name", "sort_order", "created_at")
    )


def get_idea_for_user(user: AbstractBaseUser | AnonymousUser, pk) -> IdeaRequest:
    return get_object_or_404(ideas_queryset_for_user(user), pk=pk)


def get_company_for_user(user: AbstractBaseUser | AnonymousUser, pk) -> Company:
    return get_object_or_404(companies_queryset_for_user(user), pk=pk)


def get_assigned_task_for_user(
    user: AbstractBaseUser | AnonymousUser, company_pk, task_pk
) -> CompanyTask:
    return get_object_or_404(
        assigned_tasks_queryset_for_user(user),
        pk=task_pk,
        company_id=company_pk,
    )


def user_can_update_task(
    user: AbstractBaseUser | AnonymousUser, task: CompanyTask
) -> bool:
    """Update status/progress/results; owners/admins can also reassign."""
    if not user.is_authenticated:
        return False
    if user_can_manage_company(user, task.company):
        return True
    if task.assignee_type != CompanyTask.AssigneeType.HUMAN:
        return False
    human = task.assigned_human
    return bool(human and human.user_id == user.pk)


def user_can_reassign_task(
    user: AbstractBaseUser | AnonymousUser, task: CompanyTask
) -> bool:
    return user_can_manage_company(user, task.company)


def ensure_can_create_ideas(user: AbstractBaseUser | AnonymousUser) -> None:
    if not user_can_create_ideas(user):
        raise Http404


def ensure_can_create_companies(user: AbstractBaseUser | AnonymousUser) -> None:
    if not user_can_create_companies(user):
        raise Http404
