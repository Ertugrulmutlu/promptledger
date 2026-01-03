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
    ledger.add("delta", "content", tags=["t1"], metrics={"score": 1})

    jsonl_path = tmp_path / "export.jsonl"
    csv_path = tmp_path / "export.csv"

    ledger.export("jsonl", jsonl_path)
    ledger.export("csv", csv_path)

    assert jsonl_path.exists()
    assert csv_path.exists()
    assert "delta" in jsonl_path.read_text(encoding="utf-8")
    assert "delta" in csv_path.read_text(encoding="utf-8")


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
        label_cols = {row[1] for row in conn.execute("PRAGMA table_info(labels)")}
        assert "prompt_id" in label_cols
        assert "label" in label_cols
        assert "version" in label_cols
        assert "updated_at" in label_cols
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
