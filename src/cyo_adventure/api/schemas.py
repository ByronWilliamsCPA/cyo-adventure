"""Pydantic request and response models for the reader and generation APIs.

These are the wire contracts the frontend client is generated from. The
reading-state PUT body never carries a ``profile_id``: the profile is taken from
the path and validated against the token subject (IDOR defense).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.moderation.report import Source, Verdict
from cyo_adventure.storybook.evaluator import VarState
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle

# ---------------------------------------------------------------------------
# Reading-state resource bounds (audit Finding 8)
# ---------------------------------------------------------------------------
#
# Derivation (do not invent numbers; see the F8 commit body for the full
# reasoning): the largest currently-authored skeleton is
# skeletons/16+/the-ashfall-expedition.json with 505 nodes (16+ band, "long"
# gamebook, production_eligible). ``visit_set`` is the set of DISTINCT nodes
# entered in a reading session; a real story's distinct-visit count can never
# exceed its total node count, so 505 is the exact real ceiling. ``path`` is
# the FULL ordered visit history INCLUDING revisits (loop_and_grow topology
# stories legitimately revisit nodes), so it needs headroom above
# ``visit_set``; a 4x multiplier is a judgment call (not itself derived from
# repo data) sized to comfortably cover heavy backtracking without leaving the
# cap effectively unbounded.
_MAX_REAL_SKELETON_NODES = 505
VISIT_SET_MAX_LENGTH = _MAX_REAL_SKELETON_NODES
PATH_MAX_LENGTH = _MAX_REAL_SKELETON_NODES * 4

# Byte ceiling for the serialized save_slots payload. save_slots is
# arbitrary client-supplied game state persisted in a JSONB column; without a
# byte-size guard a client could submit a multi-megabyte blob (row/storage
# bloat, a DoS vector independent of the list-length caps above, since a dict
# has no natural "count" cap).
_SAVE_SLOTS_MAX_BYTES = 64_000


class ReadingStateBody(BaseModel):
    """A reading-state save submitted by the client (PUT body)."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    current_node: str = Field(min_length=1)
    var_state: VarState = Field(default_factory=dict)
    # #ASSUME: security: path/visit_set are client-supplied lists persisted to
    # a JSONB column; an unbounded list is a resource-exhaustion vector (a
    # malicious or buggy client could submit millions of entries). See the
    # module-level derivation comment above for how these caps were sized.
    # #VERIFY: tests/unit/test_schemas.py::test_path_over_max_length_rejected
    # and test_visit_set_over_max_length_rejected assert a 422 past the cap;
    # the ``_at_max_length_accepted`` counterparts assert the boundary itself
    # still passes.
    path: list[str] = Field(default_factory=list, max_length=PATH_MAX_LENGTH)
    visit_set: list[str] = Field(default_factory=list, max_length=VISIT_SET_MAX_LENGTH)
    save_slots: dict[str, object] = Field(default_factory=dict)
    state_revision: int = Field(ge=0)
    device_id: str | None = None
    event_id: str | None = None
    choice_path: list[str] | None = None

    @model_validator(mode="after")
    def _save_slots_within_byte_budget(self) -> ReadingStateBody:
        """Reject a save_slots payload whose serialized size exceeds the cap.

        # #ASSUME: security: save_slots has no natural item-count cap (it is a
        # dict of arbitrary client-chosen keys), so the guard is on the
        # serialized byte size instead, mirroring the audit finding.
        # #VERIFY: test_save_slots_over_byte_budget_rejected /
        # test_save_slots_at_byte_budget_accepted exercise the boundary.
        """
        size = len(json.dumps(self.save_slots))
        if size > _SAVE_SLOTS_MAX_BYTES:
            msg = (
                f"save_slots serialized size {size} exceeds the "
                f"{_SAVE_SLOTS_MAX_BYTES}-byte limit"
            )
            raise ValueError(msg)
        return self


class ReadingStateView(BaseModel):
    """A reading-state row returned to the client."""

    child_profile_id: str
    storybook_id: str
    version: int
    current_node: str
    var_state: VarState
    path: list[str]
    visit_set: list[str]
    save_slots: dict[str, object]
    state_revision: int
    updated_by_device_id: str | None
    last_synced_at: datetime | None


