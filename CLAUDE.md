# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with Python code in this repository.

## Core Development Philosophy

### KISS (Keep It Simple, Stupid)

Simplicity should be a key goal in design. Choose straightforward solutions over complex ones whenever possible. Simple solutions are easier to understand, maintain, and debug.

### YAGNI (You Aren't Gonna Need It)

Avoid building functionality on speculation. Implement features only when they are needed, not when you anticipate they might be useful in the future.

### Design Principles

- **Dependency Inversion**: High-level modules should not depend on low-level modules. Both should depend on abstractions.
- **Open/Closed Principle**: Software entities should be open for extension but closed for modification.
- **Single Responsibility**: Each function, class, and module should have one clear purpose.
- **Fail Fast**: Check for potential errors early and raise exceptions immediately when issues occur.

## 🧱 Code Structure & Modularity

### File and Function Limits

- **Never create a file longer than 500 lines of code**. If approaching this limit, refactor by splitting into modules.
- **Functions should be under 50 lines** with a single, clear responsibility.
- **Classes should be under 100 lines** and represent a single concept or entity.
- **Organize code into clearly separated modules**, grouped by feature or responsibility.
- **Line lenght should be max 100 characters** ruff rule in pyproject.toml


## Project Overview

This is an Autogen playground for AI agent development using Microsoft's Autogen framework (v0.7.5+). The project demonstrates various multi-agent architectures including simple agents, customer support systems, group chats, and integration with external tools like Gmail via Composio. The developer would want to test various Agentic product ideas in this codebase before full-fledgedly committing to one.

### Project Structure

The project consists of two main components:

1. **Backend (FastAPI)** - Python-based API server (`/workspaces/autogen-test/backend/`)
   - FastAPI REST API for OAuth, email operations, and agent runs
   - Composio integration for Gmail operations
   - Supabase for data persistence
   - Runs in devcontainer on port 8000

### Key Applications

- **Command-line demos**: Autogen agent examples (main.py, customer-support.py, etc.)
- **Backend API**: FastAPI server for OAuth and Gmail operations

## Key Dependencies

### Backend (Python)
- **autogen-agentchat**, **autogen-core**, **autogen-ext**: Core framework for building AI agents
- **FastAPI**: Modern web framework for building APIs
- **OpenAI**: Primary LLM provider (gpt-4o, gpt-4o-mini)
- **Ollama**: Alternative local LLM support (configured for host.docker.internal:11436)
- **Composio**: External tool integration platform (Gmail operations via Composio 1.0 API)
- **Supabase**: PostgreSQL database for data persistence
- **Pydantic v2**: Data validation for message schemas and settings
- **Rich**: Console output formatting
- **Uvicorn**: ASGI server for FastAPI

## Environment Setup

### Development Container
The project uses a devcontainer with:
- Base image: `mcr.microsoft.com/devcontainers/base:ubuntu`
- Docker-outside-of-docker for container management
- Python with `uv` package manager

### UV Package Management

This project uses UV for blazing-fast Python package and environment management.

```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv

# Sync dependencies
uv sync

# Add a package ***NEVER UPDATE A DEPENDENCY DIRECTLY IN PYPROJECT.toml***
# ALWAYS USE UV ADD
uv add requests

# Add development dependency
uv add --dev pytest ruff mypy

# Remove a package
uv remove requests

# Run commands in the environment
uv run python script.py
uv run pytest
uv run ruff check .

# Install specific Python version
uv python install 3.12
```


### Initial Setup
```bash
# Install dependencies (automatically done in devcontainer via startup.sh)
pip install uv --break-system-packages
uv venv
uv sync
source .venv/bin/activate
```

### Development Commands

```bash
# Run all tests
uv run pytest

# Run specific tests with verbose output
uv run pytest tests/test_module.py -v

# Run tests with coverage
uv run pytest --cov=src --cov-report=html

# Format code
uv run ruff format .

# Check linting
uv run ruff check .

# Fix linting issues automatically
uv run ruff check --fix .

# Type checking
uv run mypy src/

# Run pre-commit hooks
uv run pre-commit run --all-files
```

### Running Examples

