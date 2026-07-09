"""Unit tests for the generation worker and provider factory (no DB, no Redis).

Tests cover:
1. build_provider("mock") returns a MockProvider seeded with a valid canned story.
2. build_provider with deferred providers raises ConfigurationError.
3. The canned mock story is schema-valid (Storybook.model_validate succeeds).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.config import settings as config_settings
from cyo_adventure.core.exceptions import ConfigurationError, ResourceNotFoundError
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
from cyo_adventure.storybook.models import Storybook

if TYPE_CHECKING:
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

    def test_anthropic_is_deferred(self) -> None:
        """The direct-Anthropic ('anthropic') adapter is deferred and raises."""
        settings = Settings(generation_provider="anthropic")  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings)
        # Points the operator at the supported OpenRouter path.
        assert "openrouter" in str(exc_info.value)

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
                pii=PiiContext(child_names=frozenset(), birthdates=frozenset()),
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
        "ConceptBrief", SimpleNamespace(age_band=SimpleNamespace(value="8-11"))
    )
    provider = cast("GenerationProvider", object())
    pii = PiiContext(child_names=frozenset(), birthdates=frozenset())
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
