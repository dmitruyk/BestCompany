"""Template context for access flags."""
from apps.core.access import (
    is_app_admin,
    user_can_create_companies,
    user_can_create_ideas,
)


def user_access(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    return {
        "is_app_admin": is_app_admin(user),
        "can_create_ideas": user_can_create_ideas(user),
        "can_create_companies": user_can_create_companies(user),
    }
