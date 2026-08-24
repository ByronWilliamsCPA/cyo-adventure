"""Admin-editable provider/model allowlist (WS-C PR1).

Providers are a code-fixed enum; only the model id within a provider is
admin-managed via ``api/provider_allowlist.py``. ``DEFAULT_ALLOWLIST`` is the
code-side mirror of the CUMULATIVE state the Supabase migrations leave the
table in, and the two are hand-synced. Three migrations contribute:

* ``20260721230000_seed_provider_model_allowlist.sql`` inserts the original set.
* ``20260818120000_retire_ollama_provider.sql`` deletes the ollama row and
  narrows the provider CHECK to the three that remain.
* ``20260823140000_align_allowlist_with_d1_lane_ruling.sql`` adds the two
  DeepSeek rows and disables the two direct-anthropic rows (D1, ``UW-C346``).

The docstring previously named an Alembic path
(``migrations/versions/20260709_1000_add_provider_model_allowlist.py``) that
was never ported to Supabase CLI migrations (ADR-012) and no longer exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.db.models import ProviderModelAllowlist
from cyo_adventure.generation.provider import FAMILY_LANE_PROVIDERS
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.generation.provider import GenerationLane

logger = get_logger(__name__)

# Mirrors the ck_provider_model_allowlist_provider CHECK constraint. mock is
# deliberately absent: it is a CI-only test double, never a real generation
# backend, so it can never be allowlisted.
ALLOWLIST_PROVIDERS: tuple[str, ...] = ("anthropic", "openrouter", "modal")


@dataclass(frozen=True, slots=True)
class AllowlistSeed:
    """One hand-synced seed row mirrored from the PR1 migration.

    Attributes:
        provider: One of ``ALLOWLIST_PROVIDERS``.
        model_id: The provider-native model id.
        display_name: The human label the migration seeds alongside it.
        enabled: Whether an admin may currently select this pair. Defaults to
            ``True``; a ``False`` row is one the migrations deliberately leave
            present and unselectable rather than delete.
    """

    provider: str
    model_id: str
    display_name: str
    enabled: bool = True

    def __post_init__(self) -> None:
        """Reject a seed that states the exact configuration D1 forbids.

        Raises:
            ConfigurationError: If ``provider`` is not one of
                ``ALLOWLIST_PROVIDERS``, or if an ``enabled`` seed names a
                provider the family generation lane forbids.
        """
        # #CRITICAL: security: DEFAULT_ALLOWLIST is a module-level literal, so
        # this runs at import and an offending edit cannot reach a running
        # process at all. The unit test that asserts the same invariant is a
        # weaker control on its own: it fails only where the suite runs, while
        # this fails everywhere the package is imported. Both are kept because
        # the test names the invariant in a place a reader looks for it.
        # #VERIFY: tests/unit/test_allowlist.py::
        # test_no_enabled_seed_row_names_a_provider_the_family_lane_forbids.
        if self.provider not in ALLOWLIST_PROVIDERS:
            msg = (
                f"allowlist seed provider '{self.provider}' is not one of "
                f"{list(ALLOWLIST_PROVIDERS)}; the seed mirrors the "
                "ck_provider_model_allowlist_provider CHECK constraint and "
                "cannot name a provider that constraint rejects"
            )
            raise ConfigurationError(msg)
        if self.enabled and self.provider not in FAMILY_LANE_PROVIDERS:
            msg = (
                f"allowlist seed '{self.provider}/{self.model_id}' is enabled "
                "but names a provider the family generation lane forbids; a "
                "kid- or guardian-triggered job may use only "
                f"{sorted(FAMILY_LANE_PROVIDERS)}. Seed it with enabled=False "
                "instead of deleting it (D1, `UW-C346`)."
            )
            raise ConfigurationError(msg)


# #CRITICAL: security: an ENABLED row here is a pair the authoring-plan endpoint
# will accept. Every authoring plan is created by a guardian for a family
# against a story request, so a job built from one runs on the "family" lane,
# where `provider.py::FAMILY_LANE_PROVIDERS` permits only the routed legs. The
# legacy concept-intake path (api/generation.py's
# POST /concepts/{id}/generate) creates a job without going through this
# endpoint, and without a story request or authoring metadata at all, but the
# worker still forces lane="family" for it (generation/worker.py), so the same
# restriction reaches that path too. An enabled row naming a provider either
# path's family lane forbids is a pair the admin dialog offers and the worker
# then refuses, turning a configuration error into a generation-time failure
# attributed to the job.
# #VERIFY: tests/unit/test_allowlist.py::
# test_no_enabled_seed_row_names_a_provider_the_family_lane_forbids.
DEFAULT_ALLOWLIST: tuple[AllowlistSeed, ...] = (
    # Retained but DISABLED by D1 (ruled 2026-08-23, `UW-C346`): routing
    # family-triggered work through the operator's own Anthropic account is
    # outside that account's terms. Kept as rows rather than deleted because
    # the original seed migration's ``ON CONFLICT DO NOTHING`` suppresses a
    # re-insert only while the row exists, so a deleted row comes back ENABLED
    # on any replay of that seed.
    AllowlistSeed(
        "anthropic",
        "claude-sonnet-4-6",
        "Claude Sonnet 4.6 (direct, withdrawn)",
        enabled=False,
    ),
    AllowlistSeed(
        "anthropic",
        "claude-haiku-4-5",
        "Claude Haiku 4.5 (direct, withdrawn)",
        enabled=False,
    ),
    AllowlistSeed(
        "openrouter", "deepseek/deepseek-v4-pro", "OpenRouter fill (DeepSeek V4 Pro)"
    ),
    AllowlistSeed(
        "openrouter",
        "deepseek/deepseek-v4-flash",
        "OpenRouter review (DeepSeek V4 Flash)",
    ),
    AllowlistSeed(
        "openrouter", "anthropic/claude-haiku-4.5", "OpenRouter primary (Haiku 4.5)"
    ),
    AllowlistSeed(
        "openrouter",
        "anthropic/claude-sonnet-4.6",
        "OpenRouter fallback (Sonnet 4.6)",
    ),
)


async def is_enabled_allowlist_pair(
    session: AsyncSession,
    provider: str,
    model_id: str,
    *,
    lane: GenerationLane = "family",
) -> bool:
    """Return whether ``(provider, model_id)`` is selectable on ``lane``.

    Two independent conditions, both required: the row must exist and be
    enabled, and the provider must be one ``lane`` permits. The lane rule is a
    parameter rather than a hardcoded family check because D1 withdrew the
    direct Anthropic leg from family-triggered work only; out-of-band admin
    generation may still use it, and hardcoding would make that legitimate
    answer unreachable.

    Args:
        session: The request-scoped async session.
        provider: The provider name from untrusted admin input.
        model_id: The provider-native model id from untrusted admin input.
        lane: Which actor's request the pair would serve. Keyword-only, and
            defaults to the restrictive ``"family"`` lane, mirroring
            ``generation/provider.py::build_provider``: a call site that says
            nothing is restricted rather than exempt.

    Returns:
        bool: True only when a row exists for the exact pair, is enabled, and
        names a provider ``lane`` permits.
    """
    # #CRITICAL: security: this is the control that keeps free-string model
    # ids out of billing. enabled=True is checked in the SAME query as the
    # natural-key match, not as a separate filter a caller could forget or
    # apply after the fact.
    # #VERIFY: tests/integration/test_allowlist.py::
    # test_disabled_pair_is_not_enabled and test_unknown_pair_is_not_enabled.
    row = await session.scalar(
        select(ProviderModelAllowlist).where(
            ProviderModelAllowlist.provider == provider,
            ProviderModelAllowlist.model_id == model_id,
            ProviderModelAllowlist.enabled.is_(True),
        )
    )
    if row is None:
        return False

    # #CRITICAL: security: the D1 lane rule (`UW-C346`) applied to the READ
    # path, so a forbidden pair is refused whatever the table says. The API
    # write path already refuses to create or enable such a row, but a
    # migration, scripts/seed_dev_data.py, or raw SQL reaches the table
    # without passing it, and this helper is the single answer the
    # authoring-plan endpoint trusts. Imported from provider.py rather than
    # restated here: one copy of the rule is what keeps the write-time, read-
    # time, and job-time answers from drifting apart.
    # #VERIFY: tests/integration/test_allowlist.py::
    # test_family_lane_refuses_an_enabled_row_it_forbids and
    # test_the_default_lane_is_the_restrictive_one and
    # test_admin_lane_accepts_an_enabled_row_the_family_lane_forbids.
    if lane == "family" and provider not in FAMILY_LANE_PROVIDERS:
        # Logged rather than silently dropped: reaching this line means an
        # enabled row the family lane forbids is sitting in the table, which
        # no API caller can produce and which the at-rest CHECK constraint
        # `ck_provider_model_allowlist_enabled_family_lane` (migration
        # 20260823160000, `UW-C350` part (b)) now rejects at write time too.
        # With all three layers in place this branch should be unreachable,
        # so the log line is not a routine refusal notice: it means the
        # constraint was dropped, or the row predates it, or a reader is
        # asking about a table this process is not the only writer of. Treat
        # a hit as a configuration defect to investigate, not as noise.
        logger.error(
            "allowlist_pair_refused_by_lane",
            provider=provider,
            model_id=model_id,
            lane=lane,
            permitted_providers=sorted(FAMILY_LANE_PROVIDERS),
        )
        return False

    return True
