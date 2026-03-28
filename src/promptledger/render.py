"""Deterministic review renderers for terminal and markdown output."""

from __future__ import annotations

import json
from typing import Any

from .review import MetadataChange, ReviewResult


def render_metadata_change_value(value: Any) -> str:
    if value is None:
        return "(empty)"
    if isinstance(value, str):
        return value if value else "(empty)"
    return json.dumps(value, sort_keys=True)


def render_review_text(review: ReviewResult) -> str:
    lines = [
        f"Prompt Review: {review.prompt_id}",
        f"From: {review.from_ref.input_ref} -> v{review.from_ref.resolved_version}",
        f"To: {review.to_ref.input_ref} -> v{review.to_ref.resolved_version}",
        "",
        "Semantic summary",
    ]
    if review.semantic_summary:
        lines.extend(f"- {item.summary}" for item in review.semantic_summary)
    else:
        lines.append("- No confident semantic change detected.")

    lines.extend(["", "Metadata changes"])
    if review.metadata_changes:
        lines.extend(_metadata_lines(review.metadata_changes))
    else:
        lines.append("- None")

    lines.extend(["", "Warnings"])
    if review.warnings:
        lines.extend(f"- [{item.severity}] {item.message}" for item in review.warnings)
    else:
        lines.append("- None")

    lines.extend(["", "Label context"])
    label_lines = _label_context_lines(review.label_context)
    if label_lines:
        lines.extend(label_lines)
    else:
        lines.append("- None")

    if review.notes:
        lines.extend(["", "Notes"])
        lines.extend(f"- {note}" for note in review.notes)

    return "\n".join(lines).rstrip() + "\n"


def export_review_markdown(review: ReviewResult) -> str:
    lines = [
        f"# Prompt Review: `{review.prompt_id}`",
        "",
        "## Compared refs",
        "",
        f"- From: `{review.from_ref.input_ref}` -> `v{review.from_ref.resolved_version}`",
        f"- To: `{review.to_ref.input_ref}` -> `v{review.to_ref.resolved_version}`",
        "",
        "## Semantic summary",
        "",
    ]
    if review.semantic_summary:
        lines.extend(f"- {item.summary}" for item in review.semantic_summary)
    else:
        lines.append("- No confident semantic change detected.")

    lines.extend(["", "## Text diff", ""])
    if review.text_changed:
        lines.append("- Text content changed. Use `promptledger diff` for line-level detail.")
    else:
        lines.append("- No text change detected.")

    lines.extend(["", "## Metadata changes", ""])
    if review.metadata_changes:
        lines.extend(_metadata_lines(review.metadata_changes))
    else:
        lines.append("- None")

    lines.extend(["", "## Warnings", ""])
    if review.warnings:
        lines.extend(f"- [{item.severity}] {item.message}" for item in review.warnings)
    else:
        lines.append("- None")

    lines.extend(["", "## Label information", ""])
    label_lines = _label_context_lines(review.label_context)
    if label_lines:
        lines.extend(label_lines)
    else:
        lines.append("- None")

    lines.extend(["", "## Reviewer notes", "", "- _Add reviewer notes here._", ""])
    return "\n".join(lines)


def _metadata_lines(changes: list[MetadataChange]) -> list[str]:
    lines: list[str] = []
    for item in changes:
        old_value = render_metadata_change_value(item.old_value)
        new_value = render_metadata_change_value(item.new_value)
        lines.append(f"- `{item.field}`: {old_value} -> {new_value}")
    return lines


def _label_context_lines(label_context: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    compared = label_context.get("compared_refs", {})
    for key in ("from", "to"):
        item = compared.get(key)
        if item and item.get("ref_kind") == "label":
            lines.append(
                f"- `{key}` label `{item['input_ref']}` currently resolves to `v{item['resolved_version']}`"
            )

    labels_by_version = label_context.get("labels_by_version", {})
    for version in sorted(labels_by_version):
        labels = labels_by_version[version]
        if labels:
            lines.append(f"- `v{version}` labels: {', '.join(labels)}")
    return lines
