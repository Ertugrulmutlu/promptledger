import json
import sqlite3
import hashlib
from pathlib import Path

import pytest

from promptledger.core import PromptLedger
from promptledger import db


def test_db_path_explicit_override_beats_env(tmp_path, monkeypatch):
    custom = tmp_path / "custom_home"
    explicit = tmp_path / "explicit.db"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(custom))
    ledger = PromptLedger(db_path=explicit)
    assert ledger.db_path == explicit


def test_path_resolution_env_override(tmp_path, monkeypatch):
    custom = tmp_path / "custom_home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(custom))
    ledger = PromptLedger(root=tmp_path)
    expected = custom / "promptledger.db"
    assert ledger.db_path == expected


def test_path_resolution_git_root_nested(tmp_path):
    repo_root = tmp_path / "repo"
    nested = repo_root / "src" / "pkg"
    (repo_root / ".git").mkdir(parents=True)
    nested.mkdir(parents=True)

    ledger = PromptLedger(root=nested)
    expected = repo_root / ".promptledger" / "promptledger.db"
    assert ledger.db_path == expected


def test_path_resolution_fallback_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ledger = PromptLedger()
    expected = tmp_path / ".promptledger" / "promptledger.db"
    assert ledger.db_path == expected


def test_init_gitignore_idempotent(tmp_path):
    (tmp_path / ".git").mkdir(parents=True)
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text(encoding="utf-8")
    assert ".promptledger/" in content.splitlines()

    ledger.init()
    content_after = gitignore.read_text(encoding="utf-8")
    assert content_after.count(".promptledger/") == 1


