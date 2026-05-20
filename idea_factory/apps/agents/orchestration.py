"""Orchestration pipeline - runs agents in sequence and persists results."""
import json
import logging
import os
from typing import Any, Callable, Optional

from django.db import IntegrityError
from django.utils import timezone

from apps.ideas.context import build_idea_request_prompt
from apps.ideas.models import AgentRun, IdeaConclusion, IdeaRequest

from .agents import (
    run_critic,
    run_evaluator,
    run_estimator,
    run_executor,
    run_idea_generator,
    run_internet_explorer,
    run_overviewer,
    run_prompt_generator,
)
from .confidence import adjust_confidence, count_unknown_assumptions
from .providers import get_model_for_idea, validate_provider_config
from .schemas import (
    CritiqueOutput,
    EstimateOutput,
    ExecutorOutput,
    IdeaSetOutput,
    InternetExplorerOutput,
    OverviewOutput,
)

# Pipeline order: (role, context_key, schema_class, run_fn)
PIPELINE_STEPS: list[tuple[str, str, type, Callable[..., tuple[Any, dict]]]] = [
    (AgentRun.Role.INTERNET_EXPLORER, "internet_explorer", InternetExplorerOutput, run_internet_explorer),
    (AgentRun.Role.IDEA_GENERATOR, "idea_generator", IdeaSetOutput, run_idea_generator),
    (AgentRun.Role.ESTIMATOR, "estimator", EstimateOutput, run_estimator),
    (AgentRun.Role.CRITIC, "critic", CritiqueOutput, run_critic),
    (AgentRun.Role.EXECUTOR, "executor", ExecutorOutput, run_executor),
    (AgentRun.Role.OVERVIEWER, "overviewer", OverviewOutput, run_overviewer),
]

ROLE_TO_STEP: dict[str, tuple[str, str, type, Callable]] = {
    role: (role, ctx_key, schema, fn) for role, ctx_key, schema, fn in PIPELINE_STEPS
}

logger = logging.getLogger(__name__)

MAX_CYCLES = 8
MAX_EVAL_RETRIES = 2  # Max retries per agent when Evaluator rejects


def _compute_confidence(
    agent_name: str,
    base: float,
    metrics: dict,
    output: Any,
    context: dict,
) -> float:
    """Apply confidence heuristic per agent."""
    hit_max = metrics.get("cycles", 0) >= MAX_CYCLES
    unknown_count = 0
    internet_ok = False
    if agent_name == "internet_explorer" and output:
        internet_ok = bool(
            getattr(output, "sources_checked", None)
            or getattr(output, "market_insights", "")
        )
    if output and hasattr(output, "assumptions"):
        unknown_count = count_unknown_assumptions(output.assumptions)
    elif output and isinstance(getattr(output, "assumptions", None), list):
        unknown_count = count_unknown_assumptions(output.assumptions)

    return adjust_confidence(
        base,
        internet_sources_found=internet_ok,
        unknown_assumptions_count=unknown_count,
        hit_max_cycles=hit_max,
    )


def _load_context_from_runs(idea_request: IdeaRequest) -> dict[str, Any]:
    """Rebuild context dict from successful AgentRun output_json records."""
    context: dict[str, Any] = {}
    role_to_schema = {role: schema for role, ctx_key, schema, _ in PIPELINE_STEPS}
    for run in idea_request.agent_runs.filter(status=AgentRun.RunStatus.SUCCEEDED):
        if not run.output_json:
            continue
        role = run.role
        if role not in role_to_schema:
            continue
        schema = role_to_schema[role]
        ctx_key = ROLE_TO_STEP[role][1]
        try:
            data = json.loads(run.output_json)
            context[ctx_key] = schema.model_validate(data)
        except (json.JSONDecodeError, Exception):
            pass
    return context


def _get_provider_model(idea_request: IdeaRequest) -> Optional[Any]:
    """Get model for idea_request provider. Returns None on error."""
    try:
        err = validate_provider_config(idea_request.provider)
        if err:
            logger.error("Provider config error: %s", err)
            return None
        return get_model_for_idea(idea_request)
    except (ValueError, ImportError) as e:
        logger.error("Provider setup failed: %s", e)
        return None


