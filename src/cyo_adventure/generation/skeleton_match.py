"""Cell-aware skeleton selection for a story's (band, length, style) cell.

Replaces the old band-only, style/length-blind ``select_skeleton_for_band``
(WS-C PR2). Splits into a pure core (metadata loading, cell matching, the
weighted pick) and one impure recency query
(:func:`recent_skeleton_usage`), so the selection logic itself is fully
unit-testable without a database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.diversity.normalize import containment, similarity_signature
from cyo_adventure.generation.skeleton import (
    MAX_FILL_OUTPUT_TOKENS,
    expected_output_tokens,
    is_fill_feasible,
    is_sidecar,
)
from cyo_adventure.storybook.models import StoryMetadata
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import random
    import uuid
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

# The cap this screen runs against: the model-independent DEFAULT, imported
# from generation/skeleton.py rather than restated so the default cannot drift
# between the two files.
#
# It is deliberately NOT the cap `fill_skeleton` resolves. That call clamps to
# the configured model's own ceiling (`resolve_output_cap(active_fill_model())`,
# 32,768 on `deepseek/deepseek-chat-v3.1`), so screening against it would make
# the catalog a child can be offered depend on which backend happens to be
# configured, and swapping models would silently change the library rather than
# the plumbing. Selection is therefore a claim about the skeleton, not about the
# backend; the per-model shortfall is absorbed downstream by the chunked fill
# (`generation/chunking.py`), which fills a batch at a time under whatever cap
# the backend actually offers. An earlier version of this comment claimed the
# sharing meant the two sites "can never disagree about the budget", which
# stopped being true the moment the clamp landed (`AL-425`).
_FILL_MAX_TOKENS: Final[int] = MAX_FILL_OUTPUT_TOKENS

logger = get_logger(__name__)

# #ASSUME: external-resources: the skeleton library is read cwd-relative
# ("skeletons/<band>/*.json"), matching the existing discovery convention in
# tests/unit/test_skeleton.py (Path("skeletons").glob(...)); the app and test
# suite are always invoked from the repository root.
# #VERIFY: a deployment that changes the working directory must mount or copy
# skeletons/ at that same relative path, or cell matching silently finds
# nothing (returns an empty list, surfaced by the caller as a 422, not a
# crash).
_SKELETON_ROOT = Path("skeletons")

# Bands where the narrative-style axis is meaningful (ADR-011); below these,
# style collapses to prose and is not matched.
_STYLE_AWARE_BANDS = frozenset({"13-16", "16+"})


@dataclass(frozen=True, slots=True)
class Selection:
    """A weighted-random skeleton pick plus the full in-cell candidate list.

    Invariants (finding H):
        - ``alternatives`` is always non-empty. Every Selection is produced from
          at least one candidate, so an empty alternatives list is an
          internal-invariant violation rejected at construction.
        - ``slug`` need NOT appear in ``alternatives``: an admin out-of-cell
          override legitimately picks a slug that is not in the in-cell list.

    Attributes:
        slug: The chosen skeleton slug (may be an out-of-cell override).
        alternatives: Every in-cell candidate slug, as an immutable tuple.
            The admin's view of the cell, not the pool the draw ran over: a
            slug excluded by the reuse cap is still listed here, so a reviewer
            can see the option they may override to.
        reuse_cap_relaxed: True when every in-cell candidate had already been
            used by this family, so the reuse cap could not be honored and the
            draw fell back to inverse-frequency weighting over all of them.
            False on both the ordinary path and the no-history path.
    """

    slug: str
    alternatives: tuple[str, ...]
    reuse_cap_relaxed: bool = False

    def __post_init__(self) -> None:
        """Reject an empty alternatives tuple.

        Raises:
            ValidationError: If ``alternatives`` is empty (a Selection must
                carry at least one candidate).
        """
        if not self.alternatives:
            msg = "Selection.alternatives requires at least one candidate"
            raise ValidationError(msg, field="alternatives", value=None)


def _load_metadata(path: Path) -> StoryMetadata | None:
    """Return the typed metadata for a skeleton file, or None if unreadable.

    Mirrors the old select_skeleton_for_band contract: a corrupt or
    unreadable file must not crash the scan (this runs synchronously inside
    POST /authoring-plan). Malformed or schema-invalid metadata is treated
    the same as a missing file: skipped, not raised.

    Args:
        path: Path to a skeleton JSON file.

    Returns:
        The typed StoryMetadata, or None on any read/parse/schema failure.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        data = cast("dict[str, object]", json.loads(raw))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("skeleton.unreadable", path=str(path), error=str(exc))
        return None
    meta = data.get("metadata") if isinstance(data, dict) else None
    if not isinstance(meta, dict):
        logger.warning("skeleton.missing_metadata_block", path=str(path))
        return None
    try:
        return StoryMetadata.model_validate(meta)
    except PydanticValidationError as exc:
        logger.warning("skeleton.schema_invalid", path=str(path), error=str(exc))
        return None


