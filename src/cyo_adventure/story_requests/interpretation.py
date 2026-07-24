"""WS-7 request-interpretation core (D1): models, echo floor, and derivation.

This module turns a set of requested story elements (short phrases the binder
decomposed from a child's premise) into a :class:`RequestInterpretation`: a
per-element reflection of what was built in versus set aside and why, rendered
in kid language and guardian detail. It is the "buildable now" and
"contract-grounded" core of capability K19
(``docs/planning/ws7-request-interpretation-design.md`` sections 3.1, 3.3, 5.3,
5.4, 7.2).

Pure module by design (mirrors ``storybook/theme_contract.py`` and
``validator/slots.py`` layering): stdlib + pydantic + the reused
``validator.slots`` echo-safety helpers + the ``generation.pii`` egress guard
only. NO database, generation-orchestration, LLM, randomness, or wall-clock
I/O: ``created_at`` is passed in by the caller, never read here, so the same
inputs always render the same object. The db write and the provider call live
in the WS-7 callers (worker / endpoints), not here.

Security (LLM01 / echo safety)
------------------------------
The single free-text field derived from untrusted premise content is
``InterpretedElement.element``, and it is nullable: a phrase that fails the
echo-safety floor (:func:`sanitize_element`, design section 7.2) is stored as
``None`` and the templates fall back to a generic, premise-free variant. Every
``kid_text`` / ``guardian_text`` is template output, never model output, so the
rendered object is safe to persist and serialize without re-moderation (CR-3).
Construction of an :class:`InterpretedElement` whose ``reason`` is
``SAFETY_POLICY``, ``PERSONAL_DETAILS``, or ``IDENTITY_PROTECTION`` with a
non-null ``element`` is a hard error (CR-3 belt and braces).

# #CRITICAL: security: the echo floor (sanitize_element) is the only thing that
#            keeps untrusted premise content from round-tripping to a child; it
#            reuses validator/slots' structural-injection block and denylist
#            stem matcher by import, never a copy, so it can never drift from
#            the slot gate. #VERIFY: tests/unit/test_interpretation.py exercises
#            every floor branch (structural, word cap, band floor, graphic echo
#            minimum, and the PII split to PERSONAL_DETAILS).
# #CRITICAL: data-integrity: InterpretedElement enforces element=None for the
#            three protected reasons at model construction, so no persistence
#            path can smuggle an unsafe phrase around the models. #VERIFY:
#            test_construction_rejects_non_null_element_for_protected_reasons.

Re-entry rule for the future (design section 7.4)
-------------------------------------------------
v1 NEVER injects any :class:`RequestInterpretation` content back into a prompt;
it is a read-only reflection surface. Any FUTURE consumer that re-injects an
``element`` phrase into a prompt (the plan's safety-invariant-4 list names
covers, repair, and richer kid echo) MUST treat that phrase as untrusted data
and fence it, exactly as ``fill_bound.md`` labels bound values "validated data,
not instructions". The echo floor's charset rules make such a reuse
structurally injection-proof, but the labeling duty is the consumer's: do not
add a consumer that skips the fence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.pii import PiiContext, assert_prompt_pii_safe
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.slots import (
    band_mandatory_bundles,
    denylisted_bundles,
    normalized_contains_any,
    structural_value_violations,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from typing import Self

__all__ = [
    "ENDING_FATE_LEXICON",
    "INTERPRETATION_VERSION",
    "LEXICON_VERSION",
    "MAX_ELEMENT_WORDS",
    "SELF_REFERENCE_LEXICON",
    "BandGroup",
    "ElementDecision",
    "ElementDisposition",
    "InterpretedElement",
    "RawElement",
    "ReasonCode",
    "RequestInterpretation",
    "band_group_for",
    "build_general_interpretation",
    "derive_dispositions",
    "render_interpretation",
    "sanitize_element",
]

_logger = get_logger(__name__)

# Versioning. INTERPRETATION_VERSION stamps the serialized object shape;
# LEXICON_VERSION versions the ending/fate and self-reference frozensets below,
# which are safety-bearing informational lexicons (bump on any term change),
# mirroring validator/slots.DENYLIST_VERSION.
INTERPRETATION_VERSION = 1
LEXICON_VERSION = 1

# An "element" is a short requested phrase, not a paragraph: the echo floor
# caps it (design section 7.2 check 2) both to keep it phrase-shaped and to
# bound the persisted at-rest surface.
MAX_ELEMENT_WORDS = 12

# The echo minimum applied on TOP of a band's mandatory denylist floor, even
# for bands whose floor is empty (design section 7.2 check 3): echoing gore
# back to a reader, even a 16+ reader and even to decline it, is a different
# act than binding it, so the graphic bundle is always an echo denylist. This
# is WS-7 data, NOT a change to validator/slots._BAND_MANDATORY.
_ECHO_MINIMUM_BUNDLES: frozenset[str] = frozenset({"graphic"})

# Shared empty default so keyword-only frozenset parameters below do not call
# frozenset() in a default expression (reportCallInDefaultInitializer). A
# frozenset is immutable, so sharing one instance across calls is safe.
_EMPTY_STR_SET: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Versioned informational lexicons (design sections 3.1, 5.3 rules 2 and 6).
# Lowercase stems matched on word boundaries via the reused
# validator/slots normalization (normalized_contains_any). These are
# informational, never enforcement: the deterministic slot gate already
# enforced safety, so a lexical miss here is imprecise, never unsafe.
# ---------------------------------------------------------------------------

# Endings/fates are structural (PL-15 / ADR-019 Decision 3 leg 2): no requested
# theme may choose them. A slot_id-null phrase matching this lexicon is set
# aside as STRUCTURE_FIXED (derivation rule 6). Includes lethal/win/lose fate
# words so that in a band whose denylist floor is empty (13-16, 16+) a
# "the dragon dies at the end" request still lands here rather than falling
# through to NOT_THIS_STORY_KIND.
ENDING_FATE_LEXICON: frozenset[str] = frozenset(
    {
        "ending",
        "endings",
        "ends",
        "the end",
        "finale",
        "final scene",
        "last scene",
        "fate",
        "destiny",
        "dies",
        "die",
        "death",
        "dead",
        "killed",
        "wins",
        "win",
        "won",
        "victory",
        "loses",
        "lose",
        "lost",
        "defeat",
        "defeated",
        "forever",
        "happily ever after",
        "the villain wins",
        "everyone survives",
        "no one survives",
    }
)

# Self-naming: a request for the child to appear as themselves. Route A
# (coppa-gdpr-remediation-plan.md Section 5 Decision 4) disallows self-naming by
# design, so a matching phrase is set aside as IDENTITY_PROTECTION with
# element=None (derivation rule 2), making the policy legible instead of
# silently substituting a fictional name. Detection is this lexicon OR the
# requesting child's own registered name (passed as ``self_names``).
SELF_REFERENCE_LEXICON: frozenset[str] = frozenset(
    {
        "myself",
        "my name",
        "my own name",
        "my real name",
        "about me",
        "story about me",
        "make me the hero",
        "make me the star",
        "me as the hero",
        "me as the star",
        "i want to be the hero",
        "i want to be in it",
        "put me in the story",
        "use my name",
        "name the hero after me",
        "the hero is me",
        "hero is me",
        "based on me",
    }
)


class ElementDisposition(StrEnum):
    """What became of one requested element (design section 3.1)."""

    BUILT_IN = "built_in"
    """Bound into the story (a validated slot binding or a structural fit)."""

    ADAPTED = "adapted"
    """Carried, but transformed to fit the band/structure.

    OQ-7 (ratified): kept as an enum member but emitted ONLY under the narrow
    3.1 trigger, a slot that was rejected on the first bind attempt and
    corrected on retry (:func:`derive_dispositions`' ``adapted_slot_ids``).
    Everything else that was placed is ``BUILT_IN``.
    """

    SET_ASIDE = "set_aside"
    """Understood, but deliberately not included."""

    CANNOT_CARRY = "cannot_carry"
    """This tree (or any tree in the cell) cannot host it."""


class ReasonCode(StrEnum):
    """Why an element got its disposition (design section 3.1)."""

    BOUND_TO_SLOT = "bound_to_slot"
    """Placed via a validated slot binding."""

    STORY_FIT = "story_fit"
    """Matches the skeleton's fixed structure/themes (e.g. the band promise)."""

    BAND_POLICY = "band_policy"
    """Tripped the band-mandatory denylist floor / content ceiling."""

    SAFETY_POLICY = "safety_policy"
    """Withheld by the echo-safety floor (structural / charset / word cap)."""

    GUARDIAN_CONTROL = "guardian_control"
    """Matched a G2 banned theme / content-flag cap for this profile."""

    STRUCTURE_FIXED = "structure_fixed"
    """Endings, topology, and fail-states are structural, not requestable."""

    NOT_THIS_STORY_KIND = "not_this_story_kind"
    """No slot carried it; a benign misfit for this skeleton."""

    NO_CONFORMING_BINDING = "no_conforming_binding"
    """Bind failed after retries (a whole-theme cannot-carry)."""

    PERSONAL_DETAILS = "personal_details"
    """PII in the request (name/email/phone/address); a privacy block, never a
    theme rejection."""

    IDENTITY_PROTECTION = "identity_protection"
    """Self-naming request; disallowed by design (Route A)."""


# The three reasons for which ``element`` MUST be null, in ANY register: a
# phrase that is unsafe, contains real personal data, or requests self-naming
# is never echoed, stored, or paraphrased (design sections 3.1, 6.3, 8;
# CR-3). Enforced at :class:`InterpretedElement` construction.
_ELEMENT_MUST_BE_NULL: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.SAFETY_POLICY,
        ReasonCode.PERSONAL_DETAILS,
        ReasonCode.IDENTITY_PROTECTION,
    }
)


