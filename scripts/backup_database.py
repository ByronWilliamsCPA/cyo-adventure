"""Dump the Supabase database and ship an encrypted, tiered backup to R2.

Closes the gap `docs/operations/runbook.md` section 6 has documented since Phase 5 as
"no backup script, restore script, or restore runbook anywhere in this repository"
(issue #558, `UW-D27`). Runs three `supabase db dump` legs (roles, schema, data) against
the SESSION-mode Supavisor pooler on port 5432 (NOT the direct host, which publishes
AAAA only and is unreachable from the CLI's IPv4-only dump container; NOT transaction mode
on 6543, which reassigns backends mid-session), encrypts each file, and uploads to a
dedicated R2 bucket under a tiered prefix.

# #CRITICAL: data integrity: the lifecycle rules below are NOT asserted by this script
# in the current deployment. The backup R2 token is object-scoped, so every bucket-level
# call is refused, and R2 admin permissions cannot be narrowed to one bucket. The three
# rules are set by hand on the bucket instead, and ensure_lifecycle_rules() degrades to a
# `backup_lifecycle_unmanaged` warning. Nothing automated can confirm they are still
# correct, because the token cannot read them either.
# #VERIFY: re-check the rules by eye in the Cloudflare dashboard whenever the bucket is
# touched; runbook section 6 holds the table they must match.

Tiered retention (GFS rotation), sized for limited R2 space rather than kept forever:

- ``daily/``   always written; expires after ``--daily-days``   (default 7)
- ``weekly/``  written on ISO Sunday; expires after ``--weekly-days``  (default 28)
- ``monthly/`` written on the 1st;    expires after ``--monthly-days`` (default 180)

# #ASSUME: external resources: these day counts are a reasonable GFS default, not a
# measurement of this project's actual dump size or R2 budget -- nobody has run this
# against the live database yet. #VERIFY: after the first real run, check the object
# sizes reported in R2 and tune --daily-days/--weekly-days/--monthly-days (or the
# workflow_dispatch inputs that pass them through) to fit the available space; values
# below the documented per-tier floors need --force-retention and destroy history.
#
# Retention is enforced by an R2 bucket LIFECYCLE RULE per prefix (server-side expiry),
# not by this script deleting objects itself: ensure_lifecycle_rules() asserts the
# current three rules on every run, which is both idempotent and self-healing if the
# bucket configuration ever drifts. Because that call REPLACES the target bucket's whole
# lifecycle configuration, it is guarded on both sides: verify_backup_bucket() proves
# the bucket is this script's bucket before anything is written, and the lifecycle write
# itself happens only after every upload has succeeded and
# assert_recent_backup_exists() has confirmed the bucket still holds recent history.

Run recipe (mirrors scripts/backfill_covers_r2.py's dry-run convention)::

    uv run --env-file .env python scripts/backup_database.py --dry-run
    uv run --env-file .env python scripts/backup_database.py

Required environment variables (see .github/workflows/supabase-backup.yml):

- ``SUPABASE_DB_URL``: Supavisor SESSION-mode pooler connection string on port 5432
  (``postgresql://postgres.<ref>:<pw>@aws-0-us-east-1.pooler.supabase.com:5432/postgres``),
  NOT the transaction-mode pooler on 6543. This said "direct (non-pooler)" until
  2026-08-24; that route cannot work here, because the direct host publishes AAAA only
  and both the Supabase CLI's dump container and GitHub runners are IPv4-only. See
  ``docs/operations/runbook.md`` section 6.
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
# run_dump_leg now strips the credential out of the URL before it ever becomes an argv
# element (see `_strip_credentials_from_db_url`, which covers BOTH the `://user:pw@`
# userinfo form and libpq's `?password=` query-parameter form) and exports it to the
# subprocess only via `PGPASSWORD` in `env=`, which the Supabase CLI's underlying libpq
# connection honors (verified manually against a live Supabase CLI 2.109.1 / local
# Postgres 17.6 stack: an otherwise-identical dump with the password moved from the URL
# to `PGPASSWORD` produced byte-identical output). `env=` values are not visible in
# `/proc/<pid>/cmdline` the way argv is, and that `env=` is an explicit allowlist rather
# than a copy of this process's environment, so the CLI never sees the encryption key,
# either R2 credential, or the raw SUPABASE_DB_URL.
# #VERIFY: test_backup_database.py::test_run_dump_leg_never_puts_password_in_argv,
# ::test_strip_credentials_moves_password_out_of_the_url,
# ::test_strip_credentials_moves_query_parameter_password_out_of_the_url and
# ::test_run_dump_leg_env_excludes_unrelated_secrets pin this; grep for `_logger` call
# sites here before adding new ones and confirm none interpolate `encryption_key`,
# `raw`, the R2 secret, or a raw (unsanitized) db_url, and route every `print` of an
# exception through `_redact_secrets`.

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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import boto3
import structlog
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

# Annotated because `structlog.get_logger` returns Any, which makes every call site
# below a reportAny warning under basedpyright strict.
_logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

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

# Floors below which a retention value stops being a policy and becomes a deletion
# order. An R2 lifecycle rule applies to the WHOLE prefix, not just to objects this run
# wrote, so `--monthly-days 1` (a plausible typo for 180) tells R2 to expire every
# object under `monthly/` older than a day, destroying roughly six months of history
# that correct earlier runs produced. The rule also PERSISTS on the bucket after the run
# that set it, so the deletion continues after the operator's session ends.
_MIN_DAILY_RETENTION_DAYS = 3
_MIN_WEEKLY_RETENTION_DAYS = 14
_MIN_MONTHLY_RETENTION_DAYS = 90

# Sentinel object proving a bucket is THIS script's backup bucket. Checked before any
# write, because every destructive operation here (the lifecycle replace especially) is
# scoped by bucket name alone, and a bucket name is one environment variable away from
# being the public covers bucket.
_BUCKET_SENTINEL_KEY = ".cyo-backup-bucket"
_BUCKET_SENTINEL_BODY = (
    b"Marker for scripts/backup_database.py. Its presence authorizes that script to\n"
    b"write encrypted database dumps here and to REPLACE this bucket's lifecycle\n"
    b"configuration with expire-daily/expire-weekly/expire-monthly rules.\n"
    b"Delete this object only if this bucket is no longer the backup bucket.\n"
)

# The lifecycle rule IDs this script owns. Anything else already on the bucket belongs
# to someone (or something) else and is reported before it gets overwritten.
_OWNED_LIFECYCLE_RULE_IDS = frozenset(
    {"expire-daily", "expire-weekly", "expire-monthly"}
)

# S3/R2 error codes that mean "the thing you asked about is not there", as opposed to
# "you may not ask". A missing sentinel is a refusal-to-proceed; a 403 is a credential
# problem and must propagate rather than be mistaken for an uninitialized bucket.
_NOT_FOUND_ERROR_CODES = frozenset({"404", "NoSuchKey", "NoSuchBucket", "NotFound"})
_NO_LIFECYCLE_ERROR_CODES = frozenset(
    {"NoSuchLifecycleConfiguration", "NoSuchConfiguration"}
)

# R2 scopes API tokens by permission CLASS, and lifecycle is a BUCKET-level operation.
# The backup token is deliberately object-scoped (put/get/head/list objects on one
# bucket) because R2's admin permissions cannot be restricted to a single bucket, so an
# admin token able to manage lifecycle here could also delete the public covers bucket.
# The three expiry rules are therefore configured BY HAND on the bucket (runbook s6) and
# this script reports rather than asserts them. A refusal is a known posture, not a
# failed backup; anything else from the lifecycle API still fails the run.
_LIFECYCLE_DENIED_ERROR_CODES = frozenset(
    {"AccessDenied", "AccessDeniedException", "Forbidden", "403"}
)

# Environment variables the Supabase CLI subprocess is allowed to inherit. Everything
# else is dropped, including BACKUP_ENCRYPTION_KEY, both R2 keys, and the raw
# password-bearing SUPABASE_DB_URL: none of them is anything the CLI needs, and a
# subprocess that cannot read a secret cannot leak it through a crash dump, a --debug
# trace, or a grandchild process.
#
# #ASSUME: external resources: this allowlist is what a `supabase db dump` against a
# remote --db-url needs (PATH to find the binary and its bundled pg_dump, HOME/XDG for
# the CLI's config dir, TMPDIR for its scratch files, SSL_CERT_* for TLS trust, and the
# SUPABASE_* pair the CLI documents for non-interactive use). It is a deliberate
# allowlist, not a measurement of every variable the CLI might ever read.
# #VERIFY: if a live run fails with a CLI error that names a missing setting rather
# than a database problem, add that variable here rather than reverting to
# os.environ.copy(); reverting re-exposes all six secrets.
_SUBPROCESS_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "TMPDIR",
    "TMP",
    "TEMP",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "SUPABASE_ACCESS_TOKEN",
    "SUPABASE_WORKDIR",
)

_ISO_SUNDAY = 7

# The prefix whose history proves the schedule is still running. `daily/` is the right
# one to measure: it is written on EVERY run, so its newest date is the last time this
# job did anything at all, whereas `weekly/` and `monthly/` are legitimately days or
# weeks stale by design.
_HISTORY_PREFIX = "daily/"
_BACKUP_DATE_FORMAT = "%Y-%m-%d"

# How stale the newest PRE-EXISTING daily backup may be before a run fails.
#
# Three days, chosen against two boundaries. Upper: it must be comfortably below the
# 7-day default (and the 3-day hard floor) for daily retention, so that when the alarm
# fires there is still history left to restore from rather than an already-empty
# prefix. Lower: it must tolerate ordinary noise, and one missed night is ordinary (a
# GitHub Actions incident, a Supabase maintenance window, a transient R2 error). Three
# days means two consecutive misses are tolerated and the third is a pattern.
_MAX_BACKUP_GAP_DAYS = 3

# A dump leg below this many bytes is rejected outright, no marker check needed: real
# legs (even a roles.sql from a project with zero custom roles) run into the hundreds
# of bytes at minimum (a live capture from a default local Supabase stack measured 297
# bytes for roles.sql). This floor only catches a truly empty or near-truncated file;
# the structural marker check below is what actually distinguishes a real dump from
# well-formed boilerplate.
_MIN_LEG_BYTES = 40

# Leg-appropriate structural markers, verified empirically (2026-08-03) against a live
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


@dataclass(frozen=True, kw_only=True)
class RetentionPolicy:
    """Day counts each tier's R2 lifecycle rule expires objects after.

    # #CRITICAL: data integrity: these numbers are not a preference, they are a
    # standing instruction to R2 to DELETE objects. The rule is applied to the whole
    # prefix and survives the run that set it, so an unvalidated value is a data-loss
    # primitive: `--monthly-days 1` in place of 180 expires every object under
    # `monthly/`, including history no later run can regenerate. `__post_init__`
    # therefore rejects sub-floor and out-of-order values here, at construction, rather
    # than trusting each call site to check. ``force`` (``--force-retention``) is the
    # deliberate-shrink escape hatch and waives ONLY the floors; a positive-days check
    # and the daily <= weekly <= monthly ordering are structural and never waived,
    # since a GFS rotation whose coarser tier expires first has no meaning.
    # #VERIFY: test_backup_database.py::test_retention_policy_rejects_sub_floor_days,
    # ::test_retention_policy_rejects_inverted_ordering,
    # ::test_retention_policy_force_waives_floors_but_not_ordering.
    #
    # Fields are keyword-only by construction (``kw_only=True``): three same-typed ints
    # in a row are silently swappable positionally, and a swap of daily_days and
    # monthly_days would type-check, lint, and pass every behavioural test while
    # setting `monthly/` to expire in 7 days.

    Args:
        daily_days: Expiry for the ``daily/`` prefix.
        weekly_days: Expiry for the ``weekly/`` prefix.
        monthly_days: Expiry for the ``monthly/`` prefix.
        force: Waive the per-tier floors for a deliberate shrink.
    """

    daily_days: int = _DEFAULT_DAILY_RETENTION_DAYS
    weekly_days: int = _DEFAULT_WEEKLY_RETENTION_DAYS
    monthly_days: int = _DEFAULT_MONTHLY_RETENTION_DAYS
    force: bool = False

    def __post_init__(self) -> None:
        """Reject any value that would turn a retention rule into a deletion order.

        Raises:
            ValueError: If any tier is below one day, below its documented floor
                without ``force``, or if the tiers are not in non-decreasing order.
        """
        problems: list[str] = []
        for flag, value, floor in (
            ("--daily-days", self.daily_days, _MIN_DAILY_RETENTION_DAYS),
            ("--weekly-days", self.weekly_days, _MIN_WEEKLY_RETENTION_DAYS),
            ("--monthly-days", self.monthly_days, _MIN_MONTHLY_RETENTION_DAYS),
        ):
            if value < 1:
                problems.append(
                    f"{flag}={value} is not a positive number of days; R2 expiration "
                    "requires at least 1"
                )
            elif value < floor and not self.force:
                problems.append(
                    f"{flag}={value} is below the {floor}-day floor for that tier; "
                    "pass --force-retention if the shrink is deliberate and you "
                    "accept that R2 will expire existing objects under that prefix"
                )
        if not self.daily_days <= self.weekly_days <= self.monthly_days:
            problems.append(
                f"tiers must be non-decreasing, got daily={self.daily_days} "
                f"weekly={self.weekly_days} monthly={self.monthly_days}; a coarser "
                "tier that expires sooner than a finer one cannot retain more history"
            )
        if problems:
            msg = "invalid retention policy: " + "; ".join(problems)
            raise ValueError(msg)


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


def _require_env(name: str) -> str:
    """Read a required configuration value from the environment, whitespace-trimmed.

    # #CRITICAL: data integrity: every value this reads is pasted into a GitHub
    # secret by hand, and a leading space or trailing newline survives that paste.
    # GitHub masks the *trimmed* secret value in logs, so the stray character is
    # invisible in the run output: a leading space in ``R2_ACCOUNT_ID`` surfaced only
    # as ``Invalid endpoint: https:// ***.r2.cloudflarestorage.com`` on 2026-08-27,
    # after the workflow had been unable to complete a single run for weeks. None of
    # these values can legitimately carry leading or trailing whitespace.
    # #VERIFY: strip before use, and treat an empty result as absent. Covered by
    # tests/unit/test_backup_database.py::test_main_strips_whitespace_around_every_configuration_value
    # and ::test_main_rejects_a_variable_that_is_present_but_blank.

    The empty-string case is not hypothetical either. ``env: X: ${{ secrets.Y }}``
    renders an *undefined* secret as the empty string rather than omitting the
    variable, so from inside the job a missing repository or environment secret is
    indistinguishable from a blank one, and ``os.environ[name]`` never raises. Both
    arms have to be rejected here or the failure lands somewhere downstream that
    cannot name the variable responsible.

    Args:
        name: The environment variable to read.

    Returns:
        The value with surrounding whitespace removed.

    Raises:
        ValueError: If the variable is unset, empty, or whitespace-only. The message
            names the variable but never echoes its value: five of the six callers
            pass a credential.
    """
    raw = os.environ.get(name)
    if raw is None:
        msg = f"{name} is not set"
        raise ValueError(msg)
    value = raw.strip()
    if not value:
        msg = (
            f"{name} is set but empty. An undefined GitHub secret renders as an "
            "empty string, so check that the secret exists in the scope the "
            "workflow's `environment:` selects."
        )
        raise ValueError(msg)
    return value


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


def _strip_credentials_from_db_url(db_url: str) -> tuple[str, dict[str, str]]:
    """Split a Postgres connection URL into a credential-free URL and libpq env vars.

    # #CRITICAL: security: this is what keeps the database password out of argv (and
    # therefore out of `/proc/<pid>/cmdline`, readable by any co-resident process for
    # the subprocess's lifetime) and out of any error text that renders that argv.
    # Manually verified against a live Supabase CLI 2.109.1 / local Postgres 17.6
    # stack: dumping with the password left in `--db-url` and dumping with the password
    # stripped from the URL and exported as `PGPASSWORD` instead produced
    # byte-identical roles.sql output, confirming the CLI's underlying libpq connection
    # honors `PGPASSWORD` from the environment when the URL's userinfo omits a
    # password. No Supabase-CLI-specific env var was needed or invented.
    #
    # TWO credential locations are handled, not one. libpq accepts the password in the
    # userinfo (`://user:pw@host`) AND as a URI query parameter: a `password` key in the
    # query string, alongside ordinary connection parameters such as `sslmode`. That
    # second form is spelled out in words rather than shown as a literal
    # `key=value` pair, because a secret scanner's generic-password detector matches the
    # assignment SHAPE and cannot tell an illustrative token in a comment apart from a
    # real credential; written literally here it raised a false-positive incident
    # against this file. `urlsplit().password` is None for the second
    # form, so a query-parameter password used to survive this function untouched,
    # reach argv, and get echoed verbatim by the failure path in main(). The same
    # applies to `passfile`, which is moved to PGPASSFILE rather than dropped, since
    # dropping it would break authentication for anyone using that form.
    #
    # #CRITICAL: security: the userinfo password is PERCENT-DECODED before export.
    # `urlsplit().password` is the raw encoded substring, so `p%40ss` is the four
    # characters libpq would decode to `p@ss`; exporting the encoded form as PGPASSWORD
    # sends the wrong password and fails every dump leg with an auth error that points
    # at the credential rather than at this transform. The username is deliberately
    # NOT decoded: it is re-embedded in the URL, where libpq does its own decoding.
    # #VERIFY: test_backup_database.py::test_strip_credentials_percent_decodes_the_password,
    # ::test_strip_credentials_moves_query_parameter_password_out_of_the_url,
    # ::test_strip_credentials_brackets_ipv6_hosts.

    Args:
        db_url: A (possibly credential-bearing) Postgres connection URL, e.g.
            ``postgresql://<user>:<password>@<host>:5432/<dbname>``.

    Returns:
        A tuple of ``(sanitized_url, env_overrides)``. ``env_overrides`` carries the
        libpq environment variables (``PGPASSWORD``, ``PGPASSFILE``) that replace what
        was removed, and is empty when the URL carried no credential;
        ``sanitized_url`` is always safe to pass as a CLI argument.
    """
    parsed = urlsplit(db_url)
    overrides: dict[str, str] = {}

    kept_query: list[tuple[str, str]] = []
    for name, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = name.lower()
        if lowered == "password":
            overrides["PGPASSWORD"] = value
        elif lowered == "passfile":
            overrides["PGPASSFILE"] = value
        else:
            kept_query.append((name, value))

    # Userinfo wins over the query parameter when a URL somehow carries both: it is the
    # form the runbook documents and the one libpq's own URI parser reads first.
    if parsed.password is not None:
        overrides["PGPASSWORD"] = unquote(parsed.password)

    if not overrides:
        # Nothing to strip: return the URL byte-identical rather than round-tripping it
        # through urlunsplit, which would rewrite forms like `postgresql://direct`.
        return db_url, overrides

    host = parsed.hostname or ""
    if ":" in host:
        # An IPv6 literal loses its brackets via `.hostname`; without them the rebuilt
        # URL is unparseable and the dump fails on a host that was always valid.
        host = f"[{host}]"
    netloc = host
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    if parsed.username:
        netloc = f"{parsed.username}@{netloc}"
    sanitized = urlunsplit(
        (parsed.scheme, netloc, parsed.path, urlencode(kept_query), parsed.fragment)
    )
    return sanitized, overrides


# The password class is `[^/\s]+`, NOT `[^/\s@]+`: a password may legitimately
# contain an unencoded `@`. Excluding `@` made the match stop at the FIRST inner
# `@`, so `://user:abc@123@host/db` had only `://user:abc@` replaced and leaked the
# `123` tail. Allowing `@` and relying on greediness makes the match run to the LAST
# `@` in the run, which is the real user-info/host boundary.
_URL_CREDENTIALS_RE = re.compile(r"://[^/\s:@]+:[^/\s]+@")

# libpq also accepts keyword/value conninfo strings, and some client error paths echo
# that form instead of a URL. The URL pattern above cannot see a bare `password=...`.
# The value class stops at `&` as well as whitespace: the same `password=` shape occurs
# in a URI query string, where the password and a following `sslmode` are two separate
# parameters, and a `\S+` class swallowed the `sslmode` diagnostic along with the secret.
# (Spelled out rather than shown as a literal pair, for the scanner reason given at
# _strip_credentials_from_db_url.)
_CONNINFO_PASSWORD_RE = re.compile(r"(?i)\bpassword\s*=\s*[^\s&]+")


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
    # supabase-production.yml's pinned version) and a reachable SESSION-mode Supavisor
    # connection on port 5432. Until 2026-08-24 this block required the DIRECT
    # (non-pooler) host and forbade the pooler outright. That instruction was wrong and
    # unrunnable: the direct host publishes AAAA only, while the CLI dumps from inside an
    # IPv4-only Docker bridge network and GitHub runners have no IPv6 egress, so name
    # resolution fails before authentication. The runbook's pooling warning is about
    # TRANSACTION mode on 6543, which reassigns backends mid-session; session mode holds
    # one backend for the life of the connection and is what the production
    # cyo-adventure-db-backup sidecar has dumped this same database through since 2026-07.
    # Do not "restore" the direct host: it cannot resolve from either dump environment.
    # #VERIFY: test_backup_database.py::test_run_dump_leg_passes_the_db_url_through_to_the_cli,
    # ::test_run_dump_leg_propagates_cli_failure. Both dump legs were additionally run
    # against live session mode on 2026-08-24, producing this project's first backup.

    Args:
        db_url: Supavisor session-mode connection string (port 5432).
        out_path: File to write the dump SQL to.
        extra_args: Additional flags for this leg (e.g. ``("--role-only",)``).

    Raises:
        subprocess.CalledProcessError: If the Supabase CLI exits non-zero.
        subprocess.TimeoutExpired: If the dump does not finish within
            ``_DUMP_TIMEOUT_SECONDS``.
    """
    sanitized_url, credential_env = _strip_credentials_from_db_url(db_url)
    # #CRITICAL: security: an allowlisted env, NOT os.environ.copy(). A copy handed the
    # CLI subprocess BACKUP_ENCRYPTION_KEY, both R2 keys, and the raw password-bearing
    # SUPABASE_DB_URL, which contradicts this module's least-exposure rationale: the
    # password is carefully kept out of argv and then re-exposed in full to the same
    # process through its environment.
    # #VERIFY: test_backup_database.py::test_run_dump_leg_env_excludes_unrelated_secrets.
    env = {
        name: value
        for name in _SUBPROCESS_ENV_ALLOWLIST
        if (value := os.environ.get(name)) is not None
    }
    env.update(credential_env)
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