def _read_story(path: Path) -> dict[str, object] | None:
    """Return the decoded skeleton document, or None when it cannot be read.

    Args:
        path: Path to a skeleton JSON file.

    Returns:
        dict[str, object] | None: The decoded document, or None on failure.
    """
    # #EDGE: data-integrity: `read_text` raises UnicodeDecodeError on a file that
    # is not valid UTF-8, and that is a ValueError, not an OSError and not a
    # JSONDecodeError, so it escaped this handler and crashed the scan the same
    # way a corrupt file was supposed not to. Reachable from any mangled commit
    # or partial write under `skeletons/`, and this runs synchronously inside
    # POST /authoring-plan (`AL-438`).
    # #VERIFY: test_skeleton_match.py::
    # test_a_skeleton_that_is_not_valid_utf8_is_skipped_not_raised.
    try:
        return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _expected_tokens(path: Path) -> int:
    """Return the expected fill output size for a skeleton file.

    Args:
        path: Path to a skeleton JSON file.

    Returns:
        int: Expected completion tokens, or 0 when the file cannot be read.
    """
    story = _read_story(path)
    return 0 if story is None else expected_output_tokens(story)


def _is_feasible(path: Path) -> bool:
    """Return whether a skeleton's fill fits the model-independent DEFAULT cap.

    Deliberately not the cap `fill_skeleton` resolves. That call clamps to the
    serving model's own ceiling, so screening against it would make the catalog a
    child can be offered depend on which backend happens to be configured. See
    `_FILL_MAX_TOKENS` for the full rationale; the per-model shortfall is absorbed
    downstream by the chunked fill, not by narrowing selection.

    An unreadable file is treated as feasible so this predicate cannot become a
    second, silent reason a skeleton disappears; `_load_metadata` already logs
    and drops that case.

    Args:
        path: Path to a skeleton JSON file.

    Returns:
        bool: True when the fill is expected to fit under the cap.
    """
    story = _read_story(path)
    if story is None:
        return True
    return is_fill_feasible(story, max_tokens=_FILL_MAX_TOKENS)


