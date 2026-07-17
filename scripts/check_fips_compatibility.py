#!/usr/bin/env python3
"""Check code and dependencies for FIPS 140-2/140-3 compatibility issues.

This script detects common patterns and packages that may cause issues when
running on FIPS-enabled systems (like Ubuntu LTS with fips-updates).

FIPS mode restricts cryptographic algorithms to NIST-approved ones:
- Approved: AES, SHA-256/384/512, RSA (2048+), ECDSA, etc.
- Approved post-quantum (ADR-013): ML-KEM (FIPS 203), ML-DSA (FIPS 204),
  SLH-DSA (FIPS 205), and hybrid key exchange combining an approved classical
  scheme with ML-KEM (e.g. the X25519MLKEM768 TLS group).
- Prohibited: MD5, SHA-1 (for signatures), DES, RC4, Blowfish, etc.
- Flagged for migration: pre-standardization PQC names (Kyber, Dilithium,
  SPHINCS+); use the finalized FIPS 203/204/205 parameter sets instead.

Findings that are manual-verification nudges (severity "info") can be
acknowledged in pyproject.toml under [tool.fips_check.acknowledged] with a
mandatory reason, reference, and reviewed date; see ACK_MAX_AGE_DAYS below.

Usage:
    python scripts/check_fips_compatibility.py [--strict] [--fail-level LEVEL]
        [--fix-hints]

Exit codes:
    0: No findings at or above the failure level (acknowledged info excluded)
    1: Findings at or above the failure level (errors always fail; warnings
       fail under --strict or --fail-level warning/info; unacknowledged info
       fails under --fail-level info)
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

# Known FIPS-incompatible packages
FIPS_INCOMPATIBLE_PACKAGES: dict[str, str] = {
    "pycrypto": "Deprecated and not FIPS-compliant. Use 'pycryptodome' with FIPS mode.",
    "pycryptodome": "Use 'pycryptodomex' for FIPS compliance or ensure FIPS mode is enabled.",
    "m2crypto": "May use non-FIPS OpenSSL. Verify OpenSSL FIPS module is active.",
    "pyopenssl": "Depends on OpenSSL configuration. Ensure FIPS provider is enabled.",
    "paramiko": "Uses cryptography; ensure FIPS-compliant crypto backend.",
    "bcrypt": "bcrypt algorithm is not FIPS-approved. Use PBKDF2 or scrypt instead.",
    "passlib": "Some hashers (bcrypt, argon2) are not FIPS-approved.",
    "itsdangerous": "May use non-FIPS algorithms for signing. Verify configuration.",
}

# Packages that need verification but may be OK
FIPS_VERIFY_PACKAGES: dict[str, str] = {
    "cryptography": (
        "Ensure version >= 3.4.6 and OpenSSL FIPS provider is enabled; "
        ">= 45 adds ML-DSA/SLH-DSA (FIPS 204/205) primitives (ADR-013)."
    ),
    "pyca/cryptography": (
        "Ensure version >= 3.4.6 and OpenSSL FIPS provider is enabled; "
        ">= 45 adds ML-DSA/SLH-DSA (FIPS 204/205) primitives (ADR-013)."
    ),
    "requests": "Uses urllib3; TLS settings should use FIPS-compliant ciphers.",
    "urllib3": "Ensure TLS 1.2+ with FIPS-approved cipher suites.",
    "httpx": "Verify TLS configuration uses FIPS-approved algorithms.",
    "aiohttp": "Verify TLS configuration uses FIPS-approved algorithms.",
    "boto3": "AWS SDK; ensure FIPS endpoints are used for gov/compliance.",
    "azure-identity": "Azure SDK; ensure FIPS-compliant configuration.",
    "google-cloud-core": "GCP SDK; verify crypto configuration.",
    "jwt": (
        "PyJWT; ensure asymmetric algorithms (not HS256 with weak keys). "
        "This project's allowlist is config-driven via OIDC_ALLOWED_ALGS "
        "(ADR-013), ready for ML-DSA JOSE algorithms once registered."
    ),
    "pyjwt": (
        "Ensure asymmetric algorithms (not HS256 with weak keys). "
        "This project's allowlist is config-driven via OIDC_ALLOWED_ALGS "
        "(ADR-013), ready for ML-DSA JOSE algorithms once registered."
    ),
    "python-jose": "Verify algorithm configuration for FIPS compliance.",
}

# Non-FIPS approved hash algorithms
NON_FIPS_HASHES = {"md5", "md4", "sha1", "sha", "ripemd160"}

# Non-FIPS approved ciphers/algorithms
NON_FIPS_CIPHERS = {
    "des",
    "3des",
    "tripledes",
    "rc2",
    "rc4",
    "rc5",
    "blowfish",
    "idea",
    "cast5",
    "seed",
}

# Cipher names that are also ordinary English identifiers. Matching them as
# bare attribute names produces false positives (a `seed_staging.seed()` call
# is database seeding, not the SEED block cipher of RFC 4269), so these names
# are only flagged when the call carries cryptographic context: the module
# imports a crypto library, or the call's attribute chain passes through a
# known crypto namespace. Unambiguous names (des, rc4, blowfish, ...) are
# flagged unconditionally as before.
AMBIGUOUS_CIPHER_NAMES = {"seed", "idea"}

# Lowercased module-path or attribute-chain segments that mark code as
# cryptographic for the ambiguous-name gate above.
CRYPTO_NAMESPACE_SEGMENTS = {
    "crypto",  # pycrypto / pycryptodome (Crypto.Cipher.*)
    "cryptodome",  # pycryptodomex (Cryptodome.Cipher.*)
    "cryptography",  # pyca/cryptography
    "hazmat",
    "ciphers",
    "cipher",
    "m2crypto",
}

# NIST-finalized post-quantum algorithms (FIPS 203/204/205) and the hybrid TLS
# key-exchange group built on them. These are FIPS-approved (ADR-013) and must
# never be flagged, including by any future substring or name-list matching.
FIPS_PQC_APPROVED = {
    "ml-kem",
    "ml_kem",
    "mlkem",
    "ml-dsa",
    "ml_dsa",
    "mldsa",
    "slh-dsa",
    "slh_dsa",
    "slhdsa",
    "x25519mlkem768",
}

# Pre-standardization names for the FIPS 203/204/205 algorithms. Round-3
# submissions are not the finalized parameter sets and carry no FIPS
# validation; flag them with a migration hint rather than an error.
PQC_PRE_STANDARD_NAMES: dict[str, str] = {
    "kyber": "Use ML-KEM (FIPS 203); round-3 Kyber is not the finalized parameter set.",
    "dilithium": (
        "Use ML-DSA (FIPS 204); round-3 Dilithium is not the finalized parameter set."
    ),
    "sphincs": (
        "Use SLH-DSA (FIPS 205); SPHINCS+ round 3 is not the finalized parameter set."
    ),
}


# Acknowledged-findings baseline (ADR-013). Info-level "may need FIPS
# verification" findings can be acknowledged in pyproject.toml under a
# [tool.fips_check.acknowledged.<package>] table whose mandatory keys are
# reason (why the disposition is acceptable), reference (a citation into
# docs/security/crypto-inventory.md), and reviewed (a YYYY-MM-DD date).
#
# Acknowledgments apply ONLY to info-severity findings; error findings can
# never be baselined away. An acknowledgment older than ACK_MAX_AGE_DAYS stops
# suppressing and emits a warning instead, which fails the build at
# --fail-level warning or stricter; the cadence mirrors the quarterly
# signature-gate review mandated by ADR-013 decision 5.
ACK_MAX_AGE_DAYS = 90
ACK_REQUIRED_FIELDS = ("reason", "reference", "reviewed")


@dataclass
class Acknowledgment:
    """A justified, dated disposition for one info-level package finding."""

    package: str
    reason: str
    reference: str
    reviewed: datetime.date


@dataclass
class FipsIssue:
    """Represents a FIPS compatibility issue."""

    file_path: Path
    line_number: int
    severity: str  # "error", "warning", "info"
    category: str  # "hash", "cipher", "package", "config"
    message: str
    fix_hint: str | None = None
    package: str | None = None  # set on package findings; keys acknowledgments
    acknowledged: bool = False  # excluded from failure computation when True


def _module_imports_crypto(tree: ast.AST) -> bool:
    """Report whether a module imports any known cryptography library.

    Scans every ``import``/``from ... import`` in the tree (not just
    top-of-file ones) so the result does not depend on statement order
    relative to the calls being checked.

    Args:
        tree: Parsed AST of the module under inspection.

    Returns:
        True when any imported module path contains a segment from
        CRYPTO_NAMESPACE_SEGMENTS.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module] if node.module else []
        else:
            continue
        for module in modules:
            segments = {part.lower() for part in module.split(".")}
            if segments & CRYPTO_NAMESPACE_SEGMENTS:
                return True
    return False


