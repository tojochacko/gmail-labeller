# Phase 1 – Backend Foundations

## Goals
- Stand up a FastAPI backend under `backend/app/` driving OAuth, email retrieval, label management, and agent run orchestration.
- Persist Gmail metadata and tokens in Supabase with encrypted storage.
- Expose typed endpoints that the Electron renderer can consume.
- Provide automated tests covering the Phase 1 surface.

## Deliverables
- **Configuration**: `backend/app/config.py` introduces a `Settings` model (pydantic-settings) with Supabase, Composio, Gmail, and runtime URLs; extra env vars are ignored so local secrets don’t break tests. `config/env.example` documents all expected keys.
- **App factory**: `backend/app/main.py` now exports `create_app`, registers CORS for localhost origins, mounts `/health`, and includes the `/api` router built in `backend/app/routes/__init__.py`.
- **Dependencies**: `backend/app/dependencies.py` wires singleton services (Supabase, Gmail toolkit, Email, Label, Agent) for FastAPI dependency injection.
- **Schemas**: Pydantic models live in `backend/app/schemas/` (`oauth.py`, `email.py`, `labels.py`, `agent.py`) and are exported via `__init__.py`.
- **Services**:
  - `gmail_toolkit.py`: wraps Composio Gmail toolkit via a protocol and factory, handles OAuth exchange, message listing, and label application.
  - `supabase_service.py`: CRUD for users, tokens, emails, agent runs with Fernet encryption of sensitive fields.
  - `email_service.py`, `label_service.py`, `agent_service.py`: orchestrate Gmail/Supabase interactions and agent runtime calls (using `httpx`).
- **Routes**: New FastAPI routers (`oauth.py`, `emails.py`, `labels.py`, `agent.py`) expose `/api/oauth/*`, `/api/emails`, `/api/labels`, `/api/runs`.
- **Testing**: `backend/tests/` hosts `conftest.py` with fake services plus `test_routes.py` covering all endpoints. Tests run with `pytest backend/tests -q`.
- **Dependencies added**: FastAPI, Uvicorn, Supabase client, httpx, cryptography, and pydantic-settings were added to `pyproject.toml`.

## Outstanding Setup
- Provision Supabase tables (`users`, `gmail_tokens`, `emails`, `agent_runs`, `label_configs`) with Row Level Security policies using the Supabase SQL editor or the REST/PostgREST API (see `docs/SUPABASE_API_MIGRATIONS.md`).
- Configure the agent runtime service to expose `/runs` endpoints expected by `AgentService`.
- Replace fake Composio interactions with real OAuth flow once credentials are available; extend integration tests accordingly.

## Verification
```bash
pytest backend/tests -q
```
- All six route tests pass using the fake service layer.
- No linting errors reported yet; add `ruff`/`mypy` checks when lint setup is in place.
