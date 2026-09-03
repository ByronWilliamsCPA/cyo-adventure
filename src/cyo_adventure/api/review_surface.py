"""C3-4 review-surface projection: reshape a stored moderation report for review.

Pure and synchronous: no database, network, or filesystem access (diagnostic
logging aside). Turns a version's stored ``moderation_report`` plus its story
``blob`` into the guardian-facing view: flagged passages (node prose joined to
per-node findings) and whole-story findings.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, NamedTuple, cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api.schemas import (
    ContentSummaryView,
    FindingView,
    FlaggedPassage,
    GenerationMeasuresView,
    GuardianFinding,
    GuardianValidatorNote,
    OutstandingModerationDetail,
    ReviewQueueItem,
    ReviewSummary,
    ReviewSurfaceView,
    SafetyConcernCount,
    ValidatorFindingView,
    ValidatorSeverity,
)
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.moderation.report import (
    FindingSeverity,
    Source,
    Verdict,
    legacy_hidden_fail_safe_node_counts,
    moderation_report_unusable,
)
from cyo_adventure.moderation.thresholds import (
    admin_noise_floor_for,
    admin_surfaces,
)
from cyo_adventure.storybook.models import ContentFlags
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from cyo_adventure.moderation.thresholds import ThresholdPolicy

_logger = get_logger(__name__)

# Deterministic admin ranking (design doc 2.6): verdict outranks severity
# outranks node count. PASS never reaches these buckets (filtered before
# construction), but is included so _VERDICT_RANK.get() never needs a
# fallback default for a value the type system already guarantees is a
# Verdict member.
_VERDICT_RANK: dict[Verdict, int] = {
    Verdict.BLOCK: 3,
    Verdict.FLAG: 2,
    Verdict.ADVISORY: 1,
    Verdict.PASS: 0,
}

_SEVERITY_RANK: dict[FindingSeverity | None, int] = {
    FindingSeverity.HIGH: 3,
    FindingSeverity.MEDIUM: 2,
    FindingSeverity.LOW: 1,
    None: 0,
}

# Design doc 2.7 option (a): only these two rule ids are ever surfaced; every
# other validator rule id (topology, safety, band-profile, etc.) already gates
# through the deterministic validator/moderation pipeline before generation
# reaches review, so projecting it here too would be a duplicate, confusing
# signal.
_VALIDATOR_RULE_IDS = frozenset({"RL-13", "PL-19"})


# #ASSUME: data-integrity: a story that was NEVER screened (moderation_report
# is None, e.g. a freshly-imported catalog draft ahead of its first
# moderation run) and a story that WAS screened but whose stored report
# carries no genuine judgment (fail-safe or mock-reviewer artifacts only) are
# both "unusable" for moderation_report_unusable()'s purposes, but they read
# as different admin actions: "run moderation" versus "re-run moderation".
# Distinguishing the message (and using the neutral "pipeline" category
# rather than "llm_safety" for the never-screened case, since no LLM safety
# stage ran at all) keeps the synthetic finding accurate instead of implying
# a screening attempt happened and produced nothing usable.
# #VERIFY: tests/unit/test_review_surface.py::
# test_null_report_synthetic_finding_says_unscreened.
def _unusable_report_finding(
    moderation_report: dict[str, object] | None,
) -> FindingView:
    """Build the synthetic structural finding for an unusable report.

    Args:
        moderation_report: The story's stored moderation report, already
            known to be unusable (per moderation_report_unusable), or None
            when the story has never been screened at all.

    Returns:
        FindingView: The one synthetic story-level finding to render.
    """
    if moderation_report is None:
        category = "pipeline"
        message = (
            "this story has not been screened by moderation yet; run "
            "moderation before reviewing"
        )
    else:
        category = "llm_safety"
        message = (
            "moderation report is unusable (fail-safe or mock-reviewer "
            "artifacts only); re-run moderation before reviewing"
        )
    return FindingView(
        stage=1,
        source=Source.PIPELINE,
        category=category,
        node_id=None,
        verdict=Verdict.FLAG,
        score=None,
        message=message,
        structural=True,
        concern="reviewer_unavailable",
    )


# #CRITICAL: security: a report can be usable AND largely unreviewed at the
# same time. moderation_report_unusable answers a whole-report question and
# returns False at the first genuine finding, so a story whose safety stage
# judged every node while its readability stage defaulted to fail-safe on 88%
# of them clears that predicate outright. The fail-safe verdict on a soft
# stage is PASS, and the per-finding loop below drops PASS before rendering,
# so those nodes are invisible rather than merely unlabelled: the approver
# sees a clean, fully-reviewed-looking surface over prose no readability
# check ever read, and ADR-005 makes that approver the final gate. This
# notice is what makes the hidden remainder countable on the surface.
# Deliberately NOT the whole unjudged remainder: a Stage 1 safety fail-safe
# is a FLAG, which gates and renders as its own flagged passage already, so
# legacy_hidden_fail_safe_node_counts excludes it and this notice never
# restates an outage the approver can already read.
# #VERIFY: tests/unit/test_review_surface.py::
# test_partially_fail_safe_report_is_usable_but_surfaces_the_gap and
# ::test_partial_gap_finding_stays_admin_only_and_off_the_passages;
# ::test_fully_reviewed_report_gets_no_gap_finding is the negative control.
def _partial_gap_findings(
    moderation_report: dict[str, object] | None, *, report_unusable: bool
) -> list[FindingView]:
    """Build the notice for a usable-but-partly-unjudged report, if any.

    Returns a list rather than an optional single view so the call site can
    ``extend`` unconditionally. That keeps the "is there a gap" decision
    inside this function instead of adding another branch to
    ``build_review_surface``, which is already at the complexity ceiling.

    Args:
        moderation_report: The stored report, or ``None``.
        report_unusable: Whether the caller already classified this report as
            wholly unusable. When it did, the caller emits its own
            reviewer_unavailable notice and this function returns nothing, so
            one outage is never described twice.

    Returns:
        list[FindingView]: One structural finding naming each stage that fell
        back and how much of the story it left unjudged, or an empty list when
        no stage fell back.
    """
    if report_unusable:
        return []
    scopes = legacy_hidden_fail_safe_node_counts(moderation_report)
    if not scopes:
        return []
    # A whole-story scope subsumes any named nodes from the same source: the
    # stage judged nothing, so naming a node count alongside it would imply a
    # partial result that does not exist.
    parts = [
        f"{source} left the whole story unjudged"
        if scope.whole_story
        else f"{source} left {scope.nodes} node"
        f"{'' if scope.nodes == 1 else 's'} unjudged"
        for source, scope in sorted(scopes.items())
    ]
    # A gap detected on the surface is the only witness that a stage fell back
    # invisibly: it never enters the stored report, so no machine gate reads
    # it, and without this line the sole record is an admin happening to open
    # the detail page.
    _logger.warning(
        "moderation_gap_detected",
        sources={
            source: {"nodes": scope.nodes, "whole_story": scope.whole_story}
            for source, scope in scopes.items()
        },
    )
    return [
        FindingView(
            # Stage 1 matches the wholly-unusable notice: the gap can span
            # several stages, so no single stage index describes it, and the
            # schema bounds the field to 0-4.
            stage=1,
            source=Source.PIPELINE,
            category="pipeline",
            node_id=None,
            verdict=Verdict.FLAG,
            score=None,
            # No "before approving": this notice is admin-only (see the call
            # site) and reaches published books too, where approval is long
            # past and re-moderation is the only remaining action.
            message=(
                f"{', '.join(parts)}; "
                f"{'each stage' if len(parts) > 1 else 'the stage'} defaulted "
                f"to fail-safe rather than judging. Re-run moderation."
            ),
            structural=True,
            concern="reviewer_unavailable",
        )
    ]


class _RoutedFindings(NamedTuple):
    """The four lanes one moderation report's findings are routed into.

    Extracted from ``build_review_surface`` so the routing rules live in one
    named place: the function was over Ruff's C901 complexity ceiling, and
    every branch inside the loop carries a `#CRITICAL` marker about which
    lane a finding must land in, which is exactly the logic that benefits
    from a name of its own.
    """

    flagged: dict[str, list[FindingView]]
    order: list[str]
    story_level: list[FindingView]
    all_views: list[FindingView]


def _route_findings(
    findings: list[dict[str, object]],
    *,
    admin_noise_floor: float | None,
    age_band: str = "",
    policy: ThresholdPolicy | None = None,
) -> _RoutedFindings:
    """Route each persisted finding into the per-node, story-level, and ranker lanes.

    Args:
        findings: The persisted finding dicts, already narrowed to the set the
            caller wants routed (empty when the report is wholly unusable).
        admin_noise_floor: The admin-configured global noise floor, or ``None``
            to skip floor filtering entirely. See ``build_review_surface``.
        age_band: The story's age band, used with ``policy`` to resolve a
            per-category floor (`RS-B3`). Empty resolves to the code default.
        policy: The resolved threshold policy, or ``None`` to use the flat
            floor for every category (the behaviour before `RS-B3`).

    Returns:
        The four lanes, as a ``_RoutedFindings``.
    """
    flagged: dict[str, list[FindingView]] = {}
    order: list[str] = []
    story_level: list[FindingView] = []
    all_views: list[FindingView] = []
    for finding in findings:
        view = _finding_view(finding)
        if view.verdict is Verdict.PASS:
            continue
        # #ASSUME: security: the floor denoises the ADMIN review view only
        # (opt-in via admin_noise_floor); admin_surfaces guarantees
        # FLAG/BLOCK/unscored findings always surface, so a bright-line
        # 0.0 BLOCK is never hidden.
        # #VERIFY: tests/integration/test_review_surface_noise_floor.py.
        # `RS-B3`: the floor is resolved per CATEGORY and band, while the
        # never-hide guarantees stay in admin_surfaces. The resolution is
        # deliberately not ThresholdPolicy.surfaces: that would import a
        # min_verdict default of FLAG and hide every advisory admin-wide while
        # moderation_threshold is empty. See admin_noise_floor_for.
        floor = admin_noise_floor_for(
            view.category,
            age_band=age_band,
            policy=policy,
            flat_floor=admin_noise_floor,
        )
        if floor is not None and not admin_surfaces(
            view.verdict, view.score, noise_floor=floor
        ):
            continue
        # #CRITICAL: security: all_views must be appended to BEFORE the
        # structural guard below, because _rank_and_split reads all_views to
        # build structural_findings. Moving this append after the guard's
        # `continue` leaves structural_findings permanently empty, which
        # looks like "no pipeline problems" on the admin surface rather than
        # like a bug. The two routings are orthogonal: all_views feeds the
        # ranker, flagged/story_level feed the legacy fan-out.
        # #VERIFY: tests/unit/test_review_surface.py::
        # test_structural_finding_node_ids_survive_alongside_content_finding
        # asserts both halves (story-level routing AND structural_findings
        # membership) on a genuinely-structural finding, so either
        # ordering mistake fails it; the fully-collapsed
        # test_structural_finding_with_node_ids_stays_story_level no
        # longer exercises this branch at all.
        all_views.append(view)
        # #CRITICAL: security: a structural finding describes the PIPELINE
        # ("the reviewer was unavailable on 12 nodes"), not the prose of any
        # one passage, so it must never enter the per-node fan-out below.
        # Stage A (8ca8d1b3) collapsed N per-node fail-safe findings into a
        # single story-level finding precisely to stop a reviewer outage from
        # flooding the approver's queue with N identical rows. Stage B2 gave
        # that finding node_ids so the ranking stage can weigh its true node
        # coverage; without this guard those ids route it straight back
        # through the fan-out and reinstate the flood, while simultaneously
        # dropping it out of the guardian content summary, which is built
        # from story_level_findings. Both regressions, opposite directions,
        # one cause. node_ids stays populated on the view for the admin
        # detail panel and the ranker; only the routing changes.
        # #VERIFY: tests/unit/test_review_surface.py::
        # test_structural_finding_node_ids_survive_alongside_content_finding
        # keeps node_ids populated on a genuinely-structural finding while
        # routing it to story_level instead of the fan-out below.
        if view.structural:
            story_level.append(view)
            continue
        # #CRITICAL: security: a merged finding (design doc 2.2) names every
        # affected node in node_ids and only the first in node_id. Grouping
        # on node_id alone would render one passage and leave the rest of
        # the flagged prose looking clean to the human approver, who is the
        # final gate under ADR-005. Fan out across node_ids, falling back to
        # node_id for unmerged and pre-Stage-B findings.
        # #VERIFY: tests/unit/test_review_surface.py::
        # test_merged_finding_fans_out_across_every_affected_node.
        target_nodes = view.node_ids or ([] if view.node_id is None else [view.node_id])
        if not target_nodes:
            story_level.append(view)
            continue
        # `RS-A1` (owner ruling 2026-08-31): a LOW-severity ADVISORY is
        # counted and reachable, but is NOT part of the default detail
        # view. It is already carried, ranked, by low_advisory_findings
        # via all_views (appended above) -> _rank_and_split, and the
        # frontend renders that list collapsed. Fanning it out here as
        # well is what made the surface unreviewable: the fan-out is
        # O(findings x affected_nodes), so one merged provider advisory
        # covering 380 nodes emitted 380 full-prose passage cards. On the
        # largest queued book that produced 610 cards for 1 blocking
        # finding plus 14 flags, a 2.5% signal-to-noise ratio, and put 102
        # screens of boilerplate between the reviewer and the ranked list
        # that states the block in one line.
        #
        # #CRITICAL: security: the skip sits BELOW the empty-target_nodes
        # fallback above, not above it, and the placement is the whole
        # difference between fixing the fan-out and shrinking what a
        # guardian sees. Multiplication is the defect: a low advisory
        # naming N nodes emits N cards. One naming NO node emits exactly
        # one story-level row, and story_level_findings is a different
        # audience, redacted into build_content_summary and counted into
        # the queue's flagged_count. Skipping before the fallback drops
        # that row from the guardian summary and decrements the badge,
        # which the ruling never asked for.
        #
        # #CRITICAL: security: the predicate is also deliberately narrower
        # than "any advisory". A MEDIUM or HIGH advisory still fans out,
        # and a scored BLOCK at any severity always does, because the low
        # tier is the only one the owner ruled out of the default view. Do
        # not widen this to verdict alone; that would hide graded provider
        # signal a reviewer is meant to read in context.
        # #VERIFY: tests/unit/test_review_surface.py::
        # test_low_advisory_is_not_fanned_out_but_stays_collapsed and
        # ::test_medium_advisory_still_fans_out_into_passages pin both
        # sides of the severity boundary;
        # ::test_low_advisory_with_no_node_stays_story_level pins the
        # placement, so hoisting the skip above the fallback fails it.
        if _is_low_advisory(view):
            continue
        for nid in target_nodes:
            if nid not in flagged:
                flagged[nid] = []
                order.append(nid)
            flagged[nid].append(view)
    return _RoutedFindings(
        flagged=flagged, order=order, story_level=story_level, all_views=all_views
    )


def build_review_surface(
    *,
    status: str,
    storybook_id: str,
    version: int,
    blob: dict[str, object],
    moderation_report: dict[str, object] | None,
    admin_noise_floor: float | None = None,
    validation_report: dict[str, object] | None = None,
    age_band: str = "",
    policy: ThresholdPolicy | None = None,
) -> ReviewSurfaceView:
    """Build the guardian review surface for one story version.

    Args:
        status: The storybook's lifecycle status.
        storybook_id: The story id.
        version: The version being reviewed.
        blob: The stored story blob (source of node prose).
        moderation_report: The stored report, or ``None`` if unmoderated.
        admin_noise_floor: The admin-configured global noise floor, or
            ``None`` to skip floor filtering entirely. The two ADMIN call
            paths pass a floor: the review detail endpoint
            (``api/approval.py::get_review_surface``) and the review queue
            (via ``build_review_queue_item``). The guardian reuse path
            (``build_content_summary``) must keep passing ``None``: guardian
            surfaces are gated by the age-band ``ThresholdPolicy`` instead
            (default ``min_verdict=FLAG``), and the floor is an admin-only
            denoise, never a guardian filter.
        validation_report: The story's stored ``validation_report`` (design
            doc 2.7 option (a)), or ``None`` when the caller has none to pass
            (a pre-validator-persistence row, or a call site, like the
            guardian content-summary reuse path, that does not need it).
            Read-only: this function never re-runs the validator, it only
            projects RL-13/PL-19 findings already in the stored report.
        age_band: The story's age band (`RS-B3`), used with ``policy`` to
            resolve the admin floor per category. Only meaningful alongside a
            non-``None`` ``admin_noise_floor``; the guardian reuse path leaves
            both at their defaults.
        policy: The resolved threshold policy (`RS-B3`), or ``None`` to apply
            the flat floor to every category. Supplies ``min_score`` only:
            ``min_verdict`` is never read here, because its FLAG default would
            hide every advisory from the admin lane while
            ``moderation_threshold`` is empty.

    Returns:
        ReviewSurfaceView: Blob plus summary, flagged passages, story-level
            findings, the ranked/structural/low-advisory merged-finding
            buckets, and validator findings. Empty projections when the
            report is ``None``.

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
        # #CRITICAL: security: a report with no genuine content judgment (every
        # finding a fail-safe artifact, or a non-independent/mock reviewer)
        # must never render as N separate flagged passages: that dresses up
        # "nothing was actually reviewed" as a busy, reviewed-looking surface
        # and buries the one fact an approver needs (re-run moderation) under
        # noise. Starve _route_findings of input (pass it no findings at all)
        # rather than post-filtering what it returns, so its flagged/order/
        # story_level lanes come back empty and the queue's flagged_count
        # reads 0, not the count of discarded fail-safe rows.
        # #VERIFY: tests/unit/test_review_surface.py::
        # test_unusable_report_collapses_to_one_structural_finding and
        # ::test_unusable_report_queue_item_counts.
        report_unusable = moderation_report_unusable(moderation_report)
        routed = _route_findings(
            [] if report_unusable else _findings(moderation_report),
            admin_noise_floor=admin_noise_floor,
            age_band=age_band,
            policy=policy,
        )
        flagged, order, story_level = routed.flagged, routed.order, routed.story_level
        all_views = (
            [_unusable_report_finding(moderation_report)]
            if report_unusable
            else routed.all_views
        )
        # #CRITICAL: security: admin lane ONLY, matching the wholly-unusable
        # notice above (which is also appended to all_views alone). all_views
        # feeds _rank_and_split, so a structural=True gap notice lands in
        # structural_findings and the admin detail panel renders it;
        # story_level_findings is a DIFFERENT audience, redacted into the
        # guardian content summary by build_content_summary and counted into
        # the queue's flagged_count. Routing the gap notice there too sent a
        # guardian the internal stage identifier that _guardian_group_key
        # strips from every other finding, told the guardian of an ALREADY
        # PUBLISHED book to act before approving it, and inflated
        # flagged_count by one on both the guardian summary and the admin
        # badge. A stage that fell back is an operator fact, and re-running
        # moderation is an action no guardian can take.
        # #VERIFY: tests/unit/test_review_surface.py::
        # test_partial_gap_finding_stays_admin_only_and_off_the_passages.
        gap_findings = _partial_gap_findings(
            moderation_report, report_unusable=report_unusable
        )
        all_views.extend(gap_findings)
        passages = [
            FlaggedPassage(
                node_id=nid, prose=prose_by_id.get(nid, ""), findings=flagged[nid]
            )
            for nid in order
        ]
        structural, low_advisory, ranked = _rank_and_split(all_views)
        return ReviewSurfaceView(
            storybook_id=storybook_id,
            version=version,
            status=status,
            blob=blob,
            # Finding 3: the only reliable "never screened" signal, since a
            # screened-clean report also yields empty passages/findings below.
            screened=moderation_report is not None,
            report_unusable=report_unusable,
            summary=_summary(moderation_report),
            flagged_passages=passages,
            story_level_findings=story_level,
            ranked_findings=ranked,
            structural_findings=structural,
            low_advisory_findings=low_advisory,
            validator_findings=_validator_findings(validation_report),
            generation_measures=_generation_measures(validation_report, all_views),
        )
    except PydanticValidationError as exc:
        msg = "review surface cannot be built from a malformed moderation report"
        raise ValidationError(msg, field="moderation_report") from exc


