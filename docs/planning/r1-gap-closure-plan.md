---
title: "R1 Gap-Closure Project Plan (cyo.williamshome.family live)"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Close every gap between the 2026-07-04 comprehensive R1 review and a working family deployment at cyo.williamshome.family, executed by supervised subagents."
tags:
  - planning
  - project_management
component: Strategy
source: "2026-07-04 comprehensive R1 deployment review (session findings; memory: r1-deployment-review-2026-07-04)"
---

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.
> Each Phase 2/3 feature slice begins with a slice-plan task that produces a detailed
> TDD plan; implementation subagents execute that plan task-by-task with review gates.

## Goal

Take CYO Adventure from "reviewed, not deployed" to a working R1 at
`https://cyo.williamshome.family` where: guardians and admins log in
(email+password and Google), children read assigned books with tracked
progress, children request books in free text, guardians approve those
requests, admins approve generated books, guardians assign published books,
and both roles see content review tags at their approval step.

## Decisions of record (owner-confirmed 2026-07-04)

1. **Full generation in R1**: Redis + RQ worker + live providers ship in the
   production stack.
2. **Login**: merge the existing email+password branch now; Google OAuth is
   already enabled in Supabase and gets verified end-to-end in Phase 1.
3. **Child requests are free text**, which requires a new input-moderation
   step (review finding: `POST /concepts` screens only child-name PII, no
   content classifier runs on intake text).
4. **Ingress**: Pangolin resource targets docker-host:443; the stack joins the
   existing docker-host Traefik via the external `traefik_proxy` network with
   `public-chain@file` middleware (security headers, compress, rate limit; no
   Authentik forward-auth, the app validates Supabase JWTs itself). The
   committed `8000:80` port publish is removed (Portainer owns host port 8000).
5. GHCR image publishing is a separate user workstream; Phase 1 deploys
   build-from-source and flips to `image:` lines when that workstream lands.

## Supervision model

Claude (this session) supervises; subagents implement. Per global standards:

| Role | Agent / model | Used for |
| --- | --- | --- |
| Supervisor | session (Fable) | task decomposition, dispatch, review arbitration, merge prep |
| Slice planner | Plan agent, `model: opus` | Phase 2/3 slice plans (detailed TDD task lists) |
| Implementer | general-purpose, `model: sonnet` | all code/config tasks below unless marked opus |
| Deep reviewer | code-reviewer, `model: opus` | security-adjacent slices (auth, moderation, ingress) |
| Standard reviewer | code-reviewer, `model: sonnet` | remaining slices |
| Scout | Explore, `model: haiku` | any additional read-only lookups |

Rules of engagement: feature branches only, signed conventional commits,
`pre-commit run --all-files` before each commit, pushes and merges are
user-gated, one worktree per parallel slice under `.worktrees/`.
Every finished slice gets both reviewer passes before its PR.

## Phase map and dependencies

```text
Phase 0 (hygiene)
  -> Phase 1 (deploy + auth live)        [infra repo + small CYO fixes]
       -> Phase 4 verification on live domain
  -> Phase 2 (guardian gaps + reader fixes)   [parallel with Phase 1]
  -> Phase 3 (child request flow)             [after Phase 2 review-tag slice]
```

Phases 1 and 2 run in parallel (different repos / different files). Phase 3
depends on Phase 2's tag-exposure endpoint (the guardian request queue reuses
it). Phase 4 gates launch.

---

## Phase 0: Branch hygiene and preconditions

### Task 0.1: Land the two open feature branches

Owner: supervisor prepares; merges are user-gated.

- [ ] Rebase `feat/guardian-password-login` (15 ahead / 14 behind main) onto
  `origin/main`; resolve conflicts; run backend + frontend suites.
- [ ] Push and open its PR (email+password login, tip currently `8465e10`).
- [ ] Confirm PR #90 (reader styling) merge state; both PRs merge before any
  Phase 2 slice branches cut, so slices build on the merged reader/auth code.

Abort if: rebase produces failing tests that trace to main-side changes;
surface to user instead of force-fixing.

### Task 0.2: Delete the obsolete deploy-prep branch

- [ ] `git branch -D fix/homelab-r1-deploy-prep` (its nginx `/api` fix is
  already on origin/main; verified 2026-07-04).

### Task 0.3: Working-tree stray changes

- [ ] Ask user about uncommitted `docs/template_feedback.md` and
  `tests/unit/test_providers.py` (ModalProvider test) before any branch
  switching; they belong to another session's work and must not be bundled.

---

