"""Build and check the retained shapes (WP-2.2, owner decision D4).

Usage:
    uv run python scripts/retain_shapes.py                 # check (default)
    uv run python scripts/retain_shapes.py --write         # regenerate files
    uv run python scripts/retain_shapes.py --add skeletons/8-11/<slug>.json

A retained shape is a v1 skeleton converted to the typed v2 directive grammar
(``<<FILL v=2 role=... words=... function=...>>``, no beats) and written to
``shapes/<band>/<slug>.json``; ``shapes/registry.json`` lists each one with its
cell, its files and its :func:`~cyo_adventure.storyplan.models.shape_hash`. The
v1 skeleton under ``skeletons/`` is never modified: see
:mod:`cyo_adventure.storyplan.shapes` for why the shape is a copy.

``--check`` (the default) fails when any shape file is not exactly the v2
conversion of its source, when a hash disagrees, or when the registry is
malformed. ``--write`` rewrites every shape file and registry hash from the
sources. ``--add`` appends sources to the registry (then writes). Neither ever
writes under ``skeletons/``.

Exit codes:
    0 - consistent (check) or written (write/add).
    1 - a problem was found, or a source could not be converted.
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from cyo_adventure.core.exceptions import ProjectBaseError
from cyo_adventure.storybook.fill_directive import convert_to_v2
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storyplan.models import shape_hash
from cyo_adventure.storyplan.shapes import (
    REGISTRY_FILE,
    SHAPES_ROOT,
    RetainedShape,
    ShapeRegistry,
    dump_shape,
    load_registry,
    registry_problems,
)

_DEFAULT_DECISION = (
    "D4, decided 2026-11-21 (docs/planning/story-plan-implementation-plan.md "
    "decision table; docs/planning/d4-retained-shell-proposal.md)"
)


def _entry_from_source(source: Path) -> RetainedShape:
    """Build a registry entry from a v1 skeleton path.

    Args:
        source: Repository-relative path ``skeletons/<band>/<slug>.json``.

    Returns:
        RetainedShape: The entry, hashed from the source.

    Raises:
        ProjectBaseError: If the path is not under ``skeletons/<band>/``.
        ValueError: If the source does not parse as a Storybook.
    """
    parts = source.as_posix().split("/")
    if len(parts) != 3 or parts[0] != "skeletons":
        msg = f"{source}: expected skeletons/<band>/<slug>.json"
        raise ProjectBaseError(msg)
    book = Storybook.model_validate_json(source.read_text(encoding="utf-8"))
    length = book.metadata.length
    if length is None:
        msg = f"{source}: declares no length tier, so it has no cell to retain in"
        raise ProjectBaseError(msg)
    slug = source.stem
    return RetainedShape(
        id=slug,
        band=book.metadata.age_band,
        length=length,
        narrative_style=book.metadata.narrative_style,
        source=source.as_posix(),
        file=f"{SHAPES_ROOT.as_posix()}/{parts[1]}/{slug}.json",
        hash=shape_hash(book),
    )


def _write(registry: ShapeRegistry) -> ShapeRegistry:
    """Regenerate every shape file and hash, then write the registry.

    Args:
        registry: The registry whose entries name the sources.

    Returns:
        ShapeRegistry: The registry as written.
    """
    entries: list[RetainedShape] = []
    for entry in registry.shapes:
        source_path = Path(entry.source)
        source = cast(
            "dict[str, object]", json.loads(source_path.read_text(encoding="utf-8"))
        )
        rebuilt = _entry_from_source(source_path)
        shape_file = Path(rebuilt.file)
        shape_file.parent.mkdir(parents=True, exist_ok=True)
        shape_file.write_text(dump_shape(convert_to_v2(source)), encoding="utf-8")
        entries.append(rebuilt)
    written = registry.model_copy(update={"shapes": entries})
    payload = written.model_dump(mode="json")
    (SHAPES_ROOT / REGISTRY_FILE).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return written


def main(argv: list[str] | None = None) -> int:
    """Check, write, or extend the retained shapes.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code per the module docstring.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Regenerate files.")
    mode.add_argument(
        "--add", nargs="+", type=Path, default=None, help="Append v1 sources."
    )
    args = parser.parse_args(argv)
    add: list[Path] | None = args.add  # pyright: ignore[reportAny]
    write: bool = args.write  # pyright: ignore[reportAny]
    try:
        if add is not None:
            registry_path = SHAPES_ROOT / REGISTRY_FILE
            current = load_registry() if registry_path.is_file() else None
            registry = ShapeRegistry(
                registry_version=1,
                directive_version=2,
                decision=_DEFAULT_DECISION if current is None else current.decision,
                shapes=[
                    *(current.shapes if current is not None else []),
                    *(_entry_from_source(path) for path in add),
                ],
            )
            _write(registry)
        elif write:
            _write(load_registry())
        problems = registry_problems(load_registry())
    except (ProjectBaseError, OSError, ValueError) as exc:
        sys.stderr.write(f"FAIL {exc}\n")
        return 1
    for problem in problems:
        sys.stderr.write(f"FAIL {problem}\n")
    if problems:
        return 1
    count = len(load_registry().shapes)
    sys.stdout.write(f"ok: {count} retained shapes consistent with their sources\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
