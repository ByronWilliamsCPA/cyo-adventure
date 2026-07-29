"""Unit tests for scripts/prototype_sentinel_reinsertion.py (plan 3.4 re-analysis).

Exercises the callable core (`main(argv)`) directly, never a subprocess, per
the `scripts/measure_sentinel_survival.py` sibling's precedent. The focus is
the recoverable-input contract: every way a saved fill file can be bad has to
produce a path-labelled diagnostic and exit 1, never a traceback, because the
operator's next move is to delete or re-generate the one offending file out of
a run directory holding hundreds.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts.prototype_sentinel_reinsertion import main

if TYPE_CHECKING:
    from pathlib import Path


def _fills_dir(tmp_path: Path) -> Path:
    """Create and return an empty `fills/` subdirectory under a run directory."""
    fills = tmp_path / "run" / "fills"
    fills.mkdir(parents=True)
    return fills


@pytest.mark.unit
def test_truncated_fill_file_reports_the_path_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fill file that is not valid JSON names itself in the error, no traceback.

    `--save-fills` writes one file per trial across a long provider run, so a
    run killed mid-write leaves exactly this: a truncated file. The regression
    guarded here is that `json.JSONDecodeError` used to escape the CLI's
    `except TypeError` entirely.
    """
    fills = _fills_dir(tmp_path)
    (fills / "trial-0007.json").write_text('{"specimen_slug": "a', encoding="utf-8")

    exit_code = main([str(fills.parent)])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "trial-0007.json" in err
    assert "not valid JSON" in err


@pytest.mark.unit
def test_unreadable_fill_file_reports_the_path_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fill file that cannot be read names itself in the error, no traceback.

    Uses a directory named `*.json` rather than a chmod, so the test behaves
    the same when run as root (where a 0o000 file is still readable) and on
    filesystems that do not honour permission bits.
    """
    fills = _fills_dir(tmp_path)
    (fills / "trial-0008.json").mkdir()

    exit_code = main([str(fills.parent)])

    assert exit_code == 1
    assert "trial-0008.json" in capsys.readouterr().err


@pytest.mark.unit
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ('["not an object"]', "expected a JSON object"),
        ('{"provider": "mock"}', "'specimen_slug' missing or not a string"),
        ('{"specimen_slug": "a"}', "'provider' missing or not a string"),
        (
            '{"specimen_slug": "a", "provider": "mock"}',
            "'bound_skeleton' missing or not an object",
        ),
        (
            '{"specimen_slug": "a", "provider": "mock", "bound_skeleton": {}}',
            "'filled_storybook' missing or not an object",
        ),
    ],
)
def test_misshapen_fill_file_reports_the_offending_field(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    payload: str,
    expected: str,
) -> None:
    """Valid JSON of the wrong shape names the field that is wrong, and exits 1."""
    fills = _fills_dir(tmp_path)
    (fills / "trial-0009.json").write_text(payload, encoding="utf-8")

    exit_code = main([str(fills.parent)])

    assert exit_code == 1
    assert expected in capsys.readouterr().err


@pytest.mark.unit
def test_missing_fills_directory_points_at_the_save_fills_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run directory with no fills/ tells the operator which flag to re-run with."""
    exit_code = main([str(tmp_path)])

    assert exit_code == 1
    assert "--save-fills" in capsys.readouterr().err


@pytest.mark.unit
def test_empty_fills_directory_is_an_error_not_an_empty_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An existing but empty fills/ must not write a vacuously clean report.

    A zero-trial aggregate would render 0/0 and could read as a passing
    viability result, which is the report this script exists to produce.
    """
    fills = _fills_dir(tmp_path)

    exit_code = main([str(fills.parent)])

    assert exit_code == 1
    assert "no saved fill files" in capsys.readouterr().err
    assert not (fills.parent / "reinsertion-report.json").exists()


@pytest.mark.unit
def test_a_well_formed_fill_writes_both_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The happy path writes reinsertion-report.json and .md into the run dir."""
    fills = _fills_dir(tmp_path)
    node: dict[str, object] = {
        "id": "n1",
        "body": "The {~HERO:Explorer~} set off.",
        "choices": [],
    }
    (fills / "trial-0001.json").write_text(
        json.dumps(
            {
                "specimen_slug": "3-5:puddle-jumping-day",
                "provider": "mock",
                "bound_skeleton": {"nodes": [node]},
                "filled_storybook": {
                    "nodes": [{**node, "body": "The Explorer set off."}]
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = main([str(fills.parent)])

    assert exit_code == 0
    assert (fills.parent / "reinsertion-report.json").is_file()
    assert (fills.parent / "reinsertion-report.md").is_file()
    assert "sentinel-reinsertion:" in capsys.readouterr().out
