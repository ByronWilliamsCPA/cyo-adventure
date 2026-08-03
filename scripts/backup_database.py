"""Dump the Supabase database and ship an encrypted, tiered backup to R2.

Closes the gap `docs/operations/runbook.md` section 6 has documented since Phase 5 as
"no backup script, restore script, or restore runbook anywhere in this repository"
(issue #558, `UW-D27`). Runs three `supabase db dump` legs (roles, schema, data) against
the DIRECT (non-pooled) database connection -- the runbook's Supavisor-pooling warning
applies to any long-lived dump/restore connection, not just this script -- encrypts each
file, and uploads to a dedicated R2 bucket under a tiered prefix.

Tiered retention (GFS rotation), sized for limited R2 space rather than kept forever:

- ``daily/``   always written; expires after ``--daily-days``   (default 7)
- ``weekly/``  written on ISO Sunday; expires after ``--weekly-days``  (default 28)
- ``monthly/`` written on the 1st;    expires after ``--monthly-days`` (default 180)

# #ASSUME: external resources: these day counts are a reasonable GFS default, not a
# measurement of this project's actual dump size or R2 budget -- nobody has run this
# against the live database yet. #VERIFY: after the first real run, check the object
# sizes reported in R2 and tune --daily-days/--weekly-days/--monthly-days (or the
# workflow_dispatch inputs that pass them through) to fit the available space.
#
# Retention is enforced by an R2 bucket LIFECYCLE RULE per prefix (server-side expiry),
# not by this script deleting objects itself: ensure_lifecycle_rules() asserts the
# current three rules on every run, which is both idempotent and self-healing if the
# bucket configuration ever drifts.

Run recipe (mirrors scripts/backfill_covers_r2.py's dry-run convention)::

    uv run --env-file .env python scripts/backup_database.py --dry-run
    uv run --env-file .env python scripts/backup_database.py

Required environment variables (see .github/workflows/supabase-backup.yml):

- ``SUPABASE_DB_URL``: direct (non-pooler) Postgres connection string.
- ``R2_ACCOUNT_ID``: Cloudflare account id (shared with covers/storage.py).
- ``R2_BACKUP_ACCESS_KEY_ID`` / ``R2_BACKUP_SECRET_ACCESS_KEY``: a scoped R2 API token
  with access to the backup bucket ONLY -- deliberately not the covers-upload token, so
  a compromised cover-art credential cannot read or overwrite backups and vice versa.
- ``R2_BACKUP_BUCKET``: destination bucket, separate from the public covers bucket.
- ``BACKUP_ENCRYPTION_KEY``: base64-encoded 32-byte AES-256 key.

# #CRITICAL: security: BACKUP_ENCRYPTION_KEY and the R2 secret access key are read
# straight from the environment and passed only as function arguments/bytes; neither
# this module nor any structlog call below ever logs their values or lengths. The one
# thing that IS logged about the key is that it failed to decode (load_encryption_key's
# error messages), never the raw or partially-decoded value.
# #VERIFY: test_backup_database.py has no assertion for this because it is a negative
# property (absence of a log call); grep for `_logger` call sites here before adding
# new ones and confirm none interpolate `encryption_key`, `raw`, or the R2 secret.

This is a real one-shot/scheduled operator script that dumps a live database and uploads
to a live bucket. It is NOT covered by integration tests against live infrastructure;
always run ``--dry-run`` first and read its summary before running live, and see the
restore drill in ``docs/operations/runbook.md`` section 6 before trusting these backups.
"""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
import structlog
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

_logger = structlog.get_logger(__name__)

_DUMP_TIMEOUT_SECONDS = 300.0
_UPLOAD_TIMEOUT_SECONDS = 120.0
_NONCE_LENGTH_BYTES = 12
_AES_256_KEY_LENGTH_BYTES = 32

