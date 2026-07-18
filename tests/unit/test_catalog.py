"""Tests for the canonical catalog-ownership constants."""

import uuid
from pathlib import Path

import pytest

from cyo_adventure.core.catalog import LIBRARY_FAMILY_ID, LIBRARY_FAMILY_NAME

_MIGRATION = Path("supabase/migrations/20260718000000_library_family.sql")


@pytest.mark.unit
def test_library_family_id_is_the_reserved_sentinel() -> None:
    # The value is an ownership boundary seeded identically in every
    # environment; pin it so a refactor cannot silently orphan Library stories.
    assert uuid.UUID("00000000-0000-0000-0000-000000000001") == LIBRARY_FAMILY_ID


@pytest.mark.unit
def test_library_family_name_is_library() -> None:
    assert LIBRARY_FAMILY_NAME == "Library"


@pytest.mark.unit
def test_migration_seeds_the_same_library_id_and_name() -> None:
    # Guard against drift between the constant and the SQL that seeds the row:
    # the migration must insert exactly this id and name.
    sql = _MIGRATION.read_text(encoding="utf-8")
    assert str(LIBRARY_FAMILY_ID) in sql
    assert f"'{LIBRARY_FAMILY_NAME}'" in sql
    # Idempotent so re-running the migration or seeding over it is safe.
    assert "ON CONFLICT" in sql.upper()
