"""Batch-import the pre-authored draft story catalog into the review pipeline.

Loads every filled story listed in ``docs/planning/draft-stories-manifest.md``
(23 distinct stories plus 2 "Cave of Echoes" pilot re-theme variants, 25
total) and imports each through :func:`cyo_adventure.generation.import_story.import_filled_story`,
owned by ``CATALOG_FAMILY_ID`` (the sentinel catalog family seeded by
migration ``20260718020000_seed_catalog_family.sql``). Three of the 25 files
carry an older Storybook schema shape (missing ``topology``, stale
``ending.type`` fields, ``schema_version: "1.0"``) and are normalized against
their source skeleton before import; see :func:`_normalize_legacy_fill`.

This module only IMPORTS: it runs the validator gate, persists a draft, and
runs moderation, leaving each story at ``in_review`` or ``needs_revision``.
It never publishes (ADR-005 mandatory human approval); promotion to
``published``/``catalog`` visibility is a separate, explicitly-invoked step
(see ``publishing/catalog_publish.py``).

Usage:
    uv run python -m cyo_adventure.generation.import_catalog
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from sqlalchemy.exc import SQLAlchemyError

from cyo_adventure.core.database import get_session
from cyo_adventure.core.exceptions import ProjectBaseError, ValidationError
from cyo_adventure.db.models import CATALOG_FAMILY_ID, Storybook
from cyo_adventure.generation.import_story import ImportRequest, import_filled_story
from cyo_adventure.generation.skeleton_match import resolve_skeleton_path

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

_DEFAULT_MODEL = "catalog-import"
_PROMPT_VERSION = "catalog-import-v1"

Outcome = Literal["imported", "skipped_existing", "gate_blocked", "error"]

_OUTCOME_ORDER: tuple[Outcome, ...] = (
    "imported",
    "skipped_existing",
    "gate_blocked",
    "error",
)


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One manifest row: a filled story file plus its skeleton provenance.

    Attributes:
        title: Human-readable story title, for the batch summary only.
        path: Path to the filled JSON, relative to the repo root.
        skeleton_band: The age-band directory segment the source skeleton
            lives under (e.g. "8-11" or "16+").
        skeleton_slug: The source skeleton's filename stem, threaded into
            ``ImportRequest.skeleton_slug`` for recency-weighted skeleton
            pick provenance (see import_story.py::ImportRequest docstring).
        id_suffix: When set, appended to the blob's own ``id`` (joined with
            "__") before the idempotency check and import. Required for the
            two pilot re-theme variants: both share the blob id
            ``sk_cave_of_echoes`` with the main Cave of Echoes entry, and
            persist_storybook always INSERTs (no upsert), so importing all
            three unmodified would collide on the primary key.
    """

    title: str
    path: str
    skeleton_band: str
    skeleton_slug: str
    id_suffix: str | None = None


