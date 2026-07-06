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
