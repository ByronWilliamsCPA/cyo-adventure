"""WS-8 catalog-flywheel trigger: pure saturation reading and threshold math.

The reader half of the flywheel's demand signal (design section 4.1). Story
requests whose skeleton selection escalates past tree-level differentiation
persist an enum-only ``CELL_SATURATED`` pipeline event (see
``story_requests/authoring_plan.py`` and ``events/writer.py``'s allowlist).
This module turns those already-fetched rows into per-cell
:class:`SaturationReading` values and applies the trigger thresholds.

It is PURE by construction (mirroring ``diversity/query.py::score_history``):
no I/O, no database, no network. A caller (``scripts/flywheel_scan.py``)
fetches the rows and hands them in as :class:`RawSaturationEvent` values, so
every branch is exercisable from hand-built inputs.

**OWASP LLM01, the reader half of the both-directions safety property.** The
writer's payload allowlist forbids free text on the way in; this module
re-validates every field against the closed band/length/style/level
vocabularies on the way out, DROPPING any row whose values fail, so a row that
somehow carried junk (a manual insert, a schema drift) can never propagate an
unvalidated value into a cell coordinate.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.diversity.query import DifferentiationLevel
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle

if TYPE_CHECKING:
    from collections.abc import Sequence

# The trigger thresholds (design section 4.1 / 8.2). A cell triggers when it
# has at least this many CATALOG-level escalations, from at least this many
# distinct requests, within the caller's scan window. Module-level so they are
# tunable only by a reviewed PR (the same posture as the floor baseline).
DEFAULT_MIN_CATALOG_EVENTS = 3
DEFAULT_MIN_DISTINCT_REQUESTS = 2

# Closed-vocabulary value sets for the reader-side re-validation (LLM01). Built
# from the enums so they can never drift from the vocabularies the writer's
# allowlist implicitly enforces.
_VALID_BANDS = frozenset(band.value for band in AgeBand)
_VALID_LENGTHS = frozenset(length.value for length in Length)
_VALID_STYLES = frozenset(style.value for style in NarrativeStyle)
_VALID_LEVELS = frozenset(level.value for level in DifferentiationLevel)


@dataclass(frozen=True, slots=True)
class RawSaturationEvent:
    """One un-validated ``CELL_SATURATED`` row as fetched from the event log.

    The fields are raw strings taken verbatim from the event payload
    (``age_band``/``length``/``style``/``level``) and the row's anchor
    (``request_id`` from ``entity_id``). They are re-validated by
    :func:`saturation_readings`; a caller or test can hand-build these without
    a database.

    Attributes:
        age_band: The cell's age band, expected to be an :class:`AgeBand`
            value.
        length: The cell's length tier, expected to be a :class:`Length`
            value.
        style: The cell's narrative style, expected to be a
            :class:`NarrativeStyle` value.
        level: The escalation level that fired the event, expected to be a
            :class:`DifferentiationLevel` value (``leaf`` or ``catalog``).
        request_id: The anchoring story-request id (the event's ``entity_id``);
            the distinct-request denominator counts these.
    """

    age_band: str
    length: str
    style: str
    level: str
    request_id: str


@dataclass(frozen=True, slots=True)
class SaturationReading:
    """Per-cell saturation counters over a scan window (design section 4.1).

    Attributes:
        band: The cell's validated :class:`AgeBand` value.
        length: The cell's validated :class:`Length` value.
        style: The cell's validated :class:`NarrativeStyle` value.
        catalog_events: Count of CATALOG-level events for the cell in the
            window (the trigger's numerator).
        leaf_events: Count of LEAF-level events for the cell in the window
            (context only; never a trigger input).
        distinct_requests: Count of distinct request anchors behind the
            cell's CATALOG-level events (the trigger's distinct-request
            qualifier, so one prolific family cannot single-handedly commission
            catalog growth).
        window_days: The scan window the counts were computed over, passed in
            by the caller.
    """

    band: str
    length: str
    style: str
    catalog_events: int
    leaf_events: int
    distinct_requests: int
    window_days: int


def saturation_readings(
    events: Sequence[RawSaturationEvent],
    *,
    window_days: int,
) -> list[SaturationReading]:
    """Aggregate raw events into validated per-cell saturation readings.

    Rows whose enum values fail re-validation are DROPPED, never propagated:
    this is the reader half of the LLM01 both-directions safety property
    (module docstring). Surviving rows are grouped by ``(band, length,
    style)`` and reduced to counts.

    Args:
        events: Raw ``CELL_SATURATED`` rows, in any order.
        window_days: The scan window the caller fetched ``events`` over,
            carried onto every reading for reporting.

    Returns:
        One :class:`SaturationReading` per distinct valid cell, ordered by
        ``(band, length, style)`` for deterministic output.
    """
    # #ASSUME: data-integrity: an event field that is not a member of its
    # closed enum vocabulary is treated as corrupt and its whole row is
    # dropped, rather than coerced or passed through, so no un-vetted value
    # ever becomes a cell coordinate downstream.
    # #VERIFY: test drops rows with a junk band/length/style/level and keeps
    # only fully-valid rows (tests/unit/test_flywheel_trigger.py).
    cells: dict[tuple[str, str, str], list[RawSaturationEvent]] = defaultdict(list)
    for event in events:
        if (
            event.age_band in _VALID_BANDS
            and event.length in _VALID_LENGTHS
            and event.style in _VALID_STYLES
            and event.level in _VALID_LEVELS
        ):
            cells[(event.age_band, event.length, event.style)].append(event)

    catalog = DifferentiationLevel.CATALOG.value
    leaf = DifferentiationLevel.LEAF.value
    readings: list[SaturationReading] = []
    for (band, length, style), cell_events in sorted(cells.items()):
        catalog_events = [event for event in cell_events if event.level == catalog]
        readings.append(
            SaturationReading(
                band=band,
                length=length,
                style=style,
                catalog_events=len(catalog_events),
                leaf_events=sum(1 for event in cell_events if event.level == leaf),
                distinct_requests=len({event.request_id for event in catalog_events}),
                window_days=window_days,
            )
        )
    return readings


def saturated_cells(
    readings: Sequence[SaturationReading],
    *,
    min_catalog_events: int = DEFAULT_MIN_CATALOG_EVENTS,
    min_distinct_requests: int = DEFAULT_MIN_DISTINCT_REQUESTS,
) -> list[SaturationReading]:
    """Return the readings that meet BOTH trigger thresholds.

    A cell triggers only when it has enough CATALOG escalations AND those come
    from enough distinct requests; a cell with many escalations from a single
    request does not trigger (design section 4.1).

    Args:
        readings: Per-cell readings (from :func:`saturation_readings`).
        min_catalog_events: Minimum CATALOG-level events to trigger.
        min_distinct_requests: Minimum distinct request anchors to trigger.

    Returns:
        The subset of ``readings`` at or above both thresholds, in input
        order.
    """
    return [
        reading
        for reading in readings
        if reading.catalog_events >= min_catalog_events
        and reading.distinct_requests >= min_distinct_requests
    ]