class ConflictView(BaseModel):
    """The 409 body returned when a reading-state save loses a revision race."""

    detail: str
    current_row: ReadingStateView
    options: list[str] = Field(
        default_factory=lambda: ["continue_from_this_device", "use_newer_progress"]
    )


class LibraryProgress(BaseModel):
    """A child's reading progress on one library book (for shelf progress bars).

    ``nodes_visited`` counts distinct visited nodes; percent completion is a
    frontend concern (``nodes_visited / node_count`` of the containing item).
    ``updated_at`` is the server-maintained ReadingState timestamp and drives
    "Continue Reading" (most recently active) selection.
    """

    current_node: str
    nodes_visited: int
    updated_at: datetime


class LibraryItem(BaseModel):
    """A published story as seen in a child's library listing."""

    id: str
    title: str
    version: int
    age_band: str
    tier: int
    reading_level_target: float
    node_count: int = 0
    rating: int | None = None
    progress: LibraryProgress | None = None
    series_id: str | None = None
    book_index: int | None = None
    cover_url: str | None = None


class LibraryView(BaseModel):
    """A library listing for a profile."""

    stories: list[LibraryItem]


class CompletionBody(BaseModel):
    """A request to record that a child reached an ending."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    storybook_id: str
    version: int = Field(ge=1)
    ending_id: str = Field(min_length=1)
    event_id: str | None = None


class CompletionView(BaseModel):
    """A recorded completion."""

    child_profile_id: str
    storybook_id: str
    version: int
    ending_id: str
    found_at: datetime


# ---------------------------------------------------------------------------
# Generation / concept schemas
# ---------------------------------------------------------------------------


class ConceptCreateRequest(BaseModel):
    """Guardian request to create a concept brief.

    ``extra="forbid"`` propagates ConceptBrief's strictness at the API boundary.
    """

    model_config = ConfigDict(extra="forbid")

    brief: ConceptBrief


class ConceptCreatedResponse(BaseModel):
    """Response returned after a concept is persisted."""

    concept_id: str


# The generation-job lifecycle states, shared by the response model field and the
# boundary coercion in api/generation.py. GenerationJob.status is a plain string
# column guarded at rest by the ck_generation_job_status CHECK constraint, so the
# handler casts the read-back value to this alias and Pydantic revalidates it.
JobStatusLiteral = Literal[
    "queued", "running", "passed", "needs_review", "failed", "awaiting_manual_fill"
]


class GenerationEnqueuedResponse(BaseModel):
    """Response returned after a generation job is created and enqueued."""

    job_id: str
    status: Literal["queued"] = "queued"


class GenerationJobResponse(BaseModel):
    """Full status payload for a generation job."""

    id: str
    status: JobStatusLiteral
    report: dict[str, object] | None = None
    storybook_id: str | None = None
    version: int | None = None
    error: str | None = None
    skeleton_slug: str | None = None
    theme_brief: dict[str, object] | None = None


class GenerationJobListItem(BaseModel):
    """One row in the guardian's "My Requests" list.

    Deliberately omits the raw ``report`` column (ADR-007): guardian-facing
    endpoints expose job status and the linked storybook only, never the
    multi-stage model output. ``storybook_status`` is the linked storybook's
    current lifecycle state (or ``None`` when no storybook row exists yet), so
    the UI can tell an awaiting-review story from a published one.
    """

    id: str
    status: JobStatusLiteral
    storybook_id: str | None = None
    storybook_status: str | None = None
    version: int | None = None
    error: str | None = None
    title: str | None = None
    premise_snippet: str = ""
    age_band: str | None = None
    created_at: datetime


class GenerationJobListView(BaseModel):
    """The generation jobs visible to the calling guardian's family."""

    jobs: list[GenerationJobListItem]


class ValidateResponse(BaseModel):
    """Response returned by the re-validate endpoint."""

    blocked: bool
    report: dict[str, object]


# ---------------------------------------------------------------------------
# Rating schemas
# ---------------------------------------------------------------------------


class RatingBody(BaseModel):
    """A request to set or update a child's rating of a storybook."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    storybook_id: str
    value: int = Field(ge=1, le=5)


class RatingView(BaseModel):
    """A child's recorded rating of a storybook."""

    child_profile_id: str
    storybook_id: str
    value: int
    rated_at: datetime
    updated_at: datetime


class RatingListView(BaseModel):
    """All ratings recorded by a single child profile."""

    ratings: list[RatingView]


