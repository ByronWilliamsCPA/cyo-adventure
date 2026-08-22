"""Flag prose-craft defects the deterministic gate cannot see.

Usage:
    uv run python scripts/check_prose_craft.py <filled.json> [<filled.json>...]
        [--max-unstable-nodes N] [--min-tense-cues N] [--max-node-mix F]
        [--max-moral-tags N] [--ending-tail-sentences N]
        [--max-told-per-1000 F] [--check]

AL-170/UW-C106: all nine books of the model-tier study cleared fill
integrity, the full validator gate, safety, topology, word bands, and the
title contract on the first pass, and a blind rater still judged the three
weakest-tier books unpublishable. Three defect classes drove that verdict
and no existing check can see any of them, because every existing check
asks about structure, safety, or sameness and none asks about craft:

1. **Tense instability.** Two of three weak-tier books mix past and present
   narration, sometimes inside one paragraph ("They forced the rings. It
   seemed easier than thinking ... Tom's heart sinks. But Sef takes a
   breath."). A book may be told in either tense; it may not be told in
   both.
2. **Narrator moral tags.** Weak-tier endings close by stating the lesson
   ("understanding that sometimes the prize is not taking something, but
   giving something back", "it taught them what matters more than
   objects"). For the 10-13 band this is the single most condescending
   move available.
3. **Told emotion.** Stock interiority reports ("Tom's heart sinks",
   "panic flickers", "Nia's eyes go wide", "Tom laughs nervously") stand in
   for staged behavior.

Deterministic and dependency-free: verb-form cues for tense, curated
pattern sets for the other two. Dialogue is exempt throughout, because a
present-tense line of speech inside past narration is correct English, not a
defect. Exemption is by ``strip_dialogue``, which covers quoted spans *and*
tagged ones ("Almost there, Nina whispered."); it covered only quoted spans
until 2026-08-14, which exempted nothing at all in a catalogue that writes
its speech untagged by quotation marks.

Thresholds are calibrated against the nine-book clocktower tier corpus
(AL-168: blind craft means 4.9 frontier, 4.0 Sonnet, 2.2 Haiku); every
default is the loosest value that still leaves the two shippable tiers
clean. See each ``--flag`` help string for the measured per-tier numbers.

With ``--check``, exits 1 when any threshold is breached. Without it,
reports and exits 0.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, cast

from cyo_adventure.utils.sentences import split_sentences
from cyo_adventure.validator.dialogue import strip_tagged

# --------------------------------------------------------------------------
# Tense
# --------------------------------------------------------------------------

# Past/present-third-singular pairs for high-frequency narrative verbs. The
# table is deliberately symmetric: every past form has its present partner
# and vice versa, so neither tense can win a node just by being better
# represented in the lexicon. Forms that are ambiguous between the two
# tenses, such as read, set, put, cut, hit, cost, shut, left and lay, are
# excluded from both sides rather than assigned to one.
_TENSE_PAIRS: tuple[tuple[str, str], ...] = (
    ("was", "is"),
    ("were", "are"),
    ("had", "has"),
    ("said", "says"),
    ("went", "goes"),
    ("came", "comes"),
    ("took", "takes"),
    ("looked", "looks"),
    ("turned", "turns"),
    ("stood", "stands"),
    ("felt", "feels"),
    ("knew", "knows"),
    ("saw", "sees"),
    ("made", "makes"),
    ("found", "finds"),
    ("gave", "gives"),
    ("told", "tells"),
    ("held", "holds"),
    ("got", "gets"),
    ("began", "begins"),
    ("thought", "thinks"),
    ("ran", "runs"),
    ("walked", "walks"),
    ("nodded", "nods"),
    ("pulled", "pulls"),
    ("pushed", "pushes"),
    ("reached", "reaches"),
    ("watched", "watches"),
    ("waited", "waits"),
    ("opened", "opens"),
    ("closed", "closes"),
    ("smiled", "smiles"),
    ("laughed", "laughs"),
    ("tried", "tries"),
    ("stopped", "stops"),
    ("started", "starts"),
    ("moved", "moves"),
    ("climbed", "climbs"),
    ("stepped", "steps"),
    ("shook", "shakes"),
    ("leaned", "leans"),
    ("pointed", "points"),
    ("whispered", "whispers"),
    ("asked", "asks"),
    ("answered", "answers"),
    ("replied", "replies"),
    ("wanted", "wants"),
    ("needed", "needs"),
    ("seemed", "seems"),
    ("kept", "keeps"),
    ("sat", "sits"),
    ("heard", "hears"),
    ("did", "does"),
    ("swung", "swings"),
    ("caught", "catches"),
    ("carried", "carries"),
    ("dropped", "drops"),
    ("lifted", "lifts"),
    ("wrote", "writes"),
    ("meant", "means"),
    ("liked", "likes"),
    ("hoped", "hopes"),
    ("decided", "decides"),
    ("agreed", "agrees"),
    ("grinned", "grins"),
    ("frowned", "frowns"),
    ("counted", "counts"),
    ("checked", "checks"),
    ("followed", "follows"),
    ("stayed", "stays"),
    ("returned", "returns"),
    ("passed", "passes"),
    ("touched", "touches"),
    ("traced", "traces"),
    ("slipped", "slips"),
    ("hung", "hangs"),
    ("rang", "rings"),
    ("spun", "spins"),
    ("froze", "freezes"),
    ("glowed", "glows"),
    ("sounded", "sounds"),
    ("echoed", "echoes"),
    ("settled", "settles"),
    ("gathered", "gathers"),
    ("crossed", "crosses"),
    ("entered", "enters"),
    ("noticed", "notices"),
    ("realized", "realizes"),
    ("wondered", "wonders"),
    ("remembered", "remembers"),
    ("understood", "understands"),
    ("learned", "learns"),
    ("showed", "shows"),
    ("brought", "brings"),
    ("threw", "throws"),
    ("fell", "falls"),
    ("rose", "rises"),
    ("grew", "grows"),
    ("tugged", "tugs"),
    ("eased", "eases"),
    ("edged", "edges"),
    ("shifted", "shifts"),
    ("pressed", "presses"),
    ("tapped", "taps"),
    ("knocked", "knocks"),
    ("called", "calls"),
    ("shouted", "shouts"),
    ("muttered", "mutters"),
    ("added", "adds"),
    ("explained", "explains"),
    ("offered", "offers"),
    ("refused", "refuses"),
    ("chose", "chooses"),
    ("picked", "picks"),
    ("placed", "places"),
    ("hesitated", "hesitates"),
    ("paused", "pauses"),
    ("stared", "stares"),
    ("glanced", "glances"),
    ("blinked", "blinks"),
    ("swallowed", "swallows"),
    ("exhaled", "exhales"),
    ("forced", "forces"),
    ("locked", "locks"),
    ("protested", "protests"),
    ("jammed", "jams"),
    ("sank", "sinks"),
    ("remained", "remains"),
    ("emerged", "emerges"),
    ("trusted", "trusts"),
    ("solved", "solves"),
    ("worked", "works"),
    ("swore", "swears"),
    ("shone", "shines"),
    ("blew", "blows"),
    ("bound", "binds"),
    ("stumbled", "stumbles"),
    ("hurried", "hurries"),
    ("spoke", "speaks"),
    ("drew", "draws"),
    ("became", "becomes"),
    ("belonged", "belongs"),
    ("waved", "waves"),
    ("rested", "rests"),
    ("filled", "fills"),
    ("covered", "covers"),
    ("marked", "marks"),
    ("matched", "matches"),
    ("wore", "wears"),
    ("bent", "bends"),
    ("slid", "slides"),
    ("swept", "sweeps"),
    ("flickered", "flickers"),
    ("washed", "washes"),
    ("flooded", "floods"),
    ("crept", "creeps"),
    ("burned", "burns"),
    ("shivered", "shivers"),
    ("trembled", "trembles"),
    ("hummed", "hums"),
    ("clicked", "clicks"),
    ("creaked", "creaks"),
    ("groaned", "groans"),
    ("rattled", "rattles"),
    ("scraped", "scrapes"),
    ("appeared", "appears"),
    ("vanished", "vanishes"),
    ("promised", "promises"),
    ("insisted", "insists"),
    ("argued", "argues"),
    ("sighed", "sighs"),
    ("gasped", "gasps"),
)

_PAST_FORMS = frozenset(past for past, _ in _TENSE_PAIRS)
_PRESENT_FORMS = frozenset(present for _, present in _TENSE_PAIRS)

# A sentence carrying any of these is habitual, gnomic, or irrealis ("they
# would come back", "the tower always keeps its hour", "one day they will
# know"). Present-tense verbs in such a sentence are legitimate inside past
# narration, so the sentence contributes no tense evidence at all.
_HABITUAL_MARKERS = frozenset(
    "will would always never sometimes every each usually often whenever "
    "tomorrow someday must may might could should can".split()
)

# A sentence opening with a subordinator is a dependent clause whose verb
# routinely disagrees with the main narrative tense ("Since the tower was
# built ..."). Skipped outright rather than counted for either side.
_SUBORDINATORS = frozenset(
    "before when after since once while because though although if until as "
    "whenever where unless that".split()
)

# A cue directly preceded by one of these is a participle in a perfect or
# passive construction ("had found", "is opened"), not a finite past verb.
_AUXILIARIES = frozenset("have has had been being is are was were".split())

_CONTRACTIONS: dict[str, str] = {"wo": "will", "ca": "can", "sha": "shall"}

# Curly quotes are written as escapes so the pattern source stays ASCII
# (ruff RUF001 flags ambiguous unicode literals).
_LEFT_DOUBLE = "\u201c"
_RIGHT_DOUBLE = "\u201d"
_LEFT_SINGLE = "\u2018"
_RIGHT_SINGLE = "\u2019"

_DOUBLE_QUOTED = re.compile(
    f'["{_LEFT_DOUBLE}][^"{_LEFT_DOUBLE}{_RIGHT_DOUBLE}]{{0,400}}["{_RIGHT_DOUBLE}]'
)
_SINGLE_QUOTED = re.compile(
    f"(?<![A-Za-z])['{_LEFT_SINGLE}]"
    f"[^'{_LEFT_SINGLE}{_RIGHT_SINGLE}]{{0,400}}"
    f"['{_RIGHT_SINGLE}](?![A-Za-z])"
)
_WORD = re.compile(r"[A-Za-z']+")

PAST = "past"
PRESENT = "present"


def strip_quoted(text: str) -> str:
    """Return text with quoted dialogue replaced by whitespace.

    Handles quotation marks only. Callers wanting the exemption this script
    actually intends want :func:`strip_dialogue`; this stays separate because
    the single-quote handling below is more careful than a general detector
    should be, and is worth keeping distinct rather than folding away.

    Double quotes are removed first; single-quoted spans are then removed
    only where the opening quote is not preceded by a letter, so
    possessives and contractions ("Elara's", "isn't") survive.

    Args:
        text: Raw node body.

    Returns:
        The body with quoted spans blanked out.
    """
    return _SINGLE_QUOTED.sub(" ", _DOUBLE_QUOTED.sub(" ", text))


def strip_dialogue(text: str) -> str:
    """Return text with all recognised dialogue removed, quoted or tagged.

    Dialogue is exempt from every detector in this script: a child speaking
    in the present tense inside a past-tense book is correct English, and a
    character may say "my heart sank" without the narrator telling emotion.
    That rationale never depended on quotation marks, but the implementation
    did, so the catalogue's own unquoted house style ("Almost there, Nina
    whispered.") was being classified for tense and scanned for told emotion
    as though the narrator had said it.

    Args:
        text: Raw node body.

    Returns:
        The body with quoted spans blanked and tagged sentences dropped.
    """
    return strip_tagged(strip_quoted(text))


def _words(sentence: str) -> list[str]:
    """Return lowercased word tokens with ``n't`` contractions expanded."""
    tokens: list[str] = []
    for raw in cast("list[str]", _WORD.findall(sentence)):
        word = raw.lower()
        if word.endswith("n't"):
            stem = word[:-3]
            word = _CONTRACTIONS.get(stem, stem)
        tokens.append(word)
    return tokens


