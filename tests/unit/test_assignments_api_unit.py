"""Unit tests for the assignments API handlers and schemas (no DB, no ASGI)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.schemas import AssignmentCreateBody, AssignmentListView
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TestAssignmentSchemas:
    @pytest.mark.unit
    def test_create_body_requires_at_least_one_profile(self) -> None:
        """An empty profile_ids list is rejected."""
        with pytest.raises(ValueError, match="profile_ids"):
            AssignmentCreateBody(profile_ids=[])

    @pytest.mark.unit
    def test_create_body_forbids_extra_fields(self) -> None:
        """Unknown fields are rejected (extra='forbid')."""
        with pytest.raises(ValueError, match="Extra inputs"):
            AssignmentCreateBody.model_validate({"profile_ids": ["a"], "surprise": 1})

    @pytest.mark.unit
    def test_list_view_round_trips(self) -> None:
        """The list view carries the storybook id and profile ids."""
        view = AssignmentListView(storybook_id="s1", profile_ids=["p1", "p2"])
        assert view.storybook_id == "s1"
        assert view.profile_ids == ["p1", "p2"]


class _FakeScalars:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows

    def __iter__(self) -> object:
        return iter(self._rows)


class _FakeSession:
    """Minimal async session double for the assignments handlers."""

    def __init__(
        self,
        *,
        book: object | None = None,
        assigned: list[object] | None = None,
        version: object | None = None,
    ) -> None:
        self._book = book
        self._assigned = list(assigned or [])
        self._version = version
        self.added: list[object] = []
        self.flushed = False

    async def get(self, model: type[object], key: object) -> object | None:
        from cyo_adventure.db.models import StorybookVersion

        if model is StorybookVersion:
            return self._version
        return self._book

    async def scalars(self, stmt: object) -> _FakeScalars:
        return _FakeScalars(self._assigned)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed = True


def _guardian(family_id: uuid.UUID, profiles: set[uuid.UUID]) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=family_id,
        profile_ids=frozenset(profiles),
    )


def _child(family_id: uuid.UUID, profile_id: uuid.UUID) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="child",
        family_id=family_id,
        profile_ids=frozenset({profile_id}),
    )


def _admin(family_id: uuid.UUID, profiles: set[uuid.UUID]) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="admin",
        family_id=family_id,
        profile_ids=frozenset(profiles),
    )


def _ctx(principal: Principal, session: _FakeSession) -> RequestContext:
    return RequestContext(principal=principal, session=cast("AsyncSession", session))


def _book(storybook_id: str, family_id: uuid.UUID, status: str = "published") -> object:
    from cyo_adventure.db.models import Storybook

    b = Storybook(id=storybook_id, family_id=family_id)
    b.status = status
    return b


class TestAssignStorybook:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_guardian_assigns_returns_sorted_ids(self) -> None:
        from cyo_adventure.api.assignments import assign_storybook
        from cyo_adventure.db.models import StorybookAssignment

        fam = uuid.uuid4()
        p1, p2 = uuid.uuid4(), uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam))
        body = AssignmentCreateBody(profile_ids=[str(p1), str(p2)])
        view = await assign_storybook(
            "s1", body, _ctx(_guardian(fam, {p1, p2}), session)
        )
        assert view.storybook_id == "s1"
        assert view.profile_ids == sorted([str(p1), str(p2)])
        added_assignments = [
            obj for obj in session.added if isinstance(obj, StorybookAssignment)
        ]
        assert len(added_assignments) == 2
        assert session.flushed

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_idempotent_skips_existing(self) -> None:
        from cyo_adventure.api.assignments import assign_storybook

        fam = uuid.uuid4()
        p1 = uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam), assigned=[p1])
        body = AssignmentCreateBody(profile_ids=[str(p1)])
        view = await assign_storybook("s1", body, _ctx(_guardian(fam, {p1}), session))
        assert session.added == []  # already assigned, no insert
        assert view.profile_ids == [str(p1)]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_duplicate_profile_ids_insert_once(self) -> None:
        """Duplicate ids in one request must not double-insert."""
        from cyo_adventure.api.assignments import assign_storybook
        from cyo_adventure.db.models import StorybookAssignment

        fam = uuid.uuid4()
        p1 = uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam))
        body = AssignmentCreateBody(profile_ids=[str(p1), str(p1)])
        view = await assign_storybook("s1", body, _ctx(_guardian(fam, {p1}), session))
        added_assignments = [
            obj for obj in session.added if isinstance(obj, StorybookAssignment)
        ]
        assert len(added_assignments) == 1
        assert view.profile_ids == [str(p1)]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_token_forbidden(self) -> None:
        from cyo_adventure.api.assignments import assign_storybook
        from cyo_adventure.core.exceptions import AuthorizationError

        fam = uuid.uuid4()
        p1 = uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam))
        body = AssignmentCreateBody(profile_ids=[str(p1)])
        with pytest.raises(
            AuthorizationError, match=r"only a guardian may manage assignments"
        ):
            await assign_storybook("s1", body, _ctx(_child(fam, p1), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_admin_token_forbidden(self) -> None:
        """An admin is a cross-family safety reviewer, not a family assigner."""
        from cyo_adventure.api.assignments import assign_storybook
        from cyo_adventure.core.exceptions import AuthorizationError

        fam = uuid.uuid4()
        p1 = uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam))
        body = AssignmentCreateBody(profile_ids=[str(p1)])
        with pytest.raises(
            AuthorizationError, match=r"only a guardian may manage assignments"
        ):
            await assign_storybook("s1", body, _ctx(_admin(fam, {p1}), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unknown_storybook_404(self) -> None:
        from cyo_adventure.api.assignments import assign_storybook
        from cyo_adventure.core.exceptions import ResourceNotFoundError

        fam = uuid.uuid4()
        p1 = uuid.uuid4()
        session = _FakeSession(book=None)
        body = AssignmentCreateBody(profile_ids=[str(p1)])
        with pytest.raises(ResourceNotFoundError, match=r"storybook 'nope' not found"):
            await assign_storybook("nope", body, _ctx(_guardian(fam, {p1}), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cross_family_existing_storybook_403(self) -> None:
        """An EXISTING book in another family is 403, per the ratings.py convention."""
        from cyo_adventure.api.assignments import assign_storybook
        from cyo_adventure.core.exceptions import AuthorizationError

        fam, other = uuid.uuid4(), uuid.uuid4()
        p1 = uuid.uuid4()
        session = _FakeSession(book=_book("s1", other))
        body = AssignmentCreateBody(profile_ids=[str(p1)])
        with pytest.raises(
            AuthorizationError, match=r"resource belongs to another family"
        ):
            await assign_storybook("s1", body, _ctx(_guardian(fam, {p1}), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_non_published_400(self) -> None:
        from cyo_adventure.api.assignments import assign_storybook
        from cyo_adventure.core.exceptions import BusinessLogicError

        fam = uuid.uuid4()
        p1 = uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam, status="draft"))
        body = AssignmentCreateBody(profile_ids=[str(p1)])
        with pytest.raises(
            BusinessLogicError, match=r"only a published story can be assigned"
        ):
            await assign_storybook("s1", body, _ctx(_guardian(fam, {p1}), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_profile_outside_family_403(self) -> None:
        from cyo_adventure.api.assignments import assign_storybook
        from cyo_adventure.core.exceptions import AuthorizationError

        fam = uuid.uuid4()
        mine, foreign = uuid.uuid4(), uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam))
        body = AssignmentCreateBody(profile_ids=[str(mine), str(foreign)])
        with pytest.raises(
            AuthorizationError, match=r"profile is not accessible to this principal"
        ):
            await assign_storybook("s1", body, _ctx(_guardian(fam, {mine}), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_uuid_422(self) -> None:
        from cyo_adventure.api.assignments import assign_storybook
        from cyo_adventure.core.exceptions import ValidationError

        fam = uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam))
        body = AssignmentCreateBody(profile_ids=["not-a-uuid"])
        with pytest.raises(ValidationError, match=r"profile_ids must be a UUID"):
            await assign_storybook("s1", body, _ctx(_guardian(fam, set()), session))


class TestListAssignments:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_guardian_lists_sorted(self) -> None:
        from cyo_adventure.api.assignments import list_assignments

        fam = uuid.uuid4()
        p1, p2 = uuid.uuid4(), uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam), assigned=[p2, p1])
        view = await list_assignments("s1", _ctx(_guardian(fam, {p1, p2}), session))
        assert view.profile_ids == sorted([str(p1), str(p2)])

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_token_forbidden(self) -> None:
        from cyo_adventure.api.assignments import list_assignments
        from cyo_adventure.core.exceptions import AuthorizationError

        fam = uuid.uuid4()
        p1 = uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam))
        with pytest.raises(
            AuthorizationError, match=r"only a guardian may manage assignments"
        ):
            await list_assignments("s1", _ctx(_child(fam, p1), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_admin_token_forbidden(self) -> None:
        """List is guardian-only too; an admin token is rejected."""
        from cyo_adventure.api.assignments import list_assignments
        from cyo_adventure.core.exceptions import AuthorizationError

        fam = uuid.uuid4()
        session = _FakeSession(book=_book("s1", fam))
        with pytest.raises(
            AuthorizationError, match=r"only a guardian may manage assignments"
        ):
            await list_assignments("s1", _ctx(_admin(fam, set()), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cross_family_existing_storybook_403(self) -> None:
        """An EXISTING book in another family is 403, per the ratings.py convention."""
        from cyo_adventure.api.assignments import list_assignments
        from cyo_adventure.core.exceptions import AuthorizationError

        fam, other = uuid.uuid4(), uuid.uuid4()
        session = _FakeSession(book=_book("s1", other))
        with pytest.raises(
            AuthorizationError, match=r"resource belongs to another family"
        ):
            await list_assignments("s1", _ctx(_guardian(fam, set()), session))


class TestContentSummary:
    @staticmethod
    def _pub_book(storybook_id: str, family_id: uuid.UUID) -> object:
        from cyo_adventure.db.models import Storybook

        b = Storybook(id=storybook_id, family_id=family_id)
        b.status = "published"
        b.current_published_version = 1
        return b

    @staticmethod
    def _version_row(storybook_id: str, *, approved: bool = True) -> object:
        from cyo_adventure.db.models import StorybookVersion

        return StorybookVersion(
            storybook_id=storybook_id,
            version=1,
            blob={"id": storybook_id, "nodes": [{"id": "n1", "body": "Prose."}]},
            approved_by=uuid.uuid4() if approved else None,
            moderation_report={
                "findings": [
                    {
                        "stage": 3,
                        "source": "llm_coherence",
                        "category": "coherence",
                        "node_id": None,
                        "verdict": "advisory",
                        "score": None,
                        "message": "slightly disjoint",
                    }
                ],
                "summary": {
                    "count": 1,
                    "hard_block": False,
                    "soft_flag": False,
                    "repaired": False,
                    "reviewer_independent": True,
                },
            },
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_guardian_gets_summary(self) -> None:
        from cyo_adventure.api.assignments import get_content_summary

        fam = uuid.uuid4()
        session = _FakeSession(
            book=self._pub_book("s1", fam), version=self._version_row("s1")
        )
        view = await get_content_summary("s1", _ctx(_guardian(fam, set()), session))
        assert view.storybook_id == "s1"
        assert view.screened is True
        # The lone finding is a story-level "coherence" advisory, below the
        # default (FLAG) surfacing threshold, so it is filtered out here.
        assert view.findings == []
        assert view.flagged_count == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_is_forbidden(self) -> None:
        from cyo_adventure.api.assignments import get_content_summary

        fam = uuid.uuid4()
        session = _FakeSession(
            book=self._pub_book("s1", fam), version=self._version_row("s1")
        )
        with pytest.raises(
            AuthorizationError,
            match=r"only a guardian or admin may read a content summary",
        ):
            await get_content_summary("s1", _ctx(_child(fam, uuid.uuid4()), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cross_family_guardian_is_forbidden(self) -> None:
        from cyo_adventure.api.assignments import get_content_summary

        owner_fam = uuid.uuid4()
        other_fam = uuid.uuid4()
        session = _FakeSession(
            book=self._pub_book("s1", owner_fam), version=self._version_row("s1")
        )
        with pytest.raises(
            AuthorizationError, match=r"resource belongs to another family"
        ):
            await get_content_summary("s1", _ctx(_guardian(other_fam, set()), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_admin_reads_cross_family(self) -> None:
        from cyo_adventure.api.assignments import get_content_summary

        owner_fam = uuid.uuid4()
        admin_fam = uuid.uuid4()
        session = _FakeSession(
            book=self._pub_book("s1", owner_fam), version=self._version_row("s1")
        )
        view = await get_content_summary("s1", _ctx(_admin(admin_fam, set()), session))
        assert view.storybook_id == "s1"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_story_is_404(self) -> None:
        from cyo_adventure.api.assignments import get_content_summary

        fam = uuid.uuid4()
        session = _FakeSession(book=None)
        with pytest.raises(ResourceNotFoundError, match=r"storybook 's1' not found"):
            await get_content_summary("s1", _ctx(_guardian(fam, set()), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unpublished_story_is_404(self) -> None:
        from cyo_adventure.api.assignments import get_content_summary

        fam = uuid.uuid4()
        draft = _book("s1", fam, status="in_review")
        session = _FakeSession(book=draft)
        with pytest.raises(ResourceNotFoundError, match=r"storybook 's1' not found"):
            await get_content_summary("s1", _ctx(_guardian(fam, set()), session))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unapproved_version_is_404(self) -> None:
        """Defense-in-depth: published status with an unapproved version row
        (approved_by is None) is 404, not a summary leak, even though the sole
        publish path is expected to never produce this state."""
        from cyo_adventure.api.assignments import get_content_summary

        fam = uuid.uuid4()
        session = _FakeSession(
            book=self._pub_book("s1", fam),
            version=self._version_row("s1", approved=False),
        )
        with pytest.raises(
            ResourceNotFoundError, match=r"storybook 's1' has no published version"
        ):
            await get_content_summary("s1", _ctx(_guardian(fam, set()), session))
