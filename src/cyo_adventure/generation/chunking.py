"""Chunked skeleton fill: partition, batch payloads, and a body-only merge.

``generation/orchestrator.py::fill_skeleton`` is one-shot by default: the whole
skeleton goes out and the whole filled document comes back in a single
completion. At the current default cap (``MAX_FILL_OUTPUT_TOKENS``, 131,072)
every production skeleton fits, so that path stays exactly as it was.

This module exists for **portability**, not for feasibility. The moment the
configured backend is a smaller-output model the default cap clamps down (see
``skeleton.MODEL_OUTPUT_CAPS``: ``deepseek/deepseek-chat-v3.1`` emits 32,768),
and the largest skeleton in the catalog needs 99,906 output tokens (measured
2026-08-19 on `the-last-cartage`; this said 87,200 until then, which was the
catalog's largest when written and is now its second). Under
such a backend a one-shot fill cannot be emitted at all: the completion stops on
``finish_reason=length``, truncated JSON parses as nothing, and the run dies
without a single line of prose. Chunking lets the same skeleton be filled a
batch at a time, so the catalog is not silently coupled to one vendor's
output ceiling.

Three responsibilities, all pure:

* :func:`plan_fill_batches` partitions the fillable nodes into batches whose
  expected output fits the cap, in narrative (breadth-first) order so a batch
  holds nodes that are adjacent in the story graph.
* :func:`batch_request` and :func:`written_prose` build the two per-batch
  payloads the subset prompt carries: what to write now, and what earlier
  batches already wrote (so names, world, and voice survive across batches).
* :func:`merge_fill_batch` folds one batch reply back into the document. It is
  a whitelist merge: only node bodies, choice label text, and ending titles
  (leaf content per the 2026-08-21 ruling,
  ``docs/planning/live-structural-round-2026-08-21.md`` section 8.3) are ever
  read from the reply, so no reply can change a node id, a choice target,
  ``start_node``, ``is_ending``, an ending's ``id``/``kind``/``valence``,
  ``variables``, or ``metadata``.

The expected-size arithmetic is not re-derived here. ``skeleton``'s
:func:`~cyo_adventure.generation.skeleton.expected_output_tokens` and
:func:`~cyo_adventure.generation.skeleton.is_fill_feasible` are called on a
synthetic ``{"nodes": [...]}`` slice, so a batch is measured by exactly the
function, ratio, and headroom margin that decided the whole skeleton did not
fit.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, cast

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.skeleton import (
    FILL_MARKER,
    expected_output_tokens,
    is_fill_feasible,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "UnpartitionableSkeletonError",
    "batch_request",
    "merge_fill_batch",
    "plan_fill_batches",
    "written_prose",
]


class UnpartitionableSkeletonError(ValidationError):
    """No partition of this skeleton fits the cap, so retrying cannot help.

    Distinct from a plain :class:`ValidationError` because `fill_skeleton`
    converts THIS case into a deterministic failed outcome rather than raising.
    A blanket `except ValidationError` around the chunked fill also swallowed
    two unrelated failures and reported both as "unfillable under cap": a PII
    abort from `PiiGuardedProvider.complete` (a security stop that must
    propagate, and does on the one-shot path) and a rejected model reply from
    `merge_fill_batch` (retryable, and not a capacity problem at all).
    Mislabelling a PII abort as a capacity limit is the serious half (`AL-435`).
    """


def _nodes(document: dict[str, object]) -> list[dict[str, object]]:
    """Return the document's node dicts, skipping any non-dict entry.

    Args:
        document: A skeleton or partially-filled story document.

    Returns:
        list[dict[str, object]]: The node dicts in document order.
    """
    raw = document.get("nodes")
    if not isinstance(raw, list):
        return []
    return [
        cast("dict[str, object]", entry)
        for entry in cast("list[object]", raw)
        if isinstance(entry, dict)
    ]


def _node_id(node: dict[str, object]) -> str | None:
    """Return a node's id when it is a string, else ``None``.

    Args:
        node: One node dict.

    Returns:
        str | None: The id, or ``None`` when absent or not a string.
    """
    node_id = node.get("id")
    return node_id if isinstance(node_id, str) else None


def _choices(node: dict[str, object]) -> list[dict[str, object]]:
    """Return a node's choice dicts, skipping any non-dict entry.

    Args:
        node: One node dict.

    Returns:
        list[dict[str, object]]: The choice dicts in declared order.
    """
    raw = node.get("choices")
    if not isinstance(raw, list):
        return []
    return [
        cast("dict[str, object]", entry)
        for entry in cast("list[object]", raw)
        if isinstance(entry, dict)
    ]


def _needs_fill(node: dict[str, object]) -> bool:
    """Return whether this node's body still carries a ``<<FILL ...>>`` directive.

    Args:
        node: One node dict.

    Returns:
        bool: True when the body is a string containing the fill marker.
    """
    body = node.get("body")
    return isinstance(body, str) and FILL_MARKER in body


def _narrative_order(document: dict[str, object]) -> list[dict[str, object]]:
    """Return every fillable node, ordered breadth-first from ``start_node``.

    Batching in document order would be arbitrary: a skeleton's node array has
    no guaranteed relationship to the reading order. Breadth-first traversal
    from the start node, following each node's choices in declared order, keeps
    a node and the passages it leads to in the same batch wherever the budget
    allows, so one batch reads as a contiguous stretch of story rather than as
    scattered passages the model has no way to connect.

    Nodes never reached from ``start_node`` are appended in document order.
    A gate-validated skeleton has none (reachability is a blocking L1 rule), so
    this is defence against being handed something the gate never saw, not an
    expected case.

    Args:
        document: A skeleton or partially-filled story document.

    Returns:
        list[dict[str, object]]: The fillable node dicts in traversal order.
    """
    nodes = _nodes(document)
    by_id = {node_id: node for node in nodes if (node_id := _node_id(node)) is not None}
    start = document.get("start_node")
    queue: deque[str] = deque()
    if isinstance(start, str) and start in by_id:
        queue.append(start)
    seen: set[str] = set(queue)
    ordered: list[dict[str, object]] = []
    while queue:
        node = by_id[queue.popleft()]
        if _needs_fill(node):
            ordered.append(node)
        for choice in _choices(node):
            target = choice.get("target")
            if isinstance(target, str) and target in by_id and target not in seen:
                seen.add(target)
                queue.append(target)
    ordered.extend(
        node
        for node in nodes
        if _needs_fill(node) and (nid := _node_id(node)) is not None and nid not in seen
    )
    return ordered


def _batch_ids(open_batch: list[dict[str, object]]) -> tuple[str, ...]:
    """Return the ids of every node in *open_batch*, refusing to drop any.

    The earlier inline form was ``tuple(_id for n in b if (_id := _node_id(n)))``,
    a TRUTHINESS test rather than an identity one. A node carrying ``id: ""`` is a
    string, so it survived ``_narrative_order`` and counted toward the batch's
    feasibility arithmetic, then vanished from the emitted tuple: the batch asked
    for fewer nodes than it was measured against, and a batch of only such nodes
    emitted ``()``, which made ``merge_fill_batch`` reject every reply with a
    message naming no node at all.

    Args:
        open_batch: The nodes packed into the batch being closed.

    Returns:
        tuple[str, ...]: One id per node, in order.

    Raises:
        ValidationError: If any node has no usable string id. Failing here is
            deliberate: the alternative is a batch that silently under-requests.
    """
    ids = tuple(
        node_id for node in open_batch if (node_id := _node_id(node)) is not None
    )
    if len(ids) != len(open_batch):
        msg = (
            f"{len(open_batch) - len(ids)} of {len(open_batch)} nodes in a fill batch "
            f"have no string 'id'; a batch cannot request a node it cannot name"
        )
        raise ValidationError(msg, field="id", value=len(open_batch))
    return ids


def plan_fill_batches(
    document: dict[str, object], *, max_tokens: int
) -> list[tuple[str, ...]]:
    """Partition the fillable nodes into batches that each fit under *max_tokens*.

    Greedy packing over :func:`_narrative_order`: a node joins the open batch
    while the batch as a whole stays feasible, and starts a new batch when it
    does not. Deterministic and stable, because both the order and the
    feasibility test are pure functions of the document.

    Feasibility per batch is
    :func:`~cyo_adventure.generation.skeleton.is_fill_feasible` applied to the
    batch's nodes, so a batch inherits the same 20 percent headroom margin that
    the whole-skeleton screen uses. That margin matters more per batch than it
    does per book: reasoning tokens bill against the same budget and are
    invisible to this arithmetic (`AL-328`, `AL-329`).

    Args:
        document: The skeleton to partition. Nodes whose bodies no longer carry
            a ``<<FILL ...>>`` directive are not batched: there is nothing left
            to write for them.
        max_tokens: The output cap each batch call will run under.

    Returns:
        list[tuple[str, ...]]: Batches of node ids, in narrative order. Empty
        when the document has no fillable node.

    Raises:
        ValidationError: If one node's own expected output does not fit under
            *max_tokens*. No partition can rescue that: the smallest batch this
            function can emit is a single node, so the caller must be told
            rather than handed a batch that is certain to truncate.
    """
    batches: list[tuple[str, ...]] = []
    open_batch: list[dict[str, object]] = []
    for node in _narrative_order(document):
        if not is_fill_feasible({"nodes": [node]}, max_tokens=max_tokens):
            msg = (
                f"node {_node_id(node)!r} expects "
                f"{expected_output_tokens({'nodes': [node]})} output tokens, which "
                f"does not fit a {max_tokens}-token cap even alone; no partition "
                f"of this skeleton is fillable on this backend"
            )
            raise UnpartitionableSkeletonError(
                msg, field="max_tokens", value=max_tokens
            )
        if open_batch and not is_fill_feasible(
            {"nodes": [*open_batch, node]}, max_tokens=max_tokens
        ):
            batches.append(_batch_ids(open_batch))
            open_batch = []
        open_batch.append(node)
    if open_batch:
        batches.append(_batch_ids(open_batch))
    return batches


def batch_request(
    document: dict[str, object], node_ids: Sequence[str]
) -> list[dict[str, object]]:
    """Return the per-node work order for one batch.

    Each entry carries the node's id, its unfilled ``<<FILL ...>>`` directive
    body, and its choices as ``{"id": ..., "label": ...}`` pairs. Targets,
    conditions, and effects are deliberately not included: the model is not
    asked to reproduce anything it is forbidden to change, and
    :func:`merge_fill_batch` would ignore them if it did.

    Args:
        document: The skeleton or partially-filled document.
        node_ids: The ids in this batch.

    Returns:
        list[dict[str, object]]: One entry per requested id, in the order given.
        Ids absent from the document are skipped.
    """
    by_id = {
        node_id: node
        for node in _nodes(document)
        if (node_id := _node_id(node)) is not None
    }
    request: list[dict[str, object]] = []
    for node_id in node_ids:
        node = by_id.get(node_id)
        if node is None:
            continue
        request.append(
            {
                "node_id": node_id,
                "directive": node.get("body"),
                "choices": [
                    {"id": choice.get("id"), "label": choice.get("label")}
                    for choice in _choices(node)
                ],
            }
        )
    return request


def written_prose(document: dict[str, object]) -> dict[str, str]:
    """Return the prose earlier batches have already written, keyed by node id.

    This is the coherence carrier. A batch that saw only its own directives
    would invent its own names, setting details, and voice, and the merged book
    would read as several stories stapled together. Passing back what is
    already written costs input tokens (cheap) rather than output tokens (the
    constrained resource).

    Args:
        document: The partially-filled document.

    Returns:
        dict[str, str]: Node id to body, for every node whose body is prose
        rather than an unfilled directive. Empty for an untouched skeleton.
    """
    return {
        node_id: body
        for node in _nodes(document)
        if (node_id := _node_id(node)) is not None
        and isinstance(body := node.get("body"), str)
        and FILL_MARKER not in body
    }


def _require_str(value: object, *, what: str, node_id: str) -> str:
    """Return *value* as a non-blank string, or raise.

    Args:
        value: The candidate value from the model reply.
        what: What is being validated, for the error message.
        node_id: The node the value belongs to, for the error message.

    Returns:
        str: The validated string.

    Raises:
        ValidationError: If the value is not a string, or is blank.
    """
    if not isinstance(value, str) or not value.strip():
        msg = f"batch reply for node {node_id!r} has a missing or non-string {what}"
        raise ValidationError(msg, field=what, value=node_id)
    return value


def _merged_labels(
    node: dict[str, object], reply: dict[str, object], node_id: str
) -> object:
    """Return this node's choices with only their label text replaced.

    Every other key on a choice (``id``, ``target``, ``condition``,
    ``effects``) is carried through from the skeleton by dict spread, never
    read from the reply. A label the reply omits keeps the skeleton's text.

    Args:
        node: The skeleton node.
        reply: The reply entry for this node.
        node_id: The node id, for error messages.

    Returns:
        object: The rebuilt choices list, or the skeleton's own ``choices``
        value unchanged when it is not a list.

    Raises:
        ValidationError: If ``choices`` is present but not a mapping, names a
            choice id this node does not have, or supplies a label that is still
            a ``<<FILL ...>>`` directive. An invented choice id means the reply
            is not about this node's choices, and guessing which one it meant
            would write the wrong text under the wrong branch.
    """
    raw = node.get("choices")
    if not isinstance(raw, list):
        # Carry a malformed `choices` through untouched rather than replacing it
        # with []. Returning [] here was the one place this merge mutated the
        # graph, which contradicts the whitelist promise in `merge_fill_batch`'s
        # docstring, and it silently discarded a node's branches instead of
        # letting the gate fail on the reason the document was really malformed.
        return raw
    choices = cast("list[object]", raw)
    labels = reply.get("choices")
    if labels is None:
        return list(choices)
    if not isinstance(labels, dict):
        msg = f"batch reply for node {node_id!r} has a non-object 'choices'"
        raise ValidationError(msg, field="choices", value=node_id)
    proposed = cast("dict[str, object]", labels)
    known = {
        choice_id
        for entry in choices
        if isinstance(entry, dict)
        and isinstance(choice_id := cast("dict[str, object]", entry).get("id"), str)
    }
    unknown = set(proposed) - known
    if unknown:
        msg = (
            f"batch reply for node {node_id!r} names choice ids this node does "
            f"not have: {sorted(unknown)}"
        )
        raise ValidationError(msg, field="choices", value=node_id)
    rebuilt: list[object] = []
    for entry in choices:
        if not isinstance(entry, dict):
            rebuilt.append(entry)
            continue
        choice = cast("dict[str, object]", entry)
        choice_id = choice.get("id")
        if isinstance(choice_id, str) and choice_id in proposed:
            label = _require_str(
                proposed[choice_id], what="choice label", node_id=node_id
            )
            # #CRITICAL: data-integrity: a label is reader-visible button text, and
            # nothing downstream catches a directive left in one. PL-27 iterates
            # `story.nodes` and tests `node.body` only, `has_unfilled_directives`
            # likewise, and `Choice.label` carries only `min_length=1`, so a reply
            # echoing its own directive back as a label produced a book that
            # cleared the fill-result gate unblocked and showed `<<FILL role=choice
            # words=8>>` to a child. Verified end-to-end before the guard existed:
            # the merge accepted it and `run_gate(..., context="fill_result")`
            # returned blocked=False with no finding mentioning the marker.
            # #VERIFY: test_chunked_fill.py::
            # test_a_batch_whose_choice_label_is_a_directive_is_rejected, and
            # test_gate.py::test_fill_result_context_blocks_a_directive_in_a_choice_label
            # covers the same class at the gate as defence in depth.
            if FILL_MARKER in label:
                msg = (
                    f"batch reply for node {node_id!r} returned the fill directive "
                    f"instead of prose for choice {choice_id!r}"
                )
                raise ValidationError(msg, field="choice label", value=node_id)
            rebuilt.append({**choice, "label": label})
        else:
            rebuilt.append(choice)
    return rebuilt


def _apply_merged_ending(
    merged: dict[str, object],
    node: dict[str, object],
    reply: dict[str, object],
    node_id: str,
) -> None:
    """Set ``merged["ending"]`` from the reply when the node warrants one.

    An explicit JSON null ``ending_title`` on a non-ending node must not mint
    an ``"ending": None`` key the skeleton never carried (PR #737 review,
    suggested findings); a node with no ending and no proposed title is left
    untouched.

    Args:
        merged: The node being rebuilt, mutated in place.
        node: The skeleton node.
        reply: The reply entry for this node.
        node_id: The node id, for error messages.
    """
    if "ending_title" not in reply and "ending" not in node:
        return
    merged_ending = _merged_ending(node, reply, node_id)
    if merged_ending is not None or "ending" in node:
        merged["ending"] = merged_ending


def _merged_ending(
    node: dict[str, object], reply: dict[str, object], node_id: str
) -> object:
    """Return this node's ending block with only its title replaced.

    ``ending.title`` is leaf content (ruled 2026-08-21,
    ``docs/planning/live-structural-round-2026-08-21.md`` section 8.3): a
    themed fill may retitle an ending the way it rewrites a choice label.
    Every other key on the ending (``id``, ``kind``, ``valence``, which carry
    the PL-15 fail-state policy) is carried through from the skeleton by dict
    spread, never read from the reply. A reply that omits ``ending_title``
    keeps the skeleton's title.

    Args:
        node: The skeleton node.
        reply: The reply entry for this node.
        node_id: The node id, for error messages.

    Returns:
        object: The rebuilt ending dict, or the skeleton's own ``ending``
        value unchanged when no rewrite applies.

    Raises:
        ValidationError: If ``ending_title`` is supplied for a node with no
            ending block, is not a non-blank string, or still carries a
            ``<<FILL ...>>`` directive. A title for a non-ending node means
            the reply is not about this node, and guessing would retitle the
            wrong ending.
    """
    ending = node.get("ending")
    proposed = reply.get("ending_title")
    if proposed is None:
        return ending
    if not isinstance(ending, dict):
        msg = (
            f"batch reply for node {node_id!r} supplies 'ending_title' but the "
            f"node has no ending block"
        )
        raise ValidationError(msg, field="ending_title", value=node_id)
    title = _require_str(proposed, what="ending title", node_id=node_id)
    if FILL_MARKER in title:
        msg = (
            f"batch reply for node {node_id!r} returned the fill directive "
            f"instead of an ending title"
        )
        raise ValidationError(msg, field="ending_title", value=node_id)
    return {**cast("dict[str, object]", ending), "title": title}


def merge_fill_batch(
    document: dict[str, object], node_ids: Iterable[str], payload: object
) -> dict[str, object]:
    """Fold one batch reply into *document*, taking prose and nothing else.

    # #CRITICAL: data-integrity: ``payload`` is untrusted model output being
    # merged into a document that has already passed the structural gate. The
    # merge is a whitelist, not a patch: only ``body``, choice ``label``
    # text, and the ending ``title`` (leaf content per the 2026-08-21 ruling)
    # are ever read from the reply, and every other key on the story, on
    # a node, and on a choice is carried over from *document* by dict spread.
    # A reply therefore cannot alter ``start_node``, ``variables``,
    # ``metadata``, a node id, ``is_ending``, an ending's
    # ``id``/``kind``/``valence``, or a choice's
    # ``target``/``condition``/``effects``, whatever it contains. Structural
    # validation is re-run by the caller regardless, because body text feeds
    # blocking rules; this only guarantees the graph itself is untouched.
    # #VERIFY: test_chunked_fill.py asserts a reply that tries to rewrite each
    # of those fields leaves the merged document's graph identical.
    #
    # #CRITICAL: data-integrity: a batch that returns fewer nodes than it was
    # asked for must fail rather than merge partially. Every checker in the
    # gate SKIPS a ``<<FILL ...>>`` body rather than failing on it (`AL-325`),
    # so a half-merged document can clear the gate by abstention; only
    # ``PL-27`` stands between that and a book with directives in it, and a
    # total generation failure must not rest on one rule (`AL-327`).
    # #VERIFY: test_a_batch_that_omits_a_node_is_rejected and
    # test_a_batch_that_returns_an_unknown_node_is_rejected.

    Args:
        document: The document to fold into (the skeleton for the first batch,
            the result of the previous merge afterwards).
        node_ids: Exactly the ids this batch asked for.
        payload: The parsed model reply, expected to be a mapping of node id to
            ``{"body": str, "choices": {choice_id: str}}``, plus an optional
            ``"ending_title": str`` on ending nodes.

    Returns:
        dict[str, object]: A new document with those nodes' prose replaced.
        The input is not mutated.

    Raises:
        ValidationError: If the reply is not an object, does not cover exactly
            the requested ids, still carries a ``<<FILL`` directive, or names a
            choice id the node does not have.
    """
    requested = set(node_ids)
    if not isinstance(payload, dict):
        msg = (
            "batch reply was not a JSON object mapping node ids to prose "
            f"(got {type(payload).__name__})"
        )
        raise ValidationError(msg, field="payload", value=sorted(requested))
    reply = cast("dict[str, object]", payload)
    missing = sorted(requested - set(reply))
    unexpected = sorted(set(reply) - requested)
    if missing or unexpected:
        msg = (
            f"batch reply does not cover exactly the nodes it was asked for "
            f"(missing={missing}, unexpected={unexpected})"
        )
        raise ValidationError(msg, field="payload", value=sorted(requested))

    rebuilt: list[object] = []
    for entry in cast("list[object]", document.get("nodes") or []):
        if not isinstance(entry, dict):
            rebuilt.append(entry)
            continue
        node = cast("dict[str, object]", entry)
        node_id = _node_id(node)
        if node_id is None or node_id not in requested:
            rebuilt.append(node)
            continue
        written = reply[node_id]
        if not isinstance(written, dict):
            msg = f"batch reply for node {node_id!r} was not an object"
            raise ValidationError(msg, field="payload", value=node_id)
        node_reply = cast("dict[str, object]", written)
        body = _require_str(node_reply.get("body"), what="body", node_id=node_id)
        if FILL_MARKER in body:
            msg = (
                f"batch reply for node {node_id!r} returned the fill directive "
                f"instead of prose"
            )
            raise ValidationError(msg, field="body", value=node_id)
        merged: dict[str, object] = {**node, "body": body}
        if "choices" in node:
            merged["choices"] = _merged_labels(node, node_reply, node_id)
        _apply_merged_ending(merged, node, node_reply, node_id)
        rebuilt.append(merged)
    return {**document, "nodes": rebuilt}
