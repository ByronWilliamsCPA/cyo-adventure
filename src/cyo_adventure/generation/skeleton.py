"""Skeleton loading utilities for structurally-valid Storybook shells.

A skeleton is a Storybook shell whose node bodies (ending nodes included)
carry a ``<<FILL ...>>`` directive to be replaced by prose.

The shell is validated through the existing gate's blocking layers (structure,
references, reachability, termination, budget) at load time, so a skeleton can
never introduce a structural defect; the fill step only writes prose.
"""

from __future__ import annotations

import json
import math
import re
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
        ValidationError: If any ERROR-severity finding in the gate's merged
            report has a ``rule_id`` starting with ``"CH"`` (character
            envelope, ADR-028), ``"L1"`` (Layer 1 graph structure, schema,
            and logic), ``"L2"`` (Layer 2 state-space walk), or ``"PL"``
            (policy: age-safety and shape invariants); see
            :func:`cyo_adventure.validator.gate.run_gate`'s blocking
            semantics.
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


# Output tokens the fill of one skeleton is expected to cost, per word of
# declared `words=` fill target. The completion is the whole filled JSON
# document, not just prose, so the ratio carries node ids, choice labels and
# structural scaffolding as well.
#
# Measured 2026-08-16 over all 31 committed filled books, using a chars/4 proxy
# against each book's own skeleton fill-word total: median 2.00, range 1.43 to
# 3.02. The ratio is highest on the smallest books (3.02 on the 682-word
# sleepy-little-star) because fixed JSON scaffolding is a larger share of a
# short document, and settles to 1.43-1.59 on the large books, which are the
# only ones that come near the cap. Cross-checked against AL-328's direct
# measurement of 6,054 completion tokens on a 5-8 skeleton, which implies 1.40
# to 2.33 for that band; the two methods agree.
# The output cap a one-shot fill runs under. Owned here rather than in the
# orchestrator so the feasibility screen and the call it screens for read one
# constant and cannot drift. Still 32,000: raising it is UW-C07's other half
# and is bounded by what a backend will emit in a single response, which is
# below what the largest skeletons need (~76,000).
MAX_FILL_OUTPUT_TOKENS = 32_000

_TOKENS_PER_FILL_WORD = 2.0

# Share of the output cap a fill may be expected to need before the skeleton is
# treated as infeasible. Not arbitrary: AL-328 measured claude-sonnet-5 at 91%
# of the 32,000-token cap across four briefs and it truncated on one of them, so
# a leg with under ~20% headroom is a coin toss rather than a working leg.
# Reasoning tokens make this worse and are invisible here, because they bill
# against the same budget and produce no prose (moonshotai/kimi-k3 spent 28,247
# of 32,000 thinking and returned nothing).
_FEASIBILITY_MARGIN = 0.8

_FILL_WORDS_RE = re.compile(r"\bwords=(\d+)")


def expected_output_tokens(story: dict[str, object]) -> int:
    """Return the output tokens a one-shot fill of *story* is expected to cost.

    Derived from the declared ``words=`` targets rather than from prose, so it
    is computable at selection time, before anything has been generated or paid
    for.

    Args:
        story: The decoded skeleton dict.

    Returns:
        int: Expected completion tokens for the whole filled document.
    """
    nodes = story.get("nodes")
    if not isinstance(nodes, list):
        return 0
    words = 0
    for node in nodes:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(node, dict):
            continue
        body = node.get("body")
        if isinstance(body, str):
            words += sum(int(m) for m in _FILL_WORDS_RE.findall(body))
    return math.ceil(words * _TOKENS_PER_FILL_WORD)


def is_fill_feasible(story: dict[str, object], *, max_tokens: int) -> bool:
    """Return whether a one-shot fill of *story* can fit under *max_tokens*.

    #CRITICAL: payment: without this predicate selection could pick a skeleton
    the fill pipeline provably cannot emit. ``fill_skeleton`` is one-shot with
    no chunking anywhere in ``generation/``, so an over-cap skeleton does not
    degrade, it fails: the completion truncates, no document parses, and the
    orchestrator burns its whole repair budget (roughly four rounds of ~100k
    input tokens) before failing deterministically, forever, on every retry.
    Measured 2026-08-16: 26 of the 62 production skeletons exceed the current
    32,000-token cap, the largest needing about 76,000. This is `UW-C07` and
    `AL-046`.
    #VERIFY: test_skeleton_feasibility.py asserts an over-cap skeleton is
    refused and that `skeleton_match` drops it from the candidate set.

    Note this bounds the *document*, not the call: reasoning tokens share the
    same budget and are not visible here, so a model that reasons heavily can
    still exhaust a cap this predicate called feasible. Choosing ``max_tokens``
    is the caller's job; this only refuses what cannot fit under any reasoning
    behaviour at all.

    Args:
        story: The decoded skeleton dict.
        max_tokens: The output cap the fill will run under.

    Returns:
        bool: True when the expected output leaves the required headroom.
    """
    return expected_output_tokens(story) <= max_tokens * _FEASIBILITY_MARGIN


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
