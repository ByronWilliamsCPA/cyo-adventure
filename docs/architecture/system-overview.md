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
generation pipeline behind a mandatory admin approval gate (ADR-005).

## C4 Level 1: System Context

The system context shows the three human actors and the external systems the CYO
Adventure system depends on.

![C4 System Context](diagrams/c4-context.svg)

**Key relationships:**

- **Child Reader** uses the PWA to read stories, make choices, and progress through
  branching narratives, including while offline.
- **Guardian/Author** uses the PWA to submit story concepts and monitor generation
  jobs for the family; a guardian cannot self-approve.
- **Admin (Approver)** is a global, cross-family role (`is_admin`) that reviews and
  approves stories before any child can see them (ADR-005: mandatory approval).
  Guardians and children who attempt the approve action receive 403.
- **OpenRouter** is the primary LLM provider, tried across two legs: leg 1 (primary
  model, claude-haiku-4.5) then leg 2 (fallback model, claude-sonnet-4.6). Stories are
  generated through a three-stage pipeline (Structure, Prose, Repair) with a provider
  fallback cascade.
- **Modal** is the non-OpenRouter backstop (leg 3), replacing the retired local
  Ollama leg. If both OpenRouter legs fail (leg-fatal errors), the
  `FallbackProvider` cascade tries Modal before giving up. The leg is included
  only when `MODAL_BASE_URL` and `MODAL_MODEL` are set; with them unset the
  cascade is two OpenRouter legs on one vendor and one account, and
  `build_provider` logs `generation.cascade_single_vendor` at WARNING.
- **Supabase Auth** provides OIDC identity (ADR-009). The guardian identity and child
  session are encoded in the token; the local dev environment uses a token-as-subject
  seam, while non-local environments verify the JWT via `jwt.PyJWKClient` (see `api/deps.py`).
- **PostgreSQL** holds all operational metadata: family records, users, child profiles,
  storybook lifecycle, reading state, completions, generation jobs.
- **Kids Web Services (Epic)** is the verifiable-parental-consent counterparty under
  evaluation (ADR-018 D1, still open). The backend sends a verification email through
  Epic's API, the parent completes Epic's hosted flow, and Epic calls a webhook back. The
  parent's browser also returns to us over a signed redirect, but that leg is display-only:
  its HMAC covers no timestamp and no nonce, so a link a parent once received replays
  forever. **Only the `parent-verified` webhook writes consent state.** As of 2026-08-09
  this is wired on staging against the KWS **Test** environment and nothing is wired in
  production; a Test verification is not a valid VPC. See
  [seq-kws-verification.puml](diagrams/seq-kws-verification.puml).

## C4 Level 2: Containers

The container diagram shows how the system is split across runtime boundaries.

![C4 Container Diagram](diagrams/c4-container.svg)

**Container responsibilities:**

| Container | Technology | Responsibility |
| ----------- | ------------ | ---------------- |
| PWA | React 19, TypeScript, Vite | Reader UI, library, offline cache, XState player |
| FastAPI Backend | Python 3.14, FastAPI, Pydantic v2 | API routers, auth, validator, generation dispatch |
| Generation Worker | RQ, Python | Async staged generation; long-running, separate container |
| PostgreSQL | PostgreSQL 16, SQLAlchemy 2 | All operational entities (31 ORM tables) |
| Redis | Redis 7, RQ | Generation job queue and broker |
| MinIO | MinIO / S3 API | Story blob storage (deferred to Phase 5; Phase 1 uses inline JSONB) |
| Cloudflare R2 | R2 / S3 API | AI cover-art (WebP) object storage, ADR-017 (shipped); written by the covers RQ worker (`covers/worker.py`) |

**The OpenAPI contract:**

The PWA never hand-writes HTTP request or response types. The frontend
`src/client/` directory is fully generated from the backend's OpenAPI schema:

```bash
# Start the backend, then:
cd frontend && npm run generate-client
```

Treat `frontend/src/client/` as build output; do not edit files there directly.

## Lifecycle State Machines

No story reaches a child profile without a recorded admin approval (ADR-005).
Two independent lifecycles enforce this, with no bypass path.

**GenerationJob** tracks one staged-generation attempt:

```text
queued -> running -> passed | needs_review | failed
```

**Storybook** tracks the review-and-publish lifecycle of a story
(`publishing/state_machine.py`):

```text
draft ----submit-----> in_review ----approve----> published --archive--> archived
  |                        |    ^                     |
  |auto_reject             |    +------recall---------+
  |                        |send_back
  v                        v
needs_revision <-----------+
  |
  +--submit--> in_review
```

The `in_review -> published` (approve) transition requires a **global admin**
(`is_admin`), which is cross-family; a guardian or child who attempts it receives
403. Automated checks (validation gate plus moderation) drive `draft -> in_review`
or `draft -> needs_revision`; a reviewer can send a story back with
`in_review -> needs_revision`. There is no `generating`, `auto_check`, or `approved`
storybook state; those live only in the GenerationJob lifecycle (`passed`,
`needs_review`) or are folded into `published`. A story is visible to a child only
in `published`.

`published` has two exits, not one. `archive` is terminal (`archived` is absorbing);
`recall` (`RS-C1`) returns the book to `in_review`, which is where a threshold change
that invalidated a stored verdict is handled without killing the book. Recall is also
admin-only and extends ADR-005 rather than relaxing it: the recalled book must clear
the human gate again before any child sees it. Assignment rows survive a recall, so a
re-approval restores the book to exactly the shelves it left. Neither exit reaches a
copy already downloaded to a device; that copy is evicted only on the device's next
successful `/v1/library` fetch, so neither is an incident-response tool.

## Further Reading

- [Generation Pipeline](generation-pipeline.md): staged LLM generation and provider cascade
- [Validation and Player](validation-and-player.md): validator gate and story engine
- [Data Model](data-model.md): the 31 ORM tables and their relationships
- [KWS Parent Verification](diagrams/seq-kws-verification.puml): the three legs of the
  ADR-018 D1 consent integration and why only one of them may write consent state
- [Deployment](deployment.md): homelab Docker deployment
- ADR-005: [Mandatory Human Approval](../planning/adr/adr-005-mandatory-human-approval.md)
- ADR-002: [Client: Progressive Web App](../planning/adr/adr-002-client-pwa.md)
