"""Unit tests for the Stage-0 classifier adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from cyo_adventure.moderation.classifiers import run_classifiers
from cyo_adventure.moderation.report import Verdict

pytestmark = pytest.mark.asyncio


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.unit
async def test_openai_brightline_category_yields_block() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": True,
                        "categories": {"sexual/minors": True},
                        "category_scores": {"sexual/minors": 0.99},
                    }
                ]
            },
        )

    findings = await run_classifiers(
        nodes=[("n1", "some text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert any(f.verdict is Verdict.BLOCK for f in findings)


@pytest.mark.unit
async def test_missing_both_keys_yields_no_findings() -> None:
    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key=None,
        client=_client(lambda _r: httpx.Response(500)),
    )
    assert findings == []


@pytest.mark.unit
async def test_graded_category_is_not_a_block() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": False,
                        "categories": {"violence": False},
                        "category_scores": {"violence": 0.4},
                    }
                ]
            },
        )

    findings = await run_classifiers(
        nodes=[("n1", "mild peril")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert all(f.verdict is not Verdict.BLOCK for f in findings)


def _perspective_response(
    scores: dict[str, float],
) -> dict[str, object]:
    """Build a well-formed Perspective API response body."""
    return {
        "attributeScores": {
            attr: {"summaryScore": {"value": score, "type": "PROBABILITY"}}
            for attr, score in scores.items()
        }
    }


@pytest.mark.unit
async def test_perspective_sexually_explicit_high_score_yields_block() -> None:
    """A SEXUALLY_EXPLICIT summaryScore >= 0.8 must produce a BLOCK finding."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_perspective_response({"SEXUALLY_EXPLICIT": 0.95}),
        )

    findings = await run_classifiers(
        nodes=[("n1", "inappropriate content")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    assert any(
        f.verdict is Verdict.BLOCK and f.category == "sexually_explicit"
        for f in findings
    )


@pytest.mark.unit
async def test_perspective_toxicity_graded_score_is_not_block() -> None:
    """A graded TOXICITY score must produce a non-BLOCK (ADVISORY) finding."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_perspective_response({"TOXICITY": 0.3}),
        )

    findings = await run_classifiers(
        nodes=[("n1", "somewhat rude text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    assert findings
    assert all(f.verdict is not Verdict.BLOCK for f in findings)


@pytest.mark.unit
async def test_perspective_malformed_attribute_degrades_gracefully() -> None:
    """A Perspective response with a missing summaryScore must not raise; it degrades."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "attributeScores": {
                    # Well-formed attribute alongside the malformed one.
                    "TOXICITY": {"summaryScore": {"value": 0.2, "type": "PROBABILITY"}},
                    # Malformed: summaryScore key is absent entirely.
                    "SEXUALLY_EXPLICIT": {"noSummaryHere": True},
                }
            },
        )

    # Must not raise; malformed attribute is skipped, well-formed one is kept.
    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    categories = {f.category for f in findings}
    assert "toxicity" in categories
    assert "sexually_explicit" not in categories
