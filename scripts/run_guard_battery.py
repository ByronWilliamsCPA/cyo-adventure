"""Run every guard a book must clear, in one command, with the right defaults.

Usage:
    uv run python scripts/run_guard_battery.py <skeleton.json> <contract.json>
        <filled.json>... [--check] [--binding sel.json]...

**Written because invoking the guards by hand failed twice in one working day.**
A rating round was spoiled by a defect no checker existed for yet, and a
recorded result was briefly doubted because a checker was invoked without the
flag it needed. Both are the same failure: the battery lived in somebody's head
and in scattered shell history, so which checks ran, and how, varied per round.

This is not a new check. It is the list, in one place, with the defaults each
one is calibrated for, so that "did this book pass" has a single answer.

**What it runs, and why each is here.**

| Guard | Question | Gates |
| --- | --- | --- |
| `check_graph_structure` | is it a well-formed story graph | yes |
| `check_fill_integrity` | did the fill change anything structural | yes |
| `run_story_gate` | safety, band profile, schema | yes |
| `check_prose_craft` | tense stability, told emotion, moral tags | yes |
| `check_reading_level` | is the whole book too hard for its band | yes |
| `check_label_template` | is the book identifiable from its labels alone | yes |
| `check_promise_discharge` | does a choice promise what nothing delivers | yes |
| `check_device_vocabulary` | can the contract's vocabulary support the series | yes |
| `check_sibling_fills` | do sibling books converge on shared wording | yes, with 2+ books |
| `check_corpus_convergence` | which PAIR converges, and how it is related | no, observed only |
| `check_device_collision` | do sibling books share their props | yes, with 2+ bindings |

**What it deliberately does not run.** `check_fill_fidelity` and
`build_prose_review_worklist` both answer entailment questions that this
programme has twice measured as unanswerable lexically, and neither can gate.
They are reported as follow-up work rather than folded in, so that a green
battery never implies the prose was read.

**One pairwise row reports rather than gates.** `check_sibling_fills` answers
"is this set within budget" against an aggregate; `check_corpus_convergence`
answers "which two books, and are they siblings, a series, or unrelated". The
second exists because a series pair sharing 8,164 body 4-grams survived the
first (`AL-564`), and it cannot gate yet: whether a series may repeat phrasing
deliberately is an open owner decision (`UW-C341`), and a bound invented here
would read as a ruling.

**Pairwise guards need pairs.** Convergence and device collision are properties
of a *set* of books, not of one, and the two most expensive failures in this
programme were both invisible to any single-book check. Pass every sibling in
one invocation, or those rows are skipped and say so.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from itertools import combinations
from pathlib import Path
from typing import NamedTuple

_HERE = Path(__file__).resolve().parent

# Convergence and device collision are properties of a set, not of a book.
_PAIR = 2


class Result(NamedTuple):
    """One guard's outcome."""

    guard: str
    scope: str
    ok: bool
    detail: str
    gating: bool


