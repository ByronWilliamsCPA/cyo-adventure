"""ADR-023 Task D4 pilot integrity proofs (the-midnight-museum, 10-13).

Proves, against the REAL on-disk pilot contract and skeleton (not a
synthetic fixture), the three claims Task D4 requires before the pilot
contract can be trusted: (1) the contract declares exactly the one
personalizable slot the pilot intends (HERO), (2) the Variant A/B at-rest
integrity checks (`verify_manifest`, ADR-023 Task R3 semantics: the mutated
blob no longer matches the version's DERIVED `sentinel_manifest`, not a
contract-prescribed multiset) actually fire against a mutated blob built
from this contract's own `default_binding.HERO` value ("Nadia"), and (3)
the zero-coverage soft floor (`_warn_on_zero_coverage_slots`,
`generation/worker.py`) emits a WARNING, never a failure, for this
contract's declared slot set when the fill prose never mentions it.

Builders reuse the small hand-built-document pattern already established in
`test_storybook_reinsertion.py` (`_skeleton`/`_node_text`-style documents)
rather than reinventing it. The warning capture is local
(`_capture_warning`): `test_worker.py`'s `_WarningCapturingLogger` doubles a
whole logger for the fill path, which this direct call to
`_warn_on_zero_coverage_slots` does not need.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.generation import worker as worker_module
from cyo_adventure.generation.binding import load_contract_for, personalizable_slot_ids
from cyo_adventure.generation.skeleton import load_skeleton
from cyo_adventure.storybook.reinsertion import (
    TokenOutcome,
    reinsert_storybook,
    verify_manifest,
)

if TYPE_CHECKING:
    from cyo_adventure.storybook.theme_contract import ThemeContract

# Root-anchored, not cwd-relative: three of this module's four tests read this
# file directly, and pytest is run from worktrees and subdirectories as often
# as from the repo root (the second occurrence of AL-073's lesson).
_PILOT_SKELETON_PATH = (
    Path(__file__).resolve().parents[2]
    / "skeletons"
    / "10-13"
    / "the-midnight-museum.json"
)

# The contract's own `default_binding.HERO` value (skeletons/10-13/the-midnight-museum.contract.json).
_PILOT_HERO_VALUE = "Nadia"


def _pilot_skeleton_and_contract() -> tuple[dict[str, object], ThemeContract]:
    """Load the real pilot skeleton and its cross-checked theme contract.

    Uses the production loaders (`load_skeleton`, `load_contract_for`)
    unchanged, so a future edit to either on-disk file that breaks the
    cross-check (declared slot set vs. `{SLOT}` tokens) fails this test the
    same way it would fail the real fill pipeline.
    """
    skeleton = load_skeleton(_PILOT_SKELETON_PATH)
    contract = load_contract_for(_PILOT_SKELETON_PATH, skeleton)
    assert contract is not None
    return skeleton, contract


def _skeleton_doc(nodes: list[dict[str, object]]) -> dict[str, object]:
    return {"nodes": nodes}


@pytest.mark.unit
def test_pilot_contract_declares_exactly_hero() -> None:
    """The pilot contract's personalizable slot set is exactly {HERO}.

    This is the D4 "power switch" itself: before this test, no on-disk
    contract declared any `kind: "personalizable"` slot at all
    (`personalizable_slot_ids` returned the empty set catalog-wide). A
    regression here (an accidental second slot, or HERO reverting to
    `kind: "theme"`) would silently widen or void the pilot's blast radius.

    The slot set alone is too coarse a guard: HERO could keep
    `kind: "personalizable"` while its `personalization_field` or
    `role_safety` drifted, which would rebind the slot to the wrong request
    field or drop it out of protagonist-scoped safety checks without changing
    the set. Both are asserted here.
    """
    _skeleton, contract = _pilot_skeleton_and_contract()

    assert personalizable_slot_ids(contract) == frozenset({"HERO"})
    hero = next(slot for slot in contract.slots if slot.id == "HERO")
    assert hero.kind == "personalizable"
    assert hero.personalization_field == "protagonist_first_name"
    assert hero.role_safety == "protagonist"


@pytest.mark.unit
def test_untouched_pilot_blob_passes_verify_manifest() -> None:
    """A document `reinsert_storybook` produced for HERO verifies clean against its own manifest.

    Uses the pilot contract's actual `default_binding.HERO` value ("Nadia"),
    so this exercises the exact string the pilot will bind, not an
    arbitrary placeholder.
    """
    pre_fill = _skeleton_doc(
        [{"id": "n_start", "body": f"{{~HERO:{_PILOT_HERO_VALUE}~}} steps inside."}]
    )
    filled = _skeleton_doc(
        [{"id": "n_start", "body": f"{_PILOT_HERO_VALUE} steps inside."}]
    )
    outcome = reinsert_storybook(pre_fill, filled)

    assert verify_manifest(outcome.document, outcome.manifest) is True


@pytest.mark.unit
def test_mutated_pilot_blob_fails_verify_manifest() -> None:
    """Variant A/B: three independent at-rest mutations of the pilot's HERO blob each fail verification.

    ADR-023 Task D4 / Stage R re-scope: "fire" means the mutated blob no
    longer matches the version's DERIVED `sentinel_manifest` (Task R3
    semantics), not a contract-prescribed token multiset. Three
    independent corruption shapes are exercised, mirroring
    `test_verify_manifest_rejects_a_mutated_document`,
    `_rejects_a_partial_occurrence_strip`, and `_rejects_a_forged_addition`
    in `test_storybook_reinsertion.py`, but against this pilot's own HERO
    binding rather than a generic fixture:

    1. Every occurrence stripped back to plain text (sentinel dropped).
    2. One of two occurrences stripped, the other left wrapped (partial strip).
    3. A forged sentinel injected into a node the manifest never recorded.
    """
    pre_fill = _skeleton_doc(
        [
            {
                "id": "n_start",
                "body": f"{{~HERO:{_PILOT_HERO_VALUE}~}} steps inside.",
            },
            {"id": "n_key", "body": "The case is locked tight."},
        ]
    )
    filled = _skeleton_doc(
        [
            {
                "id": "n_start",
                "body": (
                    f"{_PILOT_HERO_VALUE} paused. {_PILOT_HERO_VALUE} steps inside."
                ),
            },
            {"id": "n_key", "body": "The case is locked tight."},
        ]
    )
    outcome = reinsert_storybook(pre_fill, filled)
    assert verify_manifest(outcome.document, outcome.manifest) is True

    # Variant A: strip the sentinel back to plain text (at-rest hand-edit).
    stripped = {
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    f"{_PILOT_HERO_VALUE} paused. {_PILOT_HERO_VALUE} steps inside."
                ),
            },
            {"id": "n_key", "body": "The case is locked tight."},
        ]
    }
    assert verify_manifest(stripped, outcome.manifest) is False

    # Variant B: partial strip, one of two recorded occurrences dropped back
    # to plain text while the other stays wrapped (the manifest recorded
    # count=2 for n_start; only 1 wrapped occurrence remains at rest).
    document = outcome.document
    nodes = cast("list[dict[str, object]]", document["nodes"])
    partial = {
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    f"{_PILOT_HERO_VALUE} paused. "
                    f"{{~HERO:{_PILOT_HERO_VALUE}~}} steps inside."
                ),
            },
            nodes[1],
        ]
    }
    assert verify_manifest(partial, outcome.manifest) is False

    # Variant C: a forged sentinel injected into a node the manifest never claimed.
    forged = {
        "nodes": [
            nodes[0],
            {"id": "n_key", "body": "{~HERO:Someone Else~} unlocks the case."},
        ]
    }
    assert verify_manifest(forged, outcome.manifest) is False


@pytest.mark.unit
def test_hero_coverage_warns_only_when_hero_is_uncovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The soft floor fires for an uncovered HERO and stays silent for a covered one.

    Calls the worker's own `_warn_on_zero_coverage_slots` directly (the
    exact function `_run_skeleton_fill` invokes post-transform), fed the
    real pilot contract's declared slot set, so this proves the soft floor
    actually engages for HERO specifically, not just for a synthetic slot
    id.

    Both halves are asserted because the warning-only half alone is a weak
    guard: a check that warned unconditionally would satisfy it. The covered
    case is what makes "soft floor" falsifiable. That the function never
    raises is proved structurally, by both calls returning.
    """
    _skeleton, contract = _pilot_skeleton_and_contract()
    declared = personalizable_slot_ids(contract)

    # No `"reinsertable"` outcome anywhere for HERO: the model paraphrased
    # the value away in every node it appeared in.
    token_outcomes = (
        TokenOutcome(
            node_id="n_start",
            slot_id="HERO",
            value=_PILOT_HERO_VALUE,
            occurrence_count=0,
            status="not_found",
        ),
    )

    warning_calls: list[tuple[str, dict[str, object]]] = []

    def _capture_warning(event: str, **kwargs: object) -> None:
        warning_calls.append((event, kwargs))

    monkeypatch.setattr(worker_module.logger, "warning", _capture_warning)

    worker_module._warn_on_zero_coverage_slots(  # pyright: ignore[reportPrivateUsage]
        declared, token_outcomes, skeleton_slug="the-midnight-museum"
    )

    assert len(warning_calls) == 1
    event, kwargs = warning_calls[0]
    assert event == "generation_job.personalizable_slot_zero_coverage"
    assert kwargs["slot_ids"] == ["HERO"]
    assert kwargs["skeleton_slug"] == "the-midnight-museum"

    # The complement: one reinsertable occurrence anywhere covers the slot, so
    # the same declared set must produce no second warning.
    worker_module._warn_on_zero_coverage_slots(  # pyright: ignore[reportPrivateUsage]
        declared,
        (
            TokenOutcome(
                node_id="n_start",
                slot_id="HERO",
                value=_PILOT_HERO_VALUE,
                occurrence_count=1,
                status="reinsertable",
            ),
        ),
        skeleton_slug="the-midnight-museum",
    )

    assert len(warning_calls) == 1
