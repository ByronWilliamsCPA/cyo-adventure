"""Reader-agency detectors: does the book still behave like a gamebook?

An editorial read of the filled catalogue (2026-11-20) found books that open
well and stop behaving like choose-your-own-adventures by the middle, through
four defect classes that every existing check is blind to. None is a safety,
structure, sameness, or tense question, which is why the gate, topology,
fill-integrity, and the other prose-craft detectors all passed books carrying
dozens of them:

1. **Merge-seam narration** (:func:`merge_seams`). A node reached from two or
   more nodes opens by telling the reader their route did not matter:
   "Whichever way Mira had come, every path had led her here at last."
2. **Option recap** (:func:`option_recaps`). A decision node closes by restating
   its buttons in prose ("She could hum slow and sure into the tube. Or she
   could let her fear win out...") or by announcing that a choice is due ("Wren
   had a choice to make.").
3. **Label defects** (:func:`label_defects`). Labels that name a mental act
   rather than an action ("Sit with what this means."), graph jargon leaking
   into the story ("Feel your way to the hub."), and second-person labels over
   third-person prose ("Use your grandfather transmitter.").
4. **Give-up and early setback endings** (:func:`give_up_endings`,
   :func:`early_setbacks`). Negative endings whose close has the hero go home
   or quit, and negative endings a reader reaches within very few decisions.

A fifth fact frames all four: a book with merge nodes and no state
(variables, conditions, effects) can never let an earlier choice matter
later, so every merge is a place where the reader's route is erased.
:class:`AgencyReport` carries the counts and a one-sentence headline a
non-engineer can read. Fork-level consequence ("false" forks whose options
rejoin with nothing changed) is ``validator/consequence.py``'s job and is
deliberately not recomputed here.

**Calibration.** Every pattern below was tuned against all 31 committed
``out/*.filled.json`` books (six bands, prose and gamebook, past and present
tense, third and second person), not the five books the defects were first
noticed in: ``validator/dialogue.py``'s module docstring records three earlier
detectors that were tuned on a handful of books and were blind to the house
style of the rest. Each false-positive class found during calibration is
named next to the rule that excludes it and pinned by a regression test in
``tests/unit/test_validator_agency.py``.

Baseline on ``main`` (2026-11-20), all 31 books; book, band, merge nodes,
seams, decisions, recaps, meta / jargon / second-person labels, negative
endings, give-ups, early setbacks (at 3 decisions), variables::

    book                     band  mrg seam dec recap meta jar 2p neg give early var
    baking-day-with-grandma- 3-5     5    0   8     5    0   0  0   0    0     0   0
    puddle-jumping-day       3-5     0    0   3     1    0   0  0   0    0     0   0
    ashfall-expedition       16+    21    0  57    15    0   0  0 140   56    10   0
    backyard-treasure-map    5-8     0    0  10     2    0   0  0   0    0     0   0
    big-red-balloon          3-5     0    0   5     0    0   0  0   0    0     0   0
    cave-of-echoes           8-11    0    0  14     5    0   0  0   0    0     0   0
    clocktower-cipher        10-13   3    0  11    10    0   0  2   4    1     0   0
    clockwork-menagerie      8-11   12    8  29    21    0   0  6   7    0     3   0
    clover-and-the-butterfly 3-5     0    0   5     3    0   0  0   0    0     0   0
    drowned-court            16+    10    0  37    20    0   0  0  98   44    11   0
    harrowstone-keep         13-16  66    0 211     0    0   0  0 145    7     3   4
    hollow-lighthouse        10-13  17   14  63    42    0   0  0  16    4     2   0
    lantern-festival         5-8     2    0  17    17    0   0  3   0    0     0   0
    last-train-north         16+    21   21  43    26    0   0 20  11    0     4   0
    lost-mitten              3-5     3    0   6     6    0   0  1   0    0     0   0
    mapmakers-island         10-13  33    1 113     7    3   0  3  29    4     2   0
    midnight-museum          10-13   8    2  31     9    1   1  4   9    3     3   0
    night-market             5-8     8    0  23    16    0   0  0   0    0     0   0
    salt-archive             16+    11   11  62    55    0   0 16  18    0     4   0
    school-garden-mystery    5-8     3    0  20    10    0   0  0   0    0     0   0
    signal-in-the-static     13-16   6    5  51    42    8   0  4  21    4     2   0
    sky-ship-stowaway        8-11   20    4  36    32    0   0  6   4    2     2   0
    sleepy-little-star       3-5     3    0   6     6    0   0  0   0    0     0   0
    snow-day-expedition      5-8     0    0   9     2    0   0  0   0    0     0   0
    sunken-signal            16+     5    0  13    12    0   0  0  12    1     2   4
    sunken-temple            13-16  66    0 211     0    2   0  0 145    3     3   4
    sunspire-ascent          13-16  11    0  37    31    0   0  0  67   50     3   0
    teddy-bears-picnic       3-5     2    0  16    10    0   0  0   0    0     0   0
    thornwood-trial          13-16  19    0  40    11    0   0  0 111   17     6   0
    tide-pool-rescue         5-8    14    0  26    23    0   0  5   0    0     0   0
    vanishing-orchard        13-16   9    3  38    23    3   0 18  23    2     8   0

**Dialogue.** Seams, recaps, and give-up closes are narrator moves, so
dialogue is stripped first with :func:`~cyo_adventure.validator.prose_craft.narration_of`,
exactly as the other narrator-attribution detectors do. A character who says
"We could try the attic, or the shed" is staging a choice in-scene, which is
craft rather than the defect.

Pure module: stdlib plus ``validator.prose_craft`` and ``utils.sentences``.
Offline and report-first: nothing on the request path imports it.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

from cyo_adventure.utils.sentences import split_sentences
from cyo_adventure.validator.prose_craft import (
    MIN_GAMEBOOK_SECOND_PERSON,
    narration_of,
    person_report,
    strip_quoted,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "DEFAULT_EARLY_SETBACK_DECISIONS",
    "AgencyReport",
    "BookPerson",
    "EndingHit",
    "LabelDefects",
    "LabelHit",
    "RecapHit",
    "SeamHit",
    "StateCounts",
    "agency_report",
    "book_person",
    "decisions_to_reach",
    "early_setbacks",
    "give_up_endings",
    "inbound_sources",
    "label_defects",
    "merge_seams",
    "option_recaps",
    "state_counts",
]

DEFAULT_EARLY_SETBACK_DECISIONS: Final[int] = 3
"""A negative ending reachable within this many decisions counts as early.

