"""Unit tests for the generation worker and provider factory (no DB, no Redis).

Tests cover:
1. build_provider("mock") returns a MockProvider seeded with a valid canned story.
2. build_provider with deferred providers raises ConfigurationError.
3. The canned mock story is schema-valid (Storybook.model_validate succeeds).
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import MultipleResultsFound

from cyo_adventure.core.config import Settings
from cyo_adventure.core.config import settings as config_settings
from cyo_adventure.core.exceptions import (
    BusinessLogicError,
    ConfigurationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.generation import worker as worker_module
from cyo_adventure.generation.orchestrator import GenerationOutcome
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import (
    _CANNED_STORY,
    _CANNED_STORY_JSON,
    MockProvider,
    build_provider,
)
from cyo_adventure.generation.providers import (
    AnthropicProvider,
    FallbackProvider,
    ModalProvider,
    OpenRouterProvider,
)
from cyo_adventure.generation.usage import TokenUsage
from cyo_adventure.generation.worker import (
    _regate_after_transform,
    _review_stage2_override,
    _run_skeleton_fill,
    _should_persist_storybook,
    _SkeletonFillContext,
    _stamp_provider_accounting,
)
from cyo_adventure.storybook.models import AgeBand, Storybook
from cyo_adventure.storybook.reinsertion import verify_manifest
from cyo_adventure.storybook.sentinels import wrap
from cyo_adventure.storybook.theme_contract import (
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
)
from cyo_adventure.validator.gate import GateResult
from cyo_adventure.validator.report import ValidationReport
from cyo_adventure.validator.slots import DENYLIST_VERSION

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.db.models import GenerationJob
    from cyo_adventure.generation.concept import ConceptBrief
    from cyo_adventure.generation.provider import GenerationProvider


@pytest.fixture
def mock_settings() -> Settings:
    """Return a Settings instance with generation_provider='mock'."""
    return Settings(generation_provider="mock")  # type: ignore[call-arg]


class TestBuildProviderMock:
    """build_provider with generation_provider='mock'."""

    def test_returns_mock_provider_instance(self, mock_settings: Settings) -> None:
        """build_provider('mock') returns a MockProvider."""
        provider = build_provider(mock_settings)
        assert isinstance(provider, MockProvider)

    def test_mock_provider_has_enough_responses(self, mock_settings: Settings) -> None:
        """The mock provider queue has at least Stage A + Stage B + 3 repairs."""
        provider = build_provider(mock_settings)
        assert isinstance(provider, MockProvider)
        assert len(provider.responses) >= 5

    def test_mock_provider_responses_are_canned_json(
        self, mock_settings: Settings
    ) -> None:
        """Each queued response is the canned story JSON string."""
        provider = build_provider(mock_settings)
        assert isinstance(provider, MockProvider)
        for response in provider.responses:
            assert isinstance(response, str)
            parsed = json.loads(response)
            assert parsed["id"] == "s_mock_generated"


class TestBuildProviderLive:
    """build_provider assembles the live cascade and isolated legs from settings."""

    def test_anthropic_without_key_raises(self) -> None:
        """anthropic without a credential raises ConfigurationError by key name."""
        settings = Settings(generation_provider="anthropic", anthropic_api_key=None)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings, lane="admin")
        assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_anthropic_key_value_not_leaked_in_error(self) -> None:
        """A missing-key error never echoes any key value."""
        settings = Settings(generation_provider="anthropic", anthropic_api_key=None)  # type: ignore[call-arg]
        # lane="admin" on purpose: on the family lane this would raise the lane
        # error instead, and the assertion would pass without ever reaching the
        # credential path it claims to cover.
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings, lane="admin")
        assert "Bearer" not in str(exc_info.value)

    def test_anthropic_with_key_builds_bare_leg(self) -> None:
        """anthropic + key builds a single AnthropicProvider (no cascade)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="anthropic", anthropic_api_key="test-key"
        )
        provider = build_provider(settings, lane="admin")
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == settings.anthropic_model

    def test_openrouter_without_key_raises(self) -> None:
        """openrouter without a credential raises ConfigurationError by key name."""
        settings = Settings(generation_provider="openrouter", openrouter_api_key=None)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings)
        message = str(exc_info.value)
        assert "OPENROUTER_API_KEY" in message

    def test_openrouter_key_value_not_leaked_in_error(self) -> None:
        """A missing-key error never echoes any key value."""
        settings = Settings(generation_provider="openrouter", openrouter_api_key=None)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings)
        # The message references the variable by name only.
        assert "Bearer" not in str(exc_info.value)

    def test_openrouter_with_modal_configured_builds_three_leg_cascade(self) -> None:
        """openrouter + key + a configured Modal endpoint assembles the full cascade."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            modal_base_url="https://example--cyo.modal.run/v1",
            modal_model="google/gemma-4-26b-a4b-it",
            modal_proxy_key=None,
            modal_proxy_secret=None,
        )
        provider = build_provider(settings)
        assert isinstance(provider, FallbackProvider)
        assert len(provider.legs) == 3
        assert isinstance(provider.legs[0], OpenRouterProvider)
        assert isinstance(provider.legs[1], OpenRouterProvider)
        # The third leg is the non-OpenRouter backstop that replaced the
        # retired Ollama leg; without it the cascade is single-vendor.
        assert isinstance(provider.legs[2], ModalProvider)

    def test_openrouter_cascade_leg_order_matches_settings(self) -> None:
        """The cascade legs target the primary, fallback, and modal models in order."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            openrouter_model="anthropic/claude-sonnet-4.6",
            openrouter_fallback_model="google/gemma-4-31b-it:free",
            modal_base_url="https://example--cyo.modal.run/v1",
            modal_model="google/gemma-4-26b-a4b-it",
        )
        provider = build_provider(settings)
        assert isinstance(provider, FallbackProvider)
        names = [leg.name for leg in provider.legs]  # type: ignore[attr-defined]
        assert names == [
            "openrouter:anthropic/claude-sonnet-4.6",
            "openrouter:google/gemma-4-31b-it:free",
            "modal:google/gemma-4-26b-a4b-it",
        ]

    def test_openrouter_without_modal_degrades_to_two_leg_cascade(self) -> None:
        """An unconfigured Modal endpoint drops the leg rather than failing the build.

        build_modal_leg raises when MODAL_BASE_URL/MODAL_MODEL are unset, which
        is every local dev run, CI run, and Modal-less deploy. Including the leg
        unconditionally would turn all of those into hard generation failures.
        """
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
        )
        provider = build_provider(settings)
        assert isinstance(provider, FallbackProvider)
        assert len(provider.legs) == 2
        assert all(isinstance(leg, OpenRouterProvider) for leg in provider.legs)

    def test_half_configured_modal_endpoint_also_degrades(self) -> None:
        """A base url with no model is not "configured"; the leg is omitted, not built.

        modal_leg_configured requires BOTH fields, matching exactly what
        build_modal_leg demands, so a half-set endpoint can never reach the
        raise inside the cascade path.
        """
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            modal_base_url="https://example--cyo.modal.run/v1",
        )
        provider = build_provider(settings)
        assert isinstance(provider, FallbackProvider)
        assert len(provider.legs) == 2

    def test_single_vendor_cascade_is_warned_about(self) -> None:
        """Degrading to two OpenRouter legs must be loud, not silent.

        Both remaining legs are the same vendor on the same account, so the
        cascade no longer spans two failure domains. That is a real availability
        posture change and an operator has to be able to see it in the logs.
        """
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
        )
        with patch("cyo_adventure.generation.provider.logger") as mock_logger:
            build_provider(settings)
        mock_logger.warning.assert_called_once()
        assert mock_logger.warning.call_args.args[0] == (
            "generation.cascade_single_vendor"
        )

    def test_configured_modal_cascade_emits_no_warning(self) -> None:
        """The healthy three-leg path must not cry wolf."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            modal_base_url="https://example--cyo.modal.run/v1",
            modal_model="google/gemma-4-26b-a4b-it",
            modal_proxy_key=None,
            modal_proxy_secret=None,
        )
        with patch("cyo_adventure.generation.provider.logger") as mock_logger:
            build_provider(settings)
        mock_logger.warning.assert_not_called()

    def test_openrouter_fallback_disabled_returns_bare_primary(self) -> None:
        """With fallback disabled the bare primary leg is returned (isolation runs)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            provider_fallback_enabled=False,
        )
        provider = build_provider(settings)
        assert isinstance(provider, OpenRouterProvider)
        # The shipped fill default since D1 (ruled 2026-08-23, `UW-C346`).
        assert provider.name == "openrouter:deepseek/deepseek-v4-pro"

    def test_retired_ollama_provider_is_rejected(self) -> None:
        """ "ollama" is no longer a constructible backend, at the Settings boundary.

        Pydantic rejects it against the generation_provider Literal, so a stale
        CYO_ADVENTURE_GENERATION_PROVIDER=ollama in a deploy env fails fast at
        startup rather than reaching build_provider's unknown-provider raise.
        """
        with pytest.raises(PydanticValidationError):
            Settings(generation_provider="ollama")  # type: ignore[call-arg,arg-type]

    def test_modal_without_base_url_raises(self) -> None:
        """modal without MODAL_BASE_URL raises ConfigurationError by name."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="modal", modal_model="google/gemma-4-26b-a4b-it"
        )
        with pytest.raises(ConfigurationError, match="MODAL_BASE_URL"):
            build_provider(settings)

    def test_modal_without_model_raises(self) -> None:
        """modal without MODAL_MODEL raises ConfigurationError by name."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="modal",
            modal_base_url="https://example--cyo-standard.modal.run/v1",
        )
        with pytest.raises(ConfigurationError, match="MODAL_MODEL"):
            build_provider(settings)

    @pytest.mark.parametrize(
        ("base_url", "model", "expected"),
        [
            ("   ", "google/gemma-4-26b-a4b-it", "MODAL_BASE_URL"),
            ("https://example--cyo-standard.modal.run/v1", "  ", "MODAL_MODEL"),
            ("\t", "\n", "MODAL_BASE_URL"),
        ],
    )
    def test_modal_with_whitespace_only_config_raises(
        self, base_url: str, model: str, expected: str
    ) -> None:
        """Whitespace-only config is absent on the direct path too, not just the cascade.

        ``Settings.modal_leg_configured`` treats a whitespace-only half as
        absent so a compose interpolation of an unset variable
        (``${MODAL_MODEL:- }``) omits the cascade leg instead of poisoning it.
        This adapter has to agree: when it did not,
        ``generation_provider="modal"`` built a ModalProvider whose base url was
        ``"   "`` and whose reported name was ``"modal:   "``, so the leg failed
        on every call and mis-attributed itself while doing so, while the
        cascade path correctly degraded on the very same settings.
        """
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="modal", modal_base_url=base_url, modal_model=model
        )
        assert settings.modal_leg_configured is False
        with pytest.raises(ConfigurationError, match=expected):
            build_provider(settings)

    def test_modal_config_is_stripped_before_use(self) -> None:
        """Surrounding whitespace never reaches the HTTP client or the leg's name.

        A padded value is a dotenv/compose artifact, never an intent, and it
        would otherwise ride into the request url and into the provider
        attribution that reviewer independence is computed from.
        """
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="modal",
            modal_base_url="  https://example--cyo-standard.modal.run/v1  ",
            modal_model="  google/gemma-4-26b-a4b-it\t",
        )
        provider = build_provider(settings)
        assert isinstance(provider, ModalProvider)
        assert provider.model == "google/gemma-4-26b-a4b-it"
        assert provider.name == "modal:google/gemma-4-26b-a4b-it"

    def test_modal_with_config_returns_bare_leg(self) -> None:
        """modal with both required settings returns a bare ModalProvider (no cascade)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="modal",
            modal_base_url="https://example--cyo-standard.modal.run/v1",
            modal_model="google/gemma-4-26b-a4b-it",
        )
        provider = build_provider(settings)
        assert isinstance(provider, ModalProvider)
        assert provider.name == "modal:google/gemma-4-26b-a4b-it"

    def test_modal_partial_proxy_credentials_raises_at_settings_construction(
        self,
    ) -> None:
        """A half-set MODAL_PROXY pair now fails at startup, not at job time.

        This used to raise from build_provider. Since Modal became the default
        cascade's third leg, waiting until then would mean failing every
        generation job on a serving deploy, so the check moved to a Settings
        model_validator (`_require_modal_proxy_credentials_together`).
        """
        with pytest.raises(ConfigurationError, match="MODAL_PROXY_KEY"):
            Settings(  # type: ignore[call-arg]
                generation_provider="modal",
                modal_base_url="https://example--cyo-standard.modal.run/v1",
                modal_model="google/gemma-4-26b-a4b-it",
                modal_proxy_key="only-the-key",
            )

    def test_build_modal_leg_still_guards_partial_credentials(self) -> None:
        """build_modal_leg keeps its own half-set guard as defence in depth.

        The Settings validator above makes this branch unreachable through
        normal construction, but model_construct (and any future caller that
        hand-builds a Settings) bypasses validators entirely, so the adapter
        must not assume the pair was already checked.
        """
        settings = Settings.model_construct(
            generation_provider="modal",
            modal_base_url="https://example--cyo-standard.modal.run/v1",
            modal_model="google/gemma-4-26b-a4b-it",
            modal_proxy_key="only-the-key",
            modal_proxy_secret=None,
            modal_timeout_seconds=180,
        )
        with pytest.raises(ConfigurationError, match="MODAL_PROXY_KEY"):
            build_provider(settings)


class TestBuildProviderOverrides:
    """build_provider's keyword-only provider_override/model_override (WS-C PR1)."""

    def test_no_override_matches_prior_behavior_openrouter(self) -> None:
        """Calling with no overrides is identical to today's positional-only call."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter", openrouter_api_key="test-key"
        )
        without_kwargs = build_provider(settings)
        with_no_overrides = build_provider(
            settings, provider_override=None, model_override=None
        )
        assert isinstance(without_kwargs, FallbackProvider)
        assert isinstance(with_no_overrides, FallbackProvider)
        names_a = [leg.name for leg in without_kwargs.legs]  # type: ignore[attr-defined]
        names_b = [leg.name for leg in with_no_overrides.legs]  # type: ignore[attr-defined]
        assert names_a == names_b

    def test_provider_override_wins_over_global_setting(self) -> None:
        """provider_override picks the leg even when settings.generation_provider differs."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="mock", anthropic_api_key="test-key"
        )
        provider = build_provider(settings, provider_override="anthropic", lane="admin")
        assert isinstance(provider, AnthropicProvider)

    def test_model_override_replaces_openrouter_primary_only(self) -> None:
        """model_override replaces the primary leg's model; the fallback leg is untouched."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            openrouter_fallback_model="anthropic/claude-sonnet-4.6",
        )
        provider = build_provider(settings, model_override="anthropic/claude-opus-4.8")
        assert isinstance(provider, FallbackProvider)
        names = [leg.name for leg in provider.legs]  # type: ignore[attr-defined]
        assert names[0] == "openrouter:anthropic/claude-opus-4.8"
        assert names[1] == "openrouter:anthropic/claude-sonnet-4.6"

    def test_model_override_replaces_anthropic_model(self) -> None:
        """model_override replaces the single anthropic leg's model."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="anthropic", anthropic_api_key="test-key"
        )
        provider = build_provider(
            settings, model_override="claude-opus-4-8", lane="admin"
        )
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-opus-4-8"

    def test_retired_provider_override_raises_a_named_error(self) -> None:
        """A job row still naming a retired provider fails with an actionable message.

        This is the one route by which "ollama" can still reach build_provider:
        a job enqueued before the retirement deployed, whose
        authoring_metadata the worker passes through verbatim. The generic
        unknown-provider message would not tell an operator that the cause is a
        stale row rather than a typo.
        """
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings, provider_override="ollama")
        message = str(exc_info.value)
        assert "retired" in message
        assert "ollama" in message
        # Must not be mistaken for the typo path.
        assert "unknown generation_provider" not in message

    def test_a_typo_never_gets_the_retirement_message(self) -> None:
        """A genuine typo is not reported as a retirement, on either lane.

        The invariant is the discrimination, not one exact string: on the
        family lane FAMILY_LANE_PROVIDERS rejects an unrecognised name before
        the unknown-provider branch is reached, so pinning "unknown
        generation_provider" here would assert the ordering of a guard this
        test is not about. What must hold on every lane is that a misspelling
        is never attributed to a retirement.
        """
        settings = Settings()  # type: ignore[call-arg]
        for lane in ("family", "admin"):
            with pytest.raises(ConfigurationError) as exc_info:
                build_provider(settings, provider_override="ollamaa", lane=lane)
            assert "retired" not in str(exc_info.value)

    def test_a_typo_on_the_admin_lane_keeps_the_generic_error(self) -> None:
        """Past the lane guard, an unrecognised name still names itself.

        The admin lane carries no allowlist, so this is the one path that
        reaches build_provider's own unknown-provider branch and can assert
        its message directly.
        """
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings, provider_override="ollamaa", lane="admin")
        assert "unknown generation_provider" in str(exc_info.value)

    def test_unknown_provider_override_raises_configuration_error(self) -> None:
        """A provider_override outside the known branches raises, naming the value."""
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            # lane="admin" so the unknown-provider branch is what raises;
            # the family lane would reject the value earlier, for a different
            # reason, and this test would stop covering the branch it names.
            build_provider(
                settings, provider_override="not-a-real-provider", lane="admin"
            )
        assert "not-a-real-provider" in str(exc_info.value)