def _as_rate(value: object) -> float | None:
    """Narrow a persisted JSON value to a rate in [0, 1], or ``None`` otherwise.

    ``bool`` is excluded explicitly: it is an ``int`` subclass in Python, so
    ``True`` would otherwise project as a fill rate of 1.0, which reads as a
    perfect fill rather than as the corrupt value it is.

    Args:
        value: The raw value read from the persisted report.

    Returns:
        The rate as a float, or ``None`` when the value is absent, not a
        number, or outside the unit interval.
    """
    # #ASSUME: data-integrity: every caller renders this as a percentage
    # (`Math.round(rate * 100)` on the approval screen), so a value that is
    # merely a `float` is not yet safe to show. `NaN`, `inf`, and a rate
    # persisted as a percentage (82 rather than 0.82) all pass a bare type
    # check and render as "NaN%", "Infinity%", or "8200%" beside a real
    # measurement, which is worse than reporting the value as unavailable: an
    # approver cannot tell a corrupt rate from a measured one. Degrade to
    # absent, matching the `bool` rejection above, so a malformed record can
    # only ever read as "not recorded".
    # #VERIFY: tests/unit/test_review_surface.py::
    # test_generation_measures_non_finite_fill_rate_degrades_to_absent and
    # ::test_generation_measures_out_of_range_fill_rate_degrades_to_absent.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    rate = float(value)
    if not math.isfinite(rate) or not (0.0 <= rate <= 1.0):
        return None
    return rate


