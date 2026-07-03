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


@pytest.mark.unit
@pytest.mark.parametrize("rel", _DEMO_SKELETONS)
def test_skeletons_pass_full_gate_including_policy(rel: str) -> None:
    """Each demo skeleton passes the full gate, including the policy layer."""
    import json

    from cyo_adventure.validator.gate import run_gate

    data = json.loads(Path(rel).read_text(encoding="utf-8"))
    result = run_gate(data)
    assert not result.blocked, [f.message for f in result.report.errors]


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
# pins the seed as launch-ready in CI. Extend this list as new cells are seeded.
_PRODUCTION_SKELETONS = [
    "skeletons/8-11/the-cave-of-echoes.json",
]


@pytest.mark.unit
@pytest.mark.parametrize("rel", _PRODUCTION_SKELETONS)
def test_production_skeletons_pass_full_gate(rel: str) -> None:
    """Each production skeleton passes the full gate (blocked is False)."""
    import json

    from cyo_adventure.validator.gate import run_gate

    data = json.loads(Path(rel).read_text(encoding="utf-8"))
    result = run_gate(data)
    assert not result.blocked, [f.message for f in result.report.errors]


@pytest.mark.unit
@pytest.mark.parametrize("rel", _PRODUCTION_SKELETONS)
def test_production_skeletons_are_production_eligible(rel: str) -> None:
    """Each production skeleton is scale-classified as production-eligible."""
    data = load_skeleton(Path(rel))
    assert is_production_eligible(data) is True
