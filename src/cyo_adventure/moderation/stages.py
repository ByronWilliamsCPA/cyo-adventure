"""Stages 1-4: the LLM moderation passes.

Each stage prompts an independent review model and parses one JSON verdict.
Stage 1 (safety) is the only hard gate. Stages 2-3 are soft. Stage 4 is
advisory. All prompts run through the PII-guarded review provider supplied by
the caller.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.moderation.review_provider import ReviewProvider

_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_SAFETY_SYSTEM = (
    "You are a child-safety reviewer for a children's choose-your-own-adventure "
    "app. Judge one passage against the target age band. Return ONLY JSON: "
    '{"verdict": "safe"|"flag"|"block", "reason": "<short>"}. '
    '"block" for content unsafe at any age (sexual content, self-harm instructions, '
    "real-world danger modeled as achievable, cruelty rewarded as the good outcome); "
    '"flag" for content too mature for the band that a human should weigh; '
    '"safe" otherwise.'
)

_READABILITY_SYSTEM = (
    "You are a reading-level reviewer for a children's choose-your-own-adventure "
    "app. Judge one passage's vocabulary and sentence complexity against the "
    "Flesch-Kincaid grade target and tolerance provided in the user message. "
    "Return ONLY JSON: "
    '{"verdict": "flag"|"pass", "reason": "<short>"}. '
    '"flag" when the passage is significantly too hard or too easy relative to '
    "the target (outside the tolerance band); "
    '"pass" when it is within the acceptable range.'
)

_COHERENCE_SYSTEM = (
    "You are a story-consistency reviewer for a children's choose-your-own-adventure "
    "app. You will receive all story nodes. Judge whether there are severe "
    "cross-branch inconsistencies in plot, character identity, or world-state "
    "(for example, a character alive in one branch is dead in another without "
    "explanation, or a key object disappears between connected nodes). "
    "Return ONLY JSON: "
    '{"verdict": "flag"|"pass", "reason": "<short>"}. '
    '"flag" for severe incoherence a reader would notice; "pass" otherwise.'
)

_ENGAGEMENT_SYSTEM = (
    "You are an engagement reviewer for a children's choose-your-own-adventure "
    "app. You will receive all story nodes. Judge whether the choices are "
    "meaningfully distinct (not just paraphrases of each other), whether the "
    "pacing keeps a young reader interested, and whether the prose uses an "
    "authentic child-friendly voice. This is an advisory review only, not a "
    "gate. Return ONLY JSON: "
    '{"verdict": "advisory"|"pass", "reason": "<short>"}. '
    '"advisory" when there is a concern worth flagging to the author; '
    '"pass" when the story reads well for its audience.'
)


# ---------------------------------------------------------------------------
# Shared verdict parser
# ---------------------------------------------------------------------------


def _parse_verdict(raw: str, *, fail_safe: Verdict) -> tuple[Verdict, str]:
    """Parse a model verdict JSON; map unknown or unparseable output to fail_safe.

    Args:
        raw: The raw model output.
        fail_safe: The verdict to return when parsing fails (``FLAG`` for hard
            gates, ``PASS`` for soft/advisory stages).

    Returns:
        ``(verdict, reason)``.
    """
    mapping: dict[str, Verdict] = {
        "safe": Verdict.PASS,
        "pass": Verdict.PASS,
        "flag": Verdict.FLAG,
        "block": Verdict.BLOCK,
        "advisory": Verdict.ADVISORY,
    }
    try:
        # json.loads is typed -> Any; we deliberately re-bind to object and narrow
        # via isinstance below, so the reportAny here is an intentional boundary.
        parsed: object = json.loads(raw)  # pyright: ignore[reportAny]
        if not isinstance(parsed, dict):
            msg = "expected a JSON object"
            raise TypeError(msg)  # noqa: TRY301
        payload = cast("dict[str, object]", parsed)
        verdict = mapping.get(str(payload.get("verdict", "")).lower())
        reason = str(payload.get("reason", ""))
    except (json.JSONDecodeError, AttributeError, TypeError):
        _logger.warning("verdict_parse_failed", raw=raw[:200])
        return fail_safe, "verdict parse failed; defaulted to fail-safe"
    if verdict is None:
        _logger.warning("verdict_unknown", raw=raw[:200])
        return fail_safe, "unknown verdict; defaulted to fail-safe"
    return verdict, reason


# ---------------------------------------------------------------------------
# Stage 1: safety (per-node, hard gate)
# ---------------------------------------------------------------------------


async def run_safety_stage(
    *,
    provider: ReviewProvider,
    nodes: Sequence[tuple[str, str]],
    age_band: str,
    max_tokens: int,
) -> list[Finding]:
    """Stage 1: per-node safety/age-policy hard gate.

    Args:
        provider: The PII-guarded review provider.
        nodes: ``(node_id, prose)`` pairs to review.
        age_band: The story's target band, for example ``"6-9"``.
        max_tokens: Token budget per review call.

    Returns:
        One finding per node (``BLOCK``/``FLAG``/``PASS``).
    """
    # #CRITICAL: security: this is the only hard safety gate; a parse failure
    # must fail safe (FLAG for human review), never silently PASS.
    # #VERIFY: _parse_verdict maps unknown/garbled output to FLAG, not PASS.
    findings: list[Finding] = []
    for node_id, prose in nodes:
        prompt = f"Age band: {age_band}\nPassage:\n{prose}"
        raw = await provider.complete(
            system=_SAFETY_SYSTEM, prompt=prompt, max_tokens=max_tokens
        )
        verdict, reason = _parse_verdict(raw, fail_safe=Verdict.FLAG)
        findings.append(
            Finding(
                stage=1,
                source=Source.LLM_SAFETY,
                category="safety",
                node_id=node_id,
                verdict=verdict,
                message=reason,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Stage 2: readability (per-node, soft gate)
# ---------------------------------------------------------------------------


async def run_readability_stage(
    *,
    provider: ReviewProvider,
    nodes: Sequence[tuple[str, str]],
    reading_target: float,
    tolerance: float,
    max_tokens: int,
) -> list[Finding]:
    """Stage 2: per-node Flesch-Kincaid reading-level soft gate.

    Args:
        provider: The PII-guarded review provider.
        nodes: ``(node_id, prose)`` pairs to review.
        reading_target: The band's Flesch-Kincaid grade target.
        tolerance: Acceptable deviation from the target (half-width).
        max_tokens: Token budget per review call.

    Returns:
        One finding per node (``FLAG``/``PASS``).
    """
    # #ASSUME: external-resources: LLM judgment of reading level is approximate;
    # fail_safe=PASS avoids blocking on ambiguous passages.
    # #VERIFY: FLAG findings are surfaced for human review, never auto-blocked.
    findings: list[Finding] = []
    for node_id, prose in nodes:
        prompt = (
            f"Flesch-Kincaid grade target: {reading_target} "
            f"(tolerance: +/-{tolerance})\n"
            f"Passage:\n{prose}"
        )
        raw = await provider.complete(
            system=_READABILITY_SYSTEM, prompt=prompt, max_tokens=max_tokens
        )
        verdict, reason = _parse_verdict(raw, fail_safe=Verdict.PASS)
        findings.append(
            Finding(
                stage=2,
                source=Source.LLM_READABILITY,
                category="reading_level",
                node_id=node_id,
                verdict=verdict,
                message=reason,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Stage 3: coherence (whole-story, one call, soft gate)
# ---------------------------------------------------------------------------


async def run_coherence_stage(
    *,
    provider: ReviewProvider,
    nodes: Sequence[tuple[str, str]],
    max_tokens: int,
) -> list[Finding]:
    """Stage 3: whole-story cross-branch coherence soft gate.

    Makes a single provider call for the entire story rather than per-node, so
    the model can reason about cross-branch consistency.

    Args:
        provider: The PII-guarded review provider.
        nodes: ``(node_id, prose)`` pairs for all story nodes.
        max_tokens: Token budget for the single review call.

    Returns:
        At most one finding (``node_id=None``, ``FLAG``/``PASS``).
    """
    # #ASSUME: external-resources: LLM coherence judgment is holistic and
    # approximate; fail_safe=PASS avoids blocking on model uncertainty.
    # #VERIFY: FLAG findings are surfaced for human review, never auto-blocked.
    node_lines = "\n".join(f"[{nid}] {prose}" for nid, prose in nodes)
    prompt = f"Story nodes:\n{node_lines}"
    raw = await provider.complete(
        system=_COHERENCE_SYSTEM, prompt=prompt, max_tokens=max_tokens
    )
    verdict, reason = _parse_verdict(raw, fail_safe=Verdict.PASS)
    return [
        Finding(
            stage=3,
            source=Source.LLM_COHERENCE,
            category="coherence",
            node_id=None,
            verdict=verdict,
            message=reason,
        )
    ]


# ---------------------------------------------------------------------------
# Stage 4: engagement (whole-story, one call, advisory only)
# ---------------------------------------------------------------------------


async def run_engagement_stage(
    *,
    provider: ReviewProvider,
    nodes: Sequence[tuple[str, str]],
    max_tokens: int,
) -> list[Finding]:
    """Stage 4: whole-story engagement advisory pass.

    Makes a single provider call for the entire story. This stage never gates;
    all findings are advisory.

    Args:
        provider: The PII-guarded review provider.
        nodes: ``(node_id, prose)`` pairs for all story nodes.
        max_tokens: Token budget for the single review call.

    Returns:
        At most one finding (``node_id=None``, ``ADVISORY``/``PASS``).
    """
    # #ASSUME: external-resources: LLM engagement judgment is subjective;
    # fail_safe=PASS ensures a parse failure never advisory-flags clean content.
    # #VERIFY: ADVISORY findings surface to the author but do not gate the pipeline.
    node_lines = "\n".join(f"[{nid}] {prose}" for nid, prose in nodes)
    prompt = f"Story nodes:\n{node_lines}"
    raw = await provider.complete(
        system=_ENGAGEMENT_SYSTEM, prompt=prompt, max_tokens=max_tokens
    )
    verdict, reason = _parse_verdict(raw, fail_safe=Verdict.PASS)
    return [
        Finding(
            stage=4,
            source=Source.LLM_ENGAGEMENT,
            category="engagement",
            node_id=None,
            verdict=verdict,
            message=reason,
        )
    ]
