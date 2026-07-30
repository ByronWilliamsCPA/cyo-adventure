"""Unit tests for scripts/seed_moderation_qa.py (no network, no real DB).

scripts/ is not an importable package (no __init__.py, by design; see the
INP per-file-ignore for scripts/**/*.py in pyproject.toml), so the module is
loaded directly from its file path via importlib, mirroring
tests/unit/test_seed_staging.py.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.db.models import ChildProfile
from cyo_adventure.publishing import service as publishing_service

_SPEC = importlib.util.spec_from_file_location(
    "seed_moderation_qa",
    Path(__file__).resolve().parents[2] / "scripts" / "seed_moderation_qa.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
seed_moderation_qa = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seed_moderation_qa)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Hard guard: refuse to run unless ENVIRONMENT=staging
# ---------------------------------------------------------------------------


def test_require_staging_or_exit_refuses_non_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(SystemExit) as exc:
        seed_moderation_qa._require_staging_or_exit()
    message = str(exc.value)
    assert "staging" in message
    assert "production" in message


def test_require_staging_or_exit_refuses_missing_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(SystemExit):
        seed_moderation_qa._require_staging_or_exit()


def test_require_staging_or_exit_passes_on_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    assert seed_moderation_qa._require_staging_or_exit() == "staging"


@pytest.mark.asyncio
async def test_seed_exits_before_any_engine_or_session_access_when_not_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard must block BEFORE any engine/session/network access.

    A refactor that moved the ENVIRONMENT check after engine setup would still
    raise SystemExit but would already have opened a real connection against a
    non-staging target. Patch get_engine and assert it is never even called.
    """
    monkeypatch.setenv("ENVIRONMENT", "local")
    fake_get_engine = MagicMock()
    with (
        patch.object(seed_moderation_qa, "get_engine", fake_get_engine),
        pytest.raises(SystemExit) as exc,
    ):
        await seed_moderation_qa.seed()
    assert "staging" in str(exc.value)
    fake_get_engine.assert_not_called()


# ---------------------------------------------------------------------------
# load_manifest / _load_blob
# ---------------------------------------------------------------------------


def test_load_manifest_returns_the_real_corpus_books() -> None:
    books = seed_moderation_qa.load_manifest()
    assert books, "moderation-qa-corpus.json manifest lost all its books"
    ids = {book["id"] for book in books}
    assert all(book_id.startswith("mqa_") for book_id in ids)


def test_load_blob_parses_the_referenced_fixture_file() -> None:
    books = seed_moderation_qa.load_manifest()
    entry = next(book for book in books if book["id"] == "mqa_clean_meadow_market")
    blob = seed_moderation_qa._load_blob(entry)
    assert blob["id"] == "mqa_clean_meadow_market"
    assert blob["nodes"]


def test_load_manifest_raises_configuration_error_naming_a_missing_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "nope" / "moderation-qa-corpus.json"
    monkeypatch.setattr(seed_moderation_qa, "_MANIFEST_PATH", missing)
    with pytest.raises(ConfigurationError) as exc:
        seed_moderation_qa.load_manifest()
    assert str(missing) in str(exc.value)


def test_load_manifest_raises_configuration_error_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "moderation-qa-corpus.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(seed_moderation_qa, "_MANIFEST_PATH", broken)
    with pytest.raises(ConfigurationError) as exc:
        seed_moderation_qa.load_manifest()
    assert str(broken) in str(exc.value)
    assert "valid JSON" in str(exc.value)


def test_load_manifest_raises_configuration_error_when_books_key_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    no_books = tmp_path / "moderation-qa-corpus.json"
    no_books.write_text('{"version": "1.0"}', encoding="utf-8")
    monkeypatch.setattr(seed_moderation_qa, "_MANIFEST_PATH", no_books)
    with pytest.raises(ConfigurationError) as exc:
        seed_moderation_qa.load_manifest()
    assert "books" in str(exc.value)


