"""Run every guard a book must clear, in one command, with the right defaults.

Usage:
    uv run python scripts/run_guard_battery.py <skeleton.json> <contract.json>
        <filled.json>... [--check] [--binding sel.json]...
    uv run python scripts/run_guard_battery.py --corpus [--check] [--jobs N]

**``--corpus`` runs the battery over every committed fill, and is what CI
invokes.** `UW-C453` / `AL-726`: every guard below was registered
``gating=True`` inside a harness that no workflow, hook or nox session ran, so
a green battery was a claim nobody had made. The corpus mode enumerates the
tree deterministically, one tuple per ``out/<slug>.filled.json``:

* skeleton: the unique ``skeletons/<band>/<slug>.json`` (a fill whose slug
  matches no shell, or more than one, is a corpus defect and fails the run);
* contract: ``skeletons/<band>/<slug>.narrative.json`` when present. This is
  the NARRATIVE contract the two contract-scoped guards read. The theme
  contract sidecar (``<slug>.contract.json``) is a different document with no
  ``world_recipe``, and handing it to ``check_device_vocabulary`` produces a
  DV-0 "nothing to check" error on every book, so it is never substituted. A
  book with no narrative contract has those two rows reported as skipped, in
  the summary's skipped count, rather than silently passed;
* bindings: none. Each committed shell has exactly one fill, so the pairwise
  guards (sibling fills, corpus convergence, device collision) skip in this
  mode and the summary says so; they gate at authoring time when a sibling
  set is passed by hand.

``--jobs`` runs books concurrently (each guard is a subprocess and start-up
dominates); output order is fixed by slug regardless of completion order.

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
first (`AL-564`). It reports rather than gates because no bound on this RATE
has been ruled; the series case is gated instead by validator rule SR-10, on
run length, which `scripts/build_series_book.py` already runs (`AL-568`).

**Pairwise guards need pairs.** Convergence and device collision are properties
of a *set* of books, not of one, and the two most expensive failures in this
programme were both invisible to any single-book check. Pass every sibling in
one invocation, or those rows are skipped and say so.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path
from typing import NamedTuple

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

# The committed fill corpus, per docs/planning/draft-stories-manifest.md: one
# finished book per shell, flat under out/. Pilot re-themes (out/pilot/fills)
# and vendor pools (out/w4w5-pool, ...) are measurement fixtures, not the
# catalog's books, and are out of scope on purpose.
_FILLED_SUFFIX = ".filled.json"
_NARRATIVE_SUFFIX = ".narrative.json"

# Convergence and device collision are properties of a set, not of a book.
_PAIR = 2


class Result(NamedTuple):
    """One guard's outcome."""

    guard: str
    scope: str
    ok: bool
    detail: str
    gating: bool


class Book(NamedTuple):
    """One committed (skeleton, narrative contract, filled) tuple."""

    slug: str
    skeleton: Path
    contract: Path | None
    filled: Path


