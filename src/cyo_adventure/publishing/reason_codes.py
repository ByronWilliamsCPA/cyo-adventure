"""The closed send-back reason vocabulary, owned by the domain.

This module exists so the vocabulary has one home that both the API boundary
and the publishing service can reach. It previously lived in ``api/schemas.py``,
so ``publishing/service.py::send_back`` took an unvalidated ``str`` and
documented the gap rather than closing it. Importing it back the other way was
not an option: ``api/schemas.py`` is what the API boundary validates against and
what the OpenAPI schema is generated from, so ``publishing`` importing from it
while it imports the vocabulary would be a cycle. The dependency now runs one
way: ``api/schemas.py`` imports the vocabulary from here.

Note the narrower claim. This is not "the domain never imports from the API
layer", which this package does not honour: ``catalog_publish.py`` imports
``Principal`` and ``Role`` from ``api/deps.py`` at runtime, and ``service.py``
imports ``Principal`` from the same module under ``TYPE_CHECKING``. The reason
the vocabulary moved is the cycle above, not a rule with no exceptions.

The vocabulary is the review-scorecard calibration corpus's structured label,
persisted on the ``SENT_BACK`` pipeline event's payload. It is D3-compliant by
construction: a value from a closed set, never free text. The reviewer's prose
travels in ``send_back``'s separate ``reason`` argument, which is logged and
not persisted.

Nothing here does I/O; it is a vocabulary plus one guard function.
"""

from __future__ import annotations

from typing import Final, Literal, cast, get_args

from cyo_adventure.core.exceptions import ValidationError

# Closed-vocabulary calibration signal for a reviewer's send-back decision.
# Mirrors the KidFlagReasonLiteral pattern in api/schemas.py: named once,
# referenced from the request and response models there so the wire contract
# and the persisted payload stay in lockstep. "other" is the deliberate escape
# hatch for a reason this list does not anticipate; the free-text `reason`
# argument still carries the reviewer's prose for that case.
#
# A Literal, not an enum, deliberately: pydantic renders it inline in the
# OpenAPI schema as {"type": "string", "enum": [...]}, and the frontend client
# is generated from that schema and drift-checked in CI. Swapping in a StrEnum
# would emit a named component instead and churn the generated client for no
# behavioural gain.
SendBackReasonCodeLiteral = Literal[
    "safety_concern",
    "reading_level",
    "coherence_error",
    "continuity_error",
    "weak_choices",
    "repetitive",
    "prose_quality",
    "unsatisfying_ending",
    "factual_error",
    "other",
]

# Derived from the Literal rather than written out a second time, so the two
# can never disagree about what the vocabulary is.
SEND_BACK_REASON_CODES: Final[frozenset[str]] = frozenset(
    get_args(SendBackReasonCodeLiteral)
)


def validate_reason_code(value: str) -> SendBackReasonCodeLiteral:
    """Return ``value`` if it is in the vocabulary, else raise.

    Args:
        value: The candidate reason code.

    Returns:
        The same string, narrowed to ``SendBackReasonCodeLiteral``.

    Raises:
        ValidationError: If ``value`` is outside the closed vocabulary.
    """
    # #CRITICAL: data integrity: an out-of-vocabulary code reaching the
    # SENT_BACK event's payload pollutes the calibration corpus permanently,
    # because pipeline_event is append-only and has no deletion path (see
    # docs/compliance/data-retention-policy.md). Pydantic rejects one at the
    # API boundary, but the boundary is not the only caller: a script, a
    # worker, or a future internal path reaches send_back() directly. Validate
    # in the domain so the guarantee holds wherever the call comes from.
    # #VERIFY: tests/unit/test_send_back_reason_codes.py::
    # test_validate_reason_code_rejects_unknown_code.
    if value not in SEND_BACK_REASON_CODES:
        message = (
            f"Unknown send-back reason code {value!r}; expected one of "
            f"{sorted(SEND_BACK_REASON_CODES)}"
        )
        raise ValidationError(message, field="reason_code", value=value)
    return cast("SendBackReasonCodeLiteral", value)