## Phase 1: Deployment (homelab-infra + CYO build fixes)

### Task 1.1: Frontend Dockerfile Supabase build args (CYO repo) [sonnet]

**Files:** Modify `frontend/Dockerfile:36-37`.

The production build currently accepts only `VITE_API_URL`. Guardian login
requires `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` at build time
(lazy `supabaseClient.ts` throws without them).

- [ ] Add `ARG VITE_SUPABASE_URL` / `ARG VITE_SUPABASE_ANON_KEY` + matching
  `ENV` lines beside the existing `VITE_API_URL` pair.
- [ ] Verify: `docker build --build-arg VITE_SUPABASE_URL=... -t t frontend/`
  then confirm the built bundle contains the URL (grep the dist assets).
- [ ] Commit `fix(frontend): accept Supabase env as production build args`.

Note: the anon key is a publishable key by design; baking it into the bundle
is standard Supabase practice, not a secret leak.

### Task 1.2: Compose rework for Traefik ingress (homelab-infra) [sonnet]

**Files:** Modify `services/cyo-adventure/docker-compose.yml`, `stack.env`,
`README.md`.

- [ ] Remove `ports: "8000:80"` from `frontend`.
- [ ] Attach `frontend` to external network `traefik_proxy` (keep
  `backend-net` for backend/db reachability) and add labels following the
  fleet convention (see `services/heimdall/docker-compose.yml:38-44`):
  `traefik.enable`, router rule ``Host(`cyo.williamshome.family`)``,
  entrypoint `websecure`, `tls: true`, middleware `public-chain@file`,
  loadbalancer port `80`, `traefik.docker.network: traefik_proxy`.
- [ ] Declare `traefik_proxy` as `external: true` in the compose `networks:`.
- [ ] Pass the new Supabase build args through the frontend `build.args`.
- [ ] Update README ingress section (port table, Pangolin note: resource
  targets docker-host:443, Traefik routes by Host).
- [ ] Verify: `docker compose config` renders cleanly; no host-port publishes
  remain except none.

### Task 1.3: Redis + worker services in the prod stack (homelab-infra) [sonnet]

**Files:** Modify `services/cyo-adventure/docker-compose.yml`, `stack.env`,
`README.md`.

- [ ] Add `redis` service (hardened pattern like `db`: cap_drop ALL,
  no-new-privileges, mem/pids limits, `backend-net` only, healthcheck
  `redis-cli ping`). Use the GHCR mirror image if a `dhi-redis` exists,
  otherwise pinned `redis:7-alpine` with a Renovate digest-pin note.
- [ ] Add `worker` service: same backend image/build context, command
  `rq worker generation --url "$CYO_ADVENTURE_REDIS_URL"` (queue name
  `generation` per `generation/queue.py:55`; entrypoint resolved by dotted
  path, needs no console script), env = backend env plus
  `CYO_ADVENTURE_REDIS_URL=redis://redis:6379/0`, depends_on db+redis
  healthy, no published ports.
- [ ] Backend env additions: `CYO_ADVENTURE_REDIS_URL`,
  `CYO_ADVENTURE_GENERATION_PROVIDER=openrouter`,
  `CYO_ADVENTURE_REVIEW_PROVIDER=openrouter`, `OPENROUTER_API_KEY`,
  `OPENAI_API_KEY` (Stage-0 classifier). Secrets land in Portainer env UI;
  `stack.env` carries `CHANGE_ME_IN_PORTAINER` placeholders.
- [ ] `OIDC_AUDIENCE` needs no entry (defaults to `authenticated`,
  `core/config.py:241-243`, matching Supabase).
- [ ] Verify: `docker compose config`; startup guard notes in README
  (`config.py` fails fast when a non-mock reviewer has no classifier key).

### Task 1.4: Migration step for first deploy (homelab-infra) [sonnet]

The backend image CMD runs uvicorn only; nothing applies Alembic migrations.

- [ ] Add a `migrate` one-shot service (backend image, command
  `alembic upgrade head`, `restart: "no"`, backend-net, depends_on db
  healthy) and document `docker compose run --rm migrate` in the README as
  the pre-upgrade step for first deploy and every image bump.

### Task 1.5: Bring-up on docker-host [operational, supervisor + user]

- [ ] Clone source, `docker compose build`, run migrate, `docker compose up -d`.
  Expected: backend healthy (its `/health/live` healthcheck), worker running,
  frontend attached to `traefik_proxy`.