# ---------------------------------------------------------------------------
# Assignment schemas (C4a-6)
# ---------------------------------------------------------------------------


class AssignmentCreateBody(BaseModel):
    """A guardian's request to assign a story to one or more child profiles."""

    model_config = ConfigDict(extra="forbid")

    # #ASSUME: security: a family has a small number of child profiles, so a cap
    # of 64 comfortably exceeds any real assign batch while bounding a single
    # request's per-id authorize/insert work against batch-abuse.
    # #VERIFY: min_length rejects [] (422); max_length rejects an oversized list.
    profile_ids: list[str] = Field(min_length=1, max_length=64)


class AssignmentListView(BaseModel):
    """The full current set of profiles a story is assigned to."""

    storybook_id: str
    profile_ids: list[str]


class GuardianBookItem(BaseModel):
    """A published family book as the guardian browses it to assign (Task 2.2).

    Carries a redacted content badge (``screened`` + ``flagged_count``, the same
    two signals the assign dialog and console rows show) and the set of child
    profiles the book is currently assigned to. The full story-level findings are
    deliberately not embedded here: the assign dialog lazy-fetches them from the
    content-summary endpoint (Task 2.1) when it opens, so the browse list stays
    lean and the findings projection lives in exactly one place.
    """

    storybook_id: str
    title: str
    version: int
    age_band: str
    screened: bool
    flagged_count: int = Field(ge=0)
    assigned_profile_ids: list[str]

    @model_validator(mode="after")
    def _unscreened_has_no_flags(self) -> GuardianBookItem:
        """Reject an unscreened badge that also reports flagged passages.

        The projector derives ``screened`` and ``flagged_count`` from the same
        moderation report, so an unscreened book always has zero flags and the
        corrupt-report degrade sets both to ``(False, 0)`` together. This guard
        makes that coupling a type invariant: a future caller cannot construct a
        contradictory "unscreened, N flagged" badge that would misreport a book's
        safety posture to a guardian.
        """
        if not self.screened and self.flagged_count != 0:
            msg = "an unscreened book cannot report flagged passages"
            raise ValueError(msg)
        return self


class GuardianBooksView(BaseModel):
    """The family's published books for the guardian browse-and-assign page."""

    books: list[GuardianBookItem]


# ---------------------------------------------------------------------------
# Story-request schemas (Task 3.0)
# ---------------------------------------------------------------------------


# The four story-request lifecycle states, shared by the response field and the
# boundary coercion. The story_request.status column is a plain string guarded at
# rest by ck_story_request_status; the API coerces read/write values to this alias.
StoryRequestStatus = Literal["pending", "approved", "declined", "blocked"]

RequestText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]

SeriesTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]

