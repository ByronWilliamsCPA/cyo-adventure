---
schema_type: planning
title: "WS-F: Moderation Suggestion Dashboard Implementation Plan"
description: "Task-level implementation plan for the WS-F moderation suggestion dashboard: pure
  aggregation core, DB loader, two admin GET endpoints, OpenAPI client regen, and the admin
  dashboard page with an apply-suggestion flow through the existing WS-A threshold upsert."
tags:
  - planning
  - moderation
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an implementer with zero context every file path, code block, command, and expected
  output needed to build WS-F task by task under the ratified spec."
component: Moderation
source: "docs/planning/ws-f-suggestion-dashboard-spec.md (decisions F1-F5 ratified 2026-07-09);
  codebase discovery 2026-07-09 against main b15ed15 in .worktrees/ws-f."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Build the WS-F admin moderation dashboard: aggregate per-version moderation reports plus the
pipeline event log into per-(age band, category) override evidence and threshold suggestions,
served by two admin-only GET endpoints and a new admin page whose apply control reuses the
existing audited threshold upsert. No migration, no new event type, no auto-calibration.

## Architecture

Pure computation lives in a new `moderation/insights.py` (dataclasses plus functions that
unit-test without a DB); a single loader function does the three reads (version rows with
reports, `moderation_completed` timestamps, `released`/`sent_back` decision events). A new
router `api/moderation_dashboard.py` exposes `GET /api/v1/admin/moderation/dashboard` and
`GET /api/v1/admin/moderation/suggestions`. The frontend adds a hand-typed adapter and
`ModerationDashboardPage.tsx` under `frontend/src/guardian/`, routed inside the existing
admin-only `ProtectedRoute` group; apply calls the existing `makeThresholdsApi(api).upsert`.

## Tech Stack

FastAPI + async SQLAlchemy 2.x (PostgreSQL JSONB), Pydantic v2 views in `api/schemas.py`,
pytest (+ testcontainers Postgres for integration), React 19 + Vitest + Testing Library,
hand-typed axios adapters importing types from the generated `frontend/src/client/types.gen.ts`.

---

## Verified facts the plan builds on (do not re-derive)

- `moderation_completed` events: `entity_type="storybook_version"`,
  `entity_id=f"{story_id}:{version}"`. Payload has NO categories (WS-D D3 forbids them).
- `released` / `sent_back` events: `entity_type="storybook"`, `entity_id=storybook.id`
  (`src/cyo_adventure/publishing/service.py:181-189` and `:229-237`), `from_state="in_review"`.
  Version attribution = first decision event on the storybook at or after that version's
  `moderation_completed` time; `approved_by IS NOT NULL` is the released fallback for
  pre-event history; otherwise undecided (excluded from rate denominators).
- `StorybookVersion` (`src/cyo_adventure/db/models.py:234-279`): `blob` JSONB (band at
  `blob["metadata"]["age_band"]`), `moderation_report` JSONB nullable, `approved_by` UUID
  nullable, `created_at`. Report shape (`moderation/report.py:126-137`):
  `{"findings": [{"stage", "source", "category", "node_id", "verdict", "score", "message"}, ...],
  "summary": {...}}`. `Verdict` values: `block`, `flag`, `advisory`, `pass`.
- Thresholds: `DEFAULT_THRESHOLD = Threshold(min_verdict=Verdict.FLAG, min_score=None)`
  (`moderation/thresholds.py:70`); `ThresholdPolicy.resolve(age_band, category)`;
  `load_threshold_policy(session)` loads rows over the default. `MinVerdict =
  Literal["advisory", "flag", "block"]` (`api/schemas.py:955`).
- Age bands: `'3-5', '5-8', '8-11', '10-13', '13-16', '16+'`.
- Admin gate pattern: module-local `_require_admin(ctx: Context)` raising
  `AuthorizationError("admin role required", required_permission="admin")`
  (`api/moderation_thresholds.py:47-61`); router registered in `app.py:182`.
- Integration fixtures (`tests/integration/conftest.py`): `client` (AsyncClient), `seed`
  (dataclass `Seed` with `family_id`, `admin_token`, `guardian_token`, `storybook_id`, ...),
  `sessions` (async_sessionmaker), `auth(token)` header helper; fresh schema per test via
  testcontainers Postgres 16. Marker: `@pytest.mark.integration`.
- `PipelineEvent`: `id` defaults to `uuid.uuid4`, `occurred_at` server-default now (tests must
  set it explicitly for deterministic ordering), `payload` non-null (use `{}`), CHECK requires
  `actor_id IS NULL` when `actor_role='system'`. Append-only by DB trigger: tests INSERT only.
- Frontend: adapters are hand-typed factories over the `useApi()` axios instance, importing
  types from `../client/types.gen` (see `frontend/src/guardian/moderationThresholdsApi.ts`).
  Admin routes live in `frontend/src/router.tsx:104-124` (inner `ProtectedRoute
  allowedRoles={['admin']} deniedRedirectTo={GUARDIAN_CONSOLE_PATH}`, child path
  `'moderation-thresholds'` under the `/guardian` subtree); lazy imports in
  `frontend/src/routeElements.tsx:80-84`. Page tests mock `useApi` and route `mockGet` by path.
- `frontend/src/client/` IS committed; CI drift gate regenerates via in-process
  `app.openapi()` dump piped to `OPENAPI_INPUT=... npm run generate-client` and fails on diff.
  Never sort keys.
- Baseline on this branch (`feat/ws-f-suggestion-dashboard`, cut from main `b15ed15`):
  backend 2048 passed / 95.64% coverage.

## File structure

| File | Action | Responsibility |
| --- | --- | --- |
| `src/cyo_adventure/moderation/insights.py` | Create | Outcome attribution, aggregation, suggestion rule (pure) + `load_version_records` (DB read) |
| `src/cyo_adventure/api/schemas.py` | Modify | Five new response views |
| `src/cyo_adventure/api/moderation_dashboard.py` | Create | Two admin GET endpoints |
| `src/cyo_adventure/app.py` | Modify | Register the router |
| `tests/unit/test_moderation_insights.py` | Create | Pure-function unit tests |
| `tests/integration/test_moderation_dashboard_api.py` | Create | Endpoint + authz + seeded-event tests |
| `frontend/src/client/*` | Regenerate | Generated types for the new views |
| `frontend/src/guardian/moderationDashboardApi.ts` | Create | Hand-typed adapter for the two GETs |
| `frontend/src/guardian/ModerationDashboardPage.tsx` | Create | Dashboard page with apply flow |
| `frontend/src/guardian/ModerationDashboardPage.test.tsx` | Create | Vitest page tests |
| `frontend/src/routeElements.tsx` | Modify | Lazy import |
| `frontend/src/router.tsx` | Modify | Admin child route `'moderation-dashboard'` |
| `frontend/src/guardian/ConsolePage.tsx` (+ test) | Modify | Admin-only links to dashboard and thresholds |
| `CHANGELOG.md` | Modify | Unreleased entry |

All commands below run from the worktree root `/home/byron/dev/CYO_Adventure/.worktrees/ws-f`
unless a `cd frontend` is shown. Backend tests need Docker running (testcontainers).

---

### Task 1: Pure aggregation core (`insights.py`, no DB)

**Files:**
- Create: `src/cyo_adventure/moderation/insights.py`
- Test: `tests/unit/test_moderation_insights.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_moderation_insights.py`:

