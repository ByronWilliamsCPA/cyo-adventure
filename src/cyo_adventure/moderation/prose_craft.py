"""Wire the prose-craft detectors onto the request path (`UW-C313`, `UW-C328`).

Self-repetition and narrative-person drift were measurable offline long before
they were visible to a reviewer: ``scripts/check_prose_craft.py`` has caught
both since `AL-496`/`AL-523`, but nothing ran them on a book on its way to
approval, so the one live book with 23 duplicate bodies and three labels
covering 89.8 percent of 674 choices reached a human with no note attached.
This module closes that gap by running the same definitions
(``validator/prose_craft.py``) inside the moderation pipeline.

**Advisory by design, and deliberately not a soft FLAG.** A ``Verdict.FLAG``
routes a book into the pipeline's one bounded auto-repair, whose prompt asks
the model to return the revised document. Neither defect is repairable that
way: a collapsed label set is a property of the skeleton's whole choice menu,
and a narrative-person mismatch is a whole-book rewrite. Both are exactly the
kind of judgment ADR-005's mandatory human approval exists to receive, so the
finding's job is to put the numbers in front of the reviewer, not to gate.
Promotion to a gate is `UW-C105`/`UW-C147`'s residual and wants a distribution
across real books first; the calibration figures here come from a handful.

Fail-open like every other advisory on this path: a shape this module cannot
read yields no findings rather than an exception. Nothing here touches the
database, so unlike ``leaf_diversity`` there is no transport failure to let
propagate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.validator.prose_craft import (
    judge_person,
    judge_sameness,
    person_report,
    sameness_report,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def _is_readable(blob: Mapping[str, Any]) -> bool:
    """Return whether ``blob`` has a node list the detectors can measure.

    The pipeline schema-validates the blob before this runs, and a validation
    failure adds a hard BLOCK that skips this guard entirely, so an unreadable
    shape should be unreachable. Checked anyway: an advisory that raises would
    convert a cosmetic finding into a failed moderation run, which is the one
    outcome this guard must never cause.

    Args:
        blob: The story blob under moderation.

    Returns:
        ``True`` when ``nodes`` is a list of mappings.
    """
    nodes = blob.get("nodes")
    return isinstance(nodes, list) and all(
        isinstance(node, dict) for node in cast("list[object]", nodes)
    )


def findings_from_prose_craft(blob: Mapping[str, Any]) -> list[Finding]:
    """Measure self-repetition and narrative person, and report what breached.

    #CRITICAL: security: every message here is numbers and instructions only,
    never story text. These findings are persisted on the version row and are
    read back onto the reviewer's surface, and a body quoted into a message
    would carry the child's personalized prose with it. The leaf-diversity
    guard keeps the same rule for the same reason.
    #VERIFY: tests/unit/test_moderation_prose_craft.py::
    test_no_finding_message_carries_story_prose.

    Args:
        blob: The story blob under moderation.

    Returns:
        list[Finding]: Up to two ``Verdict.ADVISORY`` findings, one per
        detector that breached its calibrated bound; ``[]`` when the book is
        clean or its shape cannot be read.
    """
    if not _is_readable(blob):
        return []

    findings: list[Finding] = []

    same = sameness_report(blob)
    if judge_sameness(same).breached:
        findings.append(
            Finding(
                stage=0,
                source=Source.PIPELINE,
                category="prose_craft_sameness",
                verdict=Verdict.ADVISORY,
                node_id=None,
                score=None,
                message=(
                    f"self-repetition: {same.redundant_nodes} nodes repeat "
                    f"another node's exact body across {same.repeated_texts} "
                    f"repeated texts; {same.distinct_labels} distinct choice "
                    f"labels over {same.labels}, top-3 share "
                    f"{same.top3_share:.1%}. Known-good books have zero "
                    "duplicate bodies and a top-3 share of 0.02 to 0.27; "
                    "advisory only"
                ),
            )
        )

    person = person_report(blob)
    verdict = judge_person(blob, person)
    if verdict.breached:
        findings.append(
            Finding(
                stage=0,
                source=Source.PIPELINE,
                category="prose_craft_person",
                verdict=Verdict.ADVISORY,
                node_id=None,
                score=None,
                message=(
                    f"narrative person: second-person narration in "
                    f"{person.second_person_nodes} of {person.nodes} nodes "
                    f"({person.rate:.1%}), against {verdict.framing}. "
                    "Committed gamebooks run 71.5% to 100% and committed "
                    "third-person prose 0% to 27%; advisory only"
                ),
            )
        )

    return findings
