"""Stage 1 semantic fidelity: beat fidelity plus choice-label intent.

Does filled prose match its beat, and does each rewritten choice label preserve
the original's action-semantic?

One aggregate LLM call per fill job (all originally-FILLed node beats plus all
rewritten choice labels in one prompt), reusing the ReviewProvider abstraction
moderation/stages.py already uses. Advisory only: an unparseable or missing
response fails open (treated as "pass"), since this check is one signal among
several, not a hard gate -- the pure-code checks in generation/fidelity.py
already catch the failures that matter structurally.

The label-intent half is the WS-1 semantic guarantee that replaced the removed
byte-level label check: the automated fill rewrites every choice label to a new
theme (generation/templates/fill.md), and once choice labels became leaf
content excluded from the structure fingerprint (see
docs/planning/ws0-label-fingerprint-evaluation.md), this reviewer is the check
that a rewritten label still means the same decision.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from cyo_adventure.generation.fidelity import parse_fill_directive

if TYPE_CHECKING:
    from cyo_adventure.moderation.review_provider import ReviewProvider

_FIDELITY_SYSTEM = (
    "You are a fidelity reviewer for a children's choose-your-own-adventure "
    "app. For each node you will receive the original skeleton's beat "
    "description, the final filled prose, and for each choice its original "
    "label and its final label. Names, settings, wording, and theme may have "
    "been adapted to a new premise. Judge two things: (1) does each node's "
    "prose actually depict its described beat (same events, same outcome)? and "
    "(2) does each choice's final label preserve the action-semantic of its "
    "original label (the same decision the reader is making, even if reworded "
    "or re-themed)? "
    'Return ONLY JSON: {"verdict": "pass"|"flag", "notes": "<short>"}. '
    '"flag" when one or more nodes depict materially different events than '
    "their beat description, OR one or more final labels change what the "
    'decision means (for example an original "go left at the fork" became '
    '"go right", or "trust the stranger" became "attack the stranger"); '
    '"pass" otherwise.'
)

_MAX_FIDELITY_TOKENS = 512


def _string_bodies_by_id(nodes: list[object]) -> dict[str, str]:
    """Index node string bodies by node id, skipping malformed entries.

    Args:
        nodes: A story's ``nodes`` list (entries of unknown shape).

    Returns:
        A mapping of node id to body for every node that is a dict with both a
        string ``id`` and a string ``body``.
    """
    result: dict[str, str] = {}
    for node in nodes:
        if isinstance(node, dict) and isinstance(node.get("id"), str):
            body = node.get("body")
            if isinstance(body, str):
                result[node["id"]] = body
    return result


def _beat_prose_pairs(
    original: dict[str, object], filled: dict[str, object]
) -> list[tuple[str, str, str]]:
    """Return (node_id, beats, filled_body) for every originally-FILLed node.

    Args:
        original: The skeleton before filling.
        filled: The candidate filled document.

    Returns:
        One triple per node whose original body was a parseable FILL
        directive and whose filled body is a string.
    """
    original_nodes = original.get("nodes")
    filled_nodes = filled.get("nodes")
    if not isinstance(original_nodes, list) or not isinstance(filled_nodes, list):
        return []
    filled_by_id = _string_bodies_by_id(filled_nodes)

    pairs: list[tuple[str, str, str]] = []
    for node_id, body in _string_bodies_by_id(original_nodes).items():
        directive = parse_fill_directive(body)
        filled_body = filled_by_id.get(node_id)
        if directive is not None and filled_body is not None:
            pairs.append((node_id, directive["beats"], filled_body))
    return pairs


def _choice_labels_by_node(nodes: list[object]) -> dict[str, dict[str, str]]:
    """Index each node's choice labels by node id then choice id.

    Args:
        nodes: A story's ``nodes`` list (entries of unknown shape).

    Returns:
        A mapping ``node_id -> {choice_id: label}`` for every node that is a
        dict with a string ``id`` whose ``choices`` list holds at least one
        choice dict with both a string ``id`` and a string ``label``; malformed
        entries are skipped rather than raising.
    """
    result: dict[str, dict[str, str]] = {}
    for node in nodes:
        if not (isinstance(node, dict) and isinstance(node.get("id"), str)):
            continue
        choices = node.get("choices")
        if not isinstance(choices, list):
            continue
        labels: dict[str, str] = {}
        for choice in cast("list[object]", choices):
            if (
                isinstance(choice, dict)
                and isinstance(choice.get("id"), str)
                and isinstance(choice.get("label"), str)
            ):
                labels[cast("str", choice["id"])] = cast("str", choice["label"])
        if labels:
            result[cast("str", node["id"])] = labels
    return result


def _label_intent_pairs(
    original: dict[str, object], filled: dict[str, object]
) -> dict[str, list[tuple[str, str, str]]]:
    """Return per-node ``(choice_id, original_label, final_label)`` triples.

    Only choices present in BOTH the skeleton and the fill (matched by the
    choice id, which the fill contract forbids changing) with a string label on
    each side are included. This is the label-intent input the WS-1 fidelity
    check judges (see module docstring): the byte-level label check was removed
    when labels became leaf content, so the reviewer confirms the reskin
    preserved each choice's meaning.

    Args:
        original: The skeleton before filling.
        filled: The candidate filled document.

    Returns:
        A mapping ``node_id -> [(choice_id, original_label, final_label), ...]``,
        omitting nodes and choices that are absent from either side.
    """
    original_nodes = original.get("nodes")
    filled_nodes = filled.get("nodes")
    if not isinstance(original_nodes, list) or not isinstance(filled_nodes, list):
        return {}
    original_labels = _choice_labels_by_node(original_nodes)
    filled_labels = _choice_labels_by_node(filled_nodes)

    result: dict[str, list[tuple[str, str, str]]] = {}
    for node_id, originals in original_labels.items():
        final_for_node = filled_labels.get(node_id, {})
        triples = [
            (choice_id, original_label, final_for_node[choice_id])
            for choice_id, original_label in originals.items()
            if choice_id in final_for_node
        ]
        if triples:
            result[node_id] = triples
    return result


def _ordered_review_node_ids(original: dict[str, object], keep: set[str]) -> list[str]:
    """Return ``keep`` node ids in the skeleton's own node order, de-duplicated.

    Args:
        original: The skeleton before filling (defines canonical node order).
        keep: The node ids that have something to review (a beat, a label, or
            both).

    Returns:
        The subset of ``keep`` ordered as the nodes appear in ``original``, so
        the reviewer prompt reads in story order and is deterministic.
    """
    nodes = original.get("nodes")
    ordered: list[str] = []
    seen: set[str] = set()
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                node_id = cast("str", node["id"])
                if node_id in keep and node_id not in seen:
                    ordered.append(node_id)
                    seen.add(node_id)
    return ordered


async def run_semantic_fidelity_check(
    original: dict[str, object],
    filled: dict[str, object],
    review_provider: ReviewProvider,
) -> str | None:
    """Ask an independent model whether the fill preserved beats and label intent.

    Args:
        original: The skeleton before filling (FILL-directive bodies, original
            choice labels).
        filled: The candidate filled document.
        review_provider: The (already PII-guarded) reviewer to call.

    Returns:
        None when the reviewer returns "pass", when there is nothing to check
        (no originally-FILLed node bodies AND no matched choice labels), or when
        its response cannot be parsed as the expected verdict shape (fails open
        -- advisory, not a hard gate); a short note string when it returns
        "flag".
    """
    beat_pairs = _beat_prose_pairs(original, filled)
    label_pairs = _label_intent_pairs(original, filled)
    if not beat_pairs and not label_pairs:
        return None

    beats_by_id = {node_id: (beats, body) for node_id, beats, body in beat_pairs}
    ordered_ids = _ordered_review_node_ids(
        original, set(beats_by_id) | set(label_pairs)
    )
    blocks: list[str] = []
    for node_id in ordered_ids:
        lines = [f"Node {node_id}"]
        if node_id in beats_by_id:
            beats, body = beats_by_id[node_id]
            lines.append(f"Beat: {beats}")
            lines.append(f"Prose: {body}")
        for choice_id, original_label, final_label in label_pairs.get(node_id, []):
            lines.append(
                f'Choice {choice_id}: original label "{original_label}" '
                f'-> final label "{final_label}"'
            )
        blocks.append("\n".join(lines))
    user = "\n\n".join(blocks)
    # #ASSUME: external-resources: the review provider returns a str per the
    # ReviewProvider.complete contract. An unparseable, empty, or non-str
    # response fails open (returns None = "pass"), matching this module's
    # advisory-only design (see docstring); the isinstance guard covers a
    # contract violation (e.g. None) that json.loads would raise TypeError on.
    # #VERIFY: test_semantic_check_fails_open_on_non_string_response.
    raw = await review_provider.complete(
        system=_FIDELITY_SYSTEM, prompt=user, max_tokens=_MAX_FIDELITY_TOKENS
    )
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or parsed.get("verdict") != "flag":
        return None
    notes = parsed.get("notes")
    return (
        notes
        if isinstance(notes, str) and notes
        else "fidelity reviewer flagged this fill"
    )
