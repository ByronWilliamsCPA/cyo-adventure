#!/usr/bin/env python
"""ADR-030 engagement-correlation analysis job: read-only, no route, flag-off.

Joins the persisted Stage-4 engagement advisory against aggregated real reading
outcomes per storybook, so the project can learn over time which synthetic
quality scores actually predict that a band's readers finish a book and come
back to it. Its output feeds the flywheel's candidate strategy, which today
triggers on request-side saturation only.

    uv run python scripts/engagement_correlation.py              # run the job
    uv run python scripts/engagement_correlation.py --self-check # arm check only

**This is a scheduled analysis job, not an API surface.** It acquires no route,
now or later (ADR-030 Decision 8): a route is a data-egress path, reachable by
anything that can reach the service and subject to whatever authorisation bug
the service acquires next, and this data set is exactly the kind that should not
gain one.

**It ships inert.** ``ANALYSIS_ENGAGEMENT_CORRELATION_ENABLED`` defaults to
False, and off means the job reads no database, computes nothing, and writes
nothing. ADR-030 is ``proposed`` and not yet ratified; the flag staying off is
the mitigation the owner's assumed-approval ruling depends on.

**What it prints.** The mode, the output path, and how many artifact files were
retained. Never a row, never a rate, never an identifier, and never a count of
storybooks considered, included, or excluded. That restraint is deliberate and
is the same rule as ADR-030 Decision 6's: stdout on this project is read by
agents, and an agent summarising a run into a pull-request description is the
most likely real leak here, more likely than a stray ``git add``. A figure that
never reaches stdout cannot be quoted out of it.

**Where the artifact goes.** A directory named by configuration with no default,
outside any git working tree (the settings validator refuses to construct
otherwise), created ``0700`` with each file written ``0600``. The job keeps the
current and the immediately preceding run and deletes anything older, and
turning the kill switch off deletes them rather than orphaning them.

Exit codes:
    0 - the job ran (or was disabled), or every self-check passed.
    1 - a self-check failed.
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import asyncio
import stat
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cyo_adventure.analysis.engagement_correlation import (
    FLAG_REASONS,
    StorybookObservations,
    build_artifact,
    stage_four_verdict,
)
from cyo_adventure.analysis.queries import (
    completion_families_statement,
    flag_families_statement,
    moderation_reports_statement,
    rating_families_statement,
    reader_families_statement,
    storybooks_statement,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.database import get_session
from cyo_adventure.core.exceptions import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

# The artifact's filename shape. Run-scoped, so two retained runs never collide
# and a stale one is identifiable by name alone.
ARTIFACT_PREFIX = "engagement-correlation-"
ARTIFACT_SUFFIX = ".json"

# ADR-030 Decision 6's retention window: the current run and the one before it.
# Two is enough to diff a run against its predecessor, which is the only reason
# to keep more than one, and "however many accumulate" is how three windowless
# data classes already happened elsewhere in this system.
RETAINED_RUNS = 2

_DIR_MODE = stat.S_IRWXU  # 0o700
_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR  # 0o600

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKIPPED_TREE_DIRS = frozenset(
    {".git", ".venv", "node_modules", ".worktrees", ".mypy_cache", ".ruff_cache"}
)


def _build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser.

    Returns:
        argparse.ArgumentParser: The parser for this CLI.
    """
    parser = argparse.ArgumentParser(description="ADR-030 engagement correlation")
    _ = parser.add_argument(
        "--self-check",
        action="store_true",
        help=(
            "Verify the ADR-030 controls are armed and that no artifact has "
            "reached this repository. Touches no database."
        ),
    )
    return parser


# --- artifact I/O (ADR-030 Decision 6) ---


def artifact_paths(output_dir: Path) -> list[Path]:
    """Return this job's artifacts in the directory, oldest name first.

    Only files matching the job's own prefix and suffix, so a purge can never
    reach a file this job did not write.

    Args:
        output_dir: The configured output directory.

    Returns:
        list[Path]: The matching files, sorted by name (which sorts by run).
    """
    if not output_dir.is_dir():
        return []
    return sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file()
        and path.name.startswith(ARTIFACT_PREFIX)
        and path.name.endswith(ARTIFACT_SUFFIX)
    )


def prune_artifacts(output_dir: Path, *, keep: int) -> int:
    """Delete all but the newest ``keep`` artifacts and return the retained count.

    Args:
        output_dir: The configured output directory.
        keep: How many runs to retain; ``0`` deletes every one.

    Returns:
        int: How many artifacts remain.
    """
    existing = artifact_paths(output_dir)
    doomed = existing[: max(len(existing) - keep, 0)]
    for path in doomed:
        path.unlink(missing_ok=True)
    return len(existing) - len(doomed)


