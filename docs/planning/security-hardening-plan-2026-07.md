---
schema_type: planning
title: "Security Hardening Plan: Red-Team Design-Gap Remediation (2026-07)"
description: "Turns the 2026-07-10 adversarial red-team design review into PR-sized, trackable
  remediation workstreams: per-finding gap, attack, affected files, fix approach, and acceptance
  criteria, sequenced by severity and dependency."
tags:
  - planning
  - security
  - child-safety
  - privacy
  - technical-debt
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Close every design gap the red-team review confirmed, grouped into reviewable PR-sized
  workstreams so the fail-open auth default and the child-safety delivery path land first and the
  remaining hardening backlog lands in priority order."
component: Strategy
source: "docs/security/red-team-design-review-2026-07.md (eight-surface adversarial review plus
  completeness critic; every finding independently verified for a reachable path or a blocking
  control). 19 gaps confirmed: 1 critical, 4 high, 8 medium, 5 low, 1 keystone."
---

> **For agentic workers:** implement this plan task-by-task (fresh subagent per task, supervisor
> review between tasks). Steps use checkbox (`- [ ]`) syntax for tracking. Every worker: sign commits
> (`git commit -S`), Conventional Commits, no em-dashes, one branch per workstream, never commit to
> `main`. Each finding ID below (C1, H1-H4, M1-M8, L1-L5, K1) maps 1:1 to the review report so the
> plan and the assessment cross-reference cleanly.

## Goal

Remediate the 19 verified design gaps from the 2026-07-10 red-team review. Land the auth fail-open
default (C1) first because it is a one-variable-away total auth bypass, then the child-safety delivery
cluster (H1, H2, H4, M1, M2, M3) and its keystone (K1), then privacy/retention (H3, M5), then supply
chain, cost, deployment, and inert-control cleanup. Each workstream lands as its own reviewed PR.

## Severity and status map

| ID | Severity | Title | Workstream | Status |
| --- | --- | --- | --- | --- |
| C1 | Critical | `environment` defaults to unverified auth stub (fail-open) | A | [ ] not started |
| H1 | High | No age-band ceiling from approval through delivery | B | [ ] not started |
| H2 | High | AI cover images reach children unmoderated | B | [ ] not started |
| H3 | High | ADR-007 retention purge unimplemented | D | [ ] not started |
| H4 | High | No fail-fast on the no-op `mock` moderation reviewer | C | [ ] not started |
| K1 | Keystone | Children share the guardian token in R1 | E | [ ] not started |
| M1 | Medium | Reading/completion routes bypass the assignment read-gate | B | [ ] not started |
| M2 | Medium | Guardian blob-fetch skips the assignment gate | B | [ ] not started |
| M3 | Medium | Auto-repair skips the deterministic validator gate | B | [ ] not started |
| M4 | Medium | Review-model IDs bypass the provider allowlist | F | [ ] not started |
| M5 | Medium | PII egress guard is display-name-only; birthdate arm dead | D | [ ] not started |
| M6 | Medium | Stranded-job reclaim can double-execute a job | F | [ ] not started |
| M7 | Medium | Family cost cap enforced on only one enqueue path | F | [ ] not started |
| M8 | Medium | Prod Postgres exposed to host; base compose password default | G | [ ] not started |
| L1 | Low | Reading-state anti-forgery replay optional, off by default | H | [ ] not started |
| L2 | Low | Child free-text templated into prompt with no delimiting | H | [ ] not started |
| L3 | Low | `allowed_content_flags` cap completely inert | H | [ ] not started |
| L4 | Low | `reading_level_cap` not enforced at delivery | H | [ ] not started |
| L5 | Low | Health endpoints disclose exact Python/app version | G | [ ] not started |

## Architecture of the work

Eight workstreams (A-H), each a dedicated branch and reviewed PR. Dependency and sequencing:

- **A (auth fail-closed)** gates nothing technically but is the highest risk; land first.
- **B (child-safety delivery)** and **E (identity/keystone)** are the core child-safety cluster. B
  can land independently; E (distinct child tokens) strengthens B's assignment gates and should
  follow close behind. B2 (assignment/read-gate) and E share reasoning about the guardian token, so
  sequence E after B or coordinate.
- **C (moderation fail-fast)** and **D (privacy/retention)** are independent of B/E.
- **F (supply chain + cost)**, **G (deployment)**, **H (integrity + inert controls)** are the
  remaining backlog, independent of each other.

