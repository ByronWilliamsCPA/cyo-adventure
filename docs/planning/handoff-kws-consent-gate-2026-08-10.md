---
purpose: Hand the KWS parental-verification gate to a reviewer, separating what is built and testable from
  what is an owner ruling, an unverified assumption, or still missing, so validation targets the right claims
component: src/cyo_adventure/consent/, src/cyo_adventure/api/consent.py, docs/compliance/,
  docs/planning/adr/adr-018-childrens-privacy-compliance.md
source: session 2026-08-10, worktree .worktrees/kws-test-integration, branch feat/kws-consent-gate
---

# Handoff: the KWS consent gate, what is built and what is not

Written 2026-08-10, at the close of the session that built all four slices of the ADR-018 D1
verification gate. **Merged to `main` on 2026-08-11 as PR #681**; the branch it describes,
`feat/kws-consent-gate`, no longer exists. The feature flag is off in every environment, and production
has never been wired at all.

> **Status note, added 2026-08-11 on merge.** The body below was written before the pull request was
> opened and describes the branch as it stood at `bc6080b5`, seven commits ahead of `main`. Three more
> commits landed before merge: this document itself, `e8e59b81` (closing five CI gates, including the
> repo-root-relative links mkdocs resolves against the doc's own directory), and an ER-diagram
> re-render. The original text is corrected in place only where it would mislead a reader about what is
> true now; where it records *method* rather than state, notably section 6, it is left as written and
> marked. Section 7 remains unanswered.

Read this document as three separate kinds of claim, because they need three different kinds of review:

1. **Built and testable.** Code on the branch, with named tests. Verify by reading and running.
2. **Ruled, not proven.** Positions the owner has taken where the underlying fact is unestablished.
   These are the ones a reviewer is most likely to mistake for findings, and the ones most likely to be
   wrong. Section 4 lists them explicitly.
3. **Missing.** Section 5. Some of it blocks switching the flag on; some of it does not.

## 1. What the gate does, in one paragraph

A guardian cannot create a child profile until an adult identity behind their account has been verified
through Epic's Kids Web Services. `POST /api/v1/consent/kws/start` sends the verification, the parent completes
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
| `e4ce4d3a` | Slice 2: `POST /api/v1/consent/kws/start`, rate limits, open-attempt refusal, `/api/v1/me` state |
| `bd5c6c49` | Slice 3: `needs-verification` AuthStatus, start page, polling wait page |
| `0f420dbd` | Slice 4a: alert when verification deliveries stop arriving |
| `ad72a36e` | Slice 4b: disclose Epic Games as a processor of adult emails |
| `6ca4a569` | Slice 4c: record in ADR-018, the runbook, and the register that the gate is built |
| `bc6080b5` | Close Gate 1 questions Q2 and Q3 |
| `2962b5fc` | This handoff document |
| `e8e59b81` | Close the five CI gates PR #681 failed (docs links, coverage matrix, authz matrix, ER diagram) |
| `313b58b3` | Re-render the ER diagram SVG |

The last three landed after the body below was written, which is why it says seven. Both automated
reviewers reviewed `2962b5fc`, two commits behind the merged tip, so any of their findings about the
five gates `e8e59b81` closed are stale by construction.

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
  only**, and the DPIA residual risk for this stays **High**, as section 2.2 says explicitly.
  **Corrected 2026-08-11:** the sentence that stood here said the enumerated-method question was
  "accepted as a risk under O-122 with expiry at R2." That describes the acceptance recorded
  **2026-08-09**, which O-122 **superseded on 2026-08-10**. The owner ruled that KWS card or debit
  verification is the **sole** VPC method and that no parent is verified until it is active, which is
  scheduled remediation rather than a carried exception; the row's status moved off `accepted exception`
  and reads **`finding open`** today. The typed-name attestation is retained in a different role, as the
  312.5(a)(1) and 312.4 record of what the parent agreed to, not as the method establishing that they
  are a parent. Cite O-122 by date, not by row id alone: the row deliberately preserves superseded
  records in place rather than editing them, so a row-id-only citation resolves to whichever entry the
  reader reaches first.
- **Those first two bullets are load-bearing in series, not in parallel.** Retiring typed-name-as-VPC
  removed the fallback, and O-122 says so in terms: the retirement mechanism named on 2026-08-09 "is now
  the only mechanism, so its unearned status is more consequential, not less," and Gate 1's Q2 is
  promoted "from the highest-value experiment to the **viability gate**." The acceptance in the first
  bullet then answered that viability gate by owner reading rather than by evidence. Read as a list,
  the risk looks distributed across four cautions; read as a chain, the whole VPC posture rests on one
  un-counselled reading of 312.5(b)(2)(ii)'s notification limb with nothing behind it.
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
- **Two staging keys are present but empty, which is not the same as absent** (verified 2026-08-11 in
  `homelab-infra/services/cyo-adventure-staging/stack.env`). `KWS_VERIFICATION_SECRET` is the redirect-leg
  key named above. `KWS_PRODUCT_ID` is **not named anywhere else in this document and should be**: O-124
  records that the webhook's product comparison "is vacuously true today because `KWS_PRODUCT_ID` is unset
  on staging, so a delivery naming any product passes." Both keys go through
  `config.py::_empty_kws_override_means_unset`, so the empty value is handled rather than crashing, and
  the control is simply not in force.
- **Longer-standing**: ADR-018 **D4 is unsatisfied** (`UW-N07`); `data-retention-policy.md` is still
  `status: draft`; one unpushed homelab-infra commit `074c568` sits on
  `docs/kws-staging-config-corrections`. **Corrected 2026-08-11:** the count of stale bare `/v1/` paths
  is **five, not four**, and this document reproduced the same error itself in sections 1 and 2 (every
  router carries `prefix="/api/v1"`). They are `dpia.md:216` (`GET /v1/me`) and
  `coppa-gdpr-remediation-plan.md` lines 300 and 314 (`POST /v1/onboarding`) and 315 and 333
  (`GET /v1/me`). Every `/api/v1/...` path in both files matches a real route and is not stale.

## 6. Branch disposition, and the trap in checking it

> **Superseded as state, retained as method, 2026-08-11.** Both branches named below have merged and no
> longer exist: `feat/kws-consent-gate` as PR #681 and `feat/kws-return-landing` as PR #679 (which landed
> at `ecc38dcf`, 6 files and +223/-7, not the `591d10b8` and 5 files and +212/-7 recorded here). The
> stale-branch table is therefore history. What survives is the two-dot versus three-dot reasoning at the
> end of this section, which is the reason the section exists, and the standing warning about
> `docs/kws-adr-and-diagrams` below, which applies for as long as that branch exists anywhere.

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
PR #675.** Confirmed 2026-08-11 by reading the diff: it deletes `_EPOCH_MILLIS_MIN`/`_EPOCH_MILLIS_MAX`,
the `raw_timestamp` field, the `unit` discriminator, and the `timestamp // 1000` conversion, which is the
whole of #675. Cherry-pick if wanted, never merge wholesale.

