"""C3-4 review-surface projection: reshape a stored moderation report for review.

Pure and synchronous. Turns a version's stored ``moderation_report`` plus its
story ``blob`` into the guardian-facing view: flagged passages (node prose joined
to per-node findings) and whole-story findings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api.schemas import (
    ContentSummaryView,
    FindingView,
    FlaggedPassage,
    GuardianFinding,
    ReviewQueueItem,
    ReviewSummary,
    ReviewSurfaceView,
)
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.moderation.report import Source, Verdict
from cyo_adventure.moderation.thresholds import admin_surfaces

if TYPE_CHECKING:
    from cyo_adventure.moderation.thresholds import ThresholdPolicy


def build_review_surface(
    *,
    status: str,
    storybook_id: str,
    version: int,
    blob: dict[str, object],
    moderation_report: dict[str, object] | None,
    admin_noise_floor: float | None = None,
) -> ReviewSurfaceView:
    """Build the guardian review surface for one story version.

    Args:
        status: The storybook's lifecycle status.
        storybook_id: The story id.
        version: The version being reviewed.
        blob: The stored story blob (source of node prose).
        moderation_report: The stored report, or ``None`` if unmoderated.
        admin_noise_floor: The admin-configured global noise floor, or
            ``None`` to skip floor filtering entirely. Only the admin review
            call site (``api/approval.py``) passes a floor; guardian reuse
            call sites in this module (``build_content_summary``,
            ``build_review_queue_item``) must keep passing ``None`` since
            they already filter by ``min_verdict=FLAG`` and must not change.

    Returns:
        ReviewSurfaceView: Blob plus summary, flagged passages, and story-level
            findings. Empty projections when the report is ``None``.

    Raises:
        ValidationError: If the stored report no longer conforms to the view
            schema (an out-of-range stage/count, or an unrecognized source or
            verdict at rest).
    """
    # #EDGE: data integrity: moderation_report is a JSONB column read back as
    # plain dict/list/str; FindingView/ReviewSummary now enforce it against
    # StrEnums and bounded ints, so a corrupt row is surfaced as a generic 422
    # (CWE-209) instead of an unhandled 500, matching player/replay.py::_parse.
    # #VERIFY: the pydantic detail is not forwarded to the client.
    try:
        prose_by_id = _prose_index(blob)
        flagged: dict[str, list[FindingView]] = {}
        order: list[str] = []
        story_level: list[FindingView] = []
        for finding in _findings(moderation_report):
            view = _finding_view(finding)
            if view.verdict is Verdict.PASS:
                continue
            # #ASSUME: security: the floor denoises the ADMIN review view only
            # (opt-in via admin_noise_floor); admin_surfaces guarantees
            # FLAG/BLOCK/unscored findings always surface, so a bright-line
            # 0.0 BLOCK is never hidden.
            # #VERIFY: tests/integration/test_review_surface_noise_floor.py.
            if admin_noise_floor is not None and not admin_surfaces(
                view.verdict, view.score, noise_floor=admin_noise_floor
            ):
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
            # Finding 3: the only reliable "never screened" signal, since a
            # screened-clean report also yields empty passages/findings below.
            screened=moderation_report is not None,
            summary=_summary(moderation_report),
            flagged_passages=passages,
            story_level_findings=story_level,
        )
    except PydanticValidationError as exc:
        msg = "review surface cannot be built from a malformed moderation report"
        raise ValidationError(msg, field="moderation_report") from exc


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
    # cast()'s str-typ overload (forward-reference style, what TC006 suggests)
    # returns Any, not the narrowed type -- pass the type object itself so
    # BasedPyright keeps the dict[str, object] narrowing isinstance() alone
    # cannot express on a parameterized generic. dict[str, object] has no
    # forward reference to defer, so there is no runtime cost to not quoting it.
    return [
        cast(dict[str, object], f)  # noqa: TC006
        for f in raw
        if isinstance(f, dict)
    ]


def _finding_view(finding: dict[str, object]) -> FindingView:
    """Narrow one persisted finding dict into a FindingView."""
    node_id = finding.get("node_id")
    score = finding.get("score")
    return FindingView(
        stage=_as_int(finding.get("stage")),
        source=_as_source(finding.get("source")),
        category=_as_str(finding.get("category")),
        node_id=node_id if isinstance(node_id, str) else None,
        verdict=_as_verdict(finding.get("verdict")),
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
    summary = cast(dict[str, object], raw)  # noqa: TC006 (see _findings above)
    return ReviewSummary(
        count=_as_int(summary.get("count")),
        hard_block=_as_bool(summary.get("hard_block")),
        soft_flag=_as_bool(summary.get("soft_flag")),
        repaired=_as_bool(summary.get("repaired")),
        reviewer_independent=_as_bool(summary.get("reviewer_independent")),
    )


def _as_str(value: object) -> str:
    """Coerce a JSON value to str, defaulting to empty."""
    return value if isinstance(value, str) else ""


def _as_source(value: object) -> Source:
    """Narrow a JSON value to a declared Source.

    Unlike ``_as_str``/``_as_int``/``_as_bool``, there is no safe default
    classifier to fall back to: an unrecognized source is exactly the
    corrupt-at-rest case this projection must reject, not paper over.

    Raises:
        ValidationError: If value is not a string, or not a recognized Source.
    """
    if isinstance(value, str):
        try:
            return Source(value)
        except ValueError:
            pass
    msg = "finding has an unrecognized source"
    raise ValidationError(msg, field="source", value=value)


def _as_verdict(value: object) -> Verdict:
    """Narrow a JSON value to a declared Verdict.

    Raises:
        ValidationError: If value is not a string, or not a recognized Verdict.
    """
    if isinstance(value, str):
        try:
            return Verdict(value)
        except ValueError:
            pass
    msg = "finding has an unrecognized verdict"
    raise ValidationError(msg, field="verdict", value=value)


def _as_int(value: object) -> int:
    """Coerce a JSON value to int, defaulting to 0 (bools excluded)."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _as_bool(value: object) -> bool:
    """Coerce a JSON value to bool, defaulting to False."""
    # #EDGE: data integrity: a persisted summary block should always store real
    # booleans; this rejects Python-truthy coercion of a corrupt value (e.g. the
    # string "false" or a non-empty list) so a malformed record cannot flip a
    # gating flag on by accident.
    # #VERIFY: tests/unit/test_review_surface.py::test_summary_rejects_non_bool_gate_values.
    return value if isinstance(value, bool) else False


