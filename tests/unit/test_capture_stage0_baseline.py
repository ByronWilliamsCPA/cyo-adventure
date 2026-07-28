# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Unit tests for the Stage-0 baseline capture script's pure logic.

The network-calling paths are exercised only by an explicit operator run; what
is tested here is everything that decides *which* text gets scored and whether
the resulting artifact is writable, because a silent parsing bug would produce
a baseline that looks complete and calibrates the wrong thing.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.capture_stage0_baseline import (
    PassageScores,
    _build_artifact,  # pyright: ignore[reportPrivateUsage]
    _corpus_item_texts,  # pyright: ignore[reportPrivateUsage]
    _finite_or_none,  # pyright: ignore[reportPrivateUsage]
    _load_adversarial_passages,  # pyright: ignore[reportPrivateUsage]
    _load_clean_passages,  # pyright: ignore[reportPrivateUsage]
    _summarize,  # pyright: ignore[reportPrivateUsage]
)

_CORPUS = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "planning"
    / "safety"
    / "adversarial-corpus.json"
)


class TestFiniteOrNone:
    """Non-finite provider scores must degrade to null, never crash the write."""

    @pytest.mark.unit
    def test_finite_float_is_preserved(self) -> None:
        """An ordinary score round-trips unchanged."""
        assert _finite_or_none(0.42) == pytest.approx(0.42)

    @pytest.mark.unit
    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_non_finite_score_becomes_none(self, value: float) -> None:
        """NaN and infinities are recorded as an explicit null."""
        assert _finite_or_none(value) is None

    @pytest.mark.unit
    @pytest.mark.parametrize("value", ["0.5", None, {}, []])
    def test_non_numeric_becomes_none(self, value: object) -> None:
        """A shape change on the provider side yields null, not a crash."""
        assert _finite_or_none(value) is None

    @pytest.mark.unit
    def test_bool_is_not_treated_as_a_score(self) -> None:
        """bool is a subclass of int; a flag must not be recorded as a score."""
        flag: object = True
        assert _finite_or_none(flag) is None


class TestCorpusItemTexts:
    """All three corpus text shapes reach Stage 0, so all three are captured."""

    @pytest.mark.unit
    def test_passage_item_yields_one_unsuffixed_text(self) -> None:
        """A plain passage item contributes exactly one unit with no id suffix."""
        assert _corpus_item_texts({"passage": "hello world"}) == [("", "hello world")]

    @pytest.mark.unit
    def test_payload_item_yields_payload_suffix(self) -> None:
        """A brief-injection payload is captured and marked as such."""
        assert _corpus_item_texts({"payload": "ignore prior"}) == [
            ("#payload", "ignore prior")
        ]

    @pytest.mark.unit
    def test_nodes_item_yields_one_unit_per_body(self) -> None:
        """Aggregate items contribute each node body separately."""
        item = {
            "nodes": [{"id": "n1", "body": "first"}, {"id": "n2", "body": "second"}]
        }
        assert _corpus_item_texts(item) == [("#n1", "first"), ("#n2", "second")]

    @pytest.mark.unit
    def test_node_without_id_falls_back_to_positional_suffix(self) -> None:
        """A body with no node id still gets a stable, unique suffix."""
        assert _corpus_item_texts({"nodes": [{"body": "only"}]}) == [("#node0", "only")]

    @pytest.mark.unit
    def test_textless_item_yields_nothing(self) -> None:
        """Structural-bypass items (class D) carry no prose and are skipped."""
        assert _corpus_item_texts({"target": "import", "executable": False}) == []

    @pytest.mark.unit
    def test_blank_passage_is_not_captured(self) -> None:
        """Whitespace-only text is not a scorable passage."""
        assert _corpus_item_texts({"passage": "   "}) == []


class TestLoadAdversarialPassages:
    """The real corpus must load without silently dropping scorable text."""

    @pytest.mark.unit
    def test_every_text_bearing_corpus_item_is_represented(self) -> None:
        """Each corpus item carrying prose contributes at least one passage."""
        passages = _load_adversarial_passages(_CORPUS)
        items = json.loads(_CORPUS.read_text(encoding="utf-8"))["items"]
        expected_ids = {
            item["id"]
            for item in items
            if item.get("passage") or item.get("payload") or item.get("nodes")
        }
        covered = {p.id.split("#")[0] for p in passages}
        assert covered == expected_ids

    @pytest.mark.unit
    def test_passage_ids_are_unique(self) -> None:
        """Duplicate ids would silently overwrite rows in a comparison run."""
        passages = _load_adversarial_passages(_CORPUS)
        ids = [p.id for p in passages]
        assert len(ids) == len(set(ids))

    @pytest.mark.unit
    def test_all_passages_are_labelled_adversarial(self) -> None:
        """Population labelling drives positive/negative split downstream."""
        passages = _load_adversarial_passages(_CORPUS)
        assert passages
        assert all(p.population == "adversarial" for p in passages)

    @pytest.mark.unit
    def test_text_digest_tracks_the_scored_text(self) -> None:
        """The digest must be of the exact text sent, so drift is detectable."""
        import hashlib

        passage = _load_adversarial_passages(_CORPUS)[0]
        expected = hashlib.sha256(passage.text.encode("utf-8")).hexdigest()
        assert passage.text_sha256 == expected


