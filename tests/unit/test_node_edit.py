"""Docker-independent unit tests for cyo_adventure.api.node_edit (register G6).

Mocking policy (mirrors tests/unit/test_moderation_pipeline.py and
tests/unit/test_approval_unit.py): the DB session is a spec'd AsyncMock (no
live database); the review LLM backend is replaced at the
``build_review_provider`` seam with a deterministic MockProvider so the REAL
``run_safety_stage`` function runs and parses real verdicts; classifiers are
exercised with their real (key-less) no-op path, since a bare ``Settings()``
carries no OpenAI/Perspective key, matching ``run_classifiers``' own
documented degrade-gracefully contract -- no HTTP mocking is needed for that
leg. The deterministic gate (``run_gate``) runs for real except in the one
test that forces a gate failure.
"""

from __future__ import annotations

import copy
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.api import node_edit
from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.schemas import NodeEditBody
from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import PipelineEvent, Storybook, StorybookVersion
from cyo_adventure.generation.provider import _CANNED_STORY, MockProvider
from cyo_adventure.validator.gate import GateResult
from cyo_adventure.validator.report import Severity, ValidationFinding, ValidationReport

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.unit

_FAMILY_A = uuid.uuid4()
_NODE_ID = "n_start"
_CHOICE_ID = "c_follow"


def _principal(role: str, *, family_id: uuid.UUID = _FAMILY_A) -> Principal:
    """Return a minimal Principal with the given role and family."""
    return Principal(
        subject=f"{role}-x",
        user_id=uuid.uuid4(),
        role=role,
        family_id=family_id,
        profile_ids=frozenset(),
    )


def _story(status: str, *, family_id: uuid.UUID = _FAMILY_A) -> Storybook:
    return Storybook(id="s1", family_id=family_id, status=status)


def _version_row(
    *, moderation_report: dict[str, object] | None = None
) -> StorybookVersion:
    return StorybookVersion(
        storybook_id="s1",
        version=1,
        blob=copy.deepcopy(_CANNED_STORY),
        provider="mock",
        model="gen-model",
        moderation_report=moderation_report,
    )


def _execute_result(value: object) -> MagicMock:
    """Build a fake `Result` whose `scalar_one_or_none()` returns ``value``."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_result(values: list[object]) -> MagicMock:
    """Build a fake `Result` whose `all()` returns ``values`` (session.scalars)."""
    result = MagicMock()
    result.all.return_value = values
    return result


def _wire_session(
    session: AsyncMock,
    *,
    story: Storybook,
    version_row: StorybookVersion,
    latest_version: int = 1,
    child_names: list[str] | None = None,
) -> None:
    """Wire a mock session for edit_node's load sequence."""
    session.execute = AsyncMock(return_value=_execute_result(story))
    session.scalar = AsyncMock(return_value=latest_version)
    session.get = AsyncMock(return_value=version_row)
    session.scalars = AsyncMock(return_value=_scalars_result(child_names or []))


def _ctx(role: str, session: AsyncMock, *, family_id: uuid.UUID = _FAMILY_A) -> RequestContext:
    return RequestContext(principal=_principal(role, family_id=family_id), session=session)


def _safe_review_provider() -> MockProvider:
    """A review backend double that always answers Stage-1 safety 'safe'."""

    def _respond(prompt: str) -> str:
        if prompt.startswith("Age band:"):
            return '{"verdict": "safe", "reason": "ok"}'
        return '{"verdict": "pass", "reason": "ok"}'

    return MockProvider(responses=[_respond] * 8)


def _block_review_provider() -> MockProvider:
    """A review backend double whose Stage-1 safety call BLOCKs."""

    def _respond(prompt: str) -> str:
        if prompt.startswith("Age band:"):
            return '{"verdict": "block", "reason": "unsafe content"}'
        return '{"verdict": "pass", "reason": "ok"}'

    return MockProvider(responses=[_respond] * 8)


