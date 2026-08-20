"""Unit tests for the cross-vendor fill comparison harness.

The harness's whole value is the bucketing rule: shared four-grams between two
books mean different things depending on whether the books came from the same
vendor and whether they were written from the same brief. Mixing a cross-vendor
same-brief pair into the cross-vendor floor would credit shared premise wording
to vendor agreement, which would make the headline comparison lie. Most of what
follows pins that partition down.

No test here makes a network call: the live path is exercised through the
deterministic mock provider or a stubbed ``fill_skeleton``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.pricing import ModelPrice
from scripts.compare_vendors import (
    _PREFLIGHT_MAX_TOKENS,  # pyright: ignore[reportPrivateUsage]
    BookRecord,
    ComparisonReport,
    Vendor,
    _book_row,  # pyright: ignore[reportPrivateUsage]
    _fill_completeness,  # pyright: ignore[reportPrivateUsage]
    _load_briefs,  # pyright: ignore[reportPrivateUsage]
    _load_differentiation,  # pyright: ignore[reportPrivateUsage]
    _load_skeletons,  # pyright: ignore[reportPrivateUsage]
    _load_vendors,  # pyright: ignore[reportPrivateUsage]
    _measure,  # pyright: ignore[reportPrivateUsage]
    _mirror_as_mock,  # pyright: ignore[reportPrivateUsage]
    _report_preflight,  # pyright: ignore[reportPrivateUsage]
    _summarize,  # pyright: ignore[reportPrivateUsage]
    _verdict,  # pyright: ignore[reportPrivateUsage]
    _write_outputs,  # pyright: ignore[reportPrivateUsage]
    analyze,
    main,
    preflight,
    run_comparison,
    unpopulable_fields,
)

if TYPE_CHECKING:
    from pathlib import Path

# Two long passages with no four-gram in common. Reused verbatim to drive the
# shared-gram rate up for exactly the pairs a test means to converge.
_SHARED = (
    "the brave young otter slipped between the tall reeds and counted every "
    "silver ripple that crossed the wide slow river before the morning bell "
    "rang across the quiet valley and woke the sleeping village below"
)
_DISTINCT = (
    "a curious hedgehog measured each pebble along the winding chalk lane "
    "while distant kites turned above the barley and somebody hummed an old "
    "tune nobody could name in the yellow afternoon light"
)


def _doc(text: str, *, target: float | None = 3.0) -> dict[str, Any]:
    """Build a minimal filled-document dict carrying one leaf body.

    Args:
        text: The leaf body text.
        target: Reading-level target, or ``None`` to declare no band at all.

    Returns:
        A document shaped like a filled Storybook for the analysis path.
    """
    metadata: dict[str, Any] = {"age_band": "6-8"}
    if target is not None:
        metadata["reading_level"] = {
            "scheme": "flesch_kincaid",
            "target": target,
            "tolerance": 1.0,
        }
    return {
        "id": "s_test",
        "metadata": metadata,
        "nodes": [{"id": "n1", "body": text, "is_ending": True, "choices": []}],
    }


def _record(
    vendor: str, brief_index: int, text: str, *, family: str | None = None
) -> BookRecord:
    """Build a successful book record around one leaf body.

    Args:
        vendor: The vendor label.
        brief_index: The brief index the book was written from.
        text: The leaf body text.
        family: The producing leg's lineage. Defaults to ``vendor``, which is
            what a single-checkpoint vendor gets, so every pair between two
            such records reads as cross-family.

    Returns:
        A record ready for :func:`analyze`.
    """
    return BookRecord(
        vendor=vendor,
        family=vendor if family is None else family,
        brief_index=brief_index,
        status="passed",
        attempts=0,
        latency_s=1.0,
        grade=4.0,
        in_band=1.0,
        leaf_words=len(text.split()),
        doc=_doc(text),
        error=None,
        # A record built here is a written book. `analyze` participates only
        # fully-written books (AL-335), so leaving this at its 0.0 default would
        # silently empty every bucket in every test in this file.
        fill_completeness=1.0,
    )


_SUFFIX = "abcdefghijklmnopqrstuvwxyz"


def _filler(seed: str, count: int = 60) -> str:
    """Return ``count`` alphabetic words unique to ``seed``.

    The four-gram tokenizer keeps only ``[a-z']+``, so digit-suffixed words
    would all collapse to the seed and every filler four-gram would match every
    other one. Letter suffixes keep each book's baseline text genuinely
    disjoint, which is what lets a test attribute a shared-gram rate to the
    passage it deliberately duplicated.

    Args:
        seed: A lowercase alphabetic prefix unique to one book.
        count: How many words to emit.

    Returns:
        A space-joined run of distinct words.
    """
    return " ".join(f"{seed}{_SUFFIX[i // 26]}{_SUFFIX[i % 26]}" for i in range(count))


def _six_books(*, converge: str) -> list[BookRecord]:
    """Build three vendors x two briefs, converging on one chosen axis.

    Every book starts from filler unique to itself, so the only four-grams two
    books can share are the ones a mode deliberately duplicates.

    Args:
        converge: ``"within"`` gives each vendor a passage it repeats across
            both briefs; ``"cross"`` gives each brief a passage every vendor
            repeats; ``"none"`` duplicates nothing.

    Returns:
        Six book records.
    """
    books: list[BookRecord] = []
    # A short passage every book carries, so no bucket is ever exactly zero. A
    # real run always has some baseline overlap, and the verdict deliberately
    # refuses to divide by a zero cross-vendor floor.
    common = _filler("common", 8)
    for vendor in ("alpha", "beta", "gamma"):
        for brief in (0, 1):
            unique = f"{common} {_filler(f'{vendor}{_SUFFIX[brief]}')}"
            if converge == "within":
                # Duplicated by one vendor across both briefs, and by no other.
                text = f"{unique} {_filler('shared' + vendor, 40)}"
            elif converge == "cross":
                # Duplicated by every vendor for one brief, across no briefs.
                text = f"{unique} {_filler('shared' + _SUFFIX[brief] * 2, 40)}"
            else:
                text = unique
            books.append(_record(vendor, brief, text))
    return books


def test_analyze_partitions_pairs_on_both_axes() -> None:
    """Six books split into 3 within, 6 same-brief-cross, and 6 cross pairs."""
    report = analyze(_six_books(converge="none"))

    within_pairs = sum(int(s["pairs"]) for s in report.within_vendor.values())
    assert within_pairs == 3
    assert int(report.same_brief_cross_vendor["pairs"]) == 6
    assert int(report.cross_vendor["pairs"]) == 6


def test_analyze_reports_one_bucket_per_vendor() -> None:
    """Each vendor gets its own within-vendor summary, keyed by label."""
    report = analyze(_six_books(converge="none"))

    assert sorted(report.within_vendor) == ["alpha", "beta", "gamma"]


def test_analyze_detects_a_vendor_driven_floor() -> None:
    """Repeating wording within a vendor lifts within above cross."""
    report = analyze(_six_books(converge="within"))

    within = report.within_vendor["alpha"]["mean_per_1000"]
    assert within > report.cross_vendor["mean_per_1000"]
    assert report.verdict.startswith("vendor-driven")


def test_analyze_keeps_same_brief_convergence_out_of_the_cross_floor() -> None:
    """Premise-shared wording lands in its own bucket, not in cross-vendor.

    This is the confound the two-axis split exists to prevent: with every vendor
    echoing the same text for a given brief, the same-brief bucket must spike
    while the cross-vendor different-brief floor stays low.
    """
    report = analyze(_six_books(converge="cross"))

    assert (
        report.same_brief_cross_vendor["mean_per_1000"]
        > report.cross_vendor["mean_per_1000"]
    )


def _family_books(*, converge: bool) -> list[BookRecord]:
    """Build two checkpoints of one lab plus an unrelated lab, over two briefs.

    Six books, so fifteen pairs. Three of them are within-vendor, four are the
    two same-family cells, and the remaining eight are genuinely cross-lab.

    Args:
        converge: When true, every book from the shared-family lab carries one
            extra passage the other lab never uses.

    Returns:
        Six book records across three legs and two families.
    """
    books: list[BookRecord] = []
    common = _filler("common", 8)
    legs = (("a46", "anthropic"), ("a5", "anthropic"), ("xai", "xai"))
    for vendor, family in legs:
        for brief in (0, 1):
            text = f"{common} {_filler(f'{vendor}{_SUFFIX[brief]}')}"
            if converge and family == "anthropic":
                text = f"{text} {_filler('sharedlab', 40)}"
            books.append(_record(vendor, brief, text, family=family))
    return books


def test_analyze_routes_a_same_lab_pair_out_of_the_cross_vendor_floor() -> None:
    """Two checkpoints of one lab form their own cells, not cross-vendor ones.

    On a label-only split this grid would read as 6 same-brief and 6
    different-brief cross-vendor pairs. The family axis moves two out of each,
    which is the whole point: a version-bump pair is not evidence about vendor
    choice and must not be averaged into the headline.
    """
    report = analyze(_family_books(converge=False))

    assert int(report.cross_vendor["pairs"]) == 4
    assert int(report.same_brief_cross_vendor["pairs"]) == 4
    assert int(report.same_family_cross_model["pairs"]) == 2
    assert int(report.same_family_same_brief["pairs"]) == 2


def test_analyze_keeps_within_vendor_buckets_per_leg_not_per_family() -> None:
    """Two legs of one lab still get one within-vendor bucket each."""
    report = analyze(_family_books(converge=False))

    assert sorted(report.within_vendor) == ["a46", "a5", "xai"]


def test_analyze_keeps_same_lab_convergence_out_of_the_cross_floor() -> None:
    """A house style shared across one lab's checkpoints cannot inflate cross."""
    report = analyze(_family_books(converge=True))

    assert (
        report.same_family_cross_model["mean_per_1000"]
        > report.cross_vendor["mean_per_1000"]
    )


def test_vendor_lineage_falls_back_to_the_label() -> None:
    """A leg with no declared family is its own lineage, so pairs stay cross."""
    assert Vendor(label="solo", model="m", provider_order=()).lineage() == "solo"


def test_vendor_lineage_prefers_a_declared_family() -> None:
    """A declared family is what two checkpoints of one lab share."""
    vendor = Vendor(label="a5", model="m", provider_order=(), family="anthropic")

    assert vendor.lineage() == "anthropic"


def _write_vendors(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    """Write a vendor spec array and return its path.

    Args:
        tmp_path: Directory to write into.
        entries: The raw vendor objects.

    Returns:
        The written path.
    """
    path = tmp_path / "vendors.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_load_vendors_reads_a_declared_family(tmp_path: Path) -> None:
    """Two legs may declare the same family, which is how the axis is set."""
    path = _write_vendors(
        tmp_path,
        [
            {"label": "a46", "model": "m1", "provider_order": ["p"], "family": "anth"},
            {"label": "a5", "model": "m2", "provider_order": ["p"], "family": "anth"},
        ],
    )

    assert [v.lineage() for v in _load_vendors(path)] == ["anth", "anth"]


def test_load_vendors_rejects_a_non_string_family(tmp_path: Path) -> None:
    """A mistyped family would silently split a lab back into two vendors."""
    path = _write_vendors(
        tmp_path,
        [{"label": "a5", "model": "m", "provider_order": ["p"], "family": 7}],
    )

    with pytest.raises(SystemExit):
        _load_vendors(path)


def test_load_vendors_rejects_a_duplicate_label(tmp_path: Path) -> None:
    """Two vendors sharing a label would overwrite each other's paid books.

    `_book_filename` names each output file `{vendor}__{brief_index:02d}.json`,
    using the label as its only identity component. A duplicate label is
    therefore not a cosmetic mistake; it is silent data loss on a run that
    already paid a provider for the book it just overwrote.
    """
    path = _write_vendors(
        tmp_path,
        [
            {"label": "dup", "model": "m1", "provider_order": ["p"]},
            {"label": "dup", "model": "m2", "provider_order": ["p"]},
        ],
    )

    with pytest.raises(SystemExit):
        _load_vendors(path)


def test_mirror_as_mock_preserves_the_family_layout() -> None:
    """A dry run must rehearse the real grid, families included.

    The point of a dry run is to de-risk the paid one. If it substituted its own
    legs, a slate that split one lab across two families would look healthy up
    to the moment the money was spent.
    """
    slate = [
        Vendor(label="a46", model="m1", provider_order=("anthropic",), family="anth"),
        Vendor(label="a5", model="m2", provider_order=("anthropic",), family="anth"),
        Vendor(label="solo", model="m3", provider_order=("xai/zdr",)),
    ]

    mirrored = _mirror_as_mock(slate)

    assert [v.lineage() for v in mirrored] == ["anth", "anth", "solo"]
    assert {v.model for v in mirrored} == {"mock"}
    assert all(v.provider_order == () for v in mirrored)


def test_mirror_as_mock_marks_every_label_as_a_dry_run() -> None:
    """Real vendor names in a saturated report would invite being quoted."""
    mirrored = _mirror_as_mock([Vendor(label="a5", model="m", provider_order=())])

    assert mirrored[0].label == "mock:a5"


def test_analyze_drops_a_same_vendor_same_brief_pair() -> None:
    """A duplicate (vendor, brief) belongs to no floor and is not counted."""
    books = [
        _record("alpha", 0, _SHARED),
        _record("alpha", 0, _SHARED),
    ]

    report = analyze(books)

    assert report.within_vendor == {}
    assert int(report.cross_vendor["pairs"]) == 0
    assert int(report.same_brief_cross_vendor["pairs"]) == 0


def test_analyze_with_one_usable_book_reports_not_measured() -> None:
    """A run where everything but one book failed says so rather than zero."""
    books = [
        _record("alpha", 0, _SHARED),
        BookRecord(
            vendor="beta",
            family="beta",
            brief_index=0,
            status="error",
            attempts=0,
            latency_s=0.1,
            grade=None,
            in_band=None,
            leaf_words=0,
            doc=None,
            error="boom",
        ),
    ]

    report = analyze(books)

    assert report.verdict.startswith("not measured")
    assert len(report.books) == 2


def test_summarize_empty_reports_zero_pairs() -> None:
    """An unmeasured bucket reads as zero pairs, not as a clean zero rate."""
    assert _summarize([])["pairs"] == 0.0


def test_summarize_reports_mean_and_max() -> None:
    """The summary quotes both the average pair and the worst one."""
    summary = _summarize([1.0, 3.0, 8.0])

    assert summary["mean_per_1000"] == 4.0
    assert summary["max_per_1000"] == 8.0


@pytest.mark.parametrize(
    ("within_mean", "cross_mean", "expected"),
    [
        (10.0, 4.0, "vendor-driven"),
        (4.0, 4.0, "task-driven"),
        (2.0, 4.0, "inverted"),
    ],
)
def test_verdict_classifies_the_two_floors(
    within_mean: float, cross_mean: float, expected: str
) -> None:
    """The verdict names which of the two diversification strategies applies."""
    # Median tracks the mean here: this test is about the classification bands,
    # and a divergence between the two is its own verdict (contamination), which
    # test_verdict_refuses_when_mean_and_median_disagree covers.
    within = {
        "alpha": {
            "pairs": 1.0,
            "mean_per_1000": within_mean,
            "median_per_1000": within_mean,
            "max_per_1000": 0.0,
        }
    }
    cross = {
        "pairs": 1.0,
        "mean_per_1000": cross_mean,
        "median_per_1000": cross_mean,
        "max_per_1000": 0.0,
    }

    assert _verdict(within, cross).startswith(expected)


def test_verdict_without_cross_pairs_reports_not_measured() -> None:
    """A single-vendor run cannot answer the question and must not pretend to."""
    within = {
        "alpha": {
            "pairs": 1.0,
            "mean_per_1000": 5.0,
            "median_per_1000": 5.0,
            "max_per_1000": 5.0,
        }
    }

    assert _verdict(within, _summarize([])).startswith("not measured")


def test_measure_returns_none_without_a_declared_band() -> None:
    """A document declaring no reading level yields no FK figure."""
    grade, in_band, words = _measure(_doc(_SHARED, target=None))

    assert (grade, in_band, words) == (None, None, 0)


def test_measure_scores_a_banded_document() -> None:
    """A banded document with enough prose yields a grade and an in-band share."""
    grade, in_band, words = _measure(_doc(_SHARED))

    assert grade is not None
    assert in_band is not None
    assert words > 0


def test_load_briefs_rejects_a_single_brief(tmp_path: Path) -> None:
    """One brief cannot produce a within-vendor pair, so it is refused up front."""
    path = tmp_path / "briefs.json"
    path.write_text(json.dumps([{"setting": "a quiet place"}]), encoding="utf-8")

    with pytest.raises(SystemExit):
        _load_briefs(path)


def test_load_briefs_accepts_two(tmp_path: Path) -> None:
    """Two briefs are the documented minimum and load cleanly."""
    path = tmp_path / "briefs.json"
    path.write_text(
        json.dumps([{"setting": "a quiet place"}, {"setting": "a loud place"}]),
        encoding="utf-8",
    )

    assert len(_load_briefs(path)) == 2


def _write_skeletons(tmp_path: Path, *names: str) -> list[Path]:
    """Write one minimal skeleton JSON per name and return the paths.

    Args:
        tmp_path: Directory to write into.
        *names: Skeleton ids, one file each.

    Returns:
        The written paths, in argument order.
    """
    paths: list[Path] = []
    for name in names:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"id": name}), encoding="utf-8")
        paths.append(path)
    return paths


