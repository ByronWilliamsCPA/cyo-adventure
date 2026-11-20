"""Aggregate stored reading trails into the owner's per-book report.

Pure and database-free: ``scripts/report_reading_trail.py`` loads rows and
blobs and hands them here, so the arithmetic is unit-testable without a
database. The output is a per-(storybook, version) summary: reads started and
finished, endings reached, where unfinished reads stopped, and for every node
that offers two or more choices, how often each choice was picked and how often
a rewind brought a reader back to that node.

Children are not identified unless the caller asks for a per-profile
breakdown, and then only by the profile's display name.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cyo_adventure.reading_trail.steps import StepKind, StoryIndex

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

# Kinds after which the reader's position is the step's own node_id.
_POSITION_KINDS = frozenset(
    {
        StepKind.START.value,
        StepKind.RESUME.value,
        StepKind.BACK.value,
        StepKind.END.value,
        StepKind.JUMP.value,
    }
)
# Kinds that end a read without changing position.
_CLOSING_KINDS = frozenset({StepKind.LEAVE.value, StepKind.RESTART.value})


@dataclass(frozen=True, slots=True)
class TrailRecord:
    """One stored trail, as the report script loads it.

    Attributes:
        storybook_id: The story.
        version: The pinned version.
        profile_label: The profile's display name (used only by the
            per-profile breakdown).
        steps: The stored steps, ordered by ``seq``.
    """

    storybook_id: str
    version: int
    profile_label: str
    steps: Sequence[Mapping[str, object]]


@dataclass
class StopPoint:
    """Where unfinished reads stopped, for one node.

    Attributes:
        reads: Unfinished reads whose last position was this node.
        left: Of those, how many carried an explicit leave marker.
        restarted: Of those, how many were restarted rather than left.
        dwell_seconds: Seconds spent on the node before an explicit leave
            or restart (only reads with a marker contribute).
    """

    reads: int = 0
    left: int = 0
    restarted: int = 0
    dwell_seconds: list[int] = field(default_factory=list)


@dataclass
class BookReport:
    """The aggregate for one storybook version.

    Attributes:
        storybook_id: The story.
        version: The version.
        title: The story title from the blob, if any.
        reads_started: Trails opening with ``start``.
        reads_resumed: Trails opening with ``resume`` (a session picking up
            saved progress, not a new read).
        reads_finished: Trails with at least one ``end`` step.
        endings: Ending id to times reached (every ``end`` step counts).
        stops: Node id to where unfinished trails stopped.
        picks: Node id to choice id to times picked, for nodes declaring two
            or more choices (every declared choice is listed, zero included).
        rewinds_to: Node id to rewinds that landed there, same nodes.
        by_profile: Profile label to ``(started, finished)``, filled only when
            requested.
    """

    storybook_id: str
    version: int
    title: str | None
    reads_started: int = 0
    reads_resumed: int = 0
    reads_finished: int = 0
    endings: Counter[str] = field(default_factory=Counter[str])
    stops: dict[str, StopPoint] = field(default_factory=lambda: defaultdict(StopPoint))
    picks: dict[str, Counter[str]] = field(default_factory=dict)
    rewinds_to: Counter[str] = field(default_factory=Counter[str])
    by_profile: dict[str, list[int]] = field(default_factory=dict)


def _str(value: object) -> str | None:
    """Return ``value`` when it is a string, else ``None``."""
    return value if isinstance(value, str) else None


def _int(value: object) -> int:
    """Return ``value`` when it is an int, else 0."""
    return value if isinstance(value, int) else 0


def _final_position(
    index: StoryIndex, steps: Sequence[Mapping[str, object]]
) -> tuple[str | None, int]:
    """Return the reader's last position and the elapsed time they arrived.

    Args:
        index: The version's node index (for choice targets).
        steps: The trail's steps, ordered by ``seq``.

    Returns:
        tuple[str | None, int]: The node the reader was last on, and the
            ``elapsed_s`` of the step that brought them there.
    """
    position: str | None = None
    arrived_at = 0
    for step in steps:
        kind = _str(step.get("kind"))
        node_id = _str(step.get("node_id"))
        if kind in _POSITION_KINDS and node_id is not None:
            position, arrived_at = node_id, _int(step.get("elapsed_s"))
        elif kind in {StepKind.CHOICE.value, StepKind.AUTO.value}:
            facts = index.nodes.get(node_id or "")
            choice_id = _str(step.get("choice_id"))
            target = facts.targets.get(choice_id or "") if facts else None
            if target is not None:
                position, arrived_at = target, _int(step.get("elapsed_s"))
    return position, arrived_at


def _count_rewinds(report: BookReport, steps: Sequence[Mapping[str, object]]) -> None:
    """Count each run of consecutive ``back`` steps once, at its landing node.

    A "Try a different choice" rewind sends several BACK transitions in a row;
    the node where the run ends is the one the reader came back to choose
    again, so only the last ``back`` of a run counts.
    """
    for position, step in enumerate(steps):
        if step.get("kind") != StepKind.BACK.value:
            continue
        following = steps[position + 1] if position + 1 < len(steps) else None
        if following is not None and following.get("kind") == StepKind.BACK.value:
            continue
        node_id = _str(step.get("node_id"))
        if node_id is not None:
            report.rewinds_to[node_id] += 1


def _add_trail(report: BookReport, index: StoryIndex, record: TrailRecord) -> bool:
    """Fold one trail into its book report; return whether it finished."""
    steps = record.steps
    opening = _str(steps[0].get("kind")) if steps else None
    if opening == StepKind.START.value:
        report.reads_started += 1
    elif opening == StepKind.RESUME.value:
        report.reads_resumed += 1
    finished = False
    for step in steps:
        kind = _str(step.get("kind"))
        node_id = _str(step.get("node_id")) or ""
        if kind == StepKind.END.value:
            facts = index.nodes.get(node_id)
            if facts is not None and facts.ending_id is not None:
                report.endings[facts.ending_id] += 1
                finished = True
        elif kind == StepKind.CHOICE.value and node_id in report.picks:
            choice_id = _str(step.get("choice_id"))
            if choice_id is not None:
                report.picks[node_id][choice_id] += 1
    _count_rewinds(report, steps)
    if finished:
        report.reads_finished += 1
    elif steps:
        _add_stop(report, index, steps)
    return finished


def _add_stop(
    report: BookReport, index: StoryIndex, steps: Sequence[Mapping[str, object]]
) -> None:
    """Record where an unfinished trail stopped."""
    position, arrived_at = _final_position(index, steps)
    if position is None:
        return
    stop = report.stops[position]
    stop.reads += 1
    last = steps[-1]
    last_kind = _str(last.get("kind"))
    if last_kind in _CLOSING_KINDS:
        if last_kind == StepKind.LEAVE.value:
            stop.left += 1
        else:
            stop.restarted += 1
        stop.dwell_seconds.append(max(0, _int(last.get("elapsed_s")) - arrived_at))


def build_report(
    trails: Iterable[TrailRecord],
    blobs: Mapping[tuple[str, int], Mapping[str, object]],
    *,
    by_profile: bool = False,
) -> list[BookReport]:
    """Aggregate trails into one report per storybook version.

    Args:
        trails: Every trail to include.
        blobs: ``(storybook_id, version)`` to that version's stored blob.
            A trail whose version has no blob is skipped (its version was
            deleted, which would have cascaded the trail anyway).
        by_profile: Whether to fill the per-profile breakdown.

    Returns:
        list[BookReport]: Reports ordered by storybook id then version.
    """
    reports: dict[tuple[str, int], BookReport] = {}
    indexes: dict[tuple[str, int], StoryIndex] = {}
    for record in trails:
        key = (record.storybook_id, record.version)
        blob = blobs.get(key)
        if blob is None:
            continue
        if key not in reports:
            index = StoryIndex.from_blob(blob)
            indexes[key] = index
            reports[key] = BookReport(
                storybook_id=record.storybook_id,
                version=record.version,
                title=_str(blob.get("title")),
                picks={
                    node_id: Counter(dict.fromkeys(facts.choice_ids, 0))
                    for node_id, facts in index.nodes.items()
                    if len(facts.choice_ids) >= 2
                },
            )
        report = reports[key]
        finished = _add_trail(report, indexes[key], record)
        if by_profile:
            counts = report.by_profile.setdefault(record.profile_label, [0, 0])
            opening = _str(record.steps[0].get("kind")) if record.steps else None
            counts[0] += 1 if opening == StepKind.START.value else 0
            counts[1] += 1 if finished else 0
    return [reports[key] for key in sorted(reports)]


def _median_minutes(samples: Sequence[int]) -> str:
    """Render a median dwell in minutes, or a dash with no samples."""
    if not samples:
        return "-"
    return f"{statistics.median(samples) / 60:.1f} min"


def render_report(
    reports: Sequence[BookReport], blobs: Mapping[tuple[str, int], Mapping[str, object]]
) -> str:
    """Render reports as plain text for a terminal.

    Args:
        reports: The aggregated reports.
        blobs: The same blobs ``build_report`` used (for ending titles).

    Returns:
        str: The report text.
    """
    lines: list[str] = []
    if not reports:
        lines.append("No reading trails recorded.")
    for report in reports:
        index = StoryIndex.from_blob(blobs[(report.storybook_id, report.version)])
        lines.extend(_render_book(report, index))
    return "\n".join(lines) + "\n"


def _render_book(report: BookReport, index: StoryIndex) -> list[str]:
    """Render one book's section."""
    title = report.title or report.storybook_id
    started = f"Reads started: {report.reads_started}"
    resumed = f"resumed sessions: {report.reads_resumed}"
    finished = f"finished: {report.reads_finished}"
    counts = f"{started}   {resumed}   {finished}"
    lines = ["", f"== {title} ({report.storybook_id} v{report.version}) ==", counts]
    lines.extend(_render_endings(report, index))
    lines.extend(_render_stops(report))
    lines.extend(_render_choices(report, index))
    if report.by_profile:
        lines.append("By profile (started / finished):")
        for label in sorted(report.by_profile):
            started, finished = report.by_profile[label]
            lines.append(f"  {label}: {started} / {finished}")
    return lines


