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

import json
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from scripts.compare_vendors import (
    BookRecord,
    Vendor,
    _load_briefs,  # pyright: ignore[reportPrivateUsage]
    _load_skeletons,  # pyright: ignore[reportPrivateUsage]
    _measure,  # pyright: ignore[reportPrivateUsage]
    _summarize,  # pyright: ignore[reportPrivateUsage]
    _verdict,  # pyright: ignore[reportPrivateUsage]
    analyze,
    run_comparison,
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


def _record(vendor: str, brief_index: int, text: str) -> BookRecord:
    """Build a successful book record around one leaf body.

    Args:
        vendor: The vendor label.
        brief_index: The brief index the book was written from.
        text: The leaf body text.

    Returns:
        A record ready for :func:`analyze`.
    """
    return BookRecord(
        vendor=vendor,
        brief_index=brief_index,
        status="passed",
        attempts=0,
        latency_s=1.0,
        grade=4.0,
        in_band=1.0,
        leaf_words=len(text.split()),
        doc=_doc(text),
        error=None,
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
    within = {
        "alpha": {"pairs": 1.0, "mean_per_1000": within_mean, "max_per_1000": 0.0}
    }
    cross = {"pairs": 1.0, "mean_per_1000": cross_mean, "max_per_1000": 0.0}

    assert _verdict(within, cross).startswith(expected)


def test_verdict_without_cross_pairs_reports_not_measured() -> None:
    """A single-vendor run cannot answer the question and must not pretend to."""
    within = {"alpha": {"pairs": 1.0, "mean_per_1000": 5.0, "max_per_1000": 5.0}}

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
