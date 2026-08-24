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

Replace the inequality at `api/remoderate.py:407` with a membership test against a
named module-level constant:

```python
_REMODERATABLE_STATUSES = frozenset({Status.PUBLISHED, Status.IN_REVIEW})
```

`draft`, `needs_revision`, and `archived` remain rejected. The `rule` string is
renamed off `remoderate_requires_published`, which the widened set falsifies.

A named frozenset rather than an inline `in (a, b)` for the same reason
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

### 5. Tests

- An `in_review` book refreshes its stored report and its status stays `in_review`.
- An `in_review` book whose repair is adopted ends with `validation_report`
  describing the **repaired** blob. Proved by mutation: removing the post-pipeline
  pass must fail this test.
- A `published` book still runs `allow_repair=False` and its blob is unchanged.
  The existing `test_published_blob_unchanged_when_repair_disallowed` must survive.
- `draft`, `needs_revision`, and `archived` remain rejected.
- The import-provider fallback genuinely serves a repair on the `in_review` path.

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

Once this lands and deploys, all seventeen books are re-moderated in production.
Two preconditions are unresolved and are confirmed before any production call
rather than assumed:

- The run uses `test_admin@williamshome.family`. Production holds exactly two
  admin accounts and the other one, `byronawilliams@gmail.com`, authenticates
  through Google OIDC, so it cannot mint a bearer token for a scripted loop.
  Both are `role='guardian'` carrying the orthogonal `is_admin` capability;
  no account holds an admin-only base role.
- That account sits in `E2E Test Family`, not the family owning the seventeen
  books, so the run crosses a family boundary. `_require_admin` gates on
  `ctx.principal.is_admin` alone and applies no family scoping, and
  `core/database.py::apply_family_rls_context` sets `app.is_admin` alongside
  `app.family_id`, so the crossing is intended at both layers. It is confirmed
  against one book before the other sixteen rather than assumed: an RLS-filtered
  read surfaces as a 404 on every book, not as a 403, which reads like a bad
  storybook id rather than a scoping failure.
- Whether the deployed image carries this change.

Repair on the `in_review` path runs through the default configured provider for
imported books, which under the D1 ruling is the restricted family lane. The direct
`anthropic` leg is disabled at rest in `provider_model_allowlist` and must stay so.
