---
title: "Cryptographic Inventory (CBOM)"
schema_type: common
status: published
owner: core-maintainer
purpose: "Living inventory of every cryptographic touchpoint in CYO Adventure: algorithms, key
  exchange legs, signatures, hashing, and dependency floors, with quantum-risk posture per
  ADR-013."
tags:
  - security
  - reference
  - compliance
---

Audited: 2026-07-11 (full-repo sweep; function-level citations below are stable anchors, line
numbers drift).
Mandated by: [ADR-013](../planning/adr/adr-013-hybrid-pqc-readiness.md) (hybrid post-quantum
readiness).
Update trigger: any change to a crypto-adjacent dependency, TLS leg, algorithm choice, or
token/signing scheme must update this file in the same PR.

## Summary

The application performs almost no cryptography itself. It verifies JWTs issued by Supabase,
computes SHA-256 fingerprints for non-security integrity checks, and delegates all TLS
termination to infrastructure (Cloudflare and the Pangolin/nginx layer in `homelab-infra`).
Quantum-risk priorities per ADR-013: key-exchange legs first (harvest-now-decrypt-later),
signatures deferred.

| # | Surface | Mechanism | Algorithms | Owner | Quantum risk | Posture |
|---|---------|-----------|------------|-------|--------------|---------|
| 1 | Bearer-token verification | PyJWT + JWKS | RS256/ES256 (config-driven) | this repo | Forgery-only (deferred) | Agile via `OIDC_ALLOWED_ALGS` |
| 2 | Client to Cloudflare edge | TLS 1.3 | Hybrid X25519MLKEM768 (browser+edge default) | Cloudflare | HNDL | Already hybrid |
| 3 | Edge to origin (Tunnel/Pangolin) | TLS | Classical today | homelab-infra | HNDL | Target: X25519MLKEM768 |
| 4 | Pangolin to backend | Plain HTTP (internal) | none | homelab-infra | n/a | Trusted network segment |
| 5 | Backend to Supabase Postgres | TLS (session pooler) | Classical | Supabase | HNDL (accepted) | Third-party gate |
| 6 | Backend to LLM/image APIs | TLS via httpx | OS OpenSSL defaults | this repo + OS | HNDL | Inherits OpenSSL 3.5 groups |
| 7 | Backend to Ollama (homelab) | TLS + private CA | OS OpenSSL defaults | this repo | HNDL (LAN) | Inherits OpenSSL 3.5 groups |
| 8 | Backend to R2 (covers) | TLS + SigV4 | HMAC-SHA256 request signing | boto3/Cloudflare | Safe (symmetric) | No change needed |
| 9 | Integrity hashing | hashlib | SHA-256 | this repo | Safe | No change needed |
| 10 | Frontend auth session | supabase-js, token in localStorage | none locally (opaque token) | this repo | n/a | Size-sensitive to PQC tokens |

## 1. Bearer-token verification (the only in-repo algorithm decision)

- `src/cyo_adventure/api/deps.py::_verify_oidc_jwt`: verifies Supabase-issued JWTs via
  `jwt.PyJWKClient` against `OIDC_JWKS_URL` (signature, issuer, audience, expiry; `exp`, `iat`,
  `sub` required). No token is ever signed by this project.
- Algorithm allowlist: `Settings.oidc_allowed_algs` (env `OIDC_ALLOWED_ALGS`, default
  `["RS256", "ES256"]`). The startup validator
  (`core/config.py::_reject_forgeable_jwt_algorithms`) refuses an empty list, `none`, and the
  symmetric `HS*` family.
- Key discovery/rotation: JWKS by `kid`; a PQC key added by the issuer is picked up with no
  code change once its algorithm is allowlisted.
- Negative-token suite: `tests/unit/test_oidc_verification.py` (expired, wrong
  issuer/audience/key, tampered signature, alg=none, HS256 confusion, config-driven allowlist).
- Quantum posture: signature forgery only; deferred per ADR-013 decision 5 (gated on Supabase,
  JOSE registration, PyJWT, and a header-size capacity test; ML-DSA-44 signatures are ~2.4 KB).

## 2. TLS legs

Documented chain (`docs/architecture/deployment.md`): Cloudflare (Tunnel) or Tailscale into
Pangolin, which terminates TLS and forwards plain HTTP to FastAPI on port 8000; an nginx rung
serves the R1 internal-web tier. No file in this repo pins TLS versions, cipher suites, or
groups; that is deliberate and lives in `homelab-infra` plus the Cloudflare dashboard.

