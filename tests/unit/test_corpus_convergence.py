"""Unit tests for the corpus convergence observer (``scripts/check_corpus_convergence.py``).

The request-path advisory in ``moderation/leaf_diversity.py`` compares one new
fill against one partner chosen by SAME SKELETON within the SAME FAMILY. That
is the right partner for the question it asks and it is structurally unable to
see two books that converge across skeletons, across families, or across a
series. This tool is the other half: all pairs of a given corpus, classified by
what relationship the pair actually has, with prose-free output so the report
can be read by someone who is not entitled to read the stories.

The threshold assertions are anchored on the committed corpus, measured
2026-08-23 over 465 pairs of ``out/*.filled.json`` (body-only shared 4-grams
per 1000 mean words):

    class        n     median    p90      max
    unrelated  464       0.59    2.52    12.92
    series       1     215.25  215.25   215.25   <- the AL-564 defect

The one series pair is 16.7x the highest of every other pair in the corpus, so
ranking alone isolates it; no threshold is needed to find it, which is why this
tool observes by default and refuses to invent a bound (`UW-C341`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.check_corpus_convergence import (
    PairRow,
    classify_pair,
    main,
    rank_pairs,
)

pytestmark = pytest.mark.unit

_OUT = Path("out")


def _story(
    story_id: str,
    bodies: list[str],
    *,
    series_id: str | None = None,
    book_index: int = 1,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"age_band": "8-11"}
    if series_id is not None:
        metadata["series"] = {"series_id": series_id, "book_index": book_index}
    return {
        "id": story_id,
        "metadata": metadata,
        "nodes": [
            {"id": f"n{i}", "body": body, "choices": []}
            for i, body in enumerate(bodies)
        ],
    }


def test_two_books_of_one_series_classify_as_series() -> None:
    """The series relationship wins: it is the one a child reads end to end."""
    a = _story("sk_a", ["x"], series_id="brass-lantern", book_index=1)
    b = _story("sk_b", ["y"], series_id="brass-lantern", book_index=2)
    assert classify_pair(a, b) == "series"


def test_two_fills_of_one_skeleton_classify_as_sibling() -> None:
    """Same skeleton id, no shared series: the WS-2 re-theming relationship."""
    a = _story("sk_cave", ["x"])
    b = _story("sk_cave", ["y"])
    assert classify_pair(a, b) == "sibling"


def test_books_of_different_series_are_not_a_series_pair() -> None:
    """Both declaring *a* series is not the same as declaring the SAME one."""
    a = _story("sk_a", ["x"], series_id="brass-lantern")
    b = _story("sk_b", ["y"], series_id="tin-whistle")
    assert classify_pair(a, b) == "unrelated"


def test_unrelated_books_classify_as_unrelated() -> None:
    """The baseline class, which supplies the corpus noise floor."""
    assert classify_pair(_story("sk_a", ["x"]), _story("sk_b", ["y"])) == "unrelated"


def test_rank_pairs_breaks_rate_ties_deterministically() -> None:
    """Two runs over one corpus must produce one report.

    ``AL-565``: the sibling-fill tool printed an evidence list whose tie order
    permuted per process, which read as churn in the fills. Ties break on the
    pair's names here so the report is a function of its input.
    """
    rows = [
        PairRow("zebra", "yak", "unrelated", 5, 3.0),
        PairRow("apple", "beetle", "unrelated", 5, 3.0),
        PairRow("mango", "melon", "series", 9, 9.0),
    ]
    assert [r.left for r in rank_pairs(rows, limit=3)] == ["mango", "apple", "zebra"]


def test_check_without_an_explicit_bound_refuses_rather_than_inventing_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--check`` with no bound exits 2 and says why.

    Where the bound sits is an open owner decision (`UW-C341`): a series may
    share phrasing deliberately, and the only anchors so far are one converged
    pair at 215 and a corpus whose every other pair is under 13. A default
    would be a guess that later reads as a ruling, so the tool declines.
    """
    code = main(
        [
            str(_OUT / "the-harrowstone-keep.filled.json"),
            str(_OUT / "the-sunken-temple.filled.json"),
            "--check",
        ]
    )
    assert code == 2
    assert "UW-C341" in capsys.readouterr().err


