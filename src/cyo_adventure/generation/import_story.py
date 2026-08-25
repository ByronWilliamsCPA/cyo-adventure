"""Import an externally-authored filled story into the story store.

Gated by the same validator used by the generation worker, and screened by the
same moderation pipeline before it can leave ``draft``. Intended for use by the
cyo-author Claude Code authoring skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.database import apply_family_rls_context
from cyo_adventure.core.exceptions import (
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import ChildProfile, Concept, GenerationJob
from cyo_adventure.generation.authoring_metadata import (
    SKELETON_BAND_KEY,
    SKELETON_SLUG_KEY,
)
from cyo_adventure.generation.binding import (
    load_contract_for,
    personalizable_slot_ids,
    render_bound_skeleton,
)
from cyo_adventure.generation.fidelity_gate import run_stage1_gate
from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.generation.skeleton import load_skeleton
from cyo_adventure.generation.skeleton_match import resolve_skeleton_path
from cyo_adventure.moderation import run_moderation_pipeline
from cyo_adventure.moderation.personalizable_slots import (
    PERSONALIZABLE_SLOTS_UNSET,
    PersonalizableSlots,
    PersonalizableSlotsArg,
    PersonalizableSlotsUnrecoverable,
    personalizable_slot_ids_for_job,
)
from cyo_adventure.storybook.reinsertion import (
    manifest_carries_tokens,
    reinsert_storybook,
    verify_manifest,
)
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.gate import run_fill_gate
from cyo_adventure.validator.sentinel_integrity import check_sentinel_integrity_at_rest

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

# Every job resumed by resume_manual_fill produces a fresh Storybook, so its
# sole version is 1, mirroring generation/worker.py's _FIRST_VERSION.
_FIRST_VERSION = 1

# Sentinel recorded on StorybookVersion.provider for a version created via
# this offline authoring import path, distinguishing it from a real generation
# provider name ("mock", "anthropic", ...) stamped by generation/worker.py.
# Public: api/remoderate.py must recognize it to avoid handing a provenance
# marker to generation.provider.build_provider as if it named a provider.
IMPORT_PROVIDER = "import"


@dataclass(frozen=True, slots=True)
class ImportRequest:
    """Caller-supplied inputs for import_filled_story.

    Attributes:
        family_id: Owning family (the ownership boundary).
        blob: The filled Storybook JSON as a dict.
        created_by: Optional authoring user id.
        model: Optional model identifier (e.g. the fill model).
        prompt_version: Skill/prompt version recorded on the version.
        review_model_override: Optional admin-chosen override for the Stage 2
            moderation review model, threaded into ``run_moderation_pipeline``.
            Mirrors ``generation/worker.py::run_generation_job``'s own
            ``authoring_metadata.get("review_stage2_model")`` read, so the
            skill-authored resume path (``resume_manual_fill``) honors the
            same per-job override the automated_provider path already does.
        skeleton_slug: The production skeleton this filled version was
            authored from, threaded into ``StorybookParams`` so
            ``storybook_version.skeleton_slug`` provenance is recorded for
            skill-authored versions too (WS-C PR2 final review I1: the
            recency-weighted pick reads this column, so a NULL here silently
            exempts skill-authored families from that weighting).
        sentinel_manifest: The manifest the pre-persist reinsertion transform
            produced for ``blob``, threaded into ``StorybookParams`` so this
            path records the same at-rest evidence the automated fill path
            does (ADR-023 Task R3). None for a caller that ran no transform.
    """

    family_id: uuid.UUID
    blob: dict[str, object]
    created_by: uuid.UUID | None = None
    model: str | None = None
    prompt_version: str = "skeleton-fill-v1"
    review_model_override: str | None = None
    skeleton_slug: str | None = None
    sentinel_manifest: dict[str, object] | None = None


async def import_filled_story(
    session: AsyncSession,
    request: ImportRequest,
    *,
    personalizable_slots: PersonalizableSlotsArg = PERSONALIZABLE_SLOTS_UNSET,
) -> str:
    """Validate a filled story and persist it if the gate does not block.

    Args:
        session: Open async session; caller owns the transaction.
        request: The grouped import inputs (see :class:`ImportRequest`).
        personalizable_slots: Task 6c pass-through to
            :func:`~cyo_adventure.moderation.pipeline.run_moderation_pipeline`'s
            own same-named parameter. Left at its default for every caller
            except :func:`resume_manual_fill`, which resolves this itself
            (see that function's docstring) and threads the result through
            here so the moderation-entry backstop uses the identical slot
            set the resume path's own pre-persist check used, instead of
            re-resolving it from the database (where, at this point in
            :func:`resume_manual_fill`'s call sequence, the job is not yet
            linked to ``story_id``).

    Returns:
        The persisted story id (the blob's ``id``). The story leaves ``draft``
        for ``in_review`` (clean or repaired) or ``needs_revision`` (hard
        block) before this returns; it is never left as an unscreened draft.

    Raises:
        ValidationError: If the validation gate blocks the story, or the blob has
            no string id.
        ProjectBaseError: Propagated, uncaught, from the post-persist moderation
            pipeline call below (e.g. ResourceNotFoundError, or an
            ExternalServiceError from a review-backend failure). Unlike
            generation/worker.py, this function does not own the transaction, so
            it does not catch or reinterpret a moderation failure; the caller's
            session close/rollback (core/database.py::get_session) is what keeps
            a failed import from leaving a half-committed row.
    """
    # #CRITICAL: data-integrity: the gate result and the blob must agree on id;
    # if the blob's id is missing or wrong, the stored version row is unreachable.
    # #VERIFY: test_import_persists_a_valid_filled_story asserts story_id == blob["id"].
    # AL-325: this endpoint imports a *filled* story, so a retained
    # "<<FILL" directive means the blob was never written and PL-27 must
    # reject it. Every other checker abstains on a directive body rather
    # than failing, so without the posture an unwritten book imports clean.
    # Called inline, NOT via run_sync(..., limiter=gate_limiter()) the way
    # api/remoderate.py calls it. The gate is CPU-bound and measured at ~50s
    # worst case, so on a request path that would stall the event loop; here
    # there is no event loop to stall that anyone else shares. Every caller of
    # import_filled_story is offline: import_cli, import_catalog,
    # resume_manual_fill, and scripts/series_e2e_local.py. No router reaches
    # it, so the shared capacity limiter would only serialize an operator
    # against himself.
    # #ASSUME: concurrency: no FastAPI route ever calls import_filled_story.
    # #VERIFY: tests/unit/test_gate_capacity_limiter.py::
    # test_both_gate_call_sites_share_one_limiter covers the api package and
    # rejects exactly this inline shape there; the day a router does import
    # this, that test must grow to reach it and this call has to move behind
    # run_sync.
    result = run_fill_gate(request.blob)
    if result.blocked:
        messages = (
            "; ".join(f.message for f in result.report.errors)
            or "no error details available"
        )
        msg = f"filled story blocked by validation gate: {messages}"
        raise ValidationError(msg)

    story_id = request.blob.get("id")
    if not isinstance(story_id, str) or not story_id:
        msg = "filled story has no string id"
        raise ValidationError(msg)

    # #CRITICAL: data integrity: this is the import/resume path's ONLY
    # computation of personalization_eligible; the reader (api/library.py,
    # D8) trusts the persisted column verbatim. True requires BOTH a real,
    # non-empty declared personalizable-slot set AND a manifest that actually
    # tallies at least one surviving sentinel. Manifest PRESENCE alone is not
    # enough: `build_manifest` returns `{"tokens": {}}` rather than `None` for
    # a document carrying no sentinel, so a presence test would stamp True for
    # a blob with nothing to personalize, contradicting the column's contract
    # in db/models.py. `manifest_carries_tokens` is the shared predicate.
    # `personalizable_slots` is a tri-state (see
    # moderation/personalizable_slots.py): a genuine frozenset (possibly
    # empty), `PERSONALIZABLE_SLOTS_UNRECOVERABLE` (contract uncomputable,
    # fail closed), or the
    # `PERSONALIZABLE_SLOTS_UNSET` marker for callers (import_cli.py,
    # import_catalog.py) that never resolved it because they also never
    # populate `request.sentinel_manifest`; the `isinstance` check below
    # normalizes UNSET to falsy explicitly rather than relying on the manifest
    # leg alone to coincidentally cancel it out.
    # #VERIFY: tests/unit/test_import_story.py::test_import_stamps_personalization_eligible_when_contract_declares_slots,
    # tests/unit/test_import_story.py::test_import_leaves_personalization_eligible_false_without_manifest,
    # tests/unit/test_import_story.py::test_import_leaves_personalization_eligible_false_for_empty_manifest.
    declared_slots = (
        personalizable_slots if isinstance(personalizable_slots, frozenset) else None
    )
    personalization_eligible = bool(declared_slots) and manifest_carries_tokens(
        request.sentinel_manifest
    )

    params = StorybookParams(
        story_id=story_id,
        blob=request.blob,
        family_id=request.family_id,
        created_by=request.created_by,
        model=request.model,
        prompt_version=request.prompt_version,
        provider=IMPORT_PROVIDER,
        validation_report=result.report.to_dict(),
        skeleton_slug=request.skeleton_slug,
        sentinel_manifest=request.sentinel_manifest,
        personalization_eligible=personalization_eligible,
    )
    await persist_storybook(session, params)

    # #CRITICAL: security: closes C3-SAFETY Finding 1 (adversarial-safety-
    # evaluation.md): import_filled_story used to persist a draft and stop,
    # leaving an externally-authored story (e.g. the cyo-author skeleton-fill
    # route) reachable by admin submit/approve with zero content screening.
    # This calls the same run_moderation_pipeline as generation/worker.py, but
    # NOT identically: worker.py wraps this call in try/except and does its own
    # rollback/status bookkeeping on failure, while this function deliberately
    # lets a moderation-pipeline exception propagate uncaught (see the Raises:
    # section above) because it does not own the transaction.
    # publishing.service.approve additionally refuses to publish any version
    # with moderation_report=None (Finding 2's structural backstop), so this
    # call is defense in depth, not the sole gate.
    # #VERIFY: test_import_screens_the_persisted_story /
    # test_import_propagates_moderation_failure.
    #
    # #CRITICAL: security: this reads child_profile, an ADR-022 Tier 1 table,
    # from OUTSIDE the request path, so nothing has set the app.family_id GUC
    # the family_scoped policy reads. Post-ADR-021-cutover the import CLIs run
    # as a non-owner role, and without this context the SELECT returns zero
    # rows: not an error, an EMPTY child_names set. The import then succeeds
    # while the moderation pass runs with no PII context and cannot recognize
    # a real child's name in the generated prose. Fail-closed at the database
    # becomes fail-OPEN at the safety gate, silently.
    # family_id is derived from the persisted request, never from story
    # content, and set_config's is_local => true scopes the GUC to this
    # transaction, so it reverts with the caller's COMMIT/ROLLBACK and cannot
    # bleed into the next user of a pooled connection.
    # #VERIFY: test_import_sets_rls_context_before_reading_child_profiles pins
    # the ordering; tests/integration/test_rls_tier1_enforcement.py covers the
    # unset (fail-closed) and set (per-family) paths as the cyo_api role;
    # docs/operations/runbook.md section 11.3 lists the import CLIs.
    await apply_family_rls_context(session, family_id=request.family_id, is_admin=False)
    child_result = await session.execute(
        select(ChildProfile.display_name).where(
            ChildProfile.family_id == request.family_id
        )
    )
    child_names: frozenset[str] = frozenset(row for (row,) in child_result.all() if row)
    pii = PiiContext(child_names=child_names)

    await run_moderation_pipeline(
        session=session,
        story_id=story_id,
        version=params.version,
        settings=_default_settings,
        # Family-serving: this import is scoped to a family story request,
        # so the moderation provider runs on the restricted lane (D1,
        # 2026-08-23, UW-C346).
        generation_provider=build_provider(_default_settings, lane="family"),
        pii=pii,
        review_model_override=request.review_model_override,
        personalizable_slots=personalizable_slots,
    )

    return story_id


def _str_meta(metadata: object, key: str) -> str | None:
    """Read a string value from a job's ``authoring_metadata``, tolerating junk.

    Args:
        metadata: The job's ``authoring_metadata`` (expected dict, but any type
            is tolerated).
        key: The metadata key to read.

    Returns:
        The value at ``key`` only when ``metadata`` is a dict and the value is a
        string; any other shape degrades to ``None`` (no override) instead of
        raising, matching the defensive reads in generation/worker.py.
    """
    # #ASSUME: data-integrity: authoring_metadata is a plain dict for every
    # method="skeleton_fill" job (see story_requests/authoring_plan.py); a
    # missing/wrong-typed value degrades to "no override" instead of raising.
    # #VERIFY: test_review_model_overrides_are_threaded_through_resume.
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _dict_meta(metadata: object, key: str) -> dict[str, str] | None:
    """Read a ``dict[str, str]`` value from a job's ``authoring_metadata``.

    Mirrors :func:`_str_meta`'s defensive posture, but for the WS-2
    ``slot_bindings`` shape (:class:`~cyo_adventure.generation.authoring_metadata.SkeletonAuthoringMetadata`),
    a flat slot-id-to-value map rather than a scalar string.

    Args:
        metadata: The job's ``authoring_metadata`` (expected dict, but any
            type is tolerated).
        key: The metadata key to read.

    Returns:
        The value at ``key`` only when ``metadata`` is a dict and the value
        is itself a dict whose keys and values are all strings; any other
        shape (missing key, wrong type, non-string key/value) degrades to
        ``None`` (no recorded binding) instead of raising.
    """
    # #ASSUME: data-integrity: a recorded slot_bindings entry is a plain
    # dict[str, str] written by the import CLI for a parameterized-skeleton
    # skill fill; a missing/wrong-typed value degrades to "use
    # contract.default_binding instead" rather than raising, matching
    # _str_meta's defensive reads of the other authoring_metadata keys.
    # #VERIFY: test_recorded_slot_bindings_are_preferred_over_default_binding.
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    if not isinstance(value, dict):
        return None
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        return None
    return cast("dict[str, str]", value)


def _resolve_resume_band(job: GenerationJob, concept: Concept) -> str:
    """Return the age-band directory segment to load a resumed fill's skeleton from.

    Args:
        job: The parked GenerationJob being resumed.
        concept: The job's concept, whose brief carries the request's own band.

    Returns:
        The job's stored ``skeleton_band`` when present (the OVERRIDE
        skeleton's real band, WS-C PR2 final review C1), otherwise the
        concept's own brief ``age_band``, or ``""`` if neither is a string.

    #ASSUME: data-integrity: prefer the stored skeleton_band over the
    concept's own brief age_band, which is wrong for a cross-band admin
    override; fall back to the concept's band only for a pre-fix job whose
    authoring_metadata predates this key.
    #VERIFY: cross-band resume test asserting the stored band is used to
    build skeletons/<band>/<slug>.json.
    """
    stored_band = _str_meta(job.authoring_metadata, SKELETON_BAND_KEY)
    if stored_band is not None:
        return stored_band
    band = concept.brief.get("age_band") if isinstance(concept.brief, dict) else None
    return band if isinstance(band, str) else ""


def _load_resume_skeleton(band: str, skeleton_slug: str) -> dict[str, object]:
    """Load the skeleton a parked fill was matched against, as a clean error.

    Args:
        band: The age-band directory segment (may be "").
        skeleton_slug: The matched skeleton's filename stem.

    Returns:
        The parsed skeleton document.

    Raises:
        ResourceNotFoundError: If the skeleton file no longer exists.
        ValidationError: If the skeleton file is unreadable or not valid JSON.
    """
    # #ASSUME: external-resources: re-reads the same skeleton file the
    # authoring-plan endpoint matched (see generation/skeleton_match.py); a file
    # moved or corrupted since matching raises a raw FileNotFoundError/JSON
    # error, which is not a ProjectBaseError. Map those to the project hierarchy
    # so import_cli's top-level handler reports a clean "import failed" instead
    # of a raw traceback; the caller still rolls back cleanly (no orphaned job).
    # #VERIFY: test_resume_missing_skeleton_file_is_clean_error.
    skeleton_path = resolve_skeleton_path(band, skeleton_slug)
    try:
        return load_skeleton(skeleton_path)
    except FileNotFoundError as exc:
        msg = f"skeleton file not found for resume: {skeleton_path}"
        raise ResourceNotFoundError(
            msg, resource_type="Skeleton", resource_id=skeleton_slug
        ) from exc
    except (OSError, ValueError) as exc:
        msg = f"skeleton for resume is unreadable or invalid: {skeleton_path}"
        raise ValidationError(msg) from exc


def _stage1_reference_skeleton(
    band: str,
    skeleton_slug: str,
    original_skeleton: dict[str, object],
    job: GenerationJob,
) -> tuple[dict[str, object] | None, str | None]:
    """Return the Stage 1 fidelity reference for a resumed skill fill.

    For a legacy (unparameterized) skeleton -- no ``<slug>.contract.json``
    sidecar -- the reference is ``original_skeleton`` itself, byte-identical
    to pre-WS-2 behavior. For a parameterized skeleton, the reference must
    instead be the BOUND skeleton: ``original_skeleton`` still carries
    ``{SLOT}`` tokens in its beats/title/label surfaces (WS-2 design section
    5.1), so comparing a fill against it as-is would compare theme'd prose
    against literal placeholder tokens and false-flag the fill. The bound
    reference is rendered from the job's recorded
    ``authoring_metadata["slot_bindings"]`` (the theme the skill actually
    filled) when present, else the contract's ``default_binding``
    (reproducing the classic-story reference), per
    ``docs/planning/ws2-parameterized-catalog-design.md`` section 5.3.

    Args:
        band: The age-band directory segment the skeleton was resolved from
            (see :func:`_resolve_resume_band`).
        skeleton_slug: The matched skeleton's filename stem.
        original_skeleton: The raw skeleton document, already loaded (see
            :func:`_load_resume_skeleton`).
        job: The parked GenerationJob being resumed, for its
            ``authoring_metadata["slot_bindings"]``.

    Returns:
        ``(reference_skeleton, None)`` on success. ``(None, error_message)``
        when a parameterized skeleton's contract cannot be loaded/cross-
        checked, or its bind/render post-conditions fail (e.g. a stale
        recorded binding that no longer validates): the caller must treat
        this as a degrade-to-``needs_review`` signal, never a crash, since by
        the time this runs the story is already persisted and moderated.
    """
    # #CRITICAL: data-integrity: a stale recorded `slot_bindings`, a
    # contract/skeleton slot-token drift, or any other bind/render
    # post-condition failure (render_bound_skeleton's four post-conditions)
    # must not crash or strand an already-persisted, already-moderated
    # resume; the caller degrades to needs_review on a `(None, ...)` return
    # instead of letting a ValidationError propagate uncaught.
    # #VERIFY: tests/unit/test_resume_manual_fill_stage1.py::
    # test_parameterized_skeleton_uses_bound_skeleton_as_stage1_reference,
    # ::test_recorded_slot_bindings_are_preferred_over_default_binding,
    # ::test_default_binding_used_when_no_slot_bindings_recorded,
    # ::test_legacy_skeleton_resume_reference_is_unchanged,
    # ::test_contract_render_error_degrades_to_needs_review.
    try:
        skeleton_path = resolve_skeleton_path(band, skeleton_slug)
        contract = load_contract_for(skeleton_path, original_skeleton)
    except ValidationError as exc:
        return None, str(exc)
    if contract is None:
        return original_skeleton, None

    recorded_bindings = _dict_meta(job.authoring_metadata, "slot_bindings")
    bindings = (
        recorded_bindings if recorded_bindings is not None else contract.default_binding
    )
    personalizable_slots = personalizable_slot_ids(contract)
    try:
        return (
            render_bound_skeleton(original_skeleton, bindings, personalizable_slots),
            None,
        )
    except ValidationError as exc:
        return None, str(exc)


@dataclass(frozen=True, slots=True)
class _ResumeStage1Context:
    """Grouped parameters for :func:`_finalize_resume`.

    Bundled into one object (mirroring ``generation/worker.py``'s
    ``_SkeletonFillContext``) so the function stays under the project's
    argument-count limit while keeping each field explicit.

    Attributes:
        job: The parked GenerationJob being resumed (its ``storybook_id``/
            ``version`` are already linked to the persisted story by the
            caller before this context is built).
        skeleton_slug: The job's matched skeleton slug, or ``None`` if the
            job carries no skeleton provenance (Stage 1 is skipped entirely).
        original_skeleton: The raw skeleton loaded before persisting (see
            :func:`_load_resume_skeleton`), or ``None`` if it could not be
            loaded.
        skeleton_load_error: The load failure message, only meaningful when
            ``original_skeleton`` is ``None``.
        reference_skeleton: The Stage 1 fidelity reference (see
            :func:`_stage1_reference_skeleton`), already computed by the
            caller (:func:`resume_manual_fill`) BEFORE the story was
            persisted -- this is the same artifact the new pre-persist
            sentinel-integrity check (Task 6b) reuses, so it is threaded
            through rather than recomputed a second time here. ``None`` when
            ``original_skeleton`` is ``None``, or when the contract/render
            step itself failed.
        reference_error: The reference-build failure message, only
            meaningful when ``reference_skeleton`` is ``None`` and
            ``original_skeleton`` is not ``None`` (a contract/render
            failure, as opposed to a skeleton-load failure).
        blob: The filled Storybook JSON being resumed.
    """

    job: GenerationJob
    skeleton_slug: str | None
    original_skeleton: dict[str, object] | None
    skeleton_load_error: str | None
    reference_skeleton: dict[str, object] | None
    reference_error: str | None
    blob: dict[str, object]


async def _finalize_resume(session: AsyncSession, ctx: _ResumeStage1Context) -> str:
    """Run the Stage 1 fidelity gate (if applicable) and commit the job's final status.

    Mirrors the shape of the missing-skeleton-file degradation
    (:func:`_stage1_reference_skeleton`'s docstring) for every way Stage 1
    can fail to run at all: a job with no ``skeleton_slug`` skips straight to
    "passed" (no Stage 1 possible); a skeleton that could not be loaded, or a
    parameterized skeleton whose contract/render step failed, both degrade to
    "needs_review" without raising, since ``ctx.job.storybook_id``/``version``
    are already linked to a story that is already persisted and moderated by
    the time this runs. Only an actual Stage 1 fidelity violation (the gate
    ran and found a mismatch) and a clean pass are distinguished beyond that.

    Args:
        session: Open async session; every branch below commits the job row
            directly (this function owns that commit, mirroring
            :func:`resume_manual_fill`'s own documented commit contract).
        ctx: The grouped resume context (see :class:`_ResumeStage1Context`).

    Returns:
        The job's final status: ``"needs_review"`` or ``"passed"``.
    """
    job = ctx.job
    if ctx.skeleton_slug is None:
        job.status = "passed"
        await session.commit()
        return "passed"

    if ctx.original_skeleton is None:
        # #CRITICAL: data-integrity: the skeleton could not be loaded even
        # before persisting (moved/removed at any point since the
        # authoring-plan match, or concurrently). The story already exists
        # and passed moderation; it just cannot be re-verified against its
        # origin skeleton, so this is a needs_review downgrade, never a
        # stuck "awaiting_manual_fill" job (#128).
        # #VERIFY: covered at the unit level by monkeypatching
        # load_skeleton to raise; no dedicated real-file test for this
        # branch since it degenerates to the same missing-file mechanics
        # test_resume_survives_skeleton_file_deleted_after_persist proves.
        job.status = "needs_review"
        job.error = (
            ctx.skeleton_load_error or "matched skeleton unavailable for Stage 1 gate"
        )[:512]
        await session.commit()
        return "needs_review"

    # #CRITICAL: data-integrity: for a WS-2 parameterized skeleton, the
    # Stage 1 reference must be the BOUND skeleton, not the raw
    # {SLOT}-bearing one just loaded above (see _stage1_reference_skeleton's
    # docstring); a legacy skeleton is unaffected. ``ctx.reference_skeleton``
    # is ``None`` when the contract/render step itself failed (e.g. a stale
    # recorded binding) -- degrade to needs_review exactly like the missing-
    # skeleton-file branch above, never crash or strand this already-
    # persisted, already-moderated resume. This reference was already
    # computed once, before the story was persisted, by
    # :func:`resume_manual_fill` (Task 6b): reused here rather than
    # recomputed, so a resume never does the contract/render step twice.
    # #VERIFY: tests/unit/test_resume_manual_fill_stage1.py (see the helper's
    # own docstring for the full test list).
    if ctx.reference_skeleton is None:
        job.status = "needs_review"
        job.error = f"could not build Stage 1 reference: {ctx.reference_error}"[:512]
        await session.commit()
        return "needs_review"

    pii = PiiContext(child_names=frozenset())
    review_stage1_model = _str_meta(job.authoring_metadata, "review_stage1_model")
    violations = await run_stage1_gate(
        ctx.reference_skeleton,
        ctx.blob,
        review_stage1_model=review_stage1_model,
        prep_model=job.model,
        settings=_default_settings,
        pii=pii,
    )
    if violations:
        # #CRITICAL: data-integrity: storybook_id/version were already
        # linked above; only status/error differ from the clean-pass branch
        # below, mirroring the automated_provider mechanism's own Stage 1
        # downgrade in worker.py::run_generation_job, which persists the
        # storybook and still marks the job needs_review.
        # #VERIFY: covered by test_stage1_violations_are_recorded_on_the_job
        # in the unit test file, which checks the job's storybook_id and
        # version fields are both populated alongside needs_review.
        job.status = "needs_review"
        job.error = "; ".join(violations)[:512]
        await session.commit()
        return "needs_review"

    job.status = "passed"
    await session.commit()
    return "passed"


@dataclass(frozen=True, slots=True)
class _ResumeSentinelReinsertionContext:
    """Grouped parameters for :func:`_reinsert_and_verify_resume_sentinels`.

    Bundled into one object (mirroring :class:`_ResumeStage1Context` above)
    so the function stays under the project's argument-count limit while
    keeping each field explicit.

    Attributes:
        job: The in-memory GenerationJob row being resumed.
        job_id: The job id, for log/error context.
        skeleton_slug: The matched skeleton slug, for log context.
        reference_skeleton: The Stage 1 fidelity reference
            (:func:`_stage1_reference_skeleton`'s output), the source of
            truth `reinsert_storybook` derives every reinsertable token from.
        blob: The filled Storybook JSON to transform.
        personalizable_slots: The story's declared personalizable-slot set,
            or :data:`~cyo_adventure.moderation.personalizable_slots.PERSONALIZABLE_SLOTS_UNRECOVERABLE`
            when the contract itself is unrecoverable. The at-rest corruption
            re-scan only runs when this is a real ``frozenset`` (Task 6c, M1);
            an unrecoverable contract here is left for the moderation-entry
            backstop to fail closed on instead.
    """

    job: GenerationJob
    job_id: uuid.UUID
    skeleton_slug: str
    reference_skeleton: dict[str, object]
    blob: dict[str, object]
    personalizable_slots: PersonalizableSlots


async def _reinsert_and_verify_resume_sentinels(
    session: AsyncSession, ctx: _ResumeSentinelReinsertionContext
) -> tuple[dict[str, object], dict[str, object]]:
    """Derive the pre-persist blob via reinsertion and verify it fails closed.

    Extracted from :func:`resume_manual_fill` (ADR-023 Stage R / Task R3) to
    keep that function's cyclomatic complexity under the project's Ruff C901
    gate; the two checks below are the same derive-not-prescribe sequence
    generation/worker.py::_run_skeleton_fill runs, applied to this path's
    reference skeleton and filled blob before ``import_filled_story`` (and
    thus its ``persist_storybook`` call) ever sees them.

    Args:
        session: Open async session; used only to commit the job row's
            failure state before a raise, matching resume_manual_fill's own
            failure-commit-then-reraise contract.
        ctx: The grouped reinsertion context (see
            :class:`_ResumeSentinelReinsertionContext`).

    Returns:
        tuple[dict[str, object], dict[str, object]]: The transform's derived
        document, to replace ``blob`` in the caller, and the manifest it
        produced, which the caller threads to ``persist_storybook`` so
        ``storybook_version.sentinel_manifest`` records what this path
        actually re-inserted (ADR-023 Task R3). The manifest is derived here
        and nowhere else on this path, so dropping it would leave the column
        NULL for every skill-authored version.

    Raises:
        ValidationError: If the transform fails its own manifest (a
            transform bug, not a fill-content problem) or the derived
            document fails the at-rest sentinel-integrity re-scan. Either
            case marks the job "failed" and commits before raising, per
            resume_manual_fill's failure-commit-then-reraise pattern.
    """
    job = ctx.job
    job_id = ctx.job_id
    skeleton_slug = ctx.skeleton_slug
    personalizable_slots = ctx.personalizable_slots

    reinsertion_outcome = reinsert_storybook(ctx.reference_skeleton, ctx.blob)
    document = reinsertion_outcome.document

    if not verify_manifest(document, reinsertion_outcome.manifest):
        # verify_manifest rebuilds a reference document from the manifest it
        # is passed and re-runs the prescriptive check against the document
        # that manifest was derived from, so it passes by construction when
        # both come from the same reinsert_storybook call. A failure here
        # means reinsert_storybook itself produced a document its own
        # manifest cannot account for: a transform bug, not a fill-content
        # problem.
        logger.error(
            "resume_manual_fill.sentinel_manifest_verification_failed",
            job_id=str(job_id),
            skeleton_slug=skeleton_slug,
        )
        msg = (
            f"reinsertion transform for job {job_id} produced a "
            "document that fails its own manifest"
        )
        job.status = "failed"
        job.error = msg[:512]
        await session.commit()
        raise ValidationError(
            msg,
            field="sentinel_integrity",
            details={"sentinel_integrity_violations": []},
        )

    if not isinstance(personalizable_slots, PersonalizableSlotsUnrecoverable):
        at_rest_result = check_sentinel_integrity_at_rest(
            document, personalizable_slots
        )
        if not at_rest_result.ok:
            # Redact the raw sentinel token from the log payload as
            # defense-in-depth; node_id + kind fully classify+locate each
            # violation, and the token holds only a generic default
            # server-side, never resolved child data.
            violation_details = [
                {"node_id": v.node_id, "kind": v.kind}
                for v in at_rest_result.violations
            ]
            logger.error(
                "resume_manual_fill.sentinel_integrity_violation",
                job_id=str(job_id),
                skeleton_slug=skeleton_slug,
                violations=violation_details,
            )
            msg = (
                f"filled story for job {job_id} failed sentinel integrity: "
                f"{len(violation_details)} violation(s)"
            )
            job.status = "failed"
            job.error = msg[:512]
            await session.commit()
            raise ValidationError(
                msg,
                field="sentinel_integrity",
                details={"sentinel_integrity_violations": violation_details},
            )

    return document, reinsertion_outcome.manifest


async def resume_manual_fill(
    session: AsyncSession,
    job_id: uuid.UUID,
    blob: dict[str, object],
    *,
    model: str | None = None,
) -> tuple[str, str]:
    """Resume a skill-authored skeleton fill parked at "awaiting_manual_fill".

    Loads the job's concept for its family_id, then, when the job carries a
    ``skeleton_slug`` and its matched skeleton loaded successfully, computes
    the Stage 1 fidelity reference (:func:`_stage1_reference_skeleton`) and
    runs the ADR-023 Stage R strip-all-then-reinsert step against it BEFORE
    persisting anything (:func:`_reinsert_and_verify_resume_sentinels`,
    replacing Task 6b's prescriptive
    :func:`~cyo_adventure.validator.sentinel_integrity.check_sentinel_integrity`
    call): the transform's own manifest must account for its output, and the
    derived document must pass
    :func:`~cyo_adventure.validator.sentinel_integrity.check_sentinel_integrity_at_rest`.
    Either failure marks the job "failed" and raises, so the blob is never
    persisted. A sentinel the fill merely paraphrased away is no longer a
    violation: it is re-derived. Only then does this function
    delegate to :func:`import_filled_story` for the same gate + persist +
    moderation pipeline every other import uses, threading the job's own
    ``authoring_metadata.get("review_stage2_model")`` override through as
    ``ImportRequest.review_model_override``. On success the job is marked
    "passed" and linked to the new storybook. If the job carries a
    ``skeleton_slug``, the Stage 1 fidelity gate also runs afterward (using
    ``authoring_metadata.get("review_stage1_model")`` as its own override,
    same source dict, different key); a fidelity violation marks the job
    "needs_review" instead of "passed", but the job is still linked to the
    storybook :func:`import_filled_story` already persisted (only
    status/error differ between the two outcomes -- neither branch orphans
    the job row from its story). For a WS-2 parameterized skeleton (a
    ``<slug>.contract.json`` sidecar exists), the Stage 1 reference is the
    BOUND skeleton -- rendered from the job's recorded
    ``authoring_metadata["slot_bindings"]`` when present, else the contract's
    ``default_binding`` -- never the raw ``{SLOT}``-bearing skeleton; a
    legacy skeleton is unaffected. A bind/render failure at this point (e.g.
    a stale recorded binding) also downgrades to "needs_review" rather than
    raising, since the story is already persisted and moderated. On a
    validation-gate block the job is
    marked "failed" and the error is recorded before the exception
    propagates, mirroring generation/worker.py's failure-commit-then-reraise
    pattern. Unlike import_filled_story (which deliberately does not own the
    transaction -- see its own docstring), this function commits the job row's
    status itself for every HANDLED outcome (gate block -> "failed", Stage 1
    downgrade -> "needs_review", clean -> "passed"), so a caller-side rollback
    cannot silently discard a recorded outcome. An UNEXPECTED exception after
    the storybook was persisted (a provider error in the semantic check) is
    deliberately NOT committed here: it propagates and the caller's session
    rolls back, discarding the just-persisted story so the job stays
    "awaiting_manual_fill" for a clean retry (never orphaned).

    The matched skeleton library file is loaded BEFORE the story is persisted
    (closes #128), not re-read afterward: the file may be moved, renamed, or
    removed at any point in the job's lifetime (it is static production
    content matched at authoring-plan time, possibly long before a skill
    resumes it), and a re-read after persisting used to raise an uncaught
    ResourceNotFoundError, stranding the job at "awaiting_manual_fill" despite
    a real, already-persisted story existing for it. Loading first means the
    in-memory snapshot survives even if the file is deleted later in this same
    call. If the file cannot be loaded at all (missing even at this earlier
    point), the Stage 1 gate is skipped and the job is marked "needs_review"
    instead of being stranded: the story already exists and passed moderation,
    it just cannot be re-verified against its origin skeleton.

    Task 6c (whole-branch review findings I1/I2/M1): this function also
    resolves the story's declared personalizable-slot set itself, from the
    in-memory ``job`` and the band already resolved above
    (:func:`_resolve_resume_band`'s brief-band fallback), and threads it
    through :func:`import_filled_story` into
    :func:`~cyo_adventure.moderation.pipeline.run_moderation_pipeline`'s
    entry-level sentinel-integrity backstop. Resolving it here, rather than
    letting that backstop resolve it from the database as it does for every
    other caller, closes two gaps the Task 6a backstop introduced on this
    path specifically: the backstop's own ``GenerationJob`` lookup is keyed
    on ``storybook_id``, which this function does not set until AFTER
    :func:`import_filled_story` (and thus the moderation pass) returns (I1:
    without this fix, the backstop would always see "no job" here and
    silently pass an empty slot set, which would wrongly reject a legitimate
    personalizable sentinel as an ``unknown_slot`` the moment a real
    personalizable contract ships); and the backstop's own band recovery
    reads only the raw ``authoring_metadata`` key, not this function's own
    brief-band fallback (I2). A resolution of ``None`` (the contract is
    genuinely uncomputable, as opposed to merely a render/binding failure)
    is threaded through unchanged and makes the moderation entry fail closed
    on this resume (M1), rather than the story silently persisting clean
    with no entry-level check at all.

    Args:
        session: Open async session; the story/version write still follows
            import_filled_story's own transaction contract, but this
            function's job-row updates are committed here directly.
        job_id: The GenerationJob row to resume.
        blob: The filled Storybook JSON, already loaded from disk.
        model: Optional model identifier to record (the fill model).

    Returns:
        A ``(story_id, status)`` pair: the persisted story id and the job's
        final status, either ``"passed"`` or ``"needs_review"`` (a Stage 1
        fidelity downgrade, or a skeleton the Stage 1 gate could not load). A
        hard gate block does not return; it raises.

    Raises:
        ResourceNotFoundError: If the job or its concept does not exist.
        StateTransitionError: If the job is not "awaiting_manual_fill".
        ValidationError: Raised BEFORE persisting if the pre-persist sentinel-
            integrity check (Task 6b) finds a dropped, forged, migrated, or
            malformed sentinel (the job is marked "failed" first); also
            propagated from import_filled_story if the validation gate
            blocks the filled story (the job is marked "failed" first,
            same as the sentinel-integrity case).
        ProjectBaseError: Propagated from the moderation pipeline on failure,
            same as import_filled_story (not intercepted here).
    """
    job = await session.get(GenerationJob, job_id)
    if job is None:
        msg = f"GenerationJob {job_id} not found"
        raise ResourceNotFoundError(
            msg, resource_type="GenerationJob", resource_id=str(job_id)
        )
    if job.status != "awaiting_manual_fill":
        msg = f"job is '{job.status}', not awaiting_manual_fill"
        raise StateTransitionError(msg)

    concept = await session.get(Concept, job.concept_id)
    if concept is None:
        msg = f"Concept {job.concept_id} not found"
        raise ResourceNotFoundError(
            msg, resource_type="Concept", resource_id=str(job.concept_id)
        )

    # #CRITICAL: external-resources: load the matched skeleton BEFORE
    # persisting the filled story, not after (#128). The skeleton library file
    # is read once here, into memory; even if it is moved or removed later in
    # this same call (or at any point before this call, since it may have been
    # matched long ago), the Stage 1 gate below still runs against this
    # captured snapshot -- or, if it could not be loaded at all, degrades to
    # a needs_review downgrade instead of stranding the job.
    # #VERIFY: integration test test_resume_survives_skeleton_file_deleted_after_persist
    # in tests/integration/test_resume_manual_fill.py exercises a real missing
    # file, not a monkeypatched load_skeleton.
    skeleton_slug = _str_meta(job.authoring_metadata, SKELETON_SLUG_KEY)
    original_skeleton: dict[str, object] | None = None
    skeleton_load_error: str | None = None
    # Initialized unconditionally (rather than only inside the `if` below) so
    # it is never "possibly unbound" at its second use further down (the
    # reference-computation block), which re-enters under the identical
    # `skeleton_slug is not None` guard; the "" default is never actually read
    # since that guard is always true whenever band is used again.
    band = ""
    if skeleton_slug is not None:
        band = _resolve_resume_band(job, concept)
        try:
            original_skeleton = _load_resume_skeleton(band, skeleton_slug)
        except (ResourceNotFoundError, ValidationError) as exc:
            skeleton_load_error = str(exc)

    # #CRITICAL: security: Task 6c (I1/I2). The moderation-entry Variant B
    # backstop (moderation/pipeline.py::run_moderation_pipeline) resolves the
    # story's declared personalizable-slot set via a `GenerationJob` lookup
    # keyed on `storybook_id`; on THIS path that link is not written until
    # `job.storybook_id = story_id` below, AFTER `import_filled_story` (and
    # thus the moderation pass) has already run. Resolving via that lookup
    # inside the pipeline would therefore always see "no job" and answer an
    # empty set (I1) -- fail-open for a legitimate sentinel the instant a real
    # personalizable contract ships. Resolved HERE instead, directly from the
    # in-memory `job` and the band this function has ALREADY correctly
    # resolved (`_resolve_resume_band`'s brief-band fallback, not the raw
    # `authoring_metadata` key alone, closing I2), then threaded through
    # `import_filled_story` into the moderation entry below, so it uses the
    # exact answer `personalizable_slot_ids_for_story` would have produced
    # for this job had it been linked in time -- never a guess. A `None`
    # result (contract genuinely uncomputable) is threaded through verbatim
    # too: the moderation entry backstop then fails closed on this resume
    # (M1), rather than the pre-Task-6c gap where an uncomputable contract
    # here silently persisted a clean-looking version with no entry-level
    # check at all.
    # #VERIFY: tests/unit/test_resume_manual_fill_personalizable_slots.py.
    personalizable_slots = personalizable_slot_ids_for_job(job, band=band)

    # #CRITICAL: security: a personalizable slot's sentinel-wrapped value is
    # the ONLY marker standing between an authored fill's free-text output
    # and a family's later personalization resolve; a dropped or forged
    # sentinel in a skill-authored/imported fill must not reach the
    # guardian/admin approval queue looking like ordinary prose (ADR-023 plan
    # section 3.2, "Fail closed"). G1 measurement showed the fill LLM
    # preserves a sentinel wrapper verbatim on only 3.3% of tokens (ADR-023
    # Stage R), so as of Task R3 this no longer prescribes the fill against a
    # reference and rejects a mismatch; it DERIVES the final blob from
    # `reference_skeleton` (the same pre-fill bound reference
    # `_finalize_resume`'s own Stage 1 gate uses) via the deterministic
    # strip-all-then-reinsert transform (`reinsert_storybook`), then verifies
    # the transform's own output against its own manifest before persisting
    # anything. Task 6a's moderation-entry Variant B backstop
    # (run_moderation_pipeline) remains blob-only and still cannot itself
    # catch a DROPPED sentinel by inspection alone; that gap is now closed by
    # construction instead, since the reinsertion transform re-derives every
    # reinsertable token from `reference_skeleton` rather than trusting
    # whatever the fill happened to contain. Run HERE, before
    # `import_filled_story` (and thus before its `persist_storybook` call)
    # runs, so a transform-bug blob is NEVER persisted, mirroring
    # generation/worker.py's own check (Task R3/4a): `blob` is reassigned to
    # the transform's derived document before any downstream use. Reuses the
    # EXISTING reference-skeleton production (`_stage1_reference_skeleton`,
    # the same artifact `_finalize_resume`'s Stage 1 fidelity gate consumes
    # below) rather than a second binding/contract-load path. This
    # pre-persist step itself is skipped (not run) when `reference_skeleton`
    # cannot be computed (skeleton unreadable, or a contract/render failure):
    # that already-existing degrade-to-needs_review case is left exactly as
    # it was pre-Task-6b (see `_finalize_resume`), which still runs and can
    # still downgrade the job's status, and `blob` is left byte-unchanged in
    # that case. The at-rest corruption re-scan
    # (`check_sentinel_integrity_at_rest`) only runs when `personalizable_slots`
    # is a real `frozenset` (Task 6c, M1): when the contract itself is
    # unrecoverable, this step is skipped and the moderation-entry backstop
    # this function threads `personalizable_slots` into (below) fails closed on
    # that same marker instead, so this is a deferred check, not a new gap. Also dormant, like the worker's own
    # check, whenever `personalizable_slot_ids` resolves empty (every
    # contract on disk today): the transform has no expected tokens to
    # reinsert, so it is a byte-identical no-op, and
    # `check_sentinel_integrity_at_rest` derives zero expected sentinels for
    # existing content. Its malformed-near-miss scan still runs
    # unconditionally, but fires only on genuinely sentinel-shaped tokens
    # ordinary prose never contains, so this stays byte-neutral for all real
    # sentinel-free content.
    # #VERIFY: test_resume_forged_sentinel_stripped_and_not_reinserted_pre_persist,
    # test_resume_manifest_verification_failure_marks_job_failed, and
    # test_resume_clean_sentinel_free_import_persists_unchanged in
    # tests/unit/test_resume_manual_fill_sentinel_integrity.py.
    reference_skeleton: dict[str, object] | None = None
    reference_error: str | None = None
    # Stays None when no transform ran (no skeleton_slug, an unreadable
    # skeleton, or an uncomputable reference): the column then honestly
    # records "nothing was re-inserted here" rather than an empty manifest
    # that would read as "the transform ran and found nothing".
    sentinel_manifest: dict[str, object] | None = None
    if skeleton_slug is not None and original_skeleton is not None:
        reference_skeleton, reference_error = _stage1_reference_skeleton(
            band, skeleton_slug, original_skeleton, job
        )
        if reference_skeleton is not None:
            blob, sentinel_manifest = await _reinsert_and_verify_resume_sentinels(
                session,
                _ResumeSentinelReinsertionContext(
                    job=job,
                    job_id=job_id,
                    skeleton_slug=skeleton_slug,
                    reference_skeleton=reference_skeleton,
                    blob=blob,
                    personalizable_slots=personalizable_slots,
                ),
            )

    review_stage2_model = _str_meta(job.authoring_metadata, "review_stage2_model")
    request = ImportRequest(
        blob=blob,
        family_id=concept.family_id,
        model=model,
        review_model_override=review_stage2_model,
        skeleton_slug=skeleton_slug,
        sentinel_manifest=sentinel_manifest,
    )
    try:
        story_id = await import_filled_story(
            session, request, personalizable_slots=personalizable_slots
        )
    except ValidationError as exc:
        # #CRITICAL: data-integrity: record the gate-block on the job row
        # before re-raising, mirroring worker.py's failure-commit-then-reraise
        # pattern, so import_cli's get_session context manager (which rolls
        # back on an exception exiting the `async with` block) cannot
        # silently discard this job's failure state.
        # #VERIFY: covered at the integration level (tests/integration/
        # test_resume_manual_fill.py::test_resume_gate_block_marks_job_failed);
        # this unit test file's fake session cannot exercise the real gate.
        job.status = "failed"
        job.error = str(exc)[:512]
        await session.commit()
        raise

    # import_filled_story already persisted a real Storybook + StorybookVersion
    # for story_id above; link the job to it now, before the Stage 1 check
    # below can downgrade the status, so neither outcome ever orphans the job
    # row from the story it produced (only status/error differ below).
    job.storybook_id = story_id
    job.version = _FIRST_VERSION

    status = await _finalize_resume(
        session,
        _ResumeStage1Context(
            job=job,
            skeleton_slug=skeleton_slug,
            original_skeleton=original_skeleton,
            skeleton_load_error=skeleton_load_error,
            reference_skeleton=reference_skeleton,
            reference_error=reference_error,
            blob=blob,
        ),
    )
    return story_id, status
