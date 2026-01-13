# PromptLedger: Local-first prompt version control (technical dev.to draft)

This post is a technical deep dive into PromptLedger. The goal is simple: treat prompts like code by storing every change in a single SQLite database, expose a small CLI and Python API, and provide a read-only UI for inspection and diffs.

## Architecture overview

The project is intentionally small and split by responsibility:

- `src/promptledger/cli.py`: CLI parsing and IO for `init/add/list/show/diff/export/search/label/ui`.
- `src/promptledger/core.py`: `PromptLedger` domain logic and query composition.
- `src/promptledger/db.py`: SQLite connection, schema creation, and migrations.
- `src/promptledger/ui.py`: Streamlit-based read-only viewer.

## Storage layout and resolution

Default database resolution is deterministic and local:

- If a git repo is found: `<repo_root>/.promptledger/promptledger.db`
- Otherwise: `<cwd>/.promptledger/promptledger.db`
- Override with `PROMPTLEDGER_HOME=/custom/path` (db becomes `/custom/path/promptledger.db`)
- Explicit override: `PromptLedger(db_path="/abs/path/to.db")`

That keeps data local and easy to back up, and avoids any server dependency.

## Schema (SQLite)

PromptLedger uses a compact schema with a versioned prompt table and a labels table:

```sql
CREATE TABLE IF NOT EXISTS prompt_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  reason TEXT,
  author TEXT,
  tags TEXT,
  env TEXT,
  metrics TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(prompt_id, version)
);

CREATE TABLE IF NOT EXISTS labels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_id TEXT NOT NULL,
  label TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(prompt_id, label)
);
```

Indexes exist on `prompt_versions(prompt_id)` and `prompt_versions(env)` for faster list and filter operations.

## Versioning algorithm

When you call `add`, PromptLedger:

1) Normalizes newlines to LF (see below).
2) Hashes the content (SHA-256) for change detection.
3) Reads the latest version for the same `prompt_id`.
4) If the hash matches, it does not create a new version.
5) Otherwise it increments `version` and inserts a new row with metadata.

This keeps history clean and avoids noise from formatting-only changes.

## Newline normalization

Prompt text can come from Windows CRLF or Unix LF. PromptLedger normalizes line endings before hashing and storing, so identical content is not duplicated across platforms. This also improves diff readability by removing CRLF/LF churn.

## Metadata model

Each prompt version can store:

- `reason`: why the change was made
- `author`: who authored the change
- `tags`: stored as JSON array string (for simple filtering)
- `env`: `dev`, `staging`, `prod`, etc.
- `metrics`: JSON blob for accuracy/latency/cost

This makes the data model richer than raw text diffs and supports audit-like workflows.

## Labels as release pointers

Labels are stable pointers to a specific version. Think of them like `prod`, `staging`, or `latest` tags. The label table enforces uniqueness per `(prompt_id, label)` and uses `INSERT ... ON CONFLICT ... DO UPDATE` to move pointers atomically.

## CLI behavior

Core commands and their purpose:

- `promptledger init`: create the db, schema, and `.gitignore` entry.
- `promptledger add`: add or skip a new version depending on hash.
- `promptledger list`: list all prompt versions, optionally by id.
- `promptledger show`: show full metadata and content for a version.
- `promptledger diff`: unified diff between two versions.
- `promptledger search`: content search with optional filters.
- `promptledger export`: JSONL or CSV output with deterministic ordering.
- `promptledger label set/get/list`: manage release pointers.
- `promptledger ui`: Streamlit viewer.

The CLI prints a short row-per-version format (id, version, created_at, env, tags, reason) to make it easy to pipe or grep.

## General workflow (technical)

A typical end-to-end workflow looks like this:

1) Initialize the local ledger.
2) Add prompt versions with metadata and tags.
3) Inspect diffs and metadata for review.
4) Optionally label a known-good version (for prod/staging).
5) Export history for offline review or audit.
6) Use the UI for read-only browsing and comparison.

### 1) Initialize

`promptledger init` creates the SQLite database, applies schema migrations, and writes a `.gitignore` entry for the `.promptledger/` directory when inside a git repo.

```bash
promptledger init
```

### 2) Add versions

Add prompt content via `--text` or `--file`. The add path normalizes newlines, hashes content, checks the latest version, and inserts only if the hash differs.

```bash
promptledger add --id support_reply --text "Draft a concise reply." --reason "first pass" --tags support --env dev
promptledger add --id support_reply --file .\prompts\support_reply.txt --reason "refine tone" --tags support --env dev
```

### 3) Review and diff

Use `list`, `show`, and `diff` to review history. `diff` uses unified diff semantics, so it is easy to scan in code review workflows.

```bash
promptledger list --id support_reply
promptledger show --id support_reply --version 2
promptledger diff --id support_reply --from 1 --to 2
```

### 4) Label a release

Labels act as stable pointers. You can move them without creating a new version.

```bash
promptledger label set --id support_reply --version 2 --name prod
promptledger label get --id support_reply --name prod
```

### 5) Export

Export to JSONL or CSV for offline review, dashboards, or audit trails. Output is deterministic to keep diffs stable in version control.

```bash
promptledger export --format jsonl --out prompt_history.jsonl
promptledger export --format csv --out prompt_history.csv
```

### 6) UI browsing

The Streamlit UI provides a read-only inspection layer with filters and side-by-side comparison.

```bash
promptledger ui
```

## Search and export

Search is a basic content filter over stored prompt text with optional metadata filters (`--id`, `--author`, `--tag`, `--env`). Export is deterministic:

- JSONL keys are sorted.
- CSV columns have a stable order.

This means repeated exports of the same dataset produce identical diffs, which is important for version-controlled artifacts.

## Streamlit UI

The UI is intentionally read-only:

- Loads all records and labels into memory.
- Offers timeline view and filters (prompt id, tags, env).
- Renders selected version metadata and content.
- Provides diff and side-by-side comparison for two versions.

The UI does not mutate data, so the CLI remains the single write path.

## Security note

PromptLedger includes a basic secret-warning check when adding content. It is intentionally conservative and can be disabled with `--no-secret-warn`. The recommendation remains: do not store API keys or secrets in prompts.

## What it is not

PromptLedger is not an LLM framework, a hosted service, or a prompt playground. It is a local version ledger for prompt text and metadata.

## Quickstart (technical)

```bash
promptledger init
promptledger add --id onboarding --text "Write a friendly onboarding email." --reason "Initial draft" --tags draft --env dev
promptledger add --id onboarding --file .\prompts\onboarding.txt --reason "Tone shift" --tags draft,marketing --env dev
promptledger list --id onboarding
promptledger show --id onboarding --version 2
promptledger diff --id onboarding --from 1 --to 2
promptledger label set --id onboarding --version 2 --name prod
promptledger ui
```

## Closing thoughts

If your team treats prompts as production artifacts, PromptLedger provides a clean, local, and inspectable history with minimal surface area. It is small by design, with predictable storage and traceable diffs.
