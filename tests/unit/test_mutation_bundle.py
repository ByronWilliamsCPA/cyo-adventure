"""Tests for the WS-5 D8 promotion bundle (mutation/bundle.py).

Covers the content hash (determinism + change detection), the versioned lineage
schema and its round trip, the bundle writer, the parent-hash verification
(including the hard failure on a since-changed parent), and the mutant-contract
derivation (contract parity, graft slot import, prune slot drop).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.mutation.bundle import (
    LINEAGE_VERSION,
    Lineage,
    LineageV2,
    OpChainEntry,
    acceptance_digest,
    build_lineage,
    content_sha256,
    derive_mutant_contract,
    load_lineage,
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


def _lineage(mutant_slug: str = "m-slug") -> LineageV2:
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
    assert lineage.origin == "mutation"
    assert lineage.parent_sha256 == content_sha256({"id": "p", "title": "P"})
    assert lineage.acceptance_digest == acceptance_digest(_acceptance_stub())
    assert lineage.donor_slugs == ["a-donor"]
    assert [e.op_id for e in lineage.op_chain] == ["M3"]


@pytest.mark.unit
def test_lineage_round_trips_through_json() -> None:
    """A serialized v2 lineage validates back to an equal record."""
    lineage = _lineage()
    restored = LineageV2.model_validate_json(lineage.model_dump_json())
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


# --------------------------------------------------------------------------- #
# Lineage v2: the feed-agnostic origin discriminator (WS-8 D5, design 7.2).
# --------------------------------------------------------------------------- #


def _v1_lineage(*, parent_slug: str, parent_sha256: str) -> Lineage:
    """Build a genuine v1 (``lineage_version == 1``, no origin) lineage record."""
    return Lineage(
        lineage_version=1,
        mutant_slug="m",
        parent_slug=parent_slug,
        parent_sha256=parent_sha256,
        donor_slugs=["a-donor"],
        op_chain=[OpChainEntry(op_id="M1", params={}, seed=0)],
        created_at="2026-07-20T00:00:00+00:00",
        tool_version="9.9.9",
        acceptance_digest="abc123",
    )


@pytest.mark.unit
def test_v1_bundle_still_verifies(tmp_path: Path) -> None:
    """A v1 bundle on disk (no origin field) still loads and verify_bundle's OK."""
    parent = _load(_CAVE)
    v1 = _v1_lineage(
        parent_slug="the-cave-of-echoes", parent_sha256=content_sha256(parent)
    )
    write_bundle(
        tmp_path,
        slug="m",
        candidate=parent,
        lineage=v1,
        acceptance=_acceptance_stub(),
        reguide={"items": []},
    )
    # The sidecar on disk is genuinely v1: keyed on lineage_version, no origin.
    written = cast(
        "dict[str, object]",
        json.loads((tmp_path / "m" / "m.lineage.json").read_text(encoding="utf-8")),
    )
    assert written["lineage_version"] == 1
    assert "origin" not in written
    result = verify_bundle(tmp_path / "m", skeletons_root=_SKELETONS_ROOT)
    assert result.ok is True
    assert result.actual_sha256 == content_sha256(parent)


@pytest.mark.unit
def test_load_lineage_upgrades_v1_to_v2_mutation() -> None:
    """A v1 payload upgrades to a canonical LineageV2 mutation record on read."""
    v1 = _v1_lineage(parent_slug="p", parent_sha256="h")
    upgraded = load_lineage(v1.model_dump_json())
    assert isinstance(upgraded, LineageV2)
    assert upgraded.origin == "mutation"
    assert upgraded.lineage_version == LINEAGE_VERSION
    assert upgraded.parent_slug == "p"
    assert upgraded.parent_sha256 == "h"
    assert [e.op_id for e in upgraded.op_chain] == ["M1"]


@pytest.mark.unit
def test_v2_mutation_without_parent_fails() -> None:
    """A v2 mutation record without a parent fails cross-field validation."""
    with pytest.raises(PydanticValidationError):
        LineageV2(
            origin="mutation",
            mutant_slug="m",
            parent_slug=None,
            parent_sha256=None,
            op_chain=[OpChainEntry(op_id="M1")],
            created_at="2026-07-20T00:00:00+00:00",
            tool_version="9.9.9",
            acceptance_digest="abc123",
        )


@pytest.mark.unit
def test_v2_mutation_with_empty_op_chain_fails() -> None:
    """A v2 mutation record with an empty op_chain fails validation."""
    with pytest.raises(PydanticValidationError):
        LineageV2(
            origin="mutation",
            mutant_slug="m",
            parent_slug="p",
            parent_sha256="h",
            op_chain=[],
            created_at="2026-07-20T00:00:00+00:00",
            tool_version="9.9.9",
            acceptance_digest="abc123",
        )


