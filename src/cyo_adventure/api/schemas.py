"""Pydantic request and response models for the reader API.

These are the wire contracts the frontend client is generated from. The
reading-state PUT body never carries a ``profile_id``: the profile is taken from
the path and validated against the token subject (IDOR defense).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cyo_adventure.storybook.evaluator import VarState


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


class LibraryItem(BaseModel):
    """A published story as seen in a child's library listing."""

    id: str
    title: str
    version: int
    age_band: str
    tier: int
    reading_level_target: float


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
