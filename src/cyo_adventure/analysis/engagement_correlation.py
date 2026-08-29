"""ADR-030 engagement-correlation core: cohort gating, suppression, and emit.

The pure half of the C3 analysis job. It takes per-storybook observations that a
caller has already read out of the database (``queries.py`` holds the
read-allowlisted statements) and returns the artifact document, applying every
control ADR-030 decides:

- the 5-distinct-family floor, counted over families and not child profiles, and
  binding **every emitted signal over its own contributing population** rather
  than only the row (Decision 1);
- the two categorical exclusions that do not depend on any count, ``visibility =
  'family'`` and a non-null ``personalization_subject_profile_id`` (Decision 2);
- the closed emit allowlist, the stated rounding, and the single suppression
  marker form (Decision 3);
- no total, count, or summary spanning more than one storybook (Decision 3).

**Nothing here is operator-configurable.** :data:`MIN_FAMILIES` is a module
constant with no environment variable and no settings field, per Decision 1:
lowering it is a code change, a review, and an amendment to ADR-030, in that
order.

Two places where this module is deliberately narrower than ADR-030's emit
allowlist, both because Decision 4's read allowlist does not admit the input the
field would need:

- ``age_band`` is allowlisted for emission and is described as coming from "the
  request that produced it or from the Storybook blob's declared band". Neither
  ``storybook_version.blob`` nor any request table is in the read allowlist, so
  the field is not emitted and is not in :data:`EMIT_ALLOWLIST` either. Adding it
  needs the read allowlist widened first.
- no skeleton slug is read or emitted, which is why
  :mod:`cyo_adventure.analysis.flywheel_input` takes the storybook-to-slug map
  from its caller rather than from the artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Final, NoReturn, cast, final

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# --- Decision 1: the threshold, not operator-configurable ---

# #CRITICAL: security: the minimum-cohort floor. A per-storybook aggregate over
# fewer than this many distinct FAMILIES can be re-identified by any adult in
# the cohort, who knows their own household's contribution exactly. Counted over
# families and never over child profiles: siblings are one household's data.
# Lowering this is an ADR-030 Decision 1 amendment, not a code edit.
# #VERIFY: tests/unit/test_engagement_correlation.py::TestCohortFloor::
# test_four_families_are_excluded_and_five_are_included.
MIN_FAMILIES: Final = 5

# The three ``kid_flag.reason`` values, mirroring the DB CHECK vocabulary
# (``db/models.py::_KID_FLAG_REASON_VALUES``). Closed: a reason outside this set
# is dropped rather than emitted, so a schema addition cannot widen the artifact
# without a deliberate edit here.
FLAG_REASONS: Final = ("did_not_like", "scared_me", "confusing")

# The storybook lifecycle state and visibility value this job cares about,
# mirroring ``db/models.py::_STORYBOOK_STATUS_VALUES`` / ``_VISIBILITY_VALUES``.
PUBLISHED_STATUS: Final = "published"
FAMILY_VISIBILITY: Final = "family"

# The closed set of Stage-4 verdict values this job will emit (ADR-030 Decision
# 3). Stage 4 never gates, so ``advisory`` and ``pass`` are the two values it
# produces; anything else in a stored report is treated as no judgment rather
# than emitted, so the field cannot widen because a stage changed behaviour.
ENGAGEMENT_VERDICTS: Final = ("advisory", "pass")

# The moderation stage whose engagement advisory this job correlates.
_ENGAGEMENT_STAGE: Final = 4

# Decision 3's stated rounding, as exact decimal steps.
_RATE_STEP: Final = "0.05"
_RATING_STEP: Final = "0.1"

# The single published bucket edge (Decision 3): below it "5-9", at or above
# it "10+". Never the exact count.
_BAND_EDGE: Final = 10


@final
class SuppressedCell:
    """The single form a suppressed cell takes: never null, zero, or absent.

    Decision 3 requires one explicit marker, and Decision 5 requires it to span
    the whole 0-to-4 range so a book nobody flagged is indistinguishable from a
    book four families flagged. The consumer must treat it as **unknown**.

    ``__bool__`` raises rather than answering. This repository has already paid
    for a tri-state whose two falsy arms collapsed into one benign branch at a
    single ``if not x:``; a marker that cannot be truth-tested makes that
    collapse a runtime error at the point it is written instead of a silent
    misreading in production.
    """

    __slots__ = ()

    def __bool__(self) -> NoReturn:
        """Refuse truth-testing, which is how a tri-state collapses.

        Raises:
            TypeError: always. Compare against :data:`SUPPRESSED` with ``is``,
                or call :func:`is_suppressed`.
        """
        msg = (
            "A suppressed engagement cell has no truth value: it means "
            "'unknown', not 'zero' and not 'false'. Use is_suppressed(cell)."
        )
        raise TypeError(msg)

    def __repr__(self) -> str:
        """Return the debugging representation.

        Returns:
            str: The sentinel's name.
        """
        return "SUPPRESSED"


SUPPRESSED: Final = SuppressedCell()

# What a suppressed cell serialises to. Decision 5's ``<5`` form, used for every
# suppressed signal so the artifact has exactly one marker to recognise.
SUPPRESSION_MARKER: Final = "<5"


def is_suppressed(cell: object) -> bool:
    """Return whether a cell is the suppression marker.

    Args:
        cell: A cell value from a :class:`StorybookRow`.

    Returns:
        bool: True when the cell is :data:`SUPPRESSED`.
    """
    return isinstance(cell, SuppressedCell)


# --- Decision 3: the closed emit allowlist ---

# #CRITICAL: security: the closed set of keys a row may carry (ADR-030 Decision
# 3). Hand-maintained here as a mirror of that table and deliberately NOT
# derived from :func:`row_to_json`, so a field added to the serialiser fails the
# allowlist test by default rather than passing by omission.
# #VERIFY: tests/unit/test_engagement_correlation.py::TestEmitAllowlist::
# test_a_serialised_row_carries_no_field_outside_the_allowlist.
EMIT_ALLOWLIST: Final = frozenset(
    {
        "storybook_id",
        "engagement_verdict",
        "completion_rate",
        "return_read_rate",
        "rating_mean",
        "flag_counts",
        "reader_family_band",
        "rater_family_band",
        "flagger_family_band",
    }
)

# The artifact's envelope. Two keys, neither of them a count: Decision 3 forbids
# any total, corpus-wide count, summary row, or count of storybooks considered,
# included, or excluded, and that prohibition is what makes per-cell suppression
# sufficient without complementary suppression.
ARTIFACT_ENVELOPE_KEYS: Final = frozenset({"schema_version", "rows"})
ARTIFACT_SCHEMA_VERSION: Final = 1


@dataclass(frozen=True, slots=True)
class StorybookObservations:
    """One storybook's inputs, already reduced to family-grain sets.

    The reader resolves every child identifier to a ``family_id`` before
    building one of these, so no child profile id, device id, guardian id, or
    ``kid_flag.node_id`` reaches this module at all.

    Attributes:
        storybook_id: The ``storybook.id`` value.
        visibility: The ``storybook.visibility`` value.
        is_personalized: Whether ``personalization_subject_profile_id`` is set.
        status: The ``storybook.status`` value.
        current_published_version: The published version, or None.
        engagement_verdict: The Stage-4 verdict (``advisory`` or ``pass``), or
            None when the stored moderation report carries no Stage-4 judgment.
        reader_families: Families with an observed read of the published
            version.
        completed_families: Families with at least one completion.
        returned_families: Families with a completion on a later calendar date
            than their first.
        rating_by_family: Rating values contributed, keyed by family.
        flag_families_by_reason: Flagging families, keyed by ``kid_flag.reason``.
    """

    storybook_id: str
    visibility: str
    is_personalized: bool
    status: str
    current_published_version: int | None
    engagement_verdict: str | None
    reader_families: frozenset[str]
    completed_families: frozenset[str]
    returned_families: frozenset[str]
    rating_by_family: Mapping[str, tuple[int, ...]]
    flag_families_by_reason: Mapping[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class StorybookRow:
    """One emitted row, before serialisation.

    Every cell is either a value or :data:`SUPPRESSED`; there is no null and no
    omitted key, so a consumer never has to distinguish "absent" from "hidden".

    Attributes:
        storybook_id: The book's own identifier, not any person's.
        engagement_verdict: The Stage-4 verdict, or None when unjudged.
        completion_rate: Completing families over reader families.
        return_read_rate: Returning families over reader families.
        rating_mean: Mean of each rating family's own mean.
        flag_counts: Flagging families per reason, or the whole-cell marker.
        reader_family_band: Bucketed reader-family count.
        rater_family_band: Bucketed rating-family count.
        flagger_family_band: Bucketed flagging-family count.
    """

    storybook_id: str
    engagement_verdict: str | None
    completion_rate: float | SuppressedCell
    return_read_rate: float | SuppressedCell
    rating_mean: float | SuppressedCell
    flag_counts: Mapping[str, int | SuppressedCell] | SuppressedCell
    reader_family_band: str | SuppressedCell
    rater_family_band: str | SuppressedCell
    flagger_family_band: str | SuppressedCell


def _round_to(value: float, step: str) -> float:
    """Round a value to a decimal step, half away from zero.

    Args:
        value: The unrounded value.
        step: The decimal step as a string, e.g. ``"0.05"``.

    Returns:
        float: The rounded value.
    """
    quantum = Decimal(step)
    scaled = (Decimal(value) / quantum).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return float(scaled * quantum)


def family_band(count: int) -> str | SuppressedCell:
    """Return the bucketed contributing-family count Decision 3 allows.

    Never the exact count and never a raw denominator: a count of 1 beside a
    mean recovers the value, so only ``5-9`` and ``10+`` are publishable, and a
    population below the floor carries the suppression marker along with the
    signal it describes.

    Args:
        count: The distinct contributing-family count.

    Returns:
        str | SuppressedCell: ``"5-9"``, ``"10+"``, or :data:`SUPPRESSED`.
    """
    if count < MIN_FAMILIES:
        return SUPPRESSED
    return "5-9" if count < _BAND_EDGE else "10+"


def is_eligible(observations: StorybookObservations) -> bool:
    """Return whether a storybook may appear in the artifact at all.

    Applies ADR-030 Decision 2's two categorical exclusions before any
    aggregation, then Decision 1's reader-cohort floor. The categorical
    exclusions are checked first and independently: their predicate is a column
    value rather than a computed cardinality, so their correctness does not
    depend on the cohort count being computed correctly.

    Args:
        observations: The storybook's observations.

    Returns:
        bool: True when the storybook is included in the output.
    """
    if observations.visibility == FAMILY_VISIBILITY:
        return False
    if observations.is_personalized:
        return False
    if observations.status != PUBLISHED_STATUS:
        return False
    if observations.current_published_version is None:
        return False
    return len(observations.reader_families) >= MIN_FAMILIES


def _rating_mean(rating_by_family: Mapping[str, tuple[int, ...]]) -> float:
    """Return the mean rating at family grain.

    Each family contributes one value, its own mean, so a household with five
    children cannot outweigh four single-child households in a figure whose
    whole point is cross-family reach.

    Args:
        rating_by_family: Rating values keyed by family.

    Returns:
        float: The unrounded mean of the per-family means.
    """
    per_family = [
        sum(values) / len(values) for values in rating_by_family.values() if values
    ]
    return sum(per_family) / len(per_family)


def _flag_cell(
    flag_families_by_reason: Mapping[str, frozenset[str]],
) -> tuple[Mapping[str, int | SuppressedCell] | SuppressedCell, str | SuppressedCell]:
    """Return the flag cell and its family band.

    Two floors, because ADR-030 states one in each of two places and the
    conservative implementation applies both. Decision 5 gates the whole cell on
    at least 5 distinct flagging families over the union of reasons, folding 0
    through 4 into one marker so a book nobody flagged reads the same as a book
    four families flagged. Decision 3 additionally requires the floor to be
    re-applied at any leaf cell a breakdown dimension produces, and ``reason``
    is such a dimension, so a reason below the floor is suppressed inside an
    otherwise published cell.

    Counts are of distinct FAMILIES per reason, never of flags: five flags from
    one household are one household's data.

    Args:
        flag_families_by_reason: Flagging families keyed by reason.

    Returns:
        tuple: The flag cell (a per-reason mapping or the whole-cell marker) and
            the bucketed flagging-family count.
    """
    union: set[str] = set()
    for reason in FLAG_REASONS:
        union |= flag_families_by_reason.get(reason, frozenset())
    if len(union) < MIN_FAMILIES:
        return SUPPRESSED, SUPPRESSED
    counts: dict[str, int | SuppressedCell] = {}
    for reason in FLAG_REASONS:
        families = len(flag_families_by_reason.get(reason, frozenset()))
        counts[reason] = families if families >= MIN_FAMILIES else SUPPRESSED
    return counts, family_band(len(union))


def build_row(observations: StorybookObservations) -> StorybookRow:
    """Build one storybook's row, suppressing each signal on its own population.

    Clearing the reader-cohort gate is not a licence for any cell in the row: a
    book read by 5 families and rated by 1 publishes no rating, because the
    published mean would be exactly one child's ``rating.value``.

    Args:
        observations: The storybook's observations. Callers pass only rows that
            :func:`is_eligible` accepted.

    Returns:
        StorybookRow: The row, with every under-floor signal suppressed.
    """
    readers = observations.reader_families
    reader_count = len(readers)
    if reader_count >= MIN_FAMILIES:
        completed = len(observations.completed_families & readers)
        returned = len(observations.returned_families & readers)
        completion: float | SuppressedCell = _round_to(
            completed / reader_count, _RATE_STEP
        )
        returning: float | SuppressedCell = _round_to(
            returned / reader_count, _RATE_STEP
        )
    else:
        completion = SUPPRESSED
        returning = SUPPRESSED

    raters = observations.rating_by_family
    if len(raters) >= MIN_FAMILIES:
        rating: float | SuppressedCell = _round_to(_rating_mean(raters), _RATING_STEP)
    else:
        rating = SUPPRESSED

    flag_counts, flagger_band = _flag_cell(observations.flag_families_by_reason)

    return StorybookRow(
        storybook_id=observations.storybook_id,
        engagement_verdict=observations.engagement_verdict,
        completion_rate=completion,
        return_read_rate=returning,
        rating_mean=rating,
        flag_counts=flag_counts,
        reader_family_band=family_band(reader_count),
        rater_family_band=family_band(len(raters)),
        flagger_family_band=flagger_band,
    )


def _cell(value: object) -> object:
    """Serialise one cell, folding the sentinel into its published marker.

    Args:
        value: A cell value.

    Returns:
        object: The marker string for a suppressed cell, else the value.
    """
    return SUPPRESSION_MARKER if is_suppressed(value) else value


def row_to_json(row: StorybookRow) -> dict[str, object]:
    """Serialise one row to its JSON mapping.

    Written out key by key on purpose. Deriving this from
    :data:`EMIT_ALLOWLIST` would make the allowlist test unable to fail: the
    serialiser would agree with the allowlist by construction, whatever either
    one said. The allowlist is the independent declaration this is checked
    against.

    Args:
        row: The row to serialise.

    Returns:
        dict[str, object]: The row's JSON mapping.
    """
    flags = row.flag_counts
    # isinstance rather than is_suppressed: the narrowing is what keeps the
    # mapping branch typed, and a helper call does not narrow.
    if isinstance(flags, SuppressedCell):
        flag_counts: object = SUPPRESSION_MARKER
    else:
        flag_counts = {reason: _cell(value) for reason, value in flags.items()}
    return {
        "storybook_id": row.storybook_id,
        "engagement_verdict": row.engagement_verdict,
        "completion_rate": _cell(row.completion_rate),
        "return_read_rate": _cell(row.return_read_rate),
        "rating_mean": _cell(row.rating_mean),
        "flag_counts": flag_counts,
        "reader_family_band": _cell(row.reader_family_band),
        "rater_family_band": _cell(row.rater_family_band),
        "flagger_family_band": _cell(row.flagger_family_band),
    }


def build_artifact(
    observations: Iterable[StorybookObservations],
) -> dict[str, object]:
    """Build the whole artifact document.

    The envelope carries a schema version and the rows and nothing else. There
    is no grand total, no corpus-wide count, and no count of how many storybooks
    were considered, included, or excluded: a suppressed cell is recoverable by
    subtraction only if some published figure includes it, and no published
    figure spans books.

    Args:
        observations: One entry per candidate storybook, in any order.

    Returns:
        dict[str, object]: The artifact document, ready to serialise as JSON.
    """
    rows = [
        row_to_json(build_row(entry)) for entry in observations if is_eligible(entry)
    ]
    return {"schema_version": ARTIFACT_SCHEMA_VERSION, "rows": rows}


def _as_mapping(value: object) -> Mapping[str, object] | None:
    """Return a JSON object as a typed mapping, or None.

    Args:
        value: Any decoded JSON value.

    Returns:
        Mapping[str, object] | None: The mapping, or None when not one.
    """
    return cast("Mapping[str, object]", value) if isinstance(value, dict) else None


def stage_four_verdict(report: object) -> str | None:
    """Extract the Stage-4 engagement verdict from a stored moderation report.

    ADR-030 Decision 4 admits ``storybook_version.moderation_report``, the
    ``stage: 4`` entry only, and Decision 3 emits its ``Verdict`` value while
    denying its ``message``: the message is LLM-authored free text, and an
    allowlist whose whole purpose is that a row's contents can be enumerated is
    defeated by one unbounded field. It is also the field an agent would most
    naturally quote into a summary, which Decision 6 forbids. Only the verdict
    is read here; the message is never touched.

    A clean engagement pass is not stored as a finding: ``ModerationReport``
    aggregates PASS findings into ``aggregate.pass_counts`` keyed by category
    (``moderation/report.py::to_dict``). Decision 3 names ``pass`` as an
    emittable value, so the pass aggregate for the ``engagement`` category is
    the only place that value can come from, and it is read for that one key.

    Args:
        report: The stored ``moderation_report`` payload, of any shape.

    Returns:
        str | None: ``"advisory"``, ``"pass"``, or None when the stored report
            carries no Stage-4 engagement judgment.
    """
    stored = _as_mapping(report)
    if stored is None:
        return None
    findings = stored.get("findings")
    if isinstance(findings, list):
        for entry in cast("list[object]", findings):
            finding = _as_mapping(entry)
            if finding is None or finding.get("stage") != _ENGAGEMENT_STAGE:
                continue
            verdict = finding.get("verdict")
            if isinstance(verdict, str) and verdict in ENGAGEMENT_VERDICTS:
                return verdict
    aggregate = _as_mapping(stored.get("aggregate"))
    if aggregate is None:
        return None
    pass_counts = _as_mapping(aggregate.get("pass_counts"))
    if pass_counts is None:
        return None
    engagement = pass_counts.get("engagement")
    if isinstance(engagement, bool) or not isinstance(engagement, int):
        return None
    return "pass" if engagement >= 1 else None