AnchorId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class StoryRequestCreateBody(BaseModel):
    """A child's free-text story request (kid surface; guardian-scoped in R1).

    ``proposed_series_title`` and ``anchor_storybook_id`` are mutually
    exclusive: the former proposes a brand-new, unratified series name; the
    latter asks for a soft continuation anchored to an existing storybook.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    request_text: RequestText
    proposed_series_title: SeriesTitle | None = None
    anchor_storybook_id: AnchorId | None = None

    @model_validator(mode="after")
    def _proposal_xor_anchor(self) -> StoryRequestCreateBody:
        if (
            self.proposed_series_title is not None
            and self.anchor_storybook_id is not None
        ):
            msg = "a request may propose a new series or continue one, not both"
            raise ValueError(msg)
        return self


_TEEN_BANDS = frozenset({AgeBand.BAND_13_16, AgeBand.BAND_16_PLUS})


class StoryRequestSpecBody(BaseModel):
    """The band/length/style trio shared by approve and authored-create bodies.

    One base class because ADR-011's teen-only gamebook rule must hold at every
    entry point that sets ``narrative_style``; subclassing keeps the validator
    in one place (mirroring the ck_story_request_style_band CHECK at rest).
    """

    model_config = ConfigDict(extra="forbid")

    age_band: AgeBand
    length: Length
    narrative_style: NarrativeStyle = NarrativeStyle.PROSE

    @model_validator(mode="after")
    def _style_allowed_for_band(self) -> StoryRequestSpecBody:
        if (
            self.narrative_style is NarrativeStyle.GAMEBOOK
            and self.age_band not in _TEEN_BANDS
        ):
            msg = "narrative_style 'gamebook' requires age band 13-16 or 16+"
            raise ValueError(msg)
        return self


class StoryRequestApproveBody(StoryRequestSpecBody):
    """Guardian confirmation required to approve a request (WS-B).

    The request becomes the source of truth for band and length at approval;
    ``narrative_style`` follows ADR-011: gamebook only for 13-16 and 16+.
    ``series_title`` ratifies or edits the kid's proposed series title;
    omitting it declines the proposal (the anchored-plus-title conflict is a
    service-layer check because it needs the row).
    """

    series_title: SeriesTitle | None = None


class StoryRequestAuthoredCreateBody(StoryRequestSpecBody):
    """A guardian's or admin's pre-approved story request (WS-B PR 2).

    ``profile_id`` is optional (an authored request need not target a child).
    ``family_id`` is admin-only: admins must name the target family (decision
    B3); guardians must omit it (their own family is server-derived).
    ``series_title`` and ``anchor_storybook_id`` are mutually exclusive: the
    former creates a new series immediately (no ratification step), the
    latter continues an existing one.
    """

    request_text: RequestText
    profile_id: str | None = None
    family_id: str | None = None
    series_title: SeriesTitle | None = None
    anchor_storybook_id: AnchorId | None = None

    @model_validator(mode="after")
    def _series_xor_anchor(self) -> StoryRequestAuthoredCreateBody:
        if self.series_title is not None and self.anchor_storybook_id is not None:
            msg = "a request may create a new series or continue one, not both"
            raise ValueError(msg)
        return self


class StoryRequestFlag(BaseModel):
    """A redacted screening flag shown to a guardian.

    Mirrors GuardianFinding: category, gating verdict, and message only. Never
    the classifier score, source, or the child's raw request text.
    """

    category: str
    verdict: Verdict
    message: str


class StoryRequestView(BaseModel):
    """One story request as seen by a guardian, admin, or (via guardian token) child.

    ``request_text`` is ``None`` for a ``blocked`` row: the raw text of a
    bright-line request is never surfaced. ``moderation_flags`` carries only the
    redacted StoryRequestFlag list. ``age_band``, ``length``, and
    ``narrative_style`` are request-sourced (WS-B): for a still-pending
    request they reflect the profile-stamped defaults from creation; for an
    approved request they reflect the guardian's approval confirmation, and
    the guardian UI uses the band/length/style trio to prefill the approve
    dialog. ``profile_id`` is ``None`` for an authored request with no target
    child (WS-B PR 2). ``proposed_series_title`` is ``None`` for blocked rows
    (screened content, same redaction as ``request_text``).

    ``series_id``, ``proposed_series_title``, and ``anchor_storybook_id``
    default to ``None`` rather than being required so older tests
    constructing a view directly need not supply them; ``_to_view``
    (api/story_requests.py) populates all three from the row for every
    caller (WS-B PR 3).
    """

    id: str
    profile_id: str | None
    status: StoryRequestStatus
    request_text: str | None
    moderation_flags: list[StoryRequestFlag]
    created_at: datetime
    initiator_role: Literal["child", "guardian", "admin"]
    age_band: AgeBand
    length: Length | None
    narrative_style: NarrativeStyle
    series_id: str | None = None
    proposed_series_title: str | None = None
    anchor_storybook_id: str | None = None


class StoryRequestListView(BaseModel):
    """The story requests visible to the caller, newest first."""

    requests: list[StoryRequestView]


class StoryRequestCreatedView(BaseModel):
    """The result of submitting a request: its id and post-screening status."""

    id: str
    status: StoryRequestStatus


class StoryRequestApprovedView(BaseModel):
    """The result of approving a request: the linked concept.

    No GenerationJob is created at approval time; an admin creates one by
    calling POST /story-requests/{id}/authoring-plan (see
    story_requests/authoring_plan.py).
    """

    id: str
    status: Literal["approved"]
    concept_id: str


class StoryRequestAuthoredCreatedView(BaseModel):
    """The result of an authored create: approved with a concept, or blocked."""

    id: str
    status: StoryRequestStatus
    concept_id: str | None


class FamilyView(BaseModel):
    """A family as listed for the admin authored-request form."""

    id: str
    name: str


class FamilyListView(BaseModel):
    """All families, admin-only (powers the required family selector)."""

    families: list[FamilyView]


AuthoringMethod = Literal["skeleton_fill", "fresh_generation"]
AuthoringMechanism = Literal["skill", "automated_provider"]


class AuthoringPlanRequest(BaseModel):
    """Admin's choice of authoring method, mechanism, and prep model.

    ``review_stage1_model`` / ``review_stage2_model`` are optional overrides
    for the Stage 1 fidelity review and Stage 2 model, used only when
    method='skeleton_fill'. ``provider``/``model`` (WS-C PR1) select the
    generation backend when ``mechanism='automated_provider'``; both are
    required together in that case and are validated against the enabled
    provider/model allowlist by ``build_authoring_plan`` (a DB-backed check
    the schema layer cannot perform).
    """

    model_config = ConfigDict(extra="forbid")

    method: AuthoringMethod
    mechanism: AuthoringMechanism
    prep_model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    provider: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None
    ) = None
    model: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None
    ) = None
    review_stage1_model: str | None = None
    review_stage2_model: str | None = None

    @model_validator(mode="after")
    def _skill_requires_skeleton_fill(self) -> AuthoringPlanRequest:
        """Reject the one illegal method/mechanism pairing at the type boundary.

        The ``skill`` mechanism means a human runs the cyo-author skill to fill
        an existing skeleton, so it is only meaningful with
        ``method='skeleton_fill'``. Encoding this here makes the illegal
        ``fresh_generation`` + ``skill`` state unrepresentable rather than
        relying on a downstream runtime guard, and FastAPI rejects it as a 422
        before it ever reaches ``build_authoring_plan``.
        """
        if self.method == "fresh_generation" and self.mechanism == "skill":
            msg = "mechanism='skill' requires method='skeleton_fill'"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _provider_model_match_mechanism(self) -> AuthoringPlanRequest:
        """Bind provider/model presence to mechanism='automated_provider'.

        mechanism='skill' means a human runs the cyo-author skill; no
        GenerationProvider is ever constructed for that job, so provider/model
        are meaningless there. mechanism='automated_provider' always drives
        the worker's build_provider() call (fresh_generation always pairs with
        automated_provider per the validator above; skeleton_fill may pair
        with either), so both fields must be present together.

        Both directions are enforced so no invalid combination is
        representable: automated_provider without both fields is rejected, and
        (the inverse) a non-automated_provider request carrying provider/model
        is rejected rather than silently dropping the admin's inert choice in
        build_authoring_plan. Mirrors ``_skill_requires_skeleton_fill``.
        """
        if self.mechanism == "automated_provider":
            if self.provider is None or self.model is None:
                msg = (
                    "provider and model are both required when "
                    "mechanism='automated_provider'"
                )
                raise ValueError(msg)
        elif self.provider is not None or self.model is not None:
            msg = "provider/model are only valid when mechanism='automated_provider'"
            raise ValueError(msg)
        return self


class AuthoringPlanResponse(BaseModel):
    """The generation job created (or parked) by an authoring-plan decision."""

    request_id: str
    concept_id: str
    job_id: str
    method: AuthoringMethod
    mechanism: AuthoringMechanism
    status: JobStatusLiteral
    skeleton_slug: str | None = None
    warnings: list[str] = Field(default_factory=list)


class StoryRequestDeclinedView(BaseModel):
    """The result of declining a request."""

    id: str
    status: Literal["declined"]


# ---------------------------------------------------------------------------
# Profile schemas
# ---------------------------------------------------------------------------


DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]

# #CRITICAL: security: avatars must stay opaque glyph ids, never photos or free
# text (the child-photo privacy decision is unresolved; see the frontend
# avatar catalog's module docstring). A closed vocabulary here is what
# enforces that invariant server-side; the UI radio group alone is bypassable.
# #VERIFY: tests/integration/test_profiles.py::test_create_rejects_unknown_avatar
# asserts 422 for an id outside this catalog. Keep in sync with
# frontend/src/profiles/avatars.ts AVATARS.
AvatarId = Literal["fox", "owl", "dragon", "cat", "unicorn", "robot", "rocket", "frog"]


class ProfileView(BaseModel):
    """A child profile as seen by its guardian or the child themself."""

    id: str
    display_name: str
    age_band: AgeBand
    reading_level_cap: float
    avatar: str | None
    tts_enabled: bool
    created_at: datetime


class ProfileListView(BaseModel):
    """The profiles the calling principal may act on."""

    profiles: list[ProfileView]


class ProfileCreateBody(BaseModel):
    """A guardian's request to create a child profile."""

    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName
    age_band: AgeBand
    reading_level_cap: float = Field(default=99.0, ge=0.0, le=99.0)
    avatar: AvatarId | None = None
    tts_enabled: bool = False