def build_review_queue_item(
    *,
    storybook_id: str,
    status: str,
    version: int,
    blob: dict[str, object],
    moderation_report: dict[str, object] | None,
) -> ReviewQueueItem:
    """Project one storybook version into a review-queue item.

    Reuses ``build_review_surface`` so the Verdict.PASS filtering and the
    screened-versus-unscreened rule are defined in exactly one place.

    Args:
        storybook_id: The story id.
        status: The storybook's lifecycle status.
        version: The version under review (latest).
        blob: The stored story blob (source of the title).
        moderation_report: The stored report, or ``None`` if unmoderated.

    Returns:
        ReviewQueueItem: Title, status, version, screened flag, flagged count,
            and the gating summary (``None`` when unmoderated).

    Raises:
        ValidationError: If the stored moderation report is corrupt at rest
            (propagated from ``build_review_surface``).
    """
    # #EDGE: data integrity: a single corrupt moderation_report raises here. The
    # caller (get_review_queue) isolates this per row: it logs the bad row with
    # its storybook_id and drops it, so one corrupt-at-rest story no longer fails
    # the whole queue. build_review_surface still surfaces the corruption loudly
    # (as a ValidationError) rather than papering over it.
    # #VERIFY: build_review_surface maps a PydanticValidationError to
    # ValidationError; tests/unit/test_review_surface.py covers the malformed
    # case, and tests/integration/test_approval_api.py covers the per-row queue
    # isolation (one corrupt row does not fail the whole queue).
    surface = build_review_surface(
        status=status,
        storybook_id=storybook_id,
        version=version,
        blob=blob,
        moderation_report=moderation_report,
    )
    flagged_count = sum(
        len(passage.findings) for passage in surface.flagged_passages
    ) + len(surface.story_level_findings)
    return ReviewQueueItem(
        storybook_id=storybook_id,
        title=_queue_title(blob, storybook_id),
        status=status,
        version=version,
        screened=surface.screened,
        flagged_count=flagged_count,
        summary=surface.summary,
    )


def _queue_title(blob: dict[str, object], storybook_id: str) -> str:
    """Return the story title from the blob, or the id as a fallback."""
    title = blob.get("title")
    return title if isinstance(title, str) and title else storybook_id


def build_content_summary(
    *,
    storybook_id: str,
    version: int,
    blob: dict[str, object],
    moderation_report: dict[str, object] | None,
    age_band: str,
    policy: ThresholdPolicy,
) -> ContentSummaryView:
    """Build the redacted guardian content summary for a published story version.

    Reuses build_review_surface so Verdict.PASS filtering, the screened-versus-
    unscreened rule, and corrupt-report rejection are defined in exactly one
    place. It then projects the admin surface down to a guardian-safe view: the
    gating summary, the total flagged count (per-node plus story-level, filtered
    by the age-band threshold policy), and the story-level findings that clear
    the threshold. Per-node flagged passages are intentionally dropped: a
    guardian is the assigner, not the safety reviewer, and passage prose can
    spoil content and leak generation internals.

    Args:
        storybook_id: The story id.
        version: The published version being summarized.
        blob: The stored story blob (source of node prose for the surface).
        moderation_report: The stored report, or ``None`` if unmoderated.
        age_band: The story's age band, used to resolve the surfacing threshold.
        policy: The resolved threshold policy (code default plus DB overrides).

    Returns:
        ContentSummaryView: Screened flag, gating summary, flagged count, and
            story-level findings (category, verdict, message) that meet the
            age-band threshold.

    Raises:
        ValidationError: If the stored moderation report is corrupt at rest
            (propagated from build_review_surface).
    """
    surface = build_review_surface(
        status="published",
        storybook_id=storybook_id,
        version=version,
        blob=blob,
        moderation_report=moderation_report,
    )

    def _surfaces(category: str, verdict: Verdict, score: float | None) -> bool:
        return policy.surfaces(
            age_band=age_band, category=category, verdict=verdict, score=score
        )

    # #CRITICAL: security: guardian/kid surfaces filter by threshold; the admin
    # review surface (build_review_surface) never does. flagged_count MUST count
    # only surfaced findings or the badge contradicts the visible list.
    # #VERIFY: test_guardian_summary_hides_below_threshold_advisory.
    flagged_count = sum(
        1
        for passage in surface.flagged_passages
        for finding in passage.findings
        if _surfaces(finding.category, finding.verdict, finding.score)
    ) + sum(
        1
        for finding in surface.story_level_findings
        if _surfaces(finding.category, finding.verdict, finding.score)
    )
    findings = [
        GuardianFinding(
            category=finding.category,
            verdict=finding.verdict,
            message=finding.message,
        )
        for finding in surface.story_level_findings
        if _surfaces(finding.category, finding.verdict, finding.score)
    ]
    return ContentSummaryView(
        storybook_id=storybook_id,
        version=version,
        screened=surface.screened,
        summary=surface.summary,
        flagged_count=flagged_count,
        findings=findings,
    )
