---
title: "ADR-013: Hybrid post-quantum cryptography readiness"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the key-exchange-first hybrid post-quantum posture: hybrid X25519+ML-KEM TLS as
  the target for every leg we control, crypto agility (no hardcoded algorithm lists) in this
  repo, and explicit gates for the deferred signature migration."
tags:
  - planning
  - architecture
  - decisions
  - security
---

# ADR-013: Hybrid post-quantum cryptography readiness

> **Status**: Accepted (2026-07-11; amended 2026-08-02, see Amendment below)
> **Date**: 2026-07-11
> **Relates to**: [ADR-009](./adr-009-supabase-platform.md) (Supabase auth and JWKS verification),
> [ADR-004](./adr-004-homelab-first-deployment.md) (deployment topology and the external TLS layer)

## Amendment (2026-08-02): there is no Cloudflare Tunnel, and the edge leg is now hybrid

The `cloudflared`/"Cloudflare Tunnel" references in this ADR describe infrastructure the
deployment no longer uses; a security review flagged the drift. They appear in **TL;DR**,
**Context > Constraints**, **Decision item 2**, and **Consequences > Technical Debt**. They do not
appear in the Implementation section.

The actual chain: Cloudflare's proxied DNS points at the Charon VPS and reaches it over **TLS on
443**, where **Traefik on Charon terminates**; only inside Charon does traffic enter the WireGuard
tunnel (Gerbil to Newt) to the homelab, where a second Traefik re-terminates. Pangolin sits behind
Charon's Traefik as an HTTP service and does not terminate public TLS. There is no `cloudflared`
process anywhere in the stack. LAN clients bypass Cloudflare entirely through split-horizon DNS
(an Unbound override routing straight to the homelab) plus mTLS. Tailscale is likewise not in this
path.

**The decision itself is unchanged, and its target has now been met on the leg that matters.**
`X25519MLKEM768` is negotiated on the Cloudflare-to-origin leg as of 2026-08-02, verified directly
against the origin. Getting there was not routine: Cloudflare now offers origins only post-quantum
groups, the Traefik build then running on Charon supported none of them, and the resulting TLS
alert 40 took both `cyo` and `cyo-staging` publicly offline until Traefik was moved to v3.7.10.
That makes the Go/Traefik version floor an availability control on this leg, not merely a posture
one; see `docs/security/crypto-inventory.md` section 2 and its dependency-floor table.

The one voided item is the "keep `cloudflared` current" tracking entry in Technical Debt, since
there is no `cloudflared` to keep current. The sections below are left as originally written
rather than silently rewritten, following the amendment convention used in ADR-003, ADR-005,
ADR-007, ADR-009, ADR-015, and ADR-020; do not action the `cloudflared` items in them.

## TL;DR

Adopt a key-exchange-first hybrid post-quantum posture. Hybrid X25519+ML-KEM-768 key agreement
(the `X25519MLKEM768` TLS group) is the target for every TLS leg we control; enabling it is an
infrastructure concern (Cloudflare edge and Tunnel, the Pangolin/nginx layer in the separate
`homelab-infra` repo), not application code. This repo's contribution is crypto agility: the JWT
signature-algorithm allowlist moves from a hardcoded list in `api/deps.py` into configuration
(`OIDC_ALLOWED_ALGS`, validated at startup), the FIPS checker learns the finalized FIPS
203/204/205 algorithm names, dependency floors are pinned, and a living cryptographic inventory
is maintained at `docs/security/crypto-inventory.md`. The signature migration (ML-DSA JWTs,
composite certificates) is explicitly deferred behind ecosystem gates and revisited quarterly.

## Context

### Problem

The application carries children's profile data, story content, and guardian credentials and
bearer tokens over TLS. The relevant quantum threat today is harvest-now-decrypt-later (HNDL):
an adversary recording classically-encrypted traffic now and decrypting it once a
cryptographically relevant quantum computer exists. For a children's product whose data remains
sensitive for a decade or more, HNDL is a present-tense recording risk, not a future one.

NIST finalized the post-quantum standards in August 2024: FIPS 203 (ML-KEM, key encapsulation),
FIPS 204 (ML-DSA, signatures), and FIPS 205 (SLH-DSA, hash-based signatures). Browsers and
Cloudflare's edge already negotiate hybrid X25519+ML-KEM key agreement by default. Before this
ADR, the repo had exactly one hardcoded algorithm decision (the `["RS256", "ES256"]` JWT
allowlist in `api/deps.py`), a FIPS compatibility checker with no knowledge of the finalized PQC
names, and no documented cryptographic inventory or PQC position.