def _production_candidates(band: str) -> list[tuple[str, StoryMetadata]]:
    """Return (slug, metadata) for every production-eligible skeleton in a band.

    Args:
        band: The age band directory name (e.g. "8-11").

    Returns:
        Sorted-by-filename (slug, metadata) pairs; empty if the band
        directory does not exist or has no production-eligible skeleton.
    """
    band_dir = _SKELETON_ROOT / band
    if not band_dir.is_dir():
        return []
    candidates: list[tuple[str, StoryMetadata]] = []
    for path in sorted(band_dir.glob("*.json")):
        # #ASSUME: data-integrity: a sidecar (a WS-2 theme contract
        # `<slug>.contract.json` or a WS-5 lineage record `<slug>.lineage.json`,
        # ADR-020 decision 2) lives next to its skeleton and also matches this
        # `*.json` glob; without this skip it would be treated as a skeleton with
        # a missing metadata block, logging one spurious
        # `skeleton.missing_metadata_block` warning per sidecar on every scan.
        # Sidecars are authoring-time data, never a selectable skeleton. The
        # shared `is_sidecar` predicate keeps the suffix set in one place.
        # #VERIFY: test_skeleton_match.py asserts a `*.contract.json` and a
        # `*.lineage.json` file each produce no candidate and no warning log.
        if is_sidecar(path):
            continue
        metadata = _load_metadata(path)
        if metadata is None or not metadata.production_eligible:
            continue
        # ADR-011 D11: a retired skeleton is superseded, not defective. It stays
        # in the catalog (as a mutation parent, as provenance for the books
        # already filled from it, and as history) and simply stops being drawn
        # for new stories. Books already published from it are untouched.
        # #VERIFY: test_skeleton_match.py::
        # test_a_deprecated_skeleton_is_not_a_candidate.
        if metadata.deprecated:
            continue
        # #CRITICAL: payment: a skeleton that fits NO backend must not be
        # selectable. This screens against the model-independent default, so it
        # refuses only what is unfillable in principle; a skeleton that merely
        # exceeds the serving model's ceiling is chunked instead of excluded.
        # Without the screen an over-cap skeleton does not degrade, it
        # truncates, parses as nothing, and burns the whole repair budget
        # (roughly four rounds of ~100k input tokens) before failing
        # deterministically on every retry, forever.
        # Screening here costs a file read and no provider call, which is the
        # trade: `_load_metadata` has already read this path, and the
        # infeasible branch reads it again to report the size, so an excluded
        # skeleton costs three reads rather than one. Cheap against a provider
        # call, but do not describe it as free. UW-C07 / AL-046.
        # #VERIFY: test_skeleton_match.py::
        # test_an_over_cap_skeleton_is_not_a_candidate.
        if not _is_feasible(path):
            # A skeleton no backend can emit must not be offered. `fill_skeleton`
            # does chunk now, but only against the RESOLVED (per-model) cap;
            # `_is_feasible` screens against the model-independent DEFAULT cap,
            # so reaching here means the skeleton is over-cap for every backend,
            # where chunking cannot save it: the completion truncates, parses as
            # nothing, and burns the whole repair budget before failing
            # deterministically on every retry, forever. See `is_fill_feasible`
            # on why the two callers must keep asking at different caps.
            #
            # This was observe-only from 2026-08-16 until the cap was raised the
            # same day, because at 32,000 it would have excluded 36 of 59
            # skeletons and emptied the 13-16 and 16+ bands. At 131,072 it
            # excludes nothing in the current catalog, so it is a safety net for
            # future skeletons rather than a live filter. UW-C07 / AL-046.
            # #VERIFY: test_skeleton_match.py::
            # test_an_over_cap_skeleton_is_not_a_candidate.
            logger.warning(
                "skeleton.fill_infeasible",
                path=str(path),
                expected_output_tokens=_expected_tokens(path),
                max_tokens=_FILL_MAX_TOKENS,
            )
            continue
        candidates.append((path.stem, metadata))
    return candidates


def skeleton_matches_cell(
    metadata: StoryMetadata,
    *,
    band: str,
    length: str,
    style: str,
    include_continuations: bool = False,
) -> bool:
    """Return whether a skeleton's metadata matches a (band, length, style) cell.

    Args:
        metadata: The skeleton's typed metadata. A skeleton whose ``length`` is
            None is length-less (a documented valid backward-compat state on
            StoryMetadata.length: Length | None) and matches any request length.
        band: The request's age band.
        length: The request's length ("short"/"medium"/"long"); a null
            request length must already be collapsed to a default by the
            caller (see story_requests/authoring_plan.py::_length_of).
        style: The request's narrative style; ignored for every band except
            "13-16" and "16+" (ADR-011: style collapses to prose below the
            teen bands).
        include_continuations: When False (the default, used by generation
            selection), a mid-series continuation is not a cell match, because
            it must not be drawn for an ordinary themed request (AL-045). When
            True, the continuation gate is skipped: the in-cell clone audit
            (diversity/incell.py) opts in so that a book 2 which re-skins book 1
            is still measured against the catalog. Selection and catalog-quality
            are separate concerns that happen to share this predicate; only the
            audit sets this flag.

    Returns:
        True if age_band matches, the skeleton's length matches (or the
        skeleton declares no length, which is a wildcard that matches any
        request length), and (for the two teen bands only) narrative_style
        also matches.
    """
    if metadata.age_band != band:
        return False
    if not include_continuations and is_continuation_skeleton(metadata):
        return False
    if metadata.length is not None and metadata.length != length:
        return False
    return band not in _STYLE_AWARE_BANDS or metadata.narrative_style == style