def sentence_tense(sentence: str) -> str | None:
    """Classify one sentence as ``past``, ``present``, or unclassifiable.

    Only the first finite verb cue counts. English main clauses are
    subject-verb-object, so the leftmost cue is the main-clause verb far
    more often than not; counting every cue instead made backstory clauses
    inside present-tense narration ("Jubal Finch built this pavilion, she
    says") read as tense breaks, which is exactly the false positive this
    detector cannot afford.

    Args:
        sentence: A single sentence, dialogue already stripped.

    Returns:
        ``PAST``, ``PRESENT``, or None when the sentence carries no usable
        evidence (no cue, a habitual/irrealis marker, a subordinate
        opening, or a participle after an auxiliary).
    """
    words = _words(sentence)
    if not words:
        return None
    if words[0] in _SUBORDINATORS:
        return None
    if any(word in _HABITUAL_MARKERS for word in words):
        return None
    for index, word in enumerate(words):
        if word in _PAST_FORMS:
            if index > 0 and words[index - 1] in _AUXILIARIES:
                return None
            return PAST
        if word in _PRESENT_FORMS:
            return PRESENT
    return None


def node_tense_counts(body: str) -> tuple[int, int]:
    """Return (past sentences, present sentences) for one node body.

    Args:
        body: Raw node body, quotes included.

    Returns:
        A pair of counts over classifiable, non-dialogue sentences.
    """
    # #ASSUME: data-integrity: splits with `utils.sentences.split_sentences`
    # (UW-C260, AL-390) rather than the old bare `[^.!?]+[.!?]*` idiom, so an
    # abbreviation ("Mr. Fez") or a tagged "!"/"?" line no longer produces a
    # spurious extra sentence. Measured over the 31 committed books: the
    # (past, present) totals move by at most one sentence in 3 of 31 books
    # (a "!"/abbreviation merge absorbing a one-word tag clause), and neither
    # the dominant tense nor the set of nodes `tense_report` flags as
    # unstable changes in any book.
    # #VERIFY: tests/unit/test_sentences.py pins the splitter itself;
    # tests/unit/test_check_prose_craft.py exercises this function's tense
    # classification.
    stripped = strip_dialogue(body)
    past = present = 0
    for sentence in split_sentences(stripped):
        tense = sentence_tense(sentence)
        if tense == PAST:
            past += 1
        elif tense == PRESENT:
            present += 1
    return past, present


