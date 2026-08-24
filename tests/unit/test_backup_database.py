"""Unit tests for scripts/backup_database.py (no network, no live database).

scripts/ is not an importable package (no __init__.py, by design; see per-file-ignores
INP for scripts/**/*.py in pyproject.toml), so the module is loaded directly from its
file path via importlib, mirroring tests/unit/test_backfill_covers_r2.py.

Fixture convention: every credential-shaped literal here uses an angle-bracket
placeholder (``<user>``, ``<host>``, ``<secret>``), never a realistic password. These
tests exist to prove that redaction strips a password out of a connection string, so the
fixtures must contain something occupying the password slot, and a secret scanner cannot
tell that slot apart from a real leak. A plausible-looking literal there makes this
repository's own scanners raise incidents against their own test data. Whatever a given
test actually needs to exercise (an embedded ``@``, a query-parameter form, an ``&``
boundary) goes *inside* the brackets, so the shape under test survives while the value
stays obviously inert.
"""

from __future__ import annotations

import base64
import importlib.util
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from cryptography.exceptions import InvalidTag

_SPEC = importlib.util.spec_from_file_location(
    "backup_database",
    Path(__file__).resolve().parents[2] / "scripts" / "backup_database.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
backup_database = importlib.util.module_from_spec(_SPEC)
# Registering in sys.modules before exec_module is required here (unlike the sibling
# backfill_covers_r2/seed_staging loaders): dataclasses.dataclass's field-type
# resolution looks the defining module up via sys.modules[cls.__module__], which is
# None for an unregistered module and raises AttributeError at class-definition time.
sys.modules[_SPEC.name] = backup_database
_SPEC.loader.exec_module(backup_database)

pytestmark = pytest.mark.unit

_VALID_KEY = base64.b64encode(b"0" * 32).decode()

# Realistic `supabase db dump` output captured from a live local Supabase stack
# (2026-08-03, CLI 2.109.1, Postgres 17.6) for a project with zero custom roles and
# zero application tables. This is the shape a wrong-project-ref, revoked-grant, or
# wrong-search_path dump actually produces: non-whitespace, well-formed SQL, with none
# of the leg's real content. `str.strip()` alone cannot distinguish this from a good
# dump; only a structural marker check can.
_BOILERPLATE_ROLES_SQL = """
SET default_transaction_read_only = off;

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

RESET ALL;
"""

_BOILERPLATE_SCHEMA_SQL = """--
-- PostgreSQL database dump
--

-- \\restrict aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

-- \\unrestrict aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"""

_BOILERPLATE_DATA_SQL = """SET session_replication_role = replica;

--
-- PostgreSQL database dump
--

-- \\restrict bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

-- \\unrestrict bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

RESET ALL;
"""

# Real leg content (also captured from the same live stack) for legs that must pass
# the guard while a sibling leg is deliberately boilerplate-only.
_REAL_ROLES_SQL = 'ALTER ROLE "anon" SET "statement_timeout" TO \'3s\';\n'
_REAL_SCHEMA_SQL = (
    'CREATE TABLE IF NOT EXISTS "public"."profiles" (\n    "id" uuid NOT NULL\n);\n'
)
_REAL_DATA_SQL = 'COPY "public"."profiles" ("id") FROM stdin;\n\\.\n'

_ALL_LEGS_REAL = {
    "roles.sql": _REAL_ROLES_SQL,
    "schema.sql": _REAL_SCHEMA_SQL,
    "data.sql": _REAL_DATA_SQL,
}

# Every connection string below uses the <user>/<host>/<dbname> placeholder form rather
# than a realistic-looking one. TruffleHog's Postgres detector fires on a literal
# `postgresql://user:pass@host:port`, so realistic fixtures made this repository's own
# secret-scanning pre-commit hook fail on its own test data, which is exactly the
# pressure that teaches people to reach for --no-verify. Keep new fixtures in this form.
_LIVE_ENV = {
    "SUPABASE_DB_URL": "postgresql://<user>:<password>@<host>/<db>",
    "R2_ACCOUNT_ID": "acct",
    "R2_BACKUP_ACCESS_KEY_ID": "key",
    "R2_BACKUP_SECRET_ACCESS_KEY": "secret",
    "R2_BACKUP_BUCKET": "backup-bucket",
    "BACKUP_ENCRYPTION_KEY": _VALID_KEY,
}


def _client_error(code: str, operation: str = "HeadObject") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


def _mock_backup_client(
    *,
    prior_dates: tuple[str, ...] = ("2026-08-01",),
    fail_upload_after: int | None = None,
    sentinel_present: bool = True,
) -> MagicMock:
    """Build an R2 client stub that behaves like an initialized backup bucket.

    Models the three read paths ``run_backup`` now depends on: the sentinel
    ``head_object``, the ``list_objects_v2`` history probe, and the ETag ``head_object``
    the rollback uses to prove an object is still the one this run wrote. ETags are
    tracked per key so a rollback sees the value its own upload produced, which is what
    makes the mismatch case in ``test_rollback_uploads_skips_an_object_another_run_replaced``
    a real distinction rather than an artifact of the mock.

    Args:
        prior_dates: Backup dates already present under ``daily/``.
        fail_upload_after: Raise a ``ClientError`` on the put_object call after this
            many successful ones; ``None`` means every upload succeeds.
        sentinel_present: When False, the sentinel ``head_object`` 404s.

    Returns:
        A configured ``MagicMock`` standing in for the boto3 S3 client.
    """
    client = MagicMock()
    stored: dict[str, str] = {}

    def _put(**kwargs: object) -> dict[str, str]:
        if fail_upload_after is not None and len(stored) >= fail_upload_after:
            raise _client_error("500", "PutObject")
        key = str(kwargs["Key"])
        etag = f'"etag-{len(stored)}"'
        stored[key] = etag
        return {"ETag": etag}

    def _head(**kwargs: object) -> dict[str, str]:
        key = str(kwargs["Key"])
        if key == backup_database._BUCKET_SENTINEL_KEY and not sentinel_present:
            raise _client_error("404")
        if key in stored:
            return {"ETag": stored[key]}
        return {}

    client.put_object.side_effect = _put
    client.head_object.side_effect = _head
    client.get_bucket_lifecycle_configuration.return_value = {"Rules": []}
    client.list_objects_v2.return_value = {
        "CommonPrefixes": [{"Prefix": f"daily/{date}/"} for date in prior_dates],
        "IsTruncated": False,
    }
    return client


def test_tiers_for_date_weekday_is_daily_only() -> None:
    # 2026-08-04 is a Tuesday.
    tiers = backup_database.tiers_for_date(datetime(2026, 8, 4, tzinfo=UTC))
    assert tiers == ("daily",)


def test_tiers_for_date_sunday_adds_weekly() -> None:
    # 2026-08-02 is a Sunday.
    tiers = backup_database.tiers_for_date(datetime(2026, 8, 2, tzinfo=UTC))
    assert tiers == ("daily", "weekly")


def test_tiers_for_date_first_of_month_adds_monthly() -> None:
    # 2026-09-01 is a Tuesday.
    tiers = backup_database.tiers_for_date(datetime(2026, 9, 1, tzinfo=UTC))
    assert tiers == ("daily", "monthly")


def test_tiers_for_date_sunday_and_first_adds_both() -> None:
    # 2026-11-01 is a Sunday.
    tiers = backup_database.tiers_for_date(datetime(2026, 11, 1, tzinfo=UTC))
    assert tiers == ("daily", "weekly", "monthly")


def test_load_encryption_key_accepts_valid_32_byte_key() -> None:
    key = backup_database.load_encryption_key(_VALID_KEY)
    assert key == b"0" * 32


def test_load_encryption_key_rejects_wrong_length() -> None:
    short_key = base64.b64encode(b"too-short").decode()
    with pytest.raises(ValueError, match="32 bytes"):
        backup_database.load_encryption_key(short_key)


def test_load_encryption_key_rejects_invalid_base64() -> None:
    with pytest.raises(ValueError, match="base64"):
        backup_database.load_encryption_key("not base64!!!")


def test_encrypt_decrypt_round_trip() -> None:
    key = backup_database.load_encryption_key(_VALID_KEY)
    plaintext = b"-- a fake sql dump\nCREATE TABLE t();\n"
    blob = backup_database.encrypt_bytes(plaintext, key)
    assert blob != plaintext
    assert backup_database.decrypt_bytes(blob, key) == plaintext


def test_decrypt_fails_closed_on_wrong_key() -> None:
    key = backup_database.load_encryption_key(_VALID_KEY)
    other_key = b"1" * 32
    blob = backup_database.encrypt_bytes(b"secret", key)
    with pytest.raises(InvalidTag):
        backup_database.decrypt_bytes(blob, other_key)


def test_decrypt_fails_closed_on_tampered_ciphertext() -> None:
    key = backup_database.load_encryption_key(_VALID_KEY)
    blob = bytearray(backup_database.encrypt_bytes(b"secret", key))
    blob[-1] ^= 0xFF
    with pytest.raises(InvalidTag):
        backup_database.decrypt_bytes(bytes(blob), key)


def test_ensure_lifecycle_rules_asserts_three_prefixed_rules() -> None:
    client = _mock_backup_client()
    policy = backup_database.RetentionPolicy(
        daily_days=7, weekly_days=28, monthly_days=180
    )
    backup_database.ensure_lifecycle_rules(client, "backup-bucket", policy)
    client.put_bucket_lifecycle_configuration.assert_called_once()
    call = client.put_bucket_lifecycle_configuration.call_args
    assert call.kwargs["Bucket"] == "backup-bucket"
    rules = call.kwargs["LifecycleConfiguration"]["Rules"]
    by_prefix = {r["Filter"]["Prefix"]: r["Expiration"]["Days"] for r in rules}
    assert by_prefix == {"daily/": 7, "weekly/": 28, "monthly/": 180}


def test_ensure_lifecycle_rules_tolerates_a_lifecycle_read_denied_by_the_token() -> (
    None
):
    """An object-scoped R2 token cannot read bucket config; that is not a failed backup.

    R2 scopes API tokens by permission CLASS: an object-level token (put/get/head/list
    objects) is refused every BUCKET-level call, lifecycle included. This project issues
    an object-scoped token on purpose, so the three expiry rules are configured by hand
    on the bucket and this script reports rather than asserts them. Treating the refusal
    as fatal would have made every night's run red AFTER it had already uploaded three
    good objects.
    """
    client = _mock_backup_client()
    client.get_bucket_lifecycle_configuration.side_effect = _client_error(
        "AccessDenied", "GetBucketLifecycleConfiguration"
    )
    policy = backup_database.RetentionPolicy()

    with patch.object(backup_database._logger, "warning") as warn:
        backup_database.ensure_lifecycle_rules(client, "backup-bucket", policy)

    # Assert the READ was actually attempted, not just that the event fired: a
    # regression that skipped lifecycle entirely and warned anyway would otherwise pass.
    client.get_bucket_lifecycle_configuration.assert_called_once_with(
        Bucket="backup-bucket"
    )
    # The write is skipped, not merely attempted-and-swallowed: put_bucket_lifecycle_
    # configuration REPLACES the whole configuration, so firing it blind would destroy
    # hand-set rules this run could not read.
    client.put_bucket_lifecycle_configuration.assert_not_called()
    # Both degraded paths log the SAME event name, so the event alone cannot tell them
    # apart; the operation kwarg is what identifies which call was refused.
    assert warn.call_args.args[0] == "backup_lifecycle_unmanaged"
    assert warn.call_args.kwargs["operation"] == "GetBucketLifecycleConfiguration"


def test_ensure_lifecycle_rules_tolerates_a_lifecycle_write_denied_by_the_token() -> (
    None
):
    """A token that can READ bucket config but not write it must not fail the run."""
    client = _mock_backup_client()
    client.put_bucket_lifecycle_configuration.side_effect = _client_error(
        "AccessDenied", "PutBucketLifecycleConfiguration"
    )
    policy = backup_database.RetentionPolicy()

    with patch.object(backup_database._logger, "warning") as warn:
        backup_database.ensure_lifecycle_rules(client, "backup-bucket", policy)

    # The refusal has to come from the WRITE actually being issued; the readable
    # config must not have short-circuited it.
    client.put_bucket_lifecycle_configuration.assert_called_once()
    assert warn.call_args.args[0] == "backup_lifecycle_unmanaged"
    assert warn.call_args.kwargs["operation"] == "PutBucketLifecycleConfiguration"


def test_ensure_lifecycle_rules_still_raises_on_a_non_permission_lifecycle_error() -> (
    None
):
    """Only a permission refusal degrades. A 500 is still a broken run.

    Without this, the tolerance added for the object-scoped token would swallow every
    lifecycle failure, and a genuinely broken bucket would report success.
    """
    client = _mock_backup_client()
    client.put_bucket_lifecycle_configuration.side_effect = _client_error(
        "500", "PutBucketLifecycleConfiguration"
    )
    policy = backup_database.RetentionPolicy()
    with pytest.raises(ClientError):
        backup_database.ensure_lifecycle_rules(client, "backup-bucket", policy)


def test_run_backup_dry_run_makes_no_network_call() -> None:
    with patch.object(backup_database, "_build_client") as build_client:
        result = backup_database.run_backup(
            db_url="",
            r2_account_id="",
            r2_access_key_id="",
            r2_secret_access_key="",
            r2_bucket="",
            encryption_key=b"0" * 32,
            policy=backup_database.RetentionPolicy(),
            dry_run=True,
            now=datetime(2026, 8, 4, tzinfo=UTC),
        )
    build_client.assert_not_called()
    assert result["date"] == "2026-08-04"
    assert result["tiers"] == ["daily"]
    assert len(result["uploaded"]) == 3  # roles + schema + data, daily tier only


def test_run_backup_rejects_empty_dump(tmp_path: Path) -> None:
    def _write_empty(
        _db_url: str, out_path: Path, _extra_args: tuple[str, ...]
    ) -> None:
        out_path.write_text("")

    patched_client = patch.object(
        backup_database, "_build_client", return_value=_mock_backup_client()
    )
    patched_dump_leg = patch.object(
        backup_database, "run_dump_leg", side_effect=_write_empty
    )
    policy = backup_database.RetentionPolicy()
    now = datetime(2026, 8, 4, tzinfo=UTC)

    with patched_client, patched_dump_leg, pytest.raises(RuntimeError, match="empty"):
        backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=policy,
            dry_run=False,
            now=now,
        )


