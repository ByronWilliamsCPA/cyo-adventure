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
# _moderate_new_books: never approve/publish, only run_moderation_pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderate_new_books_calls_run_moderation_pipeline_per_book() -> None:
    session = AsyncMock()
    pipeline = AsyncMock()
    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        await seed_moderation_qa._moderate_new_books(session, ["mqa_a", "mqa_b"])

    assert pipeline.await_count == 2
    called_story_ids = {call.kwargs["story_id"] for call in pipeline.await_args_list}
    assert called_story_ids == {"mqa_a", "mqa_b"}


@pytest.mark.asyncio
async def test_moderate_new_books_never_calls_approve_or_publish() -> None:
    """The moderation step must drive only run_moderation_pipeline.

    run_moderation_pipeline itself may only call submit/auto_reject (its own
    module contract); this test pins that _moderate_new_books calls nothing
    else that could publish a fixture, by asserting publishing.service.approve
    is never imported/called from this module's namespace.
    """
    assert "approve" not in vars(seed_moderation_qa)
    assert not hasattr(seed_moderation_qa, "publish")


@pytest.mark.asyncio
async def test_moderate_new_books_continues_after_one_failure() -> None:
    session = AsyncMock()
    pipeline = AsyncMock(side_effect=[RuntimeError("boom"), None])
    with (
        patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline),
        patch.object(seed_moderation_qa, "build_provider", MagicMock()),
    ):
        await seed_moderation_qa._moderate_new_books(session, ["mqa_a", "mqa_b"])

    assert pipeline.await_count == 2


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


def _mock_session_factory() -> tuple[MagicMock, MagicMock]:
    session = AsyncMock()
    session.add = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.commit = AsyncMock()

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
    return session_factory, session


@pytest.mark.asyncio
async def test_seed_skips_moderation_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    session_factory, session = _mock_session_factory()
    engine = _mock_engine()
    pipeline = AsyncMock()

    with patch.object(seed_moderation_qa, "run_moderation_pipeline", pipeline):
        await seed_moderation_qa.seed(
            engine=engine, session_factory=session_factory, moderate=False
        )

    pipeline.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_runs_moderation_on_newly_inserted_books_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    session_factory, session = _mock_session_factory()
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
