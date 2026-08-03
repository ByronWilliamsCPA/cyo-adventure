"""Kid-scoped progress projection (W3.1): badges, gallery, lifetime totals.

``GET /me/progress`` computes badges 1-8/10/11 (gamification recommendation
section 2.2), per-book collection state (the Endings Gallery / Finished
Shelf, section 2.1), and lifetime totals entirely on read, from
``Completion``/``Rating``/``StoryRequest`` rows this module loads and the
pure ``progress/`` package composes -- zero new tables for this half of the
recommendation (section 5: "starting derived means zero migrations for the
entire badge and collection layer").

Child-only in this v1 slice, not the "guardian may also call for a specific
profile they own" variant the plan names as an option: this route has no
path parameter (mirrors ``api/me.py::whoami``'s "me" shape), so a guardian
caller would need a profile id parameter this route deliberately omits to
keep the child-ownership check trivial (structural: a CHILD principal is
always scoped to exactly one profile, ``api/deps.py::Principal``). Badges
are family-visible per the plan's adopted defaults, but no guardian-facing
badge surface exists yet (W3.2, frontend, is out of scope for this change);
when one lands it can call this same pure ``progress.badges.compute_progress``
with a guardian-supplied profile id rather than duplicate the projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import select, tuple_

from cyo_adventure.api.deps import CurrentPrincipal, DbSession, Role
from cyo_adventure.api.schemas import (
    BookProgressView,
    EarnedBadgeView,
    FoundEndingView,
    ProgressTotalsView,
    ProgressView,
    ResolvedGamificationSettingsView,
    error_responses,
)
from cyo_adventure.api.sentinel_log import strip_and_log
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import (
    RING_GOAL_DAYS_MAX,
    RING_GOAL_DAYS_MIN,
    ChildProfile,
    Completion,
    Rating,
    ReadingActivityDay,
    Storybook,
    StorybookVersion,
    StoryRequest,
)
from cyo_adventure.progress.badges import compute_progress
from cyo_adventure.progress.blob import book_title, ending_count, ending_valence_map
from cyo_adventure.progress.models import BookFacts
from cyo_adventure.storybook.models import AgeBand, Valence
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.api.deps import Principal
    from cyo_adventure.progress.models import ProgressFacts

_logger = get_logger(__name__)

# #ASSUME: security: every route on this router runs _require_child_profile,
# which raises AuthorizationError for a non-child principal; app.py maps that
# to 403. Declaring only 401 left the generated client with no 403 in its
# error union, so a guardian previewing as a child hit an UNMODELLED failure
# that surfaced as an empty-looking success rather than a denial.
# #VERIFY: tests/unit/test_progress_api_unit.py::
# test_router_declares_the_403_it_can_raise.
router = APIRouter(
    prefix="/api/v1", tags=["progress"], responses=error_responses(401, 403)
)

# W3.4 (gamification-recommendation-2026-08-01.md section 4 / design review
# P-A, ratified as D17): per-band weekly-ring defaults. Keyed on the raw
# ChildProfile.age_band string (mirrors _AGE_BAND_RANK's own choice in
# storybook/models.py) rather than the AgeBand enum, since a profile row may
# in principle carry a value this deploy's enum does not recognize yet. An
# unknown band resolves through _UNKNOWN_BAND rather than raising, so a
# settings read can never 500 a kid's whole progress screen over a band-table
# gap.
#
# #CRITICAL: security: the fallback direction matters and is easy to get
# backwards. These tables exist precisely BECAUSE "3-5" differs from every
# other band, so a per-key default of ``True`` (the shape a bare
# ``dict.get(band, True)`` takes) points the wrong way: any band string that
# fails to match turns the streak ring ON for what may be the youngest
# readers, which is the one group D17 deliberately excludes. Resolve an
# unrecognized band to the youngest band's row instead, which is the only
# genuinely conservative reading.
# #VERIFY: tests/unit/test_progress_api_unit.py::
# test_unknown_age_band_falls_back_to_the_youngest_bands_defaults.
_RING_DEFAULT_ENABLED: dict[str, bool] = {
    "3-5": False,
    "5-8": True,
    "8-11": True,
    "10-13": True,
    "13-16": True,
    "16+": True,
}
_RING_DEFAULT_GOAL_DAYS: dict[str, int] = {
    "3-5": 2,
    "5-8": 2,
    "8-11": 3,
    "10-13": 3,
    "13-16": 4,
    "16+": 4,
}

# gamification-recommendation-2026-08-01.md "Plan defaults" item 4: the
# selectable goal caps at 6 at every band, so one guaranteed free day always
# survives a guardian's most aggressive setting. This is a second backstop
# alongside the Pydantic Field bound on ProfileUpdateBody/ProfileCreateBody
# and the DB CHECK (ck_child_profile_ring_goal_days_range): a row written
# before any of those bounds existed, or restored from a backup taken between
# them, still resolves to a safe value here.
#
# Imported rather than re-typed: db/models.py owns the pair, the DB CHECK is
# built from it, and api/schemas.py's RingGoalDays alias bounds the wire
# contract with it. Three enforcement points, one definition.

# The band an unrecognized (or unavailable) age_band string resolves to. Tied
# to the enum rather than a bare "3-5" literal so a future band rename cannot
# silently turn this into an unknown key of its own. See the #CRITICAL note on
# _RING_DEFAULT_ENABLED for why the YOUNGEST band is the safe choice here.
_UNKNOWN_BAND = AgeBand.BAND_3_5.value


def _resolve_ring_settings(
    age_band: str, ring_enabled: bool | None, ring_goal_days: int | None
) -> tuple[bool, int]:
    """Resolve a profile's nullable ring columns to concrete values (W3.4).

    # #CRITICAL: data-integrity: this is the ONLY place the P-A band-default
    # table is consulted; api/profiles.py deliberately never resolves (it
    # round-trips the raw nullable columns so the guardian form can show
    # "following the band default" versus "explicitly set"). A bug here that
    # treated None as False/0 instead of the band default would silently turn
    # off every untouched profile's ring, contradicting D17's "on by default"
    # ruling for every band but 3-5.
    # #VERIFY: tests/unit/test_progress_api_unit.py::TestResolveRingSettings
    # pins every band's default plus the explicit-override and the
    # max-6-goal clamp.
    #
    # #ASSUME: data integrity: teens (13-16/16+) are speced in P-A to self-set
    # their own goal within a guardian-set ceiling ("kid, within guardian
    # cap"). This v1 slice implements the guardian-side toggle only (see the
    # kid-appeal-implementation-plan.md W3.4 task's explicit "leave the teen
    # self-set as a documented TODO" allowance): ring_goal_days IS the
    # effective goal for every band, including teens, until a kid-side
    # goal-setting control exists. A future teen self-set control must clamp
    # its own value to this same resolved number, never exceed it.
    # #VERIFY: none yet; this is an intentional v1 deferral, not a bug.

    Args:
        age_band: The profile's stored age band string.
        ring_enabled: The stored column value, or ``None`` for "no override".
        ring_goal_days: The stored column value, or ``None`` for "no
            override".

    Returns:
        tuple[bool, int]: ``(effective_enabled, effective_goal_days)``.
    """
    band = age_band if age_band in _RING_DEFAULT_ENABLED else _UNKNOWN_BAND
    enabled = _RING_DEFAULT_ENABLED[band] if ring_enabled is None else ring_enabled
    goal_days = (
        _RING_DEFAULT_GOAL_DAYS[band] if ring_goal_days is None else ring_goal_days
    )
    # Clamped at BOTH ends, not just the cap. ``ResolvedGamificationSettingsView``
    # now declares ``RingGoalDays`` (ge=1, le=6), so a stored 0 or a negative,
    # which is exactly what a row written before the CHECK constraint existed
    # can hold, would fail response validation and 500 the whole progress read
    # rather than degrade. A floor also keeps the ring's own arithmetic sane:
    # the frontend divides by the goal to size ``strokeDashoffset``.
    return enabled, min(max(goal_days, RING_GOAL_DAYS_MIN), RING_GOAL_DAYS_MAX)


def _coerce_valence(raw: str, ending_id: str, storybook_id: str) -> Valence:
    """Map a blob's raw valence string onto the ``Valence`` enum.

    # #ASSUME: data integrity: every published version passed the validator,
    # whose Storybook schema constrains ``ending.valence`` to this enum, so an
    # unrecognized string means the stored blob predates or bypassed that gate
    # (a hand-edited row, a restored backup). ``FoundEndingView.valence`` is a
    # closed enum on the wire, so an unrecognized value would otherwise fail
    # response validation and 500 the entire gallery for one bad ending.
    # Degrading to NEUTRAL keeps the other endings readable and logs loudly
    # enough to find the row; NEUTRAL specifically because it is the valence
    # that makes no claim, so a corrupt ending is never miscoloured as a
    # triumph or a loss to a child.
    # #VERIFY: tests/unit/test_progress_api_unit.py::
    # test_unknown_ending_valence_degrades_to_neutral.

    Args:
        raw: The valence string as stored in the version blob.
        ending_id: The ending the value came from, for the log line.
        storybook_id: The book the ending belongs to, for the log line.

    Returns:
        Valence: The matching member, or ``Valence.NEUTRAL`` if unrecognized.
    """
    try:
        return Valence(raw)
    except ValueError:
        _logger.warning(
            "progress_unknown_ending_valence",
            storybook_id=storybook_id,
            ending_id=ending_id,
            raw_valence=raw,
        )
        return Valence.NEUTRAL


def _week_start(today: date) -> date:
    """Return the Monday that starts ``today``'s ISO week.

    Mirrors ``api/reading_history.py::_week_start`` exactly (same ISO-week,
    Monday-start definition the guardian summary uses for
    ``days_read_this_week``), duplicated here rather than imported because
    that helper is module-private and this module's touch scope
    (kid-appeal-implementation-plan.md W3 constraints) does not include
    editing ``reading_history.py`` to export it.
    """
    return today - timedelta(days=today.weekday())


def _reading_day_totals(rows: list[ReadingActivityDay], today: date) -> tuple[int, int]:
    """Return ``(days_read_this_week, lifetime_days_read)`` from day rows.

    # #ASSUME: timing dependencies: "today" is the server's current UTC date,
    # and each row's ``activity_date`` is the client-reported reader-local
    # date it was flushed under (api/reading_time.py's own #ASSUME on client
    # clocks applies transitively here); a day that straddles UTC midnight
    # for a reader in a different timezone may count against the "wrong"
    # server-week in a rare edge case. Acceptable for a literacy signal, not
    # a billing ledger, matching the reasoning already accepted for the
    # guardian summary's identical computation.
    # #VERIFY: tests/unit/test_progress_api_unit.py::TestReadingDayTotals.

    Args:
        rows: This profile's ``ReadingActivityDay`` rows (any window; a
            lifetime query is safe since retention is bounded to 12 months
            per the plan's adopted defaults).
        today: The server's current UTC date.

    Returns:
        tuple[int, int]: Days with any active reading time inside the
        current ISO week (Monday start), and lifetime distinct days with any
        active reading time.
    """
    week_start = _week_start(today)
    days_this_week = 0
    lifetime_days = 0
    for row in rows:
        if row.active_seconds <= 0:
            continue
        lifetime_days += 1
        if week_start <= row.activity_date <= today:
            days_this_week += 1
    return days_this_week, lifetime_days


def _require_child_profile(principal: Principal) -> uuid.UUID:
    """Return the caller's own profile id, rejecting a non-child principal.

    Args:
        principal: The authenticated principal.

    Returns:
        uuid.UUID: The child's own profile id.

    Raises:
        AuthorizationError: If the principal is not a child (see module
            docstring for why this endpoint has no guardian/admin path).
    """
    # #CRITICAL: security: this is the endpoint's entire authorization gate.
    # A CHILD Principal is structurally scoped to exactly one profile
    # (api/deps.py::Principal.__post_init__ / _child_principal), so taking
    # the single element of profile_ids can never leak a sibling's data; a
    # non-child principal is rejected outright rather than guessing which
    # profile it might mean.
    # #VERIFY: tests/unit/test_progress_api_unit.py::
    # test_guardian_and_admin_rejected; tests/integration/test_authz_matrix.py
    # ROUTE_TABLE entry for GET /me/progress.
    if principal.role != Role.CHILD:
        msg = "this endpoint is child-scoped; no guardian/admin surface exists yet"
        raise AuthorizationError(msg)
    return next(iter(principal.profile_ids))


@router.get("/me/progress")
async def get_my_progress(
    principal: CurrentPrincipal, session: DbSession
) -> ProgressView:
    """Return the caller's own badges, collection state, and lifetime totals.

    Args:
        principal: The authenticated principal (must be a child token).
        session: The request session.

    Returns:
        ProgressView: Earned badges, per-book collection state, and lifetime
        totals for the caller's own profile.

    Raises:
        AuthorizationError: If the caller is not a child.
    """
    profile_id = _require_child_profile(principal)

    completions = list(
        await session.scalars(
            select(Completion).where(Completion.child_profile_id == profile_id)
        )
    )
    ratings = list(
        await session.scalars(
            select(Rating).where(Rating.child_profile_id == profile_id)
        )
    )
    story_requests = list(
        await session.scalars(
            select(StoryRequest).where(StoryRequest.profile_id == profile_id)
        )
    )

    facts, found_endings_by_book = await _build_progress_facts(
        session, completions, ratings, story_requests
    )

    # W3.4: the profile row (age_band + the raw gamification columns) and the
    # reading-activity rows are loaded here rather than folded into
    # _build_progress_facts/compute_progress, since both are settings/day-
    # count concerns orthogonal to the badge/collection projection that
    # composer owns; keeping them separate avoids widening ProgressFacts (a
    # pure, DB-free dataclass) with DB-shaped concerns.
    profile_rows = list(
        await session.scalars(select(ChildProfile).where(ChildProfile.id == profile_id))
    )
    activity_rows = list(
        await session.scalars(
            select(ReadingActivityDay).where(
                ReadingActivityDay.child_profile_id == profile_id
            )
        )
    )
    today = datetime.now(UTC).date()
    days_read_this_week, lifetime_days_read = _reading_day_totals(activity_rows, today)

    # #EDGE: external resources: profile_row can only be None if the child's
    # own profile row vanished between token verification and this query (a
    # concurrent delete/erasure racing this request). Resolving that through
    # _UNKNOWN_BAND rather than inventing a mid-range band keeps the whole
    # module on one fallback policy: an age we cannot establish is treated as
    # the youngest, so a race degrades to the least-pressuring settings rather
    # than raising or guessing upward.
    profile_row = profile_rows[0] if profile_rows else None
    ring_enabled, ring_goal_days = _resolve_ring_settings(
        profile_row.age_band if profile_row is not None else _UNKNOWN_BAND,
        profile_row.ring_enabled if profile_row is not None else None,
        profile_row.ring_goal_days if profile_row is not None else None,
    )
    settings = ResolvedGamificationSettingsView(
        ring_enabled=ring_enabled,
        ring_goal_days=ring_goal_days,
        badges_enabled=(
            profile_row.badges_enabled if profile_row is not None else True
        ),
        # #CRITICAL: security: a missing row resolves to PAUSED, not to the
        # column default. The other two fall back to their column defaults
        # because they are decoration; this one is the guardian privacy toggle,
        # and api/reading_time.py::flush_reading_time already reasons the
        # opposite way for the identical condition ("failing open there would
        # record behavioural data for a profile whose settings cannot be
        # read"). Resolving False here told the client accumulator to start
        # measuring and transmitting for a profile whose settings the server
        # cannot read, which the flush endpoint would then discard: work the
        # child's device should never have done. The only way to reach this is
        # a delete/erasure racing the request, where "keep recording" is
        # exactly the wrong default. This is also what the #EDGE note above
        # already claims the whole module does (degrade to the least-pressuring
        # settings); the ring obeyed it via _UNKNOWN_BAND, this did not.
        # #VERIFY: tests/unit/test_progress_api_unit.py::
        # test_missing_profile_row_resolves_time_capture_to_paused.
        time_capture_paused=(
            profile_row.time_capture_paused if profile_row is not None else True
        ),
    )

    return _to_view(
        facts,
        _ProgressExtras(
            found_endings_by_book=found_endings_by_book,
            days_read_this_week=days_read_this_week,
            lifetime_days_read=lifetime_days_read,
            settings=settings,
        ),
    )


async def _load_touched_books(
    session: AsyncSession, completions: list[Completion]
) -> dict[str, Storybook]:
    """Bulk-load every ``Storybook`` a profile's completions reference."""
    book_ids = {completion.storybook_id for completion in completions}
    if not book_ids:
        return {}
    return {
        book.id: book
        for book in await session.scalars(
            select(Storybook).where(Storybook.id.in_(book_ids))
        )
    }


