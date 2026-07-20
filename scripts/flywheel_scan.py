#!/usr/bin/env python3
"""Read-only WS-8 catalog-flywheel saturation scan (design section 4.1 / 8.1).

Reports which ``(band, length, style)`` cells have accumulated enough
CELL_SATURATED escalations to warrant growing the tree catalog. It is the
operator-facing surface of the manual-loop v1: it reads pipeline events and
prints a report, and writes NOTHING (no mutation, no branch, no PR).

    uv run python scripts/flywheel_scan.py --window-days 30

The heavy lifting is the pure :mod:`cyo_adventure.flywheel.trigger`: this
script only fetches ``CELL_SATURATED`` rows in the window, maps each to a
``RawSaturationEvent`` (payload enum values plus the request anchor), and runs
the reader + threshold functions. Enum re-validation and threshold math live
in that module and are unit-tested there.

Exit codes:
    0 - report printed (whether or not any cell triggered).
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.database import get_session
from cyo_adventure.db.models import PipelineEvent
from cyo_adventure.events.models import EventType
from cyo_adventure.flywheel.trigger import (
    DEFAULT_MIN_CATALOG_EVENTS,
    DEFAULT_MIN_DISTINCT_REQUESTS,
    RawSaturationEvent,
    SaturationReading,
    saturated_cells,
    saturation_readings,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_DEFAULT_WINDOW_DAYS = 30


def _build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser.

    Returns:
        argparse.ArgumentParser: The parser for the scan CLI.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window-days",
        type=int,
        default=_DEFAULT_WINDOW_DAYS,
        help=f"Scan window in days (default: {_DEFAULT_WINDOW_DAYS}).",
    )
    parser.add_argument(
        "--min-catalog-events",
        type=int,
        default=DEFAULT_MIN_CATALOG_EVENTS,
        help=(
            "Minimum CATALOG-level events for a cell to trigger "
            f"(default: {DEFAULT_MIN_CATALOG_EVENTS})."
        ),
    )
    parser.add_argument(
        "--min-distinct-requests",
        type=int,
        default=DEFAULT_MIN_DISTINCT_REQUESTS,
        help=(
            "Minimum distinct request anchors for a cell to trigger "
            f"(default: {DEFAULT_MIN_DISTINCT_REQUESTS})."
        ),
    )
    return parser


def _payload_field(payload: Mapping[str, object], key: str) -> str:
    """Return a payload value as a str, or "" for a missing/non-str value.

    An empty string is not a member of any closed vocabulary, so a malformed
    value collapses to a row the reader drops (LLM01 reader-side validation),
    rather than propagating an unvetted value.

    Args:
        payload: The event's JSON payload.
        key: The payload key to read.

    Returns:
        The string value, or "" when absent or not a string.
    """
    value = payload.get(key)
    return value if isinstance(value, str) else ""


async def _fetch_events(window_days: int) -> list[RawSaturationEvent]:
    """Fetch CELL_SATURATED rows in the window as raw saturation events.

    Args:
        window_days: The look-back window in days.

    Returns:
        One :class:`RawSaturationEvent` per row, un-validated (the pure reader
        validates and drops junk).
    """
    # #EDGE: external-resources: read-only query against the pipeline event log;
    # the session is never committed or written to, so a report run cannot
    # mutate state. get_session's context manager rolls back on exit.
    # #VERIFY: no session.add/commit here; the flywheel scan is read-only by
    # design (design sections 3.3, 8.1).
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    async with get_session() as session:
        rows = await session.scalars(
            select(PipelineEvent)
            .where(PipelineEvent.event_type == str(EventType.CELL_SATURATED))
            .where(PipelineEvent.occurred_at >= cutoff)
        )
        return [
            RawSaturationEvent(
                age_band=_payload_field(row.payload, "age_band"),
                length=_payload_field(row.payload, "length"),
                style=_payload_field(row.payload, "style"),
                level=_payload_field(row.payload, "level"),
                request_id=row.entity_id,
            )
            for row in rows
        ]


def _format_reading(reading: SaturationReading) -> str:
    """Render one reading as a single aligned report line.

    Args:
        reading: The per-cell reading to render.

    Returns:
        A one-line summary of the cell and its counters.
    """
    cell = f"band={reading.band} length={reading.length} style={reading.style}"
    return (
        f"  {cell:<44} catalog={reading.catalog_events} "
        f"distinct_requests={reading.distinct_requests} "
        f"leaf={reading.leaf_events}"
    )


def _render_report(
    readings: Sequence[SaturationReading],
    triggered: Sequence[SaturationReading],
    *,
    window_days: int,
    min_catalog_events: int,
    min_distinct_requests: int,
) -> str:
    """Build the plain-text scan report.

    Args:
        readings: Every per-cell reading in the window.
        triggered: The subset meeting both thresholds.
        window_days: The scan window, echoed in the header.
        min_catalog_events: The catalog-event threshold, echoed in the header.
        min_distinct_requests: The distinct-request threshold, echoed.

    Returns:
        The full report as a string ending in a newline.
    """
    triggered_ids = {(r.band, r.length, r.style) for r in triggered}
    context = [r for r in readings if (r.band, r.length, r.style) not in triggered_ids]
    lines = [
        "CYO Adventure catalog-flywheel scan (read-only)",
        (
            f"window: {window_days} days | thresholds: "
            f"catalog>={min_catalog_events}, "
            f"distinct-requests>={min_distinct_requests}"
        ),
        f"cells with CELL_SATURATED events in window: {len(readings)}",
        "",
        f"TRIGGERED cells ({len(triggered)}):",
    ]
    lines.extend(_format_reading(r) for r in triggered)
    if not triggered:
        lines.append("  (none)")
    lines.extend(["", f"Below-threshold cells, for context ({len(context)}):"])
    lines.extend(_format_reading(r) for r in context)
    if not context:
        lines.append("  (none)")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run the flywheel saturation scan.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        int: ``0`` on a printed report, ``2`` on an argparse usage error.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    window_days = int(args.window_days)
    min_catalog_events = int(args.min_catalog_events)
    min_distinct_requests = int(args.min_distinct_requests)

    events = asyncio.run(_fetch_events(window_days))
    readings = saturation_readings(events, window_days=window_days)
    triggered = saturated_cells(
        readings,
        min_catalog_events=min_catalog_events,
        min_distinct_requests=min_distinct_requests,
    )
    sys.stdout.write(
        _render_report(
            readings,
            triggered,
            window_days=window_days,
            min_catalog_events=min_catalog_events,
            min_distinct_requests=min_distinct_requests,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