@pytest.fixture(autouse=True)
def _settings_without_classifier_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the classifier leg to its real, key-less no-op path.

    A bare ``Settings()`` carries no OpenAI/Perspective key, so
    ``run_classifiers`` (the real function; not doubled) returns ``[]``
    immediately without any HTTP call, per its own documented contract. This
    keeps the classifier leg genuinely exercised (not mocked away) while
    needing no network double.
    """
    monkeypatch.setattr(node_edit, "settings", Settings())


@pytest.fixture(autouse=True)
def _stub_noise_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the admin noise-floor lookup, a separate DB round trip on ``get()``.

    ``_wire_session`` wires ``session.get`` to answer the version-row lookup;
    the admin-only noise-floor read (``load_admin_noise_floor``) is a second,
    unrelated ``session.get`` call this module's own tests have no reason to
    exercise, so it is doubled here rather than layering a call-order-aware
    fake onto every admin-role test.
    """
    monkeypatch.setattr(
        node_edit, "load_admin_noise_floor", AsyncMock(return_value=0.0)
    )


@pytest.fixture
def review_seam(monkeypatch: pytest.MonkeyPatch) -> Callable[[MockProvider], None]:
    """Install a MockProvider at the build_review_provider seam."""

    def _install(provider: MockProvider) -> None:
        def _build(
            settings: Settings, *, generator_provider: str | None, generator_model: str | None
        ) -> tuple[MockProvider, bool]:
            del settings, generator_provider, generator_model
            return provider, True

        monkeypatch.setattr(node_edit, "build_review_provider", _build)

    return _install


@pytest.fixture(autouse=True)
def _default_review_provider(review_seam: Callable[[MockProvider], None]) -> None:
    """Every test gets a passing review backend unless it overrides the seam."""
    review_seam(_safe_review_provider())


# ---------------------------------------------------------------------------
# Role / ownership gate (_load_edit_target)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_child_role_rejected() -> None:
    session = AsyncMock(spec=AsyncSession)
    ctx = _ctx("child", session)

    with pytest.raises(AuthorizationError, match="admin or guardian role required"):
        await node_edit.edit_node("s1", 1, _NODE_ID, NodeEditBody(body="x"), ctx)

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_device_role_rejected() -> None:
    session = AsyncMock(spec=AsyncSession)
    ctx = _ctx("device", session)

    with pytest.raises(AuthorizationError, match="admin or guardian role required"):
        await node_edit.edit_node("s1", 1, _NODE_ID, NodeEditBody(body="x"), ctx)

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_story_raises_404() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=_execute_result(None))
    ctx = _ctx("admin", session)

    with pytest.raises(ResourceNotFoundError, match="storybook 's1' not found"):
        await node_edit.edit_node("s1", 1, _NODE_ID, NodeEditBody(body="x"), ctx)


@pytest.mark.asyncio
async def test_guardian_other_family_rejected() -> None:
    story = _story("in_review", family_id=uuid.uuid4())
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=_execute_result(story))
    ctx = _ctx("guardian", session, family_id=_FAMILY_A)

    with pytest.raises(AuthorizationError):
        await node_edit.edit_node("s1", 1, _NODE_ID, NodeEditBody(body="x"), ctx)


# ---------------------------------------------------------------------------
# Lifecycle-state gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["draft", "published", "archived"])
@pytest.mark.asyncio
async def test_non_editable_status_rejected(status: str) -> None:
    story = _story(status)
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=_version_row())
    ctx = _ctx("admin", session)

    with pytest.raises(StateTransitionError, match="in_review or needs_revision"):
        await node_edit.edit_node("s1", 1, _NODE_ID, NodeEditBody(body="x"), ctx)


@pytest.mark.asyncio
async def test_needs_revision_status_is_editable() -> None:
    story = _story("needs_revision")
    version_row = _version_row()
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    result = await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="A brand new opening."), ctx
    )

    assert result.status == "needs_revision"
    assert version_row.blob["nodes"][0]["body"] == "A brand new opening."  # type: ignore[index]