#### Autogen Agent Examples (DevContainer)
```bash
# Run the basic agent example
uv run python main.py

# Run customer support multi-agent system
uv run python customer-support.py

# Run group chat with multiple specialized agents
uv run python group-chat-example.py

# Run Gmail organizer (requires Composio setup)
uv run python gmail-organizer.py
```

#### Backend API Server (DevContainer)
```bash
# Start the FastAPI backend server
cd /workspaces/autogen-test
uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000

# Verify backend is running
curl http://localhost:8000/health
# Expected: {"status":"ok"}

# View API documentation
# Open http://localhost:8000/docs in browser
```

## 📋 Style & Conventions

### Python Style Guide

- **Follow PEP8** with these specific choices:
  - Line length: 100 characters (set by Ruff in pyproject.toml)
  - Use double quotes for strings
  - Use trailing commas in multi-line structures
- **Always use type hints** for function signatures and class attributes
- **Format with `ruff format`** (faster alternative to Black)
- **Use `pydantic` v2** for data validation and settings management

### Docstring Standards

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

### Naming Conventions

- **Variables and functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private attributes/methods**: `_leading_underscore`
- **Type aliases**: `PascalCase`
- **Enum values**: `UPPER_SNAKE_CASE`

## 🧪 Testing Strategy

### Test-Driven Development (TDD)

1. **Write the test first** - Define expected behavior before implementation
2. **Watch it fail** - Ensure the test actually tests something
3. **Write minimal code** - Just enough to make the test pass
4. **Refactor** - Improve code while keeping tests green
5. **Repeat** - One test at a time

### Testing Best Practices

```python
# Always use pytest fixtures for setup
import pytest
from datetime import datetime

@pytest.fixture
def sample_user():
    """Provide a sample user for testing."""
    return User(
        id=123,
        name="Test User",
        email="test@example.com",
        created_at=datetime.now()
    )

# Use descriptive test names
def test_user_can_update_email_when_valid(sample_user):
    """Test that users can update their email with valid input."""
    new_email = "newemail@example.com"
    sample_user.update_email(new_email)
    assert sample_user.email == new_email

# Test edge cases and error conditions
def test_user_update_email_fails_with_invalid_format(sample_user):
    """Test that invalid email formats are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        sample_user.update_email("not-an-email")
    assert "Invalid email format" in str(exc_info.value)
```

### Test Organization

- Unit tests: Test individual functions/methods in isolation
- Integration tests: Test component interactions
- End-to-end tests: Test complete user workflows
- Keep test files next to the code they test
- Use `conftest.py` for shared fixtures
- Aim for 80%+ code coverage, but focus on critical paths

## 🚨 Error Handling

### Exception Best Practices

```python
# Create custom exceptions for your domain
class PaymentError(Exception):
    """Base exception for payment-related errors."""
    pass

class InsufficientFundsError(PaymentError):
    """Raised when account has insufficient funds."""
    def __init__(self, required: Decimal, available: Decimal):
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient funds: required {required}, available {available}"
        )

# Use specific exception handling
try:
    process_payment(amount)
except InsufficientFundsError as e:
    logger.warning(f"Payment failed: {e}")
    return PaymentResult(success=False, reason="insufficient_funds")
except PaymentError as e:
    logger.error(f"Payment error: {e}")
    return PaymentResult(success=False, reason="payment_error")

# Use context managers for resource management
from contextlib import contextmanager

@contextmanager
def database_transaction():
    """Provide a transactional scope for database operations."""
    conn = get_connection()
    trans = conn.begin_transaction()
    try:
        yield conn
        trans.commit()
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()
```

### Logging Strategy

```python
import logging
from functools import wraps

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Log function entry/exit for debugging
def log_execution(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"Entering {func.__name__}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"Exiting {func.__name__} successfully")
            return result
        except Exception as e:
            logger.exception(f"Error in {func.__name__}: {e}")
            raise
    return wrapper
```

## 🏗️ Data Models and Validation

### Example Pydantic Models strict with pydantic v2

