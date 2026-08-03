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
#
# SUPABASE_DB_URL embeds a password too, and that one previously WAS exposed: it was
# passed as a `--db-url` argv element to the `supabase` subprocess, readable from
# `/proc/<pid>/cmdline` by any co-resident process for up to _DUMP_TIMEOUT_SECONDS.
# run_dump_leg now strips the password out of the URL before it ever becomes an argv
# element (see `_strip_password_from_db_url`) and exports it to the subprocess only via
# `PGPASSWORD` in `env=`, which the Supabase CLI's underlying libpq connection honors
# (verified manually against a live Supabase CLI 2.109.1 / local Postgres 17.6 stack:
# an otherwise-identical dump with the password moved from the URL to `PGPASSWORD`
# produced byte-identical output). `env=` values are not visible in `/proc/<pid>/cmdline`
# the way argv is.
# #VERIFY: test_backup_database.py::test_run_dump_leg_never_puts_password_in_argv and
# ::test_strip_password_from_db_url_moves_password_out_of_the_url pin this; grep for
# `_logger` call sites here before adding new ones and confirm none interpolate
# `encryption_key`, `raw`, the R2 secret, or a raw (unsanitized) db_url.

This is a real one-shot/scheduled operator script that dumps a live database and uploads
to a live bucket. It is NOT covered by integration tests against live infrastructure;
always run ``--dry-run`` first and read its summary before running live, and see the
restore drill in ``docs/operations/runbook.md`` section 6 before trusting these backups.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

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

# A dump leg below this many bytes is rejected outright, no marker check needed: real
# legs (even a roles.sql from a project with zero custom roles) run into the hundreds
# of bytes at minimum (a live capture from a default local Supabase stack measured 297
# bytes for roles.sql). This floor only catches a truly empty or near-truncated file;
# the structural marker check below is what actually distinguishes a real dump from
# well-formed boilerplate.
_MIN_LEG_BYTES = 40

# Leg-appropriate structural markers, verified empirically (2026-08-04) against a live
# local Supabase stack (CLI 2.109.1, Postgres 17.6) rather than assumed:
#
# - roles.sql (`supabase db dump --role-only`): pg_dumpall's own sed pipeline comments
#   out and then deletes CREATE ROLE/ALTER ROLE lines for every reserved Supabase role
#   name (anon, authenticated, service_role, ...), so a project with no custom roles
#   can legitimately have ZERO `CREATE ROLE` lines. What always survives, because it is
#   explicitly excluded from that deletion, are the platform-default per-role
#   statement_timeout settings emitted as `ALTER ROLE "..." SET "statement_timeout" ...`
#   -- confirmed present (3 lines: anon/authenticated/authenticator) on a fresh local
#   stack with no custom roles at all. Hence the marker accepts either verb.
# - schema.sql (`supabase db dump`, schema-only): pg_dump emits `CREATE TABLE "..."`,
#   which the CLI's own sed pipeline rewrites to `CREATE TABLE IF NOT EXISTS "..."`; a
#   plain substring/regex search for `CREATE TABLE` matches both forms.
# - data.sql (`supabase db dump --data-only --use-copy`): confirmed this flag combination
#   produces `COPY "schema"."table" (...) FROM stdin;` blocks, not `INSERT INTO`
#   statements (the `--use-copy` flag specifically means "do not add pg_dump's
#   --column-inserts", which is what forces INSERT-style output). If this leg's
#   `extra_args` in `_DUMP_LEGS` above ever changes to drop `--use-copy`, this marker
#   must change to `INSERT INTO` too.
_LEG_REQUIREMENTS: dict[str, tuple[str, re.Pattern[str]]] = {
    "roles.sql": (
        "CREATE ROLE or ALTER ROLE",
        re.compile(r"\b(?:CREATE|ALTER)\s+ROLE\b"),
    ),
    "schema.sql": ("CREATE TABLE", re.compile(r"\bCREATE\s+TABLE\b")),
    "data.sql": ("COPY ... FROM stdin", re.compile(r"\bCOPY\b[^\n]*\bFROM stdin\b")),
}