class TestCannedStorySchemaValid:
    """The canned mock story satisfies the Storybook schema."""

    def test_canned_story_dict_validates(self) -> None:
        """_CANNED_STORY is a valid Storybook (Pydantic model_validate succeeds)."""
        book = Storybook.model_validate(_CANNED_STORY)
        assert book.id == "s_mock_generated"
        assert book.metadata.tier == 1
        # Compared against the source rather than a literal: the assertion is
        # "validation drops no node", which is what makes the round-trip
        # meaningful. A literal count instead measures how many nodes the mock
        # story happens to have, so it fails whenever the story legitimately
        # changes shape (it did, when PL-25's floor forced an opening node).
        source_nodes = _CANNED_STORY["nodes"]
        assert isinstance(source_nodes, list)
        assert len(book.nodes) == len(source_nodes)

    def test_canned_story_json_round_trips(self) -> None:
        """JSON-serialised canned story round-trips through Storybook validation."""
        parsed = json.loads(_CANNED_STORY_JSON)
        book = Storybook.model_validate(parsed)
        assert book.id == "s_mock_generated"

    def test_canned_story_ending_count_matches_nodes(self) -> None:
        """The canned story's ending nodes agree with metadata.ending_count."""
        book = Storybook.model_validate(_CANNED_STORY)
        ending_nodes = [node for node in book.nodes if node.is_ending]
        assert len(ending_nodes) == book.metadata.ending_count
        assert book.metadata.ending_count >= 3

    def test_canned_story_start_node_exists(self) -> None:
        """start_node references an existing node id."""
        book = Storybook.model_validate(_CANNED_STORY)
        node_ids = {node.id for node in book.nodes}
        assert book.start_node in node_ids


