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
from typing import TYPE_CHECKING, cast
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
from cyo_adventure.db.models import (
    GenerationJob,
    PipelineEvent,
    Storybook,
    StorybookVersion,
)
from cyo_adventure.generation.provider import _CANNED_STORY, MockProvider
from cyo_adventure.moderation import personalizable_slots as pslots_mod
from cyo_adventure.moderation.personalizable_slots import (
    PERSONALIZABLE_SLOTS_UNRECOVERABLE,
    PersonalizableSlots,
)
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.sentinels import wrap
from cyo_adventure.storybook.theme_contract import SlotScope, SlotSpec, ThemeContract
from cyo_adventure.validator.gate import GateResult
from cyo_adventure.validator.report import Severity, ValidationFinding, ValidationReport

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from sqlalchemy import Select

pytestmark = pytest.mark.unit

_FAMILY_A = uuid.uuid4()
_NODE_ID = "n_start"
_CHOICE_ID = "c_follow"


def _node(blob: object, node_id: str = _NODE_ID) -> dict[str, object]:
    """Return the node with the given id from a story blob.

    Looked up by id rather than by position on purpose. These tests all act on
    ``_NODE_ID``, and indexing the shared ``_CANNED_STORY`` positionally silently
    retargets every one of them the moment that story changes shape, which is
    what happened when PL-25's floor forced an establishing node ahead of
    ``n_start``.

    Args:
        blob: A story blob dict (or the ORM column holding one).
        node_id: The node to return; defaults to the node under edit.

    Returns:
        The matching node dict.
    """
    nodes = cast("list[dict[str, object]]", cast("dict[str, object]", blob)["nodes"])
    return next(node for node in nodes if node["id"] == node_id)


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
    job: GenerationJob | None = None,
) -> None:
    """Wire a mock session for edit_node's load sequence.

    ``session.execute`` now serves two distinct ``select(...)`` statements:
    the storybook row lookup (``_load_edit_target``) and, since Task 6a's
    at-rest sentinel re-check, the ``GenerationJob`` provenance lookup inside
    ``personalizable_slot_ids_for_story``. The two are distinguished by
    which ORM entity they target, mirroring
    tests/unit/test_moderation_pipeline.py::_load. Default ``job=None``
    (no job on record) resolves an empty personalizable-slot set: today's
    dormant default for every test that does not explicitly wire a job.
    """

    def _execute_side_effect(stmt: Select[tuple[object]]) -> MagicMock:
        if stmt.column_descriptions[0]["type"] is GenerationJob:
            return _execute_result(job)
        return _execute_result(story)

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    session.scalar = AsyncMock(return_value=latest_version)
    session.get = AsyncMock(return_value=version_row)
    session.scalars = AsyncMock(return_value=_scalars_result(child_names or []))


def _ctx(
    role: str, session: AsyncMock, *, family_id: uuid.UUID = _FAMILY_A
) -> RequestContext:
    return RequestContext(
        principal=_principal(role, family_id=family_id), session=session
    )


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
            settings: Settings,
            *,
            generator_provider: str | None,
            generator_model: str | None,
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

    body = NodeEditBody(body="x")
    with pytest.raises(AuthorizationError, match="admin or guardian role required"):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_device_role_rejected() -> None:
    session = AsyncMock(spec=AsyncSession)
    ctx = _ctx("device", session)

    body = NodeEditBody(body="x")
    with pytest.raises(AuthorizationError, match="admin or guardian role required"):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_story_raises_404() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=_execute_result(None))
    ctx = _ctx("admin", session)

    body = NodeEditBody(body="x")
    with pytest.raises(ResourceNotFoundError, match="storybook 's1' not found"):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)


@pytest.mark.asyncio
async def test_guardian_other_family_rejected() -> None:
    story = _story("in_review", family_id=uuid.uuid4())
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=_execute_result(story))
    ctx = _ctx("guardian", session, family_id=_FAMILY_A)

    body = NodeEditBody(body="x")
    with pytest.raises(AuthorizationError):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)


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

    body = NodeEditBody(body="x")
    with pytest.raises(StateTransitionError, match="in_review or needs_revision"):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)


@pytest.mark.asyncio
async def test_needs_revision_status_is_editable() -> None:
    story = _story("needs_revision")
    version_row = _version_row()
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    result = await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="A brand new opening."), ctx=ctx
    )

    assert result.status == "needs_revision"
    assert _node(version_row.blob)["body"] == "A brand new opening."


