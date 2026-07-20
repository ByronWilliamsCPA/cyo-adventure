"""Shared mutation-operator framework: protocol, result types, registry.

WS-5 D1 (design section 4.1). This module defines the contract every mutation
operator (M1-M5, delivered in D2 and later) implements, the immutable value
types an operator returns, and a small registry so operators can be looked up
by their stable ``op_id``.

Pure module: standard library plus the project exception hierarchy only. It
imports nothing from ``db``, ``generation``, ``validator``, or ``network``
surfaces, so it can be reused by both the (future) CLI and the acceptance
harness without any layering inversion, mirroring the discipline of
``storybook/theme_contract.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cyo_adventure.core.exceptions import ValidationError

if TYPE_CHECKING:
    import random
    from collections.abc import Mapping

# The JSON-scalar value types an operator accepts as a parameter. Operator
# parameters are reviewer-supplied and recorded verbatim in the lineage
# manifest (design section 9.2), so they are restricted to values that round
# trip through JSON without loss.
ParamValue = str | int | float | bool | None


class ReguideTarget(StrEnum):
    """What kind of surface a :class:`ReguideItem` points at."""

    NODE = "node"
    CHOICE = "choice"
    ENDING = "ending"


@dataclass(frozen=True, slots=True)
class ReguideItem:
    """One node, choice, or ending whose guidance a mutation invalidated.

    A structural move changes the context an entry-beat or a choice label
    describes, so the affected surfaces must be re-authored before the mutant
    is promotable (design sections 4.2-4.5). D1 defines the record; the
    operators that emit it arrive in D2 and later.

    Attributes:
        target: The kind of surface that needs re-authoring.
        target_id: The node, choice, or ending id the item refers to.
        reason: A short, human-readable explanation of why re-guidance is
            needed (audit and reviewer context).
        current_text: The surface's text before the mutation, when the
            operator can supply it; empty otherwise.
    """

    target: ReguideTarget
    target_id: str
    reason: str
    current_text: str = ""


@dataclass(frozen=True, slots=True)
class PreconditionReport:
    """The outcome of an operator's precondition check for a candidate.

    A satisfied report means the operator may attempt ``apply``; an
    unsatisfied report carries the grammar-stated reasons the attempt would be
    wasted (design section 6, stage 0), and the caller discards without
    spending a gate run.

    Attributes:
        satisfied: Whether every precondition holds.
        failures: The reasons the check failed; empty when satisfied.
        notes: Optional advisory notes recorded regardless of outcome.
    """

    satisfied: bool
    failures: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @classmethod
    def passed(cls, *notes: str) -> PreconditionReport:
        """Return a satisfied report with optional advisory notes.

        Args:
            *notes: Advisory notes to record.

        Returns:
            PreconditionReport: A satisfied report.
        """
        return cls(satisfied=True, failures=(), notes=notes)

    @classmethod
    def failed(cls, *failures: str) -> PreconditionReport:
        """Return an unsatisfied report carrying at least one reason.

        Args:
            *failures: One or more reasons the precondition check failed.

        Returns:
            PreconditionReport: An unsatisfied report.

        Raises:
            ValidationError: If no failure reason is supplied (an unsatisfied
                report must explain itself, so a discard is always auditable).
        """
        if not failures:
            msg = "a failed PreconditionReport must carry at least one failure reason"
            raise ValidationError(msg, field="failures", value=None)
        return cls(satisfied=False, failures=failures)


@dataclass(frozen=True, slots=True)
class OpParams:
    """Immutable, JSON-round-trippable operator parameters.

    Parameters are stored as a canonically ordered tuple of ``(key, value)``
    pairs so two equal parameter sets are equal and hashable, and so the
    lineage manifest records them deterministically (design section 3,
    principle 5). Build one with :meth:`of` for keyword ergonomics.

    Attributes:
        items: The canonically ordered ``(key, value)`` pairs.
    """

    items: tuple[tuple[str, ParamValue], ...] = ()

    @classmethod
    def of(cls, **values: ParamValue) -> OpParams:
        """Build parameters from keyword arguments, in canonical key order.

        Args:
            **values: The named parameter values.

        Returns:
            OpParams: The immutable, key-sorted parameter set.
        """
        return cls(items=tuple(sorted(values.items())))

    @property
    def mapping(self) -> dict[str, ParamValue]:
        """Return the parameters as a plain dict (a fresh copy each call)."""
        return dict(self.items)

    def get(self, key: str, default: ParamValue = None) -> ParamValue:
        """Return the value for ``key``, or ``default`` when absent.

        Args:
            key: The parameter name.
            default: The value to return when ``key`` is not present.

        Returns:
            ParamValue: The stored value, or ``default``.
        """
        for stored_key, value in self.items:
            if stored_key == key:
                return value
        return default

    def require(self, key: str) -> ParamValue:
        """Return the value for ``key`` or raise when it is absent.

        Args:
            key: The parameter name.

        Returns:
            ParamValue: The stored value.

        Raises:
            ValidationError: If ``key`` is not present.
        """
        for stored_key, value in self.items:
            if stored_key == key:
                return value
        msg = f"required operator parameter '{key}' is missing"
        raise ValidationError(msg, field=key, value=None)


@dataclass(frozen=True, slots=True)
class MutationResult:
    """The product of one operator ``apply`` call.

    Attributes:
        candidate: The mutated skeleton shell as a raw dict, with ids and
            metadata already resynced (see :mod:`cyo_adventure.mutation.identity`).
            The value is a fresh document; the operator never mutates its input.
        reguide: The surfaces whose guidance the mutation invalidated. The
            bundle is not promotable while any item is unresolved (design
            section 4.5).
        notes: Operator-specific audit notes.
    """

    candidate: dict[str, object]
    reguide: tuple[ReguideItem, ...] = ()
    notes: tuple[str, ...] = ()


@runtime_checkable
class MutationOp(Protocol):
    """The contract every WS-5 mutation operator implements.

    An operator is a pure function of ``(parent, params, rng)``: given the same
    inputs it produces byte-identical output, so any promoted mutant can be
    re-derived and re-verified (design section 3, principle 5). Concrete
    operators are delivered from D2 onward; D1 defines only this protocol.

    Attributes:
        op_id: The operator's stable identifier, recorded in every lineage
            manifest and used as the registry key.
    """

    op_id: str

    def preconditions(
        self, parent: Mapping[str, object], params: OpParams
    ) -> PreconditionReport:
        """Return whether the operator may attempt this mutation.

        Args:
            parent: The parent skeleton shell.
            params: The operator parameters.

        Returns:
            PreconditionReport: A satisfied or unsatisfied report.
        """
        ...

    def apply(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> MutationResult:
        """Apply the mutation and return the resynced candidate.

        Args:
            parent: The parent skeleton shell.
            params: The operator parameters.
            rng: An injected random source, so a recorded seed reproduces the
                exact candidate.

        Returns:
            MutationResult: The mutated candidate plus its re-guidance list.
        """
        ...


class OpRegistry:
    """A collection of mutation operators keyed by ``op_id``.

    The registry is an ordinary object rather than a module global so tests
    (and any future multi-catalog tooling) can build an isolated instance
    without leaking registrations across cases. A module-level default,
    :data:`REGISTRY`, is provided for the common single-catalog use.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._ops: dict[str, MutationOp] = {}

    def register(self, op: MutationOp) -> MutationOp:
        """Register an operator under its ``op_id``.

        Args:
            op: The operator to register.

        Returns:
            MutationOp: The same operator, so this can be used as a decorator.

        Raises:
            ValidationError: If ``op.op_id`` is blank or already registered.
        """
        op_id = op.op_id
        if not op_id:
            msg = "cannot register an operator with a blank op_id"
            raise ValidationError(msg, field="op_id", value=op_id)
        if op_id in self._ops:
            msg = f"operator id '{op_id}' is already registered"
            raise ValidationError(msg, field="op_id", value=op_id)
        self._ops[op_id] = op
        return op

    def get(self, op_id: str) -> MutationOp:
        """Return the operator registered under ``op_id``.

        Args:
            op_id: The operator identifier.

        Returns:
            MutationOp: The registered operator.

        Raises:
            ValidationError: If no operator is registered under ``op_id``.
        """
        op = self._ops.get(op_id)
        if op is None:
            msg = f"no operator registered under id '{op_id}'"
            raise ValidationError(msg, field="op_id", value=op_id)
        return op

    def ids(self) -> tuple[str, ...]:
        """Return every registered ``op_id``, sorted."""
        return tuple(sorted(self._ops))

    def __contains__(self, op_id: str) -> bool:
        """Return whether an operator is registered under ``op_id``."""
        return op_id in self._ops


# The default single-catalog registry. Operators (D2 onward) register here.
REGISTRY = OpRegistry()
