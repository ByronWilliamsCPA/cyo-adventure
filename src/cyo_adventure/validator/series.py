"""Cross-book series meta-validator (rules SR-1..SR-7).

Unlike the single-story gate (Layer 1, Layer 2, and the PL-* policy rules), this
validator runs over a *chain* of books: a series is a meta-skeleton whose nodes
are whole Storybooks and whose edges are the completion-to-entry continuations.
It checks the ADR-011 section-8 invariant that ties the chain together: in any
non-final book, every successful-completion ending converges on the next book's
single ``series_entry_node`` (many endings -> one entry), with declared state
carried across (or explicitly episodic for young/Tier-1 bands). v1 series are a
linear chain.

Each book still passes its own single-story gate independently; this validator
adds only the cross-book checks and returns its own report, so it is invoked
separately from ``run_gate``.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

from cyo_adventure.storybook.models import EndingKind, VariableType
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.storybook.models import Series, Storybook, Variable

# A satisfying continuation ending: a win the reader carries into the next book.
# A fail-fast negative ending does not continue the campaign, matching PL-20.
_SATISFYING_KINDS = frozenset({EndingKind.SUCCESS, EndingKind.COMPLETION})

# Bands that must run episodic (no state carry) series, per ADR-011 section 8.
_YOUNG_BANDS = frozenset({"3-5", "5-8"})

_Book = tuple["Storybook", "Series"]


def validate_series(books: Sequence[Storybook]) -> ValidationReport:
    """Validate a chain of books as an ADR-011 series.

    Args:
        books: The books of a single series, in any order. The checks key off
            ``book_index`` and are order-independent; the input is not reordered.

    Returns:
        ValidationReport: SR-* findings; ``ok`` is ``True`` when none are errors.
    """
    report = ValidationReport()
    series_books = _collect_series_books(books, report)
    if not series_books:
        return report
    _check_shared_id(series_books, report)
    well_formed = _check_indices(series_books, report)
    _check_entry_nodes(series_books, report)
    if well_formed:
        _check_final_flags(series_books, report)
        _check_continuity(series_books, report)
    _check_state_carry(series_books, report)
    if well_formed:
        _check_carried_variables(series_books, report)
    return report


def _collect_series_books(
    books: Sequence[Storybook], report: ValidationReport
) -> list[_Book]:
    """SR-1: pair each book with its series metadata, flagging any that lack it.

    A book with no ``series`` block cannot participate in a chain; it is reported
    and excluded so the remaining checks operate only on series-tagged books.
    """
    series_books: list[_Book] = []
    for book in books:
        series = book.metadata.series
        if series is None:
            report.add(
                ValidationFinding(
                    rule_id="SR-1",
                    severity=Severity.ERROR,
                    story_id=book.id,
                    message=(
                        f"SR-1 series: book '{book.id}' declares no series metadata "
                        f"but was passed as part of a series chain"
                    ),
                )
            )
        else:
            series_books.append((book, series))
    return series_books


def _check_shared_id(series_books: list[_Book], report: ValidationReport) -> None:
    """SR-1: every book in the chain must share one ``series_id``."""
    ids = {series.series_id for _book, series in series_books}
    if len(ids) > 1:
        first = series_books[0][0]
        report.add(
            ValidationFinding(
                rule_id="SR-1",
                severity=Severity.ERROR,
                story_id=first.id,
                message=(
                    f"SR-1 series: chain spans multiple series ids "
                    f"{sorted(ids)}; a series is one id"
                ),
            )
        )


def _check_indices(series_books: list[_Book], report: ValidationReport) -> bool:
    """SR-2: ``book_index`` values must be a contiguous ``1..N`` with no repeats.

    Returns:
        ``True`` when the indices are well-formed, so the index-dependent checks
        (final flag, continuity) can run safely.
    """
    indices = sorted(series.book_index for _book, series in series_books)
    expected = list(range(1, len(series_books) + 1))
    if indices != expected:
        report.add(
            ValidationFinding(
                rule_id="SR-2",
                severity=Severity.ERROR,
                story_id=series_books[0][0].id,
                message=(
                    f"SR-2 series: book_index values {indices} are not a contiguous "
                    f"1..{len(series_books)} chain (gaps or duplicates)"
                ),
            )
        )
        return False
    return True


def _check_entry_nodes(series_books: list[_Book], report: ValidationReport) -> None:
    """SR-3: a declared ``series_entry_node`` must exist; book >1 must declare one."""
    for book, series in series_books:
        node_ids = {node.id for node in book.nodes}
        if (
            series.series_entry_node is not None
            and series.series_entry_node not in node_ids
        ):
            report.add(
                ValidationFinding(
                    rule_id="SR-3",
                    severity=Severity.ERROR,
                    story_id=book.id,
                    node_id=series.series_entry_node,
                    message=(
                        f"SR-3 series: series_entry_node "
                        f"'{series.series_entry_node}' is not a node in book "
                        f"'{book.id}'"
                    ),
                )
            )
        if series.book_index > 1 and series.series_entry_node is None:
            report.add(
                ValidationFinding(
                    rule_id="SR-3",
                    severity=Severity.ERROR,
                    story_id=book.id,
                    message=(
                        f"SR-3 series: continued-into book {series.book_index} "
                        f"'{book.id}' must declare a series_entry_node"
                    ),
                )
            )


def _check_final_flags(series_books: list[_Book], report: ValidationReport) -> None:
    """SR-4: a book below the highest index must not be ``is_final``.

    The top-index book MAY be final (closed series) or not (open-ended chain
    a future continuation extends). ADR-011 section 8 and the WS-G spec (G4)
    make open chains first-class; v1 generation always writes is_final=False.
    """
    last = len(series_books)
    for book, series in series_books:
        if series.is_final and series.book_index != last:
            report.add(
                ValidationFinding(
                    rule_id="SR-4",
                    severity=Severity.ERROR,
                    story_id=book.id,
                    message=(
                        f"SR-4 series: book {series.book_index} '{book.id}' is "
                        f"marked is_final but is not the last of {last} books"
                    ),
                )
            )


def _check_continuity(series_books: list[_Book], report: ValidationReport) -> None:
    """SR-5: each non-final book has a win ending and a next-book entry node.

    This verifies the two ends of the continuation exist: the non-final book
    declares a successful-completion ending, and the next book declares a single
    ``series_entry_node``. It does NOT trace that the win ending targets that entry
    node; books are independent graphs with no shared node ids, so cross-book target
    convergence is not machine-checkable here.
    """
    by_index = {series.book_index: (book, series) for book, series in series_books}
    last = len(series_books)
    for book, series in series_books:
        if series.book_index == last:
            continue  # the final book continues to no next book
        has_win = any(
            node.ending is not None and node.ending.kind in _SATISFYING_KINDS
            for node in book.nodes
        )
        if not has_win:
            report.add(
                ValidationFinding(
                    rule_id="SR-5",
                    severity=Severity.ERROR,
                    story_id=book.id,
                    message=(
                        f"SR-5 series: non-final book {series.book_index} "
                        f"'{book.id}' has no successful-completion ending to "
                        f"continue the campaign"
                    ),
                )
            )
        next_book = by_index.get(series.book_index + 1)
        if next_book is not None and next_book[1].series_entry_node is None:
            report.add(
                ValidationFinding(
                    rule_id="SR-5",
                    severity=Severity.ERROR,
                    story_id=book.id,
                    message=(
                        f"SR-5 series: book {series.book_index} '{book.id}' "
                        f"continues, but the next book '{next_book[0].id}' declares "
                        f"no series_entry_node to converge on"
                    ),
                )
            )


def _check_state_carry(series_books: list[_Book], report: ValidationReport) -> None:
    """SR-6/SR-7: young/Tier-1 books are episodic; the chain is uniform."""
    for book, series in series_books:
        is_young_or_tier1 = (
            book.metadata.age_band.value in _YOUNG_BANDS or book.metadata.tier == 1
        )
        if is_young_or_tier1 and series.carries_state:
            report.add(
                ValidationFinding(
                    rule_id="SR-6",
                    severity=Severity.ERROR,
                    story_id=book.id,
                    message=(
                        f"SR-6 series: book '{book.id}' is a young or Tier-1 story "
                        f"and must run an episodic (carries_state=false) series"
                    ),
                )
            )
    carries = {series.carries_state for _book, series in series_books}
    if len(carries) > 1:
        report.add(
            ValidationFinding(
                rule_id="SR-7",
                severity=Severity.ERROR,
                story_id=series_books[0][0].id,
                message=(
                    "SR-7 series: the chain mixes state-carrying and episodic books; "
                    "carries_state must be uniform across a series"
                ),
            )
        )


def _check_carried_variables(
    series_books: list[_Book], report: ValidationReport
) -> None:
    """SR-8: a state-carrying chain must not lose reader state between books.

    The client seeds a continuation by **variable name** and clamps carried ints
    into the *receiving* book's declared bounds
    (``frontend/src/player/engine.ts::startContinuation``), silently. Two
    consequences, both of which shipped undetected in a real chain:

    * A receiving range narrower than the sending book's rewrites every outcome
      outside it. A book declaring ``renown`` 3..5 after a book that can end
      anywhere in 0..5 turns every low-reputation playthrough into a
      maximum-reputation one. That is data loss, so it is an ERROR.
    * A variable the sender declares and the receiver does not is dropped without
      trace. That is sometimes deliberate (a new jurisdiction, a closed
      storyline), so it is a WARNING naming the variable rather than a block.

    A type change is an ERROR: the client skips a wrong-typed carried value
    entirely, so the receiving book silently runs on its own initial.

    Only runs on a chain that declares ``carries_state``; an episodic chain
    carries nothing by definition.

    Args:
        series_books: (story, series) pairs, already index-validated.
        report: The report to append findings to.
    """
    ordered = sorted(series_books, key=lambda pair: pair[1].book_index)
    if not ordered or not all(series.carries_state for _, series in ordered):
        return
    for (sender, sender_series), (receiver, receiver_series) in pairwise(ordered):
        received = {var.name: var for var in receiver.variables}
        for var in sender.variables:
            target = received.get(var.name)
            if target is None:
                report.add(
                    ValidationFinding(
                        rule_id="SR-8",
                        severity=Severity.WARNING,
                        story_id=receiver.id,
                        message=(
                            f"SR-8 carry: book {receiver_series.book_index} "
                            f"'{receiver.id}' does not declare '{var.name}', which "
                            f"book {sender_series.book_index} declares, so that "
                            f"carried value is dropped without trace"
                        ),
                    )
                )
                continue
            if target.type is not var.type:
                report.add(
                    ValidationFinding(
                        rule_id="SR-8",
                        severity=Severity.ERROR,
                        story_id=receiver.id,
                        message=(
                            f"SR-8 carry: '{var.name}' is {var.type.value} in book "
                            f"{sender_series.book_index} and {target.type.value} in "
                            f"book {receiver_series.book_index} '{receiver.id}'; a "
                            f"wrong-typed carried value is skipped, so the receiving "
                            f"book silently runs on its own initial"
                        ),
                    )
                )
                continue
            _check_range_contains(
                (var, sender_series), (target, receiver_series), receiver.id, report
            )


def _check_range_contains(
    sender: tuple[Variable, Series],
    receiver: tuple[Variable, Series],
    receiver_id: str,
    report: ValidationReport,
) -> None:
    """Flag a receiving int range that cannot hold every value the sender emits."""
    sender_var, sender_series = sender
    receiver_var, receiver_series = receiver
    if sender_var.type is not VariableType.INT:
        return
    sender_lo, sender_hi = sender_var.min, sender_var.max
    recv_lo, recv_hi = receiver_var.min, receiver_var.max
    if sender_lo is None or sender_hi is None or recv_lo is None or recv_hi is None:
        return
    if int(recv_lo) <= int(sender_lo) and int(recv_hi) >= int(sender_hi):
        return
    report.add(
        ValidationFinding(
            rule_id="SR-8",
            severity=Severity.ERROR,
            story_id=receiver_id,
            message=(
                f"SR-8 carry: '{sender_var.name}' is [{int(sender_lo)},"
                f"{int(sender_hi)}] in book {sender_series.book_index} but "
                f"[{int(recv_lo)},{int(recv_hi)}] in book "
                f"{receiver_series.book_index} '{receiver_id}'; the receiving range "
                f"must contain the sending range or the client clamps carried "
                f"outcomes away"
            ),
        )
    )
