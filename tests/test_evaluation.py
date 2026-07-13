import json
import math
import sqlite3

import pytest

from promptledger import db
from promptledger.core import PromptLedger


@pytest.fixture
def ledger(tmp_path):
    value = PromptLedger(db_path=tmp_path / "ledger.db")
    value.init()
    value.add("demo", "baseline")
    value.add("demo", "candidate")
    value.set_label("demo", 1, "prod")
    value.set_label("demo", 2, "staging")
    return value


def test_new_schema_contains_evaluation_table_and_repeated_init_is_safe(tmp_path):
    ledger = PromptLedger(db_path=tmp_path / "ledger.db")
    ledger.init()
    ledger.init()
    with sqlite3.connect(ledger.db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(evaluation_runs)")}
        version = conn.execute("SELECT version FROM schema_migrations").fetchone()[0]
    assert "evaluation_runs" in tables
    assert columns == {
        "id", "prompt_id", "version", "suite", "model", "dataset_hash",
        "metrics", "metadata", "created_at",
    }
    assert version == db.CURRENT_SCHEMA_VERSION == 6


def test_v5_database_migrates_without_losing_existing_data(tmp_path):
    db_path = tmp_path / "legacy.db"
    legacy = PromptLedger(db_path=db_path)
    legacy.init()
    legacy.add("keep", "content")
    legacy.set_label("keep", 1, "prod")
    legacy.set_marker("keep", 1, "stable")
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE evaluation_runs")
        conn.execute("UPDATE schema_migrations SET version = 5")
        conn.commit()

    legacy.init()
    assert legacy.get("keep", 1).content == "content"
    assert legacy.get_label("keep", "prod") == 1
    assert legacy.get_markers("keep", 1) == ["stable"]
    assert legacy.list_evaluations() == []


def test_record_by_version_and_label_allows_repeated_runs(ledger):
    first = ledger.record_evaluation(
        "demo", 1, "suite", {"accuracy": 0.8}, metadata={"seed": 1}
    )
    second = ledger.record_evaluation(
        "demo", "prod", "suite", {"accuracy": 0.81}, model="model-a"
    )
    assert first.version == second.version == 1
    assert first.id != second.id
    assert ledger.get_evaluation(first.id) == first
    assert len(ledger.list_evaluations(prompt_id="demo", ref="prod")) == 2


def test_list_filters_and_stable_newest_order(ledger):
    a = ledger.record_evaluation("demo", 1, "one", {"score": 1}, model="a")
    b = ledger.record_evaluation("demo", 1, "two", {"score": 2}, model="b")
    with sqlite3.connect(ledger.db_path) as conn:
        conn.execute("UPDATE evaluation_runs SET created_at = '2026-01-01T00:00:00Z'")
        conn.commit()
    assert [run.id for run in ledger.list_evaluations()] == [b.id, a.id]
    assert [run.id for run in ledger.list_evaluations(suite="one")] == [a.id]
    assert [run.id for run in ledger.list_evaluations(model="b")] == [b.id]
    assert ledger.list_evaluations(limit=1)[0].id == b.id


@pytest.mark.parametrize(
    "metrics, message",
    [
        ({}, "non-empty"),
        ({"ok": True}, "booleans"),
        ({"ok": "yes"}, "numeric"),
        ({"ok": math.nan}, "finite"),
        ({"ok": math.inf}, "finite"),
    ],
)
def test_invalid_metrics_are_rejected(ledger, metrics, message):
    with pytest.raises(ValueError, match=message):
        ledger.record_evaluation("demo", 1, "suite", metrics)


def test_invalid_refs_and_metadata_are_rejected(ledger):
    with pytest.raises(ValueError, match="Prompt version"):
        ledger.record_evaluation("demo", 99, "suite", {"score": 1})
    with pytest.raises(ValueError, match="Label not found"):
        ledger.record_evaluation("demo", "unknown", "suite", {"score": 1})
    with pytest.raises(ValueError, match="metadata"):
        ledger.record_evaluation("demo", 1, "suite", {"score": 1}, metadata=[])


def test_malformed_stored_json_has_clear_error(ledger):
    run = ledger.record_evaluation("demo", 1, "suite", {"score": 1})
    with sqlite3.connect(ledger.db_path) as conn:
        conn.execute("UPDATE evaluation_runs SET metrics = ? WHERE id = ?", ("{", run.id))
        conn.commit()
    with pytest.raises(ValueError, match="malformed JSON"):
        ledger.get_evaluation(run.id)


def test_comparison_uses_latest_compatible_run_and_reports_missing_metrics(ledger):
    ledger.record_evaluation("demo", "prod", "suite", {"accuracy": 0.7}, model="m")
    ledger.record_evaluation(
        "demo", "prod", "suite", {"accuracy": 0.8, "old": 1}, model="m"
    )
    ledger.record_evaluation(
        "demo", "staging", "suite", {"accuracy": 0.9, "new": 2}, model="m"
    )
    comparison = ledger.compare_evaluations(
        "demo", "prod", "staging", suite="suite", model="m"
    )
    assert comparison.from_ref["resolved_version"] == 1
    assert comparison.to_ref["resolved_version"] == 2
    assert comparison.metrics[0].metric == "accuracy"
    assert comparison.metrics[0].baseline == 0.8
    assert comparison.metrics[0].delta == pytest.approx(0.1)
    assert comparison.missing_from == ("new",)
    assert comparison.missing_to == ("old",)


def test_comparison_zero_baseline_and_missing_or_incompatible_runs(ledger):
    ledger.record_evaluation("demo", 1, "suite", {"score": 0}, model="m")
    ledger.record_evaluation("demo", 2, "suite", {"score": 1}, model="m")
    comparison = ledger.compare_evaluations("demo", 1, 2)
    assert comparison.metrics[0].delta_percent is None
    with pytest.raises(ValueError, match="baseline"):
        ledger.compare_evaluations("demo", 1, 2, suite="missing")
    ledger.record_evaluation("demo", 1, "suite", {"score": 0}, model="other")
    with pytest.raises(ValueError, match="candidate"):
        ledger.compare_evaluations("demo", 1, 2, model="other")


def _policy():
    return {
        "suite": "suite",
        "model": "m",
        "metrics": {
            "accuracy": {"direction": "higher", "max_regression": 0.02},
            "latency": {"direction": "lower", "max_regression_percent": 15},
        },
    }


def test_gate_passes_higher_and_lower_thresholds(ledger):
    ledger.record_evaluation("demo", 1, "suite", {"accuracy": 0.8, "latency": 100}, model="m")
    ledger.record_evaluation("demo", 2, "suite", {"accuracy": 0.79, "latency": 110}, model="m")
    result = ledger.evaluate_gate("demo", "prod", "staging", _policy())
    assert result.passed is True
    assert all(item.passed for item in result.metrics)


def test_gate_fails_regression_missing_metric_and_zero_baseline(ledger):
    ledger.record_evaluation("demo", 1, "suite", {"accuracy": 0.8, "latency": 0}, model="m")
    ledger.record_evaluation("demo", 2, "suite", {"accuracy": 0.7, "latency": 1}, model="m")
    result = ledger.evaluate_gate("demo", 1, 2, _policy())
    assert result.passed is False
    assert "exceeds" in result.metrics[0].message
    assert "zero baseline" in result.metrics[1].message

    missing_policy = {"suite": "suite", "model": "m", "metrics": {
        "missing": {"direction": "higher", "max_regression": 0}
    }}
    assert ledger.evaluate_gate("demo", 1, 2, missing_policy).passed is False


@pytest.mark.parametrize(
    "policy",
    [
        [],
        {},
        {"metrics": {}},
        {"metrics": {"x": {"direction": "sideways", "max_regression": 1}}},
        {"metrics": {"x": {"direction": "higher", "max_regression": -1}}},
        {"metrics": {"x": {"direction": "higher"}}},
    ],
)
def test_malformed_gate_policies_are_rejected(ledger, policy):
    with pytest.raises(ValueError):
        ledger.evaluate_gate("demo", 1, 2, policy)


def test_evaluation_export_is_deterministic(ledger, tmp_path):
    ledger.record_evaluation("demo", 1, "suite", {"z": 1, "a": 2})
    first = ledger.export_evaluations(tmp_path / "a.jsonl")
    second = ledger.export_evaluations(tmp_path / "b.jsonl")
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["metrics"] == {"a": 2, "z": 1}