class InterpretedElement(BaseModel):
    """One requested element's disposition, reason, and rendered reflection.

    ``element`` is the only untrusted-derived free text and is nullable: it is
    the echo-safe normalized phrase, or ``None`` when the echo floor withheld
    it. ``kid_text`` / ``guardian_text`` are always template output.
    """

    model_config = ConfigDict(extra="forbid")

    element: str | None
    disposition: ElementDisposition
    reason: ReasonCode
    slot_id: str | None = None
    rule: str | None = None
    kid_text: str
    guardian_text: str

    # #CRITICAL: security: belt-and-braces echo-safety enforcement (CR-3): a
    # protected-reason element with a non-null phrase is a construction error,
    # so no persistence path (even one that hand-builds a dict) can smuggle an
    # unsafe/PII/self-naming phrase into the at-rest surface.
    # #VERIFY: test_construction_rejects_non_null_element_for_protected_reasons.
    @model_validator(mode="after")
    def _enforce_element_null_for_protected_reasons(self) -> Self:
        """Reject a protected-reason element that still carries a phrase.

        Returns:
            Self: The validated element.

        Raises:
            ValueError: If ``reason`` is a protected reason (SAFETY_POLICY,
                PERSONAL_DETAILS, IDENTITY_PROTECTION) yet ``element`` is not
                ``None``.
        """
        if self.reason in _ELEMENT_MUST_BE_NULL and self.element is not None:
            msg = (
                f"reason '{self.reason}' requires element=None (echo-safety "
                "CR-3), but a non-null element phrase was supplied"
            )
            raise ValueError(msg)
        return self


class RequestInterpretation(BaseModel):
    """The per-request reflection object (design section 3.1)."""

    model_config = ConfigDict(extra="forbid")

    interpretation_version: int = INTERPRETATION_VERSION
    layer: Literal["general", "refined"]
    elements: list[InterpretedElement]
    kid_summary: str
    guardian_summary: str
    skeleton_slug: str | None = None
    contract_version: int | None = None
    created_at: datetime


class BandGroup(StrEnum):
    """A coarsened band grouping for template selection (design section 3.3).

    Kid phrasing can simplify for young readers without a per-band template
    explosion: ``young`` = 3-5 / 5-8, ``middle`` = 8-11 / 10-13, ``teen`` =
    13-16 / 16+.
    """

    YOUNG = "young"
    MIDDLE = "middle"
    TEEN = "teen"


_BAND_GROUPS: dict[AgeBand, BandGroup] = {
    AgeBand.BAND_3_5: BandGroup.YOUNG,
    AgeBand.BAND_5_8: BandGroup.YOUNG,
    AgeBand.BAND_8_11: BandGroup.MIDDLE,
    AgeBand.BAND_10_13: BandGroup.MIDDLE,
    AgeBand.BAND_13_16: BandGroup.TEEN,
    AgeBand.BAND_16_PLUS: BandGroup.TEEN,
}


def band_group_for(band: AgeBand) -> BandGroup:
    """Return the template band group for a reading age band.

    Args:
        band: The reading age band.

    Returns:
        The :class:`BandGroup` used to key the template catalog.
    """
    return _BAND_GROUPS[band]


# ---------------------------------------------------------------------------
# Raw input and derived decision value objects (pre-render). Kept as frozen
# dataclasses (not pydantic) because they are internal, un-persisted, and pure.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RawElement:
    """A binder-decomposed requested element before echo-safety/derivation.

    Attributes:
        phrase: The requester-vocabulary phrase (untrusted, premise-derived).
        slot_id: The slot the binder placed it into, or ``None`` if unplaced.
    """

    phrase: str
    slot_id: str | None = None


@dataclass(frozen=True, slots=True)
class ElementDecision:
    """The derived disposition for one element, pre-rendering.

    Attributes:
        element: The echo-safe phrase, or ``None`` when withheld/protected.
        disposition: The chosen :class:`ElementDisposition`.
        reason: The chosen :class:`ReasonCode`.
        slot_id: The bound slot id (BOUND_TO_SLOT only), else ``None``.
        rule: The deciding ``forbid:<bundle>`` rule (BAND_POLICY only), else
            ``None``.
    """

    element: str | None
    disposition: ElementDisposition
    reason: ReasonCode
    slot_id: str | None = None
    rule: str | None = None


# ---------------------------------------------------------------------------
# The echo-safety floor (design section 7.2).
# ---------------------------------------------------------------------------


