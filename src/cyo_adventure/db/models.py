"""SQLAlchemy ORM models for the operational entities (tech-spec data model).

These map the Postgres tables that back the reader: family ownership, users and
their roles, per-child profiles, storybooks and their immutable versions, and the
per-child reading state and completions. The Storybook content blob is stored
inline on ``storybook_version.blob`` for Phase 1 (the MinIO ``blob_ref`` path is
deferred); see the module note on the blob column.

Enumerated columns (role, status, age band) are stored as strings validated at
the application boundary rather than native Postgres enums, which keeps Alembic
migrations simple and avoids enum-type churn.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cyo_adventure.core.database import Base
from cyo_adventure.storybook.evaluator import VarState
from cyo_adventure.storybook.models import AgeBand

# All timestamps are stored timezone-aware (TIMESTAMP WITH TIME ZONE).
_TS = DateTime(timezone=True)

# Foreign-key target column names, named once to avoid duplicated string literals.
_FK_FAMILY = "family.id"
_FK_USER = "user.id"
_FK_CHILD_PROFILE = "child_profile.id"
_FK_STORYBOOK = "storybook.id"
_FK_CONCEPT = "concept.id"
_FK_SERIES = "series.id"

# The five storybook lifecycle states, named once for the CHECK constraint.
_STORYBOOK_STATUS_VALUES = (
    "'draft', 'in_review', 'needs_revision', 'published', 'archived'"
)

# The six generation-job lifecycle states, named once for the CHECK constraint.
# "awaiting_manual_fill" is set only for method="skeleton_fill" +
# mechanism="skill" jobs (see story_requests/authoring_plan.py), and cleared by
# generation/import_story.py::resume_manual_fill once the human-authored fill
# is imported.
_GENERATION_JOB_STATUS_VALUES = (
    "'queued', 'running', 'passed', 'needs_review', 'failed', 'awaiting_manual_fill'"
)

# The four story-request lifecycle states, named once for the CHECK constraint.
_STORY_REQUEST_STATUS_VALUES = "'pending', 'approved', 'declined', 'blocked'"

# Derived from the AgeBand enum so the at-rest CHECK can never drift from the
# application vocabulary; adding a band changes this SQL and thereby forces a
# migration (alembic autogenerate flags the constraint difference).
_AGE_BAND_VALUES = ", ".join(f"'{band.value}'" for band in AgeBand)

# The three story-request initiator roles, length bands, and narrative styles
# (WS-B), named once for their CHECK constraints.
_STORY_REQUEST_INITIATOR_VALUES = "'child', 'guardian', 'admin'"
_STORY_REQUEST_LENGTH_VALUES = "'short', 'medium', 'long'"
_STORY_REQUEST_STYLE_VALUES = "'prose', 'gamebook'"


class Family(Base):
    """A family: the ownership root for users, profiles, and stories."""

    __tablename__ = "family"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class Series(Base):
    """A named, family-owned chain of storybooks (WS-B PR 3, decision B2).

    DB-level linkage only in WS-B: books reference a series via
    ``storybook.series_id``/``book_index``; the embedded document ``Series``
    metadata block (storybook/models.py) is NOT written, so the SR-1..SR-7
    cross-book validator stays dormant until WS-G adds structural chaining.

    Attributes:
        id: Surrogate primary key.
        family_id: Owning family (NOT NULL, decision B3; widening is WS-E).
        title: Guardian- or admin-ratified series title (screened at intake).
        age_band: The band every book in the series targets; continuations
            must match it (approval rejects a mismatch).
        carries_state: ADR-011 band rule: False (episodic) for '3-5'/'5-8',
            True for all higher bands.
        created_by: The ratifying user, or None.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "series"
    __table_args__ = (
        CheckConstraint(
            f"age_band IN ({_AGE_BAND_VALUES})",
            name="ck_series_age_band",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_FAMILY), index=True)
    title: Mapped[str] = mapped_column(String(120))
    age_band: Mapped[str] = mapped_column(String(16))
    carries_state: Mapped[bool] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class User(Base):
    """An authenticated user (guardian, child, or admin) within a family."""

    __tablename__ = "user"
    # #CRITICAL: security: ``role`` is coerced to the closed Role enum at the auth
    # boundary (api/deps.py); this CHECK is the at-rest backstop so a non-API write
    # path cannot persist an unmodeled role that would then drive authorization.
    # #VERIFY: api/deps.Role(user.role) raises on any value outside this set.
    __table_args__ = (
        CheckConstraint("role IN ('guardian', 'child', 'admin')", name="ck_user_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_FAMILY), index=True)
    role: Mapped[str] = mapped_column(String(16))
    authn_subject: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Null for guardians; set for a child user to the single profile it may act on.
    child_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE), default=None
    )
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class ChildProfile(Base):
    """A per-child reading profile with age band and content caps."""

    __tablename__ = "child_profile"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_FAMILY), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    age_band: Mapped[str] = mapped_column(String(16))
    reading_level_cap: Mapped[float] = mapped_column(default=99.0)
    allowed_content_flags: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict
    )
    tts_enabled: Mapped[bool] = mapped_column(default=False)
    avatar: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class Storybook(Base):
    """A story's lifecycle row; one per story id regardless of version."""

    __tablename__ = "storybook"
    # #CRITICAL: data integrity: ``status`` is the lifecycle ORM boundary, coerced
    # to the closed Status enum in publishing/state_machine.py; this CHECK is the
    # at-rest backstop so no write path persists a status outside the five resting
    # states. GenerationJob.status is a SEPARATE lifecycle with its own CHECK
    # (ck_generation_job_status), defined on that model.
    # #VERIFY: Status(storybook.status) raises on any value outside this set.
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_STORYBOOK_STATUS_VALUES})",
            name="ck_storybook_status",
        ),
        UniqueConstraint(
            "series_id", "book_index", name="uq_storybook_series_book_index"
        ),
        CheckConstraint(
            "book_index IS NULL OR book_index >= 1",
            name="ck_storybook_book_index",
        ),
        CheckConstraint(
            "(series_id IS NULL) = (book_index IS NULL)",
            name="ck_storybook_series_index_pairing",
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_FAMILY), index=True)
    current_published_version: Mapped[int | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_SERIES), default=None
    )
    book_index: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class StorybookVersion(Base):
    """An immutable version of a story, including its content blob.

    The Storybook JSON is stored inline on ``blob`` for Phase 1; ``blob_ref`` is
    reserved for the MinIO object key once object storage is wired (Phase 5).
    """

    __tablename__ = "storybook_version"

    storybook_id: Mapped[str] = mapped_column(
        ForeignKey(_FK_STORYBOOK), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    blob: Mapped[dict[str, object]] = mapped_column(JSONB)
    blob_ref: Mapped[str | None] = mapped_column(String(512), default=None)
    validation_report: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
    )
    moderation_report: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    published_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    model: Mapped[str | None] = mapped_column(String(120), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(120), default=None)
    # Which generation provider produced this version ("mock", "anthropic",
    # "openrouter", ...), or the "import" sentinel for a version created via
    # the offline authoring import path (generation/import_story.py) rather
    # than the live worker. Nullable: backfilled rows predating this column
    # (and any future write path that forgets to stamp it) simply have no
    # provenance recorded, which degrades to "unknown" for display, not an error.
    provider: Mapped[str | None] = mapped_column(String(120), default=None)
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class ReadingState(Base):
    """Per-child, per-story reading progress with revision-based concurrency.

    ``visit_set`` is persisted as a JSON list (it drives ``once: true`` effects)
    and ``last_event_id`` records the most recently applied write so idempotent
    replays of an offline queue are no-ops.
    """

    __tablename__ = "reading_state"
    __table_args__ = (
        # A saved state is pinned to a concrete published version; the composite
        # FK prevents persisting a reading state for a version that does not exist.
        ForeignKeyConstraint(
            ["storybook_id", "version"],
            ["storybook_version.storybook_id", "storybook_version.version"],
        ),
    )

    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE), primary_key=True
    )
    storybook_id: Mapped[str] = mapped_column(
        ForeignKey(_FK_STORYBOOK), primary_key=True
    )
    version: Mapped[int] = mapped_column()
    current_node: Mapped[str] = mapped_column(String(120))
    var_state: Mapped[VarState] = mapped_column(JSONB, default=dict)
    path: Mapped[list[str]] = mapped_column(JSONB, default=list)
    visit_set: Mapped[list[str]] = mapped_column(JSONB, default=list)
    save_slots: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    state_revision: Mapped[int] = mapped_column(default=0)
    last_event_id: Mapped[str | None] = mapped_column(String(64), default=None)
    updated_by_device_id: Mapped[str | None] = mapped_column(String(64), default=None)
    last_synced_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )


