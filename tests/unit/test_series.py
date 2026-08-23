"""Unit tests for the cross-book series meta-validator (SR-1..SR-7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.diversity.grams import shared_run_profile
from cyo_adventure.diversity.normalize import storybook_text
from cyo_adventure.storybook.models import (
    AgeBand,
    Choice,
    Effect,
    EffectOp,
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
from cyo_adventure.storybook.sentinels import find_sentinels
from cyo_adventure.validator.report import Severity, ValidationReport
from cyo_adventure.validator.series import (
    SERIES_MAX_SHARED_RUN_COVERAGE,
    SERIES_MAX_SHARED_RUN_WORDS,
    validate_series,
)


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
# SR-9: the continuation handoff (B3)
# ---------------------------------------------------------------------------


def _sr9_ids(report: ValidationReport) -> list[str]:
    """Return the messages of every SR-9 finding, ignoring other rules."""
    return [f.message for f in report.findings if f.rule_id == "SR-9"]


def _stateful_book(
    *,
    book_index: int,
    nodes: list[Node],
    variables: list[Variable],
    entry: str | None = None,
    is_final: bool = False,
    carries_state: bool = True,
    ending_count: int = 1,
) -> Storybook:
    """Build a Tier-2 series book with declared variables."""
    return Storybook(
        id=f"book{book_index}",
        version=1,
        title="T",
        start_node="n0",
        nodes=nodes,
        variables=variables,
        metadata=StoryMetadata(
            age_band=AgeBand.BAND_10_13,
            reading_level=ReadingLevel(target=2.0),
            tier=2,
            estimated_minutes=5,
            ending_count=ending_count,
            topology=Topology.GAUNTLET,
            series=Series(
                series_id="camp",
                book_index=book_index,
                series_entry_node=entry,
                is_final=is_final,
                carries_state=carries_state,
            ),
        ),
    )


def _sender_setting_lantern() -> Storybook:
    """Book 1: wins with ``has_lantern`` true, the F3 acquisition shape."""
    return _stateful_book(
        book_index=1,
        variables=[Variable(name="has_lantern", type=VariableType.BOOL, initial=False)],
        nodes=[
            Node(
                id="n0",
                body="go",
                on_enter=[Effect(op=EffectOp.SET, var="has_lantern", value=True)],
                choices=[Choice(id="c1", label="x", target="n_win")],
            ),
            Node(
                id="n_win",
                body="done",
                is_ending=True,
                ending=Ending(
                    id="e1",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="W",
                ),
            ),
        ],
    )


def test_sr9_flags_a_dead_acquisition_branch_in_the_receiving_book() -> None:
    """The F3 shape: book 2 gifts what book 1 already gave.

    Book 2 carries a "gift it if missing" branch conditioned on
    ``has_lantern == false``. Book 1 always exits with it true, so that branch is
    unsatisfiable for every real continuation reader and Layer 2 raises L2-11 --
    but only when entered with the carried state, which no other rule does.
    Escalates series-stress-test-findings.md F3 from authoring guidance to a
    gate-detectable defect.
    """
    receiver = _stateful_book(
        book_index=2,
        entry="n0",
        is_final=True,
        variables=[Variable(name="has_lantern", type=VariableType.BOOL, initial=False)],
        nodes=[
            Node(
                id="n0",
                body="go",
                choices=[
                    Choice(
                        id="c_gift",
                        label="take the spare lantern",
                        target="n_win",
                        condition={"==": [{"var": "has_lantern"}, False]},
                    ),
                    Choice(id="c_on", label="press on", target="n_win"),
                ],
            ),
            Node(
                id="n_win",
                body="done",
                is_ending=True,
                ending=Ending(
                    id="e2",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="W",
                ),
            ),
        ],
    )
    findings = _sr9_ids(validate_series([_sender_setting_lantern(), receiver]))
    assert len(findings) == 1
    assert "L2-11" in findings[0]
    assert "has_lantern" in findings[0]


def test_sr9_passes_when_the_receiving_gate_expects_the_carried_value() -> None:
    """The correct redesign: gate on the carried value being true."""
    receiver = _stateful_book(
        book_index=2,
        entry="n0",
        is_final=True,
        variables=[Variable(name="has_lantern", type=VariableType.BOOL, initial=False)],
        nodes=[
            Node(
                id="n0",
                body="go",
                choices=[
                    Choice(
                        id="c_use",
                        label="raise the lantern",
                        target="n_win",
                        condition={"==": [{"var": "has_lantern"}, True]},
                    ),
                    Choice(id="c_on", label="press on", target="n_win"),
                ],
            ),
            Node(
                id="n_win",
                body="done",
                is_ending=True,
                ending=Ending(
                    id="e2",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="W",
                ),
            ),
        ],
    )
    assert _sr9_ids(validate_series([_sender_setting_lantern(), receiver])) == []


def test_sr9_flags_a_continuation_that_cannot_be_won() -> None:
    """A win that leads into an unwinnable book.

    L2-10 cannot catch this: an ending IS reachable, just never a satisfying
    one, so book 2 passes Layer 2 cleanly while being impossible to win from the
    only state a real reader can arrive in.
    """
    receiver = _stateful_book(
        book_index=2,
        entry="n0",
        is_final=True,
        ending_count=2,
        variables=[Variable(name="has_sigil", type=VariableType.BOOL, initial=False)],
        nodes=[
            Node(
                id="n0",
                body="go",
                choices=[
                    Choice(
                        id="c_win",
                        label="open the seal",
                        target="n_win",
                        condition={"==": [{"var": "has_sigil"}, True]},
                    ),
                    Choice(id="c_lose", label="turn back", target="n_lose"),
                ],
            ),
            Node(
                id="n_win",
                body="done",
                is_ending=True,
                ending=Ending(
                    id="e2",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="W",
                ),
            ),
            Node(
                id="n_lose",
                body="alas",
                is_ending=True,
                ending=Ending(
                    id="e3",
                    valence=Valence.NEGATIVE,
                    kind=EndingKind.SETBACK,
                    title="L",
                ),
            ),
        ],
    )
    # The sender never grants has_sigil, so the winning branch is never visible.
    findings = _sr9_ids(validate_series([_sender_setting_lantern(), receiver]))
    assert any("no satisfying ending reachable" in message for message in findings)


def test_sr9_does_not_run_on_an_episodic_chain() -> None:
    """No state crosses an episodic join, so there is nothing to check."""
    sender = _sender_setting_lantern()
    sender.metadata.series = Series(
        series_id="camp",
        book_index=1,
        series_entry_node=None,
        is_final=False,
        carries_state=False,
    )
    receiver = _stateful_book(
        book_index=2,
        entry="n0",
        is_final=True,
        carries_state=False,
        variables=[Variable(name="has_lantern", type=VariableType.BOOL, initial=False)],
        nodes=[
            Node(
                id="n0",
                body="go",
                choices=[
                    Choice(
                        id="c_gift",
                        label="take the spare",
                        target="n_win",
                        condition={"==": [{"var": "has_lantern"}, False]},
                    ),
                    Choice(id="c_on", label="press on", target="n_win"),
                ],
            ),
            Node(
                id="n_win",
                body="done",
                is_ending=True,
                ending=Ending(
                    id="e2",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="W",
                ),
            ),
        ],
    )
    assert _sr9_ids(validate_series([sender, receiver])) == []


def test_sr9_reports_only_the_delta_not_the_receiving_books_own_defects() -> None:
    """A defect the receiving book already has under its own gate is not SR-9's.

    Book 2 here has a branch that is dead from its own declared initials too, so
    its single-story gate already reports it. SR-9 must stay silent rather than
    duplicating that as a cross-book failure.
    """
    receiver = _stateful_book(
        book_index=2,
        entry="n0",
        is_final=True,
        variables=[
            Variable(name="has_lantern", type=VariableType.BOOL, initial=False),
            Variable(name="never_set", type=VariableType.BOOL, initial=False),
        ],
        nodes=[
            Node(
                id="n0",
                body="go",
                choices=[
                    Choice(
                        id="c_dead",
                        label="use the thing nobody has",
                        target="n_win",
                        condition={"==": [{"var": "never_set"}, True]},
                    ),
                    Choice(id="c_on", label="press on", target="n_win"),
                ],
            ),
            Node(
                id="n_win",
                body="done",
                is_ending=True,
                ending=Ending(
                    id="e2",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="W",
                ),
            ),
        ],
    )
    report = validate_series([_sender_setting_lantern(), receiver])
    assert _sr9_ids(report) == []


def test_sr9_flags_the_b5_direction_a_win_that_does_not_grant_the_gate() -> None:
    """B5's exact case: book 1 can be won without earning what book 2 needs.

    ``series-stress-test-findings.md`` F3 is usually described in the acquisition
    direction (book 1 always grants it, so book 2's if-missing branch dies). B5
    names the mirror: book 2 is correctly redesigned to gate on the carried value
    being true, but book 1's win endings are reachable **without** granting it,
    so a legitimate winner arrives with false and book 2's gated content is dead.
    Both directions are the same class of defect and SR-9 catches both, because
    it compares Layer-2 errors rather than looking for one shape.
    """
    sender = _stateful_book(
        book_index=1,
        ending_count=1,
        variables=[Variable(name="has_lantern", type=VariableType.BOOL, initial=False)],
        nodes=[
            # No effect sets has_lantern, so the win is reachable with it false.
            Node(
                id="n0",
                body="go",
                choices=[Choice(id="c1", label="x", target="n_win")],
            ),
            Node(
                id="n_win",
                body="done",
                is_ending=True,
                ending=Ending(
                    id="e1",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="W",
                ),
            ),
        ],
    )
    receiver = _stateful_book(
        book_index=2,
        entry="n0",
        is_final=True,
        variables=[Variable(name="has_lantern", type=VariableType.BOOL, initial=True)],
        nodes=[
            Node(
                id="n0",
                body="go",
                choices=[
                    Choice(
                        id="c_use",
                        label="raise the lantern",
                        target="n_win",
                        condition={"==": [{"var": "has_lantern"}, True]},
                    ),
                    Choice(id="c_on", label="press on", target="n_win"),
                ],
            ),
            Node(
                id="n_win",
                body="done",
                is_ending=True,
                ending=Ending(
                    id="e2",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="W",
                ),
            ),
        ],
    )
    findings = _sr9_ids(validate_series([sender, receiver]))
    assert len(findings) == 1
    assert "L2-11" in findings[0]


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
    """Return the three wyrmreach books, skipping if the corpus is absent.

    None of the three is currently committed, so every test using this helper skips
    and has never executed. They are kept because they run unchanged once the corpus
    lands. Deliberately a skip rather than a CI failure: the artifacts are absent on
    every checkout including CI, so failing would break the suite instead of revealing
    anything. Tracked by UW-F19 (weak-skip audit) and UW-F20 (corpus coverage).
    """
    books: list[Storybook] = []
    for name in _WYRMREACH:
        path = _REPO_ROOT / "out" / name
        if not path.is_file():
            pytest.skip(f"out/{name} is not committed; tracked by UW-F19 and UW-F20")
        books.append(
            Storybook.model_validate(json.loads(path.read_text(encoding="utf-8")))
        )
    return books


@pytest.mark.unit
def test_real_three_book_chain_validates() -> None:
    """The wyrmreach trilogy passes every SR rule, once it is committed.

    Skips today: the corpus is not in the tree. See _load_wyrmreach.
    """
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


# ---------------------------------------------------------------------------
# SR-9 must walk the node the reader enters (UW-C296)
# ---------------------------------------------------------------------------


def _sender_that_always_wins_without_the_key() -> Storybook:
    """A one-decision book whose only satisfying ending leaves `key` false."""
    return Storybook(
        id="s_send",
        version=1,
        title="Sender",
        start_node="a_start",
        nodes=[
            Node(
                id="a_start",
                body="A short road.",
                choices=[
                    Choice(id="a_c1", label="Walk on.", target="a_win"),
                    Choice(id="a_c2", label="Turn back.", target="a_lose"),
                ],
            ),
            Node(
                id="a_win",
                body="Arrived.",
                is_ending=True,
                ending=Ending(
                    id="a_e1",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="Arrived",
                ),
            ),
            Node(
                id="a_lose",
                body="Home again.",
                is_ending=True,
                ending=Ending(
                    id="a_e2",
                    valence=Valence.NEGATIVE,
                    kind=EndingKind.SETBACK,
                    title="Home",
                ),
            ),
        ],
        variables=[Variable(name="key", type=VariableType.BOOL, initial=False)],
        metadata=StoryMetadata(
            age_band=AgeBand.BAND_10_13,
            reading_level=ReadingLevel(target=5.5),
            tier=2,
            estimated_minutes=5,
            ending_count=2,
            topology=Topology.GAUNTLET,
            series=Series(
                series_id="entry", book_index=1, is_final=False, carries_state=True
            ),
        ),
    )


def _receiver_whose_prologue_grants_the_key(*, entry: str) -> Storybook:
    """A receiver whose only win needs `key`, granted solely by its prologue.

    ``b_open`` is the story's ``start_node`` and sets ``key`` on entry.
    ``b_gate`` is the declared ``series_entry_node``. A reader entering at
    ``b_gate`` never runs the prologue, so the win is unreachable for them; a
    walk seeded at ``b_open`` sees it as reachable. The two entries therefore
    give SR-9 opposite verdicts on one graph, which is what makes this a test of
    which node is walked rather than of the reachability logic.
    """
    return Storybook(
        id="s_recv",
        version=1,
        title="Receiver",
        start_node="b_open",
        nodes=[
            Node(
                id="b_open",
                body="The prologue, where the key is handed over.",
                on_enter=[Effect(op=EffectOp.SET, var="key", value=True)],
                choices=[Choice(id="b_c0", label="Go on.", target="b_gate")],
            ),
            Node(
                id="b_gate",
                body="The gate.",
                choices=[
                    Choice(
                        id="b_c1",
                        label="Unlock it.",
                        target="b_win",
                        condition={"var": "key"},
                    ),
                    Choice(id="b_c2", label="Give up.", target="b_lose"),
                ],
            ),
            Node(
                id="b_win",
                body="Through.",
                is_ending=True,
                ending=Ending(
                    id="b_e1",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="Through",
                ),
            ),
            Node(
                id="b_lose",
                body="Turned away.",
                is_ending=True,
                ending=Ending(
                    id="b_e2",
                    valence=Valence.NEGATIVE,
                    kind=EndingKind.SETBACK,
                    title="Turned away",
                ),
            ),
        ],
        variables=[Variable(name="key", type=VariableType.BOOL, initial=False)],
        metadata=StoryMetadata(
            age_band=AgeBand.BAND_10_13,
            reading_level=ReadingLevel(target=5.5),
            tier=2,
            estimated_minutes=5,
            ending_count=2,
            topology=Topology.GAUNTLET,
            series=Series(
                series_id="entry",
                book_index=2,
                series_entry_node=entry,
                is_final=True,
                carries_state=True,
            ),
        ),
    )


def test_sr9_walks_the_declared_series_entry_node() -> None:
    """A non-start entry must change SR-9's carried reachability.

    SR-9 seeded the receiver from ``start_node`` until `UW-C296`, justified by an
    assumption that a continuation's ``series_entry_node`` always equals its
    ``start_node``. Both committed brass-lantern books already broke that, and a
    receiver whose prologue grants what its win requires is the case where it
    stops being harmless: the reader enters past the prologue and can never win,
    while the old walk entered at the prologue and reported the chain sound.
    """
    sender = _sender_that_always_wins_without_the_key()
    report = validate_series(
        [sender, _receiver_whose_prologue_grants_the_key(entry="b_gate")]
    )
    sr9 = [f for f in report.errors if f.rule_id == "SR-9"]
    assert sr9, "entering past the prologue leaves no satisfying ending reachable"
    assert "b_gate" in str(report.findings) or "no satisfying" in sr9[0].message.lower()


def test_the_same_chain_is_sound_when_the_entry_is_the_start_node() -> None:
    """The control. Only the declared entry differs between the two books.

    Without this, the test above would pass for any reason that makes the
    receiver unwinnable, rather than because SR-9 now reads the entry node.
    """
    sender = _sender_that_always_wins_without_the_key()
    report = validate_series(
        [sender, _receiver_whose_prologue_grants_the_key(entry="b_open")]
    )
    assert [f for f in report.errors if f.rule_id == "SR-9"] == []


def test_an_entry_node_absent_from_the_story_falls_back_to_the_start_node() -> None:
    """Mirrors the client's existence guard rather than trusting the declaration.

    ``frontend/src/player/engine.ts`` starts at ``story.start_node`` when the
    declared entry names no node, so a stale or misspelled entry degrades the
    same way on both sides instead of diverging.
    """
    sender = _sender_that_always_wins_without_the_key()
    report = validate_series(
        [sender, _receiver_whose_prologue_grants_the_key(entry="b_nonexistent")]
    )
    assert [f for f in report.errors if f.rule_id == "SR-9"] == []


# ---------------------------------------------------------------------------
# SR-10: a series may repeat a phrase; it may not reuse a passage
# ---------------------------------------------------------------------------
#
# Measured 2026-08-23 across all 465 pairs of the committed corpus (`AL-564`,
# `AL-568`): the 464 non-series pairs run 2 to 8 words, median 5, exactly one
# at 8, every one of them at 0% coverage, while the
# brass-lantern series pair reaches 98 words over 246 distinct passages of 15+
# words, 18.6% of book 2. The 6,691 covered words are 16.8% of the 39,935-word
# book 1 and 18.6% of the 35,920-word book 2; `RunProfile.coverage` reports the
# WORSE-affected side, so 18.6% is the number the rule actually compares
# against the 2% bound. A deliberate refrain is short by construction and
# therefore cannot reach the bound, which is what lets the rule permit one
# without any declaration, allowlist, or authoring step.


def _prose_book(
    *,
    book_index: int,
    body: str,
    is_final: bool = False,
    entry: str | None = None,
) -> Storybook:
    """A chain-valid book whose single non-ending node carries ``body``."""
    book = _book(book_index=book_index, is_final=is_final, entry=entry, win=True)
    return book.model_copy(
        update={
            "nodes": [
                book.nodes[0].model_copy(update={"body": body}),
                book.nodes[1],
            ]
        }
    )


def _distinct(prefix: str, count: int) -> str:
    """Return ``count`` words that cannot collide with any other prefix."""
    return " ".join(f"{prefix}{i}" for i in range(count))


def _sr10(report: ValidationReport) -> list[str]:
    """Return the SR-10 messages in a report."""
    return [f.message for f in report.findings if f.rule_id == "SR-10"]


@pytest.mark.unit
def test_sr10_flags_a_passage_reused_between_two_books() -> None:
    """A shared 40-word passage is reuse, and blocks the chain."""
    passage = _distinct("shared", 40)
    report = validate_series(
        [
            _prose_book(book_index=1, body=f"{_distinct('a', 60)} {passage}"),
            _prose_book(
                book_index=2,
                body=f"{_distinct('b', 60)} {passage}",
                entry="n0",
                is_final=True,
            ),
        ]
    )
    messages = _sr10(report)
    assert len(messages) == 1
    assert "40" in messages[0]
    assert not report.ok


@pytest.mark.unit
def test_sr10_allows_a_refrain_repeated_across_the_chain() -> None:
    """The decision this rule encodes: a repeated phrase is legitimate craft.

    The refrain appears twice in each book, so a volume measure would count it
    four times over. Run length does not care how often a short phrase recurs.
    """
    refrain = "the brass lantern never tells lies"
    report = validate_series(
        [
            _prose_book(
                book_index=1,
                body=f"{refrain} {_distinct('a', 80)} {refrain}",
            ),
            _prose_book(
                book_index=2,
                body=f"{refrain} {_distinct('b', 80)} {refrain}",
                entry="n0",
                is_final=True,
            ),
        ]
    )
    assert _sr10(report) == []
    assert report.ok, [f.message for f in report.findings]


@pytest.mark.unit
def test_sr10_run_bound_is_inclusive_at_the_limit_and_fires_one_word_over() -> None:
    """Fifteen words is a refrain; sixteen is a reused passage.

    The two books carry enough distinct filler that coverage stays under 2% in
    BOTH cases, so only the run-length bound can decide the verdict. Nothing
    else in the suite pins whether the comparison is ``<=`` or ``<``, and an
    off-by-one either permanently blocks a legitimate 15-word refrain or lets a
    16-word reused passage through as one.
    """
    filler_a, filler_b = _distinct("a", 1000), _distinct("b", 1000)

    at_limit = _distinct("shared", SERIES_MAX_SHARED_RUN_WORDS)
    permitted = validate_series(
        [
            _prose_book(book_index=1, body=f"{at_limit} {filler_a}"),
            _prose_book(
                book_index=2, body=f"{at_limit} {filler_b}", entry="n0", is_final=True
            ),
        ]
    )
    assert _sr10(permitted) == []

    one_over = _distinct("shared", SERIES_MAX_SHARED_RUN_WORDS + 1)
    blocked = validate_series(
        [
            _prose_book(book_index=1, body=f"{one_over} {filler_a}"),
            _prose_book(
                book_index=2, body=f"{one_over} {filler_b}", entry="n0", is_final=True
            ),
        ]
    )
    assert len(_sr10(blocked)) == 1
    assert f"{SERIES_MAX_SHARED_RUN_WORDS + 1} words" in _sr10(blocked)[0]


@pytest.mark.unit
def test_sr10_coverage_bound_fires_while_every_run_is_within_the_limit() -> None:
    """Many passages at the limit are caught by volume, not by length.

    This is the case the second bound exists for and the only one that
    distinguishes it: ten separate 15-word reuses leave ``longest`` at exactly
    15, so the run bound passes, and only the coverage bound can catch a book
    that is three quarters copied. Without this test the coverage check could
    be deleted and the suite would stay green.
    """
    runs = [_distinct(f"shared{n}", SERIES_MAX_SHARED_RUN_WORDS) for n in range(10)]
    # Different separators on each side, so adjacent shared runs cannot merge
    # into one longer run and push `longest` past the bound.
    body_a = " ".join(f"{run} {_distinct(f'gapa{n}', 5)}" for n, run in enumerate(runs))
    body_b = " ".join(f"{run} {_distinct(f'gapb{n}', 5)}" for n, run in enumerate(runs))

    report = validate_series(
        [
            _prose_book(book_index=1, body=body_a),
            _prose_book(book_index=2, body=body_b, entry="n0", is_final=True),
        ]
    )

    messages = _sr10(report)
    assert len(messages) == 1
    # The run bound is satisfied; the verdict comes entirely from coverage.
    assert f"longest shared passage {SERIES_MAX_SHARED_RUN_WORDS} words" in messages[0]


@pytest.mark.unit
def test_sr10_compares_every_pair_not_only_adjacent_books() -> None:
    """Books 1 and 3 reusing prose must be caught even when book 2 is clean.

    ``_check_prose_convergence`` uses ``combinations``, but ``pairwise`` is
    imported in this same module for the rules that genuinely are adjacency
    rules, so an adjacent-only implementation is a live possibility rather than
    a strawman. A chain that skips a book is exactly how it would hide.
    """
    passage = _distinct("shared", 40)
    report = validate_series(
        [
            _prose_book(book_index=1, body=f"{passage} {_distinct('a', 80)}"),
            _prose_book(book_index=2, body=_distinct("b", 200), entry="n0"),
            _prose_book(
                book_index=3,
                body=f"{passage} {_distinct('c', 80)}",
                entry="n0",
                is_final=True,
            ),
        ]
    )

    messages = _sr10(report)
    assert len(messages) == 1
    assert "'book1'" in messages[0]
    assert "'book3'" in messages[0]
    assert "'book2'" not in messages[0]


@pytest.mark.unit
def test_sr10_names_both_books_and_carries_no_prose() -> None:
    """The message must identify the pair without quoting the shared text.

    A series chain can span families once catalog books enter a chain, and a
    validation message is read by whoever is holding the failing publish.
    """
    passage = _distinct("shared", 40)
    report = validate_series(
        [
            _prose_book(book_index=1, body=passage),
            _prose_book(book_index=2, body=passage, entry="n0", is_final=True),
        ]
    )
    message = _sr10(report)[0]
    assert "book1" in message
    assert "book2" in message
    assert "shared0" not in message


_CONTROL_PAIR = ("the-hollow-lighthouse", "the-midnight-museum")
_DEFECT_PAIR = ("the-harrowstone-keep", "the-sunken-temple")


def _fill_text(name: str) -> str:
    """Return one committed fill's body prose, choice labels excluded."""
    blob = json.loads(
        (_REPO_ROOT / "out" / f"{name}.filled.json").read_text(encoding="utf-8")
    )
    return storybook_text(Storybook.model_validate(blob), include_choice_labels=False)


@pytest.mark.unit
def test_the_fifteen_word_bound_sits_in_an_empty_gap_in_the_corpus() -> None:
    """Recompute the calibration the 15-word bound rests on.

    A constant justified only by a number in a commit message rots the moment
    the corpus grows. This recomputes both ends of the gap the bound sits in.

    Full sweep of the 31 committed top-level fills, 465 pairs, measured
    2026-08-23 by running the shipped ``shared_run_profile`` over every pair
    (17.9s; the earlier quadratic implementation could not do this at all):

        longest shared run   pairs
                 2 words       3
                 3 words     103
                 4 words     120
                 5 words     155
                 6 words      69
                 7 words      13
                 8 words       1   <- the highest control
                98 words       1   <- the AL-564 defect, and the only one

    Every one of the 464 control pairs sits at exactly 0% coverage. Nothing at
    all falls between 8 words and 98, so the bound is not a threshold picked
    on a crowded axis: it is a line drawn through empty space, which is why
    `AL-568` could rule without an allowlist. This test pins the two edges of
    that gap, since a regression that matters would have to move one of them.
    """
    control = shared_run_profile(*(_fill_text(n) for n in _CONTROL_PAIR))
    defect = shared_run_profile(*(_fill_text(n) for n in _DEFECT_PAIR))

    # The worst control the corpus offers still clears the bound with room.
    assert control.longest == 8
    assert control.coverage == 0.0
    assert control.longest < SERIES_MAX_SHARED_RUN_WORDS

    # The defect that motivated the rule breaks BOTH bounds, not just one.
    assert defect.longest == 98
    assert defect.longest > SERIES_MAX_SHARED_RUN_WORDS
    assert defect.coverage > SERIES_MAX_SHARED_RUN_COVERAGE
    assert round(defect.coverage, 4) == 0.1863

    # The property that makes the bound cheap: it is not near anything. It
    # clears the worst control by 1.87x and undercuts the defect by 6.53x, so
    # neither edge of the gap is within rounding distance of the constant.
    assert SERIES_MAX_SHARED_RUN_WORDS / control.longest >= 1.8
    assert defect.longest / SERIES_MAX_SHARED_RUN_WORDS >= 6.5


@pytest.mark.unit
def test_sr10_measures_sentinel_stripped_prose() -> None:
    """A chain is not blocked by slot ids the reader never sees.

    An ADR-023 sentinel is `{~SLOTID:Generic~}` and survives verbatim through
    fill, moderation, approval and storage by design, so a published body can
    carry them once that work is flag-ON. The grams tokenizer lowercases and
    splits on `[a-z']+`, so an UNSTRIPPED `{~HERO:Explorer~}` yields both
    `hero` and `explorer`, and the slot-id half is identical in every book that
    binds that slot. Each sentinel inside a shared run therefore adds one
    spurious shared token, which can only lengthen a run and never shorten it,
    so the error is always a FALSE block on a legitimate chain.

    `story_text` strips, which is what makes this chain pass. Twelve shared
    words plus two sentinels measures 14 stripped and 16 unstripped, so the
    bound (15, inclusive) falls between the two verdicts and this test fails if
    the strip is removed. Stripping there rather than in `storybook_text` is
    what keeps one definition of a fill's prose across the blob path and the
    parsed-model path, which is the `AL-563` drift.
    """
    for name in ("the-harrowstone-keep", "the-sunken-temple"):
        assert find_sentinels(_fill_text(name)) == [], (
            f"{name} now carries sentinels; SR-10's calibration figures were "
            f"measured on sentinel-free prose and need a recheck"
        )

    bound = _prose_book(book_index=1, body="the {~HERO:Explorer~} walked north")
    text = storybook_text(bound, include_choice_labels=False)
    assert "{~HERO:Explorer~}" not in text
    assert "Explorer" in text

    shared = _distinct("shared", 12).split()
    for offset, index in enumerate((4, 8)):
        shared.insert(index + offset, "{~HERO:Explorer~}")
    run = " ".join(shared)
    filler_a, filler_b = _distinct("a", 1000), _distinct("b", 1000)

    report = validate_series(
        [
            _prose_book(book_index=1, body=f"{run} {filler_a}"),
            _prose_book(
                book_index=2, body=f"{run} {filler_b}", entry="n0", is_final=True
            ),
        ]
    )
    assert _sr10(report) == []
    assert report.ok, [f.message for f in report.findings]

    # The bound really does sit between the two measurements, so the assertion
    # above is load-bearing rather than passing for an unrelated reason.
    stripped = shared_run_profile(
        storybook_text(
            _prose_book(book_index=1, body=f"{run} {filler_a}"),
            include_choice_labels=False,
        ),
        storybook_text(
            _prose_book(
                book_index=2, body=f"{run} {filler_b}", entry="n0", is_final=True
            ),
            include_choice_labels=False,
        ),
    )
    unstripped = shared_run_profile(f"{run} {filler_a}", f"{run} {filler_b}")
    assert stripped.longest <= SERIES_MAX_SHARED_RUN_WORDS < unstripped.longest


@pytest.mark.unit
def test_sr10_catches_the_real_brass_lantern_pair() -> None:
    """The falsification: the defect that motivated the rule must fail it.

    `AL-564`. Both books are committed, so unlike the wyrmreach fixtures above
    this one actually executes.
    """
    books = [
        Storybook.model_validate(
            json.loads(
                (_REPO_ROOT / "out" / f"{name}.filled.json").read_text(encoding="utf-8")
            )
        )
        for name in ("the-harrowstone-keep", "the-sunken-temple")
    ]
    messages = _sr10(validate_series(books))
    assert len(messages) == 1
    assert "98" in messages[0]
