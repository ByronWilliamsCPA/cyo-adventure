"""Unit tests for the admin re-moderation endpoint (moderation review redesign).

Mocking policy (mirrors tests/unit/test_moderation_pipeline.py and
tests/unit/test_rescreen_unit.py, org testing standard SS4.2/4.3):

- ``test_published_state_unchanged_after_real_remoderation`` runs the REAL
  ``run_moderation_pipeline`` (real stage functions, real report/routing
  logic, real ``publishing.service.submit``/``auto_reject``), doubling only
  the review LLM backend seam (``pipeline_mod.build_review_provider``),
  exactly like ``tests/unit/test_moderation_pipeline.py::
  test_pipeline_locks_storybook_row_for_update``. This is the test that
  proves the StateTransitionError-catch logic actually works against
  production code, not a stub.
- Every other test doubles ``remoderate.run_moderation_pipeline`` wholesale
  (an ``AsyncMock``), since they exercise this module's own gating/plumbing
  (auth, 404s, status scope, event payload, locking), not the pipeline's
  internals.
- The DB session is the shared spec'd ``AsyncMock`` (``mock_async_session``,
  tests/unit/conftest.py); no live database in unit tests.
"""

from __future__ import annotations

import asyncio
import copy
import uuid
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from cyo_adventure.api import remoderate as remoderate_api
from cyo_adventure.api.deps import Principal, RequestContext, Role
from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
    StateTransitionError,
)
from cyo_adventure.db.models import GenerationJob, Storybook, StorybookVersion
from cyo_adventure.events import Actor
from cyo_adventure.generation.import_story import IMPORT_PROVIDER
from cyo_adventure.generation.provider import _CANNED_STORY, MockProvider
from cyo_adventure.moderation import pipeline as pipeline_mod
from cyo_adventure.publishing.state_machine import (
    LEGAL_TRANSITIONS,
    Action,
    Status,
)
from cyo_adventure.validator.gate import run_fill_gate

if TYPE_CHECKING:
    from sqlalchemy import Select

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

_FAMILY = uuid.uuid4()
_ADMIN = Principal(
    subject="admin-x",
    user_id=uuid.uuid4(),
    role=Role.ADMIN,
    family_id=_FAMILY,
    profile_ids=frozenset(),
)
_GUARDIAN = Principal(
    subject="guardian-x",
    user_id=uuid.uuid4(),
    role=Role.GUARDIAN,
    family_id=_FAMILY,
    profile_ids=frozenset(),
)

_NODE_COUNT = len(cast("list[object]", _CANNED_STORY["nodes"]))
_REVIEW_BUDGET = 4 * (2 * _NODE_COUNT + 2)

# Generous enough that a loaded CI runner never trips it, short enough that a
# genuine deadlock fails in seconds rather than at the job timeout.
_SLOT_TEST_TIMEOUT = 10.0


def _ctx(principal: Principal, session: AsyncMock) -> RequestContext:
    return RequestContext(principal=principal, session=session)


def _blob() -> dict[str, object]:
    return copy.deepcopy(_CANNED_STORY)


def _story(status: str = "published") -> Storybook:
    return Storybook(id="s1", family_id=_FAMILY, status=status)


def _version_row(
    moderation_report: dict[str, object] | None = None,
    *,
    provider: str = "mock",
    model: str | None = "gen-model",
) -> StorybookVersion:
    return StorybookVersion(
        storybook_id="s1",
        version=1,
        blob=_blob(),
        model=model,
        provider=provider,
        moderation_report=moderation_report,
    )


def _report_summary(version_row: StorybookVersion) -> dict[str, object]:
    """Typed access to the stored report's ``summary`` dict.

    ``moderation_report`` is JSONB (``dict[str, object] | None``), so both
    subscripts are unknowable to basedpyright's strict mode; assert the
    runtime shape once here instead of casting at every call site.
    """
    report = version_row.moderation_report
    assert report is not None
    summary = report["summary"]
    assert isinstance(summary, dict)
    return cast("dict[str, object]", summary)


def _execute_result(value: object) -> MagicMock:
    """Fake a `Result` whose `scalar_one_or_none()` returns ``value``."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_result(rows: list[str]) -> MagicMock:
    """Fake a `ScalarResult` whose `.all()` returns ``rows`` (child names)."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _wire_session(
    session: AsyncMock,
    story: Storybook | None,
    version_row: StorybookVersion | None,
    *,
    child_names: list[str] | None = None,
) -> None:
    """Wire a mock session for the load-lock-check pattern this module uses.

    ``session.execute`` dispatches on the queried entity type (mirrors
    tests/unit/test_moderation_pipeline.py::_load): this module's own
    Storybook lock-load runs first, and a REAL ``run_moderation_pipeline``
    call (the real-pipeline test) re-executes its own Storybook select PLUS
    a GenerationJob select (the personalizable-slot resolution); returning
    the Storybook for both would make the pipeline treat a Storybook as a
    GenerationJob and crash on a missing attribute.
    """

    def _execute_side_effect(stmt: Select[tuple[object]]) -> MagicMock:
        if stmt.column_descriptions[0]["type"] is GenerationJob:
            return _execute_result(None)
        return _execute_result(story)

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    session.get = AsyncMock(return_value=version_row)
    session.scalars = AsyncMock(return_value=_scalars_result(child_names or []))
    session.add = MagicMock()
    session.flush = AsyncMock()


