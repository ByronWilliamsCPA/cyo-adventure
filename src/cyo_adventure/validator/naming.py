"""PN-1: a proper noun a reader can meet before the prose introduces it.

The defect this closes
----------------------

``the-cave-of-echoes`` names the companion "Biscuit" in **all 65 of its 65
nodes**, 70 times in total, and never once says he is a dog: the word "dog"
does not appear in the book in any case. Its theme contract binds
``COMPANION`` to ``"her dog Biscuit"``, so the descriptor existed at fill
time; the fill used the name and dropped the gloss. A child reader met a
proper noun with no antecedent in every node and asked who that was, which is
the correct reading of the text. The same catalog shows the right shape:
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
enumerable per book (median **5** distinct names across the 31 committed
filled books), and most are declared up front in the contract's
``default_binding``. Calibrated over the same corpus this rule measures
**2.97 findings per 100 nodes** (135 over 4,542), a hundredfold below the wall
the general form hit, at a median of 2 per book, a max of 34 in
``the-harrowstone-keep`` (551 nodes, a teen gamebook with a large named
cast), and 3 of 31 books clean.

Twelve of those 135 are a name reported twice rather than twelve separate
names, and they are worth knowing about because they look like noise. Eleven
come from ``the-sunken-temple``, whose fill emitted **zero apostrophes of any
kind** ("Heddas seal", not the possessive it means), so every possessive
reads as a separate name and both ``Hedda`` and ``Heddas`` report. The
twelfth is ``the-harrowstone-keep``'s ``Redcloak``/``Redcloaks``, which is a
real plural rather than a lost apostrophe. Nothing here tries to reunite
either pair: guessing at an absent apostrophe would merge genuine plurals,
and in the first case the book is what is wrong.

Zero apostrophes is not unique to that book, only consequential there.
``the-teddy-bears-picnic`` is apostrophe-free too, and reports once
(``Owl``) with no doubling at all, because 29 nodes give it no possessive to
lose. Across the 29 artifacts that do write apostrophes the count is small
and varies widely: a median of **31** per book, seven at 100 or more, and
exactly one past 200 (``the-harrowstone-keep``, 345).

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
  **at least twice**. One lowercase use is not evidence: "a rusty gate"
  somewhere in a book does not gloss a dog named Rusty, and the floor of two
  is what separates a book's working vocabulary from an incidental
  collision. It is derived from the book's own prose either way, so it needs
  no hardcoded place-name list.
* **An address term standing alone.** "Grandma" is a common noun doing a
  name's job, so a reader who meets it knows exactly who that is. Same
  reasoning as the title pattern, applied to a name that is only the title.
* **Calendar terms, number words and interjections.** "Monday" and "Hooray"
  are capitalized without naming anything.
* **ALL-CAPS tokens.** Signage and shouting are typography, not naming.

Known boundaries
----------------

* **Choice labels are out of scope.** The scan reads node bodies only, so a
  reader who meets a name for the first time in a choice label ("Follow
  Biscuit into the woods") gets no finding. That is a real gap rather than a
  claim the gap does not matter, and widening the scan to labels would
  re-calibrate every figure above, so it is a separate decision.
  ``test_a_name_met_first_in_a_choice_label_is_out_of_scope`` asserts the
  boundary from both sides so that it moves deliberately or not at all.
* **A story past the scan budget is not checked.** See ``_SCAN_BUDGET``
  below. The skip emits its own finding rather than an empty report, because
  a story nobody checked and a story with nothing to report are otherwise
  the same answer.

**This is a WARNING and never blocks**, on the same terms as CG-4 and CG-6.
Token-level naming is a heuristic and a human makes the real call.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

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
# The last characters any entry of `_POSSESSIVES` can end with, as a
# single cheap pre-test for `_base`. A token ending in a bare "s" passes
# this guard and then matches no suffix, which is the intended answer.
_POSSESSIVE_TAILS = ("s", "'", _RIGHT_SINGLE)

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

# The address terms filled prose abbreviates with a trailing period, held as
# an intersection with `_TITLES` rather than as a parallel list so the two
# can never disagree about what an address term is. Three of the 31 committed
# books write them ("Mr. Fez", "Ms. Flores", "Mrs. Okafor", "Mr. Pell");
# "dr" rides along because it is the same orthography.
_ABBREVIATED_TITLES: frozenset[str] = _TITLES & frozenset({"mr", "mrs", "ms", "dr"})

# A period closing an abbreviated address term is not a sentence boundary.
# Splitting there turned "Her cat Mr. Whiskers purred loudly." into two
# sentences, which dropped "Whiskers" as a sentence-initial capital. The
# costly half was the false positive rather than that miss: a book that
# introduced "Mr. Vole" and later wrote a bare "Vole" reported the name as
# never introduced, where the unabbreviated "Mister Vole" control reported
# nothing. Python requires a fixed-width lookbehind, so the guard is one
# lookbehind per abbreviation rather than one alternation.
_ABBREVIATION_GUARD = "".join(
    rf"(?<!\b{title}\.)" for title in sorted(_ABBREVIATED_TITLES)
)
_SENTENCE_SPLIT = re.compile(
    rf"(?<=[.!?]){_ABBREVIATION_GUARD}[\s”\"']+", re.IGNORECASE
)

# How many lowercase uses it takes for a book's own vocabulary to exempt a
# name as self-glossing. One is not evidence: `the-salt-archive` writes
# "Verrin" capitalized 38 times and lowercase exactly once, in "...what elias
# verrin could set down...", which is the same proper name miscased by the
# fill rather than the common noun the name was built from. Requiring two
# recovers that name while keeping the place names the rule must not report
# ("Astronomy Hall", "Map Room", "Windvale Museum").
_LEXICAL_EXEMPTION_FLOOR = 2

# The upper bound on (surviving names x characters of prose) PN-1 will scan.
# The cost is one full-body search per (name, node) pair, so that product is
# what grows, and it grows without limit on a request path: `api/node_edit.py`
# runs the gate per edit, synchronously, holding an AnyIO worker thread and a
# checked-out AsyncSession for the duration (`api/gate_limits.py`).
#
# Measured 2026-08-28. A synthetic story sized exactly at this budget (50
# names over 20 nodes whose bodies sit at `api/schemas.py`'s 20,000-character
# cap) takes 0.25s, so the budget is a wall-clock ceiling of roughly a quarter
# of a second. It is a ceiling and not a target: the heaviest committed book,
# `the-harrowstone-keep`, pairs 36 surviving names with 217,210 characters
# for a product of 7,819,560, 39% of the budget, and runs in 42.8ms.
_SCAN_BUDGET = 20_000_000

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
    # The tuple test is one call that clears the overwhelming majority of
    # tokens; without it this ran four `endswith` probes per token and, at
    # roughly 71,000 tokens per pass over `the-harrowstone-keep`, was a third
    # of the whole rule's cost.
    if not token.endswith(_POSSESSIVE_TAILS):
        return token
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


def _sentence_tokens(text: str) -> list[list[str]]:
    """Return *text* split into sentences and tokenized, once.

    Every consumer here wants the same two derived forms of a node body, and
    each used to recompute both per phrase it was asked about. Computing them
    once per node is what makes the cost of the rule linear in prose rather
    than in prose times names.

    Args:
        text: Prose with sentinels already resolved.

    Returns:
        list[list[str]]: One token list per sentence, in order.
    """
    sentences: list[list[str]] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        tokens: list[str] = _TOKEN.findall(sentence)
        sentences.append(tokens)
    return sentences


def _phrases_from_sentences(sentences: list[list[str]]) -> tuple[str, ...]:
    """Return the proper-noun phrases a tokenized body names, in order.

    Args:
        sentences: One token list per sentence, as `_sentence_tokens` returns.

    Returns:
        tuple[str, ...]: The distinct phrases, in first-appearance order.
    """
    found: dict[str, None] = {}
    for tokens in sentences:
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
    return _phrases_from_sentences(_sentence_tokens(strip_sentinels(text)))


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
    # `_TOKEN` emits the period of "Mr." as its own token, so the address term
    # sits one further back than the walk above leaves the cursor. Stepping
    # over it is gated on the preceding word actually being an abbreviated
    # title, so a sentence-final period can never be walked through.
    if (
        cursor >= 1
        and tokens[cursor] == "."
        and _base(tokens[cursor - 1]).lower() in _ABBREVIATED_TITLES
    ):
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


def _introduces_in(sentences: list[list[str]], phrase: str) -> bool:
    """Return whether a tokenized body glosses *phrase* rather than naming it.

    Args:
        sentences: One token list per sentence, as `_sentence_tokens` returns.
        phrase: The proper-noun phrase to look for.

    Returns:
        bool: ``True`` when any occurrence of the phrase carries a gloss.
    """
    head = phrase.rsplit(" ", 1)[-1]
    for tokens in sentences:
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


def introduces(body: str, phrase: str) -> bool:
    """Return whether *body* introduces *phrase* rather than merely naming it.

    Args:
        body: One node's prose.
        phrase: The proper-noun phrase to look for.

    Returns:
        bool: ``True`` when any occurrence of the phrase carries a gloss.
    """
    return _introduces_in(_sentence_tokens(strip_sentinels(body)), phrase)


def _hero_tokens(story: Storybook) -> frozenset[str]:
    """Return the lowercased words naming the point-of-view character.

    Read from the ``HERO`` sentinel's generic value rather than inferred, so
    the exemption is grounded in what the book declares.

    Args:
        story: The story to inspect.

    Returns:
        frozenset[str]: Lowercased hero name tokens, empty when undeclared.
    """
    # #ASSUME: data integrity: a book that declares no HERO/PROTAGONIST
    # sentinel gets an empty exemption, so the rule reports the protagonist
    # like any other name. That is not hypothetical: all 31 committed
    # ``out/*.filled.json`` artifacts predate ADR-023 and carry no sentinels
    # at all, so every corpus figure in the module docstring includes one
    # hero finding per book that a sentinelized fill would not produce.
    # #VERIFY: tests/unit/test_naming.py::test_the_protagonist_is_exempt and
    # ::test_a_protagonist_sentinel_names_the_hero pin the declared case;
    # ::test_an_undeclared_protagonist_is_reported pins the undeclared one.
    tokens: set[str] = set()
    for node in story.nodes:
        for slot_id, value in find_sentinels(node.body):
            if slot_id in _HERO_SLOT_IDS:
                tokens.update(word.lower() for word in value.split())
    return frozenset(tokens)


def _lowercase_counts(stripped: dict[str, str]) -> dict[str, int]:
    """Return how often the book writes each word entirely in lowercase.

    Counts rather than membership, because a single lowercase use is as
    likely to be the fill miscasing a proper name as it is to be the common
    noun the name was built from. See `_LEXICAL_EXEMPTION_FLOOR`.

    Args:
        stripped: Node id to prose with sentinels already resolved.

    Returns:
        dict[str, int]: Lowercased word to the number of times it appears.
    """
    counts: Counter[str] = Counter()
    for text in stripped.values():
        words: list[str] = _LOWERCASE_WORD.findall(text)
        counts.update(_base(word) for word in words)
    return counts


def _is_exempt(
    phrase: str, hero_tokens: frozenset[str], vocabulary: dict[str, int]
) -> bool:
    """Return whether a phrase is outside what PN-1 can meaningfully judge.

    The head-noun test is deliberately not restricted to multi-word phrases.
    Restricting it cost 24 spurious findings over the committed corpus, and
    relaxing it is safe on the case that matters: a fill that names a
    character and never writes the common noun in lowercase, which is exactly
    ``the-cave-of-echoes`` and ``Biscuit`` (0 lowercase occurrences in 65
    nodes), still reports.

    Args:
        phrase: The proper-noun phrase.
        hero_tokens: Lowercased words naming the protagonist.
        vocabulary: Lowercased word to how often the book writes it that way.

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
    return vocabulary.get(words[-1], 0) >= _LEXICAL_EXEMPTION_FLOOR


