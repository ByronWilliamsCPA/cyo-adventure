"""Tests for the in-place personalization retrofit (ADR-023 content migration).

The transform under test rewrites stored, guardian-approved prose, so every
test here is about a guard rather than a happy path. Two real catalog books
carry the load: ``the-backyard-treasure-map``, whose prose names its hero
throughout, and ``the-snow-day-expedition``, whose stored blob was generated
from a binding the catalog contract no longer records. Both are tracked
under ``out/``, so these are real fills rather than hand-built fixtures that
could agree with the code by construction.

``test_a_rethemed_book_is_skipped_not_silently_zero_covered`` is named by a
``#VERIFY`` tag on :func:`plan_retrofit` and is load-bearing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.binding import load_contract_for
from cyo_adventure.storybook.sentinels import SENTINEL_RE
from scripts.retrofit_personalization import (
    RetrofitSkippedError,
    _assert_gate_neutral,
    _assert_only_wrappers_added,
    document_surfaces,
    personalizable_slot_ids,
    plan_retrofit,
    resolve_skeleton_path,
)

if TYPE_CHECKING:
    from cyo_adventure.storybook.theme_contract import ThemeContract

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_ROOT = _REPO_ROOT / "skeletons"
_FILLS = _REPO_ROOT / "out"

_NAMED_HERO_BOOK = "the-backyard-treasure-map"
_RETHEMED_BOOK = "the-snow-day-expedition"


def _load(slug: str) -> tuple[dict[str, object], ThemeContract, dict[str, object]]:
    """Return a book's skeleton, contract, and stored fill.

    Args:
        slug: The skeleton slug, which is also the fill's filename stem.

    Returns:
        tuple: ``(skeleton, contract, blob)``.
    """
    skeleton_path = resolve_skeleton_path(_CATALOG_ROOT, slug)
    skeleton = cast("dict[str, object]", json.loads(skeleton_path.read_text()))
    contract = load_contract_for(skeleton_path, skeleton)
    assert contract is not None, f"{slug} has no theme contract"
    blob = cast(
        "dict[str, object]",
        json.loads((_FILLS / f"{slug}.filled.json").read_text()),
    )
    return skeleton, contract, blob


def test_a_rethemed_book_is_skipped_not_silently_zero_covered() -> None:
    """A book whose stored binding is unrecoverable is skipped, not stamped.

    #VERIFY for the ``#CRITICAL`` data-integrity tag on ``plan_retrofit``:
    no column records the binding a stored book was generated with, so the
    contract's pinned value is an assumption. Where it is wrong, reinsertion
    quietly finds nothing and the book would be marked
    ``personalization_eligible`` while promising a personalization the
    reader never gets. Absence of the pinned value must therefore stop the
    book, not merely lower its coverage.
    """
    skeleton, contract, blob = _load(_RETHEMED_BOOK)
    pinned = contract.default_binding["HERO"]
    assert pinned not in json.dumps(blob), (
        f"{_RETHEMED_BOOK} now contains {pinned!r}; this test needs a book "
        "whose stored binding differs from its contract"
    )

    with pytest.raises(RetrofitSkippedError, match="does not appear"):
        plan_retrofit(skeleton, contract, blob)

    # Discrimination: the skip is caused by the missing value, not by
    # anything else about this book. Rename the stored hero to the pinned
    # value and the very same book plans cleanly.
    stored_hero = "June"
    rebound = cast(
        "dict[str, object]",
        json.loads(json.dumps(blob).replace(stored_hero, pinned)),
    )
    if stored_hero != pinned:
        plan = plan_retrofit(skeleton, contract, rebound)
        assert plan.tokens_reinserted > 0


def test_retrofit_only_adds_sentinel_wrappers() -> None:
    """Stripping the retrofit's sentinels reproduces the stored prose exactly.

    The strongest thing that can be said about a transform applied to
    already-approved, already-moderated text: it added wrappers and changed
    nothing a reader would see differently once resolved.
    """
    skeleton, contract, blob = _load(_NAMED_HERO_BOOK)
    plan = plan_retrofit(skeleton, contract, blob)

    assert plan.tokens_reinserted > 0
    assert any(
        SENTINEL_RE.search(text) for _, text in document_surfaces(plan.document)
    ), "retrofit produced no sentinel at all"
    _assert_only_wrappers_added(blob, plan.document)


def test_altered_prose_is_rejected_even_when_it_looks_like_a_wrapper() -> None:
    """The wrapper guard rejects a document whose text actually changed."""
    before: dict[str, object] = {
        "title": "A Map",
        "nodes": [{"id": "n1", "body": "Nina ran home."}],
    }
    good: dict[str, object] = {
        "title": "A Map",
        "nodes": [{"id": "n1", "body": "{~HERO:Nina~} ran home."}],
    }
    _assert_only_wrappers_added(before, good)

    tampered: dict[str, object] = {
        "title": "A Map",
        "nodes": [{"id": "n1", "body": "{~HERO:Nina~} ran away."}],
    }
    with pytest.raises(ValidationError, match="beyond adding sentinels"):
        _assert_only_wrappers_added(before, tampered)

    dropped: dict[str, object] = {"title": "A Map", "nodes": []}
    with pytest.raises(ValidationError, match="surface set"):
        _assert_only_wrappers_added(before, dropped)


def test_gate_neutrality_guard_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A retrofit that changes the validation verdict is rejected.

    Stubs the gate rather than hunting for a book that trips it: the guard's
    job is to stop the write on any difference, and that behaviour is what
    needs proving. A real difference has never been observed, which is
    exactly why the guard cannot be left untested.
    """
    import scripts.retrofit_personalization as module

    class _Finding:
        def __init__(self, rule_id: str) -> None:
            self.rule_id = rule_id

    class _Report:
        def __init__(self, rule_ids: list[str]) -> None:
            self.findings = [_Finding(rule_id) for rule_id in rule_ids]

    class _Result:
        def __init__(self, rule_ids: list[str], *, blocked: bool = False) -> None:
            self.report = _Report(rule_ids)
            self.blocked = blocked

    calls: list[int] = []

    def _drifting_gate(_data: object, **_kwargs: object) -> _Result:
        calls.append(1)
        return _Result(["L1-1"]) if len(calls) == 1 else _Result(["L1-1", "PL-17"])

    monkeypatch.setattr(module, "run_gate", _drifting_gate)
    with pytest.raises(ValidationError, match="changed the validation gate"):
        _assert_gate_neutral({}, {})