@pytest.mark.asyncio
async def test_not_latest_version_rejected() -> None:
    story = _story("in_review")
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=_version_row(), latest_version=2)
    ctx = _ctx("admin", session)

    body = NodeEditBody(body="x")
    with pytest.raises(StateTransitionError, match="latest version"):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)


# ---------------------------------------------------------------------------
# Prose-only edit semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_node_id_raises_404() -> None:
    story = _story("in_review")
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=_version_row())
    ctx = _ctx("admin", session)

    body = NodeEditBody(body="x")
    with pytest.raises(ResourceNotFoundError, match="node 'does-not-exist'"):
        await node_edit.edit_node("s1", 1, "does-not-exist", body, ctx=ctx)


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
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)

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
    result = await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)

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
        f["node_id"] == "n_clearing_fork"
        and f["message"] == "unrelated node, must survive"
        for f in findings
    )
    assert any(f["message"] == "whole-story note" for f in findings)
    # The fresh Stage-1 re-review PASSes (the autouse review backend always
    # answers "safe" per _safe_review_provider), and design doc 2.1 (Task
    # B1.8) says PASS is never persisted: the fresh PASS finding is filtered
    # out, and the stale finding was already dropped above, so no llm_safety
    # finding for the edited node survives in either form.
    assert not any(
        f["node_id"] == _NODE_ID and f["source"] == "llm_safety" for f in findings
    )

    # The response surface reflects the edit: the returned blob is the same
    # edited story state persisted above (asserted on version_row.blob at the
    # top of this test). flagged_passages is a filtered projection: PASS
    # verdicts and, for admins, noise-floored findings drop out, so it is not a
    # reliable oracle that the edit is visible; the surface blob is.
    assert result.storybook_id == "s1"
    assert result.blob == version_row.blob


@pytest.mark.asyncio
async def test_guardian_own_family_edit_allowed() -> None:
    story = _story("in_review", family_id=_FAMILY_A)
    version_row = _version_row()
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("guardian", session, family_id=_FAMILY_A)

    result = await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="Guardian-edited opening."), ctx=ctx
    )

    assert result.status == "in_review"
    assert _node(version_row.blob)["body"] == "Guardian-edited opening."


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
        "run_fill_gate",
        lambda *_a, **_kw: GateResult(
            report=failing_report, blocked=True, safety_flagged=False
        ),
    )

    body = NodeEditBody(body="x")
    with pytest.raises(ValidationError) as exc_info:
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)

    assert exc_info.value.details["findings"][0]["rule_id"] == "L1-7"
    # The stored blob is untouched: the mutation happened on a discarded copy.
    assert version_row.blob is original_blob
    session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Sentinel-integrity at-rest re-check (Task 6a): an edit that injects, forges,
# or mislocates a sentinel is rejected fail-closed, mirroring the gate cap
# above (422, stored blob left byte-for-byte unchanged).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_injecting_forged_sentinel_rejected_and_blob_unchanged() -> None:
    """A body edit that injects a well-formed sentinel is rejected.

    No ``GenerationJob`` is wired, so the story's personalizable-slot set
    resolves to the dormant default (empty, per ``_wire_session``'s
    docstring): ANY well-formed sentinel in the edited body is therefore an
    ``unknown_slot`` violation under ``check_sentinel_integrity_at_rest``,
    exactly as it would be for a real story with no personalizable contract.
    """
    story = _story("in_review")
    version_row = _version_row()
    original_blob = version_row.blob
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    body = NodeEditBody(body=f"You step onto a path marked {wrap('HERO', 'Ada')}.")
    with pytest.raises(ValidationError, match="sentinel"):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)

    # The stored blob is untouched: the mutation happened on a discarded copy.
    assert version_row.blob is original_blob
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_edit_leaving_sentinel_in_choice_label_rejected() -> None:
    """A choice-label edit that leaves a well-formed sentinel in place is
    rejected, even though the slot id would otherwise be declared: a choice
    label is never a legal sentinel surface (mirrors the title case in
    sentinel_integrity.py).
    """
    story = _story("in_review")
    version_row = _version_row()
    original_blob = version_row.blob
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    body = NodeEditBody(choice_labels={_CHOICE_ID: wrap("HERO", "Ada")})
    with pytest.raises(ValidationError, match="sentinel"):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)

    assert version_row.blob is original_blob
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_edit_contract_unrecoverable_with_sentinel_rejected() -> None:
    """An UNRECOVERABLE contract still fails closed when the edited blob bears a
    sentinel: with no declared slots, any well-formed sentinel is an
    ``unknown_slot`` violation, so a forged/injected sentinel is rejected
    exactly as it would be under a recovered contract.

    A ``GenerationJob`` with a skeleton_slug but no recoverable band leaves
    the personalizable-slot set unrecoverable (``None``), which degrades to an
    empty declared-slot set for the at-rest check.
    """
    story = _story("in_review")
    version_row = _version_row()
    original_blob = version_row.blob
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={"skeleton_slug": "themed-slug"},  # no skeleton_band
    )
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row, job=job)
    ctx = _ctx("admin", session)

    body = NodeEditBody(body=f"You reach the gate marked {wrap('HERO', 'Ada')}.")
    with pytest.raises(ValidationError, match="sentinel"):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)

    assert version_row.blob is original_blob
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_edit_contract_unrecoverable_sentinel_free_succeeds() -> None:
    """An UNRECOVERABLE contract must NOT permanently block a sentinel-free edit.

    Regression: a story whose personalizable-slot contract cannot be recovered
    (a ``GenerationJob`` with a skeleton_slug but no recoverable band) used to
    fail closed on EVERY node edit, locking the entire (dormant, sentinel-free)
    existing catalog out of editing. With no sentinel in the edited blob there
    is nothing for the at-rest check to validate against the contract, so the
    edit proceeds; fail-closed is preserved only for blobs that actually carry
    a sentinel (see the sibling ``..._with_sentinel_rejected`` test).
    """
    story = _story("in_review")
    version_row = _version_row()
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={"skeleton_slug": "themed-slug"},  # no skeleton_band
    )
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row, job=job)
    ctx = _ctx("admin", session)

    result = await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="A perfectly ordinary edit."), ctx=ctx
    )

    assert result.status == "in_review"
    assert _node(version_row.blob)["body"] == "A perfectly ordinary edit."


