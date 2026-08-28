"""Tests for the in-place personalization retrofit (ADR-023 content migration).

The transform under test rewrites stored, guardian-approved prose, so every
test here is about a guard rather than a happy path. Two real catalog books
carry the load: ``the-backyard-treasure-map``, whose prose names its hero
throughout, and ``the-snow-day-expedition``, whose stored blob was generated
from a binding the catalog contract no longer records. Both are tracked
under ``out/``, so these are real fills rather than hand-built fixtures that
could agree with the code by construction.

Most tests here are named by a ``#VERIFY`` tag in the script and are
load-bearing; renaming one breaks the tag it answers. Among them:
``test_a_rethemed_book_is_skipped_not_silently_zero_covered``,
``test_a_second_retrofit_over_a_retrofitted_blob_plans_cleanly``,
``test_resolve_skeleton_path_rejects_a_traversing_slug``,
``test_a_failed_book_does_not_abort_the_rest_of_the_sweep``,
``test_a_metadata_change_outside_the_text_surfaces_is_rejected``, and
``test_an_error_severity_finding_the_retrofit_retires_is_rejected``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.binding import load_contract_for
from cyo_adventure.storybook.sentinels import SENTINEL_RE
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.report import Severity
from scripts.retrofit_personalization import (
    _BLANKED_SURFACE,
    RetrofitPlan,
    RetrofitSkippedError,
    SkeletonNotFoundError,
    _assert_gate_no_worse,
    _assert_only_wrappers_added,
    _non_surface_skeleton,
    document_surfaces,
    load_skeleton,
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
# An ADR-011 MVP/Test seed: PL-28 fires against its stored blob at ERROR
# severity and blocks it, which is what makes it the right book to prove an
# ERROR retirement is refused.
_SEED_BOOK = "the-lost-mitten"
# Its stored blob carries RL-13 findings, which a widened reading-level
# tolerance retires at WARNING severity, so the severity floor cannot be
# what catches a metadata drift.
_ADVISORY_BOOK = "the-cave-of-echoes"


def _stored_blob(slug: str) -> dict[str, object]:
    """Return one book's stored fill without its catalog inputs.

    ``_load`` is the wrong tool for a book this module never plans: it
    insists on a theme contract, and two of the books used here are chosen
    precisely for what their VALIDATION report says, not for what their
    contract declares.

    Args:
        slug: The fill's filename stem.

    Returns:
        dict[str, object]: The stored document.
    """
    return cast(
        "dict[str, object]",
        json.loads((_FILLS / f"{slug}.filled.json").read_text(encoding="utf-8")),
    )


def _load(slug: str) -> tuple[dict[str, object], ThemeContract, dict[str, object]]:
    """Return a book's skeleton, contract, and stored fill.

    Args:
        slug: The skeleton slug, which is also the fill's filename stem.

    Returns:
        tuple: ``(skeleton, contract, blob)``.
    """
    skeleton_path = resolve_skeleton_path(_CATALOG_ROOT, slug)
    skeleton = load_skeleton(skeleton_path)
    contract = load_contract_for(skeleton_path, skeleton)
    assert contract is not None, f"{slug} has no theme contract"
    blob = cast(
        "dict[str, object]",
        json.loads((_FILLS / f"{slug}.filled.json").read_text(encoding="utf-8")),
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
    # ``plan_retrofit`` searches ``json.dumps(blob, ensure_ascii=False)``;
    # searching an ASCII-escaped dump here would report a non-ASCII pinned
    # value absent when the blob in fact contains it.
    assert pinned not in json.dumps(blob, ensure_ascii=False), (
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
        json.loads(json.dumps(blob, ensure_ascii=False).replace(stored_hero, pinned)),
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


def test_a_second_retrofit_over_a_retrofitted_blob_plans_cleanly() -> None:
    """The sweep is re-runnable: retrofitting an already-retrofitted blob is a no-op.

    #VERIFY for the ``#CRITICAL`` data-integrity tag on
    ``_assert_only_wrappers_added``. The stored ``before`` on a re-run is
    the sentinel-wrapped blob this same tool wrote, so a guard that strips
    only the ``after`` side compares bare prose against wrapped prose and
    rejects a byte-perfect transform. An operator resuming a partially
    completed migration depends on this passing.
    """
    skeleton, contract, blob = _load(_NAMED_HERO_BOOK)
    first = plan_retrofit(skeleton, contract, blob)
    assert first.tokens_reinserted > 0

    second = plan_retrofit(skeleton, contract, first.document)

    assert second.document == first.document
    assert second.manifest == first.manifest
    assert second.tokens_reinserted == first.tokens_reinserted


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


def test_a_metadata_change_outside_the_text_surfaces_is_rejected() -> None:
    """A drift in a field no text surface covers is caught by invariant 3.

    #VERIFY for the ``#CRITICAL`` data-integrity tag on
    ``_assert_only_wrappers_added``. ``document_surfaces`` yields four of
    the roughly thirty-seven field paths a stored blob carries, so a guard
    built only on it is silent about ``metadata``, and ``metadata`` is read
    by the validation gate: widening ``reading_level.tolerance`` retires
    every RL-13 finding the book had.

    The two assertions that make this test discriminating rather than
    decorative are the ones about the OTHER guards. The text half sees
    identical surfaces, and ``_assert_gate_no_worse`` permits the change
    because RL-13 is advisory, so neither the prose comparison nor the
    severity floor is standing between this mutation and a persisted write.
    Only the non-text comparison is.
    """
    blob = _stored_blob(_ADVISORY_BOOK)
    drifted = cast("dict[str, object]", json.loads(json.dumps(blob)))
    reading_level = cast(
        "dict[str, object]",
        cast("dict[str, object]", drifted["metadata"])["reading_level"],
    )
    reading_level["tolerance"] = 12.0

    stored_findings = run_gate(blob, context="fill_result").report.findings
    drifted_findings = run_gate(drifted, context="fill_result").report.findings
    stored_rl13 = sum(f.rule_id == "RL-13" for f in stored_findings)
    assert stored_rl13 > 0, "the fixture book no longer carries RL-13"
    assert sum(f.rule_id == "RL-13" for f in drifted_findings) < stored_rl13

    assert dict(document_surfaces(blob)) == dict(document_surfaces(drifted))
    _assert_gate_no_worse(blob, drifted)

    with pytest.raises(ValidationError, match="outside the text surfaces"):
        _assert_only_wrappers_added(blob, drifted)


def test_the_non_text_comparison_reaches_past_metadata() -> None:
    """Every non-text field is compared, not a hand-listed subset of them.

    A retargeted choice reroutes a reader mid-story and a moved
    ``start_node`` reroutes every reader from the first page, and neither
    changes one character of prose. The comparison is written as a whole
    document equality with the four text surfaces blanked, so a field
    nobody thought to enumerate is covered by construction.
    """
    before: dict[str, object] = {
        "title": "A Map",
        "start_node": "n1",
        "nodes": [
            {
                "id": "n1",
                "body": "Nina ran.",
                "choices": [{"label": "go", "target": "n2"}],
            },
            {"id": "n2", "body": "The end.", "is_ending": True},
        ],
    }

    retargeted = cast("dict[str, object]", json.loads(json.dumps(before)))
    node = cast("dict[str, object]", cast("list[object]", retargeted["nodes"])[0])
    cast("dict[str, object]", cast("list[object]", node["choices"])[0])["target"] = "n1"
    with pytest.raises(ValidationError, match="outside the text surfaces"):
        _assert_only_wrappers_added(before, retargeted)

    restarted = cast("dict[str, object]", json.loads(json.dumps(before)))
    restarted["start_node"] = "n2"
    with pytest.raises(ValidationError, match="outside the text surfaces"):
        _assert_only_wrappers_added(before, restarted)


def test_the_blanked_frame_hides_exactly_the_text_surfaces() -> None:
    """The two readers of the surface definition agree, by construction.

    ``document_surfaces`` reads the text and ``_non_surface_skeleton``
    blanks it; if those two enumerations ever disagreed, a surface the
    blanker missed would be compared as prose AND as a non-text field, and
    a legitimate wrapper insertion would be rejected as a field change.
    Both go through ``_text_surface_slots``, and this is what says so.
    """
    blob = _stored_blob(_NAMED_HERO_BOOK)
    frame = _non_surface_skeleton(blob)

    assert dict(document_surfaces(blob)).keys() == dict(document_surfaces(frame)).keys()
    assert {text for _, text in document_surfaces(frame)} == {_BLANKED_SURFACE}
    assert dict(document_surfaces(blob)) != dict(document_surfaces(frame))


def test_gate_guard_fails_closed_on_an_introduced_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retrofit that ADDS a validation finding is rejected.

    Stubs the gate rather than hunting for a book that trips it: the guard's
    job is to stop the write when the transform makes validation worse, and
    that behaviour is what needs proving. No book has ever been observed
    introducing a finding, which is exactly why the guard cannot be left
    untested. Removal is the opposite direction and is now permitted; see
    ``test_a_finding_the_retrofit_retires_is_permitted`` for why, and for the
    proof that the two directions really are treated differently.

    Args:
        monkeypatch: Pytest's patching fixture.
    """
    import scripts.retrofit_personalization as module

    class _Finding:
        def __init__(self, rule_id: str) -> None:
            self.rule_id = rule_id
            self.severity = Severity.WARNING

    class _Report:
        def __init__(self, rule_ids: list[str]) -> None:
            self.findings = [_Finding(rule_id) for rule_id in rule_ids]

        def to_dict(self) -> dict[str, object]:
            return {"ok": True, "findings": [f.rule_id for f in self.findings]}

    class _Result:
        def __init__(self, rule_ids: list[str], *, blocked: bool = False) -> None:
            self.report = _Report(rule_ids)
            self.blocked = blocked

    calls: list[int] = []

    def _drifting_gate(_data: object, **_kwargs: object) -> _Result:
        calls.append(1)
        return _Result(["L1-1"]) if len(calls) == 1 else _Result(["L1-1", "PL-17"])

    monkeypatch.setattr(module, "run_gate", _drifting_gate)
    with pytest.raises(ValidationError, match="worsened the validation gate"):
        _assert_gate_no_worse({}, {})


