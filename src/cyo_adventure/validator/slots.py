"""Deterministic pre-fill slot validator, WS-2.

Checks a proposed theme *binding* (a flat ``{SLOT_ID: value}`` map produced by
the LLM binding step) against its :class:`~cyo_adventure.storybook.theme_contract.ThemeContract`
before any fill call is spent. This is deliberately distinct from
:func:`cyo_adventure.validator.gate.run_gate`: ``run_gate`` judges a finished
story *document* after generation; :func:`validate_slot_bindings` judges a
proposed theme binding *before any story exists*. Both are pure and
deterministic; they guard different artifacts at different points in the
pipeline (``docs/planning/ws2-parameterized-catalog-design.md`` section 4.2).

Pure module: stdlib + pydantic types + ``storybook.theme_contract`` +
``storybook.models`` (for :class:`AgeBand`) only. No generation, db,
sqlalchemy, LLM, randomness, or I/O of any kind.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.storybook.models import AgeBand

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cyo_adventure.storybook.theme_contract import SlotSpec, ThemeContract

# Denylist bundles: versioned, lowercase word/phrase stems matched on word
# boundaries against a normalized (NFC, casefolded, whitespace-collapsed)
# candidate value. These are safety-bearing code, reviewed like code (see
# ADR-019 OQ-8): a change to any bundle bumps DENYLIST_VERSION.
DENYLIST_VERSION = 1

_LETHAL: frozenset[str] = frozenset(
    {
        "die",
        "dies",
        "died",
        "dying",
        "dead",
        "death",
        "deadly",
        "fatal",
        "kill",
        "kills",
        "killed",
        "killing",
        "drown",
        "drowns",
        "drowned",
        "drowning",
        "suffocate",
        "suffocates",
        "suffocated",
        "suffocating",
        "corpse",
        "grave",
        "lethal",
        "perish",
        "perished",
        "perishes",
    }
)

_WEAPON: frozenset[str] = frozenset(
    {
        "gun",
        "knife",
        "blade",
        "sword",
        "spear",
        "axe",
        "dagger",
        "rifle",
        "pistol",
        "weapon",
        "crossbow",
        "javelin",
    }
)

_TOXIC: frozenset[str] = frozenset(
    {
        "poison",
        "poisonous",
        "poisoned",
        "venom",
        "venomous",
        "toxic",
        "acid",
        "radioactive",
        "unbreathable",
        "toxin",
        "toxins",
    }
)

_CAPTURE: frozenset[str] = frozenset(
    {
        "kidnap",
        "kidnapped",
        "kidnaps",
        "imprisoned",
        "imprison",
        "trapped forever",
        "cage",
        "caged",
        "hostage",
        "captive",
        "shackled",
        "chained",
    }
)

_GRAPHIC: frozenset[str] = frozenset(
    {
        "blood",
        "bleeding",
        "bleeds",
        "gore",
        "gory",
        "wound",
        "wounded",
        "mutilate",
        "mutilated",
        "mangled",
        "severed",
    }
)

_DESPAIR: frozenset[str] = frozenset(
    {
        "hopeless",
        "hopelessness",
        "despair",
        "despairing",
        "abandoned forever",
        "alone forever",
        "forsaken",
        "forgotten forever",
    }
)

_BUNDLES: dict[str, frozenset[str]] = {
    "lethal": _LETHAL,
    "weapon": _WEAPON,
    "toxic": _TOXIC,
    "capture": _CAPTURE,
    "graphic": _GRAPHIC,
    "despair": _DESPAIR,
}

# Public: the known denylist bundle ids, so a caller (e.g.
# scripts/check_theme_contract.py) can reject a contract that declares an
# unknown `forbid` bundle id (a typo that would otherwise silently
# contribute zero terms to a slot's effective denylist).
BUNDLE_IDS: frozenset[str] = frozenset(_BUNDLES)

# #CRITICAL: security: this union is the band-mandatory denylist floor
# (ws2-parameterized-catalog-design.md section 3.1, mirrored against the real
# fail-state policy in validator/band_profile.py:38-92: 3-5 and 5-8 forbid
# death + capture endings; 8-11 forbids death). It is applied unconditionally
# by validate_slot_bindings below, unioned with whatever a contract declares.
# A contract can only ADD bundles beyond this floor; nothing in contract data
# can remove or shrink it, so a contract-authoring omission (forgetting to
# declare `lethal` on a young-band slot) can never open a young-band safety
# hole. Defense in depth against ADR-019's leg 1.
# #VERIFY: tests/unit/test_slot_validator.py::test_band_mandatory_union_*
_BAND_MANDATORY: dict[AgeBand, frozenset[str]] = {
    AgeBand.BAND_3_5: frozenset(
        {"lethal", "capture", "weapon", "toxic", "graphic", "despair"}
    ),
    AgeBand.BAND_5_8: frozenset(
        {"lethal", "capture", "weapon", "toxic", "graphic", "despair"}
    ),
    AgeBand.BAND_8_11: frozenset({"lethal", "toxic", "graphic"}),
    AgeBand.BAND_10_13: frozenset({"graphic"}),
    AgeBand.BAND_13_16: frozenset(),
    AgeBand.BAND_16_PLUS: frozenset(),
}

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class SlotViolation:
    """One deterministic reason a proposed binding was rejected.

    Attributes:
        slot_id: The offending slot's id, or ``""`` for a binding-level
            violation (a missing or undeclared key) that names no single slot.
        rule: The check that failed, e.g. ``"charset"``, ``"max_words"``,
            ``"forbid:lethal"``, ``"distinct_from"``, ``"legacy_lexicon"``,
            ``"completeness"``, ``"non_empty"``, ``"single_line"``,
            ``"fence_guard"``, ``"pattern"``.
        message: A human-readable explanation. Safe to echo verbatim into a
            re-bind LLM prompt: it never contains the candidate story text,
            only slot/bundle identifiers, counts, and instructions.
    """

    slot_id: str
    rule: str
    message: str


def band_mandatory_bundles(age_band: AgeBand) -> frozenset[str]:
    """Return the denylist bundle ids mandatory for every slot in a band.

    Args:
        age_band: The contract's reading age band.

    Returns:
        The frozen set of bundle ids the validator unions into every slot's
        effective denylist for this band, regardless of what the contract
        declares.
    """
    return _BAND_MANDATORY.get(age_band, frozenset())


def _normalize(value: str) -> str:
    """NFC-normalize, casefold, and collapse internal whitespace runs.

    Used for word/denylist/distinctness matching only; charset, length, and
    single-line checks run against the raw value instead (per
    ws2-parameterized-catalog-design.md section 3.1).

    Args:
        value: The raw candidate string.

    Returns:
        The normalized string, stripped of leading/trailing whitespace.
    """
    nfc = unicodedata.normalize("NFC", value)
    folded = nfc.casefold()
    return _WHITESPACE_RE.sub(" ", folded).strip()


def _contains_stem(normalized_value: str, stem: str) -> bool:
    r"""Return whether a normalized value contains a stem on word boundaries.

    A multi-word stem (e.g. ``"trapped forever"``) matches as a
    boundary-anchored substring, since the escaped stem's internal space is
    literal and `\\b` anchors the whole phrase's edges.

    Args:
        normalized_value: A value already passed through :func:`_normalize`.
        stem: A lowercase denylist term or phrase.

    Returns:
        ``True`` if the stem appears in the value on word boundaries.
    """
    normalized_stem = _normalize(stem)
    if not normalized_stem:
        return False
    pattern = rf"\b{re.escape(normalized_stem)}\b"
    return re.search(pattern, normalized_value) is not None


def _jaccard(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Return the Jaccard overlap of two token sets.

    Args:
        tokens_a: The first value's whitespace-split token set.
        tokens_b: The second value's whitespace-split token set.

    Returns:
        ``len(intersection) / len(union)``, or ``0.0`` when the union is
        empty (both sets empty; equality is separately checked by the
        caller).
    """
    union = tokens_a | tokens_b
    if not union:
        return 0.0
    return len(tokens_a & tokens_b) / len(union)


