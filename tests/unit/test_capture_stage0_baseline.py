# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Unit tests for the Stage-0 baseline capture script's pure logic.

No test here makes a real network call: the provider paths are driven through a
fake async client so every malformed-payload shape can be pinned. What is tested
is everything that decides *which* text gets scored, whether a screen counts as
captured, and whether the resulting artifact is writable, because a silent
parsing or accounting bug would produce a baseline that looks complete and
calibrates the wrong thing.
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.moderation.classifiers import PERSPECTIVE_URL
from scripts.capture_stage0_baseline import (
    _OPENAI_URL,  # pyright: ignore[reportPrivateUsage]
    MalformedProviderResponseError,
    Passage,
    PassageScores,
    RunContext,
    _build_artifact,  # pyright: ignore[reportPrivateUsage]
    _corpus_item_texts,  # pyright: ignore[reportPrivateUsage]
    _coverage_shortfalls,  # pyright: ignore[reportPrivateUsage]
    _finite_or_none,  # pyright: ignore[reportPrivateUsage]
    _git_commit,  # pyright: ignore[reportPrivateUsage]
    _load_adversarial_passages,  # pyright: ignore[reportPrivateUsage]
    _load_clean_passages,  # pyright: ignore[reportPrivateUsage]
    _score_passage,  # pyright: ignore[reportPrivateUsage]
    _summarize,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    import httpx

_CORPUS = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "planning"
    / "safety"
    / "adversarial-corpus.json"
)

# A well-formed 200 from each provider, used as the "this one worked" arm of the
# accounting tests.
_GOOD_PERSPECTIVE = {
    "attributeScores": {"TOXICITY": {"summaryScore": {"value": 0.0004}}}
}
_GOOD_OPENAI = {
    "results": [
        {"category_scores": {"violence": 0.001}, "categories": {"violence": False}}
    ]
}


class _FakeResponse:
    """A 200 response carrying a chosen JSON body."""

    def __init__(self, body: object) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        """A 200 has nothing to raise; the defects under test are body-shaped."""

    def json(self) -> object:
        """Return the canned body."""
        return self._body


class _FakeClient:
    """Async client stand-in that answers each POST from a per-URL body table.

    Records every URL it was asked for, so a test can assert that a provider was
    never contacted at all (which is the whole point of the PII guard).
    """

    def __init__(self, bodies: dict[str, object]) -> None:
        self._bodies = bodies
        self.urls: list[str] = []

    async def post(self, url: str, **_kwargs: object) -> _FakeResponse:
        """Record the URL and answer with its canned body."""
        self.urls.append(url)
        return _FakeResponse(self._bodies[url])


def _as_client(fake: _FakeClient) -> httpx.AsyncClient:
    """Present the fake where an ``httpx.AsyncClient`` is annotated."""
    return cast("httpx.AsyncClient", fake)


def _passage(passage_id: str = "p1", *, text: str = "Ordinary clean prose.") -> Passage:
    """Build a minimal clean passage carrying no PII."""
    return Passage(
        id=passage_id, population="clean", text=text, source_ref=f"book#{passage_id}"
    )


