"""Unit tests for scripts/check_fill_integrity.py.

scripts/ is not an importable package (no __init__.py, by design; see
per-file-ignores INP for scripts/**/*.py in pyproject.toml), so the module
is loaded directly from its file path via importlib.

Covers the WS-0 labels-are-leaves alignment: a fill that only rewrites
choice labels (in addition to bodies) passes the structural check, while a
rewritten ``target`` still fails it.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str) -> ModuleType:
    """Load a scripts/ module from its file path."""
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_fill_integrity = _load("check_fill_integrity")

pytestmark = pytest.mark.unit

_SKELETON: dict[str, Any] = {
    "schema_version": "2.0",
    "id": "sk_test",
    "version": 1,
    "title": "A Fine Adventure",
    "metadata": {
        "age_band": "8-11",
        "reading_level": {"scheme": "flesch_kincaid", "target": 4.5},
        "tier": 1,
        "estimated_minutes": 5,
        "ending_count": 1,
        "topology": "gauntlet",
    },
    "start_node": "n1",
    "nodes": [
        {
            "id": "n1",
            "body": "<<FILL body>>",
            "is_ending": False,
            "choices": [
                {"id": "c1", "label": "<<FILL label>>", "target": "n2"},
            ],
        },
        {
            "id": "n2",
            "body": "<<FILL body>>",
            "is_ending": True,
            "ending": {
                "id": "e1",
                "valence": "positive",
                "kind": "completion",
                "title": "Home Safe",
            },
        },
    ],
}


def _filled() -> dict[str, Any]:
    """Return a filled version of ``_SKELETON`` with bodies/labels replaced.

    Title and ending title are left untouched here so individual tests can
    opt into rewriting them; since the 2026-08-21 ruling they are leaf
    fields by default and ``--frozen-titles`` restores the old comparison.
    """
    filled = copy.deepcopy(_SKELETON)
    filled["nodes"][0]["body"] = "You stand at a fork in the path."
    filled["nodes"][0]["choices"][0]["label"] = "Go toward the light."
    filled["nodes"][1]["body"] = "You made it home safe."
    return filled


def _write(tmp_path: Path, name: str, data: dict[str, Any]) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_label_rewritten_fill_passes_the_structure_check(tmp_path: Path) -> None:
    """A fill that rewrites bodies and choice labels passes structural check."""
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    filled_path = _write(tmp_path, "filled.json", _filled())
    exit_code = check_fill_integrity.main([skeleton_path, filled_path])
    assert exit_code == 0


def test_title_rewrite_is_legal_by_default_and_frozen_titles_restores_it(
    tmp_path: Path,
) -> None:
    """Storybook and ending titles are leaves by default (ruled 2026-08-21).

    The 2026-08-21 ruling (live-structural-round-2026-08-21.md section 8.3)
    makes both titles leaf content: 15 of 16 measured one-shot fills retitled
    endings, and AL-161 already showed byte-frozen titles are a sibling
    recognition channel. A title diff therefore passes without any flag; the
    deprecated --allow-title-rewrite stays accepted as a no-op; and
    --frozen-titles restores the pre-ruling comparison for callers that want
    the old strictness.
    """
    filled = _filled()
    filled["title"] = "The Comet Glyphs"
    filled["nodes"][1]["ending"]["title"] = "Starlight Kept"
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    filled_path = _write(tmp_path, "filled.json", filled)
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 0
    assert (
        check_fill_integrity.main([skeleton_path, filled_path, "--allow-title-rewrite"])
        == 0
    )
    assert (
        check_fill_integrity.main([skeleton_path, filled_path, "--frozen-titles"]) == 1
    )


def test_frozen_titles_still_passes_an_untouched_fill(tmp_path: Path) -> None:
    """--frozen-titles restores the old comparison, not a new failure mode."""
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    filled_path = _write(tmp_path, "filled.json", _filled())
    assert (
        check_fill_integrity.main([skeleton_path, filled_path, "--frozen-titles"]) == 0
    )


def test_rewritten_target_fails_the_structure_check(tmp_path: Path) -> None:
    """A fill whose choice target changes is a genuine structural violation."""
    filled = _filled()
    filled["nodes"][0]["choices"][0]["target"] = "n1"
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    filled_path = _write(tmp_path, "filled.json", filled)
    exit_code = check_fill_integrity.main([skeleton_path, filled_path])
    assert exit_code == 1


def test_variable_description_rewrite_passes_but_machine_fields_stay_frozen(
    tmp_path: Path,
) -> None:
    """A themed variable description is a reskin; its machine fields are not.

    The 2026-08-21 freeze split (section 8.2) makes ``variables[].description``
    writable, matching ``normalize_filled_story``'s overlay; the comparison
    previously retained descriptions and reported a valid retheme as a
    structural failure (PR #737 review finding). Name/type/bounds/initial stay
    in the comparison.
    """
    skeleton = copy.deepcopy(_SKELETON)
    skeleton["variables"] = [
        {
            "name": "plates",
            "type": "int",
            "min": 0,
            "max": 3,
            "initial": 3,
            "description": "Unexposed photographic plates remaining.",
        }
    ]
    rethemed = copy.deepcopy(skeleton)
    rethemed["nodes"][0]["body"] = "You stand at a fork in the path."
    rethemed["nodes"][0]["choices"][0]["label"] = "Go toward the light."
    rethemed["nodes"][1]["body"] = "You made it home safe."
    rethemed["variables"][0]["description"] = "Glass slides left in the carrier."
    skeleton_path = _write(tmp_path, "skeleton.json", skeleton)
    assert (
        check_fill_integrity.main(
            [skeleton_path, _write(tmp_path, "rethemed.json", rethemed)]
        )
        == 0
    )
    moved = copy.deepcopy(rethemed)
    moved["variables"][0]["max"] = 5
    assert (
        check_fill_integrity.main(
            [skeleton_path, _write(tmp_path, "moved.json", moved)]
        )
        == 1
    )


def test_check_fill_integrity_rejects_same_file(tmp_path: Path) -> None:
    """Comparing a file against itself is a degenerate, always-passing input.

    AL-016: a builder bug once wrote the prose story to both the skeleton
    and filled paths, and the structural comparison then compared a file
    with itself and passed, making the verification vacuous. The checker
    must refuse this input outright rather than report a meaningless
    success.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    exit_code = check_fill_integrity.main([skeleton_path, skeleton_path])
    assert exit_code == 1


def _commissioned_skeleton() -> dict[str, Any]:
    """Return ``_SKELETON`` with explicit ``words=`` targets on both nodes."""
    skeleton = copy.deepcopy(_SKELETON)
    skeleton["nodes"][0]["body"] = "<<FILL role=scene words=100 beats='a fork'>>"
    skeleton["nodes"][1]["body"] = "<<FILL role=ending words=100 beats='home'>>"
    return skeleton


def _filled_at(words_per_node: int) -> dict[str, Any]:
    """Return a fill of ``_commissioned_skeleton`` at a chosen delivery length."""
    filled = copy.deepcopy(_SKELETON)
    body = " ".join(f"word{i}" for i in range(words_per_node))
    filled["nodes"][0]["body"] = body
    filled["nodes"][0]["choices"][0]["label"] = "Go toward the light."
    filled["nodes"][1]["body"] = body
    return filled


def test_an_underdelivered_fill_fails_the_fill_rate_check(tmp_path: Path) -> None:
    """A book at 40 percent of its commissioned words is blocked (AL-490).

    The live DeepSeek run delivered 38.9-52.9 percent of three books'
    commissioned prose and every book passed, because the per-node advisory
    is soft and the only hard word rule is a ceiling. The story-level ratio
    is the check that composes those legitimate per-node liberties into an
    illegitimate whole.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    filled_path = _write(tmp_path, "filled.json", _filled_at(40))
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 1


def test_a_delivered_fill_passes_the_fill_rate_check(tmp_path: Path) -> None:
    """Delivery near the commissioned total clears the floor."""
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    filled_path = _write(tmp_path, "filled.json", _filled_at(95))
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 0


def test_min_fill_rate_zero_measures_without_blocking(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A zero floor reports the ratio but never fails on it."""
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    filled_path = _write(tmp_path, "filled.json", _filled_at(40))
    assert (
        check_fill_integrity.main([skeleton_path, filled_path, "--min-fill-rate", "0"])
        == 0
    )
    assert (
        "fill-rate: delivered 80 of 200 commissioned words" in capsys.readouterr().out
    ), (
        "a zero floor must still measure and report the fill rate; success "
        "with no fill-rate line means the measurement was skipped, not passed"
    )


@pytest.mark.parametrize(
    "floor", ["nan", "inf", "-0.5"], ids=["nan", "inf", "negative"]
)
def test_a_degenerate_fill_rate_floor_is_refused(
    tmp_path: Path, floor: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A NaN or negative floor would pass every fill, so it is a usage error.

    ``fill_rate < float("nan")`` is False for every ratio and a negative
    floor sits below every possible delivery; either silently disables the
    gate while looking configured. Zero stays legal as the documented
    measure-without-blocking setting.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    # Delivered at 95 percent, i.e. a fill that CLEARS the real floor. With the
    # 40-percent fixture the `inf` case was vacuous: `0.4 < inf` is True, so it
    # exited 1 whether or not the guard existed. A passing fill makes each
    # parameter fail only because the floor was refused as a usage error.
    filled_path = _write(tmp_path, "filled.json", _filled_at(95))
    assert (
        check_fill_integrity.main(
            [skeleton_path, filled_path, "--min-fill-rate", floor]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "FAIL inputs: --min-fill-rate" in captured.err, (
        f"a {floor} floor must be refused at the argument boundary with an "
        "explanatory error, not silently accepted"
    )
    assert "fill-rate: delivered" not in captured.out, (
        "the run must be refused BEFORE measuring; a fill-rate line means the "
        "guard ran too late to protect the gate"
    )


def test_fill_rate_joins_id_less_nodes_positionally(tmp_path: Path) -> None:
    """An id-less directive node still gets credit for its delivered prose.

    The commissioned side keys an id-less node ``#index``; if the delivered
    side keyed it ``"?"`` (as ``_word_stats`` does for display), the join
    would miss it, undercount delivery, and fail a fill that delivered in
    full. The structural check pins node order, which is what makes the
    positional key comparable.
    """
    skeleton = _commissioned_skeleton()
    del skeleton["nodes"][1]["id"]
    filled = _filled_at(95)
    del filled["nodes"][1]["id"]
    skeleton_path = _write(tmp_path, "skeleton.json", skeleton)
    filled_path = _write(tmp_path, "filled.json", filled)
    # Structure check compares stripped copies, so the matching id deletion on
    # both sides keeps this a fill-rate-only scenario; only the check's own
    # blocking outcome is asserted.
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 0


def test_a_directive_less_skeleton_reports_nothing_to_measure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No ``words=`` targets commissions nothing, which is not a failure.

    Older skeletons predate the per-node targets, so an absent commission is
    legitimate and the check says so rather than inventing a zero rate.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    filled_path = _write(tmp_path, "filled.json", _filled())
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 0
    assert "no words= directives" in capsys.readouterr().out


def test_an_unscannable_skeleton_fails_rather_than_passing_vacuously(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A skeleton exposing no node objects must not report success.

    ``commissioned_words_by_node`` degrades to ``{}`` for a malformed node
    collection because ``expected_output_tokens`` wants a relaxed estimate
    rather than an exception. A blocking gate wants the opposite: left as a
    note, every check above reports ``ok`` having compared nothing, which is
    the vacuous-success shape ``AL-294`` ruled a defect in
    ``check_reading_level``.
    """
    skeleton = copy.deepcopy(_commissioned_skeleton())
    filled = copy.deepcopy(_filled_at(95))
    # A dict rather than a list: identical on both sides, so the structural
    # comparison still passes and only the fill-rate gate can catch it. The
    # title must itself be a FILL directive so ``_defers_titles`` short-
    # circuits on it; otherwise that helper iterates the node collection
    # expecting dicts and raises before this gate is reached.
    skeleton["title"] = "<<FILL title>>"
    skeleton["nodes"] = {"n0": skeleton["nodes"][0]}
    filled["nodes"] = {"n0": filled["nodes"][0]}
    skeleton_path = _write(tmp_path, "skeleton.json", skeleton)
    filled_path = _write(tmp_path, "filled.json", filled)
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 1
    assert "exposes no node objects to scan" in capsys.readouterr().err, (
        "a skeleton the scan cannot read must fail; reporting ok on a "
        "comparison that examined nothing manufactures confidence"
    )


def test_surplus_on_one_node_cannot_pay_for_an_empty_node(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Over-delivery must not buy the right to omit another node's prose.

    Both nodes are commissioned at 100 words. The first delivers 200 and the
    second delivers nothing, so a raw sum reaches 200 of 200 and reports a
    perfect fill on a book that is half blank. ``Node.body`` carries no
    ``min_length`` and the band profile sets no per-node minimum by design,
    so nothing else in the battery catches it either.
    """
    skeleton = _commissioned_skeleton()
    filled = _filled_at(0)
    filled["nodes"][0]["body"] = " ".join(f"word{i}" for i in range(200))
    filled["nodes"][1]["body"] = ""
    skeleton_path = _write(tmp_path, "skeleton.json", skeleton)
    filled_path = _write(tmp_path, "filled.json", filled)
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 1
    err = capsys.readouterr().err
    assert "50.0% once per-node surplus is discounted" in err, (
        "the blocking ratio must be monotone in per-node delivery: a node "
        f"credited beyond its commission masks an empty sibling. Got: {err!r}"
    )


def test_a_dropped_node_body_counts_as_zero_delivery(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A filled node with no ``body`` key at all delivers nothing.

    The structural check strips ``body`` from both sides, so a wholly absent
    body survives it; the fill-rate ratio is what registers the loss.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    filled = _filled_at(95)
    del filled["nodes"][1]["body"]
    filled_path = _write(tmp_path, "filled.json", filled)
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 1
    assert (
        "delivered 95 of 200 commissioned words (47.5%)" in capsys.readouterr().err
    ), "a dropped body must count as zero delivered words, not be skipped"


def test_a_fill_rate_floor_above_one_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--min-fill-rate 60`` is the percent typo, and fails every book.

    It clears the finiteness guard and then rejects even a fill that
    delivered in full, which reads as a vendor finding rather than the usage
    error it is.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    filled_path = _write(tmp_path, "filled.json", _filled_at(100))
    assert (
        check_fill_integrity.main([skeleton_path, filled_path, "--min-fill-rate", "60"])
        == 1
    )
    assert "is a ratio, not a percentage" in capsys.readouterr().err, (
        "a floor above 1.0 must be named as the percent mistake it almost "
        "always is, not reported as a whole slate under-delivering"
    )


def test_check_fill_integrity_rejects_a_skeleton_with_no_markers(
    tmp_path: Path,
) -> None:
    """A ``skeleton`` argument with no ``<<FILL`` directive is not a skeleton.

    Comparing two already-filled stories cannot detect a failed fill, so the
    checker must refuse this input rather than run the structural comparison
    against a skeleton that carries no markers to check.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _filled())
    filled_path = _write(tmp_path, "filled.json", _filled())
    exit_code = check_fill_integrity.main([skeleton_path, filled_path])
    assert exit_code == 1


def _twinned_id_skeleton() -> dict[str, Any]:
    """Return a commissioned skeleton whose two ending nodes share one id.

    Both twins are commissioned at 100 words, so the id-keyed join collapses
    them into a single ``"n2"`` key worth 200 commissioned words.
    """
    skeleton = copy.deepcopy(_commissioned_skeleton())
    skeleton["nodes"].append(copy.deepcopy(skeleton["nodes"][1]))
    return skeleton


def _twinned_id_fill() -> dict[str, Any]:
    """Return a fill that pays one twin double and leaves the other empty."""
    filled = copy.deepcopy(_twinned_id_skeleton())
    filled["nodes"][0]["body"] = " ".join(f"word{i}" for i in range(100))
    filled["nodes"][0]["choices"][0]["label"] = "Go toward the light."
    filled["nodes"][1]["body"] = " ".join(f"word{i}" for i in range(200))
    filled["nodes"][2]["body"] = ""
    return filled


def test_duplicate_node_ids_in_the_skeleton_refuse_to_score(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A skeleton that reuses a node id is refused, not scored.

    Every measure here joins the two files by node id, and
    ``commissioned_words_by_node`` accumulates duplicate keys by contract, so
    two nodes sharing an id become one key carrying the sum of both sides.
    That collapses the per-node cap the fill rate depends on. The production
    path never sees this shape (``Storybook._check_unique_ids`` rejects it and
    ``run_gate`` model-validates first), but this checker reads raw JSON with
    no model validation, so the duplicate reaches it unfiltered.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _twinned_id_skeleton())
    filled_path = _write(tmp_path, "filled.json", _twinned_id_fill())

    assert check_fill_integrity.main([skeleton_path, filled_path]) == 1

    captured = capsys.readouterr()
    assert "reuses node id(s) ['n2']" in captured.err
    assert "fill-rate: delivered" not in captured.out, (
        "the run must be refused BEFORE measuring; a fill-rate line means an "
        "ambiguous document was scored anyway"
    )


def test_duplicate_node_ids_in_the_filled_story_refuse_to_score(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A filled story that reuses a node id is refused by name.

    The structural comparison would also reject this pairing, since ids are
    compared, but it would report a generic structural diff. Refusing up front
    names the actual defect and keeps the join unambiguous either way.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    filled = _filled_at(95)
    filled["nodes"][0]["id"] = "n2"
    filled_path = _write(tmp_path, "filled.json", filled)

    assert check_fill_integrity.main([skeleton_path, filled_path]) == 1
    assert "the filled reuses node id(s) ['n2']" in capsys.readouterr().err


def test_the_duplicate_id_refusal_is_what_stops_the_fill_rate_laundering(
    tmp_path: Path,
) -> None:
    """Pin the mechanism, not just the message: the score WOULD have been clean.

    CodeRabbit's PR #731 finding. Run the id-keyed join by hand over the same
    twinned document the refusal blocks: the empty twin's shortfall is paid for
    by its double-length sibling under a shared key, the per-node cap never
    bites, and the capped ratio reaches a perfect 1.0 on a book with a blank
    node. Without the refusal a fill that left a node empty clears the floor.
    """
    skeleton = _twinned_id_skeleton()
    filled = _twinned_id_fill()

    commissioned = check_fill_integrity.commissioned_words_by_node(skeleton)
    delivered = check_fill_integrity._delivered_words_by_node(filled)  # pyright: ignore[reportPrivateUsage]
    capped = sum(
        min(delivered.get(nid, 0), words) for nid, words in commissioned.items()
    )
    total = sum(commissioned.values())

    assert commissioned == {"n1": 100, "n2": 200}, (
        "the twins must collapse into one key for this to be the laundering "
        f"CodeRabbit found; got {commissioned}"
    )
    assert filled["nodes"][2]["body"] == "", "one twin must be empty"
    assert capped / total == 1.0, (
        "the un-refused metric scores a book with a blank node at 100 percent, "
        "which is why an ambiguous document must not be scored at all"
    )

    skeleton_path = _write(tmp_path, "skeleton.json", skeleton)
    filled_path = _write(tmp_path, "filled.json", filled)
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 1


def test_id_less_nodes_are_never_read_as_duplicates(tmp_path: Path) -> None:
    """Two nodes with no ``id`` at all are distinct, not a repeated id.

    The commissioned side keys them ``#index``, which cannot collide. Treating
    a shared absence as a duplicate would refuse the legitimate id-less
    skeleton ``test_fill_rate_joins_id_less_nodes_positionally`` covers.
    """
    skeleton = _commissioned_skeleton()
    filled = _filled_at(95)
    for document in (skeleton, filled):
        del document["nodes"][0]["id"]
        del document["nodes"][1]["id"]
    skeleton_path = _write(tmp_path, "skeleton.json", skeleton)
    filled_path = _write(tmp_path, "filled.json", filled)

    assert check_fill_integrity.main([skeleton_path, filled_path]) == 0


def test_the_offline_delivery_join_dedupes_ids_the_way_production_does() -> None:
    """The offline helper and ``story_fill_rate`` must agree on a duplicate id.

    The CLI refuses a twinned document before this helper runs, so the dedupe
    inside it is not what stops the laundering; the refusal above is. What it
    buys is parity. This script and
    ``cyo_adventure.generation.skeleton.story_fill_rate`` implement one metric
    twice, and a duplicated id is the single input on which "sum the twins"
    and "credit the first" disagree, so it is the input that would let the
    offline number and the production number drift apart on the same document.
    Production cannot refuse (it must return a ratio, and model validation
    upstream means it never actually meets a duplicate); this checker can, and
    does. Pinning the agreement keeps the unreachable branch honest rather
    than merely unfalsifiable (PR #737 review, I15 as corrected).
    """
    from cyo_adventure.generation.skeleton import story_fill_rate

    skeleton = _twinned_id_skeleton()
    filled = _twinned_id_fill()

    delivered = check_fill_integrity._delivered_words_by_node(filled)  # pyright: ignore[reportPrivateUsage]
    assert delivered == {"n1": 100, "n2": 200}, (
        "the empty second twin must neither add to nor overwrite the first "
        f"twin's key; got {delivered}"
    )

    commissioned = check_fill_integrity.commissioned_words_by_node(skeleton)
    offline = sum(
        min(delivered.get(nid, 0), words) for nid, words in commissioned.items()
    ) / sum(commissioned.values())
    assert story_fill_rate(skeleton, filled) == offline
