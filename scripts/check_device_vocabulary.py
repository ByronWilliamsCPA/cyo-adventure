"""Check a narrative contract's device vocabulary against what a series needs.

Usage:
    uv run python scripts/check_device_vocabulary.py <narrative.json>...
        [--books N] [--check]

The upstream feasibility gate the existing device checks assume but never
verify. ``check_bible_diversity.py`` compares kind multisets between bibles
that already exist, and ``check_device_collision.py`` compares props between
books that are already bound; both answer "did these books collide?". Neither
answers the question that determines whether they *could* have avoided it:
given the contract's declared vocabulary, how many books can be bound before
the pigeonhole principle forces a repeat?

That number is a property of the contract alone. An axis that offers ``K``
distinct kinds and spends ``P`` free picks per book runs out after
``floor(K / P)`` books, so book ``floor(K / P) + 1`` must reuse a kind no
matter how the binder is written. When that book number falls inside the
series, a downstream diversity failure is not a binder bug and no amount of
re-binding will fix it; the contract was under-specified before any book was
written. Catching it here costs one JSON read, and catching it downstream
costs a rated round (AL-195: a wasted round is the observed price).

**Frozen kinds are excluded from the headroom, not from the count.** A node
spec carrying ``kind_must_be`` spends that kind in *every* book, so it can
never diverge. Both the free picks and the free kinds shrink by the frozen
set: an axis with 7 kinds, 3 picks and 1 frozen pick has 2 free picks over 6
free kinds, which is 3 books of headroom rather than the 2 a naive
``floor(7 / 3)`` reports. Modelling this wrong understates real capacity and
would drive pointless vocabulary authoring.

**An axis may be frozen on purpose.** Some axes name the story engine rather
than a vocabulary: a single-kind axis whose kind *is* the premise cannot be
widened without authoring a different book. Such an axis declares
``"premise_fixed": true`` with a ``note`` saying why, which exempts it from
the headroom check (DV-6) and nothing else. No shipped contract is in that
state today, so this text deliberately names no contract as its example: an
earlier version cited the 3-5 band's ``obstacle_kinds`` and ``help_modes``,
and went stale the moment those axes were widened in the same change that
introduced this gate.

Checks (all ERROR unless marked):

- DV-0 uncheckable contract: no ``world_recipe.requires`` mapping, so no axis
  can be analysed at all. Reported alone; no other check runs.
- DV-1 unbindable axis: an axis declares ``count`` but enumerates no
  ``kinds``. The binder has nothing to draw from, and because every
  downstream device check keys on the kind, such an axis is invisible to all
  of them: it fails open rather than loudly.
- DV-2 duplicate kinds: a repeated entry inflates the apparent vocabulary,
  so headroom must be computed over distinct kinds.
- DV-3 under-supplied axis: fewer distinct kinds than picks per book. The
  axis cannot fill even ONE book without repeating inside a single story.
- DV-4 envelope breach: a kind absent from ``safety_envelope.
  permitted_device_kinds``, or present in ``forbidden_device_kinds``. NC-5
  checks a *bible* against the envelope; nothing checked the contract's own
  enumerations, so an out-of-envelope kind could be authored into the
  contract and only caught one layer later. An ABSENT permitted list is
  skipped (NC-5 reports the missing envelope); an explicitly empty one is
  enforced, since it declares that nothing is permitted.
- DV-5 declared-vs-consumed: ``count`` must equal the picks the node
  ``invention`` specs actually take from the axis. A ``count`` above the real
  consumption inflates the bible the author is asked to write and the
  headroom this script computes; below it, the bible runs dry at bind time.
- DV-6 series headroom: the forced-repeat book falls at or inside
  ``--books``. Exempt when ``premise_fixed``.
- DV-7 frozen kind not in vocabulary: a ``kind_must_be`` naming a kind the
  axis does not enumerate. The bind can never satisfy it.
- DV-8 uncategorised spec: an ``invention`` spec that omits ``category``.
  ``check_bible_diversity.py --contract`` keys its frozen-kind report on
  ``category`` alone, so a spec without one is silently reported as
  unfrozen; the 3-5 contract's ``testimony`` freeze was invisible to it for
  exactly this reason.
- DV-9 unknown axis (WARNING): a spec drawing ``from`` a
  ``bible.device_vocabulary.*`` path with no matching axis in ``requires``.

Exits 1 under ``--check`` on any ERROR finding; warnings print but never fail.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple, cast

# Picks are read from the node invention specs, whose `from` is a dotted path
# into the bible. Only this prefix names a device axis; `n_start.loss_moment`
# in the 3-5 contract draws from `bible.world.physics_notes + bible.motifs`,
# which is prose inspiration rather than a device axis and must not be counted.
_VOCAB_PREFIX = "bible.device_vocabulary."

# The default series length the headroom check bills against. The shipped
# Wyrmreach series is 3 books; the repulsion rows in the diversity test
# register plan 5 on one skeleton. 5 is the larger bar and subsumes the
# smaller, so a contract that clears it clears both. Override with --books.
_DEFAULT_BOOKS = 5


class Finding(NamedTuple):
    """One check result against one contract.

    Attributes:
        code: The DV-n check identifier.
        severity: ``"ERROR"`` or ``"WARNING"``. Only errors fail ``--check``.
        axis: The device axis the finding is about, or the node/slot path for
            findings that are not axis-scoped.
        message: What is wrong, in terms the contract author can act on.
    """

    code: str
    severity: str
    axis: str
    message: str


class AxisCapacity(NamedTuple):
    """How many books one axis can supply with distinct kinds.

    Attributes:
        axis: The axis name as it appears in ``world_recipe.requires``.
        picks: Picks per book, from the axis's declared ``count``.
        frozen_picks: How many of those picks a ``kind_must_be`` spec pins to
            one kind in every book.
        distinct_kinds: Distinct entries in the axis's ``kinds`` enumeration.
        frozen_kinds: Distinct kinds pinned by ``kind_must_be``.
        premise_fixed: Whether repeating this axis across books is intended.
    """

    axis: str
    picks: int
    frozen_picks: int
    distinct_kinds: int
    frozen_kinds: int
    premise_fixed: bool

    @property
    def free_picks(self) -> int:
        """Picks per book that are actually free to vary.

        Returns:
            Picks not pinned by a ``kind_must_be`` spec, floored at zero.
        """
        return max(0, self.picks - self.frozen_picks)

    @property
    def free_kinds(self) -> int:
        """Kinds available to the free picks.

        Returns:
            Distinct kinds less those a ``kind_must_be`` spec has spent,
            floored at zero.
        """
        return max(0, self.distinct_kinds - self.frozen_kinds)

    @property
    def books_supported(self) -> int | None:
        """How many books this axis can bind with no kind reused across them.

        Returns:
            ``floor(free_kinds / free_picks)``, or ``None`` when the axis has
            no free picks at all. ``None`` is unbounded rather than zero: an
            axis whose every pick is frozen repeats by construction and no
            vocabulary size changes that, so it has nothing to run out of.
        """
        if self.free_picks == 0:
            return None
        return self.free_kinds // self.free_picks

    @property
    def forced_repeat_book(self) -> int | None:
        """The first book that must reuse a kind from an earlier book.

        Returns:
            ``books_supported + 1``, or ``None`` when nothing is free to vary.
        """
        supported = self.books_supported
        return None if supported is None else supported + 1


def _load_contract(path: str) -> dict[str, Any] | None:
    """Load a narrative contract, reporting a readable error on failure.

    Args:
        path: Filesystem path to a ``<slug>.narrative.json`` document.

    Returns:
        The parsed object, or ``None`` when it could not be read or is not a
        JSON object.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot load {path}: {exc}\n")
        return None
    if not isinstance(data, dict):
        sys.stderr.write(f"error: expected a JSON object in {path}\n")
        return None
    return cast("dict[str, Any]", data)