# Explicit, manifest-driven enumeration (not a glob over out/*.filled.json):
# self-documents against docs/planning/draft-stories-manifest.md and will not
# silently pick up a future stray file dropped into out/. The 8 files under
# tests/data/diversity_panel/ are eval-only and are deliberately absent here.
CATALOG_ENTRIES: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        "Clover and the Butterfly",
        "out/the-clover-and-the-butterfly.filled.json",
        "3-5",
        "the-clover-and-the-butterfly",
    ),
    CatalogEntry(
        "The Lost Mitten",
        "out/the-lost-mitten.filled.json",
        "3-5",
        "the-lost-mitten",
    ),
    CatalogEntry(
        "The Teddy Bears' Picnic",
        "out/the-teddy-bears-picnic.filled.json",
        "3-5",
        "the-teddy-bears-picnic",
    ),
    CatalogEntry(
        "The Backyard Treasure Map",
        "out/the-backyard-treasure-map.filled.json",
        "5-8",
        "the-backyard-treasure-map",
    ),
    CatalogEntry(
        "The Lantern Festival",
        "out/the-lantern-festival.filled.json",
        "5-8",
        "the-lantern-festival",
    ),
    CatalogEntry(
        "The Cave of Echoes",
        "out/the-cave-of-echoes.filled.json",
        "8-11",
        "the-cave-of-echoes",
    ),
    CatalogEntry(
        "The Clockwork Menagerie",
        "out/the-clockwork-menagerie.filled.json",
        "8-11",
        "the-clockwork-menagerie",
    ),
    CatalogEntry(
        "The Sky-Ship Stowaway",
        "out/the-sky-ship-stowaway.filled.json",
        "8-11",
        "the-sky-ship-stowaway",
    ),
    CatalogEntry(
        "The Clocktower Cipher",
        "out/the-clocktower-cipher.filled.json",
        "10-13",
        "the-clocktower-cipher",
    ),
    CatalogEntry(
        "The Hollow Lighthouse",
        "out/the-hollow-lighthouse.filled.json",
        "10-13",
        "the-hollow-lighthouse",
    ),
    CatalogEntry(
        "The Mapmaker's Island",
        "out/the-mapmakers-island.filled.json",
        "10-13",
        "the-mapmakers-island",
    ),
    CatalogEntry(
        "The Midnight Museum",
        "out/the-midnight-museum.filled.json",
        "10-13",
        "the-midnight-museum",
    ),
    CatalogEntry(
        "The Harrowstone Keep",
        "out/the-harrowstone-keep.filled.json",
        "13-16",
        "the-harrowstone-keep",
    ),
    CatalogEntry(
        "The Signal in the Static",
        "out/the-signal-in-the-static.filled.json",
        "13-16",
        "the-signal-in-the-static",
    ),
    CatalogEntry(
        "The Sunken Temple",
        "out/the-sunken-temple.filled.json",
        "13-16",
        "the-sunken-temple",
    ),
    CatalogEntry(
        "The Sunspire Ascent",
        "out/the-sunspire-ascent.filled.json",
        "13-16",
        "the-sunspire-ascent",
    ),
    CatalogEntry(
        "The Thornwood Trial",
        "out/the-thornwood-trial.filled.json",
        "13-16",
        "the-thornwood-trial",
    ),
    CatalogEntry(
        "The Vanishing Orchard",
        "out/the-vanishing-orchard.filled.json",
        "13-16",
        "the-vanishing-orchard",
    ),
    CatalogEntry(
        "The Ashfall Expedition",
        "out/the-ashfall-expedition.filled.json",
        "16+",
        "the-ashfall-expedition",
    ),
    CatalogEntry(
        "The Drowned Court",
        "out/the-drowned-court.filled.json",
        "16+",
        "the-drowned-court",
    ),
    CatalogEntry(
        "The Last Train North",
        "out/the-last-train-north.filled.json",
        "16+",
        "the-last-train-north",
    ),
    CatalogEntry(
        "The Salt Archive",
        "out/the-salt-archive.filled.json",
        "16+",
        "the-salt-archive",
    ),
    CatalogEntry(
        "The Sunken Signal",
        "out/the-sunken-signal.filled.json",
        "16+",
        "the-sunken-signal",
    ),
    CatalogEntry(
        "The Cave of Echoes (dino-dig)",
        "out/pilot/fills/the-cave-of-echoes.dino-dig.filled.json",
        "8-11",
        "the-cave-of-echoes",
        id_suffix="dino-dig",
    ),
    CatalogEntry(
        "The Cave of Echoes (space-station)",
        "out/pilot/fills/the-cave-of-echoes.space-station.filled.json",
        "8-11",
        "the-cave-of-echoes",
        id_suffix="space-station",
    ),
)


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    """Result of attempting to import one :class:`CatalogEntry`.

    Attributes:
        entry: The manifest entry this outcome is for.
        story_id: The (possibly id_suffix-rewritten) story id, when known.
            None only for a load failure so early no id could be computed.
        outcome: One of the four outcome buckets.
        detail: Human-readable context (error message, or the persisted
            story's post-import status).
    """

    entry: CatalogEntry
    story_id: str | None
    outcome: Outcome
    detail: str = ""


