---
title: "ADR-016: Recommendation sharing and the social boundary (three rings)"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the nuanced social policy: structured book recommendations flow within a
  family and between guardian-approved connected families (the cousins case), the system may
  eventually recommend from anonymized aggregate scores, and everything else social stays
  excluded: no messaging, no user discovery, no kid-to-kid contact without active parental
  approval."
tags:
  - planning
  - architecture
  - decisions
  - safety
  - privacy
---

# ADR-016: Recommendation sharing and the social boundary (three rings)

> **Status**: Accepted (2026-07-16)
> **Date**: 2026-07-16
> **Relates to**: [ADR-008](./adr-008-public-app-store-launch.md) (Kids Category compliance
> posture), [ADR-015](./adr-015-story-request-initiation-and-gating.md) (the register-driven
> decision process this continues)
> **Source**: owner ruling 2026-07-16, refining the vision's flat "no social features"
> exclusion; the `family_connection` substrate landed in PR #267 ahead of this record

## TL;DR

Replace the flat "no social, chat, or user-to-user features" exclusion with a three-ring
policy. Ring 1: within a family, kids give and receive book recommendations freely. Ring 2:
between two families explicitly connected by their guardians (the cousins case), structured
recommendations flow along directional, revocable connections; there is no "receive from
everyone" option. Ring 3: globally, only the system recommends, from anonymized aggregated
book scores, never kid to kid. Everything else social remains excluded: no messaging or free
text between users, no user discovery, and no contact between children outside active
approval from their parents.

## Context

### Problem

The vision doc's hard exclusion ("any social, chat, or user-to-user feature: a children's
app has no reason to carry one") was written in the one-family era, where the question could
not arise: every reader was a sibling. The owner's actual intent is narrower than the written
rule: the children's cousins should be able to receive recommendations from each other, which
requires a controlled cross-family channel. PR #267 built the substrate for this (a
directional `family_connection` table, "family A views family B's recommendations") before
any document recorded the policy, which the capability register flagged as unregistered
scope requiring an owner ruling. This ADR records that ruling.

### Constraints

- **Safety**: children must never come into contact with anyone outside active parental
  approval. A recommendation channel must not be a communication channel.
- **Compliance**: ADR-008's Kids Category posture (no social features exposed to children,
  no user-generated contact surfaces) must survive App Store review; the three-ring model
  must be describable in review notes as parent-approved family linking, not social
  networking.
- **Privacy**: a recommendation crossing a family boundary carries child-linked data (at
  minimum a display name and a reading signal) into another household; aggregate scoring
  must not.

### Significance

This is the boundary that separates "a reading app cousins can share" from "a social network
for children." Drawing it precisely, in writing, is what lets the cousins feature exist at
all without eroding the exclusion that protects everything else.

## Decision

**We will allow structured book recommendations in three rings, each with its own consent
model, and continue to exclude every other social capability.**

### Ring 1: within the family (allowed, default)

Kids in the same family may see each other's recommendations and ratings ("made for you by
Dad," "your sister loved this"). No new consent needed; the family is the trust boundary.

### Ring 2: connected families (allowed, guardian-gated, the cousins case)

