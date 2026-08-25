"""Library and story-fetch endpoints.

A child sees only published stories in their own family, plus any
visibility='catalog' story assigned to their profile (WS-E Task 13). Per-profile
age-band and reading-level cap filtering is a Phase 4a concern; Phase 1 lists
every published story in the family (or the catalog) and enforces
profile/family/assignment access. Listing additionally requires admin approval:
only versions whose ``approved_by IS NOT NULL`` (the recorded human approver)
are returned. Story fetch returns the immutable Storybook JSON blob for a
specific version: a global admin may read any version cross-family (to review
drafts), a visibility='catalog' book is readable cross-family too, while a
guardian or child otherwise receives 404 (not 403, so a draft's existence is not
revealed) for any unpublished, unapproved, or non-current version.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from typing import TYPE_CHECKING, TypeGuard

from fastapi import APIRouter
from sqlalchemy import and_, exists, or_, select, tuple_

from cyo_adventure.api.deps import (
    CurrentPrincipal,
    DbSession,
    Role,
    authorize_family,
    authorize_profile,
)
from cyo_adventure.api.schemas import (
    LibraryItem,
    LibraryProgress,
    LibraryView,
    error_responses,
)
from cyo_adventure.api.sentinel_log import strip_and_log
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.covers.storage import generate_presigned_cover_urls
from cyo_adventure.db.models import (
    ChildProfile,
    Rating,
    ReadingState,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from cyo_adventure.publishing.state_machine import Visibility
from cyo_adventure.storybook.models import parse_age_band_rank
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

_logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1", tags=["library"], responses=error_responses(401, 403)
)

_PUBLISHED = "published"


def _is_real_number(value: object) -> TypeGuard[int | float]:
    """Return whether value is a real int/float (a bool is rejected).

    Args:
        value: The candidate metadata value.

    Returns:
        TypeGuard[int | float]: ``True`` for an ``int`` or ``float`` that is not
        a ``bool``, narrowing the value for the caller.
    """
    # bool is a subclass of int in Python; a True/False slipped into a numeric
    # metadata field must not read as 1/0.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_profile_id(raw: str) -> uuid.UUID:
    """Parse a profile id, raising a 422-mapped error on bad input.

    Args:
        raw: The raw profile id string.

    Returns:
        uuid.UUID: The parsed id.

    Raises:
        ValidationError: If the value is not a valid UUID.
    """
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        msg = "profile_id must be a UUID"
        raise ValidationError(msg, field="profile_id", value=raw) from exc


def _str_field(raw: object, default: str, field: str, malformed: list[str]) -> str:
    """Return a string field, recording a fallback when the value is malformed.

    Args:
        raw: The raw value from the blob.
        default: The fallback when ``raw`` is not a string.
        field: The field name, appended to ``malformed`` on a non-null fallback.
        malformed: The accumulator of malformed field names (mutated).

    Returns:
        str: ``raw`` if it is a string, else ``default``.
    """
    if isinstance(raw, str):
        return raw
    if raw is not None:
        malformed.append(field)
    return default


def _tier_field(raw: object, malformed: list[str]) -> int:
    """Return the tier int, rejecting bool and recording a fallback otherwise.

    Args:
        raw: The raw ``tier`` value.
        malformed: The accumulator of malformed field names (mutated).

    Returns:
        int: ``raw`` if it is a non-bool int, else 0.
    """
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if raw is not None:
        malformed.append("tier")
    return 0


def _reading_level_target(meta: Mapping[str, object], malformed: list[str]) -> float:
    """Return a finite reading-level target, recording any malformed input.

    A non-dict ``reading_level``, a non-numeric or bool ``target``, or a
    non-finite float (NaN/Inf) all fall back to 0.0 and record the field. The
    finite guard matters because Starlette serializes with ``allow_nan=False``,
    so a single NaN/Inf would 500 the whole listing.

    Args:
        meta: The metadata mapping.
        malformed: The accumulator of malformed field names (mutated).

    Returns:
        float: A finite target, or 0.0 on any malformed input.
    """
    reading_level = meta.get("reading_level")
    if not isinstance(reading_level, dict):
        if reading_level is not None:
            malformed.append("reading_level")
        return 0.0
    raw_target = reading_level.get("target")
    if _is_real_number(raw_target):
        candidate = float(raw_target)
        if math.isfinite(candidate):
            return candidate
    if raw_target is not None:
        malformed.append("reading_level.target")
    return 0.0


def _node_count(blob: Mapping[str, object], malformed: list[str]) -> int:
    """Return the number of story nodes, recording a malformed ``nodes`` field.

    Args:
        blob: The stored Storybook content blob.
        malformed: The accumulator of malformed field names (mutated).

    Returns:
        int: The node count, or 0 if ``nodes`` is missing or not a list.
    """
    nodes = blob.get("nodes")
    if isinstance(nodes, list):
        return len(nodes)
    if nodes is not None:
        malformed.append("nodes")
    return 0


def _current_node_is_ending(blob: Mapping[str, object], current_node: str) -> bool:
    """Return True when ``current_node`` is an ending node in the blob (UX-K5).

    Read-only over the already-loaded blob: no extra query. A branching story
    touches only a fraction of its nodes, so "reached an ending" is the honest
    signal for "finished", not visit-count / total-node-count.
    """
    nodes = blob.get("nodes")
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if isinstance(node, dict) and node.get("id") == current_node:
            return bool(node.get("is_ending", False))
    return False


def _blob_age_band(blob: Mapping[str, object]) -> str:
    """Return a story's age band from blob metadata, or "" if absent/malformed.

    Mirrors ``assignments.py::_book_age_band``; kept local rather than shared
    because that module's helper is typed for ``dict[str, object]`` while this
    one runs over the read-only ``Mapping`` blobs library.py already handles.

    Args:
        blob: The stored Storybook content blob.

    Returns:
        str: ``metadata.age_band`` when present and a string, else ``""``.
    """
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        age_band = metadata.get("age_band")
        if isinstance(age_band, str):
            return age_band
    return ""


def _accepts_character(blob: Mapping[str, object]) -> bool:
    """Return whether a stored Storybook blob declares a character envelope.

    Mirrors the schema's own "absent means no character" default
    (``storybook/models.py::Storybook.accepts_character``): the field is
    declared only when present and not ``None``; an empty dict ``{}`` still
    counts as declared (ADR-028), so this checks presence, not truthiness.

    Args:
        blob: The stored Storybook content blob.

    Returns:
        bool: True when ``accepts_character`` is present and not None.
    """
    return blob.get("accepts_character") is not None


def storybook_content_hash(blob: Mapping[str, object]) -> str:
    """Return a stable content identity for a served Storybook blob.

    ``StorybookVersion`` is documented as immutable (``db/models.py``) and the
    offline cache in ``frontend/src/offline/db.ts`` was built on that promise:
    it keys downloaded blobs by ``id@version`` alone and never re-fetches on a
    hit. A blob rewritten in place under an unchanged ``version`` (as
    ``scripts/retrofit_personalization.py`` did to 15 published rows) is
    therefore invisible to every device that already downloaded it. This hash
    is the missing signal: it changes whenever the served bytes change, so the
    client can tell "same version, different content" from "same version, same
    content".

    The digest is taken over the exact response body
    ``get_storybook_version`` emits for this blob, not over the ORM object,
    a re-ordered dict, or the sanitized ``LibraryItem`` built from it. The
    client caches the *blob* (``frontend/src/offline/db.ts`` stores the
    ``Storybook`` payload from the read route under ``id@version``), and the
    retrofit this exists to detect rewrote node bodies, ending titles, and
    choice labels: none of which appear on a ``LibraryItem`` at all. A digest
    over the listing item would therefore be blind to the very defect it is
    meant to catch. Starlette's ``JSONResponse`` renders with
    ``ensure_ascii=False``, no indent, and ``(",", ":")`` separators, and
    preserves the dict's own key order, so those settings are mirrored here
    verbatim. Any drift between the two serializations would make every book
    read as permanently changed and turn the client's eviction check into a
    whole-shelf re-download on every load.

    Args:
        blob: The stored Storybook content blob, as served.

    Returns:
        str: ``sha256:`` followed by the lowercase hex digest.
    """
    # #ASSUME: data-integrity: key order is NOT normalized here, because the
    # digest must match the read route's bytes and Starlette emits the dict's
    # own order. That is safe only because ``storybook_version.blob`` is a
    # ``jsonb`` column: Postgres canonicalizes object key order on write and
    # returns the same order on every read, so two reads of an unmoved row
    # serialize identically. Sorting here would restore order-independence at
    # the cost of the byte equality the client actually depends on. If the
    # column ever becomes plain ``json`` (which preserves the input text
    # verbatim) or the blob starts being assembled in Python, this assumption
    # dies and the digest must be pinned some other way.
    # #VERIFY: tests/integration/test_library_content_hash.py::
    # test_library_content_hash_is_stable_across_repeat_listings.
    #
    # #CRITICAL: data-integrity: ``allow_nan`` is left at its default (True)
    # and MUST NOT be set to False here. Starlette renders with
    # ``allow_nan=False``, but mirroring that would make this raise
    # ``ValueError`` on a blob carrying NaN/Infinity, and this helper runs
    # once per book inside the library listing: one bad float would 500 the
    # whole shelf, for every book on it. ``_library_item`` is explicitly
    # built to tolerate exactly that input (it defaults the field and logs
    # ``library_item_malformed_metadata``), so the digest must tolerate it
    # too. The default never raises on a non-finite float, and for every blob
    # Starlette CAN serialize the two settings emit identical bytes, so byte
    # equality with the read route is preserved where it matters. A blob that
    # does carry a non-finite float still gets a stable, non-empty digest; the
    # read route would 500 on it, so no client can ever cache it, and there is
    # nothing for the digest to be wrong about.
    # #VERIFY: tests/unit/test_library_content_hash_unit.py::
    # test_storybook_content_hash_with_nonfinite_float_returns_stable_digest.
    rendered = json.dumps(
        blob,
        ensure_ascii=False,
        indent=None,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(rendered).hexdigest()}"


def _library_item(
    storybook_id: str,
    blob: Mapping[str, object],
    version: int,
    *,
    rating: int | None = None,
    state: ReadingState | None = None,
    series_id: str | None = None,
    book_index: int | None = None,
    cover_url: str | None = None,
    published_at: datetime | None = None,
    personalization_eligible: bool = False,
) -> LibraryItem:
    """Build a library item from a stored Storybook blob.

    Every field is read defensively: a malformed value falls back to a safe
    default rather than propagating into the response. A non-finite reading
    level (NaN/Inf) is rejected too, because Starlette serializes with
    ``allow_nan=False`` and a single bad float would 500 the whole listing.

    Args:
        storybook_id: The story id (also the title fallback).
        blob: The stored Storybook content blob.
        version: The published version number.
        rating: The profile's 1-5 rating of this story, if any.
        state: The profile's saved reading state for this story, if any.
        series_id: The book's series, or None for a standalone story (WS-B
            PR 3). Sourced from the ``Storybook`` row, not the blob.
        book_index: The book's 1-based position in its series, or None.
        cover_url: A freshly presigned cover image URL, or None if no cover
            is ready yet. Generated from ``StorybookVersion.cover_status``
            (never read from the stored ``cover_image_url`` audit column).
        published_at: When this version was published (K9 "what's new" leg),
            sourced from ``StorybookVersion.published_at``, or None for a
            pre-migration row that predates the column.
        personalization_eligible: ADR-023 Task D8, sourced verbatim from
            ``StorybookVersion.personalization_eligible`` (Stage B). Defaults
            to False, matching the column's own default for a version that
            predates it or carries no personalizable slots.

    Note:
        ``accepts_character`` is derived from ``blob`` itself (via
        ``_accepts_character``), unlike the parameters above which come from
        DB columns: ADR-028 declares the envelope in the Storybook document,
        not a separate version-row column.

    Returns:
        LibraryItem: The listing item with safe, finite, correctly typed
            fields, with personalization sentinels stripped from the title
            to their generic word (ADR-023 P3), plus ``content_hash``, the
            offline cache's content identity for this exact (id, version)
            payload (see ``storybook_content_hash``). The raw, sentinel-bearing
            blob is served verbatim by ``get_storybook_version`` (which the
            client resolves personalization against) and by the admin
            review surface (``build_review_surface`` in
            ``api/review_surface.py``, reached via
            ``api/approval.py::get_review_surface``); see
            ``tests/unit/test_title_strip_registry.py`` for the authoritative
            strip-or-raw enumeration across every title-bearing surface.
    """
    # #ASSUME: data integrity: an APPROVED published blob is well-formed, but a
    # malformed metadata field (wrong type, bool-as-number, NaN/Inf) must degrade
    # to a default AND surface a warning rather than 500 the listing silently.
    # #VERIFY: every fallback appends to ``malformed`` and emits one structured
    # warning; non-finite floats are caught by math.isfinite in the helper.
    metadata = blob.get("metadata")
    meta: Mapping[str, object] = metadata if isinstance(metadata, dict) else {}
    malformed: list[str] = []

    # #CRITICAL: security: this is the library listing, not the read surface
    # (get_storybook_version) the client resolves personalization against,
    # so a raw personalization sentinel (e.g. {~HERO:Explorer~}) must never
    # reach it (ADR-023 P3); see tests/unit/test_title_strip_registry.py for
    # the authoritative strip-or-raw enumeration across every title-bearing
    # response surface.
    # #VERIFY: tests/unit/test_library_api_unit.py::TestLibraryItem::
    # test_title_sentinels_are_stripped.
    title = strip_and_log(
        _str_field(blob.get("title"), storybook_id, "title", malformed),
        at="library_item.title",
        storybook_id=storybook_id,
        version=version,
    )
    age_band = _str_field(meta.get("age_band"), "", "age_band", malformed)
    tier = _tier_field(meta.get("tier"), malformed)
    target = _reading_level_target(meta, malformed)
    node_count = _node_count(blob, malformed)

    if malformed:
        _logger.warning(
            "library_item_malformed_metadata",
            storybook_id=storybook_id,
            version=version,
            fields=malformed,
        )

    progress: LibraryProgress | None = None
    if state is not None:
        # #EDGE: data integrity: the saved state may be pinned to an older
        # version than the currently published one, so nodes_visited can exceed
        # node_count after a republish; the frontend clamps percent at 100.
        # #VERIFY: frontend bookCardUtils.percentComplete clamps at 100.
        visit_set = state.visit_set if isinstance(state.visit_set, list) else []
        progress = LibraryProgress(
            current_node=state.current_node,
            nodes_visited=len(visit_set),
            updated_at=state.updated_at,
            completed=_current_node_is_ending(blob, state.current_node),
        )

    return LibraryItem(
        id=storybook_id,
        title=title,
        version=version,
        age_band=age_band,
        tier=tier,
        reading_level_target=target,
        node_count=node_count,
        rating=rating,
        progress=progress,
        series_id=series_id,
        book_index=book_index,
        cover_url=cover_url,
        published_at=published_at,
        personalization_eligible=personalization_eligible,
        accepts_character=_accepts_character(blob),
        content_hash=storybook_content_hash(blob),
    )


@router.get("/library")
async def list_library(
    profile_id: str,
    principal: CurrentPrincipal,
    session: DbSession,
) -> LibraryView:
    """List published stories visible to the given profile.

    Args:
        profile_id: The child profile requesting its library.
        principal: The authenticated principal.
        session: The request session.

    Returns:
        LibraryView: The published stories in the profile's family.
    """
    # #CRITICAL: security: the library includes the principal's own family AND
    # any visibility='catalog' book (WS-E Task 13: a cross-family catalog book
    # must be listable once assigned), the requested profile is authorized,
    # only APPROVED published versions are listed, AND the story must be
    # assigned to this profile (the read-path leg of the no-unpermitted-story
    # invariant); the assignment EXISTS clause is the gate for catalog books
    # too, unchanged by this widening.
    # #VERIFY: the join requires approved_by IS NOT NULL; the EXISTS requires a
    # storybook_assignment row for (this story, this profile).
    parsed = _parse_profile_id(profile_id)
    authorize_profile(principal, parsed)
    # #CRITICAL: security: H1 defense in depth. assign_storybook is the
    # PRIMARY gate for the age-band ceiling; this repeats the check at read
    # time so a book banded above the profile is hidden here too even if a
    # mismatched StorybookAssignment row exists (a bypassed assign call, a
    # profile's band lowered after assignment, a hand-inserted row in a
    # future migration/import path). Lenient (fail open) when the profile's
    # own age_band string is not a recognized AgeBand: this is a filter on
    # top of the existing family/assignment gates, not a new hard dependency
    # on band data being present.
    # #VERIFY: tests/integration/test_library_invariant.py::
    # test_list_library_hides_book_banded_above_profile.
    profile = await session.get(ChildProfile, parsed)
    profile_rank = (
        parse_age_band_rank(profile.age_band) if profile is not None else None
    )
    rows = await session.scalars(
        select(Storybook)
        .join(
            StorybookVersion,
            and_(
                StorybookVersion.storybook_id == Storybook.id,
                StorybookVersion.version == Storybook.current_published_version,
            ),
        )
        .where(
            or_(
                Storybook.family_id == principal.family_id,
                Storybook.visibility == Visibility.CATALOG.value,
            ),
            Storybook.status == _PUBLISHED,
            Storybook.current_published_version.is_not(None),
            StorybookVersion.approved_by.is_not(None),
            exists().where(
                StorybookAssignment.storybook_id == Storybook.id,
                StorybookAssignment.child_profile_id == parsed,
            ),
        )
    )
    books = [
        (book.id, book.current_published_version, book.series_id, book.book_index)
        for book in rows.all()
        if book.current_published_version is not None
    ]
    if not books:
        return LibraryView(stories=[])
    # #ASSUME: external resources: load every published version in one query to
    # avoid an N+1 round-trip per story as a family's library grows.
    # #VERIFY: a composite (storybook_id, version) IN filter selects only the
    # published rows.
    version_rows = await session.scalars(
        select(StorybookVersion).where(
            tuple_(StorybookVersion.storybook_id, StorybookVersion.version).in_(
                [(b[0], b[1]) for b in books]
            )
        )
    )
    blobs: dict[tuple[str, int], dict[str, object]] = {}
    published_ats: dict[tuple[str, int], datetime | None] = {}
    # ADR-023 Task D8: read verbatim off the version row, same keying as
    # published_ats above; never recomputed here (Stage B already decided
    # eligibility at fill/import time).
    personalization_eligibles: dict[tuple[str, int], bool] = {}
    ready_covers: list[tuple[str, int, str | None]] = []
    for row in version_rows:
        blobs[(row.storybook_id, row.version)] = row.blob
        published_ats[(row.storybook_id, row.version)] = row.published_at
        personalization_eligibles[(row.storybook_id, row.version)] = (
            row.personalization_eligible
        )
        if row.cover_status == "ready":
            ready_covers.append((row.storybook_id, row.version, row.cover_object_salt))
    # #CRITICAL: security: H1 defense in depth (continued from the comment
    # above authorize_profile): drop any blob banded above the profile's
    # band. The item-construction loop below already skips any
    # (storybook_id, version) missing from ``blobs``, so removing it here is
    # the whole filter; downstream state/rating/cover lookups may still
    # touch a filtered book's id, which wastes a lookup but leaks nothing
    # (its result is never read).
    # #VERIFY: tests/integration/test_library_invariant.py::
    # test_list_library_hides_book_banded_above_profile.
    if profile_rank is not None:
        for key in [
            key
            for key, blob in blobs.items()
            if (band_rank := parse_age_band_rank(_blob_age_band(blob))) is not None
            and band_rank > profile_rank
        ]:
            del blobs[key]
    # #CRITICAL: security: covers are private-by-default in R2 (Phase 1d); the
    # only way a client legitimately learns a cover's URL is a freshly
    # generated, short-lived signed GET URL, never the stored (permanent,
    # audit-only) cover_image_url column. One batched call signs every
    # ready cover in this listing instead of reading URLs off the rows above.
    # #VERIFY: test_library_api.py::test_library_returns_presigned_cover_urls.
    covers = await generate_presigned_cover_urls(ready_covers, settings)
    book_ids = [b[0] for b in books]
    # #ASSUME: external resources: per-profile state and ratings load in one
    # bulk query each (not per-book) so the listing stays two+2 queries total.
    # #VERIFY: both filters use IN on the published book ids and the single
    # authorized profile id.
    state_rows = await session.scalars(
        select(ReadingState).where(
            ReadingState.child_profile_id == parsed,
            ReadingState.storybook_id.in_(book_ids),
        )
    )
    states = {row.storybook_id: row for row in state_rows}
    rating_rows = await session.scalars(
        select(Rating).where(
            Rating.child_profile_id == parsed,
            Rating.storybook_id.in_(book_ids),
        )
    )
    ratings = {row.storybook_id: row.value for row in rating_rows}
    # #EDGE: external resources: every item hashes its whole blob (see
    # ``storybook_content_hash``), so this listing now does one sha256 per
    # published, assigned book on every shelf fetch. The blobs are already
    # fully loaded above for title/metadata extraction, so this adds CPU over
    # bytes already in memory rather than any new I/O, and at the current
    # catalog scale (tens of books per shelf, low hundreds of KB each) it is
    # well inside the listing's existing cost. Persisting the digest on
    # ``storybook_version`` instead would remove it entirely at the price of a
    # Supabase migration plus a backfill of every existing row; that is the
    # deliberate deferral, not an oversight, and it becomes the right trade
    # once a shelf routinely carries hundreds of books.
    # #VERIFY: tests/integration/test_library_content_hash.py::
    # test_library_content_hash_matches_served_version_bytes pins the digest to
    # the served bytes, so a future move to a stored column has an equality
    # test to satisfy rather than a guess.
    items = [
        _library_item(
            storybook_id,
            blobs[(storybook_id, version)],
            version,
            rating=ratings.get(storybook_id),
            state=states.get(storybook_id),
            series_id=str(series_id) if series_id is not None else None,
            book_index=book_index,
            cover_url=covers.get((storybook_id, version)),
            published_at=published_ats.get((storybook_id, version)),
            personalization_eligible=personalization_eligibles.get(
                (storybook_id, version), False
            ),
        )
        for storybook_id, version, series_id, book_index in books
        if (storybook_id, version) in blobs
    ]
    return LibraryView(stories=items)


@router.get(
    "/storybooks/{storybook_id}/versions/{version}",
    responses=error_responses(404),
)
async def get_storybook_version(
    storybook_id: str,
    version: int,
    principal: CurrentPrincipal,
    session: DbSession,
) -> dict[str, object]:
    """Return the immutable Storybook JSON for a specific version.

    Args:
        storybook_id: The story id.
        version: The story version.
        principal: The authenticated principal.
        session: The request session.

    Returns:
        dict[str, object]: The Storybook content blob.

    Raises:
        ResourceNotFoundError: If the story or version does not exist.
    """
    book = await session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: security: a global admin may read any version of any family (to
    # review drafts). A visibility='catalog' book is readable cross-family too
    # (WS-E Task 13: guardian preview parity with the content-summary endpoint;
    # a child still needs the StorybookAssignment row checked below). Otherwise
    # a guardian or child is scoped to their own family and may read ONLY the
    # approved, published, current version; 404 (not 403) so a draft's
    # existence is not revealed.
    # #VERIFY: non-admin, non-catalog, cross-family -> 403; non-admin +
    # (unpublished | non-current | unapproved) -> 404; admin -> any blob.
    if not principal.is_admin and book.visibility != Visibility.CATALOG.value:
        authorize_family(principal, book.family_id)
    version_row = await session.get(StorybookVersion, (storybook_id, version))
    if version_row is None:
        msg = f"version {version} of storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if not principal.is_admin and (
        book.status != _PUBLISHED
        or book.current_published_version != version
        or version_row.approved_by is None
    ):
        msg = f"version {version} of storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: security: M2 - a non-admin may fetch a story blob directly
    # ONLY if it is assigned to one of their own profiles; an unassigned (but
    # published+approved) book is 404 (existence hidden), matching the
    # library-listing gate. This WAS scoped to Role.CHILD/Role.DEVICE only,
    # which let a guardian principal skip the gate entirely and fetch any
    # published/approved blob, assigned or not; broadened to every non-admin
    # caller so a guardian is held to the same assignment gate as their own
    # children (principal.profile_ids for a guardian is every non-deactivated
    # child in their family, so this reduces to "assigned to some child in
    # this family"). A DEVICE principal is routed through the SAME gate: it
    # carries no profile_ids (enforced in Principal.__post_init__), so the
    # assignment lookup matches nothing and every direct blob read is 404.
    # Content reaches a device only after it mints a child session, which then
    # reads under its own assignment scope; the device grant itself never
    # reads story content. Only a CROSS-family admin action skips this branch:
    # the exemption keys on ``acting_role(book.family_id) == Role.ADMIN``, not
    # on the raw ``is_admin`` capability, because an admin-ONLY adult already
    # holds an empty ``profile_ids`` set (see ``_resolve_profiles`` in deps.py)
    # and so an ``is_admin`` test would fire for exactly one population, the
    # dual-role adult (role=GUARDIAN + is_admin=True) acting on their OWN
    # family, silently exempting the very people this gate protects.
    # #VERIFY: tests/integration/test_library_invariant.py::
    # test_child_cannot_fetch_unassigned_version,
    # test_child_can_fetch_approved_seed_version,
    # test_guardian_cannot_fetch_unassigned_version (renamed from
    # test_guardian_can_fetch_unassigned_version by this fix),
    # test_guardian_can_fetch_assigned_version, and
    # test_dual_role_adult_cannot_fetch_unassigned_own_family_version.
    if principal.acting_role(book.family_id) != Role.ADMIN:
        assigned_ids = await session.scalars(
            select(StorybookAssignment.child_profile_id).where(
                StorybookAssignment.storybook_id == storybook_id,
                StorybookAssignment.child_profile_id.in_(principal.profile_ids),
            )
        )
        assigned_profiles = await session.scalars(
            select(ChildProfile).where(ChildProfile.id.in_(list(assigned_ids)))
        )
        assigned_bands = [p.age_band for p in assigned_profiles]
        if not assigned_bands:
            msg = f"version {version} of storybook '{storybook_id}' not found"
            raise ResourceNotFoundError(msg)
        # #CRITICAL: security: H1 defense in depth. Even with a genuine
        # assignment row, the assigned profile's band must not be exceeded by
        # the book's band; lenient (fail open) when the book's band or EVERY
        # assigned profile's band is unparseable, mirroring the same
        # leniency in assign_storybook and list_library.
        # #VERIFY: tests/integration/test_library_invariant.py::
        # test_get_storybook_version_hides_book_banded_above_assigned_profile.
        book_rank = parse_age_band_rank(_blob_age_band(version_row.blob))
        if book_rank is not None:
            profile_ranks = [
                r
                for band in assigned_bands
                if (r := parse_age_band_rank(band)) is not None
            ]
            if profile_ranks and book_rank > max(profile_ranks):
                msg = f"version {version} of storybook '{storybook_id}' not found"
                raise ResourceNotFoundError(msg)
    return version_row.blob
