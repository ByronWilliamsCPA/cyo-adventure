"""C3-4 review-surface projection: reshape a stored moderation report for review.

Pure and synchronous. Turns a version's stored ``moderation_report`` plus its
story ``blob`` into the guardian-facing view: flagged passages (node prose joined
to per-node findings) and whole-story findings.
"""

from __future__ import annotations

from typing import cast

from cyo_adventure.api.schemas import (
    FindingView,
    FlaggedPassage,
    ReviewSummary,
    ReviewSurfaceView,
)

# "pass" is a verdict value, not a credential (S105/B105 false positive); see
# the identical rationale on moderation/report.py::Verdict.PASS. Two
# suppressions are required: Ruff's flake8-bandit port honors its own
# directive, but the standalone bandit binary the CI Security Gate runs does
# not recognize that directive and only honors its own.
_PASS = "pass"  # noqa: S105  # nosec B105


def build_review_surface(
    *,
    status: str,
    storybook_id: str,
    version: int,
    blob: dict[str, object],
    moderation_report: dict[str, object] | None,
) -> ReviewSurfaceView:
    """Build the guardian review surface for one story version.

    Args:
        status: The storybook's lifecycle status.
        storybook_id: The story id.
        version: The version being reviewed.
        blob: The stored story blob (source of node prose).
        moderation_report: The stored report, or ``None`` if unmoderated.

    Returns:
        ReviewSurfaceView: Blob plus summary, flagged passages, and story-level
            findings. Empty projections when the report is ``None``.
    """
    prose_by_id = _prose_index(blob)
    flagged: dict[str, list[FindingView]] = {}
    order: list[str] = []
    story_level: list[FindingView] = []
    for finding in _findings(moderation_report):
        view = _finding_view(finding)
        if view.verdict == _PASS:
            continue
        if view.node_id is None:
            story_level.append(view)
            continue
        if view.node_id not in flagged:
            flagged[view.node_id] = []
            order.append(view.node_id)
        flagged[view.node_id].append(view)
    passages = [
        FlaggedPassage(
            node_id=nid, prose=prose_by_id.get(nid, ""), findings=flagged[nid]
        )
        for nid in order
    ]
    return ReviewSurfaceView(
        storybook_id=storybook_id,
        version=version,
        status=status,
        blob=blob,
        summary=_summary(moderation_report),
        flagged_passages=passages,
        story_level_findings=story_level,
    )


def _prose_index(blob: dict[str, object]) -> dict[str, str]:
    """Map node id -> prose (``Node.body``) from a story blob."""
    nodes = blob.get("nodes")
    if not isinstance(nodes, list):
        return {}
    index: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        body = node.get("body")
        if isinstance(nid, str):
            index[nid] = body if isinstance(body, str) else ""
    return index


def _findings(report: dict[str, object] | None) -> list[dict[str, object]]:
    """Return the report's findings list, or empty."""
    if report is None:
        return []
    raw = report.get("findings")
    if not isinstance(raw, list):
        return []
    return [cast("dict[str, object]", f) for f in raw if isinstance(f, dict)]


def _finding_view(finding: dict[str, object]) -> FindingView:
    """Narrow one persisted finding dict into a FindingView."""
    node_id = finding.get("node_id")
    score = finding.get("score")
    return FindingView(
        stage=_as_int(finding.get("stage")),
        source=_as_str(finding.get("source")),
        category=_as_str(finding.get("category")),
        node_id=node_id if isinstance(node_id, str) else None,
        verdict=_as_str(finding.get("verdict")),
        score=score
        if isinstance(score, (int, float)) and not isinstance(score, bool)
        else None,
        message=_as_str(finding.get("message")),
    )


def _summary(report: dict[str, object] | None) -> ReviewSummary | None:
    """Narrow the report summary block into a ReviewSummary, or None."""
    if report is None:
        return None
    raw = report.get("summary")
    if not isinstance(raw, dict):
        return None
    summary = cast("dict[str, object]", raw)
    return ReviewSummary(
        count=_as_int(summary.get("count")),
        hard_block=bool(summary.get("hard_block")),
        soft_flag=bool(summary.get("soft_flag")),
        repaired=bool(summary.get("repaired")),
        reviewer_independent=bool(summary.get("reviewer_independent")),
    )


def _as_str(value: object) -> str:
    """Coerce a JSON value to str, defaulting to empty."""
    return value if isinstance(value, str) else ""


def _as_int(value: object) -> int:
    """Coerce a JSON value to int, defaulting to 0 (bools excluded)."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
