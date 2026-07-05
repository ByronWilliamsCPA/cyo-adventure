"""Unit tests for the Stage 1 semantic fidelity check."""

from __future__ import annotations

import json

import pytest

from cyo_adventure.moderation.fidelity_review import run_semantic_fidelity_check

pytestmark = pytest.mark.asyncio


class _ScriptedReviewProvider:
    """A ReviewProvider double that returns one scripted response."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Record the call and return the scripted response."""
        _ = max_tokens
        self.calls.append((system, prompt))
        return self._response


def _skeleton(body: str) -> dict[str, object]:
    return {
        "nodes": [
            {"id": "n1", "body": body, "choices": []},
        ]
    }


async def test_pass_verdict_returns_none() -> None:
    """A 'pass' verdict from the reviewer means no violation."""
    original = _skeleton("<<FILL role=setup words=10 beats='a fox finds a lantern'>>")
    filled = _skeleton("A fox finds a glowing lantern in the woods.")
    provider = _ScriptedReviewProvider(json.dumps({"verdict": "pass", "notes": ""}))

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None
    assert len(provider.calls) == 1


async def test_flag_verdict_returns_notes() -> None:
    """A 'flag' verdict surfaces the reviewer's notes as the violation message."""
    original = _skeleton("<<FILL role=setup words=10 beats='a fox finds a lantern'>>")
    filled = _skeleton("A dragon burns down the castle.")
    provider = _ScriptedReviewProvider(
        json.dumps({"verdict": "flag", "notes": "prose depicts unrelated events"})
    )

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result == "prose depicts unrelated events"


async def test_no_filled_nodes_makes_no_call() -> None:
    """A skeleton with no FILL-directive nodes never calls the reviewer."""
    original = _skeleton("plain prose, not a directive")
    filled = _skeleton("plain prose, not a directive")
    provider = _ScriptedReviewProvider(json.dumps({"verdict": "pass", "notes": ""}))

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None
    assert provider.calls == []


async def test_unparseable_response_fails_open() -> None:
    """A non-JSON or wrong-shape response is treated as pass, not an error."""
    original = _skeleton("<<FILL role=setup words=10 beats='a fox finds a lantern'>>")
    filled = _skeleton("A fox finds a lantern.")
    provider = _ScriptedReviewProvider("not json at all")

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None