def _generation_measures(
    validation_report: dict[str, object] | None,
    views: list[FindingView],
) -> GenerationMeasuresView:
    """Project the measurements behind the routing decision (R-2).

    Read-only, like ``_validator_findings``: a missing or malformed value
    degrades to absent rather than raising, because ``validation_report`` is a
    read-only annex to the review surface and a corrupt rate is not worth
    failing the whole approval screen over.

    Args:
        validation_report: The stored generation/validation report, or
            ``None``.
        views: Every finding already narrowed and floor-filtered for this
            surface, so the roll-up counts exactly what the approver sees.

    Returns:
        GenerationMeasuresView: The fill rate against its floor, plus the
        surfaced content concerns with their counts.
    """
    report = validation_report or {}
    counts: dict[str, int] = {}
    for view in views:
        # Structural findings describe the pipeline ("the reviewer was
        # unavailable on 12 nodes"), not the book. Counting them beside content
        # concerns would tell an approver a story raised a safety concern when
        # what happened is that a backend was down.
        # The `category` test is belt-and-suspenders rather than a second bug
        # fix: every concern-bearing non-safety finding today also sets
        # `structural=True` (moderation/stages.py's `reviewer_unavailable`,
        # pipeline.py's `mock_reviewer_active`), and synthesis routes
        # structural findings to its passthrough list so the flag survives the
        # merge. But this field is named for safety and is read as such by an
        # approver, so it should not depend on every future concern-bearing
        # finding remembering to mark itself structural. `category="safety"` is
        # set once, in `stages._safety_finding`, and synthesis preserves it.
        if view.structural or view.category != "safety" or view.concern is None:
            continue
        counts[view.concern] = counts.get(view.concern, 0) + 1
    return GenerationMeasuresView(
        fill_rate=_as_rate(report.get("fill_rate")),
        fill_rate_floor=_as_rate(report.get("fill_rate_floor")),
        fill_rate_downgrade=_as_bool(report.get("fill_rate_downgrade")),
        # Count descending, then concern ascending: a stable order, so a
        # re-render of an unchanged report never reshuffles the block.
        safety_concerns=[
            SafetyConcernCount(concern=concern, count=count)
            for concern, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    )


def _target_node_count(view: FindingView) -> int:
    """Return how many nodes a finding covers, fan-out aware (design doc 2.2).

    Mirrors the ``target_nodes`` computation in ``build_review_surface``'s main
    loop exactly, so the ranking's node-count term and the passage fan-out
    always agree on what a finding covers.
    """
    if view.node_ids:
        return len(view.node_ids)
    return 0 if view.node_id is None else 1


def _ranking_key(view: FindingView) -> tuple[int, int, int]:
    """Deterministic admin ranking key: verdict desc, severity desc, node-count desc.

    ``list.sort``/``sorted`` are stable, so findings tied on all three ranks
    keep the persisted report's original order as the final tiebreak (design
    doc 2.6's "stable tiebreak"), rather than an arbitrary or reshuffled order
    on every request.
    """
    return (
        -_VERDICT_RANK.get(view.verdict, 0),
        -_SEVERITY_RANK.get(view.severity, 0),
        -_target_node_count(view),
    )


def _is_low_advisory(view: FindingView) -> bool:
    """Is this the lowest-consequence tier: a LOW-severity ADVISORY?

    `RS-A1`: this predicate has two callers that MUST agree, and the whole
    correctness of the low-advisory channel rests on them agreeing. Owner
    ruling 2026-08-31: low advisories are "counted and available for a
    reviewer to dig into, but not part of the default view in detail". That
    is two behaviours over one set: `_rank_and_split` collapses the set into
    ``low_advisory_findings``, and ``_review_surface`` declines to fan the
    node-bearing members of that same set out into ``flagged_passages``.

    #CRITICAL: data integrity: if the two callers ever test different
    conditions, a finding can be dropped from the fan-out AND from the
    collapsed list at the same time, which removes it from the admin surface
    entirely while every count still reports it. The human approver is the
    final gate under ADR-005, so a silently unreachable finding is a safety
    defect, not a display bug. Both callers therefore call this function and
    neither inlines the comparison.
    #VERIFY: tests/unit/test_review_surface.py::
    test_fan_out_skip_set_and_collapsed_set_are_the_same_set asserts set
    equality over a mixed corpus, so inlining a divergent copy in either
    caller fails it.
    """
    return view.severity is FindingSeverity.LOW and view.verdict is Verdict.ADVISORY


def _rank_and_split(
    findings: list[FindingView],
) -> tuple[list[FindingView], list[FindingView], list[FindingView]]:
    """Split findings into (structural, low_advisory, ranked-primary), each ranked.

    Design doc 2.6: structural findings get their own visually distinct block
    regardless of severity (checked first, so a structural finding never also
    lands in the low-advisory bucket). Everything else that is a low-severity
    advisory collapses behind the low-ADVISORY toggle; the admin_noise_floor
    row (applied earlier, in the caller) remains the mechanism for Stage-0
    scored advisories, so this severity-based split is purely additive, not a
    replacement. Everything remaining is the primary ranked list.
    """
    structural: list[FindingView] = []
    low_advisory: list[FindingView] = []
    primary: list[FindingView] = []
    for view in findings:
        if view.structural:
            structural.append(view)
        elif _is_low_advisory(view):
            low_advisory.append(view)
        else:
            primary.append(view)
    structural.sort(key=_ranking_key)
    low_advisory.sort(key=_ranking_key)
    primary.sort(key=_ranking_key)
    return structural, low_advisory, primary


def _validator_findings(
    validation_report: dict[str, object] | None,
) -> list[ValidatorFindingView]:
    """Project RL-13/PL-19 findings from the stored validation report.

    Read-only (design doc 2.7 option (a)): this never re-runs the validator,
    it only reads ``validator/report.py::ValidationReport.to_dict()``'s
    already-persisted shape (``{"ok": bool, "findings": [...]}}``). A missing
    report, a malformed entry, or any rule id outside the two-item allowlist
    degrades to omission rather than raising: unlike moderation source/verdict,
    an unrecognized validator rule id is not a corrupt-at-rest signal worth
    failing the whole review surface over, since ``validation_report`` is a
    read-only annex to it, not the report this function's caller must not
    silently mis-render.
    """
    if validation_report is None:
        return []
    raw = validation_report.get("findings")
    if not isinstance(raw, list):
        # Degrading to [] is deliberate (see docstring), but a silent degrade
        # is indistinguishable from "this story genuinely has no RL-13/PL-19
        # findings". A future change to ValidationReport.to_dict() would zero
        # out validator visibility for every book with no operational signal,
        # so leave a breadcrumb without changing the non-raising contract.
        _logger.debug(
            "validation_report_findings_not_a_list",
            findings_type=type(raw).__name__,
        )
        return []
    views: list[ValidatorFindingView] = []
    for entry in raw:
        if not isinstance(entry, dict):
            _logger.debug(
                "validation_report_finding_not_a_dict",
                entry_type=type(entry).__name__,
            )
            continue
        entry = cast(dict[str, object], entry)  # noqa: TC006 (see _findings above)
        rule_id = entry.get("rule_id")
        if not isinstance(rule_id, str) or rule_id not in _VALIDATOR_RULE_IDS:
            continue
        severity = entry.get("severity")
        message = entry.get("message")
        node_id = entry.get("node_id")
        # #CRITICAL: security: an unreadable severity must fail toward the
        # LOUDER tier, not the calmer one. PL-19 spans both values (per-node
        # word wall is ERROR, story-mean drift is WARNING), and this projection
        # feeds the guardian's assignment screen via _validator_notes, which
        # groups by (rule_id, severity). Defaulting to "warning" would let a
        # corrupt row silently downgrade an error into advisory text under the
        # exact button a guardian presses to give a book to a child, and would
        # additionally split one "RL-13 error x6" note into "error x5" plus
        # "warning x1". Over-warning is recoverable; under-warning is not.
        # #VERIFY: tests/unit/test_review_surface.py::
        # test_validator_finding_with_unreadable_severity_defaults_to_error.
        if severity not in ("error", "warning"):
            _logger.debug(
                "validator_finding_severity_unreadable",
                rule_id=rule_id,
                severity_repr=repr(severity),
            )
        # Normalize HERE rather than letting ValidatorSeverity's Literal reject
        # it: a pydantic failure inside build_review_surface is caught and
        # re-raised as a 422, which would take down the entire review surface
        # over a read-only annex this function's docstring promises to degrade
        # on. A typo'd "warn" therefore becomes "error", never a third bucket
        # that would silently split a guardian's "RL-13 error xN" note.
        severity_value: ValidatorSeverity = (
            "warning" if severity == "warning" else "error"
        )
        views.append(
            ValidatorFindingView(
                rule_id=rule_id,
                severity=severity_value,
                node_id=node_id if isinstance(node_id, str) else None,
                # An unreadable message says so, rather than rendering as an
                # empty cell an admin would read as "this rule fired and had
                # nothing to add". Dropping the whole finding instead (the
                # other obvious option) would hide a real validator signal
                # over one corrupt field, which is the wrong trade on a
                # safety-review surface: rule_id, severity, and node_id are
                # each independently actionable without the prose.
                message=(
                    message
                    if isinstance(message, str)
                    else f"({rule_id}: stored message unreadable)"
                ),
            )
        )
    return views


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
    concern = finding.get("concern")
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
        severity=_as_severity(finding.get("severity")),
        node_ids=_as_node_ids(finding.get("node_ids")),
        structural=_as_bool(finding.get("structural")),
        concern=concern if isinstance(concern, str) else None,
    )


