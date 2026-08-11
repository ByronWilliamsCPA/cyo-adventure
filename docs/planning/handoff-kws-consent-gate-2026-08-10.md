---
purpose: Hand the KWS parental-verification gate to a reviewer, separating what is built and testable from
  what is an owner ruling, an unverified assumption, or still missing, so validation targets the right claims
component: src/cyo_adventure/consent/, src/cyo_adventure/api/consent.py, docs/compliance/,
  docs/planning/adr/adr-018-childrens-privacy-compliance.md
source: session 2026-08-10, worktree .worktrees/kws-test-integration, branch feat/kws-consent-gate
---

# Handoff: the KWS consent gate, what is built and what is not

Written 2026-08-10, at the close of the session that built all four slices of the ADR-018 D1
verification gate. Everything described here lives on **`feat/kws-consent-gate`**, pushed to origin at
`bc6080b5`, seven commits ahead of `main`. **No pull request has been opened.** The feature flag is off
in every environment, and production has never been wired at all.

Read this document as three separate kinds of claim, because they need three different kinds of review:

1. **Built and testable.** Code on the branch, with named tests. Verify by reading and running.
2. **Ruled, not proven.** Positions the owner has taken where the underlying fact is unestablished.
   These are the ones a reviewer is most likely to mistake for findings, and the ones most likely to be
   wrong. Section 4 lists them explicitly.
3. **Missing.** Section 5. Some of it blocks switching the flag on; some of it does not.

## 1. What the gate does, in one paragraph

A guardian cannot create a child profile until an adult identity behind their account has been verified
through Epic's Kids Web Services. `POST /v1/consent/kws/start` sends the verification, the parent completes
it in Epic's hosted flow, and a KWS webhook resolves the row. Three call sites read the gate
(`src/cyo_adventure/api/profiles.py:346`,
`src/cyo_adventure/api/admin_profiles.py:131`,
`src/cyo_adventure/api/onboarding.py:182`); the frontend routes an unverified guardian
to a start page and then a polling wait page.

**KWS establishes that an adult is an adult. It does not obtain consent.** Epic's own Parent Verification
Service documentation says it is not a COPPA consent mechanism, and the webhook reports no verification
method at all. The 312.4 direct notice and the 312.5 record remain ours: the typed-name attestation we
already collect is retained as the consent *content*, and KWS is the identity check standing in front of
it. A reviewer who reads this branch as "we now have verifiable parental consent" has read it wrong. What
we have is one necessary component whose sufficiency is still the open question in ADR-018 D1.

## 2. What shipped

Seven commits, in order:

| Commit | What it adds |
| --- | --- |
| `155ca613` | Slice 1: gate child-profile creation on a usable KWS verification |
| `e4ce4d3a` | Slice 2: `POST /v1/consent/kws/start`, rate limits, open-attempt refusal, `/v1/me` state |
| `bd5c6c49` | Slice 3: `needs-verification` AuthStatus, start page, polling wait page |
| `0f420dbd` | Slice 4a: alert when verification deliveries stop arriving |
| `ad72a36e` | Slice 4b: disclose Epic Games as a processor of adult emails |
| `6ca4a569` | Slice 4c: record in ADR-018, the runbook, and the register that the gate is built |
| `bc6080b5` | Close Gate 1 questions Q2 and Q3 |

Totals: 57 files, roughly +5,160/-95. The code additions concentrate in
`src/cyo_adventure/consent/service.py` (+370),
`src/cyo_adventure/api/consent.py` (new, +224), and
`src/cyo_adventure/api/health.py` (+124), against
`tests/integration/test_consent_api.py` (new, +543) and
`tests/unit/test_kws_verification_service.py` (+504).

## 3. What to validate independently

These are the four places where a wrong implementation would be invisible in normal use.

### 3.1 The Test-environment refusal is ordered before the query

`usable_verification_id` (`src/cyo_adventure/consent/service.py:300-354`)
refuses a KWS **Test** verification *before the database query runs*, and separately filters on
`kws_environment` so the opposite direction is also closed. The ordering matters: a refusal applied to
query results would still have let a Test row satisfy the gate through any path that did not go through
that filter.

The function keys on the row's own `kws_environment` column, **never on `settings.environment`**. That is
deliberate and not a style choice: staging declares `ENVIRONMENT=production`, so any check written against
the process-level environment reads staging as production and accepts Test evidence there.

Verify with `tests/unit/test_kws_verification_service.py::test_a_test_environment_verification_is_not_usable_by_default`
(line 546), `::test_the_test_refusal_never_reaches_the_database` (line 564), and
`::test_an_accepted_test_verification_is_usable` (line 582), which covers the
`settings.kws_accept_test_evidence` escape hatch.

