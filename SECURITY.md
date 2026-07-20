# Security Policy

## Supported Versions

| Version                    | Supported |
|----------------------------|-----------|
| 0.1.0 | Yes       |

## Reporting a Vulnerability

Do not open a public GitHub issue for security vulnerabilities.

Use GitHub Security Advisories to report privately:
[Private Vulnerability Reporting](https://github.com/ByronWilliamsCPA/cyo-adventure/security/advisories/new)

Or email: byronawilliams@gmail.com

## Response Timeline

- Acknowledgement: within 48 hours (14 days maximum)
- Initial assessment: within 5 business days
- Resolution target: 30 days for critical, 90 days for others
- We commit to acknowledging all vulnerability reports within 14 days of submission at the latest; our target is 48 hours.

## Known Infrastructure Limitations

The following limitations are documented and tracked for remediation before
production deployment or horizontal scaling:

- **Rate limiting is Redis-backed with an in-memory fail-open fallback.**
  `middleware/security.py: RateLimitMiddleware` enforces per-IP rate limits
  using a Redis sorted set (an atomic Lua script), shared across every worker
  process and replica, and keyed on the same Redis instance/URL the RQ task
  queue uses (`core/config.py: Settings.redis_url`,
  `Settings.rate_limit_backend`, default `"redis"` on every deployed tier).
  This closes the multi-process gap tracked as a Phase 5 hardening task in the
  roadmap. If Redis is unreachable or times out, the middleware deliberately
  fails OPEN: it logs a structured `rate_limit_redis_unavailable` warning and
  falls back to the original process-local in-memory counter for a short
  cooldown window before retrying Redis, rather than rejecting or hanging
  every request. This is an intentional availability-over-strictness
  trade-off: during a Redis outage, the effective rate limit reverts to
  per-process enforcement (a client distributing requests across replicas is
  no longer capped in aggregate) until Redis recovers. Operators should alert
  on the `rate_limit_redis_unavailable` log event.

- **Dev auth stub is local-only; real OIDC verification is enforced everywhere
  else.** The bearer-token extraction in `api/deps.py` has two paths: a dev/test
  stub that treats any token as an already-verified OIDC subject (no signature,
  issuer, or expiry validation), and real Supabase-issued JWT verification
  (ADR-009: the project's auth provider, superseding an earlier Authentik plan)
  against a cached JWKS, checking signature, issuer, audience, and expiry, with
  an explicit algorithm allowlist (`RS256`/`ES256` by default) so PyJWT never
  falls back to a caller-supplied algorithm. A module-level guard raises
  `ConfigurationError` at import time if the environment is not `local` and no
  OIDC verification is configured (`OIDC_ISSUER`/`OIDC_JWKS_URL`), so the
  unverified stub cannot silently reach staging or production.

## Organization Policy

See also: [ByronWilliamsCPA organization Security Policy](https://github.com/ByronWilliamsCPA/.github/blob/main/SECURITY.md)

## Security Surface

CYO Adventure is a choose-your-own-adventure reading app for kids, built on FastAPI (Python). The primary security concerns for this project are:

- **Story-content injection**: User-generated or author-supplied story content could embed malicious scripts or links targeting child readers. Mitigations: strict output encoding, content-security-policy headers via security middleware, and input validation on all story payloads.
- **Dependency supply-chain**: Third-party packages introduce transitive vulnerabilities. Mitigations: Bandit static analysis, OSV-Scanner and pip-audit in CI, Dependabot automated updates, and a 60-day remediation policy for unfixed CVEs.
- **CI/CD secret exposure**: Workflow secrets (API tokens, signing keys) could be exfiltrated via malicious PR changes. Mitigations: secret scanning (GitHub native), trufflehog pre-commit hook, required-status-check rulesets on the default branch, and signed commits enforced by GPG.
- **Child-safety data handling**: The app processes account and reading data for minors. Mitigations: data minimization by design (a coarse age band and a nickname/display name only, no birthdate, exact age, photo, email, phone, or geolocation collected from a child), a PII egress guard blocking real-child identifiers and email/phone/address-shaped content before it reaches any external provider, cover images served only via short-lived presigned R2 URLs (never a permanent public one), guardian-facing erasure (`DELETE /api/v1/profiles/{id}`, `DELETE /api/v1/me/family`) and data export/portability (`GET /api/v1/me/export`) endpoints, an append-only audit log of every admin cross-family read of child-linked data (`GET /api/v1/admin/profiles`, logged as a `profile_viewed` event queryable via `GET /api/v1/admin/audit`) alongside every admin/system mutation, and encryption in transit (TLS). **Not yet implemented**: verifiable parental consent gating child-profile creation or data collection, and a published data-retention policy. See [`docs/compliance/coppa-compliance-audit.md`](docs/compliance/coppa-compliance-audit.md) and [`docs/compliance/gdpr-compliance-review.md`](docs/compliance/gdpr-compliance-review.md) for the full assessment; do not rely on this bullet alone as a compliance claim.
- **Authentication and authorization**: Unauthenticated access to story management or admin endpoints could allow content tampering. Mitigations: authentication middleware, OWASP-aligned security headers via `cyo_adventure.middleware.security`, and correlation-ID tracing for incident investigation.
