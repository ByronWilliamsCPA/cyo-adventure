"""The three slotted authoring surfaces of a skeleton, enumerated once.

WS-2 fixes exactly three places in a skeleton where a ``{SLOT}`` token may
legally appear: the ``beats='...'`` guidance inside a ``<<FILL ...>>`` node
body, an ending's ``title``, and a choice's ``label``
(``docs/planning/ws2-parameterized-catalog-design.md`` section 4). Four
call sites had each grown their own walk over those surfaces:
:mod:`cyo_adventure.generation.binding` (to collect declared tokens and to
substitute values), :mod:`cyo_adventure.mutation.contract_gate` (which said
so in its own docstring: "Reimplements
``generation.binding._slotted_surface_tokens``"), ``scripts/
parameterize_skeleton.py``, and :mod:`cyo_adventure.mutation.bundle`.

Four copies of "what counts as a slotted surface" is how a surface gets
checked by one pass and missed by another, which is exactly the shape of the
A21 defect: 273 retired-theme proper nouns sat in beats, ending titles, and
choice labels that the acceptance suite walked for *tokens* but never for
*text*. This module is the single definition, and it lives in the pure
``storybook`` layer so the validator can import it without inverting the
established ``generation -> validator -> storybook`` direction.

The request- and validation-path copies (``generation.binding`` and
``mutation.contract_gate``) now delegate here, and the A21 residual-leak scan
added alongside this module (:mod:`cyo_adventure.validator.theme_leak`)
consumes it from the start rather than ever having been a fifth copy. The two
offline catalog tools, ``scripts/parameterize_skeleton.py`` and
:mod:`cyo_adventure.mutation.bundle`, still carry their own walk; neither
gates a child-facing fill, so they are tracked as the remaining un-unified
surfaces rather than blocked on here.

Deliberately dependency-light: stdlib plus
:data:`cyo_adventure.storybook.theme_contract.SLOT_TOKEN_RE` only. It walks
raw decoded JSON rather than a validated model, because both the migration
tooling and the drift guard need to read a skeleton *before* deciding whether
it is well-formed; schema validity is the gate's job, not this walker's, so a
malformed node is skipped rather than raised on.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, NamedTuple, cast

from cyo_adventure.storybook.theme_contract import SLOT_TOKEN_RE

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

__all__ = [
    "FILL_DIRECTIVE_RE",
    "SlottedSurface",
    "iter_slotted_surfaces",
    "slot_tokens_in_surfaces",
]

# The production FILL directive parse. Previously copied into
# `generation/binding.py`, `mutation/contract_gate.py` and
# `scripts/parameterize_skeleton.py`; matches `generation/templates/fill.md`
# and the words-target parse in `validator/policy.py`. DOTALL so a beats
# segment containing a newline still matches as one group.
FILL_DIRECTIVE_RE = re.compile(
    r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$", re.DOTALL
)

SurfaceKind = Literal["beats", "title", "label"]


class SlottedSurface(NamedTuple):
    """One piece of authored text that may legally carry ``{SLOT}`` tokens.

    Attributes:
        kind: Which of the three legal surfaces this is.
        node_id: The owning node's ``id``, or ``""`` when the node has no
            usable string id (a malformed skeleton mid-migration).
        choice_id: For ``kind == "label"``, the owning choice's ``id``;
            ``None`` for the other two kinds.
        text: The raw authored text, exactly as it sits on disk. For
            ``kind == "beats"`` this is the inner ``beats='...'`` group only,
            never the surrounding ``<<FILL ...>>`` wrapper, so a caller
            scanning for stray words cannot trip on ``role`` or ``words``.
    """

    kind: SurfaceKind
    node_id: str
    choice_id: str | None
    text: str

    @property
    def location(self) -> str:
        """Return a stable human-readable location for messages and reports.

        Returns:
            str: ``"<node_id>"`` for a beats or title surface,
                ``"<node_id>/<choice_id>"`` for a choice label.
        """
        return f"{self.node_id}/{self.choice_id}" if self.choice_id else self.node_id


def _as_list(value: object) -> list[object] | None:
    """Narrow ``value`` to ``list[object]``, or ``None`` when it is not a list.

    Args:
        value: Any raw-JSON value.

    Returns:
        list[object] | None: ``value`` narrowed, or ``None``.
    """
    return cast("list[object]", value) if isinstance(value, list) else None


def _as_mapping(value: object) -> dict[str, object] | None:
    """Narrow ``value`` to ``dict[str, object]``, or ``None`` when not a dict.

    Args:
        value: Any raw-JSON value.

    Returns:
        dict[str, object] | None: ``value`` narrowed, or ``None``.
    """
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _str_or_empty(value: object) -> str:
    """Return ``value`` when it is a string, else ``""``.

    Args:
        value: Any raw-JSON value.

    Returns:
        str: The string, or ``""`` for any non-string (including ``None``).
    """
    return value if isinstance(value, str) else ""


def _node_surfaces(node: Mapping[str, object]) -> Iterator[SlottedSurface]:
    """Yield the slotted surfaces belonging to one raw node.

    Args:
        node: One raw node mapping.

    Yields:
        SlottedSurface: The node's beats guidance (when its body is a FILL
            directive), its ending title (when it has one), and one entry per
            choice label. Surfaces whose text is absent or not a string are
            skipped; a caller can only report on text that exists.
    """
    node_id = _str_or_empty(node.get("id"))

    body = _str_or_empty(node.get("body"))
    fill = FILL_DIRECTIVE_RE.match(body) if body else None
    if fill is not None:
        yield SlottedSurface("beats", node_id, None, fill.group(3))

    ending = _as_mapping(node.get("ending"))
    if ending is not None:
        title = _str_or_empty(ending.get("title"))
        if title:
            yield SlottedSurface("title", node_id, None, title)

    for raw_choice in _as_list(node.get("choices")) or ():
        choice = _as_mapping(raw_choice)
        if choice is None:
            continue
        label = _str_or_empty(choice.get("label"))
        if label:
            yield SlottedSurface(
                "label", node_id, _str_or_empty(choice.get("id")) or None, label
            )


def iter_slotted_surfaces(skeleton: Mapping[str, object]) -> Iterator[SlottedSurface]:
    """Yield every slotted authoring surface in a raw skeleton, in document order.

    Args:
        skeleton: The raw skeleton mapping (or a bound copy of one).

    Yields:
        SlottedSurface: Each beats guidance, ending title, and choice label.
            A non-dict entry in ``nodes``, or a missing/non-list ``nodes``,
            yields nothing rather than raising: this walker runs on
            mid-migration documents, and schema validity belongs to the gate.
    """
    for raw_node in _as_list(skeleton.get("nodes")) or ():
        node = _as_mapping(raw_node)
        if node is not None:
            yield from _node_surfaces(node)


def slot_tokens_in_surfaces(skeleton: Mapping[str, object]) -> frozenset[str]:
    """Return every ``{SLOT}`` id referenced across the three legal surfaces.

    Args:
        skeleton: The raw skeleton mapping to scan.

    Returns:
        frozenset[str]: The set of slot ids referenced anywhere in the
            skeleton's beats guidance, ending titles, or choice labels.
    """
    return frozenset(
        token
        for surface in iter_slotted_surfaces(skeleton)
        for token in SLOT_TOKEN_RE.findall(surface.text)
    )
