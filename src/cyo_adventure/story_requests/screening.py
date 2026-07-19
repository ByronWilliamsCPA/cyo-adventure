"""Submission-time screening of a child's story-request text.

The public entrypoint (``screen_request_text``) is async: the deterministic PII
egress guard is synchronous, but the Stage-0 classifier pass makes async HTTP
calls.

Two guards run in order: the deterministic PII egress guard (local, always runs)
then the Stage-0 classifiers over the single request "node". A bright-line PII
match or a classifier BLOCK verdict marks the request blocked before any guardian
reads the raw text. Advisory findings are recorded (redacted) but do not block.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from cyo_adventure.api.schemas import StoryRequestFlag
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.pii import PiiContext, assert_prompt_pii_safe
from cyo_adventure.moderation.classifiers import run_classifiers
from cyo_adventure.moderation.report import Finding, Verdict
from cyo_adventure.utils.logging import get_logger

_logger = get_logger(__name__)

# Bounds the request-screening classifier client (connect + pool); the per-call
# timeout inside run_classifiers is the primary limit.
_CLIENT_TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class ScreeningResult:
    """The outcome of screening one request.

    Attributes:
        blocked: True when a PII match or a bright-line classifier BLOCK was hit.
        flags: Redacted flags (category/verdict/message) for the guardian.
    """

    blocked: bool
    flags: list[StoryRequestFlag]


def _redact(findings: list[Finding]) -> list[StoryRequestFlag]:
    """Project raw findings to guardian-safe flags (drop score and source)."""
    # #CRITICAL: security: never surface classifier score/source to a guardian;
    # only category/verdict/message cross this boundary (GuardianFinding rule).
    # #VERIFY: test_screen_blocks_on_bright_line_classifier asserts the shape.
    return [
        StoryRequestFlag(category=f.category, verdict=f.verdict, message=f.message)
        for f in findings
        if f.verdict is not Verdict.PASS
    ]


async def screen_request_text(
    request_text: str,
    *,
    child_names: frozenset[str],
    openai_key: str | None,
    perspective_key: str | None,
) -> ScreeningResult:
    """Screen a child's request text; return whether it is blocked plus flags.

    Args:
        request_text: The child's raw free-text request.
        child_names: The family's real child display names (PII guard input).
        openai_key: OpenAI Moderation key, or None to skip.
        perspective_key: Perspective key, or None to skip.

    Returns:
        ScreeningResult: blocked flag and redacted guardian flags.
    """
    # #CRITICAL: security: the PII guard is deterministic and local; it always
    # runs and a match hard-blocks so a real child name never reaches the
    # guardian queue or the generation prompt.
    # #VERIFY: test_screen_blocks_on_pii_match.
    try:
        assert_prompt_pii_safe(
            request_text,
            forbidden=PiiContext(child_names=child_names),
        )
    except ValidationError:
        return ScreeningResult(
            blocked=True,
            flags=[
                StoryRequestFlag(
                    category="personal_information",
                    verdict=Verdict.BLOCK,
                    message="request mentions personal information",
                )
            ],
        )

    # #CRITICAL: external-resource: classifier APIs are network calls; a failure
    # (or both keys unset) yields [] and the request proceeds to pending review
    # (the guardian is the human gate; the PII guard already ran). It never 5xxs.
    # #VERIFY: test_screen_clean_when_no_keys_and_no_pii and
    # test_screen_fails_open_on_classifier_network_error. Fail-open holds because
    # run_classifiers catches each classifier's failure internally and returns a
    # non-gating ``classifier_degraded`` advisory instead of raising; screening
    # never blocks on an advisory, so a classifier outage still proceeds to
    # pending review. require_classifiers is left False here (intake screen), so
    # an unset key stays a silent skip.
    async with httpx.AsyncClient(timeout=_CLIENT_TIMEOUT) as client:
        findings = await run_classifiers(
            nodes=[("request", request_text)],
            openai_key=openai_key,
            perspective_key=perspective_key,
            client=client,
        )
    blocked = any(f.verdict is Verdict.BLOCK for f in findings)
    if blocked:
        _logger.info("story_request.blocked_by_classifier")
    return ScreeningResult(blocked=blocked, flags=_redact(findings))