class ProfileUpdateBody(BaseModel):
    """A guardian's partial update to a child profile.

    ``avatar`` distinguishes "omitted" from "explicit null" via
    ``model_fields_set``: an explicit ``"avatar": null`` clears the avatar.
    The other four fields have no legitimate "clear" semantics, so an explicit
    ``null`` on them is a deliberate no-op (the router only applies non-null
    values); see ``update_profile`` and
    ``test_update_ignores_explicit_null_on_non_avatar_fields``.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName | None = None
    age_band: AgeBand | None = None
    reading_level_cap: float | None = Field(default=None, ge=0.0, le=99.0)
    avatar: AvatarId | None = None
    tts_enabled: bool | None = None


# ---------------------------------------------------------------------------
# Approval schemas
# ---------------------------------------------------------------------------


class SendBackRequest(BaseModel):
    """Body for the send-back endpoint."""

    model_config = ConfigDict(extra="forbid")

    # #ASSUME: security: a whitespace-only reason must not pass server-side.
    # strip_whitespace runs before the length check so "   " collapses to ""
    # and fails min_length=1 (422). The frontend already rejects blank reasons;
    # this closes the direct-API bypass and trims the logged value.
    # #VERIFY: test_send_back_rejects_whitespace_only_reason (422).
    # Mirrors the DisplayName constraint above.
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]


class SubmittedView(BaseModel):
    """The response to a successful submit action."""

    id: str
    status: Literal["in_review"]
    current_published_version: int | None


class ApprovedView(BaseModel):
    """The response to a successful approve action.

    ``approved_by`` and ``published_at`` are REQUIRED: a published story always
    carries its approver and publish time, so this model cannot represent the
    illegal "published without an approver" combination.
    """

    id: str
    status: Literal["published"]
    current_published_version: int
    approved_by: str
    published_at: datetime


class SentBackView(BaseModel):
    """The response to a successful send-back action; ``reason`` is required."""

    id: str
    status: Literal["needs_revision"]
    reason: str


class ArchivedView(BaseModel):
    """The response to a successful archive action."""

    id: str
    status: Literal["archived"]


# ---------------------------------------------------------------------------
# Review-surface schemas (C3-4)
# ---------------------------------------------------------------------------


class FindingView(BaseModel):
    """One moderation finding, shaped for the guardian review UI."""

    stage: int = Field(ge=0, le=4)
    source: Source
    category: str
    node_id: str | None
    verdict: Verdict
    score: float | None
    message: str


class ReviewSummary(BaseModel):
    """The moderation report's derived gating summary."""

    count: int = Field(ge=0)
    hard_block: bool
    soft_flag: bool
    repaired: bool
    reviewer_independent: bool


