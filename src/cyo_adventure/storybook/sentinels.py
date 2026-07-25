"""Canonical sentinel format for story personalization (ADR-023, plan section 2).

A sentinel is a machine-recognizable placeholder that survives verbatim
through fill, validation, moderation, approval, and storage, and strips to a
generic word for any non-opted-in reader.

**Canonical shape:** ``{~SLOTID:GenericWord~}``, e.g. ``{~HERO:Explorer~}``.

- ``SLOTID`` is the slot id, matching the existing slot-id shape
  ``[A-Z][A-Z0-9_]*`` (the same grammar as
  :data:`cyo_adventure.storybook.theme_contract.SLOT_ID_PATTERN`).
- ``GenericWord`` is the pinned generic default value. It may contain spaces
  but must not contain ``{ } < > ' ~``.

This shape satisfies four constraints:

1. It never matches ``SLOT_TOKEN_RE``
   (:data:`cyo_adventure.storybook.theme_contract.SLOT_TOKEN_RE`) at any
   offset, because the interior begins with ``~``, which is not
   ``[A-Z]``. ``render_bound_skeleton``'s post-condition requires zero
   ``{SLOT}``-shaped tokens remain in the rendered document, so a sentinel
   must never be mistaken for an unbound token.
2. It contains no ``<<``, ``>>``, or ``'``, so it cannot corrupt a
   ``<<FILL role=... words=... beats='...'>>`` directive.
3. It strips to exactly the inner word via :func:`strip_sentinels`.
4. The slot id is carried inline, so resolution needs no external lookup.

This module is the single source of truth for the sentinel format (plan risk
R9: "two rendering implementations drift"). Later consumers (the slot
machinery, the integrity checker, the frontend resolver) must import
``SENTINEL_RE`` and the helpers below rather than re-deriving the pattern.
"""

from __future__ import annotations

import re

# The slot id grammar, matching the existing `[A-Z][A-Z0-9_]*` shape used by
# `cyo_adventure.storybook.theme_contract.SLOT_ID_PATTERN`. Quoted here
# (rather than imported) to keep this module dependency-light, since later
# consumers (validator, generation, and eventually a frontend resolver) must
# be able to import it without pulling in the theme-contract Pydantic models.
_SLOT_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Characters a sentinel value must never contain. `{`, `}`, and `~` would
# produce an unparseable token; `<`, `>`, and `'` would corrupt a
# `<<FILL role=... words=... beats='...'>>` directive.
_FORBIDDEN_VALUE_CHARS = frozenset("{}<>'~")

# The canonical sentinel pattern. Two capture groups: the slot id and the
# inner generic value. The value character class excludes `{ } < > ' ~`, the
# same charset `wrap` rejects, so every token this module builds is also
# parseable by this same pattern (the `~` exclusion is what makes the `~}`
# terminator unambiguous).
SENTINEL_RE: re.Pattern[str] = re.compile(r"\{~([A-Z][A-Z0-9_]*):([^{}<>'~]+)~\}")


def wrap(slot_id: str, value: str) -> str:
    """Build the canonical sentinel token for a slot id and generic value.

    Args:
        slot_id: The slot id. Must match ``[A-Z][A-Z0-9_]*``.
        value: The pinned generic default value. May contain spaces but must
            not contain any of ``{ } < > ' ~``.

    Returns:
        str: The canonical ``{~SLOTID:GenericWord~}`` sentinel token.

    Raises:
        ValueError: If ``slot_id`` does not match ``[A-Z][A-Z0-9_]*``, or if
            ``value`` contains any of ``{ } < > ' ~``.
    """
    if not _SLOT_ID_RE.match(slot_id):
        msg = f"invalid slot id {slot_id!r}: must match [A-Z][A-Z0-9_]*"
        raise ValueError(msg)
    found = _FORBIDDEN_VALUE_CHARS.intersection(value)
    if found:
        msg = f"invalid sentinel value {value!r}: must not contain {sorted(found)}"
        raise ValueError(msg)
    return "{~" + slot_id + ":" + value + "~}"


def strip_sentinels(text: str) -> str:
    """Replace every sentinel in text with its inner generic value.

    Args:
        text: Text that may contain zero or more sentinel tokens.

    Returns:
        str: ``text`` with every ``SENTINEL_RE`` match replaced by its
            captured inner value. Text with no sentinels is returned
            unchanged.
    """

    def _replace(match: re.Match[str]) -> str:
        return match.group(2)

    return SENTINEL_RE.sub(_replace, text)


def find_sentinels(text: str) -> list[tuple[str, str]]:
    """Find every sentinel in text, in order.

    Args:
        text: Text that may contain zero or more sentinel tokens.

    Returns:
        list[tuple[str, str]]: Every ``(slot_id, value)`` pair found, in the
            order they appear in ``text``. Empty if no sentinels are found.
    """
    return [(match.group(1), match.group(2)) for match in SENTINEL_RE.finditer(text)]
