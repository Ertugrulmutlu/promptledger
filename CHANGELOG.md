# Changelog

All notable changes to PromptLedger are documented in this file.

This project follows Keep a Changelog and Semantic Versioning.

## [0.7.0] - 2026-07-13

### Added
- SQLite-backed evaluation runs attached to concrete prompt versions, with repeated runs and deterministic JSON serialization
- Python APIs for recording, listing, retrieving, comparing, gating, and exporting evaluation data
- `promptledger eval record`, `list`, `show`, `compare`, `gate`, and `export` commands
- JSON regression policies with higher/lower directions and absolute/percentage thresholds
- Read-only dashboard evaluation endpoints, version run history, and compatible metric deltas
- Dashboard evaluation status that distinguishes `EVALUATED` from `NO EVAL DATA` without inventing gate conclusions

### Changed
- SQLite schema version 6 adds the non-destructive `evaluation_runs` table and supporting indexes
- Dashboard prompt comparison now uses server-generated `difflib.SequenceMatcher` opcodes
- Dashboard documentation now accurately distinguishes read-only prompt content from writable local marker metadata

### Fixed
- Inserted or removed prompt lines no longer cause every subsequent dashboard line to appear changed
- Dashboard comparison normalizes CRLF and LF before computing line opcodes

## [0.6.0] - 2026-05-04

### Added
- Local workspace dashboard launched with `promptledger dashboard`
- Static HTML/CSS/JavaScript dashboard served by a small local Python HTTP API
- Prompt card workspace with search, metadata filters, draggable card ordering, and browser-local layout persistence
- Detail modal with latest prompt text, metadata badges, labels, markers, version timeline, and side-by-side compare
- Basic line-based visual diff in the dashboard compare view
- Dashboard card action menu with open, copy prompt, copy CLI command, and marker actions
- Local marker write API for dashboard actions:
  - `POST /api/prompts/{prompt_id}/versions/{version}/markers/{marker_name}`
  - `DELETE /api/prompts/{prompt_id}/versions/{version}/markers/{marker_name}`
- Dashboard marker toggles for `stable` and `milestone` using the existing PromptLedger marker system
- Read-only dashboard API endpoints for prompts, versions, search, and stats
- `--host`, `--port`, and `--no-open` options for the dashboard command
- Prompt metadata grouping with `collection` and built-in `role`
- Marker shortcuts: `promptledger stable` and `promptledger milestone`
- `promptledger add --quick` for reusing safe metadata from the latest prompt version

### Changed
- `promptledger ui` is now the legacy Streamlit viewer; `promptledger dashboard` is the primary local UI
- Dashboard package data is included in distributions so static assets ship with the wheel
- README now documents the workspace dashboard, local-only behavior, and browser-local layout state

### Fixed
- Dashboard marker filter results refresh after marker changes
- Dashboard handles empty prompt/search states intentionally
- Version timeline is scrollable for prompts with many versions

## [0.4.0] - 2026-04-16

### Added
- `promptledger add --quick` for reusing safe metadata from the latest prompt version
- Version markers with `stable` and `milestone` CLI commands and SQLite storage
- Prompt organization metadata through free-form `collection` and built-in `role` fields
- Collection and role filters across list, search, and the legacy UI

### Changed
- SQLite schema migrations add marker storage plus collection and role columns without replacing existing data
- Prompt list, show, review, and export surfaces include the new organization metadata

## [0.3.0] - 2026-03-28

### Added
- Local prompt review workflow with resolved label/version references
- Conservative semantic summaries, metadata changes, warnings, and review notes
- Deterministic Markdown review export

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