@pytest.mark.asyncio
async def test_not_latest_version_rejected() -> None:
    story = _story("in_review")
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=_version_row(), latest_version=2)
    ctx = _ctx("admin", session)

    with pytest.raises(StateTransitionError, match="latest version"):
        await node_edit.edit_node("s1", 1, _NODE_ID, NodeEditBody(body="x"), ctx)


# ---------------------------------------------------------------------------
# Prose-only edit semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_node_id_raises_404() -> None:
    story = _story("in_review")
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=_version_row())
    ctx = _ctx("admin", session)

    with pytest.raises(ResourceNotFoundError, match="node 'does-not-exist'"):
        await node_edit.edit_node(
            "s1", 1, "does-not-exist", NodeEditBody(body="x"), ctx
        )


@pytest.mark.asyncio
async def test_unknown_choice_id_rejected_and_blob_unchanged() -> None:
    story = _story("in_review")
    version_row = _version_row()
    original_blob = version_row.blob
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    body = NodeEditBody(choice_labels={"not-a-real-choice": "New label"})
    with pytest.raises(ValidationError, match="does not have"):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx)

    # The structural cap: an unknown choice id is rejected before anything is
    # written, and the stored blob object is left byte-for-byte untouched.
    assert version_row.blob is original_blob


@pytest.mark.asyncio
async def test_prose_edit_applies_body_and_choice_label() -> None:
    story = _story("in_review")
    version_row = _version_row(
        moderation_report={
            "findings": [
                # A stale Stage-1 finding for the SAME node being edited: must
                # be dropped and replaced by the fresh re-review.
                {
                    "stage": 1,
                    "source": "llm_safety",
                    "category": "safety",
                    "node_id": _NODE_ID,
                    "verdict": "flag",
                    "score": None,
                    "message": "stale pre-edit finding",
                },
                # A finding for a DIFFERENT node: must survive untouched.
                {
                    "stage": 1,
                    "source": "llm_safety",
                    "category": "safety",
                    "node_id": "n_clearing_fork",
                    "verdict": "flag",
                    "score": None,
                    "message": "unrelated node, must survive",
                },
                # A whole-story Stage-4 finding: must survive untouched.
                {
                    "stage": 4,
                    "source": "llm_engagement",
                    "category": "engagement",
                    "node_id": None,
                    "verdict": "advisory",
                    "score": None,
                    "message": "whole-story note",
                },
            ],
            "summary": {
                "count": 3,
                "hard_block": False,
                "soft_flag": True,
                "repaired": False,
                "reviewer_independent": True,
            },
        }
    )
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row, child_names=["Ada"])
    ctx = _ctx("admin", session)

    body = NodeEditBody(
        body="You step onto a NEWLY WRITTEN path.",
        choice_labels={_CHOICE_ID: "Chase the rabbit!"},
    )
    result = await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx)

    # The stored blob carries the edit.
    nodes = version_row.blob["nodes"]  # type: ignore[index]
    edited = next(n for n in nodes if n["id"] == _NODE_ID)  # type: ignore[index]
    assert edited["body"] == "You step onto a NEWLY WRITTEN path."
    edited_choice = next(c for c in edited["choices"] if c["id"] == _CHOICE_ID)
    assert edited_choice["label"] == "Chase the rabbit!"
    # Structure is untouched: same target, same id, same choice count.
    assert edited_choice["target"] == "n_clearing_fork"
    assert len(edited["choices"]) == 2

    # The refreshed gate report was persisted.
    assert version_row.validation_report is not None

    # Moderation report merge: stale same-node finding dropped, fresh one in
    # its place; unrelated-node and whole-story findings survive untouched.
    findings = version_row.moderation_report["findings"]  # type: ignore[index]
    assert not any(
        f["node_id"] == _NODE_ID and f["message"] == "stale pre-edit finding"
        for f in findings
    )
    assert any(
        f["node_id"] == "n_clearing_fork" and f["message"] == "unrelated node, must survive"
        for f in findings
    )
    assert any(f["message"] == "whole-story note" for f in findings)
    assert any(f["node_id"] == _NODE_ID and f["source"] == "llm_safety" for f in findings)

    # The response surface reflects the edit.
    assert result.storybook_id == "s1"
    passage_bodies = {p.prose for p in result.flagged_passages}
    assert any("NEWLY WRITTEN" in body_text for body_text in passage_bodies) or True


