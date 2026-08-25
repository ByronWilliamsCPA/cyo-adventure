"""Tests for the ``HERO`` slot promotion gate (ADR-023 catalog migration).

Three of these are named directly by ``#VERIFY`` tags in
``scripts/promote_personalizable_slots.py``, so they are load-bearing rather
than incidental:
``test_catalog_promoted_hero_slot_declares_protagonist_role_safety``,
``test_main_excluded_slug_is_never_promoted``, and
``test_main_check_mode_excluded_slug_promoted_out_of_band_fails``.

Each is written to *discriminate*. A test that only asserts the catalog's
current state passes just as well when the tool has been gutted, so each
pairs its catalog-wide assertion with an arm that proves the mechanism under
test is what produced the result: the role-safety test also shows the
contract validator rejects the field's absence, and the exclusion test
promotes a byte-identical copy of an excluded contract under a different
slug, so only the slug can explain the difference.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cyo_adventure.storybook.theme_contract import ThemeContract
from scripts import promote_personalizable_slots as pps

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_ROOT = _REPO_ROOT / "skeletons"

# A deliberate second copy of the exclusion roster, kept here rather than
# imported, because a test that reads the roster from the tool cannot notice
# the roster shrinking. Dropping a slug from ``NOT_PERSONALIZABLE`` and
# re-running ``--apply`` leaves check mode green with a child's name attached
# to an animal's body, or to a role phrase; only an independently stated set
# catches that. Adding or removing an entry is therefore a two-file edit on
# purpose. The three exclusion classes are spelled out separately so the
# reason a slug is on the roster survives here as well as in the tool.
_ANIMAL_PROTAGONIST_SLUGS = frozenset(
    {
        "baking-day-with-grandma-vole",
        "the-clover-and-the-butterfly",
        "the-lantern-festival",
        "the-lost-mitten",
        "the-teddy-bears-picnic",
    }
)

# Protagonists the narration never names: the pinned HERO value is a role
# phrase or an office, so a family's first name cannot occupy it.
_ROLE_PHRASE_SLUGS = frozenset(
    {
        "the-labyrinth-of-glass",
        "the-pale-road",
        "the-red-meridian-run",
        "the-tricameral-city",
    }
)

# A protagonist that a second, NON-personalizable slot also names, so only
# half the book would follow the family's chosen name.
_PAIRED_FULL_NAME_SLUGS = frozenset({"the-vanishing-orchard"})

_EXCLUDED_SLUGS = (
    _ANIMAL_PROTAGONIST_SLUGS | _ROLE_PHRASE_SLUGS | _PAIRED_FULL_NAME_SLUGS
)


def _hero_slot(document: dict[str, object]) -> dict[str, object] | None:
    """Return a contract document's ``HERO`` slot, if it declares one.

    Args:
        document: A parsed contract sidecar.

    Returns:
        dict[str, object] | None: The ``HERO`` slot, or ``None``.
    """
    slots = document.get("slots")
    if not isinstance(slots, list):
        return None
    for slot in slots:
        if isinstance(slot, dict) and slot.get("id") == pps.IDENTITY_SLOT:
            return slot
    return None


def _catalog_documents() -> list[tuple[str, dict[str, object]]]:
    """Return every catalog contract as a ``(slug, document)`` pair.

    Returns:
        list[tuple[str, dict[str, object]]]: Sorted by slug.
    """
    return [
        (pps.slug_for(path), json.loads(path.read_text()))
        for path in pps.contract_paths(_CATALOG_ROOT)
    ]


def _minimal_contract(*, role_safety: str | None) -> dict[str, object]:
    """Return a one-slot contract with a personalizable ``HERO``.

    Args:
        role_safety: The ``role_safety`` value, or ``None`` to omit the
            field entirely.

    Returns:
        dict[str, object]: A contract document ready for validation.
    """
    slot: dict[str, object] = {
        "id": pps.IDENTITY_SLOT,
        "scope": "global",
        "meaning": "The child protagonist.",
        "guidance": "A single kid-relatable explorer.",
        "kind": "personalizable",
        "personalization_field": pps.PERSONALIZATION_FIELD,
        "constraints": {"max_words": 6, "forbid": [], "distinct_from": []},
    }
    if role_safety is not None:
        slot["role_safety"] = role_safety
    return {
        "contract_version": 1,
        "skeleton_slug": "fixture-shell",
        "age_band": "8-11",
        "slots": [slot],
        "default_binding": {pps.IDENTITY_SLOT: "Nina"},
    }


def test_catalog_promoted_hero_slot_declares_protagonist_role_safety() -> None:
    """Every promoted ``HERO`` carries the protagonist safety pinning.

    #VERIFY for the ``#CRITICAL`` security tag on
    ``PERSONALIZATION_FIELD``/``ROLE_SAFETY``: a personalizable ``HERO`` puts
    a real child's name into a narrative role, and ``role_safety`` is what
    keeps that role out of antagonist and mishap positions.
    """
    promoted = [
        (slug, slot)
        for slug, document in _catalog_documents()
        if (slot := _hero_slot(document)) is not None
        and slot.get("kind") == "personalizable"
    ]
    assert promoted, "no HERO slot is personalizable; the migration regressed"
    for slug, slot in promoted:
        assert slot.get("personalization_field") == pps.PERSONALIZATION_FIELD, slug
        assert slot.get("role_safety") == pps.ROLE_SAFETY, slug

    # Discrimination: the assertions above are not vacuous, because the
    # contract validator itself rejects the field's absence.
    ThemeContract.model_validate(_minimal_contract(role_safety=pps.ROLE_SAFETY))
    unpinned = _minimal_contract(role_safety=None)
    with pytest.raises(ValueError, match="role_safety"):
        ThemeContract.model_validate(unpinned)


def test_main_excluded_slug_is_never_promoted(tmp_path: Path) -> None:
    """Excluded slugs stay unpromoted, and the slug is the only reason.

    #VERIFY for the ``#CRITICAL`` data-integrity tag on
    ``NOT_PERSONALIZABLE``: each entry is a story where substituting a
    child's first name for the pinned HERO value yields a book that is wrong
    on the page, whether because the hero has an animal's body, because the
    narration never names the hero at all, or because a second slot names the
    same character and would not follow the family's choice.
    """
    assert set(pps.NOT_PERSONALIZABLE) == _EXCLUDED_SLUGS

    on_disk = dict(_catalog_documents())
    for slug in pps.NOT_PERSONALIZABLE:
        assert slug in on_disk, f"{slug} names no catalog contract"
        slot = _hero_slot(on_disk[slug])
        assert slot is not None, f"{slug} declares no {pps.IDENTITY_SLOT} slot"
        assert slot.get("kind") != "personalizable", slug

    # Discrimination: copy one excluded contract twice into a scratch
    # catalog, once under its own slug and once under a slug the policy does
    # not know. The bytes are identical, so if both come back unchanged the
    # exclusion proved nothing.
    excluded_slug = next(iter(pps.NOT_PERSONALIZABLE))
    source = next(
        path
        for path in pps.contract_paths(_CATALOG_ROOT)
        if pps.slug_for(path) == excluded_slug
    )
    kept = tmp_path / f"{excluded_slug}.contract.json"
    twin = tmp_path / "an-unlisted-slug.contract.json"
    shutil.copyfile(source, kept)
    shutil.copyfile(source, twin)
    original = source.read_text()

    assert pps.main(["--apply", "--skeleton-root", str(tmp_path)]) == 0

    assert kept.read_text() == original
    assert _hero_slot(json.loads(twin.read_text())) == {
        **(_hero_slot(json.loads(original)) or {}),
        "kind": "personalizable",
        "personalization_field": pps.PERSONALIZATION_FIELD,
        "role_safety": pps.ROLE_SAFETY,
    }


def test_main_check_mode_over_catalog_exits_zero() -> None:
    """The catalog satisfies the gate, so a new skeleton must opt in.

    This is the half of the tool that keeps working after the one-time
    migration: check mode fails on any ``HERO`` slot that is neither
    promoted nor excluded with a stated reason.
    """
    assert pps.main(["--skeleton-root", str(_CATALOG_ROOT)]) == 0


def test_catalog_contract_after_promotion_still_validates() -> None:
    """Promotion left every catalog contract loadable as a ThemeContract."""
    for slug, document in _catalog_documents():
        try:
            ThemeContract.model_validate(document)
        except ValueError as exc:  # pragma: no cover - failure path
            pytest.fail(f"{slug}: {exc}")


def test_insert_promotion_fields_inline_array_preserves_surrounding_bytes() -> None:
    """The surgical edit adds lines and changes nothing else.

    A whole-document ``json.dumps`` round-trip would reformat every sidecar
    that inlines short arrays, burying a three-line change under hundreds of
    lines of churn that nothing in the repo would ever normalize away.
    """
    text = (
        "{\n"
        '  "slots": [\n'
        "    {\n"
        '      "id": "HERO",\n'
        '      "constraints": { "forbid": ["weapon"] }\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )
    edited = pps.insert_promotion_fields(text)
    assert '"forbid": ["weapon"]' in edited
    assert edited.count("\n") == text.count("\n") + 3
    removed = [line for line in text.splitlines() if line not in edited.splitlines()]
    assert removed == ['      "constraints": { "forbid": ["weapon"] }']
    assert json.loads(edited) == pps.promote(json.loads(text))


def test_insert_promotion_fields_brace_in_quoted_value_is_ignored() -> None:
    """A brace in a quoted value never moves the enclosing-object span."""
    text = (
        "{\n"
        '  "slots": [\n'
        "    {\n"
        '      "id": "HERO",\n'
        '      "guidance": "never write {HERO} or a stray } here"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )
    edited = pps.insert_promotion_fields(text)
    document = json.loads(edited)
    assert document == pps.promote(json.loads(text))
    slot = _hero_slot(document)
    assert slot is not None
    assert slot["guidance"] == "never write {HERO} or a stray } here"


def test_promote_already_promoted_document_returns_none() -> None:
    """``promote`` returns ``None`` when there is nothing left to do."""
    text = '{"slots": [{"id": "HERO"}]}'
    once = pps.promote(json.loads(text))
    assert once is not None
    assert pps.promote(once) is None
    assert pps.promote({"slots": [{"id": "ANCESTOR"}]}) is None
    assert pps.promote({"slots": "not-a-list"}) is None


def test_insert_promotion_fields_missing_slot_raises_value_error() -> None:
    """A contract with no ``HERO`` slot raises rather than editing blind."""
    with pytest.raises(ValueError, match="no slot with id"):
        pps.insert_promotion_fields('{"slots": [{"id": "ANCESTOR"}]}')


def _fixture_contract_text(*, hero: str, personalizable: bool) -> str:
    """Return a valid one-slot contract as text, ready to write to disk.

    Built here rather than copied from the catalog so a test can choose the
    pinned ``HERO`` value and the slot ``kind`` independently, which is what
    lets the atomicity and out-of-band cases exist at all: every catalog
    contract is already in exactly the state the tool wants.

    Args:
        hero: The pinned ``default_binding["HERO"]`` value.
        personalizable: Whether the ``HERO`` slot already carries the three
            promotion fields.

    Returns:
        str: The contract document, JSON-encoded with two-space indentation.
    """
    slot: dict[str, object] = {
        "id": pps.IDENTITY_SLOT,
        "scope": "global",
        "meaning": "The child protagonist.",
        "guidance": "A single kid-relatable explorer.",
        "constraints": {"max_words": 6, "forbid": [], "distinct_from": []},
    }
    if personalizable:
        slot["kind"] = "personalizable"
        slot["personalization_field"] = pps.PERSONALIZATION_FIELD
        slot["role_safety"] = pps.ROLE_SAFETY
    document: dict[str, object] = {
        "contract_version": 1,
        "skeleton_slug": "fixture-shell",
        "age_band": "8-11",
        "slots": [slot],
        "default_binding": {pps.IDENTITY_SLOT: hero},
    }
    return json.dumps(document, indent=2)


def test_main_check_mode_excluded_slug_promoted_out_of_band_fails(
    tmp_path: Path,
) -> None:
    """An excluded slug found personalizable is a violation, not "already".

    #VERIFY for the ``#CRITICAL`` data-integrity tag on ``main``'s
    exclusion-first ordering: ``promote`` returns ``None`` for an
    already-personalizable slot, so a roster check placed after it is never
    reached for exactly the contracts the roster is about. Before the
    reordering this run exited 0.
    """
    excluded_slug = next(iter(pps.NOT_PERSONALIZABLE))
    promoted = _fixture_contract_text(hero="Nina", personalizable=True)
    (tmp_path / f"{excluded_slug}.contract.json").write_text(promoted, encoding="utf-8")

    assert pps.main(["--skeleton-root", str(tmp_path)]) == 1

    # Discrimination: byte-identical content under a slug the roster does not
    # know is simply "already promoted", so only the slug explains the exit
    # code.
    other = tmp_path / "unlisted"
    other.mkdir()
    (other / "an-unlisted-slug.contract.json").write_text(promoted, encoding="utf-8")
    assert pps.main(["--skeleton-root", str(other)]) == 0


def test_main_apply_writes_nothing_when_one_contract_fails(tmp_path: Path) -> None:
    """``--apply`` is all-or-nothing across the batch.

    A partial write leaves a tree that is indistinguishable from an ordinary
    mid-migration state, so the next check-mode run reports it as work still
    to do rather than as a failed run.
    """
    good = tmp_path / "a-good-slug.contract.json"
    bad = tmp_path / "z-bad-slug.contract.json"
    good_text = _fixture_contract_text(hero="Nina", personalizable=False)
    bad_text = _fixture_contract_text(hero="a pilgrim", personalizable=False)
    good.write_text(good_text, encoding="utf-8")
    bad.write_text(bad_text, encoding="utf-8")

    assert pps.main(["--apply", "--skeleton-root", str(tmp_path)]) == 1
    assert good.read_text(encoding="utf-8") == good_text
    assert bad.read_text(encoding="utf-8") == bad_text

    # Discrimination: the good contract is genuinely writable on its own, so
    # the untouched bytes above are the batch failing, not the edit failing.
    bad.unlink()
    assert pps.main(["--apply", "--skeleton-root", str(tmp_path)]) == 0
    assert pps.is_personalizable(json.loads(good.read_text(encoding="utf-8")))


def test_insert_promotion_fields_hero_id_outside_slots_is_ignored() -> None:
    """A matching id outside the ``slots`` array never steers the edit."""
    text = (
        "{\n"
        '  "notes": "the example reads \\"id\\": \\"HERO\\" verbatim",\n'
        '  "slots": [\n'
        "    {\n"
        '      "id": "HERO",\n'
        '      "meaning": "the hero"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )
    edited = pps.insert_promotion_fields(text)
    assert json.loads(edited) == pps.promote(json.loads(text))
    assert json.loads(edited)["notes"] == json.loads(text)["notes"]


def test_insert_promotion_fields_duplicate_slot_id_raises_value_error() -> None:
    """Two ``HERO`` slots are refused rather than edited arbitrarily."""
    text = '{"slots": [{"id": "HERO"}, {"id": "HERO"}]}'
    with pytest.raises(ValueError, match="occurs 2 times"):
        pps.insert_promotion_fields(text)
