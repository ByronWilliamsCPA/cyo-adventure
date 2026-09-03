# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""`RS-CAL1`: tests for the production advisory-floor replay.

Three of these pin traps the first version of this analysis fell into:
node hits counted band-wide instead of per book (node ids repeat across books,
so `count(DISTINCT node_id)` silently merges different books' nodes), floors
below the production floor reported as "no change" when the data simply does
not exist, and reviewer load measured in findings when a single merged finding
spans up to 408 nodes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from cyo_adventure.api.review_surface import (
    _is_low_advisory as surface_is_low_advisory,  # pyright: ignore[reportPrivateUsage]
)
from cyo_adventure.api.schemas import FindingView
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.moderation.report import FindingSeverity, Source, Verdict
from scripts.replay_production_floors import (
    BAND_ORDER,
    DEFAULT_EXTRACT,
    PRODUCTION_FLOOR,
    Scenario,
    _is_low_advisory,  # pyright: ignore[reportPrivateUsage]
    evaluate,
    load_extract,
    main,
    render_markdown,
)

# ``DEFAULT_EXTRACT`` is relative to the repository root (the script is run
# from there), so it is anchored against ``__file__`` rather than against the
# process working directory; otherwise every fixture-dependent test below fails
# with FileNotFoundError when pytest is invoked from anywhere else.
EXTRACT = Path(__file__).resolve().parents[2] / DEFAULT_EXTRACT


def _records(value: object, *, label: str) -> list[dict[str, object]]:
    """Validate that ``value`` is a list of string-keyed objects, and return it.

    ``load_extract`` hands back ``dict[str, object]`` because that is all JSON
    promises, so every nested shape the assertions below index into has to be
    proven before it can be typed. The proof is a real runtime walk rather than
    a bare cast: a cast alone would let a malformed extract surface as an
    ``AttributeError`` inside an unrelated assertion, and would make this module
    claim an input shape it never checked.

    Args:
        value: The raw JSON value to validate.
        label: The extract path being validated, used in the failure message.

    Returns:
        list[dict[str, object]]: The same records, typed.

    Raises:
        TypeError: If the value is not a list of objects with string keys.
    """
    if not isinstance(value, list):
        msg = f"{label}: expected a list, got {type(value).__name__}"
        raise TypeError(msg)
    records: list[dict[str, object]] = []
    for index, item in enumerate(cast("list[object]", value)):
        if not isinstance(item, dict):
            msg = f"{label}[{index}]: expected an object, got {type(item).__name__}"
            raise TypeError(msg)
        keyed = cast("dict[object, object]", item)
        non_str = sorted(repr(key) for key in keyed if not isinstance(key, str))
        if non_str:
            msg = f"{label}[{index}]: non-string keys {', '.join(non_str)}"
            raise TypeError(msg)
        records.append(cast("dict[str, object]", item))
    return records


@pytest.fixture(scope="module")
def books() -> list[dict[str, object]]:
    """The anonymized production findings extract."""
    return _records(load_extract(EXTRACT)["books"], label="books")


def _finding(**kw: object) -> dict[str, object]:
    """A stored-report finding with sensible defaults."""
    base: dict[str, object] = {
        "source": "openai",
        "category": "violence",
        "verdict": "advisory",
        "severity": "low",
        "score": 0.5,
        "structural": False,
        "stage": "0",
        "node_ixs": [0],
    }
    base.update(kw)
    return base


@pytest.mark.parametrize(
    ("severity", "verdict"),
    [
        (FindingSeverity.LOW, Verdict.ADVISORY),
        (FindingSeverity.LOW, Verdict.FLAG),
        (FindingSeverity.MEDIUM, Verdict.ADVISORY),
        (FindingSeverity.HIGH, Verdict.BLOCK),
        (None, Verdict.ADVISORY),
    ],
)
def test_low_advisory_predicate_matches_the_review_surface(
    severity: FindingSeverity | None, verdict: Verdict
) -> None:
    """The JSON mirror agrees with the real surface predicate.

    The replay's headline claim is that the shipped `RS-A` low-advisory collapse
    removes 97% of production reviewer load. That claim is only about the shipped
    behaviour if this predicate is the shipped predicate, so both are run over
    the same cases.
    """
    view = FindingView(
        stage=0,
        source=Source.OPENAI,
        category="violence",
        node_id="n1",
        verdict=verdict,
        score=0.5,
        message="m",
        severity=severity,
    )
    mirrored = _is_low_advisory(
        {
            "severity": None if severity is None else severity.value,
            "verdict": verdict.value,
        }
    )
    assert mirrored == surface_is_low_advisory(view)


def test_node_hits_are_counted_per_book_not_band_wide() -> None:
    """Two books that both hit their own node 0 are two node hits, not one.

    Node identifiers repeat across books, so a band-wide DISTINCT over raw node
    ids merges unrelated books' nodes and undercounts reviewer load. This is the
    defect the first pass of this analysis shipped in SQL.
    """
    books: list[dict[str, object]] = [
        {"age_band": "8-11", "node_count": 10, "findings": [_finding(node_ixs=[0])]},
        {"age_band": "8-11", "node_count": 10, "findings": [_finding(node_ixs=[0])]},
    ]
    totals = evaluate(books, Scenario(name="t"))
    assert totals["8-11"].node_hits == 2
    assert totals["8-11"].books == 2
    assert totals["8-11"].nodes == 20


def test_occurrences_and_findings_are_different_axes() -> None:
    """One merged finding spanning 40 nodes is 1 finding and 40 occurrences."""
    books: list[dict[str, object]] = [
        {
            "age_band": "16+",
            "node_count": 50,
            "findings": [_finding(node_ixs=list(range(40)))],
        }
    ]
    totals = evaluate(books, Scenario(name="t"))["16+"]
    assert totals.findings == 1
    assert totals.occurrences == 40
    assert totals.node_hits == 40
    assert totals.occurrences_per_node == pytest.approx(0.8)


def test_an_unscored_finding_survives_every_floor() -> None:
    """No floor can remove a finding the classifier could not grade.

    Treating a missing score as zero would delete structural and verdict-only
    safety signal, which is the direction that gets a book published.
    """
    books: list[dict[str, object]] = [
        {"age_band": "16+", "node_count": 5, "findings": [_finding(score=None)]}
    ]
    for floor in (0.01, 0.5, 0.99):
        assert evaluate(books, Scenario(name="t", default=floor))["16+"].findings == 1


def test_a_per_category_floor_matches_the_slash_subcategory_but_not_a_prefix() -> None:
    """`violence` covers `violence/graphic` and does not cover `violencex`."""
    scenario = Scenario(name="t", per_category={"violence": 0.5})
    assert scenario.floor_for("violence") == pytest.approx(0.5)
    assert scenario.floor_for("violence/graphic") == pytest.approx(0.5)
    assert scenario.floor_for("violencex") == pytest.approx(PRODUCTION_FLOOR)
    assert scenario.floor_for("harassment") == pytest.approx(PRODUCTION_FLOOR)


def test_a_sub_production_floor_is_refused_rather_than_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Below 0.01 the stored reports hold nothing, so no row may be printed.

    The stored findings were truncated at the production floor, so a row for
    0.005 would be byte-identical to the baseline and would read as the false
    conclusion "lowering the floor surfaces nothing new".
    """
    # ``--extract`` is passed explicitly for the same reason ``EXTRACT`` is
    # anchored above: ``main`` loads the extract before it reaches the refusal,
    # so the script's cwd-relative default would make this a FileNotFoundError
    # rather than the exit code under test.
    assert main(["--extract", str(EXTRACT), "--floors", "0.005"]) == 2
    out = capsys.readouterr().out
    assert "Refusing to report floors below the production floor" in out
    assert "RS-CAL3" in out


@pytest.mark.parametrize(
    "argv",
    [
        # ``--extract`` is passed for the same reason as in the test above:
        # ``main`` loads the extract before it reaches the finiteness check, so
        # the cwd-relative default would raise FileNotFoundError from a
        # non-root working directory and the test would pass for the wrong
        # reason.
        ["--extract", str(EXTRACT), "--floors", "nan"],
        ["--extract", str(EXTRACT), "--floors", "inf"],
        # "=" form: argparse reads a bare "-inf" as an option, not a value.
        ["--extract", str(EXTRACT), "--floors=-inf"],
    ],
)
def test_a_non_finite_floor_is_rejected_rather_than_replayed(argv: list[str]) -> None:
    """A non-finite floor is refused, not silently reported as a huge win.

    argparse's ``type=float`` accepts these strings, and the below-production
    guard cannot catch nan or inf: every comparison with nan is False, so
    ``nan < PRODUCTION_FLOOR`` is False. Left unchecked, the scenario's own
    ``score >= floor`` is then False for every scored finding, the whole corpus
    drops out, and the table reports a near-total load reduction that is an
    IEEE-754 artifact rather than a measurement, which is the worst possible
    failure mode for a script whose only output is a percentage someone
    ratifies a safety floor from.
    """
    with pytest.raises(ValidationError, match="finite"):
        main(argv)


def test_the_extract_holds_nothing_below_the_production_floor(
    books: list[dict[str, object]],
) -> None:
    """The truncation the refusal above depends on is real in the data."""
    scores = [
        score
        for b in books
        for f in _records(b["findings"], label="findings")
        for score in [f.get("score")]
        if isinstance(score, (int, float))
    ]
    assert scores
    assert min(scores) >= PRODUCTION_FLOOR


def test_the_replay_totals_reconcile_with_the_extracts_own_counts(
    books: list[dict[str, object]],
) -> None:
    """Summing the bands reproduces the counts recorded at extract time."""
    payload = load_extract(EXTRACT)
    counts = payload["counts"]
    assert isinstance(counts, dict)
    totals = evaluate(books, Scenario(name="prod"))
    assert sum(t.books for t in totals.values()) == counts["books"]
    assert sum(t.findings for t in totals.values()) == counts["findings"]
    assert sum(t.nodes for t in totals.values()) == counts["nodes"]
    assert (
        sum(t.occurrences for t in totals.values())
        == counts["finding_node_occurrences"]
    )


def test_all_six_age_bands_are_represented(books: list[dict[str, object]]) -> None:
    """A per-band conclusion needs every band present."""
    totals = evaluate(books, Scenario(name="prod"))
    assert set(totals) == set(BAND_ORDER)


def test_the_ratified_split_barely_moves_the_two_heaviest_bands(
    books: list[dict[str, object]],
) -> None:
    """The ratified per-category floor is not the lever for reviewer load.

    On the fixture corpus the 0.10 violence floor looked like a 63% noise cut.
    In production the wide merged violence advisories score 0.33 to 0.45, so a
    0.10 floor passes essentially all of them: under 1% removed in the two bands
    carrying most of the load. Pinned because the fixture figure is the one
    `UW-C378` published, and reading it as a production estimate would ratify a
    floor that does nothing.
    """
    baseline = evaluate(books, Scenario(name="prod"))
    ratified = evaluate(
        books, Scenario(name="ratified", per_category={"violence": 0.10})
    )
    for band in ("13-16", "16+"):
        removed = baseline[band].occurrences - ratified[band].occurrences
        assert removed / baseline[band].occurrences < 0.01, band


def test_the_low_advisory_collapse_removes_most_of_the_load(
    books: list[dict[str, object]],
) -> None:
    """The shipped `RS-A` change dominates every floor candidate.

    Owner ruling 2026-08-31 took low advisories out of the default detail view.
    Measured against production, that removes over 95% of surfaced occurrences
    in every band, which is two orders of magnitude more than the ratified floor
    achieves. Pinned so the calibration work is not mistaken for the fix.
    """
    baseline = evaluate(books, Scenario(name="prod"))
    collapsed = evaluate(books, Scenario(name="rs-a", drop_low_advisory=True))
    for band in BAND_ORDER:
        removed = baseline[band].occurrences - collapsed[band].occurrences
        assert removed / baseline[band].occurrences > 0.95, band


def test_more_than_a_third_of_nodes_carry_a_finding_in_the_older_bands(
    books: list[dict[str, object]],
) -> None:
    """The load being measured is real, not an artifact of a small corpus."""
    totals = evaluate(books, Scenario(name="prod"))
    assert totals["13-16"].node_hit_rate > 0.5
    assert totals["16+"].node_hit_rate > 0.4
    assert totals["8-11"].node_hit_rate > 0.3


def test_the_table_renders_one_row_per_scenario_band_pair(
    books: list[dict[str, object]],
) -> None:
    """Rendering covers header, separator, and every populated band."""
    baseline = evaluate(books, Scenario(name="prod"))
    other = evaluate(books, Scenario(name="flat 0.1", default=0.10))
    table = render_markdown(
        [(Scenario(name="prod"), baseline), (Scenario(name="flat 0.1"), other)],
        baseline=baseline,
    )
    lines = table.splitlines()
    assert len(lines) == 2 + 2 * len(BAND_ORDER)
    assert lines[0].startswith("| Scenario | Band |")
    assert "baseline" in lines[2]


def test_the_extract_carries_no_story_text_or_identifiers(
    books: list[dict[str, object]],
) -> None:
    """The committed extract is findings metadata only.

    It ships in the repo, so the absence of prose, titles, and family or profile
    identifiers is a property worth enforcing rather than trusting.
    """
    allowed = {
        "source",
        "category",
        "verdict",
        "severity",
        "score",
        "structural",
        "stage",
        "node_ixs",
    }
    for book in books:
        assert set(book) <= {
            "book_ix",
            "age_band",
            "node_count",
            "findings",
            "distinct_nodes_with_findings",
        }
        for finding in _records(book["findings"], label="findings"):
            assert set(finding) <= allowed
    blob = json.dumps(books)
    for banned in ("storybook_id", "family_id", "profile_id", "title", "message"):
        assert banned not in blob
