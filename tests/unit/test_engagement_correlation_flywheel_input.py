"""The flywheel input derived from the ADR-030 artifact.

Acceptance for this task is that a flywheel strategy input is *demonstrably*
derived, so every test here runs the whole chain: observations -> the job's own
``build_artifact`` -> the derivation -> ``eligible_parents`` over the real
catalog, and asserts on what the strategy returns. Nothing here asserts that a
set was passed somewhere, which is the shape a wiring-only test would take and
which would pass against a strategy that ignored the argument.

Each behavioural test is stated as a pair. The low-completion case alone is
satisfied by a derivation that excludes everything, and the high-completion case
alone is satisfied by one that excludes nothing; only together do they show the
strategy's output is a function of the artifact's content.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.analysis.engagement_correlation import (
    SUPPRESSION_MARKER,
    StorybookObservations,
    build_artifact,
)
from cyo_adventure.analysis.flywheel_input import (
    LOW_COMPLETION_CEILING,
    excluded_parent_slugs,
    low_completion_storybook_ids,
)
from cyo_adventure.flywheel.strategy import (
    Cell,
    eligible_parents,
    load_catalog,
    plan_attempts,
)

if TYPE_CHECKING:
    from cyo_adventure.flywheel import strategy

pytestmark = pytest.mark.unit

_STORYBOOK_ID = "3f7a1c9e-0000-4000-8000-000000000001"


def _entry_cell(entry: strategy.CatalogEntry) -> Cell:
    """Return the cell an entry belongs to.

    Args:
        entry: A catalog entry.

    Returns:
        Cell: Its band/length/style coordinate.
    """
    meta = entry.metadata
    return Cell(
        band=meta.age_band.value,
        length=meta.length.value if meta.length is not None else "n/a",
        style=meta.narrative_style.value,
    )


def _an_eligible_parent() -> tuple[strategy.Catalog, strategy.CatalogEntry, Cell]:
    """Return a real catalog entry that is eligible in its own cell.

    Picking the subject from the strategy's own output rather than naming a slug
    keeps the test honest if the catalog changes: an entry the strategy already
    refuses for some other reason could not show an exclusion working.

    Returns:
        tuple: The catalog, the entry, and its cell.
    """
    catalog = load_catalog()
    for entry in catalog.entries:
        cell = _entry_cell(entry)
        if entry.slug in {e.slug for e in eligible_parents(cell, catalog)}:
            return catalog, entry, cell
    pytest.fail("the real catalog has no entry eligible in its own cell")


def _a_planned_parent() -> tuple[strategy.Catalog, strategy.CatalogEntry, Cell]:
    """Return a catalog entry the planner actually plans an attempt against.

    ``plan_attempts`` caps at ``MAX_ATTEMPTS_PER_CELL``, so merely being
    eligible does not put an entry in the plan. Choosing the subject from the
    plan's own output is what keeps the exclusion assertion meaningful.

    Returns:
        tuple: The catalog, the entry, and its cell.
    """
    catalog = load_catalog()
    for entry in catalog.entries:
        cell = _entry_cell(entry)
        if entry.slug in {p.parent_slug for p in plan_attempts(cell, catalog, {})}:
            return catalog, entry, cell
    pytest.fail("the real catalog yields no planned parent in its own cell")


def _observations(*, readers: int, completers: int) -> StorybookObservations:
    """Build one published, catalog-visible storybook's observations.

    Args:
        readers: How many families read it.
        completers: How many of them completed it.

    Returns:
        StorybookObservations: The observations.
    """
    families = frozenset(f"family-{index:02d}" for index in range(readers))
    return StorybookObservations(
        storybook_id=_STORYBOOK_ID,
        visibility="catalog",
        is_personalized=False,
        status="published",
        current_published_version=2,
        engagement_verdict="advisory",
        reader_families=families,
        completed_families=frozenset(sorted(families)[:completers]),
        returned_families=frozenset(),
        rating_by_family={},
        flag_families_by_reason={},
    )


class TestExclusionDerivation:
    """The strategy's parent pool changes as a function of the artifact."""

    def test_a_low_completion_row_excludes_its_parent_slug(self) -> None:
        """One family in eight finishing it: the strategy stops offering the shell.

        The whole chain runs here, so a break anywhere in it fails this test:
        the job's aggregation, its rounding, the ceiling comparison, the slug
        map, and the strategy's use of ``excluded_parent_slugs``.
        """
        catalog, entry, cell = _an_eligible_parent()
        artifact = build_artifact([_observations(readers=8, completers=1)])
        excluded = excluded_parent_slugs(artifact, {_STORYBOOK_ID: entry.slug})

        assert excluded == frozenset({entry.slug})
        eligible = {e.slug for e in eligible_parents(cell, catalog)}
        withheld = {
            e.slug
            for e in eligible_parents(cell, catalog, excluded_parent_slugs=excluded)
        }
        assert entry.slug in eligible
        assert entry.slug not in withheld

    def test_a_high_completion_row_leaves_its_parent_slug_eligible(self) -> None:
        """The discriminating half of the pair.

        Same book, same slug map, same code path; only the reading outcome
        differs. Without this, a derivation that returned every slug in the map
        would pass the exclusion test above.
        """
        catalog, entry, cell = _an_eligible_parent()
        artifact = build_artifact([_observations(readers=8, completers=7)])
        excluded = excluded_parent_slugs(artifact, {_STORYBOOK_ID: entry.slug})

        assert excluded == frozenset()
        withheld = {
            e.slug
            for e in eligible_parents(cell, catalog, excluded_parent_slugs=excluded)
        }
        assert entry.slug in withheld

    def test_the_ceiling_is_inclusive_and_the_book_just_above_it_survives(
        self,
    ) -> None:
        """A rounded 0.35 excludes; a rounded 0.40 does not.

        Pins the comparison direction and the boundary together, which a single
        far-from-the-boundary case does not.
        """
        assert LOW_COMPLETION_CEILING == 0.35
        at_ceiling = build_artifact([_observations(readers=20, completers=7)])
        above = build_artifact([_observations(readers=20, completers=8)])
        assert low_completion_storybook_ids(at_ceiling) == frozenset({_STORYBOOK_ID})
        assert low_completion_storybook_ids(above) == frozenset()

    def test_a_book_below_the_family_floor_excludes_nothing(self) -> None:
        """A privacy suppression must not become a catalog decision.

        Four families is under ADR-030's floor, so the book produces no row at
        all. The derivation must read that as "no evidence", not as "no
        completions".
        """
        catalog, entry, cell = _an_eligible_parent()
        artifact = build_artifact([_observations(readers=4, completers=0)])
        assert artifact["rows"] == []
        excluded = excluded_parent_slugs(artifact, {_STORYBOOK_ID: entry.slug})
        assert excluded == frozenset()
        withheld = {
            e.slug
            for e in eligible_parents(cell, catalog, excluded_parent_slugs=excluded)
        }
        assert entry.slug in withheld

    def test_a_suppressed_completion_cell_is_read_as_unknown_and_not_as_zero(
        self,
    ) -> None:
        """The reader-side contract for the marker.

        Today ``build_artifact`` suppresses ``completion_rate`` only for a book
        it also withholds entirely, so this case cannot arise from the current
        writer. It is asserted anyway because the derivation reads a file that a
        later writer produces, and a marker string compared numerically or
        coerced to zero would silently retire shells on a privacy suppression.
        """
        document: dict[str, object] = {
            "schema_version": 1,
            "rows": [
                {
                    "storybook_id": _STORYBOOK_ID,
                    "completion_rate": SUPPRESSION_MARKER,
                }
            ],
        }
        assert low_completion_storybook_ids(document) == frozenset()

    def test_a_storybook_absent_from_the_slug_map_excludes_nothing(self) -> None:
        """The map is the caller's, and an unmapped book is not a wildcard."""
        artifact = build_artifact([_observations(readers=8, completers=0)])
        assert low_completion_storybook_ids(artifact) == frozenset({_STORYBOOK_ID})
        assert excluded_parent_slugs(artifact, {}) == frozenset()
        assert (
            excluded_parent_slugs(artifact, {"other-book": "some-slug"}) == frozenset()
        )

    def test_a_malformed_artifact_degrades_to_no_exclusions(self) -> None:
        """A bad file must not stop a catalog-growth run or empty the pool."""
        for document in (
            {},
            {"rows": None},
            {"rows": "not-a-list"},
            {"rows": [None, 3, "row"]},
            {"rows": [{"storybook_id": 7, "completion_rate": 0.0}]},
        ):
            assert low_completion_storybook_ids(document) == frozenset()

    def test_a_boolean_completion_rate_is_not_treated_as_a_number(self) -> None:
        """``False <= 0.35`` is True in Python; a bool is not a rate."""
        document: dict[str, object] = {
            "rows": [{"storybook_id": _STORYBOOK_ID, "completion_rate": False}]
        }
        assert low_completion_storybook_ids(document) == frozenset()


