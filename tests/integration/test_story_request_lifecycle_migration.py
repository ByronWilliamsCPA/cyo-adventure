"""Round-trip and backfill tests for the WS-B story_request lifecycle migration."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

if TYPE_CHECKING:
    from collections.abc import Iterator

REVISION = "d0e1f2a3b4c5"
DOWN_REVISION = "c9d0e1f2a3b4"


def _env(pg_url: str) -> dict[str, str]:
    import os

    env = os.environ.copy()
    env["CYO_ADVENTURE_DATABASE_URL"] = pg_url
    return env


@pytest.fixture
def upgraded_engine(migration_pg_url: str) -> Iterator[sa.engine.Engine]:
    """Reset to the previous head, seed a legacy row, then upgrade to REVISION.

    Function-scoped against a module-scoped container, so several test
    functions below reuse one Postgres instance. ``upgrade DOWN_REVISION`` is
    a no-op on a fresh database already past that point, and
    ``downgrade DOWN_REVISION`` is a no-op once already there; issuing both
    unconditionally is therefore idempotent from any of the three states a
    prior test in this module could have left the schema in (unmigrated,
    exactly DOWN_REVISION, or already at REVISION), and reliably lands on
    DOWN_REVISION. Downgrading drops the WS-B columns but not the rows a
    previous test seeded, so those are cleared explicitly before reseeding to
    keep row-count and uniqueness assumptions from leaking across tests.
    """
    env = _env(migration_pg_url)
    up = run_alembic(PROJECT_ROOT, env, "upgrade", DOWN_REVISION)
    assert up.returncode == 0, up.stderr
    down = run_alembic(PROJECT_ROOT, env, "downgrade", DOWN_REVISION)
    assert down.returncode == 0, down.stderr
    # psycopg (v3), not psycopg2, is the sync driver available in this project
    # (see pyproject.toml); a bare "postgresql://" URL defaults to psycopg2.
    sync_url = migration_pg_url.replace("+asyncpg", "+psycopg")
    engine = sa.create_engine(sync_url)
    try:
        _seed_and_upgrade(engine, env)
        yield engine
    finally:
        engine.dispose()


def _seed_and_upgrade(engine: sa.engine.Engine, env: dict[str, str]) -> None:
    """Delete legacy rows, seed a fresh family/user/profile/request, then upgrade."""
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM story_request"))
        conn.execute(sa.text('DELETE FROM "user"'))
        conn.execute(sa.text("DELETE FROM child_profile"))
        conn.execute(sa.text("DELETE FROM family"))
        family_id = str(uuid.uuid4())
        profile_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        # Minimal valid rows per the initial-schema create_table definitions
        # (see tests/integration/test_assignments_migration.py for the same
        # pattern): family needs name; user needs family_id/role/authn_subject
        # (there is no email column); child_profile needs display_name/
        # age_band/reading_level_cap/allowed_content_flags/tts_enabled.
        conn.execute(
            sa.text("INSERT INTO family (id, name) VALUES (:id, 'Fam')"),
            {"id": family_id},
        )
        conn.execute(
            sa.text(
                'INSERT INTO "user" (id, family_id, role, authn_subject) '
                "VALUES (:id, :family_id, 'guardian', 'g@example.com')"
            ),
            {"id": user_id, "family_id": family_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO child_profile (id, family_id, display_name, age_band, "
                "reading_level_cap, allowed_content_flags, tts_enabled) "
                "VALUES (:id, :family_id, 'Kid', '8-11', 99.0, '[]'::jsonb, false)"
            ),
            {"id": profile_id, "family_id": family_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO story_request (id, family_id, profile_id, request_text, status) "
                "VALUES (:id, :family_id, :profile_id, 'a fox story', 'pending')"
            ),
            {"id": str(uuid.uuid4()), "family_id": family_id, "profile_id": profile_id},
        )
    result = run_alembic(PROJECT_ROOT, env, "upgrade", REVISION)
    assert result.returncode == 0, result.stderr


def test_backfill_band_from_profile_and_role_default(
    upgraded_engine: sa.engine.Engine,
) -> None:
    with upgraded_engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT age_band, initiator_role, length, narrative_style FROM story_request"
            )
        ).one()
    assert row.age_band == "8-11"
    assert row.initiator_role == "child"
    assert row.length is None
    assert row.narrative_style == "prose"


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("initiator_role", "robot"),
        ("age_band", "2-4"),
        ("length", "epic"),
        ("narrative_style", "opera"),
    ],
)
def test_check_constraints_reject_bad_values(
    upgraded_engine: sa.engine.Engine, column: str, value: str
) -> None:
    with upgraded_engine.connect() as conn:
        family_id = conn.execute(sa.text("SELECT id FROM family")).scalar_one()
        profile_id = conn.execute(sa.text("SELECT id FROM child_profile")).scalar_one()
        defaults = {
            "id": str(uuid.uuid4()),
            "family_id": family_id,
            "profile_id": profile_id,
            "age_band": "8-11",
            "initiator_role": "child",
            "length": "short",
            "narrative_style": "prose",
        }
        defaults[column] = value
        with pytest.raises(IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO story_request "
                    "(id, family_id, profile_id, request_text, status, age_band, "
                    "initiator_role, length, narrative_style) "
                    "VALUES (:id, :family_id, :profile_id, 't', 'pending', :age_band, "
                    ":initiator_role, :length, :narrative_style)"
                ),
                defaults,
            )
        conn.rollback()


def test_gamebook_below_teen_band_rejected(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.connect() as conn:
        family_id = conn.execute(sa.text("SELECT id FROM family")).scalar_one()
        profile_id = conn.execute(sa.text("SELECT id FROM child_profile")).scalar_one()
        with pytest.raises(IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO story_request "
                    "(id, family_id, profile_id, request_text, status, age_band, "
                    "initiator_role, narrative_style) "
                    "VALUES (:id, :family_id, :profile_id, 't', 'pending', '8-11', "
                    "'child', 'gamebook')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "family_id": family_id,
                    "profile_id": profile_id,
                },
            )
        conn.rollback()


def test_downgrade_round_trip(migration_pg_url: str) -> None:
    env = _env(migration_pg_url)
    assert run_alembic(PROJECT_ROOT, env, "upgrade", REVISION).returncode == 0
    assert run_alembic(PROJECT_ROOT, env, "downgrade", DOWN_REVISION).returncode == 0
    assert run_alembic(PROJECT_ROOT, env, "upgrade", REVISION).returncode == 0