def sanitize_element(
    phrase: str,
    *,
    band: AgeBand,
    child_names: frozenset[str],
) -> tuple[str | None, ReasonCode | None]:
    """Decide whether ``phrase`` may be echoed back to a child of ``band``.

    The four checks run IN ORDER (design section 7.2); the first failure wins:

    1. Structural: the reused ``validator/slots`` structural-injection block
       (non-empty, single-line/no control chars, charset incl. no ``{}``,
       ``<<``/``>>``, em dash, <= 120 chars, and the fence-marker guard).
    2. Word cap: <= :data:`MAX_ELEMENT_WORDS` words.
    3. Band-mandatory denylist floor for ``band`` unioned with the
       :data:`_ECHO_MINIMUM_BUNDLES` graphic echo minimum (applied even for
       empty-floor bands), via the reused stem matcher.
    4. The deterministic PII egress guard (:func:`assert_prompt_pii_safe`)
       against ``PiiContext(child_names=child_names)``, which also runs the
       unconditional email/phone/address pattern checks.

    A PII hit (check 4) maps to :attr:`ReasonCode.PERSONAL_DETAILS`; every
    other floor failure maps to :attr:`ReasonCode.SAFETY_POLICY`.

    Args:
        phrase: The raw, untrusted requested phrase.
        band: The reading age band the phrase might be echoed to.
        child_names: Real child display names to screen for (the family's, per
            the PII guard's contract; the caller keeps the requesting child's
            OWN name out of this set when self-naming should surface as
            IDENTITY_PROTECTION, see :func:`derive_dispositions`).

    Returns:
        ``(phrase, None)`` when every check passes (the phrase is echo-safe),
        otherwise ``(None, reason)`` with the withholding reason.
    """
    # Check 1: structural-injection block (reused from validator/slots).
    if structural_value_violations(phrase):
        return None, ReasonCode.SAFETY_POLICY

    # Check 2: word cap.
    if len(phrase.split()) > MAX_ELEMENT_WORDS:
        return None, ReasonCode.SAFETY_POLICY

    # Check 3: band denylist floor + graphic echo minimum.
    echo_floor = band_mandatory_bundles(band) | _ECHO_MINIMUM_BUNDLES
    if denylisted_bundles(phrase, echo_floor):
        return None, ReasonCode.SAFETY_POLICY

    # Check 4: deterministic PII egress guard on the phrase itself.
    try:
        assert_prompt_pii_safe(phrase, forbidden=PiiContext(child_names=child_names))
    except ValidationError:
        return None, ReasonCode.PERSONAL_DETAILS

    return phrase, None


def _is_self_naming(phrase: str, self_names: Iterable[str]) -> bool:
    """Return whether ``phrase`` requests the child appear as themselves.

    Detected via the :data:`SELF_REFERENCE_LEXICON` OR the requesting child's
    own registered name(s), both matched on word boundaries with the reused
    normalization (design section 5.3 rule 2).

    Args:
        phrase: The raw requested phrase.
        self_names: The requesting child's own registered display name(s).

    Returns:
        ``True`` if the phrase is a self-naming request.
    """
    if normalized_contains_any(phrase, SELF_REFERENCE_LEXICON):
        return True
    return normalized_contains_any(phrase, self_names)


# ---------------------------------------------------------------------------
# Disposition derivation (design section 5.3): a pure function over WS-2 facts.
# ---------------------------------------------------------------------------


def _matches_content_nogo(phrase: str, content_nogo: Iterable[str]) -> bool:
    """Return whether ``phrase`` matches any guardian banned-theme string.

    Args:
        phrase: The raw requested phrase.
        content_nogo: Guardian banned-theme strings (G2 controls).

    Returns:
        ``True`` if any banned theme matches on word boundaries.
    """
    return normalized_contains_any(phrase, content_nogo)


def _derive_one(  # noqa: PLR0911, PLR0913
    raw: RawElement,
    *,
    band: AgeBand,
    bindings: Mapping[str, str],
    content_nogo: Iterable[str],
    child_names: frozenset[str],
    self_names: frozenset[str],
    adapted_slot_ids: frozenset[str],
) -> ElementDecision:
    """Derive one element's :class:`ElementDecision` by the 7 precedence rules.

    Precedence (design section 5.3), most-protective first. Within "echo-safety
    first", the STRUCTURAL limb precedes self-naming (an injection/malformed
    phrase is always SAFETY_POLICY, never reinterpreted), while the PII limb
    FOLLOWS self-naming so the requesting child's own name lands the more
    specific IDENTITY_PROTECTION rather than the generic PERSONAL_DETAILS. The
    band-floor limb of the echo floor is expressed through rule 5 (BAND_POLICY)
    so the guardian sees the precise reason; the element is still withheld
    (element=None) exactly as the floor requires, so a band-denylisted phrase
    is never echoed.

    Args:
        raw: The element phrase plus the slot the binder placed it into.
        band: The contract's reading age band.
        bindings: The final validated ``{slot_id: value}`` map.
        content_nogo: Guardian banned-theme strings.
        child_names: Family child names for the PII floor (excluding the
            requesting child's own name when self-naming should surface).
        self_names: The requesting child's own registered name(s).
        adapted_slot_ids: Slots rejected on the first bind attempt and
            corrected on retry (the narrow ADAPTED trigger, OQ-7).

    Returns:
        The derived :class:`ElementDecision`.
    """
    phrase = raw.phrase

    # Rule 1 (structural limb): a malformed/injection/over-long phrase is
    # unconditionally withheld as SAFETY_POLICY, ahead of every other reading.
    if structural_value_violations(phrase) or len(phrase.split()) > MAX_ELEMENT_WORDS:
        return ElementDecision(
            None, ElementDisposition.SET_ASIDE, ReasonCode.SAFETY_POLICY
        )

    # Rule 2 (self-naming): checked before the PII limb so the requesting
    # child's own name is IDENTITY_PROTECTION, not generic PERSONAL_DETAILS.
    if _is_self_naming(phrase, self_names):
        return ElementDecision(
            None, ElementDisposition.SET_ASIDE, ReasonCode.IDENTITY_PROTECTION
        )

    # Rule 1 (PII limb): any other real personal data withholds as
    # PERSONAL_DETAILS. Uses the full echo floor so a band-denylisted phrase is
    # also caught here as SAFETY_POLICY before it can be described as built in.
    safe, floor_reason = sanitize_element(phrase, band=band, child_names=child_names)
    if floor_reason is ReasonCode.PERSONAL_DETAILS:
        return ElementDecision(
            None, ElementDisposition.SET_ASIDE, ReasonCode.PERSONAL_DETAILS
        )

    # Rule 3 (bound to slot): only when echo-safe (rule 1 already withheld an
    # unsafe cousin above); an unsafe phrase is never described as built in.
    if safe is not None and raw.slot_id is not None and raw.slot_id in bindings:
        disposition = (
            ElementDisposition.ADAPTED
            if raw.slot_id in adapted_slot_ids
            else ElementDisposition.BUILT_IN
        )
        return ElementDecision(
            safe, disposition, ReasonCode.BOUND_TO_SLOT, slot_id=raw.slot_id
        )

    # Rule 4 (guardian control): a banned-theme match, element echoed only if
    # echo-safe.
    if _matches_content_nogo(phrase, content_nogo):
        return ElementDecision(
            safe, ElementDisposition.SET_ASIDE, ReasonCode.GUARDIAN_CONTROL
        )

    # Rule 5 (band policy): a band-floor bundle hit. The phrase is not
    # echo-safe (the floor withheld it: safe is None), so element=None with the
    # precise forbid:<bundle> rule.
    band_hits = denylisted_bundles(phrase, band_mandatory_bundles(band))
    if band_hits:
        bundle_id = min(band_hits)
        return ElementDecision(
            None,
            ElementDisposition.SET_ASIDE,
            ReasonCode.BAND_POLICY,
            rule=f"forbid:{bundle_id}",
        )

    # Any residual echo-floor withhold that was neither PII nor a band hit
    # (e.g. the graphic echo minimum on an empty-floor band): SAFETY_POLICY.
    if safe is None:
        return ElementDecision(
            None, ElementDisposition.SET_ASIDE, ReasonCode.SAFETY_POLICY
        )

    # Rule 6 (structure fixed): a request to choose the ending/fate.
    if normalized_contains_any(phrase, ENDING_FATE_LEXICON):
        return ElementDecision(
            safe, ElementDisposition.SET_ASIDE, ReasonCode.STRUCTURE_FIXED
        )

    # Rule 7: benign misfit; this tree had no spot for it.
    return ElementDecision(
        safe, ElementDisposition.SET_ASIDE, ReasonCode.NOT_THIS_STORY_KIND
    )


