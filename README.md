# Autogen Playground

Autogen Playground showcases several multi-agent workflows that you can run locally with
Python 3.12+. The repository ships a collection of command-line demos along with an optional
Electron UI for the Gmail labeler scenario.

## Prerequisites

- Python 3.12 and [`uv`](https://docs.astral.sh/uv/) for dependency management
- OpenAI or Composio API credentials stored in a local `.env`
- (Optional) Node.js 18+ and [`pnpm`](https://pnpm.io/) for the Electron preview

## Environment Setup

```bash
uv venv && uv sync
# Reason: start from the backend template and fill in your secrets
cp config/env.example .env
```

Populate `.env` with keys such as `OPENAI_API_KEY` and `COMPOSIO_API_KEY` before launching any
agents.

Activate the virtual environment when you are not using `uv run` directly:

```bash
source .venv/bin/activate
```

## Preview The App

### Command-line agent demos

Run the baseline single-threaded flow:

```bash
uv run python main.py
```

Other multi-agent examples live at the repository root:

- `uv run python customer-support.py`
- `uv run python group-chat-example.py`
- `uv run python gmail-organizer.py`

Each script prints progress to the terminal so you can observe the message routing between
agents. Stop the preview with `Ctrl+C`.

### Backend FastAPI server (on DevContainer)

Spin up the backend API that powers the Gmail labeler workflows:

```bash
uv run uvicorn backend.app.main:create_app --reload --host 127.0.0.1 --port 8000
```

The interactive OpenAPI docs are available at `http://127.0.0.1:8000/docs`. Keep this process
running while you exercise the Electron UI or any API clients pointed at `ELECTRON_API_BASE_URL`.

### Electron Gmail labeler UI (on Host machine)

The `electron-app/` directory contains a desktop preview for the Gmail labeler agent. Launch it
from a second terminal:

```bash
cd electron-app
pnpm install
pnpm dev
```

Sometimes electron package can have installation issues due to the use of pnpm. To circumspect the issue, run the following commands:

```bash
cd node_modules/.pnpm/electron@39.0.0/node_modules/electron && node install.js
```

The renderer development server starts at `http://127.0.0.1:7777/`, and Electron opens a desktop
window pointing at it.

## Testing

The project includes comprehensive test coverage for the OAuth workflow and Composio integration.

### Running Tests

Run all tests:
```bash
uv run pytest backend/tests/ -v
```

Run tests with coverage:
```bash
uv run pytest backend/tests/ --cov=backend/app --cov-report=html
```

### Test Suites

**OAuth Workflow Tests** (`test_routes.py`):
```bash
# Test OAuth start endpoint
uv run pytest backend/tests/test_routes.py::test_oauth_start_returns_authorization_url -v

# Test OAuth callback endpoint
uv run pytest backend/tests/test_routes.py::test_oauth_callback_stores_tokens -v

# Run all route tests
uv run pytest backend/tests/test_routes.py -v
```

**Composio Adapter Tests** (`test_composio_adapter.py`):
```bash
# Test Composio 1.0 integration
uv run pytest backend/tests/test_composio_adapter.py -v

# Test specific adapter functionality
uv run pytest backend/tests/test_composio_adapter.py::test_get_authorization_url -v
uv run pytest backend/tests/test_composio_adapter.py::test_list_messages -v
uv run pytest backend/tests/test_composio_adapter.py::test_apply_label -v
```

### What's Tested

✅ **OAuth Flow** (2 tests)
- Authorization URL generation
- Token exchange and storage

✅ **Composio Integration** (9 tests)
- Composio 1.0 API compliance
- Gmail message fetching
- Label application
- Token management
- Error handling

✅ **API Routes** (4 tests)
- Health checks
- Email operations
- Agent execution

### Test Reports

Detailed test documentation is available in:
- `OAUTH_TEST_REPORT.md` - Comprehensive test breakdown and validation
- `COMPOSIO_INTEGRATION_FIX.md` - Integration guide and setup instructions

### Continuous Testing

Watch mode for development (install pytest-watch first):
```bash
uv add --dev pytest-watch
uv run ptw backend/tests/
```

## Code Quality

Run linting and formatting:
```bash
# Format code
uv run ruff format .

# Check for linting issues
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .
```

Run type checking:
```bash
uv run mypy backend/
```

## Next Steps

- Review the scenario-specific docs in `PRPs/` for deeper background
- Check `COMPOSIO_INTEGRATION_FIX.md` for Composio setup instructions
- Read `OAUTH_TEST_REPORT.md` for detailed test documentation
