"""Sentinel neutrality for the diversity gates (A19).

A stored fill may carry ADR-023 personalization sentinels (``{~SLOTID:Generic~}``)
in node bodies and choice labels. Every diversity measure must score such a fill
exactly as it scores the same fill with its sentinels already resolved to their
inner generic word, because the sentinel is a rendering instruction, not prose.

Scope note on how large the untreated effect actually was. Measured against the
two committed pilot fills of ``the-cave-of-echoes`` with every protagonist and
companion mention wrapped (113 and 108 sites), the untreated deviation was
**small**: unigram distance was unchanged, because ``HERO`` is uppercase at a
sentence-medial position and so was adopted as an entity and masked to the same
placeholder as the real name it displaced; bigram distance moved by about 0.006;
and no verdict flipped. These tests therefore guard an invariant rather than
repair a live misclassification. The invariant is worth pinning because the
cancellation was **incidental**: it depended on the slot id happening to be
uppercase and happening to appear sentence-medially, and a sentinel appearing
only sentence-initially in both fills, or a future lower-case slot id, would not
have cancelled at all.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.diversity.aggregate import pair_score
from cyo_adventure.diversity.leaf import leaf_distance_profile
from cyo_adventure.diversity.lexical import lexical_profile
from cyo_adventure.diversity.normalize import (
    extract_entities,
    mask_tokens,
)
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storybook.sentinels import strip_sentinels

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_SPACE_STATION_FILL = Path(
    "out/pilot/fills/the-cave-of-echoes.space-station.filled.json"
)
_DINO_DIG_FILL = Path("out/pilot/fills/the-cave-of-echoes.dino-dig.filled.json")

# Each pilot fill's own protagonist and companion bindings. A stored
# personalizable fill wraps its own generic binding, so the two fills share the
# slot id and differ in the inner word.
_BINDINGS: dict[Path, tuple[tuple[str, str], ...]] = {
    _SPACE_STATION_FILL: (("HERO", "Priya"), ("COMPANION", "Pip")),
    _DINO_DIG_FILL: (("HERO", "Theo"), ("COMPANION", "Comet")),
}


def _load(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def _map_prose(
    fill: Mapping[str, object], transform: Callable[[str], str]
) -> dict[str, object]:
    """Return a deep copy with ``transform`` applied to every prose string.

    Prose means node bodies and choice labels, which is the same "leaf text"
    definition the diversity modules use.
    """
    out: dict[str, object] = copy.deepcopy(dict(fill))
    nodes = cast("list[dict[str, object]]", out["nodes"])
    for node in nodes:
        body = node.get("body")
        if isinstance(body, str):
            node["body"] = transform(body)
        choices = cast("list[dict[str, object]]", node.get("choices") or [])
        for choice in choices:
            label = choice.get("label")
            if isinstance(label, str):
                choice["label"] = transform(label)
    return out


def _sentinelize(
    fill: Mapping[str, object], bindings: tuple[tuple[str, str], ...]
) -> dict[str, object]:
    """Wrap every occurrence of each generic binding in its sentinel."""
    out = dict(fill)
    for slot, generic in bindings:
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(generic)}(?![A-Za-z])")
        replacement = f"{{~{slot}:{generic}~}}"
        out = _map_prose(out, lambda text, p=pattern, r=replacement: p.sub(r, text))
    return out


def _resolve(fill: Mapping[str, object]) -> dict[str, object]:
    """Strip every sentinel back to its inner word."""
    return _map_prose(fill, strip_sentinels)


def _pair() -> tuple[Storybook, Storybook, Storybook, Storybook]:
    """Return (sentinel_a, sentinel_b, resolved_a, resolved_b)."""
    raw_a = _load(_SPACE_STATION_FILL)
    raw_b = _load(_DINO_DIG_FILL)
    sent_a = _sentinelize(raw_a, _BINDINGS[_SPACE_STATION_FILL])
    sent_b = _sentinelize(raw_b, _BINDINGS[_DINO_DIG_FILL])
    return (
        Storybook.model_validate(sent_a),
        Storybook.model_validate(sent_b),
        Storybook.model_validate(_resolve(sent_a)),
        Storybook.model_validate(_resolve(sent_b)),
    )


def test_mask_tokens_resolves_sentinels_to_inner_word() -> None:
    """The token sequence must not contain the slot id."""
    text = "{~HERO:Robin~} checked the seal and {~HERO:Robin~} frowned."
    masked = mask_tokens(text, frozenset())
    assert "hero" not in masked, "the slot id must never survive as a token"
    assert masked == mask_tokens(strip_sentinels(text), frozenset())


def test_extract_entities_does_not_adopt_the_slot_id() -> None:
    """A slot id is not a character name, however capitalized it looks.

    Regression for the specific mechanism: `HERO` is uppercase at a
    sentence-medial position, so the medial-caps scan adopted it as an entity
    and it displaced a real one from the set.
    """
    sent_a, sent_b, res_a, res_b = _pair()
    sentinel_entities = extract_entities(sent_a) | extract_entities(sent_b)
    resolved_entities = extract_entities(res_a) | extract_entities(res_b)
    assert "hero" not in sentinel_entities
    assert "companion" not in sentinel_entities
    assert sentinel_entities == resolved_entities


def test_leaf_distance_is_identical_for_a_sentinel_bearing_pair() -> None:
    """Per-node and summary leaf distances must not move at all."""
    sent_a, sent_b, res_a, res_b = _pair()
    sentinel = leaf_distance_profile(sent_a, sent_b)
    resolved = leaf_distance_profile(res_a, res_b)

    assert sentinel.entity_count == resolved.entity_count
    assert sentinel.mean_d_uni == pytest.approx(resolved.mean_d_uni)
    assert sentinel.median_d_uni == pytest.approx(resolved.median_d_uni)
    assert sentinel.p10_d_uni == pytest.approx(resolved.p10_d_uni)
    assert sentinel.min_d_uni == pytest.approx(resolved.min_d_uni)
    # The bigram statistics are the ones that actually moved before the fix,
    # because each sentinel inserted a token that shifted every bigram
    # spanning it.
    assert sentinel.mean_d_big == pytest.approx(resolved.mean_d_big)
    assert sentinel.p25_d_uni == pytest.approx(resolved.p25_d_uni)
    assert sentinel.max_d_uni == pytest.approx(resolved.max_d_uni)

    assert len(sentinel.nodes) == len(resolved.nodes)
    for got, want in zip(sentinel.nodes, resolved.nodes, strict=True):
        assert got.node_id == want.node_id
        assert got.d_uni == pytest.approx(want.d_uni)
        assert got.d_big == pytest.approx(want.d_big)
        assert got.word_count_a == want.word_count_a
        assert got.word_count_b == want.word_count_b


def test_lexical_profile_is_identical_for_a_sentinel_bearing_fill() -> None:
    """lexical.py tokenizes bodies through the same boundary."""
    sent_a, _, res_a, _ = _pair()
    got = lexical_profile(sent_a)
    want = lexical_profile(res_a)
    assert got.distinct_1 == pytest.approx(want.distinct_1)
    assert got.distinct_2 == pytest.approx(want.distinct_2)
    assert got.self_bleu_lite == pytest.approx(want.self_bleu_lite)
    assert got.content_token_count == want.content_token_count


def test_pair_score_is_identical_for_a_sentinel_bearing_pair() -> None:
    """The aggregate PS proxy must be sentinel-blind too.

    Note this is the one assertion here that is **not** load-bearing: it passes
    with and without the fix, because the aggregate rounds the per-node
    deviation away on this pair. Kept as an invariant assertion, not claimed as
    a regression guard. The other five fail without the fix.
    """
    sent_a, sent_b, res_a, res_b = _pair()
    got = pair_score(sent_a, sent_b)
    want = pair_score(res_a, res_b)
    assert got.leaf_similarity == pytest.approx(want.leaf_similarity)
    assert got.structural_similarity == pytest.approx(want.structural_similarity)
    assert got.theme_similarity == pytest.approx(want.theme_similarity)
    assert got.perceived_similarity == pytest.approx(want.perceived_similarity)
    assert got.same_tree == want.same_tree


def test_sentinel_only_at_sentence_initial_position_is_still_neutral() -> None:
    """The case the incidental entity-masking cancellation would have missed.

    A slot id is adopted as an entity only when it appears at a sentence-medial
    position. A sentinel that only ever opens a sentence was therefore never
    masked, and leaked its slot id into the content tokens. This is the case
    that makes the fix load-bearing rather than cosmetic.
    """
    resolved = "Robin opened the gate. Robin waited."
    sentinel = "{~HERO:Robin~} opened the gate. {~HERO:Robin~} waited."
    entities = frozenset({"robin"})
    assert mask_tokens(sentinel, entities) == mask_tokens(resolved, entities)
    assert "hero" not in mask_tokens(sentinel, entities)
