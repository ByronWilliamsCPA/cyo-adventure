---
schema_type: common
title: "Re-moderating In-Review Books: Widening the Admin Re-Moderation Scope"
status: draft
owner: core-maintainer
purpose: "Extend POST /api/v1/admin/remoderate to accept in_review storybooks so the 17 books stuck at the human gate get fresh automated verdicts, with auto-repair enabled for in_review and the deterministic gate re-derived after any adopted repair."
tags:
  - safety
  - guardrails
  - api
  - specifications
---

## Problem

Seventeen storybooks have sat in `in_review` since 2026-07-21 carrying moderation
reports computed on that date. The review surface
(`api/review_surface.py::_validator_findings`) is read-only by decision, so it
renders a month-old verdict identically to a second-old one. A reviewer opening one
of these books today reads a stale verdict as a current one, and cannot tell.

There is no way to refresh those verdicts. Every whole-book re-derivation path in
the codebase is scoped to `published`:

| Path | Status scope | Refreshes the stored report? |
| --- | --- | --- |
| `api/remoderate.py` | `published` only | Yes, whole book |
| `moderation/rescreen.py` | `published` only | No, by design (no-report-overwrite) |
| `api/node_edit.py` | `in_review`, `needs_revision` | Yes, but one node per call |

`api/remoderate.py:407` rejects any other status with `BusinessLogicError`
(`rule="remoderate_requires_published"`). The books that most need a fresh verdict
are exactly the ones the endpoint refuses.

The prior session's handoff recorded this mechanism as verified for the sprint. It
is verified to exist, not to apply; every call against the seventeen would return
400.

## Goal

Make an `in_review` storybook re-moderatable through the existing admin endpoint,
so all seventeen books can be re-derived before a human decides on them.

## Why widening is safe, and why that is not obvious

`api/remoderate.py` never flips `storybook.status`, and it proves that
structurally rather than by checking. `run_moderation_pipeline`'s terminal step
always calls `publishing.service.submit` (clean or repaired) or `auto_reject`
(hard block). Neither `(PUBLISHED, SUBMIT)` nor `(PUBLISHED, AUTO_REJECT)` appears
in `publishing/state_machine.py::LEGAL_TRANSITIONS`, so that call always raises
`StateTransitionError`, which the endpoint swallows.

What makes the swallow safe is ordering, not the catch. The pipeline runs
`_persist_report` before it attempts the transition, so the exception discards only
the illegal move and never the freshly written report.

`in_review` satisfies the identical proof. `LEGAL_TRANSITIONS` holds
`(DRAFT, SUBMIT)` and `(NEEDS_REVISION, SUBMIT)` but no `(IN_REVIEW, SUBMIT)`, and
`(DRAFT, AUTO_REJECT)` but no `(IN_REVIEW, AUTO_REJECT)`. An `in_review` book
therefore gets its report refreshed and its status left alone by the same
mechanism, with no state-machine change.

`moderation/pipeline.py` makes no status assumption of its own. It reads
`storybook.status` in exactly one place, as the `to_state` of an event record.

## Design

### 1. Widen the status guard

Replace the inequality at `api/remoderate.py:407` with a membership test against
named module-level constants:

```python
REMODERATABLE_STATUSES: frozenset[Status] = frozenset(
    {Status.PUBLISHED, Status.IN_REVIEW}
)

REMODERATABLE_STATUS_VALUES: frozenset[str] = frozenset(
    s.value for s in REMODERATABLE_STATUSES
)
```

Two constants, and both public, which is a deliberate departure from the single
underscore-prefixed name this section first specified. `Storybook.status` is stored
as a `str`, so the guard needs the value set, while a reader reasoning about the
admission set against `LEGAL_TRANSITIONS` needs the `Status` members; deriving the
second from the first is what keeps them from drifting apart. They are public
because `scripts/remoderate_books.py` validates an operator's explicit `--book-id`
against the same set, so the sweep refuses an inadmissible status before
`--execute` touches any book rather than aborting mid-sweep on this module's 400.
A private constant would have forced a second copy of a security-relevant
admission set into the script, which is the failure the naming avoids.

`draft`, `needs_revision`, and `archived` remain rejected. The `rule` string is
renamed off `remoderate_requires_published`, which the widened set falsifies, to
`remoderate_requires_reviewable_status`.

