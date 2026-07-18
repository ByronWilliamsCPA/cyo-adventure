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

import math
from typing import TYPE_CHECKING, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import Sequence

from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.utils.logging import get_logger

_logger = get_logger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/moderations"
_OPENAI_MODEL = "omni-moderation-latest"
_CLASSIFIER_TIMEOUT = 20.0

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


class ClassifierUnavailable(Exception):  # noqa: N818 -- not an error state, a signal
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


async def run_classifiers(  # noqa: PLR0913 -- all keyword-only, one cohesive call
    *,
    nodes: Sequence[tuple[str, str]],
    openai_key: str | None,
    perspective_key: str | None,
    client: httpx.AsyncClient,
    require_classifiers: bool = False,
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

    Returns:
        A flat list of findings across all nodes and classifiers. A classifier
        that fails on any node (HTTP/parse error) contributes exactly one
        ``classifier_degraded`` advisory (whole-story) instead of failing
        silently, and is not retried for the remaining nodes.
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
    findings: list[Finding] = []
    openai_reason: str | None = None
    perspective_reason: str | None = None
    for node_id, prose in nodes:
        if openai_key and openai_reason is None:
            try:
                findings.extend(await _run_openai(node_id, prose, openai_key, client))
            except ClassifierUnavailable as exc:
                openai_reason = exc.reason
        if perspective_key and perspective_reason is None:
            try:
                findings.extend(
                    await _run_perspective(node_id, prose, perspective_key, client)
                )
            except ClassifierUnavailable as exc:
                perspective_reason = exc.reason

    if openai_reason is None and require_classifiers and openai_key is None:
        openai_reason = "not configured"
    if perspective_reason is None and require_classifiers and perspective_key is None:
        perspective_reason = "not configured"

    if openai_reason is not None:
        _logger.warning("classifier_degraded", source="openai", reason=openai_reason)
        findings.append(_degraded_finding(Source.OPENAI, openai_reason))
    if perspective_reason is not None:
        _logger.warning(
            "classifier_degraded", source="perspective", reason=perspective_reason
        )
        findings.append(_degraded_finding(Source.PERSPECTIVE, perspective_reason))
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
    """Build a single OpenAI Finding, or return None when there is nothing to report.

    #EDGE: data integrity: httpx's ``.json()`` uses ``json.loads`` with
    ``allow_nan=True``, so a non-finite score (``NaN``/``Infinity``) survives the
    ``isinstance(_, (int, float))`` guard upstream. Passed straight through it
    would make ``Finding.__post_init__`` raise ``ValueError`` (its range check
    is false for ``NaN``), matching the Perspective crash tracked in #144. Treat
    a non-finite score as an absent score: drop it from the graded-floor
    comparison and report ``score=None`` rather than crashing, while still
    honoring OpenAI's independent boolean ``flagged`` signal so a flagged
    bright-line category is never lost to a garbage score.
    #VERIFY: test_classifiers covers flagged and unflagged non-finite scores.
    """
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
    url = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
    attributes: dict[str, dict[str, str]] = {
        "SEXUALLY_EXPLICIT": {},
        "SEVERE_TOXICITY": {},
        "THREAT": {},
        "TOXICITY": {},
        "PROFANITY": {},
        "IDENTITY_ATTACK": {},
        "INSULT": {},
    }
    try:
        response = await client.post(
            url,
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
