---
title: "API Testing (Postman/newman)"
schema_type: common
status: published
owner: core-maintainer
purpose: "Documents the Postman/newman API test suite, how to run it locally, and how CI executes it."
tags:
  - api
  - testing
  - ci_cd
---

The Postman collection at [`docs/api/postman-collection.json`](postman-collection.json) exercises the
FastAPI backend end to end over HTTP: real routing, middleware, authorization, and a migrated PostgreSQL
schema. CI runs it with [newman](https://github.com/postmanlabs/newman) in the `api-tests` job of
`.github/workflows/ci.yml` and uploads the JUnit results to Codecov Test Analytics under the `api` flag.

## What is tested

The collection contains 23 folders (one per resource), 136 requests, and 404 assertions, covering 67 of
the 83 operations the app registers as of this writing. The 16 operations added after this suite's last
extension still need folders: 14 from the M4b-d family-tier wave (PR #270: `flags`, `notifications`,
`reading-history`, `recommendations`, `node-edit`, `rescreen`, `audit`, guardian family-connection
consent, and the family budget/reading-summary reads) plus the admin master library listing and the
admin generation-job force-fail action (PR #277). New routers must get a folder here. Every request
asserts an exact status code and validates the response body against a JSON Schema resolved from the
app's OpenAPI components; happy-path requests add semantic assertions (state transitions, echoed fields,
list contents guaranteed by seed data).

| Folder | Coverage |
| --- | --- |
| health | Liveness, readiness, and startup probes |
| auth-negative | Cross-cutting 401 (no token), 403 (wrong role), 401 (unknown subject) |
| me, profiles, families | Identity, profile create/read/update, admin family listing + create/rename, role gates |
| child-sessions | Mint for the seeded profile, prove the token acts as that child via /me, role/cross-family/missing-profile gates |
| device-grants | Mint, list (token never re-exposed), the device token's exact capability matrix (profiles list + child-session mint only), revoke, and online revocation enforcement (401 after revoke) |
| onboarding | First-login provisioning (201), idempotent retry (200), child-session and device tokens refused |
| library, reading, ratings | Published-book discovery, reading-state save/replay, series-next continuation (Ember Trail pair, null cases, gates), rating creation (the endpoint is an upsert; the update path is not yet re-exercised) |
| assignments | Assign storybooks, guardian book listing, content summary (no unassign endpoint exists) |
| story-requests | Full lifecycle: create, decline, approve, authored create, admin authoring-plan (201 + 409 idempotency), admin cross-family queue |
| approval | Storybook lifecycle on the seeded in-review story: send-back, resubmit, approve |
| generation | Concept creation and generation-job flow (enqueue is best-effort without Redis) |
| moderation-thresholds, provider-allowlist | Admin CRUD plus role gates |
| moderation-dashboard | Override-evidence aggregation and threshold suggestions (runs after the thresholds folder so its writes appear in recent_changes) |
| admin-users | Adult-account listing (never `authn_subject`), invite into the newman family, duplicate-invite 409, pending-transition 422, self-manage 403 |
| admin-profiles | Cross-family listing, create, PIN + deactivate lifecycle (deactivated profile then 404s a child-session mint), malformed-PIN 422 never echoing the input |
| family-connections | Directional connect, duplicate 409, self-connection 422, unknown-family 404, delete |
| covers | Auth negatives and DB-only status reads only (see externals policy below) |
| archive | Archive lifecycle on the second seeded published story; runs last because it removes the book from the library |

All resource IDs are discovered dynamically from prior responses (`pm.collectionVariables.set`), never
hardcoded, so the suite is stable across reseeded databases. Requests the suite creates on the way
(a sibling profile, the "Newman Ops Family", an invited user, an admin-created profile) are additive and
never touch the seeded rows the earlier folders assert on.

### Externals policy

CI runs with no Supabase, Gemini, R2, or LLM credentials and no Redis. Endpoints whose happy path calls an
external service are covered by auth negatives and side-effect-free reads only: `POST
/storybooks/{id}/versions/{v}/cover` (Gemini + Cloudflare R2) is never triggered, and generation
enqueue failures are tolerated by design (the job row is still created).

### Auth model

The stack runs with `ENVIRONMENT=local`, which enables the dev-auth path: the bearer token string is
treated as the verified OIDC subject (no JWT verification), and authorization still resolves real `User`
rows, roles, and family scoping from the database. `scripts/seed_dev_data.py` provisions the three
subjects the collection uses as collection variables:

| Variable | Token | Role |
| --- | --- | --- |
| `guardian_token` | `dev-guardian` | guardian |
| `child_token` | `dev-child` | child (bound to the seeded profile) |
| `admin_token` | `dev-admin` | admin |

Two further bearers are not seeded but minted over the API during the run and stored as collection
variables: `child_session_token` (a real backend-signed child session JWT, minted in the child-sessions
folder) and `device_grant_token` (a backend-signed device grant, minted and later revoked in the
device-grants folder). Both exercise the non-guardian verification branches of `api/deps.py` end to end,
which requires the dev signing secrets described under "Required environment" below.

### Request pacing (mandatory)

Every newman invocation must pass `--delay-request 1100` (CI does; the local command below does), for
two reasons:

1. **Commit visibility.** The app's unit-of-work commits when the request's yield-dependency tears
   down, which happens after the response is sent. A zero-delay runner can therefore receive a 201 and
   fire the next request before the created row is committed, producing intermittent 403/404s on
   just-created resources. The delay serializes each request against the previous one's commit.
2. **Rate limiting.** Wherever `RateLimitMiddleware` is enabled (any non-`local` environment; the
   compose/CI stack runs `ENVIRONMENT=local`, where it is off), the delay keeps any 60-second window
   under the 60 requests/minute ceiling.

A full run takes roughly 3 minutes by design. If you run the collection in the Postman desktop Runner
instead of newman, set its own Delay setting to 1100 ms; the CLI flag does not apply there. If the suite
grows enough to hurt CI latency, do not shrink the delay; batch-friendly alternatives (splitting the
collection across parallel stacks) are the way out.

## Running locally

Prerequisites: Docker with the compose plugin, `uv`, Node.js, `npm install -g newman`, and the
[Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) (pinned to 2.109.1
in CI via `supabase/setup-cli`). From the repo root:

```bash
docker compose down -v --remove-orphans          # fresh database (this project's stack only)
docker compose up -d --build app db
until curl -fsS http://localhost:8000/health/live >/dev/null 2>&1; do sleep 2; done

export DATABASE_URL=postgresql+asyncpg://cyo_adventure:password@localhost:5432/cyo_adventure
PGSSLMODE=disable supabase db push \
  --db-url postgresql://cyo_adventure:password@localhost:5432/cyo_adventure --yes
                                                  # real migration chain, not create_all;
                                                  # PGSSLMODE=disable works around the CLI's
                                                  # TLS-by-default pgx driver against this
                                                  # plain, non-TLS compose Postgres (ADR-012)
uv run python scripts/seed_dev_data.py           # idempotent seed (users, stories, assignments)

newman run docs/api/postman-collection.json \
  --env-var "base_url=http://localhost:8000" \
  --delay-request 1100 \
  --reporters cli,junit --reporter-junit-export newman-junit.xml --bail
```

If another compose project already occupies the default ports or the pinned `172.25.0.0/16` subnet (for
example a running dev stack), run the suite under an isolated project with remapped ports and point
`base_url`/`DATABASE_URL` at them (`docker compose -p cyo-adventure-apitest ...`).

## Required environment

No real secrets are required to run the suite. The compose defaults are sufficient: `ENVIRONMENT=local`
(dev auth), `DATABASE_URL` pointing at the compose `db` service, benign dev defaults for
`CHILD_SESSION_SECRET` and `DEVICE_GRANT_SECRET` (shipped in `docker-compose.yml`; without them the
child-session and device-grant mint endpoints answer 400 `ConfigurationError`, so the child-sessions,
device-grants, and onboarding folders cannot pass), and no Supabase/Gemini/R2/LLM/Redis configuration.
If you run the backend outside compose (bare `uvicorn`), export those two variables yourself. The only
non-default env used in CI is `DATABASE_URL` for the runner-side migrate and seed steps, which targets
the published Postgres port. Separately from running the tests, CI's upload step uses the repo-level
`CODECOV_TOKEN` secret for optional, non-blocking Test Analytics reporting (`fail_ci_if_error: false`);
a missing token degrades reporting only, never test execution.

## CI integration

`.github/workflows/ci.yml` gates the `api-tests` job on this collection existing
(`detect-api-collection`), then: builds and starts `app` + `db` from the repo compose file, waits on
`/health/live`, installs the backend (`uv sync --extra api`), sets up the pinned Supabase CLI
(`supabase/setup-cli`, version 2.109.1) and applies the real migration chain with
`PGSSLMODE=disable supabase db push --db-url ... --yes` (ADR-012; `PGSSLMODE=disable` works around the
CLI's TLS-by-default driver against the plain compose Postgres) followed by `scripts/seed_dev_data.py`
against the migrated compose database, runs newman with the JUnit reporter, and uploads
`newman-junit.xml` via `codecov/test-results-action` under the `api` flag (org standard: one report, one
flag). Results appear in the Codecov Tests tab for the PR.

## Maintenance

The OpenAPI schema is the source of truth. After adding or changing a route or response model: update the
affected requests and their inlined JSON Schemas in the collection, regenerate the frontend client
(`npm run generate-client`) so the `contract` job stays green, and re-run the local loop above before
pushing.
