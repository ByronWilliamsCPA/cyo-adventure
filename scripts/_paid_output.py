"""Keep a paid measurement run's output from quietly ceasing to exist.

`AL-368` traces four blocked or degraded workplan items to one cause: the
`out/vendor-comparison/` results were produced by a run that cost real money and
then were not committed. W2's published reading-level figure became
unreproducible, the `AL-330` dialogue recheck became impossible once the
detector was found blind, and W4 and W5 were built against a pool that no longer
existed. Each occurrence was written up as a limitation of the blocked item
rather than as one recurring cause.

The register row proposed inverting a default, and looking at it that framing
was wrong: `out/vendor-comparison/` was never gitignored. Nothing pointed the
output anywhere hostile. It was simply never committed, and nothing in the run
ever mentioned that this was now the operator's problem. So the guard is in two
parts, matching the two ways the output can be lost:

* **Before the spend**, refuse a destination git is configured to ignore. That
  case is not a risk, it is a guarantee of loss, and it is worth failing early
  and loudly rather than after the invoice.
* **After the spend**, say plainly what the run cost, that the result is
  unreproducible until committed, and print the command that commits it. A
  reminder no one reads is still better than the silence that lost the last one,
  and this one carries the number that makes it land.

Neither part can force the commit, and neither pretends to. The measure that
matters is not what a run cost to produce but what it would cost to reproduce.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["ensure_persistable", "persistence_notice"]

_GIT: Final[str] = "git"


def _is_ignored(path: Path) -> bool:
    """Return whether git is configured to ignore *path*.

    Args:
        path: The destination directory or file.

    Returns:
        bool: ``True`` when ``git check-ignore`` claims it. A git failure (no
        repository, git absent) returns ``False``: this guard exists to catch a
        known-bad configuration, and it must never be the reason a run cannot
        start.
    """
    try:
        # Fixed argv, shell=False, no user-controlled executable: this is git
        # plumbing rather than a command line.
        result = subprocess.run(
            [_GIT, "check-ignore", "-q", str(path)],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def ensure_persistable(path: Path, *, allow_untracked: bool = False) -> None:
    """Raise before any spend if *path* is somewhere the result cannot survive.

    Args:
        path: The run's output destination.
        allow_untracked: Set by an explicit operator flag for a genuinely
            throwaway run. The escape hatch exists because scratch runs are
            real; the default does not assume every run is one.

    Raises:
        SystemExit: When the destination is gitignored and the operator has not
            said that is intended.
    """
    if allow_untracked or not _is_ignored(path):
        return
    message = (
        f"refusing to start: '{path}' is gitignored, so this run's output "
        "cannot be committed and the result will not survive the working tree. "
        "AL-368 records four workplan items blocked by exactly this. Choose a "
        "tracked path, or pass --allow-untracked-out if the run is scratch."
    )
    raise SystemExit(message)


def persistence_notice(path: Path, spend_usd: float | None = None) -> str:
    """Return the end-of-run message telling the operator to commit the output.

    Args:
        path: Where the run wrote its results.
        spend_usd: What the run cost, when known. Included because the abstract
            request to commit an artifact is easy to skip and a dollar figure
            attached to losing it is not.

    Returns:
        str: The notice, ready to print.
    """
    cost = f" This run cost ${spend_usd:.2f}." if spend_usd is not None else ""
    return (
        f"\nOutput written to {path}.{cost} It is NOT yet in git, so it exists "
        "only in this working tree and reproducing it means paying again:\n"
        f"    git add {path} && git commit -S -m 'chore(measurement): <what ran>'\n"
        "See AL-368 for the four items lost to skipping this."
    )
