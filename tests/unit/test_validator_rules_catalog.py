"""Lockstep guard: every enforced rule id must appear in the rule catalog.

``docs/planning/validator-rules.md`` calls itself the stable reference for every
validation rule, and the S6 close-out step assumed it was "lockstep-tested, so
this is not optional". It was not. The only mention of the catalog anywhere in
the suite was a docstring in ``test_fixtures_validate.py``, and in that gap the
registry drifted badly: ``L2-13``, ``L2-14`` and **the entire SR family**
(``SR-1``..``SR-7``, ``SR-9``) were enforced in ``src/cyo_adventure/validator/``
while documented nowhere in the catalog.

This module is that missing test. It fails when code and catalog disagree in
either direction, so the drift cannot silently recur:

* a rule id emitted by the validator but absent from the catalog is an
  undocumented gate, which is what happened to SR;
* a rule id in the catalog with no counterpart in code must say why in its own
  row, in one of exactly two ways. ``RESERVED`` means another branch holds the
  id and ``main`` must not reuse it (``SR-8``, held by PR #416, per the plan's
  method rule 5: an id is free only when no *open* PR has claimed it).
  ``NO ID EMITTED`` means the row documents semantics rather than a reportable
  finding (``L2-8``, which defines the configuration walk every other L2 rule
  is stated against, and whose named failure L1-6 makes unreachable). Anything
  else is a stale entry.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATOR_DIR = _REPO_ROOT / "src" / "cyo_adventure" / "validator"
_CATALOG = _REPO_ROOT / "docs" / "planning" / "validator-rules.md"

# The rule-id grammar shared by every family. Bounded to the families the
# catalog actually governs, so an unrelated token like "UTF-8" cannot match.
_RULE_ID_RE = re.compile(r"\b(?:L1|L2|PL|RL|SAFE|SR)-\d+\b")

# Families the catalog delegates elsewhere rather than defining inline. PL-19,
# PL-20 and PL-21 are specified in ADR-011 and the catalog says so explicitly;
# they are referenced by id in its prose, so they still resolve here.
_DELEGATED: frozenset[str] = frozenset()


def _ids_in(text: str) -> frozenset[str]:
    """Return every rule id appearing in a blob of text.

    Args:
        text: File contents to scan.

    Returns:
        frozenset[str]: The distinct rule ids found.
    """
    return frozenset(_RULE_ID_RE.findall(text))


def _code_rule_ids() -> frozenset[str]:
    """Return every rule id referenced anywhere under ``validator/``.

    Scans whole files rather than only message literals, because a rule's id
    also appears in the docstring that defines its semantics and in the
    cross-references between rules; all of those are ids the catalog is
    supposed to carry.

    Returns:
        frozenset[str]: The distinct rule ids the validator package knows about.
    """
    found: set[str] = set()
    for path in sorted(_VALIDATOR_DIR.glob("*.py")):
        found |= _ids_in(path.read_text(encoding="utf-8"))
    return frozenset(found)


def test_the_catalog_and_the_validator_package_are_both_findable() -> None:
    """Guard the guard: a moved catalog or package must fail loudly."""
    assert _CATALOG.is_file(), f"rule catalog not found at {_CATALOG}"
    assert list(_VALIDATOR_DIR.glob("*.py")), (
        f"no validator modules under {_VALIDATOR_DIR}"
    )
    assert _code_rule_ids(), "found no rule ids in the validator package at all"


def test_every_enforced_rule_id_is_documented() -> None:
    """An enforced rule absent from the catalog is an undocumented gate.

    This is the assertion that would have caught the SR family, L2-13 and
    L2-14 when they landed.
    """
    catalogued = _ids_in(_CATALOG.read_text(encoding="utf-8")) | _DELEGATED
    missing = sorted(_code_rule_ids() - catalogued)
    assert not missing, (
        "rule id(s) enforced in src/cyo_adventure/validator/ but absent from "
        f"docs/planning/validator-rules.md: {missing}. Adding, removing or "
        "renumbering a rule requires a catalog revision."
    )


def test_a_catalogued_rule_with_no_code_declares_why() -> None:
    """A catalog entry with no implementation must declare which shape it is.

    Without this, a stale row, a deliberate reservation, and a semantics-only
    row all look identical, and a future author cannot tell which ids are safe
    to claim. Both live cases are load-bearing: ``SR-8`` is implemented by PR
    #416 so must stay unused on ``main``, and ``L2-8`` defines the walk itself.
    """
    catalog_text = _CATALOG.read_text(encoding="utf-8")
    undocumented_in_code = sorted(_ids_in(catalog_text) - _code_rule_ids())
    for rule_id in undocumented_in_code:
        row = next(
            (
                line
                for line in catalog_text.splitlines()
                if line.startswith(f"| {rule_id} ")
            ),
            None,
        )
        assert row is not None, (
            f"{rule_id} appears in the catalog's prose but has no code and no table "
            "row; give it a row stating why, or remove the reference."
        )
        assert "RESERVED" in row or "NO ID EMITTED" in row, (
            f"{rule_id} is catalogued but no code references it, and its row declares "
            "neither RESERVED (another branch holds the id) nor NO ID EMITTED (the row "
            "documents semantics, not a reportable finding). Mark which it is, naming "
            "who holds a reservation, or delete the stale entry."
        )