def _leg_writer(content_by_filename: dict[str, str]):
    def _write(_db_url: str, out_path: Path, _extra_args: tuple[str, ...]) -> None:
        out_path.write_text(content_by_filename[out_path.name])

    return _write


def test_run_backup_rejects_boilerplate_only_roles_dump() -> None:
    """Load-bearing regression test: boilerplate-only roles.sql must be rejected.

    This is the exact shape a real ``supabase db dump --role-only`` produces when the
    dump connected successfully but the target has no custom roles to report (wrong
    project ref, revoked grant, wrong search_path): pg_dump/pg_dumpall boilerplate,
    zero whitespace-only content, and no restorable roles. The old
    ``if not plaintext.strip()`` guard passes this silently because it is
    non-whitespace bytes; run this test against that implementation and it fails
    (no RuntimeError is raised).
    """
    writer = _leg_writer(
        {
            "roles.sql": _BOILERPLATE_ROLES_SQL,
            "schema.sql": _REAL_SCHEMA_SQL,
            "data.sql": _REAL_DATA_SQL,
        }
    )
    patched_client = patch.object(
        backup_database, "_build_client", return_value=_mock_backup_client()
    )
    patched_dump_leg = patch.object(backup_database, "run_dump_leg", side_effect=writer)
    policy = backup_database.RetentionPolicy()
    now = datetime(2026, 8, 4, tzinfo=UTC)

    with (
        patched_client,
        patched_dump_leg,
        pytest.raises(RuntimeError, match=r"roles\.sql"),
    ):
        backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=policy,
            dry_run=False,
            now=now,
        )


