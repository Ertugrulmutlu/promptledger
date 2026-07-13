"""Evaluation run validation, comparison, and regression gate logic."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping


Numeric = int | float


@dataclass(frozen=True)
class EvaluationRun:
    id: int
    prompt_id: str
    version: int
    suite: str
    model: str | None
    dataset_hash: str | None
    metrics: dict[str, Numeric]
    metadata: dict[str, Any] | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetricDelta:
    metric: str
    baseline: Numeric
    candidate: Numeric
    delta: Numeric
    delta_percent: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationComparison:
    prompt_id: str
    from_ref: dict[str, Any]
    to_ref: dict[str, Any]
    baseline_run: EvaluationRun
    candidate_run: EvaluationRun
    suite: str
    model: str | None
    metrics: tuple[MetricDelta, ...]
    missing_from: tuple[str, ...]
    missing_to: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["common_metrics"] = [item.metric for item in self.metrics]
        return result


@dataclass(frozen=True)
class GateRule:
    metric: str
    direction: str
    max_regression: float | None = None
    max_regression_percent: float | None = None


@dataclass(frozen=True)
class GateMetricResult:
    metric: str
    passed: bool
    direction: str
    baseline: Numeric | None
    candidate: Numeric | None
    regression: float | None
    regression_percent: float | None
    max_regression: float | None
    max_regression_percent: float | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateResult:
    passed: bool
    comparison: EvaluationComparison
    metrics: tuple[GateMetricResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_metrics(metrics: Any) -> dict[str, Numeric]:
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("Metrics must be a non-empty JSON object.")
    validated: dict[str, Numeric] = {}
    for name, value in metrics.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Metric names must be non-empty strings.")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Metric '{name}' must be numeric (booleans are not allowed).")
        if not math.isfinite(value):
            raise ValueError(f"Metric '{name}' must be finite.")
        validated[name] = value
    return validated


def validate_metadata(metadata: Any) -> dict[str, Any] | None:
    if metadata is None:
        return None
    if not isinstance(metadata, dict):
        raise ValueError("Evaluation metadata must be a JSON object.")
    _validate_json_value(metadata, "Evaluation metadata")
    return metadata


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite numbers.")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} object keys must be strings.")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ValueError(f"{path} must contain only JSON values.")


def compare_runs(
    prompt_id: str,
    from_ref: Mapping[str, Any],
    to_ref: Mapping[str, Any],
    baseline: EvaluationRun,
    candidate: EvaluationRun,
) -> EvaluationComparison:
    if baseline.suite != candidate.suite or baseline.model != candidate.model:
        raise ValueError("Evaluation runs must have the same suite and model.")
    common = sorted(set(baseline.metrics) & set(candidate.metrics))
    deltas = []
    for metric in common:
        left = baseline.metrics[metric]
        right = candidate.metrics[metric]
        delta = right - left
        percent = None if left == 0 else (delta / abs(left)) * 100
        deltas.append(MetricDelta(metric, left, right, delta, percent))
    return EvaluationComparison(
        prompt_id=prompt_id,
        from_ref=dict(from_ref),
        to_ref=dict(to_ref),
        baseline_run=baseline,
        candidate_run=candidate,
        suite=baseline.suite,
        model=baseline.model,
        metrics=tuple(deltas),
        missing_from=tuple(sorted(set(candidate.metrics) - set(baseline.metrics))),
        missing_to=tuple(sorted(set(baseline.metrics) - set(candidate.metrics))),
    )


def parse_gate_policy(policy: Any) -> tuple[str | None, str | None, tuple[GateRule, ...]]:
    if not isinstance(policy, dict):
        raise ValueError("Gate policy must be a JSON object.")
    unknown_policy = set(policy) - {"suite", "model", "metrics"}
    if unknown_policy:
        raise ValueError(
            f"Gate policy has unsupported fields: {', '.join(sorted(unknown_policy))}."
        )
    suite = policy.get("suite")
    model = policy.get("model")
    if suite is not None and (not isinstance(suite, str) or not suite.strip()):
        raise ValueError("Gate policy suite must be a non-empty string.")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError("Gate policy model must be a non-empty string.")
    metrics = policy.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("Gate policy metrics must be a non-empty JSON object.")
    rules = []
    for metric in sorted(metrics):
        raw = metrics[metric]
        if not isinstance(metric, str) or not metric.strip() or not isinstance(raw, dict):
            raise ValueError("Each gate metric must have a named JSON object rule.")
        direction = raw.get("direction")
        if direction not in {"higher", "lower"}:
            raise ValueError(f"Metric '{metric}' direction must be 'higher' or 'lower'.")
        absolute = _threshold(raw, metric, "max_regression")
        percent = _threshold(raw, metric, "max_regression_percent")
        if absolute is None and percent is None:
            raise ValueError(f"Metric '{metric}' must configure at least one regression threshold.")
        unknown = set(raw) - {"direction", "max_regression", "max_regression_percent"}
        if unknown:
            raise ValueError(f"Metric '{metric}' has unsupported policy fields: {', '.join(sorted(unknown))}.")
        rules.append(GateRule(metric, direction, absolute, percent))
    return suite, model, tuple(rules)


def evaluate_comparison_gate(
    comparison: EvaluationComparison, rules: tuple[GateRule, ...]
) -> GateResult:
    baseline = comparison.baseline_run.metrics
    candidate = comparison.candidate_run.metrics
    results = tuple(_evaluate_rule(rule, baseline, candidate) for rule in rules)
    return GateResult(all(item.passed for item in results), comparison, results)


def _threshold(raw: dict[str, Any], metric: str, key: str) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Metric '{metric}' {key} must be a finite number.")
    if value < 0:
        raise ValueError(f"Metric '{metric}' {key} cannot be negative.")
    return float(value)


def _evaluate_rule(
    rule: GateRule,
    baseline_metrics: Mapping[str, Numeric],
    candidate_metrics: Mapping[str, Numeric],
) -> GateMetricResult:
    if rule.metric not in baseline_metrics or rule.metric not in candidate_metrics:
        missing = []
        if rule.metric not in baseline_metrics:
            missing.append("baseline")
        if rule.metric not in candidate_metrics:
            missing.append("candidate")
        return GateMetricResult(
            rule.metric, False, rule.direction,
            baseline_metrics.get(rule.metric), candidate_metrics.get(rule.metric),
            None, None, rule.max_regression, rule.max_regression_percent,
            f"missing from {' and '.join(missing)} evaluation metrics",
        )

    baseline = baseline_metrics[rule.metric]
    candidate = candidate_metrics[rule.metric]
    signed = baseline - candidate if rule.direction == "higher" else candidate - baseline
    regression = max(0.0, float(signed))
    regression_percent = None if baseline == 0 else regression / abs(float(baseline)) * 100
    failures = []
    if rule.max_regression is not None and _exceeds(regression, rule.max_regression):
        failures.append(f"absolute regression {regression:g} exceeds {rule.max_regression:g}")
    if rule.max_regression_percent is not None:
        if baseline == 0 and regression > 0:
            failures.append("percentage regression is undefined for a zero baseline")
        elif regression_percent is not None and _exceeds(
            regression_percent, rule.max_regression_percent
        ):
            failures.append(
                f"regression {regression_percent:.2f}% exceeds {rule.max_regression_percent:.2f}%"
            )
    if failures:
        message = "; ".join(failures)
    elif regression == 0:
        improvement = (candidate - baseline) if rule.direction == "higher" else (baseline - candidate)
        message = f"candidate improved by {improvement:g}" if improvement > 0 else "no regression"
    elif rule.max_regression_percent is not None and regression_percent is not None:
        message = (
            f"regression {regression_percent:.2f}% within allowed "
            f"{rule.max_regression_percent:.2f}%"
        )
    else:
        message = f"regression {regression:g} within allowed {rule.max_regression:g}"
    return GateMetricResult(
        rule.metric, not failures, rule.direction, baseline, candidate, regression,
        regression_percent, rule.max_regression, rule.max_regression_percent, message,
    )


def _exceeds(value: float, threshold: float) -> bool:
    return value > threshold and not math.isclose(value, threshold, rel_tol=1e-12, abs_tol=1e-12)
