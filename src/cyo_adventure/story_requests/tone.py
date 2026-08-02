"""Derive a request's tone from screened request text (W2.2, D5/D18).

``story_requests/brief.py`` used to hardcode every request's tone to
``"gentle"`` regardless of what the child asked for (design review finding
2.5). This module derives a tone from the request's own text instead, using
the D18 starting vocabulary ratified in
``docs/planning/design-review-kid-appeal-2026-08-01.md`` section 8, table
P-B:

===================  ====  ====  =====  ======  ======  ====
Tone                 3-5   5-8   8-11   10-13   13-16   16+
===================  ====  ====  =====  ======  ======  ====
gentle                yes   yes   yes    yes     yes     yes
funny                 yes   yes   yes    yes     yes     yes
exciting               yes   yes   yes    yes     yes     yes
mysterious              -    yes   yes    yes     yes     yes
a_little_spooky           -     -   yes    yes     yes     yes
scary                     -     -    -      -     yes     yes
sad (bittersweet)         -     -    -      -     yes     yes
===================  ====  ====  =====  ======  ======  ====

Detection is deterministic keyword/phrase matching over the lowercased
request text, never a model call, so the derivation is auditable and
reproducible. It is intentionally simple and will under-detect nuanced or
unusually-phrased requests; the default (``"gentle"``) is the safe fallback
for that case, per D18/P-B.

The cap ladder (D5's "a requested tone can narrow but never widen a band's
safety envelope")
--------------------------------------------------------------------------
A band that has not "unlocked" a detected tone yet does not simply fall back
to ``"gentle"``: it steps down the ladder to the strongest tone the band
*does* offer, matching the P-B table's own nesting (every band that offers
``scary`` also offers everything above it in the table). Concretely:

* ``scary``           -> ``a_little_spooky`` -> ``mysterious`` -> ``gentle``
* ``sad``              -> ``gentle`` (no intermediate step; "bittersweet" has
  no lesser sibling in the P-B vocabulary)
* ``a_little_spooky``  -> ``mysterious`` -> ``gentle``
* ``mysterious``       -> ``gentle``
* ``gentle`` / ``funny`` / ``exciting`` are available at every band and never
  step down.

So a "scary" request at 8-11 (which offers ``a_little_spooky`` but not
``scary``) resolves to ``a_little_spooky``; the same request at 5-8 (which
offers neither) steps all the way down to ``mysterious`` if the ``mysterious``
keywords also happen to match, otherwise ``gentle``. This is the
implementation plan's worked example (W2.2 accept criteria).

This module never widens anything: it can only pick a band-appropriate tone
*label* for the generation prompt. It has no access to, and does not touch,
the deterministic safety gates (``validator/policy.py`` PL-15/PL-16) that
enforce the band's actual content ceiling; the tone label is guidance to the
generator, exactly as ``brief.py``'s existing G2 ``special_constraints`` line
is documented to be (see that module's docstring).
"""

from __future__ import annotations

from cyo_adventure.storybook.models import AgeBand, age_band_rank

# The D18/P-B starting vocabulary. A plain string (ConceptBrief.tone is a
# free-form ``str`` field, not an enum) so this stays additive: widening the
# vocabulary later (D18's documented future push) needs no schema change.
TONE_VOCABULARY: frozenset[str] = frozenset(
    {
        "gentle",
        "funny",
        "exciting",
        "mysterious",
        "a_little_spooky",
        "scary",
        "sad",
    }
)

DEFAULT_TONE = "gentle"

# Keyword/phrase triggers per tone. Matched as a lowercased substring test
# against the whole request text (not tokenized), so both single words and
# hyphenated/multi-word phrases match with one mechanism.
#
# #ASSUME: data-integrity: this is a deliberately small, hand-picked starting
# list (D18: "expansion is a future push, not v1 scope"), not a claim of
# linguistic completeness. A request phrased outside these words is silently
# gentle-by-default rather than misclassified into a wrong-but-confident tone,
# which is the safer failure mode for a child-facing tone signal.
# #VERIFY: tests/unit/test_tone.py exercises each tone's positive keywords and
# the no-match default.
_TONE_KEYWORDS: dict[str, frozenset[str]] = {
    "scary": frozenset(
        {
            "scary",
            "terrifying",
            "horror",
            "frightening",
            "nightmare",
            "nightmares",
            "dread",
            "petrifying",
            "spine-chilling",
            "bloodcurdling",
        }
    ),
    "sad": frozenset(
        {
            "sad",
            "bittersweet",
            "tearjerker",
            "heartbreaking",
            "melancholy",
            "grief",
            "weepy",
            "cry",
            "make me cry",
        }
    ),
    "a_little_spooky": frozenset(
        {
            "spooky",
            "haunted",
            "haunted house",
            "ghost",
            "ghosts",
            "ghost story",
            "eerie",
            "creepy",
            "goosebumps",
        }
    ),
    "mysterious": frozenset(
        {
            "mysterious",
            "mystery",
            "puzzle",
            "puzzles",
            "riddle",
            "riddles",
            "secret",
            "secrets",
            "clue",
            "clues",
            "whodunit",
            "detective",
        }
    ),
    "funny": frozenset(
        {
            "funny",
            "silly",
            "hilarious",
            "goofy",
            "comedy",
            "joke",
            "jokes",
            "giggle",
            "laugh",
            "laughs",
            "laughing",
        }
    ),
    "exciting": frozenset(
        {
            "exciting",
            "adventure",
            "adventurous",
            "thrilling",
            "action-packed",
            "fast-paced",
            "daring",
            "epic",
            "action",
        }
    ),
    "gentle": frozenset(
        {
            "gentle",
            "cozy",
            "cosy",
            "calm",
            "sweet",
            "soothing",
            "warm",
            "peaceful",
            "bedtime",
        }
    ),
}

