"""CLI for PromptLedger."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .core import PromptLedger, contains_secret, normalize_newlines


def _format_timestamp(value: str) -> str:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return value
from .ui import launch_ui


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


def _print_record(record) -> None:
    tags = ",".join(record.tags) if record.tags else ""
    env = record.env or ""
    reason = record.reason or ""
    created = _format_timestamp(record.created_at)
    print(f"{record.prompt_id}\t{record.version}\t{created}\t{env}\t{tags}\t{reason}")


def _error(message: str, code: int) -> int:
    print(message, file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="promptledger", description="Local prompt version control.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize a PromptLedger database.")

    add_parser = subparsers.add_parser("add", help="Add a new prompt version.")
    add_parser.add_argument("--id", required=True, dest="prompt_id")
    add_group = add_parser.add_mutually_exclusive_group(required=True)
    add_group.add_argument("--file", type=Path)
    add_group.add_argument("--text")
    add_parser.add_argument("--reason")
    add_parser.add_argument("--author")
    add_parser.add_argument("--tags", help="Comma-separated tags")
    add_parser.add_argument("--env", choices=["dev", "staging", "prod"])
    add_parser.add_argument("--metrics", help="JSON metrics payload")
    add_parser.add_argument("--no-secret-warn", action="store_true", help="Disable secret warning")

    list_parser = subparsers.add_parser("list", help="List prompt versions.")
    list_parser.add_argument("--id", dest="prompt_id")

    show_parser = subparsers.add_parser("show", help="Show a prompt version.")
    show_parser.add_argument("--id", required=True, dest="prompt_id")
    show_parser.add_argument("--version", type=int)

    diff_parser = subparsers.add_parser("diff", help="Diff two versions.")
    diff_parser.add_argument("--id", required=True, dest="prompt_id")
    diff_parser.add_argument("--from", dest="from_version", type=int, required=True)
    diff_parser.add_argument("--to", dest="to_version", type=int, required=True)

    export_parser = subparsers.add_parser("export", help="Export prompt history.")
    export_parser.add_argument("--format", choices=["jsonl", "csv"], required=True)
    export_parser.add_argument("--out", type=Path, required=True)

    search_parser = subparsers.add_parser("search", help="Search prompt content.")
    search_parser.add_argument("--contains", required=True)
    search_parser.add_argument("--id", dest="prompt_id")
    search_parser.add_argument("--author")
    search_parser.add_argument("--tag")
    search_parser.add_argument("--env", choices=["dev", "staging", "prod"])

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

    subparsers.add_parser("ui", help="Launch the Streamlit UI.")

    args = parser.parse_args(argv)
    ledger = PromptLedger()

    try:
        if args.command == "init":
            path = ledger.init()
            print(f"Initialized PromptLedger at {path}")
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
            tags = _parse_tags(args.tags)
            metrics = _parse_metrics(args.metrics)
            try:
                result = ledger.add(
                    prompt_id=args.prompt_id,
                    content=content,
                    reason=args.reason,
                    author=args.author,
                    tags=tags,
                    env=args.env,
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
            records = ledger.list(prompt_id=args.prompt_id)
            for record in records:
                _print_record(record)
        elif args.command == "show":
            record = ledger.get(args.prompt_id, args.version)
            if record is None:
                return _error("Prompt version not found.", 2)
            print(f"prompt_id: {record.prompt_id}")
            print(f"version: {record.version}")
            print(f"created_at: {_format_timestamp(record.created_at)}")
            if record.env:
                print(f"env: {record.env}")
            if record.tags:
                print(f"tags: {', '.join(record.tags)}")
            if record.reason:
                print(f"reason: {record.reason}")
            if record.author:
                print(f"author: {record.author}")
            if record.metrics:
                print(f"metrics: {json.dumps(record.metrics)}")
            print("\n" + record.content)
        elif args.command == "diff":
            try:
                diff_text = ledger.diff(args.prompt_id, args.from_version, args.to_version)
            except ValueError as exc:
                return _error(str(exc), 2)
            except Exception as exc:
                return _error(f"Failed to diff prompts: {exc}", 1)
            print(diff_text)
        elif args.command == "export":
            path = ledger.export(args.format, args.out)
            print(f"Exported to {path}")
        elif args.command == "search":
            records = ledger.search(
                contains=args.contains,
                prompt_id=args.prompt_id,
                author=args.author,
                tag=args.tag,
                env=args.env,
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
            else:
                return _error("Unknown label command.", 2)
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
