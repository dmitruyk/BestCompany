"""Agent definitions - each agent as a runnable component."""
import asyncio
import json
import logging
import time
from typing import Any, Optional

from strands import Agent
from strands.models.model import Model

from .providers import is_ollama_model
from .schemas import (
    CritiqueOutput,
    EstimateOutput,
    EvaluatorOutput,
    ExecutorOutput,
    IdeaSetOutput,
    InternetExplorerOutput,
    OverviewOutput,
    PromptGeneratorOutput,
    SearchQueriesOutput,
)
from .tools import fetch_url_summary, get_web_search_tool, run_web_searches

logger = logging.getLogger(__name__)

# Max cycles per agent - Strands may not expose this directly; we track from metrics
MAX_CYCLES_PER_AGENT = 8


def _messages_from_prompt(user_prompt: str) -> list:
    """Build Messages format for model.structured_output."""
    return [{"role": "user", "content": [{"text": user_prompt}]}]


def _run_structured_output_direct(
    model: Model,
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
    structured_output_model: type,
) -> tuple[Any, dict[str, Any]]:
    """
    Single LLM call via model.structured_output() — no Agent loop or tool rounds.

    Used for Ollama (tool_choice ignored) and for read-only paths that already gathered
    context server-side (company assistant), to avoid extra OpenAI requests and retries.
    """

    async def _run() -> tuple[Any, dict[str, Any]]:
        output = None
        async for event in model.structured_output(
            structured_output_model,
            _messages_from_prompt(user_prompt),
            system_prompt=system_prompt,
        ):
            if "output" in event:
                output = event["output"]
        return output, {"cycles": 1, "latency_ms": 0, "tool_usage": {}}

    started = time.time()
    out, _ = asyncio.run(_run())
    elapsed_ms = int((time.time() - started) * 1000)
    metrics = {"cycles": 1, "latency_ms": elapsed_ms, "tool_usage": {}}
    return out, metrics


def _run_internet_explorer_ollama(
    model: Model,
    user_prompt: str,
) -> tuple[Optional[InternetExplorerOutput], dict[str, Any]]:
    """
    Ollama workaround: run web searches server-side, then structured output (avoids tool-calling bugs).
    """
    web_search_available = get_web_search_tool() is not None
    if not web_search_available:
        return (
            InternetExplorerOutput(
                sources_checked=[],
                market_insights="Web search unavailable. Install ddgs or duckduckgo_search.",
                competitor_notes="",
                pricing_trends="",
                search_available=False,
                confidence=0.0,
            ),
            {"cycles": 1, "latency_ms": 0, "tool_usage": {}},
        )

    query_system = "Output 2-5 specific web search queries for market size, competitors, pricing. JSON with 'queries' array of strings."
    query_user = f"{user_prompt[:1200]}\n\nOutput web search queries as JSON."

    async def _get_queries() -> list[str]:
        queries: list[str] = []
        async for event in model.structured_output(
            SearchQueriesOutput,
            _messages_from_prompt(query_user),
            system_prompt=query_system,
        ):
            if "output" in event:
                queries = event["output"].queries
        return queries or [f"{user_prompt[:100]} market size", f"{user_prompt[:100]} competitors"]

    queries = asyncio.run(_get_queries())
    search_results = run_web_searches(queries)

    main_system = """You are an Internet Explorer agent. Summarize the provided search results into:
- sources_checked: list of URLs found
- market_insights: key market findings
- competitor_notes: competitor observations
- pricing_trends: pricing/trend observations
Output valid JSON matching InternetExplorerOutput schema."""
    main_user = f"{user_prompt}\n\nSearch results:\n{search_results}\n\nSummarize into the required schema."

    async def _get_output() -> Optional[InternetExplorerOutput]:
        out = None
        async for event in model.structured_output(
            InternetExplorerOutput,
            _messages_from_prompt(main_user),
            system_prompt=main_system,
        ):
            if "output" in event:
                out = event["output"]
        return out

    started = time.time()
    out = asyncio.run(_get_output())
    elapsed_ms = int((time.time() - started) * 1000)
    if out:
        out.search_available = True
    return out or InternetExplorerOutput(
        sources_checked=[], market_insights="Parse failed.", competitor_notes="", pricing_trends="", search_available=True, confidence=0.0
    ), {"cycles": 2, "latency_ms": elapsed_ms, "tool_usage": {}}


