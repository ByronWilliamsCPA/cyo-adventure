"""The Stage 1 semantic fidelity check: does filled prose match its beat?

One aggregate LLM call per fill job (all originally-FILLed nodes in one
prompt), reusing the ReviewProvider abstraction moderation/stages.py already
uses. Advisory only: an unparseable or missing response fails open (treated
as "pass"), since this check is one signal among several, not a hard gate --
the pure-code checks in generation/fidelity.py already catch the failures
that matter structurally.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cyo_adventure.generation.fidelity import parse_fill_directive

if TYPE_CHECKING:
    from cyo_adventure.moderation.review_provider import ReviewProvider

_FIDELITY_SYSTEM = (
    "You are a fidelity reviewer for a children's choose-your-own-adventure "
    "app. You will receive an original story skeleton's beat descriptions and "
    "the final filled prose for the same nodes. Judge whether each node's "
    "prose actually depicts its described beat (same events, same outcome), "
    "even though names, settings, and wording may have been adapted to a new "
    'theme. Return ONLY JSON: {"verdict": "pass"|"flag", "notes": "<short>"}. '
    '"flag" when one or more nodes depict materially different events than '
    'their beat description; "pass" otherwise.'
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


async def run_semantic_fidelity_check(
    original: dict[str, object],
    filled: dict[str, object],
    review_provider: ReviewProvider,
) -> str | None:
    """Ask an independent model whether filled prose matches its beat description.

    Args:
        original: The skeleton before filling (FILL-directive bodies).
        filled: The candidate filled document.
        review_provider: The (already PII-guarded) reviewer to call.

    Returns:
        None when the reviewer returns "pass", when there are no
        originally-FILLed nodes to check, or when its response cannot be
        parsed as the expected verdict shape (fails open -- advisory, not a
        hard gate); a short note string when it returns "flag".
    """
    pairs = _beat_prose_pairs(original, filled)
    if not pairs:
        return None

    user = "\n\n".join(
        f"Node {node_id}\nBeat: {beats}\nProse: {body}"
        for node_id, beats, body in pairs
    )
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
