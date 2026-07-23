"""Tests for Δr̄ acceptance gates."""

from agent_core.skill_evolution.validation import evaluate_acceptance_gates


def test_gate_accepts_positive_delta():
    ok, reason = evaluate_acceptance_gates(0.08, threshold=0.05)
    assert ok is True
    assert reason == "ok"


def test_gate_rejects_small_delta():
    ok, reason = evaluate_acceptance_gates(0.01, threshold=0.05)
    assert ok is False
    assert "score_delta" in reason


def test_gate_rejects_critical_regression_even_if_avg_up():
    ok, _ = evaluate_acceptance_gates(0.2, threshold=0.05, critical_regressions=1)
    assert ok is False


def test_gate_rejects_step_worsening():
    ok, reason = evaluate_acceptance_gates(
        0.1,
        threshold=0.05,
        old_avg_steps=10.0,
        new_avg_steps=13.0,
        max_step_worsen=0.15,
    )
    assert ok is False
    assert "steps_worsened" in reason


def test_gate_allows_mild_step_increase():
    ok, _ = evaluate_acceptance_gates(
        0.1,
        threshold=0.05,
        old_avg_steps=10.0,
        new_avg_steps=11.0,
        max_step_worsen=0.15,
    )
    assert ok is True
