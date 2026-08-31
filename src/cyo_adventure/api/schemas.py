"""Pydantic request and response models for the reader and generation APIs.

These are the wire contracts the frontend client is generated from. The
reading-state PUT body never carries a ``profile_id``: the profile is taken from
the path and validated against the token subject (IDOR defense).
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from cyo_adventure.api.residence_countries import ASSIGNED_RESIDENCE_COUNTRY_CODES

# ADR-018 D1: the three-valued verification state, imported rather than
# restated so the wire contract cannot drift from the function that
# computes it (consent/service.py::verification_status).
from cyo_adventure.consent import VerificationStatus
from cyo_adventure.db.models import (
    _PERSONALIZATION_RING2_SLOT_TYPE_VALUES,
    RING_GOAL_DAYS_MAX,
    RING_GOAL_DAYS_MIN,
)
from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.moderation.report import FindingSeverity, Source, Verdict
from cyo_adventure.publishing.reason_codes import SendBackReasonCodeLiteral
from cyo_adventure.storybook.character_vocabulary import ARCHETYPE_ROSTER
from cyo_adventure.storybook.evaluator import VarState
from cyo_adventure.storybook.models import (
    AgeBand,
    ContentFlagLevel,
    ContentFlags,
    Length,
    NarrativeStyle,
    Valence,
)

# W3.4: the selectable weekly-ring goal, bounded once. The cap exists so one
# guaranteed free day always survives a guardian's most aggressive setting
# (gamification-recommendation-2026-08-01.md, "Plan defaults" item 4).
#
# One alias, four uses: the two WRITE bodies below (create and update) and the
# two READ views (the guardian's raw ProfileView and the kid's resolved
# ProgressView.settings). The read paths previously declared a bare ``int``, so
# the OpenAPI schema, and therefore the generated frontend client, described a
# number the server can never actually emit as unbounded. The DB CHECK in
# ``db/models.py`` is built from these same two constants, so the SQL bound and
# the API bound cannot drift.
RingGoalDays = Annotated[int, Field(ge=RING_GOAL_DAYS_MIN, le=RING_GOAL_DAYS_MAX)]

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
    """A reading-state row returned to the client.

    ``character_id``, ``character_name``, and ``seed_var_state`` are
    server-derived (Task 6, ADR-028 spec section 7.3): the server resolves
    the profile's active character at read start and snapshots its
    attributes as the replay baseline. None of the three may be set by a
    client; ``ReadingStateBody`` has no such fields and is
    ``extra="forbid"``, so a request that tries is rejected before this
    view is ever built.
    """

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
    character_id: str | None
    character_name: str | None
    seed_var_state: VarState | None


class ReadingStateResultView(BaseModel):
    """GET /reading-state response; ``state`` is null for a first-time reader.

    A profile with no saved progress for a story is a normal condition, not
    an error (matching ``SeriesNextView``'s convention below); errors are
    reserved for the story or the profile's access to it being invalid. Do
    not weaken ``ReadingStateView`` itself to make its fields nullable: it
    is reused unchanged as ``ConflictView.current_row`` above, where the row
    is always real.
    """

    model_config = ConfigDict(extra="forbid")

    state: ReadingStateView | None = None


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
    # True when the child's current node is an ending, i.e. they reached a
    # finish this playthrough. Lets the shelf render "Finished!" instead of a
    # misleading "N of M pages explored" that under-reports a branching book
    # (UX-K5); a branch touches only a fraction of all nodes.
    completed: bool = False


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
    # K9 shelf presentation, "what's new" leg: reuses the publishing state
    # machine's existing StorybookVersion.published_at (publishing/service.py
    # stamps it in the same transaction as approved_by), rather than adding a
    # new column. None only for a pre-migration row that predates the column;
    # such a row degrades to "not new" on the shelf, never an error.
    published_at: datetime | None = None
    # ADR-023 Stage D Task D8 (closes Stage C open question 2): mirrors
    # StorybookVersion.personalization_eligible (Stage B), read verbatim, not
    # recomputed. Off by default for a book whose contract carries no
    # personalizable slots at all; the frontend uses this to skip the
    # per-profile personalization-values fetch entirely rather than firing a
    # request that would just come back empty. Pure client-side optimization:
    # the values fetch already fails safe (renders the generic title/body) on
    # any error, timeout, or empty response, so a stale/absent value here
    # never breaks personalization, it only means one extra network round
    # trip for a non-personalizable book.
    personalization_eligible: bool = False
    # ADR-028: whether this book declares a persistent-character envelope
    # (``Storybook.accepts_character is not None``), read verbatim off the
    # stored blob at listing time, not off a DB column. The frontend uses
    # this to decide whether to show the character creator for this book at
    # all; a book that never opted in must never surface one. False for any
    # document that omits the field entirely (including every pre-2.1 book),
    # matching the same "absent means no character" default the schema
    # itself enforces (storybook/models.py::Storybook.accepts_character).
    accepts_character: bool = False
    # Content identity for the served blob of this (id, version), computed on
    # read by ``library.py::storybook_content_hash``. ``StorybookVersion`` is
    # documented as immutable, but a blob rewritten in place under an
    # unchanged version (as scripts/retrofit_personalization.py did to 15
    # published rows) leaves every device that already downloaded that book
    # stuck on the old prose forever: the offline cache keys on ``id@version``
    # alone and a cache hit is never re-fetched. This lets the client tell
    # "same version, changed content" from "unchanged" and evict just the
    # entries that actually drifted. Defaults to the empty string only for a
    # hand-constructed item (see TestLibraryItemEnrichmentFields, which
    # documents the same default-to-safe-empty convention for every other
    # enrichment field); the listing route always populates it, and the client
    # treats an empty value as "server said nothing, do not evict".
    content_hash: str = ""


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


class CompletionRecordedView(CompletionView):
    """The result of ``POST /completions``: the row plus the celebration signal.

    Design review 2026-08-01 section 3.4 / kid-appeal-implementation-plan.md
    W0.3: the previous response (bare ``CompletionView``) discarded whether
    this call's insert was new, so the frontend re-fetched reading-history in
    a race that could under-report the ending just reached. ``is_new``,
    ``found``, and ``total`` are computed fresh on every call, not cached, so
    the ending screen can render "you found a NEW ending!" versus a repeat
    visit directly from this response instead of a second, racing GET.
    """

    is_new: bool
    found: int
    total: int

    @model_validator(mode="after")
    def _check_tally_is_possible(self) -> CompletionRecordedView:
        """Reject tallies the ending screen cannot render coherently.

        # #ASSUME: data integrity: ``found`` counts DISTINCT endings this
        # profile has reached in this book and ``total`` is the pinned
        # version's declared ending count, so ``found > total`` means the
        # projection and the blob disagree (a version pinned backwards, a
        # stale metadata.ending_count) and ``is_new and found == 0`` is
        # self-contradictory: the call that just recorded a new ending must
        # count at least that one. Both would render as a nonsense "you found
        # 9 of 3!" or a celebration over an empty tally.
        # #VERIFY: tests/unit/test_completions_api.py::
        # TestCompletionRecordedViewInvariants.

        Returns:
            CompletionRecordedView: This instance when the tally is coherent.

        Raises:
            ValueError: If ``found`` exceeds ``total``, or a new find is
                reported with a zero tally.
        """
        if self.found > self.total:
            msg = (
                f"found ({self.found}) cannot exceed the book's declared "
                f"ending total ({self.total})"
            )
            raise ValueError(msg)
        if self.is_new and self.found == 0:
            msg = "is_new is True but found is 0; a new find must be counted"
            raise ValueError(msg)
        return self


class CompletionListView(BaseModel):
    """A profile's recorded completions (COPPA 312.6(a) / GDPR Article 15 read path)."""

    completions: list[CompletionView]


class ReadingHistoryItem(BaseModel):
    """One storybook's reading-history summary for a profile (register K6/G9).

    ``total_endings`` is read from the pinned (currently published) version's
    ``metadata.ending_count``; a book with no current published version, or a
    version whose metadata is missing/malformed, reports 0 rather than raising
    (the listing degrades one row, never the whole response).
    """

    storybook_id: str
    title: str
    endings_found: int
    ending_ids: list[str]
    total_endings: int
    in_progress: bool
    last_activity_at: datetime


class ReadingHistoryView(BaseModel):
    """A profile's reading-history listing (the kid endings tracker, K6)."""

    profile_id: str
    books: list[ReadingHistoryItem]


class DailyMinutesView(BaseModel):
    """Active reading minutes for one calendar day (W3.3, guardian-only).

    Derived from ``reading_activity_day.active_seconds // 60``. Guardian-only
    by construction: this type is nested only in ``ChildEngagementItem``,
    which ``get_family_reading_summary`` (guardian/admin-only) is the sole
    producer of. Kids see days, never minutes (gamification recommendation
    section 2.4, P4): no kid-facing surface serves this type.
    """

    activity_date: date
    minutes: int


class ChildEngagementItem(BaseModel):
    """One child's engagement signals for a guardian's family reading summary.

    Deliberately signals-only (G9's privacy model: signals, not surveillance):
    no story title, node, or choice content is carried here, only counts and
    ids already visible to the guardian elsewhere (the library listing).
    ``minutes_last_7_days``/``days_read_this_week`` (W3.3) extend that same
    signals-only posture to active reading time: day-grain counts and minute
    totals only, never a session-level or sub-day breakdown.
    """

    profile_id: str
    display_name: str
    books_started: int
    books_finished: int
    total_endings_found: int
    last_activity_at: datetime | None
    minutes_last_7_days: list[DailyMinutesView] = Field(default_factory=list)
    days_read_this_week: int = 0


class FamilyReadingSummaryView(BaseModel):
    """Per-child engagement summary for the caller's own family (G9)."""

    children: list[ChildEngagementItem]


class EarnedBadgeView(BaseModel):
    """One badge a profile has earned (W3.1, gamification recommendation 2.2)."""

    id: str
    name: str
    description: str
    earned_at: datetime


class FoundEndingView(BaseModel):
    """One found ending, card-ready for the Endings Gallery (W3.2).

    Deliberately carries no data for an UNFOUND ending: the gallery renders
    those as generic "still hidden" silhouette placeholders (count only,
    ``total_endings - len(found_endings)``), never a real title or id, so a
    child can never learn what an ending is called before finding it.
    """

    ending_id: str
    title: str
    # The closed set, not a bare str. A blob's stored valence string is coerced
    # to this enum at the boundary in ``api/progress.py`` (unknown -> NEUTRAL,
    # logged), so a corrupt blob still degrades rather than 500ing, while the
    # generated client gets a union it can exhaustively switch on instead of a
    # string that renders as a blank or literal "undefined" label to a child.
    valence: Valence


class BookProgressView(BaseModel):
    """One book's collection state for a profile (W3.1, the Endings Gallery)."""

    storybook_id: str
    title: str
    endings_found: int
    total_endings: int
    finished: bool
    every_path_walked: bool
    # W3.2: every distinct ending this profile has found in this book, oldest
    # find first, card-ready for the gallery. See FoundEndingView's docstring
    # for why unfound endings carry no identity here.
    #
    # Required with no default: the server always supplies the list (empty when
    # nothing is found yet), and the empty list is the meaningful value, so an
    # implicit default would hide a construction-site omission behind a state
    # the gallery renders as "all silhouettes" rather than surfacing it.
    found_endings: list[FoundEndingView]


class ProgressTotalsView(BaseModel):
    """Lifetime totals across every book a profile has touched (W3.1)."""

    books_finished: int
    endings_found: int


class ResolvedGamificationSettingsView(BaseModel):
    """A profile's gamification settings, resolved to concrete values (W3.4).

    Resolution (nullable stored column -> concrete value per the P-A band
    table) happens once, server-side, in
    ``api/progress.py::_resolve_ring_settings`` -- the kid client renders
    directly from this view and never re-implements the band-default table
    itself. See ``ChildProfile.ring_enabled``/``ring_goal_days`` for the raw,
    guardian-editable stored values.
    """

    ring_enabled: bool
    # Bounded here as well as on the write paths: this value is server-RESOLVED
    # (band default or stored override, then clamped by
    # ``api/progress.py::_resolve_ring_settings``), so an out-of-range number
    # reaching a client would mean the resolver, not the caller, was wrong. The
    # generated frontend client now carries the same bound rather than a bare
    # number, which is what let ``strokeDashoffset`` be computed from an
    # unvalidated value in the first place.
    ring_goal_days: RingGoalDays
    badges_enabled: bool
    time_capture_paused: bool


class ProgressView(BaseModel):
    """``GET /me/progress`` response: badges, collection state, totals (W3.1).

    ``days_read_this_week``/``lifetime_days_read`` (W3.4) feed the weekly
    ring and badge 12 ("Forty Days of Stories"): counts only, computed from
    ``reading_activity_day``, matching the guardian summary's own
    ISO-week-Monday-start definition in ``api/reading_history.py``. The kid
    client shows days, never minutes (gamification recommendation P4);
    minutes exist only on the guardian-facing reading summary.
    """

    badges: list[EarnedBadgeView]
    books: list[BookProgressView]
    totals: ProgressTotalsView
    # Required, not defaulted. Both are computed unconditionally by
    # ``api/progress.py::_reading_day_totals`` on every call, so a default only
    # ever fires when a hand-built instance forgets them, which is precisely
    # when a silent 0 is worst: a zeroed weekly ring reads to a child as "you
    # have not read this week". Required here also makes them non-optional in
    # the generated client, retiring the `?? 0` at each consumer.
    days_read_this_week: int = Field(ge=0)
    lifetime_days_read: int = Field(ge=0)
    settings: ResolvedGamificationSettingsView


# Loose upper bound on a single reading-time flush's seconds_delta: one full
# day. The real business-rule clamp (elapsed-time-since-last-write plus a
# grace margin, capped at a much tighter 6 hours) runs in
# api/reading_time.py; this Pydantic bound only guards against a malformed or
# hostile payload carrying an absurd integer before it ever reaches that
# logic (a resource-exhaustion/garbage-input guard, not the sanity clamp
# itself).
_READING_TIME_FLUSH_MAX_SECONDS = 86_400


class ReadingTimeFlushBody(BaseModel):
    """A client-side active-reading-time flush for one day bucket (W3.3).

    ``device_id`` is accepted for parity with the reading-state sync
    contract and future per-device analytics, but is not currently persisted
    (the recommendation's data-model sketch, section 5, carries no
    device_id column); see ``db/models.py::ReadingActivityDay``.
    """

    model_config = ConfigDict(extra="forbid")

    date: date
    seconds_delta: int = Field(ge=0, le=_READING_TIME_FLUSH_MAX_SECONDS)
    flush_id: str = Field(min_length=1, max_length=64)
    device_id: str | None = Field(default=None, max_length=64)


class ReadingActivityDayView(BaseModel):
    """A profile's active-reading-seconds bucket for one day (W3.3)."""

    activity_date: date
    active_seconds: int
    updated_at: datetime
    # The portion of THIS flush's seconds_delta the server has taken
    # responsibility for, either by recording it or by discarding it under the
    # guardian pause policy. The client advances its synced baseline by exactly
    # this, so a clamped flush leaves the unsettled remainder to be retried
    # later rather than being marked synced and lost. Distinct from
    # active_seconds, which is the day's running total across every device.
    settled_seconds: int = 0


class SeriesNextBook(BaseModel):
    """The next readable book in a series, resolved for one profile."""

    model_config = ConfigDict(extra="forbid")

    storybook_id: str
    version: int
    title: str
    series_entry_node: str | None = None
    carries_state: bool


class SeriesNextView(BaseModel):
    """GET /series-next response; ``next`` is null for every expected absence."""

    model_config = ConfigDict(extra="forbid")

    next: SeriesNextBook | None = None


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
    """Status payload for a single generation job.

    ``report`` is the raw multi-stage LLM output (ADR-007: admin/system
    only). Per the 2026-07-16 ruling, ``GET /generation-jobs/{id}``
    (api/generation.py::get_generation_job) populates it only when the
    calling principal holds the admin capability (``Principal.is_admin``,
    which covers a dual-role guardian+admin); a plain guardian always gets
    ``None`` here, same as the list view.
    """

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


class AdminJobActionResponse(BaseModel):
    """Result of an admin operator action on a generation job."""

    id: str
    status: JobStatusLiteral
    error: str | None = None


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
# Notification feed schemas (S9 delivery infrastructure, G10 first slice)
# ---------------------------------------------------------------------------


class NotificationView(BaseModel):
    """One guardian-facing notification derived from a pipeline_event row.

    A read-only projection: there is no notification table. ``id`` is the
    underlying pipeline_event id, which doubles as a stable sort/dedup key
    for the client-side unread tracking this first slice relies on (see
    api/notifications.py).
    """

    id: str
    occurred_at: datetime
    kind: str
    severity: Literal["alert", "info"]
    title: str
    body: str
    storybook_id: str | None = None
    request_id: str | None = None
    profile_id: str | None = None


class NotificationListView(BaseModel):
    """The guardian's family-scoped notification feed, newest first."""

    notifications: list[NotificationView]


# ---------------------------------------------------------------------------
# Kid flag schemas (K15) -- structured, no-free-text child feedback signal.
# ADR-016's no-free-text principle: none of these models carries a
# child-authored text field; ``reason`` is a closed Literal vocabulary.
# ---------------------------------------------------------------------------

KidFlagReasonLiteral = Literal["did_not_like", "scared_me", "confusing"]
KidFlagResolutionLiteral = Literal["dismissed", "archived_book", "noted"]


class KidFlagCreateBody(BaseModel):
    """A child's structured flag on a storybook passage (K15).

    Deliberately carries no free-text field (``extra="forbid"`` rejects any
    caller attempt to smuggle one in under an unexpected key); ``reason`` is
    the entire signal.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    storybook_id: str
    version: int = Field(ge=1)
    reason: KidFlagReasonLiteral
    node_id: str | None = None


class KidFlagCreatedView(BaseModel):
    """The response to a successful flag submission."""

    id: str
    reason: KidFlagReasonLiteral


class KidFlagView(BaseModel):
    """A stored kid flag, as returned on the admin queue."""

    id: str
    family_id: str
    profile_id: str
    storybook_id: str
    version: int
    reason: KidFlagReasonLiteral
    node_id: str | None
    created_at: datetime
    resolved_by: str | None
    resolved_at: datetime | None
    resolution: KidFlagResolutionLiteral | None


class KidFlagListView(BaseModel):
    """The admin open-flags queue, newest first."""

    flags: list[KidFlagView]


class KidFlagResolveBody(BaseModel):
    """An admin's resolution decision for one open flag."""

    model_config = ConfigDict(extra="forbid")

    resolution: KidFlagResolutionLiteral


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
    two signals the assign dialog and console rows show), descriptive metadata
    (``themes``, ``content_flags``) for the book-detail popover, and the set of
    child profiles the book is currently assigned to. The full story-level
    findings are deliberately not embedded here: the assign dialog lazy-fetches
    them from the content-summary endpoint (Task 2.1) when it opens, so the
    browse list stays lean and the findings projection lives in exactly one
    place.
    """

    storybook_id: str
    title: str
    version: int
    age_band: str
    visibility: Literal["family", "catalog"]
    screened: bool
    flagged_count: int = Field(ge=0)
    assigned_profile_ids: list[str]
    # Book-detail popover (age-bands-details): themes and content-sensitivity
    # flags read straight from the blob's metadata, so the browse list can show
    # a detail popover without a second round trip.
    themes: list[str] = Field(default_factory=list)
    content_flags: ContentFlags | None = None

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


class InterpretedElementView(BaseModel):
    """One requested element's disposition, reason, and rendered reflection (K19).

    A straight, serialisable projection of
    ``story_requests.interpretation.InterpretedElement``: ``element`` is the
    only untrusted-derived free text and is nullable (``None`` when the
    echo-safety floor withheld it); ``kid_text`` / ``guardian_text`` are always
    template output. ``disposition`` and ``reason`` are the string values of the
    stored ``ElementDisposition`` / ``ReasonCode`` enums, carried as plain
    strings because the column is JSON (no re-derivation at the boundary).
    """

    element: str | None
    disposition: str
    reason: str
    slot_id: str | None = None
    rule: str | None = None
    kid_text: str
    guardian_text: str


class RequestInterpretationView(BaseModel):
    """The per-request K19 reflection object, as returned on the request view.

    A straight projection of
    ``story_requests.interpretation.RequestInterpretation`` (the persisted
    ``story_request.interpretation`` JSONB column). It is a read model only: the
    stored object was rendered from a fixed template catalog and is already
    echo-safe (CR-3), so this view copies it field-for-field and adds no derived
    content. For a blocked row the stored object is the generic
    CANNOT_CARRY/SAFETY_POLICY interpretation with no premise-derived content
    (every element carries ``element=None``), so it is surfaced alongside
    ``request_text=None`` without further redaction (CR-1).
    """

    interpretation_version: int
    layer: Literal["general", "refined"]
    elements: list[InterpretedElementView]
    kid_summary: str
    guardian_summary: str
    skeleton_slug: str | None = None
    contract_version: int | None = None
    created_at: datetime


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

    ``interpretation`` is the WS-7 K19 reflection (built in / set aside / cannot
    carry, in kid and guardian registers), projected from the
    ``story_request.interpretation`` JSONB column; it is ``None`` for a row
    created before WS-7 shipped (no stored interpretation). For a blocked row it
    is the generic, premise-free interpretation, safe to surface alongside
    ``request_text=None`` (CR-1); ``_to_view`` does not redact it separately.

    ``resulting_storybook_id`` (W0.4) is the storybook this request produced,
    or ``None`` until publish. It is stamped exactly once, by
    ``publishing/service.py::approve()`` -- the sole path that sets
    ``storybook.status="published"`` -- so a non-``None`` value here always
    names a fully moderated, human-approved book; unlike ``status`` (which
    stays ``"approved"`` forever and never itself distinguishes "still
    generating" from "on the shelf"), this field is the honest signal the
    kid-facing request card needs. ``_to_view`` applies no further
    per-caller narrowing beyond the row projection every other field here
    gets (see its own #ASSUME for why exposing the bare id, even before the
    book is assigned to any profile, is safe).
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
    interpretation: RequestInterpretationView | None = None
    resulting_storybook_id: str | None = None


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


FamilyStatus = Literal["active", "deactivated"]


class FamilyView(BaseModel):
    """A family as listed for the admin authored-request form.

    ``status``/``guardian_count``/``kid_count``/``created_at`` were added for
    the WS-J admin user-management console; they are additive to the
    original id/name shape the authored-request family selector already
    consumes, so that consumer is unaffected.
    """

    id: str
    name: str
    status: FamilyStatus
    guardian_count: int
    kid_count: int
    created_at: datetime


class FamilyListView(BaseModel):
    """All families, admin-only (powers the required family selector)."""

    families: list[FamilyView]


class ChildEnvelopeUsageView(BaseModel):
    """One child's ADR-015 G3 pre-authorization envelope usage this month.

    Deliberately usage-only, no balance-display styling here (the balance
    UI is a later, out-of-scope piece); this is the raw numbers a future
    guardian-facing view will render.
    """

    profile_id: str
    display_name: str
    request_auto_approve: bool
    monthly_request_envelope: int | None
    used_this_month: int


class FamilyBudgetView(BaseModel):
    """GET /families/me/budget: the caller's family monthly story budget (ADR-015 G7/G3)."""

    quota: int
    spent_this_month: int
    remaining: int
    children: list[ChildEnvelopeUsageView]


