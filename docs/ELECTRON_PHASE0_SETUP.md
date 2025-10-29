# Phase 0 – Environment & Planning Notes

## Environment Prerequisites
- Node.js: `v24.10.0` (verified via `node -v`)
- pnpm: `10.20.0` (verified via `pnpm -v`)
- Python: `3.12.3` (verified via `python --version`)
- Supabase CLI: **not installed** (run `brew install supabase/tap/supabase` or use the official installer)
- Composio credentials: required `COMPOSIO_API_KEY` and Gmail toolkit configuration (obtain from Composio dashboard)
- OpenAI credentials for agent runtime: `OPENAI_API_KEY`

All contributors should install the Supabase CLI, authenticate with `supabase login`, and ensure Docker is available for local Supabase emulation if desired.

## Secrets & Configuration Strategy
- Copy `config/env.example` to `.env` (backend) and `.env.app` (Electron) as needed; never commit populated files.
- Store encryption key (`FERNET_SECRET_KEY`) in 1Password/Secrets Manager and inject at runtime.
- Electron runtime will read `ELECTRON_API_BASE_URL` (default `http://localhost:8000`) from its own `.env`.
- Update `.gitignore` to continue blocking `.env*` files; use `direnv` or `doppler` for local loading if desired.

## Supabase Schema Draft
- `users`: `id (uuid)`, `email`, `created_at`
- `gmail_tokens`: `id (uuid)`, `user_id (fk)`, `access_token`, `refresh_token`, `expires_at`, `scope`
- `emails`: `id (uuid)`, `user_id (fk)`, `gmail_message_id`, `thread_id`, `subject`, `snippet`, `received_at`, `processed_at`, `agent_suggestion`
- `label_configs`: `id (uuid)`, `user_id (fk)`, `label_name`, `description`, `gmail_label_id`
- `agent_runs`: `id (uuid)`, `user_id (fk)`, `email_id (fk)`, `status`, `result_payload`, `started_at`, `completed_at`, `error_message`

Row Level Security should be enabled with policies scoping rows to the authenticated user.

## CI & Tooling Alignment
- Backend: `ruff` for linting, `pytest`/`pytest-asyncio` for tests (target 80%+ coverage on new modules).
- Frontend: `eslint` + `prettier` (or `biome`), `vitest` + React Testing Library.
- End-to-end: Playwright smoke test hitting mocked backend.
- GitHub Actions workflow will run lint/test jobs and build Electron `.dmg` artifact via `electron-builder`.

## Tracking & Coordination
- Manage milestones manually (e.g., shared spreadsheet or local notes) aligned with the phase breakdown in `ELECTRONJS_IMPL_PLAN.md`.
- Record task ownership, estimates, and status updates in the chosen manual tracker.
- Use Git locally for commits; skip remote GitHub project boards or workflows for this iteration.

## Outstanding To-Dos
- [ ] Install Supabase CLI and authenticate.
- [ ] Populate Supabase project with the schema draft (SQL migration or Prisma).
- [ ] Provision secure storage for encryption keys (1Password/Secrets Manager).
- [ ] Set up the GitHub Projects board and invite collaborators.
