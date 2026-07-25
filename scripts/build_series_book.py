"""Compile a series book spec into a Storybook skeleton and a filled story.

A book spec (``data/series/<series>/<book>.spec.json``) is a compact authoring
form: one entry per node carrying the node's role, word budget, beats, choice
labels with shorthand conditions and effects, and (for leaves) its ending. This
script expands the shorthand into full Storybook JSON, either as a skeleton
(bodies are ``<<FILL ...>>`` directives) or as a filled story (bodies are the
prose from a sidecar prose file keyed by node id).

Both committed artifacts are compiled from the same spec, so a skeleton and its
filled story cannot drift apart. See
``docs/planning/wyrmreach-series-design.md`` section 6 for the spec format.

Usage:
    uv run python scripts/build_series_book.py <spec.json> --check
    uv run python scripts/build_series_book.py <spec.json> --skeleton <out.json>
    uv run python scripts/build_series_book.py <spec.json> --prose <prose.json>
        --filled <out.json>
    uv run python scripts/build_series_book.py --series <filled.json> ...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import networkx as nx

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.band_profile import (
    breadth_scaled_floors,
    min_complete_floor,
    production_cell_budget,
    words_per_node_profile,
)
from cyo_adventure.validator.series import validate_series

_ObjectMap = dict[str, Any]

_COMPARISON_RE = re.compile(r"^([a-z][a-z0-9_]*)\s*(==|!=|>=|<=|>|<)\s*(-?\d+)$")
_EFFECT_RE = re.compile(r"^([a-z][a-z0-9_]*)(\+|-|=)([A-Za-z0-9_]+)$")
_SATISFYING = frozenset({"success", "completion"})
_TRUTHY = {"true": True, "false": False}


class SpecError(Exception):
    """A book spec (or its prose sidecar) is malformed."""


def parse_condition(text: str) -> _ObjectMap:
    """Expand a shorthand condition into the JSONLogic condition object.

    Grammar: ``name`` (bool held), ``!name`` (bool not held), a comparison such
    as ``vigor>=3``, or several of those joined by ``&`` (and) or ``|`` (or).

    Args:
        text: The shorthand condition string.

    Returns:
        The expanded condition object.

    Raises:
        SpecError: If the shorthand cannot be parsed.
    """
    stripped = text.strip()
    for token, operator in (("&", "and"), ("|", "or")):
        if token in stripped:
            parts = [part for part in stripped.split(token) if part.strip()]
            return {operator: [parse_condition(part) for part in parts]}
    match = _COMPARISON_RE.match(stripped)
    if match is not None:
        name, operator, literal = match.groups()
        return {operator: [{"var": name}, int(literal)]}
    if stripped.startswith("!"):
        return {"==": [{"var": stripped[1:]}, False]}
    if re.fullmatch(r"[a-z][a-z0-9_]*", stripped):
        return {"==": [{"var": stripped}, True]}
    msg = f"cannot parse condition shorthand {text!r}"
    raise SpecError(msg)


def parse_effects(text: str) -> list[_ObjectMap]:
    """Expand a shorthand effect list into Storybook effect objects.

    Grammar: comma-separated items, each ``var+N`` (inc), ``var-N`` (dec),
    ``var=true`` / ``var=false`` (set bool) or ``var=N`` (set int). A trailing
    ``!`` on an item marks it ``once`` (meaningful only for ``on_enter``).

    Args:
        text: The shorthand effect string.

    Returns:
        The expanded list of effect objects.

    Raises:
        SpecError: If any item cannot be parsed.
    """
    effects: list[_ObjectMap] = []
    for raw_item in text.split(","):
        item = raw_item.strip()
        if not item:
            continue
        once = item.endswith("!")
        match = _EFFECT_RE.match(item.removesuffix("!"))
        if match is None:
            msg = f"cannot parse effect shorthand {item!r}"
            raise SpecError(msg)
        name, operator, literal = match.groups()
        effect: _ObjectMap = {"var": name}
        if operator == "=":
            effect["op"] = "set"
            effect["value"] = _TRUTHY.get(literal, literal)
            if isinstance(effect["value"], str):
                effect["value"] = _as_int(literal, item)
        else:
            effect["op"] = "inc" if operator == "+" else "dec"
            effect["value"] = _as_int(literal, item)
        if once:
            effect["once"] = True
        effects.append(effect)
    return effects


def _as_int(literal: str, item: str) -> int:
    """Parse an integer effect operand.

    Args:
        literal: The operand text.
        item: The whole shorthand item, for the error message.

    Returns:
        The parsed integer.

    Raises:
        SpecError: If the operand is not an integer.
    """
    try:
        return int(literal)
    except ValueError as exc:
        msg = f"effect {item!r} needs an integer or true/false operand"
        raise SpecError(msg) from exc


def _expand_choice(node_id: str, index: int, raw: list[Any]) -> _ObjectMap:
    """Expand one shorthand choice row into a Storybook choice object.

    Args:
        node_id: The owning node's id (used to mint the choice id).
        index: The 1-based position of the choice on the node.
        raw: ``[label, target]``, optionally plus a condition shorthand and an
            effect shorthand.

    Returns:
        The expanded choice object.

    Raises:
        SpecError: If the row is not a 2- to 4-item list.
    """
    if not 2 <= len(raw) <= 4:
        msg = f"node '{node_id}' choice {index} must have 2-4 fields, got {len(raw)}"
        raise SpecError(msg)
    choice: _ObjectMap = {
        "id": f"c_{node_id}_{index}",
        "label": str(raw[0]),
        "target": str(raw[1]),
    }
    if len(raw) >= 3 and raw[2]:
        choice["condition"] = parse_condition(str(raw[2]))
    if len(raw) == 4 and raw[3]:
        choice["effects"] = parse_effects(str(raw[3]))
    return choice


def _expand_ending(node_id: str, spec: str) -> _ObjectMap:
    """Expand a ``kind|valence|Title`` ending shorthand.

    Args:
        node_id: The ending node's id (used to mint the ending id).
        spec: The shorthand string.

    Returns:
        The expanded ending object.

    Raises:
        SpecError: If the shorthand does not have three fields.
    """
    parts = [part.strip() for part in spec.split("|")]
    if len(parts) != 3:
        msg = f"node '{node_id}' ending must be 'kind|valence|Title', got {spec!r}"
        raise SpecError(msg)
    kind, valence, title = parts
    return {
        "id": f"end_{node_id}",
        "kind": kind,
        "valence": valence,
        "title": title,
    }


def _expand_node(entry: _ObjectMap, prose: _ObjectMap | None) -> _ObjectMap:
    """Expand one spec entry into a Storybook node.

    Args:
        entry: The spec entry (keys ``i``, ``r``, ``w``, ``b``, ``c``, ``e``,
            ``x``, ``s``).
        prose: The prose map when compiling a filled story, else ``None`` (which
            compiles the ``<<FILL ...>>`` skeleton body).

    Returns:
        The expanded node object.

    Raises:
        SpecError: If the entry lacks an id, or its prose is missing.
    """
    node_id = entry.get("i")
    if not isinstance(node_id, str) or not node_id:
        msg = f"spec entry has no node id: {entry!r}"
        raise SpecError(msg)
    role = str(entry.get("r", "rising"))
    words = int(entry.get("w", 0))
    beats = str(entry.get("b", ""))
    if prose is None:
        body = f"<<FILL role={role} words={words} beats='{beats}'>>"
    else:
        text = prose.get(node_id)
        if not isinstance(text, str) or not text.strip():
            msg = f"no prose for node '{node_id}'"
            raise SpecError(msg)
        body = text.strip()
    node: _ObjectMap = {"id": node_id, "body": body, "is_ending": False}
    if entry.get("x"):
        node["on_enter"] = parse_effects(str(entry["x"]))
    ending = entry.get("e")
    if ending:
        node["is_ending"] = True
        node["choices"] = []
        node["ending"] = _expand_ending(node_id, str(ending))
    else:
        raw_choices = entry.get("c") or []
        node["choices"] = [
            _expand_choice(node_id, index, raw)
            for index, raw in enumerate(raw_choices, start=1)
        ]
    if entry.get("s"):
        node["safety_scope"] = [str(scope) for scope in entry["s"]]
    return node


def _spec_entries(spec: _ObjectMap, base: Path) -> list[_ObjectMap]:
    """Collect a spec's node entries, expanding any ``include`` part files.

    A book is authored act by act: the spec lists its parts in ``include``
    (paths relative to the spec file), each a JSON array of node entries, and
    they are concatenated in order ahead of any inline ``nodes`` list.

    Args:
        spec: The decoded book spec.
        base: The directory the spec lives in, for resolving includes.

    Returns:
        The concatenated node entries.

    Raises:
        SpecError: If the spec has no entries, or a part file is not an array.
    """
    entries: list[_ObjectMap] = []
    for name in spec.get("include") or []:
        path = base / str(name)
        try:
            part = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            msg = f"cannot load part {path}: {exc}"
            raise SpecError(msg) from exc
        if not isinstance(part, list):
            msg = f"part {path} must be a JSON array of node entries"
            raise SpecError(msg)
        entries.extend(part)
    inline = spec.get("nodes")
    if isinstance(inline, list):
        entries.extend(inline)
    if not entries:
        msg = "spec has no node entries (neither 'include' nor 'nodes')"
        raise SpecError(msg)
    return entries


def build_story(
    spec: _ObjectMap,
    prose: _ObjectMap | None = None,
    base: Path | None = None,
) -> _ObjectMap:
    """Compile a book spec into a Storybook document.

    Args:
        spec: The decoded book spec.
        prose: The prose map for a filled story, or ``None`` for a skeleton.
        base: The spec's directory, used to resolve ``include`` part files.

    Returns:
        The Storybook document, with ``metadata.ending_count`` recomputed from
        the graph so L1-7 cannot fail on a stale count.

    Raises:
        SpecError: If the spec has no node entries.
    """
    entries = _spec_entries(spec, base or Path())
    nodes = [_expand_node(entry, prose) for entry in entries]
    metadata = dict(spec.get("metadata") or {})
    metadata["ending_count"] = sum(1 for node in nodes if node["is_ending"])
    return {
        "schema_version": str(spec.get("schema_version", "2.0")),
        "id": str(spec["id"]),
        "version": int(spec.get("version", 1)),
        "title": str(spec["title"]),
        "metadata": metadata,
        "variables": list(spec.get("variables") or []),
        "start_node": str(spec["start_node"]),
        "nodes": nodes,
    }


def _graph(story: _ObjectMap) -> nx.DiGraph[str]:
    """Build the directed choice graph of a compiled story.

    Args:
        story: The compiled Storybook document.

    Returns:
        The choice graph over node ids.
    """
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(node["id"] for node in story["nodes"])
    for node in story["nodes"]:
        for choice in node["choices"]:
            if choice["target"] in graph:
                graph.add_edge(node["id"], choice["target"])
    return graph


def _structure_lines(story: _ObjectMap) -> list[str]:
    """Return the reference/reachability diagnostics for a compiled story.

    Args:
        story: The compiled Storybook document.

    Returns:
        One line per problem found (empty when the graph is sound).
    """
    ids = {node["id"] for node in story["nodes"]}
    lines: list[str] = []
    for node in story["nodes"]:
        lines.extend(
            f"DANGLING {node['id']} -> {choice['target']} ({choice['label']!r})"
            for choice in node["choices"]
            if choice["target"] not in ids
        )
        if not node["is_ending"] and not node["choices"]:
            lines.append(f"NO-CHOICE  {node['id']} is a non-ending node with no exit")
    graph = _graph(story)
    reachable = nx.descendants(graph, story["start_node"]) | {story["start_node"]}
    lines.extend(f"UNREACHED  {node_id}" for node_id in sorted(ids - reachable))
    return lines


def _word_count(body: str) -> int:
    """Return the PL-19 word count for a node body.

    Args:
        body: The node body (a FILL directive or prose).

    Returns:
        The declared ``words=`` budget for a FILL body, else the token count.
    """
    match = re.search(r"words=(\d+)", body)
    if "<<FILL" in body and match is not None:
        return int(match.group(1))
    return len(body.split())


def _budget_lines(story: _ObjectMap) -> list[str]:
    """Return the scale-cell budget diagnostics for a compiled story.

    Args:
        story: The compiled Storybook document.

    Returns:
        Human-readable metric lines (counts against floors, depth, arc, words).
    """
    metadata = story["metadata"]
    band = str(metadata["age_band"])
    style = str(metadata.get("narrative_style", "prose"))
    length = metadata.get("length")
    nodes = story["nodes"]
    total = len(nodes)
    endings = [node for node in nodes if node["is_ending"]]
    decisions = sum(
        1 for node in nodes if not node["is_ending"] and len(node["choices"]) >= 2
    )
    min_endings, min_decisions = breadth_scaled_floors(total, style)
    budget = production_cell_budget(band, str(length), style) if length else None
    counts = [_word_count(node["body"]) for node in nodes]
    profile = words_per_node_profile(band, style)
    lines = [
        f"nodes      {total}"
        + (f" (cell {budget[0]}..{budget[1]})" if budget else " (band budget)"),
        f"endings    {len(endings)} (floor {min_endings})",
        f"decisions  {decisions} (floor {min_decisions})",
        f"words/node mean {sum(counts) / total:.1f}, max {max(counts)}"
        + (
            f" (advisory {profile[1]}..{profile[2]}, max {profile[3]})"
            if profile
            else ""
        ),
    ]
    lines.extend(_path_lines(story, endings, budget, band, style, length))
    return lines


def _path_lines(
    story: _ObjectMap,
    endings: list[_ObjectMap],
    budget: tuple[int, int, int] | None,
    band: str,
    style: str,
    length: object,
) -> list[str]:
    """Return depth and fastest-finish diagnostics.

    Args:
        story: The compiled Storybook document.
        endings: The ending nodes of the story.
        budget: The cell ``(min, max, depth)`` budget, when scale-classified.
        band: The story age band.
        style: The narrative style.
        length: The declared length, or ``None``.

    Returns:
        The depth line, the fastest-satisfying-finish line, and the ending mix.
    """
    graph = _graph(story)
    lines: list[str] = []
    if nx.is_directed_acyclic_graph(graph):
        depth = int(nx.dag_longest_path_length(graph))
        lines.append(f"depth      {depth}" + (f" (max {budget[2]})" if budget else ""))
    else:
        lines.append("depth      undefined (graph has a cycle)")
    satisfying = [
        node["id"] for node in endings if str(node["ending"]["kind"]) in _SATISFYING
    ]
    best: int | None = None
    for target in satisfying:
        if nx.has_path(graph, story["start_node"], target):
            hops = int(nx.shortest_path_length(graph, story["start_node"], target))
            best = hops + 1 if best is None else min(best, hops + 1)
    floor = min_complete_floor(band, str(length), style) if length else None
    lines.append(f"fastest win {best} node(s)" + (f" (floor {floor})" if floor else ""))
    mix: dict[str, int] = {}
    for node in endings:
        kind = str(node["ending"]["kind"])
        mix[kind] = mix.get(kind, 0) + 1
    lines.append("ending mix " + ", ".join(f"{k}={v}" for k, v in sorted(mix.items())))
    return lines


def _load_json(path: Path) -> _ObjectMap:
    """Read a JSON object from disk.

    Args:
        path: The file to read.

    Returns:
        The decoded object.

    Raises:
        SpecError: If the file is unreadable or is not a JSON object.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"cannot load {path}: {exc}"
        raise SpecError(msg) from exc
    if not isinstance(data, dict):
        msg = f"expected a JSON object in {path}"
        raise SpecError(msg)
    return data