def derive_dispositions(  # noqa: PLR0913
    elements: Sequence[RawElement],
    *,
    band: AgeBand,
    bindings: Mapping[str, str],
    content_nogo: Iterable[str] = (),
    child_names: frozenset[str] = _EMPTY_STR_SET,
    self_names: frozenset[str] = _EMPTY_STR_SET,
    adapted_slot_ids: frozenset[str] = _EMPTY_STR_SET,
) -> list[ElementDecision]:
    """Derive a disposition per element by the 7 precedence rules (section 5.3).

    Pure and deterministic: the same inputs always return an equal list, in the
    input order. Never enforcement (the deterministic slot gate already
    enforced); a lexical miss is imprecise, never unsafe, because the
    precedence puts the most-protective true reason first.

    Args:
        elements: The binder-decomposed requested elements (phrase + slot).
        band: The contract's reading age band.
        bindings: The final validated ``{slot_id: value}`` map.
        content_nogo: Guardian banned-theme strings (G2 controls).
        child_names: Family child names for the echo-floor PII screen; keep the
            requesting child's OWN name out of this set so a self-name surfaces
            as IDENTITY_PROTECTION (it is withheld either way).
        self_names: The requesting child's own registered name(s), for the
            self-naming rule.
        adapted_slot_ids: Slots corrected on bind retry (the narrow ADAPTED
            trigger, OQ-7); default empty means every placed element is
            ``BUILT_IN``.

    Returns:
        One :class:`ElementDecision` per input element, in order.
    """
    return [
        _derive_one(
            raw,
            band=band,
            bindings=bindings,
            content_nogo=content_nogo,
            child_names=child_names,
            self_names=self_names,
            adapted_slot_ids=adapted_slot_ids,
        )
        for raw in elements
    ]


# ---------------------------------------------------------------------------
# The template catalog and pure renderer (design section 3.3).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _TemplatePair:
    """The four rendered forms for one (disposition, reason, band_group) key.

    Each register has a with-``{element}`` variant (used when the echo-safe
    phrase is present) and a without variant (used when ``element is None``).
    No form contains an em dash.
    """

    kid_with: str
    kid_without: str
    guardian_with: str
    guardian_without: str


# Generic fallback used when a (disposition, reason, band_group) key is missing
# from the catalog: never raises, logs once, keeps the reflection honest.
_GENERIC_PAIR = _TemplatePair(
    kid_with="We looked at {element} for your story.",
    kid_without="We looked at one part of your idea for your story.",
    guardian_with=("'{element}' was recorded as {disposition} ({reason})."),
    guardian_without=("One element was recorded as {disposition} ({reason})."),
)


def _forms(
    kid_with: str, kid_without: str, guardian_with: str, guardian_without: str
) -> _TemplatePair:
    """Build a template pair (thin constructor to keep the catalog readable)."""
    return _TemplatePair(kid_with, kid_without, guardian_with, guardian_without)


# The catalog: one _TemplatePair per (disposition, reason, band_group). Copy is
# seeded from the design section 3.3 table, simplified for the young group. No
# em dash (U+2014) appears in any string.
_CATALOG: dict[tuple[ElementDisposition, ReasonCode, BandGroup], _TemplatePair] = {}


def _register(  # noqa: PLR0913
    disposition: ElementDisposition,
    reason: ReasonCode,
    *,
    young: _TemplatePair,
    middle: _TemplatePair,
    teen: _TemplatePair,
) -> None:
    """Register the three band-group template pairs for one (disposition, reason)."""
    _CATALOG[disposition, reason, BandGroup.YOUNG] = young
    _CATALOG[disposition, reason, BandGroup.MIDDLE] = middle
    _CATALOG[disposition, reason, BandGroup.TEEN] = teen


