---
schema_type: planning
title: "WS-B PR 2: Guardian and Admin Request Creation Implementation Plan"
description: "Task-by-task implementation plan for WS-B PR 2: the authored (pre-approved) create
  endpoint for guardians and admins, the admin families listing, the nullable profile_id view,
  and the guardian/admin request-a-story forms."
tags:
  - planning
  - architecture
  - story-requests
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an implementer with zero session context everything needed to build WS-B PR 2
  task by task against the approved spec."
component: Strategy
source: "docs/planning/ws-b-request-lifecycle-plan.md (spec); codebase discovery 2026-07-08 on
  feat/ws-b-guardian-admin-create at 6b4b0b1 (PR 1 head)."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Let guardians and admins create story requests directly: a new authored-create endpoint that
screens the text, creates the row in `approved` status with the caller's `initiator_role`, and
builds the Concept immediately (skipping the redundant guardian approval); an admin-only
families listing to power the admin form's required family selector; `StoryRequestView.profile_id`
widened to nullable; and a shared "Request a story" form with a guardian variant (optional child
selector) and an admin variant (required family selector).

## Architecture

No migration: PR 1 already added `initiator_role`/`age_band`/`length`/`narrative_style` and made
`profile_id` nullable. This PR is code-only. Backend: a shared `_build_concept` helper is
extracted from `approve_story_request` (behavior-preserving refactor), then reused by a new
`create_authored_request` service function; one new endpoint
`POST /api/v1/story-requests/authored` (gated guardian|admin) and one new admin-only
`GET /api/v1/admin/families`. Frontend: one `RequestStoryForm` component with a `mode` prop,
embedded on `RequestsPage` (guardian) and `ConsolePage` (admin, the one-door admin console area).
The generated client is regenerated from an in-process schema dump.

## Tech stack

FastAPI + Pydantic v2, async SQLAlchemy 2.x, pytest (testcontainers Postgres for integration),
React 19 + Vitest + Playwright, `@hey-api/openapi-ts` client generation.

## Conventions that bind every task

- Branch: `feat/ws-b-guardian-admin-create` (worktree `.worktrees/ws-b-pr2`), based on PR 1's
  `feat/ws-b-request-lifecycle` at 6b4b0b1. Work on it directly.
- Signed conventional commits (`git commit -S`); stage only the files you changed; never
  `git add -A`. No em-dash characters anywhere (pre-commit hook enforces).
- Run `uv run ruff format . && uv run ruff check .` and `uv run basedpyright src/` before each
  backend commit; `pre-commit run --files <changed files>` must pass.
- New/changed functions touching DB or auth need RAD markers (`#CRITICAL`/`#ASSUME`/`#EDGE` +
  `#VERIFY`).
- Enum string literals (binding, verbatim): `AgeBand` is
  `'3-5', '5-8', '8-11', '10-13', '13-16', '16+'`
  (`src/cyo_adventure/storybook/models.py:32`); `Length` is `'short', 'medium', 'long'` (`:126`);
  `NarrativeStyle` is `'prose', 'gamebook'` (`:140`); `initiator_role` is
  `'child', 'guardian', 'admin'`.
- Ratified decisions (do not re-litigate): B3 admin-initiated requests REQUIRE a family
  (`family_id` stays NOT NULL); authored rows are created in `approved` status with the Concept
  built at creation; screening still runs and can block an authored request.
- Backend tests: `uv run pytest tests/unit -x -q` for unit,
  `uv run pytest tests/integration -x -q` for integration (testcontainers needs Docker).
  Frontend: run from `frontend/`: `npm run test:run`, `npm run lint`, `npm run typecheck`.

---

### Task 1: Schemas: authored body/views, family views, nullable profile_id

**Files:**
- Modify: `src/cyo_adventure/api/schemas.py` (approve body at ~384-405, `StoryRequestView` at
  ~420-441, created/approved views at ~450-467)
- Test: `tests/unit/test_schemas_story_request_approve.py` (extend; keep filename)

`StoryRequestApproveBody` currently holds the band/length/style trio plus the
`_style_allowed_for_band` validator. Hoist that trio into a shared base so the new authored
create body reuses it without duplicating the validator.

- [ ] **Step 1: Write failing unit tests** in
  `tests/unit/test_schemas_story_request_approve.py` (append; mirror the file's existing
  style):

