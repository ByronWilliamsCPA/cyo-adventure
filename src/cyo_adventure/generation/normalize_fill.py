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

Nodes and choices are matched by position after an id-alignment check, because
position is what the fill contract preserves; a fill whose node or choice
COUNT differs, or whose raw node list carries non-object entries, is not
normalized (returned unchanged) since overlaying leaves onto a different or
malformed graph would fabricate a book, and the gate owns that verdict.
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


def _overlay_choices(
    skeleton_node: dict[str, object],
    filled_node: dict[str, object],
    notes: list[str],
    node_id: object,
) -> object:
    """Return the skeleton node's choices with the fill's label text overlaid."""
    skeleton_choices = skeleton_node.get("choices")
    if not isinstance(skeleton_choices, list):
        return skeleton_choices
    filled_raw = filled_node.get("choices")
    filled_choices = filled_raw if isinstance(filled_raw, list) else []
    rebuilt: list[object] = []
    for index, entry in enumerate(cast("list[object]", skeleton_choices)):
        if not isinstance(entry, dict):
            rebuilt.append(entry)
            continue
        choice = dict(cast("dict[str, object]", entry))
        filled_entry = (
            cast("list[object]", filled_choices)[index]
            if index < len(filled_choices)
            else None
        )
        if isinstance(filled_entry, dict):
            filled_choice = cast("dict[str, object]", filled_entry)
            label = _str_or_none(filled_choice.get("label"))
            if label is not None:
                choice["label"] = label
            notes.extend(
                _drift_notes(
                    filled_choice,
                    choice,
                    ("id", "target", "condition", "effects"),
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


def _overlay_variables(
    skeleton: dict[str, object], filled: dict[str, object], notes: list[str]
) -> object:
    """Return the skeleton's variables with the fill's descriptions overlaid."""
    skeleton_vars = skeleton.get("variables")
    if not isinstance(skeleton_vars, list):
        return skeleton_vars
    filled_raw = filled.get("variables")
    filled_vars = filled_raw if isinstance(filled_raw, list) else []
    rebuilt: list[object] = []
    for index, entry in enumerate(cast("list[object]", skeleton_vars)):
        if not isinstance(entry, dict):
            rebuilt.append(entry)
            continue
        variable = dict(cast("dict[str, object]", entry))
        filled_entry = (
            cast("list[object]", filled_vars)[index]
            if index < len(filled_vars)
            else None
        )
        if isinstance(filled_entry, dict):
            filled_var = cast("dict[str, object]", filled_entry)
            description = _str_or_none(filled_var.get("description"))
            if description is not None and description != variable.get("description"):
                variable["description"] = description
            notes.extend(
                _drift_notes(
                    filled_var,
                    variable,
                    ("name", "type", "min", "max", "initial"),
                    f"variables[{index}]",
                )
            )
        rebuilt.append(variable)
    return rebuilt


def normalize_filled_story(
    skeleton: dict[str, object], filled: dict[str, object]
) -> NormalizedFill:
    """Rebuild ``filled`` as the skeleton plus its writable leaf content.

    Args:
        skeleton: The pristine skeleton the fill was commissioned from.
        filled: The parsed model output for that skeleton.

    Returns:
        NormalizedFill: The normalized document, the frozen drifts restored,
        and a skip reason when the graphs cannot be aligned.
    """
    skeleton_nodes = _nodes(skeleton)
    filled_raw = filled.get("nodes")
    # Judge the RAW node list, not a dict-filtered view of it: filtering first
    # would let a response carrying, say, the right number of node objects plus
    # stray strings pass the count check with the garbage silently discarded,
    # laundering malformed output into a valid-looking book. A malformed list
    # is the gate's verdict to deliver, on the document as the model wrote it.
    malformed = 0
    if isinstance(filled_raw, list):
        malformed = sum(
            1
            for entry in cast("list[object]", filled_raw)
            if not isinstance(entry, dict)
        )
    if malformed:
        return NormalizedFill(
            document=filled,
            skipped_reason=(
                f"{malformed} node entr{'y is' if malformed == 1 else 'ies are'} "
                "not JSON objects; malformed output is judged as written, not "
                "repaired by discarding entries"
            ),
        )
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

    notes: list[str] = _story_level_notes(skeleton, filled)
    normalized: dict[str, object] = dict(skeleton)

    title = _str_or_none(filled.get("title"))
    if title is not None:
        normalized["title"] = title
    normalized["variables"] = _overlay_variables(skeleton, filled, notes)

    rebuilt_nodes: list[object] = []
    for skeleton_node, filled_node in zip(skeleton_nodes, filled_nodes, strict=True):
        node_id = skeleton_node.get("id")
        if filled_node.get("id") != node_id:
            notes.append(f"node id {filled_node.get('id')!r} restored to {node_id!r}")
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
    return NormalizedFill(document=normalized, restored=tuple(notes))
