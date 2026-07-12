"""Unit tests for the profile-PIN hashing module (P6-07, core/pin.py)."""

from __future__ import annotations

import base64

import pytest

from cyo_adventure.core.pin import hash_pin, verify_pin

pytestmark = pytest.mark.security

# A low iteration count keeps the unit suite fast; the encoding stores the
# count, so verification uses the same one.
_FAST = 1_000


def test_hash_pin_round_trips_with_correct_pin() -> None:
    """A hashed PIN verifies against the PIN it was derived from."""
    encoded = hash_pin("4321", iterations=_FAST)
    assert verify_pin("4321", encoded) is True


def test_verify_pin_rejects_wrong_pin() -> None:
    """A different PIN of the same shape does not verify."""
    encoded = hash_pin("4321", iterations=_FAST)
    assert verify_pin("4322", encoded) is False


def test_hash_pin_encoding_shape_and_default_iterations() -> None:
    """The encoding is pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>."""
    encoded = hash_pin("12345678")
    scheme, iters, salt_b64, hash_b64 = encoded.split("$")
    assert scheme == "pbkdf2_sha256"
    assert int(iters) == 600_000
    assert len(base64.b64decode(salt_b64, validate=True)) == 16
    assert len(base64.b64decode(hash_b64, validate=True)) == 32
    assert verify_pin("12345678", encoded) is True


def test_hash_pin_salts_are_unique_per_call() -> None:
    """Equal PINs hash to different encodings (fresh random salt each time)."""
    first = hash_pin("0000", iterations=_FAST)
    second = hash_pin("0000", iterations=_FAST)
    assert first != second
    assert verify_pin("0000", first) is True
    assert verify_pin("0000", second) is True


def test_verify_pin_honours_stored_iteration_count() -> None:
    """Verification reads the iteration count from the encoding, not a global."""
    encoded = hash_pin("9876", iterations=2_000)
    assert verify_pin("9876", encoded) is True


@pytest.mark.parametrize(
    "tampered",
    [
        "",  # empty stored value
        "pbkdf2_sha256",  # no fields at all
        "pbkdf2_sha256$1000$onlythreefields",  # wrong field count
        "md5$1000$c2FsdA==$aGFzaA==",  # wrong scheme
        "pbkdf2_sha256$abc$c2FsdA==$aGFzaA==",  # non-integer iterations
        "pbkdf2_sha256$0$c2FsdA==$aGFzaA==",  # non-positive iterations
        "pbkdf2_sha256$1000$!!notb64!!$aGFzaA==",  # invalid salt base64
        "pbkdf2_sha256$1000$c2FsdA==$!!notb64!!",  # invalid hash base64
        "pbkdf2_sha256$1000$$aGFzaA==",  # empty salt
        "pbkdf2_sha256$1000$c2FsdA==$",  # empty hash
        "pbkdf2_sha256$1000$c2FsdA==$aGFzaA==$extra",  # trailing extra field
    ],
)
def test_verify_rejects_tampered_encodings(tampered: str) -> None:
    """Every malformed or tampered encoding fails closed (False, no raise)."""
    assert verify_pin("4321", tampered) is False


def test_verify_rejects_truncated_stored_hash() -> None:
    """Chopping bytes off the stored digest invalidates it (no prefix match)."""
    encoded = hash_pin("4321", iterations=_FAST)
    scheme, iters, salt_b64, hash_b64 = encoded.split("$")
    truncated = base64.b64encode(base64.b64decode(hash_b64, validate=True)[:-8]).decode(
        "ascii"
    )
    assert verify_pin("4321", f"{scheme}${iters}${salt_b64}${truncated}") is False


def test_verify_rejects_empty_candidate_pin() -> None:
    """An empty candidate never verifies, whatever is stored."""
    encoded = hash_pin("4321", iterations=_FAST)
    assert verify_pin("", encoded) is False


def test_hash_pin_rejects_empty_pin() -> None:
    """The empty string can never become a stored credential."""
    with pytest.raises(ValueError, match="empty"):
        hash_pin("")


def test_hash_pin_rejects_non_positive_iterations() -> None:
    """A zero or negative iteration request is refused."""
    with pytest.raises(ValueError, match="positive"):
        hash_pin("4321", iterations=0)