def test_run_backup_rejects_boilerplate_only_schema_dump() -> None:
    """Boilerplate-only schema.sql (no CREATE TABLE) must be rejected."""
    writer = _leg_writer(
        {
            "roles.sql": _REAL_ROLES_SQL,
            "schema.sql": _BOILERPLATE_SCHEMA_SQL,
            "data.sql": _REAL_DATA_SQL,
        }
    )
    patched_client = patch.object(
        backup_database, "_build_client", return_value=_mock_backup_client()
    )
    patched_dump_leg = patch.object(backup_database, "run_dump_leg", side_effect=writer)
    policy = backup_database.RetentionPolicy()
    now = datetime(2026, 8, 4, tzinfo=UTC)

    with (
        patched_client,
        patched_dump_leg,
        pytest.raises(RuntimeError, match=r"schema\.sql"),
    ):
        backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=policy,
            dry_run=False,
            now=now,
        )


def test_run_backup_rejects_boilerplate_only_data_dump() -> None:
    """Boilerplate-only data.sql (no COPY ... FROM stdin) must be rejected."""
    writer = _leg_writer(
        {
            "roles.sql": _REAL_ROLES_SQL,
            "schema.sql": _REAL_SCHEMA_SQL,
            "data.sql": _BOILERPLATE_DATA_SQL,
        }
    )
    patched_client = patch.object(
        backup_database, "_build_client", return_value=_mock_backup_client()
    )
    patched_dump_leg = patch.object(backup_database, "run_dump_leg", side_effect=writer)
    policy = backup_database.RetentionPolicy()
    now = datetime(2026, 8, 4, tzinfo=UTC)

    with (
        patched_client,
        patched_dump_leg,
        pytest.raises(RuntimeError, match=r"data\.sql"),
    ):
        backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=policy,
            dry_run=False,
            now=now,
        )


def test_run_backup_uploads_nothing_when_a_later_leg_fails() -> None:
    """No R2 upload happens for any leg unless all three legs pass validation.

    Regression test for the partial-backup finding: leg 1 (roles) and leg 2 (schema)
    are valid, leg 3 (data) is boilerplate-only. Nothing must reach R2 for any of the
    three legs, not just the failing one.
    """
    writer = _leg_writer(
        {
            "roles.sql": _REAL_ROLES_SQL,
            "schema.sql": _REAL_SCHEMA_SQL,
            "data.sql": _BOILERPLATE_DATA_SQL,
        }
    )
    mock_client = _mock_backup_client()
    patched_client = patch.object(
        backup_database, "_build_client", return_value=mock_client
    )
    patched_dump_leg = patch.object(backup_database, "run_dump_leg", side_effect=writer)
    policy = backup_database.RetentionPolicy()
    now = datetime(2026, 8, 4, tzinfo=UTC)

    with (
        patched_client,
        patched_dump_leg,
        pytest.raises(RuntimeError, match=r"data\.sql"),
    ):
        backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=policy,
            dry_run=False,
            now=now,
        )
    mock_client.put_object.assert_not_called()