### Constraints

- **Technical**: TLS termination happens entirely outside this repo
  (`docs/architecture/deployment.md`: Cloudflare or Tailscale into Pangolin, which forwards
  plain HTTP to the backend), so the key-exchange work cannot land here. Supabase issues only
  classical RS256/ES256 JWTs today, and the JOSE algorithm registrations for ML-DSA are still
  in flight, so a signature migration is not actionable yet regardless of local readiness.
- **Operational**: a solo operator; every posture claim must be mechanically verifiable
  (negotiated-group checks, startup validators, CI) rather than assumed.
- **Regulatory**: FIPS alignment is a template-level goal (`scripts/check_fips_compatibility.py`);
  there is no hard PQC mandate for this project, but COPPA-adjacent duty of care motivates
  treating children's data confidentiality on long horizons.

### Significance

This decision sets the project's algorithm-transition posture generally, not just for PQC: the
same agility (config-driven allowlists, JWKS key discovery, a maintained inventory, checker
guardrails) is what makes any future migration cheap, including a hypothetical migration away
from an algorithm broken classically.

## Decision

1. **Threat model and scope.** HNDL against recorded traffic is the priority. Confidentiality
   (key exchange) migrates first; authentication (signatures) is deferred. A signature forged
   after a quantum computer exists cannot retroactively decrypt traffic recorded today, so
   deferring signatures loses nothing against HNDL. This matches the sequencing in NIST and
   CNSA 2.0 guidance.

2. **Hybrid key exchange is the target for every TLS leg we control.** The target group is
   `X25519MLKEM768` (classical X25519 combined with ML-KEM-768; the hybrid construction keeps
   classical security even if the ML-KEM half fails). Ownership:
   - Client to Cloudflare edge: already hybrid by default (Cloudflare edge plus modern
     browsers); nothing to do beyond not disabling it.
   - Cloudflare Tunnel leg: keep `cloudflared` current; Cloudflare ships PQC support in the
     tunnel daemon.
   - Pangolin/nginx ingress (the `homelab-infra` repo): Pangolin components are Go, and Go's
     `crypto/tls` enables `X25519MLKEM768` by default from Go 1.24; nginx requires an OpenSSL
     3.5+ build. Enablement and a negotiated-group verification check (for example
     `openssl s_client -groups X25519MLKEM768` against the live endpoint) are tracked in
     `homelab-infra`, not here.

3. **Crypto agility in this repo: no hardcoded algorithm lists.** The JWT signature-algorithm
   allowlist is configuration (`Settings.oidc_allowed_algs`, env `OIDC_ALLOWED_ALGS`, default
   `["RS256", "ES256"]`). A startup validator refuses an empty list, `none`, and the symmetric
   `HS*` family, so the agility cannot reopen the alg=none or key-confusion forgeries the
   hardcoded list defended against. JWKS-based key discovery (ADR-009) is retained as the key
   rotation mechanism; when the issuer adds a PQC key alongside a classical one, the verifier
   picks it up once the algorithm is allowlisted.

4. **Dependency floors.** `cryptography` >= 45 (ML-DSA/SLH-DSA primitives; currently 49.0.0 via
   `pyjwt[crypto]`), runtime container on Debian 13 (OpenSSL 3.5.x, already true of
   `dhi-python:3.14-debian13`), and Go 1.24+ builds for the Go proxies in `homelab-infra`.
   Floors are recorded in the cryptographic inventory; downgrades are treated as regressions.

5. **Signature migration is deferred behind explicit gates**, revisited quarterly:
   - Supabase issues ML-DSA (or composite) signed tokens;
   - the JOSE algorithm registrations for ML-DSA are finalized;
   - PyJWT verifies them;
   - a header-size capacity test passes: an ML-DSA-44 signature is roughly 2.4 KB, the bearer
     token rides in the `Authorization` header on every API request and is stored in
     `localStorage`, so proxy and server header limits must be verified before enabling.

6. **The FIPS checker recognizes PQC.** `scripts/check_fips_compatibility.py` treats the
   finalized FIPS 203/204/205 names (ML-KEM, ML-DSA, SLH-DSA) and `X25519MLKEM768` as approved,
   and warns on pre-standardization names (Kyber, Dilithium, SPHINCS+) with a migration hint to
   the finalized parameter sets.