def test_gate_guard_returns_the_refreshed_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unchanged gate hands back the refreshed report instead of discarding it.

    The write path persists this as ``validation_report`` so the stored
    report describes the blob actually stored.

    Args:
        monkeypatch: Pytest's patching fixture.
    """
    import scripts.retrofit_personalization as module

    class _Report:
        def __init__(self) -> None:
            self.findings: list[object] = []

        def to_dict(self) -> dict[str, object]:
            return {"ok": True, "findings": []}

    class _Result:
        def __init__(self) -> None:
            self.report = _Report()
            self.blocked = False

    monkeypatch.setattr(module, "run_gate", lambda *_a, **_k: _Result())
    assert _assert_gate_no_worse({}, {}) == {"ok": True, "findings": []}


def test_a_finding_the_retrofit_retires_is_permitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retrofit that REMOVES a finding proceeds, and stores the smaller report.

    #VERIFY for the ``#CRITICAL`` data-integrity tag on
    ``_assert_gate_no_worse``. This is not a hypothetical direction: PN-1
    exempts the protagonist by reading the ``HERO`` sentinel, and installing
    that sentinel is what this script does, so every book whose prose named
    its hero flatly loses a PN-1 finding to the retrofit. Measured on
    ``the-backyard-treasure-map``, PN-1 reports ``Nina``, ``Pepper`` and
    ``Theo`` before and ``Pepper`` and ``Theo`` after, ``Nina`` being the
    contract's pinned ``HERO`` binding; under the previous equality check
    that book stopped with ``findings delta ['PN-1']``.

    Paired with ``test_gate_guard_fails_closed_on_an_introduced_finding``,
    which feeds the same guard the same rule ids in the opposite order, this
    proves the guard discriminates by DIRECTION rather than having been
    relaxed into accepting any difference.

    Args:
        monkeypatch: Pytest's patching fixture.
    """
    import scripts.retrofit_personalization as module

    class _Finding:
        def __init__(self, rule_id: str) -> None:
            self.rule_id = rule_id
            # PN-1, the finding this direction exists to permit, is a
            # WARNING. The guard reads severity, so a stub that omitted it
            # would prove the permission for a severity no real finding has.
            self.severity = Severity.WARNING

    class _Report:
        def __init__(self, rule_ids: list[str]) -> None:
            self.findings = [_Finding(rule_id) for rule_id in rule_ids]

        def to_dict(self) -> dict[str, object]:
            return {"ok": True, "findings": [f.rule_id for f in self.findings]}

    class _Result:
        def __init__(self, rule_ids: list[str]) -> None:
            self.report = _Report(rule_ids)
            self.blocked = False

    calls: list[int] = []

    def _retiring_gate(_data: object, **_kwargs: object) -> _Result:
        calls.append(1)
        return _Result(["L1-1", "PN-1"]) if len(calls) == 1 else _Result(["L1-1"])

    monkeypatch.setattr(module, "run_gate", _retiring_gate)

    # The report handed back describes the AFTER document, so the retired
    # finding must be absent from what the write path persists.
    assert _assert_gate_no_worse({}, {}) == {"ok": True, "findings": ["L1-1"]}


