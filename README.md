
![](https://github.com/Ertugrulmutlu/promptledger/blob/main/assests/PromptLedger.png)
<p align="center">
  <img alt="CI" src="https://github.com/Ertugrulmutlu/promptledger/actions/workflows/ci.yml/badge.svg">
  <img alt="PyPI" src="https://img.shields.io/pypi/v/promptledger">
  <img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/promptledger">
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
</p>

# PromptLedger

PromptLedger is a **local-first prompt version control system** for developers. It treats prompts like code: every change is versioned, diffable, and labeled — all stored locally in a single SQLite database.

It ships with a small CLI, a Python API, and a **read-only Streamlit viewer**. There are no backend services, no SaaS, and no telemetry.

---

## What it is

* A local prompt change ledger stored in SQLite
* Git-style history with multiple diff modes (`unified`, `context`, `ndiff`, `metadata`)
* Lightweight metadata support: `reason`, `author`, `tags`, `env`, `metrics`
* Human-readable labels (`prod`, `staging`, etc.) with **append-only label history**
* Deterministic exports (stable CSV / JSONL)
* CLI and Python API for add / list / diff / search / export workflows
* Read-only Streamlit UI with timeline, filtering, diff, and side-by-side comparison
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

---

## Quickstart

### CLI

```bash
promptledger init

promptledger add --id onboarding --text "Write a friendly onboarding email." \
  --reason "Initial draft" --tags draft --env dev

promptledger add --id onboarding --file ./prompts/onboarding.txt \
  --reason "Tone shift" --tags draft,marketing --env dev

promptledger list
promptledger list --id onboarding
promptledger show --id onboarding --version 2

promptledger diff --id onboarding --from 1 --to 2
promptledger diff --id onboarding --from prod --to staging
promptledger diff --id onboarding --from 1 --to 2 --mode context
promptledger diff --id onboarding --from 1 --to 2 --mode ndiff
promptledger diff --id onboarding --from 1 --to 2 --mode metadata

promptledger search --contains "friendly" --id onboarding --tag draft --env dev

promptledger label set --id onboarding --version 2 --name prod
promptledger label history --id onboarding

promptledger status
promptledger ui
```

Notes:

* `promptledger list` lists all prompt versions across all prompts.
* `promptledger search` exits with code `0` even when no results are found.
* The UI is **read-only by design**; all writes go through the CLI or API.

---

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
    metrics={"accuracy": 0.92},
)

ledger.add(
    "summary",
    "Summarize the document in 5 bullets.",
    tags=["draft"],
    env="dev",
    metrics={"accuracy": 0.94},
)

print(ledger.get("summary").version)
print(ledger.diff("summary", 1, 2))
```

---

## Labels

Labels are human-readable pointers to specific prompt versions (similar to movable git tags). They let you track active releases without duplicating prompt content.

Every label update is recorded in an **append-only label history log** for auditing and review.

```bash
promptledger label set --id onboarding --version 7 --name prod
promptledger label set --id onboarding --version 9 --name staging
promptledger label get --id onboarding --name prod
promptledger label list --id onboarding
promptledger label history --id onboarding
promptledger status --id onboarding
```

---

## Metadata

Each prompt version can store optional metadata:

* `reason` — why the prompt changed
* `author` — who made the change
* `tags` — arbitrary grouping labels
* `env` — `dev`, `staging`, `prod`
* `metrics` — JSON blob (accuracy, latency, cost, ratings, etc.)

This turns raw text history into a lightweight audit trail.

---

## Newline normalization

* Line endings are normalized to LF before hashing and diffing.
* Windows CRLF and Unix LF content are treated as identical.
* Diff output focuses on meaningful textual changes.

---

## Storage model

* Inside a git repository: `<repo_root>/.promptledger/promptledger.db`
* Outside git: `<cwd>/.promptledger/promptledger.db`
* Environment override: `PROMPTLEDGER_HOME=/custom/path`
* Explicit override: `PromptLedger(db_path="/abs/path/to.db")`

The database is **not committed to git by default**.

---

## Export determinism

* CSV exports have a fixed column order.
* JSONL exports use sorted keys.
* Repeated exports of the same data are byte-for-byte identical.

This makes PromptLedger suitable for reviews, audits, and downstream tooling.

---

## Review workflow

Use PromptLedger the same way you would review code changes.

1. Inspect history

* `promptledger list --id <prompt_id>`
* `promptledger label list --id <prompt_id>`

2. Review the change

* `promptledger diff --id <prompt_id> --from <old> --to <new>`

3. Verify metadata

* `promptledger show --id <prompt_id> --version <new>`

4. Promote

* `promptledger label set --id <prompt_id> --version <new> --name prod`

---

## Security

PromptLedger never sends data anywhere.

The CLI includes an advisory warning for common secret patterns (e.g. `sk-`, `AKIA`, `-----BEGIN`).
Use `--no-secret-warn` to suppress this warning.

---

## Development

* Python >= 3.10
* Tests with pytest

```bash
pytest
```

