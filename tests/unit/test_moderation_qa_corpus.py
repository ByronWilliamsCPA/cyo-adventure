# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Fixture-integrity tests for the staging Moderation QA corpus.

Pins the ground truth ``docs/planning/safety/moderation-qa-corpus.json`` and
the full storybook fixtures under ``tests/fixtures/moderation_qa/books/``
(moderation-review-redesign-2026-07-28.md section 5): every book must parse
as a schema-valid Storybook, every ``mqa_`` id must be unique and namespaced,
and every manifest label must reference a real node in its book. These are
pure parse/shape checks; the corpus's live behavior against a real reviewer
is exercised by scripts/seed_moderation_qa.py in staging and compared by
scripts/moderation_qa_scorecard.py, neither of which this module runs.

One check here is not a shape check: the corpus is also run through the
deterministic validation gate. The corpus originally shipped without ever
being gated, and five of six fixtures turned out to be blocked (a 10-13 book
declaring intense flags its own band caps at moderate, two mis-declared
topologies, and four books under their band's ending/decision floors). That
is invisible at the manifest level but decides whether an auto-repair can be
adopted, because moderation/pipeline.py only adopts a repaired blob that
itself clears run_gate. So gate status is pinned, with an explicit allowlist
for the one book whose off-ceiling declaration is the point of the fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cyo_adventure.storybook.models import Storybook as StorybookDoc
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.report import Severity

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = (
    _REPO_ROOT / "docs" / "planning" / "safety" / "moderation-qa-corpus.json"
)
_KNOWN_VERDICTS = frozenset({"pass", "advisory", "flag", "block"})
_KNOWN_CATEGORIES = frozenset({"clean_control", "band_borderline", "bright_line_block"})

# The only corpus book allowed to fail the deterministic gate, and the only
# rule it is allowed to fail on. Its whole purpose is to declare content above
# its band's ceiling, so PL-16 firing is the fixture working, not a defect.
# Adding a book here costs that book its repair-adoption coverage, so it is a
# deliberate, documented trade rather than a way to quiet a red test.
# Gate-blocked fixtures, each mapped to the exact rules it may be blocked by.
# Per-book rather than one global rule set: a global allowlist would let ANY
# book start failing on a listed rule unnoticed, which is the drift this test
# exists to catch.
#
# storm_watch is blocked on two counts and both are deliberate. PL-16 is the
# content exception it was written for. PL-29 was added 2026-08-16 and is a
# real defect the fixture had all along: its graph reconverges at `n_water`,
# and ADR-011 section 7 gives 5-8 no reconverging topology at all (the row is
# loop_and_grow / open_map / time_cave), so there is no legal label for this
# shape at this band. Left as-is rather than repaired, because the graph is
# load-bearing for the moderation labels this corpus asserts and the book is a
# deliberately borderline fixture that is never adopted; recorded here so it
# reads as a known exception rather than as drift.
_GATE_BLOCKED_BY_DESIGN: dict[str, frozenset[str]] = {
    "mqa_borderline_storm_watch_5_8": frozenset({"PL-16", "PL-29"}),
}


def _manifest() -> dict[str, Any]:
    """Load the moderation QA corpus manifest."""
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def _books() -> list[dict[str, Any]]:
    """Load the manifest's book entries."""
    books: list[dict[str, Any]] = _manifest()["books"]
    return books


def _load_blob(entry: dict[str, Any]) -> dict[str, Any]:
    """Load a book entry's storybook JSON blob from its manifest-relative path."""
    path = _REPO_ROOT / entry["file"]
    blob: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return blob


@pytest.mark.unit
def test_manifest_verdict_severity_matches_moderation_report_verdicts() -> None:
    """The manifest's verdict scale must stay in lockstep with Verdict."""
    from cyo_adventure.moderation.report import Verdict

    manifest = _manifest()
    assert set(manifest["verdict_severity"]) == {v.value for v in Verdict}


@pytest.mark.unit
def test_every_book_id_is_unique_and_mqa_prefixed() -> None:
    """Every fixture id carries the mqa_ containment namespace and is unique."""
    books = _books()
    ids = [book["id"] for book in books]
    assert len(ids) == len(set(ids)), "duplicate book ids in the manifest"
    assert ids, "corpus lost all its books"
    for book_id in ids:
        assert book_id.startswith("mqa_"), (
            f"'{book_id}' is missing the mqa_ containment prefix"
        )


@pytest.mark.unit
def test_every_book_covers_the_three_authoring_categories() -> None:
    """At least one clean, borderline, and bright-line-block book exists."""
    categories = {book["category"] for book in _books()}
    assert categories == _KNOWN_CATEGORIES


@pytest.mark.unit
def test_every_book_parses_as_a_valid_storybook() -> None:
    """Every fixture blob satisfies the enforced Storybook pydantic schema.

    This is the schema-validation half of deliverable 1: a book that fails to
    parse (a bad ending kind/valence, a mismatched ending_count, a dangling
    start_node) fails loudly here instead of surfacing later as a moderation
    pipeline crash against a corrupted blob.
    """
    for entry in _books():
        blob = _load_blob(entry)
        story = StorybookDoc.model_validate(blob)
        assert story.id == entry["id"], (
            f"manifest id {entry['id']!r} does not match blob id {story.id!r}"
        )
        assert story.id.startswith("mqa_")


@pytest.mark.unit
def test_gate_blocked_books_are_exactly_the_declared_exceptions() -> None:
    """Only the allowlisted book may fail run_gate, and on a per-book allowlist (PL-16, plus PL-29 for the one 5-8 fixture whose reconverging graph ADR-011 s7 gives no legal label).

    A gate-blocked fixture can be moderated but can never have a repair
    adopted, because moderation/pipeline.py re-runs run_gate over the repaired
    blob before swapping it in. Silently letting a fixture drift off-gate
    therefore removes repair coverage without removing any manifest label, so
    the failure mode is a corpus that quietly tests less than it claims.
    """
    blocked: dict[str, list[str]] = {}
    for entry in _books():
        result = run_gate(_load_blob(entry))
        if not result.blocked:
            continue
        blocked[entry["id"]] = sorted(
            {
                finding.rule_id
                for finding in result.report.findings
                if finding.severity is Severity.ERROR
            }
        )
    assert set(blocked) == set(_GATE_BLOCKED_BY_DESIGN), (
        f"gate-blocked books changed: {blocked}"
    )
    for book_id, rule_ids in blocked.items():
        assert set(rule_ids) <= _GATE_BLOCKED_BY_DESIGN[book_id], (
            f"{book_id} is blocked by more than its declared exception: {rule_ids}"
        )


@pytest.mark.unit
def test_every_manifest_field_satisfies_the_label_schema() -> None:
    """Every manifest entry carries a well-formed expected-label record."""
    for entry in _books():
        book_id = entry["id"]
        assert entry.get("category") in _KNOWN_CATEGORIES, book_id
        assert entry.get("expected_min_verdict") in _KNOWN_VERDICTS, book_id
        rationale = entry.get("rationale")
        assert isinstance(rationale, str), book_id
        assert rationale, book_id
        age_band = entry.get("age_band")
        assert isinstance(age_band, str), book_id
        assert age_band, book_id
        negative_control = entry.get("negative_control", False)
        assert isinstance(negative_control, bool), book_id
        if negative_control:
            assert entry["expected_min_verdict"] == "pass", (
                f"{book_id}: a negative_control must expect exactly 'pass'"
            )
        node_labels = entry.get("node_labels")
        assert isinstance(node_labels, list), book_id
        for label in node_labels:
            node_id = label.get("node_id")
            assert isinstance(node_id, str), book_id
            assert node_id, book_id
            assert label.get("expected_min_verdict") in _KNOWN_VERDICTS, (
                f"{book_id}: node {label.get('node_id')!r}"
            )


@pytest.mark.unit
def test_every_node_label_references_a_real_node_in_its_book() -> None:
    """A manifest node label must name a node id that actually exists."""
    for entry in _books():
        blob = _load_blob(entry)
        real_node_ids = {node["id"] for node in blob["nodes"]}
        for label in entry.get("node_labels", []):
            assert label["node_id"] in real_node_ids, (
                f"{entry['id']}: node label references unknown node "
                f"{label['node_id']!r}"
            )


@pytest.mark.unit
def test_bright_line_block_book_declares_a_block_expectation() -> None:
    """The bright-line category book expects an unambiguous BLOCK.

    Guards against someone softening the corpus's one hard-stop case to a
    flag by accident: the whole point of a bright-line item is that it must
    never be mistaken for merely borderline.
    """
    block_books = [book for book in _books() if book["category"] == "bright_line_block"]
    assert block_books, "corpus lost its bright-line BLOCK case"
    for book in block_books:
        assert book["expected_min_verdict"] == "block", book["id"]
        assert any(
            label["expected_min_verdict"] == "block" for label in book["node_labels"]
        ), f"{book['id']}: bright-line book has no node-level block label"


@pytest.mark.unit
def test_clean_control_books_are_negative_controls() -> None:
    """Clean-control books must assert 'pass' as a negative control, not a floor.

    A clean book labeled as a bare expected_min_verdict floor (without
    negative_control) would silently tolerate the reviewer over-flagging it;
    that defeats the point of having a clean-control category at all.
    """
    clean_books = [book for book in _books() if book["category"] == "clean_control"]
    assert clean_books, "corpus lost its clean-control books"
    for book in clean_books:
        assert book.get("negative_control") is True, book["id"]
