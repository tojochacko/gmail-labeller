# Task Completion Checklist

When completing a development task in this project, follow these steps:

## 1. Code Quality Checks

### Formatting
```bash
# Format code with Ruff
uv run ruff format .
```

### Linting
```bash
# Check for linting issues
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .
```

### Type Checking
```bash
# Run mypy for type checking (if configured)
uv run mypy src/
```

## 2. Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html
```

**NOTE**: Currently, no tests exist in this project. When implementing new features, consider adding tests following TDD principles.

## 3. Documentation

- [ ] Update docstrings for new/modified functions and classes
- [ ] Use Google-style docstrings
- [ ] Add type hints to all function signatures
- [ ] Update CLAUDE.md if new patterns/conventions are introduced
- [ ] Update README.md if user-facing changes occur

## 4. Code Structure Validation

- [ ] No file exceeds 500 lines
- [ ] No function exceeds 50 lines
- [ ] No class exceeds 100 lines
- [ ] Line length does not exceed 100 characters
- [ ] Each function/class has a single responsibility

## 5. Security & Best Practices

- [ ] No secrets committed to version control
- [ ] All user input validated with Pydantic
- [ ] Environment variables used for configuration
- [ ] Proper error handling implemented
- [ ] Logging added for debugging

## 6. Git Workflow

```bash
# Check status
git status

# Stage changes
git add .

# Commit with proper message format
git commit -m "feat(scope): description"

# NEVER include "Claude Code" or "Generated with Claude Code" in commits
```

## 7. Manual Testing

- [ ] Run the affected entry point (main.py, customer-support.py, etc.)
- [ ] Verify expected behavior
- [ ] Test edge cases
- [ ] Check console output is clear and informative

## Common Commands Summary

```bash
# Complete quality check workflow
uv run ruff format .
uv run ruff check --fix .
uv run mypy src/  # if configured

# Run the application
python main.py  # or other entry point

# Verify environment
source .venv/bin/activate
```

## TDD Workflow (Recommended)

1. **Write test first** - Define expected behavior
2. **Watch it fail** - Ensure test is valid
3. **Write minimal code** - Make test pass
4. **Refactor** - Improve while keeping tests green
5. **Repeat** - One test at a time

## Before Creating PR

- [ ] All checks above completed
- [ ] Code reviewed locally
- [ ] Commit messages follow convention
- [ ] Branch follows naming convention (feature/*, fix/*, etc.)