"""CLI: validate and import a filled story JSON into the store.

Usage:
    uv run python -m cyo_adventure.generation.import_cli <path> --family <family-uuid>
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


async def _run(blob: dict[str, object], family: str, model: str | None) -> str:
    """Validate and persist a filled story blob.

    Args:
        blob: The filled Storybook JSON already loaded from disk.
        family: Owning family UUID string.
        model: Optional model identifier to record.

    Returns:
        The persisted story id.

    Raises:
        ValidationError: If the validation gate blocks the story.
    """
    request = ImportRequest(blob=blob, family_id=uuid.UUID(family), model=model)
    async with get_session() as session:
        story_id = await import_filled_story(session, request)
        await session.commit()
    return story_id


def main(argv: list[str] | None = None) -> int:
    """Parse args, import the story, and print the resulting story id.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 on success, 1 on validation failure.
    """
    # #CRITICAL: data-integrity: JSON parsing and UUID conversion can raise at
    # runtime; callers see an unhandled traceback for bad paths or UUIDs.
    # #VERIFY: acceptable for a CLI tool where the operator controls both inputs;
    # ValidationError (gate failure) is the only caught exception.
    args = build_arg_parser().parse_args(argv)
    blob: dict[str, object] = json.loads(Path(args.path).read_text(encoding="utf-8"))
    try:
        story_id = asyncio.run(_run(blob, args.family, args.model))
    except ValidationError as exc:
        print(f"import failed: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    print(f"imported {story_id}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
