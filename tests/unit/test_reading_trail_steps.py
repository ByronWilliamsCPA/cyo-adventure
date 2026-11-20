"""Unit tests for reading-trail step validation, merge, and the API body bounds."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api.schemas import ReadingTrailBatchBody, ReadingTrailStepBody
from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import READING_TRAIL_MAX_STEPS
from cyo_adventure.reading_trail import (
    MAX_ELAPSED_SECONDS,
    MAX_STEPS_PER_BATCH,
    StepKind,
    StoryIndex,
    TrailStep,
    ending_of,
    merge_steps,
    validate_steps,
)

_LANTERN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "03_tier2_lantern.json"
)


@pytest.fixture
def index() -> StoryIndex:
    """Index the lantern fixture (n_open -> n_entrance -> n_cave_fork -> ends)."""
    return StoryIndex.from_blob(json.loads(_LANTERN.read_text(encoding="utf-8")))


def _step(
    seq: int,
    kind: StepKind,
    node: str,
    choice: str | None = None,
    elapsed: int = 0,
) -> TrailStep:
    return TrailStep(
        seq=seq, kind=kind, node_id=node, choice_id=choice, elapsed_s=elapsed
    )


def _finished_read() -> list[TrailStep]:
    return [
        _step(0, StepKind.START, "n_open"),
        _step(1, StepKind.AUTO, "n_open", "c_n_open", 5),
        _step(2, StepKind.CHOICE, "n_entrance", "c_take_lantern", 20),
        _step(3, StepKind.CHOICE, "n_cave_fork", "c_dark_passage", 40),
        _step(4, StepKind.END, "n_treasure", None, 41),
    ]


def test_index_records_choices_targets_and_endings(index: StoryIndex) -> None:
    """The index keeps declared choice order, targets, and ending ids."""
    entrance = index.nodes["n_entrance"]
    assert entrance.choice_ids == (
        "c_take_lantern",
        "c_ignore_lantern",
        "xc_start_extra",
    )
    assert entrance.targets["c_take_lantern"] == "n_cave_fork"
    assert index.nodes["n_treasure"].ending_id == "e_treasure_found"
    assert index.nodes["n_open"].ending_id is None


def test_index_tolerates_malformed_blob() -> None:
    """A malformed blob indexes to nothing rather than raising."""
    assert StoryIndex.from_blob({"nodes": "nope"}).nodes == {}
    malformed = StoryIndex.from_blob(
        {"nodes": [1, {"id": 2}, {"id": "a", "choices": [3, {"id": "c"}]}]}
    )
    assert malformed.nodes["a"].choice_ids == ()


def test_validate_accepts_a_full_read(index: StoryIndex) -> None:
    """A well-formed read validates."""
    validate_steps(index, _finished_read())


def test_validate_accepts_resume_back_jump_restart_leave(index: StoryIndex) -> None:
    """Every non-choice kind validates on a known node."""
    validate_steps(
        index,
        [
            _step(0, StepKind.RESUME, "n_cave_fork"),
            _step(1, StepKind.BACK, "n_entrance", None, 3),
            _step(2, StepKind.JUMP, "n_cave_fork", None, 4),
            _step(3, StepKind.RESTART, "n_cave_fork", None, 9),
        ],
    )
    validate_steps(index, [_step(7, StepKind.LEAVE, "n_exit", None, 99)])


@pytest.mark.parametrize(
    ("step", "reason"),
    [
        (_step(1, StepKind.BACK, "n_nowhere"), "node"),
        (_step(1, StepKind.CHOICE, "n_entrance", "c_dark_passage"), "choice"),
        (_step(1, StepKind.CHOICE, "n_entrance", None), "choice"),
        (_step(1, StepKind.AUTO, "n_entrance", "c_take_lantern"), "exactly one"),
        (_step(1, StepKind.CHOICE, "n_open", "c_n_open"), "two or more"),
        (_step(1, StepKind.BACK, "n_open", "c_n_open"), "choice id"),
        (_step(1, StepKind.END, "n_cave_fork"), "ending node"),
        (_step(1, StepKind.START, "n_open"), "seq 0"),
        (_step(0, StepKind.BACK, "n_open"), "seq 0"),
    ],
)
def test_validate_rejects_inconsistent_steps(
    index: StoryIndex, step: TrailStep, reason: str
) -> None:
    """Each rule rejects, and the message never echoes the submitted id."""
    with pytest.raises(ValidationError) as caught:
        validate_steps(index, [step])
    assert reason in str(caught.value)
    assert step.node_id not in str(caught.value)
    if step.choice_id is not None:
        assert step.choice_id not in str(caught.value)


def test_validate_rejects_duplicate_seq_in_batch(index: StoryIndex) -> None:
    """A batch may not carry the same seq twice."""
    with pytest.raises(ValidationError, match="repeat"):
        validate_steps(
            index,
            [_step(2, StepKind.BACK, "n_open"), _step(2, StepKind.BACK, "n_open")],
        )


def test_merge_is_idempotent_and_first_write_wins(index: StoryIndex) -> None:
    """Replaying a batch adds nothing; a conflicting seq keeps the stored step."""
    first = merge_steps([], _finished_read())
    assert merge_steps(first, _finished_read()) == first
    forged = [_step(2, StepKind.CHOICE, "n_entrance", "c_ignore_lantern", 20)]
    assert merge_steps(first, forged) == first
    assert ending_of(index, first) == "e_treasure_found"


def test_merge_orders_by_seq_and_unions_overlap() -> None:
    """Out-of-order, overlapping batches merge into one ordered list."""
    read = _finished_read()
    merged = merge_steps(merge_steps([], read[3:]), read[:4])
    assert [step["seq"] for step in merged] == [0, 1, 2, 3, 4]
    assert set(merged[0]) == {"seq", "kind", "node_id", "choice_id", "elapsed_s"}


def test_merge_refuses_to_exceed_the_step_cap() -> None:
    """The merge never grows a read past READING_TRAIL_MAX_STEPS."""
    stored = [
        {
            "seq": seq,
            "kind": "back",
            "node_id": "n_open",
            "choice_id": None,
            "elapsed_s": 0,
        }
        for seq in range(READING_TRAIL_MAX_STEPS)
    ]
    with pytest.raises(ValidationError, match="at most"):
        merge_steps(stored, [_step(READING_TRAIL_MAX_STEPS, StepKind.BACK, "n_open")])


def test_ending_of_takes_the_last_ending_and_handles_none(index: StoryIndex) -> None:
    """A read that reached two endings records the later one; none is None."""
    steps = merge_steps(
        [],
        [
            _step(0, StepKind.START, "n_open"),
            _step(1, StepKind.END, "n_treasure"),
            _step(2, StepKind.BACK, "n_cave_fork"),
            _step(3, StepKind.END, "n_exit"),
        ],
    )
    assert ending_of(index, steps) == "e_safe_exit"
    assert ending_of(index, steps[:1]) is None


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "read_id": str(uuid.uuid4()),
        "version": 1,
        "steps": [{"seq": 0, "kind": "start", "node_id": "n_open", "elapsed_s": 0}],
    }
    body.update(overrides)
    return body


def test_batch_body_accepts_a_minimal_batch() -> None:
    """The smallest valid batch parses."""
    parsed = ReadingTrailBatchBody.model_validate(_body())
    assert parsed.steps[0].kind is StepKind.START


@pytest.mark.parametrize(
    "overrides",
    [
        {"steps": []},
        {
            "steps": [
                {"seq": seq, "kind": "back", "node_id": "n", "elapsed_s": 0}
                for seq in range(MAX_STEPS_PER_BATCH + 1)
            ]
        },
        {"version": 0},
        {"read_id": "not-a-uuid"},
        {"extra": True},
    ],
)
def test_batch_body_bounds(overrides: dict[str, object]) -> None:
    """Empty, oversized, extra-field, and malformed batches are refused."""
    with pytest.raises(PydanticValidationError):
        ReadingTrailBatchBody.model_validate(_body(**overrides))


@pytest.mark.parametrize(
    "step",
    [
        {"seq": -1, "kind": "start", "node_id": "n", "elapsed_s": 0},
        {
            "seq": READING_TRAIL_MAX_STEPS,
            "kind": "back",
            "node_id": "n",
            "elapsed_s": 0,
        },
        {"seq": 1, "kind": "teleport", "node_id": "n", "elapsed_s": 0},
        {"seq": 1, "kind": "back", "node_id": "has space", "elapsed_s": 0},
        {"seq": 1, "kind": "back", "node_id": "x" * 121, "elapsed_s": 0},
        {"seq": 1, "kind": "back", "node_id": "", "elapsed_s": 0},
        {"seq": 1, "kind": "back", "node_id": "n", "elapsed_s": -1},
        {
            "seq": 1,
            "kind": "back",
            "node_id": "n",
            "elapsed_s": MAX_ELAPSED_SECONDS + 1,
        },
        {"seq": 1, "kind": "back", "node_id": "n", "elapsed_s": 0, "at": "12:00"},
    ],
)
def test_step_body_bounds(step: dict[str, object]) -> None:
    """Out-of-range, free-text-shaped, and extra-field steps are refused."""
    with pytest.raises(PydanticValidationError):
        ReadingTrailStepBody.model_validate(step)


def test_reading_trail_capture_is_off_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The kill switch defaults off; an empty override also reads as off."""
    monkeypatch.delenv("READING_TRAIL_ENABLED", raising=False)
    assert Settings().reading_trail_enabled is False
    monkeypatch.setenv("READING_TRAIL_ENABLED", "")
    assert Settings().reading_trail_enabled is False
    monkeypatch.setenv("READING_TRAIL_ENABLED", "true")
    assert Settings().reading_trail_enabled is True
