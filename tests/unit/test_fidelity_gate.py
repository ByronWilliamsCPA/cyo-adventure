"""Unit tests for the combined Stage 1 fidelity gate."""

from __future__ import annotations

import json

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.generation.fidelity_gate import run_stage1_gate
from cyo_adventure.generation.pii import PiiContext

pytestmark = pytest.mark.asyncio


def _skeleton(body: str) -> dict[str, object]:
    return {
        "id": "s_x",
        "start_node": "n1",
        "variables": {},
        "metadata": {"age_band": "8-11"},
        "nodes": [
            {"id": "n1", "body": body, "is_ending": True, "on_enter": [], "choices": []}
        ],
    }


async def test_pure_code_failure_skips_the_semantic_call(monkeypatch) -> None:
    """A structural violation short-circuits before any provider call is built."""
    original = _skeleton("<<FILL role=setup words=10 beats='go'>>")
    filled = _skeleton("<<FILL role=setup words=10 beats='go'>>")  # still unfilled

    called = False

    def _fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("build_review_provider must not be called")

    monkeypatch.setattr(
        "cyo_adventure.generation.fidelity_gate.build_review_provider", _fail_if_called
    )
    pii = PiiContext(child_names=frozenset(), birthdates=frozenset())

    violations = await run_stage1_gate(
        original, filled, review_stage1_model=None, settings=Settings(), pii=pii
    )

    assert not called
    assert any("unfilled" in v for v in violations)


async def test_clean_pure_code_pass_runs_the_semantic_check(monkeypatch) -> None:
    """A structurally clean fill proceeds to the semantic check."""
    original = _skeleton("<<FILL role=setup words=10 beats='a fox finds a lantern'>>")
    filled = _skeleton(" ".join(["word"] * 10))

    class _FlaggingProvider:
        async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
            _ = (system, prompt, max_tokens)
            return json.dumps({"verdict": "flag", "notes": "beat mismatch"})

    monkeypatch.setattr(
        "cyo_adventure.generation.fidelity_gate.build_review_provider",
        lambda *a, **k: (_FlaggingProvider(), True),
    )
    pii = PiiContext(child_names=frozenset(), birthdates=frozenset())

    violations = await run_stage1_gate(
        original, filled, review_stage1_model=None, settings=Settings(), pii=pii
    )

    assert any("beat mismatch" in v for v in violations)


async def test_omitted_review_stage1_model_falls_back_to_prep_model(
    monkeypatch,
) -> None:
    """When review_stage1_model is omitted, prep_model becomes the review default.

    Closes #134: resolve_review_settings previously fell through to
    build_review_provider's own generic default whenever review_stage1_model
    was None, with no way to prefer the same model that wrote the prose.
    """
    original = _skeleton("<<FILL role=setup words=10 beats='a fox finds a lantern'>>")
    filled = _skeleton(" ".join(["word"] * 10))

    captured: dict[str, object] = {}

    def _capture_resolve(settings: Settings, model_override: str | None) -> Settings:
        captured["model_override"] = model_override
        return settings

    class _PassingProvider:
        async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
            _ = (system, prompt, max_tokens)
            return json.dumps({"verdict": "pass"})

    monkeypatch.setattr(
        "cyo_adventure.generation.fidelity_gate.resolve_review_settings",
        _capture_resolve,
    )
    monkeypatch.setattr(
        "cyo_adventure.generation.fidelity_gate.build_review_provider",
        lambda *a, **k: (_PassingProvider(), True),
    )
    pii = PiiContext(child_names=frozenset(), birthdates=frozenset())

    await run_stage1_gate(
        original,
        filled,
        review_stage1_model=None,
        prep_model="anthropic/claude-sonnet-5",
        settings=Settings(),
        pii=pii,
    )

    assert captured["model_override"] == "anthropic/claude-sonnet-5"


async def test_explicit_review_stage1_model_takes_precedence_over_prep_model(
    monkeypatch,
) -> None:
    """An explicit review_stage1_model override still wins over prep_model."""
    original = _skeleton("<<FILL role=setup words=10 beats='a fox finds a lantern'>>")
    filled = _skeleton(" ".join(["word"] * 10))

    captured: dict[str, object] = {}

    def _capture_resolve(settings: Settings, model_override: str | None) -> Settings:
        captured["model_override"] = model_override
        return settings

    class _PassingProvider:
        async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
            _ = (system, prompt, max_tokens)
            return json.dumps({"verdict": "pass"})

    monkeypatch.setattr(
        "cyo_adventure.generation.fidelity_gate.resolve_review_settings",
        _capture_resolve,
    )
    monkeypatch.setattr(
        "cyo_adventure.generation.fidelity_gate.build_review_provider",
        lambda *a, **k: (_PassingProvider(), True),
    )
    pii = PiiContext(child_names=frozenset(), birthdates=frozenset())

    await run_stage1_gate(
        original,
        filled,
        review_stage1_model="anthropic/claude-opus-4.8",
        prep_model="anthropic/claude-sonnet-5",
        settings=Settings(),
        pii=pii,
    )

    assert captured["model_override"] == "anthropic/claude-opus-4.8"
