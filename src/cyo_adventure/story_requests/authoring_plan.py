"""Service layer for the authoring-plan decision.

An admin picks a method (skeleton_fill/fresh_generation), a mechanism
(skill/automated_provider), and a prep model for an approved story request.
This module validates that choice, matches a skeleton when needed, and
creates the GenerationJob row -- enqueued immediately for the automated
fresh-generation path, or parked at "awaiting_manual_fill" for the skill
mechanism (resumed later via generation/import_cli.py --job).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.exceptions import StateTransitionError, ValidationError
from cyo_adventure.db.models import GenerationJob
from cyo_adventure.generation.skeleton_match import select_skeleton_for_band

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.api.schemas import AuthoringMechanism, AuthoringMethod
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
        skeleton_slug: The matched skeleton's slug, or None for fresh_generation.
        warnings: Non-blocking eligibility warnings for the admin to read.
    """

    job: GenerationJob
    skeleton_slug: str | None
    warnings: list[str]


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


async def build_authoring_plan(
    session: AsyncSession,
    request: StoryRequest,
    concept: Concept,
    *,
    method: AuthoringMethod,
    mechanism: AuthoringMechanism,
    prep_model: str,
) -> AuthoringPlanResult:
    """Validate an authoring-plan choice and create the GenerationJob row.

    Args:
        session: The request session (caller owns the transaction).
        request: The approved story request (status already checked by the caller).
        concept: The request's linked concept.
        method: "skeleton_fill" or "fresh_generation".
        mechanism: "skill" or "automated_provider".
        prep_model: The admin-chosen prep model identifier.

    Returns:
        AuthoringPlanResult: The created job, matched skeleton slug (if any),
        and any non-blocking eligibility warnings.

    Raises:
        ValidationError: On an invalid method/mechanism combination (-> 422),
            an unrecognized skill-mechanism model (-> 400), or no matching
            production skeleton for the concept's band (-> 422).
        StateTransitionError: If a GenerationJob already exists for this
            concept (-> 409, idempotency guard).
    """
    _ = request  # reserved for future request-level checks; status is caller-verified
    if method == "fresh_generation" and mechanism == "skill":
        msg = "mechanism='skill' requires method='skeleton_fill'"
        raise ValidationError(msg, field="mechanism", value=mechanism)
    if method == "skeleton_fill" and mechanism == "automated_provider":
        msg = (
            "method='skeleton_fill' with mechanism='automated_provider' is not "
            "yet supported; use mechanism='skill', or method='fresh_generation'"
        )
        raise ValidationError(msg, field="mechanism", value=mechanism)

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

    band = _band_of(concept)
    skeleton_slug: str | None = None
    if method == "skeleton_fill":
        skeleton_slug = select_skeleton_for_band(band)
        if skeleton_slug is None:
            msg = f"no production-eligible skeleton available for band '{band}'"
            raise ValidationError(msg, field="band", value=band)

    warnings = eligibility_warnings(method, mechanism, band, prep_model)

    if method == "skeleton_fill":
        job = GenerationJob(
            concept_id=concept.id,
            status="awaiting_manual_fill",
            model=prep_model,
            authoring_metadata={
                "skeleton_slug": skeleton_slug,
                "theme_brief": concept.brief,
            },
        )
    else:
        job = GenerationJob(concept_id=concept.id, status="queued", model=prep_model)

    session.add(job)
    await session.flush()
    return AuthoringPlanResult(job=job, skeleton_slug=skeleton_slug, warnings=warnings)