def _remod_ctx(
    *, settings: Settings | None = None, actor: Actor | None = None
) -> remoderate_api.RemoderateContext:
    return remoderate_api.RemoderateContext(
        settings=settings or Settings(),
        actor=actor or Actor.system(),
    )


def _clean_review_provider() -> MockProvider:
    """A review backend double that answers every stage with a passing verdict.

    Mirrors tests/unit/test_moderation_pipeline.py::_verdict_review_provider
    exactly (duplicated rather than imported: that helper is private to its
    own test module).
    """

    def _respond(prompt: str) -> str:
        if prompt.startswith("Age band:"):
            return '{"verdict": "safe", "reason": "ok"}'
        if prompt.startswith("Flesch-Kincaid"):
            return '{"verdict": "pass", "reason": "ok"}'
        return '{"verdict": "pass", "reason": "ok"}'

    return MockProvider(responses=[_respond] * _REVIEW_BUDGET)


# ---------------------------------------------------------------------------
# Admin gate
# ---------------------------------------------------------------------------


async def test_non_admin_rejected_with_403_before_any_query(
    mock_async_session: AsyncMock,
) -> None:
    """A guardian caller is rejected before the storybook row is even loaded."""
    ctx = _ctx(_GUARDIAN, mock_async_session)

    with pytest.raises(AuthorizationError):
        await remoderate_api.trigger_remoderate("s1", 1, ctx)

    mock_async_session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# 404 / scope checks (core function, pipeline never invoked)
# ---------------------------------------------------------------------------


async def test_unknown_storybook_raises_404(mock_async_session: AsyncMock) -> None:
    _wire_session(mock_async_session, None, None)
    ctx = _remod_ctx()

    with pytest.raises(ResourceNotFoundError):
        await remoderate_api.remoderate_storybook_version(
            mock_async_session, "missing", 1, ctx
        )


async def test_unknown_version_raises_404(mock_async_session: AsyncMock) -> None:
    _wire_session(mock_async_session, _story(), None)
    ctx = _remod_ctx()

    with pytest.raises(ResourceNotFoundError):
        await remoderate_api.remoderate_storybook_version(
            mock_async_session, "s1", 99, ctx
        )


@pytest.mark.parametrize("status", ["draft", "needs_revision", "archived"])
async def test_non_remoderatable_status_rejected(
    status: str, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every status outside REMODERATABLE_STATUSES is rejected pre-pipeline.

    'in_review' left this set deliberately. For the three that remain, the
    pipeline's terminal submit/auto_reject IS a legal hop and would actually
    move the story, which is the ordinary generation path's job, not this
    endpoint's.
    """
    _wire_session(mock_async_session, _story(status=status), _version_row())
    pipeline = AsyncMock()
    monkeypatch.setattr(remoderate_api, "run_moderation_pipeline", pipeline)
    ctx = _remod_ctx()

    with pytest.raises(BusinessLogicError, match="not re-moderatable"):
        await remoderate_api.remoderate_storybook_version(
            mock_async_session, "s1", 1, ctx
        )
    pipeline.assert_not_awaited()


async def test_in_review_status_is_accepted(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """in_review reaches the pipeline instead of being rejected at the guard.

    The seventeen books this widening exists for are all in_review, and every
    whole-book re-derivation path in the codebase was published-scoped, so
    before this the endpoint refused exactly the books that most needed it.
    """
    version_row = _version_row()

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.moderation_report = _PASSING_REPORT

    _wire_session(mock_async_session, _story(status="in_review"), version_row)
    pipeline = AsyncMock(side_effect=_fake_pipeline)
    monkeypatch.setattr(remoderate_api, "run_moderation_pipeline", pipeline)

    result = await remoderate_api.remoderate_storybook_version(
        mock_async_session, "s1", 1, _remod_ctx()
    )

    pipeline.assert_awaited_once()
    assert result.status == "in_review"


async def test_in_review_status_is_not_changed_by_remoderation(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The book stays in_review: the same structural proof the published path uses.

    LEGAL_TRANSITIONS holds (DRAFT, SUBMIT) and (NEEDS_REVISION, SUBMIT) but no
    (IN_REVIEW, SUBMIT), and (DRAFT, AUTO_REJECT) but no (IN_REVIEW,
    AUTO_REJECT), so the pipeline's terminal call always raises and this
    endpoint's catch discards only the illegal move. _persist_report runs
    BEFORE that attempt, so the fresh report survives. ADR-005 keeps every
    status change a human's.
    """
    story = _story(status="in_review")
    version_row = _version_row()

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.moderation_report = _PASSING_REPORT
        raise StateTransitionError(
            "cannot submit", rule="invalid_state_transition", context={}
        )

    _wire_session(mock_async_session, story, version_row)
    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_fake_pipeline)
    )

    result = await remoderate_api.remoderate_storybook_version(
        mock_async_session, "s1", 1, _remod_ctx()
    )

    assert story.status == "in_review"
    assert result.status == "in_review"
    assert version_row.moderation_report == _PASSING_REPORT


# ---------------------------------------------------------------------------
# Concurrency: the storybook load must carry SELECT ... FOR UPDATE
# ---------------------------------------------------------------------------


