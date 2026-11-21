"""The twelve retained shapes of owner decision D4 (WP-2.2).

Pins: the registry is exactly the D4 set, two per short and medium family cell;
every shape file is the v2 conversion of its v1 source and passes the gate in
skeleton posture and ``--strict-agency`` with the same findings as its source;
conversion leaves the shape hash unchanged; ``skeletons/`` stays all-v1 and
every retained source stays production-eligible and selectable.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import cast

import pytest

import scripts.check_skeleton as check_skeleton
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.skeleton_match import candidates_for_cell
from cyo_adventure.storybook.fill_directive import (
    convert_to_v2,
    directive_version,
    v2_directive_violations,
)
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storyplan.models import shape_hash
from cyo_adventure.storyplan.shapes import (
    RetainedShape,
    load_registry,
    load_shape,
    registry_problems,
    shape_entry_for,
)
from cyo_adventure.validator.gate import GateResult, run_gate

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[2]

# D4 as decided 2026-11-21 (story-plan-implementation-plan.md decision table).
_D4: dict[tuple[str, str, str], frozenset[str]] = {
    ("8-11", "short", "prose"): frozenset(
        {"the-locked-carousel", "the-cave-of-echoes"}
    ),
    ("8-11", "medium", "prose"): frozenset(
        {"the-lantern-keepers-list", "the-storm-chasers-club"}
    ),
    ("10-13", "short", "prose"): frozenset(
        {"the-glass-comet", "the-cinderwick-exchange"}
    ),
    ("10-13", "medium", "prose"): frozenset(
        {"the-orchard-signal", "the-flooded-quarter"}
    ),
    ("13-16", "medium", "prose"): frozenset(
        {"the-undertow-season", "the-conservatory-wars"}
    ),
    ("13-16", "medium", "gamebook"): frozenset(
        {"the-quarry-signal", "the-iron-spire-trial"}
    ),
}

_ENTRIES = load_registry(_REPO).shapes


def _load(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def _bodies(story: dict[str, object]) -> list[str]:
    return [str(n["body"]) for n in cast("list[dict[str, object]]", story["nodes"])]


def test_the_registry_is_exactly_the_d4_set() -> None:
    cells: dict[tuple[str, str, str], set[str]] = {}
    for entry in _ENTRIES:
        key = (entry.band.value, entry.length.value, entry.narrative_style.value)
        cells.setdefault(key, set()).add(entry.id)
    assert cells == {key: set(ids) for key, ids in _D4.items()}
    assert len(_ENTRIES) == 12


def test_the_registry_matches_its_files() -> None:
    assert registry_problems(load_registry(_REPO), _REPO) == []


@pytest.mark.parametrize("entry", _ENTRIES, ids=lambda e: e.id)
def test_conversion_leaves_the_shape_hash_unchanged(entry: RetainedShape) -> None:
    """Hash before conversion (v1 source) equals hash after (v2 shape)."""
    source = Storybook.model_validate(_load(_REPO / entry.source))
    shape = Storybook.model_validate(_load(_REPO / entry.file))
    assert shape_hash(source) == shape_hash(shape) == entry.hash


@pytest.mark.parametrize("entry", _ENTRIES, ids=lambda e: e.id)
def test_a_shape_is_all_v2_with_no_beats(entry: RetainedShape) -> None:
    shape = _load(_REPO / entry.file)
    assert v2_directive_violations(shape) == []
    assert all(directive_version(body) == 2 for body in _bodies(shape))
    assert not any("beats" in body for body in _bodies(shape))


@pytest.mark.parametrize("entry", _ENTRIES, ids=lambda e: e.id)
def test_a_shape_passes_the_skeleton_gate_with_its_sources_findings(
    entry: RetainedShape,
) -> None:
    """Skeleton posture; the v2 bodies change no finding the gate makes."""
    source = run_gate(_load(_REPO / entry.source), context="skeleton")
    shape = run_gate(_load(_REPO / entry.file), context="skeleton")
    assert not shape.blocked

    def key(result: GateResult) -> Counter[tuple[str, str | None, str]]:
        return Counter(
            (f.rule_id, f.node_id, str(f.severity)) for f in result.report.findings
        )

    assert key(shape) == key(source)


@pytest.mark.parametrize("entry", _ENTRIES, ids=lambda e: e.id)
def test_a_shape_passes_strict_agency(
    entry: RetainedShape, capsys: pytest.CaptureFixture[str]
) -> None:
    assert check_skeleton.main([str(_REPO / entry.file), "--strict-agency"]) == 0
    assert "directives: version 2" in capsys.readouterr().out


def test_no_skeleton_in_the_catalog_is_converted_in_place() -> None:
    """``skeletons/`` stays v1: the live skeleton-fill path keeps its beats."""
    offenders = [
        path.relative_to(_REPO).as_posix()
        for path in sorted((_REPO / "skeletons").glob("*/*.json"))
        if any(
            directive_version(str(node.get("body", ""))) == 2
            for node in cast("list[dict[str, object]]", _load(path).get("nodes", []))
            if isinstance(node, dict)
        )
    ]
    assert offenders == []


def test_every_retained_source_stays_production_eligible_and_selectable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(_REPO)
    for entry in _ENTRIES:
        assert entry.file.startswith("shapes/"), "a shape must sit outside the catalog"
        cell = candidates_for_cell(
            entry.band.value, entry.length.value, entry.narrative_style.value
        )
        assert entry.id in cell


def test_load_shape_returns_a_checked_shape_and_refuses_a_stale_one(
    tmp_path: Path,
) -> None:
    registry = load_registry(_REPO)
    entry = shape_entry_for(registry, "the-cave-of-echoes")
    assert entry is not None
    assert shape_entry_for(registry, "the-sky-ship-stowaway") is None
    shape = load_shape(entry, _REPO)
    assert _bodies(shape)[0].startswith("<<FILL v=2 ")

    stale = convert_to_v2(_load(_REPO / entry.source))
    nodes = cast("list[dict[str, object]]", stale["nodes"])
    choices = cast("list[dict[str, object]]", nodes[0]["choices"])
    choices[0]["target"] = nodes[-1]["id"]
    target = tmp_path / entry.file
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(stale), encoding="utf-8")
    with pytest.raises(ValidationError, match="registry hash"):
        load_shape(entry, tmp_path)


def test_a_missing_registry_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="cannot read"):
        load_registry(tmp_path)


def test_a_drifted_shape_file_is_a_registry_problem(tmp_path: Path) -> None:
    """A shape that is no longer the conversion of its source is caught."""
    registry = load_registry(_REPO)
    entry = registry.shapes[0]
    for rel in (entry.source, entry.file):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(
            (_REPO / rel).read_text(encoding="utf-8"), encoding="utf-8"
        )
    one = registry.model_copy(update={"shapes": [entry]})
    assert registry_problems(one, tmp_path) == []
    drifted = (
        (tmp_path / entry.file)
        .read_text(encoding="utf-8")
        .replace("function=opening", "function=decision", 1)
    )
    (tmp_path / entry.file).write_text(drifted, encoding="utf-8")
    problems = registry_problems(one, tmp_path)
    assert any("not the v2 conversion" in p for p in problems)