class TenseNode(NamedTuple):
    """One node's tense evidence."""

    node_id: str
    past: int
    present: int
    reason: str


class TenseReport(NamedTuple):
    """A book's tense verdict."""

    dominant: str
    past: int
    present: int
    unstable: list[TenseNode]

    @property
    def minority_ratio(self) -> float:
        """Return the share of sentences disagreeing with the book tense."""
        total = self.past + self.present
        if total == 0:
            return 0.0
        return min(self.past, self.present) / total


def tense_report(
    story: dict[str, Any],
    *,
    min_cues: int = 6,
    max_node_mix: float = 0.34,
) -> TenseReport:
    """Classify a book's narrative tense and find the nodes that break it.

    Args:
        story: Decoded filled-story JSON.
        min_cues: Minimum classifiable sentences before a node may be
            flagged. Short nodes carry too little evidence to distinguish a
            tense break from two incidental clauses. A node whose sentences
            are *unanimously* in the non-dominant tense needs only half
            that (floor 3): unanimity is not a judgment call, so the
            evidence bar that guards mixture judgments does not apply.
        max_node_mix: Minority share at or above which a node counts as
            internally mixed.

    Returns:
        The dominant tense, the book totals, and every node that either
        disagrees with the dominant tense or mixes both above the
        threshold. A node meeting both conditions is reported once.
    """
    unanimous_min = max(3, min_cues // 2)
    per_node: list[tuple[str, int, int]] = []
    total_past = total_present = 0
    for node in cast("list[dict[str, Any]]", story.get("nodes") or []):
        past, present = node_tense_counts(str(node.get("body", "")))
        total_past += past
        total_present += present
        per_node.append((str(node.get("id", "?")), past, present))

    dominant = PAST if total_past >= total_present else PRESENT
    unstable: list[TenseNode] = []
    for node_id, past, present in per_node:
        total = past + present
        if total == 0:
            continue
        node_tense = PAST if past >= present else PRESENT
        minority = min(past, present) / total
        unanimous = minority == 0.0
        if node_tense != dominant and (
            total >= min_cues or (unanimous and total >= unanimous_min)
        ):
            unstable.append(
                TenseNode(node_id, past, present, f"node is wholly {node_tense}")
                if unanimous
                else TenseNode(node_id, past, present, f"node is {node_tense}-dominant")
            )
        elif total >= min_cues and minority >= max_node_mix:
            unstable.append(
                TenseNode(
                    node_id, past, present, f"mixed {minority:.0%} minority tense"
                )
            )
    return TenseReport(dominant, total_past, total_present, unstable)


# --------------------------------------------------------------------------
# Narrator moral tags
# --------------------------------------------------------------------------

# Curated lesson framings, matched only near the close of an ending body:
# the defect AL-170 names is a narrator stepping forward at the last moment
# to explain what the reader just read. Each pattern is drawn from a phrase
# a blind rater cited, or is the minimal generalization of one.
_MORAL_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\blearn(?:ed|ing|s)?\s+(?:that|what|why|how)\b", "learned that"),
    (r"\btaught\s+(?:them|him|her|us)\b", "taught them"),
    (r"\bunderstand(?:ing|s)?\s+(?:that|what|why)\b", "understanding that"),
    (
        r"\bsometimes\b[^.!?]{0,80}\bis not\b[^.!?]{0,80}\bbut\b",
        "sometimes the X is not Y but Z",
    ),
    (r"\bnot\s+\w+ing\b[^.!?]{0,40}\bbut\s+\w+ing\b", "not Xing but Ying"),
    (r"\bis what matters\b", "is what matters"),
    (r"\bwhat matters (?:more|most)\b", "what matters more than"),
    (r"\bis its own (?:kind of|sort of|reward)\b", "is its own kind of"),
    (r"\b(?:shows|showed|sounds|sounded|looks|looked) in\b", "shows in"),
    (r"\bcomes from choosing\b", "comes from choosing"),
    (r"\bthe real \w+ (?:was|is)\b", "the real X was"),
    (r"\bis(?:n't| not) punishing\b", "is not punishing them"),
    (r"\bit(?:'s| is) teaching\b", "it is teaching them"),
    (r"\bthat(?:'s| is) what \w+ (?:means|is)\b", "that is what X means"),
    (r"\bthe lesson\b", "the lesson"),
    (
        (
            r"\b(?:wisdom|courage|strength|kindness|respect|patience)\s+"
            r"(?:sometimes\s+)?(?:sounds|looks|shows|is|comes)\b"
        ),
        "virtue sounds like",
    ),
    (
        r"\b(?:respect|courage|kindness|honesty|patience|trust)\s+that comes from\b",
        "virtue that comes from",
    ),
    (r"\bthe knowing\b[^.!?]{0,30}\bwas enough\b", "the knowing was enough"),
)

