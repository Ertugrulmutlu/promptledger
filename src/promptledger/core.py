"""Core API for PromptLedger."""

from __future__ import annotations

import csv
import difflib
import hashlib
import json
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import db


@dataclass
class PromptRecord:
    prompt_id: str
    version: int
    content: str
    content_hash: str
    reason: str | None
    author: str | None
    tags: list[str] | None
    env: str | None
    metrics: dict[str, Any] | None
    created_at: str


SECRET_PATTERNS = ("sk-", "AKIA", "-----BEGIN")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def contains_secret(text: str) -> bool:
    return any(pattern in text for pattern in SECRET_PATTERNS)


class PromptLedger:
    """Local prompt version ledger backed by SQLite."""

    def __init__(self, root: str | Path | None = None, db_path: str | Path | None = None) -> None:
        self._explicit_db = Path(db_path).expanduser() if db_path else None
        self._root = Path(root).expanduser() if root else None
        if self._explicit_db:
            self._db_path = self._explicit_db
            self._use_default = False
            self._project_root = self._db_path.parent
        else:
            self._db_path, self._use_default, self._project_root = db.get_db_path(self._root)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def init(self) -> Path:
        db.ensure_dir_and_gitignore(self._db_path, self._project_root, self._use_default)
        db.init_db(self._db_path)
        return self._db_path

    def _ensure_initialized(self) -> None:
        if not self._db_path.exists():
            raise RuntimeError("PromptLedger not initialized. Run `promptledger init`.")

    def _connect(self):
        self._ensure_initialized()
        return db.connect(self._db_path)

    def add(
        self,
        prompt_id: str,
        content: str,
        reason: str | None = None,
        author: str | None = None,
        tags: list[str] | None = None,
        env: str | None = None,
        metrics: dict[str, Any] | None = None,
        warn_on_secrets: bool = True,
    ) -> dict[str, Any]:
        content = normalize_newlines(content)
        if warn_on_secrets and contains_secret(content):
            warnings.warn("Possible secret detected in prompt content.", UserWarning, stacklevel=2)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        tags_json = json.dumps(tags) if tags is not None else None
        metrics_json = json.dumps(metrics) if metrics is not None else None

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT version, content_hash
                FROM prompt_versions
                WHERE prompt_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (prompt_id,),
            ).fetchone()
            if row and row["content_hash"] == content_hash:
                return {
                    "created": False,
                    "prompt_id": prompt_id,
                    "version": int(row["version"]),
                    "content_hash": content_hash,
                }
            next_version = (int(row["version"]) if row else 0) + 1
            conn.execute(
                """
                INSERT INTO prompt_versions (
                    prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_id,
                    next_version,
                    content,
                    content_hash,
                    reason,
                    author,
                    tags_json,
                    env,
                    metrics_json,
                    created_at,
                ),
            )
            conn.commit()
        return {
            "created": True,
            "prompt_id": prompt_id,
            "version": next_version,
            "content_hash": content_hash,
        }

    def list(
        self,
        prompt_id: str | None = None,
        tags: Iterable[str] | None = None,
        env: str | None = None,
    ) -> list[PromptRecord]:
        filters = []
        params: list[Any] = []
        if prompt_id:
            filters.append("prompt_id = ?")
            params.append(prompt_id)
        if env:
            filters.append("env = ?")
            params.append(env)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
                FROM prompt_versions
                {where}
                ORDER BY created_at DESC
                """,
                params,
            ).fetchall()

        records = [self._row_to_record(row) for row in rows]
        if tags:
            tag_set = set(tags)
            records = [r for r in records if r.tags and tag_set.intersection(r.tags)]
        return records

    def set_label(self, prompt_id: str, version: int, label: str) -> None:
        record = self.get(prompt_id, version)
        if record is None:
            raise ValueError("Prompt version not found.")
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO labels (prompt_id, label, version, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(prompt_id, label) DO UPDATE SET
                    version=excluded.version,
                    updated_at=excluded.updated_at
                """,
                (prompt_id, label, version, updated_at),
            )
            conn.commit()

    def get_label(self, prompt_id: str, label: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT version
                FROM labels
                WHERE prompt_id = ? AND label = ?
                LIMIT 1
                """,
                (prompt_id, label),
            ).fetchone()
        if row is None:
            raise ValueError("Label not found.")
        return int(row["version"])

    def list_labels(self, prompt_id: str | None = None) -> list[dict[str, Any]]:
        filters = []
        params: list[Any] = []
        if prompt_id:
            filters.append("prompt_id = ?")
            params.append(prompt_id)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT prompt_id, label, version, updated_at
                FROM labels
                {where}
                ORDER BY updated_at DESC
                """,
                params,
            ).fetchall()
        return [
            {
                "prompt_id": row["prompt_id"],
                "label": row["label"],
                "version": int(row["version"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def search(
        self,
        contains: str,
        prompt_id: str | None = None,
        author: str | None = None,
        tag: str | None = None,
        env: str | None = None,
    ) -> list[PromptRecord]:
        filters = ["content LIKE ?"]
        params: list[Any] = [f"%{contains}%"]
        if prompt_id:
            filters.append("prompt_id = ?")
            params.append(prompt_id)
        if author:
            filters.append("author = ?")
            params.append(author)
        if env:
            filters.append("env = ?")
            params.append(env)
        where = f"WHERE {' AND '.join(filters)}"

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
                FROM prompt_versions
                {where}
                ORDER BY created_at DESC
                """,
                params,
            ).fetchall()

        records = [self._row_to_record(row) for row in rows]
        if tag:
            records = [r for r in records if r.tags and tag in r.tags]
        return records

    def get(self, prompt_id: str, version: int | None = None) -> PromptRecord | None:
        with self._connect() as conn:
            if version is None:
                row = conn.execute(
                    """
                    SELECT prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
                    FROM prompt_versions
                    WHERE prompt_id = ?
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (prompt_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
                    FROM prompt_versions
                    WHERE prompt_id = ? AND version = ?
                    LIMIT 1
                    """,
                    (prompt_id, version),
                ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def diff(self, prompt_id: str, from_version: int, to_version: int) -> str:
        left = self.get(prompt_id, from_version)
        right = self.get(prompt_id, to_version)
        if left is None or right is None:
            raise ValueError("One or both versions not found.")
        left_lines = normalize_newlines(left.content).splitlines(keepends=True)
        right_lines = normalize_newlines(right.content).splitlines(keepends=True)
        diff_lines = difflib.unified_diff(
            left_lines,
            right_lines,
            fromfile=f"{prompt_id}@{from_version}",
            tofile=f"{prompt_id}@{to_version}",
        )
        return "".join(diff_lines)

    def export(self, format: str, out_path: str | Path) -> Path:
        format = format.lower()
        records = self.list()
        path = Path(out_path)

        if format == "jsonl":
            with path.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record.__dict__, sort_keys=True) + "\n")
        elif format == "csv":
            fieldnames = [
                "prompt_id",
                "version",
                "content",
                "content_hash",
                "reason",
                "author",
                "tags",
                "env",
                "metrics",
                "created_at",
            ]
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for record in records:
                    row = record.__dict__.copy()
                    row["tags"] = json.dumps(row["tags"]) if row["tags"] is not None else ""
                    row["metrics"] = json.dumps(row["metrics"]) if row["metrics"] is not None else ""
                    writer.writerow(row)
        else:
            raise ValueError("Unsupported export format. Use jsonl or csv.")
        return path

    def _row_to_record(self, row) -> PromptRecord:
        tags = json.loads(row["tags"]) if row["tags"] else None
        metrics = json.loads(row["metrics"]) if row["metrics"] else None
        return PromptRecord(
            prompt_id=row["prompt_id"],
            version=int(row["version"]),
            content=row["content"],
            content_hash=row["content_hash"],
            reason=row["reason"],
            author=row["author"],
            tags=tags,
            env=row["env"],
            metrics=metrics,
            created_at=row["created_at"],
        )
