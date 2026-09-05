"""Unit tests for the two-model comprehension probe (C1).

The probe's value depends entirely on guards that are easy to get quietly
wrong: a spend cap that never actually binds, a truncated reply that gets
misread as a malformed one, and a ``<<FILL ...>>`` skeleton node that gets
scored as if it were prose. Each of those failure modes produces a plausible
number, which is exactly what makes them worth pinning down with tests rather
than trusting by inspection.

No test here makes a network call: every provider is
:class:`~cyo_adventure.generation.provider.MockProvider`.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.machinery
import importlib.util
import inspect
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.core.pricing import estimate_cost, price_for
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.generation.usage import Completion, TokenUsage
from scripts import comprehension_probe
from scripts.comprehension_probe import (
    _ANSWER_MODEL,  # pyright: ignore[reportPrivateUsage]
    _PROVIDER,  # pyright: ignore[reportPrivateUsage]
    _QUESTION_MODEL,  # pyright: ignore[reportPrivateUsage]
    _REPO_ROOT,  # pyright: ignore[reportPrivateUsage]
    _SAMPLING_STRATEGY,  # pyright: ignore[reportPrivateUsage]
    AnswerRecord,
    BudgetTracker,
    CorpusStats,
    NodeResult,
    Passage,
    ProbeParseError,
    ProbeSummary,
    UnaccountableSpendError,
    _ensure_gitignored_destination,  # pyright: ignore[reportPrivateUsage]
    _ensure_models_are_priced,  # pyright: ignore[reportPrivateUsage]
    _extract_answers,  # pyright: ignore[reportPrivateUsage]
    _extract_questions,  # pyright: ignore[reportPrivateUsage]
    _parse_json_object,  # pyright: ignore[reportPrivateUsage]
    _validate_model_pair,  # pyright: ignore[reportPrivateUsage]
    collect_passages,
    main,
    probe_passage,
    run_probe,
    summarize,
    write_tracked_aggregate,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import CodeType

# Real, priced (provider, model) pairs from core/pricing.py, so cost math in
# these tests exercises the same price table a live run would, instead of a
# fixture price that could drift from it unnoticed.
_QUESTION_PAIR = ("openrouter", "google/gemini-2.5-flash")
_ANSWER_PAIR = ("openrouter", "deepseek/deepseek-v4-flash")


class _RewrittenSourceLoader(importlib.machinery.SourceFileLoader):
    """Import a module from a pre-rewritten AST rather than from its file.

    ``get_code`` is overridden rather than ``source_to_code`` so no
    ``__pycache__`` entry can short-circuit the rewrite and quietly import the
    unmodified module, which would turn an import-wiring test into a test that
    always passes.
    """

    def __init__(self, fullname: str, path: str, tree: ast.Module) -> None:
        super().__init__(fullname, path)
        self._tree = tree

    def get_code(self, fullname: str) -> CodeType:
        """Return the rewritten module code, ignoring source and cache alike."""
        return compile(self._tree, self.path, "exec")


def _completion(
    text: str,
    *,
    provider: str = "mock",
    model: str = "mock",
    input_tokens: int | None = 200,
    output_tokens: int | None = 60,
    finish_reason: str | None = "stop",
    vendor_cost_usd: Decimal | None = None,
) -> Completion:
    """Wrap text as a provider would, with a costable usage record by default."""
    return Completion(
        text=text,
        usage=TokenUsage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=5,
        ),
        finish_reason=finish_reason,
        vendor_cost_usd=vendor_cost_usd,
    )


def _questions_json(questions: list[str] | None = None) -> str:
    q = questions or [
        "What happened?",
        "Why did it happen?",
        "What should the reader remember?",
    ]
    return json.dumps({"questions": q})


def _answers_json(can_answer: list[bool]) -> str:
    return json.dumps(
        {
            "answers": [
                {
                    "question": f"q{i}",
                    "can_answer": ok,
                    "answer": "" if not ok else "an answer",
                    "reason": "",
                }
                for i, ok in enumerate(can_answer)
            ]
        }
    )


class TestParseJsonObject:
    """The truncation-versus-malformed-JSON distinction (recon trap 2)."""

    def test_a_complete_valid_reply_parses(self) -> None:
        completion = _completion(_questions_json())
        payload = _parse_json_object(completion)
        assert payload["questions"] == [
            "What happened?",
            "Why did it happen?",
            "What should the reader remember?",
        ]

    def test_finish_reason_length_with_unclosed_json_is_truncated_not_malformed(
        self,
    ) -> None:
        # Cut off mid-object: the greedy regex has nothing to match at all
        # because the object never even opens a closing brace's worth of text
        # after the outer `{`.
        cut_off = '{"questions": ["What happened'
        completion = _completion(cut_off, finish_reason="length")
        with pytest.raises(ProbeParseError) as exc_info:
            _parse_json_object(completion)
        assert exc_info.value.kind == "truncated"

    def test_finish_reason_length_with_unbalanced_json_is_truncated_not_malformed(
        self,
    ) -> None:
        # This is AL-329's exact shape: the regex's greedy `.*` still matches
        # (closing on the last inner brace the reply managed to emit), so
        # json.loads fails on an unbalanced object. Without checking
        # finish_reason first this reads as "the model emitted garbage",
        # which is the wrong diagnosis and the wrong fix.
        #
        # This fixture does not, on its own, prove finish_reason is what
        # reached that verdict: the closing-brace fallback agrees with it
        # here. The two `..._is_what_decides_...` tests below carry that
        # proof, one per decision point, on fixtures where the fallback
        # disagrees.
        truncated_mid_entry = '{"questions": ["What happened?", "Why did it'
        completion = _completion(truncated_mid_entry, finish_reason="length")
        with pytest.raises(ProbeParseError) as exc_info:
            _parse_json_object(completion)
        assert exc_info.value.kind == "truncated"

    def test_finish_reason_is_what_decides_a_prose_prefixed_cut_off_reply(
        self,
    ) -> None:
        """The no-JSON-match branch, on a fixture where the fallback disagrees.

        Both arms of ``truncated_signal or raw.lstrip().startswith("{")`` reach
        "truncated" whenever the reply's first character is the object's ``{``,
        so a fixture of that shape cannot tell a working signal from a deleted
        one. Here a prose preamble and a ```json fence precede the object, so
        ``lstrip().startswith("{")`` is False and the fallback reaches
        "malformed" by itself. Only ``finish_reason == "length"`` reaches
        "truncated", and the paired call proves the fallback still governs when
        the provider reports no finish_reason at all.

        The shape is the commonest real one: a provider that narrates before it
        emits JSON and is then cut off mid-object.
        """
        fenced = 'Here are the questions:\n```json\n{"questions": ["What happened'
        signalled = _completion(fenced, finish_reason="length")
        unsignalled = _completion(fenced, finish_reason=None)
        with pytest.raises(ProbeParseError) as truncated:
            _parse_json_object(signalled)
        assert truncated.value.kind == "truncated"
        with pytest.raises(ProbeParseError) as malformed:
            _parse_json_object(unsignalled)
        assert malformed.value.kind == "malformed"

    def test_finish_reason_is_what_decides_a_reply_ending_on_an_inner_brace(
        self,
    ) -> None:
        """The decode-error branch, on a fixture where the fallback disagrees.

        ``truncated_signal or not raw.rstrip().endswith("}")`` has the same
        weakness one branch down: a cut-off reply that happens to stop just
        after an *inner* object's closing brace does end in ``}``, so the
        fallback reaches "malformed" and only the finish_reason reaches
        "truncated". Without this pair the whole signal is deletable here with
        the suite green, and every such run is filed as
        ``question_generation:malformed``, routing the operator to tighten the
        prompt instead of raising the completion token budget.
        """
        ends_on_inner_brace = '{"questions": [{"q": "What happened?"}'
        signalled = _completion(ends_on_inner_brace, finish_reason="length")
        unsignalled = _completion(ends_on_inner_brace, finish_reason=None)
        with pytest.raises(ProbeParseError) as truncated:
            _parse_json_object(signalled)
        assert truncated.value.kind == "truncated"
        with pytest.raises(ProbeParseError) as malformed:
            _parse_json_object(unsignalled)
        assert malformed.value.kind == "malformed"

    def test_a_complete_reply_with_invalid_json_is_malformed_not_truncated(
        self,
    ) -> None:
        # Ends in a closing brace and finish_reason is "stop": the model
        # finished, and what it finished with just is not valid JSON.
        completion = _completion('{"questions": [1, 2, 3]}}', finish_reason="stop")
        with pytest.raises(ProbeParseError) as exc_info:
            _parse_json_object(completion)
        assert exc_info.value.kind == "malformed"

    def test_no_finish_reason_falls_back_to_the_closing_brace_heuristic(self) -> None:
        # No finish_reason reported at all: falls back to judge_books.py's
        # heuristic (did the reply end in a closing brace).
        completion = _completion('{"questions": ["a", "b"', finish_reason=None)
        with pytest.raises(ProbeParseError) as exc_info:
            _parse_json_object(completion)
        assert exc_info.value.kind == "truncated"

    def test_no_json_object_at_all_is_malformed(self) -> None:
        completion = _completion("I cannot help with that.", finish_reason="stop")
        with pytest.raises(ProbeParseError) as exc_info:
            _parse_json_object(completion)
        assert exc_info.value.kind == "malformed"


class TestExtractQuestions:
    def test_exactly_three_nonempty_strings_is_accepted(self) -> None:
        payload = {"questions": ["a?", "b?", "c?"]}
        assert _extract_questions(payload) == ["a?", "b?", "c?"]

    def test_wrong_count_is_malformed(self) -> None:
        with pytest.raises(ProbeParseError) as exc_info:
            _extract_questions({"questions": ["a?", "b?"]})
        assert exc_info.value.kind == "malformed"

    def test_a_blank_question_is_malformed(self) -> None:
        with pytest.raises(ProbeParseError):
            _extract_questions({"questions": ["a?", "  ", "c?"]})


class TestExtractAnswers:
    def test_matching_count_and_shape_is_accepted(self) -> None:
        payload = json.loads(_answers_json([True, False, True]))
        records = _extract_answers(payload, questions=["q1", "q2", "q3"])
        assert [r.can_answer for r in records] == [True, False, True]
        assert records[0].question == "q1"

    def test_mismatched_count_is_malformed(self) -> None:
        payload = json.loads(_answers_json([True, False]))
        with pytest.raises(ProbeParseError) as exc_info:
            _extract_answers(payload, questions=["q1", "q2", "q3"])
        assert exc_info.value.kind == "malformed"

    def test_missing_can_answer_key_is_malformed(self) -> None:
        payload = {"answers": [{"question": "q1", "answer": "x"}]}
        with pytest.raises(ProbeParseError):
            _extract_answers(payload, questions=["q1"])


class TestFillDirectiveHandling:
    """A <<FILL ...>> node is not a passage (recon trap 4)."""

    def _write_story(
        self, tmp_path: Path, name: str, nodes: list[dict[str, object]]
    ) -> None:
        doc = {
            "id": name,
            "metadata": {"age_band": "5-8"},
            "nodes": nodes,
        }
        (tmp_path / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")

    def test_fill_and_empty_nodes_are_excluded_and_counted(
        self, tmp_path: Path
    ) -> None:
        self._write_story(
            tmp_path,
            "story-a",
            [
                {"id": "n1", "body": "<<FILL role=open words=50 beats='x'>>"},
                {"id": "n2", "body": "   "},
                {"id": "n3", "body": "Real prose that a reader can read."},
            ],
        )
        passages, stats = collect_passages(tmp_path, max_passages=60)
        assert [p.node_id for p in passages] == ["n3"]
        assert stats.nodes_seen == 3
        assert stats.nodes_skipped_fill == 1
        assert stats.nodes_skipped_empty == 1
        assert stats.passages_collected == 1

    def test_a_wholly_unfilled_corpus_yields_zero_passages(
        self, tmp_path: Path
    ) -> None:
        # This is the real shape of the committed skeletons/ tree today: every
        # node is a FILL directive. Excluding them correctly means an
        # all-skeleton corpus slice is legitimately empty, not a crash.
        self._write_story(
            tmp_path,
            "story-b",
            [{"id": "n1", "body": "<<FILL role=open words=50 beats='x'>>"}],
        )
        passages, stats = collect_passages(tmp_path, max_passages=60)
        assert passages == []
        assert stats.nodes_skipped_fill == 1
        assert stats.passages_collected == 0

    def test_non_storybook_sidecar_files_are_skipped_not_crashed_on(
        self, tmp_path: Path
    ) -> None:
        # Mirrors skeletons/*.contract.json and *.lineage.json: valid JSON,
        # but no top-level `nodes` list.
        (tmp_path / "story-a.contract.json").write_text(
            json.dumps({"contract_version": 1, "slots": []}), encoding="utf-8"
        )
        self._write_story(
            tmp_path, "story-a", [{"id": "n1", "body": "Real prose here."}]
        )
        passages, stats = collect_passages(tmp_path, max_passages=60)
        assert len(passages) == 1
        assert stats.files_skipped_non_storybook == 1

    def test_age_band_filter_excludes_non_matching_files(self, tmp_path: Path) -> None:
        doc = {
            "id": "s",
            "metadata": {"age_band": "8-11"},
            "nodes": [{"id": "n1", "body": "x."}],
        }
        (tmp_path / "s.json").write_text(json.dumps(doc), encoding="utf-8")
        passages, stats = collect_passages(tmp_path, age_band="5-8", max_passages=60)
        assert passages == []
        assert stats.files_skipped_age_band == 1

    def test_max_passages_caps_the_slice_deterministically(
        self, tmp_path: Path
    ) -> None:
        self._write_story(
            tmp_path,
            "story-c",
            [{"id": f"n{i}", "body": f"Passage number {i}."} for i in range(10)],
        )
        passages, stats = collect_passages(tmp_path, max_passages=3)
        # Deterministic AND strided: the block midpoints of 10 nodes taken 3
        # at a time. ``["n0", "n1", "n2"]`` is what a prefix walk returns, and
        # is the exact figure-narrowing defect this sampler exists to avoid.
        assert [p.node_id for p in passages] == ["n1", "n5", "n8"]
        assert stats.passages_collected == 3


class TestStratification:
    """The cap must be spent ACROSS stories, and ACROSS each story.

    The first pilot's headline ``0.2034`` was reported as an age-band figure
    and was in fact a single-book figure: ``collect_passages`` filled greedily
    from the first file in sorted order and stopped, so all 60 passages came
    from ``sk_backyard_treasure_map`` and 27 of the 31 globbed files were
    never opened. Nothing in the old suite could fail on that, because every
    corpus fixture it used held exactly one story.

    The depth-interleaved fix for that spread the cap over six stories and
    then took node positions 0 to 9 of every one of them, so the second
    pilot's ``0.1954`` was the band's OPENING-PREFIX rate reported as the
    band's rate. Story openings introduce their referents and carry the least
    prior context, so a prefix is not a neutral narrower slice: it is biased
    toward "unanswerable" for a probe that asks whether a passage stands
    alone. Both defects are the same shape, a figure reading broader than the
    slice behind it, so both get a test here.
    """

    def _write_story(
        self, tmp_path: Path, name: str, count: int, *, band: str = "5-8"
    ) -> None:
        doc = {
            "id": name,
            "metadata": {"age_band": band},
            "nodes": [
                {"id": f"{name}-n{i}", "body": f"Prose {i} of {name}."}
                for i in range(count)
            ],
        }
        (tmp_path / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")

    def test_the_cap_is_spent_across_stories_not_down_the_first_one(
        self, tmp_path: Path
    ) -> None:
        # story-a alone could satisfy the cap on its own, which is precisely
        # the corpus shape that produced the single-book pilot.
        self._write_story(tmp_path, "story-a", 20)
        self._write_story(tmp_path, "story-b", 20)
        self._write_story(tmp_path, "story-c", 20)
        passages, stats = collect_passages(tmp_path, max_passages=6)
        assert len(passages) == 6
        assert {p.story_id for p in passages} == {"story-a", "story-b", "story-c"}
        # Round-robin, so the order is one from each in turn, deterministically.
        assert [p.story_id for p in passages] == [
            "story-a",
            "story-b",
            "story-c",
            "story-a",
            "story-b",
            "story-c",
        ]
        assert stats.stories_available == 3
        assert stats.stories_sampled == 3

    def test_a_story_too_short_for_its_share_hands_the_remainder_back(
        self, tmp_path: Path
    ) -> None:
        """A story with fewer nodes than its share must not strand the cap.

        Renamed from ``test_a_short_story_does_not_starve_the_others``, which
        claimed a property it could not discriminate: a greedy walk returns
        the same STORY sequence here, so asserting story ids alone passed
        under the very implementation the class exists to rule out. The
        assertion is on node ids instead, which a greedy prefix walk fails
        (it would return ``b-n0, b-n1, b-n2``).
        """
        self._write_story(tmp_path, "story-a", 1)
        self._write_story(tmp_path, "story-b", 5)
        passages, stats = collect_passages(tmp_path, max_passages=4)
        # story-a can only supply 1 of its 2-passage share, so story-b takes
        # 3, strided across all five of its nodes rather than its first three.
        assert [p.node_id for p in passages] == [
            "story-a-n0",
            "story-b-n0",
            "story-b-n2",
            "story-b-n4",
        ]
        assert stats.stories_available == 2
        assert stats.stories_sampled == 2

    def test_the_slice_spans_each_story_rather_than_its_opening(
        self, tmp_path: Path
    ) -> None:
        """The published figure must be the band's rate, not its openings' rate.

        This is the test that fails if the selection degenerates back to a
        prefix. Under the depth-interleaved sampler it replaces, every
        assertion below is false: that sampler returns positions 0 to 3 of
        each story.
        """
        self._write_story(tmp_path, "story-a", 40)
        self._write_story(tmp_path, "story-b", 40)
        passages, _ = collect_passages(tmp_path, max_passages=8)
        for story in ("story-a", "story-b"):
            positions = [
                int(p.node_id.rsplit("-n", 1)[1])
                for p in passages
                if p.story_id == story
            ]
            assert len(positions) == 4
            assert positions == sorted(positions)
            assert len(set(positions)) == 4
            # Not the opening: the first pick is past the story's first tenth.
            assert positions[0] >= 4
            # And the slice reaches the story's final quarter rather than
            # stopping wherever the per-story share ran out.
            assert positions[-1] >= 30
            # Spanning, not clustered: the picks cover most of the story.
            assert positions[-1] - positions[0] >= 30

    def test_a_story_shorter_than_its_share_contributes_every_node(
        self, tmp_path: Path
    ) -> None:
        """Striding must not silently drop nodes when there is nothing to skip."""
        self._write_story(tmp_path, "story-a", 3)
        passages, stats = collect_passages(tmp_path, max_passages=10)
        assert [p.node_id for p in passages] == [
            "story-a-n0",
            "story-a-n1",
            "story-a-n2",
        ]
        assert stats.passages_collected == 3

    def test_every_matching_file_is_opened_even_once_the_cap_is_reachable(
        self, tmp_path: Path
    ) -> None:
        """``CorpusStats`` must describe the CORPUS, not where the walk stopped.

        The greedy version broke out of the file loop, so ``nodes_seen`` and
        ``files_scanned`` counted only the prefix it had reached. That is the
        same accounting that made the pilot's misdescription invisible.
        """
        self._write_story(tmp_path, "story-a", 10)
        self._write_story(tmp_path, "story-b", 10)
        self._write_story(tmp_path, "story-c", 10)
        passages, stats = collect_passages(tmp_path, max_passages=2)
        assert len(passages) == 2
        assert stats.files_scanned == 3
        assert stats.nodes_seen == 30
        assert stats.passages_collected == 2
        # Available counts every story with an eligible passage; sampled counts
        # only the ones the capped slice actually drew from, so a single-book
        # slice of a six-book corpus is legible in the report itself.
        assert stats.stories_available == 3
        assert stats.stories_sampled == 2

    def test_the_age_band_filter_still_bounds_the_stratified_walk(
        self, tmp_path: Path
    ) -> None:
        self._write_story(tmp_path, "story-a", 5)
        self._write_story(tmp_path, "story-b", 5, band="8-11")
        passages, stats = collect_passages(tmp_path, age_band="5-8", max_passages=10)
        assert {p.story_id for p in passages} == {"story-a"}
        assert stats.files_skipped_age_band == 1
        assert stats.stories_available == 1
        assert stats.stories_sampled == 1


class TestProbePassage:
    """End-to-end passage probing against a mocked two-model split."""

    @staticmethod
    def _passage() -> Passage:
        return Passage(
            story_id="s1",
            story_path="s1.json",
            node_id="n1",
            body="Once there was a fox.",
        )

    def test_a_fully_answerable_passage_reports_no_findings(self) -> None:
        question_provider = MockProvider(
            responses=[_questions_json()],
            token_usage=TokenUsage(
                provider=_QUESTION_PAIR[0],
                model=_QUESTION_PAIR[1],
                input_tokens=200,
                output_tokens=60,
                duration_ms=5,
            ),
        )
        answer_provider = MockProvider(
            responses=[_answers_json([True, True, True])],
            token_usage=TokenUsage(
                provider=_ANSWER_PAIR[0],
                model=_ANSWER_PAIR[1],
                input_tokens=250,
                output_tokens=80,
                duration_ms=5,
            ),
        )
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        result = asyncio.run(
            probe_passage(
                self._passage(),
                question_provider=question_provider,
                answer_provider=answer_provider,
                budget=budget,
            )
        )
        assert result.error_stage is None
        assert result.answers is not None
        assert all(a.can_answer for a in result.answers)
        assert budget.calls == 2
        assert budget.spent_usd > 0

    def test_two_different_models_are_actually_used(self) -> None:
        # The plan is explicit: one model both asking and answering measures
        # nothing. Confirm the two calls really go to different providers.
        question_provider = MockProvider(
            responses=[_questions_json()],
            token_usage=TokenUsage(
                provider=_QUESTION_PAIR[0],
                model=_QUESTION_PAIR[1],
                input_tokens=100,
                output_tokens=40,
                duration_ms=1,
            ),
        )
        answer_provider = MockProvider(
            responses=[_answers_json([False, True, True])],
            token_usage=TokenUsage(
                provider=_ANSWER_PAIR[0],
                model=_ANSWER_PAIR[1],
                input_tokens=100,
                output_tokens=40,
                duration_ms=1,
            ),
        )
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        result = asyncio.run(
            probe_passage(
                self._passage(),
                question_provider=question_provider,
                answer_provider=answer_provider,
                budget=budget,
            )
        )
        assert question_provider.calls  # question leg was called
        assert answer_provider.calls  # a genuinely different leg was called
        assert result.answers is not None
        assert sum(1 for a in result.answers if not a.can_answer) == 1

    def test_malformed_question_reply_skips_the_answer_call_entirely(self) -> None:
        question_provider = MockProvider(
            responses=["not json at all"],
            token_usage=TokenUsage(
                provider=_QUESTION_PAIR[0],
                model=_QUESTION_PAIR[1],
                input_tokens=50,
                output_tokens=10,
                duration_ms=1,
            ),
        )
        answer_provider = MockProvider(responses=["should never be called"])
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        result = asyncio.run(
            probe_passage(
                self._passage(),
                question_provider=question_provider,
                answer_provider=answer_provider,
                budget=budget,
            )
        )
        assert result.error_stage == "question_generation:malformed"
        assert result.answers is None
        assert answer_provider.calls == []
        # Only the question call's cost was posted.
        assert budget.calls == 1


class TestBudgetTracker:
    """The spend cap must actually bind, and must not bind spuriously."""

    def _fixtures(
        self, n: int
    ) -> tuple[list[Passage], Callable[[], MockProvider], Callable[[], MockProvider]]:
        passages = [
            Passage(
                story_id="s", story_path="s.json", node_id=f"n{i}", body=f"Passage {i}."
            )
            for i in range(n)
        ]

        def make_question_provider() -> MockProvider:
            return MockProvider(
                responses=[_questions_json() for _ in range(n)],
                token_usage=TokenUsage(
                    provider=_QUESTION_PAIR[0],
                    model=_QUESTION_PAIR[1],
                    input_tokens=200,
                    output_tokens=60,
                    duration_ms=5,
                ),
            )

        def make_answer_provider() -> MockProvider:
            return MockProvider(
                responses=[_answers_json([False, True, True]) for _ in range(n)],
                token_usage=TokenUsage(
                    provider=_ANSWER_PAIR[0],
                    model=_ANSWER_PAIR[1],
                    input_tokens=250,
                    output_tokens=80,
                    duration_ms=5,
                ),
            )

        return passages, make_question_provider, make_answer_provider

    def test_an_absurdly_low_cap_stops_the_run_after_one_passage(self) -> None:
        passages, make_q, make_a = self._fixtures(5)
        question_provider = make_q()
        answer_provider = make_a()
        # One millionth of a cent: the very first call's real cost (computed
        # from the real price table) exceeds this immediately.
        budget = BudgetTracker(cap_usd=Decimal("0.00000001"))
        results = asyncio.run(
            run_probe(
                passages,
                question_provider=question_provider,
                answer_provider=answer_provider,
                budget=budget,
            )
        )
        assert len(results) == 5
        # Only the first passage could have made any calls at all; everything
        # after it must be a budget skip with zero provider calls attributed
        # to it, which is provable because the providers' response queues
        # were never drained past what the first passage could consume.
        made_calls = [r for r in results if r.error_stage != "budget"]
        assert len(made_calls) <= 1
        budget_skipped = [r for r in results if r.error_stage == "budget"]
        assert len(budget_skipped) >= 4
        # The providers were not called for every passage: proof the cap
        # actually stopped new calls rather than merely being recorded.
        assert len(question_provider.calls) < 5
        assert budget.exhausted is True

    def test_the_real_cap_does_not_fire_on_a_realistic_slice(self) -> None:
        passages, make_q, make_a = self._fixtures(5)
        question_provider = make_q()
        answer_provider = make_a()
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        results = asyncio.run(
            run_probe(
                passages,
                question_provider=question_provider,
                answer_provider=answer_provider,
                budget=budget,
            )
        )
        assert len(results) == 5
        assert all(r.error_stage is None for r in results)
        assert len(question_provider.calls) == 5
        assert len(answer_provider.calls) == 5
        assert budget.exhausted is False
        # Real per-call cost for these tiny fixtures is a small fraction of a
        # cent per node; five nodes should land far under the dollar cap.
        assert budget.spent_usd < Decimal("0.01")

    def test_an_unpriced_call_aborts_the_run_rather_than_costing_zero(self) -> None:
        """An unpriced pair must stop the run, not post $0 and continue.

        This is the exact shape the reviewer demonstrated: 100 calls of 100k
        in / 100k out against a $0.0000001 cap previously reported
        ``SPENT: 0  EXHAUSTED: False``. The assertion is on the RUN stopping,
        not on a counter being incremented, because a counter nothing reads is
        what let the defect through.
        """
        budget = BudgetTracker(cap_usd=Decimal("0.0000001"))
        estimate = estimate_cost(
            price_for(_PROVIDER, "not-a-real-model"), 100_000, 100_000
        )
        assert estimate.complete is False
        assert estimate.amount_usd == Decimal(0)
        with pytest.raises(UnaccountableSpendError, match="cannot bind on it"):
            budget.add(estimate, vendor_cost_usd=None)

    def test_an_unreported_usage_block_aborts_the_run(self) -> None:
        """A vendor that omits ``usage`` is the same hazard by another route.

        ``dig_usage`` yields ``(None, None)`` and ``estimate_cost`` again
        returns a complete-looking ``Decimal(0)``. Exercised through
        ``run_probe`` rather than ``add`` directly, so what is pinned is that
        the RUN dies at the first such call rather than buying 4 more.
        """
        passages, _make_q, make_a = self._fixtures(5)
        question_provider = MockProvider(
            responses=[_questions_json() for _ in range(5)],
            token_usage=TokenUsage(
                provider=_QUESTION_PAIR[0],
                model=_QUESTION_PAIR[1],
                input_tokens=None,
                output_tokens=None,
                duration_ms=5,
            ),
        )
        answer_provider = make_a()
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        coro = run_probe(
            passages,
            question_provider=question_provider,
            answer_provider=answer_provider,
            budget=budget,
        )
        with pytest.raises(UnaccountableSpendError):
            asyncio.run(coro)
        # Died on the first call, not after spending on all five passages.
        assert budget.calls == 1
        assert len(question_provider.calls) == 1
        assert len(answer_provider.calls) == 0

    def test_a_vendor_reported_cost_binds_the_cap_even_when_the_table_is_low(
        self,
    ) -> None:
        """The cap binds on the LARGER of observed and estimated spend.

        A price table that has drifted below the vendor's live rate would
        otherwise let a run overspend by exactly the drift, silently, which is
        the failure mode ``core/pricing.py``'s own docstring warns about.
        """
        budget = BudgetTracker(cap_usd=Decimal("1.00"))
        estimate = estimate_cost(price_for(*_QUESTION_PAIR), 100, 100)
        assert estimate.complete is True
        assert estimate.amount_usd < Decimal("1.00")
        budget.add(estimate, vendor_cost_usd=Decimal("2.50"))
        assert budget.observed_usd == Decimal("2.50")
        assert budget.calls_reporting_vendor_cost == 1
        assert budget.charged_usd == Decimal("2.50")
        assert budget.exhausted is True

    def test_an_unreported_vendor_cost_is_not_counted_as_a_free_call(self) -> None:
        """``None`` means "not reported", never "$0.00"."""
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        estimate = estimate_cost(price_for(*_QUESTION_PAIR), 100, 100)
        budget.add(estimate, vendor_cost_usd=None)
        assert budget.calls == 1
        assert budget.calls_reporting_vendor_cost == 0
        assert budget.observed_usd == Decimal(0)
        # The cap still binds, on the estimate, rather than on nothing.
        assert budget.charged_usd == estimate.amount_usd

    def test_the_mid_passage_guard_stops_before_the_answer_call(self) -> None:
        """A passage whose QUESTION call crosses the cap must not then answer.

        Mutation M5 (``if budget.exhausted:`` -> ``if False:``) previously
        left 30/30 tests passing: the ``budget_after_questions`` path was dead
        in the suite despite ``probe_passage`` documenting it as a deliberate
        guard. The assertion that discriminates is
        ``len(answer_provider.calls) == 0``: under M5 the answer call is made
        and the stage is ``None``.
        """
        question_provider = MockProvider(
            responses=[_questions_json()],
            token_usage=TokenUsage(
                provider=_QUESTION_PAIR[0],
                model=_QUESTION_PAIR[1],
                input_tokens=200,
                output_tokens=60,
                duration_ms=5,
            ),
        )
        answer_provider = MockProvider(
            responses=[_answers_json([True, True, True])],
            token_usage=TokenUsage(
                provider=_ANSWER_PAIR[0],
                model=_ANSWER_PAIR[1],
                input_tokens=250,
                output_tokens=80,
                duration_ms=5,
            ),
        )
        # Not exhausted on entry, so `run_probe`'s outer guard lets the
        # passage start; the question call's own cost is what crosses it.
        budget = BudgetTracker(cap_usd=Decimal("0.00000001"))
        assert budget.exhausted is False
        result = asyncio.run(
            probe_passage(
                Passage(
                    story_id="s",
                    story_path="s.json",
                    node_id="n1",
                    body="Once there was a fox.",
                ),
                question_provider=question_provider,
                answer_provider=answer_provider,
                budget=budget,
            )
        )
        assert result.error_stage == "budget_after_questions"
        assert result.questions is not None
        assert result.answers is None
        assert len(question_provider.calls) == 1
        assert len(answer_provider.calls) == 0
        assert budget.calls == 1


class TestConfiguredModels:
    """The two module constants, checked as constants rather than as fixtures.

    Every test above builds its own ``MockProvider`` pair, so none of them can
    fail when the module's real configuration breaks. Mutation M1 (set
    ``_ANSWER_MODEL = _QUESTION_MODEL``) and M2 (point ``_ANSWER_MODEL`` at a
    nonexistent slug) both previously left 30/30 tests passing.
    """

    def test_the_two_configured_models_are_not_the_same_model(self) -> None:
        assert _QUESTION_MODEL != _ANSWER_MODEL

    def test_the_pair_validator_rejects_one_model_asking_and_answering(self) -> None:
        """The validator itself, called directly.

        Renamed from ``test_one_model_asking_and_answering_is_refused_at_import``:
        that name claimed import-time WIRING and this call proves only that
        the function raises when called. Deleting the module-level
        ``_validate_model_pair(...)`` call left the whole suite green under
        the old name. The wiring is pinned by the test below instead.
        """
        with pytest.raises(ConfigurationError, match="both"):
            _validate_model_pair(_QUESTION_MODEL, _QUESTION_MODEL)

    def test_a_same_model_pair_is_refused_at_import_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IMPORTING a module configured with one model twice must fail.

        Re-running the real import machinery over the module's own source,
        with only the ``_ANSWER_MODEL`` assignment rewritten, is the only way
        to exercise the import path: the plain import has already happened and
        cannot be replayed with different constants, and monkeypatching the
        constant afterwards cannot re-run a module-level call.

        This fails if the module-level ``_validate_model_pair(...)`` call is
        deleted, which is the mutation the direct-call test above cannot
        detect.
        """
        module_path = Path(comprehension_probe.__file__)
        tree = ast.parse(
            module_path.read_text(encoding="utf-8"), filename=str(module_path)
        )
        rewritten = 0
        for statement in tree.body:
            if (
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id == "_ANSWER_MODEL"
            ):
                statement.value = ast.Constant(_QUESTION_MODEL)
                rewritten += 1
        assert rewritten == 1, (
            "expected exactly one module-level _ANSWER_MODEL annotated "
            f"assignment to rewrite, found {rewritten}"
        )
        ast.fix_missing_locations(tree)
        loader = _RewrittenSourceLoader(
            "comprehension_probe_import_under_test", str(module_path), tree
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        # Registered under its throwaway name, and removed again by
        # monkeypatch, so the module can execute to completion the way a real
        # import does. Without it a ``@dataclass(slots=True)`` further down
        # the module fails on a sys.modules lookup, and the mutation this test
        # exists to catch would then be reported as an unrelated
        # AttributeError instead of a clean "DID NOT RAISE".
        monkeypatch.setitem(sys.modules, loader.name, module)
        with pytest.raises(ConfigurationError, match="both"):
            loader.exec_module(module)

    def test_both_configured_models_resolve_to_a_complete_price_row(self) -> None:
        for model in (_QUESTION_MODEL, _ANSWER_MODEL):
            price = price_for(_PROVIDER, model)
            assert price is not None, f"{model!r} has no ({_PROVIDER}, model) price row"
            assert price.input_usd_per_mtok is not None
            assert price.output_usd_per_mtok is not None
        # And the guard the run actually calls agrees with that inspection.
        _ensure_models_are_priced()

    def test_an_unpriced_model_refuses_to_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The guard must FIRE, not merely exist, when a slug goes stale.

        A vendor slug rename is a one-character edit away, and its symptom
        without this guard is a run that reports ``$0`` for real money.
        """
        monkeypatch.setattr(
            "scripts.comprehension_probe._ANSWER_MODEL",
            "deepseek/deepseek-v9-nonexistent",
        )
        with pytest.raises(ConfigurationError, match="cap cannot bind"):
            _ensure_models_are_priced()

    # mutation_deselect: drives `main()` (or the gitignore guard) against paths
    # under `_REPO_ROOT`, which under mutmut is the generated `mutants/` copy.
    # `mutants/` is itself gitignored, so `git check-ignore` answers "ignored"
    # for every path beneath it and `ensure_persistable` refuses to start before
    # the behaviour under test is reached; the assertion then fails for a reason
    # that has nothing to do with the code being mutated. These pin properties
    # of the real worktree's ignore rules, so the copy is the wrong place to run
    # them (same reasoning as test_check_no_em_dash.py's tree guard).
    @pytest.mark.mutation_deselect
    def test_an_unpriced_model_stops_the_run_before_the_corpus_is_walked(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``main`` must REFUSE TO START, not merely have a guard available.

        The test above proves the guard raises when called. It says nothing
        about whether ``main`` calls it: replacing that call with ``pass``
        left the whole suite green. This drives ``main`` itself and pins that
        the refusal happens before the corpus walk, which is the last step
        before any provider call.

        No spend is possible on this path even if the guard were removed
        (``BudgetTracker.add`` raises on an uncostable call), but "the second
        line of defence would have caught it" is not a reason to leave the
        first one untested.
        """
        monkeypatch.setattr(
            "scripts.comprehension_probe._ANSWER_MODEL",
            "deepseek/deepseek-v9-nonexistent",
        )

        def _must_not_walk(*_args: object, **_kwargs: object) -> None:
            pytest.fail("main() reached the corpus walk with an unpriced model")

        monkeypatch.setattr(
            "scripts.comprehension_probe.collect_passages", _must_not_walk
        )
        # Paths that exist only as arguments: nothing is written on this path,
        # and the run must abort before the corpus directory is even opened.
        exit_code = main(
            [
                "--corpus",
                str(_REPO_ROOT / "tmp" / "comprehension-probe-unpriced-corpus"),
                "--out",
                str(_REPO_ROOT / "tmp" / "comprehension-probe-unpriced-out"),
                "--env-file",
                str(_REPO_ROOT / "tmp" / "comprehension-probe-unpriced.env"),
            ]
        )
        assert exit_code == 1
        # The message discriminates: a run that got past the price guard and
        # failed on provider construction instead reports something else.
        assert "cap cannot bind" in capsys.readouterr().err


class TestSummarize:
    """Aggregate rate math, and the uniform-verdict trap (recon trap 5)."""

    def _result(
        self, node_id: str, answers: list[bool] | None, error_stage: str | None = None
    ) -> NodeResult:
        records = (
            [
                AnswerRecord(question=f"q{i}", can_answer=a, answer="")
                for i, a in enumerate(answers)
            ]
            if answers is not None
            else None
        )
        return NodeResult(
            story_id="s",
            node_id=node_id,
            questions=["q0", "q1", "q2"] if answers is not None else None,
            answers=records,
            error_stage=error_stage,
        )

    def _stats(self) -> CorpusStats:
        return CorpusStats(
            files_scanned=1,
            files_skipped_non_storybook=0,
            files_skipped_age_band=0,
            nodes_seen=2,
            nodes_skipped_fill=0,
            nodes_skipped_empty=0,
            passages_collected=2,
            stories_available=1,
            stories_sampled=1,
        )

    def test_mixed_answerability_computes_the_unlabelled_rate(self) -> None:
        results = [
            self._result("n1", [True, False, True]),
            self._result("n2", [False, False, True]),
        ]
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        budget.spent_usd = Decimal("0.02")
        summary = summarize(
            results,
            budget=budget,
            corpus_stats=self._stats(),
            corpus_description="test",
        )
        assert summary.questions_asked == 6
        assert summary.questions_unanswerable == 3
        assert summary.unlabelled_unanswerable_rate == pytest.approx(0.5)
        assert summary.nodes_with_any_unanswerable == 2
        assert summary.uniform_verdict_warning is None

    def test_all_answerable_flags_the_uniform_verdict_warning(self) -> None:
        results = [
            self._result("n1", [True, True, True]),
            self._result("n2", [True, True, True]),
        ]
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        summary = summarize(
            results,
            budget=budget,
            corpus_stats=self._stats(),
            corpus_description="test",
        )
        assert summary.unlabelled_unanswerable_rate == 0.0
        assert summary.uniform_verdict_warning is not None
        assert "environment fault" in summary.uniform_verdict_warning

    def test_all_unanswerable_flags_the_uniform_verdict_warning(self) -> None:
        results = [self._result("n1", [False, False, False])]
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        summary = summarize(
            results,
            budget=budget,
            corpus_stats=self._stats(),
            corpus_description="test",
        )
        assert summary.unlabelled_unanswerable_rate == 1.0
        assert summary.uniform_verdict_warning is not None

    def test_a_note_disclaiming_precision_is_always_present(self) -> None:
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        summary = summarize(
            [], budget=budget, corpus_stats=self._stats(), corpus_description="test"
        )
        assert "NOT precision" in summary.note
        assert summary.unlabelled_unanswerable_rate is None

    def test_budget_and_error_stage_skips_are_not_counted_as_processed(self) -> None:
        """Both budget stages count as budget skips, and neither as processed.

        ``nodes_skipped_budget`` is asserted here because it is the only field
        that says how much of the declared slice the cap swallowed, and this
        branch added ``budget_after_questions`` as a second stage that feeds
        it. A cap that binds mid-passage produces that stage, not ``budget``,
        so counting only the first understates the unprobed remainder by
        exactly the number of passages that got their questions but not their
        answers, and the unanswerable rate is then read as covering a slice it
        never reached. Two budget results and one non-budget error, so a
        summary that counted every skipped node, or only the first stage,
        fails here.
        """
        results = [
            self._result("n1", None, error_stage="budget"),
            self._result("n2", None, error_stage="question_generation:malformed"),
            self._result("n3", None, error_stage="budget_after_questions"),
        ]
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        summary = summarize(
            results,
            budget=budget,
            corpus_stats=self._stats(),
            corpus_description="test",
        )
        assert summary.nodes_processed == 0
        assert summary.nodes_skipped_budget == 2
        assert summary.unlabelled_unanswerable_rate is None
        assert summary.error_counts == {
            "budget": 1,
            "question_generation:malformed": 1,
            "budget_after_questions": 1,
        }

    def test_the_summary_records_the_sampling_strategy(self) -> None:
        """A rate is only interpretable against the slice that produced it.

        The second pilot's aggregate said ``max_passages=60`` and nothing
        about WHICH 60, so an opening-prefix figure read as a band figure.
        The strategy is taken from the module constant rather than from a
        caller-supplied string, so it cannot describe a selection rule other
        than the one ``collect_passages`` implements.

        Calling ``summarize()`` without a ``sampling_strategy`` argument and
        then checking the returned field proves only that the field defaults
        to the constant; it says nothing about whether a caller could supply
        a different one. Proved by reproduction: adding
        ``sampling_strategy: str = _SAMPLING_STRATEGY`` as a keyword parameter
        to ``summarize`` and threading it through to the constructed
        :class:`ProbeSummary` left the whole suite, including the assertions
        below, green. Guard the interface itself: no such parameter may
        exist, so no caller can claim a strategy the run did not follow.
        """
        assert "sampling_strategy" not in inspect.signature(summarize).parameters
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        summary = summarize(
            [], budget=budget, corpus_stats=self._stats(), corpus_description="test"
        )
        assert summary.sampling_strategy == _SAMPLING_STRATEGY
        assert "stride" in summary.sampling_strategy
        assert "rather than sampling its opening passages" in summary.sampling_strategy


class TestWriteTrackedAggregate:
    """The tracked aggregate is the run's durable finding, so it must survive.

    Two properties, both previously unpinned because the writer had no test at
    all: it must actually write (a no-op left the suite green), and a later
    run must not destroy an earlier run's aggregate. The original writer used
    a fixed ``latest-summary.json``, so the second paid run would silently
    have overwritten the first: a defect against ``UW-F53``, the very row the
    tracked aggregate exists to serve.
    """

    @staticmethod
    def _summary() -> ProbeSummary:
        return summarize(
            [],
            budget=BudgetTracker(cap_usd=Decimal("5.00")),
            corpus_stats=CorpusStats(
                files_scanned=1,
                files_skipped_non_storybook=0,
                files_skipped_age_band=0,
                nodes_seen=1,
                nodes_skipped_fill=0,
                nodes_skipped_empty=0,
                passages_collected=1,
                stories_available=1,
                stories_sampled=1,
            ),
            corpus_description="test",
        )

    def test_the_aggregate_is_written_under_its_run_id(self, tmp_path: Path) -> None:
        """Fails if the writer becomes a no-op, which nothing previously did."""
        written = write_tracked_aggregate(
            tmp_path, self._summary(), run_id="20260101T000000Z"
        )
        assert written == tmp_path / "summary-20260101T000000Z.json"
        assert written.exists()
        payload = json.loads(written.read_text(encoding="utf-8"))
        assert payload["sampling_strategy"] == _SAMPLING_STRATEGY
        assert payload["corpus_description"] == "test"
        assert "NOT precision" in payload["note"]

    def test_a_later_run_does_not_destroy_an_earlier_runs_aggregate(
        self, tmp_path: Path
    ) -> None:
        first = write_tracked_aggregate(
            tmp_path, self._summary(), run_id="20260101T000000Z"
        )
        second = write_tracked_aggregate(
            tmp_path, self._summary(), run_id="20260102T000000Z"
        )
        assert first != second
        assert first.exists()
        assert second.exists()

    def test_the_fixed_name_holds_a_pointer_and_no_findings(
        self, tmp_path: Path
    ) -> None:
        """``latest-summary.json`` is a convenience, never the record itself."""
        write_tracked_aggregate(tmp_path, self._summary(), run_id="20260101T000000Z")
        written = write_tracked_aggregate(
            tmp_path, self._summary(), run_id="20260102T000000Z"
        )
        pointer = json.loads(
            (tmp_path / "latest-summary.json").read_text(encoding="utf-8")
        )
        assert pointer["latest"] == written.name
        assert pointer["run_id"] == "20260102T000000Z"
        # No rate, no counts: reading the pointer can never yield a figure.
        assert "unlabelled_unanswerable_rate" not in pointer
        assert "corpus_stats" not in pointer

    @pytest.mark.parametrize(
        "run_id",
        [
            "",
            "../escape",
            "nested/run",
            "run id",
            "run\x00id",
            # Built entirely from allowlisted characters, so the character class
            # alone lets both through: ".." writes the aggregate one directory
            # ABOVE the destination it was handed, and "." collapses onto the
            # destination itself. A separator is not the only way out of a
            # directory.
            "..",
            ".",
            "...",
        ],
    )
    def test_a_run_id_that_is_not_a_safe_path_component_is_refused(
        self, tmp_path: Path, run_id: str
    ) -> None:
        summary = self._summary()
        with pytest.raises(ValueError, match="not a safe path component"):
            write_tracked_aggregate(tmp_path, summary, run_id=run_id)

    @pytest.mark.parametrize("run_id", ["20260101T000000Z", "v1.2", "run_1-a"])
    def test_a_safe_run_id_is_still_accepted(self, tmp_path: Path, run_id: str) -> None:
        """The control: the added rejection narrows the class, it does not close it.

        Without this, "reject everything" would pass every case above.
        """
        written = write_tracked_aggregate(tmp_path, self._summary(), run_id=run_id)
        assert written.name == f"summary-{run_id}.json"


# mutation_deselect: drives `main()` (or the gitignore guard) against paths
# under `_REPO_ROOT`, which under mutmut is the generated `mutants/` copy.
# `mutants/` is itself gitignored, so `git check-ignore` answers "ignored"
# for every path beneath it and `ensure_persistable` refuses to start before
# the behaviour under test is reached; the assertion then fails for a reason
# that has nothing to do with the code being mutated. These pin properties
# of the real worktree's ignore rules, so the copy is the wrong place to run
# them (same reasoning as test_check_no_em_dash.py's tree guard).
@pytest.mark.mutation_deselect
class TestEnsureGitignoredDestination:
    """Pins the discovered defect: ``out/reports/`` looks gitignored and is not.

    ``.gitignore`` only ignores specific subtrees under ``out/``
    (``out/diversity/``, ``out/mutations/``, ``out/w7/arms/``); ``out/reports/``
    itself already carries tracked content (``.gitkeep``, compliance-report
    markdown) and no ignore rule of its own. A guard that never fires against
    that exact path is not a guard, so both directions are pinned against real
    paths in this repository rather than against a synthetic tmp_path double
    that could not reproduce the false premise.
    """

    def test_a_destination_with_no_ignore_rule_raises(self) -> None:
        with pytest.raises(SystemExit, match="is NOT gitignored"):
            _ensure_gitignored_destination(_REPO_ROOT / "out" / "reports")

    def test_a_destination_under_tmp_does_not_raise(self) -> None:
        # tmp/ is a repo-wide ignore rule; the path need not exist on disk for
        # `git check-ignore` to match it, only fall within the tree.
        _ensure_gitignored_destination(
            _REPO_ROOT / "tmp" / "comprehension-probe-guard-test"
        )


# mutation_deselect: drives `main()` (or the gitignore guard) against paths
# under `_REPO_ROOT`, which under mutmut is the generated `mutants/` copy.
# `mutants/` is itself gitignored, so `git check-ignore` answers "ignored"
# for every path beneath it and `ensure_persistable` refuses to start before
# the behaviour under test is reached; the assertion then fails for a reason
# that has nothing to do with the code being mutated. These pin properties
# of the real worktree's ignore rules, so the copy is the wrong place to run
# them (same reasoning as test_check_no_em_dash.py's tree guard).
@pytest.mark.mutation_deselect
class TestMainSharesOneRunIdBetweenBothWriters:
    """``write_report``'s docstring promises both writers share one stamp.

    Proved false by reproduction: pinning the ``write_tracked_aggregate`` call
    inside ``main`` to a hardcoded ``run_id="DIVERGENT"`` literal left the
    whole 55-test suite green, because nothing exercised ``main`` end to end
    and inspected what each writer actually received. The shared stamp is how
    ``UW-F53`` reaches the raw per-story reports from the tracked aggregate,
    so a divergence between the two breaks that labelling path silently.

    Provider construction and the paid probing loop are stubbed out here (no
    test in this file makes a network call); the two writers are stubbed too,
    since the point is to observe the identity ``main`` calls each one with,
    not to exercise their own file-writing logic (``TestWriteTrackedAggregate``
    already does that).
    """

    def test_write_report_and_write_tracked_aggregate_receive_the_same_run_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        passage = Passage(
            story_id="s", story_path="s.json", node_id="n1", body="Once upon a time."
        )
        stats = CorpusStats(
            files_scanned=1,
            files_skipped_non_storybook=0,
            files_skipped_age_band=0,
            nodes_seen=1,
            nodes_skipped_fill=0,
            nodes_skipped_empty=0,
            passages_collected=1,
            stories_available=1,
            stories_sampled=1,
        )
        monkeypatch.setattr(
            comprehension_probe,
            "collect_passages",
            lambda *args, **kwargs: ([passage], stats),
        )
        monkeypatch.setattr(
            comprehension_probe,
            "build_openrouter_cost_reporting_leg",
            lambda *args, **kwargs: object(),
        )

        async def _fake_run_probe(
            *_args: object, **_kwargs: object
        ) -> list[NodeResult]:
            return [
                NodeResult(
                    story_id="s",
                    node_id="n1",
                    questions=None,
                    answers=None,
                    error_stage="budget",
                )
            ]

        monkeypatch.setattr(comprehension_probe, "run_probe", _fake_run_probe)

        received_run_ids: dict[str, str] = {}

        def _fake_write_report(
            out_dir: Path, *, run_id: str, **_kwargs: object
        ) -> Path:
            received_run_ids["write_report"] = run_id
            return out_dir / run_id

        def _fake_write_tracked_aggregate(
            aggregate_dir: Path, summary: ProbeSummary, *, run_id: str
        ) -> Path:
            received_run_ids["write_tracked_aggregate"] = run_id
            return aggregate_dir / f"summary-{run_id}.json"

        monkeypatch.setattr(comprehension_probe, "write_report", _fake_write_report)
        monkeypatch.setattr(
            comprehension_probe,
            "write_tracked_aggregate",
            _fake_write_tracked_aggregate,
        )

        exit_code = main(
            [
                "--corpus",
                str(_REPO_ROOT / "tmp" / "comprehension-probe-runid-corpus"),
                "--out",
                str(_REPO_ROOT / "tmp" / "comprehension-probe-runid-out"),
                "--aggregate-dir",
                str(
                    _REPO_ROOT
                    / "out"
                    / "reports"
                    / "comprehension-probe-runid-test-double"
                ),
                "--env-file",
                str(_REPO_ROOT / "tmp" / "comprehension-probe-runid.env"),
            ]
        )

        assert exit_code == 0
        assert "write_report" in received_run_ids
        assert "write_tracked_aggregate" in received_run_ids
        assert (
            received_run_ids["write_report"]
            == received_run_ids["write_tracked_aggregate"]
        )
