"""Residual retired-theme leaks in a parameterized skeleton's own text (A21).

The gap this closes
-------------------

``ThemeContract.legacy_lexicon`` is the retired theme's proper nouns and
distinctive setting terms. Before A21 it was evaluated in exactly one place:
:func:`cyo_adventure.validator.slots.validate_slot_bindings`, against a
*proposed slot value*, to stop a new binding from reintroducing the old
theme's identity. Nothing ever checked the skeleton's **own** text. So a
proper noun that the migration left hardcoded in a beat, an ending title, or a
choice label passed every acceptance check and then survived every re-theme
intact: bind ``SHIP_NAME`` to anything you like and
``the-sky-ship-stowaway`` still ships the ending title "The Cirrus Sails On".

Measured across the catalog when this module was written: **273 leaks in 11 of
45 migrated skeletons**, and every leaked term already owned a slot on its own
contract, so each is a migration miss with a mechanical fix rather than a
design decision.

Why the check is restricted to proper nouns
-------------------------------------------

A ``legacy_lexicon`` legitimately contains generic words: ``the-pale-road``
lists ``salt``, ``the-tricameral-city`` lists ``Roll`` and ``Register``. Those
belong in the lexicon (a *new* binding naming its hero "Salt" would be a real
leak) but they cannot be blocked in the skeleton's own prose, where "salt" is
just a word. A stem-based scan over the whole lexicon reports 1,771 hits, most
of them that kind of false positive, which is not a defect list anybody can
act on.

A proper noun is different in kind: "Tock", "Cirrus", "Bone Field" name the
retired theme and cannot be correct under any new binding. That class is
decidable without judgement, which is what makes it safe to gate CI on. The
generic remainder is left to per-term review and is deliberately not reported
here, so a passing check means "no undecidable leaks", not "no leaks at all".

Matching is case-sensitive, unlike
:func:`cyo_adventure.validator.slots.validate_slot_bindings`, which casefolds
via its ``_normalize``. That is the whole point here rather than an
inconsistency: capitalization *is* the signal that separates the character
"Alder" from an alder tree, and casefolding would destroy the only evidence
this check has.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from cyo_adventure.storybook.slotted_surfaces import iter_slotted_surfaces
from cyo_adventure.storybook.theme_contract import SLOT_TOKEN_RE

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from cyo_adventure.storybook.theme_contract import ThemeContract

__all__ = ["ThemeLeak", "proper_noun_terms", "residual_theme_leaks"]

# Words that are capitalized in a lexicon entry only because of English
# orthography or because they lead a phrase, and so are not evidence that the
# entry names something. "The Quiet" is a proper noun on the strength of
# "Quiet", not of "The".
_NON_NAMING_WORDS: frozenset[str] = frozenset(
    {"a", "an", "and", "at", "by", "for", "in", "of", "on", "the", "to", "with"}
)


class ThemeLeak(NamedTuple):
    """One retired-theme proper noun found in a skeleton's own authored text.

    Attributes:
        term: The offending ``legacy_lexicon`` entry, verbatim.
        kind: Which slotted surface it was found in (``"beats"``, ``"title"``
            or ``"label"``).
        location: The owning node id, or ``"<node_id>/<choice_id>"`` for a
            choice label.
        owning_slot_ids: Slot ids on this contract whose ``default_binding``
            value contains ``term``. Non-empty means the fix is mechanical:
            the term already has a slot and the surface simply was not
            rewritten to reference it. Empty means the migration never
            declared a slot for this piece of the theme, which is the more
            expensive case.
    """

    term: str
    kind: str
    location: str
    owning_slot_ids: tuple[str, ...]


def _names_something(word: str) -> bool:
    """Return whether a word is capitalized in a way that names something.

    Args:
        word: One whitespace-separated word from a lexicon entry.

    Returns:
        bool: ``True`` when the word starts with an uppercase letter and is
            not a non-naming connective (see :data:`_NON_NAMING_WORDS`).
    """
    stripped = word.strip("'\".,;:!?()[]")
    return bool(stripped[:1].isupper()) and stripped.lower() not in _NON_NAMING_WORDS


def proper_noun_terms(legacy_lexicon: Iterable[str]) -> tuple[str, ...]:
    """Return the lexicon entries that name something, in input order.

    Args:
        legacy_lexicon: A contract's ``legacy_lexicon`` entries.

    Returns:
        tuple[str, ...]: The subset containing at least one capitalized,
            naming word. Entries that are entirely lowercase (``"sea cave"``,
            ``"brine"``) are excluded: see this module's docstring for why
            they cannot be gated on.
    """
    return tuple(
        term
        for term in legacy_lexicon
        if any(_names_something(word) for word in term.split())
    )


def _term_pattern(term: str) -> re.Pattern[str]:
    r"""Compile a case-sensitive, boundary-anchored pattern for one term.

    An apostrophe and a hyphen both count as boundaries, so the possessive
    ``"Follow Alder's notes"`` and the compound ``"Cirrus-class airship"`` are
    both hits. That is deliberate and was a corrected mistake: treating them as
    word-interior characters (to stop ``"Gran"`` matching inside a
    hypothetical ``"Gran-Marie"``) silently swallowed four real possessive
    leaks in ``the-mapmakers-island``. A retired character's name is just as
    leaked in the possessive as in the nominative, and the case it was
    protecting cannot arise: a hyphenated name only reaches a skeleton's own
    text if the migration hardcoded it, which is the same defect.

    Lookarounds on ``\w`` rather than ``\b`` so a term that begins or ends
    with a non-word character still anchors correctly.

    Args:
        term: A lexicon entry.

    Returns:
        re.Pattern[str]: The compiled pattern.
    """
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)")


def residual_theme_leaks(
    skeleton: Mapping[str, object], contract: ThemeContract
) -> tuple[ThemeLeak, ...]:
    """Return every retired-theme proper noun left in a skeleton's own text.

    Scans the three slotted surfaces (via
    :func:`cyo_adventure.storybook.slotted_surfaces.iter_slotted_surfaces`, the
    same enumerator the binder and the migration tooling use, so no surface can
    be checked by one pass and missed by another) with ``{SLOT}`` tokens blanked
    out first: a token's own id is machine text, and leaving it in would let a
    slot id like ``{ALDER_CHART}`` register as a hit for the term "Alder".

    Args:
        skeleton: The raw parameterized skeleton mapping.
        contract: The skeleton's theme contract, supplying both the
            ``legacy_lexicon`` to scan for and the ``default_binding`` used to
            attribute each hit to the slot that should have covered it.

    Returns:
        tuple[ThemeLeak, ...]: One entry per (term, surface) hit, in document
            order then lexicon order. Empty when the skeleton carries no
            decidable leak.
    """
    terms = proper_noun_terms(contract.legacy_lexicon)
    if not terms:
        return ()
    patterns = [(term, _term_pattern(term)) for term in terms]
    owners = {
        term: tuple(
            sorted(
                slot_id
                for slot_id, value in contract.default_binding.items()
                if term in value
            )
        )
        for term in terms
    }
    return tuple(
        ThemeLeak(term, surface.kind, surface.location, owners[term])
        for surface in iter_slotted_surfaces(skeleton)
        # A blank keeps the surrounding words apart, so blanking a token can
        # never fuse two words into a spurious match.
        for bare in (SLOT_TOKEN_RE.sub(" ", surface.text),)
        for term, pattern in patterns
        if pattern.search(bare) is not None
    )