- **Client to edge**: hybrid X25519MLKEM768 by default (Cloudflare edge, modern browsers).
- **Edge to origin**: keep `cloudflared` current for tunnel PQC; Pangolin (Go) picks up
  X25519MLKEM768 from Go 1.24+ builds; nginx needs an OpenSSL 3.5+ build. Verification
  (negotiated-group check) is the `homelab-infra` acceptance test.
- **Backend egress** (`httpx`): OpenRouter/Anthropic/Gemini/Supabase JWKS fetches use the
  container's OpenSSL defaults. Runtime image `dhi-python:3.12-debian13` ships OpenSSL 3.5.x,
  so hybrid groups are offered when the far end supports them.
- **Ollama leg**: `src/cyo_adventure/generation/provider.py` builds
  `ssl.create_default_context()` and adds the homelab CA (`certs/homelab-ca.pem` via
  `OLLAMA_CA_BUNDLE`); cleartext HTTP Basic is refused off-loopback
  (`_reject_cleartext_basic_auth`). Groups inherit from OpenSSL.
- **Supabase Postgres**: session pooler over TLS, driver defaults, no explicit `sslmode` in
  code; classical until Supabase offers PQC transport (accepted, ADR-013 out-of-scope list).
- **Redis**: `redis://` (no TLS) on the internal Docker network; a network-trust boundary, not
  a crypto control.

## 3. Signatures and request signing

- **R2 uploads**: `src/cyo_adventure/covers/storage.py` uses boto3 with
  `signature_version="s3v4"` (SigV4, HMAC-SHA256). Symmetric; quantum-safe at current sizes.
  Covers are served from a public custom-domain base URL; there are no presigned/expiring URLs.
- **No app-level HMAC, webhook signing, or `secrets`-based token generation exists** in `src/`
  or `scripts/`. Modal uses a `Modal-Key`/`Modal-Secret` header pair (transport-protected).
- **Dev/CI process signatures** (out of app scope, listed for completeness): GPG-signed
  commits; `scripts/render_skeleton_diagrams.py` pins the PlantUML jar by SHA-256.

## 4. Hashing

SHA-256 only, none of it security-load-bearing:

- `src/cyo_adventure/generation/orchestrator.py`: document/finding fingerprints.
- `scripts/render_skeleton_diagrams.py`: PlantUML jar integrity pin.

Grover's algorithm at most halves effective preimage strength; SHA-256 remains adequate. No
MD5/SHA-1 anywhere (enforced by `scripts/check_fips_compatibility.py`).

## 5. Frontend

- `frontend/src/auth/supabaseClient.ts`: `createClient(VITE_SUPABASE_URL,
  VITE_SUPABASE_ANON_KEY)`; the anon key is a public identifier, not a secret.
- `frontend/src/auth/AuthContext.tsx`: stores `session.access_token` in
  `localStorage['auth_token']`; the frontend never parses or verifies tokens. PQC-sized tokens
  (~4 KB+) would inflate every `Authorization` header and this storage slot; the header-size
  capacity test in ADR-013 decision 5 covers this.
- No `jose`/`jsonwebtoken` dependency; browser TLS is item 2 above.

## 6. Dependency floors (regressions below these are posture regressions)

| Dependency | Floor | Current (2026-07-11) | Why |
|------------|-------|----------------------|-----|
| `pyjwt[crypto]` | >= 2.13 | 2.13.0 | JWKS client, allowlist enforcement |
| `cryptography` (via pyjwt extra) | >= 45 | 49.0.0 | ML-DSA/SLH-DSA (FIPS 204/205) primitives |
| Runtime base image | Debian 13 | `dhi-python:3.12-debian13` | OpenSSL 3.5.x (ML-KEM groups) |
| Pangolin/Go proxies (homelab-infra) | Go 1.24+ builds | verify in homelab-infra | X25519MLKEM768 default in crypto/tls |
| nginx (homelab-infra) | OpenSSL 3.5+ build | verify in homelab-infra | ML-KEM group support |
| `cloudflared` (homelab-infra) | current | verify in homelab-infra | Tunnel PQC support |

## 7. Tooling guardrails

- `scripts/check_fips_compatibility.py`: flags non-FIPS hashes/ciphers; treats FIPS 203/204/205
  names and `X25519MLKEM768` as approved; warns on pre-standardization names (Kyber, Dilithium,
  SPHINCS+) with migration hints.
- `core/config.py` startup validators fail the boot on forgeable JWT allowlist values.
- Bandit, OSV-Scanner, pip-audit, detect-secrets: general dependency and secret hygiene.

## Open items

- `homelab-infra`: enable and mechanically verify hybrid key exchange on the ingress legs
  (ADR-013 decision 2).
- Header-size capacity test before any PQC signature enablement (ADR-013 decision 5).
- Quarterly review of the signature-migration gates (Supabase, JOSE, PyJWT).
