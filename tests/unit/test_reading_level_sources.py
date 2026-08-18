"""Every per-band FK target must derive from one table, not restate it.

`UW-C281`. Four sites stated per-band Flesch-Kincaid targets and disagreed with
each other and with what the validator actually grades against:

===========================  =====  =====  ======  ======
site                          8-11  10-13   13-16     16+
===========================  =====  =====  ======  ======
brief.py / frontend / prompt   4.0    6.0     8.0    10.0
committed catalog (governs)    4.5    5.5     7.0     9.0
===========================  =====  =====  ======  ======

The prompt guide is spliced into every structure, prose and fill prompt and
called ITSELF "the FK-target source of record", so the generator was steered a
full grade off the window RL-13 measures on every single generation.

These tests assert the derivation rather than the values, so a future change to
`_READING_LEVEL_TARGET` propagates instead of drifting.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cyo_adventure.validator.band_profile import (
    _READING_LEVEL_TARGET,  # pyright: ignore[reportPrivateUsage]
    clamp_target_to_cap,
    reading_level_target_for,
)

_BANDS = ("3-5", "5-8", "8-11", "10-13", "13-16", "16+")
_INTAKE = Path("frontend/src/guardian/intakeApi.ts")
_PROMPT_GUIDE = Path("src/cyo_adventure/generation/templates/drafting_guide.md")


def test_reading_level_target_covers_every_band() -> None:
    """The source table configures every band the product offers."""
    assert set(_READING_LEVEL_TARGET) == set(_BANDS)
    for band in _BANDS:
        assert reading_level_target_for(band) is not None


def test_frontend_band_defaults_match_the_source_table() -> None:
    """The guardian intake UI's proposed defaults derive from the Python table.

    Parsed out of the TypeScript literal rather than duplicated here, so this
    fails when either side moves independently. The frontend cannot import the
    Python table, so a parse-and-compare test is what keeps them honest.
    """
    source = _INTAKE.read_text(encoding="utf-8")
    found = dict(re.findall(r"'([\d+\-]+)': \{[^}]*fkTarget: ([\d.]+)", source))

    assert set(found) == set(_BANDS), "intakeApi BAND_DEFAULTS lost or gained a band"
    for band in _BANDS:
        expected = reading_level_target_for(band)
        assert expected is not None
        assert float(found[band]) == pytest.approx(expected), (
            f"frontend fkTarget for {band} is {found[band]}, source table says {expected}"
        )


def test_injected_prompt_guide_matches_the_source_table() -> None:
    """The guide spliced into every prompt states the targets the gate grades.

    This is the one that mattered most: it is injected into structure, prose and
    fill prompts alike, so a wrong number here steers every generation rather
    than one surface.
    """
    text = _PROMPT_GUIDE.read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| ([\d+\-]+) \| ([\d.]+) \|", text, re.MULTILINE))

    assert set(rows) == set(_BANDS), "the injected FK table lost or gained a band"
    for band in _BANDS:
        expected = reading_level_target_for(band)
        assert expected is not None
        assert float(rows[band]) == pytest.approx(expected)


def test_a_cap_can_only_tighten_a_band_target() -> None:
    """`reading_level_cap` is a ceiling, in both directions.

    RL-13 reads a target as the CENTRE of a plus-or-minus window, so
    substituting a cap for the target admitted prose a full grade above the
    guardian's stated maximum, and a cap above the band target silently raised
    it. Clamping is correct in both directions and this pins both.
    """
    for band in _BANDS:
        target = reading_level_target_for(band)
        assert target is not None
        assert clamp_target_to_cap(target, target + 5.0) == pytest.approx(target)
        assert clamp_target_to_cap(target, 0.5) == pytest.approx(0.5)


def test_declared_catalog_targets_sit_inside_their_band_window() -> None:
    """Every committed skeleton's declared target is consistent with its band.

    A story's own `metadata.reading_level.target` governs RL-13, so the band
    table is a DEFAULT and not a constraint; asserting exact equality would make
    it one and would ban legitimate per-story variation. The 16+ catalog really
    does span 8.0 to 9.0, which is a drafting choice rather than drift.

    So this asserts the weaker, true property: a declared target sits inside its
    band's own advisory window. That still catches the failure mode that matters
    (a book declaring a target from a different band, which is how the four
    upstream tables parted company) while leaving authors their latitude.
    """
    import json

    tolerance = 1.0
    mismatches: list[str] = []
    for path in sorted(Path("skeletons").glob("*/*.json")):
        if path.name.endswith(".contract.json"):
            continue
        story = json.loads(path.read_text(encoding="utf-8"))
        metadata = story.get("metadata") or {}
        band = metadata.get("age_band")
        declared = (metadata.get("reading_level") or {}).get("target")
        expected = reading_level_target_for(str(band)) if band else None
        if expected is None or declared is None:
            continue
        if abs(float(declared) - expected) > tolerance:
            mismatches.append(
                f"{path.name}: {band} declares {declared}, band target {expected}"
            )

    assert not mismatches, (
        "declared targets are more than one grade from their band:\n"
        + "\n".join(mismatches)
    )