def _wire_personalizable_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> GenerationJob:
    """Write a real contract sidecar and wire the loader seam for one HERO slot.

    Mirrors tests/unit/test_moderation_pipeline.py::_wire_personalizable_job:
    ``resolve_skeleton_path``/``load_skeleton`` are doubled so no real skeleton
    file is needed, but ``load_contract_for``'s own sidecar read is the REAL
    function reading a REAL file, so the contract chain that
    ``personalizable_slot_ids_for_story`` drives runs end to end.

    Returns:
        A ``GenerationJob`` row naming the wired skeleton, ready for
        ``_wire_session(..., job=...)``.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / "themed-slug.json"
    contract = ThemeContract(
        contract_version=1,
        skeleton_slug="themed-slug",
        age_band=AgeBand.BAND_8_11,
        legacy_lexicon=[],
        default_binding={"HERO": "Ada"},
        slots=[
            SlotSpec(
                id="HERO",
                scope=SlotScope.GLOBAL,
                meaning="the reader's own child, personalized",
                kind="personalizable",
                personalization_field="protagonist_first_name",
                role_safety="protagonist",
            ),
        ],
    )
    skeleton_path.with_name("themed-slug.contract.json").write_bytes(
        contract.model_dump_json().encode("utf-8")
    )

    def _resolve(_band: object, _slug: object) -> Path:
        return skeleton_path

    def _load_skeleton(_path: object) -> dict[str, object]:
        # Must carry a `{HERO}` token: `load_contract_for` cross-checks the
        # contract's declared slot ids against the skeleton's own tokens and
        # fails the load (declared_but_absent) on a mismatch, which would
        # resolve the slot set to None and silently make the tests below pass
        # for the wrong reason. Mirrors test_moderation_pipeline.py's
        # `_personalizable_skeleton`.
        return {
            "nodes": [
                {
                    "id": "n_start",
                    "body": (
                        "<<FILL role=setup words=40 beats='The hero, {HERO}, "
                        "arrives and must choose a path.'>>"
                    ),
                    "choices": [],
                },
            ],
        }

    monkeypatch.setattr(pslots_mod, "resolve_skeleton_path", _resolve)
    monkeypatch.setattr(pslots_mod, "load_skeleton", _load_skeleton)
    return GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={"skeleton_slug": "themed-slug", "skeleton_band": "8-11"},
    )


@pytest.mark.asyncio
async def test_edit_removing_last_sentinel_clears_personalization_eligible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Editing away the story's only sentinel must clear the eligibility flag.

    ``personalization_eligible`` is derived once at persist time from the blob
    as it stood then, and ``api/library.py`` reads it verbatim to advertise a
    personalization affordance to the caller. A node edit rewrites the stored
    blob in place, so an edit that removes the last sentinel leaves the column
    promising a slot the blob can no longer fill unless it is recomputed at the
    same write. The at-rest sentinel check cannot substitute: it validates
    sentinels that are PRESENT and says nothing about one that is gone.
    """
    story = _story("in_review")
    blob = copy.deepcopy(_CANNED_STORY)
    edited = _node(blob)
    edited["body"] = f"{edited['body']} {wrap('HERO', 'Ada')}"
    version_row = _version_row()
    version_row.blob = blob
    version_row.personalization_eligible = True
    job = _wire_personalizable_job(monkeypatch, tmp_path)
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row, job=job)
    ctx = _ctx("admin", session)

    result = await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="Plain prose, no sentinel."), ctx=ctx
    )

    assert result.status == "in_review"
    assert _node(version_row.blob)["body"] == "Plain prose, no sentinel."
    assert version_row.personalization_eligible is False


