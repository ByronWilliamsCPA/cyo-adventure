"""Unit tests for the Stage-0 classifier adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from cyo_adventure.moderation import classifiers
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
@pytest.mark.usefixtures("_no_backoff")
async def test_openai_non_dict_top_level_response_raises_classifier_unavailable() -> (
    None
):
    """A top-level JSON body that is not a dict (for example a bare list).

    Gap G11 regression: this shape change used to log a warning and silently
    return ``[]``, indistinguishable from a genuinely clean node. It must now
    surface as a structural degraded-classifier finding via the same
    retry/circuit-breaker path as an HTTP failure, never vanish.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["unexpected", "shape"])

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    degraded = [f for f in findings if f.category == "classifier_degraded"]
    assert len(degraded) == 1
    assert degraded[0].source is Source.OPENAI
    assert degraded[0].structural is True


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_openai_empty_results_list_raises_classifier_unavailable() -> None:
    """An empty ``results`` list (present but empty) is malformed, not clean.

    Gap G11 regression: see test_openai_non_dict_top_level_response_raises_
    classifier_unavailable above.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    degraded = [f for f in findings if f.category == "classifier_degraded"]
    assert len(degraded) == 1
    assert degraded[0].source is Source.OPENAI
    assert degraded[0].structural is True


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_openai_result_zero_not_a_dict_raises_classifier_unavailable() -> None:
    """``results[0]`` that is not a dict (for example a bare number).

    Gap G11 regression: see test_openai_non_dict_top_level_response_raises_
    classifier_unavailable above.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [123]})

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    degraded = [f for f in findings if f.category == "classifier_degraded"]
    assert len(degraded) == 1
    assert degraded[0].source is Source.OPENAI
    assert degraded[0].structural is True


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_openai_non_dict_categories_raises_classifier_unavailable() -> None:
    """Non-dict ``categories`` narrows to an empty map, treated as malformed.

    Gap G11 regression: see test_openai_non_dict_top_level_response_raises_
    classifier_unavailable above.
    """

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
    degraded = [f for f in findings if f.category == "classifier_degraded"]
    assert len(degraded) == 1
    assert degraded[0].source is Source.OPENAI
    assert degraded[0].structural is True


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
@pytest.mark.usefixtures("_no_backoff")
async def test_perspective_non_dict_top_level_response_raises_classifier_unavailable() -> (
    None
):
    """A top-level JSON body that is not a dict (for example a bare list).

    Gap G11 regression: this shape change used to log a warning and silently
    return ``[]``, indistinguishable from a genuinely clean node. It must now
    surface as a structural degraded-classifier finding via the same
    retry/circuit-breaker path as an HTTP failure, never vanish.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["unexpected", "shape"])

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    degraded = [f for f in findings if f.category == "classifier_degraded"]
    assert len(degraded) == 1
    assert degraded[0].source is Source.PERSPECTIVE
    assert degraded[0].structural is True


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_perspective_missing_attribute_scores_raises_classifier_unavailable() -> (
    None
):
    """A response body missing ``attributeScores`` entirely is malformed.

    Gap G11 regression: see
    test_perspective_non_dict_top_level_response_raises_classifier_unavailable
    above.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unrelated": "field"})

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    degraded = [f for f in findings if f.category == "classifier_degraded"]
    assert len(degraded) == 1
    assert degraded[0].source is Source.PERSPECTIVE
    assert degraded[0].structural is True


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


# ---------------------------------------------------------------------------
# Non-finite (NaN / Infinity) score handling (issue #144)
#
# httpx's `.json()` uses json.loads with allow_nan=True, so a provider can
# return the non-standard NaN/Infinity tokens for a category score. Such a
# value survives the isinstance(_, (int, float)) guard (float("nan") is a
# float) but would make Finding.__post_init__ raise ValueError. Both
# classifiers must degrade gracefully instead of aborting the Stage-0 batch.
#
# These use raw `content=` bodies (not the `json=` kwarg): httpx serializes
# `json=` with allow_nan=False and would reject the value before it ever
# reached the code under test, so the raw body reproduces exactly what a real
# provider sends over the wire.
# ---------------------------------------------------------------------------

_JSON_HEADERS = {"content-type": "application/json"}


@pytest.mark.unit
async def test_openai_non_finite_unflagged_score_yields_no_finding() -> None:
    """An unflagged category with a NaN score is dropped without raising."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers=_JSON_HEADERS,
            content=(
                b'{"results":[{"flagged":false,'
                b'"categories":{"violence":false},'
                b'"category_scores":{"violence":NaN}}]}'
            ),
        )

    findings = await run_classifiers(
        nodes=[("n1", "a quiet afternoon")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    assert findings == []


@pytest.mark.unit
async def test_openai_non_finite_flagged_brightline_still_blocks() -> None:
    """A flagged bright-line category still BLOCKs even when its score is Infinity.

    The boolean flag is an independent signal; a garbage score must not drop a
    provider-flagged bright-line block. The reported score falls back to None.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers=_JSON_HEADERS,
            content=(
                b'{"results":[{"flagged":true,'
                b'"categories":{"sexual/minors":true},'
                b'"category_scores":{"sexual/minors":Infinity}}]}'
            ),
        )

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        perspective_key=None,
        client=_client(handler),
    )
    blocks = [f for f in findings if f.verdict is Verdict.BLOCK]
    assert len(blocks) == 1
    assert blocks[0].category == "sexual/minors"
    assert blocks[0].score is None