7. **A living cryptographic inventory** is maintained at `docs/security/crypto-inventory.md`
   (the CBOM). It is updated whenever a crypto-adjacent dependency, TLS leg, or algorithm
   choice changes, and it is the input to every future transition decision.

**Out of scope (accepted classical third-party legs)**: TLS to Supabase Postgres (session
pooler) and Supabase Auth, which Supabase controls; Redis, which runs plaintext on the internal
Docker network (a network-trust decision, not a PQC one); DNSSEC, which Cloudflare operates and
for which no PQC standard exists yet. Each is recorded in the inventory with its rationale.

## Options Considered

### Option 1: Key-exchange-first hybrid posture plus crypto agility ✓

Migrate confidentiality where we control it, make the one hardcoded algorithm choice
configurable with guardrails, pin floors, and gate the signature migration on the ecosystem.
Low cost now, directly addresses HNDL, and leaves no cliff when upstream support lands.

### Option 2: Full simultaneous migration including signatures

Rejected: not actionable. Supabase does not issue PQC-signed tokens, the JOSE registrations are
unfinished, and oversized tokens have real header-size and storage costs. Against HNDL it adds
no protection over Option 1.

### Option 3: Wait until standards and vendors fully mature

Rejected: leaves recorded traffic decryptable later and accrues agility debt. The cheap steps
(config-driven allowlist, checker awareness, inventory, infra upgrades that are routine version
bumps) cost little now and are exactly the steps that make the eventual mandatory migration
routine instead of an emergency.

## Consequences

### Positive

- HNDL exposure on the legs we control shrinks to routine version upgrades plus one
  verification check.
- A future PQC JOSE algorithm is an env change (`OIDC_ALLOWED_ALGS`), not a code change.
- The startup validator and the extended FIPS checker convert posture rules into mechanical
  enforcement.
- The inventory makes the next transition (PQC or otherwise) a diff against a known baseline.

### Trade-offs

- A configurable allowlist is a new misconfiguration surface; mitigated by the startup
  denylist validator (empty, `none`, `HS*` all refuse to boot) and tests.
- The decisive key-exchange work and its verification live in a different repo
  (`homelab-infra`); this ADR records the target, but cross-repo tracking is manual.
- The quarterly gate review is operator discipline, not automation.

### Technical Debt

- `homelab-infra`: enable and verify `X25519MLKEM768` on Pangolin/nginx; keep `cloudflared`
  current (tracked there).
- The header-size capacity test for oversized PQC tokens does not exist yet; required before
  the signature gates can close.

## Implementation

### Components Affected

- `src/cyo_adventure/core/config.py`: `oidc_allowed_algs` field plus the
  `_reject_forgeable_jwt_algorithms` validator.
- `src/cyo_adventure/api/deps.py`: `_verify_oidc_jwt` reads the configured allowlist.
- `scripts/check_fips_compatibility.py`: FIPS 203/204/205 approved names, pre-standard-name
  warnings, updated package hints.
- `.env.example`: documents `OIDC_ALLOWED_ALGS`.
- `docs/security/crypto-inventory.md`: the new inventory (created with this ADR).

### Testing Strategy

- `tests/unit/test_config.py::TestOidcAllowedAlgs`: default value, empty-list rejection,
  `none` rejection, `HS*` rejection, PQC-name acceptance, unprefixed env alias.
- `tests/unit/test_oidc_verification.py::test_algorithm_allowlist_is_config_driven`: narrowing
  the setting rejects an otherwise-valid token, proving the setting drives verification.
- The existing negative-token suite (expired, wrong issuer/audience/key, tampered, alg=none,
  HS256 confusion) is unchanged and still green, demonstrating no security regression.

## Validation

- Full unit suite green, including the new tests above.
- `scripts/check_fips_compatibility.py` passes on `src/` with no new findings, and correctly
  warns on synthetic pre-standard PQC names while accepting finalized ones.
- Negotiated-group verification against the live endpoints is the `homelab-infra` acceptance
  check for the key-exchange half.

## References

- NIST FIPS 203 (ML-KEM), FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA), August 2024.
- `docs/architecture/deployment.md` (the TLS termination chain this ADR builds on).
- `docs/security/crypto-inventory.md` (the living inventory this ADR mandates).
- [ADR-009](./adr-009-supabase-platform.md) (JWKS verification design this ADR extends).
