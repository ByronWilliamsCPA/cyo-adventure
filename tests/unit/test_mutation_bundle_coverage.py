"""Branch-coverage tests for defensive paths in ``mutation/bundle.py`` (WS-5 D8).

Targets the malformed-candidate skips in the slot-token scan, the unresolved
graft-token raise in ``derive_mutant_contract``, the optional sample-fill/diagram
branches of ``write_bundle``, and the missing-lineage failure in ``verify_bundle``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.bundle import (
    OpChainEntry,
    _candidate_slot_tokens,  # pyright: ignore[reportPrivateUsage]
    build_lineage,
    derive_mutant_contract,
    verify_bundle,
    write_bundle,
)
from cyo_adventure.storybook.theme_contract import ThemeContract

if TYPE_CHECKING:
    from pathlib import Path


def _host_contract() -> ThemeContract:
    """Return a minimal one-slot host contract for the derive tests."""
    return ThemeContract.model_validate(
        {
            "contract_version": 1,
            "skeleton_slug": "host",
            "age_band": "8-11",
            "default_binding": {"HERO": "a fox"},
            "slots": [
                {"id": "HERO", "scope": "global", "meaning": "hero", "guidance": ""}
            ],
        }
    )


@pytest.mark.unit
def test_candidate_slot_tokens_returns_early_when_nodes_is_not_a_list() -> None:
    """A candidate whose ``nodes`` is not a list references no slot tokens."""
    assert _candidate_slot_tokens({"nodes": "not-a-list"}) == frozenset()


@pytest.mark.unit
def test_candidate_slot_tokens_skips_malformed_surfaces() -> None:
    """Non-dict nodes/choices and non-string body/title/label are all skipped."""
    candidate = {
        "nodes": [
            "not-a-node",
            {
                "id": "n",
                "body": 5,  # non-string body
                "ending": {"title": 9},  # non-string title
                "choices": ["not-a-choice", {"label": 3}],  # non-dict, non-str label
            },
        ]
    }
    assert _candidate_slot_tokens(candidate) == frozenset()


@pytest.mark.unit
def test_derive_mutant_contract_raises_on_an_unresolvable_graft_token() -> None:
    """A graft-shaped token no donor declares is a hard derivation failure."""
    # An ending title carries a renamed graft token whose donor slot is absent.
    candidate = {
        "id": "c",
        "nodes": [
            {"id": "n", "is_ending": True, "ending": {"title": "{M1_FOO} triumphs"}}
        ],
    }
    with pytest.raises(ValidationError, match="matches no host slot and no donor slot"):
        derive_mutant_contract(
            candidate, mutant_slug="m", host_contract=_host_contract()
        )


@pytest.mark.unit
def test_write_bundle_writes_svg_and_sample_fill_without_a_gate(
    tmp_path: Path,
) -> None:
    """A sample-fill without a gate report and an SVG diagram both write cleanly."""
    parent: dict[str, object] = {"id": "p", "title": "P", "nodes": []}
    lineage = build_lineage(
        mutant_slug="m-slug",
        parent=parent,
        parent_slug="the-parent",
        op_chain=[OpChainEntry(op_id="M1", params={}, seed=0)],
        donor_slugs=[],
        created_at="2026-07-20T00:00:00+00:00",
        tool_version="9.9.9",
        acceptance={"promotable": True},
    )
    bundle_dir = write_bundle(
        tmp_path,
        slug="m-slug",
        candidate={"id": "m", "nodes": []},
        lineage=lineage,
        acceptance={"promotable": True},
        reguide={"items": []},
        sample_fill={"filled": {"id": "m"}},  # no "gate" key present
        diagram_svg="<svg></svg>",
    )
    assert (bundle_dir / "sample-fill" / "filled.json").is_file()
    assert not (bundle_dir / "sample-fill" / "gate.json").exists()
    assert (bundle_dir / "diagram.svg").read_text(encoding="utf-8") == "<svg></svg>"


@pytest.mark.unit
def test_verify_bundle_raises_when_no_lineage_sidecar_exists(tmp_path: Path) -> None:
    """A bundle directory with no ``*.lineage.json`` cannot be verified."""
    (tmp_path / "empty-bundle").mkdir()
    with pytest.raises(FileNotFoundError, match="found in bundle directory"):
        verify_bundle(tmp_path / "empty-bundle", skeletons_root=tmp_path)
