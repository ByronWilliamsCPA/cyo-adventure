"""WS-8 D6 tests: the parameterize-at-promotion glue (design section 7.3).

Covers the chained checks on a fixture ``(skeleton, plan, contract)`` triple:

- a valid triple passes the whole chain and yields a slotted skeleton whose
  ``check_theme_contract`` independently accepts;
- a plan that trips one of ``parameterize_skeleton``'s six fail-closed checks
  (a dangling reference; a corrupted ``role=``/``words=`` apply) fails the chain
  and writes nothing;
- a contract that fails ``check_theme_contract`` (a slot-id mismatch) fails the
  chain;
- the safety pin: the glue calls the real transform + contract checks and adds
  no bypass (source-level and behavioral).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cyo_adventure.generation.binding import contract_path_for
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import (
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
)
from scripts import check_theme_contract as ctc
from scripts import parameterize_promotion as pp

if TYPE_CHECKING:
    import pytest


# ---------------------------------------------------------------------------
# Fixtures: a pristine contract-less skeleton, a valid plan, a matching contract
# ---------------------------------------------------------------------------


def _pristine_skeleton() -> dict[str, object]:
    """A tiny, gate-passing, UNSLOTTED, contract-less fixture skeleton."""
    return {
        "schema_version": "2.0",
        "id": "s_test_param",
        "version": 1,
        "title": "Test Story",
        "metadata": {
            "age_band": "3-5",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 1.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": ["adventure"],
            "estimated_minutes": 5,
            "ending_count": 2,
            "topology": "time_cave",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    "<<FILL role=setup words=40 beats='Maya and her dog Biscuit "
                    "arrive at the sea cave and must choose a path.'>>"
                ),
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_a",
                        "label": "Approach the glinting tide pool.",
                        "target": "n_end_a",
                    },
                    {
                        "id": "c_b",
                        "label": "Turn back toward home.",
                        "target": "n_end_b",
                    },
                ],
            },
            {
                "id": "n_end_a",
                "body": (
                    "<<FILL role=ending words=30 beats='Maya claims the "
                    "glass starfish and celebrates.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The Glass Starfish",
                },
                "choices": [],
            },
            {
                "id": "n_end_b",
                "body": (
                    "<<FILL role=ending words=30 beats='Maya returns home safely.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "neutral",
                    "kind": "completion",
                    "title": "Home Again",
                },
                "choices": [],
            },
        ],
    }


def _valid_plan() -> dict[str, object]:
    """A slotting plan that neutralizes every beat/title, and one label."""
    return {
        "beats": {
            "n_start": (
                "{HERO} and {COMPANION} arrive at {THRESHOLD} and must choose a path."
            ),
            "n_end_a": "{HERO} claims {PRIZE} and celebrates.",
            "n_end_b": "{HERO} returns home safely.",
        },
        "titles": {
            "n_end_a": "The {PRIZE}",
            "n_end_b": "Home Again",
        },
        "labels": {
            "n_start": {"c_a": "Approach {OFFER}."},
        },
    }


_DEFAULT_BINDINGS = {
    "HERO": "Priya",
    "COMPANION": "Biscuit the dog",
    "THRESHOLD": "the sea cave",
    "OFFER": "the tide pool",
    "PRIZE": "Glass Starfish",
}


def _slot(
    slot_id: str,
    *,
    scope: SlotScope = SlotScope.GLOBAL,
    forbid: list[str] | None = None,
) -> SlotSpec:
    return SlotSpec(
        id=slot_id,
        scope=scope,
        meaning=f"placeholder meaning for {slot_id}",
        constraints=SlotConstraints(max_words=8, forbid=forbid or ["weapon"]),
    )


def _valid_contract() -> ThemeContract:
    """A contract declaring exactly the plan's five slot ids, at a floor-free band."""
    return ThemeContract(
        contract_version=1,
        skeleton_slug="s_test_param",
        age_band=AgeBand.BAND_13_16,
        legacy_lexicon=[],
        default_binding=dict(_DEFAULT_BINDINGS),
        slots=[
            _slot("HERO"),
            _slot("COMPANION"),
            _slot("THRESHOLD", scope=SlotScope.TRACK, forbid=["lethal", "weapon"]),
            _slot("OFFER", scope=SlotScope.TRACK),
            _slot("PRIZE", scope=SlotScope.ENDING, forbid=["lethal", "weapon"]),
        ],
    )


def _slot_id_mismatch_contract() -> ThemeContract:
    """A contract with an EXTRA slot the skeleton never exposes (token-set drift)."""
    contract = _valid_contract()
    slots = [*contract.slots, _slot("EXTRA")]
    bindings = dict(contract.default_binding)
    bindings["EXTRA"] = "an unused extra"
    return contract.model_copy(update={"slots": slots, "default_binding": bindings})


