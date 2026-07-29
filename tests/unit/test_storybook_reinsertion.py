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
import re
import time
from typing import cast

import pytest

from cyo_adventure.storybook.reinsertion import (
    MANIFEST_ENDING_TITLE_SUFFIX,
    ReinsertionOutcome,
    _strip_trailing_closer,
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


# ---------------------------------------------------------------------------
# Nested sentinels: `re.sub` never rescans its own replacement text
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nested_sentinel_is_fully_stripped() -> None:
    """A nested forgery must not survive as an intact sentinel.

    `re.sub` never rescans its own replacement text, so removing the INNER
    token splices the surrounding remains into a new, well-formed OUTER
    token that a single pass has already walked past. A single pass turned
    ``{~HE{~A:RO~}:Explorer~}`` into the intact sentinel
    ``{~HERO:Explorer~}``, which `reinsert_storybook` would then have
    counted as a correctly re-inserted token when building the manifest.
    """
    assert strip_model_sentinels("{~HE{~A:RO~}:Explorer~}") == "Explorer"
    assert strip_model_sentinels("a {~HERO:{~X:Y~}~} b") == "a Y b"


@pytest.mark.unit
def test_nested_sentinel_leaves_no_closer_debris() -> None:
    """No bare ``~}`` survives the strip, even when its opener was dropped.

    The fixed-point loop guarantees no whole sentinel-shaped SPAN survives,
    which is not the same as no sentinel SYNTAX surviving. Stripping an
    unterminated opener orphans whatever followed it: this input resolves
    ``{~HE`` as an unterminated near-miss, drops it, and used to leave the
    outer token's own tail ``~}`` sitting in reader-facing prose.
    """
    stripped = strip_model_sentinels("{~HE{~A:R{~Q:O~}~}:Explorer~}")

    assert "~}" not in stripped
    assert "{~" not in stripped


@pytest.mark.unit
def test_trailing_closer_strip_matches_the_regex_it_replaced() -> None:
    """The linear trailer strip is behaviour-identical to its regex form.

    The regex was ``[~}]+`` followed by ``\\s*$``. Note the cases that must
    NOT strip: a closer that is not at the end (``"Explorer~} x"``) is not a
    trailer, and a later lone ``~`` claims the match ahead of an earlier
    ``~}`` run that whitespace separates from the end.
    """
    old = re.compile(r"[~}]+\s*$")
    cases = [
        "",
        "Explorer",
        "Explorer~}",
        "Explorer~} ",
        "Explorer~}~",
        "Explorer~} x",
        "Explorer~}  ~",
        "  ~}  ",
        "~",
        "}}}",
    ]

    for case in cases:
        assert _strip_trailing_closer(case) == old.sub("", case), case


@pytest.mark.unit
def test_trailing_closer_strip_is_linear_on_a_long_tilde_run() -> None:
    """A long closer run ending in a non-closer must not backtrack.

    The regex form retried at every start offset and consumed the whole
    remaining run before failing each time: quadratic, and measured at
    seconds for a 16k-tilde string inside the generation worker's fill path.
    Nothing upstream bounds how many tildes a model may emit.
    """
    hostile = "~" * 16_000 + "x"

    start = time.perf_counter()
    result = _strip_trailing_closer(hostile)
    elapsed = time.perf_counter() - start

    assert result == hostile
    assert elapsed < 0.1


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "{~HE{~A:RO~}:Explorer~}",
        "{~HERO:{~X:Y~}~}",
        "{~HE{~A:R{~Q:O~}~}:Explorer~}",
        "The {~HERO:Explorer~} met {~SIB:Buddy~}.",
        "{~HERO:Explorer",
        "{~HERO",
        "plain prose with no tokens at all",
    ],
)
def test_strip_model_sentinels_is_idempotent(text: str) -> None:
    """Stripping is a fixed point: no input strips differently on a second pass."""
    once = strip_model_sentinels(text)
    assert strip_model_sentinels(once) == once
    assert "{~" not in once


