---
title: "Ratings and Family Sharing: Design Spec"
schema_type: common
status: draft
owner: core-maintainer
purpose: >-
  Design for a future-version feature: a child rates finished books and shares
  favorites with cousins across connected family accounts, with attributed
  per-book relative ratings.
tags:
  - specifications
  - architecture
  - development
authors:
  - name: "Byron Williams"
---

> **Status**: Draft (awaiting review). Brainstormed and converged via the
> `brainstorming` skill. This is a design for a later version, not work scheduled
> into the current generation redesign.

## 1. Goal

Let a young reader rate a book they finished, and let them share books they like
with their cousins. The product value is social: a child sees which books their
relatives loved, and can pass along a favorite. Constraint that shapes every
decision below: the only expected users are one real extended family, a small,
mutually-trusted group. This lets us apply YAGNI hard. No public discovery, no
abuse-at-scale hardening, no friend-of-friend graphs.

## 2. Settled decisions

These were decided during brainstorming and are fixed inputs to the design:

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Account model for cousins | Separate `Family` accounts that can be **connected** | Matches real-world cousins (different households); collapsing to one extended-family account remains a fallback if linking ever feels like overkill. |
| D2 | Who shares, who approves | **Child initiates; the receiving child's guardian approves** | Keeps the kid-facing "share with my cousin" experience while putting the safety call with the adult responsible for the receiving child. |
| D3 | What lands when a book is shared | **A copy** (a snapshot imported into the cousin's family) | `StorybookVersion` is already immutable (no live-update benefit from a reference) and the reader is offline-first; copy keeps the family-scoped IDOR invariant literally unchanged and lets the safety re-check happen once, at import. |
| D4 | Ratings on share | The **sender's rating snapshots onto the share** ("Maya shared this, gave it 5 stars") | Informative, travels with the copy, always available. |
| D5 | Ratings on open | The reader sees a live, online-only strip of **attributed individual** relative ratings for the same book | No averaging, no leaderboard. Attribution by first name sidesteps the age-comparability problem (a 5-year-old's 5 stars is not a 9-year-old's 5 stars). |
| D6 | How families connect | **Invite code** (guardian generates, cousin's guardian enters, both confirm) | No email/SMS infrastructure needed; self-serve; fits a small trusted group. |
| D7 | Safety gate at import | **Re-validate + inform** | Re-run existing safety + reading-level validators against the receiving child's profile, surface flags, guardian makes the final call (override allowed, not a hard block). |
| D8 | Cross-family rating visibility | First name of the rater is visible **only within connected families** | The minimum exposure that turns a star count into "oh, Maya loved this." |

## 3. Phasing

Two features, sequenced because one enables the other. Each can become its own
implementation plan.

- **Phase A: Ratings.** Small and standalone. A child rates a finished book 1-5;
  private to the family until sharing exists. Shippable alone.
- **Phase B: Connected families, sharing, and visible relative ratings.** The
  large, security-significant half. Depends on Phase A.

## 4. Data model additions

All new tables hang off the existing `Family` ownership boundary in
`src/cyo_adventure/db/models.py`. None weaken that boundary; cross-family reads
are added as narrow, explicitly-scoped, link-gated operations beside it.

### 4.1 `rating` (Phase A)

Mirrors the grain of the existing `Completion` table (a per-child fact about a
story).

| Column | Type | Notes |
|--------|------|-------|
| `child_profile_id` | uuid, PK, FK -> `child_profile.id` | |
| `storybook_id` | str, PK, FK -> `storybook.id` | The family-local (possibly copied) book. |
| `value` | smallint | Validated 1-5 at the application boundary. |
| `rated_at` | timestamptz | |
| `updated_at` | timestamptz | A re-rating overwrites in place. |

Syncs like reading state, so rating works offline.

### 4.2 `Storybook.lineage_id` (Phase B, new column)

The identity that survives copying. A freshly generated book receives a new
`lineage_id` (uuid); every shared copy **inherits the source's** `lineage_id`.
"Same book across families" is defined as "same `lineage_id`." This column is the
linchpin that makes visible relative ratings possible under copy semantics.

> Add this column when Phase B lands. Newly generated books from that point get a
> fresh `lineage_id`; a one-time backfill assigns each pre-existing storybook its
> own `lineage_id` (each is its own lineage root).

### 4.3 `family_link` (Phase B)

A durable, mutual connection between two families.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid, PK | |
| `family_low_id` | uuid, FK -> `family.id` | Canonicalized so `family_low_id < family_high_id`. |
| `family_high_id` | uuid, FK -> `family.id` | Prevents duplicate links for the same pair. |
| `status` | str | `active` (created already-confirmed via the invite flow). |
| `created_at` | timestamptz | |

Every cross-family operation requires an **active** link between the two
families.

### 4.4 `family_invite` (Phase B)

Ephemeral. Redemption plus confirmation creates the `family_link`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid, PK | |
| `code` | str, unique | Sufficiently random; not trivially guessable. |
| `issuing_family_id` | uuid, FK -> `family.id` | |
| `created_by` | uuid, FK -> `user.id` | Issuing guardian. |
| `expires_at` | timestamptz | |
| `status` | str | `pending` / `redeemed` / `expired`. |
| `redeemed_by_family_id` | uuid, FK -> `family.id`, nullable | Set on redemption. |

### 4.5 `book_share` (Phase B)

The child-initiates / guardian-approves workflow record. Snapshots make the share
message correct forever.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid, PK | |
| `lineage_id` | uuid | Of the shared book. |
| `source_storybook_id` | str | |
| `source_version` | int | Pins the immutable version cloned on approval. |
| `from_family_id` | uuid, FK -> `family.id` | |
| `from_profile_id` | uuid, FK -> `child_profile.id` | |
| `from_profile_name` | str | Snapshot of the sharer's display name. |
| `sender_rating` | smallint, nullable | Snapshot of the sharer's rating at share time. |
| `to_family_id` | uuid, FK -> `family.id` | |
| `to_profile_id` | uuid, FK -> `child_profile.id` | Target cousin. |
| `status` | str | `pending` / `approved` / `declined`. |
| `approved_by` | uuid, FK -> `user.id`, nullable | Receiving guardian. |
| `resulting_storybook_id` | str, nullable | The copy created on approval. |
| `created_at` / `decided_at` | timestamptz | |

## 5. Flows

### 5.1 Connect two families (Phase B)

1. A guardian generates an invite code in-app (`family_invite`, status `pending`,
   with an expiry).
2. The cousin's guardian enters the code; the app validates it (exists, not
   expired, not already redeemed) and shows who is inviting.
3. On confirmation, a `family_link` is created `active` and the invite is marked
   `redeemed`.

### 5.2 Share a book (Phase B)

1. **Child shares.** In the reader, the child taps "share with cousin," picks a
   profile from a **connected** family (visible only because the families are
   linked), optionally attaching their rating. Creates a `book_share`
   (status `pending`) with the name and rating snapshots. Online action.
2. **Receiving guardian approves.** That cousin's guardian sees pending shares.
   The approval screen re-runs the existing safety and reading-level validators
   (`src/cyo_adventure/validator/`) **against the receiving child's profile**,
   shows age band / reading level / content flags plus any new flags, and the
   guardian approves or declines. Override is allowed; mismatch is not a hard
   block.
3. **Import on approval.** Server-side, link-and-approval-gated, the source
   `StorybookVersion.blob` is cloned into the receiving family as a new owned
   `Storybook` (published), carrying the `lineage_id`. `resulting_storybook_id`
   is set. The book appears in the cousin's library tagged "Shared by Maya,
   5 stars."

Because it is a **copy**, the IDOR-protected content path in
`src/cyo_adventure/api/library.py` stays literally unchanged: the cousin's
library still only contains cousin-owned rows.

### 5.3 See relative ratings on open (Phase B)

New endpoint, e.g. `GET /api/v1/storybooks/{storybook_id}/relative-ratings?profile_id=...`:

1. Authorize the requester owns the opened book; read its `lineage_id`.
2. Find **active** `family_link`s for the requester's family.
3. Return ratings joined to storybooks in those connected families with the same
   `lineage_id`, as attributed individuals: `[{first_name, rating}]`. No
   averaging, no leaderboard.
4. Online-only enhancement: offline, the strip is absent and the book (a copy)
   still reads fine.
5. Minimal exposure: only `display_name` and the star value cross the boundary,
   never story content or any other child data.

Siblings (same family) may appear in the same strip as cousins; this is free and
expected.

## 6. Error handling, edges, and security

- **Revocation.** Deleting a `family_link` stops future shares and future
  relative-rating reads; already-imported copies remain (a clean consequence of
  copy semantics).
- **Re-share / duplicate.** On approval, if the target family already holds that
  `lineage_id`, skip the clone and refresh provenance instead, to avoid library
  clutter.
- **Invites.** Expiring, single-redemption, sufficiently random codes. Guessing
  is low-risk in a trusted group but the code is still not trivial.
- **Offline.** Rating writes sync like reading state; sharing and approval
  require online; relative ratings degrade gracefully to absent.
- **RAD / security markers** (mandatory per `src/cyo_adventure/CLAUDE.md`): every
  cross-family operation asserts an active link first. The relative-ratings query
  is the highest IDOR-risk surface and gets explicit `#CRITICAL: security` tags
  plus negative tests. Mandatory categories touched: security (cross-family
  authorization, input validation on codes and ratings), data integrity (ORM
  boundary, snapshot correctness), external resources (database), timing
  dependencies (all async routes).

## 7. Testing

- **Unit:** `family_link` canonicalization; invite redemption state machine;
  rating validation (1-5); `lineage_id` inheritance on clone; relative-ratings
  query scoping.
- **Integration:** full share -> approve -> import -> appears-in-library; safety
  re-validation surfaces flags against the receiving child; revocation stops new
  reads but preserves copies.
- **Security (negative):** an unlinked family cannot receive shares, cannot read
  relative ratings, and cannot fetch content for another family's lineage.

Coverage stays at the project minimum (80% line); the cross-family authorization
paths are critical and should be at or above the critical-path bar.

## 8. Deferred / flexible (not v1)

- **Rating widget**: 5 stars vs kid-friendly faces is a UI-time decision; the
  backend (smallint 1-5) does not constrain it.
- **Live cross-family leaderboard / aggregation** (the rejected "C2"): a real-time
  family-wide ranking. Explicitly out of scope; the attributed per-book strip
  delivers the value without the cross-family read surface and the
  age-comparability problem of averaging.
- **Email/SMS invites**: deferred in favor of invite codes.
- **Reference (live) sharing** instead of copy: rejected in D3.

## 9. Open questions for planning

- Exact invite code length / expiry window.
- Whether Phase A ratings ship in a release ahead of Phase B, or both land
  together.
- Whether the relative-ratings strip caps the number of names shown (likely
  unnecessary at extended-family scale).
