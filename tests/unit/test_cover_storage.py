"""upload_cover PUTs to Cloudflare R2 (S3-compatible) and returns the public URL."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import structlog
from botocore.exceptions import BotoCoreError, ClientError
from structlog.testing import LogCapture

from cyo_adventure.covers import storage as storage_module
from cyo_adventure.covers.errors import CoverGenerationError
from cyo_adventure.covers.storage import (
    cover_object_key,
    delete_cover,
    generate_presigned_cover_url,
    generate_presigned_cover_urls,
    upload_cover,
)
from cyo_adventure.utils.redaction import digest_identifier

pytestmark = pytest.mark.unit

# Clearly-fake stand-in for a cover_object_salt. Deliberately NOT shaped like
# the real thing (32 hex characters), because a 32-hex literal under a name
# containing SALT is exactly what a generic high-entropy secret detector
# flags. Nothing under test parses the salt, so its shape buys no coverage.
_PLACEHOLDER_SALT = "salt-placeholder-for-tests"


@pytest.fixture
def storage_logs(monkeypatch: pytest.MonkeyPatch) -> LogCapture:
    """Capture ``covers.storage``'s structured logs deterministically.

    Returns:
        LogCapture: The capture whose ``entries`` hold every event the module
        logged during the test.
    """
    cap = LogCapture()
    monkeypatch.setattr(
        storage_module,
        "_logger",
        structlog.wrap_logger(structlog.testing.ReturnLogger(), processors=[cap]),
    )
    return cap


def _settings(**overrides: object) -> SimpleNamespace:
    defaults = {
        "r2_account_id": "acct123",
        "r2_access_key_id": "AKIDEXAMPLE",
        "r2_secret_access_key": "secret",
        "r2_bucket": "covers",
        "r2_public_base_url": "https://images.example.com",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_uploads_and_returns_public_url() -> None:
    mock_client = MagicMock()
    with patch(
        "cyo_adventure.covers.storage.boto3.client", return_value=mock_client
    ) as mock_boto:
        url = await upload_cover(b"WEBP", "s1/2.webp", _settings())

    assert url == "https://images.example.com/s1/2.webp"
    mock_boto.assert_called_once()
    boto_kwargs = mock_boto.call_args.kwargs
    assert boto_kwargs["endpoint_url"] == "https://acct123.r2.cloudflarestorage.com"
    assert boto_kwargs["aws_access_key_id"] == "AKIDEXAMPLE"
    assert boto_kwargs["aws_secret_access_key"] == "secret"
    assert boto_kwargs["region_name"] == "auto"
    boto_config = boto_kwargs["config"]
    assert boto_config.connect_timeout == 30.0
    assert boto_config.read_timeout == 30.0
    assert boto_config.request_checksum_calculation == "when_required"
    assert boto_config.response_checksum_validation == "when_required"
    assert boto_config.s3 == {"addressing_style": "path"}
    mock_client.put_object.assert_called_once_with(
        Bucket="covers",
        Key="s1/2.webp",
        Body=b"WEBP",
        ContentType="image/webp",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_field",
    ["r2_account_id", "r2_access_key_id", "r2_secret_access_key", "r2_public_base_url"],
)
async def test_raises_when_unconfigured(missing_field: str) -> None:
    unconfigured = _settings(**{missing_field: None})
    with pytest.raises(CoverGenerationError):
        await upload_cover(b"x", "k.webp", unconfigured)


@pytest.mark.asyncio
async def test_upload_failure_propagates() -> None:
    mock_client = MagicMock()
    mock_client.put_object.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "boom"}}, "PutObject"
    )
    settings = _settings()
    with (
        patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client),
        pytest.raises(ClientError),
    ):
        await upload_cover(b"WEBP", "s1/2.webp", settings)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_cover_blank_config_value_raises_generation_error() -> None:
    """An empty-string R2 credential counts as unconfigured, same as None."""
    unconfigured = _settings(r2_account_id="")
    with pytest.raises(CoverGenerationError, match="not configured"):
        await upload_cover(b"x", "k.webp", unconfigured)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_id",
    [
        "acct 123",  # a space that survived a manual paste
        "https://acct.r2.cloudflarestorage.com",  # the endpoint URL, not the id
        "acct.123",  # two labels, so it points at some other host
        "acct_123",  # legal in a secret, illegal in a DNS label
        "-acct123",  # a label may not start with a hyphen
        "0" * 64,  # one past the longest label the regex can match
    ],
)
async def test_upload_cover_rejects_a_malformed_account_id(bad_id: str) -> None:
    """Fail before boto3, where the deployment's secret mask hides the defect.

    Reaching boto3 produces `Invalid endpoint: https://***.r2.cloudflarestorage.com`,
    which cannot distinguish a stray space from a whole pasted URL. This is the same
    failure that cost `scripts/backup_database.py` two dispatches on 2026-08-27; the
    backend reads the same `R2_ACCOUNT_ID` name and had no equivalent check.
    """
    settings = _settings(r2_account_id=bad_id)
    with pytest.raises(CoverGenerationError, match="not a valid hostname label"):
        await upload_cover(b"x", "k.webp", settings)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_cover_malformed_account_id_message_does_not_echo_the_value() -> (
    None
):
    """The message reports a length, never the characters.

    A deployment log is a less controlled surface than a CI log, so unlike the backup
    script this path does not name individual offending characters. Length alone is
    enough to separate "blank", "stray character", and "whole URL pasted in".
    """
    secret_ish = "0123456789abcdef0123456789abcdef.extra"
    settings = _settings(r2_account_id=secret_ish)
    with pytest.raises(CoverGenerationError) as exc_info:
        await upload_cover(b"x", "k.webp", settings)
    message = str(exc_info.value)
    assert f"{len(secret_ish)} characters" in message
    assert secret_ish not in message
    assert "0123456789abcdef" not in message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_cover_client_construction_failure_propagates() -> None:
    """A boto3 client construction failure propagates instead of returning a URL."""
    settings = _settings()
    with (
        patch(
            "cyo_adventure.covers.storage.boto3.client",
            side_effect=BotoCoreError(),
        ),
        pytest.raises(BotoCoreError),
    ):
        await upload_cover(b"WEBP", "s1/2.webp", settings)


@pytest.mark.asyncio
async def test_delete_cover_removes_the_object_and_reports_success() -> None:
    """The happy path issues one DeleteObject against the configured bucket."""
    mock_client = MagicMock()
    with patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client):
        deleted = await delete_cover("s1/2-abc123.webp", _settings())

    assert deleted is True
    mock_client.delete_object.assert_called_once_with(
        Bucket="covers", Key="s1/2-abc123.webp"
    )


@pytest.mark.asyncio
async def test_delete_cover_does_not_require_public_base_url() -> None:
    """Reclaiming an object builds no URL, so R2_PUBLIC_BASE_URL is optional."""
    mock_client = MagicMock()
    settings = _settings(r2_public_base_url=None)
    with patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client):
        deleted = await delete_cover("s1/2-abc123.webp", settings)

    assert deleted is True
    mock_client.delete_object.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_field",
    ["r2_account_id", "r2_access_key_id", "r2_secret_access_key", "r2_bucket"],
)
async def test_delete_cover_returns_false_when_unconfigured(
    missing_field: str,
) -> None:
    """An unconfigured R2 reports the delete did not happen rather than raising:
    the caller has already committed a replacement cover it must not fail."""
    unconfigured = _settings(**{missing_field: None})
    with patch("cyo_adventure.covers.storage.boto3.client") as mock_boto:
        deleted = await delete_cover("s1/2-abc123.webp", unconfigured)

    assert deleted is False
    mock_boto.assert_not_called()


@pytest.mark.asyncio
async def test_delete_cover_returns_false_on_client_error() -> None:
    """A failed DeleteObject is logged and reported, never raised: the orphan
    is a bounded exposure, but failing here would strand a live cover."""
    mock_client = MagicMock()
    mock_client.delete_object.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "boom"}}, "DeleteObject"
    )
    with patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client):
        deleted = await delete_cover("s1/2-abc123.webp", _settings())

    assert deleted is False


@pytest.mark.asyncio
async def test_delete_cover_returns_false_on_client_construction_failure() -> None:
    """A boto3 construction failure degrades the same way a call failure does."""
    with patch(
        "cyo_adventure.covers.storage.boto3.client", side_effect=BotoCoreError()
    ):
        deleted = await delete_cover("s1/2-abc123.webp", _settings())

    assert deleted is False


class TestDeleteCoverNeverLogsTheSaltedKey:
    """The R2 object key embeds ``cover_object_salt``; logging it leaks it.

    ``cover_object_key``'s own #CRITICAL note names that per-cover
    ``secrets.token_hex(16)`` salt as the unguessability control standing
    between a guessed storybook id and the image bytes (UW-M07). Both
    ``delete_cover`` warning paths used to pass ``key=key`` straight to the
    logger, publishing the control to every log sink in every environment.

    Capture strategy mirrors tests/unit/test_logging_security.py: the module
    logger is replaced with an explicitly wrapped ``LogCapture`` chain.
    ``structlog.testing.capture_logs`` is not usable here, because
    ``storage._logger`` is bound at import under
    ``cache_logger_on_first_use=True`` and so ignores a later reconfiguration.
    Capturing at the call site (rather than after the configured chain) also
    proves the FIX, not the censoring processor backstopping it.
    """

    @pytest.mark.unit
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_unconfigured_path_logs_no_salt(
        self, storage_logs: LogCapture
    ) -> None:
        """The unconfigured warning carries identifiers, never the salted key."""
        key = cover_object_key("s1", 2, _PLACEHOLDER_SALT)

        deleted = await delete_cover(key, _settings(r2_bucket=None))

        assert deleted is False
        emitted = repr(storage_logs.entries)
        assert _PLACEHOLDER_SALT not in emitted
        assert key not in emitted
        assert [e["event"] for e in storage_logs.entries] == [
            "cover_delete_unconfigured"
        ]
        assert storage_logs.entries[0]["storybook_id"] == "s1"
        assert storage_logs.entries[0]["version"] == 2
        assert storage_logs.entries[0]["key_digest"] == digest_identifier(key)

    @pytest.mark.unit
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_failed_delete_path_logs_no_salt(
        self, storage_logs: LogCapture
    ) -> None:
        """The failed-DeleteObject warning carries identifiers, not the key."""
        key = cover_object_key("s1", 2, _PLACEHOLDER_SALT)
        mock_client = MagicMock()
        mock_client.delete_object.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "boom"}}, "DeleteObject"
        )

        with patch(
            "cyo_adventure.covers.storage.boto3.client", return_value=mock_client
        ):
            deleted = await delete_cover(key, _settings())

        assert deleted is False
        emitted = repr(storage_logs.entries)
        assert _PLACEHOLDER_SALT not in emitted
        assert key not in emitted
        assert [e["event"] for e in storage_logs.entries] == ["cover_delete_failed"]
        assert storage_logs.entries[0]["storybook_id"] == "s1"
        assert storage_logs.entries[0]["version"] == 2
        assert storage_logs.entries[0]["key_digest"] == digest_identifier(key)

    @pytest.mark.unit
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_a_legacy_unsalted_key_still_reports_its_storybook_id(
        self, storage_logs: LogCapture
    ) -> None:
        """A pre-migration key has no salt but must still be diagnosable."""
        key = cover_object_key("s1", 2)

        deleted = await delete_cover(key, _settings(r2_account_id=None))

        assert deleted is False
        # Asserted for the same reason as its two siblings above: presence of
        # the safe fields does not by itself prove the unsafe one is gone.
        assert key not in repr(storage_logs.entries)
        assert storage_logs.entries[0]["storybook_id"] == "s1"
        assert storage_logs.entries[0]["version"] == 2
        assert storage_logs.entries[0]["key_digest"] == digest_identifier(key)


def test_cover_object_key_format() -> None:
    """With no salt, the legacy key is the single source of truth every
    pre-migration caller shares."""
    assert cover_object_key("s1", 2) == "s1/2.webp"


def test_cover_object_key_falls_back_without_salt() -> None:
    """An explicit None salt behaves the same as omitting the argument."""
    assert cover_object_key("s1", 2, None) == "s1/2.webp"


def test_cover_object_key_includes_salt_when_present() -> None:
    """UW-M07 defense in depth: a salt makes the key unguessable from
    (storybook_id, version) alone."""
    assert cover_object_key("s1", 2, "abc123") == "s1/2-abc123.webp"


@pytest.mark.asyncio
async def test_generate_presigned_cover_url_signs_the_derived_key() -> None:
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://r2.example/signed"
    with patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client):
        url = await generate_presigned_cover_url("s1", 2, _settings())

    assert url == "https://r2.example/signed"
    mock_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "covers", "Key": "s1/2.webp"},
        ExpiresIn=3600,
    )


@pytest.mark.asyncio
async def test_generate_presigned_cover_url_respects_custom_expiry() -> None:
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://r2.example/signed"
    with patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client):
        await generate_presigned_cover_url("s1", 2, _settings(), expires_in=60)

    assert mock_client.generate_presigned_url.call_args.kwargs["ExpiresIn"] == 60


@pytest.mark.asyncio
async def test_generate_presigned_cover_url_does_not_require_public_base_url() -> None:
    """Unlike upload_cover, presigning never needs a public custom domain."""
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://r2.example/signed"
    settings = _settings(r2_public_base_url=None)
    with patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client):
        url = await generate_presigned_cover_url("s1", 2, settings)

    assert url == "https://r2.example/signed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_field",
    ["r2_account_id", "r2_access_key_id", "r2_secret_access_key", "r2_bucket"],
)
async def test_generate_presigned_cover_url_returns_none_when_unconfigured(
    missing_field: str,
) -> None:
    """A misconfigured R2 degrades to no cover shown, not a raised error."""
    unconfigured = _settings(**{missing_field: None})
    with patch("cyo_adventure.covers.storage.boto3.client") as mock_boto:
        url = await generate_presigned_cover_url("s1", 2, unconfigured)

    assert url is None
    mock_boto.assert_not_called()


@pytest.mark.asyncio
async def test_generate_presigned_cover_url_signs_the_salted_key_when_present() -> None:
    """UW-M07: a non-None salt reaches the actual R2 key, not just the key builder."""
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://r2.example/signed"
    with patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client):
        await generate_presigned_cover_url("s1", 2, _settings(), salt="abc123")

    mock_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "covers", "Key": "s1/2-abc123.webp"},
        ExpiresIn=3600,
    )


@pytest.mark.asyncio
async def test_generate_presigned_cover_url_returns_none_on_client_error() -> None:
    mock_client = MagicMock()
    mock_client.generate_presigned_url.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "boom"}}, "GeneratePresignedUrl"
    )
    with patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client):
        url = await generate_presigned_cover_url("s1", 2, _settings())

    assert url is None


@pytest.mark.asyncio
async def test_generate_presigned_cover_urls_batch_signs_every_pair_with_one_client() -> (
    None
):
    mock_client = MagicMock()
    mock_client.generate_presigned_url.side_effect = [
        "https://r2.example/s1-1",
        "https://r2.example/s2-3",
    ]
    with patch(
        "cyo_adventure.covers.storage.boto3.client", return_value=mock_client
    ) as mock_boto:
        result = await generate_presigned_cover_urls(
            [("s1", 1, None), ("s2", 3, "saltvalue")], _settings()
        )

    assert result == {
        ("s1", 1): "https://r2.example/s1-1",
        ("s2", 3): "https://r2.example/s2-3",
    }
    mock_boto.assert_called_once()
    assert mock_client.generate_presigned_url.call_count == 2
    mock_client.generate_presigned_url.assert_any_call(
        "get_object",
        Params={"Bucket": "covers", "Key": "s1/1.webp"},
        ExpiresIn=3600,
    )
    mock_client.generate_presigned_url.assert_any_call(
        "get_object",
        Params={"Bucket": "covers", "Key": "s2/3-saltvalue.webp"},
        ExpiresIn=3600,
    )


@pytest.mark.asyncio
async def test_generate_presigned_cover_urls_empty_input_skips_client_construction() -> (
    None
):
    with patch("cyo_adventure.covers.storage.boto3.client") as mock_boto:
        result = await generate_presigned_cover_urls([], _settings())

    assert result == {}
    mock_boto.assert_not_called()


@pytest.mark.asyncio
async def test_generate_presigned_cover_urls_returns_empty_dict_when_unconfigured() -> (
    None
):
    """A misconfigured R2 degrades to no covers shown, not a raised error."""
    unconfigured = _settings(r2_account_id=None)
    with patch("cyo_adventure.covers.storage.boto3.client") as mock_boto:
        result = await generate_presigned_cover_urls([("s1", 1, None)], unconfigured)

    assert result == {}
    mock_boto.assert_not_called()


@pytest.mark.asyncio
async def test_generate_presigned_cover_urls_returns_empty_dict_on_client_error() -> (
    None
):
    mock_client = MagicMock()
    mock_client.generate_presigned_url.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "boom"}}, "GeneratePresignedUrl"
    )
    with patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client):
        result = await generate_presigned_cover_urls([("s1", 1, None)], _settings())

    assert result == {}


class TestKeyLogFields:
    """The projection every ``delete_cover`` warning path emits."""

    @pytest.mark.unit
    def test_a_salted_key_yields_id_version_and_digest(self) -> None:
        """The version is not secret and names WHICH cover failed."""
        key = cover_object_key("s1", 2, _PLACEHOLDER_SALT)

        assert storage_module._key_log_fields(key) == {
            "storybook_id": "s1",
            "key_digest": digest_identifier(key),
            "version": 2,
        }

    @pytest.mark.unit
    def test_a_legacy_unsalted_key_yields_the_same_shape(self) -> None:
        """A pre-migration key parses its version identically."""
        fields = storage_module._key_log_fields("s1/2.webp")

        assert fields["version"] == 2

    @pytest.mark.unit
    def test_an_unparseable_key_omits_version_rather_than_retyping_it(self) -> None:
        """``version`` must never vary in type between log lines.

        A key that does not parse (a hand-built path, a future key format)
        drops the field entirely instead of emitting a string where every
        other line carries an int.
        """
        fields = storage_module._key_log_fields("not-a-key")

        assert "version" not in fields
        assert fields["storybook_id"] == "not-a-key"