class Completion(Base):
    """Records that a child found a particular ending of a story version."""

    __tablename__ = "completion"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storybook_id", "version"],
            ["storybook_version.storybook_id", "storybook_version.version"],
        ),
    )

    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE), primary_key=True
    )
    storybook_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    ending_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    found_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class Rating(Base):
    """A child's 1-5 rating of a storybook.

    Unlike ``Completion``, which pins to an immutable ``storybook_version`` via a
    composite FK, a rating is about the *book* as a whole and is **mutable**: a
    child may re-rate, overwriting the prior value. The coarser
    ``(child_profile_id, storybook_id)`` grain is also what the cross-family
    lineage join in Phase B will need.
    """

    __tablename__ = "rating"
    __table_args__ = (
        CheckConstraint("value BETWEEN 1 AND 5", name="ck_rating_value_range"),
    )

    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE), primary_key=True
    )
    storybook_id: Mapped[str] = mapped_column(
        String(120), ForeignKey(_FK_STORYBOOK), primary_key=True
    )
    # #CRITICAL: data integrity: ``value`` is bounded 1-5 at the API boundary by
    # RatingBody and enforced at rest by the ck_rating_value_range CHECK above,
    # so a non-API write path (admin script, backfill, raw SQL) cannot persist an
    # out-of-range value that would then be served back to clients.
    # #VERIFY: RatingBody schema tests cover the boundary; the DB CHECK is the
    # at-rest backstop.
    value: Mapped[int] = mapped_column()
    rated_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )


class StorybookAssignment(Base):
    """A guardian's grant of one published story to one child profile.

    Composite-keyed on ``(child_profile_id, storybook_id)`` so a profile is
    assigned a book at most once. ``assigned_by`` records the granting guardian,
    or NULL for a system backfill (the migration that preserves pre-assignment
    visibility). This table is the read-gate: the library listing and the direct
    version fetch both filter on it, so a child sees only stories explicitly
    assigned to their profile.
    """

    __tablename__ = "storybook_assignment"
    # #CRITICAL: security: this row is the sole authority for whether a child may
    # see a story; the composite PK indexes the child-side lookup, and the extra
    # index serves the storybook-side lookup used by the guardian assign list and
    # the migration backfill. A missing/duplicate row must not silently widen or
    # narrow visibility.
    # #VERIFY: composite PK enforces at-most-one; api/library.py gates both read
    # paths on an EXISTS/IN over this table.
    __table_args__ = (Index("ix_storybook_assignment_storybook_id", "storybook_id"),)

    child_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE), primary_key=True
    )
    storybook_id: Mapped[str] = mapped_column(
        String(120), ForeignKey(_FK_STORYBOOK), primary_key=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class Concept(Base):
    """A generation concept brief: the intake form for a story request.

    One Concept row is created per guardian request and holds the serialized
    ``ConceptBrief`` payload. A concept drives one or more ``GenerationJob``
    attempts; the brief is immutable once written.

    Attributes:
        id: Surrogate primary key.
        family_id: Owning family; all access checks are scoped to this.
        brief: The full ``ConceptBrief`` JSON blob (age band, topic, constraints,
            etc.). Schema is validated at the application boundary before insert.
        created_by: The guardian user who submitted the concept. Nullable because
            the system may create concepts without a logged-in user in tests.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "concept"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_FAMILY), index=True)
    # #ASSUME: data integrity: ``brief`` shape is validated by ConceptBrief
    # Pydantic model before insertion; the DB stores raw JSON with no
    # column-level schema constraint.
    # #VERIFY: ensure all write paths go through ConceptBrief.model_validate
    # before calling session.add(Concept(...)).
    brief: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class StoryRequest(Base):
    """A child's free-text story idea awaiting a guardian or admin decision.

    Submitted by a child (running under the guardian token in R1). The request
    text is screened at submission (PII guard + Stage-0 classifiers); a
    bright-line hit lands the row in the ``blocked`` state before any guardian
    reads the raw text. A guardian or admin then approves it (which builds a
    ``ConceptBrief`` and enters the generation pipeline, linking ``concept_id``)
    or declines it.

    ``family_id`` is denormalized (stored, not derived from ``profile_id``) so
    the guardian list and the family-scope authz check stay single-table; a
    profile never changes family, so the value cannot drift.

    Attributes:
        id: Surrogate primary key.
        family_id: Owning family; all guardian access is scoped to this.
        profile_id: The requesting child profile, or ``None`` for a
            profile-less request (WS-B PR 2).
        request_text: The child's short free-text idea (<= 500 chars).
        status: Lifecycle state (pending, approved, declined, blocked).
        initiator_role: Who submitted the request (child, guardian, admin).
        age_band: The reading band the request targets. Required at flush
            with no default: every creation path must set it explicitly (from
            the requesting profile, or from the guardian's confirmation), so a
            missed path fails loudly instead of silently drifting.
        length: The requested story length (short, medium, long), or ``None``
            before a guardian confirms it.
        narrative_style: The requested narrative style (prose, gamebook).
        moderation_flags: Redacted screening findings (category/verdict/message
            plus a blocked flag), or ``None`` before screening. Never raw
            classifier score/source.
        reviewed_by: The guardian/admin who approved or declined, or ``None``.
        reviewed_at: When the decision was recorded, or ``None``.
        concept_id: The concept created on approval, or ``None``.
        series_id: The series this request continues, or ``None`` for a
            standalone request (WS-B PR 3).
        anchor_storybook_id: The storybook this soft continuation follows on
            from, or ``None``.
        proposed_series_title: The kid's original series title proposal,
            retained as an audit trail after ratification or request decline.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "story_request"
    # #CRITICAL: data integrity: ``status``, ``initiator_role``, ``age_band``,
    # ``length``, and ``narrative_style`` are closed vocabularies; these CHECKs
    # are the at-rest backstop (mirroring ck_generation_job_status) so no write
    # path persists a value outside them. ck_story_request_style_band is the
    # child-safety backstop for ADR-011: gamebook branching is teen-only
    # ('13-16', '16+'), so no row can pair a gamebook request with a younger
    # band even if an application bug slips one past the API.
    # #VERIFY: the API boundary rejects out-of-vocabulary values first:
    # api/schemas.py::StoryRequestStatus coercion for status, and
    # StoryRequestApproveBody's AgeBand/Length/NarrativeStyle enums plus its
    # _style_allowed_for_band validator (which mirrors style_band) at approve.
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_STORY_REQUEST_STATUS_VALUES})",
            name="ck_story_request_status",
        ),
        CheckConstraint(
            f"initiator_role IN ({_STORY_REQUEST_INITIATOR_VALUES})",
            name="ck_story_request_initiator_role",
        ),
        CheckConstraint(
            f"age_band IN ({_AGE_BAND_VALUES})",
            name="ck_story_request_age_band",
        ),
        CheckConstraint(
            f"length IS NULL OR length IN ({_STORY_REQUEST_LENGTH_VALUES})",
            name="ck_story_request_length",
        ),
        CheckConstraint(
            f"narrative_style IN ({_STORY_REQUEST_STYLE_VALUES})",
            name="ck_story_request_narrative_style",
        ),
        CheckConstraint(
            "narrative_style = 'prose' OR age_band IN ('13-16', '16+')",
            name="ck_story_request_style_band",
        ),
        # A request may propose a NEW series title or continue an existing
        # series via an anchor, never both. The name reflects the two columns
        # actually constrained (proposed_series_title, anchor_storybook_id);
        # ``series_id`` is guarded separately below.
        CheckConstraint(
            "NOT (proposed_series_title IS NOT NULL "
            "AND anchor_storybook_id IS NOT NULL)",
            name="ck_story_request_title_anchor_mutex",
        ),
        # #ASSUME: data-integrity: an anchored (continuation) request always
        # carries the anchor's series id; generation.series_link relies on it
        # to assign book_index, so a null series_id on an anchored row would
        # silently drop the storybook out of its series.
        # #VERIFY: every anchored-insert path sets series_id from resolve_anchor
        # (api/story_requests.py kid + authored create); this constraint blocks
        # a drifted row from a manual edit or a future code path.
        CheckConstraint(
            "anchor_storybook_id IS NULL OR series_id IS NOT NULL",
            name="ck_story_request_anchor_requires_series",
        ),
        Index("ix_story_request_family_status", "family_id", "status"),
        Index("ix_story_request_profile_status", "profile_id", "status"),
        Index("ix_story_request_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_FAMILY))
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_CHILD_PROFILE), default=None
    )
    request_text: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    initiator_role: Mapped[str] = mapped_column(
        String(16), default="child", server_default="child"
    )
    age_band: Mapped[str] = mapped_column(String(16))
    length: Mapped[str | None] = mapped_column(String(16), default=None)
    narrative_style: Mapped[str] = mapped_column(
        String(16), default="prose", server_default="prose"
    )
    # #CRITICAL: security: redacted findings only (category/verdict/message +
    # blocked flag); raw classifier score/source and the child's raw text of a
    # blocked request are NEVER stored here or surfaced to a guardian.
    # #VERIFY: story_requests/screening.py builds this via the GuardianFinding
    # projection; test_story_requests covers the redaction shape.
    moderation_flags: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(_TS, default=None)
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_CONCEPT), default=None
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_SERIES), default=None
    )
    anchor_storybook_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey(_FK_STORYBOOK), default=None
    )
    proposed_series_title: Mapped[str | None] = mapped_column(String(120), default=None)
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