class FlaggedPassage(BaseModel):
    """A node's prose plus the findings that concern it."""

    node_id: str
    prose: str
    findings: list[FindingView] = Field(min_length=1)


class ReviewSurfaceView(BaseModel):
    """The full guardian review surface for one story version (C3-4)."""

    storybook_id: str
    version: int
    status: str
    blob: dict[str, object]
    screened: bool
    summary: ReviewSummary | None
    flagged_passages: list[FlaggedPassage]
    story_level_findings: list[FindingView]

    @model_validator(mode="after")
    def _no_pass_verdict_leaks(self) -> ReviewSurfaceView:
        """Reject a surface carrying a clean-check ("pass") finding.

        build_review_surface already filters Verdict.PASS out before constructing
        this view; this is a second, independent guard so a future regression in
        that filter fails the request instead of silently showing a guardian a
        non-gating finding as if it needed review.
        """
        leaked = any(
            f.verdict is Verdict.PASS
            for passage in self.flagged_passages
            for f in passage.findings
        ) or any(f.verdict is Verdict.PASS for f in self.story_level_findings)
        if leaked:
            msg = "review surface must not contain a pass-verdict finding"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Review-queue schemas (C4a-4)
# ---------------------------------------------------------------------------


class ReviewQueueItem(BaseModel):
    """One storybook in the admin review queue, shaped for client bucketing.

    ``screened`` plus ``flagged_count`` let the console bucket into "Flagged"
    (screened with findings, or never screened) versus "Ready to review"
    (screened clean). ``summary`` carries the report's gating flags when present.
    """

    storybook_id: str
    title: str
    status: str
    version: int
    screened: bool
    flagged_count: int = Field(ge=0)
    summary: ReviewSummary | None