```python
"""Unit tests for the WS-F moderation insights aggregation core."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cyo_adventure.events import EventType
from cyo_adventure.moderation.insights import (
    VersionModerationRecord,
    VersionOutcome,
    aggregate_insights,
    attribute_outcome,
)

_T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
_LATER = _T0 + timedelta(hours=1)
_EARLIER = _T0 - timedelta(hours=1)

_RELEASED = EventType.RELEASED.value
_SENT_BACK = EventType.SENT_BACK.value


def _finding(category: str, verdict: str) -> dict[str, object]:
    return {"category": category, "verdict": verdict, "score": 0.5}


def _record(
    *,
    findings: list[dict[str, object]],
    outcome: VersionOutcome,
    age_band: str = "8-11",
    storybook_id: str = "s_1",
    version: int = 1,
    moderated_at: datetime = _T0,
) -> VersionModerationRecord:
    return VersionModerationRecord(
        storybook_id=storybook_id,
        version=version,
        age_band=age_band,
        findings=findings,
        moderated_at=moderated_at,
        outcome=outcome,
    )


class TestAttributeOutcome:
    def test_first_decision_after_moderation_wins(self) -> None:
        decisions = [(_LATER, _SENT_BACK), (_LATER + timedelta(hours=1), _RELEASED)]
        outcome = attribute_outcome(_T0, decisions, approved=False)
        assert outcome == VersionOutcome(decided=True, released=False)

    def test_released_decision(self) -> None:
        outcome = attribute_outcome(_T0, [(_LATER, _RELEASED)], approved=False)
        assert outcome == VersionOutcome(decided=True, released=True)

    def test_decision_before_moderation_is_ignored(self) -> None:
        outcome = attribute_outcome(_T0, [(_EARLIER, _RELEASED)], approved=False)
        assert outcome == VersionOutcome(decided=False, released=False)

    def test_approved_fallback_counts_as_released(self) -> None:
        outcome = attribute_outcome(_T0, [], approved=True)
        assert outcome == VersionOutcome(decided=True, released=True)

    def test_no_decision_and_not_approved_is_undecided(self) -> None:
        outcome = attribute_outcome(_T0, [], approved=False)
        assert outcome == VersionOutcome(decided=False, released=False)


class TestAggregateInsights:
    def test_counts_findings_and_versions_per_band_category(self) -> None:
        records = [
            _record(
                findings=[_finding("violence", "advisory")],
                outcome=VersionOutcome(decided=True, released=True),
                storybook_id="s_1",
            ),
            _record(
                findings=[_finding("violence", "flag")],
                outcome=VersionOutcome(decided=True, released=False),
                storybook_id="s_2",
                moderated_at=_LATER,
            ),
        ]
        insights = aggregate_insights(records)
        assert len(insights) == 1
        row = insights[0]
        assert (row.age_band, row.category) == ("8-11", "violence")
        assert row.advisory_findings == 1
        assert row.flag_findings == 1
        assert row.decided_versions == 2
        assert row.released_versions == 1
        assert row.override_rate == 0.5
        assert row.last_seen == _LATER

    def test_dedupes_category_within_a_version(self) -> None:
        records = [
            _record(
                findings=[
                    _finding("violence", "advisory"),
                    _finding("violence", "advisory"),
                ],
                outcome=VersionOutcome(decided=True, released=True),
            )
        ]
        row = aggregate_insights(records)[0]
        assert row.advisory_findings == 2
        assert row.decided_versions == 1
        assert row.released_versions == 1

    def test_undecided_versions_do_not_enter_the_denominator(self) -> None:
        records = [
            _record(
                findings=[_finding("violence", "advisory")],
                outcome=VersionOutcome(decided=False, released=False),
            )
        ]
        row = aggregate_insights(records)[0]
        assert row.decided_versions == 0
        assert row.override_rate is None

    def test_block_and_pass_findings_are_excluded(self) -> None:
        records = [
            _record(
                findings=[_finding("violence", "block"), _finding("fear", "pass")],
                outcome=VersionOutcome(decided=True, released=True),
            )
        ]
        assert aggregate_insights(records) == []

    def test_malformed_findings_are_skipped(self) -> None:
        records = [
            _record(
                findings=[{"verdict": "advisory"}, {"category": 3, "verdict": "flag"}],
                outcome=VersionOutcome(decided=True, released=True),
            )
        ]
        assert aggregate_insights(records) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --all-extras pytest tests/unit/test_moderation_insights.py -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named
'cyo_adventure.moderation.insights'`

- [ ] **Step 3: Write the implementation**

Create `src/cyo_adventure/moderation/insights.py`:

```python
"""Aggregation of moderation evidence into threshold insights (WS-F).

Read side of the moderation learning loop: correlates the per-version
moderation reports persisted on ``storybook_version.moderation_report`` with
the ``released`` / ``sent_back`` decision events in the append-only
``pipeline_event`` log, and derives admin-facing override rates and threshold
suggestions. Pure computation lives in module-level functions so it unit
tests without a database; ``load_version_records`` is the only DB read.
This module never writes (umbrella decision 3: no auto-calibration).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select

from cyo_adventure.db.models import PipelineEvent, StorybookVersion
from cyo_adventure.events import EventType
from cyo_adventure.moderation.report import Verdict

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.moderation.thresholds import ThresholdPolicy

# Suggestion gates: a proposal appears only when at least this many decided
# versions carry the (band, category) signal and at least this fraction of
# them were released despite it.
SUGGESTION_MIN_DECIDED = 5
SUGGESTION_MIN_OVERRIDE_RATE = 0.8

# Raising the surfacing bar one step: findings below min_verdict stop
# surfacing to families, so "overridden too often" moves the bar upward.
_VERDICT_RAISE: dict[str, str] = {
    Verdict.ADVISORY.value: Verdict.FLAG.value,
    Verdict.FLAG.value: Verdict.BLOCK.value,
}

# Verdicts a guardian can override by releasing anyway; hard blocks never
# reach the guardian, so they carry no override signal.
_OVERRIDABLE_VERDICTS = frozenset({Verdict.ADVISORY.value, Verdict.FLAG.value})


@dataclass(frozen=True, slots=True)
class VersionOutcome:
    """Terminal review decision attributed to one storybook version."""

    decided: bool
    released: bool


_UNDECIDED = VersionOutcome(decided=False, released=False)


def attribute_outcome(
    moderated_at: datetime,
    decisions: Sequence[tuple[datetime, str]],
    *,
    approved: bool,
) -> VersionOutcome:
    """Attribute a per-storybook decision stream to one version.

    ``released`` and ``sent_back`` events carry only the storybook id, so the
    version they decide is the one whose moderation completed most recently
    before them: the first decision at or after ``moderated_at`` belongs to
    this version.

    Args:
        moderated_at: When this version's moderation completed (event time,
            falling back to the version row's ``created_at``).
        decisions: ``(occurred_at, event_type)`` pairs for the version's
            storybook, sorted ascending by ``occurred_at``.
        approved: Whether the version row has ``approved_by`` set.

    Returns:
        The attributed outcome; undecided when no decision follows and the
        version was never approved.
    """
    for occurred_at, event_type in decisions:
        if occurred_at >= moderated_at:
            return VersionOutcome(
                decided=True, released=event_type == EventType.RELEASED.value
            )
    if approved:
        # #ASSUME: data-integrity: pre-WS-D history has approvals but no
        # decision events; approved_by on the version row is the release
        # record for those. There is no equivalent sent-back record, so
        # unapproved event-less versions stay out of the denominator.
        # #VERIFY: tests/unit/test_moderation_insights.py::TestAttributeOutcome
        return VersionOutcome(decided=True, released=True)
    return _UNDECIDED


@dataclass(frozen=True, slots=True)
class VersionModerationRecord:
    """One moderated version: band, findings, and attributed outcome."""

    storybook_id: str
    version: int
    age_band: str
    findings: Sequence[Mapping[str, object]]
    moderated_at: datetime
    outcome: VersionOutcome


@dataclass(frozen=True, slots=True)
class CategoryInsight:
    """Override evidence for one (age_band, category) pair."""

    age_band: str
    category: str
    advisory_findings: int
    flag_findings: int
    decided_versions: int
    released_versions: int
    override_rate: float | None
    last_seen: datetime


@dataclass(slots=True)
class _CategoryAccumulator:
    last_seen: datetime
    advisory_findings: int = 0
    flag_findings: int = 0
    decided_versions: int = 0
    released_versions: int = 0


def aggregate_insights(
    records: Sequence[VersionModerationRecord],
) -> list[CategoryInsight]:
    """Aggregate per-version records into per-(band, category) evidence.

    Finding counts tally every advisory/flag finding; version counts
    (``decided_versions`` / ``released_versions``) count each version at most
    once per category, since one release decision overrides every advisory on
    that version together (accepted F1 coarseness).

    Args:
        records: Version records from ``load_version_records`` (or built
            directly in tests).

    Returns:
        Insights sorted by (age_band, category).
    """
    accumulators: dict[tuple[str, str], _CategoryAccumulator] = {}
    for record in records:
        seen_categories: set[str] = set()
        for finding in record.findings:
            category = finding.get("category")
            verdict = finding.get("verdict")
            # #EDGE: data-integrity: moderation_report is JSONB written by
            # ModerationReport.to_dict(), but imported or legacy rows may
            # deviate; a finding missing category/verdict is skipped, never
            # a crash.
            # #VERIFY: tests/unit/test_moderation_insights.py::
            # TestAggregateInsights::test_malformed_findings_are_skipped
            if not isinstance(category, str) or verdict not in _OVERRIDABLE_VERDICTS:
                continue
            key = (record.age_band, category)
            accumulator = accumulators.get(key)
            if accumulator is None:
                accumulator = _CategoryAccumulator(last_seen=record.moderated_at)
                accumulators[key] = accumulator
            if verdict == Verdict.ADVISORY.value:
                accumulator.advisory_findings += 1
            else:
                accumulator.flag_findings += 1
            if record.moderated_at > accumulator.last_seen:
                accumulator.last_seen = record.moderated_at
            if category in seen_categories:
                continue
            seen_categories.add(category)
            if record.outcome.decided:
                accumulator.decided_versions += 1
                if record.outcome.released:
                    accumulator.released_versions += 1
    insights: list[CategoryInsight] = []
    for (age_band, category), accumulator in sorted(accumulators.items()):
        override_rate = (
            accumulator.released_versions / accumulator.decided_versions
            if accumulator.decided_versions
            else None
        )
        insights.append(
            CategoryInsight(
                age_band=age_band,
                category=category,
                advisory_findings=accumulator.advisory_findings,
                flag_findings=accumulator.flag_findings,
                decided_versions=accumulator.decided_versions,
                released_versions=accumulator.released_versions,
                override_rate=override_rate,
                last_seen=accumulator.last_seen,
            )
        )
    return insights
```

