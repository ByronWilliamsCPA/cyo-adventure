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

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, Uuid, func
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
    storybook_id: Mapped[str] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    ending_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    found_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