async def test_locks_storybook_row_for_update(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors test_approval_unit.py::test_load_admin_story_locks_row_for_update.

    A concurrent guardian/admin approve() (api/approval.py::_load_admin_story)
    or a second re-moderate call on the same storybook must block behind this
    lock rather than both reading a stale status.
    """
    version_row = _version_row()
    _wire_session(mock_async_session, _story(), version_row)
    monkeypatch.setattr(remoderate_api, "run_moderation_pipeline", AsyncMock())

    await remoderate_api.remoderate_storybook_version(
        mock_async_session, "s1", 1, _remod_ctx()
    )

    stmt = cast("Select[tuple[object]]", mock_async_session.execute.await_args.args[0])
    where = str(stmt.whereclause)
    assert "storybook" in where.lower()

    rendered = str(stmt.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in rendered
    assert "SKIP LOCKED" not in rendered
    assert "NOWAIT" not in rendered


# ---------------------------------------------------------------------------
# Happy path (pipeline mocked wholesale)
# ---------------------------------------------------------------------------


async def test_happy_path_returns_fresh_summary(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The endpoint returns the fresh, persisted report's verdict summary.

    Simulates exactly what run_moderation_pipeline leaves behind: a
    persisted (merged) report on version_row.moderation_report, then a
    StateTransitionError from its terminal submit() call (published is not a
    legal SUBMIT source), which this module must swallow.
    """
    version_row = _version_row(
        moderation_report={
            "findings": [{"verdict": "flag", "structural": False}],
            "summary": {
                "hard_block": False,
                "soft_flag": True,
                "count": 1,
                "repaired": False,
                "reviewer_independent": True,
            },
            "aggregate": {"nodes_reviewed": 3, "pass_counts": {}},
        }
    )
    story = _story()
    _wire_session(mock_async_session, story, version_row)

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.moderation_report = {
            "findings": [{"verdict": "block", "structural": True}],
            "summary": {
                "hard_block": True,
                "soft_flag": False,
                "count": 1,
                "repaired": False,
                "reviewer_independent": True,
            },
            "aggregate": {"nodes_reviewed": 3, "pass_counts": {}},
        }
        raise StateTransitionError(
            "cannot 'auto_reject' a storybook in its current state",
            rule="invalid_state_transition",
            context={"from": "published", "action": "auto_reject"},
        )

    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_fake_pipeline)
    )

    ctx = _ctx(_ADMIN, mock_async_session)
    view = await remoderate_api.trigger_remoderate("s1", 1, ctx)

    assert view.storybook_id == "s1"
    assert view.version == 1
    assert view.status == "published"
    assert view.overall_verdict == "block"
    assert view.verdict_counts == {"block": 1}
    assert view.structural_count == 1
    assert view.prior_reviewer_independent is True
    assert story.status == "published"


_PASSING_REPORT: dict[str, object] = {
    "findings": [{"verdict": "flag", "structural": False}],
    "summary": {
        "hard_block": False,
        "soft_flag": True,
        "count": 1,
        "repaired": False,
        "reviewer_independent": True,
    },
    "aggregate": {"nodes_reviewed": 3, "pass_counts": {}},
}


async def test_import_provenance_falls_back_to_default_provider(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 'import' provenance sentinel must not be treated as a provider name.

    Offline-authored books store ``provider="import"``
    (generation/import_story.py's ``IMPORT_PROVIDER``), which
    ``build_provider`` rejects with ConfigurationError; before the fix that
    failed the whole re-moderation before any review ran (found live by the
    2026-08-01 ops sweep: 9 of its 10 targets were imports). Imported rows
    must fall back to the configured default provider, dropping the stored
    model with the unusable provider name.
    """
    version_row = _version_row(
        copy.deepcopy(_PASSING_REPORT), provider=IMPORT_PROVIDER, model=None
    )
    story = _story()
    _wire_session(mock_async_session, story, version_row)

    captured: dict[str, object] = {}

    def _capture_build(settings: Settings, **kwargs: object) -> MockProvider:
        captured.update(kwargs)
        return MockProvider(responses=["{}"])

    monkeypatch.setattr(remoderate_api, "build_provider", _capture_build)
    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(return_value=None)
    )

    ctx = _ctx(_ADMIN, mock_async_session)
    view = await remoderate_api.trigger_remoderate("s1", 1, ctx)

    # "lane" pins D1 (2026-08-23, UW-C346): remoderation re-reviews a book
    # that belongs to a family, so it may not reach the direct account.
    assert captured == {
        "provider_override": None,
        "model_override": None,
        "lane": "family",
    }
    assert view.status == "published"


async def test_generated_provenance_passes_provider_and_model_through(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real generation-provider name and its model still reach build_provider.

    Guards the else branch of the import-sentinel fallback: the repair
    re-prompt for a generated book must keep using the provider/model that
    produced the book, not silently degrade to the configured default.
    """
    version_row = _version_row(
        copy.deepcopy(_PASSING_REPORT), provider="openrouter", model="m-1"
    )
    story = _story()
    _wire_session(mock_async_session, story, version_row)

    captured: dict[str, object] = {}

    def _capture_build(settings: Settings, **kwargs: object) -> MockProvider:
        captured.update(kwargs)
        return MockProvider(responses=["{}"])

    monkeypatch.setattr(remoderate_api, "build_provider", _capture_build)
    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(return_value=None)
    )

    ctx = _ctx(_ADMIN, mock_async_session)
    view = await remoderate_api.trigger_remoderate("s1", 1, ctx)

    assert captured == {
        "provider_override": "openrouter",
        "model_override": "m-1",
        "lane": "family",
    }
    assert view.status == "published"


async def test_event_actor_role_is_admin(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pipeline event is stamped with the 'admin' acting role, not the base role.

    Mirrors tests/unit/test_rescreen_unit.py::test_event_actor_role_is_admin:
    a dual-role guardian+admin is audited in the capacity that authorized
    the re-moderation.
    """
    version_row = _version_row()
    _wire_session(mock_async_session, _story(), version_row)

    async def _fake_pipeline(**_kwargs: object) -> None:
        raise StateTransitionError(
            "cannot submit", rule="invalid_state_transition", context={}
        )

    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_fake_pipeline)
    )

    ctx = _ctx(_ADMIN, mock_async_session)
    await remoderate_api.trigger_remoderate("s1", 1, ctx)

    added = mock_async_session.add.call_args.args[0]
    assert added.actor_role == "admin"
    assert added.event_type == "storybook_remoderated"


async def test_event_records_prior_reviewer_independent_provenance(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The audit event carries the PRIOR (pre-call) report's provenance marker.

    The prior stored report is mock-moderated (reviewer_independent=False,
    design doc 2.4's durable stamp); the fresh report the pipeline leaves
    behind is independent. The event must carry the PRIOR value, snapshotted
    before the call overwrites version_row.moderation_report.
    """
    version_row = _version_row(
        moderation_report={
            "findings": [],
            "summary": {
                "hard_block": False,
                "soft_flag": False,
                "count": 0,
                "repaired": False,
                "reviewer_independent": False,
            },
            "aggregate": {"nodes_reviewed": 3, "pass_counts": {}},
        }
    )
    _wire_session(mock_async_session, _story(), version_row)

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.moderation_report = {
            "findings": [],
            "summary": {
                "hard_block": False,
                "soft_flag": False,
                "count": 0,
                "repaired": False,
                "reviewer_independent": True,
            },
            "aggregate": {"nodes_reviewed": 3, "pass_counts": {}},
        }
        raise StateTransitionError(
            "cannot submit", rule="invalid_state_transition", context={}
        )

    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_fake_pipeline)
    )

    result = await remoderate_api.remoderate_storybook_version(
        mock_async_session, "s1", 1, _remod_ctx(actor=Actor.from_principal(_ADMIN))
    )

    assert result.prior_reviewer_independent is False
    added = mock_async_session.add.call_args.args[0]
    assert added.payload["prior_reviewer_independent"] is False


