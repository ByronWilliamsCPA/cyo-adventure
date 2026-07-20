"""Catalog-time skeleton mutation core (WS-5 D1).

This package grows distinct story trees per cell by mutating already gate
verified skeleton shells with cheap, deterministic operators. It is a pure,
offline authoring accelerator: nothing here reads a request, a database, or a
network, and no mutant reaches selection or a child except through the same
reviewed promotion path a hand authored skeleton takes (see
``docs/planning/ws5-structure-state-variation-design.md``).

D1 ships only the framework and safety-bearing utilities:

- :mod:`cyo_adventure.mutation.ops`: the ``MutationOp`` protocol, the result
  and parameter types, and an operator registry. Concrete operators land in
  D2 and later.
- :mod:`cyo_adventure.mutation.subtree`: subtree extraction plus the
  self-containment and closedness checks every subtree move depends on.
- :mod:`cyo_adventure.mutation.identity`: deterministic id renaming for
  grafted or duplicated regions, and metadata resync (ending count, estimated
  minutes, tier, and topology re-declaration).

D2 adds the first operator and the acceptance harness:

- :mod:`cyo_adventure.mutation.operators`: the M1 sibling-subtree swap, registered
  in the default :data:`~cyo_adventure.mutation.ops.REGISTRY`.
- :mod:`cyo_adventure.mutation.acceptance`: the section 6 stage table (D2 subset:
  preconditions, gate, cell assertion, plus re-guidance tracking).
"""

from __future__ import annotations

from cyo_adventure.mutation.acceptance import (
    AcceptanceResult,
    Stage,
    StageOutcome,
    acceptance_to_dict,
    run_acceptance,
)
from cyo_adventure.mutation.identity import (
    host_id_namespace,
    recompute_ending_count,
    recompute_estimated_minutes,
    recompute_tier,
    redeclare_topology,
    rename_region,
    resync_metadata,
)
from cyo_adventure.mutation.operators import (
    M1,
    M1_OP_ID,
    M2,
    M2_OP_ID,
    M3,
    M3_OP_ID,
    M1SiblingSubtreeSwap,
    M2EndingReMap,
    M3PruneGraft,
    graft_slot_id,
    merge_graft_contract,
    prune_contract,
    region_referenced_slots,
)
from cyo_adventure.mutation.ops import (
    REGISTRY,
    MutationOp,
    MutationResult,
    OpParams,
    OpRegistry,
    ParamValue,
    PreconditionReport,
    ReguideItem,
    ReguideTarget,
)
from cyo_adventure.mutation.subtree import (
    Edge,
    Subtree,
    adjacency,
    all_edges,
    descendants,
    extract_subtree,
    is_closed,
    is_self_contained,
)

__all__ = [
    "M1",
    "M1_OP_ID",
    "M2",
    "M2_OP_ID",
    "M3",
    "M3_OP_ID",
    "REGISTRY",
    "AcceptanceResult",
    "Edge",
    "M1SiblingSubtreeSwap",
    "M2EndingReMap",
    "M3PruneGraft",
    "MutationOp",
    "MutationResult",
    "OpParams",
    "OpRegistry",
    "ParamValue",
    "PreconditionReport",
    "ReguideItem",
    "ReguideTarget",
    "Stage",
    "StageOutcome",
    "Subtree",
    "acceptance_to_dict",
    "adjacency",
    "all_edges",
    "descendants",
    "extract_subtree",
    "graft_slot_id",
    "host_id_namespace",
    "is_closed",
    "is_self_contained",
    "merge_graft_contract",
    "prune_contract",
    "recompute_ending_count",
    "recompute_estimated_minutes",
    "recompute_tier",
    "redeclare_topology",
    "region_referenced_slots",
    "rename_region",
    "resync_metadata",
    "run_acceptance",
]
