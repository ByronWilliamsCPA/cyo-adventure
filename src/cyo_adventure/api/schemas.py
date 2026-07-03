"""Pydantic request and response models for the reader and generation APIs.

These are the wire contracts the frontend client is generated from. The
reading-state PUT body never carries a ``profile_id``: the profile is taken from
the path and validated against the token subject (IDOR defense).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.moderation.report import Source, Verdict
from cyo_adventure.storybook.evaluator import VarState
from cyo_adventure.storybook.models import AgeBand


class ReadingStateBody(BaseModel):
    """A reading-state save submitted by the client (PUT body)."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    current_node: str = Field(min_length=1)
    var_state: VarState = Field(default_factory=dict)
    path: list[str] = Field(default_factory=list)
    visit_set: list[str] = Field(default_factory=list)
    save_slots: dict[str, object] = Field(default_factory=dict)
    state_revision: int = Field(ge=0)
    device_id: str | None = None
    event_id: str | None = None
    choice_path: list[str] | None = None


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
JobStatusLiteral = Literal["queued", "running", "passed", "needs_review", "failed"]


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

    reason: str = Field(min_length=1, max_length=2000)


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
