"""Service layer for the authoring-plan decision.

An admin picks a method (skeleton_fill/fresh_generation), a mechanism
(skill/automated_provider), and a prep model for an approved story request.
This module validates that choice, matches a skeleton when needed, and
creates the GenerationJob row -- enqueued immediately for the automated
fresh-generation path, or parked at "awaiting_manual_fill" for the skill
mechanism (resumed later via generation/import_cli.py --job).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.exceptions import StateTransitionError, ValidationError
from cyo_adventure.db.models import GenerationJob
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.generation.allowlist import is_enabled_allowlist_pair
from cyo_adventure.generation.skeleton_match import (
    candidates_for_cell,
    find_skeleton_metadata,
    recent_skeleton_usage,
    select_skeleton_for_cell,
    skeleton_matches_cell,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.api.schemas import (
        AuthoringMechanism,
        AuthoringMethod,
        AuthoringPlanRequest,
    )
    from cyo_adventure.db.models import Concept, StoryRequest

# The only Claude Code session models valid for mechanism="skill" (the
# cyo-author skill runs inside a Claude Code session, never inside an
# automated GenerationProvider backend).
# #ASSUME: data-integrity: this list is a static mirror of the model catalog
# in the global CLAUDE.md "Model Selection" table (short aliases + full ids).
# #VERIFY: keep in sync by hand when the catalog adds or renames a model; no
# automated check ties the two together.
SKILL_MECHANISM_MODELS = frozenset(
    {
        "sonnet",
        "opus",
        "fable",
        "haiku",
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-fable-5",
        "claude-haiku-4-5-20251001",
    }
)

# Bands where a low-effort skill model is more likely to under-deliver on a
# skeleton fill, per the tiered-backends spec's fill-difficulty table
# (docs/superpowers/specs/2026-06-23-modal-generation-tiers-design.md sec 7):
# medium-high/high difficulty starts at 10-13. Starting heuristic, not
# calibrated data (see that spec's own caveat); warns only, never blocks.
_HARD_BANDS = frozenset({"10-13", "13-16", "16+"})

# The lightest Claude Code model; paired with _HARD_BANDS below.
_LOW_EFFORT_SKILL_MODEL = "haiku"


@dataclass(frozen=True, slots=True)
class AuthoringPlanResult:
    """Everything the endpoint needs to build its response.

    Attributes:
        job: The newly created (and flushed) GenerationJob row.
        skeleton_slug: The matched or overridden skeleton's slug, or None
            for fresh_generation.
        warnings: Non-blocking eligibility and override-mismatch warnings.
        skeleton_alternatives: Every in-cell production-eligible skeleton
            slug (WS-C PR2), or an empty list for fresh_generation.
    """

    job: GenerationJob
    skeleton_slug: str | None
    warnings: list[str]
    skeleton_alternatives: list[str] = field(default_factory=list)


def _band_of(concept: Concept) -> str:
    """Return the concept brief's age_band, defaulting to "" if malformed.

    Args:
        concept: The concept row backing this authoring-plan decision.

    Returns:
        str: The stored age_band string, or "" if the brief is malformed.
    """
    # #ASSUME: data-integrity: Concept.brief is loosely-typed JSON written
    # through ConceptBrief.model_validate at approval time, so the key should
    # always be a valid AgeBand string; read defensively anyway.
    # #VERIFY: brief_from_request always stamps age_band from a validated
    # ChildProfile.age_band (story_requests/brief.py).
    band = concept.brief.get("age_band") if isinstance(concept.brief, dict) else None
    return band if isinstance(band, str) else ""


_DEFAULT_LENGTH = "short"
_DEFAULT_STYLE = "prose"


def _length_of(concept: Concept) -> str:
    """Return the concept brief's length, defaulting to "short" when null/absent.

    #ASSUME: data-integrity: request.length is nullable (WS-B #164);
    brief_from_request carries that null straight onto ConceptBrief.length,
    so concept.brief["length"] may be a literal JSON null, or the key may be
    absent entirely for a pre-length-field concept (both observed in
    existing test fixtures). Cell formation must always have a length axis
    to match against, so either case collapses to the band's default rather
    than failing to form a cell.
    #VERIFY: test_skeleton_fill_null_length_falls_back_to_short.
    """
    value = concept.brief.get("length") if isinstance(concept.brief, dict) else None
    return value if isinstance(value, str) else _DEFAULT_LENGTH


def _style_of(concept: Concept) -> str:
    """Return the concept brief's narrative_style, defaulting to "prose".

    ConceptBrief.narrative_style itself defaults to NarrativeStyle.PROSE, so
    a missing/malformed value here mirrors that same default rather than
    inventing a new one.
    """
    value = (
        concept.brief.get("narrative_style")
        if isinstance(concept.brief, dict)
        else None
    )
    return value if isinstance(value, str) else _DEFAULT_STYLE


def eligibility_warnings(
    method: AuthoringMethod, mechanism: AuthoringMechanism, band: str, prep_model: str
) -> list[str]:
    """Return non-blocking warnings for a possibly-poor-fit model choice.

    Args:
        method: The chosen authoring method.
        mechanism: The chosen authoring mechanism.
        band: The concept's age band.
        prep_model: The admin-chosen prep model identifier.

    Returns:
        list[str]: Zero or more human-readable warnings. Never raises; the
        admin retains full control over which model runs.
    """
    warnings: list[str] = []
    if (
        method == "skeleton_fill"
        and mechanism == "skill"
        and band in _HARD_BANDS
        and prep_model == _LOW_EFFORT_SKILL_MODEL
    ):
        warnings.append(
            f"{_LOW_EFFORT_SKILL_MODEL} may produce lower-fidelity fills for "
            f"{band} skeletons; consider opus or fable for this band."
        )
    return warnings


async def _automated_provider_metadata(
    session: AsyncSession, plan: AuthoringPlanRequest
) -> dict[str, object] | None:
    """Validate an automated_provider choice and return its authoring_metadata.

    Returns ``None`` for any non-automated_provider mechanism (nothing to
    persist). For ``automated_provider``, validates the admin-chosen
    provider/model against the enabled allowlist and returns the metadata dict
    to store on the job. Extracted from ``build_authoring_plan`` to keep that
    function's cognitive complexity within budget.

    Args:
        session: The request session (caller owns the transaction).
        plan: The admin's authoring-plan choice.

    Returns:
        The ``{provider, model}`` metadata for an automated_provider job, or
        ``None`` when the mechanism is not automated_provider.

    Raises:
        ValidationError: If provider/model are absent, or name a pair that is
            not an enabled allowlist entry (-> 422).
    """
    if plan.mechanism != "automated_provider":
        return None
    if plan.provider is None or plan.model is None:
        # Unreachable given AuthoringPlanRequest's own model_validator; this
        # narrows the type for BasedPyright without a bare `assert` (a
        # security-critical invariant should never rely on a statement `-O`
        # can strip).
        msg = "provider and model are both required when mechanism='automated_provider'"
        raise ValidationError(msg, field="provider", value=plan.provider)
    # #CRITICAL: security: provider/model are untrusted admin input. The schema
    # validator only guarantees both fields are PRESENT, not that they name a
    # real, enabled backend; this is the check that keeps a free-string model
    # id out of billing, run BEFORE anything is persisted to authoring_metadata
    # or reaches a provider.
    # #VERIFY: test_unallowlisted_provider_model_is_rejected and
    # test_automated_provider_unallowlisted_model_is_422.
    if not await is_enabled_allowlist_pair(session, plan.provider, plan.model):
        msg = (
            f"provider '{plan.provider}' / model '{plan.model}' is not an "
            "enabled allowlist entry"
        )
        raise ValidationError(msg, field="model", value=plan.model)
    return {"provider": plan.provider, "model": plan.model}


async def build_authoring_plan(
    session: AsyncSession,
    request: StoryRequest,
    concept: Concept,
    plan: AuthoringPlanRequest,
    actor: Actor,
) -> AuthoringPlanResult:
    """Validate an authoring-plan choice and create the GenerationJob row.

    Args:
        session: The request session (caller owns the transaction).
        request: The approved story request (status already checked by the caller).
        concept: The request's linked concept.
        plan: The admin's method/mechanism/prep_model choice.
        actor: The admin assigning the plan, recorded on the pipeline event.

    Returns:
        AuthoringPlanResult: The created job, matched or overridden skeleton
        slug (if any), every in-cell skeleton_alternatives, and any
        non-blocking eligibility/override warnings.

    Raises:
        ValidationError: On an unrecognized skill-mechanism model (-> 422),
            no matching production skeleton for the concept's cell (-> 422),
            or an admin skeleton_slug override that names a skeleton not
            present on disk (-> 422). The illegal fresh_generation + skill
            pairing is rejected earlier, at the schema boundary
            (AuthoringPlanRequest._skill_requires_skeleton_fill), so it never
            reaches this function.
        StateTransitionError: If a GenerationJob already exists for this
            concept (-> 409, idempotency guard).
    """
    method, mechanism, prep_model = plan.method, plan.mechanism, plan.prep_model

    # #CRITICAL: concurrency: relies on the caller holding a FOR UPDATE lock on
    # `request` (mirrors service.approve_story_request's contract) so two
    # concurrent authoring-plan calls for the same request cannot both pass
    # this existence check and both insert a GenerationJob for the same concept.
    # #VERIFY: api/story_requests.py::create_authoring_plan loads the request
    # with for_update=True before calling this function.
    existing = await session.scalar(
        select(GenerationJob).where(GenerationJob.concept_id == concept.id)
    )
    if existing is not None:
        msg = f"a generation job already exists for concept '{concept.id}'"
        raise StateTransitionError(msg)

    if mechanism == "skill" and prep_model not in SKILL_MECHANISM_MODELS:
        msg = f"prep_model '{prep_model}' is not a recognized Claude Code session model"
        raise ValidationError(msg, field="prep_model", value=prep_model)

    authoring_metadata = await _automated_provider_metadata(session, plan)

    band = _band_of(concept)
    skeleton_slug: str | None = None
    skeleton_alternatives: list[str] = []
    override_warnings: list[str] = []
    if method == "skeleton_fill":
        length = _length_of(concept)
        style = _style_of(concept)
        skeleton_alternatives = candidates_for_cell(band, length, style)
        if not skeleton_alternatives:
            msg = (
                f"no production-eligible skeleton available for band '{band}', "
                f"length '{length}', style '{style}'"
            )
            raise ValidationError(msg, field="band", value=band)
        if plan.skeleton_slug is not None:
            # #CRITICAL: security: the override is unconstrained (decision
            # C-6), but only among skeletons that actually exist on disk; an
            # unknown slug never silently proceeds as if it had matched.
            # #VERIFY: test_skeleton_fill_override_unknown_slug_is_rejected.
            override_metadata = find_skeleton_metadata(plan.skeleton_slug)
            if override_metadata is None:
                msg = f"skeleton_slug '{plan.skeleton_slug}' does not exist"
                raise ValidationError(
                    msg, field="skeleton_slug", value=plan.skeleton_slug
                )
            skeleton_slug = plan.skeleton_slug
            if not override_metadata.production_eligible:
                override_warnings.append(
                    f"skeleton_slug override '{skeleton_slug}' is not "
                    "production-eligible."
                )
            elif not skeleton_matches_cell(
                override_metadata, band=band, length=length, style=style
            ):
                override_warnings.append(
                    f"skeleton_slug override '{skeleton_slug}' is outside the "
                    f"request's cell (band='{band}', length='{length}', "
                    f"style='{style}')."
                )
        else:
            recent_usage = await recent_skeleton_usage(session, request.family_id)
            selection = select_skeleton_for_cell(
                skeleton_alternatives, recent_usage, random.SystemRandom()
            )
            skeleton_slug = selection.slug

    warnings = eligibility_warnings(method, mechanism, band, prep_model)
    warnings.extend(override_warnings)

    if method == "skeleton_fill":
        status = "awaiting_manual_fill" if mechanism == "skill" else "queued"
        authoring_metadata = {
            **(authoring_metadata or {}),
            "skeleton_slug": skeleton_slug,
            "theme_brief": concept.brief,
            "review_stage1_model": plan.review_stage1_model,
            "review_stage2_model": plan.review_stage2_model,
        }
        job = GenerationJob(
            concept_id=concept.id,
            status=status,
            model=prep_model,
            authoring_metadata=authoring_metadata,
        )
    else:
        job = GenerationJob(
            concept_id=concept.id,
            status="queued",
            model=prep_model,
            authoring_metadata=authoring_metadata,
        )

    session.add(job)
    await session.flush()

    # #CRITICAL: external-resources: this writes a PipelineEvent row inside the
    # caller's transaction; a failure here must roll the job creation back, not
    # be swallowed (mirrors record_event's own contract).
    # #VERIFY: no try/except around this call; failures propagate to the
    # unit-of-work started by api/story_requests.py::create_authoring_plan.
    await record_event(
        session,
        actor,
        entity_type="generation_job",
        entity_id=str(job.id),
        event_type=EventType.PLAN_ASSIGNED,
        to_state=job.status,
        payload={"job_status": job.status, "plan_kind": plan.method},
    )
    return AuthoringPlanResult(
        job=job,
        skeleton_slug=skeleton_slug,
        warnings=warnings,
        skeleton_alternatives=skeleton_alternatives,
    )
