# pyright: reportImplicitStringConcatenation=false
# Ruff ISC003 requires implicit concatenation for wrapped messages and this
# BasedPyright rule forbids it; the two conflict, and Ruff is the project's gate.
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
checks exact set operations was chosen, reconciled with the four WP-0.3 plans
written in parallel (``out/<slug>.plan.json`` on the batch branch), which this
schema accepts unchanged. Every choice is listed here and in the WP-1.1 notes of
``docs/planning/story-plan-implementation-plan.md``.

1. **Sections keyed by id are JSON objects, not arrays.** ``cast``, ``facts``,
   ``nodes``, ``choices``, ``threads`` and ``endings`` are objects whose keys
   are ids, so uniqueness is free and SP-1 coverage is a set comparison.
2. **Node and choice ids are the book's ids**, verbatim (ADR-033: "Node ids and
   choice ids are shared"), only required to be non-empty, as in the Storybook.
   Fact, thread and cast ids use the pattern ``^[a-z][a-z0-9_]*$``.
3. **A fact is** ``{"text", "contradicts"?}``. ``contradicts`` is how a fact is
   "marked as contradicting" for SP-3; it may be written on one side only and is
   read both ways. A negative statement ("she has no key") is a positive fact
   that contradicts its opposite; there is no negative ``requires``. A partial
   reveal is its own fact. Facts are monotone: once established on a route a
   fact stays established; nothing retracts one, so a state change is a new
   fact. A node may both require and establish a fact, so one merge defect is
   reported once rather than cascading downstream. ``implicit_plant`` is an
   optional note on a setup that has no variable; no rule reads it.
4. **``truth`` is** ``{"statement", "facts", "question"?}``: the one canonical
   answer in prose, the non-empty list of ledger facts that make it up, and
   optionally the question it answers. Truth facts may not contradict each
   other.
5. **Nodes carry** ``function``, ``event``, ``requires``, ``establishes``.
   ``requires`` is what the prose presupposes the reader knows **on entry**;
   ``establishes`` is what it adds. A fact stated in a choice label counts as
   established by the node offering it. ``must_not_assert`` is never authored;
   :func:`cyo_adventure.storyplan.checks.must_not_assert` computes it.
6. **Choices carry** ``intent`` and ``cost`` (required), and optionally
   ``requires`` (facts the label presupposes, checked against what is known on
   entry to the offering node plus that node's ``establishes``, only in states
   where the choice is visible; a plan may instead fold label presuppositions
   into the node's ``requires``), ``establishes`` (facts taking the choice
   establishes on entry to its target, for a setup with no variable) and
   ``plants``: the thread id, or list of thread ids, the choice plants. ``"none"`` is a valid cost. SP-8 compares
   costs case-folded with trailing punctuation stripped.
7. **Threads carry** ``variable`` (the Storybook variable), ``plant`` (the
   ledger fact that is the concrete thing planted), ``planting_choices`` (a
   list: a book may set one variable from several choices) and
   ``payoff_sites``. A choice's ``plants`` and the threads'
   ``planting_choices`` must agree exactly in both directions; the double entry
   is deliberate, so a plan that edits one side is rejected at load rather than
   silently mis-checked. Traversing a planting choice establishes the thread's
   ``plant`` on entry to its target.
8. **A payoff site is** ``{"node", "choice", "shows"}``: ``node`` is where
   readers with and without the plant both arrive (SP-5 measures reach there),
   ``choice`` is the choice at that node through which the payoff shows (it may
   be gated on the variable being true or false), ``shows`` one sentence. The
   passage that shows the payoff is the choice's target in the book, which is
   what SP-6 checks.
9. **``endings`` is keyed by ending node id** with a required ``gift`` and an
   optional ``valence`` and ``kind``, which SP-1 checks against the book when
   given. SP-7 requires an entry for every negative-valence ending.
10. **``request``**: ``band`` required; ``text``, ``length``, ``style``,
    ``tone``, ``note`` optional. ``text`` is untrusted when present.
11. **``book``** (optional): ``slug``, ``storybook_id``, ``storybook_version``,
    ``title``; SP-0 checks the id and version against the book.
