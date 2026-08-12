FROM python:3.10-slim

WORKDIR /app

# curl is needed for the HEALTHCHECK below (not in the slim base image)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user early so we can own /app
RUN useradd --create-home appuser && chown appuser:appuser /app

# Install uv (fast Python package manager)
RUN pip install uv

# Copy dependency files first (Docker layer caching)
COPY --chown=appuser:appuser pyproject.toml .
COPY --chown=appuser:appuser uv.lock* .

# uv_build needs src/production_api/__init__.py, and pyproject.toml's
# readme = "README.md" field means it also needs README.md present,
# to install the project itself. Copy both now, before the heavy
# dependency install, so this layer only invalidates when they change.
COPY --chown=appuser:appuser src/ src/
COPY --chown=appuser:appuser README.md .

# Switch to non-root user before installing deps (so .venv is owned by appuser)
USER appuser

# Install dependencies (production only)
RUN uv sync --frozen --no-dev

# Copy application code
COPY --chown=appuser:appuser app/ app/

# Copy the chat frontend (served by StaticFiles at "/")
COPY --chown=appuser:appuser static/ static/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run uvicorn directly from venv (avoids uv re-syncing at runtime)
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]