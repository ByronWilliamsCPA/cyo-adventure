"""Score the judge panel against known-bad books, per criterion (W7).

The panel is an instrument nobody has validated. Every ranking-shaped claim in
Part IV rests on it, W11's pilot scoring needs it, and best-of-N would select on
it. This is the battery that says which of its criteria are worth trusting.

**The unit is the criterion, not the panel.** W7's rule retires a criterion that
fails to detect its own seeded defect, or that fires on the clean control. A
panel-level pass or fail would average a working criterion together with a blind
one and hide both.

**The comparison is within-book.** Each defect arm is scored against the *same
book's* control, not against the corpus mean. A judge's opinion of a book is
mostly an opinion of the book; pairing removes that and leaves the defect.
It also removes any constant offset from the panel's criteria being written for
one age band while the corpus spans three, which is the stated limit of this run
rather than a confound in it.

**Agreement is scored against our own floor.** Kappa 0.60, cited to Landis and
Koch (1977), not the 0.80 a review proposed: 0.80 sits in the "almost perfect"
band that human raters routinely miss, so adopting it would retire criteria for
being ordinarily noisy.

Usage::

    uv run python scripts/seed_defects.py <books> --out out/w7/arms
    uv run python scripts/w7_battery.py --arms out/w7/arms --prepare <books>
    uv run python scripts/w7_battery.py --arms out/w7/arms --out out/w7 --env-file .env
    uv run python scripts/w7_battery.py --replay out/w7/verdicts.json
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import json
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.core.config import Settings  # noqa: E402
from cyo_adventure.generation.metered import MeteredProvider  # noqa: E402
from cyo_adventure.generation.provider import build_openrouter_leg  # noqa: E402
from cyo_adventure.generation.usage import UsageLedger  # noqa: E402
from cyo_adventure.validator.reading_level import measure_book  # noqa: E402
from scripts._paid_output import (  # noqa: E402
    ensure_persistable,
    persistence_notice,
)
from scripts.judge_books import (  # noqa: E402
    _CRITERIA,
    _PANEL,
    Judge,
    Verdict,
    judge_book,
)
from scripts.seed_defects import (  # noqa: E402
    _sensory_density,  # pyright: ignore[reportPrivateUsage]
    verify,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

# Which criterion each seeded defect is supposed to be detected by. This mapping
# IS the hypothesis under test: a criterion that does not move on its own defect
# has failed its half of the rule, whatever it does elsewhere.
DEFECT_CRITERION: Final[dict[str, str]] = {
    "ending_truncated": "ending_quality",
    "imagery_flat": "imagery",
    "dialogue_flat": "dialogue",
    "dialogue_added": "dialogue",
    "false_choice": "choice_quality",
    "reading_level_up": "age_fit",
    "premise_duplicate": "engagement",
}

# `tense_break` is deliberately absent, and its absence is the correction of a
# wrong hypothesis rather than an omission. It was mapped to `voice`, which
# retired that criterion at 1 of 6 on 2026-08-14. The two are different
# properties: `voice` asks "Distinctness and consistency of the main character.
# 1 = interchangeable narrator with no personality", and the seed switches the
# NARRATOR'S TENSE. A judge assessing whether the protagonist is a distinct
# person should not move when the narrator's grammar wobbles, and two of the
# three judges did exactly that, holding at 0.00 across all six books; only the
# noisiest judge moved, and it moved in both directions. The mapping asserted a
# hypothesis the rubric does not support, so the arm tested nothing and `voice`
# is UNTESTED rather than retired.
#
# No criterion in the panel covers narrative tense stability. That is fine and
# deliberate: `check_prose_craft.py` measures it deterministically, which is
# the better instrument for it.
_UNMAPPED_DEFECTS: Final[frozenset[str]] = frozenset({"tense_break"})

# A criterion must move at least this far, on the 1-to-5 scale, against its own
# book's control before the movement counts as detection. Set below one scale
# point deliberately: a judge that reliably drops a book by half a point on a
# real defect is discriminating, and demanding a whole point would retire
# criteria for being calibrated rather than for being blind.
_DETECTION_MARGIN: Final[float] = 0.5

# How far a criterion must move on an arm it does not own before that movement
# is worth recording. Recorded only: see `CriterionVerdict.cross_arm_moves` for
# why this cannot be read as a false-positive rate.
_CROSS_ARM_MARGIN: Final[float] = _DETECTION_MARGIN

_KAPPA_FLOOR: Final[float] = 0.60

# How many US reading grades the `reading_level_up` seed aims to add. Three is
# roughly a band's width in this catalogue, so the result is a book that is
# genuinely wrong for its declared band rather than one that merely reads a
# little older.
_HARDEN_GRADES: Final[float] = 3.0

# Nodes shorter than this are left alone: rewriting a ten-word body is a
# replacement, not a reworking, and the seed would then be measuring
# substitution rather than difficulty.
_MIN_HARDENABLE_WORDS: Final[int] = 15

_HARDEN_CONCURRENCY: Final[int] = 6

# The model that writes the harder prose. Sonnet 5 rather than the cheaper
# default: this seed has to produce a book that is genuinely too old for its
# band while still reading like a book, and a weak rewrite yields an arm that
# fails to land, which costs an opportunity rather than saving money. It is a
# fixture model and has nothing to do with which model the pipeline generates
# with.
_HARDEN_MODEL: Final[str] = "anthropic/claude-sonnet-5"

# Share of a book's concrete-sensory vocabulary the `imagery_flat` arm keeps.
# Chosen so the arm is a book that has lost most of its detail rather than one
# rewritten into pure abstraction, for the same reason `_HARDEN_GRADES` is 3
# rather than 10: a defect three times its stated size measures the panel's
# eyesight, not its sensitivity.
_IMAGERY_KEEP: Final[float] = 0.4

__all__ = ["CriterionVerdict", "load_panel", "score_battery"]


def load_panel(path: Path | None) -> tuple[Judge, ...]:
    """Return the judge panel, from *path* or the built-in frontier default.

    The panel is a parameter rather than a constant because W7 has two jobs
    now. It validates the criteria against a fixed panel, and it validates a
    *panel* against criteria already known to work, which is what picking a
    distillation parent requires: run an open-weight candidate over the same
    43 arms and compare its per-criterion detection to the frontier panel's.

    Args:
        path: JSON array of ``{label, model, provider_order, family}`` objects,
            or ``None`` for the built-in panel.

    Returns:
        The panel.

    Raises:
        ValueError: If the file is not a non-empty array of objects. A panel
            that silently falls back to the default would attribute an
            open-weight run's numbers to the frontier judges.
    """
    if path is None:
        return _PANEL
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        msg = f"{path} must hold a non-empty JSON array of judge objects"
        raise ValueError(msg)

    # A row marked `pending` is a slot held open for a model we intend to test
    # and currently cannot, usually because nothing is serving it. Keeping it in
    # the slate rather than in a comment is the point: the gap stays visible
    # where the panel is defined, and picking it up later is removing a flag
    # rather than remembering a conversation.
    pending = [str(r["label"]) for r in rows if r.get("pending")]
    if pending:
        print(
            f"  Slots held open, not judged: {', '.join(pending)}.",
            file=sys.stderr,
        )
    active = [r for r in rows if not r.get("pending")]
    if not active:
        msg = f"{path} holds no judge that is not pending"
        raise ValueError(msg)
    return tuple(
        Judge(
            label=str(row["label"]),
            model=str(row["model"]),
            provider_order=tuple(row.get("provider_order") or ()),
            family=str(row.get("family", "unknown")),
        )
        for row in active
    )


@dataclass(frozen=True, slots=True)
class CriterionVerdict:
    """What the battery concluded about one criterion.

    Attributes:
        criterion: The criterion's name.
        defect: The seeded defect it was supposed to detect, or empty when no
            defect targets it and it was only checked for false positives.
        detections: Books where the criterion dropped by the margin on its own
            defect arm, against that same book's control.
        opportunities: Books where it could have.
        cross_arm_moves: Arms carrying a defect some OTHER criterion owns on
            which this criterion still moved by more than the margin. Named for
            what it counts rather than "false positives", which is what it was
            called and is not what it measures: no arm in this fixture carries a
            single isolated defect, so `reading_level_up` really does change
            voice and `premise_duplicate` really does change engagement. A high
            count here is mostly a criterion correctly noticing collateral
            change, and it decides nothing.
        control_noise: Pooled between-judge standard deviation on the control
            arms for this criterion. This is the honest version of the "fires on
            a clean book" test: with no repeat scorings there is no way to ask
            one judge the same question twice, but the panel's disagreement
            about an undefected book is the floor any detection has to clear to
            be more than scoring noise.
        deltas: Per-book movement on the defect arm, for the record.
        verdict: RETIRE, KEEP, or UNTESTED, with the reason.
    """

    criterion: str
    defect: str
    detections: int
    opportunities: int
    cross_arm_moves: int
    control_noise: float | None
    deltas: list[float]
    verdict: str

    @property
    def detection_rate(self) -> float | None:
        """Share of opportunities on which the criterion noticed its defect.

        Returns:
            The rate, or ``None`` when it was never given an opportunity.
        """
        if not self.opportunities:
            return None
        return self.detections / self.opportunities


@contextlib.contextmanager
def single_run(out_dir: Path) -> Generator[None]:
    """Refuse to start when another instance is already writing to *out_dir*.

    W7's judging pass was once relaunched on the evidence of a missing log file
    while the original process was still running. Two panels went through 93
    scorings each against the same arms: $4.94 where one run was about $2. The
    artefact would not have shown it, because both write `verdicts.json` at the
    end and the survivor's file is indistinguishable from a clean single run.

    Absence of output is the expected state for most of a paid run's life, so it
    can never be the signal to retry. This makes that structural rather than a
    thing an operator has to remember.

    Args:
        out_dir: The run's output directory.

    Yields:
        Nothing; the lock is held for the block.

    Raises:
        RuntimeError: If a live process already holds the lock. The message
            carries the other pid so an operator can check it rather than guess.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    lock = out_dir / ".run.lock"
    if lock.exists():
        holder = lock.read_text(encoding="utf-8").strip()
        if _alive(holder):
            msg = (
                f"another run (pid {holder}) is already writing to {out_dir}. "
                "A paid run produces no output until it finishes, so a quiet log "
                "is not a dead process; check that pid before starting another."
            )
            raise RuntimeError(msg)
        print(
            f"  clearing a stale lock from pid {holder}, which is gone.",
            file=sys.stderr,
        )
    lock.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