def _client_error_code(exc: ClientError) -> str:
    """Extract the S3/R2 error code from a ``ClientError``, or ``""`` if absent.

    Read defensively rather than by indexing: botocore builds this payload from the
    wire response, so a malformed or truncated error body must degrade to "no code I
    recognize" (and therefore to re-raising) rather than to a KeyError that replaces
    the real failure.

    Args:
        exc: The exception boto3 raised.

    Returns:
        The ``Error.Code`` string, or an empty string when the response has no usable
        code.
    """
    response: Mapping[str, object] = exc.response
    error = response.get("Error")
    if not isinstance(error, Mapping):
        return ""
    code: object = error.get("Code")  # pyright: ignore[reportUnknownMemberType]
    return code if isinstance(code, str) else ""


def verify_backup_bucket(
    client: S3Client, bucket: str, *, init_bucket: bool = False
) -> None:
    """Refuse to touch a bucket that is not provably this script's backup bucket.

    # #CRITICAL: data integrity: every destructive operation in this script is scoped
    # by bucket NAME alone, and the lifecycle write below fully REPLACES whatever
    # configuration the named bucket already has. If R2_BACKUP_BUCKET is ever set or
    # rotated to another bucket (the public covers bucket is one typo away), the first
    # run would discard that bucket's lifecycle rules, apply expire-after-N-days to any
    # pre-existing daily/weekly/monthly prefixes there, and write encrypted dumps into
    # a public bucket. Prefix matching is tight; bucket SELECTION was the unguarded
    # step. A sentinel object turns "the name in the env var" into "a bucket somebody
    # deliberately initialized for backups".
    # #VERIFY: test_backup_database.py::test_verify_backup_bucket_refuses_a_bucket_without_the_sentinel,
    # ::test_verify_backup_bucket_creates_the_sentinel_under_init_bucket,
    # ::test_run_backup_aborts_before_dumping_when_the_sentinel_is_missing.

    Args:
        client: R2 S3-compatible client.
        bucket: The backup bucket name.
        init_bucket: When True, create the sentinel instead of refusing. This is the
            explicit one-time ``--init-bucket`` opt-in, never the default.

    Raises:
        RuntimeError: If the sentinel is absent and ``init_bucket`` is False.
        ClientError: On any other R2 API failure, including a 403, which means a
            credential problem and must not be mistaken for an uninitialized bucket.
    """
    try:
        client.head_object(Bucket=bucket, Key=_BUCKET_SENTINEL_KEY)
    except ClientError as exc:
        if _client_error_code(exc) not in _NOT_FOUND_ERROR_CODES:
            raise
        if not init_bucket:
            msg = (
                f"bucket {bucket!r} has no {_BUCKET_SENTINEL_KEY} marker object, so "
                "this script cannot confirm it is the backup bucket; refusing to "
                "write dumps or replace its lifecycle configuration. Re-run once "
                "with --init-bucket if this really is the (empty, non-public) backup "
                "bucket, or fix R2_BACKUP_BUCKET."
            )
            raise RuntimeError(msg) from exc
        client.put_object(
            Bucket=bucket,
            Key=_BUCKET_SENTINEL_KEY,
            Body=_BUCKET_SENTINEL_BODY,
            ContentType="text/plain",
        )
        _logger.info("backup_bucket_sentinel_created", bucket=bucket)
    else:
        _logger.info("backup_bucket_verified", bucket=bucket)


