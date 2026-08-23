# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""The provider lane rule: who triggered a job constrains which leg it may use.

Ruled 2026-08-23 (D1 in ``generation-review-workstream-plan-2026-08-22.md``,
tracked at ``UW-C346``). A generation a kid or a guardian triggered may route
through OpenRouter or Modal; it may never route through the operator's direct
Anthropic account. Admin, out-of-band content generation is not so constrained.

The control is a parameter on :func:`build_provider` rather than a check at its
call sites, and it defaults to the RESTRICTIVE lane, so a future call site that
forgets to state a lane is restricted rather than permitted.
"""

from __future__ import annotations

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.generation.providers import (
    AnthropicProvider,
    FallbackProvider,
    ModalProvider,
)

_MODAL = {
    "modal_base_url": "https://example.modal.run",
    "modal_model": "deepseek/deepseek-v4-pro",
}


class TestFamilyLaneRejectsTheDirectAnthropicLeg:
    """A kid- or guardian-triggered job cannot reach the subscription account."""

    def test_the_global_default_alone_cannot_put_a_family_job_on_anthropic(
        self,
    ) -> None:
        """A misconfigured global setting is refused, not obeyed."""
        settings = Settings(
            generation_provider="anthropic", anthropic_api_key="sk-ant-test"
        )

        with pytest.raises(ConfigurationError) as excinfo:
            build_provider(settings)

        assert "anthropic" in str(excinfo.value)
        assert "family" in str(excinfo.value)

    def test_an_override_cannot_put_a_family_job_on_anthropic_either(self) -> None:
        """Defence in depth: the per-job override is refused on this lane too."""
        settings = Settings(
            generation_provider="openrouter",
            openrouter_api_key="or-test",
            anthropic_api_key="sk-ant-test",
        )

        with pytest.raises(ConfigurationError):
            build_provider(settings, provider_override="anthropic", lane="family")

    def test_the_restrictive_lane_is_the_default(self) -> None:
        """Omitting the lane must fail closed, not open."""
        settings = Settings(
            generation_provider="anthropic", anthropic_api_key="sk-ant-test"
        )

        with pytest.raises(ConfigurationError):
            build_provider(settings)


class TestFamilyLanePermitsTheRoutedLegs:
    """OpenRouter and Modal are both acceptable for a family-triggered job."""

    def test_openrouter_is_permitted(self) -> None:
        """The primary leg builds normally on the restricted lane."""
        settings = Settings(
            generation_provider="openrouter",
            openrouter_api_key="or-test",
            provider_fallback_enabled=False,
        )

        assert build_provider(settings, lane="family") is not None

    def test_modal_is_permitted(self) -> None:
        """Modal is the second acceptable routed leg, not an admin-only one."""
        settings = Settings(generation_provider="modal", **_MODAL)

        assert isinstance(build_provider(settings, lane="family"), ModalProvider)

    def test_mock_is_permitted(self) -> None:
        """The test double is reachable on every lane; it makes no calls."""
        settings = Settings(generation_provider="mock")

        assert build_provider(settings, lane="family") is not None

    def test_a_permitted_cascade_still_reaches_its_modal_backstop(self) -> None:
        """The lane check must not disturb the three-leg cascade it wraps."""
        settings = Settings(
            generation_provider="openrouter", openrouter_api_key="or-test", **_MODAL
        )

        built = build_provider(settings, lane="family")

        assert isinstance(built, FallbackProvider)
        assert isinstance(built.legs[-1], ModalProvider)


class TestAdminLaneIsUnconstrained:
    """An admin choosing an allowlisted pair out of band is not lane-limited."""

    def test_anthropic_builds_on_the_admin_lane(self) -> None:
        """The direct leg remains reachable where the ruling permits it."""
        settings = Settings(
            generation_provider="anthropic", anthropic_api_key="sk-ant-test"
        )

        assert isinstance(build_provider(settings, lane="admin"), AnthropicProvider)

    def test_an_unknown_provider_is_still_rejected_on_the_admin_lane(self) -> None:
        """The lane rule adds a constraint; it removes none."""
        settings = Settings(generation_provider="mock")

        with pytest.raises(ConfigurationError, match="unknown generation_provider"):
            build_provider(settings, provider_override="nope", lane="admin")
