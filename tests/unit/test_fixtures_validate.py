"""Parametrized corpus tests for the Storybook fixture files.

Each sub-directory of ``tests/fixtures/storybook/`` contains a well-labelled
corpus:

* ``valid/``          -- stories that must parse without error.
* ``invalid/schema/`` -- stories that must raise ``ValidationError``
  (exactly one schema rule violated per file).
* ``invalid/graph/``  -- stories that must *parse* successfully
  (schema-valid) but contain graph-level defects.  A Phase-1 graph
  validator will reject them; the Pydantic schema does not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cyo_adventure.storybook import Storybook

FIXTURES_ROOT: Path = Path(__file__).resolve().parents[1] / "fixtures" / "storybook"

_VALID_DIR: Path = FIXTURES_ROOT / "valid"
_SCHEMA_INVALID_DIR: Path = FIXTURES_ROOT / "invalid" / "schema"
_GRAPH_INVALID_DIR: Path = FIXTURES_ROOT / "invalid" / "graph"


def _collect(directory: Path) -> list[Path]:
    """Return sorted JSON fixture paths from *directory*.

    Args:
        directory: The directory to search.

    Returns:
        Sorted list of ``*.json`` Path objects.
    """
    return sorted(directory.glob("*.json"))


_VALID_FIXTURES: list[Path] = _collect(_VALID_DIR)
_SCHEMA_INVALID_FIXTURES: list[Path] = _collect(_SCHEMA_INVALID_DIR)
_GRAPH_INVALID_FIXTURES: list[Path] = _collect(_GRAPH_INVALID_DIR)


@pytest.mark.unit
@pytest.mark.parametrize("fixture_path", _VALID_FIXTURES, ids=lambda p: p.name)
def test_valid_fixture_parses_without_error(fixture_path: Path) -> None:
    """Every file in valid/ must be accepted by ``Storybook.model_validate``.

    Args:
        fixture_path: Path to a JSON fixture under ``valid/``.
    """
    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    book = Storybook.model_validate(data)

    assert book.id == data["id"]


@pytest.mark.unit
@pytest.mark.parametrize("fixture_path", _SCHEMA_INVALID_FIXTURES, ids=lambda p: p.name)
def test_schema_invalid_fixture_raises_validation_error(fixture_path: Path) -> None:
    """Every file in invalid/schema/ must raise ``ValidationError`` on parse.

    Each filename encodes the single rule it violates (e.g.
    ``duplicate_node_id.json``).

    Args:
        fixture_path: Path to a JSON fixture under ``invalid/schema/``.
    """
    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    with pytest.raises(ValidationError):
        Storybook.model_validate(data)


@pytest.mark.unit
@pytest.mark.parametrize("fixture_path", _GRAPH_INVALID_FIXTURES, ids=lambda p: p.name)
def test_graph_invalid_fixture_parses_successfully(fixture_path: Path) -> None:
    """Every file in invalid/graph/ must *parse* without error.

    These fixtures are schema-valid: the Pydantic model accepts them.
    A Phase-1 graph validator (Layer 1/2 rules from validator-rules.md)
    will reject them; that is out of scope for the schema layer.

    Args:
        fixture_path: Path to a JSON fixture under ``invalid/graph/``.
    """
    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    # Phase 1 graph validation will reject these; schema does not.
    book = Storybook.model_validate(data)

    assert book.id == data["id"]


@pytest.mark.unit
def test_fixture_corpus_has_minimum_coverage() -> None:
    """Assert the fixture corpus meets the required minimum counts.

    Ensures that future deletions are caught immediately.
    """
    assert len(_VALID_FIXTURES) >= 5, (
        f"Expected >= 5 valid fixtures, found {len(_VALID_FIXTURES)}"
    )
    assert len(_SCHEMA_INVALID_FIXTURES) + len(_GRAPH_INVALID_FIXTURES) >= 10, (
        f"Expected >= 10 invalid fixtures total, "
        f"found {len(_SCHEMA_INVALID_FIXTURES)} schema + "
        f"{len(_GRAPH_INVALID_FIXTURES)} graph"
    )