class TestShouldPersistStorybook:
    """_should_persist_storybook: the widened persist gate (Item 3).

    A pure function over GenerationOutcome, so these are unit tests with no
    database, provider, or session involved -- the regression guard for the
    persist-gating logic itself, independent of the integration-level
    end-to-end coverage in tests/integration/test_generation_worker.py.
    """

    def test_passed_with_storybook_persists(self) -> None:
        """The pre-existing "passed" case must keep persisting."""
        outcome = GenerationOutcome(
            status="passed",
            storybook={"id": "s1"},
            report={},
            attempts=0,
            stage_log=[],
        )
        assert _should_persist_storybook(outcome) is True

    def test_passed_with_no_storybook_does_not_persist(self) -> None:
        """A "passed" outcome with no storybook document has nothing to persist."""
        outcome = GenerationOutcome(
            status="passed", storybook=None, report={}, attempts=0, stage_log=[]
        )
        assert _should_persist_storybook(outcome) is False

    def test_stage1_downgraded_needs_review_persists(self) -> None:
        """A Stage 1 downgrade on an otherwise-clean fill persists.

        The report key rides along as the diagnostic a reviewer reads; the
        persist decision comes from ``clean_downgrade``.
        """
        outcome = GenerationOutcome(
            status="needs_review",
            storybook={"id": "s1"},
            report={"stage1_fidelity_violations": ["some violation"]},
            attempts=0,
            stage_log=[],
            clean_downgrade=True,
        )
        assert _should_persist_storybook(outcome) is True

    def test_fill_rate_only_needs_review_persists_the_storybook(self) -> None:
        """A fill-rate-floor downgrade on an otherwise-clean fill persists.

        PR #737 review, finding C1: without this, a fill-rate-only
        needs_review fell into the any-other branch, no Storybook was
        created, moderation never ran, and the reviewer the downgrade exists
        for had no book to review; stricter than the hard block ruling 9.3
        forbids.
        """
        outcome = GenerationOutcome(
            status="needs_review",
            storybook={"id": "s1"},
            report={
                "fill_rate": 0.44,
                "fill_rate_floor": 0.6,
                "fill_rate_downgrade": True,
            },
            clean_downgrade=True,
            attempts=0,
            stage_log=[],
        )
        assert _should_persist_storybook(outcome) is True

    def test_a_rewriting_transform_keeps_the_clean_downgrade_signal(self) -> None:
        """A real reinsertion transform must not strip the persist signal.

        ``_regate_after_transform`` rebuilds the report from the FRESH gate
        verdict and nests the pre-transform one under ``"pre_reinsertion_gate"``,
        so a clean-downgrade signal carried as a top-level report key does not
        survive a transform that actually rewrites the document. A fill that was
        downgraded on a quality axis AND rewritten would then be dropped
        entirely: no Storybook, no version, no moderation, and a job row
        pointing at a book nobody can reach, which is the exact outcome the
        downgrade paths exist to prevent. The signal therefore rides the
        outcome, which no report rebuild can touch.

        Live, not dormant: `skeletons/10-13/the-midnight-museum.contract.json`
        declares `HERO` as `kind: personalizable`, so that book rewrites bodies
        and reaches this path (ADR-023 D4). The 46 other contracts on disk take
        the byte-identical short-circuit.
        """
        rewritten = copy.deepcopy(_CANNED_STORY)
        nodes = rewritten["nodes"]
        assert isinstance(nodes, list)
        first = nodes[0]
        assert isinstance(first, dict)
        first["body"] = str(first["body"]) + " The lantern guttered once more."

        pre = GenerationOutcome(
            status="needs_review",
            storybook=copy.deepcopy(_CANNED_STORY),
            report={"fill_rate": 0.51, "fill_rate_downgrade": True},
            attempts=0,
            stage_log=[],
            clean_downgrade=True,
        )
        status, report, clean_downgrade = _regate_after_transform(
            pre, rewritten, skeleton_slug="s"
        )
        persisted = GenerationOutcome(
            status=status,
            storybook=rewritten,
            report=report,
            attempts=pre.attempts,
            stage_log=pre.stage_log,
            # The RECONCILED flag, not `pre.clean_downgrade`. Reading the
            # returned value is the whole point: it is what the caller stores.
            clean_downgrade=clean_downgrade,
        )
        # The report key really is gone: this is the stripping being guarded.
        assert "fill_rate_downgrade" not in persisted.report
        assert _should_persist_storybook(persisted) is True

    def test_a_transform_that_trips_the_safety_gate_clears_the_clean_downgrade(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A regate that finds a NEW safety problem must not persist the book.

        The reachable combination: a fill downgraded on a quality axis
        (`clean_downgrade=True`, status `needs_review`), whose reinsertion
        transform rewrites the document, whose post-transform gate then
        safety-flags it. Severity ties favour the pre-transform status, so
        `status` stays `needs_review` and reveals nothing; the report that
        gets persisted is the post-transform one describing the safety flag.
        Carrying the flag through unchanged would persist a safety-flagged
        book, which `_should_persist_storybook` documents as forbidden ("those
        are verdicts about content that has NOT been cleared").
        """
        rewritten = copy.deepcopy(_CANNED_STORY)
        nodes = rewritten["nodes"]
        assert isinstance(nodes, list)
        first = nodes[0]
        assert isinstance(first, dict)
        first["body"] = str(first["body"]) + " The lantern guttered once more."

        monkeypatch.setattr(
            worker_module,
            "run_gate",
            lambda *_a, **_k: GateResult(
                report=ValidationReport(),
                blocked=False,
                safety_flagged=True,
                context="fill_result",
            ),
        )

        pre = GenerationOutcome(
            status="needs_review",
            storybook=copy.deepcopy(_CANNED_STORY),
            report={"fill_rate": 0.51, "fill_rate_downgrade": True},
            attempts=0,
            stage_log=[],
            clean_downgrade=True,
        )
        status, report, clean_downgrade = _regate_after_transform(
            pre, rewritten, skeleton_slug="s"
        )

        # The status is NOT the tell: the severity tie keeps the pre-transform
        # verdict, so it reads identically to the benign quality downgrade.
        assert status == "needs_review"
        assert clean_downgrade is False

        persisted = GenerationOutcome(
            status=status,
            storybook=rewritten,
            report=report,
            attempts=pre.attempts,
            stage_log=pre.stage_log,
            clean_downgrade=clean_downgrade,
        )
        assert _should_persist_storybook(persisted) is False

    def test_a_diagnostic_report_key_alone_does_not_persist(self) -> None:
        """Recording violations for a reader must not flip the persist decision.

        The clean-downgrade report keys are diagnostics that review surfaces
        read. Any future path that recorded them for a human (say, on a fill
        that is ALSO safety-flagged) would, under the old key-as-signal rule,
        silently start persisting a storybook the pre-existing semantics
        deliberately drop.
        """
        outcome = GenerationOutcome(
            status="needs_review",
            storybook={"id": "s1"},
            report={"stage1_fidelity_violations": ["node 'n1' is 12 words"]},
            attempts=0,
            stage_log=[],
        )
        assert _should_persist_storybook(outcome) is False

    def test_safety_flagged_needs_review_does_not_persist(self) -> None:
        """Regression guard: a safety-flagged needs_review (no Stage 1 key) must
        NOT persist -- this is the pre-existing, non-Plan-2 semantics that the
        widened gate must not change."""
        outcome = GenerationOutcome(
            status="needs_review",
            storybook={"id": "s1"},
            report={"safety_flagged": True},
            attempts=0,
            stage_log=[],
        )
        assert _should_persist_storybook(outcome) is False

    def test_gate_blocked_needs_review_with_no_storybook_does_not_persist(self) -> None:
        """Regression guard: gate-blocked-with-doc-exhausted repairs still has no
        storybook to persist here (fill_skeleton's own outcome, pre-Stage-1)."""
        outcome = GenerationOutcome(
            status="needs_review",
            storybook=None,
            report={},
            attempts=3,
            stage_log=[],
        )
        assert _should_persist_storybook(outcome) is False

    def test_failed_does_not_persist(self) -> None:
        """A "failed" outcome never persists, Stage 1 key or not."""
        outcome = GenerationOutcome(
            status="failed",
            storybook={"id": "s1"},
            report={"stage1_fidelity_violations": ["irrelevant here"]},
            attempts=3,
            stage_log=[],
        )
        assert _should_persist_storybook(outcome) is False


class TestReviewStage2Override:
    """_review_stage2_override: the Stage 2 review-model override selector.

    A pure helper the worker uses to pass an admin's review_stage2_model choice
    (from authoring_metadata) into the moderation pipeline; it must degrade any
    missing or wrong-typed value to None (the default reviewer) rather than
    forwarding junk.
    """

    def test_none_authoring_returns_none(self) -> None:
        """A fresh (non-skeleton) job carries no authoring_metadata."""
        assert _review_stage2_override(None) is None

    def test_valid_string_override_is_forwarded(self) -> None:
        """A string review_stage2_model is returned verbatim."""
        authoring = {"review_stage2_model": "stage2-override-model"}
        assert _review_stage2_override(authoring) == "stage2-override-model"

    def test_missing_key_returns_none(self) -> None:
        """authoring_metadata without the key means the default reviewer."""
        assert _review_stage2_override({"skeleton_slug": "x"}) is None

    def test_non_string_value_returns_none(self) -> None:
        """A wrong-typed override degrades to None instead of forwarding junk."""
        assert _review_stage2_override({"review_stage2_model": 123}) is None


@pytest.mark.asyncio
async def test_run_skeleton_fill_missing_slug_raises() -> None:
    """authoring_metadata without a string skeleton_slug is a clean ResourceNotFoundError.

    The guard fires before the brief/provider are ever touched, so a job
    constructed outside build_authoring_plan (no skeleton_slug) fails as a
    handled ProjectBaseError rather than crashing deeper in the fill pipeline.
    """
    fill_context = _SkeletonFillContext(
        authoring={"theme_brief": {}},  # no skeleton_slug key
        brief=cast("ConceptBrief", object()),
        effective_provider=cast("GenerationProvider", object()),
        pii=PiiContext(child_names=frozenset()),
    )
    with pytest.raises(ResourceNotFoundError):
        await _run_skeleton_fill(fill_context)


@pytest.mark.asyncio
async def test_run_skeleton_fill_threads_stage1_params_into_fill_skeleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker threads the Stage 1 gate inputs into the folded fill_skeleton (#133).

    After the rework, the Stage 1 fidelity gate runs INSIDE
    orchestrator.fill_skeleton's bounded repair loop (see the acceptance and
    shared-budget tests in tests/unit/test_orchestrator.py); the worker's job
    is only to load the matched skeleton and hand fill_skeleton everything the
    gate needs. This asserts the loaded skeleton (the gate's ``original``),
    ``settings``, the admin ``review_stage1_model`` override, and the ``prep_model``
    default (#134) all reach fill_skeleton, and that the worker no longer runs
    the gate or an outer retry loop itself.
    """
    fake_skeleton: dict[str, object] = {"id": "s_x", "nodes": []}
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: fake_skeleton)
    # This test exercises the legacy (no-contract) fill path explicitly. The
    # real slug it uses ("the-cave-of-echoes") now ships a theme contract
    # (WS-2 Wave C0), so force the legacy dispatch branch rather than depend on
    # the on-disk catalog state; the bound-path dispatch is covered by its own
    # tests below.
    monkeypatch.setattr(worker_module, "load_contract_for", lambda *_a, **_k: None)

    captured: dict[str, object] = {}

    async def _fake_fill_skeleton(
        skeleton: dict[str, object],
        theme_brief: dict[str, object],
        provider: object,
        pii: object,
        **kwargs: object,
    ) -> GenerationOutcome:
        captured["skeleton"] = skeleton
        captured["theme_brief"] = theme_brief
        captured["provider"] = provider
        captured["pii"] = pii
        captured.update(kwargs)
        return GenerationOutcome(
            status="passed",
            storybook={"id": "s_x", "nodes": []},
            report={},
            attempts=0,
            stage_log=[],
        )

    monkeypatch.setattr(worker_module, "fill_skeleton", _fake_fill_skeleton)

    brief = cast(
        "ConceptBrief",
        SimpleNamespace(age_band=SimpleNamespace(value="8-11"), content_nogo=[]),
    )
    provider = cast("GenerationProvider", object())
    pii = PiiContext(child_names=frozenset())
    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "the-cave-of-echoes",
                "theme_brief": {"premise": "a fox"},
                "review_stage1_model": "admin-chosen-reviewer",
            },
            brief=brief,
            effective_provider=provider,
            pii=pii,
            prep_model="the-prep-model",
        )
    )

    assert outcome.status == "passed"
    # The loaded skeleton is the gate's UNFILLED "original"; the fill/repair
    # provider and pii pass straight through.
    assert captured["skeleton"] is fake_skeleton
    assert captured["theme_brief"] == {"premise": "a fox"}
    assert captured["provider"] is provider
    assert captured["pii"] is pii
    # Stage 1 gate inputs: settings enables the gate, plus the review-model
    # override and the prep_model fallback (#134).
    assert captured["settings"] is config_settings
    assert captured["review_stage1_model"] == "admin-chosen-reviewer"
    assert captured["prep_model"] == "the-prep-model"


class _FakeOverrideResult:
    """Minimal ``session.scalars()`` return double: no rows, every time."""

    def scalar_one_or_none(self) -> None:
        return None


class _OverrideCapturedError(Exception):
    """Sentinel raised by the fake build_provider once it records the overrides.

    Lets test_effective_provider_reads_job_authoring_override stop the run
    deterministically right after the override is captured, so it can assert
    on a specific exception type instead of a broad ``Exception`` and does not
    depend on the fake session's downstream query behavior.
    """


class _FakeOverrideSession:
    """Minimal session double for test_effective_provider_reads_job_authoring_override.

    Module-level (not nested in the test body) so the test function's own
    control flow stays simple; only the job/concept it was built with are
    ever returned.
    """

    def __init__(self, job: object, concept: object) -> None:
        self.job = job
        self.concept = concept
        self.added: list[object] = []

    async def get(self, model: type, ident: object) -> object:
        from cyo_adventure.db.models import Concept, GenerationJob

        if model is GenerationJob and getattr(self.job, "id", None) == ident:
            return self.job
        if model is Concept and getattr(self.concept, "id", None) == ident:
            return self.concept
        return None

    async def scalars(self, *_args: object, **_kwargs: object) -> _FakeOverrideResult:
        return _FakeOverrideResult()

    def add(self, obj: object) -> None:
        # WS-D instruments the failure path: _record_failure writes a
        # generation_failed PipelineEvent via record_event, which calls
        # session.add. Capture it so the failure path runs to completion
        # instead of raising AttributeError before the override read this
        # test is checking.
        self.added.append(obj)

    async def flush(self) -> None:
        # _load_and_start_job flushes the "running" status write before
        # build_provider is ever reached; without this the fake session
        # would raise AttributeError too early to exercise the override
        # read this test is checking.
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


# A valid ConceptBrief payload (mirrors tests/unit/test_worker_persistence.py's
# seed) so generate_story can run the full pipeline to a terminal status.
_FRESHGEN_BRIEF: dict[str, object] = {
    "premise": "A brave explorer discovers a hidden garden.",
    "protagonist": {"name": "Captain Rosa", "age": 9, "role": "young explorer"},
    "point_of_view": "second",
    "age_band": "8-11",
    "reading_level_target": 3.0,
    "tier": 1,
    "tone": "adventurous",
    "themes_allowed": ["exploration", "nature"],
    "content_nogo": [],
    "target_node_count": 4,
    "ending_count": 1,
    "structure_pattern": "time_cave",
    "desired_variables": [],
    "special_constraints": [],
}


class _FreshGenResult:
    """SQLAlchemy Result double yielding no child-name rows (empty PII).

    Also answers ``scalar_one_or_none`` with ``None`` so the WS-7 D7 request-row
    resolution (``_stamp_request_interpretation``) no-ops in the unit doubles
    that reuse this result (no originating request row is modeled).
    """

    def all(self) -> list[tuple[str]]:
        return []

    def scalar_one_or_none(self) -> None:
        return None


class _FreshGenSession:
    """Full-pipeline session double: enough surface for generate_story +
    persist + moderation to run a fresh_generation job to a terminal status.

    Unlike _FakeOverrideSession (which deliberately fails downstream), this
    supports the whole happy path so the routing assertion sees a real
    terminal status rather than the skeleton_slug ResourceNotFoundError.
    """

    def __init__(self, job: object, concept: object) -> None:
        self.job = job
        self.concept = concept
        self.added: list[object] = []

    async def get(self, model: type, ident: object) -> object | None:
        from cyo_adventure.db.models import Concept, GenerationJob

        if model is GenerationJob and getattr(self.job, "id", None) == ident:
            return self.job
        if model is Concept and getattr(self.concept, "id", None) == ident:
            return self.concept
        return None

    async def execute(self, *_args: object, **_kwargs: object) -> _FreshGenResult:
        return _FreshGenResult()

    async def scalar(self, *_args: object, **_kwargs: object) -> None:
        # No owning StoryRequest -> link_series_position takes its no-op path.
        return None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class TestEffectiveProviderPerJobOverride:
    """run_generation_job reads a per-job provider/model override off the job row (WS-C PR1)."""

    def test_authoring_provider_override_reads_string_only(self) -> None:
        """A non-string 'provider' value in authoring_metadata is ignored, not trusted."""
        from cyo_adventure.generation.worker import _authoring_provider_override

        assert _authoring_provider_override(None) is None
        assert _authoring_provider_override({"provider": "anthropic"}) == "anthropic"
        assert _authoring_provider_override({"provider": 123}) is None
        assert _authoring_provider_override({}) is None

    def test_authoring_model_override_reads_string_only(self) -> None:
        """A non-string 'model' value in authoring_metadata is ignored, not trusted."""
        from cyo_adventure.generation.worker import _authoring_model_override

        assert _authoring_model_override(None) is None
        assert (
            _authoring_model_override({"model": "claude-opus-4-8"}) == "claude-opus-4-8"
        )
        assert _authoring_model_override({"model": None}) is None

    @pytest.mark.asyncio
    async def test_effective_provider_reads_job_authoring_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run_generation_job builds the provider AFTER the job row loads, honoring
        the job's authoring_metadata provider/model override over global settings.
        """
        import uuid as uuid_mod

        from cyo_adventure.db.models import Concept, GenerationJob
        from cyo_adventure.generation import worker as worker_module

        captured: dict[str, object] = {}

        def fake_build_provider(
            settings: object,
            *,
            provider_override: str | None,
            model_override: str | None,
            lane: str,
        ) -> MockProvider:
            captured["provider_override"] = provider_override
            captured["model_override"] = model_override
            captured["lane"] = lane
            # Stop the run right here: this test only checks that
            # build_provider was called with the job's override, so raise a
            # specific sentinel rather than letting the run fail later with an
            # unpredictable downstream error.
            raise _OverrideCapturedError

        monkeypatch.setattr(worker_module, "build_provider", fake_build_provider)

        job_id = uuid_mod.uuid4()
        concept_id = uuid_mod.uuid4()

        job = GenerationJob(
            id=job_id,
            concept_id=concept_id,
            status="queued",
            authoring_metadata={
                "provider": "openrouter",
                "model": "deepseek/deepseek-v4-pro",
            },
        )
        concept = Concept(
            id=concept_id, family_id=uuid_mod.uuid4(), brief={"age_band": "8-11"}
        )

        # This test asserts only that build_provider is CALLED with the job's
        # override before the pipeline runs. It does not drive the full
        # pipeline (the existing end-to-end worker tests cover that): the fake
        # build_provider records the overrides into `captured` and then raises
        # _OverrideCapturedError to stop the run immediately. The real assertion is
        # on `captured`.
        session_ctx = _FakeOverrideSession(job, concept)

        def factory() -> object:
            # session_factory must be a plain (sync) callable returning an
            # async context manager directly, matching get_session()'s
            # signature; an `async def` here would return an unawaited
            # coroutine instead of the context manager `async with` needs.
            class _Ctx:
                async def __aenter__(self) -> _FakeOverrideSession:
                    return session_ctx

                async def __aexit__(self, *exc: object) -> None:
                    return None

            return _Ctx()

        # The sentinel raised by the fake build_provider propagates out of
        # run_generation_job after _record_failure records the failure (the
        # worker re-raises unexpected exceptions so RQ marks the job failed).
        # This is an async test inside pytest-asyncio's event loop, so the
        # coroutine is awaited directly rather than via asyncio.run.
        with pytest.raises(_OverrideCapturedError):
            await worker_module.run_generation_job(job_id, session_factory=factory)

        assert captured["provider_override"] == "openrouter"
        assert captured["model_override"] == "deepseek/deepseek-v4-pro"
        # D1 (2026-08-23, UW-C346): every job this worker runs serves a family
        # story request, so the worker states the restricted lane explicitly
        # rather than relying on build_provider's default. An admin's
        # allowlisted override narrows WHICH permitted leg runs; it cannot
        # widen the lane, because the book still reaches a child.
        assert captured["lane"] == "family"

    @pytest.mark.asyncio
    async def test_effective_provider_config_error_does_not_crash_finally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ConfigurationError raised DURING provider resolution must not turn the
        finally guard into an UnboundLocalError.

        This pins the exact invariant the ``#CRITICAL: concurrency`` comment in
        run_generation_job claims: ``effective_provider`` is bound to the
        injected ``provider`` arg (None in production) BEFORE the ``try``, so
        when ``build_provider`` raises while resolving the live adapter (after
        the job row loads, while ``effective_provider`` is still None), the
        top-level ``finally`` guard can still call
        ``_record_failure(..., provider=effective_provider)`` without an
        ``UnboundLocalError``. If the binding were moved inside the ``try``
        (after the ``build_provider`` call), that call would raise before the
        assignment, the ``finally`` would reference an unbound local, and the
        ``UnboundLocalError`` would replace the ConfigurationError, failing the
        ``pytest.raises(ConfigurationError)`` below.
        """
        import uuid as uuid_mod

        from cyo_adventure.db.models import Concept, GenerationJob
        from cyo_adventure.generation import worker as worker_module

        def raising_build_provider(
            settings: object,
            *,
            provider_override: str | None,
            model_override: str | None,
            lane: str,
        ) -> object:
            msg = "no such provider"
            raise ConfigurationError(msg)

        monkeypatch.setattr(worker_module, "build_provider", raising_build_provider)

        job_id = uuid_mod.uuid4()
        concept_id = uuid_mod.uuid4()

        job = GenerationJob(
            id=job_id,
            concept_id=concept_id,
            status="queued",
            authoring_metadata=None,
        )
        concept = Concept(
            id=concept_id, family_id=uuid_mod.uuid4(), brief={"age_band": "8-11"}
        )
        session_ctx = _FakeOverrideSession(job, concept)

        def factory() -> object:
            class _Ctx:
                async def __aenter__(self) -> _FakeOverrideSession:
                    return session_ctx

                async def __aexit__(self, *exc: object) -> None:
                    return None

            return _Ctx()

        # No injected provider -> effective_provider is None when build_provider
        # runs. build_provider raises ConfigurationError DURING resolution. The
        # function has no `except`, so that error re-propagates out of the
        # try/finally AFTER the finally guard runs. The guard's _record_failure
        # call must succeed (effective_provider bound to the pre-try None), so
        # what surfaces is the ConfigurationError, never an UnboundLocalError.
        with pytest.raises(ConfigurationError):
            await worker_module.run_generation_job(job_id, session_factory=factory)

        # Finally-guard side effect reached: the still-"running" row was
        # force-failed via _record_failure (which tolerates provider=None).
        # This proves the guard ran to completion rather than dying on an
        # UnboundLocalError before recording anything.
        assert job.status == "failed"
        # Changed 2026-08-22: the guard used to record the literal string
        # "interrupted" for every in-flight exception, which erased the one
        # piece of information an operator needs. It now recovers the live
        # exception via sys.exc_info() and records its message, so a job that
        # died on an unresolvable provider says so on its own row instead of
        # sending the reader to the worker logs. Still discriminating: this
        # function has no `except`, so the guard is the only writer that can
        # reach `job.error`, and reading the ConfigurationError's own message
        # here proves the guard both ran and saw the real cause.
        assert job.error == "no such provider"

    @pytest.mark.asyncio
    async def test_fresh_generation_with_provider_override_routes_to_generate_story(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fresh_generation job whose authoring_metadata carries only
        provider/model (NO skeleton_slug) must route to generate_story, not
        skeleton fill.

        Regression guard for the routing discriminator: build_authoring_plan
        now stamps ``{"provider", "model"}`` on EVERY automated_provider job,
        including fresh_generation. If the worker routed on ``authoring is not
        None`` (the pre-fix signal), this job would be misrouted into
        _run_skeleton_fill and die with
        ``ResourceNotFoundError("authoring_metadata.skeleton_slug is missing or
        not a string")`` on every run. Routing on a string ``skeleton_slug``
        instead sends it to generate_story, which reaches a terminal status.
        """
        import uuid as uuid_mod

        from cyo_adventure.db.models import Concept, GenerationJob
        from cyo_adventure.generation import worker as worker_module

        # Moderation is not the unit under test; stub it so a passed outcome
        # can commit terminally (mirrors the persistence-test pattern).
        monkeypatch.setattr(worker_module, "run_moderation_pipeline", AsyncMock())

        # Sentinel so a misroute is loud: if the worker ever calls skeleton
        # fill for this job, fail with a clear message instead of the opaque
        # ResourceNotFoundError.
        async def _no_skeleton_fill(*_args: object, **_kwargs: object) -> object:
            pytest.fail("fresh_generation job was misrouted to _run_skeleton_fill")

        monkeypatch.setattr(worker_module, "_run_skeleton_fill", _no_skeleton_fill)

        job_id = uuid_mod.uuid4()
        concept_id = uuid_mod.uuid4()

        job = GenerationJob(
            id=job_id,
            concept_id=concept_id,
            status="queued",
            authoring_metadata={"provider": "anthropic", "model": "claude-opus-4-8"},
        )
        concept = Concept(
            id=concept_id, family_id=uuid_mod.uuid4(), brief=_FRESHGEN_BRIEF
        )
        concept.created_by = uuid_mod.uuid4()
        session_ctx = _FreshGenSession(job, concept)

        def factory() -> object:
            class _Ctx:
                async def __aenter__(self) -> _FreshGenSession:
                    return session_ctx

                async def __aexit__(self, *exc: object) -> None:
                    return None

            return _Ctx()

        # Inject a mock provider so generate_story never makes a live call; the
        # canned story drives the pipeline to a clean terminal status.
        await worker_module.run_generation_job(
            job_id,
            provider=MockProvider(responses=[_CANNED_STORY_JSON] * 8),
            session_factory=factory,
        )

        # Reached a real terminal status via generate_story, NOT the
        # skeleton_slug ResourceNotFoundError (the misroute would have tripped
        # the _no_skeleton_fill sentinel above and failed the test first).
        assert job.status in {"passed", "needs_review", "failed"}


def test_run_generation_job_sync_parses_uuid_and_delegates_to_async_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify run_generation_job_sync parses the job id and awaits the worker.

    run_generation_job_sync is RQ's sync entrypoint: it must parse the
    incoming job id string into a real uuid.UUID (not pass the raw string
    through) before handing off to the async worker via asyncio.run. Only
    the inner coroutine is mocked here; the real asyncio.run executes the
    event loop, exercising the actual synchronous wrapper body, which
    otherwise has zero coverage (every other worker test drives
    run_generation_job directly as a coroutine, never through this sync
    wrapper).
    """
    import uuid as uuid_mod

    mock_async_worker = AsyncMock()
    monkeypatch.setattr(worker_module, "run_generation_job", mock_async_worker)

    job_id = uuid_mod.uuid4()

    worker_module.run_generation_job_sync(str(job_id))

    mock_async_worker.assert_awaited_once_with(job_id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_generation_job_default_session_factory_is_get_worker_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_generation_job's default session_factory must be get_worker_session (ADR-021).

    A regression back to the API engine's get_session would silently ignore
    a post-cutover WORKER_DATABASE_URL for every background job. Proven
    decisively via two checks: (1) worker_module no longer even imports
    get_session as a module attribute (asserted directly, so a reintroduced
    `from ...database import get_session` import is caught even if nothing
    calls it), and (2) get_worker_session is monkeypatched to a fake whose
    __aenter__ raises a distinguishable sentinel, proving the DEFAULT
    session_factory argument actually resolves to it.
    """
    import uuid as uuid_mod
    from contextlib import asynccontextmanager

    assert not hasattr(worker_module, "get_session"), (
        "worker_module must not import get_session (ADR-021: RQ worker jobs "
        "must use get_worker_session so WORKER_DATABASE_URL takes effect)"
    )

    class _SentinelFromWorkerSessionError(Exception):
        """Raised only if the default factory (get_worker_session) was used."""

    @asynccontextmanager
    async def _fake_get_worker_session():
        raise _SentinelFromWorkerSessionError
        yield  # pragma: no cover - unreachable, satisfies the generator shape

    monkeypatch.setattr(worker_module, "get_worker_session", _fake_get_worker_session)

    job_id = uuid_mod.uuid4()
    with pytest.raises(_SentinelFromWorkerSessionError):
        await worker_module.run_generation_job(job_id)


@pytest.mark.asyncio
async def test_load_and_start_job_claims_queued_row() -> None:
    """A 'queued' row is claimed: transitioned to 'running' and returned."""
    import uuid as uuid_mod

    from cyo_adventure.db.models import GenerationJob

    job_id = uuid_mod.uuid4()
    job = SimpleNamespace(id=job_id, status="queued", concept_id=uuid_mod.uuid4())

    class _ClaimSession:
        def __init__(self) -> None:
            self.added: list[object] = []

        async def get(self, model: type, ident: object) -> object | None:
            return job if model is GenerationJob and ident == job_id else None

        def add(self, obj: object) -> None:
            self.added.append(obj)

        async def flush(self) -> None:
            pass

    result = await worker_module._load_and_start_job(
        cast("Any", _ClaimSession()), job_id
    )
    assert result is job
    assert job.status == "running"


@pytest.mark.asyncio
async def test_load_and_start_job_skips_already_running_row() -> None:
    """A row already past 'queued' is not re-claimed (compare-and-set).

    A duplicate RQ delivery or a reclaim re-enqueue must not let a second run
    execute a job another delivery already owns; the loader returns None so the
    caller skips without touching the row.
    """
    import uuid as uuid_mod

    from cyo_adventure.db.models import GenerationJob

    job_id = uuid_mod.uuid4()
    job = SimpleNamespace(id=job_id, status="running", concept_id=uuid_mod.uuid4())

    class _RunningSession:
        async def get(self, model: type, ident: object) -> object | None:
            return job if model is GenerationJob and ident == job_id else None

    result = await worker_module._load_and_start_job(
        cast("Any", _RunningSession()), job_id
    )
    assert result is None
    assert job.status == "running"


@pytest.mark.asyncio
async def test_load_and_start_job_skips_terminal_row() -> None:
    """A row already in a terminal status ('passed') is likewise not re-claimed."""
    import uuid as uuid_mod

    from cyo_adventure.db.models import GenerationJob

    job_id = uuid_mod.uuid4()
    job = SimpleNamespace(id=job_id, status="passed", concept_id=uuid_mod.uuid4())

    class _TerminalSession:
        async def get(self, model: type, ident: object) -> object | None:
            return job if model is GenerationJob and ident == job_id else None

    result = await worker_module._load_and_start_job(
        cast("Any", _TerminalSession()), job_id
    )
    assert result is None
    assert job.status == "passed"


# ---------------------------------------------------------------------------
# WS-2: theme-contract dispatch in _run_skeleton_fill (worker.py section 5.1)
# ---------------------------------------------------------------------------
#
# These tests exercise the REAL generation.binding functions
# (load_contract_for, bind_theme_to_contract, render_bound_skeleton) against
# tiny on-disk fixtures under tmp_path -- never the real skeletons/ catalog --
# and only stub out fill_skeleton (the expensive LLM fill step) to observe
# what the dispatch hands it. worker_module.resolve_skeleton_path is
# monkeypatched to point at the tmp_path fixture directory so no test ever
# touches skeletons/ on disk.


def _dispatch_brief() -> ConceptBrief:
    # WS-7 D5: the refined/degraded interpretation reads brief.content_nogo (the
    # guardian banned-theme strings) as the derivation's content_nogo input, so
    # the dispatch fake carries an (empty) list for it alongside age_band.
    return cast(
        "ConceptBrief",
        SimpleNamespace(age_band=SimpleNamespace(value="8-11"), content_nogo=[]),
    )


def _dispatch_pii() -> PiiContext:
    return PiiContext(child_names=frozenset())


async def _fail_if_fill_called(*_args: object, **_kwargs: object) -> GenerationOutcome:
    """A ``fill_skeleton`` stub for tests that must never reach the fill step."""
    pytest.fail("fill_skeleton must not be called on a fail-closed dispatch path")


def _bound_dispatch_skeleton() -> dict[str, object]:
    """A tiny, gate-passing, parameterized fixture skeleton (mirrors
    tests/unit/test_binding_render.py's ``_tiny_skeleton``): one decision node
    with two slotted beats tokens and a slotted choice label, plus one slotted
    and one fixed ending title.
    """
    return {
        "schema_version": "2.0",
        "id": "s_test_worker_bind_dispatch",
        "version": 1,
        "title": "Test Story",
        "metadata": {
            "age_band": "3-5",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 1.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": ["adventure"],
            "estimated_minutes": 5,
            "ending_count": 2,
            "topology": "time_cave",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    "<<FILL role=setup words=40 beats='The hero, {HERO}, "
                    "arrives at {A1_GATE} and must choose a path.'>>"
                ),
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_a",
                        "label": "Approach {A1_OFFER}.",
                        "target": "n_end_a",
                    },
                    {
                        "id": "c_b",
                        "label": "Turn back toward home.",
                        "target": "n_end_b",
                    },
                ],
            },
            {
                "id": "n_end_a",
                "body": (
                    "<<FILL role=ending words=30 beats='The hero claims the "
                    "prize and celebrates.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The {PRIZE}",
                },
                "choices": [],
            },
            {
                "id": "n_end_b",
                "body": (
                    "<<FILL role=ending words=30 beats='The hero returns "
                    "home safely.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "neutral",
                    "kind": "completion",
                    "title": "Home Again",
                },
                "choices": [],
            },
        ],
    }


_BOUND_DISPATCH_BINDINGS = {
    "HERO": "Priya",
    "A1_GATE": "the jammed hatch",
    "A1_OFFER": "a glinting tide pool",
    "PRIZE": "Glass Starfish",
}


def _interpret_bind_response(
    bindings: dict[str, str],
    elements: list[dict[str, object]] | None = None,
) -> str:
    """Build a WS-7 interpret-and-bind provider response.

    Since the worker's parameterized path now calls ``interpret_and_bind``
    (D5), a scripted bound-path provider response is the combined shape
    ``{"bindings": {...}, "elements": [...]}`` (design section 5.2), NOT the
    flat slot map ``bind_theme_to_contract`` used to expect. ``elements`` is
    advisory: omitted here it defaults to ``[]``.

    Args:
        bindings: The flat ``{slot_id: value}`` map (load-bearing half).
        elements: Optional advisory element decomposition; ``None`` -> ``[]``.

    Returns:
        The JSON-encoded combined response.
    """
    payload: dict[str, object] = {"bindings": bindings}
    if elements is not None:
        payload["elements"] = elements
    return json.dumps(payload)


def _bound_dispatch_contract() -> ThemeContract:
    def _slot(slot_id: str, *, scope: SlotScope = SlotScope.GLOBAL) -> SlotSpec:
        return SlotSpec(
            id=slot_id,
            scope=scope,
            meaning=f"placeholder meaning for {slot_id}",
            constraints=SlotConstraints(),
        )

    return ThemeContract(
        contract_version=1,
        skeleton_slug="s_test_worker_bind_dispatch",
        age_band=AgeBand.BAND_3_5,
        legacy_lexicon=[],
        default_binding=dict(_BOUND_DISPATCH_BINDINGS),
        slots=[
            _slot("HERO"),
            _slot("A1_GATE", scope=SlotScope.TRACK),
            _slot("A1_OFFER", scope=SlotScope.TRACK),
            _slot("PRIZE", scope=SlotScope.ENDING),
        ],
    )


@pytest.mark.asyncio
async def test_run_skeleton_fill_no_sidecar_dispatches_legacy_call_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No sidecar file: fill_skeleton is called exactly as it was pre-WS-2.

    Regression pin for coexistence (design section 5.1): the real
    ``load_contract_for`` runs against a tmp_path skeleton with no ``{SLOT}``
    tokens and no ``<slug>.contract.json`` sidecar, returns ``None``, and the
    dispatch falls through to the byte-identical legacy ``fill_skeleton`` call
    -- in particular, NO ``slot_bindings`` kwarg is passed at all (not even
    ``None``), matching every one of the 59 unmigrated catalog skeletons today.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "legacy-slug.json"
    # Deliberately no "legacy-slug.contract.json" sidecar written.

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    fake_skeleton: dict[str, object] = {"id": "s_x", "nodes": []}
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: fake_skeleton)

    captured: dict[str, object] = {}

    async def _fake_fill_skeleton(
        skeleton: dict[str, object],
        theme_brief: dict[str, object],
        provider: object,
        pii: object,
        **kwargs: object,
    ) -> GenerationOutcome:
        captured["skeleton"] = skeleton
        captured["theme_brief"] = theme_brief
        captured["provider"] = provider
        captured["pii"] = pii
        captured["kwargs"] = kwargs
        return GenerationOutcome(
            status="passed",
            storybook={"id": "s_x"},
            report={},
            attempts=0,
            stage_log=[],
        )

    monkeypatch.setattr(worker_module, "fill_skeleton", _fake_fill_skeleton)

    provider = cast("GenerationProvider", object())
    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "legacy-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    assert outcome.status == "passed"
    assert captured["skeleton"] is fake_skeleton
    assert "slot_bindings" not in cast("dict[str, object]", captured["kwargs"])
    assert "theme_contract" not in outcome.report


