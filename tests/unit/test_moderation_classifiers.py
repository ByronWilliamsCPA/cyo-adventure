"""Unit tests for the Stage-0 classifier adapters."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from cyo_adventure.moderation import classifiers
from cyo_adventure.moderation.classifiers import run_classifiers
from cyo_adventure.moderation.report import (
    FindingSeverity,
    ModerationReport,
    Source,
    Verdict,
    moderation_coverage_incomplete,
)

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
        client=_client(handler),
    )
    assert any(f.verdict is Verdict.BLOCK for f in findings)


@pytest.mark.unit
async def test_missing_key_yields_no_findings() -> None:
    """The only classifier is OpenAI; an unset key means no findings at all."""
    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        client=_client(lambda _r: httpx.Response(500)),
    )
    assert findings == []


@pytest.mark.unit
async def test_run_classifiers_has_no_perspective_key_parameter() -> None:
    """Perspective is retired: run_classifiers rejects a perspective_key kwarg.

    (ratified sunset) so a caller cannot silently re-wire it back in.
    """
    assert "perspective_key" not in inspect.signature(run_classifiers).parameters


@pytest.mark.unit
async def test_run_classifiers_never_produces_perspective_findings() -> None:
    """Even a require_classifiers run degrades OpenAI alone.

    Perspective produces nothing because it is no longer called at all.
    """
    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key=None,
        client=_client(lambda _r: httpx.Response(500)),
        require_classifiers=True,
    )
    assert not any(f.source is Source.PERSPECTIVE for f in findings)


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
        client=_client(handler),
    )
    assert [(f.category, f.verdict) for f in findings] == [
        ("violence", Verdict.ADVISORY)
    ]


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
        client=_client(handler),
    )
    degraded = [f for f in findings if f.category == "classifier_degraded"]
    assert len(degraded) == 1
    assert degraded[0].source is Source.OPENAI
    assert degraded[0].structural is True


@pytest.mark.unit
async def test_openai_http_error_yields_degraded_advisory() -> None:
    """A non-2xx OpenAI response surfaces one degraded advisory, not silence.

    The failure must be visible to the reviewer: a silent [] on a down provider
    is indistinguishable from a genuinely clean report.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="okey",
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
        client=_client(lambda _r: httpx.Response(200, json={})),
        require_classifiers=True,
    )
    degraded = {f.source for f in findings if f.category == "classifier_degraded"}
    assert degraded == {Source.OPENAI}


