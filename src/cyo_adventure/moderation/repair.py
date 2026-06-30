"""Bounded soft-gate auto-repair: one re-prompt of the generator with findings.

When Stage 1 flags or Stages 2-3 raise a soft gate, the pipeline tries a single
repair: it asks the generation provider to revise the prose to address the soft
findings while preserving structure, then returns the revised blob (or None on
failure). The pipeline re-runs the deterministic gate and re-moderates the result.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.moderation.report import Verdict
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
    """
    # #CRITICAL: security: the repair prompt egresses story prose; it MUST run
    # through the PII guard exactly like generation.
    # #VERIFY: provider wrapped in PiiGuardedProvider before complete().
    guarded = PiiGuardedProvider(generation_provider, forbidden=pii)
    soft = [f for f in report.findings if f.verdict is Verdict.FLAG]
    findings_text = "\n".join(
        f"- node {f.node_id} ({f.category}): {f.message}" for f in soft
    )
    prompt = (
        f"Revise this story to address these findings:\n{findings_text}\n\n"
        f"Story JSON:\n{json.dumps(blob)}"
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
