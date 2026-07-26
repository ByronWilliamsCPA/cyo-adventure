"""Policy re-screen tooling (register A4 first cut; roadmap Phase 5 / M5).

An admin-triggered sweep that re-runs the deterministic policy/band gate
(``validator.gate.run_gate``) and the Stage-0 moderation classifiers
(``moderation.classifiers.run_classifiers``) over already-PUBLISHED
storybooks, so a moderation-threshold or band-policy change (a content
ceiling edit, a new forbidden ending kind, the PL-22 fail-closed guard, a
newly added classifier bright-line category) can be checked against the
existing catalog without an admin having to reopen every book by hand.

First-cut scope (family-tier; A4's full public-catalog sweep is Phase 9):

- Re-runs ONLY the deterministic gate and the Stage-0 classifiers, never the
  four LLM review stages (safety/readability/coherence/engagement,
  ``moderation.stages``). Those stages judge prose quality and independence,
  which a band-policy or classifier-threshold edit does not change; adding
  their LLM cost/latency to every sweep would buy no signal relevant to what
  triggered the sweep. See ``docs/planning/roadmap.md`` Phase 5 and
  ``docs/planning/capability-register.md`` row A4.
- Never runs the bounded auto-repair the generation pipeline performs
  (``moderation.repair``): repair mutates prose, and a re-screen tool must
  never silently rewrite already-published, already-approved content.
- Every currently-published storybook belongs to the family-tier catalog (the
  public App Store catalog does not exist yet; it is Phase 9/ADR-008), so
  this sweep does not filter on ``Storybook.visibility``: "family-tier" and
  "the current published catalog" are the same set today.

Design decision -- no auto-unpublish:
# #CRITICAL: security: ADR-005 (mandatory human approval) governs BOTH
# directions of the publish decision, not just the original one: a sweep
# that silently archived or hid a book a guardian's child might be mid-story
# on would be exactly the unreviewed, machine-driven content decision
# ADR-005 exists to prevent. ``publishing.state_machine.LEGAL_TRANSITIONS``
# has no ``published -> needs_revision`` (or any other machine-reachable)
# hop; the only way out of ``published`` is the human-only ``archive``
# action (``publishing.service.archive``, admin-gated). This module never
# calls it. A book that now fails is recorded via a pipeline event and
# surfaced in :class:`RescreenSummary` for a human to act on through the
# existing admin archive path.
# #VERIFY: tests/unit/test_rescreen_unit.py::test_flagged_book_is_not_archived
# asserts ``Storybook.status`` is untouched by a flagged verdict.

The rescreen result is deliberately NOT written back onto
``StorybookVersion.moderation_report``:
# #ASSUME: data-integrity: that column is the historical record of the
# screening pass that gated the original ``submit``/``approve`` transitions
# (``publishing.service.submit`` and ``.approve`` both read
# ``moderation_report is None`` as "never screened"); overwriting it with a
# re-screen result computed long after publish would rewrite that history
# for no functional gain, since nothing re-reads moderation_report once a
# story is published. The pipeline event this module writes (below) is the
# durable, admin-queryable record of a re-screen outcome instead.
# #VERIFY: tests/unit/test_rescreen_unit.py::test_rescreen_does_not_mutate_stored_report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import httpx
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.events import EventType, record_event
from cyo_adventure.moderation.classifiers import run_classifiers
from cyo_adventure.moderation.report import Finding, Verdict
from cyo_adventure.moderation.thresholds import ThresholdPolicy, load_threshold_policy
from cyo_adventure.publishing.state_machine import Status
from cyo_adventure.storybook.models import Node
from cyo_adventure.storybook.models import Storybook as StoryModel
from cyo_adventure.storybook.sentinels import (
    find_malformed_sentinels,
    find_sentinels,
    strip_sentinels,
)
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.gate import GateResult, run_gate

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.core.config import Settings
    from cyo_adventure.events import Actor

_logger = get_logger(__name__)

# Network timeout for the classifier HTTP client, mirroring
# moderation/pipeline.py's own ``_run_all_stages`` client construction.
_CLASSIFIER_CLIENT_TIMEOUT = 30.0

Outcome = Literal["passed", "flagged", "error"]


@dataclass(frozen=True, slots=True)
class BookVerdict:
    """One published storybook's re-screen outcome.

    Attributes:
        storybook_id: The story id.
        version: The screened (published) version number, or ``-1`` when the
            book could not even be located (see ``error``).
        outcome: ``"passed"`` (no new findings), ``"flagged"`` (the gate or a
            classifier now objects; the book was left published and needs
            admin attention), or ``"error"`` (the sweep could not screen this
            book; see ``error``).
        reasons: Human-readable finding summaries driving a ``"flagged"``
            outcome. Empty for ``"passed"``/``"error"``.
        error: The exception message for an ``"error"`` outcome, or ``None``.
    """

    storybook_id: str
    version: int
    outcome: Outcome
    reasons: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RescreenSummary:
    """The sweep's aggregate result.

    Attributes:
        checked: Total published books the sweep attempted to screen.
        passed: Count of ``"passed"`` outcomes.
        flagged: Count of ``"flagged"`` outcomes.
        errored: Count of ``"error"`` outcomes.
        results: Per-book verdicts, in the order books were screened.
    """

    checked: int
    passed: int
    flagged: int
    errored: int
    results: list[BookVerdict]


async def _load_published_books(
    session: AsyncSession, storybook_ids: Sequence[str] | None
) -> list[Storybook]:
    """Return published storybooks, optionally scoped to an id allowlist.

    Args:
        session: The request session.
        storybook_ids: When given, restrict the sweep to these ids; ids that
            are not published (or do not exist) are silently omitted, not
            reported as an error, mirroring an ordinary filtered list query.
        None screens every currently-published book.

    Returns:
        list[Storybook]: The matching rows, ordered by id for a deterministic
        sweep order.
    """
    # #ASSUME: concurrency: this SELECT is unlocked (no ``.with_for_update()``),
    # unlike the storybook loads in publishing/service.py and
    # moderation/pipeline.py: those lock because they WRITE ``status``; this
    # sweep never does (see the module docstring's no-auto-unpublish
    # decision), so a concurrent archive()/approve() racing this SELECT is
    # harmless -- at worst a book is screened against a status snapshot that
    # is stale by the time the admin reads the response, which is the same
    # staleness any other list-then-act admin flow already accepts.
    # #VERIFY: tests/unit/test_rescreen_unit.py asserts no with_for_update
    # clause on this statement.
    stmt = select(Storybook).where(Storybook.status == Status.PUBLISHED.value)
    if storybook_ids is not None:
        stmt = stmt.where(Storybook.id.in_(storybook_ids))
    stmt = stmt.order_by(Storybook.id)
    return list((await session.execute(stmt)).scalars().all())


def _gate_reasons(gate_result: GateResult) -> list[str]:
    """Return human-readable reason strings for the gate's blocking findings."""
    return [f"gate {f.rule_id}: {f.message}" for f in gate_result.report.errors]


