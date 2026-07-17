"""Runtime assertions backing the FIPS acknowledgment baseline (ADR-013).

Each ``[tool.fips_check.acknowledged]`` entry in pyproject.toml dispositions
one info-level finding from ``scripts/check_fips_compatibility.py`` and cites
a written rationale in ``docs/security/crypto-inventory.md``. The tests here
are the mechanical half of those dispositions: they convert "may need FIPS
verification" nudges into assertions that run on every CI leg and in the
``fips-runtime-test`` workflow job.

If a test in this module fails, the acknowledgment it backs is no longer
true. Fix the regression (or re-verify the disposition); do not renew the
acknowledgment's ``reviewed`` date while its backing assertion is red.

Deliberately not asserted here, because they are host/deployment properties
CI cannot observe: OpenSSL FIPS-provider activation, the runtime image's
OpenSSL 3.5 ML-KEM groups (a property of ``dhi-python:3.12-debian13``, not of
the CI host), and boto3 endpoint selection (R2 uses SigV4/HMAC-SHA256, which
is quantum-safe; AWS FIPS endpoints do not apply).
"""

from __future__ import annotations

import ssl

import pytest

# Dependency floors from docs/security/crypto-inventory.md section 6.
# Downgrades below these are posture regressions per ADR-013.
CRYPTOGRAPHY_MAJOR_FLOOR = 45  # ML-DSA/SLH-DSA (FIPS 204/205) primitives
PYJWT_FLOOR = (2, 13)  # JWKS client + allowlist enforcement


@pytest.mark.unit
def test_cryptography_meets_ml_dsa_floor() -> None:
    """cryptography >= 45 carries the ML-DSA/SLH-DSA primitives (ADR-013).

    Backs the ``cryptography`` acknowledgment: the floor is also pinned in
    pyproject.toml, so this failing means the resolver constraint was
    weakened or removed.
    """
    import cryptography

    major = int(cryptography.__version__.split(".")[0])
    assert major >= CRYPTOGRAPHY_MAJOR_FLOOR, (
        f"cryptography {cryptography.__version__} is below the ADR-013 floor "
        f"({CRYPTOGRAPHY_MAJOR_FLOOR}); ML-DSA/SLH-DSA primitives are absent"
    )


@pytest.mark.unit
def test_cryptography_links_openssl_3_or_newer() -> None:
    """cryptography's bundled OpenSSL is 3.x+ (FIPS-provider-capable line).

    Backs the ``cryptography`` acknowledgment. OpenSSL 1.x has no FIPS
    provider architecture; 3.x is the line the FIPS 140-3 validated provider
    ships for.
    """
    from cryptography.hazmat.backends.openssl.backend import backend

    version_text = backend.openssl_version_text()
    # Format: "OpenSSL <major>.<minor>.<patch> <date>"
    major = int(version_text.split()[1].split(".")[0])
    assert major >= 3, f"cryptography links {version_text}; need OpenSSL 3.x+"


@pytest.mark.unit
def test_stdlib_ssl_is_openssl_3_or_newer() -> None:
    """The stdlib ssl module (httpx's TLS layer) links OpenSSL 3.x+.

    Backs the ``httpx`` acknowledgment: backend egress inherits these
    defaults. The stricter 3.5 floor (ML-KEM hybrid groups) is a property of
    the runtime image (`dhi-python:3.12-debian13`), not of CI hosts, so only
    the major line is asserted here.
    """
    assert ssl.OPENSSL_VERSION_INFO[0] >= 3, (
        f"stdlib ssl links {ssl.OPENSSL_VERSION}; need OpenSSL 3.x+"
    )


@pytest.mark.unit
def test_default_tls_context_floor_is_tls_1_2() -> None:
    """Default SSL contexts refuse TLS < 1.2 (FIPS-approved protocol floor).

    Backs the ``httpx`` acknowledgment: httpx builds its contexts from these
    stdlib defaults, and no code in this repo lowers ``minimum_version``.
    """
    context = ssl.create_default_context()
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


@pytest.mark.unit
def test_pyjwt_meets_jwks_floor() -> None:
    """PyJWT >= 2.13 is the JWKS-client/allowlist floor (ADR-013).

    Backs the ``pyjwt`` acknowledgment.
    """
    import jwt

    version = tuple(int(part) for part in jwt.__version__.split(".")[:2])
    assert version >= PYJWT_FLOOR, (
        f"pyjwt {jwt.__version__} is below the ADR-013 floor "
        f"{'.'.join(str(p) for p in PYJWT_FLOOR)}"
    )


@pytest.mark.unit
def test_jwt_allowlist_default_is_asymmetric_only() -> None:
    """The default JWT algorithm allowlist contains no forgeable entries.

    Backs the ``pyjwt`` acknowledgment: verification algorithms come from
    ``Settings.oidc_allowed_algs``, and the default must never include
    ``none`` or the symmetric HS* family.
    """
    from cyo_adventure.core.config import Settings

    algs = Settings().oidc_allowed_algs
    assert algs, "empty allowlist would reject every token"
    for alg in algs:
        normalized = alg.strip().upper()
        assert normalized != "NONE"
        assert not normalized.startswith("HS")


@pytest.mark.unit
def test_jwt_allowlist_startup_validator_is_active() -> None:
    """The startup validator still refuses forgeable allowlist values.

    Backs the ``pyjwt`` acknowledgment; the full rejection matrix lives in
    tests/unit/test_config.py::TestOidcAllowedAlgs. This single probe exists
    so the FIPS baseline fails even if that suite were skipped or renamed.
    """
    from cyo_adventure.core.config import Settings
    from cyo_adventure.core.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError):
        Settings(oidc_allowed_algs=["none"])