Calibrated on the 31-book corpus with true minimum decision counts: at 2,
only the death-trap gamebooks (16+ and 13-16) register at all, which says
nothing about the prose books the editorial read was about; at 3, eleven
prose books from 8-11 up register two to eight setbacks each, the "fails on
the third tap of a 150-node book" shape the read described. The gamebooks sit
far above any budget at either value by genre, so the measure is reported,
never gated, by default.
"""

_RECAP_TAIL: Final[int] = 3
_GIVE_UP_TAIL: Final[int] = 2
_SEAM_OPENING: Final[int] = 2


# --------------------------------------------------------------------------
# Graph helpers
# --------------------------------------------------------------------------


def _nodes(story: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the story's nodes, tolerating a missing list."""
    return cast("list[dict[str, Any]]", story.get("nodes") or [])


def _choices(node: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return a node's choices, tolerating a missing list."""
    return cast("list[dict[str, Any]]", node.get("choices") or [])


def _is_ending(node: Mapping[str, Any]) -> bool:
    """Return True for an ending node (flag or ending block)."""
    return bool(node.get("is_ending")) or isinstance(node.get("ending"), dict)


def _valence(node: Mapping[str, Any]) -> str:
    """Return an ending node's valence, or an empty string."""
    ending = node.get("ending")
    if not isinstance(ending, dict):
        return ""
    return str(cast("dict[str, Any]", ending).get("valence") or "")


def _is_decision(node: Mapping[str, Any]) -> bool:
    """Return True when a node offers two or more distinct targets.

    Distinct targets rather than raw choice count: two labels leading to the
    same node are one destination, and the reader is not choosing between
    routes there.
    """
    return len({str(c.get("target")) for c in _choices(node)}) >= 2


def inbound_sources(story: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    """Map each node id to the distinct nodes with a choice targeting it.

    A self-loop is not counted: a node that leads back to itself has not been
    reached by a different route.

    Args:
        story: Decoded filled-story JSON.

    Returns:
        Node id to the frozenset of distinct source node ids; nodes with no
        inbound edge map to an empty set.
    """
    inbound: dict[str, set[str]] = {str(n.get("id")): set() for n in _nodes(story)}
    for node in _nodes(story):
        source = str(node.get("id"))
        for choice in _choices(node):
            target = str(choice.get("target"))
            if target != source:
                inbound.setdefault(target, set()).add(source)
    return {node_id: frozenset(srcs) for node_id, srcs in inbound.items()}


def decisions_to_reach(story: Mapping[str, Any]) -> dict[str, int]:
    """Return the fewest decisions a reader must make to reach each node.

    A decision is leaving a node that offers two or more distinct targets;
    following a single-choice node is a page turn and costs nothing. Computed
    by 0-1 breadth-first search, so the figure is the true minimum rather than
    the decision count on the fewest-taps path. Conditions are ignored, which
    can only make a node look closer than it is, the conservative direction
    for an "ending comes too soon" measure.

    Args:
        story: Decoded filled-story JSON.

    Returns:
        Node id to minimum decisions; unreachable nodes are absent.
    """
    nodes = {str(n.get("id")): n for n in _nodes(story)}
    start = str(story.get("start_node") or "")
    if start not in nodes:
        return {}
    best: dict[str, int] = {start: 0}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        node = nodes.get(current)
        if node is None:
            continue
        step = 1 if _is_decision(node) else 0
        for choice in _choices(node):
            target = str(choice.get("target"))
            cost = best[current] + step
            if target in nodes and cost < best.get(target, cost + 1):
                best[target] = cost
                # 0-1 BFS: a free edge goes to the front so it is settled
                # before any costlier frontier.
                if step == 0:
                    queue.appendleft(target)
                else:
                    queue.append(target)
    return best


@dataclass(frozen=True)
class StateCounts:
    """Declared state for one book.

    Attributes:
        variables: Declared variables.
        conditional_choices: Choices carrying a condition.
        effects: Choice effects plus node ``on_enter`` effects.
    """

    variables: int
    conditional_choices: int
    effects: int

    @property
    def stateless(self) -> bool:
        """Return True when nothing a reader does can be remembered."""
        return self.variables == 0 and self.conditional_choices == 0


def state_counts(story: Mapping[str, Any]) -> StateCounts:
    """Count declared variables, conditional choices, and effects.

    Args:
        story: Decoded filled-story JSON.

    Returns:
        StateCounts: The three counts.
    """
    nodes = _nodes(story)
    return StateCounts(
        variables=len(cast("list[Any]", story.get("variables") or [])),
        conditional_choices=sum(
            1 for n in nodes for c in _choices(n) if c.get("condition")
        ),
        effects=sum(
            len(cast("list[Any]", c.get("effects") or []))
            for n in nodes
            for c in _choices(n)
        )
        + sum(len(cast("list[Any]", n.get("on_enter") or [])) for n in nodes),
    )


# --------------------------------------------------------------------------
# Merge-seam narration
# --------------------------------------------------------------------------

_ROUTE_NOUNS: Final[str] = (
    r"(?:paths?|routes?|roads?|ways?|threads?|trails?|passages?|descents?"
    r"|approach(?:es)?|directions?|corridors?|tunnels?)"
)

# Verbs that put the clause after a concessive opener into the reader's
# HISTORY: how they got here, what they found, which they chose. Without one,
# "Whatever it was, it was big" and "Wherever she looked, there was dust" are
# ordinary in-scene narration; both shapes occur in the catalogue at
# non-merge nodes and would be false positives at a merge.
_HISTORY: Final[str] = (
    r"\b(?:had|has|have|came|come|got|gotten|reached|arrived|followed|chose"
    r"|chosen|picked|took|taken|found|carried|learned|learnt|led|brought|used"
    r"|read|opened|managed|climbed|gone|went|made (?:her|his|their|your|my) way)\b"
)

# Sentence-initial concessive openers. "However" followed by a comma is the
# connective adverb ("However, the door held.") and is excluded; so is a
# mid-sentence "however," (the 13-16 gamebook's "Hold your pace and read each
# mark in turn, however, and you will keep the trail.").
_CONCESSIVE_OPENER: Final[re.Pattern[str]] = re.compile(
    (
        r"^(?P<cue>whichever|whatever|wherever|however(?!,)|no matter (?:which|how"
        r"|what|where)|whether)\b(?P<clause>[^.!?;:]{0,200}?),"
    ),
    re.IGNORECASE,
)
_EITHER_WAY: Final[re.Pattern[str]] = re.compile(
    r"^(?:either way|one way or (?:the )?other|one way or another)\b",
    re.IGNORECASE,
)
_MID_CONCESSIVE: Final[re.Pattern[str]] = re.compile(
    (
        rf"\b(?:no matter (?:which|how|what|where)|whichever (?:one|of them|{_ROUTE_NOUNS}))"
        rf"\b[^.!?]{{0,80}}(?:{_HISTORY}|\b\w+ed\b|\bto get\b)"
    ),
    re.IGNORECASE,
)
# "Every path had ended here", "All three ways brought Nia out", "Both routes
# across the savanna met". A quantified route noun followed by a verb of
# arrival or convergence.
_CONVERGENCE: Final[re.Pattern[str]] = re.compile(
    (
        rf"\b(?:every|each|all|both|either|the (?:two|three|four|five))"
        rf"(?:\s+[\w-]+){{0,4}}?\s+{_ROUTE_NOUNS}\b[^.!?]{{0,120}}?"
        r"\b(?:led|leads|brought|brings|ended|ends|met|meet|meets|gathered"
        r"|gathers|arrived|arrive|arrives|came|come|comes|delivered|pointed"
        r"|folded|converged|joined|agreed|knotted)\b"
    ),
    re.IGNORECASE,
)
# "Every wing of the museum had led Nia here", "The threads she had followed
# reconverged", "The threads knotted at last into a single truth".
_LED_HERE: Final[re.Pattern[str]] = re.compile(
    (
        r"\b(?:every|each|all|both)\b[^.!?]{0,60}\b(?:led|brought|delivered)\b"
        r"[^.!?]{0,20}\bhere\b"
        rf"|\bthe {_ROUTE_NOUNS} (?:she|he|they|you|[A-Z][a-z]+) (?:had |has )?"
        r"(?:followed|taken|chosen|picked)\b"
        rf"|\bthe {_ROUTE_NOUNS} (?:knot|knots|knotted|converge[ds]?|reconverge[ds]?"
        r"|came together|come together|merged?|joined)\b"
    ),
    re.IGNORECASE,
)
# "arrives at the same certainty from three different directions", "settles
# into the same small wrongness", "brought Nia to the same door in the end".
_SAME_DESTINATION: Final[re.Pattern[str]] = re.compile(
    (
        r"\b(?:from (?:two|three|four|five|several|many) (?:different )?directions"
        r"|different for each\b[^.!?]{0,80}\bsame"
        r"|(?:arrived?|arrives|ended|ends|led|leads|brought|brings|met|came|comes"
        r"|gathers|gathered|settles|settled|delivered)\b[^.!?]{0,60}\b(?:at|to|on"
        r"|into) the (?:very )?same\b)"
    ),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SeamHit:
    """One merge node whose opening erases the reader's route.

    Attributes:
        node_id: The merge node.
        inbound: Distinct nodes leading to it.
        cue: Which seam shape matched.
        sentence: The opening sentence that carries it.
    """

    node_id: str
    inbound: int
    cue: str
    sentence: str


def _opener_cue(sentence: str) -> str | None:
    """Return the concessive-opener seam a sentence starts with, or None."""
    opener = _CONCESSIVE_OPENER.search(sentence)
    if opener is None:
        return None
    cue = opener.group("cue").lower()
    clause = opener.group("clause")
    if cue == "whether":
        # "Whether she pulled the curtain back herself or only watched the
        # gap": the alternation is what makes it a route recap.
        alternation = re.search(r"\bor\b", clause, re.IGNORECASE)
        history = re.search(_HISTORY + r"|\w+ed\b", clause, re.IGNORECASE)
        return "whether ... or" if alternation and history else None
    if re.search(_HISTORY, clause, re.IGNORECASE) or re.search(
        rf"\b{_ROUTE_NOUNS}\b", clause, re.IGNORECASE
    ):
        return f"{cue.split()[0]} ..."
    return None


_SEAM_SHAPES: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (_EITHER_WAY, "either way"),
    (_MID_CONCESSIVE, "no matter which"),
    (_CONVERGENCE, "every path led here"),
    (_LED_HERE, "every path led here"),
    (_SAME_DESTINATION, "same destination"),
)


def _seam_cue(sentence: str) -> str | None:
    """Return the seam shape a sentence carries, or None."""
    cue = _opener_cue(sentence)
    if cue is not None:
        return cue
    return next(
        (name for pattern, name in _SEAM_SHAPES if pattern.search(sentence)), None
    )


def merge_seams(
    story: Mapping[str, Any], *, opening_sentences: int = _SEAM_OPENING
) -> list[SeamHit]:
    """Find merge nodes whose opening tells the reader the route did not matter.

    Args:
        story: Decoded filled-story JSON.
        opening_sentences: Narration sentences at the start of each merge node
            to scan. Two, because the defect sometimes takes a beat to land:
            "The way down had been different for each of them, but it ended in
            the same place. Every thread Rowan had followed brought her here."

    Returns:
        One hit per offending merge node, in node order, carrying the first
        sentence that matched.
    """
    # #ASSUME: data-integrity: the seam is an OPENING move at a node with 2+
    # distinct inbound nodes. The same phrasing mid-body or at a single-parent
    # node is not reported; calibration found none that read as a seam.
    # #VERIFY: test_validator_agency.py pins the non-merge and mid-body cases.
    inbound = inbound_sources(story)
    hits: list[SeamHit] = []
    for node in _nodes(story):
        node_id = str(node.get("id"))
        sources = inbound.get(node_id, frozenset())
        if len(sources) < 2:
            continue
        opening = split_sentences(narration_of(str(node.get("body") or "")))
        for sentence in opening[: max(opening_sentences, 0)]:
            cue = _seam_cue(sentence)
            if cue is not None:
                hits.append(SeamHit(node_id, len(sources), cue, sentence))
                break
    return hits


# --------------------------------------------------------------------------
# Option recap
# --------------------------------------------------------------------------

_SUBJECT: Final[str] = r"(?:she|he|they|you|we|i|it|[A-Z][a-z]+)"
_MODAL: Final[str] = r"(?:could|can|might|may|should|would)"

# A sentence opening "Or" that carries a modal: "Or she could let her fear win
# out", "Or should they focus fully on saving the station?". A bare "Or"
# sentence ("Or so she thought.") is not a restated option.
_OR_SENTENCE: Final[re.Pattern[str]] = re.compile(
    rf"^or\b,?[^.!?]*\b{_MODAL}\b",
    re.IGNORECASE,
)
_MODAL_WORD: Final[re.Pattern[str]] = re.compile(rf"\b{_MODAL}\b", re.IGNORECASE)
_CLAUSE_BREAK: Final[re.Pattern[str]] = re.compile(
    r"[,;:]|\b(?:or|and|but|whether)\b", re.IGNORECASE
)
_SOFTENER: Final[re.Pattern[str]] = re.compile(
    r"^(?:else|maybe|perhaps|then|instead|so|just as easily)\s+", re.IGNORECASE
)
_INVERTED_AGENT: Final[re.Pattern[str]] = re.compile(
    r"(?:she|he|they|you|we|i|[A-Z][a-z]+)\b"
)
# Subjects that make a modal epistemic ("it might mean nothing at all", "the
# old wood might have gone soft", "her nerve would fail") rather than an
# option the protagonist could take.
_THING_SUBJECTS: Final[frozenset[str]] = frozenset({"it", "that", "this", "there"})
_THING_DETERMINERS: Final[tuple[str, ...]] = (
    "it ",
    "the ",
    "its ",
    "that ",
    "this ",
    "her ",
    "his ",
    "their ",
    "a ",
    "an ",
)


def _has_agent_modal(sentence: str) -> bool:
    """Return True when a modal in the sentence offers the protagonist an act.

    Calibration found an epistemic false-positive class: "The carving might
    mean something, or it might mean nothing at all", "It could wait, or it
    could not", "Or the old wood might have gone soft". Those weigh a
    possibility; they do not restate a button. A modal counts only when its
    subject is a person (a pronoun, a name, an elided subject carried over
    from the previous clause) or a gerund ("Taking her hand at once might
    carry her through"), never ``it`` or a determiner-led noun phrase. The
    cost is knowingly paid in recall: "It could be in the trunk. Or it could
    be out in his radio shed" restates two options through possibility and is
    not reported.
    """
    stripped = sentence.rstrip()
    for match in _MODAL_WORD.finditer(sentence):
        after = sentence[match.end() :].lstrip()
        if stripped.endswith("?") and _INVERTED_AGENT.match(after):
            return True
        clause = _CLAUSE_BREAK.split(sentence[: match.start()])[-1].strip()
        clause = _SOFTENER.sub("", clause).strip()
        lowered = clause.lower()
        if not clause:
            # "She can force it or could wait": the subject is elided and
            # carried over from a clause that already named the person.
            return True
        if lowered in _THING_SUBJECTS or lowered.startswith(_THING_DETERMINERS):
            continue
        return True
    return False


_NOT_A_VERB: Final[str] = (
    r"(?:the|a|an|her|his|their|its|my|your|our|some|any|maybe|perhaps|not|so"
    r"|what|whatever|who|whoever|which|where|when|how|why|else|even|at|in|on"
    r"|to|with|by|for|from|into|just|only|both|either|neither|nothing|nobody"
    r"|someone|something|anything|that|this|these|those|more|less|it|them|him"
    r"|me|us|you|she|he|they|we|i)"
)
# One sentence carrying both options: "She could X, or she could Y", "Wren
# could creep along the catwalk, or dash straight across", "She can climb
# toward the source or dig for it at ground level instead", "She could either
# X or Y".
_INLINE_ALTERNATIVE: Final[re.Pattern[str]] = re.compile(
    (
        rf"\b{_MODAL}\b[^.!?]{{3,200}}?(?:,\s*or\b[^.!?]*\b{_MODAL}\b"
        rf"|\bor\s+(?:else\s+)?(?:{_SUBJECT}\s+)?{_MODAL}\b"
        rf"|\bor\b[^.!?]{{0,120}}\binstead\b)"
        rf"|\b{_MODAL} either\b[^.!?]{{3,}}\bor\b"
        rf"|^either {_SUBJECT} {_MODAL}\b[^.!?]{{3,}}\bor\b"
        # "They could put their weight into the stiff side door, or take the
        # harder route", "You can lead them across, split the party, or send
        # scouts": a comma, "or", and a bare lowercase word that is not a
        # determiner, pronoun, preposition, or wh-word, which in this position is
        # the second option's verb. "She could see the lighthouse, or what was
        # left of it" and "ask Gran, or her friend" are excluded by the list.
        rf"|\b{_MODAL}\b[^.!?]{{3,200}}?,\s*or\s+(?!{_NOT_A_VERB}\b)[a-z]+\b"
    ),
    re.IGNORECASE,
)
# A sentence that opens with "Or" and closes with a question mark offers the
# second option as a question, as in the 5-8 lantern book's two-question close.
_OR_QUESTION: Final[re.Pattern[str]] = re.compile(r"^or\b[^?]*\?$", re.IGNORECASE)
# Announcing that a choice is due. "pick (her|his) way" is the idiom for
# moving carefully ("Wren had to pick her way fast"), not a choice, and is
# excluded by the lookahead.
_ANNOUNCE: Final[re.Pattern[str]] = re.compile(
    (
        r"\b(?:had|has|have|needed|needs|need)\s+(?:a|one|another|the)\s+"
        r"(?:choice|decision)\s+to\s+make\b"
        r"|\b(?:had|has|have|needs?|needed)\s+to\s+(?:choose|decide"
        r"|pick(?!\s+(?:her|his|their|its|your|my)\s+way))\b"
        r"|\b(?:only|just)\s+(?:a\s+moment|a\s+second|seconds|moments|one\s+chance)"
        r"\s+to\s+(?:choose|decide)\b"
        r"|\b(?:both|the\s+two|all\s+three|all\s+four)\s+(?:choices|options)\b"
        r"|\bonly\s+one\s+of\s+(?:them|these|those)\b"
        r"|\b(?:the|this|that|her|his|their)\s+(?:choice|decision)\s+(?:was|is|has"
        r"|had|would|will|could|must)\b"
        r"|\bturning\s+the\s+choice\b"
        r"|\bweighs?\s+(?:her|his|their|your)\s+options\b"
        r"|\bwhichever\s+(?:one\s+|place\s+|way\s+|path\s+)?(?:she|he|they|you|[A-Z][a-z]+)"
        r"\s+(?:picks|chooses|takes|decides)\b"
        # Deliberation narrated outright: "made up her mind which to visit",
        # "She thought hard about which", "unsure which would tell her more",
        # "weighed the sleeping butterflies against the busy little beetles".
        # "weighed the stone in her hand" has no "against" and is not matched.
        r"|\bmade\s+up\s+(?:her|his|their|your|my)\s+mind\b"
        r"|\b(?:thought\s+hard\s+about|wondered|unsure|not\s+sure)\s+which\b"
        r"|\bweigh(?:s|ed|ing)?\b[^.!?]{1,80}\bagainst\b"
        r"|\btime\s+to\s+weigh\b"
        # Imperative to the reader ("Choose your way in.") and the question form
        # ("Which would they take first?", "Which plan would work best?").
        r"|^(?:choose|decide|pick)\b"
        r"|^(?:which|what)\b[^.!?]{0,80}\b(?:choose|pick|take|try|do|work|start"
        r"|follow|decide)\b[^.!?]*\?$"
    ),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RecapHit:
    """One decision node whose close restates or announces its options.

    Attributes:
        node_id: The decision node.
        kinds: ``enumerates`` (the options are restated) and/or ``announces``
            (the narration says a choice is due), in that order.
        sentence: The first tail sentence that matched.
    """

    node_id: str
    kinds: tuple[str, ...]
    sentence: str


def option_recaps(
    story: Mapping[str, Any], *, tail_sentences: int = _RECAP_TAIL
) -> list[RecapHit]:
    """Find decision nodes whose closing narration restates their buttons.

    Args:
        story: Decoded filled-story JSON.
        tail_sentences: Closing narration sentences of each decision node to
            scan. The defect is the prose immediately above the buttons.

    Returns:
        One hit per offending decision node, in node order.
    """
    # #ASSUME: data-integrity: restated options are spelled with a modal and an
    # alternation ("could X. Or could Y") and announced choices with a small
    # closed vocabulary. Purely descriptive staging ("One stair climbed toward
    # the sky. One led down to the engines.") is the setup the buttons need and
    # is deliberately NOT matched, so recall is knowingly partial.
    # #VERIFY: test_validator_agency.py pins the staging case as a non-hit.
    hits: list[RecapHit] = []
    for node in _nodes(story):
        if _is_ending(node) or not _is_decision(node):
            continue
        sentences = split_sentences(narration_of(str(node.get("body") or "")))
        tail = sentences[-tail_sentences:] if tail_sentences > 0 else []
        enumerates = [
            s
            for s in tail
            if _OR_QUESTION.search(s)
            or (
                (_OR_SENTENCE.search(s) or _INLINE_ALTERNATIVE.search(s))
                and _has_agent_modal(s)
            )
        ]
        announces = [s for s in tail if _ANNOUNCE.search(s)]
        if not enumerates and not announces:
            continue
        kinds = tuple(
            kind
            for kind, found in (("enumerates", enumerates), ("announces", announces))
            if found
        )
        first = next(s for s in tail if s in enumerates or s in announces)
        hits.append(RecapHit(str(node.get("id")), kinds, first))
    return hits


# --------------------------------------------------------------------------
# Label defects
# --------------------------------------------------------------------------

# A label naming a mental act instead of an action in the story. Deliberately
# narrow, calibrated against every label in the catalogue:
#   * "Decide to go", "Decide the ledge is too risky and back out": the
#     decision wraps a real action, so "decide to" and any label carrying a
#     second clause ("and", "then") are excluded.
#   * "Think up a rescue plan" (5-8): naming the plan the next scene acts on;
#     "think up" is excluded, "think about/over/through" is not.
#   * "Sit with Gran and let the tide finish", "Sit with the silent drover
#     table", "Sit with the dining-car regulars": physical company, so "sit
#     with" counts only before an abstract or a written object.
#   * "Trust", "Accept", "Admit", "Feel", "Let": commitments with consequences
#     in the story ("Trust the cracked rung"), not reflection.
_MENTAL_NOUNS: Final[str] = (
    r"(?:what|it|this|that|the (?:weight|news|truth|meaning|feeling|question"
    r"|thought|idea|memory|loss|grief|silence|moment)|(?:[\w']+\s+){0,4}"
    r"(?:note|message|letter|drawing|words|news|story|thought|idea|question"
    r"|memory|loss|grief|silence))"
)
_META_LABEL: Final[re.Pattern[str]] = re.compile(
    (
        rf"^(?:sit with {_MENTAL_NOUNS}"
        rf"|take in {_MENTAL_NOUNS}"
        r"|decide(?! to\b)\b"
        r"|weigh\b|ponder\b|reflect\b|consider\b|contemplate\b|mull\b|wonder\b"
        r"|think (?:about|over|through|it|of)\b"
        r"|let (?:it|this|that) sink in\b"
        r"|choose (?:which|what|how|whether|who|an? (?:approach|option|plan|direction))\b)"
    ),
    re.IGNORECASE,
)
_COMPOUND: Final[re.Pattern[str]] = re.compile(r"\b(?:and|then)\b", re.IGNORECASE)

# Graph vocabulary in a story label. "branch", "path", "fork", "route",
# "thread", "page", "story", "try again", "start over", and "turn to" were all
# measured and excluded: every catalogue use is in-world ("Follow the downward
# branch", "Read the last log page", "Float back and try again" in a 3-5
# try-again loop, "Double back and start over" in a maze, "Turn to the great
# spring").
_JARGON_LABEL: Final[re.Pattern[str]] = re.compile(
    (
        r"\b(?:hubs?|nodes?|endings?|chapters?|restart|(?:go|turn|skip) to "
        r"(?:page|section|paragraph)|(?:page|section|paragraph) \d+"
        r"|(?:the )?(?:start|beginning) of the (?:story|book))\b"
    ),
    re.IGNORECASE,
)

# "thank-you" (a noun: "Go collect Auntie Mo's thank-you.") and "thank you"
# are courtesy formulas, not the narrator addressing the reader.
_SECOND_PERSON_LABEL: Final[re.Pattern[str]] = re.compile(
    r"(?<!thank-)(?<!thank )\b(?:you|your|yours|yourself|yourselves)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BookPerson:
    """The narrative person a book is held to, and why.

    Attributes:
        person: ``second`` or ``third``.
        source: How it was decided: the declaration, the gamebook style, or
            the measured second-person rate.
    """

    person: str
    source: str


def book_person(story: Mapping[str, Any]) -> BookPerson:
    """Decide which person a book's labels should agree with.

    Mirrors ``prose_craft.judge_person``'s precedence: a gamebook is second
    person by genre whatever its metadata says; a declared person wins next;
    an undeclared prose book is inferred from its narration with the same
    second-person floor the person gate applies to a declared-second book.

    Args:
        story: Decoded filled-story JSON.

    Returns:
        BookPerson: The person and the reason.
    """
    metadata = cast("dict[str, Any]", story.get("metadata") or {})
    declared = str(metadata.get("narrative_person") or "")
    style = str(metadata.get("narrative_style") or "")
    if style == "gamebook":
        return BookPerson("second", "gamebook style")
    if declared in {"second", "third"}:
        return BookPerson(declared, "declared")
    # #ASSUME: data-integrity: no committed book declares narrative_person
    # (2026-11-20), so this inference decides every prose book. Measured
    # rates split cleanly: third-person prose 0.0-0.27, second-person
    # 0.715-1.0, nothing between, so the 0.5 floor is not a near call.
    # #VERIFY: test_validator_agency.py pins both sides of the floor.
    rate = person_report(story).rate
    inferred = "second" if rate >= MIN_GAMEBOOK_SECOND_PERSON else "third"
    return BookPerson(inferred, f"inferred, {rate:.0%} of narration nodes say you")


@dataclass(frozen=True)
class LabelHit:
    """One defective choice label.

    Attributes:
        node_id: The node carrying the choice.
        choice_id: The choice.
        label: The label text.
    """

    node_id: str
    choice_id: str
    label: str


@dataclass(frozen=True)
class LabelDefects:
    """The three label-defect sub-kinds, reported separately.

    Attributes:
        meta: Labels naming a mental act instead of an action.
        jargon: Labels carrying graph vocabulary.
        second_person: Second-person labels in a third-person book.
        person: The person the book was held to.
    """

    meta: list[LabelHit]
    jargon: list[LabelHit]
    second_person: list[LabelHit]
    person: BookPerson


def label_defects(story: Mapping[str, Any]) -> LabelDefects:
    """Find meta, jargon, and wrong-person choice labels.

    Args:
        story: Decoded filled-story JSON.

    Returns:
        LabelDefects: Every hit per sub-kind, in node then choice order. A
        label can appear under more than one sub-kind ("Feel your way to the
        hub." is both jargon and second person in a third-person book).
    """
    person = book_person(story)
    meta: list[LabelHit] = []
    jargon: list[LabelHit] = []
    second: list[LabelHit] = []
    for node in _nodes(story):
        node_id = str(node.get("id"))
        for choice in _choices(node):
            label = str(choice.get("label") or "").strip()
            if not label:
                continue
            hit = LabelHit(node_id, str(choice.get("id") or "?"), label)
            if _META_LABEL.search(label) and not _COMPOUND.search(label):
                meta.append(hit)
            if _JARGON_LABEL.search(label):
                jargon.append(hit)
            # Quoted speech inside a label ('Ask "Are you lost?"') is a
            # character speaking, so it is stripped before the person test.
            if person.person == "third" and _SECOND_PERSON_LABEL.search(
                strip_quoted(label)
            ):
                second.append(hit)
    return LabelDefects(meta, jargon, second, person)


# --------------------------------------------------------------------------
# Give-up and early setback endings
# --------------------------------------------------------------------------

# Each pattern names a way the hero leaves or quits. Matched only in the
# closing sentences of NEGATIVE endings: a 3-5 book whose happy ending is
# "She went back home. She was happy and tired." is a bedtime close, and the
# neutral "Home went a page of underground sky" discovery endings of the
# 10-13 mapmaker book are consolation rather than surrender.
_GIVE_UP_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    (
        (
            r"\b(?:walk|walks|walked|walking|bike|bikes|biked|biking|head|heads"
            r"|headed|trudge|trudges|trudged|go|goes|went|going|ride|rides|rode"
            r"|return|returns|returned|sent|turn|turns|turned)\b[^.!?]{0,40}"
            r"\bhome\b|\b(?:long|slow) (?:walk|trudge|ride|way) home\b"
            r"|\btrudge home\b"
        ),
        "goes home",
    ),
    (r"\bturn(?:s|ed)? (?:her|his|their|your) steps\b", "goes home"),
    # "gives up its dead" (a station giving up bodies) is not quitting.
    (
        r"\b(?:gave|give|gives|giving) up\b(?!\s+(?:its|their)\b)",
        "gives up",
    ),
    (
        (
            r"\b(?:turn|turns|turned|turning|head|heads|headed) back\b"
            r"|\bback the way (?:she|he|they|you|i|we) had come\b"
            r"|\bretreat(?:s|ed)?\b|\bwalk(?:s|ed)? away\b"
        ),
        "turns back",
    ),
    (
        (
            r"\b(?:another|some other) (?:day|night|time|morning)\b|\bsomeday\b"
            r"|\bnext time\b|\bfor (?:now|tonight|today)\b"
        ),
        "defers",
    ),
    (r"\btoo (?:risky|dangerous)\b", "too risky"),
    (r"\b(?:gone|went|goes) cold\b", "trail gone cold"),
    (r"\bcall(?:s|ed)? it a night\b", "calls it a night"),
)
# "with no way onward and no time left to turn back" (the 13-16 gamebook's
# dead-end endings) negates the move it names: the hero is trapped, not
# quitting. Any sentence carrying such a negation contributes no give-up cue.
_NEGATED_RETREAT: Final[re.Pattern[str]] = re.compile(
    r"\bno (?:time|way|chance|room)(?: left)? to (?:turn|head|go) (?:back|home)\b",
    re.IGNORECASE,
)
_GIVE_UP_COMPILED: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in _GIVE_UP_PATTERNS
)


@dataclass(frozen=True)
class EndingHit:
    """One negative ending flagged as a give-up close or an early setback.

    Attributes:
        node_id: The ending node.
        reason: The give-up shape matched, or ``early`` for an early setback.
        detail: The matching sentence, or the decision count for an early
            setback.
        decisions: Fewest decisions to reach the ending, None if unreachable.
    """

    node_id: str
    reason: str
    detail: str
    decisions: int | None


def _negative_endings(story: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the ending nodes whose valence is negative."""
    return [n for n in _nodes(story) if _is_ending(n) and _valence(n) == "negative"]


def give_up_endings(
    story: Mapping[str, Any], *, tail_sentences: int = _GIVE_UP_TAIL
) -> list[EndingHit]:
    """Find negative endings whose close has the hero leave or quit.

    Args:
        story: Decoded filled-story JSON.
        tail_sentences: Closing narration sentences of each negative ending to
            scan.

    Returns:
        One hit per offending ending, in node order, under the first shape
        that matched.
    """
    depth = decisions_to_reach(story)
    hits: list[EndingHit] = []
    for node in _negative_endings(story):
        node_id = str(node.get("id"))
        sentences = split_sentences(narration_of(str(node.get("body") or "")))
        tail = sentences[-tail_sentences:] if tail_sentences > 0 else []
        found = next(
            (
                (reason, sentence)
                for sentence in tail
                if not _NEGATED_RETREAT.search(sentence)
                for pattern, reason in _GIVE_UP_COMPILED
                if pattern.search(sentence)
            ),
            None,
        )
        if found is not None:
            hits.append(EndingHit(node_id, found[0], found[1], depth.get(node_id)))
    return hits


def early_setbacks(
    story: Mapping[str, Any],
    *,
    max_decisions: int = DEFAULT_EARLY_SETBACK_DECISIONS,
) -> list[EndingHit]:
    """Find negative endings a reader can reach within very few decisions.

    Args:
        story: Decoded filled-story JSON.
        max_decisions: Highest decision count still counted as early.

    Returns:
        One hit per early negative ending, in node order.
    """
    depth = decisions_to_reach(story)
    hits: list[EndingHit] = []
    for node in _negative_endings(story):
        node_id = str(node.get("id"))
        reached = depth.get(node_id)
        if reached is not None and reached <= max_decisions:
            hits.append(EndingHit(node_id, "early", f"{reached} decisions", reached))
    return hits


# --------------------------------------------------------------------------
# Book report
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AgencyReport:
    """Every agency measure for one book, plus its headline.

    Attributes:
        merge_nodes: Nodes with 2+ distinct inbound nodes.
        decision_nodes: Non-ending nodes with 2+ distinct targets.
        state: Declared variables, conditions, and effects.
        seams: Merge nodes opening with route-erasing narration.
        recaps: Decision nodes closing by restating or announcing options.
        labels: The three label-defect sub-kinds.
        give_ups: Negative endings closing on the hero leaving or quitting.
        early: Negative endings within ``early_decisions`` decisions.
        early_decisions: The decision ceiling ``early`` was measured at.
        negative_endings: Endings with negative valence.
        endings: All endings.
    """

    merge_nodes: int
    decision_nodes: int
    state: StateCounts
    seams: list[SeamHit]
    recaps: list[RecapHit]
    labels: LabelDefects
    give_ups: list[EndingHit]
    early: list[EndingHit]
    early_decisions: int
    negative_endings: int
    endings: int

    @property
    def headline(self) -> str:
        """Return the agency picture as one sentence a non-engineer can read."""
        if self.merge_nodes:
            merges = (
                f"{self.merge_nodes} merge nodes, {len(self.seams)} of them tell "
                "the reader the route did not matter"
            )
        else:
            merges = "no merge nodes (every route stays separate)"
        if self.state.stateless:
            state = f"{self.state.variables} variables, so no choice comes back"
        else:
            state = (
                f"{self.state.variables} variables and "
                f"{self.state.conditional_choices} conditional choices carry "
                "earlier choices forward"
            )
        recaps = (
            f"{len(self.recaps)} of {self.decision_nodes} decisions restate or "
            "announce their options"
        )
        endings = (
            f"{len(self.give_ups)} of {self.negative_endings} setback endings "
            f"have the hero give up, {len(self.early)} come within "
            f"{self.early_decisions} decisions"
        )
        return f"{merges}; {state}; {recaps}; {endings}."


def agency_report(
    story: Mapping[str, Any],
    *,
    early_decisions: int = DEFAULT_EARLY_SETBACK_DECISIONS,
) -> AgencyReport:
    """Run every agency detector over one book.

    Args:
        story: Decoded filled-story JSON.
        early_decisions: Decision ceiling for :func:`early_setbacks`.

    Returns:
        AgencyReport: The counts, the hits, and the headline.
    """
    nodes = _nodes(story)
    inbound = inbound_sources(story)
    return AgencyReport(
        merge_nodes=sum(1 for srcs in inbound.values() if len(srcs) >= 2),
        decision_nodes=sum(1 for n in nodes if not _is_ending(n) and _is_decision(n)),
        state=state_counts(story),
        seams=merge_seams(story),
        recaps=option_recaps(story),
        labels=label_defects(story),
        give_ups=give_up_endings(story),
        early=early_setbacks(story, max_decisions=early_decisions),
        early_decisions=early_decisions,
        negative_endings=len(_negative_endings(story)),
        endings=sum(1 for n in nodes if _is_ending(n)),
    )
