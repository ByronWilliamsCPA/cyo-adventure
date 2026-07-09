"""generate_cover orchestrates provider+optimize+upload and writes status."""

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.covers.errors import CoverGenerationError
from cyo_adventure.covers.service import generate_cover
from cyo_adventure.db.models import StorybookVersion

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_ready_path_writes_url(sessions, seed):
    def fake_generate(prompt, settings):
        return b"PNGSOURCE"

    async def fake_upload(image_bytes, key, settings):
        return f"https://p.supabase.co/storage/v1/object/public/covers/{key}"

    async with sessions() as s:
        await generate_cover(
            seed.storybook_id,
            seed.version,
            session=s,
            settings=Settings(),
            generate=fake_generate,
            optimize=lambda b, **kw: b"WEBP",
            upload=fake_upload,
        )
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row.cover_status == "ready"
        assert row.cover_image_url is not None
        assert ".webp?v=" in row.cover_image_url


@pytest.mark.asyncio
async def test_failure_sets_failed_status(sessions, seed):
    def boom(prompt, settings):
        raise CoverGenerationError("refused")

    async def fake_upload(image_bytes, key, settings):
        return "unused"

    async with sessions() as s:
        await generate_cover(
            seed.storybook_id,
            seed.version,
            session=s,
            settings=Settings(),
            generate=boom,
            optimize=lambda b, **kw: b,
            upload=fake_upload,
        )
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row.cover_status == "failed"