class FamilyCreateBody(BaseModel):
    """An admin's request to create a family (WS-J)."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class FamilyUpdateBody(BaseModel):
    """An admin's partial update to a family: rename and/or status (WS-J).

    Deactivating a family cascades to deactivate every member ``User`` and
    ``ChildProfile`` in the same transaction; reactivating a family does NOT
    auto-reactivate its members (deliberate asymmetry, see
    ``api/families.py``).
    """

    model_config = ConfigDict(extra="forbid")

    name: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
        ]
        | None
    ) = None
    status: FamilyStatus | None = None


AuthoringMethod = Literal["skeleton_fill", "fresh_generation"]
AuthoringMechanism = Literal["skill", "automated_provider"]
# The generation backends an admin may name. Mirrors the
# ck_provider_model_allowlist_provider CHECK constraint and
# generation.allowlist.ALLOWLIST_PROVIDERS (mock is a CI-only double, never
# allowlistable). Typed here so AuthoringPlanRequest.provider rejects an
# unknown backend at the schema boundary (422) instead of at the DB query.
ProviderName = Literal["anthropic", "openrouter", "modal"]


class AlternativeView(BaseModel):
    """One in-cell, production-eligible skeleton the admin could pick instead."""

    slug: Annotated[str, StringConstraints(min_length=1)]


class AuthoringPlanRequest(BaseModel):
    """Admin's choice of authoring method, mechanism, and prep model.

    ``review_stage1_model`` / ``review_stage2_model`` are optional overrides
    for the Stage 1 fidelity review and Stage 2 model, used only when
    method='skeleton_fill'. ``provider``/``model`` (WS-C PR1) select the
    generation backend when ``mechanism='automated_provider'``; both are
    required together in that case and are validated against the enabled
    provider/model allowlist by ``build_authoring_plan`` (a DB-backed check
    the schema layer cannot perform). ``skeleton_slug`` is an optional admin
    override (decision C-6): any slug on disk is accepted, including a
    non-production-eligible or out-of-cell one, with a warning surfaced on
    mismatch rather than a rejection. It is "unconstrained" in WHICH skeleton it
    may name, but the value is charset-bounded to a slug (lowercase, digits,
    hyphens) so a path-traversal string can never reach the filesystem path
    builders; the DB provenance column is String(120), so the length is capped
    to match.
    """

    model_config = ConfigDict(extra="forbid")

    method: AuthoringMethod
    mechanism: AuthoringMechanism
    prep_model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    provider: ProviderName | None = None
    model: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None
    ) = None
    review_stage1_model: str | None = None
    review_stage2_model: str | None = None
    # #CRITICAL: security: admin override input (decision C-6) reaches the
    # filesystem path builders in skeleton_match/worker/import_story. The slug
    # charset (lowercase, digits, hyphens) rejects path-traversal segments
    # (``..``, ``/``) at the boundary; max_length matches the String(120) column.
    # #VERIFY: test_authoring_plan_api rejects a traversing/oversized slug at 422,
    # plus skeleton_match.resolve_skeleton_path as defense-in-depth.
    skeleton_slug: (
        Annotated[
            str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=120)
        ]
        | None
    ) = None

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
    skeleton_alternatives: list[AlternativeView] = Field(default_factory=list)
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

# A guardian-set profile PIN (P6-07): exactly 4-8 ASCII digits. Enforced at
# the API boundary so core/pin.py only ever hashes well-formed values.
PinCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{4,8}$")]

# #CRITICAL: security: a banned theme is guardian-supplied free text that
# later flows, unmodified, into a generation prompt via
# story_requests/brief.py's ConceptBrief.content_nogo (see
# generation/concept.py's control-character strip, which this mirrors for
# the same reason: safety-eval Finding 5 / #64). Stripping control
# characters and constraining to a narrow, lowercase charset here closes
# that gap at the single point every theme string passes through before it
# reaches ChildProfile.banned_themes.
# #VERIFY: tests/integration/test_profiles.py banned-theme validation tests
# assert control characters are stripped and out-of-charset input is a 422.
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_THEME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9 '-]{0,39}$")


def _normalize_theme(value: str) -> str:
    """Strip control characters, lowercase, and validate a banned-theme string.

    Args:
        value: The raw theme string from the request body.

    Returns:
        str: The normalized (control-stripped, trimmed, lowercased) theme.

    Raises:
        ValueError: If the normalized value is empty or outside the allowed
            charset (letters, digits, spaces, hyphens, apostrophes; 1-40
            chars), which Pydantic reports as a 422.
    """
    normalized = _CONTROL_CHAR_PATTERN.sub("", value).strip().lower()
    if not _THEME_PATTERN.fullmatch(normalized):
        msg = (
            "banned theme must be 1-40 characters: letters, numbers, "
            "spaces, hyphens, or apostrophes"
        )
        raise ValueError(msg)
    return normalized


BannedTheme = Annotated[str, AfterValidator(_normalize_theme)]

# Mirrors ConceptBrief.content_nogo's per-brief cap (generation/concept.py);
# a profile cannot carry more banned themes than a single brief can express.
_BANNED_THEMES_MAX = 20


class ContentFlagCaps(BaseModel):
    """Per-child ceiling overrides for the three content-sensitivity flags.

    Each field is ``None`` when the guardian has not set an override for
    that flag. A value here can only ever tighten what the child's age band
    already permits: the band's own ceiling
    (``validator/band_profile.py::BandProfile.content_ceiling``) is enforced
    unconditionally by the validation gate regardless of this model, so a
    guardian cannot use it to loosen the age-safety default, only to
    restrict further (see ``story_requests/brief.py``'s clamp-to-band-ceiling
    derivation). Stored on ``ChildProfile.allowed_content_flags`` as a dict
    containing only the keys that are set.
    """

    model_config = ConfigDict(extra="forbid")

    violence: ContentFlagLevel | None = None
    scariness: ContentFlagLevel | None = None
    peril: ContentFlagLevel | None = None


# #CRITICAL: security: avatars must stay opaque glyph ids, never photos or free
# text (the child-photo privacy decision is unresolved; see the frontend
# avatar catalog's module docstring). A closed vocabulary here is what
# enforces that invariant server-side; the UI radio group alone is bypassable.
# #VERIFY: tests/integration/test_profiles.py::test_create_rejects_unknown_avatar
# asserts 422 for an id outside this catalog. Keep in sync with
# frontend/src/profiles/avatars.ts AVATARS.
AvatarId = Literal[
    "fox",
    "owl",
    "dragon",
    "cat",
    "unicorn",
    "robot",
    "rocket",
    "frog",
    "wolf",
    "panther",
    "ember-dragon",
    "hawk",
    "raven",
    "pegasus",
    "alicorn",
    "butterfly",
    "shark",
    "soccer",
    "baseball-gear",
    "cheer-gear",
    "baseball-kid",
    "cheer-kid",
]


class ProfileView(BaseModel):
    """A child profile as seen by its guardian or the child themself.

    ``has_pin`` is the ONLY PIN-related field any view exposes; the stored
    ``pin_hash`` is write-only credential material and must never be
    serialized (see the ``#CRITICAL`` note on ``ChildProfile.pin_hash``).
    ``content_flag_caps`` and ``banned_themes`` are the G2 per-child content
    controls (see ``ContentFlagCaps`` and ``ChildProfile.banned_themes``);
    both always serialize (an empty-caps object / empty list, never absent),
    so a profile created before G2 shipped reads back with no overrides
    rather than a missing field.
    """

    id: str
    display_name: str
    age_band: AgeBand
    reading_level_cap: float
    avatar: str | None
    tts_enabled: bool
    reduce_motion: bool
    has_pin: bool
    content_flag_caps: ContentFlagCaps
    banned_themes: list[str]
    request_auto_approve: bool
    monthly_request_envelope: int | None
    # GDPR Article 18/21 (remediation plan, newly scoped): derived from
    # ChildProfile.processing_restricted_at is not None, mirroring how
    # has_pin derives from pin_hash is not None -- the timestamp itself is
    # never serialized, only the boolean state.
    processing_restricted: bool
    # W3.4 gamification settings (gamification-recommendation-2026-08-01.md
    # section 4). ring_enabled/ring_goal_days are the RAW stored value, null
    # meaning "no override, use the P-A band default"; this view is what the
    # guardian settings form edits, so it must distinguish "guardian chose
    # off" from "never touched, following the band default" rather than
    # showing a pre-resolved value that would hide that distinction. The
    # kid-facing resolved value (what actually renders) comes from
    # ``GET /me/progress``'s ``settings`` field instead.
    ring_enabled: bool | None
    ring_goal_days: RingGoalDays | None
    badges_enabled: bool
    time_capture_paused: bool
    created_at: datetime


class ProfileListView(BaseModel):
    """The profiles the calling principal may act on."""

    profiles: list[ProfileView]


class ProfileStoryStatusView(BaseModel):
    """One profile's "new story ready" pill status (W1.4, design review 4.1).

    Deliberately boolean-only: this view is served to a pre-child-session
    picker principal (a device grant, or a guardian who has not yet handed
    the device to a specific child), which may legitimately list every
    profile in the family (``api/profiles.py::_listable_profiles``) but must
    never learn a SIBLING profile's book titles or shelf counts from the
    picker screen. ``has_new_story`` is the only signal; no
    ``storybook_id``/``title``/``count`` field is ever added here (see the
    endpoint docstring for the "new" definition).
    """

    profile_id: str
    has_new_story: bool


class ProfileStoryStatusListView(BaseModel):
    """Bulk "new story ready" status for every profile the caller may list.

    One entry per profile ``api/profiles.py::_listable_profiles`` returns for
    the calling principal, in the same order; a profile the principal cannot
    list never appears here either (see ``GET /profiles/story-status``).
    """

    statuses: list[ProfileStoryStatusView]


class ProfileCreateBody(BaseModel):
    """A guardian's request to create a child profile."""

    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName
    age_band: AgeBand
    reading_level_cap: float = Field(default=99.0, ge=0.0, le=99.0)
    avatar: AvatarId | None = None
    tts_enabled: bool = False
    reduce_motion: bool = False
    content_flag_caps: ContentFlagCaps | None = None
    banned_themes: (
        Annotated[list[BannedTheme], Field(max_length=_BANNED_THEMES_MAX)] | None
    ) = None
    request_auto_approve: bool = False
    monthly_request_envelope: Annotated[int, Field(ge=0, le=100)] | None = None
    # W3.4: omitted/null at creation means "no override yet, follow the P-A
    # band default" (see ProfileView's field docstring); a guardian who wants
    # a non-default ring state sets it via a follow-up PATCH, same as every
    # other optional G2/G3 field on create.
    ring_enabled: bool | None = None
    ring_goal_days: RingGoalDays | None = None
    badges_enabled: bool = True
    time_capture_paused: bool = False


class ProfileUpdateBody(BaseModel):
    """A guardian's partial update to a child profile.

    ``avatar``, ``pin``, ``content_flag_caps``, and ``banned_themes``
    distinguish "omitted" from "explicit null" via ``model_fields_set``: an
    explicit ``"avatar": null`` clears the avatar, an explicit ``"pin":
    null`` removes the profile's picker PIN (a 4-8 digit string sets or
    replaces it), and an explicit null on either G2 field clears it back to
    "no override" / "no exclusions" (a non-null value replaces the stored
    value wholesale, it does not merge). The other five fields have no
    legitimate "clear" semantics, so an explicit ``null`` on them is a
    deliberate no-op (the router only applies non-null values); see
    ``update_profile`` and
    ``test_update_ignores_explicit_null_on_non_avatar_fields``.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName | None = None
    age_band: AgeBand | None = None
    reading_level_cap: float | None = Field(default=None, ge=0.0, le=99.0)
    avatar: AvatarId | None = None
    tts_enabled: bool | None = None
    reduce_motion: bool | None = None
    pin: PinCode | None = None
    content_flag_caps: ContentFlagCaps | None = None
    banned_themes: (
        Annotated[list[BannedTheme], Field(max_length=_BANNED_THEMES_MAX)] | None
    ) = None
    # G3 (ADR-015 pre-authorization envelope): request_auto_approve follows the
    # non-null-applies rule; monthly_request_envelope follows the explicit-null
    # -clears rule via model_fields_set (null = no envelope = auto-approve
    # inert even when the toggle is on, see story_requests.service.can_auto_approve).
    request_auto_approve: bool | None = None
    monthly_request_envelope: Annotated[int, Field(ge=0, le=100)] | None = None
    # GDPR Article 18/21: non-null-applies, like tts_enabled/request_auto_approve
    # (no "explicit null" semantics -- there is no legitimate reason to send
    # a null here rather than simply omitting the field). True sets
    # processing_restricted_at to now; False clears it back to None.
    processing_restricted: bool | None = None
    # W3.4 gamification settings (gamification-recommendation-2026-08-01.md
    # section 4). ring_enabled/ring_goal_days follow the avatar/pin
    # "explicit null clears back to band default, omitted leaves unchanged"
    # contract via model_fields_set; badges_enabled/time_capture_paused
    # follow the non-null-applies contract (no legitimate "clear" state --
    # they always have a concrete, non-band-dependent default).
    ring_enabled: bool | None = None
    ring_goal_days: RingGoalDays | None = None
    badges_enabled: bool | None = None
    time_capture_paused: bool | None = None


def _nfc(value: str) -> str:
    """NFC-normalize a user-supplied personalization value.

    Shared by the guardian-authored personalization value types below and by
    ``CharacterName`` (ADR-028), whose value is a child-authored free-text
    name that resolves into the same ``character_name`` personalization slot
    and therefore needs the same canonical stored form.

    Args:
        value: The raw submitted string.

    Returns:
        str: The NFC-normalized string.
    """
    # #ASSUME: data-integrity: the denylist and distinctness matching in
    # `validator/slots.py::_normalize` already NFC-normalizes before it
    # compares, so this is NOT what stops a decomposed spelling from evading
    # the denylist; that hole does not exist. What this fixes is that the
    # value is STORED in whatever form the client sent. Two consequences,
    # both real and both small: the 120-character structural limit is
    # measured on the raw form, so a decomposed spelling can be rejected at a
    # length its precomposed twin passes; and the replace route's change
    # detection compares stored text to submitted text with `!=`, so
    # re-saving a visually identical name from a client that normalizes
    # differently reads as an edit and rewrites the row. Normalizing at the
    # edge makes the stored form canonical and both problems go away. NFC is
    # idempotent, so an already-normalized value (nearly all of them) is
    # unchanged.
    # #VERIFY: tests/unit/test_api_schemas_personalization.py::
    # test_decomposed_and_precomposed_text_values_normalize_identically.
    return unicodedata.normalize("NFC", value)


# ---------------------------------------------------------------------------
# Character schemas (ADR-028)
# ---------------------------------------------------------------------------

# Built from ARCHETYPE_ROSTER rather than retyped: db/models.py already keeps
# its own SQL-CHECK copy (_CHARACTER_ARCHETYPE_NAMES) honest against the same
# roster via tests/unit/test_character_vocab_drift.py; deriving this pattern
# from the roster directly avoids adding a third hand-maintained copy of the
# six names.
_CHARACTER_ARCHETYPE_PATTERN = "^(" + "|".join(ARCHETYPE_ROSTER) + ")$"

# A character's name resolves into the `character_name` personalization slot
# and is substituted into child-facing story prose, so it is constrained the
# same way the other real-person free-text slot values are: NFC-normalized at
# the edge (see `_nfc`), with the structural and band-denylist checks run in
# the route handler via `storybook.personalization_values`, exactly as
# `protagonist_first_name` gets them from `api/personalization.py`'s PUT. The
# checks cannot move into this type: the denylist floor depends on the owning
# profile's age band, which no request body carries.
# #VERIFY: tests/unit/test_api_schemas_personalization.py::
# test_character_name_is_nfc_normalized_like_a_personalization_value;
# tests/integration/test_characters_api.py::
# test_create_character_rejects_a_sentinel_shaped_name.
CharacterName = Annotated[str, Field(min_length=1, max_length=32), AfterValidator(_nfc)]
CharacterArchetype = Annotated[str, Field(pattern=_CHARACTER_ARCHETYPE_PATTERN)]
CharacterLook = Annotated[str, Field(pattern=r"^avatar_(0[1-9]|1[0-2])$")]


class CharacterCreateBody(BaseModel):
    """A request to create a character for one child profile."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    name: CharacterName
    archetype: CharacterArchetype
    look: CharacterLook


class CharacterUpdateBody(BaseModel):
    """A partial update: name and look are re-choosable; archetype is not.

    Attributes, books_completed, and archetype are absent by design.
    Attributes and books_completed are server-derived and no principal may
    write them (spec section 3.4). archetype is identity, not a re-pickable
    preference: ``characters/progression.py``'s ``_PROGRESSION_VARIABLES``
    excludes it on the stated grounds that it is "set once at
    creation/build and never raised", and ``Character.archetype`` (the
    string column) has no update path that also rewrites the persisted
    ``character_attribute`` row holding the integer code a read binds from
    (``characters/seeding.py::initial_attributes``); a PATCH that touched
    only the column would leave the two permanently disagreeing. In all
    three cases ``extra="forbid"`` turns an attempt into a 422 rather than
    a silent drop.
    """

    model_config = ConfigDict(extra="forbid")

    name: CharacterName | None = None
    look: CharacterLook | None = None


class CharacterView(BaseModel):
    """A character as returned to a kid or guardian.

    ``seed_var_state`` is the server's own answer to "what numbers would a
    read started by this character carry": exactly what
    ``reading.py::_bind_active_character`` snapshots onto a new
    reading-state row. It is exposed because a FRESH read has no
    reading-state row yet, so there is no ``ReadingStateView`` to read a
    seed off, and the player must still open the book from the bound
    character's numbers rather than the story's declared initials (ADR-028
    Task 9, issue #460, and the ``#EDGE`` marker on ``put_reading_state``'s
    create path).

    #CRITICAL: data integrity: this field exists so the client CONSUMES a
    server-derived seed instead of re-deriving one from ``attributes``. A
    second, client-side attribute-to-seed mapping would be free to drift
    from ``characters/seeding.py::character_seed``, and the two disagreeing
    is not a cosmetic bug: the server replays a submitted state from the
    stored seed (``player/replay.py::validate_reading_state``), so the
    first save carrying a ``choice_path`` would 422 and wedge the read
    permanently. Both this view and the read-start binding call
    ``character_seed`` on the same stored attribute rows, so there is
    exactly one mapping.
    #VERIFY: tests/integration/test_reading_character_binding.py::
    test_character_view_seed_matches_the_seed_a_read_start_would_bind
    asserts this field equals the ``seed_var_state`` the reading-state
    create path persists for the same character, so a change to either
    side alone fails.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    profile_id: str
    name: str
    archetype: str
    look: str
    is_active: bool
    books_completed: int
    attributes: dict[str, int]
    seed_var_state: VarState
    created_at: datetime
    retired_at: datetime | None


class CharacterListView(BaseModel):
    """All of one profile's characters, active first."""

    model_config = ConfigDict(extra="forbid")

    characters: list[CharacterView]


# ---------------------------------------------------------------------------
# Approval schemas
# ---------------------------------------------------------------------------

# The closed-vocabulary calibration signal for a reviewer's send-back decision
# is defined in publishing/reason_codes.py and imported at the top of this
# module. It used to be declared here, which left publishing/service.py::
# send_back unable to validate against the very vocabulary this file owned,
# because the domain cannot import from the API layer. Moving it reverses the
# arrow: the boundary imports the domain's vocabulary.
#
# The wire contract is unchanged. A type alias is transparent to pydantic, so
# the OpenAPI schema still carries the same inline string enum and the
# generated frontend client does not move.


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
    # #ASSUME: data integrity: required, not optional. Requiring it is what
    # makes "every send-back has a calibration-ready reason code" hold
    # structurally rather than by reviewer discipline. The free-text `reason`
    # above stays alongside it, unchanged, for the prose a reviewer still
    # wants to leave.
    #
    # The in-repo callers are `api/approval.py` (the admin console review
    # dialog) and **the committed Postman collection**, which is a caller and
    # was updated in the same change. An earlier version of this note claimed
    # there was no caller a required field could break; the collection was
    # exactly that, sent no reason_code, took a 422 and failed the newman job.
    # There is no *external* integrator, which is the narrower claim that is
    # actually true. Anyone adding a required field to this surface should
    # treat the collection as a caller, because it does not look like one.
    # #VERIFY: test_send_back_requires_reason_code covers requiredness (422
    # when omitted); the **newman job** is what catches a caller this change
    # forgot to update, which is the assumption above rather than the field.
    reason_code: SendBackReasonCodeLiteral


class SubmittedView(BaseModel):
    """The response to a successful submit action."""

    id: str
    status: Literal["in_review"]
    current_published_version: int | None


class ApproveBody(BaseModel):
    """Optional approve-time release options (WS-E decision E2).

    ``visibility`` defaults to ``family`` so an approve with no body keeps the
    pre-WS-E behavior; ``catalog`` shares the book with every family.
    """

    visibility: Literal["family", "catalog"] = "family"
    override_reason: str | None = Field(
        default=None,
        min_length=10,
        max_length=2000,
        description=(
            "Required when the moderation report contains a block or "
            "high-severity finding. Logged for the reviewer of record, not "
            "persisted verbatim on the audit event: the pipeline_event "
            "payload is PII-free by contract (spec D3), so only the "
            "structured overridden-finding counts are recorded there."
        ),
    )

    # #ASSUME: data-integrity: without this, a value like
    # "   whitespace-padded reason" (>= 10 raw characters, but shorter or
    # blank once stripped) passes this schema's min_length check only for the
    # service layer's own stripped-truthiness check
    # (publishing/service.py::approve) to then reject it as though no reason
    # had been given at all, a confusing two-stage rejection for one bad
    # input. Stripping here (mode="before") makes the length check test the
    # same content the service layer ultimately requires.
    # #VERIFY: tests/integration/test_approval_api.py::
    # test_approve_over_block_with_whitespace_only_reason_returns_422 (422, not
    # 400, since 10 spaces strip to empty and fail this schema's min_length
    # before the request ever reaches the service).
    @field_validator("override_reason", mode="before")
    @classmethod
    def _strip_override_reason(cls, value: object) -> object:
        """Strip surrounding whitespace before the ``min_length`` check runs."""
        if isinstance(value, str):
            return value.strip()
        return value


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
    visibility: Literal["family", "catalog"]


class SentBackView(BaseModel):
    """The response to a successful send-back action; ``reason`` is required."""

    id: str
    status: Literal["needs_revision"]
    reason: str
    reason_code: SendBackReasonCodeLiteral


class ArchivedView(BaseModel):
    """The response to a successful archive action."""

    id: str
    status: Literal["archived"]


# ---------------------------------------------------------------------------
# Passage edit schema (G6: lightweight passage editor with re-review)
# ---------------------------------------------------------------------------


class NodeEditBody(BaseModel):
    """A prose-only edit to one node: replacement body text and/or choice labels.

    Structure (ids, targets, conditions, effects, graph shape) is never
    editable through this body; ``api/node_edit.py::edit_node`` applies
    ``body`` to the node's prose and each ``choice_labels`` entry to the
    matching existing choice id's ``label`` only, rejecting any id absent
    from the node.
    """

    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, StringConstraints(min_length=1, max_length=20000)] | None = (
        None
    )
    choice_labels: (
        dict[str, Annotated[str, StringConstraints(min_length=1, max_length=500)]]
        | None
    ) = None

    @model_validator(mode="after")
    def _require_an_edit(self) -> NodeEditBody:
        """Reject a body that edits nothing.

        Raises:
            ValueError: If both ``body`` and ``choice_labels`` are absent.
        """
        if self.body is None and not self.choice_labels:
            msg = "at least one of body or choice_labels must be supplied"
            raise ValueError(msg)
        return self


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
    # Additive (Stage B, design doc 2.2): severity/node_ids come from the
    # post-review merge stage; structural/concern existed on persisted
    # findings since Stage A but were never projected until B3's surfaces
    # needed them. All four default so a pre-Stage-B report still projects.
    severity: FindingSeverity | None = None
    node_ids: list[str] | None = None
    structural: bool = False
    concern: str | None = None


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


