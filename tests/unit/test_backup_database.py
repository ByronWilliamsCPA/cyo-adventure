"""Unit tests for scripts/backup_database.py (no network, no live database).

scripts/ is not an importable package (no __init__.py, by design; see per-file-ignores
INP for scripts/**/*.py in pyproject.toml), so the module is loaded directly from its
file path via importlib, mirroring tests/unit/test_backfill_covers_r2.py.
"""

from __future__ import annotations

import base64
import importlib.util
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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
# (2026-08-04, CLI 2.109.1, Postgres 17.6) for a project with zero custom roles and
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
    client = MagicMock()
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

    with (
        patch.object(backup_database, "_build_client", return_value=MagicMock()),
        patch.object(backup_database, "run_dump_leg", side_effect=_write_empty),
        pytest.raises(RuntimeError, match="empty"),
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
    with (
        patch.object(backup_database, "_build_client", return_value=MagicMock()),
        patch.object(backup_database, "run_dump_leg", side_effect=writer),
        pytest.raises(RuntimeError, match=r"roles\.sql"),
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


def test_run_backup_rejects_boilerplate_only_schema_dump() -> None:
    """Boilerplate-only schema.sql (no CREATE TABLE) must be rejected."""
    writer = _leg_writer(
        {
            "roles.sql": _REAL_ROLES_SQL,
            "schema.sql": _BOILERPLATE_SCHEMA_SQL,
            "data.sql": _REAL_DATA_SQL,
        }
    )
    with (
        patch.object(backup_database, "_build_client", return_value=MagicMock()),
        patch.object(backup_database, "run_dump_leg", side_effect=writer),
        pytest.raises(RuntimeError, match=r"schema\.sql"),
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


def test_run_backup_rejects_boilerplate_only_data_dump() -> None:
    """Boilerplate-only data.sql (no COPY ... FROM stdin) must be rejected."""
    writer = _leg_writer(
        {
            "roles.sql": _REAL_ROLES_SQL,
            "schema.sql": _REAL_SCHEMA_SQL,
            "data.sql": _BOILERPLATE_DATA_SQL,
        }
    )
    with (
        patch.object(backup_database, "_build_client", return_value=MagicMock()),
        patch.object(backup_database, "run_dump_leg", side_effect=writer),
        pytest.raises(RuntimeError, match=r"data\.sql"),
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
    mock_client = MagicMock()
    with (
        patch.object(backup_database, "_build_client", return_value=mock_client),
        patch.object(backup_database, "run_dump_leg", side_effect=writer),
        pytest.raises(RuntimeError, match=r"data\.sql"),
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
    mock_client.put_object.assert_not_called()


def test_run_backup_uploads_each_leg_to_every_applicable_tier() -> None:
    writer = _leg_writer(
        {
            "roles.sql": _REAL_ROLES_SQL,
            "schema.sql": _REAL_SCHEMA_SQL,
            "data.sql": _REAL_DATA_SQL,
        }
    )

    mock_client = MagicMock()
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
    assert sorted(result["uploaded"]) == [
        "daily/2026-08-02/data.sql.enc",
        "daily/2026-08-02/roles.sql.enc",
        "daily/2026-08-02/schema.sql.enc",
        "weekly/2026-08-02/data.sql.enc",
        "weekly/2026-08-02/roles.sql.enc",
        "weekly/2026-08-02/schema.sql.enc",
    ]


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


def test_strip_password_from_db_url_moves_password_out_of_the_url() -> None:
    sanitized, password = backup_database._strip_password_from_db_url(
        "postgresql://<user>:<password>@<host>:5432/<dbname>"
    )
    assert password == "<password>"
    assert "<password>" not in sanitized
    assert sanitized == "postgresql://<user>@<host>:5432/<dbname>"


def test_strip_password_from_db_url_passes_through_urls_with_no_password() -> None:
    sanitized, password = backup_database._strip_password_from_db_url(
        "postgresql://direct"
    )
    assert password is None
    assert sanitized == "postgresql://direct"


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
