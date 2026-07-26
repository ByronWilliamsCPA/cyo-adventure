"""Offline-only sentinel-survival measurement (story personalization plan 3.4).

Never imported by ``app.py`` or any router; not part of the deployed service.

Story personalization (ADR-023) wraps a ``kind="personalizable"`` slot's bound
value in a ``{~SLOTID:GenericWord~}`` sentinel before the fill LLM sees it
(:mod:`cyo_adventure.storybook.sentinels`); the fill step must reproduce that
token verbatim, and :func:`cyo_adventure.validator.sentinel_integrity.check_sentinel_integrity`
fail-closes on any drift. Plan section 3.4 asks a question design alone cannot
answer: do sentinels actually survive the fill LLM often enough that a single
retry is cheap? That is a measurement, not a design decision, and this package
is the instrument that produces it.

No contract on disk declares a personalizable slot yet (the "dormancy fact"),
so a real generation run today produces zero sentinels to measure. This
package therefore authors its own fixtures: it takes real catalog
skeletons+contracts, flips a chosen set of slots to ``kind="personalizable"``,
and binds them so the resulting skeleton actually carries sentinels
(:mod:`cyo_adventure.measurement.fixtures`). It then drives the unchanged
:func:`cyo_adventure.generation.orchestrator.fill_skeleton` boundary,
classifies the result against the plan's failure taxonomy
(:mod:`cyo_adventure.measurement.taxonomy`), and aggregates a clean-pass rate
and retry-cost projection (:mod:`cyo_adventure.measurement.report`).

This package builds the instrument only. It does not run the real, paid,
multi-provider measurement (that is ``scripts/measure_sentinel_survival.py``'s
job, triggered by a human with live provider credentials), does not build the
later sentinel manifest, and does not build the deterministic post-fill
re-insertion fallback (conditional on a poor measured rate, plan 3.4).
"""

from __future__ import annotations

from cyo_adventure.measurement.fixtures import (
    DEFAULT_FIXTURES,
    Specimen,
    build_specimen,
    load_pair,
)
from cyo_adventure.measurement.report import (
    ProviderStats,
    ReportData,
    TrialRecord,
    aggregate,
    render_json,
    render_markdown,
    threshold_band,
)
from cyo_adventure.measurement.taxonomy import (
    RunRecord,
    ViolationRecord,
    bucket_for,
    classify_fill,
)

__all__ = [
    "DEFAULT_FIXTURES",
    "ProviderStats",
    "ReportData",
    "RunRecord",
    "Specimen",
    "TrialRecord",
    "ViolationRecord",
    "aggregate",
    "bucket_for",
    "build_specimen",
    "classify_fill",
    "load_pair",
    "render_json",
    "render_markdown",
    "threshold_band",
]
