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
from .evaluation import (
    EvaluationComparison,
    EvaluationRun,
    GateResult,
    compare_runs,
    evaluate_comparison_gate,
    parse_gate_policy,
    validate_metadata,
    validate_metrics,
)
from .render import export_review_markdown as render_review_markdown
from .review import MetadataChange, ReviewRef, ReviewResult, ReviewWarning, summarize_semantic_changes


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
    collection: str | None
    role: str | None
    metrics: dict[str, Any] | None
    created_at: str


SECRET_PATTERNS = ("sk-", "AKIA", "-----BEGIN")
BUILTIN_MARKERS = ("milestone", "stable")
BUILTIN_ROLES = ("system", "user", "template", "modelfile", "eval")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def contains_secret(text: str) -> bool:
    return any(pattern in text for pattern in SECRET_PATTERNS)


def normalize_collection(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def validate_role(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in BUILTIN_ROLES:
        allowed = ", ".join(BUILTIN_ROLES)
        raise ValueError(f"Unsupported role. Use one of: {allowed}.")
    return value


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
        collection: str | None = None,
        role: str | None = None,
        metrics: dict[str, Any] | None = None,
        warn_on_secrets: bool = True,
    ) -> dict[str, Any]:
        content = normalize_newlines(content)
        collection = normalize_collection(collection)
        role = validate_role(role)
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
                    prompt_id, version, content, content_hash, reason, author, tags, env, collection, role, metrics, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    collection,
                    role,
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
        collection: str | None = None,
        role: str | None = None,
    ) -> list[PromptRecord]:
        filters = []
        params: list[Any] = []
        if prompt_id:
            filters.append("prompt_id = ?")
            params.append(prompt_id)
        if env:
            filters.append("env = ?")
            params.append(env)
        normalized_collection = normalize_collection(collection)
        if normalized_collection:
            filters.append("collection = ?")
            params.append(normalized_collection)
        validated_role = validate_role(role)
        if validated_role:
            filters.append("role = ?")
            params.append(validated_role)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT prompt_id, version, content, content_hash, reason, author, tags, env, collection, role, metrics, created_at
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

    def status(self, prompt_id: str | None = None) -> dict[str, dict[str, Any]]:
        prompt_filter = "WHERE prompt_id = ?" if prompt_id else ""
        params: list[Any] = [prompt_id] if prompt_id else []
        latest_rows: dict[str, dict[str, Any]] = {}

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT prompt_id, MAX(version) AS version
                FROM prompt_versions
                {prompt_filter}
                GROUP BY prompt_id
                ORDER BY prompt_id ASC
                """,
                params,
            ).fetchall()
            if not rows:
                return {}

            for row in rows:
                latest_rows[row["prompt_id"]] = {"latest_version": int(row["version"])}

            for prompt in latest_rows.keys():
                latest_version = latest_rows[prompt]["latest_version"]
                created_row = conn.execute(
                    """
                    SELECT created_at
                    FROM prompt_versions
                    WHERE prompt_id = ? AND version = ?
                    LIMIT 1
                    """,
                    (prompt, latest_version),
                ).fetchone()
                latest_rows[prompt]["latest_created_at"] = (
                    created_row["created_at"] if created_row else None
                )

        labels = self.list_labels(prompt_id)
        label_map: dict[str, dict[str, int]] = {}
        for item in labels:
            label_map.setdefault(item["prompt_id"], {})[item["label"]] = item["version"]

        status: dict[str, dict[str, Any]] = {}
        for prompt in sorted(latest_rows.keys()):
            latest_version = latest_rows[prompt]["latest_version"]
            prompt_labels = label_map.get(prompt, {})
            status[prompt] = {
                "latest_version": latest_version,
                "latest_created_at": latest_rows[prompt]["latest_created_at"],
                "labels": prompt_labels,
                "labels_at_latest": {
                    label: version == latest_version for label, version in prompt_labels.items()
                },
            }
        return status

    def set_label(self, prompt_id: str, version: int, label: str) -> None:
        record = self.get(prompt_id, version)
        if record is None:
            raise ValueError("Prompt version not found.")
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._connect() as conn:
            old_row = conn.execute(
                """
                SELECT version
                FROM labels
                WHERE prompt_id = ? AND label = ?
                LIMIT 1
                """,
                (prompt_id, label),
            ).fetchone()
            old_version = int(old_row["version"]) if old_row else None
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
            conn.execute(
                """
                INSERT INTO label_events (prompt_id, label, old_version, new_version, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (prompt_id, label, old_version, version, updated_at),
            )
            conn.commit()

    def set_marker(self, prompt_id: str, version: int, name: str) -> bool:
        self._validate_marker_name(name)
        record = self.get(prompt_id, version)
        if record is None:
            raise ValueError("Prompt version not found.")
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO markers (prompt_id, version, name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (prompt_id, version, name, created_at),
            )
            conn.commit()
        return cursor.rowcount > 0

    def remove_marker(self, prompt_id: str, version: int, name: str) -> bool:
        self._validate_marker_name(name)
        record = self.get(prompt_id, version)
        if record is None:
            raise ValueError("Prompt version not found.")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM markers
                WHERE prompt_id = ? AND version = ? AND name = ?
                """,
                (prompt_id, version, name),
            )
            conn.commit()
        return cursor.rowcount > 0

    def list_markers(
        self,
        prompt_id: str | None = None,
        version: int | None = None,
    ) -> list[dict[str, Any]]:
        filters = []
        params: list[Any] = []
        if prompt_id:
            filters.append("prompt_id = ?")
            params.append(prompt_id)
        if version is not None:
            filters.append("version = ?")
            params.append(version)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT prompt_id, version, name, created_at
                FROM markers
                {where}
                ORDER BY prompt_id ASC, version DESC, name ASC
                """,
                params,
            ).fetchall()
        return [
            {
                "prompt_id": row["prompt_id"],
                "version": int(row["version"]),
                "name": row["name"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_markers(self, prompt_id: str, version: int) -> list[str]:
        record = self.get(prompt_id, version)
        if record is None:
            raise ValueError("Prompt version not found.")
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT name
                FROM markers
                WHERE prompt_id = ? AND version = ?
                ORDER BY name ASC
                """,
                (prompt_id, version),
            ).fetchall()
        return [str(row["name"]) for row in rows]

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

    def list_label_events(
        self,
        prompt_id: str | None = None,
        label: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        filters = []
        params: list[Any] = []
        if prompt_id:
            filters.append("prompt_id = ?")
            params.append(prompt_id)
        if label:
            filters.append("label = ?")
            params.append(label)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, prompt_id, label, old_version, new_version, updated_at
                FROM label_events
                {where}
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "prompt_id": row["prompt_id"],
                "label": row["label"],
                "old_version": int(row["old_version"]) if row["old_version"] is not None else None,
                "new_version": int(row["new_version"]),
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
        collection: str | None = None,
        role: str | None = None,
    ) -> list[PromptRecord]:
        filters = []
        params: list[Any] = []
        if contains:
            filters.append("content LIKE ?")
            params.append(f"%{contains}%")
        if prompt_id:
            filters.append("prompt_id = ?")
            params.append(prompt_id)
        if author:
            filters.append("author = ?")
            params.append(author)
        if env:
            filters.append("env = ?")
            params.append(env)
        normalized_collection = normalize_collection(collection)
        if normalized_collection:
            filters.append("collection = ?")
            params.append(normalized_collection)
        validated_role = validate_role(role)
        if validated_role:
            filters.append("role = ?")
            params.append(validated_role)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT prompt_id, version, content, content_hash, reason, author, tags, env, collection, role, metrics, created_at
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
                    SELECT prompt_id, version, content, content_hash, reason, author, tags, env, collection, role, metrics, created_at
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
                    SELECT prompt_id, version, content, content_hash, reason, author, tags, env, collection, role, metrics, created_at
                    FROM prompt_versions
                    WHERE prompt_id = ? AND version = ?
                    LIMIT 1
                    """,
                    (prompt_id, version),
                ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def diff(
        self,
        prompt_id: str,
        from_version: int,
        to_version: int,
        mode: str = "unified",
        include_metadata: bool = False,
    ) -> str:
        left = self.get(prompt_id, from_version)
        right = self.get(prompt_id, to_version)
        if left is None or right is None:
            raise ValueError("One or both versions not found.")
        if mode == "summary":
            review = self.review(prompt_id, from_version, to_version)
            if not review.semantic_summary:
                return "No confident semantic change detected."
            return "\n".join(item.summary for item in review.semantic_summary)
        if mode == "metadata":
            return self._diff_metadata(prompt_id, left, right)
        left_lines = normalize_newlines(left.content).splitlines(keepends=True)
        right_lines = normalize_newlines(right.content).splitlines(keepends=True)
        diff_text = self._diff_lines(
            left_lines,
            right_lines,
            fromfile=f"{prompt_id}@{from_version}",
            tofile=f"{prompt_id}@{to_version}",
            mode=mode,
        )
        if include_metadata:
            meta_text = self._diff_metadata(prompt_id, left, right)
            if meta_text:
                if diff_text:
                    diff_text += "\n"
                diff_text += meta_text
        return diff_text

    def diff_labels(
        self,
        prompt_id: str,
        from_label: str,
        to_label: str,
        mode: str = "unified",
        include_metadata: bool = False,
    ) -> str:
        from_version = self.get_label(prompt_id, from_label)
        to_version = self.get_label(prompt_id, to_label)
        return self.diff(
            prompt_id,
            from_version,
            to_version,
            mode=mode,
            include_metadata=include_metadata,
        )

    def diff_any(
        self,
        prompt_id: str,
        from_ref: int | str,
        to_ref: int | str,
        mode: str = "unified",
        include_metadata: bool = False,
    ) -> str:
        from_version = self._resolve_ref(prompt_id, from_ref)
        to_version = self._resolve_ref(prompt_id, to_ref)
        return self.diff(
            prompt_id,
            from_version,
            to_version,
            mode=mode,
            include_metadata=include_metadata,
        )

    def review(self, prompt_id: str, from_ref: int | str, to_ref: int | str) -> ReviewResult:
        from_resolved = self.resolve_ref(prompt_id, from_ref)
        to_resolved = self.resolve_ref(prompt_id, to_ref)
        left = self.get(prompt_id, from_resolved.resolved_version)
        right = self.get(prompt_id, to_resolved.resolved_version)
        if left is None or right is None:
            raise ValueError("One or both versions not found.")

        metadata_changes = self._metadata_changes(left, right)
        semantic_summary = summarize_semantic_changes(
            normalize_newlines(left.content),
            normalize_newlines(right.content),
        )
        labels_by_version = self._labels_for_versions(
            prompt_id, [from_resolved.resolved_version, to_resolved.resolved_version]
        )
        warnings = self._review_warnings(left, right, semantic_summary, metadata_changes)
        notes = self._review_notes(left, right, semantic_summary)
        return ReviewResult(
            prompt_id=prompt_id,
            from_ref=from_resolved,
            to_ref=to_resolved,
            semantic_summary=semantic_summary,
            metadata_changes=metadata_changes,
            label_context={
                "compared_refs": {
                    "from": from_resolved.to_dict(),
                    "to": to_resolved.to_dict(),
                },
                "labels_by_version": labels_by_version,
            },
            warnings=warnings,
            notes=notes,
            text_changed=normalize_newlines(left.content) != normalize_newlines(right.content),
        )

    def export_review_markdown(self, prompt_id: str, from_ref: int | str, to_ref: int | str) -> str:
        return render_review_markdown(self.review(prompt_id, from_ref, to_ref))

    def record_evaluation(
        self,
        prompt_id: str,
        ref: int | str,
        suite: str,
        metrics: dict[str, Any],
        model: str | None = None,
        dataset_hash: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationRun:
        resolved = self.resolve_ref(prompt_id, ref)
        if self.get(prompt_id, resolved.resolved_version) is None:
            raise ValueError("Prompt version not found.")
        suite = suite.strip() if isinstance(suite, str) else ""
        if not suite:
            raise ValueError("Evaluation suite must be a non-empty string.")
        if model is not None and not isinstance(model, str):
            raise ValueError("Evaluation model must be a string when provided.")
        if dataset_hash is not None and not isinstance(dataset_hash, str):
            raise ValueError("Evaluation dataset hash must be a string when provided.")
        model = model.strip() if isinstance(model, str) else model
        dataset_hash = dataset_hash.strip() if isinstance(dataset_hash, str) else dataset_hash
        if model == "":
            model = None
        if dataset_hash == "":
            dataset_hash = None
        validated_metrics = validate_metrics(metrics)
        validated_metadata = validate_metadata(metadata)
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        metrics_json = json.dumps(
            validated_metrics, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        metadata_json = (
            json.dumps(
                validated_metadata, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            if validated_metadata is not None
            else None
        )
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO evaluation_runs (
                    prompt_id, version, suite, model, dataset_hash, metrics, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_id, resolved.resolved_version, suite, model, dataset_hash,
                    metrics_json, metadata_json, created_at,
                ),
            )
            run_id = int(cursor.lastrowid)
            conn.commit()
        run = self.get_evaluation(run_id)
        if run is None:  # pragma: no cover - SQLite insert invariant
            raise RuntimeError("Evaluation run could not be read after insertion.")
        return run

    def get_evaluation(self, run_id: int) -> EvaluationRun | None:
        if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
            raise ValueError("Evaluation run ID must be a positive integer.")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, prompt_id, version, suite, model, dataset_hash,
                       metrics, metadata, created_at
                FROM evaluation_runs WHERE id = ? LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        return self._row_to_evaluation(row) if row else None

    def list_evaluations(
        self,
        prompt_id: str | None = None,
        ref: int | str | None = None,
        suite: str | None = None,
        model: str | None = None,
        limit: int = 200,
    ) -> list[EvaluationRun]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("Evaluation limit must be a positive integer.")
        filters = []
        params: list[Any] = []
        if prompt_id:
            filters.append("prompt_id = ?")
            params.append(prompt_id)
        if ref is not None:
            if not prompt_id:
                raise ValueError("A prompt ID is required when filtering by ref.")
            resolved = self.resolve_ref(prompt_id, ref)
            if self.get(prompt_id, resolved.resolved_version) is None:
                raise ValueError("Prompt version not found.")
            filters.append("version = ?")
            params.append(resolved.resolved_version)
        if suite is not None:
            filters.append("suite = ?")
            params.append(suite)
        if model is not None:
            filters.append("model = ?")
            params.append(model)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, prompt_id, version, suite, model, dataset_hash,
                       metrics, metadata, created_at
                FROM evaluation_runs
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_evaluation(row) for row in rows]

    def compare_evaluations(
        self,
        prompt_id: str,
        from_ref: int | str,
        to_ref: int | str,
        suite: str | None = None,
        model: str | None = None,
    ) -> EvaluationComparison:
        left_ref = self.resolve_ref(prompt_id, from_ref)
        right_ref = self.resolve_ref(prompt_id, to_ref)
        for resolved in (left_ref, right_ref):
            if self.get(prompt_id, resolved.resolved_version) is None:
                raise ValueError("Prompt version not found.")
        baseline = self._latest_evaluation(
            prompt_id, left_ref.resolved_version, suite=suite, model=model,
            match_model=model is not None,
        )
        if baseline is None:
            raise ValueError("No matching evaluation run found for the baseline ref.")
        selected_suite = suite or baseline.suite
        selected_model = model if model is not None else baseline.model
        candidate = self._latest_evaluation(
            prompt_id, right_ref.resolved_version, suite=selected_suite,
            model=selected_model, match_model=True,
        )
        if candidate is None:
            raise ValueError("No compatible evaluation run found for the candidate ref.")
        return compare_runs(
            prompt_id, left_ref.to_dict(), right_ref.to_dict(), baseline, candidate
        )

    def evaluate_gate(
        self,
        prompt_id: str,
        from_ref: int | str,
        to_ref: int | str,
        policy: dict[str, Any],
    ) -> GateResult:
        suite, model, rules = parse_gate_policy(policy)
        comparison = self.compare_evaluations(
            prompt_id, from_ref, to_ref, suite=suite, model=model
        )
        return evaluate_comparison_gate(comparison, rules)

    def export_evaluations(
        self, out_path: str | Path, prompt_id: str | None = None
    ) -> Path:
        path = Path(out_path)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for run in self.list_evaluations(prompt_id=prompt_id, limit=2_147_483_647):
                handle.write(json.dumps(run.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
        return path

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
                "collection",
                "role",
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
            collection=row["collection"],
            role=row["role"],
            metrics=metrics,
            created_at=row["created_at"],
        )

    def _row_to_evaluation(self, row) -> EvaluationRun:
        try:
            metrics = json.loads(row["metrics"])
            metadata = json.loads(row["metadata"]) if row["metadata"] is not None else None
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Evaluation run {row['id']} contains malformed JSON: {exc}.") from exc
        return EvaluationRun(
            id=int(row["id"]), prompt_id=str(row["prompt_id"]), version=int(row["version"]),
            suite=str(row["suite"]), model=row["model"], dataset_hash=row["dataset_hash"],
            metrics=validate_metrics(metrics), metadata=validate_metadata(metadata),
            created_at=str(row["created_at"]),
        )

    def _latest_evaluation(
        self,
        prompt_id: str,
        version: int,
        suite: str | None,
        model: str | None,
        match_model: bool,
    ) -> EvaluationRun | None:
        filters = ["prompt_id = ?", "version = ?"]
        params: list[Any] = [prompt_id, version]
        if suite is not None:
            filters.append("suite = ?")
            params.append(suite)
        if match_model:
            if model is None:
                filters.append("model IS NULL")
            else:
                filters.append("model = ?")
                params.append(model)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT id, prompt_id, version, suite, model, dataset_hash,
                       metrics, metadata, created_at
                FROM evaluation_runs
                WHERE {' AND '.join(filters)}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return self._row_to_evaluation(row) if row else None

    def resolve_ref(self, prompt_id: str, ref: int | str) -> ReviewRef:
        if isinstance(ref, int):
            return ReviewRef(input_ref=str(ref), resolved_version=ref, ref_kind="version")
        try:
            version = int(ref)
            return ReviewRef(input_ref=str(ref), resolved_version=version, ref_kind="version")
        except (TypeError, ValueError):
            return ReviewRef(
                input_ref=str(ref),
                resolved_version=self.get_label(prompt_id, str(ref)),
                ref_kind="label",
            )

    def _resolve_ref(self, prompt_id: str, ref: int | str) -> int:
        return self.resolve_ref(prompt_id, ref).resolved_version

    def _diff_lines(
        self,
        left_lines: list[str],
        right_lines: list[str],
        fromfile: str,
        tofile: str,
        mode: str,
    ) -> str:
        if mode == "unified":
            diff_lines = difflib.unified_diff(
                left_lines,
                right_lines,
                fromfile=fromfile,
                tofile=tofile,
            )
        elif mode == "context":
            diff_lines = difflib.context_diff(
                left_lines,
                right_lines,
                fromfile=fromfile,
                tofile=tofile,
            )
        elif mode == "ndiff":
            diff_lines = difflib.ndiff(left_lines, right_lines)
        else:
            raise ValueError("Unsupported diff mode.")
        return "".join(diff_lines)

    def _diff_metadata(self, prompt_id: str, left: PromptRecord, right: PromptRecord) -> str:
        left_meta = {
            "reason": left.reason,
            "author": left.author,
            "tags": left.tags,
            "env": left.env,
            "collection": left.collection,
            "role": left.role,
            "metrics": left.metrics,
        }
        right_meta = {
            "reason": right.reason,
            "author": right.author,
            "tags": right.tags,
            "env": right.env,
            "collection": right.collection,
            "role": right.role,
            "metrics": right.metrics,
        }
        left_text = json.dumps(left_meta, sort_keys=True, indent=2)
        right_text = json.dumps(right_meta, sort_keys=True, indent=2)
        left_lines = left_text.splitlines(keepends=True)
        right_lines = right_text.splitlines(keepends=True)
        return self._diff_lines(
            left_lines,
            right_lines,
            fromfile=f"{prompt_id}@{left.version}",
            tofile=f"{prompt_id}@{right.version}",
            mode="unified",
        )

    def _metadata_changes(self, left: PromptRecord, right: PromptRecord) -> list[MetadataChange]:
        changes: list[MetadataChange] = []
        pairs = [
            ("reason", left.reason, right.reason),
            ("author", left.author, right.author),
            ("tags", left.tags, right.tags),
            ("env", left.env, right.env),
            ("collection", left.collection, right.collection),
            ("role", left.role, right.role),
            ("metrics", left.metrics, right.metrics),
        ]
        for field, old_value, new_value in pairs:
            if old_value != new_value:
                changes.append(MetadataChange(field=field, old_value=old_value, new_value=new_value))
        return changes

    def _labels_for_versions(self, prompt_id: str, versions: list[int]) -> dict[int, list[str]]:
        labels = self.list_labels(prompt_id)
        by_version = {version: [] for version in sorted(set(versions))}
        for item in labels:
            version = item["version"]
            if version in by_version:
                by_version[version].append(item["label"])
        for version in by_version:
            by_version[version].sort()
        return by_version

    def _markers_for_versions(self, prompt_id: str, versions: list[int]) -> dict[int, list[str]]:
        markers = self.list_markers(prompt_id=prompt_id)
        by_version = {version: [] for version in sorted(set(versions))}
        for item in markers:
            version = item["version"]
            if version in by_version:
                by_version[version].append(item["name"])
        for version in by_version:
            by_version[version].sort()
        return by_version

    def _validate_marker_name(self, name: str) -> None:
        if name not in BUILTIN_MARKERS:
            allowed = ", ".join(BUILTIN_MARKERS)
            raise ValueError(f"Unsupported marker name. Use one of: {allowed}.")

    def _review_warnings(
        self,
        left: PromptRecord,
        right: PromptRecord,
        semantic_summary,
        metadata_changes: list[MetadataChange],
    ) -> list[ReviewWarning]:
        warnings: list[ReviewWarning] = []
        if left.version == right.version:
            warnings.append(
                ReviewWarning(
                    code="same-version",
                    severity="info",
                    message="Comparing a version to itself.",
                )
            )
        if left.env and right.env and left.env != right.env:
            warnings.append(
                ReviewWarning(
                    code="env-changed",
                    severity="warning",
                    message=f"Environment changed from {left.env} to {right.env}.",
                )
            )
        if any(item.category in {"safety", "refusal"} for item in semantic_summary):
            warnings.append(
                ReviewWarning(
                    code="behavior-drift",
                    severity="warning",
                    message="Policy or refusal wording changed; review likely behavior drift carefully.",
                )
            )
        if not semantic_summary and metadata_changes:
            warnings.append(
                ReviewWarning(
                    code="metadata-only",
                    severity="info",
                    message="Only metadata changed; prompt text is unchanged after newline normalization.",
                )
            )
        return warnings

    def _review_notes(self, left: PromptRecord, right: PromptRecord, semantic_summary) -> list[str]:
        notes: list[str] = []
        left_lines = len(normalize_newlines(left.content).splitlines())
        right_lines = len(normalize_newlines(right.content).splitlines())
        if left_lines != right_lines:
            notes.append(f"Line count changed from {left_lines} to {right_lines}.")
        if semantic_summary:
            notes.append("Semantic summaries are heuristic and intentionally conservative.")
        return notes
