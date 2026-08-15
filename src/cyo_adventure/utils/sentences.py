"""Shared prose sentence splitter (UW-C255, AL-379).

Four independent copies of the same crude idiom, ``[^.!?]+[.!?]*``, lived in
this repository: ``validator/dialogue.py``, ``diversity/normalize.py``,
``scripts/check_prose_craft.py``, and ``scripts/seed_defects.py``. Three of
them had already produced a defect by cutting where a sentence does not end,
because none of them knew an abbreviation from a full stop. The sharpest
instance: ``validator/choice_grammar.py``'s CG-4 rule borrowed
``diversity.normalize.split_sentences`` (honestly documented there as
"crude, not linguistic sentences", written only to tell sentence-initial
apart from sentence-medial capitalization for a different check) to extract
a node's *opening sentence*. A node opening "Mr. Fez's table was a tiny
hospital for toys." had its opening sentence read as the string ``Mr.``,
which shares no content word with any choice label, so CG-4 fired and no
rewrite could ever satisfy it.

This module is the one splitter a caller in this position should use
instead. It lives under ``utils/`` rather than under ``validator/`` or
``diversity/`` because it is a general text primitive with no domain
dependency (pure ``re`` and ``dataclasses``, exactly like
``storybook/sentinels.py``'s "generic text helper" precedent), and both a
``validator/`` caller and a ``diversity/``-independent ``scripts/`` caller
need it; putting it in either package would make the other import across a
layer boundary that does not otherwise exist (``diversity`` never imports
``validator``).

Not every one of the four original copies was migrated: ``validator/
dialogue.py`` was measured and deliberately left on its own splitter. Its
``sentence_share`` is, by its own docstring, built around the old crude
splitter's habit of counting a bisected utterance as two sentences rather
than one, and that count feeds ``scripts/evaluate_books.py``'s
dialogue-quality-panel comparison; migrating it moved that figure by up to
roughly a third, book to book, with no request to recalibrate the panel
against a new number. ``diversity/normalize.py``'s own ``split_sentences``
was left alone for the same reason in miniature: its only remaining caller
after the ``choice_grammar.py`` fix is its own medial-capitalization scan,
which is a different, already-correct-for-its-purpose job this module does
not need to take over.

**What this handles, deliberately, and only this:**

1. **Common abbreviations** (``Mr.``, ``Mrs.``, ``Ms.``, ``Dr.``, ``St.``,
   ``Jr.``, ``Sr.``, ``vs.``, ``etc.``, ``e.g.``, ``i.e.``) do not end a
   sentence.
2. **Terminal punctuation inside a quoted utterance** does not end a
   sentence when what follows (past any closing quote or bracket) is
   lowercase, which is exactly the shape of a quoted line followed by its
   own speech tag: ``"Run now!" she called.`` is one sentence, not two
   fragments with one unbalanced quote each. This lowercase-follow rule
   applies to a ``!``/``?``/ellipsis run, never to a bare single ``.``: a
   plain full stop followed by a lowercase word that is not a listed
   abbreviation still ends the sentence, matching every splitter this
   module replaces (measured needed, not assumed: an earlier draft applied
   the rule to every terminator and silently merged this corpus's own
   unquoted, untagged dialogue convention, "X. said Pip.", into its
   preceding sentence for `check_prose_craft.py`'s tense count).
3. **A run of terminators** (``...``, ``?!``) is one boundary, not several:
   the run is matched as a single unit, so it is never split internally nor
   read as more than one sentence end.
4. **A mid-sentence ellipsis** followed by a lowercase word is a pause, not
   a full stop: ``"She waited... and then ran."`` stays one sentence,
   while ``"She paused... Then she left."`` (uppercase after the ellipsis)
   is read as two.

**What this deliberately does not do.** It is a heuristic over punctuation
and casing, not a parser: a decimal number ("3.14") and a bare initial
("J. K. Rowling") can still be misread as a sentence boundary, because
nothing in the required case list asks for either and guessing at more
abbreviations invites a different wrong guess. Every caller migrated to this
splitter had its behaviour measured against its previous crude splitter
across the full committed book catalogue before the migration landed (see
``UW-C255``); a caller whose numbers would have moved in a way nobody
decided on was left alone rather than silently changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["SentenceSpan", "sentence_spans", "split_sentences"]

_TERMINATOR_RUN = re.compile(r"[.!?]+")

# The trailing bare word before a single "." that never ends a sentence.
# Case-insensitive; "etc" covers "etc." (a plain trailing word, no embedded
# dot). "e.g." and "i.e." carry two dots of their own and are handled by
# `_dotted_abbreviation_positions` instead, since neither of their two dots
# is a trailing-word boundary the way `_ABBREVIATIONS` expects.
_ABBREVIATIONS: frozenset[str] = frozenset(
    {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "etc"}
)

# Matches the whole two-dot abbreviation so both its dots can be protected
# at once: neither "e.g." nor "i.e." ends a sentence at either dot. The
# first dot (between "e"/"i" and "g"/"e") cannot be recognised by
# `_is_abbreviation`'s trailing-word check, because at that point the text
# before it is just "e" or "i", not yet "e.g"/"i.e".
_DOTTED_ABBREVIATION = re.compile(r"\b(?:e\.g\.|i\.e\.)", re.IGNORECASE)

_TRAILING_WORD = re.compile(r"[A-Za-z]+$")

# Closing quotes/brackets that cling to the sentence they close rather than
# to whatever follows: a straight or curly close-quote, or a closing
# paren/bracket. Curly quotes are written as escapes so the pattern source
# stays ASCII (ruff RUF001 flags ambiguous unicode literals), mirroring
# `check_prose_craft.py`'s own convention for the same characters. The
# straight double quote doubles as an opening mark in ASCII text, which only
# matters for the lookahead below, where skipping past one is harmless
# either way (see module docstring point 2).
_RIGHT_DOUBLE_QUOTE = "\u201d"
_RIGHT_SINGLE_QUOTE = "\u2019"
_CLOSERS = "\"')]" + _RIGHT_DOUBLE_QUOTE + _RIGHT_SINGLE_QUOTE


def _is_abbreviation(prefix: str) -> bool:
    """Return whether *prefix* ends in a bare trailing word a "." must not close.

    Args:
        prefix: The text preceding a candidate single-``.`` terminator.

    Returns:
        bool: True when the trailing word (``Mr``, ``etc``, ...) is a known
            abbreviation. Does not handle ``e.g.``/``i.e.``; see
            :func:`_dotted_abbreviation_positions` for those.
    """
    match = _TRAILING_WORD.search(prefix)
    return match is not None and match.group(0).lower() in _ABBREVIATIONS


def _dotted_abbreviation_positions(text: str) -> frozenset[int]:
    """Return the offset of every "." that belongs to an "e.g." or "i.e.".

    Both dots of ``e.g.``/``i.e.`` need protecting, and the first one (the
    one between "e"/"i" and "g"/"e") cannot be recognised the way
    :func:`_is_abbreviation` recognises everything else: at that offset the
    preceding text is just "e" or "i", not yet the whole abbreviation.
    Matching the abbreviation as one unit up front, rather than reasoning
    about each dot in isolation, protects both at once.

    Args:
        text: The full text being split.

    Returns:
        frozenset[int]: Start offsets of every "." that is part of a
            recognised dotted abbreviation.
    """
    positions: set[int] = set()
    for match in _DOTTED_ABBREVIATION.finditer(text):
        span = match.group(0)
        base = match.start()
        for index, char in enumerate(span):
            if char == ".":
                positions.add(base + index)
    return frozenset(positions)


def _consume_closers(text: str, pos: int) -> int:
    """Return the index past any closing quote/bracket run starting at *pos*.

    Used to grow a confirmed sentence boundary to include punctuation that
    clings to it directly (no intervening whitespace), so ``"Stop!"``
    keeps its closing quote rather than stranding it at the start of the
    next sentence.
    """
    n = len(text)
    while pos < n and text[pos] in _CLOSERS:
        pos += 1
    return pos


def _peek_content_char(text: str, pos: int) -> str | None:
    """Return the first non-closer, non-space character at or after *pos*.

    A decision-only lookahead: it skips whitespace and closer/opener-shaped
    quote and bracket characters to find the character whose case decides
    whether a terminator ends a sentence. It never affects where a sentence
    is actually cut; that is :func:`_consume_closers`'s job.

    Args:
        text: The full text being split.
        pos: The index to start looking from.

    Returns:
        str | None: The first significant character, or None at end of text.
    """
    n = len(text)
    while pos < n and (text[pos] in _CLOSERS or text[pos].isspace()):
        pos += 1
    return text[pos] if pos < n else None


@dataclass(frozen=True, slots=True)
class SentenceSpan:
    """One sentence's raw character span within its source text.

    Attributes:
        start: Start offset (inclusive), contiguous with the previous
            span's ``end`` (or ``0`` for the first span) so that every
            span in a full :func:`sentence_spans` call partitions the
            source text with no gaps -- a caller checking a region's
            overlap against these spans (e.g. dialogue detection) needs
            that contiguity, exactly as the four splitters this replaces
            provided it.
        end: End offset (exclusive).
        text: ``source[start:end]``, unstripped: leading whitespace from
            the previous boundary is part of this span, matching what
            every migrated caller already expected and stripped itself.
    """

    start: int
    end: int
    text: str


def sentence_spans(text: str) -> list[SentenceSpan]:
    """Split *text* into sentence spans over the whole string.

    Args:
        text: Prose to split, typically one node body.

    Returns:
        list[SentenceSpan]: Contiguous spans partitioning ``text``; empty
            only when ``text`` is empty. A trailing chunk with no terminal
            punctuation (or the entire text, if it carries none) is
            returned as a final span.
    """
    spans: list[SentenceSpan] = []
    start = 0
    n = len(text)
    dotted = _dotted_abbreviation_positions(text)
    for match in _TERMINATOR_RUN.finditer(text):
        run_start, run_end = match.span()
        run_text = match.group(0)
        if run_text == "." and (
            run_start in dotted or _is_abbreviation(text[:run_start])
        ):
            continue
        # The lowercase-follow continuation rule (point 2 and point 4 of the
        # module docstring) applies only to a run carrying "!", "?", or more
        # than one character (an ellipsis): a bare single "." is either a
        # recognised abbreviation (handled above) or an ordinary full stop,
        # and treating every other "." followed by a lowercase word as a
        # continuation is too broad. Measured against the full committed
        # book catalogue (UW-C255): this corpus's own dialogue convention
        # sometimes tags a line with a bare, unquoted "X. said Pip." (no
        # comma or "!"/"?" before the tag, so `validator/dialogue.py` does
        # not recognise it as dialogue either), and a single-"." version of
        # this rule read that as one continuing sentence, silently
        # shortening `check_prose_craft.py`'s per-book sentence counts. This
        # narrower rule leaves that case as two sentences, matching every
        # splitter this module replaces, while still merging the "!"/"?"
        # and ellipsis cases the required test list asks for.
        if run_text != ".":
            next_char = _peek_content_char(text, run_end)
            if next_char is not None and next_char.islower():
                continue
        end = _consume_closers(text, run_end)
        spans.append(SentenceSpan(start, end, text[start:end]))
        start = end
    if start < n:
        spans.append(SentenceSpan(start, n, text[start:n]))
    return spans


def split_sentences(text: str) -> list[str]:
    """Return the non-empty, stripped sentences of *text*.

    The convenience form most callers want: a plain list of sentence
    strings, in order, with whitespace-only spans dropped. A caller that
    needs offsets (to test overlap against another regex's spans, the way
    ``validator/dialogue.py``'s internal sentence splitting does, though
    that module keeps its own splitter rather than this one -- see the
    module docstring) should use :func:`sentence_spans` directly instead.

    Args:
        text: Prose to split.

    Returns:
        list[str]: Non-empty sentences, stripped of surrounding whitespace.
    """
    return [span.text.strip() for span in sentence_spans(text) if span.text.strip()]