```python
from pydantic import BaseModel, Field, validator, EmailStr
from datetime import datetime
from typing import Optional, List
from decimal import Decimal

class ProductBase(BaseModel):
    """Base product model with common fields."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    price: Decimal = Field(..., gt=0, decimal_places=2)
    category: str
    tags: List[str] = []

    @validator('price')
    def validate_price(cls, v):
        if v > Decimal('1000000'):
            raise ValueError('Price cannot exceed 1,000,000')
        return v

    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }

class ProductCreate(ProductBase):
    """Model for creating new products."""
    pass

class ProductUpdate(BaseModel):
    """Model for updating products - all fields optional."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    category: Optional[str] = None
    tags: Optional[List[str]] = None

class Product(ProductBase):
    """Complete product model with database fields."""
    id: int
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

    class Config:
        from_attributes = True  # Enable ORM mode
```

## 🔄 Git Workflow

### Branch Strategy

- `main` - Production-ready code
- `develop` - Integration branch for features
- `feature/*` - New features
- `fix/*` - Bug fixes
- `docs/*` - Documentation updates
- `refactor/*` - Code refactoring
- `test/*` - Test additions or fixes

### Commit Message Format

Never include claude code, or written by claude code in commit messages

```
<type>(<scope>): <subject>

<body>

<footer>
``
Types: feat, fix, docs, style, refactor, test, chore

Example:
```

feat(auth): add two-factor authentication

- Implement TOTP generation and validation
- Add QR code generation for authenticator apps
- Update user model with 2FA fields

Closes #123

````

## 🗄️ Database Naming Standards

### Entity-Specific Primary Keys
All database tables use entity-specific primary keys for clarity and consistency:

```sql
-- ✅ STANDARDIZED: Entity-specific primary keys
sessions.session_id UUID PRIMARY KEY
leads.lead_id UUID PRIMARY KEY
messages.message_id UUID PRIMARY KEY
daily_metrics.daily_metric_id UUID PRIMARY KEY
agencies.agency_id UUID PRIMARY KEY
````

### Field Naming Conventions

```sql
-- Primary keys: {entity}_id
session_id, lead_id, message_id

-- Foreign keys: {referenced_entity}_id
session_id REFERENCES sessions(session_id)
agency_id REFERENCES agencies(agency_id)

-- Timestamps: {action}_at
created_at, updated_at, started_at, expires_at

-- Booleans: is_{state}
is_connected, is_active, is_qualified

-- Counts: {entity}_count
message_count, lead_count, notification_count

-- Durations: {property}_{unit}
duration_seconds, timeout_minutes
```

### Repository Pattern Auto-Derivation

The enhanced BaseRepository automatically derives table names and primary keys:

```python
# ✅ STANDARDIZED: Convention-based repositories
class LeadRepository(BaseRepository[Lead]):
    def __init__(self):
        super().__init__()  # Auto-derives "leads" and "lead_id"

class SessionRepository(BaseRepository[AvatarSession]):
    def __init__(self):
        super().__init__()  # Auto-derives "sessions" and "session_id"
```

**Benefits**:

- ✅ Self-documenting schema
- ✅ Clear foreign key relationships
- ✅ Eliminates repository method overrides
- ✅ Consistent with entity naming patterns

### Model-Database Alignment

Models mirror database fields exactly to eliminate field mapping complexity:

```python
# ✅ STANDARDIZED: Models mirror database exactly
class Lead(BaseModel):
    lead_id: UUID = Field(default_factory=uuid4)  # Matches database field
    session_id: UUID                               # Matches database field
    agency_id: str                                 # Matches database field
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(
        use_enum_values=True,
        populate_by_name=True,
        alias_generator=None  # Use exact field names
    )
```

### API Route Standards

```python
# ✅ STANDARDIZED: RESTful with consistent parameter naming
router = APIRouter(prefix="/api/v1/leads", tags=["leads"])

@router.get("/{lead_id}")           # GET /api/v1/leads/{lead_id}
@router.put("/{lead_id}")           # PUT /api/v1/leads/{lead_id}
@router.delete("/{lead_id}")        # DELETE /api/v1/leads/{lead_id}