def _render_endings(report: BookReport, index: StoryIndex) -> list[str]:
    """Render the endings-reached block."""
    lines = ["Endings reached:"]
    if not report.endings:
        lines.append("  (none)")
    titles = {
        facts.ending_id: facts.ending_title
        for facts in index.nodes.values()
        if facts.ending_id is not None
    }
    for ending_id, count in report.endings.most_common():
        label = titles.get(ending_id) or ""
        lines.append(f"  {count:4d}  {ending_id}  {label}".rstrip())
    return lines


def _render_stops(report: BookReport) -> list[str]:
    """Render the stopped-without-an-ending block."""
    lines = ["Stopped without an ending (last node):"]
    if not report.stops:
        lines.append("  (none)")
    ranked = sorted(report.stops.items(), key=lambda item: (-item[1].reads, item[0]))
    for node_id, stop in ranked:
        dwell = _median_minutes(stop.dwell_seconds)
        detail = f"left {stop.left}, restarted {stop.restarted}"
        lines.append(
            f"  {stop.reads:4d}  {node_id}  ({detail}, median time on node {dwell})"
        )
    return lines


def _render_choices(report: BookReport, index: StoryIndex) -> list[str]:
    """Render the per-node choice picks and rewinds block."""
    lines = ["Choices (nodes with two or more choices):"]
    shown = False
    for node_id in sorted(report.picks):
        counter = report.picks[node_id]
        rewinds = report.rewinds_to.get(node_id, 0)
        if not any(counter.values()) and rewinds == 0:
            continue
        shown = True
        lines.append(f"  {node_id}  (rewinds back to here: {rewinds})")
        lines.extend(
            f"    {counter[choice_id]:4d}  {choice_id}"
            for choice_id in index.nodes[node_id].choice_ids
        )
    if not shown:
        lines.append("  (no choices taken yet)")
    return lines