# The largest pid either platform's probe can carry without changing the
# question being asked. POSIX `os.kill` converts through C `int` and raises
# `OverflowError` at exactly 2**31; the Win32 probe takes a `c_uint32` DWORD,
# and ctypes converts an out-of-range int mod 2**32 rather than raising, so an
# oversized value silently becomes a different, possibly live, pid. 2**31 - 1
# is under both, and far above any pid either kernel issues.
_MAX_PID: Final[int] = 2**31 - 1


def _alive(pid: str) -> bool:
    """Return whether *pid* names a live process.

    Args:
        pid: A process id as written into the lock file.

    Returns:
        ``True`` when the process exists. Anything outside ``1.._MAX_PID``,
        including a value no integer can be read out of, reads as dead, so a
        corrupted lock cannot wedge the harness permanently.
    """
    try:
        numeric = int(pid)
    except ValueError:
        return False
    if not 0 < numeric <= _MAX_PID:
        # A lock is written with `os.getpid()`, so a value outside this range is
        # a corrupted file rather than a process, and every way of passing one
        # through is worse than reading it as dead.
        #
        # Below the range, POSIX `kill` inverts the answer instead of erroring:
        # 0 means the caller's own process group and -1 means every process it
        # may signal, so both succeed and report a live holder that does not
        # exist. On Windows a negative value is converted mod 2**32 against the
        # `c_uint32` argtype below, so `-1` asks about pid 4294967295 and any
        # answer is about some unrelated process. (Windows pid 0 is the one
        # benign case: `OpenProcess` rejects the System Idle Process with
        # ERROR_INVALID_PARAMETER, which already reads as dead.
        # ERROR_ACCESS_DENIED, the code that reads as live, is what the System
        # process and the CSRSS processes return, not pid 0.)
        #
        # Above the range, `os.kill` raises `OverflowError` converting to C
        # `int`, which is a crash rather than an answer, and Windows truncates
        # as above, so a lock holding 2**32 + 1234 would probe pid 1234 and an
        # innocent live process would hold the lock forever.
        #
        # Either direction, a corrupted lock would wedge the harness
        # permanently, which is the one outcome this guard must never produce.
        return False
    if sys.platform == "win32":
        return _alive_windows(numeric)
    try:
        os.kill(numeric, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # It exists and belongs to someone else, which still counts as live.
        return True
    return True


def _alive_windows(pid: int) -> bool:
    """Return whether *pid* names a live process, on Windows.

    `os.kill(pid, 0)` is a POSIX idiom that does not survive the port. Signal 0
    is `CTRL_C_EVENT` on Windows, so CPython routes it to
    `GenerateConsoleCtrlEvent` rather than to a liveness check: against a pid
    that is not a console process group it fails with `WinError 87`, which is
    how this read as an error rather than as an answer, and against one that is
    it would *deliver a Ctrl-C* to a process the harness only meant to ask
    about. Neither outcome is a probe.

    `OpenProcess` plus `WaitForSingleObject` asks the actual question: whether
    the process handle is signaled. `GetExitCodeProcess` cannot answer it,
    because `STILL_ACTIVE` is 259 and 259 is also a perfectly legal exit code,
    so a previous run that exited 259 would read as live and wedge the harness
    for good. Microsoft documents the ambiguity and points at the wait
    functions instead. `ctypes` keeps this in the standard library rather than
    adding `psutil`, which this project has only as a transitive development
    dependency.

    Args:
        pid: A process id, already bounded to ``1.._MAX_PID`` by `_alive`.

    Returns:
        ``True`` when the process exists and has not exited.

    Raises:
        ValueError: If *pid* is outside the range the DWORD conversion can
            carry unchanged.
    """
    # `_alive` bounds the pid before dispatching here and is the only caller,
    # but restating the precondition is what keeps the `c_uint32` conversion
    # below honest: ctypes converts an out-of-range int mod 2**32 instead of
    # raising, so a caller that skipped the guard would quietly ask about a
    # different process rather than fail. Refusing is the loud alternative.
    if not 0 < pid <= _MAX_PID:
        msg = (
            f"pid {pid} is outside 1..{_MAX_PID}, the range this probe can ask "
            "about without the DWORD conversion changing which process it names"
        )
        raise ValueError(msg)

    import ctypes  # noqa: PLC0415 - Windows-only, kept out of the POSIX path

    # #ASSUME: external resources: the Win32 error, access-right and wait-result
    # constants below are stable ABI, documented in the Windows SDK headers, so
    # they are inlined rather than discovered at runtime.
    # #VERIFY: covered by tests/unit/test_w7_battery.py, which exercises this
    # branch on every platform through a fake kernel32.
    error_access_denied = 5
    error_invalid_parameter = 87
    # SYNCHRONIZE alone, not PROCESS_QUERY_LIMITED_INFORMATION: it is the only
    # right `WaitForSingleObject` needs, and asking for less is likelier to be
    # granted, so a restricted process gives a real answer instead of the
    # access-denied fallback below.
    synchronize = 0x0010_0000
    wait_object_0 = 0x0000_0000
    wait_timeout = 0x0000_0102

    # `OpenProcess`'s second parameter is `bInheritHandle`, which is positional
    # in the Win32 ABI and so cannot be passed by keyword (ruff FBT003); naming
    # it here says what the flag means instead of suppressing the rule.
    inherit_handle = False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # pyright: ignore[reportAttributeAccessIssue]

    # ctypes defaults every foreign function to a `c_int` return and to
    # by-guess argument conversion. Win32 `HANDLE` is pointer-sized, so on
    # 64-bit Windows an untyped `OpenProcess` truncates its handle to 32 bits,
    # and the truncated value is then passed back to `WaitForSingleObject` and
    # `CloseHandle`. Declaring the signatures keeps the handle intact and stops
    # a wrong one being waited on or closed. DWORD is `c_uint32`, BOOL is
    # `c_int`, HANDLE is `c_void_p`; a NULL `c_void_p` result arrives as None,
    # which is falsy, so the failure branch below still reads correctly.
    kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_int

    handle = kernel32.OpenProcess(synchronize, inherit_handle, pid)
    if not handle:
        code = ctypes.get_last_error()
        if code == error_access_denied:
            # It exists and belongs to someone else, which still counts as
            # live, matching the PermissionError arm of the POSIX path.
            return True
        if code == error_invalid_parameter:
            return False
        # An unrecognised failure must not be read as "dead": clearing the lock
        # on a guess is the exact double-run this guard exists to prevent.
        return True
    try:
        # A zero timeout polls rather than waits, so this never blocks the
        # caller on another run's lifetime.
        waited = kernel32.WaitForSingleObject(handle, 0)
        if waited == wait_timeout:
            return True
        if waited == wait_object_0:
            # Signaled means terminated. A handle can outlive the process it
            # names, so an openable pid is not yet a live one.
            return False
        # WAIT_FAILED, WAIT_ABANDONED, or anything undocumented: no answer, so
        # keep the lock rather than guess it away.
        return True
    finally:
        kernel32.CloseHandle(handle)


def _book_key(book: str) -> str:
    """Return an arm identifier with `judge_book`'s brief suffix removed.

    `judge_book` labels every verdict ``f"{leg}#{brief_index}"``, which is the
    right identity for the vendor comparison it was written for: there, one leg
    writes one book per brief and the index separates them. This battery passes
    the arm's file stem as the leg and has no briefs, so every verdict comes
    back as ``the-lost-mitten__control#0`` while the battery joins on
    ``the-lost-mitten__control``.

    Nothing matched, so every arm was invisible, every criterion reported zero
    opportunities, and the run printed seven UNTESTED verdicts over 93 perfectly
    good scorings. The failure was total rather than partial, which is the tell:
    a battery that is merely short of data reports some numbers.

    Args:
        book: A verdict's book identifier.

    Returns:
        The identifier up to the first ``#``.
    """
    return book.split("#", 1)[0]


def _mean_by_criterion(verdicts: Sequence[Verdict], book: str) -> dict[str, float]:
    """Average each criterion's score across the panel for one book.

    Args:
        verdicts: Every verdict.
        book: The book identifier, without a brief suffix.

    Returns:
        Criterion name to its panel-mean score. Missing criteria are absent
        rather than zero: a judge that failed to score one is not a judge that
        scored it badly.
    """
    rows = [
        v
        for v in verdicts
        if _book_key(v.book) == book and v.scores and v.error is None
    ]
    out: dict[str, float] = {}
    for name in _CRITERIA:
        values = [v.scores[name] for v in rows if name in v.scores]
        if values:
            out[name] = statistics.fmean(values)
    return out


def _control_noise(
    verdicts: Sequence[Verdict], arms: Sequence[tuple[str, str]], criterion: str
) -> float | None:
    """Return the panel's disagreement about undefected books, for one criterion.

    W7's rule has a second half: a criterion must not fire on a clean control.
    As written it was implemented by looking at *other* criteria's defect arms,
    which does not test that, because no arm in this fixture carries a single
    isolated defect. `reading_level_up` rewrites a third of the prose, so voice
    and imagery genuinely change; a criterion noticing that is working, not
    misfiring, and the old count charged it as an error.

    What the data can actually support is a noise floor. There are no repeat
    scorings, so a judge cannot be asked the same question twice, but three
    judges scoring the same undefected book give a direct read on how much this
    criterion moves when nothing has moved. A detection smaller than that floor
    is not distinguishable from scoring noise, whatever its sign.

    Args:
        verdicts: Every verdict from the run.
        arms: ``(book_stem, defect)`` pairs describing what each book is.
        criterion: The criterion being scored.

    Returns:
        The pooled between-judge standard deviation over control arms, or
        ``None`` when fewer than two controls carry two or more judge scores.
    """
    spreads: list[float] = []
    for stem, arm in arms:
        if arm != "control":
            continue
        scores = [
            v.scores[criterion]
            for v in verdicts
            if _book_key(v.book) == f"{stem}__control"
            and v.scores
            and v.error is None
            and criterion in v.scores
        ]
        if len(scores) >= 2:
            spreads.append(statistics.stdev(scores))
    if len(spreads) < 2:
        return None
    return statistics.fmean(spreads)


def score_battery(
    verdicts: Sequence[Verdict], arms: Sequence[tuple[str, str]]
) -> list[CriterionVerdict]:
    """Apply W7's per-criterion rule to a finished set of verdicts.

    Args:
        verdicts: Every verdict from the blind panel run.
        arms: ``(book_stem, defect)`` pairs describing what each book is.

    Returns:
        One verdict per criterion, in the order the criteria are declared.
    """
    by_book = {f"{stem}__{defect}": (stem, defect) for stem, defect in arms}
    controls = {
        stem: _mean_by_criterion(verdicts, f"{stem}__control")
        for stem, defect in arms
        if defect == "control"
    }

    out: list[CriterionVerdict] = []
    for criterion in _CRITERIA:
        defect = next((d for d, c in DEFECT_CRITERION.items() if c == criterion), "")
        deltas: list[float] = []
        detections = 0
        opportunities = 0
        cross_arm_moves = 0
        control_noise = _control_noise(verdicts, arms, criterion)

        for book, (stem, arm) in by_book.items():
            control = controls.get(stem)
            if control is None or criterion not in control:
                continue
            scored = _mean_by_criterion(verdicts, book)
            if criterion not in scored:
                continue
            delta = scored[criterion] - control[criterion]
            if arm == defect and defect:
                opportunities += 1
                deltas.append(delta)
                # Detection is a DROP: a seeded defect should lower the score of
                # the criterion that observes it.
                if delta <= -_DETECTION_MARGIN:
                    detections += 1
            elif arm not in {"control", defect} and abs(delta) > _CROSS_ARM_MARGIN:
                # This arm carries a defect some other criterion owns. That is
                # NOT evidence against this criterion: the arms are not
                # single-defect documents, so the movement is usually real.
                # Counted for the record, used for nothing.
                cross_arm_moves += 1

        out.append(
            CriterionVerdict(
                criterion=criterion,
                defect=defect,
                detections=detections,
                opportunities=opportunities,
                cross_arm_moves=cross_arm_moves,
                control_noise=control_noise,
                deltas=deltas,
                verdict=_verdict_for(
                    criterion, defect, detections, opportunities, deltas, control_noise
                ),
            )
        )
    return out


def _verdict_for(
    criterion: str,
    defect: str,
    detections: int,
    opportunities: int,
    deltas: Sequence[float],
    control_noise: float | None,
) -> str:
    """State the rule's conclusion for one criterion.

    Two gates, in order. The detection rate is the original rule. The noise
    floor is the honest replacement for the "fires on the clean control" half:
    a criterion whose median movement on its own defect does not exceed the
    panel's disagreement about an *undefected* book has not demonstrated it can
    tell the two apart, however often it happened to cross the margin.

    Args:
        criterion: The criterion's name.
        defect: The defect targeting it, or empty.
        detections: How many times it noticed.
        opportunities: How many times it could have.
        deltas: Per-book movement on the defect arm.
        control_noise: Between-judge spread on the control arms, or ``None``
            when too few controls carry two or more judge scores.

    Returns:
        The verdict line.
    """
    if not defect or not opportunities:
        return (
            f"UNTESTED: no seeded defect exercised {criterion}, so this run says "
            "nothing about it either way"
        )
    rate = detections / opportunities
    if rate <= 0.5:
        return (
            f"RETIRE: detected its own seeded {defect} on {detections} of "
            f"{opportunities} books. A criterion that misses the defect it "
            "exists to catch cannot support a ranking"
        )

    median = abs(statistics.median(deltas)) if deltas else 0.0
    if control_noise is not None and median <= control_noise:
        return (
            f"INCONCLUSIVE: detected its own seeded {defect} on {detections} of "
            f"{opportunities} books, but its median movement ({median:.2f}) does "
            f"not exceed the panel's disagreement about an undefected book "
            f"({control_noise:.2f}). The detections are not separable from "
            "scoring noise"
        )
    noise = (
        "" if control_noise is None else f", against a {control_noise:.2f} noise floor"
    )
    return (
        f"KEEP: detected its own seeded {defect} on {detections} of "
        f"{opportunities} books{noise}"
    )


def cohens_kappa(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Return Cohen's kappa between two judges' scores over the same books.

    Scores are binned to the integer scale before agreement is computed, since
    kappa is a categorical statistic and treating 3.0 and 3.4 as different
    categories would report disagreement that no rubric asked for.

    Args:
        a: One judge's scores.
        b: Another judge's scores over the same books, in the same order.

    Returns:
        Kappa, or ``None`` when the pair is too small or degenerate.
    """
    if len(a) != len(b) or len(a) < 2:
        return None
    left = [round(x) for x in a]
    right = [round(x) for x in b]
    labels = sorted(set(left) | set(right))
    if len(labels) < 2:
        # Both judges used one category throughout. Kappa is undefined here and
        # reporting 0.0 would read as total disagreement when the two agreed on
        # every book.
        return None
    observed = sum(1 for x, y in zip(left, right, strict=True) if x == y) / len(left)
    expected = sum(
        (left.count(label) / len(left)) * (right.count(label) / len(right))
        for label in labels
    )
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


def weighted_kappa(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Return quadratic-weighted kappa between two judges on one criterion.

    Replaces the unweighted :func:`cohens_kappa` for reporting, and the reason
    is that the unweighted form gave W7's first run an uninterpretable answer.
    It was fed each judge's *mean across all seven criteria*, rounded to an
    integer. After rounding, `judge-gpt-5.6` occupied two categories with 24 of
    31 books in one and `judge-grok-4.6` three with 23 of 31 in one: the
    skewed-marginals regime where kappa collapses despite high raw agreement.
    The reported figures matched that exactly, +0.58 between the two similarly
    skewed judges and about +0.15 for both pairings with the judge whose scale
    is spread wider. Those numbers measure scale spread, not agreement.

    Two changes. Quadratic weighting, because a 1-to-5 rubric is ordinal and
    scoring 3 against 4 is not the same failure as scoring 3 against 1; the
    unweighted form counts both as simple disagreement. And the caller passes
    one criterion's raw scores rather than a rounded average, because the
    criterion is W7's unit and averaging seven of them discards exactly the
    structure the run exists to examine.

    Args:
        a: One judge's scores on one criterion, one entry per arm.
        b: The other judge's scores over the same arms, in the same order.

    Returns:
        Kappa, or ``None`` when the pair is too small, or when neither judge
        varied at all and the statistic is undefined rather than zero.
    """
    if len(a) != len(b) or len(a) < 2:
        return None
    left = [round(x) for x in a]
    right = [round(x) for x in b]
    labels = sorted(set(left) | set(right))
    if len(labels) < 2:
        return None

    span = (len(labels) - 1) ** 2

    def weight(x: int, y: int) -> float:
        return 1.0 - ((labels.index(x) - labels.index(y)) ** 2) / span

    n = len(left)
    observed = sum(weight(x, y) for x, y in zip(left, right, strict=True)) / n
    expected = sum(
        (left.count(x) / n) * (right.count(y) / n) * weight(x, y)
        for x in labels
        for y in labels
    )
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


def _marginals(scores: Sequence[float]) -> str:
    """Summarise one judge's use of the scale, for printing beside a kappa.

    A kappa that collapses from skewed marginals is indistinguishable from one
    that collapses from real disagreement unless the marginals are shown. This
    is what makes that visible rather than something a reader has to suspect.

    Args:
        scores: One judge's scores on one criterion.

    Returns:
        A compact category count, e.g. ``"{2:7, 3:24}"``.
    """
    counts: dict[int, int] = {}
    for value in scores:
        counts[round(value)] = counts.get(round(value), 0) + 1
    return "{" + ", ".join(f"{k}:{v}" for k, v in sorted(counts.items())) + "}"


_FLATTEN_SYSTEM: Final[str] = (
    "You rewrite children's story prose to be LESS vivid, on purpose, for a "
    "measurement fixture. Keep every event, character, name and plot beat exactly "
    "as they are, and keep the length about the same. Remove concrete sensory "
    "detail: replace specific colours, textures, sounds, smells and named physical "
    "objects with generic, abstract wording ('a bright red mitten' becomes 'the "
    "item', 'the floorboard creaked' becomes 'there was a noise'). Do not add or "
    "remove events. Return only the rewritten prose for the passage given, with no "
    "commentary."
)

_HARDEN_SYSTEM: Final[str] = (
    "You rewrite children's story prose to be HARDER to read, on purpose, for a "
    "measurement fixture. Keep every event, character, name and plot beat exactly "
    "as they are. Change only the language: longer sentences, subordinate clauses, "
    "abstract and polysyllabic vocabulary in place of concrete simple words. Do "
    "not add or remove events. Do not change who does what. Return only the "
    "rewritten prose for the passage given, with no commentary."
)


async def harden_book(
    doc: dict[str, Any], provider: object, *, grades: float
) -> dict[str, Any]:
    """Rewrite a book's prose to raise its reading grade, via generation.

    The other four seeds are mechanical, and this one deliberately is not. A
    formula can raise Flesch-Kincaid by padding syllables, but the result stops
    reading like a book, and a judge scoring "would a child want to read on"
    would then be reacting to word salad rather than to a harder text. The point
    of the fixture is a book that is genuinely too old for its band while still
    being a book.

    Args:
        doc: The passing book.
        provider: A ``GenerationProvider``; each node is rewritten in one call.
        grades: How many grades harder to aim for.

    Returns:
        A copy with rewritten bodies. A node whose rewrite fails keeps its
        original prose rather than being dropped, so a partial failure lowers
        the seed's strength rather than corrupting the book; `verify` then
        reports the grade rise that actually landed.
    """
    out = copy.deepcopy(doc)
    nodes = out.get("nodes")
    if not isinstance(nodes, list):
        return out

    # Bounded concurrency rather than a sequential loop. A six-book corpus is
    # 213 hardenable nodes and one call each; serialised at a few seconds per
    # call that is most of an hour of wall clock, which is long enough that an
    # operator starts wondering whether to kill it. The bound is low because the
    # cap is the provider's rate limit, not ours.
    return await _rewrite_nodes(
        out,
        provider,
        system=_HARDEN_SYSTEM,
        instruction=(
            f"Rewrite this passage about {grades:.0f} US reading grades harder, "
            "preserving every event exactly:"
        ),
        label="harden",
    )


async def flatten_book(doc: dict[str, Any], provider: object) -> dict[str, Any]:
    """Rewrite a book's prose to strip concrete sensory detail, via generation.

    Seeds `imagery_flat`, the arm the `imagery` criterion had none of. Like the
    reading-level seed this cannot be faked by a formula: removing specific
    colours, textures and sounds while keeping the events and the length is a
    rewrite, and a lexical substitution would leave prose no reader would accept
    as a book. Also like it, the raw rewrite overshoots, so `prepare_arms`
    blends it back to a stated magnitude rather than shipping it whole.

    Args:
        doc: The passing book.
        provider: A ``GenerationProvider``; each eligible node costs one call.

    Returns:
        A copy with the prose flattened. A node whose rewrite fails keeps its
        original text, so a partial failure weakens the seed rather than
        corrupting the book, and `verify` reports what actually landed.
    """
    return await _rewrite_nodes(
        copy.deepcopy(doc),
        provider,
        system=_FLATTEN_SYSTEM,
        instruction=(
            "Rewrite this passage with the concrete sensory detail removed, "
            "preserving every event and roughly the length:"
        ),
        label="flatten",
    )


async def _rewrite_nodes(
    out: dict[str, Any],
    provider: object,
    *,
    system: str,
    instruction: str,
    label: str,
) -> dict[str, Any]:
    """Rewrite every eligible node body of *out* in place, concurrently.

    Args:
        out: The document to rewrite, already a copy.
        provider: A ``GenerationProvider``.
        system: The system prompt describing the rewrite.
        instruction: The per-node instruction, prepended to the body.
        label: Name used in the failure message.

    Returns:
        *out*, rewritten.
    """
    nodes = out.get("nodes")
    if not isinstance(nodes, list):
        return out

    # Bounded concurrency rather than a sequential loop. A six-book corpus is
    # 224 eligible nodes and one call each; serialised at a few seconds per call
    # that is most of an hour of wall clock. The bound is low because the cap is
    # the provider's rate limit, not ours.
    semaphore = asyncio.Semaphore(_HARDEN_CONCURRENCY)

    async def rewrite(node: dict[str, Any]) -> None:
        body = str(node.get("body", ""))
        if len(body.split()) < _MIN_HARDENABLE_WORDS:
            # Too short to rework meaningfully; a rewrite would be a
            # replacement rather than a reworking.
            return
        async with semaphore:
            try:
                completion = await provider.complete(  # pyright: ignore[reportAttributeAccessIssue]
                    system=system,
                    prompt=f"{instruction}\n\n{body}",
                    max_tokens=1500,
                )
            except Exception as exc:  # one node failing must not void the book
                print(f"    {label} failed on {node.get('id')}: {exc}", file=sys.stderr)
                return
        text = completion.text.strip()
        if text:
            node["body"] = text

    await asyncio.gather(*(rewrite(node) for node in nodes if isinstance(node, dict)))
    return out


def _book_grade(doc: dict[str, Any]) -> float | None:
    """Return the whole-book Flesch-Kincaid grade of *doc*.

    Args:
        doc: A story document.

    Returns:
        The grade, or ``None`` when the book declares no reading level or is
        too short to measure.
    """
    metadata = doc.get("metadata")
    level = metadata.get("reading_level") if isinstance(metadata, dict) else None
    if not isinstance(level, dict):
        return None
    nodes = doc.get("nodes")
    if not isinstance(nodes, list):
        return None
    measured = measure_book(
        (
            str(node.get("body", ""))
            for node in nodes
            if isinstance(node, dict) and str(node.get("body", "")).strip()
        ),
        target=float(level.get("target", 3.0)),
        tolerance=float(level.get("tolerance", 1.0)),
    )
    return None if measured is None else measured.grade


def _spread_order(count: int) -> list[int]:
    """Return indices ordered to spread evenly over ``range(count)``.

    A low-discrepancy (golden-ratio) sequence rather than ``range``: swapping
    nodes in index order would put every hardened passage at the front of the
    book, which is a different defect (a book that starts hard and softens)
    from the one being seeded.

    Args:
        count: How many indices.

    Returns:
        A permutation of ``range(count)``.
    """
    return sorted(range(count), key=lambda i: (i * 0.6180339887498949) % 1.0)


def blend_to_grade(
    original: dict[str, Any], hardened: dict[str, Any], *, grades: float
) -> tuple[dict[str, Any], str]:
    """Compose an arm that is *grades* harder, from a rewrite that overshot.

    The generation seed does not take direction on magnitude. Asked for three
    US grades harder it delivered between 8.2 and 11.1 across the six-book
    corpus, moving books whose bands target grades 1.0 to 4.5 up to grades 8.1
    to 13.3. That is not a book too old for its band; it is a different genre,
    and it breaks the fixture two ways. It makes `age_fit`'s detection trivial,
    so the arm stops measuring the criterion's sensitivity to a realistic miss.
    And it moves voice, engagement and dialogue genuinely, which this battery's
    false-positive rule counts against those criteria for noticing something
    that really did change.

    Rather than re-prompting for a magnitude the model cannot hit reliably, the
    arm is composed: hardened bodies are swapped in one at a time, spread across
    the book, until the whole-book grade reaches the target. That is
    deterministic, exact, free (the generation is already paid for), and it
    seeds a more realistic defect than a uniform rewrite does, since a book
    whose passages drift too hard in places is what the pipeline actually
    produces when it fails this way.

    Args:
        original: The passing book.
        hardened: The same book with every eligible body rewritten harder.
        grades: How many US grades above the original to aim for.

    Returns:
        The blended arm, and a one-line note of what was achieved, because a
        seed whose strength is not reported cannot be read back against the
        detection rate computed over it.
    """
    base = _book_grade(original)
    if base is None:
        return copy.deepcopy(hardened), "unmeasurable grade; full rewrite used"

    out = copy.deepcopy(original)
    out_nodes = out.get("nodes")
    hard_nodes = hardened.get("nodes")
    if not isinstance(out_nodes, list) or not isinstance(hard_nodes, list):
        return out, "no nodes to blend"

    swappable = [
        i
        for i, (a, b) in enumerate(zip(out_nodes, hard_nodes, strict=False))
        if isinstance(a, dict)
        and isinstance(b, dict)
        and a.get("body") != b.get("body")
    ]
    swapped = 0
    for index in _spread_order(len(swappable)):
        node_index = swappable[index]
        out_nodes[node_index]["body"] = hard_nodes[node_index]["body"]
        swapped += 1
        current = _book_grade(out)
        if current is not None and current - base >= grades:
            break

    achieved = _book_grade(out)
    delta = "unmeasurable" if achieved is None else f"{achieved - base:+.2f}"
    return out, (
        f"{swapped} of {len(swappable)} rewritable nodes swapped, "
        f"grade {base:.2f} -> {achieved if achieved is None else round(achieved, 2)} "
        f"({delta} against a {grades:+.1f} target)"
    )


def blend_to_density(
    original: dict[str, Any], flattened: dict[str, Any], *, keep: float
) -> tuple[dict[str, Any], str]:
    """Compose an `imagery_flat` arm that keeps a stated share of its detail.

    Same reasoning as `blend_to_grade`, and the same reason: a rewrite asked to
    remove sensory detail removes as much as it feels like, and an arm that
    strips a book to abstraction is a trivially detectable defect that also
    moves voice and engagement. Blending stops at a measured target.

    Args:
        original: The passing book.
        flattened: The same book with every eligible body rewritten flat.
        keep: Target share of the original's sensory density to retain.

    Returns:
        The blended arm, and a one-line note of what was achieved.
    """
    base = _sensory_density(original)
    if not base:
        return copy.deepcopy(flattened), "no sensory words to lose; full rewrite used"

    out = copy.deepcopy(original)
    out_nodes = out.get("nodes")
    flat_nodes = flattened.get("nodes")
    if not isinstance(out_nodes, list) or not isinstance(flat_nodes, list):
        return out, "no nodes to blend"

    swappable = [
        i
        for i, (a, b) in enumerate(zip(out_nodes, flat_nodes, strict=False))
        if isinstance(a, dict)
        and isinstance(b, dict)
        and a.get("body") != b.get("body")
    ]
    swapped = 0
    for index in _spread_order(len(swappable)):
        node_index = swappable[index]
        out_nodes[node_index]["body"] = flat_nodes[node_index]["body"]
        swapped += 1
        if _sensory_density(out) <= base * keep:
            break

    achieved = _sensory_density(out)
    return out, (
        f"{swapped} of {len(swappable)} rewritable nodes swapped, "
        f"sensory density {base:.1f} -> {achieved:.1f} per 1000 words "
        f"({achieved / base:.0%} retained against a {keep:.0%} target)"
    )


async def prepare_arms(
    corpus: Sequence[Path],
    arms_dir: Path,
    harden_dir: Path,
    settings: Settings | None,
) -> tuple[int, float | None]:
    """Write each book's control and its generation-seeded reading-level arm.

    The other arms are mechanical and `seed_defects.py` writes them, control
    included; the control is rewritten here only so this step is usable on its
    own. The reading-level arm is here because it needs a provider, and because
    it was otherwise absent: `harden_book` existed with no caller at all, so a
    run would have scored `age_fit` with no arm to score it on and reported the
    criterion untested without saying why.

    The full rewrite is kept under ``harden_dir`` and the arm is *blended* from
    it, for the reason given in `blend_to_grade`. Keeping the rewrite means a
    change of target costs nothing: the generation is the expensive half and it
    is done once.

    Args:
        corpus: The passing books to build arms from.
        arms_dir: Directory the mechanical seeds were written to.
        harden_dir: Directory holding, or to receive, the full rewrites.
        settings: Settings supplying the credential, or ``None`` to blend from
            rewrites already on disk without calling any provider.

    Returns:
        The number of arms written, and the dollars spent, which is ``None``
        when no call was made and may also be ``None`` when the models used are
        unpriced (`UW-C239`).
    """
    ledger = UsageLedger()
    provider = (
        MeteredProvider(build_openrouter_leg(settings, _HARDEN_MODEL), ledger=ledger)
        if settings is not None
        else None
    )
    written = 0
    for path in corpus:
        doc = json.loads(path.read_text(encoding="utf-8"))
        stem = path.stem.replace(".filled", "")

        (arms_dir / f"{stem}__control.json").write_text(
            json.dumps(doc, indent=2) + "\n", encoding="utf-8"
        )
        written += 1

        for defect, rewrite, blend in (
            (
                "reading_level_up",
                lambda d, p: harden_book(d, p, grades=_HARDEN_GRADES),
                lambda o, r: blend_to_grade(o, r, grades=_HARDEN_GRADES),
            ),
            (
                "imagery_flat",
                flatten_book,
                lambda o, r: blend_to_density(o, r, keep=_IMAGERY_KEEP),
            ),
        ):
            rewrite_path = harden_dir / f"{stem}__{defect}.json"
            if provider is not None:
                rewritten = await rewrite(doc, provider)
                rewrite_path.write_text(
                    json.dumps(rewritten, indent=2) + "\n", encoding="utf-8"
                )
            elif rewrite_path.exists():
                rewritten = json.loads(rewrite_path.read_text(encoding="utf-8"))
            else:
                print(f"  SKIP {stem}__{defect}: no rewrite on disk", file=sys.stderr)
                continue

            arm, note = blend(doc, rewritten)
            result = verify(defect, doc, arm)
            target = arms_dir / f"{stem}__{defect}.json"
            if not result.landed:
                print(
                    f"  SKIP {stem}__{defect}  {result.evidence}; {note}",
                    file=sys.stderr,
                )
                target.unlink(missing_ok=True)
                continue
            print(
                f"  ok   {stem}__{defect}  {result.evidence}; {note}", file=sys.stderr
            )
            target.write_text(json.dumps(arm, indent=2) + "\n", encoding="utf-8")
            written += 1

    return written, (_spend(ledger) if provider is not None else None)


async def run_panel(
    books: Sequence[tuple[str, dict[str, Any]]],
    settings: Settings,
    panel: Sequence[Judge] = _PANEL,
    journal: Path | None = None,
) -> tuple[list[Verdict], float]:
    """Score every book with every judge, blind, and meter the spend.

    Args:
        books: ``(identifier, document)`` pairs.
        settings: Settings supplying the credential.
        panel: The judges to run.
        journal: Where to append each verdict as it arrives, one JSON object
            per line. This exists because on 2026-08-15 two runs were killed
            mid-flight by an environment interruption after 92 and 34 paid
            scorings, and both produced nothing: results were held in memory
            and written once at the end, so an interrupted run lost every
            call it had paid for. Appending as we go makes a killed run
            partially usable instead of entirely wasted (`AL-407`).

    Returns:
        Every verdict, and the measured spend in USD.

    Note:
        The judge never learns which arm it is reading. The identifier is used
        only to join the results afterwards; the prompt carries the story text
        and nothing else, which is what makes a within-book comparison a
        comparison rather than a suggestion.
    """
    verdicts: list[Verdict] = []
    ledger = UsageLedger()
    for judge in panel:
        provider = MeteredProvider(
            build_openrouter_leg(
                settings, model=judge.model, provider_order=judge.provider_order
            ),
            ledger=ledger,
        )
        for identifier, doc in books:
            verdict = await judge_book(
                provider, judge, doc, leg=identifier, family="w7", brief_index=0
            )
            detail = verdict.error or (
                f"{statistics.fmean(verdict.scores.values()):.2f}"
                if verdict.scores
                else "no scores"
            )
            print(f"  {judge.label} -> {identifier}: {detail}", file=sys.stderr)
            verdicts.append(verdict)
            _journal(journal, verdict)
    return verdicts, _spend(ledger)


def _journal(path: Path | None, verdict: Verdict) -> None:
    """Append one verdict to the run journal, if a journal was requested.

    Flushed per line rather than buffered: the whole point is to survive a
    process that does not get to run its exit path, and a buffered write is
    exactly what such a process loses.

    Args:
        path: The journal file, or ``None`` to skip journalling.
        verdict: The verdict just produced.
    """
    if path is None:
        return
    row = {
        "book": verdict.book,
        "leg": verdict.leg,
        "family": verdict.family,
        "judge": verdict.judge,
        "self_family": verdict.self_family,
        "scores": verdict.scores,
        "notes": verdict.notes,
        "error": verdict.error,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _spend(ledger: UsageLedger) -> float:
    """Return measured spend for the run, priced per judge model.

    Args:
        ledger: The run's ledger.

    Returns:
        USD spent, as a lower bound when any model is unpriced.
    """
    from cyo_adventure.core.pricing import estimate_cost, price_for  # noqa: PLC0415

    total = 0.0
    for call in ledger.calls:
        estimate = estimate_cost(
            price_for(call.provider, call.model), call.input_tokens, call.output_tokens
        )
        total += float(estimate.amount_usd)
    return total


def _print_report(
    results: Sequence[CriterionVerdict], verdicts: Sequence[Verdict], spend: float
) -> None:
    """Print the per-criterion table, the agreement figures, and the spend.

    Args:
        results: Output of :func:`score_battery`.
        verdicts: Every verdict, for the agreement pass.
        spend: Measured USD.
    """
    print("\nW7 KNOWN-BAD BATTERY  (per criterion; within-book against control)")
    width = max(len(r.criterion) for r in results)
    print(
        f"  {'criterion':<{width}}  {'defect':<18} {'detect':>7} {'x-arm':>6} "
        f"{'noise':>6} {'median delta':>13}"
    )
    for row in results:
        rate = f"{row.detections}/{row.opportunities}" if row.opportunities else "-"
        delta = f"{statistics.median(row.deltas):+.2f}" if row.deltas else "-"
        noise = "-" if row.control_noise is None else f"{row.control_noise:.2f}"
        print(
            f"  {row.criterion:<{width}}  {row.defect or '-':<18} {rate:>7} "
            f"{row.cross_arm_moves:>6} {noise:>6} {delta:>13}"
        )
    print(
        "\n  x-arm counts movement on arms this criterion does not own. The arms "
        "are not\n  single-defect documents, so most of it is real collateral "
        "change; it decides nothing."
    )
    print("\n  Verdicts:")
    for row in results:
        print(f"    {row.criterion}: {row.verdict}")

    print(
        f"\n  Agreement, per criterion, quadratic-weighted kappa against a "
        f"{_KAPPA_FLOOR} floor (Landis and Koch 1977)."
    )
    books = sorted({v.book for v in verdicts})
    # Judges are read off the verdicts rather than the module constant, so a
    # replay of an open-weight run reports the judges that produced it.
    labels = sorted({v.judge for v in verdicts})
    for criterion in _CRITERIA:
        print(f"\n    {criterion}")
        for i, left in enumerate(labels):
            for right in labels[i + 1 :]:
                pairs = [
                    (
                        _score(verdicts, left, b, criterion),
                        _score(verdicts, right, b, criterion),
                    )
                    for b in books
                ]
                usable = [(x, y) for x, y in pairs if x is not None and y is not None]
                xs = [x for x, _ in usable]
                ys = [y for _, y in usable]
                kappa = weighted_kappa(xs, ys)
                text = "undefined" if kappa is None else f"{kappa:+.2f}"
                flag = (
                    ""
                    if kappa is None or kappa >= _KAPPA_FLOOR
                    else "  <-- below floor"
                )
                print(f"      {left} vs {right}: {text} (n={len(usable)}){flag}")
                # Marginals beside the figure, because a kappa depressed by
                # skew reads identically to one depressed by disagreement.
                print(f"        {left} {_marginals(xs)}")
                print(f"        {right} {_marginals(ys)}")

    # Zero here means the judge models carry no rate in `core/pricing.py`
    # (UW-C239), not that the panel was free. The harden step printed "$0.0000"
    # for 224 calls that cost $0.85 against the provider's own balance, so a
    # dollar figure from this ledger is not evidence of anything until that row
    # is closed.
    if spend:
        print(f"\n  Measured spend: ${spend:.4f}")
    else:
        print(
            "\n  Measured spend: UNPRICED. The judge models have no rate in "
            "core/pricing.py (UW-C239); read the provider balance instead."
        )


def _score(
    verdicts: Sequence[Verdict], judge: str, book: str, criterion: str
) -> float | None:
    """Return one judge's score for one book on one criterion.

    Args:
        verdicts: Every verdict.
        judge: The judge label.
        book: The book identifier, as recorded on the verdict.
        criterion: The criterion name.

    Returns:
        The score, or ``None`` when that judge did not score that book, or
        scored it without that criterion.
    """
    for v in verdicts:
        if v.judge == judge and v.book == book and v.scores and v.error is None:
            return v.scores.get(criterion)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Run or replay the battery.

    Args:
        argv: Argument vector, or ``None`` for ``sys.argv``.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--allow-untracked-out",
        action="store_true",
        help="Permit a gitignored --out. Scratch runs only; see AL-379.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--replay", type=Path)
    parser.add_argument(
        "--panel",
        type=Path,
        help=(
            "JSON array of judge objects to use instead of the frontier panel. "
            "This is how an open-weight candidate is evaluated as a "
            "distillation parent: same arms, same rubric, different judges."
        ),
    )
    parser.add_argument(
        "--exclude-judge",
        action="append",
        default=[],
        metavar="LABEL",
        help=(
            "Drop this judge before scoring. Repeatable. For asking which "
            "verdicts survive without a judge whose own run-to-run drift "
            "exceeds the detection margin."
        ),
    )
    parser.add_argument(
        "--harden-dir",
        type=Path,
        default=Path("out/w7/harden"),
        help=(
            "Where the full generation rewrites live. The arm is blended from "
            "them to a controlled grade delta, so re-targeting costs nothing."
        ),
    )
    parser.add_argument(
        "--reblend",
        action="store_true",
        help=(
            "Rebuild the reading_level_up arms from the rewrites already in "
            "--harden-dir, calling no provider."
        ),
    )
    parser.add_argument(
        "--prepare",
        nargs="+",
        type=Path,
        metavar="BOOK",
        help=(
            "Write each book's control and its generation-seeded "
            "reading_level_up arm into --arms, then exit without judging. "
            "Separate from the run so the paid harden is not repeated when a "
            "judging pass is retried."
        ),
    )
    args = parser.parse_args(argv)

    if args.replay is not None:
        payload = json.loads(args.replay.read_text(encoding="utf-8"))
        verdicts = [Verdict(**row) for row in payload["verdicts"]]
        arms = [tuple(pair) for pair in payload["arms"]]
        if args.exclude_judge:
            before = len({v.judge for v in verdicts})
            verdicts = [v for v in verdicts if v.judge not in set(args.exclude_judge)]
            after = len({v.judge for v in verdicts})
            print(
                f"Excluded {', '.join(args.exclude_judge)}: "
                f"{before} judges -> {after}.",
                file=sys.stderr,
            )
        _print_report(
            score_battery(verdicts, arms),  # pyright: ignore[reportArgumentType]
            verdicts,
            float(payload.get("spend_usd", 0.0)),
        )
        return 0

    if args.env_file.exists():
        for line in args.env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                os.environ["OPENROUTER_API_KEY"] = (
                    line.split("=", 1)[1].strip().strip("'\"")
                )

    if args.prepare is not None:
        if args.arms is None:
            print("Error: --prepare needs --arms.", file=sys.stderr)
            return 2
        args.arms.mkdir(parents=True, exist_ok=True)
        args.harden_dir.mkdir(parents=True, exist_ok=True)
        with single_run(args.harden_dir):
            written, spent = asyncio.run(
                prepare_arms(
                    args.prepare,
                    args.arms,
                    args.harden_dir,
                    None if args.reblend else Settings(),
                )
            )
        # Never print "$0.0000" for an unpriced run. `core/pricing.py` leaves
        # input rates unset for every cloud model (UW-C239), so a zero here
        # means the call was not priced, not that it was free, and printing it
        # as a dollar figure would put a false number in the run's record.
        if args.reblend:
            cost = "no provider call"
        elif not spent:
            cost = f"spend unpriced ({_HARDEN_MODEL} has no rate; UW-C239)"
        else:
            cost = f"${spent:.4f} spent hardening"
        print(f"\n{written} arm(s) written; {cost}.")
        return 0

    if args.arms is None or args.out is None:
        print("Error: --arms and --out are required without --replay.", file=sys.stderr)
        return 2

    # #CRITICAL: payment: --reblend means "rebuild the arms without calling a
    # provider", but it is only read inside the --prepare branch above. Passed
    # without --prepare it used to fall through to here, which is the paid
    # judging pass: a flag whose entire purpose is to avoid spending money
    # silently became a run that spends it. Observed 2026-08-15, killed after
    # 17 billed scorings (AL-412). Refuse instead, because there is no reading
    # of `--reblend` alone under which judging is what the operator asked for.
    # #VERIFY: test_reblend_without_prepare_refuses_rather_than_judging in
    # tests/unit/test_w7_battery.py.
    if args.reblend:
        print(
            "Error: --reblend rebuilds arms and only applies with --prepare. "
            "Refusing, because continuing would start a paid judging run.",
            file=sys.stderr,
        )
        return 2

    ensure_persistable(args.out, allow_untracked=args.allow_untracked_out)

    files = sorted(args.arms.glob("*.json"))
    books = [(p.stem, json.loads(p.read_text(encoding="utf-8"))) for p in files]
    arms = [tuple(p.stem.rsplit("__", 1)) for p in files]
    panel = load_panel(args.panel)
    print(
        f"Judging {len(books)} books with {len(panel)} judges "
        f"({len(books) * len(panel)} scorings): "
        f"{', '.join(j.label for j in panel)}.",
        file=sys.stderr,
    )

    with single_run(args.out):
        verdicts, spend = asyncio.run(
            run_panel(books, Settings(), panel, journal=args.out / "journal.jsonl")
        )
    results = score_battery(verdicts, arms)  # pyright: ignore[reportArgumentType]

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "verdicts.json").write_text(
        json.dumps(
            {
                "arms": [list(a) for a in arms],
                "spend_usd": spend,
                "verdicts": [
                    {
                        "book": v.book,
                        "leg": v.leg,
                        "family": v.family,
                        "judge": v.judge,
                        "self_family": v.self_family,
                        "scores": v.scores,
                        "notes": v.notes,
                        "error": v.error,
                    }
                    for v in verdicts
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _print_report(results, verdicts, spend)
    print(f"\nWrote {args.out / 'verdicts.json'}")
    print(persistence_notice(args.out, spend or None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