def _load_blob(repo_root: Path, rel_path: str) -> dict[str, object]:
    """Read and parse a manifest entry's filled story JSON.

    Args:
        repo_root: The repository root the entry's path is relative to.
        rel_path: The entry's ``path`` (repo-root-relative).

    Returns:
        The parsed JSON object.

    Raises:
        ValidationError: If the file is not valid JSON, or its top-level
            value is not a JSON object.
        OSError: If the file cannot be read (propagated as-is; the caller
            classifies this into the "error" outcome bucket).
    """
    # #ASSUME: external-resources: every path in CATALOG_ENTRIES is a fixed,
    # git-tracked, repo-root-relative literal (never user/LLM-supplied), so
    # this skips the path-traversal guard import_cli.py::_load_blob applies
    # to its own CLI-argument path. If this module ever grows a mode that
    # accepts an externally-supplied path, add that guard back.
    # #VERIFY: CATALOG_ENTRIES is a hardcoded tuple; no test exercises an
    # untrusted path here by design.
    raw = (repo_root / rel_path).read_text(encoding="utf-8")
    try:
        blob = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"invalid JSON in {rel_path}: {exc}"
        raise ValidationError(msg, field="path", value=rel_path) from exc
    if not isinstance(blob, dict):
        msg = f"expected a JSON object in {rel_path}, got {type(blob).__name__}"
        raise ValidationError(msg, field="path", value=rel_path)
    return blob


def _needs_legacy_normalization(blob: dict[str, object]) -> bool:
    """Detect the older Storybook shape structurally, not by filename.

    A legacy blob is missing the (now-required) ``metadata.topology`` field,
    or declares a ``schema_version`` other than the current "2.0". Detecting
    this structurally (rather than hardcoding the 3 known filenames) means
    any future manifest entry with the same stale shape is caught
    automatically instead of silently failing the gate.

    Args:
        blob: The parsed filled story JSON.

    Returns:
        True if the blob needs :func:`_normalize_legacy_fill` before it can
        pass :func:`cyo_adventure.validator.gate.run_gate`.
    """
    metadata = blob.get("metadata")
    if blob.get("schema_version") != "2.0":
        return True
    return not (isinstance(metadata, dict) and "topology" in metadata)


def _load_reference_skeleton(band: str, slug: str) -> dict[str, object]:
    """Load the raw skeleton shell a legacy fill was authored from.

    Deliberately a raw ``json.loads`` read, not
    :func:`cyo_adventure.generation.skeleton.load_skeleton`: that helper runs
    the full validation gate, which a raw skeleton shell (still carrying
    unfilled ``<<FILL>>`` directives) is not expected to pass.

    Args:
        band: The age-band directory segment.
        slug: The skeleton's filename stem.

    Returns:
        The parsed skeleton document.

    Raises:
        ValidationError: If the resolved path escapes the skeleton root, or
            the file is missing or not valid JSON.
    """
    # #ASSUME: external-resources: resolve_skeleton_path (like the rest of
    # the codebase's skeleton machinery, see skeleton_match.py::_SKELETON_ROOT)
    # resolves "skeletons/<band>/<slug>.json" against the process's current
    # working directory, not an explicit repo-root parameter; this function
    # therefore requires the process to be launched from the repo root,
    # matching import_cli.py's own established convention. Its containment
    # check still applies even though band/slug here originate from
    # CATALOG_ENTRIES (a hardcoded tuple, not untrusted input) so behavior
    # stays consistent with the rest of the codebase's skeleton resolution.
    # #VERIFY: test_normalize_legacy_fill_matches_source_skeleton exercises
    # this against the real skeletons/ tree for all 3 legacy entries.
    resolved = resolve_skeleton_path(band, slug)
    try:
        raw = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"skeleton not found for legacy normalization: {resolved}"
        raise ValidationError(msg, field="skeleton_slug", value=slug) from exc
    try:
        skeleton = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"skeleton is not valid JSON: {resolved}"
        raise ValidationError(msg, field="skeleton_slug", value=slug) from exc
    if not isinstance(skeleton, dict):
        msg = f"expected a JSON object in skeleton {resolved}"
        raise ValidationError(msg, field="skeleton_slug", value=slug)
    return skeleton


