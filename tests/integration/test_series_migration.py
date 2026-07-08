"""Round-trip and constraint tests for the WS-B PR 3 series migration."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

REVISION = "e1f2a3b4c5d6"
DOWN_REVISION = "d0e1f2a3b4c5"


def _env(pg_url: str) -> dict[str, str]:
    import os

    env = os.environ.copy()
    env["CYO_ADVENTURE_DATABASE_URL"] = pg_url
    return env


@pytest.fixture
def upgraded_engine(migration_pg_url: str) -> sa.engine.Engine:
    """Land on DOWN_REVISION, clear rows, seed a family, upgrade to REVISION."""
    env = _env(migration_pg_url)
    up = run_alembic(PROJECT_ROOT, env, "upgrade", DOWN_REVISION)
    assert up.returncode == 0, up.stderr
    down = run_alembic(PROJECT_ROOT, env, "downgrade", DOWN_REVISION)
    assert down.returncode == 0, down.stderr
    sync_url = migration_pg_url.replace("+asyncpg", "+psycopg")
    engine = sa.create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM story_request"))
        conn.execute(sa.text("DELETE FROM storybook_version"))
        conn.execute(sa.text("DELETE FROM storybook"))
        conn.execute(sa.text("DELETE FROM family"))
        conn.execute(
            sa.text("INSERT INTO family (id, name) VALUES (:id, 'Fam')"),
            {"id": str(uuid.uuid4())},
        )
    result = run_alembic(PROJECT_ROOT, env, "upgrade", REVISION)
    assert result.returncode == 0, result.stderr
    return engine


def _family_id(conn: sa.Connection) -> str:
    return str(conn.execute(sa.text("SELECT id FROM family LIMIT 1")).scalar_one())


def _seed_series(conn: sa.Connection, family_id: str, band: str = "8-11") -> str:
    series_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO series (id, family_id, title, age_band, carries_state) "
            "VALUES (:id, :family_id, 'Fox Tales', :band, true)"
        ),
        {"id": series_id, "family_id": family_id, "band": band},
    )
    return series_id


def _seed_storybook(
    conn: sa.Connection,
    family_id: str,
    *,
    series_id: str | None = None,
    book_index: int | None = None,
) -> str:
    storybook_id = f"s_{uuid.uuid4().hex[:12]}"
    conn.execute(
        sa.text(
            "INSERT INTO storybook (id, family_id, status, series_id, book_index) "
            "VALUES (:id, :family_id, 'published', :series_id, :book_index)"
        ),
        {
            "id": storybook_id,
            "family_id": family_id,
            "series_id": series_id,
            "book_index": book_index,
        },
    )
    return storybook_id


def test_series_table_accepts_valid_row(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.begin() as conn:
        _seed_series(conn, _family_id(conn))


def test_series_rejects_bad_band(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.connect() as conn:
        family_id = _family_id(conn)
        conn.rollback()
        with pytest.raises(IntegrityError, match="ck_series_age_band"):
            _seed_series(conn, family_id, band="4-7")
        conn.rollback()


def test_storybook_unique_series_index(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.begin() as conn:
        family_id = _family_id(conn)
        series_id = _seed_series(conn, family_id)
        _seed_storybook(conn, family_id, series_id=series_id, book_index=1)
    with (
        upgraded_engine.connect() as conn,
        pytest.raises(IntegrityError, match="uq_storybook_series_book_index"),
        conn.begin(),
    ):
        _seed_storybook(conn, family_id, series_id=series_id, book_index=1)


def test_storybook_null_pair_rows_unlimited(
    upgraded_engine: sa.engine.Engine,
) -> None:
    """(NULL, NULL) never collides: non-series books are unaffected."""
    with upgraded_engine.begin() as conn:
        family_id = _family_id(conn)
        _seed_storybook(conn, family_id)
        _seed_storybook(conn, family_id)


def test_storybook_rejects_zero_index(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.connect() as conn:
        family_id = _family_id(conn)
        conn.rollback()
        with upgraded_engine.begin() as seed:
            series_id = _seed_series(seed, family_id)
        with pytest.raises(IntegrityError, match="ck_storybook_book_index"):
            _seed_storybook(conn, family_id, series_id=series_id, book_index=0)
        conn.rollback()


def test_storybook_rejects_unpaired_series_fields(
    upgraded_engine: sa.engine.Engine,
) -> None:
    with upgraded_engine.connect() as conn:
        family_id = _family_id(conn)
        conn.rollback()
        with upgraded_engine.begin() as seed:
            series_id = _seed_series(seed, family_id)
        with pytest.raises(IntegrityError, match="ck_storybook_series_index_pairing"):
            _seed_storybook(conn, family_id, series_id=series_id, book_index=None)
        conn.rollback()


def test_story_request_rejects_proposal_and_anchor(
    upgraded_engine: sa.engine.Engine,
) -> None:
    with upgraded_engine.connect() as conn:
        family_id = _family_id(conn)
        conn.rollback()
        with upgraded_engine.begin() as seed:
            anchor_id = _seed_storybook(seed, family_id)
        with pytest.raises(IntegrityError, match="ck_story_request_series_xor"):
            conn.execute(
                sa.text(
                    "INSERT INTO story_request (id, family_id, request_text, "
                    "status, age_band, proposed_series_title, anchor_storybook_id) "
                    "VALUES (:id, :family_id, 'x', 'pending', '8-11', "
                    "'Fox Tales', :anchor)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "family_id": family_id,
                    "anchor": anchor_id,
                },
            )
        conn.rollback()


def test_downgrade_round_trip(upgraded_engine: sa.engine.Engine) -> None:
    """Downgrade drops the table and columns; a re-upgrade restores them."""
    # Re-derive the env from the engine URL (the fixture consumed the raw URL).
    url = upgraded_engine.url.render_as_string(hide_password=False).replace(
        "+psycopg", "+asyncpg"
    )
    env = _env(url)
    down = run_alembic(PROJECT_ROOT, env, "downgrade", DOWN_REVISION)
    assert down.returncode == 0, down.stderr
    with upgraded_engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        }
    assert "series" not in tables
    up = run_alembic(PROJECT_ROOT, env, "upgrade", REVISION)
    assert up.returncode == 0, up.stderr