_MORAL_COMPILED: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), name) for pattern, name in _MORAL_PATTERNS
)


class MoralHit(NamedTuple):
    """One narrator moral tag."""

    node_id: str
    pattern: str
    sentence: str


def _is_ending(node: dict[str, Any]) -> bool:
    """Return True when a node is an ending node."""
    return bool(node.get("is_ending")) or isinstance(node.get("ending"), dict)


def _sentences(text: str) -> list[str]:
    """Return non-empty, stripped sentences of a text.

    Delegates to :func:`cyo_adventure.utils.sentences.split_sentences`
    (UW-C260, AL-390) rather than the bare ``[^.!?]+[.!?]*`` idiom this
    script used before: the tail-sentence extraction below is exactly the
    kind of "opening/closing sentence" use that idiom got wrong on an
    abbreviation. Measured over the 31 committed books: the extracted
    tail-sentence set for :func:`moral_tags` is byte-identical, old splitter
    versus new, in every book.
    """
    return split_sentences(text)


def moral_tags(story: dict[str, Any], *, tail_sentences: int = 4) -> list[MoralHit]:
    """Find narrator moral tags in the closing sentences of ending nodes.

    Args:
        story: Decoded filled-story JSON.
        tail_sentences: How many closing sentences of each ending body to
            scan. The defect is a closing move, so scanning the whole body
            buys little and risks flagging a character's mid-scene
            reflection.

    Returns:
        One hit per matching sentence, in node order. A sentence matching
        several patterns is reported once, under the first that matched.
    """
    hits: list[MoralHit] = []
    for node in cast("list[dict[str, Any]]", story.get("nodes") or []):
        if not _is_ending(node):
            continue
        node_id = str(node.get("id", "?"))
        body = strip_dialogue(str(node.get("body", "")))
        # A tail of 0 would slice [-0:], i.e. the WHOLE body, and a negative
        # value inverts the window; both silently widen the scan.
        tail = _sentences(body)[-tail_sentences:] if tail_sentences > 0 else []
        for sentence in tail:
            for pattern, name in _MORAL_COMPILED:
                if pattern.search(sentence):
                    hits.append(MoralHit(node_id, name, sentence))
                    break
    return hits