def corpus_books(repo_root: Path = _REPO_ROOT) -> list[Book]:
    """Enumerate the committed fill corpus deterministically.

    Args:
        repo_root: The repository root holding ``out/`` and ``skeletons/``.

    Returns:
        One Book per ``out/<slug>.filled.json``, sorted by slug.

    Raises:
        FileNotFoundError: If a fill names a slug no shell carries, or no
            fills exist at all. An empty corpus would make a green run
            vacuous, which is the one outcome this mode exists to prevent.
        ValueError: If a slug resolves to more than one shell; the battery
            cannot know which skeleton the fill was written against.
    """
    fills = sorted((repo_root / "out").glob(f"*{_FILLED_SUFFIX}"))
    if not fills:
        msg = f"no {_FILLED_SUFFIX} files under {repo_root / 'out'}"
        raise FileNotFoundError(msg)
    books: list[Book] = []
    for filled in fills:
        slug = filled.name[: -len(_FILLED_SUFFIX)]
        shells = sorted((repo_root / "skeletons").glob(f"*/{slug}.json"))
        if not shells:
            msg = f"{filled} names slug {slug!r} but no skeletons/*/{slug}.json exists"
            raise FileNotFoundError(msg)
        if len(shells) > 1:
            msg = f"slug {slug!r} resolves to {len(shells)} shells: {shells}"
            raise ValueError(msg)
        skeleton = shells[0]
        contract = skeleton.with_name(f"{slug}{_NARRATIVE_SUFFIX}")
        books.append(
            Book(slug, skeleton, contract if contract.is_file() else None, filled)
        )
    return books


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
    contract: str | None,
    filled: list[str],
    bindings: list[str],
    series_books: int | None = None,
) -> list[Result]:
    """Run every guard over one or more sibling books.

    Args:
        skeleton: The shared skeleton.
        contract: A narrative contract over it, or None when the shell has
            none, in which case the two contract-scoped guards are reported
            as skipped (never as passed) so the summary's skipped count
            discloses them.
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

    if contract is None:
        # A skipped row, not a passed one: the detail must start with
        # "skipped" so main()'s summary counts it and names the guard.
        no_contract = "skipped: no narrative contract sidecar for this shell"
        out.extend(
            Result(
                guard=guard,
                scope="skipped",
                ok=True,
                detail=no_contract,
                gating=False,
            )
            for guard in ("check_promise_discharge", "check_device_vocabulary")
        )
        return _pairwise(filled, bindings, out)

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

    return _pairwise(filled, bindings, out)


def _pairwise(
    filled: list[str], bindings: list[str], out: list[Result]
) -> list[Result]:
    """Append the set-scoped guards (sibling fills, convergence, collision).

    Args:
        filled: The sibling books.
        bindings: Their device selections, if any.
        out: The per-book and contract rows already collected.

    Returns:
        ``out``, extended in place.
    """
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
        # No --check, permanently. UW-C341 was ruled on 2026-08-23 (AL-568)
        # and the ruling was that a per-1000 RATE is the wrong axis: it cannot
        # separate a deliberate refrain from a reused passage. Gating moved to
        # validator rule SR-10, which bounds run LENGTH. This row survives as
        # the ranked view that names the offending pair, which SR-10's
        # per-chain verdict does not, so it reports and never gates.
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


def _print_rows(results: list[Result]) -> None:
    """Print one aligned line per guard result."""
    width = max(len(r.guard) for r in results)
    for r in results:
        mark = "ok  " if r.ok else "FAIL"
        sys.stdout.write(f"{mark}  {r.guard:{width}s}  {r.scope:22s}  {r.detail}\n")


def _summarize(results: list[Result]) -> list[Result]:
    """Print the gating-denominator summary and return the failed gating rows.

    Args:
        results: Every guard result from one or more batteries.

    Returns:
        The rows that failed AND gate; advisory failures are not among them.
    """
    failed = [r for r in results if not r.ok and r.gating]
    gating = [r for r in results if r.gating]
    advisory = [r for r in results if not r.gating]
    skipped = [r for r in results if r.detail.lower().startswith("skipped")]
    # Report the gating denominator, not the total. Counting advisory and
    # skipped checks toward "clear" let a single-book run print a fully green
    # battery while every pairwise guard had been skipped for want of a sibling,
    # which is the one case where a reader most needs to see the gap.
    clear = len(gating) - len(failed)
    sys.stdout.write(
        f"\n{clear} of {len(gating)} GATING guards clear  "
        f"({len(advisory)} advisory, {len(skipped)} skipped)\n"
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
        names = ", ".join(sorted({r.guard for r in failed}))
        sys.stderr.write(
            f"FAIL guard battery: {len(failed)} guard(s) failed: {names}\n"
        )
    return failed


def corpus_battery(books: list[Book], jobs: int) -> dict[str, list[Result]]:
    """Run one single-book battery per committed book, concurrently.

    Args:
        books: The enumerated corpus.
        jobs: How many books to run at once.

    Returns:
        Each book's results, keyed by slug, in the order ``books`` was given.
    """

    def _one(book: Book) -> list[Result]:
        return battery(
            str(book.skeleton),
            None if book.contract is None else str(book.contract),
            [str(book.filled)],
            [],
        )

    # #ASSUME: concurrency: battery() shares no mutable state across books
    # (each guard is its own subprocess and every Result is built from that
    # call's return), so a thread pool is safe and the only shared resource is
    # CPU. #VERIFY: tests/unit/test_guard_battery_wiring.py runs corpus_battery
    # with jobs=3 over a stubbed _run and asserts every book's rows are present
    # and attributed to the right slug.
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        per_book = list(pool.map(_one, books))
    return {book.slug: rows for book, rows in zip(books, per_book, strict=True)}


def _run_corpus(repo_root: Path, jobs: int, check: bool) -> int:
    """Run and report the whole committed corpus. Returns the process exit code."""
    try:
        books = corpus_books(repo_root)
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"error: corpus enumeration failed: {exc}\n")
        return 2
    with_contract = sum(1 for b in books if b.contract is not None)
    sys.stdout.write(
        f"corpus: {len(books)} committed fill(s) under {repo_root / 'out'}, "
        f"{with_contract} with a narrative contract, {jobs} job(s)\n"
    )
    per_book = corpus_battery(books, jobs)
    everything: list[Result] = []
    red_books: dict[str, list[str]] = {}
    for book in books:
        rows = per_book[book.slug]
        everything.extend(rows)
        contract = "-" if book.contract is None else book.contract.name
        sys.stdout.write(f"\n=== {book.slug}  ({book.skeleton}, contract {contract})\n")
        _print_rows(rows)
        failed_here = sorted({r.guard for r in rows if not r.ok and r.gating})
        if failed_here:
            red_books[book.slug] = failed_here

    # The per-book and per-guard tallies are what a reader needs to act on a
    # red run: "which books, which guard" rather than one aggregate count.
    sys.stdout.write("\n=== corpus summary\n")
    by_guard: dict[str, int] = {}
    for r in everything:
        if not r.ok and r.gating:
            by_guard[r.guard] = by_guard.get(r.guard, 0) + 1
    clear_books = len(books) - len(red_books)
    sys.stdout.write(
        f"books: {clear_books} of {len(books)} clear every gating guard run on them\n"
    )
    for guard, count in sorted(by_guard.items(), key=lambda kv: (-kv[1], kv[0])):
        sys.stdout.write(f"  {guard:26s} fails on {count} book(s)\n")
    for slug, guards in red_books.items():
        sys.stdout.write(f"  {slug}: {', '.join(guards)}\n")
    failed = _summarize(everything)
    return 1 if (failed and check) else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 1 with --check when any gating guard fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="<skeleton.json> <contract.json> <filled.json>... (omit with --corpus)",
    )
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
    parser.add_argument(
        "--corpus",
        action="store_true",
        help=(
            "run one battery per committed out/<slug>.filled.json, resolving "
            "its skeleton and narrative contract from skeletons/ (what CI runs)"
        ),
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=min(4, os.cpu_count() or 1),
        help="books to run concurrently in --corpus mode (default: min(4, cpus))",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.series_books is not None and args.series_books < 1:
        sys.stderr.write(
            f"error: --series-books must be at least 1, got {args.series_books}\n"
        )
        return 2

    if args.corpus:
        if args.paths or args.bindings or args.series_books is not None:
            sys.stderr.write(
                "error: --corpus enumerates the tree itself; it takes no paths, "
                "--binding or --series-books\n"
            )
            return 2
        return _run_corpus(_REPO_ROOT, args.jobs, args.check)

    if len(args.paths) < 3:
        parser.error("expected <skeleton.json> <contract.json> <filled.json>...")
    skeleton, contract, *filled = args.paths
    results = battery(skeleton, contract, filled, args.bindings, args.series_books)
    _print_rows(results)
    failed = _summarize(results)
    return 1 if (failed and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