def _report_foreign_lifecycle_rules(client: S3Client, bucket: str) -> bool:
    """Log any lifecycle rule already on the bucket that this script does not own.

    ``put_bucket_lifecycle_configuration`` replaces the whole configuration, so a rule
    written by someone else disappears without a trace. This read-before-write turns
    that into a logged, greppable event rather than a silent loss.

    Args:
        client: R2 S3-compatible client.
        bucket: The backup bucket name.

    Returns:
        True when the caller may proceed to write lifecycle rules; False when the token
        is refused bucket-level access, in which case the caller must NOT attempt the
        write. A blind write would replace rules this run was unable to read, which is
        exactly the silent loss the read-before-write exists to prevent.
    """
    try:
        current = client.get_bucket_lifecycle_configuration(Bucket=bucket)
    except ClientError as exc:
        code = _client_error_code(exc)
        if code in _NO_LIFECYCLE_ERROR_CODES:
            return True
        if code in _LIFECYCLE_DENIED_ERROR_CODES:
            _logger.warning(
                "backup_lifecycle_unmanaged",
                bucket=bucket,
                operation="GetBucketLifecycleConfiguration",
                error_code=code,
                detail=(
                    "object-scoped R2 token cannot read bucket lifecycle config; "
                    "retention is enforced by hand-set rules on the bucket and is NOT "
                    "verified by this run (see docs/operations/runbook.md section 6)"
                ),
            )
            return False
        raise
    existing = [str(rule.get("ID", "")) for rule in current.get("Rules", [])]
    foreign = sorted(set(existing) - _OWNED_LIFECYCLE_RULE_IDS)
    if foreign:
        _logger.warning(
            "backup_lifecycle_replacing_foreign_rules",
            bucket=bucket,
            foreign_rule_ids=foreign,
            owned_rule_ids=sorted(_OWNED_LIFECYCLE_RULE_IDS),
        )
    return True


