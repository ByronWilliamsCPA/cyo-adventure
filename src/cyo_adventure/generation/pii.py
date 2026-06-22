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
from dataclasses import dataclass

from cyo_adventure.core.exceptions import ValidationError

__all__ = [
    "PiiContext",
    "assert_prompt_pii_safe",
]

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
    # Screen name tokens with lookaround-anchored matching.
    for name in forbidden.child_names:
        if not name:
            continue
        pattern = _compile_name_pattern(name)
        if pattern.search(prompt):
            msg = "prompt contains a forbidden real-child identifier"
            raise ValidationError(
                msg,
                field="prompt",
                details={"kind": "name"},
            )

    # Screen birthdate strings with substring matching.
    # Date strings are distinctive enough that substring matching is adequate
    # and safer than word-boundary matching for formats with non-word characters.
    prompt_lower = prompt.lower()
    for birthdate in forbidden.birthdates:
        if not birthdate:
            continue
        if birthdate.lower() in prompt_lower:
            msg = "prompt contains a forbidden real-child identifier"
            raise ValidationError(
                msg,
                field="prompt",
                details={"kind": "birthdate"},
            )
