"""Cross-vendor fill comparison: does model choice diversify prose, or not?

The anti-template work so far has measured a single vendor against itself. The
open question it cannot answer is whether the residual shared-idiom floor (the
~3.3 shared four-grams per 1000 leaf words the sibling-fill guard calibrates
against) is a property of *the task* (a skeleton, a band, a prompt) or a
property of *the vendor* (one model's house style). Those two possibilities
imply opposite diversification strategies:

- Task-driven floor: rotating vendors buys nothing. Spend the effort on prompt
  and skeleton variety.
- Vendor-driven floor: rotating vendors is a cheap, large lever, and model
  selection belongs in the diversification strategy alongside skeleton choice.

Neither number exists today. This harness produces both from one run.

**Method.** Every vendor fills the SAME (skeleton, brief) grid, one book per
cell, where skeleton *i* is paired with brief *i*. Structure is therefore held
constant across the vendor axis, which is what isolates prose idiom as the
variable, and varied across the brief axis, which is what makes the
within-vendor cell reproduce the condition the 3.3 floor was measured under:
"book pairs sharing nothing but the model and the age band". Pass one
``--skeleton`` and it is reused for every brief; that still measures the vendor
contrast correctly, but its within-vendor number is then a shared-structure
figure and is not the 3.3 quantity, so the harness says so in its output.

Generating from concept briefs instead would let each book invent its own
structure and confound the vendor axis, so this harness offers no brief-only
mode.

**Reading the output.** Pairs are bucketed on three axes, not one::

                                same brief          different brief
    same leg                    (not produced)      WITHIN-VENDOR FLOOR
    same lab, other checkpoint  both confounds      version-bump control
    different lab               premise convergence CROSS-VENDOR FLOOR

The headline comparison is the right-hand column's first and last rows:
within-vendor versus cross-vendor, both over different-brief pairs only.

Two confounds are held out of it deliberately. Comparing a cross-vendor
same-brief pair against a within-vendor different-brief pair would attribute
shared premise wording to vendor agreement. And a run carrying two checkpoints
of one lab (Sonnet 4.6 alongside Sonnet 5) would, on a vendor-label split
alone, count that pair as cross-vendor and drag the headline toward
"task-driven" for a reason that is not about vendor choice at all. A vendor
entry's optional ``family`` marks the shared lineage; that pair becomes its own
control, which answers a real question: does a house style survive a model
generation, or is it per-checkpoint?

**Provider pinning.** One OpenRouter slug can be served by several backends at
different quantizations, so an unpinned run is not reproducible and is not
attributable to a vendor. Each vendor entry therefore carries a
``provider_order``; the adapter sends ``allow_fallbacks: false`` alongside it,
turning a silent substitution into a visible error.

**Cost is measured, per book, across every call that book consumed.** Each book
gets its own :class:`~cyo_adventure.generation.usage.UsageLedger` wrapped around
its provider, so fill and repair calls are both billed to the book that caused
them; a leg needing three repairs to deliver is more expensive than one landing
first time, and that is exactly the difference this comparison exists to find.
A run refuses to start when a leg has no complete price, because a comparison
that exists to price vendors and cannot price them has already failed: run-6
spent twenty generations and recorded ``cost: null`` twenty times (AL-348).
Pass ``--allow-unpriced`` to accept the gap deliberately.

**The completion cap is a condition, not a setting.** At 32,000 one leg spends
6,054 completion tokens on a book and another spends all 32,000, 28,247 of them
on hidden reasoning. A leg with no headroom was measured against the wall rather
than against itself, so its fill rate is suppressed rather than printed, and the
cap is stamped on every book row (AL-328).

Dry run (no network, proves the plumbing and the analysis path)::

    uv run python scripts/compare_vendors.py \\
        --skeleton skeletons/<a>.json --skeleton skeletons/<b>.json \\
        --briefs <briefs.json> --mock \\
        --out out/vendor-comparison/dry-run

Live run (spends money; one paid fill per vendor leg per brief)::

    uv run python scripts/compare_vendors.py \\
        --skeleton skeletons/5-8/<a>.json --skeleton skeletons/5-8/<b>.json \\
        --skeleton skeletons/5-8/<c>.json --skeleton skeletons/5-8/<d>.json \\
        --briefs docs/planning/vendor-comparison/briefs-5-8.json \\
        --vendors docs/planning/vendor-comparison/vendors.json \\
        --throttle 3 --out out/vendor-comparison/run-1

``--skeleton`` is repeatable and pairs index-wise with ``--briefs``; pass either
one skeleton or exactly as many as there are briefs. Every skeleton must belong
to the same age band, since a cross-band pair would measure band difference
rather than vendor difference.

``--vendors`` is a JSON array of ``{"label", "model", "provider_order"}``
objects, each optionally carrying ``"family"`` to mark two legs as one lab's
lineage. ``OPENROUTER_API_KEY`` is read from the environment, sourced from the
gitignored ``.env`` by default (``--env-file``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import unicodedata
from dataclasses import dataclass, replace
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from cyo_adventure.core.config import Settings
from cyo_adventure.core.pricing import estimate_cost, price_for
from cyo_adventure.diversity.query import DifferentiationLevel
from cyo_adventure.generation.metered import MeteredProvider
from cyo_adventure.generation.orchestrator import _MAX_TOKENS_PROSE, fill_skeleton
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.prompts import build_differentiation_directive
from cyo_adventure.generation.provider import build_openrouter_leg, build_provider
from cyo_adventure.generation.skeleton import (
    resolve_output_cap,
    story_fill_rate,
)
from cyo_adventure.generation.usage import UsageLedger
from cyo_adventure.generation.variation import axis_for_key
from cyo_adventure.validator.reading_level import measure_book

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.generation.usage import Completion

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

# Pre-flight completion budget. Sized to clear reasoning overhead, not to fit an
# answer: a reasoning leg emits nothing until its hidden tokens are spent, so a
# budget below that overhead returns empty content and is indistinguishable from
# a dead pin. See preflight's docstring for the 2026-08-12 measurements.
_PREFLIGHT_MAX_TOKENS: Final[int] = 512

# The orchestrator's own prose cap, mirrored so a run that does not override it
# still records the cap it ran under. Imported rather than restated: a local copy
# would drift and the recorded condition would then be fiction.
_PROSE_CAP: Final[int] = _MAX_TOKENS_PROSE

# Share of the completion budget above which a leg is treated as having had no
# headroom. At the production cap of 32,000, one leg spent 6,054 tokens on a book
# and another spent all 32,000 (AL-328); the legs scored unreliable were exactly
# the two without headroom, so their fill rate measured the cap rather than the
# model. 0.95 rather than 1.0 because a model that stops just short of the wall
# was still shaped by it.
_NEAR_CAP_SHARE: Final[float] = 0.95

__all__ = [
    "BookRecord",
    "ComparisonReport",
    "Vendor",
    "analyze",
    "preflight",
    "run_comparison",
]


def _ensure_repo_on_path() -> None:
    """Make the repository root importable so the sibling check scripts resolve."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))


@dataclass(frozen=True, slots=True)
class Vendor:
    """One vendor leg in the comparison.

    Attributes:
        label: Short name used in the report and in output filenames.
        model: The OpenRouter model slug this leg calls.
        provider_order: OpenRouter backend pin, most preferred first. Empty is
            accepted (and warned about) so a mock dry run needs no pin, but a
            live run without one is not a reproducible measurement.
        family: The training lineage this leg belongs to, defaulting to
            ``label``. Two checkpoints from one lab (Sonnet 4.6 and Sonnet 5)
            are different legs but the same family, and counting that pair as
            cross-vendor would drag the headline toward "task-driven" for a
            reason that has nothing to do with vendor choice. Same-family pairs
            are bucketed separately as the version-bump control.
    """

    label: str
    model: str
    provider_order: tuple[str, ...]
    family: str = ""

    def lineage(self) -> str:
        """Return the family this leg belongs to, falling back to its label.

        Returns:
            ``family`` when set, otherwise ``label``, so a single-checkpoint
            vendor needs no extra configuration.
        """
        return self.family or self.label


