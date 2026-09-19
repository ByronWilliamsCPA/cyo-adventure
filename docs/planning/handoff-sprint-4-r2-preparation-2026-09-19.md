---
purpose: Hand the Sprint 4 work (start the long-lead R2 and R3 items and cap the planning corpus) to the implementing
  session, separating owner and counsel decisions from engineering spikes and from mechanical follow-through
component: docs/planning/adr/adr-018-childrens-privacy-compliance.md, src/cyo_adventure/consent/, docs/planning/PROJECT-PLAN.md
  (Phases 6 to 9), src/cyo_adventure/moderation/classifiers.py, docs/planning/unscheduled-work-register.md
source: project review session 2026-09-19 (branch claude/project-review-critical-path-kbz6zn); one of four sprint handoffs
---

# Handoff: Sprint 4, R2 preparation

Written 2026-09-19 from a read-only review of `main` at `2ca65e1` (v0.89.0), production, GitHub, and the
planning corpus. A plan for work not yet started; re-probe before acting.

**Prerequisite: Sprint 3's `M5.1` sign-off row exists**, or the owner has explicitly chosen to start R2
work in parallel. One item below does not wait for anything: sending the ADR-018 counsel package is the
longest lead on the whole path to public launch and has been "should start now" in `roadmap.md` since
2026-07-16.

Sibling handoffs: Sprint 1 (restore production), Sprint 2 (catalog unblock), Sprint 3 (R1 full
sign-off), all dated 2026-09-19.

## Goal / Intent

R2 is TestFlight iOS (Phases 6 and 8); R3 is the public App Store launch (Phases 7 and 9). Phase 6's
guardian-side substance is built; Phase 8 has no code ("zero Capacitor/entitlement code anywhere",
confirmed 2026-07-20) and Phase 9 has no hosted infrastructure. Two things gate R3 on calendar time
rather than engineering effort: external counsel closing ADR-018 D1 to D5, and the Google Perspective API
sunset on 2026-12-31, which the live gate no longer depends on but the calibration baseline script does. Sprint 4 starts every long-lead item,
answers the cheap feasibility questions with throwaway spikes, and reduces the planning corpus to a size
one person can keep true.

## Current State

**Children's privacy (ADR-018, status Proposed):**

- KWS parent verification is built and deployed to staging against the KWS **Test** environment only;
  the feature flag is off everywhere and production has never been wired (`handoff-kws-consent-gate-2026-08-10.md`).
  A Test verification is not a valid VPC.
- Owner ruling 2026-08-10: KWS card or debit verification is the sole VPC method, and no parent is
  verified until it is active. The typed-name attestation currently shipped is carried as residual risk
  (register row O-122, "High", expiring at R2), with adverse FTC authority noted in D1.
- Counsel package for D1 to D5 is prepared and unsent (`UW-M03`, status `decision`, owner). Questions 1A
  and 1B remain open. ADR-016 and ADR-023 legs are not packaged.
- `UW-J24` and `UW-J25` (both `decision`): whether self-signup stays behind the admin gate, and whether
  KWS verification is on. The register notes the unsafe pairing is not obvious from either decision alone.
- Processor gaps: OpenRouter DPA unexecuted (`UW-M04`); processor rows for Modal, Bedrock, Azure, Vertex
  missing (`UW-A15`, blocks P7-12); OpenAI Moderation and Perspective retention terms for child-typed
  text unverified (D5). Starting a KWS check discloses the adult's email to Epic with no executed DPA
  (register O-125).
- Launch geography is US-only by owner decision (D3).

**Phase 8 (iOS shell and subscriptions):** not started. `PROJECT-PLAN.md` rows P8-01 to P8-09. P8-04
names the decision RevenueCat versus direct StoreKit 2 plus App Store Server API, "at phase start".
P8-03's row still says "Alembic migrations"; Alembic was retired by ADR-012, a doc drift to fix.

