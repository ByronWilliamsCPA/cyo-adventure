---
title: "Gamification Recommendation: Collection, Badges, Streaks, Reading Time (v1)"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Agent-developed recommendation commissioned by owner decision D12 (kid-appeal design
  review): a kid-kind, ring-1-only gamification design covering collection mechanics, badges, a
  weekly reading-days ring, and total active reading time, for owner approval."
tags:
  - planning
  - frontend
  - engagement
audience: product-owner, engineering
---

# Gamification Recommendation: CYO Adventure v1

> **Status**: Recommendation for owner approval | **Date**: 2026-08-01
> **Scope authority**: owner decisions D6 and D12 in
> [design-review-kid-appeal-2026-08-01.md](design-review-kid-appeal-2026-08-01.md) section 8:
> collection mechanics, badges, streaks, and total active reading time are in scope; engagement is
> child-focused, at most family-visible, and never leaves ring 1.
> **Binding constraints**: ADR-016 (ring 1 only), ADR-018 (first-party data, COPPA, Kids Category,
> K14 no dark patterns), D4 (kid notifications are in-app only, no push).

## 1. Design principles

Each principle is grounded in a source or a repo constraint; these are the acceptance criteria for
every feature below.

**P1. Reward the reading, with reading.** Extrinsic rewards for reading can crowd out intrinsic
motivation (the overjustification effect); Accelerated Reader's points-and-prizes model is the
canonical cautionary example, criticized since Kohn (1993) and Carter (1996), with Persinger (2001)
concluding it motivates children to earn points rather than to read
([Chartered College review](https://my.chartered.college/research-hub/motivating-students-to-read-a-look-at-the-theory)).
The strongest counter-finding is Marinak and Gambrell (2008): rewards *proximal* to reading (a
book, or nothing) sustain motivation, while unrelated tokens undermine it
([study](https://www.tandfonline.com/doi/abs/10.1080/19388070701749546),
[Reading Rockets summary](https://www.readingrockets.org/topics/motivation/articles/reading-motivation-what-research-says)).
Consequence: every reward in this design is made of story (endings, books, story-themed badges),
never points, coins, or purchasable anything.

**P2. Celebrate what happened; never punish what did not.** Duolingo's consecutive-day streak
drives retention (7-day streaks correlate with 3.6x course completion,
[UX Magazine](https://uxmag.com/articles/the-psychology-of-hot-streak-game-design-how-to-keep-players-coming-back-every-day-without-shame))
but runs on loss aversion, which in children produces documented anxiety and "performative
learning" ("a meltdown at 11:45 PM over a 200-day streak",
[Screenwise parent guide](https://screenwiseapp.com/guides/duolingo-streaks-and-anxiety-in-kids)).
Even Duolingo's own research concedes rigid streaks need "slack" to sustain persistence
([Duolingo blog](https://blog.duolingo.com/how-duolingo-streak-builds-habit)). Apps praised for
kind design (Finch, Pokemon Smile) have no loss state at all
([Together with Kai roundup](https://togetherwithkai.com/blog/best-habit-tracker-apps);
[Pokemon Smile](https://smile.pokemon.com/en-us)). Consequence: nothing in this design can be
lost, reset to zero, or visibly decay.

**P3. Ring 1 only, and no ranking even inside ring 1.** ADR-016 confines all child-linked social
visibility to the family; rings 2 and 3 are off limits for gamification per the owner constraint.
Prodigy shows what comparative mechanics do to children: the FTC complaint by Fairplay/CCFC
documents "two classes of students" and status pressure from visible tiers
([EdWeek](https://www.edweek.org/technology/popular-interactive-math-game-prodigy-is-target-of-complaint-to-federal-trade-commission/2021/02),
[Fairplay](https://fairplayforkids.org/pf/prodigy)). Sibling dynamics reproduce this in miniature,
so even within the family: badges may be *visible*, but no surface ever ranks siblings or places
their numbers side by side.

**P4. Reward days, not minutes.** A metric that pays out per minute of screen time is an
engagement-maximization mechanic. The FTC declined to ban engagement techniques in the 2025 COPPA
amendments but "remains deeply concerned about the use of push notifications and other engagement
techniques that are designed to prolong children's time online" and reserved Section 5 enforcement
([Federal Register](https://www.federalregister.gov/documents/2025/04/22/2025-05904/childrens-online-privacy-protection-rule),
[Jones Day](https://www.jonesday.com/en/insights/2025/05/ftc-finalizes-amendments-to-coppa--rule)).
The repo already commits to the parent-facing promise "we never use it to make the app harder to
put down" (reader-path-engagement-design.md section 7). Consequence: total active reading time is
a *guardian literacy signal and a kid diary fact*, never a score; nothing unlocks per minute.

**P5. Mastery-linked, not completion-farmable.** Khan Academy's early badge system taught students
to optimize for badges via fast, careless completion, and was redesigned to tie rewards to
demonstrated mastery
([HiWave research summary](https://hiwavemakers.com/blog/gamification-learning-apps-backfire-kids-research)).
Consequence: badge conditions key on *distinct* endings, *distinct* books, and replay depth, which
cannot be farmed by tapping through one corridor repeatedly.

**P6. First-party, in-app, behind the existing consent architecture.** ADR-018: no third-party
analytics in the kid context (also an Apple Kids Category rule: "Apps in the Kids Category should
not include third-party analytics or third-party advertising",
[App Review Guidelines 1.3](https://developer.apple.com/app-store/review/guidelines)). D4: the kid
channel is in-app only, so streak/badge mechanics get **zero** re-engagement notifications by
construction. New child-linked tables pay the standing four-artifact tax (section 5).

## 2. Recommended feature set v1

### 2.1 Collection mechanic: the Endings Gallery and the Finished Shelf

This is the anchor mechanic because it is the one made entirely of story (P1) and it extends the
existing K6 per-book tracker (`frontend/src/reader/EndingsProgress.tsx`,
`frontend/src/library/EndingsBadge.tsx`) rather than importing a foreign metaphor. Pokemon Smile's
collect-to-complete loop (catch Pokemon, earn caps, no penalty for missed days) is the comparable
done well.

- **Endings Gallery (per book)**: a screen reachable from the book card and the ending screen
  showing each *found* ending as a collectible card (title, valence-aware icon), and each unfound
  ending as a silhouette with "still hidden". Prerequisite fix already ranked #4 in the design
  review: `POST /completions` returns `{is_new, found, total}` so the "You found a NEW ending!"
  moment renders from the response and the current under-count race dies (section 3.4).
- **Finished Shelf**: a book with at least one ending found gets a "Finished" ribbon state on
  `BookCard`; a book with all endings found gets an "Every path walked!" state. Derived entirely
  from existing `Completion` rows.
- **Large-M honesty (AL-028)**: for books with many endings, the gallery denominator uses curated
  signature endings or milestone framing ("3 new endings this week"), per the design review's open
  question; do not show "1 of 232".
- **Later (not v1)**: `ending.rarity` / `is_secret` authored metadata, now cheap via ADR-025
  additive-minor schema versioning. Design the gallery so a rarity chip can slot in without layout
  change.

### 2.2 Badge seed taxonomy

Story-themed names, all computable today from `Completion`, `Rating`, and the `pipeline_event` log
(design review 4.2 confirms the substrate is sufficient to compute retroactively, with zero new
writes). No time-of-day badges (bedtime pressure), no speed badges (P5), no consecutive-day badges
(P2).

| # | Badge | Earn condition | Data source |
|---|---|---|---|
| 1 | **First Ending** | First `Completion` row ever | `Completion.found_at` |
| 2 | **The Path Not Taken** | 2+ distinct endings found in one book (first replay) | `Completion` per (book, version) |
| 3 | **Every Path Walked** | All endings of one book found | `Completion` vs storybook ending count |
| 4 | **Bookworm** | 5 distinct books with at least one ending found | `Completion` distinct `storybook_id` |
| 5 | **Shelf Hero** | 10 distinct books finished | same |
| 6 | **Ending Collector** | 25 total distinct endings found | `Completion` count |
| 7 | **Brave Reader** | After reaching a setback/negative-valence ending, went back and found another ending in the same book | `Completion.found_at` ordering + ending valence (blob) |
| 8 | **Story Wisher** | First child-initiated story request | `REQUEST_CREATED` event, `initiator_role="child"` |
| 9 | **Wish Come True** | A story the child requested was published and read to an ending | `REQUEST_CREATED` + `resulting_storybook_id` (needs the already-ranked #2 request-loop fix) + `Completion` |
| 10 | **Star Giver** | Rated 3 different books | `Rating` rows / `RATED` events |
| 11 | **Series Finisher** | Finished every book in one series | series metadata + `Completion` |
| 12 | **Forty Days of Stories** | Read on 40 distinct days, lifetime | new `reading_activity_day` table (section 2.4); the only badge needing new writes |

Badge 7 deliberately converts the miscoded-valence pain (design review 2.7) into a resilience
frame; ship it after the valence re-tag audit so it does not fire on mislabeled happy endings.
Badge 9 depends on `story_request.resulting_storybook_id` landing (already recommendation #2 in
the design review); hold it until then.

### 2.3 Streak design: a weekly reading-days ring, not a consecutive-day streak

**The variants, explicitly:**

- **Calendar-day consecutive streak (Duolingo)**: one counter that grows daily and resets to zero
  on a miss. Strongest retention mechanic in the industry, and the mechanism *is* loss aversion;
  mitigations (streak freezes) exist because the base design is punitive, and freezes themselves
  become an economy and a source of meta-anxiety.
- **Reading-days-per-week goal**: "read on N days this week"; the week refills every Monday. A
  missed Tuesday costs nothing that Wednesday cannot recover; there is no chain to break, only a
  ring to fill.
- **No-reset / lifetime designs (Finch-style)**: no streak at all; only ever-growing totals and
  gentle check-ins.

**Recommendation: reading-days-per-week ring plus a lifetime days-read total, and no
consecutive-day streak anywhere.** Concretely:

- A weekly ring: "You read on 3 days this week" toward a per-profile goal (default 3,
  guardian-adjustable, or off).
- Filling the ring produces a one-time celebration that week (mascot moment). An unfilled ring at
  week's end produces *nothing*: no sad state, no "you lost it" copy, no partial-failure framing.
  Next week simply starts fresh.
- A lifetime "days with stories" count that only ever grows, feeding badge 12.
- **No reminders of any kind.** D4 already rules out push to kids, and the FTC's stated concern
  plus the repo's own trust-copy promise rule out nag mechanics. The ring is visible when the
  child is already in the app, and nowhere else.

**Why this one.** A consecutive-day streak punishes exactly the days a child does not control:
school nights, a shared family tablet, a custody schedule, a camping weekend. The Screenwise
guide's core observation is that for a child the reset reads as erasure of effort, not as a missed
day. A weekly ring is the same habit-formation cue (regular reading rhythm) with the loss-aversion
engine removed: research Duolingo itself cites shows slack *increases* persistence, and the weekly
frame builds the slack into the structure instead of selling it back as freezes. It also happens
to be the only variant compatible with the repo's committed parent promise ("we never use it to
make the app harder to put down"): a mechanic whose worst case is "nothing happens" cannot make
the app hard to put down.

### 2.4 Total active reading time

No reading time is tracked anywhere today; this is the one genuinely new measurement.

**Definition of "active"**: time during which (a) the reader route is mounted, (b) the page is
foregrounded (`document.visibilityState === 'visible'`), and (c) the most recent interaction is
within the idle timeout. Interaction means: passage navigation, choice tap, scroll,
text-size/theme change, or read-aloud actively playing (read-aloud counts as active with no taps,
or the 3-5 band, which is read *to*, would register zero). **Idle timeout: 90 seconds** without
interaction pauses the clock (long enough for a slow reader on a long passage at the teen bands,
short enough that a tablet left open on the sofa does not accrue hours). Timer pauses immediately
on `visibilitychange` to hidden and on route unmount.

**Client measurement**: a small accumulator hook in the player (client-only measurement, so no
dual-engine conformance burden). Accumulate seconds into a per-day bucket keyed by
**reader-local date**, persisted to IndexedDB alongside the existing offline state so offline
reading counts.

**Sync**: piggyback on the existing reading-state sync cycle (`frontend/src/offline/sync.ts`):
flush day buckets as `{date, seconds_delta, device_id}` to a new `POST /v1/me/reading-time`.
Server adds deltas into `reading_activity_day` with two integrity guards: (a) idempotency via a
client-minted flush id so an offline queue replay is a no-op (same pattern as
`ReadingState.last_event_id`), and (b) a sanity clamp rejecting deltas exceeding elapsed wall time
since the bucket's last write (client clocks are reader-reported and unverified, the same caveat
reader-path-engagement-design.md section 6 records; acceptable for a literacy signal, tagged
`#ASSUME`).

**Where it surfaces**:

- **Kid**: days, not minutes. The weekly ring and lifetime days-read total derive from this table.
  Minutes are not shown to the child in v1 (P4: a kid-visible minutes counter invites
  self-optimization of screen time, the exact behavior we refuse to reward).
- **Guardian**: minutes per day and days-per-week, folded into the existing
  `GET /families/me/reading-summary` (which correctly 403s kid tokens today,
  `reading_history.py:418`, and stays that way). This is the "literacy signals, not surveillance"
  G9 framing: "Maya read on 4 days this week, about 65 minutes total."

## 3. Surfaces

| Surface | Shows | Visibility |
|---|---|---|
| **Ending screen** (Reader) | "NEW ending!" moment from the `{is_new, found, total}` response; gallery progress for this book; badge-unlock toast when a completion triggers one | Child |
| **Library** (`LibraryPage`/`BookCard`) | Finished/Every-Path ribbons; endings chip (exists); entry to the badge case and gallery; the weekly ring, small, in the shell header | Child |
| **Badge case** (new, off the library or `KidShell` nav) | Earned badges in color, unearned as silhouettes with kid-readable earn hints | Child; family-visible (below) |
| **Profile picker** (`ProfilePickerPage`) | Nothing numeric. At most a small celebratory sparkle on a profile with an unseen new badge. No counts, rings, or totals here | Family screen, hence the restraint |
| **Guardian console** (reading summary) | Minutes/day, days/week, badges earned, per-profile toggles | Guardian |

**Family-visible vs child-private**: badges and finished-shelf states are family-visible (a
sibling browsing the shared device can see them, consistent with ring-1 rating chips today). The
weekly ring, day counts, and all time data are child-plus-guardian only. The profile picker, the
one surface where siblings appear side by side, carries no comparable numbers at all: that is the
anti-leaderboard line inside ring 1 (P3). Nothing here crosses ring 2 or 3, ever; recommendation
payloads to connected families remain exactly the ADR-016 structured triple and gain no
gamification fields.

## 4. Guardian controls

Per-profile, in the existing profile settings surface, gated behind the parental gate like all
guardian settings (ADR-018):

| Control | Default | Notes |
|---|---|---|
| Weekly reading-days ring | **On, goal 3 days/week** | Off switch removes the ring entirely from the kid UI; guardian summary unaffected. Goal adjustable |
| Badges | On | Off hides the badge case and suppresses unlock toasts; awards still compute (re-enabling restores everything, nothing lost) |
| Show weekly ring at 3-5 band | **Off by default at 3-5** | Habit mechanics on pre-readers reward the parent's schedule, not the child; badges and gallery remain on |
| Reading-time capture | On (it is the substrate) | A guardian who disables *all* of the above still gets the reading summary; a separate "pause time capture" toggle is offered for families who want none of it recorded |

Defaults follow the K14 safe-room posture: everything shippable is on, but nothing punitive exists
to turn off; the toggles exist for family values (some families explicitly reject habit
mechanics).

## 5. Data model sketch

**Derivable from existing data (no new writes)**: endings gallery, finished shelf, badges 1-11,
the NEW-ending moment. Recommended v1 shape: a kid-scoped `GET /v1/me/progress` endpoint that
computes badges and collection state on read from `Completion`, `Rating`, and `pipeline_event`,
following the pure-composer projection pattern of `notifications/registry.py` (pure function over
rows, unit-testable without a session). Badge "seen" state for toasts lives client-side in
IndexedDB, avoiding a table. If read cost grows, materialize later; starting derived means
**zero migrations for the entire badge and collection layer**.

**New writes (one new table)**:

```text
reading_activity_day
  child_profile_id  uuid  FK child_profile ON DELETE CASCADE  (PK part)
  activity_date     date                                       (PK part)
  active_seconds    int   CHECK >= 0
  updated_at        timestamptz
```

Day-grain by design: no session rows, no timestamps finer than a day reach the server, which is
the minimum needed for rings, day counts, and guardian minutes, and the least surveillance-shaped
thing that satisfies the requirement (S10 posture).

**The four-artifact migration tax applies once, to this table** (per
reader-path-engagement-design.md, the established pattern): (1) raw SQL migration in
`supabase/migrations/`, (2) RLS policy, (3) cascade FK to `child_profile` (child-linked behavioral
data must purge with the profile), (4) extension of `tests/integration/test_deletion_drill.py`.
Plus the standing contract rule: new routes mean regenerating and committing the frontend client
in the same change or the `contract` CI job fails.

**Also needed (already ranked work, not new)**: `POST /completions` response gains
`{is_new, found, total}` (design review #4); `story_request.resulting_storybook_id` for badge 9
(design review #2).

## 6. Compliance and risk notes

- **COPPA / ADR-018**: everything is first-party, inside our Postgres, no new processors, no
  third-party analytics in the kid context (also Apple Kids Category guideline 1.3).
  `reading_activity_day` is new child-linked behavioral data: add it to the privacy-model data
  classification and the deletion-readiness set, and set a retention window (open question 2
  below).
- **ADR-018 counsel bundle (UW-M03), items to add**: (1) description of the engagement mechanics
  for the Kids Category review notes ("progress celebration and a weekly reading goal; no
  notifications, no purchases, no loss mechanics"); (2) the reading-time data classification and
  retention schedule; (3) trust-surface copy in parent words: *"We count which days your child
  reads and for how long, so you can support them. Nothing in the app punishes a missed day, and
  we never use this to make the app harder to put down."* That sentence is the design's own
  conformance test.
- **App Store Kids Category**: no purchases, links, or third-party anything in the kid surfaces
  (already the posture); the mechanics as designed have nothing a reviewer could read as
  manipulative because there is no loss state, no countdown, no nag, and no monetization
  adjacency (the entire Prodigy failure mode is structurally absent).
- **FTC direction of travel**: the 2025 COPPA amendments dropped the engagement-technique ban but
  flagged Section 5 enforcement and future rulemaking on practices encouraging prolonged use
  ([Latham and Watkins](https://www.lw.com/admin/upload/SiteAttachments/FTC-Publishes-Updates-to-COPPA-Rule.pdf)).
  Designing to "reward days, not minutes; celebrate, never punish" is ahead of that curve rather
  than exposed to it.
- **Explicitly do NOT build**: consecutive-day streaks or any reset-to-zero counter; streak
  freezes or any recovery economy; leaderboards or side-by-side sibling numbers (any ring,
  including ring 1); points, coins, gems, or any currency; anything purchasable or tiered;
  per-minute rewards or time-based unlocks; push/PWA notifications or emails to re-engage the
  child (D4); variable-ratio "mystery reward" mechanics; badges for speed or for time-of-day.

## 7. Open questions for the owner

1. **Badge visibility inside ring 1**: family-visible as proposed (consistent with rating chips),
   or kid-private with an explicit "show my badges to my family" per-profile choice?
2. **Retention for `reading_activity_day`**: keep day buckets indefinitely (they power the
   lifetime days-read total), or purge detail after 12 months keeping only running totals?
   Determines the counsel-bundle retention entry.
3. **Default weekly goal**: is 3 days/week the right default, and may guardians set 7 (which
   quietly rebuilds a daily streak)? Recommend capping the selectable goal at 6 to keep one
   guaranteed free day.
4. **3-5 band**: confirm ring off by default at 3-5 (badges and gallery on). Same question for
   5-8?
5. **v1 cut line**: gallery + badges 1-8/10/11 + ring + time tracking is the proposed v1; badges
   9 and 12 trail their dependencies (request-loop fix; time table). Approve that sequencing, or
   pull the request-loop fix into this workstream?
