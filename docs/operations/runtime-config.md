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

One exclusion is deliberate and stated so it is not mistaken for an oversight: the runbook's
inventory also lists CI-only secrets under its **GitHub Actions secrets** heading
(`RELEASE_TOKEN`, `CODECOV_TOKEN`, `SONAR_TOKEN`, `INFISICAL_CLIENT_ID`,
`INFISICAL_CLIENT_SECRET`, the `E2E_PROD_*` credentials). None of them is read by the deployed
process, so none gets a row here. The filter is "read by the running service", not "is a secret".

The `Setting` and `Consumed by` columns are seeded from the secrets and keys inventory in
[the operator runbook](runbook.md), which is the naming source of record for secrets. The
remaining columns are for a human to complete against the deployed environment.

**That seed is a starting point, not the inventory.** The runbook section it comes from indexes
secrets, while this check asks for every runtime-affecting setting. The authoritative enumeration
is the `Settings` model in `src/cyo_adventure/core/config.py`, which sets
`env_prefix="cyo_adventure_"` and therefore binds an environment variable for every field it
declares, not only the fields carrying an explicit alias. At the time this scaffold was written
that model declared 70 fields and the tables below carry rows for 30 of them, so completing the
enumeration is the first operator step rather than a formality. Settings absent from the seed are
mostly timeouts, model selectors, and sizing knobs; the security-relevant ones found during review
have been added to the feature-flag table below.

### Backend and worker process configuration

| Setting | Consumed by | Value class in production | Supply mechanism | verified_on |
| --- | --- | --- | --- | --- |
| `CYO_ADVENTURE_DATABASE_URL` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CYO_ADVENTURE_WORKER_DATABASE_URL` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CYO_ADVENTURE_REDIS_URL` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `ANTHROPIC_API_KEY` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OPENROUTER_API_KEY` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OLLAMA_BASE_URL` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OLLAMA_AUTH` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `OLLAMA_CA_BUNDLE` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `MODAL_BASE_URL` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `MODAL_PROXY_KEY` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `MODAL_PROXY_SECRET` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `GEMINI_API_KEY` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `R2_ACCOUNT_ID` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `R2_ACCESS_KEY_ID` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `R2_SECRET_ACCESS_KEY` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `R2_BUCKET` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `R2_PUBLIC_BASE_URL` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
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

Two `Consumed by` entries above are easy to get wrong in the direction that understates exposure,
so both are recorded here with the code path that settles them:

- **The generation, cover-art, and object-storage credentials are read by the backend too**, not
  by the worker alone. `POST /v1/admin/storybook-versions/{id}/remoderate` builds a generation
  provider in-request (`api/remoderate.py`, via `generation/provider.py`), the node-edit rescreen
  path builds a review provider the same way (`api/node_edit.py`), and three routers presign cover
  URLs through `covers/storage.py` (`api/covers.py`, `api/library.py`, `api/recommendations.py`).
  An operator scoping container-level credential exposure needs this: those keys are resident in
  the backend container's memory, not only the worker's.
- **`CYO_ADVENTURE_WORKER_DATABASE_URL` is read by both processes**, because
  `core/database.py` constructs the API engine and the worker engine at import time in every
  process. The API process therefore holds the `cyo_worker` DSN without ever using it. The code
  carries this as a standing `#ASSUME: security` note, and the mitigation is configuration rather
  than code: the API container leaves this variable unset so it falls back to the API DSN. Whether
  that mitigation is actually in force in each environment is exactly what this row records.

### Feature flags and connection targets

Any deployed feature flag, provider selector, or connection target not covered above belongs
here, one row each. The rows below are the security-relevant settings found during review; each
one's `Consumed by` was confirmed against its call sites, and the enumeration is still incomplete
by the count given above.

| Setting | Consumed by | Value class in production | Supply mechanism | verified_on |
| --- | --- | --- | --- | --- |
| `ENVIRONMENT` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CYO_ADVENTURE_ALLOWED_HOSTS` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CYO_ADVENTURE_RATE_LIMIT_BACKEND` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CYO_ADVENTURE_GENERATION_PROVIDER` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `MODAL_MODEL` | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| `CYO_ADVENTURE_SENTRY_TRACES_SAMPLE_RATE` | backend | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |

`ENVIRONMENT` earns its row because several authorization and publishing behaviours branch on it
(`api/deps.py`, `publishing/service.py`, `moderation/pipeline.py`), so its deployed value is a
security-relevant fact rather than a label. `CYO_ADVENTURE_ALLOW_MOCK_REVIEW` deliberately has no
row: the field is declared in `config.py` but read nowhere in the package, so setting it changes
nothing today. Recording it as a live setting would assert an effect the code does not have.

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

**Record that a limit is in force, not what the limit is.** This repository is public, and an
exact requests-per-window figure is worth more to someone tuning an attack against these endpoints
than to anyone maintaining them, which the disclosure rule in [`README.md`](README.md) forbids
publishing. Record instead that a limit exists, the key it is scoped to (per IP, per account
identifier, per session), where it is enforced, and the dated result of confirming it from
outside. The numeric value stays where it is configured; what this table attests is that somebody
observed the limit take effect. [`public-write-paths.md`](public-write-paths.md) records its
controls on the same terms.

Where the limit is enforced by the managed auth provider rather than by application code, name the
provider setting in `Where enforced` and note that OPS-012 governs whether that setting is
versioned and applied by CI.

| Endpoint class | Exposed by this service | Limit in force | Scope key | Where enforced | Confirmed from | verified_on |
| --- | --- | --- | --- | --- | --- | --- |
| Login | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Token refresh | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Password reset request | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| MFA verification | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |

**Limit in force** is `yes` or `no`, the observed outcome of exceeding the limit from outside the
boundary, not a number. **Confirmed from** is the vantage the observation was made from.

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

- [ ] Reconcile section 1 against the `Settings` model in `src/cyo_adventure/core/config.py`,
      remembering that `env_prefix="cyo_adventure_"` binds a variable for every declared field and
      not only for the fields carrying an explicit alias. The seed covers 30 of 70 fields; the
      remainder need a row or a recorded reason for not having one.
- [ ] Enumerate every runtime-affecting setting the deployed process reads, add any missing row
      to section 1, and record each setting's value class in production. Record classes, never
      values.
- [ ] Record, for every secret in section 1, the mechanism that supplies it at runtime, and
      complete the artifact review in section 2.
- [ ] Record which of the four authentication endpoint classes this service exposes, and for
      each exposed one, that a limit is in force and the key it is scoped to, observed from
      outside the deployed boundary. Record the outcome, never the threshold.
- [ ] Set the `verified_on` date at the top of this document, and change the front matter
      `status` from `draft` to `published`.

## Related documentation

- [Operator runbook](runbook.md), sections 1 and 8: service topology, and the names-only secrets
  and keys inventory this document's setting names are drawn from.
- [`../security/assurance-register.md`](../security/assurance-register.md), rows **O-85** and
  **O-86**: the same subject matter stated as assertions rather than as evidence. O-85 covers
  control-plane settings held in vendor dashboards, and O-86 names `ENVIRONMENT`'s effect on rate
  limiting as a verification target, which is why that setting carries a row above. Sections 1 and
  3 of this document are the evidence those rows are asserted from; keep the two in step when
  either changes.
- [`README.md`](README.md) in this directory: the index of attestation artifacts and their
  review cadences.