def test_a_contract_with_no_personalizable_slot_is_skipped() -> None:
    """An excluded skeleton is skipped rather than retrofitted empty.

    The animal-protagonist exclusions from
    ``promote_personalizable_slots.py`` reach this code as contracts with
    zero personalizable slots, and must not be stamped eligible.
    """
    skeleton, contract, blob = _load("the-lost-mitten")
    assert personalizable_slot_ids(contract) == frozenset()
    with pytest.raises(RetrofitSkippedError, match="no personalizable slot"):
        plan_retrofit(skeleton, contract, blob)


def test_resolve_skeleton_path_fails_closed_on_an_unknown_slug() -> None:
    """A slug naming no catalog skeleton is a skip, not a guess."""
    with pytest.raises(RetrofitSkippedError, match="no catalog skeleton"):
        resolve_skeleton_path(_CATALOG_ROOT, "a-slug-that-does-not-exist")


def test_resolve_skeleton_path_fails_closed_on_an_ambiguous_slug(
    tmp_path: Path,
) -> None:
    """A slug in two bands raises rather than picking one binding."""
    for band in ("5-7", "8-11"):
        band_dir = tmp_path / band
        band_dir.mkdir()
        (band_dir / "twinned.json").write_text("{}")
    with pytest.raises(ValidationError, match="matches 2 skeletons"):
        resolve_skeleton_path(tmp_path, "twinned")


def test_document_surfaces_covers_every_reinsertion_surface() -> None:
    """The wrapper guard inspects the same surfaces the transform touches."""
    document: dict[str, object] = {
        "title": "T",
        "nodes": [
            {
                "id": "n1",
                "body": "B",
                "choices": [{"label": "C"}],
                "ending": {"title": "E"},
            }
        ],
    }
    assert dict(document_surfaces(document)) == {
        "title": "T",
        "n1.body": "B",
        "n1.ending.title": "E",
        "n1.choices[0].label": "C",
    }