# Sub-resources
@router.get("/{lead_id}/messages")  # GET /api/v1/leads/{lead_id}/messages
@router.get("/agency/{agency_id}")  # GET /api/v1/leads/agency/{agency_id}
```

For complete naming standards, see [NAMING_CONVENTIONS.md](./NAMING_CONVENTIONS.md).

## 📝 Documentation Standards

### Code Documentation

- Every module should have a docstring explaining its purpose
- Public functions must have complete docstrings
- Complex logic should have inline comments with `# Reason:` prefix
- Keep README.md updated with setup instructions and examples
- Maintain CHANGELOG.md for version history

### API Documentation

```python
from fastapi import APIRouter, HTTPException, status
from typing import List

router = APIRouter(prefix="/products", tags=["products"])

@router.get(
    "/",
    response_model=List[Product],
    summary="List all products",
    description="Retrieve a paginated list of all active products"
)
async def list_products(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None
) -> List[Product]:
    """
    Retrieve products with optional filtering.

    - **skip**: Number of products to skip (for pagination)
    - **limit**: Maximum number of products to return
    - **category**: Filter by product category
    """
    # Implementation here
```

## 🚀 Performance Considerations

### Optimization Guidelines

- Profile before optimizing - use `cProfile` or `py-spy`
- Use `lru_cache` for expensive computations
- Prefer generators for large datasets
- Use `asyncio` for I/O-bound operations
- Consider `multiprocessing` for CPU-bound tasks
- Cache database queries appropriately

### Example Optimization

```python
from functools import lru_cache
import asyncio
from typing import AsyncIterator

@lru_cache(maxsize=1000)
def expensive_calculation(n: int) -> int:
    """Cache results of expensive calculations."""
    # Complex computation here
    return result

async def process_large_dataset() -> AsyncIterator[dict]:
    """Process large dataset without loading all into memory."""
    async with aiofiles.open('large_file.json', mode='r') as f:
        async for line in f:
            data = json.loads(line)
            # Process and yield each item
            yield process_item(data)
```

## 🛡️ Security Best Practices

### Security Guidelines

- Never commit secrets - use environment variables
- Validate all user input with Pydantic
- Use parameterized queries for database operations
- Implement rate limiting for APIs
- Keep dependencies updated with `uv`
- Use HTTPS for all external communications
- Implement proper authentication and authorization

### Example Security Implementation

```python
from passlib.context import CryptContext
import secrets

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)
```

## 🔍 Debugging Tools

### Debugging Commands

```bash
# Interactive debugging with ipdb
uv add --dev ipdb
# Add breakpoint: import ipdb; ipdb.set_trace()

# Memory profiling
uv add --dev memory-profiler
uv run python -m memory_profiler script.py

# Line profiling
uv add --dev line-profiler
# Add @profile decorator to functions

# Debug with rich traceback
uv add --dev rich
# In code: from rich.traceback import install; install()
```

## 📊 Monitoring and Observability

### Structured Logging

```python
import structlog

logger = structlog.get_logger()

# Log with context
logger.info(
    "payment_processed",
    user_id=user.id,
    amount=amount,
    currency="USD",
    processing_time=processing_time
)
```

## 📚 Useful Resources

### Essential Tools

- UV Documentation: https://github.com/astral-sh/uv
- Ruff: https://github.com/astral-sh/ruff
- Pytest: https://docs.pytest.org/
- Pydantic: https://docs.pydantic.dev/
- FastAPI: https://fastapi.tiangolo.com/

### Python Best Practices

- PEP 8: https://pep8.org/
- PEP 484 (Type Hints): https://www.python.org/dev/peps/pep-0484/
- The Hitchhiker's Guide to Python: https://docs.python-guide.org/

## ⚠️ Important Notes

- **NEVER ASSUME OR GUESS** - When in doubt, ask for clarification
- **Always verify file paths and module names** before use
- **Keep CLAUDE.md updated** when adding new patterns or dependencies
- **Test your code** - No feature is complete without tests
- **Document your decisions** - Future developers (including yourself) will thank you

## 🔍 Search Command Requirements

**CRITICAL**: Always use `rg` (ripgrep) instead of traditional `grep` and `find` commands:

```bash
# ❌ Don't use grep
grep -r "pattern" .

# ✅ Use rg instead
rg "pattern"

# ❌ Don't use find with name
find . -name "*.py"

# ✅ Use rg with file filtering
rg --files | rg "\.py$"
# or
rg --files -g "*.py"
```

