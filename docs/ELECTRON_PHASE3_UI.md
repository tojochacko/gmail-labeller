# Phase 3 – Renderer Onboarding & Dashboard

## Goals
- Replace the placeholder renderer with a functional onboarding workflow that persists session info and drives the Gmail OAuth handshake through the preload bridge.
- Display connection status, token expiry, and basic email insights pulled from the FastAPI backend.
- Provide per-email actions (apply label, trigger agent run) and surface live feedback for each invocation.
- Add renderer-level tests that exercise the new flows under jsdom using Testing Library.

## Deliverables
- **UI & state**: `src/App.tsx` and `src/App.css` now implement the onboarding card, connection panel, email list, and status banners. Session persistence lives in `src/utils/sessionStorage.ts`.
- **IPC usage**: Renderer calls the typed APIs exposed in Phase 2 (`window.electronAPI.oauth/emails/labels/runs`) and interprets completion events to update the UI.
- **Email actions**: Each email row surfaces “Apply Autogen label” and “Trigger agent” buttons—hooked to backend endpoints via IPC—and displays inline results.
- **Testing**: Added jsdom + Testing Library setup (`test/setup.ts`) and scenario coverage in `test/app.spec.tsx` for onboarding, OAuth completion, email fetch, label apply, and agent run flows. Vitest config now targets jsdom.
- **Dependencies**: Introduced `@testing-library/react`, `@testing-library/jest-dom`, and `jsdom` to support the new tests; package script continues to run `pnpm run test`.

## Verification
```bash
cd electron-app
pnpm install
pnpm run dev        # launch renderer + preload for manual UX checks
pnpm run test       # builds + vitest (includes Testing Library specs)
```

## Next Steps
- Style refinements (light/dark polish, typography) to align with eventual production design.
- Wire up deeper agent status polling and expose Composio insights once backend delivers richer payloads.
- Add renderer coverage for error scenarios (OAuth denial, backend failures) to ensure messaging stays actionable.
