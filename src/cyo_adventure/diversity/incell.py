"""In-cell clone audit over the hand-authored skeleton catalog (diversity/incell.py).

Two skeletons in the same ``(band, length, style)`` cell are what a reader is
actually choosing between: ``select_skeleton_for_cell`` picks from exactly that
set, so a duplicate tree inside one cell is the cheapest possible way for a
reader's second story to feel like their first. This module measures every
in-cell pair against the committed ``TAU_CELL`` floor and reports breaches.

Why ``structural_distance`` and not ``structure_fingerprint``: the fingerprint is
node-id sensitive and cannot see a renamed clone. The known duplicate pair
differs on 355 of its 550 node ids while being graph-isomorphic, so the
fingerprint reports the two as unequal and only the distance catches them.

Why ``TAU_CELL`` and not ``TAU_STRUCT``:

- ``TAU_CELL`` (0.05) is the anti-duplication floor. ADR-020's
  floor-recalibration amendment fixes it as an owner-chosen constant, and
  ``ws5_floor_baseline.json``'s own ``clamps`` entry records that it was set to
  reject "the observed same-cell minimum pair at 0.000947 with margin", which is
  this very pair. So the audit enforces an intent the baseline already states.
- ``TAU_STRUCT`` (0.298321 as of the 2026-08-19 recalibration; this said
  0.332507 until then, and the value moves whenever the catalog grows because
  it is derived as a percentile of it) is **documentation only** as of that
  same amendment
  ("No longer gates mutants"). Measured over the committed catalog it would fail
  17 of 67 in-cell pairs across 12 of 18 populated cells, which is the
  whole-class failure that PR #416's AL-051 lesson says to read as a wrong
  threshold rather than a wrong corpus.

Unlike its sibling modules this one reads the ``skeletons/`` tree, because the
committed catalog is the thing under audit. It still imports no ``db``,
``generation`` model, or ``sqlalchemy``: ``skeleton_match`` is used only for cell
enumeration and path resolution.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, cast

from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.diversity.normalize import coerce_storybook
from cyo_adventure.diversity.structure import structural_distance
from cyo_adventure.generation.skeleton_match import (
    candidates_for_cell,
    resolve_skeleton_path,
)
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from cyo_adventure.storybook.models import Storybook

FLOOR_BASELINE = Path("docs/planning/ws5_floor_baseline.json")

# Pairs known to sit below TAU_CELL, each with the item that resolves it. A debt
# register, not an exemption regime: :func:`audit` reports a stale entry as a
# finding, so a fixed pair must be deleted here in the same change. It can only
# shrink.
#
# #CRITICAL: data integrity: an allowlist that never shrinks silently converts a
# blocking gate into a report. The stale-entry finding is what prevents that.
# #VERIFY: tests/unit/test_incell_clone_audit.py::test_stale_allowlist_entry_fails
ALLOWLIST: Mapping[tuple[str, str], str] = {
    ("the-harrowstone-keep", "the-sunken-temple"): (
        "A9: brass-lantern books 1 and 2 are structural twins. Measured "
        "2026-07-26: every `structure_features` field is identical (550 nodes, "
        "152 endings, 801 choices, max_depth 58, same ending-kind and valence "
        "histograms, same topology) except `n_effects`, 49 vs 48. Their PROSE is "
        "not duplicated: 1326 of 1503 slotted surfaces differ, and the "
        "`structure_fingerprint`s are unequal, so this is a re-skinned skeleton, "
        "not a copied story. The defect is therefore shape, not text, and the "
        "resolution is to restructure book 2 while keeping its prose rather than "
        "to replace it. Bound by ADR-011 section 8's series-retirement addendum, "
        "so retire-one is unavailable regardless."
    ),
}


class PairDistance(NamedTuple):
    """One in-cell skeleton pair and its structural distance.

    Attributes:
        distance: ``structural_distance`` between the two skeletons.
        cell: The ``band/length/style`` cell label. Style is joined with ``+``
            when the cell is not style-partitioned at this band.
        slug_a: The alphabetically first slug.
        slug_b: The alphabetically second slug.
    """

    distance: float
    cell: str
    slug_a: str
    slug_b: str

    @property
    def key(self) -> tuple[str, str]:
        """Return the order-independent allowlist key."""
        return (self.slug_a, self.slug_b)


def load_tau_cell(path: Path = FLOOR_BASELINE) -> float:
    """Return the committed ``TAU_CELL`` anti-duplication floor.

    Args:
        path: The floor-baseline JSON.

    Returns:
        float: The ``tau_cell`` value.

    Raises:
        ConfigurationError: If the baseline is missing, unparseable, or has no
            numeric ``tau_cell``. Never falls back to a default, since a
            permissive default would silently disable the gate.
    """
    if not path.exists():
        msg = f"floor baseline not found at {path}"
        raise ConfigurationError(msg)
    raw = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        msg = f"{path} is not a JSON object"
        raise ConfigurationError(msg)
    baseline = cast("dict[str, object]", raw)
    tau = baseline.get("tau_cell")
    # `bool` is an `int` subclass, so a stray `true` would otherwise coerce to 1.0
    # and set an absurdly permissive floor.
    if not isinstance(tau, (int, float)) or isinstance(tau, bool):
        msg = f"{path} has no numeric 'tau_cell'"
        raise ConfigurationError(msg)
    return float(tau)


def _load_skeleton(band: str, slug: str, cache: dict[str, Storybook]) -> Storybook:
    """Load and cache one skeleton by band and slug."""
    if slug not in cache:
        path = resolve_skeleton_path(band, slug)
        blob = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        cache[slug] = coerce_storybook(blob)
    return cache[slug]


def iter_incell_pairs() -> Iterator[PairDistance]:
    """Yield every in-cell hand-authored pair with its structural distance.

    A cell holding fewer than two production-eligible skeletons yields nothing:
    there is no pair to compare, and an empty cell is A10's concern.

    Yields:
        PairDistance: One entry per distinct in-cell pair, in matrix order.
    """
    cache: dict[str, Storybook] = {}
    for band in AgeBand:
        for length in Length:
            # #ASSUME: data integrity: narrative style partitions a cell only at
            # the style-aware bands (13-16 and 16+). Below those,
            # skeleton_matches_cell ignores style, so both styles return the
            # same candidate list and a naive style loop measures every
            # lower-band pair twice, inflating the pair count and reporting any
            # finding twice. Deduplicating on the candidate list fixes both and
            # lets the cell label state when style did not partition.
            # #VERIFY: tests/unit/test_incell_clone_audit.py::
            # test_lower_band_pairs_are_not_double_counted
            #
            # #CRITICAL: data integrity: the audit measures continuations that
            # generation selection deliberately excludes (AL-045). A book 2 is
            # never *drawn* for a cell, but if it re-skins book 1 it is still a
            # near-duplicate tree a series reader meets, so it must stay in the
            # catalog-quality measurement. Passing include_continuations=True
            # keeps the audit independent of the selection filter; without it a
            # book-2 re-skin would silently drop out of the gate and the #415
            # allowlist entry that tracks it would read as stale.
            # #VERIFY: tests/unit/test_incell_clone_audit.py::
            # test_exactly_one_pair_breaches_the_floor
            by_slugs: dict[tuple[str, ...], list[str]] = {}
            for style in NarrativeStyle:
                slugs = tuple(
                    candidates_for_cell(
                        band.value,
                        length.value,
                        style.value,
                        include_continuations=True,
                    )
                )
                if len(slugs) < 2:
                    continue
                by_slugs.setdefault(slugs, []).append(style.value)

            for slugs, styles in by_slugs.items():
                label = styles[0] if len(styles) == 1 else "+".join(sorted(styles))
                for slug_a, slug_b in itertools.combinations(sorted(slugs), 2):
                    yield PairDistance(
                        distance=structural_distance(
                            _load_skeleton(band.value, slug_a, cache),
                            _load_skeleton(band.value, slug_b, cache),
                        ),
                        cell=f"{band.value}/{length.value}/{label}",
                        slug_a=slug_a,
                        slug_b=slug_b,
                    )


def audit(
    pairs: list[PairDistance],
    tau_cell: float,
    allowlist: Mapping[tuple[str, str], str] = ALLOWLIST,
) -> list[str]:
    """Return every finding for a measured catalog.

    Args:
        pairs: Every in-cell pair with its distance.
        tau_cell: The loaded anti-duplication floor.
        allowlist: Known breaches mapped to the item that resolves each.

    Returns:
        list[str]: One human-readable finding per unallowlisted breach and per
            stale allowlist entry. Empty when the catalog is clean.
    """
    breaching = {pair.key for pair in pairs if pair.distance < tau_cell}
    findings: list[str] = []

    for pair in sorted(pairs):
        if pair.distance >= tau_cell or pair.key in allowlist:
            continue
        findings.append(
            " ".join(
                [
                    f"IN-CELL CLONE: {pair.slug_a} vs {pair.slug_b} in {pair.cell}",
                    f"at structural_distance {pair.distance:.5f} <",
                    f"tau_cell {tau_cell}.",
                    "Two skeletons this close in one cell are one tree to a reader.",
                    "Resolve per the catalog-disposition principle (repair or",
                    "replace), or add an ALLOWLIST entry naming the item that will.",
                ]
            )
        )

    for key, reason in sorted(allowlist.items()):
        if key in breaching:
            continue
        findings.append(
            " ".join(
                [
                    f"STALE ALLOWLIST ENTRY: {key[0]} vs {key[1]} no longer breaches",
                    f"tau_cell {tau_cell}.",
                    "Delete it from ALLOWLIST. It was recorded as:",
                    reason,
                ]
            )
        )

    return findings
