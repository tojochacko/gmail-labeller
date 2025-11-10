# Electron App in DevContainer - GUI Limitation

**Date**: 2025-11-03
**Status**: ⚠️ EXPECTED LIMITATION

---

## Issue Summary

When running `pnpm dev` in the electron-app directory, the following error occurs:

```
/workspaces/autogen-test/electron-app/node_modules/.pnpm/electron@39.0.0/node_modules/electron/dist/electron:
error while loading shared libraries: libglib-2.0.so.0: cannot open shared object file: No such file or directory
```

## Root Cause

The devcontainer is a **headless Linux environment** without:
- X11 display server
- GUI libraries (libglib, libgtk, libx11, etc.)
- Desktop environment

Electron is a desktop GUI application framework that requires these components to run.

---

## ✅ What Works

1. **TypeScript Compilation**: ✅ `npx tsc --noEmit` passes
2. **Linting**: ✅ `pnpm lint` passes
3. **Vite Build**: ✅ The Vite development server starts successfully
4. **Electron Binary**: ✅ Downloaded and installed correctly
5. **Backend API**: ✅ Can run independently

---

## 🔧 Solutions

### Option 1: Run Electron App on Host Machine (RECOMMENDED)

**Best for:** Local development with full GUI support

```bash
# On your host machine (not in devcontainer)
cd /path/to/autogen-test/electron-app
pnpm install
pnpm dev
```

**Backend runs in devcontainer, Electron runs on host:**
```bash
# Terminal 1 (devcontainer): Start backend
cd /workspaces/autogen-test
uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000

# Terminal 2 (host machine): Start Electron
cd /path/to/autogen-test/electron-app
pnpm dev
```

**Note**: Electron app will connect to `http://localhost:8000` (exposed from devcontainer)

---

### Option 2: Use X Virtual Frame Buffer (Xvfb) in DevContainer

**Best for:** Automated testing, CI/CD, headless screenshots

#### Install System Dependencies

Add to `.devcontainer/devcontainer.json`:
```json
{
  "postCreateCommand": "apt-get update && apt-get install -y xvfb libglib2.0-0 libgtk-3-0 libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 libxi6 libxtst6 libnss3 libcups2 libxss1 libxrandr2 libasound2 libpangocairo-1.0-0 libatk1.0-0 libatk-bridge2.0-0 libgtk-3-0"
}
```

#### Run with Xvfb

```bash
# Install xvfb (if not already in devcontainer)
sudo apt-get update
sudo apt-get install -y xvfb libglib2.0-0 libgtk-3-0 libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 libxi6 libxtst6 libnss3 libcups2 libxss1 libxrandr2 libasound2 libpangocairo-1.0-0 libatk1.0-0 libatk-bridge2.0-0

# Run Electron with virtual display
xvfb-run --auto-servernum pnpm dev
```

**Limitations**:
- No visible GUI (headless)
- Useful for automated testing only
- May have rendering/interaction issues

---

### Option 3: Use X11 Forwarding (Advanced)

**Best for:** Remote development with local display

#### On Host Machine

```bash
# macOS: Install XQuartz
brew install --cask xquartz
# Start XQuartz and enable "Allow connections from network clients"

# Linux: X11 already available
xhost +local:docker
```

#### Update DevContainer

Add to `.devcontainer/devcontainer.json`:
```json
{
  "runArgs": [
    "--env", "DISPLAY=${env:DISPLAY}",
    "--volume", "/tmp/.X11-unix:/tmp/.X11-unix:rw"
  ]
}
```

#### Run Electron

```bash
export DISPLAY=host.docker.internal:0  # macOS/Windows
# OR
export DISPLAY=:0                       # Linux

pnpm dev
```

**Limitations**:
- Requires X11 server on host
- May have performance issues over network
- Complex setup

---

### Option 4: Build and Test Electron App Separately (CURRENT APPROACH)

**Best for:** Current development workflow

1. **TypeScript/Linting** - Test in devcontainer:
   ```bash
   cd /workspaces/autogen-test/electron-app
   npx tsc --noEmit  # Verify types
   pnpm lint         # Check code quality
   pnpm test         # Run unit tests
   ```

2. **Backend Development** - Run in devcontainer:
   ```bash
   cd /workspaces/autogen-test
   uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000
   ```

3. **Electron GUI** - Run on host machine:
   ```bash
   # Outside devcontainer
   cd /path/to/autogen-test/electron-app
   pnpm dev
   ```

4. **Production Build** - Build in devcontainer (no GUI needed):
   ```bash
   cd /workspaces/autogen-test/electron-app
   pnpm build  # Creates distributable packages
   ```

---

## 📋 Current Status

### ✅ Completed Fixes

1. **Phase 1**: All TypeScript errors fixed
   - Electron package installed
   - Type definitions created
   - All implicit `any` types resolved
   - Compilation passes: `npx tsc --noEmit`
   - Linting passes: `pnpm lint`

2. **Phase 2**: Backend fully configured
   - Environment variables set
   - Mock agent service implemented
   - Database schema ready
   - Backend loads successfully

3. **Electron Binary**: Successfully downloaded
   - Manual install script execution worked
   - Binary located at: `node_modules/.pnpm/electron@39.0.0/node_modules/electron/dist/`

### ⚠️ Known Limitation

- **Electron GUI cannot run in headless devcontainer** (expected behavior)
- **Solution**: Run Electron on host machine or use Xvfb for headless testing

---

## 🚀 Recommended Workflow

### For Development

1. **Backend** (devcontainer):
   ```bash
   cd /workspaces/autogen-test
   uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000
   ```

2. **Electron App** (host machine):
   ```bash
   cd /path/to/autogen-test/electron-app
   pnpm install  # First time only
   pnpm dev
   ```

3. **Test Flow**:
   - Electron app connects to `http://localhost:8000`
   - Complete OAuth flow
   - Fetch emails
   - Apply labels
   - Trigger AI agent runs (mock mode)

### For CI/CD

```bash
# In CI environment (no GUI needed)
cd electron-app

# Type check
npx tsc --noEmit

# Lint
pnpm lint

# Test
pnpm test

# Build distributables
pnpm build

# Artifacts: electron-app/dist/
```

---

## 🔍 Troubleshooting

### Error: "libglib-2.0.so.0: cannot open shared object file"

**Expected**: This is the error we're seeing because the devcontainer lacks GUI libraries.

**Solutions**: See Options 1-4 above.

### Error: "Electron failed to install correctly"

**Fixed**: ✅ Ran manual install script: `node install.js`

**Prevention**: Add to `.npmrc`:
```
enable-pre-post-scripts=true
```

### Port 8000 not accessible from host

**Fix**: Ensure backend binds to `0.0.0.0` not `127.0.0.1`:
```bash
uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000
```

**Verify port forwarding** in VS Code:
- Ports panel should show `8000` forwarded
- Access via `http://localhost:8000`

---

## 📚 References

- [Electron in Docker/Containers](https://www.electronjs.org/docs/latest/tutorial/automated-testing#running-in-headless-ci-environments)
- [Xvfb for Headless Testing](https://github.com/electron/electron/blob/main/docs/tutorial/testing-on-headless-ci.md)
- [VS Code DevContainer X11 Forwarding](https://code.visualstudio.com/docs/devcontainers/containers#_forwarding-gui-applications)

---

**Last Updated**: 2025-11-03
**Status**: Documented - Use Option 1 (Run on Host) or Option 4 (Hybrid Approach)
