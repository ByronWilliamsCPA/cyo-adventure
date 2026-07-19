r"""PII egress guard for the CYO Adventure generation pipeline.

This module provides the sole chokepoint that prevents real-child identifying
data from reaching an external LLM provider. It must be called on EVERY
assembled prompt before any provider completion call.

Screening scope
---------------
The guard runs two independent checks, both unconditional on every call:

1. **Registered-identifier matching**: prompts are screened against the
   FAMILY'S real-child display names, supplied via ``PiiContext``. These
   values come from authenticated ``child_profile`` rows, not from concept
   brief fields. ``child_profile`` has no birthdate column (the app collects
   only a coarse age band, by design, per the data-minimization posture in
   ``docs/planning/privacy-model.md``), so there is no birthdate-matching
   check here: one existed in an earlier version of this guard but every
   caller could only ever pass an empty set, which is dead code that implies
   coverage the guard doesn't have. If exact birthdates are ever collected,
   add the check back deliberately rather than resurrecting unused code.
2. **Pattern-based content screening**: prompts are additionally screened for
   email addresses, phone numbers, and street-address-shaped text,
   independent of any registered family data. This catches identifying
   content a guardian or child free-typed into an open-ended field (e.g. a
   story premise) that the registered-identifier check cannot know about,
   such as a sibling's contact details, a home address, or a friend's phone
   number. Coverage note: general free-text PII detection can never be
   complete; this is defense-in-depth on top of, not a replacement for, the
   product-level policy that guardians and children are told not to include
   such details in a story request.

The ``protagonist.name`` in a ``ConceptBrief`` is a FICTIONAL character name
chosen by the guardian for the story and is NOT screened by the
registered-identifier check (check 1 above). Screening it there would be
incorrect because the character name is intentionally included in generation
prompts as story content, and it does not identify a real child. It IS still
subject to the pattern-based check (check 2), like every other part of the
prompt, since an email/phone/address pattern is never legitimate story
content regardless of which field it appears in.

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

Pattern-based matching (email, phone, street address) uses fixed regexes with
no configuration input, so there is no evasion surface analogous to the
name lookup table; NFKC folding is still applied first so a
full-width or ligature-obfuscated pattern is still caught. The street-address
pattern requires a leading house number and a recognized street-suffix word
(e.g. "123 Oak Street") to keep the false-positive rate low; a bare number or
a bare capitalized word is deliberately not enough to match, since both are
common in ordinary story prose.

Exception safety
----------------
The raised ``ValidationError`` message names the KIND of PII that was found
(name, email, phone, or address) but NEVER includes the actual value. This
prevents the secret from appearing in log output, Sentry breadcrumbs, or
exception chains.
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

    Populated from the authenticated family's child profiles (real display
    names), NOT from the concept brief (whose protagonist name is a fictional
    character chosen by the guardian).

    Attributes:
        child_names: Real child display names in the family account.
    """

    child_names: frozenset[str]


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


# ---------------------------------------------------------------------------
# Pattern-based content screening (email, phone, street address).
#
# Unlike name matching, these patterns are fixed and not sourced
# from PiiContext: they catch identifying content a guardian or child typed
# into a free-text field (e.g. ConceptBrief.premise) that the
# registered-identifier check cannot know about in advance, such as a
# sibling's contact details or a home address. See the module docstring for
# the false-positive tradeoff each pattern makes.
# ---------------------------------------------------------------------------

# Standard email local-part/domain shape. Deliberately permissive on the
# local part (RFC 5322 allows more punctuation than most real addresses use)
# since under-matching here means real PII slips through, which is the
# costlier failure mode for this guard.
_EMAIL_PATTERN = re.compile(
    r"(?<!\w)[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?!\w)"
)

# US-shaped phone numbers: optional +1/1 country code, optional parens around
# the area code, and 3-3-4 digit grouping with -, ., or space separators.
# Anchored on both sides so it does not fire inside a longer digit run (e.g.
# an ISBN or a UUID fragment), and the digit grouping (3-3-4) does not
# collide with an ISO-format date that might appear in story prose (e.g.
# "2018-04-07" groups as 4-2-2, not 3-3-4).
_PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)"
)

# A house number followed by up to three words and a recognized street-suffix
# word (e.g. "123 Oak Street", "42 W Elm Ave"). Requiring the suffix word
# keeps the false-positive rate low: a bare number or a bare capitalized word
# alone is common in ordinary story prose and is deliberately not enough to
# match on its own.
_STREET_SUFFIXES = (
    "street|st|avenue|ave|boulevard|blvd|road|rd|lane|ln|drive|dr|court|ct|"
    "place|pl|way|circle|cir|terrace|ter|trail|trl|parkway|pkwy|highway|hwy|"
    "square|sq"
)
_ADDRESS_PATTERN = re.compile(
    r"(?<!\w)\d{1,6}\s+(?:[A-Za-z0-9'.-]+\s+){0,3}(?:" + _STREET_SUFFIXES + r")(?!\w)",
    re.IGNORECASE,
)

# Ordered so the first structural match wins; the exact order does not affect
# correctness, only which "kind" is reported when a prompt happens to match
# more than one pattern.
_CONTENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", _EMAIL_PATTERN),
    ("phone", _PHONE_PATTERN),
    ("address", _ADDRESS_PATTERN),
)


def assert_prompt_pii_safe(prompt: str, *, forbidden: PiiContext) -> None:
    """Raise ValidationError if the prompt contains any forbidden or PII-shaped content.

    Checks each name in ``forbidden.child_names`` using lookaround-anchored
    matching (case-insensitive), and (unconditionally, independent of
    ``forbidden``) every prompt for email-, phone-, and
    street-address-shaped text.

    An empty ``child_names`` makes the registered-identifier check a no-op;
    the pattern-based check still runs regardless.

    The raised exception message names the KIND of match (name, email,
    phone, or address) but NEVER echoes the actual PII value, so it is safe
    to propagate to logs and Sentry.

    Args:
        prompt: The fully assembled prompt string about to be sent to a provider.
        forbidden: The PiiContext carrying real-child names for this family.
            Sourced from authenticated child_profile rows.

    Raises:
        ValidationError: If the prompt contains any name token from
            ``forbidden``, or any email/phone/address-shaped text. The
            message identifies the kind of match but omits the value.

    Example:
        >>> ctx = PiiContext(child_names=frozenset({"Emma"}))
        >>> assert_prompt_pii_safe("Write a story about Emma.", forbidden=ctx)
        ValidationError: ...
    """
    # Fold once: NFKC + strip invisibles so evasion by zero-width insertion or
    # compatibility-form spelling cannot slip a name past the guard.
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

    # Screen for email/phone/address-shaped content, unconditional on
    # `forbidden`: this catches identifying content typed into a free-text
    # field (e.g. a story premise) that no registered-identifier list could
    # have anticipated. See the module docstring for the false-positive
    # tradeoff each pattern makes.
    for kind, pattern in _CONTENT_PATTERNS:
        if pattern.search(folded_prompt):
            msg = "prompt contains PII-shaped content"
            raise ValidationError(
                msg,
                field="prompt",
                details={"kind": kind},
            )
