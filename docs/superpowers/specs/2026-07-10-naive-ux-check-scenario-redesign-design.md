---
schema_type: common
title: "Naive-UX-Check Scenario Redesign: Auth-Gate Tier and Staging Fixtures"
status: draft
owner: core-maintainer
purpose: "Redesign the naive-ux-check Track B scenario set around the app's auth-gating behavior, running against the delivered Supabase staging environment and its seeded fixtures."
tags:
  - testing
  - planning
  - project
---

> **Revised 2026-07-11.** First written 2026-07-10, before two workstreams landed.
> The UX workstream (PRs #198, #206, #209, #210) fixed the auth-gate findings that
> motivated this spec: [issue #196](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/196)
> is closed, and the kid surfaces now show differentiated gate states instead of one
> generic error. The Supabase environments workstream (PRs #199, #201, #205;
> ADR-012) delivered the staging environment that Section C originally designed as
> hand-provisioned future work. This revision reframes the fixed findings as
> history, rewrites Section C to describe the staging environment that now exists,
> and keeps the still-undone core: the `K0`/`G0`/`A0` scenario tier and the skill's
> repoint to staging. Tracked in
> [issue #204](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/204).

## Problem

Two live-site runs of the `naive-ux-check` skill (K1, K2; 2026-07-10) both hit an
identical dead-end: a first-time kid persona clicking "Kids -- Start reading" landed
on a generic "Oops, we hit a snag" error instead of any usable next step, and the
same failure reproduced exactly on the second, differently-framed scenario.

Investigation (`frontend/src/kid/ProfilePickerPage.tsx`)
showed this was not a bug in the sense of "the backend is broken." The kid picker has
no session of its own; it rides on whatever `auth_token` a guardian's Supabase
sign-in already placed in that browser's `localStorage`
(`frontend/src/hooks/useApi.ts`). A fresh browser with no
guardian ever signed in correctly cannot load family data: for a kids' app, that's
the intended protection, not a defect. Filed as
[issue #196](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/196), since
**fixed and closed** by PR #198: `classifyApiError`
(`frontend/src/hooks/classifyApiError.ts`) now maps
401, 403, and transient failures separately, and the kid surfaces render
differentiated gates ("Ask a grown-up to help" on the picker, "Time to find your
grown-up" on the library, distinct empty states, with "Oops, we hit a snag" reserved
for genuine transient errors).

The remaining gaps are:

1. The 14-scenario Track B set
   (`docs/planning/naive-user-ux-testing-design.md`, Section 6) has no scenario at
   all for the sign-in/auth-gate step itself. `K1`-`K4` assume a kid already has a
   usable session; `G1`-`G7` and `A1`-`A3` all start from "sign in and..." as a
   given, so sign-in discoverability has never been tested. The differentiated gate
   copy shipped in PR #198 has therefore never been exercised by a naive-user run:
   nothing confirms it actually reads as a friendly invitation rather than an error.
2. Credentialed scenarios have so far meant using real production accounts
   (`byronawilliams@`/`byron.a.williams@`) against `cyo.williamshome.family`, which
   risks mixing test noise into real family data once the gate scenarios and K1-K4's
   real precondition require an actual sign-in. The staging environment with seeded
   test credentials now exists (Section C), but the skill does not yet target it.

## Goals

1. Add scenarios that test the auth-gate itself (kid-side and sign-in-side), so gate
   quality is a first-class, correctly-scored part of the naive-user suite instead of
   an unplanned dead-end, and so the differentiated gates shipped in PR #198 get
   their first naive-user verification.
2. Give K1-K4 a real, documented precondition (a guardian has signed in on this
   device) instead of silently assuming a session that doesn't exist.
3. Repoint the skill at the dedicated staging environment (now live and seeded, see
   Section C), so naive-ux-check runs (including ones that submit, approve, or
   decline content) never touch real family data or real production infrastructure
   by default.

## Non-goals

- **Not changing the gate UI.** PR #198 shipped the differentiated gate states and
  issue #196 is closed; this spec only tests that UI, it does not redesign it.
- **Not changing the staging environment itself.** The Supabase environments
  pipeline (ADR-012; PRs #199, #201, #205) is delivered and out of scope here.
  Section C describes it as an input this spec consumes, not a deliverable.
- **Not touching Track A** (`frontend/e2e/naive-user/*` Playwright specs). This
  redesign is Track B (Claude-for-Chrome comprehension prompts) only.

## Design

### A. Scenario set changes

Three new scenarios, added in place to the existing persona files (paths below
are relative to the skill's directory, `.claude/skills/naive-ux-check/`):

| ID | File | Scenario | What it reveals |
| --- | --- | --- | --- |
| `K0` | `prompts/kid.md` | Fresh device, no guardian has ever signed in | Whether the differentiated gate shipped in PR #198 ("Ask a grown-up to help", with an "I am a grown-up" path) reads as a clear, friendly invitation rather than a technical error |
| `G0` | `prompts/guardian.md` | Naive persona tries to find and complete sign-in itself | Whether sign-in is discoverable and its feedback (success/failure) is clear, tested for the first time |
| `A0` | `prompts/admin.md` | "You were just told you're an admin" framing, applied to sign-in | Whether sign-in itself gives any admin-distinct signal, mirroring A1's post-login framing |

`K1`-`K4` keep their existing persona text unchanged. Each gains one **operator-only**
instruction line, outside the persona prompt itself: "Before pasting this prompt,
sign in as the seeded test guardian (`SEED_GUARDIAN_EMAIL`, default
`cyo-test-guardian@example.com`) in this browser tab first." A real device gets
activated by a guardian signing in once; the human running the extension performs
that step, not the kid persona (a 7-year-old wouldn't know to).

Two consequences of the merged workstreams that the prompt rewrite must absorb:

- **Seeded fixtures change some preconditions.** Against seeded staging (Section C),
  the family already has a "Test Reader" profile with two published stories, so any
  scenario whose framing assumes a zero state (a no-profiles cold start, an empty
  library) no longer matches what a signed-in run will see. Those scenarios' expected
  observations get updated to the seeded fixture state; if a zero-state reading
  ("No profiles yet", "No books yet") is still worth testing, it needs an
  operator-arranged empty family, not the default seeded one, and the prompt must
  say so.
- **Expected observations need re-verification against the refreshed UI.** PRs #206
  (guardian console visual refresh), #209 (R2 cover art), and #210 (illustrated
  avatar presets) restyled the surfaces `G1`-`G7` and `K1`-`K4` walk through. The
  rewrite pass re-checks each scenario's expected observations against the current
  UI rather than trusting descriptions written before those PRs.

Scenario count goes from 14 to 17. IDs are additive (`K0`/`G0`/`A0` as new
zero-indexed entries), so the `K1`/`K2` IDs the 2026-07-10 findings were recorded
under keep their meaning without renumbering. (No report file from those runs is
committed; `docs/qa/naive-ux-reports/` currently holds only a `.gitkeep`, and
future run reports there will use the extended numbering.)

### B. Skill operational changes (`.claude/skills/naive-ux-check/SKILL.md`)

- **Run order**: `K0` before `K1`-`K4`, `G0` before `G1`-`G7`, `A0` before `A1`-`A3`.
  Full order: `K0`-`K4`, `G0`-`G7`, `A0`-`A3`. Each of `K0`/`G0`/`A0` must start
  from a fresh browser context (a new browser profile, or site data and
  `localStorage` cleared for the target origin) so it actually observes the
  signed-out state: `K1`-`K4`'s operator sign-in leaves a live session in the
  browser, and running `G0` or `A0` in that same context would silently skip the
  auth gate those scenarios exist to test.
- **Target URL default** changes from "local dev, typically `http://localhost:5173`"
  to "local dev, pointed at the staging Supabase project via `.env.staging`" (the
  committed `.env.staging.example` documents the required variables; see Section C).
  Live production stops being an equally-weighted default; it becomes an explicit,
  occasional, deliberate choice the operator states up front, still subject to the
  existing rule that mutating personas never target it.
- **Verdict rubric** gains one rule: for `K0`/`G0`/`A0` specifically, a clear,
  friendly, correctly-functioning auth gate (a real invitation to sign in / find a
  grown-up, not an error page or a retry loop) is a **pass**. A gate that's
  confusing, mislabeled, or broken (like the pre-#198 "Oops, we hit a snag" loop the
  2026-07-10 runs found) is still dead-end/friction under the existing rules.
- **Step 1** (asking for a target URL) gets a short explanation of why staging is now
  the default: dedicated test credentials live there; live production has no account
  naive-ux-check should use.

### C. Test fixtures and the staging environment (delivered; an input, not a deliverable)

This section originally designed a hand-provisioned Supabase project with dashboard
setup and Alembic migrations. That design was superseded and then delivered, in
better shape, by the Supabase environments workstream
(`2026-07-10-supabase-environments-pipeline-design.md` in this directory; ADR-012;
PRs #199, #201, #205). As of 2026-07-11, staging is live, migrated, seeded, and
sign-in verified (issue #204's Gate C). What the scenarios can rely on:

- **A real Supabase staging project** whose schema is managed by Supabase CLI SQL
  migrations (`supabase/migrations/`; Alembic is retired per ADR-012). Merges to
  `main` touching migrations auto-promote to staging
  (`.github/workflows/supabase-staging.yml`); production promotion is a separate,
  approval-gated manual dispatch (`supabase-production.yml`).
- **Seeded fixtures** from the idempotent `scripts/seed_staging.py`, which refuses
  to run unless `ENVIRONMENT=staging`: a dedicated test guardian and test admin
  (Supabase Auth users; emails from `SEED_GUARDIAN_EMAIL`/`SEED_ADMIN_EMAIL`,
  passwords supplied only via shell environment), a "Test Family", a "Test Reader"
  child profile (age-band `5-8`, matching the "7-year-old" framing `K1`-`K4` already
  use), and two published, assigned fixture stories, so `K1`-`K4` have something
  real to read or request against once the gate is passed.
- **Env plumbing**: the committed `.env.staging.example` documents the full variable
  surface (`ENVIRONMENT`, `CYO_ADVENTURE_DATABASE_URL`, `SUPABASE_URL`,
  `SUPABASE_SERVICE_KEY`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`,
  seed-account emails, optional R2 cover-storage variables); the real `.env.staging`
  stays git-ignored. No plaintext password goes into git, even for throwaway test
  accounts.
- **Generation provider**: staging runs the local **Ollama** provider
  (`generation_provider=ollama` via `.env.staging`; the code default is `mock` and
  production uses `openrouter`, see `core/config.py`), so repeated `K2`/`K3` and
  future mutating reruns don't place real, billed LLM calls.

### D. Documentation updates

- `docs/planning/naive-user-ux-testing-design.md` gets a new dated status-banner
  entry (matching its existing amendment pattern) summarizing this change and
  pointing at this spec. Section 6.1's scenario table gets three new rows (`K0`,
  `G0`, `A0`).
- `.claude/skills/naive-ux-check/SKILL.md`'s header comment ("14 scenarios total:
  K1-K4, G1-G7, A1-A3") updates to 17 scenarios / `K0`-`K4`, `G0`-`G7`, `A0`-`A3`,
  plus the Section B changes.
- A CHANGELOG entry, per the repo's changelog gate.

## Follow-ups (both resolved since the original draft)

1. ~~Update issue #196's framing~~ Overtaken by events: PR #198 shipped the
   differentiated gate UI and
   [#196](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/196) is closed
   as completed. No framing correction is needed.
2. ~~File an issue for Supabase's canonical environment pattern~~ Delivered rather
   than filed: the Supabase environments workstream adopted CLI-driven migrations
   with GitHub Actions promotion (ADR-012; PRs #199, #201, #205).

The live tracking issue for this spec's own remaining work is
[issue #204](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/204), which
records the Section C supersession and gated the scenario redesign on Gate C
(completed 2026-07-11: the seeded guardian signed in against a locally-served
frontend pointed at staging and saw the Test Reader profile and fixture stories).

## Testing

- Run `K0`-`K4` against the live staging environment. `K0` should now score a pass
  by observing the differentiated gate from PR #198 ("Ask a grown-up to help" with a
  working "I am a grown-up" path), not the pre-#198 "Oops, we hit a snag" dead-end
  the 2026-07-10 runs found; if `K0` still reads as an error to a naive user, that
  is a genuinely new finding against the new copy.
- `G0`/`A0` get their first real run against the seeded test guardian/admin
  accounts.
- No automated test coverage changes; this is a skill/prompt/documentation change,
  not application code.
