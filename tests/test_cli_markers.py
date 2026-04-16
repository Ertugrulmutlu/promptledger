import os
import sys
from pathlib import Path
from subprocess import run


def _run_cli(args, cwd: Path):
    command = [sys.executable, "-m", "promptledger.cli", *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return run(command, cwd=cwd, text=True, capture_output=True, env=env)


def test_marker_set_show_list_and_remove(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "one"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "two"], cwd=tmp_path)

    set_res = _run_cli(
        ["marker", "set", "--id", "demo", "--version", "2", "--name", "stable"],
        cwd=tmp_path,
    )
    assert set_res.returncode == 0
    assert "stable" in set_res.stdout

    show_res = _run_cli(["marker", "show", "--id", "demo", "--version", "2"], cwd=tmp_path)
    assert show_res.returncode == 0
    assert show_res.stdout.strip() == "stable"

    list_res = _run_cli(["marker", "list", "--id", "demo"], cwd=tmp_path)
    assert list_res.returncode == 0
    assert "demo\t2\tstable\t" in list_res.stdout

    remove_res = _run_cli(
        ["marker", "remove", "--id", "demo", "--version", "2", "--name", "stable"],
        cwd=tmp_path,
    )
    assert remove_res.returncode == 0
    assert "Removed stable" in remove_res.stdout

    show_after_remove = _run_cli(["marker", "show", "--id", "demo", "--version", "2"], cwd=tmp_path)
    assert show_after_remove.returncode == 0
    assert show_after_remove.stdout.strip() == "0 results"


def test_duplicate_marker_set_is_noop(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "one"], cwd=tmp_path)

    first = _run_cli(["marker", "set", "--id", "demo", "--version", "1", "--name", "stable"], cwd=tmp_path)
    second = _run_cli(["marker", "set", "--id", "demo", "--version", "1", "--name", "stable"], cwd=tmp_path)
    listed = _run_cli(["marker", "list", "--id", "demo"], cwd=tmp_path)

    assert first.returncode == 0
    assert second.returncode == 0
    assert "Marker already set" in second.stdout
    assert listed.stdout.count("\tstable\t") == 1


def test_shortcut_commands_with_explicit_version(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "one"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "two"], cwd=tmp_path)

    stable_res = _run_cli(["stable", "--id", "demo", "--version", "1"], cwd=tmp_path)
    milestone_res = _run_cli(["milestone", "--id", "demo", "--version", "2"], cwd=tmp_path)
    list_res = _run_cli(["marker", "list", "--id", "demo"], cwd=tmp_path)

    assert stable_res.returncode == 0
    assert milestone_res.returncode == 0
    assert "demo\t2\tmilestone\t" in list_res.stdout
    assert "demo\t1\tstable\t" in list_res.stdout


def test_shortcut_commands_without_version_use_latest(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "one"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "two"], cwd=tmp_path)

    res = _run_cli(["stable", "--id", "demo"], cwd=tmp_path)
    show_res = _run_cli(["marker", "show", "--id", "demo", "--version", "2"], cwd=tmp_path)

    assert res.returncode == 0
    assert "demo@2" in res.stdout
    assert show_res.stdout.strip() == "stable"


def test_show_and_list_include_markers(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "one"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "two"], cwd=tmp_path)
    _run_cli(["marker", "set", "--id", "demo", "--version", "2", "--name", "stable"], cwd=tmp_path)
    _run_cli(["marker", "set", "--id", "demo", "--version", "2", "--name", "milestone"], cwd=tmp_path)

    show_res = _run_cli(["show", "--id", "demo", "--version", "2"], cwd=tmp_path)
    list_res = _run_cli(["list", "--id", "demo"], cwd=tmp_path)

    assert show_res.returncode == 0
    assert "markers: milestone, stable" in show_res.stdout
    assert list_res.returncode == 0
    assert "milestone,stable" in list_res.stdout


def test_marker_invalid_version_returns_2(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "one"], cwd=tmp_path)

    res = _run_cli(["marker", "set", "--id", "demo", "--version", "2", "--name", "stable"], cwd=tmp_path)
    assert res.returncode == 2
    assert "Prompt version not found." in res.stderr


def test_marker_invalid_name_returns_2(tmp_path):
    _run_cli(["init"], cwd=tmp_path)
    _run_cli(["add", "--id", "demo", "--text", "one"], cwd=tmp_path)

    res = _run_cli(["marker", "set", "--id", "demo", "--version", "1", "--name", "gold"], cwd=tmp_path)
    assert res.returncode == 2
    assert "invalid choice" in res.stderr.lower()
