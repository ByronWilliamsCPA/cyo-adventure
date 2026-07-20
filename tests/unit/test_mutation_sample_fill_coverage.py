"""Branch-coverage tests for the stage-5 sample fill (WS-5 D8 follow-up).

Targets the branches of ``mutation/sample_fill.py`` that
``test_mutation_sample_fill.py`` does not reach: the ``_mock_fill_document``
skips (non-list nodes, junk node entries, and non-FILL bodies), the
contract-less fill path, and the two non-clean note branches (a structural
block versus a fidelity-only downgrade). The two note branches are driven by
stubbing ``fill_skeleton`` with a deterministic outcome, since forcing a real
gate to block or downgrade on a clean skeleton is not deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from cyo_adventure.generation.orchestrator import GenerationOutcome
from cyo_adventure.generation.skeleton import FILL_MARKER
from cyo_adventure.mutation import sample_fill
from cyo_adventure.mutation.sample_fill import (
    _mock_fill_document,  # pyright: ignore[reportPrivateUsage]
    run_mock_sample_fill,
)

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"


def _cave() -> dict[str, object]:
    """Return the-cave-of-echoes skeleton as a raw document."""
    return cast(
        "dict[str, object]",
        json.loads(
            (_SKELETONS_ROOT / "8-11/the-cave-of-echoes.json").read_text(
                encoding="utf-8"
            )
        ),
    )


# --- _mock_fill_document skips ---


@pytest.mark.unit
def test_mock_fill_document_returns_unchanged_when_nodes_not_a_list() -> None:
    """A document whose ``nodes`` is not a list is returned unchanged."""
    document: dict[str, object] = {"nodes": "not-a-list"}
    assert _mock_fill_document(document) == document


@pytest.mark.unit
def test_mock_fill_document_skips_junk_and_non_fill_bodies() -> None:
    """Junk node entries and non-FILL bodies are left untouched; FILL is replaced."""
    document: dict[str, object] = {
        "nodes": [
            42,
            {"body": "plain prose with no directive"},
            {"body": f"{FILL_MARKER} role=body words=5 beats='x'>>"},
        ]
    }
    filled = _mock_fill_document(document)
    nodes = cast("list[object]", filled["nodes"])
    assert (
        cast("dict[str, object]", nodes[1])["body"] == "plain prose with no directive"
    )
    replaced = cast("str", cast("dict[str, object]", nodes[2])["body"])
    assert FILL_MARKER not in replaced


# --- The contract-less fill path ---


@pytest.mark.unit
def test_run_mock_sample_fill_contract_less_path_runs_the_free_text_fill() -> None:
    """A contract-less mutant fills via the default-theme path and records evidence."""
    result = run_mock_sample_fill(_cave(), contract=None)
    assert result.status in {"passed", "needs_review", "failed"}
    assert result.structurally_blocked is False


# --- The two non-clean note branches ---


def _stub_outcome(status: str, *, blocked: bool) -> GenerationOutcome:
    """Return a GenerationOutcome carrying a fixed status and gate-blocked flag."""
    return GenerationOutcome(
        status=status,  # pyright: ignore[reportArgumentType]
        storybook={"nodes": []},
        report={"blocked": blocked},
        attempts=0,
        stage_log=[],
    )


@pytest.mark.unit
def test_run_mock_sample_fill_flags_a_structural_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fill whose own gate blocks is recorded as a stage-5 structural discard."""

    async def _blocked_fill(*_args: object, **_kwargs: object) -> GenerationOutcome:
        return _stub_outcome("failed", blocked=True)

    monkeypatch.setattr(sample_fill, "fill_skeleton", _blocked_fill)
    result = run_mock_sample_fill(_cave(), contract=None)
    assert result.structurally_blocked is True
    assert "STRUCTURAL BLOCK" in result.note


@pytest.mark.unit
def test_run_mock_sample_fill_records_a_fidelity_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A needs_review fill without a blocked gate is recorded, not blocking."""

    async def _downgrade_fill(*_args: object, **_kwargs: object) -> GenerationOutcome:
        return _stub_outcome("needs_review", blocked=False)

    monkeypatch.setattr(sample_fill, "fill_skeleton", _downgrade_fill)
    result = run_mock_sample_fill(_cave(), contract=None)
    assert result.structurally_blocked is False
    assert result.fidelity_downgrade is True
    assert "fidelity downgrade" in result.note
