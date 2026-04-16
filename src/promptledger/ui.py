"""Streamlit UI for PromptLedger (read-only)."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from promptledger.render import render_metadata_change_value
except Exception:  # pragma: no cover - fallback for direct script execution
    from .render import render_metadata_change_value


def launch_ui() -> None:
    try:
        import streamlit  # noqa: F401
    except Exception as exc:  # pragma: no cover - exercised in manual usage
        raise SystemExit("Streamlit is not installed. Try `pip install promptledger[ui]`.") from exc

    script = Path(__file__).resolve()
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(script)], check=True)


def _load_data():
    try:
        from promptledger.core import PromptLedger
    except Exception:
        from .core import PromptLedger

    ledger = PromptLedger()
    try:
        records = ledger.list()
        labels = ledger.list_labels()
        label_events = ledger.list_label_events(limit=500)
        markers = ledger.list_markers()
    except RuntimeError:
        records = []
        labels = []
        label_events = []
        markers = []
    return ledger, records, labels, label_events, markers


def _labels_for_prompt(labels, prompt_id: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in labels:
        if item["prompt_id"] == prompt_id:
            result[item["label"]] = item["version"]
    return result


def _unique(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _markers_for_prompt_version(markers, prompt_id: str, version: int) -> list[str]:
    result = []
    for item in markers:
        if item["prompt_id"] == prompt_id and item["version"] == version:
            result.append(item["name"])
    return sorted(result)


def _format_timestamp(value: str) -> str:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return value


def _review_badges(review) -> list[str]:
    badges: list[str] = []
    for item in review.warnings:
        badges.append(f"{item.severity.upper()}: {item.message}")
    return badges


def _review_metadata_rows(review) -> list[dict[str, str]]:
    rows = []
    for item in review.metadata_changes:
        rows.append(
            {
                "field": item.field,
                "from": render_metadata_change_value(item.old_value),
                "to": render_metadata_change_value(item.new_value),
            }
        )
    return rows


def app():
    import streamlit as st

    st.set_page_config(page_title="PromptLedger", layout="wide")
    st.title("PromptLedger")
    st.caption("Local-first prompt version history")

    ledger, records, labels, label_events, markers = _load_data()
    if not records:
        st.info("No prompt history found. Run `promptledger init` and `promptledger add`.")
        return

    prompt_ids = _unique([r.prompt_id for r in records])
    all_tags = sorted({tag for r in records if r.tags for tag in r.tags})
    envs = _unique([r.env for r in records if r.env])

    with st.sidebar:
        st.header("Filters")
        prompt_filter = st.selectbox("Prompt", ["All"] + prompt_ids)
        env_filter = st.selectbox("Env", ["All"] + envs)
        tag_filter = st.multiselect("Tags", all_tags)

    filtered = records
    if prompt_filter != "All":
        filtered = [r for r in filtered if r.prompt_id == prompt_filter]
    if env_filter != "All":
        filtered = [r for r in filtered if r.env == env_filter]
    if tag_filter:
        tag_set = set(tag_filter)
        filtered = [r for r in filtered if r.tags and tag_set.intersection(r.tags)]

    st.subheader("Timeline")
    timeline_rows = []
    for r in filtered:
        label_map = _labels_for_prompt(labels, r.prompt_id)
        marker_names = _markers_for_prompt_version(markers, r.prompt_id, r.version)
        timeline_rows.append(
            {
                "prompt_id": r.prompt_id,
                "version": r.version,
                "created_at": _format_timestamp(r.created_at),
                "env": r.env or "",
                "collection": r.collection or "",
                "role": r.role or "",
                "tags": ", ".join(r.tags) if r.tags else "",
                "reason": r.reason or "",
                "labels": ", ".join(
                    f"{label}->{version}" for label, version in sorted(label_map.items())
                )
                if label_map
                else "",
                "markers": ", ".join(marker_names) if marker_names else "",
            }
        )
    st.dataframe(timeline_rows, use_container_width=True)

    st.subheader("Label history")
    label_prompt_ids = _unique([event["prompt_id"] for event in label_events])
    if label_events:
        label_prompt_filter = st.selectbox("Prompt ID (labels)", ["All"] + label_prompt_ids)
        filtered_events = label_events
        if label_prompt_filter != "All":
            filtered_events = [e for e in label_events if e["prompt_id"] == label_prompt_filter]
        event_rows = []
        for event in filtered_events:
            event_rows.append(
                {
                    "prompt_id": event["prompt_id"],
                    "label": event["label"],
                    "old_version": event["old_version"],
                    "new_version": event["new_version"],
                    "updated_at": _format_timestamp(event["updated_at"]),
                }
            )
        st.dataframe(event_rows, use_container_width=True)
    else:
        st.info("No label history found.")

    st.subheader("Inspect")
    selected_prompt = st.selectbox("Prompt ID", prompt_ids)
    versions = [r for r in records if r.prompt_id == selected_prompt]
    versions_sorted = sorted(versions, key=lambda r: r.version)
    version_numbers = [r.version for r in versions_sorted]
    selected_version = st.selectbox("Version", version_numbers, index=len(version_numbers) - 1)
    record = ledger.get(selected_prompt, selected_version)

    if record:
        meta_col, content_col = st.columns([1, 2])
        with meta_col:
            st.markdown("**Metadata**")
            label_map = _labels_for_prompt(labels, record.prompt_id)
            marker_names = _markers_for_prompt_version(markers, record.prompt_id, record.version)
            metadata = {
                "prompt_id": record.prompt_id,
                "version": record.version,
                "created_at": _format_timestamp(record.created_at),
            }
            if record.env:
                metadata["env"] = record.env
            if record.collection:
                metadata["collection"] = record.collection
            if record.role:
                metadata["role"] = record.role
            if record.tags:
                metadata["tags"] = record.tags
            if record.reason:
                metadata["reason"] = record.reason
            if record.author:
                metadata["author"] = record.author
            if record.metrics:
                metadata["metrics"] = record.metrics
            if label_map:
                metadata["labels"] = label_map
            if marker_names:
                metadata["markers"] = marker_names
            st.write(metadata)
        with content_col:
            st.markdown("**Content**")
            st.code(record.content, language="")

    st.subheader("Diff")
    diff_col_left, diff_col_right = st.columns(2)
    with diff_col_left:
        from_version = st.selectbox("From", version_numbers, index=max(0, len(version_numbers) - 2))
    with diff_col_right:
        to_version = st.selectbox("To", version_numbers, index=len(version_numbers) - 1)

    if from_version == to_version:
        st.info("Select two different versions to compare.")
    else:
        review = ledger.review(selected_prompt, from_version, to_version)
        st.markdown("### Review")
        summary_col, warning_col = st.columns([2, 1])
        with summary_col:
            st.markdown("**Semantic summary**")
            if review.semantic_summary:
                for item in review.semantic_summary:
                    st.markdown(f"- {item.summary}")
            else:
                st.caption("No confident semantic change detected.")
        with warning_col:
            st.markdown("**Warnings**")
            badges = _review_badges(review)
            if badges:
                for badge in badges:
                    st.caption(badge)
            else:
                st.caption("None")

        meta_rows = _review_metadata_rows(review)
        st.markdown("**Metadata diff**")
        if meta_rows:
            st.dataframe(meta_rows, use_container_width=True, hide_index=True)
        else:
            st.caption("No metadata changes.")

        diff_text = ledger.diff(selected_prompt, from_version, to_version)
        st.markdown("**Line diff**")
        st.code(diff_text or "(no diff)", language="diff")
        left_record = ledger.get(selected_prompt, from_version)
        right_record = ledger.get(selected_prompt, to_version)
        if left_record and right_record:
            left_col, right_col = st.columns(2)
            with left_col:
                left_markers = _markers_for_prompt_version(markers, selected_prompt, from_version)
                left_title = f"**{selected_prompt}@{from_version}**"
                if left_record.role:
                    left_title += f"  \nRole: {left_record.role}"
                if left_markers:
                    left_title += f"  \nMarkers: {', '.join(left_markers)}"
                st.markdown(left_title)
                st.code(left_record.content, language="")
            with right_col:
                right_markers = _markers_for_prompt_version(markers, selected_prompt, to_version)
                right_title = f"**{selected_prompt}@{to_version}**"
                if right_record.role:
                    right_title += f"  \nRole: {right_record.role}"
                if right_markers:
                    right_title += f"  \nMarkers: {', '.join(right_markers)}"
                st.markdown(right_title)
                st.code(right_record.content, language="")


if __name__ == "__main__":
    app()
