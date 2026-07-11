"""upload_cover PUTs to Cloudflare R2 (S3-compatible) and returns the public URL."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cyo_adventure.covers.errors import CoverGenerationError
from cyo_adventure.covers.storage import upload_cover

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
    with (
        patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client),
        pytest.raises(ClientError),
    ):
        await upload_cover(b"WEBP", "s1/2.webp", _settings())
