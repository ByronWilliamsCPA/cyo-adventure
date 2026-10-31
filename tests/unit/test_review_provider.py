"""Unit tests for review-model override resolution."""

from __future__ import annotations

import json
from typing import cast

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.review_provider import (
    ReviewProvider,
    _mock_review_response,  # pyright: ignore[reportPrivateUsage]
    build_review_provider,
    resolve_review_settings,
)
from cyo_adventure.moderation.stages import run_safety_stage


def test_none_override_returns_settings_unchanged() -> None:
    """No override means the original settings object is returned as-is."""
    # #ASSUME: data-integrity: Settings requires a classifier key whenever
    # review_provider != "mock" (see config.py::_require_classifier_when_reviewing);
    # supply one so this test exercises resolve_review_settings, not that gate.
    # #VERIFY: test_non_mock_review_without_any_classifier_key_raises in test_config.py.
    settings = Settings(review_provider="openrouter", openai_api_key="k")
    assert resolve_review_settings(settings, None) is settings


def test_override_replaces_openrouter_model() -> None:
    """An override replaces review_openrouter_model when that backend is active."""
    settings = Settings(review_provider="openrouter", openai_api_key="k")
    result = resolve_review_settings(settings, "anthropic/claude-opus-4.8")
    assert result.review_openrouter_model == "anthropic/claude-opus-4.8"
    assert result.review_provider == "openrouter"


def test_override_is_a_noop_for_modal_backend() -> None:
    """The deferred modal backend has no review model to override.

    Replaces the retired ollama case: openrouter is now the only backend with
    a configurable review model, so every other branch must fall through
    returning settings unchanged rather than writing an attribute nothing reads.
    """
    settings = Settings(review_provider="modal", openai_api_key="k")
    result = resolve_review_settings(settings, "some-model")
    assert result is settings


def test_override_is_a_noop_for_mock_backend() -> None:
    """The mock backend has no configurable model; the override is ignored."""
    settings = Settings(review_provider="mock")
    result = resolve_review_settings(settings, "some-model")
    assert result.review_provider == "mock"


# ---------------------------------------------------------------------------
# Deterministic mock reviewer (nightly real-backend E2E regression)
# ---------------------------------------------------------------------------

_MOCK_NODES: list[tuple[str, str]] = [
    ("n1", "A quiet morning at the lake."),
    ("n2", "The fox shares its berries."),
    ("n3", "They walk home together."),
]


def _mock_review_provider() -> ReviewProvider:
    """Build the mock review backend exactly as the pipeline does."""
    provider, _independent = build_review_provider(
        Settings(review_provider="mock"),
        generator_provider="mock",
        generator_model=None,
    )
    return provider


@pytest.mark.asyncio
async def test_mock_reviewer_batch_returns_safe_pass_for_every_node() -> None:
    """A safety batch is answered per node, so nothing falls back or auto-rejects.

    The old static ``"{}"`` made every node ``verdict_unknown`` and the story was
    auto-rejected, which kept the nightly full-pipeline tier red.
    """
    findings = await run_safety_stage(
        provider=_mock_review_provider(),
        nodes=_MOCK_NODES,
        age_band="8-11",
        max_tokens=256,
        batch_size=3,
    )
    assert {f.node_id for f in findings} == {"n1", "n2", "n3"}
    assert all(f.verdict is Verdict.PASS for f in findings)


@pytest.mark.asyncio
async def test_mock_reviewer_single_node_path_returns_safe_pass() -> None:
    """The size-1 (per-node) safety path also gets a parseable safe verdict."""
    findings = await run_safety_stage(
        provider=_mock_review_provider(),
        nodes=_MOCK_NODES,
        age_band="8-11",
        max_tokens=256,
        batch_size=1,
    )
    assert len(findings) == len(_MOCK_NODES)
    assert all(f.verdict is Verdict.PASS for f in findings)


def test_mock_review_response_leaves_other_stages_unchanged() -> None:
    """Coherence, engagement and fidelity prompts still get the old ``{}``."""
    assert _mock_review_response("Story nodes:\n[n1] <untrusted_passage>\nx\n") == "{}"
    assert _mock_review_response("anything else") == "{}"


def test_mock_review_response_batch_echoes_each_label_once() -> None:
    """Each node label in a batch prompt yields exactly one verdict entry."""
    prompt = (
        "Age band: 5-8\nNodes:\n"
        "[a] <untrusted_passage>\none\n</untrusted_passage>\n"
        "[b] <untrusted_passage>\ntwo\n</untrusted_passage>"
    )
    entries = cast("list[dict[str, str]]", json.loads(_mock_review_response(prompt)))  # pyright: ignore[reportAny]
    assert [e["node_id"] for e in entries] == ["a", "b"]
    assert {e["verdict"] for e in entries} == {"safe"}