def test_load_blob_raises_configuration_error_when_entry_has_no_file_key() -> None:
    with pytest.raises(ConfigurationError) as exc:
        seed_moderation_qa._load_blob({"id": "mqa_x"})
    assert "mqa_x" in str(exc.value)
    assert "file" in str(exc.value)


def test_load_blob_raises_configuration_error_naming_a_missing_fixture() -> None:
    with pytest.raises(ConfigurationError) as exc:
        seed_moderation_qa._load_blob(
            {"id": "mqa_x", "file": "tests/fixtures/moderation_qa/books/gone.json"}
        )
    assert "gone.json" in str(exc.value)


# ---------------------------------------------------------------------------
# _ensure_qa_family
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_qa_family_returns_existing_without_adding() -> None:
    existing = seed_moderation_qa.Family(
        id=seed_moderation_qa._QA_FAMILY_ID, name="Moderation QA"
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=existing)
    session.add = MagicMock()

    result = await seed_moderation_qa._ensure_qa_family(session)

    assert result is existing
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_qa_family_inserts_when_absent() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()

    result = await seed_moderation_qa._ensure_qa_family(session)

    session.add.assert_called_once()
    (added,) = session.add.call_args.args
    assert added.id == seed_moderation_qa._QA_FAMILY_ID
    assert added.name == "Moderation QA"
    assert result is added


@pytest.mark.asyncio
async def test_ensure_qa_family_never_creates_a_child_profile() -> None:
    """Containment layer 2: the QA family must never gain a ChildProfile.

    The read gate is (approved AND assigned); a StorybookAssignment needs a
    profile to target. If this function ever inserted one, a QA fixture could
    in principle become assignable. Assert the only row it adds is the Family.
    """
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()

    await seed_moderation_qa._ensure_qa_family(session)

    added = [call.args[0] for call in session.add.call_args_list]
    assert not any(isinstance(row, ChildProfile) for row in added)
    assert [type(row).__name__ for row in added] == ["Family"]


# ---------------------------------------------------------------------------
# _seed_fixture_rows
# ---------------------------------------------------------------------------


def _fake_family() -> Any:
    return seed_moderation_qa.Family(id=uuid.uuid4(), name="Moderation QA")


@pytest.mark.asyncio
async def test_seed_fixture_rows_skips_already_present_books() -> None:
    books = seed_moderation_qa.load_manifest()
    session = AsyncMock()
    # Every book already exists: session.get always returns a truthy sentinel.
    session.get = AsyncMock(return_value=object())
    session.add = MagicMock()

    inserted = await seed_moderation_qa._seed_fixture_rows(
        session, _fake_family(), books
    )

    assert inserted == []
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_seed_fixture_rows_inserts_as_draft_with_no_published_version() -> None:
    books = seed_moderation_qa.load_manifest()
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()
    family = _fake_family()

    inserted = await seed_moderation_qa._seed_fixture_rows(session, family, books)

    assert set(inserted) == {book["id"] for book in books}
    added = [call.args[0] for call in session.add.call_args_list]
    storybooks = [row for row in added if type(row).__name__ == "Storybook"]
    versions = [row for row in added if type(row).__name__ == "StorybookVersion"]
    assert len(storybooks) == len(books)
    assert len(versions) == len(books)
    assert all(sb.status == "draft" for sb in storybooks)
    assert all(sb.current_published_version is None for sb in storybooks)
    assert all(sb.family_id == family.id for sb in storybooks)
    assert all(v.version == 1 for v in versions)
    assert all(v.moderation_report is None for v in versions)
    assert all(sb.id.startswith("mqa_") for sb in storybooks)


@pytest.mark.asyncio
async def test_seed_fixture_rows_only_inserts_the_missing_book() -> None:
    books = seed_moderation_qa.load_manifest()
    target_id = books[0]["id"]
    session = AsyncMock()

    async def _get(model: Any, key: object) -> object | None:
        if model.__name__ == "Storybook" and key == target_id:
            return None
        return object()

    session.get = AsyncMock(side_effect=_get)
    session.add = MagicMock()
    session.flush = AsyncMock()

    inserted = await seed_moderation_qa._seed_fixture_rows(
        session, _fake_family(), books
    )

    assert inserted == [target_id]


