"""Shared key constants and typed shape for GenerationJob.authoring_metadata.

The ``authoring_metadata`` dict on a GenerationJob is written by the authoring
plan service (:mod:`cyo_adventure.story_requests.authoring_plan`) and read back
by the skeleton-fill executors (:mod:`cyo_adventure.generation.worker` and
:mod:`cyo_adventure.generation.import_story`). Those producer and consumer
sites previously spelled the dict keys as bare string literals at each end, so
a rename on one side would silently desync from the other; that class of bug
already surfaced once as a cross-band metadata mismatch (finding C1).

The constants below are the single source of truth for those keys. Importing
the same symbol at every read/write site means a key rename is a one-line edit
that BasedPyright and the test suite both follow, so producer and consumer can
never drift apart. ``SkeletonAuthoringMetadata`` documents the full shape.
"""

from __future__ import annotations

from typing import TypedDict

# The two skeleton-provenance keys. Shared by the writer (authoring_plan) and
# the readers (worker.py, import_story.py) so a rename cannot silently desync.
SKELETON_SLUG_KEY = "skeleton_slug"
SKELETON_BAND_KEY = "skeleton_band"


class SkeletonAuthoringMetadata(TypedDict, total=False):
    """Typed shape of a GenerationJob.authoring_metadata dict.

    Every field is optional (``total=False``): a fresh_generation job carries
    only ``provider``/``model``, while a skeleton_fill job carries the skeleton
    provenance plus the review-model choices and theme brief.

    ``skeleton_band`` is an AgeBand string (``str(AgeBand member)``, e.g.
    ``"8-11"``): it records the REAL band of the chosen skeleton, which for an
    admin override may differ from the request's own band, so the executors
    load ``skeletons/<skeleton_band>/<skeleton_slug>.json`` from the skeleton's
    own directory rather than the request's.

    Attributes:
        skeleton_slug: The matched or overridden skeleton's filename stem.
        skeleton_band: The chosen skeleton's real age band (an AgeBand string).
        provider: The automated GenerationProvider backend id, when applicable.
        model: The provider model id, when applicable.
        review_stage1_model: The Stage 1 review model choice, if any.
        review_stage2_model: The Stage 2 review model choice, if any.
        theme_brief: The concept brief carried through to the fill job.
        slot_bindings: WS-2 theme-contract slot values recorded for a
            parameterized skeleton fill (manual/skill authoring path), so
            :mod:`cyo_adventure.generation.import_story`'s ``resume_manual_fill``
            can re-render the same bound skeleton for its Stage 1 check.
            ``None``/absent for a fresh_generation job, an unparameterized
            skeleton_fill job, or a pre-WS-2 job.
    """

    skeleton_slug: str
    skeleton_band: str
    provider: str
    model: str
    review_stage1_model: str
    review_stage2_model: str
    theme_brief: dict[str, object]
    slot_bindings: dict[str, str] | None
