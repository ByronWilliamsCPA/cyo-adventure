"""Unit tests for the FIPS checker's post-quantum awareness (ADR-013).

The checker's PQC logic is an approved-names allowlist checked before a
pre-standard-names denylist; its correctness rests on those sets never
overlapping with (or suppressing) the classical NON_FIPS findings. These
tests pin that invariant so it cannot regress silently, since scripts/ is
outside the coverage gate's source tree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from scripts.check_fips_compatibility import (
    AMBIGUOUS_CIPHER_NAMES,
    FIPS_PQC_APPROVED,
    NON_FIPS_CIPHERS,
    NON_FIPS_HASHES,
    PQC_PRE_STANDARD_NAMES,
    FipsIssue,
    check_python_file,
)


def _issues_for(tmp_path: Path, source: str) -> list[FipsIssue]:
    """Write ``source`` to a temp module and run the checker over it.

    Args:
        tmp_path: pytest-provided temp directory.
        source: Python source code to scan.

    Returns:
        list[FipsIssue]: The issues the checker reports for the file.
    """
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return check_python_file(target)


@pytest.mark.unit
def test_pqc_sets_never_overlap_classical_denylists() -> None:
    """The approved/pre-standard PQC sets are disjoint from NON_FIPS sets.

    The exemption helper runs before classical matching, so any overlap
    would let the PQC allowlist suppress a legitimate finding.
    """
    classical = NON_FIPS_CIPHERS | NON_FIPS_HASHES
    assert not FIPS_PQC_APPROVED & classical
    assert not set(PQC_PRE_STANDARD_NAMES) & classical


@pytest.mark.unit
@pytest.mark.parametrize("algo", ["ml-kem", "ml_dsa", "slh-dsa", "x25519mlkem768"])
def test_finalized_pqc_name_in_new_call_not_flagged(tmp_path: Path, algo: str) -> None:
    """A finalized FIPS 203/204/205 name passed to .new() reports nothing."""
    issues = _issues_for(tmp_path, f'def use(kem):\n    kem.new("{algo}")\n')
    assert issues == []


@pytest.mark.unit
def test_finalized_pqc_attribute_call_not_flagged(tmp_path: Path) -> None:
    """A finalized PQC name as a method call (e.g. kem.ml_kem()) is approved."""
    issues = _issues_for(tmp_path, "def use(kem):\n    kem.ml_kem()\n")
    assert issues == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("algo", "finalized_hint"),
    [
        ("kyber512", "ML-KEM"),
        ("dilithium2", "ML-DSA"),
        ("sphincs_plus", "SLH-DSA"),
    ],
)
def test_pre_standard_pqc_name_warns_with_migration_hint(
    tmp_path: Path, algo: str, finalized_hint: str
) -> None:
    """Round-3 names warn (not error) and point at the finalized FIPS name."""
    issues = _issues_for(tmp_path, f'def use(factory):\n    factory.new("{algo}")\n')
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == "warning"
    assert issue.category == "pqc"
    assert issue.fix_hint is not None
    assert finalized_hint in issue.fix_hint


@pytest.mark.unit
def test_pre_standard_pqc_attribute_call_warns(tmp_path: Path) -> None:
    """A pre-standard name inside a method name is caught on attribute calls."""
    issues = _issues_for(tmp_path, "def use(signer):\n    signer.dilithium_sign()\n")
    assert [issue.category for issue in issues] == ["pqc"]
    assert issues[0].severity == "warning"


@pytest.mark.unit
def test_pqc_exemption_does_not_suppress_classical_findings(
    tmp_path: Path,
) -> None:
    """DES and md5 findings survive alongside PQC names in the same file."""
    source = (
        "import hashlib\n"
        "def mixed(cipher, kem):\n"
        "    hashlib.md5(b'x')\n"
        '    cipher.new("des")\n'
        '    kem.new("ml-kem")\n'
        '    kem.new("kyber768")\n'
    )
    issues = _issues_for(tmp_path, source)
    severities = sorted(issue.severity for issue in issues)
    assert severities == ["error", "error", "warning"]
    messages = " | ".join(issue.message for issue in issues)
    assert "md5" in messages
    assert "des" in messages
    assert "kyber768" in messages


@pytest.mark.unit
def test_pre_standard_match_is_substring_and_warn_only(tmp_path: Path) -> None:
    """An identifier merely embedding a legacy name still warns, by design.

    The match is a substring test, so ``describe_kyber_migration`` trips the
    same nudge as a real ``kyber512`` call. This characterizes that boundary:
    the over-match is acceptable because the finding is warn-only (severity
    ``warning``, never ``error``), so a false positive costs a benign warning,
    not a blocked build. A name with no legacy substring stays silent.
    """
    warns = _issues_for(
        tmp_path, "def use(factory):\n    factory.describe_kyber_migration()\n"
    )
    assert [issue.severity for issue in warns] == ["warning"]
    assert warns[0].category == "pqc"

    clean = _issues_for(tmp_path, "def use(factory):\n    factory.ed25519_sign()\n")
    assert clean == []


@pytest.mark.unit
def test_ambiguous_names_are_subset_of_cipher_denylist() -> None:
    """The context gate only narrows existing findings, never adds names.

    Every ambiguous name must already be in NON_FIPS_CIPHERS; an entry
    outside the denylist would be dead configuration that silently gates
    nothing.
    """
    assert AMBIGUOUS_CIPHER_NAMES <= NON_FIPS_CIPHERS


@pytest.mark.unit
def test_bare_seed_call_without_crypto_context_not_flagged(tmp_path: Path) -> None:
    """A domain seed() call is not the SEED cipher (the PR #205 regression).

    ``seed_staging.seed()`` and ``random.seed()`` carry no cryptographic
    context and must report nothing.
    """
    source = (
        "import random\n"
        "from scripts import seed_staging\n"
        "async def run():\n"
        "    random.seed(42)\n"
        "    await seed_staging.seed()\n"
    )
    assert _issues_for(tmp_path, source) == []


@pytest.mark.unit
def test_seed_call_with_crypto_import_flagged_regardless_of_order(
    tmp_path: Path,
) -> None:
    """A seed() call in a module importing a crypto library errors.

    The import appears after the call: crypto context is a whole-module
    pre-scan, not a statement-order accident.
    """
    source = "def use(c, key):\n    c.seed(key)\nfrom Crypto.Cipher import SEED\n"
    issues = _issues_for(tmp_path, source)
    assert [issue.severity for issue in issues] == ["error"]
    assert "seed" in issues[0].message


@pytest.mark.unit
def test_seed_call_via_crypto_attribute_chain_flagged(tmp_path: Path) -> None:
    """An attribute chain through a crypto namespace supplies context alone."""
    issues = _issues_for(tmp_path, "def use(lib, key):\n    lib.cipher.seed(key)\n")
    assert [issue.severity for issue in issues] == ["error"]


@pytest.mark.unit
def test_seed_string_in_new_call_follows_the_same_gate(tmp_path: Path) -> None:
    """.new("seed") is gated identically to the attribute-call form."""
    assert _issues_for(tmp_path, 'def use(f):\n    f.new("seed")\n') == []

    with_context = _issues_for(
        tmp_path,
        'import Cryptodome.Cipher\ndef use(f):\n    f.new("seed")\n',
    )
    assert [issue.severity for issue in with_context] == ["error"]


@pytest.mark.unit
def test_unambiguous_cipher_call_flagged_without_any_context(tmp_path: Path) -> None:
    """Names with no benign reading (rc4, blowfish) never need context."""
    issues = _issues_for(
        tmp_path, "def use(x, data):\n    x.rc4(data)\n    x.blowfish(data)\n"
    )
    assert [issue.severity for issue in issues] == ["error", "error"]
