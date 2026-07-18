"""Unit tests for the Stage-0 classifier adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from cyo_adventure.moderation.classifiers import run_classifiers
from cyo_adventure.moderation.report import Source, Verdict

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


@pytest.mark.unit
async def test_openai_near_zero_score_yields_no_finding() -> None:
    """Unflagged categories with noise-level scores must not emit findings.

    OpenAI Moderation returns a nonzero float for every category on every
    call, so without a floor every clean node emits all categories as
    advisory findings and the review surface reads as fully flagged.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": False,
                        "categories": {"violence": False, "harassment": False},
                        # Real noise ceiling observed on clean prose: ~6e-4.
                        "category_scores": {
                            "violence": 0.0006,
                            "harassment": 0.0000022,
                        },
                    }
                ]
            },
        )

    findings = await run_classifiers(
        nodes=[("n1", "a friendly unicorn story")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert findings == []


@pytest.mark.unit
async def test_openai_elevated_score_yields_advisory() -> None:
    """An unflagged category at or above the floor still emits an advisory."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": False,
                        "categories": {"violence": False},
                        "category_scores": {"violence": 0.02},
                    }
                ]
            },
        )

    findings = await run_classifiers(
        nodes=[("n1", "a duel at dawn")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert [f.verdict for f in findings] == [Verdict.ADVISORY]


@pytest.mark.unit
async def test_openai_flagged_non_brightline_bypasses_floor() -> None:
    """A provider-flagged category emits an advisory even with a sub-floor score.

    OpenAI's own boolean flag crossed the provider's threshold; our score
    floor must never silence it.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": True,
                        "categories": {"violence": True},
                        "category_scores": {"violence": 0.001},
                    }
                ]
            },
        )

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert [f.verdict for f in findings] == [Verdict.ADVISORY]


@pytest.mark.unit
async def test_openai_brightline_below_floor_still_blocks() -> None:
    """The advisory floor must never suppress a flagged bright-line BLOCK.

    Bright-line blocking keys on the provider's boolean flag and is evaluated
    before (and independently of) the score floor, so a flagged bright-line
    category still hard-blocks even when its score sits far below the floor.
    This pins the child-safety guarantee against a future refactor that folds
    the floor check into the bright-line branch.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": True,
                        "categories": {"sexual/minors": True},
                        "category_scores": {"sexual/minors": 0.005},
                    }
                ]
            },
        )

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert [f.verdict for f in findings] == [Verdict.BLOCK]


@pytest.mark.unit
async def test_openai_score_at_floor_yields_advisory() -> None:
    """A score exactly at the floor emits an advisory (the floor is inclusive)."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": False,
                        "categories": {"violence": False},
                        "category_scores": {"violence": 0.01},
                    }
                ]
            },
        )

    findings = await run_classifiers(
        nodes=[("n1", "a tense standoff")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert [f.verdict for f in findings] == [Verdict.ADVISORY]


@pytest.mark.unit
async def test_openai_mixed_scores_filter_per_category() -> None:
    """The floor drops only the sub-floor categories, keeping above-floor ones."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": False,
                        "categories": {"violence": False, "harassment": False},
                        "category_scores": {"violence": 0.02, "harassment": 0.0005},
                    }
                ]
            },
        )

    findings = await run_classifiers(
        nodes=[("n1", "a duel at dawn")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert [(f.category, f.verdict) for f in findings] == [
        ("violence", Verdict.ADVISORY)
    ]


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
async def test_perspective_near_zero_score_yields_no_finding() -> None:
    """Perspective attributes with noise-level scores must not emit findings."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_perspective_response({"TOXICITY": 0.001, "INSULT": 0.004}),
        )

    findings = await run_classifiers(
        nodes=[("n1", "a friendly unicorn story")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    assert findings == []


@pytest.mark.unit
async def test_perspective_score_at_floor_yields_advisory() -> None:
    """A Perspective score exactly at the floor is kept (the drop is `< floor`)."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_perspective_response({"TOXICITY": 0.01}),
        )

    findings = await run_classifiers(
        nodes=[("n1", "somewhat rude text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    assert [f.verdict for f in findings] == [Verdict.ADVISORY]


@pytest.mark.unit
async def test_perspective_sexually_explicit_midband_yields_advisory() -> None:
    """SEXUALLY_EXPLICIT above the floor but below 0.8 advises, never blocks.

    The bright-line threshold is 0.8; a mid-band score must still surface to
    the guardian as an ADVISORY rather than being floored away or hard-blocked.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_perspective_response({"SEXUALLY_EXPLICIT": 0.5}),
        )

    findings = await run_classifiers(
        nodes=[("n1", "borderline content")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    assert [(f.category, f.verdict) for f in findings] == [
        ("sexually_explicit", Verdict.ADVISORY)
    ]


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


@pytest.mark.unit
async def test_openai_non_dict_top_level_response_returns_no_findings() -> None:
    """A top-level JSON body that is not a dict (for example a bare list) degrades."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["unexpected", "shape"])

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert findings == []


@pytest.mark.unit
async def test_openai_empty_results_list_returns_no_findings() -> None:
    """An empty ``results`` list (present but empty) must not raise or emit findings."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert findings == []


@pytest.mark.unit
async def test_openai_result_zero_not_a_dict_returns_no_findings() -> None:
    """``results[0]`` that is not a dict (for example a bare number) degrades."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [123]})

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert findings == []


@pytest.mark.unit
async def test_openai_non_dict_categories_and_scores_return_no_findings() -> None:
    """Non-dict ``categories``/``category_scores`` fields narrow to empty maps."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": False,
                        "categories": "not-a-dict",
                        "category_scores": "not-a-dict",
                    }
                ]
            },
        )

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert findings == []