def _classifier_block_reasons(findings: list[Finding]) -> list[str]:
    """Return reason strings for hard-blocking (bright-line) classifier findings."""
    return [
        f"classifier {f.source.value}/{f.category}: {f.message}"
        for f in findings
        if f.verdict is Verdict.BLOCK
    ]


def _newly_surfaced_findings(
    findings: list[Finding], *, age_band: str, threshold_policy: ThresholdPolicy
) -> list[Finding]:
    """Return advisory findings that now surface under the current threshold policy.

    A classifier finding is either ``BLOCK`` (handled separately, always a
    fail) or ``ADVISORY`` (see moderation/classifiers.py; classifiers never
    emit ``FLAG``). An ``ADVISORY`` finding that the CURRENT
    :class:`ThresholdPolicy` says should surface for this book's band and
    category is exactly the "moderation-threshold change" case A4 exists
    for: a finding that was noise under the old threshold is now considered
    worth a human's attention.

    Args:
        findings: The fresh Stage-0 classifier findings for this book.
        age_band: The story's ``metadata.age_band`` value.
        threshold_policy: The current, freshly loaded threshold policy.

    Returns:
        list[Finding]: The findings that newly surface.
    """
    return [
        f
        for f in findings
        if f.verdict is Verdict.ADVISORY
        and threshold_policy.surfaces(
            age_band=age_band, category=f.category, verdict=f.verdict, score=f.score
        )
    ]


