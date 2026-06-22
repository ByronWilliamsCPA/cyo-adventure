"""Tests for the generation yield harness (WP14).

All tests run against deterministic MockProvider instances -- no real network
or LLM calls are made. Async tests use @pytest.mark.asyncio.

Test inventory:
    1. All-pass: provider factory always returns passing story -> pass_rate 1.0,
       meets_threshold True at 0.6, per_story length == len(briefs).
    2. Mixed pass/fail: 8 passing and 2 failing -> pass_rate 0.8,
       meets_threshold True at 0.6, False at 0.9.
    3. Zero briefs: total==0 -> pass_rate 0.0, meets_threshold False,
       no ZeroDivisionError.
    4. Failing story carries ERROR rule_ids in per_story entry.
    5. CLI smoke: run_yield directly with a small in-memory brief list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.generation.concept import ConceptBrief, StructurePattern
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import MockProvider, build_provider
from cyo_adventure.storybook.models import AgeBand
from scripts.yield_harness import YieldReport, run_yield

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "storybook"


def _load_fixture(name: str) -> dict[str, object]:
    """Load a fixture JSON file as a dict."""
    with (FIXTURE_DIR / name).open(encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


# A valid Storybook story (passes the gate cleanly).
_VALID_STORY: dict[str, object] = _load_fixture("valid/01_hello_world.json")
_VALID_JSON: str = json.dumps(_VALID_STORY)

# An invalid story with a dangling choice target (triggers L1-2 ERROR).
_BLOCKED_STORY: dict[str, object] = _load_fixture("invalid/graph/dangling_target.json")
_BLOCKED_JSON: str = json.dumps(_BLOCKED_STORY)


def _make_brief(
    *, premise: str = "A young sailor discovers a mysterious island."
) -> ConceptBrief:
    """Build a valid ConceptBrief with sane defaults.

    Args:
        premise: The story premise string.

    Returns:
        A fully validated :class:`~cyo_adventure.generation.concept.ConceptBrief`.
    """
    return ConceptBrief(
        title="Test Adventure",
        premise=premise,
        protagonist={"name": "Captain Rosa", "age": 10, "role": "explorer"},  # type: ignore[arg-type]
        point_of_view="second",
        age_band=AgeBand.BAND_8_11,
        reading_level_target=4.5,
        tier=1,
        tone="adventurous",
        themes_allowed=["friendship"],
        content_nogo=[],
        target_node_count=5,
        ending_count=1,
        structure_pattern=StructurePattern.QUEST,
        desired_variables=[],
        special_constraints=[],
    )


def _empty_pii() -> PiiContext:
    """Return a PiiContext with no forbidden tokens."""
    return PiiContext(child_names=frozenset(), birthdates=frozenset())


def _passing_factory() -> Callable[[], MockProvider]:
    """Return a factory whose providers always yield the valid canned story.

    Each call returns a fresh MockProvider seeded with enough copies of the
    valid story JSON to cover Stage A + Stage B without exhausting the queue.

    Returns:
        A zero-argument factory callable.
    """

    def _factory() -> MockProvider:
        """Build a fresh MockProvider that returns the valid story."""
        return MockProvider(responses=[_VALID_JSON] * 8)

    return _factory


def _blocked_factory() -> Callable[[], MockProvider]:
    """Return a factory whose providers always yield the blocked (invalid) story.

    The blocked story triggers a gate ERROR on every stage call and exhausts
    repairs, so every brief processed via this factory produces
    status='needs_review'.

    Returns:
        A zero-argument factory callable.
    """

    def _factory() -> MockProvider:
        """Build a fresh MockProvider that returns the blocked story."""
        # Supply enough copies for Stage A + repair loop without exhausting.
        return MockProvider(responses=[_BLOCKED_JSON] * 8)

    return _factory


# ---------------------------------------------------------------------------
# Test 1: All-pass run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_pass_returns_full_pass_rate() -> None:
    """All briefs produce 'passed' outcomes -> pass_rate 1.0, meets_threshold True.

    Three briefs are processed; the provider factory always returns the valid
    canned story so every story clears the gate with no repairs.
    """
    briefs = [_make_brief(premise=f"Premise {i}.") for i in range(3)]
    pii = _empty_pii()
    factory = _passing_factory()

    report = await run_yield(briefs, factory, pii, threshold=0.60)

    assert isinstance(report, YieldReport)
    assert report.total == 3
    assert report.passed == 3
    assert report.pass_rate == 1.0
    assert report.meets_threshold is True
    assert len(report.per_story) == 3

    for entry in report.per_story:
        assert entry["status"] == "passed"
        assert entry["failing_rule_ids"] == []


# ---------------------------------------------------------------------------
# Test 2: Mixed pass/fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_pass_fail_computes_correct_pass_rate() -> None:
    """8 passing and 2 failing briefs -> pass_rate 0.8, threshold-dependent result.

    The factory alternates: even-indexed briefs get a passing provider,
    odd-indexed briefs get a blocking provider. With 10 briefs total, indices
    0,2,4,6,8 pass (5) and 1,3,5,7,9 fail (5) -- but the task spec says "8
    passing and 2 failing", so the test uses a counter-based factory.
    """
    call_count = 0

    def _mixed_factory() -> MockProvider:
        """Return a passing provider for the first 8 calls, blocking for the last 2."""
        nonlocal call_count
        call_count += 1
        if call_count <= 8:
            return MockProvider(responses=[_VALID_JSON] * 8)
        return MockProvider(responses=[_BLOCKED_JSON] * 8)

    briefs = [_make_brief(premise=f"Premise {i}.") for i in range(10)]
    pii = _empty_pii()

    report = await run_yield(briefs, _mixed_factory, pii, threshold=0.60)

    assert report.total == 10
    assert report.passed == 8
    assert report.pass_rate == pytest.approx(0.8)

    # Meets 0.60 threshold.
    assert report.meets_threshold is True

    # Does NOT meet 0.90 threshold.
    report_strict = await run_yield(
        briefs, _build_counter_factory(), pii, threshold=0.90
    )
    assert report_strict.meets_threshold is False
    assert report_strict.pass_rate == pytest.approx(0.8)


def _build_counter_factory() -> Callable[[], MockProvider]:
    """Build an 8-pass, 2-fail counter factory for the threshold comparison.

    Returns:
        A zero-argument factory callable.
    """
    counter = 0

    def _factory() -> MockProvider:
        """Return a passing or failing provider based on call count."""
        nonlocal counter
        counter += 1
        if counter <= 8:
            return MockProvider(responses=[_VALID_JSON] * 8)
        return MockProvider(responses=[_BLOCKED_JSON] * 8)

    return _factory


# ---------------------------------------------------------------------------
# Test 3: Zero briefs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_briefs_no_division_by_zero() -> None:
    """Empty brief list: total==0, pass_rate 0.0, meets_threshold False."""
    pii = _empty_pii()
    factory = _passing_factory()

    report = await run_yield([], factory, pii, threshold=0.60)

    assert report.total == 0
    assert report.passed == 0
    assert report.pass_rate == 0.0
    assert report.meets_threshold is False
    assert report.per_story == []


# ---------------------------------------------------------------------------
# Test 4: Failing story carries ERROR rule_ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failing_story_carries_error_rule_ids() -> None:
    """A brief whose provider returns the blocked story has ERROR rule ids.

    The dangling_target fixture triggers rule L1-2 (dangling choice target).
    The per_story entry for that brief must contain 'L1-2' in failing_rule_ids.
    """
    briefs = [_make_brief()]
    pii = _empty_pii()
    factory = _blocked_factory()

    report = await run_yield(briefs, factory, pii, threshold=0.60)

    assert report.total == 1
    assert report.passed == 0
    assert len(report.per_story) == 1

    entry = report.per_story[0]
    # The story produces 'needs_review' (blocked but a doc was produced).
    assert entry["status"] in {"needs_review", "failed"}

    failing_ids: list[str] = entry["failing_rule_ids"]  # type: ignore[assignment]
    assert len(failing_ids) > 0, "Expected at least one failing rule id"
    # The dangling target fixture triggers L1-2.
    assert "L1-2" in failing_ids


# ---------------------------------------------------------------------------
# Test 5: CLI smoke -- run_yield directly with a small in-memory brief list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cli_smoke_run_yield_with_canned_story_factory() -> None:
    """Smoke test: run_yield with the canned-story factory produces 100% pass rate.

    This exercises the same code path as the CLI 'main()' function without
    requiring subprocess invocation. The canned story (used by build_provider
    in mock mode) passes the gate cleanly on every brief.
    """
    briefs = [
        _make_brief(premise="A young pirate seeks buried treasure."),
        _make_brief(premise="A curious girl explores an ancient library."),
    ]
    pii = _empty_pii()

    _settings = Settings()

    def _canned_factory() -> MockProvider:
        """Build a fresh MockProvider via build_provider (mock mode)."""
        provider = build_provider(_settings)
        assert isinstance(provider, MockProvider)
        return provider

    report = await run_yield(briefs, _canned_factory, pii, threshold=0.60)

    assert report.total == 2
    assert report.passed == 2
    assert report.pass_rate == 1.0
    assert report.meets_threshold is True

    for entry in report.per_story:
        assert entry["status"] == "passed"
        assert entry["attempts"] == 0
        assert entry["failing_rule_ids"] == []
