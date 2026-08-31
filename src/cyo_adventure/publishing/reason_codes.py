"""The closed send-back and recall reason vocabularies, owned by the domain.

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

Two vocabularies live here, not one, and they are deliberately separate sets.
A send-back answers "why is this draft not publishable yet"; a recall answers
"why is this already-published book coming back to the human gate". The only
overlap is ``safety_concern``, and collapsing them into one list would let a
recall be labelled ``unsatisfying_ending`` (a drafting critique that cannot
motivate pulling a live book) or a send-back be labelled ``threshold_change``
(which cannot apply to a book that was never published under the old
thresholds). Both vocabularies are persisted on append-only pipeline events, so
a label that cannot be true is a permanent corpus defect.

Nothing here does I/O; it is two vocabularies plus their guard functions.
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


# Closed-vocabulary reason for recalling a PUBLISHED book back to the human
# gate (publishing/service.py::recall, the published->in_review hop added for
# `RS-C1`). Same Literal-not-enum rationale as the send-back vocabulary above.
#
# The members are the reasons that can motivate pulling a live book, which is a
# different question from why a draft is not publishable yet:
#
# - threshold_change: the moderation thresholds moved, so this book's stored
#   verdict was reached under a rule set that no longer applies. This is the
#   case that motivated recall existing at all.
# - safety_concern: a specific safety problem in this book, found by a fresh
#   re-moderation, a kid flag, or a human reading it.
# - content_correction: a non-safety content defect worth fixing (a continuity
#   break, a factual error) that does not make the book unsafe to have shipped.
# - curation: a deliberate catalog decision with no defect in the book.
# - other: the escape hatch, matching the send-back vocabulary's.
RecallReasonCodeLiteral = Literal[
    "threshold_change",
    "safety_concern",
    "content_correction",
    "curation",
    "other",
]

# Derived from the Literal, same as SEND_BACK_REASON_CODES above.
RECALL_REASON_CODES: Final[frozenset[str]] = frozenset(
    get_args(RecallReasonCodeLiteral)
)

# #CRITICAL: security: the reasons that do NOT raise a guardian alert, as an
# ALLOW-list. notifications/registry.py::_compose_storybook_recalled reads this
# to decide severity, and it must fail CLOSED: a reason absent from this set
# (including any member added later, and any value that somehow bypassed
# validation) alerts the guardian. The negation (`reason != "curation"`) would
# be default-open over an open vocabulary, which is the exact defect
# api/remoderate.py::_allow_repair_for documents having fixed.
# #VERIFY: tests/unit/test_recall_reason_codes.py::
# test_every_reason_outside_the_quiet_set_alerts and
# ::test_the_quiet_set_is_a_subset_of_the_vocabulary.
QUIET_RECALL_REASON_CODES: Final[frozenset[str]] = frozenset(
    {"content_correction", "curation"}
)


def validate_recall_reason_code(value: str) -> RecallReasonCodeLiteral:
    """Return ``value`` if it is in the recall vocabulary, else raise.

    Args:
        value: The candidate reason code.

    Returns:
        The same string, narrowed to ``RecallReasonCodeLiteral``.

    Raises:
        ValidationError: If ``value`` is outside the closed vocabulary.
    """
    # #CRITICAL: data integrity: same append-only argument as
    # validate_reason_code above. The API boundary is not the only caller: a
    # threshold-change sweep script is the motivating use case for recall and
    # would reach this service directly.
    # #VERIFY: tests/unit/test_recall_reason_codes.py::
    # test_validate_recall_reason_code_rejects_unknown_code and
    # ::test_a_send_back_code_is_not_a_valid_recall_code.
    if value not in RECALL_REASON_CODES:
        message = (
            f"Unknown recall reason code {value!r}; expected one of "
            f"{sorted(RECALL_REASON_CODES)}"
        )
        raise ValidationError(message, field="reason_code", value=value)
    return cast("RecallReasonCodeLiteral", value)
