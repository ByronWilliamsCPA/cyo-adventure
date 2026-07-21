"""The re-guidance resolution flow (WS-5 D8, design sections 4.5 / 6 stage 3).

D2-D7 leave every accepted mutant *held*: a structural or state operator changes
the context a seam's entry beat or a choice label describes, so those surfaces
carry :class:`~cyo_adventure.mutation.ops.ReguideItem` records and the mutant is
not promotable while any is unresolved. D8 closes the loop: an author supplies
resolved guidance (new beats / labels) for each emitted item, the resolutions are
recorded in the bundle's ``reguide.json``, and their ``target_id`` values feed
``run_acceptance(..., resolved_reguide_ids=...)`` so a fully-resolved mutant
becomes would-be-promotable and then faces the D7 anti-clone floor.

Resolution text is author-attributed: every :class:`ResolvedReguide` carries a
mandatory ``author``. Under WS-8 (OQ-1 ratified, design 5.4) a resolution may be
agent-drafted rather than hand-authored; an agent-drafted resolution is
floor-screened, untrusted-derived content that MUST be human-reviewed in the
promotion PR, and it is attributed ``author="agent:<model-id>"`` so the audit
trail distinguishes drafted from hand-authored resolutions forever. This module
stays generation-free: it only models, loads, and reconciles resolutions against
the emitted items and never generates guidance text itself. The drafting and its
deterministic reguide floor live in :mod:`cyo_adventure.flywheel.reguide_draft`,
which feeds screened :class:`ResolvedReguide` values in (OWASP LLM01: the drafting
prompt consumes catalog content only, and its output faces the floor, the full
acceptance re-run, and human PR approval before it can reach the catalog).

Pure module: standard library plus Pydantic and the ``mutation.ops`` value types.
Deterministic: reconciliation is a pure function of the emitted items and the
resolution file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from cyo_adventure.mutation.ops import ReguideTarget

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from cyo_adventure.mutation.ops import ReguideItem


class ResolvedReguide(BaseModel):
    """One author-supplied resolution for an emitted re-guidance item.

    Attributes:
        target: The kind of surface resolved (node beats, choice label, ending
            title), matching the emitted item's ``target``.
        target_id: The node / choice / ending id the resolution addresses; this
            is the key that reconciles against the emitted items and feeds
            ``resolved_reguide_ids``.
        resolved_text: The new author-written guidance (beats / label / title).
        author: Who authored the resolution (audit and reviewer context).
        note: An optional rationale recorded alongside the resolution.
    """

    model_config = ConfigDict(extra="forbid")

    target: ReguideTarget
    target_id: str = Field(min_length=1)
    resolved_text: str = Field(min_length=1)
    author: str = Field(min_length=1)
    note: str = ""


class ReguideResolutions(BaseModel):
    """An author's resolution file for one mutant's re-guidance items.

    The documented resolution-file format: a JSON object with an optional
    ``mutant_slug`` and a ``resolutions`` list of :class:`ResolvedReguide`. It is
    loaded with :func:`load_resolutions` and passed to :func:`reconcile`.

    Attributes:
        mutant_slug: The mutant the resolutions target (advisory; not enforced
            against the bundle so a resolution file can be drafted before the
            slug is final).
        resolutions: One entry per resolved re-guidance target.
    """

    model_config = ConfigDict(extra="forbid")

    mutant_slug: str = ""
    resolutions: list[ResolvedReguide] = Field(default_factory=list)


# The empty resolution set, as a module constant so it is not a call in a
# parameter default (basedpyright reportCallInDefaultInitializer).
_NO_RESOLUTIONS: ReguideResolutions = ReguideResolutions(resolutions=[])


def load_resolutions(path: Path) -> ReguideResolutions:
    """Load and validate an author resolution file.

    Args:
        path: The resolution JSON file path.

    Returns:
        ReguideResolutions: The validated resolutions.

    Raises:
        OSError: If the file cannot be read.
        pydantic.ValidationError: If the file is not a valid resolution document.
    """
    return ReguideResolutions.model_validate_json(path.read_text(encoding="utf-8"))


def resolved_ids(resolutions: ReguideResolutions) -> frozenset[str]:
    """Return the set of ``target_id`` values the resolutions cover.

    This is the value passed as ``run_acceptance(..., resolved_reguide_ids=...)``:
    an emitted item whose ``target_id`` is in this set is treated as resolved and
    no longer holds the mutant back from promotability.

    Args:
        resolutions: The author resolutions.

    Returns:
        frozenset[str]: The resolved target ids.
    """
    return frozenset(item.target_id for item in resolutions.resolutions)


def unresolved_targets(
    emitted: Sequence[ReguideItem], resolutions: ReguideResolutions
) -> list[str]:
    """Return the emitted target ids that no resolution covers, in emit order.

    Args:
        emitted: The re-guidance items the operator chain emitted.
        resolutions: The author resolutions.

    Returns:
        list[str]: The still-outstanding target ids (deduplicated, emit-ordered).
    """
    covered = resolved_ids(resolutions)
    seen: set[str] = set()
    outstanding: list[str] = []
    for item in emitted:
        if item.target_id in covered or item.target_id in seen:
            continue
        seen.add(item.target_id)
        outstanding.append(item.target_id)
    return outstanding


def reconcile(
    emitted: Sequence[ReguideItem],
    resolutions: ReguideResolutions = _NO_RESOLUTIONS,
) -> dict[str, object]:
    """Return the serialized ``reguide.json`` document (design 9.2).

    Reconciles each emitted item against the author resolutions by ``target_id``,
    producing a per-item before/after record and a summary. A fully-resolved
    mutant has ``fully_resolved`` true and an empty ``outstanding`` list, which is
    exactly the condition (via ``resolved_reguide_ids``) that lets acceptance mark
    it promotable.

    Args:
        emitted: The re-guidance items the operator chain emitted.
        resolutions: The author resolutions (defaults to none resolved).

    Returns:
        dict[str, object]: The ``reguide.json`` content.
    """
    by_id = {item.target_id: item for item in resolutions.resolutions}
    items: list[dict[str, object]] = []
    for emitted_item in emitted:
        resolution = by_id.get(emitted_item.target_id)
        items.append(
            {
                "target": str(emitted_item.target),
                "target_id": emitted_item.target_id,
                "reason": emitted_item.reason,
                "before": emitted_item.current_text,
                "resolved": resolution is not None,
                "after": resolution.resolved_text if resolution is not None else None,
                "author": resolution.author if resolution is not None else None,
                "note": resolution.note if resolution is not None else None,
            }
        )
    outstanding = unresolved_targets(emitted, resolutions)
    return {
        "emitted_count": len(items),
        "resolved_count": len(items) - len(outstanding),
        "outstanding": outstanding,
        "fully_resolved": len(outstanding) == 0,
        "items": items,
    }
