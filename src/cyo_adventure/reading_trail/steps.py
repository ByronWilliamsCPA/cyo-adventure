"""Step vocabulary, batch validation, and the idempotent merge for reading trails.

A reading trail is one read-through of one storybook version, recorded as an
ordered list of steps. Each step is a closed ``kind`` plus a node id (and, for
a choice, a choice id) from the pinned version's own blob, an ordinal ``seq``
the client assigns, and ``elapsed_s``, whole seconds since the read began on
the reader's own clock.

Step kinds (the client recorder, ``frontend/src/reader/readingTrail.ts``, is
the only producer):

- ``start``: the read began at its opening node (a fresh read, a restart, or a
  series continuation's entry node). Only ever ``seq`` 0.
- ``resume``: the read picked up from saved progress at ``node_id``. Only ever
  ``seq`` 0.
- ``choice``: a real decision. ``node_id`` declares two or more choices and
  ``choice_id`` is the one taken.
- ``auto``: ``node_id`` declares exactly one choice and the reader moved
  through it. Under ADR-026 flowed rendering the reader walks these nodes
  automatically; at page-per-node bands the child taps the only option.
  Neither is a decision, so they are recorded (keeping the path and the dwell
  timing complete) but marked, and pick-rate reporting ignores them.
- ``back``: a rewind. ``node_id`` is the node the reader landed on. A run of
  consecutive ``back`` steps is one "try a different choice" rewind.
- ``end``: the reader reached the ending at ``node_id``.
- ``jump``: the position changed in a way none of the above explains (a
  bookmark load, or adopting another device's newer position). ``node_id`` is
  the new position.
- ``restart``: the last step of a read the reader started over; ``node_id`` is
  where they were. The new read is a new trail.
- ``leave``: the reader left the book; ``node_id`` is where they were. This is
  the abandon marker.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import READING_TRAIL_MAX_STEPS

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

# Whole seconds since read start, capped at one week. A read left open longer
# than this is not telling us anything about a passage; the client clamps to
# this bound so a legitimately long-open tab is never rejected.
MAX_ELAPSED_SECONDS = 7 * 24 * 60 * 60
# Steps per POST. The client flushes far smaller batches; this bounds the
# validation work one request can demand.
MAX_STEPS_PER_BATCH = 200
# Identifier length bound, matching the String(120) node/choice/ending columns
# used elsewhere in the schema.
MAX_ID_LENGTH = 120

# Rejection messages. Each names a rule, never the submitted id (see _reject).
_MSG_DUPLICATE_SEQ = "a batch may not repeat a step seq"
_MSG_UNKNOWN_NODE = "step names a node this version does not have"
_MSG_OPENING_POSITION = "a read opens with start or resume at seq 0, and only there"
_MSG_STRAY_CHOICE = "only a choice or auto step carries a choice id"
_MSG_END_NOT_ENDING = "an end step must name an ending node"
_MSG_UNKNOWN_CHOICE = "step names a choice its node does not declare"
_MSG_AUTO_ARITY = "an auto step needs a node with exactly one choice"
_MSG_CHOICE_ARITY = "a choice step needs a node with two or more choices"


class StepKind(StrEnum):
    """The closed step vocabulary (see the module docstring for meanings)."""

    START = "start"
    RESUME = "resume"
    CHOICE = "choice"
    AUTO = "auto"
    BACK = "back"
    END = "end"
    JUMP = "jump"
    RESTART = "restart"
    LEAVE = "leave"


# Kinds that open a read; exactly these, and only at seq 0.
OPENING_KINDS = frozenset({StepKind.START, StepKind.RESUME})
_CHOICE_KINDS = frozenset({StepKind.CHOICE, StepKind.AUTO})


@dataclass(frozen=True, slots=True)
class TrailStep:
    """One validated-shape step, as the API body hands it to this module.

    Attributes:
        seq: The client-assigned ordinal within the read, from 0.
        kind: The step kind.
        node_id: A node id of the pinned version.
        choice_id: The choice taken, for ``choice``/``auto`` only.
        elapsed_s: Whole seconds since the read began (reader's clock).
    """

    seq: int
    kind: StepKind
    node_id: str
    choice_id: str | None
    elapsed_s: int

    def as_stored(self) -> dict[str, object]:
        """Return the exact JSONB element shape persisted in ``steps``."""
        return {
            "seq": self.seq,
            "kind": self.kind.value,
            "node_id": self.node_id,
            "choice_id": self.choice_id,
            "elapsed_s": self.elapsed_s,
        }


@dataclass(frozen=True, slots=True)
class NodeFacts:
    """What validation and reporting need to know about one node.

    Attributes:
        choice_ids: Every choice id the node declares, in declared order.
        targets: Choice id to the node id it leads to.
        ending_id: The node's ending id when it is an ending, else ``None``.
        ending_title: The ending's title when it is an ending, else ``None``.
    """

    choice_ids: tuple[str, ...]
    targets: Mapping[str, str]
    ending_id: str | None
    ending_title: str | None = None


@dataclass(frozen=True, slots=True)
class StoryIndex:
    """A node lookup built once per request from a stored Storybook blob.

    Attributes:
        nodes: Node id to its facts.
    """

    nodes: Mapping[str, NodeFacts]

    @classmethod
    def from_blob(cls, blob: Mapping[str, object]) -> StoryIndex:
        """Index a stored Storybook blob, tolerating malformed parts.

        A malformed node or choice is skipped rather than raised on: the blob
        was already validated at publish time, and an index that is missing a
        node only makes validation stricter (a step naming it is rejected),
        never looser.

        Args:
            blob: The pinned version's ``storybook_version.blob``.

        Returns:
            StoryIndex: The index.
        """
        nodes: dict[str, NodeFacts] = {}
        raw_nodes = blob.get("nodes")
        if not isinstance(raw_nodes, list):
            return cls(nodes={})
        for raw in raw_nodes:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(raw, dict):
                continue
            node: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType]
            node_id = node.get("id")
            if not isinstance(node_id, str):
                continue
            choices = _choices(node.get("choices"))
            ending_id, ending_title = _ending(node)
            nodes[node_id] = NodeFacts(
                choice_ids=tuple(choice_id for choice_id, _ in choices),
                targets=dict(choices),
                ending_id=ending_id,
                ending_title=ending_title,
            )
        return cls(nodes=nodes)


def _choices(raw: object) -> list[tuple[str, str]]:
    """Return ``(choice id, target)`` pairs from a node's raw ``choices``."""
    if not isinstance(raw, list):
        return []
    found: list[tuple[str, str]] = []
    for item in raw:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(item, dict):
            continue
        choice: dict[str, object] = item  # pyright: ignore[reportUnknownVariableType]
        choice_id = choice.get("id")
        target = choice.get("target")
        if isinstance(choice_id, str) and isinstance(target, str):
            found.append((choice_id, target))
    return found


def _ending(node: Mapping[str, object]) -> tuple[str | None, str | None]:
    """Return the node's ``(ending id, ending title)`` when it is an ending."""
    if node.get("is_ending") is not True:
        return None, None
    raw = node.get("ending")
    if not isinstance(raw, dict):
        return None, None
    ending: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType]
    ending_id = ending.get("id")
    title = ending.get("title")
    if not isinstance(ending_id, str):
        return None, None
    return ending_id, title if isinstance(title, str) else None