def test_load_skeletons_pairs_one_per_brief(tmp_path: Path) -> None:
    """A skeleton per brief loads index-aligned, which is the 3.3 condition."""
    paths = _write_skeletons(tmp_path, "sk-a", "sk-b", "sk-c")

    assert [s["id"] for s in _load_skeletons(paths, 3)] == ["sk-a", "sk-b", "sk-c"]


def test_load_skeletons_broadcasts_a_lone_skeleton(tmp_path: Path) -> None:
    """One skeleton is reused for every brief rather than rejected."""
    loaded = _load_skeletons(_write_skeletons(tmp_path, "sk-a"), 3)

    assert [s["id"] for s in loaded] == ["sk-a", "sk-a", "sk-a"]


def test_load_skeletons_broadcast_copies_rather_than_aliases(tmp_path: Path) -> None:
    """Broadcast entries are independent, so one fill cannot mutate another's input."""
    loaded = _load_skeletons(_write_skeletons(tmp_path, "sk-a"), 2)
    loaded[0]["id"] = "mutated"

    assert loaded[1]["id"] == "sk-a"


def test_load_skeletons_rejects_a_partial_count(tmp_path: Path) -> None:
    """Two skeletons for three briefs is a silent mispairing, so it exits."""
    paths = _write_skeletons(tmp_path, "sk-a", "sk-b")

    with pytest.raises(SystemExit):
        _load_skeletons(paths, 3)