**Corrected 2026-08-11: the residual insertions are 63 lines across 9 files, not 44 across 4.** The
four-file list given here omits **`src/cyo_adventure/core/config.py` (13 lines)** and
`tests/unit/test_kws_external_payload.py` (3), so anyone cherry-picking by that list drops the config
changes silently. The full set is `consent/kws_signature.py` (17), `tests/unit/test_kws_signature.py` (13),
`core/config.py` (13), `docs/operations/kws-test-runbook.md` (9), `api/kws_webhook.py` (5),
`tests/unit/test_kws_external_payload.py` (3), `docs/testing/coverage-matrix.md` (1), and one line each in
`pyproject.toml` and `uv.lock`.

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

**Unanswered at merge; answered later the same day against staging, recorded below.** Four things
sharpened the query, and are kept because they are what makes the answer readable rather than a bare
row count:

- **Run it against the staging project, not production.** Production has no `kws_verification` table and
  is several migrations behind `main`, which is an independent confirmation of Gate 3 above and means a
  query there returns "no such table" rather than an answer.
- **Establish that staging is running post-#675 code first.** #675 merged `2026-08-10T20:12:58Z` and an
  image built at `21:51Z`, but staging pins `VERSION=latest`, a mutable tag, so what is deployed depends
  on when the stack was last restarted. Against a pre-#675 container the answer is knowably "no" and
  proves nothing about the fix.
