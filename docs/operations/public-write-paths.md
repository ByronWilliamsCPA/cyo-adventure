---
title: "Public Write Path Inventory"
schema_type: common
status: draft
owner: core-maintainer
purpose: >-
  Inventory of every unauthenticated endpoint that creates state, each mapped to the
  anti-automation control that protects it and the place that control is enforced.
tags:
  - deployment
  - security
  - compliance
---

This document is an attestation scaffold. **No row below has been filled in yet.** An empty table
here means the control is unattested, not that it is absent by design.

It serves **OPS-009** in the standards manifest. The check carries no fixed staleness window;
re-verify whenever the service's public surface changes, and record the date of each review.

**verified_on**: `_(not yet verified)_`

## Why the enumeration is the artifact

The mapping half of this check is easy and the enumeration half is where it fails. If the list of
paths is assembled ad hoc during a review, two reviewers produce two different lists, and a path
that nobody thought to list is indistinguishable from a path that was listed and found to be
covered. Both read as silence.

So the order matters: **enumerate first, then map**. The enumeration is committed here, which
makes the next review a diff against a known list rather than a fresh act of recall.

## What may be written here

Record the endpoint by the route a client already sees, and the control by name. Do not record
thresholds, bypass conditions, exemptions, or any detail that is more useful to someone probing
the service than to someone maintaining it. Where an endpoint's mapping is incomplete, reference
the issue tracking it by ID rather than describing the shape of the gap; this repository is
public, and an inventory of soft spots is not a thing to publish. The tracking ID keeps the item
reviewable without narrating it.

## 1. Public write path inventory

**Serves OPS-009.** One row per unauthenticated endpoint that creates or mutates state.

| Endpoint (method and route) | Anti-automation control | Where the control is enforced | Status | verified_on |
| --- | --- | --- | --- | --- |
| _(no entry recorded)_ | | | | |

Field meanings:

- **Endpoint (method and route)**: as a client addresses it.
- **Anti-automation control**: the named class of control, one of a challenge (CAPTCHA or
  equivalent), a per-IP or per-identifier rate limit, or proof-of-work.
- **Where the control is enforced**: application code, edge or CDN, or managed provider. Where it
  is a managed provider setting, OPS-012 governs whether that setting is versioned and applied by
  CI rather than living only in a console.
- **Status**: `mapped`, or a tracking ID for an endpoint whose mapping is in progress.
- **verified_on**: the date this row was last confirmed against the deployed service.

## 2. How to enumerate

An enumeration is complete when it is derived from the deployed route table rather than from
memory:

1. List every route the deployed service exposes.
2. Mark each route that requires an authenticated principal. Those are out of scope for this
   check.
3. Of the remainder, mark each that creates or mutates persistent state, including state created
   indirectly such as a queued job, an outbound message, or a stored upload. A read-only
   unauthenticated route is out of scope here.
4. Every route surviving step 3 gets a row in section 1.

Categories the check expects to see considered, whether this service exposes each or not. A
category this service does not expose is not a finding, but recording that it is not exposed is
what makes the exclusion checkable later, so each one gets a row here rather than being passed
over in silence:

| Category | Exposed by this service | If not exposed, the precondition that makes it so | Confirmed on |
| --- | --- | --- | --- |
| Account signup | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Password reset request | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Contact or feedback submission | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Invite acceptance | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |
| Any other public API write | _(unfilled)_ | _(unfilled)_ | _(unfilled)_ |

State the precondition so it can be proven false. "No unauthenticated signup route exists; adult
accounts are provisioned just-in-time from an authenticated `POST /v1/onboarding`" is a
precondition a future reviewer can re-test in one request. "Not applicable" is not, and reads
identically whether the category was examined or skipped.

Record the date of the enumeration and the number of routes reviewed, so the next review can tell
whether the surface has grown:

| Enumeration date | Routes reviewed | Unauthenticated state-creating routes found | Reviewed by |
| --- | --- | --- | --- |
| _(no entry recorded)_ | | | |

## Where to verify from

A control that is supposed to stop automated traffic is a property of the deployed edge, so
confirm it by observing what an external client actually receives from the deployed hostname,
from a hosted runner or another network. Reading the control's configuration out of the process
that applies it, or exercising it from inside the same network, does not observe the path a real
client takes. Record which vantage each verification was made from.

## Operator step required

This scaffold is not a control until a human completes it.

- [ ] Enumerate the deployed route table by the procedure in section 2, and record the
      enumeration date and counts.
- [ ] Add a row to section 1 for every unauthenticated state-creating endpoint found.
- [ ] Map each row to its anti-automation control and record where that control is enforced,
      confirmed from outside the deployed boundary.
- [ ] For any row that cannot yet be mapped, open a tracking issue and record its ID in the
      `Status` column rather than describing the gap here.
- [ ] Set the `verified_on` date at the top of this document, and change the front matter
      `status` from `draft` to `published`.
- [ ] Re-enumerate whenever a route is added or an authentication requirement changes.

## Related documentation

- [`runtime-config.md`](runtime-config.md), section 3: rate limits on the authentication
  endpoints, which are scored separately under OPS-011.
- [`README.md`](README.md) in this directory: the index of attestation artifacts.