async def _load_versions(
    session: AsyncSession, completions: list[Completion], books: dict[str, Storybook]
) -> dict[tuple[str, int], StorybookVersion]:
    """Bulk-load every played version plus each book's current published one.

    The played versions feed badge 7's valence lookup (a completion's own
    version, not necessarily the current one); the current published
    versions feed the collection-state totals/titles (mirrors
    ``reading_history.py``).
    """
    version_keys: set[tuple[str, int]] = {
        (completion.storybook_id, completion.version) for completion in completions
    }
    for book in books.values():
        if book.current_published_version is not None:
            version_keys.add((book.id, book.current_published_version))
    if not version_keys:
        return {}
    version_rows = await session.scalars(
        select(StorybookVersion).where(
            tuple_(StorybookVersion.storybook_id, StorybookVersion.version).in_(
                version_keys
            )
        )
    )
    return {(row.storybook_id, row.version): row for row in version_rows}


def _build_ending_valence(
    versions: dict[tuple[str, int], StorybookVersion],
) -> dict[tuple[str, int, str], str]:
    """Flatten every played version's blob into (book, version, ending) valence."""
    ending_valence: dict[tuple[str, int, str], str] = {}
    for (storybook_id, version), row in versions.items():
        for ending_id, valence in ending_valence_map(row.blob).items():
            ending_valence[(storybook_id, version, ending_id)] = valence
    return ending_valence


