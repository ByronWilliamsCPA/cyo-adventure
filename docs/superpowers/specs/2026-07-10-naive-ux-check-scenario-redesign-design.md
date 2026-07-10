---
schema_type: common
title: "Naive-UX-Check Scenario Redesign: Auth-Gate Tier and Staging Fixtures"
status: draft
owner: core-maintainer
purpose: "Redesign the naive-ux-check Track B scenario set to reflect the app's actual auth-gating behavior, and define the staging environment it needs to run safely."
tags:
  - testing
  - planning
  - project
---

## Problem

Two live-site runs of the `naive-ux-check` skill (K1, K2; 2026-07-10) both hit an
identical dead-end: a first-time kid persona clicking "Kids -- Start reading" landed
on a generic "Oops, we hit a snag" error instead of any usable next step, and the
same failure reproduced exactly on the second, differently-framed scenario.

Investigation ([ProfilePickerPage.tsx](../../../frontend/src/kid/ProfilePickerPage.tsx))
showed this is not a bug in the sense of "the backend is broken." The kid picker has
no session of its own; it rides on whatever `auth_token` a guardian's Supabase
sign-in already placed in that browser's `localStorage`
([useApi.ts](../../../frontend/src/hooks/useApi.ts#L40)). A fresh browser with no
guardian ever signed in correctly cannot load family data: for a kids' app, that's
the intended protection, not a defect. Filed as
[issue #196](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/196).

The actual gaps are:

1. The failure-mode UI doesn't distinguish "no grown-up has signed in on this device
   yet" from a genuine technical failure, and doesn't guide the user toward the fix
   (tracked in #196, not designed here).
2. The 14-scenario Track B set
   (`docs/planning/naive-user-ux-testing-design.md`, Section 6) has no scenario at
   all for the sign-in/auth-gate step itself. `K1`-`K4` assume a kid already has a
   usable session; `G1`-`G7` and `A1`-`A3` all start from "sign in and..." as a
   given, so sign-in discoverability has never been tested.
3. Running credentialed scenarios has so far meant using real production accounts
   (`byronawilliams@`/`byron.a.williams@`) against `cyo.williamshome.family`, which
   risks mixing test noise into real family data once the gate scenarios and K1-K4's
   real precondition require an actual sign-in.

## Goals

1. Add scenarios that test the auth-gate itself (kid-side and sign-in-side), so gate
   quality is a first-class, correctly-scored part of the naive-user suite instead of
   an unplanned dead-end.
2. Give K1-K4 a real, documented precondition (a guardian has signed in on this
   device) instead of silently assuming a session that doesn't exist.
3. Provide a dedicated, disposable staging environment with seeded test credentials,
   so naive-ux-check runs (including ones that submit, approve, or decline content)
   never touch real family data or real production infrastructure by default.

## Non-goals

- **Not fixing #196's UI.** The guardian-login-prompt redesign on
  `ProfilePickerPage.tsx` is separate, tracked work. This spec only updates #196's
  framing (see Follow-ups) to reflect that unauthenticated blocking is by design.
- **Not adopting Supabase's full canonical environment pattern** (CLI-linked local
  dev, `develop`-branch staging, GitHub Actions migration promotion) in this pass.
  Tracked as a separate follow-up issue (see Follow-ups).
- **Not touching Track A** (`frontend/e2e/naive-user/*` Playwright specs). This
  redesign is Track B (Claude-for-Chrome comprehension prompts) only.

## Design

### A. Scenario set changes

Three new scenarios, added in place to the existing persona files:

| ID | File | Scenario | What it reveals |
| --- | --- | --- | --- |
| `K0` | `prompts/kid.md` | Fresh device, no guardian has ever signed in | Whether the gate reads as a clear, friendly "ask a grown-up" invitation rather than a technical error |
| `G0` | `prompts/guardian.md` | Naive persona tries to find and complete sign-in itself | Whether sign-in is discoverable and its feedback (success/failure) is clear, tested for the first time |
| `A0` | `prompts/admin.md` | "You were just told you're an admin" framing, applied to sign-in | Whether sign-in itself gives any admin-distinct signal, mirroring A1's post-login framing |

`K1`-`K4` keep their existing persona text unchanged. Each gains one **operator-only**
instruction line, outside the persona prompt itself: "Before pasting this prompt,
sign in as the test guardian in this browser tab first." A real device gets activated
by a guardian signing in once; the human running the extension performs that step,
not the kid persona (a 7-year-old wouldn't know to).

Scenario count goes from 14 to 17. IDs are additive (`K0`/`G0`/`A0` as new
zero-indexed entries), so `docs/qa/naive-ux-reports/2026-07-10.md`'s existing `K1`/`K2`
entries stay valid without renumbering.

### B. Skill operational changes (`SKILL.md`)

- **Run order**: `K0` before `K1`-`K4`, `G0` before `G1`-`G7`, `A0` before `A1`-`A3`.
  Full order: `K0`-`K4`, `G0`-`G7`, `A0`-`A3`.
- **Target URL default** changes from "local dev, typically `http://localhost:5173`"
  to "local dev, pointed at the staging Supabase project via `.env.staging`" (see
  Section C). Live production stops being an equally-weighted default; it becomes an
  explicit, occasional, deliberate choice the operator states up front, still subject
  to the existing rule that mutating personas never target it.
- **Verdict rubric** gains one rule: for `K0`/`G0`/`A0` specifically, a clear,
  friendly, correctly-functioning auth gate (a real invitation to sign in / find a
  grown-up, not an error page or a retry loop) is a **pass**. A gate that's
  confusing, mislabeled, or broken (today's live "hit a snag" loop) is still
  dead-end/friction under the existing rules.
- **Step 1** (asking for a target URL) gets a short explanation of why staging is now
  the default: dedicated test credentials live there; live production has no account
  naive-ux-check should use.

### C. Test fixtures and the staging environment

- **New Supabase Cloud project**, hand-provisioned via the dashboard (no CLI
  automation in this pass). This step is **user-gated**: creating a Supabase project
  requires an account-level dashboard action that this agent cannot perform (the
  `mcp__supabase__*` tools available are project-scoped, e.g. `apply_migration`,
  `execute_sql`; none of them create a project). The implementation plan needs an
  explicit checkpoint where the user creates the project and hands back its
  connection string and API keys before automated steps (migrations, seeding, env
  file updates) continue. Alembic migrations run against it once to create schema,
  the same as any fresh environment.
- **Seed data**: one dedicated test guardian account, one dedicated test admin
  account, and one seeded child profile (age-band `5-8`, matching the "7-year-old"
  framing `K1`-`K4` already use) under the test guardian's family, so `K1`-`K4` have
  something real to read or request against once the gate is passed.
- **Local dev points at staging** via a new `.env.staging` (git-ignored, real
  values) with a committed `.env.staging.example` template documenting the required
  variables (`DATABASE_URL`, `OIDC_ISSUER`, `OIDC_JWKS_URL`, `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_ANON_KEY`, test-account email placeholders). No plaintext password
  goes into git, even for throwaway test accounts.
- **Generation provider**: staging's backend config defaults to the local
  **Ollama** provider (already supported under `generation/providers/`) rather than a
  paid Anthropic/OpenRouter/Modal key, so repeated `K2`/`K3` and future mutating
  reruns don't place real, billed LLM calls.

### D. Documentation updates

- `docs/planning/naive-user-ux-testing-design.md` gets a new dated status-banner
  entry (matching its existing amendment pattern) summarizing this change and
  pointing at this spec. Section 6.1's scenario table gets three new rows (`K0`,
  `G0`, `A0`).
- `SKILL.md`'s header comment ("14 scenarios total: K1-K4, G1-G7, A1-A3") updates to
  17 scenarios / `K0`-`K4`, `G0`-`G7`, `A0`-`A3`, plus the Section B changes.
- A CHANGELOG entry, per the repo's changelog gate.

## Follow-ups (filed, not designed here)

1. Update [issue #196](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/196)
   with a comment correcting its framing: unauthenticated blocking on the kid picker
   is by design (child protection), not a backend failure to root-cause; the actual
   gap is the failure-mode UI not distinguishing "no grown-up signed in yet" from a
   real error, and not guiding the user toward signing in.
2. File a new issue tracking adoption of Supabase's full canonical environment
   pattern (CLI-linked local dev, `develop`-branch staging project, GitHub Actions
   migration promotion) as later work.

## Testing

- Once the staging environment and seed data exist, re-run `K0`-`K4` against it and
  confirm `K0` now scores as a pass (or a genuinely new, distinct finding if the gate
  itself still has UX problems once #196 lands).
- `G0`/`A0` get their first real run against the test guardian/admin accounts.
- No automated test coverage changes; this is a skill/prompt/documentation and
  environment-provisioning change, not application code.
