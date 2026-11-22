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

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.policy import check_unbound_slot_tokens

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


# Fills that still carry an unbound ``{SLOT}`` token, found when PL-29 landed. Keyed by
# file name; the value says why the exemption exists and where the fix is tracked.
#
# Strict xfail, not a skip and not a quarantine: the moment a book is fixed its xfail
# becomes an XPASS, which strict mode reports as a FAILURE, so the entry has to be
# deleted in the same change that fixes the book. This is the only exemption in this
# file and it is bounded by a named follow-up (UW-C479); do not add a second one.
_KNOWN_UNBOUND_TOKENS: dict[str, str] = {
    "the-clocktower-cipher.filled.json": (
        "frozen as the 10-13 book of the WP-1.6 fresh-corpus test until it is "
        "scored; three ending titles are raw skeleton slot tokens (UW-C479)"
    ),
    "the-lost-mitten.filled.json": (
        "n_found's ending title is the raw skeleton text 'The {ITEM_COLOR} "
        "{LOST_ITEM}'; not edited here because it may belong to the same frozen "
        "corpus (UW-C479)"
    ),
}


def _unbound_token_params() -> list[object]:
    """Parametrize every fill, marking the known offenders as strict xfails."""
    params: list[object] = []
    for path in _FILLED:
        reason = _KNOWN_UNBOUND_TOKENS.get(path.name)
        marks = [pytest.mark.xfail(strict=True, reason=reason)] if reason else []
        params.append(pytest.param(path, id=path.name, marks=marks))
    return params


@pytest.mark.unit
@pytest.mark.parametrize("path", _unbound_token_params())
def test_filled_story_has_no_unbound_slot_tokens(path: Path) -> None:
    """PL-29 over the committed fills, called directly (not via the gate posture).

    ``test_filled_story_passes_the_gate`` runs ``run_gate`` under the default
    ``"skeleton"`` posture, where PL-27/PL-28/PL-29 do not run at all, so it cannot
    see a token left in a finished book. This calls the checker itself.
    """
    story = Storybook.model_validate(json.loads(path.read_text(encoding="utf-8")))
    findings = check_unbound_slot_tokens(story).errors
    assert not findings, f"{path.name}: {[f.message for f in findings][:3]}"


@pytest.mark.unit
def test_known_unbound_exemptions_name_real_files() -> None:
    """An exemption for a file that no longer exists would never expire."""
    assert set(_KNOWN_UNBOUND_TOKENS) <= {p.name for p in _FILLED}