- [ ] Seed production users: insert guardian + admin `User` rows whose
  `authn_subject` values are the two Supabase user subs (guardian
  `byronawilliams@gmail.com`, admin `byron.williams@gmail.com`), plus family and
  child profiles. Script this as `scripts/seed_prod_users.py` variant or
  documented SQL; do NOT reuse `seed_dev_data.py` (Task 2.4 fixes it, but
  prod gets real profiles, not "Dev Reader").
- [ ] Verify: `curl https://cyo.williamshome.family/health/live` returns 200
  via Pangolin -> docker-host Traefik -> nginx; `/api/v1/me` returns 401
  unauthenticated.
- Abort if: Traefik router does not pick up the labels (check
  `traefik_proxy` attachment and router in Traefik dashboard) or Pangolin
  resource does not reach docker-host:443.

### Task 1.6: Supabase + Google OAuth verification [operational, supervisor + user]

- [ ] Supabase Auth settings: add `https://cyo.williamshome.family` (and its
  `/guardian` callback route) to Site URL / additional redirect URLs.
- [ ] Google client: confirm the Supabase callback URL
  (`https://<project>.supabase.co/auth/v1/callback`) is an authorized
  redirect URI.
- [ ] Browser verification on the live domain: email+password login succeeds;
  Google login succeeds; `GET /api/v1/me` returns the guardian principal;
  admin login reaches the review queue; guardian gets the 403 notice there.

---

## Phase 2: Guardian gaps and reader fixes (CYO repo)

Each task below is a slice: an opus Plan agent writes the detailed TDD plan
(saved beside this file as `r1-slice-<name>.md`), then sonnet implements it
under subagent-driven-development with reviewer gates. Files listed are the
expected touch set discovered during review; the slice plan finalizes them.

### Task 2.1: Guardian-visible content review tags [plan: opus, impl: sonnet, review: opus]

The moderation report (Source/Verdict/category findings,
`moderation/report.py`) renders only on admin-only surfaces today.

**Expected files:** new guardian endpoint in `src/cyo_adventure/api/`
(e.g. extend `assignments.py` GET or a `GET /storybooks/{id}/content-summary`),
serializer reuse from `publishing/review_surface.py` (`FindingView`,
summary flags); frontend `frontend/src/guardian/AssignChildrenDialog.tsx`,
`frontend/src/guardian/assignApi.ts`, shared `FlagBadge` reuse; colocated
vitest files; backend tests `tests/unit/` + `tests/integration/`.

Acceptance: a guardian assigning a published book sees its content tags
(verdict badges, categories, flagged counts) in the assign flow; a guardian
cannot see unpublished books' reports; admin surfaces unchanged.
depends-on: Task 0.1 [completion].

### Task 2.2: Guardian "browse published library and assign" [plan: opus, impl: sonnet, review: sonnet]

**Expected files:** backend guardian list endpoint (family-scoped published
books with assignment status per child; extend `api/assignments.py` or
`api/library.py` with a guardian branch); frontend new
`frontend/src/guardian/BooksPage.tsx` + nav entry in `GuardianShell.tsx`,
reusing `AssignChildrenDialog`; e2e spec `frontend/e2e/`.

