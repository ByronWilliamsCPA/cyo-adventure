"""Unit tests for the cross-book series meta-validator (SR-1..SR-7)."""

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
from cyo_adventure.validator.report import ValidationReport
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