**Conflict rule:** if a worker finds a file already changed by a concurrently-merged PR, rebase the
branch onto `origin/main` before continuing; never force-push over another head without
`--force-with-lease`.

---

## Workstream A: Auth fail-closed (C1)

Branch: `fix/auth-fail-closed`. Priority: P0, land first.

### C1. Invert the `environment` default so an unset value fails closed

- **Severity:** Critical.
- **Design gap.** The switch deciding whether bearer tokens are verified defaults to the insecure
  value. `Settings.environment` defaults to `"local"` (`core/config.py:65-67`); in `local`,
  `_resolve_subject` trusts the token verbatim with no verification (`api/deps.py:279-281`). Every
  misconfig guard is itself gated on `environment != "local"`, so they all no-op when the value
  silently resolves to `local`. The Dockerfile bakes no `ENVIRONMENT`.
- **Attack.** Deploy the image via any path other than the two repo compose files, forget
  `ENVIRONMENT`; the app boots and accepts `Authorization: Bearer <any-subject>` as that user,
  including admin. Total auth bypass, defeating tenant isolation, privilege separation, and content
  approval at once.
- **Affected files.** `core/config.py:65-67`; `api/deps.py:67-76`, `:195`, `:279-281`; `Dockerfile`.
- **Fix approach.** Default `environment` to `production` (or remove the default and require it), so
  an unset or misspelled value fails closed. Bake `ENV ENVIRONMENT=production` into the runtime image
  stage. Make the unverified `local` stub a deliberate opt-in. Add a startup assertion that refuses
  to serve when `environment == "local"` while bound to a non-loopback interface.
- **Acceptance criteria.**
  - [ ] `Settings()` with no env vars set does NOT resolve to `local` (unit test).
  - [ ] Starting the app with `environment` unset and a non-loopback bind raises at startup.
  - [ ] The published image sets `ENVIRONMENT=production` by default.
  - [ ] A test asserts the unverified subject path is unreachable unless `environment == "local"` is
        set explicitly.
  - [ ] `uv run pytest`, `uv run ruff check`, `uv run basedpyright src/` pass.

---

## Workstream B: Child-safety delivery path (H1, H2, M1, M2, M3)

Branch: `fix/child-safety-delivery`. Priority: P1. May split into B1 (band + read-gate), B2 (cover
moderation), B3 (repair re-gate) if the diff is large.

### H1. Enforce an age-band ceiling from approval through assignment to delivery

- **Severity:** High.
- **Design gap.** Age band is stamped from the profile only at request-create (`api/story_requests.py:345`),
  then overwritten by the guardian confirmation with any band at approve
  (`story_requests/service.py:227`; `api/schemas.py:515`). Neither `assign_storybook`
  (`api/assignments.py:190-260`) nor the read gate (`api/library.py:287-296`, `:405-411`) compares the
  story's band to the target profile's band, and Stage-1 moderation is parameterized by the story's
  band (higher band surfaces fewer findings). Per-profile band filtering is deferred to "Phase 4a"
  (`api/library.py:5-8`).
- **Attack.** Approve at `16+`, assign to a `3-5` profile in the same family; no band check, no
  re-moderation; the young child reads content only ever cleared for 16+.
- **Fix approach.** Reject a confirmation band above the requesting profile's band at approve and
  authored-create; reject (or require a logged explicit override) assigning a storybook whose band
  exceeds the target profile's band; add the band comparison to the read gate as defense in depth.
- **Acceptance criteria.**
  - [ ] Approve with a band above the profile's band is rejected (test).
  - [ ] `assign_storybook` rejects a higher-band book for a lower-band profile (test).
  - [ ] Read gate filters/refuses a higher-band book even if a mismatched assignment row exists (test).

### H2. Moderate and human-approve AI cover images before children see them

- **Severity:** High.
- **Design gap.** The safety pipeline operates only on the story text blob. `generate_cover` flips
  `cover_status` from `generating` straight to `ready` and publishes `cover_image_url`
  (`covers/service.py:110-129`); the cover URL renders on the child library card
  (`api/library.py:316-351`). The only safety is the image provider's own refusal plus prose clauses
  in the prompt.
- **Attack.** An admin requests a cover; untrusted title/themes/opening excerpt are templated into
  the image prompt (`covers/prompt.py:78`, `:87-96`); the returned image is shown to every assigned
  child with no human review and no image-moderation verdict.
- **Fix approach.** Run an image-safety check before flipping to `ready`; require explicit human
  approval before `cover_image_url` is exposed to any child card (mirror the text `approved_by`
  gate); audit the decision. Until then, do not surface machine-generated covers to children.
