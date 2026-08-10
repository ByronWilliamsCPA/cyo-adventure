"""Tests for the KWS ``externalPayload`` correlation blob.

The blob is the only thing tying a verification result back to the guardian who
started it, and it round-trips through a third party, so the tests are split
between what we mint (must stay inside the vendor's cap, must leak nothing) and
what we read back (must be treated as attacker-controlled).
"""

from __future__ import annotations

import json
from uuid import UUID

import pytest

from cyo_adventure.consent import (
    MAX_EXTERNAL_PAYLOAD_CHARS,
    VerificationCorrelation,
    mint_correlation,
    parse_correlation,
    serialize_correlation,
)
from cyo_adventure.core.exceptions import ValidationError


class TestMintAndSerialize:
    """What we send out."""

    @pytest.mark.unit
    def test_round_trips(self) -> None:
        """Mint, serialise, parse, and get the same attempt id back."""
        minted = mint_correlation()

        parsed = parse_correlation(serialize_correlation(minted))

        assert parsed == minted

    @pytest.mark.unit
    def test_each_mint_is_unique(self) -> None:
        """Two attempts must never share a correlation token.

        A reused token would let one verification's result be attributed to a
        different attempt, which is the whole failure mode the token exists to
        prevent.
        """
        assert mint_correlation() != mint_correlation()

    @pytest.mark.unit
    def test_stays_well_inside_the_vendor_cap(self) -> None:
        """KWS rejects anything over 250 characters.

        Asserting real headroom rather than mere compliance: at roughly a fifth
        of the cap, a future field can be added without a vendor-side surprise.
        """
        rendered = serialize_correlation(mint_correlation())

        assert len(rendered) <= MAX_EXTERNAL_PAYLOAD_CHARS
        assert len(rendered) < MAX_EXTERNAL_PAYLOAD_CHARS // 2

    @pytest.mark.unit
    def test_carries_nothing_but_the_attempt_id(self) -> None:
        """The payload appears in a redirect URL, so its contents are public.

        Pinning the exact key set is the point: this test fails the moment
        somebody adds an email, a user id, or a child's name to a blob that
        lands in browser history.
        """
        decoded = json.loads(serialize_correlation(mint_correlation()))

        assert set(decoded) == {"v", "attemptId"}

    @pytest.mark.unit
    def test_is_compact_json(self) -> None:
        """No incidental whitespace, since every character counts against 250."""
        assert " " not in serialize_correlation(mint_correlation())


class TestParse:
    """What comes back, which is untrusted no matter what we minted."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "not json",
            "[1,2,3]",
            '"a string"',
            "{}",
            '{"v":1}',
            '{"attemptId":"6f1b9e4c-0000-4000-8000-000000000001"}',
            '{"v":2,"attemptId":"6f1b9e4c-0000-4000-8000-000000000001"}',
            '{"v":"1","attemptId":"6f1b9e4c-0000-4000-8000-000000000001"}',
            '{"v":1,"attemptId":"not-a-uuid"}',
            '{"v":1,"attemptId":123}',
            '{"v":1,"attemptId":null}',
        ],
        ids=[
            "empty",
            "not_json",
            "json_array",
            "json_string",
            "empty_object",
            "no_attempt_id",
            "no_version",
            "future_version",
            "version_as_string",
            "malformed_attempt_id",
            "numeric_attempt_id",
            "null_attempt_id",
        ],
    )
    def test_malformed_payloads_rejected(self, raw: str) -> None:
        """Every unusual shape raises rather than yielding a partial token.

        The redirect leg delivers this value as a query parameter, so all of
        these are things a caller can simply type.
        """
        with pytest.raises(ValidationError):
            parse_correlation(raw)

    @pytest.mark.unit
    def test_unknown_extra_keys_are_tolerated(self) -> None:
        """Forward compatibility runs one way only.

        An unknown VERSION is refused because the fields may have changed
        meaning, but an unknown extra KEY at a known version is ignored, so a
        payload minted by a newer build in a rolling deploy still parses.
        """
        raw = '{"v":1,"attemptId":"6f1b9e4c-0000-4000-8000-000000000001","x":"y"}'

        parsed = parse_correlation(raw)

        assert parsed.attempt_id == UUID("6f1b9e4c-0000-4000-8000-000000000001")

    @pytest.mark.unit
    def test_parsing_does_not_prove_the_attempt_exists(self) -> None:
        """A well-formed token is a lookup key, not an authorization.

        Anyone can mint a syntactically valid payload, so this documents by
        example that parsing succeeds on a token we never issued. The row it
        fails to find is what makes the decision.
        """
        forged = serialize_correlation(
            VerificationCorrelation(
                attempt_id=UUID("00000000-0000-4000-8000-00000000dead")
            )
        )

        assert parse_correlation(forged).attempt_id.hex.endswith("dead")