# The deterministic validator's own severity vocabulary
# (validator/report.py::Severity). Deliberately NOT FindingSeverity
# (high/medium/low), which is the moderation scale; the two are different
# axes and must not be interchangeable at the API boundary.
ValidatorSeverity = Literal["error", "warning"]


class ValidatorFindingView(BaseModel):
    """One deterministic-gate finding, projected read-only onto the admin surface.

    Design doc 2.7 option (a): RL-13 (advisory reading level) and PL-19 (words-
    per-node) currently gate nothing and show nowhere. This is a pure read of
    the story's already-persisted ``StorybookVersion.validation_report``
    (``validator/report.py::ValidationReport.to_dict()``); it never re-runs the
    validator. ``severity`` here is the validator's own ``error``/``warning``
    vocabulary (``validator/report.py::Severity``), a distinct scale from the
    moderation ``FindingSeverity`` (high/medium/low) used elsewhere on this
    surface. It is typed as its own two-member ``Literal`` rather than reused
    from ``FindingSeverity``, which keeps the two scales from conflating while
    still making the vocabulary explicit at the contract boundary. Normalizing
    an unreadable value is ``_validator_findings``' job, not this model's: it
    maps anything outside the two members to ``"error"`` so a corrupt row
    degrades loudly instead of raising and 422-ing the whole review surface.
    """

    rule_id: str
    severity: ValidatorSeverity
    node_id: str | None
    message: str


