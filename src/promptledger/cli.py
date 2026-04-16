"""CLI for PromptLedger."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .core import (
    BUILTIN_MARKERS,
    BUILTIN_ROLES,
    PromptLedger,
    contains_secret,
    normalize_collection,
    normalize_newlines,
)
from .render import render_review_text
from .ui import launch_ui


def _format_timestamp(value: str) -> str:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return value


def _parse_tags(value: str | None) -> list[str] | None:
    if not value:
        return None
    tags = [tag.strip() for tag in value.split(",") if tag.strip()]
    return tags or None


def _parse_metrics(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid metrics JSON: {exc}") from exc


def _resolve_add_metadata_defaults(
    ledger: PromptLedger, args
) -> tuple[str | None, list[str] | None, str | None, str | None, str | None]:
    tags = _parse_tags(args.tags)
    collection = normalize_collection(args.collection)
    if not args.quick:
        return args.author, tags, args.env, collection, args.role

    latest = ledger.get(args.prompt_id)
    if latest is None:
        return args.author, tags, args.env, collection, args.role

    author = args.author if args.author is not None else latest.author
    resolved_tags = tags if tags is not None else latest.tags
    env = args.env if args.env is not None else latest.env
    resolved_collection = collection if args.collection is not None else latest.collection
    role = args.role if args.role is not None else latest.role
    return author, resolved_tags, env, resolved_collection, role


def _print_record(record) -> None:
    tags = ",".join(record.tags) if record.tags else ""
    env = record.env or ""
    collection = record.collection or ""
    role = record.role or ""
    reason = record.reason or ""
    created = _format_timestamp(record.created_at)
    print(f"{record.prompt_id}\t{record.version}\t{created}\t{env}\t{collection}\t{role}\t{tags}\t{reason}")


def _print_record_with_markers(record, markers: list[str] | None = None) -> None:
    tags = ",".join(record.tags) if record.tags else ""
    env = record.env or ""
    collection = record.collection or ""
    role = record.role or ""
    reason = record.reason or ""
    marker_text = ",".join(markers or [])
    created = _format_timestamp(record.created_at)
    print(
        f"{record.prompt_id}\t{record.version}\t{created}\t{env}\t{collection}\t{role}\t{tags}\t{reason}\t{marker_text}"
    )


def _resolve_target_version(ledger: PromptLedger, prompt_id: str, version: int | None) -> int:
    if version is not None:
        return version
    latest = ledger.get(prompt_id)
    if latest is None:
        raise ValueError("Prompt version not found.")
    return latest.version


def _markers_by_prompt_version(items: list[dict[str, object]]) -> dict[tuple[str, int], list[str]]:
    result: dict[tuple[str, int], list[str]] = {}
    for item in items:
        key = (str(item["prompt_id"]), int(item["version"]))
        result.setdefault(key, []).append(str(item["name"]))
    for names in result.values():
        names.sort()
    return result


def _error(message: str, code: int) -> int:
    print(message, file=sys.stderr)
    return code


def _print_enzo_easter_egg() -> None:
    print("Thanks, UnclaEnzo.")
    print("Your early feedback helped shape PromptLedger:")
    print("lower-friction iteration, prompt-library thinking, and respect for messy workflows.")
    print("Sometimes a funny idea turns out to be a good idea.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="promptledger", description="Local prompt version control.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize a PromptLedger database.")
    subparsers.add_parser("enzo")

    add_parser = subparsers.add_parser("add", help="Add a new prompt version.")
    add_parser.add_argument("--id", required=True, dest="prompt_id")
    add_group = add_parser.add_mutually_exclusive_group(required=True)
    add_group.add_argument("--file", type=Path)
    add_group.add_argument("--text")
    add_parser.add_argument("--reason")
    add_parser.add_argument("--author")
    add_parser.add_argument("--tags", help="Comma-separated tags")
    add_parser.add_argument("--env", choices=["dev", "staging", "prod"])
    add_parser.add_argument("--collection")
    add_parser.add_argument("--role", choices=BUILTIN_ROLES)
    add_parser.add_argument("--metrics", help="JSON metrics payload")
    add_parser.add_argument(
        "--quick",
        action="store_true",
        help="Reuse metadata defaults from the latest version of the same prompt id.",
    )
    add_parser.add_argument("--no-secret-warn", action="store_true", help="Disable secret warning")

    list_parser = subparsers.add_parser("list", help="List prompt versions.")
    list_parser.add_argument("--id", dest="prompt_id")
    list_parser.add_argument("--collection")
    list_parser.add_argument("--role", choices=BUILTIN_ROLES)

    show_parser = subparsers.add_parser("show", help="Show a prompt version.")
    show_parser.add_argument("--id", required=True, dest="prompt_id")
    show_parser.add_argument("--version", type=int)

    diff_parser = subparsers.add_parser("diff", help="Diff two versions.")
    diff_parser.add_argument("--id", required=True, dest="prompt_id")
    diff_parser.add_argument("--from", dest="from_version", required=True)
    diff_parser.add_argument("--to", dest="to_version", required=True)
    diff_parser.add_argument(
        "--mode",
        choices=["unified", "context", "ndiff", "metadata", "summary"],
        default="unified",
    )

    review_parser = subparsers.add_parser("review", help="Review two prompt versions or labels.")
    review_parser.add_argument("--id", required=True, dest="prompt_id")
    review_parser.add_argument("--from", dest="from_version", required=True)
    review_parser.add_argument("--to", dest="to_version", required=True)

    status_parser = subparsers.add_parser("status", help="Show prompt status.")
    status_parser.add_argument("--id", dest="prompt_id")

    export_parser = subparsers.add_parser("export", help="Export prompt history.")
    export_parser.add_argument("export_command", nargs="?")
    export_parser.add_argument("--format", choices=["jsonl", "csv", "md"], required=True)
    export_parser.add_argument("--out", type=Path, required=True)
    export_parser.add_argument("--id", dest="prompt_id")
    export_parser.add_argument("--from", dest="from_version")
    export_parser.add_argument("--to", dest="to_version")

    search_parser = subparsers.add_parser("search", help="Search prompt content.")
    search_parser.add_argument("--contains", default="")
    search_parser.add_argument("--id", dest="prompt_id")
    search_parser.add_argument("--author")
    search_parser.add_argument("--tag")
    search_parser.add_argument("--env", choices=["dev", "staging", "prod"])
    search_parser.add_argument("--collection")
    search_parser.add_argument("--role", choices=BUILTIN_ROLES)

    label_parser = subparsers.add_parser("label", help="Manage labels.")
    label_sub = label_parser.add_subparsers(dest="label_command", required=True)
    label_set = label_sub.add_parser("set", help="Set a label to a version.")
    label_set.add_argument("--id", dest="prompt_id", required=True)
    label_set.add_argument("--version", type=int, required=True)
    label_set.add_argument("--name", dest="label", required=True)

    label_get = label_sub.add_parser("get", help="Get a label version.")
    label_get.add_argument("--id", dest="prompt_id", required=True)
    label_get.add_argument("--name", dest="label", required=True)

    label_list = label_sub.add_parser("list", help="List labels.")
    label_list.add_argument("--id", dest="prompt_id")

    label_history = label_sub.add_parser("history", help="Show label history.")
    label_history.add_argument("--id", dest="prompt_id")
    label_history.add_argument("--name", dest="label")
    label_history.add_argument("--limit", type=int, default=200)

    marker_parser = subparsers.add_parser("marker", help="Manage markers.")
    marker_sub = marker_parser.add_subparsers(dest="marker_command", required=True)
    marker_set = marker_sub.add_parser("set", help="Attach a marker to a version.")
    marker_set.add_argument("--id", dest="prompt_id", required=True)
    marker_set.add_argument("--version", type=int, required=True)
    marker_set.add_argument("--name", required=True, choices=BUILTIN_MARKERS)

    marker_remove = marker_sub.add_parser("remove", help="Remove a marker from a version.")
    marker_remove.add_argument("--id", dest="prompt_id", required=True)
    marker_remove.add_argument("--version", type=int, required=True)
    marker_remove.add_argument("--name", required=True, choices=BUILTIN_MARKERS)

    marker_list = marker_sub.add_parser("list", help="List markers for a prompt.")
    marker_list.add_argument("--id", dest="prompt_id", required=True)

    marker_show = marker_sub.add_parser("show", help="Show markers for a prompt version.")
    marker_show.add_argument("--id", dest="prompt_id", required=True)
    marker_show.add_argument("--version", type=int, required=True)

    stable_parser = subparsers.add_parser("stable", help="Mark a version as stable.")
    stable_parser.add_argument("--id", dest="prompt_id", required=True)
    stable_parser.add_argument("--version", type=int)

    milestone_parser = subparsers.add_parser("milestone", help="Mark a version as milestone.")
    milestone_parser.add_argument("--id", dest="prompt_id", required=True)
    milestone_parser.add_argument("--version", type=int)

    subparsers.add_parser("ui", help="Launch the Streamlit UI.")

    args = parser.parse_args(argv)
    ledger = PromptLedger()

    try:
        if args.command == "init":
            path = ledger.init()
            print(f"Initialized PromptLedger at {path}")
        elif args.command == "enzo":
            _print_enzo_easter_egg()
        elif args.command == "add":
            content = args.text
            if args.file:
                if not args.file.exists():
                    return _error(f"File not found: {args.file}", 1)
                try:
                    content = args.file.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    return _error(f"Failed to read file: {args.file} ({exc})", 1)
                if "\ufffd" in content:
                    print(
                        f"Warning: {args.file} contained invalid UTF-8; replacements were made.",
                        file=sys.stderr,
                    )
            content = normalize_newlines(content)
            if not args.no_secret_warn and contains_secret(content):
                print("Warning: possible secret detected in prompt content.", file=sys.stderr)
            author, tags, env, collection, role = _resolve_add_metadata_defaults(ledger, args)
            metrics = _parse_metrics(args.metrics)
            try:
                result = ledger.add(
                    prompt_id=args.prompt_id,
                    content=content,
                    reason=args.reason,
                    author=author,
                    tags=tags,
                    env=env,
                    collection=collection,
                    role=role,
                    metrics=metrics,
                    warn_on_secrets=False,
                )
            except Exception as exc:
                return _error(f"Failed to add prompt: {exc}", 1)
            if result["created"]:
                print(f"Added {args.prompt_id} version {result['version']}")
            else:
                print(f"No change detected for {args.prompt_id}")
        elif args.command == "list":
            records = ledger.list(
                prompt_id=args.prompt_id,
                collection=args.collection,
                role=args.role,
            )
            marker_items = ledger.list_markers(prompt_id=args.prompt_id)
            marker_map = _markers_by_prompt_version(marker_items)
            for record in records:
                markers = marker_map.get((record.prompt_id, record.version), [])
                _print_record_with_markers(record, markers)
        elif args.command == "show":
            record = ledger.get(args.prompt_id, args.version)
            if record is None:
                return _error("Prompt version not found.", 2)
            markers = ledger.get_markers(record.prompt_id, record.version)
            print(f"prompt_id: {record.prompt_id}")
            print(f"version: {record.version}")
            print(f"created_at: {_format_timestamp(record.created_at)}")
            if record.env:
                print(f"env: {record.env}")
            if record.collection:
                print(f"collection: {record.collection}")
            if record.role:
                print(f"role: {record.role}")
            if record.tags:
                print(f"tags: {', '.join(record.tags)}")
            if record.reason:
                print(f"reason: {record.reason}")
            if record.author:
                print(f"author: {record.author}")
            if record.metrics:
                print(f"metrics: {json.dumps(record.metrics)}")
            if markers:
                print(f"markers: {', '.join(markers)}")
            print("\n" + record.content)
        elif args.command == "diff":
            try:
                diff_text = ledger.diff_any(
                    args.prompt_id,
                    args.from_version,
                    args.to_version,
                    mode=args.mode,
                )
            except ValueError as exc:
                return _error(str(exc), 2)
            except Exception as exc:
                return _error(f"Failed to diff prompts: {exc}", 1)
            print(diff_text)
        elif args.command == "review":
            try:
                review = ledger.review(args.prompt_id, args.from_version, args.to_version)
            except ValueError as exc:
                return _error(str(exc), 2)
            except Exception as exc:
                return _error(f"Failed to review prompts: {exc}", 1)
            print(render_review_text(review), end="")
        elif args.command == "status":
            try:
                status = ledger.status(args.prompt_id)
            except Exception as exc:
                return _error(f"Failed to get status: {exc}", 1)
            if not status:
                print("0 results")
            else:
                for prompt_id, info in status.items():
                    latest_created = info.get("latest_created_at") or ""
                    latest_created_fmt = _format_timestamp(latest_created) if latest_created else ""
                    labels = info.get("labels", {})
                    label_parts = [
                        f"{label}->{labels[label]}" for label in sorted(labels.keys())
                    ]
                    label_text = ",".join(label_parts)
                    print(
                        f"{prompt_id}\t{info['latest_version']}\t{latest_created_fmt}\t{label_text}"
                    )
        elif args.command == "export":
            if args.export_command == "review":
                if not args.prompt_id or not args.from_version or not args.to_version:
                    return _error("Review export requires --id, --from, and --to.", 2)
                if args.format != "md":
                    return _error("Review export currently supports only --format md.", 2)
                try:
                    markdown = ledger.export_review_markdown(
                        args.prompt_id,
                        args.from_version,
                        args.to_version,
                    )
                    args.out.write_text(markdown, encoding="utf-8")
                except ValueError as exc:
                    return _error(str(exc), 2)
                except Exception as exc:
                    return _error(f"Failed to export review: {exc}", 1)
                print(f"Exported to {args.out}")
            else:
                if args.export_command:
                    return _error("Unknown export command.", 2)
                if args.format == "md":
                    return _error("History export supports only jsonl or csv.", 2)
                path = ledger.export(args.format, args.out)
                print(f"Exported to {path}")
        elif args.command == "search":
            records = ledger.search(
                contains=args.contains,
                prompt_id=args.prompt_id,
                author=args.author,
                tag=args.tag,
                env=args.env,
                collection=args.collection,
                role=args.role,
            )
            if not records:
                print("0 results")
            else:
                for record in records:
                    _print_record(record)
        elif args.command == "label":
            if args.label_command == "set":
                try:
                    ledger.set_label(args.prompt_id, args.version, args.label)
                except ValueError as exc:
                    return _error(str(exc), 2)
                except Exception as exc:
                    return _error(f"Failed to set label: {exc}", 1)
                print(f"Set label {args.label} -> {args.prompt_id}@{args.version}")
            elif args.label_command == "get":
                try:
                    version = ledger.get_label(args.prompt_id, args.label)
                except ValueError as exc:
                    return _error(str(exc), 2)
                except Exception as exc:
                    return _error(f"Failed to get label: {exc}", 1)
                print(f"{args.prompt_id}@{version}")
            elif args.label_command == "list":
                try:
                    labels = ledger.list_labels(args.prompt_id)
                except Exception as exc:
                    return _error(f"Failed to list labels: {exc}", 1)
                if not labels:
                    print("0 results")
                else:
                    for item in labels:
                        updated = _format_timestamp(item["updated_at"])
                        print(
                            f"{item['prompt_id']}\t{item['label']}\t{item['version']}\t{updated}"
                        )
            elif args.label_command == "history":
                try:
                    events = ledger.list_label_events(
                        prompt_id=args.prompt_id,
                        label=args.label,
                        limit=args.limit,
                    )
                except Exception as exc:
                    return _error(f"Failed to list label history: {exc}", 1)
                if not events:
                    print("0 results")
                else:
                    for item in events:
                        updated = _format_timestamp(item["updated_at"])
                        old_version = "" if item["old_version"] is None else str(item["old_version"])
                        print(
                            f"{item['prompt_id']}\t{item['label']}\t{old_version}\t{item['new_version']}\t{updated}"
                        )
            else:
                return _error("Unknown label command.", 2)
        elif args.command == "marker":
            if args.marker_command == "set":
                try:
                    created = ledger.set_marker(args.prompt_id, args.version, args.name)
                except ValueError as exc:
                    return _error(str(exc), 2)
                except Exception as exc:
                    return _error(f"Failed to set marker: {exc}", 1)
                action = "Set" if created else "Marker already set"
                print(f"{action} marker {args.name} on {args.prompt_id}@{args.version}")
            elif args.marker_command == "remove":
                try:
                    removed = ledger.remove_marker(args.prompt_id, args.version, args.name)
                except ValueError as exc:
                    return _error(str(exc), 2)
                except Exception as exc:
                    return _error(f"Failed to remove marker: {exc}", 1)
                action = "Removed" if removed else "Marker not present"
                print(f"{action} {args.name} on {args.prompt_id}@{args.version}")
            elif args.marker_command == "list":
                try:
                    markers = ledger.list_markers(prompt_id=args.prompt_id)
                except Exception as exc:
                    return _error(f"Failed to list markers: {exc}", 1)
                if not markers:
                    print("0 results")
                else:
                    for item in markers:
                        created = _format_timestamp(item["created_at"])
                        print(
                            f"{item['prompt_id']}\t{item['version']}\t{item['name']}\t{created}"
                        )
            elif args.marker_command == "show":
                try:
                    markers = ledger.get_markers(args.prompt_id, args.version)
                except ValueError as exc:
                    return _error(str(exc), 2)
                except Exception as exc:
                    return _error(f"Failed to show markers: {exc}", 1)
                if not markers:
                    print("0 results")
                else:
                    print(", ".join(markers))
            else:
                return _error("Unknown marker command.", 2)
        elif args.command in {"stable", "milestone"}:
            marker_name = args.command
            try:
                version = _resolve_target_version(ledger, args.prompt_id, args.version)
                created = ledger.set_marker(args.prompt_id, version, marker_name)
            except ValueError as exc:
                return _error(str(exc), 2)
            except Exception as exc:
                return _error(f"Failed to set marker: {exc}", 1)
            action = "Set" if created else "Marker already set"
            print(f"{action} marker {marker_name} on {args.prompt_id}@{version}")
        elif args.command == "ui":
            launch_ui()
        else:
            return _error("Unknown command.", 2)
    except RuntimeError as exc:
        return _error(str(exc), 2)
    except Exception as exc:
        return _error(f"Unexpected error: {exc}", 1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
