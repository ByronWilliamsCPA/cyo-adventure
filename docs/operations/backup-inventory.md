---
title: "Backup Inventory"
schema_type: common
status: draft
owner: core-maintainer
review_cycle_days: 365
purpose: >-
  Inventory of every stateful store the application depends on, with each store's backup
  schedule, retention window, destination, and whether that destination sits in a different
  failure domain than the primary.
tags:
  - deployment
  - infrastructure
  - compliance
---

This document is an attestation scaffold. **No row below has been filled in yet.** An empty table
here means the control is unattested, not that it is absent by design.

It serves **OPS-007** in the standards manifest. Review cadence: **365 days**.

**verified_on**: `_(not yet verified)_`

Set this to the ISO date (`YYYY-MM-DD`) on which a human last confirmed every row below against
the deployed environment.

## Scope rule

Every stateful store the application depends on gets a row, whether or not it is currently in
scope for backup. The inventory is the artifact that makes a store's backup posture reviewable;
a store that is running in production but missing from this table is invisible to the review,
which is the specific failure this check exists to prevent. Add a row the same day a new stateful
store is introduced.

## 1. Stateful store inventory

**Serves OPS-007.** One row per store.

| Store | Backup schedule | Retention window | Destination | Different failure domain than primary | verified_on |
| --- | --- | --- | --- | --- | --- |
| Supabase Postgres (primary application database) | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Redis (queue and rate-limiter state) | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Cloudflare R2, cover-image bucket | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |

Field meanings:

- **Backup schedule**: how often a backup is taken, and by what (a named workflow, a platform
  feature, a manual procedure). "Daily at 08:00 UTC by `<workflow name>`" is a schedule;
  "regularly" is not.
- **Retention window**: how long a backup survives before it is expired, per tier if tiered.
- **Destination**: where the backup lands, named as a store, never as a URL, bucket address, or
  credentialed endpoint.
- **Different failure domain than primary**: `yes` or `no`, plus one clause naming the shared
  dependency if the answer is `no`. A backup that shares an account, a region, or a provider with
  the primary shares that dependency's failure.

Where a store deliberately carries no backup, `Backup schedule` reads `none` and the decision goes
in the table below, so a deliberate choice is distinguishable from an unreviewed one.
Reconstructible or ephemeral state is a legitimate answer; recording nothing is not, and a row
whose schedule is `none` with no matching entry here is an unreviewed store rather than an
exempt one.

| Store | Reason no backup is taken | Decided on | Decided by | What would change this |
| --- | --- | --- | --- | --- |
| _(no entry recorded)_ | | | | |

**What would change this** is the field that keeps the exemption falsifiable. "Holds only queue
and rate-limiter state, all of it reconstructible" stops being true the day something durable is
written to that store, so the exemption should name the condition that retires it rather than
standing indefinitely on the reasoning that was true when it was written.

## 2. Backup integrity properties

Record the properties that determine whether a stored backup is usable, once per destination.

| Destination | Encrypted at rest | Key held outside this repository | Restore path documented | verified_on |
| --- | --- | --- | --- | --- |
| _(no entry recorded)_ | | | | |

Never record a key, a key location that functions as an address, or any credential needed to
reach a destination. Booleans and the name of the mechanism only.

## Operator step required

This scaffold is not a control until a human completes it.

- [ ] Confirm the store list in section 1 is complete against the deployed environment, adding a
      row for any stateful store not listed.
- [ ] Record, for each store, its backup schedule, retention window, destination, and whether the
      destination sits in a different failure domain than the primary.
- [ ] Record the reasoning and decision date for any store deliberately carrying no backup.
- [ ] Complete section 2 for each destination.
- [ ] Set the `verified_on` date at the top of this document, and change the front matter
      `status` from `draft` to `published`.

An inventory records intent. [`restore-drill-log.md`](restore-drill-log.md) is the artifact that
records whether the intent works, and the two are deliberately kept separate so that a backup
which has never been restored cannot pass by proximity to one that has.

## Related documentation

- [Operator runbook](runbook.md), section 6: backup and restore procedures as they exist in this
  repository.
- [`restore-drill-log.md`](restore-drill-log.md): the dated record of restores actually performed.
- [`../security/assurance-register.md`](../security/assurance-register.md), row **O-33**: the
  assertion that backups are "demonstrably restorable, not merely taken." This inventory is the
  "taken" half and cannot satisfy O-33 on its own; the drill log holds the date O-33 is asserted
  from. O-33 runs on a quarterly trigger while this inventory's cadence is 365 days, which is not
  a conflict: the two documents attest different things on different schedules.
- [`README.md`](README.md) in this directory: the index of attestation artifacts.