def ensure_lifecycle_rules(
    client: S3Client, bucket: str, policy: RetentionPolicy
) -> None:
    """Assert the three tiered expiration rules on the backup bucket.

    Idempotent and self-healing FOR THE BACKUP BUCKET: called on every run rather than
    once at setup time, so a bucket configuration that drifts (or a bucket that is
    recreated) is corrected on the next scheduled backup instead of silently growing
    unbounded. That claim depends entirely on the bucket being the right one, which is
    ``verify_backup_bucket``'s job and must have run first.

    # #CRITICAL: data integrity: called only AFTER the upload loop succeeds. When it
    # ran first, a run that passed a bad retention value and then failed its dump still
    # left the destructive lifecycle change on the bucket: the operator saw a red run,
    # went debugging the dump, and R2 deleted good backups underneath them. Ordering it
    # last means no failed run can mutate retention.
    # #VERIFY: test_backup_database.py::test_run_backup_does_not_touch_lifecycle_when_a_leg_fails,
    # ::test_run_backup_sets_lifecycle_only_after_every_upload_succeeds.

    Args:
        client: R2 S3-compatible client.
        bucket: The backup bucket name.
        policy: Retention day counts per tier, already validated by
            ``RetentionPolicy.__post_init__``.
    """
    if not _report_foreign_lifecycle_rules(client, bucket):
        return
    try:
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
    except ClientError as exc:
        code = _client_error_code(exc)
        if code not in _LIFECYCLE_DENIED_ERROR_CODES:
            raise
        _logger.warning(
            "backup_lifecycle_unmanaged",
            bucket=bucket,
            operation="PutBucketLifecycleConfiguration",
            error_code=code,
            detail=(
                "object-scoped R2 token cannot write bucket lifecycle config; "
                "retention is enforced by hand-set rules on the bucket and is NOT "
                "asserted by this run (see docs/operations/runbook.md section 6)"
            ),
        )


