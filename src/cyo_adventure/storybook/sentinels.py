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
# Used with fullmatch() to ensure exact end-to-end match (no trailing newlines).
_SLOT_ID_RE = re.compile(r"[A-Z][A-Z0-9_]*")

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
        value: The pinned generic default value. Must be non-empty; may contain
            spaces but must not contain any of ``{ } < > ' ~``.

    Returns:
        str: The canonical ``{~SLOTID:GenericWord~}`` sentinel token.

    Raises:
        ValueError: If ``slot_id`` does not match ``[A-Z][A-Z0-9_]*``, if
            ``value`` is empty, or if ``value`` contains any of
            ``{ } < > ' ~``.
    """
    if not _SLOT_ID_RE.fullmatch(slot_id):
        msg = f"invalid slot id {slot_id!r}: must match [A-Z][A-Z0-9_]*"
        raise ValueError(msg)
    if not value:
        msg = "invalid sentinel value: must not be empty"
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


def _closer_end(text: str, start: int) -> int | None:
    """Resolve the end of a candidate attempt's closer, from `start` onward.

    The search is bounded by the next ``{~`` opener (if any), so an
    unterminated attempt never swallows a later, independent one.

    A well-formed ``~}`` terminator is preferred wherever it is found in
    range, even when an ordinary brace pair (not itself an ``{~``/``~}``
    marker) appears earlier in that range: that embedded brace is tolerated
    as part of a forged value, not treated as ending the span (this is what
    closes the brace-embedded-forgery blind spot in the previous, non-nested
    brace-scan design). Only when no ``~}`` exists in range does a bare
    ``}`` serve as the closer instead, marking a missing-closing-tilde near
    miss (e.g. ``{~HERO:Explorer}``).

    Args:
        text: The full text being scanned.
        start: The index immediately after the opening ``{~``.

    Returns:
        The exclusive end index of the closer, or ``None`` if neither a
        ``~}`` nor a bare ``}`` exists before the next opener or the end of
        text (the ``{`` is then ordinary prose, not an attempt).
    """
    next_opener = text.find("{~", start)
    boundary = next_opener if next_opener != -1 else len(text)
    tilde_close = text.find("~}", start, boundary)
    if tilde_close != -1:
        return tilde_close + 2
    bare_close = text.find("}", start, boundary)
    if bare_close != -1:
        return bare_close + 1
    return None


def find_malformed_sentinels(text: str) -> list[str]:
    """Find every sentinel-shaped-but-malformed substring in text.

    This is the canonical near-miss detector (plan risk R9: keep all
    sentinel-format regex knowledge in this module); callers such as
    `cyo_adventure.validator.sentinel_integrity` must import this rather
    than write their own near-miss grammar.

    **Grammar.** A near miss is anchored on the two sentinel-distinctive
    markers, the opener ``{~`` and the closer ``~}``, rather than on generic
    non-nested ``{...}`` brace spans (the previous design): a plain
    templating brace with no tilde involved (``{blank}``) or a tilde-less
    ``{SLOT}`` theme token is never a sentinel attempt and is never
    reported, since neither marker is present.

    Scanning left to right:

    - An ``{~`` opens a candidate attempt. Its closer is resolved by
      `_closer_end`: the next ``~}`` before the next opener or end of text,
      tolerating any embedded brace pair along the way (so a forged value
      that itself embeds a literal brace, e.g. ``{~HERO:El{evated}~}``, is
      still captured as one whole span, rather than being cut short at the
      inner ``{``); or, when no ``~}`` exists in range, the nearest bare
      ``}`` (a missing-closing-tilde near miss, e.g. ``{~HERO:Explorer}``).
      When neither closer exists, the ``{`` is ordinary prose and scanning
      resumes at the next character.
    - A ``~}`` with no ``{~`` opener already claiming it is paired with the
      nearest preceding, not-yet-claimed ``{`` (a missing-opening-tilde near
      miss, e.g. ``{HERO:Explorer~}``). When no such ``{`` exists, the ``~``
      is ordinary prose.

    Every resolved candidate span is then tested against
    ``SENTINEL_RE.fullmatch``; it is reported only when that full match
    fails. This also covers whitespace inside the braces
    (``{~ HERO:Explorer~}``, ``{~HERO : Explorer~}``), a lowercase or
    otherwise malformed slot id (``{~hero:Explorer~}``), and a value
    containing a forbidden character or empty (``{~HERO:~}``).

    Args:
        text: Text that may contain zero or more sentinel-shaped substrings.

    Returns:
        list[str]: Every malformed near-miss substring found, in the order
            they appear in `text`. Empty if none are found.
    """
    hits: list[str] = []
    index = 0
    floor = 0
    length = len(text)
    while index < length:
        if text.startswith("{~", index):
            span_end = _closer_end(text, index + 2)
            if span_end is None:
                index += 1
                continue
            span = text[index:span_end]
            if not SENTINEL_RE.fullmatch(span):
                hits.append(span)
            index = span_end
            floor = index
        elif text.startswith("~}", index):
            open_index = text.rfind("{", floor, index)
            if open_index == -1:
                index += 1
                continue
            hits.append(text[open_index : index + 2])
            index += 2
            floor = index
        else:
            index += 1
    return hits
