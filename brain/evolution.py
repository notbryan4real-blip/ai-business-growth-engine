"""Bounded, deterministic self-improvement evaluator.

No network calls, file writes, code execution, or autonomous deployment.
A caller supplies measurements from a controlled experiment.
"""
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class EvolutionPolicy:
    max_iterations: int = 3
    max_model_calls: int = 12
    max_cost_usd: float = 0.50
    min_quality_gain: float = 0.02
    max_regression: float = 0.0


@dataclass(frozen=True)
class Evaluation:
    accepted: bool
    reason: str
    needs_owner_approval: bool = False


OWNER_GATED = frozenset({
    "production_deploy", "permission_change", "financial_action",
    "safety_policy_change", "secret_access", "external_outreach",
})


def evaluate_candidate(
    *,
    baseline: Mapping[str, float],
    candidate: Mapping[str, float],
    iteration: int,
    model_calls: int,
    cost_usd: float,
    action: str = "prompt_revision",
    policy: EvolutionPolicy = EvolutionPolicy(),
) -> Evaluation:
    """Evaluate quality (higher better), errors and latency (lower better).

    The baseline and candidate must have independently measured metrics.
    This does not prove benchmark integrity; callers must supply trusted tests.
    """
    if action in OWNER_GATED:
        return Evaluation(False, "Owner approval required for consequential action", True)
    if action not in {"prompt_revision", "routing_revision", "knowledge_proposal"}:
        return Evaluation(False, "Action is not allowlisted", True)
    if iteration < 1 or iteration > policy.max_iterations:
        return Evaluation(False, "Iteration limit exceeded")
    if model_calls < 0 or model_calls > policy.max_model_calls:
        return Evaluation(False, "Model-call budget exceeded")
    if cost_usd < 0 or cost_usd > policy.max_cost_usd:
        return Evaluation(False, "Cost budget exceeded")
    keys = ("quality", "errors", "latency")
    if any(k not in baseline or k not in candidate for k in keys):
        return Evaluation(False, "Required benchmark metrics missing")
    import math
    if any(not math.isfinite(float(m[k])) for m in (baseline, candidate) for k in keys):
        return Evaluation(False, "Invalid benchmark metric")
    if not (0 <= baseline["quality"] <= 1 and 0 <= candidate["quality"] <= 1):
        return Evaluation(False, "Quality must be normalized to [0,1]")
    if any(m[k] < 0 for m in (baseline, candidate) for k in ("errors", "latency")):
        return Evaluation(False, "Negative error or latency metric")
    if candidate["quality"] - baseline["quality"] < policy.min_quality_gain:
        return Evaluation(False, "Quality gain below acceptance threshold")
    if candidate["errors"] > baseline["errors"] + policy.max_regression:
        return Evaluation(False, "Error regression detected")
    if candidate["latency"] > baseline["latency"] * 1.1:
        return Evaluation(False, "Latency regression above 10%")
    return Evaluation(True, "Candidate passed bounded evaluation; eligible for staged review")