```python
def test_authored_body_requires_band_length_and_text() -> None:
    with pytest.raises(PydanticValidationError):
        StoryRequestAuthoredCreateBody.model_validate({"request_text": "a turtle tale"})


def test_authored_body_rejects_gamebook_below_teen_bands() -> None:
    with pytest.raises(PydanticValidationError, match="gamebook"):
        StoryRequestAuthoredCreateBody.model_validate(
            {
                "request_text": "a turtle tale",
                "age_band": "5-8",
                "length": "short",
                "narrative_style": "gamebook",
            }
        )


def test_authored_body_accepts_optional_profile_and_family() -> None:
    body = StoryRequestAuthoredCreateBody.model_validate(
        {"request_text": "a turtle tale", "age_band": "13-16", "length": "medium"}
    )
    assert body.profile_id is None
    assert body.family_id is None
    assert body.narrative_style is NarrativeStyle.PROSE


def test_authored_body_forbids_unknown_fields() -> None:
    with pytest.raises(PydanticValidationError):
        StoryRequestAuthoredCreateBody.model_validate(
            {
                "request_text": "a turtle tale",
                "age_band": "5-8",
                "length": "short",
                "status": "approved",
            }
        )


def test_story_request_view_allows_null_profile_id() -> None:
    view = StoryRequestView.model_validate(
        {
            "id": "r1",
            "profile_id": None,
            "status": "approved",
            "request_text": "t",
            "moderation_flags": [],
            "created_at": "2026-07-08T00:00:00Z",
            "initiator_role": "guardian",
            "age_band": "5-8",
            "length": "short",
            "narrative_style": "prose",
        }
    )
    assert view.profile_id is None
```

Match the file's existing import names (it already imports the approve body and enums; extend
those imports). If the file aliases pydantic's `ValidationError` differently, follow it.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_schemas_story_request_approve.py -q`
Expected: FAIL with `ImportError`/`NameError` on `StoryRequestAuthoredCreateBody`.

- [ ] **Step 3: Implement in `src/cyo_adventure/api/schemas.py`**

Rename the field-holding part of `StoryRequestApproveBody` into a base and subclass both bodies
from it. Keep `StoryRequestApproveBody`'s name, fields, defaults, `extra="forbid"`, and
validator semantics byte-for-byte identical from the API contract's point of view (the OpenAPI
schema for approve must not change shape; a title-only change to the validator's error output is
not acceptable either, so move the validator unmodified):

```python
class StoryRequestSpecBody(BaseModel):
    """The band/length/style trio shared by approve and authored-create bodies.

    One base class because ADR-011's teen-only gamebook rule must hold at every
    entry point that sets ``narrative_style``; subclassing keeps the validator
    in one place (mirroring the ck_story_request_style_band CHECK at rest).
    """

    model_config = ConfigDict(extra="forbid")

    age_band: AgeBand
    length: Length
    narrative_style: NarrativeStyle = NarrativeStyle.PROSE

    @model_validator(mode="after")
    def _style_allowed_for_band(self) -> StoryRequestSpecBody:
        ...  # move the existing body of StoryRequestApproveBody's validator here, unchanged


class StoryRequestApproveBody(StoryRequestSpecBody):
    """(keep the existing docstring)"""


class StoryRequestAuthoredCreateBody(StoryRequestSpecBody):
    """A guardian's or admin's pre-approved story request (WS-B PR 2).

    ``profile_id`` is optional (an authored request need not target a child).
    ``family_id`` is admin-only: admins must name the target family (decision
    B3); guardians must omit it (their own family is server-derived).
    """

    request_text: RequestText
    profile_id: str | None = None
    family_id: str | None = None
```

`RequestText` is the constrained type the child create body already uses (same module); reuse
it verbatim so length caps and stripping stay identical.

Add the response and family views near the other story-request views:

```python
class StoryRequestAuthoredCreatedView(BaseModel):
    """The result of an authored create: approved with a concept, or blocked."""

    id: str
    status: StoryRequestStatus
    concept_id: str | None


class FamilyView(BaseModel):
    """A family as listed for the admin authored-request form."""

    id: str
    name: str


class FamilyListView(BaseModel):
    """All families, admin-only (powers the required family selector)."""

    families: list[FamilyView]
```

