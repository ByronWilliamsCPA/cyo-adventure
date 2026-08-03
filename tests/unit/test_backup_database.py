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


def test_run_backup_uploads_each_leg_to_every_applicable_tier() -> None:
    written: dict[Path, str] = {}

    def _write_fake_dump(
        _db_url: str, out_path: Path, _extra_args: tuple[str, ...]
    ) -> None:
        out_path.write_text("-- fake dump content\n")
        written[out_path] = out_path.name

    mock_client = MagicMock()
    with (
        patch.object(backup_database, "_build_client", return_value=mock_client),
        patch.object(backup_database, "run_dump_leg", side_effect=_write_fake_dump),
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
