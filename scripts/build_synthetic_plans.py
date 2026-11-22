#!/usr/bin/env python3
# pyright: reportImplicitStringConcatenation=false
# Ruff ISC003 requires implicit concatenation for wrapped messages and this
# BasedPyright rule forbids it; the two conflict, and Ruff is the project's gate.
"""Build the synthetic seeded-defect plan set for the plan reviewer (WP-3.7, D12).

Owner decision D12 (as amended 2026-11-21) lets the plan reviewer's validation
set be supplemented with plans seeded with one defect each, **reported
separately as synthetic**. This builder writes that set, deterministically,
from committed files only (no model call, no network, no randomness):

* ``docs/planning/evidence/plan-reviewer/synthetic/<id>.plan.json``: one seeded
  plan per item;
* ``docs/planning/evidence/plan-reviewer/synthetic/validation-set.synthetic.json``:
  the items, schema ``validation-set-synthetic/v1``.

The set is never merged into
``docs/planning/evidence/continuity-reader/validation-set.json`` or into any
recall figure computed from it. Two families, reported apart from each other:

* **Family A, checker-visible.** One property change per WP-1.2 rule witness
  (``WITNESSES`` in ``cyo_adventure.storyplan.checks``; SP-0 excluded), moved
  onto a real clean plan. The seed must trip **exactly its intended rule** when
  run through ``check_plan``, the function ``verify_witnesses`` uses.
* **Family B, checker-invisible.** A hand-designed defect the deterministic
  checks cannot see (B1 a choice whose intent contradicts its outcome, B2 a fact
  that contradicts the truth with no ``contradicts`` mark, B3 an ending gift that
  contradicts its valence or the truth, B4 a payoff ``shows`` that does not match
  its planted choice). The seed must pass ``check_plan`` with **no ERROR**.

Sources are the validation set's clean held-out plans (``expected_verdict`` of
``pass``, ``label_strength`` of ``strong``, the e and f plans of the five fixed
books) and the two tuning clean plans. A held-out source seeds only held-out
items and a tuning source only tuning items. Museum's minor-only plans (post-fix,
c1, d3) are never sources. See the README beside the output for the method.

Usage:
    uv run python scripts/build_synthetic_plans.py            # write
    uv run python scripts/build_synthetic_plans.py --check    # exit 1 on drift
    uv run python scripts/build_synthetic_plans.py --summary  # print the counts

Exit codes: 0 ok; 1 drift or a seed that breaks its family rule; 2 a pinned
revision missing from this checkout.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess  # nosec B404 - fixed argv, no shell, used only for git show
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from cyo_adventure.storybook.models import Ending, Storybook, Valence
from cyo_adventure.storyplan.checks import WITNESSES, PlanFinding, check_plan
from cyo_adventure.storyplan.models import StoryPlan, book_sha256

if TYPE_CHECKING:
    from cyo_adventure.validator.report import ValidationReport

REPO: Final = Path(__file__).resolve().parents[1]
VALIDATION_SET: Final = (
    REPO / "docs/planning/evidence/continuity-reader/validation-set.json"
)
OUT_DIR: Final = REPO / "docs/planning/evidence/plan-reviewer/synthetic"
OUT_FILE: Final = OUT_DIR / "validation-set.synthetic.json"
README_LINK: Final = "docs/planning/evidence/plan-reviewer/synthetic/README.md"
SCHEMA: Final = "validation-set-synthetic/v1"
SCORED_FOR: Final = "D12-synthetic"

EXIT_OK: Final = 0
EXIT_FAIL: Final = 1
EXIT_NO_REVISION: Final = 2

TUNING: Final = "tuning"
HELD_OUT: Final = "held_out"

#: Seeds are drawn by deterministic search over a fixed ordering, so no random
#: number generator is used. The split seed is recorded only so a reader can tie
#: this set to the split it respects; it is never fed to a generator.
SPLIT_SEED: Final = "990054da2cc73d8b2b4c6b5744dc197288c40213"

#: Family A: no rule may supply more than this many seeds in one half.
MAX_SEEDS_PER_RULE: Final = 2
#: Candidate edits tried per seed before the build gives up on it.
SEARCH_BUDGET: Final = 600

JsonObj = dict[str, object]


class MissingRevisionError(RuntimeError):
    """A pinned git revision is not available in this checkout."""


class SeedError(RuntimeError):
    """A source plan failed verification, or a seed broke its family rule."""


# ---------------------------------------------------------------------------
# Small typed accessors for JSON-shaped dicts
# ---------------------------------------------------------------------------


def _obj(value: object) -> JsonObj:
    """Return ``value`` as a JSON object.

    Args:
        value: A decoded JSON value.

    Returns:
        JsonObj: The same object, typed.

    Raises:
        SeedError: If ``value`` is not an object.
    """
    if not isinstance(value, dict):
        msg = f"expected a JSON object, got {type(value).__name__}"
        raise SeedError(msg)
    return cast("JsonObj", value)


def _sect(doc: JsonObj, *keys: str) -> JsonObj:
    """Return a nested object of ``doc``.

    Args:
        doc: The document.
        *keys: The path of keys.

    Returns:
        JsonObj: The nested object.
    """
    current: object = doc
    for key in keys:
        current = _obj(current)[key]
    return _obj(current)


def _strs(value: object) -> list[str]:
    """Return a JSON array of strings, or ``[]`` for a missing value.

    Args:
        value: A decoded JSON value.

    Returns:
        list[str]: A copy of the strings.
    """
    if value is None:
        return []
    return [str(item) for item in cast("list[object]", value)]


def _str(value: object) -> str:
    """Return ``value`` as a string.

    Args:
        value: A decoded JSON value.

    Returns:
        str: The string.

    Raises:
        SeedError: If ``value`` is not a string.
    """
    if not isinstance(value, str):
        msg = f"expected a string, got {type(value).__name__}"
        raise SeedError(msg)
    return value


# ---------------------------------------------------------------------------
# Reading the validation set and its pinned files
# ---------------------------------------------------------------------------


def _sha(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data``.

    Args:
        data: The bytes.

    Returns:
        str: The digest.
    """
    return hashlib.sha256(data).hexdigest()


