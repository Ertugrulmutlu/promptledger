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


def test_review_unknown_label_returns_2(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "hello"], cwd=tmp_path)
    result = _run_cli(["review", "--id", "demo", "--from", "missing", "--to", "1"], cwd=tmp_path)
    assert result.returncode == 2
    assert "label not found" in result.stderr.lower()


def test_export_review_missing_args_returns_2(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    result = _run_cli(["export", "review", "--format", "md", "--out", "review.md"], cwd=tmp_path)
    assert result.returncode == 2
    assert "requires --id, --from, and --to" in result.stderr.lower()


def test_add_invalid_role_returns_2(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    result = _run_cli(
        ["add", "--id", "demo", "--text", "hello", "--role", "assistant"],
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr.lower()


def test_enzo_easter_egg_prints_message(tmp_path):
    result = _run_cli(["enzo"], cwd=tmp_path)
    assert result.returncode == 0
    assert "UnclaEnzo" in result.stdout
    assert "lower-friction iteration" in result.stdout
    assert "prompt-library thinking" in result.stdout
    assert "messy workflows" in result.stdout
    assert "funny idea" in result.stdout.lower()