def is_continuation_skeleton(metadata: StoryMetadata) -> bool:
    """Return whether a skeleton is a mid-series book rather than an entry point.

    A continuation book opens on state it did not earn: the Wyrmreach book 2
    skeleton declares ``iron_key`` and ``knows_compact`` already true and
    ``renown`` already at 2, and its opening beats name the artifact and the
    conspiracy from book 1. Drawn for an ordinary themed request it delivers a
    protagonist who owns things from a story the reader has never seen, and the
    fill has to render those beats against an unrelated theme, so the Stage 1
    fidelity check ends up fighting the skeleton instead of checking it.

    Book 1 of a series stays selectable: it is a valid standalone entry point,
    and its continuations are reached through the series flow
    (``generation/series_link.py``), not through cell matching.

    Args:
        metadata: The skeleton's typed metadata.

    Returns:
        bool: True when the skeleton declares a series ``book_index`` above 1.
    """
    # #CRITICAL: data-integrity: without this, roughly 40% of
    # (16+, medium, gamebook) requests drew a Wyrmreach book and about 20% drew
    # book 2 specifically, pre-seeded with a previous book's outcome (AL-045).
    # #VERIFY: test_continuation_book_is_not_a_cell_candidate and
    # test_series_first_book_is_still_a_cell_candidate.
    series = metadata.series
    return series is not None and series.book_index > 1


def candidates_for_cell(
    band: str, length: str, style: str, *, include_continuations: bool = False
) -> list[str]:
    """Return slugs of every production-eligible skeleton matching a cell.

    Args:
        band: The request's age band.
        length: The request's length, already defaulted if the request's own
            length was null.
        style: The request's narrative style.
        include_continuations: Forwarded to :func:`skeleton_matches_cell`. The
            default (False) is generation-selection behavior and excludes
            mid-series books. The in-cell clone audit passes True so a
            continuation is still measured against its cell-mates.

    Returns:
        Sorted-by-filename slugs; empty if no skeleton matches (the caller
        must treat an empty list as "no skeleton available", exactly as the
        old select_skeleton_for_band's None return was treated).
    """
    return [
        slug
        for slug, metadata in _production_candidates(band)
        if skeleton_matches_cell(
            metadata,
            band=band,
            length=length,
            style=style,
            include_continuations=include_continuations,
        )
    ]


def request_theme_signature(premise: str) -> frozenset[str]:
    """Return a request premise's canonical similarity-tag signature (W2.2).

    Thin wrapper over ``diversity.normalize.similarity_signature`` so both
    sides of a theme-aware skeleton pick (the request premise here, a
    candidate's ``metadata.themes`` via :func:`_theme_overlap_bonus`) go
    through the exact same ``SIMILARITY_TAG_MAP`` machinery the diversity
    package already uses for request/story similarity elsewhere, rather than
    duplicating tag-matching logic in this module.

    Args:
        premise: The request's free-text premise (``ConceptBrief.premise``,
            or the raw request text before a brief is built).

    Returns:
        frozenset[str]: Canonical similarity tags; empty when the premise
            matches nothing in the vocabulary (a zero-overlap request, which
            leaves every candidate's bonus at 0.0 -- today's behavior).
    """
    return similarity_signature({"premise": premise})


def _theme_overlap_bonus(
    request_tags: frozenset[str], metadata: StoryMetadata
) -> float:
    """Return a candidate skeleton's theme-overlap bonus against a request.

    Args:
        request_tags: The request's similarity-tag signature (see
            :func:`request_theme_signature`).
        metadata: The candidate skeleton's typed metadata.

    Returns:
        float: ``containment(request_tags, story_tags)`` in ``[0, 1]``: how
            much of what the request asked for this skeleton's curated
            themes already cover. ``0.0`` when ``request_tags`` is empty (a
            request the vocabulary did not recognize contributes no bonus to
            anything, per :func:`diversity.normalize.containment`) or when
            the candidate's themes share no tag with the request.
    """
    story_tags = similarity_signature(None, metadata.themes)
    return containment(request_tags, story_tags)


