---
schema_type: planning
title: "WS-A Addendum: Admin Moderation Noise Floor"
description: "Configurable global noise floor that hides low-score advisory findings from the
  admin review surface, so a genuine low-but-real moderation score is not lost in a wall of
  near-zero advisories. Extends WS-A on the same branch."
tags:
  - planning
  - moderation
  - implementation
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an engineer with zero context everything needed to implement the admin noise floor
  task by task: exact files, signatures, test-first steps, and verification commands."
component: Moderation
source: "User refinement (2026-07-07) to WS-A's admin-visibility fix (commit b9466f5); codebase
  discovery against feat/ws-a-moderation-thresholds HEAD b9466f5."
---

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use
> checkbox (`- [ ]`) syntax.

## Goal

Give admins a single, editable global "noise floor" so that ADVISORY findings scoring below the
floor are hidden on the admin storybook review surface. FLAG and BLOCK findings (including
bright-line blocks that carry score `0.0`) and any unscored finding always surface. Seed the floor
at `0.05`.

## Why (context)

WS-A commit `b9466f5` restored the invariant "admins see every finding regardless of the age-band
threshold." But the classifier records advisories down to `0.01` (`_ADVISORY_SCORE_FLOOR = 0.01`,
`moderation/classifiers.py:38`), so an admin sees a wall of `0.01`-`0.10` advisories that buries the
one category with real signal. The floor denoises the admin view. It is a GLOBAL scalar, distinct
from the per-`(age_band, category)` `ThresholdPolicy`, because denoising is orthogonal to
age-appropriateness gating.

## Key facts (verified 2026-07-07)

- `build_review_surface` (`api/review_surface.py:30`) is the shared builder. The ONLY admin call
  site is `api/approval.py:241`. Guardian reuse paths (`review_surface.py:260`, `:324`) already
  filter at `min_verdict=FLAG`, which hides all advisories from guardians, so the floor must be an
  opt-in parameter passed ONLY by the admin path.
- Finding-enumeration loop is `review_surface.py:66-76`; each `FindingView` carries `verdict` and
  numeric `score` (or `None`) (`review_surface.py:135-149`).
- `surfaces()` in `moderation/thresholds.py` applies `min_score` across ALL verdicts, so it CANNOT
  be reused for the floor (it would hide a bright-line `0.0` BLOCK). A dedicated advisory-only
  helper is required.
- Router: extend `api/moderation_thresholds.py` (`APIRouter(prefix="/api/v1")`, registered
  `app.py:177`). Threshold paths are `/admin/moderation/thresholds`; add `/admin/moderation/noise-floor`.
- New migration chains `down_revision = "b8c9d0e1f2a3"` (WS-A's, file
  `migrations/versions/20260706_1600_add_moderation_threshold.py`). Real user table is `"user"`.

## Design decision (no separate audit table)

`moderation_setting` carries `updated_by` + `updated_at` for traceability, but no append-only audit
table (unlike `moderation_threshold_audit`). Rationale: a single low-churn scalar; full change
history is deferred to WS-D's `pipeline_event` log. This is an intentional YAGNI call; reviewers
should not flag the asymmetry as a defect.

---

## Task A1: `moderation_setting` table + migration + loader

**Files:** Modify `src/cyo_adventure/db/models.py`; Create
`migrations/versions/20260707_*_add_moderation_setting.py`; Modify
`src/cyo_adventure/moderation/thresholds.py`; Test
`tests/integration/test_moderation_setting_migration.py`,
`tests/unit/test_admin_noise_floor.py`.

- Model `ModerationSetting`: `key` (String PK), `value` (Float, NOT NULL,
  `CheckConstraint("value >= 0 AND value <= 1")`), `updated_at` (TIMESTAMP), `updated_by`
  (FK `"user".id`, nullable). RAD-tag the security relevance (floor controls what admins see).
- Migration: create table; seed `INSERT` row `('admin_noise_floor', 0.05, now(), NULL)`. Downgrade
  drops the table. Pin explicit revision ids; add an import/chain test mirroring
  `test_storybook_version_provider_migration.py`.
- In `thresholds.py`: add `ADMIN_NOISE_FLOOR_DEFAULT = 0.05`;
  `def admin_surfaces(verdict: Verdict | str, score: float | None, *, noise_floor: float) -> bool`
  (coerce verdict, unknown/PASS -> False; ADVISORY with `score is not None and score < noise_floor`
  -> False; else True); `async def load_admin_noise_floor(session) -> float` returning the row
  value or `ADMIN_NOISE_FLOOR_DEFAULT` when absent (tests build tables via metadata, no seed row).
- Unit tests for `admin_surfaces`: BLOCK score 0.0 -> True; FLAG score 0.0 -> True; ADVISORY 0.02
  with floor 0.05 -> False; ADVISORY 0.08 -> True; ADVISORY score None -> True; PASS -> False;
  unknown verdict -> False.

## Task A2: apply the floor on the admin surface

**Files:** Modify `src/cyo_adventure/api/review_surface.py`, `src/cyo_adventure/api/approval.py`;
Test `tests/integration/test_review_surface_noise_floor.py` (or extend the approval test).

- `build_review_surface` gains `admin_noise_floor: float | None = None`. In the enumeration loop
  (`:66-76`), when the floor is not None, skip a finding for which
  `not admin_surfaces(view.verdict, view.score, noise_floor=admin_noise_floor)`. Verdict.PASS skip
  stays. Guardian callers keep passing nothing (default None).
- `approval.py` admin review handler: `floor = await load_admin_noise_floor(session)` and pass
  `admin_noise_floor=floor` into `build_review_surface(...)` at `:241`.
- Integration test: an admin review of a version whose report has an ADVISORY at 0.02 and an
  ADVISORY at 0.09 (floor 0.05) surfaces only the 0.09; a BLOCK at 0.0 still surfaces.

## Task A3: admin API GET/PUT for the floor

**Files:** Modify `src/cyo_adventure/api/moderation_thresholds.py`,
`src/cyo_adventure/api/schemas.py`; Test `tests/integration/test_moderation_noise_floor_api.py`.

- `GET /api/v1/admin/moderation/noise-floor` -> `{"value": <float>}` (admin only, via
  `_require_admin`). `PUT` body `{"value": <float>}` validated to `[0, 1]` (422 otherwise); upsert
  the `admin_noise_floor` row, set `updated_by = ctx.principal.user_id`, `updated_at = now`.
- Schemas `NoiseFloorView`, `NoiseFloorUpdateBody`. `_require_admin` runs before any DB access on
  both endpoints. Tests: guardian 403 on GET and PUT; PUT 0.2 then GET returns 0.2; PUT 1.5 -> 422.

## Task A4: console control + client regen + CHANGELOG

**Files:** Modify `frontend/src/guardian/ModerationThresholdsPage.tsx`,
`frontend/src/guardian/moderationThresholdsApi.ts` (+ test); regen `frontend/src/client/`;
Modify `CHANGELOG.md`.

- Add a small "Admin noise floor" number input (0-1 step 0.01) to the thresholds page that loads via
  GET and saves via PUT, using the `useApi()` adapter pattern (NOT a hand-rolled axios). Scoped
  action error on save failure; top-level error only on initial load.
- Regenerate the client with CI's file-based recipe (`OPENAPI_INPUT=<dumped schema>`) so the
  contract-drift gate stays clean; verify `git diff --exit-code -- frontend/src/client`.
- CHANGELOG "Added": admin-configurable moderation noise floor (denoises the admin review surface).

## Final

Whole-increment review (A1-A4 diff), then the branch awaits the user's push/PR decision.