Acceptance: guardian sees every published family book (not just their own
request history), each with content tags (from Task 2.1's endpoint) and an
assign action. depends-on: Task 2.1 [output] (endpoint shape).

### Task 2.3: Reader progress correctness [plan: opus, impl: sonnet, review: sonnet]

Three review findings, one slice:

- Wire `POST /completions` when the reader reaches an ending
  (`frontend/src/reader/Reader.tsx:66-68` renders the ending id but never
  posts; backend `api/reading.py:285-334` is ready).
- Server-side resume: on cold IndexedDB, fall back to
  `GET /reading-state/{profile}/{storybook}` (`ReaderPage.tsx:76,101` reads
  only the local cache today).
- Issue #86: suppress the duplicate initial save (StrictMode double-effect)
  with a stable event_id or a no-op guard on the unchanged start state.

Acceptance: finishing a story creates a completion row exactly once;
a cleared-cache device resumes from server state; opening a story issues no
409 and at most one save. depends-on: Task 0.1 [completion] (PR #90 touches
these reader files).

### Task 2.4: Fix seed_dev_data.py [impl: sonnet, no slice plan needed]

**Files:** `scripts/seed_dev_data.py:90-92`.

- [ ] Set `approved_by` + `published_at` on seeded `StorybookVersion` rows and
  create `StorybookAssignment` rows for the seeded profile (both gaps
  verified in review; the assignment gap is new beyond the recorded memory).
- [ ] Verify: fresh local db + seed -> library lists both seeded stories and
  the reader opens them.

---

## Phase 3: Child request -> guardian approval (new feature)

### Task 3.0: Slice design plan [Plan agent, opus]

Free-text child requests need design decisions the implementer must not make
ad hoc; the opus plan resolves at minimum:

- **New `story_request` table** (Concept has no status/profile fields:
  `db/models.py:291-321`): id, family_id, profile_id (requesting child),
  request_text, status (`pending`/`approved`/`declined`), moderation flags,
  reviewed_by, created_at; Alembic migration.
- **Input moderation at submission**: reuse `moderation/classifiers.py`
  `run_classifiers` (currently wired only to generated output) plus the
  existing PII screen (`generation/pii.py:101`) against the child text;
  bright-line hits mark the request blocked before any guardian sees raw text.
- **Endpoints**: `POST /api/v1/story-requests` (kid surface; note the kid UI
  runs under the guardian token in R1, so authorization is guardian-scoped
  with profile_id payload), `GET /api/v1/story-requests?status=pending`
  (guardian or admin), `POST /api/v1/story-requests/{id}/approve` (guardian
  or admin, per the stated requirement; prefills a ConceptBrief and hands off
  to the existing concept+generate path; note the downstream `POST /concepts`
  is guardian-only today, so the plan must either relax that gate for admins
  or route admin approvals through a service-layer call), `POST .../decline`.
- **Kid UI**: request affordance on `frontend/src/kid/` library page (button +
  simple text form, age-appropriate).
- **Guardian UI**: pending-requests section on `ConsolePage` (or a nav page),
  showing the child, the (screened) text, moderation flags, approve (opens
  prefilled `IntakePage` flow) and decline actions.

depends-on: Task 2.1 [output] (tag/flag rendering conventions reused in the
request queue).

### Task 3.1: Backend slice [impl: sonnet, review: opus]

Implement per Task 3.0's plan: model + migration, moderation-on-input,
endpoints, tests (unit + integration, testcontainers pattern per
`tests/integration/conftest.py`).

### Task 3.2: Frontend slice [impl: sonnet, review: sonnet]

Kid request form, guardian queue UI, `<domain>Api.ts` factory per convention,
`npm run generate-client` after backend lands, vitest + one Playwright spec.
depends-on: Task 3.1 [output].

---

## Phase 4: Verification and launch gate

### Task 4.1: Live end-to-end journey verification [ui-testing-agent or supervisor]

Operational checklist on `https://cyo.williamshome.family`, one row per
original requirement:

- [ ] Admin login (email+password and Google) -> review queue loads.
- [ ] Guardian login -> console loads; review queue shows the 403 notice.
- [ ] Guardian hands off to kid surface -> profile picker -> library.
- [ ] Child reads an assigned book; progress persists across reload AND a
  second browser (server resume); completion recorded at the ending.
- [ ] Child submits a free-text request -> appears in guardian pending queue
  with moderation flags.
- [ ] Guardian approves the request -> generation job runs on the worker ->
  book reaches the admin review queue with content tags.
- [ ] Admin approves -> guardian assigns from the browse page, seeing content
  tags -> book appears in the child's library.
- [ ] Backup sidecar healthy (`.last_success` fresh) and worker survives
  restart (`docker compose restart worker`).

### Task 4.2: Deferred-items register [supervisor]

Document as accepted R1 debt, filed as issues: child-session scoping
(PIN/handoff gate, scoped child tokens: hard R2 blocker), admin role granting
UI (DB-edit only today), GHCR image flip (external workstream), Apple OAuth,
`cyo-content` edge store (R2).

---

## Risks and watch items

1. **Concurrent worktree sessions**: stage only owned files; never
   `git add -A` (stray changes present, Task 0.3).
2. **Generation cost/quotas**: worker now runs unattended with live keys;
   OpenRouter/OpenAI failures surface as `failed` jobs in "My Requests", and
   Stage-0 quota exhaustion (seen 2026-07-04 as 429) blocks moderation:
   verify both keys funded before Task 4.1.
3. **docker-host headroom**: stack budget grows past the reviewed ~1G with
   redis+worker; check free RAM before bring-up (ADR-014 note).
4. **Traefik label drift**: `public-chain@file` must stay auth-free for this
   host; adding Authentik forward-auth would double-authenticate against the
   wrong IdP (README security note).
5. **Kid-surface authority**: R1 knowingly ships the kid UI on the guardian
   token; the new request endpoint must still validate profile_id belongs to
   the token's family (IDOR pattern already established in `api/reading.py`).