# ---------------------------------------------------------------------------
# Mock-reviewer guard interaction (decision 6): no bypass added here.
# ---------------------------------------------------------------------------


async def test_mock_reviewer_stamp_is_not_stripped_or_overridden(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh mock-reviewer-stamped report is surfaced verbatim, not bypassed.

    Simulates the exact persisted shape run_moderation_pipeline's own
    _stamp_mock_reviewer leaves behind (design doc 2.4, pipeline.py lines
    ~166-189: reviewer_independent overridden to False plus a structural
    advisory finding carrying concern="mock_reviewer_active") when the
    CYO_ADVENTURE_ALLOW_MOCK_REVIEW escape hatch is active outside local.
    This module adds no logic that reads or special-cases that stamp: it
    only reads summary.hard_block/soft_flag and the findings list, so the
    stamp rides through into the response and the audit event exactly as
    the pipeline produced it, with no override of its own.
    """
    version_row = _version_row()
    _wire_session(mock_async_session, _story(), version_row)

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.moderation_report = {
            "findings": [
                {
                    "verdict": "advisory",
                    "structural": True,
                    "concern": "mock_reviewer_active",
                }
            ],
            "summary": {
                "hard_block": False,
                "soft_flag": False,
                "count": 1,
                "repaired": False,
                "reviewer_independent": False,
            },
            "aggregate": {"nodes_reviewed": 3, "pass_counts": {}},
        }
        raise StateTransitionError(
            "cannot submit", rule="invalid_state_transition", context={}
        )

    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_fake_pipeline)
    )

    result = await remoderate_api.remoderate_storybook_version(
        mock_async_session, "s1", 1, _remod_ctx()
    )

    assert result.overall_verdict == "pass"
    assert result.verdict_counts == {"advisory": 1}
    assert result.structural_count == 1
    assert _report_summary(version_row)["reviewer_independent"] is False


# ---------------------------------------------------------------------------
# Real pipeline: published status genuinely survives the terminal call.
# ---------------------------------------------------------------------------


async def test_published_state_unchanged_after_real_remoderation(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drives the REAL run_moderation_pipeline against a published book.

    Proves the StateTransitionError-catch logic works against production
    code, not a stub: publishing.service.submit's own assert_transition call
    genuinely raises for a 'published' source state, and this module
    genuinely swallows it while keeping the freshly persisted report.
    """
    story = _story(status="published")
    version_row = _version_row(
        moderation_report={
            "findings": [
                {
                    "verdict": "advisory",
                    "structural": True,
                    "concern": "mock_reviewer_active",
                }
            ],
            "summary": {
                "hard_block": False,
                "soft_flag": False,
                "count": 1,
                "repaired": False,
                "reviewer_independent": False,
            },
            "aggregate": {"nodes_reviewed": 0, "pass_counts": {}},
        }
    )
    _wire_session(mock_async_session, story, version_row)

    def _build(settings: Settings, **kwargs: object) -> tuple[MockProvider, bool]:
        del settings, kwargs
        return _clean_review_provider(), True

    monkeypatch.setattr(pipeline_mod, "build_review_provider", _build)

    result = await remoderate_api.remoderate_storybook_version(
        mock_async_session,
        "s1",
        1,
        _remod_ctx(settings=Settings(), actor=Actor.from_principal(_ADMIN)),
    )

    assert story.status == "published"
    assert result.status == "published"
    assert _report_summary(version_row)["hard_block"] is False
    # The fresh (real, merged) report replaced the stale mock-moderated one:
    # the mock_reviewer_active advisory from the PRIOR report is gone, and
    # reviewer_independent is now True (the clean review_seam double, not
    # the mock backend).
    assert _report_summary(version_row)["reviewer_independent"] is True
    assert result.prior_reviewer_independent is False
    mock_async_session.add.assert_called_once()


def _flagging_review_provider() -> MockProvider:
    """A review backend double whose safety verdict is a soft FLAG.

    Same shape as ``_clean_review_provider``, but every safety prompt (single
    or batched, both start with "Age band:", moderation/stages.py) returns a
    structured ``flag`` verdict, so the resulting report satisfies exactly
    the repair branch's precondition (``has_soft_flag and not
    has_hard_block``, moderation/pipeline.py).
    """

    def _respond(prompt: str) -> str:
        if prompt.startswith("Age band:"):
            return (
                '{"verdict": "flag", "concern": "frightening_content", '
                '"severity": "low", "reason": "test flag"}'
            )
        return '{"verdict": "pass", "reason": "ok"}'

    return MockProvider(responses=[_respond] * _REVIEW_BUDGET)


async def test_published_blob_unchanged_when_repair_disallowed(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A soft-FLAG re-moderation must never rewrite the published blob.

    Drives the REAL ``run_moderation_pipeline`` with a review double whose
    safety verdict is a soft FLAG, the exact precondition under which the
    generation path would attempt the bounded auto-repair (and, on adoption,
    assign ``version_row.blob = revised``). ``api/remoderate.py`` passes
    ``allow_repair=False``, so the repair branch must short-circuit before
    ``_attempt_and_adopt_repair`` is ever awaited and the published prose a
    guardian approved (ADR-005) stays byte-identical.
    """
    story = _story(status="published")
    version_row = _version_row()
    blob_snapshot = copy.deepcopy(version_row.blob)
    _wire_session(mock_async_session, story, version_row)

    def _build(settings: Settings, **kwargs: object) -> tuple[MockProvider, bool]:
        del settings, kwargs
        return _flagging_review_provider(), True

    monkeypatch.setattr(pipeline_mod, "build_review_provider", _build)
    repair = AsyncMock()
    monkeypatch.setattr(pipeline_mod, "_attempt_and_adopt_repair", repair)

    result = await remoderate_api.remoderate_storybook_version(
        mock_async_session,
        "s1",
        1,
        _remod_ctx(settings=Settings(), actor=Actor.from_principal(_ADMIN)),
    )

    repair.assert_not_awaited()
    assert version_row.blob == blob_snapshot
    assert story.status == "published"
    assert result.status == "published"
    # The FLAG itself was recorded, not repaired away: reporting on a
    # published book is this endpoint's whole contract, editing it is not.
    assert _report_summary(version_row)["soft_flag"] is True
    assert _report_summary(version_row)["hard_block"] is False


# ---------------------------------------------------------------------------
# _summarize_report: JSONB shapes the annotation does not actually guarantee
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        pytest.param(None, ("pass", {}, 0), id="never-moderated"),
        pytest.param({"summary": None}, ("pass", {}, 0), id="null-summary"),
        pytest.param({"summary": "corrupt"}, ("pass", {}, 0), id="non-dict-summary"),
        pytest.param(
            {"summary": {"hard_block": True}, "findings": "corrupt"},
            ("block", {}, 0),
            id="non-list-findings",
        ),
        pytest.param(
            {"summary": {}, "findings": ["not-a-dict", None, 7]},
            ("pass", {}, 0),
            id="non-dict-finding-elements",
        ),
        pytest.param(
            {"summary": {"soft_flag": True}, "findings": [{"structural": True}]},
            ("flag", {"unknown": 1}, 1),
            id="finding-without-verdict",
        ),
        pytest.param(
            {"summary": {}, "findings": [{"verdict": 42}]},
            ("pass", {"unknown": 1}, 0),
            id="non-string-verdict",
        ),
    ],
)
async def test_summarize_report_tolerates_malformed_shapes(
    report: dict[str, object] | None, expected: tuple[str, dict[str, int], int]
) -> None:
    """A stored report is JSONB, so its runtime shape is not the annotation.

    ``cast`` is erased at runtime and validates nothing. Every one of these
    shapes would raise AttributeError or TypeError under cast-only reads, and
    would do so AFTER the pipeline had already written its fresh report,
    turning a cosmetic summarization step into a failed request.

    Async despite awaiting nothing: this module's ``pytestmark`` applies
    ``pytest.mark.asyncio`` module-wide, and pytest-asyncio warns on a sync
    test carrying that mark, which ``filterwarnings = ["error"]`` escalates
    to a failure (tests/CLAUDE.md, "pytest conventions").
    """
    assert remoderate_api._summarize_report(report) == expected


# ---------------------------------------------------------------------------
# Unexpected pipeline failure: propagate (so the unit-of-work rolls back)
# ---------------------------------------------------------------------------


async def test_provider_failure_logs_and_propagates(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anything other than StateTransitionError must reach the caller.

    api/deps.py::get_db_session rolls the request transaction back on any
    exception, which is both why the failure must propagate (a half-run
    re-moderation must not be committed) and why this path logs instead of
    recording a pipeline event: an event row written here would be discarded
    by that same rollback, so writing one would only manufacture the
    appearance of an audit trail.
    """
    story = _story()
    version_row = _version_row()
    _wire_session(mock_async_session, story, version_row)

    monkeypatch.setattr(
        remoderate_api,
        "run_moderation_pipeline",
        AsyncMock(side_effect=RuntimeError("provider timeout")),
    )
    logger = MagicMock()
    monkeypatch.setattr(remoderate_api, "_logger", logger)
    ctx = _remod_ctx(actor=Actor.from_principal(_ADMIN))

    with pytest.raises(RuntimeError, match="provider timeout"):
        await remoderate_api.remoderate_storybook_version(
            mock_async_session,
            "s1",
            1,
            ctx,
        )

    # No event was recorded: record_event's only write path is session.add.
    mock_async_session.add.assert_not_called()
    logger.exception.assert_called_once()
    assert logger.exception.call_args.args[0] == "remoderate.failed"
    assert logger.exception.call_args.kwargs["error_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# A fresh hard block on a published book has to be visible somewhere
# ---------------------------------------------------------------------------


async def test_hard_block_on_published_book_logs_warning(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A block leaves the book published and readable, so it must be shouted.

    No existing surface shows this state: the review queue filters to
    IN_REVIEW and StorybookSummary has no verdict field, so a freshly-blocked
    published book renders identically to a healthy one. The WARNING plus the
    pipeline event are the entire signal.
    """
    story = _story()
    version_row = _version_row()
    _wire_session(mock_async_session, story, version_row)

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.moderation_report = {
            "findings": [{"verdict": "block", "structural": True}],
            "summary": {
                "hard_block": True,
                "soft_flag": False,
                "count": 1,
                "repaired": False,
                "reviewer_independent": True,
            },
            "aggregate": {"nodes_reviewed": 3, "pass_counts": {}},
        }

    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_fake_pipeline)
    )
    logger = MagicMock()
    monkeypatch.setattr(remoderate_api, "_logger", logger)

    result = await remoderate_api.remoderate_storybook_version(
        mock_async_session,
        "s1",
        1,
        _remod_ctx(actor=Actor.from_principal(_ADMIN)),
    )

    assert result.overall_verdict == "block"
    # The block changed nothing about the book itself; that is the point.
    assert story.status == "published"
    logger.warning.assert_called_once()
    assert (
        logger.warning.call_args.args[0]
        == "remoderate.hard_block_without_status_change"
    )
    assert logger.warning.call_args.kwargs["status"] == "published"
    assert logger.warning.call_args.kwargs["storybook_id"] == "s1"


async def test_clean_verdict_logs_no_hard_block_warning(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The block warning must not fire for a clean re-moderation."""
    story = _story()
    version_row = _version_row()
    _wire_session(mock_async_session, story, version_row)

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.moderation_report = {
            "findings": [],
            "summary": {
                "hard_block": False,
                "soft_flag": False,
                "count": 0,
                "repaired": False,
                "reviewer_independent": True,
            },
            "aggregate": {"nodes_reviewed": 3, "pass_counts": {}},
        }

    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_fake_pipeline)
    )
    logger = MagicMock()
    monkeypatch.setattr(remoderate_api, "_logger", logger)

    result = await remoderate_api.remoderate_storybook_version(
        mock_async_session,
        "s1",
        1,
        _remod_ctx(actor=Actor.from_principal(_ADMIN)),
    )

    assert result.overall_verdict == "pass"
    logger.warning.assert_not_called()


# ---------------------------------------------------------------------------
# Single-flight: one re-moderation per worker
# ---------------------------------------------------------------------------


async def test_second_concurrent_remoderation_is_rejected(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second in-flight call is rejected, not queued.

    One re-moderation is dozens of review-model calls; the app-wide 60/min
    per-IP limit would happily admit 60 of them concurrently. Rejecting is
    deliberate: queueing inside the request would hold connections and turn a
    burst into pool exhaustion instead of a clear error.
    """
    story = _story()
    version_row = _version_row()
    _wire_session(mock_async_session, story, version_row)

    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_pipeline(**_kwargs: object) -> None:
        started.set()
        await release.wait()
        version_row.moderation_report = {
            "findings": [],
            "summary": {
                "hard_block": False,
                "soft_flag": False,
                "count": 0,
                "repaired": False,
                "reviewer_independent": True,
            },
            "aggregate": {"nodes_reviewed": 3, "pass_counts": {}},
        }

    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_slow_pipeline)
    )

    ctx = _ctx(_ADMIN, mock_async_session)
    first = asyncio.create_task(remoderate_api.trigger_remoderate("s1", 1, ctx))
    # Bound both waits. This project installs no pytest-timeout, so an
    # unbounded wait here would not fail the test, it would hang the whole
    # pytest process until the CI job's own timeout killed it, reporting as
    # an opaque infrastructure failure rather than as this test. If the first
    # call raises before reaching the slot, `started` is never set; if the
    # slot is never released, `first` never completes. Both become a
    # TimeoutError naming this line instead.
    await asyncio.wait_for(started.wait(), timeout=_SLOT_TEST_TIMEOUT)

    try:
        with pytest.raises(BusinessLogicError) as excinfo:
            await remoderate_api.trigger_remoderate("s1", 1, ctx)
        assert excinfo.value.details["rule"] == "remoderate_already_running"
    finally:
        release.set()
        await asyncio.wait_for(first, timeout=_SLOT_TEST_TIMEOUT)

    # The slot is released for the next caller once the first call returns.
    assert not remoderate_api._REMODERATION_SLOT.locked()


async def test_child_names_passed_to_pipeline_for_pii_guard(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The story family's child names reach the pipeline as the PII denylist.

    The names travel INWARD so the pipeline can keep them out of provider
    prompts. The family queried is the STORY's, which for a cross-family
    admin sweep is not the caller's; narrowing it to the principal's own
    family would silently disable the guard for exactly those sweeps.
    """
    _wire_session(
        mock_async_session,
        _story(),
        _version_row(),
        child_names=["Briella", "Ember"],
    )

    async def _fake_pipeline(**_kwargs: object) -> None:
        raise StateTransitionError(
            "cannot submit", rule="invalid_state_transition", context={}
        )

    pipeline = AsyncMock(side_effect=_fake_pipeline)
    monkeypatch.setattr(remoderate_api, "run_moderation_pipeline", pipeline)

    await remoderate_api.trigger_remoderate("s1", 1, _ctx(_ADMIN, mock_async_session))

    assert pipeline.call_args.kwargs["pii"].child_names == frozenset(
        {"Briella", "Ember"}
    )


async def test_remoderate_response_excludes_child_names(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Child names reach the pipeline but never the response or the audit event.

    The PII denylist is the one genuinely-sensitive value this module holds.
    An event payload or response field carrying it would exfiltrate exactly
    what the guard exists to protect, into a store with different retention
    and access rules than the profile table.
    """
    names = ["Briella", "Ember"]
    _wire_session(mock_async_session, _story(), _version_row(), child_names=list(names))

    async def _fake_pipeline(**_kwargs: object) -> None:
        raise StateTransitionError(
            "cannot submit", rule="invalid_state_transition", context={}
        )

    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_fake_pipeline)
    )

    view = await remoderate_api.trigger_remoderate(
        "s1", 1, _ctx(_ADMIN, mock_async_session)
    )

    serialized = view.model_dump_json()
    event = mock_async_session.add.call_args.args[0]
    event_payload = repr(event.payload)
    for name in names:
        assert name not in serialized
        assert name not in event_payload


# ---------------------------------------------------------------------------
# Validator refresh (the review surface's deterministic input)
# ---------------------------------------------------------------------------


async def test_remoderation_refreshes_the_stored_validation_report(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-moderation re-runs the validator gate over the stored blob.

    Before this, ``POST /admin/remoderate`` refreshed ``moderation_report``
    and left ``validation_report`` exactly as the import or generation run
    wrote it, however many rule changes ago. The admin review surface reads
    the stored report and never re-runs the gate by design
    (api/review_surface.py::_validator_findings), so a stale report is
    displayed as current forever. Re-moderation is the one admin-triggered
    entry point that re-derives a book's automated verdicts, so it is where
    the deterministic half has to be re-derived too.
    """
    stale = {"findings": [{"rule_id": "RL-13", "severity": "warning"}], "ok": True}
    version_row = _version_row()
    version_row.validation_report = stale
    _wire_session(mock_async_session, _story(), version_row)

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.moderation_report = _PASSING_REPORT
        raise StateTransitionError(
            "cannot submit", rule="invalid_state_transition", context={}
        )

    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_fake_pipeline)
    )

    await remoderate_api.trigger_remoderate("s1", 1, _ctx(_ADMIN, mock_async_session))

    assert version_row.validation_report is not stale
    assert version_row.validation_report == run_fill_gate(_blob()).report.to_dict()


# ---------------------------------------------------------------------------
# Auto-repair forks on status; the slot contract comes from the version
# ---------------------------------------------------------------------------


async def test_in_review_book_allows_repair(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A soft-FLAG in_review book reaches the repair branch.

    The inverse of test_published_blob_unchanged_when_repair_disallowed, and
    the pair is the point: this endpoint's behaviour forks on status, so each
    arm carries its own test and neither can be changed silently.
    """
    version_row = _version_row()
    _wire_session(mock_async_session, _story(status="in_review"), version_row)

    def _build(settings: Settings, **kwargs: object) -> tuple[MockProvider, bool]:
        del settings, kwargs
        return _flagging_review_provider(), True

    monkeypatch.setattr(pipeline_mod, "build_review_provider", _build)
    # A non-None slot set is the repair branch's other precondition. Supplying
    # it here keeps this test about allow_repair rather than about contract
    # resolution, which has its own test below.
    monkeypatch.setattr(
        remoderate_api, "personalizable_slot_ids_for_version", lambda _row: frozenset()
    )
    repair = AsyncMock(side_effect=lambda **kw: kw["report"])
    monkeypatch.setattr(pipeline_mod, "_attempt_and_adopt_repair", repair)

    await remoderate_api.remoderate_storybook_version(
        mock_async_session, "s1", 1, _remod_ctx(actor=Actor.from_principal(_ADMIN))
    )

    repair.assert_awaited_once()


async def test_slot_contract_resolved_from_the_version_not_a_job(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resolved slot set is passed to the pipeline explicitly.

    Without this the pipeline falls back to a generation_job lookup, and all
    seventeen production books have no job row, so it resolves the fail-closed
    None and manufactures a sentinel_integrity_violation BLOCK out of absent
    provenance: it would overwrite every accurate report and, because repair is
    gated on not having a hard block, suppress the repair enabled alongside it.
    """
    version_row = _version_row()
    version_row.skeleton_slug = "any-slug"
    _wire_session(mock_async_session, _story(status="in_review"), version_row)
    monkeypatch.setattr(
        remoderate_api,
        "personalizable_slot_ids_for_version",
        lambda _row: frozenset({"companion"}),
    )

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.moderation_report = _PASSING_REPORT

    pipeline = AsyncMock(side_effect=_fake_pipeline)
    monkeypatch.setattr(remoderate_api, "run_moderation_pipeline", pipeline)

    await remoderate_api.remoderate_storybook_version(
        mock_async_session, "s1", 1, _remod_ctx()
    )

    assert pipeline.await_args is not None
    assert pipeline.await_args.kwargs["personalizable_slots"] == frozenset(
        {"companion"}
    )
    assert pipeline.await_args.kwargs["allow_repair"] is True


async def test_published_book_still_disallows_repair(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The published invariant survives the fork.

    ADR-005: a published book is a guardian-approved artifact a child may be
    reading offline, so re-moderation reports on it and never rewrites it.
    """
    version_row = _version_row()
    _wire_session(mock_async_session, _story(status="published"), version_row)

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.moderation_report = _PASSING_REPORT

    pipeline = AsyncMock(side_effect=_fake_pipeline)
    monkeypatch.setattr(remoderate_api, "run_moderation_pipeline", pipeline)

    await remoderate_api.remoderate_storybook_version(
        mock_async_session, "s1", 1, _remod_ctx()
    )

    assert pipeline.await_args is not None
    assert pipeline.await_args.kwargs["allow_repair"] is False


async def test_repaired_blob_gets_a_matching_validation_report(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After an adopted repair, validation_report describes the REPAIRED blob.

    The pre-pipeline gate pass stays where it is, because design principle 4
    (deterministic before generative) wants those findings available to the
    generative stage. That ordering was safe only while allow_repair=False
    guaranteed the blob could not change underneath it. With repair enabled the
    blob does change, so without a second pass the stored verdict would
    describe prose that no longer exists: staleness that is invisible rather
    than merely old, introduced by the fix for the visible kind.
    """
    version_row = _version_row()
    repaired = _blob()
    nodes = repaired["nodes"]
    assert isinstance(nodes, list)
    first = nodes[0]
    assert isinstance(first, dict)
    # Long, subordinate-clause-heavy prose, deliberately. The fill gate's
    # findings are driven by reading-level metrics, so a short substitution
    # (or a title change) produces a byte-identical report and the
    # discriminating assertion below would pass with the code under test
    # deleted.
    first["body"] = (
        "Notwithstanding the extraordinarily convoluted circumstances, the "
        "protagonist deliberated interminably. " * 12
    )

    async def _fake_pipeline(**_kwargs: object) -> None:
        version_row.blob = repaired
        version_row.moderation_report = _PASSING_REPORT

    _wire_session(mock_async_session, _story(status="in_review"), version_row)
    monkeypatch.setattr(
        remoderate_api, "run_moderation_pipeline", AsyncMock(side_effect=_fake_pipeline)
    )

    await remoderate_api.remoderate_storybook_version(
        mock_async_session, "s1", 1, _remod_ctx()
    )

    assert version_row.validation_report == run_fill_gate(repaired).report.to_dict()
    # The discriminating half: without the post-pipeline pass the stored report
    # is the PRE-repair one, so these two must differ or the test proves nothing.
    assert version_row.validation_report != run_fill_gate(_blob()).report.to_dict()


async def test_remoderatable_statuses_cannot_be_moved_by_the_pipeline() -> None:
    """Every admitted status must be one the pipeline's terminal call cannot move.

    This is the invariant the whole endpoint rests on. ``remoderate`` calls
    ``run_moderation_pipeline`` unmodified, and that pipeline always ends by
    attempting ``submit`` (clean/repaired) or ``auto_reject`` (hard block).
    The endpoint is safe only because both hops are ILLEGAL for every status
    it admits, so ``assert_transition`` raises before ``storybook.status`` is
    touched and the endpoint catches it.

    Nothing in the type system enforces that. Adding a status to
    ``REMODERATABLE_STATUSES``, or adding a hop to ``LEGAL_TRANSITIONS`` for
    a status already in it, would silently convert a report-only endpoint into
    one that moves books past the human gate ADR-005 requires. This test is
    the enforcement.

    Async despite awaiting nothing: this module's ``pytestmark`` applies
    ``pytest.mark.asyncio`` to every test in the file.
    """
    for status in remoderate_api.REMODERATABLE_STATUSES:
        for action in (Action.SUBMIT, Action.AUTO_REJECT):
            assert (status, action) not in LEGAL_TRANSITIONS, (
                f"({status}, {action}) is now a legal transition, so "
                f"re-moderating a {status} book would MOVE it. Either remove "
                f"{status} from REMODERATABLE_STATUSES or stop calling "
                f"run_moderation_pipeline unmodified."
            )


async def test_remoderatable_statuses_excludes_every_movable_status() -> None:
    """The converse: no status the pipeline CAN move may be admitted.

    Guards the other direction of the same invariant, so a future widening
    that admits ``draft`` or ``needs_revision`` fails here rather than in
    production. Both of those have a legal SUBMIT hop today.
    """
    movable = {
        status
        for (status, action) in LEGAL_TRANSITIONS
        if action in {Action.SUBMIT, Action.AUTO_REJECT}
    }
    assert movable, "sanity: LEGAL_TRANSITIONS should have movable statuses"
    assert not (movable & remoderate_api.REMODERATABLE_STATUSES), (
        "a status the pipeline can move is admitted for re-moderation"
    )
    # The specific statuses this pins today, so the sanity check above cannot
    # go vacuous if LEGAL_TRANSITIONS is restructured.
    assert Status.DRAFT in movable
    assert Status.NEEDS_REVISION in movable
