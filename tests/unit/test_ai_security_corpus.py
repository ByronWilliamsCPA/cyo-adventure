# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""CI-runnable adversarial-corpus tests (the ai_security marker's substance).

The full adversarial evaluation needs a live review model and is run
offline via scripts/adversarial_harness.py, whose honesty guardrail
refuses to report a mock run as evidence. These tests pin everything
about that pipeline that IS deterministic, so the corpus and the
fail-safe plumbing are exercised on every CI run instead of never:

- corpus integrity (schema, unique ids, taxonomy coverage), so the
  hand-authored JSON cannot rot silently;
- the PII positive control (F1) run for real: the PiiGuardedProvider is
  model-independent and must raise before any egress;
- fail-safe routing: with a provider returning the unparseable "{}",
  every Stage-1 safety probe resolves to FLAG (fail closed), never PASS;
- the honesty guardrail itself: a mock-provider corpus run is never
  evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.adversarial_harness import (
    CorpusReport,
    _observe_item,  # pyright: ignore[reportPrivateUsage]
    run_corpus,
)

_CORPUS_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "planning"
    / "safety"
    / "adversarial-corpus.json"
)
_KNOWN_STATUSES = frozenset(
    {"caught", "missed", "control_ok", "control_over_block", "gap", "skipped"}
)


def _corpus() -> dict[str, Any]:
    """Load the adversarial corpus JSON document."""
    return json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))


def _items() -> list[dict[str, Any]]:
    """Load the corpus items array."""
    items: list[dict[str, Any]] = _corpus()["items"]
    return items


class _RecordingMockProvider:
    """ReviewProvider double: records calls, returns unparseable output.

    Mirrors the real mock review provider's behavior ("{}" for every call,
    which the stage parsers map to their fail-safe verdict) while recording
    each call so egress can be asserted.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Record the call and return output no stage parser accepts."""
        _ = max_tokens
        self.calls.append((system, prompt))
        return "{}"


@pytest.mark.unit
@pytest.mark.ai_security
def test_corpus_items_have_unique_ids_and_valid_schema() -> None:
    """Every corpus item satisfies the shape the harness routes on."""
    corpus = _corpus()
    severity = set(corpus["verdict_severity"])
    items = _items()
    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids)), "duplicate corpus item ids"
    for item in items:
        assert isinstance(item.get("id"), str), item
        assert item["id"], item
        assert item.get("taxonomy_class") in set("ABCDEF"), item["id"]
        assert isinstance(item.get("executable"), bool), item["id"]
        assert isinstance(item.get("rationale"), str), item["id"]
        assert item["rationale"], item["id"]
        expected = item.get("expected_min_verdict")
        assert expected is None or expected in severity, item["id"]
        if not item["executable"]:
            continue
        if item.get("target") == "pii_guard":
            assert isinstance(item.get("passage"), str), item["id"]
            assert isinstance(item.get("pii_context"), dict), item["id"]
        else:
            assert item.get("target_stage") in {1, 2, "aggregate"}, item["id"]
            has_passage = isinstance(item.get("passage"), str)
            has_nodes = isinstance(item.get("nodes"), list) and item["nodes"]
            assert has_passage or has_nodes, item["id"]
            assert expected is not None, item["id"]


@pytest.mark.unit
@pytest.mark.ai_security
def test_corpus_covers_every_taxonomy_class() -> None:
    """Classes A-F each keep at least one item (anti-deletion guard)."""
    classes = {item["taxonomy_class"] for item in _items()}
    assert classes == set("ABCDEF")


@pytest.mark.unit
@pytest.mark.ai_security
@pytest.mark.asyncio
async def test_pii_positive_control_raises_before_egress() -> None:
    """F1's real-child name is caught by the guard with zero provider calls.

    This is the corpus's model-independent item: the PiiGuardedProvider
    screens the prompt BEFORE the inner provider is invoked, so the catch
    must be deterministic in CI, not just in a live evaluation.
    """
    (f1,) = [item for item in _items() if item.get("target") == "pii_guard"]
    provider = _RecordingMockProvider()
    observed, guard_raised = await _observe_item(f1, provider)
    assert guard_raised is True
    assert observed == []
    assert provider.calls == [], "PII reached the provider (egress before guard)"


@pytest.mark.unit
@pytest.mark.ai_security
@pytest.mark.asyncio
async def test_stage1_probes_fail_safe_to_flag_on_unparseable_output() -> None:
    """Every Stage-1 item resolves to FLAG when the reviewer output is junk.

    The moderation stages must fail closed: a reviewer that returns
    unparseable output must never let adversarial prose PASS by default.
    """
    stage1_items = [
        item
        for item in _items()
        if item["executable"] and item.get("target_stage") in (1, "aggregate")
    ]
    assert stage1_items, "corpus lost its Stage-1 adversarial items"
    for item in stage1_items:
        observed, guard_raised = await _observe_item(item, _RecordingMockProvider())
        assert guard_raised is None, item["id"]
        assert observed, item["id"]
        assert all(verdict == "flag" for verdict in observed), (
            f"{item['id']}: stage-1 fail-safe produced {observed} instead of flag"
        )


@pytest.mark.unit
@pytest.mark.ai_security
@pytest.mark.asyncio
async def test_mock_corpus_run_completes_and_is_never_evidence() -> None:
    """A full mock run classifies every item but can never count as evidence.

    Pins the harness's honesty guardrail: catch-rates from a mock provider
    measure fail-safe routing, not classifier discrimination, so
    ``is_evidence`` must be False no matter how good the numbers look.
    """
    report = await run_corpus(
        _items(), _RecordingMockProvider(), review_provider_name="mock"
    )
    assert isinstance(report, CorpusReport)
    assert report.is_evidence is False
    assert len(report.outcomes) == len(_items())
    assert {outcome.status for outcome in report.outcomes} <= _KNOWN_STATUSES
