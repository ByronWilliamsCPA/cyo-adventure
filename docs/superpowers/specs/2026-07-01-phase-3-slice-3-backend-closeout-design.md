---
title: "Phase 3 Slice 3: Backend Closeout (Review-Surface API + Save-State Replay) (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "completion-plan.md C3-4 (review-surface read API); redteam-phase3-findings Finding 2 (reading-state save integrity); api/reading.py (_apply_body, record_completion), api/approval.py (_load_admin_story), moderation/report.py (ModerationReport.to_dict), player/engine.py (StoryEngine), moderation/pipeline.py (blob model_validate pattern); brainstorming decisions 2026-07-01"
purpose: "Design for the Phase 3 backend closeout slice: a guardian review-surface read API (C3-4) that projects the stored moderation report plus flagged passages, and a save-state integrity guard (Finding 2) that validates PUT reading-state against the pinned version via a structural floor plus optional full engine replay."
tags:
  - planning
  - architecture
  - project
---

> Branch: `feat/phase-3-slice-3-backend-closeout` (created off main tip `b973221`) | Date: 2026-07-01 | Author: Byron Williams (with Claude)
> Builds on: slice 1 (approval spine, merged PR #34), slice 2 (moderation pipeline, merged PR #36).
> Implements: [completion-plan C3-4](../../planning/completion-plan.md), [roadmap Phase 3](../../planning/roadmap.md),
> [ADR-005 mandatory human approval](../../planning/adr/adr-005-mandatory-human-approval.md).

## 1. Problem and scope

Phase 3's safety logic (moderation pipeline) and approval spine are merged. Two backend
items remain before the phase is closed and the 4a guardian console can be built:

1. **C3-4 (review-surface read API).** The guardian console (4a, C4a-4) needs one endpoint
   that returns a version's story blob plus its moderation findings, shaped for a parent to
   review flagged passages and approve or send back. No such read endpoint exists;
   `api/approval.py` has only the write transitions.
2. **Finding 2 (save-state integrity).** `api/reading.py::_apply_body` writes client
   `current_node` / `var_state` / `path` / `visit_set` verbatim on the PUT reading-state
   path with no validation against the story graph. Its sibling `record_completion` already
   validates `ending_id` against the cited version's blob, so the write path is internally
   inconsistent: a forged or corrupt save is accepted unchecked.

Both features validate or project client data against a stored `StorybookVersion.blob`, so
they ship as one cohesive backend slice. No frontend work and no database migration are in
scope (see section 7).

## 2. Decisions (from brainstorming, 2026-07-01)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Bundle C3-4 and Finding 2 into one backend slice. | Both read/validate against a version blob; cohesive, no frontend. |
| D2 | Finding 2 validation depth: **full engine replay**. | Strongest guarantee; proves the saved state is actually reachable, not just structurally well-formed. |
| D3 | Replay contract: **compare-and-reject (additive)**. | Client keeps sending derived state and adds `choice_path`; server replays and 422s on mismatch. Minimal, additive schema change; the comparison doubles as a client/server engine-drift detector. |
| D4 | Rollout: **phased, `choice_path` optional now, required later**. | Keeps the slice backend-pure; the frontend player is updated in a tracked follow-up before the field is made required. |
| D5 | Refinement on D4: **two-tier validation** so "optional" is not a total bypass. | A structural floor runs on every save even when `choice_path` is absent; full replay runs when it is present. |

## 3. Part A: C3-4 review-surface read API

### 3.1 Endpoint

`GET /api/v1/storybooks/{storybook_id}/review` on the existing approval router
(`api/approval.py`, prefix `/api/v1`).

- **Query param:** `version: int | None = None`. When omitted, resolve the latest version
  via the existing `_latest_version` helper. When provided, use it directly.
- **Authorization:** reuse `_load_admin_story(ctx, storybook_id)` (admin role required,
  checked before the story is loaded; child or non-admin token -> 403). Admin authority is
  global and cross-family by design, matching every other handler in `api/approval.py` (the
  backend safety-review operator, not a family-scoped guardian); `authorize_family` is
  intentionally not called. This is a read of unpublished, possibly-flagged content, so it
  must never be reachable by a child token.

### 3.2 Response: `ReviewSurfaceView`

```text
ReviewSurfaceView:
    storybook_id: str
    version: int
    status: str                       # storybook.status
    blob: dict[str, object]           # the full stored story blob (StorybookVersion.blob)
    summary: ReviewSummary | None     # None when moderation_report is null
    flagged_passages: list[FlaggedPassage]
    story_level_findings: list[FindingView]

ReviewSummary:                        # mirrors ModerationReport.to_dict()["summary"]
    count: int
    hard_block: bool
    soft_flag: bool
    repaired: bool
    reviewer_independent: bool

FlaggedPassage:
    node_id: str
    prose: str                        # joined from blob node text; "" if node absent
    findings: list[FindingView]

FindingView:                          # mirrors moderation/report.py Finding.to_dict()
    stage: int
    source: str
    category: str
    node_id: str | None
    verdict: str
    score: float | None
    message: str
```

### 3.3 Projection logic

The stored `moderation_report` is already `{findings: [...], summary: {...}}` (see
`moderation/report.py::ModerationReport.to_dict`). The endpoint reshapes it:

- Read `moderation_report` from the resolved `StorybookVersion` row. If `None`, return the
  surface with `summary=None`, `flagged_passages=[]`, `story_level_findings=[]` (an
  `in_review` story with no report yet is valid, not a 404).
- Partition findings by `node_id`:
  - Findings with a non-null `node_id` and a non-`pass` verdict (BLOCK / FLAG / ADVISORY)
    are grouped by `node_id` into `FlaggedPassage`s. `prose` is looked up from the blob's
    node list by id (`""` if the node id is absent from the blob, a defensive fallback for
    a report that references a node the blob no longer contains).
  - Findings with `node_id is None` (coherence / engagement) become `story_level_findings`.
  - `pass` findings are excluded from both projections (clean-check records; the raw counts
    remain in `summary`).

### 3.4 Errors

- `storybook_id` unknown -> `ResourceNotFoundError` (404) via `_load_admin_story`.
- Explicit `version` that does not exist -> `ResourceNotFoundError` (404).
- Non-admin principal -> `AuthorizationError` (403) via `_load_admin_story`.

## 4. Part B: Finding 2 save-state replay validation

### 4.1 Schema change (additive)

Add one optional, request-only field to `ReadingStateBody` (`api/schemas.py`):

```python
choice_path: list[str] | None = None
```

The ordered choice-ids the child selected from the story start to reach `current_node`.
Optional in this slice (D4); a tracked follow-up makes it required once the frontend sends
it (section 6). No change to `ReadingStateView` and no database migration.

### 4.2 New module: `player/replay.py`

A pure, synchronous validator with no I/O:

```text
def validate_reading_state(
    blob: dict[str, object],
    *,
    current_node: str,
    var_state: VarState,
    path: list[str],
    visit_set: list[str],
    choice_path: list[str] | None,
) -> None:
    """Raise ValidationError (-> 422) if the save is not consistent with the blob."""
```

It parses the blob once and runs two tiers.

**Parse (defensive):** `story = Storybook.model_validate(blob)` (the same pattern
`moderation/pipeline.py:195` uses). A `pydantic.ValidationError` here means the version was
corrupted at rest; re-raise as a domain `ValidationError` (422) with a generic message
(CWE-209: do not leak the raw schema error to the client; log the detail server-side).

**Tier 1, structural floor (ALWAYS, even when `choice_path is None`):**

- `body.current_node` must be an existing node id.
- Every id in `body.path` and `body.visit_set` must be an existing node id.
- Every key in `body.var_state` must be a declared variable; each `int`-typed variable's
  value must be within its declared `min`/`max` bounds and of the declared type.
- Any violation -> `ValidationError` (422), naming the offending field.

**Tier 2, full replay (only when `choice_path is not None`):**

- `state = StoryEngine(story).start()`.
- For each `choice_id` in `body.choice_path`: `state = engine.choose(state, choice_id)`.
  A `BusinessLogicError` (unknown/invisible choice, or choosing from an ending) is caught
  and re-raised as `ValidationError` (422).
- Compare the replayed state to the submitted state: `current_node`, `var_state`,
  `set(visit_set)`, and `path` must all match. Any mismatch -> `ValidationError` (422).

### 4.3 Call site

In `api/reading.py::put_reading_state`, after `_load_owned_storybook` and before applying
the body, load the pinned version and validate:

- `version_row = await ctx.session.get(StorybookVersion, (storybook_id, body.version))`;
  `None` -> `ResourceNotFoundError` (404), matching `record_completion`.
- `validate_reading_state(version_row.blob, body)`.
- Applies to both the create (`_create_reading_state`) and update paths, so a first save is
  validated too.

This adds one version-blob fetch and parse per save. Saves are human-paced (one per child
choice), so the cost is acceptable; tagged with a RAD `#ASSUME` marker at the call site.

### 4.4 Boundary: save slots

`body.save_slots` are stored but not replay-validated in this slice. Each slot is a
client-side checkpoint snapshot without its own `choice_path`, so the server cannot replay
it. Only the top-level current state is validated per save. Stated here as an explicit
Phase-3 scope boundary; revisit if slots become a forgeable surface.

## 5. Error handling

All client-caused rejections raise from the centralized hierarchy
(`core/exceptions.py`): `ValidationError` -> 422, `ResourceNotFoundError` -> 404,
`AuthorizationError` -> 403. Corrupt-at-rest blobs raise a generic `ValidationError` (422)
with server-side-only detail (CWE-209), consistent with `moderation/pipeline.py` handling
the same case. No new exception types are introduced.

## 6. Tracked follow-up (the "required later" half of D4)

Recorded so the phased rollout closes:

1. Frontend: the React player accumulates each `choice_id` (it currently tracks only
   `path`, the node ids), persists it in the offline cache and offline queue, and includes
   `choice_path` in every save. Regenerate the OpenAPI client.
2. Backend: flip `choice_path` to required and drop the `None` branch so Tier 2 runs on
   every save.

A `#ASSUME` RAD marker at the `put_reading_state` call site references this follow-up, and a
backlog entry is added to the completion plan / project memory.

## 7. Out of scope

- Any frontend change (player, offline sync, client regen) - deferred to the follow-up.
- Making `choice_path` required - deferred to the follow-up.
- Replay-validating `save_slots` - stated boundary (section 4.4).
- Database migrations - none needed (`choice_path` is request-only; `moderation_report`
  column already exists).
- The 4a guardian console UI that consumes C3-4 - separate Phase 4a slice.

## 8. Testing

Unit tests only (Docker-independent), following the existing `httpx.MockTransport` and
FastAPI test-client patterns in `tests/unit`. Target 90% coverage on new code (Phase 3
acceptance bar).

**Part A (C3-4):**

- Admin gets the surface for the latest version; explicit `?version=` returns that version.
- Child or non-admin token -> 403. Cross-family admin -> 200 (admin authority is global,
  matching every other `api/approval.py` handler; this is not a family-scoped guardian read).
- Flagged-passage join: a finding with a `node_id` is grouped and its `prose` matches the
  blob node text; a `node_id=None` finding lands in `story_level_findings`; `pass` findings
  are excluded.
- A story `in_review` with `moderation_report=None` returns empty projections, not 404.
- Unknown storybook / unknown explicit version -> 404.

**Part B (Finding 2):**

- Structural floor (no `choice_path`): a valid state passes; a `current_node` not in the
  blob, a `path`/`visit_set` id not in the blob, an undeclared `var_state` key, and an
  out-of-bounds int value each -> 422.
- Full replay (`choice_path` present): a genuine replayed state passes; a forged
  `current_node`, a forged `var_state`, and an illegal/invisible `choice_id` each -> 422;
  a `path`/`visit_set` mismatch vs replay -> 422.
- Create path (first save) is validated the same as update.
- A corrupt-at-rest blob -> generic 422 (no schema-detail leak).
- Regression: existing reading-state concurrency/idempotency tests still pass.