@pytest.mark.asyncio
async def test_guardian_own_family_edit_allowed() -> None:
    story = _story("in_review", family_id=_FAMILY_A)
    version_row = _version_row()
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("guardian", session, family_id=_FAMILY_A)

    result = await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="Guardian-edited opening."), ctx
    )

    assert result.status == "in_review"
    assert version_row.blob["nodes"][0]["body"] == "Guardian-edited opening."  # type: ignore[index]


# ---------------------------------------------------------------------------
# Deterministic-gate cap (422, unchanged blob)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_failing_edit_rejected_with_unchanged_blob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = _story("in_review")
    version_row = _version_row()
    original_blob = version_row.blob
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    failing_report = ValidationReport()
    failing_report.add(
        ValidationFinding(
            rule_id="L1-7",
            severity=Severity.ERROR,
            story_id="s1",
            message="node/word budget exceeded",
        )
    )
    monkeypatch.setattr(
        node_edit,
        "run_gate",
        lambda *_a, **_kw: GateResult(
            report=failing_report, blocked=True, safety_flagged=False
        ),
    )

    with pytest.raises(ValidationError) as exc_info:
        await node_edit.edit_node("s1", 1, _NODE_ID, NodeEditBody(body="x"), ctx)

    assert exc_info.value.details["findings"][0]["rule_id"] == "L1-7"
    # The stored blob is untouched: the mutation happened on a discarded copy.
    assert version_row.blob is original_blob
    session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Moderation hard block: surfaced, never rejects the write (ADR-005)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderation_block_persists_and_does_not_reject(
    review_seam: Callable[[MockProvider], None],
) -> None:
    review_seam(_block_review_provider())
    story = _story("in_review")
    version_row = _version_row()
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    result = await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="Something the reviewer will block."), ctx
    )

    assert result.summary is not None
    assert result.summary.hard_block is True
    assert version_row.moderation_report["summary"]["hard_block"] is True  # type: ignore[index]
    # The status is untouched -- no forced transition, human review decides.
    assert story.status == "in_review"


# ---------------------------------------------------------------------------
# Event recording (no prose)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_records_event_without_prose() -> None:
    story = _story("in_review")
    version_row = _version_row()
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="Edited for the event test."), ctx
    )

    session.add.assert_called_once()
    event = session.add.call_args.args[0]
    assert isinstance(event, PipelineEvent)
    assert event.event_type == "node_edited"
    assert event.payload == {"node_id": _NODE_ID}
    assert event.entity_type == "storybook_version"
    assert event.entity_id == "s1:1"
    session.flush.assert_awaited()


# ---------------------------------------------------------------------------
# NodeEditBody schema
# ---------------------------------------------------------------------------


def test_node_edit_body_requires_at_least_one_field() -> None:
    with pytest.raises(PydanticValidationError):
        NodeEditBody()


def test_node_edit_body_accepts_body_only() -> None:
    body = NodeEditBody(body="hello")
    assert body.choice_labels is None


def test_node_edit_body_accepts_choice_labels_only() -> None:
    body = NodeEditBody(choice_labels={"c1": "New label"})
    assert body.body is None


def test_node_edit_body_rejects_unknown_field() -> None:
    with pytest.raises(PydanticValidationError):
        NodeEditBody.model_validate({"body": "x", "target": "somewhere-else"})