def _reject(message: str, seq: int) -> ValidationError:
    """Build the rejection for one step.

    The message names the step's ordinal and the rule, never the submitted
    node or choice id: rejected content does not belong in a response body or
    in the structured log line the exception handler writes.
    """
    return ValidationError(message, field="steps", value=seq)


def validate_steps(index: StoryIndex, steps: Iterable[TrailStep]) -> None:
    """Reject a batch unless every step is consistent with the pinned version.

    Args:
        index: The pinned version's node index.
        steps: The batch, in any order.

    Raises:
        ValidationError: On the first step naming an unknown node, a choice the
            node does not declare, a kind inconsistent with the node, an
            opening kind away from ``seq`` 0 (or a non-opening kind at it), or
            a duplicate ``seq`` within the batch.
    """
    # #CRITICAL: data-integrity: this is the only thing standing between a
    # client and the owner's report. Every node and choice id must exist in the
    # pinned version, so a forged or stale batch cannot inject identifiers the
    # book does not contain. A whole batch is rejected on one bad step rather
    # than partially stored, so a replay is all-or-nothing.
    # #VERIFY: tests/unit/test_reading_trail_steps.py covers each rejection;
    # tests/integration/test_reading_trail.py::test_unknown_node_rejected
    # proves the route applies it before any write.
    seen: set[int] = set()
    for step in steps:
        if step.seq in seen:
            raise _reject(_MSG_DUPLICATE_SEQ, step.seq)
        seen.add(step.seq)
        facts = index.nodes.get(step.node_id)
        if facts is None:
            raise _reject(_MSG_UNKNOWN_NODE, step.seq)
        if (step.kind in OPENING_KINDS) != (step.seq == 0):
            raise _reject(
                _MSG_OPENING_POSITION,
                step.seq,
            )
        if step.kind in _CHOICE_KINDS:
            _check_choice(step, facts)
        elif step.choice_id is not None:
            raise _reject(_MSG_STRAY_CHOICE, step.seq)
        if step.kind is StepKind.END and facts.ending_id is None:
            raise _reject(_MSG_END_NOT_ENDING, step.seq)


