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

D8 completes the workstream with the promotion bundle and its hand-off pieces:

- :mod:`cyo_adventure.mutation.bundle`: the versioned ``lineage.json`` schema, the
  promotion-bundle writer, and ``verify_bundle`` (the parent-hash hard check).
- :mod:`cyo_adventure.mutation.reguide`: the author re-guidance resolution flow
  that turns a held mutant into a would-be-promotable one.
- :mod:`cyo_adventure.mutation.sample_fill`: the stage-5 sample-fill evidence
  (a deterministic mock fill of the mutant), bundle-time, not a gate.
- :mod:`cyo_adventure.mutation.compose`: bounded operator chains (OQ-7, ``<= 3``
  ops) and chain acceptance over the unchanged harness.
"""

from __future__ import annotations

from cyo_adventure.mutation.acceptance import (
    AcceptanceResult,
    Stage,
    StageOutcome,
    acceptance_to_dict,
    run_acceptance,
)
from cyo_adventure.mutation.bundle import (
    LINEAGE_VERSION,
    Lineage,
    LineageV2,
    OpChainEntry,
    VerifyResult,
    acceptance_digest,
    build_lineage,
    content_sha256,
    derive_mutant_contract,
    load_lineage,
    verify_bundle,
    write_bundle,
)
from cyo_adventure.mutation.compose import (
    MAX_CHAIN_LENGTH,
    ChainResult,
    ChainStep,
    apply_chain,
    run_chain_acceptance,
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
from cyo_adventure.mutation.reguide import (
    ReguideResolutions,
    ResolvedReguide,
    load_resolutions,
    reconcile,
    resolved_ids,
    unresolved_targets,
)
from cyo_adventure.mutation.sample_fill import (
    SampleFillResult,
    run_mock_sample_fill,
    skipped_result,
)
from cyo_adventure.mutation.state_ops import (
    M5,
    M5_OP_ID,
    M5StateVariation,
    StateSignature,
    clock_floor_for,
    ending_coverage_gap,
    state_distance,
    state_signature,
    state_signature_floor_reason,
    walk_fastest_satisfying_finish,
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
    "LINEAGE_VERSION",
    "M1",
    "M1_OP_ID",
    "M2",
    "M2_OP_ID",
    "M3",
    "M3_OP_ID",
    "M5",
    "M5_OP_ID",
    "MAX_CHAIN_LENGTH",
    "REGISTRY",
    "AcceptanceResult",
    "ChainResult",
    "ChainStep",
    "Edge",
    "Lineage",
    "LineageV2",
    "M1SiblingSubtreeSwap",
    "M2EndingReMap",
    "M3PruneGraft",
    "M5StateVariation",
    "MutationOp",
    "MutationResult",
    "OpChainEntry",
    "OpParams",
    "OpRegistry",
    "ParamValue",
    "PreconditionReport",
    "ReguideItem",
    "ReguideResolutions",
    "ReguideTarget",
    "ResolvedReguide",
    "SampleFillResult",
    "Stage",
    "StageOutcome",
    "StateSignature",
    "Subtree",
    "VerifyResult",
    "acceptance_digest",
    "acceptance_to_dict",
    "adjacency",
    "all_edges",
    "apply_chain",
    "build_lineage",
    "clock_floor_for",
    "content_sha256",
    "derive_mutant_contract",
    "descendants",
    "ending_coverage_gap",
    "extract_subtree",
    "graft_slot_id",
    "host_id_namespace",
    "is_closed",
    "is_self_contained",
    "load_lineage",
    "load_resolutions",
    "merge_graft_contract",
    "prune_contract",
    "recompute_ending_count",
    "recompute_estimated_minutes",
    "recompute_tier",
    "reconcile",
    "redeclare_topology",
    "region_referenced_slots",
    "rename_region",
    "resolved_ids",
    "resync_metadata",
    "run_acceptance",
    "run_chain_acceptance",
    "run_mock_sample_fill",
    "skipped_result",
    "state_distance",
    "state_signature",
    "state_signature_floor_reason",
    "unresolved_targets",
    "verify_bundle",
    "walk_fastest_satisfying_finish",
    "write_bundle",
]
