"""upload_cover posts to Supabase Storage and returns the public URL."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cyo_adventure.covers.errors import CoverGenerationError
from cyo_adventure.covers.storage import upload_cover

pytestmark = pytest.mark.unit


def _settings():
    return SimpleNamespace(
        supabase_url="https://proj.supabase.co",
        supabase_service_key="svc",
        covers_bucket="covers",
    )


@pytest.mark.asyncio
async def test_uploads_and_returns_public_url():
    post = AsyncMock(return_value=SimpleNamespace(raise_for_status=lambda: None))
    client = SimpleNamespace(post=post)
    # MagicMock (not SimpleNamespace) for the context manager: CPython looks up
    # __aenter__/__aexit__ on the type, not the instance, so a plain
    # SimpleNamespace with those as instance attributes fails `async with`.
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("cyo_adventure.covers.storage.httpx.AsyncClient", return_value=ctx):
        url = await upload_cover(b"WEBP", "s1/2.webp", _settings())
    assert url == "https://proj.supabase.co/storage/v1/object/public/covers/s1/2.webp"
    args, kwargs = post.call_args
    assert args[0] == "https://proj.supabase.co/storage/v1/object/covers/s1/2.webp"
    assert kwargs["headers"]["x-upsert"] == "true"
    assert kwargs["headers"]["Content-Type"] == "image/webp"
    assert kwargs["headers"]["Authorization"] == "Bearer svc"


@pytest.mark.asyncio
async def test_raises_when_unconfigured():
    unconfigured = SimpleNamespace(
        supabase_url=None,
        supabase_service_key=None,
        covers_bucket="covers",
    )
    with pytest.raises(CoverGenerationError):
        await upload_cover(b"x", "k.webp", unconfigured)
