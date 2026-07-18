# Multi-stage Dockerfile for CYO Adventure
# Optimized for production with security best practices and minimal image size

# =============================================================================
# Stage 1: Builder - Install dependencies
# =============================================================================
# Tier A standard image for the build stage: has apt-get, /bin/sh, and
# build-essential. The DHI hardened image lacks a shell and cannot run RUN
# blocks, so we use python:3.12-slim-bookworm here and copy only the built
# artifacts into the hardened runtime stage below.
FROM python:3.14-slim-bookworm AS builder

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

# dhi-uv:0-debian13 ships a glibc 2.39-dynamically-linked binary; bookworm ships
# glibc 2.36, so copying from dhi-uv into this Debian 12 builder causes a symbol
# version error at runtime. astral-sh/uv ships a musl-statically-linked binary
# with no glibc dependency. Switch to dhi-uv once the builder moves to
# dhi-python:3.12-debian13-dev (Debian 13, tracked in container-images catalog PR).
# Renovate manages digest bumps via the ghcr.io/astral-sh/uv repository.
COPY --from=ghcr.io/astral-sh/uv:0.8.17@sha256:db99140470350437166de1fc646323ecb59e4d99d7857d0baf429a7b4a9523f3 /uv /usr/local/bin/uv

# #CRITICAL: external resources: the DHI runtime stage keeps its interpreter at
# /opt/python/bin and ships NO /usr/local/bin, so a venv created against this
# builder's /usr/local/bin/python3.12 arrives with a dangling python symlink
# and a stale pyvenv.cfg home; every console script (uvicorn, rq)
# then exec-fails at runtime with a misleading "no such file or directory"
# (first observed as the cyo-adventure-worker crash-loop on docker-host).
# Mirror the builder's interpreter at the runtime path and pin uv to it so the
# venv's symlink chain and pyvenv.cfg resolve identically in BOTH stages.
# #VERIFY: `docker run --rm <image> rq --version` (plus uvicorn
# --version) must succeed on the built image before publishing.
RUN mkdir -p /opt/python/bin && ln -s /usr/local/bin/python3.12 /opt/python/bin/python3.12
ENV UV_PYTHON=/opt/python/bin/python3.12

# Copy dependency files
# README.md is referenced by pyproject.toml via [project] readme; uv reads project
# metadata even on --no-install-project, so it must be present for both syncs.
# COPY README.md in its own layer so README edits do not invalidate the
# dependency-resolution cache; only pyproject.toml/uv.lock changes should.
COPY pyproject.toml uv.lock ./
COPY README.md ./

# Install dependencies to a virtual environment
# This creates .venv/ which we'll copy to the final stage.
# --extra api is REQUIRED: fastapi/uvicorn/sqlalchemy/asyncpg live in
# the [project.optional-dependencies] api extra, not main dependencies, so a
# plain --no-dev sync ships an image that cannot serve HTTP. Schema migrations
# are applied separately by the Supabase CLI (ADR-012), not from this image.
RUN uv sync --frozen --no-dev --no-install-project --extra api

# Copy application code
COPY . .

# Install the project itself
RUN uv sync --frozen --no-dev --extra api

# =============================================================================
# Stage 2: Runtime - Minimal hardened production image
# =============================================================================
# DHI hardened Python image: ~95% CVE reduction vs python:3.12-slim, ships 150
# CA certs, no shell. Mirror syncs weekly from dhi.io/python:3.12-debian13.
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

# Numeric UID/GID: equivalent non-root security without groupadd/useradd
# (DHI hardened images have no shell tools for user management).
USER 1000:1000

# Expose port (default for FastAPI/web apps)
EXPOSE 8000

# Health check - uses the Python stdlib (urllib) so the image does not need curl.
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live', timeout=2).status == 200 else 1)"]

# Default command - run web server. The application module is
# cyo_adventure.app (create_app() at import time); there is no main.py.
# --proxy-headers/--forwarded-allow-ips (Task E1, audit Group A: A1/A2): trust
# X-Forwarded-For/-Proto from this CIDR only, so RateLimitMiddleware keys on
# the real client (security.py) instead of the nginx/Traefik container's own
# IP, and SecurityHeadersMiddleware's HSTS branch (request.url.scheme ==
# "https") can fire behind the TLS-terminating reverse proxy.
# #CRITICAL: security: this hardcoded 172.16.0.0/12 default is the PRODUCTION
# fallback only, not a dev value: this repo's own docker-compose.yml pins its
# dev network to an exact /16 and overrides FORWARDED_ALLOW_IPS to that
# narrower subnet instead (see its own comment), so this broad /12 default
# is reached only when running this image directly or via
# docker-compose.prod.yml. It stays broad because the separate homelab-infra
# repo's production `cyo-adventure` stack's `backend-net` has no pinned
# subnet: Docker auto-assigns it from the 172.17.0.0-172.31.255.255 pool on
# each recreation, so no single narrower CIDR can be hardcoded here yet.
# Narrow this once backend-net is pinned; tracked in issue #138 (see
# core/config.py's forwarded_allow_ips docstring for the full rationale).
# This exec-form CMD is a hardcoded fallback, not the override point: the DHI
# hardened runtime image ships no shell (confirmed for this same image in the
# separate homelab-infra repo's own cyo-adventure-worker service, which needs
# the analogous compose-level override for the same reason), so it cannot
# itself expand ${FORWARDED_ALLOW_IPS:-172.16.0.0/12}. docker-compose.yml and
# docker-compose.prod.yml override the CIDR via their own compose-level
# `command:` with client-side ${FORWARDED_ALLOW_IPS:-...} substitution
# (resolved by the docker compose CLI before the container starts, needing no
# shell inside the image).
# #VERIFY: never set FORWARDED_ALLOW_IPS to "*" in any compose override or
# deployment env; that would let any upstream peer spoof its own client IP or
# scheme.
CMD ["uvicorn", "cyo_adventure.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=172.16.0.0/12"]
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