def test_run_backup_does_not_touch_lifecycle_when_a_leg_fails() -> None:
    """A run that fails its dump must not leave a lifecycle change on the bucket.

    ``ensure_lifecycle_rules`` used to run BEFORE the first dump, so a run that passed
    a bad retention value and then failed still landed the destructive, PERSISTENT
    lifecycle change. The operator saw a red run, went debugging the dump, and R2 kept
    expiring good backups underneath them. Ordering it last is the fix; this pins it.
    """
    writer = _leg_writer(
        {
            "roles.sql": _REAL_ROLES_SQL,
            "schema.sql": _REAL_SCHEMA_SQL,
            "data.sql": _BOILERPLATE_DATA_SQL,
        }
    )
    mock_client = _mock_backup_client()
    patched_client = patch.object(
        backup_database, "_build_client", return_value=mock_client
    )
    patched_dump_leg = patch.object(backup_database, "run_dump_leg", side_effect=writer)
    # Deliberately not the defaults: if the call happened at all, it would
    # apply these.
    policy = backup_database.RetentionPolicy(
        daily_days=3, weekly_days=14, monthly_days=90
    )
    now = datetime(2026, 8, 4, tzinfo=UTC)

    with (
        patched_client,
        patched_dump_leg,
        pytest.raises(RuntimeError, match=r"data\.sql"),
    ):
        backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=policy,
            dry_run=False,
            now=now,
        )
    mock_client.put_bucket_lifecycle_configuration.assert_not_called()


def test_run_backup_uploads_each_leg_to_every_applicable_tier() -> None:
    writer = _leg_writer(dict(_ALL_LEGS_REAL))

    mock_client = _mock_backup_client()
    with (
        patch.object(backup_database, "_build_client", return_value=mock_client),
        patch.object(backup_database, "run_dump_leg", side_effect=writer),
    ):
        result = backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=backup_database.RetentionPolicy(),
            dry_run=False,
            # 2026-08-02 is a Sunday: daily + weekly tiers.
            now=datetime(2026, 8, 2, tzinfo=UTC),
        )

    mock_client.put_bucket_lifecycle_configuration.assert_called_once()
    assert mock_client.put_object.call_count == 6  # 3 legs x 2 tiers
    # The single most valuable assertion a backup system can make about a good run:
    # it deleted NOTHING. Without it a stray delete is absorbed silently by the mock.
    mock_client.delete_object.assert_not_called()
    assert sorted(result["uploaded"]) == [
        "daily/2026-08-02/data.sql.enc",
        "daily/2026-08-02/roles.sql.enc",
        "daily/2026-08-02/schema.sql.enc",
        "weekly/2026-08-02/data.sql.enc",
        "weekly/2026-08-02/roles.sql.enc",
        "weekly/2026-08-02/schema.sql.enc",
    ]
    # Leg-major, tier-minor, in _DUMP_LEGS order. The rollback test depends on this
    # order to know which keys a mid-loop failure had already written, so an
    # accidental reordering must fail here rather than silently there.
    assert result["uploaded"] == [
        "daily/2026-08-02/roles.sql.enc",
        "weekly/2026-08-02/roles.sql.enc",
        "daily/2026-08-02/schema.sql.enc",
        "weekly/2026-08-02/schema.sql.enc",
        "daily/2026-08-02/data.sql.enc",
        "weekly/2026-08-02/data.sql.enc",
    ]


def test_run_backup_sets_lifecycle_only_after_every_upload_succeeds() -> None:
    """The lifecycle write is the LAST R2 call, after all six uploads and the probe."""
    writer = _leg_writer(dict(_ALL_LEGS_REAL))
    mock_client = _mock_backup_client()

    with (
        patch.object(backup_database, "_build_client", return_value=mock_client),
        patch.object(backup_database, "run_dump_leg", side_effect=writer),
    ):
        backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=backup_database.RetentionPolicy(),
            dry_run=False,
            now=datetime(2026, 8, 4, tzinfo=UTC),
        )

    # MagicMock records every child call on the parent in order, so this reads the
    # real sequence rather than a re-implementation of it.
    interesting = {
        "put_object",
        "list_objects_v2",
        "put_bucket_lifecycle_configuration",
    }
    calls = [name for name, _args, _kwargs in mock_client.method_calls]
    assert [name for name in calls if name in interesting] == [
        "put_object",
        "put_object",
        "put_object",
        "list_objects_v2",
        "put_bucket_lifecycle_configuration",
    ], f"unexpected R2 call order: {calls}"


def test_run_backup_rolls_back_uploaded_keys_when_a_later_upload_fails() -> None:
    """A mid-loop upload failure deletes the keys this run already wrote.

    Validation passing for all three legs only guarantees nothing bad reaches R2
    BEFORE the loop. Once the loop starts, a network blip or a credential revoked
    mid-sequence can still land some objects, which would leave a partial set under
    that date's prefix and read as a usable backup to anyone listing the bucket.
    """
    writer = _leg_writer(dict(_ALL_LEGS_REAL))
    # Upload order is leg-major, tier-minor: roles/daily, roles/weekly, schema/daily,
    # then schema/weekly, which is the one that fails here.
    mock_client = _mock_backup_client(fail_upload_after=3)
    patched_client = patch.object(
        backup_database, "_build_client", return_value=mock_client
    )
    patched_dump_leg = patch.object(backup_database, "run_dump_leg", side_effect=writer)
    policy = backup_database.RetentionPolicy()
    now = datetime(2026, 8, 2, tzinfo=UTC)

    with patched_client, patched_dump_leg, pytest.raises(ClientError):
        backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=policy,
            dry_run=False,
            # 2026-08-02 is a Sunday: daily + weekly tiers, so 6 planned uploads.
            now=now,
        )

    deleted = [call.kwargs["Key"] for call in mock_client.delete_object.call_args_list]
    # Newest first, and only the three that actually succeeded: the failed key was
    # never appended, and the two never-attempted keys must not be deleted either.
    assert deleted == [
        "daily/2026-08-02/schema.sql.enc",
        "weekly/2026-08-02/roles.sql.enc",
        "daily/2026-08-02/roles.sql.enc",
    ]


def test_rollback_uploads_continues_after_a_failed_delete() -> None:
    """One failed delete neither aborts the rollback nor masks the original error."""
    mock_client = MagicMock()
    mock_client.head_object.return_value = {"ETag": '"same"'}
    mock_client.delete_object.side_effect = [
        ClientError({"Error": {"Code": "500", "Message": "boom"}}, "DeleteObject"),
        None,
        None,
    ]

    # Must not raise: the caller re-raises the original upload error instead.
    backup_database._rollback_uploads(
        mock_client,
        "backup-bucket",
        [
            ("daily/2026-08-02/roles.sql.enc", '"same"'),
            ("daily/2026-08-02/schema.sql.enc", '"same"'),
            ("k3", '"same"'),
        ],
    )

    assert mock_client.delete_object.call_count == 3


