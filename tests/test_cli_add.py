import os
import sys
from pathlib import Path
from subprocess import run

from promptledger.core import PromptLedger


def _run_cli(args, cwd: Path):
    command = [sys.executable, "-m", "promptledger.cli", *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["PROMPTLEDGER_HOME"] = str((cwd / "home").resolve())
    return run(command, cwd=cwd, text=True, capture_output=True, env=env)


def test_quick_add_reuses_metadata(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(
        [
            "add",
            "--id",
            "onboarding",
            "--text",
            "first version",
            "--author",
            "Ada",
            "--tags",
            "alpha,beta",
            "--env",
            "dev",
            "--collection",
            "chunking-lab",
            "--role",
            "system",
        ],
        cwd=tmp_path,
    )

    result = _run_cli(
        ["add", "--id", "onboarding", "--text", "second version", "--quick"],
        cwd=tmp_path,
    )

    assert result.returncode == 0
    ledger = PromptLedger(db_path=tmp_path / "home" / "promptledger.db")
    record = ledger.get("onboarding", 2)
    assert record is not None
    assert record.author == "Ada"
    assert record.tags == ["alpha", "beta"]
    assert record.env == "dev"
    assert record.collection == "chunking-lab"
    assert record.role == "system"


def test_quick_add_override_beats_reused_metadata(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(
        [
            "add",
            "--id",
            "demo",
            "--text",
            "first version",
            "--env",
            "dev",
            "--role",
            "system",
        ],
        cwd=tmp_path,
    )

    result = _run_cli(
        [
            "add",
            "--id",
            "demo",
            "--text",
            "second version",
            "--quick",
            "--env",
            "staging",
            "--role",
            "eval",
        ],
        cwd=tmp_path,
    )

    assert result.returncode == 0
    ledger = PromptLedger(db_path=tmp_path / "home" / "promptledger.db")
    record = ledger.get("demo", 2)
    assert record is not None
    assert record.env == "staging"
    assert record.role == "eval"


def test_quick_add_with_no_previous_version(tmp_path):
    _run_cli(["init"], cwd=tmp_path)

    result = _run_cli(
        ["add", "--id", "fresh", "--text", "first version", "--quick"],
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert "Added fresh version 1" in result.stdout

    ledger = PromptLedger(db_path=tmp_path / "home" / "promptledger.db")
    record = ledger.get("fresh", 1)
    assert record is not None
    assert record.author is None
    assert record.tags is None
    assert record.env is None
    assert record.collection is None
    assert record.role is None


def test_quick_add_reason_remains_optional(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(
        ["add", "--id", "demo", "--text", "first version", "--reason", "initial reason"],
        cwd=tmp_path,
    )

    result = _run_cli(
        ["add", "--id", "demo", "--text", "second version", "--quick"],
        cwd=tmp_path,
    )

    assert result.returncode == 0
    ledger = PromptLedger(db_path=tmp_path / "home" / "promptledger.db")
    record = ledger.get("demo", 2)
    assert record is not None
    assert record.reason is None


def test_quick_add_respects_unchanged_content_behavior(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(
        ["add", "--id", "demo", "--text", "same content", "--author", "Ada", "--env", "dev"],
        cwd=tmp_path,
    )

    result = _run_cli(
        ["add", "--id", "demo", "--text", "same content", "--quick"],
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert "No change detected for demo" in result.stdout

    ledger = PromptLedger(db_path=tmp_path / "home" / "promptledger.db")
    assert ledger.get("demo", 2) is None


def test_add_collection_normalization_and_show_output(tmp_path):
    _run_cli(["init"], cwd=tmp_path)

    add_result = _run_cli(
        [
            "add",
            "--id",
            "demo",
            "--text",
            "hello",
            "--collection",
            "  chunking-lab  ",
            "--role",
            "modelfile",
        ],
        cwd=tmp_path,
    )
    show_result = _run_cli(["show", "--id", "demo", "--version", "1"], cwd=tmp_path)

    assert add_result.returncode == 0
    assert show_result.returncode == 0
    assert "collection: chunking-lab" in show_result.stdout
    assert "role: modelfile" in show_result.stdout

    ledger = PromptLedger(db_path=tmp_path / "home" / "promptledger.db")
    record = ledger.get("demo", 1)
    assert record is not None
    assert record.collection == "chunking-lab"
    assert record.role == "modelfile"


def test_whitespace_only_collection_is_absent(tmp_path):
    _run_cli(["init"], cwd=tmp_path)

    result = _run_cli(
        ["add", "--id", "demo", "--text", "hello", "--collection", "   "],
        cwd=tmp_path,
    )

    assert result.returncode == 0
    ledger = PromptLedger(db_path=tmp_path / "home" / "promptledger.db")
    record = ledger.get("demo", 1)
    assert record is not None
    assert record.collection is None
