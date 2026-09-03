"""Unit tests for the admin-view noise-floor helper (WS-A admin noise-floor addendum).

``admin_surfaces`` denoises the ADMIN review view only: it hides a low-scored
ADVISORY finding below the configured floor, but never hides a FLAG or BLOCK
finding (including a bright-line BLOCK carrying score ``0.0``), and never
hides an unscored finding of any verdict.
"""

from __future__ import annotations

import pytest

from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.thresholds import (
    ADMIN_NOISE_FLOOR_DEFAULT,
    ADMIN_NOISE_FLOOR_KEY,
    Threshold,
    ThresholdPolicy,
    admin_noise_floor_for,
    admin_surfaces,
)

pytestmark = pytest.mark.unit

_FLOOR = 0.05


def test_admin_noise_floor_default_is_point_zero_five() -> None:
    """Lock the code default so it cannot drift silently from the seed row."""
    # NOSONAR-adjacent tool conflict: ruff's SIM300 (no Yoda conditions) wants
    # the literal-first form, but that is exactly what SonarCloud python:S3415
    # flags (assert actual, expected order). S3415 is the semantic-correctness
    # rule (a swapped pytest.approx(...) == actual reads misleadingly on
    # failure), so it wins; noqa is scoped to this one line only.
    assert ADMIN_NOISE_FLOOR_DEFAULT == pytest.approx(0.05)  # noqa: SIM300


def test_admin_noise_floor_key_matches_migration_seed() -> None:
    """Lock the setting key to the frozen migration literal.

    The seed INSERT in migrations/versions/20260707_1700_add_moderation_setting.py
    hand-copies this key (migrations must not import live app constants); a
    rename of either side without the other would silently orphan the seed row.
    """
    assert ADMIN_NOISE_FLOOR_KEY == "admin_noise_floor"


def test_block_at_zero_score_surfaces() -> None:
    """A bright-line BLOCK carrying score 0.0 always surfaces."""
    assert admin_surfaces(Verdict.BLOCK, 0.0, noise_floor=_FLOOR)


def test_flag_at_zero_score_surfaces() -> None:
    """A FLAG carrying score 0.0 always surfaces."""
    assert admin_surfaces(Verdict.FLAG, 0.0, noise_floor=_FLOOR)


def test_advisory_below_floor_is_hidden() -> None:
    """An ADVISORY scored under the floor is denoised away."""
    assert not admin_surfaces(Verdict.ADVISORY, 0.02, noise_floor=_FLOOR)


def test_advisory_above_floor_surfaces() -> None:
    """An ADVISORY scored at or above the floor surfaces."""
    assert admin_surfaces(Verdict.ADVISORY, 0.08, noise_floor=_FLOOR)


def test_advisory_unscored_surfaces() -> None:
    """An unscored ADVISORY always surfaces; there is no score to denoise on."""
    assert admin_surfaces(Verdict.ADVISORY, None, noise_floor=_FLOOR)


def test_pass_never_surfaces() -> None:
    """A PASS verdict never surfaces on the admin view either."""
    assert not admin_surfaces(Verdict.PASS, None, noise_floor=_FLOOR)


def test_unknown_string_verdict_does_not_surface() -> None:
    """A malformed stored verdict degrades to hidden, not a crash."""
    assert not admin_surfaces("banana", None, noise_floor=_FLOOR)


def test_string_verdict_is_coerced() -> None:
    """Callers holding serialized verdict strings get the same behavior."""
    assert admin_surfaces("flag", 0.0, noise_floor=_FLOOR)


def test_advisory_score_exactly_at_floor_surfaces() -> None:
    """The floor comparison is strict-less-than: a score equal to the floor surfaces."""
    assert admin_surfaces(Verdict.ADVISORY, 0.05, noise_floor=_FLOOR)


def test_noise_floor_zero_surfaces_all_scored_advisory() -> None:
    """A 0.0 floor denoises nothing: every scored ADVISORY surfaces."""
    assert admin_surfaces(Verdict.ADVISORY, 0.0, noise_floor=0.0)
    assert admin_surfaces(Verdict.ADVISORY, 0.5, noise_floor=0.0)


