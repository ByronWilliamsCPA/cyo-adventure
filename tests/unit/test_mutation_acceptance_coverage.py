"""Branch-coverage tests for defensive paths in ``mutation/acceptance.py`` (WS-5).

Targets the reject-only helper branches the primary stage-table suite in
``test_mutation_acceptance.py`` does not reach: the Tier-2 parse guard, the two
clock-reproof early exits, the unparseable-parent state-floor skip, the stage-4
contract discard, and the apply-after-preconditions failure path.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.acceptance import (
    Stage,
    _clock_reproof_reason,  # pyright: ignore[reportPrivateUsage]
    _RunContext,  # pyright: ignore[reportPrivateUsage]
    _state_floor_reason,  # pyright: ignore[reportPrivateUsage]
    _tier2_state_stage,  # pyright: ignore[reportPrivateUsage]
    run_acceptance,
)
from cyo_adventure.mutation.operators import M1
from cyo_adventure.mutation.ops import (
    MutationResult,
    OpParams,
    PreconditionReport,
)
from cyo_adventure.mutation.state_ops import M5
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storybook.theme_contract import ThemeContract
from cyo_adventure.validator.walk import WalkResult, walk_configurations

if TYPE_CHECKING:
    import random
    from collections.abc import Mapping

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_FLOODED_QUARTER = _SKELETONS_ROOT / "10-13" / "the-flooded-quarter.json"
_CAVE = _SKELETONS_ROOT / "8-11" / "the-cave-of-echoes.json"


def _flooded_quarter() -> dict[str, object]:
    """Return the-flooded-quarter Tier-2 skeleton as a raw document."""
    return cast(
        "dict[str, object]",
        json.loads(_FLOODED_QUARTER.read_text(encoding="utf-8")),
    )


def _cave() -> dict[str, object]:
    """Return the-cave-of-echoes Tier-1 skeleton as a raw document."""
    return cast("dict[str, object]", json.loads(_CAVE.read_text(encoding="utf-8")))


class _RaisingApplyOp:
    """A stub op whose preconditions pass but whose apply raises ValidationError."""

    op_id = "RAISE"

    def preconditions(
        self, parent: Mapping[str, object], params: OpParams
    ) -> PreconditionReport:
        """Return a satisfied report (the apply failure is the test's subject)."""
        _ = (parent, params)
        return PreconditionReport.passed()

    def apply(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> MutationResult:
        """Raise as if a post-precondition invariant failed inside apply."""
        _ = (parent, params, rng)
        msg = "synthetic apply failure after preconditions passed"
        raise ValidationError(msg, field="apply", value=None)


@pytest.mark.unit
def test_tier2_stage_returns_a_parse_reason_for_an_unparseable_candidate() -> None:
    """A Tier-2 candidate that fails to parse is discarded with a parse reason."""
    context = _RunContext()
    candidate: dict[str, object] = {
        "variables": [{"name": "x"}],
        "nodes": [],
    }  # tier 2, not a Storybook
    reason = _tier2_state_stage(context, {}, candidate, walk_cap=100)
    assert reason is not None
    assert "failed to parse for the state walk" in reason


@pytest.mark.unit
def test_clock_reproof_is_skipped_when_the_cell_has_no_floor() -> None:
    """A non-production story has no ``min_complete_floor``, so the clock is a no-op."""
    raw = _flooded_quarter()
    meta = cast("dict[str, object]", raw["metadata"])
    meta["production_eligible"] = False
    story = Storybook.model_validate(raw)
    walk = walk_configurations(story)
    assert _clock_reproof_reason(story, walk) is None


@pytest.mark.unit
def test_clock_reproof_flags_an_unreachable_satisfying_finish() -> None:
    """An empty walk makes every satisfying finish unreachable (infinite fastest)."""
    story = Storybook.model_validate(_flooded_quarter())
    empty_walk = WalkResult(configs={}, edges={}, capped=False)
    reason = _clock_reproof_reason(story, empty_walk)
    assert reason is not None
    assert "fastest satisfying finish is infinite" in reason


@pytest.mark.unit
def test_state_floor_is_skipped_for_an_unparseable_parent() -> None:
    """An unparseable parent skips the state-signature floor rather than discarding."""
    story = Storybook.model_validate(_flooded_quarter())
    walk = walk_configurations(story)
    assert _state_floor_reason({"not": "a story"}, story, walk) is None


@pytest.mark.unit
def test_run_acceptance_discards_at_stage_four_on_a_mismatched_contract() -> None:
    """A gate-passing candidate whose contract omits its tokens is discarded at 4."""
    cave = _cave()
    wrong_contract = ThemeContract.model_validate(
        {
            "contract_version": 1,
            "skeleton_slug": "wrong",
            "age_band": "8-11",
            "default_binding": {"HERO": "a fox"},
            "slots": [
                {"id": "HERO", "scope": "global", "meaning": "hero", "guidance": ""}
            ],
        }
    )
    result = run_acceptance(
        M1,
        cave,
        OpParams.of(),
        seed=0,
        parent_slug="the-cave-of-echoes",
        mutated_contract=wrong_contract,
    )
    assert result.discarded_at_stage is Stage.CONTRACT
    assert result.promotable is False
    assert "stage 4" in result.discard_reason


@pytest.mark.unit
def test_run_acceptance_treats_a_failed_apply_as_a_stage_zero_discard() -> None:
    """An apply that raises after preconditions pass is a controlled stage-0 discard."""
    result = run_acceptance(_RaisingApplyOp(), _cave(), OpParams.of(), seed=0)
    assert result.discarded_at_stage is Stage.PRECONDITIONS
    assert "apply failed after preconditions passed" in result.discard_reason
    assert result.candidate is None


@pytest.mark.unit
def test_run_acceptance_passes_the_tier2_stage_for_a_clean_retune() -> None:
    """A clean M5 retune clears every D6 Tier-2 check and records a passed stage."""
    parent = _flooded_quarter()
    retune = OpParams.of(
        mode="retune", variable="oil", max=4, description="Roomier oil."
    )
    result = run_acceptance(M5, parent, retune, seed=0, parent_slug="fq")
    assert result.discarded_at_stage is None
    stage_details = {
        outcome.stage: outcome for outcome in result.stages if outcome.passed
    }
    assert Stage.TIER2_STATE in stage_details
    assert "Tier-2 checks passed" in stage_details[Stage.TIER2_STATE].detail


@pytest.mark.unit
def test_mutated_copy_helper_is_isolated() -> None:
    """Sanity: the raw loaders return independent documents (no shared mutation)."""
    a = _flooded_quarter()
    b = _flooded_quarter()
    cast("dict[str, object]", a["metadata"])["production_eligible"] = False
    assert (
        cast("dict[str, object]", b["metadata"]).get("production_eligible") is not False
    )
    assert copy.deepcopy(a) is not a
