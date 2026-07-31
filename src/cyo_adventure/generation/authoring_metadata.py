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

# The skeleton-provenance keys. Shared by the writer (authoring_plan) and the
# readers (worker.py, import_story.py) so a rename cannot silently desync.
SKELETON_SLUG_KEY = "skeleton_slug"
SKELETON_BAND_KEY = "skeleton_band"
# WS-7 D7: the in-cell alternatives the worker's bounded re-route iterates.
SKELETON_ALTERNATIVES_KEY = "skeleton_alternatives"

# A6/A7: the differentiation signal, persisted so it reaches the fill prompt.
# Before this, `DifferentiationLevel` reached a warning string, a log line, and
# the flywheel trigger, and then stopped: the fill that could have acted on it
# never saw it, which is why escalation had no effect on the prose.
#
# PRIOR_TITLES_KEY carries published titles only. It must never carry a prior
# story's premise or request text: that is another child's words, and routing a
# sibling's request into this fill's prompt would make one child's phrasing an
# input to another child's story. Theme tags come from the closed similarity
# vocabulary, so they are not free text either.
DIFFERENTIATION_LEVEL_KEY = "differentiation_level"
VARIATION_AXIS_KEY = "variation_axis"
PRIOR_TITLES_KEY = "prior_titles"
PRIOR_THEME_TAGS_KEY = "prior_theme_tags"


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

    This class is applied as the annotation on the writer in
    :func:`cyo_adventure.story_requests.authoring_plan.build_authoring_plan`.
    That is deliberate and load-bearing. Until 2026-07-31 it was referenced only
    from a docstring, so nothing checked it against the dict it describes, and
    it had silently drifted: the four A6/A7 differentiation keys below
    (``differentiation_level``, ``variation_axis``, ``prior_titles``,
    ``prior_theme_tags``) were added to this module as key constants and written
    by the producer without ever being added to this shape, and four scalars
    declared here as ``str`` were in fact written as ``str | None``. An unapplied
    TypedDict documents an intention, not a shape; only an annotation a type
    checker reads can keep the two in step.

    Attributes:
        skeleton_slug: The matched or overridden skeleton's filename stem.
            ``None`` is written when a skeleton_fill plan resolves no slug.
        skeleton_band: The chosen skeleton's real age band (an AgeBand string),
            or None alongside an unresolved ``skeleton_slug``.
        skeleton_alternatives: WS-7 D7 (design section 6.2). The in-cell
            production-eligible skeleton slugs the AUTO-PICK planner considered
            (already sorted), for the worker's bounded alternate-skeleton
            re-route on a bind failure. An ADMIN OVERRIDE persists ``[]``: an
            override is a deliberate pick and must never be silently re-routed.
            Absent/``[]`` for a fresh_generation job.
        differentiation_level: A6/A7. The ``DifferentiationLevel`` value driving
            the fill prompt's escalation, or None on the admin-override path
            where no similarity context is computed.
        variation_axis: A7. The craft axis drawn for this fill, seeded on the
            request id so a re-run reproduces it.
        prior_titles: A6. Published titles of this family's prior stories on the
            chosen skeleton. Titles only, never premise or request text: that
            would route one child's words into another child's story.
        prior_theme_tags: A6. Canonical similarity tags those stories carry,
            from the closed vocabulary, so this is not free text either.
        provider: The automated GenerationProvider backend id, when applicable.
        model: The provider model id, when applicable.
        review_stage1_model: The Stage 1 review model choice, or None.
        review_stage2_model: The Stage 2 review model choice, or None.
        theme_brief: The concept brief carried through to the fill job.
        slot_bindings: WS-2 theme-contract slot values recorded for a
            parameterized skeleton fill (manual/skill authoring path), so
            :mod:`cyo_adventure.generation.import_story`'s ``resume_manual_fill``
            can re-render the same bound skeleton for its Stage 1 check.
            ``None``/absent for a fresh_generation job, an unparameterized
            skeleton_fill job, or a pre-WS-2 job.
    """

    skeleton_slug: str | None
    skeleton_band: str | None
    skeleton_alternatives: list[str]
    differentiation_level: str | None
    variation_axis: str
    prior_titles: list[str]
    prior_theme_tags: list[str]
    provider: str
    model: str
    review_stage1_model: str | None
    review_stage2_model: str | None
    theme_brief: dict[str, object]
    slot_bindings: dict[str, str] | None
