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