def _run_steps(
    idea_request: IdeaRequest,
    provider_model: Any,
    context: dict[str, Any],
    start_index: int,
) -> None:
    """Run pipeline steps from start_index to end, with evaluate-and-retry loop."""
    request_prompt = build_idea_request_prompt(idea_request)
    agent_outputs = {
        k: v.model_dump() if hasattr(v, "model_dump") else v
        for k, v in context.items()
        if v is not None
    }
    agents_involved = list(agent_outputs.keys())

    for i in range(start_index, len(PIPELINE_STEPS)):
        try:
            idea_request.refresh_from_db()
        except IdeaRequest.DoesNotExist:
            logger.warning("Idea %s was deleted, stopping pipeline", idea_request.pk)
            return

        if idea_request.status != IdeaRequest.Status.RUNNING:
            logger.info("Pipeline stopped: idea %s status=%s", idea_request.pk, idea_request.status)
            return

        role, ctx_key, schema, run_fn = PIPELINE_STEPS[i]
        agent_name = role.replace("_", " ").title()
        improvement_hint: Optional[str] = None
        retry_count = 0

        while True:
            try:
                idea_request.refresh_from_db()
                if idea_request.status != IdeaRequest.Status.RUNNING:
                    logger.info("Pipeline stopped during %s: idea %s status=%s", agent_name, idea_request.pk, idea_request.status)
                    return
            except IdeaRequest.DoesNotExist:
                return

            try:
                out, metrics = run_fn(
                    provider_model, request_prompt, context, improvement_hint
                )
            except IntegrityError as e:
                logger.exception("IntegrityError (idea may have been deleted): %s", e)
                try:
                    idea_request.status = IdeaRequest.Status.FAILED
                    idea_request.save(update_fields=["status", "updated_at"])
                except Exception:
                    pass
                return
            except Exception as e:
                logger.exception("%s error: %s", agent_name, e)
                try:
                    _save_agent_run(
                        idea_request,
                        f"{agent_name} (retry {retry_count})" if retry_count else agent_name,
                        role,
                        None,
                        {"error": str(e)},
                        context,
                        failed=True,
                        error=str(e),
                    )
                except IntegrityError:
                    return
                if role == AgentRun.Role.IDEA_GENERATOR:
                    idea_request.status = IdeaRequest.Status.FAILED
                    idea_request.save(update_fields=["status", "updated_at"])
                    return
                break

            display_name = f"{agent_name} (retry {retry_count})" if retry_count else agent_name
            context[ctx_key] = out
            if out:
                agent_outputs[ctx_key] = out.model_dump()
                if ctx_key not in agents_involved:
                    agents_involved.append(ctx_key)
            _save_agent_run(
                idea_request, display_name, role, out, metrics, context
            )

            if role == AgentRun.Role.OVERVIEWER:
                break

            idea_request.refresh_from_db()
            if idea_request.status != IdeaRequest.Status.RUNNING:
                logger.info("Pipeline stopped before evaluator: idea %s", idea_request.pk)
                return

            eval_out, eval_metrics = run_evaluator(
                provider_model,
                agent_name,
                json.dumps(out.model_dump(), indent=2) if out and hasattr(out, "model_dump") else "{}",
                request_prompt[:600],
            )
            _save_agent_run(
                idea_request,
                f"Evaluator ({agent_name})",
                AgentRun.Role.EVALUATOR,
                eval_out,
                eval_metrics,
                context,
                explicit_confidence=eval_out.score if eval_out else 0.5,
            )

            if eval_out and eval_out.is_acceptable:
                break
            if retry_count >= MAX_EVAL_RETRIES:
                logger.info("%s: max retries reached, accepting output", agent_name)
                break

            idea_request.refresh_from_db()
            if idea_request.status != IdeaRequest.Status.RUNNING:
                logger.info("Pipeline stopped before prompt generator: idea %s", idea_request.pk)
                return

            pg_out, pg_metrics = run_prompt_generator(
                provider_model,
                agent_name,
                json.dumps(out.model_dump(), indent=2) if out and hasattr(out, "model_dump") else "{}",
                eval_out.feedback if eval_out else "Quality below threshold",
                eval_out.improvement_suggestions if eval_out else [],
                request_prompt,
            )
            _save_agent_run(
                idea_request,
                f"Prompt Generator ({agent_name})",
                AgentRun.Role.PROMPT_GENERATOR,
                pg_out,
                pg_metrics,
                context,
            )
            improvement_hint = (
                pg_out.improved_instructions if pg_out else (eval_out.feedback if eval_out else "")
            )
            retry_count += 1

    final_summary = ""
    if context.get("overviewer"):
        final_summary = context["overviewer"].executive_summary
    else:
        final_summary = "Pipeline completed with partial results. Check agent outputs."

    result_bundle = {
        "final_summary": final_summary,
        "agents_involved": agents_involved,
        "agent_outputs": agent_outputs,
        "request": {"title": idea_request.title, "prompt": idea_request.prompt},
    }
    idea_request.status = IdeaRequest.Status.SUCCEEDED
    idea_request.save(update_fields=["status", "updated_at"])
    IdeaConclusion.objects.update_or_create(
        idea_request=idea_request,
        defaults={
            "final_summary": final_summary,
            "result_json": json.dumps(result_bundle, indent=2),
        },
    )


