import pytest

from cyo_adventure.generation.import_cli import build_arg_parser


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