def upload_encrypted(
    client: S3Client,
    bucket: str,
    tier: str,
    date_str: str,
    filename: str,
    ciphertext: bytes,
) -> tuple[str, str | None]:
    """Upload one encrypted dump leg to ``{tier}/{date_str}/{filename}.enc``.

    Args:
        client: R2 S3-compatible client.
        bucket: The backup bucket name.
        tier: One of ``"daily"``, ``"weekly"``, ``"monthly"``.
        date_str: ISO date (``YYYY-MM-DD``) this backup was taken.
        filename: The dump leg's base filename, e.g. ``"schema.sql"``.
        ciphertext: The output of ``encrypt_bytes``.

    Returns:
        ``(key, etag)``: the object key written and the ETag R2 reported for it, or
        ``None`` when the response carried no ETag. The ETag is what lets a rollback
        prove an object is still the one THIS run wrote before deleting it.
    """
    key = f"{tier}/{date_str}/{filename}.enc"
    response = client.put_object(
        Bucket=bucket,
        Key=key,
        Body=ciphertext,
        ContentType="application/octet-stream",
    )
    return key, response.get("ETag")


def _rollback_uploads(
    client: S3Client, bucket: str, written: list[tuple[str, str | None]]
) -> None:
    """Best-effort delete of the objects this run already wrote, newest first.

    Called only from the upload loop's failure path, to keep R2 from holding a
    partial set for a date.

    # #CRITICAL: data integrity: every delete is attempted even when an earlier one
    # fails, and no failure here is allowed to propagate: the caller re-raises the
    # ORIGINAL upload error, which is the one that explains the run. A rollback error
    # replacing it would hide the cause and send an operator chasing the cleanup
    # instead of the outage. Failures are logged individually so a surviving object is
    # still nameable from the run's logs.
    #
    # #CRITICAL: concurrency: each delete is guarded by the ETag this run received for
    # that key. Object keys are date-derived, not run-derived, so two overlapping runs
    # (a delayed schedule plus a manual dispatch) compute IDENTICAL keys. Without the
    # guard, run A's rollback deletes run B's freshly uploaded objects, and run B has
    # already exited 0 reporting a complete backup: an incomplete set for a date a
    # successful run called complete, with nothing red anywhere. The workflow's
    # `concurrency:` group is the first line of defense; this is the one that does not
    # depend on GitHub scheduling.
    # #VERIFY: test_backup_database.py::test_rollback_uploads_continues_after_a_failed_delete,
    # ::test_rollback_uploads_skips_an_object_another_run_replaced.

    Args:
        client: R2 S3-compatible client.
        bucket: The backup bucket name.
        written: ``(key, etag)`` pairs written earlier in this run, in write order.
    """
    for key, etag in reversed(written):
        try:
            if etag is not None:
                current = client.head_object(Bucket=bucket, Key=key)
                if current.get("ETag") != etag:
                    _logger.error(
                        "backup_rollback_skipped_replaced_object",
                        key=key,
                        reason="etag_mismatch",
                    )
                    continue
            client.delete_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            _logger.error(
                "backup_rollback_delete_failed",
                key=key,
                error_type=type(exc).__name__,
            )
        else:
            _logger.info("backup_rollback_deleted", key=key)


