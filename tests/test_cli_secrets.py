import os
import sys
from pathlib import Path
from subprocess import run


def _run_cli(args, cwd: Path):
    command = [sys.executable, "-m", "promptledger.cli", *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return run(command, cwd=cwd, text=True, capture_output=True, env=env)


def test_cli_secret_warning(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    result = _run_cli(["add", "--id", "secret", "--text", "sk-123"], cwd=tmp_path)
    assert result.returncode == 0
    assert "possible secret" in result.stderr.lower()


def test_cli_no_secret_warning(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    result = _run_cli(
        ["add", "--id", "secret", "--text", "sk-123", "--no-secret-warn"],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "secret" not in result.stderr.lower()
