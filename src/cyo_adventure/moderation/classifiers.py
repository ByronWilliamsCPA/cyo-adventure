"""Stage 0: deterministic classifier pre-filter (OpenAI Moderation + Perspective).

Each classifier is optional: a missing key skips it. Bright-line categories produce
a hard ``BLOCK`` finding (the pipeline routes straight to auto_reject, no LLM spend);
graded categories at or above ``_ADVISORY_SCORE_FLOOR`` produce non-blocking
``ADVISORY`` findings recorded in the report for the guardian (they do not
currently feed the Stage 1 prompt). Sub-floor graded scores are classifier
noise and are dropped, except that OpenAI's own boolean flag for a category
bypasses the floor (a provider-flagged category is always recorded).
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.utils.logging import get_logger

_logger = get_logger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/moderations"
_OPENAI_MODEL = "omni-moderation-latest"
_CLASSIFIER_TIMEOUT = 20.0

# Perspective's endpoint and the exact attribute set this pipeline requests.
# Public (not underscore-prefixed) so scripts/capture_stage0_baseline.py probes
# the same endpoint and the same attributes the live gate does: a baseline taken
# against a different attribute set would not be a baseline of this pipeline.
#
# #CRITICAL: security: the key goes in the x-goog-api-key header, never this URL's
# query string. See the note in _run_perspective.
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

# Graded scores below this floor are classifier noise, not signal: both APIs
# return a nonzero float for every category on every call (observed ceiling on
# clean children's prose ~6e-4), so without a floor every node emits every
# category as an advisory finding and the review surface reads as fully
# flagged. OpenAI's own boolean flag bypasses the floor (Perspective returns
# no such flag, so its only bypass is the score-based bright-line); advisories
# never gate (report.has_soft_flag counts FLAG only), so the floor is report
# hygiene, not a safety relaxation.
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
    perspective_key: str | None,
    client: httpx.AsyncClient,
) -> tuple[list[Finding], _CoverageState, _CoverageState]:
    """Run OpenAI and Perspective over every node, one call per classifier.

    Extracted from :func:`run_classifiers` (S3776): isolates the per-node
    double try/except loop, the function's single biggest nesting
    contributor, behind one call.

    A per-node failure no longer disables its classifier for the rest of the
    book: each call is retried with backoff, an unscreenable node is recorded in
    the returned coverage state, and only a run of consecutive failures opens the
    circuit. The caller turns any shortfall into a gating finding.

    Args:
        nodes: ``(node_id, prose)`` pairs to screen.
        openai_key: OpenAI Moderation key, or ``None`` to skip OpenAI.
        perspective_key: Perspective key, or ``None`` to skip Perspective.
        client: An httpx async client (injected for testability).

    Returns:
        tuple[list[Finding], _CoverageState, _CoverageState]: All findings
            produced, plus the OpenAI and Perspective coverage states (failure
            reason, if any, and the node ids each classifier never screened).
    """
    findings: list[Finding] = []
    openai = _CoverageState()
    perspective = _CoverageState()
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
        if perspective_key:
            findings.extend(
                await _screen_one(
                    perspective,
                    node_id,
                    lambda nid=node_id, text=prose: _run_perspective(
                        nid, text, perspective_key, client
                    ),
                )
            )
    return findings, openai, perspective


async def run_classifiers(  # noqa: PLR0913
    *,
    nodes: Sequence[tuple[str, str]],
    openai_key: str | None,
    perspective_key: str | None,
    client: httpx.AsyncClient,
    require_classifiers: bool = False,
    report_coverage: bool = True,
) -> list[Finding]:
    """Run available classifiers over each node's prose and collect findings.

    Args:
        nodes: ``(node_id, prose)`` pairs to screen.
        openai_key: OpenAI Moderation key, or ``None`` to skip OpenAI.
        perspective_key: Perspective key, or ``None`` to skip Perspective.
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
        A flat list of findings across all nodes and classifiers. A classifier
        that fails contributes exactly one ``classifier_degraded`` advisory
        (whole-story) instead of failing silently, and additionally a
        ``classifier_coverage_incomplete`` **FLAG** naming every node it never
        screened, so a partially-screened report cannot be mistaken for a clean
        one. Individual failures are retried with backoff, and only a run of
        consecutive failures stops the classifier for the remaining nodes.
    """
    # #CRITICAL: external-resource: classifier APIs are network calls; a failure
    # of one classifier must not crash the pipeline (the LLM stages still gate).
    # It must also not be invisible: a silent [] on a down provider looks
    # identical to a genuinely clean report on a kids'-content pipeline whose
    # reviewer calibration assumes the automated net ran. Each failure or unset
    # key now surfaces a non-gating ADVISORY so the review UI can show it.
    # #VERIFY: test_openai_http_error_yields_degraded_advisory,
    # test_perspective_http_error_yields_degraded_advisory,
    # test_require_classifiers_flags_unset_keys.
    # #CRITICAL: security: incomplete bright-line coverage must GATE, not merely
    # annotate. Before this, the first failure disabled a classifier for every
    # remaining node and the only trace was one ADVISORY, so a report with 93% of
    # a 746-node book unscreened was indistinguishable from a clean one and both
    # submit() and approve() passed it.
    # #VERIFY: test_partial_failure_flags_incomplete_coverage and
    # test_unscreened_nodes_are_named_in_the_coverage_finding.
    findings, openai, perspective = await _screen_all_nodes(
        nodes,
        openai_key=openai_key,
        perspective_key=perspective_key,
        client=client,
    )

    if openai.reason is None and require_classifiers and openai_key is None:
        openai.reason = "not configured"
    if perspective.reason is None and require_classifiers and perspective_key is None:
        perspective.reason = "not configured"

    total = len(nodes)
    for source, state in ((Source.OPENAI, openai), (Source.PERSPECTIVE, perspective)):
        if state.reason is not None:
            _logger.warning(
                "classifier_degraded", source=source.value, reason=state.reason
            )
            findings.append(_degraded_finding(source, state.reason))
        if state.unscreened and report_coverage:
            _logger.error(
                "classifier_coverage_incomplete",
                source=source.value,
                unscreened=len(state.unscreened),
                total=total,
            )
            findings.append(
                _incomplete_coverage_finding(source, state.unscreened, total)
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
    if flagged and category in _OPENAI_BRIGHTLINE:
        return Finding(
            stage=0,
            source=Source.OPENAI,
            category=category,
            node_id=node_id,
            verdict=Verdict.BLOCK,
            score=reportable_score,
            message=f"OpenAI bright-line category '{category}' flagged",
        )
    if flagged or over_floor:
        return Finding(
            stage=0,
            source=Source.OPENAI,
            category=category,
            node_id=node_id,
            verdict=Verdict.ADVISORY,
            score=reportable_score,
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

    top = _as_str_map(data)
    if top is None:
        _logger.warning(
            "openai_moderation_malformed", node_id=node_id, reason="top not a dict"
        )
        return []

    results = top.get("results")
    if not isinstance(results, list) or not results:
        _logger.warning(
            "openai_moderation_malformed",
            node_id=node_id,
            reason="results missing or empty",
        )
        return []

    result = _as_str_map(cast("object", results[0]))
    if result is None:
        _logger.warning(
            "openai_moderation_malformed",
            node_id=node_id,
            reason="result[0] not a dict",
        )
        return []

    categories = _narrow_bool_map(result.get("categories"))
    scores = _narrow_float_map(result.get("category_scores"))
    # #EDGE: external-resources: `_narrow_bool_map` degrades a missing or
    # non-dict `categories` field to `{}` rather than raising, so a shape
    # change on OpenAI's side would otherwise fail silently (empty findings,
    # no signal that the payload was malformed). Log it like the sibling
    # shape checks above so the degrade is observable.
    # #VERIFY: alerting on openai_moderation_malformed log volume.
    if not categories:
        _logger.warning(
            "openai_moderation_malformed",
            node_id=node_id,
            reason="categories missing or not a dict",
        )

    findings: list[Finding] = []
    for category, flagged in categories.items():
        finding = _openai_finding(node_id, category, flagged, scores.get(category, 0.0))
        if finding is not None:
            findings.append(finding)
    return findings


async def _run_perspective(
    node_id: str, prose: str, key: str, client: httpx.AsyncClient
) -> list[Finding]:
    """Call Google Perspective for one node; SEXUALLY_EXPLICIT -> BLOCK, else graded."""
    # #CRITICAL: security: the key goes in the x-goog-api-key header, never the URL
    # query string. httpx.HTTPStatusError.__str__ embeds the request URL, so a keyed
    # URL would leak the credential into the perspective_failed log line on any 4xx/5xx.
    # #VERIFY: error=str(exc) below cannot contain the key because the URL is key-free.
    attributes: dict[str, dict[str, str]] = {
        name: {} for name in PERSPECTIVE_ATTRIBUTES
    }
    try:
        response = await client.post(
            PERSPECTIVE_URL,
            headers={"x-goog-api-key": key},
            json={
                "comment": {"text": prose},
                "languages": ["en"],
                "requestedAttributes": attributes,
            },
            timeout=_CLASSIFIER_TIMEOUT,
        )
        response.raise_for_status()
        data: object = cast("object", response.json())
    except (httpx.HTTPError, ValueError) as exc:
        _logger.warning("perspective_failed", node_id=node_id, error=str(exc))
        raise ClassifierUnavailable(Source.PERSPECTIVE, str(exc)) from exc

    top = _as_str_map(data)
    if top is None:
        _logger.warning(
            "perspective_malformed", node_id=node_id, reason="top not a dict"
        )
        return []

    attribute_scores = _as_str_map(top.get("attributeScores"))
    if attribute_scores is None:
        _logger.warning(
            "perspective_malformed", node_id=node_id, reason="attributeScores missing"
        )
        return []

    findings: list[Finding] = []
    for attribute, payload in attribute_scores.items():
        finding = _perspective_attribute_finding(node_id, attribute, payload)
        if finding is not None:
            findings.append(finding)
    return findings


def _perspective_attribute_finding(
    node_id: str, attribute: str, payload: object
) -> Finding | None:
    """Build a Perspective Finding for one attribute.

    Returns None on malformed data, and for non-bright-line attributes whose
    score sits below the advisory noise floor.
    """
    payload_dict = _as_str_map(payload)
    if payload_dict is None:
        _logger.warning(
            "perspective_attribute_malformed",
            node_id=node_id,
            attribute=attribute,
            reason="payload not a dict",
        )
        return None

    summary = _as_str_map(payload_dict.get("summaryScore"))
    if summary is None:
        _logger.warning(
            "perspective_attribute_malformed",
            node_id=node_id,
            attribute=attribute,
            reason="summaryScore missing or not a dict",
        )
        return None

    raw_value = summary.get("value")
    if not isinstance(raw_value, (int, float)):
        _logger.warning(
            "perspective_attribute_malformed",
            node_id=node_id,
            attribute=attribute,
            reason="summaryScore.value not numeric",
        )
        return None

    score = float(raw_value)
    # #EDGE: data integrity: a non-finite score (NaN/Infinity) passes the
    # isinstance guard above (float("nan") is a float) but every comparison
    # against it is False, so without this guard the sub-floor early-return
    # would not fire and Finding.__post_init__ would raise ValueError,
    # aborting the entire Stage-0 batch (#144). Perspective's only signal is
    # the score, so a non-finite one is unusable: log and drop this single
    # attribute, matching the module's other malformed-payload handling.
    # #VERIFY: test_classifiers covers a non-finite Perspective summary score.
    if not math.isfinite(score):
        _logger.warning(
            "perspective_attribute_malformed",
            node_id=node_id,
            attribute=attribute,
            reason="summaryScore.value non-finite",
        )
        return None
    is_brightline = attribute == "SEXUALLY_EXPLICIT" and score >= 0.8
    if not is_brightline and score < _ADVISORY_SCORE_FLOOR:
        return None
    return Finding(
        stage=0,
        source=Source.PERSPECTIVE,
        category=attribute.lower(),
        node_id=node_id,
        verdict=Verdict.BLOCK if is_brightline else Verdict.ADVISORY,
        score=score,
        message=f"Perspective '{attribute}' score {score:.2f}",
    )
