# Multi-stage Dockerfile for CYO Adventure Frontend
# Based on FastAPI full-stack template best practices

# =============================================================================
# Stage 1: Dependencies
# =============================================================================
# Hardened Node image from the org GHCR mirror of Docker Hardened Images (DHI).
# Replaces node:22-alpine; Debian-based so apt-get applies, not apk.
FROM ghcr.io/byronwilliamscpa/dhi-node:22-debian13 AS deps

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
FROM ghcr.io/byronwilliamscpa/dhi-node:22-debian13 AS builder

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

# =============================================================================
# Stage 3: Production (nginx)
# =============================================================================
# Hardened nginx image from the org GHCR mirror of Docker Hardened Images (DHI).
FROM ghcr.io/byronwilliamscpa/dhi-nginx:1.26-debian13 AS production

# Metadata labels
LABEL org.opencontainers.image.title="CYO Adventure Frontend"
LABEL org.opencontainers.image.description="A choose-your-own-adventure reading app for kids"
LABEL org.opencontainers.image.authors="Byron Williams <byronawilliams@gmail.com>"

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create non-root user for nginx
RUN addgroup -g 1001 -S appgroup && \
    adduser -u 1001 -S appuser -G appgroup && \
    chown -R appuser:appgroup /var/cache/nginx && \
    chown -R appuser:appgroup /var/log/nginx && \
    chown -R appuser:appgroup /etc/nginx/conf.d && \
    touch /var/run/nginx.pid && \
    chown -R appuser:appgroup /var/run/nginx.pid

# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost/health || exit 1

# Run as non-root user
USER appuser

CMD ["nginx", "-g", "daemon off;"]

# =============================================================================
# Stage 4: Development (optional - for docker-compose dev)
# =============================================================================
FROM ghcr.io/byronwilliamscpa/dhi-node:22-debian13 AS development

WORKDIR /app

# Copy package files
COPY package*.json ./

# Same --ignore-scripts rationale as the deps stage above.
RUN npm ci

# Copy source code (.dockerignore excludes node_modules, .env, dist, etc.)
COPY . .

# Drop root before starting the dev server; the standard node image ships with
# a non-root "node" user (uid 1000) that the DHI image preserves.
USER node

# Expose Vite dev server port
EXPOSE 3000

# Start development server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
