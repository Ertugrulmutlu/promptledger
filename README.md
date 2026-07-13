
![](https://github.com/Ertugrulmutlu/promptledger/blob/main/assests/PromptLedger.png)
<p align="center">
  <img alt="CI" src="https://github.com/Ertugrulmutlu/promptledger/actions/workflows/ci.yml/badge.svg">
  <img alt="PyPI" src="https://img.shields.io/pypi/v/promptledger?cacheSeconds=300">
  <img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/promptledger">
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
</p>

# PromptLedger

PromptLedger is a **local-first prompt version control system** for developers. It treats prompts like code: every change is versioned, diffable, labeled, and marked, all stored locally in a single SQLite database.

It ships with a small CLI, a Python API, and a **local review dashboard**. There are no remote backend services, no SaaS, and no telemetry. The dashboard itself uses a small local HTTP server.

---

## What it is

* A local prompt change ledger stored in SQLite
* Git-style prompt history with multiple diff modes via `difflib`
* A prompt review workflow with heuristic semantic summaries and markdown export
* Metadata support for `reason`, `author`, `tags`, `env`, `collection`, `role`, and `metrics`
* Label support for release-style pointers plus an append-only label history audit trail
* Marker support for version-attached annotations such as `stable` and `milestone`
* Deterministic exports for history and review artifacts
* Evaluation runs, metric comparisons, and policy-based regression gates for externally produced benchmark results
* CLI and Python API for add / get / list / diff / review / evaluate / gate / export workflows
* A local workspace dashboard with read-only prompt content, evaluation history, draggable prompt cards, search, filters, marker controls, version timeline, and a sequence-aware prompt diff
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

CI is configured for Windows, macOS, and Linux with Python 3.10–3.12.

---

## Installation

```bash
pip install promptledger
```

The core install includes the CLI, Python API, and local dashboard.

Legacy Streamlit support remains available as an optional extra:

```bash
pip install "promptledger[ui]"
```

## Quickstart

The following Bash workflow starts with an empty database and creates exactly two versions of one prompt before assigning labels and recording compatible evaluation runs:

```bash
promptledger init

promptledger add --id onboarding \
  --text "Write a concise, friendly onboarding email." \
  --reason "Initial version"

promptledger add --id onboarding \
  --text "Write a concise, friendly onboarding email with three next steps." \
  --reason "Add actionable next steps"

promptledger label set --id onboarding --version 1 --name prod
promptledger label set --id onboarding --version 2 --name staging

promptledger eval record \
  --id onboarding --ref prod --suite support-v1 --model test-model \
  --metrics '{"accuracy":0.84,"latency_ms":380}'

promptledger eval record \
  --id onboarding --ref staging --suite support-v1 --model test-model \
  --metrics '{"accuracy":0.87,"latency_ms":410}'

promptledger eval compare \
  --id onboarding --from prod --to staging \
  --suite support-v1 --model test-model

promptledger dashboard
```

Inline JSON above is intended for Bash-like shells. PowerShell users should use the file-based evaluation workflow shown below. After creating a gate policy, the optional gate step is:

```bash
promptledger eval gate \
  --id onboarding --from prod --to staging \
  --policy promptledger-gate.json
```

## Command reference

These examples are independent reference commands, not additional steps in the Quickstart:

```bash
promptledger list --id onboarding
promptledger show --id onboarding --version 2
promptledger status --id onboarding

promptledger diff --id onboarding --from prod --to staging
promptledger diff --id onboarding --from 1 --to 2 --mode context
promptledger diff --id onboarding --from 1 --to 2 --mode ndiff
promptledger diff --id onboarding --from 1 --to 2 --mode metadata
promptledger diff --id onboarding --from 1 --to 2 --mode summary
promptledger review --id onboarding --from prod --to staging

promptledger search --contains "friendly" --id onboarding
promptledger search --collection support-bot --role system

promptledger marker set --id onboarding --version 2 --name stable
promptledger marker list --id onboarding
promptledger stable --id onboarding
promptledger milestone --id onboarding --version 1

promptledger export --format jsonl --out prompt_history.jsonl
promptledger export --format csv --out prompt_history.csv
promptledger export review --id onboarding --from prod --to staging --format md --out review.md
```

`promptledger add --quick` reuses `author`, `tags`, `env`, `collection`, and `role` from the latest version of the same prompt unless explicitly overridden. It does not inherit `reason` or legacy prompt-version `metrics`. Unchanged content remains a no-op. `promptledger search` returns exit code `0` and prints `0 results` when nothing matches.

## Dashboard

The dashboard is a local prompt workspace for reviewing PromptLedger history and evaluation results. It starts a small local web server and serves static HTML/CSS/JavaScript against the existing SQLite database.

```bash
promptledger dashboard
promptledger dashboard --port 8765
```

The first screen shows prompt cards in a draggable workspace board. Click a card to open prompt text, metadata, version history, evaluation runs, labels, markers, and side-by-side prompt and metric comparisons. Card layout is saved only in browser `localStorage`.

Prompt content is read-only in the dashboard; no prompt content editing occurs there. Evaluation information can be viewed, and local marker metadata (`stable` and `milestone`) can be updated through the same marker system used by the CLI. The dashboard adds no auth, telemetry, remote backend, cloud service, hosted behavior, or provider calls and remains local-first.

## Evaluation runs and regression gates

PromptLedger stores results produced by external benchmark tools; it never runs prompts or calls a model provider. Every evaluation run is attached to a concrete prompt version even when it is recorded through a label. Repeated runs of the same suite are retained.

### Bash: inline JSON

```bash
promptledger eval record \
  --id onboarding \
  --ref prod \
  --suite support-v1 \
  --model test-model \
  --metrics '{"accuracy":0.84,"latency_ms":380}'
```

### PowerShell: JSON file

For PowerShell, `--file` is recommended because native executable argument parsing may alter quotes in inline JSON.

```powershell
$evaluation = [ordered]@{
  suite = "support-v1"
  model = "test-model"
  metrics = [ordered]@{
    accuracy = 0.84
    latency_ms = 380
  }
  metadata = [ordered]@{
    seed = 42
    sample_count = 100
  }
} | ConvertTo-Json -Depth 5

[System.IO.File]::WriteAllText(
  (Join-Path $PWD "evaluation-result.json"),
  $evaluation,
  [System.Text.UTF8Encoding]::new($false)
)

promptledger eval record `
  --id onboarding `
  --ref prod `
  --file .\evaluation-result.json
```

### Evaluation commands

```bash
promptledger eval record --id onboarding --ref staging --file evaluation-result.json
promptledger eval list --id onboarding --ref staging --suite support-v1 --model test-model
promptledger eval show --run 12
promptledger eval compare --id onboarding --from prod --to staging --suite support-v1 --model test-model
promptledger eval export --id onboarding --format jsonl --out evaluations.jsonl
```

The file payload may contain `suite`, `model`, `dataset_hash`, `metrics`, and `metadata`. `--metrics` and `--file` are mutually exclusive; when `--file` is used, explicit `--suite`, `--model`, or `--dataset-hash` values override the corresponding file fields, while `--metadata` is rejected to avoid an ambiguous merge.

Evaluation lists and exports are ordered newest first by creation timestamp, using run ID as a stable tiebreaker. Comparison selects the newest baseline run matching the requested suite/model, then selects the newest candidate run with that exact suite and model. If no filters are supplied, the newest baseline determines the compatibility pair. Incompatible runs are never combined. Percentage delta is unavailable when the baseline is zero.

A gate policy is a JSON object:

```json
{
  "suite": "support-v1",
  "model": "test-model",
  "metrics": {
    "accuracy": {"direction": "higher", "max_regression": 0.02},
    "latency_ms": {"direction": "lower", "max_regression_percent": 15}
  }
}
```

```bash
promptledger eval gate --id onboarding --from prod --to staging --policy promptledger-gate.json
```

Gate exit code `0` means pass, `3` means a valid gate detected a regression, and `2` means invalid input, a malformed policy, or missing compatible evaluation data. Missing policy metrics fail the gate. A percentage threshold cannot permit a positive regression from a zero baseline; use an absolute threshold for that case.

Policy directions are `higher` and `lower`. Each metric rule must contain `max_regression`, `max_regression_percent`, or both; thresholds must be finite and non-negative. If both are present, the metric must satisfy both limits. Unexpected operational failures use exit code `1`.

Python exposes the same workflow through `record_evaluation`, `list_evaluations`, `get_evaluation`, `compare_evaluations`, `evaluate_gate`, and `export_evaluations`.

## Python API

```python
from promptledger import PromptLedger

ledger = PromptLedger()
ledger.init()

ledger.add("summary", "Summarize the document in 3 bullets.")
ledger.add("summary", "Summarize the document in 5 concise bullets.")

ledger.record_evaluation(
    prompt_id="summary",
    ref=1,
    suite="support-v1",
    model="test-model",
    metrics={"accuracy": 0.84, "latency_ms": 380},
)
ledger.record_evaluation(
    prompt_id="summary",
    ref=2,
    suite="support-v1",
    model="test-model",
    metrics={"accuracy": 0.87, "latency_ms": 410},
)

comparison = ledger.compare_evaluations(
    "summary", 1, 2, suite="support-v1", model="test-model"
)
print(comparison.metrics)
```

Refs may be integer versions, numeric strings, or labels. Evaluation runs always store the resolved concrete version.

## Core concepts

### Prompt metadata

Each prompt version can store:

* `reason`
* `author`
* `tags`
* `env` (`dev`, `staging`, `prod`)
* `collection` (free-form grouping such as `chunking-lab` or `support-bot`)
* `role` (`system`, `user`, `template`, `modelfile`, `eval`)
* `metrics` (legacy per-version metrics, still supported for backward compatibility)

Benchmark history belongs in dedicated evaluation runs rather than prompt-version `metrics`.

This turns raw text history into a lightweight audit trail.

### Faster iteration with `--quick`

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

### Lightweight prompt grouping

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

### Labels

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

### Markers

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

### Prompt reviews

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

#### Concise review output example

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

#### Markdown export example

```md
# Prompt Review: `onboarding`

## Compared refs

- From: `prod` -> `v7`
- To: `staging` -> `v9`
```

## Recommended release workflow

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

### 5. Evaluate

* `promptledger eval record --id <prompt_id> --ref <new> --file evaluation-result.json`
* `promptledger eval compare --id <prompt_id> --from <old> --to <new> --suite <suite>`
* Evaluation metrics are produced by external benchmark tools; PromptLedger stores and compares them.

### 6. Gate

* `promptledger eval gate --id <prompt_id> --from <old> --to <new> --policy promptledger-gate.json`
* The gate decides whether configured absolute and percentage regression limits are acceptable.

### 7. Promote with labels

* `promptledger label set --id <prompt_id> --version <new> --name <label>`
* Labels are moving release pointers; update `prod` or `staging` only after review and gating.

### 8. Annotate important versions with markers

* `promptledger stable --id <prompt_id> --version <new>` to mark a reliable baseline
* `promptledger milestone --id <prompt_id> --version <new>` to mark a turning point
* Markers are historical annotations, not release-routing pointers.

## Storage and security

### Newline normalization

* Line endings are normalized to LF for hashing and diffing.
* CRLF and LF content are treated as the same prompt content.
* Review summaries avoid fake changes caused only by line-ending differences.

### Storage location

* Inside a Git repository: `<repo_root>/.promptledger/promptledger.db`
* Outside Git: `<cwd>/.promptledger/promptledger.db`
* Environment override: `PROMPTLEDGER_HOME=/custom/path`
* Explicit override: `PromptLedger(db_path="/abs/path/to.db")`

### Export determinism

* CSV exports use a stable column order.
* JSONL exports use sorted keys.
* Evaluation JSONL exports use deterministic newest-first record ordering and sorted JSON keys.
* Repeated exports of the same data are byte-identical.
* Review markdown export is deterministic for the same input.

### Security

PromptLedger does not send prompt data anywhere.

Do not store API keys or secrets in prompt text. Use `--no-secret-warn` to suppress the CLI warning.

## Development

* Python >= 3.10
* Tests with pytest

```bash
pytest
```

## Legacy UI note

* `promptledger ui` still launches the old Streamlit viewer when `promptledger[ui]` is installed.
* The Streamlit viewer is deprecated in favor of `promptledger dashboard`.
