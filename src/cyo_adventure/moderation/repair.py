"""Bounded soft-gate auto-repair: one re-prompt of the generator with findings.

When Stage 1 flags or Stages 2-3 raise a soft gate, the pipeline tries a single
repair: it asks the generation provider to revise the prose to address the soft
findings while preserving structure, then returns the revised blob (or None on
failure). The pipeline schema-validates and re-moderates the revised result before
adopting it; it does NOT currently re-run the deterministic structural/policy gate
(``validator.gate.run_gate``) on the revision. Re-gating the repaired blob is a
documented follow-up (the human guardian remains the final gate per ADR-005).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.stages import (
    _UNTRUSTED_SUFFIX,  # pyright: ignore[reportPrivateUsage]
    _sanitize_delimited,  # pyright: ignore[reportPrivateUsage]
)
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from cyo_adventure.generation.pii import PiiContext
    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.moderation.report import ModerationReport

_logger = get_logger(__name__)

_REPAIR_SYSTEM = (
    "You revise a children's choose-your-own-adventure story to address review "
    "findings. Preserve the exact node ids, choices, and branching structure. "
    "Only revise prose. Return ONLY the full revised story JSON, same schema."
    + _UNTRUSTED_SUFFIX
)


async def attempt_repair(
    *,
    blob: dict[str, object],
    report: ModerationReport,
    generation_provider: GenerationProvider,
    pii: PiiContext,
    max_tokens: int,
) -> dict[str, object] | None:
    """Run one bounded repair pass; return the revised blob or None on failure.

    Args:
        blob: The current story JSON.
        report: The moderation report whose soft findings drive the repair prompt.
        generation_provider: The generation provider (re-prompted to revise prose).
        pii: The PII context; the provider is PII-guarded before any call.
        max_tokens: Token budget for the repair completion.

    Returns:
        The revised story blob, or ``None`` if the model output did not parse.

    Raises:
        ProviderError: a backend outage (timeout/5xx/auth) propagates by design;
            the worker rolls back the unreviewed persist and records the job failed
            so RQ can retry, rather than submitting a partially-reviewed story.
    """
    soft = [f for f in report.findings if f.verdict is Verdict.FLAG]
    if not soft:
        # Nothing to repair: a caller with no soft flags gets no LLM call.
        return None
    # #CRITICAL: security: the repair prompt egresses story prose; it MUST run
    # through the PII guard exactly like generation.
    # #VERIFY: provider wrapped in PiiGuardedProvider before complete().
    # #CRITICAL: external-resource: guarded.complete() is a network LLM call; a
    # provider outage propagates to the worker for rollback + RQ retry (intentional
    # non-catch). Only a parse failure of a returned body degrades to None here.
    # #VERIFY: only json.JSONDecodeError is caught below; provider errors propagate.
    # #CRITICAL: security: the story JSON below contains untrusted node prose
    # (the same fifth-concat-site risk as the stages.py prompts): it MUST be
    # delimited and sanitized exactly like the stage prompts, or a hostile
    # generation could break out of the delimited zone and steer the repair
    # model directly.
    # #VERIFY: the blob is sanitized via _sanitize_delimited and wrapped in
    # <untrusted_passage> below (test_repair_prompt_wraps_story_json_in_untrusted_delimiter
    # and test_repair_prompt_neutralizes_literal_closing_tag_in_story_json in
    # tests/unit/test_moderation_repair.py).
    guarded = PiiGuardedProvider(generation_provider, forbidden=pii)
    findings_text = "\n".join(
        f"- node {f.node_id} ({f.category}): {f.message}" for f in soft
    )
    sanitized_blob = _sanitize_delimited(json.dumps(blob))
    prompt = (
        f"Revise this story to address these findings:\n{findings_text}\n\n"
        f"Story JSON:\n<untrusted_passage>\n{sanitized_blob}\n</untrusted_passage>"
    )
    raw = await guarded.complete(
        system=_REPAIR_SYSTEM, prompt=prompt, max_tokens=max_tokens
    )
    try:
        parsed: object = cast("object", json.loads(raw))
    except json.JSONDecodeError:
        _logger.warning("repair_parse_failed", raw=raw[:200])
        return None
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, object]", parsed)
