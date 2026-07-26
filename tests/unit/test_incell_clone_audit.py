"""The in-cell clone audit gate (A8).

Covers the properties that make this a gate rather than a report: it loads its
floor instead of hardcoding one, it refuses a permissive default, its allowlist
can only shrink, and it counts each pair exactly once.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.diversity.incell import (
    ALLOWLIST,
    FLOOR_BASELINE,
    PairDistance,
    audit,
    iter_incell_pairs,
    load_tau_cell,
)

if TYPE_CHECKING:
    from pathlib import Path

_CLONE_PAIR = ("the-harrowstone-keep", "the-sunken-temple")


@pytest.fixture(scope="module")
def pairs() -> list[PairDistance]:
    """Measure the committed catalog once for the whole module."""
    return list(iter_incell_pairs())


def test_tau_cell_is_loaded_from_the_committed_baseline() -> None:
    """The floor must track the baseline, not a literal in the audit."""
    baseline = cast(
        "dict[str, object]", json.loads(FLOOR_BASELINE.read_text(encoding="utf-8"))
    )
    expected = baseline["tau_cell"]
    assert isinstance(expected, float)
    assert load_tau_cell() == pytest.approx(expected)


def test_missing_baseline_raises_rather_than_defaulting(tmp_path: Path) -> None:
    """A missing floor must not silently become a permissive default."""
    with pytest.raises(ConfigurationError):
        load_tau_cell(tmp_path / "absent.json")


def test_non_numeric_tau_cell_raises(tmp_path: Path) -> None:
    """A malformed baseline must fail loudly, not coerce."""
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"tau_cell": "0.05"}), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_tau_cell(path)


def test_committed_catalog_passes_the_gate(pairs: list[PairDistance]) -> None:
    """The catalog is clean today, with the known duplicate allowlisted."""
    assert len(pairs) > 0
    assert audit(pairs, load_tau_cell()) == []


def test_exactly_one_pair_breaches_the_floor(pairs: list[PairDistance]) -> None:
    """Pins the measurement the threshold decision rests on.

    The decision to gate at TAU_CELL rather than TAU_STRUCT was justified on the
    failing set being exactly the one pair A9 already resolves. If this count
    changes, story-diversity-plan-v2.md section 6 needs re-examining.
    """
    tau_cell = load_tau_cell()
    breaching = [pair for pair in pairs if pair.distance < tau_cell]
    assert [pair.key for pair in breaching] == [_CLONE_PAIR]


def test_lower_band_pairs_are_not_double_counted(pairs: list[PairDistance]) -> None:
    """Narrative style partitions a cell only at 13-16 and 16+.

    Below those bands ``skeleton_matches_cell`` ignores style, so both styles
    return the same candidate list. Without deduplication every lower-band pair
    is measured twice, which inflates the pair count and reports any finding
    twice.
    """
    keys = [pair.key for pair in pairs]
    assert len(keys) == len(set(keys)), "each pair must be measured exactly once"


def test_a_non_style_partitioned_cell_is_labelled_as_such(
    pairs: list[PairDistance],
) -> None:
    """A deduplicated cell says both styles matched, rather than picking one."""
    labels = {pair.cell for pair in pairs}
    assert any("gamebook+prose" in label for label in labels)


def test_an_unallowlisted_breach_is_a_finding() -> None:
    """A new clone must block, not warn."""
    clone = PairDistance(
        distance=0.001, cell="8-11/medium/prose", slug_a="alpha", slug_b="beta"
    )
    findings = audit([clone], 0.05, allowlist={})
    assert len(findings) == 1
    assert "IN-CELL CLONE" in findings[0]


def test_stale_allowlist_entry_is_a_finding() -> None:
    """A fixed pair must be deleted from the allowlist in the same change.

    This is what keeps the allowlist a shrinking debt register rather than a
    permanent exemption regime.
    """
    passing = PairDistance(
        distance=0.9, cell="8-11/medium/prose", slug_a="alpha", slug_b="beta"
    )
    findings = audit([passing], 0.05, allowlist={("alpha", "beta"): "not a breach"})
    assert len(findings) == 1
    assert "STALE ALLOWLIST ENTRY" in findings[0]


def test_allowlisted_breach_is_not_a_finding() -> None:
    """An allowlisted breach passes while it is still tracked."""
    breach = PairDistance(
        distance=0.001, cell="8-11/medium/prose", slug_a="alpha", slug_b="beta"
    )
    assert audit([breach], 0.05, allowlist={("alpha", "beta"): "tracked"}) == []


def test_the_real_allowlist_names_only_the_known_clone_pair() -> None:
    """Guards against the allowlist quietly accumulating entries."""
    assert set(ALLOWLIST) == {_CLONE_PAIR}
