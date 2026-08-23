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
tool observes by default and refuses to invent a bound. `UW-C341` was ruled on
2026-08-23 (`AL-568`) and the ruling kept it that way: the gate went to
validator rule SR-10 on run LENGTH, because a rate cannot tell a deliberate
refrain from a reused passage at any threshold. This tool stays the ranked
view, which is what names the offending PAIR.
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

    A rate cannot separate a deliberate refrain from a reused passage, since it
    totals overlap and both raise the total. That is why no default bound is
    shipped here and why the series case is gated by validator rule SR-10 on
    run LENGTH instead (`AL-568`). The tool declines rather than guessing.
    """
    code = main(
        [
            str(_OUT / "the-harrowstone-keep.filled.json"),
            str(_OUT / "the-sunken-temple.filled.json"),
            "--check",
        ]
    )
    assert code == 2
    assert "SR-10" in capsys.readouterr().err


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
    blob = json.loads(
        (_OUT / "the-harrowstone-keep.filled.json").read_text(encoding="utf-8")
    )
    for node in blob["nodes"]:
        body = str(node.get("body", ""))
        if len(body) > 40:
            assert body[:40] not in out


def test_a_single_fill_is_not_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Convergence is a property of a set; one book yields an empty report."""
    assert main([str(_OUT / "the-harrowstone-keep.filled.json")]) == 0
    assert "0 pair" in capsys.readouterr().out


def test_check_on_a_single_fill_fails_rather_than_passing_vacuously(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A gate that measured nothing has not passed.

    The counterpart to the test above: observing one book is a legitimate ask
    and exits 0, but asking a GATE about one book is not. Zero pairs makes the
    per-row bound check vacuously true, so returning 0 here would report a
    clean corpus the tool never compared. That is how an empty or
    mis-globbed artifact satisfies a gate it should have failed.
    """
    code = main(
        [
            str(_OUT / "the-harrowstone-keep.filled.json"),
            "--check",
            "--max-per-1000",
            "5",
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "at least two fills" in err
    assert "0 pairs measured" in err


def test_a_file_that_is_not_utf8_is_reported_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``read_text`` raises ``UnicodeDecodeError``, which is not a JSON error.

    ``_load_corpus`` documents that it reports the first failure and returns
    None. A decode failure escaped that contract, because
    ``UnicodeDecodeError`` is a ``ValueError`` and not a
    ``json.JSONDecodeError``, so a mis-encoded corpus file reached the caller
    as a traceback rather than the documented exit 2.
    """
    bad = tmp_path / "mojibake.filled.json"
    bad.write_bytes(b'{"id": "\xff\xfe not utf-8"}')

    assert main([str(bad), str(_OUT / "the-harrowstone-keep.filled.json")]) == 2
    assert "cannot load" in capsys.readouterr().err


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
    corpus contains a real defect, and no bound on this rate exists, so an "ok"
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
    assert "SR-10" in last


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