@pytest.mark.unit
def test_nested_forgery_is_not_counted_as_a_reinserted_token() -> None:
    """A nested forgery must not reach the manifest as a genuine token."""
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "{~HE{~A:RO~}:Explorer~} sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    # Exactly one HERO sentinel, the one this transform inserted itself.
    tokens = cast("dict[str, object]", outcome.manifest["tokens"])
    assert tokens == {"n1": [{"slot_id": "HERO", "value": "Explorer", "count": 1}]}
    assert _node_text(outcome.document) == "{~HERO:Explorer~} sets off."


# ---------------------------------------------------------------------------
# Value collisions: two slots bound to the same generic value
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_two_slots_sharing_one_value_report_ambiguous() -> None:
    """The slot that loses a value collision reports "ambiguous", not "reinsertable".

    One text occurrence cannot be attributed to two slots. The wrap pass has
    always resolved this by wrapping the value once for the first slot; the
    defect was reporting the LOSER as "reinsertable" while it contributed
    zero sentinels to the document and zero entries to the manifest.
    """
    pre_fill = _skeleton(
        [{"id": "n1", "body": "{~HERO:Explorer~} and {~SIDEKICK:Explorer~} set off."}]
    )
    filled = _skeleton([{"id": "n1", "body": "Explorer sets off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    by_slot = {token.slot_id: token for token in outcome.token_outcomes}
    assert by_slot["HERO"].status == "reinsertable"
    assert by_slot["SIDEKICK"].status == "ambiguous"

    # The manifest is the ground truth: only HERO is actually present.
    tokens = cast("dict[str, object]", outcome.manifest["tokens"])
    assert tokens == {"n1": [{"slot_id": "HERO", "value": "Explorer", "count": 1}]}


@pytest.mark.unit
def test_value_collision_with_the_word_absent_is_still_not_found() -> None:
    """A collision on a word the model dropped stays "not_found" for both slots."""
    pre_fill = _skeleton(
        [{"id": "n1", "body": "{~HERO:Explorer~} and {~SIDEKICK:Explorer~} set off."}]
    )
    filled = _skeleton([{"id": "n1", "body": "They set off together."}])
    outcome = reinsert_storybook(pre_fill, filled)

    assert {token.status for token in outcome.token_outcomes} == {"not_found"}


@pytest.mark.unit
def test_distinct_values_never_collide() -> None:
    """Two slots with different values both stay reinsertable."""
    pre_fill = _skeleton(
        [{"id": "n1", "body": "{~HERO:Explorer~} and {~SIDEKICK:Buddy~} set off."}]
    )
    filled = _skeleton([{"id": "n1", "body": "Explorer and Buddy set off."}])
    outcome = reinsert_storybook(pre_fill, filled)

    assert {token.status for token in outcome.token_outcomes} == {"reinsertable"}


# ---------------------------------------------------------------------------
# verify_manifest: exact per-surface, per-count comparison
# ---------------------------------------------------------------------------


def _manifest_with_hero_thrice() -> tuple[dict[str, object], dict[str, object]]:
    """Build a document carrying three HERO occurrences plus its manifest."""
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} sets off."}])
    filled = _skeleton(
        [{"id": "n1", "body": "Explorer packed. Explorer waved. Explorer left."}]
    )
    outcome = reinsert_storybook(pre_fill, filled)
    assert verify_manifest(outcome.document, outcome.manifest) is True
    return outcome.document, outcome.manifest


@pytest.mark.unit
def test_verify_manifest_rejects_a_count_only_edit() -> None:
    """Editing only a manifest `count` must fail verification.

    `check_sentinel_integrity` compares the DISTINCT token set per node, so
    delegating to it alone accepted a count edited from 3 to 99.
    """
    document, manifest = _manifest_with_hero_thrice()
    tokens = cast("dict[str, list[dict[str, object]]]", manifest["tokens"])
    assert tokens["n1"][0]["count"] == 3
    tokens["n1"][0]["count"] = 99

    assert verify_manifest(document, manifest) is False


@pytest.mark.unit
def test_verify_manifest_rejects_a_partial_occurrence_strip() -> None:
    """Stripping two of three at-rest occurrences must fail verification."""
    document, manifest = _manifest_with_hero_thrice()
    nodes = cast("list[dict[str, object]]", document["nodes"])
    nodes[0]["body"] = "Explorer packed. Explorer waved. {~HERO:Explorer~} left."

    assert verify_manifest(document, manifest) is False


@pytest.mark.unit
def test_verify_manifest_rejects_a_surface_migration() -> None:
    """Moving a sentinel from the ending title into the body must fail verification.

    Both surfaces belong to the same node, so a per-node distinct-token-set
    comparison sees no change at all; the manifest's two-key scheme is the
    only thing that records WHERE the token lived.
    """
    pre_fill = _skeleton(
        [
            {
                "id": "n1",
                "body": "{~HERO:Explorer~} sets off.",
                "ending": {"title": "{~HERO:Explorer~} comes home"},
            }
        ]
    )
    filled = _skeleton(
        [
            {
                "id": "n1",
                "body": "Explorer sets off.",
                "ending": {"title": "Explorer comes home"},
            }
        ]
    )
    outcome = reinsert_storybook(pre_fill, filled)
    manifest = outcome.manifest
    tokens = cast("dict[str, object]", manifest["tokens"])
    assert set(tokens) == {"n1", f"n1{MANIFEST_ENDING_TITLE_SUFFIX}"}

    nodes = cast("list[dict[str, object]]", outcome.document["nodes"])
    ending = cast("dict[str, object]", nodes[0]["ending"])
    nodes[0]["body"] = "{~HERO:Explorer~} sets off. {~HERO:Explorer~} comes home"
    ending["title"] = "The journey ends"

    assert verify_manifest(outcome.document, manifest) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "manifest",
    [
        {},
        {"tokens": []},
        {"tokens": {"n1": {}}},
        {"tokens": {"n1": [{"slot_id": "HERO", "value": "Explorer"}]}},
        {"tokens": {"n1": [{"slot_id": "HERO", "value": "Explorer", "count": 0}]}},
        {"tokens": {"n1": [{"slot_id": "HERO", "value": "Explorer", "count": True}]}},
        {"tokens": {"n1": [{"slot_id": 7, "value": "Explorer", "count": 1}]}},
        {"tokens": {"n1": []}},
    ],
)
def test_verify_manifest_rejects_a_malformed_manifest(
    manifest: dict[str, object],
) -> None:
    """A manifest that does not match `build_manifest`'s schema fails, never crashes.

    ``count: True`` is in this list on purpose: `bool` subclasses `int`, so a
    JSON ``true`` would otherwise be silently accepted as a count of 1.
    """
    document, _ = _manifest_with_hero_thrice()
    assert verify_manifest(document, manifest) is False


# ---------------------------------------------------------------------------
# Observability: a dropped slot is otherwise a completely silent outcome
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unreinserted_tokens_are_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A token that could not be re-inserted emits a structured warning."""
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "They set off together."}])

    with caplog.at_level("WARNING"):
        reinsert_storybook(pre_fill, filled)

    assert "reinsertion.tokens_not_reinserted" in caplog.text
    assert "HERO" in caplog.text
    # The child's personalization VALUE must never reach a log line.
    assert "Explorer" not in caplog.text


@pytest.mark.unit
def test_clean_reinsertion_logs_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A run where every expected token was re-inserted stays quiet."""
    pre_fill = _skeleton([{"id": "n1", "body": "{~HERO:Explorer~} sets off."}])
    filled = _skeleton([{"id": "n1", "body": "Explorer sets off."}])

    with caplog.at_level("WARNING"):
        reinsert_storybook(pre_fill, filled)

    assert "reinsertion.tokens_not_reinserted" not in caplog.text
