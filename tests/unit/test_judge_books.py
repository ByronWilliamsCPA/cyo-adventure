"""Unit tests for the blind cross-lab quality judge panel.

The panel's output is an opinion, so its value rests entirely on the guards
around that opinion: a failed scoring must not read as a bad book, a lenient
judge must not out-vote a strict one, and a judge must be able to see the branch
structure it is asked to grade. Each of those is a place where a silent bug
produces a plausible number, which is the worst failure mode an evaluation can
have.

No test here makes a network call: the provider is stubbed.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest

from scripts.judge_books import (
    _JUDGE_MAX_TOKENS,  # pyright: ignore[reportPrivateUsage]
    Judge,
    Verdict,
    _parse,  # pyright: ignore[reportPrivateUsage]
    _story_text,  # pyright: ignore[reportPrivateUsage]
    _z_scores,  # pyright: ignore[reportPrivateUsage]
    judge_book,
    panel_participation,
    pool_scores,
)

_CRITERIA_NAMES = (
    "age_fit",
    "imagery",
    "voice",
    "dialogue",
    "choice_quality",
    "ending_quality",
    "engagement",
)


def _verdict(
    leg: str,
    judge: str,
    book: str,
    value: float,
    *,
    error: str | None = None,
    self_family: bool = False,
) -> Verdict:
    """Build a verdict scoring every criterion at one value.

    Args:
        leg: The generating leg.
        judge: The scoring judge.
        book: The book identifier.
        value: The score to give every criterion.
        error: Failure text, or ``None`` for a successful scoring.
        self_family: Whether the judge shares the leg's lab.

    Returns:
        The verdict.
    """
    return Verdict(
        book=book,
        leg=leg,
        family=leg,
        judge=judge,
        self_family=self_family,
        scores={} if error else dict.fromkeys(_CRITERIA_NAMES, value),
        notes={},
        error=error,
    )


def test_parse_reads_the_nested_score_and_note_shape() -> None:
    """The requested shape parses into scores and their justifications."""
    raw = json.dumps({name: {"score": 4, "note": "n"} for name in _CRITERIA_NAMES})

    scores, notes = _parse(raw)

    assert scores["voice"] == 4.0
    assert notes["voice"] == "n"


def test_parse_accepts_a_bare_number_per_criterion() -> None:
    """A judge that answers with plain numbers is still usable.

    Models drift from a requested JSON shape under load. Discarding an otherwise
    complete scoring over a missing wrapper object would silently shrink the
    panel, and a shrinking panel changes the pooled verdict.
    """
    raw = json.dumps(dict.fromkeys(_CRITERIA_NAMES, 3))

    scores, _ = _parse(raw)

    assert scores["imagery"] == 3.0


def test_parse_finds_the_object_inside_surrounding_prose() -> None:
    """A judge that adds commentary around the JSON is still parsed."""
    body = json.dumps(dict.fromkeys(_CRITERIA_NAMES, 2))

    scores, _ = _parse(f"Here are my scores:\n{body}\nHappy to expand.")

    assert scores["age_fit"] == 2.0


def test_parse_calls_a_truncated_reply_truncated_not_malformed() -> None:
    """A cut-off completion must point at the budget, not at the judge.

    This is the exact shape that silently removed one of three judges from the
    2026-08-12 panel: the greedy object regex closes on the last *inner* brace
    the completion managed to emit, so a truncated reply arrives at ``json.loads``
    as an unbalanced object and every error landed at the same line and column.
    Read as malformed JSON it looks like a judge that cannot follow a schema, and
    the fix would be to loosen the parse. The real fix is the opposite.
    """
    # The observed 2026-08-12 shape: one criterion closed, the next cut mid-note.
    truncated = (
        '{\n  "age_fit": {\n    "score": 5,\n    "note": "Short sentences."\n  },'
        '\n  "imagery": {\n    "score": 5,\n    "note": "The text is rich with'
    )

    with pytest.raises(ValueError, match="cut off") as excinfo:
        _ = _parse(truncated)

    assert "_JUDGE_MAX_TOKENS" in str(excinfo.value)


def test_parse_diagnoses_a_reply_cut_off_before_any_brace_closed() -> None:
    """The same cause with no closing brace at all must give the same guidance."""
    with pytest.raises(ValueError, match="cut off") as excinfo:
        _ = _parse('{\n  "age_fit": {\n    "score": 5,\n    "note": "Short sen')

    assert "_JUDGE_MAX_TOKENS" in str(excinfo.value)


def test_judge_budget_exceeds_the_measured_answer_by_a_reasoning_margin() -> None:
    """The cap must absorb hidden reasoning, not just the seven criteria.

    Measured 2026-08-12 against one 3,000-word book: the three panel judges
    returned at most 1,530 characters of content, roughly 385 tokens. The answer
    was never the binding constraint; a 2,000-token cap still truncated every
    Gemini 3.1 Pro reply, because a reasoning judge spends its budget before it
    emits a first content token. The margin below is that headroom, so this test
    fails if someone trims the cap back toward the size of the answer.
    """
    measured_answer_tokens = 385

    assert measured_answer_tokens * 10 <= _JUDGE_MAX_TOKENS, (
        f"a {_JUDGE_MAX_TOKENS}-token cap leaves too little headroom over the "
        f"measured {measured_answer_tokens}-token answer; reasoning judges "
        "truncate mid-note and their scorings drop out of the panel silently"
    )


def test_parse_rejects_a_reply_carrying_no_criterion() -> None:
    """An unrecognised reply must raise, not return an empty scoring.

    An empty score dict that reached the pool would be a book nobody judged,
    counted as if judged.
    """
    with pytest.raises(ValueError, match="no recognised criterion"):
        _ = _parse('{"unrelated": 5}')


def test_story_text_carries_choice_labels_and_targets() -> None:
    """A judge cannot grade choice quality it cannot see.

    ``choice_quality`` asks whether the branches feel like real decisions. If
    the rendering dropped the options and where they lead, the judge would be
    scoring that criterion from the prose alone and returning a number anyway.
    """
    doc: dict[str, Any] = {
        "title": "T",
        "nodes": [
            {
                "id": "n1",
                "body": "She stopped at the gate.",
                "is_ending": False,
                "choices": [
                    {"id": "c1", "label": "Climb over", "target": "n2"},
                    {"id": "c2", "label": "Walk around", "target": "n3"},
                ],
            }
        ],
    }

    text = _story_text(doc)

    assert "Climb over" in text
    assert "Walk around" in text
    assert "n2" in text
    assert "n3" in text


def test_z_scores_survive_a_judge_who_scored_everything_the_same() -> None:
    """Zero spread must yield zero, not a division error.

    A judge awarding every book the same score carries no ordering information.
    Calling every one of its books exactly average is the honest reading, and it
    is the only one that does not crash the pool.
    """
    verdicts = [_verdict("a", "flat", "a#0", 3.0), _verdict("b", "flat", "b#0", 3.0)]

    z = _z_scores(verdicts)

    assert z["flat", "a#0"] == 0.0
    assert z["flat", "b#0"] == 0.0


def test_pool_scores_drops_a_failed_scoring_rather_than_scoring_it_zero() -> None:
    """A judge that errored on a book must not push that book down.

    Treating a transport failure as a zero would rank a leg by how reliably the
    judge's network held up, not by how well the leg wrote.
    """
    verdicts = [
        _verdict("alpha", "j1", "alpha#0", 5.0),
        _verdict("alpha", "j2", "alpha#0", 0.0, error="TimeoutError: boom"),
    ]

    pooled = pool_scores(verdicts)

    assert pooled["alpha"]["scorings"] == 1
    assert pooled["alpha"]["raw_mean"] == 5.0


def test_normalisation_stops_a_lenient_judge_outvoting_a_strict_one() -> None:
    """Pooled ordering must reflect agreement, not one judge's generosity.

    Both judges rank alpha above beta. The lenient judge scores a full point
    higher across the board, so a raw mean would let its absolute level dominate
    any leg it happened to see. After normalising within each judge, the shared
    ordering is what survives.
    """
    verdicts = [
        _verdict("alpha", "lenient", "alpha#0", 5.0),
        _verdict("beta", "lenient", "beta#0", 4.0),
        _verdict("alpha", "strict", "alpha#0", 3.0),
        _verdict("beta", "strict", "beta#0", 2.0),
    ]

    pooled = pool_scores(verdicts)

    alpha = float(pooled["alpha"]["normalised_mean"])
    beta = float(pooled["beta"]["normalised_mean"])

    # Both judges agree on the ordering, and each contributed the same distance
    # from its own mean, so the two legs must land symmetrically about zero. The
    # magnitude depends on the estimator (statistics.stdev is the sample
    # deviation) and is not the property under test; the symmetry is.
    assert alpha > beta
    assert alpha == pytest.approx(-beta)
    assert pooled["alpha"]["raw_mean"] == pytest.approx(4.0)
    assert pooled["beta"]["raw_mean"] == pytest.approx(3.0)


def test_peers_only_pooling_demotes_a_leg_its_own_lab_scored_generously() -> None:
    """A leg graded by its own lab must be checkable against rival labs alone.

    Two of this panel's three judges are the very models behind generating legs,
    so the confound is not hypothetical: those legs are partly grading
    themselves, and the leader of the pooled table is one of them. The peer
    column is the control, and it has to actually move a leg that its own lab
    favoured, or it is decoration.
    """
    verdicts = [
        _verdict("own-lab-leg", "judge-own", "own#0", 5.0, self_family=True),
        _verdict("rival-a", "judge-own", "a#0", 3.0),
        _verdict("rival-b", "judge-own", "b#0", 3.0),
        _verdict("own-lab-leg", "judge-rival", "own#0", 3.0),
        _verdict("rival-a", "judge-rival", "a#0", 4.0),
        _verdict("rival-b", "judge-rival", "b#0", 5.0),
    ]

    pooled = pool_scores(verdicts)
    peers = pool_scores(verdicts, peers_only=True)

    ranked = sorted(pooled, key=lambda leg: -float(pooled[leg]["normalised_mean"]))
    peer_ranked = sorted(peers, key=lambda leg: -float(peers[leg]["normalised_mean"]))

    assert ranked.index("own-lab-leg") == 1
    assert peer_ranked.index("own-lab-leg") == 2, (
        "dropping its own lab's generous scoring must cost the leg its place"
    )
    assert pooled["own-lab-leg"]["scorings"] == 2
    assert peers["own-lab-leg"]["scorings"] == 1

    # The legs nobody self-scored must not move at all. Their figures shift only
    # if the z-baseline was re-estimated on the shrunken set, which would mean
    # the control is also changing the judge's leniency correction rather than
    # isolating the self-scoring.
    for leg in ("rival-a", "rival-b"):
        assert peers[leg]["normalised_mean"] == pytest.approx(
            float(pooled[leg]["normalised_mean"])
        )


def test_participation_separates_a_dead_judge_from_scattered_flakiness() -> None:
    """The same failure count must read differently depending on where it lands.

    Four failures spread across three judges is flakiness and the panel is still
    cross-lab. Four failures inside one judge means that lab contributed nothing
    and the pooled figure is no longer a cross-lab verdict, even though the table
    keeps its shape and the aggregate count is identical. This is what silently
    reduced the 2026-08-12 panel from three judges to two.
    """
    scattered = [
        _verdict("alpha", "j1", "alpha#0", 4.0),
        _verdict("alpha", "j2", "alpha#0", 0.0, error="boom"),
        _verdict("beta", "j1", "beta#0", 0.0, error="boom"),
        _verdict("beta", "j2", "beta#0", 4.0),
    ]
    concentrated = [
        _verdict("alpha", "j1", "alpha#0", 4.0),
        _verdict("alpha", "j2", "alpha#0", 0.0, error="boom"),
        _verdict("beta", "j1", "beta#0", 4.0),
        _verdict("beta", "j2", "beta#0", 0.0, error="boom"),
    ]

    spread = panel_participation(scattered)
    dead = panel_participation(concentrated)

    total_failures_are_equal = sum(
        r["attempted"] - r["scored"] for r in spread.values()
    ) == sum(r["attempted"] - r["scored"] for r in dead.values())
    assert total_failures_are_equal, "the two cases must be indistinguishable by count"
    assert all(row["scored"] > 0 for row in spread.values())
    assert dead["j2"]["scored"] == 0
    assert dead["j1"]["scored"] == 2


@pytest.mark.asyncio
async def test_judge_book_records_a_provider_failure_without_raising() -> None:
    """One failed scoring must not abandon the rest of the panel's work."""

    async def _complete(**_kwargs: object) -> str:
        """Fail the way a dead endpoint does."""
        msg = "openrouter returned HTTP 502"
        raise RuntimeError(msg)

    judge = Judge("j", "m", ("p",), "openai")

    verdict = await judge_book(
        mock.Mock(complete=_complete),
        judge,
        {"title": "T", "nodes": []},
        leg="alpha",
        family="xai",
        brief_index=0,
    )

    assert verdict.error is not None
    assert "RuntimeError" in verdict.error
    assert verdict.scores == {}


@pytest.mark.asyncio
async def test_judge_book_marks_a_judge_scoring_its_own_family() -> None:
    """Self-family scoring is flagged so the bias is visible in the output.

    A model asked to rank prose favours its own lineage. The panel cannot avoid
    that entirely when a lab appears on both sides, so the fix is to mark the
    row rather than to quietly pool it with the rest.
    """

    async def _complete(**_kwargs: object) -> str:
        """Answer with a well-formed scoring."""
        return json.dumps(dict.fromkeys(_CRITERIA_NAMES, 4))

    judge = Judge("judge-gpt", "m", ("p",), "openai")

    verdict = await judge_book(
        mock.Mock(complete=_complete),
        judge,
        {"title": "T", "nodes": []},
        leg="openai-gpt-5.6-sol",
        family="openai",
        brief_index=0,
    )

    assert verdict.self_family is True
    assert verdict.error is None
