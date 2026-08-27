"""Cover-related settings load from env with sane defaults."""

import pydantic
import pytest

from cyo_adventure.core.config import Settings

pytestmark = pytest.mark.unit


def test_defaults() -> None:
    s = Settings()
    assert s.r2_bucket == "covers"
    assert s.cover_model == "gemini-3-pro-image"
    assert s.cover_max_width == 800
    assert s.cover_max_bytes == 256_000
    assert s.covers_backup_dir is None


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "AKIDEXAMPLE")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "svc")
    monkeypatch.setenv("R2_BUCKET", "custom-covers")
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://images.example.com")
    s = Settings()
    assert s.gemini_api_key == "g"
    assert s.r2_account_id == "acct123"
    assert s.r2_access_key_id == "AKIDEXAMPLE"
    assert s.r2_secret_access_key == "svc"
    assert s.r2_bucket == "custom-covers"
    assert s.r2_public_base_url == "https://images.example.com"


@pytest.mark.unit
@pytest.mark.parametrize(
    "env_var",
    [
        "CYO_ADVENTURE_COVER_MAX_WIDTH",
        "CYO_ADVENTURE_COVER_QUALITY",
        "CYO_ADVENTURE_COVER_MAX_BYTES",
        "CYO_ADVENTURE_COVER_JOB_TIMEOUT_SECONDS",
    ],
)
def test_settings_non_integer_cover_value_raises_validation_error(
    env_var: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-integer env value for an int cover setting fails fast at load."""
    monkeypatch.setenv(env_var, "not-a-number")
    with pytest.raises(pydantic.ValidationError):
        Settings()


@pytest.mark.unit
def test_settings_fractional_cover_max_width_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fractional width is rejected rather than silently truncated."""
    monkeypatch.setenv("CYO_ADVENTURE_COVER_MAX_WIDTH", "800.5")
    with pytest.raises(pydantic.ValidationError):
        Settings()


@pytest.mark.unit
def test_r2_credentials_are_whitespace_trimmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hand-pasted R2 secret carries stray whitespace that must not reach boto3.

    The account id is interpolated into a hostname, so a leading space produces
    `Invalid endpoint: https:// ***.r2.cloudflarestorage.com`, whose mask hides which
    character is at fault. The two keys are signed material, where a trailing newline
    breaks the signature with an equally opaque error.
    """
    monkeypatch.setenv("R2_ACCOUNT_ID", " 0123456789abcdef0123456789abcdef\n")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "\tAKIDEXAMPLE")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "svc \n")
    s = Settings()
    assert s.r2_account_id == "0123456789abcdef0123456789abcdef"
    assert s.r2_access_key_id == "AKIDEXAMPLE"
    assert s.r2_secret_access_key == "svc"


@pytest.mark.unit
@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_whitespace_only_r2_credential_reads_as_absent(
    blank: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "   " is truthy, so it used to sail past the falsy guard in covers/storage.

    Collapsing it to None is what makes `_require_r2_configured`'s "missing or blank"
    docstring true. Asserting `is None` rather than falsiness is deliberate: the
    empty string is also falsy, so a weaker assertion would not distinguish a
    normalizing validator from no validator at all.
    """
    monkeypatch.setenv("R2_ACCOUNT_ID", blank)
    assert Settings().r2_account_id is None


@pytest.mark.unit
def test_a_malformed_r2_account_id_does_not_break_settings_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shape is NOT enforced here, and that is the point.

    `settings = Settings()` runs at module import, so raising on a malformed value
    would turn a cover-art misconfiguration into a whole-application startup failure.
    The rejecting check lives in `covers/storage.py::_require_r2_configured`, where it
    raises a CoverGenerationError scoped to cover art. This test pins that division so
    a later "tighten the validator" change has to confront it.
    """
    monkeypatch.setenv("R2_ACCOUNT_ID", "https://acct.r2.cloudflarestorage.com")
    assert Settings().r2_account_id == "https://acct.r2.cloudflarestorage.com"