def _normalize_legacy_fill(
    blob: dict[str, object], skeleton: dict[str, object]
) -> dict[str, object]:
    """Backfill a legacy-shape fill to the current schema, in place.

    Three normalizations, empirically verified (via direct ``run_gate()``
    calls against all 3 affected files) to be exactly what is required to
    clear the validation gate, each copied verbatim from the source skeleton
    rather than invented:

    1. ``schema_version``: bumped to "2.0" (the current model only accepts
       this value; the fills were serialized against a stale "1.0" writer).
    2. ``metadata.topology`` and ``metadata.production_eligible``: backfilled
       from the skeleton's own metadata. ``topology`` is a required field
       with no default. ``production_eligible`` is preserved as ``False``
       (all 3 affected skeletons declare it explicitly), not defaulted to the
       Pydantic-model default of ``True``: these are structurally MVP/Test-
       tier skeletons (resolve_node_budget's band-independent MVP envelope,
       not a production-cell budget, governed their node counts), and
       silently promoting them to production-eligible would apply the wrong
       budget check retroactively.
    3. Each ending-bearing node's ``ending`` dict: the fills carry a stale
       ``{id, type, title}`` shape; the current model requires
       ``{id, valence, kind, title}``. Replaced wholesale with the matching
       skeleton node's ``ending`` dict (matched by node id) rather than
       migrated field-by-field, since every id/title pair was verified to
       match exactly between fill and skeleton across all 3 files.

    Args:
        blob: The parsed filled story JSON (mutated in place and returned).
        skeleton: The parsed source skeleton (see
            :func:`_load_reference_skeleton`).

    Returns:
        The same ``blob`` dict, mutated.

    Raises:
        ValidationError: If a node needing ending normalization has no
            id-matching counterpart in the skeleton, or its skeleton ending
            is not a dict. This should not happen for the 3 known legacy
            files (verified 0 mismatches), so it only guards a future
            manifest entry misclassified as legacy.
    """
    blob["schema_version"] = "2.0"
    _normalize_legacy_metadata(blob, skeleton)
    _normalize_legacy_endings(blob, skeleton)
    return blob


def _normalize_legacy_metadata(
    blob: dict[str, object], skeleton: dict[str, object]
) -> None:
    """Backfill ``metadata.topology``/``production_eligible`` in place.

    Split out of :func:`_normalize_legacy_fill` to keep each helper's
    branching under the project's complexity limit. See that function's
    docstring (item 2) for why both values are copied verbatim from the
    skeleton rather than defaulted.

    Args:
        blob: The parsed filled story JSON (mutated in place).
        skeleton: The parsed source skeleton.
    """
    metadata = blob.get("metadata")
    skel_metadata = skeleton.get("metadata")
    if not (isinstance(metadata, dict) and isinstance(skel_metadata, dict)):
        return
    for key in ("topology", "production_eligible"):
        if key not in metadata and key in skel_metadata:
            metadata[key] = skel_metadata[key]


def _index_skeleton_nodes_by_id(
    skeleton: dict[str, object],
) -> dict[str, dict[str, object]]:
    """Build a node-id-to-node lookup from a parsed skeleton document.

    Args:
        skeleton: The parsed source skeleton.

    Returns:
        A dict mapping each node's string ``id`` to its node dict; nodes
        with a missing or non-string id are skipped.
    """
    skel_nodes: dict[str, dict[str, object]] = {}
    skel_node_list = skeleton.get("nodes")
    if not isinstance(skel_node_list, list):
        return skel_nodes
    for skel_node in skel_node_list:
        if isinstance(skel_node, dict):
            node_id = skel_node.get("id")
            if isinstance(node_id, str):
                skel_nodes[node_id] = skel_node
    return skel_nodes


