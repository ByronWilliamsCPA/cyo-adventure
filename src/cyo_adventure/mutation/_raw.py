"""Shared raw-document accessors for the mutation package.

These three helpers read the loosely typed raw skeleton document (its nodes,
each node's choices, and string-valued fields) defensively, skipping any
malformed entries. They were duplicated verbatim across several mutation
modules; centralizing them keeps that single reading discipline in one place.

The module is pure (standard library and typing only) and imports nothing from
other mutation modules, so any of them can import it without an import cycle.
The module name is underscore-prefixed to mark it internal to the package; the
helpers carry public names so importers do not reach across a module boundary
for a private symbol (they alias them to the local ``_``-prefixed names they
already use).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Mapping


def nodes_of(story: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return the story's node dicts, skipping any malformed entries.

    Args:
        story: The raw story document.

    Returns:
        list[Mapping[str, object]]: Every well-formed node dict, in file order.
    """
    raw = story.get("nodes")
    if not isinstance(raw, list):
        return []
    return [
        cast("Mapping[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    ]


def choices_of(node: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return a node's choice dicts, skipping any malformed entries."""
    raw = node.get("choices")
    if not isinstance(raw, list):
        return []
    return [
        cast("Mapping[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    ]


def str_field(container: Mapping[str, object], key: str) -> str | None:
    """Return a string-valued field of a mapping, or None when not a string."""
    value = container.get(key)
    return value if isinstance(value, str) else None
