#!/usr/bin/env python3
"""Generate PlantUML structure diagrams for every preset story skeleton.

Walks ``skeletons/**/*.json``, validates each via ``load_skeleton``, writes a
``.puml`` per skeleton under the output root (preserving the ``<band>/`` layout),
optionally renders ``.svg`` with a SHA-verified PlantUML jar, and supports a
``--check`` mode that fails when committed ``.puml`` files are stale.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess  # nosec B404 -- subprocess is used only with a SHA-verified jar; usage is audited below
import sys
import urllib.request
from pathlib import Path

from cyo_adventure.generation.diagram import skeleton_to_plantuml
from cyo_adventure.generation.skeleton import load_skeleton

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKELETONS = REPO_ROOT / "skeletons"
DEFAULT_OUT = REPO_ROOT / "docs" / "architecture" / "diagrams" / "skeletons"

# #CRITICAL: external resource: the render step downloads and executes a PlantUML jar.
# #VERIFY: pin version 1.2024.7, verify SHA-256 before any java invocation, and treat
#          download/verify failure as a skipped-SVG warning (exit 0), never as an
#          unverified execution.
PLANTUML_VERSION = "1.2024.7"
PLANTUML_SHA256 = "e34c12bbe9944f1f338ca3d88c9b116b86300cc8e90b35c4086b825b5ae96d24"
PLANTUML_URL = (
    f"https://github.com/plantuml/plantuml/releases/download/v{PLANTUML_VERSION}"
    f"/plantuml-{PLANTUML_VERSION}.jar"
)
JAR_CACHE = (
    Path.home() / ".cache" / "cyo-adventure" / f"plantuml-{PLANTUML_VERSION}.jar"
)


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


def verify_sha256(path: Path, expected: str) -> bool:
    """Return True if ``path``'s SHA-256 hex digest equals ``expected``."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest == expected.lower()


def resolve_jar() -> Path | None:
    """Return a path to a SHA-verified PlantUML jar, or None if unavailable.

    Resolution order: ``PLANTUML_JAR`` env var, then the version-pinned cache,
    then a one-time download. The jar is executed only after SHA-256 verification.
    """
    env = os.environ.get("PLANTUML_JAR")
    if env:
        candidate = Path(env)
        if candidate.is_file() and verify_sha256(candidate, PLANTUML_SHA256):
            return candidate
        return None
    if JAR_CACHE.is_file() and verify_sha256(JAR_CACHE, PLANTUML_SHA256):
        return JAR_CACHE
    JAR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    try:
        # URL is a pinned constant (PLANTUML_URL), not user-supplied input
        urllib.request.urlretrieve(PLANTUML_URL, JAR_CACHE)  # noqa: S310  # nosec B310
    except OSError:
        return None
    if JAR_CACHE.is_file() and verify_sha256(JAR_CACHE, PLANTUML_SHA256):
        return JAR_CACHE
    return None


def render_svgs(puml_paths: list[Path], *, jar: Path | None) -> list[Path]:
    """Render each ``.puml`` to ``.svg`` next to it. Returns rendered SVG paths.

    When ``jar`` is None the step is a no-op (returns ``[]``); callers warn rather
    than fail so the generator still produces committed ``.puml`` source.
    """
    if jar is None or not puml_paths:
        return []
    rendered: list[Path] = []
    for puml in puml_paths:
        # jar is SHA-256 verified before this call; list-form avoids shell injection
        subprocess.run(  # nosec B603 B607
            ["java", "-jar", str(jar), "-tsvg", str(puml)],
            check=True,
            capture_output=True,
        )
        svg = puml.with_suffix(".svg")
        if svg.is_file():
            rendered.append(svg)
    return rendered


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
    if not args.no_svg:
        jar = resolve_jar()
        if jar is None:
            _msg = (
                "PlantUML jar unavailable or unverified; skipped SVG rendering."
                " Set PLANTUML_JAR or allow network access to render.\n"
            )
            sys.stderr.write(_msg)
        else:
            rendered = render_svgs(written, jar=jar)
            sys.stdout.write(f"Rendered {len(rendered)} .svg file(s).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
