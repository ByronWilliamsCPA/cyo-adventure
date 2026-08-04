---
title: "Service Credential Attestation"
schema_type: common
status: draft
owner: core-maintainer
review_cycle_days: 180
purpose: >-
  Records, for each data store, the identity each deployed process connects as, whether that is a
  runtime process or operator automation, the privileges that identity holds, and the explicit
  confirmations that it is not the table owner, not a superuser, and does not hold BYPASSRLS.
tags:
  - deployment
  - infrastructure
  - security
  - compliance
---

This document is an attestation scaffold. **No entry below has been filled in yet.** An empty
table here means the control is unattested, not that it is absent by design.

It serves **OPS-002** in the standards manifest, which asks for the least-privilege half of the
service credential story: not what the repository configures, but what identity the deployed
process actually presents to each data store. Review cadence: **180 days**.

**verified_on**: `_(not yet verified)_`

Set this to the ISO date (`YYYY-MM-DD`) on which a human last confirmed every row below against
the deployed environment. The check scores this document stale once that date is more than 180
days old.

## What may be written here

Role names and boolean attributes only. Never write a connection string, DSN, host, port,
password, token, or key into this document, in a table cell, an example, or a pasted command
output. The three confirmations this check asks for are booleans about a named role, and a
boolean carries no secret.

## 1. Relational data store roles

**Serves OPS-002.** One row per **connecting process**, not per data store. A single store reached
by two processes under two different roles is two rows, because the whole point of the check is
which identity a given process presents.

| Data store | Connecting process | Role that process connects as | Privileges granted to that role | Not the table owner | Not a superuser | Does not hold BYPASSRLS | verified_on |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Supabase Postgres (primary application database) | backend (API) | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Supabase Postgres (primary application database) | worker (RQ) | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |

Both rows are for the same store on purpose. [ADR-021](../planning/adr/adr-021-service-account-rls-and-worker-deployment.md)
splits the application's database credential into two roles with different privileges, `cyo_api`
for the request path and `cyo_worker` for the queue path, and an environment is only partly cut
over until both rows are filled. Recording one row for "the application" would hide exactly the
difference the split exists to create: a single row cannot show that one process was migrated and
the other still connects on the shared credential, which is the state a half-finished cutover
leaves behind. Section 11 of the [operator runbook](runbook.md) is the per-environment procedure.

The three confirmation columns are deliberately separate and deliberately explicit. A role that
owns the tables, or that holds `SUPERUSER` or `BYPASSRLS`, is not constrained by row-level
security regardless of what policies exist on those tables, so recording "row-level security is
enabled" without recording these three booleans records only half of the control. See
[`rls-verification-log.md`](rls-verification-log.md) for the policy half.

## 2. Non-relational store identities

**Serves OPS-002.** Redis and object storage do not have SQL roles, but they do have an identity
whose scope determines what a compromised process can reach. Record the credential's name and its
granted scope, never its value.

`Reached by` matters here because not every store in this table is reached by the deployed
application. The database-backup bucket is written by the nightly backup workflow under its own
`R2_BACKUP_*` credentials; it belongs in a least-privilege inventory, but attributing it to the
running service would misstate which identity holds it.

| Store | Reached by | Credential identity name | Granted scope | Read-only where possible | verified_on |
| --- | --- | --- | --- | --- | --- |
| Redis (queue and rate-limiter state) | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Cloudflare R2, cover-image bucket | backend, worker | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Cloudflare R2, database-backup bucket | `supabase-backup.yml` workflow | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |

Add a row when a new store is introduced. A store the deployed application or its operator
automation reaches that has no row here leaves this document incomplete.

## How to determine the role, and where to run the query

The role has to be read **from the deployed session**, not from a local test fixture. A fixture
that sets a role before asserting on it cannot observe what the deployed process connects as; it
can only report back the role it was told to use. A measurement taken from inside the boundary
being described is not evidence about that boundary.

Run a read-only introspection query in the deployed environment, against the same connection the
application uses:

```sql
-- Read-only. Returns the connected role's name and its privilege attributes.
select current_user, session_user;

select rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
from pg_roles
where rolname = current_user;

-- Ownership of the application's tables, to confirm the connected role is not the owner.
select tablename, tableowner
from pg_tables
where schemaname = 'public'
order by tablename;
```

Transcribe the role name and the boolean results into the table above. Do not paste raw session
output into this document; it can carry host and connection detail that does not belong in a
public repository.

## Operator step required

This scaffold is not a control until a human completes it.

- [ ] Record the role each connecting process presents, for each relational data store, read from
      that process's own deployed session rather than from a test fixture. The backend row and the
      worker row are separate observations; reading one and copying it into the other defeats the
      purpose of the ADR-021 split.
- [ ] Record the privileges granted to that role.
- [ ] Confirm and record explicitly that the role is not the table owner, is not a superuser, and
      does not hold BYPASSRLS.
- [ ] Record the credential identity name and granted scope for each non-relational store.
- [ ] Set the `verified_on` date at the top of this document, and change the front matter
      `status` from `draft` to `published`.

Changing a role, a grant, or a policy is an operator decision with real consequences and is out
of scope for a compliance sweep. This document records what is; changing what is belongs in a
reviewed change of its own.

## Related documentation

- [`rls-verification-log.md`](rls-verification-log.md): the two-direction proof that row-level
  security is effective for the role recorded here.
- [Operator runbook](runbook.md), section 11: the service-account cutover procedure.
- [ADR-021](../planning/adr/adr-021-service-account-rls-and-worker-deployment.md): the decision
  that split this credential into `cyo_api` and `cyo_worker`.
- [`../security/assurance-register.md`](../security/assurance-register.md), row **O-77**: the same
  control stated as an assertion, that the connection's identity is "asserted from the deployed
  session, not assumed from a fixture." This document is the evidence O-77 is asserted from; a
  change to one without the other leaves the two disagreeing.
- [`README.md`](README.md) in this directory: the index of attestation artifacts.
