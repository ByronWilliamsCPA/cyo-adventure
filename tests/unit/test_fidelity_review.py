"""Unit tests for the Stage 1 semantic fidelity check."""

from __future__ import annotations

import json
from typing import cast

import pytest

from cyo_adventure.generation.usage import Completion, TokenUsage
from cyo_adventure.moderation.fidelity_review import run_semantic_fidelity_check

pytestmark = pytest.mark.asyncio


_REVIEW_USAGE = TokenUsage(
    provider="scripted",
    model="scripted",
    input_tokens=None,
    output_tokens=None,
    duration_ms=0,
)


class _ScriptedReviewProvider:
    """A ReviewProvider double that returns one scripted response."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[tuple[str, str]] = []

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Record the call and return the scripted response."""
        _ = max_tokens
        self.calls.append((system, prompt))
        return Completion(text=self._response, usage=_REVIEW_USAGE)


class _NonCompletionReviewProvider:
    """A misbehaving double that returns no Completion at all.

    ReviewProvider is a structural protocol, so nothing stops an implementation
    returning a bare string (the pre-instrumentation shape) or ``None``. That
    is the likelier real-world violation than a malformed Completion, since it
    is what every caller of the old contract returned.
    """

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Return a non-Completion, simulating a contract-violating provider."""
        _ = (system, prompt, max_tokens)
        return cast("Completion", None)


class _NonStringTextReviewProvider:
    """A double whose Completion carries a non-str ``text``.

    Completion is a plain frozen dataclass with no runtime validation, so the
    shape can be right while the payload is not.
    """

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Return a Completion whose text violates the declared ``str`` type."""
        _ = (system, prompt, max_tokens)
        return Completion(text=cast("str", None), usage=_REVIEW_USAGE)


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


@pytest.mark.parametrize(
    "provider",
    [_NonCompletionReviewProvider(), _NonStringTextReviewProvider()],
    ids=["not-a-completion", "completion-with-non-str-text"],
)
async def test_semantic_check_provider_contract_violation_fails_open(
    provider: _NonCompletionReviewProvider | _NonStringTextReviewProvider,
) -> None:
    """A provider violating the contract fails open, at either boundary.

    Two guards run before json.loads: one that the return value is a
    Completion, one that its text is a str. Both must hold, because binding the
    result through ``object`` is the only thing keeping them live under a strict
    type checker. This advisory-only check must treat a misbehaving reviewer as
    "pass" (return None) rather than aborting the fill job with an
    AttributeError or a TypeError.
    """
    original = _skeleton("<<FILL role=setup words=10 beats='a fox finds a lantern'>>")
    filled = _skeleton("A fox finds a lantern.")

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None


def _node_with_choices(
    node_id: str, body: str, choices: list[dict[str, object]]
) -> dict[str, object]:
    return {"id": node_id, "body": body, "choices": choices}


async def test_rewritten_choice_label_pair_reaches_the_reviewer() -> None:
    """Both the original and the final choice label are sent to the reviewer, so
    it can judge whether the reskin preserved the decision's meaning."""
    original: dict[str, object] = {
        "nodes": [
            _node_with_choices(
                "n1",
                "<<FILL role=choice words=10 beats='pick a path at the fork'>>",
                [{"id": "c1", "label": "Go left at the fork.", "target": "n2"}],
            )
        ]
    }
    filled: dict[str, object] = {
        "nodes": [
            _node_with_choices(
                "n1",
                "You reach a fork in the glowing caves.",
                [
                    {
                        "id": "c1",
                        "label": "Drift left along the humming duct.",
                        "target": "n2",
                    }
                ],
            )
        ]
    }
    provider = _ScriptedReviewProvider(json.dumps({"verdict": "pass", "notes": ""}))

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None
    prompt = provider.calls[0][1]
    assert "Go left at the fork." in prompt
    assert "Drift left along the humming duct." in prompt