def _attribute_chain(node: ast.expr) -> list[str]:
    """Return the lowercased dotted-name chain of an expression.

    ``Crypto.Cipher.SEED.new`` yields ``["crypto", "cipher", "seed", "new"]``.
    Non-name path elements (calls, subscripts) terminate the walk, so only
    the trailing plain-attribute suffix is returned.

    Args:
        node: The expression to unwind (typically ``ast.Call.func``).

    Returns:
        Chain segments from base to attribute, lowercased.
    """
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr.lower())
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id.lower())
    return list(reversed(parts))


class FipsCodeVisitor(ast.NodeVisitor):
    """AST visitor to detect FIPS-incompatible code patterns."""

    def __init__(self, file_path: Path, has_crypto_import: bool = False) -> None:
        self.file_path = file_path
        self.has_crypto_import = has_crypto_import
        self.issues: list[FipsIssue] = []

    def _call_has_crypto_context(self, node: ast.Call) -> bool:
        """Decide whether a call is plausibly cryptographic.

        Used only to gate AMBIGUOUS_CIPHER_NAMES; unambiguous cipher names
        never consult this.

        Args:
            node: The call under inspection.

        Returns:
            True when the module imports a crypto library or the call's
            attribute chain passes through a crypto namespace segment.
        """
        if self.has_crypto_import:
            return True
        return bool(set(_attribute_chain(node.func)) & CRYPTO_NAMESPACE_SEGMENTS)

    def _check_hashlib_call(self, node: ast.Call) -> None:
        """Detect hashlib.md5(), hashlib.sha1(), and similar non-FIPS hash calls.

        Emits a FipsIssue when a hashlib call uses a non-FIPS-approved hash
        and does not pass `usedforsecurity=False`. md5 and md4 are reported
        as errors; other non-FIPS hashes are reported as warnings.
        """
        if not isinstance(node.func, ast.Attribute):
            return
        if not (
            isinstance(node.func.value, ast.Name) and node.func.value.id == "hashlib"
        ):
            return
        func_name = node.func.attr.lower()
        if func_name not in NON_FIPS_HASHES:
            return
        has_usedforsecurity_false = any(
            keyword.arg == "usedforsecurity"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is False
            for keyword in node.keywords
        )
        if has_usedforsecurity_false:
            return
        severity = "error" if func_name in {"md5", "md4"} else "warning"
        self.issues.append(
            FipsIssue(
                file_path=self.file_path,
                line_number=node.lineno,
                severity=severity,
                category="hash",
                message=f"hashlib.{func_name}() is not FIPS-approved",
                fix_hint=(
                    f"Add usedforsecurity=False if not used for security: "
                    f"hashlib.{func_name}(..., usedforsecurity=False)"
                ),
            )
        )

    def _check_pqc_pre_standard_name(self, node: ast.Call, name: str) -> bool:
        """Flag pre-standardization PQC names (Kyber, Dilithium, SPHINCS+).

        Emits a warning-severity FipsIssue pointing at the finalized FIPS
        203/204/205 name when ``name`` contains a pre-standard PQC algorithm
        name. Finalized names (ML-KEM, ML-DSA, SLH-DSA) are exempted first.

        The pre-standard match is a substring test (``legacy in name``), so an
        identifier that merely embeds ``kyber``/``dilithium``/``sphincs`` also
        warns. That is intentional: this is a warn-only migration nudge, and a
        false positive costs a benign warning, not a blocked build.

        Args:
            node: The AST call node; supplies the line number for any issue.
            name: The lowercased algorithm identifier under inspection (both
                call sites pass an already ``.lower()``-ed string).

        Returns:
            True when ``name`` was handled as a PQC name (approved or
            pre-standard), so the caller skips its own matching.
        """
        if name in FIPS_PQC_APPROVED:
            return True
        for legacy, hint in PQC_PRE_STANDARD_NAMES.items():
            if legacy in name:
                self.issues.append(
                    FipsIssue(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        severity="warning",
                        category="pqc",
                        message=f"Pre-standardization PQC algorithm name: {name}",
                        fix_hint=hint,
                    )
                )
                return True
        return False

    def _check_cipher_call(self, node: ast.Call) -> None:
        """Detect non-FIPS cipher constructor calls (DES, RC4, Blowfish, etc.).

        Emits an error-severity FipsIssue when the called function's name
        is an exact match against a member of NON_FIPS_CIPHERS.
        """
        if not isinstance(node.func, ast.Attribute):
            return
        func_name = node.func.attr.lower()
        if self._check_pqc_pre_standard_name(node, func_name):
            return
        if func_name not in NON_FIPS_CIPHERS:
            return
        if func_name in AMBIGUOUS_CIPHER_NAMES and not self._call_has_crypto_context(
            node
        ):
            return
        self.issues.append(
            FipsIssue(
                file_path=self.file_path,
                line_number=node.lineno,
                severity="error",
                category="cipher",
                message=f"Non-FIPS cipher detected: {func_name}",
                fix_hint="Use AES, ChaCha20-Poly1305, or other FIPS-approved algorithms",
            )
        )

    def _check_new_algorithm_call(self, node: ast.Call) -> None:
        """Detect .new("algoname") calls (pycryptodome pattern) using non-FIPS algos.

        Emits an error-severity FipsIssue when a .new() call passes a string
        constant matching a known non-FIPS hash or cipher algorithm.
        """
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "new"):
            return
        for arg in node.args:
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            algo = arg.value.lower()
            if self._check_pqc_pre_standard_name(node, algo):
                continue
            if algo not in NON_FIPS_HASHES and algo not in NON_FIPS_CIPHERS:
                continue
            if algo in AMBIGUOUS_CIPHER_NAMES and not self._call_has_crypto_context(
                node
            ):
                continue
            self.issues.append(
                FipsIssue(
                    file_path=self.file_path,
                    line_number=node.lineno,
                    severity="error",
                    category="cipher" if algo in NON_FIPS_CIPHERS else "hash",
                    message=f"Non-FIPS algorithm: {algo}",
                    fix_hint="Use FIPS-approved algorithms (AES, SHA-256, etc.)",
                )
            )

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function calls to detect FIPS-incompatible crypto usage."""
        self._check_hashlib_call(node)
        self._check_cipher_call(node)
        self._check_new_algorithm_call(node)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Check for imports of known problematic modules."""
        for alias in node.names:
            module = alias.name.lower()
            if "crypto" in module and "pycryptodome" not in module:
                if "des" in module or "blowfish" in module or "rc4" in module:
                    self.issues.append(
                        FipsIssue(
                            file_path=self.file_path,
                            line_number=node.lineno,
                            severity="warning",
                            category="cipher",
                            message=f"Import of potentially non-FIPS module: {alias.name}",
                            fix_hint="Verify this module uses FIPS-approved algorithms",
                        )
                    )
        self.generic_visit(node)


