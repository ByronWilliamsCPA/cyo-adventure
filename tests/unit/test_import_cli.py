import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.import_cli import _run, build_arg_parser, main
from cyo_adventure.generation.import_story import (
    ImportRequest,
    import_filled_story,
    resume_manual_fill,
)


def _closing_run_raising(exc: BaseException) -> object:
    """Build an ``asyncio.run`` stand-in that raises ``exc`` after closing the coroutine.

    ``main()`` builds the real ``_run(...)`` coroutine object as an argument
    to ``asyncio.run(...)``, so patching ``asyncio.run`` with a bare
    ``side_effect=`` exception still leaves that coroutine constructed and
    never awaited: Python warns "coroutine '_run' was never awaited" at GC
    time. Closing it explicitly here silences that at the source instead of
    suppressing the warning globally.
    """

    def _fake_run(coro: object) -> object:
        coro.close()  # type: ignore[attr-defined]
        raise exc

    return _fake_run


def _closing_run_returning(value: object) -> object:
    """Build an ``asyncio.run`` stand-in that returns ``value`` after closing the coroutine.

    See ``_closing_run_raising`` for why the coroutine must be closed.
    """

    def _fake_run(coro: object) -> object:
        coro.close()  # type: ignore[attr-defined]
        return value

    return _fake_run


