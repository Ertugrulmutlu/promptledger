
![](https://github.com/Ertugrulmutlu/promptledger/blob/main/assests/PromptLedger.png)
<p align="center">
  <img alt="CI" src="https://github.com/Ertugrulmutlu/promptledger/actions/workflows/ci.yml/badge.svg">
  <img alt="PyPI" src="https://img.shields.io/pypi/v/promptledger">
  <img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/promptledger">
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
</p>

# PromptLedger

PromptLedger is a local-first prompt version control system for developers.
It keeps a Git-style history of prompt changes in a single SQLite file, with a small CLI,
Python API, and a read-only Streamlit viewer.

## What it is

- A local prompt change ledger stored in SQLite
- Git-style history with multiple diff modes via `difflib`
- Metadata support: reason, author, tags, env, metrics
- Label support for release-style pointers plus label history audit trail
- CLI and Python API for add/get/list/diff/export workflows
- Read-only Streamlit UI with timeline, filtering, diff, and side-by-side comparison
- Newline normalization to avoid CRLF/LF noise

## What it is NOT

- An LLM framework
- An agent framework
- A SaaS or hosted service
- A prompt playground

## Why it exists

Prompt iteration is real code work, but most teams track it in scratch files or notebooks.
PromptLedger gives you reliable history, diffs, and metadata without standing up a service
or changing how you work.

Tested on Windows, macOS, and Linux via CI.

## Installation

```bash
pip install promptledger
pip install "promptledger[ui]"
```

- First command installs core CLI + Python API.
- Second command installs optional Streamlit UI support.

## Quickstart

### CLI Quickstart

```bash
promptledger init
promptledger add --id onboarding --text "Write a friendly onboarding email." --reason "Initial draft" --tags draft --env dev
promptledger add --id onboarding --file ./prompts/onboarding.txt --reason "Tone shift" --tags draft,marketing --env dev
promptledger list
promptledger list --id onboarding
promptledger show --id onboarding --version 2
promptledger diff --id onboarding --from 1 --to 2
promptledger diff --id onboarding --from prod --to staging
promptledger diff --id onboarding --from 1 --to 2 --mode context
promptledger diff --id onboarding --from 1 --to 2 --mode ndiff
promptledger diff --id onboarding --from 1 --to 2 --mode metadata
promptledger export --format jsonl --out prompt_history.jsonl
promptledger export --format csv --out prompt_history.csv
promptledger search --contains "friendly" --id onboarding --tag draft --env dev
promptledger label set --id onboarding --version 2 --name prod
promptledger label get --id onboarding --name prod
promptledger label list --id onboarding
promptledger label history --id onboarding
promptledger status
promptledger ui
```
Notes:
- `promptledger list` lists all prompt versions across all prompts.
- `promptledger list --id onboarding` lists versions of a single prompt.
- `promptledger search` exits 0 even with no matches and prints `0 results`.
- `promptledger ui` launches a read-only Streamlit UI.

### Python API Quickstart

```python
from promptledger import PromptLedger

ledger = PromptLedger()
ledger.init()
ledger.add(
    "summary",
    "Summarize the doc in 3 bullets.",
    tags=["draft"],
    env="dev",
    metrics={"accuracy": 0.92},
)
ledger.add(
    "summary",
    "Summarize the doc in 5 bullets.",
    tags=["draft"],
    env="dev",
    metrics={"accuracy": 0.94},
)
latest = ledger.get("summary")
print(latest.version, latest.content)
print(ledger.diff("summary", 1, 2))
print(ledger.diff_labels("summary", "prod", "staging"))
```

## Example Workflow

```bash
promptledger init
promptledger add --id demo --text "Hello"
promptledger add --id demo --text "Hello World"
promptledger diff --id demo --from 1 --to 2
```

## Metadata

Each prompt version can store:

- reason
- author
- tags
- env (`dev`, `staging`, `prod`)
- metrics (e.g. accuracy, latency, cost)

## Labels

Labels are human-readable pointers to specific prompt versions. Use them to track active releases (e.g. `prod`, `staging`, `latest`) without creating new versions. Every label change is recorded in an append-only label history log.

```bash
promptledger label set --id onboarding --version 7 --name prod
promptledger label set --id onboarding --version 9 --name staging
promptledger label get --id onboarding --name prod
promptledger label list --id onboarding
promptledger label history --id onboarding --name prod
promptledger status --id onboarding
```

## Newline Normalization

- Line endings are normalized to LF for hashing and diffs.
- Content with CRLF vs LF is treated as the same prompt.

## Storage

- Git repo present: `<repo_root>/.promptledger/promptledger.db`
- No git repo: `<cwd>/.promptledger/promptledger.db`
- Environment override: `PROMPTLEDGER_HOME=/custom/path` -> `/custom/path/promptledger.db`
- Explicit override: `PromptLedger(db_path="/abs/path/to.db")`

## Search

```bash
promptledger search --contains "error message"
promptledger search --contains "error message" --id onboarding --author "Ada" --tag draft --env dev
```

## Export Determinism

- CSV column order is stable.
- JSONL keys are sorted.
- Repeated exports of the same data produce identical files.

## Review Guide

Use this checklist to review prompt changes like code.

1) Identify scope
- `promptledger list --id <prompt_id>` to see recent versions.
- `promptledger label list --id <prompt_id>` to see active releases.

2) Review the change
- `promptledger diff --id <prompt_id> --from <old> --to <new>`
- Focus on intent, tone, structure, and constraints.

3) Verify metadata
- `promptledger show --id <prompt_id> --version <new>`
- Confirm `reason`, `author`, `tags`, `env`, `metrics` align with the change.

4) Validate safety
- Look for accidental secrets or credentials.
- Ensure sensitive data is not embedded in the prompt text.
5) Promote with labels
- `promptledger label set --id <prompt_id> --version <new> --name <label>`
- Update `prod`/`staging` labels only after review.

## Security

Do not store API keys or secrets in prompts. Use `--no-secret-warn` to suppress the CLI warning.

## Development

- Python >= 3.10
- Tests with pytest

```bash
pytest
```
