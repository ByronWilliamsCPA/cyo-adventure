"""Round-trip and append-only-trigger tests for the WS-D pipeline_event migration."""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

if TYPE_CHECKING:
    from collections.abc import Iterator

REVISION = "f2a3b4c5d6e7"
DOWN_REVISION = "e1f2a3b4c5d6"


def _env(pg_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["CYO_ADVENTURE_DATABASE_URL"] = pg_url
    return env


@pytest.fixture
def upgraded_engine(migration_pg_url: str) -> Iterator[sa.engine.Engine]:
    """Land on DOWN_REVISION, then upgrade to REVISION; yield a sync engine."""
    env = _env(migration_pg_url)
    up = run_alembic(PROJECT_ROOT, env, "upgrade", DOWN_REVISION)
    assert up.returncode == 0, up.stderr
    result = run_alembic(PROJECT_ROOT, env, "upgrade", REVISION)
    assert result.returncode == 0, result.stderr
    sync_url = migration_pg_url.replace("+asyncpg", "+psycopg")
    engine = sa.create_engine(sync_url)
    try:
        yield engine
    finally:
        engine.dispose()


def _insert_event(conn: sa.Connection) -> str:
    event_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO pipeline_event "
            "(id, actor_role, entity_type, entity_id, event_type) "
            "VALUES (:id, 'system', 'storybook', 's_x', 'generation_started')"
        ),
        {"id": event_id},
    )
    return event_id


def test_insert_is_allowed(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.begin() as conn:
        event_id = _insert_event(conn)
        stored_type = conn.execute(
            sa.text("SELECT event_type FROM pipeline_event WHERE id = :id"),
            {"id": event_id},
        ).scalar_one()
    assert stored_type == "generation_started"


def test_update_is_rejected(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.begin() as conn:
        event_id = _insert_event(conn)
    with (
        upgraded_engine.connect() as conn,
        pytest.raises(DBAPIError, match="append-only"),
        conn.begin(),
    ):
        conn.execute(
            sa.text("UPDATE pipeline_event SET to_state = 'x' WHERE id = :id"),
            {"id": event_id},
        )


def test_delete_is_rejected(upgraded_engine: sa.engine.Engine) -> None:
    with upgraded_engine.begin() as conn:
        event_id = _insert_event(conn)
    with (
        upgraded_engine.connect() as conn,
        pytest.raises(DBAPIError, match="append-only"),
        conn.begin(),
    ):
        conn.execute(
            sa.text("DELETE FROM pipeline_event WHERE id = :id"), {"id": event_id}
        )


def test_truncate_bypasses_the_trigger(upgraded_engine: sa.engine.Engine) -> None:
    """TRUNCATE is a statement-level op; row triggers do not fire, so teardown works."""
    with upgraded_engine.begin() as conn:
        _insert_event(conn)
    with upgraded_engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE pipeline_event"))
        remaining = conn.execute(
            sa.text("SELECT count(*) FROM pipeline_event")
        ).scalar_one()
    assert remaining == 0


def test_downgrade_removes_table_and_function(
    upgraded_engine: sa.engine.Engine,
) -> None:
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
        fns = {
            r[0]
            for r in conn.execute(
                sa.text("SELECT proname FROM pg_proc WHERE proname = :n"),
                {"n": "pipeline_event_append_only"},
            )
        }
    assert "pipeline_event" not in tables
    assert not fns
    up = run_alembic(PROJECT_ROOT, env, "upgrade", REVISION)
    assert up.returncode == 0, up.stderr