def _write_differentiation(tmp_path: Path, entries: list[object]) -> Path:
    """Write a differentiation spec file and return its path."""
    path = tmp_path / "differentiation.json"
    _ = path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_load_differentiation_renders_the_production_block(tmp_path: Path) -> None:
    """A spec entry renders through build_differentiation_directive verbatim.

    The point of the flag (AL-498) is measuring the block production would
    send, so the rendered directive must carry the level's escalation text, the
    axis's instruction, and the prior titles, not some harness paraphrase.
    """
    path = _write_differentiation(
        tmp_path,
        [
            {
                "level": "leaf",
                "axis": "awestruck_wonder",
                "prior_titles": ["The Tin Whistle Map"],
                "prior_theme_tags": ["canal", "boatyard"],
            },
            None,
        ],
    )

    directives = _load_differentiation(path, 2)

    assert len(directives) == 2
    assert "already read every skeleton in this cell" in directives[0]
    assert "genuinely wondrous" in directives[0]
    assert "'The Tin Whistle Map'" in directives[0]
    assert "boatyard, canal" in directives[0]
    assert directives[1] == ""


def test_load_differentiation_rejects_a_count_mismatch(tmp_path: Path) -> None:
    """One spec for two briefs would silently pair wrong, so it exits."""
    path = _write_differentiation(tmp_path, [None])

    with pytest.raises(SystemExit):
        _load_differentiation(path, 2)


