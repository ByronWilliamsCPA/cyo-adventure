"""Unit tests for the plan reviewer's pure core (WP-3.7, D11 and D12).

``cyo_adventure.storyplan.review`` holds the verdict model and its defensive
parser, the independence rule, the combination of two runs, the checker's
authority, the seeded exception sample, the suspension rule and the
validated-pairing refusal. Everything here is offline.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cyo_adventure.core.exceptions import BusinessLogicError, ConfigurationError
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storyplan.checks import base_example
from cyo_adventure.storyplan.review import (
    DEFAULT_SAMPLE_SEED,
    FINDING_CLASSES,
    UNVALIDATED,
    CheckerSummary,
    PlanVerdict,
    ReviewFinding,
    SampledPass,
    ValidatedPairing,
    apply_checker_authority,
    assert_independent,
    assert_reviewer_usable,
    combine_runs,
    draw_sample,
    evaluate_suspension,
    format_validated_pairing,
    model_family,
    parse_plan_verdict,
    parse_validated_pairing,
    plan_content_hash,
    plan_entry_ids,
    plan_for_review,
    render_book_graph,
    reviewer_refusal,
    scrub_reason,
    unsure_verdict,
)

if TYPE_CHECKING:
    from typing import Literal

EM_DASH = chr(0x2014)

GOOD = json.dumps(
    {
        "verdict": "reject",
        "confidence": 0.8,
        "findings": [
            {
                "entry": "c_take_map",
                "class": "label_outcome_mismatch",
                "severity": "should-fix",
                "reason": "The intent says one thing and n_path establishes another.",
            }
        ],
    }
)


def _answer(verdict: str, findings: list[dict[str, object]] | None = None) -> str:
    return json.dumps(
        {"verdict": verdict, "confidence": 0.7, "findings": findings or []}
    )


def _finding(
    entry: str, severity: str = "should-fix", cls: str = "other"
) -> dict[str, object]:
    return {"entry": entry, "class": cls, "severity": severity, "reason": "r"}


class TestParsing:
    """parse_plan_verdict fails closed and never passes a doubtful answer."""

    def test_a_clean_answer_is_parsed(self) -> None:
        v = parse_plan_verdict(GOOD, finish_reason="stop", known_entries={"c_take_map"})
        assert v.verdict == "reject"
        assert v.confidence == pytest.approx(0.8)
        assert v.reasons == ()
        (f,) = v.findings
        assert (f.entry, f.defect_class, f.severity) == (
            "c_take_map",
            "label_outcome_mismatch",
            "should-fix",
        )
        assert f.entry_known
        assert f.authoritative

    def test_a_fenced_answer_is_parsed(self) -> None:
        v = parse_plan_verdict(f"```json\n{_answer('pass')}\n```", finish_reason="stop")
        assert v.verdict == "pass"

    @pytest.mark.parametrize("text", ["", "   ", None])
    def test_an_empty_answer_is_unsure(self, text: str | None) -> None:
        v = parse_plan_verdict(text, finish_reason="stop")
        assert v.verdict == "unsure"
        assert v.reasons == ("empty_answer",)

    @pytest.mark.parametrize(
        "text",
        [
            "I think this plan is fine.",
            '{"verdict": "pass", "findings": [',
            '{"verdict": "pass"',
            "[1, 2, 3]",
            '{"verdict": ',
        ],
    )
    def test_garbage_and_truncated_json_is_unsure_never_pass(self, text: str) -> None:
        v = parse_plan_verdict(text, finish_reason="stop")
        assert v.verdict == "unsure"
        assert v.reasons == ("unparseable_answer",)

    def test_a_length_finish_is_unsure_even_when_the_text_says_pass(self) -> None:
        # AL-823: a starved call may still return a JSON object; it is not trusted.
        v = parse_plan_verdict(_answer("pass"), finish_reason="length")
        assert v.verdict == "unsure"
        assert v.reasons == ("finish_reason_length",)

    def test_any_other_abnormal_finish_is_unsure(self) -> None:
        v = parse_plan_verdict(_answer("pass"), finish_reason="content_filter")
        assert v.verdict == "unsure"
        assert v.reasons == ("finish_reason_content_filter",)

    @pytest.mark.parametrize("reason", ["stop", "end_turn", "<absent>", None])
    def test_a_normal_finish_is_trusted(self, reason: str | None) -> None:
        assert (
            parse_plan_verdict(_answer("pass"), finish_reason=reason).verdict == "pass"
        )

    def test_an_unknown_verdict_is_unsure(self) -> None:
        v = parse_plan_verdict(_answer("approve"), finish_reason="stop")
        assert v.verdict == "unsure"
        assert v.reasons == ("unknown_verdict",)

    def test_a_pass_claimed_over_a_blocker_finding_is_unsure(self) -> None:
        v = parse_plan_verdict(
            _answer("pass", [_finding("n_fork", "blocker")]), finish_reason="stop"
        )
        assert v.verdict == "unsure"
        assert "pass_with_blocker_finding" in v.reasons

    def test_a_pass_with_minor_findings_is_still_a_pass(self) -> None:
        v = parse_plan_verdict(
            _answer("pass", [_finding("n_fork", "minor")]), finish_reason="stop"
        )
        assert v.verdict == "pass"

    def test_a_reject_without_findings_is_kept_and_noted(self) -> None:
        v = parse_plan_verdict(_answer("reject"), finish_reason="stop")
        assert v.verdict == "reject"
        assert v.reasons == ("reject_without_findings",)

    def test_finding_fields_are_coerced_defensively(self) -> None:
        raw = _answer(
            "reject",
            [
                {
                    "entry": ["n_a", "n_b"],
                    "class": "Truth-Contradiction",
                    "severity": "BLOCKER",
                },
                {"entry": "n_c", "class": "made up", "severity": "huge", "reason": 5},
                {"class": "other"},
                "not a dict",
                {"entry": "ghost", "severity": "minor"},
            ],
        )
        v = parse_plan_verdict(raw, finish_reason="stop", known_entries={"n_a", "n_c"})
        entries = {f.entry: f for f in v.findings}
        assert set(entries) == {"n_a", "n_c", "ghost"}
        assert entries["n_a"].defect_class == "truth_contradiction"
        assert entries["n_a"].severity == "blocker"
        assert entries["n_c"].defect_class == "other"
        assert entries["n_c"].severity == "should-fix"
        assert entries["n_c"].reason == ""
        assert not entries["ghost"].entry_known
        assert "finding_without_entry" in v.reasons

    def test_every_class_a_finding_can_carry_is_a_known_class(self) -> None:
        v = parse_plan_verdict(
            _answer("reject", [_finding("n", cls=c) for c in FINDING_CLASSES]),
            finish_reason="stop",
        )
        assert {f.defect_class for f in v.findings} == set(FINDING_CLASSES)

    @pytest.mark.parametrize("confidence", [-1, 2, "high", True, None])
    def test_a_bad_confidence_is_dropped(self, confidence: object) -> None:
        raw = json.dumps({"verdict": "pass", "confidence": confidence, "findings": []})
        assert parse_plan_verdict(raw, finish_reason="stop").confidence is None

    def test_a_reason_we_generate_never_carries_model_output(self) -> None:
        secret = "the lighthouse keeper whispered a secret sentence"
        for text, finish in (
            (secret, "stop"),
            (secret, "length"),
            ('{"verdict": "x", "note": "' + secret + '"}', "stop"),
        ):
            v = parse_plan_verdict(text, finish_reason=finish)
            assert secret not in json.dumps(v.to_dict())

    @given(st.text(), st.sampled_from(["stop", "length", None, "error"]))
    def test_parsing_never_raises_and_length_is_never_a_pass(
        self, text: str, finish: str | None
    ) -> None:
        v = parse_plan_verdict(text, finish_reason=finish)
        assert v.verdict in {"pass", "reject", "unsure"}
        if finish in {"length", "error"}:
            assert v.verdict == "unsure"


class TestScrubReason:
    """A reason is stored and printed only after it is scrubbed."""

    def test_a_long_quoted_span_is_replaced(self) -> None:
        quote = "x" * 60
        out = scrub_reason(f'The node says "{quote}" which is wrong.')
        assert quote not in out
        assert "[quoted text removed]" in out

    def test_a_long_curly_quoted_span_is_replaced(self) -> None:
        quote = "y" * 60
        out = scrub_reason(f"See {chr(0x201C)}{quote}{chr(0x201D)} here.")
        assert quote not in out

    def test_a_short_quoted_id_is_kept(self) -> None:
        assert '"has_key"' in scrub_reason('The fact "has_key" is wrong.')

    def test_the_em_dash_and_control_characters_are_removed(self) -> None:
        out = scrub_reason(f"one {EM_DASH} two\x00\x07 three\n four")
        assert EM_DASH not in out
        assert "\x00" not in out
        assert "\n" not in out
        assert out == "one - two three four"

    def test_the_length_is_capped(self) -> None:
        assert len(scrub_reason("a" * 5000)) == 400

    @pytest.mark.parametrize("value", [None, 5, ["x"], {"a": 1}])
    def test_a_non_string_is_empty(self, value: object) -> None:
        assert scrub_reason(value) == ""

    def test_a_reason_in_a_parsed_answer_is_scrubbed(self) -> None:
        reason = f'quote "{"z" * 80}" and {EM_DASH} more'
        raw = _answer(
            "reject",
            [{"entry": "n", "class": "other", "severity": "minor", "reason": reason}],
        )
        (f,) = parse_plan_verdict(raw, finish_reason="stop").findings
        assert "z" * 80 not in f.reason
        assert EM_DASH not in f.reason


class TestCombination:
    """Two runs: identical verdicts keep, any disagreement is unsure, findings union."""

    def test_identical_verdicts_are_kept(self) -> None:
        a = PlanVerdict("pass", 0.9)
        b = PlanVerdict("pass", 0.6)
        out = combine_runs([a, b])
        assert out.verdict == "pass"
        assert out.confidence == pytest.approx(0.6)
        assert out.reasons == ()

    def test_a_disagreement_is_unsure(self) -> None:
        out = combine_runs([PlanVerdict("pass", 0.9), PlanVerdict("reject", 0.9)])
        assert out.verdict == "unsure"
        assert "runs_disagree" in out.reasons

    def test_reject_and_unsure_is_unsure(self) -> None:
        out = combine_runs([PlanVerdict("reject", None), unsure_verdict("x")])
        assert out.verdict == "unsure"

    def test_findings_are_unioned_and_deduplicated(self) -> None:
        f1 = ReviewFinding("n_a", "other", "minor", "first")
        f2 = ReviewFinding("n_b", "other", "minor", "second")
        dup = ReviewFinding("n_a", "other", "minor", "different words")
        out = combine_runs(
            [PlanVerdict("reject", 0.5, (f1,)), PlanVerdict("reject", 0.5, (dup, f2))]
        )
        assert [f.entry for f in out.findings] == ["n_a", "n_b"]
        assert out.findings[0].reason == "first"

    def test_reason_codes_are_unioned(self) -> None:
        out = combine_runs(
            [unsure_verdict("finish_reason_length"), unsure_verdict("provider_error")]
        )
        assert out.reasons == ("finish_reason_length", "provider_error")

    def test_no_runs_is_unsure(self) -> None:
        assert combine_runs([]).verdict == "unsure"

    @given(
        st.lists(st.sampled_from(["pass", "reject", "unsure"]), min_size=1, max_size=4)
    )
    def test_agreement_keeps_and_any_difference_is_unsure(
        self, kinds: list[str]
    ) -> None:
        verdicts = [
            PlanVerdict(cast("Literal['pass', 'reject', 'unsure']", k), None)
            for k in kinds
        ]
        out = combine_runs(verdicts)
        if len(set(kinds)) == 1:
            assert out.verdict == kinds[0]
        else:
            assert out.verdict == "unsure"


class TestCheckerAuthority:
    """The reviewer never overrides the deterministic checker."""

    def test_a_pass_over_a_checker_error_is_forced_to_reject(self) -> None:
        checker = CheckerSummary.from_rule_ids(["SP-2", "SP-2", "SP-3"])
        out = apply_checker_authority(
            PlanVerdict("pass", 0.9), checker, run_verdicts=["pass", "pass"]
        )
        assert out.verdict == "reject"
        assert out.checker_caught
        assert out.reviewer_pass_overridden
        assert out.reviewer_ran
        assert out.reasons[:2] == ("checker_error:SP-2", "checker_error:SP-3")

    def test_a_reject_over_a_checker_error_is_not_an_override(self) -> None:
        out = apply_checker_authority(
            PlanVerdict("reject", 0.9), CheckerSummary.from_rule_ids(["SP-7"])
        )
        assert out.verdict == "reject"
        assert out.checker_caught
        assert not out.reviewer_pass_overridden

    def test_a_checker_error_needs_no_reviewer(self) -> None:
        out = apply_checker_authority(None, CheckerSummary.from_rule_ids(["SP-1"]))
        assert out.verdict == "reject"
        assert out.checker_caught
        assert not out.reviewer_ran
        assert not out.reviewer_pass_overridden

    def test_a_clean_check_leaves_the_reviewers_verdict(self) -> None:
        clean = CheckerSummary.from_rule_ids([], warnings=2)
        for kind in ("pass", "reject", "unsure"):
            out = apply_checker_authority(
                PlanVerdict(cast("Literal['pass', 'reject', 'unsure']", kind), None),
                clean,
            )
            assert out.verdict == kind
            assert not out.checker_caught

    def test_a_clean_check_with_no_reviewer_is_unsure_not_pass(self) -> None:
        out = apply_checker_authority(None, CheckerSummary.from_rule_ids([]))
        assert out.verdict == "unsure"
        assert out.reasons == ("reviewer_not_run",)
        assert out.flagged

    @given(
        st.sampled_from(["pass", "reject", "unsure"]),
        st.integers(min_value=1, max_value=5),
    )
    def test_no_verdict_survives_a_checker_error_as_a_pass(
        self, kind: str, errors: int
    ) -> None:
        checker = CheckerSummary.from_rule_ids(["SP-2"] * errors)
        out = apply_checker_authority(
            PlanVerdict(cast("Literal['pass', 'reject', 'unsure']", kind), None),
            checker,
        )
        assert out.verdict == "reject"


class TestIndependence:
    """The reviewer must be a different model from the plan's writer."""

    def test_the_same_model_id_is_refused(self) -> None:
        with pytest.raises(BusinessLogicError) as exc:
            assert_independent(
                "anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5.5"
            )
        assert exc.value.details["rule"] == "plan_reviewer_not_independent"

    @pytest.mark.parametrize(
        "reviewer",
        [
            "openrouter:anthropic/claude-sonnet-5.5",
            "Anthropic/Claude-Sonnet-5.5",
            "anthropic/claude-sonnet-5.5:thinking",
            "~anthropic/claude-sonnet-5.5",
        ],
    )
    def test_the_same_model_spelled_another_way_is_refused(self, reviewer: str) -> None:
        with pytest.raises(BusinessLogicError):
            assert_independent("anthropic/claude-sonnet-5.5", reviewer)

    @pytest.mark.parametrize(
        "reviewer",
        [
            "anthropic/claude-sonnet-4.6",
            "claude-sonnet-4-6",
            "anthropic/claude-sonnet-5",
        ],
    )
    def test_a_different_generation_of_the_same_family_is_refused(
        self, reviewer: str
    ) -> None:
        with pytest.raises(BusinessLogicError) as exc:
            assert_independent("anthropic/claude-sonnet-5.5", reviewer)
        assert exc.value.details["rule"] == "plan_reviewer_not_independent"

    @pytest.mark.parametrize(
        "reviewer",
        [
            "google/gemini-3.1-pro-preview",
            "openai/gpt-5.6-sol",
            "anthropic/claude-opus-4.8",
            "deepseek/deepseek-v4-pro",
        ],
    )
    def test_a_different_vendor_or_family_is_allowed(self, reviewer: str) -> None:
        assert_independent("anthropic/claude-sonnet-5.5", reviewer)

    @pytest.mark.parametrize(
        ("writer", "reviewer"), [(None, "x/y"), ("x/y", None), ("", "x/y"), ("x/y", "")]
    )
    def test_an_unknown_model_fails_closed(
        self, writer: str | None, reviewer: str | None
    ) -> None:
        with pytest.raises(BusinessLogicError) as exc:
            assert_independent(writer, reviewer)
        assert exc.value.details["rule"] == "plan_reviewer_model_unknown"

    def test_a_bare_id_infers_its_vendor(self) -> None:
        assert model_family("claude-sonnet-4-6")[0] == "anthropic"
        assert model_family("gemini-2.5-flash")[0] == "google"
        assert model_family("anthropic/claude-sonnet-5.5")[2] == ("claude", "sonnet")
        assert model_family("google/gemini-3.1-pro-preview")[2] == ("gemini", "pro")

    def test_the_message_names_both_models(self) -> None:
        with pytest.raises(BusinessLogicError, match=r"claude-sonnet-5\.5"):
            assert_independent(
                "anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-4.6"
            )


