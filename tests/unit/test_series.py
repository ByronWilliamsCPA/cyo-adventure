"""Unit tests for the cross-book series meta-validator (SR-1..SR-7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.storybook.models import (
    AgeBand,
    Choice,
    Ending,
    EndingKind,
    Node,
    ReadingLevel,
    Series,
    Storybook,
    StoryMetadata,
    Topology,
    Valence,
    Variable,
    VariableType,
)
from cyo_adventure.validator.report import Severity
from cyo_adventure.validator.series import validate_series


def _book(
    *,
    book_index: int,
    series_id: str = "camp",
    entry: str | None = None,
    is_final: bool = False,
    carries_state: bool = True,
    age_band: AgeBand = AgeBand.BAND_10_13,
    tier: int = 2,
    win: bool = True,
    with_series: bool = True,
) -> Storybook:
    """Build a minimal valid book, optionally tagged into a series.

    ``win`` controls whether the book has a successful-completion ending (a
    campaign can continue from it) or only a fail-fast setback.
    """
    kind = EndingKind.SUCCESS if win else EndingKind.SETBACK
    valence = Valence.POSITIVE if win else Valence.NEGATIVE
    end = Node(
        id="n_win",
        body="done",
        is_ending=True,
        ending=Ending(id="e1", valence=valence, kind=kind, title="End"),
    )
    start = Node(
        id="n0",
        body="go",
        choices=[Choice(id="c1", label="x", target="n_win")],
    )
    series = (
        Series(
            series_id=series_id,
            book_index=book_index,
            series_entry_node=entry,
            is_final=is_final,
            carries_state=carries_state,
        )
        if with_series
        else None
    )
    return Storybook(
        id=f"book{book_index}",
        version=1,
        title="T",
        start_node="n0",
        nodes=[start, end],
        metadata=StoryMetadata(
            age_band=age_band,
            reading_level=ReadingLevel(target=2.0),
            tier=tier,
            estimated_minutes=5,
            ending_count=1,
            topology=Topology.GAUNTLET,
            series=series,
        ),
    )


def _valid_two_book_chain() -> list[Storybook]:
    """A clean two-book chain that satisfies every SR-* rule."""
    return [
        _book(book_index=1, is_final=False, win=True),
        _book(book_index=2, entry="n0", is_final=True, win=True),
    ]


def test_valid_chain_has_no_findings():
    report = validate_series(_valid_two_book_chain())
    assert report.ok
    assert report.findings == []


def test_empty_chain_is_ok():
    report = validate_series([])
    assert report.ok
    assert report.findings == []


def test_missing_series_metadata_is_sr1():
    books = [_book(book_index=1, with_series=False)]
    report = validate_series(books)
    assert any(f.rule_id == "SR-1" for f in report.errors)


def test_mixed_series_ids_is_sr1():
    books = [
        _book(book_index=1, series_id="a", is_final=False),
        _book(book_index=2, series_id="b", entry="n0", is_final=True),
    ]
    report = validate_series(books)
    assert any(f.rule_id == "SR-1" for f in report.errors)


def test_non_contiguous_indices_is_sr2():
    books = [
        _book(book_index=1, is_final=False),
        _book(book_index=3, entry="n0", is_final=True),
    ]
    report = validate_series(books)
    assert any(f.rule_id == "SR-2" for f in report.errors)


def test_entry_node_must_exist_is_sr3():
    books = [
        _book(book_index=1, is_final=False),
        _book(book_index=2, entry="ghost", is_final=True),
    ]
    report = validate_series(books)
    assert any(f.rule_id == "SR-3" and f.node_id == "ghost" for f in report.errors)


def test_continued_book_without_entry_is_sr3():
    books = [
        _book(book_index=1, is_final=False),
        _book(book_index=2, entry=None, is_final=True),
    ]
    report = validate_series(books)
    assert any(f.rule_id == "SR-3" for f in report.errors)


def test_wrong_final_flag_is_sr4():
    # book 1 is wrongly marked final in a two-book chain.
    books = [
        _book(book_index=1, is_final=True),
        _book(book_index=2, entry="n0", is_final=True),
    ]
    report = validate_series(books)
    assert any(f.rule_id == "SR-4" for f in report.errors)


def test_open_chain_all_not_final_is_valid():
    # WS-G G4: an open-ended chain (no book marked final) is a first-class
    # state; only a NON-top book marked final is an SR-4 error.
    books = [
        _book(book_index=1),
        _book(book_index=2, entry="n0"),
    ]
    report = validate_series(books)
    assert not any(f.rule_id == "SR-4" for f in report.errors)


def test_closed_chain_top_final_is_valid():
    books = [
        _book(book_index=1),
        _book(book_index=2, entry="n0", is_final=True),
    ]
    report = validate_series(books)
    assert not any(f.rule_id == "SR-4" for f in report.errors)


def test_middle_book_final_in_three_book_chain_is_sr4():
    # A 3-book chain: the middle book (index 2 of 3) marked is_final is an
    # SR-4 error, since it is not the top of the chain.
    books = [
        _book(book_index=1),
        _book(book_index=2, entry="n0", is_final=True),
        _book(book_index=3, entry="n0"),
    ]
    report = validate_series(books)
    assert any(f.rule_id == "SR-4" for f in report.errors)


def test_top_book_in_three_book_chain_either_final_flag_is_valid():
    # The top book (index 3 of 3) may be marked final (closed series) or not
    # (open-ended chain); neither triggers SR-4.
    for top_final in (True, False):
        books = [
            _book(book_index=1),
            _book(book_index=2, entry="n0"),
            _book(book_index=3, entry="n0", is_final=top_final),
        ]
        report = validate_series(books)
        assert not any(f.rule_id == "SR-4" for f in report.errors)


def test_non_final_book_without_win_is_sr5():
    books = [
        _book(book_index=1, is_final=False, win=False),  # only a setback ending
        _book(book_index=2, entry="n0", is_final=True, win=True),
    ]
    report = validate_series(books)
    assert any(f.rule_id == "SR-5" for f in report.errors)


def test_young_band_must_be_episodic_is_sr6():
    # A single 5-8 book that carries state violates the episodic rule.
    books = [
        _book(
            book_index=1,
            is_final=True,
            carries_state=True,
            age_band=AgeBand.BAND_5_8,
        )
    ]
    report = validate_series(books)
    assert any(f.rule_id == "SR-6" for f in report.errors)


def test_tier1_book_must_be_episodic_is_sr6():
    books = [_book(book_index=1, is_final=True, carries_state=True, tier=1)]
    report = validate_series(books)
    assert any(f.rule_id == "SR-6" for f in report.errors)


def test_mixed_state_carry_is_sr7():
    books = [
        _book(book_index=1, is_final=False, carries_state=True),
        _book(book_index=2, entry="n0", is_final=True, carries_state=False),
    ]
    report = validate_series(books)
    assert any(f.rule_id == "SR-7" for f in report.errors)


def test_episodic_young_chain_passes():
    # A young-band episodic chain (no state carry) is valid.
    books = [
        _book(
            book_index=1,
            is_final=False,
            carries_state=False,
            age_band=AgeBand.BAND_5_8,
        ),
        _book(
            book_index=2,
            entry="n0",
            is_final=True,
            carries_state=False,
            age_band=AgeBand.BAND_5_8,
        ),
    ]
    report = validate_series(books)
    assert report.ok


# ---------------------------------------------------------------------------
# The real three-book chain as a fixture (AL-048)
# ---------------------------------------------------------------------------
#
# Every case above builds a synthetic 2-node book, a shape no author would ever
# write. The wyrmreach trilogy is the repo's first real state-carrying chain, and
# validating it costs ~0.02s because the meta-validator does not walk the state
# space, so there is no reason for SR-1..SR-7 to be proven only on toys.

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_WYRMREACH = (
    "the-vault-of-nine-iron.filled.json",
    "the-sunless-march.filled.json",
    "the-ninth-hand.filled.json",
)


def _load_wyrmreach() -> list[Storybook]:
    """Return the three real filled books, skipping if the corpus is absent."""
    books: list[Storybook] = []
    for name in _WYRMREACH:
        path = _REPO_ROOT / "out" / name
        if not path.is_file():
            pytest.skip(f"{name} not present")
        books.append(Storybook.model_validate(json.loads(path.read_text())))
    return books


@pytest.mark.unit
def test_real_three_book_chain_validates() -> None:
    """The committed wyrmreach trilogy passes every SR rule."""
    report = validate_series(_load_wyrmreach())
    assert report.ok, [f.message for f in report.findings]


@pytest.mark.unit
def test_real_chain_with_a_missing_middle_book_fails_contiguity() -> None:
    """SR-2 must catch a gap in a real chain, not just a synthetic one."""
    books = _load_wyrmreach()
    report = validate_series([books[0], books[2]])
    assert not report.ok
    assert any("SR-2" in f.rule_id for f in report.findings)


@pytest.mark.unit
def test_real_chain_with_a_blank_entry_node_fails() -> None:
    """SR-3 must catch an unresolvable entry node on a real multi-ending book."""
    books = _load_wyrmreach()
    third = books[2].model_copy(deep=True)
    assert third.metadata.series is not None
    third.metadata.series.series_entry_node = "n_does_not_exist"
    report = validate_series([books[0], books[1], third])
    assert not report.ok
    assert any("SR-3" in f.rule_id for f in report.findings)


@pytest.mark.unit
def test_real_chain_with_inconsistent_carry_flag_fails() -> None:
    """SR-7 must catch a chain that disagrees with itself about carrying state."""
    books = _load_wyrmreach()
    first = books[0].model_copy(deep=True)
    assert first.metadata.series is not None
    first.metadata.series.carries_state = False
    report = validate_series([first, books[1], books[2]])
    assert not report.ok
    assert any("SR-7" in f.rule_id for f in report.findings)


# ---------------------------------------------------------------------------
# SR-8 carried-variable integrity (AL-038)
# ---------------------------------------------------------------------------


def _carry_book(
    *, book_index: int, variables: list[Variable], is_final: bool = False
) -> Storybook:
    """A minimal state-carrying series book with an explicit variable set.

    Books above index 1 declare an entry node so SR-3/SR-5 are satisfied and SR-8
    is the only rule under test.
    """
    book = _book(
        book_index=book_index,
        is_final=is_final,
        carries_state=True,
        entry="n_win" if book_index > 1 else None,
    )
    return book.model_copy(update={"variables": variables})


def _int_var(name: str, low: int, high: int) -> Variable:
    return Variable(name=name, type=VariableType.INT, initial=low, min=low, max=high)


@pytest.mark.unit
def test_sr8_errors_when_a_receiving_range_narrows_the_senders() -> None:
    """A narrowed carried range is silent data loss, so it blocks.

    This is the defect that shipped in the real chain: the client clamps carried
    ints into the receiving book's bounds, turning every low value into the floor.
    """
    books = [
        _carry_book(book_index=1, variables=[_int_var("renown", 0, 5)]),
        _carry_book(book_index=2, variables=[_int_var("renown", 3, 5)]),
    ]
    report = validate_series(books)
    sr8 = [f for f in report.findings if f.rule_id == "SR-8"]
    assert len(sr8) == 1
    assert sr8[0].severity is Severity.ERROR
    assert "must contain the sending range" in sr8[0].message
    assert not report.ok, "an SR-8 range error must block the chain"


@pytest.mark.unit
def test_sr8_accepts_a_receiving_range_that_contains_the_senders() -> None:
    """Widening, or matching, is fine."""
    books = [
        _carry_book(book_index=1, variables=[_int_var("renown", 0, 3)]),
        _carry_book(book_index=2, variables=[_int_var("renown", 0, 5)]),
    ]
    assert not [f for f in validate_series(books).findings if f.rule_id == "SR-8"]


@pytest.mark.unit
def test_sr8_warns_when_a_carried_variable_is_dropped() -> None:
    """A dropped variable is sometimes deliberate, so it warns rather than blocks."""
    books = [
        _carry_book(
            book_index=1,
            variables=[_int_var("renown", 0, 5), _int_var("charts", 0, 1)],
        ),
        _carry_book(book_index=2, variables=[_int_var("renown", 0, 5)]),
    ]
    report = validate_series(books)
    sr8 = [f for f in report.findings if f.rule_id == "SR-8"]
    assert len(sr8) == 1
    assert sr8[0].severity is Severity.WARNING
    assert "'charts'" in sr8[0].message
    assert report.ok, "a dropped variable must not block the chain"


@pytest.mark.unit
def test_sr8_is_silent_on_an_episodic_chain() -> None:
    """A chain that carries nothing cannot lose carried state."""
    books = [
        _book(book_index=1, carries_state=False),
        _book(book_index=2, carries_state=False),
    ]
    assert not [f for f in validate_series(books).findings if f.rule_id == "SR-8"]