def _as_severity(value: object) -> FindingSeverity | None:
    """Narrow a JSON value to a FindingSeverity, or None on any mismatch.

    Unlike ``_as_source``/``_as_verdict``, severity is a ranking hint, not a
    gate: an old report legitimately lacks it, and a corrupt value should
    degrade quietly rather than block the whole review surface.
    """
    if isinstance(value, str):
        try:
            return FindingSeverity(value)
        except ValueError:
            return None
    return None


def _as_node_ids(value: object) -> list[str] | None:
    """Narrow a JSON value to a list[str], or None on any mismatch."""
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return cast(list[str], value)  # noqa: TC006 (see _findings above)
    return None


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


class DecisionCounts(NamedTuple):
    """The gating numbers every admin list shows for one story version.

    Named fields rather than a bare tuple so the two call sites (`RS-A7`'s queue
    row and `RS-C2`'s outstanding-decisions row) name the same four things;
    ``NamedTuple`` matches ``_RoutedFindings`` above rather than introducing a
    second value-object idiom in one module.
    """

    block_findings: int
    flag_findings: int
    advisory_findings: int
    top_finding: FindingView | None


def build_decision_counts(surface: ReviewSurfaceView) -> DecisionCounts:
    """Count the distinct gating findings on a built surface, and pick its headline.

    Task 4: tiered DISTINCT-finding counts, as opposed to a queue item's
    ``flagged_count`` (which counts occurrences: a finding fanned across 3 nodes
    via ``node_ids`` counts 3 times there). Each merged finding view here counts
    exactly once, regardless of its node coverage. Sourced from the three
    merged-finding buckets (ranked/structural/low_advisory), which together are
    every non-PASS finding the surface produced; advisories never gate and are
    counted separately, never folded into block/flag.

    ``top_finding`` (`RS-A7`) is taken from the ALREADY RANKED lists rather than
    re-sorted here, so a row's headline finding is the same object the detail
    page shows first; re-deriving an order would be a second ranking rule to
    keep in step with ``_ranking_key``. Bucket precedence, not a merged sort: a
    ranked finding outranks a structural one (the book, not the pipeline), and
    both outrank a low advisory. A structural finding is a real headline when it
    is all there is, because it means the report itself needs a re-run.

    Args:
        surface: A surface already built by ``build_review_surface``, so the
            noise floor and per-band policy have been applied. Passing an
            unfloored surface would produce counts that contradict the detail
            view an admin clicks into.

    Returns:
        DecisionCounts: Distinct block/flag/advisory counts plus the headline
            finding, or ``None`` for the latter when the report has no non-PASS
            finding at all.
    """
    # #VERIFY: tests/unit/test_review_surface.py::
    # test_tiered_counts_are_distinct_findings_not_occurrences,
    # ::test_queue_top_finding_prefers_ranked_over_structural and
    # ::test_queue_top_finding_falls_back_to_low_advisory.
    merged = [
        *surface.ranked_findings,
        *surface.structural_findings,
        *surface.low_advisory_findings,
    ]
    return DecisionCounts(
        block_findings=sum(1 for f in merged if f.verdict == Verdict.BLOCK),
        flag_findings=sum(
            1 for f in merged if f.verdict == Verdict.FLAG and not f.structural
        ),
        advisory_findings=sum(1 for f in merged if f.verdict == Verdict.ADVISORY),
        top_finding=next(
            iter(
                surface.ranked_findings
                or surface.structural_findings
                or surface.low_advisory_findings
            ),
            None,
        ),
    )