**Phase 9 (public catalog, hosted infra, launch):** not started. P9-01 proposes a `catalog_published`
state; `visibility='catalog'` already exists on `storybook` and Sprint 2 promotes into it, so P9-01 may be
partly superseded (`[VERIFY]` against `publishing/state_machine.py`). P9-03 hosted infrastructure
evaluation is time-boxed but unscheduled. P9-04 (`review_provider != "mock"` enforced in production
config) is worth verifying now rather than at Phase 9, given the mock-reviewer defects of late August.

**Perspective sunset:** `roadmap.md`'s Risk Register still reads "Google Perspective API sunset
(2026-12-31), classifiers.py has no live date gate", probability High. The code has moved past that row:
`moderation/classifiers.py`'s module docstring records that Perspective "was retired as a Stage-0 signal
source (ratified sunset)" and that nothing in the module produces a new Perspective finding. What remains
exposed to the date is `scripts/capture_stage0_baseline.py`, which probes Perspective directly to freeze
raw scores before the sunset, and `Source.PERSPECTIVE` kept on the enum so historical reports still
deserialize. The risk row is a stale negative: a risk recorded as open that the code has closed.

**Planning corpus:** about 805 register rows across 14 clusters, of which cluster C is 478 rows that
mirror the 391 still-open rows of a 763-row authoring lessons log. Status counts: 584 `unscheduled`, 125
`done`, 54 `decision`, 24 `blocked`, 18 `verify`. `docs/planning/` holds roughly 130 documents.

## What Was Done

No code changed. State established from ADR-008, ADR-009, ADR-018 (read in full by a subagent),
`handoff-kws-consent-gate-2026-08-10.md`, `handoff-adr-018-counsel-engagement-2026-08-06.md`,
`privacy-model.md`, `PROJECT-PLAN.md` Phases 6 to 9, the register rows named above, `SECURITY.md`, and
`src/cyo_adventure/consent/` plus `api/kws_webhook.py` and `api/kws_redirect.py`.

## What Remains

Ordered by lead time, longest first. Goal, then mechanism where obvious or flagged.

1. **Send the ADR-018 counsel package.** Goal: counsel is engaged on D1 to D5 with a return date. Owner
   action (`UW-M03`); engineering's part is to refresh the package against `main` (the KWS build and the
   2026-08-10 ruling postdate the 2026-08-06 handoff) and to add the unresolved counterparty entity and
   DPA questions for Epic (O-125). Fable-tier for the memo: framing options and residual risk for a
   legal reader without asserting legal conclusions.

2. **Decide the KWS production posture as one decision, not three.** Goal: `UW-J24`, `UW-J25`, and the
   card-only VPC ruling are resolved together so the unsafe pairing (self-signup open while KWS is off)
   cannot occur. Engineering supplies the state table: for each pairing of {self-signup gated, open} and
   {KWS off, Test, production}, what a stranger can do today. Owner rules. Then, if production KWS is
   chosen: wire the production environment, execute the DPA first, and turn the flag on behind the
   existing delivery-health alert (`kws-delivery-health`, runbook 7.1).

3. **Close out the Perspective sunset.** Goal: nothing in the repository depends on the Perspective API
   after 2026-12-31, and the plan says so. Verify with `grep -rn PERSPECTIVE src scripts` that the only
   live caller is `scripts/capture_stage0_baseline.py`; decide whether the baseline capture it exists for
   (`RS-CAL3`, `UW-C476`) will run before the sunset or be re-scoped to OpenAI-only, and record that in
   `UW-C476`; then correct the `roadmap.md` Risk Register row from "no live date gate" to the retired
   state with the PR that retired it as `Ref`. Sonnet-suitable; no gate change, so no lessons row unless
   the calibration scope changes.

