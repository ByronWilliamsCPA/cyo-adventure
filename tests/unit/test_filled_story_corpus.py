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


# Committed fills that predate Storybook schema v2 and cannot pass today's gate:
# they carry the retired ``ending.type`` field instead of ``ending.kind`` /
# ``ending.valence`` and omit the now-required ``metadata.topology``. They are
# legacy demo artifacts, not regressions, and this suite is what surfaced them.
# xfail is STRICT on purpose: migrating one of these to v2 makes its test XPASS,
# which fails the suite and forces this list to be pruned, so the quarantine can
# never quietly become a dumping ground for genuinely broken fills.
_LEGACY_PRE_V2 = frozenset(
    {
        "the-lost-mitten.filled.json",
        "the-sunken-signal.filled.json",
        "the-clocktower-cipher.filled.json",
    }
)

_FILLED = _discover_filled_stories()


def _gate_params() -> list[object]:
    """Return parametrize entries, quarantining the known pre-v2 documents."""
    params: list[object] = []
    for path in _FILLED:
        if path.name in _LEGACY_PRE_V2:
            params.append(
                pytest.param(
                    path,
                    marks=pytest.mark.xfail(
                        strict=True,
                        reason=(
                            "pre-schema-v2 fill: uses ending.type and omits "
                            "metadata.topology; migrate to v2 then drop from "
                            "_LEGACY_PRE_V2"
                        ),
                    ),
                )
            )
        else:
            params.append(path)
    return params


@pytest.mark.unit
def test_the_corpus_is_not_empty() -> None:
    """Guard the guard: a broken glob must fail loudly, not silently pass."""
    assert _FILLED, (
        "no out/*.filled.json found; this suite would be vacuous, which is the "
        "failure mode AL-016 exists to prevent"
    )
    stale = _LEGACY_PRE_V2 - {p.name for p in _FILLED}
    assert not stale, f"_LEGACY_PRE_V2 names files that no longer exist: {stale}"


@pytest.mark.unit
@pytest.mark.parametrize("path", _gate_params(), ids=lambda p: Path(str(p)).name)
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
