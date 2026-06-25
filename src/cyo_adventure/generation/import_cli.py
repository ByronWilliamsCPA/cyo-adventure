"""CLI: validate and import a filled story JSON into the store.

Usage:
    uv run python -m cyo_adventure.generation.import_cli <path> --family <family-uuid> [--model <model-id>]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from cyo_adventure.core.database import get_session
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.import_story import ImportRequest, import_filled_story


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the import CLI argument parser.

    Returns:
        Configured argument parser for the import command.
    """
    parser = argparse.ArgumentParser(
        description="Import a filled story into the store."
    )
    parser.add_argument("path", help="Path to the filled story JSON.")
    parser.add_argument("--family", required=True, help="Owning family UUID.")
    parser.add_argument("--model", default=None, help="Model id to record.")
    return parser


async def _run(blob: dict[str, object], family_id: uuid.UUID, model: str | None) -> str:
    """Validate and persist a filled story blob.

    Args:
        blob: The filled Storybook JSON already loaded from disk.
        family_id: Owning family UUID (parsed by the caller).
        model: Optional model identifier to record.

    Returns:
        The persisted story id.

    Raises:
        ValidationError: Propagated from the validation gate if it blocks the
            story (or the blob has no string id). UUID parsing is handled by the
            caller, so this no longer raises on an invalid family id.
    """
    request = ImportRequest(blob=blob, family_id=family_id, model=model)
    async with get_session() as session:
        story_id = await import_filled_story(session, request)
        await session.commit()
    return story_id


def main(argv: list[str] | None = None) -> int:
    """Parse args, import the story, and print the resulting story id.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 on success, 1 on any handled failure.
    """
    args = build_arg_parser().parse_args(argv)
    # Bind argparse Namespace attributes (typed Any) to explicit locals so the
    # rest of main stays strictly typed.
    path: str = args.path
    family: str = args.family
    model: str | None = args.model
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"error: cannot read {path}: {exc}\n")
        return 1
    try:
        raw_blob = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"error: invalid JSON in {path}: {exc}\n")
        return 1
    if not isinstance(raw_blob, dict):
        sys.stderr.write(
            f"error: expected a JSON object in {path}, got {type(raw_blob).__name__}\n"
        )
        return 1
    blob: dict[str, object] = raw_blob
    try:
        family_id = uuid.UUID(family)
    except ValueError:
        sys.stderr.write(f"error: invalid family UUID: {family}\n")
        return 1
    # #CRITICAL: data-integrity: ValidationError (a ProjectBaseError, not a
    # ValueError) is the only gate/import failure caught here; the UUID ValueError
    # catch above does not overlap with it.
    # #VERIFY: test_arg_parser_* cover parsing; gate failures map to exit 1.
    try:
        story_id = asyncio.run(_run(blob, family_id, model))
    except ValidationError as exc:
        sys.stderr.write(f"import failed: {exc}\n")
        return 1
    sys.stdout.write(f"imported {story_id}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