- **Distinguish four outcomes, not two, and do not reach for `status <> 'sent'`.** That predicate was
  correct against a three-value enum and stopped being correct when `20260810190000` added a fourth.
  `send_failed` satisfies it while proving the opposite of what is being asked: per that migration,
  "`send_failed` is our own outbound call giving up and says nothing whatever about the parent." The
  same migration rules out the other shortcut, `resolved_at IS NOT NULL`, because the resolution-pairing
  CHECK forces a `send_failed` row to carry a `resolved_at` too. So:
  - a `verified` or `failed` row **clears the fact**; those statuses are only reachable over the webhook;
  - only `send_failed` means the send never left, so the return path was never exercised and this says
    nothing about #675; it points at the outbound call or the edge, not the webhook;
  - only `sent` means sends left and nothing ever came back, the failure this check exists to detect;
  - **zero rows** is a fourth and different failure: the row is INSERTed and committed before the
    outbound call precisely so this cannot be ambiguous, so an empty table means no send was ever
    recorded rather than that none was accepted.

  Group by `status`. Do **not** reach for `transaction_id` as a discriminator among `sent` rows: it is
  written only by the webhook (`api/kws_webhook.py:342`), so it is collinear with resolution by
  construction and a `sent` row can never carry one. Nothing in this table separates a send that
  reached KWS from one that never did. Expect `kws_environment = 'test'` on staging, which is correct
  there and is deliberately not usable evidence.
- **Resolve the version threshold rather than reading `latest`.** #675 merged as `1c5e26fe` and first
  shipped in tag `v0.74.1`, so a `version` at or above `v0.74.1` establishes the deployed container
  carries the fix. The endpoint is `GET /api/v1/health`, not `/health`: the bare path is served by the
  SPA on the deployed hosts and answers `404` with `index.html`, which is the same anti-oracle the
  production health-probe stub already presents.

### Answered 2026-08-11, against staging

**The fact is cleared.** Staging (`lbhyjcykbamjtghcidgp`) holds seven rows, all `kws_environment = 'test'`:
five `sent` and two `verified`. The decisive one was requested `2026-08-10 22:15:35Z` and resolved
`2026-08-10 22:16:12Z`, a **37-second** webhook round trip. `GET /api/v1/health` reports `0.77.0`.

The proof does not rest on that version reading, which only describes the container running now. It rests
on what #675 fixed: before it, the verifier compared a millisecond `t=` against a seconds clock, so every
genuine delivery measured roughly 56,000 years of skew and **was rejected at the freshness gate before its
HMAC was ever computed**. A `verified` row is therefore only reachable by post-#675 code, and its existence
is itself the deployment evidence. That is a stronger argument than any restart timeline, which staging's
mutable `latest` tag cannot supply anyway.

Two observations that follow from the same query, neither of which the section 7 question asked for:

- **The five `sent` rows are a live stuck-delivery alarm on a timer.** The newest is `2026-08-10 20:54:48Z`
  and `_KWS_STUCK_AFTER` is 24h, so the health check flips to degraded around `2026-08-11 20:54Z` unless
  the rows are resolved. Section 3.2 anticipates exactly this and says to resolve the rows rather than
  widen the rule. What to resolve them *to* is an owner call, not a mechanical one: `20260810190000`
  explicitly refuses to stamp old `sent` rows as `send_failed`, on the grounds that whether those emails
  went out is genuinely unknown and inventing the status would assert something never observed.
- **`location` is NULL on all seven rows, and that is expected, not a defect.** The column and its writer
  arrived with #681 (merged 2026-08-11), and no attempt has been made since. It is worth re-checking on
  the first post-#681 send, because a NULL there would be a real gap.
