"""Tests for the WS-5 D2 acceptance harness (mutation/acceptance.py).

Covers the section 6 stage table subset: stage-0 precondition discard, stage-1
gate discard (including the load-bearing safety property that a blocked gate can
never be promotable), stage-2 cell-drift discard, and the held-for-re-guidance
outcome. Also pins the structured discard log and the serialization used by the
CLI.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.mutation.acceptance import (
    Stage,
    _cell_matches,  # pyright: ignore[reportPrivateUsage]
    acceptance_to_dict,
    run_acceptance,
)
from cyo_adventure.mutation.operators import M1
from cyo_adventure.mutation.ops import (
    MutationResult,
    OpParams,
    PreconditionReport,
    ReguideItem,
    ReguideTarget,
)
from cyo_adventure.validator.gate import GateResult
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)

if TYPE_CHECKING:
    import random
    from collections.abc import Mapping

    from structlog.stdlib import BoundLogger

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"


def _load(slug_path: str) -> dict[str, object]:
    """Load one catalog skeleton by its ``band/slug.json`` path."""
    return cast(
        "dict[str, object]",
        json.loads((_SKELETONS_ROOT / slug_path).read_text(encoding="utf-8")),
    )


def _first_eligible_tier1() -> tuple[str, dict[str, object]]:
    """Return the first production Tier-1 standalone skeleton M1 accepts."""
    for path in sorted(_SKELETONS_ROOT.glob("*/*.json")):
        if path.name.endswith(".contract.json"):
            continue
        story = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        if M1.preconditions(story, OpParams.of()).satisfied:
            return path.stem, story
    pytest.skip("no eligible Tier-1 parent in the catalog")


class _RecordingLogger:
    """A minimal structlog-shaped logger that records ``info`` calls."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **kwargs: object) -> None:
        """Record one structured event."""
        self.events.append((event, kwargs))


