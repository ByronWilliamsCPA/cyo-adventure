---
title: "Restore Drill Log"
schema_type: common
status: draft
owner: core-maintainer
review_cycle_days: 180
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

It serves **OPS-008** in the standards manifest. Review cadence: **180 days**.

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

**Serves OPS-008.** Each row carries all five fields. The check requires at least one entry dated
within 180 days.

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
      production store.
- [ ] Record the drill date, the source backup identifier, the target environment, the elapsed
      restore time, and the verification that confirmed the restored data was usable.
- [ ] Record any finding the drill surfaced, and where the follow-up is tracked.
- [ ] Set the `verified_on` date at the top of this document, and change the front matter
      `status` from `draft` to `published`.
- [ ] Repeat at least every 180 days, and after any change to the backup format, the encryption
      mechanism, the destination, or the restore procedure.

Performing a restore is an operator action against real infrastructure. It is not something a
compliance sweep can carry out on the operator's behalf, which is why this file ships empty and
stays empty until a human runs the drill.

## Related documentation

- [Operator runbook](runbook.md), section 6: the restore procedure to follow during a drill.
- [`backup-inventory.md`](backup-inventory.md): the inventory of stores and their backup posture.
- [`README.md`](README.md) in this directory: the index of attestation artifacts.
