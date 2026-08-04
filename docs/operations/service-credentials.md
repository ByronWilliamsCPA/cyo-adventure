---
title: "Service Credential Attestation"
schema_type: common
status: draft
owner: core-maintainer
review_cycle_days: 180
purpose: >-
  Records, for each data store, the role the deployed application connects as, the privileges
  that role holds, and the explicit confirmations that it is not the table owner, not a
  superuser, and does not hold BYPASSRLS.
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

**Serves OPS-002.** One row per relational data store the deployed application connects to.

| Data store | Role the deployed application connects as | Privileges granted to that role | Not the table owner | Not a superuser | Does not hold BYPASSRLS | verified_on |
| --- | --- | --- | --- | --- | --- | --- |
| Supabase Postgres (primary application database) | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |

The three confirmation columns are deliberately separate and deliberately explicit. A role that
owns the tables, or that holds `SUPERUSER` or `BYPASSRLS`, is not constrained by row-level
security regardless of what policies exist on those tables, so recording "row-level security is
enabled" without recording these three booleans records only half of the control. See
[`rls-verification-log.md`](rls-verification-log.md) for the policy half.

## 2. Non-relational store identities

**Serves OPS-002.** Redis and object storage do not have SQL roles, but they do have an identity
whose scope determines what a compromised process can reach. Record the credential's name and its
granted scope, never its value.

| Store | Credential identity name | Granted scope | Read-only where possible | verified_on |
| --- | --- | --- | --- | --- |
| Redis (queue and rate-limiter state) | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Cloudflare R2, cover-image bucket | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Cloudflare R2, database-backup bucket | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |

Add a row when a new store is introduced. A store the deployed application reaches that has no
row here leaves this document incomplete.

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

- [ ] Record the role the deployed application connects as, for each relational data store, read
      from the deployed session rather than from a test fixture.
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
- [`README.md`](README.md) in this directory: the index of attestation artifacts.