@pytest.mark.unit
async def test_perspective_http_error_yields_degraded_advisory() -> None:
    """A non-2xx Perspective response surfaces one degraded advisory, not silence.

    The failure must be visible to the reviewer: a silent [] on a down provider
    is indistinguishable from a genuinely clean report.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    findings = await run_classifiers(
        nodes=[("n1", "text"), ("n2", "more text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    degraded = [f for f in findings if f.category == "classifier_degraded"]
    # Exactly one advisory for the whole run, not one per node, and non-gating.
    assert len(degraded) == 1
    assert degraded[0].verdict is Verdict.ADVISORY
    assert degraded[0].source is Source.PERSPECTIVE


@pytest.mark.unit
async def test_openai_http_error_yields_degraded_advisory() -> None:
    """A non-2xx OpenAI response likewise surfaces one degraded advisory."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="okey",
        perspective_key=None,
        client=_client(handler),
    )
    degraded = [f for f in findings if f.category == "classifier_degraded"]
    assert len(degraded) == 1
    assert degraded[0].source is Source.OPENAI


@pytest.mark.unit
async def test_require_classifiers_flags_unset_keys() -> None:
    """With require_classifiers, an unconfigured key yields a degraded advisory."""
    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key=None,
        client=_client(lambda _r: httpx.Response(200, json={})),
        require_classifiers=True,
    )
    degraded = {f.source for f in findings if f.category == "classifier_degraded"}
    assert degraded == {Source.OPENAI, Source.PERSPECTIVE}


@pytest.mark.unit
async def test_perspective_non_dict_top_level_response_returns_no_findings() -> None:
    """A top-level JSON body that is not a dict (for example a bare list) degrades."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["unexpected", "shape"])

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    assert findings == []


@pytest.mark.unit
async def test_perspective_missing_attribute_scores_returns_no_findings() -> None:
    """A response body missing ``attributeScores`` entirely degrades gracefully."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unrelated": "field"})

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    assert findings == []


@pytest.mark.unit
async def test_perspective_attribute_payload_not_a_dict_is_skipped() -> None:
    """A per-attribute payload that is not a dict (for example a bare string) is skipped."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"attributeScores": {"TOXICITY": "not-a-dict"}},
        )

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    assert findings == []


@pytest.mark.unit
async def test_perspective_attribute_value_non_numeric_is_skipped() -> None:
    """A ``summaryScore.value`` that is not numeric (for example a string) is skipped."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "attributeScores": {
                    "TOXICITY": {
                        "summaryScore": {"value": "high", "type": "PROBABILITY"}
                    }
                }
            },
        )

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    assert findings == []