def _git_blob(revision: str, path: str) -> bytes:
    """Return ``git show <revision>:<path>``.

    Args:
        revision: A commit-ish.
        path: A repository-relative path.

    Returns:
        bytes: The file as committed.

    Raises:
        MissingRevisionError: The object is not in this checkout.
    """
    # #ASSUME: external-resource: git is on PATH and REPO is a checkout.
    # #VERIFY: a failed lookup raises MissingRevisionError so a shallow clone is
    # told apart from a wrong hash (which raises SeedError in read_pinned).
    proc = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        ["git", "-C", str(REPO), "show", f"{revision}:{path}"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        msg = f"git object {revision}:{path} is not available in this checkout"
        raise MissingRevisionError(msg)
    return proc.stdout


def read_pinned(path: str, revision: str | None, sha256: str) -> bytes:
    """Return a pinned file's bytes, verified against its recorded sha256.

    The working-tree file is used when it still has the pinned hash; otherwise
    the file is read from its pinned git revision.

    Args:
        path: Repository-relative path.
        revision: ``git:<commit>``, or None/``working-tree`` for the working tree.
        sha256: The recorded digest.

    Returns:
        bytes: The verified bytes.

    Raises:
        SeedError: The file does not hash to ``sha256``.
    """
    local = REPO / path
    data = local.read_bytes() if local.is_file() else b""
    if _sha(data) != sha256 and revision is not None and revision.startswith("git:"):
        data = _git_blob(revision.removeprefix("git:"), path)
    if _sha(data) != sha256:
        msg = f"{path} does not hash to the recorded sha256 {sha256}"
        raise SeedError(msg)
    return data


@dataclass(frozen=True)
class Source:
    """A clean source plan with its book, both verified against the set.

    Attributes:
        item: The validation-set item of the source plan.
        plan: The source plan as decoded JSON (never mutated).
        book: The parsed Storybook the plan is bound to.
        digest: SHA-256 of the book file, for SP-0's ``book_sha256`` check.
    """

    item: JsonObj
    plan: JsonObj
    book: Storybook
    digest: str

    @property
    def plan_id(self) -> str:
        """Return the source plan's validation-set id."""
        return _str(self.item["id"])

    @property
    def half(self) -> str:
        """Return the source plan's half (``tuning`` or ``held_out``)."""
        return _str(self.item["half"])


def load_validation_set() -> dict[str, JsonObj]:
    """Return the validation set's plan items by id.

    Returns:
        dict[str, JsonObj]: Every ``kind: plan`` item.
    """
    doc = _obj(cast("object", json.loads(VALIDATION_SET.read_text("utf-8"))))
    return {
        _str(_obj(item)["id"]): _obj(item)
        for item in cast("list[object]", doc["items"])
        if _obj(item)["kind"] == "plan"
    }


def load_source(plan_id: str, items: dict[str, JsonObj]) -> Source:
    """Load and verify one source plan.

    Args:
        plan_id: The validation-set id of the clean plan.
        items: The set's plan items.

    Returns:
        Source: The verified source.

    Raises:
        SeedError: The item is not a clean strong plan of a legitimate source.
    """
    if plan_id not in items:
        msg = f"source {plan_id} is not a plan of the validation set"
        raise SeedError(msg)
    item = items[plan_id]
    if (
        item["expected_verdict"] != "pass"
        or item["label_strength"] != "strong"
        or item["half"] not in {TUNING, HELD_OUT}
    ):
        msg = f"source {plan_id} is not a strong clean (pass) plan"
        raise SeedError(msg)
    residual_ids = [
        str(_obj(r).get("id")) for r in cast("list[object]", item["known_residuals"])
    ]
    if any(rid.startswith("R1121-") for rid in residual_ids):
        msg = f"source {plan_id} is a minor-only plan (pass by ruling); not a source"
        raise SeedError(msg)
    book_ref, plan_ref = _obj(item["book"]), _obj(item["plan"])
    book_bytes = read_pinned(
        _str(book_ref["file"]), _str(book_ref["revision"]), _str(book_ref["sha256"])
    )
    plan_bytes = read_pinned(
        _str(plan_ref["file"]),
        cast("str | None", plan_ref.get("revision")),
        _str(plan_ref["sha256"]),
    )
    return Source(
        item=item,
        plan=_obj(cast("object", json.loads(plan_bytes))),
        book=Storybook.model_validate(json.loads(book_bytes)),
        digest=book_sha256(book_bytes),
    )


def run_check(plan: JsonObj, source: Source) -> ValidationReport:
    """Validate a plan against ``StoryPlan`` and run ``check_plan`` on it.

    This is the same call ``verify_witnesses`` makes, plus the book digest so
    SP-0 also verifies ``provenance.book_sha256``.

    Args:
        plan: The plan document.
        source: The source whose book the plan is bound to.

    Returns:
        ValidationReport: The checker's report.
    """
    parsed = StoryPlan.model_validate(plan)
    return check_plan(parsed, source.book, book_digest=source.digest)


def error_rules(report: ValidationReport) -> set[str]:
    """Return the rule ids of a report's ERROR findings.

    Args:
        report: The report.

    Returns:
        set[str]: The distinct rule ids.
    """
    return {f.rule_id for f in report.errors}


# ---------------------------------------------------------------------------
# Baseline repair: the clean e/f plans are clean as books, not as checked plans
# ---------------------------------------------------------------------------

#: The blind extractions are labelled clean because their *book* carries no
#: blocker or should-fix, but several of them still trip SP checks (a blind
#: extractor records presuppositions the book does not guarantee). A seed must
#: differ from a checker-clean plan by exactly one defect, so each source is
#: first brought to zero ERRORs by the mechanical repairs below, recorded per
#: item as ``baseline_repairs``. SP-2 and SP-6 findings drop the unguaranteed
#: fact from the offending ``requires``; an SP-3 ERROR drops the contradiction
#: mark between the pair; an SP-9 finding is reworded by the table below.
SP9_REWORDINGS: Final[dict[tuple[str, str], str]] = {
    (
        "PL-f5",
        "/facts/wren_sings/text",
    ): "The wren, wound up, hops, sings three notes and bows.",
    (
        "PL-f5",
        "/nodes/e_win_secret_workshop/event",
    ): (
        "The wren, wound up, sings and bows, and she waits for the curator "
        "with living proof of the workshop."
    ),
}
_REPAIR_ROUNDS: Final = 8
_QUOTED_ID: Final = re.compile(r"'([A-Za-z0-9_]+)'")
_SP9_PATH: Final = re.compile(r"^((?:facts|nodes)\.[A-Za-z0-9_]+\.(?:text|event))")


def _drop(items: object, fact_id: str) -> bool:
    """Remove ``fact_id`` from a JSON list in place.

    Args:
        items: A decoded JSON list of ids.
        fact_id: The id to remove.

    Returns:
        bool: True when something was removed.
    """
    if not isinstance(items, list):
        return False
    lst = cast("list[object]", items)
    if fact_id in lst:
        lst.remove(fact_id)
        return True
    return False


def _repair_requires(
    plan: JsonObj, node: str | None, choice: str | None, fact: str
) -> str | None:
    """Drop an unguaranteed fact from a ``requires`` list.

    Args:
        plan: The plan document, modified in place.
        node: The finding's node id.
        choice: The finding's choice id, when the finding is about a choice.
        fact: The fact id.

    Returns:
        str | None: The JSON pointer edited, or None when nothing applied.
    """
    if choice is not None:
        entry = _sect(plan, "choices").get(choice)
        if entry is not None and _drop(_obj(entry).get("requires"), fact):
            return f"/choices/{choice}/requires"
    if node is not None:
        entry = _sect(plan, "nodes").get(node)
        if entry is not None and _drop(_obj(entry).get("requires"), fact):
            return f"/nodes/{node}/requires"
    return None


def _repair_marks(plan: JsonObj, message: str) -> list[str]:
    """Drop the contradiction mark between the two facts an SP-3 finding names.

    Args:
        plan: The plan document, modified in place.
        message: The finding's message, which quotes both fact ids.

    Returns:
        list[str]: The JSON pointers edited.
    """
    named = cast("list[str]", _QUOTED_ID.findall(message))[:2]
    facts = _sect(plan, "facts")
    edited: list[str] = []
    if len(named) == 2:
        for first, second in (named, named[::-1]):
            entry = _obj(facts[first])
            if _drop(entry.get("contradicts"), second):
                edited.append(f"/facts/{first}/contradicts")
    return edited


def _repair_text(plan: JsonObj, plan_id: str, location: str) -> str | None:
    """Reword an SP-9 string from the rewording table.

    Args:
        plan: The plan document, modified in place.
        plan_id: The source plan id.
        location: Dotted location from the finding, ``facts.<id>.text`` or
            ``nodes.<id>.event``.

    Returns:
        str | None: The JSON pointer edited, or None when the table has no row.
    """
    pointer = "/" + location.replace(".", "/")
    new_text = SP9_REWORDINGS.get((plan_id, pointer))
    if new_text is None:
        return None
    _, section, key, field = pointer.split("/")
    _sect(plan, section)[key] = {**_sect(plan, section, key), field: new_text}
    return pointer


def repair_baseline(source: Source) -> tuple[JsonObj, list[str]]:
    """Return the source plan with every checker ERROR mechanically repaired.

    Args:
        source: The verified source.

    Returns:
        tuple[JsonObj, list[str]]: A deep copy of the plan that raises no ERROR
            (the source itself when it already raised none), and the sorted
            JSON pointers the repair edited.

    Raises:
        SeedError: A finding has no mechanical repair, or the loop does not
            converge.
    """
    plan = copy.deepcopy(source.plan)
    touched: set[str] = set()
    for _ in range(_REPAIR_ROUNDS):
        report = run_check(plan, source)
        if report.ok:
            return plan, sorted(touched)
        progress = False
        for finding in report.errors:
            edited: list[str] = []
            fact = _fact_of(finding)
            if finding.rule_id in {"SP-2", "SP-6"} and fact is not None:
                pointer = _repair_requires(
                    plan, finding.node_id, finding.choice_id, fact
                )
                edited = [] if pointer is None else [pointer]
            elif finding.rule_id == "SP-3":
                edited = _repair_marks(plan, finding.message)
            elif finding.rule_id == "SP-9":
                located = _SP9_PATH.match(finding.message.split(":", 1)[0])
                pointer = (
                    _repair_text(plan, source.plan_id, located.group(1))
                    if located is not None
                    else None
                )
                edited = [] if pointer is None else [pointer]
            touched.update(edited)
            progress = progress or bool(edited)
        if not progress:
            fired = sorted({f"{f.rule_id}@{f.node_id}" for f in report.errors})
            msg = f"{source.plan_id}: no mechanical repair for {fired}"
            raise SeedError(msg)
    msg = f"{source.plan_id}: baseline repair did not converge"
    raise SeedError(msg)


# ---------------------------------------------------------------------------
# Edits and the book's shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Edit:
    """One candidate change to a plan.

    Attributes:
        apply: Mutates a deep copy of the baseline plan.
        paths: JSON pointers the change touches.
        description: What the change does, in one sentence.
    """

    apply: Callable[[JsonObj], None]
    paths: tuple[str, ...]
    description: str


class Shape:
    """The book-and-plan facts the candidate searches share.

    Attributes:
        plan: The repaired baseline plan.
        book: The parsed book.
    """

    def __init__(self, plan: JsonObj, book: Storybook) -> None:
        """Index the book's graph.

        Args:
            plan: The repaired baseline plan.
            book: The parsed book.
        """
        self.plan = plan
        self.book = book
        self.node_ids = [n.id for n in book.nodes]
        self.inbound: Counter[str] = Counter()
        self.choice_node: dict[str, str] = {}
        self.choice_target: dict[str, str] = {}
        for node in book.nodes:
            for choice in node.choices:
                self.inbound[choice.target] += 1
                self.choice_node[choice.id] = node.id
                self.choice_target[choice.id] = choice.target
        self.node_choices = {n.id: [c.id for c in n.choices] for n in book.nodes}
        self.start = book.start_node
        self.order = self._breadth_first()

    def _breadth_first(self) -> list[str]:
        """Return every node id, nearest the start first, ties in book order.

        Candidate searches walk this order so an edit lands near the opening
        rather than wherever the book's node list happens to put a passage.

        Returns:
            list[str]: Reachable nodes breadth first, then any unreachable ones.
        """
        seen = [self.start]
        known = {self.start}
        index = 0
        while index < len(seen):
            for cid in self.node_choices[seen[index]]:
                target = self.choice_target[cid]
                if target not in known:
                    known.add(target)
                    seen.append(target)
            index += 1
        return [*seen, *(n for n in self.node_ids if n not in known)]

    def decision_nodes(self) -> list[str]:
        """Return non-start nodes offering two or more choices, in book order."""
        return [
            n for n in self.order if len(self.node_choices[n]) >= 2 and n != self.start
        ]

    def merge_nodes(self) -> list[str]:
        """Return non-start nodes with two or more inbound choices, in book order."""
        return [n for n in self.order if self.inbound[n] >= 2 and n != self.start]

    def negative_endings(self) -> list[str]:
        """Return negative-valence ending nodes with a plan entry, in book order."""
        entries = _sect(self.plan, "endings")
        by_id = {n.id: n for n in self.book.nodes}
        return [
            nid
            for nid in self.order
            if by_id[nid].is_ending
            and by_id[nid].ending is not None
            and cast("Ending", by_id[nid].ending).valence is Valence.NEGATIVE
            and nid in entries
        ]

    def threads(self) -> list[str]:
        """Return the plan's thread ids in plan order."""
        return list(_sect(self.plan, "threads"))

    def plants(self) -> set[str]:
        """Return every thread's declared plant fact."""
        return {_str(_obj(t)["plant"]) for t in _sect(self.plan, "threads").values()}

    def established_by_nodes(self) -> list[str]:
        """Return facts some node establishes, in ledger order."""
        seen = {
            f
            for n in _sect(self.plan, "nodes").values()
            for f in _strs(_obj(n).get("establishes"))
        }
        return [f for f in _sect(self.plan, "facts") if f in seen]


Generator = Callable[[Shape], Iterator[Edit]]


def _append_unique(items: list[object], fact_id: str) -> None:
    """Append ``fact_id`` to a JSON list unless present.

    Args:
        items: The list, modified in place.
        fact_id: The id to append.
    """
    if fact_id not in items:
        items.append(fact_id)


def _add_to(plan: JsonObj, section: str, key: str, field: str, fact_id: str) -> None:
    """Append a fact id to ``plan[section][key][field]``, creating the list.

    Args:
        plan: The plan document, modified in place.
        section: ``nodes`` or ``choices``.
        key: The node or choice id.
        field: ``requires`` or ``establishes``.
        fact_id: The fact id.
    """
    entry = _sect(plan, section, key)
    current = entry.get(field)
    lst = cast("list[object]", current) if isinstance(current, list) else []
    entry[field] = lst
    _append_unique(lst, fact_id)


# ---------------------------------------------------------------------------
# Family A: one candidate generator per WP-1.2 witness
# ---------------------------------------------------------------------------


def gen_sp1(shape: Shape) -> Iterator[Edit]:
    """SP-1: drop one decision choice's plan entry (the witness's change).

    Args:
        shape: The baseline's shape.

    Yields:
        Edit: Candidates in book order.
    """
    for node in shape.decision_nodes():
        for cid in shape.node_choices[node]:

            def apply(plan: JsonObj, cid: str = cid) -> None:
                del _sect(plan, "choices")[cid]

            yield Edit(
                apply,
                (f"/choices/{cid}",),
                f"Deletes the plan entry of choice {cid} (offered at {node}), so the "
                "plan no longer covers the book's choices.",
            )


def gen_sp2(shape: Shape) -> Iterator[Edit]:
    """SP-2: make a merge node presuppose a fact only some routes establish.

    Args:
        shape: The baseline's shape.

    Yields:
        Edit: Candidates, merge nodes first, then every other non-start node.
    """
    ordered = [*shape.merge_nodes(), *(n for n in shape.order if n != shape.start)]
    facts = [f for f in shape.established_by_nodes() if f not in shape.plants()]
    seen: set[str] = set()
    for node in ordered:
        if node in seen:
            continue
        seen.add(node)
        for fact in facts:

            def apply(plan: JsonObj, node: str = node, fact: str = fact) -> None:
                _add_to(plan, "nodes", node, "requires", fact)

            yield Edit(
                apply,
                (f"/nodes/{node}/requires",),
                f"Adds fact {fact} to the requires of node {node}, which some routes "
                "reach without having established it.",
            )


@dataclass(frozen=True)
class SecondAnswer:
    """The hand-written rival answer for an SP-3 seed.

    Attributes:
        fact_id: The new fact's id.
        text: Its sentence (at most 240 characters, no braces).
        rival_of: The truth fact it contradicts.
    """

    fact_id: str
    text: str
    rival_of: str


SECOND_ANSWERS: Final[dict[str, SecondAnswer]] = {
    "PL-e5": SecondAnswer(
        "hold_holds_salt_fish",
        "The sealed hold holds only barrels of salt fish, and the captain carries "
        "no secret at all.",
        "nimbus_sky_whale",
    ),
    "PL-the-vanishing-orchard-postfix": SecondAnswer(
        "quiet_is_river_fog",
        "The Quiet is only a cold fog that drifts up from the river each autumn "
        "and has nothing to do with any tree.",
        "quiet_from_oldest_tree",
    ),
}


def gen_sp3_for(plan_id: str) -> Generator:
    """Build SP-3's generator: a second answer to the book's question.

    The new fact contradicts a truth fact and is established at a node some
    single reading also crosses the truth at, which is the "one reading meets
    both" ERROR (the Lighthouse B2 shape).

    Args:
        plan_id: The source plan id, keying :data:`SECOND_ANSWERS`.

    Returns:
        Generator: The generator.
    """
    answer = SECOND_ANSWERS[plan_id]

    def gen(shape: Shape) -> Iterator[Edit]:
        for node in shape.order:
            if node == shape.start:
                continue

            def apply(plan: JsonObj, node: str = node) -> None:
                _sect(plan, "facts")[answer.fact_id] = {
                    "text": answer.text,
                    "contradicts": [answer.rival_of],
                }
                _add_to(plan, "nodes", node, "establishes", answer.fact_id)

            yield Edit(
                apply,
                (f"/facts/{answer.fact_id}", f"/nodes/{node}/establishes"),
                f"Adds fact {answer.fact_id}, a rival answer marked as contradicting "
                f"truth fact {answer.rival_of}, and establishes it at node {node}, "
                "which one reading also crosses with the truth told.",
            )

    return gen


def gen_sp4_public(shape: Shape) -> Iterator[Edit]:
    """SP-4: show every reader the declared plant on the unplanted path.

    Args:
        shape: The baseline's shape.

    Yields:
        Edit: Candidates, thread by thread, in book order.
    """
    facts = _sect(shape.plan, "facts")
    marked = {k for k, v in facts.items() if _strs(_obj(v).get("contradicts"))} | {
        c for v in facts.values() for c in _strs(_obj(v).get("contradicts"))
    }
    # A plant that some fact contradicts would also trip SP-3 wherever it is
    # shown, so those threads go last.
    ordered = sorted(
        shape.threads(),
        key=lambda t: _str(_sect(shape.plan, "threads", t)["plant"]) in marked,
    )
    for thread in ordered:
        plant = _str(_sect(shape.plan, "threads", thread)["plant"])
        for node in shape.order:
            if node == shape.start:
                continue

            def apply(plan: JsonObj, node: str = node, plant: str = plant) -> None:
                _add_to(plan, "nodes", node, "establishes", plant)

            yield Edit(
                apply,
                (f"/nodes/{node}/establishes",),
                f"Establishes plant fact {plant} of thread {thread} at node {node}, "
                "which readers reach without taking the planting choice.",
            )


def gen_sp4_named_half(shape: Shape) -> Iterator[Edit]:
    """SP-4 (second witness): show the other half of a two-part plant to all.

    The planting choice's target already establishes a fact the payoff relies
    on; the edit has a node on the unplanted path establish it too, so the
    declared plant stays private while what it was meant to reveal goes public.

    Args:
        shape: The baseline's shape.

    Yields:
        Edit: Candidates, thread by thread, in book order.
    """
    nodes = _sect(shape.plan, "nodes")
    for thread in shape.threads():
        spec = _sect(shape.plan, "threads", thread)
        relied: set[str] = set()
        for site in cast("list[object]", spec["payoff_sites"]):
            target = shape.choice_target[_str(_obj(site)["choice"])]
            relied.update(_strs(_obj(nodes[target]).get("requires")))
        relied.discard(_str(spec["plant"]))
        for pc in _strs(spec["planting_choices"]):
            target_est = _strs(_obj(nodes[shape.choice_target[pc]]).get("establishes"))
            for fact in target_est:
                if fact not in relied:
                    continue
                for node in shape.order:
                    if node == shape.start:
                        continue

                    def apply(
                        plan: JsonObj, node: str = node, fact: str = fact
                    ) -> None:
                        _add_to(plan, "nodes", node, "establishes", fact)

                    yield Edit(
                        apply,
                        (f"/nodes/{node}/establishes",),
                        f"Establishes fact {fact} at node {node}, which readers "
                        f"reach without taking {pc}; thread {thread}'s payoff relies "
                        f"on {fact}, which {pc} makes known to planted readers only.",
                    )


def _gated_on(shape: Shape, variable: str) -> list[str]:
    """Return the book choices whose condition tests ``variable``.

    Args:
        shape: The baseline's shape.
        variable: A book variable name.

    Returns:
        list[str]: Choice ids in breadth-first order of their node.
    """
    marker = f'"var": "{variable}"'
    gated: list[str] = []
    for nid in shape.order:
        for choice in shape.book.nodes[shape.node_ids.index(nid)].choices:
            condition = choice.condition
            if condition is not None and marker in json.dumps(
                condition, sort_keys=True
            ):
                gated.append(choice.id)
    return gated


def gen_sp5(shape: Shape) -> Iterator[Edit]:
    """SP-5: move a payoff site where readers are only planted or only unplanted.

    The WP-1.2 witness puts the site behind the thread's own gate. Candidates
    start with the choices leaving a passage that a choice gated on the
    thread's variable leads to (readers there are all planted, or all not), then
    fall back to every other book choice in breadth-first order.

    Args:
        shape: The baseline's shape.

    Yields:
        Edit: Candidates, thread by thread.
    """
    for thread in shape.threads():
        spec = _sect(shape.plan, "threads", thread)
        shows = _str(_obj(cast("list[object]", spec["payoff_sites"])[0])["shows"])
        gated_targets = [
            shape.choice_target[c] for c in _gated_on(shape, _str(spec["variable"]))
        ]
        near = [c for t in gated_targets for c in shape.node_choices[t]]
        rest = [
            c
            for _n, c in sorted(
                (shape.order.index(shape.choice_node[c]), c) for c in shape.choice_node
            )
            if c not in near
        ]
        for cid in [*near, *rest]:
            node = shape.choice_node[cid]

            def apply(
                plan: JsonObj,
                thread: str = thread,
                cid: str = cid,
                node: str = node,
                shows: str = shows,
            ) -> None:
                _sect(plan, "threads", thread)["payoff_sites"] = [
                    {"node": node, "choice": cid, "shows": shows}
                ]

            yield Edit(
                apply,
                (f"/threads/{thread}/payoff_sites",),
                f"Moves thread {thread}'s payoff site to choice {cid} at node {node}, "
                "which readers reach only planted or only unplanted, so the payoff "
                "cannot show the difference the plant makes.",
            )


def gen_sp6(shape: Shape) -> Iterator[Edit]:
    """SP-6: make one thread's payoff lean on what another thread's payoff showed.

    Every real plan gates a payoff on a single variable and records each plant at
    the node after its planting choice, so a payoff never leans on another
    thread's plant in a way the plant-blind analysis misses. The shape that does
    trip SP-6 is a payoff passage that requires a fact only another thread's
    payoff passage establishes, reached only through that passage. The edit moves
    thread ``lean``'s payoff to a choice out of thread ``other``'s payoff passage
    and has the new payoff passage require one of the facts that passage
    establishes.

    Args:
        shape: The baseline's shape.

    Yields:
        Edit: Candidates in plan order.
    """
    nodes = _sect(shape.plan, "nodes")
    threads = shape.threads()
    for lean in threads:
        lean_spec = _sect(shape.plan, "threads", lean)
        own_plant = _str(lean_spec["plant"])
        shows = _str(_obj(cast("list[object]", lean_spec["payoff_sites"])[0])["shows"])
        for other in threads:
            if other == lean:
                continue
            other_spec = _sect(shape.plan, "threads", other)
            passages = [
                shape.choice_target[_str(_obj(site)["choice"])]
                for site in cast("list[object]", other_spec["payoff_sites"])
            ]
            for passage in passages:
                shown = [
                    f
                    for f in _strs(_obj(nodes[passage]).get("establishes"))
                    if f != own_plant
                ]
                for cid in shape.node_choices[passage]:
                    landing = shape.choice_target[cid]
                    for fact in shown:

                        def apply(
                            plan: JsonObj,
                            lean: str = lean,
                            passage: str = passage,
                            cid: str = cid,
                            landing: str = landing,
                            fact: str = fact,
                            shows: str = shows,
                        ) -> None:
                            _sect(plan, "threads", lean)["payoff_sites"] = [
                                {"node": passage, "choice": cid, "shows": shows}
                            ]
                            _add_to(plan, "nodes", landing, "requires", fact)

                        yield Edit(
                            apply,
                            (
                                f"/threads/{lean}/payoff_sites",
                                f"/nodes/{landing}/requires",
                            ),
                            f"Moves thread {lean}'s payoff to choice {cid} out of "
                            f"{passage}, the payoff passage of thread {other}, and "
                            f"has {landing} require {fact}, which only {passage} "
                            "establishes.",
                        )


def gen_sp7(shape: Shape) -> Iterator[Edit]:
    """SP-7: drop a negative ending's gift entry.

    Args:
        shape: The baseline's shape.

    Yields:
        Edit: Candidates in book order.
    """
    for node in shape.negative_endings():

        def apply(plan: JsonObj, node: str = node) -> None:
            del _sect(plan, "endings")[node]

        yield Edit(
            apply,
            (f"/endings/{node}",),
            f"Deletes the ending entry (and so the gift) of negative ending {node}.",
        )


def gen_sp8(shape: Shape) -> Iterator[Edit]:
    """SP-8: make a decision costless, every option's cost "None.".

    Args:
        shape: The baseline's shape.

    Yields:
        Edit: Candidates in book order.
    """
    for node in shape.decision_nodes():
        cids = shape.node_choices[node]

        def apply(plan: JsonObj, cids: list[str] = cids) -> None:
            for cid in cids:
                _sect(plan, "choices", cid)["cost"] = "None."

        yield Edit(
            apply,
            tuple(f"/choices/{cid}/cost" for cid in cids),
            f"Sets the cost of every choice at decision node {node} to None., so no "
            "option gives anything up.",
        )


def _fact_text_edits(
    shape: Shape, suffix_for: Callable[[str], str], what: str
) -> Iterator[Edit]:
    """Yield one edit per ledger fact that appends text to its sentence.

    Args:
        shape: The baseline's shape.
        suffix_for: Builds the text to append from the fact's current text.
        what: A clause for the description.

    Yields:
        Edit: Candidates in ledger order, skipping facts that would pass the cap.
    """
    for fact_id, fact in _sect(shape.plan, "facts").items():
        text = _str(_obj(fact)["text"])
        new_text = suffix_for(text)
        if len(new_text) > 240:
            continue

        def apply(
            plan: JsonObj, fact_id: str = fact_id, new_text: str = new_text
        ) -> None:
            _sect(plan, "facts", fact_id)["text"] = new_text

        yield Edit(apply, (f"/facts/{fact_id}/text",), f"{what} in fact {fact_id}.")


def gen_sp9_token(shape: Shape) -> Iterator[Edit]:
    """SP-9: forge a slot token in a fact sentence.

    Args:
        shape: The baseline's shape.

    Yields:
        Edit: Candidates in ledger order.
    """
    yield from _fact_text_edits(
        shape,
        lambda text: text.rstrip(".") + " for {HERO}.",
        "Forges the slot token {HERO}",
    )


def gen_sp9_wound(shape: Shape) -> Iterator[Edit]:
    """SP-9 (second witness): the injury sense of "wound" beside a winding word.

    Args:
        shape: The baseline's shape.

    Yields:
        Edit: Candidates in ledger order.
    """
    yield from _fact_text_edits(
        shape,
        lambda text: text.rstrip(".") + ". A wound from the clock key marks it.",
        'Adds the injury sense of "wound" beside a clock word',
    )


# ---------------------------------------------------------------------------
# Family A: the seed specifications
# ---------------------------------------------------------------------------


def _always(generator: Generator) -> Callable[[str], Generator]:
    """Return a factory that ignores the source plan and yields ``generator``.

    Args:
        generator: The candidate generator.

    Returns:
        Callable[[str], Generator]: The factory.
    """
    return lambda _plan_id: generator


@dataclass(frozen=True)
class WitnessKind:
    """A WP-1.2 witness, as a rule and a candidate generator.

    Attributes:
        key: Short name used in :data:`SEEDS_A`.
        rule: The rule the seed must trip (and nothing else).
        witness: The WP-1.2 witness this transplants, for the README.
        factory: Builds the candidate generator for a source plan id.
    """

    key: str
    rule: str
    witness: str
    factory: Callable[[str], Generator]


KINDS: Final[dict[str, WitnessKind]] = {
    k.key: k
    for k in (
        WitnessKind("sp1", "SP-1", "drop a choice's plan entry", _always(gen_sp1)),
        WitnessKind(
            "sp2", "SP-2", "a shared node presupposes a plant", _always(gen_sp2)
        ),
        WitnessKind("sp3", "SP-3", "a second backstory", gen_sp3_for),
        WitnessKind(
            "sp4", "SP-4", "the plant shown on the shared path", _always(gen_sp4_public)
        ),
        WitnessKind(
            "sp4b",
            "SP-4",
            "the plant's named half shown to all",
            _always(gen_sp4_named_half),
        ),
        WitnessKind("sp5", "SP-5", "a payoff behind its own gate", _always(gen_sp5)),
        WitnessKind("sp6", "SP-6", "a payoff leans on another's", _always(gen_sp6)),
        WitnessKind(
            "sp7", "SP-7", "a negative ending's gift dropped", _always(gen_sp7)
        ),
        WitnessKind(
            "sp8", "SP-8", "an opening decision made costless", _always(gen_sp8)
        ),
        WitnessKind("sp9", "SP-9", "a forged slot token", _always(gen_sp9_token)),
        WitnessKind(
            "sp9b", "SP-9", 'the injury sense of "wound"', _always(gen_sp9_wound)
        ),
    )
}


@dataclass(frozen=True)
class SeedA:
    """One family A seed: a witness moved onto a source plan.

    Attributes:
        kind: A key of :data:`KINDS`.
        source: The source plan's validation-set id.
    """

    kind: str
    source: str


#: Held-out sources first. Each held-out book carries at least two seeds on
#: different rules; no rule exceeds two seeds in a half. Rules a plan's shape
#: cannot carry are left to another book: Cave of Echoes and Mapmaker's Island
#: declare no variables (so no SP-4 to SP-6), and Cave has no negative ending
#: (so no SP-7). The tuning half lacks SP-4 (named half) and SP-6: no
#: Lighthouse payoff is reached only through another thread's payoff passage.
SEEDS_A: Final[tuple[SeedA, ...]] = (
    SeedA("sp1", "PL-e4"),
    SeedA("sp9", "PL-f1"),
    SeedA("sp2", "PL-e3"),
    SeedA("sp7", "PL-e3"),
    SeedA("sp8", "PL-e3"),
    SeedA("sp4", "PL-e1"),
    SeedA("sp6", "PL-e1"),
    SeedA("sp4b", "PL-f5"),
    SeedA("sp5", "PL-f5"),
    SeedA("sp3", "PL-e5"),
    SeedA("sp9b", "PL-e5"),
    SeedA("sp4", "PL-the-hollow-lighthouse-postfix"),
    SeedA("sp5", "PL-the-hollow-lighthouse-postfix"),
    SeedA("sp9b", "PL-the-hollow-lighthouse-postfix"),
    SeedA("sp1", "PL-the-vanishing-orchard-postfix"),
    SeedA("sp2", "PL-the-vanishing-orchard-postfix"),
    SeedA("sp3", "PL-the-vanishing-orchard-postfix"),
    SeedA("sp7", "PL-the-vanishing-orchard-postfix"),
    SeedA("sp8", "PL-the-vanishing-orchard-postfix"),
    SeedA("sp9", "PL-the-vanishing-orchard-postfix"),
)


# ---------------------------------------------------------------------------
# Family B: hand-designed checker-invisible defects
# ---------------------------------------------------------------------------

#: The four classes. Ids use the short code, ``defect_class`` the name.
B_CLASSES: Final[dict[str, str]] = {
    "B1": "label_outcome_mismatch",
    "B2": "truth_contradiction",
    "B3": "ending_gift_mismatch",
    "B4": "payoff_shows_mismatch",
}


@dataclass(frozen=True)
class Op:
    """One edit to a plan, at a JSON pointer.

    Attributes:
        pointer: RFC 6901 pointer of the value to set or the list to extend.
        value: The new value, or the item to append.
        append: When True the pointer names a list (created if absent) and
            ``value`` is appended to it; otherwise ``value`` replaces the target.
    """

    pointer: str
    value: object
    append: bool = False


@dataclass(frozen=True)
class SeedB:
    """One family B seed.

    Attributes:
        code: ``B1`` to ``B4`` (a key of :data:`B_CLASSES`).
        source: The source plan's validation-set id.
        ops: The edits, applied in order.
        severity: The designer's reasoned severity for the defect.
        description: What the edit does, in one sentence.
        reviewer_should_say: What a reviewer ought to report, in one sentence.
    """

    code: str
    source: str
    ops: tuple[Op, ...]
    severity: str
    description: str
    reviewer_should_say: str


SEEDS_B: Final[tuple[SeedB, ...]] = (
    # --- held out -----------------------------------------------------------
    SeedB(
        "B1",
        "PL-e4",
        (
            Op("/choices/c_lakeback/intent", "wait on the shelf until the tide turns"),
            Op("/choices/c_lakeback/cost", "risks the rising water while she waits"),
        ),
        "should-fix",
        "Rewrites choice c_lakeback so it says Maya waits on the slick shelf, while "
        "its target ra_lake_back still establishes that she retreats along the "
        "passage to daylight.",
        "Choice c_lakeback is planned as waiting on the shelf for the tide, but its "
        "target passage ra_lake_back has Maya leave the cave at once, so the label "
        "contradicts the outcome.",
    ),
    SeedB(
        "B3",
        "PL-e4",
        (
            Op(
                "/endings/da_bat_back/gift",
                "a dark scramble back that nearly cost her Biscuit, proving that "
                "turning back is not safe",
            ),
        ),
        "should-fix",
        "Rewrites the gift of the neutral turn-back ending da_bat_back so it says "
        "turning back was dangerous, against the truth that turning back always "
        "gets Maya and Biscuit out safely.",
        "The gift of da_bat_back says turning back nearly cost Maya her dog, which "
        "contradicts the truth that turning back at a risk point is always safe and "
        "the ending's own calm neutral kind.",
    ),
    SeedB(
        "B2",
        "PL-e3",
        (
            Op(
                "/facts/alder_sailed_home",
                {
                    "text": "A faded note in the survey tower says Alder finished "
                    "the chart and sailed home safely."
                },
            ),
            Op("/nodes/tw_enter/establishes", "alder_sailed_home", append=True),
        ),
        "blocker",
        "Adds fact alder_sailed_home, which the truth rules out (Alder never "
        "returned), establishes it at the survey tower entrance tw_enter, and "
        "leaves its contradicts list empty so no check sees the clash.",
        "Node tw_enter establishes that Alder sailed home safely, but the truth is "
        "that a storm took Alder's boat and Alder never returned, and the plan does "
        "not mark the two as contradicting.",
    ),
    SeedB(
        "B3",
        "PL-e1",
        (
            Op(
                "/endings/e_count_wait/gift",
                "the loop is saved, and Kell and Marin are on the phone together "
                "by morning",
            ),
        ),
        "should-fix",
        "Rewrites the gift of the negative ending e_count_wait so it describes a "
        "happy reunion, while the ending's node still establishes that the loop is "
        "gone.",
        "The gift of the negative ending e_count_wait describes the loop saved and "
        "a reunion, which contradicts the ending's negative valence and its own "
        "passage, where the tide kills the relay and the loop is gone.",
    ),
    SeedB(
        "B4",
        "PL-e1",
        (
            Op(
                "/threads/has_battery/payoff_sites/0/shows",
                "she splices grandpa's headset across the empty terminals and the "
                "station holds",
            ),
        ),
        "should-fix",
        "Rewrites the shows line of the battery thread's payoff so the station is "
        "saved by the headset, which belongs to a different thread.",
        "The has_battery payoff says the headset saves the station, but the thread "
        "planted the spare battery at c_n_shelf_1; the payoff does not show what "
        "the planting choice set up.",
    ),
    SeedB(
        "B1",
        "PL-f5",
        (
            Op(
                "/choices/c_alarm_hide/intent",
                "step out and ask the guard what he is hunting",
            ),
            Op(
                "/choices/c_alarm_hide/cost",
                "gives up hiding; the guard may send her home early",
            ),
        ),
        "should-fix",
        "Rewrites choice c_alarm_hide so Nadia steps out to question the guard, "
        "while the target a_gems_hide still establishes that she stays hidden and "
        "only overhears him.",
        "Choice c_alarm_hide is planned as stepping out to speak to the guard, but "
        "its target a_gems_hide has her stay hidden behind the plinth and overhear "
        "him, so the intent and cost contradict the outcome.",
    ),
    SeedB(
        "B4",
        "PL-f5",
        (
            Op(
                "/threads/has_chalk/payoff_sites/0/shows",
                "the borrowed lantern lights a path through the dark stacks to Row Q",
            ),
        ),
        "should-fix",
        "Rewrites the shows line of the chalk thread's first payoff so a lantern, "
        "not the kept chalk, lights the way.",
        "The has_chalk payoff credits a lantern, but the thread planted the chalk "
        "stub she kept; the payoff does not match what c_desk_chalk set up.",
    ),
    SeedB(
        "B2",
        "PL-e5",
        (
            Op(
                "/facts/quill_sells_calf",
                {
                    "text": "Captain Quill plans to sell the sky-whale calf at the "
                    "hunters' market."
                },
            ),
            Op("/nodes/b_hold_deep/establishes", "quill_sells_calf", append=True),
        ),
        "blocker",
        "Adds fact quill_sells_calf, which the truth rules out (the captain carries "
        "the calf to a haven), establishes it in the cargo hold at b_hold_deep, and "
        "leaves contradicts empty.",
        "Node b_hold_deep establishes that Captain Quill means to sell the calf to "
        "hunters, but the truth is that he is secretly carrying it to a haven, and "
        "the plan does not mark the two as contradicting.",
    ),
    # --- tuning -------------------------------------------------------------
    SeedB(
        "B1",
        "PL-the-hollow-lighthouse-postfix",
        (
            Op("/choices/c_a_hearth_1/intent", "leave the cold ash undisturbed"),
            Op("/choices/c_a_hearth_1/cost", "forgoes the scorched photograph"),
        ),
        "should-fix",
        "Rewrites choice c_a_hearth_1 so Mira leaves the ash alone, while its target "
        "a_hearth_ash still establishes that she sifts it and finds a photograph.",
        "Choice c_a_hearth_1 is planned as leaving the ash undisturbed and giving up "
        "the photograph, but its target a_hearth_ash has Mira find the scorched "
        "photograph in the ash.",
    ),
    SeedB(
        "B4",
        "PL-the-hollow-lighthouse-postfix",
        (
            Op(
                "/threads/t_key/payoff_sites/0/shows",
                "with the keeper's code she flashes the great lamp and the coastguard "
                "answers",
            ),
        ),
        "should-fix",
        "Rewrites the shows line of the key thread's first payoff so the lamp is "
        "worked with the keeper's code, which belongs to the code thread.",
        "The t_key payoff shows the signal code working the lamp, but the thread "
        "planted the brass key; the payoff does not show what the planting choices "
        "set up.",
    ),
    SeedB(
        "B2",
        "PL-the-vanishing-orchard-postfix",
        (
            Op(
                "/facts/grandmother_writes_postcards",
                {
                    "text": "A postcard shows Rowan's grandmother alive and well in "
                    "a far city, forty years after she left."
                },
            ),
            Op(
                "/nodes/pho_entry/establishes",
                "grandmother_writes_postcards",
                append=True,
            ),
        ),
        "blocker",
        "Adds fact grandmother_writes_postcards, which the truth rules out (the "
        "grandmother went into the spring and is held there), establishes it in "
        "Teo's attic at pho_entry, and leaves contradicts empty.",
        "Node pho_entry establishes that Rowan's grandmother lives in a far city, "
        "but the truth is that she went into the spring forty years ago and is held "
        "there, and the plan does not mark the two as contradicting.",
    ),
    SeedB(
        "B3",
        "PL-the-vanishing-orchard-postfix",
        (
            Op(
                "/endings/e_pho_a/gift",
                "the prints saved, the Quiet beaten for good, and the whole town "
                "cheering Rowan",
            ),
        ),
        "should-fix",
        "Rewrites the gift of the negative ending e_pho_a as a triumph over the "
        "Quiet, while the ending's node still has Rowan burn the prints and finish "
        "the Quiet's work.",
        "The gift of the negative ending e_pho_a describes the Quiet beaten and a "
        "cheering town, which contradicts its negative valence, its own passage "
        "where she burns the evidence, and the truth that the Quiet cannot be "
        "ended that way.",
    ),
)


# ---------------------------------------------------------------------------
# Building the seeds
# ---------------------------------------------------------------------------


def _walk(doc: object, parts: list[str]) -> object:
    """Follow JSON pointer parts through dicts and lists.

    Args:
        doc: The document.
        parts: Already-split pointer parts.

    Returns:
        object: The value reached.
    """
    current = doc
    for part in parts:
        if isinstance(current, list):
            current = cast("list[object]", current)[int(part)]
        else:
            current = _obj(current)[part]
    return current


def apply_op(plan: JsonObj, op: Op) -> None:
    """Apply one :class:`Op` to a plan, in place.

    Args:
        plan: The plan document.
        op: The edit.

    Raises:
        SeedError: The pointer's parent does not exist.
    """
    parts = op.pointer.removeprefix("/").split("/")
    parent = _walk(plan, parts[:-1])
    last = parts[-1]
    if op.append:
        holder = _obj(parent)
        current = holder.get(last)
        if not isinstance(current, list):
            current = []
            holder[last] = current
        cast("list[object]", current).append(op.value)
    elif isinstance(parent, list):
        cast("list[object]", parent)[int(last)] = op.value
    else:
        holder = _obj(parent)
        new_fact = op.pointer.startswith("/facts/") and len(parts) == 2
        if last not in holder and not new_fact:
            msg = f"pointer {op.pointer} does not exist in the plan"
            raise SeedError(msg)
        holder[last] = op.value


def _fact_of(finding: object) -> str | None:
    """Return the ledger fact a plan finding concerns, if any.

    Args:
        finding: A finding from ``check_plan`` (a ``PlanFinding``).

    Returns:
        str | None: The fact id, or None for a finding about no fact.
    """
    return finding.fact_id if isinstance(finding, PlanFinding) else None


def _warning_keys(report: ValidationReport) -> set[tuple[str, str | None, str | None]]:
    """Return a report's warnings as ``(rule, node, fact)`` keys.

    Args:
        report: The report.

    Returns:
        set[tuple[str, str | None, str | None]]: One key per warning.
    """
    keys: set[tuple[str, str | None, str | None]] = set()
    for finding in report.warnings:
        keys.add((finding.rule_id, finding.node_id, _fact_of(finding)))
    return keys


def encode_plan(plan: JsonObj) -> str:
    """Serialise a plan for its file: indent 2, ASCII only, trailing newline.

    Args:
        plan: The plan document.

    Returns:
        str: The file text.
    """
    return json.dumps(plan, indent=2, ensure_ascii=True) + "\n"


@dataclass(frozen=True)
class Seed:
    """A built, verified seed ready to be written.

    Attributes:
        item: The synthetic validation-set item (without ``plan.sha256`` yet
            filled in only if the text is unknown; it is always filled here).
        text: The plan file's text.
    """

    item: JsonObj
    text: str


def _verify_text(text: str, source: Source) -> ValidationReport:
    """Re-read a plan from its file text and check it, so the file is what was tested.

    Args:
        text: The plan file text.
        source: The source whose book the plan is bound to.

    Returns:
        ValidationReport: The checker's report on the re-read plan.
    """
    return run_check(_obj(cast("object", json.loads(text))), source)


def _item_common(
    source: Source,
    baseline_repairs: list[str],
    text: str,
    seed_id: str,
    family: str,
) -> JsonObj:
    """Return the item fields every seed shares.

    Args:
        source: The source plan.
        baseline_repairs: The repair pointers applied before the edit.
        text: The plan file text.
        seed_id: The item id.
        family: ``A`` or ``B``.

    Returns:
        JsonObj: The shared fields.
    """
    plan_ref = _obj(source.item["plan"])
    return {
        "id": seed_id,
        "kind": "plan",
        "family": family,
        "half": source.half,
        "book": copy.deepcopy(_obj(source.item["book"])),
        "source_plan_id": source.plan_id,
        "source_plan": {
            "file": plan_ref["file"],
            "sha256": plan_ref["sha256"],
        },
        "baseline_repairs": baseline_repairs,
        "plan": {
            "file": f"{OUT_REL}/{seed_id}.plan.json",
            "sha256": _sha(text.encode("utf-8")),
        },
        "expected_verdict": "reject",
        "scored_for": SCORED_FOR,
        "label_strength": "synthetic",
    }


OUT_REL: Final = "docs/planning/evidence/plan-reviewer/synthetic"


def build_seed_a(
    spec: SeedA,
    n: int,
    source: Source,
    baseline: JsonObj,
    repairs: list[str],
) -> Seed:
    """Search for the first candidate edit that trips exactly the witness's rule.

    Args:
        spec: The seed specification.
        n: This seed's ordinal among the seeds of its rule.
        source: The source plan.
        baseline: The repaired baseline plan.
        repairs: The pointers the baseline repair edited.

    Returns:
        Seed: The verified seed.

    Raises:
        SeedError: No candidate within the search budget trips exactly the rule.
    """
    kind = KINDS[spec.kind]
    shape = Shape(baseline, source.book)
    for tried, edit in enumerate(kind.factory(source.plan_id)(shape), start=1):
        if tried > SEARCH_BUDGET:
            break
        plan = copy.deepcopy(baseline)
        edit.apply(plan)
        try:
            if error_rules(run_check(plan, source)) != {kind.rule}:
                continue
        except ValueError:
            continue  # a candidate that breaks the plan schema is not a seed
        text = encode_plan(plan)
        report = _verify_text(text, source)
        if error_rules(report) != {kind.rule}:
            msg = f"{spec.source}: {kind.rule} seed changed on re-read"
            raise SeedError(msg)
        seed_id = f"SY-A-{kind.rule}-{n}"
        item = _item_common(source, repairs, text, seed_id, "A")
        item.update(
            {
                "defect_class": kind.rule,
                "intended_rule": kind.rule,
                "witness": kind.witness,
                "edited_paths": list(edit.paths),
                "description": edit.description,
                "checker_errors": sorted(error_rules(report)),
                "severity": "blocker",
            }
        )
        return Seed(item, text)
    msg = f"{spec.source}: no {kind.rule} candidate within {SEARCH_BUDGET} tries"
    raise SeedError(msg)


def build_seed_b(
    spec: SeedB,
    n: int,
    source: Source,
    baseline: JsonObj,
    repairs: list[str],
) -> Seed:
    """Apply a hand-designed edit and verify it is checker-invisible.

    Args:
        spec: The seed specification.
        n: This seed's ordinal among the seeds of its class.
        source: The source plan.
        baseline: The repaired baseline plan.
        repairs: The pointers the baseline repair edited.

    Returns:
        Seed: The verified seed.

    Raises:
        SeedError: The edited plan raises an ERROR, or a warning the baseline
            does not already raise.
    """
    plan = copy.deepcopy(baseline)
    for op in spec.ops:
        apply_op(plan, op)
    text = encode_plan(plan)
    report = _verify_text(text, source)
    base_report = run_check(baseline, source)
    if not report.ok:
        fired = sorted({f"{f.rule_id}@{f.node_id}" for f in report.errors})
        msg = f"{source.plan_id}: {spec.code} seed is not checker-invisible: {fired}"
        raise SeedError(msg)
    added = _warning_keys(report) - _warning_keys(base_report)
    if added:
        msg = (
            f"{source.plan_id}: {spec.code} seed adds warnings {sorted(added, key=str)}"
        )
        raise SeedError(msg)
    seed_id = f"SY-B-{spec.code}-{n}"
    item = _item_common(source, repairs, text, seed_id, "B")
    item.update(
        {
            "defect_class": B_CLASSES[spec.code],
            "intended_class": B_CLASSES[spec.code],
            "class_code": spec.code,
            "edited_paths": [op.pointer for op in spec.ops],
            "description": spec.description,
            "reviewer_should_say": spec.reviewer_should_say,
            "checker_errors": [],
            "severity": spec.severity,
        }
    )
    return Seed(item, text)


def _summary(items: list[JsonObj]) -> JsonObj:
    """Count the items per family, rule or class, and half.

    Args:
        items: The synthetic items.

    Returns:
        JsonObj: The summary block.
    """

    def count(family: str, half: str | None) -> Counter[str]:
        return Counter(
            _str(i["defect_class"])
            for i in items
            if i["family"] == family and (half is None or i["half"] == half)
        )

    out: JsonObj = {"items": len(items)}
    for family, label in (("A", "family_a"), ("B", "family_b")):
        block: JsonObj = {"total": sum(count(family, None).values())}
        block["by_rule_or_class"] = dict(sorted(count(family, None).items()))
        for half in (TUNING, HELD_OUT):
            block[half] = {
                "total": sum(count(family, half).values()),
                "by_rule_or_class": dict(sorted(count(family, half).items())),
            }
        out[label] = block
    held = [i for i in items if i["half"] == HELD_OUT]
    out["held_out_by_unit"] = dict(
        sorted(
            Counter(
                f"{_str(_obj(i['book'])['unit'])} {i['family']}" for i in held
            ).items()
        )
    )
    return out


def build() -> tuple[JsonObj, dict[str, str]]:
    """Build every seed, enforce the family rules and return the outputs.

    Returns:
        tuple[JsonObj, dict[str, str]]: The synthetic validation-set document and
            the plan files (``<id>.plan.json`` to text).

    Raises:
        SeedError: A seed breaks its family rule or a source fails verification.
    """
    plan_items = load_validation_set()
    cache: dict[str, tuple[Source, JsonObj, list[str]]] = {}

    def prepared(plan_id: str) -> tuple[Source, JsonObj, list[str]]:
        if plan_id not in cache:
            source = load_source(plan_id, plan_items)
            baseline, repairs = repair_baseline(source)
            cache[plan_id] = (source, baseline, repairs)
        return cache[plan_id]

    seeds: list[Seed] = []
    counters: Counter[str] = Counter()
    for spec_a in SEEDS_A:
        source, baseline, repairs = prepared(spec_a.source)
        rule = KINDS[spec_a.kind].rule
        counters[rule] += 1
        seeds.append(build_seed_a(spec_a, counters[rule], source, baseline, repairs))
    for spec_b in SEEDS_B:
        source, baseline, repairs = prepared(spec_b.source)
        counters[spec_b.code] += 1
        seeds.append(
            build_seed_b(spec_b, counters[spec_b.code], source, baseline, repairs)
        )
    items = [seed.item for seed in seeds]
    _enforce(items)
    sources: JsonObj = {
        plan_id: {
            "half": src.half,
            "book_unit": _obj(src.item["book"])["unit"],
            "plan": _obj(src.item["plan"])["file"],
            "sha256": _obj(src.item["plan"])["sha256"],
            "baseline_repairs": repairs,
        }
        for plan_id, (src, _base, repairs) in sorted(cache.items())
    }
    doc: JsonObj = {
        "schema": SCHEMA,
        "work_package": "WP-3.7",
        "decision": "D12 (as amended 2026-11-21), synthetic seeded-defect plans",
        "generator": "scripts/build_synthetic_plans.py",
        "readme": README_LINK,
        "never_merged": (
            "These items are synthetic. They are never merged into "
            "docs/planning/evidence/continuity-reader/validation-set.json or into "
            "any recall or flag-rate figure computed from it; family A and family B "
            "are reported separately from each other and from the real set."
        ),
        "source_set": "docs/planning/evidence/continuity-reader/validation-set.json",
        "split_seed": SPLIT_SEED,
        "sources": sources,
        "summary": _summary(items),
        "items": items,
    }
    return doc, {
        f"{_str(i['id'])}.plan.json": s.text for i, s in zip(items, seeds, strict=True)
    }


def _enforce(items: list[JsonObj]) -> None:
    """Enforce the set-level rules D12 and the task set.

    Args:
        items: The built items.

    Raises:
        SeedError: A rule is broken.
    """
    ids = [_str(i["id"]) for i in items]
    if len(set(ids)) != len(ids):
        msg = "duplicate synthetic item ids"
        raise SeedError(msg)
    for half in (TUNING, HELD_OUT):
        rules = Counter(
            _str(i["intended_rule"])
            for i in items
            if i["family"] == "A" and i["half"] == half
        )
        for rule, count in rules.items():
            if count > MAX_SEEDS_PER_RULE:
                msg = f"{half}: rule {rule} supplies {count} seeds (maximum 2)"
                raise SeedError(msg)
    for item in items:
        source_half = _str(item["half"])
        if source_half not in {TUNING, HELD_OUT}:
            msg = f"{item['id']}: unknown half {source_half}"
            raise SeedError(msg)
    witnessed = {w.rule_id for w in WITNESSES}
    unknown = {_str(i["defect_class"]) for i in items if i["family"] == "A"} - witnessed
    if unknown:
        msg = f"seeded rules with no WP-1.2 witness: {sorted(unknown)}"
        raise SeedError(msg)


# ---------------------------------------------------------------------------
# Output and CLI
# ---------------------------------------------------------------------------


def render(doc: JsonObj) -> str:
    """Serialise the document deterministically (sorted keys, indent 2, newline).

    Args:
        doc: The synthetic validation-set document.

    Returns:
        str: The file text.
    """
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def expected_files() -> dict[Path, str]:
    """Build everything and return the file each path must hold.

    Returns:
        dict[Path, str]: Absolute path to text, for the set file and every plan.
    """
    doc, plans = build()
    files = {OUT_DIR / name: text for name, text in plans.items()}
    files[OUT_FILE] = render(doc)
    return files


def _drift(files: dict[Path, str]) -> list[str]:
    """Compare the expected files with the working tree.

    Args:
        files: Absolute path to expected text.

    Returns:
        list[str]: One line per missing, different or stray file.
    """
    problems: list[str] = []
    for path, text in sorted(files.items()):
        current = path.read_text("utf-8") if path.is_file() else None
        if current != text:
            problems.append(f"drift: {path.relative_to(REPO)}")
    if OUT_DIR.is_dir():
        problems.extend(
            f"stray: {path.relative_to(REPO)}"
            for path in sorted(OUT_DIR.glob("*.plan.json"))
            if path not in files
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    """Run the builder CLI.

    Args:
        argv: Arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        int: The exit code.
    """
    parser = argparse.ArgumentParser(description="Build the WP-3.7 synthetic plans.")
    parser.add_argument("--check", action="store_true", help="compare, do not write")
    parser.add_argument("--summary", action="store_true", help="print the counts")
    args = parser.parse_args(argv)
    check = cast("bool", args.check)
    summary = cast("bool", args.summary)
    try:
        files = expected_files()
    except MissingRevisionError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return EXIT_NO_REVISION
    except SeedError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return EXIT_FAIL
    if summary:
        doc = _obj(cast("object", json.loads(files[OUT_FILE])))
        sys.stdout.write(json.dumps(doc["summary"], indent=2) + "\n")
        return EXIT_OK
    if check:
        problems = _drift(files)
        for problem in problems:
            sys.stderr.write(problem + "; rerun without --check\n")
        return EXIT_FAIL if problems else EXIT_OK
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.plan.json"):
        if stale not in files:
            stale.unlink()
    for path, text in files.items():
        path.write_text(text, "utf-8")
    sys.stdout.write(f"wrote {len(files)} files under {OUT_DIR.relative_to(REPO)}\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
