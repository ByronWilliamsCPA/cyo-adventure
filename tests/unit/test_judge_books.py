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
    Judge,
    Verdict,
    _parse,  # pyright: ignore[reportPrivateUsage]
    _story_text,  # pyright: ignore[reportPrivateUsage]
    _z_scores,  # pyright: ignore[reportPrivateUsage]
    judge_book,
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
    leg: str, judge: str, book: str, value: float, *, error: str | None = None
) -> Verdict:
    """Build a verdict scoring every criterion at one value.

    Args:
        leg: The generating leg.
        judge: The scoring judge.
        book: The book identifier.
        value: The score to give every criterion.
        error: Failure text, or ``None`` for a successful scoring.

    Returns:
        The verdict.
    """
    return Verdict(
        book=book,
        leg=leg,
        family=leg,
        judge=judge,
        self_family=False,
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
