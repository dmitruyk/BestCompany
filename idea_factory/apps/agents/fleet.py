"""Fleet generation - creates company agents from accepted idea."""
import json
import logging
import os
from typing import Any

from apps.ideas.context import build_idea_context_text, build_idea_request_prompt
from apps.ideas.models import ActionProposal, Company, CompanyAgent, IdeaRequest

from .agents import _run_agent
from .providers import get_model_for_idea, validate_provider_config
from .schemas import FleetGenerationOutput

logger = logging.getLogger(__name__)

ROLE_MAP = {
    "founder": CompanyAgent.Role.FOUNDER,
    "founder_assistant": CompanyAgent.Role.FOUNDER_ASSISTANT,
    "cpa": CompanyAgent.Role.CPA,
    "accountant": CompanyAgent.Role.CPA,
    "director": CompanyAgent.Role.DIRECTOR,
    "planner": CompanyAgent.Role.PLANNER,
    "qa": CompanyAgent.Role.QA,
    "marketer": CompanyAgent.Role.MARKETER,
    "marketing": CompanyAgent.Role.MARKETER,
    "developer": CompanyAgent.Role.DEVELOPER,
    "product": CompanyAgent.Role.PRODUCT,
    "operations": CompanyAgent.Role.OPERATIONS,
}
MAX_AGENTS = 20


def _get_provider_model(idea_request: IdeaRequest) -> Any | None:
    """Get model for idea_request provider."""
    try:
        err = validate_provider_config(idea_request.provider)
        if err:
            logger.error("Provider config error: %s", err)
            return None
        return get_model_for_idea(idea_request)
    except (ValueError, ImportError) as e:
        logger.error("Provider setup failed: %s", e)
        return None


def _run_fleet_generator(model: Any, context_text: str) -> FleetGenerationOutput | None:
    """Call LLM to generate fleet definition."""
    try:
        system = """You are a Fleet Generator. Given a business idea and its analysis,
create a company structure with specialized AI agents. You MUST include:

1. Founder (founder) - One AI founder voice aligned with the owner/investor vision.
2. Founder Assistant (founder_assistant) - Supports founders with research and coordination.
3. CPA (cpa) - Budget, finance, spending. One agent.
4. Directors (director) - EXACTLY 3 directors minimum (Strategy, Operations, Growth). Priority 80-100.
5. Planner (planner) - Development plan, milestones, roadmap.
6. QA (qa) - Quality, best practices, acceptance criteria for deliverables.
7. Marketer (marketer) - Marketing and go-to-market. One agent.
8. Optionally: developer (build/SPA), product, operations based on the idea.

ONLY use roles: founder, founder_assistant, cpa, director, planner, qa, marketer, developer, product, operations.
No custom roles. At most 20 agents total.
For each agent: role, name, system_prompt (2-4 sentences), priority (0-100; directors 80-100).
Output valid JSON matching FleetGenerationOutput."""

        user = f"""Business idea context:
{context_text}

Generate the agent fleet. company_name should be a short memorable name.
Include founder, founder_assistant, CPA, exactly 3 directors, planner, QA, and marketer."""

        out, _ = _run_agent(
            model,
            "fleet_generator",
            system,
            user,
            FleetGenerationOutput,
            tools=None,
        )
        if out and isinstance(out, FleetGenerationOutput):
            return out
        return None
    except Exception as e:
        logger.exception("Fleet generator failed: %s", e)
        return None


MIN_DIRECTORS = 3

DEFAULT_DIRECTOR_TEMPLATES = [
    ("Chief Strategy Director", 90, "You focus on long-term strategy, market positioning, and competitive advantage. Generate strategic ideas aligned with the company vision."),
    ("Operations Director", 85, "You focus on execution, processes, and day-to-day operations. Generate operational ideas to deliver value efficiently."),
    ("Growth Director", 80, "You focus on scaling, partnerships, and growth channels. Generate ideas to expand the business."),
]


def _ensure_min_directors(company: Company, context_text: str) -> None:
    """Ensure company has at least MIN_DIRECTORS. Add default directors if needed."""
    director_count = company.agents.filter(role=CompanyAgent.Role.DIRECTOR).count()
    if director_count >= MIN_DIRECTORS:
        return
    idea = company.idea_request
    idea_summary = (
        build_idea_request_prompt(idea)[:800] if idea else ""
    )
    to_add = MIN_DIRECTORS - director_count
    used_templates = director_count
    for i in range(to_add):
        name, priority, prompt = DEFAULT_DIRECTOR_TEMPLATES[used_templates + i]
        system_prompt = f"You are {name}. {prompt} Company context: {idea_summary}"
        CompanyAgent.objects.create(
            company=company,
            role=CompanyAgent.Role.DIRECTOR,
            name=name,
            system_prompt=system_prompt,
            config_json="{}",
            priority=priority,
        )
        logger.info("Added director %s to company %s", name, company.pk)


def _build_company_state_context(company: Company) -> str:
    """Build context from current company state for fleet regeneration."""
    from django.utils import timezone

    parts = [
        f"Company: {company.name}",
        f"Original idea: {company.idea_request.title}",
        build_idea_request_prompt(company.idea_request),
    ]
    calendar_actions = company.calendar_actions.order_by("action_date")[:50]
    if calendar_actions.exists():
        lines = ["Calendar actions (what has been done/planned):"]
        for e in calendar_actions:
            lines.append(f"- {e.action_date}: {e.title} [{e.get_status_display}]")
        parts.append("\n".join(lines))
    selected = ActionProposal.objects.filter(
        discussion__company=company, status=ActionProposal.ActionStatus.SELECTED
    ).values_list("action_type", "description")[:10]
    if selected:
        parts.append("Selected actions: " + "\n".join(f"- {t}: {d[:80]}" for t, d in selected))
    return "\n\n".join(parts)