The same function supplies both the gate's answer and the evidence link recorded against the profile, so
the two cannot disagree. Check that this is still true if you refactor it.

### 3.2 The stuck-delivery alarm is a timestamp comparison, not a count

`src/cyo_adventure/api/health.py` reports degraded when nothing has resolved since the most recent
attempt that is still waiting, once that attempt is older than `_KWS_STUCK_AFTER` (24h). A plain
"N rows stuck" alarm would fire forever on abandoned attempts; a count-and-window conjunction (the
shape this started as) goes blind on a quiet tier, because a blocked inbound leg does not produce the
fresh sends such a rule requires.

Two things to preserve if you touch it. The anchor is the **newest** waiting attempt: anchoring on the
oldest lets one long-abandoned row absorb every later resolution and mask a fresh outage. And a lone
abandoned attempt on a silent tier keeps alarming on purpose, because that state is not
distinguishable from a broken leg on the evidence the table holds; resolve the row rather than
widening the rule.

Verify with `TestVerificationDeliveryHealth` in `tests/unit/test_kws_verification_service.py`,
particularly `::test_an_old_abandoned_row_does_not_mask_a_fresh_outage` and
`::test_an_outage_on_a_quiet_tier_still_alarms`, plus `TestCheckKwsVerification` for what the
published message says. `TestReadinessKwsDoesNotGate` confirms the check is published even with the
flag off and never gates readiness.

### 3.3 No email address is stored

`kws_verification` has **no `parent_email` column under any name**. The email is sent to Epic and not
retained; the row holds an id, the owning `user_id`, the KWS environment, the status, the requested and
resolved timestamps, the vendor's `transaction_id`, the send-time `enabled_methods` snapshot, and
`location`. No language column: the language tag is sent to Epic on the wire but never stored, so it
is a disclosure to describe in `privacy-notice.md`, not a retained field. Both the webhook handler and
the start endpoint log the attempt id rather than the parent email. This is recorded
as activity 12 in [records-of-processing-activities.md](../compliance/records-of-processing-activities.md).

Grep the migration and the model before trusting this paragraph; it is the kind of property that a later
convenience field quietly breaks.

### 3.4 The disclosure set is complete and consistent

Commit `ad72a36e` adds Epic Games as a processor across four documents at once: the privacy notice
(collection row, retention row, and paragraphs separating "who you are" from "what you are agreeing to"),
the DPIA (new section 2.8), the RoPA (activity 12 plus a Section 5 carve-out and a Section 8 open item),
and the processor DPA checklist. Register row **O-125** was opened for the gap this exposes.

Validate these as a set rather than individually. The failure mode is one document being updated and the
others not, which reads as complete from inside any single file.

## 4. Claims that are owner rulings, not established facts

**Flag these to yourself before reviewing, because each one is written in the documents as settled and is
only settled by decision.**

- **Q2's notification limb is accepted, not proven.** 312.5(b)(2)(ii) requires that the card be used in
  connection with a transaction *and* that notification of each discrete transaction reach the primary
  account holder. The structural half is answered by observation: Epic issues a real `PaymentIntent` for
  $0.05 with a `pi_...` id, not a `SetupIntent` and not a zero-amount authorization. The notification half
  is **an owner acceptance recorded in O-122**, taken 2026-08-10, with compensating controls and an expiry
  (reassess if Epic switches to a zero-amount auth, a same-day refund, or a `SetupIntent`, and again at R2).
  It was deliberately **not** sent to counsel. Do not upgrade it to a finding; do not restate it as fact.
- **312.5(b)(2) has no "sign and submit electronically" branch.** Re-verified 2026-08-09 against the eCFR
  renderer API, because the HTML page is bot-blocked. Consent as we collect it today is a **typed name
  only**. The enumerated-method question was withdrawn from counsel and accepted as a risk under O-122 with
  expiry at R2. The DPIA residual risk for this stays **High**, and section 2.2 says so explicitly.
- **"Received" is not "accepted."** A webhook delivery was observed, and its `x-kws-signature` header
  carried Stripe-style `t=`/`v1=` components with `t=` in **milliseconds**. That capture predates PR #675,
  which taught the verifier to accept both units. On the code that was running at the time, that delivery
  would have been rejected with a 401. **Whether any delivery has been accepted since #675 deployed is
  unverified.** The oracle is a `kws_verification` row that has left `sent`, not a log line.
- **O-123 was downgraded, not closed.** Its status moved from `evidence invalid` to `mechanism unproven`.
  That is a description of where it now sits in the pipeline, not a pass.

## 5. What remains

### Blocks switching the flag on

1. **O-125: no DPA with Epic.** Three parts, all open: execute the DPA; determine which Epic entity
   receives the adult's email and under what transfer mechanism; ensure the pre-send disclosure exists
   before the first real send. The check discloses a real adult's email to Epic at the *start* of the flow,
   so this is the gate in front of any production send, not paperwork trailing a live integration. The DPA
   checklist row says so in those words.
