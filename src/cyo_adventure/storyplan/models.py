"""Story Plan schema v0 (ADR-033 Decision 1, work package WP-1.1).

A Story Plan is one JSON document per book. It is written before prose (or,
for a hand-revised catalog book, by reading the book) and it is what the
structural checks in :mod:`cyo_adventure.storyplan.checks` read. The reader app
never loads it; the Storybook schema does not reference it (ADR-025 untouched).

This module is pure: Pydantic models, one hash function, no I/O.

Shape choices
=============

ADR-033 Decision 1 names the sections and their contents. Where it is specific
this schema follows it; where it is not, the simplest shape that makes the
checks exact set operations was chosen. Every such choice is listed here and in
the WP-1.1 notes of ``docs/planning/story-plan-implementation-plan.md``.

1. **Sections keyed by id are JSON objects, not arrays.** ``cast``, ``facts``,
   ``nodes``, ``choices``, ``threads`` and ``endings`` are objects whose keys
   are ids. Uniqueness is then free, and SP-1 coverage is a set comparison of
   keys. This matches the August narrative contracts
   (``skeletons/*/*.narrative.json``), which key ``facts`` and ``nodes`` the
   same way.
2. **Node and choice ids are the book's ids**, verbatim (ADR-033: "Node ids and
   choice ids are shared"). They are only required to be non-empty, matching
   the Storybook, so any valid book can be planned. Fact, thread and cast ids
   use the Storybook variable pattern ``^[a-z][a-z0-9_]*$``.
3. **A fact is an object** ``{"text": ..., "contradicts": [...]}``. ``text`` is
   the one sentence the ADR asks for. ``contradicts`` is how a fact is "marked
   as contradicting" for SP-3; it is read symmetrically, so marking one side of
   a pair is enough. Facts are monotone: once established on a route a fact
   stays established (a reader cannot un-learn it). Nothing retracts a fact.
4. **``truth`` is** ``{"question", "answer", "facts"}``: the book's question,
   its one canonical answer in a sentence, and the non-empty list of ledger
   fact ids that make up that answer. SP-3 requires each to be established on
   some reachable route and forbids any fact contradicting it from being
   established anywhere. Truth facts may not contradict each other.
5. **Nodes carry** ``function``, ``event``, ``requires``, ``establishes``
   exactly as the ADR names them. ``requires`` is what the node's prose
   presupposes the reader already knows **on entry**; ``establishes`` is what
   the prose adds. A fact stated in a choice label counts as established by the
   node that offers the choice, because every reader at that node sees the
   label. ``must_not_assert`` is never authored; it is computed by
   :func:`cyo_adventure.storyplan.checks.must_not_assert`.
6. **Choices carry** ``intent`` and ``cost`` (both required, per the ADR) and an
   optional ``plants``: the ids of the threads this choice plants. A choice
   that plants nothing omits it. ``cost`` is short free text; ``"none"`` is a
   legitimate cost for the safe or continue option. SP-8 compares costs after
   case-folding, whitespace collapsing and trailing-punctuation stripping, so
   two costs differ only if their words differ.
7. **Threads carry** ``variable`` (the Storybook variable the thread drives),
   ``planted_fact`` (the ledger fact that is the concrete thing planted),
   ``planted_by`` (the planting choices: a list, because a hand-revised book
   may set one variable from several choices) and ``payoffs``. The ADR names
   both a thread's planting choice and a choice's ``plants``; both are kept and
   must agree exactly: choice ``c`` lists thread ``t`` in ``plants`` if and only
   if ``t.planted_by`` contains ``c``. This is deliberate double entry, so a
   hand-written plan that edits one side and forgets the other is rejected at
   load rather than silently mis-checked. Traversing a planting choice
   establishes the thread's ``planted_fact`` on entry to the choice's target.
8. **A payoff is** ``{"site", "node", "shows"}``. ``site`` is the node where
   readers with and without the plant both arrive (SP-5 measures reach there);
   ``node`` is the passage that shows the payoff, usually the target of a
   choice at ``site`` that only planted readers see (SP-6 checks its
   requirements). ``node`` may equal ``site``. ``shows`` is one sentence.
   Without conditional passage text (deferred by ADR-033), a payoff needs an
   arrival node distinct from the shared site, which is why both are named.
9. **``endings`` is keyed by ending node id** (not by the Storybook's ``Ending.id``),
   because node ids are the shared key. Each entry holds a required ``gift``.
   SP-7 requires an entry for every negative-valence ending; entries for other
   endings are allowed.
10. **``request.band`` is required; every other request field is optional.**
    A hand-revised catalog book has no request text. When present, the text is
    untrusted and is exempt from SP-9's floors (it is screened upstream and
    fenced wherever it is reused); every other plan string is floored.
11. **``provenance`` carries the shape binding**: ``shape_id`` (the skeleton
    slug, or the book id for a hand-revised book, which has no separate shape)
    and ``shape_hash`` (:func:`shape_hash` of the book's graph, ``null`` until
    first bound). SP-0 fails an unbound or stale plan. ``checks`` records the
    summary of the last check run; ``approver`` who approved the plan.
12. **``plan_version`` is** ``MAJOR.MINOR``, additive within a major (ADR-025's
    rule). This build writes ``0.1`` and reads any ``0.x`` with ``x <= 1``.
    ``0.0`` was skipped so an unset or defaulted version is never mistaken for
    a real one.

What this schema enforces at load (:class:`StoryPlan` validation)
----------------------------------------------------------------

Unknown keys anywhere (``extra="forbid"``); every fact id referenced by a node,
cast member, truth, contradiction or thread is declared in ``facts``; every
node id referenced by a payoff or ``endings`` is a key of ``nodes``; every
planting choice is a key of ``choices``; every thread a choice plants exists;
the ``plants``/``planted_by`` agreement; one thread per variable and per
planted fact; no duplicate entries in any id list; no self-contradiction; no
contradiction among truth facts; a supported ``plan_version``.

What is checked against the book, not here: that the plan's node and choice ids
are exactly the book's, and that each thread's variable is declared in the book
and set by exactly its planting choices. The plan does not own variable
declarations (the Storybook does, and ADR-033 leaves it unchanged), so "a
thread naming an undeclared variable" is an SP-1 error from
:func:`cyo_adventure.storyplan.checks.check_plan` rather than a load error.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from cyo_adventure.storybook.models import (
    AgeBand,
    Length,
    NarrativeStyle,
    is_supported_schema_version,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cyo_adventure.storybook.models import Storybook

PLAN_MAJOR = 0
PLAN_MINOR = 1
PLAN_VERSION = f"{PLAN_MAJOR}.{PLAN_MINOR}"

SHAPE_HASH_PREFIX = "sha256:"

Ident = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
"""A fact, thread or cast id: the Storybook variable-name pattern."""

BookId = Annotated[str, StringConstraints(min_length=1)]
"""A node or choice id, verbatim from the book (the Storybook only requires non-empty)."""

Text = Annotated[str, StringConstraints(min_length=1)]
"""A plan string. Length, charset and denylist floors are SP-9's job, not the schema's."""


def is_supported_plan_version(value: object) -> bool:
    """Report whether this build can read a plan at ``value``.

    Args:
        value: The raw ``plan_version`` value, of any type.

    Returns:
        bool: True for a ``MAJOR.MINOR`` string of the same major and a minor at
            or below :data:`PLAN_MINOR`.
    """
    return is_supported_schema_version(value, major=PLAN_MAJOR, minor=PLAN_MINOR)


class _Strict(BaseModel):
    """Base for every plan model: unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")


