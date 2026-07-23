"""Unit tests for the mutation-operator framework (WS-5 D1, ops.py)."""

from __future__ import annotations

import random
from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.ops import (
    MutationOp,
    MutationResult,
    OpParams,
    OpRegistry,
    PreconditionReport,
    ReguideItem,
    ReguideTarget,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class _NoOp:
    """A minimal operator satisfying the ``MutationOp`` protocol for tests."""

    op_id = "noop"

    def preconditions(
        self, parent: Mapping[str, object], params: OpParams
    ) -> PreconditionReport:
        """Return a satisfied report unconditionally."""
        _ = (parent, params)
        return PreconditionReport.passed()

    def apply(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> MutationResult:
        """Return the parent unchanged as the candidate."""
        _ = (params, rng)
        return MutationResult(candidate=dict(parent))


@pytest.mark.unit
def test_op_params_of_orders_keys_canonically_for_determinism() -> None:
    """OpParams.of sorts keys so equal parameter sets compare and hash equal."""
    first = OpParams.of(seed=7, node="a", count=2)
    second = OpParams.of(count=2, node="a", seed=7)
    assert first == second
    assert hash(first) == hash(second)
    assert first.items == (("count", 2), ("node", "a"), ("seed", 7))


@pytest.mark.unit
def test_op_params_get_and_require_return_stored_values() -> None:
    """get returns a stored value or the default; mapping is a fresh dict."""
    params = OpParams.of(node="root", ratio=0.5)
    assert params.get("node") == "root"
    assert params.get("missing", "fallback") == "fallback"
    assert params.require("ratio") == 0.5
    assert params.mapping == {"node": "root", "ratio": 0.5}
    assert params.mapping is not params.mapping


@pytest.mark.unit
def test_op_params_require_missing_key_raises_validation_error() -> None:
    """require raises a project ValidationError when the key is absent."""
    params = OpParams.of(node="root")
    with pytest.raises(ValidationError):
        params.require("seed")


@pytest.mark.unit
def test_precondition_report_passed_is_satisfied_with_no_failures() -> None:
    """A passed report is satisfied and records only notes."""
    report = PreconditionReport.passed("a note")
    assert report.satisfied is True
    assert report.failures == ()
    assert report.notes == ("a note",)


@pytest.mark.unit
def test_precondition_report_failed_records_reasons() -> None:
    """A failed report is unsatisfied and carries every supplied reason."""
    report = PreconditionReport.failed("too deep", "cycle created")
    assert report.satisfied is False
    assert report.failures == ("too deep", "cycle created")


@pytest.mark.unit
def test_precondition_report_failed_without_reason_raises() -> None:
    """A failed report must explain itself, so an empty reason list raises."""
    with pytest.raises(ValidationError):
        PreconditionReport.failed()


@pytest.mark.unit
def test_reguide_item_and_result_are_frozen() -> None:
    """The value types are immutable, so a candidate cannot be edited in place."""
    item = ReguideItem(
        target=ReguideTarget.CHOICE, target_id="c1", reason="context changed"
    )
    result = MutationResult(candidate={"id": "story"}, reguide=(item,))
    with pytest.raises(FrozenInstanceError):
        item.reason = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.notes = ("x",)  # type: ignore[misc]


@pytest.mark.unit
def test_registry_registers_and_retrieves_by_op_id() -> None:
    """An operator registered under its op_id is retrievable and reported."""
    registry = OpRegistry()
    op = _NoOp()
    returned = registry.register(op)
    assert returned is op
    assert "noop" in registry
    assert registry.get("noop") is op
    assert registry.ids() == ("noop",)


@pytest.mark.unit
def test_registry_rejects_duplicate_op_id() -> None:
    """Registering the same op_id twice raises rather than shadowing."""
    registry = OpRegistry()
    registry.register(_NoOp())
    duplicate = _NoOp()
    with pytest.raises(ValidationError):
        registry.register(duplicate)


@pytest.mark.unit
def test_registry_get_unknown_op_id_raises() -> None:
    """Looking up an unregistered op_id raises a ValidationError."""
    registry = OpRegistry()
    with pytest.raises(ValidationError):
        registry.get("missing")


@pytest.mark.unit
def test_registry_rejects_blank_op_id() -> None:
    """An operator with a blank op_id cannot be registered."""
    registry = OpRegistry()

    class _Blank:
        op_id = ""

        def preconditions(
            self, parent: Mapping[str, object], params: OpParams
        ) -> PreconditionReport:
            _ = (parent, params)
            return PreconditionReport.passed()

        def apply(
            self, parent: Mapping[str, object], params: OpParams, rng: random.Random
        ) -> MutationResult:
            _ = (params, rng)
            return MutationResult(candidate=dict(parent))

    blank = _Blank()
    with pytest.raises(ValidationError):
        registry.register(blank)


@pytest.mark.unit
def test_noop_satisfies_runtime_checkable_protocol() -> None:
    """The test operator is recognized as a MutationOp at runtime."""
    op = _NoOp()
    assert isinstance(op, MutationOp)
    result = op.apply({"id": "s"}, OpParams(), random.Random(0))
    assert result.candidate == {"id": "s"}
