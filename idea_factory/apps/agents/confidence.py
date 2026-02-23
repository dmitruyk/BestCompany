"""Confidence scoring heuristics per agent output."""


def adjust_confidence(
    base: float,
    *,
    internet_sources_found: bool = False,
    unknown_assumptions_count: int = 0,
    hit_max_cycles: bool = False,
) -> float:
    """
    Apply transparent heuristic adjustments to base confidence.

    - +0.05 if internet exploration succeeded and sources found
    - -0.1 if many assumptions flagged as "unknown"
    - -0.1 if agent hit max cycles
    Clamp to 0..1.
    """
    score = base
    if internet_sources_found:
        score += 0.05
    if unknown_assumptions_count >= 3:
        score -= 0.1
    if hit_max_cycles:
        score -= 0.1
    return max(0.0, min(1.0, score))


def count_unknown_assumptions(assumptions: list) -> int:
    """Count assumptions with confidence 'unknown'."""
    count = 0
    for a in assumptions or []:
        conf = getattr(a, "confidence", None) or (
            a.get("confidence") if isinstance(a, dict) else None
        )
        if conf and str(conf).lower() == "unknown":
            count += 1
    return count