# Detection priority: the more specific/intense tones are checked first, so a
# request naming both a mild and an intense cue (e.g. "a funny but a little
# spooky story") resolves to the stronger, more specific signal. Purely a
# tie-break for multi-keyword text; each tone is still only ever selected when
# its own keywords actually match.
_DETECTION_PRIORITY: tuple[str, ...] = (
    "scary",
    "sad",
    "a_little_spooky",
    "mysterious",
    "funny",
    "exciting",
    "gentle",
)

# The cap ladder: for a detected tone whose band floor exceeds the request's
# band, the sequence of successively-weaker fallbacks to try, ending at
# "gentle" (always available). A tone not listed here has no fallback beyond
# itself (it is available at every band, per the P-B table).
_DOWNGRADE_LADDER: dict[str, tuple[str, ...]] = {
    "scary": ("scary", "a_little_spooky", "mysterious", "gentle"),
    "sad": ("sad", "gentle"),
    "a_little_spooky": ("a_little_spooky", "mysterious", "gentle"),
    "mysterious": ("mysterious", "gentle"),
}

# The band rank (age_band_rank, 0=3-5 .. 5=16+) at or above which a tone is
# offered, per the P-B table. A tone absent here (gentle/funny/exciting) is
# offered at every band (floor 0).
_TONE_BAND_FLOOR: dict[str, int] = {
    "mysterious": age_band_rank(AgeBand.BAND_5_8),
    "a_little_spooky": age_band_rank(AgeBand.BAND_8_11),
    "scary": age_band_rank(AgeBand.BAND_13_16),
    "sad": age_band_rank(AgeBand.BAND_13_16),
}


def _detect_tone(request_text: str) -> str:
    """Return the highest-priority tone whose keywords appear in the text.

    Args:
        request_text: The child's raw (already-screened) request text.

    Returns:
        str: A tone from :data:`TONE_VOCABULARY`; :data:`DEFAULT_TONE` when
            no keyword matches.
    """
    lowered = request_text.lower()
    for tone in _DETECTION_PRIORITY:
        if any(keyword in lowered for keyword in _TONE_KEYWORDS[tone]):
            return tone
    return DEFAULT_TONE


def _cap_to_band(tone: str, band_rank: int) -> str:
    """Step a detected tone down the cap ladder until its band offers it.

    Args:
        tone: A tone from :data:`TONE_VOCABULARY`.
        band_rank: The request's band rank (``age_band_rank`` value).

    Returns:
        str: ``tone`` unchanged when the band already offers it; otherwise
            the strongest fallback the band offers, per
            :data:`_DOWNGRADE_LADDER`; :data:`DEFAULT_TONE` in the worst case
            (always offered at every band).
    """
    ladder = _DOWNGRADE_LADDER.get(tone, (tone,))
    for step in ladder:
        if _TONE_BAND_FLOOR.get(step, 0) <= band_rank:
            return step
    return DEFAULT_TONE


def derive_tone(request_text: str, age_band: AgeBand) -> str:
    """Derive a band-capped tone from a request's screened text (D5/D18).

    Args:
        request_text: The child's raw (already-screened) request text.
        age_band: The request's target age band; caps the detected tone so a
            request never resolves to a tone its band does not offer.

    Returns:
        str: A tone from :data:`TONE_VOCABULARY`, always safe for the given
            band. :data:`DEFAULT_TONE` (``"gentle"``) when nothing is
            detected or the detected tone's whole ladder outranks the band
            (unreachable in practice, since ``"gentle"`` is always offered).
    """
    detected = _detect_tone(request_text)
    return _cap_to_band(detected, age_band_rank(age_band))
