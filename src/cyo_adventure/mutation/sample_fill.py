"""The stage-5 sample-fill evidence (WS-5 D8, design section 6 stage 5).

Stage 5 is bundle-time EVIDENCE, not a gate: it runs the unchanged
``generation/orchestrator.py::fill_skeleton`` once on the mutant's default
binding (parameterized parents) or default theme (contract-less parents), using a
deterministic MOCK provider so no live LLM is required, and attaches the filled
JSON plus its own gate report to the bundle. Per design section 6 stage 5:

- A fill whose OWN gate blocks STRUCTURALLY is a discard (the mutant's seams do
  not compose into a fillable story).
- A fidelity-only downgrade (``needs_review`` without a blocked gate) is
  RECORDED, not blocking: it reflects seam-guidance quality, which the human
  structure reviewer assesses anyway.

The mock path is preferred (the design's guidance): a live provider is never
required to produce the evidence. When no provider is available at all,
:func:`skipped_result` records "sample-fill skipped (no provider)" so the bundle
stays well-formed.

Pure-ish module: it imports the generation orchestrator and runs one async fill
via ``asyncio.run`` at its own boundary; it performs no network I/O (the provider
is a deterministic in-memory mock).
"""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from cyo_adventure.generation.binding import render_bound_skeleton
from cyo_adventure.generation.orchestrator import fill_skeleton
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.generation.skeleton import FILL_MARKER

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cyo_adventure.storybook.theme_contract import ThemeContract

# A tiny pool of deliberately simple, low-reading-level sentences the mock fill
# writes into each FILL body. Kept short and plain so the filled document clears
# the same gate the shell already passed (fewer, simpler words than the beats
# placeholder), giving a clean structural sample fill without a live model.
_MOCK_SENTENCES: tuple[str, ...] = (
    "The friends looked around. They saw a few ways to go. Each one felt new.",
    "A soft light fell here. The path ahead was calm and clear. They went on.",
    "Something small caught their eye. They stopped to look. It was worth it.",
    "The air was cool and quiet. They listened for a sound. Then they chose.",
)

# The default theme brief for the mock fill. Content is inert: the mock provider
# ignores the prompt, and the PII guard screens an empty child-name set.
_DEFAULT_THEME_BRIEF: dict[str, object] = {
    "setting": "a quiet, friendly place",
    "notes": "deterministic sample-fill evidence (WS-5 stage 5); no live model",
}


@dataclass(frozen=True, slots=True)
class SampleFillResult:
    """The outcome of the stage-5 sample fill.

    Attributes:
        status: The fill status: ``"passed"``, ``"needs_review"``, ``"failed"``,
            or ``"skipped"`` (no provider available).
        structurally_blocked: True when the fill's own gate BLOCKED (a discard
            condition, design 6 stage 5), distinct from a fidelity-only downgrade.
        fidelity_downgrade: True when the fill downgraded to ``needs_review``
            without a blocked gate (recorded, not blocking).
        filled: The filled document, or None when skipped/failed with no doc.
        gate: The fill's serialized gate report (empty when skipped).
        note: A human-readable summary line.
    """

    status: str
    structurally_blocked: bool
    fidelity_downgrade: bool
    filled: dict[str, object] | None
    gate: dict[str, object]
    note: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable view for the bundle's ``sample-fill/``."""
        return {
            "status": self.status,
            "structurally_blocked": self.structurally_blocked,
            "fidelity_downgrade": self.fidelity_downgrade,
            "filled": self.filled,
            "gate": self.gate,
            "note": self.note,
        }


def skipped_result(reason: str) -> SampleFillResult:
    """Return a ``skipped`` sample-fill result (no provider available).

    Args:
        reason: Why the fill was skipped.

    Returns:
        SampleFillResult: A skipped result recording the reason.
    """
    return SampleFillResult(
        status="skipped",
        structurally_blocked=False,
        fidelity_downgrade=False,
        filled=None,
        gate={},
        note=f"sample-fill skipped ({reason})",
    )


