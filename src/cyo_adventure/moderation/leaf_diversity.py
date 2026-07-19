"""Wire the anti-template guard (ATG) into the moderation pipeline (WS-1 D1).

Advisory and fail-open by contract (see
``docs/planning/ws1-leaf-diversity-sprint-design.md`` section 3): every
no-partner, first-use, malformed-blob, or structure-drift path returns an
empty finding list and the pipeline proceeds unchanged. The guard never
blocks, never auto-rejects, and never touches approve/publish; its only
power is to add soft-``FLAG`` findings that ride the moderation pipeline's
one existing bounded repair (``moderation/repair.py``), after which the
story routes to the human guardian exactly as it does today.

Only data-shaped failures (a missing partner, a malformed blob, a structural
mismatch) are swallowed here. A transport-level ``SQLAlchemyError`` from
either of the two reads (``load_family_history``, ``load_version_blob``)
is deliberately NOT caught: it propagates to the worker's existing rollback
plus RQ-retry path, the same posture as this pipeline's intentional
``ProviderError``/``BusinessLogicError`` propagation (supervisor ruling,
design doc section 10).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.history import load_family_history, load_version_blob
from cyo_adventure.diversity.leaf import anti_template_verdict
from cyo_adventure.diversity.normalize import coerce_storybook
from cyo_adventure.diversity.query import select_atg_comparison_partner
from cyo_adventure.diversity.report import AntiTemplateReport, AntiTemplateVerdict
from cyo_adventure.diversity.structure import structure_fingerprint
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.db.models import Storybook, StorybookVersion

_logger = get_logger(__name__)


def findings_from_anti_template(
    report: AntiTemplateReport,
    *,
    partner_storybook_id: str,
    partner_version: int,
) -> list[Finding]:
    """Pure verdict -> Finding mapping (design doc section 3.4).

    Every finding this function returns uses ``source=Source.PIPELINE``,
    ``stage=0``, ``score=None``: the existing convention for pipeline-level,
    non-LLM findings (mirrors ``reviewer_independence``/``invalid_story`` in
    ``moderation/pipeline.py``). Messages are prose-free by design
    (instructions and numbers only): the FLAG messages enter the
    PII-guarded repair prompt, so they must never carry story text.

    Args:
        report: The anti-template guard's result for one same-tree pair.
        partner_storybook_id: The comparison partner's story id, for the
            message text.
        partner_version: The comparison partner's version, for the message
            text.

    Returns:
        list[Finding]: One ``Verdict.FLAG`` per ``report.templated_nodes``
            entry plus one whole-story ``Verdict.ADVISORY`` summary on
            ``FAIL`` (the summary alone when ``templated_nodes`` is empty);
            one ``Verdict.ADVISORY`` summary on ``WARN``; ``[]`` on
            ``PASS_``.
    """
    if report.verdict is AntiTemplateVerdict.PASS_:
        return []

    findings: list[Finding] = []
    if report.verdict is AntiTemplateVerdict.FAIL:
        findings.extend(
            Finding(
                stage=0,
                source=Source.PIPELINE,
                category="leaf_diversity",
                verdict=Verdict.FLAG,
                node_id=node_id,
                score=None,
                message=(
                    "leaf prose is too close to this family's previous fill "
                    f"of the same skeleton (storybook {partner_storybook_id} "
                    f"v{partner_version}, masked distance "
                    f"{report.p10_distance:.2f}); re-imagine this passage for "
                    "the current theme with new imagery, action, and sensory "
                    "detail rather than reusing the prior fill's sentences "
                    "with substituted nouns"
                ),
            )
            for node_id in report.templated_nodes
        )

    findings.append(
        Finding(
            stage=0,
            source=Source.PIPELINE,
            category="leaf_diversity_summary",
            verdict=Verdict.ADVISORY,
            node_id=None,
            score=None,
            message=(
                f"anti-template guard {report.verdict.value} vs storybook "
                f"{partner_storybook_id} v{partner_version}: median masked "
                f"distance {report.median_distance:.2f}, p25 "
                f"{report.p25_distance:.2f}, {len(report.templated_nodes)} of "
                f"{report.node_count} nodes below the per-node floor; "
                "advisory only, thresholds uncalibrated per band"
            ),
        )
    )
    return findings


async def run_leaf_diversity_check(
    *,
    session: AsyncSession,
    storybook: Storybook,
    version_row: StorybookVersion,
) -> list[Finding]:
    """Run the anti-template guard against the family's prior same-tree fill.

    Advisory and fail-open by contract: every no-partner, first-use,
    malformed-blob, or structure-drift path returns ``[]`` and the pipeline
    proceeds unchanged. Never raises on data problems; a ``SQLAlchemyError``
    from either read is the one exception that is allowed to propagate (see
    module docstring).

    Args:
        session: The pipeline's own open async session (caller owns the
            transaction).
        storybook: The db row under moderation (``id``, ``family_id``).
        version_row: The persisted version under moderation (``blob``,
            ``skeleton_slug``, ``version``).

    Returns:
        list[Finding]: Findings to append to the moderation report: per-node
            soft FLAGs on an ATG FAIL (repair targets), one story-level
            ADVISORY summary on FAIL or WARN, ``[]`` on PASS or any
            fail-open path.
    """
    # #CRITICAL: data-integrity: the draft under moderation is already visible
    # to same-transaction queries (persist_storybook ran, nothing committed), so
    # the family history MUST exclude storybook.id or the story becomes its own
    # comparison partner and every second fill FAILs at distance ~0.
    # #VERIFY: test_atg_excludes_current_storybook_from_history.
    # #ASSUME: external-resources: two read-only queries on the pipeline's
    # session (history window + one PK blob fetch); data-shaped failures fail
    # open here, but an infrastructure failure (SQLAlchemyError) propagates to
    # the worker's existing rollback + RQ-retry path, because a broken
    # transaction cannot "proceed unchanged" through the submit that follows.
    # #VERIFY: test_atg_partner_blob_missing_is_noop; the propagation choice is
    # recorded in ws1-leaf-diversity-sprint-design.md section 3.5.
    # #EDGE: concurrency: partner rows are immutable versions; no lock taken.
    # #VERIFY: no with_for_update in this module.
    slug = version_row.skeleton_slug
    if slug is None:
        return []

    history = [
        entry
        for entry in await load_family_history(session, storybook.family_id)
        if entry.storybook_id != storybook.id
    ]

    partner = select_atg_comparison_partner(slug, history)
    if partner is None:
        return []

    partner_blob = await load_version_blob(
        session, partner.storybook_id, partner.version
    )
    if partner_blob is None:
        _logger.info(
            "moderation.atg_partner_blob_missing",
            story_id=storybook.id,
            partner_storybook_id=partner.storybook_id,
            partner_version=partner.version,
        )
        return []

    try:
        current = coerce_storybook(version_row.blob)
        partner_fill = coerce_storybook(partner_blob)
    except ValidationError:
        _logger.warning("moderation.atg_blob_invalid", story_id=storybook.id)
        return []

    # Pre-check the structure fingerprint rather than catching
    # anti_template_verdict's raise (design doc section 3.2): a mismatch here
    # is an expected, meaningful production condition (the skeleton was
    # structurally revised between fills), not an error, so it gets an
    # explicit, logged, individually-testable branch instead of an exception
    # path.
    if structure_fingerprint(current) != structure_fingerprint(partner_fill):
        _logger.info(
            "moderation.atg_structure_drift",
            story_id=storybook.id,
            partner_storybook_id=partner.storybook_id,
            partner_version=partner.version,
        )
        return []

    atg = anti_template_verdict(current, partner_fill, brief_a=None, brief_b=None)
    return findings_from_anti_template(
        atg,
        partner_storybook_id=partner.storybook_id,
        partner_version=partner.version,
    )