class ReviewQueueView(BaseModel):
    """The admin review queue: storybooks awaiting a publish decision."""

    items: list[ReviewQueueItem]


# ---------------------------------------------------------------------------
# Guardian content-summary schemas (Task 2.1)
# ---------------------------------------------------------------------------


class GuardianFinding(BaseModel):
    """A redacted, story-level moderation finding shown to a guardian.

    Deliberately narrower than FindingView: it drops source, stage, score, and
    node_id so the guardian assign flow never leaks generation internals or a
    per-node passage locator. Only the category, gating verdict, and the
    human-readable message reach the guardian.
    """

    category: str
    verdict: Verdict
    message: str


class ContentSummaryView(BaseModel):
    """The guardian-facing content review summary for a published story.

    A redacted projection of the admin review surface: it carries the gating
    summary and story-level findings, plus a total flagged count, but never the
    per-node flagged passages (which can spoil content and leak generation
    internals). ``findings`` holds only whole-story findings; per-node findings
    are counted in ``flagged_count`` but not enumerated.
    """

    storybook_id: str
    version: int
    screened: bool
    summary: ReviewSummary | None
    flagged_count: int = Field(ge=0)
    findings: list[GuardianFinding]


# ---------------------------------------------------------------------------
# Principal introspection
# ---------------------------------------------------------------------------


class MeResponse(BaseModel):
    """The authenticated caller's own identity and role.

    The frontend has no way to inspect a bearer token itself (it may be an
    opaque dev-stub string locally, or a signed Supabase JWT it should not
    parse); this is the sole source of truth for which shell (kid vs
    guardian) and nav to render for the current session.
    """

    subject: str
    role: str
    family_id: str
    profile_ids: list[str]


# ---------------------------------------------------------------------------
# Moderation threshold admin CRUD (WS-A)
# ---------------------------------------------------------------------------

# The surfacing floor domain; PASS is deliberately excluded (never surfaces).
MinVerdict = Literal["advisory", "flag", "block"]


class ThresholdView(BaseModel):
    """One stored (age_band, category) surfacing override."""

    age_band: str
    category: str
    min_verdict: MinVerdict
    min_score: float | None


class ThresholdListView(BaseModel):
    """All overrides plus the code default and the category suggestion list."""

    default_min_verdict: MinVerdict
    default_min_score: float | None
    known_categories: list[str]
    rows: list[ThresholdView]


class ThresholdUpsertBody(BaseModel):
    """PUT body for a threshold override."""

    min_verdict: MinVerdict
    # Only gates storybook flags, which carry a real classifier score.
    # Story-request flags always pass score=None, so a min_score override
    # never affects story-request surfacing; verdict-level filtering only.
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Admin noise-floor schemas (WS-A admin noise-floor addendum, Task A3)
# ---------------------------------------------------------------------------


class NoiseFloorView(BaseModel):
    """The global admin noise floor: the ADVISORY-score cutoff for admin review."""

    value: float


class NoiseFloorUpdateBody(BaseModel):
    """PUT body for the global admin noise floor."""

    # The global admin noise floor, bounded to [0, 1]; out-of-range values 422.
    value: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Provider/model allowlist schemas (WS-C PR1)
# ---------------------------------------------------------------------------

ProviderName = Literal["anthropic", "openrouter", "modal", "ollama"]


class AllowlistView(BaseModel):
    """One provider/model allowlist row."""

    id: str
    provider: ProviderName
    model_id: str
    enabled: bool
    display_name: str | None


class AllowlistListView(BaseModel):
    """The whole allowlist table, ordered by (provider, model_id)."""

    rows: list[AllowlistView]


class AllowlistCreateBody(BaseModel):
    """POST body to add a new allowlist row."""

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    model_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ]
    display_name: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
        ]
        | None
    ) = None


class AllowlistUpdateBody(BaseModel):
    """PUT body: full replace of the mutable fields (mirrors ThresholdUpsertBody)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    display_name: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
        ]
        | None
    ) = None
