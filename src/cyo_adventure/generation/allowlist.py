"""Admin-editable provider/model allowlist (WS-C PR1).

Providers are a code-fixed enum; only the model id within a provider is
admin-managed via ``api/provider_allowlist.py``. ``DEFAULT_ALLOWLIST`` is the
code-side mirror of the seed rows
``migrations/versions/20260709_1000_add_provider_model_allowlist.py`` inserts;
the two are hand-synced (see the RAD note on that migration).
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
ALLOWLIST_PROVIDERS: tuple[str, ...] = ("anthropic", "openrouter", "modal", "ollama")


@dataclass(frozen=True, slots=True)
class AllowlistSeed:
    """One hand-synced seed row mirrored from the PR1 migration.

    Attributes:
        provider: One of ``ALLOWLIST_PROVIDERS``.
        model_id: The provider-native model id.
        display_name: The human label the migration seeds alongside it.
    """

    provider: str
    model_id: str
    display_name: str


DEFAULT_ALLOWLIST: tuple[AllowlistSeed, ...] = (
    AllowlistSeed("anthropic", "claude-sonnet-4-6", "Claude Sonnet 4.6 (direct)"),
    AllowlistSeed("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5 (direct)"),
    AllowlistSeed(
        "openrouter", "anthropic/claude-haiku-4.5", "OpenRouter primary (Haiku 4.5)"
    ),
    AllowlistSeed(
        "openrouter",
        "anthropic/claude-sonnet-4.6",
        "OpenRouter fallback (Sonnet 4.6)",
    ),
    AllowlistSeed("ollama", "qwen2.5:14b", "Ollama local default"),
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
