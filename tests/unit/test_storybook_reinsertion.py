"""Unit tests for the strip-all-then-reinsert sentinel transform (ADR-023 Stage R Task R2).

Drives `reinsert_storybook` through the algorithm's core cases with small,
hand-built pre-fill/filled node maps (no LLM, no fixtures package
involvement): a sentinel preserved verbatim, a bare word present once or
several times, a bare word absent entirely, a forged/malformed model
sentinel that must never falsely count as a match, case sensitivity,
word-boundary scoping, and the manifest contract (shape, JSON-serializability,
deterministic ordering, body vs ending-title keying, and the by-construction
round-trip property via `verify_manifest`). Aggregation across trials and the
report renderers stay in `test_measurement_reinsertion.py`, since those are
measurement-specific concerns; this file only exercises the promoted domain
transform.
"""

from __future__ import annotations

import json
from typing import cast

import pytest

from cyo_adventure.storybook.reinsertion import (
    MANIFEST_ENDING_TITLE_SUFFIX,
    ReinsertionOutcome,
    build_manifest,
    reinsert_storybook,
    strip_model_sentinels,
    verify_manifest,
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
# reinsert_storybook: core classification cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_token_already_present_verbatim_is_reinsertable() -> None:
    """A sentinel the model preserved verbatim round-trips through strip+rewrap unchanged."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    assert len(outcome.token_outcomes) == 1
    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.node_id == "n1"
    assert token_outcome.slot_id == "HERO"
    assert token_outcome.value == "Explorer"
    assert token_outcome.occurrence_count == 1
    assert token_outcome.status == "reinsertable"
    assert _node_text(outcome.document) == "The {~HERO:Explorer~} sets off."


@pytest.mark.unit
def test_bare_word_present_once_is_reinsertable() -> None:
    """A dropped sentinel whose bare inner word survives once is reinsertable."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The Explorer sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.occurrence_count == 1
    assert token_outcome.status == "reinsertable"
    assert _node_text(outcome.document) == "The {~HERO:Explorer~} sets off."


@pytest.mark.unit
def test_bare_word_present_multiple_times_wraps_every_occurrence() -> None:
    """Every occurrence of a reinsertable token's value gets wrapped, not just the first."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton(
        [{"id": "n1", "body": "Explorer waved. Explorer smiled. Explorer left."}]
    )
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.occurrence_count == 3
    assert token_outcome.status == "reinsertable"
    body = _node_text(outcome.document)
    assert body.count("{~HERO:Explorer~}") == 3


@pytest.mark.unit
def test_word_absent_is_not_found() -> None:
    """A fully paraphrased sentence with no trace of the word is not_found."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "A brave adventurer sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.occurrence_count == 0
    assert token_outcome.status == "not_found"
    # Nothing is wrapped for a not_found token.
    assert "{~" not in _node_text(outcome.document)


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
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.status == "not_found"
    assert token_outcome.occurrence_count == 0
    document_body = _node_text(outcome.document)
    assert "{~" not in document_body
    assert "Vagabond" in document_body
    independent_check = check_sentinel_integrity(pre_fill, outcome.document)
    assert independent_check.ok is False


@pytest.mark.unit
def test_case_sensitive_lowercase_does_not_match() -> None:
    """A lowercase mention of the word does not satisfy a case-sensitive expected value."""
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The explorer sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.occurrence_count == 0
    assert token_outcome.status == "not_found"


@pytest.mark.unit
def test_word_boundary_excludes_match_inside_a_longer_word() -> None:
    """ "Explorer" does not match inside "Explorers" (deliberate word-boundary scoping).

    See `cyo_adventure.storybook.reinsertion._word_boundary_pattern`'s
    docstring: matching inside a longer, unrelated word would corrupt prose
    the fill LLM wrote for its own reasons, so a whole-word match is
    required at both ends of the literal value.
    """
    pre_fill = _skeleton([{"id": "n1", "body": "The {~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "The Explorers set off together."}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.occurrence_count == 0
    assert token_outcome.status == "not_found"


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
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.status == "reinsertable"
    assert (
        _node_text(outcome.document, field="ending_title")
        == "The {~HERO:Explorer~} Returns"
    )


@pytest.mark.unit
def test_two_distinct_tokens_in_same_node_wrap_independently() -> None:
    """Two different expected tokens in one node are counted and wrapped without interference."""
    pre_fill = _skeleton(
        [{"id": "n1", "body": "{~PET:Buddy~} chased {~FRIEND:Max~} around the yard."}]
    )
    filled = _skeleton([{"id": "n1", "body": "Buddy chased Max around the yard."}])
    outcome = reinsert_storybook(pre_fill, filled)

    body = _node_text(outcome.document)
    assert "{~PET:Buddy~}" in body
    assert "{~FRIEND:Max~}" in body


@pytest.mark.unit
def test_no_expected_tokens_yields_no_outcomes() -> None:
    """A bound skeleton with zero expected tokens produces zero token outcomes."""
    pre_fill = _skeleton([{"id": "n1", "body": "Plain beats guidance, no slot."}])
    filled = _skeleton([{"id": "n1", "body": "A perfectly ordinary sentence."}])
    outcome = reinsert_storybook(pre_fill, filled)

    assert outcome.token_outcomes == ()
    assert outcome.manifest == {"tokens": {}}


# ---------------------------------------------------------------------------
# Widening 1: sentence-start capitalization matching
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sentence_start_variant_after_period_is_reinsertable() -> None:
    """A lowercase-value token appearing capitalized right after ". " is reinsertable."""
    pre_fill = _skeleton(
        [{"id": "n1", "body": "The dog ran. {~COMPANION:the pup~} barked."}]
    )
    filled = _skeleton([{"id": "n1", "body": "The dog ran. The pup barked."}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.value == "the pup"
    assert token_outcome.occurrence_count == 1
    assert token_outcome.status == "reinsertable"
    assert outcome.sentence_start_hits == 1
    assert _node_text(outcome.document) == "The dog ran. {~COMPANION:The pup~} barked."


@pytest.mark.unit
def test_sentence_start_variant_at_start_of_text_is_reinsertable() -> None:
    """A lowercase-value token capitalized at the very start of the text is reinsertable."""
    pre_fill = _skeleton([{"id": "n1", "body": "{~COMPANION:the pup~} dashed off."}])
    filled = _skeleton([{"id": "n1", "body": "The pup dashed off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.status == "reinsertable"
    assert outcome.sentence_start_hits == 1
    assert _node_text(outcome.document) == "{~COMPANION:The pup~} dashed off."


@pytest.mark.unit
def test_sentence_start_variant_after_newline_is_reinsertable() -> None:
    """A lowercase-value token capitalized at the start of a new line is reinsertable."""
    pre_fill = _skeleton(
        [{"id": "n1", "body": "Quiet night.\n{~COMPANION:the pup~} slept."}]
    )
    filled = _skeleton([{"id": "n1", "body": "Quiet night.\nThe pup slept."}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.status == "reinsertable"
    assert outcome.sentence_start_hits == 1
    assert _node_text(outcome.document) == "Quiet night.\n{~COMPANION:The pup~} slept."


@pytest.mark.unit
def test_sentence_start_variant_after_closing_quote_is_reinsertable() -> None:
    """A lowercase-value token capitalized right after a closing quote is reinsertable."""
    pre_fill = _skeleton(
        [{"id": "n1", "body": '"Stay close!" {~COMPANION:the pup~} yipped.'}]
    )
    filled = _skeleton([{"id": "n1", "body": '"Stay close!" The pup yipped.'}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.status == "reinsertable"
    assert outcome.sentence_start_hits == 1
    assert _node_text(outcome.document) == '"Stay close!" {~COMPANION:The pup~} yipped.'


@pytest.mark.unit
def test_mid_sentence_capitalized_variant_remains_a_miss() -> None:
    """A capitalized mid-sentence mention (not after a sentence terminator) stays not_found."""
    pre_fill = _skeleton([{"id": "n1", "body": "I love {~COMPANION:the pup~} dearly."}])
    filled = _skeleton([{"id": "n1", "body": "I love The pup dearly."}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.occurrence_count == 0
    assert token_outcome.status == "not_found"
    assert outcome.sentence_start_hits == 0
    assert "{~" not in _node_text(outcome.document)


@pytest.mark.unit
def test_uppercase_initial_value_is_unaffected_by_sentence_start_widening() -> None:
    """A value that already starts uppercase gets no widened matcher at all."""
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "explorer sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.occurrence_count == 0
    assert token_outcome.status == "not_found"
    assert outcome.sentence_start_hits == 0


@pytest.mark.unit
def test_mixed_node_wraps_both_cases_without_double_wrap() -> None:
    """One node with both a mid-sentence and a sentence-start mention wraps both, once each."""
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
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.occurrence_count == 2
    assert token_outcome.status == "reinsertable"
    assert outcome.sentence_start_hits == 1
    body = _node_text(outcome.document)
    assert body.count("{~COMPANION:") == 2
    assert "{~COMPANION:The pup~}" in body
    assert "{~COMPANION:the pup~}" in body
    assert "{~COMPANION:The pup~}~}" not in body
    assert verify_manifest(outcome.document, outcome.manifest) is True


@pytest.mark.unit
def test_round_trip_by_construction_with_sentence_start_only_capitalized_token() -> (
    None
):
    """`verify_manifest` accepts the transform's own output even under casing widening.

    The wrapped token's case differs from the pre-fill skeleton's own
    declared (lowercase) value; `verify_manifest` still accepts because the
    manifest is derived directly from `outcome.document`, not from
    `bound_skeleton`'s declared casing. An independent check against the raw
    `bound_skeleton` legitimately still fails on the byte-exact casing
    mismatch, which is why the two diverge here (see the module docstring's
    "round trip by construction" note).
    """
    pre_fill = _skeleton([{"id": "n1", "body": "{~COMPANION:the pup~} dashed off."}])
    filled = _skeleton([{"id": "n1", "body": "The pup dashed off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    assert _node_text(outcome.document) == "{~COMPANION:The pup~} dashed off."
    assert verify_manifest(outcome.document, outcome.manifest) is True
    independent_check = check_sentinel_integrity(pre_fill, outcome.document)
    assert independent_check.ok is False


# ---------------------------------------------------------------------------
# Widening 2: possessive matching (already-supported) and plural reporting
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_possessive_apostrophe_wraps_the_stem_and_round_trips() -> None:
    """The apostrophe in a possessive is a non-word char, so `\\b` finds the stem.

    The possessive suffix (`'s`) is left outside the wrap, and since the
    wrapped value matches the pre-fill skeleton's own declared value exactly
    (no case shift involved), the round-trip proof passes via the
    pre-existing, unmodified mechanism.
    """
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} grinned."}])
    filled = _skeleton([{"id": "n1", "body": "Explorer's compass spun."}])
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.occurrence_count == 1
    assert token_outcome.status == "reinsertable"
    assert _node_text(outcome.document) == "{~HERO:Explorer~}'s compass spun."
    assert verify_manifest(outcome.document, outcome.manifest) is True


@pytest.mark.unit
def test_plural_form_is_counted_but_not_wrapped() -> None:
    """A plural mention ("Explorers") is counted, not matched or wrapped."""
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} grinned."}])
    filled = _skeleton(
        [{"id": "n1", "body": "Explorers gathered. Explorer waved to them."}]
    )
    outcome = reinsert_storybook(pre_fill, filled)

    token_outcome = outcome.token_outcomes[0]
    assert token_outcome.occurrence_count == 1
    assert token_outcome.status == "reinsertable"
    assert outcome.plural_occurrences == 1
    body = _node_text(outcome.document)
    assert body == "Explorers gathered. {~HERO:Explorer~} waved to them."
    assert "{~HERO:Explorers~}" not in body


# ---------------------------------------------------------------------------
# The manifest contract: shape, JSON-serializability, deterministic ordering,
# body vs ending-title keying, and the by-construction round-trip property.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_manifest_records_body_and_ending_title_under_distinct_keys() -> None:
    """A node with both a body and an ending-title sentinel gets two manifest keys."""
    pre_fill = _skeleton(
        [
            {
                "id": "n1",
                "body": "{~HERO:Explorer~} sets off.",
                "ending": {"title": "{~HERO:Explorer~} Returns"},
            }
        ]
    )
    filled = _skeleton(
        [
            {
                "id": "n1",
                "body": "Explorer sets off.",
                "ending": {"title": "Explorer Returns"},
            }
        ]
    )
    outcome = reinsert_storybook(pre_fill, filled)

    tokens = cast("dict[str, object]", outcome.manifest["tokens"])
    assert set(tokens) == {"n1", f"n1{MANIFEST_ENDING_TITLE_SUFFIX}"}
    body_entries = cast("list[dict[str, object]]", tokens["n1"])
    title_entries = cast(
        "list[dict[str, object]]", tokens[f"n1{MANIFEST_ENDING_TITLE_SUFFIX}"]
    )
    assert body_entries == [{"slot_id": "HERO", "value": "Explorer", "count": 1}]
    assert title_entries == [{"slot_id": "HERO", "value": "Explorer", "count": 1}]


@pytest.mark.unit
def test_manifest_records_the_actual_occurrence_multiset() -> None:
    """A token wrapped three times in one node's body is recorded with count 3."""
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} sets off."}])
    filled = _skeleton(
        [{"id": "n1", "body": "Explorer waved. Explorer smiled. Explorer left."}]
    )
    outcome = reinsert_storybook(pre_fill, filled)

    tokens = cast("dict[str, object]", outcome.manifest["tokens"])
    assert tokens["n1"] == [{"slot_id": "HERO", "value": "Explorer", "count": 3}]


@pytest.mark.unit
def test_manifest_is_json_serializable() -> None:
    """The manifest round-trips cleanly through json.dumps with no custom encoder."""
    pre_fill = _skeleton(
        [
            {
                "id": "n1",
                "body": "{~PET:Buddy~} chased {~FRIEND:Max~} around.",
                "ending": {"title": "{~PET:Buddy~} Comes Home"},
            }
        ]
    )
    filled = _skeleton(
        [
            {
                "id": "n1",
                "body": "Buddy chased Max around.",
                "ending": {"title": "Buddy Comes Home"},
            }
        ]
    )
    outcome = reinsert_storybook(pre_fill, filled)

    serialized = json.dumps(outcome.manifest)
    assert json.loads(serialized) == outcome.manifest


@pytest.mark.unit
def test_manifest_key_ordering_is_deterministic() -> None:
    """Manifest keys are emitted in sorted order regardless of node traversal order."""
    pre_fill = _skeleton(
        [
            {"id": "z1", "body": "{~HERO:Explorer~} sets off."},
            {"id": "a1", "body": "{~PET:Buddy~} chased a ball."},
        ]
    )
    filled = _skeleton(
        [
            {"id": "z1", "body": "Explorer sets off."},
            {"id": "a1", "body": "Buddy chased a ball."},
        ]
    )
    outcome = reinsert_storybook(pre_fill, filled)

    tokens = cast("dict[str, object]", outcome.manifest["tokens"])
    assert list(tokens) == sorted(tokens)
    assert list(tokens) == ["a1", "z1"]


@pytest.mark.unit
def test_build_manifest_matches_reinsert_storybook_manifest() -> None:
    """`build_manifest(document)` called directly reproduces `reinsert_storybook`'s own manifest.

    This is the manifest's defining property: it is derived straight from
    the document, not from any separate bookkeeping collected mid-transform.
    """
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "Explorer sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    assert build_manifest(outcome.document) == outcome.manifest


@pytest.mark.unit
@pytest.mark.parametrize(
    ("body_text", "filled_text"),
    [
        ("The {~HERO:Explorer~} sets off.", "The Explorer sets off."),
        (
            "{~COMPANION:the pup~} barked once. Loyally, the pup barked again.",
            "The pup barked once. Loyally, the pup barked again.",
        ),
        ("The {~HERO:Explorer~} sets off.", "A brave adventurer sets off."),
    ],
)
def test_round_trip_holds_by_construction(body_text: str, filled_text: str) -> None:
    """Property: verifying `reinsert_storybook`'s own document against its own manifest always passes.

    This holds regardless of whether every expected token was reinsertable
    (the last case here leaves HERO:Explorer not_found): the manifest never
    claims a token it did not actually place, so it can never disagree with
    the document it was derived from.
    """
    pre_fill = _skeleton([{"id": "n1", "body": body_text}])
    filled = _skeleton([{"id": "n1", "body": filled_text}])
    outcome = reinsert_storybook(pre_fill, filled)

    assert verify_manifest(outcome.document, outcome.manifest) is True


@pytest.mark.unit
def test_verify_manifest_rejects_a_mutated_document() -> None:
    """A manifest no longer matches once its document is corrupted after the fact.

    Simulates at-rest corruption (e.g. a hand-edit that drops a wrapped
    sentinel back to plain text) between manifest-creation-time and a later
    integrity re-check: `verify_manifest` must reject it.
    """
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "Explorer sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)
    assert verify_manifest(outcome.document, outcome.manifest) is True

    mutated = outcome.document
    nodes = cast("list[dict[str, object]]", mutated["nodes"])
    nodes[0]["body"] = "Explorer sets off."  # sentinel dropped back to plain text

    assert verify_manifest(mutated, outcome.manifest) is False


@pytest.mark.unit
def test_verify_manifest_rejects_a_forged_addition() -> None:
    """A document with an extra sentinel the manifest never claimed is also rejected."""
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "Explorer sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    mutated = outcome.document
    nodes = cast("list[dict[str, object]]", mutated["nodes"])
    nodes[0]["body"] = "{~HERO:Explorer~} sets off. {~SIB:Buddy~} tagged along."

    assert verify_manifest(mutated, outcome.manifest) is False


@pytest.mark.unit
def test_verify_manifest_accepts_an_empty_manifest_for_a_sentinel_free_document() -> (
    None
):
    """A document with no expected tokens produces an empty manifest that verifies clean."""
    pre_fill = _skeleton([{"id": "n1", "body": "Plain beats guidance, no slot."}])
    filled = _skeleton([{"id": "n1", "body": "A perfectly ordinary sentence."}])
    outcome = reinsert_storybook(pre_fill, filled)

    assert outcome.manifest == {"tokens": {}}
    assert verify_manifest(outcome.document, outcome.manifest) is True


@pytest.mark.unit
def test_reinsertion_outcome_is_a_frozen_dataclass() -> None:
    """`ReinsertionOutcome` carries exactly the documented production contract fields."""
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "Explorer sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    assert isinstance(outcome, ReinsertionOutcome)
    assert set(ReinsertionOutcome.__dataclass_fields__) == {
        "document",
        "manifest",
        "token_outcomes",
        "sentence_start_hits",
        "plural_occurrences",
    }