def _coerce_reviewed_date(value: object) -> datetime.date | None:
    """Normalize a TOML ``reviewed`` value to a date, or None if invalid.

    TOML bare dates parse to ``datetime.date`` (or ``datetime.datetime`` with
    a time component); quoted ISO strings are also accepted.

    Args:
        value: The raw value from the acknowledgment table.

    Returns:
        The reviewed date, or None when the value is not a usable date.
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return None
    return None


def load_acknowledgments(
    pyproject_path: Path,
) -> tuple[dict[str, Acknowledgment], list[FipsIssue]]:
    """Load [tool.fips_check.acknowledged] entries from pyproject.toml.

    Malformed entries (missing required fields, unparseable dates, non-table
    values) are never silently dropped: each produces a warning-severity
    issue, so under --strict or --fail-level warning a broken acknowledgment
    fails the build instead of quietly acknowledging nothing.

    Args:
        pyproject_path: Path to the pyproject.toml to read.

    Returns:
        A mapping of lowercased package name to Acknowledgment, plus any
        config-hygiene issues found while loading.
    """
    acks: dict[str, Acknowledgment] = {}
    issues: list[FipsIssue] = []
    if not pyproject_path.exists():
        return acks, issues
    try:
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        issues.append(
            FipsIssue(
                file_path=pyproject_path,
                line_number=0,
                severity="warning",
                category="config",
                message=f"Could not parse acknowledgment config: {exc}",
            )
        )
        return acks, issues

    table = data.get("tool", {}).get("fips_check", {}).get("acknowledged", {})
    if not isinstance(table, dict):
        issues.append(
            FipsIssue(
                file_path=pyproject_path,
                line_number=0,
                severity="warning",
                category="config",
                message="[tool.fips_check.acknowledged] must be a table of tables",
            )
        )
        return acks, issues

    for package, entry in table.items():
        problem: str | None = None
        reviewed: datetime.date | None = None
        if not isinstance(entry, dict):
            problem = "entry must be a table with reason, reference, reviewed"
        else:
            missing = [field for field in ACK_REQUIRED_FIELDS if field not in entry]
            if missing:
                problem = f"missing required field(s): {', '.join(missing)}"
            else:
                reviewed = _coerce_reviewed_date(entry["reviewed"])
                if reviewed is None:
                    problem = "reviewed must be a date (YYYY-MM-DD)"
        if problem is not None or reviewed is None:
            issues.append(
                FipsIssue(
                    file_path=pyproject_path,
                    line_number=0,
                    severity="warning",
                    category="config",
                    message=f"Invalid acknowledgment for '{package}': {problem}",
                    fix_hint=(
                        "Each [tool.fips_check.acknowledged.<pkg>] entry needs "
                        "reason, reference, and reviewed (a YYYY-MM-DD date)"
                    ),
                    package=package.lower(),
                )
            )
            continue
        acks[package.lower()] = Acknowledgment(
            package=package.lower(),
            reason=str(entry["reason"]),
            reference=str(entry["reference"]),
            reviewed=reviewed,
        )
    return acks, issues


def apply_acknowledgments(
    issues: list[FipsIssue],
    acks: dict[str, Acknowledgment],
    today: datetime.date,
) -> list[FipsIssue]:
    """Mark acknowledged info-level package findings; report ack hygiene.

    Mutates matching findings' ``acknowledged`` flag in place and returns the
    extra issues this pass generates:

    - stale acknowledgment (older than ACK_MAX_AGE_DAYS): the finding stays
      active and a warning is added, so strict/fail-level-warning runs fail
      until the disposition is re-reviewed;
    - future-dated acknowledgment: warning, finding stays active;
    - acknowledgment matching an error-severity finding: warning, never
      suppressed (errors cannot be baselined);
    - acknowledgment matching no finding at all: warning to remove dead
      config.

    Args:
        issues: Findings collected so far (read for package matches).
        acks: Loaded acknowledgments keyed by lowercased package name.
        today: Date used for staleness computation (injectable for tests).

    Returns:
        The hygiene issues produced while applying the baseline.
    """
    extra: list[FipsIssue] = []
    matched: set[str] = set()
    warned: set[str] = set()

    def _warn_once(ack: Acknowledgment, message: str, fix_hint: str | None) -> None:
        if ack.package in warned:
            return
        warned.add(ack.package)
        extra.append(
            FipsIssue(
                file_path=Path("pyproject.toml"),
                line_number=0,
                severity="warning",
                category="config",
                message=message,
                fix_hint=fix_hint,
                package=ack.package,
            )
        )

    for issue in issues:
        if issue.package is None:
            continue
        ack = acks.get(issue.package)
        if ack is None:
            continue
        matched.add(ack.package)
        if issue.severity != "info":
            _warn_once(
                ack,
                f"Acknowledgment for '{ack.package}' cannot apply: only "
                "info-level findings can be acknowledged, and this package "
                f"has a {issue.severity}-level finding",
                "Fix the underlying finding; errors cannot be baselined",
            )
            continue
        age_days = (today - ack.reviewed).days
        if age_days < 0:
            _warn_once(
                ack,
                f"Acknowledgment for '{ack.package}' has a future reviewed "
                f"date ({ack.reviewed.isoformat()})",
                "Set reviewed to the date the disposition was actually checked",
            )
            continue
        if age_days > ACK_MAX_AGE_DAYS:
            _warn_once(
                ack,
                f"Acknowledgment for '{ack.package}' is stale: reviewed "
                f"{ack.reviewed.isoformat()} ({age_days} days ago, max "
                f"{ACK_MAX_AGE_DAYS} per the ADR-013 quarterly review)",
                "Re-verify the disposition against "
                "docs/security/crypto-inventory.md and update the reviewed date",
            )
            continue
        issue.acknowledged = True

    for package, ack in acks.items():
        if package not in matched:
            _warn_once(
                ack,
                f"Acknowledgment for '{package}' matches no finding; remove "
                "the dead entry",
                "Delete the [tool.fips_check.acknowledged] entry for this package",
            )
    return extra


def compute_exit_code(
    error_count: int,
    warning_count: int,
    unacknowledged_info_count: int,
    fail_level: str,
    strict: bool,
) -> int:
    """Resolve the process exit code from finding counts and failure policy.

    Args:
        error_count: Error-severity findings (always fatal).
        warning_count: Warning-severity findings (including ack hygiene).
        unacknowledged_info_count: Info findings not covered by a fresh
            acknowledgment.
        fail_level: Lowest severity that fails ("error", "warning", "info").
        strict: Legacy flag; raises an "error" fail_level to "warning". The
            stricter of the two settings wins.

    Returns:
        1 when any finding at or above the effective failure level exists,
        else 0.
    """
    effective = fail_level
    if strict and effective == "error":
        effective = "warning"
    if error_count:
        return 1
    if effective in {"warning", "info"} and warning_count:
        return 1
    if effective == "info" and unacknowledged_info_count:
        return 1
    return 0


def check_python_file(file_path: Path) -> list[FipsIssue]:
    """Check a Python file for FIPS compatibility issues."""
    issues: list[FipsIssue] = []

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))

        visitor = FipsCodeVisitor(
            file_path, has_crypto_import=_module_imports_crypto(tree)
        )
        visitor.visit(tree)
        issues.extend(visitor.issues)

    except SyntaxError as e:
        issues.append(
            FipsIssue(
                file_path=file_path,
                line_number=e.lineno or 0,
                severity="warning",
                category="parse",
                message=f"Could not parse file: {e.msg}",
            )
        )
    except Exception as e:
        issues.append(
            FipsIssue(
                file_path=file_path,
                line_number=0,
                severity="warning",
                category="parse",
                message=f"Error reading file: {e}",
            )
        )

    return issues


def check_pyproject_toml(file_path: Path) -> list[FipsIssue]:
    """Check pyproject.toml for FIPS-incompatible dependencies."""
    issues: list[FipsIssue] = []

    if not file_path.exists():
        return issues

    try:
        content = file_path.read_text(encoding="utf-8")

        # Check for incompatible packages
        for package, message in FIPS_INCOMPATIBLE_PACKAGES.items():
            # Match package in dependencies (various formats)
            patterns = [
                rf'"{package}["\s\[<>=]',
                rf"'{package}['\s\[<>=]",
                rf"^{package}\s*[<>=\[]",
            ]
            for pattern in patterns:
                matches = list(
                    re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE)
                )
                for match in matches:
                    line_num = content[: match.start()].count("\n") + 1
                    issues.append(
                        FipsIssue(
                            file_path=file_path,
                            line_number=line_num,
                            severity="error",
                            category="package",
                            message=f"FIPS-incompatible package: {package}",
                            fix_hint=message,
                            package=package.lower(),
                        )
                    )

        # Check for packages that need verification
        for package, message in FIPS_VERIFY_PACKAGES.items():
            patterns = [
                rf'"{package}["\s\[<>=]',
                rf"'{package}['\s\[<>=]",
            ]
            for pattern in patterns:
                matches = list(
                    re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE)
                )
                for match in matches:
                    line_num = content[: match.start()].count("\n") + 1
                    issues.append(
                        FipsIssue(
                            file_path=file_path,
                            line_number=line_num,
                            severity="info",
                            category="package",
                            message=f"Package may need FIPS verification: {package}",
                            fix_hint=message,
                            package=package.lower(),
                        )
                    )

    except Exception as e:
        issues.append(
            FipsIssue(
                file_path=file_path,
                line_number=0,
                severity="warning",
                category="parse",
                message=f"Error reading pyproject.toml: {e}",
            )
        )

    return issues


def check_requirements_file(file_path: Path) -> list[FipsIssue]:
    """Check requirements.txt for FIPS-incompatible dependencies."""
    issues: list[FipsIssue] = []

    if not file_path.exists():
        return issues

    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()

        for line_num, line in enumerate(lines, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Extract package name (handle various formats)
            package = re.split(r"[<>=\[\s#]", line)[0].lower()

            if package in FIPS_INCOMPATIBLE_PACKAGES:
                issues.append(
                    FipsIssue(
                        file_path=file_path,
                        line_number=line_num,
                        severity="error",
                        category="package",
                        message=f"FIPS-incompatible package: {package}",
                        fix_hint=FIPS_INCOMPATIBLE_PACKAGES[package],
                        package=package,
                    )
                )
            elif package in FIPS_VERIFY_PACKAGES:
                issues.append(
                    FipsIssue(
                        file_path=file_path,
                        line_number=line_num,
                        severity="info",
                        category="package",
                        message=f"Package may need FIPS verification: {package}",
                        fix_hint=FIPS_VERIFY_PACKAGES[package],
                        package=package,
                    )
                )

    except Exception as e:
        issues.append(
            FipsIssue(
                file_path=file_path,
                line_number=0,
                severity="warning",
                category="parse",
                message=f"Error reading requirements file: {e}",
            )
        )

    return issues


def find_python_files(directories: list[Path]) -> Iterator[Path]:
    """Find all Python files in the given directories."""
    for directory in directories:
        if directory.exists():
            yield from directory.rglob("*.py")


def print_issue(issue: FipsIssue, show_hints: bool = False) -> None:
    """Print a FIPS issue with formatting."""
    severity_symbols = {"error": "✗", "warning": "⚠", "info": "i"}
    severity_colors = {"error": "\033[91m", "warning": "\033[93m", "info": "\033[94m"}
    reset = "\033[0m"

    symbol = severity_symbols.get(issue.severity, "?")
    color = severity_colors.get(issue.severity, "")

    location = (
        f"{issue.file_path}:{issue.line_number}"
        if issue.line_number
        else str(issue.file_path)
    )
    print(f"{color}{symbol}{reset} [{issue.severity.upper()}] {location}")
    print(f"  {issue.message}")

    if show_hints and issue.fix_hint:
        print(f"  💡 {issue.fix_hint}")
    print()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check for FIPS 140-2/140-3 compatibility issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Check src/ directory
  %(prog)s --strict           # Treat warnings as errors
  %(prog)s --fix-hints        # Show fix suggestions
  %(prog)s --include-tests    # Also check test files
        """,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (equivalent to --fail-level warning)",
    )
    parser.add_argument(
        "--fail-level",
        choices=("error", "warning", "info"),
        default="error",
        help=(
            "Lowest severity that fails the check (default: error). 'info' "
            "additionally requires every info finding to be resolved or "
            "acknowledged under [tool.fips_check.acknowledged] in "
            "pyproject.toml. When --strict is also given, the stricter of "
            "the two settings wins."
        ),
    )
    parser.add_argument(
        "--fix-hints",
        action="store_true",
        help="Show fix hints for each issue",
    )
    parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path("src"),
        help="Source directory to check (default: src)",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Also check test files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    all_issues: list[FipsIssue] = []

    # Check Python source files
    dirs_to_check = [args.src_dir]
    if args.include_tests:
        dirs_to_check.append(Path("tests"))

    for file_path in find_python_files(dirs_to_check):
        if "__pycache__" in str(file_path):
            continue
        all_issues.extend(check_python_file(file_path))

    # Check dependency files
    all_issues.extend(check_pyproject_toml(Path("pyproject.toml")))
    all_issues.extend(check_requirements_file(Path("requirements.txt")))
    all_issues.extend(check_requirements_file(Path("requirements-dev.txt")))

    # Apply the acknowledged-findings baseline (ADR-013)
    acks, ack_config_issues = load_acknowledgments(Path("pyproject.toml"))
    all_issues.extend(ack_config_issues)
    today = datetime.datetime.now(tz=datetime.UTC).date()
    all_issues.extend(apply_acknowledgments(all_issues, acks, today))

    # Filter and count by severity; acknowledged findings never fail
    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]
    infos = [i for i in all_issues if i.severity == "info" and not i.acknowledged]
    acknowledged = [i for i in all_issues if i.acknowledged]

    exit_code = compute_exit_code(
        len(errors), len(warnings), len(infos), args.fail_level, args.strict
    )

    if args.json:
        output = {
            "summary": {
                "errors": len(errors),
                "warnings": len(warnings),
                "info": len(infos),
                "acknowledged": len(acknowledged),
            },
            "issues": [
                {
                    "file": str(i.file_path),
                    "line": i.line_number,
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "fix_hint": i.fix_hint,
                    "package": i.package,
                    "acknowledged": i.acknowledged,
                }
                for i in all_issues
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print("=" * 60)
        print("FIPS 140-2/140-3 Compatibility Check")
        print("=" * 60)
        print()

        if errors or warnings or infos:
            # Print errors first, then warnings, then unacknowledged info
            for issue in errors + warnings + infos:
                print_issue(issue, show_hints=args.fix_hints)
        else:
            print("✓ No unacknowledged FIPS compatibility issues found")
            print()

        if acknowledged:
            print(
                f"Acknowledged findings ({len(acknowledged)}), per "
                "[tool.fips_check.acknowledged] in pyproject.toml:"
            )
            for issue in acknowledged:
                ack = acks[issue.package or ""]
                print(f"  ✓ {ack.package}: {ack.reason}")
                print(f"    ref: {ack.reference} (reviewed {ack.reviewed})")
            print()

        # Summary
        print("-" * 60)
        print(
            f"Summary: {len(errors)} error(s), {len(warnings)} warning(s), "
            f"{len(infos)} info, {len(acknowledged)} acknowledged"
        )
        print()

        if errors:
            print("FIPS Compliance: ❌ FAILED")
            print("  Address errors before deploying to FIPS-enabled systems.")
        elif exit_code:
            print("FIPS Compliance: ❌ FAILED")
            print(
                f"  Unresolved findings at or above --fail-level "
                f"{args.fail_level}; fix them or acknowledge info findings "
                "in [tool.fips_check.acknowledged]."
            )
        elif warnings:
            print("FIPS Compliance: ⚠️  NEEDS REVIEW")
            print("  Review warnings for potential FIPS issues.")
        else:
            print("FIPS Compliance: ✅ PASSED")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
