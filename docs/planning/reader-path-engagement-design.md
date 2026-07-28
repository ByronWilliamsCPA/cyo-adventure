---
title: "Reader Path Retention and Engagement Analysis"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Retain the routes children read and where they stop, roll them up de-identified, and use them to find book defects and engagement drivers."
tags:
  - planning
  - analytics
  - privacy
  - authoring
component: Backend
source: "story-quality-lessons-2026-07.md finding C"
---

# Reader Path Retention and Engagement Analysis

> **Status**: Proposed | **Date**: 2026-07-25
> **Serves**: [G9](./capability-register.md) (engagement visibility, literacy signals not
> surveillance), [A11](./capability-register.md) (corpus-level quality tooling),
> [A7](./capability-register.md) (observability), [K3](./capability-register.md) (choices are
> consequential)
> **Constrained by**: [S10](./capability-register.md) (privacy architecture),
> [S12](./capability-register.md) (anonymized aggregates, minimum-population threshold),
> [ADR-018](./adr/adr-018-childrens-privacy-compliance.md), [privacy-model.md](./privacy-model.md)
> **Lessons**: AL-019, AL-020, AL-023 in the [authoring lessons log](./authoring-lessons-log.md)

## 1. Goal

Two questions, neither answerable today:

1. **Where is this book broken?** Which passages do readers stop at, which endings has nobody ever
   reached, which choices does nobody take.
2. **What makes a reader keep going?** Which properties of a book or a passage correlate with
   readers continuing and finishing.

The first is a defect signal and pays off immediately. The second is a genuine research question
that only becomes trustworthy as the catalog and the reader population grow, and this design is
explicit about not overclaiming it early.

## 2. What exists today

Verified against the code, because the delta turns out to be much smaller than it looks:

| Fact | Location |
| --- | --- |
| The client sends the **full accumulated path** on every save, including after offline reading | `frontend/src/offline/sync.ts::toPutPayload` |
| The server **overwrites** it, keeping only the latest route | `api/reading.py`, `row.path = list(body.path)` |
| `ReadingState` is one mutable row per (child, storybook); no history across re-reads | `db/models.py::ReadingState` |
| `Completion` is append-only per ending, with `found_at` | `db/models.py::Completion` |
| `Completion` is read in five places, and **every one is a per-child read** | `api/me.py`, `api/reading.py`, `api/reading_history.py` |
| A published version already records the skeleton it was filled from | `StorybookVersion.skeleton_slug` |
| Ratings exist per (child, book) | `db/models.py::Rating` |
| Guardian per-child engagement visibility is shipped | `api/reading_history.py`, `GET /families/me/reading-summary` |

**The route data we want already arrives and is discarded.** Retaining it needs no client change and
no change to the request contract. That is the central fact of this design (AL-020).

What is genuinely missing: history across re-reads, any notion of stopping, and any aggregation
across children.

## 3. Data model

Two tables with deliberately opposite lifetimes. Child-linked detail is short-lived; the learning is
permanent and carries no identity.

### 3.1 `reading_trail` (child-linked, short retention)

One row per read-through, append-only in content, closed by a status transition.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | PK |
| `child_profile_id` | uuid | FK `child_profile` **ON DELETE CASCADE** |
| `storybook_id`, `version` | text, int | Composite FK `storybook_version` **ON DELETE CASCADE** |
| `path` | jsonb | Ordered node ids, as last reported |
| `steps` | int | `len(path)`, denormalized so rollup does not parse jsonb |
| `terminal_node` | text | Where the reader was when the trail closed |
| `ending_id` | text NULL | Null means they stopped without reaching an ending |
| `outcome` | text | `in_progress`, `completed`, `abandoned`, `restarted` |
| `started_at`, `last_step_at`, `closed_at` | timestamptz | `last_step_at` is **reader clock**, see section 4 |
| `device_id` | text NULL | Already available on the write |
| `rolled_up_at` | timestamptz NULL | Set when counted into `node_engagement`; gates the purge |

CASCADE on both FKs is not optional: this is child-linked data and must be purged with either the
profile or the story, exactly like `ReadingState` and `Completion`, and the existing deletion drill
must be extended to cover it.

```text
# #CRITICAL: security: reading_trail is child-linked behavioural data. Both FKs must
#            CASCADE or a profile deletion leaves an orphaned route history that the
#            deletion-readiness commitment (S10, ADR-018) says cannot exist.
# #VERIFY: extend tests/integration/test_deletion_drill.py to assert trail rows are
#          purged with the profile and with the storybook.
```

### 3.2 `node_engagement` (de-identified, permanent)

The learning artifact. No child id, no device id, no timestamps finer than a day. It is the only
part that survives the retention window.

| Column | Type | Notes |
| --- | --- | --- |
| `storybook_id`, `version`, `node_id` | text, int, text | Composite PK |
| `arrivals` | int | Trails that reached this node |
| `continued` | int | Trails that left this node to another node |
| `stopped` | int | Trails whose last observed step was this node, outcome `abandoned` |
| `completed_here` | int | Trails that closed here as `completed` (ending nodes) |
| `distinct_trails_min` | int | Population counter for the S12 threshold |
| `updated_at` | timestamptz | Last rollup |