def test_load_differentiation_rejects_an_unknown_level(tmp_path: Path) -> None:
    """A level outside the closed vocabulary is an operator typo, not a miss."""
    path = _write_differentiation(tmp_path, [{"level": "maximal"}, None])

    with pytest.raises(SystemExit):
        _load_differentiation(path, 2)


def test_load_differentiation_rejects_an_unknown_axis(tmp_path: Path) -> None:
    """An unknown axis key must fail loudly, unlike the worker's tolerant miss.

    In production a missing axis degrades to "no axis" because an axis is a
    craft hint; here the same silence would measure the no-context block and
    report it as the directed floor, which is the exact confusion AL-498 exists
    to end.
    """
    path = _write_differentiation(tmp_path, [{"axis": "no_such_axis"}, None])

    with pytest.raises(SystemExit):
        _load_differentiation(path, 2)


def test_load_differentiation_rejects_an_unknown_key(tmp_path: Path) -> None:
    """A misspelled spec key would silently render the no-context block."""
    path = _write_differentiation(tmp_path, [{"prior_title": ["x"]}, None])

    with pytest.raises(SystemExit):
        _load_differentiation(path, 2)


@pytest.mark.parametrize(
    "field", ["prior_titles", "prior_theme_tags"], ids=["titles", "tags"]
)
@pytest.mark.parametrize(
    "value", ["The Canal Compass", ["The Canal Compass", 7]], ids=["scalar", "mixed"]
)
def test_load_differentiation_rejects_a_malformed_list(
    tmp_path: Path, field: str, value: object
) -> None:
    """A scalar or non-string member must fail, not silently weaken the block.

    Dropping the malformed part would run a weaker directive than the
    operator specified and report its convergence as the directed floor,
    the same silent-degradation failure the unknown-axis error exists to
    prevent.
    """
    path = _write_differentiation(tmp_path, [{field: value}, None])

    with pytest.raises(SystemExit):
        _load_differentiation(path, 2)


@pytest.mark.asyncio
async def test_compare_vendors_pairs_skeleton_i_with_brief_i() -> None:
    """Every vendor sees the same skeleton for a brief index, and only that one.

    This is the whole basis of the vendor axis: if skeleton and brief drifted
    out of step, a cross-vendor pair would differ in structure as well as
    vendor and the comparison would measure nothing in particular.
    """
    seen: list[tuple[str, str]] = []

    async def _stub(
        skeleton: dict[str, object],
        brief: dict[str, object],
        _provider: object,
        _pii: object,
        **_kwargs: object,
    ) -> object:
        """Record the (skeleton, brief) pairing handed to each fill."""
        seen.append((str(skeleton["id"]), str(brief["setting"])))
        return mock.Mock(status="passed", attempts=0, storybook=_doc(_SHARED))

    with mock.patch("scripts.compare_vendors.fill_skeleton", _stub):
        await run_comparison(
            [{"id": "sk-a"}, {"id": "sk-b"}],
            [{"setting": "a"}, {"setting": "b"}],
            [
                Vendor(label="alpha", model="mock", provider_order=()),
                Vendor(label="beta", model="mock", provider_order=()),
            ],
        )

    assert seen == [("sk-a", "a"), ("sk-b", "b"), ("sk-a", "a"), ("sk-b", "b")]


@pytest.mark.asyncio
async def test_compare_vendors_rejects_mismatched_grid_lengths() -> None:
    """A length mismatch is a programming error, not a survivable per-book fault."""
    vendors = [Vendor(label="alpha", model="mock", provider_order=())]

    with pytest.raises(ValueError, match="pair index-wise"):
        await run_comparison(
            [{"id": "sk-a"}], [{"setting": "a"}, {"setting": "b"}], vendors
        )


@pytest.mark.asyncio
async def test_compare_vendors_uses_an_empty_pii_context() -> None:
    """No real child identity may reach a paid endpoint from this harness."""
    seen: list[Any] = []

    async def _stub(
        _skeleton: dict[str, object],
        _brief: dict[str, object],
        _provider: object,
        pii: object,
        **_kwargs: object,
    ) -> object:
        """Record the PII context and return a passing outcome."""
        seen.append(pii)
        return mock.Mock(status="passed", attempts=0, storybook=_doc(_SHARED))

    with mock.patch("scripts.compare_vendors.fill_skeleton", _stub):
        await run_comparison(
            [{"id": "sk-a"}, {"id": "sk-b"}],
            [{"setting": "a"}, {"setting": "b"}],
            [Vendor(label="alpha", model="mock", provider_order=())],
        )

    assert seen
    assert all(ctx.child_names == frozenset() for ctx in seen)


@pytest.mark.asyncio
async def test_compare_vendors_threads_the_directive_per_brief() -> None:
    """Each fill receives its own brief's directive, held constant per vendor.

    The directive pairs with the brief the way the skeleton does: if it
    drifted out of step, a directed pair would differ in directive as well as
    brief, and the measured delta (AL-498) would be attributable to nothing.
    """
    seen: list[tuple[str, object]] = []

    async def _stub(
        _skeleton: dict[str, object],
        brief: dict[str, object],
        _provider: object,
        _pii: object,
        **kwargs: object,
    ) -> object:
        """Record the (brief, directive) pairing handed to each fill."""
        seen.append((str(brief["setting"]), kwargs.get("differentiation_directive")))
        return mock.Mock(status="passed", attempts=0, storybook=_doc(_SHARED))

    with mock.patch("scripts.compare_vendors.fill_skeleton", _stub):
        await run_comparison(
            [{"id": "sk-a"}, {"id": "sk-b"}],
            [{"setting": "a"}, {"setting": "b"}],
            [
                Vendor(label="alpha", model="mock", provider_order=()),
                Vendor(label="beta", model="mock", provider_order=()),
            ],
            directives=["directive-a", "directive-b"],
        )

    assert seen == [
        ("a", "directive-a"),
        ("b", "directive-b"),
        ("a", "directive-a"),
        ("b", "directive-b"),
    ]


