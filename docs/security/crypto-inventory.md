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
termination to infrastructure (Cloudflare at the edge, then Traefik in `homelab-infra`).
Quantum-risk priorities per ADR-013: key-exchange legs first (harvest-now-decrypt-later),
signatures deferred.

| # | Surface | Mechanism | Algorithms | Owner | Quantum risk | Posture |
|---|---------|-----------|------------|-------|--------------|---------|
| 1 | Bearer-token verification | PyJWT + JWKS | RS256/ES256 (config-driven) | this repo | Forgery-only (deferred) | Agile via `OIDC_ALLOWED_ALGS` |
| 2 | Client to Cloudflare edge | TLS 1.3 | Hybrid X25519MLKEM768 (browser+edge default) | Cloudflare | HNDL | Already hybrid |
| 3 | Edge to origin (Cloudflare to Traefik) | TLS 1.3 | Hybrid X25519MLKEM768 | homelab-infra | HNDL | Hybrid since 2026-08-02 |
| 4 | Charon to homelab, then to app | WireGuard, then internal TLS/HTTP | Curve25519 (WireGuard) | homelab-infra | HNDL | No WireGuard PQ option yet |
| 5 | Backend to Supabase Postgres | TLS (session pooler) | Classical | Supabase | HNDL (accepted) | Third-party gate |
| 6 | Backend to LLM/image APIs | TLS via httpx | OS OpenSSL defaults | this repo + OS | HNDL | Inherits OpenSSL 3.5 groups |
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

Documented chain (`docs/architecture/deployment.md`, corroborated by `homelab-infra`): Cloudflare's
proxied DNS points at the Charon VPS, and Cloudflare reaches it **over TLS on 443**. Public TLS is
terminated by **Traefik on Charon** (`services/pangolin/vps/docker-compose.yml`, `websecure`
entrypoint on `:443`), not by Pangolin, which is an HTTP service behind that Traefik. Only inside
Charon does the traffic enter the WireGuard tunnel (Gerbil on the VPS to Newt on the docker host),
which carries already-decrypted TCP; a second Traefik on the docker host re-terminates TLS and
forwards to nginx and to FastAPI on port 8000. LAN clients bypass Cloudflare entirely via
split-horizon DNS plus mTLS. There is no `cloudflared` process in this stack. No file in this repo
pins TLS versions, cipher suites, or groups; that is deliberate and lives in `homelab-infra` plus
the Cloudflare dashboard.

The distinction between the two legs is not pedantry: they fail differently, and conflating them
hides the failure that actually occurred. Cloudflare to Charon is a TLS negotiation whose group is
chosen by Traefik's Go version; Charon to homelab is WireGuard, whose posture is fixed by the
protocol and has no group to negotiate.

- **Client to edge**: hybrid X25519MLKEM768 by default (Cloudflare edge, modern browsers).
- **Edge to origin**: TLS, and **now hybrid**. Cloudflare offers origins only post-quantum groups
  (`0x11ec` X25519MLKEM768 and `0xfe32`). The Traefik build then running on Charon (v3.4.0,
  Go 1.23) supported neither, answered with TLS alert 40, and Cloudflare surfaced that as HTTP
  525: on 2026-08-02 both `cyo` and `cyo-staging` were publicly unreachable until Charon's Traefik
  was moved to v3.7.10. Verified
  2026-08-02 against the origin directly:
  `openssl s_client -connect 66.42.78.207:443 -servername cyo.williamshome.family
  -groups X25519MLKEM768 -tls1_3` returns `Negotiated TLS1.3 group: X25519MLKEM768`. This is the
  one leg where a routine version floor is load-bearing for availability, not just for posture.
- **Charon to homelab**: Newt/Gerbil (WireGuard), so its post-quantum posture is WireGuard's, not
  a TLS group, and it is not addressed by keeping any Cloudflare daemon current. WireGuard has no
  standardized hybrid handshake in this deployment, so this leg stays classical (Curve25519) and
  is deferred under ADR-013's key-exchange-first ordering.
- **Backend egress** (`httpx`): OpenRouter/Anthropic/Gemini/Supabase JWKS fetches use the
  container's OpenSSL defaults. Runtime image `dhi-python:3.14-debian13` ships OpenSSL 3.5.x,
  so hybrid groups are offered when the far end supports them; the 3.5 floor is asserted in
  CI by the `fips-runtime-parity` and `fips-image-floor` jobs (see section 7).