def _axis_of_spec(spec: dict[str, Any]) -> str | None:
    """Return the device axis an invention spec draws from, if any.

    Prefers the explicit ``category`` and falls back to the tail of the
    ``from`` path, so a contract that predates the ``category`` key is still
    accounted for rather than silently contributing zero picks. DV-8 reports
    the omission separately; this function's job is to get the arithmetic
    right either way.

    Args:
        spec: One entry of a node's ``invention`` mapping.

    Returns:
        The axis name, or ``None`` when the spec draws from something that is
        not a device axis.
    """
    category = spec.get("category")
    if isinstance(category, str) and category:
        return category
    source = spec.get("from")
    if isinstance(source, str) and source.startswith(_VOCAB_PREFIX):
        return source[len(_VOCAB_PREFIX) :].strip()
    return None


def _iter_specs(contract: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Flatten every node invention spec into ``(node_id, slot, spec)``.

    Args:
        contract: The parsed narrative contract.

    Returns:
        One triple per invention spec, skipping malformed node or spec
        entries rather than raising: a shape problem in the contract is
        NC-0's finding to report, not this script's.
    """
    specs: list[tuple[str, str, dict[str, Any]]] = []
    nodes = contract.get("nodes")
    if not isinstance(nodes, dict):
        return specs
    for node_id, node in cast("dict[str, Any]", nodes).items():
        if not isinstance(node, dict):
            continue
        invention = cast("dict[str, Any]", node).get("invention")
        if not isinstance(invention, dict):
            continue
        for slot, spec in cast("dict[str, Any]", invention).items():
            if isinstance(spec, dict):
                specs.append((str(node_id), str(slot), cast("dict[str, Any]", spec)))
    return specs


def _pick_count(spec: dict[str, Any]) -> int:
    """Return how many kinds one invention spec consumes.

    Args:
        spec: One entry of a node's ``invention`` mapping.

    Returns:
        The spec's ``pick``, defaulting to 1 and floored at 0. A non-integer
        ``pick`` counts as 1 rather than raising, so a malformed value cannot
        make an axis silently look unconsumed.
    """
    pick = spec.get("pick", 1)
    if isinstance(pick, bool) or not isinstance(pick, int):
        return 1
    return max(0, pick)


def _consumption(
    contract: dict[str, Any],
) -> tuple[dict[str, int], dict[str, int], dict[str, set[str]]]:
    """Summarise what the node specs take from each axis.

    Args:
        contract: The parsed narrative contract.

    Returns:
        ``(picks, frozen_picks, frozen_kinds)`` keyed by axis: total picks
        consumed, picks pinned by ``kind_must_be``, and the distinct kinds
        those pins name.
    """
    picks: dict[str, int] = {}
    frozen_picks: dict[str, int] = {}
    frozen_kinds: dict[str, set[str]] = {}
    for _node_id, _slot, spec in _iter_specs(contract):
        axis = _axis_of_spec(spec)
        if axis is None:
            continue
        count = _pick_count(spec)
        picks[axis] = picks.get(axis, 0) + count
        must = spec.get("kind_must_be")
        if isinstance(must, str) and must:
            frozen_picks[axis] = frozen_picks.get(axis, 0) + count
            frozen_kinds.setdefault(axis, set()).add(must)
    return picks, frozen_picks, frozen_kinds


def _kind_list(axis_config: dict[str, Any]) -> list[str] | None:
    """Return an axis's declared kinds, or ``None`` when it enumerates none.

    Args:
        axis_config: One entry of ``world_recipe.requires``.

    Returns:
        The kinds as strings, or ``None`` when the key is absent or not a
        list. An empty list is returned as an empty list, not ``None``: an
        author who wrote ``"kinds": []`` said something different from one
        who wrote nothing, and DV-3 reports the former more precisely.
    """
    kinds = axis_config.get("kinds")
    if not isinstance(kinds, list):
        return None
    return [str(kind) for kind in cast("list[Any]", kinds)]


def _envelope(contract: dict[str, Any]) -> tuple[set[str] | None, set[str]]:
    """Return the contract's permitted and forbidden device kinds.

    Args:
        contract: The parsed narrative contract.

    Returns:
        ``(permitted, forbidden)``. ``permitted`` is ``None`` when no list was
        declared and a set when one was, so DV-4 can tell "no envelope" from
        an explicit ``[]``. Collapsing both to an empty set made an author who
        wrote ``"permitted_device_kinds": []`` (nothing is permitted) read as
        one who wrote nothing (everything is permitted), which is the inverse
        of what they said and passed every kind silently. This mirrors the
        distinction :func:`_kinds` already draws for DV-3.

        ``forbidden`` needs no such distinction: an absent list and an empty
        one both mean nothing is forbidden.
    """
    envelope = contract.get("safety_envelope")
    if not isinstance(envelope, dict):
        return (None, set())
    envelope_map = cast("dict[str, Any]", envelope)

    def _as_set(key: str) -> set[str] | None:
        value = envelope_map.get(key)
        if not isinstance(value, list):
            return None
        return {str(item) for item in cast("list[Any]", value)}

    return (
        _as_set("permitted_device_kinds"),
        _as_set("forbidden_device_kinds") or set(),
    )


def _declared_count(axis_config: dict[str, Any]) -> int:
    """Return an axis's declared ``count``, or 0 when absent or not an integer.

    DV-3 reads this on one path and DV-5/DV-6 on another. They were separate
    copies of the same expression, so a change to either would have left the
    checks disagreeing about picks per book while both still reported
    confidently.

    Args:
        axis_config: One entry of ``world_recipe.requires``.

    Returns:
        The declared picks per book. A ``bool`` is rejected because it is an
        ``int`` subclass and a ``true`` here is a typo, not a count of one.
    """
    declared = axis_config.get("count")
    if isinstance(declared, bool) or not isinstance(declared, int):
        return 0
    return declared


def _check_axis_kinds(
    axis: str, axis_config: dict[str, Any], kinds: list[str] | None
) -> list[Finding]:
    """Run the enumeration-shape checks (DV-1, DV-2, DV-3) for one axis.

    Args:
        axis: The axis name.
        axis_config: Its entry in ``world_recipe.requires``.
        kinds: Its declared kinds, or ``None`` when it enumerates none.

    Returns:
        Findings for a missing enumeration, duplicate entries, or a
        vocabulary too small to fill one book.
    """
    declared = axis_config.get("count")
    count = _declared_count(axis_config)
    if kinds is None:
        return [
            Finding(
                "DV-1",
                "ERROR",
                axis,
                f"declares count={declared} but enumerates no kinds; the binder "
                f"has nothing to draw from and every kind-keyed device check "
                f"skips this axis silently",
            )
        ]
    findings: list[Finding] = []
    duplicates = sorted({kind for kind in kinds if kinds.count(kind) > 1})
    if duplicates:
        findings.append(
            Finding(
                "DV-2",
                "ERROR",
                axis,
                f"repeats kind(s) {', '.join(duplicates)}; headroom is computed "
                f"over distinct kinds, so a duplicate inflates the apparent "
                f"vocabulary without adding capacity",
            )
        )
    distinct = len(set(kinds))
    if count and distinct < count:
        findings.append(
            Finding(
                "DV-3",
                "ERROR",
                axis,
                f"{distinct} distinct kind(s) for {count} pick(s) per book; the "
                f"axis cannot fill even one book without repeating inside a "
                f"single story",
            )
        )
    return findings


def _check_envelope(
    axis: str, kinds: list[str] | None, permitted: set[str] | None, forbidden: set[str]
) -> list[Finding]:
    """Run DV-4 for one axis against the contract's safety envelope.

    Args:
        axis: The axis name.
        kinds: Its declared kinds, or ``None``.
        permitted: The envelope's permitted device kinds, or ``None`` when the
            contract declared no list at all. An empty set is a declaration
            that nothing is permitted, and is enforced as one.
        forbidden: The envelope's forbidden device kinds.

    Returns:
        One finding per kind outside the envelope.
    """
    if kinds is None:
        return []
    findings: list[Finding] = []
    for kind in sorted(set(kinds)):
        if kind in forbidden:
            findings.append(
                Finding(
                    "DV-4",
                    "ERROR",
                    axis,
                    f"kind {kind!r} is listed in forbidden_device_kinds",
                )
            )
        # An ABSENT permitted list means no envelope was declared, which NC-5
        # reports; treating it as "everything is forbidden" here would bury
        # that one finding under one-per-kind noise. An explicitly empty list
        # is the opposite case and is enforced: the author declared that
        # nothing is permitted, so every kind breaches it.
        elif permitted is not None and kind not in permitted:
            findings.append(
                Finding(
                    "DV-4",
                    "ERROR",
                    axis,
                    f"kind {kind!r} is absent from permitted_device_kinds",
                )
            )
    return findings


def _check_specs(contract: dict[str, Any], requires: dict[str, Any]) -> list[Finding]:
    """Run the spec-level checks (DV-7, DV-8, DV-9).

    Args:
        contract: The parsed narrative contract.
        requires: Its ``world_recipe.requires`` mapping.

    Returns:
        Findings for unsatisfiable frozen kinds, uncategorised specs, and
        specs naming an axis the recipe does not declare.
    """
    findings: list[Finding] = []
    for node_id, slot, spec in _iter_specs(contract):
        axis = _axis_of_spec(spec)
        if axis is None:
            continue
        where = f"{node_id}.{slot}"
        # An empty string must fail here exactly as an absent key does.
        # `_axis_of_spec` requires a NON-empty `category` and otherwise falls
        # back to the `from` path tail, so a spec carrying `"category": ""`
        # still resolves to an axis and would escape DV-8 on a bare
        # `isinstance` test, which is the precise case DV-8 exists to catch.
        category = spec.get("category")
        if not isinstance(category, str) or not category:
            findings.append(
                Finding(
                    "DV-8",
                    "ERROR",
                    axis,
                    f"{where} omits 'category'; check_bible_diversity.py "
                    f"--contract keys its frozen-kind report on that field "
                    f"alone and reports such a spec as unfrozen",
                )
            )
        axis_config = requires.get(axis)
        if not isinstance(axis_config, dict):
            findings.append(
                Finding(
                    "DV-9",
                    "WARNING",
                    axis,
                    f"{where} draws from an axis absent from world_recipe.requires",
                )
            )
            continue
        must = spec.get("kind_must_be")
        kinds = _kind_list(cast("dict[str, Any]", axis_config))
        if isinstance(must, str) and kinds is not None and must not in set(kinds):
            findings.append(
                Finding(
                    "DV-7",
                    "ERROR",
                    axis,
                    f"{where} pins kind_must_be={must!r}, which the axis does "
                    f"not enumerate; no bind can satisfy it",
                )
            )
    return findings


def analyse(
    contract: dict[str, Any], books: int
) -> tuple[list[Finding], list[AxisCapacity]]:
    """Run every check over one narrative contract.

    Args:
        contract: The parsed narrative contract.
        books: The series length the headroom check (DV-6) bills against.

    Returns:
        ``(findings, capacities)``. Capacities are returned for every axis
        that enumerates kinds, so the report can show headroom even for axes
        with no findings.
    """
    recipe = contract.get("world_recipe")
    requires_raw = (
        cast("dict[str, Any]", recipe).get("requires")
        if isinstance(recipe, dict)
        else None
    )
    if not isinstance(requires_raw, dict):
        return (
            [
                Finding(
                    "DV-0",
                    "ERROR",
                    "(contract)",
                    "no world_recipe.requires mapping; nothing to check",
                )
            ],
            [],
        )
    requires = cast("dict[str, Any]", requires_raw)
    permitted, forbidden = _envelope(contract)
    picks, frozen_picks, frozen_kinds = _consumption(contract)

    findings: list[Finding] = list(_check_specs(contract, requires))
    capacities: list[AxisCapacity] = []

    for axis, axis_config_raw in sorted(requires.items()):
        if not isinstance(axis_config_raw, dict):
            continue
        axis_config = cast("dict[str, Any]", axis_config_raw)
        kinds = _kind_list(axis_config)
        findings.extend(_check_axis_kinds(axis, axis_config, kinds))
        findings.extend(_check_envelope(axis, kinds, permitted, forbidden))

        count = _declared_count(axis_config)
        consumed = picks.get(axis, 0)
        if count != consumed:
            findings.append(
                Finding(
                    "DV-5",
                    "ERROR",
                    axis,
                    f"declares count={count} but node invention specs consume "
                    f"{consumed}; the bible is sized to the declared count, so "
                    f"a mismatch either over-orders vocabulary or runs it dry "
                    f"at bind time",
                )
            )
        if kinds is None:
            continue

        premise_fixed = axis_config.get("premise_fixed") is True
        capacity = AxisCapacity(
            axis=axis,
            picks=count,
            frozen_picks=frozen_picks.get(axis, 0),
            distinct_kinds=len(set(kinds)),
            frozen_kinds=len(frozen_kinds.get(axis, set())),
            premise_fixed=premise_fixed,
        )
        capacities.append(capacity)

        repeat_at = capacity.forced_repeat_book
        if not premise_fixed and repeat_at is not None and repeat_at <= books:
            findings.append(
                Finding(
                    "DV-6",
                    "ERROR",
                    axis,
                    f"supports {capacity.books_supported} book(s); book "
                    f"{repeat_at} must reuse a kind ({capacity.free_kinds} free "
                    f"kind(s) over {capacity.free_picks} free pick(s) per book, "
                    f"target {books}). No binder can avoid this; widen kinds or "
                    f"declare premise_fixed with a note if repetition is intended",
                )
            )
    return findings, capacities


def _report(
    path: str, findings: list[Finding], capacities: list[AxisCapacity], books: int
) -> None:
    """Write the per-contract report to stdout.

    Args:
        path: The contract path, used as the report heading.
        findings: Every finding for this contract.
        capacities: Per-axis capacity, for the headroom table.
        books: The series length being billed against.
    """
    sys.stdout.write(f"{Path(path).name} (target {books} books)\n")
    for capacity in capacities:
        repeat_at = capacity.forced_repeat_book
        if capacity.premise_fixed:
            verdict = "premise-fixed"
        elif repeat_at is None:
            verdict = "fully frozen"
        elif repeat_at <= books:
            verdict = f"FAIL repeats at book {repeat_at}"
        else:
            verdict = f"ok, repeats at book {repeat_at}"
        sys.stdout.write(
            f"  {capacity.axis:24} {capacity.distinct_kinds:3} kinds / "
            f"{capacity.picks} pick(s)"
            f"{f' ({capacity.frozen_picks} frozen)' if capacity.frozen_picks else ''}"
            f"  -> {verdict}\n"
        )
    for finding in findings:
        sys.stdout.write(
            f"  {finding.severity} {finding.code} [{finding.axis}]: {finding.message}\n"
        )
    if not findings:
        sys.stdout.write("  no findings\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; exit 1 under ``--check`` when any ERROR is found.

    Args:
        argv: Argument vector, or ``None`` to read ``sys.argv``.

    Returns:
        0 when clean or when ``--check`` was not passed, 1 when ``--check``
        found an error, 2 on a usage or load failure.
    """
    # The module docstring is a 70-line structured list of DV codes. The
    # default formatter reflows it into one unreadable block, so --help would
    # hide the very reference a caller opens it for.
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "contracts", nargs="+", help="One or more <slug>.narrative.json paths."
    )
    parser.add_argument(
        "--books",
        type=int,
        default=_DEFAULT_BOOKS,
        help=(
            "Series length the headroom check bills against "
            f"(default {_DEFAULT_BOOKS})."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when any ERROR is found. Warnings never affect the "
        "exit code. Without this flag the script only reports.",
    )
    args = parser.parse_args(argv)
    if args.books < 1:
        sys.stderr.write(f"error: --books must be at least 1, got {args.books}\n")
        return 2

    errors = 0
    for path in args.contracts:
        contract = _load_contract(path)
        if contract is None:
            return 2
        findings, capacities = analyse(contract, args.books)
        _report(path, findings, capacities, args.books)
        errors += sum(1 for finding in findings if finding.severity == "ERROR")
    if args.check and errors:
        sys.stderr.write(f"\n{errors} error finding(s)\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