@dataclass(frozen=True, slots=True)
class BookRecord:
    """One filled book plus everything measured about it.

    Attributes:
        vendor: The vendor label that produced it.
        family: The producing leg's training lineage, so two checkpoints from
            one lab can be told apart from two genuinely different vendors.
        brief_index: 0-based index into the brief list, so pairs can be split
            by same-brief versus different-brief.
        status: ``fill_skeleton``'s outcome status, or ``"error"``.
        attempts: Repair attempts the fill consumed.
        latency_s: Wall-clock seconds for the whole fill, the only run-cost
            proxy available until #701 lands.
        grade: Whole-book Flesch-Kincaid grade, or ``None`` when the book had
            too little scorable prose or declared no reading-level band.
        in_band: Fraction of scorable nodes inside the declared band. Never
            read this without ``fill_rate`` beside it: the 2026-08-21 grid
            measured a thin book conforming BECAUSE it was thin and a full
            book out of band, so either number alone misleads
            (`AL-491`/`AL-511`/`UW-C308`).
        fill_rate: The production ``story_fill_rate`` (per-node delivery capped
            at each node's commissioned ``words=`` target, so one node's
            surplus cannot mask another's shortfall), or ``None`` when the
            book failed entirely. This is the same definition the pipeline
            stamps on ``outcome.report["fill_rate"]``, so the harness column
            and the gate can never disagree; an earlier draft recorded raw
            delivered-over-commissioned words here, which could report an
            underfilled book as 100 percent. Over-delivery is still visible
            through ``leaf_words`` against the skeleton's commission.
        leaf_words: Total scorable leaf words.
        doc: The filled Storybook dict, or ``None`` on a total failure.
        error: Truncated exception text when ``status == "error"``.
        fill_completeness: Fraction of node bodies that are prose rather than a
            retained ``<<FILL ...>>`` directive. ``1.0`` is a written book.
        output_tokens: Completion tokens the leg spent on this book, summed
            across fill and repair calls, or ``None`` when unmetered.
        reasoning_tokens: Hidden reasoning tokens inside ``output_tokens``, or
            ``None`` when the backend reported none.
        cost_usd: Measured spend for this book, or ``None`` when unpriced.
        cost_complete: Whether every half of the price and the counts was known.
            A ``False`` here makes ``cost_usd`` a lower bound.
        cost_unavailable_reason: Why cost is absent or partial. Empty when
            complete.
        max_tokens: The completion cap this book was written under. Recorded
            because it is a condition of the measurement, not a setting: results
            at different caps are not poolable (`AL-328`).
        reading_level_degraded: Whether Stage D did less than it was asked to,
            by discarding a pass or dropping nodes from one.
        reading_level_nodes_dropped: How many accepted revisions Stage D threw
            away. Non-zero on a book that otherwise reads as fully repaired.
    """

    vendor: str
    family: str
    brief_index: int
    status: str
    attempts: int
    latency_s: float
    grade: float | None
    in_band: float | None
    fill_rate: float | None
    leaf_words: int
    doc: dict[str, Any] | None
    error: str | None
    fill_completeness: float = 0.0
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: float | None = None
    cost_complete: bool = False
    cost_unavailable_reason: str = ""
    max_tokens: int | None = None
    reading_level_degraded: bool = False
    reading_level_nodes_dropped: int = 0

    @property
    def complete(self) -> bool:
        """Whether this book is finished prose rather than a schema-valid shell.

        Returns:
            ``True`` only when a document was produced and no node body still
            holds a ``<<FILL ...>>`` directive. Four unfilled books out of
            thirty-two inverted a published diversity verdict (`AL-335`), so
            this is the participation test for every pair bucket rather than
            ``doc is not None``.
        """
        return self.doc is not None and self.fill_completeness >= 1.0

    @property
    def near_cap(self) -> bool:
        """Whether this book was written with no meaningful budget headroom.

        A fixed ``max_tokens`` is not a neutral condition across vendors: at the
        production cap of 32,000 one leg spends 6,054 completion tokens on a
        book and another spends all 32,000, 28,247 of them on hidden reasoning
        (`AL-328`). The legs scored unreliable were exactly the two without
        headroom, so a fill rate for those measures the cap rather than the
        model.

        Returns:
            ``True`` when the call spent at least ``_NEAR_CAP_SHARE`` of its
            budget. ``False`` when either figure is unknown, since an unmeasured
            call is not evidence of headroom either way; ``output_tokens`` being
            ``None`` is visible separately in the row.
        """
        if self.output_tokens is None or self.max_tokens is None:
            return False
        return self.output_tokens >= self.max_tokens * _NEAR_CAP_SHARE


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    """The aggregate answer plus every input needed to audit it.

    Attributes:
        books: Every book record, in generation order.
        within_vendor: ``label -> {"pairs", "mean_per_1000", "max_per_1000"}``
            over that vendor's different-brief pairs.
        cross_vendor: The same shape, over different-brief pairs whose two
            books came from different vendor *families*. This is the headline
            denominator, so a same-lab version pair is deliberately excluded.
        same_brief_cross_vendor: The same shape, over same-brief pairs from
            different families. Reported separately because shared premise
            wording is not vendor agreement.
        same_family_cross_model: The same shape, over different-brief pairs
            from two checkpoints of one lab. The version-bump control: it says
            whether a house style survives a model generation, and it belongs
            in neither the within-vendor nor the cross-vendor cell.
        same_family_same_brief: The same shape, over same-brief pairs from two
            checkpoints of one lab. Carries both the premise confound and the
            shared lineage, so it is recorded rather than dropped and is never
            part of any headline.
        verdict: A one-line reading of within versus cross.
        excluded_incomplete: Books that produced a document but were not fully
            written, named rather than silently dropped so a reader can see how
            much of a paid run did not reach the analysis.
    """

    books: list[BookRecord]
    within_vendor: dict[str, dict[str, float]]
    cross_vendor: dict[str, float]
    same_brief_cross_vendor: dict[str, float]
    same_family_cross_model: dict[str, float]
    same_family_same_brief: dict[str, float]
    verdict: str
    excluded_incomplete: tuple[str, ...] = ()


