"""Unit tests for the sentinel-survival failure taxonomy (plan 3.4).

Drives `classify_fill` through every `check_sentinel_integrity` violation
kind using small, hand-built pre-fill/filled node maps (no LLM, no fixtures
package involvement), asserting the correct plan 3.4 bucket AND the
underlying raw checker kind are both recorded, and that `clean` is only True
on an exact sentinel match.
"""

from __future__ import annotations

import pytest

from cyo_adventure.measurement.taxonomy import bucket_for, classify_fill


def _story(nodes: list[dict[str, object]]) -> dict[str, object]:
    return {"nodes": nodes}


@pytest.mark.unit
def test_classify_fill_clean_when_sentinel_preserved_verbatim() -> None:
    """An exact sentinel match yields clean=True and zero violations."""
    pre_fill = _story(
        [{"id": "n1", "body": "The {~HERO:Explorer~} sets off on an adventure."}]
    )
    filled = _story([{"id": "n1", "body": "The {~HERO:Explorer~} sets off at last."}])
    record = classify_fill(pre_fill, filled)
    assert record.clean is True
    assert record.violations == ()
    assert record.raw_kind_counts() == {}
    assert record.bucket_counts() == {}


@pytest.mark.unit
def test_classify_fill_dropped_sentinel() -> None:
    """A sentinel present pre-fill but absent from the filled node is dropped."""
    pre_fill = _story([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _story([{"id": "n1", "body": "A brave adventurer sets off."}])
    record = classify_fill(pre_fill, filled)
    assert record.clean is False
    assert record.raw_kind_counts() == {"dropped": 1}
    assert record.bucket_counts() == {"dropped": 1}
    assert record.violations[0].node_id == "n1"
    assert record.violations[0].token == "{~HERO:Explorer~}"


@pytest.mark.unit
def test_classify_fill_forged_sentinel() -> None:
    """A well-formed sentinel that no pre-fill node declared anywhere is forged."""
    pre_fill = _story([{"id": "n1", "body": "Plain beats guidance, no slot."}])
    filled = _story(
        [{"id": "n1", "body": "The {~HERO:Explorer~} appears from nowhere."}]
    )
    record = classify_fill(pre_fill, filled)
    assert record.clean is False
    assert record.raw_kind_counts() == {"forged": 1}
    assert record.bucket_counts() == {"mutated_wrapper_or_inner": 1}


@pytest.mark.unit
def test_classify_fill_migrated_sentinel() -> None:
    """A token dropped from its declared node but reappearing unmutated elsewhere is migrated."""
    pre_fill = _story(
        [
            {"id": "n1", "body": "The {~HERO:Explorer~} sets off."},
            {"id": "n2", "body": "Plain beats guidance, no slot."},
        ]
    )
    filled = _story(
        [
            {"id": "n1", "body": "A brave adventurer sets off."},
            {"id": "n2", "body": "The {~HERO:Explorer~} appears here instead."},
        ]
    )
    record = classify_fill(pre_fill, filled)
    assert record.clean is False
    assert record.raw_kind_counts() == {"migrated": 2}
    assert record.bucket_counts() == {"relocated": 2}


@pytest.mark.unit
def test_classify_fill_malformed_sentinel() -> None:
    """A truncated/near-miss sentinel wrapper is malformed."""
    pre_fill = _story([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _story([{"id": "n1", "body": "The {~HERO:Ex sets off."}])
    record = classify_fill(pre_fill, filled)
    assert record.clean is False
    assert "malformed" in record.raw_kind_counts()
    assert "mutated_wrapper" in record.bucket_counts()


@pytest.mark.unit
def test_classify_fill_sentinel_in_choice_label() -> None:
    """A well-formed sentinel surfacing in a choice label is in_choice_label."""
    pre_fill = _story(
        [
            {
                "id": "n1",
                "body": "The {~HERO:Explorer~} sets off.",
                "choices": [{"label": "Go north."}],
            }
        ]
    )
    filled = _story(
        [
            {
                "id": "n1",
                "body": "The {~HERO:Explorer~} sets off.",
                "choices": [{"label": "Follow {~HERO:Explorer~} north."}],
            }
        ]
    )
    record = classify_fill(pre_fill, filled)
    assert record.clean is False
    assert record.raw_kind_counts() == {"in_choice_label": 1}
    assert record.bucket_counts() == {"relocated_into_label": 1}


@pytest.mark.unit
def test_bucket_for_maps_every_raw_kind() -> None:
    """Every raw checker kind maps to exactly one plan 3.4 bucket."""
    assert bucket_for("dropped") == "dropped"
    assert bucket_for("forged") == "mutated_wrapper_or_inner"
    assert bucket_for("migrated") == "relocated"
    assert bucket_for("malformed") == "mutated_wrapper"
    assert bucket_for("in_choice_label") == "relocated_into_label"


@pytest.mark.unit
def test_bucket_for_unmapped_kind_raises() -> None:
    """An unmapped raw kind fails loudly rather than being silently dropped."""
    with pytest.raises(ValueError, match="unmapped sentinel-integrity violation kind"):
        bucket_for("unknown_slot")