def assert_recent_backup_exists(
    client: S3Client,
    bucket: str,
    *,
    today: datetime,
    exclude_date: str,
    allow_empty: bool,
) -> None:
    """Fail the run unless a recent PRE-EXISTING daily backup is still in the bucket.

    Retention expires objects on an age-based schedule unconditionally, but until this
    check nothing ever asserted that a recent good backup exists. The workflow's
    alert-on-failure step fires on ``failure()``, meaning on a run that HAPPENS and
    fails; it cannot fire for a run that never happens at all. GitHub disables
    scheduled workflows after 60 days of repository inactivity, and a disabled
    ``production`` environment gate or a deleted secret stops dispatch just as
    silently. In that scenario the schedule stops on day 0, every ``daily/`` object
    expires by day 7, ``weekly/`` by day 28 and ``monthly/`` by day 180, and the bucket
    empties with zero red runs and zero issues filed. This check is what converts the
    next run that DOES happen into a loud failure.

    It doubles as the only exercise of the R2 READ path anywhere in this script: every
    other call is a write (put_object, put_bucket_lifecycle_configuration), so a token
    scoped without list/read permission, or pointed at the wrong bucket, would
    otherwise go undetected until a restore.

    # #CRITICAL: data integrity: a list call that fails is a FAILURE, never a pass.
    # BotoCoreError/ClientError are deliberately not caught here: "I could not tell
    # whether backups exist" must never be reported as "backups are fine", which is
    # the exact silent-failure shape this whole check exists to close.
    # #CRITICAL: external resources: the empty-prefix case is a real first run only
    # when the operator says so (``--init-bucket``). Left to pass silently in the
    # general path it would rebuild the same blind spot, since a bucket emptied by
    # runaway retention also lists zero objects.
    # #VERIFY: test_backup_database.py::test_assert_recent_backup_exists_accepts_a_fresh_prior_backup,
    # ::test_assert_recent_backup_exists_rejects_a_stale_newest_backup,
    # ::test_assert_recent_backup_exists_rejects_an_empty_bucket_without_init,
    # ::test_assert_recent_backup_exists_allows_an_empty_bucket_under_init_bucket,
    # ::test_assert_recent_backup_exists_propagates_a_list_failure.

    Args:
        client: R2 S3-compatible client.
        bucket: The backup bucket name.
        today: This run's clock, used to measure the gap.
        exclude_date: This run's own ``YYYY-MM-DD``, skipped so the check measures the
            history that existed BEFORE this run rather than the objects it just wrote.
        allow_empty: When True (``--init-bucket``), a bucket with no prior backup is
            accepted as a genuine first run.

    Raises:
        RuntimeError: If no prior backup exists and ``allow_empty`` is False, or if the
            newest prior backup is more than ``_MAX_BACKUP_GAP_DAYS`` days old.
        BotoCoreError: If the list call fails at the client/network level.
        ClientError: If the list call fails at the R2 API level (bad credentials, no
            list permission, missing bucket).
    """
    dates = sorted(_list_backup_dates(client, bucket) - {exclude_date})
    if not dates:
        if allow_empty:
            _logger.info("backup_history_empty_first_run", bucket=bucket)
            return
        msg = (
            f"bucket {bucket!r} holds no backup under {_HISTORY_PREFIX!r} other than "
            f"today's ({exclude_date}); either this is a genuine first run, in which "
            "case re-run once with --init-bucket, or every prior backup has been "
            "expired or deleted, which is a data-loss incident and not something this "
            "run may pass over silently"
        )
        raise RuntimeError(msg)

    newest = datetime.strptime(dates[-1], _BACKUP_DATE_FORMAT).replace(tzinfo=UTC)
    gap_days = (today.date() - newest.date()).days
    if gap_days > _MAX_BACKUP_GAP_DAYS:
        msg = (
            f"the newest backup preceding today under {_HISTORY_PREFIX!r} is "
            f"{dates[-1]} ({gap_days} days old), past the {_MAX_BACKUP_GAP_DAYS}-day "
            "gap threshold; the schedule stopped running at some point (a disabled "
            "workflow, a revoked secret, or a blocked environment gate) and retention "
            "has been expiring objects the whole time"
        )
        raise RuntimeError(msg)
    _logger.info(
        "backup_history_verified",
        bucket=bucket,
        newest_prior_backup=dates[-1],
        gap_days=gap_days,
    )


