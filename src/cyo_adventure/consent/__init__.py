"""Verifiable parental consent plumbing (ADR-018).

Scope note, because the name invites a wrong reading. The KWS Parent
Verification Service this package talks to establishes that an adult is an
adult; Epic's own documentation states it "has not been designed to obtain
consent from verified parents or guardians or to address direct notice
requirements when required by applicable law (such as COPPA)". The 16 CFR
312.5 consent record and the 312.4 direct notice remain ours: today they live
on ``User.consent_*`` (written solely by ``api/onboarding.py::_record_consent``)
and the adult-verification signal from KWS is corroborating evidence alongside
them, never a replacement for them.
"""

from cyo_adventure.consent.external_payload import (
    MAX_EXTERNAL_PAYLOAD_CHARS,
    VerificationCorrelation,
    mint_correlation,
    parse_correlation,
    serialize_correlation,
)
from cyo_adventure.consent.kws_client import (
    KwsClient,
    VerificationEmailRequest,
    VerificationEmailResult,
)
from cyo_adventure.consent.kws_signature import (
    FreshnessWindow,
    ParsedSignatureHeader,
    parse_signature_header,
    verify_redirect_signature,
    verify_webhook_signature,
)
from cyo_adventure.consent.service import (
    ParentVerifiedOutcome,
    VerificationStartRequest,
    record_parent_verified,
    start_parent_verification,
)

__all__ = [
    "MAX_EXTERNAL_PAYLOAD_CHARS",
    "FreshnessWindow",
    "KwsClient",
    "ParentVerifiedOutcome",
    "ParsedSignatureHeader",
    "VerificationCorrelation",
    "VerificationEmailRequest",
    "VerificationEmailResult",
    "VerificationStartRequest",
    "mint_correlation",
    "parse_correlation",
    "parse_signature_header",
    "record_parent_verified",
    "serialize_correlation",
    "start_parent_verification",
    "verify_redirect_signature",
    "verify_webhook_signature",
]