def test_a_retrofit_that_newly_blocks_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blocking is refused in the bad direction even with no new finding.

    The finding multiset and the blocked verdict are separate arms of the
    guard. A stub that keeps the rule ids identical while flipping
    ``blocked`` false to true isolates the second arm, so the direction
    check on findings cannot be the only thing standing between a retrofit
    and a newly unpublishable book.

    Args:
        monkeypatch: Pytest's patching fixture.
    """
    import scripts.retrofit_personalization as module

    class _Report:
        def __init__(self) -> None:
            self.findings: list[object] = []

        def to_dict(self) -> dict[str, object]:
            return {"ok": True, "findings": []}

    class _Result:
        def __init__(self, *, blocked: bool) -> None:
            self.report = _Report()
            self.blocked = blocked

    calls: list[int] = []

    def _newly_blocking_gate(_data: object, **_kwargs: object) -> _Result:
        calls.append(1)
        return _Result(blocked=len(calls) != 1)

    monkeypatch.setattr(module, "run_gate", _newly_blocking_gate)
    with pytest.raises(ValidationError, match="worsened the validation gate"):
        _assert_gate_no_worse({}, {})


def test_an_error_severity_finding_the_retrofit_retires_is_rejected() -> None:
    """Retiring an ERROR-severity finding is refused, even in the good direction.

    #VERIFY for the ``#CRITICAL`` security tag on
    ``_assert_gate_no_worse``. ``the-lost-mitten`` is a real ADR-011
    MVP/Test seed, so PL-28 fires against its stored blob at ERROR severity
    and blocks it. Flipping ``metadata.production_eligible`` retires that
    one finding and nothing else, which under a purely directional guard
    reads as an improvement: the book goes from blocked to publishable and
    the retrofit persists a ``validation_report`` describing the unblocked
    state. PL-28 is the firewall that keeps a prototyping shell out of a
    child's library, so this direction is refused whatever the arithmetic
    says.

    Uses the real gate rather than a stub: the severity that matters here
    is a property of a real rule against a real book, and a stub could
    assert it into existence.
    """
    blob = _stored_blob(_SEED_BOOK)
    unblocked = cast("dict[str, object]", json.loads(json.dumps(blob)))
    cast("dict[str, object]", unblocked["metadata"])["production_eligible"] = True

    stored = run_gate(blob, context="fill_result")
    mutated = run_gate(unblocked, context="fill_result")
    assert stored.blocked, "the fixture book is no longer blocked as stored"
    assert not mutated.blocked, "the mutation no longer unblocks the fixture book"
    assert [f.severity for f in stored.report.findings if f.rule_id == "PL-28"] == [
        Severity.ERROR
    ]
    assert not any(f.rule_id == "PL-28" for f in mutated.report.findings)

    with pytest.raises(ValidationError, match="never an error"):
        _assert_gate_no_worse(blob, unblocked)


def test_the_severity_floor_still_lets_the_real_hero_exemption_through() -> None:
    """The PR's motivating case survives the floor: a real book retires PN-1.

    The floor added by ``test_an_error_severity_finding_the_retrofit_
    retires_is_rejected`` must not close the direction the relaxation
    exists to open. ``the-backyard-treasure-map`` names its hero in the
    prose, so installing the ``HERO`` sentinel retires PN-1's finding on
    that name, and PN-1 is a WARNING. Nothing here is stubbed: if the floor
    were written against retirement rather than against severity, the whole
    plan would raise.
    """
    skeleton, contract, blob = _load(_NAMED_HERO_BOOK)
    stored_pn1 = sum(
        f.rule_id == "PN-1"
        for f in run_gate(blob, context="fill_result").report.findings
    )
    assert stored_pn1 > 0, "the fixture book no longer names its hero flatly"

    plan = plan_retrofit(skeleton, contract, blob)

    retrofitted_pn1 = sum(
        f.rule_id == "PN-1"
        for f in run_gate(plan.document, context="fill_result").report.findings
    )
    assert retrofitted_pn1 < stored_pn1, "no PN-1 finding was retired at all"


def test_a_manifest_that_does_not_describe_the_document_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A document/manifest pair that fails verification never reaches a write.

    Discrimination against a vacuous stub: the same book plans cleanly under
    the real ``verify_manifest`` in
    ``test_retrofit_only_adds_sentinel_wrappers``, so this failure is caused
    by the verification verdict alone.

    Args:
        monkeypatch: Pytest's patching fixture.
    """
    import scripts.retrofit_personalization as module

    skeleton, contract, blob = _load(_NAMED_HERO_BOOK)
    monkeypatch.setattr(module, "verify_manifest", lambda *_a, **_k: False)
    with pytest.raises(ValidationError, match="its own manifest"):
        plan_retrofit(skeleton, contract, blob)


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
    with pytest.raises(SkeletonNotFoundError, match="no catalog skeleton"):
        resolve_skeleton_path(_CATALOG_ROOT, "a-slug-that-does-not-exist")