12. **``provenance`` carries the binding**, one or both of: ``shape``
    (``{"id", "hash"}``, the hash being :func:`shape_hash` of the graph: ids,
    targets, conditions, effects, variables, ending valence and kind, so a
    prose edit keeps it) for a plan built from a shape; ``book_sha256`` (hex
    SHA-256 of the book file's bytes, so any edit makes the plan stale) for a
    hand-revised book, which has no shape. SP-0 fails a plan with neither, or
    with one that does not match. Also ``producer`` (required), ``model``,
    ``method``, ``book_file``, ``authored``, ``authoring_minutes``, ``checks``,
    ``approver``, and ``notes`` (free-form strings, such as continuity notes).
13. **``plan_version`` is** ``MAJOR.MINOR``, additive within a major (ADR-025's
    rule). This build writes ``0.1`` and reads ``0.0`` and ``0.1``.

What this schema enforces at load (:class:`StoryPlan` validation)
----------------------------------------------------------------

Unknown keys anywhere (``extra="forbid"``); every referenced fact id is
declared; every node id referenced by a payoff site or ``endings`` is a key of
``nodes``; every planting and payoff choice is a key of ``choices``; every
thread a choice plants exists; the ``plants``/``planting_choices`` agreement;
one thread per variable and per plant; no duplicate entries in any id list; no
self-contradiction; no contradiction among truth facts; a supported
``plan_version``.

What is checked against the book, not here (SP-0 and SP-1): that the plan's
node and choice ids are exactly the book's, that a payoff choice belongs to its
site node, and that each thread's variable is declared in the book and set by
exactly its planting choices. The plan does not own variable declarations (the
Storybook does), so "a thread naming an undeclared variable" is an SP-1 error
rather than a load error.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from cyo_adventure.storybook.models import (
    AgeBand,
    EndingKind,
    Length,
    NarrativeStyle,
    Valence,
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
"""A fact, thread or cast id."""

BookId = Annotated[str, StringConstraints(min_length=1)]
"""A node or choice id, verbatim from the book (the Storybook only requires non-empty)."""

Text = Annotated[str, StringConstraints(min_length=1)]
"""A plan string. Length, charset and denylist floors are SP-9's job, not the schema's."""


def _one_or_many(value: object) -> object:
    """Accept a bare id where a list of ids is expected.

    Args:
        value: The raw ``plants`` value.

    Returns:
        object: ``[value]`` for a string, ``value`` unchanged otherwise.
    """
    return [value] if isinstance(value, str) else value


ThreadRefs = Annotated[
    list[Ident],
    BeforeValidator(_one_or_many, json_schema_input_type=Ident | list[Ident]),
]
"""``plants``: one thread id or a list of them, held as a list."""


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


class BookRef(_Strict):
    """Which book the plan was written for."""

    slug: Text
    storybook_id: Text
    storybook_version: int = Field(ge=1)
    title: Text


class PlanRequest(_Strict):
    """The request the book answers. ``text`` is untrusted when present."""

    text: str | None = None
    band: AgeBand
    length: Length | None = None
    style: NarrativeStyle | None = None
    tone: Text | None = None
    note: str | None = None


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
    """The book's one canonical answer and the facts that make it up."""

    statement: Text
    facts: list[Ident] = Field(min_length=1)
    question: Text | None = None


class Fact(_Strict):
    """One ledger fact: a sentence plus the facts it contradicts."""

    text: Text
    contradicts: list[Ident] = Field(default_factory=list)
    implicit_plant: str | None = None


class NodePlan(_Strict):
    """A node's obligations: what happens, what it presupposes and adds."""

    function: Text
    event: Text
    requires: list[Ident] = Field(default_factory=list)
    establishes: list[Ident] = Field(default_factory=list)


class ChoicePlan(_Strict):
    """A choice's meaning: why, at what cost, what it presupposes and plants."""

    intent: Text
    cost: Text
    requires: list[Ident] = Field(default_factory=list)
    establishes: list[Ident] = Field(default_factory=list)
    plants: ThreadRefs = Field(default_factory=list)


class PayoffSite(_Strict):
    """Where a thread returns: the shared node, the choice that shows it, what it shows."""

    node: BookId
    choice: BookId
    shows: Text


class Thread(_Strict):
    """A plant and its payoffs, bound to one Storybook variable."""

    variable: Ident
    plant: Ident
    planting_choices: list[BookId] = Field(min_length=1)
    payoff_sites: list[PayoffSite] = Field(min_length=1)


class EndingPlan(_Strict):
    """What an ending gives the reader: the reveal, the laugh, or the reason to retry."""

    gift: Text
    valence: Valence | None = None
    kind: EndingKind | None = None


class CheckRecord(_Strict):
    """Summary of the last structural check run recorded on a plan."""

    ok: bool
    errors: int = Field(ge=0)
    warnings: int = Field(ge=0)


class ShapeRef(_Strict):
    """The shape a plan was built for, by id and graph hash."""

    id: Text
    hash: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


class Provenance(_Strict):
    """Who produced the plan, what it is bound to, and who approved it."""

    producer: Text
    model: str | None = None
    method: str | None = None
    shape: ShapeRef | None = None
    book_file: str | None = None
    book_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = (
        None
    )
    authored: date | None = None
    authoring_minutes: int | None = Field(default=None, ge=0)
    checks: CheckRecord | None = None
    approver: str | None = None
    notes: list[str] = Field(default_factory=list)


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
    book: BookRef | None = None
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
        for choice_id, choice in self.choices.items():
            refs.extend((f"choices.{choice_id}.requires", f) for f in choice.requires)
            refs.extend(
                (f"choices.{choice_id}.establishes", f) for f in choice.establishes
            )
        for cast_id, member in self.cast.items():
            refs.extend((f"cast.{cast_id}.knows", f) for f in member.knows)
        refs.extend(("truth.facts", f) for f in self.truth.facts)
        for fact_id, fact in self.facts.items():
            refs.extend((f"facts.{fact_id}.contradicts", f) for f in fact.contradicts)
        for thread_id, thread in self.threads.items():
            refs.append((f"threads.{thread_id}.plant", thread.plant))
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
                f"threads.{thread_id}.planting_choices names unknown choice {c!r}"
                for c in thread.planting_choices
                if c not in self.choices
            )
            for index, site in enumerate(thread.payoff_sites):
                where = f"threads.{thread_id}.payoff_sites[{index}]"
                if site.node not in self.nodes:
                    problems.append(f"{where}.node names unknown node {site.node!r}")
                if site.choice not in self.choices:
                    problems.append(
                        f"{where}.choice names unknown choice {site.choice!r}"
                    )
        return problems

    def _thread_problems(self) -> list[str]:
        """Return thread uniqueness and plants/planting_choices agreement problems.

        Returns:
            list[str]: The problems found.
        """
        problems: list[str] = []
        for label, values in (
            ("variable", [t.variable for t in self.threads.values()]),
            ("plant", [t.plant for t in self.threads.values()]),
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
                elif choice_id not in thread.planting_choices:
                    problems.append(
                        f"choices.{choice_id}.plants names {thread_id!r}, "
                        "whose planting_choices omit it"
                    )
        for thread_id, thread in self.threads.items():
            problems.extend(
                f"threads.{thread_id}.planting_choices lists {c!r}, "
                "whose plants omit the thread"
                for c in thread.planting_choices
                if c in self.choices and thread_id not in self.choices[c].plants
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
        for choice_id, choice in self.choices.items():
            lists.extend(
                (
                    (f"choices.{choice_id}.requires", choice.requires),
                    (f"choices.{choice_id}.establishes", choice.establishes),
                    (f"choices.{choice_id}.plants", choice.plants),
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
            (f"threads.{thread_id}.planting_choices", thread.planting_choices)
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

    def plants_by_choice(self) -> dict[str, frozenset[str]]:
        """Return, per choice, the facts traversing it establishes.

        Returns:
            dict[str, frozenset[str]]: Choice id to its own ``establishes`` plus
                the ``plant`` of every thread it plants. Choices that establish
                nothing are absent.
        """
        planted: dict[str, set[str]] = {
            choice_id: set(choice.establishes)
            for choice_id, choice in self.choices.items()
            if choice.establishes
        }
        for thread in self.threads.values():
            for choice_id in thread.planting_choices:
                planted.setdefault(choice_id, set()).add(thread.plant)
        return {choice_id: frozenset(facts) for choice_id, facts in planted.items()}


def book_sha256(raw: bytes) -> str:
    """Return the hex SHA-256 of a book file's bytes, for ``provenance.book_sha256``.

    Args:
        raw: The file's bytes exactly as stored.

    Returns:
        str: The lowercase hex digest.
    """
    return hashlib.sha256(raw).hexdigest()


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
