import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.import_cli import build_arg_parser, main


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
        patch("asyncio.run", side_effect=ValidationError("gate blocked")),
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
        patch("asyncio.run", return_value=("story-abc-123", None)),
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
