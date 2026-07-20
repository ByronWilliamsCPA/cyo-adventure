"""Unit tests for the generation worker and provider factory (no DB, no Redis).

Tests cover:
1. build_provider("mock") returns a MockProvider seeded with a valid canned story.
2. build_provider with deferred providers raises ConfigurationError.
3. The canned mock story is schema-valid (Storybook.model_validate succeeds).
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.config import settings as config_settings
from cyo_adventure.core.exceptions import (
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
    _split_basic_auth,
    build_provider,
)
from cyo_adventure.generation.providers import (
    AnthropicProvider,
    FallbackProvider,
    ModalProvider,
    OllamaProvider,
    OpenRouterProvider,
)
from cyo_adventure.generation.worker import (
    _review_stage2_override,
    _run_skeleton_fill,
    _should_persist_storybook,
    _SkeletonFillContext,
)
from cyo_adventure.storybook.models import AgeBand, Storybook
from cyo_adventure.storybook.theme_contract import (
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
)
from cyo_adventure.validator.slots import DENYLIST_VERSION

if TYPE_CHECKING:
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
            build_provider(settings)
        assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_anthropic_key_value_not_leaked_in_error(self) -> None:
        """A missing-key error never echoes any key value."""
        settings = Settings(generation_provider="anthropic", anthropic_api_key=None)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings)
        assert "Bearer" not in str(exc_info.value)

    def test_anthropic_with_key_builds_bare_leg(self) -> None:
        """anthropic + key builds a single AnthropicProvider (no cascade)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="anthropic", anthropic_api_key="test-key"
        )
        provider = build_provider(settings)
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

    def test_openrouter_with_key_builds_three_leg_cascade(self) -> None:
        """openrouter + key + fallback enabled assembles the ordered cascade."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
        )
        provider = build_provider(settings)
        assert isinstance(provider, FallbackProvider)
        assert len(provider.legs) == 3
        assert isinstance(provider.legs[0], OpenRouterProvider)
        assert isinstance(provider.legs[1], OpenRouterProvider)
        assert isinstance(provider.legs[2], OllamaProvider)

    def test_openrouter_cascade_leg_order_matches_settings(self) -> None:
        """The cascade legs target the primary, fallback, and ollama models in order."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            openrouter_model="anthropic/claude-sonnet-4.6",
            openrouter_fallback_model="google/gemma-4-31b-it:free",
            ollama_model="qwen3",
        )
        provider = build_provider(settings)
        assert isinstance(provider, FallbackProvider)
        names = [leg.name for leg in provider.legs]  # type: ignore[attr-defined]
        assert names == [
            "openrouter:anthropic/claude-sonnet-4.6",
            "openrouter:google/gemma-4-31b-it:free",
            "ollama:qwen3",
        ]

    def test_openrouter_fallback_disabled_returns_bare_primary(self) -> None:
        """With fallback disabled the bare primary leg is returned (isolation runs)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            provider_fallback_enabled=False,
        )
        provider = build_provider(settings)
        assert isinstance(provider, OpenRouterProvider)
        assert provider.name == "openrouter:anthropic/claude-haiku-4.5"

    def test_ollama_returns_bare_ollama_leg(self) -> None:
        """generation_provider='ollama' returns the local Ollama leg alone."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama", ollama_model="qwen3:30b"
        )
        provider = build_provider(settings)
        assert isinstance(provider, OllamaProvider)
        assert provider.name == "ollama:qwen3:30b"

    def test_ollama_ca_bundle_valid_path_builds_leg(self) -> None:
        """A valid CA bundle path builds the leg with an SSLContext verifier."""
        import ssl

        import certifi

        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama", ollama_ca_bundle=certifi.where()
        )
        provider = build_provider(settings)
        assert isinstance(provider, OllamaProvider)
        # The CA bundle must be threaded through as an SSLContext (verify=),
        # not silently dropped; this is the leg's whole TLS-to-homelab purpose.
        assert isinstance(provider._verify, ssl.SSLContext)

    def test_ollama_no_ca_bundle_uses_default_verification(self) -> None:
        """Without a CA bundle the leg verifies against the public store (verify=True)."""
        settings = Settings(generation_provider="ollama")  # type: ignore[call-arg]
        provider = build_provider(settings)
        assert isinstance(provider, OllamaProvider)
        assert provider._verify is True

    def test_ollama_ca_bundle_bad_path_raises_configuration_error(self) -> None:
        """A nonexistent CA bundle path maps to ConfigurationError, not a raw OSError."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama",
            ollama_ca_bundle="/nonexistent/homelab-ca.pem",
        )
        with pytest.raises(ConfigurationError, match="OLLAMA_CA_BUNDLE"):
            build_provider(settings)

    def test_ollama_auth_over_http_remote_raises(self) -> None:
        """Basic auth over plaintext http to a remote host is rejected (cleartext leak)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama",
            ollama_base_url="http://ollama.example.com",
            ollama_auth="testservice:testcred",
        )
        with pytest.raises(ConfigurationError, match="cleartext"):
            build_provider(settings)

    def test_ollama_auth_over_https_is_allowed(self) -> None:
        """Basic auth over https builds the leg (credential is encrypted in transit)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama",
            ollama_base_url="https://ollama.example.com",
            ollama_auth="testservice:testcred",
        )
        assert isinstance(build_provider(settings), OllamaProvider)

    def test_ollama_auth_over_http_loopback_is_allowed(self) -> None:
        """Basic auth over http to loopback is allowed (never crosses the network)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama",
            ollama_base_url="http://localhost:11434",
            ollama_auth="testservice:testcred",
        )
        assert isinstance(build_provider(settings), OllamaProvider)

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

    def test_modal_partial_proxy_credentials_raises(self) -> None:
        """Setting only one of MODAL_PROXY_KEY/MODAL_PROXY_SECRET raises by name."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="modal",
            modal_base_url="https://example--cyo-standard.modal.run/v1",
            modal_model="google/gemma-4-26b-a4b-it",
            modal_proxy_key="only-the-key",
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
        provider = build_provider(settings, provider_override="anthropic")
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

    def test_model_override_threads_through_ollama(self) -> None:
        """model_override replaces the ollama leg's model (build_ollama_leg already supports it)."""
        settings = Settings(generation_provider="ollama")  # type: ignore[call-arg]
        provider = build_provider(settings, model_override="qwen3:30b")
        assert isinstance(provider, OllamaProvider)
        assert provider.name == "ollama:qwen3:30b"

    def test_model_override_replaces_anthropic_model(self) -> None:
        """model_override replaces the single anthropic leg's model."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="anthropic", anthropic_api_key="test-key"
        )
        provider = build_provider(settings, model_override="claude-opus-4-8")
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-opus-4-8"

    def test_unknown_provider_override_raises_configuration_error(self) -> None:
        """A provider_override outside the known branches raises, naming the value."""
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings, provider_override="not-a-real-provider")
        assert "not-a-real-provider" in str(exc_info.value)


class TestSplitBasicAuth:
    """_split_basic_auth turns an OLLAMA_AUTH string into (username, password)."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            # A basic user:pass pair splits cleanly.
            ("testservice:testcred", ("testservice", "testcred")),
            # A username containing hyphens still splits on the first colon.
            ("test-svc-laptop:abc123", ("test-svc-laptop", "abc123")),
            # First-colon split keeps a password that itself contains colons.
            ("user:p:a:ss", ("user", "p:a:ss")),
            # Missing/blank/half values yield no credential.
            (None, (None, None)),
            ("", (None, None)),
            ("   ", (None, None)),
            ("no-colon", (None, None)),
            (":only-password", (None, None)),
            ("only-user:", (None, None)),
            # Surrounding whitespace on either half is trimmed (stray-space typo).
            (" testservice : testcred ", ("testservice", "testcred")),
            (" : ", (None, None)),
        ],
    )
    def test_split(
        self, value: str | None, expected: tuple[str | None, str | None]
    ) -> None:
        """A well-formed user:password splits on the first colon; else (None, None)."""
        assert _split_basic_auth(value) == expected


