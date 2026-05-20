"""Authentication views for human users."""
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.core.forms import AppLoginForm, ForcePasswordChangeForm


def _redirect_after_login(user) -> str:
    if getattr(user, "profile", None) and user.profile.must_change_password:
        return reverse("force_password_change")
    return reverse("home")


@require_http_methods(["GET", "POST"])
def app_login(request: HttpRequest) -> HttpResponse:
    """Log in to Idea Factory (main app, not Django admin)."""
    if request.user.is_authenticated:
        return redirect(_redirect_after_login(request.user))

    form = AppLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, f"Welcome, {user.username}.")
        return redirect(_redirect_after_login(user))

    return render(request, "web/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def app_logout(request: HttpRequest) -> HttpResponse:
    """Log out."""
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("app_login")


@login_required
@require_http_methods(["GET", "POST"])
def force_password_change(request: HttpRequest) -> HttpResponse:
    """Required password change before using the service."""
    profile = request.user.profile
    if not profile.must_change_password:
        return redirect("home")

    form = ForcePasswordChangeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["new_password1"])
        request.user.save(update_fields=["password"])
        profile.must_change_password = False
        profile.save(update_fields=["must_change_password", "updated_at"])
        login(request, request.user)
        messages.success(request, "Password updated. You can now use Idea Factory.")
        return redirect("home")

    return render(
        request,
        "web/force_password_change.html",
        {"form": form, "username": request.user.username},
    )
