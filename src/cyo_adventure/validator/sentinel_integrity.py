"""Sentinel-integrity checks for story personalization (ADR-023, plan section 3).

A personalizable slot's value is sentinel-wrapped by ``render_bound_skeleton``
(`cyo_adventure.storybook.sentinels.wrap`) before it reaches the fill LLM;
the fill step is expected to copy each sentinel verbatim into finished prose.
This module provides the deterministic, PURE post-fill checks that verify a
filled blob carries exactly the sentinels its pre-fill skeleton declared, and
nothing forged.

Two variants, for two different call sites (Task 4 wires both; this module
only builds the mechanism):

- `check_sentinel_integrity` (Variant A, plan 3.2): the full check. Needs the
  pre-fill skeleton as a reference, so it can assert per-node expected/actual
  set equality. Used by the worker/import/repair paths, which always have
  the pre-fill skeleton on hand.
- `check_sentinel_integrity_at_rest` (Variant B, plan 3.3): a weaker,
  blob-only check. Rescreen re-reads a PUBLISHED blob with no pre-fill
  reference, so it cannot assert expected-set equality; it can only detect
  corruption-at-rest (an unknown slot id, a malformed near-miss, or a
  sentinel that leaked into a choice label). A rescreen that rewrites
  nothing can still fail this check (plan 3.3): that is a detection signal,
  not a bug.

This module is NOT part of `cyo_adventure.validator.gate.run_gate`: that gate
takes a single blob and has no pre-fill reference, and the full check
fundamentally needs two inputs. All sentinel-format regex knowledge stays in
`cyo_adventure.storybook.sentinels` (plan risk R9); this module imports
`find_sentinels` and `find_malformed_sentinels` from there rather than
re-deriving any pattern.

**Violation location convention** (this module's own design decision, since
the two variants have different scoping guarantees):

- A violation naturally scoped to one node (a dropped, forged, or migrated
  token in a node body or ending title) carries that node's real id.
- A violation found inside a choice label (`"in_choice_label"`, or a
  malformed near-miss located in a label) always uses the fixed placeholder
  ``"<choice-label>"``, regardless of which node the choice belongs to:
  choice labels must never carry sentinel content at all (Task 2), so
  pinpointing the owning node adds no actionable detail over "a choice
  label somewhere in this blob".
- Every Variant B violation that is not a choice-label finding uses the
  fixed placeholder ``"<global>"``, because Variant B has no pre-fill
  reference to scope a finding to "the node where content changed"; it can
  only say "somewhere in this published blob".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from cyo_adventure.storybook.sentinels import (
    find_malformed_sentinels,
    find_sentinels,
    wrap,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

# Fixed location placeholders (see module docstring, "Violation location
# convention").
_CHOICE_LABEL_LOCATION = "<choice-label>"
_GLOBAL_LOCATION = "<global>"

# A sentinel token, represented as its (slot_id, value) pair. Per plan 3.2,
# comparing full canonical tokens (equivalently, this pair) gives
# byte-exactness for free: two tokens are equal only if both the slot id and
# the inner value match exactly.
_Token = tuple[str, str]

# One surface reading: (surface kind, owning node id or None, raw text).
# Surface kind is one of "body", "ending_title", "choice_label".
_Surface = tuple[str, "str | None", str]


@dataclass(frozen=True, slots=True)
class IntegrityViolation:
    """A single sentinel-integrity violation.

    Attributes:
        node_id: The node id that owns this violation, or one of the fixed
            location placeholders ``"<choice-label>"`` / ``"<global>"`` where
            node-scoping does not apply (see the module docstring's
            "Violation location convention").
        kind: The violation kind. One of ``"forged"`` (a token present in a
            node's actual set that no node declared anywhere), ``"migrated"``
            (a token expected in one node but found, unmutated, in another;
            reported once on each of the two nodes), ``"dropped"`` (a token
            declared by the pre-fill skeleton but absent from the filled
            blob), ``"malformed"`` (a sentinel-shaped near-miss; see
            `cyo_adventure.storybook.sentinels.find_malformed_sentinels`),
            ``"unknown_slot"`` (Variant B only: a well-formed sentinel whose
            slot id is not a declared personalizable slot of this story), or
            ``"in_choice_label"`` (a well-formed sentinel found in a choice
            label, which must never carry one).
        token: The offending token or text: the full canonical sentinel
            string (``{~SLOTID:Value~}``) for a well-formed token, or the raw
            near-miss substring for a malformed one.
    """

    node_id: str
    kind: str
    token: str


@dataclass(frozen=True, slots=True)
class IntegrityResult:
    """The outcome of a sentinel-integrity check (full or at-rest).

    Attributes:
        ok: True when zero violations were found. The consumer (Task 4)
            fails closed on ``not ok``.
        violations: Every violation found, in the order the checker
            discovered them; empty when ``ok`` is True. The checker collects
            every violation rather than stopping at the first (plan 3.2).
    """

    ok: bool
    violations: list[IntegrityViolation]


# ---------------------------------------------------------------------------
# Raw-JSON narrowing and blob walking
# ---------------------------------------------------------------------------


def _as_list_object(value: object) -> list[object] | None:
    """Narrow ``value`` to ``list[object]``, or ``None`` when it is not a list.

    Args:
        value: Any raw-JSON value.

    Returns:
        ``value`` cast to ``list[object]``, or ``None``.
    """
    return cast("list[object]", value) if isinstance(value, list) else None


def _as_dict_str_object(value: object) -> dict[str, object] | None:
    """Narrow ``value`` to ``dict[str, object]``, or ``None`` when not a dict.

    Args:
        value: Any raw-JSON value.

    Returns:
        ``value`` cast to ``dict[str, object]``, or ``None``.
    """
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _iter_nodes(blob: Mapping[str, object]) -> Iterator[dict[str, object]]:
    """Yield every node dict in a raw story mapping.

    Args:
        blob: A raw story mapping (a pre-fill skeleton or a filled blob).

    Yields:
        Each node as a ``dict[str, object]``. Non-dict entries in a malformed
        ``nodes`` list are silently skipped; schema validity is the
        deterministic validation gate's job, not this walker's.
    """
    nodes = _as_list_object(blob.get("nodes"))
    if nodes is None:
        return
    for raw_node in nodes:
        node = _as_dict_str_object(raw_node)
        if node is not None:
            yield node


def _node_id_of(node: dict[str, object]) -> str | None:
    """Return a node's id if it is a string, else ``None``.

    Args:
        node: One raw node dict.

    Returns:
        The node's ``id``, or ``None`` if absent or not a string (a
        defensive case; schema validity is the gate's job, not this
        walker's).
    """
    raw_node_id = node.get("id")
    return raw_node_id if isinstance(raw_node_id, str) else None


def _body_surface(node: dict[str, object], node_id: str | None) -> Iterator[_Surface]:
    """Yield the node's body as a ``"body"`` surface, if it is a string.

    Args:
        node: One raw node dict.
        node_id: That node's id (or ``None``), pre-resolved by the caller.

    Yields:
        One ``("body", node_id, body)`` tuple, or nothing.
    """
    body = node.get("body")
    if isinstance(body, str):
        yield ("body", node_id, body)


def _ending_title_surface(
    node: dict[str, object], node_id: str | None
) -> Iterator[_Surface]:
    """Yield the node's ending title as an ``"ending_title"`` surface.

    Args:
        node: One raw node dict.
        node_id: That node's id (or ``None``), pre-resolved by the caller.

    Yields:
        One ``("ending_title", node_id, title)`` tuple, or nothing when the
        node has no ``ending`` block or its ``title`` is not a string.
    """
    ending = _as_dict_str_object(node.get("ending"))
    if ending is None:
        return
    title = ending.get("title")
    if isinstance(title, str):
        yield ("ending_title", node_id, title)


def _choice_label_surfaces(
    node: dict[str, object], node_id: str | None
) -> Iterator[_Surface]:
    """Yield each of the node's choice labels as a ``"choice_label"`` surface.

    Args:
        node: One raw node dict.
        node_id: That node's id (or ``None``), pre-resolved by the caller.

    Yields:
        One ``("choice_label", node_id, label)`` tuple per choice whose
        ``label`` is a string; nothing when the node has no ``choices`` list.
    """
    choices = _as_list_object(node.get("choices"))
    if choices is None:
        return
    for raw_choice in choices:
        choice = _as_dict_str_object(raw_choice)
        if choice is None:
            continue
        label = choice.get("label")
        if isinstance(label, str):
            yield ("choice_label", node_id, label)


def _iter_surfaces(blob: Mapping[str, object]) -> Iterator[_Surface]:
    """Yield every sentinel-bearing surface in a blob, tagged by kind and node id.

    The three surfaces are exactly the ones sentinels can legally (bodies,
    ending titles) or illegally (choice labels) appear in.

    Args:
        blob: A raw story mapping (a pre-fill skeleton or a filled blob).

    Yields:
        ``(surface, node_id, text)`` for every node body, ending title, and
        choice label found. ``surface`` is one of ``"body"``,
        ``"ending_title"``, or ``"choice_label"``. ``node_id`` is the owning
        node's id, or ``None`` if the node has no string id.
    """
    for node in _iter_nodes(blob):
        node_id = _node_id_of(node)
        yield from _body_surface(node, node_id)
        yield from _ending_title_surface(node, node_id)
        yield from _choice_label_surfaces(node, node_id)


def _node_token_map(blob: Mapping[str, object]) -> dict[str, frozenset[_Token]]:
    """Return each node's distinct sentinel token set (body and ending title only).

    Choice labels are deliberately excluded here: they are never a legal home
    for a sentinel (Task 2), so they are checked separately, not folded into
    the per-node expected/actual comparison.

    Args:
        blob: A raw story mapping (a pre-fill skeleton or a filled blob).

    Returns:
        dict[str, frozenset[_Token]]: Node id to the distinct
            ``(slot_id, value)`` tokens found in that node's body and ending
            title, unioned. A node with no sentinels still appears in the
            returned mapping, mapped to an empty ``frozenset`` (via
            ``setdefault``); `_diff_by_node` treats a missing key and an
            empty set identically, so this is harmless, not a guarantee of
            absence.
    """
    tokens_by_node: dict[str, set[_Token]] = {}
    for surface, node_id, text in _iter_surfaces(blob):
        if surface == "choice_label" or node_id is None:
            continue
        tokens_by_node.setdefault(node_id, set()).update(find_sentinels(text))
    return {node_id: frozenset(tokens) for node_id, tokens in tokens_by_node.items()}


# ---------------------------------------------------------------------------
# Shared violation builders
# ---------------------------------------------------------------------------


def _malformed_violations(text: str, location: str) -> list[IntegrityViolation]:
    """Build a ``"malformed"`` violation for every near-miss found in ``text``.

    Args:
        text: The surface text to scan.
        location: The location to attribute each violation to.

    Returns:
        One violation per near-miss found; empty if none.
    """
    return [
        IntegrityViolation(node_id=location, kind="malformed", token=near_miss)
        for near_miss in find_malformed_sentinels(text)
    ]


def _choice_label_sentinel_violations(
    text: str, location: str
) -> list[IntegrityViolation]:
    """Build an ``"in_choice_label"`` violation for every sentinel in ``text``.

    Args:
        text: A choice label's text.
        location: The location to attribute each violation to.

    Returns:
        One violation per well-formed sentinel found; empty if none.
    """
    return [
        IntegrityViolation(
            node_id=location, kind="in_choice_label", token=wrap(slot_id, value)
        )
        for slot_id, value in find_sentinels(text)
    ]


# ---------------------------------------------------------------------------
# Variant A: check_sentinel_integrity
# ---------------------------------------------------------------------------


def _diff_by_node(
    expected_by_node: dict[str, frozenset[_Token]],
    actual_by_node: dict[str, frozenset[_Token]],
) -> tuple[dict[str, frozenset[_Token]], dict[str, frozenset[_Token]], list[str]]:
    """Compute the per-node dropped and forged token sets.

    Args:
        expected_by_node: Node id to expected token set (from the pre-fill
            skeleton).
        actual_by_node: Node id to actual token set (from the filled blob).

    Returns:
        A ``(dropped_by_node, forged_by_node, node_order)`` triple.
        ``node_order`` lists every node id that appears in either input, in
        first-seen order, and only includes an entry in ``dropped_by_node``
        or ``forged_by_node`` when that node has at least one such token.
    """
    dropped_by_node: dict[str, frozenset[_Token]] = {}
    forged_by_node: dict[str, frozenset[_Token]] = {}
    node_order = list(dict.fromkeys([*expected_by_node, *actual_by_node]))
    for node_id in node_order:
        expected = expected_by_node.get(node_id, frozenset())
        actual = actual_by_node.get(node_id, frozenset())
        dropped = expected - actual
        forged = actual - expected
        if dropped:
            dropped_by_node[node_id] = dropped
        if forged:
            forged_by_node[node_id] = forged
    return dropped_by_node, forged_by_node, node_order


def _find_migrated_tokens(
    dropped_by_node: dict[str, frozenset[_Token]],
    forged_by_node: dict[str, frozenset[_Token]],
) -> set[_Token]:
    """Find every dropped token that reappears, unmutated, in another node.

    A dropped token that shows up as a forged token in a *different* node is
    a migration, not an independent drop-and-forge pair.

    Args:
        dropped_by_node: Node id to its dropped token set.
        forged_by_node: Node id to its forged token set.

    Returns:
        The set of tokens that migrated from one node to another.
    """
    migrated: set[_Token] = set()
    for node_id, dropped in dropped_by_node.items():
        for token in dropped:
            for other_node_id, forged in forged_by_node.items():
                if other_node_id != node_id and token in forged:
                    migrated.add(token)
                    break
    return migrated


def _set_diff_violations(
    node_order: list[str],
    dropped_by_node: dict[str, frozenset[_Token]],
    forged_by_node: dict[str, frozenset[_Token]],
    migrated_tokens: set[_Token],
) -> list[IntegrityViolation]:
    """Build the dropped/forged/migrated violations for every node.

    Args:
        node_order: Every node id to report on, in order.
        dropped_by_node: Node id to its dropped token set.
        forged_by_node: Node id to its forged token set.
        migrated_tokens: Tokens identified as migrated (see
            `_find_migrated_tokens`); these are reported as ``"migrated"``
            instead of ``"dropped"``/``"forged"``.

    Returns:
        The violations, node by node, dropped before forged within a node.
    """
    violations: list[IntegrityViolation] = []
    for node_id in node_order:
        for token in sorted(dropped_by_node.get(node_id, frozenset())):
            kind = "migrated" if token in migrated_tokens else "dropped"
            violations.append(
                IntegrityViolation(node_id=node_id, kind=kind, token=wrap(*token))
            )
        for token in sorted(forged_by_node.get(node_id, frozenset())):
            kind = "migrated" if token in migrated_tokens else "forged"
            violations.append(
                IntegrityViolation(node_id=node_id, kind=kind, token=wrap(*token))
            )
    return violations


def _location_for_full_check(surface: str, node_id: str | None) -> str | None:
    """Resolve the violation location for a Variant A surface reading.

    Args:
        surface: The surface kind (``"body"``, ``"ending_title"``, or
            ``"choice_label"``).
        node_id: The owning node's id, or ``None``.

    Returns:
        ``_CHOICE_LABEL_LOCATION`` for a choice label; otherwise ``node_id``
        (which may be ``None`` when the node has no string id, in which case
        the caller must skip this surface).
    """
    if surface == "choice_label":
        return _CHOICE_LABEL_LOCATION
    return node_id


def _surface_violations_full(
    filled_blob: Mapping[str, object],
) -> list[IntegrityViolation]:
    """Build checks 3 and 4 (malformed near-misses, sentinels in choice labels).

    Args:
        filled_blob: The raw filled blob mapping.

    Returns:
        Every malformed-near-miss and in-choice-label violation found across
        the whole blob.
    """
    violations: list[IntegrityViolation] = []
    for surface, node_id, text in _iter_surfaces(filled_blob):
        location = _location_for_full_check(surface, node_id)
        if location is None:
            continue
        violations.extend(_malformed_violations(text, location))
        if surface == "choice_label":
            violations.extend(_choice_label_sentinel_violations(text, location))
    return violations


def check_sentinel_integrity(
    pre_fill_skeleton: Mapping[str, object],
    filled_blob: Mapping[str, object],
) -> IntegrityResult:
    """Check that a filled blob carries exactly the sentinels its pre-fill declared.

    Derives the EXPECTED per-node sentinel set from ``pre_fill_skeleton``
    (the sentinels a personalizable-slot render placed in each node's body
    and, for an ending node, its ending title) and compares it to the ACTUAL
    per-node sentinel set from ``filled_blob``. Nodes are matched by node id.

    Four checks run, and every failure is collected as a distinct violation
    (this function never stops at the first):

    1. Per node, ACTUAL distinct-token set == EXPECTED distinct-token set (a
       set, not a multiset: a sentinel recurring twice in prose is fine, per
       the "at least once" producer contract). A token in actual-but-not-
       expected for a node is reported as ``"forged"`` unless that same
       token was also dropped from a different node, in which case both the
       drop and the reappearance are reported as ``"migrated"`` (a stronger,
       more specific signal than a blind forge). A token in
       expected-but-not-actual is reported as ``"dropped"``.
    2. Byte-exactness is implied by (1): a token whose inner value was
       "improved" or whose slot id changed, while remaining well-formed, is
       simply not equal to any expected token and is caught by (1) (see
       `IntegrityViolation.kind` for the dropped+forged pair this produces).
    3. No sentinel-shaped-but-malformed near-miss appears anywhere in the
       filled blob (any node body, ending title, or choice label); see
       `cyo_adventure.storybook.sentinels.find_malformed_sentinels`.
    4. No well-formed sentinel appears in any choice label.

    Args:
        pre_fill_skeleton: The raw pre-fill skeleton mapping (node bodies
            still carry ``<<FILL ...>>`` directives; sentinels live inside
            the ``beats='...'`` text, which this function scans directly
            without parsing the directive).
        filled_blob: The raw filled blob mapping (node bodies are finished
            prose).

    Returns:
        IntegrityResult: ``ok`` is True only when zero violations were found
            across all four checks.
    """
    expected_by_node = _node_token_map(pre_fill_skeleton)
    actual_by_node = _node_token_map(filled_blob)

    dropped_by_node, forged_by_node, node_order = _diff_by_node(
        expected_by_node, actual_by_node
    )
    migrated_tokens = _find_migrated_tokens(dropped_by_node, forged_by_node)

    violations = _set_diff_violations(
        node_order, dropped_by_node, forged_by_node, migrated_tokens
    )
    violations.extend(_surface_violations_full(filled_blob))

    return IntegrityResult(ok=not violations, violations=violations)


# ---------------------------------------------------------------------------
# Variant B: check_sentinel_integrity_at_rest
# ---------------------------------------------------------------------------


def _unknown_slot_violations(
    text: str, personalizable_slot_ids: frozenset[str]
) -> list[IntegrityViolation]:
    """Build an ``"unknown_slot"`` violation for every non-declared sentinel.

    Args:
        text: A body or ending-title surface's text (never a choice label;
            that surface is checked separately).
        personalizable_slot_ids: The declared personalizable slot ids for
            this story.

    Returns:
        One violation per well-formed sentinel whose slot id is not in
        ``personalizable_slot_ids``; empty if none.
    """
    return [
        IntegrityViolation(
            node_id=_GLOBAL_LOCATION, kind="unknown_slot", token=wrap(slot_id, value)
        )
        for slot_id, value in find_sentinels(text)
        if slot_id not in personalizable_slot_ids
    ]


def _location_for_at_rest_check(surface: str) -> str:
    """Resolve the violation location for a Variant B surface reading.

    Mirrors `_location_for_full_check`'s choice-label awareness so a
    malformed near-miss inside a choice label is tagged `<choice-label>`,
    per the module docstring's "Violation location convention", instead of
    always falling through to the generic `<global>` placeholder.

    Args:
        surface: The surface kind (``"body"``, ``"ending_title"``, or
            ``"choice_label"``).

    Returns:
        `_CHOICE_LABEL_LOCATION` for a choice label; otherwise
        `_GLOBAL_LOCATION`, since Variant B has no pre-fill reference to
        scope a body/ending-title finding more specifically than
        "somewhere in this published blob".
    """
    if surface == "choice_label":
        return _CHOICE_LABEL_LOCATION
    return _GLOBAL_LOCATION


def _surface_violations_at_rest(
    blob: Mapping[str, object],
    personalizable_slot_ids: frozenset[str],
) -> list[IntegrityViolation]:
    """Build every at-rest violation for one surface reading.

    Args:
        blob: The raw published blob mapping.
        personalizable_slot_ids: The declared personalizable slot ids for
            this story.

    Returns:
        Every malformed, in-choice-label, and unknown-slot violation found
        across the whole blob.
    """
    violations: list[IntegrityViolation] = []
    for surface, _node_id, text in _iter_surfaces(blob):
        location = _location_for_at_rest_check(surface)
        violations.extend(_malformed_violations(text, location))
        if surface == "choice_label":
            violations.extend(_choice_label_sentinel_violations(text, location))
        else:
            violations.extend(_unknown_slot_violations(text, personalizable_slot_ids))
    return violations


def check_sentinel_integrity_at_rest(
    blob: Mapping[str, object],
    personalizable_slot_ids: frozenset[str],
) -> IntegrityResult:
    """Check a published blob, with no pre-fill reference, for corruption at rest.

    Rescreen re-reads a PUBLISHED blob and has no pre-fill skeleton, so it
    cannot assert per-node expected/actual set equality the way
    `check_sentinel_integrity` does. This is a deliberately WEAKER contract
    (plan 3.3): it does not assert per-node counts or expected placement, so
    it will not catch a sentinel that is well-formed, declared for this
    story, and outside a choice label, but sitting in the "wrong" node. What
    it does catch is corruption-at-rest:

    - Every well-formed sentinel in the blob has a ``slot_id`` that is a
      member of ``personalizable_slot_ids`` (a sentinel whose slot id is not
      a declared personalizable slot of this story is corruption, reported
      as ``"unknown_slot"``).
    - No sentinel-shaped-but-malformed near-miss appears anywhere in the
      blob (``"malformed"``).
    - No well-formed sentinel appears in any choice label
      (``"in_choice_label"``).

    A rescreen that rewrites nothing can still fail this check (plan 3.3):
    that is a detection signal that the blob was already corrupt at rest, not
    a false positive from this function.

    Args:
        blob: The raw published blob mapping.
        personalizable_slot_ids: The set of slot ids this story declared as
            personalizable at generation time.

    Returns:
        IntegrityResult: ``ok`` is True only when zero violations were found.
    """
    violations = _surface_violations_at_rest(blob, personalizable_slot_ids)
    return IntegrityResult(ok=not violations, violations=violations)
