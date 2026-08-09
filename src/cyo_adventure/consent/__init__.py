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

from cyo_adventure.consent.kws_signature import (
    FreshnessWindow,
    ParsedSignatureHeader,
    parse_signature_header,
    verify_redirect_signature,
    verify_webhook_signature,
)

__all__ = [
    "FreshnessWindow",
    "ParsedSignatureHeader",
    "parse_signature_header",
    "verify_redirect_signature",
    "verify_webhook_signature",
]
