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
uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000
```

**Important**: Use `0.0.0.0` (not `127.0.0.1`) so the backend is accessible from the host machine
where the Electron app runs.

The interactive OpenAPI docs are available at `http://localhost:8000/docs`. Keep this process
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

## Intelligent Auto-Labeling Feature

The Gmail Labeler includes a complete AI-powered auto-labeling system that learns from your
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

**Three-Category UI**
- ⭐ **Important** - Auto-labeled or manually marked as important
- 🗑️ **Not Important** - Auto-labeled or manually marked as not important
- ❓ **Uncategorized** - System couldn't confidently categorize (below threshold)

**Transparency & Control**
- Confidence badges show AI decision confidence (e.g., "65% confidence")
- Visual indicators distinguish auto-labels (blue) from manual labels (green)
- Easy re-marking with one-click correction buttons
- Real-time statistics on fetch results

### How It Works

1. **Initial Learning**: Manually label 5-10 emails to build initial pattern library
2. **Pattern Extraction**: System extracts domains, keywords, and subject patterns
3. **Auto-Labeling**: New emails are automatically categorized during fetch
4. **Continuous Improvement**: User corrections apply 2x weight to improve accuracy
5. **Steady State**: After 2-3 weeks, achieve 90-95% auto-labeling accuracy

### Quick Start

**Prerequisites**:
- Database migration completed (see `MIGRATION_EXECUTION_GUIDE.md`)
- Backend and frontend running

**15-Minute Test Flow**:

```bash
# 1. Start backend (in devcontainer)
uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000

# 2. Start frontend (on host machine)
cd electron-app && pnpm dev

# 3. In the Electron UI:
#    - Click "Fetch Emails"
#    - Manually label 5 emails (3 Important, 2 Not Important)
#    - Wait for new emails or send test emails
#    - Click "Fetch Emails" again
#    - See auto-labels with confidence badges!

# 4. Test re-mark learning:
#    - Find an auto-labeled email
#    - Click "Re-mark as [opposite label]"
#    - Check backend logs for "🚀 ACCELERATED LEARNING"
#    - Verify pattern weight doubled in database
```

### Database Migration

Before using auto-labeling, execute the schema migration:

```bash
# Open Supabase Dashboard → SQL Editor
# Run: database/migrations/002_consolidate_label_schema_v2.sql
# Execute sections 0-6 sequentially
# Verify success with provided queries
```

See `MIGRATION_EXECUTION_GUIDE.md` for step-by-step instructions with verification queries.

### Performance Expectations

| Week | Auto-Labeled | Manual | Time Investment |
|------|-------------|--------|-----------------|
| 1 (Learning) | 0-20% | 80-100% | 5-10 min/day |
| 2 (Adoption) | 40-50% | 50-60% | 2-3 min/day |
| 3+ (Maturity) | 80-90% | 10-20% | <1 min/day |
| Steady State | 90-95% | 5-10% | Minimal |

### Documentation

**Getting Started**:
- `COMPLETE_TESTING_GUIDE.md` - End-to-end testing (start here!)
- `MIGRATION_EXECUTION_GUIDE.md` - Safe database migration steps

**Feature Deep Dives**:
- `AUTO_LABEL_FULL_IMPLEMENTATION_SUMMARY.md` - Complete feature overview
- `REMARK_LEARNING_TEST_GUIDE.md` - How 2x learning works
- `PRIORITY_2_COMPLETION_SUMMARY.md` - Technical implementation details

**Planning & Status**:
- `AUTO_LABEL_IMPLEMENTATION_PLAN.md` - Original 9-phase plan
- `AUTO_LABEL_IMPLEMENTATION_STATUS.md` - Implementation progress
- `AUTO_LABEL_REMAINING_STEPS.md` - Task breakdown and priorities

### Monitoring & Debugging

**Backend Logs**: Watch for auto-labeling decisions
```bash
# Example log output
🆕 NEW EMAIL: Meeting tomorrow from boss@company.com
🤖 AUTO-LABELED: 'Important' (confidence: 0.652, matched: company.com)
📝 RE-MARK DETECTED: 'Important' → 'Not Important' (will apply 2x learning weight)
🚀 ACCELERATED LEARNING: Applying 2x weight for re-mark
```

**Database Queries**: Check pattern performance
```sql
-- View pattern statistics
SELECT pattern_type, pattern_value, label_type,
       pattern_weight, times_applied, times_corrected,
       confidence_score
FROM label_patterns
WHERE user_id = 'YOUR_USER_ID'
ORDER BY pattern_weight DESC, confidence_score DESC;

-- Auto-labeling statistics
SELECT label, label_source,
       COUNT(*) as count,
       AVG(label_confidence) as avg_confidence
FROM emails
WHERE label IS NOT NULL
GROUP BY label, label_source;
```

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

**For Auto-Labeling Feature**:
- Start with `COMPLETE_TESTING_GUIDE.md` for end-to-end testing (15 minutes)
- Follow `MIGRATION_EXECUTION_GUIDE.md` to execute database migration
- Review `AUTO_LABEL_FULL_IMPLEMENTATION_SUMMARY.md` for complete feature overview

**For Development**:
- Review the scenario-specific docs in `PRPs/` for deeper background
- Check `COMPOSIO_INTEGRATION_FIX.md` for Composio setup instructions
- Read `OAUTH_TEST_REPORT.md` for detailed test documentation
- See `CLAUDE.md` for project-specific development guidelines
