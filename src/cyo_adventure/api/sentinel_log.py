"""Shared strip-and-report helper for personalization sentinels at API egress.

Every API surface that serves story-derived free text routes it through
:func:`strip_and_log` rather than calling ``strip_sentinels`` inline. Two
reasons this is centralized rather than duplicated per router, despite this
package's general tolerance for small per-module private helpers
(``_parse_profile_id`` exists in three routers, ``_book_title`` in two):

1. The redaction rule below is a *security* invariant, not a convenience. A
   sentinel's inner value may be a child's first name, so it must never reach
   a log sink. Six copies of a PII rule is six places for it to drift; six
   copies of a UUID parser is merely untidy.
2. One event name with an ``at`` dimension keeps "how many sentinel leaks
   happened today" a single log query, and "which surface leaked" a group-by.
   Per-router event names turn the same question into one query per router,
   and silently miss any router added later.

A sentinel reaching this helper always means an upstream invariant already
broke. Sentinels are legal at rest only in a node body and an ending title
(``validator/sentinel_integrity.py``, ``storybook/slotted_surfaces.py``), and
``moderation/pipeline.py`` turns any other placement into a BLOCK verdict at
moderation entry. So this is defense-in-depth: it converts a
would-be-visibly-broken title into clean generic prose, and the warning below
is then the only remaining signal that the invariant broke at all.
"""

from __future__ import annotations

from cyo_adventure.storybook.sentinels import find_sentinels, strip_sentinels
from cyo_adventure.utils.logging import get_logger

_logger = get_logger(__name__)

_EVENT = "api.served_field_sentinel_stripped"


def strip_and_log(
    text: str,
    *,
    at: str,
    storybook_id: str | None = None,
    version: int | None = None,
) -> str:
    """Strip personalization sentinels from a served field, warning on change.

    Args:
        text: The raw field value, which may carry a sentinel.
        at: Dotted ``<surface>.<field>`` location of the call site, e.g.
            ``"library_item.title"``. One dimension rather than two so the
            signature stays inside the project's argument-count limit, and so
            a log query can group by exact site or by ``surface.`` prefix.
        storybook_id: The story id, for the warning log, or None when the
            calling surface is not story-linked (notifications).
        version: The story version, for the warning log, or None when the
            calling surface has no version concept.

    Returns:
        str: ``text`` with every sentinel replaced by its generic value.
    """
    stripped = strip_sentinels(text)
    if stripped != text:
        # #CRITICAL: security: never log the sentinel's inner value, nor the
        # raw or stripped text itself; a personalization value may be a
        # child's first name. Log only non-identifying fields, mirroring the
        # redaction in moderation/pipeline.py's
        # "moderation.entry_sentinel_integrity_violation".
        # #VERIFY: tests/unit/test_sentinel_log.py asserts the emitted event
        # carries only at/storybook_id/version/slot_ids, and that neither the
        # sentinel's value nor the raw text appears anywhere in it.
        _logger.warning(
            _EVENT,
            at=at,
            storybook_id=storybook_id,
            version=version,
            slot_ids=[slot_id for slot_id, _value in find_sentinels(text)],
        )
    return stripped