class SafetyConcernCount(BaseModel):
    """How many findings the moderation gate raised under one concern."""

    concern: str
    count: int = Field(ge=1)


class GenerationMeasuresView(BaseModel):
    """What the automated gate measured, for the human gate that follows (R-2).

    Every field is a read of something already persisted; nothing here is
    recomputed at request time. The block exists because the approval screen
    was showing findings without showing the measurements behind the routing
    decision, so an approver could not tell a book that scraped past a floor
    from one that cleared it comfortably.

    Deliberately absent: the deterministic gate's ``safety_flagged``. Its
    SAFE-14 producer is a Phase-2 stub that returns an empty finding list by
    construction, so the field is structurally always ``False`` and would read
    on an approval screen as a clean bill from a check that never ran. The
    safety evidence here comes from the moderation gate, which does run.

    Attributes:
        fill_rate: Share of commissioned words the fill actually produced, or
            ``None`` for a version with no recorded rate (an imported book, or
            one generated before the rate was stamped). Not zero: a book with
            no measurement is not a book that filled nothing.
        fill_rate_floor: The floor the rate was judged against, or ``None``.
        fill_rate_downgrade: Whether falling under that floor is what routed
            this book to review. The rate alone cannot answer this, because it
            is stamped on every outcome carrying a book, breach or not.
        safety_concerns: Surfaced content concerns with their finding counts,
            most frequent first. Pipeline-structural findings ("the reviewer
            was unavailable") are excluded: they describe the run, not the
            book.
    """

    fill_rate: float | None = None
    fill_rate_floor: float | None = None
    fill_rate_downgrade: bool = False
    safety_concerns: list[SafetyConcernCount] = Field(default_factory=list)


