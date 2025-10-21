# Suggested Commands

## Package Management (UV)

### Installation & Setup
```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv

# Sync dependencies from pyproject.toml
uv sync

# Activate virtual environment
source .venv/bin/activate
```

### Dependency Management
```bash
# Add a package
uv add requests

# Add development dependency
uv add --dev pytest ruff mypy

# Remove a package
uv remove requests

# IMPORTANT: NEVER UPDATE DEPENDENCIES DIRECTLY IN pyproject.toml
# ALWAYS USE: uv add <package>
```

## Running Examples

```bash
# Run the basic agent example
python main.py

# Run customer support multi-agent system
python customer-support.py

# Run group chat with multiple specialized agents
python group-chat-example.py

# Run Gmail organizer (requires Composio setup)
python gmail-organizer.py

# Run with UV
uv run python main.py
```

## Development Tools

### Testing
```bash
# Run all tests (NOTE: No tests exist yet in this project)
uv run pytest

# Run specific tests with verbose output
uv run pytest tests/test_module.py -v

# Run tests with coverage
uv run pytest --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code with Ruff
uv run ruff format .

# Check linting
uv run ruff check .

# Fix linting issues automatically
uv run ruff check --fix .

# Type checking with mypy
uv run mypy src/

# NOTE: No pre-commit configuration exists yet
# If added: uv run pre-commit run --all-files
```

## Searching Code

**CRITICAL**: Always use `rg` (ripgrep) instead of grep/find:

```bash
# Search for pattern in all files
rg "pattern"

# Search with file type filtering
rg "pattern" -g "*.py"

# List Python files
rg --files -g "*.py"

# Search with context (3 lines before/after)
rg "pattern" -C 3

# Case-insensitive search
rg -i "pattern"
```

## Git Workflow

### Branch Strategy
- `main` - Production-ready code
- `develop` - Integration branch
- `feature/*` - New features
- `fix/*` - Bug fixes
- `docs/*` - Documentation
- `refactor/*` - Code refactoring
- `test/*` - Test additions

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: feat, fix, docs, style, refactor, test, chore

**IMPORTANT**: Never include "Claude Code" or "Generated with Claude Code" in commit messages

## Environment Setup

### Required Environment Variables
Create a `.env` file with:
```bash
OPENAI_API_KEY=<your-openai-api-key>
COMPOSIO_API_KEY=<your-composio-api-key>
```

**WARNING**: Never commit the `.env` file to version control

## System Commands (macOS/Darwin)

```bash
# List files
ls -la

# Change directory
cd /path/to/directory

# Search files (use rg instead)
rg --files -g "pattern"

# Search content (use rg instead)
rg "pattern"

# View file content
cat filename

# Interactive Python
ipython
```

## Debugging

```bash
# Interactive debugging with ipdb (if installed)
# Add to code: import ipdb; ipdb.set_trace()

# Run with rich traceback
# Add to code: from rich.traceback import install; install()

# View Python version
python --version
```