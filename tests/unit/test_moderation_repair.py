"""Unit tests for the bounded soft-gate auto-repair pass."""

from __future__ import annotations

import json

import pytest

from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.moderation.repair import attempt_repair
from cyo_adventure.moderation.report import Finding, ModerationReport, Source, Verdict

pytestmark = pytest.mark.asyncio


def _soft_report() -> ModerationReport:
    report = ModerationReport()
    report.add(
        Finding(
            stage=2,
            source=Source.LLM_READABILITY,
            category="reading_level",
            node_id="n1",
            verdict=Verdict.FLAG,
            message="too hard",
        )
    )
    return report


@pytest.mark.unit
async def test_repair_returns_revised_blob_from_generator() -> None:
    revised = {"id": "s1", "nodes": [{"id": "n1", "body": "simpler"}]}
    provider = MockProvider(responses=[json.dumps(revised)])
    new_blob = await attempt_repair(
        blob={"id": "s1", "nodes": [{"id": "n1", "body": "hard"}]},
        report=_soft_report(),
        generation_provider=provider,
        pii=PiiContext(child_names=frozenset(), birthdates=frozenset()),
        max_tokens=4096,
    )
    assert new_blob is not None
    assert new_blob["nodes"][0]["body"] == "simpler"


@pytest.mark.unit
async def test_repair_returns_none_on_unparseable_output() -> None:
    provider = MockProvider(responses=["not json"])
    new_blob = await attempt_repair(
        blob={"id": "s1", "nodes": []},
        report=_soft_report(),
        generation_provider=provider,
        pii=PiiContext(child_names=frozenset(), birthdates=frozenset()),
        max_tokens=4096,
    )
    assert new_blob is None
