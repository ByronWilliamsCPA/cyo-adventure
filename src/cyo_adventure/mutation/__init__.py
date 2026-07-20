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
"""

from __future__ import annotations

from cyo_adventure.mutation.identity import (
    host_id_namespace,
    recompute_ending_count,
    recompute_estimated_minutes,
    recompute_tier,
    redeclare_topology,
    rename_region,
    resync_metadata,
)
from cyo_adventure.mutation.ops import (
    MutationOp,
    MutationResult,
    OpParams,
    OpRegistry,
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
    "Edge",
    "MutationOp",
    "MutationResult",
    "OpParams",
    "OpRegistry",
    "PreconditionReport",
    "ReguideItem",
    "ReguideTarget",
    "Subtree",
    "adjacency",
    "all_edges",
    "descendants",
    "extract_subtree",
    "host_id_namespace",
    "is_closed",
    "is_self_contained",
    "recompute_ending_count",
    "recompute_estimated_minutes",
    "recompute_tier",
    "redeclare_topology",
    "rename_region",
    "resync_metadata",
]
