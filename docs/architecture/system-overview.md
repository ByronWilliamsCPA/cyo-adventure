---
title: "System Overview"
schema_type: common
status: published
owner: core-maintainer
purpose: "C4 context and container diagrams for the CYO Adventure system."
tags:
  - architecture
  - overview
---

CYO Adventure is a choose-your-own-adventure reading app for kids. A React 19 PWA
lets children read and play through branching stories offline; a FastAPI backend
serves the story library, manages reading progress, and runs an LLM-powered story
generation pipeline behind a mandatory guardian approval gate (ADR-005).

## C4 Level 1: System Context

The system context shows the two human actors and the external systems the CYO
Adventure system depends on.

![C4 System Context](diagrams/c4-context.svg)

**Key relationships:**

- **Child Reader** uses the PWA to read stories, make choices, and progress through
  branching narratives, including while offline.
- **Guardian/Author** uses the PWA to submit story concepts, monitor generation jobs,
  and approve stories before any child can see them (ADR-005: mandatory approval).
- **OpenRouter** is the primary LLM provider. Stories are generated through a
  three-stage pipeline (Structure, Prose, Repair) with a provider fallback cascade.
- **Ollama** is the local fallback LLM. If OpenRouter fails (leg-fatal errors), the
  `FallbackProvider` cascade tries Ollama before giving up.
- **Authentik** provides OIDC identity. Guardian and child roles are encoded in the
  token; the dev environment uses a token-as-subject seam (see `api/deps.py`).
- **PostgreSQL** holds all operational metadata: family records, users, child profiles,
  storybook lifecycle, reading state, completions, generation jobs.

## C4 Level 2: Containers

The container diagram shows how the system is split across runtime boundaries.

![C4 Container Diagram](diagrams/c4-container.svg)

**Container responsibilities:**

| Container | Technology | Responsibility |
|-----------|------------|----------------|
| PWA | React 19, TypeScript, Vite | Reader UI, library, offline cache, XState player |
| FastAPI Backend | Python 3.12, FastAPI, Pydantic v2 | API routers, auth, validator, generation dispatch |
| Generation Worker | RQ, Python | Async staged generation; long-running, separate container |
| PostgreSQL | PostgreSQL 16, SQLAlchemy 2 | All operational entities (9 ORM tables) |
| Redis | Redis 7, RQ | Generation job queue and broker |
| MinIO | MinIO / S3 API | Story blob storage (deferred to Phase 5; Phase 1 uses inline JSONB) |

**The OpenAPI contract:**

The PWA never hand-writes HTTP request or response types. The frontend
`src/client/` directory is fully generated from the backend's OpenAPI schema:

```bash
# Start the backend, then:
cd frontend && npm run generate-client
```

Treat `frontend/src/client/` as build output; do not edit files there directly.

## Publish State Machine

No story reaches a child profile without a recorded guardian approval (ADR-005).
The lifecycle is enforced as a state machine with no bypass path:

```text
draft -> generating -> auto_check -+-> needs_revision -> (repair/regenerate) -+
                                   |                                           |
                                   +-> in_review -> approved -> published -> archived
```

The `in_review -> approved` transition requires a guardian. Automated checks
(validation gate plus moderation) gate `generating -> in_review`; failures route
to `needs_revision`. A story is visible to a child only in `published`.

## Further Reading

- [Generation Pipeline](generation-pipeline.md): staged LLM generation and provider cascade
- [Validation and Player](validation-and-player.md): validator gate and story engine
- [Data Model](data-model.md): the 9 ORM tables and their relationships
- [Deployment](deployment.md): homelab Docker deployment
- ADR-005: [Mandatory Human Approval](../planning/adr/adr-005-mandatory-human-approval.md)
- ADR-002: [Client: Progressive Web App](../planning/adr/adr-002-client-pwa.md)
