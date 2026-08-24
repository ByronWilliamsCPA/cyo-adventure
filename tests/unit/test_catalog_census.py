"""Tests for the skeleton catalog census (`AL-551`, `AL-554`, `UW-G24`)."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

import scripts.catalog_census as catalog_census
from cyo_adventure.generation.skeleton import is_sidecar
from cyo_adventure.validator.band_profile import offered_cells
from scripts.catalog_census import (
    GENERATED_DOC,
    Shell,
    _band_rank,
    _doc_path,
    census,
    load_shells,
    main,
    render,
)

# Anchored to the repository rather than the process working directory, so a
# run from a subdirectory fails visibly instead of globbing nothing and passing.
CATALOG_ROOT = Path(__file__).resolve().parents[2] / "skeletons"


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
    paths = {s.path for s in load_shells(CATALOG_ROOT)}
    all_json = set(CATALOG_ROOT.rglob("*.json"))
    # Use the shared predicate rather than a dot-count heuristic: counting dots
    # classifies any multi-dot slug as a sidecar, so the test would agree with a
    # broken implementation for the wrong reason.
    sidecars = {p for p in all_json if is_sidecar(p)}
    assert sidecars, "expected the catalog to contain sidecars to exclude"
    assert not (paths & sidecars)
    assert paths == all_json - sidecars


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


def test_the_two_eligibility_counts_are_distinct_and_ordered(
    data: dict[str, object],
) -> None:
    """Declaring the flag and being reachable in an offered cell differ.

    Both were previously reported under one "production-eligible shells"
    label, so a document quoting that row transcribed a number that measured
    something else (`UW-G24`).
    """
    cells = data["cells"]
    declared = cells["declared_production_eligible"]
    reachable = cells["reachable_in_offered_cells"]
    assert reachable <= declared <= data["totals"]["shells"]


def test_node_and_word_maxima_are_reported_separately(
    data: dict[str, object],
) -> None:
    """The largest graph by nodes need not be the largest by words.

    Conflating the two is how a 677-node graph acquired a word count it never
    had (`AL-551`).
    """
    largest = data["largest"]
    # Compare against an independent computation. The ordering assertions alone
    # also pass when both entries are the SAME shell, so a conflated maximum
    # would go undetected by them.
    shells = load_shells(CATALOG_ROOT)
    expected_nodes = max(shells, key=lambda s: s.nodes)
    expected_words = max(shells, key=lambda s: s.commissioned_words)

    assert largest["by_nodes"]["nodes"] == expected_nodes.nodes
    assert (
        largest["by_nodes"]["commissioned_words"] == expected_nodes.commissioned_words
    )
    assert largest["by_commissioned_words"]["nodes"] == expected_words.nodes
    assert (
        largest["by_commissioned_words"]["commissioned_words"]
        == expected_words.commissioned_words
    )
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
    assert GENERATED_DOC.read_text(encoding="utf-8") == render(census())


def test_a_document_path_is_forward_slashed_on_every_platform() -> None:
    """The census names a repository location, not a host filesystem location.

    `str(path)` renders the host separator, so a census generated on Windows
    disagreed with the committed document generated on Linux and
    `test_generated_doc_is_current` failed there and only there. That is a
    Windows-only red on a check that no per-PR job runs, so the guard has to be
    one every platform can fail: a Windows path is asserted here directly
    rather than waiting for a Windows runner to produce one.
    """
    windows = PureWindowsPath("skeletons") / "16+" / "the-tenfold-siege.json"
    assert _doc_path(windows) == "skeletons/16+/the-tenfold-siege.json"
    posix = PurePosixPath("skeletons/16+/the-tenfold-siege.json")
    assert _doc_path(posix) == "skeletons/16+/the-tenfold-siege.json"
    assert _doc_path(windows) == _doc_path(posix)


def test_the_generated_doc_carries_no_host_separator(data: dict[str, object]) -> None:
    """No path anywhere in the rendered census may carry a backslash."""
    largest = data["largest"]
    assert isinstance(largest, dict)
    for superlative in ("by_nodes", "by_commissioned_words"):
        entry: object = largest[superlative]
        assert isinstance(entry, dict)
        path: object = entry["path"]
        assert isinstance(path, str)
        assert "\\" not in path
        assert path.startswith("skeletons/")
    body = render(data)
    paths = [line for line in body.splitlines() if "`skeletons" in line]
    assert paths, "expected the largest-graph table to cite skeleton paths"
    assert not [line for line in paths if "\\" in line]


def test_a_windows_catalog_path_is_forward_slashed_before_it_reaches_the_doc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The forward-slashing has to happen in `census`, not on the host.

    `test_the_generated_doc_carries_no_host_separator` reads the real catalog,
    so on a Linux runner `PosixPath.__str__` emits no backslash whether or not
    `_doc_path` normalises anything: that test passes with the fix reverted and
    can only ever fail on the Windows job, which is the job that let the defect
    reach `main` in the first place. Feeding `census` a Windows-pathed shell
    makes the same regression fail on every platform, which is the whole point
    of catching it in a unit test rather than in CI.
    """
    windows_shell = Shell(
        path=PureWindowsPath("skeletons") / "16+" / "the-tenfold-siege.json",
        band="16+",
        nodes=999_999,
        commissioned_words=999_999,
        production_eligible=True,
    )
    monkeypatch.setattr(catalog_census, "load_shells", lambda: [windows_shell])

    data = census()

    largest = data["largest"]
    assert isinstance(largest, dict)
    for superlative in ("by_nodes", "by_commissioned_words"):
        entry: object = largest[superlative]
        assert isinstance(entry, dict)
        assert entry["path"] == "skeletons/16+/the-tenfold-siege.json"
    assert "\\" not in render(data)


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