def theme_overlap_for_candidates(
    request_premise: str, band: str, candidates: Sequence[str]
) -> dict[str, float]:
    """Return a per-slug theme-overlap bonus for an in-cell candidate list.

    A convenience entry point for a caller that only has the request premise
    and candidate slugs on hand (:func:`candidates_for_cell`'s return shape);
    it re-scans the band's production-eligible metadata once and computes
    :func:`_theme_overlap_bonus` for each requested slug, so a future
    ``select_skeleton_for_cell(..., theme_overlap=...)`` caller does not need
    to separately load and thread ``StoryMetadata`` for every candidate.

    Args:
        request_premise: The request's free-text premise.
        band: The request's age band (the candidates' own band; scans that
            band's directory only, matching how the candidates were found).
        candidates: The in-cell candidate slugs (from
            :func:`candidates_for_cell`).

    Returns:
        dict[str, float]: ``{slug: bonus}`` for every slug in ``candidates``
            whose metadata is still readable; a slug absent from the band's
            production-eligible scan (should not happen for a slug that was
            itself just produced by :func:`candidates_for_cell` against the
            same band) is simply omitted, which
            :func:`select_skeleton_for_cell` treats as a 0.0 bonus via
            ``.get(slug, 0.0)``.
    """
    request_tags = request_theme_signature(request_premise)
    metadata_by_slug = dict(_production_candidates(band))
    return {
        slug: _theme_overlap_bonus(request_tags, metadata_by_slug[slug])
        for slug in candidates
        if slug in metadata_by_slug
    }


def resolve_skeleton_path(band: str, slug: str) -> Path:
    """Return the validated ``skeletons/<band>/<slug>.json`` path.

    Resolves the candidate path and confirms it stays inside the skeleton root
    before returning it, so an admin-supplied slug cannot escape the library
    tree via path traversal.

    Args:
        band: The age band directory name (e.g. "8-11").
        slug: The skeleton's filename stem, as supplied by the admin (untrusted).

    Returns:
        The resolved, containment-checked path (it may or may not exist on
        disk; the caller checks ``is_file()``).

    Raises:
        ValidationError: If the resolved path escapes the skeleton root (a
            path-traversal attempt via ``band`` or ``slug``).
    """
    # #CRITICAL: security: ``slug`` is untrusted admin-override input
    # (decision C-6, unconstrained skeleton_slug). A slug such as
    # "../../etc/passwd" would otherwise resolve outside skeletons/ and let a
    # crafted request read or fill an arbitrary file. Reject any resolved path
    # that is not contained in the skeleton root.
    # #VERIFY: test_resolve_skeleton_path_rejects_traversing_slug and
    # test_find_skeleton_metadata_rejects_traversing_slug assert the
    # ValidationError; worker.py and import_story.py resolve through this helper.
    root = _SKELETON_ROOT.resolve()
    candidate = (_SKELETON_ROOT / band / f"{slug}.json").resolve()
    if not candidate.is_relative_to(root):
        msg = (
            f"skeleton path for band '{band}', slug '{slug}' escapes the skeleton root"
        )
        raise ValidationError(msg, field="skeleton_slug", value=slug)
    return candidate


def _locate_skeleton(slug: str) -> tuple[str, Path] | None:
    """Return the (band directory name, path) holding ``<slug>.json``.

    The single definition of "which band holds this slug", shared by
    :func:`find_skeleton_metadata` and :func:`find_skeleton_band` so the
    ambiguity and traversal rules cannot drift between them.

    Args:
        slug: The skeleton's filename stem (untrusted).

    Returns:
        The matched band directory name and its path, or None if no band
        directory has a file named "<slug>.json".

    Raises:
        ValidationError: If ``slug`` traverses outside the skeleton root (via
            :func:`resolve_skeleton_path`), or if the same "<slug>.json"
            exists in two or more bands (ambiguous).
    """
    if not _SKELETON_ROOT.is_dir():
        return None
    matches: list[tuple[str, Path]] = []
    for band_dir in sorted(_SKELETON_ROOT.iterdir()):
        if not band_dir.is_dir():
            continue
        path = resolve_skeleton_path(band_dir.name, slug)
        if path.is_file():
            matches.append((band_dir.name, path))
    if len(matches) > 1:
        bands = ", ".join(sorted(band for band, _ in matches))
        msg = f"ambiguous skeleton_slug '{slug}' present in multiple bands: {bands}"
        raise ValidationError(msg, field="skeleton_slug", value=slug)
    if not matches:
        return None
    return matches[0]


