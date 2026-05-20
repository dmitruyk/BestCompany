"""Access control helpers for ideas, companies, and permissions."""
from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.ideas.models import Company, IdeaRequest


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


def ideas_queryset_for_user(user: AbstractBaseUser | AnonymousUser):
    qs = IdeaRequest.objects.all().order_by("-created_at")
    if is_app_admin(user):
        return qs
    return qs.filter(owner=user)


def companies_queryset_for_user(user: AbstractBaseUser | AnonymousUser):
    qs = Company.objects.all().order_by("-created_at")
    if is_app_admin(user):
        return qs
    return qs.filter(owner=user)


def get_idea_for_user(user: AbstractBaseUser | AnonymousUser, pk) -> IdeaRequest:
    return get_object_or_404(ideas_queryset_for_user(user), pk=pk)


def get_company_for_user(user: AbstractBaseUser | AnonymousUser, pk) -> Company:
    return get_object_or_404(companies_queryset_for_user(user), pk=pk)


def ensure_can_create_ideas(user: AbstractBaseUser | AnonymousUser) -> None:
    if not user_can_create_ideas(user):
        raise Http404


def ensure_can_create_companies(user: AbstractBaseUser | AnonymousUser) -> None:
    if not user_can_create_companies(user):
        raise Http404
