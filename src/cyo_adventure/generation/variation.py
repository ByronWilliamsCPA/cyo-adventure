"""The variation-axis library (generation/variation.py).

A7. A small set of authored *craft* axes, one drawn per request, so two fills of
one skeleton differ along a chosen dimension rather than only by whatever the
sampler happened to do.

Why an axis and not a temperature
---------------------------------

Raising sampling temperature buys variation by making every choice noisier,
including word choice and sentence length, which is exactly what the reading-level
gate (RL-13) measures. So the cheap knob trades directly against the one property
the band contract cannot flex on. An axis instead varies a *decision the author
makes*, at a fixed register: where the camera sits, whose feelings the scene
tracks, which sense leads. Prose written to a different axis reads differently
without reading harder.

Why one axis and not several
----------------------------

Each axis is a whole-story instruction, and stacking them produces mush: a fill
told to be simultaneously close-third, sound-led, slow-paced and
antagonist-sympathetic has been given four masters and will serve none. One axis
per fill, drawn deterministically from a seed so a re-run reproduces it.

What this is not
----------------

Not a content lever. No axis changes what happens, who is in danger, or how a
story ends; those are the skeleton's and the gate's business. An axis only
changes how a fixed sequence of beats is narrated, which is why it cannot move a
story out of its band profile or past a safety classifier.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Sequence


class VariationAxis(NamedTuple):
    """One authored craft axis.

    Attributes:
        key: Stable identifier, persisted in ``authoring_metadata`` so a fill is
            reproducible and an axis's effect is measurable after the fact.
        label: Short human-readable name for logs and review surfaces.
        instruction: The sentence handed to the fill prompt. Written as a
            positive craft direction, never as a prohibition, because a
            prohibition tells a model what to avoid without telling it what to
            do instead.
    """

    key: str
    label: str
    instruction: str


# The authored library. Deliberately small: each entry has to be a direction a
# competent writer could actually follow across a whole story, and a longer list
# would mostly add near-duplicates that dilute the effect without adding variety.
VARIATION_AXES: tuple[VariationAxis, ...] = (
    VariationAxis(
        key="close_interior",
        label="narrative distance: close",
        instruction=(
            "Stay close to the protagonist's interior. Prefer what they notice, "
            "want, and fear in the moment over any wider view of the scene."
        ),
    ),
    VariationAxis(
        key="wide_observational",
        label="narrative distance: wide",
        instruction=(
            "Keep a slight observational distance. Let the place and the other "
            "characters carry as much of each scene as the protagonist's "
            "feelings do."
        ),
    ),
    VariationAxis(
        key="sound_led",
        label="sensory emphasis: sound",
        instruction=(
            "Lead with sound. Establish each new place by what can be heard "
            "there before what can be seen."
        ),
    ),
    VariationAxis(
        key="touch_led",
        label="sensory emphasis: touch and temperature",
        instruction=(
            "Lead with touch and temperature. Ground each new place in how it "
            "feels against skin, underfoot, and in the air."
        ),
    ),
    VariationAxis(
        key="wry_register",
        label="tonal register: wry",
        instruction=(
            "Keep a dry, lightly wry narrating voice. Let the protagonist notice "
            "the absurd without ever undercutting a moment that matters."
        ),
    ),
    VariationAxis(
        key="earnest_register",
        label="tonal register: earnest",
        instruction=(
            "Keep an earnest, unironic narrating voice. Take the protagonist's "
            "stakes entirely seriously, at their own scale."
        ),
    ),
    VariationAxis(
        key="companion_favoured",
        label="viewpoint favour: the companion",
        instruction=(
            "Give the companion or secondary character real interiority. Let "
            "them want something of their own that the protagonist has to notice."
        ),
    ),
    VariationAxis(
        key="antagonist_understood",
        label="viewpoint favour: the opposition",
        instruction=(
            "Make the opposing force comprehensible. Whoever or whatever stands "
            "in the way should have a reason a reader could restate, without "
            "being excused."
        ),
    ),
    VariationAxis(
        key="patient_pacing",
        label="pacing: patient openings",
        instruction=(
            "Take your time entering each scene and leave quickly. Establish "
            "place and mood first, then move."
        ),
    ),
    VariationAxis(
        key="in_motion_pacing",
        label="pacing: already in motion",
        instruction=(
            "Begin each scene already in motion, mid-action or mid-exchange, and "
            "fill in where they are as they go."
        ),
    ),
)

_AXES_BY_KEY: dict[str, VariationAxis] = {axis.key: axis for axis in VARIATION_AXES}


def axis_for_key(key: str) -> VariationAxis | None:
    """Return the axis with this key, or ``None``.

    Args:
        key: A persisted axis key.

    Returns:
        VariationAxis | None: The axis, or ``None`` when the key is unknown (a
            library entry removed after a job was queued). Callers treat a miss
            as "no axis" rather than failing the job, since an axis is a craft
            hint and never a correctness requirement.
    """
    return _AXES_BY_KEY.get(key)


def select_axis(
    seed: str, *, exclude: Sequence[str] = (), axes: Sequence[VariationAxis] = ()
) -> VariationAxis:
    """Pick one axis deterministically from a seed, avoiding recent ones.

    Deterministic rather than random so a re-run of the same job reproduces the
    same prose direction, which is what makes an axis's effect measurable at all;
    a randomly-drawn axis would confound every before-and-after comparison.

    Args:
        seed: Any stable per-request string (the request or job id). Hashed, so
            callers need not think about distribution.
        exclude: Axis keys used recently for this family, which are skipped while
            any unexcluded axis remains. Exhausting the library falls back to the
            full set rather than failing, because repeating an axis is a much
            smaller problem than refusing to generate.
        axes: Override the library, for tests.

    Returns:
        VariationAxis: The chosen axis. Never ``None``: a fill always gets a
            direction, since "no axis" is the behaviour this item exists to end.
    """
    library = tuple(axes) or VARIATION_AXES
    excluded = frozenset(exclude)
    pool = tuple(axis for axis in library if axis.key not in excluded) or library
    # #ASSUME: data integrity: blake2b over the seed, not hash(), because
    # Python's str hash is salted per process and would make the same job pick a
    # different axis on every worker restart, silently breaking reproducibility.
    # #VERIFY: tests/unit/test_variation.py::test_selection_is_stable_across_calls
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    return pool[int.from_bytes(digest, "big") % len(pool)]
