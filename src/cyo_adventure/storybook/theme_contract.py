"""Theme contract schema (Pydantic v2), WS-2.

A theme contract is a machine-readable sidecar document
(``skeletons/<band>/<slug>.contract.json``) that declares the named ``{SLOT}``
positions a parameterized skeleton exposes for re-theming, plus the
machine-checkable constraints each slot must satisfy before any value is bound
to it. This module holds only the schema and the token grammar; it is a pure,
dependency-light module (stdlib + pydantic + :mod:`cyo_adventure.storybook.models`
only) so it can be imported from both the generation pipeline and the
deterministic validator without any layering inversion (see
``docs/planning/ws2-parameterized-catalog-design.md`` section 2.2 and
``docs/planning/adr/adr-019-parameterized-skeletons-theme-contracts.md``).

The authoritative safety check against a proposed slot *binding* (whether a
value actually satisfies a slot's constraints, including the band-mandatory
denylist floor) lives in :mod:`cyo_adventure.validator.slots`, not here. This
module only shapes and cross-validates the contract document itself.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cyo_adventure.storybook.models import AgeBand

# The token grammar for `{SLOT}` placeholders, defined once here and imported
# everywhere a slotted surface (beats guidance, ending title, choice label
# template) is parsed or rendered. A token is a bare, all-caps identifier
# wrapped in braces, e.g. `{A1_GATE}`; `{lower}` and `{1BAD}` do not match.
SLOT_TOKEN_RE = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")

# The slot id grammar, shared by SlotSpec.id's Field pattern below and quoted
# here for callers that need to validate a candidate id without constructing
# a SlotSpec.
SLOT_ID_PATTERN = r"^[A-Z][A-Z0-9_]*$"

# The closed ADR-023 vocabulary for `SlotSpec.personalization_field` (story
# personalization P1, plan section 2.1): the only fields a `personalizable`
# slot may declare. A slot whose field is not a member of this set is
# rejected by `ThemeContract._check_personalizable_slots` below.
PERSONALIZATION_FIELDS: frozenset[str] = frozenset(
    {
        "protagonist_first_name",
        "pronoun_set",
        "sibling_name",
        "pet_species",
        "pet_name",
        "kinship_label",
        "favorite",
        "home_type",
        "dedication",
    }
)

# The subset of `PERSONALIZATION_FIELDS` that names a real person (a real
# child's own first name or a real sibling's name), as opposed to a pet,
# object, or category. A `personalizable` slot bound to one of these fields
# must also declare `role_safety` (plan R11: a real name must never land in
# an antagonist/mishap role), proving a per-skeleton role audit happened.
REAL_PERSON_PERSONALIZATION_FIELDS: frozenset[str] = frozenset(
    {"protagonist_first_name", "sibling_name"}
)


class SlotScope(StrEnum):
    """The structural level a slot's value is bound at.

    Attributes:
        GLOBAL: Whole-story identity (hero, companion, place, deadline).
        ROUTE: A top-level branch's identity.
        TRACK: A sub-track or segment within a branch.
        ENDING: A slot that names an ending title.
    """

    GLOBAL = "global"
    ROUTE = "route"
    TRACK = "track"
    ENDING = "ending"


class SlotConstraints(BaseModel):
    """Deterministic and opt-in constraints on one slot's bound value.

    ``max_words``, the ``forbid`` denylist bundles, ``distinct_from``
    sibling references, and ``pattern`` are all enforced deterministically
    by :func:`cyo_adventure.validator.slots.validate_slot_bindings`; this
    model only carries the declared constraint data, it performs no
    matching itself.
    """

    model_config = ConfigDict(extra="forbid")

    max_words: int = Field(default=8, ge=1, le=16)
    forbid: list[str] = Field(default_factory=list)
    distinct_from: list[str] = Field(default_factory=list)
    pattern: str | None = None


class SlotSpec(BaseModel):
    """One named, constrained slot a parameterized skeleton exposes.

    Attributes:
        id: The slot id, matching :data:`SLOT_ID_PATTERN`.
        scope: The structural level the slot's value is bound at.
        meaning: A human-readable description of what the slot represents.
        guidance: Advisory guidance for the LLM binder (may be empty).
        constraints: Deterministic/opt-in constraints on the bound value.
        kind: ``"theme"`` (the default): a slot bound by the LLM theme
            binder from the child/guardian's free-text brief, exactly as
            before P1b. ``"personalizable"``: a slot whose value is ALWAYS
            the contract's own ``default_binding[id]`` (never an LLM-proposed
            value; ADR-023 plan section 2), rendered with a sentinel wrapper
            (:func:`cyo_adventure.storybook.sentinels.wrap`) so a client can
            later resolve it to a family's chosen personalization.
        personalization_field: For a ``personalizable`` slot, which member of
            :data:`PERSONALIZATION_FIELDS` this slot personalizes. Must be
            ``None`` for a ``theme`` slot.
        role_safety: For a ``personalizable`` slot, the narrative role this
            slot's value plays (``"protagonist"`` or ``"companion"``).
            Required (non-``None``) when ``personalization_field`` is in
            :data:`REAL_PERSON_PERSONALIZATION_FIELDS` (a real person's
            name must never land in an antagonist/mishap role, plan R11).
            Must be ``None`` for a ``theme`` slot.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=SLOT_ID_PATTERN)
    scope: SlotScope
    meaning: str = Field(min_length=1)
    guidance: str = ""
    constraints: SlotConstraints = Field(default_factory=SlotConstraints)
    kind: Literal["theme", "personalizable"] = "theme"
    personalization_field: str | None = None
    role_safety: Literal["protagonist", "companion"] | None = None