def test_resolve_skeleton_path_fails_closed_on_an_ambiguous_slug(
    tmp_path: Path,
) -> None:
    """A slug in two bands raises rather than picking one binding.

    Args:
        tmp_path: Pytest's per-test temporary directory.
    """
    for band in ("5-7", "8-11"):
        band_dir = tmp_path / band
        band_dir.mkdir()
        (band_dir / "twinned.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValidationError, match="matches 2 skeletons"):
        resolve_skeleton_path(tmp_path, "twinned")


def test_resolve_skeleton_path_rejects_a_traversing_slug(tmp_path: Path) -> None:
    """A slug carrying ``..`` cannot reach a file outside the catalog root.

    #VERIFY for the ``#CRITICAL`` security tag on
    ``resolve_skeleton_path``. ``skeleton_slug`` is a database column and
    ``Path.glob`` honours literal ``..`` components, so the glob pattern
    alone provides no containment. Discrimination: the same root resolves a
    well-behaved slug, so the rejection is caused by the escape, not by the
    fixture.

    Args:
        tmp_path: Pytest's per-test temporary directory.
    """
    root = tmp_path / "skeletons"
    (root / "5-7").mkdir(parents=True)
    (root / "5-7" / "ordinary.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.json").write_text("{}", encoding="utf-8")

    assert resolve_skeleton_path(root, "ordinary").name == "ordinary.json"

    with pytest.raises(ValidationError, match="outside the catalog root"):
        resolve_skeleton_path(root, "../../outside/secret")


def test_load_skeleton_rejects_a_non_object_document(tmp_path: Path) -> None:
    """A catalog file that decodes to a list fails at the boundary, not deep inside.

    Args:
        tmp_path: Pytest's per-test temporary directory.
    """
    path = tmp_path / "listy.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValidationError, match="not an object"):
        load_skeleton(path)


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


class _FakeVersion:
    """A stand-in for one ``StorybookVersion`` row the sweep may write to."""

    def __init__(self, blob: dict[str, object], storybook_id: str = "sk_fake") -> None:
        """Store the row's starting state.

        Args:
            blob: The stored storybook document.
            storybook_id: The row's book id.
        """
        self.storybook_id = storybook_id
        self.version = 1
        self.skeleton_slug = _NAMED_HERO_BOOK
        self.blob = blob
        self.sentinel_manifest: dict[str, object] | None = None
        self.validation_report: dict[str, object] | None = None
        self.personalization_eligible = False


class _FakeSession:
    """The narrowest async session the sweep's write path actually uses."""

    def __init__(self) -> None:
        """Start with no commits, adds, or flushes recorded."""
        self.commits = 0
        self.added: list[object] = []
        self.calls: list[str] = []

    async def __aenter__(self) -> _FakeSession:
        """Enter the context.

        Returns:
            _FakeSession: This session.
        """
        return self

    async def __aexit__(self, *_: object) -> bool:
        """Leave the context without swallowing exceptions.

        Returns:
            bool: Always ``False``.
        """
        return False

    def add(self, instance: object) -> None:
        """Record an ORM object added to the session.

        Args:
            instance: The object added.
        """
        self.added.append(instance)
        self.calls.append("add")

    async def flush(self) -> None:
        """Record a flush."""
        self.calls.append("flush")

    async def commit(self) -> None:
        """Record a commit."""
        self.commits += 1
        self.calls.append("commit")

    async def rollback(self) -> None:
        """Fail loudly: the sweep must never roll back mid-loop.

        Raises:
            AssertionError: Always. ``AsyncSession.rollback()`` expires every
                loaded row, and the next iteration's attribute read would
                then lazy-refresh outside a greenlet and crash the sweep.
        """
        msg = "sweep called rollback(); loaded rows would be expired"
        raise AssertionError(msg)


def _plan_for(tokens: dict[str, object], blob: dict[str, object]) -> RetrofitPlan:
    """Build a ``RetrofitPlan`` stub with the given manifest tally.

    Args:
        tokens: The manifest tally the planner reports.
        blob: The document the plan would persist.

    Returns:
        RetrofitPlan: A plan the write path can consume.
    """
    return RetrofitPlan(
        document=blob,
        manifest={"tokens": tokens},
        validation_report={"ok": True, "findings": []},
        personalizable_slots=frozenset({"HERO"}),
        tokens_expected=289,
        tokens_reinserted=sum(
            cast("dict[str, int]", v)["count"] for v in tokens.values()
        ),
    )


@pytest.mark.parametrize(
    ("tokens", "expected_eligible"),
    [({}, False), ({"HERO": {"count": 3}}, True)],
)
def test_a_zero_coverage_book_is_not_stamped_eligible(
    monkeypatch: pytest.MonkeyPatch,
    tokens: dict[str, object],
    expected_eligible: bool,
) -> None:
    """The eligibility stamp must follow coverage, not merely a plan.

    The reader prompts a child for a name whenever this column is True, so a
    book whose prose names its hero nowhere (``the-drowned-court`` reinserts
    0 of 289 expected tokens) must come out ineligible. ``build_manifest``
    returns ``{"tokens": {}}`` rather than ``None`` for such a document, so a
    presence test would stamp True and ask for a name no page can show.

    Both directions are asserted: an empty tally must not stamp, and a
    non-empty one must.

    Args:
        monkeypatch: Pytest's patching fixture.
        tokens: The manifest tally the planner reports.
        expected_eligible: The stamp the write path must produce.
    """
    from scripts import retrofit_personalization as module

    _, _, blob = _load(_NAMED_HERO_BOOK)
    row = _FakeVersion(blob)
    session = _FakeSession()

    async def _targets(*_: object) -> list[_FakeVersion]:
        return [row]

    def _plan(*_: object) -> RetrofitPlan:
        return _plan_for(tokens, blob)

    monkeypatch.setattr(module, "_select_targets", _targets)
    monkeypatch.setattr(module, "plan_retrofit", _plan)

    outcomes = asyncio.run(
        module.sweep(
            session_factory=lambda: cast("object", session),  # pyright: ignore[reportArgumentType]
            skeleton_root=_CATALOG_ROOT,
            execute=True,
        )
    )

    assert session.commits == 1
    assert outcomes[0].status == "retrofitted"
    assert row.personalization_eligible is expected_eligible
    assert f"eligible={expected_eligible}" in outcomes[0].detail


def test_a_retrofit_records_an_append_only_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-place blob rewrite writes an audit event in the same transaction.

    ``db/models.py`` documents a storybook version as immutable, and
    ``api/node_edit.py`` establishes that a path mutating one persists a
    refreshed validation report and writes an append-only event. Both are
    asserted here, along with the ordering that makes them atomic: the event
    is flushed BEFORE the commit, so a commit failure takes both.

    Args:
        monkeypatch: Pytest's patching fixture.
    """
    from scripts import retrofit_personalization as module

    _, _, blob = _load(_NAMED_HERO_BOOK)
    row = _FakeVersion(blob)
    session = _FakeSession()

    async def _targets(*_: object) -> list[_FakeVersion]:
        return [row]

    monkeypatch.setattr(module, "_select_targets", _targets)
    monkeypatch.setattr(
        module,
        "plan_retrofit",
        lambda *_: _plan_for({"HERO": {"count": 3}}, blob),
    )

    outcomes = asyncio.run(
        module.sweep(
            session_factory=lambda: cast("object", session),  # pyright: ignore[reportArgumentType]
            skeleton_root=_CATALOG_ROOT,
            execute=True,
        )
    )

    assert outcomes[0].status == "retrofitted"
    assert row.validation_report == {"ok": True, "findings": []}
    assert len(session.added) == 1
    event = session.added[0]
    assert event.event_type == "repair_applied"
    assert event.entity_type == "storybook_version"
    assert event.entity_id == "sk_fake:1"
    assert event.payload == {"stage": "personalization_retrofit"}
    assert event.actor_role == "system"
    assert session.calls == ["add", "flush", "commit"]


def test_a_failed_book_does_not_abort_the_rest_of_the_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A book failing an invariant is recorded, and the next book still runs.

    #VERIFY for the ``#CRITICAL`` data-integrity tag on ``sweep``. The
    handler used to call ``session.rollback()``, which expires every loaded
    row; the next iteration's ``version.skeleton_slug`` would then lazy-load
    outside a greenlet and raise ``MissingGreenlet`` out of ``asyncio.run``
    with no summary printed. ``_FakeSession.rollback`` raises, so any
    reintroduction of that call fails this test outright.

    Args:
        monkeypatch: Pytest's patching fixture.
    """
    from scripts import retrofit_personalization as module

    _, _, blob = _load(_NAMED_HERO_BOOK)
    first = _FakeVersion(blob, storybook_id="sk_bad")
    second = _FakeVersion(blob, storybook_id="sk_good")
    session = _FakeSession()

    async def _targets(*_: object) -> list[_FakeVersion]:
        return [first, second]

    seen: list[int] = []

    def _plan(*_: object) -> RetrofitPlan:
        seen.append(1)
        if len(seen) == 1:
            msg = "retrofit altered text at n1.body beyond adding sentinels"
            raise ValidationError(msg)
        return _plan_for({"HERO": {"count": 2}}, blob)

    monkeypatch.setattr(module, "_select_targets", _targets)
    monkeypatch.setattr(module, "plan_retrofit", _plan)

    outcomes = asyncio.run(
        module.sweep(
            session_factory=lambda: cast("object", session),  # pyright: ignore[reportArgumentType]
            skeleton_root=_CATALOG_ROOT,
            execute=True,
        )
    )

    assert [(o.storybook_id, o.status) for o in outcomes] == [
        ("sk_bad", "failed"),
        ("sk_good", "retrofitted"),
    ]
    assert session.commits == 1


def test_an_unreadable_catalog_file_is_recorded_failed_not_raised(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A malformed catalog file fails one book, not the whole sweep.

    The module's contract is per-book isolation, and ``main()`` never
    reaches its summary if a decode error escapes ``asyncio.run``.

    Args:
        monkeypatch: Pytest's patching fixture.
        tmp_path: Pytest's per-test temporary directory.
    """
    from scripts import retrofit_personalization as module

    root = tmp_path / "skeletons"
    (root / "5-7").mkdir(parents=True)
    (root / "5-7" / "broken.json").write_text("{not json", encoding="utf-8")

    broken = _FakeVersion({}, storybook_id="sk_broken")
    broken.skeleton_slug = "broken"
    missing = _FakeVersion({}, storybook_id="sk_missing")
    missing.skeleton_slug = "absent-from-catalog"
    session = _FakeSession()

    async def _targets(*_: object) -> list[_FakeVersion]:
        return [broken, missing]

    monkeypatch.setattr(module, "_select_targets", _targets)

    outcomes = asyncio.run(
        module.sweep(
            session_factory=lambda: cast("object", session),  # pyright: ignore[reportArgumentType]
            skeleton_root=root,
            execute=True,
        )
    )

    assert [(o.storybook_id, o.status) for o in outcomes] == [
        ("sk_broken", "failed"),
        ("sk_missing", "unmatched"),
    ]
    assert "could not read catalog input" in outcomes[0].detail
    assert session.commits == 0


def test_main_configures_logging_before_sweeping(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``main`` installs the redaction processor before any work runs.

    #VERIFY for the ``#CRITICAL`` security tag on ``main``. A module-level
    ``get_logger`` alone leaves structlog on its unconfigured default chain,
    where ``censor_sensitive_processor`` is not installed and the redaction
    backstop is inert.

    Args:
        monkeypatch: Pytest's patching fixture.
        capsys: Pytest's stdout capture fixture.
    """
    from scripts import retrofit_personalization as module

    order: list[str] = []

    def _setup(**_kwargs: object) -> None:
        order.append("setup_logging")

    async def _sweep(**_kwargs: object) -> list[object]:
        order.append("sweep")
        return []

    monkeypatch.setattr(module, "setup_logging", _setup)
    monkeypatch.setattr(module, "sweep", _sweep)

    assert module.main(["--all"]) == 0
    assert order == ["setup_logging", "sweep"]
    assert "no candidate versions found" in capsys.readouterr().out
