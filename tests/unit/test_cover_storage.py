"""upload_cover PUTs to Cloudflare R2 (S3-compatible) and returns the public URL."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from cyo_adventure.covers.errors import CoverGenerationError
from cyo_adventure.covers.storage import (
    cover_object_key,
    generate_presigned_cover_url,
    generate_presigned_cover_urls,
    upload_cover,
)

pytestmark = pytest.mark.unit


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


def test_cover_object_key_format() -> None:
    """The canonical key is the single source of truth every caller shares."""
    assert cover_object_key("s1", 2) == "s1/2.webp"


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
            [("s1", 1), ("s2", 3)], _settings()
        )

    assert result == {
        ("s1", 1): "https://r2.example/s1-1",
        ("s2", 3): "https://r2.example/s2-3",
    }
    mock_boto.assert_called_once()
    assert mock_client.generate_presigned_url.call_count == 2


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
        result = await generate_presigned_cover_urls([("s1", 1)], unconfigured)

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
        result = await generate_presigned_cover_urls([("s1", 1)], _settings())

    assert result == {}
