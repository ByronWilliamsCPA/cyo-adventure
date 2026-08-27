"""PN-1: a proper noun a reader can meet before the prose introduces it.

The defect this closes
----------------------

``the-cave-of-echoes`` names the companion "Biscuit" in **all 64 of its 64
nodes** and never once says he is a dog. Its theme contract binds
``COMPANION`` to ``"her dog Biscuit"``, so the descriptor existed at fill
time; the fill used the name and dropped the gloss. A child reader met a
proper noun with no antecedent 64 times and asked who that was, which is the
correct reading of the text. The same catalog shows the right shape:
``the-clockwork-menagerie`` opens "On her shoulder rode Tock, her tiny
wind-up mouse", and reports nothing here.

The scope is every proper noun, not only a companion: a pet, a sibling, a
secondary character, or a town all fail the same way and are all caught by
the same question.

Why this is buildable where the definite-noun-phrase rule was not
------------------------------------------------------------------

:mod:`cyo_adventure.validator.continuity` records that the general form of
this check, "for every definite noun phrase, require that every path to it
passed through a node introducing it", measures **3.48 findings per node**
and is unusable: bridging reference (``the ground``, ``the light``) is
ordinary English, and separating a presupposition from an introduction is
entailment.

Proper nouns are a different population, and the difference is decidable
rather than a matter of degree. They are marked by capitalization, they are
enumerable per book (median **6** distinct names across the 31 committed
filled books), and most are declared up front in the contract's
``default_binding``. Calibrated over the same corpus this rule measures
**2.86 findings per 100 nodes** (130 over 4,542), a hundredfold below the wall
the general form hit, at a median of 2 per book, a max of 33 in a 551-node
teen gamebook with a large named cast, and 3 of 31 books clean.

Twelve of those 130 are one book's defect rather than this rule's noise, and
they are worth knowing about because they look like duplicates. Eleven come
from ``the-sunken-temple``, whose fill emitted **zero apostrophes of any
kind** ("Heddas seal", not the possessive it means) where its siblings carry hundreds,
so every possessive reads as a separate name and both ``Hedda`` and
``Heddas`` report. Nothing here tries to reunite them: guessing at an absent
apostrophe would merge genuine plurals, and the book is what is wrong.

That figure is an upper bound, and knowing why matters before anyone reads it
as a defect rate. The measured corpus is the ``out/*.filled.json`` artifacts,
which predate ADR-023 and carry **no sentinels at all**, so no book in it
declares a protagonist and every book reports its own hero. A sentinelized
fill result, which is what the gate actually sees, reports one fewer. The
exemption is deliberately not inferred from frequency instead: "Biscuit"
appears in the start node and in **100%** of ``the-cave-of-echoes``'s nodes,
so any share-based hero rule would erase precisely the defect this rule
exists for.

What counts as an introduction
------------------------------

Four patterns, all contiguous rather than proximity windows:

* **Determiner-anchored pre-modifier**: ``(det|poss) <lowercase>+ NAME``, as
  in "her dog Biscuit" or "a stowaway cat named Pip".
* **Appositive**: ``NAME , (det|poss) <lowercase>+``, as in "Tock, her tiny
  wind-up mouse".
* **Copular**: ``NAME is/was (det|poss) ...``, as in "Biscuit is her dog".
* **Title**: a name preceded by an address term ("Mister Vole", "Marshal
  Hedda") carries its own descriptor.

The determiner anchor is the load-bearing part and is not a stylistic
preference. A first prototype accepted any lowercase word immediately before
a name, which made "calls Biscuit" indistinguishable from "her dog Biscuit"
and reported ``the-cave-of-echoes`` as clean. Requiring the run to close on a
determiner separates a noun phrase from a transitive verb without a
part-of-speech tagger. ``tests/unit/test_naming.py`` pins that case
explicitly; relaxing it silently restores the defect the rule exists for.

Why the check is path-sensitive
-------------------------------

Introducing a name *somewhere* is not enough in a branching book. A gloss on
an optional branch leaves every reader who took the other branch meeting the
name cold. So a name is covered at a node only when some introducing node
**dominates** it, which is exactly
:func:`cyo_adventure.validator.continuity.dominating_nodes`. Reusing that
computation rather than restating it matters: it is an exact fixed point and
handles the cyclic ``loop_and_grow`` hubs a DAG formulation would get wrong.

Exemptions, and why each is principled rather than a noise filter
------------------------------------------------------------------

* **The protagonist.** A point-of-view character is introduced by narrative
  position, not by apposition; no children's book glosses its own hero. The
  hero's name is read from the ``HERO`` sentinel rather than guessed.
* **A self-glossing head noun.** "Windvale Museum", or a bare "the Keep",
  needs no separate gloss when the book also writes that word in lowercase
  somewhere. Derived from the book's own vocabulary, so it needs no hardcoded
  place-name list.
* **An address term standing alone.** "Grandma" is a common noun doing a
  name's job, so a reader who meets it knows exactly who that is. Same
  reasoning as the title pattern, applied to a name that is only the title.
* **Calendar terms, number words and interjections.** "Monday" and "Hooray"
  are capitalized without naming anything.
* **ALL-CAPS tokens.** Signage and shouting are typography, not naming.

**This is a WARNING and never blocks**, on the same terms as CG-4 and CG-6.
Token-level naming is a heuristic and a human makes the real call.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from cyo_adventure.storybook.sentinels import find_sentinels, strip_sentinels
from cyo_adventure.validator.continuity import dominating_nodes
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)

if TYPE_CHECKING:
    from cyo_adventure.storybook.models import Storybook

__all__ = [
    "check_proper_noun_introduction",
    "introduces",
    "proper_noun_phrases",
]

_FILL_MARKER = "<<FILL"

# Named rather than inlined because ruff RUF001 flags an ambiguous unicode
# literal, and a typographic apostrophe is unavoidable here: filled prose
# carries whichever one the provider emitted. Same pattern as
# `utils/sentences.py` and `validator/prose_craft.py`.
_RIGHT_SINGLE = "\u2019"
_APOSTROPHES = ("'", _RIGHT_SINGLE)
# The possessive suffixes to strip, longest first so "'s" wins over "'".
_POSSESSIVES = ("'s", f"{_RIGHT_SINGLE}s", "'", _RIGHT_SINGLE)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\s”\"']+")
_TOKEN = re.compile(rf"[A-Za-z][A-Za-z'{_RIGHT_SINGLE}-]*|[,.;:!?]")
_LOWERCASE_WORD = re.compile(rf"[a-z][a-z'{_RIGHT_SINGLE}-]*")

# The slot ids that name the point-of-view character across the catalog.
_HERO_SLOT_IDS: frozenset[str] = frozenset({"HERO", "PROTAGONIST"})

# Capitalized only by orthography or phrase position; these name nothing.
_NON_NAMING: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "by",
        "for",
        "in",
        "of",
        "on",
        "the",
        "to",
        "with",
        "but",
        "or",
        "if",
        "so",
        "then",
        "when",
        "while",
        "as",
        "from",
        "into",
        "out",
        "up",
        "down",
        "over",
    }
)

_PRONOUNS: frozenset[str] = frozenset(
    {
        "he",
        "she",
        "they",
        "her",
        "his",
        "him",
        "it",
        "its",
        "their",
        "them",
        "we",
        "us",
        "our",
        "you",
        "your",
        "i",
        "me",
        "my",
        "mine",
        "this",
        "that",
        "these",
        "those",
        "who",
        "what",
        "which",
        "there",
        "here",
    }
)

# Openers of a noun phrase. A pre-modifier run must close on one of these,
# which is what stops a transitive verb reading as a descriptor.
_DETERMINERS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "her",
        "his",
        "its",
        "their",
        "my",
        "your",
        "our",
        "one",
        "another",
        "every",
        "each",
    }
)

# An address term is its own descriptor: "Mister Vole" introduces Vole.
_TITLES: frozenset[str] = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "miss",
        "mister",
        "missus",
        "dr",
        "doctor",
        "captain",
        "keeper",
        "king",
        "queen",
        "prince",
        "princess",
        "lord",
        "lady",
        "sir",
        "madam",
        "professor",
        "officer",
        "chief",
        "marshal",
        "aunt",
        "auntie",
        "uncle",
        "grandma",
        "grandpa",
        "granny",
        "nana",
        "mom",
        "mum",
        "mama",
        "dad",
        "papa",
        "cousin",
        "sister",
        "brother",
        "old",
        "young",
        "little",
        "big",
    }
)

# Tokens that break a contiguous noun phrase walking backwards from a name.
_PHRASE_BREAKS: frozenset[str] = frozenset(
    {
        "and",
        "or",
        "but",
        "with",
        "at",
        "by",
        "for",
        "in",
        "of",
        "on",
        "to",
        "from",
        "into",
        "as",
        "then",
        "when",
        "while",
        "if",
        "so",
        "out",
        "up",
        "down",
        "over",
        "near",
        "past",
        "behind",
        "beside",
        "toward",
        "towards",
        "under",
        "above",
        "across",
        "through",
        "around",
        "before",
        "after",
        "is",
        "was",
        "are",
        "were",
        "be",
        "been",
    }
)

_CALENDAR: frozenset[str] = frozenset(
    {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "spring",
        "summer",
        "autumn",
        "fall",
        "winter",
        "christmas",
        "easter",
        "halloween",
    }
)

_NUMBER_WORDS: frozenset[str] = frozenset(
    {
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "first",
        "second",
        "third",
        "north",
        "south",
        "east",
        "west",
    }
)

_INTERJECTIONS: frozenset[str] = frozenset(
    {
        "hooray",
        "thank",
        "thanks",
        "please",
        "hello",
        "goodbye",
        "yes",
        "no",
        "okay",
        "ok",
        "wow",
        "oh",
        "ah",
        "hey",
        "well",
        "now",
        "every",
        "each",
        "move",
        "go",
        "stop",
        "look",
        "come",
        "beside",
        "below",
        "above",
        "behind",
        "never",
        "always",
        "maybe",
        "perhaps",
        "suddenly",
        "tomorrow",
        "yesterday",
        "today",
        "more",
        "less",
    }
)


def _base(token: str) -> str:
    """Strip a possessive suffix so ``Biscuit's`` compares equal to ``Biscuit``.

    Args:
        token: One word token.

    Returns:
        str: The token without a trailing possessive. A name that merely ends
            in "s" is returned intact: ``rstrip`` strips a character SET, so
            it turned "Jess" into "Je", and because the head regex built from
            the short form then matched nothing, the name was skipped rather
            than misreported.
    """
    for suffix in _POSSESSIVES:
        if token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _names_something(token: str) -> bool:
    """Return whether a capitalized token is naming rather than orthographic.

    Args:
        token: One word token, already known to be capitalized.

    Returns:
        bool: ``True`` when the token could name an entity.
    """
    stem = _base(token)
    if len(stem) < 2 or (stem.isupper() and len(stem) > 1):
        return False
    return stem.lower() not in _NON_NAMING | _PRONOUNS


def proper_noun_phrases(text: str) -> tuple[str, ...]:
    """Return the proper-noun phrases *text* names, deduplicated, in order.

    A phrase is a maximal run of consecutive capitalized naming tokens, so a
    multi-word name is one entity rather than one candidate per token. The
    first token of a sentence is dropped from its run: English capitalizes it
    regardless of whether it names anything, so it carries no evidence.

    Args:
        text: Prose to scan. Sentinels are resolved to their generic values
            first, so a personalized name is read as the name it renders as.

    Returns:
        tuple[str, ...]: The distinct phrases, in first-appearance order.
    """
    found: dict[str, None] = {}
    for sentence in _SENTENCE_SPLIT.split(strip_sentinels(text)):
        tokens: list[str] = _TOKEN.findall(sentence)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if not (token[:1].isalpha() and token[:1].isupper()):
                index += 1
                continue
            start = index
            run: list[str] = []
            while (
                index < len(tokens)
                and tokens[index][:1].isalpha()
                and tokens[index][:1].isupper()
            ):
                run.append(tokens[index])
                index += 1
            if start == 0:
                run = run[1:]  # sentence-initial capital is orthography
            kept = [_base(word) for word in run if _names_something(word)]
            if kept:
                found[" ".join(kept)] = None
    return tuple(found)


def _is_title_introduction(tokens: list[str], index: int, phrase: str) -> bool:
    """Return whether an address term precedes the phrase at *index*.

    Args:
        tokens: The sentence's tokens.
        index: Position of the phrase's head token.
        phrase: The full proper-noun phrase being tested.

    Returns:
        bool: ``True`` when a title opens the name.
    """
    parts = set(phrase.split())
    cursor = index - 1
    while (
        cursor >= 0
        and tokens[cursor][:1].isalpha()
        and tokens[cursor][:1].isupper()
        and _base(tokens[cursor]) in parts
    ):
        if _base(tokens[cursor]).lower() in _TITLES:
            return True
        cursor -= 1
    return cursor >= 0 and _base(tokens[cursor]).lower().rstrip(".") in _TITLES


def _has_premodifier_gloss(tokens: list[str], index: int, phrase: str) -> bool:
    """Return whether a determiner-anchored noun phrase precedes the name.

    Walks backwards collecting contiguous lowercase words and requires the run
    to close on a determiner. Without that anchor a transitive verb ("calls
    Biscuit") is shaped exactly like a modifier ("her dog Biscuit"), which is
    the defect this rule exists to catch.

    Args:
        tokens: The sentence's tokens.
        index: Position of the phrase's head token.
        phrase: The full proper-noun phrase being tested.

    Returns:
        bool: ``True`` when a determiner-anchored gloss is present.
    """
    parts = set(phrase.split())
    cursor = index - 1
    while (
        cursor >= 0
        and tokens[cursor][:1].isalpha()
        and tokens[cursor][:1].isupper()
        and _base(tokens[cursor]) in parts
    ):
        cursor -= 1
    collected = 0
    while cursor >= 0 and tokens[cursor][:1].isalpha():
        word = _base(tokens[cursor]).lower()
        if word in _DETERMINERS:
            return collected > 0
        if word in _PHRASE_BREAKS or tokens[cursor][:1].isupper():
            return False
        collected += 1
        cursor -= 1
    return False


def _has_appositive_gloss(tokens: list[str], index: int) -> bool:
    """Return whether a comma-led descriptor follows the name.

    Args:
        tokens: The sentence's tokens.
        index: Position of the phrase's head token.

    Returns:
        bool: ``True`` for the "Tock, her tiny mouse" shape.
    """
    if index + 3 >= len(tokens) or tokens[index + 1] != ",":
        return False
    if _base(tokens[index + 2]).lower() not in _DETERMINERS:
        return False
    following = tokens[index + 3]
    return (
        following[:1].isalpha()
        and not following[:1].isupper()
        and _base(following).lower() not in _PHRASE_BREAKS
    )


def _has_copular_gloss(tokens: list[str], index: int) -> bool:
    """Return whether the name is the subject of a defining copula.

    Args:
        tokens: The sentence's tokens.
        index: Position of the phrase's head token.

    Returns:
        bool: ``True`` for the "Biscuit is her dog" shape.
    """
    if index + 2 >= len(tokens):
        return False
    return (
        _base(tokens[index + 1]).lower() in {"is", "was", "are", "were"}
        and _base(tokens[index + 2]).lower() in _DETERMINERS
    )


def introduces(body: str, phrase: str) -> bool:
    """Return whether *body* introduces *phrase* rather than merely naming it.

    Args:
        body: One node's prose.
        phrase: The proper-noun phrase to look for.

    Returns:
        bool: ``True`` when any occurrence of the phrase carries a gloss.
    """
    head = phrase.rsplit(" ", 1)[-1]
    for sentence in _SENTENCE_SPLIT.split(strip_sentinels(body)):
        tokens: list[str] = _TOKEN.findall(sentence)
        for index, token in enumerate(tokens):
            if _base(token) != head:
                continue
            if (
                _is_title_introduction(tokens, index, phrase)
                or _has_premodifier_gloss(tokens, index, phrase)
                or _has_appositive_gloss(tokens, index)
                or _has_copular_gloss(tokens, index)
            ):
                return True
    return False


def _hero_tokens(story: Storybook) -> frozenset[str]:
    """Return the lowercased words naming the point-of-view character.

    Read from the ``HERO`` sentinel's generic value rather than inferred, so
    the exemption is grounded in what the book declares.

    Args:
        story: The story to inspect.

    Returns:
        frozenset[str]: Lowercased hero name tokens, empty when undeclared.
    """
    tokens: set[str] = set()
    for node in story.nodes:
        for slot_id, value in find_sentinels(node.body):
            if slot_id in _HERO_SLOT_IDS:
                tokens.update(word.lower() for word in value.split())
    return frozenset(tokens)


def _lowercase_vocabulary(bodies: dict[str, str]) -> frozenset[str]:
    """Return every word the book also writes in lowercase.

    Args:
        bodies: Node id to prose.

    Returns:
        frozenset[str]: Lowercased common-noun vocabulary.
    """
    words: set[str] = set()
    for body in bodies.values():
        words.update(
            _base(word)
            for word in cast(
                "list[str]", _LOWERCASE_WORD.findall(strip_sentinels(body))
            )
        )
    return frozenset(words)


def _is_exempt(
    phrase: str, hero_tokens: frozenset[str], vocabulary: frozenset[str]
) -> bool:
    """Return whether a phrase is outside what PN-1 can meaningfully judge.

    The head-noun test is deliberately not restricted to multi-word phrases.
    Restricting it cost 31 spurious findings over the committed corpus, and
    relaxing it is safe on the case that matters: a fill that names a
    character and never writes the common noun in lowercase, which is exactly
    ``the-cave-of-echoes`` and ``Biscuit`` (0 lowercase occurrences in 65
    nodes), still reports.

    Args:
        phrase: The proper-noun phrase.
        hero_tokens: Lowercased words naming the protagonist.
        vocabulary: Words the book also writes in lowercase.

    Returns:
        bool: ``True`` when the phrase needs no gloss.
    """
    words = [word.lower().strip("." + "".join(_APOSTROPHES)) for word in phrase.split()]
    contractions = tuple(f"i{mark}" for mark in _APOSTROPHES)
    if any(word.startswith(contractions) for word in words):
        return True
    if all(word in _CALENDAR | _NUMBER_WORDS | _INTERJECTIONS for word in words):
        return True
    if all(word in _TITLES for word in words):
        return True  # an address term is a common noun doing a name's job
    if any(word in hero_tokens for word in words):
        return True
    return words[-1] in vocabulary


def check_proper_noun_introduction(story: Storybook) -> ValidationReport:
    """PN-1: flag a proper noun a reader can reach before it is introduced.

    Reports once per offending name rather than once per mention, because a
    name is introduced once and an author fixes it in one place. A node still
    carrying a ``<<FILL`` directive is skipped: this rule reads prose, so an
    unfilled skeleton has nothing to say to it.

    Args:
        story: The parsed Storybook to check.

    Returns:
        ValidationReport: WARNING findings, one per un-introduced name.
    """
    report = ValidationReport()
    bodies = {
        node.id: node.body
        for node in story.nodes
        if _FILL_MARKER not in node.body and node.body.strip()
    }
    if not bodies:
        return report

    dominators = dominating_nodes(story)
    hero_tokens = _hero_tokens(story)
    vocabulary = _lowercase_vocabulary(bodies)

    # Collapse phrases sharing a head noun to the bare form. "Marshal Hedda"
    # and "Hedda" select the same mentions and run the same coverage analysis,
    # so reporting both hands an author two rows for one edit; the bare form is
    # kept because that is what a reader meets with nothing attached.
    phrases: dict[str, str] = {}
    for body in bodies.values():
        for phrase in proper_noun_phrases(body):
            head = phrase.rsplit(" ", 1)[-1]
            held = phrases.get(head)
            if held is None or len(phrase.split()) < len(held.split()):
                phrases[head] = phrase

    for phrase in phrases.values():
        if _is_exempt(phrase, hero_tokens, vocabulary):
            continue
        bare = re.escape(phrase.rsplit(" ", 1)[-1])
        head = re.compile(rf"(?<![A-Za-z]){bare}(?![A-Za-z])")
        mentions = {
            node_id
            for node_id, body in bodies.items()
            if node_id in dominators and head.search(strip_sentinels(body))
        }
        if not mentions:
            continue
        introducing = {
            node_id for node_id in mentions if introduces(bodies[node_id], phrase)
        }
        uncovered = sorted(
            node_id
            for node_id in mentions
            if node_id not in introducing
            and not (introducing & dominators.get(node_id, frozenset()))
        )
        if not uncovered:
            continue
        detail = (
            "the story never introduces it"
            if not introducing
            else (
                "it is introduced only on a branch a reader can skip "
                f"({', '.join(sorted(introducing))})"
            )
        )
        report.add(
            ValidationFinding(
                rule_id="PN-1",
                severity=Severity.WARNING,
                story_id=story.id,
                node_id=uncovered[0],
                message=(
                    f"PN-1 naming: '{phrase}' is named at node "
                    f"'{uncovered[0]}' but {detail}, so a reader meets the "
                    f"name with no idea who or what it is ({len(uncovered)} "
                    f"node(s) affected in story '{story.id}'; advisory "
                    f"heuristic, see module docstring)"
                ),
            )
        )
    return report
