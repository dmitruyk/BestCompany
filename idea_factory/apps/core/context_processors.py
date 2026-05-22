"""Template context for access flags."""
from apps.core.access import (
    is_app_admin,
    user_can_create_companies,
    user_can_create_ideas,
    user_has_team_memberships,
    user_is_team_member_only,
)


def user_access(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    return {
        "is_app_admin": is_app_admin(user),
        "can_create_ideas": user_can_create_ideas(user),
        "can_create_companies": user_can_create_companies(user),
        "has_team_memberships": user_has_team_memberships(user),
        "is_team_member_only": user_is_team_member_only(user),
    }