def _pii_control() -> Passage:
    """Return the corpus's own PII positive control, loaded from the real corpus."""
    return next(
        p
        for p in _load_adversarial_passages(_CORPUS)
        if p.id.startswith("F1-pii-positive-control")
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
    def test_negative_control_is_not_labelled_adversarial(self) -> None:
        """A true negative in the positive population would flatten separation."""
        by_id = {p.id: p for p in _load_adversarial_passages(_CORPUS)}
        control = by_id["A4-control-onband-8-11"]
        assert control.negative_control is True
        assert control.population == "control"
        assert by_id["A1-roof-flight-3-5"].population == "adversarial"

    @pytest.mark.unit
    def test_corpus_classification_fields_are_carried_through(self) -> None:
        """Dropping these forced a comparison run to reverse-engineer them."""
        by_id = {p.id: p for p in _load_adversarial_passages(_CORPUS)}
        aggregate = by_id["C1-aggregate-fire-8-11#n1"]
        assert aggregate.known_gap is True
        assert aggregate.age_band == "8-11"
        assert aggregate.target_stage == "aggregate"
        assert aggregate.taxonomy_class == "C"
        assert by_id["A1-roof-flight-3-5"].target_stage == 1

    @pytest.mark.unit
    def test_pii_control_carries_its_expected_outcome_and_seeded_name(self) -> None:
        """F1's only stated outcome is ``expected``; it has no min verdict at all."""
        control = _pii_control()
        assert control.expected == "raise_before_egress"
        assert control.expected_min_verdict is None
        assert control.pii_child_names == ("Aabria",)

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

    @pytest.mark.unit
    def test_unconfigured_provider_is_not_advertised_as_probed(self) -> None:
        """An absent key must read as "not probed", not as a silent zero."""
        artifact = _build_artifact(
            [],
            captured_at="2026-07-28T00:00:00+00:00",
            counts={},
            run=_run_context(openai_configured=False),
        )
        probe = artifact["probe"]
        assert isinstance(probe, dict)
        assert probe["perspective_configured"] is True
        assert probe["openai_configured"] is False


def _run_context(*, openai_configured: bool = True) -> RunContext:
    """Build a RunContext with values a reproduction test can assert on."""
    return RunContext(
        corpus_path="docs/planning/safety/adversarial-corpus.json",
        corpus_sha256="c0ffee",
        filled_dir="out",
        clean_limit=120,
        seed=20261231,
        qps=1.0,
        git_commit="0123456789abcdef",
        perspective_configured=True,
        openai_configured=openai_configured,
    )


class TestReproduction:
    """A baseline that cannot be reconstructed cannot be compared against."""

    @pytest.mark.unit
    def test_artifact_records_every_reproduction_input(self) -> None:
        """Seed, sample cap, corpus digest, and commit pin what was scored."""
        artifact = _build_artifact(
            [],
            captured_at="2026-07-28T00:00:00+00:00",
            counts={},
            run=_run_context(),
        )
        reproduction = artifact["reproduction"]
        assert isinstance(reproduction, dict)
        assert reproduction["seed"] == 20261231
        assert reproduction["clean_limit"] == 120
        assert reproduction["corpus_sha256"] == "c0ffee"
        assert reproduction["corpus_path"].endswith("adversarial-corpus.json")
        assert reproduction["git_commit"] == "0123456789abcdef"

    @pytest.mark.unit
    def test_artifact_stays_json_strict_with_a_run_block(self) -> None:
        """The script writes with allow_nan=False and sort_keys=True."""
        artifact = _build_artifact(
            [],
            captured_at="2026-07-28T00:00:00+00:00",
            counts={},
            run=_run_context(),
        )
        assert json.dumps(artifact, sort_keys=True, allow_nan=False)

    @pytest.mark.unit
    def test_git_commit_is_null_when_git_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing git must not abort a capture that already spent quota."""

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise OSError(2, "No such file or directory: 'git'")

        monkeypatch.setattr(subprocess, "run", _boom)
        assert _git_commit() is None


class TestDecisionBoundary:
    """Raw scores are meaningless without the boundary they are read against."""

    @pytest.mark.unit
    def test_artifact_records_the_stage0_thresholds(self) -> None:
        """The floor and the bright lines define what a score would have done."""
        from cyo_adventure.moderation.classifiers import (
            _ADVISORY_SCORE_FLOOR,  # pyright: ignore[reportPrivateUsage]
        )

        artifact = _build_artifact(
            [], captured_at="2026-07-28T00:00:00+00:00", counts={}
        )
        boundary = artifact["decision_boundary"]
        assert isinstance(boundary, dict)
        assert boundary["advisory_score_floor"] == _ADVISORY_SCORE_FLOOR
        assert "sexual/minors" in boundary["openai_brightline_categories"]


class TestProviderPayloads:
    """A 200 carrying no score is a failed screen, never a captured one."""

    @staticmethod
    async def _record_for(
        perspective_body: object, openai_body: object
    ) -> PassageScores:
        """Score one clean passage against a fake client with canned bodies."""
        client = _FakeClient(
            {PERSPECTIVE_URL: perspective_body, _OPENAI_URL: openai_body}
        )
        return await _score_passage(
            _passage(),
            perspective_key="k",
            openai_key="k",
            client=_as_client(client),
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("body", "label"),
        [
            ({}, "empty object"),
            ({"error": {"code": 429, "message": "Quota exceeded"}}, "error-shaped"),
            ({"attributeScores": None}, "null attributeScores"),
            ([], "non-object body"),
            (
                {"attributeScores": {"TOXICITY": {"summaryScore": {"value": "nope"}}}},
                "no finite score",
            ),
        ],
    )
    async def test_perspective_malformed_body_is_recorded_as_a_failure(
        self, body: object, label: str
    ) -> None:
        """Each shape previously returned a truthy all-null dict counted as OK."""
        record = await self._record_for(body, _GOOD_OPENAI)
        assert record.perspective_error is not None, label
        assert record.perspective == {}
        assert _summarize([record])["perspective_ok"] == 0
        assert _summarize([record])["perspective_failed"] == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_perspective_error_shaped_body_is_recorded_as_a_failure(self) -> None:
        """A throttled 200 must not read as a clean screen."""
        record = await self._record_for(
            {"error": {"code": 429, "message": "Quota exceeded"}}, _GOOD_OPENAI
        )
        assert record.perspective_error is not None
        assert "attributeScores" in record.perspective_error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_perspective_null_attribute_scores_is_recorded_as_a_failure(
        self,
    ) -> None:
        """A post-sunset stub body must not write 300 empty rows as complete."""
        record = await self._record_for({"attributeScores": None}, _GOOD_OPENAI)
        assert record.perspective_error is not None
        assert record.perspective == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("body", "label"),
        [
            ({}, "no results key"),
            ({"results": []}, "empty results"),
            ({"results": [[]]}, "non-object result"),
            ({"results": [{"categories": {"violence": False}}]}, "no category_scores"),
            ({"results": [{"category_scores": {"violence": None}}]}, "no finite score"),
            ("not an object", "non-object body"),
        ],
    )
    async def test_openai_malformed_body_is_recorded_as_a_failure(
        self, body: object, label: str
    ) -> None:
        """Each shape previously landed in neither bucket, silently."""
        record = await self._record_for(_GOOD_PERSPECTIVE, body)
        assert record.openai_error is not None, label
        assert record.openai_scores == {}
        counts = _summarize([record])
        assert counts["openai_ok"] == 0
        assert counts["openai_failed"] == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_openai_empty_results_is_recorded_as_a_failure(self) -> None:
        """The named case from the review, pinned on its own."""
        record = await self._record_for(_GOOD_PERSPECTIVE, {"results": []})
        assert record.openai_error is not None
        assert "results" in record.openai_error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_well_formed_bodies_are_recorded_as_captured(self) -> None:
        """The success path still works, and requires an actual score."""
        record = await self._record_for(_GOOD_PERSPECTIVE, _GOOD_OPENAI)
        assert record.perspective_error is None
        assert record.openai_error is None
        assert record.perspective["TOXICITY"] == pytest.approx(0.0004)
        assert record.openai_scores["violence"] == pytest.approx(0.001)

    @pytest.mark.unit
    def test_malformed_response_is_a_value_error(self) -> None:
        """It must ride the same per-passage failure path as a decode error."""
        assert issubclass(MalformedProviderResponseError, ValueError)


class TestPiiGuard:
    """Production screens for PII before Stage 0; so must this capture."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pii_positive_control_is_blocked_before_any_provider_call(
        self,
    ) -> None:
        """F1's whole purpose is to raise before egress; scoring it defeats it."""
        client = _FakeClient(
            {PERSPECTIVE_URL: _GOOD_PERSPECTIVE, _OPENAI_URL: _GOOD_OPENAI}
        )
        record = await _score_passage(
            _pii_control(),
            perspective_key="k",
            openai_key="k",
            client=_as_client(client),
        )
        assert record.pii_blocked is True
        # The load-bearing assertion: neither provider was contacted at all.
        assert client.urls == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pii_blocked_passage_records_no_scores_and_no_errors(self) -> None:
        """A block is its own outcome: not a success, and not a failure."""
        client = _FakeClient(
            {PERSPECTIVE_URL: _GOOD_PERSPECTIVE, _OPENAI_URL: _GOOD_OPENAI}
        )
        record = await _score_passage(
            _pii_control(),
            perspective_key="k",
            openai_key="k",
            client=_as_client(client),
        )
        assert record.perspective == {}
        assert record.openai_scores == {}
        assert record.perspective_error is None
        assert record.openai_error is None
        counts = _summarize([record])
        assert counts["pii_blocked"] == 1
        assert counts["perspective_ok"] == 0
        assert counts["perspective_failed"] == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_clean_passage_is_not_blocked(self) -> None:
        """The guard must not suppress the population it exists to measure."""
        client = _FakeClient(
            {PERSPECTIVE_URL: _GOOD_PERSPECTIVE, _OPENAI_URL: _GOOD_OPENAI}
        )
        record = await _score_passage(
            _passage(text="The lantern swung over the quiet harbour water."),
            perspective_key="k",
            openai_key="k",
            client=_as_client(client),
        )
        assert record.pii_blocked is False
        assert client.urls == [PERSPECTIVE_URL, _OPENAI_URL]


