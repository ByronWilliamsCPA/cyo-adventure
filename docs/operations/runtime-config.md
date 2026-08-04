---
title: "Deployed Runtime Configuration Attestation"
schema_type: common
status: draft
owner: core-maintainer
review_cycle_days: 180
purpose: >-
  Records what the deployed process is actually configured with: every runtime-affecting
  setting by name and value class, how each secret is supplied at runtime, and the rate
  limits configured on the authentication endpoints the service exposes.
tags:
  - deployment
  - infrastructure
  - security
  - compliance
---

This document is an attestation scaffold. **No entry below has been filled in yet.** An empty
table here means the control is unattested, not that it is absent by design. Nothing in this
repository can observe what the running process is configured with; only a human with access to
the deployed environment can complete it.

It serves three checks in the `operations` domain of the standards manifest:

| Section | Check | Review cadence |
| --- | --- | --- |
| [1. Runtime settings inventory](#1-runtime-settings-inventory) | OPS-001 | 180 days |
| [2. Secret supply mechanisms](#2-secret-supply-mechanisms) | OPS-010 | reviewed with section 1 |
| [3. Authentication endpoint rate limits](#3-authentication-endpoint-rate-limits) | OPS-011 | reviewed with section 1 |

**verified_on**: `_(not yet verified)_`

Set this to the ISO date (`YYYY-MM-DD`) on which a human last confirmed every section below
against the deployed environment. OPS-001 scores this document stale once that date is more than
180 days old, so re-confirming and re-dating is part of the cadence, not a one-time task.

## How to record a value

**Record the value class, never the value.** A value class describes the shape and origin of a
setting, not its contents. Use this vocabulary:

- `set` / `unset`: whether the deployed process reads a value for this setting at all.
- `secret_manager`: supplied at runtime from a secret manager or platform secret store.
- `platform_env`: set as an environment variable on the hosting platform.
- `file`: read from a file mounted or baked into the runtime environment.
- `literal_default`: the application's own committed default is in force.

Never write a connection string, DSN, host, port, username, API key, token, or any other
credential-shaped value into this document. Names and classes only. `.env.example` is the
canonical description of what each setting means; this document records what the deployed process
does with it.

## 1. Runtime settings inventory

**Serves OPS-001.** Every runtime-affecting setting the deployed process reads, with its value
class in production. A setting the deployed process reads that has no row here leaves this
section incomplete.

The `Setting` and `Consumed by` columns are pre-populated from the secrets and keys inventory in
[the operator runbook](runbook.md), which is the naming source of record. The remaining columns
are for a human to complete against the deployed environment.

### Backend and worker process configuration

| Setting | Consumed by | Value class in production | Supply mechanism | verified_on |
| --- | --- | --- | --- | --- |
| `CYO_ADVENTURE_DATABASE_URL` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CYO_ADVENTURE_REDIS_URL` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `ANTHROPIC_API_KEY` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OPENROUTER_API_KEY` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OLLAMA_BASE_URL` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OLLAMA_AUTH` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OLLAMA_CA_BUNDLE` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `MODAL_BASE_URL` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `MODAL_PROXY_KEY` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `MODAL_PROXY_SECRET` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `GEMINI_API_KEY` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `R2_ACCOUNT_ID` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `R2_ACCESS_KEY_ID` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `R2_SECRET_ACCESS_KEY` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `R2_BUCKET` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `R2_PUBLIC_BASE_URL` | worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OPENAI_API_KEY` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `PERSPECTIVE_API_KEY` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CYO_ADVENTURE_REVIEW_PROVIDER` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OIDC_ISSUER` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OIDC_JWKS_URL` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OIDC_AUDIENCE` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OIDC_ALLOWED_ALGS` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CHILD_SESSION_SECRET` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CHILD_SESSION_TTL_SECONDS` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `DEVICE_GRANT_SECRET` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `DEVICE_GRANT_TTL_SECONDS` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `SENTRY_DSN` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `FORWARDED_ALLOW_IPS` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |

### Feature flags and connection targets

Any deployed feature flag, provider selector, or connection target not covered above belongs
here, one row each.

| Setting | Consumed by | Value class in production | Supply mechanism | verified_on |
| --- | --- | --- | --- | --- |
| _(no entry recorded)_ | | | | |

### Frontend build-time configuration

Browser-side `VITE_*` settings are compiled into the published bundle and are not process
secrets. Record them here so the deployed bundle's configuration is attested alongside the
backend's.

| Setting | Value class in the deployed bundle | Supply mechanism | verified_on |
| --- | --- | --- | --- |
| _(no entry recorded)_ | | | |

## 2. Secret supply mechanisms

**Serves OPS-010.** For each secret the deployed process reads, the mechanism that supplies it at
runtime is recorded in the `Supply mechanism` column of section 1. This section records the
second half of the check: that no deployment artifact in this repository carries a credential
into the built image or the running container.

An operator completes the following review and dates it. Each line stays unchecked until a human
has looked at the artifact and confirmed it.

- [ ] `Dockerfile`: reviewed, and it does not `COPY` a populated `.env` file or embed a literal
      credential in a layer, build argument, or default environment variable.
- [ ] `docker-compose.yml` and `docker-compose.prod.yml`: reviewed, and no service definition
      carries an inline credential value.
- [ ] GitHub Actions workflows: reviewed, and every credential reaches a job through
      `secrets.*` or an environment secret rather than a committed literal.
- [ ] Any chart, manifest, or platform configuration used to deploy this service: reviewed on
      the same terms.
- [ ] Every secret named in section 1 resolves to a supply mechanism at runtime, and that
      mechanism is recorded in its row.

Reviewed on: `_(unfilled)_` by `_(unfilled)_`.

## 3. Authentication endpoint rate limits

**Serves OPS-011.** This check is scoped to the authentication endpoints the service actually
exposes, drawn from four candidates. An endpoint the service does not expose is not a finding,
but the exclusion has to be recorded rather than assumed, which is why every candidate gets a row
and an explicit exposed yes/no.

Record the configured limit as requests per window plus the key the limit is scoped to (per IP,
per account identifier, per session). Where the limit is enforced by the managed auth provider
rather than by application code, name the provider setting in `Where enforced` and note that
OPS-012 governs whether that setting is versioned and applied by CI.

| Endpoint class | Exposed by this service | Requests per window | Window | Scope key | Where enforced | verified_on |
| --- | --- | --- | --- | --- | --- | --- |
| Login | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Token refresh | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Password reset request | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| MFA verification | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |

If all four rows record `no` under `Exposed by this service`, OPS-011 is not applicable. Record
the precondition and a command that re-tests it, so the verdict un-asserts itself if an
authentication surface is added later:

- Precondition making OPS-011 not applicable: `_(unfilled)_`
- Command that re-tests the precondition: `_(unfilled)_`

## Where to measure from

A limit configured in a settings file is a claim about the deployed edge, and a claim about a
trust boundary has to be measured from outside that boundary. Confirm a rate limit by observing
the response an external client receives from the deployed hostname, from a hosted runner or
another network, not from a developer machine inside the same network as the service and not by
reading the configuration back out of the process that sets it. Record in the row where the
observation was made from; a measurement with no recorded vantage cannot be reproduced on the
next review.

## Operator step required

This scaffold is not a control until a human completes it.

- [ ] Enumerate every runtime-affecting setting the deployed process reads, add any missing row
      to section 1, and record each setting's value class in production. Record classes, never
      values.
- [ ] Record, for every secret in section 1, the mechanism that supplies it at runtime, and
      complete the artifact review in section 2.
- [ ] Record which of the four authentication endpoint classes this service exposes, and for
      each exposed one, the configured limit and the scope key, measured from outside the
      deployed boundary.
- [ ] Set the `verified_on` date at the top of this document, and change the front matter
      `status` from `draft` to `published`.

## Related documentation

- [Operator runbook](runbook.md), sections 1 and 8: service topology, and the names-only secrets
  and keys inventory this document's setting names are drawn from.
- [`README.md`](README.md) in this directory: the index of attestation artifacts and their
  review cadences.
