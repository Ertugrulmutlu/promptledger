"""SQLite storage and migrations for PromptLedger."""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

CURRENT_SCHEMA_VERSION = 2


def _git_root_via_cli(start: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None
    output = result.stdout.strip()
    if not output:
        return None
    return Path(output)


def find_git_root(start: Path) -> Path | None:
    current = start.resolve()
    git_root = _git_root_via_cli(current)
    if git_root:
        return git_root
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def get_db_path(root: Path | None = None) -> tuple[Path, bool, Path]:
    env_home = os.getenv("PROMPTLEDGER_HOME")
    if env_home:
        base = Path(env_home).expanduser()
        return base / "promptledger.db", False, base

    start = root.resolve() if root else Path.cwd().resolve()
    git_root = find_git_root(start)
    if git_root is not None:
        db_path = git_root / ".promptledger" / "promptledger.db"
        return db_path, True, git_root
    db_path = start / ".promptledger" / "promptledger.db"
    return db_path, False, start


def ensure_dir_and_gitignore(db_path: Path, project_root: Path, use_default: bool) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not use_default:
        return
    gitignore = project_root / ".gitignore"
    entry = ".promptledger/"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        lines = content.splitlines()
        if entry in lines:
            return
        new_content = content.rstrip("\n") + "\n" + entry + "\n"
    else:
        new_content = entry + "\n"
    gitignore.write_text(new_content, encoding="utf-8")


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _get_schema_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_migrations LIMIT 1").fetchone()
    if row is None:
        return 0
    return int(row["version"])


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("DELETE FROM schema_migrations")
    conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))


def _create_schema_v1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            reason TEXT,
            author TEXT,
            tags TEXT,
            env TEXT,
            metrics TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(prompt_id, version)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_versions_prompt ON prompt_versions(prompt_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_versions_env ON prompt_versions(env)")

def _create_labels_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS labels (
            prompt_id TEXT NOT NULL,
            label TEXT NOT NULL,
            version INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(prompt_id, label)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_labels_prompt ON labels(prompt_id)")


def _migrate_0_to_1(conn: sqlite3.Connection) -> None:
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(prompt_versions)")}
    if "env" not in existing_cols:
        conn.execute("ALTER TABLE prompt_versions ADD COLUMN env TEXT")
    if "metrics" not in existing_cols:
        conn.execute("ALTER TABLE prompt_versions ADD COLUMN metrics TEXT")

def _migrate_1_to_2(conn: sqlite3.Connection) -> None:
    _create_labels_table(conn)


def apply_migrations(conn: sqlite3.Connection) -> None:
    version = _get_schema_version(conn)
    if not _table_exists(conn, "prompt_versions"):
        _create_schema_v1(conn)
        _create_labels_table(conn)
        _set_schema_version(conn, CURRENT_SCHEMA_VERSION)
        return

    if version < 1:
        _migrate_0_to_1(conn)
        _set_schema_version(conn, 1)
        version = 1

    if version < 2:
        _migrate_1_to_2(conn)
        _set_schema_version(conn, 2)


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        apply_migrations(conn)
        conn.commit()