def _run_agent(
    model: Model,
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
    structured_output_model: type,
    tools: Optional[list] = None,
) -> tuple[Any, dict[str, Any]]:
    """
    Run a single agent invocation with structured output.
    Returns (structured_output, metrics_dict).
    Uses Ollama-specific path when model is Ollama (avoids tool-calling bugs).
    """
    if is_ollama_model(model) and tools:
        if agent_name == "internet_explorer":
            return _run_internet_explorer_ollama(model, user_prompt)
        raise ValueError(f"Ollama workaround not implemented for agent with tools: {agent_name}")

    if is_ollama_model(model) and not tools:
        return _run_structured_output_direct(
            model, agent_name, system_prompt, user_prompt, structured_output_model
        )

    agent = Agent(
        model=model,
        name=agent_name,
        system_prompt=system_prompt,
        tools=tools or [],
        callback_handler=None,
    )
    started = time.time()
    result = agent(user_prompt, structured_output_model=structured_output_model)
    elapsed_ms = int((time.time() - started) * 1000)

    metrics: dict[str, Any] = {
        "cycles": 0,
        "latency_ms": elapsed_ms,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "tool_usage": {},
    }
    if hasattr(result, "metrics") and result.metrics:
        try:
            summary = result.metrics.get_summary()
            if isinstance(summary, dict):
                metrics["cycles"] = summary.get("total_cycles", 0)
                acc = summary.get("accumulated_usage", {})
                metrics["input_tokens"] = acc.get("inputTokens")
                metrics["output_tokens"] = acc.get("outputTokens")
                metrics["total_tokens"] = acc.get("totalTokens", 0) or (
                    (metrics["input_tokens"] or 0) + (metrics["output_tokens"] or 0)
                )
                metrics["tool_usage"] = summary.get("tool_usage", {})
        except Exception:
            pass

    out = result.structured_output if hasattr(result, "structured_output") else None
    return out, metrics


def run_internet_explorer(
    model: Model,
    request_prompt: str,
    context: dict[str, Any],
    improvement_hint: Optional[str] = None,
) -> tuple[Optional[InternetExplorerOutput], dict[str, Any]]:
    """Gather external info for validation."""
    web_search = get_web_search_tool()
    tools = [fetch_url_summary]
    if web_search:
        tools.append(web_search)

    search_available = web_search is not None
    system = """You are an Internet Explorer agent. Your goal is to gather external information
for validating a business idea: market size, competitors, pricing, trends.

CRITICAL: You MUST use your tools BEFORE producing the output. Do NOT summarize without gathering data first.

1. Call web_search at least 2-3 times with different queries (e.g. market size for [domain], competitors in [space], pricing trends [industry]). Use the business idea context to craft specific search queries.
2. Optionally call fetch_url_summary on relevant URLs from search results to get deeper content.
3. Then produce your output: list every URL/source consulted in sources_checked, summarize market_insights, competitor_notes, pricing_trends from the search results.

If web_search is unavailable, use fetch_url_summary on known industry URLs. If web search is available, you MUST use it - never produce empty sources_checked."""
    user = f"Business idea context:\n{request_prompt}\n\nFIRST: Run web_search (and optionally fetch_url_summary) to gather real data. THEN produce your summary. Web search available: {search_available}"
    if improvement_hint:
        user += f"\n\n[RETRY - Previous attempt was unsatisfactory. Please improve: {improvement_hint}]"
    try:
        out, m = _run_agent(
            model,
            "internet_explorer",
            system,
            user,
            InternetExplorerOutput,
            tools=tools,
        )
        return out, m
    except Exception as e:
        logger.exception("InternetExplorer failed: %s", e)
        fallback = InternetExplorerOutput(
            sources_checked=[],
            market_insights="Failed to gather external data.",
            competitor_notes="",
            pricing_trends="",
            search_available=web_search is not None,
            confidence=0.0,
        )
        return fallback, {"cycles": 0, "latency_ms": 0, "error": str(e)}


def run_idea_generator(
    model: Model,
    request_prompt: str,
    context: dict[str, Any],
    improvement_hint: Optional[str] = None,
) -> tuple[Optional[IdeaSetOutput], dict[str, Any]]:
    """Generate 5-10 business ideas and select top 3."""
    ie = context.get("internet_explorer")
    ie_text = ""
    if ie:
        ie_text = f"\nMarket/Competitor context:\n{ie.market_insights}\n{ie.competitor_notes}"

    system = """You are an Idea Generator agent. Generate 5-10 innovative business ideas
tailored to the user's request. Select the top 3. For each idea provide name, description,
target users, differentiation, and feasibility_score 0-1. Use top_3_indices as 0-based list indices.

CRITICAL: Output strictly valid JSON. Each array must end with ]. No trailing commas. Use standard ASCII hyphens (-)."""
    user = f"Request:\n{request_prompt}{ie_text}\n\nGenerate ideas and output in the required schema."
    if improvement_hint:
        user += f"\n\n[RETRY - Improve based on: {improvement_hint}]"
    return _run_agent(model, "idea_generator", system, user, IdeaSetOutput)