def _completeness_violations(
    contract: ThemeContract, bindings: Mapping[str, str]
) -> list[SlotViolation]:
    """Return violations for missing or undeclared binding keys.

    Args:
        contract: The theme contract the binding is checked against.
        bindings: The proposed slot-value map.

    Returns:
        A list of binding-level (``slot_id=""``) completeness violations.
    """
    declared = {slot.id for slot in contract.slots}
    bound = set(bindings)
    missing = [
        SlotViolation(
            "", "completeness", f"slot '{slot_id}' is missing from the binding"
        )
        for slot_id in sorted(declared - bound)
    ]
    extra = [
        SlotViolation(
            "", "completeness", f"binding contains undeclared slot '{slot_id}'"
        )
        for slot_id in sorted(bound - declared)
    ]
    return missing + extra


def _charset_violations(slot_id: str, value: str) -> list[SlotViolation]:
    """Return charset/length violations, checked against the RAW value.

    Blocks slot-token injection (`{`/`}`), FILL-directive and fence forgery
    (`<<`/`>>`), the banned em dash, non-printable characters, and
    over-length values. This is the LLM01 structural-injection block: no
    slot value may ever contain the characters needed to forge a template
    token, a directive, or a prompt fence.

    Args:
        slot_id: The slot this value is bound to.
        value: The raw candidate value.

    Returns:
        Zero or more charset-rule violations.
    """
    violations: list[SlotViolation] = []
    if "{" in value or "}" in value:
        violations.append(
            SlotViolation(
                slot_id,
                "charset",
                "value must not contain '{' or '}' (blocks slot-token injection)",
            )
        )
    if "<<" in value or ">>" in value:
        violations.append(
            SlotViolation(
                slot_id,
                "charset",
                "value must not contain '<<' or '>>' (blocks FILL-directive forgery)",
            )
        )
    if "\u2014" in value:
        violations.append(
            SlotViolation(slot_id, "charset", "value must not contain an em dash")
        )
    if not value.isprintable():
        violations.append(
            SlotViolation(
                slot_id, "charset", "value must contain only printable characters"
            )
        )
    if len(value) > 120:
        violations.append(
            SlotViolation(
                slot_id,
                "charset",
                f"value exceeds the 120-character limit (length {len(value)})",
            )
        )
    return violations


