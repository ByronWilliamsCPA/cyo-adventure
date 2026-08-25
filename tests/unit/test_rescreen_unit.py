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
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from cyo_adventure.api import rescreen as rescreen_api
from cyo_adventure.api.deps import Principal, RequestContext, Role
from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import (
    GenerationJob,
    PipelineEvent,
    Storybook,
    StorybookVersion,
)
from cyo_adventure.events import Actor
from cyo_adventure.generation.provider import _CANNED_STORY
from cyo_adventure.moderation import rescreen as rescreen_mod
from cyo_adventure.moderation.personalizable_slots import (
    PERSONALIZABLE_SLOTS_UNRECOVERABLE,
    PersonalizableSlots,
)
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.moderation.thresholds import Threshold, ThresholdPolicy
from cyo_adventure.storybook.sentinels import wrap
from cyo_adventure.validator.sentinel_integrity import IntegrityViolation

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


def _scalars_result(rows: list[GenerationJob]) -> MagicMock:
    """Fake a `ScalarResult` whose `.all()` returns ``rows`` (session.scalars)."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _wire_session(
    session: AsyncMock,
    *,
    books: list[Storybook],
    versions: dict[tuple[str, int], StorybookVersion],
    jobs: list[GenerationJob] | None = None,
) -> None:
    """Wire a mock session for the sweep's load, prefetch, per-book-get sequence.

    `session.scalars` serves the ONE personalizable-slot prefetch the sweep
    issues before screening anything; `session.execute` serves the published-
    book load. They are deliberately different session methods so a test can
    assert on either statement without disambiguating a shared call list.
    """
    session.execute = AsyncMock(return_value=_execute_books(books))
    session.scalars = AsyncMock(return_value=_scalars_result(jobs or []))

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


def _with_sentinel_in_body(blob: dict[str, object], sentinel: str) -> dict[str, object]:
    """Return a deep copy of ``blob`` with ``sentinel`` appended to n_start's body."""
    modified = copy.deepcopy(blob)
    nodes = cast("list[dict[str, object]]", modified["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    start_node["body"] = f"{start_node['body']} {sentinel}"
    return modified


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
# ADR-023 plan 3.3 (Task 4b sub-task 3): strip-before-classify (3a, plan R12,
# MANDATORY) and the contract-free sentinel corruption-at-rest scan (3b).
# ---------------------------------------------------------------------------


async def test_classifier_input_is_stripped_of_sentinels(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(3a) A published body carrying a sentinel is stripped to its generic
    value before it reaches the classifiers; the stored blob is untouched.
    """
    _patch_threshold_policy(monkeypatch)
    classifiers = AsyncMock(return_value=[])
    monkeypatch.setattr(rescreen_mod, "run_classifiers", classifiers)
    book = _book()
    sentinel = wrap("HERO", "Ada")
    tainted_blob = _with_sentinel_in_body(_blob(), sentinel)
    version_row = _version_row("s1", 1, tainted_blob)
    _wire_session(mock_async_session, books=[book], versions={("s1", 1): version_row})

    await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    classifiers.assert_awaited_once()
    assert classifiers.await_args is not None
    nodes = dict(classifiers.await_args.kwargs["nodes"])
    assert "{~" not in nodes["n_start"]
    assert nodes["n_start"].endswith("Ada")

    # The stored blob is never mutated: the sentinel survives at rest.
    stored_nodes = cast("list[dict[str, object]]", version_row.blob["nodes"])
    stored_start = next(n for n in stored_nodes if n["id"] == "n_start")
    assert sentinel in cast("str", stored_start["body"])


async def test_sentinel_free_body_is_unaffected_by_strip(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sentinel-free body reaches the classifier byte-identical (dormancy
    fact): stripping a sentinel-free string is a documented no-op.
    """
    _patch_threshold_policy(monkeypatch)
    classifiers = AsyncMock(return_value=[])
    monkeypatch.setattr(rescreen_mod, "run_classifiers", classifiers)
    book = _book()
    clean_blob = _blob()
    version_row = _version_row("s1", 1, clean_blob)
    _wire_session(mock_async_session, books=[book], versions={("s1", 1): version_row})

    await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert classifiers.await_args is not None
    nodes = dict(classifiers.await_args.kwargs["nodes"])
    stored_nodes = cast("list[dict[str, object]]", clean_blob["nodes"])
    for node in stored_nodes:
        assert nodes[cast("str", node["id"])] == node["body"]


async def test_malformed_sentinel_flags_rescreen(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(3b) A malformed sentinel-shaped near-miss in a published body flags
    the book, even though the deterministic gate and classifiers see nothing
    wrong (a near-miss is valid, non-empty prose to both of those).
    """
    _patch_threshold_policy(monkeypatch)
    monkeypatch.setattr(rescreen_mod, "run_classifiers", AsyncMock(return_value=[]))
    book = _book()
    near_miss = "{~HERO:Explorer}"  # missing the closing tilde
    corrupted_blob = _with_sentinel_in_body(_blob(), near_miss)
    _wire_session(
        mock_async_session,
        books=[book],
        versions={("s1", 1): _version_row("s1", 1, corrupted_blob)},
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.flagged == 1
    result = summary.results[0]
    assert any("malformed" in r for r in result.reasons)


async def test_sentinel_in_choice_label_flags_rescreen(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(3b) A well-formed sentinel that leaked into a choice label flags the
    book: a choice label must never carry personalization content (Task 2).
    """
    _patch_threshold_policy(monkeypatch)
    monkeypatch.setattr(rescreen_mod, "run_classifiers", AsyncMock(return_value=[]))
    book = _book()
    corrupted_blob = _blob()
    nodes = cast("list[dict[str, object]]", corrupted_blob["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    choices = cast("list[dict[str, object]]", start_node["choices"])
    choices[0]["label"] = f"{choices[0]['label']} {wrap('HERO', 'Ada')}"
    _wire_session(
        mock_async_session,
        books=[book],
        versions={("s1", 1): _version_row("s1", 1, corrupted_blob)},
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.flagged == 1
    result = summary.results[0]
    assert any("choice label" in r for r in result.reasons)


async def test_sentinel_in_title_flags_rescreen(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(Task 6a) A well-formed sentinel that leaked into the top-level title
    flags the book: the title is kid-facing (library listings) and never a
    personalizable location, so it must never carry sentinel content.
    """
    _patch_threshold_policy(monkeypatch)
    monkeypatch.setattr(rescreen_mod, "run_classifiers", AsyncMock(return_value=[]))
    book = _book()
    corrupted_blob = _blob()
    corrupted_blob["title"] = f"{corrupted_blob['title']} {wrap('HERO', 'Ada')}"
    _wire_session(
        mock_async_session,
        books=[book],
        versions={("s1", 1): _version_row("s1", 1, corrupted_blob)},
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.flagged == 1
    result = summary.results[0]
    assert any("title" in r for r in result.reasons)


async def test_malformed_sentinel_in_title_flagged_by_scan() -> None:
    """(Task 6a) A malformed near-miss in the top-level title is caught by
    the direct `_sentinel_corruption_reasons` scan, mirroring the body/label
    near-miss coverage above.
    """
    blob = _blob()
    blob["title"] = f"{blob['title']} {{~HERO:Explorer}}"

    reasons = rescreen_mod._sentinel_corruption_reasons(blob, frozenset())

    assert any("malformed" in r and "title" in r for r in reasons)


async def test_clean_blob_is_not_flagged_by_sentinel_scan() -> None:
    """(3b) A clean, sentinel-free published blob contributes zero reasons
    from the sentinel-corruption scan (dormancy fact): with no malformed
    near-miss and no well-formed sentinel anywhere in the blob (body, ending
    title, or a choice label), `_sentinel_corruption_reasons` finds nothing
    to report, so it never contributes a reason toward a "flagged" outcome.
    """
    reasons = rescreen_mod._sentinel_corruption_reasons(_blob(), frozenset())

    assert reasons == []


async def test_sentinel_corruption_scan_fails_closed_when_contract_unrecoverable() -> (
    None
):
    """(ADR-023 Stage R, M1) An unrecoverable personalizable-slot contract
    fails the scan closed with one explicit reason, mirroring
    `moderation/pipeline.py`'s own moderation-entry backstop, instead of
    guessing an empty declared set that could let a real corruption through
    unflagged.
    """
    reasons = rescreen_mod._sentinel_corruption_reasons(
        _blob(), PERSONALIZABLE_SLOTS_UNRECOVERABLE
    )

    assert reasons == [
        "personalizable-slot contract could not be recovered; failing closed"
    ]


async def test_slot_contracts_are_prefetched_in_one_query(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole sweep's slot contracts come from ONE GenerationJob query.

    Resolving the contract per book was an N+1: three books meant three
    `GenerationJob` SELECTs inside the per-book try/except. One prefetch,
    scoped by an IN clause over every book id, replaces them.
    """
    _patch_threshold_policy(monkeypatch)
    monkeypatch.setattr(rescreen_mod, "run_classifiers", AsyncMock(return_value=[]))
    books = [_book("s1"), _book("s2"), _book("s3")]
    _wire_session(
        mock_async_session,
        books=books,
        versions={(b.id, 1): _version_row(b.id, 1, _blob()) for b in books},
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert summary.checked == 3
    mock_async_session.scalars.assert_awaited_once()
    stmt = mock_async_session.scalars.await_args.args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "generation_job.storybook_id IN" in sql
    assert "'s1'" in sql
    assert "'s2'" in sql
    assert "'s3'" in sql


async def test_prefetch_db_failure_aborts_the_sweep(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB failure resolving the contracts aborts the sweep, loudly.

    The prefetch sits OUTSIDE `_rescreen_one`'s per-book `except Exception`
    on purpose. When the same query ran per book inside that guard, a DB
    outage became N `outcome="error"` verdicts logged at WARNING while the
    sweep still returned a completed-looking summary. Now the caller gets the
    exception and no book is screened at all.
    """
    _patch_threshold_policy(monkeypatch)
    book = _book()
    _wire_session(
        mock_async_session,
        books=[book],
        versions={("s1", 1): _version_row("s1", 1, _blob())},
    )
    mock_async_session.scalars = AsyncMock(side_effect=RuntimeError("db down"))
    settings = _settings()
    actor = _actor()

    with pytest.raises(RuntimeError, match="db down"):
        await rescreen_mod.rescreen_published_books(
            mock_async_session, settings=settings, actor=actor
        )

    mock_async_session.get.assert_not_awaited()
    mock_async_session.add.assert_not_called()


async def test_prefetched_job_drives_the_per_book_slot_contract(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prefetched job row, not a second lookup, resolves each book's contract.

    The resolver is handed the job the prefetch found and its tri-state answer
    threads through to the per-book scan: an unrecoverable contract
    still fails that book closed, exactly as the per-book resolution did.
    """
    _patch_threshold_policy(monkeypatch)
    monkeypatch.setattr(rescreen_mod, "run_classifiers", AsyncMock(return_value=[]))
    job = GenerationJob(storybook_id="s1", authoring_metadata={"skeleton_slug": "x"})
    seen: list[GenerationJob] = []

    def _unrecoverable(passed_job: GenerationJob) -> PersonalizableSlots:
        seen.append(passed_job)
        return PERSONALIZABLE_SLOTS_UNRECOVERABLE

    monkeypatch.setattr(rescreen_mod, "personalizable_slot_ids_for_job", _unrecoverable)
    book = _book()
    _wire_session(
        mock_async_session,
        books=[book],
        versions={("s1", 1): _version_row("s1", 1, _blob())},
        jobs=[job],
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    assert seen == [job]
    assert summary.flagged == 1
    assert summary.results[0].reasons == [
        "personalizable-slot contract could not be recovered; failing closed"
    ]


async def test_at_rest_scan_runs_even_when_the_blob_fails_to_parse(
    mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blob the gate blocks AND that fails schema validation is still scanned.

    The at-rest sentinel scan reads the raw blob mapping, never the parsed
    model, so it must not be gated on `model_validate` succeeding. Nested
    under the parse-success branch it was skipped for precisely the blobs
    most likely to be damaged: the verdict carried the gate's reasons and
    said nothing about the sentinel state of the stored content.
    """
    _patch_threshold_policy(monkeypatch)
    classifiers = AsyncMock(return_value=[])
    monkeypatch.setattr(rescreen_mod, "run_classifiers", classifiers)
    job = GenerationJob(storybook_id="s1", authoring_metadata={"skeleton_slug": "x"})
    monkeypatch.setattr(
        rescreen_mod,
        "personalizable_slot_ids_for_job",
        lambda _job: PERSONALIZABLE_SLOTS_UNRECOVERABLE,
    )
    _wire_session(
        mock_async_session,
        books=[_book()],
        # `{}` fails StoryModel.model_validate and the gate blocks it first.
        versions={("s1", 1): _version_row("s1", 1, {})},
        jobs=[job],
    )

    summary = await rescreen_mod.rescreen_published_books(
        mock_async_session, settings=_settings(), actor=_actor()
    )

    result = summary.results[0]
    assert result.outcome == "flagged"
    assert any(r.startswith("gate ") for r in result.reasons)
    assert (
        "personalizable-slot contract could not be recovered; failing closed"
        in result.reasons
    )
    classifiers.assert_not_awaited()


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


async def test_violation_reason_malformed_in_node_body_names_the_body_location() -> (
    None
):
    """A malformed violation outside title/choice-label reads as body/ending title.

    `_violation_reason` fans out over two location placeholders (`<title>`,
    `<choice-label>`) before falling through to a real node id, and each of the
    three branches splits again on `kind == "malformed"`. The
    body-plus-malformed corner was the one combination no existing test
    reached, so the vocabulary it emits ("sentinel malformed in body/ending
    title") was unasserted: a rename there would have shipped silently even
    though `RescreenResult.reasons` is operator-facing text.
    """
    body = rescreen_mod._violation_reason(
        IntegrityViolation(node_id="n_3", kind="malformed", token="{~HERO:Ada~")
    )

    assert body == "sentinel malformed in body/ending title: '{~HERO:Ada~'"
    # Pinned against its two siblings, because the point of the branch is that
    # the three locations stay distinguishable in the operator-facing string.
    assert (
        rescreen_mod._violation_reason(
            IntegrityViolation(node_id="<title>", kind="malformed", token="{~HERO:Ada~")
        )
        == "sentinel malformed in title: '{~HERO:Ada~'"
    )
    assert (
        rescreen_mod._violation_reason(
            IntegrityViolation(
                node_id="<choice-label>", kind="malformed", token="{~HERO:Ada~"
            )
        )
        == "sentinel malformed in choice label: '{~HERO:Ada~'"
    )


async def test_prefetch_personalizable_slots_never_queries_for_an_empty_sweep() -> None:
    """No books means no query at all, not a query with an empty `IN ()`.

    The guard exists because `GenerationJob.storybook_id.in_([])` is a
    degenerate predicate, and because the sweep calls this helper
    unconditionally. Asserting the empty mapping alone would pass even if the
    guard were deleted, so this asserts the stronger property the guard is
    actually for: the session is never touched.

    The session is wired with a WORKING `scalars` double rather than a bare
    `AsyncMock` on purpose. With a bare mock, deleting the guard makes the
    helper die on `TypeError: 'coroutine' object is not iterable` before it
    ever reaches the assertion below, so the test would fail for a reason that
    says nothing about the guard. Wired this way, the no-guard version runs to
    completion and fails on `assert_not_awaited`, which names the actual defect.
    """
    session = AsyncMock()
    session.scalars = AsyncMock(return_value=_scalars_result([]))

    result = await rescreen_mod._prefetch_personalizable_slots(session, [])

    assert result == {}
    session.scalars.assert_not_awaited()
    session.execute.assert_not_awaited()
