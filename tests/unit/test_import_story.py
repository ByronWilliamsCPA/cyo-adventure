import uuid
from unittest.mock import AsyncMock

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import StorybookVersion
from cyo_adventure.generation.import_story import ImportRequest, import_filled_story


class _FakeResult:
    """Stand-in for a SQLAlchemy Result yielding one-tuples of child names."""

    def __init__(self, names: list[str]) -> None:
        self._names = names

    def all(self) -> list[tuple[str]]:
        """Return rows as one-tuples, matching ``select(column)`` results."""
        return [(name,) for name in self._names]


class _FakeSession:
    def __init__(self, *, child_names: list[str] | None = None) -> None:
        self.added: list[object] = []
        self._child_names = child_names or []

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None

    async def execute(self, _stmt: object) -> _FakeResult:
        """Stand in for the post-persist ChildProfile.display_name query."""
        return _FakeResult(self._child_names)


def _filled_story() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "id": "s_filled",
        "version": 1,
        "title": "Filled",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 4,
            "topology": "time_cave",
        },
        "variables": [],
        "start_node": "start",
        "nodes": [
            {
                "id": "start",
                "body": "You step onto the mossy path as a rabbit darts past.",
                "is_ending": False,
                "choices": [
                    {"id": "c1", "label": "Follow it", "target": "end"},
                    {"id": "c2", "label": "Look around first", "target": "d1"},
                ],
            },
            {
                "id": "d1",
                "body": "Two trails wind away from the clearing.",
                "is_ending": False,
                "choices": [
                    {"id": "c_d1a", "label": "Uphill", "target": "d2"},
                    {"id": "c_d1b", "label": "Toward the brook", "target": "alt1"},
                ],
            },
            {
                "id": "d2",
                "body": "The path forks once more.",
                "is_ending": False,
                "choices": [
                    {"id": "c_d2a", "label": "Into the ferns", "target": "alt2"},
                    {"id": "c_d2b", "label": "Up the ridge", "target": "alt3"},
                ],
            },
            {
                "id": "end",
                "body": "The rabbit leads you to a sunny clearing. You feel happy.",
                "is_ending": True,
                "ending": {
                    "id": "e_home",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "Home",
                },
            },
            {
                "id": "alt1",
                "body": "The brook sparkles over smooth stones.",
                "is_ending": True,
                "ending": {
                    "id": "e_brook",
                    "valence": "neutral",
                    "kind": "discovery",
                    "title": "The Brook",
                },
            },
            {
                "id": "alt2",
                "body": "A soft bed of ferns invites a quiet rest.",
                "is_ending": True,
                "ending": {
                    "id": "e_ferns",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "The Ferns",
                },
            },
            {
                "id": "alt3",
                "body": "From the ridge you can see the whole valley.",
                "is_ending": True,
                "ending": {
                    "id": "e_ridge",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The Ridge",
                },
            },
        ],
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_persists_a_valid_filled_story(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moderation = AsyncMock()
    monkeypatch.setattr(
        "cyo_adventure.generation.import_story.run_moderation_pipeline", moderation
    )
    session = _FakeSession()
    request = ImportRequest(
        blob=_filled_story(), family_id=uuid.uuid4(), model="opus-4.8"
    )
    story_id = await import_filled_story(session, request)
    assert story_id == "s_filled"
    versions = [r for r in session.added if isinstance(r, StorybookVersion)]
    assert len(versions) == 1
    assert versions[0].blob["id"] == "s_filled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_screens_the_persisted_story(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 1: import must run moderation on the version it just persisted.

    Before this fix, import_filled_story persisted a draft and returned,
    leaving the cyo-author skeleton-fill route reachable by admin
    submit/approve with zero content screening.
    """
    moderation = AsyncMock()
    monkeypatch.setattr(
        "cyo_adventure.generation.import_story.run_moderation_pipeline", moderation
    )
    session = _FakeSession(child_names=["Rosa"])
    request = ImportRequest(blob=_filled_story(), family_id=uuid.uuid4())

    story_id = await import_filled_story(session, request)

    moderation.assert_awaited_once()
    _, kwargs = moderation.call_args
    assert kwargs["story_id"] == story_id
    assert kwargs["version"] == 1
    assert kwargs["pii"].child_names == frozenset({"Rosa"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_propagates_moderation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A moderation-backend failure propagates; the caller owns the rollback.

    import_filled_story does not manage the transaction (see module docstring),
    so unlike the generation worker it must not swallow or reinterpret a
    moderation-pipeline exception -- it must simply not be caught here.
    """
    moderation = AsyncMock(side_effect=RuntimeError("review backend down"))
    monkeypatch.setattr(
        "cyo_adventure.generation.import_story.run_moderation_pipeline", moderation
    )
    session = _FakeSession()
    request = ImportRequest(blob=_filled_story(), family_id=uuid.uuid4())

    with pytest.raises(RuntimeError, match="review backend down"):
        await import_filled_story(session, request)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_threads_review_model_override_to_moderation_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ImportRequest.review_model_override reaches run_moderation_pipeline.

    Closes the parity gap between the two authoring mechanisms: the
    automated_provider path (generation/worker.py) already threaded
    authoring_metadata's review_stage2_model into this same call; the
    skill/import path had no override parameter at all until this fix.
    """
    moderation = AsyncMock()
    monkeypatch.setattr(
        "cyo_adventure.generation.import_story.run_moderation_pipeline", moderation
    )
    session = _FakeSession()
    request = ImportRequest(
        blob=_filled_story(),
        family_id=uuid.uuid4(),
        review_model_override="claude-opus-4.8",
    )

    await import_filled_story(session, request)

    moderation.assert_awaited_once()
    _, kwargs = moderation.call_args
    assert kwargs["review_model_override"] == "claude-opus-4.8"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_rejects_a_blocked_story() -> None:
    session = _FakeSession()
    broken = _filled_story()
    broken["nodes"][0]["choices"][0]["target"] = "missing"
    request = ImportRequest(blob=broken, family_id=uuid.uuid4())
    with pytest.raises(ValidationError, match="blocked"):
        await import_filled_story(session, request)
    assert session.added == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_rejects_blob_with_no_string_id() -> None:
    """A blob missing a string id raises ValidationError (via gate or id check).

    The gate's L1-1 schema conformance catches a non-string id before the
    explicit check at line 69-70, so this tests the gate-blocked path.
    """
    session = _FakeSession()
    blob = _filled_story()
    blob["id"] = 42  # non-string id - gate will block this
    request = ImportRequest(blob=blob, family_id=uuid.uuid4())
    with pytest.raises(ValidationError):
        await import_filled_story(session, request)
    assert session.added == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_id_check_fires_when_gate_passes_without_id() -> None:
    """The explicit id check guards against a gate-passing blob with no string id.

    This uses a targeted mock to simulate a gate that passes while the blob
    lacks a proper id -- exercising the defensive check at import_story.py:69.
    """
    from unittest.mock import patch

    from cyo_adventure.validator.gate import GateResult
    from cyo_adventure.validator.report import ValidationReport

    session = _FakeSession()
    blob = _filled_story()
    del blob["id"]  # remove the id key

    fake_result = GateResult(
        report=ValidationReport(), blocked=False, safety_flagged=False
    )
    with patch(
        "cyo_adventure.generation.import_story.run_gate", return_value=fake_result
    ):
        request = ImportRequest(blob=blob, family_id=uuid.uuid4())
        with pytest.raises(ValidationError, match="no string id"):
            await import_filled_story(session, request)

    # The id guard must reject before any row is staged: a regression that
    # appends rows before the check would otherwise leak a partial import.
    assert session.added == []