class ReviewSurfaceView(BaseModel):
    """The full guardian review surface for one story version (C3-4)."""

    storybook_id: str
    version: int
    status: str
    blob: dict[str, object]
    screened: bool
    # Task 4: True when the stored report carries no genuine content judgment
    # (fail-safe artifacts only, or a non-independent/mock reviewer). Set from
    # moderation/report.py::moderation_report_unusable. Default False so a
    # caller that predates this field (or a report projected before Task 4
    # shipped) still reads as usable, matching the additive-field convention
    # every other Stage B/B3 field on this view follows.
    report_unusable: bool = False
    summary: ReviewSummary | None
    flagged_passages: list[FlaggedPassage]
    story_level_findings: list[FindingView]
    # Stage B3 additive fields (design doc 2.6): a flat, non-fanned merged-
    # finding view alongside the existing node-joined flagged_passages above.
    # Each entry still carries node_ids, so the frontend can drill down to
    # affected nodes on demand without the admin surface pre-joining prose to
    # every occurrence the way flagged_passages does. All four default empty
    # so a caller that has not been updated to pass validation_report, or an
    # older stored report, still projects a valid surface.
    ranked_findings: list[FindingView] = Field(default_factory=list)
    structural_findings: list[FindingView] = Field(default_factory=list)
    low_advisory_findings: list[FindingView] = Field(default_factory=list)
    validator_findings: list[ValidatorFindingView] = Field(default_factory=list)
    # R-2: the measurements behind the routing decision, so the human gate
    # sees what the automated gate measured. Defaults empty so a caller that
    # passes no validation_report still projects a valid surface.
    generation_measures: GenerationMeasuresView = Field(
        default_factory=GenerationMeasuresView
    )

    @model_validator(mode="after")
    def _no_pass_verdict_leaks(self) -> ReviewSurfaceView:
        """Reject a surface carrying a clean-check ("pass") finding.

        build_review_surface already filters Verdict.PASS out before constructing
        this view; this is a second, independent guard so a future regression in
        that filter fails the request instead of silently showing a guardian a
        non-gating finding as if it needed review. Extended in Stage B3 to cover
        the three new merged-finding buckets alongside the original two.
        """
        leaked = (
            any(
                f.verdict is Verdict.PASS
                for passage in self.flagged_passages
                for f in passage.findings
            )
            or any(f.verdict is Verdict.PASS for f in self.story_level_findings)
            or any(f.verdict is Verdict.PASS for f in self.ranked_findings)
            or any(f.verdict is Verdict.PASS for f in self.structural_findings)
            or any(f.verdict is Verdict.PASS for f in self.low_advisory_findings)
        )
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
    # Task 4: mirrors ReviewSurfaceView.report_unusable, plus tiered distinct-
    # finding counts (each merged finding counts once, regardless of how many
    # nodes it fans out to via node_ids). Advisories never gate, so
    # flag_findings excludes structural findings and advisory_findings is
    # never added to block/flag; see review_surface.py::build_review_queue_item.
    # All four default so a caller or fixture built before Task 4 still
    # projects a valid queue item.
    report_unusable: bool = False
    block_findings: int = Field(default=0, ge=0)
    flag_findings: int = Field(default=0, ge=0)
    advisory_findings: int = Field(default=0, ge=0)
    summary: ReviewSummary | None
    # Triage metadata for the console (UX-A3): the story's target age band and
    # when this version was created (a "waiting since" proxy). Both optional so a
    # blob missing metadata still projects a valid queue item.
    age_band: str | None = None
    waiting_since: datetime | None = None
    # Book-detail popover (age-bands-details): themes and content-sensitivity
    # flags read straight from the blob's metadata, alongside the fields above.
    # Both default empty/None so a blob missing metadata still projects a valid
    # queue item.
    themes: list[str] = Field(default_factory=list)
    content_flags: ContentFlags | None = None
    # `RS-A7`: the highest-ranked finding on this version, so the queue row can
    # say WHAT the decision is about. Before this, learning that a hard block
    # was one cistern passage meant loading the whole book (2.5 MB, ~10,900 DOM
    # nodes) to read one line. The full FindingView is reused rather than a
    # narrower projection: the queue is admin-only and the same admin sees
    # every one of these fields on the detail surface anyway, so a second
    # shape would only be a chance for the two to disagree. ``None`` when the
    # version has no findings at all (a clean or unscreened book).
    top_finding: FindingView | None = None


class ReviewQueueView(BaseModel):
    """The admin review queue: storybooks awaiting a publish decision."""

    items: list[ReviewQueueItem]


class StorybookSummary(BaseModel):
    """One storybook in the admin master library, any lifecycle status (P19).

    Unlike the review queue (which lists only ``in_review`` stories), the master
    library lets an admin browse and re-open every story: published, archived,
    needs_revision, draft, or in_review. ``version`` is the latest version;
    ``updated_at`` is that version's creation time, an activity proxy for
    sorting most-recent-first.
    """

    storybook_id: str
    title: str
    status: str
    version: int
    age_band: str | None = None
    family_id: str
    current_published_version: int | None = None
    created_at: datetime
    updated_at: datetime | None = None
    # Book-detail popover (age-bands-details): themes and content-sensitivity
    # flags read straight from the blob's metadata. Both default empty/None so
    # a story with no version row yet (draft, blob-less) still projects.
    themes: list[str] = Field(default_factory=list)
    content_flags: ContentFlags | None = None


class StorybookLibraryView(BaseModel):
    """The admin master library: every storybook, newest activity first."""

    items: list[StorybookSummary]


# ---------------------------------------------------------------------------
# Guardian content-summary schemas (Task 2.1)
# ---------------------------------------------------------------------------


class GuardianFinding(BaseModel):
    """A redacted, story-level moderation finding shown to a guardian.

    Deliberately narrower than FindingView: it drops source, stage, score, and
    node_id (and node_ids) so the guardian assign flow never leaks generation
    internals or a per-node passage locator. This is the "GuardianFinding
    rule" a comment in story_requests/screening.py names for the narrower,
    unrelated StoryRequestFlag boundary; it does not freeze this model's field
    count. Only category, gating verdict, message, plus (Stage B3, design doc
    2.6) concern and severity, and node_count -- a COUNT, never the node ids
    themselves -- reach the guardian.
    """

    category: str
    verdict: Verdict
    message: str
    # Additive (Stage B3, design doc 2.6): the merged concern list's per-row
    # signal. concern/severity mirror FindingView's own fields (None on a
    # pre-Stage-B report or an unconcerned category-only finding). node_count
    # is the finding's total node coverage (len(node_ids), or 1 for a single
    # unmerged node finding, or 0 for a genuinely story-level finding),
    # deliberately a count and never the node ids: see the class docstring.
    concern: str | None = None
    severity: FindingSeverity | None = None
    node_count: int = Field(default=0, ge=0)


class GuardianValidatorNote(BaseModel):
    """A story-level, node-id-free count of one validator rule's findings.

    Design doc 2.7 option (a) closes the gap: RL-13 (advisory reading level)
    and PL-19 (words-per-node) must be visible on BOTH the admin review
    surface (``ValidatorFindingView``, per-finding with a node id) and the
    guardian content summary (this type). The guardian view is story-level
    only (design doc 2.6), so this drops node_id and the per-node message
    entirely and keeps only an aggregate ``count`` per (rule_id, severity):
    the guardian sees e.g. "RL-13 warning x12", never which node or what the
    per-node message said (a per-node PL-19 message embeds node context).
    """

    rule_id: str
    severity: ValidatorSeverity
    count: int = Field(ge=1)


class ContentSummaryView(BaseModel):
    """The guardian-facing content review summary for a published story.

    A redacted, story-level-only projection of the admin review surface
    (design doc 2.6): the gating summary, a total flagged count, and a merged
    concern list, but never a per-node row or a node id. ``findings`` merges
    every threshold-surfaced finding (both the admin surface's per-node and
    story-level findings) by concern/severity/verdict/message, so a single
    admin-visible finding that spans several nodes collapses into one
    guardian row whose ``node_count`` sums that coverage, never a passage
    list. See ``review_surface.py::_content_summary_findings``.

    ``validator_notes`` (Stage B3 follow-up, design doc 2.7 option (a)) is
    the guardian-side validator projection: additive, defaults to ``[]`` so
    an older backend response or a report predating validator persistence
    still projects a valid summary. See ``review_surface.py::_validator_notes``.
    """

    storybook_id: str
    version: int
    screened: bool
    summary: ReviewSummary | None
    flagged_count: int = Field(ge=0)
    findings: list[GuardianFinding]
    validator_notes: list[GuardianValidatorNote] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Principal introspection
# ---------------------------------------------------------------------------


class MeResponse(BaseModel):
    """The authenticated caller's own identity and role.

    The frontend has no way to inspect a bearer token itself (it may be an
    opaque dev-stub string locally, or a signed Supabase JWT it should not
    parse); this is the sole source of truth for which shell (kid vs
    guardian vs admin) and nav to render for the current session.

    ``role`` is the base persona (guardian/child/admin); ``is_admin`` is the
    orthogonal admin capability, so one adult can be a guardian, an admin,
    or both (role='guardian' with is_admin=true).
    """

    subject: str
    role: str
    is_admin: bool
    family_id: str
    profile_ids: list[str]
    # ADR-018 D1. Two fields rather than one because they answer independent
    # questions: whether this tier gates child-profile creation on parent
    # verification at all, and where this caller stands. A client needs both
    # to decide between routing to the verification screen and leaving the
    # guardian alone.
    verification_required: bool
    # #ASSUME: security: reported as "none" for every caller when
    # ``verification_required`` is False, rather than queried and reported
    # accurately, so this endpoint keeps costing zero database round trips on
    # the tiers where nothing consumes the answer. It is never the basis of an
    # enforcement decision: the gates in api/profiles.py and
    # api/admin_profiles.py re-derive the same fact from the database at the
    # point of use, so a client that ignores or misreads this field cannot
    # create a child profile it should not.
    # #VERIFY: tests/integration/test_me.py::
    # test_me_reports_no_verification_state_while_the_flag_is_off.
    verification_status: VerificationStatus