# --------------------------------------------------------------------------
# Told emotion
# --------------------------------------------------------------------------

_EMOTION = (
    r"(?:panic|relief|dread|fear|joy|worry|excitement|guilt|shame|hope|pride"
    r"|anger|doubt|sadness|nerves|fright|terror)"
)

# Stock interiority reports: an organ or an abstract noun performing the
# feeling on the character's behalf, in place of staged behavior.
_TOLD_PATTERNS: tuple[str, ...] = (
    (
        r"\bhearts? (?:sinks?|sank|sunk|leaps?|leapt|leaped|pounds?|pounded"
        r"|hammers?|hammered|races?|raced|thuds?|thudded|skips?|skipped"
        r"|swells?|swelled)\b"
    ),
    (
        r"\bstomachs? (?:drops?|dropped|twists?|twisted|knots?|knotted|flips?"
        r"|flipped|lurches|lurched|clenches|clenched)\b"
    ),
    r"\beyes? (?:go|goes|went|grow|grew) wide\b",
    r"\beyes? widen(?:ed|s)?\b",
    (
        rf"\b{_EMOTION} (?:flickers?|flickered|washes|washed|floods?|flooded"
        r"|surges?|surged|rises?|rose|spikes?|spiked|flares?|flared|courses?"
        r"|coursed|prickles?|prickled|creeps?|crept|settles?|settled)\b"
    ),
    rf"\ba (?:wave|surge|flood|rush|stab|pang|jolt|flicker) of {_EMOTION}\b",
    r"\b(?:laughs?|laughed|giggles?|giggled|smiles?|smiled) nervously\b",
    r"\bbreaths? (?:catches|caught|hitches|hitched)\b",
    r"\bthroats? (?:tightens?|tightened|closes?|closed)\b",
    r"\bchests? (?:tightens?|tightened|squeezes?|squeezed)\b",
    r"\bpulse (?:quickens?|quickened|races?|raced)\b",
    r"\bblood (?:runs?|ran) cold\b",
    r"\bshivers? (?:runs?|ran|goes|went) (?:down|up)\b",
    r"\bspine (?:tingles?|tingled|prickles?|prickled)\b",
    r"\bbutterflies in\b",
    r"\bknot in (?:his|her|their|its|my) (?:stomach|chest|throat)\b",
    r"\bhands? (?:shakes?|shook|trembles?|trembled)\b",
    r"\bmouth (?:goes|went) dry\b",
    r"\bcheeks? (?:burns?|burned|flush(?:es|ed)?|reddens?|reddened)\b",
    r"\btears? (?:pricks?|pricked|sting|stung|wells?|welled)\b",
    rf"\bfe(?:els?|lt) (?:a )?(?:sudden )?{_EMOTION}\b",
    (
        rf"\b{_EMOTION} (?:grips?|gripped|seizes?|seized|fills?|filled"
        r"|washes over|washed over)\b"
    ),
    r"\bswallow(?:s|ed)? hard\b",
    r"\bfroze(?:n)? in place\b",
    r"\bwith a (?:sinking|racing|pounding) (?:heart|feeling)\b",
)

_TOLD_COMPILED: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in _TOLD_PATTERNS
)


class TellHit(NamedTuple):
    """One told-emotion phrase."""

    node_id: str
    phrase: str


