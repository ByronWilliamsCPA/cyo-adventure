#!/usr/bin/env python3
"""Generate PlantUML structure diagrams for every preset story skeleton.

Walks ``skeletons/**/*.json``, validates each via ``load_skeleton``, writes a
``.puml`` per skeleton under the output root (preserving the ``<band>/`` layout),
optionally renders ``.svg`` with a verified PlantUML jar, and supports a
``--check`` mode that fails when committed ``.puml`` files are stale.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cyo_adventure.generation.diagram import skeleton_to_plantuml
from cyo_adventure.generation.skeleton import load_skeleton

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKELETONS = REPO_ROOT / "skeletons"
DEFAULT_OUT = REPO_ROOT / "docs" / "architecture" / "diagrams" / "skeletons"


def slug_for(path: Path) -> str:
    """Return the diagram slug for a skeleton file (its filename stem)."""
    return path.stem


def generate_puml(skeletons_dir: Path, out_root: Path) -> dict[Path, str]:
    """Return a mapping of output ``.puml`` path -> PlantUML source.

    Validates every skeleton via ``load_skeleton`` (raises on structural failure).
    Output paths mirror the ``<band>/`` subdirectory layout of the input.
    """
    mapping: dict[Path, str] = {}
    for json_path in sorted(skeletons_dir.rglob("*.json")):
        data = load_skeleton(json_path)
        slug = slug_for(json_path)
        rel_dir = json_path.parent.relative_to(skeletons_dir)
        out_path = out_root / rel_dir / f"{slug}.puml"
        mapping[out_path] = skeleton_to_plantuml(data, name=slug)
    return mapping


def write_outputs(mapping: dict[Path, str]) -> list[Path]:
    """Write each ``.puml`` file, creating parent directories. Returns paths written."""
    written: list[Path] = []
    for path, content in mapping.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def check_outputs(mapping: dict[Path, str]) -> list[Path]:
    """Return paths whose on-disk content differs from the freshly-generated source."""
    stale: list[Path] = []
    for path, content in mapping.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            stale.append(path)
    return stale


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeletons-dir", type=Path, default=DEFAULT_SKELETONS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail (exit 1) if any committed .puml is stale; write nothing.",
    )
    parser.add_argument(
        "--no-svg",
        action="store_true",
        help="Skip SVG rendering even when a PlantUML jar is available.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    args = _build_parser().parse_args(argv)
    mapping = generate_puml(args.skeletons_dir, args.out_dir)

    if args.check:
        stale = check_outputs(mapping)
        if stale:
            sys.stderr.write(
                "Stale skeleton diagrams (re-run the generator and commit):\n"
                + "\n".join(f"  {p}" for p in stale)
                + "\n"
            )
            return 1
        sys.stdout.write(f"All {len(mapping)} skeleton diagrams are up to date.\n")
        return 0

    written = write_outputs(mapping)
    sys.stdout.write(f"Wrote {len(written)} .puml file(s).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