def test_noise_floor_one_hides_all_scored_advisory_but_not_others() -> None:
    """A 1.0 floor hides every scored ADVISORY, but never FLAG/BLOCK/unscored."""
    assert not admin_surfaces(Verdict.ADVISORY, 0.99, noise_floor=1.0)
    assert not admin_surfaces(Verdict.ADVISORY, 0.0, noise_floor=1.0)
    assert admin_surfaces(Verdict.ADVISORY, None, noise_floor=1.0)
    assert admin_surfaces(Verdict.FLAG, 0.0, noise_floor=1.0)
    assert admin_surfaces(Verdict.BLOCK, 0.0, noise_floor=1.0)


# ---------------------------------------------------------------------------
# `RS-B3`: band-aware resolution of the admin floor.
#
# admin_noise_floor_for supplies the NUMBER; admin_surfaces (above) keeps the
# never-hide guarantees. These tests pin the absence semantics, because every
# arm that resolves HIGHER than intended hides an advisory from the human who
# is the final gate under ADR-005.
# ---------------------------------------------------------------------------

_BAND = "10-13"


def _policy_with(
    *pairs: tuple[str, str, float | None],
) -> ThresholdPolicy:
    """Build a policy whose rows carry only ``min_score`` variation.

    ``min_verdict`` is fixed at FLAG on every row, which is both the table's
    real default and the value that would hide every advisory if the admin
    lane ever routed through ``ThresholdPolicy.surfaces``. Fixing it here is
    what makes ``test_min_verdict_is_never_consulted`` meaningful.
    """
    return ThresholdPolicy(
        rows={
            (band, category): Threshold(min_verdict=Verdict.FLAG, min_score=min_score)
            for band, category, min_score in pairs
        }
    )


def test_flat_floor_none_wins_over_a_band_row() -> None:
    """A None flat floor disables floor filtering absolutely.

    The flat floor is the emergency kill switch (a guardian caller, or an
    operator who set the floor to None). A seeded band row must not resurrect
    filtering behind that switch, so the None arm returns before the policy is
    consulted at all.
    """
    policy = _policy_with((_BAND, "violence", 0.9))
    assert (
        admin_noise_floor_for(
            "violence", age_band=_BAND, policy=policy, flat_floor=None
        )
        is None
    )


def test_a_row_without_a_min_score_falls_back_to_the_flat_floor() -> None:
    """A row is not automatically a score override.

    ``moderation_threshold`` rows exist to carry ``min_verdict`` as well, so a
    row whose ``min_score`` is NULL says nothing about the score floor. Reading
    that NULL as 0.0 would silently disable the flat floor for that pair, and
    reading it as "no floor" would disable filtering entirely.
    """
    policy = _policy_with((_BAND, "violence", None))
    assert admin_noise_floor_for(
        "violence", age_band=_BAND, policy=policy, flat_floor=0.05
    ) == pytest.approx(0.05)


def test_a_band_row_overrides_the_flat_floor_for_its_own_pair_only() -> None:
    """Denoising is scoped to the (band, category) pair that was seeded."""
    policy = _policy_with((_BAND, "violence", 0.5))
    assert admin_noise_floor_for(
        "violence", age_band=_BAND, policy=policy, flat_floor=0.05
    ) == pytest.approx(0.5)
    # Same category, different band.
    assert admin_noise_floor_for(
        "violence", age_band="3-5", policy=policy, flat_floor=0.05
    ) == pytest.approx(0.05)
    # Same band, different category.
    assert admin_noise_floor_for(
        "harassment", age_band=_BAND, policy=policy, flat_floor=0.05
    ) == pytest.approx(0.05)


