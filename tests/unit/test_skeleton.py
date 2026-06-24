from pathlib import Path

import pytest

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
    with pytest.raises(ValueError, match="structural"):
        load_skeleton(path)
