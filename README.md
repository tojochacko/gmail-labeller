# Autogen Playground

Autogen Playground showcases several multi-agent workflows that you can run locally with
Python 3.12+. The repository ships a collection of command-line demos along with a FastAPI
backend for Gmail labeling workflows.

## Prerequisites

- Python 3.12 and [`uv`](https://docs.astral.sh/uv/) for dependency management
- OpenAI or Composio API credentials stored in a local `.env`

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

### Backend FastAPI server

Spin up the backend API that powers the Gmail labeler workflows:

```bash
uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000
```

The interactive OpenAPI docs are available at `http://localhost:8000/docs`.

## Intelligent Auto-Labeling Feature

The Gmail Labeler backend includes a complete AI-powered auto-labeling system that learns from your
behavior and automatically categorizes emails during the fetch process.

### Key Capabilities

**Pattern-Based Auto-Labeling**
- Automatically labels emails as "Important" or "Not Important" based on learned patterns
- Multi-factor scoring: Domain matching (50%), Keywords (30%), Subject patterns (20%)
- Configurable confidence threshold (default: 40%)
- Applies labels directly to Gmail and local database

**Accelerated Learning**
- Learns from manual labels you apply
- Re-mark detection: When you correct an auto-label, the system learns 2x faster
- Pattern weights increase from corrections (1.0x → 2.0x → up to 5.0x)
- Continuous improvement from user feedback

### API Integration

The auto-labeling system provides enhanced REST endpoints:

**GET `/api/emails`** - Fetch emails with statistics
```bash
# Filter by category
curl "http://localhost:8000/api/emails?user_id=UUID&category=important"
curl "http://localhost:8000/api/emails?user_id=UUID&category=not_important"
curl "http://localhost:8000/api/emails?user_id=UUID&category=uncategorized"

# Response includes statistics
{
  "items": [...],
  "stats": {
    "total": 10,
    "important": 3,
    "notImportant": 2,
    "uncategorized": 5,
    "autoLabeled": 3,
    "manualLabeled": 2
  }
}
```

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
uv run pytest backend/tests/test_routes.py -v
```

**Composio Adapter Tests** (`test_composio_adapter.py`):
```bash
uv run pytest backend/tests/test_composio_adapter.py -v
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

- Review `COMPOSIO_INTEGRATION_FIX.md` for Composio setup instructions
- Read `OAUTH_TEST_REPORT.md` for detailed test documentation
- See `CLAUDE.md` for project-specific development guidelines