A sibling `choice_engagement` (`storybook_id`, `version`, `choice_id`, `taken`, `offered`) carries
choice-level take rates, which is what surfaces a badly labelled or invisible-in-practice choice.

Rollup is incremental and idempotent: it counts trails whose `rolled_up_at` is null and whose
`outcome` is terminal, then stamps them. Re-running it is a no-op, which matters because it will run
from a scheduled job.

## 4. Session and stop semantics

This is where an offline-first app can easily lie to itself.

**Opening and continuing a trail.** No client change in phase 1: on each reading-state write, compare
the incoming `path` against the open trail's `path`.

- Incoming path **extends** the open trail's path: same trail, update it.
- Incoming path is a strict **prefix** of it: same trail, a K5 back-step, update it.
- Incoming path **diverges** at any shared index, or collapses to a single node (a restart): close
  the open trail (`restarted` if the reader chose to start over, `abandoned` otherwise) and open a
  new one.

This is a heuristic and should be labelled one. Phase 2 replaces it with a client-minted `trail_id`,
which makes it exact; the heuristic exists so phase 1 needs no contract change and starts collecting
immediately.

**Stopping.** A trail closes as `completed` when an ending is recorded. Otherwise it is
`abandoned`, and this is the part that must not be naive:

```text
# #CRITICAL: timing: a child may read offline for days before syncing. The idle
#            clock MUST run on last_step_at (the reader's own clock, as reported)
#            and NOT on server receipt time, or every offline reader is
#            misclassified as having abandoned the book.
# #VERIFY: a test that syncs a trail whose steps are dated 5 days ago and asserts
#          the trail is not classified abandoned on arrival.
```

And, correspondingly:

```text
# #CRITICAL: data-integrity: "abandoned" is a DERIVED, REVISABLE classification,
#            never a destructive transition. A late sync that extends a trail must
#            be able to reopen it and decrement the stopped counter it contributed.
# #VERIFY: a test that abandons a trail, rolls it up, then extends it, and asserts
#          node_engagement.stopped is corrected rather than double-counted.
```

The idle threshold is a tunable constant, proposed at **14 days of reader-clock inactivity**, which
is long enough to survive a holiday and short enough to be useful. Absence of data is not evidence
of stopping; it is absence of data.

## 5. What we can then answer

**Book defects (immediate value, small population needed):**

- **Stop rate per node** = `stopped / arrivals`. A passage that ends a large share of the trails
  that reach it is a difficulty cliff, a confusing passage, or a dead-feeling choice set.
- **Unreached endings.** The Ninth Hand has 232 endings. Which have ever been reached is a direct
  measure of whether the breadth we authored is breadth a reader experiences, and it is the honest
  test of AL-009's "breadth not depth" claim.
- **Choice take rates.** A choice offered often and taken never is usually mislabelled, not
  unattractive. This is the single most actionable authoring signal in the set.
- **Depth before stopping**, against the cell's fastest-finish floor: readers stopping consistently
  short of the arc floor means the front of the book is not carrying them.
- **Re-read rate**, which K5 and K6 treat as the goal, so it is a success metric rather than a defect
  signal.

**Engagement drivers (slower, and to be reported with its uncertainty):** join the aggregates against
attributes we already have per node and per book: words per node, FK grade, choice count, whether the
node is a decision, ending-kind mix, cell, `skeleton_slug`, cover presence, rating. The
`skeleton_slug` join is the highest-value one, because it separates "this fill is weak" from "this
skeleton is weak", and only the second should change the catalog.

```text
# #ASSUME: data integrity: with a small catalog and a small reader population these
#          correlations are DESCRIPTIVE, not causal, and a per-node rate over a
#          handful of trails is noise.
# #VERIFY: every surfaced figure carries its population, and the API refuses to
#          return a rate below the S12 minimum-population threshold.
```

**Feeding the flywheel.** `scripts/flywheel_scan.py` today reads only `CELL_SATURATED`, which is
request-time **demand**. Engagement is the missing **quality** signal: a cell whose books are opened
once and abandoned needs different catalog work than a cell with unmet demand. Adding it as a second
trigger input is a phase-3 item and inherits every existing WS-8 cap and the human-merge boundary
(ADR-020); nothing here gains the power to promote a skeleton.

## 6. Data integrity caveat that must be fixed first

The shipped client never sends `choice_path`, so the server-side engine replay that exists to reject
a forged `current_node`, `var_state`, or `path` is **dormant** (`api/reading.py` carries the
`#ASSUME` admitting it). Every route we would retain is therefore unverified reader-reported data.

For finding book defects that is acceptable, because a child has no motive to forge a route and the
signal is directional. It is not acceptable as an input to catalog automation. So AL-023 (enable
`choice_path` and make the replay authoritative) is a **prerequisite for phase 3**, not a
nice-to-have, and it is a security fix on its own merits regardless of this design.

## 7. Privacy posture

The governing phrase is G9's own: **literacy signals, not surveillance.** Concretely:

1. **First-party only.** No third-party analytics SDK, ever, in the kid context. ADR-018 decision 2
   is absolute and this design stays inside our own database.