def find_skeleton_band(slug: str) -> str | None:
    """Return the band directory name holding ``<slug>.json``.

    Used by :func:`~cyo_adventure.moderation.personalizable_slots.personalizable_slot_ids_for_version`
    to recover the band a ``StorybookVersion`` does not store, so an imported
    book's theme contract can be loaded without a ``GenerationJob`` row.

    The band is the matched DIRECTORY, deliberately not the metadata's declared
    ``age_band``. The two agree for every skeleton in the catalog today; taking
    the directory means they never have to. A skeleton filed under one band
    while declaring another would otherwise resolve to a path that does not
    exist, and its caller would fail closed to a block that reads as a safety
    verdict rather than as a catalog inconsistency.

    Args:
        slug: The skeleton's filename stem, from
            ``StorybookVersion.skeleton_slug``.

    Returns:
        The band directory name (e.g. "8-11"), or None if no band directory
        has a file named "<slug>.json".

    Raises:
        ValidationError: If ``slug`` traverses outside the skeleton root, or if
            the same "<slug>.json" exists in two or more bands.
    """
    located = _locate_skeleton(slug)
    return None if located is None else located[0]


def find_skeleton_metadata(slug: str) -> StoryMetadata | None:
    """Return a skeleton's typed metadata by scanning every band directory.

    Used for the admin's unconstrained skeleton_slug override (decision C-6),
    which may name a skeleton outside the request's own band directory (an
    explicitly out-of-cell pick), or a non-production-eligible one. Every
    candidate path is routed through :func:`resolve_skeleton_path` so a
    traversing slug is rejected rather than read.

    A genuinely-absent slug (no band has "<slug>.json") returns None so the
    caller can surface the standard "does not exist" 422. A slug that exists
    but is corrupt, or exists in more than one band, raises so the caller does
    not misreport a real, distinct failure as "does not exist".

    Args:
        slug: The skeleton's filename stem, as supplied by the admin.

    Returns:
        The typed metadata, or None if no band directory has a file named
        "<slug>.json".

    Raises:
        ValidationError: If ``slug`` traverses outside the skeleton root
            (via :func:`resolve_skeleton_path`); if the same "<slug>.json"
            exists in two or more bands (ambiguous); or if exactly one exists
            but is unreadable or has invalid metadata (present-but-corrupt).
    """
    located = _locate_skeleton(slug)
    if located is None:
        return None
    metadata = _load_metadata(located[1])
    if metadata is None:
        msg = f"skeleton_slug '{slug}' exists but is unreadable or has invalid metadata"
        raise ValidationError(msg, field="skeleton_slug", value=slug)
    return metadata


def _weight(recent_count: int) -> float:
    """Return the inverse-frequency weight for a candidate's recent-use count.

    Args:
        recent_count: How many times this slug appeared in the family's
            recent storybook_version history (0 if never, or no history).

    Returns:
        1 / (1 + recent_count): 1.0 for an unused candidate, strictly
        decreasing but never zero as recent_count grows (the "implicit
        nonzero floor" from decision C-4: nothing is ever fully excluded).
    """
    return 1.0 / (1 + recent_count)


# De-weights a similar-theme reuse of a tree like 3 plain recent uses (WS-4,
# docs/planning/story-flexibility-plan.md section "WS-4: Similarity-driven,
# escalating selection"): a family's second dragon story on a skeleton it
# already used for a dragon story should feel like a much heavier repeat than
# an unrelated-theme recent use of that same skeleton. A starting heuristic,
# not calibrated data, tunable once WS-0 metrics accumulate; mirrors the
# `_HARD_BANDS`-style heuristics in story_requests/authoring_plan.py.
_THEME_REUSE_PENALTY: Final[int] = 3


def _blended_weight(recent_count: int, similar_count: int) -> float:
    """Return an inverse-frequency weight blending recency and theme reuse.

    Args:
        recent_count: How many times this slug appeared in the family's
            recent storybook_version history (see recent_skeleton_usage).
        similar_count: How many of the family's recent similar-theme
            stories used this slug (see
            diversity.query.similarity_context's
            ``similar_count_per_slug``).

    Returns:
        1 / (1 + recent_count + _THEME_REUSE_PENALTY * similar_count): 1.0
        for a wholly-unused candidate, strictly decreasing but never zero as
        either count grows (the same never-zero novelty floor as
        :func:`_weight`, decision C-4).
    """
    return 1.0 / (1 + recent_count + _THEME_REUSE_PENALTY * similar_count)


