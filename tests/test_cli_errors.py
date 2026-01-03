import os
import sys
from pathlib import Path
from subprocess import run


def _run_cli(args, cwd: Path, env=None):
    command = [sys.executable, "-m", "promptledger.cli", *args]
    final_env = os.environ.copy()
    final_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    if env:
        final_env.update(env)
    return run(command, cwd=cwd, text=True, capture_output=True, env=final_env)


def test_add_rejects_both_file_and_text(tmp_path):
    result = _run_cli(
        ["add", "--id", "demo", "--text", "hi", "--file", "demo.txt"],
        cwd=tmp_path,
    )
    assert result.returncode == 2


def test_add_rejects_neither_file_nor_text(tmp_path):
    result = _run_cli(["add", "--id", "demo"], cwd=tmp_path)
    assert result.returncode == 2


def test_show_unknown_id_returns_2(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    result = _run_cli(["show", "--id", "missing"], cwd=tmp_path)
    assert result.returncode == 2
    assert "not found" in result.stderr.lower()


def test_diff_unknown_version_returns_2(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "hello"], cwd=tmp_path)
    result = _run_cli(["diff", "--id", "demo", "--from", "1", "--to", "2"], cwd=tmp_path)
    assert result.returncode == 2
    assert "not found" in result.stderr.lower()
