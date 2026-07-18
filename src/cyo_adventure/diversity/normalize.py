"""Tokenization, entity masking, and theme signatures (diversity/normalize.py).

Shared normalization primitives every other ``diversity`` module builds on:
sentence/word splitting, the stopword list, NER-free entity extraction
(brief-declared names plus medial-caps tokens), the single-placeholder entity
mask, and theme-tag normalization for request-time similarity matching
(WS-0 design doc section 2.1; supervisor Adjustment 1).

Pure module: stdlib plus ``cyo_adventure.storybook.models`` /
``cyo_adventure.core.exceptions`` only. Never imports ``db``, ``generation``,
or ``sqlalchemy`` (WS-0 design doc section 1.1 import rule).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.storybook.models import Storybook

# Deliberately crude: only needs to identify sentence-initial vs
# sentence-medial capitalization, not linguistic sentence boundaries
# (WS-0 design doc section 2.1).
_SENTENCE_SPLIT = re.compile(r"[.!?]\s+")

# Numbers and punctuation are dropped; apostrophes and hyphens stay
# word-internal ("kestrel's", "repair-drone").
_WORD_TOKEN = re.compile(r"[A-Za-z][A-Za-z'-]*")

# A brief field value that "looks like a name": one to four Title Case
# tokens filling the ENTIRE field value (not a substring match), so ordinary
# prose fields (which mix case) never match by accident.
_NAME_LIKE = re.compile(r"^[A-Z][A-Za-z'-]*(?:\s[A-Z][A-Za-z'-]*){0,3}$")

# The single placeholder every masked entity collapses to (WS-0 design doc
# section 2.1): "Priya" vs "Theo" must contribute zero distance, so all
# entities -- regardless of identity -- become this one token.
ENTITY_PLACEHOLDER = "<ent>"

# ~120 English function words (articles, pronouns, auxiliaries,
# prepositions, conjunctions). No NLTK; committed here per WS-0 design doc
# section 2.1. "Content tokens" are tokens not in this set after lowercasing
# and entity masking.
STOPWORDS: frozenset[str] = frozenset(
    {
        "i",
        "me",
        "my",
        "myself",
        "we",
        "our",
        "ours",
        "ourselves",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "he",
        "him",
        "his",
        "himself",
        "she",
        "her",
        "hers",
        "herself",
        "it",
        "its",
        "itself",
        "they",
        "them",
        "their",
        "theirs",
        "themselves",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "am",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "a",
        "an",
        "the",
        "and",
        "but",
        "if",
        "or",
        "because",
        "as",
        "until",
        "while",
        "of",
        "at",
        "by",
        "for",
        "with",
        "about",
        "against",
        "between",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "to",
        "from",
        "up",
        "down",
        "in",
        "out",
        "on",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "any",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "s",
        "t",
        "can",
        "will",
        "just",
        "don",
        "should",
        "now",
    }
)

# Curated keyword/synonym map: free-form nouns -> a normalized theme tag
# (supervisor Adjustment 1). Deliberately small and data-driven; extend by
# adding entries, never by changing the matching logic. Only mapped tokens
# survive into a theme_signature, which is the point: it filters premise
# noise down to the thematically informative words, so short paraphrased
# briefs land close together instead of being diluted by unrelated content
# words (see docs/planning/ws0-diversity-metrics-design.md section 10).
_THEME_TAG_MAP: dict[str, str] = {
    "dragon": "dragon",
    "dragons": "dragon",
    "wyvern": "dragon",
    "wyverns": "dragon",
    "dinosaur": "dinosaur",
    "dinosaurs": "dinosaur",
    "dino": "dinosaur",
    "dinos": "dinosaur",
    "fossil": "dinosaur",
    "fossils": "dinosaur",
    "space": "space",
    "spaceship": "space",
    "spaceships": "space",
    "spacecraft": "space",
    "station": "space",
    "orbital": "space",
    "astronaut": "space",
    "astronauts": "space",
    "rocket": "space",
    "rockets": "space",
    "galaxy": "space",
    "space station": "space",
    "ocean": "ocean",
    "sea": "ocean",
    "undersea": "ocean",
    "underwater": "ocean",
    "mermaid": "ocean",
    "mermaids": "ocean",
    "reef": "ocean",
    "forest": "forest",
    "woods": "forest",
    "woodland": "forest",
    "jungle": "forest",
    "pirate": "pirate",
    "pirates": "pirate",
    "treasure": "pirate",
    "buccaneer": "pirate",
    "cave": "cave",
    "caves": "cave",
    "cavern": "cave",
    "caverns": "cave",
    "canyon": "cave",
    "canyons": "cave",
    "fire": "fire",
    "flame": "fire",
    "flames": "fire",
    "ember": "fire",
    "embers": "fire",
    "castle": "castle",
    "kingdom": "castle",
    "knight": "knight",
    "knights": "knight",
    "robot": "robot",
    "robots": "robot",
    "android": "robot",
    "androids": "robot",
    "drone": "robot",
    "drones": "robot",
    "wizard": "magic",
    "wizards": "magic",
    "witch": "magic",
    "witches": "magic",
    "magic": "magic",
    "magical": "magic",
    "spell": "magic",
    "spells": "magic",
    "sorcery": "magic",
}


def split_sentences(text: str) -> list[str]:
    """Split text into crude "sentences" for medial-caps detection.

    Args:
        text: The prose to split.

    Returns:
        list[str]: Text chunks split on ``[.!?]`` followed by whitespace.
            Not linguistic sentences; only sentence-initial vs
            sentence-medial position needs to be identifiable.
    """
    return _SENTENCE_SPLIT.split(text)


def tokenize(text: str) -> list[str]:
    """Extract word tokens from text, preserving original case.

    Args:
        text: The text to tokenize.

    Returns:
        list[str]: Alphabetic tokens (apostrophes/hyphens kept
            word-internal); numbers and punctuation are dropped.
    """
    return _WORD_TOKEN.findall(text)


def content_tokens(tokens: Sequence[str]) -> list[str]:
    """Filter stopwords out of an already-lowercased/masked token list.

    Args:
        tokens: Lowercased tokens, as returned by :func:`mask_tokens`.

    Returns:
        list[str]: Tokens that are not stopwords. The entity placeholder
            (:data:`ENTITY_PLACEHOLDER`) is never a stopword, so it is kept.
    """
    return [token for token in tokens if token not in STOPWORDS]


def _medial_caps_tokens(bodies: Sequence[str]) -> frozenset[str]:
    """Return lowercased tokens capitalized at a sentence-medial position.

    Args:
        bodies: Node prose bodies to scan.

    Returns:
        frozenset[str]: Every distinct lowercased token seen with an
            uppercase first letter at index > 0 within its split
            "sentence", across all given bodies (WS-0 design doc section
            2.1, point 2). Sentence-initial recovery (point 3) needs no
            extra code: masking checks lowercase membership regardless of
            position, so a name found medially elsewhere is masked at
            sentence-initial position too.
    """
    found: set[str] = set()
    for body in bodies:
        for sentence in split_sentences(body):
            words = tokenize(sentence)
            for index, word in enumerate(words):
                if index > 0 and word[:1].isupper():
                    found.add(word.lower())
    return frozenset(found)


def _iter_string_leaves(value: object) -> list[str]:
    """Recursively collect every string leaf from a JSON-like value.

    Args:
        value: A brief mapping, or any nested dict/list/scalar within one.

    Returns:
        list[str]: Every string found at any depth (dict values, list
            items), in traversal order.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        leaves: list[str] = []
        for nested in cast("Mapping[str, object]", value).values():
            leaves.extend(_iter_string_leaves(nested))
        return leaves
    if isinstance(value, list):
        leaves = []
        for nested in cast("list[object]", value):
            leaves.extend(_iter_string_leaves(nested))
        return leaves
    return []


