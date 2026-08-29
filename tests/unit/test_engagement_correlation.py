"""ADR-030 privacy controls on the engagement-correlation job.

Every test here exists to fail when a control is removed, not merely to describe
one. Where a control has a plausible weaker implementation that a single test
would still pass against, the pair is stated explicitly in the test's docstring:
a threshold test that only checks the exclusion passes against an inverted
comparison, and a row-level cohort test passes against an implementation that
applies the gate exactly once and never reaches the per-signal floor.
"""

from __future__ import annotations

import json
import stat
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.analysis.engagement_correlation import (
    ARTIFACT_ENVELOPE_KEYS,
    EMIT_ALLOWLIST,
    FLAG_REASONS,
    MIN_FAMILIES,
    SUPPRESSED,
    SUPPRESSION_MARKER,
    StorybookObservations,
    _round_to,
    build_artifact,
    build_row,
    is_eligible,
    row_to_json,
    stage_four_verdict,
)
from scripts.engagement_correlation import (
    ARTIFACT_PREFIX,
    ARTIFACT_SUFFIX,
    RETAINED_RUNS,
    artifact_paths,
    prune_artifacts,
    write_artifact,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit


def _families(count: int, prefix: str = "family") -> frozenset[str]:
    """Return ``count`` distinct, recognisable family identifiers.

    Args:
        count: How many identifiers to mint.
        prefix: A prefix that makes them greppable in a serialised artifact.

    Returns:
        frozenset[str]: The identifiers.
    """
    return frozenset(f"{prefix}-{index:02d}-a1b2c3" for index in range(count))


def _observations(
    *,
    storybook_id: str = "book-alpha",
    visibility: str = "catalog",
    is_personalized: bool = False,
    status: str = "published",
    current_published_version: int | None = 3,
    engagement_verdict: str | None = "advisory",
    readers: int = 8,
    completers: int = 4,
    returners: int = 2,
    raters: int = 8,
    rating_value: int = 4,
    flaggers_by_reason: dict[str, int] | None = None,
) -> StorybookObservations:
    """Build one storybook's observations from counts.

    Args:
        storybook_id: The book's id.
        visibility: The ``storybook.visibility`` value.
        is_personalized: Whether the book is about a named child.
        status: The ``storybook.status`` value.
        current_published_version: The published version, or None.
        engagement_verdict: The Stage-4 verdict.
        readers: How many families read it.
        completers: How many of them completed it.
        returners: How many of them came back on a later day.
        raters: How many families rated it.
        rating_value: The value each rating family gave.
        flaggers_by_reason: Flagging-family counts keyed by reason.

    Returns:
        StorybookObservations: The observations.
    """
    reader_families = _families(readers)
    ordered = sorted(reader_families)
    flags = flaggers_by_reason or {}
    return StorybookObservations(
        storybook_id=storybook_id,
        visibility=visibility,
        is_personalized=is_personalized,
        status=status,
        current_published_version=current_published_version,
        engagement_verdict=engagement_verdict,
        reader_families=reader_families,
        completed_families=frozenset(ordered[:completers]),
        returned_families=frozenset(ordered[:returners]),
        rating_by_family=dict.fromkeys(
            sorted(_families(raters, "rater")), (rating_value,)
        ),
        flag_families_by_reason={
            reason: _families(count, f"flagger-{reason}")
            for reason, count in flags.items()
        },
    )


class TestCohortFloor:
    """ADR-030 Decision 1: 5 distinct families, counted over families."""

    def test_the_floor_is_five_families(self) -> None:
        """The integer itself, so a silent edit to 3 fails here first."""
        assert MIN_FAMILIES == 5

    def test_four_families_are_excluded_and_five_are_included(self) -> None:
        """Pins the integer and the comparison direction together.

        Cite the pair, not the exclusion alone: a test that only asserts the
        4-family book is absent passes against an inverted comparison, which
        would publish every book below the floor and suppress every book above
        it.
        """
        artifact = build_artifact(
            [
                _observations(storybook_id="book-four", readers=4, raters=0),
                _observations(storybook_id="book-five", readers=5, raters=0),
            ]
        )
        rows = artifact["rows"]
        assert isinstance(rows, list)
        published = {row["storybook_id"] for row in rows}
        assert published == {"book-five"}

    def test_a_book_below_the_floor_leaves_no_trace_at_all(self) -> None:
        """No row, no partial row, no null placeholder, no identifier anywhere."""
        artifact = build_artifact([_observations(storybook_id="book-tiny", readers=2)])
        assert artifact["rows"] == []
        assert "book-tiny" not in json.dumps(artifact)


class TestCategoricalExclusions:
    """ADR-030 Decision 2: both hold without depending on any count."""

    def test_a_family_visibility_book_is_excluded_at_any_cohort_size(self) -> None:
        """A reader ceiling of one household, whatever the count says."""
        observations = _observations(visibility="family", readers=40)
        assert is_eligible(observations) is False

    def test_a_personalized_book_is_excluded_at_any_cohort_size(self) -> None:
        """The book names the child it is about; no counting argument reaches it."""
        observations = _observations(is_personalized=True, readers=40)
        assert is_eligible(observations) is False

    def test_each_exclusion_fires_independently_of_the_other(self) -> None:
        """Neither exclusion is doing the other's work."""
        assert is_eligible(_observations(readers=40)) is True
        assert is_eligible(_observations(visibility="family", readers=40)) is False
        assert is_eligible(_observations(is_personalized=True, readers=40)) is False

    def test_an_unpublished_status_is_excluded_with_a_version_still_present(
        self,
    ) -> None:
        """Status alone, because in production it does arrive alone.

        Setting ``status`` and ``current_published_version`` in one fixture
        leaves each check individually deletable, which is the same shape as
        the dual-role tests this branch already fixed. The archived case is
        why it matters: archived is the only exit from published and it is
        absorbing, an archived book keeps its ``current_published_version``,
        and its historical ``reading_state`` rows survive. With the status
        check gone every archived book with 5+ reader families is emitted into
        the artifact and into the flywheel exclusion set, so a withdrawn book's
        engagement governs which shells get mutated.
        """
        assert (
            is_eligible(_observations(status="archived", current_published_version=3))
            is False
        )
        assert (
            is_eligible(_observations(status="in_review", current_published_version=3))
            is False
        )

    def test_a_missing_published_version_is_excluded_at_published_status(
        self,
    ) -> None:
        """Version alone, with ``published`` status still set.

        Version-scoped signals need a published version to be scoped to, and
        ``is_eligible`` is a public predicate that must hold that at its own
        boundary rather than leaning on the reducer mapping a null version to
        ``-1`` and the cohort floor catching the empty result downstream.
        """
        assert (
            is_eligible(
                _observations(status="published", current_published_version=None)
            )
            is False
        )


class TestPerSignalFloor:
    """ADR-030 Decision 1: the floor binds every signal on its own population."""

    def test_five_readers_and_one_rater_publish_the_row_without_the_rating(
        self,
    ) -> None:
        """The case a row-level-only implementation passes every test against.

        A book read by 5 families and rated by 1 satisfies every other rule in
        ADR-030, and its published rating mean would be exactly one child's
        ``rating.value``, an integer from 1 to 5.
        """
        row = row_to_json(build_row(_observations(readers=5, raters=1)))
        assert row["storybook_id"] == "book-alpha"
        assert row["completion_rate"] != SUPPRESSION_MARKER
        assert row["rating_mean"] == SUPPRESSION_MARKER

    def test_a_suppressed_signal_takes_its_family_band_with_it(self) -> None:
        """A band on a suppressed signal restates the population it withheld."""
        row = row_to_json(build_row(_observations(readers=5, raters=1)))
        assert row["rater_family_band"] == SUPPRESSION_MARKER
        assert row["reader_family_band"] == "5-9"

    def test_a_published_band_is_a_bucket_and_never_an_exact_count(self) -> None:
        """A count of 1 beside a mean recovers the value; buckets do not."""
        row = row_to_json(build_row(_observations(readers=7, raters=12)))
        assert row["reader_family_band"] == "5-9"
        assert row["rater_family_band"] == "10+"

    def test_a_completer_outside_the_reader_cohort_is_not_in_the_numerator(
        self,
    ) -> None:
        """The rate's numerator is intersected with its own denominator.

        Every other fixture in this file builds ``completed_families`` and
        ``returned_families`` as slices of the reader set, so the intersection
        in :func:`build_row` is a no-op in all of them and is deletable with
        the suite green. Here two families have a completion but no
        ``reading_state`` row for this (book, version), which is reachable
        today: offline sync writes completions on reconnect, and
        ``reading_state`` is a single row per (profile, book) that a republish
        or a cleanup can leave unmatched on version.

        Without the intersection this book publishes ``completion_rate`` 1.0
        rather than 0.6. That is nonsense in the artifact and, being at or
        above the ceiling, it silently exempts the parent shell from the
        flywheel exclusion it should have received.
        """
        base = _observations(readers=5, completers=3, returners=1, raters=0)
        ghosts = _families(2, "ghost")
        observations = replace(
            base,
            completed_families=base.completed_families | ghosts,
            returned_families=base.returned_families | ghosts,
        )
        row = row_to_json(build_row(observations))
        assert row["completion_rate"] == pytest.approx(0.6)
        assert row["return_read_rate"] == pytest.approx(0.2)


class TestFlagCell:
    """ADR-030 Decision 5: flags, folded so zero is not published."""

    def test_the_marker_is_the_same_at_zero_and_at_four_flagging_families(
        self,
    ) -> None:
        """Publishing zero as zero would disclose exactly what the marker hides.

        A marker used only for 1 to 4, with zero published as zero, publishes
        the predicate that at least one child flagged this book, which every
        guardian in the cohort who knows their own child did not flag it can
        read.
        """
        none_flagged = row_to_json(build_row(_observations(readers=8)))
        four_flagged = row_to_json(
            build_row(_observations(readers=8, flaggers_by_reason={"scared_me": 4}))
        )
        assert none_flagged["flag_counts"] == SUPPRESSION_MARKER
        assert four_flagged["flag_counts"] == SUPPRESSION_MARKER
        assert none_flagged["flag_counts"] == four_flagged["flag_counts"]
        assert none_flagged["flagger_family_band"] == SUPPRESSION_MARKER
        assert four_flagged["flagger_family_band"] == SUPPRESSION_MARKER

    def test_a_reason_below_the_floor_is_suppressed_inside_a_published_cell(
        self,
    ) -> None:
        """``reason`` is a breakdown dimension, so the floor re-applies at the leaf.

        Decision 3 requires the 5-family threshold at any leaf cell a breakdown
        produces; without this, a cell that clears Decision 5's union gate can
        still publish a per-reason count of one.
        """
        row = row_to_json(
            build_row(
                _observations(
                    readers=12,
                    flaggers_by_reason={"scared_me": 6, "confusing": 1},
                )
            )
        )
        counts = row["flag_counts"]
        assert isinstance(counts, dict)
        assert counts["scared_me"] == 6
        assert counts["confusing"] == SUPPRESSION_MARKER
        assert counts["did_not_like"] == SUPPRESSION_MARKER

    def test_the_cell_publishes_once_five_families_have_flagged(self) -> None:
        """The gate is on distinct flagging families over the union of reasons."""
        row = row_to_json(
            build_row(_observations(readers=12, flaggers_by_reason={"scared_me": 5}))
        )
        assert row["flag_counts"] != SUPPRESSION_MARKER
        assert row["flagger_family_band"] == "5-9"

    def test_a_reason_outside_the_closed_vocabulary_is_never_emitted(self) -> None:
        """The three CHECK-constrained reasons, and nothing a schema adds later."""
        widened = replace(
            _observations(readers=12),
            flag_families_by_reason={
                "scared_me": _families(6, "flag-a"),
                "self_harm_disclosure": _families(9, "flag-b"),
            },
        )
        counts = row_to_json(build_row(widened))["flag_counts"]
        assert isinstance(counts, dict)
        assert set(counts) == set(FLAG_REASONS)


class TestEmitAllowlist:
    """ADR-030 Decision 3: what the artifact may say is closed by default."""

    def test_a_serialised_row_carries_no_field_outside_the_allowlist(self) -> None:
        """Asserted against the allowlist, never against a forbidden-name list.

        A field added to the serialiser must fail by default rather than pass
        by omission, which is why this compares key sets rather than checking
        that a handful of known-bad names are absent.
        """
        row = row_to_json(build_row(_observations()))
        assert set(row) == EMIT_ALLOWLIST

    def test_the_stage_four_message_is_never_emitted(self) -> None:
        """LLM-authored free text defeats an allowlist whose point is enumerability."""
        report = {
            "findings": [
                {
                    "stage": 4,
                    "verdict": "advisory",
                    "message": "PROSE-THAT-MUST-NOT-BE-EMITTED",
                    "node_id": None,
                }
            ]
        }
        observations = _observations(engagement_verdict=stage_four_verdict(report))
        text = json.dumps(build_artifact([observations]))
        assert "advisory" in text
        assert "PROSE-THAT-MUST-NOT-BE-EMITTED" not in text

    def test_the_artifact_envelope_is_closed_too(self) -> None:
        """The envelope is two keys, neither of them a count."""
        artifact = build_artifact([_observations()])
        assert set(artifact) == ARTIFACT_ENVELOPE_KEYS


class TestNoIdentifierReachesTheArtifact:
    """ADR-030 Decisions 3 and 5: no person, and no passage, in any form."""

    def test_no_family_identifier_appears_in_a_serialised_artifact(self) -> None:
        """Not raw, not hashed, not truncated, not positional."""
        observations = _observations(readers=9, raters=9)
        text = json.dumps(build_artifact([observations]))
        for family in observations.reader_families | set(observations.rating_by_family):
            assert family not in text
            assert family.split("-")[-1] not in text

    def test_node_id_appears_nowhere_in_a_serialised_artifact(self) -> None:
        """A passage pointer is a level finer than the aggregate authorised."""
        text = json.dumps(
            build_artifact([_observations(flaggers_by_reason={"scared_me": 9})])
        )
        assert "node_id" not in text
        assert "node" not in text

    def test_the_job_never_holds_a_passage_or_person_field_at_all(self) -> None:
        """Structural: the input type carries no field the artifact must strip.

        The serialiser cannot leak what the reader never loaded. This fails if
        the observation type grows a node, profile, or device field, which is
        the change that would make a leak possible in the first place.
        """
        names = set(StorybookObservations.__dataclass_fields__)
        assert not {name for name in names if "node" in name or "device" in name}
        assert "profile_id" not in names


class TestNoTotalSpansMoreThanOneStorybook:
    """ADR-030 Decision 3: what makes per-cell suppression sufficient alone."""

    def test_the_artifact_carries_no_count_of_books_considered_or_excluded(
        self,
    ) -> None:
        """A suppressed cell is recoverable only if some published figure spans it."""
        included = [
            _observations(storybook_id=f"book-in-{index}", readers=8)
            for index in range(3)
        ]
        excluded = [
            _observations(storybook_id=f"book-out-{index}", readers=1)
            for index in range(7)
        ]
        artifact = build_artifact([*included, *excluded])
        rows = artifact["rows"]
        assert isinstance(rows, list)
        assert len(rows) == 3
        envelope = {key: value for key, value in artifact.items() if key != "rows"}
        assert envelope == {"schema_version": 1}
        assert 3 not in envelope.values()
        assert 7 not in envelope.values()
        assert 10 not in envelope.values()

    def test_every_row_names_exactly_one_storybook(self) -> None:
        """No summary row and no "all books" line hiding among the real ones."""
        artifact = build_artifact(
            [_observations(storybook_id=f"book-{index}") for index in range(4)]
        )
        rows = artifact["rows"]
        assert isinstance(rows, list)
        ids = [row["storybook_id"] for row in rows]
        assert sorted(ids) == ["book-0", "book-1", "book-2", "book-3"]


class TestRoundingAndGrain:
    """ADR-030 Decision 3: the stated rounding, computed at family grain."""

    def test_a_completion_rate_is_rounded_to_the_nearest_twentieth(self) -> None:
        """A full-precision rate reconstructs the denominator a bucket withholds."""
        row = build_row(_observations(readers=7, completers=3, returners=1))
        assert row.completion_rate == pytest.approx(0.45)
        assert row.return_read_rate == pytest.approx(0.15)

    def test_a_rating_mean_is_rounded_to_the_nearest_tenth(self) -> None:
        """The stated step for the rating aggregate."""
        rated = replace(
            _observations(readers=8, raters=0),
            rating_by_family={
                "fam-1": (5,),
                "fam-2": (4,),
                "fam-3": (4,),
                "fam-4": (3,),
                "fam-5": (5,),
                "fam-6": (4,),
                "fam-7": (4,),
            },
        )
        assert build_row(rated).rating_mean == pytest.approx(4.1)

    def test_a_halfway_rate_rounds_up_and_not_down(self) -> None:
        """The declared ROUND_HALF_UP must actually reach the halfway case.

        ``_round_to`` built its Decimal straight from the float, so the binary
        representation, not the decimal value, is what ``quantize`` saw.
        ``Decimal(0.075)`` is ``0.0749999...``: already below the midpoint
        before the rounding mode is consulted, so ROUND_HALF_UP was correct and
        unreachable. Both directions are asserted because the error is not a
        consistent bias, it is whichever side the binary expansion happens to
        land on, which is exactly why hand-picked cases miss it.
        """
        assert _round_to(3 / 40, "0.05") == pytest.approx(0.1)
        assert _round_to(7 / 40, "0.05") == pytest.approx(0.2)

    def test_a_non_halfway_rate_is_unchanged_by_the_halfway_fix(self) -> None:
        """The control: a ratio that already rounded correctly still does.

        ``1/40`` is 0.025, whose binary expansion happens to land ABOVE the
        midpoint, so it rounded up before the fix as well. Without this arm the
        pair above could be satisfied by an implementation that simply rounds
        every value up.
        """
        assert _round_to(1 / 40, "0.05") == pytest.approx(0.05)
        assert _round_to(0.024, "0.05") == pytest.approx(0.0)
        assert _round_to(0.26, "0.05") == pytest.approx(0.25)

    def test_a_halfway_completion_rate_reaches_the_published_row(self) -> None:
        """The unit fix has to be the one the artifact actually consumes.

        Three of forty reader families completing is 0.075 exactly. The row is
        what feeds ``flywheel_input``'s LOW_COMPLETION_CEILING decision, so a
        fix that stopped at the helper while the row kept its own path would
        change nothing that matters.
        """
        row = build_row(_observations(readers=40, completers=3, returners=7))
        assert row.completion_rate == pytest.approx(0.1)
        assert row.return_read_rate == pytest.approx(0.2)

    def test_a_rating_mean_weights_households_and_not_children(self) -> None:
        """One household of five children must not outweigh five households."""
        rated = replace(
            _observations(readers=9, raters=0),
            rating_by_family={
                "big-household": (1, 1, 1, 1, 1),
                "fam-2": (5,),
                "fam-3": (5,),
                "fam-4": (5,),
                "fam-5": (5,),
            },
        )
        # Flat over ratings this would be 2.6; at family grain it is 4.2.
        assert build_row(rated).rating_mean == pytest.approx(4.2)


class TestSuppressionMarker:
    """ADR-030 Decision 5: a third named value, not a falsy arm."""

    def test_a_suppressed_cell_refuses_truth_testing(self) -> None:
        """The tri-state collapse this repository has already paid for once."""
        cell = build_row(_observations(readers=5, raters=1)).rating_mean
        with pytest.raises(TypeError, match="no truth value"):
            _ = bool(cell)

    def test_every_suppressed_cell_serialises_to_one_marker(self) -> None:
        """One marker to recognise, never a null, a zero, or a missing key."""
        row = row_to_json(build_row(_observations(readers=5, raters=1)))
        assert row["rating_mean"] == SUPPRESSION_MARKER
        assert row["rater_family_band"] == SUPPRESSION_MARKER
        assert row["flag_counts"] == SUPPRESSION_MARKER
        assert None not in row.values()


class TestStageFourVerdict:
    """ADR-030 Decisions 3 and 4: the verdict, and only the verdict."""

    def test_an_advisory_finding_yields_advisory(self) -> None:
        """The persisted Stage-4 finding's verdict."""
        report = {"findings": [{"stage": 4, "verdict": "advisory", "message": "x"}]}
        assert stage_four_verdict(report) == "advisory"

    def test_a_pass_aggregate_yields_pass(self) -> None:
        """A clean engagement pass is aggregated, not stored as a finding."""
        report = {
            "findings": [{"stage": 1, "verdict": "flag"}],
            "aggregate": {"pass_counts": {"engagement": 1}},
        }
        assert stage_four_verdict(report) == "pass"

    def test_a_report_with_no_engagement_judgment_yields_none(self) -> None:
        """Absence stays absence rather than becoming a default verdict."""
        assert stage_four_verdict({"findings": [], "aggregate": {}}) is None
        assert stage_four_verdict(None) is None

    def test_a_verdict_outside_the_closed_set_is_not_emitted(self) -> None:
        """A stage that started gating must not widen this field silently."""
        report = {"findings": [{"stage": 4, "verdict": "block"}]}
        assert stage_four_verdict(report) is None

    def test_an_unrecognised_stage_four_verdict_does_not_fall_through_to_pass(
        self,
    ) -> None:
        """The laundering path, with both halves present at once.

        The pair matters: ``test_a_verdict_outside_the_closed_set_is_not_emitted``
        above passes against the pre-fix implementation too, because that report
        carries no ``pass_counts`` for the fall-through to reach. Only a report
        that has BOTH an unreadable stage-4 finding and an engagement pass count
        discriminates "the match is exhaustive" from "the loop just continued".
        """
        report = {
            "findings": [{"stage": 4, "verdict": "flag"}],
            "aggregate": {"pass_counts": {"engagement": 1}},
        }
        assert stage_four_verdict(report) is None

    def test_a_mock_reviewed_report_contributes_no_verdict(self) -> None:
        """A mock-reviewer run produced no judgment to correlate against.

        ``moderation_report_unusable`` already answers this question for the
        approval path; the correlation reads the same predicate rather than a
        paraphrase of it, so the two cannot drift.
        """
        report = {
            "summary": {"reviewer_independent": False},
            "aggregate": {"pass_counts": {"engagement": 1}},
        }
        assert stage_four_verdict(report) is None

    def test_an_unusable_report_cannot_contribute_an_advisory_either(self) -> None:
        """The gate is on the report, not on the value it would have emitted."""
        report = {
            "summary": {"reviewer_independent": False},
            "findings": [{"stage": 4, "verdict": "advisory"}],
        }
        assert stage_four_verdict(report) is None

    def test_a_genuine_report_still_yields_its_verdict(self) -> None:
        """The control. Without it, "return None always" passes every test above.

        Shaped as ``ModerationReport.to_dict`` writes a real independently
        reviewed report, so the unusable predicate accepts it.
        """
        report = {
            "findings": [{"stage": 4, "verdict": "advisory", "message": "x"}],
            "summary": {"reviewer_independent": True},
            "reviewer": {"provider": "anthropic"},
        }
        assert stage_four_verdict(report) == "advisory"

    def test_an_engagement_pass_count_of_zero_is_not_a_pass(self) -> None:
        """The ``>= 1`` boundary, which a surviving mutant proved untested.

        ``pass_counts`` is keyed by category and only carries a key when that
        category produced at least one PASS finding, but a writer that emits
        every category with a zero would make ``>= 0`` say "pass" for a book
        whose engagement stage passed nothing at all.
        """
        report = {
            "findings": [],
            "summary": {"reviewer_independent": True},
            "reviewer": {"provider": "anthropic"},
            "aggregate": {"pass_counts": {"engagement": 0}},
        }
        assert stage_four_verdict(report) is None

    def test_an_engagement_pass_count_of_one_is_a_pass(self) -> None:
        """The other side of the same boundary, so ``> 1`` fails here too."""
        report = {
            "findings": [],
            "summary": {"reviewer_independent": True},
            "reviewer": {"provider": "anthropic"},
            "aggregate": {"pass_counts": {"engagement": 1}},
        }
        assert stage_four_verdict(report) == "pass"


class TestRatingPopulation:
    """A family that contributed no rating value is not a rating family."""

    def test_five_families_that_rated_nothing_publish_no_rating(self) -> None:
        """The half-guard: the gate counted keys, the mean counted values.

        Five keys mapped to empty tuples cleared ``len(raters) >= MIN_FAMILIES``
        and then divided by an empty list inside ``_rating_mean``. Both halves
        must count the same population.
        """
        observations = replace(
            _observations(readers=8),
            rating_by_family=dict.fromkeys(sorted(_families(5, "rater")), ()),
        )
        row = build_row(observations)
        assert row.rating_mean is SUPPRESSED
        assert row.rater_family_band is SUPPRESSED

    def test_a_family_that_rated_nothing_does_not_count_toward_the_floor(
        self,
    ) -> None:
        """Four real raters plus one empty key is four, not five."""
        contributing = dict.fromkeys(sorted(_families(4, "rater")), (4,))
        observations = replace(
            _observations(readers=8),
            rating_by_family={**contributing, "rater-silent": ()},
        )
        row = build_row(observations)
        assert row.rating_mean is SUPPRESSED
        assert row.rater_family_band is SUPPRESSED

    def test_five_contributing_families_still_publish(self) -> None:
        """The control: the guard narrows the population, it does not close it."""
        observations = replace(
            _observations(readers=8),
            rating_by_family=dict.fromkeys(sorted(_families(5, "rater")), (4,)),
        )
        row = build_row(observations)
        assert row.rating_mean == pytest.approx(4.0)
        assert row.rater_family_band == "5-9"


class TestArtifactOnDisk:
    """ADR-030 Decision 6: who may read it, and how many runs survive."""

    def test_the_artifact_is_owner_only_inside_an_owner_only_directory(
        self, tmp_path: Path
    ) -> None:
        """No other account on the host has read access, and no copy is made."""
        target = tmp_path / "reports"
        path = write_artifact(target, build_artifact([_observations()]))
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(target.stat().st_mode) == 0o700

    def test_the_retention_window_is_two_runs(self) -> None:
        """The integer itself, so a silent widening fails here first.

        The behavioural test below asserts against ``RETAINED_RUNS`` imported
        from the subject, so the constant and its expectation move together and
        a window widened to 4 or 6 leaves that test green. ADR-030 Decision 6
        fixes the window at the current run and the one before it, and it is a
        privacy control over aggregated children's reading outcomes on disk, so
        the literal is what holds the commitment.
        """
        assert RETAINED_RUNS == 2

    def test_only_the_current_and_previous_runs_are_retained(
        self, tmp_path: Path
    ) -> None:
        """Two runs is enough to diff a run against its predecessor."""
        target = tmp_path / "reports"
        target.mkdir()
        for index in range(5):
            written = (
                target / f"{ARTIFACT_PREFIX}2026010{index}T000000Z{ARTIFACT_SUFFIX}"
            )
            _ = written.write_text("{}", encoding="utf-8")
        _ = write_artifact(target, build_artifact([]))
        assert len(artifact_paths(target)) == RETAINED_RUNS

    def test_turning_the_kill_switch_off_deletes_the_artifacts(
        self, tmp_path: Path
    ) -> None:
        """Deleted rather than orphaned, per Decision 6's retention rule."""
        target = tmp_path / "reports"
        _ = write_artifact(target, build_artifact([]))
        assert artifact_paths(target)
        assert prune_artifacts(target, keep=0) == 0
        assert artifact_paths(target) == []

    def test_a_purge_never_touches_a_file_this_job_did_not_write(
        self, tmp_path: Path
    ) -> None:
        """The purge is scoped to this job's own filename shape."""
        target = tmp_path / "reports"
        target.mkdir()
        bystander = target / "unrelated.json"
        _ = bystander.write_text("{}", encoding="utf-8")
        _ = write_artifact(target, build_artifact([]))
        _ = prune_artifacts(target, keep=0)
        assert bystander.exists()

    def test_the_written_document_round_trips_as_the_artifact(
        self, tmp_path: Path
    ) -> None:
        """The job produces a report: a real file with the real schema in it."""
        path = write_artifact(
            tmp_path / "reports", build_artifact([_observations(readers=6)])
        )
        document = json.loads(path.read_text(encoding="utf-8"))
        assert set(document) == ARTIFACT_ENVELOPE_KEYS
        assert document["schema_version"] == 1
        assert set(document["rows"][0]) == EMIT_ALLOWLIST