# Template strings reused across band groups (and, for several reasons, across
# the with-element and without-element variants too, since guardian copy
# never echoes untrusted element text and several kid-facing lines are
# identical across bands). Named by (audience, reason[, disposition when the
# reason spans more than one], with/without element when both exist) so each
# occurrence's meaning stays traceable; grouped here instead of inlined below
# to satisfy S1192 (no duplicated string literal).
_GUARDIAN_BAND_PROMISE = (
    "Band promise for {band}: content kept within the age-band guarantee."
)
_GUARDIAN_BAND_POLICY_WITH_ELEMENT = (
    "'{element}' was set aside: it exceeds the {band} content policy ({rule})."
)
_GUARDIAN_BAND_POLICY_WITHOUT_ELEMENT = (
    "An element was set aside: it exceeds the {band} content policy ({rule})."
)
_GUARDIAN_CONTROL_WITH_ELEMENT = (
    "'{element}' was set aside by this profile's content controls (banned theme)."
)
_GUARDIAN_CONTROL_WITHOUT_ELEMENT = (
    "An element was set aside by this profile's content controls (banned theme)."
)
_KID_GUARDIAN_CONTROL = (
    "That part is on your family's not-right-now list, so we left it out."
)
_KID_STRUCTURE_FIXED = (
    "Every adventure here ends a way that is fair and safe, so we picked the ending."
)
_GUARDIAN_STRUCTURE_FIXED_WITH_ELEMENT = (
    "'{element}' conflicts with the story's fixed ending set; endings are "
    "structural and not requestable (ADR-011/PL-15)."
)
_GUARDIAN_STRUCTURE_FIXED_WITHOUT_ELEMENT = (
    "An element conflicts with the story's fixed ending set; endings are "
    "structural and not requestable (ADR-011/PL-15)."
)
_GUARDIAN_NOT_THIS_STORY_KIND_WITH_ELEMENT = (
    "'{element}' had no slot in skeleton '{skeleton_slug}'; it was not woven in."
)
_GUARDIAN_NOT_THIS_STORY_KIND_WITHOUT_ELEMENT = (
    "An element had no slot in skeleton '{skeleton_slug}'; it was not woven in."
)
_KID_SAFETY_POLICY_SET_ASIDE = (
    "One part of your idea is not something we can put in a story."
)
_GUARDIAN_SAFETY_POLICY_SET_ASIDE = (
    "An element was withheld by the safety policy; the element text is not echoed."
)
_GUARDIAN_PERSONAL_DETAILS_SET_ASIDE = (
    "An element contained personal details (a real name, email, phone, or "
    "address); it was withheld and not echoed."
)
_KID_PERSONAL_DETAILS_SET_ASIDE = (
    "Story wishes stay about made-up things, not real names or numbers."
)
_GUARDIAN_IDENTITY_PROTECTION = (
    "The request asked to use the child's real name/self as the protagonist; "
    "self-naming is disallowed by design (Route A). A fictional protagonist "
    "was used."
)
_KID_NO_CONFORMING_BINDING = (
    "We could not build this wish into any of our adventures yet. Try "
    "changing it a little!"
)
_GUARDIAN_NO_CONFORMING_BINDING = (
    "No skeleton in the request's cell could bind this theme; see the "
    "recorded violations."
)
_KID_PERSONAL_DETAILS_CANNOT_CARRY = (
    "Story wishes cannot include real names, phone numbers, or addresses. Ask a "
    "grown-up to help you send it again without them."
)
_GUARDIAN_PERSONAL_DETAILS_CANNOT_CARRY = (
    "The request contains personal details (a real name, email, phone, or "
    "address). Please remove them and resubmit; this is a privacy block, not a "
    "theme limitation."
)
_KID_SAFETY_POLICY_CANNOT_CARRY = (
    "We could not use this story wish. Try a different idea!"
)
_GUARDIAN_SAFETY_POLICY_CANNOT_CARRY = (
    "The request was blocked by the safety screen; no request text is echoed."
)


_register(
    ElementDisposition.BUILT_IN,
    ReasonCode.BOUND_TO_SLOT,
    young=_forms(
        "Yay! Your story has {element} in it!",
        "Yay! We put your idea in the story!",
        "'{element}' was built into the story (slot {slot_id}).",
        "An element was built into the story (slot {slot_id}).",
    ),
    middle=_forms(
        "Your story has {element} in it!",
        "We built your idea into the story.",
        "'{element}' was built into the story (slot {slot_id}).",
        "An element was built into the story (slot {slot_id}).",
    ),
    teen=_forms(
        "We wove {element} into your story.",
        "We wove your idea into the story.",
        "'{element}' was bound into the story (slot {slot_id}).",
        "An element was bound into the story (slot {slot_id}).",
    ),
)

_register(
    ElementDisposition.ADAPTED,
    ReasonCode.BOUND_TO_SLOT,
    young=_forms(
        "We put {element} in, with a friendly twist!",
        "We put your idea in, with a friendly twist!",
        "'{element}' was built in with an adjustment to fit the story (slot {slot_id}).",
        "An element was built in with an adjustment to fit the story (slot {slot_id}).",
    ),
    middle=_forms(
        "We built in {element}, tweaked a little to fit.",
        "We built in your idea, tweaked a little to fit.",
        "'{element}' was built in, adapted on retry to satisfy the slot (slot {slot_id}).",
        "An element was built in, adapted on retry to satisfy the slot (slot {slot_id}).",
    ),
    teen=_forms(
        "We wove in {element}, adapted to fit the story.",
        "We wove in your idea, adapted to fit the story.",
        "'{element}' was bound after a retry-time adaptation (slot {slot_id}).",
        "An element was bound after a retry-time adaptation (slot {slot_id}).",
    ),
)

_register(
    ElementDisposition.BUILT_IN,
    ReasonCode.STORY_FIT,
    young=_forms(
        "This will be a friendly adventure that always ends safe.",
        "This will be a friendly adventure that always ends safe.",
        "Band promise for {band}: a friendly adventure with a safe ending.",
        "Band promise for {band}: a friendly adventure with a safe ending.",
    ),
    middle=_forms(
        "This adventure fits stories made for readers your age.",
        "This adventure fits stories made for readers your age.",
        _GUARDIAN_BAND_PROMISE,
        _GUARDIAN_BAND_PROMISE,
    ),
    teen=_forms(
        "This adventure fits stories made for your reading level.",
        "This adventure fits stories made for your reading level.",
        _GUARDIAN_BAND_PROMISE,
        _GUARDIAN_BAND_PROMISE,
    ),
)

_register(
    ElementDisposition.SET_ASIDE,
    ReasonCode.BAND_POLICY,
    young=_forms(
        "We saved {element} for when you are older. This story stays friendly.",
        "We saved one idea for when you are older. This story stays friendly.",
        _GUARDIAN_BAND_POLICY_WITH_ELEMENT,
        _GUARDIAN_BAND_POLICY_WITHOUT_ELEMENT,
    ),
    middle=_forms(
        "We saved {element} for when you are older. This story stays friendly.",
        "We saved one part of your idea for when you are older.",
        _GUARDIAN_BAND_POLICY_WITH_ELEMENT,
        _GUARDIAN_BAND_POLICY_WITHOUT_ELEMENT,
    ),
    teen=_forms(
        "We kept {element} out to stay within this reading level.",
        "We kept one part of your idea out to stay within this reading level.",
        _GUARDIAN_BAND_POLICY_WITH_ELEMENT,
        _GUARDIAN_BAND_POLICY_WITHOUT_ELEMENT,
    ),
)

_register(
    ElementDisposition.SET_ASIDE,
    ReasonCode.GUARDIAN_CONTROL,
    young=_forms(
        "That part is on your family's not-right-now list.",
        "That part is on your family's not-right-now list.",
        _GUARDIAN_CONTROL_WITH_ELEMENT,
        _GUARDIAN_CONTROL_WITHOUT_ELEMENT,
    ),
    middle=_forms(
        _KID_GUARDIAN_CONTROL,
        _KID_GUARDIAN_CONTROL,
        _GUARDIAN_CONTROL_WITH_ELEMENT,
        _GUARDIAN_CONTROL_WITHOUT_ELEMENT,
    ),
    teen=_forms(
        _KID_GUARDIAN_CONTROL,
        _KID_GUARDIAN_CONTROL,
        _GUARDIAN_CONTROL_WITH_ELEMENT,
        _GUARDIAN_CONTROL_WITHOUT_ELEMENT,
    ),
)