def _normalize_legacy_endings(
    blob: dict[str, object], skeleton: dict[str, object]
) -> None:
    """Replace every stale ``{id, type, title}`` ending with the current shape.

    Split out of :func:`_normalize_legacy_fill` to keep each helper's
    branching under the project's complexity limit. See that function's
    docstring (item 3) for why endings are replaced wholesale rather than
    migrated field-by-field.

    Args:
        blob: The parsed filled story JSON (mutated in place).
        skeleton: The parsed source skeleton.

    Raises:
        ValidationError: If a node needing ending normalization has no
            id-matching counterpart in the skeleton, or its skeleton ending
            is not a dict.
    """
    skel_nodes = _index_skeleton_nodes_by_id(skeleton)
    nodes = blob.get("nodes")
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        ending = node.get("ending")
        if not isinstance(ending, dict) or "kind" in ending:
            continue  # already current shape, or no ending on this node
        node_id = node.get("id")
        skel_node = skel_nodes.get(node_id) if isinstance(node_id, str) else None
        skel_ending = skel_node.get("ending") if skel_node is not None else None
        if not isinstance(skel_ending, dict):
            msg = (
                f"cannot normalize legacy ending for node {node_id!r}: "
                "no matching skeleton ending"
            )
            raise ValidationError(msg, field="nodes", value=node_id)
        node["ending"] = dict(skel_ending)


@dataclass(frozen=True, slots=True)
class ImportConfig:
    """Grouped run parameters for :func:`import_catalog` / :func:`_import_one`.

    Bundled into one object (mirroring ``import_story.py``'s own
    ``_ResumeStage1Context`` pattern) so those functions stay under the
    project's argument-count limit while keeping each field explicit.

    Attributes:
        repo_root: Repository root every entry's ``path`` is relative to.
            ``None`` (the default) resolves to ``Path.cwd()`` at call time,
            matching ``import_cli.py``'s and ``skeleton_match.py``'s own
            convention of resolving relative to the process cwd (skeleton
            lookups always resolve against cwd regardless of this field; see
            :func:`_load_reference_skeleton`).
        model: Model identifier recorded on every imported version.
        prompt_version: Prompt/skill version recorded on every imported
            version.
    """

    repo_root: Path | None = None
    model: str = _DEFAULT_MODEL
    prompt_version: str = _PROMPT_VERSION


def _prepare_blob(
    repo_root: Path, entry: CatalogEntry
) -> tuple[str, dict[str, object]] | ImportOutcome:
    """Load, id-suffix, and (if needed) legacy-normalize one entry's blob.

    Args:
        repo_root: Repository root ``entry.path`` is relative to.
        entry: The manifest entry to prepare.

    Returns:
        ``(story_id, blob)`` on success, or a terminal ``ImportOutcome``
        (outcome "error") describing the first failure.
    """
    try:
        blob = _load_blob(repo_root, entry.path)
    except (OSError, ValidationError) as exc:
        return ImportOutcome(entry, None, "error", f"load failed: {exc}")

    if entry.id_suffix is not None:
        base_id = blob.get("id")
        if not isinstance(base_id, str) or not base_id:
            return ImportOutcome(
                entry, None, "error", "blob has no string id to suffix"
            )
        blob["id"] = f"{base_id}__{entry.id_suffix}"

    story_id = blob.get("id")
    if not isinstance(story_id, str) or not story_id:
        return ImportOutcome(entry, None, "error", "blob has no string id")

    if _needs_legacy_normalization(blob):
        try:
            skeleton = _load_reference_skeleton(
                entry.skeleton_band, entry.skeleton_slug
            )
            blob = _normalize_legacy_fill(blob, skeleton)
        except ValidationError as exc:
            return ImportOutcome(
                entry, story_id, "error", f"normalization failed: {exc}"
            )

    return story_id, blob