def _is_tail_of(inner: str, outer: str) -> bool:
    """Return whether *inner*'s words are a word-aligned suffix of *outer*.

    Word-aligned so that "Hollow" is not a tail of "Green Hollow"'s *word*
    "Hollow" by accident of spelling: "Marsh Hollow" and "Green Hollow" share
    a head and neither ends the other, which is the case the caller needs.
    No explicit length guard: when *inner* is the longer phrase the slice is
    shorter than it and the comparison is false on length alone, so a guard
    would be a second spelling of the same answer.

    Args:
        inner: The candidate tail phrase.
        outer: The phrase it may end.

    Returns:
        bool: ``True`` when inner ends outer, an equal pair included.
    """
    inner_words = inner.split()
    outer_words = outer.split()
    return outer_words[max(len(outer_words) - len(inner_words), 0) :] == inner_words


def _collapse_by_head(sentences: dict[str, list[list[str]]]) -> list[str]:
    """Return one phrase per entity the book names, in first-appearance order.

    "Marshal Hedda" and a later bare "Hedda" are one entity and one edit, so
    they collapse to the bare form: that is what a reader meets with nothing
    attached. Sharing a head noun is not on its own enough to make two phrases
    one entity, and treating it that way lost real findings. "Old Hollow" and
    "Green Hollow" are two places; collapsing them kept whichever the
    discovery order reached first, so a book that introduced one and not the
    other reported nothing, while the same book written with distinct heads
    ("Hollow" and "Marsh") reported correctly. The test is therefore a suffix
    test: a phrase folds into another only when its words end the other's.

    Args:
        sentences: Node id to that node's tokenized sentences.

    Returns:
        list[str]: One phrase per entity.
    """
    groups: dict[str, list[str]] = {}
    for tokens in sentences.values():
        for phrase in _phrases_from_sentences(tokens):
            held = groups.setdefault(phrase.rsplit(" ", 1)[-1], [])
            for position, other in enumerate(held):
                if _is_tail_of(phrase, other) or _is_tail_of(other, phrase):
                    if len(phrase.split()) < len(other.split()):
                        held[position] = phrase
                    break
            else:
                held.append(phrase)
    return [phrase for held in groups.values() for phrase in held]