def _mock_fill_document(bound_skeleton: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministically filled copy of a (bound) skeleton.

    Every ``<<FILL ...>>`` node body is replaced with a short, simple sentence;
    ending blocks, choices, and structure are untouched. Because the shell (with
    its FILL placeholders and slot values rendered) already passed the gate,
    replacing each placeholder with shorter, plainer prose keeps the document
    gate-clean, so the mock provider returns valid, structurally-passing output.

    Args:
        bound_skeleton: The skeleton to fill (already slot-rendered when
            parameterized).

    Returns:
        dict[str, object]: The filled document the mock provider returns.
    """
    filled = copy.deepcopy(dict(bound_skeleton))
    raw_nodes = filled.get("nodes")
    if not isinstance(raw_nodes, list):
        return filled
    index = 0
    for raw_node in cast("list[object]", raw_nodes):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        body = node.get("body")
        if isinstance(body, str) and FILL_MARKER in body:
            node["body"] = _MOCK_SENTENCES[index % len(_MOCK_SENTENCES)]
            index += 1
    return filled


def _classify(status: str, report: Mapping[str, object]) -> tuple[bool, bool]:
    """Return ``(structurally_blocked, fidelity_downgrade)`` for a fill outcome.

    Args:
        status: The fill status.
        report: The fill's gate report.

    Returns:
        tuple[bool, bool]: Whether the gate blocked, and whether the fill
            downgraded on fidelity/safety without a blocked gate.
    """
    blocked = report.get("blocked") is True
    downgrade = (status == "needs_review") and not blocked
    return blocked, downgrade


def run_mock_sample_fill(
    candidate: Mapping[str, object],
    *,
    contract: ThemeContract | None = None,
) -> SampleFillResult:
    """Run the stage-5 sample fill with a deterministic mock provider.

    For a parameterized mutant the candidate is first rendered with the contract's
    ``default_binding`` (:func:`render_bound_skeleton`), and the fill runs with
    those bindings; for a contract-less mutant the free-text default-theme fill
    path runs. The mock provider returns a deterministically filled document, so
    the fill exercises the real ``fill_skeleton`` machinery and its gate without a
    live LLM.

    Args:
        candidate: The gate-passing mutant shell (FILL intact).
        contract: The mutant's theme contract, or None for a contract-less mutant.

    Returns:
        SampleFillResult: The recorded fill evidence (per design 6 stage 5: a
            structural block is a discard; a fidelity downgrade is recorded).
    """
    # #ASSUME: external-resources: fill_skeleton is provider-agnostic; here the
    # provider is a pure in-memory MockProvider, so no network or live model is
    # touched. The mock returns a valid filled document, so the fill runs one
    # stage and does not exhaust the response queue.
    # #VERIFY: tests/unit/test_mutation_sample_fill.py asserts a mock fill of a
    # real skeleton produces a non-blocked gate and a "passed"/"needs_review"
    # status, and that a structurally-blocking fill is flagged structurally_blocked.
    pii = PiiContext(child_names=frozenset())
    if contract is not None:
        bound = render_bound_skeleton(dict(candidate), contract.default_binding)
        filled_doc = _mock_fill_document(bound)
        # Queue several identical responses so an unexpected repair pass cannot
        # exhaust the mock; a clean fill consumes exactly one.
        provider = MockProvider(responses=[json.dumps(filled_doc)] * 4)
        outcome = asyncio.run(
            fill_skeleton(
                bound,
                _DEFAULT_THEME_BRIEF,
                provider,
                pii,
                slot_bindings=dict(contract.default_binding),
            )
        )
    else:
        filled_doc = _mock_fill_document(candidate)
        provider = MockProvider(responses=[json.dumps(filled_doc)] * 4)
        outcome = asyncio.run(
            fill_skeleton(dict(candidate), _DEFAULT_THEME_BRIEF, provider, pii)
        )

    blocked, downgrade = _classify(outcome.status, outcome.report)
    if blocked:
        note = (
            "STRUCTURAL BLOCK: the sample fill's own gate blocked; this mutant is a "
            "stage-5 discard (design 6 stage 5)"
        )
    elif downgrade:
        note = (
            "fidelity downgrade (needs_review) recorded, NOT blocking; the human "
            "structure reviewer assesses seam-guidance quality (design 6 stage 5)"
        )
    else:
        note = "sample fill passed its own gate cleanly (structural evidence attached)"
    return SampleFillResult(
        status=outcome.status,
        structurally_blocked=blocked,
        fidelity_downgrade=downgrade,
        filled=outcome.storybook,
        gate=outcome.report,
        note=note,
    )
