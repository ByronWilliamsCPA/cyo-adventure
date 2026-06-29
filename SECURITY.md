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

- **Rate limiting is in-memory only.** `middleware/security.py: RateLimitMiddleware`
  enforces per-IP rate limits using a process-local counter. This is effective for
  single-process, single-machine deployments but provides no protection across
  multiple processes or behind a load balancer. Redis-backed rate limiting (e.g.
  `fastapi-limiter`) is required before any multi-instance deployment. Tracked as
  a Phase 5 hardening task in the roadmap.

- **Dev auth stub must be replaced before non-local deployment.** The bearer-token
  extraction in `api/deps.py` treats any token as a verified OIDC subject (no
  signature, issuer, or expiry validation). A module-level guard raises
  `ConfigurationError` at startup if the environment is not `local`, preventing
  accidental staging or production deployment. Real Authentik JWT validation
  (RS256, issuer/audience check) must replace this stub in Phase 3.

## Organization Policy

See also: [ByronWilliamsCPA organization Security Policy](https://github.com/ByronWilliamsCPA/.github/blob/main/SECURITY.md)

## Security Surface

CYO Adventure is a choose-your-own-adventure reading app for kids, built on FastAPI (Python). The primary security concerns for this project are:

- **Story-content injection**: User-generated or author-supplied story content could embed malicious scripts or links targeting child readers. Mitigations: strict output encoding, content-security-policy headers via security middleware, and input validation on all story payloads.
- **Dependency supply-chain**: Third-party packages introduce transitive vulnerabilities. Mitigations: Bandit static analysis, OSV-Scanner and pip-audit in CI, Dependabot automated updates, and a 60-day remediation policy for unfixed CVEs.
- **CI/CD secret exposure**: Workflow secrets (API tokens, signing keys) could be exfiltrated via malicious PR changes. Mitigations: secret scanning (GitHub native), trufflehog pre-commit hook, required-status-check rulesets on the default branch, and signed commits enforced by GPG.
- **Child-safety data handling**: The app may process account data for minors. Mitigations: minimal data collection, no persistent PII without explicit parental consent, and encryption in transit (TLS) and at rest for any stored user data.
- **Authentication and authorization**: Unauthenticated access to story management or admin endpoints could allow content tampering. Mitigations: authentication middleware, OWASP-aligned security headers via `cyo_adventure.middleware.security`, and correlation-ID tracing for incident investigation.
