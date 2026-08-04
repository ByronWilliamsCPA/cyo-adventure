---
title: "Security Alert Test-Fire Log"
schema_type: common
status: draft
owner: core-maintainer
review_cycle_days: 180
purpose: >-
  Dated record of security alert rules being deliberately fired and the delivery confirmed at the
  destination channel that is supposed to receive them.
tags:
  - deployment
  - monitoring
  - security
  - compliance
---

This document is an attestation scaffold. **No test-fire has been recorded yet.** An empty table
here means the control is unattested, not that it is absent by design.

It serves **OPS-006** in the standards manifest. Review cadence: **180 days**.

**There are no alert rules to record yet, and that is a known state rather than an open question.**
Section 6 of the [security event catalog](security-events.md) states that no alert rules ship in
this repository today: the events are shaped to be alertable, but wiring them to a notification
channel is a deployment-side task in `homelab-infra` that has not been done. The gap is tracked as
[`UW-D28`](../planning/unscheduled-work-register.md) against issue
[#557](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/557).

This changes what completing this document takes. OPS-006 cannot be satisfied by finding an
existing rule and writing it down; the rules have to be built first, then fired, then observed.
Read section 6 of the catalog before starting, and treat the "Alert on" guidance in its section 2
as the specification for the rules to build, not as a description of rules that exist.

**verified_on**: `_(not yet verified)_`

Set this to the date of the most recent recorded test-fire below.

## What this log proves that a rule definition does not

An alert rule is a claim that a human will find out. The claim has three joints, and each one
fails independently: the rule can stop matching, the delivery path can break, and the destination
can stop being watched. A committed rule file demonstrates only the first joint, and only at the
moment it was written.

The delivery result therefore has to be **observed at the destination**. Seeing the application
emit the alert, or seeing a log line saying a notifier was called, confirms the sending side of a
path whose failure mode is on the receiving side. Record what arrived where somebody would
actually see it.

## 1. Alert rules in scope

**Serves OPS-006.** The check requires committed rule definitions covering at least two event
classes. Record each rule, where its definition is committed, and the destination it routes to.

| Rule identity | Definition path (committed) | Event class covered | Destination channel | Who watches that destination |
| --- | --- | --- | --- | --- |
| _(no entry recorded)_ | | | | |

Event classes that must each be covered by at least one rule, with the event the application
already emits for each:

| Required event class | Event emitted today | Where it is specified |
| --- | --- | --- |
| Authentication-failure spike | `security_auth_failed` | [`security-events.md`](security-events.md), section 2 |
| Authorization-denial spike | `security_authz_denied` | [`security-events.md`](security-events.md), section 2 |

Both events exist and carry structured fields today; only the rules over them are missing. A third
rule is worth building at the same time even though OPS-006 does not require it:
`security_event_write_failed` has no alert, and the catalog notes that without one, the fail-open
write path makes a silent audit gap look identical to an absence of attacks.

A rule configured only in a vendor console is not reviewable by anyone reading this repository,
and does not satisfy the check on its own. Where a console is the only place a rule can live,
OPS-012 governs whether that setting is versioned and applied by CI.

## 2. Test-fire records

**Serves OPS-006.** Each row carries all four fields. A row missing any of the four is not a
test-fire record. The most recent row for a given rule must fall within 180 days.

| Test-fire timestamp (UTC) | Alert rule identity | Destination channel delivered to | Delivery result observed at the destination |
| --- | --- | --- | --- |
| _(no test-fire recorded)_ | | | |

Field meanings:

- **Test-fire timestamp (UTC)**: ISO `YYYY-MM-DDTHH:MMZ`, the moment the rule was deliberately
  triggered.
- **Alert rule identity**: the rule name exactly as it appears in section 1.
- **Destination channel delivered to**: the channel the notification was expected to reach, named
  the same way it is named in section 1. Record the channel name only, never a webhook URL, token,
  or any other address that carries a credential.
- **Delivery result observed at the destination**: what a human saw at the destination, and how
  long after the trigger. `Notification visible in the destination inbox, 40 seconds after
  trigger, acknowledged by <name>` is a result. `Alert sent` is not; it describes the sending
  side.

## Where to observe from

Confirm delivery from the destination, as the person who would be on the receiving end during a
real incident. If the destination is a GitHub issue label, confirm the issue exists and that
notification on that label is actually enabled for a human who reads it. If the destination is a
mailbox or a chat channel, confirm the message arrived in it. An observation made from inside the
application that emitted the alert cannot see any of the failure modes this check exists to
catch.

## Operator step required

This scaffold is not a control until a human completes it.

- [ ] Build the alert rules. No rule exists today for either required event class, so this step
      is deployment work tracked as `UW-D28` / issue #557, not a documentation step. Completing
      the rest of this document depends on it.
- [ ] Record in section 1 each committed alert rule, its definition path, the event class it
      covers, and the destination channel it routes to, ensuring both required event classes are
      covered.
- [ ] Deliberately fire each rule and confirm the notification at its destination.
- [ ] Record, in section 2, the timestamp, the rule identity, the destination, and the delivery
      result observed at that destination, for each rule fired.
- [ ] Set the `verified_on` date at the top of this document, and change the front matter
      `status` from `draft` to `published`.
- [ ] Re-fire and re-record at least every 180 days, and after any change to a rule, a routing
      configuration, or a destination.

## Related documentation

- [Security event catalog](security-events.md): which events the application emits and their
  fields. **Section 6 is the precondition for this document**, recording that no alert rules ship
  today and tracking that gap as `UW-D28` against issue #557; section 2 is the specification for
  the rules that have to be built.
- [Operator runbook](runbook.md), section 7: the scheduled checks that exist today and how their
  failures surface.
- [`README.md`](README.md) in this directory: the index of attestation artifacts.
