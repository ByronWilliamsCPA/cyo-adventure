"""Unit tests for the WS-8 catalog-flywheel trigger (pure reader + thresholds)."""

from __future__ import annotations

from cyo_adventure.flywheel.trigger import (
    DEFAULT_MIN_CATALOG_EVENTS,
    DEFAULT_MIN_DISTINCT_REQUESTS,
    RawSaturationEvent,
    SaturationReading,
    saturated_cells,
    saturation_readings,
)


def _event(
    *,
    band: str = "8-11",
    length: str = "short",
    style: str = "prose",
    level: str = "catalog",
    request_id: str = "req-1",
) -> RawSaturationEvent:
    """Build one raw saturation event with sensible cell defaults."""
    return RawSaturationEvent(
        age_band=band,
        length=length,
        style=style,
        level=level,
        request_id=request_id,
    )


def _reading(
    *,
    catalog_events: int,
    distinct_requests: int,
    leaf_events: int = 0,
) -> SaturationReading:
    """Build a per-cell reading for direct threshold-math tests."""
    return SaturationReading(
        band="8-11",
        length="short",
        style="prose",
        catalog_events=catalog_events,
        leaf_events=leaf_events,
        distinct_requests=distinct_requests,
        window_days=30,
    )


def test_saturation_readings_drops_rows_with_junk_enum_values() -> None:
    # The reader half of the LLM01 both-directions property: a row whose band,
    # length, style, or level is not a member of its closed vocabulary is
    # dropped whole, never coerced or propagated into a cell coordinate.
    events = [
        _event(),  # fully valid
        _event(band="99-100"),  # junk band
        _event(length="epic"),  # junk length
        _event(style="opera"),  # junk style
        _event(level="tree-ish"),  # junk level
    ]
    readings = saturation_readings(events, window_days=30)
    assert len(readings) == 1
    only = readings[0]
    assert (only.band, only.length, only.style) == ("8-11", "short", "prose")
    assert only.catalog_events == 1


def test_saturation_readings_counts_catalog_leaf_and_distinct_requests() -> None:
    # Two catalog events from two distinct requests, plus one leaf event, all
    # in the same cell: catalog and leaf are counted separately, and the
    # distinct-request denominator counts only the catalog anchors.
    events = [
        _event(level="catalog", request_id="req-1"),
        _event(level="catalog", request_id="req-2"),
        _event(level="leaf", request_id="req-3"),
    ]
    readings = saturation_readings(events, window_days=30)
    assert len(readings) == 1
    cell = readings[0]
    assert cell.catalog_events == 2
    assert cell.leaf_events == 1
    assert cell.distinct_requests == 2
    assert cell.window_days == 30


def test_saturation_readings_groups_by_full_cell_coordinate() -> None:
    # Events differing only in length/style are distinct cells, not merged.
    events = [
        _event(length="short"),
        _event(length="medium"),
        _event(style="gamebook", band="13-16", length="long"),
    ]
    readings = saturation_readings(events, window_days=30)
    cells = {(r.band, r.length, r.style) for r in readings}
    assert cells == {
        ("8-11", "short", "prose"),
        ("8-11", "medium", "prose"),
        ("13-16", "long", "gamebook"),
    }


def test_saturation_readings_empty_input_yields_no_readings() -> None:
    assert saturation_readings([], window_days=30) == []


def test_saturated_cells_below_both_thresholds_does_not_trigger() -> None:
    readings = [_reading(catalog_events=2, distinct_requests=1)]
    assert saturated_cells(readings) == []


def test_saturated_cells_at_both_thresholds_triggers() -> None:
    # Exactly at the defaults (>= is inclusive) must trigger.
    reading = _reading(
        catalog_events=DEFAULT_MIN_CATALOG_EVENTS,
        distinct_requests=DEFAULT_MIN_DISTINCT_REQUESTS,
    )
    assert saturated_cells([reading]) == [reading]


def test_saturated_cells_above_both_thresholds_triggers() -> None:
    reading = _reading(catalog_events=10, distinct_requests=5)
    assert saturated_cells([reading]) == [reading]


def test_saturated_cells_enough_events_one_request_does_not_trigger() -> None:
    # The distinct-requests qualifier: many catalog events from a single
    # request must NOT trigger, so one prolific family cannot single-handedly
    # commission catalog growth (design section 4.1).
    reading = _reading(catalog_events=5, distinct_requests=1)
    assert saturated_cells([reading]) == []


def test_saturated_cells_enough_requests_too_few_events_does_not_trigger() -> None:
    # The dual-threshold is AND, not OR: distinct requests alone is not enough.
    reading = _reading(
        catalog_events=DEFAULT_MIN_CATALOG_EVENTS - 1,
        distinct_requests=DEFAULT_MIN_DISTINCT_REQUESTS + 3,
    )
    assert saturated_cells([reading]) == []


def test_saturated_cells_honors_custom_thresholds() -> None:
    reading = _reading(catalog_events=1, distinct_requests=1)
    triggered = saturated_cells(
        [reading], min_catalog_events=1, min_distinct_requests=1
    )
    assert triggered == [reading]


def test_saturated_cells_selects_only_qualifying_cells_from_a_mix() -> None:
    qualifying = _reading(catalog_events=4, distinct_requests=3)
    one_request = _reading(catalog_events=9, distinct_requests=1)
    too_few = _reading(catalog_events=1, distinct_requests=1)
    triggered = saturated_cells([qualifying, one_request, too_few])
    assert triggered == [qualifying]
