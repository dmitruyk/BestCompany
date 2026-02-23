"""Tests for confidence heuristic."""
import pytest

from apps.agents.confidence import adjust_confidence, count_unknown_assumptions


def test_adjust_confidence_base() -> None:
    """Base confidence unchanged when no modifiers."""
    assert adjust_confidence(0.7) == 0.7


def test_adjust_confidence_internet_bonus() -> None:
    """+0.05 when internet sources found."""
    assert adjust_confidence(0.7, internet_sources_found=True) == 0.75


def test_adjust_confidence_unknown_penalty() -> None:
    """-0.1 when 3+ unknown assumptions."""
    assert adjust_confidence(0.7, unknown_assumptions_count=3) == 0.6


def test_adjust_confidence_max_cycles_penalty() -> None:
    """-0.1 when hit max cycles."""
    assert adjust_confidence(0.7, hit_max_cycles=True) == 0.6


def test_adjust_confidence_clamped() -> None:
    """Result clamped to 0..1."""
    assert adjust_confidence(1.0, internet_sources_found=True) == 1.0
    assert adjust_confidence(0.0, unknown_assumptions_count=5) == 0.0


def test_count_unknown_assumptions() -> None:
    """Counts assumptions with confidence=unknown."""
    class A:
        def __init__(self, c: str):
            self.confidence = c
    items = [A("high"), A("unknown"), A("unknown"), A("low")]
    assert count_unknown_assumptions(items) == 2