@pytest.mark.unit
def test_v2_fresh_without_generator_fails() -> None:
    """A v2 fresh record without generator provenance fails validation."""
    with pytest.raises(PydanticValidationError):
        LineageV2(
            origin="fresh",
            mutant_slug="fresh-tree",
            created_at="2026-07-20T00:00:00+00:00",
            tool_version="9.9.9",
            acceptance_digest="abc123",
        )


@pytest.mark.unit
def test_v2_fresh_with_parent_fails() -> None:
    """A v2 fresh record that carries a parent fails validation."""
    with pytest.raises(PydanticValidationError):
        LineageV2(
            origin="fresh",
            mutant_slug="fresh-tree",
            parent_slug="p",
            parent_sha256="h",
            generator="ws6:0.1",
            generation_params_sha256="params-hash",
            created_at="2026-07-20T00:00:00+00:00",
            tool_version="9.9.9",
            acceptance_digest="abc123",
        )


def _fresh_lineage(*, acceptance_digest_value: str) -> LineageV2:
    """Build a well-formed v2 fresh (WS-6) lineage record."""
    return LineageV2(
        origin="fresh",
        mutant_slug="fresh-tree",
        generator="ws6:0.1",
        generation_params_sha256="params-hash",
        created_at="2026-07-20T00:00:00+00:00",
        tool_version="9.9.9",
        acceptance_digest=acceptance_digest_value,
    )


@pytest.mark.unit
def test_v2_fresh_bundle_verifies_acceptance_digest(tmp_path: Path) -> None:
    """A well-formed fresh bundle verifies its acceptance digest, not a parent."""
    acceptance = _acceptance_stub()
    fresh = _fresh_lineage(acceptance_digest_value=acceptance_digest(acceptance))
    write_bundle(
        tmp_path,
        slug="fresh-tree",
        candidate={"id": "fresh-tree"},
        lineage=fresh,
        acceptance=acceptance,
        reguide={"items": []},
    )
    written = cast(
        "dict[str, object]",
        json.loads(
            (tmp_path / "fresh-tree" / "fresh-tree.lineage.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    assert written["origin"] == "fresh"
    # No parent exists, so a nonexistent skeletons_root is irrelevant to the result.
    result = verify_bundle(tmp_path / "fresh-tree", skeletons_root=_SKELETONS_ROOT)
    assert result.ok is True
    assert result.actual_sha256 == acceptance_digest(acceptance)


@pytest.mark.unit
def test_v2_fresh_bundle_hard_fails_on_tampered_acceptance(tmp_path: Path) -> None:
    """A fresh bundle whose acceptance.json changed since bundling must not verify."""
    fresh = _fresh_lineage(acceptance_digest_value="deadbeefdeadbeef")
    write_bundle(
        tmp_path,
        slug="fresh-tree",
        candidate={"id": "fresh-tree"},
        lineage=fresh,
        acceptance=_acceptance_stub(),  # digest will not match the recorded one
        reguide={"items": []},
    )
    result = verify_bundle(tmp_path / "fresh-tree", skeletons_root=_SKELETONS_ROOT)
    assert result.ok is False
    assert "acceptance digest mismatch" in result.message


@pytest.mark.unit
def test_origin_is_metadata_only_no_acceptance_stage_branches() -> None:
    """Safety pin: no acceptance stage or floor keys a decision off ``origin``.

    The lineage ``origin`` is provenance metadata only (design 7.2 safety
    property). If ``acceptance.py`` or ``floors.py`` ever read ``.origin`` or a bare
    ``origin`` name, a promotion could be relaxed by declaring a different origin;
    the contract forbids it, so every acceptance stage and floor that applies to a
    tree applies regardless of origin. This AST check fails loudly if that ever
    changes, and no ``origin`` value may be added to relax an acceptance stage.
    """
    import cyo_adventure.mutation.acceptance as acceptance_mod
    import cyo_adventure.mutation.floors as floors_mod

    for module in (acceptance_mod, floors_mod):
        source_path = module.__file__
        assert source_path is not None
        tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr != "origin", (
                    f"{Path(source_path).name} branches on .origin; "
                    f"origin must never key an acceptance/floor decision"
                )
            if isinstance(node, ast.Name):
                assert node.id != "origin", (
                    f"{Path(source_path).name} references a bare 'origin'; "
                    f"origin must never key an acceptance/floor decision"
                )
