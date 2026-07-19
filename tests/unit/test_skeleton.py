from pathlib import Path

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.skeleton import (
    has_unfilled_directives,
    is_production_eligible,
    load_skeleton,
)

_SKELETON = Path("tests/fixtures/skeletons/demo_shell.json")


@pytest.mark.unit
def test_load_skeleton_accepts_valid_shell() -> None:
    """A structurally valid shell loads and is reported as unfilled."""
    data = load_skeleton(_SKELETON)
    assert data["id"] == "sk_demo"
    assert has_unfilled_directives(data) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "story",
    [
        pytest.param({}, id="no_nodes_key"),
        pytest.param({"nodes": "not-a-list"}, id="nodes_not_a_list"),
    ],
)
def test_has_unfilled_directives_returns_false_when_nodes_missing_or_not_a_list(
    story: dict[str, object],
) -> None:
    """A story with no 'nodes' key, or a non-list 'nodes', reports no directives."""
    assert has_unfilled_directives(story) is False


@pytest.mark.unit
def test_load_skeleton_rejects_structurally_broken_shell(tmp_path: Path) -> None:
    """A shell whose choice targets a missing node is rejected."""
    import json

    broken = json.loads(_SKELETON.read_text())
    broken["nodes"][0]["choices"][0]["target"] = "does_not_exist"
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken))
    with pytest.raises(ValidationError, match="structural"):
        load_skeleton(path)


_DEMO_SKELETONS = [
    "skeletons/3-5/the-lost-mitten.json",
    "skeletons/10-13/the-clocktower-cipher.json",
    "skeletons/16+/the-sunken-signal.json",
]


@pytest.mark.unit
@pytest.mark.parametrize("rel", _DEMO_SKELETONS)
def test_skeletons_load_under_schema_2_0(rel: str) -> None:
    """Each demo skeleton parses under schema 2.0 with typed endings."""
    data = load_skeleton(Path(rel))
    assert data["schema_version"] == "2.0"
    assert "topology" in data["metadata"]
    for node in data["nodes"]:
        ending = node.get("ending")
        if ending is not None:
            assert set(ending) == {"id", "valence", "kind", "title"}


def _assert_passes_full_gate(rel: str) -> None:
    """Load the skeleton at ``rel`` and assert it passes the full gate."""
    import json

    from cyo_adventure.validator.gate import run_gate

    data = json.loads(Path(rel).read_text(encoding="utf-8"))
    result = run_gate(data)
    assert not result.blocked, [f.message for f in result.report.errors]


@pytest.mark.unit
@pytest.mark.parametrize("rel", _DEMO_SKELETONS)
def test_skeletons_pass_full_gate_including_policy(rel: str) -> None:
    """Each demo skeleton passes the full gate, including the policy layer."""
    _assert_passes_full_gate(rel)


@pytest.mark.unit
def test_demo_shell_is_production_eligible_by_default() -> None:
    """A skeleton with no ``production_eligible`` flag is production-eligible."""
    data = load_skeleton(_SKELETON)
    assert is_production_eligible(data) is True


@pytest.mark.unit
@pytest.mark.parametrize("rel", _DEMO_SKELETONS)
def test_seed_skeletons_are_mvp_non_production(rel: str) -> None:
    """The three current hand-authored seeds are MVP/Test, not production."""
    data = load_skeleton(Path(rel))
    assert is_production_eligible(data) is False


@pytest.mark.unit
def test_is_production_eligible_missing_metadata_defaults_true() -> None:
    """A malformed skeleton with no metadata is treated as production-eligible."""
    assert is_production_eligible({}) is True


# Production-eligible (scale-classified) skeletons authored against ADR-011.
# Each declares ``length`` + ``narrative_style`` + ``production_eligible: true``,
# which arms the PL-17/19/20/21 story-scale rules, so passing the full gate here
# pins the seed as launch-ready in CI. Discovered by scanning ``skeletons/`` so
# new cells are picked up automatically (MVP/Test seeds are excluded by their
# ``production_eligible: false`` flag), and no per-cell list edit is needed.
def _discover_production_skeletons() -> list[str]:
    import json

    found: list[str] = []
    for path in sorted(Path("skeletons").glob("*/*.json")):
        # Skip WS-2 theme-contract sidecars: they share the .json suffix and
        # this band-directory glob, but they are not skeletons (see
        # generation/skeleton_match.py, which skips them the same way).
        if path.name.endswith(".contract.json"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if is_production_eligible(data):
            found.append(str(path))
    return found


_PRODUCTION_SKELETONS = _discover_production_skeletons()


@pytest.mark.unit
def test_at_least_one_production_skeleton_exists() -> None:
    """Guard the discovery glob: the launch corpus is never silently empty."""
    assert _PRODUCTION_SKELETONS, "no production-eligible skeletons discovered"


@pytest.mark.unit
@pytest.mark.parametrize("rel", _PRODUCTION_SKELETONS)
def test_production_skeletons_pass_full_gate(rel: str) -> None:
    """Each production skeleton passes the full gate (blocked is False)."""
    _assert_passes_full_gate(rel)


@pytest.mark.unit
@pytest.mark.parametrize("rel", _PRODUCTION_SKELETONS)
def test_production_skeletons_are_production_eligible(rel: str) -> None:
    """Each production skeleton is scale-classified as production-eligible."""
    data = load_skeleton(Path(rel))
    assert is_production_eligible(data) is True