- A `family_connection` is **directional** (family A receiving family B's recommendations is
  a separate fact from B receiving A's) and **revocable at any time**.
- A connection is active only with **active guardian approval on both sides**: the sharing
  family's guardian consents to their children's recommendations being visible out, and the
  receiving family's guardian consents to what their children see in. The admin console
  (PR #267) may broker and administer connections, but admin action cannot substitute for
  either family's guardian consent.
- What flows is **structured data only**: book reference, recommender display name, and
  rating/like. No free-text notes, no replies, no presence, no activity feed. A
  recommendation is a pointer to a book, never a message.
- There is **no "receive recommendations from everyone" option**, by design. The connection
  graph is enumerable, parent-built, and small.

#### Ring-2 data granularity (amendment, 2026-07-26)

The Decision above defines the rings but never enumerated *what granularity of child-linked data* may
cross ring 2. This amendment states it, and resolves the two in-flight asks that a prior proposed
addendum flagged as needing one edit rather than two racing ones. Both are now settled.

**Normative rule: two, and only two, categories of child-linked data may cross ring 2, and they carry
different consent bars.**

| Category | What crosses | Consent bar |
| --- | --- | --- |
| **Recommendation attribution** | A book reference, the recommender's `display_name` (a first name or nickname, and the only stored child name), and a rating or like | The mutual connection consent this ADR already requires. **Nothing further.** |
| **Personalized story content** | A child's real first name, and a closed set of other opted-in details, substituted into story prose read in the connected household | Mutual connection consent **plus** a separate, separately-worded, timestamped, policy-versioned disclosure consent, held per profile and per connection ([ADR-023](./adr-023-story-personalization-slots.md) section 3) |

Anything not in this table does not cross ring 2.

**Why the same datum carries two different bars.** A child's first name appears in both rows, so the
asymmetry needs justifying rather than asserting. The difference is bandwidth, audience, and
compounding, not the datum:

- An attribution is a **single low-bandwidth fact attached to a pointer**, rendered once, in a feed
  surface the receiving *guardian* opted into seeing.
- A substituted name is the **same datum delivered continuously**, through every passage of a book that
  may be re-read many times, and read directly by the other household's **children**.
- It also arrives **compounded**: one book can carry a first name, a sibling's first name, a pet's name,
  a kinship label, favourites, and a home type together. Individually trivial, jointly a recognisable
  portrait of a named child and their household. An attribution line carries one of those, once, and
  never compounds. Pronouns remain ring 1 only, so the most identity-sensitive slot never participates
  in a ring-2 disclosure at all.

This reasoning is not claimed to be decisive on the merits. It is recorded so a later reader can contest
the argument rather than guess at it. Both positions were confirmed by owner decision on 2026-07-25: the
attribution bar as working-as-intended, and ADR-023's stricter bar via OD-1. **Counsel review is the
remaining gate on the divergence**, not on the attribution row.

**Supporting basis for the attribution row**: `display_name` is established as a first name or nickname
and the only stored child name (`coppa-compliance-audit.md:129`), and the disclosure is already
inventoried (`gdpr-compliance-review.md:160`).

### Ring 3: global (system only, future)

The system may eventually aggregate book scores across all families and recommend books to a
child ("kids your age loved this"). Aggregation is anonymized: no child identity, family
identity, or connection-graph information may surface in or be inferable from a global
recommendation. Kid-to-kid recommendation across unconnected families never happens, at any
scale.

### The standing exclusions (unchanged in force, now precisely scoped)

No messaging, chat, comments, or any free-text channel between users. No user or family
discovery/search. No follower or friend mechanics. No way for a child to come into contact
with any person outside their family except through ring 2, which exists only by the active
approval of the parents on both sides.

## Options Considered

### Option 1: Three rings with dual-guardian consent ✓

Delivers the cousins use case with an enumerable, parent-built graph; every cross-family
edge has two accountable adult approvals; App Store posture stays "family linking."

### Option 2: Keep the flat exclusion

Simplest and safest on paper, but it silently loses the cousins use case the owner actually
wants, and the substrate had already landed; an unwritten exception is worse than a written
narrow one.

### Option 3: Opt-in public recommendations (receive from everyone)

Rejected outright by the owner. It converts the recommendation channel into a discovery
surface and makes the moderation burden unbounded.

## Consequences

### Positive

- ✅ Cousins can share book recommendations under parental control; the register's family
  loop gains a genuinely valuable capability without opening a social surface.
- ✅ The exclusion boundary is now written and testable instead of implicit.

### Trade-offs

- ⚠️ Cross-family visibility of child display names and reading signals is new child-linked
  data flow. Mitigation: structured-data-only payloads, dual-guardian consent, revocability,
  and a privacy-model entry (see below); recommendation payloads never include reading
  progress or request text.
- ⚠️ PR #267's substrate is admin-managed only; the guardian consent flow (both sides) does
  not exist yet. Until it does, connections must not activate recommendation visibility for
  child surfaces. The register tracks this as G17.
- ⚠️ Ring 3 anonymization is a hard requirement, not an optimization; small-population
  aggregates can deanonymize. Design gate: a global recommendation must be computable
  without any per-child or per-family identifier reaching the recommendation surface, and
  must apply a minimum-population threshold before a score aggregate is used.

### Technical Debt

- The guardian consent flow, the child-facing recommendation surface, and the ring-3
  aggregation design are all unbuilt; only the connection table and admin console exist
  (PR #267, open at the time of this ADR).

## Validation

### Success Criteria

- [ ] A recommendation is visible to a child in family A from family B only when both
      directional consents are active; revoking either side removes visibility immediately.
- [ ] No API surface accepts free text attached to a recommendation.
- [ ] A child token cannot enumerate families, users, or connections beyond its own
      family's active connections' recommendation payloads.
- [ ] Ring-3 (when built): global recommendations carry no identity and are suppressed
      below the minimum-population threshold.

### Review Schedule

- Initial: when the guardian consent flow lands.
- Pre-submission: ADR-008 Phase 7 compliance checklist (describe ring 2 as parent-approved
  family linking in review notes).

## Related

- [Capability register](../capability-register.md): items K17, G17, A15, S11, S12.
- [ADR-008](./adr-008-public-app-store-launch.md): Kids Category compliance posture.
- [Privacy model](../privacy-model.md): cross-family child-linked data flow entry.
- [Project vision](../project-vision.md): the out-of-scope bullet this ADR refines.
