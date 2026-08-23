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

from cyo_adventure.db.models import ProviderModelAllowlist

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

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


# #CRITICAL: security: an ENABLED row here is a pair the authoring-plan endpoint
# will accept. Every authoring plan is created against a family story request,
# so the worker builds every one of these on the "family" lane, where
# `provider.py::_FAMILY_LANE_PROVIDERS` permits only the routed legs. An enabled
# row naming a provider that lane forbids is a pair the admin dialog offers and
# the worker then refuses, turning a configuration error into a generation-time
# failure attributed to the job.
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
    session: AsyncSession, provider: str, model_id: str
) -> bool:
    """Return whether ``(provider, model_id)`` is an enabled allowlist row.

    Args:
        session: The request-scoped async session.
        provider: The provider name from untrusted admin input.
        model_id: The provider-native model id from untrusted admin input.

    Returns:
        bool: True only when a row exists for the exact pair AND enabled=True.
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
    return row is not None