def test_version_incrementing(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    res1 = ledger.add("alpha", "hello")
    res2 = ledger.add("alpha", "hello world")

    assert res1["version"] == 1
    assert res2["version"] == 2


def test_add_stores_collection_and_role(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    ledger.add("alpha", "hello", collection="chunking-lab", role="system")

    record = ledger.get("alpha", 1)
    assert record is not None
    assert record.collection == "chunking-lab"
    assert record.role == "system"


def test_add_supports_collection_only_and_role_only(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    ledger.add("alpha", "one", collection="support-bot")
    ledger.add("beta", "two", role="eval")

    alpha = ledger.get("alpha", 1)
    beta = ledger.get("beta", 1)
    assert alpha is not None
    assert alpha.collection == "support-bot"
    assert alpha.role is None
    assert beta is not None
    assert beta.collection is None
    assert beta.role == "eval"


def test_collection_normalization_and_invalid_role(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    ledger.add("trimmed", "one", collection="  chunking-lab  ")
    ledger.add("empty", "two", collection="   ")

    trimmed = ledger.get("trimmed", 1)
    empty = ledger.get("empty", 1)
    assert trimmed is not None
    assert trimmed.collection == "chunking-lab"
    assert empty is not None
    assert empty.collection is None

    with pytest.raises(ValueError):
        ledger.add("bad", "three", role="assistant")


def test_noop_hashing(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    res1 = ledger.add("beta", "same")
    res2 = ledger.add("beta", "same")

    assert res1["created"] is True
    assert res2["created"] is False
    assert len(ledger.list("beta")) == 1


def test_noop_hashing_newline_normalization(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    res1 = ledger.add("nl", "line1\nline2")
    res2 = ledger.add("nl", "line1\r\nline2")

    assert res1["created"] is True
    assert res2["created"] is False
    assert len(ledger.list("nl")) == 1


def test_diff_correctness(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    ledger.add("gamma", "line1\nline2")
    ledger.add("gamma", "line1\nline3")

    diff_text = ledger.diff("gamma", 1, 2)
    assert "-line2" in diff_text
    assert "+line3" in diff_text


def test_diff_labels_and_any(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    ledger = PromptLedger()
    ledger.init()

    ledger.add("delta", "line1\nline2")
    ledger.add("delta", "line1\nline3")
    ledger.set_label("delta", 1, "prod")
    ledger.set_label("delta", 2, "staging")

    diff_labels = ledger.diff_labels("delta", "prod", "staging")
    assert "-line2" in diff_labels
    assert "+line3" in diff_labels

    diff_any = ledger.diff_any("delta", "prod", 2)
    assert "-line2" in diff_any
    assert "+line3" in diff_any


def test_diff_modes(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    ledger = PromptLedger()
    ledger.init()

    ledger.add(
        "modes",
        "line1\nline2",
        reason="first",
        tags=["a"],
        env="dev",
        collection="chunking-lab",
        role="system",
    )
    ledger.add(
        "modes",
        "line1\nline3",
        reason="second",
        tags=["b"],
        env="prod",
        collection="agent-routing",
        role="eval",
    )

    unified = ledger.diff("modes", 1, 2, mode="unified")
    assert unified

    context_diff = ledger.diff("modes", 1, 2, mode="context")
    assert "***" in context_diff
    assert "---" in context_diff

    ndiff_text = ledger.diff("modes", 1, 2, mode="ndiff")
    assert "- line2" in ndiff_text
    assert "+ line3" in ndiff_text

    meta_text = ledger.diff("modes", 1, 2, mode="metadata")
    assert '-  "reason": "first"' in meta_text
    assert '+  "reason": "second"' in meta_text
    assert '-  "env": "dev"' in meta_text
    assert '+  "env": "prod"' in meta_text
    assert '-  "collection": "chunking-lab"' in meta_text
    assert '+  "collection": "agent-routing"' in meta_text
    assert '-  "role": "system"' in meta_text
    assert '+  "role": "eval"' in meta_text


def test_list_and_search_filter_by_collection_and_role(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    ledger.add("alpha", "Find me", collection="chunking-lab", role="system")
    ledger.add("beta", "Find me too", collection="chunking-lab", role="eval")
    ledger.add("gamma", "Find me three", collection="support-bot", role="system")

    by_collection = ledger.list(collection="chunking-lab")
    assert [record.prompt_id for record in by_collection] == ["beta", "alpha"]

    by_role = ledger.list(role="system")
    assert [record.prompt_id for record in by_role] == ["gamma", "alpha"]

    combined = ledger.list(collection="chunking-lab", role="eval")
    assert [record.prompt_id for record in combined] == ["beta"]

    searched = ledger.search("", collection="chunking-lab", role="system")
    assert [record.prompt_id for record in searched] == ["alpha"]


def test_new_db_has_label_events(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    ledger = PromptLedger()
    ledger.init()

    with sqlite3.connect(ledger.db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "label_events" in tables
    assert "markers" in tables


def test_marker_set_remove_and_duplicates(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("demo", "one")
    ledger.add("demo", "two")

    created = ledger.set_marker("demo", 2, "stable")
    duplicate = ledger.set_marker("demo", 2, "stable")

    assert created is True
    assert duplicate is False
    assert ledger.get_markers("demo", 2) == ["stable"]

    removed = ledger.remove_marker("demo", 2, "stable")
    missing = ledger.remove_marker("demo", 2, "stable")

    assert removed is True
    assert missing is False
    assert ledger.get_markers("demo", 2) == []


def test_multiple_markers_and_multiple_stable_versions(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("demo", "one")
    ledger.add("demo", "two")
    ledger.add("demo", "three")

    ledger.set_marker("demo", 1, "stable")
    ledger.set_marker("demo", 2, "stable")
    ledger.set_marker("demo", 2, "milestone")

    assert ledger.get_markers("demo", 1) == ["stable"]
    assert ledger.get_markers("demo", 2) == ["milestone", "stable"]

    markers = ledger.list_markers(prompt_id="demo")
    assert [(item["version"], item["name"]) for item in markers] == [
        (2, "milestone"),
        (2, "stable"),
        (1, "stable"),
    ]


def test_marker_api_errors(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("beta", "one")

    with pytest.raises(ValueError):
        ledger.set_marker("beta", 2, "stable")

    with pytest.raises(ValueError):
        ledger.set_marker("beta", 1, "invalid")

    with pytest.raises(ValueError):
        ledger.remove_marker("beta", 2, "stable")

    with pytest.raises(ValueError):
        ledger.get_markers("beta", 2)


def test_label_events_ordering(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    ledger = PromptLedger()
    ledger.init()

    ledger.add("alpha", "one")
    ledger.add("alpha", "two")
    ledger.set_label("alpha", 1, "prod")
    ledger.set_label("alpha", 2, "prod")
    ledger.set_label("alpha", 1, "prod")

    events = ledger.list_label_events(prompt_id="alpha", label="prod")
    assert [event["new_version"] for event in events[:3]] == [1, 2, 1]
    assert events[0]["old_version"] == 2


def test_set_label_appends_event(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    ledger = PromptLedger()
    ledger.init()

    ledger.add("beta", "one")
    ledger.add("beta", "two")
    ledger.set_label("beta", 1, "prod")
    ledger.set_label("beta", 2, "prod")

    labels = ledger.list_labels("beta")
    assert labels[0]["version"] == 2

    events = ledger.list_label_events(prompt_id="beta", label="prod")
    assert len(events) == 2
    assert events[0]["old_version"] == 1
    assert events[0]["new_version"] == 2
    assert events[1]["old_version"] is None
    assert events[1]["new_version"] == 1


def test_metadata_diff_with_same_content(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    ledger = PromptLedger()
    ledger.init()

    content = "same content"
    hash_value = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with db.connect(ledger.db_path) as conn:
        conn.execute(
            """
            INSERT INTO prompt_versions (
                prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "meta",
                1,
                content,
                hash_value,
                "first",
                "alice",
                json.dumps(["a"]),
                "dev",
                json.dumps({"score": 1}),
                "2024-01-01T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO prompt_versions (
                prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "meta",
                2,
                content,
                hash_value,
                "second",
                "alice",
                json.dumps(["b"]),
                "prod",
                json.dumps({"score": 2}),
                "2024-01-01T00:00:01Z",
            ),
        )
        conn.commit()

    diff_text = ledger.diff("meta", 1, 2, mode="metadata")
    assert '-  "reason": "first"' in diff_text
    assert '+  "reason": "second"' in diff_text
    assert '-  "env": "dev"' in diff_text
    assert '+  "env": "prod"' in diff_text
    assert '-    "a"' in diff_text
    assert '+    "b"' in diff_text
    assert '-    "score": 1' in diff_text
    assert '+    "score": 2' in diff_text


def test_status_snapshot(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    ledger = PromptLedger()
    ledger.init()

    ledger.add("alpha", "one")
    ledger.add("alpha", "two")
    ledger.add("beta", "single")
    ledger.set_label("alpha", 2, "prod")
    ledger.set_label("alpha", 1, "staging")

    status = ledger.status()
    assert list(status.keys()) == ["alpha", "beta"]
    assert status["alpha"]["latest_version"] == 2
    assert status["beta"]["latest_version"] == 1
    assert status["alpha"]["labels"]["prod"] == 2
    assert status["alpha"]["labels"]["staging"] == 1
    assert status["alpha"]["labels_at_latest"]["prod"] is True
    assert status["alpha"]["labels_at_latest"]["staging"] is False


def test_diff_ignores_newline_style(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    content_crlf = "a\r\nb"
    content_lf = "a\nb"
    hash_crlf = hashlib.sha256(content_crlf.encode("utf-8")).hexdigest()
    hash_lf = hashlib.sha256(content_lf.encode("utf-8")).hexdigest()

    with db.connect(ledger.db_path) as conn:
        conn.execute(
            """
            INSERT INTO prompt_versions (
                prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("nl-diff", 1, content_crlf, hash_crlf, None, None, None, None, None, "2024-01-01T00:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO prompt_versions (
                prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("nl-diff", 2, content_lf, hash_lf, None, None, None, None, None, "2024-01-01T00:00:01Z"),
        )
        conn.commit()

    diff_text = ledger.diff("nl-diff", 1, 2)
    assert diff_text == ""


def test_export_formats(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add(
        "delta",
        "content",
        tags=["t1"],
        collection="chunking-lab",
        role="template",
        metrics={"score": 1},
    )

    jsonl_path = tmp_path / "export.jsonl"
    csv_path = tmp_path / "export.csv"

    ledger.export("jsonl", jsonl_path)
    ledger.export("csv", csv_path)

    assert jsonl_path.exists()
    assert csv_path.exists()
    assert "delta" in jsonl_path.read_text(encoding="utf-8")
    assert "delta" in csv_path.read_text(encoding="utf-8")
    assert "chunking-lab" in jsonl_path.read_text(encoding="utf-8")
    assert "template" in csv_path.read_text(encoding="utf-8")


def test_export_deterministic(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("stable", "one")
    ledger.add("stable", "two")

    jsonl_a = tmp_path / "export_a.jsonl"
    jsonl_b = tmp_path / "export_b.jsonl"
    csv_a = tmp_path / "export_a.csv"
    csv_b = tmp_path / "export_b.csv"

    ledger.export("jsonl", jsonl_a)
    ledger.export("jsonl", jsonl_b)
    ledger.export("csv", csv_a)
    ledger.export("csv", csv_b)

    assert jsonl_a.read_text(encoding="utf-8") == jsonl_b.read_text(encoding="utf-8")
    assert csv_a.read_text(encoding="utf-8") == csv_b.read_text(encoding="utf-8")


def test_schema_migration(tmp_path):
    db_path = tmp_path / "legacy.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_migrations (version) VALUES (0)")
        conn.execute(
            """
            CREATE TABLE prompt_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                reason TEXT,
                author TEXT,
                tags TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(prompt_id, version)
            )
            """
        )
        conn.commit()

    ledger = PromptLedger(db_path=db_path)
    ledger.init()

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(prompt_versions)")}
        assert "env" in cols
        assert "metrics" in cols
        assert "collection" in cols
        assert "role" in cols
        label_cols = {row[1] for row in conn.execute("PRAGMA table_info(labels)")}
        assert "prompt_id" in label_cols
        assert "label" in label_cols
        assert "version" in label_cols
        assert "updated_at" in label_cols
        label_event_cols = {row[1] for row in conn.execute("PRAGMA table_info(label_events)")}
        assert "prompt_id" in label_event_cols
        assert "label" in label_event_cols
        assert "old_version" in label_event_cols
        assert "new_version" in label_event_cols
        assert "updated_at" in label_event_cols
        marker_cols = {row[1] for row in conn.execute("PRAGMA table_info(markers)")}
        assert "prompt_id" in marker_cols
        assert "version" in marker_cols
        assert "name" in marker_cols
        assert "created_at" in marker_cols
        version = conn.execute("SELECT version FROM schema_migrations").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION


def test_labels_db_behavior(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("alpha", "one")
    ledger.add("alpha", "two")

    ledger.set_label("alpha", 1, "prod")
    labels = ledger.list_labels("alpha")
    assert len(labels) == 1
    assert labels[0]["label"] == "prod"
    assert labels[0]["version"] == 1

    ledger.set_label("alpha", 2, "prod")
    labels = ledger.list_labels("alpha")
    assert len(labels) == 1
    assert labels[0]["version"] == 2

    events = ledger.list_label_events(prompt_id="alpha")
    assert len(events) == 2
    assert events[0]["new_version"] == 2
    assert events[0]["old_version"] == 1
    assert events[1]["new_version"] == 1
    assert events[1]["old_version"] is None


def test_labels_api_errors(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("beta", "one")

    with pytest.raises(ValueError):
        ledger.set_label("beta", 2, "prod")

    ledger.set_label("beta", 1, "prod")
    assert ledger.get_label("beta", "prod") == 1

    with pytest.raises(ValueError):
        ledger.get_label("beta", "missing")


def test_api_secret_warning(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()

    with pytest.warns(UserWarning):
        ledger.add("secret", "sk-123456")


def test_wal_pragma_attempted(monkeypatch, tmp_path):
    calls = []

    class DummyConn:
        def __init__(self):
            self.row_factory = None

        def execute(self, sql):
            calls.append(sql)
            return None

    def fake_connect(path, timeout):
        assert timeout == 5
        return DummyConn()

    monkeypatch.setattr(db.sqlite3, "connect", fake_connect)
    conn = db.connect(tmp_path / "test.db")
    assert conn.row_factory == sqlite3.Row
    assert any("PRAGMA journal_mode=WAL" in sql for sql in calls)
