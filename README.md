# CYO Adventure

## Quality & Security
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13575/badge)](https://www.bestpractices.dev/projects/13575)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/ByronWilliamsCPA/cyo-adventure/badge)](https://securityscorecards.dev/viewer/?uri=github.com/ByronWilliamsCPA/cyo-adventure)
[![codecov](https://codecov.io/gh/ByronWilliamsCPA/cyo-adventure/graph/badge.svg)](https://codecov.io/gh/ByronWilliamsCPA/cyo-adventure)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=ByronWilliamsCPA_cyo-adventure&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=ByronWilliamsCPA_cyo-adventure)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=ByronWilliamsCPA_cyo-adventure&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=ByronWilliamsCPA_cyo-adventure)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=ByronWilliamsCPA_cyo-adventure&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=ByronWilliamsCPA_cyo-adventure)
[![REUSE Compliance](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/reuse.yml/badge.svg)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/reuse.yml)
[![Dependency Review](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/dependency-review.yml/badge.svg)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/dependency-review.yml)
[![Container Security](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/container-security.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/container-security.yml?query=branch%3Amain)

## CI/CD Status
[![CI Pipeline](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/ci.yml?query=branch%3Amain)
[![Python Compatibility](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/python-compatibility.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/python-compatibility.yml?query=branch%3Amain)
[![Security Analysis](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/security-analysis.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/security-analysis.yml?query=branch%3Amain)
[![Documentation](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/docs.yml?query=branch%3Amain)
[![ClusterFuzzLite](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/cifuzzy.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/cifuzzy.yml?query=branch%3Amain)
[![SBOM & Security Scan](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/sbom.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/sbom.yml?query=branch%3Amain)
[![PR Validation](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/pr-validation.yml/badge.svg)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/pr-validation.yml)
[![Release](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/release.yml/badge.svg)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/release.yml)
[![PyPI Publish](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/workflows/publish-pypi.yml)

## Project Info

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://conventionalcommits.org)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](https://github.com/ByronWilliamsCPA/.github/blob/main/CODE_OF_CONDUCT.md)

| | |
|---|---|
| **Author** | Byron Williams |
| **Created** | 2026-06-20 |
| **Repository** | [ByronWilliamsCPA/cyo-adventure](https://github.com/ByronWilliamsCPA/cyo-adventure) |

---

## Overview

A choose-your-own-adventure reading app for kids. A guardian requests a story for a
child's profile; a staged LLM pipeline generates it; the story must pass a deterministic
validation gate and moderation review before a guardian approves and publishes it; only
then can the child read it, online or offline.

This is a full-stack application: a FastAPI backend (`src/cyo_adventure/`) and a React
19 + TypeScript + Vite frontend (`frontend/`) in the same repository, communicating over
a generated, type-safe OpenAPI contract.

## Features

- **Human-gated story generation**: staged LLM pipeline (`generation/`) with pluggable
  providers (Anthropic, OpenRouter, Ollama, Modal) behind a deterministic two-layer
  validation gate (`validator/`) and moderation review (`moderation/`); nothing reaches a
  child reader without automated validation and guardian approval and publish
  (`publishing/`)
- **AI cover art**: generated, stored, and optimized per story (`covers/`)
- **Offline-capable reader**: IndexedDB-backed offline reading and sync
  (`frontend/src/offline/`) with a client-side player engine that mirrors the backend's
  reading-state logic
- **Append-only event log**: every pipeline stage is recorded for auditability (`events/`)
- **High Quality**: 80%+ test coverage enforced via CI
- **Type Safe**: Full type hints with BasedPyright strict mode
- **Developer Friendly**: Pre-commit hooks, automated formatting, linting
- **Security First**: Dependency scanning, security analysis, SBOM generation

## Quick Start

### Prerequisites

- Python 3.11+ (CI matrix covers 3.11, 3.12, and 3.13; 3.12 is the primary local/CI target)
- [UV](https://docs.astral.sh/uv/) for dependency management
- PostgreSQL and Redis (for running the backend and its background jobs; not required to
  run lint/type-check/most unit tests)

**Install UV**:

```bash
# macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip/pipx
pip install uv
# or
pipx install uv
```

### Installation

```bash
# Clone repository
git clone https://github.com/ByronWilliamsCPA/cyo-adventure.git
cd cyo_adventure

# Install dependencies (includes dev tools - REQUIRED for development)
uv sync --all-extras

# Setup pre-commit hooks (required)
uv run pre-commit install
```

### Running the Backend

CYO Adventure is a full-stack application, not a standalone importable library. To run
the FastAPI backend locally:

```bash
uv run uvicorn cyo_adventure.app:app --reload
```

The API is then available at <http://localhost:8000>, with interactive docs at
<http://localhost:8000/docs> and the raw OpenAPI schema at
<http://localhost:8000/openapi.json> (the source of truth the frontend's client is
generated from).

## Frontend Development

The frontend is a React + TypeScript application built with Vite.

### Quick Start

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:3000 with hot reload.

### Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start dev server with HMR |
| `npm run build` | Build for production (`tsc -b && vite build`) |
| `npm run test` | Run Vitest in watch mode |
| `npm run test:run` | Run Vitest once, CI mode |
| `npm run test:coverage` | Run Vitest with coverage |
| `npm run test:e2e` | Run the mocked Playwright e2e suite |
| `npm run lint` | Lint code (ESLint) |
| `npm run format` | Format code (Prettier) |
| `npm run typecheck` | Run TypeScript type checking |
| `npm run generate-client` | Generate API client from OpenAPI |

### API Client Generation

Generate a type-safe TypeScript client from the FastAPI OpenAPI schema:

```bash
# Start backend first
uv run uvicorn cyo_adventure.app:app &

# Generate client
cd frontend && npm run generate-client
```

This creates typed API functions in `frontend/src/client/`.

### Docker

```bash
# Development (with hot reload)
docker-compose up frontend

# Production build
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up frontend
```

## Supply Chain Security

This project implements enterprise-grade supply chain security with a multi-tier package index strategy and centralized secrets management.

### Security Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                    Package Index Priority                        │
├─────────────────────────────────────────────────────────────────┤
│  1. Google Assured OSS (SLSA Level 3) - Third-party packages    │
│  2. Internal Artifact Registry - Organization packages           │
│  3. PyPI (fallback) - Packages not in tier 1 or 2               │
└─────────────────────────────────────────────────────────────────┘
```

### Quick Start

```bash
# Run the setup script
./scripts/setup-supply-chain.sh

# Or manually configure
gcloud auth login
gcloud auth application-default login
pip install keyrings.google-artifactregistry-auth
```

### Package Indexes

| Index | SLSA Level | Purpose | Default |
|-------|------------|---------|---------|
| PyPI | - | Standard packages | Yes (default) |
| Google Assured OSS | 3 | Verified third-party packages | Opt-in |
| Internal Registry | 2+ | Organization-maintained packages | Opt-in |

**How It Works:**

By default, all packages resolve from PyPI. After configuring GCP authentication, you can opt-in specific packages to use Assured OSS by uncommenting entries in `pyproject.toml`:

```toml
[tool.uv.sources]
numpy = { index = "assured-oss" }
pandas = { index = "assured-oss" }
requests = { index = "assured-oss" }
```

**Why This Matters:**

- **SLSA Level 3**: Build integrity, provenance, and tamper-proof artifacts
- **Supply Chain Protection**: Reduced risk of dependency confusion attacks
- **Compliance**: Meets enterprise security and audit requirements
- **Graceful Fallback**: Works without authentication, opt-in when ready

### Secrets Management with Infisical

Secrets are managed via [Infisical](https://infisical.com/) instead of environment variables or GitHub Secrets.

**Local Development:**

```bash
# Login to Infisical
infisical login

# Initialize project connection
infisical init

# Run commands with secrets injected
infisical run --env=dev -- uv run python main.py

# Or export secrets to local file
infisical export --env=dev > .env.local
```

**CI/CD Integration:**

- GitHub Actions use Infisical's Machine Identity authentication
- Secrets are injected at runtime, never stored in repositories
- Environment mapping: `main` → `prod`, `develop` → `staging`, `*` → `dev`

### SBOM & Attestation

Software Bill of Materials (SBOM) is generated on every release:

```bash
# Generate SBOM locally
uv run cyclonedx-py environment -o sbom.json

# Verify package attestation
pip-audit --require-hashes
```

**Automated via CI:**

- CycloneDX SBOM generated in JSON and XML formats
- Attestation attached to GitHub releases
- Vulnerability scanning with OSV database

### Setup Instructions

1. **Run the setup script** (recommended):

   ```bash
   ./scripts/setup-supply-chain.sh
   ```

2. **Or configure manually**:

   **Google Cloud Authentication:**

   ```bash
   gcloud auth login
   gcloud auth application-default login
   pip install keyrings.google-artifactregistry-auth
   ```

   **Infisical Setup:**

   ```bash
   # Install Infisical CLI
   # macOS
   brew install infisical/get-cli/infisical

   # Linux
   curl -1sLf 'https://dl.cloudsmith.io/public/infisical/infisical-cli/setup.deb.sh' | sudo -E bash
   sudo apt-get install infisical

   # Connect to project
   infisical login
   infisical init
   ```

3. **Configure CI/CD secrets in Infisical:**

   - `GCP_SA_KEY_BASE64`: Base64-encoded GCP service account key
   - `CODECOV_TOKEN`: Codecov upload token (if using Codecov)
   - `SONAR_TOKEN`: SonarCloud token (if using SonarCloud)

### Required GCP Permissions

| Role | Purpose |
|------|---------|
| `roles/artifactregistry.reader` | Read from Assured OSS and internal registry |
| `roles/artifactregistry.writer` | Publish to internal registry (CI only) |

### Troubleshooting

**Q: Packages not found in Assured OSS?**

- UV automatically falls back to PyPI - no action needed
- Check available packages: [Assured OSS Supported Packages](https://cloud.google.com/assured-open-source-software/docs/supported-packages)

**Q: Authentication errors with Artifact Registry?**

- Run `gcloud auth application-default login` to refresh credentials
- Verify service account has `Artifact Registry Reader` role
- Check keyring is installed: `pip install keyrings.google-artifactregistry-auth`

**Q: Infisical connection issues?**

- Verify `.infisical.json` has correct `workspaceId`
- Check your Infisical organization permissions
- For CI: Ensure `INFISICAL_CLIENT_ID` and `INFISICAL_CLIENT_SECRET` are set

**Q: How to verify supply chain setup?**

```bash
# Test package index access
./scripts/setup-supply-chain.sh  # Re-run to verify all checks pass
```

## Development

### Setup Development Environment

```bash
# Install all dependencies including dev tools
uv sync --all-extras

# Setup pre-commit hooks
uv run pre-commit install

# Install Qlty CLI for unified code quality checks
curl https://qlty.sh | bash

# Run tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=cyo_adventure --cov-report=html

# Run all quality checks (using Qlty)
qlty check

# Or use pre-commit
uv run pre-commit run --all-files
```

### Code Quality Standards

All code must meet these requirements:

- **Formatting**: Ruff (88 char limit)
- **Linting**: Ruff with PyStrict-aligned rules (see below)
- **Type Checking**: BasedPyright strict mode
- **Testing**: Pytest with 80%+ coverage
- **Security**: Bandit + dependency scanning
- **Documentation**: Docstrings on all public APIs

**Unified Quality Tool**: This project uses [Qlty](https://qlty.sh) to consolidate all quality checks into a single fast tool. See [`.qlty/qlty.toml`](.qlty/qlty.toml) for configuration.

### PyStrict-Aligned Ruff Configuration

This project uses **PyStrict-aligned Ruff rules** for stricter code quality enforcement beyond standard Python linting:

| Rule | Category | Purpose |
|------|----------|---------|
| **BLE** | Blind except | Prevent bare `except:` clauses |
| **EM** | Error messages | Enforce descriptive error messages |
| **SLF** | Private access | Prevent access to private members |
| **INP** | Implicit packages | Require explicit `__init__.py` |
| **ISC** | Implicit concatenation | Prevent implicit string concatenation |
| **PGH** | Pygrep hooks | Advanced pattern-based checks |
| **RSE** | Raise statement | Proper exception raising |
| **TID** | Tidy imports | Clean import organization |
| **YTT** | sys.version | Safe version checking |
| **FA** | Future annotations | Modern annotation syntax |
| **T10** | Debugger | No debugger statements in production |
| **G** | Logging format | Safe logging string formatting |

These rules catch bugs that standard linting misses and enforce production-quality code patterns.

### Claude Code Configuration

This project includes a `.claude/` directory with project-specific Claude Code configuration:

**Directory Structure**:
```text
.claude/
├── agents/            # Specialized subagent definitions
├── commands/          # Custom slash commands
├── context/           # Project-specific context files
├── skills/            # Reusable skills (e.g. cyo-author story-filling skill)
└── settings.json      # Project-scoped Claude Code settings
```

Universal, cross-project standards live at `~/.claude/CLAUDE.md` (user-level, not part of
this repo); project-specific guidelines live in this repo's root `CLAUDE.md`. See
[`.claude/README.md`](.claude/README.md) for the full breakdown.

### Running Tests

```bash
# Run all tests
uv run pytest -v

# Run specific test file
uv run pytest tests/unit/test_module.py -v

# Run with coverage report
uv run pytest --cov=cyo_adventure --cov-report=term-missing

# Run tests in parallel
uv run pytest -n auto
```

### Quality Checks with Qlty

**Recommended**: Use Qlty CLI for unified code quality checks.

```bash
# Run all quality checks (fast!)
qlty check

# Run checks on only changed files (fastest)
qlty check --filter=diff

# Run specific plugins only
qlty check --plugin ruff --plugin pyright

# Auto-format code
qlty fmt

# View current configuration
qlty config show
```

**Qlty runs all these tools in a single pass:**

**Python Quality:**

- Ruff (linting + formatting)
- BasedPyright (type checking)
- Bandit (security scanning)

**Security & Secrets:**

- Gitleaks (secrets detection)
- TruffleHog (entropy-based secrets detection)
- OSV Scanner (dependency vulnerabilities)

**File & Configuration:**

- Markdownlint (markdown linting)
- Yamllint (YAML linting)
- Prettier (JSON, YAML, Markdown formatting)
- Actionlint (GitHub Actions workflows)
- Shellcheck (shell script linting)

**Container & Infrastructure** (if Docker enabled):

- Hadolint (Dockerfile linting)
- Trivy (container security scanning)
- Checkov (infrastructure as code security)

**Code Quality Metrics:**

- Complexity analysis (cyclomatic, cognitive)
- Code smells detection
- Maintainability scoring

### Individual Tool Commands (if needed)

```bash
# Format code
uv run ruff format src tests

# Lint and auto-fix
uv run ruff check --fix src tests

# Type checking
uv run basedpyright src

# Security scanning
uv run bandit -r src

# Dependency vulnerabilities
qlty check --plugin osv_scanner
```

## Project Structure

```text
cyo_adventure/
├── src/cyo_adventure/       # FastAPI backend package
│   ├── app.py               # FastAPI app; wires all routers via include_router
│   ├── api/                 # FastAPI routers: health, library, reading, generation,
│   │                        # profiles, families, ratings, assignments, approval,
│   │                        # covers, moderation_dashboard, moderation_thresholds,
│   │                        # provider_allowlist, me, story_requests
│   ├── core/                # config.py, database.py (async SQLAlchemy), exceptions.py
│   ├── middleware/          # correlation.py, security.py (OWASP headers)
│   ├── db/                  # SQLAlchemy ORM models (stories, profiles, families,
│   │                        # requests, ratings, moderation, events)
│   ├── storybook/           # Storybook/Node/Choice/Ending domain model + condition
│   │                        # evaluator
│   ├── story_requests/      # Intake: brief, screening, authoring plan, anchoring
│   ├── generation/          # Staged LLM pipeline; providers/, RQ queue + worker,
│   │                        # skeleton catalog/matching
│   ├── validator/           # Deterministic validation gate (topology, safety,
│   │                        # reading level, band profile)
│   ├── moderation/          # Safety classifiers, fidelity review, repair, thresholds
│   ├── publishing/          # Guardian approve-and-publish state machine
│   ├── covers/              # AI cover-art generation, storage, optimization
│   ├── player/               # Reading/replay state engine
│   ├── events/               # Append-only pipeline event log
│   └── utils/                # logging.py (structlog)
├── tests/                    # Test suite (unit/, integration/, conftest.py)
├── frontend/                  # React 19 + TypeScript + Vite app (own package.json)
│   └── src/
│       ├── client/            # Generated axios client (committed, drift-checked in CI)
│       ├── auth/               # Supabase auth context, ProtectedRoute
│       ├── guardian/           # Guardian console: requests, review, moderation,
│       │                       # profiles, assignments
│       ├── kid/                 # KidShell, ProfilePickerPage
│       ├── landing/             # Landing page
│       ├── library/              # LibraryPage, BookCard, RequestStory, StarRating
│       ├── reader/                # Reader, ReaderPage, offline/conflict dialogs
│       ├── player/                # Client-side reading engine (mirrors backend player)
│       ├── profiles/              # Profile management
│       ├── offline/                # IndexedDB offline reading + sync
│       └── hooks/                   # useApi, useOnlineStatus, useReplayOnReconnect, ...
├── docs/                      # Documentation
│   ├── planning/               # Vision, tech spec, roadmap, ADRs (docs/planning/adr/)
│   └── architecture/            # System overview, data model, deployment, generation
│                                 # pipeline diagrams
├── pyproject.toml              # Dependencies & tool config
├── README.md                   # This file
├── CONTRIBUTING.md             # Contribution guidelines
└── LICENSE                     # License
```

## Documentation

- **[CONTRIBUTING.md](CONTRIBUTING.md)**: How to contribute to the project
- **[docs/planning/roadmap.md](docs/planning/roadmap.md)**: Phased implementation plan and current status
- **[docs/planning/adr/](docs/planning/adr/)**: 12 Architecture Decision Records
- **[docs/architecture/](docs/architecture/)**: System overview, data model, deployment,
  and generation-pipeline diagrams

### Writing Documentation

- Use Markdown for all documentation
- Include code examples for clarity
- Update README.md when adding major features
- Maintain architecture documentation (see [docs/ADRs/](docs/ADRs/))

## Testing

### Testing Policy

All new functionality must include tests:

- **Unit tests**: Test individual functions/classes
- **Integration tests**: Test component interactions
- **Coverage**: Maintain 80%+ coverage
- **Markers**: Use pytest markers (`@pytest.mark.unit`, `@pytest.mark.integration`)

### Test Guidelines

```bash
# Run all tests
uv run pytest -v

# Run only unit tests
uv run pytest -v -m unit

# Run only integration tests
uv run pytest -v -m integration

# Run with coverage requirements
uv run pytest --cov=cyo_adventure --cov-fail-under=80
```

## Security

### Security-First Development

- Validate all inputs
- Use secure defaults
- Scan dependencies regularly
- Report vulnerabilities responsibly

### Reporting Security Issues

Please use [GitHub Private Vulnerability Reporting](https://github.com/ByronWilliamsCPA/cyo-adventure/security/advisories/new)
or email <byronawilliams@gmail.com> rather than using the public issue tracker.

See [SECURITY.md](SECURITY.md) for the complete disclosure policy and response timelines.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development setup
- Code quality standards
- Testing requirements
- Git workflow and commit conventions
- Pull request process

### Quick Checklist Before Submitting PR

- [ ] Code follows style guide (Ruff format + lint)
- [ ] All tests pass with 80%+ coverage
- [ ] BasedPyright type checking passes
- [ ] Docstrings added for new public APIs
- [ ] CHANGELOG.md updated (if significant change)
- [ ] Commits follow conventional commit format

## Versioning

This project uses [Semantic Versioning](https://semver.org/):

- **MAJOR** version: Incompatible API changes
- **MINOR** version: Backwards-compatible functionality additions
- **PATCH** version: Backwards-compatible bug fixes

Current version: **0.1.0**

> **Known issue**: The automated release workflow currently fails on every push to `main`
> (branch protection rejects its direct version-bump push with GH013), so the version has
> not advanced past `0.1.0` despite substantial functionality being built. Tracked in
> [issue #183](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/183). The package
> is not currently published to PyPI.

### Automated Releases with Semantic Release

This project uses [python-semantic-release](https://python-semantic-release.readthedocs.io/) for automated versioning based on [Conventional Commits](https://www.conventionalcommits.org/).

**How it works:**

1. **Commit messages determine version bumps:**
   - `fix:` commits trigger a **PATCH** release (1.0.0 → 1.0.1)
   - `feat:` commits trigger a **MINOR** release (1.0.0 → 1.1.0)
   - `BREAKING CHANGE:` in commit body or `!` after type triggers **MAJOR** release (1.0.0 → 2.0.0)

2. **On merge to main:**
   - Analyzes commits since last release
   - Determines appropriate version bump
   - Updates version in `pyproject.toml`
   - Generates/updates `CHANGELOG.md`
   - Creates Git tag and GitHub Release
   - Publishes to PyPI (if configured)

**Commit message examples:**

```bash
# Patch release (bug fix)
git commit -m "fix: resolve null pointer in data parser"

# Minor release (new feature)
git commit -m "feat: add CSV export functionality"

# Major release (breaking change)
git commit -m "feat!: redesign API for better ergonomics

BREAKING CHANGE: API has been redesigned for improved usability.
See migration guide in docs/migration/v2.0.0.md"
```

**Configuration:** See `[tool.semantic_release]` in `pyproject.toml` for settings.

## Template Maintenance

This project was generated from a cookiecutter template and is managed with cruft.

### Updating from Template

To sync with the latest template changes:

```bash
# Preview changes first
cruft diff

# Apply updates (recommended: use the wrapper script)
./scripts/cruft-update.sh

# Or use cruft directly (requires manual cleanup)
cruft update
python scripts/cleanup_conditional_files.py
```

### Important: Cruft Update Limitations

**Cruft only syncs file contents** - it does NOT re-run post-generation hooks that clean up conditional files.

When you change feature flags in `.cruft.json` (e.g., disabling `include_api_framework`), the corresponding files are NOT automatically removed. You must run the cleanup script:

```bash
# Check for orphaned files
python scripts/check_orphaned_files.py

# Remove orphaned files
python scripts/cleanup_conditional_files.py

# Or preview what would be removed
python scripts/cleanup_conditional_files.py --dry-run
```

### Conditional Files

Files that may need cleanup when features are disabled:

| Feature | Files to Remove |
|---------|-----------------|
| `include_api_framework: no` | `src/*/api/`, `src/*/middleware/` |
| `include_sentry: no` | `src/*/core/sentry.py` |
| `include_background_jobs: no` | `src/*/jobs/` |
| `include_caching: no` | `src/*/core/cache.py` |
| `include_docker: no` | `Dockerfile`, `docker-compose*.yml` |
| `use_mkdocs: no` | `mkdocs.yml`, `docs/` |

The CI pipeline includes automated checks for orphaned files to prevent this issue.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/ByronWilliamsCPA/cyo-adventure/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ByronWilliamsCPA/cyo-adventure/discussions)
- **Email**: byronawilliams@gmail.com

## Acknowledgments

Thank you to all contributors and the open-source community!

---

**Made with by [Byron Williams](https://github.com/williaby)**