(The `ThresholdSuggestion` / `suggest_thresholds` and `load_version_records` pieces are added in
Tasks 2 and 3; the `func`, `select`, `PipelineEvent`, `StorybookVersion`, `AsyncSession`,
`ThresholdPolicy`, and `cast` imports above are used by those tasks. If ruff flags them unused
at this step, add them in Task 2/3 instead of suppressing.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --all-extras pytest tests/unit/test_moderation_insights.py -v`
Expected: all tests PASS

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff format src/cyo_adventure/moderation/insights.py tests/unit/test_moderation_insights.py
uv run ruff check src/cyo_adventure/moderation/insights.py tests/unit/test_moderation_insights.py
uv run basedpyright src/cyo_adventure/moderation/insights.py
git add src/cyo_adventure/moderation/insights.py tests/unit/test_moderation_insights.py
git commit -S -m "feat(moderation): WS-F insights aggregation core"
```

---

### Task 2: Suggestion rule (depends-on: Task1 [output])

**Files:**
- Modify: `src/cyo_adventure/moderation/insights.py`
- Test: `tests/unit/test_moderation_insights.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_moderation_insights.py` (extend the imports at the top of the file):

```python
from cyo_adventure.moderation.insights import (  # add to the existing import
    SUGGESTION_MIN_DECIDED,
    CategoryInsight,
    suggest_thresholds,
)
from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.thresholds import Threshold, ThresholdPolicy


def _insight(
    *,
    decided: int,
    released: int,
    age_band: str = "8-11",
    category: str = "violence",
) -> CategoryInsight:
    return CategoryInsight(
        age_band=age_band,
        category=category,
        advisory_findings=decided,
        flag_findings=0,
        decided_versions=decided,
        released_versions=released,
        override_rate=(released / decided) if decided else None,
        last_seen=_T0,
    )


class TestSuggestThresholds:
    def test_high_override_rate_raises_default_flag_to_block(self) -> None:
        policy = ThresholdPolicy(rows={})
        insights = [_insight(decided=SUGGESTION_MIN_DECIDED, released=5)]
        suggestions = suggest_thresholds(insights, policy)
        assert len(suggestions) == 1
        suggestion = suggestions[0]
        assert suggestion.current_min_verdict == "flag"
        assert suggestion.suggested_min_verdict == "block"
        assert suggestion.override_rate == 1.0
        assert suggestion.current_min_score is None

    def test_override_row_at_advisory_suggests_flag(self) -> None:
        policy = ThresholdPolicy(
            rows={
                ("8-11", "violence"): Threshold(
                    min_verdict=Verdict.ADVISORY, min_score=0.25
                )
            }
        )
        insights = [_insight(decided=6, released=6)]
        suggestion = suggest_thresholds(insights, policy)[0]
        assert suggestion.current_min_verdict == "advisory"
        assert suggestion.suggested_min_verdict == "flag"
        assert suggestion.current_min_score == 0.25

    def test_below_volume_gate_no_suggestion(self) -> None:
        policy = ThresholdPolicy(rows={})
        insights = [_insight(decided=SUGGESTION_MIN_DECIDED - 1, released=4)]
        assert suggest_thresholds(insights, policy) == []

    def test_below_rate_gate_no_suggestion(self) -> None:
        policy = ThresholdPolicy(rows={})
        insights = [_insight(decided=10, released=7)]
        assert suggest_thresholds(insights, policy) == []

    def test_current_block_has_nothing_to_raise(self) -> None:
        policy = ThresholdPolicy(
            rows={
                ("8-11", "violence"): Threshold(
                    min_verdict=Verdict.BLOCK, min_score=None
                )
            }
        )
        insights = [_insight(decided=10, released=10)]
        assert suggest_thresholds(insights, policy) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --all-extras pytest tests/unit/test_moderation_insights.py -v -k Suggest`
Expected: FAIL with `ImportError: cannot import name 'suggest_thresholds'`

- [ ] **Step 3: Write the implementation**

Append to `src/cyo_adventure/moderation/insights.py` (after `aggregate_insights`):

```python
@dataclass(frozen=True, slots=True)
class ThresholdSuggestion:
    """A computed proposal to raise one (band, category) surfacing bar."""

    age_band: str
    category: str
    current_min_verdict: str
    current_min_score: float | None
    suggested_min_verdict: str
    override_rate: float
    decided_versions: int
    released_versions: int


def suggest_thresholds(
    insights: Sequence[CategoryInsight],
    policy: ThresholdPolicy,
) -> list[ThresholdSuggestion]:
    """Derive threshold proposals from override evidence.

    A proposal appears only above the volume and rate gates and only when the
    effective threshold has a step left to raise; a (band, category) already
    at ``block`` yields nothing, which also makes an applied suggestion stop
    reappearing (F2: dismiss is a no-op, the threshold move retires it).

    Args:
        insights: Output of ``aggregate_insights``.
        policy: The resolved surfacing policy (rows over the code default).

    Returns:
        Proposals in the insights' (age_band, category) order.
    """
    suggestions: list[ThresholdSuggestion] = []
    for insight in insights:
        if insight.decided_versions < SUGGESTION_MIN_DECIDED:
            continue
        if (
            insight.override_rate is None
            or insight.override_rate < SUGGESTION_MIN_OVERRIDE_RATE
        ):
            continue
        threshold = policy.resolve(insight.age_band, insight.category)
        current = threshold.min_verdict.value
        suggested = _VERDICT_RAISE.get(current)
        if suggested is None:
            continue
        suggestions.append(
            ThresholdSuggestion(
                age_band=insight.age_band,
                category=insight.category,
                current_min_verdict=current,
                current_min_score=threshold.min_score,
                suggested_min_verdict=suggested,
                override_rate=insight.override_rate,
                decided_versions=insight.decided_versions,
                released_versions=insight.released_versions,
            )
        )
    return suggestions
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --all-extras pytest tests/unit/test_moderation_insights.py -v`
Expected: all tests PASS (Task 1 tests included)

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff format src/cyo_adventure/moderation/insights.py tests/unit/test_moderation_insights.py
uv run ruff check src/cyo_adventure/moderation/insights.py tests/unit/test_moderation_insights.py
uv run basedpyright src/cyo_adventure/moderation/insights.py
git add src/cyo_adventure/moderation/insights.py tests/unit/test_moderation_insights.py
git commit -S -m "feat(moderation): WS-F threshold suggestion rule"
```

---

### Task 3: DB loader `load_version_records` (depends-on: Task1 [output])

**Files:**
- Modify: `src/cyo_adventure/moderation/insights.py`
- Test: `tests/integration/test_moderation_dashboard_api.py` (created here with loader-level
  seeding helpers; endpoint tests are added in Tasks 4-5)

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_moderation_dashboard_api.py`:

```python
"""Integration tests for the WS-F moderation dashboard (loader + endpoints)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import PipelineEvent, Storybook, StorybookVersion
from cyo_adventure.events import EventType
from cyo_adventure.moderation.insights import load_version_records
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def _report(*findings: dict[str, object]) -> dict[str, object]:
    return {
        "findings": list(findings),
        "summary": {
            "count": len(findings),
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


def _finding(category: str, verdict: str) -> dict[str, object]:
    return {
        "stage": 1,
        "source": "openai",
        "category": category,
        "node_id": None,
        "verdict": verdict,
        "score": 0.4,
        "message": "graded signal",
    }


def _event(
    *,
    entity_type: str,
    entity_id: str,
    event_type: EventType,
    occurred_at: datetime,
) -> PipelineEvent:
    return PipelineEvent(
        id=uuid.uuid4(),
        occurred_at=occurred_at,
        actor_id=None,
        actor_role="system",
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type.value,
        payload={},
    )


async def _seed_moderated_version(
    session: AsyncSession,
    seed: Seed,
    *,
    storybook_id: str,
    age_band: str = "8-11",
    findings: list[dict[str, object]],
    decision: EventType | None,
    moderated_at: datetime = _T0,
) -> None:
    """Insert one storybook version with a report and its event trail."""
    session.add(
        Storybook(id=storybook_id, family_id=seed.family_id, status="in_review")
    )
    session.add(
        StorybookVersion(
            storybook_id=storybook_id,
            version=1,
            blob={"metadata": {"age_band": age_band}},
            moderation_report=_report(*findings),
        )
    )
    session.add(
        _event(
            entity_type="storybook_version",
            entity_id=f"{storybook_id}:1",
            event_type=EventType.MODERATION_COMPLETED,
            occurred_at=moderated_at,
        )
    )
    if decision is not None:
        session.add(
            _event(
                entity_type="storybook",
                entity_id=storybook_id,
                event_type=decision,
                occurred_at=moderated_at + timedelta(minutes=5),
            )
        )


class TestLoadVersionRecords:
    async def test_loader_builds_records_with_outcomes(
        self,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        async with sessions() as session:
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_released",
                findings=[_finding("violence", "advisory")],
                decision=EventType.RELEASED,
            )
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_sent_back",
                findings=[_finding("violence", "flag")],
                decision=EventType.SENT_BACK,
            )
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_pending",
                findings=[_finding("violence", "advisory")],
                decision=None,
            )
            await session.commit()

        async with sessions() as session:
            records = await load_version_records(session)

        by_id = {record.storybook_id: record for record in records}
        assert by_id["s_released"].outcome.decided is True
        assert by_id["s_released"].outcome.released is True
        assert by_id["s_released"].age_band == "8-11"
        assert by_id["s_released"].moderated_at == _T0
        assert by_id["s_sent_back"].outcome.decided is True
        assert by_id["s_sent_back"].outcome.released is False
        assert by_id["s_pending"].outcome.decided is False

    async def test_loader_skips_versions_without_band(
        self,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        async with sessions() as session:
            session.add(
                Storybook(id="s_no_band", family_id=seed.family_id, status="in_review")
            )
            session.add(
                StorybookVersion(
                    storybook_id="s_no_band",
                    version=1,
                    blob={"metadata": {}},
                    moderation_report=_report(_finding("violence", "advisory")),
                )
            )
            await session.commit()

        async with sessions() as session:
            records = await load_version_records(session)

        assert all(record.storybook_id != "s_no_band" for record in records)
```

Note: the `seed` fixture also inserts one published storybook of its own
(`seed.storybook_id`); it has no `moderation_report`, so the
`moderation_report IS NOT NULL` filter keeps it out of these assertions.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --all-extras pytest tests/integration/test_moderation_dashboard_api.py -v`
Expected: FAIL at collection with `ImportError: cannot import name 'load_version_records'`
(Docker must be running for the testcontainers fixture.)

- [ ] **Step 3: Write the loader**

Append to `src/cyo_adventure/moderation/insights.py`:

```python
async def load_version_records(session: AsyncSession) -> list[VersionModerationRecord]:
    """Load every moderated version with its band, findings, and outcome.

    Three reads: version rows carrying a moderation report (band extracted
    from the blob's typed metadata in SQL, so blobs are never fetched),
    ``moderation_completed`` timestamps, and per-storybook decision events.

    Args:
        session: The request-scoped async session.

    Returns:
        One record per version whose report and band are both present.
    """
    # #ASSUME: external-resources: whole-corpus reads per request are
    # deliberate at v1 volumes, mirroring list_thresholds' no-cache stance;
    # revisit with an occurred_at window if the corpus grows past a few
    # thousand versions.
    # #VERIFY: tests/integration/test_moderation_dashboard_api.py.
    version_rows = (
        await session.execute(
            select(
                StorybookVersion.storybook_id,
                StorybookVersion.version,
                StorybookVersion.moderation_report,
                StorybookVersion.created_at,
                StorybookVersion.approved_by,
                func.jsonb_extract_path_text(
                    StorybookVersion.blob, "metadata", "age_band"
                ).label("age_band"),
            ).where(StorybookVersion.moderation_report.is_not(None))
        )
    ).all()

    moderated_at_by_version: dict[tuple[str, int], datetime] = {}
    moderation_events = (
        await session.execute(
            select(PipelineEvent.entity_id, PipelineEvent.occurred_at).where(
                PipelineEvent.entity_type == "storybook_version",
                PipelineEvent.event_type == EventType.MODERATION_COMPLETED.value,
            )
        )
    ).all()
    for entity_id, occurred_at in moderation_events:
        storybook_id, _, version_text = entity_id.rpartition(":")
        # #EDGE: data-integrity: a composite id that does not parse is
        # skipped, never a crash; that version falls back to created_at
        # ordering below.
        # #VERIFY: covered by the loader integration tests seeding valid ids.
        if not storybook_id or not version_text.isdigit():
            continue
        key = (storybook_id, int(version_text))
        existing = moderated_at_by_version.get(key)
        if existing is None or occurred_at > existing:
            moderated_at_by_version[key] = occurred_at

    decisions_by_storybook: dict[str, list[tuple[datetime, str]]] = {}
    decision_events = (
        await session.execute(
            select(
                PipelineEvent.entity_id,
                PipelineEvent.occurred_at,
                PipelineEvent.event_type,
            )
            .where(
                PipelineEvent.entity_type == "storybook",
                PipelineEvent.event_type.in_(
                    [EventType.RELEASED.value, EventType.SENT_BACK.value]
                ),
            )
            .order_by(PipelineEvent.occurred_at)
        )
    ).all()
    for entity_id, occurred_at, event_type in decision_events:
        decisions_by_storybook.setdefault(entity_id, []).append(
            (occurred_at, event_type)
        )

    records: list[VersionModerationRecord] = []
    for storybook_id, version, report, created_at, approved_by, age_band in version_rows:
        if not age_band:
            # #EDGE: data-integrity: imported or legacy blobs may lack
            # metadata.age_band; such versions cannot be attributed to a
            # band and are excluded rather than mis-bucketed.
            # #VERIFY: tests/integration/test_moderation_dashboard_api.py::
            # TestLoadVersionRecords::test_loader_skips_versions_without_band
            continue
        raw_findings = report.get("findings") if isinstance(report, dict) else None
        findings = (
            cast("list[Mapping[str, object]]", raw_findings)
            if isinstance(raw_findings, list)
            else []
        )
        moderated_at = moderated_at_by_version.get(
            (storybook_id, version), created_at
        )
        records.append(
            VersionModerationRecord(
                storybook_id=storybook_id,
                version=version,
                age_band=age_band,
                findings=findings,
                moderated_at=moderated_at,
                outcome=attribute_outcome(
                    moderated_at,
                    decisions_by_storybook.get(storybook_id, ()),
                    approved=approved_by is not None,
                ),
            )
        )
    return records
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --all-extras pytest tests/integration/test_moderation_dashboard_api.py tests/unit/test_moderation_insights.py -v`
Expected: all PASS

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff format src/cyo_adventure/moderation/insights.py tests/integration/test_moderation_dashboard_api.py
uv run ruff check src/cyo_adventure/moderation/insights.py tests/integration/test_moderation_dashboard_api.py
uv run basedpyright src/cyo_adventure/moderation/insights.py
git add src/cyo_adventure/moderation/insights.py tests/integration/test_moderation_dashboard_api.py
git commit -S -m "feat(moderation): WS-F version-record loader over reports and events"
```

---

### Task 4: Schemas + `GET /admin/moderation/dashboard` (depends-on: Task3 [output])

**Files:**
- Modify: `src/cyo_adventure/api/schemas.py` (append after `NoiseFloorUpdateBody`, around line 1001)
- Create: `src/cyo_adventure/api/moderation_dashboard.py`
- Modify: `src/cyo_adventure/app.py` (next to the `moderation_thresholds` include at line 182)
- Test: `tests/integration/test_moderation_dashboard_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_moderation_dashboard_api.py`:

```python
class TestDashboardEndpoint:
    async def test_dashboard_aggregates_override_rate(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        async with sessions() as session:
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_released",
                findings=[_finding("violence", "advisory")],
                decision=EventType.RELEASED,
            )
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_sent_back",
                findings=[_finding("violence", "flag")],
                decision=EventType.SENT_BACK,
            )
            await session.commit()

        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        body = res.json()
        rows = {
            (row["age_band"], row["category"]): row for row in body["insights"]
        }
        row = rows[("8-11", "violence")]
        assert row["advisory_findings"] == 1
        assert row["flag_findings"] == 1
        assert row["decided_versions"] == 2
        assert row["released_versions"] == 1
        assert row["override_rate"] == 0.5
        assert body["recent_changes"] == []

    async def test_dashboard_shows_recent_threshold_changes(
        self,
        client: AsyncClient,
        seed: Seed,
    ) -> None:
        put = await client.put(
            "/api/v1/admin/moderation-thresholds/8-11",
            params={"category": "violence"},
            json={"min_verdict": "block", "min_score": None},
            headers=auth(seed.admin_token),
        )
        assert put.status_code == 200

        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        changes = res.json()["recent_changes"]
        assert changes, "expected the threshold_changed event to appear"
        assert changes[0]["event_type"] == "threshold_changed"
        assert changes[0]["entity_id"] == "8-11"

    async def test_guardian_gets_403(self, client: AsyncClient, seed: Seed) -> None:
        res = await client.get(
            "/api/v1/admin/moderation/dashboard", headers=auth(seed.guardian_token)
        )
        assert res.status_code == 403
```

(Verified: the upsert emits `threshold_changed` with `entity_type="moderation_threshold"` and
`entity_id=age_band`, see `api/moderation_thresholds.py:221-223`; the category rides in the
payload.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --all-extras pytest tests/integration/test_moderation_dashboard_api.py -v -k Dashboard`
Expected: FAIL with 404 responses (route not registered yet)

- [ ] **Step 3: Add the response views**

Append to `src/cyo_adventure/api/schemas.py` after the `NoiseFloorUpdateBody` block (~line
1001). The file already imports `BaseModel` and `datetime`; verify and extend its imports if
not:

```python
class CategoryInsightView(BaseModel):
    """Override evidence for one (age_band, category) pair (WS-F)."""

    age_band: str
    category: str
    advisory_findings: int
    flag_findings: int
    decided_versions: int
    released_versions: int
    override_rate: float | None
    last_seen: datetime


class ThresholdChangeView(BaseModel):
    """One recent threshold or noise-floor change event (WS-F)."""

    occurred_at: datetime
    event_type: str
    entity_id: str
    payload: dict[str, object]


class ModerationDashboardView(BaseModel):
    """Aggregated moderation evidence for the admin dashboard (WS-F)."""

    insights: list[CategoryInsightView]
    recent_changes: list[ThresholdChangeView]


class ThresholdSuggestionView(BaseModel):
    """A computed threshold proposal awaiting admin ratification (WS-F)."""

    age_band: str
    category: str
    current_min_verdict: MinVerdict
    current_min_score: float | None
    suggested_min_verdict: MinVerdict
    override_rate: float
    decided_versions: int
    released_versions: int


class SuggestionListView(BaseModel):
    """Computed proposals plus the gates that produced them (WS-F)."""

    min_decided_versions: int
    min_override_rate: float
    suggestions: list[ThresholdSuggestionView]
```

- [ ] **Step 4: Create the router with the dashboard endpoint**

Create `src/cyo_adventure/api/moderation_dashboard.py`:

```python
"""Admin read-only moderation insight dashboard (WS-F).

Aggregates persisted moderation reports and the pipeline event log into
override evidence and threshold suggestions. Read-only: the only write in
the WS-F flow is the reused, audited threshold upsert in
``api/moderation_thresholds.py`` (decision F3).
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import (
    CategoryInsightView,
    ModerationDashboardView,
    SuggestionListView,
    ThresholdChangeView,
    ThresholdSuggestionView,
)
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import PipelineEvent
from cyo_adventure.events import EventType
from cyo_adventure.moderation.insights import (
    SUGGESTION_MIN_DECIDED,
    SUGGESTION_MIN_OVERRIDE_RATE,
    aggregate_insights,
    load_version_records,
    suggest_thresholds,
)
from cyo_adventure.moderation.thresholds import load_threshold_policy

router = APIRouter(prefix="/api/v1", tags=["moderation-dashboard"])

_RECENT_CHANGES_LIMIT = 20


def _require_admin(ctx: Context) -> None:
    """Reject non-admin principals before any read."""
    # #CRITICAL: security: these aggregates describe the moderation posture
    # across every family and drive threshold changes; admin-only (F5).
    # #VERIFY: tests/integration/test_moderation_dashboard_api.py::
    # TestDashboardEndpoint::test_guardian_gets_403 and
    # TestSuggestionsEndpoint::test_guardian_gets_403
    if not ctx.principal.is_admin:
        raise AuthorizationError("admin role required", required_permission="admin")


@router.get("/admin/moderation/dashboard")
async def moderation_dashboard(ctx: Context) -> ModerationDashboardView:
    """Aggregated override evidence plus recent threshold changes."""
    _require_admin(ctx)
    records = await load_version_records(ctx.session)
    insights = aggregate_insights(records)
    recent = (
        await ctx.session.scalars(
            select(PipelineEvent)
            .where(
                PipelineEvent.event_type.in_(
                    [
                        EventType.THRESHOLD_CHANGED.value,
                        EventType.NOISE_FLOOR_CHANGED.value,
                    ]
                )
            )
            .order_by(PipelineEvent.occurred_at.desc())
            .limit(_RECENT_CHANGES_LIMIT)
        )
    ).all()
    return ModerationDashboardView(
        insights=[
            CategoryInsightView(
                age_band=insight.age_band,
                category=insight.category,
                advisory_findings=insight.advisory_findings,
                flag_findings=insight.flag_findings,
                decided_versions=insight.decided_versions,
                released_versions=insight.released_versions,
                override_rate=insight.override_rate,
                last_seen=insight.last_seen,
            )
            for insight in insights
        ],
        recent_changes=[
            ThresholdChangeView(
                occurred_at=event.occurred_at,
                event_type=event.event_type,
                entity_id=event.entity_id,
                payload=event.payload,
            )
            for event in recent
        ],
    )
```

- [ ] **Step 5: Register the router**

In `src/cyo_adventure/app.py`, next to the existing include at line 182, add the import
alongside the `moderation_thresholds` import and register:

```python
app.include_router(moderation_dashboard.router)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --all-extras pytest tests/integration/test_moderation_dashboard_api.py -v`
Expected: `TestDashboardEndpoint` PASSES (suggestions tests arrive in Task 5)

- [ ] **Step 7: Lint, type-check, commit**

```bash
uv run ruff format src/cyo_adventure/api/moderation_dashboard.py src/cyo_adventure/api/schemas.py src/cyo_adventure/app.py tests/integration/test_moderation_dashboard_api.py
uv run ruff check src/cyo_adventure/api/ tests/integration/test_moderation_dashboard_api.py
uv run basedpyright src/
git add src/cyo_adventure/api/moderation_dashboard.py src/cyo_adventure/api/schemas.py src/cyo_adventure/app.py tests/integration/test_moderation_dashboard_api.py
git commit -S -m "feat(api): WS-F admin moderation dashboard endpoint"
```

---

### Task 5: `GET /admin/moderation/suggestions` + ratify round-trip (depends-on: Task4 [output], Task2 [output])

**Files:**
- Modify: `src/cyo_adventure/api/moderation_dashboard.py`
- Test: `tests/integration/test_moderation_dashboard_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_moderation_dashboard_api.py`:

```python
async def _seed_high_override_corpus(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Six released versions with a violence flag in band 8-11 (rate 1.0)."""
    async with sessions() as session:
        for index in range(6):
            await _seed_moderated_version(
                session,
                seed,
                storybook_id=f"s_corpus_{index}",
                findings=[_finding("violence", "flag")],
                decision=EventType.RELEASED,
                moderated_at=_T0 + timedelta(hours=index),
            )
        await session.commit()


class TestSuggestionsEndpoint:
    async def test_suggestion_appears_above_gates(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        await _seed_high_override_corpus(sessions, seed)

        res = await client.get(
            "/api/v1/admin/moderation/suggestions", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        body = res.json()
        assert body["min_decided_versions"] == 5
        assert body["min_override_rate"] == 0.8
        assert len(body["suggestions"]) == 1
        suggestion = body["suggestions"][0]
        assert suggestion["age_band"] == "8-11"
        assert suggestion["category"] == "violence"
        assert suggestion["current_min_verdict"] == "flag"
        assert suggestion["suggested_min_verdict"] == "block"
        assert suggestion["override_rate"] == 1.0
        assert suggestion["decided_versions"] == 6

    async def test_no_suggestion_below_volume(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        async with sessions() as session:
            await _seed_moderated_version(
                session,
                seed,
                storybook_id="s_lone",
                findings=[_finding("violence", "flag")],
                decision=EventType.RELEASED,
            )
            await session.commit()

        res = await client.get(
            "/api/v1/admin/moderation/suggestions", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        assert res.json()["suggestions"] == []

    async def test_applying_a_suggestion_retires_it(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
    ) -> None:
        """The F3 ratify loop: apply via the WS-A PUT, suggestion disappears."""
        await _seed_high_override_corpus(sessions, seed)

        put = await client.put(
            "/api/v1/admin/moderation-thresholds/8-11",
            params={"category": "violence"},
            json={"min_verdict": "block", "min_score": None},
            headers=auth(seed.admin_token),
        )
        assert put.status_code == 200

        res = await client.get(
            "/api/v1/admin/moderation/suggestions", headers=auth(seed.admin_token)
        )
        assert res.status_code == 200
        assert res.json()["suggestions"] == []

    async def test_guardian_gets_403(self, client: AsyncClient, seed: Seed) -> None:
        res = await client.get(
            "/api/v1/admin/moderation/suggestions", headers=auth(seed.guardian_token)
        )
        assert res.status_code == 403
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --all-extras pytest tests/integration/test_moderation_dashboard_api.py -v -k Suggestions`
Expected: FAIL with 404 (route not defined)

- [ ] **Step 3: Add the endpoint**

Append to `src/cyo_adventure/api/moderation_dashboard.py`:

```python
@router.get("/admin/moderation/suggestions")
async def moderation_suggestions(ctx: Context) -> SuggestionListView:
    """Computed threshold proposals awaiting admin ratification.

    Never applied automatically (umbrella decision 3); the apply control on
    the dashboard calls the existing audited threshold upsert (F3), and a
    raised threshold retires its own suggestion (F2).
    """
    _require_admin(ctx)
    records = await load_version_records(ctx.session)
    insights = aggregate_insights(records)
    policy = await load_threshold_policy(ctx.session)
    suggestions = suggest_thresholds(insights, policy)
    return SuggestionListView(
        min_decided_versions=SUGGESTION_MIN_DECIDED,
        min_override_rate=SUGGESTION_MIN_OVERRIDE_RATE,
        suggestions=[
            ThresholdSuggestionView(
                age_band=suggestion.age_band,
                category=suggestion.category,
                current_min_verdict=suggestion.current_min_verdict,
                current_min_score=suggestion.current_min_score,
                suggested_min_verdict=suggestion.suggested_min_verdict,
                override_rate=suggestion.override_rate,
                decided_versions=suggestion.decided_versions,
                released_versions=suggestion.released_versions,
            )
            for suggestion in suggestions
        ],
    )
```

Note: `ThresholdSuggestionView.current_min_verdict` is `MinVerdict` (a `Literal`); the
dataclass carries `str`. Pydantic validates the value at construction; if basedpyright flags
the assignment, narrow with `cast("MinVerdict", suggestion.current_min_verdict)` and import
`MinVerdict` from `cyo_adventure.api.schemas`.

If `load_threshold_policy`'s actual signature differs (check
`src/cyo_adventure/moderation/thresholds.py:137`), match the call site to it; do not change
the loader.

- [ ] **Step 4: Run the full backend suite**

Run: `uv run --all-extras pytest tests/integration/test_moderation_dashboard_api.py tests/unit/test_moderation_insights.py -v`
Expected: all PASS

Run: `uv run --all-extras pytest -q`
Expected: no regressions (baseline 2048 passed; now more)

- [ ] **Step 5: Lint, type-check, security-scan, commit**

```bash
uv run ruff format src/cyo_adventure/api/moderation_dashboard.py tests/integration/test_moderation_dashboard_api.py
uv run ruff check src/ tests/
uv run basedpyright src/
uv run bandit -r src -q
git add src/cyo_adventure/api/moderation_dashboard.py tests/integration/test_moderation_dashboard_api.py
git commit -S -m "feat(api): WS-F threshold suggestions endpoint with ratify round-trip"
```

---

### Task 6: Regenerate the OpenAPI client (depends-on: Task5 [completion])

New GET endpoints change the schema; the CI drift gate fails unless `frontend/src/client/` is
regenerated in the same PR. Never sort keys.

- [ ] **Step 1: Dump the schema in-process**

Run:
```bash
uv run python -c "import json; from cyo_adventure.app import app; print(json.dumps(app.openapi()))" > /tmp/cyo-openapi-wsf.json
```
Expected: exit 0; file is non-empty JSON.
Abort if: the import fails (endpoint wiring is broken; fix before regenerating).

- [ ] **Step 2: Regenerate**

Run:
```bash
cd frontend && npm ci && OPENAPI_INPUT=/tmp/cyo-openapi-wsf.json npm run generate-client
```
Expected: generator exits 0; `git status` shows changes under `frontend/src/client/` including
new types `ModerationDashboardView`, `SuggestionListView`, `ThresholdSuggestionView`,
`CategoryInsightView`, `ThresholdChangeView` in `types.gen.ts`.
Abort if: the diff touches files outside `frontend/src/client/`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/client
git commit -S -m "chore(frontend): regenerate OpenAPI client for WS-F dashboard endpoints"
```

---

### Task 7: Frontend adapter, page, routing, tests (depends-on: Task6 [output])

**Files:**
- Create: `frontend/src/guardian/moderationDashboardApi.ts`
- Create: `frontend/src/guardian/ModerationDashboardPage.tsx`
- Create: `frontend/src/guardian/ModerationDashboardPage.test.tsx`
- Modify: `frontend/src/routeElements.tsx` (lazy import, next to `ModerationThresholdsPage` at lines 80-84)
- Modify: `frontend/src/router.tsx` (admin children array at lines 104-124)

All commands in this task run from `frontend/`.

- [ ] **Step 1: Write the adapter**

Create `frontend/src/guardian/moderationDashboardApi.ts`:

```typescript
// Hand-typed adapter like moderationThresholdsApi.ts: the generated SDK in
// src/client/sdk.gen.ts is not used; axios calls inherit baseURL, auth,
// timeout, and 401 recovery from useApi()'s instance. Types come from the
// generated client so the OpenAPI drift gate keeps them honest.
import type { AxiosInstance } from 'axios'
import type {
  ModerationDashboardView,
  SuggestionListView,
} from '../client/types.gen'

const BASE_PATH = '/v1/admin/moderation'

export interface ModerationDashboardApi {
  dashboard(): Promise<ModerationDashboardView>
  suggestions(): Promise<SuggestionListView>
}

export function makeModerationDashboardApi(
  api: AxiosInstance
): ModerationDashboardApi {
  return {
    async dashboard(): Promise<ModerationDashboardView> {
      const res = await api.get<ModerationDashboardView>(`${BASE_PATH}/dashboard`)
      return res.data
    },
    async suggestions(): Promise<SuggestionListView> {
      const res = await api.get<SuggestionListView>(`${BASE_PATH}/suggestions`)
      return res.data
    },
  }
}
```

- [ ] **Step 2: Write the failing page tests**

Create `frontend/src/guardian/ModerationDashboardPage.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ModerationDashboardPage } from './ModerationDashboardPage'

const mockGet = vi.fn()
const mockPut = vi.fn()
const fakeApi = { get: mockGet, put: mockPut }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const DASHBOARD_VIEW = {
  insights: [
    {
      age_band: '8-11',
      category: 'violence',
      advisory_findings: 2,
      flag_findings: 4,
      decided_versions: 6,
      released_versions: 6,
      override_rate: 1.0,
      last_seen: '2026-07-01T12:00:00Z',
    },
  ],
  recent_changes: [
    {
      occurred_at: '2026-07-02T09:00:00Z',
      event_type: 'threshold_changed',
      entity_id: '8-11:violence',
      payload: {},
    },
  ],
}

const SUGGESTIONS_VIEW = {
  min_decided_versions: 5,
  min_override_rate: 0.8,
  suggestions: [
    {
      age_band: '8-11',
      category: 'violence',
      current_min_verdict: 'flag',
      current_min_score: null,
      suggested_min_verdict: 'block',
      override_rate: 1.0,
      decided_versions: 6,
      released_versions: 6,
    },
  ],
}

function mockGetByPath(overrides: Record<string, unknown> = {}) {
  mockGet.mockImplementation((path: string) => {
    if (path === '/v1/admin/moderation/suggestions') {
      return Promise.resolve({ data: overrides.suggestions ?? SUGGESTIONS_VIEW })
    }
    return Promise.resolve({ data: overrides.dashboard ?? DASHBOARD_VIEW })
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
})

describe('ModerationDashboardPage', () => {
  it('renders insights, suggestions, and recent changes', async () => {
    mockGetByPath()
    render(<ModerationDashboardPage />)
    expect(await screen.findByText(/violence/i)).toBeInTheDocument()
    expect(screen.getByText(/raise to block/i)).toBeInTheDocument()
    expect(screen.getByText(/threshold_changed/)).toBeInTheDocument()
  })

  it('applies a suggestion through the thresholds upsert and refreshes', async () => {
    const user = userEvent.setup()
    mockGetByPath()
    mockPut.mockResolvedValue({
      data: {
        age_band: '8-11',
        category: 'violence',
        min_verdict: 'block',
        min_score: null,
      },
    })
    render(<ModerationDashboardPage />)
    await screen.findByText(/raise to block/i)
    await user.click(screen.getByRole('button', { name: /apply/i }))
    expect(mockPut).toHaveBeenCalledWith(
      '/v1/admin/moderation-thresholds/8-11',
      { min_verdict: 'block', min_score: null },
      { params: { category: 'violence' } }
    )
    // Initial load fires 2 GETs; the post-apply refresh fires 2 more.
    expect(mockGet).toHaveBeenCalledTimes(4)
  })

  it('shows an empty state when there are no suggestions', async () => {
    mockGetByPath({
      suggestions: {
        min_decided_versions: 5,
        min_override_rate: 0.8,
        suggestions: [],
      },
    })
    render(<ModerationDashboardPage />)
    expect(
      await screen.findByText(/no threshold suggestions/i)
    ).toBeInTheDocument()
  })

  it('surfaces a load error', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    render(<ModerationDashboardPage />)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `npm run test:run -- src/guardian/ModerationDashboardPage.test.tsx`
Expected: FAIL (module `./ModerationDashboardPage` not found)

- [ ] **Step 4: Write the page**

Create `frontend/src/guardian/ModerationDashboardPage.tsx`, following the structure of
`ModerationThresholdsPage.tsx` (cancelled-guard load, `classifyApiError`, scoped action
error):

```tsx
import { useEffect, useMemo, useState } from 'react'
import type {
  ModerationDashboardView,
  SuggestionListView,
  ThresholdSuggestionView,
} from '../client/types.gen'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { makeModerationDashboardApi } from './moderationDashboardApi'
import { makeThresholdsApi } from './moderationThresholdsApi'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | {
      kind: 'ready'
      dashboard: ModerationDashboardView
      suggestions: SuggestionListView
    }

export function ModerationDashboardPage() {
  const api = useApi()
  const dashboardApi = useMemo(() => makeModerationDashboardApi(api), [api])
  const thresholdsApi = useMemo(() => makeThresholdsApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [actionError, setActionError] = useState<string | null>(null)
  const [applying, setApplying] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [dashboard, suggestions] = await Promise.all([
          dashboardApi.dashboard(),
          dashboardApi.suggestions(),
        ])
        if (!cancelled) setState({ kind: 'ready', dashboard, suggestions })
      } catch (err) {
        if (!cancelled)
          setState({ kind: 'error', message: classifyApiError(err).message })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [dashboardApi, reloadKey])

  async function applySuggestion(suggestion: ThresholdSuggestionView) {
    const key = `${suggestion.age_band}:${suggestion.category}`
    setApplying(key)
    setActionError(null)
    try {
      await thresholdsApi.upsert(suggestion.age_band, suggestion.category, {
        min_verdict: suggestion.suggested_min_verdict,
        min_score: suggestion.current_min_score ?? null,
      })
      setReloadKey((k) => k + 1)
    } catch (err) {
      setActionError(classifyApiError(err).message)
    } finally {
      setApplying(null)
    }
  }

  if (state.kind === 'loading') {
    return (
      <div role="status" aria-live="polite">
        Loading…
      </div>
    )
  }
  if (state.kind === 'error') {
    return <div role="alert">{state.message}</div>
  }

  const { dashboard, suggestions } = state
  return (
    <main>
      <h1>Moderation dashboard</h1>
      {actionError ? <div role="alert">{actionError}</div> : null}

      <section aria-labelledby="suggestions-heading">
        <h2 id="suggestions-heading">Threshold suggestions</h2>
        <p>
          Computed from override evidence (at least{' '}
          {suggestions.min_decided_versions} decided books and{' '}
          {Math.round(suggestions.min_override_rate * 100)}% released despite
          the finding). Nothing changes until you apply it.
        </p>
        {suggestions.suggestions.length === 0 ? (
          <p>No threshold suggestions right now.</p>
        ) : (
          <ul>
            {suggestions.suggestions.map((suggestion) => {
              const key = `${suggestion.age_band}:${suggestion.category}`
              return (
                <li key={key}>
                  <strong>
                    {suggestion.category} in {suggestion.age_band}
                  </strong>
                  : released {suggestion.released_versions} of{' '}
                  {suggestion.decided_versions} times despite the finding (
                  {Math.round(suggestion.override_rate * 100)}%). Raise to{' '}
                  {suggestion.suggested_min_verdict} (currently{' '}
                  {suggestion.current_min_verdict}).
                  <button
                    type="button"
                    disabled={applying === key}
                    onClick={() => void applySuggestion(suggestion)}
                  >
                    {applying === key
                      ? 'Applying…'
                      : `Apply: raise to ${suggestion.suggested_min_verdict}`}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="insights-heading">
        <h2 id="insights-heading">Override evidence</h2>
        {dashboard.insights.length === 0 ? (
          <p>No moderated books with advisory or flag findings yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th scope="col">Age band</th>
                <th scope="col">Category</th>
                <th scope="col">Advisories</th>
                <th scope="col">Flags</th>
                <th scope="col">Decided</th>
                <th scope="col">Released</th>
                <th scope="col">Override rate</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.insights.map((row) => (
                <tr key={`${row.age_band}:${row.category}`}>
                  <td>{row.age_band}</td>
                  <td>{row.category}</td>
                  <td>{row.advisory_findings}</td>
                  <td>{row.flag_findings}</td>
                  <td>{row.decided_versions}</td>
                  <td>{row.released_versions}</td>
                  <td>
                    {row.override_rate == null
                      ? 'n/a'
                      : `${Math.round(row.override_rate * 100)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="changes-heading">
        <h2 id="changes-heading">Recent threshold changes</h2>
        {dashboard.recent_changes.length === 0 ? (
          <p>No threshold changes recorded.</p>
        ) : (
          <ul>
            {dashboard.recent_changes.map((change) => (
              <li key={`${change.event_type}:${change.entity_id}:${change.occurred_at}`}>
                <code>{change.event_type}</code> {change.entity_id} at{' '}
                {new Date(change.occurred_at).toLocaleString()}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
```

The `classifyApiError` path is verified against `ModerationThresholdsPage.tsx:3`. If
`ThresholdsApi.upsert`'s body type requires `MinVerdict`, the generated literal type from
`suggested_min_verdict` already matches.

- [ ] **Step 5: Wire the route**

In `frontend/src/routeElements.tsx`, next to the `ModerationThresholdsPage` lazy export
(lines 80-84), add:

```typescript
export const ModerationDashboardPage = lazy(() =>
  import('./guardian/ModerationDashboardPage').then((m) => ({
    default: m.ModerationDashboardPage,
  }))
)
```

In `frontend/src/router.tsx`, inside the existing admin-only `ProtectedRoute` children array
(the one containing `path: 'moderation-thresholds'` at line ~120), add a sibling:

```typescript
{
  path: 'moderation-dashboard',
  element: suspended(<ModerationDashboardPage />),
},
```

(and extend the `routeElements` import at the top of `router.tsx` with
`ModerationDashboardPage`.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npm run test:run -- src/guardian/ModerationDashboardPage.test.tsx`
Expected: 4 tests PASS

Run: `npm run lint && npm run typecheck && npm run test:run`
Expected: clean; no regressions in the full Vitest suite

- [ ] **Step 7: Commit**

```bash
git add src/guardian/moderationDashboardApi.ts src/guardian/ModerationDashboardPage.tsx src/guardian/ModerationDashboardPage.test.tsx src/routeElements.tsx src/router.tsx
git commit -S -m "feat(frontend): WS-F moderation dashboard page with apply-suggestion flow"
```

---

### Task 8: Console links for admins (depends-on: Task7 [completion])

**Files:**
- Modify: `frontend/src/guardian/ConsolePage.tsx`
- Test: `frontend/src/guardian/ConsolePage.test.tsx`

Commands run from `frontend/`.

- [ ] **Step 1: Write the failing test**

Append to the existing describe block in `frontend/src/guardian/ConsolePage.test.tsx`, reusing
its `principal(role)` helper and existing mocks:

```typescript
it('shows moderation admin links for admins only', async () => {
  mockUseAuth.mockReturnValue(principal('admin'))
  renderPage()
  expect(
    await screen.findByRole('link', { name: /moderation dashboard/i })
  ).toHaveAttribute('href', '/guardian/moderation-dashboard')
  expect(
    screen.getByRole('link', { name: /moderation thresholds/i })
  ).toHaveAttribute('href', '/guardian/moderation-thresholds')
})

it('hides moderation admin links from plain guardians', async () => {
  mockUseAuth.mockReturnValue(principal('guardian'))
  renderPage()
  await screen.findByRole('heading', { name: /console/i })
  expect(
    screen.queryByRole('link', { name: /moderation dashboard/i })
  ).not.toBeInTheDocument()
})
```

`renderPage()` is the file's existing helper (line 48); it already wraps `ConsolePage` in a
`MemoryRouter`, so the new `Link`s render without further setup. Set up the endpoint mocks the
same way the surrounding tests do (`mockQueue(...)` etc.) before calling `renderPage()`, and
if the guardian-variant test's heading query does not match the actual console heading, reuse
whatever settled-state query the file's existing guardian-role test uses.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm run test:run -- src/guardian/ConsolePage.test.tsx`
Expected: the new test FAILS (links absent); pre-existing tests still pass

- [ ] **Step 3: Add the links**

In `frontend/src/guardian/ConsolePage.tsx`, next to the existing admin-only block
(`{principal?.role === 'admin' ? <RequestStoryForm mode="admin" /> : null}` at line ~198),
add (importing `Link` from `react-router-dom` if not already imported):

```tsx
{principal?.role === 'admin' ? (
  <nav aria-label="Moderation admin">
    <Link to="/guardian/moderation-dashboard">Moderation dashboard</Link>{' '}
    <Link to="/guardian/moderation-thresholds">Moderation thresholds</Link>
  </nav>
) : null}
```

If ConsolePage's existing tests render without a router and now fail on the `Link`, wrap the
render in `MemoryRouter` inside the test file rather than changing the component.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm run test:run -- src/guardian/ConsolePage.test.tsx`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/guardian/ConsolePage.tsx src/guardian/ConsolePage.test.tsx
git commit -S -m "feat(frontend): console links to the moderation admin pages"
```

---

### Task 9: CHANGELOG + full gate (depends-on: all prior [completion])

- [ ] **Step 1: Add the CHANGELOG entry**

In `CHANGELOG.md` under `## [Unreleased]`, add (create the `### Added` subsection if absent):

```markdown
### Added
- Admin moderation suggestion dashboard (WS-F): override evidence per
  (age band, category) aggregated from persisted moderation reports and the
  pipeline event log, computed threshold suggestions behind volume and rate
  gates, and an apply control that ratifies a suggestion through the existing
  audited threshold upsert. Two new admin-only GET endpoints under
  `/api/v1/admin/moderation/`; no migration, no new event type, no
  auto-calibration.
```

- [ ] **Step 2: Backend gate**

Run: `uv run --all-extras pytest -q`
Expected: all pass, coverage >= 80% (baseline was 2048 passed / 95.64%)
Abort if: any failure; fix before proceeding.

Run: `uv run ruff check . && uv run basedpyright src/ && uv run bandit -r src -q`
Expected: all clean

- [ ] **Step 3: Frontend gate**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:run && npm run build`
Expected: all clean

- [ ] **Step 4: Pre-commit and commit**

```bash
pre-commit run --all-files
git add CHANGELOG.md
git commit -S -m "docs(changelog): WS-F moderation suggestion dashboard entry"
```

- [ ] **Step 5: Whole-branch review checkpoint**

Per the WS process: run the Opus whole-branch review before opening the PR (the controller
session handles this; it is not a subagent implementation task). PR opens only after that
review's blocking findings are fixed. Merge is owner-gated, merge queue only.

---

## Self-review notes (already applied)

- Spec clause coverage: aggregation correctness (Tasks 1, 3, 4), co-occurrence coarseness
  (Task 1 dedupe test), suggestion gates and correct proposed verdict (Tasks 2, 5), ratify
  path reusing the WS-A PUT with audit + event (Task 5 round-trip test; audit/event emission
  itself is WS-A/WS-D-tested), 403 on both GETs (Tasks 4, 5), frontend render + apply through
  the shared thresholds adapter (Task 7), OpenAPI regen in-PR (Task 6), CHANGELOG (Task 9).
  The spec's "e2e only if the session decides" clause: decided NO new Playwright spec; the
  admin console flow has no existing e2e coverage precedent (`moderation` appears nowhere in
  `frontend/e2e/`), and Vitest covers the page contract. Revisit post-R2 if admin e2e becomes
  a tier.
- Per-verdict override rates (flag vs advisory separately) are NOT computed in v1; the
  combined rate plus separate finding counts match the ratified spec text. Noted here so the
  reviewer does not read it as an omission.
- Type consistency: `CategoryInsight`/`CategoryInsightView` and
  `ThresholdSuggestion`/`ThresholdSuggestionView` field names match one-to-one; adapter and
  page use the generated names (`advisory_findings`, `override_rate`, ...).
- Test commands name exact files (multi-tier suite; no bare `pytest tests/` in task steps).
- `frontend/src/client/` is committed (verified), so Task 6's commit is valid.
- Integration seeding writes `PipelineEvent` rows directly with explicit `occurred_at`,
  `actor_role="system"`, `actor_id=None` (satisfies the D2 CHECK), `payload={}` (non-null).
