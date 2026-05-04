"""Read-only dashboard data helpers."""

from __future__ import annotations

from typing import Any

from promptledger.core import PromptLedger, PromptRecord, validate_role


def _record_to_summary(
    record: PromptRecord,
    labels: dict[int, list[str]] | None = None,
    markers: dict[int, list[str]] | None = None,
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
    }


def _record_to_detail(
    record: PromptRecord,
    labels: dict[int, list[str]] | None = None,
    markers: dict[int, list[str]] | None = None,
) -> dict[str, Any]:
    result = _record_to_summary(record, labels=labels, markers=markers)
    result.update(
        {
            "content": record.content,
            "content_hash": record.content_hash,
            "metrics": record.metrics or {},
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
    return {
        "prompts": [
            _record_to_summary(
                record,
                labels=labels.get(record.prompt_id, {}),
                markers=markers.get(record.prompt_id, {}),
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
        ),
        "version_count": len(versions["versions"]),
        "versions": versions["versions"],
    }


def get_versions(ledger: PromptLedger, prompt_id: str) -> dict[str, Any]:
    records = sorted(ledger.list(prompt_id=prompt_id), key=lambda item: item.version, reverse=True)
    labels = _labels_by_version(ledger, prompt_id).get(prompt_id, {})
    markers = _markers_by_version(ledger, prompt_id).get(prompt_id, {})
    return {
        "prompt_id": prompt_id,
        "versions": [
            _record_to_summary(record, labels=labels, markers=markers) for record in records
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
    )


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
