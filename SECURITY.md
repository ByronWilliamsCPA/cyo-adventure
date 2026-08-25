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

- **A password reset does not sign out the account's other devices.** The single
  password-change path in the app (`auth/AuthContext.tsx: updatePassword`, reached
  only from the emailed-recovery-link form) calls supabase-js's
  `updateUser({ password })`, which has no session-scope parameter. Verified
  against the live Management API auth config on 2026-08-04: Supabase exposes no
  "revoke sessions on password change" setting to reconcile, and every session
  control that does exist is off in production (`sessions_single_per_user` false,
  `sessions_timebox` 0, `sessions_inactivity_timeout` 0; refresh-token rotation is
  on, with a 10-second reuse interval). This is therefore a platform limitation
  rather than an unset option. The practical consequence: a guardian who resets
  their password because they suspect someone else has access has **not** evicted
  that person, whose existing refresh token keeps working. The available remedies
  are `sessions_single_per_user`, which would also sign a legitimate guardian out
  of their phone whenever they use a laptop, or a server-side
  `auth.admin.signOut` with a scope, which needs a backend endpoint that does not
  exist yet. Neither is wired up, and as of the sign-out scope change described in
  the next bullet there is no de-facto third remedy either. Password policy itself
  is managed as code in `supabase/config.toml` and pushed by the deploy workflows,
  so it is reviewable in git; this gap is about session invalidation, not policy.

- **App-initiated sign-out is device-local by design, so no remedy remains for a
  lost or stolen device.** `auth/AuthContext.tsx: signOut` passes
  `{ scope: 'local' }` to supabase-js explicitly. The library defaults to
  `{ scope: 'global' }`, which revokes every refresh token the account holds, on
  every device. The explicit scope is deliberate: every caller of that primitive is
  device-local by intent, and the motivating case is a kid handover (LoginPage's
  authorize-device, ConsolePage's handoff), where a guardian handing over a tablet
  signs out of that device only. Under the default, doing so silently killed the
  guardian's own session on their phone and laptop, and signing out of one browser
  logged them out of all the others. The tradeoff recorded here is that signing out
  from any device used to revoke every session account-wide, which was a de-facto
  remedy for a lost or stolen device; it no longer is. Combined with the
  password-reset gap above, there is currently no guardian-facing path to evict a
  session on a device the guardian no longer controls. The two remedies named above
  (`sessions_single_per_user`, a server-side `auth.admin.signOut`) remain the only
  candidates, and neither is wired up. If a deliberate "sign out everywhere" surface
  is ever added, it should pass its own scope at that call site rather than drop the
  argument and change the behaviour of every existing caller.

## Organization Policy

See also: [ByronWilliamsCPA organization Security Policy](https://github.com/ByronWilliamsCPA/.github/blob/main/SECURITY.md)

## Security Surface

CYO Adventure is a choose-your-own-adventure reading app for kids, built on FastAPI (Python). The primary security concerns for this project are:

- **Story-content injection**: User-generated or author-supplied story content could embed malicious scripts or links targeting child readers. Mitigations: strict output encoding, content-security-policy headers via security middleware, and input validation on all story payloads.
- **Dependency supply-chain**: Third-party packages introduce transitive vulnerabilities. Mitigations: Bandit static analysis, OSV-Scanner and pip-audit in CI, Dependabot automated updates, and a 60-day remediation policy for unfixed CVEs.
- **CI/CD secret exposure**: Workflow secrets (API tokens, signing keys) could be exfiltrated via malicious PR changes. Mitigations: secret scanning (GitHub native), trufflehog pre-commit hook, required-status-check rulesets on the default branch, and signed commits enforced by GPG.
- **Child-safety data handling**: The app processes account and reading data for minors.
  Mitigations: data minimization by design (a coarse age band and a nickname/display name
  only, no birthdate, exact age, photo, email, phone, or geolocation collected from a
  child), a PII egress guard blocking real-child identifiers and email/phone/address-shaped
  content before it reaches any external provider, cover images served only via
  short-lived presigned R2 URLs (never a permanent public one), verifiable parental
  consent (a typed full-legal-name signature attestation, layered on the guardian's
  OAuth login) gating child-profile creation (`POST /api/v1/profiles` returns 400 until
  recorded), a guardian self-signup admin-approval gate (`User.status='awaiting_approval'`
  blocks every authenticated endpoint, including `GET /v1/me`, until an admin approves
  via `PATCH /api/v1/admin/users/{id}`), a per-profile data-processing restriction flag
  (`PATCH /api/v1/profiles/{id}` with `processing_restricted`) that blocks new
  story-request submission without deleting existing data, scheduled retention purges
  for blocked/declined story-request text and stale deactivated-profile activity,
  guardian-facing erasure (`DELETE /api/v1/profiles/{id}`, `DELETE /api/v1/me/family`)
  and data export/portability (`GET /api/v1/me/export`) endpoints, an append-only audit
  log of every admin cross-family read of child-linked data (`GET /api/v1/admin/profiles`,
  logged as a `profile_viewed` event queryable via `GET /api/v1/admin/audit`) alongside
  every admin/system mutation, and encryption in transit (TLS). **Not yet implemented**:
  a published, guardian-facing privacy notice. See
  [`docs/compliance/coppa-compliance-audit.md`](docs/compliance/coppa-compliance-audit.md)
  and [`docs/compliance/gdpr-compliance-review.md`](docs/compliance/gdpr-compliance-review.md)
  for the full assessment; do not rely on this bullet alone as a compliance claim.
- **Authentication and authorization**: Unauthenticated access to story management or admin endpoints could allow content tampering. Mitigations: authentication middleware, OWASP-aligned security headers via `cyo_adventure.middleware.security`, and correlation-ID tracing for incident investigation.
