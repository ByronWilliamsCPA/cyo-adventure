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
from cyo_adventure.generation.provider import _CANNED_STORY, MockProvider
from cyo_adventure.moderation import pipeline as pipeline_mod

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


def _ctx(principal: Principal, session: AsyncMock) -> RequestContext:
    return RequestContext(principal=principal, session=session)


def _blob() -> dict[str, object]:
    return copy.deepcopy(_CANNED_STORY)


def _story(status: str = "published") -> Storybook:
    return Storybook(id="s1", family_id=_FAMILY, status=status)


def _version_row(
    moderation_report: dict[str, object] | None = None,
) -> StorybookVersion:
    return StorybookVersion(
        storybook_id="s1",
        version=1,
        blob=_blob(),
        model="gen-model",
        provider="mock",
        moderation_report=moderation_report,
    )


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

    with pytest.raises(ResourceNotFoundError):
        await remoderate_api.remoderate_storybook_version(
            mock_async_session, "missing", 1, _remod_ctx()
        )


async def test_unknown_version_raises_404(mock_async_session: AsyncMock) -> None:
    _wire_session(mock_async_session, _story(), None)

    with pytest.raises(ResourceNotFoundError):
        await remoderate_api.remoderate_storybook_version(
            mock_async_session, "s1", 99, _remod_ctx()
        )


@pytest.mark.parametrize("status", ["draft", "in_review", "needs_revision", "archived"])
async def test_non_published_status_rejected(
    status: str, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every status but 'published' is rejected before the pipeline runs."""
    _wire_session(mock_async_session, _story(status=status), _version_row())
    pipeline = AsyncMock()
    monkeypatch.setattr(remoderate_api, "run_moderation_pipeline", pipeline)

    with pytest.raises(BusinessLogicError, match="not 'published'"):
        await remoderate_api.remoderate_storybook_version(
            mock_async_session, "s1", 1, _remod_ctx()
        )
    pipeline.assert_not_awaited()


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
    assert version_row.moderation_report["summary"]["reviewer_independent"] is False


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
    assert version_row.moderation_report is not None
    assert version_row.moderation_report["summary"]["hard_block"] is False
    # The fresh (real, merged) report replaced the stale mock-moderated one:
    # the mock_reviewer_active advisory from the PRIOR report is gone, and
    # reviewer_independent is now True (the clean review_seam double, not
    # the mock backend).
    assert version_row.moderation_report["summary"]["reviewer_independent"] is True
    assert result.prior_reviewer_independent is False
    mock_async_session.add.assert_called_once()
