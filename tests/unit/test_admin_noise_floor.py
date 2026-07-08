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
    admin_surfaces,
)

pytestmark = pytest.mark.unit

_FLOOR = 0.05


def test_admin_noise_floor_default_is_point_zero_five() -> None:
    """Lock the code default so it cannot drift silently from the seed row."""
    assert ADMIN_NOISE_FLOOR_DEFAULT == 0.05


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