def _build_current_version_facts(
    books: dict[str, Storybook], versions: dict[tuple[str, int], StorybookVersion]
) -> tuple[dict[str, int], dict[str, str]]:
    """Return (ending_total_by_book, book_titles) from each book's pinned version.

    # #ASSUME: data integrity: a book absent from the returned mapping reads
    # downstream as a total of 0 (``badges.py`` uses ``.get(id, 0)``), and
    # badges are recomputed from scratch on every request with nothing
    # persisted. So a book whose pinned version cannot be resolved does not
    # merely lose a number: ``every_path_walked`` and the "walked every path"
    # badge both go from earned to unearned for as long as the condition
    # lasts, and a child sees a badge they already collected disappear. The
    # ``> 0`` guard in ``badges.py`` makes the DIRECTION safe (a missing total
    # can never falsely award), which is why this degrades rather than raises.
    # Both skips below are now logged, matching ``progress/blob.py``, which
    # logs its own malformed-blob degrade rather than swallowing it.
    # #VERIFY: tests/unit/test_progress_api_unit.py::
    # test_book_with_an_unresolvable_pinned_version_is_skipped_and_logged.
    """
    ending_total_by_book: dict[str, int] = {}
    book_titles: dict[str, str] = {}
    for book_id, book in books.items():
        pinned_version = book.current_published_version
        if pinned_version is None:
            # Ordinary for a book that has never published; noisy only if it
            # happens for a book the child has a completion against, which is
            # exactly the case worth seeing in the log.
            _logger.info(
                "progress_book_has_no_published_version",
                storybook_id=book_id,
            )
            continue
        pinned_row = versions.get((book_id, pinned_version))
        if pinned_row is None:
            # Not ordinary: the book points at a version row that was not
            # loaded, which means the pin is dangling or the query missed it.
            _logger.warning(
                "progress_pinned_version_row_missing",
                storybook_id=book_id,
                version=pinned_version,
            )
            continue
        ending_total_by_book[book_id] = ending_count(
            pinned_row.blob, book_id, pinned_version
        )
        book_titles[book_id] = book_title(pinned_row.blob, book_id, pinned_version)
    return ending_total_by_book, book_titles


