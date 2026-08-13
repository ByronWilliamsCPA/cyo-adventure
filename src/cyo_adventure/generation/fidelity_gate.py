"""The combined Stage 1 fidelity gate: pure-code checks, then one semantic check.

Shared by both prep mechanisms: generation/worker.py (automated_provider) and
generation/import_story.py::resume_manual_fill (skill), so a fill's fidelity
is checked identically regardless of who (or what) produced it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.generation.fidelity import run_fidelity_checks
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.metered import MeteredProvider
from cyo_adventure.moderation.fidelity_review import run_semantic_fidelity_check
from cyo_adventure.moderation.review_provider import (
    build_review_provider,
    resolve_review_settings,
)

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings
    from cyo_adventure.generation.pii import PiiContext
    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.generation.usage import UsageLedger


async def run_stage1_gate(
    original: dict[str, object],
    filled: dict[str, object],
    *,
    review_stage1_model: str | None,
    prep_model: str | None = None,
    settings: Settings,
    pii: PiiContext,
    ledger: UsageLedger | None = None,
) -> list[str]:
    """Run pure-code checks, then (only if clean) one semantic beats-check.

    Skips the semantic call entirely when a pure-code check already fails --
    the fill needs a redo regardless of semantic fidelity, so there is no
    reason to spend a paid review-model call on it.

    Args:
        original: The skeleton before filling (FILL-directive bodies).
        filled: The candidate filled document.
        review_stage1_model: Optional admin-chosen model override for the
            semantic check's review provider (see
            story_requests/authoring_plan.py::AuthoringPlanRequest).
        prep_model: The model that wrote the fill (the job's prep_model).
            Used as the semantic check's review-model default whenever
            ``review_stage1_model`` is omitted, per the design spec (closes
            #134): the same model that wrote the prose judges its own
            fidelity to the directive, rather than falling through to
            ``build_review_provider``'s unrelated generic default.
        settings: Application settings (review backend selection).
        pii: PII context for the egress guard on the semantic-check prompt.
        ledger: The run's usage ledger, when the caller is metering. The
            semantic check builds its own review provider, so without this the
            call it makes would be spent but never counted. ``None`` (the
            default) means the caller is not metering and preserves every
            pre-existing call site exactly.

    Returns:
        Combined violation messages; empty when the fill passes every check.
    """
    violations = run_fidelity_checks(original, filled)
    if violations:
        return violations

    review_settings = resolve_review_settings(
        settings, review_stage1_model or prep_model
    )
    provider, _independent = build_review_provider(
        review_settings, generator_provider=None, generator_model=None
    )
    # #CRITICAL: payment/financial: this review provider is built here rather
    # than passed in, so its call escapes the job's accounting unless the
    # caller's ledger reaches it. The gate runs once per fill AND once per
    # repair attempt, so the undercount would scale with exactly the jobs that
    # cost the most: the ones that needed repairing.
    # #VERIFY: tests/unit/test_review_metering.py::
    # test_the_stage1_gates_semantic_check_is_billed_to_the_ledger.
    metered: GenerationProvider = (
        provider if ledger is None else MeteredProvider(provider, ledger=ledger)
    )
    # The guard stays outermost: a prompt it rejects reaches neither the meter
    # nor the backend, so a blocked call is correctly never billed.
    guarded = PiiGuardedProvider(metered, forbidden=pii)
    note = await run_semantic_fidelity_check(original, filled, guarded)
    if note is not None:
        violations.append(f"semantic fidelity check: {note}")
    return violations
