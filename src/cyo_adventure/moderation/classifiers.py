"""Stage 0: deterministic classifier pre-filter (OpenAI Moderation).

The classifier is optional: a missing key skips it. Bright-line categories produce
a hard ``BLOCK`` finding (the pipeline routes straight to auto_reject, no LLM spend);
graded categories at or above ``_ADVISORY_SCORE_FLOOR`` produce non-blocking
``ADVISORY`` findings recorded in the report for the guardian (they do not
currently feed the Stage 1 prompt). Sub-floor graded scores are classifier
noise and are dropped, except that OpenAI's own boolean flag for a category
bypasses the floor (a provider-flagged category is always recorded).

Google Perspective was retired as a Stage-0 signal source (ratified sunset):
``_run_perspective``/``_perspective_attribute_finding`` and the
``perspective_key`` plumbing through ``run_classifiers`` are gone. ``Source.PERSPECTIVE``
itself is kept on the ``Source`` enum in ``moderation/report.py`` (not this module)
purely so historical persisted reports that carry a Perspective finding still
deserialize; nothing in this module produces a new one. ``PERSPECTIVE_URL`` and
``PERSPECTIVE_ATTRIBUTES`` below are kept for the same reason a different consumer
needs them: ``scripts/capture_stage0_baseline.py`` independently probes Perspective
directly (not through this module's classifier machinery) to freeze its raw scores
before Google's 2026-12-31 API sunset; that script is unrelated to the live gate.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

from cyo_adventure.moderation.report import Finding, FindingSeverity, Source, Verdict
from cyo_adventure.utils.logging import get_logger

_logger = get_logger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/moderations"
_OPENAI_MODEL = "omni-moderation-latest"
_CLASSIFIER_TIMEOUT = 20.0

# Perspective's endpoint and the exact attribute set the retired live classifier
# used to request. The live gate no longer calls Perspective at all (see the
# module docstring); these constants are kept public (not underscore-prefixed)
# solely because scripts/capture_stage0_baseline.py imports them to probe the
# same endpoint and attributes this pipeline historically used, for its own
# pre-sunset calibration capture. Do not delete without updating that script.
#
# #CRITICAL: security: the key goes in the x-goog-api-key header, never this
# URL's query string. See the equivalent note in scripts/capture_stage0_baseline.py,
# the only remaining caller.
PERSPECTIVE_URL = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
PERSPECTIVE_ATTRIBUTES: tuple[str, ...] = (
    "SEXUALLY_EXPLICIT",
    "SEVERE_TOXICITY",
    "THREAT",
    "TOXICITY",
    "PROFANITY",
    "IDENTITY_ATTACK",
    "INSULT",
)

# Graded scores below this floor are dropped from the advisory surface: OpenAI
# returns a nonzero float for every category on every call, so without a floor
# every node emits every category as an advisory finding and the review
# surface reads as fully flagged. OpenAI's own boolean flag bypasses the floor;
# advisories never gate (report.has_soft_flag counts FLAG only), so the floor
# is report hygiene, not a safety relaxation.
#
# This rationale originally cited an observed Perspective ceiling of ~6e-4 on
# clean children's prose, back when Perspective was still a Stage-0 signal
# source here (now retired; see the module docstring). The 2026-08-01 Stage-0
# baseline at docs/planning/safety/stage0-baseline-2026-08-01.json refutes that
# figure for Perspective's own attributes, which is now moot for this module
# but still informs scripts/capture_stage0_baseline.py's own calibration work.
#
# Recalibrated 2026-08-25 against the OpenAI-only slice of that same baseline:
# no single scalar in {0.01, 0.02, 0.05, 0.10} satisfies both the clean-noise
# target (<= 0.2 advisories/node; only 0.10 clears it) and zero adversarial-
# signal loss (0.10 loses 10 of 14 pairs, and the clean noise it removes is
# concentrated in violence/violence-graphic while the losses it causes hit
# self-harm*/sexual*). The owner ruled to keep 0.01 and move to per-category
# floors instead of a single scalar; tracked at UW-C378 in
# docs/planning/unscheduled-work-register.md.
_ADVISORY_SCORE_FLOOR = 0.01

# Category slug for a "the automated net was down" advisory finding. It never
# gates (ADVISORY), but it makes a classifier outage or unconfigured key visible
# to the human reviewer, who otherwise cannot distinguish a clean report from
# one produced with the classifiers off.
_DEGRADED_CATEGORY = "classifier_degraded"

# Category slug for incomplete bright-line coverage: some nodes were never
# screened by a configured classifier. Unlike _DEGRADED_CATEGORY this is a FLAG,
# because "we did not look at 93% of this book" is a gating fact, not a note.
_INCOMPLETE_COVERAGE_CATEGORY = "classifier_coverage_incomplete"

# A transient 429/5xx on one node must not cost the rest of the book its
# bright-line screening, so each node's call is retried with backoff before the
# node is recorded as unscreened. Kept short: the caller is inside a request or
# a job, and the circuit breaker below is what handles a genuinely down provider.
_RETRY_BACKOFF_SECONDS: tuple[float, ...] = (0.5, 2.0)

# After this many CONSECUTIVE failures a classifier is treated as down and the
# remaining nodes are recorded as unscreened rather than retried one by one. At
# ceiling scale (746 nodes) hammering a rate-limited provider for every node is
# both futile and hostile; the FLAG is what makes the shortfall visible.
_MAX_CONSECUTIVE_FAILURES = 3

# Number of unscreened node ids named in the coverage finding's message. The
# full count is always reported; the ids are a sample so the message stays
# readable when hundreds of nodes are affected.
_COVERAGE_SAMPLE_SIZE = 10


def _severity_from_score(score: float) -> FindingSeverity:
    """Map a classifier probability to a surface ranking band (design doc 2.1)."""
    if score >= 0.8:
        return FindingSeverity.HIGH
    if score >= 0.5:
        return FindingSeverity.MEDIUM
    return FindingSeverity.LOW


# Not an error state, a control-flow signal: N818 (error-suffix naming) does
# not apply to this exception, so its bare name is intentional.
class ClassifierUnavailable(Exception):  # noqa: N818
    """A classifier call failed (HTTP/parse error) so the run is degraded.

    Raised by an individual classifier so :func:`run_classifiers` can record one
    degraded advisory per classifier rather than one per node, and stop hammering
    a down provider for the remaining nodes.
    """

    def __init__(self, source: Source, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(reason)


def _degraded_finding(source: Source, reason: str) -> Finding:
    """Build the whole-story advisory finding that flags a degraded classifier."""
    return Finding(
        stage=0,
        source=source,
        category=_DEGRADED_CATEGORY,
        node_id=None,
        verdict=Verdict.ADVISORY,
        score=None,
        message=f"{source.value} classifier unavailable: {reason}",
        structural=True,
        severity=FindingSeverity.MEDIUM,
    )


def _incomplete_coverage_finding(
    source: Source, unscreened: Sequence[str], total: int
) -> Finding:
    """Build the whole-story FLAG finding for incomplete bright-line coverage.

    A ``FLAG`` rather than an ``ADVISORY`` on purpose: an advisory does not gate,
    so a report produced with most of the book unscreened would reach
    ``in_review`` looking exactly like a fully-screened clean one. The categories
    Stage 0 exists to catch (sexual/minors, self-harm instructions,
    illicit/violent) are precisely the ones that must not be sampled.

    Args:
        source: The classifier whose coverage fell short.
        unscreened: Node ids that classifier never screened.
        total: Total nodes that should have been screened.

    Returns:
        Finding: A whole-story soft-gating finding naming the shortfall.
    """
    sample = ", ".join(unscreened[:_COVERAGE_SAMPLE_SIZE])
    if len(unscreened) > _COVERAGE_SAMPLE_SIZE:
        sample += f", ... (+{len(unscreened) - _COVERAGE_SAMPLE_SIZE} more)"
    return Finding(
        stage=0,
        source=source,
        category=_INCOMPLETE_COVERAGE_CATEGORY,
        node_id=None,
        verdict=Verdict.FLAG,
        score=None,
        message=(
            f"{source.value} screened {total - len(unscreened)} of {total} nodes; "
            f"{len(unscreened)} node(s) were never bright-line screened and the "
            f"report cannot be read as clean for them: {sample}"
        ),
        structural=True,
        severity=FindingSeverity.HIGH,
    )


# Bright-line OpenAI categories: any True flag is an immediate hard block.
_OPENAI_BRIGHTLINE: frozenset[str] = frozenset(
    {
        "sexual",
        "sexual/minors",
        "self-harm/instructions",
        "self-harm/intent",
        "illicit/violent",
        "hate/threatening",
        "harassment/threatening",
    }
)


@dataclass
class _CoverageState:
    """Per-classifier screening outcome across the whole story.

    Attributes:
        reason: The first failure reason seen, or ``None`` if the classifier
            never failed. Drives the existing degraded advisory.
        unscreened: Node ids this classifier never returned a verdict for,
            whether because every retry failed or because the circuit breaker
            had already opened.
        consecutive_failures: Failure run length, reset by any success. The
            circuit opens at ``_MAX_CONSECUTIVE_FAILURES``.
    """

    reason: str | None = None
    unscreened: list[str] = field(default_factory=list)
    consecutive_failures: int = 0

    @property
    def circuit_open(self) -> bool:
        """Whether this classifier is being treated as down."""
        return self.consecutive_failures >= _MAX_CONSECUTIVE_FAILURES


async def _screen_one(
    state: _CoverageState,
    node_id: str,
    call: Callable[[], Awaitable[list[Finding]]],
) -> list[Finding]:
    """Screen one node with one classifier, retrying a transient failure.

    A node that cannot be screened is recorded in ``state.unscreened`` and the
    loop moves on, so one bad call costs one node's coverage instead of the whole
    remainder of the book. Once the circuit is open the call is skipped entirely
    and the node is still recorded, which is what keeps the reported shortfall
    honest for a provider that is genuinely down.

    Args:
        state: The classifier's coverage state, mutated in place.
        node_id: The node being screened.
        call: Zero-argument coroutine factory performing the classifier call.

    Returns:
        list[Finding]: Findings for this node, empty when it could not be screened.
    """
    if state.circuit_open:
        state.unscreened.append(node_id)
        return []
    # One initial attempt plus one per backoff delay.
    for attempt in range(len(_RETRY_BACKOFF_SECONDS) + 1):
        try:
            findings = await call()
        except ClassifierUnavailable as exc:
            if attempt < len(_RETRY_BACKOFF_SECONDS):
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS[attempt])
                continue
            # Record the reason only when the node is actually abandoned, not on
            # a transient attempt that a later retry recovers from; otherwise a
            # recovered node would still stamp state.reason and misreport the run
            # as degraded.
            state.reason = state.reason or exc.reason
            state.consecutive_failures += 1
            state.unscreened.append(node_id)
            return []
        else:
            state.consecutive_failures = 0
            return findings
    # Unreachable: the loop either returns findings or records the node.
    return []


async def _screen_all_nodes(
    nodes: Sequence[tuple[str, str]],
    *,
    openai_key: str | None,
    client: httpx.AsyncClient,
) -> tuple[list[Finding], _CoverageState]:
    """Run OpenAI over every node, one call per node.

    Extracted from :func:`run_classifiers` (S3776): isolates the per-node
    try/except loop, the function's single biggest nesting contributor,
    behind one call. Perspective was retired as a Stage-0 signal source
    (ratified sunset); this once ran OpenAI and Perspective side by side.

    A per-node failure no longer disables OpenAI for the rest of the book:
    each call is retried with backoff, an unscreenable node is recorded in
    the returned coverage state, and only a run of consecutive failures opens
    the circuit. The caller turns any shortfall into a gating finding.

    Args:
        nodes: ``(node_id, prose)`` pairs to screen.
        openai_key: OpenAI Moderation key, or ``None`` to skip OpenAI.
        client: An httpx async client (injected for testability).

    Returns:
        tuple[list[Finding], _CoverageState]: All findings produced, plus
            OpenAI's coverage state (failure reason, if any, and the node ids
            it never screened).
    """
    findings: list[Finding] = []
    openai = _CoverageState()
    for node_id, prose in nodes:
        if openai_key:
            findings.extend(
                await _screen_one(
                    openai,
                    node_id,
                    lambda nid=node_id, text=prose: _run_openai(
                        nid, text, openai_key, client
                    ),
                )
            )
    return findings, openai


async def run_classifiers(  # noqa: PLR0913
    *,
    nodes: Sequence[tuple[str, str]],
    openai_key: str | None,
    client: httpx.AsyncClient,
    require_classifiers: bool = False,
    report_coverage: bool = True,
) -> list[Finding]:
    """Run available classifiers over each node's prose and collect findings.

    Args:
        nodes: ``(node_id, prose)`` pairs to screen.
        openai_key: OpenAI Moderation key, or ``None`` to skip OpenAI.
        client: An httpx async client (injected for testability).
        require_classifiers: When True, an unconfigured classifier (``None``
            key) also produces a degraded advisory. Deployed tiers pass True so
            a missing key is visible to the reviewer; local/dev leave it False,
            where an absent key is an intentional skip.
        report_coverage: When True (the default, and what every child-facing
            story screen uses), an unscreened node produces a gating
            ``classifier_coverage_incomplete`` FLAG. The single-item intake
            screen passes False: with one item the finding only restates the
            degraded advisory, and request intake is documented fail-open with
            the guardian as the human gate.

    Returns:
        A flat list of findings across all nodes. OpenAI is the only
        classifier this function calls: Google Perspective was retired as a
        Stage-0 signal source (ratified sunset), so no finding this function
        returns ever carries ``Source.PERSPECTIVE``. A classifier that fails
        contributes exactly one ``classifier_degraded`` advisory (whole-story)
        instead of failing silently, and additionally a
        ``classifier_coverage_incomplete`` **FLAG** naming every node it never
        screened, so a partially-screened report cannot be mistaken for a clean
        one. Individual failures are retried with backoff, and only a run of
        consecutive failures stops the classifier for the remaining nodes.
    """
    # #CRITICAL: external-resource: classifier APIs are network calls; a failure
    # must not crash the pipeline (the LLM stages still gate). It must also not
    # be invisible: a silent [] on a down provider looks identical to a
    # genuinely clean report on a kids'-content pipeline whose reviewer
    # calibration assumes the automated net ran. A failure or unset key
    # surfaces a non-gating ADVISORY so the review UI can show it.
    # #VERIFY: test_openai_http_error_yields_degraded_advisory,
    # test_require_classifiers_flags_unset_keys.
    # #CRITICAL: security: incomplete bright-line coverage must GATE, not merely
    # annotate. Before this, the first failure disabled the classifier for every
    # remaining node and the only trace was one ADVISORY, so a report with 93% of
    # a 746-node book unscreened was indistinguishable from a clean one and both
    # submit() and approve() passed it.
    # #VERIFY: test_partial_failure_flags_incomplete_coverage and
    # test_unscreened_nodes_are_named_in_the_coverage_finding.
    findings, openai = await _screen_all_nodes(
        nodes,
        openai_key=openai_key,
        client=client,
    )

    if openai.reason is None and require_classifiers and openai_key is None:
        openai.reason = "not configured"

    total = len(nodes)
    if openai.reason is not None:
        _logger.warning(
            "classifier_degraded", source=Source.OPENAI.value, reason=openai.reason
        )
        findings.append(_degraded_finding(Source.OPENAI, openai.reason))
    if openai.unscreened and report_coverage:
        _logger.error(
            "classifier_coverage_incomplete",
            source=Source.OPENAI.value,
            unscreened=len(openai.unscreened),
            total=total,
        )
        findings.append(
            _incomplete_coverage_finding(Source.OPENAI, openai.unscreened, total)
        )
    return findings


# ---------------------------------------------------------------------------
# Internal narrowing helpers
# ---------------------------------------------------------------------------


def _as_str_map(obj: object) -> dict[str, object] | None:
    """Return *obj* typed as ``dict[str, object]`` if it is one, else ``None``."""
    if not isinstance(obj, dict):
        return None
    # Cast to a typed dict so iteration yields str keys and object values.
    # JSON dicts always have str keys; the cast is safe for all API responses.
    return cast("dict[str, object]", obj)


def _narrow_bool_map(raw: object) -> dict[str, bool]:
    """Extract ``{str: bool}`` entries from *raw*, skipping non-conforming items."""
    typed = _as_str_map(raw)
    if typed is None:
        return {}
    return {k: v for k, v in typed.items() if isinstance(v, bool)}


def _narrow_float_map(raw: object) -> dict[str, float]:
    """Extract ``{str: float}`` entries from *raw*, skipping non-conforming items."""
    typed = _as_str_map(raw)
    if typed is None:
        return {}
    return {k: float(v) for k, v in typed.items() if isinstance(v, (int, float))}


def _openai_finding(
    node_id: str, category: str, flagged: bool, score: float
) -> Finding | None:
    """Build a single OpenAI Finding, or return None when there is nothing to report."""
    # #EDGE: data integrity: httpx's .json() uses json.loads with
    # allow_nan=True, so a non-finite score (NaN/Infinity) survives the
    # isinstance(_, (int, float)) guard upstream. Passed straight through it
    # would make Finding.__post_init__ raise ValueError (its range check is
    # false for NaN), matching the Perspective crash tracked in #144. Treat a
    # non-finite score as an absent score: drop it from the graded-floor
    # comparison and report score=None rather than crashing, while still
    # honoring OpenAI's independent boolean flagged signal so a flagged
    # bright-line category is never lost to a garbage score.
    # #VERIFY: test_classifiers covers flagged and unflagged non-finite scores.
    if math.isfinite(score):
        reportable_score: float | None = score
        over_floor = score >= _ADVISORY_SCORE_FLOOR
    else:
        _logger.warning(
            "openai_score_non_finite",
            node_id=node_id,
            category=category,
            flagged=flagged,
        )
        reportable_score = None
        over_floor = False
    # #ASSUME: data-integrity: a scored finding's severity is normally
    # derived from its own score (design doc 2.1), but reportable_score can
    # legitimately be None here (the non-finite-score guard above). A
    # flagged bright-line/advisory signal with an unreadable score is still
    # a real provider signal, not a low-confidence one, so it degrades to
    # HIGH rather than silently losing its severity band.
    # #VERIFY: test_classifiers covers a flagged non-finite-score OpenAI
    # finding still carrying severity=HIGH.
    severity = (
        _severity_from_score(reportable_score)
        if reportable_score is not None
        else FindingSeverity.HIGH
    )
    if flagged and category in _OPENAI_BRIGHTLINE:
        return Finding(
            stage=0,
            source=Source.OPENAI,
            category=category,
            node_id=node_id,
            verdict=Verdict.BLOCK,
            score=reportable_score,
            message=f"OpenAI bright-line category '{category}' flagged",
            severity=severity,
        )
    if flagged or over_floor:
        return Finding(
            stage=0,
            source=Source.OPENAI,
            category=category,
            node_id=node_id,
            verdict=Verdict.ADVISORY,
            score=reportable_score,
            severity=severity,
            message=f"OpenAI graded signal for '{category}'",
        )
    return None


# ---------------------------------------------------------------------------
# Classifier implementations
# ---------------------------------------------------------------------------


async def _run_openai(
    node_id: str, prose: str, key: str, client: httpx.AsyncClient
) -> list[Finding]:
    """Call OpenAI Moderation for one node; bright-line -> BLOCK, else graded."""
    try:
        response = await client.post(
            _OPENAI_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": _OPENAI_MODEL, "input": prose},
            timeout=_CLASSIFIER_TIMEOUT,
        )
        response.raise_for_status()
        data: object = cast("object", response.json())
    except (httpx.HTTPError, ValueError) as exc:
        _logger.warning("openai_moderation_failed", node_id=node_id, error=str(exc))
        raise ClassifierUnavailable(Source.OPENAI, str(exc)) from exc

    # #CRITICAL: external-resources: an OpenAI response-shape change (top not a
    # dict, missing/empty results, a non-dict result, or missing categories)
    # used to log a warning and silently return [], indistinguishable from a
    # genuinely clean node (gap G11). Each malformed shape now raises
    # ClassifierUnavailable so it flows through the same retry/circuit-breaker
    # path as an HTTP failure and lands as a structural degraded-classifier
    # finding instead of vanishing.
    # #VERIFY: tests/unit/test_moderation_classifiers.py::
    # test_openai_non_dict_top_level_response_raises_classifier_unavailable
    # and the sibling malformed-shape tests.
    top = _as_str_map(data)
    if top is None:
        _logger.warning(
            "openai_moderation_malformed", node_id=node_id, reason="top not a dict"
        )
        raise ClassifierUnavailable(Source.OPENAI, "response top-level was not a dict")

    results = top.get("results")
    if not isinstance(results, list) or not results:
        _logger.warning(
            "openai_moderation_malformed",
            node_id=node_id,
            reason="results missing or empty",
        )
        raise ClassifierUnavailable(
            Source.OPENAI, "response 'results' missing or empty"
        )

    result = _as_str_map(cast("object", results[0]))
    if result is None:
        _logger.warning(
            "openai_moderation_malformed",
            node_id=node_id,
            reason="result[0] not a dict",
        )
        raise ClassifierUnavailable(Source.OPENAI, "response result[0] was not a dict")

    categories = _narrow_bool_map(result.get("categories"))
    scores = _narrow_float_map(result.get("category_scores"))
    if not categories:
        _logger.warning(
            "openai_moderation_malformed",
            node_id=node_id,
            reason="categories missing or not a dict",
        )
        raise ClassifierUnavailable(
            Source.OPENAI, "response 'categories' missing or not a dict"
        )

    findings: list[Finding] = []
    for category, flagged in categories.items():
        finding = _openai_finding(node_id, category, flagged, scores.get(category, 0.0))
        if finding is not None:
            findings.append(finding)
    return findings
