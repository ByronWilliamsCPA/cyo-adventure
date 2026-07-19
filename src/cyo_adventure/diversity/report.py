"""Anti-template guard report model (diversity/report.py).

Mirrors ``validator/report.py``'s role (a small, stable wire shape for one
gate's verdict) but as a Pydantic model per WS-0 design doc section 3.1,
since ``AntiTemplateReport`` is returned across the module boundary to
callers (WS-1's fill/repair loop) rather than accumulated internally like
``ValidationReport``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AntiTemplateVerdict(StrEnum):
    """The anti-template guard's verdict for one same-tree fill pair."""

    PASS_ = "pass"  # noqa: S105 # nosec B105 -- a verdict label, not a credential
    WARN = "warn"
    FAIL = "fail"


class AntiTemplateReport(BaseModel):
    """The anti-template guard's full result for one same-tree fill pair.

    Attributes:
        verdict: PASS, WARN, or FAIL per WS-0 design doc section 3.2.
        median_distance: Median per-node masked-unigram Jaccard distance
            (``D_uni``) across shared nodes.
        p25_distance: 25th percentile of ``D_uni`` across shared nodes.
        p10_distance: 10th percentile of ``D_uni`` across shared nodes.
        mean_bigram_distance: Mean per-node all-token bigram distance
            (``D_big``), the secondary anti-paraphrase signal.
        entity_count: Size of the masked entity set used for this pair.
        templated_nodes: Node ids with ``D_uni`` below the per-node flag
            floor, regardless of overall verdict; the repair targets WS-1
            hands back to the fill/repair loop.
        node_count: Number of shared nodes compared.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: AntiTemplateVerdict
    median_distance: float
    p25_distance: float
    p10_distance: float
    mean_bigram_distance: float
    entity_count: int
    templated_nodes: tuple[str, ...]
    node_count: int