def test_rollback_uploads_skips_an_object_another_run_replaced() -> None:
    """An ETag that no longer matches means someone else owns the object now.

    Keys are date-derived, so a concurrent run computes the same key. Deleting on key
    alone would let this run's rollback destroy the other run's completed backup.
    """
    mock_client = MagicMock()
    # Newest first: k2 is checked before the roles key, and it is the one this run
    # still owns. The roles key came back with a stranger's ETag.
    mock_client.head_object.side_effect = [
        {"ETag": '"mine-2"'},
        {"ETag": '"written-by-someone-else"'},
    ]

    backup_database._rollback_uploads(
        mock_client,
        "backup-bucket",
        [("daily/2026-08-02/roles.sql.enc", '"mine-1"'), ("k2", '"mine-2"')],
    )

    # Only the object whose ETag still matches is deleted.
    deleted = [call.kwargs["Key"] for call in mock_client.delete_object.call_args_list]
    assert deleted == ["k2"]


def test_rollback_uploads_deletes_when_the_upload_reported_no_etag() -> None:
    """A missing ETag cannot guard anything, so the delete proceeds unguarded.

    Better a best-effort cleanup than a permanently orphaned partial set; the
    concurrency window this reopens is already closed by the workflow's
    ``concurrency:`` group.
    """
    mock_client = MagicMock()

    backup_database._rollback_uploads(mock_client, "backup-bucket", [("k1", None)])

    mock_client.head_object.assert_not_called()
    assert mock_client.delete_object.call_args.kwargs["Key"] == "k1"


def test_run_dump_leg_invokes_supabase_cli_with_direct_db_url(tmp_path: Path) -> None:
    out_path = tmp_path / "schema.sql"
    with patch.object(backup_database.subprocess, "run") as mock_run:
        backup_database.run_dump_leg("postgresql://direct", out_path, ())
    args = mock_run.call_args.args[0]
    assert args[:4] == ["supabase", "db", "dump", "--db-url"]
    assert "postgresql://direct" in args


def test_run_dump_leg_propagates_cli_failure(tmp_path: Path) -> None:
    out_path = tmp_path / "schema.sql"
    with (
        patch.object(
            backup_database.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, "supabase"),
        ),
        pytest.raises(subprocess.CalledProcessError),
    ):
        backup_database.run_dump_leg("postgresql://direct", out_path, ())


def test_strip_credentials_moves_password_out_of_the_url() -> None:
    sanitized, env = backup_database._strip_credentials_from_db_url(
        "postgresql://<user>:<password>@<host>:5432/<dbname>"
    )
    assert env == {"PGPASSWORD": "<password>"}
    assert "<password>" not in sanitized
    assert sanitized == "postgresql://<user>@<host>:5432/<dbname>"


def test_strip_credentials_passes_through_urls_with_no_password() -> None:
    sanitized, env = backup_database._strip_credentials_from_db_url(
        "postgresql://direct"
    )
    assert env == {}
    assert sanitized == "postgresql://direct"


def test_strip_credentials_percent_decodes_the_password() -> None:
    """``urlsplit().password`` returns the RAW field, still percent-encoded.

    Handing that to PGPASSWORD authenticates with the literal ``%40`` text rather than
    the ``@`` the password actually is, so every dump fails with a bare auth error
    whenever the generated password contains a reserved character.
    """
    sanitized, env = backup_database._strip_credentials_from_db_url(
        "postgresql://<user>%40admin:p%40ss%3Aw%2Frd%20x@<host>:5432/<dbname>"
    )

    assert env == {"PGPASSWORD": "p@ss:w/rd x"}
    # The username stays encoded: it is still going through URL parsing on the far side.
    assert sanitized == "postgresql://<user>%40admin@<host>:5432/<dbname>"


def test_strip_credentials_moves_query_parameter_password_out_of_the_url() -> None:
    """libpq also accepts the password as a URI query parameter.

    ``urlsplit().password`` never sees that form, so before this the password stayed in
    argv (and in every error message quoting the URL).
    """
    sanitized, env = backup_database._strip_credentials_from_db_url(
        "postgresql://<user>@<host>:5432/<dbname>?password=<secret>&sslmode=require"
    )

    assert env == {"PGPASSWORD": "<secret>"}
    assert "<secret>" not in sanitized
    # Non-credential parameters are connection-relevant and must survive.
    assert sanitized == "postgresql://<user>@<host>:5432/<dbname>?sslmode=require"


def test_strip_credentials_prefers_the_userinfo_password() -> None:
    """libpq resolves the userinfo password over the query parameter; so do we."""
    _sanitized, env = backup_database._strip_credentials_from_db_url(
        "postgresql://<user>:<userinfo>@<host>/<dbname>?password=<fromquery>"
    )

    # The two placeholders differ so the assertion can tell which slot won.
    assert env == {"PGPASSWORD": "<userinfo>"}


def test_strip_credentials_moves_passfile_to_the_environment() -> None:
    """``passfile`` names a credential file and belongs in env, not argv."""
    sanitized, env = backup_database._strip_credentials_from_db_url(
        "postgresql://<user>@<host>/<dbname>?passfile=/run/secrets/pgpass"
    )

    assert env == {"PGPASSFILE": "/run/secrets/pgpass"}
    assert "passfile" not in sanitized


def test_strip_credentials_brackets_ipv6_hosts() -> None:
    """Rebuilding the netloc must not drop the brackets an IPv6 literal needs.

    Without them the address's own colons read as a port separator and the URL no
    longer parses, so the dump fails on a host that was perfectly valid going in.
    """
    sanitized, env = backup_database._strip_credentials_from_db_url(
        "postgresql://<user>:pw@[2001:db8::1]:5432/<dbname>"
    )

    assert env == {"PGPASSWORD": "pw"}
    assert sanitized == "postgresql://<user>@[2001:db8::1]:5432/<dbname>"


