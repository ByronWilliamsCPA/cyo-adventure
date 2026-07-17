# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Unit tests for the fuzz-harness check logic (fuzz/fuzz_*.py).

The harnesses' check functions are importable without atheris precisely so
this suite can prove, on every CI run, that the contracts they fuzz hold on
the curated corpora: the conformance conditions, the valid storybook
fixtures, and every invalid schema fixture. A weekly ClusterFuzzLite run
then explores beyond the corpus; these tests guarantee the harness itself
is wired to real project code (the previous template harness fuzzed nothing
and stayed green for weeks).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fuzz.fuzz_condition_evaluator import check_condition_text
from fuzz.fuzz_condition_evaluator import test_one_input as _condition_entry_point
from fuzz.fuzz_storybook_validation import check_storybook_text

_ROOT = Path(__file__).resolve().parents[2]
_CONFORMANCE = _ROOT / "schema" / "conformance" / "conditions.json"
_VALID_BOOKS = sorted(
    (_ROOT / "tests" / "fixtures" / "storybook" / "valid").glob("*.json")
)
_INVALID_SCHEMA_BOOKS = sorted(
    (_ROOT / "tests" / "fixtures" / "storybook" / "invalid" / "schema").glob("*.json")
)


def _conformance_conditions() -> list[str]:
    """Load every conformance condition as JSON text."""
    cases: list[dict[str, Any]] = json.loads(_CONFORMANCE.read_text(encoding="utf-8"))[
        "cases"
    ]
    return [json.dumps(case["condition"]) for case in cases]


@pytest.mark.unit
@pytest.mark.parametrize("condition_text", _conformance_conditions())
def test_condition_harness_accepts_every_conformance_case(
    condition_text: str,
) -> None:
    """Every conformance condition passes the harness contract silently."""
    check_condition_text(condition_text)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json at all",
        "[1, 2, 3]",
        '{"nope": []}',
        '{"==": [1]}',
        '{"var": 7}',
        '{"<": [true, 1]}',
        '{"and": []}',
        "{" * 500 + "}" * 500,
        # NUL and lone-surrogate payloads, built with chr() so the test
        # source itself stays valid UTF-8 without raw control bytes.
        '{"var": "' + chr(0) + '"}',
        '{"var": "' + chr(0xD800) + '"}',
    ],
)
def test_condition_harness_never_raises_on_malformed_input(text: str) -> None:
    """Malformed, non-dict, and hostile inputs return without raising."""
    check_condition_text(text)


@pytest.mark.unit
def test_condition_harness_entry_point_handles_arbitrary_bytes() -> None:
    """The atheris entry point tolerates invalid UTF-8 byte input."""
    _condition_entry_point(b"\xff\xfe{\x00}")
    _condition_entry_point(b'{"var": "a"}')


@pytest.mark.unit
@pytest.mark.parametrize("fixture", _VALID_BOOKS, ids=lambda path: str(path.stem))
def test_storybook_harness_accepts_every_valid_fixture(fixture: Path) -> None:
    """Every valid corpus storybook passes the harness contract silently."""
    check_storybook_text(fixture.read_text(encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.parametrize(
    "fixture", _INVALID_SCHEMA_BOOKS, ids=lambda path: str(path.stem)
)
def test_storybook_harness_rejects_every_invalid_schema_fixture(
    fixture: Path,
) -> None:
    """Every invalid-schema fixture is rejected without a non-ValidationError."""
    check_storybook_text(fixture.read_text(encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    ["", "null", "true", "42", '"str"', "[]", "{}", '{"id": 1}', "{" * 400],
)
def test_storybook_harness_never_raises_on_malformed_input(text: str) -> None:
    """Malformed and non-dict storybook inputs return without raising."""
    check_storybook_text(text)


@pytest.mark.unit
def test_fixture_corpora_are_nonempty() -> None:
    """The seed corpora the harnesses rely on exist and are populated."""
    assert len(_conformance_conditions()) >= 10
    assert len(_VALID_BOOKS) >= 5
    assert len(_INVALID_SCHEMA_BOOKS) >= 5
