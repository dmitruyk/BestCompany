"""Service LLM configuration UI (staff)."""
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.agents.llm_settings import get_service_llm_settings
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
                f"LLM provider updated to {config.get_default_provider_display()}. "
                "New idea runs use these defaults.",
            )
            return redirect("llm_settings")
    else:
        form = ServiceLLMConfigForm(instance=config)

    active = get_service_llm_settings()
    provider_error = validate_provider_config()
    openai_key_set = bool(os.environ.get("OPENAI_API_KEY"))

    return render(
        request,
        "web/llm_settings.html",
        {
            "form": form,
            "config": config,
            "active_settings": active,
            "provider_error": provider_error,
            "openai_key_set": openai_key_set,
            "ollama_models": OLLAMA_MODELS,
            "openai_models": OPENAI_MODELS,
        },
    )


@login_required
@user_passes_test(_staff_required)
@require_POST
def llm_settings_test(request: HttpRequest) -> HttpResponse:
    """Test connection to the currently saved service LLM provider."""
    provider = request.POST.get("provider") or ServiceLLMConfig.load().default_provider
    err = validate_provider_config(provider)
    if err:
        return JsonResponse({"ok": False, "message": err})
    try:
        from apps.agents.llm_settings import LLMSettings, normalize_provider
        from apps.core.models import ServiceLLMConfig

        cfg_row = ServiceLLMConfig.load()
        settings = LLMSettings(
            provider=normalize_provider(provider),
            ollama_host=cfg_row.ollama_host,
            ollama_model_id=cfg_row.ollama_model_id,
            openai_model_id=cfg_row.openai_model_id,
        )
        get_model(settings)
        return JsonResponse(
            {
                "ok": True,
                "message": f"Connected to {settings.provider} ({settings.model_id_for_provider()})",
            }
        )
    except Exception as e:
        return JsonResponse({"ok": False, "message": str(e)})