def test_run_dump_leg_env_excludes_unrelated_secrets() -> None:
    """The CLI subprocess gets an allowlisted env, never a copy of this process's.

    ``os.environ.copy()`` handed the dump subprocess BACKUP_ENCRYPTION_KEY and both R2
    keys, which defeats the point of keeping the password out of argv.
    """
    leaked = {
        "BACKUP_ENCRYPTION_KEY": _VALID_KEY,
        "R2_BACKUP_SECRET_ACCESS_KEY": "secret",
        "SUPABASE_DB_URL": "postgresql://<user>:<password>@<host>/<db>",
        "PATH": "/usr/bin",
    }
    with (
        patch.dict(backup_database.os.environ, leaked, clear=True),
        patch.object(backup_database.subprocess, "run") as mock_run,
    ):
        backup_database.run_dump_leg(
            "postgresql://<user>:pw@<host>/<dbname>", Path("/tmp/out.sql"), ()
        )

    call_env = mock_run.call_args.kwargs["env"]
    assert call_env["PATH"] == "/usr/bin"
    assert call_env["PGPASSWORD"] == "pw"
    assert "BACKUP_ENCRYPTION_KEY" not in call_env
    assert "R2_BACKUP_SECRET_ACCESS_KEY" not in call_env
    assert "SUPABASE_DB_URL" not in call_env


def test_run_dump_leg_never_puts_password_in_argv(tmp_path: Path) -> None:
    out_path = tmp_path / "schema.sql"
    with patch.object(backup_database.subprocess, "run") as mock_run:
        backup_database.run_dump_leg(
            "postgresql://<user>:<password>@<host>:5432/<dbname>", out_path, ()
        )
    args = mock_run.call_args.args[0]
    assert "<password>" not in " ".join(args)
    assert "--db-url" in args
    db_url_arg = args[args.index("--db-url") + 1]
    assert db_url_arg == "postgresql://<user>@<host>:5432/<dbname>"
    call_env = mock_run.call_args.kwargs["env"]
    assert call_env["PGPASSWORD"] == "<password>"


def test_run_dump_leg_omits_pgpassword_when_url_has_no_password(
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "schema.sql"
    with patch.object(backup_database.subprocess, "run") as mock_run:
        backup_database.run_dump_leg("postgresql://direct", out_path, ())
    call_env = mock_run.call_args.kwargs["env"]
    assert "PGPASSWORD" not in call_env


def test_redact_secrets_scrubs_url_password() -> None:
    text = (
        "connection failed: could not connect to "
        "postgresql://<user>:<password>@<host>:5432/<dbname>"
    )
    redacted = backup_database._redact_secrets(text)
    assert "<password>" not in redacted
    assert "postgres://[redacted]@" in redacted or "postgresql://[redacted]@" in (
        redacted
    )


def test_redact_secrets_scrubs_password_containing_at_sign() -> None:
    """An unencoded ``@`` inside the password must not end the redaction early.

    libpq accepts it, so it occurs in real connection strings. A password class that
    excluded ``@`` would stop at the first one and leave the remainder in the log.

    Per the module-level fixture convention, the ``@`` lives inside an angle-bracket
    placeholder: the shape under test is preserved without a realistic password literal.
    """
    text = "connection failed: postgresql://<user>:<pass@tail>@<host>:5432/<dbname>"

    redacted = backup_database._redact_secrets(text)

    assert "<pass@tail>" not in redacted
    # The tail after the first `@` is the part a naive password class would leak.
    assert "tail>" not in redacted
    assert "postgresql://[redacted]@<host>:5432/<dbname>" in redacted


def test_redact_secrets_scrubs_conninfo_password() -> None:
    """libpq's keyword/value form carries no ``://``, so the URL pattern cannot see it."""
    text = (
        "could not connect: host=<host> user=<user> password=<secret> dbname=<dbname>"
    )

    redacted = backup_database._redact_secrets(text)

    assert "<secret>" not in redacted
    assert "password=[redacted]" in redacted
    # Non-credential keywords are diagnostic and must survive.
    assert "host=<host>" in redacted


def test_decode_process_output_returns_empty_string_for_none() -> None:
    assert backup_database._decode_process_output(None) == ""
    assert backup_database._decode_process_output(b"") == ""


def test_decode_process_output_redacts_and_truncates() -> None:
    long_tail = "x" * (backup_database._ERROR_OUTPUT_TRUNCATE_CHARS + 500)
    data = f"postgresql://<user>:<password>@<host>/<db> {long_tail}".encode()
    result = backup_database._decode_process_output(data)
    assert "<password>" not in result
    assert "truncated" in result
    assert len(result) < len(long_tail) + 200


def test_main_prints_redacted_stderr_on_dump_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {
        "SUPABASE_DB_URL": "postgresql://<user>:<password>@<host>/<db>",
        "R2_ACCOUNT_ID": "acct",
        "R2_BACKUP_ACCESS_KEY_ID": "key",
        "R2_BACKUP_SECRET_ACCESS_KEY": "secret",
        "R2_BACKUP_BUCKET": "bucket",
        "BACKUP_ENCRYPTION_KEY": _VALID_KEY,
    }
    failure = subprocess.CalledProcessError(
        1,
        "supabase",
        output=b"stdout is fine",
        stderr=(
            b"FATAL: could not connect to "
            b"postgresql://<user>:<password>@<host>/<db>: connection refused"
        ),
    )
    with (
        patch.object(backup_database.sys, "argv", ["backup_database.py"]),
        patch.dict(backup_database.os.environ, env, clear=True),
        patch.object(backup_database, "run_backup", side_effect=failure),
        pytest.raises(SystemExit),
    ):
        backup_database.main()
    captured = capsys.readouterr()
    assert "<password>" not in captured.out
    assert "connection refused" in captured.out
    assert "[redacted]@" in captured.out


def test_retention_policy_rejects_non_positive_days() -> None:
    """Zero or negative days is not a retention policy, it is an immediate purge."""
    with pytest.raises(ValueError, match="at least 1"):
        backup_database.RetentionPolicy(daily_days=0, weekly_days=28, monthly_days=180)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"daily_days": 1, "weekly_days": 28, "monthly_days": 180}, "--daily-days"),
        ({"daily_days": 7, "weekly_days": 10, "monthly_days": 180}, "--weekly-days"),
        ({"daily_days": 7, "weekly_days": 28, "monthly_days": 30}, "--monthly-days"),
    ],
)
def test_retention_policy_rejects_sub_floor_days(
    kwargs: dict[str, int], expected: str
) -> None:
    """Each tier has a documented floor, and each is enforced independently.

    A single mistyped workflow input used to reach R2 as a lifecycle rule that expires
    good backups, with nothing between the typo and the deletion.
    """
    with pytest.raises(ValueError, match=expected):
        backup_database.RetentionPolicy(**kwargs)


