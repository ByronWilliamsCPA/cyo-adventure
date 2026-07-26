"""Build sentinel-bearing specimens for the survival measurement (plan 3.4).

No contract on disk declares a ``kind="personalizable"`` slot yet, so a real
catalog skeleton renders no sentinels at all (the "dormancy fact" driving this
whole package's existence). This module authors its own fixtures instead: it
loads a real skeleton+contract pair, flips a chosen number of the contract's
``theme`` slots to ``personalizable`` with a GENERIC default binding word (see
the identity-safety note below), and renders the bound skeleton
(:func:`cyo_adventure.generation.binding.render_bound_skeleton`) so it actually
carries ``{~SLOTID:GenericWord~}`` sentinels. The result is a
:class:`Specimen`: a pre-fill, sentinel-bearing skeleton ready for
:func:`cyo_adventure.generation.orchestrator.fill_skeleton`.

Pure and deterministic: given the same skeleton/contract pair and
``slots_per_story``, :func:`build_specimen` always flips the same slots to the
same generic values, so a fixture is reproducible across runs.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.binding import (
    personalizable_slot_ids,
    render_bound_skeleton,
)
from cyo_adventure.storybook.sentinels import find_sentinels, wrap
from cyo_adventure.storybook.theme_contract import ThemeContract

if TYPE_CHECKING:
    from pathlib import Path

# The candidate (personalization_field, generic default word, role_safety)
# tuples this module tries, in priority order, when flipping a theme slot to
# personalizable. `role_safety` is required by the schema only for a
# REAL_PERSON_PERSONALIZATION_FIELDS member (protagonist_first_name,
# sibling_name); every other field must leave it None.
#
# #CRITICAL: security: every word below is a GENERIC placeholder, never a real
# child's name, sibling's name, or any other real identity. This is the only
# source of sentinel inner values this package ever uses; a real-identity leak
# into a provider prompt would defeat the whole point of sentinel wrapping.
# #VERIFY: test_measurement_fixtures.py::test_fixtures_contain_no_real_identity
_CANDIDATES: tuple[tuple[str, str, str | None], ...] = (
    ("protagonist_first_name", "Explorer", "protagonist"),
    ("pet_species", "the pup", None),
    ("pet_name", "Buddy", None),
    ("kinship_label", "the grown-up", None),
    ("favorite", "the treasure", None),
    ("home_type", "the cottage", None),
    ("dedication", "for you", None),
    ("sibling_name", "the sibling", "companion"),
    ("pronoun_set", "they/them", None),
)

# The default fixture set (plan 3.4: ">=5 real skeletons spanning >=4 distinct
# bands"). Verified present on disk as of this package's authoring; a missing
# pair fails loudly at load time (see load_pair) rather than silently
# shrinking the sample.
DEFAULT_FIXTURES: tuple[tuple[str, str], ...] = (
    ("3-5", "puddle-jumping-day"),
    ("5-8", "the-night-market"),
    ("8-11", "the-cave-of-echoes"),
    ("10-13", "the-midnight-museum"),
    ("13-16", "the-signal-in-the-static"),
)

# The theme brief driving the fill. Content is inert (the mock provider
# ignores it entirely; a live provider sees only these generic words, never a
# real family's brief), mirroring the precedent in
# `cyo_adventure.mutation.sample_fill._DEFAULT_THEME_BRIEF`.
_DEFAULT_THEME_BRIEF: dict[str, object] = {
    "setting": "a quiet, friendly place",
    "notes": "deterministic sentinel-survival measurement (plan 3.4); fixture data only",
}

_DEFAULT_SLOTS_PER_STORY = 4


@dataclass(frozen=True, slots=True)
class Specimen:
    """One sentinel-bearing measurement specimen.

    Attributes:
        slug: The source skeleton's slug (filename stem).
        band: The source contract's reading age band, as a plain string.
        bound_skeleton: The pre-fill bound skeleton (FILL directives intact,
            sentinels rendered into beats guidance / ending titles); this is
            the reference :func:`~cyo_adventure.validator.sentinel_integrity.check_sentinel_integrity`
            compares a fill against.
        theme_brief: The (inert, generic) theme brief to pass to
            :func:`~cyo_adventure.generation.orchestrator.fill_skeleton`.
        slot_bindings: The full ``{slot_id: value}`` map used to render
            ``bound_skeleton``, passed straight through to ``fill_skeleton``'s
            ``slot_bindings`` parameter (the WS-2 bound-fill path).
        personalizable_slots: The ids of the slots this specimen flipped to
            ``kind="personalizable"``.
        expected_sentinels: Every full sentinel token
            (``{~SLOTID:Value~}``) present in ``bound_skeleton``, for
            fixture-level assertions.
    """

    slug: str
    band: str
    bound_skeleton: dict[str, object]
    theme_brief: dict[str, object]
    slot_bindings: dict[str, str]
    personalizable_slots: frozenset[str]
    expected_sentinels: frozenset[str]


def load_pair(
    skeletons_root: Path, band: str, slug: str
) -> tuple[dict[str, object], ThemeContract]:
    """Load a real catalog skeleton and its theme contract by band and slug.

    Args:
        skeletons_root: The repo's ``skeletons/`` directory.
        band: The age band directory name (e.g. ``"8-11"``).
        slug: The skeleton's filename stem (e.g. ``"the-cave-of-echoes"``).

    Returns:
        tuple[dict[str, object], ThemeContract]: The raw skeleton document and
            its validated theme contract.

    Raises:
        FileNotFoundError: If either file is missing.
        TypeError: If the skeleton file does not contain a JSON object.
    """
    skeleton_path = skeletons_root / band / f"{slug}.json"
    contract_path = skeletons_root / band / f"{slug}.contract.json"
    if not skeleton_path.is_file():
        msg = f"no skeleton file at {skeleton_path}"
        raise FileNotFoundError(msg)
    if not contract_path.is_file():
        msg = f"no contract file at {contract_path}"
        raise FileNotFoundError(msg)

    raw: object = json.loads(skeleton_path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    if not isinstance(raw, dict):
        msg = f"expected a JSON object in {skeleton_path}"
        raise TypeError(msg)
    skeleton = cast("dict[str, object]", raw)
    contract = ThemeContract.model_validate_json(
        contract_path.read_text(encoding="utf-8")
    )
    return skeleton, contract


def _personalize_contract(
    contract: ThemeContract, *, slots_per_story: int
) -> ThemeContract:
    """Return a contract with up to ``slots_per_story`` theme slots flipped.

    Walks the contract's slots in declared order; for each still-``theme``
    slot, tries each :data:`_CANDIDATES` entry (preferring a
    ``personalization_field`` not yet used by an earlier flip in this same
    contract) until one round-trips through :class:`ThemeContract`'s own
    validators (the contract-time invariants Task 2 added, including the
    default-binding constraint check). Stops once ``slots_per_story`` slots
    are flipped or every slot has been tried.

    Args:
        contract: The source contract (unmodified; a new contract is
            returned).
        slots_per_story: The target number of slots to flip.

    Returns:
        ThemeContract: A new, independently validated contract with the
            flipped slots and their generic default bindings.

    Raises:
        ValueError: If not even one slot could be flipped (no candidate
            satisfies any theme slot's constraints), since a specimen with
            zero personalizable slots has nothing to measure.
    """
    data = cast("dict[str, object]", contract.model_dump(mode="json"))
    slots = cast("list[dict[str, object]]", data["slots"])
    binding: dict[str, str] = dict(cast("dict[str, str]", data["default_binding"]))
    flipped: set[str] = set()
    used_fields: set[str] = set()

    for slot in slots:
        if len(flipped) >= slots_per_story:
            break
        if slot.get("kind", "theme") != "theme":
            continue
        slot_id = cast("str", slot["id"])
        ordered_candidates = sorted(_CANDIDATES, key=lambda c: c[0] in used_fields)
        for field, word, role in ordered_candidates:
            trial_slots: list[dict[str, object]] = copy.deepcopy(slots)
            trial_binding = dict(binding)
            for trial_slot in trial_slots:
                if trial_slot["id"] == slot_id:
                    trial_slot["kind"] = "personalizable"
                    trial_slot["personalization_field"] = field
                    trial_slot["role_safety"] = role
            trial_binding[slot_id] = word
            trial_data: dict[str, object] = {
                **data,
                "slots": trial_slots,
                "default_binding": trial_binding,
            }
            try:
                ThemeContract.model_validate(trial_data)
            except PydanticValidationError:
                continue
            slots = trial_slots
            binding = trial_binding
            flipped.add(slot_id)
            used_fields.add(field)
            break

    if not flipped:
        msg = (
            f"no theme slot on contract {contract.skeleton_slug!r} could be "
            "flipped to personalizable with any candidate generic default"
        )
        raise ValueError(msg)

    final_data: dict[str, object] = {**data, "slots": slots, "default_binding": binding}
    return ThemeContract.model_validate(final_data)


def build_specimen(
    skeleton: dict[str, object],
    contract: ThemeContract,
    slug: str,
    *,
    slots_per_story: int = _DEFAULT_SLOTS_PER_STORY,
) -> Specimen:
    """Build one sentinel-bearing specimen from a real skeleton+contract pair.

    Args:
        skeleton: The raw skeleton document (FILL directives intact).
        contract: The skeleton's theme contract.
        slug: The skeleton's slug, carried onto the returned specimen.
        slots_per_story: How many of the contract's ``theme`` slots to flip to
            ``personalizable``. Defaults to 4 (plan 3.4's 3-6 range).

    Returns:
        Specimen: The pre-fill, sentinel-bearing specimen.

    Raises:
        ValidationError: If ``slots_per_story`` is less than 1. A zero or
            negative count would flip no slots and yield a specimen with no
            personalizable sentinels, a degenerate data point that would
            silently count as a clean pass (nothing to survive).
    """
    if slots_per_story < 1:
        msg = "slots_per_story must be a positive integer"
        raise ValidationError(msg, field="slots_per_story", value=slots_per_story)
    personalized_contract = _personalize_contract(
        contract, slots_per_story=slots_per_story
    )
    personalizable_slots = personalizable_slot_ids(personalized_contract)
    bound = render_bound_skeleton(
        skeleton,
        personalized_contract.default_binding,
        personalizable_slots=personalizable_slots,
    )
    serialized = json.dumps(bound)
    expected_sentinels = frozenset(
        wrap(slot_id, value) for slot_id, value in find_sentinels(serialized)
    )
    return Specimen(
        slug=slug,
        band=str(contract.age_band),
        bound_skeleton=bound,
        theme_brief=dict(_DEFAULT_THEME_BRIEF),
        slot_bindings=dict(personalized_contract.default_binding),
        personalizable_slots=personalizable_slots,
        expected_sentinels=expected_sentinels,
    )
