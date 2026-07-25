"""Every rule id the validator can emit must appear in the rule catalog (AL-017).

``docs/planning/validator-rules.md`` states in its own Purpose section that
adding, removing, or renumbering a rule requires a revision to it. That was
violated silently: L2-13 shipped, fired in production as the single finding of a
746-node story, and never appeared in the catalog, while RL-13's entry described
an implementation the code does not use.

The catalog is what a reviewer consults when a finding appears, so this test
makes that drift a build failure rather than a discovery. It greps the source for
literal rule ids instead of importing them, because the ids are string literals at
their emission sites and there is no registry to import.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VALIDATOR_ROOT = _REPO_ROOT / "src" / "cyo_adventure" / "validator"
_CATALOG = _REPO_ROOT / "docs" / "planning" / "validator-rules.md"

# Matches a quoted rule id as it appears at an emission site, e.g. rule_id="PL-23".
_RULE_ID_RE = re.compile(r'rule_id="((?:L1|L2|PL|RL|SR)-\d+)"')


def _emitted_rule_ids() -> set[str]:
    """Return every rule id assigned to a finding anywhere in the validator."""
    ids: set[str] = set()
    for path in sorted(_VALIDATOR_ROOT.rglob("*.py")):
        ids.update(_RULE_ID_RE.findall(path.read_text(encoding="utf-8")))
    return ids


@pytest.mark.unit
def test_the_scan_finds_rules() -> None:
    """Guard the guard: a broken regex must fail, not vacuously pass."""
    found = _emitted_rule_ids()
    assert len(found) >= 20, (
        f"only {len(found)} rule ids found by the scan; the emission pattern "
        f"probably changed and this suite has gone blind"
    )


@pytest.mark.unit
def test_every_emitted_rule_id_is_documented() -> None:
    """A rule that can fire must be findable in the catalog."""
    catalog = _CATALOG.read_text(encoding="utf-8")
    undocumented = sorted(rid for rid in _emitted_rule_ids() if rid not in catalog)
    assert not undocumented, (
        f"rule id(s) {undocumented} can be emitted but are absent from "
        f"{_CATALOG.name}; the catalog's own Purpose section requires a revision "
        f"when a rule is added"
    )