def test_retention_policy_rejects_inverted_ordering() -> None:
    """Tiers that promote upward must also retain upward.

    A monthly tier that expires before the daily tier makes promotion pointless: the
    long-horizon copy disappears first, which is the opposite of what GFS is for.
    """
    with pytest.raises(ValueError, match="non-decreasing"):
        backup_database.RetentionPolicy(daily_days=30, weekly_days=28, monthly_days=180)


def test_retention_policy_force_waives_floors_but_not_ordering() -> None:
    """``--force-retention`` is an escape hatch for a deliberate shrink, not a bypass."""
    policy = backup_database.RetentionPolicy(
        daily_days=1, weekly_days=2, monthly_days=3, force=True
    )
    assert policy.daily_days == 1

    with pytest.raises(ValueError, match="non-decreasing"):
        backup_database.RetentionPolicy(
            daily_days=3, weekly_days=2, monthly_days=1, force=True
        )


def test_retention_policy_rejects_positional_construction() -> None:
    """Three same-typed ints in a row are a silent-swap hazard, so keywords are forced.

    ``RetentionPolicy(180, 28, 7)`` reads plausibly and would have set a 180-day daily
    tier and a 7-day monthly tier. ``kw_only=True`` makes that unwritable.
    """
    with pytest.raises(TypeError):
        backup_database.RetentionPolicy(7, 28, 180)  # pyright: ignore[reportCallIssue]


def test_verify_backup_bucket_refuses_a_bucket_without_the_sentinel() -> None:
    """An unmarked bucket could be any bucket, including the public covers bucket."""
    client = _mock_backup_client(sentinel_present=False)

    with pytest.raises(RuntimeError, match="marker object"):
        backup_database.verify_backup_bucket(client, "some-other-bucket")

    client.put_object.assert_not_called()


def test_verify_backup_bucket_creates_the_sentinel_under_init_bucket() -> None:
    client = _mock_backup_client(sentinel_present=False)

    backup_database.verify_backup_bucket(client, "backup-bucket", init_bucket=True)

    assert (
        client.put_object.call_args.kwargs["Key"]
        == backup_database._BUCKET_SENTINEL_KEY
    )


def test_verify_backup_bucket_propagates_a_non_404_error() -> None:
    """A 403 is a credential problem, not an uninitialized bucket.

    Folding it into the not-found branch would let ``--init-bucket`` "fix" a permissions
    outage by writing a sentinel it cannot even read back.
    """
    client = MagicMock()
    client.head_object.side_effect = _client_error("403")

    with pytest.raises(ClientError):
        backup_database.verify_backup_bucket(client, "backup-bucket")


def test_run_backup_aborts_before_dumping_when_the_sentinel_is_missing() -> None:
    """Bucket verification runs first, so an unverified bucket costs zero dumps."""
    client = _mock_backup_client(sentinel_present=False)
    dump = MagicMock()

    patched_client = patch.object(backup_database, "_build_client", return_value=client)
    patched_dump_leg = patch.object(backup_database, "run_dump_leg", dump)
    policy = backup_database.RetentionPolicy()
    now = datetime(2026, 8, 4, tzinfo=UTC)

    with (
        patched_client,
        patched_dump_leg,
        pytest.raises(RuntimeError, match="marker object"),
    ):
        backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=policy,
            dry_run=False,
            now=now,
        )

    dump.assert_not_called()
    client.put_bucket_lifecycle_configuration.assert_not_called()


def test_assert_recent_backup_exists_accepts_a_fresh_prior_backup() -> None:
    client = _mock_backup_client(prior_dates=("2026-08-01", "2026-08-03"))

    backup_database.assert_recent_backup_exists(
        client,
        "backup-bucket",
        today=datetime(2026, 8, 4, tzinfo=UTC),
        exclude_date="2026-08-04",
        allow_empty=False,
    )


def test_assert_recent_backup_exists_rejects_a_stale_newest_backup() -> None:
    """A gap wider than the threshold means the schedule stopped and nobody noticed."""
    client = _mock_backup_client(prior_dates=("2026-07-20",))
    today = datetime(2026, 8, 4, tzinfo=UTC)

    with pytest.raises(RuntimeError, match="gap threshold"):
        backup_database.assert_recent_backup_exists(
            client,
            "backup-bucket",
            today=today,
            exclude_date="2026-08-04",
            allow_empty=False,
        )


def test_assert_recent_backup_exists_ignores_this_runs_own_date() -> None:
    """The check measures the history that existed BEFORE this run.

    Counting today's freshly-written objects would make the check pass on every run,
    including the one where retention had already destroyed everything else.
    """
    client = _mock_backup_client(prior_dates=("2026-08-04",))
    today = datetime(2026, 8, 4, tzinfo=UTC)

    with pytest.raises(RuntimeError, match="holds no backup"):
        backup_database.assert_recent_backup_exists(
            client,
            "backup-bucket",
            today=today,
            exclude_date="2026-08-04",
            allow_empty=False,
        )


def test_assert_recent_backup_exists_rejects_an_empty_bucket_without_init() -> None:
    """An empty bucket is either a first run or a data-loss incident, never a pass."""
    client = _mock_backup_client(prior_dates=())
    today = datetime(2026, 8, 4, tzinfo=UTC)

    with pytest.raises(RuntimeError, match="--init-bucket"):
        backup_database.assert_recent_backup_exists(
            client,
            "backup-bucket",
            today=today,
            exclude_date="2026-08-04",
            allow_empty=False,
        )


def test_assert_recent_backup_exists_allows_an_empty_bucket_under_init_bucket() -> None:
    """The genuine first run is the documented exception, taken only on request."""
    client = _mock_backup_client(prior_dates=())

    backup_database.assert_recent_backup_exists(
        client,
        "backup-bucket",
        today=datetime(2026, 8, 4, tzinfo=UTC),
        exclude_date="2026-08-04",
        allow_empty=True,
    )


def test_assert_recent_backup_exists_propagates_a_list_failure() -> None:
    """A failed list means "I could not check", which is never "backups are fine"."""
    client = _mock_backup_client()
    client.list_objects_v2.side_effect = _client_error("403", "ListObjectsV2")
    today = datetime(2026, 8, 4, tzinfo=UTC)

    with pytest.raises(ClientError):
        backup_database.assert_recent_backup_exists(
            client,
            "backup-bucket",
            today=today,
            exclude_date="2026-08-04",
            allow_empty=True,
        )