class TestSampleDraw:
    """The exception sample is a seeded, auditable function of the plan hash."""

    def test_the_draw_is_deterministic_and_records_its_seed(self) -> None:
        a = draw_sample("sha256:abc", 0.1)
        b = draw_sample("sha256:abc", 0.1)
        assert a == b
        assert a.seed == DEFAULT_SAMPLE_SEED
        assert 0.0 <= a.draw < 1.0
        assert a.to_dict()["plan_id"] == "sha256:abc"

    def test_a_different_seed_gives_a_different_draw(self) -> None:
        assert (
            draw_sample("p", 0.5, seed="a").draw != draw_sample("p", 0.5, seed="b").draw
        )

    def test_rate_zero_never_samples_and_rate_one_always_does(self) -> None:
        for i in range(200):
            assert not draw_sample(f"plan-{i}", 0.0).sampled
            assert draw_sample(f"plan-{i}", 1.0).sampled

    @pytest.mark.parametrize("rate", [-0.1, 1.1, 5.0])
    def test_a_rate_outside_zero_to_one_is_a_configuration_error(
        self, rate: float
    ) -> None:
        with pytest.raises(ConfigurationError):
            draw_sample("p", rate)

    @pytest.mark.parametrize("rate", [0.1, 0.25, 0.5])
    def test_the_rate_is_hit_within_a_binomial_tolerance(self, rate: float) -> None:
        n = 1000
        hits = sum(draw_sample(f"sha256:{i:064x}", rate).sampled for i in range(n))
        sigma = (n * rate * (1 - rate)) ** 0.5
        assert abs(hits - n * rate) <= 4 * sigma

    @given(st.text(min_size=1), st.floats(0, 1), st.floats(0, 1))
    def test_a_plan_sampled_at_a_lower_rate_is_sampled_at_a_higher_one(
        self, plan_id: str, r1: float, r2: float
    ) -> None:
        low, high = sorted((r1, r2))
        if draw_sample(plan_id, low).sampled:
            assert draw_sample(plan_id, high).sampled


