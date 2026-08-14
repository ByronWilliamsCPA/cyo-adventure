"""Say what the gate did NOT look at, so its silence stops reading as a pass.

A gate assembled from checkers that all abstain on a dimension reports a clean
verdict on that dimension, and the aggregate silence reads as verification. That
is `AL-325` at the node level, where four checkers each correctly skipped a
``<<FILL>>`` body and four correct skips composed into a pass on an unwritten
book, and `AL-337` one abstraction wider, where "safe and age-appropriate,
verifiably" was claimed at the highest confidence in the programme on the
strength of a Flesch-Kincaid grade that observes one leg of a three-leg
construct.

This module emits the complement of what ran: given a gate context, the
dimensions on which no checker was even asked.

**The declaration is tied to behaviour, not maintained beside it.** A hand-kept
list of "what checker X observes" goes stale the first time X changes, and a
manifest that lies converts an unknown blind spot into a false assurance, which
is worse than no manifest at all. So every observed dimension carries a
**witness**: a document built to trip one of that dimension's rules. Running the
whole battery through the real gate is what proves the declarations still
describe the code, and :func:`verify_declarations` is that run. Delete a
checker's rule and its witness stops failing and the verification reports the
declaration stale.

That is the whole of W6's decision rule: keep this only while the declaration
cannot drift from behaviour. If a dimension is ever added here without a witness
that the real gate can trip, the honest move is to delete it from this module and
put it in prose instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from cyo_adventure.validator.gate import GateContext, run_gate

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from cyo_adventure.validator.report import ValidationReport

__all__ = [
    "OBSERVED",
    "UNOBSERVED",
    "Observation",
    "blind_spots",
    "verify_declarations",
]

_BOTH: Final[tuple[GateContext, ...]] = ("skeleton", "fill_result")


@dataclass(frozen=True, slots=True)
class Observation:
    """One dimension, the rules that observe it, and the proof they still do.

    Attributes:
        dimension: What the gate is claiming to have looked at.
        rules: Rule ids that observe it. At least one must fire on the witness.
        contexts: Gate contexts in which those rules actually run. A rule that
            runs in only one context leaves the dimension unobserved in the
            other, which is precisely the `AL-325` case: `PL-27` runs on a fill
            result and not on a skeleton, and before it existed nothing observed
            filled prose in either.
        witness: Builds a document that must trip one of ``rules``. This is what
            makes the declaration checkable rather than merely written down.
    """

    dimension: str
    rules: frozenset[str]
    contexts: tuple[GateContext, ...]
    witness: Callable[[], dict[str, object]]


def _base() -> dict[str, object]:
    """Build a small, gate-clean story for a witness to break in one place.

    Returns:
        The document. Kept minimal on purpose: a witness should differ from a
        passing document in exactly the property its dimension is about, or the
        rule that fires is not evidence about that dimension.
    """
    return {
        "schema_version": "2.0",
        "id": "s_witness",
        "version": 1,
        "title": "Witness",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 3.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": ["adventure"],
            "estimated_minutes": 5,
            "ending_count": 2,
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
            "topology": "time_cave",
        },
        "start_node": "n_start",
        "variables": [],
        "nodes": [
            {
                "id": "n_start",
                "body": "The gate is open. A small dog waits by the wall.",
                "is_ending": False,
                "choices": [
                    {"id": "c_left", "label": "Go left.", "target": "n_left"},
                    {"id": "c_right", "label": "Go right.", "target": "n_right"},
                ],
            },
            {
                "id": "n_left",
                "body": "You go left and find the dog's red ball in the grass.",
                "is_ending": True,
                "ending": {
                    "id": "e_left",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "The ball",
                },
            },
            {
                "id": "n_right",
                "body": "You go right and the dog runs home ahead of you.",
                "is_ending": True,
                "ending": {
                    "id": "e_right",
                    "valence": "positive",
                    "kind": "discovery",
                    "title": "The way home",
                },
            },
        ],
    }


def _nodes(doc: dict[str, object]) -> list[dict[str, object]]:
    """Return a document's node list, typed.

    Args:
        doc: The document.

    Returns:
        The nodes.
    """
    nodes = doc["nodes"]
    if not isinstance(nodes, list):  # pragma: no cover - the base is well formed
        msg = "witness document has no node list"
        raise TypeError(msg)
    return nodes  # pyright: ignore[reportUnknownVariableType]


def _witness_graph_integrity() -> dict[str, object]:
    """Point a choice at a node that does not exist.

    Returns:
        The document, which must raise a reference-integrity finding.
    """
    doc = _base()
    choices = _nodes(doc)[0]["choices"]
    if isinstance(choices, list):
        choices[0]["target"] = "n_nowhere"  # pyright: ignore[reportIndexIssue]
    return doc


def _witness_filled_prose() -> dict[str, object]:
    """Leave a node body holding the directive that should have been replaced.

    Returns:
        The document, which must raise a fill-residue finding when validated as
        a fill result, and must NOT raise one when validated as a skeleton.
    """
    doc = _base()
    _nodes(doc)[1]["body"] = "<<FILL role=ending words=80 beats='the ball is found'>>"
    return doc


def _witness_reading_level() -> dict[str, object]:
    """Write a body far above the declared band.

    Returns:
        The document, which must raise a reading-level finding.
    """
    doc = _base()
    _nodes(doc)[1]["body"] = (
        "Notwithstanding the incontrovertible circumstantial evidence "
        "accumulated throughout the preceding investigative interval, the "
        "determination remained fundamentally irreconcilable with the "
        "assembled participants' collective expectations regarding "
        "restitution."
    )
    return doc


def blind_spots(context: GateContext) -> frozenset[str]:
    """Return the dimensions no checker observes in *context*.

    Args:
        context: The posture the gate ran under.

    Returns:
        Dimension names on which every constituent checker abstained, including
        the ones nothing observes in any context. A caller printing a verdict
        should print this beside it: the verdict is a statement about the
        complement of this set and about nothing else.
    """
    unobserved_here = {
        entry.dimension for entry in OBSERVED if context not in entry.contexts
    }
    return frozenset(unobserved_here | set(UNOBSERVED))


def annotate(report: ValidationReport, context: GateContext) -> dict[str, object]:
    """Render a gate verdict alongside what it did not examine.

    Args:
        report: The gate's report.
        context: The posture it ran under.

    Returns:
        A serialisable mapping carrying the verdict and its blind spots, so a
        consumer reading ``ok`` sees the scope of that claim in the same object
        rather than having to know this module exists.
    """
    return {
        "ok": report.ok,
        "context": context,
        "unobserved_dimensions": sorted(blind_spots(context)),
    }


def verify_declarations(
    observed: Sequence[Observation] | None = None,
) -> list[str]:
    """Run every witness through the real gate and report stale declarations.

    This is the drift check, and it is the reason this module is allowed to make
    a machine-readable claim at all. A declaration that no longer matches the
    code is a false assurance, and a false assurance about a blind spot is the
    exact harm `AL-337` describes.

    Args:
        observed: Declarations to verify, defaulting to :data:`OBSERVED`.

    Returns:
        One line per declaration whose witness did not trip any of its declared
        rules. Empty means every declaration still describes the gate.
    """
    stale: list[str] = []
    for entry in observed if observed is not None else OBSERVED:
        context = entry.contexts[0]
        result = run_gate(entry.witness(), context=context)
        fired = {f.rule_id for f in result.report.findings}
        if not (fired & entry.rules):
            stale.append(
                f"{entry.dimension}: declares {sorted(entry.rules)} but its "
                f"witness tripped {sorted(fired) or 'nothing'} in context "
                f"{context!r}. Either the checker stopped checking or the "
                "declaration was never true."
            )
    return stale


# Dimensions the gate observes, each with the witness that proves it still does.
# Ordered by how load-bearing the dimension is rather than alphabetically.
OBSERVED: Final[tuple[Observation, ...]] = (
    Observation(
        dimension="graph_integrity",
        rules=frozenset({"L1-2", "L1-3", "L1-4", "L1-5"}),
        contexts=_BOTH,
        witness=_witness_graph_integrity,
    ),
    Observation(
        dimension="reading_level_quantitative",
        rules=frozenset({"RL-13", "PL-19"}),
        contexts=_BOTH,
        witness=_witness_reading_level,
    ),
    Observation(
        dimension="filled_prose",
        rules=frozenset({"PL-27"}),
        # The AL-325 case, and the reason `contexts` exists on this dataclass at
        # all: nothing observes filled prose when a document is validated as a
        # skeleton, correctly so, and a skeleton-context verdict must say so.
        contexts=("fill_result",),
        witness=_witness_filled_prose,
    ),
)

# Dimensions no instrument in the pipeline observes, in any context. These are
# not a backlog: three of the four are qualitative constructs that a formula
# cannot proxy, and writing four more formulas that appear to cover them would
# recreate `AL-337` rather than close it. They are listed so a reader of a clean
# verdict knows what the verdict did not include.
#
# Named from the three-leg text-complexity construct the reading-level claim
# rests on. Flesch-Kincaid is the quantitative leg; these are the qualitative
# ones, and `validator/reading_level.py` observes none of them.
UNOBSERVED: Final[tuple[str, ...]] = (
    "levels_of_meaning",
    "text_structure",
    "language_conventionality",
    "knowledge_demands",
    # W15 proposed instrumenting this one with an author-declared
    # `unknowns_to_preserve` list and a checker over it, and its rule required
    # the checker to catch a paraphrase of the declared secret. The candidate was
    # built and run (tests/unit/test_information_state_probe.py) and catches only
    # literal restatement and reordering: "the lighthouse keeper is the thief"
    # leaks just as completely through "the man who tended the light had been
    # taking the cargo", which shares no content word with the declaration.
    # Detecting that is an entailment question and nothing here answers one.
    # Dropped per the pre-registered rule, and listed here rather than behind a
    # checker that would report clean on everything but a copy-paste.
    "information_state",
)
