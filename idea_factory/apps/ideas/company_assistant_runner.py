"""Run company assistant: tool calls populate context, then structured answer."""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser

from apps.agents.agents import _run_structured_output_direct
from apps.agents.llm_settings import get_llm_settings_for_assistant, validate_llm_settings
from apps.agents.providers import get_model_for_assistant
from apps.agents.schemas import ChatResponse
from apps.core.public_urls import public_site_base
from apps.ideas.company_assistant_context import COMPANY_ASSISTANT_SYSTEM
from apps.ideas.company_assistant_tools import (
    execute_assistant_tools,
    select_tools_for_question,
)
from apps.ideas.models import Company

logger = logging.getLogger(__name__)

_ASSISTANT_ERROR_USER_MESSAGE = (
    "Sorry, I could not generate an answer right now. "
    "Check LLM settings or try again in a moment."
)


def _bootstrap_context(company: Company) -> str:
    """Minimal metadata only — entity data comes from parallel tool calls (no duplication)."""
    parts = [f"Company id: {company.pk}"]
    base = public_site_base()
    if base:
        parts.append(f"Public site base URL for links: {base}")
    return "\n\n".join(parts)


def _system_prompt(*, has_history: bool) -> str:
    prompt = (
        COMPANY_ASSISTANT_SYSTEM
        + "\n\nContext is loaded via read-only tools (already run server-side). "
        "Answer using the tool results below — do not invent data."
    )
    if has_history:
        prompt += (
            "\n\nThe user is continuing an existing thread. "
            "Use the prior conversation for follow-up context."
        )
    return prompt


def _user_facing_error(exc: BaseException, *, provider: str) -> str:
    text = str(exc).lower()
    if "connection" in text or "connect" in text or "refused" in text:
        if provider == "ollama":
            return (
                "Cannot reach Ollama. Check that Ollama is running and OLLAMA_HOST "
                "is reachable from the app server (LLM settings)."
            )
        return (
            "Cannot reach the OpenAI API. Check OPENAI_API_KEY and network access "
            "(LLM settings)."
        )
    if "timeout" in text or "timed out" in text:
        return "The LLM request timed out. Try a shorter question or try again."
    if (
        "rate limit" in text
        or "429" in text
        or "throttl" in text
        or type(exc).__name__ == "ModelThrottledException"
    ):
        return (
            "OpenAI rate limit reached for this API key. "
            "Wait a minute and try again, or switch the Assistant to Ollama in LLM settings."
        )
    if settings.DEBUG:
        return f"{_ASSISTANT_ERROR_USER_MESSAGE} ({type(exc).__name__}: {exc})"
    return _ASSISTANT_ERROR_USER_MESSAGE


def run_company_assistant_response(
    company: Company,
    user: AbstractBaseUser,
    user_content: str,
    *,
    conversation_history: str = "",
) -> str:
    """
    Answer using server-side tool gathering, then one structured LLM call.

    Works for both Ollama and OpenAI (native tool-calling + structured output is unreliable).
    """
    llm_cfg = get_llm_settings_for_assistant(company.idea_request)
    config_err = validate_llm_settings(llm_cfg)
    if config_err:
        return f"Unable to connect to AI. {config_err}"

    model = get_model_for_assistant(company.idea_request)
    if model is None:
        return "Unable to connect to AI. Check provider configuration in LLM settings."

    system = _system_prompt(has_history=bool(conversation_history))
    bootstrap = _bootstrap_context(company)
    history_block = f"\n\n{conversation_history}\n\n" if conversation_history else "\n\n"

    try:
        tool_names = select_tools_for_question(user_content)
        gathered = execute_assistant_tools(company, user, tool_names)
        logger.info(
            "company_assistant prompt company=%s tools=%s context_chars=%s history_chars=%s",
            company.pk,
            tool_names,
            len(gathered),
            len(conversation_history),
        )
        user_prompt = (
            f"{bootstrap}"
            f"{history_block}"
            f"--- Tool results (use only this data) ---\n{gathered}\n\n"
            f"Current user question: {user_content}"
        )
        out, _ = _run_structured_output_direct(
            model,
            "company_assistant",
            system,
            user_prompt,
            ChatResponse,
        )

        if out and hasattr(out, "response"):
            return out.response or "No response generated."
        return str(out) if out else "No response generated."
    except Exception as exc:
        logger.exception("Company assistant failed for company %s", company.pk)
        return _user_facing_error(exc, provider=llm_cfg.provider)