# ---------------------------------------------------------------------------
# _books_awaiting_moderation: the retry path
# ---------------------------------------------------------------------------


def _session_returning_pending(pending: list[str]) -> AsyncMock:
    """Build a session whose SELECT returns ``pending`` storybook ids."""
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=pending)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_books_awaiting_moderation_returns_empty_for_no_ids() -> None:
    session = AsyncMock()
    assert await seed_moderation_qa._books_awaiting_moderation(session, []) == []
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_books_awaiting_moderation_selects_only_unreported() -> None:
    """Only ids the query returned (report IS NULL) come back, in input order."""
    session = _session_returning_pending(["mqa_c", "mqa_a"])

    pending = await seed_moderation_qa._books_awaiting_moderation(
        session, ["mqa_a", "mqa_b", "mqa_c"]
    )

    assert pending == ["mqa_a", "mqa_c"]
    session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# _moderate_new_books: never approve/publish, only run_moderation_pipeline
# ---------------------------------------------------------------------------


class _FakeSavepoint:
    """Stand-in for ``AsyncSession.begin_nested()``'s AsyncSessionTransaction.

    Records "commit" or "rollback" so a test can assert a failed book's
    partial pipeline side effects were discarded rather than committed.
    """

    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def __aenter__(self) -> _FakeSavepoint:
        self._log.append("enter")
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self._log.append("rollback" if exc_type is not None else "commit")
        return False


def _savepoint_session() -> tuple[AsyncMock, list[str]]:
    """Build a session whose ``begin_nested()`` yields a recording savepoint."""
    log: list[str] = []
    session = AsyncMock()
    session.begin_nested = MagicMock(side_effect=lambda: _FakeSavepoint(log))
    return session, log


@pytest.mark.asyncio
async def test_moderate_new_books_calls_run_moderation_pipeline_per_book() -> None:
    session, _log = _savepoint_session()
    pipeline = AsyncMock()
    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        failures = await seed_moderation_qa._moderate_new_books(
            session, ["mqa_a", "mqa_b"]
        )

    assert pipeline.await_count == 2
    called_story_ids = {call.kwargs["story_id"] for call in pipeline.await_args_list}
    assert called_story_ids == {"mqa_a", "mqa_b"}
    assert failures == []


@pytest.mark.asyncio
async def test_moderate_new_books_never_calls_approve_or_publish() -> None:
    """The moderation step must drive only run_moderation_pipeline.

    ``publishing.service.approve`` is the only publish path (it is what sets
    ``status="published"`` and ``current_published_version``). This test
    actually RUNS _moderate_new_books with approve patched at its definition
    site, so a future edit that reaches it via ``service.approve(...)`` is
    caught, and separately asserts no module global of the seed script IS the
    real approve coroutine, which catches a ``from ... import approve``
    binding under any alias.
    """
    real_approve = publishing_service.approve
    assert real_approve not in vars(seed_moderation_qa).values()

    session, _log = _savepoint_session()
    approve = AsyncMock()
    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", AsyncMock()),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
        patch.object(publishing_service, "approve", approve),
    ):
        await seed_moderation_qa._moderate_new_books(session, ["mqa_a"])

    approve.assert_not_awaited()
    approve.assert_not_called()


@pytest.mark.asyncio
async def test_moderate_new_books_continues_after_one_failure() -> None:
    session, _log = _savepoint_session()
    pipeline = AsyncMock(side_effect=[RuntimeError("boom"), None])
    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        await seed_moderation_qa._moderate_new_books(session, ["mqa_a", "mqa_b"])

    assert pipeline.await_count == 2