def test_an_empty_policy_returns_the_flat_floor_for_every_input() -> None:
    """The behaviour-preserving case: today's table holds zero rows.

    Until somebody seeds a row this function must be a pass-through, so
    shipping `RS-B3` changes no admin's view on the day it lands.
    """
    empty = ThresholdPolicy(rows={})
    for band in ("3-5", "10-13", "16+", ""):
        for category in ("violence", "violence/graphic", "sexual", ""):
            assert admin_noise_floor_for(
                category, age_band=band, policy=empty, flat_floor=0.05
            ) == pytest.approx(0.05)


def test_a_none_policy_returns_the_flat_floor() -> None:
    """A caller that loaded no policy still gets the flat floor, not None.

    ``policy=None`` means "not consulted", which must not be confused with
    ``flat_floor=None`` ("filtering off"). Collapsing the two would turn a
    skipped DB read into a silently un-denoised admin view.
    """
    assert admin_noise_floor_for(
        "violence", age_band=_BAND, policy=None, flat_floor=0.05
    ) == pytest.approx(0.05)


def test_min_verdict_is_never_consulted() -> None:
    """The FLAG default on ``min_verdict`` must not leak into the admin lane.

    Every row built by ``_policy_with`` carries ``min_verdict=FLAG``. If this
    resolver consulted it (or if a future refactor routed the admin lane
    through ``ThresholdPolicy.surfaces``), an ADVISORY finding would be hidden
    admin-wide regardless of score. The proof is that the resolver's answer is
    a plain number driven solely by ``min_score``, and that feeding it into
    ``admin_surfaces`` still surfaces an above-floor advisory.
    """
    policy = _policy_with((_BAND, "violence", 0.10))
    floor = admin_noise_floor_for(
        "violence", age_band=_BAND, policy=policy, flat_floor=0.05
    )
    assert floor == pytest.approx(0.10)
    assert floor is not None
    assert admin_surfaces(Verdict.ADVISORY, 0.20, noise_floor=floor)
    assert not admin_surfaces(Verdict.ADVISORY, 0.05, noise_floor=floor)
    # And the never-hide guarantees are untouched by the band row.
    assert admin_surfaces(Verdict.FLAG, 0.0, noise_floor=floor)
    assert admin_surfaces(Verdict.BLOCK, 0.0, noise_floor=floor)
    assert admin_surfaces(Verdict.ADVISORY, None, noise_floor=floor)


def test_a_row_can_lower_the_floor_as_well_as_raise_it() -> None:
    """A band row replaces the flat floor; it is not a maximum of the two.

    A younger band should be able to see MORE than the global floor allows,
    which only works if the row's score is used verbatim rather than combined
    with the flat floor by max().
    """
    policy = _policy_with(("3-5", "violence", 0.001))
    assert admin_noise_floor_for(
        "violence", age_band="3-5", policy=policy, flat_floor=0.05
    ) == pytest.approx(0.001)


def test_a_zero_row_disables_the_floor_for_its_pair_without_disabling_others() -> None:
    """``min_score = 0`` is a real value, not an absent one.

    A 0.0 row means "show every scored advisory in this pair"; conflating it
    with NULL would fall back to the flat floor and keep hiding them.
    """
    policy = _policy_with((_BAND, "violence", 0.0))
    assert admin_noise_floor_for(
        "violence", age_band=_BAND, policy=policy, flat_floor=0.05
    ) == pytest.approx(0.0)
    assert admin_noise_floor_for(
        "sexual", age_band=_BAND, policy=policy, flat_floor=0.05
    ) == pytest.approx(0.05)


def test_a_category_is_matched_exactly_not_by_prefix() -> None:
    """``violence`` and ``violence/graphic`` are separate rows.

    ThresholdPolicy keys on the exact category string, so a row on the parent
    category does not silently cover its slash-subcategory. Pinning this keeps
    a future seed from assuming inheritance the lookup does not provide.
    """
    policy = _policy_with((_BAND, "violence", 0.5))
    assert admin_noise_floor_for(
        "violence/graphic", age_band=_BAND, policy=policy, flat_floor=0.05
    ) == pytest.approx(0.05)