def _run_regenerate_generator(
    model: Any, context_text: str, company_name: str
) -> FleetGenerationOutput | None:
    """Call LLM to regenerate fleet based on current company state."""
    try:
        system = """You are a Fleet Generator. Given the CURRENT STATE of a company (calendar, discussions, progress),
create an updated agent fleet tailored to the company's current needs. The fleet must properly service and develop the company.

1. CPA (cpa) - Budget, money, spending. One agent.
2. Directors (director) - EXACTLY 3. Different focuses (Strategy, Operations, Growth). Generate ideas. Priority 80-100.
3. Marketer (marketer) - Marketing, branding, go-to-market. One agent.
4. Optionally: Developer, Product Manager, Operations.

ONLY use roles: cpa, director, marketer, developer, product, operations. No custom. At most 20 agents.
Each agent: role, name, system_prompt (2-4 sentences, specific to current company state), priority.
Output valid JSON matching FleetGenerationOutput."""

        user = f"""Current company state:
{context_text}

Regenerate the agent fleet. company_name: {company_name}. Base agents on what the company has done and needs next. Include CPA, 3 Directors, Marketer."""

        out, _ = _run_agent(
            model,
            "fleet_regenerator",
            system,
            user,
            FleetGenerationOutput,
            tools=None,
        )
        if out and isinstance(out, FleetGenerationOutput):
            return out
        return None
    except Exception as e:
        logger.exception("Fleet regenerate failed: %s", e)
        return None


def regenerate_fleet(company: Company) -> bool:
    """
    Regenerate agent fleet for existing company based on current state.
    Deletes existing agents, creates new ones (max 20). Returns True on success.
    """
    company.status = Company.Status.REGENERATING_AGENTS
    company.save(update_fields=["status", "updated_at"])

    idea = company.idea_request
    model = _get_provider_model(idea)
    if model is None:
        company.status = Company.Status.ACTIVE
        company.save(update_fields=["status", "updated_at"])
        logger.error("Provider setup failed for regenerate")
        return False

    context_text = _build_company_state_context(company)
    fleet_out = _run_regenerate_generator(model, context_text, company.name)

    if not fleet_out or not fleet_out.agents:
        company.status = Company.Status.ACTIVE
        company.save(update_fields=["status", "updated_at"])
        logger.error("Regenerate returned no agents")
        return False

    company.agents.all().delete()
    agents_to_create = fleet_out.agents[:MAX_AGENTS]
    for agent_def in agents_to_create:
        role_key = (agent_def.role or "operations").lower()
        role = ROLE_MAP.get(role_key, CompanyAgent.Role.OPERATIONS)
        config_json = json.dumps(agent_def.config or {})
        CompanyAgent.objects.create(
            company=company,
            role=role,
            name=agent_def.name or role.replace("_", " ").title(),
            system_prompt=agent_def.system_prompt or f"You are a {role} for this company.",
            config_json=config_json,
            priority=agent_def.priority or 0,
        )

    _ensure_min_directors(company, context_text)

    company.status = Company.Status.ACTIVE
    company.save(update_fields=["status", "updated_at"])

    logger.info("Regenerated company %s with %d agents", company.pk, company.agents.count())
    return True


def _build_context_text(idea_request: IdeaRequest) -> str:
    """Build context string from idea, PDF attachments, and conclusion."""
    return build_idea_context_text(idea_request)


def generate_fleet(idea_request: IdeaRequest) -> Company | None:
    """
    Generate company and agent fleet for an accepted idea.
    Sets idea_request.development_status to GENERATING_FLEET, then READY on success.
    """
    if not idea_request.owner_id:
        logger.error("Idea has no owner, cannot create company")
        return None

    idea_request.development_status = IdeaRequest.DevelopmentStatus.GENERATING_FLEET
    idea_request.save(update_fields=["development_status", "updated_at"])

    model = _get_provider_model(idea_request)
    if model is None:
        idea_request.development_status = IdeaRequest.DevelopmentStatus.NOT_STARTED
        idea_request.save(update_fields=["development_status", "updated_at"])
        logger.error("Provider setup failed for fleet generation")
        return None

    context_text = _build_context_text(idea_request)
    fleet_out = _run_fleet_generator(model, context_text)

    if not fleet_out or not fleet_out.agents:
        idea_request.development_status = IdeaRequest.DevelopmentStatus.NOT_STARTED
        idea_request.save(update_fields=["development_status", "updated_at"])
        logger.error("Fleet generation returned no agents")
        return None

    company_name = fleet_out.company_name or f"{idea_request.title} Co."
    company = Company.objects.create(
        idea_request=idea_request,
        name=company_name,
        owner=idea_request.owner,
        status=Company.Status.ACTIVE,
    )

    agents_to_create = fleet_out.agents[:MAX_AGENTS]
    for agent_def in agents_to_create:
        role_key = (agent_def.role or "operations").lower()
        role = ROLE_MAP.get(role_key, CompanyAgent.Role.OPERATIONS)
        config_json = json.dumps(agent_def.config or {})
        CompanyAgent.objects.create(
            company=company,
            role=role,
            name=agent_def.name or role.replace("_", " ").title(),
            system_prompt=agent_def.system_prompt or f"You are a {role} for this company.",
            config_json=config_json,
            priority=agent_def.priority or 0,
        )

    _ensure_min_directors(company, context_text)

    idea_request.development_status = IdeaRequest.DevelopmentStatus.READY
    idea_request.save(update_fields=["development_status", "updated_at"])

    logger.info("Created company %s with %d agents", company.pk, len(fleet_out.agents))
    return company