_register(
    ElementDisposition.SET_ASIDE,
    ReasonCode.STRUCTURE_FIXED,
    young=_forms(
        _KID_STRUCTURE_FIXED,
        _KID_STRUCTURE_FIXED,
        _GUARDIAN_STRUCTURE_FIXED_WITH_ELEMENT,
        _GUARDIAN_STRUCTURE_FIXED_WITHOUT_ELEMENT,
    ),
    middle=_forms(
        _KID_STRUCTURE_FIXED,
        _KID_STRUCTURE_FIXED,
        _GUARDIAN_STRUCTURE_FIXED_WITH_ELEMENT,
        _GUARDIAN_STRUCTURE_FIXED_WITHOUT_ELEMENT,
    ),
    teen=_forms(
        "The endings here are fixed by the story's shape, so that part was set by us.",
        "The endings here are fixed by the story's shape, so that part was set by us.",
        _GUARDIAN_STRUCTURE_FIXED_WITH_ELEMENT,
        _GUARDIAN_STRUCTURE_FIXED_WITHOUT_ELEMENT,
    ),
)

_register(
    ElementDisposition.SET_ASIDE,
    ReasonCode.NOT_THIS_STORY_KIND,
    young=_forms(
        "This adventure did not have a spot for {element}, so we left it out.",
        "This adventure did not have a spot for that part, so we left it out.",
        _GUARDIAN_NOT_THIS_STORY_KIND_WITH_ELEMENT,
        _GUARDIAN_NOT_THIS_STORY_KIND_WITHOUT_ELEMENT,
    ),
    middle=_forms(
        "This adventure did not have a spot for {element}, so we left it out.",
        "This adventure did not have a spot for that part, so we left it out.",
        _GUARDIAN_NOT_THIS_STORY_KIND_WITH_ELEMENT,
        _GUARDIAN_NOT_THIS_STORY_KIND_WITHOUT_ELEMENT,
    ),
    teen=_forms(
        "This adventure did not have a place for {element}, so we left it out.",
        "This adventure did not have a place for that part, so we left it out.",
        _GUARDIAN_NOT_THIS_STORY_KIND_WITH_ELEMENT,
        _GUARDIAN_NOT_THIS_STORY_KIND_WITHOUT_ELEMENT,
    ),
)

_register(
    ElementDisposition.SET_ASIDE,
    ReasonCode.SAFETY_POLICY,
    young=_forms(
        _KID_SAFETY_POLICY_SET_ASIDE,
        _KID_SAFETY_POLICY_SET_ASIDE,
        _GUARDIAN_SAFETY_POLICY_SET_ASIDE,
        _GUARDIAN_SAFETY_POLICY_SET_ASIDE,
    ),
    middle=_forms(
        _KID_SAFETY_POLICY_SET_ASIDE,
        _KID_SAFETY_POLICY_SET_ASIDE,
        _GUARDIAN_SAFETY_POLICY_SET_ASIDE,
        _GUARDIAN_SAFETY_POLICY_SET_ASIDE,
    ),
    teen=_forms(
        _KID_SAFETY_POLICY_SET_ASIDE,
        _KID_SAFETY_POLICY_SET_ASIDE,
        _GUARDIAN_SAFETY_POLICY_SET_ASIDE,
        _GUARDIAN_SAFETY_POLICY_SET_ASIDE,
    ),
)

_register(
    ElementDisposition.SET_ASIDE,
    ReasonCode.PERSONAL_DETAILS,
    young=_forms(
        "Story wishes stay about made-up things, not real-life details.",
        "Story wishes stay about made-up things, not real-life details.",
        _GUARDIAN_PERSONAL_DETAILS_SET_ASIDE,
        _GUARDIAN_PERSONAL_DETAILS_SET_ASIDE,
    ),
    middle=_forms(
        _KID_PERSONAL_DETAILS_SET_ASIDE,
        _KID_PERSONAL_DETAILS_SET_ASIDE,
        _GUARDIAN_PERSONAL_DETAILS_SET_ASIDE,
        _GUARDIAN_PERSONAL_DETAILS_SET_ASIDE,
    ),
    teen=_forms(
        _KID_PERSONAL_DETAILS_SET_ASIDE,
        _KID_PERSONAL_DETAILS_SET_ASIDE,
        _GUARDIAN_PERSONAL_DETAILS_SET_ASIDE,
        _GUARDIAN_PERSONAL_DETAILS_SET_ASIDE,
    ),
)

_register(
    ElementDisposition.SET_ASIDE,
    ReasonCode.IDENTITY_PROTECTION,
    young=_forms(
        "Heroes in our stories always have made-up names, so we chose one for you!",
        "Heroes in our stories always have made-up names, so we chose one for you!",
        _GUARDIAN_IDENTITY_PROTECTION,
        _GUARDIAN_IDENTITY_PROTECTION,
    ),
    middle=_forms(
        "Heroes in our stories always have made-up names, so we chose one for this adventure!",
        "Heroes in our stories always have made-up names, so we chose one for this adventure!",
        _GUARDIAN_IDENTITY_PROTECTION,
        _GUARDIAN_IDENTITY_PROTECTION,
    ),
    teen=_forms(
        "Heroes in our stories always use made-up names, so we chose one for this adventure.",
        "Heroes in our stories always use made-up names, so we chose one for this adventure.",
        _GUARDIAN_IDENTITY_PROTECTION,
        _GUARDIAN_IDENTITY_PROTECTION,
    ),
)

_register(
    ElementDisposition.CANNOT_CARRY,
    ReasonCode.NO_CONFORMING_BINDING,
    young=_forms(
        _KID_NO_CONFORMING_BINDING,
        _KID_NO_CONFORMING_BINDING,
        _GUARDIAN_NO_CONFORMING_BINDING,
        _GUARDIAN_NO_CONFORMING_BINDING,
    ),
    middle=_forms(
        _KID_NO_CONFORMING_BINDING,
        _KID_NO_CONFORMING_BINDING,
        _GUARDIAN_NO_CONFORMING_BINDING,
        _GUARDIAN_NO_CONFORMING_BINDING,
    ),
    teen=_forms(
        "We could not build this wish into any of our adventures yet. Try changing it a little.",
        "We could not build this wish into any of our adventures yet. Try changing it a little.",
        _GUARDIAN_NO_CONFORMING_BINDING,
        _GUARDIAN_NO_CONFORMING_BINDING,
    ),
)

_register(
    ElementDisposition.CANNOT_CARRY,
    ReasonCode.PERSONAL_DETAILS,
    young=_forms(
        _KID_PERSONAL_DETAILS_CANNOT_CARRY,
        _KID_PERSONAL_DETAILS_CANNOT_CARRY,
        _GUARDIAN_PERSONAL_DETAILS_CANNOT_CARRY,
        _GUARDIAN_PERSONAL_DETAILS_CANNOT_CARRY,
    ),
    middle=_forms(
        _KID_PERSONAL_DETAILS_CANNOT_CARRY,
        _KID_PERSONAL_DETAILS_CANNOT_CARRY,
        _GUARDIAN_PERSONAL_DETAILS_CANNOT_CARRY,
        _GUARDIAN_PERSONAL_DETAILS_CANNOT_CARRY,
    ),
    teen=_forms(
        (
            "Story wishes cannot include real names, phone numbers, or addresses. Please "
            "remove them and send it again."
        ),
        (
            "Story wishes cannot include real names, phone numbers, or addresses. Please "
            "remove them and send it again."
        ),
        _GUARDIAN_PERSONAL_DETAILS_CANNOT_CARRY,
        _GUARDIAN_PERSONAL_DETAILS_CANNOT_CARRY,
    ),
)