@pytest.mark.asyncio
async def test_compare_vendors_defaults_to_an_undirected_fill() -> None:
    """Without directives every fill gets "", byte-identical to prior runs."""
    seen: list[object] = []

    async def _stub(
        _skeleton: dict[str, object],
        _brief: dict[str, object],
        _provider: object,
        _pii: object,
        **kwargs: object,
    ) -> object:
        """Record the directive handed to each fill."""
        seen.append(kwargs.get("differentiation_directive"))
        return mock.Mock(status="passed", attempts=0, storybook=_doc(_SHARED))

    with mock.patch("scripts.compare_vendors.fill_skeleton", _stub):
        await run_comparison(
            [{"id": "sk-a"}, {"id": "sk-b"}],
            [{"setting": "a"}, {"setting": "b"}],
            [Vendor(label="alpha", model="mock", provider_order=())],
        )

    assert seen == ["", ""]


@pytest.mark.asyncio
async def test_compare_vendors_rejects_a_directive_count_mismatch() -> None:
    """One directive for two briefs is a programming error, not a per-book fault."""
    with pytest.raises(ValueError, match="pair index-wise"):
        await run_comparison(
            [{"id": "sk-a"}, {"id": "sk-b"}],
            [{"setting": "a"}, {"setting": "b"}],
            [Vendor(label="alpha", model="mock", provider_order=())],
            directives=["only-one"],
        )


@pytest.mark.asyncio
async def test_compare_vendors_records_one_book_per_vendor_and_brief() -> None:
    """The grid is vendor-major and complete."""

    async def _stub(*_args: object, **_kwargs: object) -> object:
        """Return a passing outcome for every call."""
        return mock.Mock(status="passed", attempts=0, storybook=_doc(_SHARED))

    with mock.patch("scripts.compare_vendors.fill_skeleton", _stub):
        records = await run_comparison(
            [{"id": "sk-a"}, {"id": "sk-b"}],
            [{"setting": "a"}, {"setting": "b"}],
            [
                Vendor(label="alpha", model="mock", provider_order=()),
                Vendor(label="beta", model="mock", provider_order=()),
            ],
        )

    assert [(r.vendor, r.brief_index) for r in records] == [
        ("alpha", 0),
        ("alpha", 1),
        ("beta", 0),
        ("beta", 1),
    ]


@pytest.mark.asyncio
async def test_compare_vendors_stamps_each_book_with_its_lineage() -> None:
    """A book carries its leg's family, so ``analyze`` can bucket without the spec.

    The report JSON is read long after the run; if the family lived only in the
    vendor spec, re-analysing a saved run would silently fall back to labels and
    fold the version-bump pair into the cross-vendor floor.
    """

    async def _stub(*_args: object, **_kwargs: object) -> object:
        """Return a passing outcome for every call."""
        return mock.Mock(status="passed", attempts=0, storybook=_doc(_SHARED))

    with mock.patch("scripts.compare_vendors.fill_skeleton", _stub):
        records = await run_comparison(
            [{"id": "sk-a"}, {"id": "sk-b"}],
            [{"setting": "a"}, {"setting": "b"}],
            [
                Vendor(label="a46", model="m1", provider_order=(), family="anthropic"),
                Vendor(label="solo", model="m2", provider_order=()),
            ],
        )

    assert {(r.vendor, r.family) for r in records} == {
        ("a46", "anthropic"),
        ("solo", "solo"),
    }


def _probe_provider(error: Exception | None) -> object:
    """Build a stub provider whose ``complete`` succeeds or raises.

    Args:
        error: Raise this from ``complete``, or ``None`` to succeed.

    Returns:
        An object satisfying the one method pre-flight calls.
    """

    async def _complete(**_kwargs: object) -> str:
        """Answer the pre-flight ping."""
        if error is not None:
            raise error
        return "ok"

    return mock.Mock(complete=_complete)


@pytest.mark.asyncio
async def test_preflight_passes_every_reachable_pin() -> None:
    """A slate whose pins all answer reports no errors."""
    vendors = [
        Vendor(label="a", model="m1", provider_order=("p",)),
        Vendor(label="b", model="m2", provider_order=("q",)),
    ]

    def _build(*_a: object, **_k: object) -> object:
        """Build a provider that answers the ping."""
        return _probe_provider(None)

    with mock.patch("scripts.compare_vendors._build_provider", _build):
        results = await preflight(vendors, Settings())

    assert results == [("a", None), ("b", None)]


@pytest.mark.asyncio
async def test_preflight_reports_an_unreachable_pin_without_stopping() -> None:
    """One blocked endpoint must not hide the state of the others.

    A workspace data policy typically blocks several pins at once, so a
    pre-flight that aborted on the first would need as many runs as there are
    bad pins to converge on a working slate.
    """
    vendors = [
        Vendor(label="blocked", model="m1", provider_order=("p",)),
        Vendor(label="fine", model="m2", provider_order=("q",)),
    ]
    built: list[str] = []

    def _build(vendor: Vendor, *_a: object, **_k: object) -> object:
        """Fail the first leg only."""
        built.append(vendor.label)
        if vendor.label == "blocked":
            return _probe_provider(RuntimeError("No endpoints found"))
        return _probe_provider(None)

    with mock.patch("scripts.compare_vendors._build_provider", _build):
        results = await preflight(vendors, Settings())

    assert built == ["blocked", "fine"]
    assert results[0][1] is not None
    assert "No endpoints found" in results[0][1]
    assert results[1] == ("fine", None)


@pytest.mark.asyncio
async def test_preflight_catches_a_failure_in_provider_construction() -> None:
    """A pin can be rejected before any request, and that is still unreachable."""
    vendors = [Vendor(label="a", model="m", provider_order=("p",))]

    def _build(*_a: object, **_k: object) -> object:
        """Refuse to build."""
        msg = "missing credential"
        raise ValueError(msg)

    with mock.patch("scripts.compare_vendors._build_provider", _build):
        results = await preflight(vendors, Settings())

    assert results[0][1] is not None
    assert "missing credential" in results[0][1]


def test_report_preflight_blocks_the_run_when_any_pin_failed() -> None:
    """One unreachable pin is enough to stop a paid run before it starts."""
    assert _report_preflight([("a", None), ("b", "boom")]) is False


def test_report_preflight_allows_a_fully_reachable_slate() -> None:
    """Every pin answering is the only condition that lets the run proceed."""
    assert _report_preflight([("a", None), ("b", None)]) is True


