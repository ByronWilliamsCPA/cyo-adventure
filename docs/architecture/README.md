---
title: "Architecture Overview"
schema_type: common
status: published
owner: core-maintainer
purpose: "System architecture overview and index of architecture decision records."
tags:
  - architecture
  - overview
---

CYO Adventure is a choose-your-own-adventure reading app for kids, built as a
FastAPI service backed by PostgreSQL and deployed via Docker.

## System Layout

```
src/cyo_adventure/
├── api/
│   └── health.py          # Health-check endpoints
├── core/
│   ├── config.py          # Pydantic Settings configuration
│   ├── database.py        # SQLAlchemy async engine and session factory
│   └── exceptions.py      # Centralized exception hierarchy
├── middleware/
│   ├── security.py        # OWASP-aligned security headers and SSRF protection
│   └── correlation.py     # Request correlation and distributed tracing IDs
└── utils/
    ├── financial.py       # Decimal-precision financial utilities
    └── logging.py         # Structlog structured logging with correlation
```

The API layer delegates to core business logic in `core/`. All inbound requests
pass through the middleware stack: correlation IDs are attached first, then
security headers are applied. Configuration is loaded from environment variables
and `.env` files via `core/config.py`.

Database access is handled through SQLAlchemy 2 async sessions defined in
`core/database.py`. Alembic manages schema migrations.

## Architecture Decision Records

The ADRs below capture the key design choices for this project. They are stored
under `docs/planning/adr/` and should be consulted before changing the areas
they govern.

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](../planning/adr/adr-001-story-format-json-storybook.md) | Story format: JSON Storybook | Accepted |
| [ADR-002](../planning/adr/adr-002-client-pwa.md) | Client: Progressive Web App | Accepted |
| [ADR-003](../planning/adr/adr-003-frontier-llm-generation.md) | Frontier LLM story generation | Accepted |
| [ADR-004](../planning/adr/adr-004-homelab-first-deployment.md) | Homelab-first deployment | Accepted |
| [ADR-005](../planning/adr/adr-005-mandatory-human-approval.md) | Mandatory human approval gate | Accepted |
| [ADR-006](../planning/adr/adr-006-conditions-inhouse-evaluator.md) | Conditions: in-house evaluator | Accepted |

## Key Technology Choices

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Web framework | FastAPI | Async-native, typed, auto-generated OpenAPI docs |
| ORM | SQLAlchemy 2 asyncio | Async support, Alembic migrations, type-safe queries |
| Configuration | Pydantic Settings | Environment variable parsing with validation |
| Logging | Structlog | JSON structured logs with automatic correlation ID injection |
| Type checking | BasedPyright strict | Stricter than MyPy; catches more errors at development time |
| Package manager | UV | Faster than pip/poetry; lock file ensures reproducible builds |

## Security Posture

Security middleware (`middleware/security.py`) enforces:

- Strict Transport Security (HSTS)
- Content-Security-Policy headers
- SSRF protection: blocks requests to private IP ranges and loopback addresses
- `X-Content-Type-Options: nosniff` and related OWASP-recommended headers

All inputs are validated through Pydantic models before reaching business logic.
Secrets are loaded from environment variables. The only credential-like default
committed to the repository is the localhost-only development database URL; a
`model_validator` in `core/config.py` raises `ConfigurationError` if that
development default is used in any non-local environment, so it cannot leak into
deployed environments.

## Further Reading

- [Project vision and scope](../planning/project-vision.md)
- [Technical specification](../planning/tech-spec.md)
- [Implementation roadmap](../planning/roadmap.md)
- [ADR index](../planning/adr/README.md)
