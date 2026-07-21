#!/usr/bin/env python3
"""Render the hand-authored top-level architecture diagrams to SVG.

Unlike ``scripts/render_skeleton_diagrams.py`` (which *generates* ``.puml`` from
skeleton JSON), the diagrams under ``docs/architecture/diagrams/*.puml`` are
hand-authored. This tool only renders their sibling ``.svg`` files and reports
staleness; it never writes ``.puml`` source.

Reuse, not duplication: the SHA-256-pinned PlantUML jar resolver and the
per-file SVG renderer are imported from ``scripts.render_skeleton_diagrams`` so
the pinned version/hash (v1.2024.7) lives in exactly one place. That module's
``render_svgs`` invokes ``java -jar ... -tsvg <file>`` once per diagram and
derives each output path from the source stem, so it is immune to the
mtime-glob-rename SVG corruption that afflicts "newest file in the directory"
generators (every diagram's ``@startuml`` name matches its filename).

Modes:
    (no args)   Render only stale diagrams (missing or older-than-source SVG).
    --check     Report stale diagrams and exit non-zero; render nothing. Needs
                no jar, so it is safe to run in CI as a freshness gate.
    --all       Force re-render every diagram.

Staleness is decided by modification time: a diagram is stale when its ``.svg``
is missing or older than its ``.puml``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Make the repo root importable so ``scripts`` resolves as a namespace package
# whether this tool is run as ``python tools/generate_diagram_svgs.py`` (sys.path
# starts at tools/) or imported under pytest (rootdir already on the path).
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.render_skeleton_diagrams import (  # noqa: E402  (path set above)
    render_svgs,
    resolve_jar,
)

DIAGRAMS_DIR = REPO_ROOT / "docs" / "architecture" / "diagrams"


def _is_renderable(puml: Path) -> bool:
    """Return True if ``puml`` contains a real (non-comment) ``@startuml`` line.

    Include-only files such as ``style.puml`` carry shared skinparams and colour
    constants but no diagram of their own; their only ``@startuml`` tokens live
    inside ``'`` comments. Rendering them produces junk output, so they are
    filtered out. A line counts as a diagram start only when ``@startuml`` is the
    first token after stripping leading whitespace (a leading ``'`` comment
    marker therefore excludes it).

    Args:
        puml: Path to a ``.puml`` file.

    Returns:
        True when the file declares at least one renderable diagram.
    """
    text = puml.read_text(encoding="utf-8")
    return any(line.lstrip().startswith("@startuml") for line in text.splitlines())


def top_level_pumls(diagrams_dir: Path) -> list[Path]:
    """Return the hand-authored, renderable top-level ``.puml`` files, sorted.

    Uses a non-recursive glob so the ~60 auto-generated skeleton diagrams under
    ``diagrams/skeletons/`` (owned by ``scripts/render_skeleton_diagrams.py``)
    are excluded, and drops include-only files (e.g. ``style.puml``) that carry
    no diagram of their own.

    Args:
        diagrams_dir: The ``docs/architecture/diagrams`` directory.

    Returns:
        Sorted list of renderable top-level ``.puml`` paths.
    """
    return sorted(p for p in diagrams_dir.glob("*.puml") if _is_renderable(p))


def is_stale(puml: Path) -> bool:
    """Return True if ``puml``'s sibling SVG is missing or older than the source.

    Args:
        puml: Path to a ``.puml`` file.

    Returns:
        True when the ``.svg`` does not exist or predates the ``.puml``.
    """
    svg = puml.with_suffix(".svg")
    if not svg.is_file():
        return True
    return svg.stat().st_mtime < puml.stat().st_mtime


def find_duplicate_svgs(pumls: list[Path]) -> list[tuple[Path, Path]]:
    """Return pairs of sibling SVGs with byte-identical content.

    A defensive check against the mtime-glob-rename corruption class: two
    distinct diagrams should never render to identical SVGs. Any pair reported
    here means a rendering step overwrote one diagram's output with another's.

    Args:
        pumls: The ``.puml`` files whose ``.svg`` siblings should be compared.

    Returns:
        List of ``(svg_a, svg_b)`` pairs that are byte-for-byte identical.
    """
    digests: dict[bytes, Path] = {}
    dupes: list[tuple[Path, Path]] = []
    for puml in pumls:
        svg = puml.with_suffix(".svg")
        if not svg.is_file():
            continue
        content = svg.read_bytes()
        if content in digests:
            dupes.append((digests[content], svg))
        else:
            digests[content] = svg
    return dupes


def _rel(path: Path) -> str:
    """Return ``path`` relative to the repo root when possible, else as-is."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report stale diagrams and exit 1 if any; render nothing.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-render every diagram, not just stale ones.",
    )
    parser.add_argument(
        "--diagrams-dir",
        type=Path,
        default=DIAGRAMS_DIR,
        help="Directory holding the top-level .puml files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        Process exit code: 0 on success, 1 when ``--check`` finds stale
        diagrams or when a duplicate-SVG corruption is detected.
    """
    args = _build_parser().parse_args(argv)
    pumls = top_level_pumls(args.diagrams_dir)
    if not pumls:
        sys.stderr.write(f"No .puml files found in {_rel(args.diagrams_dir)}.\n")
        return 1

    if args.check:
        stale = [p for p in pumls if is_stale(p)]
        if stale:
            sys.stderr.write(
                "Stale diagrams (SVG missing or older than PUML; re-run"
                " `python tools/generate_diagram_svgs.py` and commit):\n"
                + "\n".join(f"  {_rel(p)}" for p in stale)
                + "\n"
            )
            return 1
        sys.stdout.write(f"All {len(pumls)} top-level diagrams are up to date.\n")
        return 0

    targets = pumls if args.all else [p for p in pumls if is_stale(p)]
    if not targets:
        sys.stdout.write("Nothing to render; all diagrams are up to date.\n")
        return 0

    jar = resolve_jar()
    if jar is None:
        sys.stderr.write(
            "PlantUML jar unavailable or unverified; cannot render."
            " Set PLANTUML_JAR to a verified jar or allow network access.\n"
        )
        return 1

    rendered = render_svgs(targets, jar=jar)
    sys.stdout.write(f"Rendered {len(rendered)}/{len(targets)} diagram(s) to SVG.\n")

    # #EDGE: data integrity: two diagrams must never share an SVG. A duplicate
    # here signals a renderer that clobbered one output with another's content.
    # #VERIFY: compare rendered bytes across all top-level SVGs and fail loudly.
    dupes = find_duplicate_svgs(pumls)
    if dupes:
        sys.stderr.write("Duplicate (byte-identical) sibling SVGs detected:\n")
        for a, b in dupes:
            sys.stderr.write(f"  {_rel(a)} == {_rel(b)}\n")
        return 1

    if len(rendered) != len(targets):
        sys.stderr.write(
            f"Warning: {len(targets) - len(rendered)} diagram(s) did not render;"
            " see messages above.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