- **Acceptance criteria.**
  - [ ] A cover cannot reach `ready`/child card without passing image moderation AND human approval.
  - [ ] The approval is recorded with an approver id and timestamp.
  - [ ] Test covering the unmoderated/unapproved cover is not returned on the child library card.

### M1. Add the assignment read-gate to reading-state and completion routes

- **Severity:** Medium.
- **Design gap.** `api/reading.py` never consults `StorybookAssignment`: `get_reading_state`,
  `put_reading_state`, and `record_completion` gate only on `authorize_profile` + `authorize_family`
  (`reading.py:75-86`, `:144-151`, `:194-224`, `:305-314`) and resolve `StorybookVersion` by composite
  key alone, accepting unapproved drafts. The `StorybookAssignment` docstring claims it is the "sole
  authority" but only `library.py` enforces it.
- **Attack.** A child calls `PUT /reading-state/{ownProfile}/{withheldStory}` or `POST /completions`
  for a story withheld from them; both succeed (own profile, same family, no assignment check),
  giving progress/completions on a withheld story and letting them enumerate valid ending ids and pin
  state to an unapproved draft.
- **Fix approach.** Add the same `StorybookAssignment` EXISTS gate that `library.py` uses to all three
  reading routes; restrict the accepted version to the approved, published, current version for
  non-admin principals. Update the `StorybookAssignment` docstring to enumerate every gated route.
- **Acceptance criteria.**
  - [ ] All three reading routes 403/404 for a story not assigned to the acting profile (test).
  - [ ] Reading routes reject a non-published / non-current / unapproved version for non-admins (test).

### M2. Enforce the assignment gate on the guardian blob-fetch path

- **Severity:** Medium.
- **Design gap.** `get_storybook_version` enforces the assignment gate only when
  `principal.role == Role.CHILD` (`api/library.py:406-415`); a guardian principal skips it, and R1
  kids use guardian tokens, so the gate never runs for real child readers.
- **Attack.** On the guardian token, list `GET /library?profile_id=B` to learn a withheld book's id,
  then `GET /storybooks/{id}/versions/{v}` returns the full blob because role is not CHILD.
- **Fix approach.** Require a `storybook_assignment` row for an explicit target profile on
  `get_storybook_version` for any non-admin caller, not only `role == CHILD`. (Interacts with E:
  distinct child tokens close the R1 exposure directly.)
- **Acceptance criteria.**
  - [ ] Non-admin blob fetch requires an assignment row for a named target profile (test).

### M3. Re-run the deterministic validator gate on repaired blobs

- **Severity:** Medium.
- **Design gap.** Auto-repair adopts the LLM-revised blob as published content
  (`moderation/pipeline.py:180-182`) after re-running only `_run_all_stages`, which does not call
  `validator.gate.run_gate`, where the age-policy invariants live (PL-15 forbidden ending kinds per
  band, PL-16 content-flag ceilings; `validator/gate.py:118-149`, `validator/policy.py:79-133`). The
  repair prompt asks the model to preserve structure but nothing enforces it.
- **Attack.** A soft-FLAG `3-5` story is repaired; the model also changes an ending to `death` or
  bumps a peril flag; the schema-valid revision publishes because PL-15/PL-16 never re-run.
- **Fix approach.** Re-run `validator.gate.run_gate` on the repaired blob before adopting it; treat a
  gate block on the revision as a hard block (discard repair, route to `needs_revision`).
- **Acceptance criteria.**
  - [ ] A repaired blob that violates PL-15 or PL-16 is not published (test).
  - [ ] A gate block on the revision routes the job to `needs_revision`/auto_reject (test).

---

## Workstream C: Moderation reviewer fail-fast (H4)

Branch: `fix/moderation-reviewer-failfast`. Priority: P1.

### H4. Reject the no-op `mock` reviewer outside local, and alarm on all-fail-safe reports

- **Severity:** High.
- **Design gap.** `review_provider` defaults to `"mock"` (`core/config.py:302`); the only
  review-related guard (`_require_classifier_when_reviewing`, `config.py:460-483`) is exempt when
  `review_provider == "mock"`. With mock, every stage receives `"{}"`, `_parse_verdict` returns the
  fail-safe (`moderation/stages.py:159-205`), Stage 1 can never emit BLOCK, and `auto_reject` is never
  called (`moderation/pipeline.py:205-208`). The automated safety gate produces no blocking signal.