_register(
    ElementDisposition.CANNOT_CARRY,
    ReasonCode.SAFETY_POLICY,
    young=_forms(
        _KID_SAFETY_POLICY_CANNOT_CARRY,
        _KID_SAFETY_POLICY_CANNOT_CARRY,
        _GUARDIAN_SAFETY_POLICY_CANNOT_CARRY,
        _GUARDIAN_SAFETY_POLICY_CANNOT_CARRY,
    ),
    middle=_forms(
        _KID_SAFETY_POLICY_CANNOT_CARRY,
        _KID_SAFETY_POLICY_CANNOT_CARRY,
        _GUARDIAN_SAFETY_POLICY_CANNOT_CARRY,
        _GUARDIAN_SAFETY_POLICY_CANNOT_CARRY,
    ),
    teen=_forms(
        "We could not use this story wish. Try a different idea.",
        "We could not use this story wish. Try a different idea.",
        _GUARDIAN_SAFETY_POLICY_CANNOT_CARRY,
        _GUARDIAN_SAFETY_POLICY_CANNOT_CARRY,
    ),
)


def _render_pair(  # noqa: PLR0913
    disposition: ElementDisposition,
    reason: ReasonCode,
    group: BandGroup,
    *,
    element: str | None,
    slot_id: str | None,
    rule: str | None,
    band: AgeBand,
    skeleton_slug: str | None,
) -> tuple[str, str]:
    """Render the (kid_text, guardian_text) for one decided element.

    Selects the catalog entry for ``(disposition, reason, group)``, falling
    back to :data:`_GENERIC_PAIR` (logged, never raised) on a missing key, then
    picks the with-``{element}`` variant when ``element`` is present or the
    without variant when it is ``None``, and formats the shared field set.

    Args:
        disposition: The element's disposition.
        reason: The element's reason code.
        group: The band group keying the catalog.
        element: The echo-safe phrase, or ``None``.
        slot_id: The bound slot id, or ``None``.
        rule: The deciding ``forbid:<bundle>`` rule, or ``None``.
        band: The reading age band (for the ``{band}`` field).
        skeleton_slug: The skeleton slug (for the ``{skeleton_slug}`` field).

    Returns:
        The rendered ``(kid_text, guardian_text)`` pair.
    """
    pair = _CATALOG.get((disposition, reason, group))
    if pair is None:
        _logger.warning(
            "interpretation_template_missing",
            disposition=disposition.value,
            reason=reason.value,
            band_group=group.value,
        )
        pair = _GENERIC_PAIR

    fields: dict[str, str] = {
        "element": element if element is not None else "",
        "slot_id": slot_id if slot_id is not None else "unknown",
        "rule": rule if rule is not None else "band policy",
        "band": band.value,
        "skeleton_slug": skeleton_slug
        if skeleton_slug is not None
        else "this adventure",
        "disposition": disposition.value,
        "reason": reason.value,
    }

    if element is not None:
        return pair.kid_with.format(**fields), pair.guardian_with.format(**fields)
    return pair.kid_without.format(**fields), pair.guardian_without.format(**fields)


def _kid_summary(decisions: Sequence[ElementDecision]) -> str:
    """Build the kid-facing count summary (design section 3.3).

    Args:
        decisions: The derived element decisions.

    Returns:
        A friendly one-line summary counting built-in vs set-aside vs
        cannot-carry dispositions.
    """
    built = sum(
        1
        for d in decisions
        if d.disposition in {ElementDisposition.BUILT_IN, ElementDisposition.ADAPTED}
    )
    set_aside = sum(
        1 for d in decisions if d.disposition is ElementDisposition.SET_ASIDE
    )
    cannot = sum(
        1 for d in decisions if d.disposition is ElementDisposition.CANNOT_CARRY
    )

    if cannot and not built and not set_aside:
        return "We could not build this wish yet. Try changing it a little!"

    parts: list[str] = []
    if built:
        parts.append(
            f"We built in {built} of your ideas"
            if built != 1
            else "We built in 1 of your ideas"
        )
    if set_aside:
        saved = (
            f"saved {set_aside} for later" if set_aside != 1 else "saved 1 for later"
        )
        parts.append(saved if parts else f"We {saved}")
    if not parts:
        return "We are getting your adventure ready!"
    return " and ".join(parts) + "."


def _guardian_summary(
    decisions: Sequence[ElementDecision], skeleton_slug: str | None
) -> str:
    """Build the guardian-facing summary with the slug and rule list (3.3).

    Args:
        decisions: The derived element decisions.
        skeleton_slug: The skeleton slug, or ``None`` (general/degraded layer).

    Returns:
        A one-line guardian summary: counts, plus the deciding rules seen.
    """
    built = sum(
        1
        for d in decisions
        if d.disposition in {ElementDisposition.BUILT_IN, ElementDisposition.ADAPTED}
    )
    set_aside = sum(
        1 for d in decisions if d.disposition is ElementDisposition.SET_ASIDE
    )
    cannot = sum(
        1 for d in decisions if d.disposition is ElementDisposition.CANNOT_CARRY
    )
    rules = sorted({d.rule for d in decisions if d.rule is not None})

    slug_part = f"Skeleton '{skeleton_slug}': " if skeleton_slug is not None else ""
    summary = (
        f"{slug_part}{built} built in, {set_aside} set aside, "
        f"{cannot} could not be carried."
    )
    if rules:
        summary += f" Rules: {', '.join(rules)}."
    return summary