# The three `supabase db dump` legs, in the order Supabase's own CI guide runs them:
# roles first (so a restore has the roles data depends on), schema, then data via COPY.
_DUMP_LEGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("roles.sql", ("--role-only",)),
    ("schema.sql", ()),
    ("data.sql", ("--data-only", "--use-copy")),
)

_DEFAULT_DAILY_RETENTION_DAYS = 7
_DEFAULT_WEEKLY_RETENTION_DAYS = 28
_DEFAULT_MONTHLY_RETENTION_DAYS = 180

_ISO_SUNDAY = 7


@dataclass(frozen=True)
class RetentionPolicy:
    """Day counts each tier's R2 lifecycle rule expires objects after."""

    daily_days: int = _DEFAULT_DAILY_RETENTION_DAYS
    weekly_days: int = _DEFAULT_WEEKLY_RETENTION_DAYS
    monthly_days: int = _DEFAULT_MONTHLY_RETENTION_DAYS


def tiers_for_date(today: datetime) -> tuple[str, ...]:
    """Return which prefixes today's backup should be written to.

    ``daily`` always runs; ``weekly`` promotes on ISO Sunday; ``monthly`` promotes on
    the 1st of the month. A date can be both (e.g. a Sunday that is also the 1st),
    which simply writes the same encrypted bytes to more than one prefix -- cheap,
    since the ciphertext is already in memory, and it keeps each tier self-contained
    (a weekly restore never depends on a daily object outliving its own expiry).

    Args:
        today: The date to classify, normally ``datetime.now(UTC)``.

    Returns:
        A tuple of one to three prefix names: always includes ``"daily"``.
    """
    tiers = ["daily"]
    if today.isoweekday() == _ISO_SUNDAY:
        tiers.append("weekly")
    if today.day == 1:
        tiers.append("monthly")
    return tuple(tiers)


def _r2_endpoint_url(account_id: str) -> str:
    """Build the R2 S3-compatible endpoint URL for an account.

    Duplicated from ``covers/storage.py`` rather than imported: this script must run
    standalone in CI with only the ``api`` extra installed (see the workflow's
    ``uv sync --extra api``), and importing from ``cyo_adventure.covers`` would pull in
    the cover-generation package's own dependency surface for one helper function.
    """
    return f"https://{account_id}.r2.cloudflarestorage.com"


def _build_client(
    account_id: str, access_key_id: str, secret_access_key: str
) -> S3Client:
    """Construct an R2 S3-compatible client scoped to the backup credentials.

    Mirrors ``covers/storage.py::_build_client``'s botocore configuration (region
    "auto", path-style addressing, relaxed checksum mode) since those are R2 platform
    requirements, not covers-specific choices. The connect/read timeout is longer than
    the covers uploader's (120s vs 30s): a full-database data dump can be far larger
    than a single cover image, so the same timeout budget would risk aborting a
    legitimate slow upload rather than only a genuinely stuck connection.
    """
    return boto3.client(
        "s3",
        endpoint_url=_r2_endpoint_url(account_id),
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
        config=BotoConfig(
            signature_version="s3v4",
            connect_timeout=_UPLOAD_TIMEOUT_SECONDS,
            read_timeout=_UPLOAD_TIMEOUT_SECONDS,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            s3={"addressing_style": "path"},
        ),
    )


def load_encryption_key(raw: str) -> bytes:
    """Decode and validate the base64 ``BACKUP_ENCRYPTION_KEY`` env value.

    Args:
        raw: The base64-encoded key string.

    Returns:
        The decoded 32-byte AES-256 key.

    Raises:
        ValueError: If the value is not valid base64 or is not exactly 32 bytes once
            decoded -- a truncated or wrong-length key must fail loudly here rather
            than produce ciphertext nothing can ever decrypt. Neither error message
            below includes ``raw`` or the decoded key: only the fact and the expected
            length are reported.
    """
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        msg = "BACKUP_ENCRYPTION_KEY is not valid base64"
        raise ValueError(msg) from exc
    if len(key) != _AES_256_KEY_LENGTH_BYTES:
        msg = (
            f"BACKUP_ENCRYPTION_KEY must decode to {_AES_256_KEY_LENGTH_BYTES} bytes "
            f"for AES-256 (got {len(key)}); generate one with "
            "`openssl rand -base64 32`"
        )
        raise ValueError(msg)
    return key


