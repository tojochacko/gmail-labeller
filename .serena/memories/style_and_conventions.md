# Style and Conventions

## Core Principles

### KISS (Keep It Simple, Stupid)
- Choose straightforward solutions over complex ones
- Simple solutions are easier to understand, maintain, and debug

### YAGNI (You Aren't Gonna Need It)
- Implement features only when needed
- Don't build functionality on speculation

### Design Principles
- **Dependency Inversion**: High-level modules should not depend on low-level modules
- **Open/Closed Principle**: Open for extension, closed for modification
- **Single Responsibility**: Each function/class/module has one clear purpose
- **Fail Fast**: Check for errors early and raise exceptions immediately

## Code Structure Limits

- **Files**: Maximum 500 lines of code
- **Functions**: Under 50 lines with single responsibility
- **Classes**: Under 100 lines representing a single concept
- **Line length**: Maximum 100 characters
- Organize code into clearly separated modules by feature/responsibility

## Python Style Guide

### PEP8 Compliance
- Line length: 100 characters (enforced by Ruff)
- Use double quotes for strings
- Use trailing commas in multi-line structures
- **Always use type hints** for function signatures and class attributes

### Naming Conventions
- **Variables and functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private attributes/methods**: `_leading_underscore`
- **Type aliases**: `PascalCase`
- **Enum values**: `UPPER_SNAKE_CASE`

## Docstring Standards

Use Google-style docstrings for all public functions, classes, and modules:

```python
def calculate_discount(
    price: Decimal,
    discount_percent: float,
    min_amount: Decimal = Decimal("0.01")
) -> Decimal:
    """
    Calculate the discounted price for a product.

    Args:
        price: Original price of the product
        discount_percent: Discount percentage (0-100)
        min_amount: Minimum allowed final price

    Returns:
        Final price after applying discount

    Raises:
        ValueError: If discount_percent is not between 0 and 100
        ValueError: If final price would be below min_amount

    Example:
        >>> calculate_discount(Decimal("100"), 20)
        Decimal('80.00')
    """
```

## Pydantic v2 Usage

- Use Pydantic v2 for data validation and settings
- Prefer `pydantic.BaseModel` over `dataclasses` for data models
- Use validators and field constraints
- Use `model_config` for configuration

## Code Documentation

- Every module should have a docstring explaining its purpose
- Public functions must have complete docstrings
- Complex logic should have inline comments with `# Reason:` prefix
- Keep README.md and CLAUDE.md updated

## Important Notes

- **Never use emojis** unless explicitly requested
- **Never commit secrets** - use environment variables
- **Never assume or guess** - ask for clarification when in doubt
- **NEVER include "Claude Code" or "written by Claude Code"** in commit messages