"""Bounded operator chains and chain acceptance (WS-5 D8, design OQ-7).

D7 showed that a single structural operator usually leaves the mutant below
``TAU_STRUCT`` (M1 preserves every aggregate shape feature; M2 is
composition-only by construction). The highest-value mutants therefore pair a
structural op with an outcome re-map or a second structural move. OQ-7 ratifies
bounded chains: ``<= 3`` operators, applied in sequence, each fed the previous
op's candidate, recorded as the lineage ``op_chain``.

This module applies such a chain (:func:`apply_chain`) and evaluates the final
candidate against the ORIGINAL parent through the unchanged acceptance harness
(:func:`run_chain_acceptance`). It adds no new gate or floor: it wraps the
precomputed final candidate in a trivial operator so ``run_acceptance`` runs its
identical stage ladder (gate, cell, Tier-2, anti-clone floor, contract) on the
composed result. Every D1-D7 acceptance behavior, and the CR-2 safety invariant,
is preserved unchanged.

Pure module: standard library plus the ``mutation`` layer. Deterministic: a chain
of ``(op_id, params, seed)`` steps re-derives byte-for-byte.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.acceptance import run_acceptance
from cyo_adventure.mutation.bundle import OpChainEntry
from cyo_adventure.mutation.ops import (
    REGISTRY,
    MutationResult,
    OpParams,
    PreconditionReport,
    ReguideItem,
)
from cyo_adventure.mutation.subtree import node_ids

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from structlog.stdlib import BoundLogger

    from cyo_adventure.mutation.acceptance import AcceptanceResult
    from cyo_adventure.mutation.ops import MutationOp
    from cyo_adventure.storybook.theme_contract import ThemeContract

# The OQ-7 chain bound: no mutant is derived by more than three operators.
MAX_CHAIN_LENGTH = 3

# The empty resolved-reguide set, as a module constant (avoids a call in a
# default; matches the acceptance module's convention).
_NO_RESOLVED_REGUIDE: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ChainStep:
    """One step in a bounded operator chain.

    Attributes:
        op_id: The operator id to apply (resolved against the registry).
        params: The operator parameters.
        seed: The rng seed for this step (recorded for replay).
    """

    op_id: str
    params: OpParams
    seed: int = 0


@dataclass(frozen=True, slots=True)
class ChainResult:
    """The product of applying a bounded operator chain (design 9.2).

    Attributes:
        candidate: The final mutated shell (ids/metadata resynced by the last
            operator), evaluated against the original parent by acceptance.
        reguide: The re-guidance items still relevant to the FINAL candidate
            (items pointing at surfaces a later step removed are dropped).
        op_chain: One :class:`~cyo_adventure.mutation.bundle.OpChainEntry` per
            applied operator, in application order (the lineage record).
        donor_slugs: The slugs of any M3 graft donors used in the chain.
        notes: The concatenated per-operator audit notes.
    """

    candidate: dict[str, object]
    reguide: tuple[ReguideItem, ...]
    op_chain: tuple[OpChainEntry, ...]
    donor_slugs: tuple[str, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


def _present_target_ids(candidate: Mapping[str, object]) -> set[str]:
    """Return every node, choice, and ending id present in the final candidate.

    Used to drop re-guidance items whose target a later chain step removed (a
    pruned subtree's beats no longer need re-authoring because they no longer
    exist), so the outstanding-reguide count reflects only real surfaces.

    Args:
        candidate: The final candidate document.

    Returns:
        set[str]: The union of node ids, choice ids, and ending ids.
    """
    present: set[str] = set(node_ids(candidate))
    raw_nodes = candidate.get("nodes")
    if not isinstance(raw_nodes, list):
        return present
    for raw_node in cast("list[object]", raw_nodes):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        ending = node.get("ending")
        if isinstance(ending, dict):
            ending_id = cast("dict[str, object]", ending).get("id")
            if isinstance(ending_id, str):
                present.add(ending_id)
        choices = node.get("choices")
        if not isinstance(choices, list):
            continue
        for raw_choice in cast("list[object]", choices):
            if isinstance(raw_choice, dict):
                choice_id = cast("dict[str, object]", raw_choice).get("id")
                if isinstance(choice_id, str):
                    present.add(choice_id)
    return present


def _surviving_reguide(
    emitted: Sequence[ReguideItem], candidate: Mapping[str, object]
) -> tuple[ReguideItem, ...]:
    """Return the emitted items whose target still exists, deduped by target id.

    Args:
        emitted: All re-guidance items emitted across the chain, in order.
        candidate: The final candidate document.

    Returns:
        tuple[ReguideItem, ...]: The surviving items; a later item for the same
            target id supersedes an earlier one.
    """
    present = _present_target_ids(candidate)
    kept: dict[str, ReguideItem] = {}
    for item in emitted:
        if item.target_id in present:
            kept[item.target_id] = item
    return tuple(kept.values())


def apply_chain(
    parent: Mapping[str, object],
    steps: Sequence[ChainStep],
    *,
    op_for: Callable[[str], MutationOp] | None = None,
) -> ChainResult:
    """Apply a bounded operator chain and return the composed result (design OQ-7).

    Each step's preconditions are checked against the running candidate; a failure
    aborts the whole chain (a chain is atomic). The final candidate is what
    acceptance evaluates against the original parent.

    Args:
        parent: The raw parent story document.
        steps: The chain steps, in application order (1..:data:`MAX_CHAIN_LENGTH`).
        op_for: Resolver from op id to operator; defaults to the shared registry.
            Tests inject a resolver so an M3 graft uses an in-memory donor.

    Returns:
        ChainResult: The composed candidate, surviving re-guidance, op chain,
            donor slugs, and notes.

    Raises:
        ValidationError: If the chain is empty or too long, an op id is unknown,
            or any step's preconditions fail on the running candidate.
    """
    if not steps:
        msg = "an operator chain must have at least one step"
        raise ValidationError(msg, field="steps", value=None)
    if len(steps) > MAX_CHAIN_LENGTH:
        msg = (
            f"an operator chain is bounded at {MAX_CHAIN_LENGTH} steps (OQ-7); "
            f"got {len(steps)}"
        )
        raise ValidationError(msg, field="steps", value=len(steps))
    resolve = op_for if op_for is not None else REGISTRY.get

    current: Mapping[str, object] = parent
    emitted: list[ReguideItem] = []
    op_chain: list[OpChainEntry] = []
    donor_slugs: list[str] = []
    notes: list[str] = []
    for index, step in enumerate(steps):
        op = resolve(step.op_id)
        report = op.preconditions(current, step.params)
        if not report.satisfied:
            reasons = "; ".join(report.failures) or "preconditions not satisfied"
            msg = f"chain step {index} ({step.op_id}) is ineligible: {reasons}"
            raise ValidationError(msg, field="steps", value=step.op_id)
        result = op.apply(current, step.params, random.Random(step.seed))  # noqa: S311 -- deterministic replay rng, not cryptographic
        current = result.candidate
        emitted.extend(result.reguide)
        notes.extend(result.notes)
        op_chain.append(
            OpChainEntry(op_id=step.op_id, params=step.params.mapping, seed=step.seed)
        )
        donor = step.params.get("donor")
        if isinstance(donor, str):
            donor_slugs.append(donor)

    final = dict(current)
    return ChainResult(
        candidate=final,
        reguide=_surviving_reguide(emitted, final),
        op_chain=tuple(op_chain),
        donor_slugs=tuple(sorted(set(donor_slugs))),
        notes=tuple(notes),
    )


@dataclass(slots=True)
class _PrecomputedOp:
    """A trivial operator that replays a precomputed candidate (design OQ-7).

    Lets ``run_acceptance`` evaluate a composed chain's final candidate against
    the original parent without re-deriving it: preconditions always pass and
    ``apply`` returns the stored candidate and its surviving re-guidance. This
    reuses the byte-identical acceptance stage ladder, so no floor is weakened and
    the CR-2 invariant is preserved (the harness still recomputes promotability
    only after the gate stage has passed).

    Attributes:
        op_id: A descriptive id recorded in the discard log (e.g. "chain:M3->M4").
        candidate: The precomputed final candidate.
        reguide: The candidate's surviving re-guidance items.
    """

    op_id: str
    candidate: dict[str, object]
    reguide: tuple[ReguideItem, ...]

    def preconditions(
        self,
        parent: Mapping[str, object],  # noqa: ARG002 -- protocol signature
        params: OpParams,  # noqa: ARG002 -- protocol signature
    ) -> PreconditionReport:
        """Return a satisfied report (the chain already validated each step)."""
        return PreconditionReport.passed()

    def apply(
        self,
        parent: Mapping[str, object],  # noqa: ARG002 -- protocol signature
        params: OpParams,  # noqa: ARG002 -- protocol signature
        rng: random.Random,  # noqa: ARG002 -- protocol signature
    ) -> MutationResult:
        """Return the precomputed candidate and its surviving re-guidance."""
        return MutationResult(candidate=self.candidate, reguide=self.reguide)


def _chain_op_id(chain: ChainResult) -> str:
    """Return a compact descriptive id for a chain (for the discard log)."""
    return "chain:" + "->".join(entry.op_id for entry in chain.op_chain)


def run_chain_acceptance(  # noqa: PLR0913 -- one cohesive acceptance delegation
    parent: Mapping[str, object],
    chain: ChainResult,
    *,
    parent_slug: str = "<unknown>",
    resolved_reguide_ids: frozenset[str] = _NO_RESOLVED_REGUIDE,
    walk_cap: int | None = None,
    mutated_contract: ThemeContract | None = None,
    logger: BoundLogger | None = None,
) -> AcceptanceResult:
    """Run the unchanged acceptance harness on a chain's final candidate (OQ-7).

    Wraps the composed candidate in a :class:`_PrecomputedOp` and delegates to
    :func:`~cyo_adventure.mutation.acceptance.run_acceptance`, so acceptance runs
    its identical stage ladder against the ORIGINAL parent. The result's
    ``reguide`` list is the chain's surviving items, so ``resolved_reguide_ids``
    from the author resolution file drives promotability exactly as for a
    single-operator mutant.

    Args:
        parent: The raw ORIGINAL parent story document.
        chain: The composed chain result.
        parent_slug: The parent's catalog slug, for the discard log.
        resolved_reguide_ids: Re-guidance target ids already resolved.
        walk_cap: An optional configuration-walk cap override (Tier-2 stage).
        mutated_contract: The mutant's theme contract (parameterized parents).
        logger: The structlog logger for discards; defaults to the harness's own.

    Returns:
        AcceptanceResult: The typed outcome of evaluating the final candidate.
    """
    op = _PrecomputedOp(
        op_id=_chain_op_id(chain),
        candidate=chain.candidate,
        reguide=chain.reguide,
    )
    if walk_cap is None:
        return run_acceptance(
            op,
            parent,
            OpParams.of(),
            parent_slug=parent_slug,
            resolved_reguide_ids=resolved_reguide_ids,
            mutated_contract=mutated_contract,
            logger=logger,
        )
    return run_acceptance(
        op,
        parent,
        OpParams.of(),
        parent_slug=parent_slug,
        resolved_reguide_ids=resolved_reguide_ids,
        walk_cap=walk_cap,
        mutated_contract=mutated_contract,
        logger=logger,
    )