def _list_backup_dates(client: S3Client, bucket: str) -> set[str]:
    """Collect the ``YYYY-MM-DD`` date segments present under the daily prefix.

    Uses a delimited list so R2 returns one common prefix per backup date rather than
    one entry per object, which keeps the response small regardless of leg count.

    Args:
        client: R2 S3-compatible client.
        bucket: The backup bucket name.

    Returns:
        Every date segment that parses as an ISO date. Unparseable segments are
        ignored rather than treated as backups.
    """
    dates: set[str] = set()
    token: str | None = None
    while True:
        response = (
            client.list_objects_v2(
                Bucket=bucket,
                Prefix=_HISTORY_PREFIX,
                Delimiter="/",
                ContinuationToken=token,
            )
            if token
            else client.list_objects_v2(
                Bucket=bucket, Prefix=_HISTORY_PREFIX, Delimiter="/"
            )
        )
        for entry in response.get("CommonPrefixes", []):
            segment = (
                str(entry.get("Prefix", "")).removeprefix(_HISTORY_PREFIX).strip("/")
            )
            try:
                datetime.strptime(segment, _BACKUP_DATE_FORMAT).replace(tzinfo=UTC)
            except ValueError:
                continue
            dates.add(segment)
        token = response.get("NextContinuationToken")
        if not response.get("IsTruncated") or not token:
            return dates


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
    init_bucket: bool = False,
    now: datetime | None = None,
) -> dict[str, object]:
    """Dump, encrypt, and upload today's backup to every applicable tier.

    # #CRITICAL: data integrity: the order of R2 operations is deliberate and is the
    # fix for two separate data-loss findings. It is:
    #
    #   1. verify the bucket is the backup bucket (read; cheap, before a 300s dump)
    #   2. dump and validate all three legs locally (no R2 involvement at all)
    #   3. upload every leg to every tier, rolling back this run's own objects on
    #      failure
    #   4. assert a recent PRE-EXISTING backup still exists (read)
    #   5. assert the lifecycle rules (the only destructive, persistent write)
    #
    # The governing principle is that nothing is expired or mutated until a good
    # backup has been positively confirmed. Step 5 last means a run that fails its
    # dump can no longer leave a bad retention value on the bucket behind it; step 4
    # before step 5 means a bucket whose history has already been destroyed fails the
    # run instead of having its expiry schedule refreshed on the way out. Step 4 after
    # step 3 (rather than at the very start) is what makes the run fail loudly WITHOUT
    # losing today's backup: today's objects are safely written before the alarm goes
    # off, so the incident starts with one more good backup, not one fewer.

    Args:
        db_url: Supavisor session-mode connection string (port 5432) for
            ``supabase db dump``.
        r2_account_id: Cloudflare account id.
        r2_access_key_id: Scoped backup-bucket R2 access key id.
        r2_secret_access_key: Scoped backup-bucket R2 secret key.
        r2_bucket: Destination bucket name.
        encryption_key: 32-byte AES-256 key from ``load_encryption_key``.
        policy: Tiered retention day counts, already validated on construction.
        dry_run: When True, report the plan (tiers, would-be keys) without running
            ``supabase db dump`` or making any network call.
        init_bucket: One-time opt-in for a brand-new bucket: creates the marker object
            instead of refusing, and accepts an empty backup history as a first run.
        now: Injectable clock for tests; defaults to ``datetime.now(UTC)``.

    Returns:
        A summary dict with ``date``, ``tiers``, and ``uploaded`` (list of object keys;
        empty in dry-run mode).

    Raises:
        RuntimeError: If the bucket carries no backup marker, if any dump leg is too
            small or missing its structural marker (nothing is uploaded to any tier
            for any leg in that case, including legs that already passed validation),
            or if no recent prior backup survives in the bucket.
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
    verify_backup_bucket(client, r2_bucket, init_bucket=init_bucket)

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

        # All three legs dumped and validated: only now does anything write to R2.
        written: list[tuple[str, str | None]] = []
        try:
            for filename, _extra_args in _DUMP_LEGS:
                ciphertext = ciphertexts[filename]
                for tier in tiers:
                    key, etag = upload_encrypted(
                        client, r2_bucket, tier, date_str, filename, ciphertext
                    )
                    written.append((key, etag))
                    _logger.info("backup_uploaded", key=key, bytes=len(ciphertext))
        # Deliberately broader than the (BotoCoreError, ClientError) pair this loop is
        # documented to raise: the trigger for rollback is "this run wrote part of a
        # set and then stopped", which is true for any exception, not just the ones
        # boto names. The error is re-raised unchanged, so nothing is swallowed.
        except Exception:
            _rollback_uploads(client, r2_bucket, written)
            raise

    # Today's set is safely in R2. Confirm the HISTORY is intact before refreshing the
    # expiry schedule, so a bucket that retention has already emptied fails the run
    # rather than getting its deletion clock wound forward one more time.
    assert_recent_backup_exists(
        client,
        r2_bucket,
        today=today,
        exclude_date=date_str,
        allow_empty=init_bucket,
    )
    ensure_lifecycle_rules(client, r2_bucket, policy)

    uploaded = [key for key, _etag in written]
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
    parser.add_argument(
        "--force-retention",
        action="store_true",
        help=(
            "Waive the per-tier retention floors "
            f"(daily >= {_MIN_DAILY_RETENTION_DAYS}, "
            f"weekly >= {_MIN_WEEKLY_RETENTION_DAYS}, "
            f"monthly >= {_MIN_MONTHLY_RETENTION_DAYS}) for a DELIBERATE shrink. "
            "R2 will expire existing objects under the shrunk prefix, irreversibly. "
            "The daily <= weekly <= monthly ordering is never waived."
        ),
    )
    parser.add_argument(
        "--init-bucket",
        action="store_true",
        help=(
            "One-time initialization of a brand-new, empty backup bucket: write the "
            f"{_BUCKET_SENTINEL_KEY} marker object instead of refusing when it is "
            "absent, and accept an empty backup history as a genuine first run "
            "rather than as evidence that retention destroyed it."
        ),
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

    # Built before anything else, and before the dry-run branch, so an out-of-range
    # retention value is rejected by the cheapest possible run rather than by the one
    # that has already written a lifecycle rule.
    try:
        policy = RetentionPolicy(
            daily_days=args.daily_days,
            weekly_days=args.weekly_days,
            monthly_days=args.monthly_days,
            force=args.force_retention,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    if args.dry_run:
        result = run_backup(
            db_url="",
            r2_account_id="",
            r2_access_key_id="",
            r2_secret_access_key="",
            r2_bucket="",
            encryption_key=b"\x00" * _AES_256_KEY_LENGTH_BYTES,
            policy=policy,
            dry_run=True,
        )
        print(f"[DRY RUN] would back up: {result}")
        return

    try:
        db_url = _require_env("SUPABASE_DB_URL")
        r2_account_id = _require_env("R2_ACCOUNT_ID")
        r2_access_key_id = _require_env("R2_BACKUP_ACCESS_KEY_ID")
        r2_secret_access_key = _require_env("R2_BACKUP_SECRET_ACCESS_KEY")
        r2_bucket = _require_env("R2_BACKUP_BUCKET")
        encryption_key = load_encryption_key(_require_env("BACKUP_ENCRYPTION_KEY"))
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
            policy=policy,
            dry_run=False,
            init_bucket=args.init_bucket,
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
        #
        # #CRITICAL: security: str(exc) goes through _redact_secrets like every other
        # output path here. It was the ONE path that did not, and it is the one
        # guaranteed to carry the database URL: str() of a CalledProcessError or
        # TimeoutExpired renders the whole argv list, which includes the `--db-url`
        # element. This repository is public and its Actions logs are public with it.
        # _strip_credentials_from_db_url now keeps the password out of that argv in the
        # first place; this is the second, independent layer, because a shape-based
        # scrub and a structural strip fail in different ways.
        # #VERIFY: test_backup_database.py::test_main_prints_redacted_stderr_on_dump_failure,
        # ::test_main_redacts_a_query_parameter_password_in_the_exception_text.
        print(f"[ERROR] backup failed: {_redact_secrets(str(exc))}")
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
