"""Put the precise reader-agency detectors in front of the approver (`UW-C479`).

``validator/agency.py`` measures whether a book still behaves like a
choose-your-own-adventure, but until this module it ran only offline through
``scripts/check_prose_craft.py``: a newly generated book whose merge nodes all
open by telling the reader their route did not matter, whose labels say "you"
over third-person prose, and which declares no variables at all, passed the
gate and reached a human approver with nothing attached. This module runs the
same definitions inside the moderation pipeline, beside
``moderation/prose_craft.py``, and with the same contract:

* **Advisory only.** Every finding is ``Verdict.ADVISORY``, so none sets
  ``has_soft_flag`` or ``has_hard_block`` and none can route a book into the
  bounded auto-repair, block it, or gate approval. Like the person and
  sameness advisories, these defects are a judgment ADR-005's human approval
  exists to receive, and a seam or a stateless graph is not repairable by a
  rewrite-the-document prompt anyway.
* **Fail-open.** A shape this module cannot read yields no findings rather
  than an exception, because an advisory that raised would turn a craft note
  into a failed moderation run.
* **Numbers and identifiers, never story text.** Messages name node ids and
  choice ids so the approver can open the passage, and never quote a body or
  a label.

**Which checks, and why only these.** The 31-book calibration recorded in
``validator/agency.py`` found merge seams and the three label checks (meta,
jargon, second person over third-person prose) precise, with essentially no
false positives, so they are surfaced here, one finding per hit. The
stateless-merge fact is surfaced once per book. Option recaps, give-up
endings, and early setbacks are deliberately NOT surfaced: recaps are
near-universal and the 3-5 and 5-8 bands use question-form recaps as
read-aloud house style, so surfacing them would encode a per-band style
ruling the owner has not made (`AL-767`); give-up endings and early setbacks
are genre-dependent (the teen gamebooks register them by design), so a
per-book count would be noise until a genre-aware budget exists. Both stay
available offline through ``scripts/check_prose_craft.py``.

**Shape on the review surface.** Per-hit findings carry ``node_id`` and
``severity=LOW``. The persist-time merge stage
(``moderation/synthesis.py::merge_findings``) collapses findings that differ
only in ``node_id``, so every seam in a book becomes ONE row carrying all its
merge nodes in ``node_ids``; label findings name their node and choice in the
message and so stay one row per label. ``LOW`` puts them in the review
surface's collapsed low-priority list rather than fanning each one out as a
flagged-passage card (`RS-A1`): they stay counted and reachable, with each
node's prose one click away (`RS-A2`), without burying a safety finding under
forty craft notes. The once-per-book stateless-merge summary carries no node
and no severity, exactly like the existing prose-craft advisories, so it
lands in the primary ranked list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, cast

from cyo_adventure.moderation.report import (
    Finding,
    FindingSeverity,
    Source,
    Verdict,
)
from cyo_adventure.validator.agency import (
    label_defects,
    merge_node_count,
    merge_seams,
    merge_state_headline,
    state_counts,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cyo_adventure.validator.agency import BookPerson, LabelHit

__all__ = [
    "CATEGORY_JARGON_LABEL",
    "CATEGORY_MERGE_SEAM",
    "CATEGORY_META_LABEL",
    "CATEGORY_SECOND_PERSON_LABEL",
    "CATEGORY_STATELESS_MERGES",
    "findings_from_agency",
]

CATEGORY_MERGE_SEAM: Final[str] = "agency_merge_seam"
CATEGORY_META_LABEL: Final[str] = "agency_meta_label"
CATEGORY_JARGON_LABEL: Final[str] = "agency_jargon_label"
CATEGORY_SECOND_PERSON_LABEL: Final[str] = "agency_second_person_label"
CATEGORY_STATELESS_MERGES: Final[str] = "agency_stateless_merges"

# Identical for every seam on purpose: the persist-time merge stage groups
# findings that differ only in node_id, so a book's seams reach the approver as
# one row listing every affected merge node. A per-node detail (the inbound
# count, the matched cue) in this string would split that row into one per
# node. The node itself is carried in node_id, never in the text.
_SEAM_MESSAGE: Final[str] = (
    "merge seam: this node is reached by more than one route and opens by "
    "telling the reader the route did not matter. Open on what arriving here "
    "is like instead, or carry a variable from the earlier choice so the "
    "route can matter; advisory only"
)


def _is_readable(blob: Mapping[str, Any]) -> bool:
    """Return whether ``blob`` has the node and choice shape the detectors read.

    Stricter than ``moderation/prose_craft.py``'s guard because these
    detectors walk choices as well as nodes: a ``choices`` value that is not a
    list of mappings would raise inside the detector. The pipeline
    schema-validates the blob first, so this should be unreachable; it is
    checked anyway for the same reason as there.

    Args:
        blob: The story blob under moderation.

    Returns:
        ``True`` when ``nodes`` is a list of mappings whose ``choices`` are
        absent or a list of mappings, and ``variables`` is absent or a list.
    """
    nodes = blob.get("nodes")
    if not isinstance(nodes, list):
        return False
    variables = blob.get("variables")
    if variables is not None and not isinstance(variables, list):
        return False
    for node in cast("list[object]", nodes):
        if not isinstance(node, dict):
            return False
        choices = cast("dict[str, object]", node).get("choices")
        if choices is None:
            continue
        if not isinstance(choices, list) or not all(
            isinstance(choice, dict) for choice in cast("list[object]", choices)
        ):
            return False
    return True


def _label_finding(category: str, message: str, hit: LabelHit) -> Finding:
    """Build one per-label advisory on the node that carries the choice."""
    return Finding(
        stage=0,
        source=Source.PIPELINE,
        category=category,
        verdict=Verdict.ADVISORY,
        node_id=hit.node_id,
        score=None,
        severity=FindingSeverity.LOW,
        message=message,
    )


def _second_person_message(hit: LabelHit, person: BookPerson) -> str:
    """Return the second-person label message; ``person.source`` is numeric."""
    return (
        f"second-person label: choice {hit.choice_id} at node {hit.node_id} "
        f"addresses the reader as 'you' in a book held to third person "
        f"({person.source}). Rewrite it in the book's own person; advisory only"
    )


def findings_from_agency(blob: Mapping[str, Any]) -> list[Finding]:
    """Measure the precise reader-agency defects and report every hit.

    #CRITICAL: security: every message here is identifiers, counts, and
    instructions only, never story text. These findings are persisted on the
    version row and read back onto the reviewer's surface, and a label or body
    quoted into a message would carry the child's personalized prose with it.
    The label checks are the risky ones, since a label IS story text; they
    name the choice by id instead. ``BookPerson.source`` is the only
    non-literal string interpolated, and it is a closed vocabulary plus a
    percentage.
    #VERIFY: tests/unit/test_moderation_agency.py::
    test_no_finding_message_carries_story_text.

    #ASSUME: data-integrity: a schema-valid book cannot carry a condition
    without a declared variable, so ``variables == 0`` (the trigger here)
    and ``StateCounts.stateless`` (which the headline clause reads) agree on
    every book that reaches this point.
    #VERIFY: tests/unit/test_moderation_agency.py::
    test_a_book_with_merges_and_no_variables_gets_one_summary.

    Args:
        blob: The story blob under moderation.

    Returns:
        list[Finding]: ``Verdict.ADVISORY`` findings only: one per merge seam,
        one per meta, jargon, or second-person label, and at most one
        story-level summary when the book has merge nodes and no variables.
        ``[]`` when the book is clean or its shape cannot be read.
    """
    if not _is_readable(blob):
        return []

    # Deliberately absent: option_recaps, give_up_endings, early_setbacks.
    # Recaps await an owner ruling on per-band recap style (AL-767); the two
    # ending measures are genre-dependent. See the module docstring.
    findings: list[Finding] = [
        Finding(
            stage=0,
            source=Source.PIPELINE,
            category=CATEGORY_MERGE_SEAM,
            verdict=Verdict.ADVISORY,
            node_id=hit.node_id,
            score=None,
            severity=FindingSeverity.LOW,
            message=_SEAM_MESSAGE,
        )
        for hit in merge_seams(blob)
    ]

    labels = label_defects(blob)
    findings.extend(
        _label_finding(
            CATEGORY_META_LABEL,
            (
                f"meta label: choice {hit.choice_id} at node {hit.node_id} names "
                "a mental act (deciding, weighing, reflecting) instead of "
                "something the hero does. Rewrite it as an action; advisory only"
            ),
            hit,
        )
        for hit in labels.meta
    )
    findings.extend(
        _label_finding(
            CATEGORY_JARGON_LABEL,
            (
                f"jargon label: choice {hit.choice_id} at node {hit.node_id} "
                "uses book-structure words (hub, node, ending, chapter, page) "
                "instead of story words. Rewrite it in-world; advisory only"
            ),
            hit,
        )
        for hit in labels.jargon
    )
    findings.extend(
        _label_finding(
            CATEGORY_SECOND_PERSON_LABEL,
            _second_person_message(hit, labels.person),
            hit,
        )
        for hit in labels.second_person
    )

    merges = merge_node_count(blob)
    state = state_counts(blob)
    # #EDGE: data-integrity: a book with conditional choices but no declared
    # variables would read "0 variables and N conditional choices carry
    # earlier choices forward" here, which contradicts the trigger. Schema
    # validation rejects that shape before moderation runs.
    # #VERIFY: test_a_book_with_merges_and_no_variables_gets_one_summary pins
    # the clause this message quotes.
    if merges and state.variables == 0:
        seams = sum(1 for f in findings if f.category == CATEGORY_MERGE_SEAM)
        findings.append(
            Finding(
                stage=0,
                source=Source.PIPELINE,
                category=CATEGORY_STATELESS_MERGES,
                verdict=Verdict.ADVISORY,
                node_id=None,
                score=None,
                message=(
                    f"reader agency: {merge_state_headline(merges, seams, state)}. "
                    "With no variables, every merge node is a place where the "
                    "reader's earlier choices stop mattering: no early choice "
                    "can change anything after it. Plant a variable before a "
                    "merge and pay it off after; advisory only"
                ),
            )
        )

    return findings
