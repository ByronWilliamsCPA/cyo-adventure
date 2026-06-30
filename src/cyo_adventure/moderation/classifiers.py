"""Stage 0: deterministic classifier pre-filter (OpenAI Moderation + Perspective).

Each classifier is optional: a missing key skips it. Bright-line categories produce
a hard ``BLOCK`` finding (the pipeline routes straight to auto_reject, no LLM spend);
graded categories produce non-blocking findings whose scores feed Stage 1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import Sequence

from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.utils.logging import get_logger

_logger = get_logger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/moderations"
_OPENAI_MODEL = "omni-moderation-latest"
_OPENAI_TIMEOUT = 20.0

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


async def _run_openai(
    node_id: str, prose: str, key: str, client: httpx.AsyncClient
) -> list[Finding]:
    """Call OpenAI Moderation for one node; bright-line -> BLOCK, else graded."""
    try:
        response = await client.post(
            _OPENAI_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": _OPENAI_MODEL, "input": prose},
            timeout=_OPENAI_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()["results"][0]
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        _logger.warning("openai_moderation_failed", node_id=node_id, error=str(exc))
        return []

    categories: dict[str, bool] = result.get("categories", {})
    scores: dict[str, float] = result.get("category_scores", {})
    findings: list[Finding] = []
    for category, flagged in categories.items():
        score = float(scores.get(category, 0.0))
        if flagged and category in _OPENAI_BRIGHTLINE:
            findings.append(
                Finding(
                    stage=0,
                    source=Source.OPENAI,
                    category=category,
                    node_id=node_id,
                    verdict=Verdict.BLOCK,
                    score=score,
                    message=f"OpenAI bright-line category '{category}' flagged",
                )
            )
        elif score > 0.0:
            findings.append(
                Finding(
                    stage=0,
                    source=Source.OPENAI,
                    category=category,
                    node_id=node_id,
                    verdict=Verdict.ADVISORY,
                    score=score,
                    message=f"OpenAI graded signal for '{category}'",
                )
            )
    return findings


async def _run_perspective(
    node_id: str, prose: str, key: str, client: httpx.AsyncClient
) -> list[Finding]:
    """Call Google Perspective for one node; SEXUALLY_EXPLICIT -> BLOCK, else graded."""
    url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={key}"
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
            json={
                "comment": {"text": prose},
                "languages": ["en"],
                "requestedAttributes": attributes,
            },
            timeout=_OPENAI_TIMEOUT,
        )
        response.raise_for_status()
        scores = response.json()["attributeScores"]
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        _logger.warning("perspective_failed", node_id=node_id, error=str(exc))
        return []

    findings: list[Finding] = []
    for attribute, payload in scores.items():
        score = float(payload["summaryScore"]["value"])
        is_brightline = attribute == "SEXUALLY_EXPLICIT" and score >= 0.8
        findings.append(
            Finding(
                stage=0,
                source=Source.PERSPECTIVE,
                category=attribute.lower(),
                node_id=node_id,
                verdict=Verdict.BLOCK if is_brightline else Verdict.ADVISORY,
                score=score,
                message=f"Perspective '{attribute}' score {score:.2f}",
            )
        )
    return findings