class ThemeContract(BaseModel):
    """The full per-skeleton theme contract.

    Attributes:
        contract_version: The contract schema version for this document.
        skeleton_slug: The slug of the skeleton this contract constrains.
        age_band: The skeleton's reading age band.
        legacy_lexicon: The original theme's proper nouns and distinctive
            setting terms; used as a deterministic leak denylist so a new
            binding cannot reintroduce the old theme's identity.
        default_binding: The original theme's slot values; the golden
            fixture and the no-theme fallback binding.
        slots: The declared slots, one :class:`SlotSpec` per ``{SLOT}``
            token the skeleton exposes.
    """

    model_config = ConfigDict(extra="forbid")

    contract_version: int = Field(ge=1)
    skeleton_slug: str = Field(min_length=1)
    age_band: AgeBand
    legacy_lexicon: list[str] = Field(default_factory=list)
    default_binding: dict[str, str]
    slots: list[SlotSpec] = Field(min_length=1)

    # #ASSUME: data-integrity: a theme contract is decoded from loosely typed
    # JSON on disk (a sidecar file, not schema-checked by anything upstream);
    # every cross-field invariant that keeps `default_binding`,
    # `distinct_from`, and `forbid` consistent with the declared slot set
    # must be enforced here, once, rather than trusted at each call site.
    # #VERIFY: tests/unit/test_theme_contract.py exercises every branch below
    # (duplicate ids, key drift, dangling distinct_from, blank forbid ids).
    @model_validator(mode="after")
    def _check_contract_invariants(self) -> Self:
        """Enforce the contract's cross-field invariants.

        Returns:
            Self: The validated contract.

        Raises:
            ValueError: If any cross-field invariant is violated.
        """
        self._check_unique_slot_ids()
        self._check_default_binding_keys()
        self._check_distinct_from_references()
        self._check_forbid_bundle_ids()
        self._check_personalizable_slots()
        return self

    def _check_unique_slot_ids(self) -> None:
        """Reject a contract that declares the same slot id twice.

        Raises:
            ValueError: If any slot id is declared more than once.
        """
        seen: set[str] = set()
        duplicates: set[str] = set()
        for slot in self.slots:
            if slot.id in seen:
                duplicates.add(slot.id)
            seen.add(slot.id)
        if duplicates:
            msg = f"duplicate slot id(s): {sorted(duplicates)}"
            raise ValueError(msg)

    def _check_default_binding_keys(self) -> None:
        """Reject a `default_binding` whose keys do not exactly match the slots.

        Raises:
            ValueError: If `default_binding` is missing a declared slot id or
                carries a key for an undeclared one.
        """
        declared = {slot.id for slot in self.slots}
        bound = set(self.default_binding)
        missing = declared - bound
        extra = bound - declared
        if missing or extra:
            msg = (
                "default_binding keys must exactly match declared slot ids: "
                f"missing={sorted(missing)} extra={sorted(extra)}"
            )
            raise ValueError(msg)

    def _check_distinct_from_references(self) -> None:
        """Reject a `distinct_from` entry that names an undeclared slot id.

        Raises:
            ValueError: If any slot's `distinct_from` references a sibling
                slot id that is not itself declared on this contract.
        """
        declared = {slot.id for slot in self.slots}
        for slot in self.slots:
            unknown = [
                ref for ref in slot.constraints.distinct_from if ref not in declared
            ]
            if unknown:
                msg = (
                    f"slot '{slot.id}' declares distinct_from reference(s) to "
                    f"undeclared slot id(s): {sorted(unknown)}"
                )
                raise ValueError(msg)

    def _check_forbid_bundle_ids(self) -> None:
        """Reject a blank `forbid` bundle id.

        This is only an import-cycle-free string presence check: whether a
        `forbid` id names a real, known denylist bundle is authoritatively
        checked by :mod:`cyo_adventure.validator.slots`, which this pure
        storybook-layer module must not import (that would invert the
        `storybook` -> `validator` dependency direction).

        Raises:
            ValueError: If any slot declares an empty or whitespace-only
                `forbid` bundle id.
        """
        for slot in self.slots:
            for bundle_id in slot.constraints.forbid:
                if not bundle_id.strip():
                    msg = f"slot '{slot.id}' declares an empty/blank forbid bundle id"
                    raise ValueError(msg)

    # #CRITICAL: security: a `personalizable` slot's value is NEVER offered to
    # the LLM bind step (`generation/binding.py::bind_theme_to_contract`); it
    # is pinned to `default_binding[slot.id]` and rendered with a sentinel
    # wrapper for later client-side resolution (ADR-023 plan section 2). Both
    # checks below are the schema-level half of that guarantee: a
    # personalizable slot must declare a real, known field so the pin has a
    # defined meaning, and a real-person field must prove a role-safety audit
    # happened (plan R11) before a real name can ever be bound to this
    # skeleton's slot in this role.
    # #VERIFY: tests/unit/test_theme_contract.py's personalizable-slot cases.
    def _check_personalizable_slots(self) -> None:
        """Enforce the `kind`/`personalization_field`/`role_safety` invariants.

        A `personalizable` slot must declare a `personalization_field` that is
        a member of :data:`PERSONALIZATION_FIELDS`; if that field is in
        :data:`REAL_PERSON_PERSONALIZATION_FIELDS` it must also declare a
        non-null `role_safety`. A `theme` slot (the default `kind`) must not
        set either field, keeping the two kinds cleanly separated.

        Raises:
            ValueError: If any of the above invariants is violated.
        """
        errors: list[str] = [
            error for slot in self.slots for error in _personalizable_slot_errors(slot)
        ]
        if errors:
            raise ValueError("; ".join(errors))