class PlanRequest(_Strict):
    """The request the book answers. ``text`` is untrusted when present."""

    text: str | None = None
    band: AgeBand
    length: Length | None = None
    style: NarrativeStyle | None = None
    tone: Text | None = None


class Pitch(_Strict):
    """The five-field pitch the owner reads for a catalog book."""

    hero: Text
    want: Text
    obstacle: Text
    stake: Text
    ending_kind: Text


class CastMember(_Strict):
    """One character: role, want, voice notes and what they know (fact ids)."""

    name: Text
    role: Text
    want: Text
    voice: Text
    knows: list[Ident] = Field(default_factory=list)


class Truth(_Strict):
    """The book's question and its one canonical answer."""

    question: Text
    answer: Text
    facts: list[Ident] = Field(min_length=1)


class Fact(_Strict):
    """One ledger fact: a sentence plus the facts it contradicts."""

    text: Text
    contradicts: list[Ident] = Field(default_factory=list)


class NodePlan(_Strict):
    """A node's obligations: what happens, what it presupposes and adds."""

    function: Text
    event: Text
    requires: list[Ident] = Field(default_factory=list)
    establishes: list[Ident] = Field(default_factory=list)


class ChoicePlan(_Strict):
    """A choice's meaning: why a reader takes it, what it costs, what it plants."""

    intent: Text
    cost: Text
    plants: list[Ident] = Field(default_factory=list)


