# Repository Guidelines

## Project Structure & Module Organization
The repo is a Python 3.12+ Autogen playground running inside a Docker devcontainer; all container configuration lives in `.devcontainer/`. Top-level scripts like `main.py`, `customer-support.py`, `group-chat-example.py`, and `gmail-organizer.py` demonstrate different multi-agent flows. Secrets go in `.env` (never commit), and dependency metadata is in `pyproject.toml` with the `uv.lock` lockfile. Planning notes reside in `PRPs/`. There is no `tests/` directory yet—add one at the root when introducing automated checks.

## Build, Test, and Development Commands
Use `uv` for environment management:
```bash
uv venv && uv sync          # bootstrap the virtual environment
source .venv/bin/activate   # activate when not using uv run
uv run python main.py       # launch the basic agent demo
uv run python customer-support.py  # multi-agent support flow
```
Quality gates:
```bash
uv run ruff format .        # apply formatting
uv run ruff check .         # lint for style and bugs
uv run mypy src/            # type-check if you add a src package
uv run pytest               # execute tests once they exist
```

## Coding Style & Naming Conventions
Follow PEP 8 with a 100-character line limit. Prefer double quotes, `snake_case` for functions and variables, `PascalCase` for classes, and `_leading_underscore` for private helpers. Every public function and module needs a Google-style docstring and explicit type hints. Keep files under 500 LOC and functions under 50 lines; refactor aggressively to preserve single responsibility. Use inline comments sparingly with a `# Reason:` prefix when logic is non-obvious.

## Testing Guidelines
Adopt `pytest` when adding tests and store them under `tests/` mirroring the module structure. Name test files `test_<feature>.py` and test functions `test_<behavior>`. Target meaningful coverage for new features; ensure agents that call external APIs are covered with fakes or fixtures. Run `uv run pytest --cov` before opening pull requests.

## Commit & Pull Request Guidelines
Commits follow `<type>(<scope>): <subject>` with lowercase conventional types (`feat`, `fix`, `docs`, `test`, `chore`, etc.). Keep bodies focused on why the change matters and link issues in the footer when available. Pull requests should explain the agent scenario, list validation runs (`uv run pytest`, demos), and attach terminal snippets or screenshots for interactive flows. Use feature branches (`feature/*`, `fix/*`, `docs/*`) and rebase before merging.

## Environment & Security Notes
Store `OPENAI_API_KEY` and `COMPOSIO_API_KEY` in `.env`; load them via `python-dotenv` or your shell, but never check them into git. When searching or auditing the codebase, prefer `rg` for speed (`rg "TopicId"`). Keep local models or Ollama endpoints off by default unless documentation specifies a need.
