"""Google Calendar integration settings for company owners."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.forms import GoogleCalendarSettingsForm
from apps.core.google_calendar import (
    build_oauth_authorization_url,
    clear_google_calendar_credentials,
    default_reminder_minutes,
    exchange_code_for_tokens,
    is_google_calendar_configured,
    profile_has_google_credentials,
    save_tokens_to_profile,
)
from apps.core.models import UserProfile


def _get_profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@login_required
@require_http_methods(["GET", "POST"])
def google_calendar_settings(request: HttpRequest) -> HttpResponse:
    """Connect Google Calendar and configure reminders for scheduled company actions."""
    profile = _get_profile(request.user)
    configured = is_google_calendar_configured()
    connected = profile_has_google_credentials(profile)

    if request.method == "POST":
        form = GoogleCalendarSettingsForm(request.POST, instance=profile)
        if form.is_valid():
            saved = form.save(commit=False)
            if not connected:
                saved.google_calendar_sync_enabled = False
            saved.save()
            messages.success(request, "Google Calendar preferences saved.")
            return redirect("google_calendar_settings")
    else:
        if not profile.google_calendar_reminder_minutes:
            profile.google_calendar_reminder_minutes = ",".join(
                str(m) for m in default_reminder_minutes()
            )
        form = GoogleCalendarSettingsForm(instance=profile)

    return render(
        request,
        "web/google_calendar_settings.html",
        {
            "form": form,
            "configured": configured,
            "connected": connected,
            "connected_at": profile.google_calendar_connected_at,
            "default_reminders": default_reminder_minutes(),
        },
    )


@login_required
@require_http_methods(["GET"])
def google_calendar_connect(request: HttpRequest) -> HttpResponse:
    if not is_google_calendar_configured():
        messages.error(
            request,
            "Google Calendar is not configured on this server. Ask an administrator to set "
            "GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET.",
        )
        return redirect("google_calendar_settings")
    return redirect(build_oauth_authorization_url(request))


@login_required
@require_http_methods(["GET"])
def google_calendar_callback(request: HttpRequest) -> HttpResponse:
    error = request.GET.get("error")
    if error:
        messages.error(request, f"Google sign-in was cancelled or failed: {error}")
        return redirect("google_calendar_settings")

    code = request.GET.get("code", "").strip()
    if not code:
        messages.error(request, "No authorization code received from Google.")
        return redirect("google_calendar_settings")

    try:
        token_payload = exchange_code_for_tokens(request, code)
    except Exception:
        messages.error(
            request,
            "Could not complete Google sign-in. Check server credentials and redirect URI.",
        )
        return redirect("google_calendar_settings")

    profile = _get_profile(request.user)
    save_tokens_to_profile(profile, token_payload)
    messages.success(
        request,
        "Google Calendar connected. New and updated company calendar actions will sync "
        "to your calendar with reminders.",
    )
    return redirect("google_calendar_settings")


@login_required
@require_POST
def google_calendar_disconnect(request: HttpRequest) -> HttpResponse:
    profile = _get_profile(request.user)
    clear_google_calendar_credentials(profile)
    messages.success(request, "Google Calendar disconnected.")
    return redirect("google_calendar_settings")