def _newly_surfaced_reasons(surfaced: list[Finding]) -> list[str]:
    """Return human-readable reason strings for newly-surfaced advisory findings."""
    reason = "now surfaces under the current moderation threshold"
    return [f"classifier {f.source.value}/{f.category}: {reason}" for f in surfaced]


# #CRITICAL: security: this is a CONTRACT-FREE subset of
# `check_sentinel_integrity_at_rest` (ADR-023 plan 3.3, sub-task 3b). It
# detects a malformed near-miss sentinel and a well-formed sentinel misplaced
# in a choice label, but deliberately does NOT check that a well-formed
# sentinel's slot id is a declared personalizable slot of this story (the
# `unknown_slot` check that Variant B's full form performs): rescreen re-reads
# an already-PUBLISHED blob with no skeleton/contract reference on this path,
# and the authoritative personalizable-slot declaration for a published book
# is deferred to the future sentinel manifest (plan line ~434, a later
# phase), which this task explicitly does not build. When that manifest
# lands, this function should be replaced by a call to the full
# `check_sentinel_integrity_at_rest`.
# #VERIFY: tests/unit/test_rescreen_unit.py::
# test_malformed_sentinel_flags_rescreen,
# ::test_sentinel_in_choice_label_flags_rescreen, and
# ::test_clean_blob_is_not_flagged_by_sentinel_scan.
def _malformed_sentinel_reasons(text: str, location: str) -> list[str]:
    """Return one reason string per malformed sentinel-shaped near-miss in ``text``."""
    return [
        f"sentinel malformed in {location}: {near_miss!r}"
        for near_miss in find_malformed_sentinels(text)
    ]


def _choice_label_sentinel_reasons(
    label: str, *, node_id: str, choice_id: str
) -> list[str]:
    """Return reasons for a choice label carrying malformed or well-formed sentinels.

    A choice label must never carry a sentinel, well-formed or not (Task 2),
    so both a near-miss and a genuine token are reported.
    """
    location = f"node {node_id} choice {choice_id} label"
    reasons = _malformed_sentinel_reasons(label, location)
    reasons.extend(
        f"sentinel in choice label: node {node_id} choice {choice_id} (slot {slot_id})"
        for slot_id, _value in find_sentinels(label)
    )
    return reasons


def _node_sentinel_corruption_reasons(node: Node) -> list[str]:
    """Return every sentinel-corruption reason found within one node.

    Args:
        node: A parsed node from the published story.

    Returns:
        list[str]: Reasons from the node's body, ending title (if any), and
        every choice label; empty if the node carries no sentinel corruption.
    """
    reasons = _malformed_sentinel_reasons(node.body, f"node {node.id} body")
    if node.ending is not None:
        reasons.extend(
            _malformed_sentinel_reasons(
                node.ending.title, f"node {node.id} ending title"
            )
        )
    for choice in node.choices:
        reasons.extend(
            _choice_label_sentinel_reasons(
                choice.label, node_id=node.id, choice_id=choice.id
            )
        )
    return reasons