4. **Processor and DPA follow-through.** Goal: every provider leg that can see child-typed text or an
   adult email has a processor row and an executed or explicitly declined DPA. `UW-M04` (OpenRouter),
   `UW-A15` (Modal, Bedrock, Azure, Vertex rows), D5 (OpenAI Moderation, Perspective retention terms).
   Sonnet-suitable for the rows and the verification checklist; owner signs.

5. **Phase 8 spikes, one question each (throwaway).** Goal: answer the questions that decide the Phase 8
   plan before committing to it.
   - Does the existing PWA run inside a Capacitor shell with Supabase auth via `signInWithIdToken` and
     the native Apple sign-in sheet (P8-01, P6-05 remainder)? Build, sign in, open the kid library,
     discard.
   - RevenueCat versus direct StoreKit 2 (P8-04): a one-page comparison against this codebase's
     entitlement needs (P8-03, P8-05), not a generic one. Owner decides.
   - Fix the P8-03 "Alembic" wording to Supabase CLI migrations (ADR-012).

6. **Phase 9 pre-checks that are cheap now.** Goal: no Phase 9 row is discovered to be already built or
   already broken at Phase 9 start. Verify P9-01 against the existing `visibility='catalog'` path and
   mark superseded or narrowed; verify P9-04 by reading `core/config.py`'s production validation for
   `review_provider`; schedule P9-03's time-boxed hosting evaluation with an explicit homelab exit
   criterion (ADR-004 is homelab-first, ADR-008 names Azure Container Apps for the public tier).

7. **Security items named as buildable in `SECURITY.md` and the compliance survey.** Goal: close the two
   remote-remedy gaps before strangers can sign up: server-side session revocation on password reset
   (a backend endpoint using Supabase admin sign-out with scope) and a remote sign-out for a lost device.
   Also `UW-E16`: the dev/test auth stub in `api/deps.py` (`_extract_subject`) is live, guarded only by
   unset OIDC environment variables; make its presence in a production build a startup failure.

8. **Cap the planning corpus.** Goal: the register and lessons log stay true with one maintainer.
   Proposal for owner decision, Fable-tier to design: stop mirroring every open lesson as a `UW-C` row
   and instead link the lessons log to phases directly, or archive lessons older than a set age that no
   scheduled work cites; require every planning document to carry a `Status` line and archive those
   marked superseded into a subfolder excluded from `mkdocs.yml` nav. The linkage scripts
   (`check_work_linkage.py`, `check_lessons_log.py`) must keep passing under whatever rule is chosen;
   change the scripts with the rule, not after.

## Key Decisions

- **Counsel first, in parallel with everything.** It is the only item whose lead time is measured in
  months and controlled by someone else.
- **Decide KWS posture as a state table, not three rulings.** Chosen because the register itself
  records that the unsafe combination is invisible from any single decision.
- **Correct stale risk rows rather than act on them.** The Perspective row describes a gate the code no
  longer has; acting on the row would have built a date gate for a retired axis.
- **Spikes are throwaway.** The Capacitor question is answered by a build that is deleted, so the real
  Phase 8 plan is written against evidence rather than a half-finished shell.

## Dead Ends / Rejected Approaches

- Treating the typed-name attestation as VPC: ADR-018 D1 found it likely matches no FTC-enumerated method
  and records adverse authority; the owner carries it as expiring residual risk, not as a solution.
- EU or UK launch scope: shelved by owner decision D3 (US-only); do not reopen GDPR-K or AADC work in
  this sprint.
- Reviewer distillation (`review-model-distillation-plan.md`): parked at Phase 0 by owner ruling
  2026-08-14 until the deterministic drafting workstream finishes; not a Sprint 4 item.

## User Corrections / Constraints

**Standing constraints:** `CLAUDE.md` (signed commits, Conventional Commits, no em-dash, RAD tagging,
authoring-lessons row for any gate or validator change, template feedback file rules). ADR-018 D3
(US-only), owner ruling 2026-08-10 (card-only VPC), ADR-005 (mandatory human approval), ADR-012
(Supabase CLI migrations, Alembic retired).
**Corrections made this session:** none.

