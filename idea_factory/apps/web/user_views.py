"""Staff-only user management in the main web UI."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.access import is_app_admin
from apps.core.forms import AppUserCreationForm, AppUserEditForm
from apps.core.models import UserProfile

User = get_user_model()


def _staff_required(view_func):
    @login_required
    @user_passes_test(is_app_admin)
    def wrapped(request: HttpRequest, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return wrapped


@_staff_required
@require_http_methods(["GET"])
def user_list(request: HttpRequest) -> HttpResponse:
    users = (
        User.objects.select_related("profile")
        .prefetch_related("team_memberships__company")
        .order_by("username")
        .all()
    )
    return render(request, "web/user_list.html", {"users": users})


@_staff_required
@require_http_methods(["GET", "POST"])
def user_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = AppUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                f"Created user “{user.username}”. They must change their password on first login.",
            )
            return redirect("user_list")
    else:
        form = AppUserCreationForm()
    return render(request, "web/user_form.html", {"form": form, "is_create": True})


@_staff_required
@require_http_methods(["GET", "POST"])
def user_edit(request: HttpRequest, user_id: int) -> HttpResponse:
    user = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
    UserProfile.objects.get_or_create(user=user)
    if request.method == "POST":
        form = AppUserEditForm(request.POST, user=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated user “{user.username}”.")
            return redirect("user_list")
    else:
        form = AppUserEditForm(user=user)
    return render(
        request,
        "web/user_form.html",
        {"form": form, "is_create": False, "edit_user": user},
    )
