# Multi-stage Dockerfile for CYO Adventure
# Optimized for production with security best practices and minimal image size

# =============================================================================
# Stage 1: Builder - Install dependencies
# =============================================================================
# Tier A (Docker Official) base for the build stage: needs apt-get and /bin/sh
# to install build-essential and run uv. The builder is discarded after the
# multi-stage copy; only the runtime stage is shipped and scanned.
FROM python:3.12-slim-bookworm AS builder

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

# Copy uv from the official Astral image. The astral-sh/uv image ships a
# musl-statically-linked binary so it runs on any libc version; dhi-uv:0-debian13
# requires GLIBC 2.38+ (Debian 13), which python:3.12-slim-bookworm does not have.
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
# Hardened runtime image from the org GHCR mirror (DHI, Tier S). ~95% CVE
# reduction vs python:3.12-slim. Shell-free: no /bin/sh, no apt-get, no
# groupadd. SHA pinned to the current weekly sync; update after each mirror
# refresh (every Sunday 02:00 UTC). CA certs are pre-installed in this image.
FROM ghcr.io/byronwilliamscpa/dhi-python:3.12-debian13@sha256:cf5aa76aaaa1466c57ca3ec494b83f8aefa1ddb1fcd6bf04b24a0bf34a270c70

# Metadata labels (OCI standard)
LABEL org.opencontainers.image.title="CYO Adventure"
LABEL org.opencontainers.image.description="A choose-your-own-adventure reading app for kids"
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.authors="Byron Williams <byronawilliams@gmail.com>"
LABEL org.opencontainers.image.url="https://github.com/williaby/cyo-adventure"
LABEL org.opencontainers.image.source="https://github.com/williaby/cyo-adventure"
LABEL org.opencontainers.image.licenses="MIT"

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=1000:1000 /app/.venv /app/.venv

# Copy application code
COPY --chown=1000:1000 . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src

# Run as non-root. DHI images have no shell so groupadd/useradd are unavailable;
# a numeric UID provides the same non-root security guarantee.
USER 1000:1000

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