def test_check_gates_on_an_explicitly_given_bound(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With a bound supplied, the tool gates on it."""
    argv = [
        str(_OUT / "the-harrowstone-keep.filled.json"),
        str(_OUT / "the-sunken-temple.filled.json"),
        "--check",
        "--max-per-1000",
    ]
    assert main([*argv, "100"]) == 1
    capsys.readouterr()
    assert main([*argv, "500"]) == 0


def test_the_committed_series_pair_ranks_above_every_unrelated_pair(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The observer finds the AL-564 defect in the real corpus by ranking alone.

    Run over the whole committed corpus, the brass-lantern pair is the top row
    and no unrelated pair comes near it. This is the falsification that
    justifies shipping the tool without a threshold: if the defect did not
    separate from the noise floor by ranking, a bound would be the only way to
    find it and the tool could not ship until one was ruled.
    """
    assert main([str(_OUT), "--top", "3"]) == 0
    ranked = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("  ") and " ~ " in line
    ]
    assert "[series] the-harrowstone-keep ~ the-sunken-temple" in ranked[0]
    assert all("[unrelated]" in line for line in ranked[1:])


def test_the_report_carries_no_story_prose(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Identifiers and numbers only.

    An all-pairs sweep is the one report here that spans books belonging to
    different people, so it must be readable by an operator who is not
    entitled to read any of them. Emitting a shared phrase as evidence, which
    the sibling-fill tool does for its single-author corpus, would make this
    report a disclosure surface.
    """
    assert (
        main(
            [
                str(_OUT / "the-harrowstone-keep.filled.json"),
                str(_OUT / "the-sunken-temple.filled.json"),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    blob = json.loads((_OUT / "the-harrowstone-keep.filled.json").read_text())
    for node in blob["nodes"]:
        body = str(node.get("body", ""))
        if len(body) > 40:
            assert body[:40] not in out


def test_a_single_fill_is_not_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Convergence is a property of a set; one book yields an empty report."""
    assert main([str(_OUT / "the-harrowstone-keep.filled.json")]) == 0
    assert "0 pair" in capsys.readouterr().out


def test_an_unreadable_path_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    """A corpus the caller thought they passed but did not is not a clean run."""
    assert main(["out/definitely-not-a-file.filled.json"]) == 2
    assert "cannot load" in capsys.readouterr().err


def test_observe_mode_ends_with_a_summary_that_claims_no_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The last line names the worst pair without passing or failing it.

    ``scripts/run_guard_battery.py`` reads a checker's last "ok"/"FAIL" line,
    falling back to its final line, so a tool run without a bound must end on
    something a battery row can quote. It must not end on "ok": the observed
    corpus contains a real defect, and no bound has been ruled, so an "ok"
    would be a verdict this tool is deliberately not entitled to give.
    """
    assert (
        main(
            [
                str(_OUT / "the-harrowstone-keep.filled.json"),
                str(_OUT / "the-sunken-temple.filled.json"),
            ]
        )
        == 0
    )
    last = capsys.readouterr().out.splitlines()[-1]
    assert not last.startswith(("ok", "FAIL"))
    assert "215" in last
    assert "series" in last
    assert "UW-C341" in last


def test_check_mode_ends_with_an_ok_line_when_the_corpus_clears_the_bound(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A cleared bound ends on the "ok" prefix the battery looks for."""
    assert (
        main(
            [
                str(_OUT / "the-harrowstone-keep.filled.json"),
                str(_OUT / "the-sunken-temple.filled.json"),
                "--check",
                "--max-per-1000",
                "500",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out.splitlines()[-1].startswith("ok ")


def test_check_mode_ends_with_a_fail_line_naming_the_breaching_pair(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A breached bound ends on "FAIL" and says which pair breached it."""
    assert (
        main(
            [
                str(_OUT / "the-harrowstone-keep.filled.json"),
                str(_OUT / "the-sunken-temple.filled.json"),
                "--check",
                "--max-per-1000",
                "100",
            ]
        )
        == 1
    )
    last = capsys.readouterr().out.splitlines()[-1]
    assert last.startswith("FAIL ")
    assert "the-sunken-temple" in last