Change `StoryRequestView.profile_id` from `str` to `str | None` (docstring note: null for
authored requests with no target child; PR 1's empty-string placeholder is retired in this PR).

- [ ] **Step 4: Run the unit tests**

Run: `uv run pytest tests/unit/test_schemas_story_request_approve.py tests/unit -q`
Expected: new tests PASS; the full unit tier stays green (the approve-body tests prove the
refactor preserved the contract).

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff format src/cyo_adventure/api/schemas.py tests/unit/test_schemas_story_request_approve.py
uv run ruff check . && uv run basedpyright src/
git add src/cyo_adventure/api/schemas.py tests/unit/test_schemas_story_request_approve.py
git commit -S -m "feat(schemas): authored-create body/views, family views, nullable profile_id (WS-B PR2)"
```

---

### Task 2: Service layer: extract `_build_concept`, add `create_authored_request` (depends-on: Task1 [output])

**Files:**
- Modify: `src/cyo_adventure/story_requests/service.py` (approve at 89-169)
- Test: existing suites prove the refactor; new behavior is covered by Task 3's integration
  tests (service needs a real session; do not build a mock-session unit test for it)

- [ ] **Step 1: Extract the concept-building tail of `approve_story_request`**

Everything in `approve_story_request` after the confirmation stamp (from `brief =
brief_from_request(request, profile)` through the `return str(concept.id)`) moves unchanged into:

```python
async def _build_concept(
    session: AsyncSession,
    principal: Principal,
    request: StoryRequest,
    profile: ChildProfile | None,
) -> str:
    """Build the brief, run the PII backstop, persist the Concept, approve.

    Shared tail of guardian approval and authored creation: both end with the
    request ``approved``, ``reviewed_by`` stamped, and a Concept linked.
    """
```

Move the existing `#CRITICAL: security` PII-backstop RAD block along with the code it annotates.
`approve_story_request` keeps its signature, its `ensure_pending` guard, its profile fetch, its
concurrency RAD block, and the confirmation stamp, then ends with
`return await _build_concept(session, principal, request, profile)`.

- [ ] **Step 2: Prove the refactor is behavior-preserving**

Run: `uv run pytest tests/unit/test_story_requests.py tests/integration/test_story_requests_api.py -q`
Expected: PASS with zero test edits.

- [ ] **Step 3: Add `create_authored_request`** to the same module:

```python
async def create_authored_request(
    session: AsyncSession,
    principal: Principal,
    *,
    family_id: uuid.UUID,
    profile: ChildProfile | None,
    request_text: str,
    confirmation: ApprovalConfirmation,
    screening: ScreeningResult,
) -> tuple[StoryRequest, str | None]:
    """Create a guardian- or admin-initiated request, pre-approved (WS-B PR 2).

    The caller (the endpoint) has already authorized the principal, resolved
    the target family, validated the optional profile, and screened the text.
    A blocked screening persists a ``blocked`` row with no concept; otherwise
    the row is approved and its Concept built in the same transaction.

    Args:
        session: The request session (caller owns the transaction).
        principal: The authoring guardian or admin.
        family_id: The resolved target family (the principal's own family for
            guardians; the admin-chosen family for admins, decision B3).
        profile: The validated target child profile, or None.
        request_text: The already-screened request text.
        confirmation: The author's band/length/style, stamped at creation.
        screening: The screening outcome for ``request_text``.

    Returns:
        tuple[StoryRequest, str | None]: The persisted row and the new concept
            id (None when the request was blocked).

    Raises:
        ValidationError: If the built brief trips the PII backstop (-> 422).
    """
    # #CRITICAL: security: initiator_role is derived from the authenticated
    # principal, never from the request body, so a guardian cannot mint an
    # admin-attributed row (and vice versa).
    # #VERIFY: test_story_requests_authored.py asserts the persisted role per
    # token; api/schemas.py::StoryRequestAuthoredCreateBody forbids the field.
    request = StoryRequest(
        family_id=family_id,
        profile_id=profile.id if profile is not None else None,
        request_text=request_text,
        status="blocked" if screening.blocked else "pending",
        moderation_flags={
            "blocked": screening.blocked,
            "flags": [f.model_dump(mode="json") for f in screening.flags],
        },
        age_band=confirmation.age_band.value,
        length=confirmation.length.value,
        narrative_style=confirmation.narrative_style.value,
        initiator_role=principal.role.value,
    )
    session.add(request)
    await session.flush()
    if screening.blocked:
        return request, None
    concept_id = await _build_concept(session, principal, request, profile)
    return request, concept_id
```

Notes:
- The transient `"pending"` before `_build_concept` flips it to `"approved"` never leaves the
  transaction; do not add an `ensure_pending` call here (the row is brand new, no lock needed).
- Imports: `uuid` (plain import at top), and under `TYPE_CHECKING`:
  `from cyo_adventure.story_requests.screening import ScreeningResult`. If ruff flags the
  moderation-flags dict construction duplicated with the child create endpoint, leave it: two
  call sites is not a DRY violation worth a helper.
- Update the module docstring's first paragraph to mention that authored creation shares the
  concept-building path with approval.

- [ ] **Step 4: Lint, type-check, run suites, commit**

```bash
uv run ruff format src/cyo_adventure/story_requests/service.py
uv run ruff check . && uv run basedpyright src/
uv run pytest tests/unit/test_story_requests.py tests/integration/test_story_requests_api.py -q
git add src/cyo_adventure/story_requests/service.py
git commit -S -m "feat(story-requests): authored-create service sharing the approve concept path (WS-B PR2)"
```

---

### Task 3: API: authored create endpoint, admin families listing, nullable view mapping (depends-on: Task2 [output])

**Files:**
- Modify: `src/cyo_adventure/api/story_requests.py` (child create at 240-311, list mapping at
  226)
- Create: `src/cyo_adventure/api/families.py`
- Modify: `src/cyo_adventure/app.py` (router registration at 169-179)
- Create: `tests/integration/test_story_requests_authored.py`
- Modify (if grep hits): any test asserting the empty-string `profile_id` placeholder

- [ ] **Step 1: Write the failing integration tests** in
  `tests/integration/test_story_requests_authored.py`. Use the `Seed` fixture and `auth()`
  helper from `tests/integration/conftest.py` (fields include `guardian_token`, `admin_token`,
  `child_token`, `family_id`, `child_profile_id`, `other_child_profile_id`); mirror the
  imports/pytestmark of `tests/integration/test_story_request_flag_thresholds.py`:

```python
"""Authored (guardian/admin) story-request creation: WS-B PR 2 contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import Concept, StoryRequest
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

AUTHORED = "/api/v1/story-requests/authored"

BODY = {
    "request_text": "a story about a patient turtle",
    "age_band": "5-8",
    "length": "short",
}


async def test_guardian_authored_create_is_approved_with_concept(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    res = await client.post(AUTHORED, json=BODY, headers=auth(seed.guardian_token))
    assert res.status_code == 201
    payload = res.json()
    assert payload["status"] == "approved"
    assert payload["concept_id"]
    async with sessions() as session:
        row = await session.get(StoryRequest, __import__("uuid").UUID(payload["id"]))
        assert row is not None
        assert row.initiator_role == "guardian"
        assert row.age_band == "5-8"
        assert row.length == "short"
        assert row.narrative_style == "prose"
        assert row.profile_id is None
        assert row.reviewed_by is not None
        concept = await session.get(Concept, row.concept_id)
        assert concept is not None and concept.family_id == seed.family_id


async def test_guardian_authored_create_accepts_own_profile(
    client: AsyncClient, seed: Seed
) -> None:
    body = {**BODY, "profile_id": str(seed.child_profile_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 201


async def test_guardian_rejects_cross_family_profile(
    client: AsyncClient, seed: Seed
) -> None:
    body = {**BODY, "profile_id": str(seed.other_child_profile_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 403


async def test_guardian_must_omit_family_id(client: AsyncClient, seed: Seed) -> None:
    body = {**BODY, "family_id": str(seed.family_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 422


async def test_child_cannot_author(client: AsyncClient, seed: Seed) -> None:
    res = await client.post(AUTHORED, json=BODY, headers=auth(seed.child_token))
    assert res.status_code == 403


async def test_admin_requires_family_id(client: AsyncClient, seed: Seed) -> None:
    res = await client.post(AUTHORED, json=BODY, headers=auth(seed.admin_token))
    assert res.status_code == 422


async def test_admin_authored_create_targets_named_family(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    body = {**BODY, "family_id": str(seed.family_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.admin_token))
    assert res.status_code == 201
    async with sessions() as session:
        row = await session.get(
            StoryRequest, __import__("uuid").UUID(res.json()["id"])
        )
        assert row is not None
        assert row.initiator_role == "admin"
        assert row.family_id == seed.family_id


async def test_admin_unknown_family_is_404(client: AsyncClient, seed: Seed) -> None:
    body = {**BODY, "family_id": "00000000-0000-0000-0000-000000000000"}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.admin_token))
    assert res.status_code == 404


async def test_authored_missing_length_is_422(client: AsyncClient, seed: Seed) -> None:
    res = await client.post(
        AUTHORED,
        json={"request_text": "a turtle tale", "age_band": "5-8"},
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 422


async def test_authored_gamebook_below_teen_band_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    res = await client.post(
        AUTHORED,
        json={**BODY, "narrative_style": "gamebook"},
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 422


async def test_blocked_screening_persists_blocked_row_without_concept(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    # PII guard blocks text naming a family child; read the seeded child's
    # display name from the DB rather than hardcoding the fixture value.
    async with sessions() as session:
        from cyo_adventure.db.models import ChildProfile

        profile = await session.get(ChildProfile, seed.child_profile_id)
        assert profile is not None
        child_name = profile.display_name
    body = {**BODY, "request_text": f"a story starring {child_name} the brave"}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 201
    payload = res.json()
    assert payload["status"] == "blocked"
    assert payload["concept_id"] is None
    async with sessions() as session:
        row = await session.get(StoryRequest, __import__("uuid").UUID(payload["id"]))
        assert row is not None and row.concept_id is None


async def test_authored_request_lists_with_null_profile_id(
    client: AsyncClient, seed: Seed
) -> None:
    created = await client.post(AUTHORED, json=BODY, headers=auth(seed.guardian_token))
    request_id = created.json()["id"]
    res = await client.get(
        "/api/v1/story-requests", headers=auth(seed.guardian_token)
    )
    target = next(r for r in res.json()["requests"] if r["id"] == request_id)
    assert target["profile_id"] is None


async def test_admin_lists_families_guardian_forbidden(
    client: AsyncClient, seed: Seed
) -> None:
    res = await client.get("/api/v1/admin/families", headers=auth(seed.admin_token))
    assert res.status_code == 200
    ids = [f["id"] for f in res.json()["families"]]
    assert str(seed.family_id) in ids
    forbidden = await client.get(
        "/api/v1/admin/families", headers=auth(seed.guardian_token)
    )
    assert forbidden.status_code == 403
```

Replace the two `__import__("uuid")` shims with a proper `import uuid` at the top when writing
the real file (they are shown inline here only to keep the snippets self-contained). If the
existing suite fetches rows by id differently (check `test_story_requests_api.py` for the
prevailing lookup idiom, e.g. `select(StoryRequest).where(...)`), mirror that idiom instead of
`session.get`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_story_requests_authored.py -q`
Expected: FAIL with 404s (routes do not exist yet).

- [ ] **Step 3: Implement the authored endpoint** in `src/cyo_adventure/api/story_requests.py`,
  after `create_story_request`:

```python
@router.post("/story-requests/authored", status_code=201)
async def create_authored_story_request(
    body: StoryRequestAuthoredCreateBody, ctx: Context
) -> StoryRequestAuthoredCreatedView:
    """Create a pre-approved request as a guardian or admin (WS-B PR 2).

    The author sets band, length, and style at creation, so the guardian
    approval step is skipped: the row is created ``approved`` with its Concept
    built immediately, ready for the admin authoring-plan step. Screening
    still runs; a blocked outcome persists a ``blocked`` row with no concept.

    Args:
        body: The request text, band/length/style, optional profile, and
            (admin-only) target family.
        ctx: The request context (principal and session).

    Returns:
        StoryRequestAuthoredCreatedView: Id, post-screening status, concept id.

    Raises:
        AuthorizationError: If the caller is a child, or the profile does not
            belong to the target family (-> 403).
        ResourceNotFoundError: If the named family or profile is missing (-> 404).
        ValidationError: If a guardian supplies ``family_id``, an admin omits
            it, or a UUID is malformed (-> 422).
    """
    # #CRITICAL: security: children cannot author pre-approved requests; the
    # authored path bypasses guardian review by design, so the role gate is the
    # only thing standing between a child token and an unreviewed concept.
    # #VERIFY: test_story_requests_authored.py::test_child_cannot_author.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = "guardian or admin role required"
        raise AuthorizationError(msg)

    # #CRITICAL: security: the target family comes from the principal for
    # guardians and from the body for admins (decision B3); a guardian naming
    # any family_id is rejected outright so cross-family authoring is
    # impossible even with a correct-looking id.
    # #VERIFY: test_guardian_must_omit_family_id, test_admin_requires_family_id.
    if ctx.principal.is_admin:
        if body.family_id is None:
            msg = "family_id is required for admin-initiated requests"
            raise ValidationError(msg, field="family_id", value=None)
        family_uuid = parse_uuid(body.family_id, "family_id")
        family = await ctx.session.get(Family, family_uuid)
        if family is None:
            msg = "family not found"
            raise ResourceNotFoundError(msg)
    else:
        if body.family_id is not None:
            msg = "family_id is server-derived for guardians"
            raise ValidationError(msg, field="family_id", value=body.family_id)
        family_uuid = ctx.principal.family_id

    profile: ChildProfile | None = None
    if body.profile_id is not None:
        profile_uuid = parse_uuid(body.profile_id, "profile_id")
        profile = await ctx.session.get(ChildProfile, profile_uuid)
        if profile is None:
            msg = "profile not found"
            raise ResourceNotFoundError(msg)
        # #CRITICAL: security: profile must belong to the target family; for
        # guardians family_uuid is their own family so this is equivalent to
        # authorize_profile, and it also covers the admin-named family (IDOR).
        # #VERIFY: test_guardian_rejects_cross_family_profile.
        if profile.family_id != family_uuid:
            msg = "profile does not belong to the target family"
            raise AuthorizationError(msg)

    child_names = await _family_child_names(ctx, family_uuid)
    result = await screen_request_text(
        body.request_text,
        child_names=child_names,
        openai_key=settings.openai_api_key,
        perspective_key=settings.perspective_api_key,
    )
    request, concept_id = await service.create_authored_request(
        ctx.session,
        ctx.principal,
        family_id=family_uuid,
        profile=profile,
        request_text=body.request_text,
        confirmation=service.ApprovalConfirmation(
            age_band=body.age_band,
            length=body.length,
            narrative_style=body.narrative_style,
        ),
        screening=result,
    )
    return StoryRequestAuthoredCreatedView(
        id=str(request.id),
        status=cast("StoryRequestStatus", request.status),
        concept_id=concept_id,
    )
```

Add the needed imports (`Family` from `cyo_adventure.db.models`, the two new schema names); the
module already imports `parse_uuid`, `AuthorizationError`, `ResourceNotFoundError`,
`ValidationError`, `ChildProfile`, `screen_request_text`, `settings`, `service`, and `cast`.
Route-ordering note: FastAPI matches `/story-requests/authored` before
`/story-requests/{request_id}/...` because those paths have an extra segment, but keep the new
route adjacent to `create_story_request` for readability. Verify no ordering clash with a quick
`uv run pytest tests/integration/test_story_requests_api.py -q` after wiring.

- [ ] **Step 4: Nullable list mapping.** In the same file, change line 226 from

```python
        profile_id=str(request.profile_id) if request.profile_id is not None else "",
```

to

```python
        profile_id=str(request.profile_id) if request.profile_id is not None else None,
```

and delete any comment that described the empty-string placeholder. Then
`grep -rn 'profile_id.*""' tests/ frontend/src --include='*.py' --include='*.ts' --include='*.tsx'`
and update anything asserting the old placeholder.

- [ ] **Step 5: Admin families endpoint.** Create `src/cyo_adventure/api/families.py`:

```python
"""Admin-only family listing (WS-B PR 2).

Powers the required family selector on the admin authored-request form
(decision B3: admin-initiated requests must name a family).
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import FamilyListView, FamilyView
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import Family

router = APIRouter(prefix="/api/v1", tags=["families"])


@router.get("/admin/families")
async def list_families(ctx: Context) -> FamilyListView:
    """List every family, for the admin authored-request form.

    Args:
        ctx: The request context (principal and session).

    Returns:
        FamilyListView: All families ordered by name.

    Raises:
        AuthorizationError: If the caller is not an admin (-> 403).
    """
    # #CRITICAL: security: the full family roster is cross-tenant data; only
    # the admin role (the global operator) may enumerate it.
    # #VERIFY: test_admin_lists_families_guardian_forbidden asserts 403 for a
    # guardian token.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg)
    rows = await ctx.session.scalars(
        select(Family).order_by(Family.name.asc(), Family.id.asc())
    )
    return FamilyListView(
        families=[FamilyView(id=str(f.id), name=f.name) for f in rows.all()]
    )
```

Register it in `src/cyo_adventure/app.py`: add `families` to the existing
`from cyo_adventure.api import ...` import and `app.include_router(families.router)` beside the
other routers (after `profiles.router` at line 173).

- [ ] **Step 6: Run the new tests plus neighbors**

Run: `uv run pytest tests/integration/test_story_requests_authored.py tests/integration/test_story_requests_api.py tests/integration/test_story_request_flag_thresholds.py tests/integration/test_authorization.py -q`
Expected: PASS.

- [ ] **Step 7: Lint, type-check, full backend suite, commit**

```bash
uv run ruff format src/cyo_adventure/api/story_requests.py src/cyo_adventure/api/families.py src/cyo_adventure/app.py tests/integration/test_story_requests_authored.py
uv run ruff check . && uv run basedpyright src/
uv run pytest -q
git add src/cyo_adventure/api/story_requests.py src/cyo_adventure/api/families.py src/cyo_adventure/app.py tests/integration/test_story_requests_authored.py
# plus any test files updated for the placeholder removal
git commit -S -m "feat(api): authored story-request create + admin families listing (WS-B PR2)"
```

---

### Task 4: Regenerate the OpenAPI client (depends-on: Task3 [output])

**Files:**
- Modify: `frontend/src/client/*` (generated; do not hand-edit)
- Modify (if typecheck breaks): frontend files consuming `StoryRequestView.profile_id`

- [ ] **Step 1: Dump the schema in-process and regenerate** (same path the CI drift gate uses;
  run from the worktree root):

```bash
schema="$(mktemp --suffix=.json)"
uv run python -c "import json; from cyo_adventure.app import app; print(json.dumps(app.openapi()))" > "$schema"
cd frontend && OPENAPI_INPUT="$schema" npm run generate-client
```

Expected: `frontend/src/client/` diff includes the new
`createAuthoredStoryRequest...` and `listFamilies...` SDK functions, the new body/view types,
and `profile_id: string | null` on the story-request view type.

- [ ] **Step 2: Type-check and fix fallout**

Run: `cd frontend && npm run typecheck && npm run lint && npm run test:run`
Expected: any compile error is from `profile_id` becoming nullable; fix consuming code by
handling `null` explicitly (no non-null assertions).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/client
# plus any consuming files fixed for nullability
git commit -S -m "feat(client): regenerate for authored create, families, nullable profile_id (WS-B PR2)"
```

---

### Task 5: RequestStoryForm: guardian and admin variants (depends-on: Task4 [output])

**Files:**
- Create: `frontend/src/guardian/RequestStoryForm.tsx`
- Create: `frontend/src/guardian/authoredRequestApi.ts`
- Create: `frontend/src/guardian/RequestStoryForm.test.tsx`
- Modify: `frontend/src/guardian/RequestsPage.tsx` (embed guardian variant)
- Modify: `frontend/src/guardian/ConsolePage.tsx` (embed admin variant)
- Modify: `frontend/src/guardian/guardian.css` (form styles, following existing class naming)

Follow the established page/API-wrapper conventions: a `make...Api(api: AxiosInstance)` factory
typed against `../client/types.gen` (mirror `storyRequestQueueApi.ts`), components using
`useApi()` + `classifyApiError`, and the PR-1 confirm-strip select patterns in
`RequestsPage.tsx` (band/length/style options, teen-band-only style select). Reuse the existing
teen-band constant/helper from `RequestsPage.tsx`; if it is module-private, export it or move it
to a small shared module rather than duplicating the band list.

- [ ] **Step 1: Write the API wrapper** `authoredRequestApi.ts`: factory exposing

```typescript
createAuthored(body: StoryRequestAuthoredCreateBody): Promise<StoryRequestAuthoredCreatedView>
listProfiles(): Promise<ProfileView[]>          // GET /v1/profiles -> .profiles
listFamilies(): Promise<FamilyView[]>           // GET /v1/admin/families -> .families
```

(paths relative to the axios instance's base, matching how `storyRequestQueueApi.ts` addresses
`/v1/story-requests`). Add `authoredRequestApi.test.ts` only if the sibling wrappers have tests
(they do: mirror `storyRequestQueueApi.test.ts`).

- [ ] **Step 2: Write failing Vitest tests** in `RequestStoryForm.test.tsx` (mirror
  `RequestsPage.test.tsx`'s render/mock setup). Cases:

1. Guardian mode renders a child select (populated from `listProfiles`, includes a "No specific
   child" option) and no family select.
2. Choosing a child prefills the band select from that profile's `age_band`; the band stays
   editable.
3. Style select renders only when the chosen band is `13-16` or `16+`; switching to a younger
   band resets style to `prose`.
4. Submit is disabled until band, length, and non-empty text are set; submitting posts the
   expected body (assert `profile_id`/`family_id` presence/absence per mode) and shows the
   success notice on `status: "approved"`.
5. A `status: "blocked"` response shows the blocked notice instead of the success notice.
6. Admin mode renders a required family select (populated from `listFamilies`) and no child
   select; submit stays disabled until a family is chosen.

- [ ] **Step 3: Run to verify failure**

Run: `cd frontend && npm run test:run -- RequestStoryForm`
Expected: FAIL (component does not exist).

- [ ] **Step 4: Implement `RequestStoryForm.tsx`**

- Props: `{ mode: 'guardian' | 'admin' }`.
- On mount: guardian mode loads profiles, admin mode loads families (via the wrapper); loading
  and error states follow the `LoadState` union style used by `RequestsPage.tsx`.
- Controlled fields: text area (label "What should the story be about?"), optional child select
  (guardian), required family select (admin), band select (all six bands), length select
  (`short/medium/long`), style select (teen bands only, default `prose`).
- Submit: guardian sends `{request_text, age_band, length, narrative_style, profile_id?}` (omit
  `family_id` entirely); admin sends the same plus required `family_id` and omits `profile_id`
  (no cross-family profile listing exists yet; the backend accepts admin `profile_id`, the form
  simply does not offer it in this PR).
- Success: clear the form, show "Request approved and sent for authoring." Blocked: show the
  blocked notice (match the tone of existing kid-flow blocked messaging). Failure:
  `classifyApiError` mapping like the neighbors.
- Keep the double-submit guard pattern (disable while in flight) used by `RequestsPage.tsx`.
- Accessibility: label every control with `htmlFor`/`id`, and tie notices to the form with
  `role="status"` (success) / `role="alert"` (blocked, error), matching existing usage.

- [ ] **Step 5: Embed the variants.** `RequestsPage.tsx`: render
  `<RequestStoryForm mode="guardian" />` above the pending queue only when the authenticated
  role is `guardian` (role comes from `AuthContext`, as the page already resolves it).
  `ConsolePage.tsx`: render `<RequestStoryForm mode="admin" />` in the console layout only when
  the role is `admin`. Update `RequestsPage.test.tsx`/`ConsolePage.test.tsx` mocks so existing
  cases still pass (the form's mount fetches must be mocked or the form gated out).

- [ ] **Step 6: Run the frontend gates**

Run: `cd frontend && npm run test:run && npm run lint && npm run typecheck`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/guardian/RequestStoryForm.tsx frontend/src/guardian/RequestStoryForm.test.tsx frontend/src/guardian/authoredRequestApi.ts frontend/src/guardian/RequestsPage.tsx frontend/src/guardian/ConsolePage.tsx frontend/src/guardian/guardian.css
# plus authoredRequestApi.test.ts and any test files updated in step 5
git commit -S -m "feat(guardian): request-a-story form with guardian and admin variants (WS-B PR2)"
```

---

### Task 6: e2e coverage, both tiers (depends-on: Task5 [output])

**Files:**
- Create: `frontend/e2e/story-requests-authored.spec.ts`
- Create: `frontend/e2e-real/authored-request.spec.ts`

- [ ] **Step 1: Mocked-tier spec.** Mirror `frontend/e2e/story-requests.spec.ts` (init-script
  auth seeding, `page.route` interception). Cases:

1. Guardian flow: mock `/api/v1/me` (role guardian), `/api/v1/profiles`, the pending list, and
   `/api/v1/story-requests/authored`; fill the form choosing a child, assert the intercepted
   POST body carries `profile_id`, the child's band, the chosen length, and NO `family_id`;
   assert the success notice.
2. Admin flow: mock `/api/v1/me` (role admin), `/api/v1/admin/families`, the pending list, and
   the authored endpoint; assert the POST body carries `family_id` and no `profile_id`; assert
   the form does not render a child selector.
3. Blocked flow: authored endpoint fulfills `{id, status: 'blocked', concept_id: null}`; assert
   the blocked notice renders.

- [ ] **Step 2: Run the mocked tier**

Run: `cd frontend && npx playwright test e2e/story-requests-authored.spec.ts`
Expected: PASS (use the repo's configured runner invocation if it differs; check
`frontend/package.json` scripts and mirror how CI runs the `e2e/` tier).

- [ ] **Step 3: Real-tier spec.** Add `frontend/e2e-real/authored-request.spec.ts` following
  `approval-flow.spec.ts`'s use of `real-stack.ts` helpers: guardian logs in, submits an
  authored request via the form, and the request appears with approved status. Do NOT invent new
  seeding helpers; if the real-stack helpers lack what the flow needs, keep the spec minimal
  (submit + success notice). This tier is local-only and will not run in CI; still keep it
  compiling under `npm run typecheck`.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/story-requests-authored.spec.ts frontend/e2e-real/authored-request.spec.ts
git commit -S -m "test(e2e): authored request flows, mocked and real tiers (WS-B PR2)"
```

---

### Task 7: CHANGELOG, gates, PR (depends-on: Task6 [completion])

- [ ] **Step 1: CHANGELOG.** Add an Unreleased entry describing guardian/admin request
  creation, the admin families listing, and the nullable `profile_id` view change (mirror the
  PR-1 entry's format).

- [ ] **Step 2: Full gate sweep**

Run, from the worktree root:

```bash
uv run pytest --cov=src --cov-fail-under=80 -q
uv run ruff check . && uv run basedpyright src/ && uv run bandit -r src -q
cd frontend && npm run lint && npm run typecheck && npm run test:run && cd ..
pre-commit run --all-files
```

Expected: all green; bandit severity-High count 0 (its "High" confidence histogram line is not
severity).

- [ ] **Step 3: Base-branch check, push, PR.**

Run: `gh pr view 164 --json state,mergedAt --jq '{state, mergedAt}'`

- If PR #164 is MERGED: rebase this branch onto `origin/main`
  (`git fetch origin && git rebase origin/main`), rerun the step-2 gates, and open the PR with
  base `main`.
- If PR #164 is still OPEN: open the PR stacked with base `feat/ws-b-request-lifecycle` and note
  in the PR body that it retargets to `main` after #164 merges.

PR title: `feat(story-requests): guardian and admin request creation (WS-B PR 2)`. Body: link
the spec and this plan; state that authored rows skip guardian approval by design (role-gated,
screening still runs, child tokens 403); call out the `profile_id` view widening as the one
consumer-visible contract change (frontend updated in the same PR); disclose the real-tier e2e
spec's execution status. Do NOT merge; merging is the owner's action.

---

## Self-review record

- Spec clause coverage: guardian create (optional profile, band/length/style at creation,
  approved status, straight to admin queue) -> Tasks 2-3; admin create (family required, B3) ->
  Tasks 1-3; screening still runs / can block -> Task 2 service + Task 3 blocked test; guardian
  form with optional child selector + band prefill -> Task 5; admin variant on the console area
  with required family selector -> Task 5; client regen via in-process dump -> Task 4;
  authorization matrix + contract 422s -> Task 3 tests; e2e both tiers -> Task 6;
  `StoryRequestView.profile_id` widening (PR-1 handoff) -> Tasks 1, 3, 4.
- Deliberate scope decisions: the admin form offers no child selector (no cross-family profile
  listing endpoint exists; the API accepts admin `profile_id` for forward-compatibility). The
  per-profile pending cap does not apply to authored requests (they never rest in `pending`).
  `GET /admin/families` is added because the admin family selector otherwise has no data source;
  it returns id+name only.
- Placeholder scan: clean; the two "mirror the sibling file" instructions name the exact sibling
  and what to copy.
- Type consistency: `StoryRequestSpecBody`/`StoryRequestAuthoredCreateBody`/
  `StoryRequestAuthoredCreatedView`/`FamilyView`/`FamilyListView` names match across Tasks 1, 3,
  4, 5. `create_authored_request` signature matches its Task 3 call site.
- Environment: backend commands assume the worktree venv (`uv run` handles it); frontend
  commands run from `frontend/`; the schema dump avoids needing a running backend.