def run_pipeline(idea_request: IdeaRequest) -> None:
    """
    Run the full agent pipeline for idea_request.
    Updates idea_request status and creates AgentRun records.
    """
    idea_request.status = IdeaRequest.Status.RUNNING
    idea_request.save(update_fields=["status", "updated_at"])

    provider_model = _get_provider_model(idea_request)
    if provider_model is None:
        idea_request.status = IdeaRequest.Status.FAILED
        idea_request.save(update_fields=["status", "updated_at"])
        logger.exception("Provider setup failed")
        return

    _run_steps(idea_request, provider_model, {}, 0)


def run_from_scratch(idea_request: IdeaRequest) -> None:
    """
    Delete all agent runs and conclusions, then run the full pipeline from the beginning.
    """
    idea_request.agent_runs.all().delete()
    IdeaConclusion.objects.filter(idea_request=idea_request).delete()
    run_pipeline(idea_request)


def rerun_failed(idea_request: IdeaRequest) -> bool:
    """
    Rerun failed pipeline steps. Loads context from successful runs,
    deletes failed runs and everything after, resumes from first failed step.
    Returns True if rerun was started, False if nothing to rerun.
    """
    failed_runs = idea_request.agent_runs.filter(status=AgentRun.RunStatus.FAILED)
    if not failed_runs.exists():
        return False

    # Find first failed run by pipeline order
    role_order = [role for role, _, _, _ in PIPELINE_STEPS]
    first_failed_role = None
    for role in role_order:
        if idea_request.agent_runs.filter(role=role, status=AgentRun.RunStatus.FAILED).exists():
            first_failed_role = role
            break
    if first_failed_role is None:
        return False

    start_index = role_order.index(first_failed_role)

    # Delete from first failed onward (including the failed run and any after)
    for i in range(start_index, len(role_order)):
        idea_request.agent_runs.filter(role=role_order[i]).delete()

    idea_request.status = IdeaRequest.Status.RUNNING
    idea_request.save(update_fields=["status", "updated_at"])

    provider_model = _get_provider_model(idea_request)
    if provider_model is None:
        idea_request.status = IdeaRequest.Status.FAILED
        idea_request.save(update_fields=["status", "updated_at"])
        return True

    context = _load_context_from_runs(idea_request)
    _run_steps(idea_request, provider_model, context, start_index)
    return True


def _save_agent_run(
    idea_request: IdeaRequest,
    agent_name: str,
    role: str,
    output: Any,
    metrics: dict,
    context: dict,
    *,
    failed: bool = False,
    error: Optional[str] = None,
    explicit_confidence: Optional[float] = None,
) -> AgentRun:
    """Create and persist AgentRun record."""
    if not IdeaRequest.objects.filter(pk=idea_request.pk).exists():
        raise IntegrityError("IdeaRequest was deleted")
    if explicit_confidence is not None:
        base_conf = explicit_confidence
    else:
        base_conf = getattr(output, "confidence", 0.5) if output else 0.0
    norm_name = agent_name.lower().replace(" ", "_")
    confidence = _compute_confidence(norm_name, base_conf, metrics, output, context)
    run = AgentRun.objects.create(
        idea_request=idea_request,
        agent_name=agent_name,
        role=role,
        confidence=confidence,
        cycles=metrics.get("cycles", 0),
        duration_ms=metrics.get("latency_ms"),
        input_tokens=metrics.get("input_tokens"),
        output_tokens=metrics.get("output_tokens"),
        total_tokens=metrics.get("total_tokens"),
        status=AgentRun.RunStatus.FAILED if failed else AgentRun.RunStatus.SUCCEEDED,
        error=error,
        output_json=json.dumps(output.model_dump(), indent=2)
        if output and hasattr(output, "model_dump")
        else None,
        finished_at=timezone.now(),
    )
    return run
