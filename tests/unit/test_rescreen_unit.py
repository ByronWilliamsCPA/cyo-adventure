"""Unit tests for the policy re-screen tooling (register A4 first cut).

Mocking policy (mirrors tests/unit/test_moderation_pipeline.py and
tests/unit/test_node_edit.py, org testing standard SS4.2/4.3): the real
``validator.gate.run_gate`` and ``moderation.thresholds.ThresholdPolicy``
logic run for real. Only true system boundaries are doubled:

- ``moderation.rescreen.run_classifiers`` (the classifier HTTP boundary),
  patched directly with an ``AsyncMock``/callable double per test, the same
  "mock at the boundary" seam ``test_moderation_pipeline.py`` documents for
  the review-provider boundary. A bare ``Settings()`` carries no OpenAI/
  Perspective key, so tests that don't need a classifier finding leave the
  real (key-less, no-op) ``run_classifiers`` in place -- no HTTP mocking is
  needed for those, mirroring ``test_node_edit.py``'s documented approach.
- ``moderation.rescreen.load_threshold_policy`` (a DB read), patched to
  return a hand-built ``ThresholdPolicy`` so tests don't need to wire
  ``session.scalars`` for the sparse override table.
- The DB session (spec'd ``AsyncMock``; no live database in unit tests).
"""

from __future__ import annotations

import copy
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from cyo_adventure.api import rescreen as rescreen_api
from cyo_adventure.api.deps import Principal, RequestContext, Role
from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import PipelineEvent, Storybook, StorybookVersion
from cyo_adventure.events import Actor
from cyo_adventure.generation.provider import _CANNED_STORY
from cyo_adventure.moderation import rescreen as rescreen_mod
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.moderation.thresholds import Threshold, ThresholdPolicy

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


def _settings() -> Settings:
    """A bare Settings with no classifier keys (the real no-op degrade path)."""
    return Settings()


def _blob() -> dict[str, object]:
    """A fresh copy of the canned, gate-passing story blob."""
    return copy.deepcopy(_CANNED_STORY)


def _book(story_id: str = "s1", *, current_version: int | None = 1) -> Storybook:
    return Storybook(
        id=story_id,
        family_id=_FAMILY,
        status="published",
        current_published_version=current_version,
    )


def _version_row(
    story_id: str, version: int, blob: dict[str, object] | None = None
) -> StorybookVersion:
    return StorybookVersion(
        storybook_id=story_id,
        version=version,
        blob=blob if blob is not None else _blob(),
    )


def _execute_books(books: list[Storybook]) -> MagicMock:
    """Fake a `Result` whose `.scalars().all()` returns ``books`` (session.execute)."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = books
    return result


def _default_threshold_policy() -> ThresholdPolicy:
    return ThresholdPolicy(rows={})


def _patch_threshold_policy(
    monkeypatch: pytest.MonkeyPatch, policy: ThresholdPolicy | None = None
) -> None:
    monkeypatch.setattr(
        rescreen_mod,
        "load_threshold_policy",
        AsyncMock(return_value=policy or _default_threshold_policy()),
    )


def _wire_session(
    session: AsyncMock,
    *,
    books: list[Storybook],
    versions: dict[tuple[str, int], StorybookVersion],
) -> None:
    """Wire a mock session for the sweep's load-then-per-book-get sequence."""
    session.execute = AsyncMock(return_value=_execute_books(books))

    async def _get(
        _model: type[object], key: tuple[str, int]
    ) -> StorybookVersion | None:
        return versions.get(key)

    session.get = AsyncMock(side_effect=_get)
    session.add = MagicMock()
    session.flush = AsyncMock()


def _actor() -> Actor:
    return Actor.from_principal(_ADMIN, acting_role="admin")


def _advisory_finding(category: str = "toxicity") -> Finding:
    return Finding(
        stage=0,
        source=Source.OPENAI,
        category=category,
        node_id="n_start",
        verdict=Verdict.ADVISORY,
        score=0.5,
        message="advisory signal",
    )


def _block_finding(category: str = "sexual") -> Finding:
    return Finding(
        stage=0,
        source=Source.OPENAI,
        category=category,
        node_id="n_start",
        verdict=Verdict.BLOCK,
        score=0.99,
        message="bright-line hit",
    )


# ---------------------------------------------------------------------------
# rescreen_published_books / _rescreen_one
# ---------------------------------------------------------------------------


