"""Promote each skeleton's ``HERO`` theme slot to a personalizable slot.

Usage::

    uv run python scripts/promote_personalizable_slots.py           # check
    uv run python scripts/promote_personalizable_slots.py --apply   # write

ADR-023 gives the catalog a second slot kind: a ``personalizable`` slot is
always bound to the contract's own ``default_binding`` value, rendered inside
a ``{~SLOTID:Value~}`` sentinel so a client can resolve it to a family's
chosen personalization at read time. The machinery for that shipped in full
(Stages R, B and C); the catalog was never migrated, so as of this script's
introduction exactly one of the catalog's 2,655 declared slots carried
``kind="personalizable"``.

This tool closes that gap and then keeps it closed. Check mode is the default
and is the useful half: it fails when any skeleton declares a ``HERO`` slot
that is neither promoted nor listed in :data:`NOT_PERSONALIZABLE` with a
reason, so a newly authored skeleton has to make the decision explicitly
rather than defaulting to "not personalizable" by silence. It fails in the
other direction too: a slug listed in :data:`NOT_PERSONALIZABLE` whose
``HERO`` has nonetheless been made personalizable is reported as a violation,
not counted as already migrated, so the roster cannot be quietly overridden by
a hand edit or a bad merge.

The promotion itself is three fields on the ``HERO`` slot
(``kind``, ``personalization_field``, ``role_safety``); every other field,
including the pinned ``default_binding`` value, is left exactly as authored.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Final

from cyo_adventure.storybook.theme_contract import ThemeContract

# The identity slot this tool promotes. Deliberately just the one: ADR-023
# section 7 makes the slot taxonomy CLOSED, so widening this to a second slot
# id is an ADR amendment, not a code change.
IDENTITY_SLOT: Final[str] = "HERO"

# #CRITICAL: security: a personalizable slot bound to
# `protagonist_first_name` puts a REAL CHILD'S NAME into the narrative role
# this slot plays. `role_safety="protagonist"` is what keeps that name out of
# an antagonist or mishap role (ADR-023 plan R11), and
# `theme_contract._check_personalizable_slots` rejects the slot outright if it
# is absent. Never relax either field to make a stubborn contract validate.
# #VERIFY: tests/unit/test_promote_personalizable_slots.py::
#   test_catalog_promoted_hero_slot_declares_protagonist_role_safety
PERSONALIZATION_FIELD: Final[str] = "protagonist_first_name"
ROLE_SAFETY: Final[str] = "protagonist"

# Skeletons whose HERO must NOT be personalized, each with the reason.
#
# #CRITICAL: data-integrity: an entry here is a story where substituting a
# real child's first name for the pinned HERO value produces a book that is
# wrong on the page, not merely unpersonalized. Three distinct shapes qualify,
# and none of them is detectable from the promotion fields alone:
#
# 1. ANIMAL PROTAGONIST. The prose establishes the hero's body, so the child's
#    name lands on a body they do not have ("Briella looked at one bare paw").
#    Evidence is the hero-name proximity scan described in the design spec, not
#    a keyword count over the whole book: animal words in a book usually belong
#    to a COMPANION (Maya's dog, Nia's clockwork menagerie, Wren's cat), and a
#    whole-book scan misclassifies all three as animal protagonists.
# 2. UNNAMED OR ROLE-TITLED PROTAGONIST. The pin is a role phrase, not a name,
#    because the narration never names the hero: substituting yields "you walk
#    the road as Maya" or "the Maya signs the opinion". The slot's own
#    `meaning`/`guidance` says so, and `theme_contract.first_name_pin_error`
#    now rejects the pin outright, so promoting one of these cannot even be
#    written down without also corrupting the pin.
# 3. PAIRED FULL-NAME SURFACE. A second, NON-personalizable slot names the same
#    character. Only the personalizable slot is rewritten at read time, so the
#    book uses the family's name in one place and the authored name in another.
#    `theme_contract._check_personalizable_value_collisions` rejects this shape.
# #VERIFY: tests/unit/test_promote_personalizable_slots.py::
#   test_main_excluded_slug_is_never_promoted
NOT_PERSONALIZABLE: Final[dict[str, str]] = {
    "the-lost-mitten": "animal protagonist: 'Pip looked at one bare paw'",
    "baking-day-with-grandma-vole": ("animal protagonist: 'Pip reached out his paws'"),
    "the-lantern-festival": (
        "animal protagonist: 'Tansy stands in her clearing and counts on her paws'"
    ),
    "the-teddy-bears-picnic": ("animal protagonist: 'The tune makes her paws dance'"),
    # Caught by contract metadata, NOT by the prose scan: this book's animal
    # body language never lands within the proximity window of the hero's
    # name, so the prose signal alone would have promoted it. Both signals are
    # required; neither is sufficient on its own.
    "the-clover-and-the-butterfly": (
        "animal protagonist: contract meaning declares "
        "'an animal in the original theme'"
    ),
    "the-labyrinth-of-glass": (
        "unnamed second-person protagonist: the book's one {HERO} beat reads "
        "'you are {HERO} who has slipped below the stage', and the slot's "
        "meaning is 'The unnamed second-person protagonist's role/identity'"
    ),
    "the-pale-road": (
        "unnamed second-person protagonist: the book's one {HERO} beat reads "
        "'you are {HERO} at the head of {THRESHOLD}', pinned to the role "
        "phrase 'a pilgrim' because second person keeps the traveler unnamed"
    ),
    "the-red-meridian-run": (
        "unnamed second-person protagonist: the book's one {HERO} beat reads "
        "'you are {HERO} of {VESSEL}', pinned to the crew role 'the pilot'; "
        "the slot's guidance asks for 'a single unnamed role title'"
    ),
    "the-tricameral-city": (
        "role-titled protagonist: every one of the 221 {HERO} uses carries a "
        "definite article ('the {HERO} pulls the opinion back to draft'), the "
        "pin is the office 'auditor', and the slot is deliberately "
        "distinct_from five separate surname slots that do the naming"
    ),
    "the-vanishing-orchard": (
        "paired full-name surface: the theme slot HERO_FULL pins "
        "'Rowan Ashby' and opens the book with it, while HERO pins 'Rowan'; "
        "only HERO would resolve at read time, so a personalized book would "
        "open as 'Rowan Ashby' and then call the child by the family's name "
        "for the remaining 114 beats"
    ),
}


def identity_slot(document: dict[str, object]) -> dict[str, object] | None:
    """Return a contract document's identity slot, if it declares one.

    Args:
        document: A parsed contract sidecar.

    Returns:
        dict[str, object] | None: The :data:`IDENTITY_SLOT` slot object, or
            ``None`` when the contract declares no such slot.
    """
    slots = document.get("slots")
    if not isinstance(slots, list):
        return None
    for slot in slots:
        if isinstance(slot, dict) and slot.get("id") == IDENTITY_SLOT:
            return slot
    return None


def is_personalizable(document: dict[str, object]) -> bool:
    """Return whether a contract's identity slot is already personalizable.

    Args:
        document: A parsed contract sidecar.

    Returns:
        bool: True when the identity slot exists and declares
            ``kind="personalizable"``.
    """
    slot = identity_slot(document)
    return slot is not None and slot.get("kind") == "personalizable"


def contract_paths(skeleton_root: Path) -> list[Path]:
    """Return every contract sidecar under a skeleton root, sorted.

    Args:
        skeleton_root: The catalog root holding ``<band>/<slug>.json`` plus
            each skeleton's ``<slug>.contract.json`` sidecar.

    Returns:
        list[Path]: Every ``*.contract.json`` path, in sorted order.
    """
    return sorted(skeleton_root.rglob("*.contract.json"))


def slug_for(contract_path: Path) -> str:
    """Return the skeleton slug a contract sidecar belongs to.

    Args:
        contract_path: A ``<slug>.contract.json`` path.

    Returns:
        str: The bare skeleton slug, with the doubled suffix removed.
    """
    return contract_path.name.removesuffix(".contract.json")


def promote(document: dict[str, object]) -> dict[str, object] | None:
    """Return the contract document with its identity slot promoted.

    Args:
        document: A parsed contract sidecar.

    Returns:
        dict[str, object] | None: A new document whose ``HERO`` slot carries
            the three personalizable fields, or ``None`` when the contract
            declares no ``HERO`` slot or has already been promoted.
    """
    slots = document.get("slots")
    if not isinstance(slots, list):
        return None
    promoted: list[object] = []
    found = False
    for slot in slots:
        if not isinstance(slot, dict) or slot.get("id") != IDENTITY_SLOT:
            promoted.append(slot)
            continue
        if slot.get("kind") == "personalizable":
            return None
        found = True
        promoted.append(
            {
                **slot,
                "kind": "personalizable",
                "personalization_field": PERSONALIZATION_FIELD,
                "role_safety": ROLE_SAFETY,
            }
        )
    if not found:
        return None
    return {**document, "slots": promoted}


def _slots_array_span(text: str) -> tuple[int, int]:
    """Return the span of the document's ``slots`` array.

    A string-aware scan, so a ``"slots"`` mentioned inside a ``guidance``
    string is not mistaken for the property. Scoping the slot lookup to this
    span is what stops a future contract that happens to spell ``"id": "HERO"``
    somewhere outside the slot list (a nested example in a ``meaning``, a
    second document embedded in a comment field) from steering the edit.

    Args:
        text: The raw contract sidecar text.

    Returns:
        tuple[int, int]: The indices of the array's opening ``[`` and its
            matching ``]``.

    Raises:
        ValueError: If the document does not contain exactly one ``slots``
            array property.
    """
    opens = [
        match.end() - 1
        for match in re.finditer(r'"slots"\s*:\s*\[', text)
        if not _inside_string(text, match.start())
    ]
    if len(opens) != 1:
        msg = f"expected exactly one 'slots' array, found {len(opens)}"
        raise ValueError(msg)
    start = opens[0]
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return start, index
    msg = "unterminated 'slots' array"
    raise ValueError(msg)


def _inside_string(text: str, index: int) -> bool:
    """Return whether an index sits inside a JSON string literal.

    Args:
        text: The raw contract sidecar text.
        index: The index to classify.

    Returns:
        bool: True when ``index`` falls inside a quoted string.
    """
    in_string = False
    escaped = False
    for position in range(index):
        char = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
    return in_string


def _enclosing_object(text: str, marker: int) -> tuple[int, int]:
    """Return the span of the innermost JSON object containing an index.

    A single string-aware forward pass, so a brace inside a quoted value
    (``"guidance": "use {HERO} here"``) never moves the span.

    Args:
        text: The raw contract sidecar text.
        marker: An index known to sit inside the wanted object.

    Returns:
        tuple[int, int]: The indices of the object's opening ``{`` and its
            matching ``}``.

    Raises:
        ValueError: If no object encloses ``marker``.
    """
    stack: list[int] = []
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            stack.append(index)
        elif char == "}":
            start = stack.pop()
            if start <= marker <= index:
                return start, index
    msg = f"no JSON object encloses index {marker}"
    raise ValueError(msg)


def insert_promotion_fields(text: str, slot_id: str = IDENTITY_SLOT) -> str:
    """Return the contract text with the three fields added to one slot.

    Edits the bytes around the slot object only. A whole-document
    ``json.dumps`` round-trip would reformat every sidecar that inlines short
    arrays (``"forbid": ["weapon"]``), burying a three-line change under a
    few hundred lines of churn in ten of the catalog's contracts. Nothing in
    the repo formats ``skeletons/`` (prettier is scoped to ``frontend/src``),
    so that churn would be permanent and reviewer-hostile.

    Args:
        text: The raw contract sidecar text.
        slot_id: The slot id to promote.

    Returns:
        str: The edited text, byte-identical outside the slot object.

    Raises:
        ValueError: If the document has no single ``slots`` array, if the
            slot id is absent from it or declared more than once inside it,
            or if the edited text no longer parses to the intended document.
    """
    span_start, span_end = _slots_array_span(text)
    pattern = re.compile(rf'"id"\s*:\s*"{re.escape(slot_id)}"')
    matches = [
        match
        for match in pattern.finditer(text, span_start, span_end)
        if not _inside_string(text, match.start())
    ]
    if not matches:
        msg = f"no slot with id {slot_id!r}"
        raise ValueError(msg)
    if len(matches) > 1:
        msg = f"slot id {slot_id!r} occurs {len(matches)} times in 'slots'"
        raise ValueError(msg)
    _, close = _enclosing_object(text, matches[0].start())

    line_start = text.rfind("\n", 0, close) + 1
    property_indent = text[line_start:close] + "  "
    end = close - 1
    while text[end] in " \t\r\n":
        end -= 1
    fields = (
        '"kind": "personalizable"',
        f'"personalization_field": "{PERSONALIZATION_FIELD}"',
        f'"role_safety": "{ROLE_SAFETY}"',
    )
    addition = ",\n" + ",\n".join(property_indent + field for field in fields)
    edited = text[: end + 1] + addition + text[end + 1 :]

    expected = promote(json.loads(text))
    if json.loads(edited) != expected:
        msg = "surgical edit did not produce the intended document"
        raise ValueError(msg)
    return edited


def _report(
    *,
    already: int,
    excluded: list[str],
    violations: list[str],
    pending: list[str],
    applied: list[str],
    failed: list[tuple[str, str]],
    apply: bool,
) -> None:
    """Print the run's tally.

    Args:
        already: How many contracts were already promoted.
        excluded: Slugs correctly left unpromoted by policy.
        violations: Excluded slugs whose identity slot IS personalizable.
        pending: Slugs check mode found unpromoted and unexcluded.
        applied: Slugs written in ``--apply`` mode.
        failed: ``(slug, message)`` pairs that could not be promoted.
        apply: Whether the run was an ``--apply`` run.
    """
    print(f"already personalizable : {already}")
    print(f"excluded by policy     : {len(excluded)}")
    for slug in sorted(excluded):
        print(f"    {slug}: {NOT_PERSONALIZABLE[slug]}")
    if apply:
        print(f"promoted               : {len(applied)}")
    else:
        print(f"pending promotion      : {len(pending)}")
        for slug in sorted(pending):
            print(f"    {slug}")
    if violations:
        print(f"EXCLUDED BUT PROMOTED  : {len(violations)}")
        for slug in sorted(violations):
            print(f"    {slug}: {NOT_PERSONALIZABLE[slug]}")
    if failed:
        print(f"FAILED validation      : {len(failed)}")
        for slug, err in failed:
            print(f"    {slug}: {err}")


def main(argv: list[str] | None = None) -> int:
    """Run the promotion in check or apply mode.

    ``--apply`` is all-or-nothing: every edit is computed in memory first and
    nothing is written unless every one of them succeeded. A partial write is
    the worst outcome available here, because the tree it leaves behind (some
    slugs promoted, some not) is byte-for-byte indistinguishable from an
    ordinary mid-migration state, so the next check-mode run reports it as
    work still to do rather than as a failed run to investigate.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        int: ``0`` when nothing is pending (or everything applied cleanly),
            ``1`` when check mode found unpromoted slots, a promotion failed
            contract validation, or an excluded slug's identity slot was
            found personalizable.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the promotions; without it the run only reports",
    )
    parser.add_argument(
        "--skeleton-root",
        type=Path,
        default=Path("skeletons"),
        help="catalog root to scan (default: skeletons)",
    )
    args = parser.parse_args(argv)

    pending: list[str] = []
    edits: list[tuple[str, Path, str]] = []
    failed: list[tuple[str, str]] = []
    excluded: list[str] = []
    violations: list[str] = []
    already = 0

    for path in contract_paths(args.skeleton_root):
        slug = slug_for(path)
        text = path.read_text(encoding="utf-8")
        document = json.loads(text)

        # #CRITICAL: data-integrity: the exclusion roster is consulted BEFORE
        # anything else, for every contract, promoted or not. Consulting it
        # only for promotion candidates (as this loop originally did) makes
        # the roster unreadable for an already-personalizable slot, so an
        # excluded slug turned personalizable out of band (a hand edit, a bad
        # merge, another tool) would route into `already` and exit 0: check
        # mode would report all-clear on exactly the violation the roster
        # exists to prevent.
        # #VERIFY: tests/unit/test_promote_personalizable_slots.py::
        #   test_main_check_mode_excluded_slug_promoted_out_of_band_fails
        if slug in NOT_PERSONALIZABLE:
            (violations if is_personalizable(document) else excluded).append(slug)
            continue

        candidate = promote(document)
        if candidate is None:
            if is_personalizable(document):
                already += 1
            continue
        try:
            ThemeContract.model_validate(candidate)
        except ValueError as exc:  # pydantic ValidationError subclasses this
            failed.append((slug, str(exc).splitlines()[-1][:120]))
            continue
        if not args.apply:
            pending.append(slug)
            continue
        try:
            edits.append((slug, path, insert_promotion_fields(text)))
        except ValueError as exc:
            failed.append((slug, str(exc)[:120]))

    applied: list[str] = []
    if args.apply and not failed and not violations:
        for slug, path, edited in edits:
            path.write_text(edited, encoding="utf-8")
            applied.append(slug)

    _report(
        already=already,
        excluded=excluded,
        violations=violations,
        pending=pending,
        applied=applied,
        failed=failed,
        apply=args.apply,
    )

    if failed or violations:
        if args.apply:
            print("\nNothing was written: --apply is all-or-nothing.")
        return 1
    if pending and not args.apply:
        print(
            "\nRun with --apply to promote, or add a slug to "
            "NOT_PERSONALIZABLE with its reason."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
