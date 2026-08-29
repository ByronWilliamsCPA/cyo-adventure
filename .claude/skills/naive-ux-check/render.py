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
because it tells the model what it is supposed to find. `render_paste_block`
reads exactly three fields off a scenario record, named explicitly in
`MODEL_FACING_FIELDS` below. This is an allowlist, not a denylist of
`operator_notes`: a field added to the schema later (including a new
sub-key under `operator_notes`, or an unrelated top-level field) is
excluded by construction, because nothing here ever iterates the
scenario's other keys.

Usage::

    python3 .claude/skills/naive-ux-check/render.py <scenario-id> <url>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.json"

# The complete set of scenario fields ever read to build the paste block.
# Allowlist, never denylist: a field not named here never reaches the model.
MODEL_FACING_FIELDS = ("persona_text", "task_text", "report_back_questions")


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

    Reads only `MODEL_FACING_FIELDS` off the scenario named by
    `scenario_id`: `persona_text`, `task_text`, and
    `report_back_questions`. `<URL>` placeholders in `persona_text` and
    `task_text` are substituted with `url`. Nothing else on the scenario
    record, including `operator_notes` and anything added to the schema
    later, is ever read.

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
    scenario = _find_scenario(scenario_id, scenarios)

    persona_text = scenario["persona_text"].replace("<URL>", url)
    task_text = scenario["task_text"].replace("<URL>", url)
    questions = "\n".join(
        f"{i}. {q}" for i, q in enumerate(scenario["report_back_questions"], start=1)
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
