"""Stage 1 fidelity checks for skeleton-fill prep (both mechanisms).

Pure-code checks only (no LLM call, no I/O): no leftover FILL directives,
structure exactly preserved except body/label text, and each originally-FILLed
node's word count within tolerance of its directive's target. See
generation/fidelity_gate.py for the composed gate that adds one semantic LLM
check via moderation/fidelity_review.py.
"""

from __future__ import annotations

import re

from cyo_adventure.generation.skeleton import has_unfilled_directives

# Matches an entire FILL-directive body exactly.
# Greedy `.*` for beats is deliberate: a beats value may contain a literal
# apostrophe (e.g. "Biscuit's ears prick"), and since the directive always
# ends in `'>>` with no other `>>` on the line, greedy matching correctly
# captures the whole beats text instead of truncating at the first `'`.
# Example directive format: <<FILL role=rising words=95 beats='...'>>
_FILL_RE = re.compile(
    r"^<<FILL role=(?P<role>\S+) words=(?P<words>\d+) beats='(?P<beats>.*)'>>$",
    re.DOTALL,
)

# Word count must land within this fraction of the directive's target to pass
# (e.g. a words=100 target accepts 60-140 words). A generous starting
# tolerance, not calibrated against real fill runs yet.
_WORD_COUNT_TOLERANCE = 0.4


def parse_fill_directive(body: str) -> dict[str, str] | None:
    """Parse a "<<FILL role=... words=... beats='...'>>" body into its parts.

    Args:
        body: A node's ``body`` string.

    Returns:
        A dict with string keys "role", "words", "beats", or None if ``body``
        is not a FILL directive.
    """
    match = _FILL_RE.match(body)
    if match is None:
        return None
    return {
        "role": match.group("role"),
        "words": match.group("words"),
        "beats": match.group("beats"),
    }


def _nodes_by_id(story: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index a story's node list by id, tolerating a malformed nodes list."""
    nodes = story.get("nodes")
    if not isinstance(nodes, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for node in nodes:
        if isinstance(node, dict) and isinstance(node.get("id"), str):
            result[node["id"]] = node
    return result


def _choices_without_label(node: dict[str, object]) -> object:
    """Return a node's choices with each label stripped, for structural diff."""
    choices = node.get("choices")
    if not isinstance(choices, list):
        return choices
    stripped: list[object] = []
    for choice in choices:
        if isinstance(choice, dict):
            stripped.append({k: v for k, v in choice.items() if k != "label"})
        else:
            stripped.append(choice)
    return stripped


def structure_violations(
    original: dict[str, object], filled: dict[str, object]
) -> list[str]:
    """Return violation messages for any structural change beyond body/label text.

    Compares every top-level key except "nodes" for exact equality, then every
    node's keys except "body", and every choice's keys except "label".

    Args:
        original: The skeleton before filling.
        filled: The candidate filled document.

    Returns:
        Human-readable violation messages; empty when structure is preserved.
    """
    violations: list[str] = [
        f"top-level '{key}' changed"
        for key in ("id", "start_node", "variables", "metadata")
        if original.get(key) != filled.get(key)
    ]

    original_nodes = _nodes_by_id(original)
    filled_nodes = _nodes_by_id(filled)
    if original_nodes.keys() != filled_nodes.keys():
        missing = sorted(original_nodes.keys() - filled_nodes.keys())
        added = sorted(filled_nodes.keys() - original_nodes.keys())
        violations.append(f"node id set changed: missing={missing} added={added}")

    for node_id, orig_node in original_nodes.items():
        filled_node = filled_nodes.get(node_id)
        if filled_node is None:
            continue
        # Iterate the union of both nodes' keys so a filled node that ADDS a
        # structural key the skeleton lacked (e.g. injecting "is_ending") is
        # flagged too; iterating only the original's keys would miss net-new
        # keys and weaken the "structure exactly preserved" guarantee.
        for key in orig_node.keys() | filled_node.keys():
            if key in ("body", "choices"):
                continue
            if orig_node.get(key) != filled_node.get(key):
                violations.append(f"node '{node_id}' field '{key}' changed")
        if _choices_without_label(orig_node) != _choices_without_label(filled_node):
            violations.append(f"node '{node_id}' choices changed beyond label text")
    return violations


def word_count_violations(
    original: dict[str, object], filled: dict[str, object]
) -> list[str]:
    """Return violation messages for filled nodes whose length misses its target.

    Only checks nodes whose original body was a FILL directive; a node the
    skeleton author left as literal prose is not subject to a word-count target.

    Args:
        original: The skeleton before filling.
        filled: The candidate filled document.

    Returns:
        Human-readable violation messages; empty when every fill is in range.
    """
    violations: list[str] = []
    original_nodes = _nodes_by_id(original)
    filled_nodes = _nodes_by_id(filled)
    for node_id, orig_node in original_nodes.items():
        orig_body = orig_node.get("body")
        if not isinstance(orig_body, str):
            continue
        directive = parse_fill_directive(orig_body)
        if directive is None:
            continue
        filled_node = filled_nodes.get(node_id)
        if filled_node is None:
            continue
        filled_body = filled_node.get("body")
        if not isinstance(filled_body, str):
            violations.append(f"node '{node_id}' has no filled body")
            continue
        target = int(directive["words"])
        actual = len(filled_body.split())
        low = target * (1 - _WORD_COUNT_TOLERANCE)
        high = target * (1 + _WORD_COUNT_TOLERANCE)
        if not (low <= actual <= high):
            violations.append(
                f"node '{node_id}' word count {actual} outside "
                f"[{low:.0f}, {high:.0f}] for target {target}"
            )
    return violations


def run_fidelity_checks(
    original: dict[str, object], filled: dict[str, object]
) -> list[str]:
    """Run all pure-code Stage 1 fidelity checks.

    Args:
        original: The skeleton before filling (FILL-directive bodies).
        filled: The candidate filled document.

    Returns:
        Combined, human-readable violation messages from all pure-code
        checks; empty when the fill is structurally sound, fully filled, and
        every node's length is within tolerance.
    """
    violations: list[str] = []
    if has_unfilled_directives(filled):
        violations.append("filled document still contains unfilled FILL directives")
    violations.extend(structure_violations(original, filled))
    violations.extend(word_count_violations(original, filled))
    return violations
