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

Nodes are matched **by id**, never by position: a model that re-emits the
same nodes in a different order is a correct fill whose prose must land on
the right graph positions, and a positional overlay would transplant bodies
and choice labels onto the wrong targets while rebuilding a structurally
perfect document no downstream gate can catch (PR #737 review, finding C2).
Choices are matched by id within their node, and variables by name. A fill
whose node id set does not exactly match the skeleton's (missing, extra,
renamed, or duplicated ids), whose node count differs, or whose raw node
list carries non-object entries is not normalized (returned unchanged),
since overlaying leaves onto a different or malformed graph would fabricate
a book, and the gate owns that verdict. Within a matched node, a choice id
absent from the fill keeps the skeleton's label (noted), and an extra
filled choice id is discarded (noted).
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
    """Return the skeleton node's choices with the fill's label text overlaid.

    # #CRITICAL: data-integrity: choices are matched BY ID, never by
    # position. A model that returns the same choices reordered is a correct
    # fill; a positional overlay would attach each theme-specific label to
    # the OPPOSITE frozen target ("Climb down into the pit" leading to the
    # safe room), and the gate cannot catch it because the rebuilt graph is
    # the skeleton's own by construction (PR #737 review, finding C2).
    # #VERIFY: test_normalize_fill.py::
    # test_reordered_choices_keep_their_labels_on_the_right_targets.
    """
    skeleton_choices = skeleton_node.get("choices")
    if not isinstance(skeleton_choices, list):
        return skeleton_choices
    filled_raw = filled_node.get("choices")
    filled_entries = filled_raw if isinstance(filled_raw, list) else []
    filled_by_id: dict[object, dict[str, object]] = {}
    for entry in cast("list[object]", filled_entries):
        if isinstance(entry, dict):
            filled_by_id[cast("dict[str, object]", entry).get("id")] = cast(
                "dict[str, object]", entry
            )
    matched_ids: set[object] = set()
    rebuilt: list[object] = []
    for entry in cast("list[object]", skeleton_choices):
        if not isinstance(entry, dict):
            rebuilt.append(entry)
            continue
        choice = dict(cast("dict[str, object]", entry))
        choice_id = choice.get("id")
        filled_choice = filled_by_id.get(choice_id)
        if filled_choice is not None:
            matched_ids.add(choice_id)
            label = _str_or_none(filled_choice.get("label"))
            if label is not None:
                choice["label"] = label
            notes.extend(
                _drift_notes(
                    filled_choice,
                    choice,
                    ("target", "condition", "effects"),
                    f"node {node_id!r} choice {choice_id!r}",
                )
            )
        else:
            notes.append(
                f"node {node_id!r} choice {choice_id!r} absent from the fill; "
                "skeleton label kept"
            )
        rebuilt.append(choice)
    notes.extend(
        f"node {node_id!r} fill carries unknown choice id {extra_id!r}; discarded"
        for extra_id in filled_by_id
        if extra_id not in matched_ids
    )
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
    """Return the skeleton's variables with the fill's descriptions overlaid.

    # #ASSUME: data-integrity: variables are matched by NAME, not position,
    # for the same reason nodes and choices are matched by id: a reordered
    # variables list must not put one variable's themed description on
    # another (PR #737 review, finding C2's variable-level sibling). A name
    # absent from the fill keeps the skeleton description; an unknown name
    # is discarded with a note.
    # #VERIFY: test_normalize_fill.py::
    # test_reordered_variables_keep_their_descriptions.
    """
    skeleton_vars = skeleton.get("variables")
    if not isinstance(skeleton_vars, list):
        return skeleton_vars
    filled_raw = filled.get("variables")
    filled_entries = filled_raw if isinstance(filled_raw, list) else []
    filled_by_name: dict[object, dict[str, object]] = {}
    for entry in cast("list[object]", filled_entries):
        if isinstance(entry, dict):
            filled_by_name[cast("dict[str, object]", entry).get("name")] = cast(
                "dict[str, object]", entry
            )
    matched_names: set[object] = set()
    rebuilt: list[object] = []
    for entry in cast("list[object]", skeleton_vars):
        if not isinstance(entry, dict):
            rebuilt.append(entry)
            continue
        variable = dict(cast("dict[str, object]", entry))
        name = variable.get("name")
        filled_var = filled_by_name.get(name)
        if filled_var is not None:
            matched_names.add(name)
            description = _str_or_none(filled_var.get("description"))
            if description is not None and description != variable.get("description"):
                variable["description"] = description
            notes.extend(
                _drift_notes(
                    filled_var,
                    variable,
                    ("type", "min", "max", "initial"),
                    f"variable {name!r}",
                )
            )
        rebuilt.append(variable)
    notes.extend(
        f"fill carries unknown variable {extra_name!r}; discarded"
        for extra_name in filled_by_name
        if extra_name not in matched_names
    )
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
    # #CRITICAL: data-integrity: nodes are paired BY ID, and a fill whose id
    # set does not exactly match the skeleton's is not normalized at all. A
    # positional zip inverted prose against the frozen graph on a
    # reordered-but-correct fill (each body and label landing on the wrong
    # node while ids were "restored"), producing a structurally perfect
    # document the gate cannot reject because the graph it validates is the
    # skeleton's own by construction (PR #737 review, finding C2, reproduced
    # by three reviewers). Missing, renamed, or duplicated ids make the
    # pairing ambiguous, so those fills go to the gate as written.
    # #VERIFY: test_normalize_fill.py::
    # test_reordered_nodes_keep_their_prose_on_the_right_graph_positions and
    # ::test_a_fill_with_renamed_node_ids_is_not_normalized.
    skeleton_ids = [node.get("id") for node in skeleton_nodes]
    filled_by_id: dict[object, dict[str, object]] = {
        node.get("id"): node for node in filled_nodes
    }
    if len(filled_by_id) != len(filled_nodes) or set(filled_by_id) != set(skeleton_ids):
        return NormalizedFill(
            document=filled,
            skipped_reason=(
                "node ids do not align with the skeleton (missing, renamed, "
                "or duplicated); pairing would be ambiguous, so the fill is "
                "judged as written"
            ),
        )

    notes: list[str] = _story_level_notes(skeleton, filled)
    normalized: dict[str, object] = dict(skeleton)

    title = _str_or_none(filled.get("title"))
    if title is not None:
        normalized["title"] = title
    normalized["variables"] = _overlay_variables(skeleton, filled, notes)

    rebuilt_nodes: list[object] = []
    for skeleton_node in skeleton_nodes:
        node_id = skeleton_node.get("id")
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
    return NormalizedFill(document=normalized, restored=tuple(notes))
