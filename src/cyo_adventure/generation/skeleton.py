"""Skeleton loading utilities for structurally-valid Storybook shells.

A skeleton is a Storybook shell whose node bodies (ending nodes included)
carry a ``<<FILL ...>>`` directive to be replaced by prose.

The shell is validated through the existing gate's blocking layers (structure,
references, reachability, termination, budget) at load time, so a skeleton can
never introduce a structural defect; the fill step only writes prose.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from cyo_adventure.validator.gate import GateResult

FILL_MARKER = "<<FILL"

# The sidecar filename suffixes that live next to a ``<slug>.json`` skeleton in a
# band directory but are NOT themselves selectable skeletons: the WS-2 theme
# contract (``<slug>.contract.json``) and the WS-5 lineage record
# (``<slug>.lineage.json``, ADR-020 decision 2 / OQ-1). Every catalog scan that
# globs ``*.json`` must skip these, so the set is defined once here and a future
# sidecar type is a single edit. Ordered longest-suffix-first is unnecessary; a
# sidecar name ends in exactly one of these.
SIDECAR_SUFFIXES: tuple[str, ...] = (
    ".contract.json",
    ".lineage.json",
    # Narrative obligation contract (skeleton-narrative-redesign proposal,
    # 2026-08-09): per-node obligations for open-tier nodes. Registered ahead
    # of the SQ-12 pilot so catalog scans never load it as a skeleton, the
    # exact trap the SQ-11 brief flagged for variant sidecars.
    ".narrative.json",
)


def is_sidecar(path: Path) -> bool:
    """Return whether a catalog path is a sidecar rather than a skeleton.

    A sidecar (a theme contract or a lineage record) shares the ``*.json`` glob
    and the band directory with the skeleton it annotates, but carries no
    ``id``/``nodes`` and must never be treated as a selectable skeleton. This is
    the single predicate every catalog scanner uses in place of an inline
    ``endswith(".contract.json")`` check (design 8, ADR-020 decision 2).

    Args:
        path: The catalog file path to classify.

    Returns:
        bool: True when ``path`` is a known sidecar, False for a skeleton.
    """
    return any(path.name.endswith(suffix) for suffix in SIDECAR_SUFFIXES)


def load_skeleton(
    path: Path,
    *,
    enforce_grammar: bool = False,
    report_sink: Callable[[GateResult], None] | None = None,
) -> dict[str, object]:
    """Load a skeleton JSON file and assert it is a structurally-valid shell.

    Args:
        path: Path to the skeleton JSON.
        enforce_grammar: Forwarded to :func:`run_gate` so an authoring caller
            (``scripts/check_skeleton.py --strict``) can opt a new skeleton
            into the CG-1..CG-4 choice-grammar checks. Defaults to ``False``
            so every existing caller is unaffected (UW-C24).
        report_sink: Optional callback that receives the full
            :class:`GateResult` before any block decision is taken. Without
            it this loader silently discarded every advisory finding (PL-19
            story mean, PL-20 arc ceiling, PL-23..PL-26, L1-7 below-min,
            L2-13, RL-13), so authoring tools printed ``ok`` for skeletons
            the gate had warned about; 40 of the 61 catalog skeletons
            carried such hidden advisories (2026-08-09 review, section 2.2).

    Returns:
        The decoded skeleton as a dict.

    Raises:
        ValidationError: If the skeleton fails the gate's blocking (L1/L2) layers.
    """
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    result = run_gate(data, enforce_grammar=enforce_grammar)
    if report_sink is not None:
        report_sink(result)
    if result.blocked:
        messages = (
            "; ".join(f.message for f in result.report.errors)
            or "no error details available"
        )
        msg = f"skeleton {path} failed structural validation: {messages}"
        raise ValidationError(msg)
    return data


def is_production_eligible(story: dict[str, object]) -> bool:
    """Return whether a skeleton may be selected for a child-facing story.

    A skeleton is production-eligible unless its metadata explicitly sets
    ``production_eligible`` to ``False`` (the MVP/Test tier; see ADR-011).
    Production story selection must exclude non-eligible skeletons; the gate
    still accepts them (against the band-independent MVP node envelope) so they
    remain usable for prototyping and pipeline testing.

    Args:
        story: The decoded skeleton dict.

    Returns:
        ``True`` unless ``metadata.production_eligible`` is explicitly ``False``.
    """
    # #CRITICAL: security: this gate decides whether a skeleton is offered to a
    # child; malformed or absent metadata defaults to eligible (the permissive
    # direction), and the raw ``is not False`` test treats a JSON string "false" as
    # eligible. A production selector MUST call this on already-schema-validated
    # metadata (StoryMetadata.production_eligible: bool), not on arbitrary raw JSON.
    # #VERIFY: production story selection screens skeletons through the Pydantic
    # StoryMetadata model before calling this, so production_eligible is a real bool.
    meta = story.get("metadata")
    if not isinstance(meta, dict):
        return True
    return meta.get("production_eligible") is not False


def has_unfilled_directives(story: dict[str, object]) -> bool:
    """Return True if any node body still contains a ``<<FILL``-prefixed directive."""
    nodes = story.get("nodes")
    if not isinstance(nodes, list):
        return False
    return any(
        isinstance(n, dict)
        and isinstance(n.get("body"), str)
        and FILL_MARKER in n["body"]
        for n in nodes
    )
