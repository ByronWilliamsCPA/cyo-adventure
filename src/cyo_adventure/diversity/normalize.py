"""Tokenization, entity masking, and theme signatures (diversity/normalize.py).

Shared normalization primitives every other ``diversity`` module builds on:
sentence/word splitting, the stopword list, NER-free entity extraction
(brief-declared names plus medial-caps tokens), the single-placeholder entity
mask, and theme-tag normalization for request-time similarity matching
(WS-0 design doc section 2.1; supervisor Adjustment 1).

Pure module: stdlib plus ``cyo_adventure.storybook.models`` /
``cyo_adventure.storybook.sentinels`` / ``cyo_adventure.core.exceptions``
only. Never imports ``db``, ``generation``, or ``sqlalchemy`` (WS-0 design
doc section 1.1 import rule). ``storybook.sentinels`` is admitted under the
same rule: it imports only ``re``, ``typing``, and ``core.exceptions``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.grams import story_text
from cyo_adventure.diversity.similarity_vocab import SIMILARITY_TAG_MAP
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storybook.sentinels import strip_sentinels

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
# #CRITICAL: security: this is the ECHO vocabulary. Its values are read back to
# a child by generation/worker.py::_degraded_set_aside_decisions, which turns
# theme_signature(theme_brief) tags into SET_ASIDE phrases on the kid surface.
# Adding a key here changes what a child is shown, so it is a content-safety
# change, not a similarity tweak. FROZEN: similarity work belongs in
# diversity/similarity_vocab.py (A1).
# #VERIFY: tests/unit/test_similarity_signature.py::
# test_echo_vocabulary_is_unchanged_by_the_similarity_split
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


def storybook_text(book: Storybook, *, include_choice_labels: bool) -> str:
    """Flatten a parsed book's prose, using the blob path's one definition.

    The request-path advisory and the offline tools measure a decoded blob via
    :func:`cyo_adventure.diversity.grams.story_text`; the series validator
    holds parsed models instead. Walking ``book.nodes`` here would be a second
    copy of "what counts as a fill's prose", the drift `AL-563` was written
    about, so the model is dumped and routed through that same function.

    Args:
        book: A parsed storybook.
        include_choice_labels: See
            :func:`cyo_adventure.diversity.grams.story_text`. False for
            fill-quality questions, since a shared skeleton supplies identical
            labels to every fill.

    #EDGE: data-integrity: the returned text is NOT sentinel-stripped, because
    ``story_text`` is the blob path's one definition of a fill's prose and
    ``grams.py`` is a pure stdlib-only module that cannot import
    ``storybook.sentinels``. A sentinel (``{~SLOTID:GenericWord~}``, ADR-023)
    survives verbatim through fill, moderation, approval and storage by
    design, and the grams tokenizer splits it into ``slotid`` plus its generic
    word, so the slot-id half is identical in every book binding that slot.
    Once ADR-023 is flag-ON that inflates SR-10's shared runs between books of
    one chain, in the direction of a FALSE block. It is a no-op today: every
    committed fill measures clean. Stripping here rather than in
    ``story_text`` would give the series validator a different definition of
    a fill's prose from the request-path advisory, which is the `AL-563`
    drift, so this is an owner decision recorded on `UW-C341`, not an
    oversight.
    #VERIFY: tests/unit/test_series.py::
    test_sr10_measures_prose_that_carries_no_sentinels_yet

    Returns:
        The book's body prose, plus choice labels when requested.
    """
    return story_text(
        book.model_dump(mode="python"), include_choice_labels=include_choice_labels
    )


def extract_entities(
    story: Storybook | Mapping[str, object],
    brief: Mapping[str, object] | None = None,
) -> frozenset[str]:
    """Return the NER-free entity set for one story (WS-0 design doc 2.1).

    The union of brief-declared entities and medial-caps tokens found in the
    story's own node bodies and choice labels. Choice labels are leaf text,
    exactly like bodies: the automated fill rewrites them per theme, so a
    label-level noun swap must mask the same way a body-level one does.
    Callers comparing two fills union the result of calling this once per
    fill (see :func:`~cyo_adventure.diversity.leaf.leaf_distance_profile`).

    Args:
        story: A validated Storybook, or a raw blob to coerce.
        brief: The story's theme brief, if available.

    Returns:
        frozenset[str]: Lowercased entity tokens.
    """
    model = coerce_storybook(story)
    bodies = [node.body for node in model.nodes]
    bodies.extend(choice.label for node in model.nodes for choice in node.choices)
    # #ASSUME: data integrity: a personalization sentinel's SLOT ID must never
    # enter the entity set. `{~HERO:Robin~}` tokenizes to `HERO` then `Robin`,
    # and `HERO` is uppercase at a sentence-medial position, so the medial-caps
    # scan would otherwise adopt the slot id as if it were a character name.
    # That is masking a synthetic token instead of a real one, and it displaces
    # a genuine entity from the set. Stripping to the inner value first makes a
    # sentinel-bearing fill produce the same entity set as the same fill with
    # its sentinels already resolved.
    # #VERIFY: tests/unit/test_diversity_sentinels.py, which asserts entity-set
    # and distance equality between a sentinel-bearing pair and its resolved
    # equivalent.
    stripped = [strip_sentinels(body) for body in bodies]
    return _medial_caps_tokens(stripped) | _brief_declared_entities(brief)


def mask_tokens(text: str, entities: frozenset[str]) -> list[str]:
    """Lowercase, tokenize, and mask every entity token to one placeholder.

    Personalization sentinels are resolved to their inner generic word before
    tokenizing, so a stored fill carrying ``{~HERO:Robin~}`` yields the same
    token sequence as the same prose with its sentinels already substituted
    (ADR-023). Without this, each sentinel contributes an extra ``HERO`` token
    that shifts every bigram spanning it.

    Args:
        text: The prose to mask (typically one node body).
        entities: The entity set (from :func:`extract_entities`, usually
            the union over both stories in a comparison).

    Returns:
        list[str]: Lowercased tokens, with every token whose lowercase form
            is in ``entities`` replaced by :data:`ENTITY_PLACEHOLDER`.
    """
    # #ASSUME: data integrity: every diversity consumer that tokenizes prose
    # funnels through here, namely the leaf, lexical and aggregate modules, so
    # this is the single boundary at which sentinels must be resolved. The
    # reading-level validator and both moderation entry points already strip at
    # their own boundaries; diversity was the remaining gate that did not.
    # #VERIFY: tests/unit/test_diversity_sentinels.py.
    masked: list[str] = []
    for token in tokenize(strip_sentinels(text)):
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


def _similarity_tag_matches(text: str) -> frozenset[str]:
    """Return similarity tags recognized in free text.

    Mirrors :func:`_tag_matches` but against the similarity vocabulary, so a
    request premise lands in the same space a story's curated themes do.

    Args:
        text: Free-form text (typically a brief's ``premise``).

    Returns:
        frozenset[str]: Canonical similarity tags for every matching content
            unigram or bigram. Unmatched words contribute nothing.
    """
    content = [token.lower() for token in tokenize(text)]
    content = [token for token in content if token not in STOPWORDS]
    tags: set[str] = set()
    for word in content:
        tag = SIMILARITY_TAG_MAP.get(word)
        if tag is not None:
            tags.add(tag)
    for first, second in pairwise(content):
        tag = SIMILARITY_TAG_MAP.get(f"{first} {second}")
        if tag is not None:
            tags.add(tag)
    return frozenset(tags)


def similarity_signature(
    brief: Mapping[str, object] | None,
    metadata_themes: Sequence[str] | None = None,
) -> frozenset[str]:
    """Return a canonical similarity signature (A1).

    The counterpart to :func:`theme_signature`, which stays the frozen **echo**
    signature. This one exists to be compared, and the difference that matters is
    what happens to a curated theme that the vocabulary does not recognise.

    ``theme_signature`` passes an unrecognised ``metadata.themes`` entry through
    **verbatim** (``normalize.py`` line ~571,
    ``tags.add(_THEME_TAG_MAP.get(lowered, lowered))``). Since no catalog theme is
    an echo-map value, the stored side accumulated 132 raw strings the request
    side could never produce, so the comparison was asymmetric by construction: a
    byte-identical premise scored 0.333 against a ``tau_theme`` of 0.35 and did
    not register as similar. Here an unrecognised theme is **dropped**, which
    keeps both sides inside one closed vocabulary at the cost of losing signal the
    map does not yet cover. That trade is deliberate: an unmappable string cannot
    make two stories measurably similar, it can only make them spuriously
    distinct. Coverage is therefore a measured number, not an assumption
    (``scripts/measure_theme_coverage.py``).

    Args:
        brief: The theme brief (a ``ConceptBrief``-shaped mapping), or None.
            Only the ``premise`` field is read.
        metadata_themes: Curated theme strings from a story's
            ``metadata.themes``, when available.

    Returns:
        frozenset[str]: Canonical similarity tags; empty when neither source
            yields a recognised tag.
    """
    tags: set[str] = set()
    premise = brief.get("premise") if brief is not None else None
    if isinstance(premise, str) and premise:
        tags |= _similarity_tag_matches(premise)
    for theme in metadata_themes or ():
        if not theme:
            continue
        # #ASSUME: data integrity: an unrecognised curated theme is DROPPED, not
        # passed through. Passing it through is exactly the defect this function
        # exists to fix: it put 132 strings on the stored side that the request
        # side could never produce.
        # #VERIFY: tests/unit/test_similarity_signature.py::
        # test_unmapped_curated_theme_is_dropped_not_passed_through
        tag = SIMILARITY_TAG_MAP.get(theme.strip().lower())
        if tag is not None:
            tags.add(tag)
    return frozenset(tags)


def containment(request: frozenset[str], story: frozenset[str]) -> float:
    """Return how much of ``request`` is covered by ``story`` (A2).

    Symmetric Jaccard is the wrong measure for request-versus-story. A request is
    a short statement of intent; a story carries a fuller set, including themes
    the reader never asked for. Jaccard divides by the union, so every theme the
    story has and the request did not mention *lowers* the score, and a story that
    fully delivers the request is punished for also being about other things. That
    is a structural penalty on a match, not a signal.

    Containment asks the question the caller actually has: of what the reader
    asked for, how much does this story already give them?

    Empty-set semantics differ from :func:`jaccard_similarity` on purpose, and
    that function is left untouched: ``normalize.py`` records "an empty signature
    must never register as similar to anything" as a deliberate WS-0 decision, and
    it is relied upon elsewhere. Here an empty *request* is not a claim of
    similarity either, so it returns ``0.0``; there is nothing the reader asked
    for, so nothing can be covered.

    Args:
        request: The request-side signature.
        story: The story-side signature.

    Returns:
        float: ``|request & story| / |request|`` in ``[0, 1]``; ``0.0`` when
            ``request`` is empty.
    """
    if not request:
        return 0.0
    return len(request & story) / len(request)