def _brief_declared_entities(brief: Mapping[str, object] | None) -> frozenset[str]:
    """Return name-like tokens declared anywhere in a brief.

    Covers ``protagonist.name`` and ``anchor_context.character_names``
    (WS-0 design doc section 2.1, point 1) via a general walk: any brief
    field whose ENTIRE value is a one-to-four-token Title Case phrase is
    treated as a declared name, so no per-field special-casing is needed.

    Args:
        brief: The theme brief (a ``ConceptBrief`` dump), or None when no
            brief travelled with the fill.

    Returns:
        frozenset[str]: Lowercased name tokens; empty when ``brief`` is
            None or declares no name-like field.
    """
    if brief is None:
        return frozenset()
    names: set[str] = set()
    for text in _iter_string_leaves(brief):
        stripped = text.strip()
        if _NAME_LIKE.match(stripped):
            names.update(token.lower() for token in tokenize(stripped))
    return frozenset(names)


def coerce_storybook(blob: Storybook | Mapping[str, object]) -> Storybook:
    """Validate a raw blob into a Storybook, or pass a Storybook through.

    Args:
        blob: A validated Storybook, or a plain mapping (e.g. a
            ``StorybookVersion.blob`` JSONB row) to validate.

    Returns:
        Storybook: The validated model.

    Raises:
        ValidationError: If ``blob`` is a mapping that fails Storybook
            schema validation. Pure metric functions must not crash on a
            malformed historical row; this is the one boundary that raises
            instead of degrading, so callers can decide how to handle it.
    """
    if isinstance(blob, Storybook):
        return blob
    try:
        return Storybook.model_validate(blob)
    except PydanticValidationError as exc:
        msg = "story blob failed Storybook schema validation"
        raise ValidationError(msg, details={"error": str(exc)}) from exc


