import uuid

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import StorybookVersion
from cyo_adventure.generation.import_story import ImportRequest, import_filled_story


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None


def _filled_story() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "id": "s_filled",
        "version": 1,
        "title": "Filled",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
        },
        "variables": [],
        "start_node": "start",
        "nodes": [
            {
                "id": "start",
                "body": "You step onto the mossy path as a rabbit darts past.",
                "is_ending": False,
                "choices": [{"id": "c1", "label": "Follow it", "target": "end"}],
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
        ],
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_persists_a_valid_filled_story() -> None:
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
async def test_import_rejects_a_blocked_story() -> None:
    session = _FakeSession()
    broken = _filled_story()
    broken["nodes"][0]["choices"][0]["target"] = "missing"
    request = ImportRequest(blob=broken, family_id=uuid.uuid4())
    with pytest.raises(ValidationError, match="blocked"):
        await import_filled_story(session, request)
    assert session.added == []
