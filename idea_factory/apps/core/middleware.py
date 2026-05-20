"""Middleware for access control."""
from django.shortcuts import redirect
from django.urls import reverse


class MustChangePasswordMiddleware:
    """
    Redirect authenticated users who must change password before using the app.
    """

    EXEMPT_PATH_PREFIXES = (
        "/login",
        "/logout",
        "/password-change-required",
        "/admin/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and self._user_must_change_password(request.user):
            path = request.path
            if not any(path.startswith(prefix) for prefix in self.EXEMPT_PATH_PREFIXES):
                return redirect(reverse("force_password_change"))
        return self.get_response(request)

    @staticmethod
    def _user_must_change_password(user) -> bool:
        profile = getattr(user, "profile", None)
        if profile is None:
            return False
        return profile.must_change_password
