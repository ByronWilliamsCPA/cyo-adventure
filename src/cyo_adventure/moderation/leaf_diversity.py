"""Wire the anti-template guard (ATG) into the moderation pipeline (WS-1 D1).

Advisory and fail-open by contract (see
``docs/planning/ws1-leaf-diversity-sprint-design.md`` section 3): every
no-partner, first-use, malformed-blob, or structure-drift path proceeds
unchanged rather than raising. The no-partner and first-use paths return an
empty finding list. The malformed-blob and structure-drift paths return the
POSITION-INDEPENDENT sibling-gram findings instead (R-3): those are computed
from raw text before the blob is coerced, so they survive a document the
structural comparison cannot read, and suppressing them would discard a
signal that is still valid. The guard never
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

from typing import TYPE_CHECKING, Any

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.grams import pairwise_overlap
from cyo_adventure.diversity.history import load_family_history, load_version_blob
from cyo_adventure.diversity.leaf import anti_template_verdict
from cyo_adventure.diversity.normalize import coerce_storybook
from cyo_adventure.diversity.query import select_atg_comparison_partner
from cyo_adventure.diversity.report import AntiTemplateReport, AntiTemplateVerdict
from cyo_adventure.diversity.structure import structure_fingerprint
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.db.models import Storybook, StorybookVersion
    from cyo_adventure.diversity.history import HistoryEntry

_logger = get_logger(__name__)

SIBLING_GRAM_ADVISORY_PER_1000 = 60.0
"""Body-only shared 4-grams per 1000 words above which a reviewer is told.

Provisional and deliberately loose. The anchors, measured 2026-08-22 on the
committed cave-of-echoes trio: three genuinely re-themed sibling fills of one
skeleton score 22.20, 33.74 and 38.41, and a noun-swap near-copy of one of
them scores 931.93. This floor sits at roughly 1.6x the highest acceptable
observation and more than an order of magnitude below the copy ceiling, so it
reports the shape it was built for and stays quiet on the shape the WS-2
programme already calls a success.

It is NOT a calibrated blocking threshold and must not become one on this
evidence: four pairs from one skeleton cannot fix a production cutoff. The
measurement is logged on every run regardless of the verdict
(``moderation.sibling_gram_overlap``), so the real distribution accumulates
and a later decision can be made from it rather than from this guess.
"""


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


def _sibling_gram_findings(
    current_blob: Mapping[str, Any],
    partner_blob: Mapping[str, Any],
    *,
    story_id: str,
    partner: HistoryEntry,
) -> list[Finding]:
    """Measure verbatim-wording overlap with the partner fill and report it.

    Runs on the RAW blobs, before ``coerce_storybook``, so it survives the two
    paths that end the ATG early (an unparseable partner, a drifted structure).
    Overlap is position-independent: two fills reuse wording whether or not
    the tree still lines up, which is exactly when the ATG's node-aligned
    distances go blind and this channel is the only one left.

    Choice labels are excluded. The skeleton hands every sibling the same
    labels, so counting them measures the tree rather than the fill; on the
    calibration trio they alone move the re-themed pairs from 22-38 (silent)
    to 61-80 (a false alarm). See ``diversity/grams.py``.

    #ASSUME: data-integrity: either blob may be malformed; ``story_text``
    degrades to empty text rather than raising, matching this module's
    fail-open contract.
    #VERIFY: tests/unit/test_diversity_grams.py::test_story_text_degrades_malformed_shapes_to_no_text

    Args:
        current_blob: The raw blob of the fill under moderation.
        partner_blob: The raw blob of the family's prior same-skeleton fill.
        story_id: The current story's id, for the log line.
        partner: The selected comparison partner, for the message and log.

    Returns:
        list[Finding]: One story-level ``Verdict.ADVISORY`` above
            :data:`SIBLING_GRAM_ADVISORY_PER_1000`, otherwise ``[]``. Never a
            ``FLAG``: a FLAG would enter the pipeline's single bounded repair,
            and no threshold here is calibrated well enough to spend it.
    """
    overlap = pairwise_overlap(current_blob, partner_blob, include_choice_labels=False)
    _logger.info(
        "moderation.sibling_gram_overlap",
        story_id=story_id,
        partner_storybook_id=partner.storybook_id,
        partner_version=partner.version,
        shared_grams=overlap.shared,
        mean_words=round(overlap.mean_words, 1),
        per_1000=round(overlap.per_1000, 2),
        threshold=SIBLING_GRAM_ADVISORY_PER_1000,
    )
    if overlap.per_1000 <= SIBLING_GRAM_ADVISORY_PER_1000:
        return []
    return [
        Finding(
            stage=0,
            source=Source.PIPELINE,
            category="sibling_gram_overlap",
            verdict=Verdict.ADVISORY,
            node_id=None,
            score=None,
            message=(
                f"this fill shares {overlap.shared} distinct four-word "
                f"phrases with storybook {partner.storybook_id} "
                f"v{partner.version}, the family's previous fill of the same "
                f"skeleton: {overlap.per_1000:.1f} per 1000 words against an "
                f"advisory line of {SIBLING_GRAM_ADVISORY_PER_1000:.0f} "
                "(choice labels excluded, since the skeleton supplies those "
                "to both). Read the two side by side and confirm the wording "
                "was re-imagined rather than reused; advisory only, "
                "threshold provisional"
            ),
        )
    ]


async def run_leaf_diversity_check(
    *,
    session: AsyncSession,
    storybook: Storybook,
    version_row: StorybookVersion,
) -> list[Finding]:
    """Run the anti-template guard against the family's prior same-tree fill.

    Advisory and fail-open by contract: every no-partner, first-use,
    malformed-blob, or structure-drift path proceeds unchanged rather than
    raising. The first two return ``[]``; the malformed-blob and
    structure-drift paths return the sibling-gram findings, which are computed
    from raw text and stay valid when the structural comparison cannot run.
    Never raises on data problems; a ``SQLAlchemyError``
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
            ADVISORY summary on FAIL or WARN, and the sibling-gram ADVISORY
            when the gram rate clears its threshold. ``[]`` on a clean PASS
            and on the no-partner and first-use paths; the malformed-blob and
            structure-drift paths return whatever the sibling-gram channel
            produced, which may be non-empty.
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

    gram_findings = _sibling_gram_findings(
        version_row.blob,
        partner_blob,
        story_id=storybook.id,
        partner=partner,
    )

    try:
        current = coerce_storybook(version_row.blob)
        partner_fill = coerce_storybook(partner_blob)
    except ValidationError:
        _logger.warning("moderation.atg_blob_invalid", story_id=storybook.id)
        return gram_findings

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
        return gram_findings

    atg = anti_template_verdict(current, partner_fill, brief_a=None, brief_b=None)
    return gram_findings + findings_from_anti_template(
        atg,
        partner_storybook_id=partner.storybook_id,
        partner_version=partner.version,
    )