@pytest.mark.asyncio
async def test_run_skeleton_fill_half_migrated_fails_closed_no_fill_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A skeleton with {SLOT} tokens but no sidecar fails closed (design 5.1).

    A raw token reaching a child-facing fill is a content defect the
    post-generation gate cannot see, so ``load_contract_for`` itself raises;
    the dispatch must let that propagate rather than silently filling raw
    placeholders, and must never reach the fill step.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "half-migrated.json"
    # No "half-migrated.contract.json" sidecar written: half-migrated state.

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    fake_skeleton: dict[str, object] = {
        "nodes": [
            {
                "id": "n_start",
                "body": "<<FILL role=setup words=10 beats='The hero {HERO} arrives.'>>",
                "is_ending": False,
                "choices": [],
            }
        ]
    }
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: fake_skeleton)
    monkeypatch.setattr(worker_module, "fill_skeleton", _fail_if_fill_called)

    fill_context = _SkeletonFillContext(
        authoring={"skeleton_slug": "half-migrated", "theme_brief": {}},
        brief=_dispatch_brief(),
        effective_provider=cast("GenerationProvider", object()),
        pii=_dispatch_pii(),
    )
    with pytest.raises(ValidationError):
        await _run_skeleton_fill(fill_context)


@pytest.mark.asyncio
async def test_run_skeleton_fill_sidecar_present_binds_renders_then_fills(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sidecar present: bind -> render -> fill, with the BOUND skeleton and
    ``slot_bindings`` threaded into fill_skeleton, plus the audit block.

    Exercises the REAL ``load_contract_for``, ``bind_theme_to_contract``, and
    ``render_bound_skeleton``; only ``fill_skeleton`` (the LLM fill step) is
    stubbed, so this pins the exact order and payload WS-2 design section 4/7
    promises without paying for a real fill.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_bytes = _bound_dispatch_contract().model_dump_json().encode("utf-8")
    contract_path.write_bytes(contract_bytes)

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _bound_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)

    # A single valid interpret-and-bind response so the ONE real provider call
    # returns the exact bindings this test asserts on (elements advisory).
    provider = MockProvider(
        responses=[_interpret_bind_response(_BOUND_DISPATCH_BINDINGS)]
    )

    captured: dict[str, object] = {}

    async def _fake_fill_skeleton(
        skeleton: dict[str, object],
        theme_brief: dict[str, object],
        provider_arg: object,
        pii: object,
        **kwargs: object,
    ) -> GenerationOutcome:
        captured["skeleton"] = skeleton
        captured["kwargs"] = kwargs
        return GenerationOutcome(
            status="passed",
            storybook={"id": "s_x"},
            report={},
            attempts=0,
            stage_log=[],
        )

    monkeypatch.setattr(worker_module, "fill_skeleton", _fake_fill_skeleton)

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "themed-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    # Exactly one provider call: the bind step. fill_skeleton is stubbed, so
    # no fill/repair provider call happens in this test.
    assert len(provider.calls) == 1

    expected_bound = worker_module.render_bound_skeleton(
        original_skeleton, _BOUND_DISPATCH_BINDINGS
    )
    assert captured["skeleton"] == expected_bound
    assert captured["skeleton"] != original_skeleton
    kwargs = cast("dict[str, object]", captured["kwargs"])
    assert kwargs["slot_bindings"] == _BOUND_DISPATCH_BINDINGS

    audit = cast("dict[str, object]", outcome.report["theme_contract"])
    assert audit["skeleton_slug"] == "s_test_worker_bind_dispatch"
    assert audit["contract_version"] == 1
    assert audit["denylist_version"] == DENYLIST_VERSION
    assert audit["slot_bindings"] == _BOUND_DISPATCH_BINDINGS
    assert audit["contract_sha256"] == hashlib.sha256(contract_bytes).hexdigest()
    # bind_theme_to_contract does not report how many attempts it used, so a
    # hardcoded count is never fabricated here (see the inline worker.py
    # comment next to this block).
    assert "bind_attempts" not in audit


# ---------------------------------------------------------------------------
# Task 4a (ADR-023 plan 3.2): LIVE, fail-closed sentinel-integrity check in
# _run_skeleton_fill. `_personalizable_dispatch_contract`/`_skeleton` extend
# the WS-2 dispatch fixtures above with one `kind="personalizable"` PROTAGONIST
# slot, so `render_bound_skeleton` renders a real sentinel into `bound` and the
# check is exercised live rather than dormantly.
# ---------------------------------------------------------------------------


def _personalizable_dispatch_contract() -> ThemeContract:
    """`_bound_dispatch_contract` plus one ``kind="personalizable"`` slot.

    PROTAGONIST's value is pinned via ``default_binding`` ("Ada") and is
    never proposed by the mocked bind response (see
    ``_request_contract``/``_merge_personalizable_defaults``), matching
    real bind behavior for a personalizable slot.
    """
    base = _bound_dispatch_contract()
    return ThemeContract(
        contract_version=base.contract_version,
        skeleton_slug=base.skeleton_slug,
        age_band=base.age_band,
        legacy_lexicon=base.legacy_lexicon,
        default_binding={**base.default_binding, "PROTAGONIST": "Ada"},
        slots=[
            *base.slots,
            SlotSpec(
                id="PROTAGONIST",
                scope=SlotScope.GLOBAL,
                meaning="the reader's own child, personalized",
                guidance="",
                kind="personalizable",
                personalization_field="protagonist_first_name",
                role_safety="protagonist",
            ),
        ],
    )


def _personalizable_dispatch_skeleton() -> dict[str, object]:
    """`_bound_dispatch_skeleton` with a ``{PROTAGONIST}`` token added to n_start."""
    skeleton = _bound_dispatch_skeleton()
    nodes = cast("list[dict[str, object]]", skeleton["nodes"])
    start_node = nodes[0]
    assert start_node["id"] == "n_start"
    start_node["body"] = (
        "<<FILL role=setup words=40 beats='The hero, {HERO}, joined by "
        "{PROTAGONIST}, arrives at {A1_GATE} and must choose a path.'>>"
    )
    return skeleton


