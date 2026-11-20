#!/usr/bin/env python
"""Owner-only report over recorded reading trails (privacy-model.md "Reading trail").

Prints, per storybook version: reads started, reads finished, endings reached
with counts, the nodes where unfinished reads stopped, and for every node with
two or more choices the pick count per choice and how often a rewind returned
to it. Children are not named unless ``--by-profile`` is passed, and then only
by profile display name.

    READING_TRAIL_REPORT_DATABASE_URL=... uv run python scripts/report_reading_trail.py
    READING_TRAIL_REPORT_DATABASE_URL=... uv run python scripts/report_reading_trail.py \\
        --by-profile --storybook s_lantern_cave

**The database URL comes only from the environment** (``READING_TRAIL_REPORT_DATABASE_URL``),
never from an argument, so it never lands in shell history or a process listing,
and it is never printed, including in error messages. Any SQLAlchemy Postgres URL
works (``postgresql://``, ``postgresql+psycopg://`` and ``postgresql+asyncpg://``
are all accepted; the script connects through asyncpg, the app's own driver). It needs a
role that can read ``reading_trail`` across families: the table owner, or
``cyo_worker`` (``cyo_api`` sees zero rows without a per-request family context,
by design).

**The output is child data.** It stays on the machine it was produced on: do not
paste it into an issue, a pull request, a chat, a commit, or an LLM prompt
(ADR-030 Decision 6's egress rule applies to this output in full). This is an
admin script, not an API: there is deliberately no route or UI over this data.

Exit codes:
    0 - the report was printed.
    1 - the environment variable is unset or the database could not be read.
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import TYPE_CHECKING

from sqlalchemy import make_url, select
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from cyo_adventure.db.models import ChildProfile, ReadingTrail, StorybookVersion
from cyo_adventure.reading_trail.report import (
    TrailRecord,
    build_report,
    render_report,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncConnection

DATABASE_URL_ENV = "READING_TRAIL_REPORT_DATABASE_URL"

_BANNER = (
    "Reading trail report. Contains children's reading data: keep it on this "
    "machine; do not paste, share, or commit it."
)


def _async_url(raw: str) -> str:
    """Return an asyncpg rendering of any Postgres SQLAlchemy URL.

    Args:
        raw: The URL from the environment.

    Returns:
        str: The same URL with the ``postgresql+asyncpg`` driver.
    """
    url = make_url(raw)
    return url.set(drivername="postgresql+asyncpg").render_as_string(
        hide_password=False
    )


async def _load(
    conn: AsyncConnection, storybook_id: str | None
) -> tuple[list[TrailRecord], dict[tuple[str, int], Mapping[str, object]]]:
    """Read every trail (optionally for one storybook) and the blobs it needs.

    Args:
        conn: An open connection.
        storybook_id: Restrict to one storybook, or ``None`` for all.

    Returns:
        tuple: The trail records and ``(storybook_id, version)`` to blob.
    """
    # #ASSUME: security: the connecting role reads across families; this is an
    # owner-run admin script, and the per-profile label is the display name
    # only (no profile id, family id, or date is ever printed).
    # #VERIFY: tests/integration/test_reading_trail.py::
    # test_report_script_prints_aggregates_without_identifiers.
    query = (
        select(
            ReadingTrail.storybook_id,
            ReadingTrail.version,
            ChildProfile.display_name,
            ReadingTrail.steps,
        )
        .join(ChildProfile, ChildProfile.id == ReadingTrail.child_profile_id)
        .order_by(ReadingTrail.storybook_id, ReadingTrail.version, ReadingTrail.id)
    )
    if storybook_id is not None:
        query = query.where(ReadingTrail.storybook_id == storybook_id)
    records = [
        TrailRecord(
            storybook_id=row.storybook_id,
            version=row.version,
            profile_label=row.display_name,
            steps=row.steps,
        )
        for row in await conn.execute(query)
    ]
    keys = sorted({(record.storybook_id, record.version) for record in records})
    blobs: dict[tuple[str, int], Mapping[str, object]] = {}
    for book, version in keys:
        blob = (
            await conn.execute(
                select(StorybookVersion.blob).where(
                    StorybookVersion.storybook_id == book,
                    StorybookVersion.version == version,
                )
            )
        ).scalar_one_or_none()
        if blob is not None:
            blobs[book, version] = blob
    return records, blobs


async def _load_all(
    raw: str, storybook_id: str | None
) -> tuple[list[TrailRecord], dict[tuple[str, int], Mapping[str, object]]]:
    """Open an engine from the environment URL, load, and dispose."""
    engine = create_async_engine(_async_url(raw))
    try:
        async with engine.connect() as conn:
            return await _load(conn, storybook_id)
    finally:
        await engine.dispose()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the command line (no database URL is ever accepted here)."""
    parser = argparse.ArgumentParser(
        description="Per-book report over recorded reading trails (owner only).",
    )
    parser.add_argument(
        "--by-profile",
        action="store_true",
        help="Add a per-profile started/finished breakdown (display names).",
    )
    parser.add_argument(
        "--storybook",
        metavar="ID",
        default=None,
        help="Report on one storybook id only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print the report.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        int: The process exit code.
    """
    args = _parse_args(argv)
    raw = os.environ.get(DATABASE_URL_ENV, "").strip()
    if not raw:
        sys.stderr.write(f"{DATABASE_URL_ENV} is not set.\n")
        return 1
    # #CRITICAL: security: the URL carries a database password. Every failure
    # below reports the exception CLASS only, never str(exc), because driver
    # errors can echo the DSN, host, or user.
    # #VERIFY: tests/unit/test_reading_trail_report.py::
    # test_bad_url_is_not_echoed.
    try:
        loaded = asyncio.run(_load_all(raw, args.storybook))
    except (ArgumentError, ValueError) as exc:
        sys.stderr.write(
            f"{DATABASE_URL_ENV} is not a usable URL ({type(exc).__name__}).\n"
        )
        return 1
    except (SQLAlchemyError, OSError) as exc:
        sys.stderr.write(f"Could not read reading trails ({type(exc).__name__}).\n")
        return 1
    records, blobs = loaded
    reports = build_report(records, blobs, by_profile=args.by_profile)
    sys.stdout.write(_BANNER + "\n")
    sys.stdout.write(render_report(reports, blobs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
