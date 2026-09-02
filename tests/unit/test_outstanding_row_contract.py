"""Pin the positional contract between the bulk query and ``_OutstandingRow``.

``api/approval.py`` builds its outstanding-decisions rows positionally
(``_OutstandingRow(*candidate)``) because a SQLAlchemy Core ``Row`` exposes the
COLUMN labels, not the names this module wants. That bridge is honest but
unguarded: the ``select()`` column order, the ``_CandidateRow`` type tuple, and
the ``_OutstandingRow`` field order are three separate lists that must stay
aligned, and six of the ten slots are ``str``-ish, so a reorder swaps values
without a type error and without a test failing anywhere else.

These tests fail the moment the three lists disagree.
"""

from __future__ import annotations

import ast
import datetime as datetime_module
import inspect
import uuid as uuid_module
from pathlib import Path
from typing import Any, ForwardRef, get_args, get_type_hints

from cyo_adventure.api import approval
from cyo_adventure.api.approval import _CandidateRow, _OutstandingRow

_SOURCE = Path(inspect.getfile(approval)).read_text(encoding="utf-8")

# approval.py imports uuid and datetime under `if TYPE_CHECKING`, so neither is
# in the module globals at runtime and both annotations are string forward
# references. Supply them explicitly rather than skipping resolution, which
# would leave the comparison below matching ForwardRef objects against real
# types and passing for the wrong reason.
_NAMESPACE: dict[str, Any] = {
    **vars(approval),
    "uuid": uuid_module,
    "datetime": datetime_module.datetime,
}


def _resolve(annotation: object) -> object:
    """Evaluate one annotation, string or not, in approval.py's namespace."""
    if isinstance(annotation, str):
        return eval(annotation, _NAMESPACE)  # noqa: S307
    if isinstance(annotation, ForwardRef):
        return eval(annotation.__forward_arg__, _NAMESPACE)  # noqa: S307
    return annotation


# The projection this contract pins, in select() order. Held here as a literal
# so that reordering two SAME-TYPED columns in approval.py (there are four
# `str | None`-ish slots, so a swap is silent) fails a test instead of quietly
# writing a title into `age_band`. Changing the query means consciously
# changing this list and `_OutstandingRow` together, which is the point.
_EXPECTED_PROJECTION = [
    "Storybook.id",
    "Storybook.status",
    "Storybook.family_id",
    "Storybook.current_published_version",
    "StorybookVersion.version",
    "StorybookVersion.blob['title'].as_string()",
    "StorybookVersion.blob['metadata']['age_band'].as_string()",
    "StorybookVersion.moderation_report",
    "StorybookVersion.cover_status",
    "StorybookVersion.created_at",
]


def _outstanding_select_columns() -> list[str]:
    """Return the outstanding-decisions select() columns, in order, as source.

    Located by AST rather than by grep: the module holds several ``select()``
    calls (this function alone builds two), so a substring probe over source
    text would match the wrong one and silently measure a different query.
    The anchor is the ``cast("list[_CandidateRow]", ...)`` wrapper, which is by
    definition the call whose column order this contract is about.
    """
    tree = ast.parse(_SOURCE)
    casts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "cast"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "list[_CandidateRow]"
    ]
    assert len(casts) == 1, (
        f"expected exactly one cast to list[_CandidateRow]; found {len(casts)}. "
        "Update this guard deliberately rather than loosening it."
    )
    selects = [
        inner
        for inner in ast.walk(casts[0])
        if isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id == "select"
    ]
    assert len(selects) == 1, (
        f"expected exactly one select() inside the cast; found {len(selects)}."
    )
    return [ast.unparse(arg) for arg in selects[0].args]


def test_candidate_tuple_and_row_fields_have_the_same_arity() -> None:
    assert len(_OutstandingRow._fields) == len(get_args(_CandidateRow))


def test_candidate_tuple_types_match_row_field_types_positionally() -> None:
    hints = get_type_hints(_OutstandingRow, globalns=_NAMESPACE)
    row_types = [hints[name] for name in _OutstandingRow._fields]
    candidate_types = [_resolve(arg) for arg in get_args(_CandidateRow)]
    assert row_types == candidate_types, (
        "_CandidateRow and _OutstandingRow drifted. The loop constructs the row "
        "positionally, so a mismatch here means a column is being read into the "
        "wrong field."
    )


def test_select_projects_the_expected_columns_in_row_field_order() -> None:
    assert _outstanding_select_columns() == _EXPECTED_PROJECTION, (
        "The bulk select() changed. _OutstandingRow is built positionally from "
        "it, so a reorder silently reassigns values between same-typed fields. "
        "Update _OutstandingRow and _CandidateRow to match, then update "
        "_EXPECTED_PROJECTION here."
    )


def test_expected_projection_and_row_fields_stay_the_same_length() -> None:
    assert len(_EXPECTED_PROJECTION) == len(_OutstandingRow._fields)