class FamilyExportView(BaseModel):
    """A guardian's full family data export.

    COPPA 312.6(a) access / GDPR Article 20 portability (remediation plan
    Phase 3c), in one endpoint: every record tied to the family and each
    child profile, as a single machine-readable (portable) JSON document.
    Nested entities are loosely-typed dicts, not per-entity Pydantic models:
    this endpoint's job is completeness of the export, not a stable typed API
    contract for any one entity (the normal per-resource endpoints already
    serve that role); each dict's keys mirror the corresponding ORM row's
    columns as built in ``api/me.py``.

    Attributes:
        exported_at: When this export was generated (UTC).
        family: The family row (id, name, created_at).
        guardians: Every guardian/admin/child login row in the family (id,
            role, is_admin, email, created_at, the consent_* quartet, and the
            O-117/O-119 residence_country/adulthood_attested_at fields); no
            ``pin_hash`` or ``authn_subject`` (credential material, never
            exported).
        profiles: Every child profile, each with its own nested
            ``reading_state``, ``completions``, ``ratings``, ``assignments``,
            ``personalization`` (ADR-023 P4 ``ChildProfilePersonalization``
            rows, plus the two ``real_name_ring1_enabled``/
            ``real_name_ring2_enabled`` booleans on the profile itself), and
            ``disclosure_consents`` (``PersonalizationDisclosureConsent``
            rows, including tombstoned ones) lists.
        story_requests: Every story request tied to the family.
    """

    exported_at: datetime
    family: dict[str, object]
    guardians: list[dict[str, object]]
    profiles: list[dict[str, object]]
    story_requests: list[dict[str, object]]


# ---------------------------------------------------------------------------
# Child-scoped session tokens (G1 / P6-04)
# ---------------------------------------------------------------------------


class ChildSessionCreateBody(BaseModel):
    """A guardian's (or admin's) request to mint a child session for one profile.

    ``pin`` is required (and checked) only when the target profile has a
    guardian-set picker PIN (P6-07); for a PIN-less profile it is ignored.
    Deliberately NOT ``PinCode``-constrained: a malformed candidate ("abc",
    three digits) must fail as an ordinary wrong PIN (403), not a 422 that
    leaks whether the profile has a PIN of a different shape. The length cap
    only bounds the hashing work.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    pin: Annotated[str, StringConstraints(max_length=64)] | None = None


class ChildSessionView(BaseModel):
    """A minted child session token and its expiry.

    The token is a backend-signed, short-lived JWT the kid surface uses as its
    own bearer (role=child, scoped to ``profile_id``). No PII beyond ids
    crosses this boundary; see ``core/child_session.py`` for the trust model.
    """

    token: str
    expires_at: datetime
    profile_id: str


# ---------------------------------------------------------------------------
# Device grants (ADR-014 phase 1)
# ---------------------------------------------------------------------------


class DeviceGrantCreateBody(BaseModel):
    """A guardian's (or admin's) request to mint a device grant.

    ``family_id`` is optional and mirrors ``StoryRequestAuthoredCreateBody``:
    a guardian must omit it (it always resolves to their own family) and an
    admin-only caller must supply it (an admin has no family of its own to
    default to). ``label`` is a free-text, guardian-facing name for the
    device ("Kitchen tablet"); never derived from request headers.
    """

    model_config = ConfigDict(extra="forbid")

    family_id: str | None = None
    label: Annotated[str, StringConstraints(max_length=120)] | None = None


class DeviceGrantView(BaseModel):
    """A minted device grant token and its record.

    The token is a backend-signed, durable (90-day) JWT the kid surface's
    device-authorization check uses; see ``core/device_grant.py`` for the
    trust model. Returned ONLY at mint time, never again: ``GET
    /device-grants`` (``DeviceGrantListItem``) never includes it.
    """

    id: str
    token: str
    expires_at: datetime
    family_id: str
    authorized_by: str


class DeviceGrantListItem(BaseModel):
    """One row of a family's device-grant list. Never carries the token.

    The list endpoint returns only currently-active grants (it filters
    ``revoked_at IS NULL``), so a revocation timestamp would always be null on
    the wire and is deliberately omitted: the row's mere presence means the
    grant is active. A future "show revoked devices" view would re-add the
    field alongside a widened query.
    """

    id: str
    label: str | None
    created_at: datetime


class DeviceDownloadReportBody(BaseModel):
    """A client reporting it has (or still has) a book cached offline (G15).

    ``device_id`` is a client-generated persistent id (``localStorage``, see
    ``frontend/src/offline/deviceId.ts``), NOT a device-grant token id; the
    two are separate identities (see ``DeviceDownload``'s docstring).
    """

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=64)
    profile_id: str
    storybook_id: str = Field(max_length=120)


class DeviceDownloadView(BaseModel):
    """One row of a family's download inventory, as the guardian console sees it."""

    id: str
    device_id: str
    profile_id: str
    profile_name: str
    storybook_id: str
    storybook_title: str | None
    downloaded_at: datetime
    last_confirmed_at: datetime


# ---------------------------------------------------------------------------
# JIT guardian onboarding (P6-03)
# ---------------------------------------------------------------------------


def _normalize_residence_country(value: str) -> str:
    """Uppercase and validate an ISO 3166-1 alpha-2 country code.

    Two checks, in order, so the 422 message tells the two failure modes
    apart: a value that is not two letters at all (a syntax error) versus a
    value that IS two letters but names no assigned country (e.g. "ZZ",
    "XX", "QQ", the user-assigned/reserved alpha-2 ranges), which the regex
    alone cannot catch.

    Args:
        value: The raw country code from the request body.

    Returns:
        str: The uppercased, validated two-letter code.

    Raises:
        ValueError: If the normalized value is not exactly two ASCII
            letters, or is two letters but not an assigned ISO 3166-1
            alpha-2 code. Pydantic reports either as a 422.
    """
    normalized = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", normalized):
        msg = "residence_country must be an ISO 3166-1 alpha-2 code (two letters)"
        raise ValueError(msg)
    if normalized not in ASSIGNED_RESIDENCE_COUNTRY_CODES:
        msg = (
            f"residence_country '{normalized}' is not an assigned "
            "ISO 3166-1 alpha-2 code"
        )
        raise ValueError(msg)
    return normalized


# O-117: enforces two things db/models.py::User.residence_country's CHECK
# constraint (``^[A-Z]{2}$``) does not: this validator also rejects a
# syntactically valid but unassigned code (e.g. "ZZ"), by checking
# membership in ASSIGNED_RESIDENCE_COUNTRY_CODES. The at-rest CHECK stays
# format-only (see its own comment for why); this is the ISO-membership
# gate, and it runs at the wire boundary so a rejected code 422s before it
# ever reaches the database.
ResidenceCountry = Annotated[str, AfterValidator(_normalize_residence_country)]


class OnboardingConsent(BaseModel):
    """Verifiable-parental-consent payload (Phase 2 / ADR-018 D1; O-117/O-119).

    A typed-name attestation layered on the Supabase/Google OAuth login that
    already authenticates the guardian: ``signer_name`` is a typed
    full-legal-name attestation, and the OAuth session supplies the identity
    binding. Nothing is drawn, uploaded, or cryptographically signed.

    Do not describe this as an enumerated FTC consent method. It was built on
    the belief that it satisfied a "sign and submit electronically" method at
    16 CFR 312.5(b)(2)(i); reading that provision directly on 2026-08-08 found
    no such method, and whether this flow is an enumerated method AT ALL is
    an open question with outside counsel (ADR-018 D1). The record this model
    captures is required under every candidate method, so it stands
    regardless of how that question resolves; only the strength of the
    verification step is in doubt. ``accepted``, ``policy_version``,
    ``signer_name``, ``residence_country``, and ``adulthood_attested`` must
    all be present together to actually record consent; a request that omits
    or falsifies any of them records nothing (see
    ``onboarding._record_consent``), it does not partially persist.

    ``residence_country`` (O-117) and ``adulthood_attested`` (O-119) are new
    fields on this same versioned consent form, not a reinterpretation of the
    guardianship attestation ``signer_name``/``accepted`` already capture:
    guardianship and age are different claims, so they get their own
    checkbox and their own columns (``User.residence_country``,
    ``User.adulthood_attested_at``). There is no separate
    attestation-version field for the new checkbox: it ships inside this same
    form, so ``policy_version`` already records what text was shown.
    """

    model_config = ConfigDict(extra="forbid")

    # #CRITICAL: security: onboarding._record_consent requires all five of
    # accepted=True, policy_version, signer_name, residence_country, and
    # adulthood_attested=True before writing a User.consent_*/O-117/O-119
    # row; this schema itself does not enforce that combination so a caller
    # can still send accepted=True with fields missing (the 422 for that
    # case comes from the route handler, not Pydantic, to keep the "what's
    # missing" error message field-specific).
    # #VERIFY: tests/integration/test_onboarding_api.py::
    # test_consent_requires_policy_version_and_signer_name,
    # test_consent_requires_residence_country_and_adulthood_attested.
    accepted: bool | None = None
    policy_version: str | None = None
    # A typed full legal name (e.g. "Jane A. Smith"), not a display name or
    # nickname; the guardian is attesting to their own identity as the
    # signer, distinct from ProfileCreateBody.display_name (a CHILD's
    # nickname, an entirely different field on an entirely different model).
    signer_name: str | None = None
    # O-117: ISO 3166-1 alpha-2, uppercased and format-checked by
    # ResidenceCountry's validator. Without a recorded country signal the DSA
    # Art. 2(1) and GDPR Art. 3(2) targeting tests cannot be answered.
    residence_country: ResidenceCountry | None = None
    # O-119: must be explicitly True, mirroring ``accepted``'s own
    # explicit-True contract (a missing or False value is treated as "not
    # attested", never coerced from truthiness).
    adulthood_attested: bool | None = None


class OnboardingBody(BaseModel):
    """First-login onboarding request body.

    All identity comes from the verified token, so the body is optional and
    carries only the P7-02 consent seam. The endpoint accepts an empty request
    (no body) equally.
    """

    model_config = ConfigDict(extra="forbid")

    consent: OnboardingConsent | None = None


class OnboardingView(BaseModel):
    """The family/guardian identity resolved or created by onboarding.

    ``created`` is ``True`` only when this request provisioned the row; a
    retry (idempotent) or an already-provisioned guardian/admin returns
    ``False``. The HTTP status mirrors it: 201 when created, 200 otherwise.
    """

    family_id: str
    user_id: str
    role: str
    created: bool
    # Lets the frontend show a "your account is awaiting admin approval"
    # state (status="awaiting_approval") instead of proceeding to
    # GET /v1/me, which api/deps.py::require_principal rejects for any
    # non-"active" status. Two tracks surface "awaiting_approval": an
    # uninvited guardian's own self-signup, and a GUARDIAN-created invite
    # (POST /me/family/invite-guardian) once bound. Only an ADMIN-created
    # invite resolves straight to "active" (the invite bind sets it).
    status: str
    # Phase 2 / ADR-018 D1: lets the frontend decide whether to show the
    # consent-capture step without a separate lookup. Derived from
    # User.consent_accepted_at is not None; always False for a non-guardian
    # (admin/child) row, since VPC consent is a guardian-only concept.
    consent_recorded: bool
    # ADR-018 D1: the same PAIR of fields MeResponse carries, surfaced here as
    # well because the two responses cover different halves of the sign-in
    # sequence and neither covers both. Verification sits BEFORE admin
    # approval, and api/deps.py::require_principal refuses any non-"active"
    # user, so GET /me is unreachable for exactly the guardian who needs to be
    # told to verify. This is how that guardian's client learns it.
    #
    # Both fields, not just the status, for the reason MeResponse gives: with
    # the flag off every caller reads "none", which is also what a guardian who
    # simply has not started yet reads. Without the boolean a client cannot
    # tell those apart, and the only other place it is published is the
    # response this caller cannot reach.
    verification_required: bool
    verification_status: VerificationStatus


class KwsVerificationStartBody(BaseModel):
    """What a parent supplies to begin verification (ADR-018 D1).

    Note what is absent: an email address. The address KWS mails is taken from
    the caller's verified token claim (falling back to the address recorded on
    their own ``User`` row), never from this body, so the endpoint cannot be
    used to mail an arbitrary third party. See ``api/consent.py`` for the full
    reasoning.
    """

    model_config = ConfigDict(extra="forbid")

    # The location that decides which verification methods KWS offers this
    # parent, so a compliance input rather than a preference. Reuses the
    # ISO-membership-checked ResidenceCountry type: db/models.py's CHECK also
    # admits an ISO 3166-2 subdivision ("US-CA"), but nothing collects one
    # yet, and admitting a shape at the wire that no screen produces would be
    # an untested path rather than a feature.
    location: ResidenceCountry
    # The parent's language for KWS's emails and web screens (ISO 639-1).
    language: str = Field(default="en", pattern=r"^[a-z]{2}$")


class KwsVerificationStartView(BaseModel):
    """The attempt a start request created.

    Carries no email address and no KWS URL: the parent receives the link by
    email, and the client's job after this response is to wait and poll, not
    to navigate anywhere.
    """

    attempt_id: str
    # Always "sent" on this response; a resolved attempt is reported through
    # the verification_status field of GET /me and POST /onboarding instead.
    status: str
    requested_at: datetime


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
# ``ProviderName`` is defined near the authoring aliases above (it is used by
# AuthoringPlanRequest.provider, which precedes this section).


class AllowlistView(BaseModel):
    """One provider/model allowlist row.

    ``provider`` is a plain ``str`` here while every *request* body in this
    module narrows it to ``ProviderName``. That asymmetry is deliberate: a
    request names a backend the pipeline must be able to call, so an unknown
    value is a client error (422). A response reports what the row actually
    holds, and a row can legitimately name a retired backend during the window
    between a new image serving and its migration running. Narrowing this field
    made that window an outage: ``_view`` builds this model per row, so a single
    surviving ``('ollama', ...)`` row turned every allowlist read into an
    unhandled ``pydantic.ValidationError`` (500), including the read an admin
    would use to find and delete it.

    #CRITICAL: data-integrity: keep this wider than the request schemas. The
    DB CHECK constraint, not this annotation, is what bounds the column.
    #VERIFY: test_list_tolerates_a_retired_provider_row.
    """

    id: str
    provider: str
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


# ---------------------------------------------------------------------------
# Moderation dashboard schemas (WS-F)
# ---------------------------------------------------------------------------


class CategoryInsightView(BaseModel):
    """Override evidence for one (age_band, category) pair (WS-F)."""

    age_band: str
    category: str
    advisory_findings: int
    flag_findings: int
    decided_versions: int
    released_versions: int
    override_rate: float | None
    last_seen: datetime


class ThresholdChangeView(BaseModel):
    """One recent threshold or noise-floor change event (WS-F)."""

    occurred_at: datetime
    event_type: str
    entity_id: str
    payload: dict[str, object]


class ModerationDashboardView(BaseModel):
    """Aggregated moderation evidence for the admin dashboard (WS-F)."""

    insights: list[CategoryInsightView]
    recent_changes: list[ThresholdChangeView]


class ThresholdSuggestionView(BaseModel):
    """A computed threshold proposal awaiting admin ratification (WS-F)."""

    age_band: str
    category: str
    current_min_verdict: MinVerdict
    current_min_score: float | None
    suggested_min_verdict: MinVerdict
    override_rate: float
    decided_versions: int
    released_versions: int


class SuggestionListView(BaseModel):
    """Computed proposals plus the gates that produced them (WS-F)."""

    min_decided_versions: int
    min_override_rate: float
    suggestions: list[ThresholdSuggestionView]


# ---------------------------------------------------------------------------
# Admin user-management schemas (WS-J)
# ---------------------------------------------------------------------------

# #ASSUME: data-integrity: a hand-rolled shape check, not full RFC 5322
# validation; this field is a contact/match key (onboarding binds a pending
# invite by exact string equality against the verified Supabase email claim),
# never an identity or security boundary itself, so a permissive
# local-part@domain pattern is sufficient. Adding a dependency
# (pydantic's email-validator extra) for a stricter check was judged not
# worth the new supply-chain surface for an admin-only input.
# #VERIFY: tests/integration/test_admin_users_api.py::
# test_create_invite_rejects_malformed_email.
AdminEmail = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]

