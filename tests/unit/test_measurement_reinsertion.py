"""Unit tests for the strip-all-then-reinsert sentinel fallback (plan 3.4 prototype).

Drives `reinsert_sentinels` through the algorithm's core cases with small,
hand-built pre-fill/filled node maps (no LLM, no fixtures package
involvement): a sentinel preserved verbatim, a bare word present once or
several times, a bare word absent entirely, a forged/malformed model
sentinel that must never falsely count as a match, case sensitivity,
word-boundary scoping, and the round-trip proof via
`check_sentinel_integrity`. `aggregate_reinsertion` and the two report
renderers are covered separately with hand-built trial records, mirroring
`test_measurement_report.py`'s style.
"""

from __future__ import annotations

from typing import Literal, cast

import pytest

from cyo_adventure.measurement.reinsertion import (
    ReinsertionResult,
    ReinsertionTrial,
    TokenOutcome,
    aggregate_reinsertion,
    reinsert_sentinels,
    render_json,
    render_markdown,
    strip_model_sentinels,
)
from cyo_adventure.validator.sentinel_integrity import check_sentinel_integrity


def _skeleton(nodes: list[dict[str, object]]) -> dict[str, object]:
    return {"nodes": nodes}


def _node_text(
    document: dict[str, object], *, index: int = 0, field: str = "body"
) -> str:
    nodes = cast("list[dict[str, object]]", document["nodes"])
    node = nodes[index]
    if field == "body":
        value = node["body"]
    else:
        ending = cast("dict[str, object]", node["ending"])
        value = ending["title"]
    assert isinstance(value, str)
    return value


# ---------------------------------------------------------------------------
# strip_model_sentinels
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_strip_model_sentinels_well_formed_token_becomes_inner_word() -> None:
    """A well-formed sentinel is replaced by its own captured inner value."""
    assert (
        strip_model_sentinels("The {~HERO:Explorer~} sets off.")
        == "The Explorer sets off."
    )


@pytest.mark.unit
def test_strip_model_sentinels_truncated_near_miss_recovers_inner_word() -> None:
    """An unterminated near-miss (no closer) still recovers text after the colon."""
    assert (
        strip_model_sentinels("The {~HERO:Explorer sets off.")
        == "The Explorer sets off."
    )


@pytest.mark.unit
def test_strip_model_sentinels_no_colon_near_miss_is_removed_entirely() -> None:
    """A near-miss with no colon at all has no recoverable word and is dropped."""
    result = strip_model_sentinels("The {~HERO sets off.")
    assert "{~" not in result
    assert "~}" not in result


# ---------------------------------------------------------------------------
# reinsert_sentinels: core classification cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_token_already_present_verbatim_is_reinsertable() -> None:
    """A sentinel the model preserved verbatim round-trips through strip+rewrap unchanged."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert len(result.token_outcomes) == 1
    outcome = result.token_outcomes[0]
    assert outcome.node_id == "n1"
    assert outcome.slot_id == "HERO"
    assert outcome.value == "Explorer"
    assert outcome.occurrence_count == 1
    assert outcome.status == "reinsertable"
    assert result.reinsertion_clean is True
    assert result.round_trip_ok is True
    assert _node_text(result.reinserted_document) == "The {~HERO:Explorer~} sets off."


@pytest.mark.unit
def test_bare_word_present_once_is_reinsertable() -> None:
    """A dropped sentinel whose bare inner word survives once is reinsertable."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The Explorer sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    outcome = result.token_outcomes[0]
    assert outcome.occurrence_count == 1
    assert outcome.status == "reinsertable"
    assert result.reinsertion_clean is True
    assert _node_text(result.reinserted_document) == "The {~HERO:Explorer~} sets off."


@pytest.mark.unit
def test_bare_word_present_multiple_times_wraps_every_occurrence() -> None:
    """Every occurrence of a reinsertable token's value gets wrapped, not just the first."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton(
        [{"id": "n1", "body": "Explorer waved. Explorer smiled. Explorer left."}]
    )
    result = reinsert_sentinels(pre_fill, filled)

    outcome = result.token_outcomes[0]
    assert outcome.occurrence_count == 3
    assert outcome.status == "reinsertable"
    reinserted_body = _node_text(result.reinserted_document)
    assert reinserted_body.count("{~HERO:Explorer~}") == 3
    assert result.reinsertion_clean is True
    assert result.round_trip_ok is True


@pytest.mark.unit
def test_word_absent_is_not_found() -> None:
    """A fully paraphrased sentence with no trace of the word is not_found."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "A brave adventurer sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    outcome = result.token_outcomes[0]
    assert outcome.occurrence_count == 0
    assert outcome.status == "not_found"
    assert result.reinsertion_clean is False
    # Nothing is wrapped for a not_found token.
    assert "{~" not in _node_text(result.reinserted_document)