def _check_choice(step: TrailStep, facts: NodeFacts) -> None:
    """Validate a ``choice``/``auto`` step against its node's declared choices."""
    if step.choice_id is None or step.choice_id not in facts.choice_ids:
        raise _reject(_MSG_UNKNOWN_CHOICE, step.seq)
    declared = len(facts.choice_ids)
    if step.kind is StepKind.AUTO and declared != 1:
        raise _reject(_MSG_AUTO_ARITY, step.seq)
    if step.kind is StepKind.CHOICE and declared < 2:
        raise _reject(_MSG_CHOICE_ARITY, step.seq)


def merge_steps(
    existing: Sequence[Mapping[str, object]], incoming: Iterable[TrailStep]
) -> list[dict[str, object]]:
    """Merge a batch into the stored steps; a step whose seq is stored is ignored.

    First write wins per ``seq``. That is what makes the ingest idempotent: an
    offline replay of an already-applied batch adds nothing, and a replay that
    overlaps a later batch adds only the steps it is missing.

    Args:
        existing: The row's stored ``steps``.
        incoming: The validated batch.

    Returns:
        list[dict[str, object]]: The merged steps, ordered by ``seq``.

    Raises:
        ValidationError: If the merged trail would exceed
            ``READING_TRAIL_MAX_STEPS``.
    """
    # #ASSUME: concurrency: the caller holds a row lock (SELECT ... FOR UPDATE)
    # across read-merge-write, so two batches for one read cannot both read the
    # same stored list and lose each other's steps.
    # #VERIFY: tests/integration/test_reading_trail.py::
    # test_overlapping_batches_merge_without_loss.
    by_seq: dict[int, dict[str, object]] = {}
    for stored in existing:
        seq = stored.get("seq")
        if isinstance(seq, int):
            by_seq[seq] = dict(stored)
    for step in incoming:
        by_seq.setdefault(step.seq, step.as_stored())
    if len(by_seq) > READING_TRAIL_MAX_STEPS:
        msg = f"a read may hold at most {READING_TRAIL_MAX_STEPS} steps"
        raise ValidationError(msg, field="steps", value=len(by_seq))
    return [by_seq[seq] for seq in sorted(by_seq)]


def ending_of(index: StoryIndex, steps: Sequence[Mapping[str, object]]) -> str | None:
    """Return the ending id of the highest-seq ``end`` step, or ``None``.

    A read can reach more than one ending (Go back from an ending screen and
    choose differently), so the row's ``ending_id`` records where the read
    finally finished; the report counts every ``end`` step separately.

    Args:
        index: The pinned version's node index.
        steps: Merged steps, ordered by ``seq``.

    Returns:
        str | None: The last ending reached, if any.
    """
    for stored in reversed(steps):
        node_id = stored.get("node_id")
        if stored.get("kind") == StepKind.END.value and isinstance(node_id, str):
            facts = index.nodes.get(node_id)
            if facts is not None and facts.ending_id is not None:
                return facts.ending_id
    return None