**Enforcement Rules:**

```
(
    r"^grep\b(?!.*\|)",
    "Use 'rg' (ripgrep) instead of 'grep' for better performance and features",
),
(
    r"^find\s+\S+\s+-name\b",
    "Use 'rg --files | rg pattern' or 'rg --files -g pattern' instead of 'find -name' for better performance",
),
```

## Architecture Patterns

### 1. RoutedAgent Pattern
All agents inherit from `RoutedAgent` and use `@message_handler` decorators to handle specific message types. Messages are routed through a `SingleThreadedAgentRuntime`.

### 2. Message-Based Communication
Agents communicate via typed Pydantic models:
- `UserTask`: Contains LLM message context
- `AgentResponse`: Contains reply context and routing info
- `GroupChatMessage`: Wraps user messages for group chats
- `RequestToSpeak`: Signals an agent to respond

### 3. Topic-Based Routing
Agents subscribe to topics using `TypeSubscription`. Messages are published to `TopicId` instances with a topic type and source (typically a session ID).

### 4. Tool Integration
- Direct tools: Executed by the agent itself (e.g., `execute_order_tool`)
- Delegate tools: Transfer control to another agent (e.g., `transfer_to_sales_agent_tool`)
- Tools are defined using `FunctionTool` wrapper around Python functions

## Key Files and Directories

### Autogen Agent Examples (Root Directory)

- **main.py**: Simple agent demonstration with message routing and multiple message types
- **customer-support.py**: Complex multi-agent customer service system with:
  - Triage agent (routes to appropriate specialist)
  - Sales agent (handles purchases)
  - Issues/Repairs agent (handles refunds)
  - Human agent (escalation path)
  - Demonstrates tool execution, delegation, and conversation flow

- **group-chat-example.py**: Collaborative multi-agent system with:
  - Group chat manager (selects next speaker using LLM)
  - Specialized agents (Writer, Editor, Illustrator)
  - Image generation with DALL-E integration
  - Rich console output for better UX

- **gmail-organizer.py**: Composio integration for Gmail automation

### Backend Directory (`/backend/`)

