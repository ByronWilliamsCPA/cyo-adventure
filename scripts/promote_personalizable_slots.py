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
rather than defaulting to "not personalizable" by silence.

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
#   test_every_promotion_declares_protagonist_role_safety
PERSONALIZATION_FIELD: Final[str] = "protagonist_first_name"
ROLE_SAFETY: Final[str] = "protagonist"

# Skeletons whose HERO must NOT be personalized, each with the reason.
#
# #CRITICAL: data-integrity: every entry here is a story whose protagonist is
# an ANIMAL, established in the prose by body language the slot substitution
# cannot rewrite. Personalizing one renders a real child's name attached to a
# body they do not have ("Briella looked at one bare paw"), which is the most
# visible way this feature can read as broken to the exact youngest readers it
# most serves. Evidence is the hero-name proximity scan described in the
# design spec, not a keyword count over the whole book: animal words in a book
# usually belong to a COMPANION (Maya's dog, Nia's clockwork menagerie, Wren's
# cat), and a whole-book scan misclassifies all three as animal protagonists.
# #VERIFY: tests/unit/test_promote_personalizable_slots.py::
#   test_excluded_slugs_are_never_promoted
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
}


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
        ValueError: If the slot id is not present, or if the edited text no
            longer parses to the intended document.
    """
    match = re.search(rf'"id"\s*:\s*"{re.escape(slot_id)}"', text)
    if match is None:
        msg = f"no slot with id {slot_id!r}"
        raise ValueError(msg)
    _, close = _enclosing_object(text, match.start())

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


def main(argv: list[str] | None = None) -> int:
    """Run the promotion in check or apply mode.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        int: ``0`` when nothing is pending (or everything applied cleanly),
            ``1`` when check mode found unpromoted slots or a promotion
            failed contract validation.
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
    applied: list[str] = []
    failed: list[tuple[str, str]] = []
    excluded: list[str] = []
    already = 0

    for path in contract_paths(args.skeleton_root):
        slug = slug_for(path)
        document = json.loads(path.read_text())
        candidate = promote(document)
        if candidate is None:
            slots = document.get("slots")
            if isinstance(slots, list) and any(
                isinstance(s, dict)
                and s.get("id") == IDENTITY_SLOT
                and s.get("kind") == "personalizable"
                for s in slots
            ):
                already += 1
            continue
        if slug in NOT_PERSONALIZABLE:
            excluded.append(slug)
            continue
        try:
            ThemeContract.model_validate(candidate)
        except ValueError as exc:  # pydantic ValidationError subclasses this
            failed.append((slug, str(exc).splitlines()[-1][:120]))
            continue
        if args.apply:
            path.write_text(insert_promotion_fields(path.read_text()))
            applied.append(slug)
        else:
            pending.append(slug)

    print(f"already personalizable : {already}")
    print(f"excluded by policy     : {len(excluded)}")
    for slug in sorted(excluded):
        print(f"    {slug}: {NOT_PERSONALIZABLE[slug]}")
    if args.apply:
        print(f"promoted               : {len(applied)}")
    else:
        print(f"pending promotion      : {len(pending)}")
        for slug in sorted(pending):
            print(f"    {slug}")
    if failed:
        print(f"FAILED validation      : {len(failed)}")
        for slug, err in failed:
            print(f"    {slug}: {err}")

    if failed:
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
