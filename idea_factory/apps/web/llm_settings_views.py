"""Service LLM configuration UI (staff)."""
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.agents.llm_settings import get_llm_settings_for_assistant, get_service_llm_settings
from apps.agents.providers import get_model, validate_provider_config
from apps.core.forms import ServiceLLMConfigForm
from apps.core.models import ServiceLLMConfig
from apps.web.views import OLLAMA_MODELS, OPENAI_MODELS


def _staff_required(user) -> bool:
    return user.is_authenticated and user.is_staff


@login_required
@user_passes_test(_staff_required)
@require_http_methods(["GET", "POST"])
def llm_settings(request: HttpRequest) -> HttpResponse:
    """Configure default LLM provider for the service (OpenAI or Ollama)."""
    config = ServiceLLMConfig.load()
    if request.method == "POST":
        form = ServiceLLMConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"LLM settings saved. Assistant uses {config.resolved_assistant_provider()} "
                f"({config.resolved_assistant_model_id()}).",
            )
            return redirect("llm_settings")
        messages.error(request, "Could not save LLM settings. Fix the errors below and try again.")
    else:
        form = ServiceLLMConfigForm(instance=config)

    active = get_service_llm_settings()
    assistant_active = get_llm_settings_for_assistant()
    provider_error = validate_provider_config()
    assistant_error = validate_provider_config(assistant_active.provider)
    openai_key_set = bool(os.environ.get("OPENAI_API_KEY"))

    return render(
        request,
        "web/llm_settings.html",
        {
            "form": form,
            "config": config,
            "active_settings": active,
            "assistant_settings": assistant_active,
            "provider_error": provider_error,
            "assistant_error": assistant_error,
            "openai_key_set": openai_key_set,
            "ollama_models": OLLAMA_MODELS,
            "openai_models": OPENAI_MODELS,
        },
    )


@login_required
@user_passes_test(_staff_required)
@require_POST
def llm_settings_test(request: HttpRequest) -> HttpResponse:
    """Test connection to saved service or Assistant LLM (see POST target)."""
    from apps.agents.llm_settings import validate_llm_settings

    target = (request.POST.get("target") or "service").strip().lower()
    if target == "assistant":
        settings = get_llm_settings_for_assistant()
        label = "Assistant"
    else:
        settings = get_service_llm_settings()
        label = "Service"
    err = validate_llm_settings(settings)
    if err:
        return JsonResponse({"ok": False, "message": f"{label}: {err}"})
    try:
        get_model(settings)
        return JsonResponse(
            {
                "ok": True,
                "message": (
                    f"{label}: connected to {settings.provider} "
                    f"({settings.model_id_for_provider()})"
                ),
            }
        )
    except Exception as e:
        return JsonResponse({"ok": False, "message": f"{label}: {e}"})