async def _load_series_membership(
    session: AsyncSession, books: dict[str, Storybook]
) -> dict[str, frozenset[str]]:
    """Return ``series_id -> every storybook_id in that series`` (badge 11).

    Loads the FULL series roster, not only the books this profile has
    touched, since "finished every book in the series" must be checked
    against every book that exists in it.
    """
    series_ids = {
        book.series_id for book in books.values() if book.series_id is not None
    }
    if not series_ids:
        return {}
    series_rows = await session.scalars(
        select(Storybook).where(Storybook.series_id.in_(series_ids))
    )
    grouped: dict[str, set[str]] = {}
    for row in series_rows:
        if row.series_id is not None:
            grouped.setdefault(str(row.series_id), set()).add(row.id)
    return {sid: frozenset(ids) for sid, ids in grouped.items()}


def _ending_titles_map(blob: dict[str, object]) -> dict[str, str]:
    """Return ``{ending_id: title}`` declared in a stored Storybook blob.

    Deliberately duplicated in shape from
    ``progress/blob.py::ending_valence_map`` (identical node-walking
    pattern) rather than extending that module: this change's touch scope
    (kid-appeal-implementation-plan.md W3 constraints) does not include
    editing ``progress/blob.py``, and that module's own docstring already
    names this repo's small-helper-duplication convention as the reason it
    has no cross-router dependency either.

    Args:
        blob: A stored Storybook content blob (any played version, not
            necessarily the current published one).

    Returns:
        dict[str, str]: One entry per ending node with both a string id and
        a string title; a malformed node is skipped, mirroring
        ``ending_valence_map``.
    """
    nodes = blob.get("nodes")
    if not isinstance(nodes, list):
        return {}
    result: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict) or node.get("is_ending") is not True:
            continue
        ending = node.get("ending")
        if not isinstance(ending, dict):
            continue
        ending_id = ending.get("id")
        title = ending.get("title")
        if isinstance(ending_id, str) and isinstance(title, str):
            result[ending_id] = title
    return result