class _FakeSessionCtx:
    """Minimal async context manager standing in for get_session()'s return.

    core/database.py::get_session() is not an async generator; it directly
    returns an AsyncSession-producing async context manager
    (_session_factory()). Patching get_session with a plain function that
    returns one of these lets _run's `async with get_session() as session:`
    line run without touching a real database.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc: object) -> bool:
        return False


@pytest.mark.unit
def test_arg_parser_requires_path_and_family() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["out/demo.filled.json", "--family", "abc"])
    assert args.path == "out/demo.filled.json"
    assert args.family == "abc"


@pytest.mark.unit
def test_arg_parser_family_and_job_default_to_none() -> None:
    # --family is no longer required at the argparse level: --job is a valid
    # alternative, so the parser must accept omitting both and defer the
    # "one of them is required" check to main().
    parser = build_arg_parser()
    args = parser.parse_args(["out/demo.filled.json"])
    assert args.family is None
    assert args.job is None


@pytest.mark.unit
def test_main_exits_1_on_path_traversal() -> None:
    # A path that resolves outside the working directory must be rejected
    # before any filesystem read (OWASP LLM07 guard).
    code = main(["../../etc/passwd", "--family", str(uuid.uuid4())])
    assert code == 1


@pytest.mark.unit
def test_main_exits_1_on_missing_file() -> None:
    code = main(["no_such_file.json", "--family", str(uuid.uuid4())])
    assert code == 1


@pytest.mark.unit
def test_main_exits_1_on_permission_error() -> None:
    with patch("pathlib.Path.read_text", side_effect=PermissionError("denied")):
        code = main(["some.json", "--family", str(uuid.uuid4())])
    assert code == 1


@pytest.mark.unit
def test_main_exits_1_on_invalid_json(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("not json")
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        code = main([str(f), "--family", str(uuid.uuid4())])
    assert code == 1


@pytest.mark.unit
def test_main_exits_1_on_non_object_json(tmp_path: Path) -> None:
    # A JSON array is syntactically valid but the gate expects a JSON object.
    # Before the fix this produced a raw AttributeError traceback.
    f = tmp_path / "array.json"
    f.write_text(json.dumps([1, 2, 3]))
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        code = main([str(f), "--family", str(uuid.uuid4())])
    assert code == 1


@pytest.mark.unit
def test_main_exits_1_on_invalid_uuid(tmp_path: Path) -> None:
    f = tmp_path / "story.json"
    f.write_text('{"id": "s1"}')
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        code = main([str(f), "--family", "not-a-uuid"])
    assert code == 1


@pytest.mark.unit
def test_main_exits_1_on_validation_error(tmp_path: Path) -> None:
    f = tmp_path / "story.json"
    f.write_text('{"id": "s1"}')
    with (
        patch("pathlib.Path.cwd", return_value=tmp_path),
        patch(
            "asyncio.run",
            side_effect=_closing_run_raising(ValidationError("gate blocked")),
        ),
    ):
        code = main([str(f), "--family", str(uuid.uuid4())])
    assert code == 1


@pytest.mark.unit
def test_main_exits_0_on_success(tmp_path: Path) -> None:
    f = tmp_path / "story.json"
    f.write_text('{"id": "s1"}')
    with (
        patch("pathlib.Path.cwd", return_value=tmp_path),
        # _run returns (story_id, status); a standalone import has no job to
        # downgrade, so status is None.
        patch(
            "asyncio.run",
            side_effect=_closing_run_returning(("story-abc-123", None)),
        ),
    ):
        code = main([str(f), "--family", str(uuid.uuid4())])
    assert code == 0


def test_job_flag_makes_family_optional(tmp_path, monkeypatch) -> None:
    """--job resumes a parked job; --family is not required in that mode."""
    story_path = tmp_path / "story.json"
    story_path.write_text(json.dumps({"id": "s_x"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    captured: dict[str, object] = {}

    def _fake_run(coro: object) -> tuple[str, str]:
        captured["coro"] = coro
        coro.close()  # type: ignore[attr-defined]  # never awaited otherwise
        # _run returns (story_id, status); a resumed job carries its final status.
        return "s_resumed", "passed"

    with patch(
        "cyo_adventure.generation.import_cli.asyncio.run", side_effect=_fake_run
    ):
        code = main(["story.json", "--job", str(uuid.uuid4())])

    assert code == 0
    assert "coro" in captured


def test_missing_family_and_job_is_an_error(tmp_path, monkeypatch) -> None:
    """Without --job, --family is still required."""
    story_path = tmp_path / "story.json"
    story_path.write_text(json.dumps({"id": "s_x"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    code = main(["story.json"])

    assert code == 1


def test_invalid_job_uuid_is_an_error(tmp_path, monkeypatch) -> None:
    """A malformed --job value exits 1 with a clear message, not a traceback."""
    story_path = tmp_path / "story.json"
    story_path.write_text(json.dumps({"id": "s_x"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    code = main(["story.json", "--job", "not-a-uuid"])

    assert code == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_standalone_import_commits_and_returns_story_id_none_status() -> None:
    """_run's no-job branch: build an ImportRequest, persist, and commit.

    Every other test in this file drives _run only through main() with
    asyncio.run patched away, so _run's own coroutine body has never
    actually been awaited. This calls _run(...) directly to exercise the
    real `if job_id is not None:` branch (the False side) and its body.
    """
    fake_session = MagicMock(spec=AsyncSession)
    fake_session.commit = AsyncMock()

    family_id = "fam-uuid"
    blob: dict[str, object] = {"x": 1}
    model = "m"

    mock_import_filled_story = AsyncMock(spec=import_filled_story)
    mock_import_filled_story.return_value = "s_abc123"

    with (
        patch(
            "cyo_adventure.generation.import_cli.get_session",
            return_value=_FakeSessionCtx(fake_session),
        ),
        patch(
            "cyo_adventure.generation.import_cli.import_filled_story",
            mock_import_filled_story,
        ),
        patch(
            "cyo_adventure.generation.import_cli.resume_manual_fill",
            AsyncMock(spec=resume_manual_fill),
        ) as mock_resume,
    ):
        result = await _run(blob=blob, family_id=family_id, model=model, job_id=None)

    assert result == ("s_abc123", None)
    fake_session.commit.assert_awaited_once()
    mock_resume.assert_not_awaited()
    mock_import_filled_story.assert_awaited_once()
    awaited_session, awaited_request = mock_import_filled_story.await_args.args
    assert awaited_session is fake_session
    assert awaited_request == ImportRequest(blob=blob, family_id=family_id, model=model)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_resumes_manual_fill_job_when_job_id_given() -> None:
    """_run's job branch: delegate to resume_manual_fill, no local commit.

    resume_manual_fill owns its own persistence (per its docstring), so
    _run must not call session.commit() itself on this branch; only the
    delegate call and its return value matter here.
    """
    fake_session = MagicMock(spec=AsyncSession)
    fake_session.commit = AsyncMock()

    job_id = "job-uuid"
    blob: dict[str, object] = {"x": 1}
    model = "m"

    mock_resume_manual_fill = AsyncMock(spec=resume_manual_fill)
    mock_resume_manual_fill.return_value = ("s_xyz", "needs_review")

    with (
        patch(
            "cyo_adventure.generation.import_cli.get_session",
            return_value=_FakeSessionCtx(fake_session),
        ),
        patch(
            "cyo_adventure.generation.import_cli.resume_manual_fill",
            mock_resume_manual_fill,
        ),
        patch(
            "cyo_adventure.generation.import_cli.import_filled_story",
            AsyncMock(spec=import_filled_story),
        ) as mock_import,
    ):
        result = await _run(blob=blob, family_id=None, model=model, job_id=job_id)

    assert result == ("s_xyz", "needs_review")
    mock_resume_manual_fill.assert_awaited_once_with(
        fake_session, job_id, blob, model=model
    )
    mock_import.assert_not_awaited()
    fake_session.commit.assert_not_awaited()