async def test_inverted_choice_label_intent_is_flagged() -> None:
    """When the reviewer flags a label whose meaning changed, the note surfaces."""
    original: dict[str, object] = {
        "nodes": [
            _node_with_choices(
                "n1",
                "<<FILL role=choice words=10 beats='decide about the stranger'>>",
                [{"id": "c1", "label": "Trust the stranger.", "target": "n2"}],
            )
        ]
    }
    filled: dict[str, object] = {
        "nodes": [
            _node_with_choices(
                "n1",
                "A hooded figure offers to guide you.",
                [{"id": "c1", "label": "Attack the stranger.", "target": "n2"}],
            )
        ]
    }
    provider = _ScriptedReviewProvider(
        json.dumps({"verdict": "flag", "notes": "c1 inverts the decision"})
    )

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result == "c1 inverts the decision"


async def test_label_only_node_without_fill_body_still_calls_reviewer() -> None:
    """A node whose body is not a FILL directive but whose choice label was
    rewritten is still reviewed (label intent alone is enough to check)."""
    original: dict[str, object] = {
        "nodes": [
            _node_with_choices(
                "n1",
                "plain prose, not a directive",
                [{"id": "c1", "label": "Open the gate.", "target": "n2"}],
            )
        ]
    }
    filled: dict[str, object] = {
        "nodes": [
            _node_with_choices(
                "n1",
                "plain prose, not a directive",
                [{"id": "c1", "label": "Lift the portcullis.", "target": "n2"}],
            )
        ]
    }
    provider = _ScriptedReviewProvider(json.dumps({"verdict": "pass", "notes": ""}))

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None
    assert len(provider.calls) == 1
    prompt = provider.calls[0][1]
    assert "Open the gate." in prompt
    assert "Lift the portcullis." in prompt


async def test_malformed_and_unmatched_choices_are_skipped() -> None:
    """Choices without a string id/label, and skeleton choices absent from the
    fill, never reach the reviewer prompt; only matched, well-formed pairs do."""
    original: dict[str, object] = {
        "nodes": [
            _node_with_choices(
                "n1",
                "<<FILL role=choice words=10 beats='a choice'>>",
                [
                    {"id": "c1", "label": "Go north.", "target": "n2"},
                    {"label": "no id", "target": "n3"},
                    {"id": "c2", "label": 123, "target": "n4"},
                    {"id": "c3", "label": "Only in skeleton.", "target": "n5"},
                ],
            )
        ]
    }
    filled: dict[str, object] = {
        "nodes": [
            _node_with_choices(
                "n1",
                "You stand at a crossroads.",
                [{"id": "c1", "label": "Head up the hill path.", "target": "n2"}],
            )
        ]
    }
    provider = _ScriptedReviewProvider(json.dumps({"verdict": "pass", "notes": ""}))

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None
    prompt = provider.calls[0][1]
    assert "Go north." in prompt
    assert "Head up the hill path." in prompt
    assert "Only in skeleton." not in prompt


async def test_sentinel_bearing_beats_and_body_never_reach_the_review_prompt() -> None:
    """Personalization sentinels are stripped from both halves of the pair.

    ``moderation/pipeline.py`` and ``moderation/rescreen.py`` already strip
    before their own model calls. Without the matching strip here, this Stage 1
    pass would score sentinel-noisy text while a later rescreen of the same
    published content scores stripped text: the exact comparability break
    rescreen's strip exists to prevent. The generic word must survive, so this
    also pins that the strip is a substitution and not a deletion.
    """
    original = _skeleton(
        "<<FILL role=setup words=10 beats='{~HERO:Robin~} finds a lantern'>>"
    )
    filled = _skeleton("{~HERO:Robin~} finds a glowing lantern in the woods.")
    provider = _ScriptedReviewProvider(json.dumps({"verdict": "pass", "notes": ""}))

    result = await run_semantic_fidelity_check(original, filled, provider)

    assert result is None
    assert len(provider.calls) == 1
    system, prompt = provider.calls[0]
    assert "{~" not in prompt
    assert "~}" not in prompt
    assert "{~" not in system
    assert prompt.count("Robin") == 2