def _apply_reuse_cap(
    candidates: list[str], recent_usage: Mapping[str, int]
) -> tuple[list[str], bool]:
    """Drop candidates this family has already read, unless that empties the cell.

    #CRITICAL: data-integrity: this is a product policy with a measurement
    behind it, not a tuning weight. Two fills of one skeleton from deliberately
    distant briefs share 96.3 four-grams per 1000 leaf words against a budget
    of 4.0, and both candidate levers measured worse (directive 110.7,
    mutation 108.1), so a family served the same skeleton twice gets a
    recognizably duplicate book. Weighting cannot express this: an
    inverse-frequency floor keeps the duplicate drawable, merely rarer. The
    exclusion therefore overrides decision C-4's never-zero floor for the
    same-skeleton case specifically, and only for as long as no lever reaches
    the bar (`UW-C315`).
    #VERIFY: tests/unit/test_skeleton_match.py::
    test_a_skeleton_the_family_already_used_is_not_drawn_again.

    #ASSUME: concurrency: `recent_usage` is a snapshot read before this call,
    not a reservation. Two requests from one family that overlap between the
    read and the version row's insert both see the same slug as unused and can
    both draw it, so the cap is a strong preference rather than a guarantee.
    That is accepted: a family issuing two simultaneous requests is rare, the
    consequence is one duplicate pairing rather than data loss, and serialising
    the draw would put a lock on the request path to prevent it.
    #VERIFY: `reuse_cap_relaxed` is False in that case, so the Selection does
    NOT record the duplicate as a known compromise. A future detector belongs
    on the persisted pairing, not here. Scheduled as `UW-C345`.

    Args:
        candidates: Every in-cell candidate slug.
        recent_usage: {slug: count} over the family's recency window.

    Returns:
        ``(pool, relaxed)``: the slugs the draw may run over, and whether the
        cap had to be given up because every candidate was already used.
    """
    unused = [slug for slug in candidates if recent_usage.get(slug, 0) == 0]
    if unused:
        return unused, False
    # Every candidate is used. Refusing here would fail a family's Nth request
    # in a small cell outright, trading a diversity defect for an availability
    # outage, so the draw falls back to the pre-cap weighting and the caller is
    # told. Note the cap is bounded by the recency window (_RECENT_WINDOW), not
    # by all history: "not reused in the family's last 20 books", which is what
    # keeps a small cell from exhausting itself permanently.
    return candidates, True