def build_moderation_decision_detail(
    *,
    storybook_id: str,
    status: str,
    version: int,
    moderation_report: dict[str, object] | None,
    admin_noise_floor: float | None,
    age_band: str,
    policy: ThresholdPolicy | None,
) -> OutstandingModerationDetail | None:
    """Project one version's report into a `RS-C2` decision row, without its blob.

    THE EMPTY BLOB IS DELIBERATE and this is the only place it appears. Every
    bucket ``build_review_surface`` routes findings into is report-derived; the
    blob is read for exactly two things, the prose attached to
    ``flagged_passages`` and the echoed ``blob`` field, neither of which this
    surface projects. The outstanding-decisions list spans every status rather
    than the 13 ``in_review`` books, so loading blobs to reach counts that do
    not depend on them would pull tens of megabytes per request to compute four
    integers. Reusing ``build_review_surface`` rather than re-deriving the
    counts is the other half of that choice: a second routing implementation
    would drift from the floored detail view it is supposed to agree with.

    Args:
        storybook_id: The story id, forwarded for the surface's own projection.
        status: The storybook's lifecycle status.
        version: The version the decision is about.
        moderation_report: That version's stored report, or ``None``.
        admin_noise_floor: The admin-configured global floor. Always passed
            here: this is an admin-only surface, and its counts must match the
            floored detail view.
        age_band: The story's age band, for per-category flooring (`RS-B3`).
        policy: The resolved threshold policy (`RS-B3`).

    Returns:
        OutstandingModerationDetail: The gating detail, or ``None`` when this
        version holds no outstanding moderation decision at all (no block, no
        flag, and a usable report). Returning ``None`` rather than a row of
        zeroes is what keeps a clean published book off the surface.

    Raises:
        ValidationError: If the stored report is corrupt at rest (propagated
            from ``build_review_surface``); the caller isolates the bad row.
    """
    surface = build_review_surface(
        status=status,
        storybook_id=storybook_id,
        version=version,
        blob={},
        moderation_report=moderation_report,
        admin_noise_floor=admin_noise_floor,
        age_band=age_band,
        policy=policy,
    )
    counts = build_decision_counts(surface)
    # #CRITICAL: security: an UNUSABLE report is an outstanding decision in its
    # own right, not a clean bill of health. A report that failed to parse or
    # came back empty produces zero findings, which without this clause would
    # read exactly like a compliant book and drop a live story off the list
    # that exists to find it. This is the same fail-closed reading
    # moderation/report.py::moderation_report_unusable was added for.
    # #VERIFY: tests/unit/test_outstanding_decisions.py::
    # test_an_unusable_report_on_a_published_book_is_an_outstanding_decision.
    if (
        not counts.block_findings
        and not counts.flag_findings
        and not surface.report_unusable
    ):
        return None
    return OutstandingModerationDetail(
        block_findings=counts.block_findings,
        flag_findings=counts.flag_findings,
        advisory_findings=counts.advisory_findings,
        report_unusable=surface.report_unusable,
        top_finding=counts.top_finding,
    )


