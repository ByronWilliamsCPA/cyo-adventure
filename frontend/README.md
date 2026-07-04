# CYO Adventure Frontend

React + TypeScript frontend for CYO Adventure.

## Tech Stack

- **React 19** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Vitest** - Testing framework
- **Axios** - HTTP client
- **ESLint + Prettier** - Code quality

## Quick Start

```bash
# Install dependencies
npm install

# Start development server (http://localhost:3000)
npm run dev

# Run tests
npm run test

# Build for production
npm run build
```

## Development

### Prerequisites

- Node.js 22+
- Backend API running on port 8000

### Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start dev server with HMR |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build |
| `npm run test` | Run tests in watch mode |
| `npm run test:run` | Run tests once |
| `npm run test:coverage` | Run tests with coverage |
| `npm run lint` | Lint code |
| `npm run lint:fix` | Fix lint issues |
| `npm run format` | Format code with Prettier |
| `npm run typecheck` | Run TypeScript type checking |
| `npm run generate-client` | Generate API client from OpenAPI |

### API Integration

The frontend connects to the backend API. In development, Vite proxies `/api` requests to `http://localhost:8000`.

#### Generate TypeScript API Client

Generate a type-safe API client from the FastAPI OpenAPI schema:

```bash
# Make sure backend is running first
cd .. && uv run uvicorn cyo_adventure.main:app &

# Generate client
npm run generate-client
```

This creates typed API functions in `src/client/`.

### Project Structure

```
frontend/
├── public/              # Static assets
├── src/
│   ├── assets/          # Images, fonts, etc.
│   ├── client/          # Auto-generated API client
│   ├── components/      # React components
│   ├── hooks/           # Custom React hooks
│   ├── test/            # Test setup and utilities
│   ├── App.tsx          # Root component
│   ├── App.css          # Root styles
│   ├── main.tsx         # Entry point
│   └── index.css        # Global styles
├── Dockerfile           # Production Docker image
├── nginx.conf           # Production nginx config
└── vite.config.ts       # Vite configuration
```

## Docker

### Development

```bash
# From project root
docker-compose up frontend
```

### Production

```bash
# Build production image
docker build -t cyo_adventure-frontend .

# Run with custom API URL
docker run -p 80:80 \
  --build-arg VITE_API_URL=https://api.example.com \
  cyo_adventure-frontend
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_URL` | Backend API URL | `http://localhost:8000` |
| `VITE_DEBUG` | Enable debug mode | `false` |

Create `.env.local` for local overrides (gitignored).

## Testing

```bash
# Run tests in watch mode
npm run test

# Run tests once with coverage
npm run test:coverage
```

Tests use Vitest with React Testing Library.

## Real-backend e2e (smoke tier)

Two e2e tiers exist: `chromium` (`e2e/`) mocks the API per test and needs no backend running;
`real-backend` (`e2e-real/`) makes zero mocks and requires the local stack below. Full design:
`docs/superpowers/specs/2026-07-04-playwright-e2e-suite-design.md`.

```bash
# 1. Postgres (default port 5432 is often taken; pick a free port, 5442+)
DB_PORT=5442 docker compose up -d db

# 2. Seed (schema + family + stories + admin + in-review story)
CYO_ADVENTURE_DATABASE_URL='postgresql+asyncpg://cyo_adventure:password@localhost:5442/cyo_adventure' \
  uv run python scripts/seed_dev_data.py

# 3. Backend (ENVIRONMENT defaults to local)
CYO_ADVENTURE_DATABASE_URL='postgresql+asyncpg://cyo_adventure:password@localhost:5442/cyo_adventure' \
  uv run uvicorn cyo_adventure.app:app --port 8000 &

# 4. Wait for readiness, then run the smoke tier
curl --retry 15 --retry-delay 2 --retry-all-errors -fsS http://localhost:8000/health/ready
cd frontend && npm run test:e2e:real
```

If 8000 or the chosen Postgres port are already taken, pick different ones and set
`E2E_BACKEND_URL` so `requireBackend()` checks the right host. Never set `VITE_API_URL` when
building for this tier: Vite bakes it into the client bundle at build time, so the browser
calls the backend directly and bypasses the same-origin preview proxy. For a non-default
backend port, build with `VITE_API_URL` unset, then run `vite preview` separately with
`VITE_API_URL` set only for that process; Playwright reuses the already-running preview server.

Reset between runs (the approve test mutates the database), then repeat steps 2 to 4:

```bash
docker compose down -v db
DB_PORT=5442 docker compose up -d db
```

`test:e2e:real` runs with `--workers=1`: the backend's per-IP rate limiter (100 rpm, burst 10)
trips when two workers share the loopback IP, producing spurious 429s.
