# pyright: reportImplicitStringConcatenation=false
# Ruff ISC003 requires implicit concatenation for wrapped messages and this
# BasedPyright rule forbids it; the two conflict, and Ruff is the project's gate.
"""Retained shapes: the shape registry and the v2 shape files (WP-2.2, D4).

ADR-033 Decision 5 freezes a shape (topology, node functions, word budgets,
ending mix) and generates meaning per book. Owner decision D4 (2026-11-21)
retained twelve shells, two per short and medium family cell. This module is
where a Story Plan or the catalog finds them.

Layout (repository-relative, read from the working directory exactly as
``generation/skeleton_match.py`` reads ``skeletons/``)::

    shapes/registry.json              the registry: id, cell, files, hash
    shapes/<band>/<slug>.json         the shape: the skeleton in the v2 grammar

**Why a copy and not the skeleton itself.** Every retained shell is
production-eligible and selectable by the live skeleton-fill path, which quotes
each node's beats to the fill model. Converting the file in place would strip
those beats from on-demand fills before the plan path that replaces them
(WP-2.3 to WP-2.6) exists, and ADR-033 Decision 5 keeps skeleton fill as built
selectable until the pilot shows plan-first is not worse. So ``skeletons/`` is
byte-identical and the v2 shape sits beside the catalog, outside every catalog
scan (``skeleton_match``, the mutation core, the flywheel, the census scripts
all walk ``skeletons/``). Nothing on the request path imports this module.

**Shape id and hash.** The id is the skeleton's slug (unique across bands;
``skeleton_match._locate_skeleton`` refuses a duplicate), so a plan built from
the v1 skeleton or from the v2 shape names the same shape. The hash is
:func:`cyo_adventure.storyplan.models.shape_hash`, which reads no body, so the
v1 source, the v2 shape and the registry all carry one value and a plan's
``provenance.shape`` binds to it. A structural edit to either file changes the
hash and stales every plan bound to it, which is SP-0's job to report.

The Storybook schema is untouched (ADR-025): the registry is a separate file,
and a shape file is a valid Storybook whose node bodies happen to be v2
directives.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.storybook.fill_directive import (
    convert_to_v2,
    v2_directive_violations,
)
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle, Storybook
from cyo_adventure.storyplan.models import shape_hash

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "REGISTRY_FILE",
    "SHAPES_ROOT",
    "RetainedShape",
    "ShapeRegistry",
    "dump_shape",
    "load_registry",
    "load_shape",
    "registry_problems",
    "shape_entry_for",
]

SHAPES_ROOT: Final[Path] = Path("shapes")
REGISTRY_FILE: Final[str] = "registry.json"

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
ShapeHash = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
RepoPath = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.+/-]+\.json$")]


class _Strict(BaseModel):
    """Base for the registry models: unknown keys are rejected, values frozen."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RetainedShape(_Strict):
    """One retained shape: its id, cell, files and graph hash.

    Attributes:
        id: The shape id, which is the source skeleton's slug.
        band: The age band (cell axis).
        length: The length tier (cell axis).
        narrative_style: The narrative style (cell axis; it partitions cells
            only at 13-16 and 16+).
        source: Repository path of the v1 skeleton the shape was converted from.
        file: Repository path of the v2 shape file.
        hash: :func:`shape_hash` of the shape, equal for source and file.
    """

    id: Slug
    band: AgeBand
    length: Length
    narrative_style: NarrativeStyle
    source: RepoPath
    file: RepoPath
    hash: ShapeHash


class ShapeRegistry(_Strict):
    """The committed list of retained shapes.

    Attributes:
        registry_version: Format version of this file.
        directive_version: The FILL grammar every shape file is written in.
        decision: Where the retained set was decided.
        shapes: The retained shapes, in registry order.
    """

    registry_version: Literal[1]
    directive_version: Literal[2]
    decision: str = Field(min_length=1)
    shapes: list[RetainedShape] = Field(min_length=1)


def _read_json(path: Path) -> dict[str, object]:
    """Read a JSON object from disk.

    Args:
        path: The file to read.

    Returns:
        dict[str, object]: The decoded object.

    Raises:
        ValidationError: If the file is missing, unreadable, not JSON, or not
            a JSON object.
    """
    # #ASSUME: external-resources: the registry and shape files are committed
    # beside the catalog and read from the working directory; a missing file is
    # a deployment or checkout error, reported as a ValidationError naming the
    # path rather than as a bare OSError.
    # #VERIFY: test_retained_shapes.py::test_a_missing_registry_is_reported.
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"cannot read {path}: {exc}"
        raise ValidationError(msg, field="path", value=str(path)) from exc
    if not isinstance(data, dict):
        msg = f"{path} does not hold a JSON object"
        raise ValidationError(msg, field="path", value=str(path))
    return cast("dict[str, object]", data)


def load_registry(root: Path | None = None) -> ShapeRegistry:
    """Load and validate ``shapes/registry.json``.

    Args:
        root: The repository root the registry's paths are relative to;
            defaults to the working directory.

    Returns:
        ShapeRegistry: The parsed registry.

    Raises:
        ValidationError: If the file cannot be read or does not match the
            registry schema.
    """
    raw = _read_json((root or Path()) / SHAPES_ROOT / REGISTRY_FILE)
    try:
        return ShapeRegistry.model_validate(raw)
    except ValueError as exc:
        msg = f"shape registry is malformed: {exc}"
        raise ValidationError(msg, field="registry") from exc