def _build_found_endings(
    completions: list[Completion],
    versions: dict[tuple[str, int], StorybookVersion],
) -> dict[str, list[FoundEndingView]]:
    """Return ``storybook_id -> found-ending cards`` for the Endings Gallery.

    One card per DISTINCT (book, ending) this profile has ever found, oldest
    find first; each ending's title/valence come from the SPECIFIC version it
    was found on (not necessarily the current published version), so a
    republished rewrite cannot make an already-found ending's card show a
    since-changed title. An ending id whose version blob is missing or
    malformed is skipped rather than raising (mirrors this module's other
    blob-parsing helpers): a corrupt row loses one card, never the whole
    projection.

    Args:
        completions: The profile's completion rows (any order).
        versions: Every played version's row, keyed by (storybook_id,
            version); built by ``_load_versions``.

    Returns:
        dict[str, list[FoundEndingView]]: Per-book found-ending cards, oldest
        find first.
    """
    earliest_found_at: dict[tuple[str, str], datetime] = {}
    cards: dict[tuple[str, str], FoundEndingView] = {}
    for completion in completions:
        key = (completion.storybook_id, completion.ending_id)
        version_row = versions.get((completion.storybook_id, completion.version))
        if version_row is None:
            continue
        titles = _ending_titles_map(version_row.blob)
        valences = ending_valence_map(version_row.blob)
        raw_title = titles.get(completion.ending_id)
        valence = valences.get(completion.ending_id)
        if raw_title is None or valence is None:
            continue
        # #CRITICAL: security: an ending title is blob-projected, kid-facing
        # text (ADR-023 P3), exactly like book_title() above; a raw
        # personalization sentinel must never reach the gallery.
        # #VERIFY: tests/unit/test_progress_api_unit.py::
        # test_found_ending_title_strips_sentinels;
        # tests/unit/test_title_strip_registry.py's FoundEndingView row.
        title = strip_and_log(
            raw_title,
            at="progress_found_ending.title",
            storybook_id=completion.storybook_id,
            version=completion.version,
        )
        if key not in cards:
            cards[key] = FoundEndingView(
                ending_id=completion.ending_id,
                title=title,
                valence=_coerce_valence(
                    valence, completion.ending_id, completion.storybook_id
                ),
            )
            earliest_found_at[key] = completion.found_at
        elif completion.found_at < earliest_found_at[key]:
            earliest_found_at[key] = completion.found_at

    by_book: dict[str, list[tuple[datetime, FoundEndingView]]] = {}
    for (storybook_id, _ending_id), card in cards.items():
        found_at = earliest_found_at[(storybook_id, card.ending_id)]
        by_book.setdefault(storybook_id, []).append((found_at, card))
    return {
        storybook_id: [card for _found_at, card in sorted(rows, key=lambda row: row[0])]
        for storybook_id, rows in by_book.items()
    }