def extract_entities(
    story: Storybook | Mapping[str, object],
    brief: Mapping[str, object] | None = None,
) -> frozenset[str]:
    """Return the NER-free entity set for one story (WS-0 design doc 2.1).

    The union of brief-declared entities and medial-caps tokens found in the
    story's own node bodies. Callers comparing two fills union the result of
    calling this once per fill (see :func:`~cyo_adventure.diversity.leaf.
    leaf_distance_profile`).

    Args:
        story: A validated Storybook, or a raw blob to coerce.
        brief: The story's theme brief, if available.

    Returns:
        frozenset[str]: Lowercased entity tokens.
    """
    model = coerce_storybook(story)
    bodies = [node.body for node in model.nodes]
    return _medial_caps_tokens(bodies) | _brief_declared_entities(brief)


def mask_tokens(text: str, entities: frozenset[str]) -> list[str]:
    """Lowercase, tokenize, and mask every entity token to one placeholder.

    Args:
        text: The prose to mask (typically one node body).
        entities: The entity set (from :func:`extract_entities`, usually
            the union over both stories in a comparison).

    Returns:
        list[str]: Lowercased tokens, with every token whose lowercase form
            is in ``entities`` replaced by :data:`ENTITY_PLACEHOLDER`.
    """
    masked: list[str] = []
    for token in tokenize(text):
        lowered = token.lower()
        masked.append(ENTITY_PLACEHOLDER if lowered in entities else lowered)
    return masked


def jaccard_distance(a: frozenset[str], b: frozenset[str]) -> float:
    """Return the Jaccard distance between two token sets.

    Args:
        a: The first set.
        b: The second set.

    Returns:
        float: ``1 - |a & b| / |a | b|``. Both-empty sets are treated as
            identical (distance ``0.0``): two empty node bodies (or two
            fills with no recognizable content) are not "different" (WS-0
            design doc section 2.2).
    """
    union = a | b
    if not union:
        return 0.0
    return 1.0 - len(a & b) / len(union)


def jaccard_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Return the Jaccard similarity between two theme-tag sets.

    Args:
        a: The first tag set.
        b: The second tag set.

    Returns:
        float: ``|a & b| / |a | b|``. Both-empty sets score ``0.0``
            (unrelated), the opposite convention from
            :func:`jaccard_distance`: an empty theme signature means "no
            theme signal recovered" (a degraded/malformed history row per
            WS-0 design doc section 5.4), never "identical theme", so it
            must never register as similar to anything.
    """
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _tag_matches(text: str) -> frozenset[str]:
    """Return normalized theme tags recognized in free text.

    Args:
        text: Free-form text (typically a brief's ``premise``).

    Returns:
        frozenset[str]: Normalized tags for every content unigram or
            bigram that matches :data:`_THEME_TAG_MAP`; unmatched words
            contribute nothing (the noise-filtering step from supervisor
            Adjustment 1).
    """
    content = [token.lower() for token in tokenize(text)]
    content = [token for token in content if token not in STOPWORDS]
    tags: set[str] = set()
    for word in content:
        tag = _THEME_TAG_MAP.get(word)
        if tag is not None:
            tags.add(tag)
    for first, second in pairwise(content):
        tag = _THEME_TAG_MAP.get(f"{first} {second}")
        if tag is not None:
            tags.add(tag)
    return frozenset(tags)


def theme_signature(
    brief: Mapping[str, object] | None,
    metadata_themes: Sequence[str] | None = None,
) -> frozenset[str]:
    """Return a normalized theme-tag signature for request-history matching.

    Unlike :func:`extract_entities`, nouns here are the signal, not noise:
    this maps a brief's free-form premise (and any curated
    ``metadata.themes``) to a small set of normalized tags via
    :data:`_THEME_TAG_MAP` (supervisor Adjustment 1), so paraphrased
    same-theme briefs ("a dragon who lost his fire" vs "dragon story
    please") land close together instead of being diluted by raw noun
    Jaccard over unrelated words.

    Args:
        brief: The theme brief (a ``ConceptBrief``-shaped mapping), or None.
            Only the ``premise`` field is read.
        metadata_themes: Curated theme strings from a story's
            ``metadata.themes``, when available (a fill's own declared
            themes are trusted signal and are kept even when a tag isn't
            in :data:`_THEME_TAG_MAP`, unlike free premise text).

    Returns:
        frozenset[str]: The normalized theme-tag signature; empty when
            neither source yields a recognizable tag.
    """
    tags: set[str] = set()
    premise = brief.get("premise") if brief is not None else None
    if isinstance(premise, str) and premise:
        tags |= _tag_matches(premise)
    for theme in metadata_themes or ():
        if theme:
            lowered = theme.strip().lower()
            tags.add(_THEME_TAG_MAP.get(lowered, lowered))
    return frozenset(tags)
