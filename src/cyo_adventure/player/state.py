"""Reading-state snapshot types for the deterministic player.

These mirror the save format in ``docs/planning/runtime-semantics.md`` section 5.
A :class:`ReadingState` is the full save; a :class:`Snapshot` is the playable
position stored in a named save slot. The same :class:`ReadingState` shape is the
payload persisted by the reading-state API (WP4) and the client cache.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cyo_adventure.storybook.evaluator import VarState


@dataclass(slots=True)
class Snapshot:
    """A point-in-time playable position within a story.

    Attributes:
        current_node: The node id the reader is at.
        var_state: The full variable name-to-value map.
        path: Ordered node ids visited from ``start_node`` to ``current_node``.
        visit_set: Node ids entered at least once (drives ``once: true``).
    """

    current_node: str
    var_state: VarState
    path: list[str]
    visit_set: set[str]

    def copy(self) -> Snapshot:
        """Return a deep copy whose mutable containers are independent.

        Returns:
            Snapshot: A snapshot that shares no mutable state with this one, so a
                save slot cannot be mutated through a cloned reading state.
        """
        return Snapshot(
            current_node=self.current_node,
            var_state=dict(self.var_state),
            path=list(self.path),
            visit_set=set(self.visit_set),
        )

    def to_dict(self) -> dict[str, object]:
        """Return the snapshot as a JSON-serializable mapping.

        Returns:
            dict[str, object]: ``visit_set`` is emitted as a sorted list.
        """
        return {
            "current_node": self.current_node,
            "var_state": dict(self.var_state),
            "path": list(self.path),
            "visit_set": sorted(self.visit_set),
        }


@dataclass(slots=True)
class ReadingState:
    """A full save: the live position plus slots, version, and revision.

    Attributes:
        current_node: The node id the reader is at.
        var_state: The full variable name-to-value map.
        path: Ordered node ids visited from ``start_node`` to ``current_node``.
        visit_set: Node ids entered at least once (drives ``once: true``).
        version: The Storybook ``version`` this save was taken against.
        state_revision: The server-side revision counter at save time.
        save_slots: Named save-slot map (slot name to snapshot).
    """

    current_node: str
    var_state: VarState
    path: list[str]
    visit_set: set[str]
    version: int
    state_revision: int = 0
    save_slots: dict[str, Snapshot] = field(default_factory=dict)

    def snapshot(self) -> Snapshot:
        """Return a deep-copied snapshot of the current playable position.

        Returns:
            Snapshot: A copy safe to store in a save slot.
        """
        return Snapshot(
            current_node=self.current_node,
            var_state=dict(self.var_state),
            path=list(self.path),
            visit_set=set(self.visit_set),
        )

    def to_dict(self) -> dict[str, object]:
        """Return the reading state as a JSON-serializable mapping.

        Returns:
            dict[str, object]: The save in the persisted wire format.
        """
        return {
            "current_node": self.current_node,
            "var_state": dict(self.var_state),
            "path": list(self.path),
            "visit_set": sorted(self.visit_set),
            "version": self.version,
            "state_revision": self.state_revision,
            "save_slots": {
                name: snap.to_dict() for name, snap in self.save_slots.items()
            },
        }
