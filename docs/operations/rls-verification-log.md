---
title: "Row-Level Security Verification Log"
schema_type: common
status: draft
owner: core-maintainer
review_cycle_days: 90
purpose: >-
  Dated record of two-direction row-level security verification runs against the deployed role:
  a tenant cannot read another tenant's row, and a tenant can read its own.
tags:
  - deployment
  - security
  - testing
  - compliance
---

This document is an attestation scaffold. **No run has been recorded yet.** An empty table here
means the control is unattested, not that it is absent by design.

It serves **OPS-003** in the standards manifest. Review cadence: **90 days**, the shortest in this
directory, because tenant isolation is the control most easily changed underneath by an ordinary
schema or policy edit.

**verified_on**: `_(not yet verified)_`

Set this to the date of the most recent recorded run below.

## Why a committed test is not enough on its own

Isolation can fail in two opposite ways that look identical on a checklist. A role that owns the
tables or holds `BYPASSRLS` is not subject to any policy, so isolation reads as configured while
being inert; conversely, a table with row-level security enabled and no policy matching it denies
every read, which is easily mistaken for correct deny-by-default behaviour until a legitimate
read fails in production.

Only a test that asserts **both** directions distinguishes working isolation from either failure,
and only a dated record of that test **having run against the deployed role** distinguishes a
working control from a test somebody wrote. A committed test is necessary; this log is the other
half.

## 1. Verification runs

**Serves OPS-003.** Each row carries all four fields. A row missing any of the four is not a
verification record, and the check fails on the most recent row if it is incomplete or older than
90 days.

| Run date | Deployed role the queries ran as | Cross-tenant read outcome | Same-tenant read outcome |
| --- | --- | --- | --- |
| _(no run recorded)_ | | | |

Field meanings:

- **Run date**: ISO `YYYY-MM-DD`, the date the queries actually executed.
- **Deployed role the queries ran as**: the role name observed from the session that ran the
  queries, not the role a fixture was configured to assume. This must match the role recorded in
  [`service-credentials.md`](service-credentials.md); if it does not, the run proves nothing
  about the deployed path and the discrepancy belongs in the notes below.
- **Cross-tenant read outcome**: the observed result of a read for a row belonging to a different
  tenant. Record what happened (`0 rows returned`, `permission denied`), not a verdict word.
- **Same-tenant read outcome**: the observed result of a read for a row belonging to the querying
  tenant. Record the observed row count.

## 2. Committed test that produces these runs

Record the test that the runs above execute, so a future reviewer can re-run it rather than
reconstruct it.

| Test path | Assertion covered | Executed by | verified_on |
| --- | --- | --- | --- |
| _(no entry recorded)_ | | | |

## 3. Not-applicable verdict

If this repository does not claim row-level security or an equivalent tenant isolation model,
record the verdict here rather than leaving the sections above empty and ambiguous. A bare
"not applicable" is indistinguishable from a control nobody got to, so a verdict is only complete
with a falsifiable precondition and a command that re-tests it.

- Applies today: `_(unfilled: yes / no)_`
- Precondition that makes this check not applicable, stated so it can be proven false:
  `_(unfilled)_`
- Command that re-tests that precondition: `_(unfilled)_`
- Recorded on: `_(unfilled)_`

## Where to run the verification from

Run the two-direction check as the deployed role, against the deployed database, from a hosted
runner or the deployed environment itself. A run from a local development database proves a
property of the local database, and a run through a fixture that sets its own role proves a
property of the fixture. Record in the notes which environment the run was executed from; a run
with no recorded vantage cannot be reproduced.

## Operator step required

This scaffold is not a control until a human completes it.

- [ ] Confirm whether this application claims tenant-scoped isolation. If it does not, complete
      section 3 with a falsifiable precondition and a re-test command, and stop.
- [ ] If it does, run the two-direction verification against the deployed role and record the
      run date, the observed role, and both outcomes in section 1.
- [ ] Record in section 2 the committed test that the run executes.
- [ ] Set the `verified_on` date at the top of this document, and change the front matter
      `status` from `draft` to `published`.
- [ ] Re-run and re-record at least every 90 days, and after any change to a policy, a grant, or
      the schema of a tenant-scoped table.

## Related documentation

- [`service-credentials.md`](service-credentials.md): the connection half of the same control,
  which records the role these queries must run as.
- [`README.md`](README.md) in this directory: the index of attestation artifacts.
