"""Fleet generation - creates company agents from accepted idea."""
import json
import logging
import os
from typing import Any

from apps.ideas.models import Company, CompanyAgent, IdeaRequest

from .agents import _run_agent
from .providers import get_model
from .schemas import FleetGenerationOutput

logger = logging.getLogger(__name__)

ROLE_MAP = {
    "cpa": CompanyAgent.Role.CPA,
    "director": CompanyAgent.Role.DIRECTOR,
    "marketer": CompanyAgent.Role.MARKETER,
    "developer": CompanyAgent.Role.DEVELOPER,
    "product": CompanyAgent.Role.PRODUCT,
    "operations": CompanyAgent.Role.OPERATIONS,
    "custom": CompanyAgent.Role.CUSTOM,
}


def _get_provider_model(idea_request: IdeaRequest) -> Any | None:
    """Get model for idea_request provider."""
    try:
        prev_provider = os.environ.get("LLM_PROVIDER")
        prev_ollama_model = os.environ.get("OLLAMA_MODEL_ID")
        prev_openai_model = os.environ.get("OPENAI_MODEL")

        os.environ["LLM_PROVIDER"] = idea_request.provider
        if idea_request.model_id:
            if idea_request.provider == "ollama":
                os.environ["OLLAMA_MODEL_ID"] = idea_request.model_id
            else:
                os.environ["OPENAI_MODEL"] = idea_request.model_id

        try:
            return get_model()
        finally:
            if prev_provider is not None:
                os.environ["LLM_PROVIDER"] = prev_provider
            elif "LLM_PROVIDER" in os.environ:
                del os.environ["LLM_PROVIDER"]
            if prev_ollama_model is not None:
                os.environ["OLLAMA_MODEL_ID"] = prev_ollama_model
            elif "OLLAMA_MODEL_ID" in os.environ and idea_request.model_id:
                del os.environ["OLLAMA_MODEL_ID"]
            if prev_openai_model is not None:
                os.environ["OPENAI_MODEL"] = prev_openai_model
            elif "OPENAI_MODEL" in os.environ and idea_request.model_id:
                del os.environ["OPENAI_MODEL"]
    except (ValueError, ImportError):
        return None


def _run_fleet_generator(model: Any, context_text: str) -> FleetGenerationOutput | None:
    """Call LLM to generate fleet definition."""
    try:
        system = """You are a Fleet Generator. Given a business idea and its analysis,
create a company structure with specialized AI agents. You MUST include:

1. CPA (cpa) - Handles budget, money, spending, financial tracking. One agent.
2. Directors (director) - EXACTLY 3 directors minimum. Each with a distinct focus (e.g. Strategy, Operations, Growth).
   Each director has a priority number (80-100, higher = more senior). They generate ideas for the company.
3. Marketer (marketer) - Marketing, branding, go-to-market. One agent.
4. Optionally: Developer, Product Manager, Operations based on the idea.

For each agent provide: role, name, system_prompt (2-4 sentences), priority (0-100, directors: 80-100).
System prompts should be specific to this business idea. Output valid JSON matching FleetGenerationOutput."""

        user = f"""Business idea context:
{context_text}

Generate the agent fleet. company_name should be a short memorable name. Include at least CPA, exactly 3 Directors (each with different focus to generate ideas), Marketer."""

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
    idea_summary = f"{idea.title}. {idea.prompt[:500]}" if idea else ""
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


def _build_context_text(idea_request: IdeaRequest) -> str:
    """Build context string from idea and conclusion."""
    parts = [
        f"Title: {idea_request.title}",
        f"Prompt: {idea_request.prompt}",
    ]
    conclusion = getattr(idea_request, "conclusion", None)
    if conclusion:
        parts.append(f"Summary: {conclusion.final_summary}")
        try:
            data = json.loads(conclusion.result_json)
            parts.append(f"Full analysis: {json.dumps(data, indent=2)[:3000]}")
        except json.JSONDecodeError:
            pass
    return "\n\n".join(parts)


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

    for agent_def in fleet_out.agents:
        role_key = (agent_def.role or "custom").lower()
        role = ROLE_MAP.get(role_key, CompanyAgent.Role.CUSTOM)
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