Named frozensets rather than an inline `in (a, b)` for the same reason
`_GATE_ENTRY_POINTS` exists in `tests/unit/test_gate_capacity_limiter.py`: the set
is the thing a future reader needs to find, and enumerating it in one place keeps a
third status from being added at a call site.

### 2. Auto-repair forks on status

`published` keeps `allow_repair=False`. The reason is unchanged and absolute: a
published book is a guardian-approved artifact a child may be reading offline, so a
silent rewrite would defeat ADR-005.

`in_review` gets `allow_repair=True`. That reason does not transfer: an in-review
book is not reader-facing, a human still gates it before it ever is, and this is
precisely the behaviour the ordinary generation path already applies to a
pre-publish draft.

This flag is load-bearing only once section 5 lands. Repair is gated on
`not report.has_hard_block`, and without the contract fix every one of the seventeen
books produces a fail-closed block, so `allow_repair=True` would be dead code on the
exact population it was enabled for.

This is the one place the endpoint's behaviour forks on status, so it is expressed
as a named helper rather than an inline conditional, and the published invariant
keeps its own dedicated test.

### 3. Re-derive the deterministic half after an adopted repair

This is the part the widening makes necessary, and it is not obvious from the
diff.

`api/remoderate.py` currently computes
`version_row.validation_report = run_fill_gate(version_row.blob).report.to_dict()`
*before* calling the pipeline, honouring design principle 4 of the approved
moderation review redesign (deterministic before generative). That ordering is
correct, and it is safe today only because `allow_repair=False` guarantees the
blob cannot change underneath it.

With repair enabled the blob does change. The pipeline runs repair, then
`_apply_prose_craft_findings`, then `_persist_report`, all before its terminal
transition attempt. On return, `moderation_report` describes the repaired prose
while `validation_report` describes prose that no longer exists.

That is a worse staleness than the month-old reports this work set out to fix,
because it is invisible rather than merely old, and it would be introduced by the
change itself.

The resolution keeps both passes. The pre-pipeline gate stays where it is, because
principle 4 wants the deterministic findings available to the generative stage. A
second `run_fill_gate` pass runs after the pipeline on the `in_review` path, the only
path where repair is enabled.
Re-deriving unconditionally on that path is cheaper than detecting whether a repair
was adopted: `run_moderation_pipeline` returns `None` and signals nothing, and the
gate is deterministic and makes no LLM call.

### 4. Correct the claims the change falsifies

Three comments in `api/remoderate.py` reason from `allow_repair=False` and become
false. They move with the code, not after it, because a stale rationale comment is
the defect class `AL-595` records:

- The module docstring's "Auto-repair is disabled on this path" section.
- The `#CRITICAL` security block asserting re-moderation never mutates prose, which
  narrows to *published* prose specifically.
- The `IMPORT_PROVIDER` `#EDGE` near `api/remoderate.py:450`, which justifies a
  fallback provider by reasoning that it only ever serves an auto-repair re-prompt
  that never runs. All seventeen books are skeleton imports, so that fallback will
  now genuinely perform repair, and the comment needs a `#VERIFY` naming the test
  that proves it.

The `StateTransitionError` catch comment gains `(IN_REVIEW, SUBMIT)` and
`(IN_REVIEW, AUTO_REJECT)` alongside the published pair, since that enumeration is
the proof that status stays untouched.

### 5. Resolve the personalizable-slot contract from the version, not from a job row

Verified against production on 2026-08-24: all seventeen books have **zero**
`generation_job` rows, and all seventeen versions carry `provider = 'import'` with
`skeleton_slug` populated. That makes the widening destructive as designed, and the
auto-repair decision inert, for reasons neither is obvious from.

`api/remoderate.py` does not pass `personalizable_slots`, so
`run_moderation_pipeline` falls back to
`personalizable_slot_ids_for_story(session, story_id)`, which recovers the contract
from the story's `GenerationJob` row and returns `None` when there is none. The
pipeline correctly treats `None` as fail-closed and adds a
`sentinel_integrity_violation` **BLOCK**. That is right on the generation path, where
a job row always exists. On this path it is a false alarm produced by absent
provenance rather than by anything in the prose.

Two consequences follow, and the second cancels an approved decision:

- Every book's stored report would be overwritten with a hard block. Today all
  seventeen store `hard_block = false` (sixteen with a soft flag, one clean), so the
  run would replace seventeen accurate reports with seventeen uninformative ones.
- The repair branch is gated on `not report.has_hard_block`, so the manufactured
  block suppresses repair. `allow_repair=True` would never fire for any of the
  seventeen.

