"""Apply an agent-authored slotting plan to a pristine skeleton.

Usage::

    uv run python scripts/parameterize_skeleton.py <skeleton.json> <plan.json> \\
        --out <path>

Generalizes ``out/pilot/_neutralize.py``, which was a bespoke, hardcoded
transform for one skeleton. The plan JSON carries exactly three maps::

    {
      "beats": {node_id: slotted_beats},
      "titles": {node_id: title_template},
      "labels": {node_id: {choice_id: label_template}}
    }

Applied to a deep copy of the skeleton, then enforced (fail with a clear
message and a non-zero exit on any violation; nothing is written to ``--out``
unless every check passes):

1. Every node whose body is a ``<<FILL ...>>`` directive has a ``beats``
   mapping, and every ``beats`` key maps to an existing FILL node (no
   missing, no unused). Same for endings vs. ``titles``.
2. Every ``labels`` entry references an existing ``(node_id, choice_id)``
   pair (labels are not exhaustively required, since only theme-specific
   labels are slotted per the migration recipe, design section 8.1 step 3;
   this check only rejects a *dangling* reference).
3. ``role=``/``words=`` are byte-preserved on every FILL body: parsed from
   both the original and the parameterized document, then compared.
4. ``structure_fingerprint(parameterized) == structure_fingerprint(original)``.
5. ``run_gate(parameterized).blocked is False``.
6. Every ``{...}`` token introduced anywhere in beats/titles/labels matches
   the slot token grammar (``SLOT_TOKEN_RE``); a malformed token (lowercase,
   leading digit, stray brace) is rejected.

See ``docs/planning/ws2-parameterized-catalog-design.md`` sections 8.1 (step
4) and 8.4 for the design this script implements.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import cast

from cyo_adventure.diversity.structure import structure_fingerprint
from cyo_adventure.storybook.theme_contract import SLOT_TOKEN_RE
from cyo_adventure.validator.gate import run_gate

# The production FILL directive parse, reused verbatim from the pilot
# (`out/pilot/_neutralize.py:337`) and from `generation/binding.py`.
_FILL_RE = re.compile(r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$", re.DOTALL)

# Any brace-delimited group anywhere in a slotted surface; used to find
# malformed tokens (a `{...}` group that does not match SLOT_TOKEN_RE's
# `{[A-Z][A-Z0-9_]*}` grammar).
_BRACE_GROUP_RE = re.compile(r"\{[^{}]*\}")
_SLOT_ID_ONLY_RE = re.compile(r"[A-Z][A-Z0-9_]*")


class PlanError(ValueError):
    """Raised when a slotting plan is malformed (not a checked invariant)."""


def _load_json_object(path: Path) -> dict[str, object]:
    """Load and return a JSON object from ``path``.

    Args:
        path: File path to read.

    Returns:
        The decoded top-level JSON object.

    Raises:
        OSError: If the file cannot be read.
        json.JSONDecodeError: If the file is not valid JSON.
        PlanError: If the top-level JSON value is not an object.
    """
    data: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    if not isinstance(data, dict):
        msg = f"expected a JSON object in {path}"
        raise PlanError(msg)
    return cast("dict[str, object]", data)


def _as_str_map(value: object, field: str) -> dict[str, str]:
    """Validate and return ``value`` as a flat ``{str: str}`` map.

    Args:
        value: The candidate value (from a decoded JSON object).
        field: The plan field name, for the error message.

    Returns:
        The validated ``dict[str, str]``.

    Raises:
        PlanError: If ``value`` is not a JSON object of string to string.
    """
    if not isinstance(value, dict):
        msg = f"plan '{field}' must be a JSON object mapping id to string"
        raise PlanError(msg)
    raw_map = cast("dict[object, object]", value)
    result: dict[str, str] = {}
    for key, val in raw_map.items():
        if not isinstance(key, str) or not isinstance(val, str):
            msg = f"plan '{field}' must map string ids to string values"
            raise PlanError(msg)
        result[key] = val
    return result


def _as_nested_str_map(value: object, field: str) -> dict[str, dict[str, str]]:
    """Validate and return ``value`` as a ``{str: {str: str}}`` map.

    Args:
        value: The candidate value (from a decoded JSON object).
        field: The plan field name, for the error message.

    Returns:
        The validated ``dict[str, dict[str, str]]``.

    Raises:
        PlanError: If ``value`` is not a JSON object of that shape.
    """
    if not isinstance(value, dict):
        msg = f"plan '{field}' must be a JSON object mapping node id to a choice map"
        raise PlanError(msg)
    raw_map = cast("dict[object, object]", value)
    result: dict[str, dict[str, str]] = {}
    for key, inner in raw_map.items():
        if not isinstance(key, str):
            msg = f"plan '{field}' must map node id (str) to a choice map"
            raise PlanError(msg)
        result[key] = _as_str_map(inner, f"{field}[{key!r}]")
    return result


def _parse_plan(
    raw: dict[str, object],
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, str]]]:
    """Validate and return the plan's three typed maps.

    Args:
        raw: The decoded plan JSON object.

    Returns:
        The ``(beats, titles, labels)`` maps, shape-checked.

    Raises:
        PlanError: If any of the three maps is missing or malformed.
    """
    beats = _as_str_map(raw.get("beats", {}), "beats")
    titles = _as_str_map(raw.get("titles", {}), "titles")
    labels = _as_nested_str_map(raw.get("labels", {}), "labels")
    return beats, titles, labels


def _iter_nodes(skeleton: dict[str, object]) -> list[dict[str, object]]:
    """Return every node dict in a raw skeleton mapping.

    Args:
        skeleton: The raw skeleton dict.

    Returns:
        Every ``dict`` entry of ``skeleton["nodes"]``; non-dict entries in a
        malformed ``nodes`` list are silently skipped (schema validity is the
        gate's job, not this walker's).
    """
    nodes = skeleton.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [n for n in cast("list[object]", nodes) if isinstance(n, dict)]


def _role_words_map(skeleton: dict[str, object]) -> dict[str, tuple[str, str] | None]:
    """Map every node id to its FILL directive's ``(role, words)``, or ``None``.

    Mirrors ``generation/binding.py::_fill_role_words_map``; comparing this
    map before and after applying a plan is the byte-preservation guard on
    ``role=``/``words=`` (analogous to CR-1's render-time invariant, design
    section 13.2, applied here at authoring time per section 8.1 step 4).

    Args:
        skeleton: The raw skeleton dict to scan.

    Returns:
        A dict from node id to its parsed ``(role, words)`` pair, or ``None``
        when the node's body is not (or is no longer) a FILL directive.
    """
    result: dict[str, tuple[str, str] | None] = {}
    for node in _iter_nodes(skeleton):
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        body = node.get("body")
        match = _FILL_RE.match(body) if isinstance(body, str) else None
        result[node_id] = (
            (match.group(1), match.group(2)) if match is not None else None
        )
    return result


def _apply_beats(
    skeleton: dict[str, object],
    beats_plan: dict[str, str],
    errors: list[str],
) -> set[str]:
    """Rewrite each FILL node's beats text in place; collect any errors.

    Args:
        skeleton: The (already-copied) skeleton to mutate.
        beats_plan: The plan's ``{node_id: new_beats}`` map.
        errors: Accumulator for human-readable failure messages.

    Returns:
        The set of node ids whose beats text was rewritten.
    """
    fill_node_ids: set[str] = set()
    rewritten: set[str] = set()
    for node in _iter_nodes(skeleton):
        node_id = node.get("id")
        body = node.get("body")
        if not (isinstance(body, str) and body.startswith("<<FILL")):
            continue
        if not isinstance(node_id, str):
            errors.append("a FILL node has a non-string or missing id")
            continue
        fill_node_ids.add(node_id)
        match = _FILL_RE.match(body)
        if match is None:
            msg = f"node '{node_id}' body does not match the FILL directive pattern"
            errors.append(msg)
            continue
        if node_id not in beats_plan:
            errors.append(f"no beats mapping for FILL node '{node_id}'")
            continue
        role, words = match.group(1), match.group(2)
        new_beats = beats_plan[node_id]
        node["body"] = f"<<FILL role={role} words={words} beats='{new_beats}'>>"
        rewritten.add(node_id)

    errors.extend(
        f"beats mapping for '{node_id}' does not match any FILL node"
        for node_id in sorted(set(beats_plan) - fill_node_ids)
    )

    return rewritten


def _apply_titles(
    skeleton: dict[str, object],
    titles_plan: dict[str, str],
    errors: list[str],
) -> set[str]:
    """Rewrite each ending node's title in place; collect any errors.

    Args:
        skeleton: The (already-copied) skeleton to mutate.
        titles_plan: The plan's ``{node_id: new_title}`` map.
        errors: Accumulator for human-readable failure messages.

    Returns:
        The set of node ids whose ending title was rewritten.
    """
    ending_node_ids: set[str] = set()
    rewritten: set[str] = set()
    for node in _iter_nodes(skeleton):
        node_id = node.get("id")
        ending = node.get("ending")
        if not isinstance(ending, dict):
            continue
        if not isinstance(node_id, str):
            errors.append("an ending node has a non-string or missing id")
            continue
        ending_node_ids.add(node_id)
        if node_id not in titles_plan:
            errors.append(f"no title mapping for ending node '{node_id}'")
            continue
        cast("dict[str, object]", ending)["title"] = titles_plan[node_id]
        rewritten.add(node_id)

    errors.extend(
        f"title mapping for '{node_id}' does not match any ending node"
        for node_id in sorted(set(titles_plan) - ending_node_ids)
    )

    return rewritten


def _apply_labels(
    skeleton: dict[str, object],
    labels_plan: dict[str, dict[str, str]],
    errors: list[str],
) -> int:
    """Rewrite the referenced choice labels in place; collect any errors.

    Unlike beats/titles, labels are not required to be exhaustive: the
    migration recipe only slots a label where a theme noun appears (design
    section 8.1 step 3), so this only rejects a plan entry that references a
    non-existent node or choice, not a choice the plan left unmapped.

    Args:
        skeleton: The (already-copied) skeleton to mutate.
        labels_plan: The plan's ``{node_id: {choice_id: new_label}}`` map.
        errors: Accumulator for human-readable failure messages.

    Returns:
        The count of labels actually rewritten.
    """
    nodes_by_id: dict[str, dict[str, object]] = {}
    for node in _iter_nodes(skeleton):
        node_id = node.get("id")
        if isinstance(node_id, str):
            nodes_by_id[node_id] = node

    rewritten = 0
    for node_id, choice_map in labels_plan.items():
        node = nodes_by_id.get(node_id)
        if node is None:
            errors.append(f"label mapping references non-existent node '{node_id}'")
            continue
        choices_by_id: dict[str, dict[str, object]] = {}
        choices = node.get("choices")
        if isinstance(choices, list):
            for raw_choice in cast("list[object]", choices):
                if isinstance(raw_choice, dict):
                    choice = cast("dict[str, object]", raw_choice)
                    choice_id = choice.get("id")
                    if isinstance(choice_id, str):
                        choices_by_id[choice_id] = choice
        for choice_id, new_label in choice_map.items():
            choice = choices_by_id.get(choice_id)
            if choice is None:
                msg = (
                    f"label mapping references non-existent choice '{choice_id}' "
                    f"on node '{node_id}'"
                )
                errors.append(msg)
                continue
            choice["label"] = new_label
            rewritten += 1

    return rewritten


def _malformed_tokens(skeleton: dict[str, object]) -> list[str]:
    """Return brace-delimited groups in the slotted surfaces that are not valid slot tokens.

    Scans the same three surfaces the render step will later substitute:
    FILL beats text, ending titles, and choice labels.

    Args:
        skeleton: The parameterized skeleton to scan.

    Returns:
        A sorted, de-duplicated list of malformed ``{...}`` groups.
    """
    malformed: set[str] = set()

    def _scan(text: str) -> None:
        groups: list[str] = _BRACE_GROUP_RE.findall(text)
        for group in groups:
            inner = group[1:-1]
            if _SLOT_ID_ONLY_RE.fullmatch(inner) is None:
                malformed.add(group)

    for node in _iter_nodes(skeleton):
        body = node.get("body")
        if isinstance(body, str):
            match = _FILL_RE.match(body)
            _scan(match.group(3) if match is not None else body)
        ending = node.get("ending")
        if isinstance(ending, dict):
            title = cast("dict[str, object]", ending).get("title")
            if isinstance(title, str):
                _scan(title)
        choices = node.get("choices")
        if isinstance(choices, list):
            for raw_choice in cast("list[object]", choices):
                if isinstance(raw_choice, dict):
                    label = cast("dict[str, object]", raw_choice).get("label")
                    if isinstance(label, str):
                        _scan(label)

    return sorted(malformed)


def _introduced_slot_ids(skeleton: dict[str, object]) -> frozenset[str]:
    """Return every well-formed ``{SLOT}`` token found in the slotted surfaces.

    Args:
        skeleton: The parameterized skeleton to scan.

    Returns:
        The set of slot ids introduced by the plan.
    """
    tokens: set[str] = set()
    for node in _iter_nodes(skeleton):
        body = node.get("body")
        if isinstance(body, str):
            match = _FILL_RE.match(body)
            if match is not None:
                tokens.update(SLOT_TOKEN_RE.findall(match.group(3)))
        ending = node.get("ending")
        if isinstance(ending, dict):
            title = cast("dict[str, object]", ending).get("title")
            if isinstance(title, str):
                tokens.update(SLOT_TOKEN_RE.findall(title))
        choices = node.get("choices")
        if isinstance(choices, list):
            for raw_choice in cast("list[object]", choices):
                if isinstance(raw_choice, dict):
                    label = cast("dict[str, object]", raw_choice).get("label")
                    if isinstance(label, str):
                        tokens.update(SLOT_TOKEN_RE.findall(label))
    return frozenset(tokens)


def _write_atomically(path: Path, text: str) -> None:
    """Write ``text`` to ``path``, replacing it atomically via a temp file.

    Supports in-place parameterization (``--out`` equal to the source
    skeleton path) without ever leaving a half-written file on disk if the
    process is interrupted mid-write.

    Args:
        path: The destination file path.
        text: The full file contents to write.
    """
    # #ASSUME: data-integrity: --out may equal the input skeleton path
    # (in-place migration per design section 8.1 step 4); writing to a
    # sibling temp file first and replacing atomically means a crash
    # mid-write never corrupts the source skeleton.
    # #VERIFY: exercised by test_parameterize_skeleton.py's success-path test.
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            _ = handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    """Apply a slotting plan to a skeleton and enforce every migration invariant.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        Exit code: 0 when the parameterized skeleton is written, 1 on any
        load error or invariant violation (nothing is written on failure).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeleton", help="Path to the pristine skeleton JSON.")
    parser.add_argument("plan", help="Path to the slotting plan JSON.")
    parser.add_argument(
        "--out", required=True, help="Path to write the parameterized skeleton."
    )
    args = parser.parse_args(argv)

    # argparse.Namespace attribute access is untyped (Any) in the stdlib
    # stubs regardless of the parser's declared arguments; this is the
    # standard, unavoidable boundary, not a loosened check on our own code.
    # ASSUME: security: skeleton/plan/out are canonicalized with .resolve()
    # (CWE-23 hardening, Snyk python/PT), but deliberately NOT contained to a
    # fixed base (the generation/import_cli.py::_load_blob idiom):
    # tests/unit/test_parameterize_skeleton.py exercises all three against
    # pytest tmp_path fixtures well outside the repo tree with no chdir,
    # proving arbitrary-location paths (including --out equal to the input
    # skeleton, the documented in-place migration mode) are legitimate,
    # exercised behavior that containment would reject. No privilege boundary
    # is crossed either way: the operator invoking this dev-only transform
    # already has full filesystem access, per the path-traversal
    # verification report (scratchpad/pt-verification-report.md).
    # VERIFY: any future change adding a fixed base must re-run
    # test_parameterize_skeleton.py first; a rejection there means real
    # behavior broke.
    skeleton_path = Path(args.skeleton).resolve()  # pyright: ignore[reportAny]
    plan_path = Path(args.plan).resolve()  # pyright: ignore[reportAny]
    out_path = Path(args.out).resolve()  # pyright: ignore[reportAny]

    try:
        original = _load_json_object(skeleton_path)
    except (OSError, json.JSONDecodeError, PlanError) as exc:
        sys.stderr.write(f"error: cannot load skeleton {skeleton_path}: {exc}\n")
        return 1
    try:
        plan_raw = _load_json_object(plan_path)
        beats_plan, titles_plan, labels_plan = _parse_plan(plan_raw)
    except (OSError, json.JSONDecodeError, PlanError) as exc:
        sys.stderr.write(f"error: cannot load plan {plan_path}: {exc}\n")
        return 1

    parameterized = copy.deepcopy(original)
    errors: list[str] = []
    beats_rewritten = _apply_beats(parameterized, beats_plan, errors)
    titles_rewritten = _apply_titles(parameterized, titles_plan, errors)
    labels_rewritten = _apply_labels(parameterized, labels_plan, errors)

    if errors:
        for error in errors:
            sys.stderr.write(f"FAIL plan: {error}\n")
        return 1

    # #CRITICAL: data-integrity: role=/words= must survive the transform
    # byte-for-byte; parsed and compared explicitly rather than assumed from
    # the reconstruction code above (mirrors CR-1's render-time check,
    # design section 13.2, applied here at authoring time).
    # #VERIFY: test_parameterize_skeleton.py's role/words preservation test.
    before_map = _role_words_map(original)
    after_map = _role_words_map(parameterized)
    if before_map != after_map:
        msg = (
            "FAIL role/words: a FILL directive's role= or words= changed, or a "
            "directive was introduced/degraded, applying the plan\n"
        )
        sys.stderr.write(msg)
        return 1

    malformed = _malformed_tokens(parameterized)
    if malformed:
        sys.stderr.write(f"FAIL token grammar: malformed slot token(s) {malformed}\n")
        return 1

    if structure_fingerprint(parameterized) != structure_fingerprint(original):
        msg = (
            "FAIL fingerprint: parameterizing changed the skeleton's structural "
            "fingerprint (something outside beats/titles/labels was touched)\n"
        )
        sys.stderr.write(msg)
        return 1

    gate_result = run_gate(parameterized)
    if gate_result.blocked:
        for finding in gate_result.report.errors:
            sys.stderr.write(f"FAIL gate: {finding.rule_id} {finding.message}\n")
        return 1

    slot_ids = _introduced_slot_ids(parameterized)
    _write_atomically(out_path, json.dumps(parameterized, indent=2) + "\n")
    summary = (
        f"wrote {out_path}: {len(beats_rewritten)} beats, "
        f"{len(titles_rewritten)} titles, {labels_rewritten} labels rewritten, "
        f"{len(slot_ids)} slot id(s) introduced: {sorted(slot_ids)}"
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