@pytest.mark.asyncio
async def test_moderate_new_books_returns_the_failed_ids() -> None:
    session, _log = _savepoint_session()
    pipeline = AsyncMock(side_effect=[RuntimeError("boom"), None])
    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        failures = await seed_moderation_qa._moderate_new_books(
            session, ["mqa_a", "mqa_b"]
        )

    assert failures == ["mqa_a"]


@pytest.mark.asyncio
async def test_moderate_new_books_rolls_back_the_failed_book() -> None:
    """A raising pipeline must roll its savepoint back, not ride the commit.

    run_moderation_pipeline mutates session state (an adopted repair
    overwrites version_row.blob, and record_event inserts a row) BEFORE it
    persists moderation_report, and seed() commits unconditionally. Without a
    per-book savepoint those partial mutations would be committed with a NULL
    moderation_report, silently drifting the seeded blob away from the repo
    fixture that defines the ground truth.
    """
    session, log = _savepoint_session()
    pipeline = AsyncMock(side_effect=[RuntimeError("boom"), None])
    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        await seed_moderation_qa._moderate_new_books(session, ["mqa_a", "mqa_b"])

    assert log == ["enter", "rollback", "enter", "commit"]


# ---------------------------------------------------------------------------
# seed(): end-to-end wiring with a fully mocked engine/session
# ---------------------------------------------------------------------------


def _mock_engine() -> MagicMock:
    conn = AsyncMock()
    conn.run_sync = AsyncMock(return_value=None)
    engine_ctx = MagicMock()
    engine_ctx.__aenter__ = AsyncMock(return_value=conn)
    engine_ctx.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.begin = MagicMock(return_value=engine_ctx)
    return engine


def _mock_session_factory(
    *, pending: list[str] | None = None, present: bool = False
) -> tuple[MagicMock, MagicMock, list[str]]:
    """Build a mocked session factory for :func:`seed`.

    Args:
        pending: Storybook ids the "awaiting moderation" SELECT should return.
            Defaults to every manifest id (the fresh-seed case).
        present: When True, ``session.get(Storybook, ...)`` reports every book
            as already present, so nothing is inserted (the retry case).

    Returns:
        The session factory, the underlying session, and the savepoint log.
    """
    if pending is None:
        pending = [str(book["id"]) for book in seed_moderation_qa.load_manifest()]
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _get(model: Any, key: object) -> object | None:
        if model.__name__ == "Family":
            return None
        return object() if present else None

    session.get = AsyncMock(side_effect=_get)

    scalars = MagicMock()
    scalars.all = MagicMock(return_value=pending)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    session.execute = AsyncMock(return_value=result)

    log: list[str] = []
    session.begin_nested = MagicMock(side_effect=lambda: _FakeSavepoint(log))

    def _populate_ids() -> None:
        for index, add_call in enumerate(session.add.call_args_list):
            row = add_call.args[0]
            if getattr(row, "id", None) is None:
                row.id = f"pk-{index}"

    session.flush = AsyncMock(side_effect=_populate_ids)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session_ctx)
    return session_factory, session, log


@pytest.mark.asyncio
async def test_seed_skips_moderation_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    session_factory, session, _log = _mock_session_factory()
    engine = _mock_engine()
    pipeline = AsyncMock()

    with patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline):
        failures = await seed_moderation_qa.seed(
            engine=engine, session_factory=session_factory, moderate=False
        )

    pipeline.assert_not_awaited()
    session.execute.assert_not_awaited()
    session.commit.assert_awaited_once()
    assert failures == []