@pytest.mark.asyncio
async def test_edit_preserving_sentinel_keeps_personalization_eligible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Positive control for the sibling test: an edit that leaves a declared
    sentinel standing in ANOTHER node must not clear the flag. The recompute
    reads the whole rewritten blob, not just the edited node, so a story that
    still carries a sentinel elsewhere stays eligible.
    """
    story = _story("in_review")
    blob = copy.deepcopy(_CANNED_STORY)
    # A node OTHER than the one under edit, so the sentinel survives the edit.
    other = _node(blob, "n_open")
    other["body"] = f"{other['body']} {wrap('HERO', 'Ada')}"
    version_row = _version_row()
    version_row.blob = blob
    version_row.personalization_eligible = True
    job = _wire_personalizable_job(monkeypatch, tmp_path)
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row, job=job)
    ctx = _ctx("admin", session)

    await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="Plain prose, no sentinel."), ctx=ctx
    )

    assert version_row.personalization_eligible is True


@pytest.mark.asyncio
async def test_unrecoverable_contract_drives_eligibility_from_the_tri_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The eligibility write reads the tri-state, not the integrity collapse.

    ``edit_node`` collapses ``PERSONALIZABLE_SLOTS_UNRECOVERABLE`` to an empty
    declared set for ONE decision: the at-rest integrity check, where "no slot
    is declared" and "which slots are declared cannot be proven" genuinely
    coincide. They do not coincide for ``personalization_eligible``, a
    persisted claim ``api/library.py`` reads verbatim, and reusing the
    collapsed value there made the column correct only by coincidence of the
    other leg (a sentinel-bearing blob 422s first; a sentinel-free one has no
    tokens anyway). No existing test sits at that intersection: both
    eligibility tests wire a RECOVERABLE contract via
    ``_wire_personalizable_job``. This pins the plumbing, so the coincidence
    can never quietly become the reason the column is right.
    """
    story = _story("in_review")
    version_row = _version_row()
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={"skeleton_slug": "themed-slug"},  # no skeleton_band
    )
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row, job=job)
    ctx = _ctx("admin", session)
    seen: list[object] = []
    real = node_edit._personalization_eligible

    def _spy(slots: object, blob: dict[str, object]) -> bool:
        seen.append(slots)
        return real(cast("PersonalizableSlots", slots), blob)

    monkeypatch.setattr(node_edit, "_personalization_eligible", _spy)

    await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="A perfectly ordinary edit."), ctx=ctx
    )

    # The RAW marker reached the eligibility decision. Under the old shape it
    # was handed `frozenset()`, the value authorized only for the check above.
    assert seen == [PERSONALIZABLE_SLOTS_UNRECOVERABLE]
    assert version_row.personalization_eligible is False


def test_personalization_eligible_is_false_for_an_unrecoverable_contract() -> None:
    """An unrecoverable contract yields False even for a token-bearing blob.

    The fail-closed choice for a column that GATES an affordance: withholding
    personalization from a book whose declared-slot set cannot be proven costs
    a reader plain prose, while asserting eligibility on an unprovable
    contract advertises a personalization the story cannot be shown to
    support. The paired frozenset case is the control that keeps this honest:
    it proves the blob really does carry tokens, so the ``False`` above comes
    from the tri-state arm and not from an empty manifest.
    """
    blob = copy.deepcopy(_CANNED_STORY)
    node = _node(blob)
    node["body"] = f"{node['body']} {wrap('HERO', 'Ada')}"

    assert (
        node_edit._personalization_eligible(PERSONALIZABLE_SLOTS_UNRECOVERABLE, blob)
        is False
    )
    assert node_edit._personalization_eligible(frozenset({"HERO"}), blob) is True
    # And a declared-but-empty contract is still False, so the two frozenset
    # readings stay distinguishable from each other as well as from the marker.
    assert node_edit._personalization_eligible(frozenset(), blob) is False


