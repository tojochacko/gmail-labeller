# Environment and Tools

## Development Environment

### System
- **Platform**: macOS (Darwin)
- **Python Version**: 3.12+
- **Package Manager**: UV (fast Python package manager)
- **File Encoding**: UTF-8

### Development Container
The project uses a devcontainer for consistent development:

```json
{
  "name": "AutoGen Testing devcontainer",
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
  "workspaceFolder": "/workspaces/autogen-test",
  "features": {
    "docker-outside-of-docker": "latest",
    "git": {},
    "python": {}
  }
}
```

### Post-Create Setup (startup.sh)
```bash
pip install uv --break-system-packages
uv sync
source .venv/bin/activate
```

## Required Tools

### UV (Package Manager)
- Fast, reliable Python package manager
- Replaces pip/pip-tools/virtualenv
- Installation: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Ruff (Linter & Formatter)
- Fast Python linter and formatter (Rust-based)
- Configured in pyproject.toml (line length: 100)
- Usage: `uv run ruff format .` or `uv run ruff check .`

### Ripgrep (rg)
- **CRITICAL**: Always use `rg` instead of `grep` or `find`
- Fast recursive search tool
- Available at: `/Users/tojochacko/.asdf/installs/nodejs/20.14.0/lib/node_modules/@anthropic-ai/claude-code/vendor/ripgrep/arm64-darwin/rg`

### Git
- Version control
- Branch strategy: main, develop, feature/*, fix/*, docs/*, refactor/*, test/*

## Optional Development Tools

### Testing (Not Yet Configured)
- **pytest**: Testing framework
- **coverage**: Code coverage tracking
- Add with: `uv add --dev pytest coverage`

### Type Checking (Not Yet Configured)
- **mypy**: Static type checker
- Add with: `uv add --dev mypy`

### Pre-commit Hooks (Not Yet Configured)
- **pre-commit**: Git hook framework
- Add with: `uv add --dev pre-commit`

### Debugging
- **ipdb**: Interactive debugger
- Add with: `uv add --dev ipdb`
- Usage: `import ipdb; ipdb.set_trace()`

## Environment Variables

Required in `.env` file:
```bash
OPENAI_API_KEY=<your-key>
COMPOSIO_API_KEY=<your-key>
```

**CRITICAL**: Never commit `.env` to version control

## VS Code Extensions (from devcontainer.json)
- ms-python.python
- ms-python.debugpy
- GitHub.copilot
- ms-dotnettools.csdevkit
- ms-dotnettools.vscodeintellicode-csharp
- github.vscode-github-actions

## Tool Configuration Status

### Configured
- ✅ UV package management
- ✅ Python 3.12+
- ✅ Basic project structure
- ✅ Development container
- ✅ Git

### Not Yet Configured
- ❌ Ruff configuration in pyproject.toml
- ❌ Pytest
- ❌ Mypy
- ❌ Pre-commit hooks
- ❌ Coverage reporting

## Ollama Configuration

For local LLM testing:
- **Host**: `host.docker.internal:11436` (from within container)
- **Model**: `deepseek-r1` (example)
- Requires Ollama server running locally