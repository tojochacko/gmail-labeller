# Phase 4 – Testing & Quality Gates

## Goals
- Establish consistent linting and formatting checks for the Electron workspace.
- Strengthen automated coverage across IPC flows (unit + component + Playwright smoke tests).
- Document the command surface so contributors can run quality gates locally.

## Deliverables
- **ESLint (flat config)**: `electron-app/eslint.config.js` targets key sources (`src/App.tsx`, `src/utils`, `electron/main`, `electron/preload`, and tests) with React/TypeScript/jsx-a11y rules. Legacy template areas (`src/demos`, update modal) are ignored until refactored.
- **Lint script**: `pnpm run lint` now enforces zero warnings and was validated to pass after addressing TypeScript typing issues in `electron/main/index.ts`.
- **Testing stack**: Existing Vitest + Testing Library scenarios were expanded (`test/app.spec.tsx`) to cover label application and agent run triggers. Playwright smoke tests (`test/e2e.spec.ts`) now assert the onboarding UI rather than template counters.
- **Python linting**: `pyproject.toml` exposes optional `dev` dependencies (pytest, ruff, etc.) and ships a baseline Ruff configuration (`[tool.ruff]`) for backend quality checks.

## Commands
Run from the project root (Electron commands executed inside `electron-app/`):

```bash
# Frontend/Electron
cd electron-app
pnpm install
pnpm run lint
pnpm run test

# Backend (optional dev setup)
uv pip install -e .[dev]
uv run ruff check backend/app backend/tests
uv run pytest backend/tests -q
```

## Notes
- ESLint currently ignores template demo/update files; once those components are replaced, remove the ignores to expand coverage.
- Playwright tests still skip automatically on Linux (as per template) due to sandbox constraints. Enable by removing the guard when CI runners support Electron.
- Ruff is configured but not yet integrated into CI—Phase 5 will add automation.