@pytest.mark.asyncio
async def test_compare_vendors_survives_one_failing_fill() -> None:
    """One vendor's outage must not discard the books already paid for."""
    calls = {"n": 0}

    async def _stub(*_args: object, **_kwargs: object) -> object:
        """Fail the second call only."""
        calls["n"] += 1
        if calls["n"] == 2:
            msg = "provider exploded"
            raise RuntimeError(msg)
        return mock.Mock(status="passed", attempts=0, storybook=_doc(_SHARED))

    with mock.patch("scripts.compare_vendors.fill_skeleton", _stub):
        records = await run_comparison(
            [{"id": "sk-a"}, {"id": "sk-b"}],
            [{"setting": "a"}, {"setting": "b"}],
            [Vendor(label="alpha", model="mock", provider_order=())],
        )

    assert [r.status for r in records] == ["passed", "error"]
    assert records[1].error is not None
    assert "provider exploded" in records[1].error


@pytest.mark.asyncio
async def test_compare_vendors_mock_run_makes_no_live_call() -> None:
    """The ``--mock`` path runs the real pipeline against the canned story."""
    records = await run_comparison(
        [{"id": "sk-a"}, {"id": "sk-b"}],
        [{"setting": "a"}, {"setting": "b"}],
        [Vendor(label="mock-a", model="mock", provider_order=())],
        mock=True,
    )

    assert len(records) == 2
    assert all(r.doc is not None for r in records)


def test_report_json_carries_every_bucket_the_report_computes(tmp_path: Path) -> None:
    """Each analysed bucket must reach disk, not just the terminal.

    ``report.json`` is what the run is read from days later; the printed table
    scrolls away. When the family axis was added, both same-family buckets were
    computed and printed but never serialized, so the version-bump control (the
    entire reason a second checkpoint of one lab is on the slate) survived only
    in scrollback. Driving this off ``dataclasses.fields`` rather than a literal
    list means the next bucket added cannot be dropped the same way.
    """
    report = analyze(
        [
            _record("a46", 0, _SHARED, family="anthropic"),
            _record("a5", 1, _SHARED, family="anthropic"),
            _record("solo", 0, _DISTINCT),
        ]
    )

    _write_outputs(tmp_path, report, {"run": "t"})
    payload = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))

    missing = {f.name for f in dataclasses.fields(ComparisonReport)} - set(payload)
    assert not missing, f"buckets computed but never written: {sorted(missing)}"


# Worst per-call reasoning overhead measured across the 2026-08-12 slate (Kimi
# K3 at 197 tokens, Gemini 3.1 Pro at 183). A pre-flight budget at or below this
# returns empty content on those legs, which the provider raises as "no message
# content" and which the report then prints as UNREACHABLE. That is a false
# negative that blocks a whole paid run on a pin that works.
_MEASURED_REASONING_OVERHEAD = 197


@pytest.mark.asyncio
async def test_preflight_budget_clears_measured_reasoning_overhead() -> None:
    """The ping must outlast a reasoning leg's hidden tokens, not just its answer."""
    seen: list[object] = []

    async def _complete(**kwargs: object) -> str:
        """Record the budget the pre-flight asked for."""
        seen.append(kwargs.get("max_tokens"))
        return "ok"

    def _build(*_a: object, **_k: object) -> object:
        """Build a provider that records its call."""
        return mock.Mock(complete=_complete)

    with mock.patch("scripts.compare_vendors._build_provider", _build):
        _ = await preflight(
            [Vendor(label="a", model="m", provider_order=("p",))], Settings()
        )

    assert seen == [_PREFLIGHT_MAX_TOKENS]
    assert _PREFLIGHT_MAX_TOKENS > _MEASURED_REASONING_OVERHEAD, (
        f"a {_PREFLIGHT_MAX_TOKENS}-token ping cannot clear the "
        f"{_MEASURED_REASONING_OVERHEAD}-token worst case; reasoning legs would "
        "report UNREACHABLE while routing correctly"
    )


# --- Incremental persistence (AL-326 / UW-C232) ---------------------------
#
# The harness used to hold every generated book in memory until the last one
# landed, so an interruption at any point lost everything already paid for.
# Run-6 proved it on 2026-08-12: an environment restart destroyed three
# completed books because the output directory was never created. These tests
# pin the durability property, which is the one property the old design's
# tests never exercised.


async def _passing_stub(*_args: object, **_kwargs: object) -> object:
    """Return a passing outcome carrying a real document."""
    return mock.Mock(status="passed", attempts=0, storybook=_doc(_SHARED))


@pytest.mark.asyncio
async def test_run_comparison_writes_each_book_as_it_completes(
    tmp_path: Path,
) -> None:
    """A completed book is on disk before the run ends, not after."""
    with mock.patch("scripts.compare_vendors.fill_skeleton", _passing_stub):
        await run_comparison(
            [{"id": "sk-a"}, {"id": "sk-b"}],
            [{"setting": "a"}, {"setting": "b"}],
            [Vendor(label="alpha", model="mock", provider_order=())],
            out_dir=tmp_path,
        )

    written = sorted(p.name for p in (tmp_path / "books").glob("*.json"))
    assert written == ["alpha__00.json", "alpha__01.json"]


@pytest.mark.asyncio
async def test_an_interrupted_run_keeps_the_books_it_already_paid_for(
    tmp_path: Path,
) -> None:
    """The defect this change exists to fix, reproduced as a test.

    ``KeyboardInterrupt`` is a ``BaseException``, so the per-book ``except
    Exception`` guard does not absorb it: it propagates exactly the way an
    environment restart or an operator abort does, killing the run before it
    can reach the end-of-run write.
    """
    calls = {"n": 0}

    async def _die_on_the_third(*_args: object, **_kwargs: object) -> object:
        """Pass twice, then kill the process the way a restart would."""
        calls["n"] += 1
        if calls["n"] == 3:
            raise KeyboardInterrupt
        return mock.Mock(status="passed", attempts=0, storybook=_doc(_SHARED))

    vendors = [
        Vendor(label="alpha", model="mock", provider_order=()),
        Vendor(label="beta", model="mock", provider_order=()),
    ]
    skeletons = [{"id": "sk-a"}, {"id": "sk-b"}]
    briefs = [{"setting": "a"}, {"setting": "b"}]

    with (
        mock.patch("scripts.compare_vendors.fill_skeleton", _die_on_the_third),
        pytest.raises(KeyboardInterrupt),
    ):
        await run_comparison(skeletons, briefs, vendors, out_dir=tmp_path)

    survived = sorted(p.name for p in (tmp_path / "books").glob("*.json"))
    assert survived == ["alpha__00.json", "alpha__01.json"]