def build_review_queue_item(
    *,
    storybook_id: str,
    status: str,
    version: int,
    blob: dict[str, object],
    moderation_report: dict[str, object] | None,
    admin_noise_floor: float | None = None,
    created_at: datetime | None = None,
    age_band: str = "",
    policy: ThresholdPolicy | None = None,
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
        admin_noise_floor: The admin-configured global noise floor, or
            ``None`` to skip floor filtering. The queue is admin-only, so
            passing the floor here keeps the console's "N flagged" badge and
            Flagged bucket consistent with the denoised detail view; a
            noise-only story no longer reads as flagged.
        created_at: When this version was created, surfaced as the queue item's
            ``waiting_since`` triage metadata (UX-A3), or ``None`` to omit it.
        age_band: The story's age band (`RS-B3`), forwarded so a queue row's
            counts are floored on the same per-category basis as the detail
            view the admin clicks into. A queue and a detail view resolving
            different floors would make the badge contradict the list.
        policy: The resolved threshold policy (`RS-B3`), forwarded unchanged.

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
    # #ASSUME: security: the floor denoises ADMIN surfaces only; the queue is
    # admin-only (approval.py::get_review_queue gates on is_admin), and
    # flagged_count must count exactly the findings the floored detail view
    # will show, or the badge contradicts the list the admin clicks into.
    # #VERIFY: tests/unit/test_review_surface.py::
    # test_queue_item_flagged_count_respects_noise_floor.
    surface = build_review_surface(
        status=status,
        storybook_id=storybook_id,
        version=version,
        blob=blob,
        moderation_report=moderation_report,
        admin_noise_floor=admin_noise_floor,
        age_band=age_band,
        policy=policy,
    )
    flagged_count = sum(
        len(passage.findings) for passage in surface.flagged_passages
    ) + len(surface.story_level_findings)
    # The tiered counts and the headline finding both come from
    # build_decision_counts below, shared with `RS-C2`'s outstanding-decisions
    # surface so a book cannot read "1 block" in one admin list and "0" in the
    # other. Note the contrast with flagged_count just above, which counts
    # OCCURRENCES and is blob-derived; these count distinct findings.
    counts = build_decision_counts(surface)
    return ReviewQueueItem(
        storybook_id=storybook_id,
        title=_queue_title(blob, storybook_id),
        status=status,
        version=version,
        screened=surface.screened,
        report_unusable=surface.report_unusable,
        flagged_count=flagged_count,
        block_findings=counts.block_findings,
        flag_findings=counts.flag_findings,
        advisory_findings=counts.advisory_findings,
        summary=surface.summary,
        age_band=_queue_age_band(blob),
        waiting_since=created_at,
        themes=_queue_themes(blob),
        content_flags=_queue_content_flags(blob),
        top_finding=counts.top_finding,
    )


def _queue_title(blob: dict[str, object], storybook_id: str) -> str:
    """Return the story title from the blob, or the id as a fallback."""
    title = blob.get("title")
    return title if isinstance(title, str) and title else storybook_id


def _queue_age_band(blob: dict[str, object]) -> str | None:
    """Return the target age band from the blob metadata, or None if absent."""
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        band = metadata.get("age_band")
        if isinstance(band, str) and band:
            return band
    return None


def _queue_themes(blob: dict[str, object]) -> list[str]:
    """Return the story's themes from the blob metadata, or [] if absent.

    Args:
        blob: The stored Storybook content blob.

    Returns:
        list[str]: ``metadata.themes``, filtered to string entries, or ``[]``
            when the metadata or field is absent.
    """
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        themes = metadata.get("themes")
        if isinstance(themes, list):
            return [theme for theme in themes if isinstance(theme, str)]
    return []


def _queue_content_flags(blob: dict[str, object]) -> ContentFlags | None:
    """Return the story's content-sensitivity flags, or None if absent/invalid.

    Args:
        blob: The stored Storybook content blob.

    Returns:
        ContentFlags | None: The parsed ``metadata.content_flags``, or
            ``None`` when absent or invalid.
    """
    # #ASSUME: data integrity: a blob written by an older schema version or a
    # corrupt-at-rest row may carry a ``content_flags`` shape ``ContentFlags``
    # no longer accepts; degrade to ``None`` (omit the badge) rather than fail
    # the whole queue row for a detail-only field.
    # #VERIFY: tests/unit/test_review_surface.py.
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        flags = metadata.get("content_flags")
        if isinstance(flags, dict):
            try:
                return ContentFlags.model_validate(flags)
            except PydanticValidationError:
                return None
    return None


def build_content_summary(
    *,
    storybook_id: str,
    version: int,
    blob: dict[str, object],
    moderation_report: dict[str, object] | None,
    age_band: str,
    policy: ThresholdPolicy,
    validation_report: dict[str, object] | None = None,
) -> ContentSummaryView:
    """Build the redacted guardian content summary for a published story version.

    Reuses build_review_surface so Verdict.PASS filtering, the screened-versus-
    unscreened rule, and corrupt-report rejection are defined in exactly one
    place. It then projects the admin surface down to a guardian-safe,
    story-level-only view (design doc 2.6): the gating summary, a total
    flagged count (per-node plus story-level, filtered by the age-band
    threshold policy), and a merged concern list -- every surfaced finding
    collapsed by concern/severity/verdict/message into one row per concern,
    carrying a node COUNT but never a node id. Per-node flagged passages
    themselves are never handed to the guardian: a guardian is the assigner,
    not the safety reviewer, and passage prose can spoil content and leak
    generation internals. See ``_content_summary_findings``.

    Args:
        storybook_id: The story id.
        version: The published version being summarized.
        blob: The stored story blob (source of node prose for the surface).
        moderation_report: The stored report, or ``None`` if unmoderated.
        age_band: The story's age band, used to resolve the surfacing threshold.
        policy: The resolved threshold policy (code default plus DB overrides).
        validation_report: The story's stored ``validation_report`` (design
            doc 2.7 option (a)), or ``None`` when the caller has none to pass.
            Forwarded to ``build_review_surface`` unchanged so RL-13/PL-19
            projection uses the exact same allowlist and tolerant parsing as
            the admin surface (``_validator_findings``); this function only
            aggregates that already-parsed list, it never re-parses the raw
            report. See ``_validator_notes``.

    Returns:
        ContentSummaryView: Screened flag, gating summary, flagged count, the
            merged concern list (category, concern, severity, verdict,
            message, node_count) that meets the age-band threshold, and the
            story-level, node-id-free ``validator_notes`` aggregate.

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
        validation_report=validation_report,
    )

    def _surfaces(category: str, verdict: Verdict, score: float | None) -> bool:
        return policy.surfaces(
            age_band=age_band, category=category, verdict=verdict, score=score
        )

    flagged_count, findings = _content_summary_findings(surface, _surfaces)
    return ContentSummaryView(
        storybook_id=storybook_id,
        version=version,
        screened=surface.screened,
        summary=surface.summary,
        flagged_count=flagged_count,
        findings=findings,
        validator_notes=_validator_notes(surface.validator_findings),
    )


def _validator_notes(
    validator_findings: list[ValidatorFindingView],
) -> list[GuardianValidatorNote]:
    """Aggregate admin-surface validator findings into guardian-safe note counts.

    Design doc 2.7 option (a): the guardian sees "RL-13 warning x12", never a
    node id or a per-node message (a per-node PL-19 message embeds node
    context, which would violate the story-level-only rule, design doc 2.6,
    even without a literal node id string). Groups ``validator_findings`` (the
    already allowlist-filtered, tolerantly-parsed output of
    ``_validator_findings``, reused here rather than re-parsed) by
    ``(rule_id, severity)``, preserving first-seen order for a deterministic,
    stable row order.

    Args:
        validator_findings: The admin surface's parsed validator findings
            (``build_review_surface``'s ``validator_findings``).

    Returns:
        list[GuardianValidatorNote]: One row per distinct (rule_id, severity)
            pair, each carrying the total occurrence count.
    """
    # Keyed on ValidatorSeverity, not str: widening it here would let an
    # arbitrary string reach GuardianValidatorNote.severity through the
    # grouping, which is the exact hop the Literal exists to close.
    counts: dict[tuple[str, ValidatorSeverity], int] = {}
    order: list[tuple[str, ValidatorSeverity]] = []
    for finding in validator_findings:
        key = (finding.rule_id, finding.severity)
        if key not in counts:
            counts[key] = 0
            order.append(key)
        counts[key] += 1
    return [
        GuardianValidatorNote(rule_id=key[0], severity=key[1], count=counts[key])
        for key in order
    ]


def _guardian_group_key(
    finding: FindingView,
) -> tuple[str, FindingSeverity | None, Verdict, str]:
    """The guardian merge key: concern (or category), severity, verdict, message.

    Mirrors ``moderation/synthesis.py``'s admin merge key
    (``category, concern, source, verdict, severity, message``) minus source
    and the bare category (concern, when set, is the more specific signal;
    category is still carried on the group as a display fallback, never part
    of the identity once concern is present) -- the guardian view carries
    neither node identity nor classifier provenance. Keying on the full tuple
    including message is deliberately conservative: it collapses only
    findings that are, in effect, the exact same admin-visible finding fanned
    across nodes (which already carry an identical message from
    ``moderation/synthesis.py``'s own merge), rather than risking two
    genuinely distinct concerns silently merging under a shared category.
    """
    concern_or_category = (
        finding.concern if finding.concern is not None else finding.category
    )
    return (concern_or_category, finding.severity, finding.verdict, finding.message)


def _content_summary_findings(
    surface: ReviewSurfaceView,
    surfaces_fn: Callable[[str, Verdict, float | None], bool],
) -> tuple[int, list[GuardianFinding]]:
    """Merge every threshold-surfaced finding into one concern-level guardian row.

    Design doc 2.6: the guardian view is story-level only, no per-node rows,
    no node ids. Every surfaced occurrence of a finding (once per node it
    covers via ``surface.flagged_passages``' existing fan-out, or once with
    zero node weight for a genuinely story-level finding) is grouped by
    ``_guardian_group_key``, so one admin-merged finding collapses to exactly
    one guardian row whose ``node_count`` sums its true node coverage.
    ``flagged_count`` stays the total surfaced-occurrence count, unchanged
    from the pre-Stage-B3 behavior this replaces (one pass over
    flagged_passages plus one over story_level_findings, each threshold-
    filtered), so the "N flagged" badge still matches what a passage-fan-out
    admin view would show, even though the guardian never sees the passages
    themselves.

    Args:
        surface: The (undenoised) admin review surface to redact and merge.
        surfaces_fn: The age-band threshold predicate (category, verdict,
            score) -> bool.

    Returns:
        tuple[int, list[GuardianFinding]]: The total flagged-occurrence count,
            and the merged, ranked-by-first-occurrence guardian findings.
    """
    flagged_count = 0
    node_counts: dict[tuple[str, FindingSeverity | None, Verdict, str], int] = {}
    categories: dict[tuple[str, FindingSeverity | None, Verdict, str], str] = {}
    concerns: dict[tuple[str, FindingSeverity | None, Verdict, str], str | None] = {}
    order: list[tuple[str, FindingSeverity | None, Verdict, str]] = []

    def _record(finding: FindingView, *, node_weight: int) -> None:
        key = _guardian_group_key(finding)
        if key not in node_counts:
            node_counts[key] = 0
            categories[key] = finding.category
            concerns[key] = finding.concern
            order.append(key)
        node_counts[key] += node_weight

    # #CRITICAL: security: guardian and kid surfaces filter by the age-band
    # threshold; the admin review surface (build_review_surface) never does.
    # Both loops below MUST apply surfaces_fn before they either increment
    # flagged_count or _record a row, and they must apply the SAME predicate,
    # or the "N flagged" badge contradicts the list printed under it. Stage B3
    # raised the stakes: pre-B3 a drift here desynced a count from an
    # (almost always empty) list, whereas now the same predicate governs both
    # the badge AND which concerns a guardian reads before handing a book to a
    # child, so an over-permissive filter here leaks a below-threshold concern
    # into guardian-visible text rather than merely inflating a number.
    # #VERIFY: tests/integration/test_content_summary_thresholds.py::
    # test_guardian_summary_hides_below_threshold_advisory.
    for passage in surface.flagged_passages:
        for finding in passage.findings:
            if not surfaces_fn(finding.category, finding.verdict, finding.score):
                continue
            flagged_count += 1
            _record(finding, node_weight=1)
    for finding in surface.story_level_findings:
        if not surfaces_fn(finding.category, finding.verdict, finding.score):
            continue
        flagged_count += 1
        _record(finding, node_weight=0)

    findings = [
        GuardianFinding(
            category=categories[key],
            verdict=key[2],
            message=key[3],
            concern=concerns[key],
            severity=key[1],
            node_count=node_counts[key],
        )
        for key in order
    ]
    return flagged_count, findings
