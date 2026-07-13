# Contributing to PromptLedger

Thank you for considering a contribution to PromptLedger.

PromptLedger is a local-first prompt version control and evaluation tool. Contributions that improve reliability, usability, documentation, testing, and cross-platform behavior are welcome.

## Before contributing

For substantial changes, please open an issue before starting implementation.

This helps confirm that the proposed change fits the scope and direction of the project.

Small bug fixes, documentation improvements, and additional tests may be submitted directly as pull requests.

## Project principles

Contributions should preserve the core principles of PromptLedger:

- Local-first operation
- No telemetry
- No required remote services
- Provider-independent evaluation storage
- Deterministic behavior and exports
- Backward-compatible database migrations
- Minimal required runtime dependencies
- Python 3.10 or newer
- Cross-platform support for Windows, macOS, and Linux

PromptLedger is not intended to become:

- An LLM provider SDK
- An agent framework
- A hosted SaaS platform
- An automatic benchmark runner
- An LLM-as-a-judge system

Features outside the current scope should be discussed in an issue first.

## Development setup

Clone the repository:

```bash
git clone https://github.com/Ertugrulmutlu/promptledger.git
cd promptledger
```

Create the development environment with `uv`:

```bash
uv sync --extra test
```

Run the test suite:

```bash
uv run pytest
```

You may also install the project in another Python environment:

```bash
python -m pip install -e ".[test]"
```

## Running PromptLedger locally

Initialize a PromptLedger database:

```bash
uv run promptledger init
```

Launch the local dashboard:

```bash
uv run promptledger dashboard
```

When testing manually, use a temporary directory or set `PROMPTLEDGER_HOME` so development data does not affect an existing PromptLedger database.

Bash:

```bash
export PROMPTLEDGER_HOME="$(pwd)/.promptledger-dev"
```

PowerShell:

```powershell
$env:PROMPTLEDGER_HOME = "$PWD\.promptledger-dev"
```

## Making changes

Please keep changes focused and avoid unrelated refactoring.

When adding or changing behavior:

- Add or update tests
- Preserve deterministic output
- Include safe database migrations when storage changes
- Keep CLI errors clear and avoid unnecessary tracebacks
- Maintain compatibility with Python 3.10
- Avoid unnecessary dependencies
- Update the README and changelog for user-facing changes

Evaluation logic should remain provider-independent.

PromptLedger stores externally produced evaluation results but does not execute model calls itself.

## Database migrations

Database changes must:

- Be non-destructive
- Preserve existing prompt versions, labels, markers, and evaluation runs
- Work for both new and existing databases
- Be covered by migration tests
- Remain safe when initialization is repeated

Do not rewrite existing migration history in a way that breaks previously created databases.

## Dashboard changes

The dashboard uses a small local Python HTTP server with static HTML, CSS, and JavaScript.

Please avoid adding a frontend framework or build system unless the change has been discussed first.

Dashboard contributions should include:

- Intentional loading, empty, and error states
- API tests where applicable
- JavaScript syntax validation
- Verification that static files are included in the built wheel
- Screenshots for visible interface changes

Prompt content should remain read-only in the dashboard unless a future project decision explicitly changes this boundary.

## Tests

Run the complete test suite before submitting a pull request:

```bash
uv run pytest
```

Check the diff for whitespace errors:

```bash
git diff --check
```

Changes involving package distribution should also verify the build:

```bash
uv build --no-sources
uvx twine check dist/*
```

## Pull requests

Please include:

- A clear summary of the change
- The reason for the change
- Tests added or updated
- Migration or compatibility considerations
- Screenshots for dashboard changes
- Documentation updates where necessary

Keep pull requests focused on one logical change when possible.

Do not include:

- PromptLedger databases
- Evaluation exports
- Build artifacts
- Cache directories
- API keys or credentials
- Local environment files
- Private or sensitive prompt content

## Reporting bugs

When reporting a bug, please include:

- PromptLedger version
- Python version
- Operating system
- Shell or terminal
- Command that was executed
- Actual output
- Expected behavior
- A minimal reproduction when possible

Remove prompts, credentials, personal data, and other sensitive information before sharing logs or database contents.

## Feature requests

Feature requests are welcome.

Please describe:

- The problem you are trying to solve
- Your proposed workflow
- Why the feature belongs in PromptLedger
- Possible alternatives or workarounds
- Any compatibility or migration concerns

## Security issues

Please do not report security vulnerabilities in a public issue.

Follow the instructions in `SECURITY.md` to report them privately.

## Code of Conduct

Participation in this project is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

By contributing to PromptLedger, you agree that your contributions will be licensed under the project’s MIT License.