def _sentinel_corruption_reasons(story: StoryModel) -> list[str]:
    """Return reason strings for sentinel corruption-at-rest in a published blob.

    Scans every node body, ending title, and choice label for a malformed
    sentinel-shaped near-miss, and every choice label for a well-formed
    sentinel (which must never appear there). See the membership-check
    deferral note above this function.

    Args:
        story: The parsed published story.

    Returns:
        list[str]: One reason string per malformed near-miss or
        in-choice-label sentinel found; empty if the blob carries no
        sentinel corruption (including, trivially, a blob with no
        sentinels at all).
    """
    reasons: list[str] = []
    for node in story.nodes:
        reasons.extend(_node_sentinel_corruption_reasons(node))
    return reasons


@dataclass(frozen=True, slots=True)
class _SweepContext:
    """Bundles the sweep-wide, per-book-invariant collaborators into one value.

    Keeps ``_rescreen_one`` within the project's 4-argument function limit
    (``session``, ``book``, ``ctx``) without splitting one logical "how to
    screen a book right now" bundle across positional/keyword args.
    """

    settings: Settings
    actor: Actor
    threshold_policy: ThresholdPolicy
    client: httpx.AsyncClient


async def _rescreen_one(
    session: AsyncSession, book: Storybook, ctx: _SweepContext
) -> BookVerdict:
    """Re-screen one published storybook's current version.

    Args:
        session: The request session (caller owns the transaction).
        book: The published storybook row.
        ctx: The sweep-wide collaborators (settings, actor, threshold policy,
            shared HTTP client).

    Returns:
        BookVerdict: This book's outcome. Never raises: every failure mode is
        converted to an ``"error"`` outcome so one book's failure cannot
        abort the sweep (see the module docstring and the broad catch below).
    """
    version_number = book.current_published_version
    if version_number is None:
        # #EDGE: data-integrity: publishing.service.approve() always stamps
        # current_published_version in the same flush that sets
        # status="published" (LEGAL_TRANSITIONS has no other path to
        # "published"), so this is unreachable through the app boundary. Guard
        # defensively anyway rather than crash the sweep on a hand-edited or
        # corrupted row.
        return BookVerdict(
            storybook_id=book.id,
            version=-1,
            outcome="error",
            error="published storybook has no current_published_version",
        )
    try:
        version_row = await session.get(StorybookVersion, (book.id, version_number))
        if version_row is None:
            return BookVerdict(
                storybook_id=book.id,
                version=version_number,
                outcome="error",
                error="published version row is missing",
            )

        # #CRITICAL: data-integrity: run_gate accepts a raw mapping and is
        # exception-safe for a malformed blob (validator/gate.py's
        # _parse_storybook catches PydanticValidationError internally and
        # returns a blocked report instead of raising), so this call cannot
        # itself throw for corrupted content -- it will simply flag it.
        # #VERIFY: tests/unit/test_rescreen_unit.py::test_corrupted_blob_flags_via_gate.
        gate_result = run_gate(version_row.blob)
        reasons = _gate_reasons(gate_result) if gate_result.blocked else []

        # The parsed model is needed for node text (classifiers) and the age
        # band (threshold resolution). A parse failure here happens ONLY when
        # the gate's own internal parse already flagged the blob (L1 caught
        # it first, so gate_result.blocked is already True and reasons is
        # already non-empty) -- run_gate's early-return-on-L1-error path never
        # reaches the policy layer for a genuinely malformed document. When
        # that holds, classifiers are simply skipped (there is no node text to
        # screen) and the gate's own reasons still drive the "flagged"
        # outcome below. The `not gate_result.blocked` branch guards the
        # theoretical case run_gate's own docstring calls "should not occur in
        # practice" (a schema-drift parse failure after a clean L1 pass); that
        # is reported as an "error", not silently swallowed as "passed".
        # #VERIFY: tests/unit/test_rescreen_unit.py::
        # test_corrupted_blob_flags_via_gate_without_running_classifiers.
        classifier_findings: list[Finding] = []
        surfaced: list[Finding] = []
        has_classifier_block = False
        try:
            story = StoryModel.model_validate(version_row.blob)
        except PydanticValidationError as exc:
            if not gate_result.blocked:
                return BookVerdict(
                    storybook_id=book.id,
                    version=version_number,
                    outcome="error",
                    error=f"story blob failed schema validation: {exc}"[:500],
                )
        else:
            # #CRITICAL: security: a personalizable sentinel (ADR-023 plan
            # 3.3, ``{~SLOTID:GenericWord~}``) must never reach a classifier
            # trained on ordinary prose: an unstripped token would read as
            # unfamiliar noise and could skew a score in either direction,
            # breaking score comparability across the personalization
            # migration boundary (plan risk R12, MANDATORY). Only the copy
            # fed to classification is stripped here; ``version_row.blob``
            # (the stored, published content) is never mutated.
            # #VERIFY: tests/unit/test_rescreen_unit.py::
            # test_classifier_input_is_stripped_of_sentinels and
            # ::test_sentinel_free_body_is_unaffected_by_strip.
            nodes = [(node.id, strip_sentinels(node.body)) for node in story.nodes]
            # #CRITICAL: external-resources: run_classifiers is the same
            # helper moderation/pipeline.py uses; a missing key skips that
            # classifier entirely (both None -> []), and a per-call HTTP
            # failure is caught INSIDE run_classifiers and logged, never
            # raised. This mirrors "how moderation/pipeline.py handles
            # provider absence" per the task brief; no separate
            # provider-absence branch is needed here.
            # #VERIFY: tests/unit/test_moderation_classifiers.py covers the
            # per-call catch; test_rescreen_unit.py::
            # test_missing_classifier_keys_skips_classifiers_not_error.
            classifier_findings = await run_classifiers(
                nodes=nodes,
                openai_key=ctx.settings.openai_api_key,
                perspective_key=ctx.settings.perspective_api_key,
                client=ctx.client,
            )
            has_classifier_block = any(
                f.verdict is Verdict.BLOCK for f in classifier_findings
            )
            surfaced = _newly_surfaced_findings(
                classifier_findings,
                age_band=story.metadata.age_band.value,
                threshold_policy=ctx.threshold_policy,
            )
            reasons.extend(_classifier_block_reasons(classifier_findings))
            reasons.extend(_newly_surfaced_reasons(surfaced))
            reasons.extend(_sentinel_corruption_reasons(story))

        outcome: Outcome = "flagged" if reasons else "passed"
        block_count = sum(1 for f in classifier_findings if f.verdict is Verdict.BLOCK)
        overall_verdict = _overall_verdict(
            gate_blocked=gate_result.blocked,
            classifier_blocked=has_classifier_block,
            newly_surfaced=bool(surfaced),
        )

        # #CRITICAL: data-integrity: this is the durable, admin-queryable
        # record of the re-screen outcome (spec D3: PII-free, closed
        # vocabulary only). Reusing MODERATION_COMPLETED (rather than adding a
        # new EventType) avoids a DB migration for this first cut: its
        # existing payload allowlist ({"overall_verdict", "repaired",
        # "counts"}) already fits a moderation outcome exactly, and
        # entity_type "storybook_version" + entity_id "{id}:{version}" match
        # moderation/pipeline.py's own convention. to_state is the book's
        # CURRENT (unchanged) status: a re-screen never transitions it (see
        # the module docstring's no-auto-unpublish decision).
        # #VERIFY: tests/unit/test_rescreen_unit.py::test_writes_pipeline_event_per_book.
        await record_event(
            session,
            ctx.actor,
            entity_type="storybook_version",
            entity_id=f"{book.id}:{version_number}",
            event_type=EventType.MODERATION_COMPLETED,
            to_state=book.status,
            payload={
                "overall_verdict": overall_verdict,
                "repaired": False,
                "counts": {
                    "gate_errors": len(gate_result.report.errors),
                    "classifier_block": block_count,
                    "classifier_advisory": len(classifier_findings) - block_count,
                },
            },
        )
        return BookVerdict(
            storybook_id=book.id,
            version=version_number,
            outcome=outcome,
            reasons=reasons,
        )
    # #CRITICAL: external-resources / data-integrity: the task brief requires
    # that one book's failure (a classifier provider outage that somehow
    # escapes run_classifiers' own per-call catch, a session/DB error writing
    # this book's event, an unexpected shape in a legacy blob) never aborts
    # the sweep; every other book must still be screened and every already-
    # screened book's event must still stand. This mirrors the established
    # "best-effort, log and continue" pattern at api/generation.py::
    # _enqueue_safely and api/story_requests.py's screening call.
    # #VERIFY: tests/unit/test_rescreen_unit.py::
    # test_provider_error_on_one_book_does_not_abort_sweep.
    except Exception as exc:  # noqa: BLE001 -- isolate one book's failure, see above
        _logger.warning(
            "rescreen.book_failed",
            storybook_id=book.id,
            version=version_number,
            error=str(exc)[:500],
        )
        return BookVerdict(
            storybook_id=book.id,
            version=version_number,
            outcome="error",
            error=str(exc)[:500],
        )


