
![](https://github.com/Ertugrulmutlu/promptledger/blob/main/assests/PromptLedger.png)
<p align="center">
  <img alt="CI" src="https://github.com/Ertugrulmutlu/promptledger/actions/workflows/ci.yml/badge.svg">
  <img alt="PyPI" src="https://img.shields.io/pypi/v/promptledger?cacheSeconds=300">
  <img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/promptledger">
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
</p>

# PromptLedger

PromptLedger is a **local-first prompt version control system** for developers. It treats prompts like code: every change is versioned, diffable, labeled, and marked — all stored locally in a single SQLite database.

It ships with a small CLI, a Python API, and a **read-only Streamlit viewer**. There are no backend services, no SaaS, and no telemetry.

---

## What it is

* A local prompt change ledger stored in SQLite
* Git-style prompt history with multiple diff modes via `difflib`
* A prompt review workflow with heuristic semantic summaries and markdown export
* Metadata support for `reason`, `author`, `tags`, `env`, `collection`, `role`, and `metrics`
* Label support for release-style pointers plus an append-only label history audit trail
* Marker support for version-attached annotations such as `stable` and `milestone`
* Deterministic exports for history and review artifacts
* CLI and Python API for add / get / list / diff / review / export workflows
* A read-only Streamlit UI with timeline, filtering, visible markers, review, diff, and side-by-side comparison
* Newline normalization to avoid CRLF/LF noise

## What it is NOT

* An LLM framework
* An agent framework
* A SaaS or hosted service
* A prompt playground or editor

---

## Why it exists

Prompt iteration is real production work, but most teams still track prompts in notebooks, scratch files, or chat logs.

PromptLedger provides **inspectable history, diffs, and release semantics** without standing up infrastructure or changing how you work.

Tested on Windows, macOS, and Linux via CI.

---

## Installation

```bash
pip install promptledger
pip install "promptledger[ui]"
```

* The first command installs the core CLI and Python API.
* The second command installs optional Streamlit UI support.

## Quickstart

### CLI

```bash
promptledger init

promptledger add --id onboarding --text "Write a friendly onboarding email." \
  --reason "Initial draft" --tags draft --env dev

promptledger add --id onboarding --file ./prompts/onboarding.txt \
  --reason "Tone shift" --tags draft,marketing --env dev

promptledger add --id onboarding --text "You are the system prompt." \
  --collection support-bot --role system

promptledger add --id onboarding --file ./prompts/onboarding.txt --quick
promptledger add --id onboarding --file ./prompts/onboarding.txt --quick --env staging
promptledger add --id onboarding --file ./prompts/onboarding.txt --quick --role eval

promptledger list
promptledger list --id onboarding
promptledger list --collection support-bot
promptledger list --collection support-bot --role system
promptledger show --id onboarding --version 2

promptledger diff --id onboarding --from 1 --to 2
promptledger diff --id onboarding --from prod --to staging
promptledger diff --id onboarding --from 1 --to 2 --mode context
promptledger diff --id onboarding --from 1 --to 2 --mode ndiff
promptledger diff --id onboarding --from 1 --to 2 --mode metadata
promptledger diff --id onboarding --from 1 --to 2 --mode summary

promptledger review --id onboarding --from prod --to staging

promptledger export --format jsonl --out prompt_history.jsonl
promptledger export --format csv --out prompt_history.csv
promptledger export review --id onboarding --from prod --to staging --format md --out review.md

promptledger search --contains "friendly" --id onboarding --tag draft --env dev
promptledger search --collection support-bot --role system

promptledger label set --id onboarding --version 2 --name prod
promptledger label history --id onboarding
promptledger marker set --id onboarding --version 2 --name stable
promptledger marker list --id onboarding
promptledger stable --id onboarding
promptledger milestone --id onboarding --version 1

promptledger status
promptledger ui
```

Notes:

* `promptledger list` lists all prompt versions across all prompts.
* `promptledger list --id onboarding` lists versions for a single prompt.
* `promptledger add --quick` reuses metadata defaults from the latest version of the same prompt id.
* With `--quick`, explicitly passed CLI values still win over inherited metadata.
* `--quick` inherits safe prompt metadata such as `author`, `tags`, `env`, `collection`, and `role`.
* `reason` remains optional and is not inherited by `--quick`.
* `metrics` are not inherited by `--quick`.
* If the new content is unchanged from the latest version, no new version is created.
* `promptledger search` exits with code `0` even when no results are found and prints `0 results`.
* `promptledger list` supports `--collection` and `--role` filters.
* `promptledger search` supports `--collection` and `--role` filters, and may be used as a metadata-only search when `--contains` is omitted.
* `promptledger stable --id <prompt_id>` and `promptledger milestone --id <prompt_id>` apply markers to the latest version when `--version` is omitted.
* `promptledger ui` launches a read-only Streamlit UI.

### Python API

```python
from promptledger import PromptLedger

ledger = PromptLedger()
ledger.init()

ledger.add(
    "summary",
    "Summarize the document in 3 bullets.",
    tags=["draft"],
    env="dev",
    collection="chunking-lab",
    role="template",
    metrics={"accuracy": 0.92},
)

ledger.add(
    "summary",
    "Summarize the document in 5 bullets.",
    tags=["draft"],
    env="dev",
    collection="chunking-lab",
    role="eval",
    metrics={"accuracy": 0.94},
)

latest = ledger.get("summary")
print(latest.version, latest.content)
print(ledger.diff("summary", 1, 2))

review = ledger.review("summary", 1, 2)
print(review.semantic_summary)
print(ledger.export_review_markdown("summary", 1, 2))
```

## Metadata

Each prompt version can store:

* `reason`
* `author`
* `tags`
* `env` (`dev`, `staging`, `prod`)
* `collection` (free-form grouping such as `chunking-lab` or `support-bot`)
* `role` (`system`, `user`, `template`, `modelfile`, `eval`)
* `metrics` (for example accuracy, latency, or cost)

This turns raw text history into a lightweight audit trail.

## Faster iteration with `--quick`

Use `--quick` when you are iterating on an existing prompt and want to avoid retyping metadata on every version.

```bash
promptledger add --id onboarding --file ./prompts/onboarding.txt --quick
promptledger add --id onboarding --file ./prompts/onboarding.txt --quick --env staging
promptledger add --id onboarding --file ./prompts/onboarding.txt --quick --role eval
```

Behavior:

* PromptLedger looks up the latest version for the same prompt id.
* It reuses safe metadata defaults from that latest version, including `author`, `tags`, `env`, `collection`, and `role`.
* Any explicitly provided CLI argument overrides the inherited value.
* The command still creates a normal new prompt version through the standard `add` flow.
* If no previous version exists, `--quick` falls back to normal `add` behavior.
* If the content is unchanged, PromptLedger keeps the existing no-op behavior and does not create a duplicate version.

## Lightweight prompt grouping

PromptLedger supports a small organizational layer on top of version metadata:

* `collection` is an optional free-form grouping name for related prompts
* `role` is an optional built-in prompt role

Supported roles:

* `system`
* `user`
* `template`
* `modelfile`
* `eval`

Examples:

```bash
promptledger add --id chunk-clunker --text "..." --collection chunking-lab --role system
promptledger list --collection chunking-lab
promptledger list --collection chunking-lab --role eval
promptledger search --role modelfile
promptledger search --collection chunking-lab --role system
```

## Labels

Labels are human-readable pointers to specific prompt versions. Use them to track active releases such as `prod`, `staging`, or `latest` without creating new prompt versions.

Every label change is recorded in an append-only label history log.

```bash
promptledger label set --id onboarding --version 7 --name prod
promptledger label set --id onboarding --version 9 --name staging
promptledger label get --id onboarding --name prod
promptledger label list --id onboarding
promptledger label history --id onboarding
promptledger status --id onboarding
```

## Markers

Markers are semantic annotations attached to a specific version. Unlike labels, they do not move and they do not act as release pointers.

Use labels for release-style pointers such as `prod`, `staging`, and `latest`.

Use markers for version-attached meaning:

* `stable` for a reliable baseline worth returning to
* `milestone` for an important checkpoint in the prompt's evolution

A prompt can have multiple `stable` versions and multiple `milestone` versions across its history. A single version can have one marker, both markers, or none.

```bash
promptledger marker set --id onboarding --version 7 --name stable
promptledger marker set --id onboarding --version 7 --name milestone
promptledger marker show --id onboarding --version 7
promptledger marker list --id onboarding
promptledger marker remove --id onboarding --version 7 --name milestone

promptledger stable --id onboarding
promptledger milestone --id onboarding --version 7
```

`promptledger show` includes markers for the selected version, and `promptledger list --id <prompt_id>` surfaces marker information inline for marked versions.

## Newline normalization

* Line endings are normalized to LF for hashing and diffing.
* CRLF and LF content are treated as the same prompt content.
* Review summaries avoid fake changes caused only by line-ending differences.

## Storage location

* Inside a Git repository: `<repo_root>/.promptledger/promptledger.db`
* Outside Git: `<cwd>/.promptledger/promptledger.db`
* Environment override: `PROMPTLEDGER_HOME=/custom/path`
* Explicit override: `PromptLedger(db_path="/abs/path/to.db")`

---

## Export determinism

* CSV exports use a stable column order.
* JSONL exports use sorted keys.
* Repeated exports of the same data are byte-identical.
* Review markdown export is deterministic for the same input.

## Prompt Review

Prompt review is a small, local-first release and regression review workflow. It compares two explicit versions or labels, resolves them to concrete versions, and produces:

* heuristic semantic summary notes
* deterministic metadata changes
* label context for compared refs
* warning flags for likely review hotspots

The semantic summary is rule-based only. It does not call external APIs and stays intentionally conservative when a change is noisy or ambiguous.

```bash
promptledger review --id onboarding --from prod --to staging
promptledger diff --id onboarding --from 7 --to 9 --mode summary
promptledger export review --id onboarding --from prod --to staging --format md --out onboarding_review.md
```

### Concise review output example

```text
Prompt Review: onboarding
From: prod -> v7
To: staging -> v9

Semantic summary
- Constraints tightened.
- Output format changed from bullets to json.

Metadata changes
- `env`: prod -> staging
```

### Markdown export example

```md
# Prompt Review: `onboarding`

## Compared refs

- From: `prod` -> `v7`
- To: `staging` -> `v9`
```

---

## Storage model

### 1. Identify scope

* `promptledger list --id <prompt_id>` to inspect recent versions
* `promptledger label list --id <prompt_id>` to inspect active releases
* `promptledger marker list --id <prompt_id>` to inspect stable and milestone versions

### 2. Review the change

* `promptledger diff --id <prompt_id> --from <old> --to <new>`
* `promptledger diff --id <prompt_id> --from <old> --to <new> --mode summary`
* `promptledger review --id <prompt_id> --from <old> --to <new>`

Focus on intent, tone, structure, constraints, and formatting expectations.

### 3. Verify metadata

* `promptledger show --id <prompt_id> --version <new>`

Confirm that `reason`, `author`, `tags`, `env`, `collection`, `role`, and `metrics` match the change.

### 4. Validate safety

* Look for accidental secrets or credentials.
* Ensure sensitive data is not embedded in prompt text.

### 5. Promote with labels

* `promptledger label set --id <prompt_id> --version <new> --name <label>`
* Update `prod` or `staging` only after review.

### 6. Annotate important versions with markers

* `promptledger stable --id <prompt_id> --version <new>` to mark a reliable baseline
* `promptledger milestone --id <prompt_id> --version <new>` to mark a turning point
* Use markers for history annotation, not release routing

## Security

PromptLedger does not send prompt data anywhere.

Do not store API keys or secrets in prompt text. Use `--no-secret-warn` to suppress the CLI warning.

## Development

* Python >= 3.10
* Tests with pytest

```bash
pytest
```

## Optional UI note

* The Streamlit viewer includes a read-only review panel for semantic summary, metadata changes, warnings, marker visibility, and side-by-side comparison.
* The viewer surfaces `collection` and `role` in the existing version metadata areas, and shows them in the timeline/details without adding a separate library-management UI.
* Screenshot/GIF placeholder: add a comparison view capture here later if you want visuals in the docs.