@pytest.mark.asyncio
async def test_seed_runs_moderation_on_every_unmoderated_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    session_factory, session, _log = _mock_session_factory()
    engine = _mock_engine()
    pipeline = AsyncMock()

    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        await seed_moderation_qa.seed(engine=engine, session_factory=session_factory)

    books = seed_moderation_qa.load_manifest()
    assert pipeline.await_count == len(books)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_retries_a_previously_unmoderated_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented retry path must be real, not a one-way door.

    Every book already exists (so _seed_fixture_rows inserts nothing), but one
    still has a NULL moderation_report because a prior run used
    --skip-moderation or raised. That book must still be moderated.
    """
    monkeypatch.setenv("ENVIRONMENT", "staging")
    session_factory, session, _log = _mock_session_factory(
        pending=["mqa_block_selfharm_reference"], present=True
    )
    engine = _mock_engine()
    pipeline = AsyncMock()

    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        await seed_moderation_qa.seed(engine=engine, session_factory=session_factory)

    added = [type(call.args[0]).__name__ for call in session.add.call_args_list]
    assert "Storybook" not in added
    assert "StorybookVersion" not in added
    assert pipeline.await_count == 1
    assert (
        pipeline.await_args_list[0].kwargs["story_id"] == "mqa_block_selfharm_reference"
    )


@pytest.mark.asyncio
async def test_seed_skips_books_that_already_carry_a_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    session_factory, _session, _log = _mock_session_factory(pending=[], present=True)
    engine = _mock_engine()
    pipeline = AsyncMock()

    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        failures = await seed_moderation_qa.seed(
            engine=engine, session_factory=session_factory
        )

    pipeline.assert_not_awaited()
    assert failures == []


@pytest.mark.asyncio
async def test_seed_returns_the_failed_ids_so_main_can_exit_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    doomed = ["mqa_clean_meadow_market", "mqa_block_selfharm_reference"]
    session_factory, _session, _log = _mock_session_factory(
        pending=doomed, present=True
    )
    engine = _mock_engine()
    pipeline = AsyncMock(side_effect=[RuntimeError("boom"), RuntimeError("boom")])

    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        failures = await seed_moderation_qa.seed(
            engine=engine, session_factory=session_factory
        )

    assert sorted(failures) == sorted(doomed)


class _Args:
    """Minimal stand-in for the parsed argparse namespace."""

    skip_moderation = False


def _patched_main(seed_mock: AsyncMock) -> Any:
    """Patch _parse_args and seed so main() can run without a database."""
    return (
        patch.object(
            seed_moderation_qa, "_parse_args", MagicMock(return_value=_Args())
        ),
        patch.object(seed_moderation_qa, "seed", seed_mock),
    )


def test_main_exits_nonzero_when_any_book_failed_moderation() -> None:
    """Six consecutive provider failures must not read as success."""
    parse_args, seed_patch = _patched_main(AsyncMock(return_value=["mqa_a"]))
    with parse_args, seed_patch, pytest.raises(SystemExit) as exc:
        seed_moderation_qa.main()
    assert "1 book(s) failed moderation" in str(exc.value)


def test_main_exits_zero_when_nothing_failed() -> None:
    parse_args, seed_patch = _patched_main(AsyncMock(return_value=[]))
    with parse_args, seed_patch:
        seed_moderation_qa.main()


def test_main_exits_with_the_offending_path_when_the_corpus_cannot_load() -> None:
    broken = ConfigurationError("moderation QA corpus manifest is unreadable: /x.json")
    parse_args, seed_patch = _patched_main(AsyncMock(side_effect=broken))
    with parse_args, seed_patch, pytest.raises(SystemExit) as exc:
        seed_moderation_qa.main()
    assert "/x.json" in str(exc.value)


@pytest.mark.asyncio
async def test_seed_never_creates_a_child_profile_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Containment layer 2, whole-script scope: no ChildProfile is ever added.

    Complements test_ensure_qa_family_never_creates_a_child_profile by
    covering every row seed() adds, not just the family helper's.
    """
    monkeypatch.setenv("ENVIRONMENT", "staging")
    session_factory, session, _log = _mock_session_factory()
    engine = _mock_engine()

    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", AsyncMock()),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        await seed_moderation_qa.seed(engine=engine, session_factory=session_factory)

    added = [call.args[0] for call in session.add.call_args_list]
    assert added, "seed() added no rows at all; the assertion below is vacuous"
    assert not any(isinstance(row, ChildProfile) for row in added)
    assert {type(row).__name__ for row in added} <= {
        "Family",
        "Storybook",
        "StorybookVersion",
    }
