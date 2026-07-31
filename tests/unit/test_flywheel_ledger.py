"""Unit tests for the WS-8 flywheel discard ledger (design section 6.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.flywheel.ledger import (
    OUTCOME_DISCARDED,
    OUTCOME_HELD,
    OUTCOME_PROMOTABLE,
    AttemptRecord,
    append_record,
    attempt_sig,
    chain_signature,
    ledger_path,
    load_outcomes,
    load_records,
)
from cyo_adventure.flywheel.strategy import TEMPLATE_SET_VERSION
from cyo_adventure.mutation.compose import ChainStep
from cyo_adventure.mutation.ops import OpParams

if TYPE_CHECKING:
    from pathlib import Path


def _steps() -> list[ChainStep]:
    """Return a representative two-step chain."""
    return [
        ChainStep(op_id="M3", params=OpParams.of(mode="graft", donor="d"), seed=0),
        ChainStep(op_id="M2", params=OpParams.of(), seed=1),
    ]


def test_attempt_sig_is_stable_for_identical_inputs() -> None:
    """Two builds of the same (parent_sha256, chain) yield the same signature."""
    first = attempt_sig("abc", _steps())
    second = attempt_sig("abc", _steps())
    assert first == second


def test_attempt_sig_changes_when_a_step_seed_changes() -> None:
    """A differing seed produces a different signature."""
    base = _steps()
    altered = [base[0], ChainStep(op_id="M2", params=OpParams.of(), seed=99)]
    assert attempt_sig("abc", base) != attempt_sig("abc", altered)


def test_attempt_sig_changes_when_parent_hash_changes() -> None:
    """A different parent content hash invalidates the signature."""
    assert attempt_sig("abc", _steps()) != attempt_sig("xyz", _steps())


def test_chain_signature_is_canonical_and_round_trippable() -> None:
    """The canonical chain reduces each step to op/params/seed."""
    signature = chain_signature(_steps())
    assert signature == [
        {"op": "M3", "params": {"mode": "graft", "donor": "d"}, "seed": 0},
        {"op": "M2", "params": {}, "seed": 1},
    ]


def test_load_outcomes_missing_file_is_empty(tmp_path: Path) -> None:
    """A missing ledger loads as an empty map (fresh checkout, design 6.3)."""
    assert load_outcomes(tmp_path / "nope.jsonl") == {}


def test_append_then_load_round_trips(tmp_path: Path) -> None:
    """A recorded attempt is read back by its signature and outcome."""
    path = ledger_path(tmp_path)
    record = AttemptRecord(
        attempt_sig="sig-1",
        parent_slug="p",
        parent_sha256="h",
        cell={"band": "8-11", "length": "short", "style": "prose"},
        chain=chain_signature(_steps()),
        outcome=OUTCOME_HELD,
        failing_stage=None,
        discard_reason="",
        distances={"parent_distance": 0.3, "min_in_cell_distance": 0.4},
        timestamp="2026-07-21T00:00:00+00:00",
        template_set_version=TEMPLATE_SET_VERSION,
    )
    append_record(path, record)
    assert load_outcomes(path) == {"sig-1": OUTCOME_HELD}


def test_load_outcomes_skips_a_malformed_line(tmp_path: Path) -> None:
    """A corrupt (interrupted) line is skipped, never fatal (design 6.3)."""
    path = ledger_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    good = (
        '{"attempt_sig": "ok", "outcome": "promotable"}\n'
        "this is not json\n"
        '{"attempt_sig": "ok2", "outcome": "discarded"}\n'
    )
    _ = path.write_text(good, encoding="utf-8")
    assert load_outcomes(path) == {"ok": OUTCOME_PROMOTABLE, "ok2": OUTCOME_DISCARDED}


def test_load_outcomes_last_write_wins(tmp_path: Path) -> None:
    """A later record for a signature supersedes an earlier one (shelved re-record)."""
    path = ledger_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (
        '{"attempt_sig": "s", "outcome": "held"}\n'
        '{"attempt_sig": "s", "outcome": "shelved"}\n'
    )
    _ = path.write_text(lines, encoding="utf-8")
    assert load_outcomes(path) == {"s": "shelved"}


def test_append_record_rejects_an_unknown_outcome(tmp_path: Path) -> None:
    """A corrupt outcome never enters the append-only log (design 6.3)."""
    path = ledger_path(tmp_path)
    record = AttemptRecord(
        attempt_sig="s",
        parent_slug="p",
        parent_sha256="h",
        cell={"band": "8-11", "length": "short", "style": "prose"},
        chain=[],
        outcome="bogus",
        failing_stage=None,
        discard_reason="",
        distances={},
        timestamp="2026-07-21T00:00:00+00:00",
        template_set_version=TEMPLATE_SET_VERSION,
    )
    with pytest.raises(ValueError, match="unknown ledger outcome"):
        append_record(path, record)


def test_ledger_path_is_under_gitignored_out(tmp_path: Path) -> None:
    """The ledger lives under out/mutations/_ledger (scratch, design 6.3)."""
    path = ledger_path(tmp_path)
    assert path == tmp_path / "out" / "mutations" / "_ledger" / "attempts.jsonl"


def test_append_then_load_records_carries_the_template_set_version(
    tmp_path: Path,
) -> None:
    """The template-set generation survives the JSON round trip.

    Without this, a bump of ``TEMPLATE_SET_VERSION`` would leave rows written
    under the old and new operator sequences indistinguishable, which is the
    interpretability the constant's own comment claims and previously did not
    deliver (nothing read the constant).
    """
    path = ledger_path(tmp_path)
    record = AttemptRecord(
        attempt_sig="sig-v",
        parent_slug="p",
        parent_sha256="h",
        cell={"band": "8-11", "length": "short", "style": "prose"},
        chain=chain_signature(_steps()),
        outcome=OUTCOME_HELD,
        failing_stage=None,
        discard_reason="",
        distances={},
        timestamp="2026-07-31T00:00:00+00:00",
        template_set_version=7,
    )
    append_record(path, record)

    loaded = load_records(path)
    assert [r.template_set_version for r in loaded] == [7]


def test_load_records_defaults_a_pre_field_row_to_generation_one(
    tmp_path: Path,
) -> None:
    """A row written before ``template_set_version`` existed reads back as 1.

    Not a guess: any such row predates the field, hence predates any bump of
    TEMPLATE_SET_VERSION, hence belongs to generation 1 by construction. This
    is why the reader's fallback is a frozen historical constant and must never
    be replaced with an import of the live TEMPLATE_SET_VERSION.
    """
    path = ledger_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = (
        '{"attempt_sig": "old", "parent_slug": "p", "parent_sha256": "h", '
        '"cell": {}, "chain": [], "outcome": "held", "failing_stage": null, '
        '"discard_reason": "", "distances": {}, '
        '"timestamp": "2026-07-01T00:00:00+00:00"}\n'
    )
    _ = path.write_text(legacy, encoding="utf-8")

    loaded = load_records(path)
    assert [r.template_set_version for r in loaded] == [1]


def test_load_records_defaults_a_junk_template_set_version(tmp_path: Path) -> None:
    """A hand-edited non-int version degrades rather than dropping the row.

    Matches every other optional field in ``_coerce_record``: the D7 report
    reads this ledger, so one bad line must not blind the funnel.
    """
    path = ledger_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    junk = (
        '{"attempt_sig": "j", "parent_slug": "p", "parent_sha256": "h", '
        '"cell": {}, "chain": [], "outcome": "held", "failing_stage": null, '
        '"discard_reason": "", "distances": {}, '
        '"timestamp": "2026-07-01T00:00:00+00:00", '
        '"template_set_version": "two"}\n'
    )
    _ = path.write_text(junk, encoding="utf-8")

    loaded = load_records(path)
    assert len(loaded) == 1
    assert loaded[0].template_set_version == 1