async def _build_progress_facts(
    session: AsyncSession,
    completions: list[Completion],
    ratings: list[Rating],
    story_requests: list[StoryRequest],
) -> tuple[ProgressFacts, dict[str, list[FoundEndingView]]]:
    """Load the blob/series facts the pure composer needs, then compose.

    # #ASSUME: external resources: a fixed, small number of bulk queries
    # regardless of how many books this profile has touched (no N+1 over
    # blobs), mirroring reading_history.py::get_reading_history.
    # #VERIFY: tests/unit/test_progress_api_unit.py asserts the query count.
    """
    books = await _load_touched_books(session, completions)
    versions = await _load_versions(session, completions, books)
    ending_valence = _build_ending_valence(versions)
    ending_total_by_book, book_titles = _build_current_version_facts(books, versions)
    series_membership = await _load_series_membership(session, books)
    series_by_book = {
        book_id: (str(book.series_id) if book.series_id is not None else None)
        for book_id, book in books.items()
    }
    found_endings_by_book = _build_found_endings(completions, versions)

    facts = compute_progress(
        completions=completions,
        ratings=ratings,
        child_story_requests=story_requests,
        book_facts=BookFacts(
            ending_valence=ending_valence,
            ending_total_by_book=ending_total_by_book,
            book_titles=book_titles,
            series_by_book=series_by_book,
            series_membership=series_membership,
        ),
    )
    return facts, found_endings_by_book


