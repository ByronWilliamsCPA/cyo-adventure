"""generate_cover orchestrates provider+optimize+upload and writes status."""

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.covers.errors import CoverGenerationError
from cyo_adventure.covers.service import generate_cover
from cyo_adventure.db.models import Concept, GenerationJob, StorybookVersion

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


@pytest.mark.asyncio
async def test_missing_target_row_warns_and_returns_without_raising(sessions, seed):
    # No StorybookVersion row exists for this (storybook_id, version) pair, so
    # generate_cover should log and return early rather than raise.
    async with sessions() as s:
        await generate_cover(
            "nonexistent-storybook",
            999,
            session=s,
            settings=Settings(),
            generate=lambda prompt, settings: b"unused",
            optimize=lambda b, **kw: b,
            upload=lambda image_bytes, key, settings: "unused",
        )
    # No row was created or touched; nothing further to assert on the DB, the
    # early return itself (no exception) is the behavior under test.


@pytest.mark.asyncio
async def test_row_deleted_during_failure_handling_skips_status_write(sessions, seed):
    # The upload step deletes the target row (via the same session generate_cover
    # is using) and commits before raising, simulating a row that vanished
    # between the initial fetch and the failure handler's re-fetch. The except
    # block's ``fresh is not None`` guard should then be False, skipping the
    # status write instead of raising on a None attribute access.
    captured_session = {}

    def fake_generate(prompt, settings):
        return b"PNGSOURCE"

    async def delete_then_raise(image_bytes, key, settings):
        s = captured_session["session"]
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        await s.delete(row)
        await s.commit()
        raise CoverGenerationError("upload failed after row was deleted")

    async with sessions() as s:
        captured_session["session"] = s
        await generate_cover(
            seed.storybook_id,
            seed.version,
            session=s,
            settings=Settings(),
            generate=fake_generate,
            optimize=lambda b, **kw: b"WEBP",
            upload=delete_then_raise,
        )
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is None


@pytest.mark.asyncio
async def test_protagonist_name_recovered_from_generation_job_included_in_prompt(
    sessions, seed
):
    # A Concept -> GenerationJob chain links back to the seeded storybook; the
    # protagonist name in the concept brief should reach the built prompt.
    captured = {}

    def capturing_generate(prompt, settings):
        captured["prompt"] = prompt
        return b"PNGSOURCE"

    async def fake_upload(image_bytes, key, settings):
        return f"https://p.supabase.co/storage/v1/object/public/covers/{key}"

    async with sessions() as s:
        concept = Concept(
            family_id=seed.family_id,
            brief={"protagonist": {"name": "Milo"}, "topic": "dragons"},
        )
        s.add(concept)
        await s.flush()
        s.add(
            GenerationJob(
                concept_id=concept.id,
                storybook_id=seed.storybook_id,
                status="passed",
            )
        )
        await s.commit()

    async with sessions() as s:
        await generate_cover(
            seed.storybook_id,
            seed.version,
            session=s,
            settings=Settings(),
            generate=capturing_generate,
            optimize=lambda b, **kw: b"WEBP",
            upload=fake_upload,
        )
    assert "Milo" in captured["prompt"]


@pytest.mark.asyncio
async def test_protagonist_not_a_dict_degrades_to_default_subject(sessions, seed):
    # The concept brief's "protagonist" key holds a non-dict value; the
    # recovery helper must degrade to None rather than raise, so the prompt
    # falls back to the generic subject phrase.
    captured = {}

    def capturing_generate(prompt, settings):
        captured["prompt"] = prompt
        return b"PNGSOURCE"

    async def fake_upload(image_bytes, key, settings):
        return f"https://p.supabase.co/storage/v1/object/public/covers/{key}"

    async with sessions() as s:
        concept = Concept(
            family_id=seed.family_id,
            brief={"protagonist": "not-a-dict", "topic": "dragons"},
        )
        s.add(concept)
        await s.flush()
        s.add(
            GenerationJob(
                concept_id=concept.id,
                storybook_id=seed.storybook_id,
                status="passed",
            )
        )
        await s.commit()

    async with sessions() as s:
        await generate_cover(
            seed.storybook_id,
            seed.version,
            session=s,
            settings=Settings(),
            generate=capturing_generate,
            optimize=lambda b, **kw: b"WEBP",
            upload=fake_upload,
        )
    assert "the main character" in captured["prompt"]