def _overall_verdict(
    *, gate_blocked: bool, classifier_blocked: bool, newly_surfaced: bool
) -> str:
    """Return the single verdict string for the event payload.

    Args:
        gate_blocked: Whether the deterministic policy/band gate blocked.
        classifier_blocked: Whether a Stage-0 classifier bright-line fired.
        newly_surfaced: Whether an advisory finding now surfaces under the
            current threshold policy (and neither of the above fired).

    Returns:
        str: ``"block"`` when the gate or a classifier bright-line blocked,
        ``"flag"`` when only a newly-surfaced advisory triggered, otherwise
        ``"pass"``.
    """
    if gate_blocked or classifier_blocked:
        return Verdict.BLOCK.value
    if newly_surfaced:
        return Verdict.FLAG.value
    return Verdict.PASS.value


async def rescreen_published_books(
    session: AsyncSession,
    *,
    settings: Settings,
    actor: Actor,
    storybook_ids: Sequence[str] | None = None,
) -> RescreenSummary:
    """Re-run the policy gate and Stage-0 classifiers over published books.

    Family-tier first cut (register A4): screens every currently-published
    storybook (or the given subset). Never mutates a storybook's status or
    its stored content; see the module docstring for the no-auto-unpublish
    and no-report-overwrite design decisions.

    Args:
        session: The request session (caller owns the transaction; each
            per-book pipeline event is flushed into it, so a caller-level
            commit or rollback governs the whole sweep's durability).
        settings: Application settings (classifier credentials).
        actor: The admin actor to stamp on every pipeline event this sweep
            writes.
        storybook_ids: When given, restrict the sweep to these ids; ``None``
            (the default) screens every published book.

    Returns:
        RescreenSummary: The aggregate counts plus every book's verdict.
    """
    books = await _load_published_books(session, storybook_ids)
    threshold_policy = await load_threshold_policy(session)

    async with httpx.AsyncClient(timeout=_CLASSIFIER_CLIENT_TIMEOUT) as client:
        sweep_ctx = _SweepContext(
            settings=settings,
            actor=actor,
            threshold_policy=threshold_policy,
            client=client,
        )
        results = [await _rescreen_one(session, book, sweep_ctx) for book in books]

    passed = sum(1 for r in results if r.outcome == "passed")
    flagged = sum(1 for r in results if r.outcome == "flagged")
    errored = sum(1 for r in results if r.outcome == "error")
    return RescreenSummary(
        checked=len(results),
        passed=passed,
        flagged=flagged,
        errored=errored,
        results=results,
    )