class TestThroughPlanAttempts:
    """The same exclusion, reaching the strategy through its planner."""

    def test_plan_attempts_stops_planning_against_an_excluded_parent(self) -> None:
        """``plan_attempts`` is the entry point a scheduler calls, not ``eligible_parents``.

        Proving the input at the lower seam alone would leave open that the
        planner never forwards it.
        """
        catalog, entry, cell = _a_planned_parent()
        artifact = build_artifact([_observations(readers=8, completers=1)])
        excluded = excluded_parent_slugs(artifact, {_STORYBOOK_ID: entry.slug})

        without = plan_attempts(cell, catalog, {})
        with_exclusion = plan_attempts(
            cell, catalog, {}, excluded_parent_slugs=excluded
        )
        assert entry.slug in {plan.parent_slug for plan in without}
        assert entry.slug not in {plan.parent_slug for plan in with_exclusion}


class TestObservationsAreUnchangedByTheDerivation:
    """The derivation reads the artifact and nothing else."""

    def test_the_derivation_never_reaches_past_the_artifact_to_the_observations(
        self,
    ) -> None:
        """Two books identical in the artifact derive identically.

        The observations carry family identifiers the artifact does not. If the
        derivation ever reached back to them, these two would differ.
        """
        base = _observations(readers=8, completers=1)
        other = replace(
            base,
            reader_families=frozenset(f"other-{i:02d}" for i in range(8)),
            completed_families=frozenset({"other-00"}),
        )
        assert low_completion_storybook_ids(
            build_artifact([base])
        ) == low_completion_storybook_ids(build_artifact([other]))
