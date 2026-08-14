"""Detect spoken lines, including the ones that carry no quotation marks.

Three separate implementations in this repository counted dialogue by looking for
quotation marks, and all three were blind to the convention the catalogue
actually uses. `the-backyard-treasure-map` carries fifteen spoken lines across
eighteen of its sixty-two nodes and every one of them is unquoted::

    Let's try this one, they said.
    Right here! he whispered.
    Almost there, Nina whispered.

Measured by quote marks that book scores ``0.000``, which is what a dialogue-free
book scores. The distinction matters more than it looks: the quality panel's
`dialogue` criterion was judged against exactly this measure, and a criterion
scoring 3.00 against a ruler reading 0.000 was written up as a broken criterion.
One of the two was blind and the deterministic one was never checked.

**What counts as dialogue here.** A quoted span, or a *tagged* one: a clause
adjacent to a speech verb attributed to a speaker. The tag has to be in tag
position, next to a comma, an exclamation or a question mark, or directly after a
pronoun or a name, because a bare speech verb is ordinary narration ("she asked
for help") and counting it would trade one insensitive measure for one that fires
on everything.

**What this deliberately does not do.** It does not attempt free indirect speech
("she wondered whether the tide had turned"), which is a judgment call rather
than a pattern. Anything this cannot see is invisible to every caller, so the
honest framing for a caller is "dialogue this detector recognises", not
"dialogue".
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "dialogue_share",
    "flatten",
    "has_dialogue",
    "sentence_share",
    "spoken_spans",
    "strip_dialogue",
    "strip_tagged",
]

# Verbs that attribute speech to a speaker. Restricted to ones that report an
# utterance: "laughed" and "smiled" are excluded because "she laughed" is an
# action, and admitting them would make almost every narrative sentence dialogue.
_TAGS: Final[str] = (
    "said|says|asked|asks|whispered|whispers|shouted|shouts|called|calls|"
    "replied|replies|answered|answers|gasped|gasps|murmured|murmurs|"
    "muttered|mutters|cried|cries|added|adds|explained|explains|"
    "agreed|agrees|announced|announces|begged|begs|warned|warns|told|tells"
)

_SPEAKER: Final[str] = r"(?:he|she|they|I|we|you|[A-Z][a-z]+)"

_DOUBLE_QUOTED: Final[re.Pattern[str]] = re.compile(r'"[^"]*"')
_CURLY_QUOTED: Final[re.Pattern[str]] = re.compile("“[^”]*”")

# "Let's try this one, they said." / "Right here! he whispered."
# The punctuation before the speaker is what marks the preceding clause as the
# utterance rather than as narration.
_TAG_AFTER: Final[re.Pattern[str]] = re.compile(
    rf"[,!?]\s+{_SPEAKER}\s+(?:{_TAGS})\b", re.IGNORECASE
)

# "Theo stopped and whispered. Listen." / "She said, follow me."
# The tag comes first and the utterance follows it.
_TAG_BEFORE: Final[re.Pattern[str]] = re.compile(
    rf"\b{_SPEAKER}\s+(?:{_TAGS})\s*[,:.]", re.IGNORECASE
)

_SENTENCE: Final[re.Pattern[str]] = re.compile(r"[^.!?]+[.!?]*")


def _regions(text: str) -> list[tuple[int, int]]:
    """Return the character spans of *text* that mark a spoken line.

    Every pattern is matched over the WHOLE text, before any sentence split.
    A spoken line routinely ends in "!" or "?", which is a sentence terminator,
    so splitting first cuts through the utterance and separates it from the tag
    that identifies it: "Right here! he whispered." becomes "Right here!" (no
    quote, no tag, reads as narration) and "he whispered." (a tag with nothing
    attributed to it). Both halves are wrong in different directions.

    That bug bit twice. The quoted case halved a book measuring 0.818 to 0.273
    on the first run; the tagged case survived that fix because the tag half
    still matched on its own, so the detector looked like it worked while
    reporting the wrong span and leaving the utterance in the narration for
    every caller that strips.

    Args:
        text: A node body.

    Returns:
        Unmerged spans, one per match, in no particular order. Callers ask only
        whether a sentence overlaps one.
    """
    return [
        m.span()
        for pattern in (_DOUBLE_QUOTED, _CURLY_QUOTED, _TAG_AFTER, _TAG_BEFORE)
        for m in pattern.finditer(text)
    ]


def _sentences(text: str) -> list[tuple[int, int, str]]:
    """Return ``(start, end, sentence)`` for each non-empty sentence of *text*."""
    return [
        (m.start(), m.end(), m.group(0))
        for m in _SENTENCE.finditer(text)
        if m.group(0).strip()
    ]


def _is_spoken(start: int, end: int, regions: list[tuple[int, int]]) -> bool:
    """Return whether the span ``[start, end)`` overlaps any dialogue region."""
    return any(rs < end and start < re_ for rs, re_ in regions)


def _marked(text: str) -> list[tuple[int, int, frozenset[int]]]:
    """Return each sentence of *text* as ``(start, end, overlapping region ids)``.

    The region ids, rather than a bare boolean, are what let :func:`spoken_spans`
    rejoin the halves of one utterance without also gluing two consecutive
    utterances into one: two sentences belong to the same spoken line only when
    the *same* region reaches across both.

    Offsets rather than substrings, so a caller rejoining two halves slices the
    original text instead of concatenating with a separator of its own choosing.
    Joining with a space turns ``"Run now!" she called.`` into ``"Run now! "
    she called.``, which is a detector inventing whitespace inside a quotation.
    """
    regions = _regions(text)
    return [
        (
            start,
            end,
            frozenset(
                i for i, (rs, re_) in enumerate(regions) if rs < end and start < re_
            ),
        )
        for start, end, _ in _sentences(text)
    ]


def _groups(text: str) -> list[tuple[str, bool]]:
    """Return *text* as ``(chunk, is_spoken)`` pairs, one chunk per utterance.

    Args:
        text: A node body.

    Returns:
        Every sentence in order, with the halves of a single spoken line merged
        into one chunk.
    """
    out: list[tuple[int, int, bool]] = []
    previous: frozenset[int] = frozenset()
    for start, end, ids in _marked(text):
        if ids and previous & ids and out:
            out[-1] = (out[-1][0], end, True)
        else:
            out.append((start, end, bool(ids)))
        previous = ids
    return [(text[start:end].strip(), spoken) for start, end, spoken in out]


def spoken_spans(text: str) -> list[str]:
    """Return the spoken lines of *text*, one entry per utterance.

    Args:
        text: A node body.

    Returns:
        Each utterance with its tag, in order. The two halves of a line cut by
        its own "!" or "?" are rejoined, because "Right here!" and "he
        whispered." are one spoken line; reporting them separately would double
        the line count of every book that punctuates dialogue with anything but
        a full stop.
    """
    return [chunk for chunk, spoken in _groups(text) if spoken]


def has_dialogue(text: str) -> bool:
    """Return whether *text* carries any recognised spoken line.

    Args:
        text: A node body.

    Returns:
        ``True`` when at least one sentence is quoted or tagged.
    """
    return bool(spoken_spans(text))


def dialogue_share(bodies: Iterable[str]) -> float:
    """Return the share of bodies carrying at least one spoken line.

    Args:
        bodies: Node bodies.

    Returns:
        The share, ``0.0`` for an empty input. The unit is the body rather than
        the sentence, matching what the previous quote-only implementations
        reported, so a re-measurement moves only because the detector improved.
    """
    items = list(bodies)
    if not items:
        return 0.0
    return sum(1 for body in items if has_dialogue(body)) / len(items)


def sentence_share(text: str) -> float | None:
    """Return the share of *sentences* carrying a spoken line.

    The book-level companion to :func:`dialogue_share`, whose unit is the node
    body. Both units are in use across this repository and they are not
    interchangeable: a book of sixty-two nodes where eighteen carry one line
    each scores 0.29 by body and roughly 0.03 by sentence.

    Args:
        text: Prose, typically every filled body concatenated.

    Returns:
        The share, or ``None`` when *text* holds no sentences, matching the
        ``None``-for-nothing-to-measure convention the callers already use.
    """
    marked = _marked(text)
    if not marked:
        return None
    # Counted per sentence, not per utterance: a line cut in half by its own
    # "!" occupies two of the sentences this denominator counts, so scoring it
    # once would report a rate against a denominator it was not measured over.
    return sum(1 for *_, ids in marked if ids) / len(marked)


def strip_tagged(text: str) -> str:
    """Remove sentences carrying a speech tag, leaving the rest untouched.

    Split out from :func:`strip_dialogue` so a caller that already has its own
    quote handling can add tagged speech to it without losing that handling.
    ``check_prose_craft.py`` is the case: its ``strip_quoted`` distinguishes a
    single-quoted utterance from a possessive, which a general detector should
    not casually replace.

    The whole sentence goes, tag clause included, and so does the other half of
    an utterance cut by its own "!" or "?". The tag itself is narration, so this
    removes a few narrator words along with the utterance; that direction is the
    safe one for a caller exempting dialogue from a false-positive-prone
    detector, and leaving "Right here!" behind while removing "he whispered."
    would be the unsafe one.

    Args:
        text: A node body.

    Returns:
        The text with every tagged sentence removed.
    """
    regions = [
        m.span()
        for pattern in (_TAG_AFTER, _TAG_BEFORE)
        for m in pattern.finditer(text)
    ]
    kept = [
        sentence
        for start, end, sentence in _sentences(text)
        if not _is_spoken(start, end, regions)
    ]
    return " ".join(part.strip() for part in kept).strip()


def strip_dialogue(text: str) -> str:
    """Remove recognised spoken lines, leaving narration.

    Args:
        text: A node body.

    Returns:
        The text with quoted spans and tagged sentences removed, for callers
        normalising a rate against narration words. A told-emotion rate computed
        over text that still contains dialogue counts a character's speech as the
        narrator's telling.
    """
    return strip_tagged(_CURLY_QUOTED.sub(" ", _DOUBLE_QUOTED.sub(" ", text)))


def flatten(text: str, *, tail: str = " That was what happened.") -> str:
    """Rewrite spoken lines as narration, preserving the events they carry.

    Used to seed the ``dialogue_flat`` known-bad. The utterance is kept and its
    attribution removed, so the book loses its dialogue without losing its plot;
    deleting the sentences outright would shorten the book and confound a
    length-sensitive judge criterion with the one under test.

    Args:
        text: A node body.
        tail: Clause appended in place of the removed attribution, so the result
            still reads as a complete narrated sentence.

    Returns:
        The body with every recognised spoken line converted to narration.
    """
    text = _CURLY_QUOTED.sub(lambda m: m.group(0)[1:-1], text)
    text = _DOUBLE_QUOTED.sub(lambda m: m.group(0)[1:-1], text)

    # Grouped by utterance rather than by sentence, for the reason given in
    # `_regions`: `_TAG_AFTER` straddles the "!" that ends the utterance, so a
    # per-sentence pass never matches it and leaves the tag standing. A seed
    # that leaves the defect in place is worse than no seed, because the arm
    # then reads as "the criterion failed to detect it".
    return " ".join(
        part
        for chunk, spoken in _groups(text)
        if (part := _narrate(chunk, tail=tail) if spoken else chunk)
    ).strip()


def _narrate(utterance: str, *, tail: str) -> str:
    """Return one spoken line rewritten as narration.

    Args:
        utterance: A spoken line, tag included, quotes already unwrapped.
        tail: Clause standing in for the removed attribution.

    Returns:
        The utterance with its tag removed and *tail* appended, so the events
        the line carried survive as narrated text.
    """
    stripped = _TAG_BEFORE.sub("", _TAG_AFTER.sub(".", utterance))
    stripped = re.sub(r"\.\s*(?=[.!?])", "", stripped).strip()
    if stripped and not stripped.endswith((".", "!", "?")):
        stripped += "."
    return f"{stripped}{tail}" if stripped else tail.strip()


def report(bodies: Sequence[str]) -> str:
    """Summarise what this detector sees, for a caller printing a measurement.

    Args:
        bodies: Node bodies.

    Returns:
        A one-line summary naming the detector, because a share reported without
        it invites the reading that anything scoring zero has no dialogue.
    """
    lines = sum(len(spoken_spans(body)) for body in bodies)
    carrying = sum(1 for body in bodies if has_dialogue(body))
    return (
        f"{lines} recognised spoken line(s) across {carrying} of {len(bodies)} "
        "bodies (quoted or tagged; free indirect speech is not detected)"
    )