@pytest.mark.asyncio
async def test_unrecoverable_contract_is_logged_at_the_edit_site(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The collapse emits its own trace, naming the story it applied to.

    The resolver logs the contract FAILURE (which slug, which band); nothing
    recorded the CONSEQUENCE, that this edit was integrity-checked against an
    empty declared set. Without it, a 422-free edit under an unrecoverable
    contract is indistinguishable in the logs from one under a recovered,
    genuinely empty contract.
    """
    story = _story("in_review")
    version_row = _version_row()
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s1",
        authoring_metadata={"skeleton_slug": "themed-slug"},  # no skeleton_band
    )
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row, job=job)
    ctx = _ctx("admin", session)

    with caplog.at_level("INFO"):
        await node_edit.edit_node(
            "s1", 1, _NODE_ID, NodeEditBody(body="A perfectly ordinary edit."), ctx=ctx
        )

    # structlog renders through stdlib logging here, so the structured kv
    # pairs land in the rendered record text; ANSI color codes sit between key
    # and value, so each token is asserted on its own.
    assert "node_edit.slot_contract_unrecoverable_empty_declared_set" in caplog.text
    assert "s1" in caplog.text
    assert _NODE_ID in caplog.text


@pytest.mark.asyncio
async def test_edit_sentinel_free_still_succeeds() -> None:
    """Dormancy: a normal sentinel-free edit is unaffected by the new check."""
    story = _story("in_review")
    version_row = _version_row()
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    result = await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="A perfectly ordinary edit."), ctx=ctx
    )

    assert result.status == "in_review"
    assert _node(version_row.blob)["body"] == "A perfectly ordinary edit."


@pytest.mark.asyncio
async def test_classifier_call_blocked_on_pii_in_edited_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A registered real-child name in the edited node body blocks the write
    before the Stage-0 classifier call, mirroring
    test_moderation_pipeline.py::test_classifier_call_blocked_on_pii_in_node_body.

    Regression test: OpenAI Moderation/Google Perspective previously received
    the edited prose with no PII screening at all, unlike the sibling LLM
    safety stage (``guarded_review``) a few lines away in the same function.
    """
    story = _story("in_review")
    version_row = _version_row()
    original_blob = version_row.blob
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row, child_names=["Ada"])
    ctx = _ctx("admin", session)

    classifier_called = {"count": 0}

    async def _counting_run_classifiers(*_a: object, **_kw: object) -> list[object]:
        classifier_called["count"] += 1
        return []

    monkeypatch.setattr(node_edit, "run_classifiers", _counting_run_classifiers)

    body = NodeEditBody(body="This page was written just for Ada today.")
    with pytest.raises(ValidationError):
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)

    assert classifier_called["count"] == 0
    # The stored blob is untouched: the mutation happened on a discarded copy.
    assert version_row.blob is original_blob
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_missing_openai_key_outside_local_is_recorded_as_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F4: outside "local", editing a node with no OpenAI key configured must
    persist a ``classifier_degraded`` finding, not silently skip Stage-0
    coverage.

    ``edit_node`` passes ``require_classifiers=settings.environment !=
    "local"`` to ``run_classifiers`` (the module-level ``settings`` this
    file's ``_settings_without_classifier_keys`` autouse fixture normally
    pins to a bare, local ``Settings()``; this test overrides it for its own
    body only), matching moderation/pipeline.py's deployed-tier posture.
    Unlike rescreen.py's ephemeral sweep outcome, this finding is MERGED
    into ``version_row.moderation_report`` (a persisted JSONB column, see
    ``_merge_moderation_report``) and read back by
    ``moderation_report_unusable``/``severe_finding_counts`` at every future
    ``approve()`` call, so the assertion here is on what is PERSISTED, not
    merely on what ``edit_node`` returns.

    Mutation check performed by hand before landing this test: with
    ``edit_node``'s ``require_classifiers=settings.environment != "local"``
    argument hardcoded back to ``require_classifiers=False``, this test
    fails with ``StopIteration`` (no ``classifier_degraded`` entry exists in
    the persisted report at all, since the classifier leg silently skips
    coverage on a missing key when not required). Restored afterward to the
    real ``settings.environment != "local"`` expression, which is what
    ships.
    """
    non_local_settings = Settings(
        environment="staging",
        database_url=(
            "postgresql+asyncpg://appuser:testpass@db.example.com/cyo_adventure"
        ),
        oidc_issuer="https://project.supabase.co/auth/v1",
        oidc_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
        child_session_secret="test-child-session-secret-0123456789abcd",
        device_grant_secret="test-device-grant-secret-0123456789abcdef",
        allow_mock_review=True,
    )
    assert non_local_settings.openai_api_key is None
    monkeypatch.setattr(node_edit, "settings", non_local_settings)

    story = _story("in_review")
    version_row = _version_row()
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    await node_edit.edit_node(
        "s1", 1, _NODE_ID, NodeEditBody(body="An ordinary edit."), ctx=ctx
    )

    report = cast("dict[str, object]", version_row.moderation_report)
    findings = cast("list[dict[str, object]]", report["findings"])
    degraded = next(f for f in findings if f["category"] == "classifier_degraded")
    assert degraded["verdict"] == "advisory"
    assert degraded["structural"] is True
    assert "not configured" in cast("str", degraded["message"])


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
        "s1",
        1,
        _NODE_ID,
        NodeEditBody(body="Something the reviewer will block."),
        ctx=ctx,
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
        "s1", 1, _NODE_ID, NodeEditBody(body="Edited for the event test."), ctx=ctx
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
# _merge_moderation_report (Task B1.8: align with the Stage B persisted shape)
# ---------------------------------------------------------------------------


def _fresh_finding(verdict: Verdict, *, source: Source = Source.LLM_SAFETY) -> Finding:
    return Finding(
        stage=1,
        source=source,
        category="safety",
        node_id=_NODE_ID,
        verdict=verdict,
        score=None,
        message="fresh re-review",
    )


def test_aggregate_carried_verbatim_when_present() -> None:
    """The stored report's aggregate block is copied through unchanged: this
    single-node re-review has no way to recompute nodes_reviewed/pass_counts
    (the old PASS rows they were built from are not persisted), so recomputing
    here would fabricate a number, not refresh one."""
    stored: dict[str, object] = {
        "findings": [],
        "summary": {
            "count": 0,
            "hard_block": False,
            "soft_flag": False,
            "repaired": False,
            "reviewer_independent": True,
        },
        "aggregate": {"nodes_reviewed": 7, "pass_counts": {"safety": 5}},
    }
    result = node_edit._merge_moderation_report(stored, _NODE_ID, [], independent=True)
    assert result["aggregate"] == {"nodes_reviewed": 7, "pass_counts": {"safety": 5}}


def test_aggregate_omitted_when_absent() -> None:
    """A legacy stored report with no aggregate block yields a merged report
    with no aggregate key at all, never a fabricated empty one."""
    stored: dict[str, object] = {
        "findings": [],
        "summary": {
            "count": 0,
            "hard_block": False,
            "soft_flag": False,
            "repaired": False,
            "reviewer_independent": True,
        },
    }
    result = node_edit._merge_moderation_report(stored, _NODE_ID, [], independent=True)
    assert "aggregate" not in result


def test_fresh_pass_findings_not_persisted() -> None:
    """A fresh single-node re-review can still emit a clean PASS (e.g. the
    classifier or safety stage finding nothing); design doc 2.1 says PASS is
    never persisted, and that must hold for this write path too."""
    fresh = [_fresh_finding(Verdict.PASS), _fresh_finding(Verdict.FLAG)]
    result = node_edit._merge_moderation_report(None, _NODE_ID, fresh, independent=True)
    findings = result["findings"]
    assert isinstance(findings, list)
    assert len(findings) == 1
    assert findings[0]["verdict"] == "flag"
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["count"] == 1


def test_single_node_merged_finding_dropped_as_stale() -> None:
    """A merged Stage-B finding scoped to ONLY the edited node (node_ids ==
    [node_id]) is fully superseded by the fresh re-review and dropped, same
    as the pre-Stage-B bare node_id match."""
    stored: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": _NODE_ID,
                "verdict": "flag",
                "score": None,
                "message": "stale single-node merged finding",
                "node_ids": [_NODE_ID],
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }
    result = node_edit._merge_moderation_report(stored, _NODE_ID, [], independent=True)
    findings = result["findings"]
    assert isinstance(findings, list)
    assert findings == []


def test_multi_node_merged_finding_narrows_to_the_unedited_nodes() -> None:
    """A merged finding covering the edited node ALONGSIDE others is narrowed.

    Neither whole-finding outcome is acceptable. Dropping it discards the other
    nodes' coverage, which this single-node endpoint cannot recompute. Keeping
    it whole pins a stale flag to the edited node permanently: the fresh
    re-review that just cleared that node cannot dislodge it, and no later edit
    to any other node will either, so the guardian sees a flag on prose that has
    been clean for every review since.

    Narrowing gives both: the edited node loses coverage it no longer warrants,
    the others keep theirs. It is sound only because ``merge_findings`` groups
    on the full field tuple, so every node in ``node_ids`` carries the same
    verdict, severity, and message; removing one leaves the rest accurate.

    # #CRITICAL: data integrity: node_id is rewritten to the first REMAINING
    # node, never left pointing at the removed one, so pre-Stage-B readers that
    # only understand node_id do not attribute the finding to cleared prose.
    # #VERIFY: this test.
    """
    stored: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": _NODE_ID,
                "verdict": "flag",
                "score": None,
                "message": "multi-node merged finding (3 findings merged)",
                "node_ids": [_NODE_ID, "n_clearing_fork", "n_river_bank"],
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }
    result = node_edit._merge_moderation_report(stored, _NODE_ID, [], independent=True)
    findings = result["findings"]
    assert isinstance(findings, list)
    assert len(findings) == 1
    assert findings[0]["message"] == "multi-node merged finding (3 findings merged)"
    # The edited node is gone; the other two keep their coverage.
    assert findings[0]["node_ids"] == ["n_clearing_fork", "n_river_bank"]
    # node_id follows node_ids rather than continuing to name cleared prose.
    assert findings[0]["node_id"] == "n_clearing_fork"


def test_merged_finding_covering_an_untouched_node_set_is_left_alone() -> None:
    """Editing a node absent from node_ids must not perturb the finding."""
    stored: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_clearing_fork",
                "verdict": "flag",
                "score": None,
                "message": "elsewhere in the book (2 findings merged)",
                "node_ids": ["n_clearing_fork", "n_river_bank"],
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }
    result = node_edit._merge_moderation_report(stored, _NODE_ID, [], independent=True)
    findings = result["findings"]
    assert isinstance(findings, list)
    assert len(findings) == 1
    assert findings[0]["node_ids"] == ["n_clearing_fork", "n_river_bank"]
    assert findings[0]["node_id"] == "n_clearing_fork"


def test_legacy_old_shape_report_merges_cleanly() -> None:
    """A pre-Stage-B stored report (no severity/concern/node_ids/aggregate
    anywhere) still merges without raising: the bare node_id match still
    drops the stale same-node finding, unrelated findings survive, and no
    aggregate key is fabricated."""
    stored: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": _NODE_ID,
                "verdict": "flag",
                "score": None,
                "message": "old-shape stale finding",
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_clearing_fork",
                "verdict": "block",
                "score": None,
                "message": "old-shape unrelated finding",
            },
        ],
        "summary": {
            "count": 2,
            "hard_block": True,
            "soft_flag": False,
            "repaired": False,
            "reviewer_independent": True,
        },
    }
    fresh = [_fresh_finding(Verdict.ADVISORY)]
    result = node_edit._merge_moderation_report(
        stored, _NODE_ID, fresh, independent=True
    )
    findings = result["findings"]
    assert isinstance(findings, list)
    assert not any(f.get("message") == "old-shape stale finding" for f in findings)
    assert any(f.get("message") == "old-shape unrelated finding" for f in findings)
    assert any(f.get("message") == "fresh re-review" for f in findings)
    assert "aggregate" not in result


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


# ---------------------------------------------------------------------------
# A FLAGGING re-review: the fresh finding must actually land in the report
# ---------------------------------------------------------------------------


def _flag_review_provider() -> MockProvider:
    """A review backend double whose Stage-1 safety call FLAGs."""

    def _respond(prompt: str) -> str:
        if prompt.startswith("Age band:"):
            return '{"verdict": "flag", "reason": "freshly flagged prose"}'
        return '{"verdict": "pass", "reason": "ok"}'

    return MockProvider(responses=[_respond] * 8)


@pytest.mark.asyncio
async def test_fresh_flag_replaces_the_stale_finding_for_the_edited_node(
    review_seam: Callable[[MockProvider], None],
) -> None:
    """The stale finding goes and the fresh FLAG takes its place.

    Every other edited-node test in this module runs against the autouse
    PASSing backend, where design doc 2.1 drops the fresh finding before
    persistence. That makes "no llm_safety finding for the edited node" the
    expected outcome whether the splice works or is a no-op, so it cannot
    distinguish a working re-review from one whose result is discarded. A
    FLAGging backend does: the fresh finding is gate-relevant, so it must be
    visible in the persisted report.
    """
    review_seam(_flag_review_provider())
    story = _story("in_review")
    version_row = _version_row(
        moderation_report={
            "findings": [
                {
                    "stage": 1,
                    "source": "llm_safety",
                    "category": "safety",
                    "node_id": _NODE_ID,
                    "verdict": "flag",
                    "score": None,
                    "message": "stale pre-edit finding",
                },
            ],
            "summary": {
                "count": 1,
                "hard_block": False,
                "soft_flag": True,
                "repaired": False,
                "reviewer_independent": True,
            },
        }
    )
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    await node_edit.edit_node(
        "s1",
        1,
        _NODE_ID,
        NodeEditBody(body="Prose the reviewer will flag."),
        ctx=ctx,
    )

    report = cast("dict[str, object]", version_row.moderation_report)
    findings = cast("list[dict[str, object]]", report["findings"])
    edited_node_safety = [
        f for f in findings if f["node_id"] == _NODE_ID and f["source"] == "llm_safety"
    ]
    assert len(edited_node_safety) == 1
    assert edited_node_safety[0]["message"] == "freshly flagged prose"
    assert edited_node_safety[0]["verdict"] == "flag"
    # The gate flags follow the fresh finding, not the discarded stale one.
    summary = cast("dict[str, object]", report["summary"])
    assert summary["soft_flag"] is True


@pytest.mark.asyncio
async def test_fresh_flag_lands_alongside_a_narrowed_merged_finding(
    review_seam: Callable[[MockProvider], None],
) -> None:
    """The narrowing and the splice compose on one report.

    A merged finding covering the edited node plus another is narrowed off the
    edited node, and the fresh single-node FLAG is spliced in for it. The other
    node keeps the merged coverage the endpoint cannot recompute.
    """
    review_seam(_flag_review_provider())
    story = _story("in_review")
    version_row = _version_row(
        moderation_report={
            "findings": [
                {
                    "stage": 1,
                    "source": "llm_safety",
                    "category": "safety",
                    "node_id": _NODE_ID,
                    "verdict": "flag",
                    "score": None,
                    "message": "merged across two nodes (2 findings merged)",
                    "node_ids": [_NODE_ID, "n_clearing_fork"],
                },
            ],
            "summary": {
                "count": 1,
                "hard_block": False,
                "soft_flag": True,
                "repaired": False,
                "reviewer_independent": True,
            },
        }
    )
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    await node_edit.edit_node(
        "s1",
        1,
        _NODE_ID,
        NodeEditBody(body="Prose the reviewer will flag."),
        ctx=ctx,
    )

    report = cast("dict[str, object]", version_row.moderation_report)
    findings = cast("list[dict[str, object]]", report["findings"])
    merged = [f for f in findings if f.get("node_ids")]
    assert len(merged) == 1
    # Narrowed off the edited node, still covering the other.
    assert merged[0]["node_ids"] == ["n_clearing_fork"]
    assert merged[0]["node_id"] == "n_clearing_fork"
    # The fresh finding covers the edited node in its place.
    fresh = [
        f
        for f in findings
        if f["node_id"] == _NODE_ID and f["message"] == "freshly flagged prose"
    ]
    assert len(fresh) == 1


@pytest.mark.asyncio
async def test_edit_writing_a_fill_directive_is_rejected() -> None:
    """An edit that writes a ``<<FILL ...>>`` directive into a body is refused.

    ``edit_node`` re-gates the edited blob, but called ``run_gate`` without a
    ``context``, so the edited FILLED book was judged under the catalog-time
    ``"skeleton"`` posture, where a retained directive is expected input rather
    than a defect. PL-27 is the only deterministic floor between an unwritten
    node and a human reviewer (validator/policy.py::check_fill_directives), so
    under the wrong posture an admin could replace real prose with a directive,
    have it accepted, and have the stored ``validation_report`` record that as
    clean.
    """
    story = _story("in_review")
    version_row = _version_row()
    original_blob = version_row.blob
    session = AsyncMock(spec=AsyncSession)
    _wire_session(session, story=story, version_row=version_row)
    ctx = _ctx("admin", session)

    body = NodeEditBody(body="<<FILL body: write the cavern scene here>>")

    with pytest.raises(ValidationError) as exc_info:
        await node_edit.edit_node("s1", 1, _NODE_ID, body, ctx=ctx)

    findings = exc_info.value.details["findings"]
    assert any(f["rule_id"] == "PL-27" for f in findings), findings
    assert version_row.blob is original_blob
    session.add.assert_not_called()
