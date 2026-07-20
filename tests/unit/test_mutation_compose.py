"""Tests for WS-5 D8 bounded operator chains (mutation/compose.py).

Covers chain application (single and multi-op), the OQ-7 chain bound, precondition
aborts, op-chain/donor recording, determinism, surviving re-guidance filtering,
and chain acceptance (held vs promotable) plus the CLI chain/verify/slug paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.compose import (
    MAX_CHAIN_LENGTH,
    ChainStep,
    apply_chain,
    run_chain_acceptance,
)
from cyo_adventure.mutation.operators import (  # pyright: ignore[reportPrivateUsage]
    M3PruneGraft,
    _load_catalog_donor,
)
from cyo_adventure.mutation.ops import REGISTRY, OpParams

if TYPE_CHECKING:
    from cyo_adventure.mutation.ops import MutationOp

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_CAVE = "8-11/the-cave-of-echoes.json"
_GRAFT = OpParams.of(
    mode="graft",
    donor="the-robot-fair-sabotage",
    subtree_root="n_lockup",
    host_decision="la_crystal_take",
)


def _load(slug_path: str) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        json.loads((_SKELETONS_ROOT / slug_path).read_text(encoding="utf-8")),
    )


def _op_for(op_id: str) -> MutationOp:
    """Resolve ops, giving M3 a real catalog donor resolver."""
    if op_id == "M3":
        return M3PruneGraft(_load_catalog_donor)
    return REGISTRY.get(op_id)


@pytest.mark.unit
def test_apply_chain_single_op_matches_direct_apply() -> None:
    """A one-step chain equals applying the operator directly."""
    parent = _load(_CAVE)
    chain = apply_chain(parent, [ChainStep("M1", OpParams.of(), 0)])
    assert len(chain.op_chain) == 1
    assert chain.op_chain[0].op_id == "M1"
    assert chain.candidate != parent


@pytest.mark.unit
def test_apply_chain_records_op_chain_and_donors() -> None:
    """A graft+M2 chain records both ops in order and the graft donor slug."""
    parent = _load(_CAVE)
    chain = apply_chain(
        parent,
        [ChainStep("M3", _GRAFT, 0), ChainStep("M2", OpParams.of(), 3)],
        op_for=_op_for,
    )
    assert [e.op_id for e in chain.op_chain] == ["M3", "M2"]
    assert chain.donor_slugs == ("the-robot-fair-sabotage",)
    assert chain.op_chain[1].seed == 3


@pytest.mark.unit
def test_apply_chain_is_deterministic() -> None:
    """The same steps re-derive a byte-identical candidate."""
    parent = _load(_CAVE)
    steps = [ChainStep("M3", _GRAFT, 0), ChainStep("M2", OpParams.of(), 3)]
    first = apply_chain(parent, steps, op_for=_op_for)
    second = apply_chain(parent, steps, op_for=_op_for)
    assert first.candidate == second.candidate


@pytest.mark.unit
def test_apply_chain_rejects_over_bound() -> None:
    """A chain longer than MAX_CHAIN_LENGTH is rejected (OQ-7)."""
    parent = _load(_CAVE)
    steps = [ChainStep("M1", OpParams.of(), i) for i in range(MAX_CHAIN_LENGTH + 1)]
    with pytest.raises(ValidationError, match="bounded"):
        apply_chain(parent, steps)


@pytest.mark.unit
def test_apply_chain_rejects_empty() -> None:
    """An empty chain is rejected."""
    with pytest.raises(ValidationError, match="at least one"):
        apply_chain(_load(_CAVE), [])


@pytest.mark.unit
def test_apply_chain_aborts_on_precondition_failure() -> None:
    """A step whose preconditions fail aborts the whole chain."""
    parent = _load(_CAVE)
    # M3 graft with a nonexistent host decision fails preconditions.
    bad = OpParams.of(mode="graft", subtree_root="nope", host_decision="nope")
    with pytest.raises(ValidationError, match="ineligible"):
        apply_chain(parent, [ChainStep("M3", bad, 0)], op_for=_op_for)


@pytest.mark.unit
def test_run_chain_acceptance_held_then_promotable() -> None:
    """A graft+M2 chain is held with reguide outstanding, promotable once resolved."""
    parent = _load(_CAVE)
    chain = apply_chain(
        parent,
        [ChainStep("M3", _GRAFT, 0), ChainStep("M2", OpParams.of(), 3)],
        op_for=_op_for,
    )
    held = run_chain_acceptance(parent, chain, parent_slug="the-cave-of-echoes")
    assert held.discarded_at_stage is None
    assert held.promotable is False
    assert held.held is True

    resolved = frozenset(item.target_id for item in chain.reguide)
    promotable = run_chain_acceptance(
        parent,
        chain,
        parent_slug="the-cave-of-echoes",
        resolved_reguide_ids=resolved,
    )
    assert promotable.promotable is True


# --- CLI: chain, verify-bundle, and the slug fix ---


@pytest.mark.unit
def test_cli_chain_writes_bundle(tmp_path: Path) -> None:
    """The CLI --chain mode writes a full bundle and exits 0."""
    from scripts import mutate_skeleton as ms

    chain_file = tmp_path / "chain.json"
    chain_file.write_text(
        json.dumps(
            [
                {
                    "op": "M3",
                    "params": {
                        "mode": "graft",
                        "donor": "the-robot-fair-sabotage",
                        "subtree_root": "n_lockup",
                        "host_decision": "la_crystal_take",
                    },
                    "seed": 0,
                },
                {"op": "M2", "params": {}, "seed": 3},
            ]
        ),
        encoding="utf-8",
    )
    parent = _SKELETONS_ROOT / _CAVE
    code = ms.main(
        [
            str(parent),
            "--chain",
            str(chain_file),
            "--out-dir",
            str(tmp_path),
            "--no-svg",
        ]
    )
    assert code == 0
    slug = "the-cave-of-echoes-chain-m3graft-s0-m2-s3"
    bundle = tmp_path / slug
    assert (bundle / f"{slug}.lineage.json").is_file()
    assert (bundle / f"{slug}.contract.json").is_file()
    assert (bundle / "diagram.puml").is_file()
    # verify-bundle mode passes on the freshly written bundle.
    assert ms.main(["--verify-bundle", str(bundle)]) == 0


@pytest.mark.unit
def test_cli_slug_distinguishes_prune_from_graft() -> None:
    """Prune and graft at the same seed derive distinct slugs (the D4/D5 fix).

    The old `<parent>-<op>-s<seed>` slug collided for two M3 modes at one seed; the
    slug now folds in the mode, so distinct mutations get distinct bundle dirs.
    """
    from scripts import mutate_skeleton as ms

    prune = ChainStep("M3", OpParams.of(mode="prune"), 0)
    graft = ChainStep("M3", _GRAFT, 0)
    prune_slug = ms._derive_slug("the-cave-of-echoes", [prune])
    graft_slug = ms._derive_slug("the-cave-of-echoes", [graft])
    assert prune_slug == "the-cave-of-echoes-m3prune-s0"
    assert graft_slug == "the-cave-of-echoes-m3graft-s0"
    assert prune_slug != graft_slug