2. **Rollup, then purge.** Raw `reading_trail` rows are purged **30 days after `closed_at`**, once
   `rolled_up_at` is set. The window matches ADR-007's raw-output precedent. The de-identified
   aggregate survives; the child-linked route does not.
3. **The purge job ships with the table, not after it.** `privacy-model.md` already records that the
   ADR-007 purge worker is an unbuilt Phase 5 deliverable. Repeating that pattern here would create
   a second pile of unpurged child data, so the purge is part of the same change or the table does
   not land.
4. **Minimum population before any aggregate surfaces** (S12). A rate computed over too few trails is
   both statistically useless and a re-identification risk in a single-child family. Proposed floor:
   **5 distinct trails** per figure, and the API returns the population alongside every rate so a
   reader of the dashboard can see what it rests on.
5. **No new child-identified read surface.** Guardians keep exactly the G9 summary they have; admins
   get aggregate-only routes. Nobody gains the ability to watch a named child's route.
6. **Purpose limitation, stated.** These aggregates exist to fix books and improve authoring. They
   are not for engagement optimization in the attention-economy sense, which the vision's permanent
   exclusions and the AADC posture rule out. Worth writing into G11's trust surface in the words a
   parent would want: we keep how far readers get in a book, we throw away who took which path after
   30 days, and we never use it to make the app harder to put down.

```text
# #CRITICAL: security: the aggregate endpoints must be aggregate-BY-CONSTRUCTION,
#            not aggregate-by-query. No route may accept a child_profile_id, so no
#            future caller can narrow an aggregate into an individual.
# #VERIFY: an IDOR-suite test asserting the insights routes reject any
#          profile-scoped parameter, alongside the existing cross-family cases.
```

## 8. API surfaces

Admin-only, read-only, modelled on the existing `api/moderation_dashboard.py` +
`moderation/insights.py` pair, which already does exactly this shape of work (aggregate persisted
records into evidence plus suggestions, read-only, admin-gated) and is the pattern to copy rather
than reinvent.

- `analytics/story_insights.py`, pure and unit-testable: given trails and aggregates, return
  stop-rate by node, unreached endings, choice take rates, depth distribution, and populations.
- `GET /api/v1/admin/story-insights/{storybook_id}/{version}`, per published version.
- `GET /api/v1/admin/skeleton-insights/{slug}`, across every version filled from one skeleton.

Both add routes, so the generated frontend client must be regenerated and committed in the same
change or the `contract` CI job fails on drift.

## 9. Phasing

**Phase 1: retain and roll up (no contract change to the write path).**
`reading_trail` and `node_engagement` tables plus a Supabase migration, trail capture in the existing
reading-state write, the incremental rollup, the 30-day purge, and the deletion-drill extension.
Acceptance: a trail is captured for an online read and for a late offline sync; an abandoned trail is
reclassified when a late sync extends it; the purge removes rolled-up rows and leaves aggregates
intact; the deletion drill passes.

**Phase 2: make it exact and trustworthy.** Client-minted `trail_id` replacing the prefix heuristic,
and `choice_path` enabled so the server replay is authoritative (AL-023). Then the admin insights
module and routes, with the S12 population floor enforced. Acceptance: route data is
server-verified; no figure surfaces below the floor.

**Phase 3: learn from it.** The attribute correlations, the `skeleton_slug` comparison, the G11 trust
copy, and engagement as a second flywheel trigger input behind the existing WS-8 caps.

Phases 1 and 2 are Phase 5 (Hardening) shaped work. Phase 3 depends on having a real reader
population and should not be scheduled by date.

## 10. Decisions needed from the owner

1. **Retention window** for raw trails: 30 days after close is proposed, on the ADR-007 precedent.
2. **Idle threshold** for `abandoned`: 14 days of reader-clock inactivity proposed.
3. **Minimum population** before an aggregate surfaces: 5 distinct trails proposed.
4. **Does a guardian see their own child's stop points?** G9 already promises engagement visibility
   and "literacy signals, not surveillance", and "Maya has started this book three times and stopped
   at the same page" is genuinely useful to a parent helping a struggling reader. It is also the
   closest this design comes to the surveillance edge. Recommendation: yes, but as reading-support
   framing at book granularity ("started 3 times, furthest point chapter 3"), never as a
   choice-by-choice replay of what the child did.

## 11. Related documents

- [Story quality lessons from the Wyrmreach build](./story-quality-lessons-2026-07.md), finding C
- [Authoring lessons log](./authoring-lessons-log.md), AL-019, AL-020, AL-023
- [ADR-018: Children's-privacy compliance](./adr/adr-018-childrens-privacy-compliance.md)
- [ADR-016: Recommendation sharing and the three-ring social boundary](./adr/adr-016-recommendation-sharing-social-boundary.md), where S12's ring-3 aggregate rules come from
- [ADR-007: Raw output retention](./adr/adr-007-raw-output-retention.md), the retention precedent
- [Privacy model](./privacy-model.md)
- [WS-8 catalog flywheel design](./ws8-catalog-flywheel-design.md), the phase-3 consumer
