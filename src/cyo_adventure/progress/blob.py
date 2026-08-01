"""Pure helpers reading a stored Storybook content blob (W3.1, badge 7).

Deliberately duplicated in shape from ``api/reading_history.py``'s own
``_ending_count``/``_book_title`` (which this module's ``ending_count``
mirrors) and ``api/reading.py``'s ``_version_ending_ids``: this package
depends on no *router* module, per this repo's small-helper-duplication
convention (see ``reading.py::_completion_ending_count``'s own docstring for
the same rationale). The one ``api``-package import it does carry is
``api/sentinel_log.py``'s ``strip_and_log``, which is a shared security
helper (registered in ``tests/unit/test_title_strip_registry.py``), not a
router; duplicating it here would fork a security-relevant behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.api.sentinel_log import strip_and_log
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

_logger = get_logger(__name__)


def ending_valence_map(blob: Mapping[str, object]) -> dict[str, str]:
    """Return ``{ending_id: valence}`` declared in a stored Storybook blob.

    Args:
        blob: The pinned version's stored Storybook content blob.

    Returns:
        dict[str, str]: One entry per ending node, keyed by the ending id
        (``Ending.id``) with the raw valence string (``Valence`` value); an
        ending node malformed enough to be missing its id or valence is
        skipped rather than raising, so one corrupt node cannot break badge 7
        for every other book.
    """
    nodes = blob.get("nodes")
    if not isinstance(nodes, list):
        return {}
    result: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict) or node.get("is_ending") is not True:
            continue
        ending = node.get("ending")
        if not isinstance(ending, dict):
            continue
        ending_id = ending.get("id")
        valence = ending.get("valence")
        if isinstance(ending_id, str) and isinstance(valence, str):
            result[ending_id] = valence
    return result


def ending_count(blob: Mapping[str, object], storybook_id: str, version: int) -> int:
    """Return the pinned version's declared ending count, defaulting to 0.

    Mirrors ``reading_history.py::_ending_count`` exactly.

    # #ASSUME: data integrity: ``metadata.ending_count`` is enforced to equal
    # the story's real ending count at validation time (validator/layer1.py
    # L1-7), so a published version's value is trustworthy. A missing or
    # malformed field degrades to 0 (never raises) so one corrupt row cannot
    # 500 the whole progress projection.
    # #VERIFY: a malformed value is logged, not silently swallowed.

    Args:
        blob: The pinned version's stored Storybook content blob.
        storybook_id: The story id, for the warning log.
        version: The pinned version number, for the warning log.

    Returns:
        int: The declared ending count, or 0 if absent/malformed.
    """
    metadata = blob.get("metadata")
    if not isinstance(metadata, dict):
        return 0
    count = metadata.get("ending_count")
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    if count is not None:
        _logger.warning(
            "progress_malformed_ending_count",
            storybook_id=storybook_id,
            version=version,
        )
    return 0


def book_title(blob: Mapping[str, object], storybook_id: str, version: int) -> str:
    """Return the blob's title, falling back to the storybook id.

    # #CRITICAL: security: a raw personalization sentinel (e.g.
    # {~HERO:Explorer~}) must never reach this kid-facing projection
    # (ADR-023 P3); mirrors reading_history.py::_book_title exactly.
    # #VERIFY: tests/unit/test_progress_blob.py::test_book_title_strips_sentinels.

    Args:
        blob: The pinned version's stored Storybook content blob.
        storybook_id: The story id (title fallback).
        version: The pinned version number, for the sentinel-stripped
            warning log.

    Returns:
        str: ``blob["title"]``, sentinel-stripped, when a non-empty string;
        else ``storybook_id``.
    """
    title = blob.get("title")
    if not (isinstance(title, str) and title):
        return storybook_id
    return strip_and_log(
        title,
        at="progress_book.title",
        storybook_id=storybook_id,
        version=version,
    )
