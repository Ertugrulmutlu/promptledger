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


def test_search_and_list_filter_by_collection_and_role(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(
        [
            "add",
            "--id",
            "alpha",
            "--text",
            "Find me",
            "--collection",
            "chunking-lab",
            "--role",
            "system",
        ],
        cwd=tmp_path,
    )
    _run_cli(
        [
            "add",
            "--id",
            "beta",
            "--text",
            "Find me too",
            "--collection",
            "chunking-lab",
            "--role",
            "eval",
        ],
        cwd=tmp_path,
    )
    _run_cli(
        [
            "add",
            "--id",
            "gamma",
            "--text",
            "Find me three",
            "--collection",
            "support-bot",
            "--role",
            "system",
        ],
        cwd=tmp_path,
    )

    list_result = _run_cli(
        ["list", "--collection", "chunking-lab", "--role", "eval"],
        cwd=tmp_path,
    )
    search_result = _run_cli(
        ["search", "--collection", "chunking-lab", "--role", "system"],
        cwd=tmp_path,
    )

    assert list_result.returncode == 0
    assert "beta" in list_result.stdout
    assert "alpha" not in list_result.stdout
    assert "gamma" not in list_result.stdout

    assert search_result.returncode == 0
    assert "alpha" in search_result.stdout
    assert "beta" not in search_result.stdout
    assert "gamma" not in search_result.stdout
