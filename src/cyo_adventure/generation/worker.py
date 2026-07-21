"""Async generation worker: loads a job from the DB and runs the pipeline.

This module contains two entry points:

* :func:`run_generation_job` -- the async core logic, directly testable
  without Redis or RQ by injecting a provider and session factory.
* :func:`run_generation_job_sync` -- a thin synchronous wrapper that
  ``asyncio.run`` dispatches to the async core; this is what RQ calls.

Session ownership
-----------------
The worker opens its own :class:`~sqlalchemy.ext.asyncio.AsyncSession` and
commits explicitly. It does NOT share the request unit-of-work. This is
intentional: background jobs have a different transaction boundary than API
requests. The RAD marker below captures this contract.

PII guard placement
-------------------
:func:`~cyo_adventure.generation.pii.assert_prompt_pii_safe` runs inside
:func:`~cyo_adventure.generation.orchestrator.generate_story` before every
provider call. No PII leaves this process before the guard fires.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.database import get_worker_session
from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    GenerationJob,
    StoryRequest,
)
from cyo_adventure.diversity.normalize import theme_signature
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.generation.authoring_metadata import (
    SKELETON_ALTERNATIVES_KEY,
    SKELETON_BAND_KEY,
    SKELETON_SLUG_KEY,
)
from cyo_adventure.generation.binding import (
    contract_path_for,
    interpret_and_bind,
    load_contract_for,
    render_bound_skeleton,
)
from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.generation.orchestrator import fill_skeleton, generate_story
from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.generation.series_link import (
    embed_series_block,
    link_series_position,
)
from cyo_adventure.generation.skeleton import load_skeleton
from cyo_adventure.generation.skeleton_match import resolve_skeleton_path
from cyo_adventure.middleware.correlation import (
    generate_correlation_id,
    set_correlation_id,
)
from cyo_adventure.moderation import run_moderation_pipeline
from cyo_adventure.story_requests.interpretation import (
    ElementDecision,
    ElementDisposition,
    RawElement,
    ReasonCode,
    derive_dispositions,
    render_interpretation,
)
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.slots import DENYLIST_VERSION

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from contextlib import AbstractAsyncContextManager
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.generation.orchestrator import GenerationOutcome
    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.story_requests.interpretation import RequestInterpretation
    from cyo_adventure.storybook.theme_contract import ThemeContract

__all__ = [
    "run_generation_job",
    "run_generation_job_sync",
]

# Prompt version label stamped on every StorybookVersion row produced by this
# worker. Bump when prompt templates change in a way that affects output shape.
# "v2" (WS-2, OQ-6): spans BOTH the legacy free-text fill/generate prompts and
# the new bound-fill prompt (build_bound_fill_prompt); the two are
# disambiguated by the presence of the report's "theme_contract" audit block,
# not by this label, so the bump is coarse by design.
_PROMPT_VERSION = "v2"

# Each generation job produces a fresh Storybook, so its sole version is 1.
# Re-running generation creates a new job and a new Storybook id, not a new
# version under an existing id.
_FIRST_VERSION = 1

# Fallback model label for a provider that exposes no real model identifier
# (the in-phase mock). Phase 2b providers carry their own model name.
_MOCK_MODEL_LABEL = "mock"

# WS-7 D7 (design section 6.2, OQ-2 ratified). The bounded alternate-skeleton
# re-route budget: on a planned-skeleton bind failure with a theme
# incompatibility (ValidationError field="theme_brief"), the worker retries the
# bind on at most this many CONTRACT-BEARING in-cell alternates before failing
# closed. A contract-less alternate is skipped WITHOUT spending an attempt. A
# PII block (field="prompt") is NEVER re-routed (6.2 step 5): the same premise
# trips the same egress guard on every candidate. Worst case: _REROUTE_LIMIT
# alternates x the bind step's own small-JSON retry budget, never a fill call.
_REROUTE_LIMIT = 2

# WS-7 D7 (design section 6.3, CR-4). The two CANNOT_CARRY reasons are chosen by
# the bind exception's `field` PROVENANCE ONLY, never by string-matching its
# message: "prompt" is the PII egress guard raising before any provider dispatch
# (a privacy block), "theme_brief" is bind exhaustion after the slot gate
# rejected every attempt (a theme incompatibility). Any other field, or a
# non-skeleton-fill job, is not a bound-path bind outcome and gets no surface.
_CANNOT_CARRY_REASONS: dict[str, ReasonCode] = {
    "prompt": ReasonCode.PERSONAL_DETAILS,
    "theme_brief": ReasonCode.NO_CONFORMING_BINDING,
}


def _validation_field(exc: ValidationError) -> str | None:
    """Return a :class:`ValidationError`'s ``field`` provenance, or ``None``.

    The exception folds ``field`` into ``details`` (core/exceptions.py), so this
    is the single typed accessor the WS-7 D7 CR-4 classification reads: the PII
    egress guard raises ``field="prompt"``, bind exhaustion raises
    ``field="theme_brief"``. Reading provenance, never the message.

    Args:
        exc: The validation error to inspect.

    Returns:
        The ``field`` string, or ``None`` when absent / non-string.
    """
    field = exc.details.get("field")
    return field if isinstance(field, str) else None


logger = get_logger(__name__)


def _model_label(provider: GenerationProvider | None) -> str:
    """Return the model identifier for the provider that actually ran.

    The mock provider has no real model name, so it falls back to a stable
    ``"mock"`` label rather than ``None``. Phase 2b providers may expose a
    ``model`` attribute carrying the real model id.

    Args:
        provider: The provider used for this generation run.

    Returns:
        str: The model identifier, never ``None``.
    """
    return getattr(provider, "model", None) or _MOCK_MODEL_LABEL


def _provider_label(provider: GenerationProvider | None) -> str:
    """Return the provider name for the provider that actually ran.

    Prefers a ``name`` attribute on the provider so an injected non-default
    provider is recorded accurately; falls back to the configured default
    provider name only when the provider exposes no name.

    Args:
        provider: The provider used for this generation run.

    Returns:
        str: The provider name actually used for this run.
    """
    return getattr(provider, "name", None) or _default_settings.generation_provider


async def _record_failure(
    session: AsyncSession,
    job: GenerationJob,
    exc: Exception,
    *,
    provider: GenerationProvider | None,
    from_state: str = "running",
    report: dict[str, object] | None = None,
) -> None:
    """Mark ``job`` failed, record the truncated error, and commit.

    Extracted from what were three near-identical inline blocks (concept
    lookup miss, pipeline exception, moderation exception) plus the top-level
    interrupted-job finally guard, so every failure path commits an identical
    row shape.

    # #CRITICAL: concurrency: this commits immediately. A caller that already
    # mutated session state it needs to discard (e.g. an unreviewed storybook
    # persist) MUST roll back before calling this. A prior rollback also
    # discards any earlier uncommitted attribute writes on ``job`` itself
    # (SQLAlchemy expires session objects on rollback), which is why
    # ``provider`` must be re-supplied here rather than assumed still set.
    # #VERIFY: the moderation-failure call site in run_generation_job rolls
    # back before calling _record_failure.

    Args:
        session: Active async session; committed at the end of this call.
        job: The GenerationJob row to mark failed (mutated in place).
        exc: The exception whose message becomes ``job.error`` (truncated to
            512 chars to match the column width).
        from_state: The last durably-committed job status the transition
            leaves from. Defaults to ``"running"`` for paths where the running
            status was committed before the failure. Callers that rolled back
            an uncommitted ``running`` write (moderation-failure, interrupt
            finally-guard) re-fetch the row and pass its actual status so the
            event records the true prior state (e.g. ``"queued"``) rather than
            a phantom ``running`` transition.
        provider: The provider in effect for this run, or ``None`` when a
            failure interrupts before ``effective_provider`` is resolved (e.g.
            a ConfigurationError raised while building the adapter reaches the
            finally guard). ``_provider_label`` tolerates ``None`` and falls
            back to the configured default label. Stamping ``job.provider``/
            ``job.prompt_version`` here means a job that fails before or
            during generation still records which provider/prompt version it
            was attempted under (matching the success path).
        report: Optional structured detail to stamp onto ``job.report``
            alongside the truncated ``job.error`` string (WS-2: a fail-closed
            slot-binding ``ValidationError`` carries a ``violations`` list in
            its ``details`` that a 512-char message would truncate away).
            ``None`` (the default) leaves ``job.report`` untouched, which is
            every pre-existing call site's behavior.
    """
    job.status = "failed"
    job.error = str(exc)[:512]
    job.provider = _provider_label(provider)
    job.prompt_version = _PROMPT_VERSION
    if report is not None:
        job.report = report

    # #CRITICAL: data-integrity: this event must land in the SAME transaction
    # as the "failed" status write below (spec D1: event atomic with the
    # transition). record_event only flushes, it never commits, so it rides
    # the explicit commit() immediately after; placing it after that commit
    # would let a crash between the two calls leave the transition committed
    # with no corresponding event.
    # #VERIFY: test_generation_finished_event_precedes_failure_commit in
    # tests/integration/test_pipeline_event_instrumentation.py (asserts the
    # event and the failed status are only ever visible together, and that
    # neither is visible if the shared commit fails).
    await record_event(
        session,
        Actor.system(),
        entity_type="generation_job",
        entity_id=str(job.id),
        event_type=EventType.GENERATION_FINISHED,
        from_state=from_state,
        to_state="failed",
        payload={"outcome": "failed"},
    )
    await session.commit()


# #CRITICAL: concurrency: the worker owns its own session/transaction, separate
# from any request unit-of-work. Never pass a request-scoped session into this
# function; doing so creates cross-transaction contamination.
# #VERIFY: worker is always called with its own session_factory, either the
# default (production) or an injected factory (tests). A request-scoped session
# must never be passed here.

# #CRITICAL: security: PII guard (assert_prompt_pii_safe) runs inside
# generate_story before every provider.complete call. No child name reaches
# the provider unless the guard clears it. This chokepoint must not be
# bypassed when wiring real providers in Phase 2b.
# #VERIFY: integration test asserts PiiContext is populated from real child rows
# and that mock story generation does not include any real-child name in prompts.


@dataclasses.dataclass(frozen=True, slots=True)
class _SkeletonFillContext:
    """Grouped parameters for :func:`_run_skeleton_fill`.

    Bundled into one object (mirroring :class:`_PersistContext` below) so the
    function stays under the argument-count limit while keeping each field
    explicit.

    Attributes:
        authoring: The job's ``authoring_metadata`` dict (set by
            ``story_requests/authoring_plan.py::build_authoring_plan`` for
            ``method="skeleton_fill"`` + ``mechanism="automated_provider"``).
        brief: The concept brief; only its ``age_band`` is used, to resolve
            the skeleton library path.
        effective_provider: The provider used for the fill/repair calls.
        pii: PII context for the egress guard on every prompt.
        prep_model: The job's prep_model (``GenerationJob.model`` at call
            time, before the post-run label overwrite), threaded into the
            Stage 1 gate as its review-model fallback whenever the job's
            ``review_stage1_model`` override is unset (closes #134).
    """

    authoring: dict[str, object]
    brief: ConceptBrief
    effective_provider: GenerationProvider
    pii: PiiContext
    prep_model: str | None = None


def _refined_interpretation_from_bind(
    *,
    raw_elements: list[RawElement],
    bindings: Mapping[str, str],
    contract: ThemeContract,
    ctx: _SkeletonFillContext,
    created_at: datetime,
) -> RequestInterpretation:
    """Build the refined WS-7 interpretation for a parameterized (bound) fill.

    Composes the binder's element decomposition (from
    :func:`~cyo_adventure.generation.binding.interpret_and_bind`) through the
    pure :func:`~cyo_adventure.story_requests.interpretation.derive_dispositions`
    and :func:`~cyo_adventure.story_requests.interpretation.render_interpretation`
    (WS-7 D5, design section 5.3). The band, the validated bindings, and the
    contract slug/version all come from the just-run bind so the reflection
    describes the binding that actually rendered.

    # #EDGE: security: v1 passes ``self_names = child_names = ctx.pii.child_names``
    # for both the self-naming and the PII floor. Route A forbids ANY family
    # child's real name as protagonist, and the worker context does not carry the
    # requesting child's own display name separately from the family set, so a
    # requested family-child name lands IDENTITY_PROTECTION (self-naming rule 2,
    # checked first) while email/phone/address and any non-family PII land
    # PERSONAL_DETAILS. The precise sibling-vs-self distinction (a sibling's name
    # should coarsen to PERSONAL_DETAILS, not IDENTITY_PROTECTION) is a documented
    # v1 approximation pending threading the requesting child's display name into
    # the worker context; both outcomes withhold (element=None), so this only
    # coarsens the reason code, never leaks a name.
    # #VERIFY: test_run_skeleton_fill_refined_layer_classifies_self_name_and_pii.

    Args:
        raw_elements: The binder's sanitized element decomposition.
        bindings: The validated ``{slot_id: value}`` map that rendered.
        contract: The theme contract that was bound (supplies band, slug,
            version).
        ctx: The skeleton-fill context (supplies the brief's ``content_nogo``
            and the PII child names).
        created_at: The worker's creation timestamp for the object.

    Returns:
        The refined :class:`RequestInterpretation`.
    """
    band = contract.age_band
    child_names = ctx.pii.child_names
    decisions = derive_dispositions(
        raw_elements,
        band=band,
        bindings=bindings,
        content_nogo=ctx.brief.content_nogo,
        child_names=child_names,
        self_names=child_names,
        # ADAPTED trigger is a D4 follow-up: interpret_and_bind does not yet
        # expose which slots were corrected on the bind retry, so no element is
        # marked ADAPTED in v1 (every placed element is BUILT_IN).
        adapted_slot_ids=frozenset(),
    )
    return render_interpretation(
        decisions,
        band=band,
        layer="refined",
        skeleton_slug=contract.skeleton_slug,
        contract_version=contract.contract_version,
        created_at=created_at,
    )


def _degraded_interpretation(
    *,
    theme_brief: Mapping[str, object],
    band: AgeBand,
    skeleton_slug: str | None,
    ctx: _SkeletonFillContext,
    created_at: datetime,
) -> RequestInterpretation:
    """Build the degraded refined interpretation for a contract-less skeleton.

    WS-7 design section 5.4: an unmigrated (no-contract) skeleton runs no bind
    step, so no binder element decomposition exists. Instead the premise is
    decomposed into WS-0 ``theme_signature`` tags (each tag is catalog
    vocabulary and echo-safe by construction), run through the SAME derivation
    with empty bindings (so the bound-to-slot rule 3 never fires). A
    ``NOT_THIS_STORY_KIND`` reason is not claimable without a contract, so those
    elements are dropped; the band-expectation element is always appended. The
    object records ``contract_version=None`` so a caption can honestly present
    it as a general interpretation.

    Args:
        theme_brief: The job's theme brief dict; only ``premise`` is read by
            :func:`~cyo_adventure.diversity.normalize.theme_signature`.
        band: The reading age band the (contract-less) skeleton targets.
        skeleton_slug: The skeleton slug for the guardian caption, or ``None``.
        ctx: The skeleton-fill context (the brief's ``content_nogo`` + PII
            child names).
        created_at: The worker's creation timestamp for the object.

    Returns:
        The degraded refined :class:`RequestInterpretation` (contract_version
        ``None``).
    """
    decisions = _degraded_set_aside_decisions(
        theme_brief=theme_brief,
        band=band,
        content_nogo=ctx.brief.content_nogo,
        child_names=ctx.pii.child_names,
    )
    # Always append the band-expectation element (the band promise).
    decisions.append(
        ElementDecision(None, ElementDisposition.BUILT_IN, ReasonCode.STORY_FIT)
    )
    return render_interpretation(
        decisions,
        band=band,
        layer="refined",
        skeleton_slug=skeleton_slug,
        contract_version=None,
        created_at=created_at,
    )


def _degraded_set_aside_decisions(
    *,
    theme_brief: Mapping[str, object],
    band: AgeBand,
    content_nogo: Iterable[str],
    child_names: frozenset[str],
) -> list[ElementDecision]:
    """Derive the SET_ASIDE facts from a keyword decomposition, no bindings.

    Shared by the degraded refined layer (:func:`_degraded_interpretation`,
    design 5.4) and the D7 CANNOT_CARRY failure surface
    (:func:`_cannot_carry_interpretation`, design 6.1): decompose the premise
    into WS-0 ``theme_signature`` tags (each catalog vocabulary and echo-safe by
    construction, so no premise substring leaks), run
    :func:`~cyo_adventure.story_requests.interpretation.derive_dispositions` with
    EMPTY bindings so the bound-to-slot rule never fires, and drop
    ``NOT_THIS_STORY_KIND`` (not claimable without a contract).

    Args:
        theme_brief: The job's theme brief dict; only ``premise`` is read by
            :func:`~cyo_adventure.diversity.normalize.theme_signature`.
        band: The reading age band the derivation runs against.
        content_nogo: Guardian banned-theme strings (G2 controls).
        child_names: Family child names for the echo-floor PII / self-naming
            screens.

    Returns:
        The derived SET_ASIDE decisions, in the (sorted) tag order.
    """
    # Sorted for determinism: theme_signature returns a frozenset.
    raw_elements = [
        RawElement(phrase=tag, slot_id=None)
        for tag in sorted(theme_signature(theme_brief))
    ]
    return [
        decision
        for decision in derive_dispositions(
            raw_elements,
            band=band,
            bindings={},
            content_nogo=content_nogo,
            child_names=child_names,
            self_names=child_names,
        )
        # NOT_THIS_STORY_KIND is not claimable without a contract (section 5.4).
        if decision.reason is not ReasonCode.NOT_THIS_STORY_KIND
    ]


def _cannot_carry_interpretation(
    *,
    theme_brief: Mapping[str, object],
    band: AgeBand,
    content_nogo: Iterable[str],
    child_names: frozenset[str],
    reason: ReasonCode,
    created_at: datetime,
) -> RequestInterpretation:
    """Build the D7 CANNOT_CARRY failure interpretation (design 6.1, 6.3).

    The derivable SET_ASIDE facts (the same keyword decomposition the degraded
    layer uses, bindings empty) keep the reflection honest, then ONE terminal
    ``(CANNOT_CARRY, reason, element=None)`` element records why the whole theme
    could not be carried. The caller chooses ``reason`` from the bind
    exception's ``field`` provenance ALONE (CR-4): ``PERSONAL_DETAILS`` for a
    PII block (``field="prompt"``), ``NO_CONFORMING_BINDING`` for a theme
    incompatibility (``field="theme_brief"``). No ``skeleton_slug`` /
    ``contract_version`` is stamped: the bind produced no contract, and the
    honest claim is that the whole cell could not carry the theme, not one tree.

    Args:
        theme_brief: The job's theme brief dict (only ``premise`` is read).
        band: The reading age band (the request's, or an override's, band).
        content_nogo: Guardian banned-theme strings (G2 controls).
        child_names: Family child names for the echo-floor screens.
        reason: The terminal CANNOT_CARRY reason, chosen by the caller from
            ``exc.field`` provenance only.
        created_at: The worker's creation timestamp for the object.

    Returns:
        The refined CANNOT_CARRY :class:`RequestInterpretation`.
    """
    decisions = _degraded_set_aside_decisions(
        theme_brief=theme_brief,
        band=band,
        content_nogo=content_nogo,
        child_names=child_names,
    )
    decisions.append(ElementDecision(None, ElementDisposition.CANNOT_CARRY, reason))
    return render_interpretation(
        decisions, band=band, layer="refined", created_at=created_at
    )


@dataclasses.dataclass(frozen=True, slots=True)
class _BindResult:
    """The resolved skeleton/contract/bindings a bound fill will render.

    Either the planned skeleton's own bind (``rerouted_from is None``) or an
    alternate skeleton's bind after the bounded WS-7 D7 re-route
    (``rerouted_from`` = the planned slug the re-route left, design section 6.2).

    Attributes:
        skeleton: The (planned or alternate) skeleton dict to render.
        contract: The theme contract that actually bound (supplies the audit
            block's slug/version and the interpretation's band/slug/version).
        contract_path: That contract's on-disk path (for the audit sha256).
        bindings: The validated ``{slot_id: value}`` map.
        raw_elements: The binder's advisory element decomposition.
        rerouted_from: The planned slug the re-route left, or ``None`` when the
            planned skeleton bound on the first try.
    """

    skeleton: dict[str, object]
    contract: ThemeContract
    contract_path: Path
    bindings: dict[str, str]
    raw_elements: list[RawElement]
    rerouted_from: str | None


def _load_alternate(
    alt_slug: str, fill_band: str
) -> tuple[dict[str, object], ThemeContract, Path] | None:
    """Resolve and load an alternate skeleton and its theme contract.

    Returns ``(skeleton, contract, contract_path)`` for a CONTRACT-BEARING
    alternate, or ``None`` for a contract-less alternate (not eligible for the
    re-route: it would take the free-text path, which fail-closed forbids,
    design 6.2 step 2). A half-migrated/drift defect on an alternate raises a
    ``ValidationError`` from ``load_contract_for`` exactly as the planned path
    would.

    Args:
        alt_slug: The alternate skeleton's filename stem.
        fill_band: The band directory to resolve the alternate under (the
            request's own cell band; alternates are in-cell).

    Returns:
        The loaded ``(skeleton, contract, contract_path)``, or ``None`` when the
        alternate has no contract sidecar.
    """
    alt_path = resolve_skeleton_path(fill_band, alt_slug)
    alt_skeleton = load_skeleton(alt_path)
    alt_contract = load_contract_for(alt_path, alt_skeleton)
    if alt_contract is None:
        return None
    return alt_skeleton, alt_contract, contract_path_for(alt_path)


async def _reroute_bind(
    original: ValidationError,
    *,
    planned_slug: str,
    fill_band: str,
    theme_brief_dict: dict[str, object],
    ctx: _SkeletonFillContext,
) -> _BindResult:
    """Try to bind an in-cell alternate after the planned skeleton failed closed.

    WS-7 D7 (design section 6.2): iterate the persisted ``skeleton_alternatives``
    (already sorted by the planner's blended weight), skipping the planned slug
    and any already-tried, and any contract-less alternate. On the FIRST
    contract-bearing alternate that binds, return its :class:`_BindResult` with
    ``rerouted_from`` set to ``planned_slug``. At most :data:`_REROUTE_LIMIT`
    contract-bearing alternates are attempted; if all are exhausted or none are
    eligible, the ORIGINAL ``field="theme_brief"`` error is re-raised (fail
    closed, design 6.1). The re-route only ever lands on another contract-gated
    bind: it never falls through to the free-text path.

    # #CRITICAL: security: a PII block on an alternate (ValidationError
    # field="prompt") is re-raised immediately, never swallowed (6.2 step 5,
    # CR-4); only a theme incompatibility (field="theme_brief") moves on to the
    # next alternate. In practice the planned bind already cleared the same
    # premise past the egress guard before this loop was entered, so a PII raise
    # here is not expected, but the guard is preserved defensively.
    # #VERIFY: test_run_skeleton_fill_reroute_* in tests/unit/test_worker.py.

    Args:
        original: The planned skeleton's fail-closed ``field="theme_brief"``
            error, re-raised on exhaustion.
        planned_slug: The planned skeleton's slug (skipped, and recorded as
            ``rerouted_from`` on success).
        fill_band: The band directory alternates resolve under.
        theme_brief_dict: The same fenced brief the planned bind used.
        ctx: The skeleton-fill context (provider + PII + authoring metadata).

    Returns:
        The alternate's :class:`_BindResult`.

    Raises:
        ValidationError: ``original`` on exhaustion (fail closed), or a
            propagated PII / load-defect error from an alternate.
    """
    alternatives = ctx.authoring.get(SKELETON_ALTERNATIVES_KEY)
    candidates = alternatives if isinstance(alternatives, list) else []
    tried: set[str] = {planned_slug}
    attempts = 0
    for alt in cast("list[object]", candidates):
        if attempts >= _REROUTE_LIMIT:
            break
        if not isinstance(alt, str) or alt in tried:
            continue
        tried.add(alt)
        loaded = _load_alternate(alt, fill_band)
        if loaded is None:
            # Contract-less alternate: not eligible, and does NOT spend an
            # attempt (no bind call was made).
            continue
        alt_skeleton, alt_contract, alt_contract_path = loaded
        attempts += 1
        try:
            bindings, raw_elements = await interpret_and_bind(
                alt_contract, theme_brief_dict, ctx.effective_provider, ctx.pii
            )
        except ValidationError as exc:
            if _validation_field(exc) != "theme_brief":
                raise
            continue
        return _BindResult(
            skeleton=alt_skeleton,
            contract=alt_contract,
            contract_path=alt_contract_path,
            bindings=bindings,
            raw_elements=raw_elements,
            rerouted_from=planned_slug,
        )
    raise original


async def _bind_or_reroute(
    *,
    skeleton: dict[str, object],
    contract: ThemeContract,
    skeleton_path: Path,
    planned_slug: str,
    fill_band: str,
    theme_brief_dict: dict[str, object],
    ctx: _SkeletonFillContext,
) -> _BindResult:
    """Bind the planned skeleton, or the bounded re-route on a theme failure.

    WS-7 D7 (design section 6.2). Binds the planned skeleton first. On a
    fail-closed ``ValidationError``:

    - ``field="prompt"`` (a PII egress block): re-raised IMMEDIATELY, never
      re-routed (6.2 step 5, CR-4). The same premise trips the same guard on
      every candidate, so alternates are pointless.
    - ``field="theme_brief"`` (a theme incompatibility): the bounded re-route
      over the in-cell alternates (:func:`_reroute_bind`).
    - Any other field (e.g. a ``bound_skeleton`` render post-condition, raised
      only AFTER a successful bind by the caller, never here): propagates.

    Args:
        skeleton: The planned skeleton dict.
        contract: The planned skeleton's theme contract.
        skeleton_path: The planned skeleton's on-disk path.
        planned_slug: The planned skeleton's slug.
        fill_band: The band directory alternates resolve under.
        theme_brief_dict: The fenced brief to bind.
        ctx: The skeleton-fill context.

    Returns:
        The :class:`_BindResult` for the planned skeleton or a re-routed
        alternate.

    Raises:
        ValidationError: A PII block, an exhausted re-route (the original
            theme-incompatibility error), or a propagated load defect.
    """
    try:
        bindings, raw_elements = await interpret_and_bind(
            contract, theme_brief_dict, ctx.effective_provider, ctx.pii
        )
    except ValidationError as exc:
        if _validation_field(exc) != "theme_brief":
            raise
        return await _reroute_bind(
            exc,
            planned_slug=planned_slug,
            fill_band=fill_band,
            theme_brief_dict=theme_brief_dict,
            ctx=ctx,
        )
    return _BindResult(
        skeleton=skeleton,
        contract=contract,
        contract_path=contract_path_for(skeleton_path),
        bindings=bindings,
        raw_elements=raw_elements,
        rerouted_from=None,
    )


async def _run_skeleton_fill(ctx: _SkeletonFillContext) -> GenerationOutcome:
    """Run the automated skeleton-fill pipeline (Stage B') for one job.

    Loads the matched skeleton library file and delegates to
    :func:`~cyo_adventure.generation.orchestrator.fill_skeleton`, threading the
    Stage 1 fidelity-gate parameters through so the gate runs INSIDE
    ``fill_skeleton``'s bounded repair loop (#133): a Stage 1 fidelity miss on a
    structurally-clean fill re-enters the same ``max_repairs`` budget with a
    fidelity-aware repair prompt, and only downgrades an otherwise-``"passed"``
    fill to ``"needs_review"`` (recording ``"stage1_fidelity_violations"`` in
    the report) once that shared budget is exhausted. The produced storybook is
    never discarded, so a guardian/admin can still review the fill either way.
    This function no longer runs the gate or an outer retry loop itself; that
    logic now lives in the orchestrator so a fidelity miss and a structural
    block share one budget.

    Args:
        ctx: The grouped skeleton-fill context (see :class:`_SkeletonFillContext`).

    Returns:
        The :class:`~cyo_adventure.generation.orchestrator.GenerationOutcome`,
        with ``report`` augmented by ``fill_skeleton`` when a Stage 1 fidelity
        violation downgrades the status.

    Raises:
        ResourceNotFoundError: If ``authoring["skeleton_slug"]`` is missing or
            not a string.
        ValidationError: If the matched skeleton file fails structural
            validation (see :func:`~cyo_adventure.generation.skeleton.load_skeleton`);
            or (WS-2) if the skeleton is half-migrated (``{SLOT}`` tokens with
            no sidecar contract), or its sidecar fails to bind/render -- both
            fail closed, propagating unchanged into the caller's pipeline-
            exception handling. No fill provider call is made in either case.
    """
    authoring = ctx.authoring
    skeleton_slug = authoring.get(SKELETON_SLUG_KEY)
    theme_brief = authoring.get("theme_brief")
    # #ASSUME: data-integrity: authoring_metadata for a method="skeleton_fill"
    # job always carries a string skeleton_slug (see
    # story_requests/authoring_plan.py); a missing/wrong-typed value here
    # means the job was constructed outside that path.
    # #VERIFY: test_worker_runs_fill_skeleton_for_authoring_metadata_jobs.
    if not isinstance(skeleton_slug, str):
        msg = "authoring_metadata.skeleton_slug is missing or not a string"
        raise ResourceNotFoundError(msg)
    # #ASSUME: data-integrity: prefer the stored skeleton_band (the
    # OVERRIDE skeleton's real band, WS-C PR2 final review C1) over the
    # request's own brief.age_band, which is wrong for a cross-band admin
    # override; fall back to the request band only for a pre-fix job whose
    # authoring_metadata predates this key.
    # #VERIFY: cross-band skeleton_fill test in
    # tests/integration/test_generation_worker.py that a job carrying
    # skeleton_band="13-16" on an 8-11 request loads the 13-16 file.
    skeleton_band = authoring.get(SKELETON_BAND_KEY)
    fill_band = (
        skeleton_band if isinstance(skeleton_band, str) else ctx.brief.age_band.value
    )
    skeleton_path = resolve_skeleton_path(fill_band, skeleton_slug)
    skeleton = load_skeleton(skeleton_path)
    theme_brief_dict = theme_brief if isinstance(theme_brief, dict) else {}
    review_stage1_model = authoring.get("review_stage1_model")
    review_stage1_model = (
        review_stage1_model if isinstance(review_stage1_model, str) else None
    )

    # #CRITICAL: data-integrity: dispatch on sidecar presence (WS-2 design
    # section 5.1). A legacy skeleton (no `<slug>.contract.json`) takes the
    # byte-identical WS-1 free-text path below; a half-migrated skeleton
    # ({SLOT} tokens with no sidecar) is a content defect the post-generation
    # gate cannot see (a token is a valid non-empty string), so
    # load_contract_for itself fails closed with a ValidationError that
    # propagates unchanged into run_generation_job's pipeline-exception
    # handler -- no fill provider call is ever made for it.
    # #VERIFY: the no-sidecar (regression) and half-migrated worker tests in
    # tests/unit/test_worker.py.
    contract = load_contract_for(skeleton_path, skeleton)

    if contract is None:
        # #ASSUME: external-resources: fill_skeleton now runs the Stage 1
        # fidelity gate inside its own bounded repair loop, so a
        # persistently-flagged fill costs at most 1 fill + max_repairs repair
        # provider calls plus the paired Stage 1 review calls, all sharing ONE
        # budget. This replaces the removed worker-level outer loop, which
        # re-ran fill_skeleton from scratch up to 3 times (each with its own
        # max_repairs) for up to 9 provider calls.
        # #VERIFY: test_fill_skeleton_stage1_exhaustion_downgrades_with_key and
        # test_fill_skeleton_stage1_fail_once_then_pass_returns_passed in
        # tests/unit/test_orchestrator.py.
        #
        # The fill_skeleton call below stays BYTE-IDENTICAL to the pre-WS-7
        # legacy path (regression pin: the no-sidecar fill prompt is unchanged);
        # WS-7 only attaches a degraded refined interpretation (design section
        # 5.4) to the returned report afterward, never touching the fill call or
        # its prompt.
        outcome = await fill_skeleton(
            skeleton,
            theme_brief_dict,
            ctx.effective_provider,
            ctx.pii,
            settings=_default_settings,
            review_stage1_model=review_stage1_model,
            prep_model=ctx.prep_model,
        )
        degraded = _degraded_interpretation(
            theme_brief=theme_brief_dict,
            band=AgeBand(fill_band),
            skeleton_slug=skeleton_slug,
            ctx=ctx,
            created_at=datetime.now(UTC),
        )
        return dataclasses.replace(
            outcome,
            report={
                **outcome.report,
                "request_interpretation": degraded.model_dump(mode="json"),
            },
        )

    # #CRITICAL: security: interpret_and_bind's return value is derived from an
    # untrusted free-text theme_brief (OWASP LLM01) and stays untrusted-derived
    # until validate_slot_bindings passes INSIDE that call (WS-2 design section
    # 4.1). A ValidationError raised by the bind (exhaustion / PII block) or by
    # render_bound_skeleton (a post-condition failure) is deliberately left
    # uncaught here: it propagates into run_generation_job's existing
    # `except Exception` around the _run_skeleton_fill call, which records the
    # job "failed" (with the D7 CANNOT_CARRY surface) and re-raises. There is no
    # silent fallback to the free-text fill path (WS-2 OQ-1, ratified
    # fail-closed): the WS-7 D7 re-route only ever lands on ANOTHER
    # contract-gated bind (_bind_or_reroute), and an exhausted re-route
    # re-raises the original theme-incompatibility error, so a brief the binder
    # cannot fit to any in-cell contract never bypasses the deterministic slot
    # validator.
    # #VERIFY: the bind-failure and re-route worker tests assert the fill
    # provider's call log stays empty on a fail-closed path and that a re-route
    # only ever binds another contract-bearing skeleton.
    #
    # WS-7 D5/D7: _bind_or_reroute returns the SAME validated bindings a bare
    # bind would (the render/fill below are byte-for-byte unchanged) plus the
    # binder's advisory element decomposition, and, on a re-route, the alternate
    # skeleton/contract to render instead of the planned one. The elements half
    # is advisory and cannot rescue nor break the bind (CR-2); a ValidationError
    # on exhaustion propagates exactly as before, so no partial interpretation
    # is ever persisted for a failed bind (that surface is built in the caller's
    # except handler, design 6.1).
    result = await _bind_or_reroute(
        skeleton=skeleton,
        contract=contract,
        skeleton_path=skeleton_path,
        planned_slug=skeleton_slug,
        fill_band=fill_band,
        theme_brief_dict=theme_brief_dict,
        ctx=ctx,
    )
    bound = render_bound_skeleton(result.skeleton, result.bindings)

    outcome = await fill_skeleton(
        bound,
        theme_brief_dict,
        ctx.effective_provider,
        ctx.pii,
        settings=_default_settings,
        review_stage1_model=review_stage1_model,
        prep_model=ctx.prep_model,
        slot_bindings=result.bindings,
    )

    # WS-2 design section 7: the audit block a reviewer needs to see exactly
    # what the theme changed. `bind_attempts` is deliberately omitted:
    # interpret_and_bind does not report how many of its (at most max_attempts)
    # LLM calls it actually used, and recording a hardcoded `1` would
    # misrepresent a bind that succeeded only on its retry. The audit block
    # describes the contract that ACTUALLY bound (the alternate on a re-route),
    # and `rerouted_from` records the planned slug the re-route left (D7).
    theme_contract_report: dict[str, object] = {
        "skeleton_slug": result.contract.skeleton_slug,
        "contract_version": result.contract.contract_version,
        "contract_sha256": hashlib.sha256(
            result.contract_path.read_bytes()
        ).hexdigest(),
        "denylist_version": DENYLIST_VERSION,
        "slot_bindings": result.bindings,
    }
    if result.rerouted_from is not None:
        theme_contract_report["rerouted_from"] = result.rerouted_from
    # WS-7 D5/D6: the refined interpretation rides the report as a SIBLING of the
    # theme_contract audit block, so StorybookVersion.validation_report and
    # job.report both carry the audit copy; run_generation_job then projects it
    # onto the originating request row (section 5.5). Its skeleton_slug is the
    # contract that actually bound (the alternate, on a re-route).
    interpretation = _refined_interpretation_from_bind(
        raw_elements=result.raw_elements,
        bindings=result.bindings,
        contract=result.contract,
        ctx=ctx,
        created_at=datetime.now(UTC),
    )
    return dataclasses.replace(
        outcome,
        report={
            **outcome.report,
            "theme_contract": theme_contract_report,
            "request_interpretation": interpretation.model_dump(mode="json"),
        },
    )


def _should_persist_storybook(outcome: GenerationOutcome) -> bool:
    """Decide whether ``run_generation_job`` should persist ``outcome.storybook``.

    Always true for a clean ``"passed"`` outcome. Also true for a
    ``"needs_review"`` outcome, but ONLY when the downgrade came from
    :func:`~cyo_adventure.generation.orchestrator.fill_skeleton`'s own Stage 1
    fidelity gate on an otherwise-clean fill: that function adds the
    ``"stage1_fidelity_violations"`` key to ``outcome.report`` only when it
    performs this specific downgrade (never for any other cause), so the
    key's presence is an exact signal that the base outcome was clean before
    Stage 1 touched it. This lets an admin reach the real story behind a
    Stage-1-flagged fill instead of a job row pointing at nothing.

    Any OTHER ``"needs_review"`` (safety-flagged, or gate-blocked-with-doc
    after exhausting repairs -- both produced by
    :func:`~cyo_adventure.generation.orchestrator._build_outcome`, for either
    ``generate_story`` or ``fill_skeleton``'s own pre-Stage-1 outcome) and
    every ``"failed"`` outcome must keep NOT persisting a storybook: this is
    pre-existing, non-Plan-2 semantics that this widened gate must not
    change.

    Args:
        outcome: The pipeline outcome (from ``generate_story`` or
            ``_run_skeleton_fill``) about to be persisted onto the job row.

    Returns:
        True if a Storybook/StorybookVersion should be created for this
        outcome.
    """
    if outcome.storybook is None:
        return False
    stage1_downgraded = "stage1_fidelity_violations" in outcome.report
    return outcome.status == "passed" or (
        outcome.status == "needs_review" and stage1_downgraded
    )


def _review_stage2_override(authoring: dict[str, object] | None) -> str | None:
    """Return the Stage 2 review-model override recorded on the job, if valid.

    Args:
        authoring: The job's ``authoring_metadata`` dict, or ``None`` for a
            fresh (non-skeleton) generation that carries no override.

    Returns:
        The override model id when ``authoring`` carries a string
        ``review_stage2_model``; otherwise ``None`` (moderation uses its
        default reviewer).
    """
    if authoring is None:
        return None
    value = authoring.get("review_stage2_model")
    return value if isinstance(value, str) else None


def _authoring_provider_override(authoring: dict[str, object] | None) -> str | None:
    """Return the per-job provider override recorded on the job, if valid.

    Args:
        authoring: The job's ``authoring_metadata`` dict, or ``None`` for a
            fresh (non-skeleton, non-automated_provider) generation.

    Returns:
        The override provider name when ``authoring`` carries a string
        ``provider`` key; otherwise ``None`` (build_provider then falls back
        to ``settings.generation_provider``).
    """
    if authoring is None:
        return None
    value = authoring.get("provider")
    return value if isinstance(value, str) else None


def _authoring_model_override(authoring: dict[str, object] | None) -> str | None:
    """Return the per-job model override recorded on the job, if valid.

    Args:
        authoring: The job's ``authoring_metadata`` dict, or ``None``.

    Returns:
        The override model id when ``authoring`` carries a string ``model``
        key; otherwise ``None`` (build_provider then falls back to the
        resolved provider's default model from settings).
    """
    if authoring is None:
        return None
    value = authoring.get("model")
    return value if isinstance(value, str) else None


def _skeleton_slug_of(authoring: dict[str, object] | None) -> str | None:
    """Return the skeleton slug recorded on the job, if any.

    Args:
        authoring: The job's ``authoring_metadata`` dict, or ``None`` for a
            fresh (non-skeleton) generation that carries no skeleton.

    Returns:
        The skeleton slug when ``authoring`` carries a string
        ``skeleton_slug``; otherwise ``None`` (fresh_generation, or a
        skeleton_fill job somehow missing the key).
    """
    if authoring is None:
        return None
    value = authoring.get("skeleton_slug")
    return value if isinstance(value, str) else None


@dataclasses.dataclass(frozen=True, slots=True)
class _PersistContext:
    """The per-job context :func:`_persist_and_moderate` needs to persist + moderate.

    Bundled into one object (mirroring
    :class:`~cyo_adventure.generation.persistence.StorybookParams`) so the helper
    stays under the argument-count limit while keeping each field explicit.

    Attributes:
        job_id: The job's UUID (the source of the per-job storybook id and the
            re-fetch key). Passed explicitly rather than read off ``job_row`` so
            the storybook id matches the id the job was loaded by, exactly as the
            pre-refactor inline code used it.
        job_row: The job row being processed (mutated in place).
        concept_row: The job's concept (supplies family/creator for the persist).
        effective_provider: The provider that actually ran (labels + review).
        authoring: The job's ``authoring_metadata``, or ``None`` for a fresh
            (non-skeleton) generation.
        pii: The PII guard context passed through to moderation.
    """

    job_id: uuid.UUID
    job_row: GenerationJob
    concept_row: Concept
    effective_provider: GenerationProvider
    authoring: dict[str, object] | None
    pii: PiiContext


async def _persist_and_moderate(
    session: AsyncSession, ctx: _PersistContext, outcome: GenerationOutcome
) -> None:
    """Persist a persist-eligible outcome's storybook and run moderation on it.

    For a non-persist-eligible outcome (see :func:`_should_persist_storybook`)
    this logs and returns without touching the store, so the caller's single
    ``session.commit()`` still records the job's status/report/error. For a
    persist-eligible outcome it creates the Storybook/StorybookVersion, links
    them to the job's series (if any), drives the moderation pipeline, and
    only then embeds the document ``Series`` block (WS-G G2) from the
    post-moderation blob; a failure from either the moderation pipeline or the
    embed step rolls back the unreviewed persist and records the failure on a
    re-fetched row before re-raising (see the inline RAD markers). The embed
    step deliberately runs after moderation, not before: see the RAD marker on
    that call for why.

    Args:
        session: The worker's owned session (caller commits on the happy path).
        ctx: The per-job persist/moderate context (see :class:`_PersistContext`).
        outcome: The pipeline outcome about to be recorded on the job.

    Raises:
        Exception: Re-raises any moderation-pipeline or embed-step failure
            after rolling back the persist and recording the failure on the
            job row.
    """
    job_id = ctx.job_id
    # The `outcome.storybook is not None` half is redundant with
    # _should_persist_storybook's own None check, but is repeated so BasedPyright
    # narrows outcome.storybook to dict[str, object] for the persist call below.
    if not (_should_persist_storybook(outcome) and outcome.storybook is not None):
        logger.info(
            "generation_job.not_passed",
            job_id=str(job_id),
            status=outcome.status,
            attempts=outcome.attempts,
        )
        return

    # Mint a per-job storybook id so successive passing jobs never collide on the
    # storybook primary key. The mock provider returns a fixed blob id
    # ("s_mock_generated"), so reusing it would raise an IntegrityError on the
    # second passing job. Stamp the same id back onto the stored blob so the
    # blob's "id" matches its DB row.
    story_id = f"s_{job_id}"

    await persist_storybook(
        session,
        StorybookParams(
            story_id=story_id,
            blob=outcome.storybook,
            family_id=ctx.concept_row.family_id,
            created_by=ctx.concept_row.created_by,
            model=ctx.job_row.model,
            prompt_version=_PROMPT_VERSION,
            provider=_provider_label(ctx.effective_provider),
            skeleton_slug=_skeleton_slug_of(ctx.authoring),
            validation_report=dict(outcome.report),
            version=_FIRST_VERSION,
        ),
    )

    ctx.job_row.storybook_id = story_id
    ctx.job_row.version = _FIRST_VERSION

    await link_series_position(
        session, story_id=story_id, concept_id=ctx.job_row.concept_id
    )

    logger.info(
        "generation_job.storybook_persisted",
        job_id=str(job_id),
        storybook_id=story_id,
        status=ctx.job_row.status,
    )

    # #CRITICAL: security: a passed story is only a draft; it must be screened
    # and submitted/auto-rejected before commit so no unreviewed story rests in
    # a state a guardian could approve.
    # #VERIFY: run_moderation_pipeline drives submit or auto_reject on the row.
    try:
        await run_moderation_pipeline(
            session=session,
            story_id=story_id,
            version=_FIRST_VERSION,
            settings=_default_settings,
            generation_provider=ctx.effective_provider,
            pii=ctx.pii,
            review_model_override=_review_stage2_override(ctx.authoring),
        )
        # #CRITICAL: data-integrity: embed_series_block MUST run AFTER
        # run_moderation_pipeline returns successfully, never before. The
        # moderation soft-repair path (moderation/pipeline.py's
        # attempt_repair, adopted at "version_row.blob = revised") reassigns
        # the version row's blob wholesale; its repair prompt preserves node
        # ids/structure but says nothing about metadata.series, and
        # StoryMetadata.series is optional, so a repaired blob is schema-valid
        # with the series block silently dropped. Embedding before moderation
        # let a soft-repair erase (or, on a lucky-shaped LLM output, corrupt)
        # the block on any series book that triggered a repair; approval's
        # grandfather rule (publishing/service.py::_series_chain_docs) then
        # reads the missing block as a legacy/unparseable chain and skips the
        # SR gate for the WHOLE series, permanently. Placing the call here,
        # after the pipeline call and still inside this try, means: (a) it
        # reads the post-repair blob when a repair happened, so
        # ``start_node`` (preserved by the repair prompt) is still valid, and
        # (b) it shares the moderation-failure except below, so a raise from
        # either call rolls back the unreviewed persist identically and never
        # runs the other. Any FUTURE stage inserted between persist and this
        # point that can rewrite ``version_row.blob`` must be audited against
        # this same ordering constraint.
        # #VERIFY: tests/integration/test_series_link.py::
        # test_embed_series_block_survives_moderation_repair drives the
        # soft-repair path with fakes and asserts the re-read blob carries the
        # correct metadata.series afterward;
        # test_persist_and_moderate_repair_roundtrip_embeds_series_block and
        # test_persist_and_moderate_embed_failure_rolls_back_and_fails_job drive
        # THIS function directly, so a reorder of the calls above fails them.
        await embed_series_block(session, story_id=story_id, version=_FIRST_VERSION)
    except Exception as exc:
        # #CRITICAL: external-resource + data-integrity: a live review backend
        # can raise (timeout, 5xx, auth), and embed_series_block can raise on a
        # malformed or over-budget blob. Roll back the unreviewed storybook persist
        # first: the per-job story_id (f"s_{job_id}") would otherwise collide
        # on an RQ retry of this same job. Then record the failure on a
        # re-fetched row and commit, so the committed job state is "failed"
        # (not a stale "running") and the row agrees with the queue.
        # #VERIFY: rollback discards the persist; failure is committed before
        # the re-raise.
        error_text = str(exc)[:512]
        await session.rollback()
        failed_row = await session.get(GenerationJob, job_id)
        if failed_row is not None:
            await _record_failure(
                session,
                failed_row,
                exc,
                provider=ctx.effective_provider,
                from_state=failed_row.status,
            )
        else:
            # The "record failed" half of the invariant could not run: the row
            # vanished post-rollback (concurrent delete, or a rollback that
            # unwound its visibility). Surface it so the queue/DB divergence the
            # rollback is meant to prevent is observable, not silent.
            logger.exception(
                "generation_job.failure_record_lost",
                job_id=str(job_id),
                error=error_text,
            )
        logger.exception(
            "generation_job.moderation_error",
            job_id=str(job_id),
            error=error_text,
        )
        raise


async def _load_and_start_job(
    session: AsyncSession, job_id: uuid.UUID
) -> GenerationJob | None:
    """Load the job row, raise if missing, and claim it for this worker.

    Extracted from :func:`run_generation_job`'s job-load section so that
    function's body stays under the file's line budget.

    Args:
        session: Active async session.
        job_id: UUID of the GenerationJob to load.

    Returns:
        The loaded GenerationJob row, flushed with ``status="running"``, or
        ``None`` when the row is no longer ``"queued"`` (another worker already
        claimed or finished it), signaling the caller to skip execution.

    Raises:
        ResourceNotFoundError: If no GenerationJob row exists for ``job_id``.
    """
    job_row = await session.get(GenerationJob, job_id)
    if job_row is None:
        msg = f"GenerationJob {job_id} not found"
        raise ResourceNotFoundError(
            msg, resource_type="GenerationJob", resource_id=str(job_id)
        )

    # #CRITICAL: concurrency: compare-and-set claim on the queued->running
    # transition. A reclaim sweep re-enqueue or a duplicate RQ delivery can
    # invoke the worker for a row another delivery already claimed ("running")
    # or already finished (a terminal status); claiming it unconditionally let
    # two runs execute the same job (duplicate LLM spend, a persist_storybook
    # primary-key race). The worker opens a fresh session per job, so this read
    # reflects the last durably committed status; only proceed when it is still
    # "queued". Concurrent (not merely sequential) redelivery is additionally
    # prevented upstream: every enqueue path now shares one RQ identity with
    # unique=True (see api/generation.py::_enqueue_safely and
    # generation/queue.py::enqueue_generation), so RQ never admits two jobs for
    # one row in the first place.
    # #VERIFY: test_load_and_start_job_skips_already_running_row and
    # test_reclaim_after_completed_run_does_not_re_execute.
    if job_row.status != "queued":
        logger.warning(
            "generation_job.claim_lost",
            job_id=str(job_id),
            status=job_row.status,
        )
        return None

    job_row.status = "running"
    await session.flush()

    # #ASSUME: data-integrity: this is a SYSTEM transition (no request
    # principal reaches the worker), so the actor is always Actor.system();
    # never thread a request-scoped principal into this function.
    # #VERIFY: test_generation_started_event_is_system_actor in
    # tests/integration/test_pipeline_event_instrumentation.py asserts
    # actor_is_system=True.
    await record_event(
        session,
        Actor.system(),
        entity_type="generation_job",
        entity_id=str(job_row.id),
        event_type=EventType.GENERATION_STARTED,
        from_state="queued",
        to_state="running",
    )

    logger.info(
        "generation_job.started",
        job_id=str(job_id),
        concept_id=str(job_row.concept_id),
    )
    return job_row


async def _load_concept_and_pii(
    session: AsyncSession,
    job_row: GenerationJob,
    *,
    effective_provider: GenerationProvider,
) -> tuple[Concept, ConceptBrief, PiiContext]:
    """Load the job's concept, its brief, and a PiiContext from real child names.

    Extracted from :func:`run_generation_job`'s concept-load section so that
    function's body stays under the file's line budget. Behavior is
    unchanged: the same missing-concept failure recording + re-raise, the
    same brief validation, and the same PiiContext construction.

    Args:
        session: Active async session.
        job_row: The job row being processed (its ``concept_id`` is looked up).
        effective_provider: The provider in effect, threaded to
            :func:`_record_failure` if the concept is missing.

    Returns:
        A ``(concept_row, brief, pii)`` tuple.

    Raises:
        ResourceNotFoundError: If no Concept row exists for
            ``job_row.concept_id``; the failure is recorded on ``job_row``
            before this re-raises.
    """
    concept_row = await session.get(Concept, job_row.concept_id)
    if concept_row is None:
        msg = f"Concept {job_row.concept_id} not found"
        exc = ResourceNotFoundError(
            msg, resource_type="Concept", resource_id=str(job_row.concept_id)
        )
        await _record_failure(session, job_row, exc, provider=effective_provider)
        raise exc

    brief = ConceptBrief.model_validate(concept_row.brief)

    child_result = await session.execute(
        select(ChildProfile.display_name).where(
            ChildProfile.family_id == concept_row.family_id
        )
    )
    child_names: frozenset[str] = frozenset(row for (row,) in child_result.all() if row)
    pii = PiiContext(child_names=child_names)
    return concept_row, brief, pii


async def _persist_passed_outcome(
    session: AsyncSession, ctx: _PersistContext, outcome: GenerationOutcome
) -> None:
    """Stamp the pipeline outcome onto ``ctx.job_row``, then persist + moderate.

    Extracted from :func:`run_generation_job`'s post-pipeline section so that
    function's body stays under the file's line budget. Behavior is
    unchanged: the same status/report/provider/prompt_version/model stamps in
    the same order, followed by the same :func:`_persist_and_moderate`
    delegation.

    Args:
        session: The worker's owned session (caller commits on the happy path).
        ctx: The per-job persist/moderate context (see :class:`_PersistContext`);
            ``ctx.job_row`` is mutated in place.
        outcome: The pipeline outcome to record.
    """
    ctx.job_row.status = outcome.status
    ctx.job_row.report = dict(outcome.report)
    ctx.job_row.provider = _provider_label(ctx.effective_provider)
    ctx.job_row.prompt_version = _PROMPT_VERSION
    # Record the model of the provider that actually ran. Deriving this from
    # the injected-arg presence recorded None in production (where provider
    # is None but the mock still runs); _model_label reflects the real run.
    ctx.job_row.model = _model_label(ctx.effective_provider)

    # #ASSUME: data-integrity: this is a SYSTEM transition (no request
    # principal reaches the worker), so the actor is always Actor.system().
    # to_state mirrors the just-stamped job status ("passed" or
    # "needs_review"); the terminal "failed" case is recorded separately in
    # _record_failure, not here.
    # #VERIFY: test_generation_finished_event_is_system_actor in
    # tests/integration/test_pipeline_event_instrumentation.py.
    await record_event(
        session,
        Actor.system(),
        entity_type="generation_job",
        entity_id=str(ctx.job_row.id),
        event_type=EventType.GENERATION_FINISHED,
        from_state="running",
        to_state=ctx.job_row.status,
        payload={
            "outcome": ctx.job_row.status,
            "provider": ctx.job_row.provider,
            "model": ctx.job_row.model,
            "prompt_version": ctx.job_row.prompt_version,
        },
    )

    await _persist_and_moderate(session, ctx, outcome)


async def _update_request_interpretation(
    session: AsyncSession, job_row: GenerationJob, outcome: GenerationOutcome
) -> None:
    """Project a refined interpretation from the report onto its request row.

    WS-7 D6 (design section 5.5): when ``outcome.report`` carries a
    ``request_interpretation`` block (a parameterized or degraded skeleton
    fill), resolve the originating request through the job's concept
    (``GenerationJob.concept_id`` -> ``StoryRequest.concept_id``) on the
    worker's OWN session and stamp the block onto ``StoryRequest.interpretation``.
    This does NOT commit: the caller's single terminal ``session.commit()``
    records it in the same transaction/session posture the worker already uses
    for the job row.

    A fresh (non-skeleton) generation carries no ``request_interpretation`` and
    is a silent no-op; so is an authored/catalog job (or any job whose concept
    has no originating request row).

    # #ASSUME: external-resources: this issues one additional UPDATE on the
    # worker's already-open session (no new session, no cross-transaction
    # contamination); it rides the existing terminal commit.
    # #VERIFY: test_update_request_interpretation_sets_row_when_found.
    # #EDGE: data-integrity: the concept -> request resolution may find no row
    # (an authored/catalog job, or a job with no originating request); this is a
    # silent no-op, the report copy still exists on the job/version rows.
    # #VERIFY: test_update_request_interpretation_no_request_row_is_noop.

    Args:
        session: The worker's owned session (caller commits on the happy path).
        job_row: The job whose ``concept_id`` resolves the request row.
        outcome: The pipeline outcome; only its ``report`` is read.
    """
    interpretation = outcome.report.get("request_interpretation")
    if interpretation is None:
        return
    await _stamp_request_interpretation(session, job_row, interpretation)


async def _stamp_request_interpretation(
    session: AsyncSession, job_row: GenerationJob, block: object
) -> None:
    """Resolve the originating request via the job's concept and stamp ``block``.

    Shared by the D6 success projection (:func:`_update_request_interpretation`)
    and the D7 failure surface (:func:`_record_cannot_carry_if_bound_path`).
    Resolves ``StoryRequest WHERE concept_id == job.concept_id`` on the worker's
    OWN session and sets ``StoryRequest.interpretation``. A missing request row
    (an authored/catalog job, or a concept with no originating request) is a
    silent no-op. Does NOT commit: the caller's terminal commit (or
    :func:`_record_failure`'s commit) records it in the same transaction.

    Args:
        session: The worker's owned session.
        job_row: The job whose ``concept_id`` resolves the request row.
        block: The serialized interpretation dict to stamp.
    """
    result = await session.execute(
        select(StoryRequest).where(StoryRequest.concept_id == job_row.concept_id)
    )
    request_row = result.scalar_one_or_none()
    if request_row is None:
        return
    request_row.interpretation = cast("dict[str, object]", block)


async def _record_cannot_carry_if_bound_path(
    session: AsyncSession,
    job_row: GenerationJob,
    exc: Exception,
    *,
    authoring: dict[str, object] | None,
    brief: ConceptBrief,
    pii: PiiContext,
    report: dict[str, object] | None,
) -> dict[str, object] | None:
    """Attach a CANNOT_CARRY interpretation for a failed bound-path fill (D7).

    Returns ``report`` UNCHANGED unless all three hold (design 6.1, 6.3): ``exc``
    is a :class:`ValidationError`; the job is a skeleton-fill job (a string
    ``skeleton_slug`` in ``authoring``); and ``exc.field`` is a bound-path bind
    provenance (:data:`_CANNOT_CARRY_REASONS`: ``"prompt"`` = PII block,
    ``"theme_brief"`` = theme incompatibility). A fresh_generation, legacy
    no-sidecar, or half-migrated failure therefore keeps today's behavior (no
    interpretation): a fresh_generation PII block raises ``field="prompt"`` too,
    which is why the skeleton-fill gate is required alongside the field check.

    When it applies, it builds the CANNOT_CARRY interpretation (reason chosen
    from ``exc.field`` ALONE, CR-4), stamps it on the originating request row
    (no-op if absent), and returns ``report`` with the serialized block added
    under ``"request_interpretation"``. Job status/retry semantics are
    untouched: the caller still records the job "failed" and re-raises.

    # #CRITICAL: security: CR-4 -- the two reasons are keyed on exc.field
    # provenance ONLY, never the message. A PII block can never become
    # NO_CONFORMING_BINDING, nor a theme reject become PERSONAL_DETAILS.
    # #VERIFY: test_run_generation_job_bind_failure_records_cannot_carry and
    # test_run_generation_job_pii_block_records_personal_details.

    Args:
        session: The worker's owned session.
        job_row: The failed job (its concept resolves the request row).
        exc: The pipeline exception being recorded.
        authoring: The job's ``authoring_metadata`` dict, or ``None``.
        brief: The concept brief (supplies band fallback + ``content_nogo``).
        pii: The PII context (supplies family child names for the echo floor).
        report: The report dict built so far (violations), or ``None``.

    Returns:
        ``report`` unchanged, or augmented with the serialized CANNOT_CARRY
        interpretation.
    """
    if not isinstance(exc, ValidationError):
        return report
    if authoring is None or not isinstance(authoring.get(SKELETON_SLUG_KEY), str):
        return report
    reason = _CANNOT_CARRY_REASONS.get(_validation_field(exc) or "")
    if reason is None:
        return report

    skeleton_band = authoring.get(SKELETON_BAND_KEY)
    fill_band = (
        skeleton_band if isinstance(skeleton_band, str) else brief.age_band.value
    )
    theme_brief = authoring.get("theme_brief")
    theme_brief_dict = theme_brief if isinstance(theme_brief, dict) else {}

    interpretation = _cannot_carry_interpretation(
        theme_brief=theme_brief_dict,
        band=AgeBand(fill_band),
        content_nogo=brief.content_nogo,
        child_names=pii.child_names,
        reason=reason,
        created_at=datetime.now(UTC),
    )
    serialized = interpretation.model_dump(mode="json")
    await _stamp_request_interpretation(session, job_row, serialized)
    return {**(report or {}), "request_interpretation": serialized}


async def run_generation_job(
    job_id: uuid.UUID,
    *,
    provider: GenerationProvider | None = None,
    session_factory: (
        Callable[[], AbstractAsyncContextManager[AsyncSession]] | None
    ) = None,
) -> None:
    """Run the generation pipeline for a single job, persisting the outcome.

    This is the testable async core. Tests inject ``provider`` and
    ``session_factory`` directly; production uses the defaults built from
    application settings.

    Lifecycle transitions::

        queued -> running -> passed | needs_review | failed

    On ``"passed"``: creates a :class:`~cyo_adventure.db.models.Storybook` row
    and a :class:`~cyo_adventure.db.models.StorybookVersion` row, then links
    both back to the job.

    On ``"needs_review"`` when the downgrade came from a Stage 1 fidelity
    check on an otherwise-clean fill (signaled by
    ``"stage1_fidelity_violations"`` in ``outcome.report``, the exact key
    :func:`~cyo_adventure.generation.orchestrator.fill_skeleton` adds only for
    this downgrade): the same
    Storybook/StorybookVersion creation and linking happens as for
    ``"passed"``, and the moderation pipeline still runs on the result, so a
    guardian/admin can review a real, queryable story instead of a job row
    pointing at nothing.

    On any OTHER ``"needs_review"`` (safety-flagged by
    :func:`~cyo_adventure.generation.orchestrator._build_outcome`, or
    gate-blocked-with-doc after exhausting repairs) or on ``"failed"``:
    records the report and error on the job row; no Storybook or
    StorybookVersion is created.

    On unexpected exception: sets ``job.status = "failed"``, records the error,
    commits, then re-raises so RQ marks the job failed in its own bookkeeping.

    A top-level ``finally`` guards against any interruption (an RQ
    ``job_timeout`` SIGALRM, a process kill) landing somewhere not already
    covered by one of the explicit failure paths above: if the job row is
    still ``"queued"`` or ``"running"`` when this function unwinds, it is
    force-failed with error ``"interrupted"`` so it is never left stranded
    (Finding 4; see ``generation/queue.py::requeue_stranded_jobs`` for the
    complementary reclaim sweep that recovers rows lost before this function
    ever ran).

    # #CRITICAL: concurrency: the finally guard cannot trust a plain
    # ``session.get(GenerationJob, job_id)`` read to reflect the row's durable
    # state. ``job_row.status`` is set in memory (e.g. to ``"passed"``) well
    # before the terminal commit lands: an interruption landing in that
    # window (during ``persist_storybook`` or the moderation call, both of
    # which run after the in-memory status write) previously returned the
    # SAME identity-mapped object with the uncommitted status, so
    # ``stranded.status in ("queued", "running")`` read False and the guard
    # skipped force-failing a row that was actually still "queued"/"running"
    # in the database (Finding 2, D2 review). The fix tracks completion with
    # an explicit local flag set only right after the real terminal commit,
    # and rolls back before re-reading in the finally so the read reflects
    # the last durably committed row state, never a dirty in-memory write.
    # #VERIFY: test_late_interrupt_during_persist_records_failed_not_passed
    # interrupts inside persist_storybook, after job_row.status is already set
    # to "passed" in memory but before any commit, and asserts the row lands
    # "failed"/"interrupted", not "passed".

    Args:
        job_id: UUID of the :class:`~cyo_adventure.db.models.GenerationJob` to
            process. Raises :class:`~cyo_adventure.core.exceptions.ResourceNotFoundError`
            if the row is missing.
        provider: Optional injected :class:`~cyo_adventure.generation.provider.GenerationProvider`.
            When ``None``, the production provider is built from
            :data:`~cyo_adventure.core.config.settings`.
        session_factory: Optional callable returning an async context manager
            that yields an :class:`~sqlalchemy.ext.asyncio.AsyncSession`. When
            ``None``, the production
            :func:`~cyo_adventure.core.database.get_worker_session` factory is
            used (ADR-021: this runs in an RQ worker process, so it must use
            the worker engine, not the API engine's ``get_session``).

    Raises:
        ResourceNotFoundError: If no GenerationJob row exists for ``job_id``.
        Exception: Re-raises any unexpected exception after recording the
            failure on the job row, so RQ can mark the job failed.
    """
    set_correlation_id(generate_correlation_id())

    # Resolve defaults: use injected factory or the production session factory.
    # #ASSUME: external-resources: get_worker_session() opens a DB connection
    # on first use; an unreachable database surfaces here as a connection
    # error. ADR-021: this must stay get_worker_session, not get_session; a
    # regression back to get_session would silently ignore a post-cutover
    # WORKER_DATABASE_URL for background jobs.
    # #VERIFY: readiness probe on api/health.check_database catches DB outages
    # before jobs are dispatched; test_worker.py pins the default factory.
    _factory = session_factory or get_worker_session

    async with _factory() as session:  # type: ignore[attr-defined]
        # #CRITICAL: concurrency: tracks whether the terminal commit below
        # actually landed. Only set True immediately after that commit; every
        # early-exit path (raise) leaves this False so the finally guard knows
        # it must verify the row's true committed state rather than trust an
        # in-memory attribute. See the finally block for the full rationale.
        completed = False
        # #CRITICAL: concurrency: declared here (not inside the try) so a
        # ConfigurationError raised while resolving the live adapter below
        # still leaves this name bound to the injected `provider` arg (often
        # None in production) for the finally guard's _record_failure call;
        # _provider_label/_model_label/_record_failure all tolerate None.
        # #VERIFY: see test_effective_provider_config_error_does_not_crash_finally
        # (added alongside this change) interrupts inside the resolution step.
        effective_provider: GenerationProvider | None = provider
        try:
            job_row = await _load_and_start_job(session, job_id)
            if job_row is None:
                # #CRITICAL: concurrency: another delivery already owns this
                # row. Mark completed so the finally guard does not force-fail a
                # job this run does not own, then exit without executing.
                # #VERIFY: test_reclaim_after_completed_run_does_not_re_execute.
                completed = True
                return
            # #CRITICAL: security: provider/model on a job's authoring_metadata
            # were already validated against the enabled allowlist at the
            # authoring-plan endpoint (story_requests/authoring_plan.py) before
            # the job was ever created; this only reads them back, it does not
            # re-validate, so no new unvalidated string can reach a live
            # provider from here.
            # #VERIFY: TestEffectiveProviderPerJobOverride and
            # test_worker.py::test_effective_provider_reads_job_authoring_override.
            authoring = (
                job_row.authoring_metadata
                if isinstance(job_row.authoring_metadata, dict)
                else None
            )
            if effective_provider is None:
                effective_provider = build_provider(
                    _default_settings,
                    provider_override=_authoring_provider_override(authoring),
                    model_override=_authoring_model_override(authoring),
                )
            concept_row, brief, pii = await _load_concept_and_pii(
                session, job_row, effective_provider=effective_provider
            )

            # ------------------------------------------------------------------
            # Run the generation pipeline. Wrap to persist failures.
            # ------------------------------------------------------------------
            try:
                # Route on the presence of a string skeleton_slug, NOT on the
                # dict being non-None. A fresh_generation automated_provider job
                # legitimately carries authoring_metadata = {"provider",
                # "model"} (no skeleton_slug) so the worker can resolve the
                # per-job provider override above; only true skeleton-fill jobs
                # (which always carry a string skeleton_slug) route to
                # _run_skeleton_fill. Everything else generates from scratch.
                # #CRITICAL: data-integrity: routing on `authoring is not None`
                # misroutes fresh_generation jobs into skeleton fill, which then
                # raises ResourceNotFoundError on the absent skeleton_slug.
                # #VERIFY: test_fresh_generation_with_provider_override_routes_to_generate_story.
                if authoring is not None and isinstance(
                    authoring.get("skeleton_slug"), str
                ):
                    outcome = await _run_skeleton_fill(
                        _SkeletonFillContext(
                            authoring=authoring,
                            brief=brief,
                            effective_provider=effective_provider,
                            pii=pii,
                            prep_model=job_row.model,
                        )
                    )
                else:
                    outcome = await generate_story(brief, effective_provider, pii)
            except Exception as exc:
                # #CRITICAL: data-integrity: a WS-2 fail-closed slot-binding
                # ValidationError (from generation.binding.bind_theme_to_contract
                # or render_bound_skeleton) carries its violation list in
                # exc.details["violations"], but job.error only stores the
                # first 512 chars of str(exc) (the message), which drops that
                # structured detail. Surface it onto job.report so an operator
                # can see exactly what the binder/renderer rejected instead of
                # a job row pointing at nothing informative.
                # #VERIFY: the bind-failure worker test asserts the violation
                # detail lands in the persisted report/error.
                violations = (
                    exc.details.get("violations")
                    if isinstance(exc, ValidationError)
                    else None
                )
                report: dict[str, object] | None = (
                    {"slot_binding_violations": violations}
                    if violations is not None
                    else None
                )
                # WS-7 D7 (design 6.1, 6.3): a bound-path skeleton-fill job that
                # fails its bind gets an honest CANNOT_CARRY interpretation on
                # BOTH the failed job report and the originating request row. The
                # reason (PERSONAL_DETAILS vs NO_CONFORMING_BINDING) is chosen by
                # exc.field provenance ONLY (CR-4); a fresh_generation, legacy,
                # or half-migrated failure is a no-op here. This does not change
                # job status/retry semantics: the job still fails below.
                report = await _record_cannot_carry_if_bound_path(
                    session,
                    job_row,
                    exc,
                    authoring=authoring,
                    brief=brief,
                    pii=pii,
                    report=report,
                )
                # Record failure and re-raise so RQ marks the job failed.
                await _record_failure(
                    session,
                    job_row,
                    exc,
                    provider=effective_provider,
                    report=report,
                )
                logger.exception(
                    "generation_job.pipeline_error",
                    job_id=str(job_id),
                    error=str(exc)[:512],
                )
                raise

            # ------------------------------------------------------------------
            # Stamp the outcome, persist, and moderate.
            # ------------------------------------------------------------------
            await _persist_passed_outcome(
                session,
                _PersistContext(
                    job_id=job_id,
                    job_row=job_row,
                    concept_row=concept_row,
                    effective_provider=effective_provider,
                    authoring=authoring,
                    pii=pii,
                ),
                outcome,
            )

            # WS-7 D6: project the refined interpretation (if any) onto the
            # originating request row, in the worker's own transaction. A
            # no-request job (fresh generation, authored/catalog) no-ops.
            await _update_request_interpretation(session, job_row, outcome)

            await session.commit()
            # #CRITICAL: concurrency: this is the ONLY place completed is set
            # True. It must stay immediately after the commit it certifies
            # (nothing may be inserted between them) so an interruption a
            # single line earlier still finds completed == False.
            completed = True
        finally:
            # #CRITICAL: timing/concurrency: an interrupt (RQ job_timeout
            # SIGALRM, process kill) landing anywhere above must not strand
            # the row at "queued"/"running" forever. Roll back BEFORE reading
            # so the read reflects the last durably committed state, never a
            # dirty in-memory write (e.g. status set to "passed" but never
            # committed). Full rationale in this function's docstring; pinned
            # by test_interrupted_job_records_failed_in_finally and
            # test_late_interrupt_during_persist_records_failed_not_passed.
            if not completed:
                await session.rollback()
                stranded = await session.get(GenerationJob, job_id)
                if stranded is not None and stranded.status in ("queued", "running"):
                    await _record_failure(
                        session,
                        stranded,
                        RuntimeError("interrupted"),
                        provider=effective_provider,
                        from_state=stranded.status,
                    )


def run_generation_job_sync(job_id_str: str) -> None:
    """Synchronous RQ entrypoint that dispatches to the async worker.

    RQ calls this function in a worker process. It converts ``job_id_str`` to
    a :class:`uuid.UUID` and delegates to :func:`run_generation_job` via
    :func:`asyncio.run`, which creates a fresh event loop per call (safe for
    RQ's process-per-job model).

    Args:
        job_id_str: The UUID string of the job to process, as stored when the
            job was enqueued by :func:`~cyo_adventure.generation.queue.enqueue_generation`.

    Raises:
        ValueError: If ``job_id_str`` is not a valid UUID string.
        Exception: Propagates any exception from :func:`run_generation_job`
            so RQ can record the failure.
    """
    asyncio.run(run_generation_job(uuid.UUID(job_id_str)))
