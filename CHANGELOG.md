# Changelog

All notable changes to PromptLedger are documented in this file.

This project follows Keep a Changelog and Semantic Versioning.

## [0.2.0] - 2026-01-13

### Added
- Label history audit trail backed by `label_events` with schema migration
- Label history CLI (`promptledger label history`) and UI section
- Label-based and mixed diff resolution via versions or labels
- `status` command for a deterministic overview of prompts and labels
- Diff modes: unified, context, ndiff, and metadata-only
- Demo script for seeding local data (`demo.py`)

## [0.1.0] - 2026-01-03

### Added
- Local-first prompt version control backed by SQLite
- Git-aware initialization that updates `.gitignore` automatically
- Prompt versioning with hash-based no-op protection
- Unified diff generation via `difflib`
- Metadata fields: reason, author, tags, env, metrics
- Label system for release-style pointers (e.g., `prod`, `staging`)
- Search command with content and metadata filters
- Deterministic export to JSONL and CSV
- Secret detection warnings for common key formats
- Read-only Streamlit UI with timeline, filters, and diff view
- Cross-platform support (Windows, macOS, Linux)
- Comprehensive pytest test suite