def render_interpretation(  # noqa: PLR0913
    elements: Sequence[ElementDecision],
    *,
    band: AgeBand,
    layer: Literal["general", "refined"],
    created_at: datetime,
    skeleton_slug: str | None = None,
    contract_version: int | None = None,
) -> RequestInterpretation:
    """Render a :class:`RequestInterpretation` from decided elements.

    Pure: builds ``kid_text`` / ``guardian_text`` for every element from the
    template catalog (never model output), counts dispositions for
    ``kid_summary``, and adds the slug plus rule list for ``guardian_summary``.
    ``created_at`` is supplied by the caller so the module reads no wall clock.

    Args:
        elements: The derived :class:`ElementDecision` values (see
            :func:`derive_dispositions`).
        band: The reading age band, used to select the template band group.
        layer: ``"general"`` (submission-time) or ``"refined"`` (contract-
            grounded, fill-time).
        created_at: The caller-supplied creation timestamp (never
            ``datetime.now()`` here; the module stays pure).
        skeleton_slug: The skeleton slug (refined/degraded layer only).
        contract_version: The theme-contract version (refined layer only).

    Returns:
        The assembled, echo-safe :class:`RequestInterpretation`.
    """
    group = band_group_for(band)
    rendered: list[InterpretedElement] = []
    for decision in elements:
        kid_text, guardian_text = _render_pair(
            decision.disposition,
            decision.reason,
            group,
            element=decision.element,
            slot_id=decision.slot_id,
            rule=decision.rule,
            band=band,
            skeleton_slug=skeleton_slug,
        )
        rendered.append(
            InterpretedElement(
                element=decision.element,
                disposition=decision.disposition,
                reason=decision.reason,
                slot_id=decision.slot_id,
                rule=decision.rule,
                kid_text=kid_text,
                guardian_text=guardian_text,
            )
        )

    return RequestInterpretation(
        interpretation_version=INTERPRETATION_VERSION,
        layer=layer,
        elements=rendered,
        kid_summary=_kid_summary(elements),
        guardian_summary=_guardian_summary(elements, skeleton_slug),
        skeleton_slug=skeleton_slug,
        contract_version=contract_version,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# The general layer: submission-time interpretation (D3, design section 4).
#
# Runs inside the two create endpoints immediately after screening, with NO
# LLM call and NO skeleton knowledge: the "buildable now" half of K19. It never
# attempts element extraction from the premise (there is no contract to
# validate extracted phrases against at the request-scoped endpoint), so the
# only premise-derived free text it can ever echo is a GUARDIAN's own
# banned-theme string that the premise trips, and even that passes through the
# echo floor for uniformity. The blocked path reads NO premise content at all
# (CR-1).
# ---------------------------------------------------------------------------


class _ScreeningFlag(Protocol):
    """The minimal shape :func:`build_general_interpretation` needs of a flag.

    Structural (read-only) so the pure module never imports the heavier
    ``story_requests.screening`` (httpx, api.schemas) at runtime: any object
    exposing a ``category`` string satisfies it (e.g. ``StoryRequestFlag``).
    """

    @property
    def category(self) -> str: ...


class _ScreeningLike(Protocol):
    """The minimal ``ScreeningResult`` shape the general layer consumes.

    ``blocked`` gates the CR-1 generic path; ``flags`` supplies the advisory
    classifier categories. Read-only members keep the match covariant so a
    concrete ``ScreeningResult`` (``flags: list[StoryRequestFlag]``) satisfies
    it without a runtime import.
    """

    @property
    def blocked(self) -> bool: ...

    @property
    def flags(self) -> Sequence[_ScreeningFlag]: ...


def _inject_advisory_categories(
    interpretation: RequestInterpretation, categories: Sequence[str | None]
) -> RequestInterpretation:
    """Append each advisory element's classifier category to guardian_text only.

    The category is classifier vocabulary, never premise text (design section
    4), so it is safe in the guardian register and MUST NOT reach kid_text;
    only ``guardian_text`` is augmented. ``categories`` is aligned by index
    with ``interpretation.elements`` (``None`` = leave the element untouched).

    Args:
        interpretation: The rendered general-layer interpretation.
        categories: Per-element advisory category, or ``None`` to leave as-is.

    Returns:
        A copy whose advisory elements carry the category in guardian_text.
    """
    updated: list[InterpretedElement] = []
    for element, category in zip(interpretation.elements, categories, strict=True):
        if category is None:
            updated.append(element)
            continue
        updated.append(
            element.model_copy(
                update={
                    "guardian_text": (
                        f"{element.guardian_text} Advisory category: {category}."
                    )
                }
            )
        )
    return interpretation.model_copy(update={"elements": updated})


def build_general_interpretation(  # noqa: PLR0913
    *,
    screening: _ScreeningLike,
    band: AgeBand,
    banned_themes: Sequence[str],
    premise: str,
    created_at: datetime,
) -> RequestInterpretation:
    """Build the submission-time general interpretation (design section 4, D3).

    Deterministic and LLM-free. Emits, in order:

    - **Blocked screening:** exactly one ``(CANNOT_CARRY, SAFETY_POLICY,
      element=None)`` element plus summaries, and reads NO ``premise`` content
      whatsoever (CR-1): the blocked general layer is generic by construction,
      matching the ``request_text=None`` redaction rule for blocked rows.
    - **Non-blocked:** one ``(SET_ASIDE, SAFETY_POLICY, element=None)`` per
      advisory flag category (the category is classifier vocabulary and is
      appended to ``guardian_text`` only, never echoed to the kid); one
      ``(SET_ASIDE, GUARDIAN_CONTROL)`` per ``banned_themes`` entry the premise
      trips on a word boundary (the echoed element is the GUARDIAN's own
      banned-theme string, still run through :func:`sanitize_element`, falling
      back to ``element=None`` if it somehow fails the floor); and always
      exactly one ``(BUILT_IN, STORY_FIT, element=None)`` band-expectation
      element whose text states the band promise (grounded in the age band, not
      the premise).

    Args:
        screening: The submission screening outcome (blocked flag + advisory
            flags); only ``.blocked`` and ``.flags[].category`` are read.
        band: The request's reading age band.
        banned_themes: The requesting profile's G2 banned-theme strings, or an
            empty sequence when no profile exists.
        premise: The raw request text. Matched (word boundary) against
            ``banned_themes`` on the NON-blocked path only; never read when
            ``screening.blocked`` is true (CR-1).
        created_at: The caller-supplied creation timestamp (endpoint clock).

    Returns:
        The echo-safe general-layer :class:`RequestInterpretation`.
    """
    if screening.blocked:
        # CR-1: do NOT read `premise` here. A blocked row's general layer is a
        # single generic safety element with no premise-derived content.
        blocked_decision = ElementDecision(
            None,
            ElementDisposition.CANNOT_CARRY,
            ReasonCode.SAFETY_POLICY,
        )
        return render_interpretation(
            [blocked_decision], band=band, layer="general", created_at=created_at
        )

    decisions: list[ElementDecision] = []
    # Aligned by index with `decisions`: the classifier category to append to
    # an advisory SAFETY_POLICY element's guardian_text, else None.
    advisory_categories: list[str | None] = []

    # One SET_ASIDE / SAFETY_POLICY per advisory flag category (dedup, ordered).
    seen_categories: set[str] = set()
    for flag in screening.flags:
        category = flag.category
        if category in seen_categories:
            continue
        seen_categories.add(category)
        decisions.append(
            ElementDecision(
                None, ElementDisposition.SET_ASIDE, ReasonCode.SAFETY_POLICY
            )
        )
        advisory_categories.append(category)

    # One SET_ASIDE / GUARDIAN_CONTROL per banned theme the premise trips.
    for theme in banned_themes:
        if not normalized_contains_any(premise, (theme,)):
            continue
        # The echoed phrase is the guardian's own banned-theme string (guardian
        # vocabulary, not premise text); it passes the echo floor trivially, but
        # fall back to element=None if it somehow does not (e.g. a guardian
        # theme that itself trips the band floor).
        safe, _ = sanitize_element(theme, band=band, child_names=_EMPTY_STR_SET)
        decisions.append(
            ElementDecision(
                safe, ElementDisposition.SET_ASIDE, ReasonCode.GUARDIAN_CONTROL
            )
        )
        advisory_categories.append(None)

    # Always exactly one band-expectation element (the band promise, grounded in
    # the age band via the template catalog, never in the premise).
    decisions.append(
        ElementDecision(None, ElementDisposition.BUILT_IN, ReasonCode.STORY_FIT)
    )
    advisory_categories.append(None)

    interpretation = render_interpretation(
        decisions, band=band, layer="general", created_at=created_at
    )
    return _inject_advisory_categories(interpretation, advisory_categories)