def encrypt_bytes(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt ``plaintext`` with AES-256-GCM (FIPS-approved per CLAUDE.md's crypto rules).

    # #CRITICAL: security: this is a children's-reading-data database dump. Per the
    # children's-privacy-compliance ADR, a backup must not sit in cleartext in object
    # storage even behind bucket ACLs -- a misconfigured bucket policy or a leaked R2
    # token must not itself be enough to read family/child data.
    # #VERIFY: test_backup_database.py::test_encrypt_decrypt_round_trip pins that the
    # output only decrypts with the correct key and fails closed (raises) on tampering
    # (GCM's authentication tag), not just that it round-trips on the happy path.

    Args:
        plaintext: The dump file bytes.
        key: The 32-byte AES-256 key from ``load_encryption_key``.

    Returns:
        ``nonce || ciphertext_with_tag``, a random 12-byte nonce prepended to the
        AESGCM output (nonce reuse under the same key breaks GCM's confidentiality
        guarantee, so a fresh random nonce is generated per call and stored alongside
        the ciphertext rather than derived from anything predictable).
    """
    nonce = os.urandom(_NONCE_LENGTH_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    """Reverse ``encrypt_bytes``; used by the restore path and by tests.

    Args:
        blob: ``nonce || ciphertext_with_tag`` as produced by ``encrypt_bytes``.
        key: The 32-byte AES-256 key.

    Returns:
        The original plaintext.

    Raises:
        cryptography.exceptions.InvalidTag: If the key is wrong or the blob was
            truncated/tampered with -- GCM authentication fails closed rather than
            returning corrupted plaintext.
    """
    nonce, ciphertext = blob[:_NONCE_LENGTH_BYTES], blob[_NONCE_LENGTH_BYTES:]
    return AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)


def run_dump_leg(db_url: str, out_path: Path, extra_args: tuple[str, ...]) -> None:
    """Run one ``supabase db dump`` leg, writing output to ``out_path``.

    # #CRITICAL: external resources: requires the Supabase CLI on PATH (the workflow
    # installs it via supabase/setup-cli, matching supabase-staging.yml/
    # supabase-production.yml's pinned version) and a reachable, DIRECT (non-pooler)
    # Postgres connection. The runbook documents Supavisor pooling as a known source of
    # dump/restore trouble; SUPABASE_DB_URL must be the direct connection string, not
    # the pgbouncer/Supavisor pooler URL used elsewhere in the app.
    # #VERIFY: this has not been run against a live Supabase project from this repo;
    # the first scheduled or manual workflow run is the real verification.

    Args:
        db_url: Direct Postgres connection string.
        out_path: File to write the dump SQL to.
        extra_args: Additional flags for this leg (e.g. ``("--role-only",)``).

    Raises:
        subprocess.CalledProcessError: If the Supabase CLI exits non-zero.
        subprocess.TimeoutExpired: If the dump does not finish within
            ``_DUMP_TIMEOUT_SECONDS``.
    """
    subprocess.run(
        [
            "supabase",
            "db",
            "dump",
            "--db-url",
            db_url,
            "-f",
            str(out_path),
            *extra_args,
        ],
        check=True,
        timeout=_DUMP_TIMEOUT_SECONDS,
        capture_output=True,
    )


def ensure_lifecycle_rules(
    client: S3Client, bucket: str, policy: RetentionPolicy
) -> None:
    """Assert the three tiered expiration rules on the backup bucket.

    Idempotent and self-healing: called on every run rather than once at setup time,
    so a bucket configuration that drifts (or a bucket that is recreated) is corrected
    on the next scheduled backup instead of silently growing unbounded.

    Args:
        client: R2 S3-compatible client.
        bucket: The backup bucket name.
        policy: Retention day counts per tier.
    """
    client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": f"expire-{tier}",
                    "Status": "Enabled",
                    "Filter": {"Prefix": f"{tier}/"},
                    "Expiration": {"Days": days},
                }
                for tier, days in (
                    ("daily", policy.daily_days),
                    ("weekly", policy.weekly_days),
                    ("monthly", policy.monthly_days),
                )
            ]
        },
    )


def upload_encrypted(
    client: S3Client,
    bucket: str,
    tier: str,
    date_str: str,
    filename: str,
    ciphertext: bytes,
) -> str:
    """Upload one encrypted dump leg to ``{tier}/{date_str}/{filename}.enc``.

    Args:
        client: R2 S3-compatible client.
        bucket: The backup bucket name.
        tier: One of ``"daily"``, ``"weekly"``, ``"monthly"``.
        date_str: ISO date (``YYYY-MM-DD``) this backup was taken.
        filename: The dump leg's base filename, e.g. ``"schema.sql"``.
        ciphertext: The output of ``encrypt_bytes``.

    Returns:
        The object key written.
    """
    key = f"{tier}/{date_str}/{filename}.enc"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=ciphertext,
        ContentType="application/octet-stream",
    )
    return key


def run_backup(
    *,
    db_url: str,
    r2_account_id: str,
    r2_access_key_id: str,
    r2_secret_access_key: str,
    r2_bucket: str,
    encryption_key: bytes,
    policy: RetentionPolicy,
    dry_run: bool,
    now: datetime | None = None,
) -> dict[str, object]:
    """Dump, encrypt, and upload today's backup to every applicable tier.

    Args:
        db_url: Direct Postgres connection string for ``supabase db dump``.
        r2_account_id: Cloudflare account id.
        r2_access_key_id: Scoped backup-bucket R2 access key id.
        r2_secret_access_key: Scoped backup-bucket R2 secret key.
        r2_bucket: Destination bucket name.
        encryption_key: 32-byte AES-256 key from ``load_encryption_key``.
        policy: Tiered retention day counts.
        dry_run: When True, report the plan (tiers, would-be keys) without running
            ``supabase db dump`` or making any network call.
        now: Injectable clock for tests; defaults to ``datetime.now(UTC)``.

    Returns:
        A summary dict with ``date``, ``tiers``, and ``uploaded`` (list of object keys;
        empty in dry-run mode).

    Raises:
        RuntimeError: If any dump leg is empty (see the #CRITICAL note below); nothing
            from that leg is uploaded to any tier.
        subprocess.CalledProcessError: If a ``supabase db dump`` leg exits non-zero.
        subprocess.TimeoutExpired: If a dump leg does not finish within
            ``_DUMP_TIMEOUT_SECONDS``.
        BotoCoreError: On an R2 client/network-level failure.
        ClientError: On an R2 API-level failure (e.g. bad credentials, missing bucket).
    """
    today = now or datetime.now(UTC)
    date_str = today.date().isoformat()
    tiers = tiers_for_date(today)

    if dry_run:
        _logger.info("backup_dry_run", date=date_str, tiers=tiers)
        return {
            "date": date_str,
            "tiers": list(tiers),
            "uploaded": [
                f"{tier}/{date_str}/{filename}.enc"
                for tier in tiers
                for filename, _ in _DUMP_LEGS
            ],
        }

    client = _build_client(r2_account_id, r2_access_key_id, r2_secret_access_key)
    ensure_lifecycle_rules(client, r2_bucket, policy)

    uploaded: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for filename, extra_args in _DUMP_LEGS:
            out_path = tmp_dir / filename
            run_dump_leg(db_url, out_path, extra_args)
            # #CRITICAL: data integrity: an empty dump file (a truncated or silently
            # failed `supabase db dump` that still exits 0) must not be uploaded as if
            # it were a real backup -- that would look like a successful nightly run
            # while actually holding nothing to restore from. This check runs BEFORE
            # any upload for this leg, to every tier, so a bad dump never reaches R2
            # under any prefix.
            # #VERIFY: test_backup_database.py::test_run_backup_rejects_empty_dump.
            plaintext = out_path.read_bytes()
            if not plaintext.strip():
                msg = f"supabase db dump produced an empty {filename}; aborting upload"
                raise RuntimeError(msg)
            ciphertext = encrypt_bytes(plaintext, encryption_key)
            for tier in tiers:
                key = upload_encrypted(
                    client, r2_bucket, tier, date_str, filename, ciphertext
                )
                uploaded.append(key)
                _logger.info("backup_uploaded", key=key, bytes=len(ciphertext))

    return {"date": date_str, "tiers": list(tiers), "uploaded": uploaded}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the backup script."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the backup plan without dumping, encrypting, or uploading anything.",
    )
    parser.add_argument(
        "--daily-days",
        type=int,
        default=_DEFAULT_DAILY_RETENTION_DAYS,
        help="R2 lifecycle expiry for the daily/ prefix (default: 7).",
    )
    parser.add_argument(
        "--weekly-days",
        type=int,
        default=_DEFAULT_WEEKLY_RETENTION_DAYS,
        help="R2 lifecycle expiry for the weekly/ prefix (default: 28).",
    )
    parser.add_argument(
        "--monthly-days",
        type=int,
        default=_DEFAULT_MONTHLY_RETENTION_DAYS,
        help="R2 lifecycle expiry for the monthly/ prefix (default: 180).",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point for the scheduled/manual backup workflow.

    Reads configuration from the environment (see the module docstring) so the
    GitHub Actions workflow only has to set env vars from secrets, not construct a
    command line. Exits non-zero on any failure so the workflow run is visibly red
    rather than a silently-empty backup.
    """
    args = _parse_args()

    if args.dry_run:
        result = run_backup(
            db_url="",
            r2_account_id="",
            r2_access_key_id="",
            r2_secret_access_key="",
            r2_bucket="",
            encryption_key=b"\x00" * _AES_256_KEY_LENGTH_BYTES,
            policy=RetentionPolicy(
                args.daily_days, args.weekly_days, args.monthly_days
            ),
            dry_run=True,
        )
        print(f"[DRY RUN] would back up: {result}")
        return

    try:
        db_url = os.environ["SUPABASE_DB_URL"]
        r2_account_id = os.environ["R2_ACCOUNT_ID"]
        r2_access_key_id = os.environ["R2_BACKUP_ACCESS_KEY_ID"]
        r2_secret_access_key = os.environ["R2_BACKUP_SECRET_ACCESS_KEY"]
        r2_bucket = os.environ["R2_BACKUP_BUCKET"]
        encryption_key = load_encryption_key(os.environ["BACKUP_ENCRYPTION_KEY"])
    except KeyError as exc:
        print(f"[ERROR] missing required environment variable: {exc}")
        sys.exit(1)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    try:
        result = run_backup(
            db_url=db_url,
            r2_account_id=r2_account_id,
            r2_access_key_id=r2_access_key_id,
            r2_secret_access_key=r2_secret_access_key,
            r2_bucket=r2_bucket,
            encryption_key=encryption_key,
            policy=RetentionPolicy(
                args.daily_days, args.weekly_days, args.monthly_days
            ),
            dry_run=False,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        BotoCoreError,
        ClientError,
        RuntimeError,
    ) as exc:
        print(f"[ERROR] backup failed: {exc}")
        sys.exit(1)

    print(f"[LIVE] backup summary: {result}")


if __name__ == "__main__":
    main()
