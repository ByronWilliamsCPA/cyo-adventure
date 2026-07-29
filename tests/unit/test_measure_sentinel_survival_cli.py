"""Unit tests for scripts/measure_sentinel_survival.py (plan 3.4 CLI runner).

Exercises the callable core (`main(argv)`) directly, never a subprocess, per
this repo's `scripts/mutate_skeleton.py` precedent. Covers: a full
`--providers mock` dry run over a handful of specimens (the plumbing proof,
end to end), the out-dir-under-skeletons/ refusal, and malformed-argument
handling. Never invokes a live, paid provider.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts.measure_sentinel_survival import (
    _select_fixture_pairs,  # pyright: ignore[reportPrivateUsage]
    main,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.unit
def test_mock_dry_run_writes_a_labeled_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A --providers mock run writes report.json/report.md, banner included."""
    out_dir = tmp_path / "results"
    exit_code = main(
        [
            "--providers",
            "mock",
            "--out-dir",
            str(out_dir),
            "--skeletons",
            "3-5:puddle-jumping-day",
            "--skeletons",
            "5-8:the-night-market",
            "--count",
            "3",
        ]
    )
    assert exit_code == 0

    run_dirs = list(out_dir.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    report_json = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report_json["dry_run"] is True
    assert report_json["dry_run_banner"] == "PLUMBING DRY-RUN, not a survival number."
    assert report_json["total_runs"] == 3

    report_md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "PLUMBING DRY-RUN, not a survival number." in report_md

    captured = capsys.readouterr()
    assert "sentinel-survival:" in captured.out


@pytest.mark.unit
def test_save_fills_writes_recoverable_trial_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--save-fills persists every trial under <run-dir>/fills/, recoverably.

    Each fill file must carry everything
    ``scripts/prototype_sentinel_reinsertion.py`` needs to recompute
    expectations offline without re-running specimen construction:
    specimen_slug, provider, slot_bindings, bound_skeleton, and
    filled_storybook (exactly what ``classify_fill`` was given).
    """
    out_dir = tmp_path / "results"
    exit_code = main(
        [
            "--providers",
            "mock",
            "--out-dir",
            str(out_dir),
            "--skeletons",
            "3-5:puddle-jumping-day",
            "--count",
            "2",
            "--save-fills",
        ]
    )
    assert exit_code == 0

    run_dir = next(out_dir.iterdir())
    fills_dir = run_dir / "fills"
    assert fills_dir.is_dir()

    fill_files = sorted(fills_dir.glob("*.json"))
    assert len(fill_files) == 2
    for index, path in enumerate(fill_files):
        assert path.name.startswith(f"{index}-mock-")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["specimen_slug"]
        assert payload["provider"] == "mock"
        assert "slot_bindings" in payload
        assert isinstance(payload["bound_skeleton"], dict)
        assert isinstance(payload["filled_storybook"], dict)

    captured = capsys.readouterr()
    assert "sentinel-survival:" in captured.out


@pytest.mark.unit
def test_without_save_fills_no_fills_directory_is_created(
    tmp_path: Path,
) -> None:
    """Omitting --save-fills matches prior behavior exactly: no fills/ ever appears."""
    out_dir = tmp_path / "results"
    exit_code = main(
        [
            "--providers",
            "mock",
            "--out-dir",
            str(out_dir),
            "--skeletons",
            "3-5:puddle-jumping-day",
            "--count",
            "2",
        ]
    )
    assert exit_code == 0

    run_dir = next(out_dir.iterdir())
    assert not (run_dir / "fills").exists()


@pytest.mark.unit
def test_refuses_out_dir_under_skeletons(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--out-dir resolving under skeletons/ is refused, never written to."""
    out_dir = tmp_path / "skeletons" / "scratch"
    exit_code = main(
        [
            "--providers",
            "mock",
            "--out-dir",
            str(out_dir),
            "--count",
            "1",
        ]
    )
    assert exit_code == 1
    assert not out_dir.exists()
    captured = capsys.readouterr()
    assert "refusing" in captured.err


@pytest.mark.unit
def test_malformed_skeletons_argument_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A --skeletons entry missing the BAND:SLUG colon errors cleanly."""
    exit_code = main(
        [
            "--providers",
            "mock",
            "--out-dir",
            str(tmp_path / "results"),
            "--skeletons",
            "not-a-valid-entry",
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "BAND:SLUG" in captured.err


@pytest.mark.unit
def test_unrecognized_provider_exits_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unrecognized --providers name errors cleanly, not a raw traceback.

    ``build_provider`` raises ``cyo_adventure.core.exceptions.ConfigurationError``
    (not a ``ValueError`` subclass) for an unrecognized provider name; this
    exercises the dedicated try/except around the ``_run_all`` fill call.
    """
    exit_code = main(
        [
            "--providers",
            "mocks",
            "--out-dir",
            str(tmp_path / "results"),
            "--skeletons",
            "3-5:puddle-jumping-day",
            "--count",
            "1",
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err


@pytest.mark.unit
def test_malformed_skeleton_file_exits_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A skeleton file that is not a JSON object errors cleanly.

    ``load_pair`` raises ``TypeError`` for a skeleton file whose JSON root is
    not an object; this exercises the widened fixture-building except clause
    (``(OSError, ValueError, ValidationError, TypeError)``).
    """
    skeletons_root = tmp_path / "skeletons"
    band_dir = skeletons_root / "3-5"
    band_dir.mkdir(parents=True)
    (band_dir / "bad-skeleton.json").write_text("[]", encoding="utf-8")
    (band_dir / "bad-skeleton.contract.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.measure_sentinel_survival._SKELETONS_ROOT", skeletons_root
    )

    exit_code = main(
        [
            "--providers",
            "mock",
            "--out-dir",
            str(tmp_path / "results"),
            "--skeletons",
            "3-5:bad-skeleton",
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err


@pytest.mark.unit
def test_select_fixture_pairs_band_filter() -> None:
    """--band restricts the default fixture set to matching bands only."""
    pairs = _select_fixture_pairs(None, ["3-5", "8-11"])
    assert pairs
    assert all(band in {"3-5", "8-11"} for band, _ in pairs)


@pytest.mark.unit
def test_select_fixture_pairs_explicit_skeletons_override_band() -> None:
    """An explicit --skeletons list overrides the default fixture set entirely."""
    pairs = _select_fixture_pairs(["10-13:the-midnight-museum"], ["3-5"])
    assert pairs == [("10-13", "the-midnight-museum")]
