"""Unit tests for the reading-history API handlers (no DB, no ASGI stack).

Calls the route functions directly with a fake session and a constructed
principal, following the pattern established in test_library_api_unit.py and
test_ratings_api_unit.py. Covers ``get_reading_history`` (K6, the kid endings
tracker) and ``get_family_reading_summary`` (G9, guardian engagement
visibility): authorization (child-own-profile, guardian-family, admin-bypass,
cross-family rejection, child rejected from the family summary), dedup of
completions across versions, the pinned-version total_endings/title read, the
in_progress node lookup against the STATE's own pinned version (not
necessarily the book's current published version), empty states, and the
fixed (no-N+1) query count.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.api.reading_history import (
    _book_title,
    _ending_count,
    _is_ending_node,
    _parse_profile_id,
    get_family_reading_summary,
    get_reading_history,
)
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.db.models import (
    ChildProfile,
    Completion,
    ReadingState,
    Storybook,
    StorybookVersion,
)

_T1 = datetime(2026, 1, 1, tzinfo=UTC)
_T2 = datetime(2026, 1, 2, tzinfo=UTC)
_T3 = datetime(2026, 1, 3, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fake session
# ---------------------------------------------------------------------------


class _FakeScalars:
    """Returned by session.scalars() -- wraps a list of ORM rows."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        """Return the seeded rows."""
        return self._rows

    def __iter__(self) -> object:
        """Support direct iteration (e.g. `for row in scalars_result`)."""
        return iter(self._rows)


class _FakeSession:
    """Minimal async session double: session.scalars() drains an ordered queue."""

    def __init__(self, queue: list[list[object]]) -> None:
        self._queue: list[list[object]] = [list(rows) for rows in queue]
        self.scalars_calls: list[object] = []

    async def scalars(self, stmt: object) -> _FakeScalars:
        """Return the next queued row list, in call order."""
        self.scalars_calls.append(stmt)
        rows = self._queue.pop(0) if self._queue else []
        return _FakeScalars(rows)


# ---------------------------------------------------------------------------
# Principal builders
# ---------------------------------------------------------------------------


def _child_principal(family_id: uuid.UUID, profile_id: uuid.UUID) -> Principal:
    """Build a child principal allowed to act on exactly one profile."""
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="child",
        family_id=family_id,
        profile_ids=frozenset({profile_id}),
    )


def _guardian_principal(
    family_id: uuid.UUID, profile_ids: frozenset[uuid.UUID] = frozenset()
) -> Principal:
    """Build a guardian principal, optionally scoped to specific profiles."""
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=family_id,
        profile_ids=profile_ids,
    )


def _admin_principal(family_id: uuid.UUID) -> Principal:
    """Build a global admin principal (cross-family read authority)."""
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="admin",
        family_id=family_id,
        profile_ids=frozenset(),
    )


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------


def _completion(
    profile_id: uuid.UUID,
    storybook_id: str,
    ending_id: str,
    *,
    version: int = 1,
    found_at: datetime = _T1,
) -> Completion:
    row = Completion(
        child_profile_id=profile_id,
        storybook_id=storybook_id,
        version=version,
        ending_id=ending_id,
    )
    row.found_at = found_at
    return row


def _state(
    profile_id: uuid.UUID,
    storybook_id: str,
    *,
    version: int = 1,
    current_node: str = "n1",
    updated_at: datetime = _T1,
) -> ReadingState:
    row = ReadingState(
        child_profile_id=profile_id,
        storybook_id=storybook_id,
        version=version,
        current_node=current_node,
    )
    row.updated_at = updated_at
    return row


def _book(
    storybook_id: str, family_id: uuid.UUID, current_version: int | None
) -> Storybook:
    book = Storybook(id=storybook_id, family_id=family_id)
    book.current_published_version = current_version
    return book


def _version(
    storybook_id: str,
    version: int,
    *,
    title: str = "A Story",
    ending_count: int = 2,
    nodes: list[dict[str, object]] | None = None,
) -> StorybookVersion:
    blob: dict[str, object] = {
        "title": title,
        "metadata": {"ending_count": ending_count},
        "nodes": nodes if nodes is not None else [],
    }
    return StorybookVersion(storybook_id=storybook_id, version=version, blob=blob)


# ---------------------------------------------------------------------------
# _parse_profile_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_profile_id_valid() -> None:
    """A valid UUID string round-trips."""
    raw = str(uuid.uuid4())
    assert str(_parse_profile_id(raw)) == raw


@pytest.mark.unit
def test_parse_profile_id_invalid_raises() -> None:
    """A non-UUID string raises ValidationError naming the field."""
    with pytest.raises(ValidationError) as exc_info:
        _parse_profile_id("not-a-uuid")
    assert "profile_id" in str(exc_info.value)


# ---------------------------------------------------------------------------
# _book_title / _ending_count / _is_ending_node
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_book_title_uses_blob_title() -> None:
    assert _book_title({"title": "Space Race"}, "fallback") == "Space Race"


@pytest.mark.unit
def test_book_title_falls_back_on_missing_title() -> None:
    assert _book_title({}, "fallback-id") == "fallback-id"


@pytest.mark.unit
def test_book_title_falls_back_on_non_string_title() -> None:
    assert _book_title({"title": 42}, "fallback-id") == "fallback-id"


@pytest.mark.unit
def test_ending_count_reads_metadata() -> None:
    blob = {"metadata": {"ending_count": 5}}
    assert _ending_count(blob, "s1", 1) == 5


@pytest.mark.unit
def test_ending_count_missing_metadata_defaults_zero() -> None:
    assert _ending_count({}, "s1", 1) == 0


@pytest.mark.unit
def test_ending_count_non_dict_metadata_defaults_zero() -> None:
    assert _ending_count({"metadata": "nope"}, "s1", 1) == 0


@pytest.mark.unit
def test_ending_count_bool_rejected_as_non_int(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bool ending_count (True) must not read as 1; it degrades to 0 and logs."""
    with caplog.at_level("WARNING"):
        result = _ending_count({"metadata": {"ending_count": True}}, "s1", 3)
    assert result == 0
    assert "reading_history_malformed_ending_count" in caplog.text