def _personalizable_filled_storybook(protagonist_surface: str) -> dict[str, object]:
    """A filled storybook whose n_start body embeds ``protagonist_surface``.

    Args:
        protagonist_surface: The exact text standing in for PROTAGONIST's
            rendered value in the finished prose: a verbatim sentinel copy
            (pass case), a mutated sentinel (fail case), or a bare word with
            no sentinel at all (dropped case).

    Returns:
        A raw filled-blob mapping shaped like a real fill_skeleton result:
        three nodes matching `_personalizable_dispatch_skeleton`'s ids.
    """
    return {
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    f"Priya stood before the jammed hatch, joined by "
                    f"{protagonist_surface}, and had to choose."
                ),
                "choices": [
                    {
                        "id": "c_a",
                        "label": "Approach a glinting tide pool.",
                        "target": "n_end_a",
                    },
                    {
                        "id": "c_b",
                        "label": "Turn back toward home.",
                        "target": "n_end_b",
                    },
                ],
            },
            {
                "id": "n_end_a",
                "body": "Priya claimed the prize and celebrated.",
                "ending": {"id": "e_a", "title": "Glass Starfish"},
                "choices": [],
            },
            {
                "id": "n_end_b",
                "body": "Priya returned home safely.",
                "ending": {"id": "e_b", "title": "Home Again"},
                "choices": [],
            },
        ]
    }


def _stub_returning(storybook: dict[str, object]) -> Callable[..., object]:
    """Build a `fill_skeleton` stub coroutine function that always returns `storybook`."""

    async def _fake_fill_skeleton(
        *_args: object, **_kwargs: object
    ) -> GenerationOutcome:
        return GenerationOutcome(
            status="passed",
            storybook=storybook,
            report={},
            attempts=0,
            stage_log=[],
        )

    return _fake_fill_skeleton


@pytest.mark.asyncio
async def test_run_skeleton_fill_sentinel_integrity_dormant_for_non_personalizable_fill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Dormancy proof (Task 4a brief): a non-personalizable fill is unaffected.

    No contract on disk declares a personalizable slot yet, so
    ``personalizable_slot_ids(contract)`` is empty here (mirroring every real
    skeleton today): `bound`'s beats/ending-title text carries plain
    substituted values, never a sentinel, so the expected sentinel set is
    empty and a sentinel-free filled blob passes the LIVE check with zero
    violations, exactly as it would have with no check at all.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(
        _bound_dispatch_contract().model_dump_json().encode("utf-8")
    )

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _bound_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)

    provider = MockProvider(
        responses=[_interpret_bind_response(_BOUND_DISPATCH_BINDINGS)]
    )
    filled_storybook = _personalizable_filled_storybook("Priya's companion")
    monkeypatch.setattr(
        worker_module, "fill_skeleton", _stub_returning(filled_storybook)
    )

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "themed-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    assert outcome.status == "passed"
    assert outcome.storybook == filled_storybook
    # D4 regression: eligibility stays False for every contract with no
    # personalizable slots (today's whole catalog minus the D4 pilot),
    # exactly as it would with no stamping logic at all.
    assert outcome.personalization_eligible is False


@pytest.mark.asyncio
async def test_run_skeleton_fill_sentinel_integrity_passes_verbatim_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A personalizable fill that copies its sentinel verbatim passes (3.2).

    PROTAGONIST is a ``kind="personalizable"`` slot, so `bound`'s beats
    guidance carries ``wrap("PROTAGONIST", "Ada")``; a conforming fill copies
    that exact sentinel into the finished prose and the LIVE check lets it
    through with zero violations.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract = _personalizable_dispatch_contract()
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(contract.model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _personalizable_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)

    provider = MockProvider(
        responses=[_interpret_bind_response(_BOUND_DISPATCH_BINDINGS)]
    )
    filled_storybook = _personalizable_filled_storybook(wrap("PROTAGONIST", "Ada"))
    monkeypatch.setattr(
        worker_module, "fill_skeleton", _stub_returning(filled_storybook)
    )

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "themed-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    assert outcome.status == "passed"
    assert outcome.storybook == filled_storybook