def _history(overturned: list[bool]) -> list[SampledPass]:
    return [SampledPass(f"p{i}", o) for i, o in enumerate(overturned)]


class TestSuspension:
    """Suspension: any overturned blocker-class pass, or more than 1 in 5 of the last 10."""

    def test_no_history_is_not_suspended(self) -> None:
        assert not evaluate_suspension([]).suspended

    def test_the_decision_is_json_ready(self) -> None:
        out = evaluate_suspension(_history([True, True, False, False, False])).to_dict()
        assert out == {
            "suspended": True,
            "reason": "overturn_rate",
            "considered": 5,
            "overturned": 2,
        }

    def test_fewer_than_five_sampled_never_suspends_on_rate(self) -> None:
        out = evaluate_suspension(_history([True, True, True, True]))
        assert not out.suspended
        assert out.considered == 4

    def test_exactly_one_in_five_does_not_suspend(self) -> None:
        assert not evaluate_suspension(
            _history([True, False, False, False, False])
        ).suspended

    def test_two_of_five_suspends(self) -> None:
        out = evaluate_suspension(_history([True, True, False, False, False]))
        assert out.suspended
        assert out.reason == "overturn_rate"

    def test_exactly_two_in_ten_does_not_suspend(self) -> None:
        assert not evaluate_suspension(_history([True, True] + [False] * 8)).suspended

    def test_three_in_ten_suspends(self) -> None:
        assert evaluate_suspension(_history([True, True, True] + [False] * 7)).suspended

    def test_only_the_last_ten_count(self) -> None:
        history = _history([True] * 6 + [False] * 10)
        out = evaluate_suspension(history)
        assert not out.suspended
        assert (out.considered, out.overturned) == (10, 0)

    def test_an_overturned_blocker_class_pass_suspends_at_once(self) -> None:
        out = evaluate_suspension(
            [SampledPass("p", owner_overturned=True, blocker_class=True)]
        )
        assert out.suspended
        assert out.reason == "blocker_overturned"

    def test_an_old_overturned_blocker_still_suspends(self) -> None:
        history = [
            SampledPass("old", owner_overturned=True, blocker_class=True),
            *_history([False] * 20),
        ]
        assert evaluate_suspension(history).suspended

    def test_a_blocker_class_pass_the_owner_upheld_does_not_suspend(self) -> None:
        assert not evaluate_suspension(
            [SampledPass("p", owner_overturned=False, blocker_class=True)]
        ).suspended

    @given(st.lists(st.booleans(), max_size=30))
    def test_the_rule_matches_its_definition(self, flags: list[bool]) -> None:
        window = flags[-10:]
        expected = len(window) >= 5 and sum(window) * 5 > len(window)
        assert evaluate_suspension(_history(flags)).suspended == expected