2. **Gate 3: production is unwired.** The homelab-infra compose for this service contains **zero** `KWS_`
   references. A production webhook round trip must be *verified*, not assumed, and the memory of how
   staging behaved does not transfer: an edge rule once ate four webhook retries with zero origin POSTs,
   which reads exactly like "the vendor never sent."
3. **PR #679 is unmerged, so the parent's return leg 404s in every browser.** The service worker
   answers *every* navigation on the origin, and `api/kws_redirect.py` renders server-side, so a
   parent who completes Epic's check lands on a 404. This does not block the *mechanism*: only the
   webhook resolves an attempt, and it resolves it regardless. It does block switching the flag on,
   because the last thing a real parent sees at the end of a successful adult check would be a broken
   page, with no signal that the check in fact worked. Note the failure is invisible to every tool we
   would reach for: curl, Postman, and CI have no service worker and all see the page fine.
4. **The flag flip revokes existing accounts.** Every guardian who consented under typed-name-only,
   including the owner's own account, loses child-profile creation until they re-verify. Staging bites
   first. This is the intended behavior per the standing decision that verification sits *before* admin
   approval and that prior consenters must re-verify, but it should be a deliberate act with a
   communication attached, not a surprise.

### Does not block, but is owed

- **Q1 needs run 2**: the `+verified` alias, with an observation window of at least two hours.
- **Operator-side fixes**: the Epic portal Global brand name is "CYO Adventures" and should be
  "CYO Adventure"; the `US Only` Cloudflare rule also gates the redirect return URL, so a travelling or
  VPN-using parent hits a block mid-flow; the redirect leg still needs `KWS_VERIFICATION_SECRET` set and
  the return URL registered in the Control Panel.
- **Longer-standing**: ADR-018 **D4 is unsatisfied** (`UW-N07`); `data-retention-policy.md` is still
  `status: draft`; four stale `/v1/` paths remain in `dpia.md` and `coppa-gdpr-remediation-plan.md`; one
  unpushed homelab-infra commit `074c568` sits on `docs/kws-staging-config-corrections`.

## 6. Branch disposition, and the trap in checking it

**Only two KWS branches exist on origin**: `feat/kws-consent-gate` (`bc6080b5`, the subject of this
document) and `feat/kws-return-landing` (`591d10b8`). Everything else in the list below is local-only.

`feat/kws-return-landing` is the one genuinely additive branch not yet merged: 5 files, +212/-7, carrying
the service-worker `navigateFallbackDenylist` plus the `kws_redirect.py` landing improvements. It already
has its own PR, **#679**, open and green; it needs merging, not opening. The denylist matters beyond KWS:
the service worker currently answers *every* navigation on the origin, so backend-rendered pages 404 in
browsers while curl, Postman, and CI all see them fine. See blocker 3 in Section 5.

Every other local KWS branch is **stale, and a PR from it would revert work already on main**:

| Branch | Two-dot against `origin/main` |
| --- | --- |
| `docs/kws-adr-and-diagrams` | +63 / -1799 |
| `docs/kws-confirmation-email-evidence` | +56 / -450 |
| `docs/kws-test-only-mailbox` | +53 / -435 |
| `feat/kws-test-integration` | +134 / -6710 |
| `feat/public-privacy-and-support-pages` | +132 / -2033 |
| `fix/kws-product-id-absence` | +2 / -12 |
| `fix/kws-webhook-timestamp-milliseconds` | +25 / -202 |

`docs/kws-adr-and-diagrams` is the dangerous one: **a PR from it reverts main's millisecond handling from
PR #675.** Its 44 residual insertion lines span the runbook, `api/kws_webhook.py`, `consent/kws_signature.py`,
and `tests/unit/test_kws_signature.py`, and should be cherry-picked if wanted, never merged wholesale.

**The method matters more than the table.** A three-dot diff (`origin/main...branch`) is structurally
incapable of detecting squash-merged content: after a squash merge the squash commit is not an ancestor of
the branch, so the full branch diff still appears. Three of the branches above were misread as "unmerged
work" on exactly that basis during this session. Use two-dot (`origin/main..branch`), which compares trees.
The inverse trap is what the table shows: on a stale branch, two-dot renders main's newer content as
deletions, which is why large negative numbers here mean "behind," not "removes."

## 7. If you validate only one thing

Confirm that a webhook delivery has been **accepted** since #675 deployed, by finding a `kws_verification`
row that has left the `sent` state. Every other claim in this document is either readable in the diff or
explicitly labelled above as a ruling. That one is the single load-bearing fact that nothing on this branch
proves.
