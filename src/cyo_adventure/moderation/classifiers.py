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


async def run_classifiers(
    *,
    nodes: Sequence[tuple[str, str]],
    openai_key: str | None,
    perspective_key: str | None,
    client: httpx.AsyncClient,
) -> list[Finding]:
    """Run available classifiers over each node's prose and collect findings.

    Args:
        nodes: ``(node_id, prose)`` pairs to screen.
        openai_key: OpenAI Moderation key, or ``None`` to skip OpenAI.
        perspective_key: Perspective key, or ``None`` to skip Perspective.
        client: An httpx async client (injected for testability).

    Returns:
        A flat list of findings across all nodes and classifiers.
    """
    # #CRITICAL: external-resource: classifier APIs are network calls; a failure of
    # one classifier must not crash the pipeline (the LLM stages still gate).
    # #VERIFY: per-call try/except logs and continues; both keys unset returns [].
    findings: list[Finding] = []
    for node_id, prose in nodes:
        if openai_key:
            findings.extend(await _run_openai(node_id, prose, openai_key, client))
        if perspective_key:
            findings.extend(
                await _run_perspective(node_id, prose, perspective_key, client)
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
    if flagged and category in _OPENAI_BRIGHTLINE:
        return Finding(
            stage=0,
            source=Source.OPENAI,
            category=category,
            node_id=node_id,
            verdict=Verdict.BLOCK,
            score=score,
            message=f"OpenAI bright-line category '{category}' flagged",
        )
    if flagged or score >= _ADVISORY_SCORE_FLOOR:
        return Finding(
            stage=0,
            source=Source.OPENAI,
            category=category,
            node_id=node_id,
            verdict=Verdict.ADVISORY,
            score=score,
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
        return []

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
        return []

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