WRITER = "anthropic/claude-sonnet-5.5"
REVIEWER = "google/gemini-3.1-pro-preview"
HASH = "sha256:" + "a" * 64


def _refusal(**overrides: object) -> str | None:
    kwargs: dict[str, object] = {
        "enabled": True,
        "suspended": False,
        "writer_model": WRITER,
        "reviewer_model": REVIEWER,
        "prompt_hash": HASH,
        "validated_pairing": format_validated_pairing(
            ValidatedPairing(WRITER, REVIEWER, HASH)
        ),
    }
    kwargs.update(overrides)
    return reviewer_refusal(**cast("dict[str, bool | str | None]", kwargs))  # pyright: ignore[reportArgumentType]


class TestReviewerRefusal:
    """The worker refuses an unvalidated, suspended, disabled or mismatched pairing."""

    def test_a_matching_validated_pairing_is_usable(self) -> None:
        assert _refusal() is None

    def test_disabled_is_refused_first(self) -> None:
        assert _refusal(enabled=False, suspended=True) == "disabled"

    def test_suspended_is_refused(self) -> None:
        assert _refusal(suspended=True) == "suspended"

    def test_unvalidated_is_refused(self) -> None:
        assert _refusal(validated_pairing=UNVALIDATED) == "unvalidated"

    def test_a_malformed_record_is_refused(self) -> None:
        assert _refusal(validated_pairing="a|b") == "pairing_malformed"
        assert _refusal(validated_pairing="yes") == "pairing_malformed"

    @pytest.mark.parametrize(
        "change",
        [
            {"writer_model": "anthropic/claude-opus-4.8"},
            {"reviewer_model": "openai/gpt-5.6-sol"},
            {"prompt_hash": "sha256:" + "b" * 64},
        ],
    )
    def test_a_changed_writer_reviewer_or_prompt_voids_the_validation(
        self, change: dict[str, str]
    ) -> None:
        assert _refusal(**change) == "pairing_mismatch"

    def test_a_writer_equal_to_the_reviewer_is_refused(self) -> None:
        assert _refusal(reviewer_model=WRITER) == "not_independent"

    def test_an_unknown_writer_is_refused(self) -> None:
        assert _refusal(writer_model=None) == "model_unknown"

    def test_assert_reviewer_usable_raises_with_the_reason(self) -> None:
        with pytest.raises(BusinessLogicError) as exc:
            assert_reviewer_usable(
                enabled=True,
                suspended=False,
                writer_model=WRITER,
                reviewer_model=REVIEWER,
                prompt_hash=HASH,
                validated_pairing=UNVALIDATED,
            )
        assert exc.value.details["rule"] == "plan_reviewer_unusable"
        assert exc.value.details["context"] == {"reason": "unvalidated"}

    def test_the_pairing_round_trips(self) -> None:
        pairing = ValidatedPairing(WRITER, REVIEWER, HASH)
        assert parse_validated_pairing(format_validated_pairing(pairing)) == pairing
        assert parse_validated_pairing(UNVALIDATED) is None
        assert parse_validated_pairing("  unvalidated ") is None
        with pytest.raises(ConfigurationError):
            parse_validated_pairing("only|two")