_MIN_VERDICT_VALUES = "'advisory', 'flag', 'block'"


class ModerationThreshold(Base):
    """Sparse per-(age_band, category) override of the surfacing default.

    Absence of a row means the code default applies
    (``moderation/thresholds.py::DEFAULT_THRESHOLD``). The table is small
    (admin-curated), so policy loads read it whole.

    Attributes:
        id: Surrogate primary key.
        age_band: The reader age band this override applies to.
        category: The moderation category this override applies to.
        min_verdict: Minimum verdict severity that surfaces to review
            (one of ``advisory``, ``flag``, ``block``).
        min_score: Optional classifier-score floor in [0.0, 1.0], or
            ``None`` to use the verdict gate alone.
        updated_by: The admin who last edited this override, or ``None``.
        updated_at: Last edit time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "moderation_threshold"
    # #CRITICAL: data integrity / security: these overrides gate which
    # moderation findings surface for review by age band; a row persisted with
    # an unknown min_verdict or an out-of-range min_score could silently relax
    # what content reaches children, and an unknown age_band would be a dead
    # row the loader silently skips. The ck_moderation_threshold_age_band,
    # ck_moderation_threshold_min_verdict, and ck_moderation_threshold_min_score
    # CHECKs are the at-rest backstop against any non-API write path (admin
    # script, backfill, raw SQL).
    # #VERIFY: moderation/thresholds.py validates at the application boundary;
    # tests/integration/test_moderation_threshold_migration.py round-trips the
    # migration that creates both CHECKs.
    __table_args__ = (
        CheckConstraint(
            f"age_band IN ({_AGE_BAND_VALUES})",
            name="ck_moderation_threshold_age_band",
        ),
        CheckConstraint(
            f"min_verdict IN ({_MIN_VERDICT_VALUES})",
            name="ck_moderation_threshold_min_verdict",
        ),
        CheckConstraint(
            "min_score IS NULL OR (min_score >= 0.0 AND min_score <= 1.0)",
            name="ck_moderation_threshold_min_score",
        ),
        UniqueConstraint(
            "age_band", "category", name="uq_moderation_threshold_band_category"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    age_band: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(64))
    min_verdict: Mapped[str] = mapped_column(String(16))
    min_score: Mapped[float | None] = mapped_column(default=None)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )


class ModerationThresholdAudit(Base):
    """Append-only audit of threshold edits (who changed what, when).

    Deliberately minimal: WS-D's pipeline_event log will subsume this role;
    keep this table write-only until then.

    Attributes:
        id: Surrogate primary key.
        age_band: The age band of the edited override.
        category: The moderation category of the edited override.
        action: What happened, either ``upsert`` or ``delete``.
        old_min_verdict: Verdict floor before the edit, or ``None`` on insert.
        new_min_verdict: Verdict floor after the edit, or ``None`` on delete.
        old_min_score: Score floor before the edit, or ``None``.
        new_min_score: Score floor after the edit, or ``None``.
        changed_by: The admin who made the edit (required; see RAD tag).
        changed_at: When the edit was recorded (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "moderation_threshold_audit"
    # #ASSUME: data integrity: the audit trail is only trustworthy if every row
    # names a known action; a typo'd action written by a non-API path (script,
    # raw SQL) would silently corrupt the "who changed what" record. No age_band
    # CHECK here on purpose: audit rows are history, and retiring a band must
    # not invalidate old records.
    # #VERIFY: the WS-A admin API writes only 'upsert'/'delete';
    # tests/integration/test_moderation_threshold_migration.py round-trips the
    # migration that creates this CHECK.
    __table_args__ = (
        CheckConstraint(
            "action IN ('upsert', 'delete')",
            name="ck_moderation_threshold_audit_action",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    age_band: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))  # 'upsert' | 'delete'
    old_min_verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    new_min_verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    old_min_score: Mapped[float | None] = mapped_column(default=None)
    new_min_score: Mapped[float | None] = mapped_column(default=None)
    # #CRITICAL: security / data integrity: every threshold edit must be
    # attributable; ``changed_by`` is a NOT NULL FK to user.id so an anonymous
    # or dangling edit record cannot be persisted. Rows are append-only by
    # convention (no update/delete path in the application layer) until WS-D's
    # pipeline_event log subsumes this table.
    # #VERIFY: the round-trip test in
    # tests/integration/test_moderation_threshold_migration.py covers the
    # migration that creates this FK; the WS-A admin API must write one audit
    # row per upsert/delete and never mutate existing rows.
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_USER))
    changed_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class ModerationSetting(Base):
    """A single named global moderation scalar (WS-A admin noise-floor addendum).

    Distinct from ``ModerationThreshold``: this table holds global scalars
    (currently one row, key ``admin_noise_floor``) rather than sparse
    per-(age_band, category) overrides. No append-only audit table backs this
    one; see the module-level design note in
    ``docs/planning/ws-a-admin-noise-floor.md`` ("Design decision") for the
    deliberate YAGNI call.

    Attributes:
        key: The setting's unique name (e.g. ``admin_noise_floor``).
        value: The scalar value, constrained to [0.0, 1.0].
        updated_by: The admin who last edited this setting, or ``None``.
        updated_at: Last edit time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "moderation_setting"
    # #ASSUME: security: admin_noise_floor controls which ADVISORY findings
    # surface on the admin moderation review surface; a row persisted with an
    # out-of-range value could hide real signal behind an over-wide floor (or
    # defeat the denoise with a floor of 0). The ck_moderation_setting_value
    # CHECK is the at-rest backstop against any non-API write path.
    # #VERIFY: the application boundary (Task A3's PUT endpoint) validates
    # to [0, 1] before writing; tests/integration/test_moderation_setting_migration.py
    # round-trips the migration that creates this CHECK.
    __table_args__ = (
        CheckConstraint(
            "value >= 0 AND value <= 1", name="ck_moderation_setting_value"
        ),
    )

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[float] = mapped_column()
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )


_ALLOWLIST_PROVIDER_VALUES = "'anthropic', 'openrouter', 'modal', 'ollama'"


class ProviderModelAllowlist(Base):
    """Admin-editable allowlist of (provider, model_id) pairs eligible for generation.

    Providers are a code-fixed enum (the CHECK below); only the model id
    within a provider is admin-managed. ``mock`` is never allowlisted: it is
    a CI-only test double, never a real generation backend.

    Attributes:
        id: Surrogate primary key.
        provider: One of the fixed provider names (see the CHECK constraint).
        model_id: The provider-native model id (e.g. ``claude-sonnet-4-6``,
            ``anthropic/claude-sonnet-4.6``).
        enabled: Whether this pair is currently selectable. Disabling a row
            (rather than deleting it) preserves audit history.
        display_name: Optional human label for a future admin UI.
        created_by: The admin who added this row, or ``None``.
        updated_by: The admin who last edited this row, or ``None``.
        created_at: Insert time (UTC, TIMESTAMPTZ).
        updated_at: Last edit time (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "provider_model_allowlist"
    # #CRITICAL: security: this is the control that keeps free-string model
    # ids out of billing; the ck_provider_model_allowlist_provider CHECK is
    # the at-rest backstop against any non-API write path (admin script,
    # backfill, raw SQL) introducing an unrecognized billing backend.
    # #VERIFY: generation/allowlist.py::is_enabled_allowlist_pair is the
    # single read path the authoring-plan endpoint trusts; both this CHECK and
    # that helper are round-tripped by
    # tests/integration/test_provider_model_allowlist_migration.py and
    # tests/integration/test_allowlist.py.
    __table_args__ = (
        CheckConstraint(
            f"provider IN ({_ALLOWLIST_PROVIDER_VALUES})",
            name="ck_provider_model_allowlist_provider",
        ),
        UniqueConstraint(
            "provider", "model_id", name="uq_provider_model_allowlist_provider_model"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )

    def __init__(  # noqa: PLR0913
        self,
        *,
        provider: str,
        model_id: str,
        enabled: bool = True,
        display_name: str | None = None,
        created_by: uuid.UUID | None = None,
        updated_by: uuid.UUID | None = None,
    ) -> None:
        """Initialize a ProviderModelAllowlist row with proper defaults."""
        self.id = uuid.uuid4()
        self.provider = provider
        self.model_id = model_id
        self.enabled = enabled
        self.display_name = display_name
        self.created_by = created_by
        self.updated_by = updated_by


class ProviderModelAllowlistAudit(Base):
    """Append-only audit of allowlist edits (who changed what, when).

    Deliberately minimal, mirroring ``ModerationThresholdAudit``: WS-D's
    pipeline_event log will subsume this role; keep this table write-only
    until then.

    Attributes:
        id: Surrogate primary key.
        provider: The affected row's provider (natural-key half).
        model_id: The affected row's model id (natural-key half).
        action: What happened: ``create``, ``update``, or ``delete``.
        old_enabled: The ``enabled`` value before the edit, or ``None`` on create.
        new_enabled: The ``enabled`` value after the edit, or ``None`` on delete.
        changed_by: The admin who made the edit (required; see RAD tag).
        changed_at: When the edit was recorded (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "provider_model_allowlist_audit"
    # #ASSUME: data integrity: the audit trail is only trustworthy if every
    # row names a known action; a typo'd action written by a non-API path
    # would silently corrupt the "who changed what" record.
    # #VERIFY: api/provider_allowlist.py writes only 'create'/'update'/'delete';
    # tests/integration/test_provider_model_allowlist_migration.py round-trips
    # the migration that creates this CHECK.
    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="ck_provider_model_allowlist_audit_action",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(16))
    old_enabled: Mapped[bool | None] = mapped_column(default=None)
    new_enabled: Mapped[bool | None] = mapped_column(default=None)
    # #CRITICAL: security / data integrity: every allowlist edit must be
    # attributable; changed_by is a NOT NULL FK to user.id so an anonymous or
    # dangling edit record cannot be persisted. Rows are append-only by
    # convention (no update/delete path in the application layer).
    # #VERIFY: tests/integration/test_provider_allowlist_api.py asserts one
    # audit row per POST/PUT/DELETE with the correct changed_by and
    # old/new_enabled pairing.
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_USER))
    changed_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class GenerationJob(Base):
    """Tracks a single staged-generation attempt for a Concept.

    One job row is created when a generation run is enqueued. The status
    transitions from ``queued`` to ``running``, then to ``passed``,
    ``needs_review``, or ``failed``. The ``report`` column stores the full
    ``GenerationOutcome`` payload once the job completes.

    ``storybook_id`` is stored as a plain nullable ``String(120)`` rather than
    a foreign key. A job may fail before any ``storybook`` row exists, so a
    hard FK would block inserting the failure record. The application layer is
    responsible for linking the job to the correct storybook after a successful
    run.

    Attributes:
        id: Surrogate primary key.
        concept_id: The concept this job was generated from.
        status: Lifecycle state (queued, running, passed, needs_review, failed).
            Stored as a string; validated at the application boundary.
        model: LLM model identifier used for generation.
        provider: LLM provider name (e.g. ``anthropic``, ``openai``).
        prompt_version: Semver-style tag for the prompt template revision.
        report: Full ``GenerationOutcome`` JSON including metrics and flags.
        storybook_id: String key of the produced storybook row, set only when
            the job reaches ``passed`` or ``needs_review``. Not a FK -- see
            class docstring.
        version: Storybook version number produced by this job.
        error: Short error message when status is ``failed``.
        created_at: Wall-clock insert time (UTC, TIMESTAMPTZ).
        updated_at: Updated on every status transition (UTC, TIMESTAMPTZ).
    """

    __tablename__ = "generation_job"
    # #CRITICAL: data integrity: ``status`` is a closed lifecycle; this CHECK is the
    # at-rest backstop (mirroring ck_storybook_status) so no write path persists a
    # status outside the five values. Application writes use only these values.
    # #VERIFY: see migration c3d4e5f6a7b8; values match _GENERATION_JOB_STATUS_VALUES.
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_GENERATION_JOB_STATUS_VALUES})",
            name="ck_generation_job_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    concept_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_CONCEPT), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    model: Mapped[str | None] = mapped_column(String(120), default=None)
    provider: Mapped[str | None] = mapped_column(String(120), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(120), default=None)
    # #CRITICAL: privacy: raw multi-stage LLM outputs; purge per ADR-007 after
    # 30 days or when the linked storybook version reaches "published" status.
    # #VERIFY: Phase 5 scheduled pg_cron job nulls this column (ADR-009 moved the
    # ADR-007 retention purge from RQ to pg_cron); GET /generation-jobs/{id}
    # (api/generation.py::get_generation_job) returns this field to the job's
    # own family guardian, family-scoped and guardian-gated, not admin-only;
    # only the list endpoint (GenerationJobListView) excludes it, and it is
    # never exposed to a child principal. There is no separate stage_log
    # column today; persisting a redacted stage log for post-purge
    # auditability is a Phase 5 task (see ADR-007).
    # #ASSUME: data integrity: ``report`` schema is determined by
    # GenerationOutcome at the application layer; no DB-level constraint
    # enforces its shape.
    # #VERIFY: all readers must tolerate None and partial report dicts (e.g.
    # when a job fails mid-run before a full report is assembled).
    report: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    # #ASSUME: data-integrity: shape is {"skeleton_slug": str, "theme_brief":
    # dict, "review_stage1_model": str | None, "review_stage2_model": str |
    # None} for method="skeleton_fill" jobs (see
    # story_requests/authoring_plan.py::build_authoring_plan); the two
    # review_* overrides are always written but may be null. None for
    # method="fresh_generation" jobs. No DB-level constraint enforces this.
    # #VERIFY: readers (api/generation.py::get_generation_job,
    # generation/worker.py::_review_stage2_override) must tolerate a missing or
    # wrong-typed key rather than trust the shape.
    authoring_metadata: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=None
    )
    # #ASSUME: data integrity: ``storybook_id`` is NOT a FK intentionally.
    # A job may fail before any storybook row is created; a hard FK constraint
    # would prevent inserting the failure record. The application layer must
    # verify the storybook row exists independently when reading this field.
    # #VERIFY: any code path that reads storybook_id and joins to storybook
    # must handle the case where the storybook row is absent.
    storybook_id: Mapped[str | None] = mapped_column(String(120), default=None)
    version: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(String(512), default=None)
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )
