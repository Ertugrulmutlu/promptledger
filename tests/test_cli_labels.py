import os
import sys
from pathlib import Path
from subprocess import run


def _run_cli(args, cwd: Path):
    command = [sys.executable, "-m", "promptledger.cli", *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return run(command, cwd=cwd, text=True, capture_output=True, env=env)


def test_label_set_get_list(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "hello"], cwd=tmp_path)
    set_res = _run_cli(["label", "set", "--id", "demo", "--version", "1", "--name", "prod"], cwd=tmp_path)
    assert set_res.returncode == 0

    get_res = _run_cli(["label", "get", "--id", "demo", "--name", "prod"], cwd=tmp_path)
    assert get_res.returncode == 0
    assert "demo@1" in get_res.stdout

    list_res = _run_cli(["label", "list", "--id", "demo"], cwd=tmp_path)
    assert list_res.returncode == 0
    assert "prod" in list_res.stdout


def test_label_diff_by_name(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "line1\nline2"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "line1\nline3"], cwd=tmp_path)
    _run_cli(["label", "set", "--id", "demo", "--version", "1", "--name", "prod"], cwd=tmp_path)
    _run_cli(["label", "set", "--id", "demo", "--version", "2", "--name", "staging"], cwd=tmp_path)

    diff_res = _run_cli(["diff", "--id", "demo", "--from", "prod", "--to", "staging"], cwd=tmp_path)
    assert diff_res.returncode == 0
    assert "-line2" in diff_res.stdout
    assert "+line3" in diff_res.stdout


def test_diff_metadata_mode(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(
        ["add", "--id", "demo", "--text", "line1\nline2", "--reason", "first", "--env", "dev"],
        cwd=tmp_path,
    )
    _run_cli(
        ["add", "--id", "demo", "--text", "line1\nline3", "--reason", "second", "--env", "prod"],
        cwd=tmp_path,
    )

    diff_res = _run_cli(
        ["diff", "--id", "demo", "--from", "1", "--to", "2", "--mode", "metadata"],
        cwd=tmp_path,
    )
    assert diff_res.returncode == 0
    assert '-  "reason": "first"' in diff_res.stdout
    assert '+  "reason": "second"' in diff_res.stdout


def test_status_command(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "alpha", "--text", "one"], cwd=tmp_path)
    _run_cli(["add", "--id", "alpha", "--text", "two"], cwd=tmp_path)
    _run_cli(["add", "--id", "beta", "--text", "single"], cwd=tmp_path)
    _run_cli(["label", "set", "--id", "alpha", "--version", "2", "--name", "prod"], cwd=tmp_path)
    _run_cli(["label", "set", "--id", "alpha", "--version", "1", "--name", "staging"], cwd=tmp_path)

    res = _run_cli(["status"], cwd=tmp_path)
    assert res.returncode == 0
    lines = [line for line in res.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    alpha = lines[0].split("\t")
    beta = lines[1].split("\t")
    assert len(alpha) == 4
    assert len(beta) == 4
    assert alpha[0] == "alpha"
    assert beta[0] == "beta"
    assert alpha[1] == "2"
    assert beta[1] == "1"
    assert alpha[3] == "prod->2,staging->1"
    assert beta[3] == ""


def test_label_history(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "hello"], cwd=tmp_path)
    _run_cli(["label", "set", "--id", "demo", "--version", "1", "--name", "prod"], cwd=tmp_path)
    _run_cli(["label", "set", "--id", "demo", "--version", "1", "--name", "staging"], cwd=tmp_path)
    _run_cli(["label", "set", "--id", "demo", "--version", "1", "--name", "prod"], cwd=tmp_path)

    res = _run_cli(["label", "history", "--id", "demo", "--name", "prod"], cwd=tmp_path)
    assert res.returncode == 0
    lines = [line for line in res.stdout.splitlines() if line.strip()]
    assert len(lines) >= 2
    cols = lines[0].split("\t")
    assert len(cols) == 5
    assert cols[0] == "demo"
    assert cols[1] == "prod"

def test_label_set_unknown_version(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "hello"], cwd=tmp_path)
    res = _run_cli(["label", "set", "--id", "demo", "--version", "2", "--name", "prod"], cwd=tmp_path)
    assert res.returncode == 2


def test_label_get_unknown_label(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "hello"], cwd=tmp_path)
    res = _run_cli(["label", "get", "--id", "demo", "--name", "missing"], cwd=tmp_path)
    assert res.returncode == 2
