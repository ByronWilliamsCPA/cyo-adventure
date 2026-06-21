"""Export the Storybook JSON Schema from the Pydantic model.

Run as a module to (re)generate ``schema/storybook.schema.json`` from the single
source of truth in ``models.py``::

    uv run python -m cyo_adventure.storybook.schema_export

The JSON Schema is committed so non-Python consumers (the TypeScript client, CI
checks, external tooling) can validate Storybook blobs without importing Python.

Caveat: the exported JSON Schema captures field types and structural shape only. It
cannot encode the cross-field ``@model_validator`` rules (ending/choice agreement,
unique node/choice/ending ids, the condition-operator whitelist, declared-variable
references, effect/variable type agreement). A consumer validating against this schema
gets a strictly weaker check than the Pydantic models; authoritative validation still
requires the Python models or a faithful port of those rules.
"""

from __future__ import annotations

import json
from pathlib import Path

from cyo_adventure.storybook.models import Storybook

# #ASSUME: external-resource: parents[3] is the repo root, true only in the src-tree
# checkout (storybook -> cyo_adventure -> src -> root), not an installed wheel.
# #VERIFY: this is a dev-only regeneration tool; run it from the repo checkout. A
# packaged caller must pass an explicit path to export_schema() instead of relying on
# this default.
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "storybook.schema.json"


def build_schema() -> dict[str, object]:
    """Return the Storybook JSON Schema as a dictionary.

    Returns:
        dict[str, object]: The JSON Schema produced from the Pydantic model.
    """
    return Storybook.model_json_schema()


def export_schema(path: Path = SCHEMA_PATH) -> Path:
    """Write the Storybook JSON Schema to ``path``.

    Args:
        path (Path): The destination file. Defaults to
            ``schema/storybook.schema.json``.

    Returns:
        Path: The path that was written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = build_schema()
    path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def main() -> None:
    """Regenerate the committed JSON Schema and report the path."""
    written = export_schema()
    print(f"wrote {written}")  # noqa: T201 - intentional CLI output


if __name__ == "__main__":
    main()
