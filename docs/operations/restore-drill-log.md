---
title: "Restore Drill Log"
schema_type: common
status: draft
owner: core-maintainer
review_cycle_days: 90
purpose: >-
  Dated record of restores actually performed from a real backup, with the source backup, the
  target environment, the elapsed time, and the verification that confirmed the restored data was
  usable.
tags:
  - deployment
  - infrastructure
  - compliance
---

This document is an attestation scaffold. **No drill has been recorded yet.** An empty table here
means the control is unattested, not that it is absent by design.

It serves **OPS-008** in the standards manifest, whose `max_evidence_age_days` is 180.

**The operative cadence here is 90 days, not 180.** Row **O-33** of the
[assurance register](../security/assurance-register.md) covers the same control and fails on "no
restore record exists within the last quarter", which is the tighter of the two schedules, and the
tighter one governs (see [`README.md`](README.md)). Taking the looser figure would let a 150-day-old
drill satisfy OPS-008 and fail O-33 at the same time, in the same repository, with the two files
reporting opposite verdicts about one drill. Every deadline below is therefore stated as 90 days;
meeting it satisfies OPS-008 as a side effect.

O-33 adds one requirement the manifest does not state: the restore must have targeted a scratch
environment separate from production. The `Target environment` column below is where that is
recorded, so a drill run against production is a recorded failure rather than an unrecorded one.

**verified_on**: `_(not yet verified)_`

Set this to the date of the most recent recorded drill below.

## Why this log is separate from the inventory

A backup that has never been restored is unproven, and the ways it fails are not visible from the
backup side: a dump written in a format the restore path cannot read, an encryption key nobody
still holds, an ordering dependency between schema and data, a restore that runs but produces a
database missing the rows that mattered. Every one of those looks like a healthy backup right up
until the moment it is needed.

This log is deliberately kept separate from [`backup-inventory.md`](backup-inventory.md) so that a
configured backup cannot satisfy the drill requirement by proximity. The inventory records intent;
this file records the proof.

## 1. Drill records

**Serves OPS-008 and O-33.** Each row carries all five fields. At least one entry must be dated
within the last 90 days, per the reconciliation above.

| Drill date | Source backup identifier | Target environment | Elapsed restore time | Verification that confirmed the restored data was usable |
| --- | --- | --- | --- | --- |
| _(no drill recorded)_ | | | | |

Field meanings:

- **Drill date**: ISO `YYYY-MM-DD`, the date the restore actually ran.
- **Source backup identifier**: enough to identify which backup was used and re-find it, for
  example the tier and date prefix under which it was stored. An identifier, not an address; no
  bucket URL, endpoint, or credentialed path.
- **Target environment**: the environment the restore was written into. A drill restores into a
  scratch or staging target, never into a live production store.
- **Elapsed restore time**: wall-clock time from starting the restore to the target being usable.
  This number is what turns a recovery time objective from an aspiration into a measurement.
- **Verification that confirmed the restored data was usable**: the specific check performed and
  its result. "Row counts on `family`, `profile`, `storybook`, `storybook_version` matched the
  source within expected drift" is a verification. "Restore completed without errors" is not; a
  restore can complete cleanly and produce an unusable database.

## 2. Findings from each drill

A drill that surfaces nothing is unusual. Record what the drill exposed, so the next one starts
from a better procedure than the last.

| Drill date | Finding | Action taken or tracked | Where tracked |
| --- | --- | --- | --- |
| _(no entry recorded)_ | | | |

## Operator step required

This scaffold is not a control until a human completes it.

- [ ] Perform a restore from a real backup into a scratch or staging target, never into a live
      production store. O-33 fails on a restore that did not target an environment separate from
      production, so the target is part of the evidence, not a detail of how the drill was run.
- [ ] Record the drill date, the source backup identifier, the target environment, the elapsed
      restore time, and the verification that confirmed the restored data was usable.
- [ ] Record any finding the drill surfaced, and where the follow-up is tracked.
- [ ] Set the `verified_on` date at the top of this document, and change the front matter
      `status` from `draft` to `published`.
- [ ] Update O-33's `Last verified` field in the assurance register to the same date. The drill
      record here is the measurement; the register restates it. Updating one and not the other
      leaves the two disagreeing about whether the control holds.
- [ ] Repeat at least every 90 days, and after any change to the backup format, the encryption
      mechanism, the destination, or the restore procedure.

Performing a restore is an operator action against real infrastructure. It is not something a
compliance sweep can carry out on the operator's behalf, which is why this file ships empty and
stays empty until a human runs the drill.

## Related documentation

- [Operator runbook](runbook.md), section 6: the restore procedure to follow during a drill.
- [`backup-inventory.md`](backup-inventory.md): the inventory of stores and their backup posture.
- [`../security/assurance-register.md`](../security/assurance-register.md), row **O-33**: the same
  control stated as an assertion, on a quarterly trigger. This log is the evidence O-33 is asserted
  from, and the reconciliation of the two cadences is at the top of this document. Row **O-106**
  constrains the restore path further: a restoration must not resurrect a deleted account or
  republish withdrawn content without reconciling against the deletion, revocation, and
  publication records. A drill is the natural place to exercise that, so record it under
  section 2 when a drill covers it.
- [`README.md`](README.md) in this directory: the index of attestation artifacts.