- **Attack.** Deploy with `DATABASE_URL` and OIDC set but `review_provider` left at `mock`; the app
  starts, every story is "reviewed" by the mock into identical fail-safe FLAGs, none auto-rejected,
  humans approve through alarm fatigue, unsafe prose reaches children with the automated layer
  silently off.
- **Affected files.** `core/config.py:302`, `:460-483`; `moderation/review_provider.py:77`;
  `moderation/stages.py:159-205`; `moderation/pipeline.py:205-208`; `moderation/classifiers.py:40-51`.
- **Fix approach.** Add a `Settings` validator that raises when `environment != "local"` and
  `review_provider == "mock"` (mirror `_reject_dev_database_url_outside_local`). Independently, treat
  an all-fail-safe-FLAG report (every node flagged with the parse-failure reason) as a pipeline health
  error so a dead/misconfigured reviewer surfaces as a job failure for retry, not silent human review.
- **Acceptance criteria.**
  - [ ] `Settings()` with `environment=production, review_provider=mock` raises `ConfigurationError` (test).
  - [ ] An all-fail-safe report is flagged as a pipeline health error rather than a normal soft-flag
        outcome (test).

---

## Workstream D: Privacy and retention (H3, M5)

Branch: `fix/privacy-retention`. Priority: P1 (grows daily).

### H3. Implement the ADR-007 retention purge and a parental-deletion path

- **Severity:** High.
- **Design gap.** `generation_job.report` and `story_request.request_text` are durable with no purge
  anywhere; retention exists only as a comment deferring to a nonexistent "Phase 5 pg_cron job"
  (`db/models.py:973-982`). No DELETE path for profiles or requests (`api/profiles.py`).
- **Attack.** A child's real name/address is stored verbatim (retained even for screening-blocked
  rows); generation writes the raw prompt+output to `report` (`generation/worker.py:704`); none is
  ever deleted; a backup leak or legal request exposes years of children's raw PII.
- **Fix approach.** Implement the purge now: a scheduled job (RQ periodic or a checked-in pg_cron
  migration) that nulls `generation_job.report` past 30 days or on publish and scrubs `request_text`
  past its window; add a parental-deletion path for family/profile data.
- **Acceptance criteria.**
  - [ ] A seeded aged `generation_job.report` is nulled by the scheduled job (test).
  - [ ] `report` is nulled when the linked version reaches `published` (test).
  - [ ] A DELETE (or equivalent) path removes a profile's/family's retained free-text (test).

### M5. Replace the exact-name PII guard with a real detector; fix or delete the birthdate arm

- **Severity:** Medium.
- **Design gap.** `assert_prompt_pii_safe` is documented as "the sole chokepoint" for names and
  birthdates (`generation/pii.py:1-10`), but all call sites pass `birthdates=frozenset()` (dead arm),
  the name set is only exact registered `display_name` strings, and raw `request_text` egresses to
  OpenAI/Perspective/the LLM (`story_requests/screening.py:105-111`). `import_story.py:410` passes both
  sets empty (total no-op).
- **Attack.** "a story about me, Tommy Ellison, and my sister Katie at 14 Oak Street" egresses the
  surname, sibling name, and address verbatim when the profile name is "Tommy E."; birthdate
  protection never runs.
- **Fix approach.** Populate birthdates from a real source or delete the dead arm and its docstring
  claim; add a generic PII detector (addresses, phones, emails, broader names) over the free text
  before egress; fix `import_story.py:410` to load family child names; document exactly which child
  data is sent to each third party.
- **Acceptance criteria.**
  - [ ] Free text with an address/phone/non-registered name is blocked or redacted before egress (test).
  - [ ] The birthdate arm either runs against real data or is removed along with its docstring claim.
  - [ ] The COPPA/DPA disclosure lists each third-party recipient of child data.

---

## Workstream E: Identity and the guardian-token keystone (K1)

Branch: `fix/child-identity-separation`. Priority: P1 (root cause of M1/M2/H1 reachability).

### K1. Give children their own principal so role checks actually apply

- **Severity:** Keystone (rated uncertain for direct content impact, but structural).
- **Design gap.** The auth model defines a `child` role, and gates assert "a child must never approve
  its own request" and "guardian-only," but R1 authenticates the kid surface AS the guardian
  (`api/story_requests.py:1-14`; `db/models.py:450`). Under that token every `is_guardian` check
  returns true for a child. `create_story_request` hardcodes `initiator_role='child'`
  (`story_requests.py:346`) regardless of the real principal, so a child self-approval is
  indistinguishable in the audit log from a guardian review.
