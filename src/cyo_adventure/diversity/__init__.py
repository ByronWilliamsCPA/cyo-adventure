"""Diversity metrics: offline core, anti-template guard, request-time query.

WS-0 Phase 1 only (docs/planning/ws0-diversity-metrics-design.md section 10,
adjustment 3): ``normalize``, ``structure``, ``leaf`` (including the
anti-template guard), ``report``, ``history``, ``query``. Phase 2
(``aggregate``/ECS, ``lexical`` guards, the PS/RAR headline, the eval
harness, the CI gate) and Phase 3 (judge-model calibration) are not
implemented here.
"""

from __future__ import annotations

from cyo_adventure.diversity.history import HistoryEntry, load_family_history
from cyo_adventure.diversity.leaf import (
    AntiTemplateThresholds,
    LeafDistanceProfile,
    NodeLeafDistance,
    anti_template_verdict,
    leaf_distance_profile,
)
from cyo_adventure.diversity.normalize import (
    coerce_storybook,
    extract_entities,
    jaccard_distance,
    jaccard_similarity,
    mask_tokens,
    theme_signature,
)
from cyo_adventure.diversity.query import (
    DifferentiationLevel,
    SimilarityContext,
    StoryNeighbor,
    score_history,
    select_atg_comparison_partner,
    similarity_context,
)
from cyo_adventure.diversity.report import AntiTemplateReport, AntiTemplateVerdict
from cyo_adventure.diversity.structure import (
    StructureFeatures,
    structural_distance,
    structure_features,
    structure_fingerprint,
)

__all__ = [
    "AntiTemplateReport",
    "AntiTemplateThresholds",
    "AntiTemplateVerdict",
    "DifferentiationLevel",
    "HistoryEntry",
    "LeafDistanceProfile",
    "NodeLeafDistance",
    "SimilarityContext",
    "StoryNeighbor",
    "StructureFeatures",
    "anti_template_verdict",
    "coerce_storybook",
    "extract_entities",
    "jaccard_distance",
    "jaccard_similarity",
    "leaf_distance_profile",
    "load_family_history",
    "mask_tokens",
    "score_history",
    "select_atg_comparison_partner",
    "similarity_context",
    "structural_distance",
    "structure_features",
    "structure_fingerprint",
    "theme_signature",
]
