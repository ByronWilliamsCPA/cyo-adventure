# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Performance regression guards for the condition evaluator (read hot path).

The evaluator runs on every conditioned choice a reader encounters, and the
TypeScript client player mirrors it, so an accidental super-linear regression
would surface as laggy reading and as a slow catalog validation pass. These
tests pin its complexity class with generous absolute budgets: they fail on a
quadratic or exponential regression, not on ordinary shared-runner jitter.

They are the in-process complement to the Phase 9 deployment load test (P9-13),
which measures API, DB-connection, and generation-worker capacity under
multi-family load against hosted infra; that is out of scope here.

Opt-in: skipped unless ``CYO_RUN_PERF=1`` (set by .github/workflows/perf.yml),
so this tier never runs on the PR path.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

import pytest

from cyo_adventure.storybook.condition import validate_condition
from cyo_adventure.storybook.evaluator import evaluate

if TYPE_CHECKING:
    from cyo_adventure.storybook.evaluator import VarState

pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(
        os.environ.get("CYO_RUN_PERF") != "1",
        reason="performance tests are opt-in (CYO_RUN_PERF=1); off the PR path",
    ),
]

_VAR_STATE: VarState = {"a": 3, "b": 1, "courage": 4, "trust": 0}


def _wide_and(width: int) -> dict[str, Any]:
    """A flat AND of ``width`` comparisons: shape-valid and O(width) to evaluate."""
    return {"and": [{">": [{"var": "a"}, i % 5]} for i in range(width)]}


def _nested_condition(depth: int) -> dict[str, Any]:
    """A negation chain ``depth`` deep over a comparison (well within the cap)."""
    node: dict[str, Any] = {">": [{"var": "courage"}, 2]}
    for _ in range(depth):
        node = {"!": node}
    return node


def test_evaluator_wide_condition_stays_linear() -> None:
    """A very wide flat condition evaluates far under a generous linear budget.

    O(width) is milliseconds; a quadratic regression would blow well past 2s.
    """
    condition = _wide_and(100_000)
    start = time.perf_counter()
    result = evaluate(condition, _VAR_STATE)
    elapsed = time.perf_counter() - start
    assert isinstance(result, bool)
    assert elapsed < 2.0, f"wide-condition eval took {elapsed:.3f}s (expected << 2s)"


def test_evaluator_batch_throughput_is_bounded() -> None:
    """Evaluating a nested gate many times stays within a generous budget.

    Simulates the aggregate cost of a read session or catalog validation pass
    that evaluates a non-trivial choice-gate across many nodes.
    """
    condition = _nested_condition(8)
    validate_condition(condition)  # confirm it is a legal (shape-valid) gate
    iterations = 50_000
    start = time.perf_counter()
    for _ in range(iterations):
        evaluate(condition, _VAR_STATE)
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, (
        f"{iterations} nested-gate evals took {elapsed:.3f}s (expected << 3s)"
    )