def _write_story(story: _ObjectMap, path: Path) -> None:
    """Write a compiled story to disk with a trailing newline.

    Args:
        story: The compiled Storybook document.
        path: The destination file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(story, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {path} ({len(story['nodes'])} nodes)\n")


def _cmd_series(paths: list[str]) -> int:
    """Validate a chain of filled books with the cross-book series validator.

    Args:
        paths: The filled-story paths, one per book.

    Returns:
        1 when the chain has errors, else 0.
    """
    books = [Storybook.model_validate(_load_json(Path(path))) for path in paths]
    report = validate_series(books)
    for finding in report.findings:
        sys.stdout.write(
            f"{finding.severity.upper():7} {finding.rule_id:5} "
            f"{finding.story_id}: {finding.message}\n"
        )
    sys.stdout.write(f"series findings={len(report.findings)} ok={report.ok}\n")
    return 0 if report.ok else 1


def _cmd_build(args: argparse.Namespace) -> int:
    """Compile one book spec and run the requested outputs.

    Args:
        args: The parsed CLI arguments.

    Returns:
        1 when the structural diagnostics found a problem, else 0.
    """
    spec_path = Path(args.spec)
    spec = _load_json(spec_path)
    prose: _ObjectMap | None = None
    if args.prose:
        prose = {}
        for part in args.prose:
            prose.update(_load_json(Path(part)))
    story = build_story(spec, prose, spec_path.parent)
    problems = _structure_lines(story)
    if args.check or problems:
        for line in problems:
            sys.stdout.write(line + "\n")
        for line in _budget_lines(story):
            sys.stdout.write(line + "\n")
    if problems:
        sys.stdout.write(f"structure problems: {len(problems)}\n")
        return 1
    if args.skeleton:
        _write_story(story, Path(args.skeleton))
    if args.filled:
        if prose is None:
            sys.stdout.write("error: --filled requires --prose\n")
            return 1
        _write_story(story, Path(args.filled))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Compile a book spec, or validate a chain of filled books.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", nargs="?", help="Path to the book spec JSON.")
    parser.add_argument(
        "--prose",
        action="append",
        help="Prose sidecar JSON (node id -> prose); repeatable, merged in order.",
    )
    parser.add_argument("--skeleton", help="Write the FILL skeleton here.")
    parser.add_argument("--filled", help="Write the filled story here.")
    parser.add_argument(
        "--check", action="store_true", help="Print structural diagnostics."
    )
    parser.add_argument(
        "--series", nargs="+", help="Validate these filled books as one chain."
    )
    args = parser.parse_args(argv)
    try:
        if args.series:
            return _cmd_series(args.series)
        if not args.spec:
            parser.error("a spec path is required unless --series is used")
        return _cmd_build(args)
    except SpecError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
