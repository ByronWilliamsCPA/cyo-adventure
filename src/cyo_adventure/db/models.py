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
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cyo_adventure.core.database import Base
from cyo_adventure.storybook.evaluator import VarState

# All timestamps are stored timezone-aware (TIMESTAMP WITH TIME ZONE).
_TS = DateTime(timezone=True)

# Foreign-key target column names, named once to avoid duplicated string literals.
_FK_FAMILY = "family.id"
_FK_USER = "user.id"
_FK_CHILD_PROFILE = "child_profile.id"
_FK_STORYBOOK = "storybook.id"
_FK_CONCEPT = "concept.id"


class Family(Base):
    """A family: the ownership root for users, profiles, and stories."""

    __tablename__ = "family"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class User(Base):
    """An authenticated user (guardian or child) within a family."""

    __tablename__ = "user"

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

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_FAMILY), index=True)
    current_published_version: Mapped[int | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_FK_USER), default=None
    )
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

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    concept_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_FK_CONCEPT), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    model: Mapped[str | None] = mapped_column(String(120), default=None)
    provider: Mapped[str | None] = mapped_column(String(120), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(120), default=None)
    # #ASSUME: data integrity: ``report`` schema is determined by
    # GenerationOutcome at the application layer; no DB-level constraint
    # enforces its shape.
    # #VERIFY: all readers must tolerate None and partial report dicts (e.g.
    # when a job fails mid-run before a full report is assembled).
    report: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
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
