---
title: "Operations Attestation Artifacts"
schema_type: common
status: published
owner: core-maintainer
purpose: >-
  Index of the operational-posture attestation artifacts in this directory: what each one
  records, which standards-manifest check it serves, and how often it has to be re-confirmed.
tags:
  - deployment
  - infrastructure
  - compliance
---

This directory holds the operator-facing documentation for running CYO Adventure, plus a set of
**attestation artifacts**: dated records of things that can only be observed in a deployed
environment.

They exist because a repository cannot check itself on these points. Static analysis can read
what the code configures; it cannot read what the running process is configured with, what role a
live connection presents, whether a backup has ever been restored, or whether an alert reached a
human. Each artifact below is the durable record a person leaves behind after checking one of
those things, so that the next reviewer inherits evidence instead of starting over.

**An artifact that is still empty means the control is unattested, not that it is absent by
design.** The two are different states with different remedies, and collapsing them is exactly
what these files exist to prevent: an unattested control is one nobody has recorded yet, while a
control that genuinely does not apply is recorded as such, with the reason and a way to re-test
that reason later. Every scaffold below carries an explicit, unchecked operator step; until that
step is completed and dated, the document is a placeholder and reads as one.

## The artifacts

| Artifact | Serves | Review cadence | What it records |
| --- | --- | --- | --- |
| [`runtime-config.md`](runtime-config.md) | OPS-001, OPS-010, OPS-011 | 180 days | Every runtime-affecting setting the deployed process reads, by name and value class; the mechanism supplying each secret at runtime; and the rate limits configured on the authentication endpoints the service exposes. |
| [`service-credentials.md`](service-credentials.md) | OPS-002 | 180 days | The role the deployed application connects to each data store as, its privileges, and the explicit confirmations that it is not the table owner, not a superuser, and does not hold BYPASSRLS. |
| [`rls-verification-log.md`](rls-verification-log.md) | OPS-003 | 90 days | Dated two-direction tenant isolation runs against the deployed role: the cross-tenant read outcome and the same-tenant read outcome. |
| [`alert-test-fire-log.md`](alert-test-fire-log.md) | OPS-006 | 180 days | Each deliberate firing of a security alert rule, and the delivery result observed at the destination channel. |
| [`backup-inventory.md`](backup-inventory.md) | OPS-007 | 365 days | Every stateful store the application depends on, with its backup schedule, retention window, destination, and whether that destination sits in a different failure domain than the primary. |
| [`restore-drill-log.md`](restore-drill-log.md) | OPS-008 | 180 days | Restores actually performed from a real backup: source backup, target environment, elapsed time, and the verification that confirmed the restored data was usable. |
| [`public-write-paths.md`](public-write-paths.md) | OPS-009 | on public-surface change | Every unauthenticated endpoint that creates state, mapped to the anti-automation control protecting it and the place that control is enforced. |

Review cadences are drawn from each check's `max_evidence_age_days` in the standards manifest. A
document whose `verified_on` date is older than its cadence fails its check on staleness, which
is a different result from the document being missing: the control was recorded once and the
record has aged out. Re-confirming and re-dating is part of owning the control, not a separate
project.

## Two rules that apply to all of them

**Record artifacts, not intentions.** Each check names a durable thing: a dated row, a named role,
a measured elapsed time. Prose asserting that a control is in place does not satisfy any of these
checks, however confident it is, because the next reviewer has no way to tell an assertion that
was checked from one that was assumed.

**Record where the measurement was taken from.** A control that describes behaviour at a trust
boundary has to be confirmed from outside that boundary. A rate limit observed by reading the
configuration that sets it, a database role reported by a fixture that assigns that role, an alert
confirmed by watching the sender rather than the destination: each of these produces a confident
result that describes the wrong side of the thing being checked. Where the only available vantage
is inside the boundary, record that as unverified with the vantage named, rather than recording
the inside measurement as a result.

## What may not be written in these files

This repository is public. These documents carry names, classes, and booleans only:

- No connection string, DSN, host, port, credential, key, token, or webhook address, in a table
  cell, an example, or pasted command output.
- No threshold, exemption, or bypass condition that is more useful to someone probing the service
  than to someone maintaining it.
- No narrative describing where a control is incomplete. Track incomplete items by issue ID and
  reference the ID, which keeps the item reviewable without publishing its shape.

## Controls provided by another plane

Several of these controls can be provided by something outside this repository: a managed
platform, a hosting provider, an edge service. A control provided elsewhere is inherited, not
absent, but it only counts as recorded if it names which plane provides it, whether it applies to
production today, and the event that requires re-validating it. That register already exists at
[`../security/control-inheritance.md`](../security/control-inheritance.md); record an inherited
control there and reference it from the relevant artifact here, rather than describing it twice.

## Other documents in this directory

- [Operator runbook](runbook.md): day-to-day operations, health checks, incident diagnosis,
  secrets and keys inventory, and the content kill switch.
- [Authoring guide](authoring-guide.md): the guardian- and admin-facing description of how a
  story reaches a child's shelf.