## Files Touched

None by this session. Files the sprint will touch, with their consumers:

- `docs/planning/adr/adr-018-childrens-privacy-compliance.md`: read by counsel via the package; keep
  decision-log dating exact.
- `docs/planning/roadmap.md` Risk Register row for Perspective: read by humans; cite the retiring PR.
- `src/cyo_adventure/api/deps.py` (`_extract_subject`): read on every authenticated request; making the
  stub a production startup failure touches `core/config.py` validation and `tests/unit/test_config.py`.
- `docs/planning/PROJECT-PLAN.md` rows P8-03, P9-01, P9-04: read by humans; the Planning Linkage
  workflow validates the register, not this file.
- `docs/planning/unscheduled-work-register.md` and `plan-manifest.toml`: read by
  `scripts/check_work_linkage.py`; item 8 changes the rules those scripts enforce, so edit the scripts
  and their tests in the same PR.
- `docs/compliance/` processor and disclosure documents (locate with `ls docs/compliance`): served
  publicly per the KWS handoff's disclosure slice; a wrong processor list is a live compliance error.

## How to Resume

1. Send item 1 today: refresh the counsel package against `main` and hand it to the owner to send.
2. Build the KWS posture state table (item 2) from `api/onboarding.py`, `api/profiles.py`,
   `api/admin_profiles.py` gate call sites and `core/config.py` flags; put it to the owner with the three
   linked decisions.
3. Run item 3's grep and correct the `roadmap.md` risk row on the same docs branch as the P8-03 and
   P9-01 wording fixes.
4. Run the Phase 8 Capacitor spike in a scratch directory outside the repo, or in a `.worktrees/` entry
   that is deleted at the end.
5. Batch owner decisions from items 1, 2, 3, 5, and 8 into one message with recommendations.

## Gotchas

- The KWS redirect return is replayable forever by construction (HMAC over `status:external_payload`
  with no timestamp or nonce); only the webhook may write consent state. Do not "fix" the redirect by
  making it write.
- The `kws_verification` row is inserted and committed on its own session before the outbound call
  because KWS will not replay a delivery. Preserve that ordering in any production wiring change.
- `SECURITY.md` records that password reset does not invalidate other-device sessions and that sign-out
  is device-local; both are known and documented, not new findings.
- `PROJECT-PLAN.md` was last verified against code on 2026-07-20; treat every Phase 6 to 9 status cell
  as two months stale.
- Model tier: items 1 (memo framing) and 8 (governance design) are Fable-tier. Items 2 (state table),
  3, 4, 5, 6, and 7 are Sonnet-suitable, with item 7's auth stub
  change reviewed by a stronger model because it touches every authenticated request.

## Next-Session Kickoff Prompt

Resuming work on cyo-adventure. Goal: Sprint 4, start the long-lead R2 and R3 items: send the ADR-018
counsel package, decide the KWS production posture as one state table, close out the retired Perspective
axis in the plan, run throwaway Phase 8 spikes, and propose a cap on the planning corpus.

First, refresh state before acting (this handoff is a snapshot):

```bash
git fetch origin main && git status --short && git log --oneline -5
```

Immediate next action: refresh the counsel package (`handoff-adr-018-counsel-engagement-2026-08-06.md`
plus the 2026-08-10 KWS ruling and the Epic DPA question) and hand it to the owner to send; nothing else
has a longer lead. Then build the KWS posture state table from the gate call sites in `api/onboarding.py`,
`api/profiles.py`, `api/admin_profiles.py` and put `UW-J24`, `UW-J25`, and the card-only VPC ruling to
the owner together.

Hard constraints: signed Conventional Commits, no em-dash, US-only scope (ADR-018 D3), only the KWS
webhook writes consent state, any gate change needs an authoring-lessons row.
Full handoff: docs/planning/handoff-sprint-4-r2-preparation-2026-09-19.md.