# ---------------------------------------------------------------------------
# Non-finite (NaN / Infinity) score handling (issue #144)
#
# httpx's `.json()` uses json.loads with allow_nan=True, so a provider can
# return the non-standard NaN/Infinity tokens for a category score. Such a
# value survives the isinstance(_, (int, float)) guard (float("nan") is a
# float) but would make Finding.__post_init__ raise ValueError. OpenAI, the
# only classifier this module calls, must degrade gracefully instead of
# aborting the Stage-0 batch.
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
        client=_client(handler),
    )
    blocks = [f for f in findings if f.verdict is Verdict.BLOCK]
    assert len(blocks) == 1
    assert blocks[0].category == "sexual/minors"
    assert blocks[0].score is None


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
async def test_partial_failure_flags_incomplete_coverage() -> None:
    """Some nodes screen cleanly, one is abandoned: the shortfall must still gate.

    Distinct from ``test_persistent_failure_flags_incomplete_coverage_as_a_soft_gate``
    above, which fails every node: this is a genuinely PARTIAL failure, most
    of the book screens clean and exactly one node is abandoned, which is
    the shape a real classifier outage on a large book actually takes. The
    finding must still gate: ``concern="classifier_unavailable"`` is what
    ``ModerationReport.has_coverage_gap`` and the stored
    ``moderation_coverage_incomplete()`` read, not the bare ``FLAG`` verdict.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if "bad-node" in body:
            return httpx.Response(500)
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

    nodes = [
        ("n1", "good text one"),
        ("n2", "bad-node text"),
        ("n3", "good text two"),
    ]
    findings = await run_classifiers(
        nodes=nodes,
        openai_key="okey",
        client=_client(handler),
    )

    coverage = [f for f in findings if f.category == "classifier_coverage_incomplete"]
    assert len(coverage) == 1
    assert "n2" in coverage[0].message
    assert "n1" not in coverage[0].message
    assert "n3" not in coverage[0].message
    assert coverage[0].concern == "classifier_unavailable"

    report = ModerationReport()
    for finding in findings:
        report.add(finding)
    assert report.has_coverage_gap is True
    assert report.blocks_release is True


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


# ---------------------------------------------------------------------------
# Retry discrimination (AL-663)
#
# _run_openai used to catch base httpx.HTTPError, which raise_for_status()
# raises as HTTPStatusError, so a permanent 401 was retried exactly like a
# transient 429: once per node, for the whole book. The oracle here is the
# CALL COUNT, not the findings, because the findings are identical either way.
# That is precisely why the defect survived: every coverage assertion in this
# file still passes with the discrimination removed.
# ---------------------------------------------------------------------------


def _counting_handler(
    status: int, calls: dict[str, int]
) -> Callable[[httpx.Request], httpx.Response]:
    """Always answer with `status`, tallying how many calls were made."""

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status)

    return handler


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_permanent_status_is_not_retried() -> None:
    """A 400 cannot succeed on re-issue, so it must be attempted exactly once.

    _no_backoff is applied deliberately: it keeps the retry BUDGET while zeroing
    the sleeps, so a call count of 1 proves the retries were skipped rather than
    merely being fast.
    """
    calls = {"n": 0}

    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="okey",
        client=_client(_counting_handler(400, calls)),
    )

    assert calls["n"] == 1, (
        "a permanent rejection must not be retried; retrying only delays the "
        "coverage FLAG that is coming regardless"
    )
    # The safety property is unchanged: failing fast still gates.
    coverage = [f for f in findings if f.category == "classifier_coverage_incomplete"]
    assert len(coverage) == 1, "the abandoned node must still produce a coverage FLAG"
    assert coverage[0].verdict is Verdict.FLAG
    assert coverage[0].severity is FindingSeverity.HIGH


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_transient_status_is_still_retried() -> None:
    """The contrast case: 429 must keep its full retry budget.

    Without this, "stop retrying permanent failures" could be satisfied by
    never retrying anything, which would trade wasted calls for lost coverage.
    """
    calls = {"n": 0}

    await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="okey",
        client=_client(_counting_handler(429, calls)),
    )

    expected = len(classifiers._RETRY_BACKOFF_SECONDS) + 1
    assert calls["n"] == expected, (
        f"a rate limit is transient and must still get {expected} attempts"
    )


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_credential_failure_opens_the_circuit_on_first_node() -> None:
    """An expired key rejects every node identically, so prove it once.

    A single node cannot show this: the saving is that nodes 2..N are never
    called at all, so the test needs a book whose remaining nodes would
    otherwise each be attempted.
    """
    calls = {"n": 0}
    nodes = [(f"n{i}", "text") for i in range(1, 6)]

    findings = await run_classifiers(
        nodes=nodes,
        openai_key="expired",
        client=_client(_counting_handler(401, calls)),
    )

    assert calls["n"] == 1, (
        "a rejected credential condemns the whole run; one call must be enough "
        "to establish that, instead of re-proving it once per node"
    )
    coverage = [f for f in findings if f.category == "classifier_coverage_incomplete"]
    assert len(coverage) == 1
    for node_id, _ in nodes:
        assert node_id in coverage[0].message or "more" in coverage[0].message, (
            "every node the circuit skipped must still be counted as unscreened"
        )


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_incomplete_coverage_finding_carries_classifier_unavailable_concern() -> (
    None
):
    """The FLAG alone is not enough to gate; ``concern`` is what the report reads.

    ``ModerationReport.has_coverage_gap`` and the stored
    ``moderation_coverage_incomplete()`` gate both key off ``Finding.concern``,
    not verdict text. A ``Finding`` built with no ``concern=`` argument
    defaults to ``None``, which matches neither ``COVERAGE_GAP_CONCERNS`` nor
    ``MOCK_MODERATED_CONCERNS``, so a book Stage 0 mostly failed to screen
    would route to ``submit()`` and become eligible for auto-repair instead
    of being blocked. This pins the concern on the finding classifiers.py
    actually emits.
    """
    findings = await run_classifiers(
        nodes=[(f"n{i}", "text") for i in range(1, 6)],
        openai_key="expired",
        client=_client(lambda _r: httpx.Response(401)),
    )
    coverage = next(
        f for f in findings if f.category == "classifier_coverage_incomplete"
    )
    assert coverage.concern == "classifier_unavailable"


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_credential_circuit_breaker_report_blocks_release() -> None:
    """The end-to-end proof: a Stage-0 credential failure must gate the book.

    This is the exact defect the concern fix closes: a Stage-0 shortfall
    used to reach ``ModerationReport`` as a bare FLAG with ``concern=None``,
    which ``has_coverage_gap`` and ``moderation_coverage_incomplete()`` both
    silently ignored, so ``blocks_release`` stayed False and a book whose
    Stage-0 classifier never screened most of its nodes routed to
    ``submit()`` and became eligible for auto-repair.
    """
    findings = await run_classifiers(
        nodes=[(f"n{i}", "text") for i in range(1, 6)],
        openai_key="expired",
        client=_client(lambda _r: httpx.Response(401)),
    )

    report = ModerationReport()
    for finding in findings:
        report.add(finding)

    assert report.has_coverage_gap is True
    assert report.blocks_release is True
    assert moderation_coverage_incomplete(report.to_dict()) is True


@pytest.mark.unit
@pytest.mark.usefixtures("_no_backoff")
async def test_server_error_does_not_disable_the_classifier() -> None:
    """A 500 is transient, so it must NOT latch the classifier off.

    `disabled` is never reset within a run, so latching it on the wrong status
    would silently drop coverage for the rest of a book over one blip.

    The oracle is WHICH nodes were attempted, not how many calls were made. A
    total count is not enough: three retries of node 1 and one attempt each at
    nodes 1..3 both give three calls, so a count-based assertion passes even
    when the classifier latched off after the first node. Each node therefore
    carries distinct prose and the handler records what it actually saw.
    """
    seen: set[str] = set()
    nodes = [(f"n{i}", f"prose-{i}") for i in range(1, 4)]

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        for _, prose in nodes:
            if prose in body:
                seen.add(prose)
        return httpx.Response(500)

    await run_classifiers(
        nodes=nodes,
        openai_key="okey",
        client=_client(handler),
    )

    assert seen == {prose for _, prose in nodes}, (
        "a 5xx must not latch the classifier off after the first node; every "
        f"node should still be attempted, but only {sorted(seen)} were"
    )


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
        client=_client(lambda _r: httpx.Response(500)),
        require_classifiers=True,
    )
    assert [f for f in findings if f.category == "classifier_degraded"]
    assert not [
        f for f in findings if f.category == "classifier_coverage_incomplete"
    ], "no key configured is a deployment choice, not a screening shortfall"


# ---------------------------------------------------------------------------
# Task B1.3: Stage-0 severity mapping (design doc 2.1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, FindingSeverity.LOW),
        (0.49, FindingSeverity.LOW),
        (0.5, FindingSeverity.MEDIUM),
        (0.79, FindingSeverity.MEDIUM),
        (0.8, FindingSeverity.HIGH),
        (1.0, FindingSeverity.HIGH),
    ],
    ids=[
        "floor",
        "just_below_medium",
        "medium_boundary",
        "just_below_high",
        "high_boundary",
        "ceiling",
    ],
)
async def test_severity_from_score_bands(
    score: float, expected: FindingSeverity
) -> None:
    assert classifiers._severity_from_score(score) is expected


@pytest.mark.unit
async def test_openai_brightline_finding_has_severity() -> None:
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
        client=_client(handler),
    )
    block = next(f for f in findings if f.verdict is Verdict.BLOCK)
    assert block.severity is FindingSeverity.HIGH


@pytest.mark.unit
async def test_degraded_classifier_finding_has_fixed_medium_severity() -> None:
    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        client=_client(lambda _r: httpx.Response(500)),
    )
    degraded = next(f for f in findings if f.category == "classifier_degraded")
    assert degraded.severity is FindingSeverity.MEDIUM
    assert degraded.score is None


@pytest.mark.unit
async def test_incomplete_coverage_finding_has_fixed_high_severity() -> None:
    findings = await run_classifiers(
        nodes=[("n1", "text")],
        openai_key="k",
        client=_client(lambda _r: httpx.Response(500)),
    )
    coverage = next(
        f for f in findings if f.category == "classifier_coverage_incomplete"
    )
    assert coverage.severity is FindingSeverity.HIGH
    assert coverage.score is None
