"""Unit tests for cross-module invariants in cyo_adventure.api.schemas.

These pin drift between response-model type aliases and the DB CHECK
constraints they claim to mirror; the two are independently hand-maintained
and nothing else ties them together.
"""

from __future__ import annotations

from typing import get_args

from cyo_adventure.api.schemas import JobStatusLiteral
from cyo_adventure.db.models import (
    _GENERATION_JOB_STATUS_VALUES,  # pyright: ignore[reportPrivateUsage]
)


def test_job_status_literal_matches_db_constraint() -> None:
    """JobStatusLiteral's values must match the ck_generation_job_status CHECK.

    ``_GENERATION_JOB_STATUS_VALUES`` is a single-quoted, comma-separated SQL
    fragment (e.g. ``"'queued', 'running', ..."``); parse it back into bare
    strings rather than duplicating the list a second time in this test.
    """
    db_values = {
        value.strip().strip("'") for value in _GENERATION_JOB_STATUS_VALUES.split(",")
    }
    literal_values = set(get_args(JobStatusLiteral))
    assert literal_values == db_values, (
        "JobStatusLiteral has drifted from the ck_generation_job_status CHECK "
        f"constraint: literal={literal_values!r} db={db_values!r}"
    )
