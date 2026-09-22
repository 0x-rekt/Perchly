FROM debian:bookworm-slim

# Install system dependencies (ca-certificates, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Enable bytecode compilation and use copy mode for uv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PYTHONUNBUFFERED=1

# Copy dependency definition files
COPY pyproject.toml uv.lock .python-version ./

# Install python and project dependencies
RUN uv sync --frozen --no-install-project

# Copy project files
COPY app ./app
COPY main.py ./main.py
COPY perchly.2026-09-12.private-key.pem* ./

# Finalize uv environment
RUN uv sync --frozen

# Create persistent data directory for SQLite
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