# Ceiling on how much subprocess stdout/stderr main() prints per stream on failure: long
# enough to carry a real Postgres/CLI error, short enough that a runaway or looping
# error message cannot flood the workflow log.
_ERROR_OUTPUT_TRUNCATE_CHARS = 4000


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


def _strip_password_from_db_url(db_url: str) -> tuple[str, str | None]:
    """Split a Postgres connection URL into a password-free URL and its password.

    # #CRITICAL: security: this is what keeps the database password out of argv (and
    # therefore out of `/proc/<pid>/cmdline`, readable by any co-resident process for
    # the subprocess's lifetime). Manually verified against a live Supabase CLI 2.109.1
    # / local Postgres 17.6 stack: dumping with the password left in `--db-url` and
    # dumping with the password stripped from the URL and exported as `PGPASSWORD`
    # instead produced byte-identical roles.sql output, confirming the CLI's underlying
    # libpq connection honors `PGPASSWORD` from the environment when the URL's userinfo
    # omits a password. No Supabase-CLI-specific env var was needed or invented.
    # #VERIFY: test_backup_database.py::test_strip_password_from_db_url_moves_password_out_of_the_url.

    Args:
        db_url: A (possibly password-bearing) Postgres connection URL, e.g.
            ``postgresql://<user>:<password>@<host>:5432/<dbname>``.

    Returns:
        A tuple of ``(sanitized_url, password)``. ``password`` is ``None`` when the
        input URL had no embedded password (nothing to strip, nothing to export);
        ``sanitized_url`` is always safe to pass as a CLI argument.
    """
    parsed = urlsplit(db_url)
    if parsed.password is None:
        return db_url, None
    netloc = parsed.username or ""
    if parsed.hostname:
        netloc += f"@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    sanitized = urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    )
    return sanitized, parsed.password


# The password class is `[^/\s]+`, NOT `[^/\s@]+`: a password may legitimately
# contain an unencoded `@`. Excluding `@` made the match stop at the FIRST inner
# `@`, so `://user:abc@123@host/db` had only `://user:abc@` replaced and leaked the
# `123` tail. Allowing `@` and relying on greediness makes the match run to the LAST
# `@` in the run, which is the real user-info/host boundary.
_URL_CREDENTIALS_RE = re.compile(r"://[^/\s:@]+:[^/\s]+@")

# libpq also accepts keyword/value conninfo strings, and some client error paths echo
# that form instead of a URL. The URL pattern above cannot see a bare `password=...`.
_CONNINFO_PASSWORD_RE = re.compile(r"(?i)\bpassword\s*=\s*\S+")


def _redact_secrets(text: str) -> str:
    """Scrub credential-shaped substrings before subprocess output reaches a log.

    # #CRITICAL: security: a failed `supabase db dump` connection (wrong host, refused
    # auth) can echo the connection string, including its embedded password, back in
    # its stderr. Two credential shapes are scrubbed: the `scheme://user:password@`
    # URL form, and libpq's keyword/value `password=...` form. Mirrors the
    # URL-credentials pattern in `src/cyo_adventure/utils/redaction.py` (PR #581)
    # rather than importing it: this script must run standalone in CI with only the
    # `api` extra installed and must not gain a dependency on the app package.
    #
    # This is shape-based scrubbing, so it is a strong mitigation and NOT a guarantee.
    # A password echoed with no surrounding structure at all, for example a bare token
    # on its own line, matches neither pattern and would survive. Treat these two
    # shapes as the covered cases, not as proof that nothing can get through.
    # #VERIFY: test_backup_database.py::test_redact_secrets_scrubs_url_password,
    # ::test_redact_secrets_scrubs_password_containing_at_sign,
    # ::test_redact_secrets_scrubs_conninfo_password.

    Args:
        text: Raw decoded subprocess output.

    Returns:
        ``text`` with URL-embedded and conninfo-style passwords replaced.
    """
    redacted = _URL_CREDENTIALS_RE.sub("://[redacted]@", text)
    return _CONNINFO_PASSWORD_RE.sub("password=[redacted]", redacted)