class Payoff(_Strict):
    """Where a thread returns: the shared site, the showing passage, and what it shows."""

    site: BookId
    node: BookId
    shows: Text


class Thread(_Strict):
    """A plant and its payoffs, bound to one Storybook variable."""

    variable: Ident
    planted_fact: Ident
    planted_by: list[BookId] = Field(min_length=1)
    payoffs: list[Payoff] = Field(min_length=1)


class EndingPlan(_Strict):
    """What an ending gives the reader: the reveal, the laugh, or the reason to retry."""

    gift: Text


class CheckRecord(_Strict):
    """Summary of the last structural check run recorded on a plan."""

    ok: bool
    errors: int = Field(ge=0)
    warnings: int = Field(ge=0)


class Provenance(_Strict):
    """Who produced the plan, from what shape, and who approved it."""

    producer: Text
    model: str | None = None
    shape_id: Text
    shape_hash: (
        Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")] | None
    ) = None
    checks: CheckRecord | None = None
    approver: str | None = None


def _duplicates(values: Iterable[str]) -> list[str]:
    """Return the values that occur more than once, in first-repeat order.

    Args:
        values: The ids to scan.

    Returns:
        list[str]: Each repeated value once.
    """
    seen: set[str] = set()
    repeated: list[str] = []
    for value in values:
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    return repeated