def _write(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_contract(tmp_path: Path, name: str, contract: ThemeContract) -> Path:
    path = tmp_path / name
    path.write_text(contract.model_dump_json(), encoding="utf-8")
    return path


class _FakeGitRunner:
    """A git seam that never touches git; returns a fixed branch."""

    def __init__(self, branch: str) -> None:
        self.branch = branch
        self.worktrees: list[tuple[Path, str]] = []

    def current_branch(self) -> str:
        return self.branch

    def add_worktree(self, worktree_dir: Path, branch: str) -> None:
        self.worktrees.append((worktree_dir, branch))


class _RecordingPrCreator:
    """A PR creator that records requests (never merges/approves)."""

    def __init__(self) -> None:
        self.calls: list[pp.PrRequest] = []

    def __call__(self, request: pp.PrRequest, *, worktree_dir: Path) -> None:
        _ = worktree_dir
        self.calls.append(request)


# ---------------------------------------------------------------------------
# Happy path: the full chain passes and yields an acceptable slotted pair
# ---------------------------------------------------------------------------


def test_valid_triple_passes_chain_and_prepares_draft_pr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A valid (skeleton, plan, contract) triple passes the whole chain (dry run)."""
    skeleton_path = _write(tmp_path, "s_test_param.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    contract_path = _write_contract(tmp_path, "contract.json", _valid_contract())
    out_dir = tmp_path / "work"
    creator = _RecordingPrCreator()

    code = pp.main(
        [
            str(skeleton_path),
            "--plan",
            str(plan_path),
            "--contract",
            str(contract_path),
            "--out-dir",
            str(out_dir),
        ],
        git_runner=_FakeGitRunner("claude/ws8-planning"),
        pr_creator=creator,
    )

    assert code == 0, capsys.readouterr().out
    # The chain wrote a slotted skeleton and authored its contract sidecar.
    slotted = out_dir / "s_test_param.json"
    sidecar = contract_path_for(slotted)
    assert slotted.is_file()
    assert sidecar.is_file()
    # The produced pair independently passes check_theme_contract.
    assert ctc.main([str(slotted)]) == 0
    # A draft PR carrying the skeleton-promotion label was prepared.
    assert len(creator.calls) == 1
    request = creator.calls[0]
    assert request.draft is True
    assert pp.PROMOTION_LABEL in request.labels
    assert request.head == "flywheel/parameterize-s_test_param"
    assert "does NOT block" in request.body


def test_dry_run_default_creator_prints_gh_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no injected creator, the default dry-run creator prints the gh command."""
    skeleton_path = _write(tmp_path, "s_test_param.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    contract_path = _write_contract(tmp_path, "contract.json", _valid_contract())

    code = pp.main(
        [
            str(skeleton_path),
            "--plan",
            str(plan_path),
            "--contract",
            str(contract_path),
            "--out-dir",
            str(tmp_path / "work"),
        ],
        git_runner=_FakeGitRunner("feature/x"),
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "gh pr create --draft --label skeleton-promotion" in out


# ---------------------------------------------------------------------------
# Refusals: branch and already-parameterized
# ---------------------------------------------------------------------------


def test_refuses_on_main_branch(tmp_path: Path) -> None:
    """The glue exits non-zero and prepares nothing when the branch is main."""
    skeleton_path = _write(tmp_path, "s_test_param.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    contract_path = _write_contract(tmp_path, "contract.json", _valid_contract())
    creator = _RecordingPrCreator()

    code = pp.main(
        [
            str(skeleton_path),
            "--plan",
            str(plan_path),
            "--contract",
            str(contract_path),
        ],
        git_runner=_FakeGitRunner("main"),
        pr_creator=creator,
    )

    assert code == 1
    assert creator.calls == []


def test_refuses_already_parameterized_skeleton(tmp_path: Path) -> None:
    """A skeleton that already exposes {SLOT} tokens is refused before the chain."""
    already = _pristine_skeleton()
    nodes = cast("list[dict[str, object]]", already["nodes"])
    nodes[0]["body"] = "<<FILL role=setup words=40 beats='{HERO} arrives.'>>"
    skeleton_path = _write(tmp_path, "s_test_param.json", already)
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    contract_path = _write_contract(tmp_path, "contract.json", _valid_contract())
    creator = _RecordingPrCreator()

    code = pp.main(
        [
            str(skeleton_path),
            "--plan",
            str(plan_path),
            "--contract",
            str(contract_path),
        ],
        git_runner=_FakeGitRunner("feature/x"),
        pr_creator=creator,
    )

    assert code == 1
    assert creator.calls == []


# ---------------------------------------------------------------------------
# The transform's six fail-closed checks gate the chain (nothing written)
# ---------------------------------------------------------------------------


def test_dangling_reference_plan_fails_chain_and_writes_nothing(tmp_path: Path) -> None:
    """A plan missing a FILL node mapping trips a transform check; nothing is written."""
    plan = _valid_plan()
    beats = cast("dict[str, str]", plan["beats"])
    del beats["n_end_b"]  # dangling: a FILL node has no beats mapping
    skeleton_path = _write(tmp_path, "s_test_param.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", plan)
    contract_path = _write_contract(tmp_path, "contract.json", _valid_contract())
    out_dir = tmp_path / "work"
    creator = _RecordingPrCreator()

    code = pp.main(
        [
            str(skeleton_path),
            "--plan",
            str(plan_path),
            "--contract",
            str(contract_path),
            "--out-dir",
            str(out_dir),
        ],
        git_runner=_FakeGitRunner("feature/x"),
        pr_creator=creator,
    )

    assert code == 1
    assert creator.calls == []
    # The transform never wrote a slotted skeleton, so no sidecar exists either.
    assert not (out_dir / "s_test_param.json").exists()
    assert not contract_path_for(out_dir / "s_test_param.json").exists()


def test_byte_preservation_violation_fails_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupted apply that mangles words= trips the transform's role/words check."""
    real_apply_beats = pp.ps._apply_beats

    def _corrupting_apply_beats(
        skeleton: dict[str, object],
        beats_plan: dict[str, str],
        errors: list[str],
    ) -> set[str]:
        rewritten = real_apply_beats(skeleton, beats_plan, errors)
        for node in pp.ps._iter_nodes(skeleton):
            if node.get("id") == "n_start":
                node["body"] = cast("str", node["body"]).replace("words=40", "words=4")
        return rewritten

    monkeypatch.setattr(pp.ps, "_apply_beats", _corrupting_apply_beats)

    skeleton_path = _write(tmp_path, "s_test_param.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    contract_path = _write_contract(tmp_path, "contract.json", _valid_contract())
    out_dir = tmp_path / "work"
    creator = _RecordingPrCreator()

    code = pp.main(
        [
            str(skeleton_path),
            "--plan",
            str(plan_path),
            "--contract",
            str(contract_path),
            "--out-dir",
            str(out_dir),
        ],
        git_runner=_FakeGitRunner("feature/x"),
        pr_creator=creator,
    )

    assert code == 1
    assert creator.calls == []
    assert not (out_dir / "s_test_param.json").exists()


# ---------------------------------------------------------------------------
# The contract acceptance gates the chain
# ---------------------------------------------------------------------------


def test_slot_id_mismatch_contract_fails_chain(tmp_path: Path) -> None:
    """A contract whose slot ids do not match the slotted tokens fails check 2."""
    skeleton_path = _write(tmp_path, "s_test_param.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    contract_path = _write_contract(
        tmp_path, "contract.json", _slot_id_mismatch_contract()
    )
    out_dir = tmp_path / "work"
    creator = _RecordingPrCreator()

    code = pp.main(
        [
            str(skeleton_path),
            "--plan",
            str(plan_path),
            "--contract",
            str(contract_path),
            "--out-dir",
            str(out_dir),
        ],
        git_runner=_FakeGitRunner("feature/x"),
        pr_creator=creator,
    )

    assert code == 1
    assert creator.calls == []
    # The transform succeeded (slotted skeleton exists), but acceptance rejected
    # the contract, so no PR was prepared.
    assert (out_dir / "s_test_param.json").is_file()


# ---------------------------------------------------------------------------
# Safety pin: the glue calls the real checks and adds no bypass
# ---------------------------------------------------------------------------


def test_glue_source_calls_the_real_checks_and_adds_no_bypass() -> None:
    """Source pin: the glue invokes the transform + contract mains, never a bypass."""
    source = Path(pp.__file__).read_text(encoding="utf-8")
    # It chains the two real check entrypoints.
    assert "ps.main(" in source
    assert "ctc.main(" in source
    # It does not re-implement (and thereby short-circuit) either gate: the six
    # fail-closed checks live in parameterize_skeleton, the contract checks in
    # check_theme_contract; the glue must not call run_gate/structure_fingerprint
    # itself as a substitute path.
    assert "run_gate(" not in source
    assert "structure_fingerprint(" not in source


def test_transform_failure_short_circuits_before_contract_and_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the transform reports failure, the chain stops: no contract call, no PR."""
    ctc_calls: list[list[str]] = []
    real_ctc_main = pp.ctc.main

    def _recording_ctc_main(argv: list[str] | None = None) -> int:
        ctc_calls.append(list(argv or []))
        return real_ctc_main(argv)

    monkeypatch.setattr(pp.ps, "main", lambda _argv: 1)
    monkeypatch.setattr(pp.ctc, "main", _recording_ctc_main)

    skeleton_path = _write(tmp_path, "s_test_param.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    contract_path = _write_contract(tmp_path, "contract.json", _valid_contract())
    creator = _RecordingPrCreator()

    code = pp.main(
        [
            str(skeleton_path),
            "--plan",
            str(plan_path),
            "--contract",
            str(contract_path),
        ],
        git_runner=_FakeGitRunner("feature/x"),
        pr_creator=creator,
    )

    assert code == 1
    assert ctc_calls == []  # contract acceptance never reached
    assert creator.calls == []  # no PR prepared
