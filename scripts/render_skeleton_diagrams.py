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
from cyo_adventure.generation.skeleton import is_sidecar, load_skeleton
from cyo_adventure.generation.skeleton_catalog import (
    build_catalog_region,
    splice_region,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKELETONS = REPO_ROOT / "skeletons"
DEFAULT_OUT = REPO_ROOT / "docs" / "architecture" / "diagrams" / "skeletons"
DEFAULT_CATALOG = REPO_ROOT / "docs" / "architecture" / "story-skeletons.md"

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
        # Skip sidecars (WS-2 theme contracts and WS-5 lineage records): they
        # share the .json suffix and this rglob, but they are not skeletons (they
        # carry no id/nodes/etc), so load_skeleton would reject them. Excluded via
        # the shared is_sidecar predicate, the same way generation/skeleton_match.py
        # and the skeleton test discovery globs do.
        if is_sidecar(json_path):
            continue
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

    Every failure path writes a distinct message to stderr before returning
    ``None`` so an operator can tell a benign "nothing to use yet" skip apart
    from a security-relevant "found a jar but its hash did not match" failure;
    both used to produce the identical generic message.
    """
    env = os.environ.get("PLANTUML_JAR")
    if env:
        candidate = Path(env)
        if not candidate.is_file():
            sys.stderr.write(f"PLANTUML_JAR={env} does not exist.\n")
            return None
        if not verify_sha256(candidate, PLANTUML_SHA256):
            sys.stderr.write(
                f"PLANTUML_JAR={env} failed SHA-256 verification"
                f" (expected {PLANTUML_SHA256}); refusing to execute it.\n"
            )
            return None
        return candidate
    if JAR_CACHE.is_file():
        if verify_sha256(JAR_CACHE, PLANTUML_SHA256):
            return JAR_CACHE
        sys.stderr.write(
            f"Cached jar at {JAR_CACHE} failed SHA-256 verification"
            f" (expected {PLANTUML_SHA256}); attempting a fresh download.\n"
        )
    try:
        JAR_CACHE.parent.mkdir(parents=True, exist_ok=True)
        # #CRITICAL: external resource: fetches an executable jar over the network.
        # #VERIFY: PLANTUML_URL is a pinned constant, not user-supplied input; the
        # post-download SHA-256 check below (against PLANTUML_SHA256) is what makes
        # this safe to execute, not the download itself.
        urllib.request.urlretrieve(PLANTUML_URL, JAR_CACHE)  # noqa: S310  # nosec B310
    except OSError as exc:
        # This handler wraps both the cache-directory mkdir and the download
        # itself, so the message must not blame "download" for what could be
        # a permissions/read-only-filesystem failure creating JAR_CACHE.parent.
        sys.stderr.write(
            f"Could not download or prepare the PlantUML jar cache at"
            f" {JAR_CACHE.parent}: {exc}\n"
        )
        return None
    if not verify_sha256(JAR_CACHE, PLANTUML_SHA256):
        sys.stderr.write(
            "Downloaded jar failed SHA-256 verification"
            f" (expected {PLANTUML_SHA256}); refusing to execute it.\n"
        )
        return None
    return JAR_CACHE


def render_svgs(puml_paths: list[Path], *, jar: Path | None) -> list[Path]:
    """Render each ``.puml`` to ``.svg`` next to it. Returns rendered SVG paths.

    When ``jar`` is None the step is a no-op (returns ``[]``); callers warn rather
    than fail so the generator still produces committed ``.puml`` source. A
    missing ``java`` binary or a per-file render failure is likewise degraded to
    a stderr warning and a partial result rather than an uncaught exception: the
    jar's SHA-256 is already verified by ``resolve_jar`` before this runs, so a
    failure here is an environment or input problem, never an unverified execution.
    """
    if jar is None or not puml_paths:
        return []
    rendered: list[Path] = []
    for puml in puml_paths:
        try:
            # #CRITICAL: external resource: shells out to a subprocess to render SVGs.
            # #VERIFY: jar is SHA-256 verified before this call (see resolve_jar);
            # list-form argv avoids shell injection.
            subprocess.run(  # nosec B603 B607
                ["java", "-jar", str(jar), "-tsvg", str(puml)],
                check=True,
                capture_output=True,
            )
        except FileNotFoundError:
            sys.stderr.write("java executable not found; skipping SVG rendering.\n")
            break
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            sys.stderr.write(f"PlantUML failed to render {puml}: {stderr}\n")
            continue
        svg = puml.with_suffix(".svg")
        if svg.is_file():
            rendered.append(svg)
    return rendered


def regenerate_catalog(skeletons_dir: Path, catalog_path: Path) -> str:
    """Return the catalog doc text with its generated region refreshed from skeletons.

    Args:
        skeletons_dir: Root directory containing skeleton JSON files.
        catalog_path: Path to the catalog Markdown document to update.

    Returns:
        The full updated document text with the generated region spliced in.
    """
    skeletons: list[dict[str, object]] = []
    slugs: list[str] = []
    for json_path in sorted(skeletons_dir.rglob("*.json")):
        # Skip sidecars (contracts and lineage records; see generate_puml): not
        # skeletons.
        if is_sidecar(json_path):
            continue
        skeletons.append(load_skeleton(json_path))
        slugs.append(slug_for(json_path))
    region = build_catalog_region(skeletons, slugs=slugs)
    doc = catalog_path.read_text(encoding="utf-8")
    return splice_region(doc, region)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeletons-dir", type=Path, default=DEFAULT_SKELETONS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail (exit 1) if any committed .puml is stale; write nothing.",
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
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
        catalog_new = regenerate_catalog(args.skeletons_dir, args.catalog)
        if args.catalog.read_text(encoding="utf-8") != catalog_new:
            stale.append(args.catalog)
        if stale:
            sys.stderr.write(
                "Stale skeleton diagrams/catalog (re-run the generator and commit):\n"
                + "\n".join(f"  {p}" for p in stale)
                + "\n"
            )
            return 1
        sys.stdout.write(
            f"All {len(mapping)} skeleton diagrams and the catalog are up to date.\n"
        )
        return 0

    written = write_outputs(mapping)
    sys.stdout.write(f"Wrote {len(written)} .puml file(s).\n")
    args.catalog.write_text(
        regenerate_catalog(args.skeletons_dir, args.catalog), encoding="utf-8"
    )
    sys.stdout.write("Refreshed the story-skeleton catalog.\n")
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
