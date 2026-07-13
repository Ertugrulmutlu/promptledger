"""Dashboard data helpers with read-only prompt content."""

from __future__ import annotations

import difflib
from typing import Any

from promptledger.core import PromptLedger, PromptRecord, normalize_newlines, validate_role
from promptledger.evaluation import compare_runs


def _record_to_summary(
    record: PromptRecord,
    labels: dict[int, list[str]] | None = None,
    markers: dict[int, list[str]] | None = None,
    evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    version = record.version
    preview = " ".join(record.content.split())
    if len(preview) > 220:
        preview = preview[:217].rstrip() + "..."
    return {
        "prompt_id": record.prompt_id,
        "version": version,
        "created_at": record.created_at,
        "updated_at": record.created_at,
        "reason": record.reason,
        "author": record.author,
        "env": record.env,
        "collection": record.collection,
        "role": record.role,
        "tags": record.tags or [],
        "labels": (labels or {}).get(version, []),
        "markers": (markers or {}).get(version, []),
        "content_preview": preview,
        "evaluation_status": "EVALUATED" if evaluation else "NO EVAL DATA",
        "latest_evaluation": evaluation,
    }


def _record_to_detail(
    record: PromptRecord,
    labels: dict[int, list[str]] | None = None,
    markers: dict[int, list[str]] | None = None,
    evaluations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evaluation = evaluations[0] if evaluations else None
    result = _record_to_summary(
        record, labels=labels, markers=markers, evaluation=evaluation
    )
    result.update(
        {
            "content": record.content,
            "content_hash": record.content_hash,
            "metrics": record.metrics or {},
            "evaluations": evaluations or [],
        }
    )
    return result


def _labels_by_version(ledger: PromptLedger, prompt_id: str | None = None) -> dict[str, dict[int, list[str]]]:
    result: dict[str, dict[int, list[str]]] = {}
    for item in ledger.list_labels(prompt_id):
        prompt = str(item["prompt_id"])
        version = int(item["version"])
        result.setdefault(prompt, {}).setdefault(version, []).append(str(item["label"]))
    for versions in result.values():
        for names in versions.values():
            names.sort()
    return result


def _markers_by_version(ledger: PromptLedger, prompt_id: str | None = None) -> dict[str, dict[int, list[str]]]:
    result: dict[str, dict[int, list[str]]] = {}
    for item in ledger.list_markers(prompt_id=prompt_id):
        prompt = str(item["prompt_id"])
        version = int(item["version"])
        result.setdefault(prompt, {}).setdefault(version, []).append(str(item["name"]))
    for versions in result.values():
        for names in versions.values():
            names.sort()
    return result


def _latest_records(ledger: PromptLedger) -> list[PromptRecord]:
    latest: dict[str, PromptRecord] = {}
    for record in ledger.list():
        current = latest.get(record.prompt_id)
        if current is None or record.version > current.version:
            latest[record.prompt_id] = record
    return sorted(latest.values(), key=lambda item: item.created_at, reverse=True)


def _facet_values(records: list[PromptRecord], markers: list[dict[str, Any]]) -> dict[str, list[str]]:
    tags = {tag for record in records for tag in (record.tags or [])}
    return {
        "collections": sorted({record.collection for record in records if record.collection}),
        "roles": sorted({record.role for record in records if record.role}),
        "envs": sorted({record.env for record in records if record.env}),
        "tags": sorted(tags),
        "markers": sorted({str(item["name"]) for item in markers}),
    }


def list_prompts(ledger: PromptLedger) -> dict[str, Any]:
    records = _latest_records(ledger)
    labels = _labels_by_version(ledger)
    markers = _markers_by_version(ledger)
    all_records = ledger.list()
    all_markers = ledger.list_markers()
    latest_evaluations: dict[tuple[str, int], dict[str, Any]] = {}
    for run in ledger.list_evaluations(limit=2_147_483_647):
        latest_evaluations.setdefault((run.prompt_id, run.version), run.to_dict())
    return {
        "prompts": [
            _record_to_summary(
                record,
                labels=labels.get(record.prompt_id, {}),
                markers=markers.get(record.prompt_id, {}),
                evaluation=latest_evaluations.get((record.prompt_id, record.version)),
            )
            for record in records
        ],
        "facets": _facet_values(all_records, all_markers),
    }


def get_prompt(ledger: PromptLedger, prompt_id: str) -> dict[str, Any] | None:
    record = ledger.get(prompt_id)
    if record is None:
        return None
    versions = get_versions(ledger, prompt_id)
    return {
        "prompt_id": prompt_id,
        "latest": _record_to_detail(
            record,
            labels=_labels_by_version(ledger, prompt_id).get(prompt_id, {}),
            markers=_markers_by_version(ledger, prompt_id).get(prompt_id, {}),
            evaluations=[run.to_dict() for run in ledger.list_evaluations(
                prompt_id=prompt_id, ref=record.version
            )],
        ),
        "version_count": len(versions["versions"]),
        "versions": versions["versions"],
    }


def get_versions(ledger: PromptLedger, prompt_id: str) -> dict[str, Any]:
    records = sorted(ledger.list(prompt_id=prompt_id), key=lambda item: item.version, reverse=True)
    labels = _labels_by_version(ledger, prompt_id).get(prompt_id, {})
    markers = _markers_by_version(ledger, prompt_id).get(prompt_id, {})
    latest_evaluations: dict[int, dict[str, Any]] = {}
    for run in ledger.list_evaluations(prompt_id=prompt_id, limit=2_147_483_647):
        latest_evaluations.setdefault(run.version, run.to_dict())
    return {
        "prompt_id": prompt_id,
        "versions": [
            _record_to_summary(
                record, labels=labels, markers=markers,
                evaluation=latest_evaluations.get(record.version),
            ) for record in records
        ],
        "order": "version_desc",
    }


def get_version(ledger: PromptLedger, prompt_id: str, version: int) -> dict[str, Any] | None:
    record = ledger.get(prompt_id, version)
    if record is None:
        return None
    return _record_to_detail(
        record,
        labels=_labels_by_version(ledger, prompt_id).get(prompt_id, {}),
        markers=_markers_by_version(ledger, prompt_id).get(prompt_id, {}),
        evaluations=[run.to_dict() for run in ledger.list_evaluations(
            prompt_id=prompt_id, ref=version
        )],
    )


def list_evaluations(
    ledger: PromptLedger,
    prompt_id: str | None = None,
    ref: int | str | None = None,
    suite: str | None = None,
    model: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    runs = ledger.list_evaluations(prompt_id, ref, suite, model, limit)
    return {"evaluations": [run.to_dict() for run in runs], "count": len(runs)}


def get_evaluation(ledger: PromptLedger, run_id: int) -> dict[str, Any] | None:
    run = ledger.get_evaluation(run_id)
    return run.to_dict() if run else None


def compare_evaluations(
    ledger: PromptLedger,
    prompt_id: str,
    from_ref: int | str,
    to_ref: int | str,
    suite: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    return ledger.compare_evaluations(
        prompt_id, from_ref, to_ref, suite=suite, model=model
    ).to_dict()


def structured_diff(left_text: str, right_text: str) -> dict[str, Any]:
    left_lines = normalize_newlines(left_text).splitlines()
    right_lines = normalize_newlines(right_text).splitlines()
    matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)
    opcodes = []
    for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        display_tag = {"insert": "added", "delete": "removed", "replace": "replaced"}.get(tag, tag)
        left = [
            {"number": index + 1, "text": left_lines[index], "type": display_tag}
            for index in range(left_start, left_end)
        ]
        right = [
            {"number": index + 1, "text": right_lines[index], "type": display_tag}
            for index in range(right_start, right_end)
        ]
        while len(left) < len(right):
            left.append({"number": None, "text": "", "type": "placeholder"})
        while len(right) < len(left):
            right.append({"number": None, "text": "", "type": "placeholder"})
        opcodes.append(
            {
                "type": display_tag,
                "left": left,
                "right": right,
            }
        )
    return {"opcodes": opcodes}


def compare_versions(
    ledger: PromptLedger, prompt_id: str, from_ref: int | str, to_ref: int | str
) -> dict[str, Any]:
    left_ref = ledger.resolve_ref(prompt_id, from_ref)
    right_ref = ledger.resolve_ref(prompt_id, to_ref)
    left = ledger.get(prompt_id, left_ref.resolved_version)
    right = ledger.get(prompt_id, right_ref.resolved_version)
    if left is None or right is None:
        raise ValueError("One or both versions not found.")
    evaluation = None
    baseline_runs = ledger.list_evaluations(
        prompt_id=prompt_id, ref=left_ref.resolved_version, limit=2_147_483_647
    )
    candidate_runs = ledger.list_evaluations(
        prompt_id=prompt_id, ref=right_ref.resolved_version, limit=2_147_483_647
    )
    if baseline_runs and candidate_runs:
        baseline = baseline_runs[0]
        candidate = next(
            (
                run for run in candidate_runs
                if run.suite == baseline.suite and run.model == baseline.model
            ),
            None,
        )
        if candidate is not None:
            evaluation = compare_runs(
                prompt_id, left_ref.to_dict(), right_ref.to_dict(), baseline, candidate
            ).to_dict()
    return {
        "prompt_id": prompt_id,
        "from_ref": left_ref.to_dict(),
        "to_ref": right_ref.to_dict(),
        "diff": structured_diff(left.content, right.content),
        "evaluation": evaluation,
    }


def search_prompts(
    ledger: PromptLedger,
    contains: str = "",
    collection: str | None = None,
    role: str | None = None,
    env: str | None = None,
    tag: str | None = None,
    marker: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    if role:
        validate_role(role)
    records = ledger.search(
        contains=contains,
        collection=collection,
        role=role,
        env=env,
        tag=tag,
    )
    labels = _labels_by_version(ledger)
    markers = _markers_by_version(ledger)
    latest_evaluations: dict[tuple[str, int], dict[str, Any]] = {}
    for run in ledger.list_evaluations(limit=2_147_483_647):
        latest_evaluations.setdefault((run.prompt_id, run.version), run.to_dict())
    if marker:
        records = [
            record
            for record in records
            if marker in markers.get(record.prompt_id, {}).get(record.version, [])
        ]
    if label:
        records = [
            record
            for record in records
            if label in labels.get(record.prompt_id, {}).get(record.version, [])
        ]
    return {
        "results": [
            _record_to_summary(
                record,
                labels=labels.get(record.prompt_id, {}),
                markers=markers.get(record.prompt_id, {}),
                evaluation=latest_evaluations.get((record.prompt_id, record.version)),
            )
            for record in records
        ],
        "count": len(records),
    }


def stats(ledger: PromptLedger) -> dict[str, int]:
    records = ledger.list()
    prompt_ids = {record.prompt_id for record in records}
    collections = {record.collection for record in records if record.collection}
    roles = {record.role for record in records if record.role}
    marked_versions = {
        (str(item["prompt_id"]), int(item["version"])) for item in ledger.list_markers()
    }
    return {
        "prompt_ids": len(prompt_ids),
        "versions": len(records),
        "collections": len(collections),
        "roles": len(roles),
        "marked_versions": len(marked_versions),
    }
