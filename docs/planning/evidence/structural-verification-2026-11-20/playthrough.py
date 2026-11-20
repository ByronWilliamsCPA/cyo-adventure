"""Play every plant-to-payoff pair of a filled stateful book, in both states.

For each declared boolean, this finds (with ``StoryEngine``, so conditions and
effects are evaluated exactly as a reader's device would) the shortest route
that takes the planting choice and reaches each payoff site, and the shortest
route that reaches the same site WITHOUT the plant. It writes, per pair, the
prose a reader sees: the plant choice and the scene it leads to, the payoff
site, the payoff scene only the planted reader gets, and what the unplanted
reader gets instead. The verdict ("would a child see the connection?") is made
by hand from this output; nothing here scores it.

Usage::

    uv run python docs/planning/evidence/structural-verification-2026-11-20/playthrough.py \
        <filled.json> --out <playthrough.md>
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Any

from cyo_adventure.player.engine import StoryEngine
from cyo_adventure.player.state import ReadingState
from cyo_adventure.storybook.models import Storybook


def _key(state: ReadingState) -> tuple[str, tuple[tuple[str, object], ...]]:
    return state.current_node, tuple(sorted(state.var_state.items()))


def _search(
    engine: StoryEngine,
    start: ReadingState,
    goal_node: str,
    var: str,
    want: bool,
) -> ReadingState | None:
    """Breadth-first: fewest choices to reach ``goal_node`` with ``var == want``."""
    seen = {_key(start)}
    queue: deque[ReadingState] = deque([start])
    while queue:
        state = queue.popleft()
        if state.current_node == goal_node and bool(state.var_state.get(var)) is want:
            return state
        if engine.is_ending(state):
            continue
        for choice in engine.visible_choices(state):
            nxt = engine.choose(state, choice.id)
            key = _key(nxt)
            if key not in seen:
                seen.add(key)
                queue.append(nxt)
    return None


def _cond_var(cond: object) -> tuple[str, bool] | None:
    if isinstance(cond, dict) and "==" in cond:
        left, right = cond["=="]
        if isinstance(left, dict) and "var" in left and isinstance(right, bool):
            return str(left["var"]), right
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filled", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    doc: dict[str, Any] = json.loads(args.filled.read_text("utf-8"))
    story = Storybook.model_validate(doc)
    engine = StoryEngine(story)
    nodes = {n["id"]: n for n in doc["nodes"]}
    lines: list[str] = [f"# Plant-to-payoff playthrough: {doc.get('title')}", ""]

    plants: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for node in doc["nodes"]:
        for ch in node.get("choices") or []:
            for eff in ch.get("effects") or []:
                if eff.get("op") == "set" and eff.get("value") is True:
                    plants.setdefault(eff["var"], []).append((node["id"], ch))

    for var in [v["name"] for v in doc.get("variables") or []]:
        lines += [f"## `{var}`", ""]
        for site_id, ch in plants.get(var, []):
            target = nodes[ch["target"]]
            lines += [
                f"**Plant** at `{site_id}`: choice \"{ch['label']}\" leads to "
                f"`{target['id']}`:",
                "",
                f"> {target['body']}",
                "",
            ]
        for node in doc["nodes"]:
            for ch in node.get("choices") or []:
                cv = _cond_var(ch.get("condition"))
                if cv != (var, True):
                    continue
                site = node["id"]
                lines += [f"### Payoff site `{site}`, choice \"{ch['label']}\"", ""]
                lines += [f"Site body (both readers):", "", f"> {node['body']}", ""]
                with_state = _search(engine, engine.start(), site, var, True)
                without = _search(engine, engine.start(), site, var, False)
                payoff = nodes[ch["target"]]
                lines += [
                    f"Planted reader (route of {len(with_state.path) if with_state else 'NONE'}"
                    f" nodes: {' > '.join(with_state.path) if with_state else 'unreachable'})"
                    f" sees `{payoff['id']}`:",
                    "",
                    f"> {payoff['body']}",
                    "",
                ]
                twin = [
                    c
                    for c in node.get("choices") or []
                    if _cond_var(c.get("condition")) == (var, False)
                    and c["label"] == ch["label"]
                ]
                if twin:
                    alt = nodes[twin[0]["target"]]
                    lines += [
                        f"Unplanted reader (route: {' > '.join(without.path) if without else 'unreachable'})"
                        f" gets `{alt['id']}` instead:",
                        "",
                        f"> {alt['body'][:700]}",
                        "",
                    ]
                else:
                    lines += [
                        "Unplanted reader: the button is absent "
                        f"(route: {' > '.join(without.path) if without else 'unreachable'}).",
                        "",
                    ]
    args.out.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