- **Attack.** A child on the guardian token self-approves their own request, declines a sibling's,
  authors pre-approved requests, and assigns any published family book to any profile. Generation and
  publish stay admin-gated, so this is not a direct unmoderated-content path, but it removes the
  guardian oversight the design relies on and is the shared root of M1, M2, and H1.
- **Fix approach.** Issue children their own child-role principal (or a scoped token), so
  `is_guardian` is false for them; OR gate the approve/decline/assign/authored transitions behind a
  server-checked guardian secret a child session cannot satisfy. At minimum, derive `initiator_role`
  from the authenticated principal (stop hardcoding) and treat approve-by-the-same-actor-that-created
  as an anomaly.
- **Acceptance criteria.**
  - [ ] A child-role principal fails every `is_guardian`/`is_admin` gate (test).
  - [ ] `initiator_role` is derived from the principal, not hardcoded (test).
  - [ ] Self-approval (creator == approver on a child-initiated request) is rejected or flagged (test).

---

## Workstream F: Supply chain and cost (M4, M6, M7)

Branch: `fix/generation-supply-chain-cost`. Priority: P2.

### M4. Validate review-model IDs against the provider allowlist

- **Severity:** Medium.
- **Design gap.** The allowlist is enforced for the generation backend
  (`story_requests/authoring_plan.py:261`) but not for `review_stage1_model`/`review_stage2_model`,
  which are unconstrained `str | None` (`api/schemas.py:614-615`) that flow unchecked into
  `build_review_provider` (`moderation/review_provider.py:86-97`).
- **Attack.** A rogue/careless admin sets `review_stage2_model` to an off-allowlist expensive model;
  every review call is billed against the unvetted model, defeating the billing control on a sibling
  route.
- **Fix approach.** Validate the review-model overrides with `is_enabled_allowlist_pair` at the
  authoring-plan seam before persisting; re-check inside `build_review_provider`.
- **Acceptance criteria.**
  - [ ] An off-allowlist review-model id is rejected at authoring-plan creation (test).

### M6. Make generation enqueue idempotent on the row id

- **Severity:** Medium.
- **Design gap.** The normal enqueue mints an RQ-random id with `unique=False`
  (`generation/queue.py:129-136`); `requeue_stranded_jobs` re-enqueues with `rq_job_id=row_id,
  unique=True`, so the uniqueness collision the `queue.py:151` comment relies on never fires and
  `run_generation_job` can run twice for one row.
- **Attack.** After a >30-min backlog/outage, reclaim double-runs a job: a duplicate billed generation
  that then collides on the `s_{job_id}` primary key, flipping the row to `failed` while the storybook
  persists.
- **Fix approach.** Enqueue with `rq_job_id=job_id, unique=True` on both paths, or take a row-level
  lock and re-check status before any provider work; fix the misleading comment.
- **Acceptance criteria.**
  - [ ] A second dispatch of the same job_id is a cheap no-op, not a duplicate paid run (test).

### M7. Enforce the family active-job cap on every enqueue path

- **Severity:** Medium.
- **Design gap.** `MAX_ACTIVE_JOBS_PER_FAMILY` is checked only in `enqueue_concept_generation`; the
  production authoring-plan path creates the `GenerationJob` directly with no family cap
  (`story_requests/authoring_plan.py:421-475`).
- **Fix approach.** Enforce the family active-job cap (and any global concurrency budget) in the shared
  enqueue helper so every path is throttled identically.
- **Acceptance criteria.**
  - [ ] The authoring-plan path is subject to the same family cap as `/concepts` (test).

---

## Workstream G: Deployment posture (M8, L5)

Branch: `fix/deployment-posture`. Priority: P2.

### M8. Stop publishing prod Postgres to the host; remove the base password default

- **Severity:** Medium.
- **Design gap.** Base compose publishes db to the host (`docker-compose.yml:146-147`) and defaults
  `POSTGRES_PASSWORD` to `password` (`:137`); the prod override never removes the `ports:` mapping, and
  Compose appends port sequences, so prod still exposes Postgres on the host (iptables DNAT bypasses
  host firewalls).
- **Fix approach.** In the prod override, drop the db host `ports:` mapping (internal-network only) or
  bind to `127.0.0.1`; remove the `password` default so a missing `DB_PASSWORD` fails fast everywhere.
- **Acceptance criteria.**
  - [ ] Merged prod compose does not publish 5432 on a host interface (verify merged config).
  - [ ] Missing `DB_PASSWORD` fails fast in every compose path.