def select_skeleton_for_cell(
    candidates: list[str],
    recent_usage: dict[str, int],
    rng: random.Random,
    *,
    similar_usage: Mapping[str, int] | None = None,
    theme_overlap: Mapping[str, float] | None = None,
) -> Selection:
    """Weighted-random pick from an in-cell candidate list.

    Args:
        candidates: Production-eligible skeleton slugs whose metadata matches
            the request's cell (from candidates_for_cell); must be
            non-empty. The caller is responsible for the "no matching
            skeleton" 422 before ever calling this.
        recent_usage: {slug: count} of how many times each slug was recently
            used by the family (from recent_skeleton_usage); an empty map
            (no family, or no history) yields a uniform pick.
        rng: An injected random.Random, so callers get deterministic
            behavior under a seeded instance (tests) and real randomness in
            production (see story_requests/authoring_plan.py, which passes a
            random.SystemRandom() rather than random.Random()).
        similar_usage: {slug: count} of how many of the family's recent
            similar-theme stories (WS-4, from
            diversity.query.SimilarityContext.similar_count_per_slug) used
            each slug. When None (the default), weights are exactly
            ``_weight(recent_usage[slug])``, unchanged from the pre-WS-4
            behavior. When provided, weights blend recency and theme reuse
            via :func:`_blended_weight`.
        theme_overlap: {slug: bonus} of how much a candidate's curated themes
            overlap the request premise (W2.2, from
            :func:`theme_overlap_for_candidates` or
            :func:`_theme_overlap_bonus`), each in ``[0, 1]``. When ``None``
            (the default), behavior is unchanged from pre-W2.2 (recency/
            similarity only) -- a zero-overlap request also leaves this
            unchanged, since every bonus is then 0.0. When provided, the
            recency/similarity weight (whichever of the two paths above
            applies) is multiplied by ``(1 + bonus)``: a perfect-overlap
            candidate (``bonus == 1.0``) gets up to double weight over an
            otherwise-identical, zero-overlap candidate in the same cell,
            so a matching skeleton reliably outdraws a non-matching one
            without the novelty floor (decision C-4) ever reaching zero for
            either.

    Returns:
        Selection: the weighted pick, plus every in-cell candidate as
        `alternatives` (an immutable tuple, so the admin sees every option,
        including the ones not drawn).

    Raises:
        ValidationError: If candidates is empty (an internal-invariant
            violation; callers must check candidates_for_cell(...) first).
            Built-in exceptions are disallowed in this service module per
            src/CLAUDE.md, so this raises the project ValidationError.
    """
    if not candidates:
        msg = "select_skeleton_for_cell requires at least one candidate"
        raise ValidationError(msg, field="candidates", value=None)
    # The cap runs BEFORE any weighting, so neither the theme-overlap bonus nor
    # a low similar-theme count can buy an already-read skeleton back into the
    # draw. An overlap bonus multiplies a weight; on an excluded slug there is
    # no weight left to multiply.
    pool, relaxed = _apply_reuse_cap(candidates, recent_usage)
    if similar_usage is None:
        base_weights = [_weight(recent_usage.get(slug, 0)) for slug in pool]
    else:
        base_weights = [
            _blended_weight(recent_usage.get(slug, 0), similar_usage.get(slug, 0))
            for slug in pool
        ]
    if theme_overlap is None:
        weights = base_weights
    else:
        weights = [
            weight * (1.0 + theme_overlap.get(slug, 0.0))
            for weight, slug in zip(base_weights, pool, strict=True)
        ]
    pick = rng.choices(pool, weights=weights, k=1)[0]
    return Selection(
        slug=pick, alternatives=tuple(candidates), reuse_cap_relaxed=relaxed
    )


# How many of the family's most recent storybook_version rows to weight
# selection against (decision C-4: "proposed 20", ratified as the final
# value for WS-C PR2). A module constant, not configurable, so behavior is
# stable across restarts and does not need a settings round trip.
_RECENT_WINDOW = 20


async def recent_skeleton_usage(
    session: AsyncSession, family_id: uuid.UUID | None
) -> dict[str, int]:
    """Return {slug: count} of skeleton usage over the family's recent history.

    Args:
        session: An open async session.
        family_id: The request's owning family, or None for a family-less
            (admin/catalog) request.

    Returns:
        A recency-window usage count per slug; empty when family_id is None,
        the family has no storybook_version history, or every recent version
        has a null skeleton_slug (fresh_generation/import versions).
    """
    # #ASSUME: external-resources: this issues a live database query against
    # storybook_version joined to storybook; the caller (select_skeleton_for_cell's
    # caller in authoring_plan.py) is expected to hold an open async session.
    # #VERIFY: a session that is closed or out of a transaction context raises
    # before this function runs; no defensive re-open is attempted here.
    #
    # #ASSUME: data-integrity: the recency window counts EVERY authored
    # storybook_version row (all statuses, and multiple versions of the same
    # storybook count separately) as "recently used". StorybookVersion has no
    # per-version delivered/approved status column; a version's delivered state
    # is only inferrable from the parent Storybook.status or approved_by. The
    # deliberate choice here is that skeleton diversity should reflect authoring
    # activity, not delivery: a skeleton the family just authored against is
    # "recently used" whether or not that version shipped. Narrowing this to
    # approved-only or distinct-storybook counting is a product decision, not a
    # bug, and is intentionally NOT done here.
    # #VERIFY: tests/unit/test_skeleton_recency.py pins the exact query and the
    # returned counts; any status filter or dedupe would break those and must be
    # a deliberate, tested product change.
    if family_id is None:
        return {}
    stmt = (
        select(StorybookVersion.skeleton_slug)
        .join(Storybook, Storybook.id == StorybookVersion.storybook_id)
        .where(Storybook.family_id == family_id)
        .order_by(StorybookVersion.created_at.desc())
        .limit(_RECENT_WINDOW)
    )
    result = await session.execute(stmt)
    counts: dict[str, int] = {}
    for (slug,) in result.all():
        if slug is None:
            continue
        counts[slug] = counts.get(slug, 0) + 1
    return counts
