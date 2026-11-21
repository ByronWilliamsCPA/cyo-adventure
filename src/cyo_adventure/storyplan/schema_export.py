"""Export the Story Plan JSON Schema from the Pydantic model.

Run as a module to (re)generate ``schema/storyplan.schema.json`` from the single
source of truth in ``models.py``::

    uv run python -m cyo_adventure.storyplan.schema_export

The JSON Schema is committed so plan writers and non-Python tooling can validate
a plan without importing Python. It captures field types and structural shape
only: the cross-reference rules in ``StoryPlan._check_references`` (declared
facts, known nodes and choices, the ``plants``/``planted_by`` agreement) cannot
be expressed in JSON Schema, so authoritative validation needs the Python model
or ``scripts/check_story_plan.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from cyo_adventure.storyplan.models import StoryPlan

# #ASSUME: external-resource: parents[3] is the repo root, true only in the src-tree
# checkout (storyplan -> cyo_adventure -> src -> root), not an installed wheel.
# #VERIFY: dev-only regeneration tool; a packaged caller passes an explicit path.
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "storyplan.schema.json"


def build_schema() -> dict[str, object]:
    """Return the Story Plan JSON Schema as a dictionary.

    Returns:
        dict[str, object]: The JSON Schema produced from the Pydantic model.
    """
    return StoryPlan.model_json_schema()


def export_schema(path: Path = SCHEMA_PATH) -> Path:
    """Write the Story Plan JSON Schema to ``path``.

    Args:
        path: The destination file. Defaults to ``schema/storyplan.schema.json``.

    Returns:
        Path: The path that was written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def main() -> None:
    """Regenerate the committed JSON Schema and report the path."""
    written = export_schema()
    print(f"wrote {written}")  # noqa: T201 - intentional CLI output


if __name__ == "__main__":
    main()