# Only these two base roles are admin-creatable; a "child" User row is only
# ever the synthetic row api/child_sessions.py provisions for a ChildProfile,
# never something an admin creates directly.
AdminManagedRole = Literal["guardian", "admin"]
# Mirrors db/models.py::_USER_STATUS_VALUES (the at-rest CHECK constraint).
# 'pending' is an ADMIN-created invite; 'pending_guardian_invite' is a
# GUARDIAN-created one (G14) that binds to 'awaiting_approval' rather than
# 'active'. Both appear here only so the admin console can read and filter
# them; neither is settable through PATCH /admin/users/{id}
# (api/admin_users.py::_apply_status_transition rejects both directions).
UserStatus = Literal[
    "pending",
    "active",
    "deactivated",
    "awaiting_approval",
    "pending_guardian_invite",
]


class UserView(BaseModel):
    """A guardian or admin account as seen by the admin console (WS-J).

    Never includes ``authn_subject``: it is bearer-adjacent identity material
    with no admin-console use, mirroring why ``pin_hash`` is never
    serialized on ``ProfileView``.
    """

    id: str
    family_id: str
    email: str | None
    role: AdminManagedRole
    is_admin: bool
    status: UserStatus
    created_at: datetime


class UserListView(BaseModel):
    """Guardians/admins across all families, optionally filtered (WS-J)."""

    users: list[UserView]


class UserCreateBody(BaseModel):
    """An admin's request to invite a guardian or admin (WS-J).

    Creates a ``status="pending"`` row with a synthetic placeholder
    ``authn_subject``; it becomes ``active`` when that email signs in via
    Supabase for the first time (``api/onboarding.py::_bind_pending_invite``).
    """

    model_config = ConfigDict(extra="forbid")

    email: AdminEmail
    family_id: str
    role: AdminManagedRole
    # Only meaningful with role="guardian" (a dual-role invite); role="admin"
    # always implies True regardless of what is sent here, mirroring the DB
    # CHECK ck_user_admin_role_flag.
    is_admin: bool = False


class UserUpdateBody(BaseModel):
    """An admin's partial update to a guardian/admin account (WS-J).

    Reassigning ``family_id`` moves the user to a different family without
    touching any ``ChildProfile`` (kid profiles belong to the family, not to
    a guardian, so they are unaffected by a guardian's own reassignment).
    """

    model_config = ConfigDict(extra="forbid")

    family_id: str | None = None
    role: AdminManagedRole | None = None
    is_admin: bool | None = None
    status: UserStatus | None = None


class GuardianInviteBody(BaseModel):
    """A guardian's self-service request to invite a co-parent (G14).

    Unlike ``UserCreateBody``, there is no ``family_id`` or ``role`` field: the
    target family is always the calling guardian's own (``ctx.principal.
    family_id``, resolved server-side in ``api/me.py::invite_guardian``, never
    client-supplied), and the invited role is always ``"guardian"``, never
    ``"admin"``, so a guardian can never self-grant the admin capability
    through this path.
    """

    model_config = ConfigDict(extra="forbid")

    email: AdminEmail


# ---------------------------------------------------------------------------
# Admin profile-management schemas (WS-J): ChildProfile CRUD across any
# family. Field-for-field mirrors of ProfileView/ProfileCreateBody/
# ProfileUpdateBody above plus family_id and status, kept as separate types
# (rather than inheritance) so the guardian-scoped schemas' self-family-only
# contract never silently widens.
# ---------------------------------------------------------------------------


class AdminProfileView(BaseModel):
    """A child profile as seen by the admin console, across any family."""

    id: str
    family_id: str
    display_name: str
    age_band: AgeBand
    reading_level_cap: float
    avatar: str | None
    tts_enabled: bool
    reduce_motion: bool
    has_pin: bool
    status: Literal["active", "deactivated"]
    created_at: datetime


class AdminProfileListView(BaseModel):
    """Child profiles across families, optionally filtered by family_id."""

    profiles: list[AdminProfileView]


class AdminProfileCreateBody(BaseModel):
    """An admin's request to create a child profile in any family."""

    model_config = ConfigDict(extra="forbid")

    family_id: str
    display_name: DisplayName
    age_band: AgeBand
    reading_level_cap: float = Field(default=99.0, ge=0.0, le=99.0)
    avatar: AvatarId | None = None
    tts_enabled: bool = False
    reduce_motion: bool = False


class AdminProfileUpdateBody(BaseModel):
    """An admin's partial update to a child profile in any family.

    Mirrors ``ProfileUpdateBody``'s omitted-vs-explicit-null semantics for
    ``avatar``/``pin``, plus a ``status`` toggle absent from the
    guardian-scoped body.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName | None = None
    age_band: AgeBand | None = None
    reading_level_cap: float | None = Field(default=None, ge=0.0, le=99.0)
    avatar: AvatarId | None = None
    tts_enabled: bool | None = None
    reduce_motion: bool | None = None
    pin: PinCode | None = None
    status: Literal["active", "deactivated"] | None = None


# ---------------------------------------------------------------------------
# Family connection schemas (WS-J): directional cross-family recommendation
# opt-in. family_id is the "viewer"; connected_family_id is the source whose
# stories may be recommended. The relationship does not imply its reverse.
# ---------------------------------------------------------------------------


class FamilyConnectionView(BaseModel):
    """One directional family-connection row, with both family names."""

    id: str
    family_id: str
    family_name: str
    connected_family_id: str
    connected_family_name: str
    created_at: datetime


class FamilyConnectionListView(BaseModel):
    """All family connections, admin-only."""

    connections: list[FamilyConnectionView]


class FamilyConnectionCreateBody(BaseModel):
    """An admin's request to opt one family in to another's recommendations."""

    model_config = ConfigDict(extra="forbid")

    family_id: str
    connected_family_id: str


# ---------------------------------------------------------------------------
# Guardian consent schemas (ADR-016, register G17): the caller's own family's
# side of each directional connection it touches, never the full admin view.
# ---------------------------------------------------------------------------


class FamilyConnectionMineItem(BaseModel):
    """One connection touching the caller's family, from their own side.

    ``direction`` is relative to the caller: ``"viewer"`` means the caller's
    family is ``FamilyConnection.family_id`` (it would see the counterpart's
    recommendations); ``"sharer"`` means the caller's family is
    ``connected_family_id`` (the counterpart would see theirs). ``active`` is
    ``True`` only when both sides have consented (ADR-016 dual-guardian rule).
    """

    id: str
    direction: Literal["viewer", "sharer"]
    counterpart_family_id: str
    counterpart_family_name: str
    my_consent: bool
    active: bool
    created_at: datetime


class FamilyConnectionMineListView(BaseModel):
    """Every connection touching the caller's family, from their own side."""

    connections: list[FamilyConnectionMineItem]


# ---------------------------------------------------------------------------
# K17 recommendation feed (ADR-016 rings 1-2). Structured data only: a book
# pointer, a rating, and a recommender display name, never free text.
# ---------------------------------------------------------------------------


class RecommendationItem(BaseModel):
    """One recommended book: a rating from another profile, never a message."""

    storybook_id: str
    title: str
    cover_url: str | None
    recommender_name: str
    rating: int
    ring: Literal["family", "connection"]


class RecommendationsView(BaseModel):
    """A profile's recommendation feed (ring 1 family + ring 2 connections)."""

    items: list[RecommendationItem]


# ---------------------------------------------------------------------------
# Story personalization (ADR-023 P4/P5): per-profile slot values and ring
# flags, ring-2 disclosure consent, and the resolved values payload a reader
# fetches for one book. Shapes pinned by
# docs/planning/story-personalization-implementation-plan.md section 6.1.
# ---------------------------------------------------------------------------

_PersonalizationSlotType = Literal[
    "protagonist_first_name",
    "pronoun_set",
    "sibling_name",
    "pet_species",
    "pet_name",
    "kinship_label",
    "favorite_color",
    "favorite_food",
    "favorite_hobby",
    "home_type",
    "dedication",
    # ADR-028: the persistent-character's name. See
    # storybook.theme_contract.PERSONALIZATION_FIELDS for the full rationale;
    # this Literal is a hand-maintained mirror of that set, drift-guarded by
    # tests/unit/test_personalization_vocab_drift.py.
    "character_name",
]