def _run(script: str, *args: str) -> tuple[int, str]:
    """Run a checker and return its exit code and last meaningful line."""
    proc = subprocess.run(
        [sys.executable, str(_HERE / script), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [
        line.strip()
        for line in (proc.stdout + proc.stderr).splitlines()
        if line.strip()
    ]
    summary = next(
        (line for line in reversed(lines) if line.startswith(("ok", "FAIL"))),
        lines[-1] if lines else "",
    )
    return proc.returncode, summary[:88]


def battery(
    skeleton: str,
    contract: str,
    filled: list[str],
    bindings: list[str],
    series_books: int | None = None,
) -> list[Result]:
    """Run every guard over one or more sibling books.

    Args:
        skeleton: The shared skeleton.
        contract: A narrative contract over it.
        filled: One or more finished storybooks.
        bindings: Zero or more device selections, one per book.
        series_books: How many books the contract must ultimately support.
            Defaults to the number given, which checks feasibility for these
            books only. Pass the intended series length when validating part
            of a series, or the vocabulary check passes on a subset while the
            contract is already infeasible at a later book.

    Returns:
        Every guard's Result, per book and per sibling pair.
    """
    series_books = series_books if series_books is not None else len(filled)
    out: list[Result] = []
    for book in filled:
        name = Path(book).stem
        for script, args in (
            ("check_graph_structure.py", (book, "--check")),
            ("check_fill_integrity.py", (skeleton, book)),
            ("run_story_gate.py", (book,)),
            # --check is what makes this one gate. Without it check_prose_craft
            # returns 0 unconditionally (its main() is `if args.check and
            # breached: return 1`), so recording it gating=True while invoking
            # it bare put a guard that could not fail into the gating
            # denominator. check_fill_integrity and run_story_gate below need
            # no flag; they gate on `return 1 if failed else 0` already.
            ("check_prose_craft.py", (book, "--check")),
            ("check_reading_level.py", (book, "--check")),
            ("check_label_template.py", (book, "--check")),
        ):
            code, detail = _run(script, *args)
            out.append(Result(script[:-3], name, code == 0, detail, gating=True))

    # Contract-scoped, so it runs once however many books share the contract.
    code, detail = _run("check_promise_discharge.py", skeleton, contract, "--check")
    out.append(
        Result("check_promise_discharge", "contract", code == 0, detail, gating=True)
    )

    # Also contract-scoped, and deliberately ordered after nothing: it is the
    # UPSTREAM feasibility question. check_device_collision below asks whether
    # these books collided; this asks whether the contract's vocabulary could
    # have let them avoid it. A contract that runs out of kinds fails here on
    # one JSON read, instead of downstream as a diversity failure that no
    # amount of re-binding fixes (AL-195: a wasted rated round is the price).
    # --check is what makes it gate, per the check_prose_craft note above.
    code, detail = _run(
        "check_device_vocabulary.py",
        contract,
        "--books",
        str(series_books),
        "--check",
    )
    out.append(
        Result(
            "check_device_vocabulary",
            f"contract, {series_books} book(s)",
            code == 0,
            detail,
            gating=True,
        )
    )

    if len(filled) >= _PAIR:
        code, detail = _run("check_sibling_fills.py", *filled, "--check")
        out.append(
            Result(
                "check_sibling_fills", "all siblings", code == 0, detail, gating=True
            )
        )
    else:
        out.append(
            Result(
                guard="check_sibling_fills",
                scope="skipped",
                ok=True,
                detail="one book given; convergence is a property of a set",
                gating=False,
            )
        )

    if len(filled) >= _PAIR:
        # No --check: the tool refuses a bound it was not given, and where the
        # bound belongs is an open owner decision (UW-C341). Reported, never
        # gating, until it is ruled.
        code, detail = _run("check_corpus_convergence.py", *filled, "--top", "3")
        out.append(
            Result(
                "check_corpus_convergence",
                "all pairs, relationship-labelled",
                code == 0,
                detail,
                gating=False,
            )
        )
    else:
        out.append(
            Result(
                guard="check_corpus_convergence",
                scope="skipped",
                ok=True,
                detail="one book given; a pair is the unit of convergence",
                gating=False,
            )
        )

    if len(bindings) >= _PAIR:
        for left, right in combinations(bindings, 2):
            code, detail = _run("check_device_collision.py", left, right, "--check")
            out.append(
                Result(
                    "check_device_collision",
                    f"{Path(left).stem} vs {Path(right).stem}",
                    code == 0,
                    detail,
                    gating=True,
                )
            )
    else:
        out.append(
            Result(
                guard="check_device_collision",
                scope="skipped",
                ok=True,
                detail="fewer than two bindings given",
                gating=False,
            )
        )
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 1 with --check when any gating guard fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeleton")
    parser.add_argument("contract")
    parser.add_argument("filled", nargs="+")
    parser.add_argument("--binding", action="append", default=[], dest="bindings")
    parser.add_argument(
        "--series-books",
        type=int,
        default=None,
        help=(
            "how many books the contract must support (default: the number "
            "of books given). Pass the intended series length when checking "
            "a subset."
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.series_books is not None and args.series_books < 1:
        sys.stderr.write(
            f"error: --series-books must be at least 1, got {args.series_books}\n"
        )
        return 2

    results = battery(
        args.skeleton,
        args.contract,
        args.filled,
        args.bindings,
        args.series_books,
    )
    width = max(len(r.guard) for r in results)
    for r in results:
        mark = "ok  " if r.ok else "FAIL"
        sys.stdout.write(f"{mark}  {r.guard:{width}s}  {r.scope:22s}  {r.detail}\n")

    failed = [r for r in results if not r.ok and r.gating]
    gating = [r for r in results if r.gating]
    advisory = [r for r in results if not r.gating]
    skipped = [r for r in results if r.detail.lower().startswith("skipped")]
    # Report the gating denominator, not the total. Counting advisory and
    # skipped checks toward "clear" let a single-book run print a fully green
    # battery while every pairwise guard had been skipped for want of a sibling,
    # which is the one case where a reader most needs to see the gap.
    sys.stdout.write(
        f"\n{len(gating) - len(failed)} of {len(gating)} GATING guards clear"
        f"  ({len(advisory)} advisory, {len(skipped)} skipped)\n"
    )
    if skipped:
        sys.stdout.write(
            "skipped, so this battery says nothing about them: "
            + ", ".join(sorted({r.guard for r in skipped}))
            + "\n"
        )
    sys.stdout.write(
        "NOT run, and not implied by a green battery: obligation delivery and "
        "prose entailment, which need a model (see "
        "build_prose_review_worklist.py)\n"
    )
    if failed:
        sys.stderr.write(
            f"FAIL guard battery: {len(failed)} guard(s) failed: "
            f"{', '.join(sorted({r.guard for r in failed}))}\n"
        )
    return 1 if (failed and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