@dataclass(frozen=True, slots=True)
class _ProgressExtras:
    """The W3.2/W3.4 additions bundled so ``_to_view`` stays within PLR0913.

    Mirrors ``progress/models.py::BookFacts``'s own "bundled into one value
    so the function stays within this project's argument-count lint budget"
    rationale.
    """

    found_endings_by_book: dict[str, list[FoundEndingView]]
    days_read_this_week: int
    lifetime_days_read: int
    settings: ResolvedGamificationSettingsView


def _to_view(facts: ProgressFacts, extras: _ProgressExtras) -> ProgressView:
    """Convert the pure-computed facts plus the W3.2/W3.4 additions into the wire view."""
    found_endings_by_book = extras.found_endings_by_book
    return ProgressView(
        badges=[
            EarnedBadgeView(
                id=badge.id,
                name=badge.name,
                description=badge.description,
                earned_at=badge.earned_at,
            )
            for badge in facts.badges
        ],
        books=[
            BookProgressView(
                storybook_id=book.storybook_id,
                title=book.title,
                endings_found=book.endings_found,
                total_endings=book.total_endings,
                finished=book.finished,
                every_path_walked=book.every_path_walked,
                found_endings=found_endings_by_book.get(book.storybook_id, []),
            )
            for book in facts.books
        ],
        totals=ProgressTotalsView(
            books_finished=facts.totals.books_finished,
            endings_found=facts.totals.endings_found,
        ),
        days_read_this_week=extras.days_read_this_week,
        lifetime_days_read=extras.lifetime_days_read,
        settings=extras.settings,
    )
