"""Unit tests for the cover-review verdict parser."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.covers.review import review_cover
from cyo_adventure.generation.usage import Completion, TokenUsage

pytestmark = pytest.mark.unit

_USAGE = TokenUsage(
    provider="mock", model="mock", input_tokens=None, output_tokens=None, duration_ms=0
)


@dataclass
class _FakeReviewProvider:
    """A minimal ImageReviewProvider test double: one queued response."""

    response: str | Exception
    calls: list[bytes] = field(default_factory=list)

    async def complete_with_image(
        self,
        *,
        system: str,
        prompt: str,
        image_bytes: bytes,
        image_mime: str,
        max_tokens: int,
    ) -> Completion:
        self.calls.append(image_bytes)
        if isinstance(self.response, Exception):
            raise self.response
        return Completion(text=self.response, usage=_USAGE)


@pytest.mark.asyncio
async def test_review_cover_pass_verdict_returns_pass_and_notes() -> None:
    provider = _FakeReviewProvider(response='{"verdict": "pass", "notes": ""}')
    verdict, notes = await review_cover(b"IMG", "a cat in a forest", provider)
    assert verdict == "pass"
    assert notes == ""
    assert provider.calls == [b"IMG"]


@pytest.mark.asyncio
async def test_review_cover_flag_verdict_returns_flag_and_notes() -> None:
    provider = _FakeReviewProvider(
        response='{"verdict": "flag", "notes": "visible text in the sky"}'
    )
    verdict, notes = await review_cover(b"IMG", "a cat in a forest", provider)
    assert verdict == "flag"
    assert notes == "visible text in the sky"


@pytest.mark.asyncio
async def test_review_cover_unparseable_response_fails_open() -> None:
    provider = _FakeReviewProvider(response="not json")
    verdict, notes = await review_cover(b"IMG", "a cat in a forest", provider)
    assert verdict is None
    assert notes is None


@pytest.mark.asyncio
async def test_review_cover_empty_response_fails_open() -> None:
    provider = _FakeReviewProvider(response="")
    verdict, notes = await review_cover(b"IMG", "a cat in a forest", provider)
    assert verdict is None
    assert notes is None


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["Flag", "FLAG", "flag ", " Flag\n"])
async def test_review_cover_flag_verdict_is_case_and_whitespace_insensitive(
    raw: str,
) -> None:
    """A genuine flag verdict must not silently fall through to fail-open
    (verdict=None, treated as pass by the caller) just because the model's
    JSON used different casing or trailing whitespace than the literal
    "flag" the system prompt requested.

    Built via json.dumps rather than an f-string: the " Flag\\n" case embeds
    a real newline, which a hand-built f-string would splice into the JSON
    text unescaped, producing invalid JSON (control characters are illegal
    unescaped inside a JSON string) and testing the wrong failure path.
    """
    provider = _FakeReviewProvider(
        response=json.dumps({"verdict": raw, "notes": "visible text"})
    )
    verdict, notes = await review_cover(b"IMG", "a cat in a forest", provider)
    assert verdict == "flag"
    assert notes == "visible text"


@pytest.mark.asyncio
async def test_review_cover_unexpected_verdict_value_fails_open() -> None:
    provider = _FakeReviewProvider(response='{"verdict": "maybe", "notes": "x"}')
    verdict, notes = await review_cover(b"IMG", "a cat in a forest", provider)
    assert verdict is None
    assert notes is None


@pytest.mark.asyncio
async def test_review_cover_non_dict_json_response_fails_open() -> None:
    provider = _FakeReviewProvider(response='["not", "a", "dict"]')
    verdict, notes = await review_cover(b"IMG", "a cat in a forest", provider)
    assert verdict is None
    assert notes is None


@pytest.mark.asyncio
async def test_review_cover_provider_error_fails_open() -> None:
    """A ProviderError (timeout, non-2xx, exhausted retries) fails open.

    Deliberate deviation from moderation/fidelity_review.py, which lets a
    ProviderError propagate: covers/service.py::generate_cover's outer
    except Exception would otherwise turn a transient OpenRouter outage into
    a failed cover generation. See this plan's Codebase Discovery Summary.
    """
    provider = _FakeReviewProvider(
        response=ProviderError("boom", provider="openrouter", model="m", leg_fatal=True)
    )
    verdict, notes = await review_cover(b"IMG", "a cat in a forest", provider)
    assert verdict is None
    assert notes is None


@pytest.mark.asyncio
async def test_review_cover_sends_the_generation_prompt_verbatim() -> None:
    """The generator's own prompt reaches the reviewer, not a re-derived one."""
    captured: dict[str, str] = {}

    class _CapturingProvider:
        async def complete_with_image(
            self, *, system, prompt, image_bytes, image_mime, max_tokens
        ):
            captured["prompt"] = prompt
            return Completion(text='{"verdict": "pass", "notes": ""}', usage=_USAGE)

    await review_cover(b"IMG", "EXACT PROMPT TEXT", _CapturingProvider())
    assert "EXACT PROMPT TEXT" in captured["prompt"]
