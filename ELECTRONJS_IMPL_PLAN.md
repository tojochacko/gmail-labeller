# Electron Desktop MVP Implementation Plan

## Architecture Snapshot
- **Desktop Shell**: Electron (main + renderer) packaged with `electron-builder` for macOS.
- **Frontend Stack**: Vite + React + TypeScript, minimal dependencies, shared type definitions across IPC.
- **Backend API**: FastAPI services under `backend/app`, persisting data to Supabase.
- **Email Integration**: Composio Gmail toolkit powering OAuth, email fetch, and label operations.
- **Secure Bridge**: Preload script exposes a narrow IPC contract for onboarding, email actions, and agent control.

## Phase 0 — Project Setup & Baseline (Day 0-1, ~3 pts)
- Confirm environment prerequisites (Node, Python, Supabase project, Composio credentials).
- Document secrets management (.env templates, encryption key storage).
- Align on Supabase schema draft and CI tooling decisions.
- Create tracking board (e.g., GitHub Projects) to map tasks to phases.

## Phase 1 — Backend Foundations (Day 1-4, ~13 pts)
- Finalize Pydantic schemas: `OAuthStartResponse`, `OAuthCallbackPayload`, `EmailItem`, `LabelRequest`, `AgentRunRequest/Status`.
- Implement Supabase service wrapper for `users`, `gmail_tokens`, `emails`, `agent_runs`, `label_configs`.
- Add token encryption helper (Fernet + env key) and integrate into Supabase writes.
- Build FastAPI endpoints:
  - `/api/oauth/start` and `/api/oauth/callback` using Composio Gmail toolkit.
  - `/api/emails` for fetching/caching Gmail messages.
- `/api/labels` for applying labels and logging status.
- `/api/runs` & `/api/runs/{id}` for agent orchestration/polling.
- Write pytest suites (async) with mocked Composio/Supabase responses, covering happy paths and error handling.

## Phase 2 — Electron Scaffold & OAuth Bridge (Day 3-6, ~10 pts)
- Bootstrap app with `npm create electron-vite@latest` (React + TS).
- Configure scripts: `dev`, `lint`, `test`, `build`, `dist`; add `electron-builder` settings for macOS.
- Implement preload script exposing IPC methods: `oauth.start`, `oauth.status`, `emails.fetch`, `labels.apply`, `runs.trigger`.
- Spin up local callback server (Fastify/Express) in main process, forwarding OAuth codes to backend.
- Persist onboarding status and tokens in `app.getPath("userData")` storage (tokens remain only in backend).
- Harden IPC (validate payloads, disable Node integration in renderer).

## Phase 3 — Renderer UX & Agent Workflows (Day 5-9, ~15 pts)
- Set up `react-router` (hash history) with routes: `Onboarding`, `Dashboard`, `Settings`.
- Onboarding screen: trigger Gmail connect, poll status, handle retry/error flows.
- Dashboard:
  - Display email list with subject/snippet, agent suggestions, and status chips.
  - Provide actions: “Apply Autogen Label”, “Re-run Agent”, manual refresh/auto-refresh toggle.
  - Poll `/api/runs/{id}` for live agent updates; show result banners or inline notes.
- Settings view: reconnect/revoke Gmail, display Supabase sync stats, adjust polling intervals.
- Implement shared React context for session/email state; add lightweight toast notifications.

## Phase 4 — Testing & Quality Gates (Day 8-11, ~11 pts)
- Frontend unit tests with Vitest + React Testing Library (onboarding, dashboard actions, IPC edge cases).
- IPC contract tests ensuring preload handlers validate payloads and error paths.
- Backend coverage review; add integration tests combining FastAPI endpoints with Supabase test instance (or heavy mocks).
- Add Playwright smoke tests launching dev app with stubbed backend endpoints to verify critical user journeys.
- Configure linting (`eslint`, `ruff`) and formatting checks in scripts and CI.

## Phase 5 — Packaging, CI, and Release Prep (Day 10-12, ~8 pts)
- Configure `.env` loading for Electron build and FastAPI deployment; document deployment steps.
- Add GitHub Actions workflow: backend lint/tests, frontend lint/tests, build macOS `.dmg` artifact.
- Prepare release notes template, notarization/signing placeholders, smoke-test checklist for packaged app.
- Run manual QA on packaged build, verify OAuth loop, email fetch, label action, and agent run updates.

## Phase 6 — Stabilization & Risk Mitigation (Ongoing, ~5 pts buffer)
- Monitor OAuth callback reliability; implement port retry and user guidance for failures.
- Audit Supabase RLS policies and ensure tokens never logged.
- Add exponential backoff/cache for Composio API calls to respect rate limits.
- Groom backlog for post-MVP improvements (Windows build, offline caching, richer analytics).

## Immediate Next Steps
1. Finalize Supabase schema/migrations and secret distribution strategy.
2. Implement Phase 1 backend endpoints with Composio integration plus unit tests.
3. Scaffold Electron app (Phase 2) and wire the local OAuth callback path before connecting UI flows.
