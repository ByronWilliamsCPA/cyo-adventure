# Multi-stage Dockerfile for CYO Adventure
# Optimized for production with security best practices and minimal image size

# =============================================================================
# Stage 1: Builder - Install dependencies
# =============================================================================
# Hardened base image from the org GHCR mirror of Docker Hardened Images (DHI).
# ~95% CVE reduction vs standard python:3.12-slim. Mirror syncs weekly from
# dhi.io/python:3.12-debian13. No login required; the image is public.
FROM ghcr.io/byronwilliamscpa/dhi-python:3.12-debian13 AS builder

# Set working directory
WORKDIR /app

# Install system dependencies for building Python packages.
# build-essential is required to compile C extensions during `uv sync`.
# Version pinning is intentionally omitted (DL3008): the build stage is discarded
# and never scanned, and Debian point releases retire exact apt versions quickly,
# which would otherwise break reproducible rebuilds.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install UV for fast dependency management
# hadolint ignore=DL3007
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
# README.md is referenced by pyproject.toml via [project] readme; uv reads project
# metadata even on --no-install-project, so it must be present for both syncs.
# COPY README.md in its own layer so README edits do not invalidate the
# dependency-resolution cache; only pyproject.toml/uv.lock changes should.
COPY pyproject.toml uv.lock ./
COPY README.md ./

# Install dependencies to a virtual environment
# This creates .venv/ which we'll copy to the final stage
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY . .

# Install the project itself
RUN uv sync --frozen --no-dev

# =============================================================================
# Stage 2: Runtime - Minimal production image
# =============================================================================
# Same hardened base as the builder stage (see note above).
FROM ghcr.io/byronwilliamscpa/dhi-python:3.12-debian13

# Metadata labels (OCI standard)
LABEL org.opencontainers.image.title="CYO Adventure"
LABEL org.opencontainers.image.description="A choose-your-own-adventure reading app for kids"
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.authors="Byron Williams <byronawilliams@gmail.com>"
LABEL org.opencontainers.image.url="https://github.com/williaby/cyo-adventure"
LABEL org.opencontainers.image.source="https://github.com/williaby/cyo-adventure"
LABEL org.opencontainers.image.licenses="MIT"

# Apply outstanding security patches from the Debian package index, then install
# only the minimal runtime dependencies. `apt-get upgrade` picks up fixes (e.g.
# openssl/libssl) that ship after the base image was built. `curl` is
# deliberately NOT installed: it and its transitive deps (libcurl, libssh2) carry
# unpatched CVEs, and the container healthcheck below uses Python's stdlib
# instead, so curl provides no value in the runtime image.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy application code
COPY --chown=appuser:appuser . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src

# Switch to non-root user
USER appuser

# Expose port (default for FastAPI/web apps)
EXPOSE 8000

# Health check - uses the Python stdlib (urllib) so the image does not need curl.
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live', timeout=2).status == 200 else 1)"]

# Default command - run web server
CMD ["uvicorn", "cyo_adventure.main:app", "--host", "0.0.0.0", "--port", "8000"]
# =============================================================================
# Build Arguments (optional, for build-time configuration)
# =============================================================================
# Example:
# ARG BUILD_ENV=production
# ENV ENVIRONMENT=${BUILD_ENV}

# =============================================================================
# Multi-architecture support
# =============================================================================
# Build for multiple platforms:
# docker buildx build --platform linux/amd64,linux/arm64 -t myimage:latest .