Status is unaffected: `(IN_REVIEW, AUTO_REJECT)` is not a legal hop either, so the
terminal call still raises and is still swallowed. The damage is confined to the
reports, which is why it would have been easy to miss.

`import_filled_story` already avoids this by passing `personalizable_slots`
explicitly rather than relying on the job lookup. Re-moderation does the same, from
the one provenance the version actually carries:

`skeleton_slug` to band via a scan of the skeleton root, then the existing
`resolve_skeleton_path` to `load_skeleton` to `load_contract_for` to
`personalizable_slot_ids` chain that `_contract_for_job` already runs.

`skeleton_match.py::find_skeleton_metadata` performs that scan today but returns only
the metadata, discarding the band directory it matched. The band is taken from the
matched **directory**, not from the metadata's declared `age_band`. The two agree for
every skeleton in the catalog today, and taking the directory keeps them from having
to: a skeleton filed under one band while declaring another would otherwise resolve to
a path that does not exist, and fail closed back to the same spurious block.

The tri-state contract is preserved exactly as `personalizable_slot_ids_for_job`
defines it. An empty frozenset means no personalizable slot could legitimately exist
(no slug, or a legacy skeleton with no contract sidecar); `None` still means the
contract genuinely could not be recovered and the pipeline must still fail closed.
This change removes only the case where `None` meant "this book never had a
generation job", which is true of every imported book and says nothing about safety.

### 6. Tests

- An `in_review` book refreshes its stored report and its status stays `in_review`.
- An `in_review` book whose repair is adopted ends with `validation_report`
  describing the **repaired** blob. Proved by mutation: removing the post-pipeline
  pass must fail this test.
- A `published` book still runs `allow_repair=False` and its blob is unchanged.
  The existing `test_published_blob_unchanged_when_repair_disallowed` must survive.
- `draft`, `needs_revision`, and `archived` remain rejected.
- The import-provider fallback genuinely serves a repair on the `in_review` path.
- A version with a `skeleton_slug` and **no** `generation_job` row resolves a real
  slot set and produces no `sentinel_integrity_violation` finding. This is the
  production shape of all seventeen books, and without the fix it is a hard block.
- A version whose `skeleton_slug` is absent, or names a skeleton that cannot be
  located, still fails closed. The tri-state's `None` arm must survive.

### 7. Give the sweep script a way to reach the new population

Widening the endpoint is not enough to run anything. `scripts/remoderate_books.py`
is the reviewable, versioned selection logic for which books get swept, and both
of its selectors resolve `storybook.current_published_version`, which is NULL for
an `in_review` book. `--mock-moderated` therefore cannot see one, and `--book-id`
raises a 404 on one. The capability would have shipped with no path to it.

Adds a third selector, `--in-review`, and makes `--book-id` resolve by status.

`list_in_review_targets` takes every `in_review` book at `max(version)`. That is
not a new rule: it is what `api/approval.py` uses in both places it needs one
(`_latest_version` for approve and send-back, and the review queue's grouped max
for the listing), so the sweep re-derives the verdicts of the exact version the
reviewer is looking at. Any other rule would write fresh verdicts onto a row the
reviewer is not about to act on.

It applies no report-content filter, unlike `--mock-moderated`. The asymmetry is
deliberate. A published book with a good report needs nothing, so that selector
filters for a specific defect. An `in_review` book's stored report is about to be
acted on by a human whatever it says, so re-deriving it is the point.

`--book-id` refuses an inadmissible status at target resolution, importing the
endpoint's own `REMODERATABLE_STATUS_VALUES` rather than restating it. Deferring
to the endpoint's 400 would abort the sweep mid-flight, after earlier books had
already committed their re-moderations and spent the LLM calls, leaving an
operator to work out which half ran.

The `sweep()` selector guard becomes a count rather than the two-way equality it
replaced. `bool(book_ids) == mock_moderated` is a correct XOR for two flags and
silently stops being one for three: with `in_review` added it accepts
`--mock-moderated --in-review` together and runs whichever branch the `if`/`elif`
chain reaches first.

`main()`'s output no longer claims a dirty book is "still published", which is
false for the population this adds and false in the dangerous direction. It states
the invariant (this sweep never moves a book) and spells out both consequences,
since `--book-id` can mix the two populations.

