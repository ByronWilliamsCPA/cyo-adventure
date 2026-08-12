"""Bounded soft-gate auto-repair: one re-prompt of the generator with findings.

When Stage 1 flags or Stages 2-3 raise a soft gate, the pipeline tries a single
repair: it asks the generation provider to revise the prose to address the soft
findings while preserving structure, then returns the revised blob (or None on
failure). This module only produces the candidate revision; it does not decide
whether to adopt it. The caller (``moderation/pipeline.py``) schema-validates
and re-moderates the revised result, then re-runs the deterministic structural/
policy gate (``validator.gate.run_gate``) on it before it is allowed to replace
the pre-repair blob: a repair that fails the gate is discarded exactly like a
schema-invalid one, so a repaired blob's structure is re-proven, not merely
trusted, before it ever reaches the human guardian who remains the final gate
per ADR-005.
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
    "Only revise prose. Some prose may contain verbatim tokens of the form "
    "{~NAME:Word~}: a family may later personalise these. Every such token must "
    "be preserved character for character, including the braces and tildes: do "
    "not reword it, re-space it, translate it, or drop it, and never move one "
    "into a choice label or the story title. Return ONLY the full revised story "
    "JSON, same schema." + _UNTRUSTED_SUFFIX
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
        report: The moderation report whose GENUINE (non-structural) soft
            findings drive the repair prompt; structural FLAGs are pipeline
            conditions, not prose defects, and are excluded.
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
    # #CRITICAL: external-resource: a STRUCTURAL FLAG describes a pipeline
    # condition (reviewer unavailable, classifier outage, mock reviewer), not
    # anything in the prose, and carries no node_id. Feeding one to the
    # generator produced a literal "- node None (pipeline): reviewer
    # unavailable or unparseable on N node(s)" instruction: a meaningless
    # _MAX_REPAIR_TOKENS call on every degraded-reviewer story, whose adopted
    # revision would then silently replace the persisted blob. Excluding them
    # here changes no routing (ModerationReport.has_soft_flag still sees the
    # structural FLAG, so the story still routes to submit for human review);
    # it only removes the pointless generation call and its blob-mutation risk.
    # #VERIFY: tests/unit/test_moderation_repair.py::
    # test_structural_only_report_makes_no_repair_call and
    # tests/unit/test_moderation_pipeline.py::
    # test_structural_only_soft_flag_skips_repair_and_submits.
    soft = [
        f for f in report.findings if f.verdict is Verdict.FLAG and not f.structural
    ]
    if not soft:
        # Nothing to repair: a caller with no genuine (non-structural) soft
        # flags gets no LLM call.
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
    completion = await guarded.complete(
        system=_REPAIR_SYSTEM, prompt=prompt, max_tokens=max_tokens
    )
    raw = completion.text
    try:
        parsed: object = cast("object", json.loads(raw))
    except json.JSONDecodeError:
        _logger.warning("repair_parse_failed", raw=raw[:200])
        return None
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, object]", parsed)
