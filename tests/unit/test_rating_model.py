"""Unit tests for the Rating ORM model registration."""

from __future__ import annotations

from cyo_adventure.core.database import Base

# Importing Rating registers its table on Base.metadata for the assertions below.
from cyo_adventure.db.models import Rating


def test_rating_table_registered() -> None:
    """The rating table is registered with the expected PK and columns."""
    assert Rating.__tablename__ == "rating"
    table = Base.metadata.tables["rating"]
    assert set(table.primary_key.columns.keys()) == {
        "child_profile_id",
        "storybook_id",
    }
    for col in ("value", "rated_at", "updated_at"):
        assert col in table.columns


def test_rating_storybook_fk_targets_storybook() -> None:
    """storybook_id is a plain FK to storybook.id (not storybook_version)."""
    table = Base.metadata.tables["rating"]
    fk_targets = {fk.target_fullname for fk in table.foreign_keys}
    assert "storybook.id" in fk_targets
    assert "child_profile.id" in fk_targets