`list_in_review_targets` returns what it had to drop as well as what it selected.
An `in_review` book with no version row is a corrupt-at-rest anomaly the review
queue also skips, and skipping it is right: one anomaly must not make the whole
sweep unselectable. Reporting it only to the structured log is not, because the
book is then neither `failed` nor `blocked` and reaches an operator through no
channel the sweep itself owns. The sweep would print a tidy target count and exit
0 having covered fewer books than the queue lists, and the all-excluded case is
worse still: it takes `main()`'s "no target books found" early return, which is
indistinguishable from a genuinely empty queue. So the ids come back to the
caller, `main()` names them above the target count, and any exclusion exits
nonzero on the dry-run path too, which is where an operator checks coverage
before spending on LLM calls.

The ids are returned rather than derived by recounting the eligible population
with a second query. A book INSERTed between the two queries would be reported as
excluded when it had merely arrived late.

`main()` also names the books whose text the repair pass rewrote, which only the
`in_review` arm can produce. Rolled into the plain success count it is invisible,
and a reviewer would approve prose they had never read.

## Non-goals

- **No state-machine change.** A hard block leaves the book in `in_review` and the
  admin decides. Adding `(IN_REVIEW, AUTO_REJECT)` would flip status without a
  human, and ADR-005 makes the human the final gate.
- **No batch endpoint.** Seventeen individual POSTs are an acceptable operational
  shape and a sweep endpoint is a second feature, for the reasons
  `api/rescreen.py`'s docstring already gives about reusing the RQ plumbing.
- **No widening of `_VALIDATOR_RULE_IDS`.** The review surface projects
  `{RL-13, PL-19}` by owner ruling (moderation review redesign, section 7 decision
  1). Widening it needs an amendment, and is tracked as the open half of `UW-C362`.

## Known limitations

Re-moderation writes no `pipeline_event`. The pipeline's `record_event` call sits
after its submit/auto_reject call, so the swallowed `StateTransitionError` skips
it. This is already true on the published path and is not a regression, but it
means working the queue this way will not produce the `submitted` events the S-6
validity gate needs. Those come from real approvals, not from re-moderation.

## Operational follow-through

Once this lands, all seventeen books are re-moderated in production. There are two
mechanisms, they differ in more than convenience, and the choice is the owner's.

**The sweep script, in-process.** `scripts/remoderate_books.py --in-review
--execute` calls `remoderate_storybook_version` directly against whatever
`CYO_ADVENTURE_DATABASE_URL` the operator points it at. Consequences: no bearer
token is needed, so the Google-OIDC constraint below does not arise; no family
boundary is crossed, because there is no request principal to scope; the audit
trail stamps `Actor.system()`, which is the honest provenance for a bulk ops
sweep rather than impersonating a test account; and the deployed image does not
need to carry this change, because the run executes the local checkout. The cost
is that it executes local, unreviewed-in-CI code with write access against the
production database, and dry-run-by-default plus `--execute` is its only rail.

**The HTTP endpoint, against the deployed service.** This runs only reviewed,
deployed code and leaves a per-book admin principal in the audit trail, at the
price of two preconditions:

- It uses `test_admin@williamshome.family`. Production holds exactly two admin
  accounts and the other one, `byronawilliams@gmail.com`, authenticates through
  Google OIDC, so it cannot mint a bearer token for a scripted loop. Both are
  `role='guardian'` carrying the orthogonal `is_admin` capability; no account
  holds an admin-only base role.
- That account sits in `E2E Test Family`, not the family owning the seventeen
  books, so the run crosses a family boundary. `_require_admin` gates on
  `ctx.principal.is_admin` alone and applies no family scoping, and
  `core/database.py::apply_family_rls_context` sets `app.is_admin` alongside
  `app.family_id`, so the crossing is intended at both layers. Confirm it against
  one book before the other sixteen rather than assuming it: an RLS-filtered read
  surfaces as a 404 on every book, not as a 403, which reads like a bad storybook
  id rather than a scoping failure.

Either way, the first book is a canary. Confirm its fresh report carries no
`sentinel_integrity_violation` finding before touching the other sixteen: that
finding is what section 5 exists to prevent, and its absence is the only direct
evidence the version-resolved slot contract worked against real rows. Run books
one at a time on the HTTP path, whose single-flight slot rejects rather than
queues; the script already serialises and commits per book.

Repair on the `in_review` path runs through the default configured provider for
imported books, which under the D1 ruling is the restricted family lane. The direct
`anthropic` leg is disabled at rest in `provider_model_allowlist` and must stay so.