def write_artifact(output_dir: Path, document: dict[str, object]) -> Path:
    """Write one run's artifact and prune older ones.

    Args:
        output_dir: The configured output directory.
        document: The artifact document.

    Returns:
        Path: The written file.
    """
    import json  # noqa: PLC0415 -- local, so importing this module stays cheap

    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(_DIR_MODE)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{ARTIFACT_PREFIX}{stamp}{ARTIFACT_SUFFIX}"
    _ = path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    path.chmod(_FILE_MODE)
    _ = prune_artifacts(output_dir, keep=RETAINED_RUNS)
    return path


# --- the read (ADR-030 Decision 4) ---


async def load_observations(session: AsyncSession) -> list[StorybookObservations]:
    """Read every allowlisted column and reduce it to family-grain observations.

    Every child identifier is resolved to a ``family_id`` here and nothing
    finer leaves this function, so the gating and emit core downstream never
    holds a child profile id, a device id, or a passage identifier.

    #EDGE: external-resources: read-only. Nothing is added to the session and
    nothing is committed; ``get_session``'s context manager rolls back on exit,
    so a run cannot mutate state whatever it finds.
    #VERIFY: no session.add or session.commit appears in this module;
    tests/unit/test_engagement_correlation_queries.py::TestReadAllowlist pins
    the statements this function is allowed to issue.

    Args:
        session: An open async session.

    Returns:
        list[StorybookObservations]: One entry per candidate storybook.
    """
    books = (await session.execute(storybooks_statement())).all()
    reports = (await session.execute(moderation_reports_statement())).all()
    readers = (await session.execute(reader_families_statement())).all()
    completions = (await session.execute(completion_families_statement())).all()
    ratings = (await session.execute(rating_families_statement())).all()
    flags = (await session.execute(flag_families_statement())).all()

    verdicts: dict[tuple[str, int], object] = {
        (row[0], row[1]): row[2] for row in reports
    }
    reader_map: defaultdict[tuple[str, int], set[str]] = defaultdict(set)
    for storybook_id, version, family_id in readers:
        reader_map[storybook_id, version].add(str(family_id))
    completion_map: defaultdict[tuple[str, int], defaultdict[str, set[date]]] = (
        defaultdict(lambda: defaultdict(set))
    )
    for storybook_id, version, family_id, found_on in completions:
        completion_map[storybook_id, version][str(family_id)].add(found_on)
    rating_map: defaultdict[str, defaultdict[str, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for storybook_id, value, family_id in ratings:
        rating_map[storybook_id][str(family_id)].append(value)
    flag_map: defaultdict[str, defaultdict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for storybook_id, reason, family_id in flags:
        if reason in FLAG_REASONS:
            flag_map[storybook_id][reason].add(str(family_id))

    observations: list[StorybookObservations] = []
    for book_id, visibility, status, published_version, subject_profile_id in books:
        version = published_version if published_version is not None else -1
        by_family = completion_map.get((book_id, version), {})
        completed = frozenset(by_family)
        returned = frozenset(
            family for family, dates in by_family.items() if len(dates) > 1
        )
        observations.append(
            StorybookObservations(
                storybook_id=book_id,
                visibility=visibility,
                is_personalized=subject_profile_id is not None,
                status=status,
                current_published_version=published_version,
                engagement_verdict=stage_four_verdict(verdicts.get((book_id, version))),
                reader_families=frozenset(reader_map.get((book_id, version), set())),
                completed_families=completed,
                returned_families=returned,
                rating_by_family={
                    family: tuple(values)
                    for family, values in rating_map.get(book_id, {}).items()
                },
                flag_families_by_reason={
                    reason: frozenset(families)
                    for reason, families in flag_map.get(book_id, {}).items()
                },
            )
        )
    return observations


async def _collect() -> list[StorybookObservations]:
    """Open a read-only session and return the observations.

    Returns:
        list[StorybookObservations]: One entry per candidate storybook.
    """
    async with get_session() as session:
        return await load_observations(session)


def run_job() -> Path:
    """Run the job end to end and return the written artifact's path.

    Path work stays out of the coroutine deliberately: the async half is the
    database read and nothing else.

    Returns:
        Path: The artifact written by this run.
    """
    output_dir = Path(
        settings.analysis_engagement_correlation_output_dir.strip()
    ).expanduser()
    observations = asyncio.run(_collect())
    return write_artifact(output_dir, build_artifact(observations))


# --- the self-check (what the scheduled workflow runs) ---


def _committed_artifacts(root: Path) -> list[Path]:
    """Return any artifact-shaped file found inside the repository tree.

    ADR-030 Decision 6 decides that this artifact may never be committed here:
    the repository is public and a push is not retractable, so an aggregate over
    five families of real children stays reachable in history after any
    subsequent deletion.

    Args:
        root: The repository root to walk.

    Returns:
        list[Path]: Any offending files.
    """
    found: list[Path] = []
    for path in root.rglob(f"{ARTIFACT_PREFIX}*{ARTIFACT_SUFFIX}"):
        if any(part in _SKIPPED_TREE_DIRS for part in path.parts):
            continue
        found.append(path)
    return found


def _gitignore_mentions_artifact(root: Path) -> bool:
    """Return whether any .gitignore claims the artifact belongs in the tree.

    Decision 6 deliberately adds no ignore entry for this artifact, because an
    ignore entry is a statement that the artifact belongs in the tree and merely
    should not be staged. It does not belong in the tree.

    Args:
        root: The repository root to walk.

    Returns:
        bool: True when an ignore file names the artifact.
    """
    for path in root.rglob(".gitignore"):
        if any(part in _SKIPPED_TREE_DIRS for part in path.parts):
            continue
        if ARTIFACT_PREFIX.rstrip("-") in path.read_text(encoding="utf-8"):
            return True
    return False


def _refuses(*, output_dir: str) -> bool:
    """Return whether Settings refuses to construct with the job enabled here.

    Args:
        output_dir: The candidate output directory, as configured.

    Returns:
        bool: True when construction raised :class:`ConfigurationError`.
    """
    from cyo_adventure.core.config import Settings  # noqa: PLC0415 -- self-check only

    try:
        _ = Settings(
            analysis_engagement_correlation_enabled=True,
            analysis_engagement_correlation_output_dir=output_dir,
        )
    except ConfigurationError:
        return True
    return False


def self_check() -> list[str]:
    """Verify the ADR-030 controls are armed, and return the failures.

    Runs on a schedule against ``main`` (see
    ``.github/workflows/engagement-correlation.yml``). It touches no database
    and needs no secret: what it answers is whether the controls that stand
    between children's reading outcomes and this public repository are still
    in place, and whether an artifact has reached the tree.

    Returns:
        list[str]: One line per failed check; empty when everything is armed.
    """
    from cyo_adventure.core.config import Settings  # noqa: PLC0415 -- self-check only

    failures: list[str] = []
    field = Settings.model_fields["analysis_engagement_correlation_enabled"]
    default: object = field.default
    if default is not False:
        failures.append("the kill switch does not default to off")

    if not _refuses(output_dir=""):
        failures.append("an empty output path is not refused")

    if not _refuses(output_dir=str(_REPO_ROOT / "out")):
        failures.append("an output path inside this repository is not refused")

    with tempfile.TemporaryDirectory() as tmp:
        outside = Path(tmp) / "artifacts"
        if _refuses(output_dir=str(outside)):
            failures.append("a path outside any working tree is refused")
        worktree = Path(tmp) / "worktree"
        (worktree / "reports").mkdir(parents=True)
        _ = (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        if not _refuses(output_dir=str(worktree / "reports")):
            failures.append("a worktree marked by a .git FILE is not refused")

    committed = _committed_artifacts(_REPO_ROOT)
    if committed:
        failures.append(
            f"{len(committed)} engagement-correlation artifact file(s) are in "
            "the repository tree and must be removed"
        )
    if _gitignore_mentions_artifact(_REPO_ROOT):
        failures.append(
            "a .gitignore entry names this artifact; Decision 6 adds none, "
            "because an ignore entry says the artifact belongs in the tree"
        )
    return failures


def _emit(lines: Iterable[str]) -> None:
    """Write lines to stdout.

    Args:
        lines: The lines to write, without trailing newlines.
    """
    for line in lines:
        _ = sys.stdout.write(f"{line}\n")


def main(argv: list[str] | None = None) -> int:
    """Run the job or the self-check.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        int: ``0`` on success, ``1`` on a failed self-check, ``2`` on usage.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    if cast("bool", args.self_check):
        failures = self_check()
        if failures:
            _emit([f"engagement-correlation: NOT ARMED: {line}" for line in failures])
            return 1
        _emit(["engagement-correlation: every ADR-030 control is armed"])
        return 0

    configured = settings.analysis_engagement_correlation_output_dir.strip()
    if not settings.analysis_engagement_correlation_enabled:
        # Off is off: no read, no computation, no artifact. Any artifact a
        # previous enabled run left is deleted rather than orphaned, but only
        # from a directory that would still pass the boot-time validator, so a
        # disabled job never touches a path nothing has vetted.
        retained = 0
        if configured and not _refuses(output_dir=configured):
            retained = prune_artifacts(Path(configured).expanduser(), keep=0)
        _emit(
            [
                (
                    "engagement-correlation: disabled "
                    "(ANALYSIS_ENGAGEMENT_CORRELATION_ENABLED is off)"
                ),
                f"engagement-correlation: retained {retained} artifact(s)",
            ]
        )
        return 0

    path = run_job()
    _emit(
        [
            "engagement-correlation: enabled",
            f"engagement-correlation: artifact written to {path}",
            (
                "engagement-correlation: retained "
                f"{len(artifact_paths(path.parent))} artifact(s)"
            ),
        ]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