async def test_passing_book_yields_passed_and_writes_pipeline_event(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clean, gate-passing book with no classifier keys yields "passed"."""
    _patch_threshold_policy(monkeypatch)
    book = _book()
    _wire_session(
        mock_async_session, books=[book], versions={("s1", 1): _version_row("s1", 1)}
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.checked == 1
    assert summary.passed == 1
    assert summary.flagged == 0
    assert summary.errored == 0
    result = summary.results[0]
    assert result.outcome == "passed"
    assert result.reasons == []

    mock_async_session.add.assert_called_once()
    event = mock_async_session.add.call_args.args[0]
    assert isinstance(event, PipelineEvent)
    assert event.event_type == "moderation_completed"
    assert event.entity_type == "storybook_version"
    assert event.entity_id == "s1:1"
    assert event.actor_role == "admin"
    assert event.to_state == "published"
    assert event.payload["overall_verdict"] == "pass"
    assert event.payload["repaired"] is False
    mock_async_session.flush.assert_awaited()


async def test_book_violating_current_thresholds_yields_flagged_with_reasons(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An advisory classifier finding that newly surfaces under the current
    threshold policy flags an otherwise-clean book (the "moderation-threshold
    change" case A4 exists for).
    """
    # 8-11 is _CANNED_STORY's band; lower the floor to advisory for this
    # (band, category) so an ADVISORY finding now surfaces.
    policy = ThresholdPolicy(
        rows={
            ("8-11", "toxicity"): Threshold(
                min_verdict=Verdict.ADVISORY, min_score=None
            )
        }
    )
    _patch_threshold_policy(monkeypatch, policy)
    monkeypatch.setattr(
        rescreen_mod, "run_classifiers", AsyncMock(return_value=[_advisory_finding()])
    )
    book = _book()
    _wire_session(
        mock_async_session, books=[book], versions={("s1", 1): _version_row("s1", 1)}
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.flagged == 1
    result = summary.results[0]
    assert result.outcome == "flagged"
    assert result.reasons
    assert "now surfaces under the current moderation threshold" in result.reasons[0]

    event = mock_async_session.add.call_args.args[0]
    assert event.payload["overall_verdict"] == "flag"


async def test_classifier_bright_line_yields_flagged_with_block_verdict(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh Stage-0 bright-line finding flags the book regardless of thresholds."""
    _patch_threshold_policy(monkeypatch)
    monkeypatch.setattr(
        rescreen_mod, "run_classifiers", AsyncMock(return_value=[_block_finding()])
    )
    book = _book()
    _wire_session(
        mock_async_session, books=[book], versions={("s1", 1): _version_row("s1", 1)}
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.flagged == 1
    event = mock_async_session.add.call_args.args[0]
    assert event.payload["overall_verdict"] == "block"


async def test_corrupted_blob_flags_via_gate_without_running_classifiers(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blob that fails schema conformance is caught by the gate (band-policy
    style failure), not silently dropped to "error": run_gate's own L1-1
    check already flags it, so the story parse failure that follows carries
    no separate reason and classifiers are skipped entirely.
    """
    _patch_threshold_policy(monkeypatch)
    classifiers = AsyncMock(return_value=[])
    monkeypatch.setattr(rescreen_mod, "run_classifiers", classifiers)
    book = _book()
    _wire_session(
        mock_async_session,
        books=[book],
        versions={("s1", 1): _version_row("s1", 1, {})},
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.flagged == 1
    assert summary.errored == 0
    result = summary.results[0]
    assert result.outcome == "flagged"
    assert any(r.startswith("gate ") for r in result.reasons)
    classifiers.assert_not_awaited()


async def test_provider_error_on_one_book_does_not_abort_sweep(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A classifier failure on one book yields "error" for it only; the sweep
    still screens every other book and still writes their events.
    """
    _patch_threshold_policy(monkeypatch)
    calls = {"n": 0}

    async def _flaky_classifiers(
        *, nodes: object, openai_key: object, perspective_key: object, client: object
    ) -> list[Finding]:
        calls["n"] += 1
        if calls["n"] == 1:
            msg = "classifier provider outage"
            raise RuntimeError(msg)
        return []

    monkeypatch.setattr(rescreen_mod, "run_classifiers", _flaky_classifiers)
    bad = _book("s_bad")
    good = _book("s_good")
    _wire_session(
        mock_async_session,
        books=[bad, good],
        versions={
            ("s_bad", 1): _version_row("s_bad", 1),
            ("s_good", 1): _version_row("s_good", 1),
        },
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.checked == 2
    assert summary.errored == 1
    assert summary.passed == 1
    by_id = {r.storybook_id: r for r in summary.results}
    assert by_id["s_bad"].outcome == "error"
    assert by_id["s_bad"].error is not None
    assert "classifier provider outage" in by_id["s_bad"].error
    assert by_id["s_good"].outcome == "passed"

    # Only the successfully-screened book gets a pipeline event; the errored
    # book raised before record_event was ever reached.
    mock_async_session.add.assert_called_once()
    event = mock_async_session.add.call_args.args[0]
    assert event.entity_id == "s_good:1"


async def test_scoping_by_id_list_narrows_the_where_clause(
    mock_async_session: AsyncMock,
) -> None:
    """Passing storybook_ids adds an IN clause; omitting it does not."""
    mock_async_session.execute = AsyncMock(return_value=_execute_books([]))
    await rescreen_mod._load_published_books(mock_async_session, ["s1", "s2"])
    scoped_stmt = mock_async_session.execute.await_args.args[0]
    scoped_sql = str(scoped_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "storybook.id IN" in scoped_sql
    assert "'s1'" in scoped_sql
    assert "'s2'" in scoped_sql

    mock_async_session.execute = AsyncMock(return_value=_execute_books([]))
    await rescreen_mod._load_published_books(mock_async_session, None)
    unscoped_stmt = mock_async_session.execute.await_args.args[0]
    unscoped_sql = str(unscoped_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "storybook.id IN" not in unscoped_sql
    assert "storybook.status" in unscoped_sql


async def test_no_with_for_update_lock_on_the_sweep_load(
    mock_async_session: AsyncMock,
) -> None:
    """The sweep's load is unlocked: it never writes storybook.status (see the
    module docstring's no-auto-unpublish decision), so no row lock is taken.
    """
    mock_async_session.execute = AsyncMock(return_value=_execute_books([]))
    await rescreen_mod._load_published_books(mock_async_session, None)
    stmt = mock_async_session.execute.await_args.args[0]
    assert "FOR UPDATE" not in str(stmt.compile()).upper()


async def test_flagged_book_is_not_archived_or_mutated(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flagged verdict never changes Storybook.status or the stored blob."""
    _patch_threshold_policy(monkeypatch)
    book = _book()
    version_row = _version_row("s1", 1, {})
    _wire_session(mock_async_session, books=[book], versions={("s1", 1): version_row})

    await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert book.status == "published"
    assert version_row.blob == {}
    assert version_row.moderation_report is None


async def test_missing_current_published_version_yields_error(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A published row with no current_published_version degrades to "error"."""
    _patch_threshold_policy(monkeypatch)
    book = _book(current_version=None)
    _wire_session(mock_async_session, books=[book], versions={})

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.errored == 1
    assert summary.results[0].outcome == "error"
    mock_async_session.add.assert_not_called()


async def test_missing_version_row_yields_error(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dangling current_published_version with no matching row is an "error"."""
    _patch_threshold_policy(monkeypatch)
    book = _book()
    _wire_session(mock_async_session, books=[book], versions={})

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.errored == 1
    assert summary.results[0].error == "published version row is missing"


# ---------------------------------------------------------------------------
# api.rescreen router
# ---------------------------------------------------------------------------


def _ctx(principal: Principal, session: AsyncMock) -> RequestContext:
    return RequestContext(principal=principal, session=session)


async def test_non_admin_rejected_with_403_before_any_query(
    mock_async_session: AsyncMock,
) -> None:
    """A guardian (non-admin) caller is rejected before the session is touched."""
    ctx = _ctx(_GUARDIAN, mock_async_session)
    request = rescreen_api.RescreenRequest(storybook_ids=None)

    with pytest.raises(AuthorizationError, match="admin role required"):
        await rescreen_api.trigger_rescreen(request, ctx)

    mock_async_session.execute.assert_not_awaited()


async def test_admin_triggers_rescreen_and_gets_summary(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An admin caller gets the full summary view and the event is stamped admin."""
    _patch_threshold_policy(monkeypatch)
    monkeypatch.setattr(rescreen_api, "settings", _settings())
    book = _book()
    _wire_session(
        mock_async_session, books=[book], versions={("s1", 1): _version_row("s1", 1)}
    )
    ctx = _ctx(_ADMIN, mock_async_session)

    view = await rescreen_api.trigger_rescreen(
        rescreen_api.RescreenRequest(storybook_ids=None), ctx
    )

    assert view.checked == 1
    assert view.passed == 1
    assert view.results[0].storybook_id == "s1"
    event = mock_async_session.add.call_args.args[0]
    assert event.actor_role == "admin"
    assert event.actor_id == _ADMIN.user_id