@pytest.mark.unit
async def test_perspective_non_finite_score_degrades_gracefully() -> None:
    """A NaN Perspective summary score is skipped, not raised; siblings survive."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers=_JSON_HEADERS,
            content=(
                b'{"attributeScores":{'
                b'"TOXICITY":{"summaryScore":{"value":0.2,"type":"PROBABILITY"}},'
                b'"SEXUALLY_EXPLICIT":{"summaryScore":'
                b'{"value":NaN,"type":"PROBABILITY"}}}}'
            ),
        )

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key="pkey",
        client=_client(handler),
    )
    categories = {f.category for f in findings}
    assert "toxicity" in categories
    assert "sexually_explicit" not in categories


# ---------------------------------------------------------------------------
# Stage-0 coverage gating (AL-033)
# ---------------------------------------------------------------------------
#
# Before this behaviour the first ClassifierUnavailable disabled its classifier
# for every remaining node and the only trace was a non-gating ADVISORY, so a
# report with most of a book unscreened was indistinguishable from a clean one.


@pytest.fixture
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero the retry sleeps, keeping the retry COUNT, so tests stay fast.

    Setting the tuple empty would remove the retries themselves, not just their
    delays, since its length is what defines the attempt budget.
    """
    monkeypatch.setattr(classifiers, "_RETRY_BACKOFF_SECONDS", (0.0, 0.0))


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_transient_failure_is_retried_and_does_not_lose_coverage() -> None:
    """A node that fails once then succeeds is screened, with no coverage flag."""
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500)
        # A non-empty categories map: an empty dict is itself a malformed
        # shape after the gap-G11 fix (OpenAI Moderation always returns every
        # category with a boolean value; an empty map now raises
        # ClassifierUnavailable rather than passing as a quiet "nothing
        # flagged" response), so this stub must look like a real success.
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
        nodes=[("n1", "text")],
        openai_key="okey",
        perspective_key=None,
        client=_client(handler),
    )
    assert calls["n"] == 2, "the failed call must be retried"
    assert not [
        f for f in findings if f.category == "classifier_coverage_incomplete"
    ], "a retried-and-succeeded node is fully covered"


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_persistent_failure_flags_incomplete_coverage_as_a_soft_gate() -> None:
    """An unscreenable node produces a FLAG, not merely an advisory."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    findings = await run_classifiers(
        nodes=[("n1", "text"), ("n2", "text"), ("n3", "text")],
        openai_key="okey",
        perspective_key=None,
        client=_client(handler),
    )
    coverage = [f for f in findings if f.category == "classifier_coverage_incomplete"]
    assert len(coverage) == 1
    assert coverage[0].verdict is Verdict.FLAG, (
        "incomplete bright-line coverage must gate; an ADVISORY would let a "
        "partially-screened report reach in_review looking clean"
    )
    assert coverage[0].source is Source.OPENAI
    assert coverage[0].node_id is None, "coverage is a whole-story finding"
    # #VERIFY: gap G2a (design doc section 2.5): a pipeline fail-safe like an
    # incomplete-coverage finding must be excluded from the threshold
    # flywheel's override-rate evidence, which insights.py does by keying
    # off this flag.
    assert coverage[0].structural is True


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_unscreened_nodes_are_named_and_counted() -> None:
    """The finding names the shortfall so a reviewer knows what was not checked."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    nodes = [(f"n{i}", "text") for i in range(5)]
    findings = await run_classifiers(
        nodes=nodes,
        openai_key="okey",
        perspective_key=None,
        client=_client(handler),
    )
    coverage = next(
        f for f in findings if f.category == "classifier_coverage_incomplete"
    )
    assert "0 of 5" in coverage.message
    assert "5 node(s) were never bright-line screened" in coverage.message
    assert "n0" in coverage.message


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_a_later_node_still_gets_screened_after_one_node_fails() -> None:
    """One bad node costs one node's coverage, not the rest of the book."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if "poison" in body:
            seen.append("poison")
            return httpx.Response(500)
        seen.append("ok")
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
        nodes=[("bad", "poison"), ("good", "clean text")],
        openai_key="okey",
        perspective_key=None,
        client=_client(handler),
    )
    assert "ok" in seen, "the node after the failure must still be called"
    assert any(f.verdict is Verdict.BLOCK for f in findings), (
        "a bright-line hit on a later node must still be caught"
    )
    coverage = next(
        f for f in findings if f.category == "classifier_coverage_incomplete"
    )
    assert "1 node(s) were never bright-line screened" in coverage.message


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_circuit_opens_after_consecutive_failures_and_stops_calling() -> None:
    """A down provider is not hammered once per node, but every node is reported."""
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    nodes = [(f"n{i}", "text") for i in range(40)]
    findings = await run_classifiers(
        nodes=nodes,
        openai_key="okey",
        perspective_key=None,
        client=_client(handler),
    )
    assert calls["n"] < len(nodes), (
        "the circuit must open rather than calling a down provider for every node"
    )
    coverage = next(
        f for f in findings if f.category == "classifier_coverage_incomplete"
    )
    assert "40 node(s) were never bright-line screened" in coverage.message, (
        "nodes skipped by the open circuit are still unscreened and must be counted"
    )


@pytest.mark.unit
async def test_unconfigured_key_does_not_flag_coverage() -> None:
    """An intentionally absent classifier is an advisory, never a gate."""
    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        perspective_key=None,
        client=_client(lambda _r: httpx.Response(500)),
        require_classifiers=True,
    )
    assert [f for f in findings if f.category == "classifier_degraded"]
    assert not [
        f for f in findings if f.category == "classifier_coverage_incomplete"
    ], "no key configured is a deployment choice, not a screening shortfall"
