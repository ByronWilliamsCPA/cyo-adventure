# Multi-stage Dockerfile for CYO Adventure Frontend
# Based on FastAPI full-stack template best practices

# =============================================================================
# Stage 1: Dependencies
# =============================================================================
# Hardened Node image from the org GHCR mirror of Docker Hardened Images (DHI).
# Replaces node:22-alpine; Debian-based so apt-get applies, not apk.
# #CRITICAL external-resource: the plain dhi-node:22-debian13 runtime tag has
# no /bin/sh, so `RUN npm ci` fails at container init. The -dev tag mirrors
# Docker's actual builder variant (shell + npm); only this build-only stage
# needs it, the shipped image below still comes from dhi-nginx.
# #VERIFY the production stage never FROMs the -dev tag.
FROM ghcr.io/byronwilliamscpa/dhi-node:22-debian13-dev@sha256:4253663c9342a83ec8d24e4218ad3cade3acbc45627aa9b19b126b752595d492 AS deps

WORKDIR /app

# Copy package files
COPY package*.json ./

# --ignore-scripts is intentionally omitted: esbuild and other Vite native deps
# download platform-specific binaries via postinstall and will silently break
# without lifecycle scripts. Dependency integrity is enforced by the lockfile
# (npm ci) and Trivy scanning in container-security.yml.
RUN npm ci --only=production=false

# =============================================================================
# Stage 2: Builder
# =============================================================================
# Same -dev rationale as the deps stage above: `npm run build` needs a shell.
FROM ghcr.io/byronwilliamscpa/dhi-node:22-debian13-dev@sha256:4253663c9342a83ec8d24e4218ad3cade3acbc45627aa9b19b126b752595d492 AS builder

WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy source code
COPY . .

# Build arguments for environment configuration
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}

# Build the application
RUN npm run build

# An empty, shell-creatable directory used below to (re)establish ownership
# in the shell-less production stage via COPY --chown, since dhi-nginx has no
# RUN-capable shell to chown existing directories in place.
RUN mkdir -p /empty-owned

# =============================================================================
# Stage 3: Production (nginx)
# =============================================================================
# Hardened nginx image from the org GHCR mirror of Docker Hardened Images (DHI).
FROM ghcr.io/byronwilliamscpa/dhi-nginx:1.26-debian13@sha256:6b0137dc31dcff3c86854e3d9bbafb33201a6b0b83c44ecb0f4f6f092d68a7f4 AS production

# Metadata labels
LABEL org.opencontainers.image.title="CYO Adventure Frontend"
LABEL org.opencontainers.image.description="A choose-your-own-adventure reading app for kids"
LABEL org.opencontainers.image.authors="Byron Williams <byronawilliams@gmail.com>"

# #CRITICAL external-resource: dhi-nginx ships no shell and no package manager
# (verified: no /bin/sh, no curl/wget/busybox), so RUN-based user/package setup
# is impossible here, unlike the deps/builder stages above. The image already
# has a built-in non-root "nginx" user at uid/gid 65532; reuse it instead of
# groupadd/useradd, and set ownership via COPY --chown (a buildkit builtin
# that needs no shell) rather than a RUN chown.
# #VERIFY uid/gid 65532 stays stable across dhi-nginx version bumps; check
# with `docker run --entrypoint cat <image> /etc/passwd` before bumping the tag.

# Copy built assets from builder stage, owned by the built-in nginx user
COPY --from=builder --chown=65532:65532 /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY --chown=65532:65532 nginx.conf /etc/nginx/conf.d/default.conf

# Replace the cache/log/run directories with empty ones owned by uid 65532;
# there is no shell available here to chown the existing ones in place.
COPY --from=builder --chown=65532:65532 /empty-owned /var/cache/nginx
COPY --from=builder --chown=65532:65532 /empty-owned /var/log/nginx
COPY --from=builder --chown=65532:65532 /empty-owned /var/run

# Expose port 80
EXPOSE 80

# No in-container HEALTHCHECK: dhi-nginx ships no HTTP client and no shell, so
# a self-reported check isn't possible without reintroducing a shell into the
# shipped image, which would undo the point of using a hardened base here.
# Health is checked externally (curl against the published port from
# docker-host or Portainer).

# Run as the image's built-in non-root user (also the base image's own
# default, kept explicit here for clarity).
USER 65532:65532

# #ASSUME dhi-nginx's own ENTRYPOINT is already ["nginx"]; CMD supplies
# arguments only. A CMD repeating the binary name (e.g. ["nginx", "-g", ...])
# runs as `nginx nginx -g ...` and fails with "invalid option: nginx".
# #VERIFY `docker inspect <image> --format '{{json .Config.Entrypoint}}'`
# before changing this if the dhi-nginx tag is ever bumped.
CMD ["-g", "daemon off;"]

# =============================================================================
# Stage 4: Development (optional - for docker-compose dev)
# =============================================================================
# Same -dev rationale as the deps stage above: `npm ci` / `npm run dev` need a
# shell, and this stage runs interactively in docker-compose dev, not just at
# build time, so the shell also has to be there at container runtime.
FROM ghcr.io/byronwilliamscpa/dhi-node:22-debian13-dev@sha256:4253663c9342a83ec8d24e4218ad3cade3acbc45627aa9b19b126b752595d492 AS development

WORKDIR /app

# Copy package files
COPY package*.json ./

# Same --ignore-scripts rationale as the deps stage above.
RUN npm ci

# Copy source code (.dockerignore excludes node_modules, .env, dist, etc.)
COPY . .

# Ensure the node user owns /app so Vite can write its cache at runtime.
# npm ci runs as root above; without this chown USER node causes EACCES
# on cache directory creation under /app/node_modules/.vite.
RUN chown -R node:node /app

# Drop root before starting the dev server; the standard node image ships with
# a non-root "node" user (uid 1000) that the DHI image preserves.
USER node

# Expose Vite dev server port
EXPOSE 3000

# Start development server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