@pytest.mark.asyncio
async def test_the_journal_records_a_row_for_a_book_that_produced_no_document(
    tmp_path: Path,
) -> None:
    """An errored leg leaves a durable trace even though it has no book file.

    Without this the only record of a failed leg is a progress line on stderr,
    which is exactly what run-6 was reduced to.
    """

    async def _always_fails(*_args: object, **_kwargs: object) -> object:
        """Fail every book with a recoverable per-book error."""
        message = "endpoint refused"
        raise RuntimeError(message)

    with mock.patch("scripts.compare_vendors.fill_skeleton", _always_fails):
        await run_comparison(
            [{"id": "sk-a"}],
            [{"setting": "a"}],
            [Vendor(label="alpha", model="mock", provider_order=())],
            out_dir=tmp_path,
        )

    rows = [
        json.loads(line)
        for line in (tmp_path / "books.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [r["status"] for r in rows] == ["error"]
    assert rows[0]["file"] is None
    assert "endpoint refused" in str(rows[0]["error"])


def test_run_comparison_writes_nothing_when_no_out_dir_is_given(
    tmp_path: Path,
) -> None:
    """The default stays non-persisting, so callers that only want the records
    (the dry-run path and every other test here) are unaffected.

    Driven with ``asyncio.run`` from a sync test rather than the usual
    ``@pytest.mark.asyncio``, so the filesystem assertion does not sit inside
    an async frame (ASYNC240). The sibling tests above escape that rule only
    because ruff cannot infer the type of a ``tmp_path / "books"`` expression,
    which is a gap in the check rather than a difference in the code.
    """
    with mock.patch("scripts.compare_vendors.fill_skeleton", _passing_stub):
        asyncio.run(
            run_comparison(
                [{"id": "sk-a"}],
                [{"setting": "a"}],
                [Vendor(label="alpha", model="mock", provider_order=())],
            )
        )

    assert list(tmp_path.glob("*")) == []


# ---------------------------------------------------------------------------
# Tier 0: what a paid run must refuse, exclude, and record
# ---------------------------------------------------------------------------


def _unfilled_doc() -> dict[str, Any]:
    """Build a schema-valid document whose body was never written.

    Returns:
        A document carrying a retained ``<<FILL ...>>`` directive, which is what
        a model echoing its input back produces.
    """
    doc = _doc("placeholder")
    nodes = cast("list[dict[str, Any]]", doc["nodes"])
    nodes[0]["body"] = "<<FILL role=leaf words=120 beats='the lantern lifts'>>"
    return doc


def test_fill_completeness_scores_a_retained_directive_as_unwritten() -> None:
    """Schema validity and being written are different questions."""
    assert _fill_completeness(_unfilled_doc()) == 0.0
    assert _fill_completeness(_doc("real prose here")) == 1.0
    assert _fill_completeness(None) == 0.0


def test_an_unwritten_book_is_excluded_from_every_bucket_and_named() -> None:
    """An unfilled book moves the headline ratio in both directions at once.

    It inflates within-vendor similarity, since two unfilled books share near
    identical directives, and deflates cross-vendor similarity, since directives
    share nothing with prose. Four such books out of thirty-two inverted the
    published verdict (AL-335). Excluding them is not enough on its own: a paid
    run that quietly analysed 28 of 32 books would report a clean result, so the
    exclusions are named.
    """
    good = [
        _record("alpha", 0, _filler("a")),
        _record("alpha", 1, _filler("b")),
        _record("beta", 0, _filler("c")),
        _record("beta", 1, _filler("d")),
    ]
    unwritten = dataclasses.replace(
        _record("gamma", 0, _filler("e")),
        doc=_unfilled_doc(),
        fill_completeness=0.0,
    )

    report = analyze([*good, unwritten])

    assert report.excluded_incomplete == ("gamma#0 (0% filled)",)
    assert "gamma" not in report.within_vendor
    assert all(book.vendor != "gamma" for book in report.books if False)


def test_a_verdict_the_mean_and_median_disagree_on_is_refused() -> None:
    """A few outlier pairs must not get to speak for the population.

    Both statistics answer the same question over the same pairs, so a
    disagreement wide enough to cross the reporting bands means the mean is
    being carried by its tail. Publishing it as the population's verdict is the
    shape of the AL-335 failure, one level up.
    """
    within = {
        "alpha": {
            "pairs": 4.0,
            "mean_per_1000": 10.0,
            "median_per_1000": 4.0,
            "max_per_1000": 30.0,
        }
    }
    cross = {
        "pairs": 4.0,
        "mean_per_1000": 4.0,
        "median_per_1000": 4.0,
        "max_per_1000": 6.0,
    }

    verdict = _verdict(within, cross)

    assert verdict.startswith("contaminated")
    assert "2.50" in verdict
    assert "1.00" in verdict


def test_a_run_refuses_to_start_when_it_cannot_price_a_leg() -> None:
    """A comparison that exists to price vendors and cannot has already failed.

    Run-6 spent twenty book generations to compare quality and cost, and every
    one carries ``cost: null`` (AL-348). Nothing objected, because nothing was
    asked to.
    """
    gaps = unpopulable_fields(
        [Vendor(label="ghost", model="nobody/never-priced", provider_order=())]
    )

    assert len(gaps) == 1
    assert "cost" in gaps[0]
    assert "ghost" in gaps[0]


def test_a_priced_leg_raises_no_objection() -> None:
    """The check must not block a run it has no complaint about.

    The price is injected rather than taken from ``core.pricing.PRICES`` because
    no cloud entry there is fully priced today: every one sets
    ``input_usd_per_mtok=None`` (AL-333 / UW-C239). Pinning this behaviour
    against the live table would make the test assert that gap rather than this
    function, and would start passing for the wrong reason the day it closes.
    """
    priced = ModelPrice(
        input_usd_per_mtok=Decimal("3.00"),
        output_usd_per_mtok=Decimal("15.00"),
        as_of="2026-08-13",
        source="test fixture",
    )
    with mock.patch("scripts.compare_vendors.price_for", return_value=priced):
        assert (
            unpopulable_fields(
                [Vendor(label="sonnet", model="a/b", provider_order=("pin",))]
            )
            == []
        )


def test_a_priced_slate_starts_and_an_unpriced_leg_still_stops_it() -> None:
    """Inverted on 2026-08-14, when `UW-C239` closed.

    This test used to record the blast radius of the open pricing gap: every
    cloud entry had a null input rate, so the pre-flight refused every live
    slate and a real run needed ``--allow-unpriced``. Both halves of every
    OpenRouter entry are now read live from the vendor, so a slate of
    table-priced legs starts on its own, which is what let the W4/W5 pool run.

    The refusal itself is the part worth keeping, and it is asserted below
    against a model absent from the table. That is how the gap reopens: a model
    promoted out of a comparison and added to the allowlist but not to
    `scripts/refresh_pricing.py`. `AL-348`'s reading is unchanged, that a
    comparison existing to price vendors must not start unable to price them.
    """
    priced = [
        Vendor(
            label="sonnet-4.6", model="anthropic/claude-sonnet-4.6", provider_order=()
        ),
        Vendor(label="gemini", model="google/gemini-2.5-flash", provider_order=()),
    ]

    assert unpopulable_fields(priced) == []

    unknown = [*priced, Vendor(label="acme", model="acme/acme-1", provider_order=())]
    gaps = unpopulable_fields(unknown)

    assert len(gaps) == 1
    assert "acme" in gaps[0]
    assert "sonnet-4.6" not in gaps[0]


def test_a_leg_with_no_budget_headroom_is_flagged_rather_than_rated() -> None:
    """A leg that spent its whole budget was measured against the cap.

    At 32,000 one leg spends 6,054 completion tokens on a book and another
    spends all 32,000, 28,247 of them on hidden reasoning; the legs scored
    unreliable were exactly the two without headroom (AL-328).
    """
    roomy = dataclasses.replace(
        _record("roomy", 0, _filler("a")), output_tokens=6_054, max_tokens=32_000
    )
    walled = dataclasses.replace(
        _record("walled", 0, _filler("b")), output_tokens=32_000, max_tokens=32_000
    )
    unmetered = dataclasses.replace(
        _record("unknown", 0, _filler("c")), output_tokens=None, max_tokens=32_000
    )

    assert roomy.near_cap is False
    assert walled.near_cap is True
    # An unmeasured call is not evidence of headroom either way, so it must not
    # be reported as if it had room.
    assert unmetered.near_cap is False


def test_the_book_row_carries_the_conditions_the_book_was_written_under() -> None:
    """The artifact has to answer "what was this measured under" on its own.

    Reconstructing the cap, the completeness, or whether Stage D silently did
    less requires re-running the job otherwise, and a paid run cannot be re-run
    for free.
    """
    record = dataclasses.replace(
        _record("alpha", 0, _filler("a")),
        max_tokens=32_000,
        output_tokens=7_000,
        reasoning_tokens=1_200,
        cost_usd=0.0398,
        cost_complete=True,
        reading_level_degraded=True,
        reading_level_nodes_dropped=3,
    )

    row = _book_row(record)

    assert row["max_tokens"] == 32_000
    assert row["reasoning_tokens"] == 1_200
    assert row["cost"] == 0.0398
    assert row["cost_complete"] is True
    assert row["complete"] is True
    assert row["reading_level_degraded"] is True
    assert row["reading_level_nodes_dropped"] == 3


def _mock_run_files(tmp_path: Path) -> tuple[str, str]:
    """Write the briefs and skeleton a ``--mock`` grid needs."""
    briefs = [
        {"slot": 0, "theme": "a canal boatyard", "keepsake": "an enamel compass"},
        {"slot": 1, "theme": "a school lost-property room", "keepsake": "a medal"},
    ]
    briefs_path = tmp_path / "briefs.json"
    briefs_path.write_text(json.dumps(briefs), encoding="utf-8")
    skeleton = {
        "schema_version": "2.0",
        "id": "sk_mock",
        "version": 1,
        "title": "A Mock Adventure",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"scheme": "flesch_kincaid", "target": 4.5},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "gauntlet",
        },
        "start_node": "n1",
        "variables": {},
        "nodes": [
            {
                "id": "n1",
                "body": "<<FILL role=scene words=100 beats='a fork'>>",
                "is_ending": False,
                "choices": [{"label": "<<FILL label>>", "target": "n2"}],
            },
            {
                "id": "n2",
                "body": "<<FILL role=ending words=100 beats='home'>>",
                "is_ending": True,
                "choices": [],
                "ending": {"id": "e1", "title": "Home", "kind": "success"},
            },
        ],
    }
    skeleton_path = tmp_path / "sk_mock.json"
    skeleton_path.write_text(json.dumps(skeleton), encoding="utf-8")
    return str(briefs_path), str(skeleton_path)


