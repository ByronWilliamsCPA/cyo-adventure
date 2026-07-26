"""Classify one fill result against the plan 3.4 failure taxonomy.

:func:`cyo_adventure.validator.sentinel_integrity.check_sentinel_integrity` is
the measurement oracle: given a pre-fill (sentinel-bearing) skeleton and a
filled blob, it returns every violation as a raw ``.kind`` string (``dropped``,
``forged``, ``migrated``, ``malformed``, ``in_choice_label``). Plan section 3.4
names a different, narrative taxonomy (dropped, duplicated, relocated,
mutated wrapper, mutated inner text). This module is the single explicit
mapping between the two, so the report stays auditable: every raw kind maps to
exactly one plan bucket, and an unmapped kind fails loudly rather than being
silently dropped from the histogram.

Pure: :func:`classify_fill` performs no I/O and is fully deterministic given
its two mapping inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.validator.sentinel_integrity import check_sentinel_integrity

if TYPE_CHECKING:
    from collections.abc import Mapping

# The canonical raw-kind -> plan-3.4-bucket mapping (brief-mandated, verbatim):
#
# - "dropped" -> "dropped": the sentinel never appears in the filled blob.
# - "forged" -> "mutated_wrapper_or_inner": a token present in the filled blob
#   that no pre-fill node declared is a corrupted or invented sentinel (the
#   wrapper, the inner value, or both were "improved" by the model).
# - "migrated" -> "relocated": right token, wrong node (the checker's own
#   stronger signal than a blind drop+forge pair).
# - "malformed" -> "mutated_wrapper": a sentinel-shaped near-miss (e.g. a
#   truncated `{~HERO:Ex` or a missing closing tilde) is the wrapper itself
#   being mutated.
# - "in_choice_label" -> "relocated_into_label": a well-formed sentinel
#   surfaced somewhere it must never appear at all.
_KIND_TO_BUCKET: dict[str, str] = {
    "dropped": "dropped",
    "forged": "mutated_wrapper_or_inner",
    "migrated": "relocated",
    "malformed": "mutated_wrapper",
    "in_choice_label": "relocated_into_label",
}


@dataclass(frozen=True, slots=True)
class ViolationRecord:
    """One classified sentinel-integrity violation.

    Attributes:
        node_id: The owning node id, or the checker's fixed location
            placeholder (``"<choice-label>"``); see
            :mod:`cyo_adventure.validator.sentinel_integrity`.
        raw_kind: The checker's own ``.kind`` value, kept verbatim for
            auditability.
        bucket: The plan 3.4 taxonomy bucket :data:`_KIND_TO_BUCKET` maps
            ``raw_kind`` onto.
        token: The offending sentinel token or near-miss text.
    """

    node_id: str
    raw_kind: str
    bucket: str
    token: str


@dataclass(frozen=True, slots=True)
class RunRecord:
    """The classified outcome of one fill attempt against one specimen.

    Attributes:
        clean: True only when the fill preserved every sentinel exactly (the
            checker's ``result.ok``); this is the first-attempt clean-pass
            signal plan 3.4 measures.
        violations: Every classified violation found, empty when ``clean`` is
            True.
    """

    clean: bool
    violations: tuple[ViolationRecord, ...]

    def raw_kind_counts(self) -> dict[str, int]:
        """Return a count of violations per raw checker ``.kind``.

        Returns:
            dict[str, int]: Counts keyed by raw kind, empty when clean.
        """
        counts: dict[str, int] = {}
        for violation in self.violations:
            counts[violation.raw_kind] = counts.get(violation.raw_kind, 0) + 1
        return counts

    def bucket_counts(self) -> dict[str, int]:
        """Return a count of violations per plan 3.4 taxonomy bucket.

        Returns:
            dict[str, int]: Counts keyed by bucket, empty when clean.
        """
        counts: dict[str, int] = {}
        for violation in self.violations:
            counts[violation.bucket] = counts.get(violation.bucket, 0) + 1
        return counts


def bucket_for(raw_kind: str) -> str:
    """Return the plan 3.4 bucket for one raw checker ``.kind`` value.

    Public (not module-private) so :mod:`cyo_adventure.measurement.report` can
    reuse this single canonical mapping when labeling its histogram, rather
    than re-deriving :data:`_KIND_TO_BUCKET`'s pairing.

    Args:
        raw_kind: The raw ``IntegrityViolation.kind`` value.

    Returns:
        str: The mapped bucket name.

    Raises:
        ValueError: If ``raw_kind`` is not a member of :data:`_KIND_TO_BUCKET`.
            This is deliberately fail-loud: a new checker violation kind must
            be explicitly mapped here, never silently excluded from the
            histogram.
    """
    try:
        return _KIND_TO_BUCKET[raw_kind]
    except KeyError as exc:
        msg = f"unmapped sentinel-integrity violation kind: {raw_kind!r}"
        raise ValueError(msg) from exc


def classify_fill(
    pre_fill_skeleton: Mapping[str, object],
    filled_blob: Mapping[str, object],
) -> RunRecord:
    """Classify one fill attempt's sentinel survival against the pre-fill reference.

    Args:
        pre_fill_skeleton: The sentinel-bearing bound skeleton the fill was
            given (a :class:`~cyo_adventure.measurement.fixtures.Specimen`'s
            ``bound_skeleton``).
        filled_blob: The fill's output document
            (:attr:`~cyo_adventure.generation.orchestrator.GenerationOutcome.storybook`).

    Returns:
        RunRecord: The classified outcome, carrying both the raw checker kind
            and the plan 3.4 bucket for every violation found.
    """
    result = check_sentinel_integrity(pre_fill_skeleton, filled_blob)
    violations = tuple(
        ViolationRecord(
            node_id=violation.node_id,
            raw_kind=violation.kind,
            bucket=bucket_for(violation.kind),
            token=violation.token,
        )
        for violation in result.violations
    )
    return RunRecord(clean=result.ok, violations=violations)
