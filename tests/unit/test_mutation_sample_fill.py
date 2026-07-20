"""Tests for the WS-5 D8 stage-5 sample fill (mutation/sample_fill.py).

Covers the deterministic mock fill on a real skeleton (a structurally clean fill
whose own gate does not block), the skipped-result path, and the classification of
a structural block vs a fidelity-only downgrade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from cyo_adventure.mutation.sample_fill import (
    _classify,  # pyright: ignore[reportPrivateUsage]
    _mock_fill_document,  # pyright: ignore[reportPrivateUsage]
    run_mock_sample_fill,
    skipped_result,
)
from cyo_adventure.storybook.theme_contract import ThemeContract

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_CAVE = "8-11/the-cave-of-echoes.json"


def _load(slug_path: str) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        json.loads((_SKELETONS_ROOT / slug_path).read_text(encoding="utf-8")),
    )


@pytest.mark.unit
def test_mock_fill_replaces_fill_directives() -> None:
    """The mock filler replaces every FILL body with plain prose (no directives)."""
    skeleton = _load(_CAVE)
    filled = _mock_fill_document(skeleton)
    nodes = filled["nodes"]
    assert isinstance(nodes, list)
    bodies = [
        cast("dict[str, object]", n).get("body") for n in nodes if isinstance(n, dict)
    ]
    assert all(not (isinstance(b, str) and b.startswith("<<FILL")) for b in bodies)


@pytest.mark.unit
def test_run_mock_sample_fill_passes_on_real_skeleton() -> None:
    """A mock fill of a real parameterized skeleton is structurally clean."""
    candidate = _load(_CAVE)
    contract = ThemeContract.model_validate_json(
        (_SKELETONS_ROOT / "8-11/the-cave-of-echoes.contract.json").read_text(
            encoding="utf-8"
        )
    )
    result = run_mock_sample_fill(candidate, contract=contract)
    assert result.structurally_blocked is False
    assert result.status in {"passed", "needs_review"}
    assert result.filled is not None


@pytest.mark.unit
def test_skipped_result_records_reason() -> None:
    """skipped_result carries the skip reason and no gate evidence."""
    result = skipped_result("no provider")
    assert result.status == "skipped"
    assert result.structurally_blocked is False
    assert result.filled is None
    assert "no provider" in result.note


@pytest.mark.unit
def test_classify_distinguishes_block_from_downgrade() -> None:
    """A blocked gate is structural; a needs_review without block is fidelity."""
    blocked, downgrade = _classify("needs_review", {"blocked": True})
    assert blocked is True
    assert downgrade is False
    blocked, downgrade = _classify("needs_review", {"blocked": False})
    assert blocked is False
    assert downgrade is True
    blocked, downgrade = _classify("passed", {"blocked": False})
    assert (blocked, downgrade) == (False, False)