class TestLoadCleanPassages:
    """The clean sample must be reproducible across runs."""

    @pytest.fixture
    def filled_dir(self, tmp_path: Path) -> Path:
        """Write a directory of synthetic filled storybooks."""
        for book in range(4):
            nodes = [
                {
                    "id": f"n{node}",
                    "body": f"Clean prose for book {book} node {node}. "
                    + "The lantern swung gently over the quiet harbour water. " * 3,
                }
                for node in range(5)
            ]
            (tmp_path / f"book{book}.filled.json").write_text(
                json.dumps({"id": f"book{book}", "nodes": nodes}), encoding="utf-8"
            )
        return tmp_path

    @pytest.mark.unit
    def test_same_seed_selects_the_same_passages(self, filled_dir: Path) -> None:
        """A later comparison run must score the identical passage set."""
        first = _load_clean_passages(filled_dir, limit=7, seed=99)
        second = _load_clean_passages(filled_dir, limit=7, seed=99)
        assert [p.id for p in first] == [p.id for p in second]

    @pytest.mark.unit
    def test_limit_is_respected(self, filled_dir: Path) -> None:
        """The sample never exceeds the requested cap."""
        assert len(_load_clean_passages(filled_dir, limit=7, seed=99)) == 7

    @pytest.mark.unit
    def test_limit_above_population_returns_everything(self, filled_dir: Path) -> None:
        """A cap larger than the corpus returns every candidate, not a crash."""
        assert len(_load_clean_passages(filled_dir, limit=500, seed=99)) == 20

    @pytest.mark.unit
    def test_unfilled_skeleton_directives_are_excluded(self, tmp_path: Path) -> None:
        """<<FILL>> directives would baseline directive syntax, not prose."""
        (tmp_path / "skeleton.filled.json").write_text(
            json.dumps(
                {
                    "id": "s",
                    "nodes": [{"id": "n1", "body": "<<FILL body>> " + "x" * 200}],
                }
            ),
            encoding="utf-8",
        )
        assert _load_clean_passages(tmp_path, limit=10, seed=1) == []

    @pytest.mark.unit
    def test_short_bodies_are_excluded(self, tmp_path: Path) -> None:
        """Trivially short text carries no calibration signal."""
        (tmp_path / "short.filled.json").write_text(
            json.dumps({"id": "s", "nodes": [{"id": "n1", "body": "Too short."}]}),
            encoding="utf-8",
        )
        assert _load_clean_passages(tmp_path, limit=10, seed=1) == []

    @pytest.mark.unit
    def test_unreadable_book_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        """One corrupt file must not abort the whole clean sample."""
        (tmp_path / "bad.filled.json").write_text("{not json", encoding="utf-8")
        assert _load_clean_passages(tmp_path, limit=10, seed=1) == []


class TestArtifact:
    """The artifact must always be writable under allow_nan=False."""

    @staticmethod
    def _record(**overrides: object) -> PassageScores:
        """Build a PassageScores with sensible defaults."""
        base = PassageScores(
            passage_id="p1",
            population="adversarial",
            source_ref="corpus#p1",
            text_sha256="deadbeef",
            text="some text",
            expected_min_verdict="flag",
            taxonomy_class="A",
        )
        for key, value in overrides.items():
            setattr(base, key, value)
        return base

    @pytest.mark.unit
    def test_artifact_with_null_scores_serializes_strictly(self) -> None:
        """A null score (from a non-finite value) must not break the write."""
        record = self._record(perspective={"TOXICITY": None, "THREAT": 0.3})
        artifact = _build_artifact(
            [record], captured_at="2026-07-28T00:00:00+00:00", counts={}
        )
        # allow_nan=False is what the script writes with; if a NaN ever survived
        # into the artifact this call is where it would surface.
        encoded = json.dumps(artifact, allow_nan=False)
        assert '"TOXICITY": null' in encoded

    @pytest.mark.unit
    def test_summarize_counts_failures_separately(self) -> None:
        """Failed calls are counted, never folded into the success total."""
        records = [
            self._record(perspective={"TOXICITY": 0.1}),
            self._record(perspective_error="429 Too Many Requests"),
            self._record(openai_scores={"violence": 0.2}),
        ]
        counts = _summarize(records)
        assert counts["passages"] == 3
        assert counts["perspective_ok"] == 1
        assert counts["perspective_failed"] == 1
        assert counts["openai_ok"] == 1

    @pytest.mark.unit
    def test_artifact_records_the_probe_definition(self) -> None:
        """The artifact self-describes what was probed, for later comparison."""
        from cyo_adventure.moderation.classifiers import PERSPECTIVE_ATTRIBUTES

        artifact = _build_artifact(
            [], captured_at="2026-07-28T00:00:00+00:00", counts={}
        )
        probe = artifact["probe"]
        assert isinstance(probe, dict)
        assert probe["perspective_attributes"] == list(PERSPECTIVE_ATTRIBUTES)