class TestRenderers:
    """What the reviewer may see, and the plan hash the sample is seeded from."""

    def _plan(self) -> dict[str, object]:
        _, plan = base_example()
        plan["request"] = {"band": "8-11", "text": "a dragon story", "note": "n"}
        plan["provenance"] = {
            "producer": "writer",
            "approver": "owner",
            "checks": {"ok": True, "errors": 0, "warnings": 0},
            "notes": ["a continuity finding"],
            "shape": {"id": "s", "hash": "sha256:" + "0" * 64},
        }
        return plan

    def test_the_request_and_the_notes_are_removed_from_the_body(self) -> None:
        plan = self._plan()
        body, request = plan_for_review(plan)
        assert "request" not in body
        assert request == {"band": "8-11", "text": "a dragon story", "note": "n"}
        provenance = cast("dict[str, object]", body["provenance"])
        assert set(provenance) == {"producer", "shape"}
        assert "a continuity finding" not in json.dumps(body)

    def test_the_input_is_not_mutated(self) -> None:
        plan = self._plan()
        before = json.dumps(plan, sort_keys=True)
        plan_for_review(plan)
        assert json.dumps(plan, sort_keys=True) == before

    def test_entry_ids_cover_every_section(self) -> None:
        plan = self._plan()
        ids = plan_entry_ids(plan)
        assert {"n_start", "c_take_map", "map_marks_cave", "t_map"} <= ids
        assert any(i for i in ids if i in cast("dict[str, object]", plan["endings"]))

    def test_the_content_hash_ignores_approval_and_notes_only(self) -> None:
        plan = self._plan()
        base = plan_content_hash(plan)
        provenance = cast("dict[str, object]", plan["provenance"])
        provenance["approver"] = "someone else"
        provenance["notes"] = ["different"]
        provenance["checks"] = {"ok": False, "errors": 1, "warnings": 0}
        assert plan_content_hash(plan) == base
        cast("dict[str, object]", plan["request"])["text"] = "another story"
        assert plan_content_hash(plan) != base
        assert base.startswith("sha256:")

    def test_the_graph_has_ids_conditions_effects_and_endings_and_no_prose(
        self,
    ) -> None:
        book_dict, _ = base_example()
        nodes = cast("list[dict[str, object]]", book_dict["nodes"])
        for node in nodes:
            node["body"] = f"PROSE_SENTINEL {node['id']} the lamp glowed"
            for choice in cast("list[dict[str, object]]", node.get("choices", [])):
                choice["label"] = f"LABEL_SENTINEL {choice['id']}"
            ending = node.get("ending")
            if isinstance(ending, dict):
                ending["title"] = "TITLE_SENTINEL"
        book = Storybook.model_validate(book_dict)
        graph = render_book_graph(book)
        assert "SENTINEL" not in graph
        assert "the lamp glowed" not in graph
        assert graph.startswith(f"start: {book.start_node}")
        assert "n_start: c_take_map -> n_path sets set has_map=true" in graph
        assert re.search(r"n_\w+: ENDING valence=\w+ kind=\w+", graph)
        assert "variables:" in graph
        assert " if {" in graph

    def test_the_graph_is_ascii(self) -> None:
        book_dict, _ = base_example()
        assert render_book_graph(Storybook.model_validate(book_dict)).isascii()


def test_no_em_dash_in_the_modules_under_test() -> None:
    import cyo_adventure.storyplan.review as module

    assert module.__file__ is not None
    with open(module.__file__, encoding="utf-8") as handle:
        assert EM_DASH not in handle.read()
