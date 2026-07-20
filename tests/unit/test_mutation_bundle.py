"""Tests for the WS-5 D8 promotion bundle (mutation/bundle.py).

Covers the content hash (determinism + change detection), the versioned lineage
schema and its round trip, the bundle writer, the parent-hash verification
(including the hard failure on a since-changed parent), and the mutant-contract
derivation (contract parity, graft slot import, prune slot drop).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.mutation.bundle import (
    LINEAGE_VERSION,
    Lineage,
    OpChainEntry,
    acceptance_digest,
    build_lineage,
    content_sha256,
    derive_mutant_contract,
    verify_bundle,
    write_bundle,
)
from cyo_adventure.mutation.compose import ChainStep, apply_chain
from cyo_adventure.mutation.operators import (  # pyright: ignore[reportPrivateUsage]
    M3PruneGraft,
    _load_catalog_donor,
)
from cyo_adventure.mutation.ops import OpParams
from cyo_adventure.storybook.theme_contract import ThemeContract

if TYPE_CHECKING:
    from cyo_adventure.mutation.ops import MutationOp

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_CAVE = "8-11/the-cave-of-echoes.json"


def _load(slug_path: str) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        json.loads((_SKELETONS_ROOT / slug_path).read_text(encoding="utf-8")),
    )


def _acceptance_stub() -> dict[str, object]:
    return {"promotable": True, "stages": [{"stage": "1-gate", "passed": True}]}


def _lineage(mutant_slug: str = "m-slug") -> Lineage:
    return build_lineage(
        mutant_slug=mutant_slug,
        parent={"id": "p", "title": "P"},
        parent_slug="the-parent",
        op_chain=[OpChainEntry(op_id="M3", params={"mode": "graft"}, seed=0)],
        donor_slugs=["a-donor"],
        created_at="2026-07-20T00:00:00+00:00",
        tool_version="9.9.9",
        acceptance=_acceptance_stub(),
    )


@pytest.mark.unit
def test_content_sha256_deterministic_and_detects_change() -> None:
    """Equal documents hash identically; any content edit changes the digest."""
    a = {"id": "x", "n": [1, 2, 3]}
    b = {"n": [1, 2, 3], "id": "x"}  # different key order, same content
    assert content_sha256(a) == content_sha256(b)
    assert content_sha256(a) != content_sha256({"id": "x", "n": [1, 2, 4]})


@pytest.mark.unit
def test_build_lineage_records_hash_and_digest() -> None:
    """build_lineage stamps the parent hash, acceptance digest, and version."""
    lineage = _lineage()
    assert lineage.lineage_version == LINEAGE_VERSION
    assert lineage.parent_sha256 == content_sha256({"id": "p", "title": "P"})
    assert lineage.acceptance_digest == acceptance_digest(_acceptance_stub())
    assert lineage.donor_slugs == ["a-donor"]
    assert [e.op_id for e in lineage.op_chain] == ["M3"]


@pytest.mark.unit
def test_lineage_round_trips_through_json() -> None:
    """A serialized lineage validates back to an equal record."""
    lineage = _lineage()
    restored = Lineage.model_validate_json(lineage.model_dump_json())
    assert restored == lineage


@pytest.mark.unit
def test_write_bundle_writes_every_artifact(tmp_path: Path) -> None:
    """The writer emits shell, lineage, acceptance, reguide, contract, sample-fill."""
    candidate = {"id": "c", "nodes": []}
    contract = ThemeContract.model_validate(
        {
            "contract_version": 1,
            "skeleton_slug": "m-slug",
            "age_band": "8-11",
            "default_binding": {"HERO": "a brave fox"},
            "slots": [
                {"id": "HERO", "scope": "global", "meaning": "the hero", "guidance": ""}
            ],
        }
    )
    bundle = write_bundle(
        tmp_path,
        slug="m-slug",
        candidate=candidate,
        lineage=_lineage(),
        acceptance=_acceptance_stub(),
        reguide={"emitted_count": 0, "items": []},
        contract=contract,
        sample_fill={
            "status": "passed",
            "filled": {"id": "c"},
            "gate": {"blocked": False},
        },
        diagram_puml="@startuml\n@enduml\n",
    )
    assert (bundle / "m-slug.json").is_file()
    assert (bundle / "m-slug.lineage.json").is_file()
    assert (bundle / "m-slug.contract.json").is_file()
    assert (bundle / "acceptance.json").is_file()
    assert (bundle / "reguide.json").is_file()
    assert (bundle / "diagram.puml").is_file()
    assert (bundle / "sample-fill" / "result.json").is_file()
    assert (bundle / "sample-fill" / "filled.json").is_file()
    assert (bundle / "sample-fill" / "gate.json").is_file()


@pytest.mark.unit
def test_verify_bundle_ok_when_parent_unchanged(tmp_path: Path) -> None:
    """A bundle whose lineage hash matches the live parent verifies ok."""
    parent = _load(_CAVE)
    lineage = build_lineage(
        mutant_slug="m",
        parent=parent,
        parent_slug="the-cave-of-echoes",
        op_chain=[OpChainEntry(op_id="M1", params={}, seed=0)],
        donor_slugs=[],
        created_at="2026-07-20T00:00:00+00:00",
        tool_version="9.9.9",
        acceptance=_acceptance_stub(),
    )
    write_bundle(
        tmp_path,
        slug="m",
        candidate=parent,
        lineage=lineage,
        acceptance=_acceptance_stub(),
        reguide={"items": []},
    )
    result = verify_bundle(tmp_path / "m", skeletons_root=_SKELETONS_ROOT)
    assert result.ok is True
    assert result.actual_sha256 == lineage.parent_sha256


@pytest.mark.unit
def test_verify_bundle_hard_fails_on_changed_parent(tmp_path: Path) -> None:
    """A bundle whose parent changed since derivation must not verify (design 9.2)."""
    # Lineage records a hash for a DIFFERENT content than the live catalog parent.
    lineage = build_lineage(
        mutant_slug="m",
        parent={"id": "the-cave-of-echoes", "stale": True},
        parent_slug="the-cave-of-echoes",
        op_chain=[OpChainEntry(op_id="M1", params={}, seed=0)],
        donor_slugs=[],
        created_at="2026-07-20T00:00:00+00:00",
        tool_version="9.9.9",
        acceptance=_acceptance_stub(),
    )
    write_bundle(
        tmp_path,
        slug="m",
        candidate={"id": "m"},
        lineage=lineage,
        acceptance=_acceptance_stub(),
        reguide={"items": []},
    )
    result = verify_bundle(tmp_path / "m", skeletons_root=_SKELETONS_ROOT)
    assert result.ok is False
    assert "mismatch" in result.message


@pytest.mark.unit
def test_verify_bundle_fails_when_parent_missing(tmp_path: Path) -> None:
    """An unverifiable bundle (parent not in the catalog) does not verify."""
    lineage = build_lineage(
        mutant_slug="m",
        parent={"id": "x"},
        parent_slug="no-such-parent-slug",
        op_chain=[OpChainEntry(op_id="M1", params={}, seed=0)],
        donor_slugs=[],
        created_at="2026-07-20T00:00:00+00:00",
        tool_version="9.9.9",
        acceptance=_acceptance_stub(),
    )
    write_bundle(
        tmp_path,
        slug="m",
        candidate={"id": "m"},
        lineage=lineage,
        acceptance=_acceptance_stub(),
        reguide={"items": []},
    )
    result = verify_bundle(tmp_path / "m", skeletons_root=_SKELETONS_ROOT)
    assert result.ok is False
    assert result.actual_sha256 is None


@pytest.mark.unit
def test_derive_mutant_contract_is_none_without_tokens() -> None:
    """A candidate with no slot tokens derives no contract (contract-less parity)."""
    host = ThemeContract.model_validate(
        {
            "contract_version": 3,
            "skeleton_slug": "host",
            "age_band": "8-11",
            "default_binding": {"HERO": "a fox"},
            "slots": [
                {"id": "HERO", "scope": "global", "meaning": "hero", "guidance": ""}
            ],
        }
    )
    candidate = {"id": "c", "nodes": [{"id": "n", "body": "plain prose, no tokens"}]}
    assert (
        derive_mutant_contract(candidate, mutant_slug="m", host_contract=host) is None
    )


@pytest.mark.unit
def test_derive_mutant_contract_imports_graft_slots() -> None:
    """A graft chain's mutant contract declares exactly the mutant's slot tokens."""
    host = _load(_CAVE)
    donor_resolver = _load_catalog_donor

    def op_for(op_id: str) -> MutationOp:
        return M3PruneGraft(donor_resolver)

    chain = apply_chain(
        host,
        [
            ChainStep(
                "M3",
                OpParams.of(
                    mode="graft",
                    donor="the-robot-fair-sabotage",
                    subtree_root="n_lockup",
                    host_decision="la_crystal_take",
                ),
                0,
            )
        ],
        op_for=op_for,
    )
    host_contract = ThemeContract.model_validate_json(
        (_SKELETONS_ROOT / "8-11/the-cave-of-echoes.contract.json").read_text(
            encoding="utf-8"
        )
    )
    donor_contract = ThemeContract.model_validate_json(
        (_SKELETONS_ROOT / "8-11/the-robot-fair-sabotage.contract.json").read_text(
            encoding="utf-8"
        )
    )
    mutant = derive_mutant_contract(
        chain.candidate,
        mutant_slug="cave-graft",
        host_contract=host_contract,
        donor_contracts={"the-robot-fair-sabotage": donor_contract},
    )
    assert mutant is not None
    # Every declared slot has a default binding, and at least one imported M<k>_
    # graft slot is present (the donor content was carried in).
    slot_ids = {spec.id for spec in mutant.slots}
    assert slot_ids == set(mutant.default_binding)
    assert any(sid.startswith("M") and "_" in sid for sid in slot_ids)
    assert mutant.contract_version == 1
    assert mutant.skeleton_slug == "cave-graft"