def check_proper_noun_introduction(story: Storybook) -> ValidationReport:
    """PN-1: flag a proper noun a reader can reach before it is introduced.

    Reports once per offending name rather than once per mention, because a
    name is introduced once and an author fixes it in one place. A node still
    carrying a ``<<FILL`` directive is skipped: this rule reads prose, so an
    unfilled skeleton has nothing to say to it.

    The work is one full-body regex search per (surviving name, node) pair, so
    its cost is the product of names and prose volume, and `_SCAN_BUDGET`
    bounds that product. A story past the bound is not scanned and says so in
    a finding of its own; it is never dropped quietly.

    Args:
        story: The parsed Storybook to check.

    Returns:
        ValidationReport: WARNING findings, one per un-introduced name, or a
            single WARNING recording that the story was too large to scan.
    """
    # #CRITICAL: timing dependencies: this is synchronous CPU on a request
    # path. `api/node_edit.py` calls the gate per edit, and
    # `api/gate_limits.py` records that such a call holds both an AnyIO
    # worker thread and a checked-out AsyncSession for its whole duration, so
    # an unbounded scan here consumes two pooled resources, not one.
    # `_SCAN_BUDGET` is the bound, and exceeding it reports rather than runs.
    # #VERIFY: tests/unit/test_naming.py::test_a_story_past_the_scan_budget_
    # is_skipped_out_loud asserts the bounded-input path reports and does not
    # scan; ::test_a_story_inside_the_scan_budget_is_scanned pins the
    # boundary from the other side.
    report = ValidationReport()
    bodies = {
        node.id: node.body for node in story.nodes if _FILL_MARKER not in node.body
    }
    if not bodies:
        return report

    # Resolve sentinels and tokenize ONCE per node. Both used to be redone
    # inside `introduces` for every (phrase, node) pair it was asked about:
    # over `the-cave-of-echoes` that was 1,295 tokenizations of 65 bodies to
    # answer 130 questions about 2 surviving names.
    stripped = {node_id: strip_sentinels(body) for node_id, body in bodies.items()}
    sentences = {node_id: _sentence_tokens(text) for node_id, text in stripped.items()}

    hero_tokens = _hero_tokens(story)
    vocabulary = _lowercase_counts(stripped)
    # Exempt first, then bound: a large cast of self-glossing place names
    # costs nothing to discard and must not push a book over the budget.
    candidates = [
        phrase
        for phrase in _collapse_by_head(sentences)
        if not _is_exempt(phrase, hero_tokens, vocabulary)
    ]

    volume = sum(len(text) for text in stripped.values())
    if len(candidates) * volume > _SCAN_BUDGET:
        report.add(
            ValidationFinding(
                rule_id="PN-1",
                severity=Severity.WARNING,
                story_id=story.id,
                message=(
                    f"PN-1 naming: NOT CHECKED. Story {story.id} pairs "
                    f"{len(candidates)} candidate name(s) with {volume} "
                    f"characters of prose, a product of {len(candidates) * volume} "
                    f"over the {_SCAN_BUDGET} scan budget, so PN-1 was skipped "
                    "and this story has not been checked for un-introduced "
                    "names (advisory heuristic, see module docstring)"
                ),
            )
        )
        return report

    dominators = dominating_nodes(story)
    for phrase in candidates:
        bare = phrase.rsplit(" ", 1)[-1]
        head = re.compile(rf"(?<![A-Za-z]){re.escape(bare)}(?![A-Za-z])")
        # A plain substring test first. It cannot change the answer, because
        # the pattern can only match where the bare head occurs literally,
        # and it is what keeps the dominant term cheap: the search below runs
        # once per (name, node) pair, 19,836 of them on
        # `the-harrowstone-keep`, and almost none of those nodes hold the name.
        mentions = {
            node_id
            for node_id, text in stripped.items()
            if node_id in dominators and bare in text and head.search(text)
        }
        introducing = {
            node_id
            for node_id in mentions
            if _introduces_in(sentences[node_id], phrase)
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
