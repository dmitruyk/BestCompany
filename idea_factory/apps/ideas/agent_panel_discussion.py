"""Run multi-agent panel discussions — selected fleet agents debate an owner question."""
from __future__ import annotations

import logging

from apps.ideas.calendar_context import build_calendar_context
from apps.ideas.context import build_idea_request_prompt
from apps.ideas.models import AgentPanelDiscussion, AgentPanelMessage, CompanyAgent

logger = logging.getLogger(__name__)


def _get_provider_model_for_company(company):
    from apps.agents.providers import get_model_for_idea, validate_provider_config

    idea = company.idea_request
    if validate_provider_config(idea.provider):
        return None
    return get_model_for_idea(idea)


def _participant_agents(discussion: AgentPanelDiscussion) -> list[CompanyAgent]:
    return [
        p.agent
        for p in discussion.participants.select_related("agent").order_by(
            "sort_order", "agent__name"
        )
    ]


def _participant_names(agents: list[CompanyAgent]) -> str:
    return ", ".join(f"{a.name} ({a.get_role_display()})" for a in agents)


def run_agent_panel_discussion(discussion: AgentPanelDiscussion) -> None:
    """Each selected agent speaks in order; then a moderator synthesizes a recommendation."""
    from apps.agents.agents import _run_agent
    from apps.agents.schemas import AgentPanelContributionOutput, AgentPanelSynthesisOutput

    discussion.refresh_from_db()
    if discussion.cancelled:
        logger.info("Agent panel %s cancelled before start", discussion.pk)
        return

    agents = _participant_agents(discussion)
    if len(agents) < 2:
        discussion.status = AgentPanelDiscussion.Status.FAILED
        discussion.save(update_fields=["status", "updated_at"])
        logger.warning(
            "Agent panel %s needs at least 2 agents, got %s",
            discussion.pk,
            len(agents),
        )
        return

    company = discussion.company
    model = _get_provider_model_for_company(company)
    if model is None:
        discussion.status = AgentPanelDiscussion.Status.FAILED
        discussion.save(update_fields=["status", "updated_at"])
        logger.error("Provider setup failed for agent panel %s", discussion.pk)
        return

    try:
        idea = company.idea_request
        calendar_ctx = build_calendar_context(company)
        base_context = (
            f"Company: {company.name}\n"
            f"Owner question:\n{discussion.question.strip()}\n\n"
            f"Idea:\n{build_idea_request_prompt(idea)}\n\n"
            f"{calendar_ctx}\n\n"
            f"Panel participants: {_participant_names(agents)}\n"
        )
        prior_messages: list[str] = []

        for agent in agents:
            discussion.refresh_from_db()
            if discussion.cancelled:
                logger.info("Agent panel %s cancelled, stopping", discussion.pk)
                return

            context = base_context
            if prior_messages:
                context += (
                    "Prior panel contributions:\n"
                    + "\n\n".join(prior_messages)
                    + "\n\n"
                )
            context += (
                "Give your contribution now. Respond to prior speakers when relevant. "
                "Be concise, specific, and actionable from your role's perspective."
            )
            system = (
                f"You are {agent.name}, {agent.get_role_display()}, in a panel discussion "
                f"with other company agents. {agent.system_prompt}\n"
                f"The user is the owner and main investor. You are helping them decide — "
                f"do not pretend to execute actions. Output valid JSON with a message field."
            )
            out, _ = _run_agent(
                model,
                agent.name,
                system,
                context,
                AgentPanelContributionOutput,
                tools=None,
            )
            msg_text = (out.message if out else "").strip()
            AgentPanelMessage.objects.create(
                discussion=discussion,
                agent=agent,
                content=msg_text or "(No contribution generated.)",
            )
            if msg_text:
                prior_messages.append(f"{agent.name} ({agent.get_role_display()}):\n{msg_text}")

        discussion.refresh_from_db()
        if discussion.cancelled:
            return

        transcript = "\n\n".join(prior_messages) if prior_messages else "(No contributions.)"
        synthesis_context = (
            f"{base_context}\n"
            f"Full panel transcript:\n{transcript}\n\n"
            "Synthesize a clear recommendation for the owner."
        )
        moderator = (
            company.agents.filter(role=CompanyAgent.Role.FOUNDER_ASSISTANT).first()
            or company.agents.filter(role=CompanyAgent.Role.FOUNDER).first()
        )
        if moderator:
            moderator_system = (
                f"You are {moderator.name}, moderating a panel discussion. "
                f"{moderator.system_prompt}\n"
                "Produce a synthesis: areas of agreement, key trade-offs, 3-5 concrete next "
                "steps, and any open questions for the owner. Output valid JSON with synthesis."
            )
            moderator_name = moderator.name
        else:
            moderator_system = (
                "You are the panel moderator. Produce a synthesis: areas of agreement, "
                "key trade-offs, 3-5 concrete next steps, and open questions for the owner. "
                "Output valid JSON with synthesis."
            )
            moderator_name = "Panel Moderator"

        synth_out, _ = _run_agent(
            model,
            moderator_name,
            moderator_system,
            synthesis_context,
            AgentPanelSynthesisOutput,
            tools=None,
        )
        discussion.synthesis = (
            (synth_out.synthesis if synth_out else "").strip()
            or "Unable to generate a synthesis."
        )
        discussion.status = AgentPanelDiscussion.Status.COMPLETED
        discussion.save(update_fields=["synthesis", "status", "updated_at"])
    except Exception:
        logger.exception("Agent panel discussion failed: %s", discussion.pk)
        discussion.status = AgentPanelDiscussion.Status.FAILED
        discussion.save(update_fields=["status", "updated_at"])