@pytest.mark.unit
def test_ending_count_non_int_logs_and_defaults_zero(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        result = _ending_count({"metadata": {"ending_count": "seven"}}, "s1", 3)
    assert result == 0
    assert "reading_history_malformed_ending_count" in caplog.text


@pytest.mark.unit
def test_is_ending_node_true_for_ending() -> None:
    blob = {
        "nodes": [{"id": "n1", "is_ending": False}, {"id": "n2", "is_ending": True}]
    }
    assert _is_ending_node(blob, "n2") is True


@pytest.mark.unit
def test_is_ending_node_false_for_non_ending() -> None:
    blob = {"nodes": [{"id": "n1", "is_ending": False}]}
    assert _is_ending_node(blob, "n1") is False


@pytest.mark.unit
def test_is_ending_node_missing_node_defaults_false() -> None:
    blob = {"nodes": [{"id": "n1", "is_ending": True}]}
    assert _is_ending_node(blob, "unknown-node") is False


@pytest.mark.unit
def test_is_ending_node_non_list_nodes_defaults_false() -> None:
    assert _is_ending_node({"nodes": "not-a-list"}, "n1") is False


# ---------------------------------------------------------------------------
# get_reading_history: authorization
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_uuid_profile_raises_validation_error() -> None:
    family_id = uuid.uuid4()
    session = _FakeSession([])
    principal = _guardian_principal(family_id)

    with pytest.raises(ValidationError):
        await get_reading_history("not-a-uuid", principal, session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_child_cannot_read_another_profile_history() -> None:
    """Child A cannot read child B's history (IDOR)."""
    family_id = uuid.uuid4()
    my_profile = uuid.uuid4()
    other_profile = uuid.uuid4()
    session = _FakeSession([])
    principal = _child_principal(family_id, my_profile)
    other_profile_str = str(other_profile)

    with pytest.raises(AuthorizationError):
        await get_reading_history(other_profile_str, principal, session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_child_can_read_own_profile_history() -> None:
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    session = _FakeSession([[], []])
    principal = _child_principal(family_id, profile_id)

    result = await get_reading_history(str(profile_id), principal, session)

    assert result.profile_id == str(profile_id)
    assert result.books == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cross_family_guardian_is_rejected() -> None:
    """A guardian whose family does not include the profile gets 403."""
    my_family = uuid.uuid4()
    other_profile = uuid.uuid4()
    session = _FakeSession([])
    # A guardian principal scoped to none of the requested profiles (mirrors
    # a guardian from a different family, per _resolve_profiles in deps.py).
    principal = _guardian_principal(my_family, frozenset())
    other_profile_str = str(other_profile)

    with pytest.raises(AuthorizationError):
        await get_reading_history(other_profile_str, principal, session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_reads_any_profile_history_bypassing_ownership() -> None:
    """An admin may read a profile's history even outside its own family."""
    admin_family = uuid.uuid4()
    other_profile = uuid.uuid4()
    session = _FakeSession([[], []])
    principal = _admin_principal(admin_family)

    result = await get_reading_history(str(other_profile), principal, session)

    assert result.profile_id == str(other_profile)
    assert result.books == []


# ---------------------------------------------------------------------------
# get_reading_history: correctness
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_history_returns_empty_books_with_two_queries() -> None:
    """No completions and no reading state -> empty list; short-circuits early."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    session = _FakeSession([[], []])
    principal = _child_principal(family_id, profile_id)

    result = await get_reading_history(str(profile_id), principal, session)

    assert result.books == []
    # Only the completions and reading-state queries run; no book/version
    # fetch is issued once both are known to be empty.
    assert len(session.scalars_calls) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repeated_ending_across_versions_dedups() -> None:
    """The same ending_id found under two versions counts once (a set, not a list)."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    completions = [
        _completion(profile_id, "story-1", "e1", version=1, found_at=_T1),
        _completion(profile_id, "story-1", "e1", version=2, found_at=_T2),
    ]
    state = _state(
        profile_id,
        "story-1",
        version=2,
        current_node="n2",
        updated_at=_T3,
    )
    book = _book("story-1", family_id, current_version=2)
    version_row = _version(
        "story-1",
        2,
        title="The Dragon's Den",
        ending_count=3,
        nodes=[
            {"id": "n1", "is_ending": False},
            {"id": "n2", "is_ending": False},
            {"id": "n3", "is_ending": True},
        ],
    )
    session = _FakeSession([completions, [state], [book], [version_row]])
    principal = _child_principal(family_id, profile_id)

    result = await get_reading_history(str(profile_id), principal, session)

    assert len(result.books) == 1
    item = result.books[0]
    assert item.storybook_id == "story-1"
    assert item.title == "The Dragon's Den"
    assert item.endings_found == 1
    assert item.ending_ids == ["e1"]
    assert item.total_endings == 3
    assert item.in_progress is True
    assert item.last_activity_at == _T3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_progress_false_when_current_node_is_an_ending() -> None:
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    state = _state(profile_id, "story-1", version=1, current_node="n3", updated_at=_T1)
    book = _book("story-1", family_id, current_version=1)
    version_row = _version(
        "story-1",
        1,
        nodes=[{"id": "n3", "is_ending": True}],
    )
    session = _FakeSession([[], [state], [book], [version_row]])
    principal = _child_principal(family_id, profile_id)

    result = await get_reading_history(str(profile_id), principal, session)

    assert result.books[0].in_progress is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_progress_checked_against_states_own_pinned_version() -> None:
    """in_progress reads the STATE's version blob, not the book's current one.

    A book republished to v3 (a fresh ending layout) must not make an older,
    still-in-progress v1 save look finished (or vice versa): the state's own
    pinned version is the one that determines whether current_node is a
    terminal node.
    """
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    # The reading state is pinned to v1, where its current_node IS an ending.
    state = _state(
        profile_id, "story-2", version=1, current_node="old-end", updated_at=_T1
    )
    book = _book("story-2", family_id, current_version=3)
    v1 = _version(
        "story-2",
        1,
        title="Old Title",
        ending_count=1,
        nodes=[{"id": "old-end", "is_ending": True}],
    )
    v3 = _version(
        "story-2",
        3,
        title="Latest Title",
        ending_count=5,
        nodes=[{"id": "old-end", "is_ending": False}],
    )
    session = _FakeSession([[], [state], [book], [v1, v3]])
    principal = _child_principal(family_id, profile_id)

    result = await get_reading_history(str(profile_id), principal, session)

    item = result.books[0]
    # Title/total_endings come from the CURRENT published version (v3)...
    assert item.title == "Latest Title"
    assert item.total_endings == 5
    # ...but in_progress is resolved against the STATE's own version (v1),
    # where "old-end" really is a terminal node.
    assert item.in_progress is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_book_with_no_current_published_version_degrades() -> None:
    """An archived book (no current_published_version) falls back safely."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    completions = [_completion(profile_id, "story-old", "e1", found_at=_T1)]
    book = _book("story-old", family_id, current_version=None)
    session = _FakeSession([completions, [], [book], []])
    principal = _child_principal(family_id, profile_id)

    result = await get_reading_history(str(profile_id), principal, session)

    item = result.books[0]
    assert item.title == "story-old"
    assert item.total_endings == 0
    assert item.in_progress is False
    assert item.last_activity_at == _T1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_books_sorted_by_last_activity_desc() -> None:
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    completions = [
        _completion(profile_id, "story-a", "e1", found_at=_T1),
        _completion(profile_id, "story-b", "e1", found_at=_T3),
    ]
    books = [
        _book("story-a", family_id, current_version=1),
        _book("story-b", family_id, current_version=1),
    ]
    versions = [_version("story-a", 1), _version("story-b", 1)]
    session = _FakeSession([completions, [], books, versions])
    principal = _child_principal(family_id, profile_id)

    result = await get_reading_history(str(profile_id), principal, session)

    assert [b.storybook_id for b in result.books] == ["story-b", "story-a"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bulk_fetch_stays_at_four_queries_for_multiple_books() -> None:
    """No N+1 over blobs: exactly one bulk book fetch and one bulk version fetch."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    completions = [
        _completion(profile_id, "story-a", "e1", found_at=_T1),
        _completion(profile_id, "story-b", "e1", found_at=_T2),
        _completion(profile_id, "story-c", "e1", found_at=_T3),
    ]
    books = [
        _book("story-a", family_id, current_version=1),
        _book("story-b", family_id, current_version=1),
        _book("story-c", family_id, current_version=1),
    ]
    versions = [
        _version("story-a", 1),
        _version("story-b", 1),
        _version("story-c", 1),
    ]
    session = _FakeSession([completions, [], books, versions])
    principal = _child_principal(family_id, profile_id)

    result = await get_reading_history(str(profile_id), principal, session)

    assert len(result.books) == 3
    # completions, reading-states, storybooks, versions: fixed at 4 regardless
    # of how many books this profile has touched.
    assert len(session.scalars_calls) == 4


# ---------------------------------------------------------------------------
# get_family_reading_summary: authorization
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_child_cannot_read_family_summary() -> None:
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    session = _FakeSession([])
    principal = _child_principal(family_id, profile_id)

    with pytest.raises(AuthorizationError):
        await get_family_reading_summary(principal, session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_guardian_reads_own_family_summary() -> None:
    family_id = uuid.uuid4()
    session = _FakeSession([[]])
    principal = _guardian_principal(family_id)

    result = await get_family_reading_summary(principal, session)

    assert result.children == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_reads_own_family_summary() -> None:
    family_id = uuid.uuid4()
    session = _FakeSession([[]])
    principal = _admin_principal(family_id)

    result = await get_family_reading_summary(principal, session)

    assert result.children == []


# ---------------------------------------------------------------------------
# get_family_reading_summary: correctness
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_family_summary_empty_family_short_circuits() -> None:
    """No child profiles at all -> empty list, only the profile query runs."""
    family_id = uuid.uuid4()
    session = _FakeSession([[]])
    principal = _guardian_principal(family_id)

    result = await get_family_reading_summary(principal, session)

    assert result.children == []
    assert len(session.scalars_calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_family_summary_aggregates_per_child_with_three_queries() -> None:
    family_id = uuid.uuid4()
    child_a = ChildProfile(family_id=family_id, display_name="Reader A", age_band="6-8")
    child_a.id = uuid.uuid4()
    child_a.created_at = _T1
    child_b = ChildProfile(family_id=family_id, display_name="Reader B", age_band="6-8")
    child_b.id = uuid.uuid4()
    child_b.created_at = _T2

    # Child A: one book started AND finished (a completion), one endings found.
    state_a = _state(child_a.id, "story-1", updated_at=_T1)
    completion_a = _completion(child_a.id, "story-1", "e1", found_at=_T2)
    # Child B: one book started only (a reading state, no completion yet).
    state_b = _state(child_b.id, "story-2", updated_at=_T3)

    session = _FakeSession(
        [
            [child_a, child_b],
            [state_a, state_b],
            [completion_a],
        ]
    )
    principal = _guardian_principal(family_id)

    result = await get_family_reading_summary(principal, session)

    assert len(session.scalars_calls) == 3
    by_id = {c.profile_id: c for c in result.children}
    a = by_id[str(child_a.id)]
    assert a.display_name == "Reader A"
    assert a.books_started == 1
    assert a.books_finished == 1
    assert a.total_endings_found == 1
    assert a.last_activity_at == _T2

    b = by_id[str(child_b.id)]
    assert b.books_started == 1
    assert b.books_finished == 0
    assert b.total_endings_found == 0
    assert b.last_activity_at == _T3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_family_summary_child_with_no_activity_is_all_zero() -> None:
    family_id = uuid.uuid4()
    child = ChildProfile(
        family_id=family_id, display_name="Quiet Reader", age_band="6-8"
    )
    child.id = uuid.uuid4()
    child.created_at = _T1
    session = _FakeSession([[child], [], []])
    principal = _guardian_principal(family_id)

    result = await get_family_reading_summary(principal, session)

    assert len(result.children) == 1
    item = result.children[0]
    assert item.books_started == 0
    assert item.books_finished == 0
    assert item.total_endings_found == 0
    assert item.last_activity_at is None