def _load_json(path: Path) -> object:
    """Read and parse a JSON file, exiting with a message on any failure.

    Args:
        path: The file to read.

    Returns:
        The parsed JSON value.

    Raises:
        SystemExit: On a read error or a parse error.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"Error reading {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"Error parsing {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def _load_vendors(path: Path) -> list[Vendor]:
    """Load the vendor spec array.

    Args:
        path: A JSON array of ``{"label", "model", "provider_order"}`` objects,
            each optionally carrying ``"family"`` to mark two legs as two
            checkpoints of one lab.

    Returns:
        The parsed vendors, in file order.

    Raises:
        SystemExit: If the file is not an array of well-formed vendor objects,
            or if two vendors share a label.
    """
    parsed = _load_json(path)
    if not isinstance(parsed, list):
        print(f"Error: {path} must contain a JSON array.", file=sys.stderr)
        sys.exit(1)
    vendors: list[Vendor] = []
    seen_labels: set[str] = set()
    for i, raw in enumerate(parsed):  # pyright: ignore[reportUnknownVariableType]
        entry: object = raw  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(entry, dict):
            print(f"Error: vendor #{i} is not an object.", file=sys.stderr)
            sys.exit(1)
        label = entry.get("label")
        model = entry.get("model")
        order_raw = entry.get("provider_order", [])
        if not isinstance(label, str) or not isinstance(model, str):
            print(f"Error: vendor #{i} needs string label and model.", file=sys.stderr)
            sys.exit(1)
        # #ASSUME: data-integrity: an empty or whitespace-only label passes the
        # bare-name check below (`Path("").name == ""`), and `_book_filename`
        # then writes `__00.json`, losing the vendor identity the filename
        # exists to carry. Not an overwrite risk (the fold below catches a
        # second empty label), so this is a legibility floor, not a money one.
        # #VERIFY: test_load_vendors_rejects_an_empty_label.
        if not label.strip():
            print(
                f"Error: vendor #{i} label is empty or whitespace-only; the "
                "book filename would carry no vendor identity.",
                file=sys.stderr,
            )
            sys.exit(1)
        # #CRITICAL: data integrity: _book_filename() names each book's output
        # file `{vendor}__{brief_index:02d}.json`, using the label as the sole
        # identity component. Two vendors sharing a label would silently
        # overwrite each other's paid artifacts, book for book, as the run
        # persists them (persist_book writes as it goes, per its own critical
        # data-integrity note on why that matters). Rejecting the duplicate
        # at load time is the only point cheap enough to catch it before any
        # provider call is billed.
        # #VERIFY: test_load_vendors_rejects_a_duplicate_label in
        # tests/unit/test_compare_vendors.py.
        # #CRITICAL: data-integrity: the label becomes the book filename in
        # `_book_filename`, so two labels that differ only in case resolve to
        # ONE file on a case-insensitive filesystem (the macOS and Windows
        # default) and the second vendor silently overwrites the first vendor's
        # already-paid-for books. A separator or traversal segment escapes the
        # output directory entirely. Neither is caught by the exact-match
        # uniqueness check this replaces.
        # #VERIFY: test_load_vendors_rejects_case_equivalent_labels and
        # test_load_vendors_rejects_a_label_that_is_not_a_bare_filename.
        # #CRITICAL: data-integrity: this guard's whole purpose, per the note
        # above, is to reject at LOAD time, before any provider call is billed.
        # A character that is legal on the authoring platform but invalid on the
        # running one defers the failure past the spend: `persist_book` then
        # raises while writing a book already paid for, which is the `AL-326`
        # loss (three books, 1,869 seconds of billed provider time) reached by a
        # different cause. A NUL byte fails the write on EVERY platform
        # (`ValueError: embedded null byte`), and Win32 rejects
        # `< > : " | ? * \ /` plus every character below 0x20 in a path
        # component, so a label authored on Linux can be unrunnable on Windows.
        # The committed specs use only `[a-z0-9.-]`, so nothing real is refused.
        # #VERIFY: test_load_vendors_rejects_a_label_with_an_unsafe_character.
        unsafe = {c for c in label if ord(c) < 0x20 or ord(c) == 0x7F} | (
            set(label) & set('<>:"|?*\\/')
        )
        if unsafe:
            shown = ", ".join(sorted(repr(c) for c in unsafe))
            print(
                f"Error: vendor #{i} label {label!r} contains character(s) "
                f"{shown} that cannot appear in a filename on every supported "
                "platform; the book write would fail after the run is billed.",
                file=sys.stderr,
            )
            sys.exit(1)
        if label != Path(label).name or label in {".", ".."}:
            print(
                f"Error: vendor #{i} label '{label}' is not a bare name; it "
                "would write outside the books directory.",
                file=sys.stderr,
            )
            sys.exit(1)
        # #CRITICAL: data-integrity: case folding alone does NOT unify Unicode
        # normalization forms, so "Cafe\u0301" (NFD) and "Caf\u00e9" (NFC) both
        # pass a casefold-only check and then resolve to ONE file on macOS,
        # whose filesystem is normalization-insensitive as well as
        # case-insensitive. That is the same paid-artifact overwrite the fold
        # was added to stop, reached through the other equivalence.
        # #VERIFY: test_load_vendors_rejects_unicode_equivalent_labels.
        folded = unicodedata.normalize("NFC", label.casefold())
        if folded in seen_labels:
            print(
                f"Error: vendor #{i} reuses label '{label}' (compared without "
                "case, because a case-insensitive filesystem would collapse "
                "the two book files into one and lose a paid run).",
                file=sys.stderr,
            )
            sys.exit(1)
        seen_labels.add(folded)
        if not isinstance(order_raw, list):
            print(f"Error: vendor #{i} provider_order must be a list.", file=sys.stderr)
            sys.exit(1)
        order = tuple(str(item) for item in order_raw)  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
        if not order:
            print(
                f"Warning: vendor '{label}' has no provider_order; its numbers "
                "are not attributable to one backend.",
                file=sys.stderr,
            )
        family_raw: object = entry.get("family", "")
        if not isinstance(family_raw, str):
            print(f"Error: vendor #{i} family must be a string.", file=sys.stderr)
            sys.exit(1)
        vendors.append(
            Vendor(label=label, model=model, provider_order=order, family=family_raw)
        )
    if not vendors:
        print(f"Error: {path} declared no vendors.", file=sys.stderr)
        sys.exit(1)
    return vendors


def _load_briefs(path: Path) -> list[dict[str, object]]:
    """Load the theme-brief array handed to ``fill_skeleton``.

    Unlike ``scripts/yield_harness.py`` these are theme briefs (free-form reskin
    dicts), not ``ConceptBrief`` models, because the fill path takes a plain
    mapping.

    Args:
        path: A JSON array of theme-brief objects.

    Returns:
        The parsed briefs, in file order.

    Raises:
        SystemExit: If the file is not an array of objects, or is empty.
    """
    parsed = _load_json(path)
    if not isinstance(parsed, list):
        print(f"Error: {path} must contain a JSON array.", file=sys.stderr)
        sys.exit(1)
    briefs: list[dict[str, object]] = []
    for i, raw in enumerate(parsed):  # pyright: ignore[reportUnknownVariableType]
        entry: object = raw  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(entry, dict):
            print(f"Error: brief #{i} is not an object.", file=sys.stderr)
            sys.exit(1)
        briefs.append(dict(entry))  # pyright: ignore[reportUnknownArgumentType]
    if len(briefs) < 2:
        print(
            "Error: at least 2 briefs are required; the within-vendor floor is "
            "measured over different-brief pairs and needs two books per vendor.",
            file=sys.stderr,
        )
        sys.exit(1)
    return briefs


def _load_differentiation(path: Path, brief_count: int) -> list[str]:
    """Load and render the per-brief differentiation directives (AL-498).

    ``fill_skeleton`` has accepted ``differentiation_directive`` since A6/A7,
    but this harness never passed it, so every recorded shared-idiom floor is
    the RAW undirected floor. This loader exists so a run can measure what the
    directive actually buys: the file is a JSON array, index-aligned with the
    briefs (the same convention ``--skeleton`` uses), and each entry is either
    ``null`` (that brief fills undirected, exactly as before) or an object with
    optional keys ``level``, ``axis``, ``prior_titles`` and ``prior_theme_tags``
    mirroring the pipeline-written ``authoring_metadata`` keys the worker reads.

    Entries are rendered through the production
    :func:`~cyo_adventure.generation.prompts.build_differentiation_directive`
    rather than accepted as free text, so a measured delta is attributable to
    the block production would send, not to operator prose. Unknown levels and
    axis keys are hard errors here, unlike the worker's tolerant miss: in the
    harness a bad key is an operator typo that would silently measure the
    no-context block and report it as the directed floor.

    Args:
        path: A JSON array of per-brief directive specs (objects or nulls).
        brief_count: How many briefs the run has; the array must match it.

    Returns:
        One rendered directive string per brief; ``""`` for a ``null`` entry.

    Raises:
        SystemExit: On a count mismatch, an unknown level or axis key, or a
            malformed entry.
    """
    parsed = _load_json(path)
    if not isinstance(parsed, list):
        print(f"Error: {path} must contain a JSON array.", file=sys.stderr)
        sys.exit(1)
    if len(parsed) != brief_count:  # pyright: ignore[reportUnknownArgumentType]
        # pyright: ignore on its own line: appended to the f-string above it
        # the comment pushes the source line to 127 characters, and neither
        # `ruff format` (it cannot split a trailing comment) nor E501 (ignored
        # as formatter-handled) will catch that.
        entry_count = len(parsed)  # pyright: ignore[reportUnknownArgumentType]
        print(
            f"Error: {path} has {entry_count} entries for {brief_count} "
            "briefs; they pair index-wise.",
            file=sys.stderr,
        )
        sys.exit(1)
    known_levels = {level.value for level in DifferentiationLevel}
    directives: list[str] = []
    for i, raw in enumerate(parsed):  # pyright: ignore[reportUnknownVariableType]
        entry: object = raw  # pyright: ignore[reportUnknownVariableType]
        if entry is None:
            directives.append("")
            continue
        if not isinstance(entry, dict):
            print(
                f"Error: differentiation #{i} must be an object or null.",
                file=sys.stderr,
            )
            sys.exit(1)
        spec = cast("dict[str, object]", entry)
        unknown = sorted(
            set(spec) - {"level", "axis", "prior_titles", "prior_theme_tags"}
        )
        if unknown:
            print(
                f"Error: differentiation #{i} has unknown keys: {', '.join(unknown)}.",
                file=sys.stderr,
            )
            sys.exit(1)
        level_raw = spec.get("level")
        if level_raw is not None and (
            not isinstance(level_raw, str) or level_raw not in known_levels
        ):
            print(
                f"Error: differentiation #{i} level must be one of "
                f"{', '.join(sorted(known_levels))}.",
                file=sys.stderr,
            )
            sys.exit(1)
        axis_raw = spec.get("axis")
        axis = None
        if axis_raw is not None:
            axis = axis_for_key(str(axis_raw))
            if axis is None:
                print(
                    f"Error: differentiation #{i} names unknown axis '{axis_raw}'.",
                    file=sys.stderr,
                )
                sys.exit(1)
        titles = _require_str_list(spec, "prior_titles", i)
        tags = _require_str_list(spec, "prior_theme_tags", i)
        directives.append(
            build_differentiation_directive(
                level=level_raw if isinstance(level_raw, str) else None,
                axis_instruction=axis.instruction if axis is not None else None,
                prior_titles=titles,
                prior_theme_tags=tags,
            )
        )
    return directives


def _require_str_list(spec: dict[str, object], key: str, index: int) -> list[str]:
    """Return a spec entry's list-of-strings field, or exit on any other shape.

    A scalar where a list belongs, or a non-string member, must be a hard
    error for the same reason an unknown axis key is: silently dropping the
    malformed part would run a WEAKER directive than the operator specified
    and report its convergence as the directed floor.

    Args:
        spec: The differentiation spec entry.
        key: The field to read (``prior_titles`` or ``prior_theme_tags``).
        index: The entry's position, for the error message.

    Returns:
        The non-empty string members; ``[]`` when the field is absent.

    Raises:
        SystemExit: If the field is not a list of strings.
    """
    value = spec.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in cast("list[object]", value)
    ):
        print(
            f"Error: differentiation #{index} {key} must be a list of strings.",
            file=sys.stderr,
        )
        sys.exit(1)
    return [item for item in cast("list[str]", value) if item]


def _load_skeletons(paths: Sequence[Path], brief_count: int) -> list[dict[str, object]]:
    """Load one skeleton per brief, broadcasting a lone skeleton across all of them.

    Pairing a distinct skeleton with each brief is what makes a within-vendor
    pair share nothing but the model and the age band, which is the condition
    the 3.3 idiom floor was measured under. A single skeleton is still accepted
    because it is the cheaper setup and still measures the vendor contrast, but
    the caller is told what the resulting number is not.

    Args:
        paths: One or ``brief_count`` skeleton JSON paths, in brief order.
        brief_count: How many briefs the run will use.

    Returns:
        Exactly ``brief_count`` skeleton dicts, index-aligned with the briefs.

    Raises:
        SystemExit: If a file is not a JSON object, or the count is neither 1
            nor ``brief_count``.
    """
    loaded: list[dict[str, object]] = []
    for path in paths:
        parsed = _load_json(path)
        if not isinstance(parsed, dict):
            print(f"Error: {path} must contain a JSON object.", file=sys.stderr)
            sys.exit(1)
        loaded.append(dict(parsed))  # pyright: ignore[reportUnknownArgumentType]

    if len(loaded) == 1 and brief_count > 1:
        print(
            "Note: one skeleton for all briefs. Within-vendor pairs will share "
            "structure, so that number is a shared-structure figure and is not "
            "comparable to the 3.3 floor, which was measured on books sharing "
            "nothing. Pass one --skeleton per brief for the comparable number.",
            file=sys.stderr,
        )
        return [dict(loaded[0]) for _ in range(brief_count)]
    if len(loaded) != brief_count:
        print(
            f"Error: got {len(loaded)} skeleton(s) for {brief_count} brief(s); "
            "pass either one skeleton or exactly one per brief.",
            file=sys.stderr,
        )
        sys.exit(1)
    return loaded


def _band(doc: dict[str, Any]) -> tuple[float, float] | None:
    """Return the declared reading-level target and tolerance, if any.

    Args:
        doc: A filled Storybook dict.

    Returns:
        ``(target, tolerance)``, or ``None`` when the document declares no
        numeric reading-level band (in which case no FK figure is meaningful).
    """
    metadata = doc.get("metadata")
    if not isinstance(metadata, dict):
        return None
    level: object = metadata.get("reading_level")  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(level, dict):
        return None
    target: object = level.get("target")  # pyright: ignore[reportUnknownMemberType]
    tolerance: object = level.get("tolerance")  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(target, (int, float)) or not isinstance(tolerance, (int, float)):
        return None
    return float(target), float(tolerance)


def _bodies(doc: dict[str, Any]) -> list[str]:
    """Return every node body in a filled document.

    Args:
        doc: A filled Storybook dict.

    Returns:
        The node bodies, in document order.
    """
    nodes: object = doc.get("nodes")
    if not isinstance(nodes, list):
        return []
    out: list[str] = []
    for raw in nodes:  # pyright: ignore[reportUnknownVariableType]
        node: object = raw  # pyright: ignore[reportUnknownVariableType]
        if isinstance(node, dict):
            body: object = node.get("body")  # pyright: ignore[reportUnknownMemberType]
            if isinstance(body, str):
                out.append(body)
    return out


def _measure(doc: dict[str, Any]) -> tuple[float | None, float | None, int]:
    """Measure whole-book reading level for one filled document.

    Args:
        doc: A filled Storybook dict.

    Returns:
        ``(grade, in_band_fraction, scorable_words)``. The first two are
        ``None`` when the document declares no band or has too little scorable
        prose for a stable Flesch-Kincaid figure.
    """
    band = _band(doc)
    if band is None:
        return None, None, 0
    target, tolerance = band
    measured = measure_book(_bodies(doc), target=target, tolerance=tolerance)
    if measured is None:
        return None, None, 0
    return measured.grade, measured.in_band, measured.words


@dataclass(frozen=True)
class _CapOverrideProvider:
    """Substitute the completion cap the orchestrator asks for.

    ``orchestrator._MAX_TOKENS_PROSE`` is a module constant, so a comparison run
    cannot vary the budget without editing production defaults. Reasoning models
    make that budget a live experimental variable rather than a formality: a leg
    that spends 19,500 tokens thinking before writing a word needs headroom a
    non-reasoning leg never touches, and a cap set below that overhead returns
    empty content that looks exactly like a dead endpoint (measured on DeepSeek
    V4 Flash, 2026-08-12).

    Wrapping the provider keeps the override at the harness boundary, where it
    is visible in the report, instead of mutating a shared constant that every
    other caller reads. Satisfies :class:`GenerationProvider` structurally.

    Attributes:
        inner: The real provider that performs the call.
        max_tokens: The cap to send, replacing whatever the caller passed.
    """

    inner: GenerationProvider
    max_tokens: int

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Delegate with the configured cap in place of the requested one.

        Args:
            system: System-role instructions, passed through unchanged.
            prompt: User-role prompt, passed through unchanged.
            max_tokens: The orchestrator's cap. Deliberately ignored; the
                override exists precisely to replace it.

        Returns:
            The inner provider's completion, forwarded unchanged. The
            annotation matters more than it looks: declared as ``str`` this
            wrapper stopped satisfying :class:`GenerationProvider` structurally
            and invited the next caller to treat a ``Completion`` as text, which
            is the defect the judge panel was carrying in the sibling script.
        """
        del max_tokens
        return await self.inner.complete(
            system=system, prompt=prompt, max_tokens=self.max_tokens
        )


