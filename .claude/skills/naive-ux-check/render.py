"""Render a naive-ux-check paste block from an explicit field allowlist.

This is the ONLY place that composes the block a human pastes into the
Claude-for-Chrome extension. SKILL.md step 4 runs this module instead of
describing the composition in prose, and the D2b automated persona runner
(planned) is expected to import `render_paste_block` directly rather than
writing a third composer, so this module, `scenarios.json`, and SKILL.md's
schema description are the only things that need to change together.

The safety property this exists to enforce: operator-only content
(`operator_notes`: operator setup lines, operator notes, persona context,
and expected observations) must never reach the block handed to the model,
because it tells the model what it is supposed to find.

The mechanism is `_model_facing_view`: `render_paste_block` never touches a
scenario record directly. It reads a restricted mapping built by keyed
lookup against `MODEL_FACING_FIELDS`, so the constant is the sole gate
through which scenario data enters the composition. The asymmetry that
buys is deliberate:

* Removing a name from `MODEL_FACING_FIELDS` raises `KeyError` in the
  composer, so the tuple cannot silently narrow.
* Adding a name makes that field *available* and nothing more. It still
  renders nothing until someone also edits the format string, which is a
  second, visible edit in the place a reviewer actually looks. A future
  editor who widens the tuple believing they extended an allowlist gets no
  leak and no effect at all.
* The view is keyed lookup against a fixed tuple, never iteration over the
  record's own keys, so a field added to `scenarios.json` later (a new
  sub-key under `operator_notes`, or an unrelated top-level field) cannot
  enter the returned mapping under any name.

What this does NOT defend against, stated so nobody reads more into it:
operator-style text typed directly into one of the three model-facing
fields reaches the model, as it must, since those fields are model-facing
by design. The operator/model split is a boundary between *fields*, not a
classifier of content.

Reverting `_model_facing_view` to three direct `scenario[...]` reads would
leave behaviour identical, so no test can detect it; that is a code-review
matter, not a test matter. The tests pin the property (nothing outside the
three fields is read or emitted), which is the thing that matters.

Usage::

    python3 .claude/skills/naive-ux-check/render.py <scenario-id> <url>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.json"

# The complete set of scenario fields ever read to build the paste block.
# Allowlist, never denylist: a field not named here never reaches the model.
# Read by `_model_facing_view` below, which is the only thing that touches a
# scenario record, so this constant is a real gate rather than documentation.
MODEL_FACING_FIELDS = ("persona_text", "task_text", "report_back_questions")


def _model_facing_view(scenario: Mapping[str, Any]) -> dict[str, Any]:
    """The only scenario data `render_paste_block` may read.

    Keyed lookup, never iteration over the scenario's own keys: a field in
    `scenarios.json` that is not named in `MODEL_FACING_FIELDS` cannot
    enter the returned mapping under any name.

    Args:
        scenario: one scenario record, as loaded from `scenarios.json`.

    Returns:
        A mapping holding exactly the `MODEL_FACING_FIELDS` keys.

    Raises:
        KeyError: the record is missing a field named in
            `MODEL_FACING_FIELDS`.
    """
    return {field: scenario[field] for field in MODEL_FACING_FIELDS}


def _load_scenarios(scenarios_path: Path) -> list[dict[str, Any]]:
    return json.loads(scenarios_path.read_text(encoding="utf-8"))


def _find_scenario(scenario_id: str, scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    for scenario in scenarios:
        if scenario["id"] == scenario_id:
            return scenario
    known = ", ".join(s["id"] for s in scenarios)
    message = f"no scenario {scenario_id!r} in scenarios.json (have: {known})"
    raise KeyError(message)


def render_paste_block(
    scenario_id: str, url: str, *, scenarios_path: Path = SCENARIOS_PATH
) -> str:
    """Compose the block a human pastes into the Claude-for-Chrome extension.

    Reads the scenario named by `scenario_id` only through
    `_model_facing_view`, so exactly the `MODEL_FACING_FIELDS` keys are
    reachable here: `persona_text`, `task_text`, and
    `report_back_questions`. `<URL>` placeholders in `persona_text` and
    `task_text` are substituted with `url`. Nothing else on the scenario
    record, including `operator_notes` and anything added to the schema
    later, can be read from this function, because the view is built by
    keyed lookup and the record itself is never indexed below.

    Args:
        scenario_id: the scenario's `id` field (e.g. "K0").
        url: the target URL to substitute for the `<URL>` placeholder.
        scenarios_path: override for `scenarios.json`'s location; defaults
            to the file next to this module.

    Returns:
        The paste block, in the "Persona / Task / Report back" shape.

    Raises:
        KeyError: no scenario with that id exists.
    """
    scenarios = _load_scenarios(scenarios_path)
    facing = _model_facing_view(_find_scenario(scenario_id, scenarios))

    persona_text = facing["persona_text"].replace("<URL>", url)
    task_text = facing["task_text"].replace("<URL>", url)
    questions = "\n".join(
        f"{i}. {q}" for i, q in enumerate(facing["report_back_questions"], start=1)
    )
    return (
        f"Persona: {persona_text}\n\nTask: {task_text}\n\nReport back:\n\n{questions}"
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: render.py <scenario-id> <url>", file=sys.stderr)
        return 2
    scenario_id, url = args
    try:
        print(render_paste_block(scenario_id, url))
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
