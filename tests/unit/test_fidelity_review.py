"""Unit tests for the Stage 1 semantic fidelity check."""

from __future__ import annotations

import json
from typing import cast

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


class _NonStringReviewProvider:
    """A misbehaving double that violates the ``complete -> str`` contract."""

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Return a non-string, simulating a contract-violating provider."""
        _ = (system, prompt, max_tokens)
        return cast("str", None)


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


async def test_skips_malformed_node_entries_when_building_beat_prose_pairs() -> None:
    """A malformed entry in either side's "nodes" list (not a dict, or a dict
    with no valid string id) is silently excluded, not a crash; only the
    well-formed node pair reaches the reviewer prompt."""
    original: dict[str, object] = {
        "nodes": [
            {"id": "n1", "body": "<<FILL role=setup words=10 beats='a fox'>>"},
            "garbage",
            {"body": "no id here"},
        ]
    }
    filled: dict[str, object] = {
        "nodes": [
            {"id": "n1", "body": "A fox finds a lantern."},
            {"id": 123, "body": "id is not a string"},
        ]
    }
    provider = _ScriptedReviewProvider(json.dumps({"verdict": "pass", "notes": ""}))

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None
    assert len(provider.calls) == 1
    assert "n1" in provider.calls[0][1]


async def test_skips_node_with_valid_id_but_non_string_body() -> None:
    """A node with a valid string id but a non-string (or missing) body is
    excluded from the id->body index, so it never reaches the beat/prose pair
    even though its id is well-formed."""
    original: dict[str, object] = {
        "nodes": [
            {"id": "n1", "body": "<<FILL role=setup words=10 beats='a fox'>>"},
            {"id": "n2", "body": None},
        ]
    }
    filled: dict[str, object] = {
        "nodes": [
            {"id": "n1", "body": "A fox finds a lantern."},
            {"id": "n2", "body": {"not": "a string"}},
        ]
    }
    provider = _ScriptedReviewProvider(json.dumps({"verdict": "pass", "notes": ""}))

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None
    assert len(provider.calls) == 1
    assert "n1" in provider.calls[0][1]
    assert "n2" not in provider.calls[0][1]


async def test_semantic_check_fails_open_on_non_string_response() -> None:
    """A provider returning a non-str (contract violation) fails open, not crash.

    The isinstance guard before json.loads prevents a TypeError from a None (or
    other non-str) response. This advisory-only check must treat a misbehaving
    reviewer as "pass" (return None) rather than aborting the fill job.
    """
    original = _skeleton("<<FILL role=setup words=10 beats='a fox finds a lantern'>>")
    filled = _skeleton("A fox finds a lantern.")
    provider = _NonStringReviewProvider()

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None
