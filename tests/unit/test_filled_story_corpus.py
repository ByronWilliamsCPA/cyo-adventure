"""Gate every committed filled story, not just its skeleton (AL-047).

The skeletons in ``skeletons/`` are covered by a glob-discovered suite, but the
filled stories in ``out/`` are the actual deliverable and were referenced by no
test at all. A skeleton passing the gate does not prove its fill passes: the two
are separate documents and a fill regresses independently through a prose edit, a
hand-patched body, or a broken slot render.

The irony that motivated this suite: the 746-node book's own L2-13 finding says
the Layer-2 configuration walk is its sole correctness guarantee at that scale,
and that walk was never run on the filled book in CI.

Discovery is by glob so a newly committed fill is covered without touching this
file, mirroring ``test_skeleton.py::_discover_production_skeletons``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.validator.gate import run_gate

_OUT_ROOT = Path(__file__).resolve().parent.parent.parent / "out"
_FILL_MARKER = "<<FILL"


def _discover_filled_stories() -> list[Path]:
    """Return every committed top-level filled story document."""
    if not _OUT_ROOT.is_dir():
        return []
    return sorted(_OUT_ROOT.glob("*.filled.json"))


# The pre-v2 quarantine (`_LEGACY_PRE_V2`) is gone, and deliberately not replaced by an
# empty frozenset. All three fills it held (`the-lost-mitten`, `the-sunken-signal`,
# `the-clocktower-cipher`) were migrated to schema v2 by running the production
# normalizer, `generation/import_catalog._normalize_legacy_fill`, over each file on disk
# and committing the result, so every committed fill now clears the gate unconditionally.
# Closes AL-050, whose proposed change was exactly "migrate all three to schema v2 and
# delete `_LEGACY_PRE_V2`". Re-adding a quarantine here would reintroduce the dumping
# ground the strict xfail existed to prevent; a fill that cannot pass the gate should be
# fixed or removed from `out/`, not marked expected-to-fail.
_FILLED = _discover_filled_stories()


@pytest.mark.unit
def test_the_corpus_is_not_empty() -> None:
    """Guard the guard: a broken glob must fail loudly, not silently pass."""
    assert _FILLED, (
        "no out/*.filled.json found; this suite would be vacuous, which is the "
        "failure mode AL-016 exists to prevent"
    )


@pytest.mark.unit
@pytest.mark.parametrize("path", _FILLED, ids=lambda p: Path(str(p)).name)
def test_filled_story_passes_the_gate(path: Path) -> None:
    """A committed fill must not be blocked by the deterministic gate."""
    blob = json.loads(path.read_text(encoding="utf-8"))
    result = run_gate(blob)
    blocking = [f for f in result.report.findings if f.severity.value == "error"]
    assert not result.blocked, (
        f"{path.name} is blocked by the gate: {[f.message for f in blocking][:5]}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("path", _FILLED, ids=lambda p: p.name)
def test_filled_story_has_no_unfilled_directives(path: Path) -> None:
    """A leftover FILL directive means the fill never finished."""
    raw = path.read_text(encoding="utf-8")
    assert _FILL_MARKER not in raw, (
        f"{path.name} still contains a {_FILL_MARKER} directive"
    )