def _single_line_violation(slot_id: str, value: str) -> SlotViolation | None:
    r"""Return a violation if the RAW value contains a control character.

    Covers `\\n`, `\\r`, and every other Unicode ``Cc`` control character.

    Args:
        slot_id: The slot this value is bound to.
        value: The raw candidate value.

    Returns:
        A ``single_line`` violation, or ``None`` when the value is clean.
    """
    if any(unicodedata.category(char) == "Cc" for char in value):
        return SlotViolation(
            slot_id,
            "single_line",
            "value must not contain newlines or control characters",
        )
    return None


def _structural_slot_violations(slot_id: str, value: str) -> list[SlotViolation]:
    """Return the RAW-value structural violations for one slot.

    Covers non-emptiness, single-line/control-character, charset/length, and
    the untrusted-input fence-marker guard. None of these checks look at the
    contract; they depend only on the candidate value itself.

    Args:
        slot_id: The slot this value is bound to.
        value: The raw candidate value bound to this slot.

    Returns:
        Zero or more structural violations.
    """
    violations: list[SlotViolation] = []

    if not value.strip():
        violations.append(
            SlotViolation(
                slot_id, "non_empty", "value must be non-empty after stripping"
            )
        )

    single_line = _single_line_violation(slot_id, value)
    if single_line is not None:
        violations.append(single_line)

    violations.extend(_charset_violations(slot_id, value))

    if "UNTRUSTED_USER_INPUT" in value or "END_UNTRUSTED_USER_INPUT" in value:
        violations.append(
            SlotViolation(
                slot_id,
                "fence_guard",
                "value must not contain the untrusted-input fence markers",
            )
        )

    return violations


def _forbid_violations(
    contract: ThemeContract, slot: SlotSpec, normalized_value: str
) -> list[SlotViolation]:
    """Return `forbid:<bundle>` violations for one slot's normalized value.

    The effective denylist is the slot's declared `constraints.forbid`
    bundles unioned with the band-mandatory floor for `contract.age_band`
    (see the `#CRITICAL` note on `_BAND_MANDATORY` above): the floor cannot
    be shrunk by contract data.

    Args:
        contract: The theme contract the binding is checked against.
        slot: The declared slot spec being checked.
        normalized_value: The slot's value, already passed through
            :func:`_normalize`.

    Returns:
        Zero or more `forbid:<bundle_id>` violations.
    """
    effective_bundles = set(slot.constraints.forbid) | band_mandatory_bundles(
        contract.age_band
    )
    violations: list[SlotViolation] = []
    for bundle_id in sorted(effective_bundles):
        terms = _BUNDLES.get(bundle_id, frozenset())
        if any(_contains_stem(normalized_value, term) for term in terms):
            violations.append(
                SlotViolation(
                    slot.id,
                    f"forbid:{bundle_id}",
                    f"value matches a denylisted term in bundle '{bundle_id}'",
                )
            )
    return violations


