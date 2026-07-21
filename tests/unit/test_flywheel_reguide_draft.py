"""Unit tests for WS-8 D3: re-guidance drafting and the deterministic floor.

Covers every floor rule with a violating fixture (design 5.3 rules 1-4), the
drive-a-held-candidate-to-promotable path through the UNCHANGED acceptance harness
with an injected deterministic provider (no network), the ``author="agent:..."``
attribution round-trip into ``reguide.json``, the OWASP LLM01 pins (no
``story_requests`` import, no request-shaped parameter, catalog content fenced as
data), the safety property that a floor failure leaves an item unresolved, and the
CLI ``--no-draft`` default.

The real catalog corpus (``skeletons/``) is git-versioned data, not a live
service, so loading it here honors the ``tests/`` no-network/no-DB posture. The
one LLM touchpoint is exercised through ``generation.provider.MockProvider``, a
pure deterministic test double.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

import cyo_adventure.flywheel as flywheel_pkg
from cyo_adventure.flywheel.reguide_draft import (
    _RULE_BAND_VOCAB,
    _RULE_SLOT_DISCIPLINE,
    _RULE_STRUCTURAL,
    _RULE_SURFACE_PARITY,
    draft_resolutions,
    render_draft_prompt,
    screen_draft,
)
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.mutation.compose import ChainStep, apply_chain, run_chain_acceptance
from cyo_adventure.mutation.operators import (  # pyright: ignore[reportPrivateUsage]
    M3PruneGraft,
    _load_catalog_donor,
)
from cyo_adventure.mutation.ops import REGISTRY, OpParams, ReguideItem, ReguideTarget
from cyo_adventure.mutation.reguide import reconcile, resolved_ids
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import (
    SlotScope,
    SlotSpec,
    ThemeContract,
)

if TYPE_CHECKING:
    from cyo_adventure.flywheel.reguide_draft import FloorResult
    from cyo_adventure.mutation.ops import MutationOp

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_CAVE = "8-11/the-cave-of-echoes.json"
_GRAFT = OpParams.of(
    mode="graft",
    donor="the-robot-fair-sabotage",
    subtree_root="n_lockup",
    host_decision="la_crystal_take",
)

# A benign resolution string that satisfies every floor rule for any target and
# for the 8-11 band: single line, no braces, no injection, under length, and no
# band-mandatory denylist stem.
_BENIGN = "A calm, brave moment as the friends decide what to do next."

# A FILL directive node body, the pre-mutation surface for a skeleton NODE.
_FILL_BODY = "<<FILL role=narrator words=50 beats='the old beats'>>"


def _op_for(op_id: str) -> MutationOp:
    """Resolve ops, giving M3 a real catalog donor resolver."""
    if op_id == "M3":
        return M3PruneGraft(_load_catalog_donor)
    return REGISTRY.get(op_id)


def _load(slug_path: str) -> dict[str, object]:
    """Load a real catalog skeleton document."""
    return cast(
        "dict[str, object]",
        json.loads((_SKELETONS_ROOT / slug_path).read_text(encoding="utf-8")),
    )


def _node_item(current_text: str = "") -> ReguideItem:
    """Build a NODE re-guidance item fixture."""
    return ReguideItem(
        target=ReguideTarget.NODE,
        target_id="n_x",
        reason="a node whose beats need re-authoring",
        current_text=current_text,
    )


def _screen(
    item: ReguideItem,
    drafted: str,
    *,
    contract: ThemeContract | None = None,
    band: AgeBand = AgeBand.BAND_8_11,
) -> FloorResult:
    """Screen a drafted resolution through the floor with test defaults."""
    return screen_draft(item, drafted, contract=contract, age_band=band)


def _rules(result: FloorResult) -> set[str]:
    """Return the set of failed rule ids in a floor result."""
    return {v.rule for v in result.violations}


def _contract_with_hero() -> ThemeContract:
    """Return a minimal one-slot contract declaring only ``{HERO}``."""
    return ThemeContract(
        contract_version=1,
        skeleton_slug="fixture",
        age_band=AgeBand.BAND_8_11,
        default_binding={"HERO": "Robot"},
        slots=[SlotSpec(id="HERO", scope=SlotScope.GLOBAL, meaning="the story hero")],
    )


# --- floor rule 1: surface parity ---


@pytest.mark.unit
def test_screen_draft_words_drift_leaves_item_unresolved() -> None:
    """A NODE draft carrying a FILL attribute token fails surface parity (rule 1)."""
    result = _screen(_node_item(_FILL_BODY), "a brave escape words=99")
    assert result.passed is False
    assert _RULE_SURFACE_PARITY in _rules(result)


@pytest.mark.unit
def test_screen_draft_valid_node_beats_passes() -> None:
    """A clean NODE beats draft preserves role=/words= and passes every rule."""
    result = _screen(_node_item(_FILL_BODY), _BENIGN)
    assert result.passed is True
    assert result.human_check_required is False


@pytest.mark.unit
def test_screen_draft_choice_requires_human_action_semantic_check() -> None:
    """A CHOICE resolution passes mechanically but flags the human check (rule 1)."""
    item = ReguideItem(
        target=ReguideTarget.CHOICE,
        target_id="c_x",
        reason="a choice label to re-author",
        current_text="Old label",
    )
    result = _screen(item, "Follow the quiet path.")
    assert result.passed is True
    assert result.human_check_required is True


@pytest.mark.unit
def test_screen_draft_multiline_choice_leaves_item_unresolved() -> None:
    """A CHOICE resolution spanning lines fails surface parity (rule 1)."""
    item = ReguideItem(
        target=ReguideTarget.CHOICE,
        target_id="c_x",
        reason="a choice label",
        current_text="Old",
    )
    result = _screen(item, "Follow the path\nand keep going")
    assert result.passed is False
    # A newline trips both the single-line parity rule and the structural block;
    # either attribution is a refusal, and the item stays unresolved.
    assert _RULE_SURFACE_PARITY in _rules(result)


# --- floor rule 2: slot-token discipline ---


@pytest.mark.unit
def test_screen_draft_invented_slot_token_leaves_item_unresolved() -> None:
    """A ``{SLOT}`` token not declared by the contract fails discipline (rule 2)."""
    result = _screen(
        _node_item(),
        "meet {VILLAIN} at the gate",
        contract=_contract_with_hero(),
    )
    assert result.passed is False
    assert _rules(result) == {_RULE_SLOT_DISCIPLINE}


@pytest.mark.unit
def test_screen_draft_declared_slot_token_passes() -> None:
    """A declared ``{HERO}`` token is permitted for a contract mutant (rule 2)."""
    result = _screen(
        _node_item(),
        "guide {HERO} gently onward",
        contract=_contract_with_hero(),
    )
    assert result.passed is True


@pytest.mark.unit
def test_screen_draft_contractless_braces_leave_item_unresolved() -> None:
    """A contract-less mutant permits no brace at all (rule 2)."""
    result = _screen(_node_item(), "guide {HERO} onward", contract=None)
    assert result.passed is False
    assert _RULE_SLOT_DISCIPLINE in _rules(result)


# --- floor rule 3: structural injection block ---


@pytest.mark.unit
def test_screen_draft_fence_marker_leaves_item_unresolved() -> None:
    """A ``<<``/``>>`` fence marker fails the structural block (rule 3)."""
    result = _screen(_node_item(), "danger <<FILL>> zone")
    assert result.passed is False
    assert _RULE_STRUCTURAL in _rules(result)


@pytest.mark.unit
def test_screen_draft_control_char_leaves_item_unresolved() -> None:
    """A control character fails the structural block (rule 3)."""
    result = _screen(_node_item(), "line one\x07bad")
    assert result.passed is False
    assert _RULE_STRUCTURAL in _rules(result)


@pytest.mark.unit
def test_screen_draft_over_length_beat_leaves_item_unresolved() -> None:
    """A NODE beats draft over the 600-character cap fails the structural block."""
    result = _screen(_node_item(), "brave word " * 80)
    assert result.passed is False
    assert _RULE_STRUCTURAL in _rules(result)


@pytest.mark.unit
def test_screen_draft_over_length_label_leaves_item_unresolved() -> None:
    """A CHOICE label over the 120-character cap fails (rule 3, single-line cap)."""
    item = ReguideItem(
        target=ReguideTarget.ENDING,
        target_id="e_x",
        reason="an ending title",
        current_text="Old",
    )
    result = _screen(item, "a gentle ending " * 10)
    assert result.passed is False
    assert _RULE_STRUCTURAL in _rules(result)


# --- floor rule 4: band vocabulary floor ---


@pytest.mark.unit
def test_screen_draft_band_denylist_stem_leaves_item_unresolved() -> None:
    """A band-mandatory denylist stem fails the band vocabulary floor (rule 4)."""
    result = _screen(_node_item(), "the trap will kill the hero")
    assert result.passed is False
    assert _RULE_BAND_VOCAB in _rules(result)


# --- drafting: drive a held candidate to promotable via the UNCHANGED harness ---


@pytest.mark.unit
def test_draft_resolutions_drives_held_candidate_to_promotable() -> None:
    """A drafted resolution set makes a held graft chain promotable (design 5.3)."""
    parent = _load(_CAVE)
    chain = apply_chain(
        parent,
        [ChainStep("M3", _GRAFT, 0), ChainStep("M2", OpParams.of(), 3)],
        op_for=_op_for,
    )
    held = run_chain_acceptance(parent, chain, parent_slug="the-cave-of-echoes")
    assert held.promotable is False
    assert chain.reguide  # the chain emits re-guidance to resolve

    provider = MockProvider(responses=[_BENIGN] * len(chain.reguide))
    resolutions = asyncio.run(
        draft_resolutions(
            chain.reguide,
            provider=provider,
            model_id="test-model",
            contract=None,
            age_band=AgeBand.BAND_8_11,
            length="short",
            style="prose",
            parent=parent,
        )
    )
    assert len(resolutions.resolutions) == len(chain.reguide)
    assert all(r.author == "agent:test-model" for r in resolutions.resolutions)

    promotable = run_chain_acceptance(
        parent,
        chain,
        parent_slug="the-cave-of-echoes",
        resolved_reguide_ids=resolved_ids(resolutions),
    )
    assert promotable.promotable is True


@pytest.mark.unit
def test_draft_resolutions_attribution_round_trips_into_reguide_json() -> None:
    """The agent attribution survives ``reconcile`` into the reguide.json dict."""
    parent = _load(_CAVE)
    chain = apply_chain(
        parent,
        [ChainStep("M3", _GRAFT, 0), ChainStep("M2", OpParams.of(), 3)],
        op_for=_op_for,
    )
    provider = MockProvider(responses=[_BENIGN] * len(chain.reguide))
    resolutions = asyncio.run(
        draft_resolutions(
            chain.reguide,
            provider=provider,
            model_id="opus-x",
            contract=None,
            age_band=AgeBand.BAND_8_11,
            length="short",
            style="prose",
            parent=parent,
        )
    )
    document = reconcile(chain.reguide, resolutions)
    assert document["fully_resolved"] is True
    items = cast("list[dict[str, object]]", document["items"])
    assert items
    assert all(item["author"] == "agent:opus-x" for item in items)


@pytest.mark.unit
def test_draft_resolutions_floor_failure_leaves_item_unresolved() -> None:
    """A floor-failing completion yields no resolution (the D3 safety property)."""
    item = _node_item()
    provider = MockProvider(responses=["danger <<FILL>> zone"])
    resolutions = asyncio.run(
        draft_resolutions(
            [item],
            provider=provider,
            model_id="m",
            contract=None,
            age_band=AgeBand.BAND_8_11,
            length="short",
            style="prose",
            parent={},
        )
    )
    assert resolutions.resolutions == []


# --- OWASP LLM01 pins ---


@pytest.mark.unit
def test_flywheel_package_imports_nothing_from_story_requests() -> None:
    """No flywheel module imports from story_requests (design 5.3 #CRITICAL)."""
    package_dir = Path(cast("str", flywheel_pkg.__file__)).parent
    for module_path in package_dir.glob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append(node.module)
        offenders = [name for name in imported if "story_requests" in name]
        assert not offenders, f"{module_path.name}: {offenders}"


@pytest.mark.unit
def test_draft_and_floor_take_no_request_shaped_parameter() -> None:
    """Neither drafting nor the floor accepts a brief/theme/premise/request arg."""
    forbidden = {"brief", "theme", "premise", "request"}
    for func in (draft_resolutions, screen_draft, render_draft_prompt):
        names = set(inspect.signature(func).parameters)
        assert forbidden.isdisjoint(names), func.__name__


@pytest.mark.unit
def test_reguide_draft_template_fences_catalog_content_as_data() -> None:
    """The template wraps its catalog-content inputs in an explicit data fence."""
    item = ReguideItem(
        target=ReguideTarget.NODE,
        target_id="n_x",
        reason="UNIQUE_REASON_TOKEN",
        current_text="before-text",
    )
    _system, user = render_draft_prompt(
        item,
        contract=None,
        age_band=AgeBand.BAND_8_11,
        length="short",
        style="prose",
    )
    begin = user.index("=== BEGIN CATALOG CONTENT")
    end = user.index("=== END CATALOG CONTENT")
    assert begin < user.index("UNIQUE_REASON_TOKEN") < end


# --- CLI: the --no-draft default ---


@pytest.mark.unit
def test_candidates_cli_default_is_no_draft() -> None:
    """The candidates CLI defaults to --no-draft, preserving D2 behavior."""
    from scripts.flywheel_candidates import (  # pyright: ignore[reportPrivateUsage]
        _build_parser,
    )

    parser = _build_parser()
    base = ["--band", "8-11", "--length", "short", "--style", "prose"]
    assert parser.parse_args(base).draft is False
    assert parser.parse_args([*base, "--draft"]).draft is True