@pytest.mark.asyncio
async def test_backup_writes_full_res_copy_when_dir_configured(
    sessions, seed, tmp_path
):
    # covers_backup_dir set to a real writable directory: _maybe_backup should
    # write the source bytes to <dir>/<storybook_id>/<version>.png without
    # affecting the ready-path status write.
    async def fake_upload(image_bytes, key, settings):
        return f"https://p.supabase.co/storage/v1/object/public/covers/{key}"

    async with sessions() as s:
        await generate_cover(
            seed.storybook_id,
            seed.version,
            session=s,
            settings=Settings(covers_backup_dir=str(tmp_path)),
            generate=lambda prompt, settings: b"PNGSOURCE",
            optimize=lambda b, **kw: b"WEBP",
            upload=fake_upload,
        )
    backup_file = tmp_path / seed.storybook_id / f"{seed.version}.png"
    assert backup_file.read_bytes() == b"PNGSOURCE"
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row.cover_status == "ready"


@pytest.mark.asyncio
async def test_generate_cover_blocks_on_registered_child_name_in_prompt(sessions, seed):
    # The concept's protagonist name matches the family's registered real
    # child display name ("Reader A", seeded by the `seed` fixture). The PII
    # guard added to generate_cover must block this before the provider is
    # ever called, mirroring the same protection the text-generation path has
    # always had.
    generate_called = {"count": 0}

    def counting_generate(prompt, settings):
        generate_called["count"] += 1
        return b"PNGSOURCE"

    async def fake_upload(image_bytes, key, settings):
        return f"https://p.supabase.co/storage/v1/object/public/covers/{key}"

    async with sessions() as s:
        concept = Concept(
            family_id=seed.family_id,
            brief={"protagonist": {"name": "Reader A"}, "topic": "dragons"},
        )
        s.add(concept)
        await s.flush()
        s.add(
            GenerationJob(
                concept_id=concept.id,
                storybook_id=seed.storybook_id,
                status="passed",
            )
        )
        await s.commit()

    async with sessions() as s:
        await generate_cover(
            seed.storybook_id,
            seed.version,
            session=s,
            settings=Settings(),
            generate=counting_generate,
            optimize=lambda b, **kw: b"WEBP",
            upload=fake_upload,
        )
    assert generate_called["count"] == 0
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row.cover_status == "failed"


@pytest.mark.asyncio
async def test_generate_cover_blocks_on_email_shaped_content_in_prompt(sessions, seed):
    # Pattern-based screening (email/phone/address) applies here too, since
    # the cover prompt is built from story content that could echo any
    # free-text field a guardian typed, not just a registered display name.
    generate_called = {"count": 0}

    def counting_generate(prompt, settings):
        generate_called["count"] += 1
        return b"PNGSOURCE"

    async def fake_upload(image_bytes, key, settings):
        return f"https://p.supabase.co/storage/v1/object/public/covers/{key}"

    async with sessions() as s:
        concept = Concept(
            family_id=seed.family_id,
            brief={
                "protagonist": {"name": "contact.us@example.com"},
                "topic": "dragons",
            },
        )
        s.add(concept)
        await s.flush()
        s.add(
            GenerationJob(
                concept_id=concept.id,
                storybook_id=seed.storybook_id,
                status="passed",
            )
        )
        await s.commit()

    async with sessions() as s:
        await generate_cover(
            seed.storybook_id,
            seed.version,
            session=s,
            settings=Settings(),
            generate=counting_generate,
            optimize=lambda b, **kw: b"WEBP",
            upload=fake_upload,
        )
    assert generate_called["count"] == 0
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row.cover_status == "failed"


@pytest.mark.asyncio
async def test_backup_failure_is_swallowed_and_job_still_succeeds(
    sessions, seed, tmp_path
):
    # covers_backup_dir points through a path component that is a regular file,
    # not a directory, so Path.mkdir(parents=True) raises OSError. _maybe_backup
    # must catch and log this without failing the cover job.
    blocked = tmp_path / "not_a_directory"
    blocked.write_text("occupied")

    async def fake_upload(image_bytes, key, settings):
        return f"https://p.supabase.co/storage/v1/object/public/covers/{key}"

    async with sessions() as s:
        await generate_cover(
            seed.storybook_id,
            seed.version,
            session=s,
            settings=Settings(covers_backup_dir=str(blocked)),
            generate=lambda prompt, settings: b"PNGSOURCE",
            optimize=lambda b, **kw: b"WEBP",
            upload=fake_upload,
        )
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row.cover_status == "ready"
