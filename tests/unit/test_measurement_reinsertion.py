"""Unit tests for the measurement-only glue over the promoted sentinel transform.

The pure strip-all-then-reinsert transform (sentinel stripping, matcher
machinery, the manifest contract) now lives in
`cyo_adventure.storybook.reinsertion` and is covered by
`tests/unit/test_storybook_reinsertion.py`. This file covers what stays
measurement-specific: `reinsert_sentinels`'s reconstruction of the legacy,
`bound_skeleton`-relative `round_trip_ok`/`reinsertion_clean` statistics (a
stricter, fidelity-to-the-original-expectations check than the domain
module's own `verify_manifest`, which only proves a document matches its own
derived manifest), plus `aggregate_reinsertion` and the two report renderers,
mirroring `test_measurement_report.py`'s style.
"""

from __future__ import annotations

from typing import Literal, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.measurement.reinsertion import (
    ReinsertionResult,
    ReinsertionTrial,
    TokenOutcome,
    _multiplicity_bucket,
    _patch_node_reference,
    aggregate_reinsertion,
    reinsert_sentinels,
    render_json,
    render_markdown,
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
# reinsert_sentinels: the legacy round_trip_ok / reinsertion_clean glue
# ---------------------------------------------------------------------------
#
# These exercise `_fidelity_reference` indirectly: it rebuilds a
# bound_skeleton-relative reference document (patched with the verbatim
# casing/variant each reinsertable token actually used) and checks it against
# `outcome.document` via `check_sentinel_integrity`. This is a stronger,
# more failure-sensitive statistic than `verify_manifest`, which only proves
# self-consistency between a document and its own derived manifest and would
# be trivially True in every one of these cases.


@pytest.mark.unit
def test_round_trip_ok_when_reinsertion_clean() -> None:
    """A clean reinsertion, checked independently, passes the same integrity gate the pipeline trusts."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The brave Explorer sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert result.reinsertion_clean is True
    assert result.round_trip_ok is True
    independent_check = check_sentinel_integrity(pre_fill, result.document)
    assert independent_check.ok is True


@pytest.mark.unit
def test_round_trip_not_ok_when_a_token_is_not_found() -> None:
    """A not_found token leaves the reinserted document short one sentinel, failing the round-trip proof."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "A brave adventurer sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert result.reinsertion_clean is False
    assert result.round_trip_ok is False
    independent_check = check_sentinel_integrity(pre_fill, result.document)
    assert independent_check.ok is False


@pytest.mark.unit
def test_no_expected_tokens_is_not_clean() -> None:
    """A bound skeleton with zero expected tokens is a non-data-point, not a vacuous pass."""
    pre_fill = _skeleton([{"id": "n1", "body": "Plain beats guidance, no slot."}])
    filled = _skeleton([{"id": "n1", "body": "A perfectly ordinary sentence."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert result.token_outcomes == ()
    assert result.reinsertion_clean is False


@pytest.mark.unit
def test_round_trip_ok_with_sentence_start_only_capitalized_token() -> None:
    """Round-trip integrity passes with a verbatim capitalized token.

    The wrapped token's case differs from the pre-fill skeleton's own
    declared (lowercase) value; `round_trip_ok` still passes because it
    compares against a derived reference that records the verbatim variant
    actually inserted (see `reinsert_sentinels`'s docstring), not the raw,
    unmodified `bound_skeleton`. An independent check against the raw
    `bound_skeleton` legitimately still fails on the byte-exact casing
    mismatch, which is why the two diverge here.
    """
    pre_fill = _skeleton([{"id": "n1", "body": "{~COMPANION:the pup~} dashed off."}])
    filled = _skeleton([{"id": "n1", "body": "The pup dashed off."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert result.reinsertion_clean is True
    assert result.round_trip_ok is True
    assert _node_text(result.document) == "{~COMPANION:The pup~} dashed off."
    independent_check = check_sentinel_integrity(pre_fill, result.document)
    assert independent_check.ok is False


@pytest.mark.unit
def test_round_trip_ok_with_mixed_case_variants_in_one_node() -> None:
    """Both the mid-sentence and sentence-start variants of one token round-trip together."""
    pre_fill = _skeleton(
        [
            {
                "id": "n1",
                "body": (
                    "{~COMPANION:the pup~} barked once. Loyally, the pup barked again."
                ),
            }
        ]
    )
    filled = _skeleton(
        [{"id": "n1", "body": "The pup barked once. Loyally, the pup barked again."}]
    )
    result = reinsert_sentinels(pre_fill, filled)

    assert result.reinsertion_clean is True
    assert result.round_trip_ok is True


@pytest.mark.unit
def test_possessive_apostrophe_wraps_the_stem_and_round_trips() -> None:
    """The apostrophe in a possessive is a non-word char, so `\\b` finds the stem.

    The possessive suffix (`'s`) is left outside the wrap, and since the
    wrapped value matches the pre-fill skeleton's own declared value exactly
    (no case shift involved), the round-trip proof passes via the
    unmodified reference-patching mechanism.
    """
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} grinned."}])
    filled = _skeleton([{"id": "n1", "body": "Explorer's compass spun."}])
    result = reinsert_sentinels(pre_fill, filled)

    outcome = result.token_outcomes[0]
    assert outcome.occurrence_count == 1
    assert outcome.status == "reinsertable"
    assert _node_text(result.document) == "{~HERO:Explorer~}'s compass spun."
    assert result.round_trip_ok is True


# ---------------------------------------------------------------------------
# verify_manifest_ok: the G1-R gate metric, distinct from round_trip_ok
# ---------------------------------------------------------------------------
#
# round_trip_ok proves fidelity to the ORIGINAL bound_skeleton's declared
# expectations (measurement-specific, see the module docstring).
# verify_manifest_ok proves the reinserted document is self-consistent with
# its OWN derived manifest, via storybook.reinsertion.verify_manifest; it is
# the required-100% gate metric for G1-R because any failure there is a
# transform bug in reinsert_storybook itself, not a fill-quality signal.


@pytest.mark.unit
def test_verify_manifest_ok_true_on_a_normal_trial() -> None:
    """verify_manifest_ok passes on an ordinary clean reinsertion."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The brave Explorer sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert result.verify_manifest_ok is True


@pytest.mark.unit
def test_verify_manifest_ok_true_even_when_round_trip_ok_is_false() -> None:
    """verify_manifest_ok is distinct from round_trip_ok: a not_found token still passes it.

    A not_found token fails round_trip_ok (the document no longer carries
    every token the ORIGINAL bound_skeleton declared), but the document
    remains self-consistent with the manifest reinsert_storybook derived
    FROM it, so verify_manifest_ok still passes. This is the behavior that
    makes verify_manifest_ok the right required-100% gate metric: a fill
    that paraphrases a word away is a fill-quality problem, not a transform
    bug, and must not fail the transform's own gate.
    """
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "A brave adventurer sets off."}])
    result = reinsert_sentinels(pre_fill, filled)

    assert result.round_trip_ok is False
    assert result.verify_manifest_ok is True


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
    outcomes: list[TokenOutcome],
    *,
    clean: bool,
    round_trip_ok: bool,
    verify_manifest_ok: bool = True,
    sentence_start_hits: int = 0,
    plural_occurrences: int = 0,
) -> ReinsertionResult:
    return ReinsertionResult(
        document={},
        manifest={"tokens": {}},
        token_outcomes=tuple(outcomes),
        reinsertion_clean=clean,
        round_trip_ok=round_trip_ok,
        verify_manifest_ok=verify_manifest_ok,
        sentence_start_hits=sentence_start_hits,
        plural_occurrences=plural_occurrences,
    )


@pytest.mark.unit
def test_aggregate_reinsertion_empty_trials_raises() -> None:
    """Aggregating an empty trial sequence is a caller error, not a silent zero.

    Asserts the project's own exception hierarchy, not the built-in: this
    module raised bare `ValueError`, which `core/exceptions.py` exists to
    replace so a caller can catch one family rather than guessing.
    """
    with pytest.raises(ValidationError, match="empty reinsertion trial sequence"):
        aggregate_reinsertion([])


@pytest.mark.unit
@pytest.mark.parametrize("count", [0, -1])
def test_multiplicity_bucket_rejects_non_positive_counts(count: int) -> None:
    """A count with no defined bucket raises rather than landing in one.

    The bucket boundaries are open-ended upward (4+ is "many") but closed
    downward: 0 belongs in `outcome_histogram` as "not_found", never in the
    multiplicity distribution. `aggregate_reinsertion` only calls this for a
    `"reinsertable"` outcome, and that status implies a count of at least 1,
    but the pairing is set in a different module. Raising is what makes a
    future decoupling there fail the measurement run instead of silently
    under-reporting a histogram nobody re-derives.
    """
    with pytest.raises(ValidationError, match="multiplicity bucket undefined"):
        _multiplicity_bucket(count)


@pytest.mark.unit
def test_multiplicity_bucket_boundaries() -> None:
    """The three buckets split at exactly 1, 2-3, and 4+.

    Pins the label strings, not just the partition: these are rendered
    verbatim into `render_json`'s `multiplicity_histogram` keys, so a rename
    is a report-format change for anything reading that file.
    """
    assert [_multiplicity_bucket(n) for n in (1, 2, 3, 4, 40)] == [
        "1",
        "2-3",
        "2-3",
        "4+",
        "4+",
    ]


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
            provider="openrouter",
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
    assert by_provider["openrouter"].total == 1
    assert by_provider["openrouter"].clean == 1

    assert data.outcome_histogram == {"reinsertable": 3, "not_found": 1}
    assert data.multiplicity_histogram == {"1": 1, "2-3": 1, "4+": 1}


@pytest.mark.unit
def test_aggregate_reinsertion_sums_sentence_start_and_plural_fields() -> None:
    """sentence_start_hits and plural_occurrences sum across every trial."""
    trials = [
        ReinsertionTrial(
            specimen_slug="s0",
            provider="mock",
            result=_result(
                [_outcome("reinsertable", 1)],
                clean=True,
                round_trip_ok=True,
                sentence_start_hits=2,
                plural_occurrences=1,
            ),
        ),
        ReinsertionTrial(
            specimen_slug="s1",
            provider="mock",
            result=_result(
                [_outcome("reinsertable", 1)],
                clean=True,
                round_trip_ok=True,
                sentence_start_hits=3,
                plural_occurrences=4,
            ),
        ),
    ]
    data = aggregate_reinsertion(trials)

    assert data.sentence_start_hits == 5
    assert data.plural_occurrences == 5


@pytest.mark.unit
def test_aggregate_reinsertion_verify_manifest_ok_counts() -> None:
    """verify_manifest_ok_trials/rate aggregate independently from round_trip_ok."""
    trials = [
        ReinsertionTrial(
            specimen_slug="s0",
            provider="mock",
            result=_result(
                [_outcome("reinsertable", 1)],
                clean=True,
                round_trip_ok=True,
                verify_manifest_ok=True,
            ),
        ),
        ReinsertionTrial(
            specimen_slug="s1",
            provider="mock",
            result=_result(
                [_outcome("not_found", 0)],
                clean=False,
                round_trip_ok=False,
                verify_manifest_ok=False,
            ),
        ),
    ]
    data = aggregate_reinsertion(trials)

    assert data.verify_manifest_ok_trials == 1
    assert data.verify_manifest_ok_rate == pytest.approx(0.5)


@pytest.mark.unit
def test_aggregate_reinsertion_per_slot_coverage() -> None:
    """Per-slot coverage tallies (node, token) outcomes by slot_id, sorted by slot_id.

    Constructed scenario: HERO has 3 total expectations across two trials (2
    reinsertable, 1 not_found); SIB has 2 total expectations in one trial (1
    reinsertable, 1 not_found).
    """
    trials = [
        ReinsertionTrial(
            specimen_slug="s0",
            provider="mock",
            result=_result(
                [
                    _outcome("reinsertable", 1, slot_id="HERO", value="Explorer"),
                    _outcome("not_found", 0, slot_id="HERO", value="Wanderer"),
                ],
                clean=False,
                round_trip_ok=False,
            ),
        ),
        ReinsertionTrial(
            specimen_slug="s1",
            provider="mock",
            result=_result(
                [
                    _outcome("reinsertable", 1, slot_id="HERO", value="Adventurer"),
                    _outcome("reinsertable", 1, slot_id="SIB", value="Buddy"),
                    _outcome("not_found", 0, slot_id="SIB", value="Pal"),
                ],
                clean=False,
                round_trip_ok=False,
            ),
        ),
    ]
    data = aggregate_reinsertion(trials)

    by_slot = {stats.slot_id: stats for stats in data.per_slot_coverage}
    assert [stats.slot_id for stats in data.per_slot_coverage] == sorted(by_slot)
    assert by_slot["HERO"].reinsertable == 2
    assert by_slot["HERO"].total == 3
    assert by_slot["HERO"].coverage_rate == pytest.approx(2 / 3)
    assert by_slot["SIB"].reinsertable == 1
    assert by_slot["SIB"].total == 2
    assert by_slot["SIB"].coverage_rate == pytest.approx(0.5)


@pytest.mark.unit
def test_render_json_shape() -> None:
    """render_json emits every field aggregate_reinsertion computed, JSON-serializable."""
    trials = [
        ReinsertionTrial(
            specimen_slug="s0",
            provider="mock",
            result=_result(
                [_outcome("reinsertable", 1)],
                clean=True,
                round_trip_ok=True,
                sentence_start_hits=1,
                plural_occurrences=2,
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
    assert payload["sentence_start_hits"] == 1
    assert payload["plural_occurrences"] == 2


@pytest.mark.unit
def test_render_json_contains_verify_manifest_and_per_slot_fields() -> None:
    """render_json emits verify_manifest_ok_* and per_slot_coverage alongside the legacy fields."""
    trials = [
        ReinsertionTrial(
            specimen_slug="s0",
            provider="mock",
            result=_result(
                [
                    _outcome("reinsertable", 1, slot_id="HERO", value="Explorer"),
                    _outcome("not_found", 0, slot_id="SIB", value="Buddy"),
                ],
                clean=False,
                round_trip_ok=False,
                verify_manifest_ok=True,
            ),
        )
    ]
    data = aggregate_reinsertion(trials)
    payload = render_json(data)

    assert payload["verify_manifest_ok_trials"] == 1
    assert payload["verify_manifest_ok_rate"] == pytest.approx(1.0)
    assert payload["per_slot_coverage"] == [
        {
            "slot_id": "HERO",
            "reinsertable": 1,
            "total": 1,
            "coverage_rate": pytest.approx(1.0),
        },
        {
            "slot_id": "SIB",
            "reinsertable": 0,
            "total": 1,
            "coverage_rate": pytest.approx(0.0),
        },
    ]


@pytest.mark.unit
def test_render_markdown_contains_verify_manifest_and_per_slot_table() -> None:
    """render_markdown surfaces the verify-manifest rate and a per-slot coverage table."""
    trials = [
        ReinsertionTrial(
            specimen_slug="s0",
            provider="mock",
            result=_result(
                [
                    _outcome("reinsertable", 1, slot_id="HERO", value="Explorer"),
                    _outcome("not_found", 0, slot_id="SIB", value="Buddy"),
                ],
                clean=False,
                round_trip_ok=False,
                verify_manifest_ok=True,
            ),
        )
    ]
    data = aggregate_reinsertion(trials)
    markdown = render_markdown(data)

    assert "Verify-manifest" in markdown
    assert "Per-slot coverage" in markdown
    assert "| HERO |" in markdown
    assert "| SIB |" in markdown


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


@pytest.mark.unit
def test_render_markdown_contains_sentence_start_and_plural_numbers() -> None:
    """render_markdown surfaces the sentence-start and plural counts in prose."""
    trials = [
        ReinsertionTrial(
            specimen_slug="s0",
            provider="mock",
            result=_result(
                [_outcome("not_found", 0)],
                clean=False,
                round_trip_ok=False,
                sentence_start_hits=3,
                plural_occurrences=7,
            ),
        )
    ]
    data = aggregate_reinsertion(trials)
    markdown = render_markdown(data)

    assert "3" in markdown
    assert "7" in markdown
    assert "sentence-start" in markdown.lower()
    assert "plural" in markdown.lower()


@pytest.mark.unit
def test_empty_variant_set_leaves_the_reference_declaration_standing() -> None:
    """An empty variant set must not erase the token from the fidelity reference.

    `_patch_node_reference` replaces a node's canonical declaration with the
    join of the variants actually wrapped. Joining zero variants yields the
    empty string, which would DELETE the declaration: `check_sentinel_
    integrity` would then expect nothing for that slot and score a document
    carrying no sentinel for it as a clean round trip. The declaration has to
    survive so the same case scores as dropped.
    """
    node: dict[str, object] = {
        "id": "n1",
        "body": "The {~HERO:Explorer~} sets off.",
        "ending": {"title": "{~HERO:Explorer~} rests."},
    }

    _patch_node_reference(node, "HERO", "Explorer", frozenset())

    assert node["body"] == "The {~HERO:Explorer~} sets off."
    ending = cast("dict[str, object]", node["ending"])
    assert ending["title"] == "{~HERO:Explorer~} rests."
