"""The variation axes and the fill differentiation directive (A6, A7).

Before A6, ``DifferentiationLevel`` reached a warning string, a log line, and the
flywheel trigger, and then stopped. The fill that could have acted on it never
saw it, so escalating from ``tree`` to ``leaf`` to ``catalog`` changed nothing
about the prose. These tests pin the two properties that make the signal real:
it reaches the prompt, and what reaches the prompt carries no other child's
words.
"""

from __future__ import annotations

from cyo_adventure.generation.prompts import (
    build_differentiation_directive,
    build_fill_prompt,
)
from cyo_adventure.generation.variation import (
    VARIATION_AXES,
    axis_for_key,
    select_axis,
)

# ---------------------------------------------------------------------------
# A7: the variation-axis library
# ---------------------------------------------------------------------------


def test_axis_keys_are_unique() -> None:
    """A duplicate key would make persisted axes ambiguous on read-back."""
    keys = [axis.key for axis in VARIATION_AXES]
    assert len(keys) == len(set(keys))


def test_axis_instructions_are_positive_directions() -> None:
    """An axis tells a writer what to do, not what to avoid.

    A prohibition leaves the model without an alternative, which is how a
    "don't be repetitive" instruction produces bland prose rather than varied
    prose.
    """
    for axis in VARIATION_AXES:
        assert axis.instruction
        assert not axis.instruction.lower().startswith(("do not", "don't", "never"))


def test_selection_is_stable_across_calls() -> None:
    """Determinism is the point: a re-run must reproduce the same direction.

    Uses blake2b rather than ``hash()`` because Python salts string hashes per
    process, which would silently pick a different axis after any worker restart
    and confound every before-and-after comparison of an axis's effect.
    """
    first = select_axis("request-abc")
    for _ in range(5):
        assert select_axis("request-abc") == first


def test_different_seeds_reach_different_axes() -> None:
    """A selector that collapses to one axis would deliver no variation."""
    chosen = {select_axis(f"request-{index}").key for index in range(60)}
    assert len(chosen) > 1


def test_exclusion_avoids_recent_axes() -> None:
    """A family should not get the same craft direction twice running."""
    first = select_axis("request-abc")
    second = select_axis("request-abc", exclude=[first.key])
    assert second.key != first.key


def test_exhausting_the_library_still_returns_an_axis() -> None:
    """Repeating an axis is a smaller problem than refusing to generate."""
    every_key = [axis.key for axis in VARIATION_AXES]
    assert select_axis("request-abc", exclude=every_key) in VARIATION_AXES


def test_axis_for_key_returns_none_for_an_unknown_key() -> None:
    """A library entry removed after a job was queued must not fail the job."""
    assert axis_for_key("no_such_axis") is None
    assert axis_for_key(VARIATION_AXES[0].key) == VARIATION_AXES[0]


# ---------------------------------------------------------------------------
# A6: the differentiation directive
# ---------------------------------------------------------------------------


def test_each_level_produces_distinguishable_guidance() -> None:
    """The whole point: the three levels must not read the same.

    If they did, threading the level through would be ceremony.
    """
    rendered = {
        level: build_differentiation_directive(level=level, axis_instruction=None)
        for level in ("tree", "leaf", "catalog")
    }
    assert len(set(rendered.values())) == 3
    assert "no extra differentiation pressure" in rendered["tree"]
    assert "every skeleton in this cell" in rendered["leaf"]
    assert "more than once already" in rendered["catalog"]


def test_missing_level_says_so_rather_than_implying_novelty() -> None:
    """An absent signal must not be rendered as "this is new to the family".

    The override path computes no similarity context, and silently claiming
    novelty there would be a false statement to the model.
    """
    directive = build_differentiation_directive(level=None, axis_instruction=None)
    assert "No similarity context was available" in directive
    assert "new to this family" not in directive


def test_the_axis_instruction_reaches_the_directive() -> None:
    """A7 is only real if the drawn axis lands in the prompt."""
    axis = VARIATION_AXES[0]
    directive = build_differentiation_directive(
        level="tree", axis_instruction=axis.instruction
    )
    assert axis.instruction in directive


def test_prior_titles_appear_but_nothing_else_about_them() -> None:
    """A6's privacy fence, stated as a test.

    Titles are published content the family already holds. A prior story's
    premise is another child's request text, and routing it here would make one
    child's phrasing an input to another child's story. The builder has no
    parameter for it, so this asserts the shape of what CAN be passed.
    """
    directive = build_differentiation_directive(
        level="leaf",
        axis_instruction=None,
        prior_titles=["The Cave of Echoes", "The Salt Archive"],
        prior_theme_tags=["courage", "forest"],
    )
    assert "'The Cave of Echoes'" in directive
    assert "'The Salt Archive'" in directive
    assert "courage, forest" in directive
    assert "what to differ" in directive


def test_no_priors_omits_the_priors_paragraph() -> None:
    """A first story for a family should not be told about stories that do not exist."""
    directive = build_differentiation_directive(level="tree", axis_instruction=None)
    assert "already owns" not in directive
    assert "Themes already covered" not in directive


def test_the_directive_reaches_the_rendered_fill_prompt() -> None:
    """End to end: the template must actually carry it.

    This is the assertion that would have failed before A6, since the signal
    stopped at a warning string.
    """
    marker = "UNIQUE-DIFFERENTIATION-MARKER-9137"
    prompt = build_fill_prompt("{}", "{}", marker)
    combined = f"{prompt.system}\n{prompt.user}"
    assert marker in combined


def test_the_fill_prompt_never_ships_an_unfilled_directive_token() -> None:
    """A caller that omits the directive must still get a complete prompt."""
    prompt = build_fill_prompt("{}", "{}")
    combined = f"{prompt.system}\n{prompt.user}"
    assert "{differentiation_directive}" not in combined
    assert "No similarity context was available" in combined


def test_the_directive_is_marked_trusted_not_user_input() -> None:
    """It must sit outside the untrusted-input fence.

    The directive is pipeline-generated instruction. Rendering it inside the
    UNTRUSTED_USER_INPUT markers would tell the model to ignore it.
    """
    marker = "UNIQUE-DIFFERENTIATION-MARKER-9137"
    prompt = build_fill_prompt("{}", "{}", marker)
    untrusted_start = prompt.user.index("<<<UNTRUSTED_USER_INPUT")
    untrusted_end = prompt.user.index(">>>END_UNTRUSTED_USER_INPUT")
    position = prompt.user.index(marker)
    assert not untrusted_start < position < untrusted_end
