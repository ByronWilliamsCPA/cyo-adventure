"""Deterministic post-review merge: one finding per (category, concern) group.

Design doc 2.2 item 3. Runs after all stages (and any repair adoption),
immediately before persistence. Plain code, not an LLM call. Structural
findings and PASS findings never merge; a group of one passes through with
node_ids populated for uniform reader handling.
"""

from __future__ import annotations

from cyo_adventure.moderation.report import Finding, FindingSeverity, Verdict

_VERDICT_RANK = {
    Verdict.BLOCK: 3,
    Verdict.FLAG: 2,
    Verdict.ADVISORY: 1,
    Verdict.PASS: 0,
}
_SEVERITY_RANK = {
    FindingSeverity.HIGH: 3,
    FindingSeverity.MEDIUM: 2,
    FindingSeverity.LOW: 1,
    None: 0,
}


def merge_findings(findings: list[Finding]) -> list[Finding]:
    """Group content findings by (category, concern); merge each group.

    The merged finding carries every affected node in ``node_ids``, the
    group's max verdict and max severity, the representative message from
    the highest-ranked member, and the group size in the message suffix.
    ``node_id`` keeps the first affected node for reader compat (or None
    for whole-story groups). Structural and PASS findings pass through
    unmerged, in their original positions relative to each other.
    """
    passthrough: list[Finding] = []
    groups: dict[tuple[str, str | None], list[Finding]] = {}
    for f in findings:
        if f.structural or f.verdict is Verdict.PASS:
            passthrough.append(f)
            continue
        groups.setdefault((f.category, f.concern), []).append(f)

    merged: list[Finding] = []
    for group in groups.values():
        top = max(
            group,
            key=lambda f: (_VERDICT_RANK[f.verdict], _SEVERITY_RANK[f.severity]),
        )
        node_ids = tuple(
            dict.fromkeys(f.node_id for f in group if f.node_id is not None)
        )
        message = top.message
        if len(group) > 1:
            message = f"{top.message} ({len(group)} findings merged)"
        merged.append(
            Finding(
                stage=top.stage,
                source=top.source,
                category=top.category,
                verdict=top.verdict,
                message=message,
                node_id=node_ids[0] if node_ids else None,
                score=top.score,
                structural=False,
                concern=top.concern,
                severity=top.severity,
                node_ids=node_ids or None,
            )
        )
    return merged + passthrough