### L5. Drop version fingerprinting from public health probes

- **Severity:** Low.
- **Design gap.** `HealthStatus` exposes `python_version` and `version` on unauthenticated
  `/health/live`, `/health/startup`, `/health` (`api/health.py:46-47`).
- **Fix approach.** Drop `python_version` (and ideally `version`) from public probe payloads, or gate
  detailed diagnostics behind an internal/authenticated route; return a bare status to anonymous
  callers.
- **Acceptance criteria.**
  - [ ] Public probes return no interpreter/app version (test).

---

## Workstream H: Integrity and inert controls (L1, L2, L3, L4)

Branch: `fix/integrity-and-inert-controls`. Priority: P3.

### L1. Make reading-state anti-forgery replay mandatory

- **Severity:** Low.
- **Design gap.** Full engine replay runs only when `choice_path` is provided
  (`player/replay.py:60-68`), which defaults to `None` (`api/schemas.py:70`); the default path runs only
  the structural floor, which accepts a client-forged state pointing at any node with any in-bounds
  vars. The `replay.py:112-120` comment claiming the floor closes the valid-but-unreached-node forgery
  is false for the default path.
- **Fix approach.** Make `choice_path` mandatory and always run the full deterministic replay; correct
  the comment.
- **Acceptance criteria.**
  - [ ] A reading-state write without a legal `choice_path` is rejected (test).
  - [ ] A state whose reachability is unverified is not trusted for gating decisions.

### L2. Frame child free-text as untrusted content in generation prompts

- **Severity:** Low.
- **Design gap.** `request_text` is serialized wholesale into the structure and fill prompts
  (`generation/prompts.py:305`, `:377`) with no untrusted-content delimiter or instruction, contrary to
  the project's OWASP LLM01 directive.
- **Fix approach.** Wrap `premise`/`theme_brief` in a uniquely-delimited untrusted-content block with a
  system instruction that its contents are story input, never instructions.
- **Acceptance criteria.**
  - [ ] Prompts render the premise inside an explicit untrusted-content delimiter (test/snapshot).

### L3. Implement or remove `allowed_content_flags`

- **Severity:** Low.
- **Design gap.** `ChildProfile.allowed_content_flags` (`db/models.py:184-186`) is documented as a
  content cap but is dead: not settable via the profile API, in no `ProfileView`, and read by no
  delivery path.
- **Fix approach.** Implement end-to-end (expose on the profile API; enforce at assignment/read by
  comparing book `metadata.content_flags` to the cap) or remove the column and its "content caps" claim.
- **Acceptance criteria.**
  - [ ] The cap is either enforced at delivery (test) or removed with its docstring claim.

### L4. Enforce `reading_level_cap` at delivery or label it generation-only

- **Severity:** Low.
- **Design gap.** `reading_level_cap` is guardian-settable and consumed only when building a generation
  brief (`story_requests/brief.py:94-95`); never enforced at assignment or read (Phase 4a deferral).
- **Fix approach.** Enforce at assignment time and/or filter in library and version fetch; if deferral
  is intended, label the field generation-only in the UI.
- **Acceptance criteria.**
  - [ ] A book above a lowered cap is filtered/refused at delivery (test), OR the field is documented
        as generation-only and the UI reflects it.

---

## Verification and exit criteria

- [ ] Every workstream lands as its own reviewed, signed PR against `main`.
- [ ] Each finding's acceptance-criteria tests are added and pass.
- [ ] The status map above is updated to `done` per finding as PRs merge.
- [ ] `uv run pytest --cov=src --cov-fail-under=80`, `uv run ruff check .`, `uv run basedpyright src/`
      pass on every PR.
- [ ] The review report (`docs/security/red-team-design-review-2026-07.md`) is annotated with the
      remediating PR per finding on completion.

## Dismissed during verification (no work planned)

Raised by a finder but refuted on re-check, recorded for traceability: in-memory rate limiter design
(tech debt, not a safety gap); condition-evaluator recursion (bounded, not reachable); cover-provider
PII egress (folded into M5); dormant cross-book series validator (no runtime path today); the
`GET /generation-jobs/{id}` report field (verified family-scoped, not cross-tenant); missing
`TrustedHostMiddleware`/HTTPS in `app.py` (reasonably delegated to the reverse proxy; a defense-in-depth
note, not a workstream); shared unbounded RQ queue as the sole throttle (overlaps M6/M7, no separate
workstream). Seven candidates dismissed in total.
