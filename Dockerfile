FROM python:3.12-slim

WORKDIR /app

# Install system dependencies needed by presidio/spacy and uv build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv (pinned to match JobApplierAgent pattern)
COPY --from=ghcr.io/astral-sh/uv:0.11.0 /uv /usr/local/bin/uv

# Copy dependency files first for Docker layer cache efficiency
COPY pyproject.toml uv.lock ./

# Install all dependencies (including dev for pytest)
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY . .

# Ensure SQLite data directory exists
RUN mkdir -p /app/data

CMD ["sleep", "infinity"]
