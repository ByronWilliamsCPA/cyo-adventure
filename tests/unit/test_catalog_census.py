"""Tests for the skeleton catalog census (`AL-551`, `AL-554`, `UW-G24`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.validator.band_profile import offered_cells
from scripts.catalog_census import GENERATED_DOC, census, load_shells, main, render


@pytest.fixture(scope="module")
def data() -> dict[str, object]:
    """Return the real catalog census, computed once for the module."""
    return census()


def test_sidecars_are_not_counted_as_shells() -> None:
    """A `.contract.json`/`.lineage.json`/`.narrative.json` is not a shell.

    This is the defect that produced the first wrong recount: excluding only
    two of the three sidecar suffixes left a `.narrative.json` counted as a
    skeleton with zero commissioned words.
    """
    paths = {s.path for s in load_shells()}
    sidecars = [
        p
        for p in Path("skeletons").rglob("*.json")
        if p.name.count(".") > 1  # <slug>.<kind>.json
    ]
    assert sidecars, "expected the catalog to contain sidecars to exclude"
    assert not (paths & set(sidecars))


def test_every_shell_reports_nodes_and_words(data: dict[str, object]) -> None:
    """Totals are positive and per-band rows sum to them."""
    totals = data["totals"]
    bands = data["bands"]
    assert totals["shells"] == sum(b["shells"] for b in bands)
    assert totals["nodes"] == sum(b["nodes"] for b in bands)
    assert totals["commissioned_words"] == sum(b["commissioned_words"] for b in bands)
    assert totals["nodes"] > 0


def test_bands_are_ordered_by_reading_age(data: dict[str, object]) -> None:
    """Bands sort by age, not lexicographically ("10-13" after "8-11")."""
    assert [b["band"] for b in data["bands"]] == [
        "3-5",
        "5-8",
        "8-11",
        "10-13",
        "13-16",
        "16+",
    ]


def test_coverage_is_reported_against_the_offered_grid(
    data: dict[str, object],
) -> None:
    """The grid is `offered_cells()`, not a cross-product of the enums.

    Three analyses invented a grid here and each manufactured empty cells that
    no request can reach, because a 3-5 long and an 8-11 gamebook are not
    sold (`AL-554`). Guard the total against the real source.
    """
    cells = data["cells"]
    assert cells["offered"] == len(offered_cells())
    assert cells["covered"] + cells["uncovered"] == cells["offered"]


def test_no_offered_cell_is_uncovered(data: dict[str, object]) -> None:
    """Every cell ADR-011 sells has at least one production-eligible skeleton.

    If this fails the catalog has a real gap: a request shape the matrix
    offers that the selector cannot fill.
    """
    assert data["cells"]["uncovered"] == 0


def test_production_eligible_is_a_subset_of_all_shells(
    data: dict[str, object],
) -> None:
    """Eligibility only ever removes shells."""
    assert data["cells"]["production_eligible_shells"] <= data["totals"]["shells"]


def test_node_and_word_maxima_are_reported_separately(
    data: dict[str, object],
) -> None:
    """The largest graph by nodes need not be the largest by words.

    Conflating the two is how a 677-node graph acquired a word count it never
    had (`AL-551`).
    """
    largest = data["largest"]
    assert largest["by_nodes"]["nodes"] >= largest["by_commissioned_words"]["nodes"]
    assert (
        largest["by_commissioned_words"]["commissioned_words"]
        >= largest["by_nodes"]["commissioned_words"]
    )


def test_generated_doc_is_current() -> None:
    """The committed census doc matches the catalog.

    This is the anti-decay mechanism: a skeleton added without regenerating
    fails here rather than silently contradicting the prose that cites it.
    """
    assert GENERATED_DOC.read_text() == render(census())


def test_check_mode_detects_a_stale_doc(tmp_path: Path, monkeypatch) -> None:
    """`--check` exits non-zero when the doc does not match."""
    stale = tmp_path / "census.md"
    stale.write_text("# Skeleton catalog census\n\nstale\n")
    monkeypatch.setattr("scripts.catalog_census.GENERATED_DOC", stale)
    assert main(["--check"]) == 1


def test_json_mode_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    """`--json` emits parseable JSON carrying the totals."""
    assert main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["totals"]["shells"] > 0
