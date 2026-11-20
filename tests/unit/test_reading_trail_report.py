"""Unit tests for the reading-trail report aggregation and its script shell."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.reading_trail.report import (
    TrailRecord,
    build_report,
    render_report,
)

if TYPE_CHECKING:
    from types import ModuleType

_ROOT = Path(__file__).resolve().parents[2]
_LANTERN = (
    _ROOT / "tests" / "fixtures" / "storybook" / "valid" / "03_tier2_lantern.json"
)
_KEY = ("s_lantern_cave", 1)


def _s(
    seq: int, kind: str, node: str, choice: str | None = None, t: int = 0
) -> dict[str, object]:
    return {
        "seq": seq,
        "kind": kind,
        "node_id": node,
        "choice_id": choice,
        "elapsed_s": t,
    }


def _blobs() -> dict[tuple[str, int], dict[str, object]]:
    return {_KEY: json.loads(_LANTERN.read_text(encoding="utf-8"))}


def _trail(label: str, steps: list[dict[str, object]]) -> TrailRecord:
    return TrailRecord(
        storybook_id=_KEY[0], version=_KEY[1], profile_label=label, steps=steps
    )


def _seeded() -> list[TrailRecord]:
    finished = [
        _s(0, "start", "n_open"),
        _s(1, "auto", "n_open", "c_n_open", 4),
        _s(2, "choice", "n_entrance", "c_take_lantern", 30),
        _s(3, "choice", "n_cave_fork", "c_dark_passage", 60),
        _s(4, "end", "n_treasure", None, 61),
    ]
    # Rewound twice in a row ("try a different choice") to n_entrance, then
    # chose differently and left at the fork after 2 minutes there.
    rewound_and_left = [
        _s(0, "start", "n_open"),
        _s(1, "auto", "n_open", "c_n_open", 3),
        _s(2, "choice", "n_entrance", "c_take_lantern", 10),
        _s(3, "back", "n_cave_fork", None, 20),
        _s(4, "back", "n_entrance", None, 21),
        _s(5, "choice", "n_entrance", "c_ignore_lantern", 25),
        _s(6, "leave", "n_cave_fork", None, 145),
    ]
    resumed_silent = [_s(0, "resume", "n_cave_fork")]
    restarted = [_s(0, "start", "n_open"), _s(1, "restart", "n_open", None, 30)]
    return [
        _trail("Ada", finished),
        _trail("Ada", rewound_and_left),
        _trail("Ben", resumed_silent),
        _trail("Ben", restarted),
    ]


def test_build_report_counts_reads_endings_stops_picks_and_rewinds() -> None:
    """The aggregate answers every question the owner asked."""
    (report,) = build_report(_seeded(), _blobs())
    assert report.title is not None
    assert (report.reads_started, report.reads_resumed, report.reads_finished) == (
        3,
        1,
        1,
    )
    assert dict(report.endings) == {"e_treasure_found": 1}
    assert report.stops["n_cave_fork"].reads == 2
    assert report.stops["n_cave_fork"].left == 1
    assert report.stops["n_cave_fork"].dwell_seconds == [120]
    assert report.stops["n_open"].restarted == 1
    assert report.picks["n_entrance"]["c_take_lantern"] == 2
    assert report.picks["n_entrance"]["c_ignore_lantern"] == 1
    assert report.picks["n_entrance"]["xc_start_extra"] == 0
    # auto steps are never counted as picks; single-choice nodes are not listed.
    assert "n_open" not in report.picks
    # One rewind run, counted once at the node it landed on.
    assert dict(report.rewinds_to) == {"n_entrance": 1}
    assert report.by_profile == {}


def test_by_profile_breakdown_is_opt_in() -> None:
    """Profile labels appear only when asked for."""
    (report,) = build_report(_seeded(), _blobs(), by_profile=True)
    assert report.by_profile == {"Ada": [2, 1], "Ben": [1, 0]}
    text = render_report([report], _blobs())
    assert "Ada: 2 / 1" in text
    plain = render_report(build_report(_seeded(), _blobs()), _blobs())
    assert "Ada" not in plain
    assert "Ben" not in plain


def test_render_report_shapes_and_empty_case() -> None:
    """The text names endings, stops with dwell, and picks per choice."""
    text = render_report(build_report(_seeded(), _blobs()), _blobs())
    assert "Reads started: 3   resumed sessions: 1   finished: 1" in text
    assert "e_treasure_found" in text
    assert "n_cave_fork  (left 1, restarted 0, median time on node 2.0 min)" in text
    assert "n_entrance  (rewinds back to here: 1)" in text
    assert render_report([], {}) == "No reading trails recorded.\n"


def test_trails_for_a_missing_version_are_skipped() -> None:
    """A trail whose blob is absent is dropped rather than crashing."""
    assert build_report(_seeded(), {}) == []


def _load_script() -> ModuleType:
    path = _ROOT / "scripts" / "report_reading_trail.py"
    spec = importlib.util.spec_from_file_location("report_reading_trail", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["report_reading_trail"] = module
    spec.loader.exec_module(module)
    return module


def test_script_requires_the_env_var(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no URL in the environment the script exits 1 and reads nothing."""
    script = _load_script()
    monkeypatch.delenv(script.DATABASE_URL_ENV, raising=False)
    assert script.main([]) == 1
    assert "is not set" in capsys.readouterr().err


def test_bad_url_is_not_echoed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A malformed or unreachable URL is reported by class name only."""
    script = _load_script()
    secret = "s3cret-password-value"
    monkeypatch.setenv(script.DATABASE_URL_ENV, f"::not a url {secret}")
    assert script.main([]) == 1
    monkeypatch.setenv(
        script.DATABASE_URL_ENV, f"postgresql://user:{secret}@127.0.0.1:1/db"
    )
    assert script.main([]) == 1
    captured = capsys.readouterr()
    assert secret not in captured.err
    assert secret not in captured.out


def test_script_rejects_a_database_url_argument() -> None:
    """There is no command-line way to pass a database URL."""
    script = _load_script()
    with pytest.raises(SystemExit):
        script.main(["--database-url", "postgresql://x"])