def test_check_and_write_cannot_be_combined() -> None:
    """Asking for a check must never perform a write.

    `--write` was evaluated before `--check`, so `--check --write` rewrote the
    tracked document and exited 0, turning a verification into an unreviewed
    edit.
    """
    with pytest.raises(SystemExit) as exc:
        main(["--check", "--write"])
    assert exc.value.code == 2


def test_missing_doc_is_reported_as_missing_not_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A doc that was never generated is a different fault from a stale one."""
    absent = tmp_path / "never-generated.md"
    monkeypatch.setattr("scripts.catalog_census.GENERATED_DOC", absent)
    assert main(["--check"]) == 1
    assert "missing" in capsys.readouterr().err


def test_a_shell_without_nodes_is_rejected(tmp_path: Path) -> None:
    """A malformed shell fails loudly rather than shrinking every total.

    Silently skipping it would undercount the catalog, which is precisely the
    drift this census exists to detect (`UW-G24`).
    """
    (tmp_path / "broken.json").write_text('{"title": "no nodes"}', encoding="utf-8")
    with pytest.raises(ValueError, match=r"broken\.json"):
        load_shells(tmp_path)


def test_a_non_object_json_root_is_rejected(tmp_path: Path) -> None:
    """A shell whose JSON root is not an object fails the same way.

    `json.loads` happily returns a list or a string, and the old code reached
    `.get()` on it, so one malformed shape raised the documented actionable
    error and another raised a bare `AttributeError`.
    """
    (tmp_path / "listy.json").write_text('["not", "a", "shell"]', encoding="utf-8")
    with pytest.raises(ValueError, match=r"listy\.json .*list at its JSON root"):
        load_shells(tmp_path)


def test_census_refuses_to_run_outside_the_repository_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The working-directory precondition is the guard, so pin it.

    Review proposed a fixture that chdirs to the repository root for every
    test that calls `census()`. That would make the suite green in a working
    directory where the CLI itself refuses to run, which hides the guard
    rather than proving it. Assert the refusal instead, and name
    `skeleton_match` so the message keeps explaining why half an anchor is
    worse than none.
    """
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="skeleton_match"):
        census()


def test_an_unknown_band_directory_is_named() -> None:
    """A stray directory names itself instead of raising a bare KeyError."""
    with pytest.raises(ValueError, match="not an age band"):
        _band_rank("not-a-band")