@pytest.mark.asyncio
async def test_run_skeleton_fill_sentinel_integrity_forged_value_not_reinserted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A model-forged sentinel is stripped and never reinserted; the job still passes (ADR-023 Stage R).

    Under "derive, not prescribe" (Task R3), the fill LLM is never trusted to
    preserve a sentinel wrapper. A forged/mutated sentinel
    (``{~PROTAGONIST:Champion~}``, the wrong inner value) is stripped down to
    its bare inner word by `reinsert_storybook`'s normalization pass, then
    the node is re-scanned for the EXPECTED value ("Ada", from the bound
    skeleton's ``default_binding``). Since "Ada" never appears in the
    stripped prose, the token is classified ``"not_found"`` and nothing is
    re-wrapped there. The result is plain text with no sentinel of any kind,
    which both `verify_manifest` and `check_sentinel_integrity_at_rest`
    accept: the old design's fail-closed ValidationError on a mutated
    sentinel no longer applies, because a forged wrapper never survives to be
    checked at all.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract = _personalizable_dispatch_contract()
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(contract.model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _personalizable_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)

    provider = MockProvider(
        responses=[_interpret_bind_response(_BOUND_DISPATCH_BINDINGS)]
    )
    mutated_sentinel = wrap("PROTAGONIST", "Champion")
    filled_storybook = _personalizable_filled_storybook(mutated_sentinel)
    monkeypatch.setattr(
        worker_module, "fill_skeleton", _stub_returning(filled_storybook)
    )

    fill_context = _SkeletonFillContext(
        authoring={
            "skeleton_slug": "themed-slug",
            "theme_brief": {"premise": "a fox"},
        },
        brief=_dispatch_brief(),
        effective_provider=provider,
        pii=_dispatch_pii(),
    )
    outcome = await _run_skeleton_fill(fill_context)

    # Not "passed": `_run_skeleton_fill` now re-runs the deterministic gate
    # against the POST-transform document, because the transform rewrote it
    # and the pre-transform verdict no longer describes what gets persisted.
    # This fixture's storybook is a hand-built stub that the real gate blocks
    # (verified directly: run_gate(...).blocked is True on it BEFORE any
    # transform runs), so the old "passed" assertion was recording what
    # `_stub_returning` fabricated, not a gate result. The sentinel behavior
    # this test actually exists to pin is unchanged and asserted below.
    assert outcome.status == "needs_review"
    assert outcome.storybook is not None
    nodes = cast("list[dict[str, object]]", outcome.storybook["nodes"])
    start_body = cast("str", nodes[0]["body"])
    assert "Champion" in start_body
    assert wrap("PROTAGONIST", "Champion") not in start_body
    assert wrap("PROTAGONIST", "Ada") not in start_body


# ---------------------------------------------------------------------------
# ADR-023 Task D4: personalization_eligible stamping. `_run_skeleton_fill` is
# the fill path's only producer of the flag (worker.py's inline #CRITICAL
# marker); these pin the two-legged rule: bool(personalizable_slots) and
# manifest_carries_tokens(sentinel_manifest). The second leg asks whether the
# manifest TALLIES anything, not whether it exists: `build_manifest` returns
# `{"tokens": {}}` rather than `None` for a document carrying no sentinel, so
# a presence test would stamp True for the zero-coverage case.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fill_stamps_personalization_eligible_when_contract_declares_slots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A declared personalizable slot plus a real manifest stamps True (D4).

    Reuses the exact fixture
    ``test_run_skeleton_fill_sentinel_integrity_passes_verbatim_copy`` sets
    up: PROTAGONIST is declared personalizable and the fill copies its
    sentinel verbatim, so `reinsert_storybook` derives a real manifest.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract = _personalizable_dispatch_contract()
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(contract.model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _personalizable_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)

    provider = MockProvider(
        responses=[_interpret_bind_response(_BOUND_DISPATCH_BINDINGS)]
    )
    filled_storybook = _personalizable_filled_storybook(wrap("PROTAGONIST", "Ada"))
    monkeypatch.setattr(
        worker_module, "fill_skeleton", _stub_returning(filled_storybook)
    )

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "themed-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    assert outcome.sentinel_manifest is not None
    assert outcome.personalization_eligible is True


@pytest.mark.asyncio
async def test_fill_leaves_personalization_eligible_false_for_empty_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A transform that ran but tallied nothing stays False (D4).

    The zero-coverage case: the bound contract declares PROTAGONIST
    personalizable, but the fill forged the sentinel, so
    `reinsert_storybook` strips it and finds no expected value to re-wrap
    (the exact fixture
    ``test_run_skeleton_fill_sentinel_integrity_forged_value_not_reinserted``
    pins). The transform still returns a manifest, because `build_manifest`
    is called unconditionally and returns ``{"tokens": {}}`` rather than
    ``None``. Testing that manifest for presence alone would stamp True for a
    document with no sentinel left in it, so the second leg asks what the
    manifest tallies instead.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract = _personalizable_dispatch_contract()
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(contract.model_dump_json().encode("utf-8"))

    original_skeleton = _personalizable_dispatch_skeleton()

    # Typed nested functions rather than this module's older
    # `lambda _band, _slug: ...` idiom: `tests/CLAUDE.md` requires annotations
    # on helpers, and an unannotated lambda draws `reportUnknownLambdaType`
    # under BasedPyright strict.
    def _resolve_skeleton_path(_band: str, _slug: str) -> Path:
        return skeleton_path

    def _load_skeleton(_path: Path) -> dict[str, object]:
        return original_skeleton

    monkeypatch.setattr(worker_module, "resolve_skeleton_path", _resolve_skeleton_path)
    monkeypatch.setattr(worker_module, "load_skeleton", _load_skeleton)

    provider = MockProvider(
        responses=[_interpret_bind_response(_BOUND_DISPATCH_BINDINGS)]
    )
    filled_storybook = _personalizable_filled_storybook(wrap("PROTAGONIST", "Champion"))
    monkeypatch.setattr(
        worker_module, "fill_skeleton", _stub_returning(filled_storybook)
    )

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "themed-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    # Present, and empty: exactly the state a `is not None` test would have
    # read as evidence the transform found something.
    assert outcome.sentinel_manifest == {"tokens": {}}
    assert outcome.personalization_eligible is False


@pytest.mark.asyncio
async def test_fill_leaves_personalization_eligible_false_without_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Declared slots but no manifest (transform skipped) stays False (D4).

    The fill produces no document at all (``storybook=None``, a "failed"
    outcome), so the reinsertion transform never runs and no manifest is
    ever derived, even though the bound contract declares PROTAGONIST
    personalizable. `StorybookVersion.personalization_eligible`'s own
    contract is "does this version's BLOB carry any sentinel-bound slots";
    with no blob there is no evidence, so this fails closed.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract = _personalizable_dispatch_contract()
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(contract.model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _personalizable_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)

    provider = MockProvider(
        responses=[_interpret_bind_response(_BOUND_DISPATCH_BINDINGS)]
    )

    async def _fake_fill_skeleton_no_doc(
        *_args: object, **_kwargs: object
    ) -> GenerationOutcome:
        return GenerationOutcome(
            status="failed", storybook=None, report={}, attempts=0, stage_log=[]
        )

    monkeypatch.setattr(worker_module, "fill_skeleton", _fake_fill_skeleton_no_doc)

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "themed-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    assert outcome.storybook is None
    assert outcome.sentinel_manifest is None
    assert outcome.personalization_eligible is False


def test_regate_after_transform_skips_when_document_unchanged() -> None:
    """A byte-identical transform returns the original verdict untouched.

    This is the path 46 of the 47 theme contracts on disk take (measured
    2026-08-23): they declare no personalizable slot, so `reinsert_storybook`
    is a no-op and re-running the full validator would only burn budget
    reproducing a verdict already held. It is not a dormant path;
    `skeletons/10-13/the-midnight-museum.contract.json` declares one and
    reaches the regate instead.
    """
    doc: dict[str, object] = {"title": "T", "nodes": []}
    outcome = GenerationOutcome(
        status="passed",
        storybook=doc,
        report={"marker": "pre-transform"},
        attempts=0,
        stage_log=[],
    )

    status, report, clean_downgrade = worker_module._regate_after_transform(
        outcome, dict(doc), skeleton_slug="themed-slug"
    )

    assert status == "passed"
    assert clean_downgrade is False
    assert report == {"marker": "pre-transform"}
    assert "pre_reinsertion_gate" not in report


def test_regate_after_transform_never_upgrades_a_blocked_outcome() -> None:
    """A pre-transform failure survives a post-transform document that gates clean.

    The transform is a text normalization, not a repair. "The rewrite happened
    to satisfy the gate" is not evidence the original problem was fixed, so
    reconciliation only ever moves toward the more severe status.
    """
    outcome = GenerationOutcome(
        status="needs_review",
        storybook={"title": "before", "nodes": []},
        report={"marker": "pre-transform"},
        attempts=0,
        stage_log=[],
    )

    status, report, _clean_downgrade = worker_module._regate_after_transform(
        outcome, {"title": "after", "nodes": []}, skeleton_slug="themed-slug"
    )

    assert status == "needs_review"
    # The post-transform report describes the document that will be persisted,
    # and the superseded verdict rides alongside it so a reviewer can tell
    # which of the two gate runs produced the downgrade.
    assert report["pre_reinsertion_gate"] == {
        "status": "needs_review",
        "report": {"marker": "pre-transform"},
    }


@pytest.mark.asyncio
async def test_run_skeleton_fill_sentinel_manifest_round_trips_with_final_storybook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`GenerationOutcome.sentinel_manifest` is populated and verifies against the returned storybook.

    ADR-023 Stage R carries the reinsertion transform's derived manifest
    forward in memory (Task B2's persisted DB column is a later phase); this
    pins that `_run_skeleton_fill` actually populates it, and that it
    round-trips against `outcome.storybook` via `verify_manifest` the same
    way a later at-rest re-check would.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract = _personalizable_dispatch_contract()
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(contract.model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _personalizable_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)

    provider = MockProvider(
        responses=[_interpret_bind_response(_BOUND_DISPATCH_BINDINGS)]
    )
    filled_storybook = _personalizable_filled_storybook(wrap("PROTAGONIST", "Ada"))
    monkeypatch.setattr(
        worker_module, "fill_skeleton", _stub_returning(filled_storybook)
    )

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "themed-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    assert outcome.sentinel_manifest is not None
    assert outcome.storybook is not None
    tokens = cast("dict[str, object]", outcome.sentinel_manifest["tokens"])
    assert "n_start" in tokens
    assert verify_manifest(outcome.storybook, outcome.sentinel_manifest)


class _WarningCapturingLogger:
    """Wraps `worker_module.logger`, recording every `.warning(...)` call.

    Every other attribute (`.error`, `.info`, ...) delegates to the real
    logger unchanged, so this double only needs to know about the one method
    the test actually asserts on.
    """

    def __init__(self, wrapped: object) -> None:
        self._wrapped = wrapped
        self.warning_calls: list[tuple[str, dict[str, object]]] = []

    def warning(self, event: str, **kwargs: object) -> None:
        self.warning_calls.append((event, kwargs))

    def __getattr__(self, name: str) -> object:
        return getattr(self._wrapped, name)


@pytest.mark.asyncio
async def test_run_skeleton_fill_warns_on_zero_coverage_personalizable_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A declared personalizable slot the fill prose never mentions logs a WARNING, never a failure.

    ADR-023 Stage R's soft coverage floor: a slot the theme contract declared
    personalizable but whose expected value never occurs anywhere in the
    finished prose (the model paraphrased it away entirely) is a content
    smell worth flagging to an operator, not a corruption worth blocking the
    job over. Uses a fill whose PROTAGONIST surface text ("the newcomer")
    genuinely does not contain the expected value ("Ada") anywhere, to drive
    the ``"not_found"`` branch deterministically.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract = _personalizable_dispatch_contract()
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(contract.model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _personalizable_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)

    provider = MockProvider(
        responses=[_interpret_bind_response(_BOUND_DISPATCH_BINDINGS)]
    )
    filled_storybook = _personalizable_filled_storybook("the newcomer")
    monkeypatch.setattr(
        worker_module, "fill_skeleton", _stub_returning(filled_storybook)
    )

    capturing_logger = _WarningCapturingLogger(worker_module.logger)
    monkeypatch.setattr(worker_module, "logger", capturing_logger)

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "themed-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    assert outcome.status == "passed"
    matching = [
        kwargs
        for event, kwargs in capturing_logger.warning_calls
        if event == "generation_job.personalizable_slot_zero_coverage"
    ]
    assert len(matching) == 1
    assert matching[0]["slot_ids"] == ["PROTAGONIST"]


@pytest.mark.asyncio
async def test_run_skeleton_fill_bind_failure_fails_closed_no_fill_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A brief the binder cannot fit to the contract fails closed (OQ-1).

    Uses the REAL ``bind_theme_to_contract`` against a MockProvider that
    always returns a denylist-violating value, so the violation detail in the
    raised ``ValidationError`` is genuine, not fabricated by a test double.
    No fill/repair provider call is ever made.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract = _bound_dispatch_contract()
    contract_path.write_bytes(contract.model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _bound_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)
    monkeypatch.setattr(worker_module, "fill_skeleton", _fail_if_fill_called)

    # HERO has no declared `forbid`, but the 3-5 band-mandatory union
    # (validator/slots.py) forbids `weapon` on every slot regardless; "a
    # sword-wielder" trips it on every attempt. The bindings half parses
    # cleanly (so it is a genuine slot-gate violation, not a parse failure),
    # so interpret_and_bind exhausts its retries and raises.
    violating_response = _interpret_bind_response(
        {
            "HERO": "a sword-wielder",
            "A1_GATE": "the jammed hatch",
            "A1_OFFER": "a glinting tide pool",
            "PRIZE": "Glass Starfish",
        }
    )
    provider = MockProvider(responses=[violating_response, violating_response])
    fill_context = _SkeletonFillContext(
        authoring={
            "skeleton_slug": "themed-slug",
            "theme_brief": {"premise": "a fox"},
        },
        brief=_dispatch_brief(),
        effective_provider=provider,
        pii=_dispatch_pii(),
    )

    with pytest.raises(ValidationError) as exc_info:
        await _run_skeleton_fill(fill_context)

    # Exactly the two bind attempts; no additional (fill/repair) call.
    assert len(provider.calls) == 2
    violations = exc_info.value.details["violations"]
    assert any(v["rule"] == "forbid:weapon" for v in violations)


class _ThemeContractBindFailureSession:
    """Session double for a run_generation_job pipeline-exception test.

    Supports the full path up to (and including) the pipeline dispatch
    failing, then the ``_record_failure`` write: job/concept lookup, the
    empty child-name query ``_load_concept_and_pii`` issues, and the
    ``record_event`` + commit calls ``_record_failure`` performs.
    """

    def __init__(self, job: object, concept: object) -> None:
        self.job = job
        self.concept = concept
        self.added: list[object] = []

    async def get(self, model: type, ident: object) -> object | None:
        from cyo_adventure.db.models import Concept, GenerationJob

        if model is GenerationJob and getattr(self.job, "id", None) == ident:
            return self.job
        if model is Concept and getattr(self.concept, "id", None) == ident:
            return self.concept
        return None

    async def execute(self, *_args: object, **_kwargs: object) -> _FreshGenResult:
        return _FreshGenResult()

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


@pytest.mark.asyncio
async def test_run_generation_job_bind_failure_records_violations_on_job_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A fail-closed bind failure surfaces through run_generation_job's own
    pipeline-exception handling: job.status == "failed" and the violation
    detail lands on job.report (job.error alone would truncate it away).

    This pins the worker.py change to `_record_failure` / the pipeline
    `except Exception` block, not just `_run_skeleton_fill` in isolation.
    """
    import uuid as uuid_mod

    from cyo_adventure.db.models import Concept, GenerationJob

    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract = _bound_dispatch_contract()
    contract_path.write_bytes(contract.model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _bound_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)
    monkeypatch.setattr(worker_module, "fill_skeleton", _fail_if_fill_called)

    violating_response = _interpret_bind_response(
        {
            "HERO": "a sword-wielder",
            "A1_GATE": "the jammed hatch",
            "A1_OFFER": "a glinting tide pool",
            "PRIZE": "Glass Starfish",
        }
    )
    provider = MockProvider(responses=[violating_response, violating_response])

    job_id = uuid_mod.uuid4()
    concept_id = uuid_mod.uuid4()
    job = GenerationJob(
        id=job_id,
        concept_id=concept_id,
        status="queued",
        authoring_metadata={
            "skeleton_slug": "themed-slug",
            "theme_brief": {"premise": "a fox"},
        },
    )
    concept = Concept(id=concept_id, family_id=uuid_mod.uuid4(), brief=_FRESHGEN_BRIEF)
    session_ctx = _ThemeContractBindFailureSession(job, concept)

    def factory() -> object:
        class _Ctx:
            async def __aenter__(self) -> _ThemeContractBindFailureSession:
                return session_ctx

            async def __aexit__(self, *exc: object) -> None:
                return None

        return _Ctx()

    with pytest.raises(ValidationError):
        await worker_module.run_generation_job(
            job_id, provider=provider, session_factory=factory
        )

    assert job.status == "failed"
    assert job.report is not None
    violations = cast("list[dict[str, object]]", job.report["slot_binding_violations"])
    assert any(v["rule"] == "forbid:weapon" for v in violations)
    # WS-7 D7: a bound-path bind failure (field="theme_brief") now also attaches
    # an honest CANNOT_CARRY interpretation, as a sibling of the violations, on
    # the failed job report. The whole-theme element is NO_CONFORMING_BINDING (a
    # theme incompatibility), never PERSONAL_DETAILS.
    interp = cast("dict[str, object]", job.report["request_interpretation"])
    assert interp["layer"] == "refined"
    elements = cast("list[dict[str, object]]", interp["elements"])
    assert any(
        e["disposition"] == "cannot_carry" and e["reason"] == "no_conforming_binding"
        for e in elements
    )
    assert not any(e["reason"] == "personal_details" for e in elements)


@pytest.mark.asyncio
async def test_run_generation_job_sentinel_manifest_verification_failure_records_on_job_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(ADR-023 Stage R) A transform-bug `verify_manifest` failure surfaces
    through run_generation_job's own pipeline-exception handling under the
    SAME ``sentinel_integrity_violations`` key the old prescriptive check
    used: an admin debugging a failed job still finds the failure under one
    stable key, even though this check can never itself point at a
    node/kind/token (a manifest-verification failure means the transform's
    OWN output failed its OWN derived manifest, a transform bug, not that any
    particular token was found bad).

    This pins the worker.py change to `_handle_pipeline_failure`, not just
    `_run_skeleton_fill` in isolation. The fixture uses a clean,
    verbatim-copy fill (nothing wrong with the CONTENT) and forces
    `verify_manifest` to report failure, isolating the plumbing this test
    targets from the reinsertion algorithm's own content-classification
    behavior (covered separately by
    test_run_skeleton_fill_sentinel_integrity_forged_value_not_reinserted).
    """
    import uuid as uuid_mod

    from cyo_adventure.db.models import Concept, GenerationJob

    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract = _personalizable_dispatch_contract()
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(contract.model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    original_skeleton = _personalizable_dispatch_skeleton()
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: original_skeleton)

    filled_storybook = _personalizable_filled_storybook(wrap("PROTAGONIST", "Ada"))
    monkeypatch.setattr(
        worker_module, "fill_skeleton", _stub_returning(filled_storybook)
    )
    monkeypatch.setattr(worker_module, "verify_manifest", lambda _doc, _manifest: False)

    provider = MockProvider(
        responses=[_interpret_bind_response(_BOUND_DISPATCH_BINDINGS)]
    )

    job_id = uuid_mod.uuid4()
    concept_id = uuid_mod.uuid4()
    job = GenerationJob(
        id=job_id,
        concept_id=concept_id,
        status="queued",
        authoring_metadata={
            "skeleton_slug": "themed-slug",
            "theme_brief": {"premise": "a fox"},
        },
    )
    concept = Concept(id=concept_id, family_id=uuid_mod.uuid4(), brief=_FRESHGEN_BRIEF)
    session_ctx = _ThemeContractBindFailureSession(job, concept)

    def factory() -> object:
        class _Ctx:
            async def __aenter__(self) -> _ThemeContractBindFailureSession:
                return session_ctx

            async def __aexit__(self, *exc: object) -> None:
                return None

        return _Ctx()

    with pytest.raises(ValidationError):
        await worker_module.run_generation_job(
            job_id, provider=provider, session_factory=factory
        )

    assert job.status == "failed"
    assert job.report is not None
    assert job.report["sentinel_integrity_violations"] == []
    # No cross-contamination: this is a sentinel-integrity failure, not a
    # slot-binding one, so the sibling key must be absent.
    assert "slot_binding_violations" not in job.report


# ---------------------------------------------------------------------------
# WS-7 D5/D6: refined and degraded interpretation on the worker report, and
# the request-row projection (design sections 5.3, 5.4, 5.5).
# ---------------------------------------------------------------------------


async def _passed_fill_stub(
    skeleton: dict[str, object],
    theme_brief: dict[str, object],
    provider_arg: object,
    pii: object,
    **_kwargs: object,
) -> GenerationOutcome:
    """A ``fill_skeleton`` stub returning a clean ``passed`` outcome (empty report)."""
    return GenerationOutcome(
        status="passed",
        storybook={"id": "s_x"},
        report={},
        attempts=0,
        stage_log=[],
    )


def _write_bound_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write the parameterized fixture skeleton + contract and patch resolution."""
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(_bound_dispatch_contract().model_dump_json().encode())
    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    monkeypatch.setattr(
        worker_module, "load_skeleton", lambda _path: _bound_dispatch_skeleton()
    )


@pytest.mark.asyncio
async def test_run_skeleton_fill_persists_refined_interpretation_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A bound fill attaches a refined interpretation SIBLING to theme_contract.

    Pins WS-7 D5: interpret_and_bind's advisory elements flow through
    derive_dispositions/render_interpretation into ``request_interpretation`` on
    the report, carrying the contract slug/version and per-element dispositions,
    while the theme_contract audit block still rides alongside it.
    """
    _write_bound_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(worker_module, "fill_skeleton", _passed_fill_stub)

    provider = MockProvider(
        responses=[
            _interpret_bind_response(
                _BOUND_DISPATCH_BINDINGS,
                elements=[
                    {"phrase": "a brave hero", "slot_id": "HERO"},
                    {"phrase": "a sword fight", "slot_id": None},
                ],
            )
        ]
    )

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "themed-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    # theme_contract and request_interpretation are siblings on one report.
    assert "theme_contract" in outcome.report
    interp = cast("dict[str, object]", outcome.report["request_interpretation"])
    assert interp["layer"] == "refined"
    assert interp["contract_version"] == 1
    assert interp["skeleton_slug"] == "s_test_worker_bind_dispatch"
    assert isinstance(interp["kid_summary"], str)
    assert isinstance(interp["guardian_summary"], str)

    elements = cast("list[dict[str, object]]", interp["elements"])
    assert len(elements) == 2
    hero = elements[0]
    assert hero["slot_id"] == "HERO"
    assert hero["disposition"] == "built_in"
    assert hero["reason"] == "bound_to_slot"
    assert hero["element"] == "a brave hero"
    assert hero["kid_text"]
    assert hero["guardian_text"]
    # "a sword fight" trips the 3-5 band weapon floor: set aside, phrase withheld.
    sword = elements[1]
    assert sword["disposition"] == "set_aside"
    assert sword["reason"] == "band_policy"
    assert sword["element"] is None


@pytest.mark.asyncio
async def test_run_skeleton_fill_refined_layer_classifies_self_name_and_pii(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A self-naming element lands IDENTITY_PROTECTION; a PII element lands
    PERSONAL_DETAILS, both with the phrase withheld (WS-7 D5 rules 1-2).

    The interpret-and-bind PROMPT (the fenced brief) is PII-clean, so the
    provider call succeeds; the classification happens deterministically in
    derive_dispositions over the returned element phrases.
    """
    _write_bound_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(worker_module, "fill_skeleton", _passed_fill_stub)

    provider = MockProvider(
        responses=[
            _interpret_bind_response(
                _BOUND_DISPATCH_BINDINGS,
                elements=[
                    {"phrase": "make me the hero", "slot_id": None},
                    {"phrase": "email me at foo@bar.com", "slot_id": None},
                ],
            )
        ]
    )

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "themed-slug",
                "theme_brief": {"premise": "a fox"},
            },
            brief=_dispatch_brief(),
            effective_provider=provider,
            pii=_dispatch_pii(),
        )
    )

    interp = cast("dict[str, object]", outcome.report["request_interpretation"])
    elements = cast("list[dict[str, object]]", interp["elements"])
    reasons = {cast("str", e["reason"]): e for e in elements}
    assert "identity_protection" in reasons
    assert reasons["identity_protection"]["element"] is None
    assert "personal_details" in reasons
    assert reasons["personal_details"]["element"] is None


@pytest.mark.asyncio
async def test_run_skeleton_fill_no_contract_persists_degraded_interpretation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A contract-less skeleton attaches a DEGRADED refined layer, and the
    legacy fill call stays byte-identical (WS-7 D5 section 5.4).

    contract_version is None; no NOT_THIS_STORY_KIND element survives; the
    band-expectation element is present. The fill_skeleton call receives no
    ``slot_bindings`` kwarg and the loaded (unfilled) skeleton, exactly as the
    pre-WS-7 legacy path did, and no theme_contract audit block appears.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "legacy-slug.json"  # no .contract.json sidecar
    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    fake_skeleton: dict[str, object] = {"id": "s_x", "nodes": []}
    monkeypatch.setattr(worker_module, "load_skeleton", lambda _path: fake_skeleton)

    captured: dict[str, object] = {}

    async def _fake_fill(
        skeleton: dict[str, object],
        theme_brief: dict[str, object],
        provider_arg: object,
        pii: object,
        **kwargs: object,
    ) -> GenerationOutcome:
        captured["skeleton"] = skeleton
        captured["theme_brief"] = theme_brief
        captured["kwargs"] = kwargs
        return GenerationOutcome(
            status="passed",
            storybook={"id": "s_x"},
            report={},
            attempts=0,
            stage_log=[],
        )

    monkeypatch.setattr(worker_module, "fill_skeleton", _fake_fill)

    outcome = await _run_skeleton_fill(
        _SkeletonFillContext(
            authoring={
                "skeleton_slug": "legacy-slug",
                "theme_brief": {"premise": "a dragon and a castle"},
            },
            brief=_dispatch_brief(),
            effective_provider=cast("GenerationProvider", object()),
            pii=_dispatch_pii(),
        )
    )

    # Legacy fill call byte-identical: same skeleton, same brief, no bindings.
    assert captured["skeleton"] is fake_skeleton
    assert captured["theme_brief"] == {"premise": "a dragon and a castle"}
    assert "slot_bindings" not in cast("dict[str, object]", captured["kwargs"])
    assert "theme_contract" not in outcome.report

    interp = cast("dict[str, object]", outcome.report["request_interpretation"])
    assert interp["layer"] == "refined"
    assert interp["contract_version"] is None
    assert interp["skeleton_slug"] == "legacy-slug"
    elements = cast("list[dict[str, object]]", interp["elements"])
    assert all(e["reason"] != "not_this_story_kind" for e in elements)
    assert any(
        e["disposition"] == "built_in" and e["reason"] == "story_fit" for e in elements
    )


class _UpdateResult:
    """A ``session.execute`` result whose scalar_one_or_none is preset."""

    def __init__(self, row: object) -> None:
        self._row = row

    def scalar_one_or_none(self) -> object:
        return self._row


class _UpdateSession:
    """A minimal session double recording execute() calls for the D6 helper."""

    def __init__(self, row: object) -> None:
        self._row = row
        self.executed: list[object] = []

    async def execute(self, statement: object) -> _UpdateResult:
        self.executed.append(statement)
        return _UpdateResult(self._row)


def _interp_outcome(report: dict[str, object]) -> GenerationOutcome:
    return GenerationOutcome(
        status="passed", storybook=None, report=report, attempts=0, stage_log=[]
    )


@pytest.mark.asyncio
async def test_update_request_interpretation_sets_row_when_found() -> None:
    """The refined block is projected onto the resolved request row (WS-7 D6)."""
    import uuid

    block = {"layer": "refined", "elements": []}
    request_row = SimpleNamespace(interpretation=None)
    session = _UpdateSession(request_row)
    job = cast("GenerationJob", SimpleNamespace(concept_id=uuid.uuid4()))

    await worker_module._update_request_interpretation(  # pyright: ignore[reportPrivateUsage]
        cast("AsyncSession", session),
        job,
        _interp_outcome({"request_interpretation": block}),
    )

    assert request_row.interpretation == block
    assert len(session.executed) == 1


@pytest.mark.asyncio
async def test_update_request_interpretation_no_request_row_is_noop() -> None:
    """A concept with no originating request row is a silent no-op (WS-7 D6)."""
    import uuid

    session = _UpdateSession(None)  # scalar_one_or_none -> None
    job = cast("GenerationJob", SimpleNamespace(concept_id=uuid.uuid4()))

    # Must not raise even though no row resolves.
    await worker_module._update_request_interpretation(  # pyright: ignore[reportPrivateUsage]
        cast("AsyncSession", session),
        job,
        _interp_outcome({"request_interpretation": {"layer": "refined"}}),
    )
    assert len(session.executed) == 1


@pytest.mark.asyncio
async def test_update_request_interpretation_no_block_skips_query() -> None:
    """No request_interpretation on the report means no DB query at all (D6).

    A fresh (non-skeleton) generation carries no interpretation block; the
    helper returns before issuing any UPDATE. The session's execute() raises so
    any query would fail the test loudly.
    """
    import uuid

    class _RaisingSession:
        async def execute(self, _statement: object) -> object:
            pytest.fail("execute must not run when there is no interpretation block")

    job = cast("GenerationJob", SimpleNamespace(concept_id=uuid.uuid4()))
    await worker_module._update_request_interpretation(  # pyright: ignore[reportPrivateUsage]
        cast("AsyncSession", _RaisingSession()),
        job,
        _interp_outcome({"other": "data"}),
    )


# ---------------------------------------------------------------------------
# ADR-023 Task D1 (gate G3): _resolve_name_personalization_enabled.
#
# Reuses the _UpdateResult/_UpdateSession doubles above: both helpers resolve
# a single scalar via session.execute(...).scalar_one_or_none(), so the same
# fake shape covers this query too.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_name_personalization_enabled_true_when_profile_opted_in() -> (
    None
):
    """A resolved profile with real_name_ring1_enabled=True returns True."""
    import uuid

    session = _UpdateSession(row=True)
    job = cast("GenerationJob", SimpleNamespace(concept_id=uuid.uuid4()))

    result = await worker_module._resolve_name_personalization_enabled(  # pyright: ignore[reportPrivateUsage]
        cast("AsyncSession", session), job
    )

    assert result is True
    assert len(session.executed) == 1


@pytest.mark.asyncio
async def test_resolve_name_personalization_enabled_false_when_profile_opted_out() -> (
    None
):
    """A resolved profile with real_name_ring1_enabled=False returns False."""
    import uuid

    session = _UpdateSession(row=False)
    job = cast("GenerationJob", SimpleNamespace(concept_id=uuid.uuid4()))

    result = await worker_module._resolve_name_personalization_enabled(  # pyright: ignore[reportPrivateUsage]
        cast("AsyncSession", session), job
    )

    assert result is False


@pytest.mark.asyncio
async def test_resolve_name_personalization_enabled_false_when_no_request_row() -> None:
    """No originating StoryRequest row (guardian-authored concept) fails closed.

    The query is an INNER join, so scalar_one_or_none() returning None covers
    every zero-row case at once: no request row carries this concept_id, the
    request's profile_id is NULL (ondelete=SET NULL after a profile delete), or
    the joined profile is excluded by the liveness predicates. All of them must
    fail closed to False, never raise.
    """
    import uuid

    session = _UpdateSession(None)
    job = cast("GenerationJob", SimpleNamespace(concept_id=uuid.uuid4()))

    result = await worker_module._resolve_name_personalization_enabled(  # pyright: ignore[reportPrivateUsage]
        cast("AsyncSession", session), job
    )

    assert result is False


@pytest.mark.asyncio
async def test_resolve_name_personalization_enabled_false_when_concept_ambiguous() -> (
    None
):
    """Two request rows sharing one concept_id fail closed instead of raising.

    ``StoryRequest.concept_id`` carries no unique constraint, so a duplicate is
    representable and would make ``scalar_one_or_none()`` raise
    ``MultipleResultsFound``. An unhandled raise here would abort the whole
    generation job, so the resolver catches it and returns the fail-closed
    False that the surrounding security contract promises.
    """
    import uuid

    class _AmbiguousResult:
        """A result whose scalar accessor raises as SQLAlchemy would on 2 rows."""

        def scalar_one_or_none(self) -> object:
            raise MultipleResultsFound

    class _AmbiguousSession:
        """A session double returning the ambiguous result for any statement."""

        async def execute(self, _statement: object) -> _AmbiguousResult:
            return _AmbiguousResult()

    job = cast("GenerationJob", SimpleNamespace(concept_id=uuid.uuid4()))

    result = await worker_module._resolve_name_personalization_enabled(  # pyright: ignore[reportPrivateUsage]
        cast("AsyncSession", _AmbiguousSession()), job
    )

    assert result is False


# ---------------------------------------------------------------------------
# WS-7 D7: the bounded alternate-skeleton re-route (design section 6.2) and the
# CANNOT_CARRY failure surface (design sections 6.1, 6.3, CR-4).
# ---------------------------------------------------------------------------


def _named_contract(skeleton_slug: str) -> ThemeContract:
    """A _bound_dispatch_contract variant carrying a distinct skeleton_slug.

    The four declared slots match _bound_dispatch_skeleton's {SLOT} tokens (so
    load_contract_for's cross-check passes); only the ``skeleton_slug`` label
    differs, so a re-route can be observed by which contract's slug lands in the
    audit block / interpretation.
    """
    return _bound_dispatch_contract().model_copy(
        update={"skeleton_slug": skeleton_slug}
    )


def _setup_multi_skeleton(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    contracts: dict[str, str | None],
    band: str = "8-11",
) -> list[str]:
    """Write per-slug contract sidecars and dispatch resolve/load per slug.

    ``contracts`` maps a skeleton slug to its contract's ``skeleton_slug`` label,
    or ``None`` for a CONTRACT-LESS alternate (no sidecar written). Every slug
    shares _bound_dispatch_skeleton (identical {SLOT} tokens). Returns a list
    that records, in order, every slug ``resolve_skeleton_path`` is called with,
    so a test can assert exactly which alternates the re-route touched.
    """
    band_dir = tmp_path / band
    band_dir.mkdir(exist_ok=True)
    for slug, contract_slug in contracts.items():
        if contract_slug is None:
            continue
        contract_path = band_dir / f"{slug}.contract.json"
        contract_path.write_bytes(
            _named_contract(contract_slug).model_dump_json().encode("utf-8")
        )

    # A contract-less alternate must be a legacy, TOKEN-FREE skeleton so
    # load_contract_for returns None (a half-migrated skeleton -- {SLOT} tokens
    # with no sidecar -- would instead fail closed with a ValidationError).
    legacy_slugs = {slug for slug, cslug in contracts.items() if cslug is None}
    resolved: list[str] = []

    def _resolve(_band: str, slug: str) -> Path:
        resolved.append(slug)
        return band_dir / f"{slug}.json"

    def _load(path: Path) -> dict[str, object]:
        if path.stem in legacy_slugs:
            return {"id": f"s_{path.stem}", "nodes": []}
        return _bound_dispatch_skeleton()

    monkeypatch.setattr(worker_module, "resolve_skeleton_path", _resolve)
    monkeypatch.setattr(worker_module, "load_skeleton", _load)
    return resolved


_VIOLATING_RESPONSE = _interpret_bind_response(
    {
        "HERO": "a sword-wielder",  # trips the 3-5 band weapon floor every time
        "A1_GATE": "the jammed hatch",
        "A1_OFFER": "a glinting tide pool",
        "PRIZE": "Glass Starfish",
    }
)
_VALID_RESPONSE = _interpret_bind_response(_BOUND_DISPATCH_BINDINGS)


def _reroute_ctx(
    provider: GenerationProvider, alternatives: list[str]
) -> _SkeletonFillContext:
    return _SkeletonFillContext(
        authoring={
            "skeleton_slug": "planned",
            "theme_brief": {"premise": "a fox"},
            "skeleton_alternatives": alternatives,
        },
        brief=_dispatch_brief(),
        effective_provider=provider,
        pii=_dispatch_pii(),
    )


@pytest.mark.asyncio
async def test_run_skeleton_fill_reroute_binds_alternate_records_rerouted_from(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Planned bind fails closed, the first in-cell alternate binds: the fill
    proceeds on the alternate and records rerouted_from (WS-7 D7, 6.2)."""
    resolved = _setup_multi_skeleton(
        tmp_path,
        monkeypatch,
        contracts={"planned": "s_planned", "alt1": "s_alt1"},
    )
    monkeypatch.setattr(worker_module, "fill_skeleton", _passed_fill_stub)

    # planned: 2 violating attempts -> fail closed; alt1: 1 valid attempt -> bind.
    provider = MockProvider(
        responses=[_VIOLATING_RESPONSE, _VIOLATING_RESPONSE, _VALID_RESPONSE]
    )

    outcome = await _run_skeleton_fill(_reroute_ctx(provider, ["alt1"]))

    # planned resolved first (initial load), then alt1 during the re-route.
    assert resolved == ["planned", "alt1"]
    assert len(provider.calls) == 3  # 2 planned + 1 alternate; no fill call
    audit = cast("dict[str, object]", outcome.report["theme_contract"])
    assert audit["skeleton_slug"] == "s_alt1"
    assert audit["rerouted_from"] == "planned"
    interp = cast("dict[str, object]", outcome.report["request_interpretation"])
    assert interp["skeleton_slug"] == "s_alt1"


@pytest.mark.asyncio
async def test_run_skeleton_fill_reroute_skips_contractless_alternate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A contract-less alternate is not eligible and is skipped without a bind;
    the next contract-bearing alternate binds (WS-7 D7, 6.2 step 2)."""
    resolved = _setup_multi_skeleton(
        tmp_path,
        monkeypatch,
        contracts={"planned": "s_planned", "altnc": None, "alt2": "s_alt2"},
    )
    monkeypatch.setattr(worker_module, "fill_skeleton", _passed_fill_stub)

    provider = MockProvider(
        responses=[_VIOLATING_RESPONSE, _VIOLATING_RESPONSE, _VALID_RESPONSE]
    )

    outcome = await _run_skeleton_fill(_reroute_ctx(provider, ["altnc", "alt2"]))

    # altnc IS resolved+loaded (to discover it has no contract) but binds nothing.
    assert resolved == ["planned", "altnc", "alt2"]
    assert len(provider.calls) == 3  # 2 planned + 1 alt2; altnc consumed no call
    audit = cast("dict[str, object]", outcome.report["theme_contract"])
    assert audit["skeleton_slug"] == "s_alt2"
    assert audit["rerouted_from"] == "planned"


@pytest.mark.asyncio
async def test_run_skeleton_fill_reroute_respects_limit_third_alternate_untried(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """At most _REROUTE_LIMIT (2) contract-bearing alternates are bound; a 3rd
    is never even resolved, and exhaustion re-raises the original error (6.2)."""
    resolved = _setup_multi_skeleton(
        tmp_path,
        monkeypatch,
        contracts={
            "planned": "s_planned",
            "alt1": "s_alt1",
            "alt2": "s_alt2",
            "alt3": "s_alt3",
        },
    )
    monkeypatch.setattr(worker_module, "fill_skeleton", _fail_if_fill_called)

    # planned + alt1 + alt2 each exhaust 2 violating attempts (6 calls). alt3 is
    # never tried, so 6 responses is exactly enough; a 7th call would over-run
    # the mock and raise a different error, proving alt3 stays untouched.
    provider = MockProvider(responses=[_VIOLATING_RESPONSE] * 6)
    fill_context = _reroute_ctx(provider, ["alt1", "alt2", "alt3"])

    with pytest.raises(ValidationError) as exc_info:
        await _run_skeleton_fill(fill_context)

    assert resolved == ["planned", "alt1", "alt2"]  # alt3 never resolved
    assert len(provider.calls) == 6
    # Fail closed with the ORIGINAL theme-incompatibility error and its details.
    assert exc_info.value.details.get("field") == "theme_brief"
    violations = cast("list[dict[str, object]]", exc_info.value.details["violations"])
    assert any(v["rule"] == "forbid:weapon" for v in violations)


@pytest.mark.asyncio
async def test_run_skeleton_fill_pii_block_short_circuits_reroute(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A PII egress block on the planned bind (field="prompt") propagates
    immediately with ZERO alternate attempts (WS-7 D7, 6.2 step 5, CR-4)."""
    resolved = _setup_multi_skeleton(
        tmp_path,
        monkeypatch,
        contracts={"planned": "s_planned", "alt1": "s_alt1"},
    )
    monkeypatch.setattr(worker_module, "fill_skeleton", _fail_if_fill_called)

    # The premise carries an email; the PII guard raises inside interpret_and_bind
    # BEFORE any provider.complete, so the mock is never called.
    provider = MockProvider(responses=[_VALID_RESPONSE])
    ctx = _SkeletonFillContext(
        authoring={
            "skeleton_slug": "planned",
            "theme_brief": {"premise": "email me at foo@bar.com"},
            "skeleton_alternatives": ["alt1"],
        },
        brief=_dispatch_brief(),
        effective_provider=provider,
        pii=_dispatch_pii(),
    )

    with pytest.raises(ValidationError) as exc_info:
        await _run_skeleton_fill(ctx)

    # Only the planned skeleton was resolved; the alternate was never touched.
    assert resolved == ["planned"]
    assert provider.calls == []  # guard fired before any dispatch
    assert exc_info.value.details.get("field") == "prompt"


@pytest.mark.asyncio
async def test_run_generation_job_pii_block_records_personal_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A PII block on a bound-path job surfaces CANNOT_CARRY / PERSONAL_DETAILS
    on the report, classified from exc.field alone (WS-7 D7, 6.3, CR-4)."""
    import uuid as uuid_mod

    from cyo_adventure.db.models import Concept, GenerationJob

    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract_path = skeleton_path.with_name("themed-slug.contract.json")
    contract_path.write_bytes(_bound_dispatch_contract().model_dump_json().encode())
    monkeypatch.setattr(
        worker_module, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    monkeypatch.setattr(
        worker_module, "load_skeleton", lambda _path: _bound_dispatch_skeleton()
    )
    monkeypatch.setattr(worker_module, "fill_skeleton", _fail_if_fill_called)

    provider = MockProvider(responses=[_VALID_RESPONSE])  # never reached
    job_id = uuid_mod.uuid4()
    concept_id = uuid_mod.uuid4()
    job = GenerationJob(
        id=job_id,
        concept_id=concept_id,
        status="queued",
        authoring_metadata={
            "skeleton_slug": "themed-slug",
            "theme_brief": {"premise": "reach me at foo@bar.com"},
        },
    )
    concept = Concept(id=concept_id, family_id=uuid_mod.uuid4(), brief=_FRESHGEN_BRIEF)
    session_ctx = _ThemeContractBindFailureSession(job, concept)

    def factory() -> object:
        class _Ctx:
            async def __aenter__(self) -> _ThemeContractBindFailureSession:
                return session_ctx

            async def __aexit__(self, *exc: object) -> None:
                return None

        return _Ctx()

    with pytest.raises(ValidationError):
        await worker_module.run_generation_job(
            job_id, provider=provider, session_factory=factory
        )

    assert job.status == "failed"
    assert provider.calls == []  # PII guard fired before any provider dispatch
    assert job.report is not None
    assert "slot_binding_violations" not in job.report  # a PII block has none
    interp = cast("dict[str, object]", job.report["request_interpretation"])
    elements = cast("list[dict[str, object]]", interp["elements"])
    assert any(
        e["disposition"] == "cannot_carry" and e["reason"] == "personal_details"
        for e in elements
    )
    assert not any(e["reason"] == "no_conforming_binding" for e in elements)


class _StampSession:
    """Session double whose StoryRequest lookup returns a preset request row."""

    def __init__(self, request_row: object) -> None:
        self._row = request_row
        self.executed: list[object] = []

    async def execute(self, statement: object) -> _UpdateResult:
        self.executed.append(statement)
        return _UpdateResult(self._row)


def _cannot_carry_brief() -> ConceptBrief:
    return cast(
        "ConceptBrief",
        SimpleNamespace(age_band=SimpleNamespace(value="8-11"), content_nogo=[]),
    )


@pytest.mark.asyncio
async def test_record_cannot_carry_classifies_and_stamps_request_row() -> None:
    """The D7 helper classifies by exc.field alone and stamps the request row.

    field="theme_brief" -> NO_CONFORMING_BINDING; field="prompt" ->
    PERSONAL_DETAILS. Both stamp the resolved request row and augment the report.
    """
    import uuid

    for field, expected_reason in (
        ("theme_brief", "no_conforming_binding"),
        ("prompt", "personal_details"),
    ):
        request_row = SimpleNamespace(interpretation=None)
        session = _StampSession(request_row)
        job = cast("GenerationJob", SimpleNamespace(concept_id=uuid.uuid4()))
        exc = ValidationError("bind failed", field=field)

        report = await worker_module._record_cannot_carry_if_bound_path(  # pyright: ignore[reportPrivateUsage]
            cast("AsyncSession", session),
            job,
            exc,
            authoring={"skeleton_slug": "themed-slug", "theme_brief": {"premise": "x"}},
            brief=_cannot_carry_brief(),
            pii=PiiContext(child_names=frozenset()),
            report=None,
        )

        assert report is not None
        block = cast("dict[str, object]", report["request_interpretation"])
        elements = cast("list[dict[str, object]]", block["elements"])
        assert any(
            e["disposition"] == "cannot_carry" and e["reason"] == expected_reason
            for e in elements
        )
        # The same block was stamped onto the resolved request row (D6 path).
        assert request_row.interpretation == block


@pytest.mark.asyncio
async def test_record_cannot_carry_noop_for_non_skeleton_or_other_field() -> None:
    """The D7 helper is a no-op for a non-skeleton-fill job, a non-bind field,
    or a non-ValidationError (WS-7 D7 gating; fresh/legacy keep today's behavior).
    """
    import uuid

    job = cast("GenerationJob", SimpleNamespace(concept_id=uuid.uuid4()))
    brief = _cannot_carry_brief()
    pii = PiiContext(child_names=frozenset())

    async def _run(
        exc: Exception, authoring: dict[str, object] | None
    ) -> dict[str, object] | None:
        session = _StampSession(SimpleNamespace(interpretation=None))
        result = await worker_module._record_cannot_carry_if_bound_path(  # pyright: ignore[reportPrivateUsage]
            cast("AsyncSession", session),
            job,
            exc,
            authoring=authoring,
            brief=brief,
            pii=pii,
            report=None,
        )
        # A no-op must never issue the request-row query.
        assert session.executed == []
        return result

    # fresh_generation: no skeleton_slug in authoring.
    assert await _run(ValidationError("x", field="theme_brief"), None) is None
    # a bound-path job but a non-bind field (e.g. a render post-condition).
    assert (
        await _run(
            ValidationError("x", field="bound_skeleton"),
            {"skeleton_slug": "themed-slug", "theme_brief": {"premise": "x"}},
        )
        is None
    )
    # a non-ValidationError never triggers the surface.
    assert (
        await _run(
            RuntimeError("boom"),
            {"skeleton_slug": "themed-slug", "theme_brief": {"premise": "x"}},
        )
        is None
    )


@dataclass
class _LabelledProvider(MockProvider):
    """A MockProvider that declares a name and a model, as real adapters do.

    MockProvider deliberately declares neither, so the worker's labels fall
    back to the configured default for it. This double exists to tell the two
    cases apart: a label that survives the metering wrapper, versus a default
    that would look identical if the wrapper swallowed it.
    """

    name: str = "acme"
    model: str = "acme-1"


class TestProviderAccounting:
    """The worker records what each job spent, on every terminal path.

    These drive the real ``run_generation_job`` rather than the wrapper in
    isolation (``tests/unit/test_metered.py`` covers that), because the claim
    under test is a wiring claim: the ledger is created per job, the wrapper
    goes around the resolved provider so no stage can escape it, and the
    accounting reaches the row on both the success and the failure path.
    """

    @staticmethod
    def _fresh_gen_job(
        usage: TokenUsage, *, responses: int = 8
    ) -> tuple[
        Any,
        Any,
        Any,
    ]:
        """Build a queued fresh-generation job, its concept, and a provider."""
        import uuid as uuid_mod

        from cyo_adventure.db.models import Concept, GenerationJob

        job_id = uuid_mod.uuid4()
        concept_id = uuid_mod.uuid4()
        job = GenerationJob(
            id=job_id,
            concept_id=concept_id,
            status="queued",
            authoring_metadata=None,
        )
        concept = Concept(
            id=concept_id, family_id=uuid_mod.uuid4(), brief=_FRESHGEN_BRIEF
        )
        concept.created_by = uuid_mod.uuid4()
        provider = MockProvider(
            responses=[_CANNED_STORY_JSON] * responses, token_usage=usage
        )
        return job, concept, provider

    @staticmethod
    def _factory(session_ctx: object) -> Any:
        """Wrap a session double in the sync-callable factory the worker wants."""

        def factory() -> object:
            class _Ctx:
                async def __aenter__(self) -> object:
                    return session_ctx

                async def __aexit__(self, *exc: object) -> None:
                    return None

            return _Ctx()

        return factory

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_successful_run_persists_what_it_consumed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tokens, call count and provider time land on the job row."""
        monkeypatch.setattr(worker_module, "run_moderation_pipeline", AsyncMock())

        usage = TokenUsage(
            provider="openrouter",
            model="anthropic/claude-haiku-4.5",
            input_tokens=1_000,
            output_tokens=2_000,
            duration_ms=250,
        )
        job, concept, provider = self._fresh_gen_job(usage)
        session_ctx = _FreshGenSession(job, concept)

        await worker_module.run_generation_job(
            job.id, provider=provider, session_factory=self._factory(session_ctx)
        )

        calls = len(provider.calls)
        assert calls > 0, "the run must actually have called the provider"
        assert job.provider_call_count == calls
        assert job.provider_unknown_calls == 0
        assert job.input_tokens == 1_000 * calls
        assert job.output_tokens == 2_000 * calls
        assert job.provider_duration_ms == 250 * calls

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_fully_priced_model_persists_a_complete_cost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both halves are billed and the figure is flagged complete.

        Named and asserted the opposite until 2026-08-14. Every OpenRouter
        entry then recorded an output price and no input price, so the shape
        production persisted was a real non-zero amount that had to be read as
        a lower bound, and `cost_complete` was false on every row: the
        accounting migration's own advice to filter on that column selected
        nothing. `UW-C239` closed by reading both halves live from the vendor,
        so a job on a table-priced model now persists a figure a reader can
        use. `test_an_unpriced_model_persists_an_incomplete_cost` below still
        covers the model-absent-from-the-table case, which is how this reopens.
        """
        monkeypatch.setattr(worker_module, "run_moderation_pipeline", AsyncMock())

        usage = TokenUsage(
            provider="openrouter",
            model="anthropic/claude-haiku-4.5",
            input_tokens=1_000,
            output_tokens=1_000_000,
            duration_ms=250,
        )
        job, concept, provider = self._fresh_gen_job(usage)
        session_ctx = _FreshGenSession(job, concept)

        await worker_module.run_generation_job(
            job.id, provider=provider, session_factory=self._factory(session_ctx)
        )

        # $1/Mtok in on 1k tokens plus $5/Mtok out on one Mtok, per call.
        assert job.cost_usd == Decimal("5.001") * len(provider.calls)
        assert job.cost_complete is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_an_unpriced_model_persists_an_incomplete_cost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A model with no price entry records zero flagged incomplete, not free.

        This is the default mock's own state, and it is the state any newly
        adopted model starts in, so the honest reading of a zero here is
        "un-costable", never "cost nothing".
        """
        monkeypatch.setattr(worker_module, "run_moderation_pipeline", AsyncMock())

        usage = TokenUsage(
            provider="acme",
            model="acme-1",
            input_tokens=10,
            output_tokens=20,
            duration_ms=5,
        )
        job, concept, provider = self._fresh_gen_job(usage)
        session_ctx = _FreshGenSession(job, concept)

        await worker_module.run_generation_job(
            job.id, provider=provider, session_factory=self._factory(session_ctx)
        )

        assert job.cost_usd == Decimal(0)
        assert job.cost_complete is False
        # The tokens are still recorded: what is missing is the price, not the
        # measurement, and a later price backfill can recost the row.
        assert job.input_tokens == 10 * len(provider.calls)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_cost_past_the_column_maximum_is_capped_before_the_driver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A run too expensive for NUMERIC(12,6) is capped, not left to raise.

        Postgres raises ``numeric field overflow`` on an out-of-range integer
        part, and it raises at COMMIT rather than at assignment. Both writers
        of this column commit, so an uncapped amount would fault twice: once
        on the success path, then again inside the ``_record_failure`` the
        interrupt guard calls to record that very failure. The second raise
        would displace the first and leave the row in ``queued``/``running``
        with nothing recorded, defeating the guard entirely.

        This harness has no Postgres, so the raise itself is not reproducible
        here. What is pinned is the cap that makes it unreachable, at the
        boundary where the value is written rather than where it is stored.
        """
        monkeypatch.setattr(worker_module, "run_moderation_pipeline", AsyncMock())

        # $5.00/Mtok out, a million Mtok per call: far past six integer digits.
        usage = TokenUsage(
            provider="openrouter",
            model="anthropic/claude-haiku-4.5",
            input_tokens=1_000,
            output_tokens=10**12,
            duration_ms=250,
        )
        job, concept, provider = self._fresh_gen_job(usage)
        session_ctx = _FreshGenSession(job, concept)

        await worker_module.run_generation_job(
            job.id, provider=provider, session_factory=self._factory(session_ctx)
        )

        assert job.cost_usd == Decimal("999999.999999")
        # Capped means the figure is a lower bound, which is what this flag
        # already means, so it must be False even though every call was priced.
        assert job.cost_complete is False
        # The tokens are NOT capped: only the derived money column is, so the
        # measurement that would let a reader recompute the real cost survives.
        assert job.output_tokens == 10**12 * len(provider.calls)
        assert job.status not in ("queued", "running")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_an_uninstrumented_backend_is_counted_not_treated_as_free(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Calls reporting no usage raise unknown_calls rather than vanishing."""
        monkeypatch.setattr(worker_module, "run_moderation_pipeline", AsyncMock())

        usage = TokenUsage(
            provider="mock",
            model="mock",
            input_tokens=None,
            output_tokens=None,
            duration_ms=7,
        )
        job, concept, provider = self._fresh_gen_job(usage)
        session_ctx = _FreshGenSession(job, concept)

        await worker_module.run_generation_job(
            job.id, provider=provider, session_factory=self._factory(session_ctx)
        )

        calls = len(provider.calls)
        assert job.provider_call_count == calls
        assert job.provider_unknown_calls == calls
        assert job.input_tokens == 0
        assert job.cost_complete is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_failed_run_still_records_what_it_spent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Money spent before the failure is recorded on the failed row.

        A job that fails halfway has already paid for the calls it made. If
        only successful jobs carried accounting, the cost of the failures, the
        ones worth investigating, would be exactly the cost nobody could see.
        """
        monkeypatch.setattr(worker_module, "run_moderation_pipeline", AsyncMock())

        usage = TokenUsage(
            provider="openrouter",
            model="anthropic/claude-haiku-4.5",
            input_tokens=100,
            output_tokens=200,
            duration_ms=11,
        )
        # One queued response, then the mock raises on the next call, so the
        # run fails with exactly one call already recorded.
        job, concept, provider = self._fresh_gen_job(usage, responses=1)
        session_ctx = _FreshGenSession(job, concept)
        # Built outside the block so the raises assertion has exactly one
        # invocation to attribute the failure to (S5778).
        factory = self._factory(session_ctx)

        with pytest.raises(BusinessLogicError):
            await worker_module.run_generation_job(
                job.id, provider=provider, session_factory=factory
            )

        assert job.status == "failed"
        assert job.provider_call_count == 1
        assert job.input_tokens == 100
        assert job.output_tokens == 200

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_two_jobs_do_not_share_a_ledger(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each job's row carries only its own spend.

        The RQ worker runs jobs concurrently. A ledger held anywhere but per
        run would cross-bill them, and the symptom would be a plausible
        total on the wrong family's job, which no assertion downstream of the
        sum could distinguish from a correct one.
        """
        monkeypatch.setattr(worker_module, "run_moderation_pipeline", AsyncMock())

        def _usage(tokens: int) -> TokenUsage:
            return TokenUsage(
                provider="openrouter",
                model="anthropic/claude-haiku-4.5",
                input_tokens=tokens,
                output_tokens=tokens,
                duration_ms=1,
            )

        first_job, first_concept, first_provider = self._fresh_gen_job(_usage(10))
        second_job, second_concept, second_provider = self._fresh_gen_job(_usage(400))

        await worker_module.run_generation_job(
            first_job.id,
            provider=first_provider,
            session_factory=self._factory(_FreshGenSession(first_job, first_concept)),
        )
        await worker_module.run_generation_job(
            second_job.id,
            provider=second_provider,
            session_factory=self._factory(_FreshGenSession(second_job, second_concept)),
        )

        assert first_job.input_tokens == 10 * len(first_provider.calls)
        assert second_job.input_tokens == 400 * len(second_provider.calls)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_metering_wrapper_does_not_relabel_the_job(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """job.provider and job.model still name the provider that ran.

        Both labels are read off the provider with ``getattr(..., None) or
        <configured default>``, so a wrapper that failed to forward them would
        not raise: it would quietly stamp every job with the configured
        default, and an audit of which provider ran a job would be reading the
        config file instead of the run.
        """
        monkeypatch.setattr(worker_module, "run_moderation_pipeline", AsyncMock())

        usage = TokenUsage(
            provider="acme",
            model="acme-1",
            input_tokens=1,
            output_tokens=1,
            duration_ms=1,
        )
        job, concept, inner = self._fresh_gen_job(usage)
        labelled = _LabelledProvider(responses=inner.responses, token_usage=usage)
        session_ctx = _FreshGenSession(job, concept)

        await worker_module.run_generation_job(
            job.id, provider=labelled, session_factory=self._factory(session_ctx)
        )

        assert job.provider == "acme"
        assert job.model == "acme-1"

    @pytest.mark.unit
    def test_an_unmetered_provider_leaves_every_column_null(self) -> None:
        """A provider the worker never wrapped records nothing, not zero.

        NULL is the schema's "not recorded" state, and it has to stay
        reachable: writing zeros here would make an unrecorded job
        indistinguishable from a job that genuinely made no calls.
        """
        import uuid as uuid_mod

        from cyo_adventure.db.models import GenerationJob

        job = GenerationJob(
            id=uuid_mod.uuid4(), concept_id=uuid_mod.uuid4(), status="queued"
        )

        _stamp_provider_accounting(job, MockProvider(responses=[]))
        _stamp_provider_accounting(job, None)

        assert job.provider_call_count is None
        assert job.cost_usd is None
        assert job.cost_complete is None