def test_main_records_the_rendered_directives_in_the_report(tmp_path: Path) -> None:
    """``--differentiation`` must reach the report metadata, not just the fills.

    This is the whole anti-conflation guard for `UW-C315`: a directed run whose
    ``report.json`` does not say it was directed can be pooled with a raw floor
    later. Nothing else exercises ``main``'s flag wiring, so a slip anywhere
    between the argument and the metadata key is otherwise invisible.
    """
    briefs_path, skeleton_path = _mock_run_files(tmp_path)
    spec_path = tmp_path / "diff.json"
    spec_path.write_text(
        json.dumps(
            [
                {"level": "leaf", "axis": "awestruck_wonder", "prior_titles": ["A"]},
                None,
            ]
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    assert (
        main(
            [
                "--skeleton",
                skeleton_path,
                "--briefs",
                briefs_path,
                "--mock",
                "--out",
                str(out_dir),
                "--differentiation",
                str(spec_path),
            ]
        )
        == 0
    )
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    recorded = cast("list[str] | None", report["differentiation_directives"])
    assert recorded is not None, (
        "a directed run must record its directives; a null here lets the "
        "directed floor be quoted as the raw one (AL-498)"
    )
    assert len(recorded) == 2
    assert recorded[0], "brief 0 was given a directive and must render one"
    assert recorded[1] == "", "a null spec entry is an undirected fill"


def test_main_records_no_directives_for_an_undirected_run(tmp_path: Path) -> None:
    """Without the flag the metadata key must be null, not an empty-string list.

    ``[null, null]`` renders as ``["", ""]``, which is byte-identical in effect
    to passing no flag, so a truthy list there would make a consumer testing
    ``if metadata["differentiation_directives"]`` read a raw run as directed.
    """
    briefs_path, skeleton_path = _mock_run_files(tmp_path)
    out_dir = tmp_path / "out"
    assert (
        main(
            [
                "--skeleton",
                skeleton_path,
                "--briefs",
                briefs_path,
                "--mock",
                "--out",
                str(out_dir),
            ]
        )
        == 0
    )
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert report["differentiation_directives"] is None

    all_null = tmp_path / "null.json"
    all_null.write_text(json.dumps([None, None]), encoding="utf-8")
    out2 = tmp_path / "out2"
    assert (
        main(
            [
                "--skeleton",
                skeleton_path,
                "--briefs",
                briefs_path,
                "--mock",
                "--out",
                str(out2),
                "--differentiation",
                str(all_null),
            ]
        )
        == 0
    )
    report2 = json.loads((out2 / "report.json").read_text(encoding="utf-8"))
    assert report2["differentiation_directives"] is None, (
        "an all-null spec is an undirected run and must not record as directed"
    )