@pytest.mark.unit
def test_forged_sentinel_is_stripped_before_matching() -> None:
    """A well-formed sentinel wrapping the WRONG word never counts as a match.

    The model can emit sentinel-shaped syntax around any text; that syntax is
    never trusted. Here the fill wraps an invented word ("Vagabond") instead
    of the expected "Explorer"; after normalization the node's text contains
    the literal word "Vagabond", not "Explorer", so the HERO:Explorer
    expectation is correctly not_found even though a well-formed-looking
    sentinel was present in the raw fill.
    """
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The {~HERO:Vagabond~} sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    outcome = result.token_outcomes[0]
    assert outcome.status == "not_found"
    assert outcome.occurrence_count == 0
    normalized_body = _node_text(result.normalized_document)
    assert "{~" not in normalized_body
    assert "Vagabond" in normalized_body
    assert result.round_trip_ok is False


@pytest.mark.unit
def test_case_sensitive_lowercase_does_not_match() -> None:
    """A lowercase mention of the word does not satisfy a case-sensitive expected value."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The explorer sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    outcome = result.token_outcomes[0]
    assert outcome.occurrence_count == 0
    assert outcome.status == "not_found"


@pytest.mark.unit
def test_word_boundary_excludes_match_inside_a_longer_word() -> None:
    """ "Explorer" does not match inside "Explorers" (deliberate word-boundary scoping).

    See `cyo_adventure.measurement.reinsertion._word_boundary_pattern`'s
    docstring: matching inside a longer, unrelated word would corrupt prose
    the fill LLM wrote for its own reasons, so a whole-word match is
    required at both ends of the literal value.
    """
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The Explorers set off together."}])
    result = reinsert_sentinels(pre_fill, filled)

    outcome = result.token_outcomes[0]
    assert outcome.occurrence_count == 0
    assert outcome.status == "not_found"


@pytest.mark.unit
def test_ending_title_expected_token_is_reinsertable() -> None:
    """A token expected in an ending title (not just the body) is scored and reinsertable."""
    pre_fill = _skeleton(
        [
            {
                "id": "n1",
                "body": "Plain beats guidance, no slot.",
                "ending": {"title": "The {~HERO:Explorer~} Returns"},
            }
        ]
    )
    filled = _skeleton(
        [
            {
                "id": "n1",
                "body": "Plain beats guidance, no slot.",
                "ending": {"title": "The Explorer Returns"},
            }
        ]
    )
    result = reinsert_sentinels(pre_fill, filled)

    outcome = result.token_outcomes[0]
    assert outcome.status == "reinsertable"
    assert (
        _node_text(result.reinserted_document, field="ending_title")
        == "The {~HERO:Explorer~} Returns"
    )


@pytest.mark.unit
def test_two_distinct_tokens_in_same_node_wrap_independently() -> None:
    """Two different expected tokens in one node are counted and wrapped without interference."""
    pre_fill = _skeleton(
        [{"id": "n1", "body": "{~PET:Buddy~} chased {~FRIEND:Max~} around the yard."}]
    )
    filled = _skeleton([{"id": "n1", "body": "Buddy chased Max around the yard."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert result.reinsertion_clean is True
    assert result.round_trip_ok is True
    body = _node_text(result.reinserted_document)
    assert "{~PET:Buddy~}" in body
    assert "{~FRIEND:Max~}" in body


@pytest.mark.unit
def test_round_trip_ok_when_reinsertion_clean() -> None:
    """A clean reinsertion, checked independently, passes the same integrity gate the pipeline trusts."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The brave Explorer sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert result.reinsertion_clean is True
    assert result.round_trip_ok is True
    independent_check = check_sentinel_integrity(pre_fill, result.reinserted_document)
    assert independent_check.ok is True