def run_estimator(
    model: Model,
    request_prompt: str,
    context: dict[str, Any],
    improvement_hint: Optional[str] = None,
) -> tuple[Optional[EstimateOutput], dict[str, Any]]:
    """Estimate feasibility, costs, risks, timeline, KPIs."""
    ideas = context.get("idea_generator")
    selected = context.get("selected_idea", "")
    if ideas and ideas.ideas:
        idx = ideas.top_3_indices[0] if ideas.top_3_indices else 0
        sel = ideas.ideas[min(idx, len(ideas.ideas) - 1)]
        selected = f"{sel.name}: {sel.description}"

    system = """You are an Estimator agent. Evaluate the selected business idea for feasibility.
Output cost ranges (USD), timeline (weeks), risks, assumptions (with confidence: high/medium/low/unknown),
MVP plan summary, and KPIs.

CRITICAL: Output strictly valid JSON. Each array must end with ]. No trailing commas. Use standard ASCII hyphens (-). For risks, kpis, assumptions: each element must be a string or valid object."""
    user = f"Request:\n{request_prompt}\n\nSelected idea to estimate:\n{selected}\n\nProduce structured estimate."
    if improvement_hint:
        user += f"\n\n[RETRY - Improve based on: {improvement_hint}]"
    return _run_agent(model, "estimator", system, user, EstimateOutput)


def run_critic(
    model: Model,
    request_prompt: str,
    context: dict[str, Any],
    improvement_hint: Optional[str] = None,
) -> tuple[Optional[CritiqueOutput], dict[str, Any]]:
    """Critique weak points and propose improvements."""
    ideas = context.get("idea_generator")
    selected = ""
    if ideas and ideas.ideas:
        idx = ideas.top_3_indices[0] if ideas.top_3_indices else 0
        sel = ideas.ideas[min(idx, len(ideas.ideas) - 1)]
        selected = f"{sel.name}: {sel.description}"
    est = context.get("estimator")
    est_text = json.dumps(est.model_dump(), indent=2) if est else ""

    system = """You are a Critic agent. Attack the idea's weak points, failure modes, missing assumptions,
legal/ops risks. Propose improvements and alternative hypotheses. Be constructive but thorough.

CRITICAL: Output strictly valid JSON. Each array must end with ]. No trailing commas. Use standard ASCII hyphens (-)."""
    user = f"Request:\n{request_prompt}\n\nIdea:\n{selected}\n\nEstimate:\n{est_text}\n\nCritique and improve."
    if improvement_hint:
        user += f"\n\n[RETRY - Improve based on: {improvement_hint}]"
    return _run_agent(model, "critic", system, user, CritiqueOutput)


def run_executor(
    model: Model,
    request_prompt: str,
    context: dict[str, Any],
    improvement_hint: Optional[str] = None,
) -> tuple[Optional[ExecutorOutput], dict[str, Any]]:
    """Output actionable next steps: MVP backlog, milestones, stack, GTM."""
    crit = context.get("critic")
    crit_text = json.dumps(crit.model_dump(), indent=2) if crit else ""
    ideas = context.get("idea_generator")
    selected = ""
    if ideas and ideas.ideas:
        idx = ideas.top_3_indices[0] if ideas.top_3_indices else 0
        sel = ideas.ideas[min(idx, len(ideas.ideas) - 1)]
        selected = f"{sel.name}: {sel.description}"

    system = """You are an Executor agent. Create actionable next steps: MVP backlog, milestones,
tech stack suggestions, go-to-market steps, and immediate next steps.

FORMAT RULES (mandatory):
- mvp_backlog, milestones, stack_suggestions, gtm_steps, next_steps_immediate must be arrays of PLAIN STRINGS only.
- Example: ["Item one", "Item two"] - NOT objects like {"step":"..."}.
- At most 6 items per list to avoid truncation. Keep each string to one short sentence.
- Output valid JSON: arrays end with ], root object ends with }. No trailing commas. Use ASCII hyphen (-)."""
    user = f"Request:\n{request_prompt}\n\nIdea:\n{selected}\n\nCritique:\n{crit_text}\n\nProduce execution plan."
    if improvement_hint:
        user += f"\n\n[RETRY - Improve based on: {improvement_hint}]"
    return _run_agent(model, "executor", system, user, ExecutorOutput)