def _personalizable_slot_errors(slot: SlotSpec) -> list[str]:
    """Return the `kind`/`personalization_field`/`role_safety` errors for one slot.

    Extracted from :meth:`ThemeContract._check_personalizable_slots` to keep
    that method's cognitive complexity low; see its docstring for the rules
    enforced.

    Args:
        slot: One declared slot spec.

    Returns:
        Zero or more human-readable error messages for this slot.
    """
    if slot.kind == "personalizable":
        return _personalizable_kind_errors(slot)
    return _theme_kind_errors(slot)


def _personalizable_kind_errors(slot: SlotSpec) -> list[str]:
    """Return the invariant errors for a `kind='personalizable'` slot.

    Args:
        slot: The slot to check (assumed `kind == "personalizable"`).

    Returns:
        Zero or more human-readable error messages.
    """
    if slot.personalization_field not in PERSONALIZATION_FIELDS:
        return [
            f"slot '{slot.id}' is kind='personalizable' but "
            f"personalization_field={slot.personalization_field!r} is not a "
            "member of PERSONALIZATION_FIELDS"
        ]
    if (
        slot.personalization_field in REAL_PERSON_PERSONALIZATION_FIELDS
        and slot.role_safety is None
    ):
        return [
            f"slot '{slot.id}' personalizes a real-person field "
            f"({slot.personalization_field!r}) and must declare a non-null "
            "role_safety"
        ]
    return []


def _theme_kind_errors(slot: SlotSpec) -> list[str]:
    """Return the invariant errors for a `kind='theme'` slot.

    Args:
        slot: The slot to check (assumed `kind == "theme"`).

    Returns:
        Zero or more human-readable error messages.
    """
    errors: list[str] = []
    if slot.personalization_field is not None:
        errors.append(
            f"slot '{slot.id}' has kind='theme' but sets personalization_field; "
            "only a kind='personalizable' slot may set it"
        )
    if slot.role_safety is not None:
        errors.append(
            f"slot '{slot.id}' has kind='theme' but sets role_safety; only a "
            "kind='personalizable' slot may set it"
        )
    return errors


def slot_ids(contract: ThemeContract) -> frozenset[str]:
    """Return the set of slot ids a contract declares.

    Args:
        contract: The theme contract to inspect.

    Returns:
        A frozen set of every declared slot id.
    """
    return frozenset(slot.id for slot in contract.slots)