class _ConstOp:
    """An operator stub whose apply returns a fixed candidate (for stage tests)."""

    def __init__(
        self,
        op_id: str,
        candidate: dict[str, object],
        reguide: tuple[ReguideItem, ...] = (),
        *,
        satisfied: bool = True,
    ) -> None:
        self.op_id = op_id
        self._candidate = candidate
        self._reguide = reguide
        self._satisfied = satisfied

    def preconditions(
        self, parent: Mapping[str, object], params: OpParams
    ) -> PreconditionReport:
        """Return the configured precondition outcome."""
        _ = (parent, params)
        return (
            PreconditionReport.passed()
            if self._satisfied
            else PreconditionReport.failed("stub precondition refused")
        )

    def apply(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> MutationResult:
        """Return the fixed candidate, unconditionally."""
        _ = (parent, params, rng)
        return MutationResult(
            candidate=copy.deepcopy(self._candidate), reguide=self._reguide
        )


def _blocking_gate(_data: Mapping[str, object], scale: str = "standard") -> GateResult:
    """Return a gate result that always blocks (a forced-failure double)."""
    _ = scale
    report = ValidationReport()
    report.add(
        ValidationFinding(
            rule_id="L1-3",
            severity=Severity.ERROR,
            story_id="forced",
            message="forced block for the safety property test",
        )
    )
    return GateResult(report=report, blocked=True, safety_flagged=False)


@pytest.mark.unit
def test_accepted_m1_candidate_is_held_not_promotable() -> None:
    """An accepted M1 mutant clears stages 0-2 but is held on unresolved reguide."""
    _slug, story = _first_eligible_tier1()
    result = run_acceptance(M1, story, OpParams.of(), seed=0, parent_slug=_slug)
    assert result.discarded_at_stage is None
    assert [outcome.passed for outcome in result.stages] == [True, True, True]
    assert result.reguide_outstanding == 4
    assert result.promotable is False
    assert result.held is True
    assert result.gate_summary["blocked"] is False


@pytest.mark.unit
def test_resolving_all_reguide_items_makes_the_candidate_promotable() -> None:
    """Marking every reguide target resolved flips a held candidate to promotable."""
    _slug, story = _first_eligible_tier1()
    dry = run_acceptance(M1, story, OpParams.of(), seed=0, parent_slug=_slug)
    resolved = frozenset(item.target_id for item in dry.reguide)
    result = run_acceptance(
        M1,
        story,
        OpParams.of(),
        seed=0,
        parent_slug=_slug,
        resolved_reguide_ids=resolved,
    )
    assert result.reguide_outstanding == 0
    assert result.promotable is True
    assert result.held is False


@pytest.mark.unit
@pytest.mark.security
def test_harness_cannot_promote_a_blocked_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The safety invariant: a blocked gate is never promotable (design CR-2)."""
    monkeypatch.setattr("cyo_adventure.mutation.acceptance.run_gate", _blocking_gate)
    _slug, story = _first_eligible_tier1()
    result = run_acceptance(M1, story, OpParams.of(), seed=0, parent_slug=_slug)
    assert result.discarded_at_stage is Stage.GATE
    assert result.promotable is False
    assert result.held is False
    assert result.gate_summary["blocked"] is True
    gate_stage = next(o for o in result.stages if o.stage is Stage.GATE)
    assert "L1-3" in gate_stage.rule_ids


@pytest.mark.unit
def test_precondition_failure_discards_at_stage_zero() -> None:
    """A stub whose preconditions refuse is discarded at stage 0 with no candidate."""
    _slug, story = _first_eligible_tier1()
    op = _ConstOp("stub-refuse", story, satisfied=False)
    result = run_acceptance(op, story, OpParams.of(), seed=0, parent_slug=_slug)
    assert result.discarded_at_stage is Stage.PRECONDITIONS
    assert result.candidate is None
    assert result.promotable is False


@pytest.mark.unit
def test_cell_drift_discards_at_stage_two() -> None:
    """A gate-passing candidate that declares a different cell is discarded at stage 2."""
    parent = _load("8-11/the-cave-of-echoes.json")
    donor = _load("3-5/the-big-red-balloon.json")  # different band/cell, gate-valid
    op = _ConstOp("stub-cell", donor)
    result = run_acceptance(op, parent, OpParams.of(), seed=0, parent_slug="cave")
    assert result.discarded_at_stage is Stage.CELL
    assert result.gate_summary["blocked"] is False
    assert result.promotable is False


@pytest.mark.unit
def test_discard_emits_structured_mutation_discarded_log() -> None:
    """A discard emits one ``mutation.discarded`` event with the required fields."""
    _slug, story = _first_eligible_tier1()
    op = _ConstOp("stub-refuse", story, satisfied=False)
    logger = _RecordingLogger()
    run_acceptance(
        op,
        story,
        OpParams.of(foo="bar"),
        seed=3,
        parent_slug="parent-x",
        logger=cast("BoundLogger", logger),
    )
    assert len(logger.events) == 1
    event, fields = logger.events[0]
    assert event == "mutation.discarded"
    assert fields["parent_slug"] == "parent-x"
    assert fields["op_id"] == "stub-refuse"
    assert fields["seed"] == 3
    assert fields["failing_stage"] == str(Stage.PRECONDITIONS)
    assert "parent_sha256" in fields
    assert fields["params"] == {"foo": "bar"}


@pytest.mark.unit
def test_cell_matches_direct() -> None:
    """The cell comparison flags the first differing key and accepts equal cells."""
    parent = _load("8-11/the-cave-of-echoes.json")
    same = copy.deepcopy(parent)
    ok, _detail = _cell_matches(parent, same)
    assert ok is True
    drifted = copy.deepcopy(parent)
    cast("dict[str, object]", drifted["metadata"])["length"] = "long"
    bad, detail = _cell_matches(parent, drifted)
    assert bad is False
    assert "length" in detail


@pytest.mark.unit
def test_acceptance_to_dict_is_json_serializable_and_complete() -> None:
    """The CLI serialization round-trips and records the D2 stage transcript."""
    _slug, story = _first_eligible_tier1()
    result = run_acceptance(M1, story, OpParams.of(), seed=0, parent_slug=_slug)
    payload = acceptance_to_dict(result)
    # Round-trips through JSON without error.
    reloaded = cast("dict[str, object]", json.loads(json.dumps(payload)))
    assert reloaded["promotable"] is False
    assert reloaded["held"] is True
    assert len(cast("list[object]", reloaded["stages"])) == 3
    assert len(cast("list[object]", reloaded["reguide"])) == 4
    assert reloaded["discarded_at_stage"] is None
    assert "bundle_note" in reloaded


@pytest.mark.unit
def test_reguide_items_reference_the_swapped_surfaces() -> None:
    """The held candidate's reguide list is two choices then two nodes."""
    _slug, story = _first_eligible_tier1()
    result = run_acceptance(M1, story, OpParams.of(), seed=0, parent_slug=_slug)
    kinds = [item.target for item in result.reguide]
    assert kinds.count(ReguideTarget.CHOICE) == 2
    assert kinds.count(ReguideTarget.NODE) == 2


# --- CLI: scripts/mutate_skeleton.py ---


def _eligible_parent_path() -> Path:
    """Return the filesystem path of an eligible Tier-1 parent for the CLI."""
    for path in sorted(_SKELETONS_ROOT.glob("*/*.json")):
        if path.name.endswith(".contract.json"):
            continue
        story = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        if M1.preconditions(story, OpParams.of()).satisfied:
            return path
    pytest.skip("no eligible Tier-1 parent in the catalog")


@pytest.mark.unit
@pytest.mark.security
def test_cli_refuses_out_dir_under_skeletons(tmp_path: Path) -> None:
    """The CLI refuses to write under skeletons/ and creates nothing there."""
    from scripts import mutate_skeleton as ms

    parent = _eligible_parent_path()
    forbidden = _SKELETONS_ROOT / "mutation-should-not-appear-here"
    exit_code = ms.main(
        [str(parent), "--op", "M1", "--seed", "0", "--out-dir", str(forbidden)]
    )
    assert exit_code == 1
    assert not forbidden.exists()


@pytest.mark.unit
def test_cli_success_writes_a_minimal_bundle(tmp_path: Path) -> None:
    """A successful run writes the candidate shell and acceptance.json, exit 0."""
    from scripts import mutate_skeleton as ms

    parent = _eligible_parent_path()
    exit_code = ms.main(
        [str(parent), "--op", "M1", "--seed", "0", "--out-dir", str(tmp_path)]
    )
    assert exit_code == 0
    slug = f"{parent.stem}-m1-s0"
    bundle = tmp_path / slug
    assert (bundle / f"{slug}.json").is_file()
    acceptance = cast(
        "dict[str, object]",
        json.loads((bundle / "acceptance.json").read_text(encoding="utf-8")),
    )
    # Held, not promotable (reguide outstanding), and never gate-blocked.
    assert acceptance["promotable"] is False
    assert acceptance["held"] is True
    assert acceptance["discarded_at_stage"] is None


@pytest.mark.unit
def test_cli_precondition_failure_exits_nonzero_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """An ineligible swap (same choice twice) discards and writes no bundle."""
    from scripts import mutate_skeleton as ms

    parent = _eligible_parent_path()
    story = cast("dict[str, object]", json.loads(parent.read_text(encoding="utf-8")))
    # Pick any real choice id and pass it as both, forcing a stage-0 discard.
    choice_id = _any_choice_id(story)
    exit_code = ms.main(
        [
            str(parent),
            "--op",
            "M1",
            "--params",
            f"choice1={choice_id}",
            f"choice2={choice_id}",
            "--out-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
def test_cli_unknown_operator_exits_nonzero(tmp_path: Path) -> None:
    """An unregistered operator id exits non-zero and writes nothing."""
    from scripts import mutate_skeleton as ms

    parent = _eligible_parent_path()
    exit_code = ms.main(
        [str(parent), "--op", "does-not-exist", "--out-dir", str(tmp_path)]
    )
    assert exit_code == 1
    assert list(tmp_path.iterdir()) == []


def _any_choice_id(story: dict[str, object]) -> str:
    """Return the first choice id found in a story."""
    for node in cast("list[object]", story["nodes"]):
        if not isinstance(node, dict):
            continue
        choices = cast("dict[str, object]", node).get("choices")
        if isinstance(choices, list):
            for choice in cast("list[object]", choices):
                if isinstance(choice, dict):
                    choice_id = cast("dict[str, object]", choice).get("id")
                    if isinstance(choice_id, str):
                        return choice_id
    pytest.skip("no choices in the chosen parent")
