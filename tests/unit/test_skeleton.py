from pathlib import Path

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.skeleton import has_unfilled_directives, load_skeleton

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