class TestSummaryAccounting:
    """Every passage must be accounted for, or "complete" is a claim about nothing."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_provider_buckets_account_for_every_passage(self) -> None:
        """ok + failed + pii_blocked == passages, for each configured provider."""
        good = {PERSPECTIVE_URL: _GOOD_PERSPECTIVE, _OPENAI_URL: _GOOD_OPENAI}
        bad = {
            PERSPECTIVE_URL: {"error": {"code": 429}},
            _OPENAI_URL: {"results": []},
        }
        records = [
            await _score_passage(
                _passage("ok"),
                perspective_key="k",
                openai_key="k",
                client=_as_client(_FakeClient(good)),
            ),
            await _score_passage(
                _passage("bad"),
                perspective_key="k",
                openai_key="k",
                client=_as_client(_FakeClient(bad)),
            ),
            await _score_passage(
                _pii_control(),
                perspective_key="k",
                openai_key="k",
                client=_as_client(_FakeClient(good)),
            ),
        ]
        counts = _summarize(records)
        assert counts["passages"] == 3
        assert counts["pii_blocked"] == 1
        for provider in ("perspective", "openai"):
            assert (
                counts[f"{provider}_ok"]
                + counts[f"{provider}_failed"]
                + counts["pii_blocked"]
                == counts["passages"]
            ), provider

    @pytest.mark.unit
    def test_population_split_is_recorded_in_counts(self) -> None:
        """A separation statistic needs the split without reverse-engineering it."""
        records = [
            PassageScores(
                passage_id=str(index),
                population=population,
                source_ref="ref",
                text_sha256="d",
                text="t",
                expected_min_verdict=None,
                taxonomy_class=None,
            )
            for index, population in enumerate(
                ["adversarial", "adversarial", "control", "clean"]
            )
        ]
        counts = _summarize(records)
        assert counts["adversarial"] == 2
        assert counts["control"] == 1
        assert counts["clean"] == 1


class TestCoverageGate:
    """A partial capture must not exit 0; the pre-sunset window closes once."""

    @staticmethod
    def _counts(**overrides: int) -> dict[str, int]:
        """Build a fully-covered 10-passage count map, then apply overrides."""
        base = {
            "passages": 10,
            "pii_blocked": 0,
            "adversarial": 10,
            "control": 0,
            "clean": 0,
            "perspective_ok": 10,
            "perspective_failed": 0,
            "openai_ok": 10,
            "openai_failed": 0,
        }
        base.update(overrides)
        return base

    @pytest.mark.unit
    def test_complete_capture_reports_no_shortfall(self) -> None:
        """A clean run must still exit 0."""
        assert _coverage_shortfalls(self._counts(), openai_configured=True) == []

    @pytest.mark.unit
    def test_pii_blocked_passages_do_not_count_against_coverage(self) -> None:
        """A blocked passage is a recorded outcome, not a missing screen."""
        counts = self._counts(pii_blocked=1, perspective_ok=9, openai_ok=9)
        assert _coverage_shortfalls(counts, openai_configured=True) == []

    @pytest.mark.unit
    def test_any_provider_failure_is_a_shortfall(self) -> None:
        """The 429 case the original code warned about but exited 0 on."""
        counts = self._counts(perspective_ok=9, perspective_failed=1)
        assert _coverage_shortfalls(counts, openai_configured=True)

    @pytest.mark.unit
    def test_silently_uncounted_passages_are_a_shortfall(self) -> None:
        """Neither-bucket records leave coverage short even with zero errors."""
        counts = self._counts(openai_ok=4)
        assert _coverage_shortfalls(counts, openai_configured=True)

    @pytest.mark.unit
    def test_unconfigured_openai_is_not_a_shortfall(self) -> None:
        """An absent provider is a declared gap, not a partial capture."""
        counts = self._counts(openai_ok=0)
        assert _coverage_shortfalls(counts, openai_configured=False) == []