async def _persist_and_classify(
    session: AsyncSession,
    entry: CatalogEntry,
    blob: dict[str, object],
    config: ImportConfig,
) -> ImportOutcome:
    """Run ``import_filled_story`` and classify its outcome.

    Commits the session on success. On a gate block, rolls back via the
    caller's ``async with`` (no ORM writes were flushed, so nothing to
    undo). On any other error, this is the per-entry boundary for the
    ``import_filled_story`` call itself (``_import_one`` wraps its own
    session-acquire and pre-insert existence check in a sibling boundary of
    the same shape): it catches every ``ProjectBaseError`` (a
    moderation-pipeline failure, etc.) and every ``SQLAlchemyError`` (notably
    ``IntegrityError``, e.g. a PK-violation from a concurrent duplicate run
    racing this entry's insert; see ``_import_one``'s own ``#ASSUME`` note),
    rolls the session back explicitly, and classifies the entry as "error"
    rather than letting the exception propagate and abort the whole batch.

    Args:
        session: Open async session for this entry's isolated transaction.
        entry: The manifest entry being imported.
        blob: The (possibly id-suffixed, possibly legacy-normalized) blob,
            whose ``id`` is the story id to import under.
        config: The run's model/prompt_version settings.

    Returns:
        The classified outcome: "gate_blocked", "error", or "imported".
    """
    # story_id is guaranteed a non-empty str by _prepare_blob before this
    # function is ever called (see _import_one); cast rather than re-check.
    story_id = cast("str", blob["id"])
    request = ImportRequest(
        family_id=CATALOG_FAMILY_ID,
        blob=blob,
        model=config.model,
        prompt_version=config.prompt_version,
        skeleton_slug=entry.skeleton_slug,
    )
    try:
        imported_id = await import_filled_story(session, request)
    except ValidationError as exc:
        return ImportOutcome(entry, story_id, "gate_blocked", str(exc))
    # #CRITICAL: data-integrity: this is the batch's per-entry error
    # boundary. ProjectBaseError covers every domain failure the moderation
    # pipeline and importer raise; SQLAlchemyError (IntegrityError is a
    # subclass) covers a PK-violation or other DB-layer failure that is not
    # a ProjectBaseError, most notably the concurrent-run race documented on
    # _import_one. Catching both here (rather than only ProjectBaseError, or
    # a blind ``except Exception``) keeps one bad entry from aborting
    # _print_summary for the other 24.
    # #VERIFY: test_import_catalog_survives_an_integrity_error_and_continues in
    # tests/integration/test_import_catalog.py forces an IntegrityError on one
    # entry and asserts the batch completes rather than crashing.
    except (ProjectBaseError, SQLAlchemyError) as exc:
        await session.rollback()
        return ImportOutcome(entry, story_id, "error", str(exc))

    book = await session.get(Storybook, imported_id)
    status = book.status if book is not None else "unknown"
    await session.commit()
    return ImportOutcome(entry, imported_id, "imported", f"status={status}")


async def _import_one(
    session_factory: Callable[[], AsyncSession],
    entry: CatalogEntry,
    config: ImportConfig,
) -> ImportOutcome:
    """Import one catalog entry, isolated in its own session/transaction.

    Args:
        session_factory: Zero-arg callable returning a fresh ``AsyncSession``
            (``core.database.get_session`` in production, the integration
            test ``sessions`` fixture in tests).
        entry: The manifest entry to import.
        config: The run's repo_root/model/prompt_version settings.

    Returns:
        The classified outcome for this entry.
    """
    # #CRITICAL: data-integrity: this function opens and commits its own
    # session per entry (not shared across CATALOG_ENTRIES), so one bad
    # story's exception cannot roll back any other story's already-committed
    # import. This is the batch's isolation boundary.
    # #VERIFY: test_import_catalog_isolates_a_bad_entry_from_the_rest.
    repo_root = config.repo_root if config.repo_root is not None else Path.cwd()
    prepared = _prepare_blob(repo_root, entry)
    if isinstance(prepared, ImportOutcome):
        return prepared
    story_id, blob = prepared

    # #CRITICAL: external-resources: the session acquire (session_factory())
    # and the pre-insert existence check (session.get) below are now INSIDE
    # this try boundary, alongside _persist_and_classify's own broadened
    # catch. Before this fix, a transient OperationalError from either one
    # (a dropped connection, a pool exhaustion blip) escaped _import_one
    # uncaught, propagated out of import_catalog()'s per-entry loop, and
    # aborted the entire 25-story batch, contradicting this module's own
    # disclosed judgment (see _persist_and_classify's docstring/#CRITICAL
    # note) that a transient failure should cost one entry, not the batch.
    # #VERIFY: see tests/unit/test_import_catalog.py, class
    # TestImportOneTransientErrorHandling: it forces an OperationalError at
    # each of these two points and asserts only that one entry is classified
    # "error" while a following entry still imports.
    try:
        async with session_factory() as session:
            # #ASSUME: concurrency: this existence check and the subsequent
            # import happen in the same session but are not itself a hard
            # lock; a concurrent second run of this batch script against the
            # same database could theoretically both pass this check and
            # then race on the Storybook PK insert. That race surfaces as an
            # "error" outcome via the PK-violation IntegrityError caught by
            # this same try boundary, not a crashed batch or a silent
            # double-import. The importer is intended to be run by one
            # operator at a time, so this window is accepted rather than
            # adding explicit row locking.
            # #VERIFY: see test_import_catalog_imports_a_small_entry_and_is_idempotent
            # for two sequential full runs staying idempotent, and
            # test_import_catalog_survives_an_integrity_error_and_continues for a
            # forced PK-violation IntegrityError not aborting the batch.
            existing = await session.get(Storybook, story_id)
            if existing is not None:
                return ImportOutcome(entry, story_id, "skipped_existing")
            return await _persist_and_classify(session, entry, blob, config)
    except (ProjectBaseError, SQLAlchemyError) as exc:
        return ImportOutcome(entry, story_id, "error", str(exc))


