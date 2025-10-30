# Phase 2 – Electron Scaffold & OAuth Bridge

## Goals
- Create an Electron + Vite + React (+ TypeScript) workspace without relying on the Supabase CLI.
- Establish a secure preload bridge that exposes only the APIs required by the renderer.
- Implement IPC handlers in the main process that proxy requests to the FastAPI backend and launch the Gmail OAuth flow.
- Run a lightweight local HTTP server to capture the Gmail OAuth callback and notify the renderer when onboarding completes.

## Deliverables
- **Project scaffold**: `electron-app/` generated from the electron-vite React template, renamed to `gmail-labeler-electron` with pnpm tooling.
- **Environment**: `.env.example` documenting `VITE_API_BASE_URL`, `ELECTRON_API_BASE_URL`, and `OAUTH_CALLBACK_PORT`. The main process loads env vars via `dotenv`.
- **Shared typing**: `src/shared/ipc.ts` defines the contract used by both the preload layer and React views.
- **Preload API**: `electron/preload/index.ts` now exposes a typed `window.electronAPI` with namespaced methods (`oauth`, `emails`, `labels`, `runs`) plus an `onComplete` listener for OAuth events.
- **Main process**:
  - `electron/main/api-client.ts` centralises calls to the FastAPI backend.
  - `electron/main/oauth-server.ts` hosts the local callback server (`http://127.0.0.1:3005/oauth/callback`) and forwards results to the backend before emitting completion events.
  - `electron/main/index.ts` wires IPC handlers, ensures the OAuth server is running, transforms backend payloads into camelCase structures, and sanitises window opening behaviour.
- **Renderer placeholder**: `src/App.tsx` replaced with a simple message ahead of Phase 3 onboarding UI work.
- **Build validation**: `pnpm run test` (vitest + Vite build) passes in `electron-app/`.

## Usage Notes
- Set up a `.env` file alongside `.env.example` before running `pnpm dev` so the main process knows the backend URL.
- The preload bridge exposes only invoke-based methods; direct access to `ipcRenderer` is removed.
- OAuth completion events are delivered over the `oauth:complete` channel; the renderer will attach listeners in Phase 3.

## Next Steps
- Implement the onboarding view that kicks off `electronAPI.oauth.start`.
- Surface connection status, email lists, and agent controls using the new IPC methods.
- Add renderer-level tests (Vitest/RTL) around onboarding flows once UI exists.