class StoryPlan(_Strict):
    """A complete Story Plan (ADR-033 Decision 1). See the module docstring."""

    plan_version: str = PLAN_VERSION
    request: PlanRequest
    pitch: Pitch
    cast: dict[Ident, CastMember] = Field(min_length=1)
    truth: Truth
    facts: dict[Ident, Fact] = Field(min_length=1)
    nodes: dict[BookId, NodePlan] = Field(min_length=1)
    choices: dict[BookId, ChoicePlan] = Field(default_factory=dict)
    threads: dict[Ident, Thread] = Field(default_factory=dict)
    endings: dict[BookId, EndingPlan] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        """Enforce the plan's internal referential integrity.

        Every problem is collected and reported together, so a hand-written
        plan is fixed in one pass rather than one error at a time.

        Returns:
            Self: The validated plan.

        Raises:
            ValueError: Listing every integrity problem found.
        """
        problems: list[str] = []
        if not is_supported_plan_version(self.plan_version):
            supported = f"{PLAN_MAJOR}.0 to {PLAN_VERSION}"
            problems.append(
                f"unsupported plan_version {self.plan_version!r}; reads {supported}"
            )
        problems.extend(self._fact_reference_problems())
        problems.extend(self._contradiction_problems())
        problems.extend(self._node_and_choice_reference_problems())
        problems.extend(self._thread_problems())
        problems.extend(self._duplicate_problems())
        # #CRITICAL: data-integrity: every SP check indexes facts, nodes,
        # choices and threads by the ids referenced here; a dangling reference
        # admitted at load would surface later as a KeyError or, worse, as a
        # silently skipped obligation.
        # #VERIFY: test_storyplan_models.py rejects an undeclared fact, an
        # unknown node, an unknown planting choice and a one-sided plant.
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def _fact_reference_problems(self) -> list[str]:
        """Return a message per reference to an undeclared fact id.

        Returns:
            list[str]: The problems, in section order.
        """
        declared = set(self.facts)
        refs: list[tuple[str, str]] = []
        for node_id, node in self.nodes.items():
            refs.extend((f"nodes.{node_id}.requires", f) for f in node.requires)
            refs.extend((f"nodes.{node_id}.establishes", f) for f in node.establishes)
        for cast_id, member in self.cast.items():
            refs.extend((f"cast.{cast_id}.knows", f) for f in member.knows)
        refs.extend(("truth.facts", f) for f in self.truth.facts)
        for fact_id, fact in self.facts.items():
            refs.extend((f"facts.{fact_id}.contradicts", f) for f in fact.contradicts)
        for thread_id, thread in self.threads.items():
            refs.append((f"threads.{thread_id}.planted_fact", thread.planted_fact))
        return [
            f"{where} names undeclared fact {fact!r}"
            for where, fact in refs
            if fact not in declared
        ]

    def _contradiction_problems(self) -> list[str]:
        """Return problems with contradiction marks and the truth.

        Returns:
            list[str]: Self-contradictions and contradicting truth facts.
        """
        problems = [
            f"facts.{fact_id} contradicts itself"
            for fact_id, fact in self.facts.items()
            if fact_id in fact.contradicts
        ]
        pairs = self.contradiction_pairs()
        truth = sorted(set(self.truth.facts))
        problems.extend(
            f"truth facts {a!r} and {b!r} are marked as contradicting"
            for i, a in enumerate(truth)
            for b in truth[i + 1 :]
            if frozenset((a, b)) in pairs
        )
        return problems

    def _node_and_choice_reference_problems(self) -> list[str]:
        """Return a message per reference to a node or choice the plan lacks.

        Returns:
            list[str]: The problems, in section order.
        """
        problems = [
            f"endings.{node_id} is not a key of nodes"
            for node_id in self.endings
            if node_id not in self.nodes
        ]
        for thread_id, thread in self.threads.items():
            problems.extend(
                f"threads.{thread_id}.planted_by names unknown choice {choice_id!r}"
                for choice_id in thread.planted_by
                if choice_id not in self.choices
            )
            for index, payoff in enumerate(thread.payoffs):
                where = f"threads.{thread_id}.payoffs[{index}]"
                problems.extend(
                    f"{where}.{field} names unknown node {node_id!r}"
                    for field, node_id in (("site", payoff.site), ("node", payoff.node))
                    if node_id not in self.nodes
                )
        return problems

    def _thread_problems(self) -> list[str]:
        """Return thread uniqueness and plants/planted_by agreement problems.

        Returns:
            list[str]: The problems found.
        """
        problems: list[str] = []
        for label, values in (
            ("variable", [t.variable for t in self.threads.values()]),
            ("planted_fact", [t.planted_fact for t in self.threads.values()]),
        ):
            problems.extend(
                f"more than one thread has {label} {value!r}"
                for value in _duplicates(values)
            )
        for choice_id, choice in self.choices.items():
            for thread_id in choice.plants:
                thread = self.threads.get(thread_id)
                if thread is None:
                    problems.append(
                        f"choices.{choice_id}.plants names unknown thread {thread_id!r}"
                    )
                elif choice_id not in thread.planted_by:
                    problems.append(
                        f"choices.{choice_id}.plants: {thread_id!r}.planted_by omits it"
                    )
        for thread_id, thread in self.threads.items():
            problems.extend(
                f"threads.{thread_id}.planted_by: {choice_id!r}.plants omits it"
                for choice_id in thread.planted_by
                if choice_id in self.choices
                and thread_id not in self.choices[choice_id].plants
            )
        return problems

    def _duplicate_problems(self) -> list[str]:
        """Return a message per id list that repeats an entry.

        Returns:
            list[str]: The problems found.
        """
        lists: list[tuple[str, list[str]]] = [("truth.facts", self.truth.facts)]
        for node_id, node in self.nodes.items():
            lists.extend(
                (
                    (f"nodes.{node_id}.requires", node.requires),
                    (f"nodes.{node_id}.establishes", node.establishes),
                )
            )
        lists.extend(
            (f"cast.{cast_id}.knows", member.knows)
            for cast_id, member in self.cast.items()
        )
        lists.extend(
            (f"facts.{fact_id}.contradicts", fact.contradicts)
            for fact_id, fact in self.facts.items()
        )
        lists.extend(
            (f"choices.{choice_id}.plants", choice.plants)
            for choice_id, choice in self.choices.items()
        )
        lists.extend(
            (f"threads.{thread_id}.planted_by", thread.planted_by)
            for thread_id, thread in self.threads.items()
        )
        return [
            f"{where} repeats {value!r}"
            for where, values in lists
            for value in _duplicates(values)
        ]

    def contradiction_pairs(self) -> frozenset[frozenset[str]]:
        """Return every contradicting fact pair, read symmetrically.

        Returns:
            frozenset[frozenset[str]]: Unordered two-fact pairs; marking either
                side of a pair is enough.
        """
        return frozenset(
            frozenset((fact_id, other))
            for fact_id, fact in self.facts.items()
            for other in fact.contradicts
            if other != fact_id
        )

    def thread_facts_by_choice(self) -> dict[str, frozenset[str]]:
        """Return, per planting choice, the facts traversing it establishes.

        Returns:
            dict[str, frozenset[str]]: Choice id to the ``planted_fact`` of every
                thread the choice plants. Choices that plant nothing are absent.
        """
        planted: dict[str, set[str]] = {}
        for thread in self.threads.values():
            for choice_id in thread.planted_by:
                planted.setdefault(choice_id, set()).add(thread.planted_fact)
        return {choice_id: frozenset(facts) for choice_id, facts in planted.items()}


