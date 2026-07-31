"""Deterministic post-review merge: collapse interchangeable findings.

Design doc 2.2 item 3. Runs after all stages (and any repair adoption),
immediately before persistence. Plain code, not an LLM call. Structural
findings and PASS findings never merge; a group of one passes through with
node_ids populated for uniform reader handling.

The doc names ``(category, concern)`` as the merge key and illustrates it
with "12 identical readability flags". That word is load-bearing: collapsing
N findings into one is only lossless when the members are interchangeable,
because every field except ``node_id`` is taken from a single survivor. Under
``(category, concern)`` alone that does not hold, and it holds least where it
matters most: Stage 1 emits no ``concern`` (design doc 2.2 item 1 supplies it,
and ships in B2), so the key degenerates to ``(category,)`` and every distinct
safety reason in a book collapses to one row with one surviving message.

The key here is therefore the full tuple of fields the merge would otherwise
destroy. ``(category, concern)`` is a prefix of it, so everything the doc
intends to merge still merges once item 1 lands; findings that differ in
verdict, severity, source, or message simply stay separate rather than having
N-1 of their reviewer messages discarded with no raw-output retention to
recover them from.
"""

from __future__ import annotations

from cyo_adventure.moderation.report import Finding, FindingSeverity, Source, Verdict

# Every field a merged Finding takes from a single survivor. Grouping on the
# full tuple is what makes the collapse lossless: members of a group differ
# only in which node they name.
_MergeKey = tuple[str, str | None, Source, Verdict, FindingSeverity | None, str]


def _merge_key(finding: Finding) -> _MergeKey:
    """Return the grouping key for one content finding."""
    return (
        finding.category,
        finding.concern,
        finding.source,
        finding.verdict,
        finding.severity,
        finding.message,
    )


def merge_findings(findings: list[Finding]) -> list[Finding]:
    """Collapse interchangeable content findings into one row per group.

    Members of a group are identical apart from ``node_id``, so the merged
    finding carries every affected node in ``node_ids`` and keeps the shared
    source, verdict, severity, and message unchanged. A group of more than
    one gets the group size appended to the message. ``node_id`` keeps the
    first affected node for readers that predate ``node_ids`` (or ``None``
    for whole-story groups); because the group is interchangeable, that node
    genuinely carries the reported verdict and message.

    ``score`` is the only field that may vary within a group. The merged
    finding takes the group maximum, which is the fail-safe direction and is
    consistent with the shared message.

    Structural and PASS findings pass through unmerged, in their original
    positions relative to each other.

    Args:
        findings: The report's findings, in production order.

    Returns:
        Merged content findings followed by the untouched passthrough set.
    """
    passthrough: list[Finding] = []
    groups: dict[_MergeKey, list[Finding]] = {}
    for f in findings:
        if f.structural or f.verdict is Verdict.PASS:
            passthrough.append(f)
            continue
        groups.setdefault(_merge_key(f), []).append(f)

    merged: list[Finding] = []
    for group in groups.values():
        first = group[0]
        node_ids = tuple(
            dict.fromkeys(f.node_id for f in group if f.node_id is not None)
        )
        scores = [f.score for f in group if f.score is not None]
        message = first.message
        if len(group) > 1:
            message = f"{first.message} ({len(group)} findings merged)"
        merged.append(
            Finding(
                stage=first.stage,
                source=first.source,
                category=first.category,
                verdict=first.verdict,
                message=message,
                node_id=node_ids[0] if node_ids else None,
                score=max(scores) if scores else None,
                structural=False,
                concern=first.concern,
                severity=first.severity,
                node_ids=node_ids or None,
            )
        )
    return merged + passthrough