class TellReport(NamedTuple):
    """A book's told-emotion verdict."""

    hits: list[TellHit]
    words: int

    @property
    def per_1000(self) -> float:
        """Return hits per 1000 non-dialogue narration words.

        Length normalization follows ``check_sibling_fills.py`` (AL-159): a
        fixed count cannot serve both an 11-node and a 26-node fill.
        """
        return len(self.hits) / max(self.words, 1) * 1000.0


def told_emotion(story: dict[str, Any]) -> TellReport:
    """Count stock interiority reports outside dialogue.

    Args:
        story: Decoded filled-story JSON.

    Returns:
        Every match with its node id, plus the narration word count the
        rate is normalized against.
    """
    hits: list[TellHit] = []
    words = 0
    for node in cast("list[dict[str, Any]]", story.get("nodes") or []):
        node_id = str(node.get("id", "?"))
        body = strip_dialogue(str(node.get("body", "")))
        words += len(_WORD.findall(body))
        for pattern in _TOLD_COMPILED:
            hits.extend(
                TellHit(node_id, match.group(0)) for match in pattern.finditer(body)
            )
    return TellReport(hits, words)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _load(path: str) -> dict[str, Any] | None:
    """Load a filled-story JSON object, or report and return None.

    Args:
        path: File path to read.

    Returns:
        The decoded object, or None on any load failure.
    """
    try:
        # #ASSUME: security: canonicalized with .resolve() (CWE-23 hardening)
        # but deliberately not contained to a fixed base, matching
        # check_fill_integrity.py::_load. This is a dev-only checker run by
        # the operator (or an authoring agent on the operator's own
        # machine) against fills that legitimately live outside the repo
        # tree, including pytest tmp_path fixtures.
        # #VERIFY: tests/unit/test_check_prose_craft.py drives main() against
        # tmp_path files; adding containment must not break it.
        data = json.loads(Path(path).resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot load {path}: {exc}\n")
        return None
    if not isinstance(data, dict):
        sys.stderr.write(f"error: expected a JSON object in {path}\n")
        return None
    return cast("dict[str, Any]", data)


def _build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this checker."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fills", nargs="+", help="One or more filled story JSON files.")
    parser.add_argument(
        "--max-redundant-nodes",
        type=int,
        default=0,
        help=(
            "Fail when more than this many nodes repeat another node's exact "
            "body (default 0: the known-good corpus has zero duplicate "
            "bodies, while the worst live book had 23; AL-496/UW-C313)."
        ),
    )
    parser.add_argument(
        "--max-top3-label-share",
        type=float,
        default=0.5,
        help=(
            "Fail when the three most common label strings cover more than "
            "this share of all labels, on books with at least 40 labels "
            "(default 0.5: known-good books run 0.02-0.27, the worst live "
            "book 0.898; AL-496/UW-C313)."
        ),
    )
    parser.add_argument(
        "--max-third-second-person",
        type=float,
        default=0.35,
        help=(
            "Fail a book declared third-person whose second-person node rate "
            "exceeds this ceiling (default 0.35: committed third-person prose "
            "runs 0.0-0.27, and the live drift case shipped a 3-5 book fully "
            "second-person against third-person beats; UW-C324)."
        ),
    )
    parser.add_argument(
        "--min-gamebook-second-person",
        type=float,
        default=0.5,
        help=(
            "Fail a book declared (or, for an undeclared gamebook, styled) "
            "second-person whose second-person node rate falls below this "
            "floor (default 0.5: committed gamebooks run 0.715-1.0). An "
            "undeclared PROSE book is reported without gating; a declared "
            "book is gated on its metadata.narrative_person declaration "
            "(ruling 9.4; AL-518/UW-C313)."
        ),
    )
    parser.add_argument(
        "--max-unstable-nodes",
        type=int,
        default=0,
        help=(
            "Nodes per book allowed to disagree with, or internally mix, the "
            "book's narrative tense (default 0; calibration on the "
            "nine-book tier corpus: frontier 0/0/0, Sonnet 0/0/0, Haiku "
            "4/0/1, so zero is the only value that separates the tiers)."
        ),
    )
    parser.add_argument(
        "--min-tense-cues",
        type=int,
        default=6,
        help=(
            "Classifiable sentences a node needs before it may be flagged "
            "for tense (default 6; at 4 a two-clause node produced false "
            "positives in a clean frontier-tier book). A node unanimously "
            "in the non-dominant tense needs only half this, floor 3."
        ),
    )
    parser.add_argument(
        "--max-node-mix",
        type=float,
        default=0.34,
        help=(
            "Minority-tense share at or above which a node counts as mixed "
            "(default 0.34, i.e. one sentence in three)."
        ),
    )
    parser.add_argument(
        "--max-moral-tags",
        type=int,
        default=0,
        help=(
            "Narrator moral tags allowed across a book's endings (default 0; "
            "calibration: frontier 0/0/0, Sonnet 0/0/0, Haiku 2/1/2)."
        ),
    )
    parser.add_argument(
        "--ending-tail-sentences",
        type=int,
        default=4,
        help=(
            "Closing sentences of each ending body scanned for moral tags "
            "(default 4; the defect is a closing move)."
        ),
    )
    parser.add_argument(
        "--max-told-per-1000",
        type=float,
        default=0.5,
        help=(
            "Told-emotion phrases per 1000 narration words (default 0.5; "
            "calibration: frontier 0.00/0.00/0.00, Sonnet 0.35/0.00/0.00, "
            "Haiku 1.10/0.00/0.31, so 0.5 clears both shippable tiers and "
            "catches the worst book)."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when any threshold is breached.",
    )
    return parser


# Label-collapse is only meaningful with enough labels to collapse: a 6-label
# picture book legitimately has a top-3 share of 0.5+.
_TOP3_MIN_LABELS = 40


@dataclass(frozen=True)
class SamenessReport:
    """Duplicate-body and label-diversity counts for one book (UW-C313).

    Attributes:
        repeated_texts: Distinct body strings appearing on 2+ nodes.
        redundant_nodes: Nodes beyond the first carrying a repeated body.
        labels: Total choice labels.
        distinct_labels: Distinct label strings.
        top3_share: Share of all labels covered by the three most common
            strings; 0.0 when the book has no labels.
    """

    repeated_texts: int
    redundant_nodes: int
    labels: int
    distinct_labels: int
    top3_share: float


def sameness_report(story: dict[str, Any]) -> SamenessReport:
    """Count duplicate bodies and label collapse (AL-496/UW-C313).

    Deliberate exception to the module's dialogue exemption: bodies are
    compared RAW, because a byte-duplicated passage is a sameness defect
    whether or not it contains quoted speech, and stripping dialogue would
    merge distinct bodies that differ only in their quotes.

    The worst live book measured had 23 redundant nodes across 11 repeated
    texts and three label strings covering 89.8 percent of 674 choices; the
    known-good corpus has zero duplicate bodies and top-3 shares of 2 to 27
    percent (the 0.02-0.27 range the --max-top3-label-share default is
    calibrated against).

    Args:
        story: Decoded filled-story JSON.

    Returns:
        SamenessReport: The counts.
    """
    nodes = cast("list[dict[str, Any]]", story.get("nodes") or [])
    bodies = [
        cast("str", node.get("body") or "").strip()
        for node in nodes
        if cast("str", node.get("body") or "").strip()
    ]
    body_counts = Counter(bodies)
    dup = {text: count for text, count in body_counts.items() if count > 1}
    labels = [
        cast("str", choice.get("label") or "")
        for node in nodes
        for choice in cast("list[dict[str, Any]]", node.get("choices") or [])
        if choice.get("label")
    ]
    label_counts = Counter(labels)
    top3 = sum(count for _, count in label_counts.most_common(3))
    return SamenessReport(
        repeated_texts=len(dup),
        redundant_nodes=sum(count - 1 for count in dup.values()),
        labels=len(labels),
        distinct_labels=len(label_counts),
        top3_share=(top3 / len(labels)) if labels else 0.0,
    )


_SECOND_PERSON_RE = re.compile(r"\b(you|your|yours|yourself)\b", re.IGNORECASE)


@dataclass(frozen=True)
class PersonReport:
    """Second-person presence for one book (AL-518/UW-C313).

    Attributes:
        nodes: Nodes with non-empty prose.
        second_person_nodes: Nodes whose body contains a second-person token.
        rate: ``second_person_nodes / nodes``; 0.0 for an empty book.
    """

    nodes: int
    second_person_nodes: int
    rate: float


def person_report(story: dict[str, Any]) -> PersonReport:
    """Measure second-person presence per node (AL-518/UW-C313).

    Calibration (2026-08-21): committed gamebooks run 0.715 to 1.0,
    committed third-person prose 0.0 to 0.27, and three live fills of one
    prose skeleton scattered to 0.07, 0.13 and 0.72 before the contract
    pinned narrative person. The contract now carries
    ``metadata.narrative_person`` (ruling 9.4), and ``_report`` gates this
    rate against the declaration: declared second-person books must clear
    the floor, declared third-person books must stay under the ceiling, and
    only an undeclared prose book is reported without gating.

    Args:
        story: Decoded filled-story JSON.

    Returns:
        PersonReport: The per-node second-person rate.
    """
    nodes = [
        cast("str", node.get("body") or "")
        for node in cast("list[dict[str, Any]]", story.get("nodes") or [])
        if cast("str", node.get("body") or "").strip()
    ]
    # Dialogue is exempt, per the module contract: a third-person book whose
    # characters say "you" to each other is not narrating in second person,
    # and counting quoted spans let ordinary dialogue breach the third-person
    # ceiling on its own (PR #737 review, I8).
    hits = sum(1 for body in nodes if _SECOND_PERSON_RE.search(strip_dialogue(body)))
    return PersonReport(
        nodes=len(nodes),
        second_person_nodes=hits,
        rate=(hits / len(nodes)) if nodes else 0.0,
    )


def _report(story: dict[str, Any], name: str, args: argparse.Namespace) -> bool:
    """Print every detector report for one book (tense, morals, told emotion, sameness, person).

    Args:
        story: Decoded filled-story JSON.
        name: Display name for the book (its file name).
        args: Parsed CLI arguments carrying the thresholds.

    Returns:
        True when any threshold is breached.
    """
    breached = False
    sys.stdout.write(f"{name}\n")

    tense = tense_report(
        story,
        min_cues=cast("int", args.min_tense_cues),
        max_node_mix=cast("float", args.max_node_mix),
    )
    over_tense = len(tense.unstable) > cast("int", args.max_unstable_nodes)
    marker = "FAIL" if over_tense else "ok  "
    sys.stdout.write(
        f"  {marker} tense: {tense.dominant}-dominant "
        f"({tense.past} past / {tense.present} present sentences, "
        f"{tense.minority_ratio:.1%} minority); "
        f"{len(tense.unstable)} unstable nodes "
        f"(budget {args.max_unstable_nodes})\n"
    )
    for node in tense.unstable:
        sys.stdout.write(
            f"       {node.node_id}: {node.past} past / {node.present} present, "
            f"{node.reason}\n"
        )
    breached = breached or over_tense

    morals = moral_tags(story, tail_sentences=cast("int", args.ending_tail_sentences))
    over_moral = len(morals) > cast("int", args.max_moral_tags)
    marker = "FAIL" if over_moral else "ok  "
    sys.stdout.write(
        f"  {marker} moral tags: {len(morals)} in ending closings "
        f"(budget {args.max_moral_tags})\n"
    )
    for hit in morals:
        sys.stdout.write(f"       {hit.node_id} [{hit.pattern}]: {hit.sentence}\n")
    breached = breached or over_moral

    told = told_emotion(story)
    over_told = told.per_1000 > cast("float", args.max_told_per_1000)
    marker = "FAIL" if over_told else "ok  "
    sys.stdout.write(
        f"  {marker} told emotion: {len(told.hits)} phrases over {told.words} "
        f"narration words ({told.per_1000:.2f} per 1000; budget "
        f"{args.max_told_per_1000})\n"
    )
    for hit in told.hits:
        sys.stdout.write(f"       {hit.node_id}: {hit.phrase}\n")
    breached = breached or over_told

    same = sameness_report(story)
    over_same = same.redundant_nodes > cast("int", args.max_redundant_nodes) or (
        same.labels >= _TOP3_MIN_LABELS
        and same.top3_share > cast("float", args.max_top3_label_share)
    )
    marker = "FAIL" if over_same else "ok  "
    sys.stdout.write(
        f"  {marker} sameness: {same.redundant_nodes} redundant nodes over "
        f"{same.repeated_texts} repeated texts (budget "
        f"{args.max_redundant_nodes}); {same.distinct_labels}/{same.labels} "
        f"distinct labels, top-3 share {same.top3_share:.1%} (budget "
        f"{args.max_top3_label_share:.0%})\n"
    )
    breached = breached or over_same

    person = person_report(story)
    metadata = cast("dict[str, Any]", story.get("metadata") or {})
    declared = cast("str", metadata.get("narrative_person") or "")
    style = cast("str", metadata.get("narrative_style") or "")
    # Keyed to the declared person (UW-C324, ruled 2026-08-21): a declared
    # second-person book must clear the floor, a declared third-person book
    # must stay under the ceiling, and an undeclared book falls back to the
    # gamebook-style floor only (the pre-declaration behavior).
    person_breach = False
    if declared == "third" and style == "gamebook":
        # Contradictory declaration: the gamebook genre addresses the reader,
        # so holding a correct second-person gamebook to the third-person
        # ceiling would invert the gate (PR #737 review, I10). The model now
        # rejects this combination at validation; a raw document carrying it
        # is flagged as a contract error rather than measured.
        person_breach = True
        framing = "contradictory declaration: a gamebook cannot be third person"
    elif declared == "second":
        person_breach = person.rate < cast("float", args.min_gamebook_second_person)
        framing = f"declared second, floor {args.min_gamebook_second_person:.0%}"
    elif declared == "third":
        person_breach = person.rate > cast("float", args.max_third_second_person)
        framing = f"declared third, ceiling {args.max_third_second_person:.0%}"
    elif style == "gamebook":
        person_breach = person.rate < cast("float", args.min_gamebook_second_person)
        framing = f"undeclared gamebook, floor {args.min_gamebook_second_person:.0%}"
    else:
        framing = "undeclared prose, reported only"
    marker = "FAIL" if person_breach else "ok  "
    sys.stdout.write(
        f"  {marker} person: second-person in "
        f"{person.second_person_nodes}/{person.nodes} nodes "
        f"({person.rate:.1%}; {framing})\n"
    )
    return breached or person_breach


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; exit 1 with --check when a threshold is breached.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 2 when a file cannot be read, 1 when ``--check`` is set
        and any book breaches a threshold, 0 otherwise.
    """
    args = _build_parser().parse_args(argv)
    breached = False
    for path in cast("list[str]", args.fills):
        story = _load(path)
        if story is None:
            return 2
        breached = _report(story, Path(path).name, args) or breached
    if args.check and breached:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