@dataclass(frozen=True)
class _ModelStampedProvider:
    """Carry the leg's model id where the orchestrator can see it.

    ``fill_skeleton`` resolves its output cap (and with it the chunking
    decision) from ``getattr(provider, "model", None)``, but the OpenRouter
    adapter exposes only ``complete`` and ``name``, so every wrapper above it
    forwards ``None`` and the cap silently resolves to the 131,072 default.
    On this harness that meant `MODEL_OUTPUT_CAPS` was never consulted for any
    leg: a low-cap model (`deepseek/deepseek-v3.2`, 65,536) was asked for
    131,072 tokens one-shot, which its endpoint rejected outright (HTTP 400,
    measured 2026-08-21 at 0.6s per leg), and the chunked path could never
    engage for any vendor. Stamping the model at the harness boundary makes
    the leg behave as the orchestrator's own resolution logic intends. The
    matching production gap (the adapter itself, reached via
    ``build_provider``) is deliberately NOT fixed here; it is reported in the
    2026-08-21 round's lessons instead.

    Attributes:
        inner: The real provider that performs the call.
        model: The vendor spec's model id, exposed for cap resolution.
    """

    inner: GenerationProvider
    model: str

    @property
    def name(self) -> str | None:
        """The inner provider's label, forwarded for job stamping."""
        inner_name: object = getattr(self.inner, "name", None)
        return inner_name if isinstance(inner_name, str) else None

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Delegate unchanged; this wrapper only carries the model id.

        Args:
            system: System-role instructions, passed through unchanged.
            prompt: User-role prompt, passed through unchanged.
            max_tokens: The caller's cap, passed through unchanged.

        Returns:
            The inner provider's completion, forwarded unchanged.
        """
        return await self.inner.complete(
            system=system, prompt=prompt, max_tokens=max_tokens
        )


def _build_provider(
    vendor: Vendor,
    settings: Settings,
    *,
    mock: bool,
    max_tokens: int | None = None,
) -> GenerationProvider:
    """Build a fresh single-leg provider for one vendor.

    No cascade is used: a failover to another model would silently attribute
    another vendor's prose to this one, which is exactly the error this
    measurement exists to avoid.

    Args:
        vendor: The vendor whose model and backend pin to use.
        settings: Settings supplying the credential, base url, and timeout.
        mock: When ``True`` return the deterministic mock provider instead, so a
            dry run exercises the whole path without spending anything.
        max_tokens: Completion cap to force for every call on this leg. ``None``
            leaves the orchestrator's own budget in place. A run that sets this
            is NOT comparable to one that does not: the budget bounds how much a
            leg can deliver, so it is part of the measurement, not a knob.

    Returns:
        A provider ready for one book.
    """
    if mock:
        base = build_provider(Settings())
    else:
        base = build_openrouter_leg(
            settings, vendor.model, provider_order=vendor.provider_order
        )
    if max_tokens is not None:
        base = _CapOverrideProvider(inner=base, max_tokens=max_tokens)
    if mock:
        return base
    # Outermost, so `getattr(provider, "model", None)` sees it through every
    # inner wrapper; see _ModelStampedProvider for why the leg needs it at all.
    return _ModelStampedProvider(inner=base, model=vendor.model)


async def run_comparison(
    skeletons: Sequence[dict[str, object]],
    briefs: Sequence[dict[str, object]],
    vendors: Sequence[Vendor],
    *,
    mock: bool = True,
    throttle: float = 0.0,
    settings: Settings | None = None,
    max_tokens: int | None = None,
    out_dir: Path | None = None,
    directives: Sequence[str] | None = None,
) -> list[BookRecord]:
    """Fill the grid once per (vendor, brief) and measure every result.

    Args:
        skeletons: One skeleton per brief, index-aligned, FILL directives
            intact. Each is copied per fill so no run mutates another's input.
            Every vendor sees the same skeleton for a given brief index, which
            is what holds structure constant across the vendor axis.
        briefs: The theme briefs; every vendor sees all of them, in order.
        vendors: The vendor legs to compare.
        mock: When ``True`` every leg is the deterministic mock provider. The
            resulting numbers are a plumbing dry run, not a vendor comparison,
            because the mock echoes one canned story for every call.
        throttle: Seconds to sleep after each fill, for per-minute rate limits.
        settings: Settings for the live legs. Defaults to a fresh ``Settings()``.
        max_tokens: Completion cap forced on every leg, or ``None`` to use the
            orchestrator's default. Applied uniformly so the legs stay
            comparable to each other, but a run at one cap cannot be pooled with
            a run at another.
        out_dir: When given, each book is written to ``out_dir/books/`` and
            journalled to ``out_dir/books.jsonl`` the moment it completes, so
            an interrupted run keeps everything it has already paid for
            (AL-326). ``None`` keeps the records in memory only, which is what
            the dry-run path and the unit tests want.
        directives: One rendered differentiation directive per brief, from
            :func:`_load_differentiation`, or ``None`` to fill undirected
            (byte-identical to every run before the flag existed). Every vendor
            sees the same directive for a given brief index, mirroring how the
            skeleton is held constant across the vendor axis. A run with
            directives is measuring a different quantity than one without
            (AL-498: the directed floor against the raw floor), so the two must
            never be pooled; ``main`` records the directives in the run's
            metadata for exactly that reason.

    Returns:
        One :class:`BookRecord` per (vendor, brief), vendor-major order.

    Raises:
        ValueError: If the skeleton and brief counts disagree (which would
            silently pair the wrong structure with a premise), or if the
            directive count disagrees with the briefs.
    """
    if directives is not None and len(directives) != len(briefs):
        message = (
            f"directives ({len(directives)}) and briefs ({len(briefs)}) must "
            "be the same length; they pair index-wise"
        )
        raise ValueError(message)
    if len(skeletons) != len(briefs):
        message = (
            f"skeletons ({len(skeletons)}) and briefs ({len(briefs)}) must be "
            "the same length; they pair index-wise"
        )
        raise ValueError(message)
    # #CRITICAL: security: this harness reaches a paid third-party endpoint and
    # must never carry real child identity into a prompt. The PII context is
    # empty by construction and the briefs are operator-authored fixtures, not
    # profile data pulled from the database.
    # #VERIFY: test_compare_vendors_uses_an_empty_pii_context asserts the
    # frozenset handed to fill_skeleton is empty.
    pii = PiiContext(child_names=frozenset())
    resolved = settings if settings is not None else Settings()
    records: list[BookRecord] = []

    for vendor in vendors:
        for index, brief in enumerate(briefs):
            # One ledger per book, never one per run: the comparison's whole
            # point is per-leg economics, and a shared accumulator would report
            # the slate's total against whichever book happened to be last.
            ledger = UsageLedger()
            provider = MeteredProvider(
                _build_provider(vendor, resolved, mock=mock, max_tokens=max_tokens),
                ledger=ledger,
            )
            # The cap the fill will really run under: `fill_skeleton` resolves it
            # from the provider's own model, so reporting `_PROSE_CAP` here made
            # the near-cap heuristic below compare against a ceiling no leg used.
            effective_cap = (
                max_tokens
                if max_tokens is not None
                else resolve_output_cap(getattr(provider, "model", None))
            )
            started = time.monotonic()
            try:
                outcome = await fill_skeleton(
                    dict(skeletons[index]),
                    dict(brief),
                    provider,
                    pii,
                    stage1_gate="skipped",
                    differentiation_directive=(
                        directives[index] if directives is not None else ""
                    ),
                )
            except Exception as exc:  # one book's failure must not void the batch
                # A comparison over N vendors is expensive; losing every prior
                # result to one vendor's outage would mean paying twice.
                records.append(
                    BookRecord(
                        vendor=vendor.label,
                        family=vendor.lineage(),
                        brief_index=index,
                        status="error",
                        attempts=0,
                        latency_s=round(time.monotonic() - started, 2),
                        grade=None,
                        in_band=None,
                        fill_rate=None,
                        leaf_words=0,
                        doc=None,
                        error=str(exc)[:512],
                        max_tokens=effective_cap,
                        **_metered_fields(ledger, vendor),
                    )
                )
            else:
                doc = outcome.storybook
                grade, in_band, words = (
                    _measure(doc) if doc is not None else (None, None, 0)
                )
                records.append(
                    BookRecord(
                        vendor=vendor.label,
                        family=vendor.lineage(),
                        brief_index=index,
                        status=outcome.status,
                        attempts=outcome.attempts,
                        latency_s=round(time.monotonic() - started, 2),
                        grade=grade,
                        in_band=in_band,
                        fill_rate=(
                            story_fill_rate(dict(skeletons[index]), doc)
                            if doc is not None
                            else None
                        ),
                        leaf_words=words,
                        doc=doc,
                        error=None,
                        fill_completeness=_fill_completeness(doc),
                        max_tokens=effective_cap,
                        **_reading_level_fields(outcome.report),
                        **_metered_fields(ledger, vendor),
                    )
                )
            last = records[-1]
            # Persist before printing: the progress line is a convenience, the
            # book is the thing that was paid for.
            if out_dir is not None:
                persist_book(out_dir, last)
            # Carry the failure text on the progress line, not only into the
            # report. A misconfigured pin fails every book identically, and the
            # operator needs to see why on book #0 rather than after paying for
            # the other twenty-three. The journal now carries the same detail
            # durably, so this line is the live signal rather than the only one.
            detail = "" if last.error is None else f" error={last.error[:160]}"
            print(
                f"[{vendor.label} #{index}] status={last.status} "
                f"fk={last.grade} in_band={last.in_band} "
                f"fill_rate={last.fill_rate} "
                f"latency={last.latency_s}s{detail}",
                file=sys.stderr,
                flush=True,
            )
            if throttle > 0:
                await asyncio.sleep(throttle)

    return records


def _fill_completeness(doc: dict[str, Any] | None) -> float:
    """Return the fraction of node bodies that are prose rather than a directive.

    Args:
        doc: The filled Storybook dict, or ``None``.

    Returns:
        ``0.0`` when no document was produced or it carries no nodes, otherwise
        the share of bodies with no retained ``<<FILL`` marker. Schema validity
        is not the same question: a skeleton echoed back is schema-clean and
        entirely unwritten, and four such books out of thirty-two inverted a
        published diversity verdict (`AL-335`).
    """
    if doc is None:
        return 0.0
    nodes = doc.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return 0.0
    bodies = [
        node.get("body")
        for node in cast("list[dict[str, Any]]", nodes)
        if isinstance(node, dict)
    ]
    if not bodies:
        return 0.0
    written = sum(
        1 for body in bodies if isinstance(body, str) and "<<FILL" not in body
    )
    return written / len(bodies)


def _reading_level_fields(report: dict[str, object]) -> dict[str, Any]:
    """Lift Stage D's self-reported degradation out of the gate report.

    A book whose reading-level repair was discarded, or partly dropped, is
    indistinguishable from a fully repaired one everywhere else in the artifact:
    ``status`` reads ``passed`` either way. Carrying the two fields into the
    per-book row is what lets a leg comparison exclude or flag affected books
    without regenerating anything (`AL-350`).

    Args:
        report: The generation outcome's report mapping.

    Returns:
        The ``reading_level_*`` keyword arguments for :class:`BookRecord`.
    """
    level = report.get("reading_level")
    if not isinstance(level, dict):
        return {}
    entry = cast("dict[str, object]", level)
    dropped = entry.get("nodes_dropped")
    return {
        "reading_level_degraded": bool(entry.get("degraded", False)),
        "reading_level_nodes_dropped": dropped if isinstance(dropped, int) else 0,
    }


def _metered_fields(ledger: UsageLedger, vendor: Vendor) -> dict[str, Any]:
    """Price one book from the calls it actually made.

    Args:
        ledger: This book's ledger, holding one entry per provider call.
        vendor: The leg, whose slug is the price-table key.

    Returns:
        The token and cost keyword arguments for :class:`BookRecord`.

    Note:
        Costed across every call the book consumed, fill plus repairs, rather
        than the fill alone. A leg that needs three repairs to deliver is more
        expensive than one that lands first time, and charging only the first
        call would hide exactly the difference this comparison exists to find.
    """
    if not ledger.calls:
        return {"cost_unavailable_reason": "no provider call was metered for this book"}
    totals = ledger.snapshot()
    price = price_for("openrouter", vendor.model)
    estimate = estimate_cost(price, totals.input_tokens, totals.output_tokens)
    reasoning = [
        call.reasoning_tokens
        for call in ledger.calls
        if call.reasoning_tokens is not None
    ]
    return {
        "output_tokens": totals.output_tokens if totals.unknown_calls == 0 else None,
        "reasoning_tokens": sum(reasoning) if reasoning else None,
        "cost_usd": float(estimate.amount_usd),
        "cost_complete": estimate.complete and totals.unknown_calls == 0,
        "cost_unavailable_reason": (
            estimate.reason
            if not estimate.complete
            else (
                f"{totals.unknown_calls} of {totals.call_count} calls reported no usage"
                if totals.unknown_calls
                else ""
            )
        ),
    }


def _summarize(rates: list[float]) -> dict[str, float]:
    """Reduce a list of per-pair rates to the figures the report quotes.

    Args:
        rates: Shared four-grams per 1000 leaf words, one entry per pair.

    Returns:
        ``{"pairs", "mean_per_1000", "median_per_1000", "max_per_1000"}``. An
        empty input yields zeros with ``pairs == 0``, which reads as "not
        measured" rather than as a clean result.

        The median is reported beside the mean as a contamination detector. A
        handful of near-identical pairs drags a mean and barely moves a median,
        so a large gap between the two says the bucket is being decided by a few
        outliers rather than by its population; four unfilled books out of
        thirty-two did exactly that and inverted a published verdict (`AL-335`).
    """
    if not rates:
        return {
            "pairs": 0.0,
            "mean_per_1000": 0.0,
            "median_per_1000": 0.0,
            "max_per_1000": 0.0,
        }
    return {
        "pairs": float(len(rates)),
        "mean_per_1000": round(statistics.fmean(rates), 2),
        "median_per_1000": round(statistics.median(rates), 2),
        "max_per_1000": round(max(rates), 2),
    }


def analyze(records: Sequence[BookRecord]) -> ComparisonReport:
    """Bucket every book pair by vendor axis and brief axis, then compare.

    Only books that were **fully written** participate. Schema validity is the
    wrong test: a skeleton echoed back parses, and an unfilled book inflates
    within-vendor similarity (near-identical directives) while deflating
    cross-vendor similarity (directives share nothing with prose) at the same
    time, moving the headline ratio in both directions at once. Four such books
    out of thirty-two inverted the published verdict (`AL-335`), so the
    participation test is ``BookRecord.complete`` and the excluded books are
    named in the report rather than dropped quietly. Pairs are computed with
    ``scripts/check_sibling_fills.pairwise_shared_grams``, so the rates use the
    same four-gram definition, stopword handling, and per-1000 normalization as
    the calibrated 3.3 sibling-fill floor and are directly comparable to it.

    Args:
        records: The book records from :func:`run_comparison`.

    Returns:
        A :class:`ComparisonReport`. When fewer than two books produced a
        document, every bucket is empty and the verdict says so.
    """
    _ensure_repo_on_path()
    from scripts.check_sibling_fills import pairwise_shared_grams  # noqa: PLC0415

    usable = [r for r in records if r.complete]
    excluded = tuple(
        f"{r.vendor}#{r.brief_index} ({r.fill_completeness:.0%} filled)"
        for r in records
        if r.doc is not None and not r.complete
    )
    if len(usable) < 2:
        return ComparisonReport(
            books=list(records),
            within_vendor={},
            cross_vendor=_summarize([]),
            same_brief_cross_vendor=_summarize([]),
            same_family_cross_model=_summarize([]),
            same_family_same_brief=_summarize([]),
            excluded_incomplete=excluded,
            verdict="not measured: fewer than two books were fully written",
        )

    docs = [r.doc for r in usable if r.doc is not None]
    rates = {(i, j): rate for i, j, _count, rate in pairwise_shared_grams(docs)}

    within: dict[str, list[float]] = {}
    cross: list[float] = []
    same_brief_cross: list[float] = []
    family_cross: list[float] = []
    family_same_brief: list[float] = []
    for i, j in combinations(range(len(usable)), 2):
        rate = rates[(i, j)]
        left, right = usable[i], usable[j]
        same_vendor = left.vendor == right.vendor
        same_family = left.family == right.family
        same_brief = left.brief_index == right.brief_index
        if same_vendor:
            # A same-vendor same-brief pair means one vendor filled one brief
            # twice. run_comparison never produces one; if a caller assembles
            # records that do, it belongs in no floor and is dropped here.
            if not same_brief:
                within.setdefault(left.vendor, []).append(rate)
        elif same_family:
            # Two checkpoints of one lab. Neither a within-vendor floor nor a
            # cross-vendor one: it is the version-bump control, and folding it
            # into cross_vendor would bias the headline toward "task-driven".
            (family_same_brief if same_brief else family_cross).append(rate)
        else:
            (same_brief_cross if same_brief else cross).append(rate)

    within_summary = {label: _summarize(vals) for label, vals in sorted(within.items())}
    cross_summary = _summarize(cross)
    return ComparisonReport(
        books=list(records),
        within_vendor=within_summary,
        cross_vendor=cross_summary,
        same_brief_cross_vendor=_summarize(same_brief_cross),
        same_family_cross_model=_summarize(family_cross),
        same_family_same_brief=_summarize(family_same_brief),
        excluded_incomplete=excluded,
        verdict=_verdict(within_summary, cross_summary),
    )


def _verdict(within: dict[str, dict[str, float]], cross: dict[str, float]) -> str:
    """State what the two floors imply for the diversification strategy.

    Args:
        within: The per-vendor within-vendor summaries.
        cross: The cross-vendor summary.

    Returns:
        A one-line reading. The 15% threshold is a reporting convention for
        "materially different", not a gate; nothing fails on it.
    """
    means = [s["mean_per_1000"] for s in within.values() if s["pairs"] > 0]
    if not means or cross["pairs"] == 0:
        return "not measured: need both within-vendor and cross-vendor pairs"
    within_mean = statistics.fmean(means)
    cross_mean = cross["mean_per_1000"]
    if cross_mean <= 0:
        return "cross-vendor pairs share no four-grams at all; check the inputs"
    ratio = within_mean / cross_mean
    medians = [s["median_per_1000"] for s in within.values() if s["pairs"] > 0]
    contamination = _contamination_note(
        ratio, statistics.fmean(medians), cross["median_per_1000"]
    )
    if contamination:
        return contamination
    if ratio >= 1.15:
        return (
            f"vendor-driven: within-vendor {within_mean:.2f} exceeds cross-vendor "
            f"{cross_mean:.2f} per 1000 (ratio {ratio:.2f}); rotating vendors "
            "removes idiom that rotating briefs does not"
        )
    if ratio <= 0.87:
        return (
            f"inverted: within-vendor {within_mean:.2f} is BELOW cross-vendor "
            f"{cross_mean:.2f} per 1000 (ratio {ratio:.2f}); investigate before "
            "acting, this is not the expected shape"
        )
    return (
        f"task-driven: within-vendor {within_mean:.2f} and cross-vendor "
        f"{cross_mean:.2f} per 1000 are comparable (ratio {ratio:.2f}); the floor "
        "follows the skeleton and prompt, so vendor rotation buys little"
    )


def _contamination_note(
    mean_ratio: float, within_median: float, cross_median: float
) -> str:
    """Refuse a verdict the mean and the median do not agree on.

    The mean-versus-median gap is the contamination detector `AL-335` asked for.
    Both statistics answer the same question over the same pairs, so a
    disagreement large enough to cross the reporting thresholds means a few
    outlier pairs are deciding the headline. Reporting the mean alone would
    publish their verdict as the population's.

    Args:
        mean_ratio: Within-over-cross computed from the bucket means.
        within_median: Mean of the per-vendor within-vendor medians.
        cross_median: The cross-vendor median.

    Returns:
        A one-line refusal when the two ratios straddle a threshold, else the
        empty string.
    """
    if cross_median <= 0:
        return ""
    median_ratio = within_median / cross_median

    def _band(ratio: float) -> str:
        if ratio >= 1.15:
            return "vendor-driven"
        if ratio <= 0.87:
            return "inverted"
        return "task-driven"

    if _band(mean_ratio) == _band(median_ratio):
        return ""
    return (
        f"contaminated: the mean ratio ({mean_ratio:.2f}) and the median ratio "
        f"({median_ratio:.2f}) fall in different bands "
        f"({_band(mean_ratio)} vs {_band(median_ratio)}), so a few outlier pairs "
        "are deciding this verdict rather than the population. Inspect the pair "
        "distribution before quoting either figure"
    )


def _pairs(summary: dict[str, float]) -> str:
    """Render a bucket's pair count for the printed table.

    Args:
        summary: A bucket summary from :func:`_summarize`.

    Returns:
        ``"n pairs"``, or ``"1 pair"``.
    """
    count = int(summary["pairs"])
    return f"{count} pair" if count == 1 else f"{count} pairs"


def _print_report(
    report: ComparisonReport,
    *,
    structure_varies: bool = True,
    directed: bool = False,
) -> None:
    """Print the human-readable summary to stdout.

    Args:
        report: The analyzed comparison.
        structure_varies: Whether each brief had its own skeleton. When it did
            not, the within-vendor number is a shared-structure figure and the
            printer says so, because 3.3 is the obvious thing a reader will
            compare it against and that comparison would not be like for like.
        directed: Whether any fill was given a differentiation directive. A
            directed run measures the DIRECTED floor, not the raw one
            (`AL-498`), so the two must never be pooled. Recording that in the
            report metadata alone is not enough: the console summary is what an
            operator reads and pastes into a calibration record, so it has to
            carry the same caveat.
    """
    print("=" * 72)
    print("Cross-vendor fill comparison")
    print("=" * 72)
    # Sized to the longest label actually present rather than a constant: a
    # descriptive slate ("anthropic-sonnet-4.6") overflows any fixed width and
    # ragged columns are the kind of thing that gets read as a bug in the run.
    width = max((len(r.vendor) for r in report.books), default=0)
    width = max(width, len("vendor"))
    print(
        f"{'vendor':<{width}}{'book':>6}{'status':>14}{'FK':>7}{'in-band':>9}"
        f"{'fill':>7}{'sec':>8}"
    )
    for record in report.books:
        grade = "-" if record.grade is None else f"{record.grade:.2f}"
        in_band = "-" if record.in_band is None else f"{record.in_band:.0%}"
        fill_rate = "-" if record.fill_rate is None else f"{record.fill_rate:.0%}"
        print(
            f"{record.vendor:<{width}}{record.brief_index:>6}{record.status:>14}"
            f"{grade:>7}{in_band:>9}{fill_rate:>7}{record.latency_s:>8.1f}"
        )
    print()
    print("Shared four-grams per 1000 leaf words (different-brief pairs):")
    if not structure_varies:
        print(
            "  one skeleton for every brief: within-vendor pairs share "
            "structure, so these are NOT comparable to the 3.3 floor."
        )
    elif directed:
        print(
            "  a differentiation directive was injected into these fills, so "
            "this is the DIRECTED floor and is NOT comparable to the 3.3 "
            "floor, which was measured undirected."
        )
    else:
        print(
            "  within-vendor pairs share nothing but the model and the band, "
            "and no differentiation directive was passed: the condition the "
            "3.3 floor was measured under."
        )
    # "within " is 7 characters, so padding the bucket names to 7 wider than the
    # widest vendor label keeps both kinds of row sharing one "mean" column.
    name_width = max([14, *(len(label) for label in report.within_vendor)]) + 7
    for label, summary in report.within_vendor.items():
        print(
            f"  within {label:<{name_width - 7}} mean "
            f"{summary['mean_per_1000']:>6.2f}  "
            f"max {summary['max_per_1000']:>6.2f}  ({_pairs(summary)})"
        )
    cross = report.cross_vendor
    print(
        f"  {'cross-vendor':<{name_width}} mean {cross['mean_per_1000']:>6.2f}  "
        f"max {cross['max_per_1000']:>6.2f}  ({_pairs(cross)})"
    )
    family = report.same_family_cross_model
    if family["pairs"] > 0:
        print(
            f"  {'same lab, new model':<{name_width}} mean {family['mean_per_1000']:>6.2f}  "
            f"max {family['max_per_1000']:>6.2f}  ({_pairs(family)})"
        )
        print(
            "    the version-bump control: two checkpoints of one lab, held "
            "out of the cross-vendor floor above."
        )
    print()
    print("Reported separately, never part of the headline:")
    same = report.same_brief_cross_vendor
    print(
        f"  {'same brief, cross lab':<{name_width}} mean {same['mean_per_1000']:>6.2f}  "
        f"max {same['max_per_1000']:>6.2f}  ({_pairs(same)})  premise convergence"
    )
    fsb = report.same_family_same_brief
    if fsb["pairs"] > 0:
        print(
            f"  {'same brief, same lab':<{name_width}} mean {fsb['mean_per_1000']:>6.2f}  "
            f"max {fsb['max_per_1000']:>6.2f}  ({_pairs(fsb)})  both confounds"
        )
    if report.excluded_incomplete:
        print()
        print(
            f"  EXCLUDED from every bucket, not fully written: "
            f"{', '.join(report.excluded_incomplete)}"
        )
    _print_conditions(report.books)
    print()
    print(f"Verdict: {report.verdict}")
    print("=" * 72)


def _print_conditions(books: Sequence[BookRecord]) -> None:
    """Print the conditions the measurement ran under, and any cost it recorded.

    The completion cap belongs here rather than in a config file nobody reads
    back: it is a variable of the experiment, not a setting. A leg that spent its
    whole budget was measured against the wall rather than against its own
    limits, so its fill rate is suppressed rather than printed (`AL-328`).

    Args:
        books: Every book record from the run.
    """
    caps = sorted({b.max_tokens for b in books if b.max_tokens is not None})
    if not caps:
        return
    print()
    cap_text = ", ".join(str(c) for c in caps)
    print(f"  Completion cap (a measured condition, not a setting): {cap_text}")
    if len(caps) > 1:
        print(
            "  WARNING: books in this report were written at DIFFERENT caps and "
            "are not poolable."
        )

    near = sorted({b.vendor for b in books if b.near_cap})
    if near:
        print(
            f"  No budget headroom, fill rate NOT reported for: {', '.join(near)}. "
            "These legs were measured against the cap rather than against "
            "themselves."
        )

    priced = [b for b in books if b.cost_usd is not None and b.cost_complete]
    if priced:
        total = sum(b.cost_usd or 0.0 for b in priced)
        print(f"  Cost: ${total:.4f} over {len(priced)} priced books.")
    unpriced = [b for b in books if not b.cost_complete]
    if unpriced:
        reasons = sorted(
            {b.cost_unavailable_reason for b in unpriced if b.cost_unavailable_reason}
        )
        detail = f" ({reasons[0]})" if reasons else ""
        print(f"  Cost incomplete for {len(unpriced)} of {len(books)} books{detail}.")

    degraded = sorted({b.vendor for b in books if b.reading_level_degraded})
    if degraded:
        print(
            f"  Stage D did less than it was asked to on: {', '.join(degraded)}. "
            "Those books read as repaired everywhere else; exclude or flag them."
        )


def _book_row(record: BookRecord) -> dict[str, object]:
    """Render one book's metadata row, shared by the journal and the report.

    Both writers must describe a book identically, or reconstructing a killed
    run from its journal would produce a report subtly unlike the one the run
    would have written itself.

    Args:
        record: The book to describe.

    Returns:
        The row, whose ``file`` is the report-relative path to the book JSON,
        or ``None`` when the leg produced no document.
    """
    return {
        "vendor": record.vendor,
        "family": record.family,
        "brief_index": record.brief_index,
        "status": record.status,
        "attempts": record.attempts,
        "latency_s": record.latency_s,
        "grade": record.grade,
        "in_band": record.in_band,
        "fill_rate": record.fill_rate,
        "leaf_words": record.leaf_words,
        "fill_completeness": round(record.fill_completeness, 3),
        "complete": record.complete,
        "max_tokens": record.max_tokens,
        "output_tokens": record.output_tokens,
        "reasoning_tokens": record.reasoning_tokens,
        "near_cap": record.near_cap,
        "reading_level_degraded": record.reading_level_degraded,
        "reading_level_nodes_dropped": record.reading_level_nodes_dropped,
        "cost": record.cost_usd,
        "cost_complete": record.cost_complete,
        "cost_unavailable_reason": record.cost_unavailable_reason,
        "file": f"books/{_book_filename(record)}" if record.doc is not None else None,
        "error": record.error,
    }


def _book_filename(record: BookRecord) -> str:
    """Name a book file from its grid position.

    Args:
        record: The book to name.

    Returns:
        A ``{vendor}__{index:02d}.json`` filename, unique per grid cell.
    """
    return f"{record.vendor}__{record.brief_index:02d}.json"


def persist_book(out_dir: Path, record: BookRecord) -> None:
    """Write one completed book and journal its row, as soon as it is bought.

    #CRITICAL: data integrity: this is the only thing standing between an
    interrupted run and the total loss of everything it has already paid a
    third party for. A multi-hour run that writes only at the end loses every
    book to any kill, which is not hypothetical: run-6 lost three completed
    books (1,869 seconds of billed provider time) to an environment restart on
    2026-08-12 because the output directory did not yet exist (AL-326).
    #VERIFY: test_an_interrupted_run_keeps_the_books_it_already_paid_for in
    tests/unit/test_compare_vendors.py kills a run mid-grid with a
    BaseException, which the per-book handler cannot absorb, and asserts the
    earlier books survive on disk.

    The journal is appended rather than rewritten so a book already flushed can
    never be lost by a later failure, and an errored leg still leaves a row
    even though it has no document to write.

    Args:
        out_dir: The run's output directory, created if absent.
        record: The book that just completed, successfully or not.
    """
    books_dir = out_dir / "books"
    books_dir.mkdir(parents=True, exist_ok=True)
    if record.doc is not None:
        (books_dir / _book_filename(record)).write_text(
            json.dumps(record.doc, indent=2) + "\n", encoding="utf-8"
        )
    with (out_dir / "books.jsonl").open("a", encoding="utf-8") as journal:
        journal.write(json.dumps(_book_row(record)) + "\n")


def _write_outputs(
    out_dir: Path, report: ComparisonReport, meta: dict[str, object]
) -> None:
    """Write the report JSON and every filled book to ``out_dir``.

    Books are normally already on disk, written by :func:`persist_book` as each
    completed. Rewriting them here is deliberate and idempotent: it keeps this
    function correct for a caller that analyzed records it did not persist
    incrementally, and the content is identical either way.

    Args:
        out_dir: Destination directory, created if absent.
        report: The analyzed comparison.
        meta: Run metadata merged into the report payload.
    """
    books_dir = out_dir / "books"
    books_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for record in report.books:
        if record.doc is not None:
            (books_dir / _book_filename(record)).write_text(
                json.dumps(record.doc, indent=2) + "\n", encoding="utf-8"
            )
        rows.append(_book_row(record))
    payload: dict[str, object] = {
        **meta,
        "books": rows,
        "within_vendor": report.within_vendor,
        "cross_vendor": report.cross_vendor,
        "same_brief_cross_vendor": report.same_brief_cross_vendor,
        "same_family_cross_model": report.same_family_cross_model,
        "same_family_same_brief": report.same_family_same_brief,
        "excluded_incomplete": list(report.excluded_incomplete),
        "verdict": report.verdict,
    }
    (out_dir / "report.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _load_env_file(env_path: Path) -> None:
    """Load ``KEY=VALUE`` lines from ``env_path`` into ``os.environ``.

    Existing variables win, so an explicitly exported key is never overwritten
    by the dotenv file. Mirrors ``scripts/yield_harness.py``'s loader.

    Args:
        env_path: A dotenv-style file. A missing file is a no-op.
    """
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Build the argument parser and parse argv.

    Args:
        argv: Argument vector, or ``None`` to read ``sys.argv``.

    Returns:
        The parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Compare how different vendors fill one skeleton, and report the "
            "within-vendor and cross-vendor shared-idiom floors."
        )
    )
    parser.add_argument(
        "--skeleton",
        required=True,
        action="append",
        type=Path,
        dest="skeletons",
        help=(
            "Skeleton JSON to fill. Repeatable; pairs index-wise with --briefs. "
            "Pass one per brief so within-vendor pairs share no structure, or a "
            "single one to reuse it for every brief."
        ),
    )
    parser.add_argument(
        "--briefs", required=True, type=Path, help="JSON array of theme briefs."
    )
    parser.add_argument(
        "--vendors",
        type=Path,
        default=None,
        help=(
            "JSON array of vendor specs. Required unless --mock. Passing it "
            "with --mock too is recommended: the dry run then rehearses the "
            "real leg count and family layout instead of a generic stand-in."
        ),
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Dry run against the deterministic mock provider (no network, no cost).",
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=0.0,
        help="Seconds to sleep between fills (per-minute rate limits).",
    )
    parser.add_argument(
        "--allow-unpriced",
        action="store_true",
        help=(
            "Run even when a leg has no complete price, accepting that its "
            "books will record an incomplete cost. Without this the run refuses "
            "to start, because a comparison that exists to price vendors and "
            "cannot price them has already failed (AL-348)."
        ),
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help=(
            "Force this completion cap on every leg, overriding the "
            "orchestrator's default. Reasoning legs spend most of a budget "
            "before writing anything, so a cap sized for prose alone returns "
            "empty content. Results at different caps are not comparable."
        ),
    )
    parser.add_argument(
        "--differentiation",
        type=Path,
        default=None,
        help=(
            "JSON array of per-brief differentiation specs, index-aligned with "
            "--briefs: null for an undirected fill, or an object with optional "
            "'level' (tree/leaf/catalog), 'axis' (a variation-axis key), "
            "'prior_titles' and 'prior_theme_tags'. Rendered through the "
            "production build_differentiation_directive, so the run measures "
            "the block production would send (AL-498). Omitting the flag "
            "fills undirected, exactly as every run before it existed."
        ),
    )
    parser.add_argument(
        "--out", required=True, type=Path, help="Directory for report.json and books/."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Dotenv file to source for the live legs (default: .env).",
    )
    return parser.parse_args(argv)


def _mock_vendors() -> list[Vendor]:
    """Return the three-label vendor set used by a ``--mock`` dry run.

    The labels are deliberately generic: a mock run measures the analysis path,
    not any real vendor, and naming real ones in its output would invite the
    numbers being quoted as a result.

    Returns:
        Three unpinned mock vendor legs.
    """
    return [
        Vendor(label=f"mock-{n}", model="mock", provider_order=())
        for n in ("a", "b", "c")
    ]


def _mirror_as_mock(vendors: list[Vendor]) -> list[Vendor]:
    """Rebuild a real vendor slate as mock legs of the same shape.

    A dry run that invents its own three legs cannot rehearse the grid the paid
    run will actually produce: it would not exercise the leg count, and, more
    importantly, it would not exercise ``family``, so a slate that accidentally
    split one lab into two families (or merged two labs into one) would look
    perfectly healthy right up until the money was spent. Passing ``--vendors``
    alongside ``--mock`` therefore keeps the declared labels and families and
    swaps only the provider.

    The label is prefixed so no line of the output can be mistaken for a real
    measurement of the vendor it names. That prefix is why ``family`` is written
    out explicitly rather than left to default: a leg that declared no family
    takes its lineage from its label, so renaming the label would quietly rename
    the lineage too, and the rehearsal would stop matching the paid run.

    Args:
        vendors: The loaded slate.

    Returns:
        One mock leg per input leg, preserving order, lineage, and relative
        labelling.
    """
    return [
        replace(
            v,
            label=f"mock:{v.label}",
            model="mock",
            provider_order=(),
            family=v.lineage(),
        )
        for v in vendors
    ]


async def preflight(
    vendors: Sequence[Vendor], settings: Settings
) -> list[tuple[str, str | None]]:
    """Send one tiny completion per leg to prove every pin is actually callable.

    Listing a model's endpoints proves what the *model* offers, not what this
    *account* may call: a workspace data policy can exclude a provider, and a
    pin at an excluded endpoint with ``allow_fallbacks: false`` fails every
    single book. Only a real completion down the same construction path
    exercises the same permission check, so that is what this does.

    The budget must clear the leg's reasoning overhead, not just its answer. A
    reasoning model spends hidden tokens before it emits any content, so a
    budget sized for the answer alone returns ``finish_reason='length'`` with an
    empty content string, which the provider reports as "no message content" and
    which reads exactly like a dead pin. Measured overhead on 2026-08-12:
    Gemini 3.1 Pro 183 tokens, Kimi K3 up to 197, GLM 5.2 98, against zero for
    the Anthropic legs. ``_PREFLIGHT_MAX_TOKENS`` sits well above the worst of
    those; it is still a rounding error against a run that generates whole books.

    Args:
        vendors: The slate about to be run.
        settings: Settings supplying the credential and base url.

    Returns:
        One ``(label, error)`` pair per leg, in slate order, where ``error`` is
        ``None`` for a reachable pin.
    """
    results: list[tuple[str, str | None]] = []
    for vendor in vendors:
        try:
            provider = _build_provider(vendor, settings, mock=False)
            _ = await provider.complete(
                system="Reply with one word.",
                prompt="ping",
                max_tokens=_PREFLIGHT_MAX_TOKENS,
            )
        except Exception as exc:
            # Deliberately broad: the point is to report every way a pin can be
            # unreachable (auth, policy, dead slug, transport) as one verdict
            # rather than to handle any of them.
            results.append((vendor.label, f"{type(exc).__name__}: {exc}"))
        else:
            results.append((vendor.label, None))
    return results


def unpopulable_fields(vendors: Sequence[Vendor]) -> list[str]:
    """Name the report fields this run could not fill in, before it spends money.

    Run-6 spent twenty book generations across five legs to compare quality
    **and cost**, and every one of the twenty carries ``cost: null``: the branch
    it executed from discarded per-call usage, so the field the run existed to
    populate was unpopulable before the first call was made (`AL-348`). Nothing
    checked, because nothing was looking.

    A missing price is the remaining way to reach that state now that metering
    is wired in, so that is what this checks.

    Args:
        vendors: The slate about to run.

    Returns:
        One line per structurally unpopulable field, empty when the run can
        fill in everything it reports.
    """
    unpriced = [
        v.label
        for v in vendors
        if (price := price_for("openrouter", v.model)) is None or not price.fully_priced
    ]
    if not unpriced:
        return []
    return [
        (
            f"cost: no complete price for {', '.join(unpriced)}. Every book "
            "from these legs would record an incomplete cost, which is the "
            "state run-6 shipped in (AL-348/UW-C245). Add them to "
            "core/pricing.py, or pass --allow-unpriced to run anyway and "
            "accept the gap."
        )
    ]


def _report_preflight(results: list[tuple[str, str | None]]) -> bool:
    """Print the pre-flight verdict and say whether the run may proceed.

    Args:
        results: Output of :func:`preflight`.

    Returns:
        ``True`` when every pin answered.
    """
    width = max([len("leg"), *(len(label) for label, _ in results)])
    print(
        f"Pre-flight: one {_PREFLIGHT_MAX_TOKENS}-token completion per pin.",
        file=sys.stderr,
    )
    for label, error in results:
        verdict = "reachable" if error is None else f"UNREACHABLE  {error[:150]}"
        print(f"  {label:<{width}}  {verdict}", file=sys.stderr)
    failed = [label for label, error in results if error is not None]
    if failed:
        print(
            f"Error: {len(failed)} of {len(results)} pins are unreachable "
            f"({', '.join(failed)}); nothing was generated. A 'No endpoints "
            "found' message usually means the account's data policy excludes "
            "that endpoint rather than that the slug is wrong; re-probe with "
            "provider.only to see the real reason. A 'no message content' "
            "message means the opposite: the pin routed, and the leg spent the "
            "whole budget on reasoning tokens before emitting anything, so "
            f"raise _PREFLIGHT_MAX_TOKENS above {_PREFLIGHT_MAX_TOKENS} rather "
            "than dropping the leg.",
            file=sys.stderr,
        )
    return not failed


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Argument vector, or ``None`` to read ``sys.argv``.

    Returns:
        Process exit code: 0 when at least one book was produced, 1 otherwise.
        This harness measures rather than gates, so a high shared-idiom rate is
        never itself a failure exit.
    """
    args = _parse_args(argv)
    skeleton_paths: list[Path] = [
        Path(str(p)).resolve()
        for p in args.skeletons  # pyright: ignore[reportAny]
    ]
    briefs_path: Path = Path(str(args.briefs)).resolve()  # pyright: ignore[reportAny]
    out_dir: Path = Path(str(args.out)).resolve()  # pyright: ignore[reportAny]
    env_path: Path = Path(str(args.env_file)).resolve()  # pyright: ignore[reportAny]
    throttle: float = float(args.throttle)  # pyright: ignore[reportAny]
    mock: bool = bool(args.mock)  # pyright: ignore[reportAny]
    max_tokens: int | None = (
        None
        if args.max_tokens is None  # pyright: ignore[reportAny]
        else int(args.max_tokens)  # pyright: ignore[reportAny]
    )

    briefs = _load_briefs(briefs_path)
    skeletons = _load_skeletons(skeleton_paths, len(briefs))
    differentiation_path: Path | None = (
        None
        if args.differentiation is None  # pyright: ignore[reportAny]
        else Path(str(args.differentiation)).resolve()  # pyright: ignore[reportAny]
    )
    directives = (
        None
        if differentiation_path is None
        else _load_differentiation(differentiation_path, len(briefs))
    )

    if mock:
        # A slate given alongside --mock is still loaded and validated, so the
        # dry run rehearses the real grid rather than a generic stand-in.
        vendors = (
            _mock_vendors()
            if args.vendors is None  # pyright: ignore[reportAny]
            else _mirror_as_mock(_load_vendors(Path(str(args.vendors)).resolve()))  # pyright: ignore[reportAny]
        )
        settings = Settings()
    else:
        if args.vendors is None:  # pyright: ignore[reportAny]
            print("Error: --vendors is required without --mock.", file=sys.stderr)
            return 1
        vendors = _load_vendors(Path(str(args.vendors)).resolve())  # pyright: ignore[reportAny]
        # Live legs read OPENROUTER_API_KEY from the environment; source the
        # gitignored dotenv so a local run picks the key up.
        _load_env_file(env_path)
        settings = Settings()
        # #EDGE: external resources: a pin proven reachable here can still be
        # withdrawn during the 40-to-80-minute run (a -preview slug retired, a
        # data policy edited, a provider outage), so a green pre-flight bounds
        # the loss to one book rather than guaranteeing the run.
        # #VERIFY: run_comparison prints each book's error inline, so a mid-run
        # withdrawal names itself at the book it first hits.
        # #CRITICAL: data integrity: a paid run must not start when a column it
        # exists to populate cannot be populated. Run-6 spent twenty
        # generations to compare cost and recorded `cost: null` twenty times
        # (AL-348), and nothing objected because nothing was asked to.
        # #VERIFY: test_compare_vendors.py drives an unpriced slate and asserts
        # both the refusal and the --allow-unpriced override.
        gaps = unpopulable_fields(vendors)
        if gaps and not args.allow_unpriced:  # pyright: ignore[reportAny]
            for line in gaps:
                print(f"Error: {line}", file=sys.stderr)
            return 1
        for line in gaps:
            print(f"WARNING: {line}", file=sys.stderr)
        if not _report_preflight(asyncio.run(preflight(vendors, settings))):
            return 1

    records = asyncio.run(
        run_comparison(
            skeletons,
            briefs,
            vendors,
            mock=mock,
            throttle=throttle,
            settings=settings,
            max_tokens=max_tokens,
            out_dir=out_dir,
            directives=directives,
        )
    )
    report = analyze(records)
    if mock:
        # The mock provider echoes one canned story for every call, so every
        # bucket saturates near 1000 per 1000 and the ratio is always ~1.00. The
        # computed verdict would read as a real "task-driven" finding, so it is
        # replaced rather than printed with a caveat next to it.
        report = replace(
            report,
            verdict=(
                "dry run: every leg was the mock provider, which returns one "
                "canned story per call. The saturated rates above prove the "
                "measurement path runs; they say nothing about any vendor."
            ),
        )
    distinct_skeletons = len({p.name for p in skeleton_paths})
    _print_report(
        report,
        structure_varies=distinct_skeletons > 1,
        # Any non-empty rendered directive makes this a directed run. An
        # all-null spec renders every entry as "", which is byte-identical to
        # passing no flag at all, so it must NOT read as directed.
        directed=bool(directives) and any(directives),
    )
    meta: dict[str, object] = {
        "skeletons": [p.name for p in skeleton_paths],
        # A within-vendor pair is only the 3.3 quantity ("sharing nothing but
        # the model and the age band") when structure varies across briefs.
        # Recording the flag beside the numbers keeps a later reader from
        # comparing a shared-structure figure against that floor.
        "structure_varies": distinct_skeletons > 1,
        "brief_count": len(briefs),
        # AL-498: a directed run and an undirected run measure different
        # quantities (the directed floor against the raw floor). The rendered
        # directives are recorded verbatim so the report says which one it is,
        # and what each fill was actually told.
        # An all-null spec renders every entry as "", which is exactly what
        # passing no flag does, so record None rather than a truthy list of
        # empty strings that a consumer's `if meta[...]` would read as directed.
        "differentiation_directives": (
            directives if directives and any(directives) else None
        ),
        "mock": mock,
        "vendors": [
            {
                "label": v.label,
                "model": v.model,
                "provider_order": list(v.provider_order),
                "family": v.lineage(),
            }
            for v in vendors
        ],
    }
    _write_outputs(out_dir, report, meta)
    print(f"Wrote {out_dir / 'report.json'}")
    return 0 if any(r.doc is not None for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