@pytest.mark.unit
def test_round_trip_not_ok_when_a_token_is_not_found() -> None:
    """A not_found token leaves the reinserted document short one sentinel, failing the round-trip proof."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "A brave adventurer sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert result.reinsertion_clean is False
    assert result.round_trip_ok is False
    independent_check = check_sentinel_integrity(pre_fill, result.reinserted_document)
    assert independent_check.ok is False


@pytest.mark.unit
def test_no_expected_tokens_is_not_clean() -> None:
    """A bound skeleton with zero expected tokens is a non-data-point, not a vacuous pass."""
    pre_fill = _skeleton([{"id": "n1", "body": "Plain beats guidance, no slot."}])
    filled = _skeleton([{"id": "n1", "body": "A perfectly ordinary sentence."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert result.token_outcomes == ()
    assert result.reinsertion_clean is False


# ---------------------------------------------------------------------------
# aggregate_reinsertion / render_json / render_markdown
# ---------------------------------------------------------------------------


def _outcome(
    status: Literal["reinsertable", "not_found"],
    count: int,
    *,
    node_id: str = "n1",
    slot_id: str = "HERO",
    value: str = "Explorer",
) -> TokenOutcome:
    return TokenOutcome(
        node_id=node_id,
        slot_id=slot_id,
        value=value,
        occurrence_count=count,
        status=status,
    )


def _result(
    outcomes: list[TokenOutcome], *, clean: bool, round_trip_ok: bool
) -> ReinsertionResult:
    return ReinsertionResult(
        normalized_document={},
        reinserted_document={},
        token_outcomes=tuple(outcomes),
        reinsertion_clean=clean,
        round_trip_ok=round_trip_ok,
    )


@pytest.mark.unit
def test_aggregate_reinsertion_empty_trials_raises() -> None:
    """Aggregating an empty trial sequence is a caller error, not a silent zero."""
    with pytest.raises(ValueError, match="empty reinsertion trial sequence"):
        aggregate_reinsertion([])


@pytest.mark.unit
def test_aggregate_reinsertion_rates_and_histograms() -> None:
    """Clean rate, round-trip rate, per-provider split, and both histograms are exact."""
    trials = [
        ReinsertionTrial(
            specimen_slug="s0",
            provider="mock",
            result=_result(
                [_outcome("reinsertable", 1)], clean=True, round_trip_ok=True
            ),
        ),
        ReinsertionTrial(
            specimen_slug="s1",
            provider="mock",
            result=_result(
                [
                    _outcome("reinsertable", 3),
                    _outcome("not_found", 0, slot_id="SIB", value="Buddy"),
                ],
                clean=False,
                round_trip_ok=False,
            ),
        ),
        ReinsertionTrial(
            specimen_slug="s2",
            provider="ollama",
            result=_result(
                [_outcome("reinsertable", 5)], clean=True, round_trip_ok=True
            ),
        ),
    ]
    data = aggregate_reinsertion(trials)

    assert data.total_trials == 3
    assert data.clean_trials == 2
    assert data.reinsertion_clean_rate == pytest.approx(2 / 3)
    assert data.round_trip_ok_trials == 2
    assert data.round_trip_ok_rate == pytest.approx(2 / 3)

    by_provider = {stats.provider: stats for stats in data.per_provider}
    assert by_provider["mock"].total == 2
    assert by_provider["mock"].clean == 1
    assert by_provider["mock"].clean_rate == pytest.approx(0.5)
    assert by_provider["ollama"].total == 1
    assert by_provider["ollama"].clean == 1

    assert data.outcome_histogram == {"reinsertable": 3, "not_found": 1}
    assert data.multiplicity_histogram == {"1": 1, "2-3": 1, "4+": 1}


@pytest.mark.unit
def test_render_json_shape() -> None:
    """render_json emits every field aggregate_reinsertion computed, JSON-serializable."""
    trials = [
        ReinsertionTrial(
            specimen_slug="s0",
            provider="mock",
            result=_result(
                [_outcome("reinsertable", 1)], clean=True, round_trip_ok=True
            ),
        )
    ]
    data = aggregate_reinsertion(trials)
    payload = render_json(data)

    assert payload["total_trials"] == 1
    assert payload["clean_trials"] == 1
    assert payload["reinsertion_clean_rate"] == pytest.approx(1.0)
    assert payload["per_provider"] == [
        {"provider": "mock", "total": 1, "clean": 1, "clean_rate": pytest.approx(1.0)}
    ]
    assert payload["outcome_histogram"] == {"reinsertable": 1}
    assert payload["multiplicity_histogram"] == {"1": 1}


@pytest.mark.unit
def test_render_markdown_contains_headline_numbers() -> None:
    """render_markdown surfaces the clean rate and round-trip rate in prose."""
    trials = [
        ReinsertionTrial(
            specimen_slug="s0",
            provider="mock",
            result=_result(
                [_outcome("not_found", 0)], clean=False, round_trip_ok=False
            ),
        )
    ]
    data = aggregate_reinsertion(trials)
    markdown = render_markdown(data)

    assert "Strip-all-then-reinsert clean rate" in markdown
    assert "Round-trip integrity-check pass rate" in markdown
    assert "not_found" in markdown