def shape_projection(book: Storybook) -> dict[str, object]:
    """Return the prose-free graph of a book, the part a plan is bound to.

    Kept: start node, variable declarations (name, type, initial, bounds), and
    per node its id, ending id, valence and kind, ``on_enter`` effects and per
    choice its id, target, condition and effects, all in book order. Dropped:
    every body, label, ending title, tag, safety scope, variable description
    and the metadata block. A fill or a prose edit therefore keeps the hash; any
    change to what a reader can reach, or under which state, changes it.

    Args:
        book: The parsed book or skeleton.

    Returns:
        dict[str, object]: The JSON-serialisable projection.
    """
    nodes: list[dict[str, object]] = [
        {
            "id": node.id,
            "ending": (
                None
                if node.ending is None
                else {
                    "id": node.ending.id,
                    "valence": node.ending.valence.value,
                    "kind": node.ending.kind.value,
                }
            ),
            "on_enter": [effect.model_dump(mode="json") for effect in node.on_enter],
            "choices": [
                {
                    "id": choice.id,
                    "target": choice.target,
                    "condition": choice.condition,
                    "effects": [e.model_dump(mode="json") for e in choice.effects],
                }
                for choice in node.choices
            ],
        }
        for node in book.nodes
    ]
    variables = [
        variable.model_dump(mode="json", exclude={"description"})
        for variable in book.variables
    ]
    return {"start_node": book.start_node, "variables": variables, "nodes": nodes}


def shape_hash(book: Storybook) -> str:
    """Return the content hash binding a plan to a book's graph.

    Args:
        book: The parsed book or skeleton.

    Returns:
        str: ``"sha256:"`` plus the hex digest of the canonical JSON of
            :func:`shape_projection`.
    """
    # #ASSUME: data-integrity: canonical JSON (sorted keys, fixed separators,
    # ASCII escapes) of a model_dump is byte-stable across runs and platforms,
    # so a plan bound once stays bound until the graph changes.
    # #VERIFY: test_storyplan_models.py asserts the hash ignores prose and
    # changes when a choice target changes.
    canonical = json.dumps(
        shape_projection(book), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return SHAPE_HASH_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
