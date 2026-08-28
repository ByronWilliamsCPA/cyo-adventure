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

import asyncio
import json
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.pricing import estimate_cost, price_for
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.generation.usage import Completion, TokenUsage
from scripts.comprehension_probe import (
    _REPO_ROOT,  # pyright: ignore[reportPrivateUsage]
    AnswerRecord,
    BudgetTracker,
    CorpusStats,
    NodeResult,
    Passage,
    ProbeParseError,
    _ensure_gitignored_destination,  # pyright: ignore[reportPrivateUsage]
    _extract_answers,  # pyright: ignore[reportPrivateUsage]
    _extract_questions,  # pyright: ignore[reportPrivateUsage]
    _parse_json_object,  # pyright: ignore[reportPrivateUsage]
    collect_passages,
    probe_passage,
    run_probe,
    summarize,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# Real, priced (provider, model) pairs from core/pricing.py, so cost math in
# these tests exercises the same price table a live run would, instead of a
# fixture price that could drift from it unnoticed.
_QUESTION_PAIR = ("openrouter", "google/gemini-2.5-flash")
_ANSWER_PAIR = ("openrouter", "deepseek/deepseek-v4-flash")


def _completion(
    text: str,
    *,
    provider: str = "mock",
    model: str = "mock",
    input_tokens: int | None = 200,
    output_tokens: int | None = 60,
    finish_reason: str | None = "stop",
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
        truncated_mid_entry = '{"questions": ["What happened?", "Why did it'
        completion = _completion(truncated_mid_entry, finish_reason="length")
        with pytest.raises(ProbeParseError) as exc_info:
            _parse_json_object(completion)
        assert exc_info.value.kind == "truncated"

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
        assert [p.node_id for p in passages] == ["n0", "n1", "n2"]
        assert stats.passages_collected == 3


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

    def test_cost_estimate_from_an_unpriced_pair_does_not_silently_read_as_free(
        self,
    ) -> None:
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        estimate = estimate_cost(price_for("openrouter", "not-a-real-model"), 100, 100)
        budget.add(estimate)
        assert estimate.complete is False
        assert budget.incomplete_cost_calls == 1


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
        results = [
            self._result("n1", None, error_stage="budget"),
            self._result("n2", None, error_stage="question_generation:malformed"),
        ]
        budget = BudgetTracker(cap_usd=Decimal("5.00"))
        summary = summarize(
            results,
            budget=budget,
            corpus_stats=self._stats(),
            corpus_description="test",
        )
        assert summary.nodes_processed == 0
        assert summary.unlabelled_unanswerable_rate is None
        assert summary.error_counts == {
            "budget": 1,
            "question_generation:malformed": 1,
        }


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
