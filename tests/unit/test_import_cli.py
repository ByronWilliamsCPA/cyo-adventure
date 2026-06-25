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
def test_arg_parser_errors_without_family() -> None:
    parser = build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["out/demo.filled.json"])


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
        patch("asyncio.run", return_value="story-abc-123"),
    ):
        code = main([str(f), "--family", str(uuid.uuid4())])
    assert code == 0
