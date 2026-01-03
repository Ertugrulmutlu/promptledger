import os
import sys
from pathlib import Path
from subprocess import run


def _run_cli(args, cwd: Path):
    command = [sys.executable, "-m", "promptledger.cli", *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return run(command, cwd=cwd, text=True, capture_output=True, env=env)


def test_search_finds_entries(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(
        ["add", "--id", "demo", "--text", "Hello world", "--author", "Ada", "--tags", "greeting", "--env", "dev"],
        cwd=tmp_path,
    )
    _run_cli(
        ["add", "--id", "demo", "--text", "Another prompt", "--author", "Ada", "--tags", "misc", "--env", "dev"],
        cwd=tmp_path,
    )
    result = _run_cli(["search", "--contains", "Hello"], cwd=tmp_path)
    assert result.returncode == 0
    assert "demo" in result.stdout


def test_search_filters(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(
        ["add", "--id", "alpha", "--text", "Find me", "--author", "Ada", "--tags", "blue", "--env", "dev"],
        cwd=tmp_path,
    )
    _run_cli(
        ["add", "--id", "beta", "--text", "Find me too", "--author", "Bob", "--tags", "red", "--env", "prod"],
        cwd=tmp_path,
    )
    result = _run_cli(
        ["search", "--contains", "Find me", "--author", "Ada", "--tag", "blue", "--env", "dev"],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "alpha" in result.stdout
    assert "beta" not in result.stdout