def test_list_backup_dates_ignores_non_date_prefixes() -> None:
    """A stray prefix must not be counted as a backup that never happened."""
    client = MagicMock()
    client.list_objects_v2.return_value = {
        "CommonPrefixes": [
            {"Prefix": "daily/2026-08-01/"},
            {"Prefix": "daily/tmp-restore/"},
        ],
        "IsTruncated": False,
    }

    assert backup_database._list_backup_dates(client, "backup-bucket") == {"2026-08-01"}


def test_run_backup_checks_history_before_writing_lifecycle_rules() -> None:
    """A stale history aborts the run without touching the expiry schedule.

    Ordering matters: today's upload is already safe in R2 when the alarm fires, and
    retention is left exactly as it was rather than re-applied to a bucket that has
    evidently been losing backups.
    """
    client = _mock_backup_client(prior_dates=("2026-07-01",))

    patched_client = patch.object(backup_database, "_build_client", return_value=client)
    patched_dump_leg = patch.object(
        backup_database,
        "run_dump_leg",
        side_effect=_leg_writer(dict(_ALL_LEGS_REAL)),
    )
    policy = backup_database.RetentionPolicy()
    now = datetime(2026, 8, 4, tzinfo=UTC)

    with (
        patched_client,
        patched_dump_leg,
        pytest.raises(RuntimeError, match="gap threshold"),
    ):
        backup_database.run_backup(
            db_url="postgresql://example",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="backup-bucket",
            encryption_key=b"0" * 32,
            policy=policy,
            dry_run=False,
            now=now,
        )

    # Today's three objects stay: an incident should start with MORE good backups.
    assert client.put_object.call_count == 3
    client.delete_object.assert_not_called()
    client.put_bucket_lifecycle_configuration.assert_not_called()


def test_redact_secrets_scrubs_a_query_parameter_password() -> None:
    """The ``?password=`` form has no ``://user:pw@`` shape for the URL pattern to see."""
    text = (
        "connection failed: "
        "postgresql://<user>@<host>:5432/<dbname>?password=<secret>&sslmode=require"
    )

    redacted = backup_database._redact_secrets(text)

    assert "<secret>" not in redacted
    assert "password=[redacted]" in redacted
    # The ampersand must bound the match, or every later parameter vanishes with it.
    assert "sslmode=require" in redacted


def test_main_exits_one_on_a_missing_environment_variable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = dict(_LIVE_ENV)
    del env["R2_BACKUP_BUCKET"]
    with (
        patch.object(backup_database.sys, "argv", ["backup_database.py"]),
        patch.dict(backup_database.os.environ, env, clear=True),
        patch.object(backup_database, "run_backup") as run_backup,
        pytest.raises(SystemExit) as exit_info,
    ):
        backup_database.main()

    assert exit_info.value.code == 1
    run_backup.assert_not_called()
    assert "R2_BACKUP_BUCKET" in capsys.readouterr().out


def test_main_exits_one_on_an_invalid_encryption_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = dict(_LIVE_ENV, BACKUP_ENCRYPTION_KEY=base64.b64encode(b"short").decode())
    with (
        patch.object(backup_database.sys, "argv", ["backup_database.py"]),
        patch.dict(backup_database.os.environ, env, clear=True),
        patch.object(backup_database, "run_backup") as run_backup,
        pytest.raises(SystemExit) as exit_info,
    ):
        backup_database.main()

    assert exit_info.value.code == 1
    run_backup.assert_not_called()
    assert "32" in capsys.readouterr().out


def test_main_exits_one_on_an_out_of_range_retention_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Retention is validated before the dry-run branch and before any secret is read.

    That ordering is what makes a mistyped workflow input cost a fast red run rather
    than a lifecycle rule that R2 has already started acting on.
    """
    argv = ["backup_database.py", "--daily-days", "1"]
    with (
        patch.object(backup_database.sys, "argv", argv),
        patch.dict(backup_database.os.environ, dict(_LIVE_ENV), clear=True),
        patch.object(backup_database, "run_backup") as run_backup,
        pytest.raises(SystemExit) as exit_info,
    ):
        backup_database.main()

    assert exit_info.value.code == 1
    run_backup.assert_not_called()
    assert "--daily-days" in capsys.readouterr().out


def test_main_passes_parsed_retention_through_to_the_lifecycle_rules() -> None:
    """Real argv rendering, all the way to the R2 lifecycle call.

    Every other main() test stops at run_backup; this one runs the whole chain so a
    flag that parses but never reaches the policy would fail here.
    """
    argv = [
        "backup_database.py",
        "--daily-days",
        "5",
        "--weekly-days",
        "30",
        "--monthly-days",
        "90",
    ]
    # main() owns the clock, so the history stub is dated relative to the real one.
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    client = _mock_backup_client(prior_dates=(yesterday,))
    with (
        patch.object(backup_database.sys, "argv", argv),
        patch.dict(backup_database.os.environ, dict(_LIVE_ENV), clear=True),
        patch.object(backup_database, "_build_client", return_value=client),
        patch.object(
            backup_database,
            "run_dump_leg",
            side_effect=_leg_writer(dict(_ALL_LEGS_REAL)),
        ),
    ):
        backup_database.main()

    call = client.put_bucket_lifecycle_configuration.call_args
    rules = call.kwargs["LifecycleConfiguration"]["Rules"]
    by_prefix = {r["Filter"]["Prefix"]: r["Expiration"]["Days"] for r in rules}
    assert by_prefix == {"daily/": 5, "weekly/": 30, "monthly/": 90}


def test_main_redacts_a_query_parameter_password_in_the_exception_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``str(CalledProcessError)`` renders the whole argv list, and this repo is public.

    A LIST-form cmd is what subprocess.run actually raises with, so this exercises the
    real rendering rather than a convenient string.
    """
    db_url = "postgresql://<user>@<host>:5432/<dbname>?password=<secret>"
    failure = subprocess.CalledProcessError(
        1, ["supabase", "db", "dump", "--db-url", db_url, "-f", "/tmp/schema.sql"]
    )
    env = dict(_LIVE_ENV, SUPABASE_DB_URL=db_url)
    with (
        patch.object(backup_database.sys, "argv", ["backup_database.py"]),
        patch.dict(backup_database.os.environ, env, clear=True),
        patch.object(backup_database, "run_backup", side_effect=failure),
        pytest.raises(SystemExit) as exit_info,
    ):
        backup_database.main()

    out = capsys.readouterr().out
    assert exit_info.value.code == 1
    assert "<secret>" not in out
    assert "password=[redacted]" in out
