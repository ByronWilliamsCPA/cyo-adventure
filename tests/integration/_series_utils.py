"""Shared anchor-seeding helper for series/soft-continuation integration tests.

Underscore-prefixed module name so pytest does not collect it as a test
module (mirrors ``_event_assertions.py``). Both the service-layer series tests
(WS-B PR 3, Task 4) and the series-request endpoint tests (Task 5) need a
published, series-linked anchor storybook to exercise
``story_requests.anchoring.resolve_anchor``/``load_anchor_context``, so the
seeding logic lives here once rather than being duplicated across files.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from cyo_adventure.db.models import Series, Storybook, StorybookVersion

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# ADR-011 band rule: young bands run episodic series that carry no state.
# Mirrors story_requests/service.py::_EPISODIC_BANDS; duplicated here rather
# than imported so this test helper has no dependency on a private constant.
_EPISODIC_BANDS = frozenset({"3-5", "5-8"})

_DEFAULT_ENDING_TITLE = "The End"


async def seed_published_anchor(
    session: AsyncSession,
    *,
    family_id: uuid.UUID,
    approved_by: uuid.UUID,
    age_band: str = "8-11",
    title: str = "Fox Tales",
    book_index: int = 1,
    approved: bool = True,
) -> tuple[Series, Storybook]:
    """Seed a published, series-linked anchor storybook and its series.

    Builds a ``Series`` row plus a ``published`` ``Storybook`` (with
    ``current_published_version`` set and ``series_id``/``book_index``
    populated) and a linked ``StorybookVersion`` whose ``approved_by`` is set
    (unless ``approved`` is ``False``) and whose ``blob`` is a minimal valid
    story dict (a title and one ending node), so
    ``resolve_anchor``/``load_anchor_context`` see a fully valid,
    kid-library-visible anchor (mirrors the published/approved predicate in
    api/library.py).

    Args:
        session: The request session; the caller flushes or commits.
        family_id: The owning family for both the series and the storybook.
        approved_by: The user id stamped as the version's approver, and as
            the series' creator regardless of ``approved``.
        age_band: The series (and anchor) age band.
        title: The series title and the anchor blob's title.
        book_index: The anchor's position in the series (default 1).
        approved: When ``False``, the ``StorybookVersion.approved_by`` column
            is left ``None`` so the anchor is published but its current
            version is not yet approved (default ``True``).

    Returns:
        tuple[Series, Storybook]: The flushed series and its anchor storybook.
    """
    series = Series(
        family_id=family_id,
        title=title,
        age_band=age_band,
        carries_state=age_band not in _EPISODIC_BANDS,
        created_by=approved_by,
    )
    session.add(series)
    await session.flush()

    storybook_id = f"s_{uuid.uuid4().hex[:12]}"
    storybook = Storybook(
        id=storybook_id,
        family_id=family_id,
        status="published",
        current_published_version=1,
        series_id=series.id,
        book_index=book_index,
    )
    session.add(storybook)
    session.add(
        StorybookVersion(
            storybook_id=storybook_id,
            version=1,
            blob={
                "schema_version": "2.0",
                "id": storybook_id,
                "version": 1,
                "title": title,
                "metadata": {"age_band": age_band},
                "variables": [],
                "start_node": "n_end",
                "nodes": [
                    {
                        "id": "n_end",
                        "body": "The adventure concludes happily.",
                        "is_ending": True,
                        "ending": {
                            "id": "e_end",
                            "valence": "positive",
                            "kind": "success",
                            "title": _DEFAULT_ENDING_TITLE,
                        },
                        "choices": [],
                    }
                ],
            },
            approved_by=approved_by if approved else None,
        )
    )
    await session.flush()
    return series, storybook