async def import_catalog(
    session_factory: Callable[[], AsyncSession],
    config: ImportConfig | None = None,
    *,
    entries: tuple[CatalogEntry, ...] = CATALOG_ENTRIES,
) -> list[ImportOutcome]:
    """Import every catalog entry, one isolated transaction each.

    Args:
        session_factory: Zero-arg callable returning a fresh ``AsyncSession``.
        config: Run parameters (repo_root/model/prompt_version); defaults to
            ``ImportConfig()`` when not given.
        entries: The entries to import (defaults to the full 25-story
            manifest; overridable for tests).

    Returns:
        One :class:`ImportOutcome` per entry, in ``entries`` order.
    """
    effective_config = config if config is not None else ImportConfig()
    outcomes: list[ImportOutcome] = []
    for entry in entries:
        outcome = await _import_one(session_factory, entry, effective_config)
        outcomes.append(outcome)
    return outcomes


def _print_summary(outcomes: list[ImportOutcome]) -> int:
    """Write the grouped outcome summary to stdout.

    Args:
        outcomes: The full outcome list from :func:`import_catalog`.

    Returns:
        Exit code: 0 if every entry imported or was already present, 1 if
        any entry was gate-blocked or errored.
    """
    buckets: dict[Outcome, list[ImportOutcome]] = {o: [] for o in _OUTCOME_ORDER}
    for outcome in outcomes:
        buckets[outcome.outcome].append(outcome)

    for name in _OUTCOME_ORDER:
        items = buckets[name]
        sys.stdout.write(f"{name}: {len(items)}\n")
        for item in items:
            story_id = item.story_id or "?"
            detail = f" ({item.detail})" if item.detail else ""
            sys.stdout.write(f"  - {item.entry.title} [{story_id}]{detail}\n")

    total = len(outcomes)
    sys.stdout.write(
        f"total: {total} imported={len(buckets['imported'])} "
        f"skipped_existing={len(buckets['skipped_existing'])} "
        f"gate_blocked={len(buckets['gate_blocked'])} error={len(buckets['error'])}\n"
    )
    return 1 if buckets["gate_blocked"] or buckets["error"] else 0


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the batch-import CLI argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Batch-import the draft story catalog into the review pipeline."
    )
    parser.add_argument(
        "--model", default=_DEFAULT_MODEL, help="Model id to record on each import."
    )
    parser.add_argument(
        "--prompt-version",
        default=_PROMPT_VERSION,
        help="Prompt/skill version to record on each import.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse args, run the batch import, and print the outcome summary.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 if every entry imported cleanly or was already present,
        1 if any entry was gate-blocked or errored.
    """
    args = build_arg_parser().parse_args(argv)
    model: str = args.model
    prompt_version: str = args.prompt_version
    config = ImportConfig(model=model, prompt_version=prompt_version)
    outcomes = asyncio.run(import_catalog(get_session, config))
    return _print_summary(outcomes)


if __name__ == "__main__":
    raise SystemExit(main())