- **Ollama leg**: RETIRED. The leg built its own `ssl.SSLContext` from a private homelab CA
  (`OLLAMA_CA_BUNDLE`) and refused cleartext HTTP Basic off-loopback
  (`_reject_cleartext_basic_auth`). Both the private-CA trust path and the reversible
  Basic-auth credential are gone with it, so the remaining external LLM-provider HTTP legs
  verify against the public CA store and carry their credential in a header over TLS.
  Database and Redis transport are separate and are documented in their own entries below.
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
| Runtime base image | Debian 13 | `dhi-python:3.14-debian13` | OpenSSL 3.5.x (ML-KEM groups) |
| Traefik on Charon (homelab-infra) | >= 3.6 (Go 1.24+) | `v3.7.10` running; repo pins `3.6` | Terminates the Cloudflare leg; below the floor the site is **down**, not merely classical |
| Traefik on docker host (homelab-infra) | >= 3.6 (Go 1.24+) | `dhi-traefik:3.6-debian13` | X25519MLKEM768 default in crypto/tls |
| Pangolin/Go proxies (homelab-infra) | Go 1.24+ builds | verify in homelab-infra | Behind Charon Traefik; no public TLS termination |
| nginx (homelab-infra) | OpenSSL 3.5+ build | verify in homelab-infra | ML-KEM group support |
| Newt/Gerbil WireGuard (homelab-infra) | current | verify in homelab-infra | Charon-to-homelab leg; WireGuard PQ posture, not TLS groups |

## 7. Tooling guardrails

- `scripts/check_fips_compatibility.py`: flags non-FIPS hashes/ciphers; treats FIPS 203/204/205
  names and `X25519MLKEM768` as approved; warns on pre-standardization names (Kyber, Dilithium,
  SPHINCS+) with migration hints. Ambiguous cipher names (`seed`, `idea`) require cryptographic
  context (a crypto-library import or a crypto namespace in the call chain) before flagging.
- **Acknowledged-findings baseline** (2026-07-17): CI runs the checker at `--fail-level info`,
  so every finding must be fixed or carry a fresh acknowledgment under
  `[tool.fips_check.acknowledged]` in `pyproject.toml` (mandatory reason, reference into this
  inventory, and reviewed date; entries expire after 90 days, matching the ADR-013 quarterly
  review). Current entries: `cryptography`, `pyjwt`, `httpx`, `boto3`, each citing its section
  here. Errors can never be acknowledged.
- **Runtime assertions**: `tests/unit/test_fips_runtime_assertions.py` mechanically enforces
  the testable half of those dispositions (cryptography >= 45 and OpenSSL 3.x link, pyjwt
  >= 2.13, stdlib OpenSSL floor with a TLS 1.2+ context floor, asymmetric-only JWT allowlist
  defaults plus an active startup validator). They run in the regular CI suite and in the
  `fips-runtime-test` workflow job; do not renew a reviewed date while its assertion is red.
- **Runtime OpenSSL floor is asserted, not assumed** (2026-07-17): the stdlib OpenSSL floor
  is parametrized via `FIPS_STDLIB_OPENSSL_FLOOR` (3.0 on ordinary hosts, whose uv-managed
  interpreters statically link OpenSSL 3.0.x). Two CI jobs in `fips-compatibility.yml` raise
  it to the ML-KEM-capable line: `fips-runtime-parity` runs the assertion suite on the
  Debian 13 python line (`python:3.14-slim-trixie`, same distro OpenSSL 3.5.x as the
  hardened runtime base) with the floor at 3.5, and `fips-image-floor` executes a shell-free
  `python -c` check inside the pinned `dhi-python:3.14-debian13` digest itself. A base-image
  digest bump that regressed below OpenSSL 3.5 now fails CI (`Dockerfile` is in the
  workflow's trigger paths).
- `core/config.py` startup validators fail the boot on forgeable JWT allowlist values.
- Bandit, OSV-Scanner, pip-audit, detect-secrets: general dependency and secret hygiene.

## Open items

- `homelab-infra`: enable and mechanically verify hybrid key exchange on the ingress legs
  (ADR-013 decision 2).
- Header-size capacity test before any PQC signature enablement (ADR-013 decision 5).
- Quarterly review of the signature-migration gates (Supabase, JOSE, PyJWT).
