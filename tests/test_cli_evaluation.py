import json
import os
import subprocess
import sys
from pathlib import Path


def _run_cli(args, cwd):
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    env["PROMPTLEDGER_HOME"] = str((cwd / "home").resolve())
    return subprocess.run(
        [sys.executable, "-m", "promptledger.cli", *args],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def _seed(tmp_path):
    assert _run_cli(["init"], tmp_path).returncode == 0
    assert _run_cli(["add", "--id", "demo", "--text", "one"], tmp_path).returncode == 0
    assert _run_cli(["add", "--id", "demo", "--text", "two"], tmp_path).returncode == 0
    assert _run_cli(
        ["label", "set", "--id", "demo", "--version", "1", "--name", "prod"], tmp_path
    ).returncode == 0
    assert _run_cli(
        ["label", "set", "--id", "demo", "--version", "2", "--name", "staging"], tmp_path
    ).returncode == 0


def test_eval_record_inline_list_show_and_labels(tmp_path):
    _seed(tmp_path)
    recorded = _run_cli([
        "eval", "record", "--id", "demo", "--ref", "prod", "--suite", "support",
        "--model", "m", "--metrics", '{"accuracy":0.8}', "--metadata", '{"seed":1}',
    ], tmp_path)
    assert recorded.returncode == 0
    assert "run 1" in recorded.stdout
    listed = _run_cli(["eval", "list", "--id", "demo", "--ref", "prod"], tmp_path)
    assert listed.returncode == 0
    assert "1\tdemo\t1\tsupport\tm" in listed.stdout
    shown = _run_cli(["eval", "show", "--run", "1"], tmp_path)
    assert shown.returncode == 0
    assert json.loads(shown.stdout)["metadata"] == {"seed": 1}


def test_eval_record_file_and_invalid_json(tmp_path):
    _seed(tmp_path)
    payload = tmp_path / "evaluation.json"
    payload.write_text(json.dumps({
        "suite": "support", "model": "m", "dataset_hash": "sha256:a",
        "metrics": {"score": 1}, "metadata": {"seed": 2},
    }), encoding="utf-8")
    result = _run_cli([
        "eval", "record", "--id", "demo", "--ref", "staging", "--file", str(payload)
    ], tmp_path)
    assert result.returncode == 0
    invalid = _run_cli([
        "eval", "record", "--id", "demo", "--ref", "staging", "--suite", "x",
        "--metrics", "{",
    ], tmp_path)
    assert invalid.returncode == 2
    assert "Invalid metrics JSON" in invalid.stderr
    assert "Traceback" not in invalid.stderr


def test_eval_compare_and_gate_exit_codes(tmp_path):
    _seed(tmp_path)
    for ref, metrics in [
        ("prod", '{"accuracy":0.8,"latency":100}'),
        ("staging", '{"accuracy":0.81,"latency":110}'),
    ]:
        assert _run_cli([
            "eval", "record", "--id", "demo", "--ref", ref, "--suite", "support",
            "--model", "m", "--metrics", metrics,
        ], tmp_path).returncode == 0
    compared = _run_cli([
        "eval", "compare", "--id", "demo", "--from", "prod", "--to", "staging",
        "--suite", "support", "--model", "m",
    ], tmp_path)
    assert compared.returncode == 0
    assert "Evaluation comparison: demo" in compared.stdout
    assert "accuracy" in compared.stdout and "+0.01" in compared.stdout

    pass_policy = tmp_path / "pass.json"
    pass_policy.write_text(json.dumps({"suite": "support", "model": "m", "metrics": {
        "accuracy": {"direction": "higher", "max_regression": 0},
        "latency": {"direction": "lower", "max_regression_percent": 15},
    }}), encoding="utf-8")
    passed = _run_cli([
        "eval", "gate", "--id", "demo", "--from", "prod", "--to", "staging",
        "--policy", str(pass_policy),
    ], tmp_path)
    assert passed.returncode == 0
    assert "Gate passed." in passed.stdout

    fail_policy = tmp_path / "fail.json"
    fail_policy.write_text(json.dumps({"suite": "support", "model": "m", "metrics": {
        "latency": {"direction": "lower", "max_regression_percent": 5},
    }}), encoding="utf-8")
    failed = _run_cli([
        "eval", "gate", "--id", "demo", "--from", "prod", "--to", "staging",
        "--policy", str(fail_policy),
    ], tmp_path)
    assert failed.returncode == 3
    assert "FAIL latency" in failed.stdout and "Gate failed." in failed.stdout

    fail_policy.write_text("{", encoding="utf-8")
    invalid = _run_cli([
        "eval", "gate", "--id", "demo", "--from", "prod", "--to", "staging",
        "--policy", str(fail_policy),
    ], tmp_path)
    assert invalid.returncode == 2
    assert "Invalid gate policy JSON" in invalid.stderr


def test_eval_export_jsonl(tmp_path):
    _seed(tmp_path)
    _run_cli([
        "eval", "record", "--id", "demo", "--ref", "1", "--suite", "s",
        "--metrics", '{"score":1}',
    ], tmp_path)
    out = tmp_path / "runs.jsonl"
    result = _run_cli([
        "eval", "export", "--id", "demo", "--format", "jsonl", "--out", str(out)
    ], tmp_path)
    assert result.returncode == 0
    assert json.loads(out.read_text(encoding="utf-8"))["version"] == 1