def _distinct_from_violations(
    slot: SlotSpec, normalized_value: str, bindings: Mapping[str, str]
) -> list[SlotViolation]:
    """Return `distinct_from` violations against this slot's declared siblings.

    Args:
        slot: The declared slot spec being checked.
        normalized_value: The slot's value, already passed through
            :func:`_normalize`.
        bindings: The full proposed slot-value map, for sibling lookups.

    Returns:
        Zero or more `distinct_from` violations.
    """
    violations: list[SlotViolation] = []
    for sibling_id in slot.constraints.distinct_from:
        sibling_value = bindings.get(sibling_id)
        if sibling_value is None:
            continue  # missing sibling is already flagged by completeness
        normalized_sibling = _normalize(sibling_value)
        overlap = _jaccard(
            set(normalized_value.split()), set(normalized_sibling.split())
        )
        if normalized_value == normalized_sibling or overlap > 0.5:
            violations.append(
                SlotViolation(
                    slot.id,
                    "distinct_from",
                    f"value must be distinct from sibling slot '{sibling_id}'",
                )
            )
    return violations


def _semantic_slot_violations(
    contract: ThemeContract, slot: SlotSpec, value: str, bindings: Mapping[str, str]
) -> list[SlotViolation]:
    """Return the normalized-matching violations for one bound slot's value.

    Covers `max_words`, the `forbid` bundles (declared plus the band floor),
    `distinct_from`, `legacy_lexicon`, and `pattern`. Word/denylist/
    distinctness checks match against the normalized value; `pattern` checks
    the raw value (an exact-format constraint).

    Args:
        contract: The theme contract the binding is checked against.
        slot: The declared slot spec being checked.
        value: The raw candidate value bound to this slot.
        bindings: The full proposed slot-value map, for `distinct_from`
            sibling lookups.

    Returns:
        Zero or more semantic violations.
    """
    violations: list[SlotViolation] = []
    normalized_value = _normalize(value)

    word_count = len(normalized_value.split())
    if word_count > slot.constraints.max_words:
        violations.append(
            SlotViolation(
                slot.id,
                "max_words",
                f"value has {word_count} words, exceeds max_words={slot.constraints.max_words}",
            )
        )

    violations.extend(_forbid_violations(contract, slot, normalized_value))
    violations.extend(_distinct_from_violations(slot, normalized_value, bindings))

    if any(_contains_stem(normalized_value, term) for term in contract.legacy_lexicon):
        violations.append(
            SlotViolation(
                slot.id,
                "legacy_lexicon",
                "value contains a term from this skeleton's legacy lexicon",
            )
        )

    if (
        slot.constraints.pattern is not None
        and re.fullmatch(slot.constraints.pattern, value) is None
    ):
        violations.append(
            SlotViolation(
                slot.id, "pattern", "value does not match the slot's required pattern"
            )
        )

    return violations


def _slot_violations(
    contract: ThemeContract, slot_id: str, value: str, bindings: Mapping[str, str]
) -> list[SlotViolation]:
    """Return every rule violation for one bound slot's value.

    Args:
        contract: The theme contract the binding is checked against.
        slot_id: The slot this value is bound to (assumed declared).
        value: The raw candidate value bound to this slot.
        bindings: The full proposed slot-value map (for `distinct_from`
            sibling lookups).

    Returns:
        Zero or more violations for this slot.
    """
    slot = next(s for s in contract.slots if s.id == slot_id)
    return _structural_slot_violations(slot_id, value) + _semantic_slot_violations(
        contract, slot, value, bindings
    )


def validate_slot_bindings(
    contract: ThemeContract, bindings: Mapping[str, str]
) -> list[SlotViolation]:
    """Deterministically check a proposed theme binding against its contract.

    Pure and total: no I/O, no LLM calls, no randomness. Calling this twice
    with the same ``contract`` and ``bindings`` always returns an equal list.
    An empty list means the binding passes and may proceed to
    ``render_bound_skeleton``.

    Distinct from :func:`cyo_adventure.validator.gate.run_gate`: ``run_gate``
    judges a finished story document after generation; this function judges
    a proposed slot-value map before any story exists, so a violating theme
    never reaches the (expensive) fill LLM call at all.

    Args:
        contract: The theme contract to validate against.
        bindings: The proposed ``{slot_id: value}`` map, as produced (and
            possibly re-produced, on retry) by the LLM binding step.

    Returns:
        A list of every :class:`SlotViolation` found, in a fixed,
        deterministic order (binding-level completeness violations first,
        then per declared slot in contract order). Empty when the binding
        passes.
    """
    violations = _completeness_violations(contract, bindings)
    for slot in contract.slots:
        if slot.id not in bindings:
            continue  # already reported by _completeness_violations
        violations.extend(
            _slot_violations(contract, slot.id, bindings[slot.id], bindings)
        )
    return violations