- **backend/app/main.py**: FastAPI application factory and route registration
- **backend/app/config.py**: Environment variables and application settings
- **backend/app/routes/**: API route handlers
  - `oauth.py`: OAuth start and callback endpoints
  - `emails.py`: Email fetching endpoints
  - `labels.py`: Label application endpoints
  - `agents.py`: Agent run triggering and status endpoints
- **backend/app/services/**: Business logic layer
  - `gmail_toolkit.py`: Composio Gmail adapter (Composio 1.0 API)
  - `agent_service.py`: AI agent integration (with mock mode)
  - `pii_redactor.py`: PII redaction via Microsoft Presidio — runs before every LLM call and before pattern storage
  - `pattern_learning_service.py`: Extracts domain/keyword patterns from labeled emails; keywords are subject-only, personal provider domains are skipped
  - `label_service.py`: Applies Gmail labels and triggers pattern learning; redacts subject PII before patterns are stored
  - `local_email_filter.py`: Rule-based pre-filter — skips LLM for sensitive/automated emails (bank statements, OTPs, transaction alerts)
  - `supabase_service.py`: Database operations
- **backend/app/schemas/**: Pydantic models for request/response validation
- **backend/tests/**: Comprehensive test suite (15/15 tests passing)
  - `test_composio_adapter.py`: Composio 1.0 integration tests
  - `test_routes.py`: OAuth workflow tests

### Database

- **database/supabase_schema.sql**: Complete database schema for Supabase
  - Tables: users, gmail_tokens, emails, agent_runs
  - Indexes, RLS policies, triggers

### Documentation

- **PHASE_2_COMPLETION_SUMMARY.md**: Backend integration and configuration
- **PROJECT_STATUS.md**: Current project status and testing instructions
- **COMPOSIO_INTEGRATION_FIX.md**: Composio 1.0 API migration guide
- **OAUTH_TEST_REPORT.md**: OAuth workflow test documentation
- All plan and summary documentation exists in the docs/ folder

## Environment Variables

### Backend Environment Variables (`.env`)

Required for the FastAPI backend:

```bash
# ============================================
# SUPABASE CONFIGURATION (Required)
# ============================================
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
SUPABASE_ANON_KEY=your_anon_key_here

# ============================================
# ENCRYPTION (Required)
# ============================================
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_SECRET_KEY=your_32_byte_base64_key_here

# ============================================
# GOOGLE OAUTH (Required for Gmail integration)
# ============================================
# Create at: https://console.cloud.google.com/apis/credentials
GOOGLE_OAUTH_CLIENT_ID=your_client_id_here.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret_here
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/oauth/callback
GOOGLE_OAUTH_SCOPE=https://www.googleapis.com/auth/gmail.modify

# ============================================
# COMPOSIO (Required for Gmail operations)
# ============================================
# Get from: https://app.composio.dev/
COMPOSIO_API_KEY=your_composio_key_here
COMPOSIO_ACCOUNT_ID=your_auth_config_id_here

# ============================================
# AI/AGENT CONFIGURATION
# ============================================
OPENAI_API_KEY=your_openai_key_here

# AGENT_RUNTIME_BASE_URL (Optional - uses mock mode if not set)
# AGENT_RUNTIME_BASE_URL=http://localhost:9000

# ============================================
# OPTIONAL SERVICES
# ============================================
# SENTRY_DSN=your_sentry_dsn_here
```

### Environment Setup

```bash
# Copy example env file
cp config/env.example config/.env

# Generate Fernet encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Copy output to FERNET_SECRET_KEY in config/.env

# Edit config/.env and fill in all required values
```

**Note**: The `config/.env` file contains API keys and should NEVER be committed to version control. It is already in `.gitignore`.

## Agent Lifecycle

1. Register agent types with runtime: `await MyAgent.register(runtime, "agent_type", factory_function)`
2. Add subscriptions: `await runtime.add_subscription(TypeSubscription(...))`
3. Start runtime: `runtime.start()`
4. Publish initial message: `await runtime.publish_message(...)`
5. Wait for completion: `await runtime.stop_when_idle()`
6. Clean up: `await runtime.close()` and `await model_client.close()`

## Current Project Status

### Completed Work

✅ **Backend Integration & Configuration** - COMPLETED
- Fernet encryption key generated
- Environment variables configured
- Supabase database schema created
- Mock mode implemented for AgentService
- Composio 1.0 API integration complete
- 15/15 tests passing

### Testing Status

**Backend Tests**: 62/62 passing ✅
- 14 Composio adapter tests
- 15 Local email filter tests
- 17 PII pattern guard tests
- 11 PII redactor tests
- 2 OAuth workflow tests
- 6 API route tests (includes label endpoint)

**Test Commands**:
```bash
# Run all backend tests (devcontainer)
cd /workspaces/autogen-test
uv run pytest backend/tests/ -v

# Run with coverage
uv run pytest backend/tests/ --cov=backend/app --cov-report=html

# Run specific test files
uv run pytest backend/tests/test_composio_adapter.py -v
uv run pytest backend/tests/test_pii_pattern_guard.py -v
uv run pytest backend/tests/test_local_email_filter.py -v
```

### Ready for End-to-End Testing

Before testing, you must complete these manual steps:

1. **Update Supabase Service Role Key** (Go to Supabase Dashboard → Settings → API)
2. **Execute Database Schema** (Run `database/supabase_schema.sql` in Supabase SQL Editor)
3. **Verify Google OAuth Redirect URI** (Ensure `http://localhost:8000/oauth/callback` is authorized)

See **PROJECT_STATUS.md** for detailed instructions.

## Development Notes

### Autogen Framework
- All agents run in a single-threaded runtime (no true concurrency)
- Session isolation is achieved via unique source IDs in TopicId
- LLM calls are async and support cancellation tokens
- Tool schemas are automatically generated from function signatures
- The framework supports both direct execution and agent delegation patterns

### Backend Architecture
- FastAPI with async/await patterns
- Dependency injection for services
- Composio 1.0 API for Gmail operations
- Mock mode for AgentService (returns hardcoded suggestions when AGENT_RUNTIME_BASE_URL not set)
- Supabase for PostgreSQL database
- Fernet encryption for OAuth tokens at rest