def _decode_process_output(data: bytes | None) -> str:
    """Decode, redact, and truncate captured subprocess stdout/stderr for printing.

    Args:
        data: Raw bytes from ``subprocess.CalledProcessError``/``TimeoutExpired``'s
            ``stdout``/``stderr`` attribute, or ``None``.

    Returns:
        An empty string if ``data`` is falsy; otherwise the decoded, redacted text,
        truncated to ``_ERROR_OUTPUT_TRUNCATE_CHARS`` characters.
    """
    if not data:
        return ""
    text = _redact_secrets(data.decode("utf-8", errors="replace"))
    if len(text) <= _ERROR_OUTPUT_TRUNCATE_CHARS:
        return text
    omitted = len(text) - _ERROR_OUTPUT_TRUNCATE_CHARS
    return f"{text[:_ERROR_OUTPUT_TRUNCATE_CHARS]}... [truncated, {omitted} more chars]"


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
    sanitized_url, password = _strip_password_from_db_url(db_url)
    env = os.environ.copy()
    if password is not None:
        env["PGPASSWORD"] = password
    subprocess.run(
        [
            "supabase",
            "db",
            "dump",
            "--db-url",
            sanitized_url,
            "-f",
            str(out_path),
            *extra_args,
        ],
        check=True,
        timeout=_DUMP_TIMEOUT_SECONDS,
        capture_output=True,
        env=env,
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


def _rollback_uploads(client: S3Client, bucket: str, keys: list[str]) -> None:
    """Best-effort delete of the keys this run already wrote, newest first.

    Called only from the upload loop's failure path, to keep R2 from holding a
    partial set for a date.

    # #CRITICAL: data integrity: every delete is attempted even when an earlier one
    # fails, and no failure here is allowed to propagate: the caller re-raises the
    # ORIGINAL upload error, which is the one that explains the run. A rollback error
    # replacing it would hide the cause and send an operator chasing the cleanup
    # instead of the outage. Failures are logged individually so a surviving object is
    # still nameable from the run's logs.
    # #VERIFY: test_backup_database.py::test_rollback_uploads_continues_after_a_failed_delete.

    Args:
        client: R2 S3-compatible client.
        bucket: The backup bucket name.
        keys: Object keys written earlier in this run, in write order.
    """
    for key in reversed(keys):
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            _logger.error(
                "backup_rollback_delete_failed",
                key=key,
                error_type=type(exc).__name__,
            )
        else:
            _logger.info("backup_rollback_deleted", key=key)


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
        RuntimeError: If any dump leg is too small or missing its structural marker
            (see the #CRITICAL note below); nothing is uploaded to any tier for any
            leg, including legs that already passed validation earlier in this run.
        subprocess.CalledProcessError: If a ``supabase db dump`` leg exits non-zero.
        subprocess.TimeoutExpired: If a dump leg does not finish within
            ``_DUMP_TIMEOUT_SECONDS``.
        BotoCoreError: On an R2 client/network-level failure. If it interrupts the
            upload loop, the keys already written this run are deleted best-effort
            first and the original error is re-raised unchanged.
        ClientError: On an R2 API-level failure (e.g. bad credentials, missing bucket);
            same best-effort rollback as above.
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

    # #CRITICAL: data integrity: dump and validate every leg into this run's temp
    # directory FIRST, uploading nothing until all three pass (chosen over a
    # completeness-marker-object approach, since the TemporaryDirectory already holds
    # every leg's bytes for the process lifetime, so buffering the encrypted
    # ciphertext too, at most tens of MB, costs nothing extra). If leg 2 or 3 fails
    # (auth revoked mid-run, CLI crash, disk full, a boilerplate-only dump), leg 1's
    # ciphertext is simply discarded when the TemporaryDirectory is cleaned up: R2
    # receives no object for this date until the whole set is known-good.
    #
    # That covers failures BEFORE the upload loop. A failure DURING it (a network
    # blip, an R2 timeout, a credential revoked mid-sequence) can still land some
    # keys, so the loop below rolls back what it already wrote. The rollback is
    # best-effort by nature: if the same outage that broke the upload also breaks the
    # delete, some objects survive. This is a strong bias against partial sets, NOT
    # an atomic multi-object write, which R2 does not offer.
    # #VERIFY: test_backup_database.py::test_run_backup_uploads_nothing_when_a_later_leg_fails,
    # ::test_run_backup_rolls_back_uploaded_keys_when_a_later_upload_fails.
    ciphertexts: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for filename, extra_args in _DUMP_LEGS:
            out_path = tmp_dir / filename
            run_dump_leg(db_url, out_path, extra_args)
            # #CRITICAL: data integrity: `supabase db dump`/pg_dump output ALWAYS
            # carries non-whitespace boilerplate (headers, `SET ...` lines, comments)
            # even when the dump captured ZERO real data for this leg -- a wrong
            # project ref, revoked grant, or wrong search_path still exits 0 and
            # produces well-formed, non-blank SQL. A bare blankness check cannot tell
            # that apart from a real backup, so each leg must additionally contain a
            # structural marker specific to what that leg is supposed to hold (see
            # `_LEG_REQUIREMENTS` above, verified against a live dump, not assumed).
            # This check runs BEFORE any upload for this leg, to every tier, so a bad
            # dump never reaches R2 under any prefix.
            # #VERIFY: test_backup_database.py::test_run_backup_rejects_boilerplate_only_roles_dump,
            # ::test_run_backup_rejects_boilerplate_only_schema_dump,
            # ::test_run_backup_rejects_boilerplate_only_data_dump,
            # ::test_run_backup_rejects_empty_dump.
            plaintext = out_path.read_bytes()
            if len(plaintext) < _MIN_LEG_BYTES:
                msg = (
                    f"supabase db dump produced an empty or near-empty {filename} "
                    f"({len(plaintext)} bytes, need at least {_MIN_LEG_BYTES}); "
                    "aborting upload"
                )
                raise RuntimeError(msg)
            marker_label, marker_pattern = _LEG_REQUIREMENTS[filename]
            if not marker_pattern.search(plaintext.decode("utf-8", errors="replace")):
                msg = (
                    f"supabase db dump produced {filename} with no {marker_label} "
                    "statement; the dump ran and produced only boilerplate output "
                    "(pg_dump/pg_dumpall headers and SET lines, no real content), "
                    "which means it likely captured the wrong project, database, or "
                    "search_path; aborting upload"
                )
                raise RuntimeError(msg)
            ciphertexts[filename] = encrypt_bytes(plaintext, encryption_key)

        # All three legs dumped and validated: only now does anything touch R2.
        uploaded: list[str] = []
        try:
            for filename, _extra_args in _DUMP_LEGS:
                ciphertext = ciphertexts[filename]
                for tier in tiers:
                    key = upload_encrypted(
                        client, r2_bucket, tier, date_str, filename, ciphertext
                    )
                    uploaded.append(key)
                    _logger.info("backup_uploaded", key=key, bytes=len(ciphertext))
        # Deliberately broader than the (BotoCoreError, ClientError) pair this loop is
        # documented to raise: the trigger for rollback is "this run wrote part of a
        # set and then stopped", which is true for any exception, not just the ones
        # boto names. The error is re-raised unchanged, so nothing is swallowed.
        except Exception:
            _rollback_uploads(client, r2_bucket, uploaded)
            raise

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
        # #CRITICAL: data integrity: str(exc) on a CalledProcessError/TimeoutExpired
        # does NOT include stdout/stderr (verified: it renders as just
        # "Command '[...]' returned non-zero exit status 1."), so without this, the one
        # piece of information most useful during a real incident, WHY the dump or
        # upload failed (auth, network, permissions), was captured by
        # capture_output=True and then silently discarded. stdout/stderr are only
        # present on the two subprocess exception types; BotoCoreError/ClientError/
        # RuntimeError have no such attributes, hence getattr with a None default.
        # #VERIFY: test_backup_database.py::test_main_prints_redacted_stderr_on_dump_failure.
        print(f"[ERROR] backup failed: {exc}")
        stdout = _decode_process_output(getattr(exc, "stdout", None))
        stderr = _decode_process_output(getattr(exc, "stderr", None))
        if stdout:
            print(f"[ERROR] stdout:\n{stdout}")
        if stderr:
            print(f"[ERROR] stderr:\n{stderr}")
        sys.exit(1)

    print(f"[LIVE] backup summary: {result}")


if __name__ == "__main__":
    main()
