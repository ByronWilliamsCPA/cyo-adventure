"""Normalize a filled story's frozen fields back from its skeleton.

The 2026-08-21 freeze-split ruling
(``docs/planning/live-structural-round-2026-08-21.md`` section 8.2) splits the
fill contract's freeze by function: machine-critical fields are frozen and the
pipeline stops depending on model obedience for them, while theme-bearing text
is writable. Measured motivation: across 16 committed one-shot fills, 4 mutated
a frozen field and 15 drifted an ambiguous one, and every frozen mutation was a
retheme of documentation text the freeze happened to cover (`AL-510`).

The normalizer is the inverse of ``check_fill_integrity``'s leaf stripping:
the result STARTS from the skeleton and overlays exactly the writable leaf
content from the fill:

- the storybook ``title`` (writable per section 8.3),
- each node's ``body``,
- each choice's ``label``,
- each ending's ``title`` (writable per section 8.3),
- each variable's ``description`` (theme documentation, writable per 8.2).

Everything else (ids, targets, conditions, effects, ``on_enter``,
``start_node``, ``is_ending``, ending ``kind``/``valence``, variable
name/type/bounds/initial, and ``metadata``) comes from the skeleton by
construction, so model drift on a frozen field becomes a non-event rather than
a shipped defect or a burned repair cycle. ``metadata`` currently includes
``themes``; the ruling wants themes re-derived at import rather than kept
stale, and that deriver is separate scheduled work (`UW-C317`), so until it
lands the skeleton's themes are what ship.

How the fill is matched to the skeleton, exactly
------------------------------------------------

Nodes and choices are matched by ID, never by position. Position is what the
fill contract asks for, but a model that returns the right ids in a different
order writes a document that is still structurally valid, so no deterministic
gate downstream can catch a positional mis-pairing: a child would read one
choice's label and land on another choice's target. Matching by id makes a
reordered fill a non-event instead.

Normalization is SKIPPED, and the fill returned exactly as the model wrote it
for the gate to judge, when any of these hold:

- the raw ``nodes`` list carries entries that are not JSON objects,
- the node count differs from the skeleton's,
- node ids on either side are absent, non-string, or duplicated, so no id
  lookup can be built,
- the fill's node id SET differs from the skeleton's (an id the skeleton does
  not have cannot be matched to anything),
- any node's choice id set differs from that skeleton node's choice id set,
  including a differing choice COUNT, an added choice on a node the skeleton
  gives none, or duplicated/non-string choice ids.

Skipping is the safe direction: overlaying leaves onto a graph that is not the
skeleton's graph would fabricate a book, and the gate owns that verdict.

Variables have no ``id``; their identity key is ``name``. They are matched by
name when both sides carry the same unique name set, so a reordered fill keeps
each description with its own variable. When the names disagree they fall back
to position, because a RENAMED variable (the measured `AL-510` case, where the
fill rethemes a variable's name and its description together) can only be
recognised by where it sits, and refusing to normalize a whole book over a
themed rename would defeat the purpose of the freeze split. A description
mis-binding is documentation drift, not a routing defect, so the fallback is
bounded in blast radius; the fallback is recorded in ``restored``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

__all__ = ["NormalizedFill", "normalize_filled_story"]


@dataclass(frozen=True)
class NormalizedFill:
    """The outcome of normalizing one filled story against its skeleton.

    Attributes:
        document: The normalized document (the input ``filled`` unchanged when
            ``skipped_reason`` is set).
        restored: Human-readable notes for each frozen field the fill had
            drifted and the normalizer restored; empty for an obedient fill.
        skipped_reason: Why normalization did not run, or None when it did.
    """

    document: dict[str, object]
    restored: tuple[str, ...] = field(default=())
    skipped_reason: str | None = None


def _nodes(doc: dict[str, object]) -> list[dict[str, object]]:
    raw = doc.get("nodes")
    if not isinstance(raw, list):
        return []
    return [cast("dict[str, object]", n) for n in raw if isinstance(n, dict)]


def _dict_entries(value: object) -> list[dict[str, object]]:
    """Return the JSON-object entries of ``value`` when it is a list."""
    if not isinstance(value, list):
        return []
    return [
        cast("dict[str, object]", entry)
        for entry in cast("list[object]", value)
        if isinstance(entry, dict)
    ]


def _keyed_by(
    entries: list[dict[str, object]], key: str
) -> dict[str, dict[str, object]] | None:
    """Return ``entries`` keyed by ``key``, or None when they are not keyable.

    Args:
        entries: The JSON objects to key.
        key: The identity field to key on (``id`` for nodes and choices,
            ``name`` for variables).

    Returns:
        dict[str, dict[str, object]] | None: The lookup, or None when any
        entry's key is missing, not a string, or duplicated. A caller that
        gets None cannot match by identity and must not guess.
    """
    keyed: dict[str, dict[str, object]] = {}
    for entry in entries:
        entry_key = entry.get(key)
        if not isinstance(entry_key, str) or entry_key in keyed:
            return None
        keyed[entry_key] = entry
    return keyed


def _node_order(nodes: list[dict[str, object]]) -> list[object]:
    """Return the node ids in list order, for an order-drift note."""
    return [node.get("id") for node in nodes]


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _drift_notes(
    filled_map: dict[str, object],
    reference: dict[str, object],
    keys: tuple[str, ...],
    where: str,
) -> list[str]:
    """Return one note per frozen ``keys`` entry the fill drifted in ``where``."""
    return [
        f"{where}.{key} restored from the skeleton"
        for key in keys
        if key in filled_map and filled_map.get(key) != reference.get(key)
    ]


def _story_level_notes(
    skeleton: dict[str, object], filled: dict[str, object]
) -> list[str]:
    """Return notes for story-level frozen fields the fill drifted."""
    notes: list[str] = []
    if filled.get("id") != skeleton.get("id"):
        notes.append(
            f"story.id restored from the skeleton "
            f"({filled.get('id')!r} -> {skeleton.get('id')!r})"
        )
    if filled.get("start_node") != skeleton.get("start_node"):
        notes.append("start_node restored from the skeleton")
    if isinstance(filled.get("metadata"), dict) and filled.get(
        "metadata"
    ) != skeleton.get("metadata"):
        notes.append("metadata restored from the skeleton")
    return notes


def _node_alignment_error(
    skeleton_nodes: list[dict[str, object]], filled_nodes: list[dict[str, object]]
) -> str | None:
    """Return why the two node lists cannot be matched by id, or None.

    Args:
        skeleton_nodes: The skeleton's node objects.
        filled_nodes: The fill's node objects, already known to be the same
            count as the skeleton's.

    Returns:
        str | None: A skip reason, or None when every skeleton node has
        exactly one same-id counterpart in the fill.
    """
    skeleton_by_id = _keyed_by(skeleton_nodes, "id")
    filled_by_id = _keyed_by(filled_nodes, "id")
    if skeleton_by_id is None or filled_by_id is None:
        return (
            "node ids are missing, duplicated, or not strings on one side; "
            "without an id lookup the fill can only be matched by position, "
            "and a reordered fill would bind prose to the wrong node"
        )
    if set(skeleton_by_id) != set(filled_by_id):
        missing = sorted(set(skeleton_by_id) - set(filled_by_id))
        unexpected = sorted(set(filled_by_id) - set(skeleton_by_id))
        return (
            f"node ids differ (missing={missing}, unexpected={unexpected}); "
            "overlaying leaves onto a different graph would fabricate a book"
        )
    return None


def _choice_alignment_error(
    skeleton_node: dict[str, object], filled_node: dict[str, object], node_id: str
) -> str | None:
    """Return why one node's choices cannot be matched by id, or None.

    Args:
        skeleton_node: The skeleton's node.
        filled_node: The fill's node carrying the same id.
        node_id: That id, for the message.

    Returns:
        str | None: A skip reason, or None when the two choice id sets are
        equal and both are keyable. A node the skeleton gives no choices
        matches a fill that gives it none.
    """
    skeleton_by_id = _keyed_by(_dict_entries(skeleton_node.get("choices")), "id")
    filled_by_id = _keyed_by(_dict_entries(filled_node.get("choices")), "id")
    if skeleton_by_id is None or filled_by_id is None:
        return (
            f"choice ids on node {node_id!r} are missing, duplicated, or not "
            "strings on one side; a label matched by position can land under "
            "another choice's target"
        )
    if set(skeleton_by_id) != set(filled_by_id):
        missing = sorted(set(skeleton_by_id) - set(filled_by_id))
        unexpected = sorted(set(filled_by_id) - set(skeleton_by_id))
        return (
            f"choice ids on node {node_id!r} differ (missing={missing}, "
            f"unexpected={unexpected}); the fill is not describing this "
            "node's branches"
        )
    return None


def _alignment_error(
    skeleton_nodes: list[dict[str, object]], filled_nodes: list[dict[str, object]]
) -> str | None:
    """Return the first reason the fill cannot be matched by id, or None.

    Args:
        skeleton_nodes: The skeleton's node objects.
        filled_nodes: The fill's node objects, same count as the skeleton's.

    Returns:
        str | None: A skip reason, or None when every node and every choice
        can be paired by id.
    """
    node_error = _node_alignment_error(skeleton_nodes, filled_nodes)
    if node_error is not None:
        return node_error
    # Not None past the check above; the `or {}` is for the type checker only.
    filled_by_id = _keyed_by(filled_nodes, "id") or {}
    for skeleton_node in skeleton_nodes:
        node_id = cast("str", skeleton_node.get("id"))
        choice_error = _choice_alignment_error(
            skeleton_node, filled_by_id[node_id], node_id
        )
        if choice_error is not None:
            return choice_error
    return None


def _overlay_choices(
    skeleton_node: dict[str, object],
    filled_node: dict[str, object],
    notes: list[str],
    node_id: object,
) -> object:
    """Return the skeleton node's choices with the fill's label text overlaid.

    # #CRITICAL: data-integrity: each label is taken from the fill's choice
    # carrying the SAME id, never from the choice at the same index. A model
    # that returns the skeleton's own choice ids in a different order writes a
    # structurally valid document, so nothing downstream can catch a positional
    # pairing; the child would read one branch's label and be routed to
    # another branch's target. ``_choice_alignment_error`` has already
    # guaranteed the two id sets are equal, so every lookup here resolves.
    # #VERIFY: tests/unit/test_normalize_fill.py::
    # test_reordered_choices_keep_each_label_with_its_own_target asserts the
    # label-to-target pairing survives a fill that reverses the choice order.

    Args:
        skeleton_node: The skeleton's node.
        filled_node: The fill's node carrying the same id.
        notes: The running restoration notes, appended to in place.
        node_id: The node id, for the notes.

    Returns:
        object: The rebuilt choices list, or the skeleton's own ``choices``
        value unchanged when it is not a list.
    """
    skeleton_choices = skeleton_node.get("choices")
    if not isinstance(skeleton_choices, list):
        return skeleton_choices
    filled_by_id = _keyed_by(_dict_entries(filled_node.get("choices")), "id") or {}
    rebuilt: list[object] = []
    for entry in cast("list[object]", skeleton_choices):
        if not isinstance(entry, dict):
            rebuilt.append(entry)
            continue
        choice = dict(cast("dict[str, object]", entry))
        choice_id = choice.get("id")
        filled_choice = (
            filled_by_id.get(choice_id) if isinstance(choice_id, str) else None
        )
        if filled_choice is not None:
            label = _str_or_none(filled_choice.get("label"))
            if label is not None:
                choice["label"] = label
            # ``id`` is absent from the frozen keys here because the pairing
            # is BY id: the two are equal by construction, so a note could
            # never fire. A fill that renames a choice id is caught earlier,
            # by ``_choice_alignment_error``, and skips normalization.
            notes.extend(
                _drift_notes(
                    filled_choice,
                    choice,
                    ("target", "condition", "effects"),
                    f"node {node_id!r} choice",
                )
            )
        rebuilt.append(choice)
    return rebuilt


def _overlay_ending(
    skeleton_node: dict[str, object],
    filled_node: dict[str, object],
    notes: list[str],
    node_id: object,
) -> object:
    """Return the skeleton node's ending with the fill's title overlaid."""
    skeleton_ending = skeleton_node.get("ending")
    if not isinstance(skeleton_ending, dict):
        return skeleton_ending
    ending = dict(cast("dict[str, object]", skeleton_ending))
    filled_ending = filled_node.get("ending")
    if isinstance(filled_ending, dict):
        filled_block = cast("dict[str, object]", filled_ending)
        title = _str_or_none(filled_block.get("title"))
        if title is not None:
            ending["title"] = title
        notes.extend(
            _drift_notes(
                filled_block,
                ending,
                ("id", "kind", "valence"),
                f"node {node_id!r} ending",
            )
        )
    return ending


def _paired_variables(
    skeleton_vars: list[dict[str, object]],
    filled_vars: list[dict[str, object]],
    notes: list[str],
) -> list[dict[str, object] | None]:
    """Return the fill's counterpart for each skeleton variable, in order.

    # #ASSUME: data-integrity: variables carry no ``id``, so ``name`` is their
    # identity key. When both sides carry the same unique name set the pairing
    # is by name, which keeps a reordered fill's description with its own
    # variable. When the names disagree the only remaining signal is position,
    # and a themed RENAME (the measured `AL-510` case) is exactly that
    # situation; the positional fallback is what preserves description
    # retheming instead of discarding the whole normalization over it. A
    # rename that ALSO reorders would mis-bind a description, which is
    # documentation drift rather than a routing defect, and the fallback is
    # recorded in the returned notes.
    # #VERIFY: tests/unit/test_normalize_fill.py::
    # test_reordered_variables_keep_each_description_with_its_own_variable
    # covers the name-matched path, and
    # test_frozen_drift_is_restored_and_writable_retheming_is_kept covers the
    # renamed, positional path.

    Args:
        skeleton_vars: The skeleton's variable objects.
        filled_vars: The fill's variable objects.
        notes: The running restoration notes, appended to in place.

    Returns:
        list[dict[str, object] | None]: One entry per skeleton variable, in
        skeleton order; None where the fill offers no counterpart.
    """
    skeleton_by_name = _keyed_by(skeleton_vars, "name")
    filled_by_name = _keyed_by(filled_vars, "name")
    if (
        skeleton_by_name is not None
        and filled_by_name is not None
        and set(skeleton_by_name) == set(filled_by_name)
    ):
        return [
            filled_by_name[cast("str", entry.get("name"))] for entry in skeleton_vars
        ]
    notes.append("variables matched by position; the fill's names differ")
    return [
        filled_vars[index] if index < len(filled_vars) else None
        for index in range(len(skeleton_vars))
    ]


def _variable_label(variable: dict[str, object], index: int) -> str:
    """Return a report label for a variable, preferring its name over position.

    Variables are paired by name, so a note that says ``variables[2]`` makes the
    reader re-derive which variable that was. The index remains the fallback for
    a nameless variable, which only the positional fallback can produce.
    """
    name = _str_or_none(variable.get("name"))
    return f"variable {name!r}" if name is not None else f"variables[{index}]"


def _overlay_variables(
    skeleton: dict[str, object], filled: dict[str, object], notes: list[str]
) -> object:
    """Return the skeleton's variables with the fill's descriptions overlaid."""
    raw_vars = skeleton.get("variables")
    if not isinstance(raw_vars, list):
        return raw_vars
    skeleton_vars = cast("list[object]", raw_vars)
    skeleton_entries = _dict_entries(skeleton_vars)
    if len(skeleton_entries) != len(skeleton_vars):
        # A skeleton whose variables list holds non-objects is malformed; leave
        # it exactly as it is rather than pairing around the gaps.
        return skeleton_vars
    paired = _paired_variables(
        skeleton_entries, _dict_entries(filled.get("variables")), notes
    )
    rebuilt: list[object] = []
    for index, (entry, filled_var) in enumerate(
        zip(skeleton_entries, paired, strict=True)
    ):
        variable = dict(entry)
        if filled_var is not None:
            description = _str_or_none(filled_var.get("description"))
            if description is not None and description != variable.get("description"):
                variable["description"] = description
            notes.extend(
                _drift_notes(
                    filled_var,
                    variable,
                    ("name", "type", "min", "max", "initial"),
                    _variable_label(variable, index),
                )
            )
        rebuilt.append(variable)
    return rebuilt


def _malformed_nodes_reason(filled: dict[str, object]) -> str | None:
    """Return why the fill's raw node list is malformed, or None.

    Judge the RAW node list, not a dict-filtered view of it: filtering first
    would let a response carrying, say, the right number of node objects plus
    stray strings pass the count check with the garbage silently discarded,
    laundering malformed output into a valid-looking book. A malformed list is
    the gate's verdict to deliver, on the document as the model wrote it.

    Args:
        filled: The parsed model output.

    Returns:
        str | None: A skip reason, or None when every entry is a JSON object.
    """
    raw = filled.get("nodes")
    if not isinstance(raw, list):
        return None
    malformed = sum(
        1 for entry in cast("list[object]", raw) if not isinstance(entry, dict)
    )
    if not malformed:
        return None
    return (
        f"{malformed} node entr{'y is' if malformed == 1 else 'ies are'} "
        "not JSON objects; malformed output is judged as written, not "
        "repaired by discarding entries"
    )


def normalize_filled_story(
    skeleton: dict[str, object], filled: dict[str, object]
) -> NormalizedFill:
    """Rebuild ``filled`` as the skeleton plus its writable leaf content.

    # #CRITICAL: data-integrity: ``filled`` is untrusted model output, and this
    # runs BEFORE the deterministic gate and again on every repair pass, so a
    # mis-pairing here is graded as if the skeleton had said it. Nodes and
    # choices are therefore paired by id, and any disagreement that an id
    # lookup cannot reconcile (a differing node count, an unknown id, a
    # duplicated or non-string id, a differing choice id set) returns the
    # document exactly as the model wrote it with a ``skipped_reason``, so the
    # gate judges the fill rather than a document this function invented.
    # #VERIFY: tests/unit/test_normalize_fill.py::
    # test_reordered_nodes_keep_each_body_with_its_own_node_id and
    # test_a_filled_node_id_absent_from_the_skeleton_is_not_normalized and
    # test_a_fill_with_a_different_choice_count_is_not_normalized.

    Args:
        skeleton: The pristine skeleton the fill was commissioned from.
        filled: The parsed model output for that skeleton.

    Returns:
        NormalizedFill: The normalized document, the frozen drifts restored,
        and a skip reason when the graphs cannot be aligned.
    """
    malformed_reason = _malformed_nodes_reason(filled)
    if malformed_reason is not None:
        return NormalizedFill(document=filled, skipped_reason=malformed_reason)
    skeleton_nodes = _nodes(skeleton)
    filled_nodes = _nodes(filled)
    if len(skeleton_nodes) != len(filled_nodes):
        return NormalizedFill(
            document=filled,
            skipped_reason=(
                f"node count differs (skeleton {len(skeleton_nodes)}, "
                f"filled {len(filled_nodes)}); overlaying leaves onto a "
                "different graph would fabricate a book"
            ),
        )
    alignment_error = _alignment_error(skeleton_nodes, filled_nodes)
    if alignment_error is not None:
        return NormalizedFill(document=filled, skipped_reason=alignment_error)

    notes: list[str] = _story_level_notes(skeleton, filled)
    normalized: dict[str, object] = dict(skeleton)

    title = _str_or_none(filled.get("title"))
    if title is not None:
        normalized["title"] = title
    normalized["variables"] = _overlay_variables(skeleton, filled, notes)

    # `_alignment_error` has proven both sides key cleanly on the same id set,
    # so this lookup is never None and every node id below resolves.
    filled_by_id = _keyed_by(filled_nodes, "id") or {}
    rebuilt_nodes: list[object] = []
    for skeleton_node in skeleton_nodes:
        node_id = cast("str", skeleton_node.get("id"))
        filled_node = filled_by_id[node_id]
        node = dict(skeleton_node)
        body = _str_or_none(filled_node.get("body"))
        if body is not None:
            node["body"] = body
        if "choices" in node:
            node["choices"] = _overlay_choices(
                skeleton_node, filled_node, notes, node_id
            )
        if isinstance(skeleton_node.get("ending"), dict):
            node["ending"] = _overlay_ending(skeleton_node, filled_node, notes, node_id)
        rebuilt_nodes.append(node)
    normalized["nodes"] = rebuilt_nodes
    if _node_order(filled_nodes) != _node_order(skeleton_nodes):
        notes.append("node order restored from the skeleton; matched by id")
    return NormalizedFill(document=normalized, restored=tuple(notes))