# The bound on `Ring2ConsentGrantBody.covered_slot_types` below. Derived from
# the RING-2 ceiling, not from `_PersonalizationSlotType`: that list is every
# slot type that exists, and three of them (pronoun_set, dedication, and
# ADR-028's character_name) are permanently ring-1-only, so they can never be
# an admissible member of a consent scope. Bounding a ring-2-only list by the
# whole vocabulary counted members that cannot legally appear in it, and each
# new ring-1-only slot loosened the bound further for no reason.
#
# Counted off `ck_cpp_ring2_ceiling`'s own literal body rather than a fourth
# hand-written copy of the ceiling (the copy-count problem AL-123 records);
# `tests/unit/test_personalization_vocab_drift.py` already pins that literal
# against PERSONALIZATION_FIELDS, so this bound inherits that guard.
# #VERIFY: tests/unit/test_api_schemas_personalization.py::
# test_covered_slot_types_bound_is_the_ring2_ceiling_not_the_whole_vocabulary.
_PERSONALIZATION_RING2_SLOT_TYPE_COUNT = len(
    re.findall(r"'([^']*)'", _PERSONALIZATION_RING2_SLOT_TYPE_VALUES)
)

# The structural gate (`validator/slots.py::_charset_violations`) rejects any
# candidate longer than this, and it is the authority: it runs on every
# personalization value at both write time and payload-build time. The schema
# bound is aligned to it so an over-long value is a shape error at the edge
# rather than a slot violation two layers in. It was 200, which meant values
# of 121 to 200 characters were accepted here only to be rejected downstream.
_PERSONALIZATION_VALUE_MAX_LENGTH = 120


def _dedupe_slot_types(values: list[str]) -> list[str]:
    """Drop repeated slot types, keeping first-seen order.

    Args:
        values: The submitted ``covered_slot_types`` list.

    Returns:
        list[str]: The same values with later duplicates removed.
    """
    # #ASSUME: data-integrity: order is preserved rather than sorted because
    # the list is echoed back to the client verbatim by `GET /v1/me`, and a
    # guardian re-reading their own consent should see the scope they chose
    # in the order they chose it. `dict.fromkeys` is the order-preserving
    # de-duplication idiom; a `set` here would make the response order vary
    # between processes.
    # #VERIFY: tests/unit/test_api_schemas_personalization.py::
    # test_covered_slot_types_are_deduplicated_in_first_seen_order.
    return list(dict.fromkeys(values))


_PersonalizationValueText = Annotated[
    str,
    StringConstraints(max_length=_PERSONALIZATION_VALUE_MAX_LENGTH),
    AfterValidator(_nfc),
]


class PersonalizationSlotBody(BaseModel):
    """One slot's proposed value and ring flags, inside the PUT replace body.

    Exactly one of ``value_text``, ``value_enum``, ``value_profile_id`` may be
    set, mirroring ``ChildProfilePersonalization.ck_cpp_value_cardinality``,
    except for ``"character_name"`` (ADR-028), for which that constraint (and
    this validator) requires all three to be absent: the slot's value is
    synthesized from the profile's active character, not stored here, so a
    consent row for it carries only the ring flags. This is a shape check
    only: the closed-vocabulary, structural, denylist, and sibling-in-family
    checks (plan section 5.2) run in the route handler via
    ``storybook.personalization_values``, not here.
    """

    model_config = ConfigDict(extra="forbid")

    slot_type: _PersonalizationSlotType
    value_text: _PersonalizationValueText | None = None
    # Deliberately tighter than `value_text`'s bound and left where it was: an
    # enum value is a closed-vocabulary member, not free text.
    value_enum: (
        Annotated[str, StringConstraints(max_length=64), AfterValidator(_nfc)] | None
    ) = None
    value_profile_id: str | None = None
    ring1_enabled: bool = False
    ring2_enabled: bool = False

    @model_validator(mode="after")
    def _exactly_one_value(self) -> PersonalizationSlotBody:
        """Reject a slot body whose value-field count does not match its slot.

        #CRITICAL: data integrity: character_name is the one slot_type
        that must carry NO value field; every other slot_type must carry
        exactly one. Without this branch, a PUT body for character_name
        either 422s unconditionally (present == 0 always fails the old
        `!= 1` check, making the slot unusable through its own API) or, if
        the check were simply relaxed to `<= 1`, a caller could smuggle a
        value_text onto character_name that this schema would accept and
        the database's `ck_cpp_value_cardinality` CHECK would then be the
        only thing left to reject it, as a raw IntegrityError instead of a
        clean 422.
        #VERIFY: tests/unit/test_api_schemas_personalization.py::
        test_character_name_slot_body_validates_with_no_value_field and
        ::test_character_name_slot_body_with_a_value_text_is_rejected.
        """
        present = sum(
            value is not None
            for value in (self.value_text, self.value_enum, self.value_profile_id)
        )
        expected = 0 if self.slot_type == "character_name" else 1
        if present != expected:
            if expected == 0:
                msg = (
                    "character_name carries no value; its value is "
                    "synthesized from the active character"
                )
            else:
                msg = (
                    "exactly one of value_text, value_enum, value_profile_id "
                    "must be set"
                )
            raise ValueError(msg)
        return self


class PersonalizationUpdateBody(BaseModel):
    """The whole personalization state for one profile: replace, not patch.

    A partial patch over a per-slot table invites ambiguity about whether an
    absent slot_type means "unchanged" or "cleared" (plan section 6.1), so
    this is always a full replace: any slot_type omitted from ``slots`` is
    cleared. The two ``real_name_*`` booleans are written through this route
    rather than ``ProfileUpdateBody``, so one guardian save is one transaction
    (plan section 6.1).
    """

    model_config = ConfigDict(extra="forbid")

    real_name_ring1_enabled: bool = False
    real_name_ring2_enabled: bool = False
    slots: list[PersonalizationSlotBody] = Field(default_factory=list)


class PersonalizationSlotView(BaseModel):
    """One slot's stored value and ring flags, plus the read-only ceiling."""

    slot_type: str
    value_text: str | None
    value_enum: str | None
    value_profile_id: str | None
    ring1_enabled: bool
    ring2_enabled: bool
    # Derived from the taxonomy ceiling (every slot type except pronoun_set,
    # dedication, and character_name), so the UI can grey out what the DB
    # CHECK would reject anyway rather than reimplementing the ceiling list
    # in TypeScript.
    ring2_eligible: bool


class PersonalizationView(BaseModel):
    """A profile's full personalization state: the GET and PUT response."""

    real_name_ring1_enabled: bool
    real_name_ring2_enabled: bool
    slots: list[PersonalizationSlotView]


class PersonalizationReceiveView(BaseModel):
    """The caller's own family's viewer-side receive switch (ADR-023 8.6)."""

    enabled: bool


class PersonalizationReceiveBody(BaseModel):
    """Set the viewer-side receive switch for the caller's own family.

    Deliberately not an evidentiary consent record: no signature, no policy
    version, no IP. It is a stored preference (design plan 8.6, "a notice
    fixes surprise; a signature would not fix it any better"), so the body
    is the single boolean and nothing else.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool


class Ring2ConsentGrantBody(BaseModel):
    """A sharer-side guardian's grant, or supersede, of a ring-2 disclosure.

    ``consent_ip`` and ``consent_accepted_at`` are never accepted from the
    client; the route stamps both server-side, mirroring how
    ``POST /v1/onboarding`` handles the ADR-018 D1 consent (plan section 6.1).
    """

    model_config = ConfigDict(extra="forbid")

    family_connection_id: str
    # Bounded and de-duplicated at the edge. The route rejects any element
    # that is not an eligible slot type, so a bogus VALUE was never storable,
    # but nothing bounded the list's LENGTH: `["dedication"] * 100_000` is
    # every-element-eligible and would have been written verbatim into the
    # consent row's JSONB column and echoed back by `GET /v1/me`. The bound is
    # the number of RING-2 ELIGIBLE slot types, since covering one twice
    # conveys nothing and a ring-1-only slot can never be covered at all, and
    # `_dedupe_slot_types` makes that bound reachable only by a genuinely
    # distinct list.
    covered_slot_types: Annotated[
        list[str],
        Field(min_length=1, max_length=_PERSONALIZATION_RING2_SLOT_TYPE_COUNT),
        AfterValidator(_dedupe_slot_types),
    ]
    policy_version: Annotated[str, StringConstraints(max_length=32)]
    signer_name: Annotated[
        str, StringConstraints(max_length=200, strip_whitespace=True, min_length=1)
    ]
    accepted: Literal[True]
    # Required true when covered_slot_types includes the sibling slot
    # (plan section 6.1); enforced in the route handler, not here, since the
    # rule depends on the sibling slot_type constant from personalization_values.
    sibling_authority_attested: bool | None = None


class Ring2ConsentView(BaseModel):
    """The result of a ring-2 consent grant or revoke."""

    id: str
    child_profile_id: str
    family_connection_id: str | None
    covered_slot_types: list[str]
    sibling_authority_attested: bool
    consent_accepted_at: datetime | None
    consent_policy_version: str | None
    consent_signer_name: str | None
    revoked_at: datetime | None


class PersonalizationValuesView(BaseModel):
    """The resolved values payload for one storybook, at whichever ring applies.

    An empty ``values`` dict is the universal failure mode (plan section 8.4):
    there is no requested-slot-type filter, and every failure mode (missing
    subject, receive-toggle off, unconnected family, revoked consent, a
    deactivated or processing-restricted subject) renders identically as an
    empty payload rather than a 403, so the route leaks nothing about whether
    a subject or connection exists (plan sections 8.3-8.5).
    """

    subject_profile_id: str | None
    ring: Literal[1, 2] | None
    policy_version: str | None
    resolved_at: datetime
    values: dict[str, str]
    # The canonical sentinel pattern (`storybook.sentinels.SENTINEL_RE.pattern`),
    # shipped so the client resolver never re-derives it. Plan risk R9: two
    # rendering implementations drift, and the drift is silent because a
    # near-miss pattern still matches most tokens. Present on EVERY response
    # including the empty one, because a client with the flag on and no values
    # still has to strip markers to their generic words.
    sentinel_pattern: str
    # slot id -> personalization field, from the book's theme contract
    # (`generation.binding.personalizable_slot_fields`). The join the resolver
    # cannot make on its own: prose sentinels carry the slot id, `values` above
    # is keyed by slot type. Empty on the empty payload and on any book whose
    # contract declares no personalizable slot.
    slot_bindings: dict[str, str]


# ---------------------------------------------------------------------------
# Error envelope (the wire contract of app.py's exception handlers)
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """The standard error envelope rendered for core-exception failures.

    Mirrors ``ProjectBaseError.to_dict()`` after ``_client_safe_error``
    sanitization (``app.py``): the exception class name, its public message,
    an optional machine-readable ``code``, and optional structured ``details``
    with the sensitive ``value``/``context`` keys already pruned. Referenced
    by the OpenAPI ``responses`` declarations below so 401/403/404/409 bodies
    are part of the documented contract, not folklore; it is never
    instantiated on the serving path (the handlers render dicts directly).
    """

    error: str
    message: str
    code: str | None = None
    details: dict[str, object] | None = None


# One generic description per documented error status. Route docstrings (the
# "Raises:" sections surfaced in /docs and the generated SDK) carry the
# endpoint-specific conditions; these stay deliberately generic so the helper
# below can be reused by every router.
_ERROR_DESCRIPTIONS: dict[int, str] = {
    400: "Domain rule violation (for example, an exhausted quota).",
    401: "Missing, malformed, expired, or unknown bearer token.",
    403: "Authenticated, but not permitted to act on this resource.",
    404: "The referenced resource does not exist.",
    409: "The action conflicts with the resource's current state.",
    429: "A per-account quota was exhausted; the action may succeed later.",
    502: "An external service failed or timed out; the action may succeed later.",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, object]]:
    """Build an OpenAPI ``responses`` mapping for the standard error envelope.

    Args:
        status_codes: The HTTP error statuses the route (or router) can
            produce via the core exception handlers; each must be one of the
            keys of ``_ERROR_DESCRIPTIONS``.

    Returns:
        dict[int | str, dict[str, object]]: A mapping suitable for FastAPI's
        ``responses=`` parameter, one ``ErrorResponse`` entry per status.
    """
    return {
        code: {"model": ErrorResponse, "description": _ERROR_DESCRIPTIONS[code]}
        for code in status_codes
    }
