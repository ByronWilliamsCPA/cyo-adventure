r"""PII egress guard for the CYO Adventure generation pipeline.

This module provides the sole chokepoint that prevents real-child identifying
data from reaching an external LLM provider. It must be called on EVERY
assembled prompt before any provider completion call.

Screening scope
---------------
The guard screens prompts against the FAMILY'S real-child names and birthdates,
supplied via ``PiiContext``. These values come from authenticated ``child_profile``
rows, not from concept brief fields.

The ``protagonist.name`` in a ``ConceptBrief`` is a FICTIONAL character name
chosen by the guardian for the story and is NOT screened here. Screening it
would be incorrect because the character name is intentionally included in
generation prompts as story content, and it does not identify a real child.

Normalization (anti-evasion)
----------------------------
Before matching, both the prompt and the forbidden tokens are folded with
:func:`_fold_for_match`: NFKC normalization collapses compatibility forms (so a
full-width or ligature spelling of a name matches its plain form), and
zero-width / format characters (Unicode category ``Cf``, e.g. U+200B ZERO WIDTH
SPACE, U+200D ZERO WIDTH JOINER, U+FEFF) plus non-whitespace control characters
(category ``Cc``, e.g. NUL) are stripped, so a name broken up by an invisible
character (e.g. "Em" + U+200B + "ma") still matches. Folding is applied
symmetrically to both sides so a forbidden value carrying such characters is
handled too.

# #CRITICAL: security: without this fold, the guard is bypassable by inserting a
#            zero-width character inside a real-child name, or by spelling it in
#            an NFKC-equivalent compatibility form, letting the PII reach the
#            provider. #VERIFY: test_pii_guard covers zero-width, ZWJ, BOM,
#            full-width, ligature, and control-character evasions.
# #EDGE: security: confusable HOMOGLYPHS (e.g. Cyrillic U+0415 for Latin "E")
#        are NOT folded here; NFKC does not treat them as equivalent and full
#        UTS-39 confusable folding risks false positives on legitimate
#        multilingual names. #VERIFY: test_name_with_cyrillic_homoglyph_is_not
#        _matched pins this known residual so a future change is a deliberate one.

Matching strategy
-----------------
Name matching uses negative-lookaround anchors so that a name token such as
"Mia" does not match inside a longer word like "amiable", while also handling
names whose edge characters are non-word characters (e.g. "J.R." ends with a
period, which ``\b`` cannot anchor against). Matching is case-insensitive.

Birthdate matching uses plain substring matching. Date strings are distinctive
enough (e.g. "2018-04-07" or "April 7, 2018") that a false positive inside a
plausible story prompt is extremely unlikely. Substring matching is simpler and
more conservative than word-boundary matching for date formats, which can
contain hyphens, slashes, or spelled-out words that interact oddly with
``\b``.

Exception safety
----------------
The raised ``ValidationError`` message names the KIND of PII that was found
(name or birthdate) but NEVER includes the actual value. This prevents the
secret from appearing in log output, Sentry breadcrumbs, or exception chains.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from cyo_adventure.core.exceptions import ValidationError

__all__ = [
    "PiiContext",
    "assert_prompt_pii_safe",
]

# Standard whitespace kept during folding: stripping these could merge otherwise
# separate tokens, so only invisible/format and non-whitespace control chars are
# removed.
_KEPT_WHITESPACE = frozenset("\t\n\r\f\v ")


def _fold_for_match(text: str) -> str:
    """Normalize text so invisible or compatibility-form evasions cannot hide PII.

    Applies NFKC normalization, then strips zero-width / format characters
    (Unicode category ``Cf``) and non-whitespace control characters (category
    ``Cc``). Standard whitespace is preserved so unrelated tokens are not merged.

    Args:
        text: The prompt or forbidden token to fold.

    Returns:
        The folded text, safe to match literally against another folded value.
    """
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(
        ch
        for ch in normalized
        if not (unicodedata.category(ch) in {"Cf", "Cc"} and ch not in _KEPT_WHITESPACE)
    )


# #CRITICAL: security: this is the sole egress guard preventing real child PII
#            from reaching an external LLM provider.
# #VERIFY: orchestrator calls assert_prompt_pii_safe on every prompt before
#          provider.complete(); test_pii_guard proves it raises on a seeded name
#          and that the exception does not echo the value.


@dataclass(frozen=True, slots=True)
class PiiContext:
    """Real-child identifying data that must never reach a provider.

    Populated from the authenticated family's child profiles (real names and
    birthdates), NOT from the concept brief (whose protagonist name is a
    fictional character chosen by the guardian).

    Attributes:
        child_names: Real child display names in the family account.
        birthdates: ISO date strings or rendered date forms to screen for
            (e.g. "2018-04-07", "April 7, 2018").
    """

    child_names: frozenset[str]
    birthdates: frozenset[str]


def _compile_name_pattern(name: str) -> re.Pattern[str]:
    r"""Return a lookaround-anchored regex for ``name``.

    Uses ``(?<!\w)`` and ``(?!\w)`` instead of ``\b`` so that names ending or
    starting with a non-word character (e.g. "J.R." has a trailing period) are
    still matched. ``\b`` only fires at a word/non-word transition, which means
    it cannot anchor against the period at the end of "J.R." -- a PII value
    that would otherwise slip through the guard. Lookaround anchors assert only
    that the character immediately outside the match is NOT a word character (or
    is the start/end of the string), which works regardless of the name's own
    edge characters.

    Args:
        name: The child's display name to screen for.

    Returns:
        A compiled pattern that matches ``name`` as a standalone token,
        case-insensitively, even when the name contains non-word edge characters.
    """
    # (?<!\w) -- no word character immediately before the match
    # (?!\w)  -- no word character immediately after the match
    # re.escape ensures metacharacters in the name are treated as literals.
    return re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.IGNORECASE)


def assert_prompt_pii_safe(prompt: str, *, forbidden: PiiContext) -> None:
    """Raise ValidationError if the prompt contains any forbidden real-child token.

    Checks each name in ``forbidden.child_names`` using lookaround-anchored
    matching (case-insensitive), and each entry in ``forbidden.birthdates``
    using substring matching.

    Empty ``child_names`` and ``birthdates`` are no-ops; no exception is raised.

    The raised exception message names the KIND of match (name or birthdate) but
    NEVER echoes the actual PII value, so it is safe to propagate to logs and
    Sentry.

    Args:
        prompt: The fully assembled prompt string about to be sent to a provider.
        forbidden: The PiiContext carrying real-child names and birthdates for
            this family. Sourced from authenticated child_profile rows.

    Raises:
        ValidationError: If the prompt contains any name token or birthdate
            substring from ``forbidden``. The message identifies the kind of
            match but omits the value.

    Example:
        >>> ctx = PiiContext(
        ...     child_names=frozenset({"Emma"}),
        ...     birthdates=frozenset(),
        ... )
        >>> assert_prompt_pii_safe("Write a story about Emma.", forbidden=ctx)
        ValidationError: ...
    """
    # Fold once: NFKC + strip invisibles so evasion by zero-width insertion or
    # compatibility-form spelling cannot slip a name or date past the guard.
    folded_prompt = _fold_for_match(prompt)

    # Screen name tokens with lookaround-anchored matching.
    for name in forbidden.child_names:
        folded_name = _fold_for_match(name)
        if not folded_name:
            continue
        pattern = _compile_name_pattern(folded_name)
        if pattern.search(folded_prompt):
            msg = "prompt contains a forbidden real-child identifier"
            raise ValidationError(
                msg,
                field="prompt",
                details={"kind": "name"},
            )

    # Screen birthdate strings with substring matching.
    # Date strings are distinctive enough that substring matching is adequate
    # and safer than word-boundary matching for formats with non-word characters.
    folded_prompt_lower = folded_prompt.lower()
    for birthdate in forbidden.birthdates:
        folded_birthdate = _fold_for_match(birthdate)
        if not folded_birthdate:
            continue
        if folded_birthdate.lower() in folded_prompt_lower:
            msg = "prompt contains a forbidden real-child identifier"
            raise ValidationError(
                msg,
                field="prompt",
                details={"kind": "birthdate"},
            )