def shape_entry_for(registry: ShapeRegistry, shape_id: str) -> RetainedShape | None:
    """Return the registry entry for a shape id, or None when not retained.

    Args:
        registry: The loaded registry.
        shape_id: A shape id (a skeleton slug).

    Returns:
        RetainedShape | None: The entry, or None.
    """
    return next((entry for entry in registry.shapes if entry.id == shape_id), None)


def load_shape(entry: RetainedShape, root: Path | None = None) -> dict[str, object]:
    """Load a shape file and check it against its registry entry.

    Args:
        entry: The registry entry.
        root: The repository root.

    Returns:
        dict[str, object]: The decoded shape (a Storybook in the v2 grammar).

    Raises:
        ValidationError: If the file cannot be read, does not parse as a
            Storybook, breaks the v2 grammar, or hashes to something other than
            the registry's ``hash`` (a stale shape must never be handed to a
            plan as if it were the one the plan was bound to).
    """
    shape = _read_json((root or Path()) / entry.file)
    problems = v2_directive_violations(shape)
    if not problems and not shape_hash_matches(shape, entry.hash):
        problems = [f"shape {entry.id!r} does not hash to its registry hash"]
    if problems:
        msg = f"shape {entry.id!r} ({entry.file}) is not usable: {problems[0]}"
        raise ValidationError(msg, field="shape", value=entry.id)
    return shape


def shape_hash_matches(story: Mapping[str, object], expected: str) -> bool:
    """Return whether a decoded story's graph hashes to ``expected``.

    Args:
        story: Decoded skeleton or shape JSON.
        expected: A ``sha256:`` shape hash.

    Returns:
        bool: True on a match; False when it differs or does not parse.
    """
    try:
        book = Storybook.model_validate(story)
    except ValueError:
        return False
    return shape_hash(book) == expected


def dump_shape(shape: Mapping[str, object]) -> str:
    """Serialise a shape the way skeleton files are written.

    Args:
        shape: The decoded shape.

    Returns:
        str: Two-space indented JSON with a trailing newline, non-ASCII kept.
    """
    return json.dumps(shape, indent=2, ensure_ascii=False) + "\n"


def registry_problems(registry: ShapeRegistry, root: Path | None = None) -> list[str]:
    """Return every inconsistency between the registry and the files.

    Checks, per entry: the source skeleton exists and parses; the shape file is
    exactly :func:`~cyo_adventure.storybook.fill_directive.convert_to_v2` of the
    source as :func:`dump_shape` writes it (so a v1 edit to labels, titles,
    metadata or structure forces a regeneration, while a beats-only edit does
    not); source, shape and registry carry one hash; the cell axes match the
    source metadata; the file paths follow the layout. Across entries: ids and
    files are unique.

    Args:
        registry: The loaded registry.
        root: The repository root.

    Returns:
        list[str]: Human-readable problems; empty when consistent.
    """
    problems: list[str] = []
    seen: set[str] = set()
    for entry in registry.shapes:
        if entry.id in seen:
            problems.append(f"{entry.id}: listed twice")
        seen.add(entry.id)
        problems.extend(_entry_problems(entry, root or Path()))
    return problems


def _entry_problems(entry: RetainedShape, root: Path) -> list[str]:
    """Return the problems for one registry entry.

    Args:
        entry: The registry entry.
        root: The repository root.

    Returns:
        list[str]: Problems, prefixed with the shape id.
    """
    expected_source = f"skeletons/{entry.band}/{entry.id}.json"
    expected_file = f"{SHAPES_ROOT.as_posix()}/{entry.band}/{entry.id}.json"
    problems: list[str] = []
    if entry.source != expected_source:
        problems.append(f"{entry.id}: source should be {expected_source}")
    if entry.file != expected_file:
        problems.append(f"{entry.id}: file should be {expected_file}")
    try:
        source = _read_json(root / entry.source)
        book = Storybook.model_validate(source)
    except (ValidationError, ValueError) as exc:
        return [*problems, f"{entry.id}: source unreadable: {exc}"]
    metadata = book.metadata
    axes = (
        (entry.band, metadata.age_band),
        (entry.length, metadata.length),
        (entry.narrative_style, metadata.narrative_style),
    )
    if any(listed != declared for listed, declared in axes):
        problems.append(f"{entry.id}: registry cell differs from source metadata")
    if shape_hash(book) != entry.hash:
        problems.append(
            f"{entry.id}: source hashes to {shape_hash(book)}, not the registry hash"
        )
    shape_path = root / entry.file
    try:
        on_disk = shape_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [*problems, f"{entry.id}: shape file unreadable: {exc}"]
    if on_disk != dump_shape(convert_to_v2(source)):
        problems.append(
            f"{entry.id}: shape file is not the v2 conversion of its source; "
            "regenerate with scripts/retain_shapes.py"
        )
    return problems