def run_evaluator(
    model: Model,
    agent_being_evaluated: str,
    agent_output_json: str,
    request_context: str,
) -> tuple[Optional[EvaluatorOutput], dict[str, Any]]:
    """Evaluate quality of another agent's output. Returns score, is_acceptable, feedback."""
    system = """You are an Evaluator agent. Assess the quality of another agent's response.

Consider: completeness, relevance, actionable value, structure, and whether key fields are populated.
Score 0-1. Set is_acceptable=false if score < 0.6, response is empty/generic, or critical fields are missing.
Provide brief feedback and 1-3 specific improvement_suggestions when is_acceptable is false.

CRITICAL: Output strictly valid JSON. Arrays end with ]. No trailing commas. Use ASCII hyphen (-)."""
    user = f"""Agent being evaluated: {agent_being_evaluated}

Request context: {request_context}

Agent output to evaluate:
{agent_output_json}

Assess quality. Output EvaluatorOutput schema."""
    try:
        return _run_agent(
            model, f"Evaluator ({agent_being_evaluated})", system, user, EvaluatorOutput
        )
    except Exception as e:
        logger.exception("Evaluator failed: %s", e)
        # Default to acceptable on evaluator failure so we don't block pipeline
        fallback = EvaluatorOutput(
            score=0.5, is_acceptable=True, feedback=f"Evaluation failed: {e}"
        )
        return fallback, {"cycles": 0, "latency_ms": 0, "error": str(e)}


def run_prompt_generator(
    model: Model,
    agent_being_improved: str,
    agent_output_json: str,
    evaluator_feedback: str,
    improvement_suggestions: list[str],
    original_user_prompt: str,
) -> tuple[Optional[PromptGeneratorOutput], dict[str, Any]]:
    """Generate improved instructions for retrying an agent based on evaluator feedback."""
    suggestions_text = "\n".join(f"- {s}" for s in improvement_suggestions) if improvement_suggestions else "Improve quality and completeness."
    system = """You are a Prompt Generator agent. Given evaluator feedback on a poor agent response,
produce improved_instructions: a short paragraph to append to the retry prompt. Be specific and actionable.
Do not repeat the original request. Focus on what to fix. Keep improved_instructions under 200 words.

CRITICAL: Output strictly valid JSON. Use ASCII hyphen (-)."""
    user = f"""Agent to retry: {agent_being_improved}

Evaluator feedback: {evaluator_feedback}

Improvement suggestions: {suggestions_text}

Original user prompt (for context): {original_user_prompt[:500]}...

Produce improved_instructions for the retry. Output PromptGeneratorOutput schema."""
    try:
        return _run_agent(
            model,
            f"Prompt Generator ({agent_being_improved})",
            system,
            user,
            PromptGeneratorOutput,
        )
    except Exception as e:
        logger.exception("PromptGenerator failed: %s", e)
        fallback = PromptGeneratorOutput(
            improved_instructions=f"Please improve based on: {evaluator_feedback}",
            changes_summary="Fallback due to error",
        )
        return fallback, {"cycles": 0, "latency_ms": 0, "error": str(e)}


def run_overviewer(
    model: Model,
    request_prompt: str,
    context: dict[str, Any],
    improvement_hint: Optional[str] = None,
) -> tuple[Optional[OverviewOutput], dict[str, Any]]:
    """Executive overview, go/no-go, key metrics, confidence."""
    all_outputs = {
        k: (v.model_dump() if hasattr(v, "model_dump") else str(v))
        for k, v in context.items()
        if v is not None
    }
    system = """You are an Overviewer agent. Produce a decision-ready executive summary,
GO or NO-GO recommendation, key metrics to track, and overall confidence 0-1.

CRITICAL: Output strictly valid JSON. Each array must end with ]. No trailing commas. Use standard ASCII hyphens (-)."""
    user = f"Request:\n{request_prompt}\n\nAll prior agent outputs:\n{json.dumps(all_outputs, indent=2)}\n\nProduce executive overview."
    return _run_agent(model, "overviewer", system, user, OverviewOutput)