class TestCannedStorySchemaValid:
    """The canned mock story satisfies the Storybook schema."""

    def test_canned_story_dict_validates(self) -> None:
        """_CANNED_STORY is a valid Storybook (Pydantic model_validate succeeds)."""
        book = Storybook.model_validate(_CANNED_STORY)
        assert book.id == "s_mock_generated"
        assert book.metadata.tier == 1
        assert len(book.nodes) == 7

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
        """The NEW case: a Stage 1 downgrade on an otherwise-clean fill persists."""
        outcome = GenerationOutcome(
            status="needs_review",
            storybook={"id": "s1"},
            report={"stage1_fidelity_violations": ["some violation"]},
            attempts=0,
            stage_log=[],
        )
        assert _should_persist_storybook(outcome) is True

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
    with pytest.raises(ResourceNotFoundError):
        await _run_skeleton_fill(
            _SkeletonFillContext(
                authoring={"theme_brief": {}},  # no skeleton_slug key
                brief=cast("ConceptBrief", object()),
                effective_provider=cast("GenerationProvider", object()),
                pii=PiiContext(child_names=frozenset()),
            )
        )


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
    """SQLAlchemy Result double yielding no child-name rows (empty PII)."""

    def all(self) -> list[tuple[str]]:
        return []


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
        ) -> MockProvider:
            captured["provider_override"] = provider_override
            captured["model_override"] = model_override
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
            authoring_metadata={"provider": "anthropic", "model": "claude-opus-4-8"},
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

        assert captured["provider_override"] == "anthropic"
        assert captured["model_override"] == "claude-opus-4-8"

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
        assert job.error == "interrupted"

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

    with pytest.raises(ValidationError):
        await _run_skeleton_fill(
            _SkeletonFillContext(
                authoring={"skeleton_slug": "half-migrated", "theme_brief": {}},
                brief=_dispatch_brief(),
                effective_provider=cast("GenerationProvider", object()),
                pii=_dispatch_pii(),
            )
        )


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

    with pytest.raises(ValidationError) as exc_info:
        await _run_skeleton_fill(
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
    # WS-7 D6: a bind failure raises out of _run_skeleton_fill BEFORE the
    # request-row update runs, so no partial interpretation is ever persisted.
    assert "request_interpretation" not in job.report


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
