---
title: "Adversarial Review Record: Ceiling-Scale Story at 746 Nodes"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Preserve the raw findings of the 2026-07-25 adversarial review of the 746-node Wyrmreach book across the reader surfaces and the import/publish legs."
tags:
  - planning
  - quality
  - review
component: Development-Tools
source: "authoring-lessons-log.md AL-026..AL-040"
---

# Adversarial Review Record: Ceiling-Scale Story at 746 Nodes

> **Date**: 2026-07-25 | **Subject**: `out/the-ninth-hand.filled.json` (746 nodes, 232 endings,
> 42,085 words, Tier-2, book 3 of the `wyrmreach` chain)

Raw output of two independent adversarial reviewers, preserved verbatim below. Findings are
labelled VERIFIED or SUSPECTED **by the reviewer**; a subset was independently re-verified before
being promoted into the [authoring lessons log](../authoring-lessons-log.md), and the log rows are
the actionable record. Read this file for the evidence and the measurements, the log for what we
decided to do.

Independently re-verified while triaging: the reader-side read-length collapse (reproduced on
`player/engine.StoryEngine`), the absence of response compression, `revisionRef` advancing only on
`saved`, the 409 adopt-and-remount path, the Stage 0 per-node classifier short-circuit, and the
carried-variable bound mismatches between books 2 and 3.

---

# Part 1: Reader surfaces

## Reader-side adversarial review: the-ninth-hand (746 nodes / 232 endings / 42,085 words)

Measured baseline for `out/the-ninth-hand.filled.json` (all numbers taken with read-only
`node`/`python3` over the artifact, plus an inline faithful port of `frontend/src/player/engine.ts`
+ `evaluator.ts`):

| metric | the-ninth-hand | vault-of-nine-iron (bk 1) |
| --- | --- | --- |
| bytes on disk (pretty) | 526,306 | 235,592 |
| bytes minified (what an API returns) | 405,742 | 177,842 |
| nodes | 746 | 305 |
| endings | 232 | 105 |
| choices | 1,030 | - |
| longest realizable route (choices) | 74 | 71 |
| body prose | 225,812 chars / 42,085 words | - |
| **condition-aware random playthrough (n=5000)** | p10 **2 pages**, median **5 pages**, p90 14, max 51 | - |
| words per playthrough | p10 137, median **301**, p90 803, mean 405 | - |
| distinct endings hit across 5,000 random reads | **100 of 232** | - |

That median of 5 pages / 301 words per completed read is the number every finding below
turns on: 215 of the 514 non-ending nodes offer at least one choice that lands straight
on an ending, so a child's typical encounter with this 42,085-word book is a ~90-second,
300-word read that terminates. Nothing in the reader is calibrated for that.

### The K6 endings mechanic inverts at M=232: it stops being a motivator and becomes a scoreboard of failure [VERIFIED]
WHAT: "You found ending N of M! Read again to find more." is designed around a small M
(the spec example and every test is 3-of-7, 2-of-5, 3-of-7). At M=232 the child finishes a
read and is told **"You found ending 1 of 232!"** - 0.4% - and the same line greets them on
the ending screen of every subsequent read (2 of 232, 3 of 232...). The shelf half degrades
worse: `EndingsBadge` drops the dot row entirely once `total > MAX_DOTS = 10`
(EndingsBadge.tsx:19,25,29), so the *only* kid-legible part of the mechanic - the row of
filled/empty dots, which is what a pre-literate-ish reader actually parses - is silently
removed exactly for the books that need replay motivation most. What is left on a phone
card is the bare string "1 of 232 endings found".
WHY: The promise "read again to find more" is arithmetic the child can do. At a measured
mean of 405 words per playthrough, filling the bar means ~232 separate reads and ~94,000
words of reading, most of it re-reading shared prefixes. A denominator that large converts
a reward ("you're 3/7 of the way, nearly there") into a permanent statement of
incompleteness. It is also partly unachievable: 5,000 condition-aware random playthroughs
reached only **100 of the 232** endings, so a large share of the denominator sits behind
specific 8-variable states a child browsing by taste will not stumble into. The mechanic
does not transfer to this scale - this is a design finding, not a layout bug. Layout itself
survives (dots are capped, text wraps), which is why it will ship unnoticed.
WHERE: frontend/src/reader/EndingsProgress.tsx:60-65 (renders whenever `total_endings > 1`,
no upper bound); frontend/src/library/EndingsBadge.tsx:19-40 (`MAX_DOTS = 10`, dots dropped
above it); src/cyo_adventure/api/reading_history.py:324-328,360-362 (`total_endings` is the
raw pinned-version ending count, 232, with no banding); frontend/src/library/LibraryPage.tsx:362.
FIX: Stop showing a raw denominator above a threshold. Two options, both cheap:
(1) switch to milestone framing for large M - "You found 3 new endings! There are lots more."
with a tier ladder (3/10/25/50 endings -> a named badge), and keep "N of M" only while
`total_endings <= MAX_DOTS`; or (2) scope the denominator to something reachable - count
endings the child can still reach from their own visited frontier, or a curated
"signature endings" subset declared in story metadata - and show that. Either way,
`EndingsProgress` and `EndingsBadge` should take the same threshold constant so the ending
screen and the shelf never disagree, and a book with 232 endings should never render a
percent-like fraction to a child.

### The reading-progress bar is frozen near zero for this entire book [VERIFIED]
WHAT: `readerProgressPercent` is `100 * visit_set.length / story.nodes.length`
(readerProgress.ts:7-11). The denominator is all 746 nodes; the numerator is the pages the
child has actually seen on this route. At the measured median playthrough (5 pages) the bar
reads **1%**; at p90 (14 pages) **2%**; on the deepest realizable 71-choice route it peaks at
**10%** just before the ending screen forces it to 100 (Reader.tsx:258).
WHY: The bar is the only always-visible feedback in the reader chrome, and for this book it
is a flat line that never visibly moves - each page tap advances it by 0.13%, below the
rendering resolution of a phone-width bar. A child reading book 1 (305 nodes) sees the same
route render as 23%, and a 100-node picture book as 71%: the bigger the book, the more
broken the signal, so this degrades specifically at 746. Then the ending screen snaps 1% to
100%, which reads as arbitrary rather than as an accomplishment. The numeric label is
already withheld as untrustworthy (`showLabel` defaults false, ReaderChrome.tsx:73), so the
team has effectively acknowledged the denominator is wrong and shipped the bar anyway; the
`aria-label` still announces "5 of 746 pages explored" to a screen-reader child.
WHERE: frontend/src/reader/readerProgress.ts:7-11,16-19; frontend/src/reader/Reader.tsx:257-259;
frontend/src/reader/ReaderChrome.tsx:11-19,88.
FIX: Progress within a read is route progress, not corpus coverage. Use the current route:
`path.length / (path.length + longest remaining distance to an ending from current_node)`,
computed once per book from a precomputed per-node depth-to-nearest/furthest-ending map
(the same walk the validator already does), or simply drop the bar in the reader for books
above some node count and show "Page 5" instead. Corpus coverage belongs on the shelf card
(where "explored" framing is honest), not in the reader chrome during a read.

### Every page turn synchronously replays the whole read from page 1, and rebuilds a 746-entry index ~300 times while doing it [VERIFIED]
WHAT: `canGoBack(story, reading)` calls `back()`, which calls `replayRecordedPath()`, which
DFS-replays the entire recorded path from `start_node` through the real engine - and throws
the result away, keeping only "yes/no". It is memoized on `[story, reading]`
(Reader.tsx:216), so it runs once per *reading state*, i.e. **once per page turn, inside the
render pass**, before the new passage paints. Compounding it, `nodeIndex(story)` builds a
fresh `Map` of all 746 nodes on *every* engine entry point (engine.ts:17-19, called from
`enterNode`:71, `visibleChoices`:157, `isEnding`:164, `currentEndingId`:169, `choose`:184),
and `intBounds` rebuilds per `choose` (engine.ts:196, with an `#ASSUME` comment
acknowledging it). A replay at depth 71 performs **285 nodeIndex rebuilds = 212,610 Map
insertions**. Measured with a faithful inline port of engine.ts + evaluator.ts against the
real artifact, walking the deepest realizable route:

| depth | the-ninth-hand (746 nodes) | vault-of-nine-iron (305 nodes) |
| --- | --- | --- |
| 10 | 5.1 ms / 30,586 Map entries | 1.5 ms / 12,505 |
| 30 | 11.0 ms / 90,266 | 5.3 ms / 36,905 |
| 50 | 16.8 ms / 149,946 | 8.4 ms / 61,305 |
| 70 | 26.1 ms / 209,626 | 9.7 ms (at 67) / 82,045 |

Cost is O(depth x nodes), so it is ~2.5x book 1 at equal depth purely because of the node
count. Worse, a **BACK press pays it three times**: the machine's `canGoBack` guard runs a
replay (machine.ts:111), `applyBack` runs `back()` again (machine.ts:99-100), and the
resulting new `reading` invalidates Reader.tsx's `useMemo` for a third. That is ~72 ms of
blocked main thread on this desktop measurement at depth 71; a mid-tier phone or an older
iPad runs 4-6x slower, i.e. **roughly 300-430 ms frozen** on the one control built for
"kids mis-tap constantly" (Reader.tsx:210).
WHY: Deep routes are exactly the replay-motivated behavior the book is designed to reward.
A child working a 40-70 choice route feels the reader get progressively stickier the further
in they get - the page turn that was instant on page 3 stalls a fifth of a second on page 60,
and the "Go back" button, which a mis-tapping child hammers, is the slowest thing in the app.
On a 300-node book none of this is visible; it becomes visible at 746 and it gets worse the
deeper the child commits. There is no spinner, so it reads as the app being broken.
WHERE: frontend/src/player/engine.ts:17-19 (nodeIndex rebuilt per call), :71, :157, :164,
:169, :184, :196 (intBounds rebuilt per choose), :253-307 (DFS replay), :325-347
(`back`/`canGoBack`, `canGoBack` discards the computed state);
frontend/src/reader/Reader.tsx:216; frontend/src/player/machine.ts:99-100,111.
Also O(nodes) per render, unmemoized: `story.nodes.find(...)` at Reader.tsx:96.
FIX: Three independent, low-risk changes, in order of payoff:
1. Memoize the node index per Storybook object (`WeakMap<Storybook, Map<string, StoryNode>>`)
   and the same for `intBounds`. Story identity is already stable for the reader's lifetime
   (ReaderPage holds it in state, ReaderPage.tsx:99,255), so the `#ASSUME` at engine.ts:192
   is satisfied by a WeakMap keyed on the story object. This alone removes ~99% of the work.
2. Make `canGoBack` not compute the answer it discards: cache the replayed `states[]` per
   reading state (or have the machine carry a `previous` state forward), so a BACK press
   costs one replay instead of three, and a page turn costs zero.
3. Cheap guard for the common case: `path.length > 1 && path[0] === story.start_node` is a
   necessary condition and answers "no" instantly; only the "yes" answer needs the replay,
   and it can be deferred off the render path (compute it in an effect and let the button
   appear a frame later) rather than blocking the passage paint.

### The story download is 405 KB uncompressed: no response compression is configured anywhere [VERIFIED]
WHAT: `GET /v1/storybooks/{id}/versions/{v}` returns `version_row.blob` whole
(library.py:405-471), and nothing in the stack compresses it. `app.py` adds only
`CorrelationMiddleware` and `add_security_middleware` (app.py:469, 58) - no
`GZipMiddleware`; `grep -rn "GZip|gzip|brotli"` across `src/`, `frontend/`,
`docker-compose.yml`, and `docker-compose.prod.yml` returns nothing. Measured: the ninth
hand serialises to **405,742 bytes** minified and **106,873 bytes** gzipped (3.8x). So the
child's device pulls **396 KB instead of 104 KB**, a 292 KB avoidable transfer for one book,
and **750 KB instead of 202 KB** to take the whole 3-book series offline.
WHY: This is the download-before-you-can-read step, and it is the one moment the child is
stuck on a spinner with nothing to do. On a weak LTE/tethered connection (~1 Mbps effective,
which is the normal case for "downloading the book in the car before the trip") 396 KB is
about 3.2 s versus 0.8 s. It is also the step most likely to be interrupted: there is no
range/resume, so a dropped connection restarts the whole 396 KB. The same book at book-1's
size (174 KB) mostly hides this; at 2.3x the bytes it becomes a visible wait.
WHERE: src/cyo_adventure/app.py:469 and the middleware block at :433-469 (no compression
middleware); src/cyo_adventure/api/library.py:405-471 (returns the raw blob);
frontend/src/reader/ReaderPage.tsx:175-190 (single `fetchStory` call, cache-first, no
progress reporting).
FIX: Add `app.add_middleware(GZipMiddleware, minimum_size=1024)` (or enable brotli/gzip at
whatever terminates TLS in the homelab deployment). One line, ~4x on every story download and
on the library listing. Separately, the download has no progress affordance: ReaderPage shows
a bare "Opening your story..." (ReaderPage.tsx:460) for the entire transfer, so consider a
determinate progress state for first-download of a book above some size.

### Every library-shelf load deserialises every book's full blob server-side [VERIFIED]
WHAT: `list_library` runs `select(StorybookVersion)` for every published book on the shelf
(library.py:346-351) - selecting the entire row, including the `blob` JSONB column - and then
uses each blob only to read `title`, `metadata`, a node count (`len(nodes)`), and one
`current_node in nodes` ending check (`_library_item`, library.py:197-270; `_node_count`
:163-179; `_current_node_is_ending` :181-195). For this 3-book series that is **768 KB of
JSONB decoded per shelf render**, of which 405 KB is the ninth hand, to produce three small
cards. `_current_node_is_ending` additionally scans the node list linearly per book.
WHY: The kid's shelf (`/library/:profileId`) is the app's front door and the screen they hit
on every launch. Its latency now scales with the total prose volume of everything assigned to
the child rather than with the number of books: adding one 746-node gamebook to a shelf costs
the same server work as adding three 300-node books. A family that accumulates a dozen of
these turns the shelf into a multi-megabyte decode per tap-through, and the child sees the
skeleton/spinner state on a screen that should be instant.
WHERE: src/cyo_adventure/api/library.py:346-351 (whole-row select incl. blob), :387
(`blobs[(storybook_id, version)]` passed into `_library_item`), :163-179, :181-195, :197-270.
FIX: Stop reading the blob on the listing path. Either (a) select only the columns needed
(`load_only(...)` / an explicit `select(StorybookVersion.storybook_id,
StorybookVersion.version, StorybookVersion.cover_status, ...)`) and denormalise `title`,
`node_count`, `ending_count`, and an `ending_node_ids` set onto `StorybookVersion` at publish
time; or (b) push the extraction into SQL with JSONB operators
(`blob->>'title'`, `jsonb_array_length(blob->'nodes')`) so Postgres never ships the prose to
the app. (a) is preferable because the ending check needs set membership, which is exactly a
publish-time-computable column.

### Reconnecting mid-read yanks the child backwards to an earlier page and remounts the reader [VERIFIED by code trace]
WHAT: The offline queue replay and the reader's live save both write the same row with no
coordination, and the reader's local revision counter does not advance while offline. Traced:
1. Offline, `persist()` gets `kind: 'queued'` and **never updates `revisionRef`** - only the
   `'saved'` branch does (ReaderPage.tsx:304-305). So after N offline choices `revisionRef`
   still holds the pre-offline revision R, while N queued writes all carry base revision R.
2. `useReplayOnReconnect` is mounted **inside ReaderRoute** (ReaderRoute.tsx:95), so it fires
   on the `online` event *while the child is mid-story*, and `replayQueue` starts sending the
   queued writes one at a time (sync.ts:285-325). The first one matches revision R and the
   server bumps the row to R+1 (reading.py:371, 413).
3. The child's next tap fires `persist()` with `state_revision: revisionRef.current` = R
   (ReaderPage.tsx:296). The server now sees `body.state_revision != row.state_revision` and
   returns **409 with the replayed row as `current_row`** (reading.py:371, :87-89).
4. ReaderPage's 409 handler adopts the server row unconditionally, writes it into the local
   cache, sets it as `initialReading`, and **bumps `readerKey` to remount the Reader**
   (ReaderPage.tsx:317-337). The adopted row is an *earlier* position from the offline
   session, so the child is teleported back and the reader restarts from there.
Then it repeats: the child reads on from the stale node, replay keeps advancing the revision,
the next live save 409s again, adopt-and-remount again.
WHY: This is not a narrow race, it is the expected outcome whenever the network returns while
the child is still reading, and the size of this book is what makes it near-certain. Measured
on the deepest realizable route: **74 queued rows** for one offline read-through
(largest PUT body 2,270 bytes, 97.8 KB total), replayed as **74 sequential round-trips** -
at a modest 150 ms RTT that is an ~11-second window in which every tap 409s. Book 1's shorter
queue gives a proportionally narrower window; a 5-page picture book gives almost none. What
the child experiences is the story jumping back several pages, the passage remounting (scroll
reset, `Go back` history rebuilt), and a "All caught up! Your reading is saved." success toast
(ReaderRoute.tsx:89-91) fired at the same moment their place was overwritten. The design note
at ReaderPage.tsx:318-327 explicitly accepts losing this device's position to *another
device*; it does not contemplate losing it to **this same device's own queued past**, which is
what happens here.
WHERE: frontend/src/reader/ReaderPage.tsx:146,237,296,304-305,317-337;
frontend/src/reader/ReaderRoute.tsx:95; frontend/src/offline/sync.ts:186-201,277-325;
src/cyo_adventure/api/reading.py:363,371,413-414,87-89.
FIX: The reader's own writes must not compete with its own replay.
1. Cheapest correct fix: have `persist()` participate in the same `navigator.locks`
   `'cyo-replay'` lock so a live save cannot interleave with a replay, and have `replayQueue`
   **collapse the queue per `(profile_id, storybook_id)` before sending** - only the newest
   queued state per story is meaningful (the row is last-write-wins with a revision chain),
   so 74 round-trips become 1 and the window nearly vanishes. Drop the superseded rows.
2. Advance `revisionRef` optimistically on a `'queued'` result, or (better) have the queued
   write path own the revision chain so the reader never sends a base revision the queue has
   already consumed.
3. Guard the adopt-and-remount branch: if the 409's `current_row` is a **prefix of** the local
   `path` (same start, shorter, same book), it is this device's own stale past - re-save the
   local state onto the server revision (`continue_from_this_device`, sync.ts:231-235) instead
   of adopting backwards. Only adopt when the server row is genuinely divergent.

ADDENDUM to the shelf finding: `/v1/reading-history` does the same whole-blob select
(reading_history.py:246-251) purely to read `metadata.ending_count` (`_ending_count`:103-134)
and run one node-membership check (`_is_ending_node`:137). `EndingsProgress` fires that
endpoint **on every ending-screen mount** (EndingsProgress.tsx:37-39), and because the median
playthrough of this book is 5 pages the child reaches an ending screen constantly - so the
highest-frequency read in the kid's session is also the one that decodes every book's full
prose server-side. Same fix (denormalised `ending_count` / `ending_node_ids` columns) closes
both call sites.

### At 746 nodes the typical read got SHORTER than at 305 nodes: 5 pages / 304 words vs 11 / 654 [VERIFIED]
WHAT: The book grew 2.4x in nodes and 2.3x in bytes, but the typical child-visible read
*halved*. Measured over 3,000 uniform walks per book (and confirmed at 5,000 walks with the
real condition-aware engine for the ninth hand):

| | vault-of-nine-iron (305 nodes) | the-ninth-hand (746 nodes) |
| --- | --- | --- |
| median pages per completed read | 11 | **5** |
| median words per completed read | 654 | **304** |
| mean pages | 11.7 | 6.7 |
| choices that end the book immediately | 106 / 475 = 22.3% | 232 / 1030 = 22.5% |
| decision nodes where >=50% of choices end the book | - | 54 |
| decision nodes where EVERY choice ends the book | - | 3 |
| endings reachable within 2 choices of the start | - | 7 |

The per-choice termination density is identical across the two books (~22.5%), so the extra
608 nodes went into *width* - more parallel early branches, each terminating - not into depth.
The result: 7 of the 232 endings sit within two taps of the start, and the median encounter
with a 42,085-word book is 304 words.
WHY: This is the finding that makes the other four bite. The reader's feedback surfaces are
all calibrated on "a read is a substantial journey": the progress bar advances 5/746 = 1% and
then snaps to 100%; the endings tracker announces "1 of 232"; the only way back in is
"Read again", which restarts at `n_start` and discards the whole 8-variable state
(machine.ts `reset` -> `safeStart`, engine.ts:90-106). So the loop a child actually lives is:
~90 seconds of reading, an ending screen that reports 0.4% completion, restart from page one.
Nothing in the reader recognises that a 5-page read of this book is normal rather than a
failure, and nothing offers re-entry other than "one page back" (which is also the slowest
control in the app - see the replay finding). A child does not conclude "this book is wide",
they conclude "I keep doing it wrong".
WHERE: measured from out/the-ninth-hand.filled.json and out/the-vault-of-nine-iron.filled.json;
the reader surfaces that mis-serve it are frontend/src/reader/readerProgress.ts:7-11,
frontend/src/reader/EndingsProgress.tsx:60-65, frontend/src/reader/Reader.tsx:372-387
(ending-screen actions: Read again / Go back / Back to my books), frontend/src/player/machine.ts
(`reset` restarts from `start_node`).
FIX: Two halves, and both are needed.
- Reader side: give the ending screen a re-entry that is not a full restart. A
  "Try a different turn" action that returns to the **last node that had an unexplored visible
  choice** on this route (computable from the replayed `states[]` that `back()` already builds,
  and cheap once the index is memoized) turns a 5-page dead end into a branch retry instead of
  a restart, and makes the 232 denominator approachable in one sitting.
- Authoring/validator side: this is worth a validator signal, not just a reader fix. A
  band/scale rule on *expected read length* (e.g. reject or warn when the median
  uniform-walk playthrough for a 16+ "long" book falls below some page floor, or when
  >20% of a node's choices terminate) would have caught this before the book was filled.
  The measurement is ~20 lines on top of the walk machinery `validator/walk.py` already has.

## Checked and fine

- **Reading-state caps are not remotely at risk.** The graph is a verified DAG (no cycles),
  the longest realizable route is 74 choices, and `path` only grows on a forward choice while
  `back()` *shrinks* it by replaying a shorter prefix (engine.ts:325-341). So `path` maxes at
  75 against `PATH_MAX_LENGTH = 2020`, and `visit_set` maxes at 75 against
  `VISIT_SET_MAX_LENGTH = 505` (schemas.py:50-52,78-79) - and both reset on RESTART
  (engine.ts:98-99). No legitimate reading pattern, including heavy backtracking or a
  multi-hour session, gets within 6x of either cap. Explicit non-finding.
- **Per-save payload is small.** Largest PUT body on the deepest route is 2,270 bytes; a whole
  74-choice read sends 97.8 KB across 74 saves. The `JSON.stringify` dedup signature in
  `persist()` (ReaderPage.tsx:279-285) is ~2 KB per choice. Fine. (The *number* of offline
  round-trips is the problem, not their size - see the reconnect finding.)
- **IndexedDB capacity is a non-issue at this size.** 526 KB pretty / 405 KB minified per
  book, ~750 KB for the whole 3-book series as structured clones. Nowhere near any mobile
  Safari or Chrome origin quota. `JSON.parse` of the full 526 KB blob measured at ~2 ms, and
  it happens once per reader mount, not per render. `cacheStorybook` failures are swallowed
  (ReaderPage.tsx:188-193) which would silently disable offline reading, but that is
  size-independent and out of this review's scope.
- **`EndingsBadge` layout does not break at 232.** The dot row is capped at `MAX_DOTS = 10`
  and simply omitted above it (EndingsBadge.tsx:19,25), and `clampedFound` prevents
  "233 of 232". The failure is semantic, not visual - which is why it is filed as a design
  finding above rather than a layout bug.
- **`visibleChoices` per render is correctly memoized** (Reader.tsx:101) and costs one node
  index build, not a replay. `story` identity is stable for the reader's lifetime
  (ReaderPage.tsx:99,255), so the `useMemo` deps do behave as intended; the replay cost is
  once per page turn, not once per render.
- **The engine is not accidentally exponential on this book.** The `MAX_REPLAY_STEPS = 5000`
  budget (engine.ts:230) was never approached: the deepest route's replay consumed 285 steps
  and always found a faithful reconstruction, so `Go back` never silently disappears here.

## Method note

All timings and payload sizes were measured with read-only `node`/`python3` over the real
artifacts in `out/`, using an inline port of `frontend/src/player/engine.ts` +
`evaluator.ts` (same transition order, same `nodeIndex`/`intBounds` call sites, same DFS
replay and budget) so the replay costs reflect the shipped algorithm rather than an estimate.
Wall-clock numbers are from this container's CPU; a phone or older tablet is conventionally
4-6x slower, and I have flagged where I applied that multiplier rather than measuring it.
The reconnect finding is a code trace end to end with line references, not an executed
scenario - hence its label.

---

# Part 2: Import and approve-and-publish legs

## Adversarial review: IMPORT and APPROVE-AND-PUBLISH legs at 746 nodes / 42,085 words

Target artifacts: out/the-ninth-hand.filled.json (746 nodes, 232 endings, Tier-2 stateful,
book 3 of the wyrmreach series), skeletons/16+/the-ninth-hand.json, data/series/wyrmreach/book3.*

Status: COMPLETE

### Moderation is 1,494 strictly-sequential LLM calls for this book; nothing bounds or parallelizes them [VERIFIED]
WHAT: `_run_all_stages` runs Stage 1 (safety) and Stage 2 (readability) **once per node, in a
plain `for` loop, awaited one at a time**, then Stage 3 and Stage 4 once each. There is no
`asyncio.gather`, no semaphore, no batching, no chunking, and no per-story call budget.
WHY: 746 nodes -> 746 safety calls + 746 readability calls + 2 whole-story calls = **1,494
sequential provider round-trips** for one import of the-ninth-hand. Per-call timeout is
`llm_timeout_seconds = 120` (openrouter) / `ollama_timeout_seconds = 300`. At an optimistic
1.5 s/call that is ~37 minutes; at 4 s/call ~100 minutes; a single slow call can legally
consume 120-300 s of that. This is wall-clock inside one `import_filled_story` call, holding
one open `AsyncSession` and one uncommitted Postgres transaction for the whole duration (see
the transaction finding below). It also means one import fans out ~1.5k billable requests: at
`review_openrouter_model = anthropic/claude-sonnet-4.6` with ~300 chars of prose per node the
Stage 1+2 legs alone are cheap per call but the count is the cost driver, and Stage 3/4 each
send the entire 225,812-char corpus (see next finding).
WHERE: src/cyo_adventure/moderation/stages.py:196-216 (Stage 1 loop), :247-268 (Stage 2 loop),
src/cyo_adventure/moderation/pipeline.py:544-575 (stage sequencing),
src/cyo_adventure/core/config.py:423 (llm_timeout_seconds=120), :434 (ollama_timeout_seconds=300),
:527-529 (review_provider/model defaults)
FIX: Bound the per-node stages with a concurrency semaphore (`asyncio.gather` over chunks,
limit ~5-8), and add an explicit per-story call budget + elapsed-time budget that, when
exceeded, records a `BLOCK`/`FLAG` finding ("moderation incomplete") rather than silently
returning a partial report. Batch several nodes per Stage 1/2 call with per-node verdicts in
one JSON response.

### The whole import is ONE Postgres transaction held open across all 1,494 LLM calls, with the Storybook row FOR UPDATE-locked [VERIFIED]
WHAT: `import_cli._run` opens a single `get_session()`, calls `import_filled_story` (gate ->
`persist_storybook` -> full moderation pipeline), then series linkage, and only commits at the
very end (import_cli.py:118). Inside that same transaction, `run_moderation_pipeline` takes
`SELECT ... FOR UPDATE` on the Storybook row (pipeline.py:98) *before* the stages run. So the
row lock and the write transaction are held for the entire multi-tens-of-minutes review run.
WHY: at 746 nodes this is a ~40-100 minute `idle in transaction` session. Concretely:
(a) `supabase/config.toml:50` sets `pool_mode = "transaction"`, and the code has an explicit
transaction-pooler mode (`database_disable_prepared_cache` -> NullPool); under Supavisor/PgBouncer
transaction pooling one server backend is pinned for the transaction's whole life, and any
`idle_in_transaction_session_timeout` or pooler `server_idle_timeout` kills it mid-run,
discarding all 1,494 calls' worth of spend with the story never persisted. (b) `pool_pre_ping`
does not help: the connection is mid-transaction, not idle-in-pool. (c) Because the failure
mode is "exception propagates -> `get_session` rolls back" (import_story.py:99-105,
import_cli.py:220-234), a review-backend hiccup at node 700 of 746 throws away the entire
import; there is no checkpoint, no resume, and no partial-report persistence. Nothing about
this is size-dependent in the code, but at 305 nodes it is a ~20-minute transaction and at 746
it is over an hour, which is where real pooler/keepalive limits start firing.
WHERE: src/cyo_adventure/generation/import_cli.py:92-119,
src/cyo_adventure/generation/import_story.py:135-167,
src/cyo_adventure/moderation/pipeline.py:98,
src/cyo_adventure/core/database.py:161-172, supabase/config.toml:50
FIX: Split the import into two transactions: commit the persisted draft first, then run
moderation in its own short transaction per checkpoint (persist the partial `moderation_report`
incrementally, take the `FOR UPDATE` lock only for the final `submit`/`auto_reject`
transition). Since `publishing.service.approve` already refuses a version with
`moderation_report=None`, a committed-but-unmoderated draft is already safe to leave behind and
resume.

### `run_gate` is a 3.7-second synchronous CPU burn called directly inside `async def` route handlers [VERIFIED]
WHAT: I timed the real artifact: `run_gate(out/the-ninth-hand.filled.json)` takes **3.72 s**
and peaks at ~238 MB RSS on this machine. Three FastAPI `async def` handlers call it inline,
with no `run_in_executor` / `anyio.to_thread`:
- `api/node_edit.py:444` (`edit_node`, every passage edit)
- `api/generation.py:632` (`validate_version`, guardian-callable)
- `moderation/rescreen.py:280` (the rescreen sweep, once per published book)
WHY: 3.7 s of pure-Python CPU inside the single-threaded asyncio event loop **stalls every
other in-flight request** for that whole window: a kid mid-read, another admin's queue load, the
health probe. On the rescreen sweep it is 3.7 s x N published books back-to-back with no yield.
On `edit_node` it is 3.7 s before the LLM re-review even starts, so one passage fix on this
book is a ~6-10 s PATCH; the reviewer will be making dozens of them. `validate_version` is
guardian-reachable, so any guardian can trigger a 3.7 s loop stall on demand for this book (a
trivially cheap self-DoS on the whole API). At 305 nodes this is ~1.5 s; at 746 it is the kind
of stall that trips a container liveness probe.
WHERE: src/cyo_adventure/api/node_edit.py:444, src/cyo_adventure/api/generation.py:632,
src/cyo_adventure/moderation/rescreen.py:280
FIX: Wrap all three in `await anyio.to_thread.run_sync(run_gate, blob)`. Additionally cache the
gate report per `(storybook_id, version)` so `validate_version` returns the already-stored
`validation_report` instead of recomputing, and rate-limit it.

### The admin review surface ships the whole 526 KB blob and renders all 746 passages unvirtualized, with no pagination anywhere [VERIFIED]
WHAT: `ReviewSurfaceView` carries `blob: dict[str, object]` verbatim (the whole story) plus
`flagged_passages`, each re-carrying that node's prose. `get_review_surface` has no `limit`,
`offset`, `cursor`, or node-range parameter. The client then renders every node: `readThrough.reachable.map(...)` followed by `readThrough.unreachable.map(...)`, one `<article>` per
passage, no windowing/virtualization library anywhere in the file.
WHY: I measured the real response by running `build_review_surface` over the real blob with a
synthetic 1,492-finding report (10% flagged): the serialized `ReviewSurfaceView` is
**444,163 bytes** with 75 flagged-passage cards, and the projection itself is cheap (7 ms), so
this is a payload and DOM problem, not a CPU one. The page mounts **746 passage components with
232 ending badges and 1,030 choice rows in one DOM**. That is the surface on which ADR-005's mandatory human approval is supposed to happen.
There is no per-node reviewed/unreviewed tracking, no progress state, no "resume where I left
off", and no way to review in sessions: the single Approve button at the bottom of a
746-passage scroll is the entire recorded human judgment. A reviewer cannot in practice read
42,085 words in one page load, so the realistic outcome is an approval that attests to far less
than it claims.
WHERE: src/cyo_adventure/api/schemas.py:1382-1392 (`blob` in the view),
src/cyo_adventure/api/approval.py:222-285 (no pagination params),
src/cyo_adventure/api/review_surface.py:100-117,
frontend/src/admin/ReviewDetailPage.tsx:346, :534-565 (unvirtualized full render)
FIX: Add node-range pagination to `GET /storybooks/{id}/review` (and stop echoing the whole
blob; send only the passages for the requested window). Virtualize the read-through list.
Persist per-node review progress keyed by `(storybook_id, version, node_id, reviewer)` so a
multi-session review of a 746-node book is possible and the approval record can state what
fraction was actually read.

### The review queue loads every in_review book's full blob just to compute a title and a count [VERIFIED]
WHAT: `get_review_queue` bulk-selects whole `StorybookVersion` rows (`select(StorybookVersion)`)
for every `in_review` storybook, then `build_review_queue_item` -> `build_review_surface` builds
a **full prose index and full finding projection for each** only to derive `title`,
`flagged_count`, `age_band`, `themes`, `content_flags`. `GET /admin/storybooks` does the same
across *every* status.
WHY: with the three wyrmreach books in review that is ~1.3 MB of blob JSON plus ~750 KB of
moderation-report JSONB read out of Postgres and hydrated per queue page-load, to produce a few
hundred bytes per row. `/admin/storybooks` (no status filter) does it for the entire library
including published and archived books, and the same reuse-`build_content_summary`-per-row pattern
is on the **guardian browse** listing (`api/assignments.py:436-441`) and the guardian content
summary (`:231-238`), so it is on a surface hit on every guardian page-load, not just an admin
one. Honest scoping: I measured the projection at ~7 ms and ~250 KB report per book, so the CPU
cost is negligible; the cost is the unbounded row-and-blob fetch, which grows linearly with the
library and has no `LIMIT` on any of these four endpoints.
WHERE: src/cyo_adventure/api/approval.py:312-317, :354-362, :644-664,
src/cyo_adventure/api/review_surface.py:298-308,
src/cyo_adventure/api/assignments.py:231-238, :436-441
FIX: Project the queue in SQL (`blob['title']`, `blob['metadata']['age_band']` as JSONB
expressions) and store `flagged_count` / gating flags as denormalized columns on
`StorybookVersion` at moderation time. Paginate both listings.

### Import silently overwrites the authored series block: declared book_index 3 is replaced by import order, and nothing ever compares the two [VERIFIED]
WHAT: `out/the-ninth-hand.filled.json` and `data/series/wyrmreach/book3.spec.json` both declare
`metadata.series = {series_id: "wyrmreach", book_index: 3, series_entry_node: "n_start",
is_final: false, carries_state: true}`. On `--series-id <uuid>` import, `assign_book_index`
computes `max(book_index)+1` **from the DB** and `embed_series_block` then *replaces* the whole
declared block: `series_id` becomes the DB UUID (not `"wyrmreach"`), `book_index` becomes the
DB-assigned integer, `is_final` is hard-coded `False`, `series_entry_node` is overwritten with
the blob's own `start_node`. There is **no comparison anywhere** between the declared
`book_index` and the assigned one -- I grepped every `book_index` reference in `src/`.
WHY: import order silently becomes the chain order. Import the-ninth-hand (declared book 3)
first and it is stored as book 1; the declared 3 is overwritten with no warning, no log line
naming the discrepancy, and no error. Every downstream consumer then trusts the wrong index:
`api/reading.py:250-255` finds "the next book" by `book_index + 1`, so a reader who finishes the
real book 1 is continued into the wrong story with the wrong carried state, and
`validator/series.py::_check_indices` (SR-2) still passes because the assigned indices are
contiguous 1..N by construction. The declared `is_final` is unconditionally flattened to
`False`, so a series can never be marked closed by authoring. And the authored `series_id`
string `"wyrmreach"` -- the identity the offline cross-book chain validator was run against --
does not survive import, so the offline validation and the stored chain are keyed on different
identifiers.
WHERE: src/cyo_adventure/generation/series_link.py:131-136 (`_next_index` = max+1),
:196-208 (block replaced wholesale, `is_final=False` hard-coded),
src/cyo_adventure/generation/import_cli.py:104-117,
src/cyo_adventure/validator/series.py:113-135 (SR-2 checks contiguity, not declared-vs-assigned)
FIX: In `embed_series_block`, read the blob's declared `metadata.series` first; if it declares a
`book_index` and it does not equal `storybook.book_index`, raise `ValidationError` rather than
overwrite. Preserve the declared `is_final`. Add a `--book-index N` option to the import CLI that
asserts the assigned index, so a 3-book series is imported deterministically instead of by
whatever order the operator happened to run the commands in.

### `--job` (the provenance route) and `--series-id` (the linkage route) are mutually exclusive, so a series book cannot have both [VERIFIED]
WHAT: `import_cli._run` returns immediately on the `--job` branch (`return await
resume_manual_fill(...)`, line 93-94); the series-linkage block at :104-117 is unreachable from
it, and the CLI help says so outright ("Ignored with --job"). `import_story.py` contains zero
references to series (grepped: no matches).
WHY: `--job` is the only route that records skeleton provenance (`skeleton_slug`, needed for
recency-weighted skeleton picking) and the only route that runs the Stage 1 fidelity gate
against the origin skeleton. `--series-id` is the only route that links a book into a series at
all. For the three wyrmreach books the operator must pick one: either the books are
fidelity-gated and provenance-stamped but **have `series_id`/`book_index` NULL** -- which means
`api/reading.py:250` (`if book.series_id is None or book.book_index is None: return`) never
offers a continuation, `publishing/service.py:299` skips `validate_series` entirely, and the
whole state-carrying chain silently degrades to three unrelated standalone books -- or they are
linked but ungated and unstamped. There is no combination that produces a correct Tier-2 series.
And because `--series-id` is silently *ignored* rather than rejected with `--job`, an operator
who passes both gets the broken outcome with a zero-exit "imported <id>" success message.
WHERE: src/cyo_adventure/generation/import_cli.py:52-59, :92-119,
src/cyo_adventure/generation/import_story.py (no series linkage),
src/cyo_adventure/api/reading.py:250
FIX: Move series linkage into `import_filled_story` (after moderation, before return) so both
routes get it, and thread `series_id` through `ImportRequest`. At minimum, make `--job
--series-id` a hard argument error instead of a silent ignore.

### There is no path to republish a corrected mid-chain book, and re-importing one permanently breaks SR-2 [VERIFIED]
WHAT: `LEGAL_TRANSITIONS` has exactly one edge out of `published` (`archive`) and **none out of
`archived`**. `submit` is only legal from `draft`/`needs_revision`. So once book 2 is published
there is no transition that returns it to review, and therefore no way to approve a v2 of it.
WHY: on a 3-book chain, errata are found *while reviewing later books* -- that is the normal
case, and it is exactly what a 746-node book 3 that depends on book 2's ending state will
surface. The only workaround is importing the fix as a new storybook id, and
`assign_book_index` then gives it `max+1 = 4` while the old book 2 still holds index 2 and a
non-null `current_published_version` (so `_series_chain_docs` still counts it, deliberately, per
the archived-sibling `#EDGE` note at publishing/service.py:160-165). The chain becomes indices
{1,2,3,4} for 4 members and passes SR-2 only if all four are published -- but the replacement
occupies slot 4, i.e. *after* book 3, so `api/reading.py`'s `book_index + 1` continuation walks
1 -> 2(stale) -> 3 -> 4(the fix), permanently. SR-2 gives no signal because it only checks
contiguity, never that indices reflect narrative order.
WHERE: src/cyo_adventure/publishing/state_machine.py:69-78,
src/cyo_adventure/publishing/service.py:148-171,
src/cyo_adventure/generation/series_link.py:131-136
FIX: Add a `published -> in_review` (or `published -> needs_revision`) revision edge guarded by
"a newer draft version exists", so a corrected version of an already-published book can be
re-approved in place under the same `book_index`. Alternatively make `book_index` explicitly
assignable so a replacement can claim the slot it is replacing.

### `moderation_report` is the one JSONB payload with no byte budget, and it is the only one that scales with node count [VERIFIED]
WHAT: `persist_storybook` byte-checks `blob` and `validation_report` against
`_MAX_BLOB_BYTES = 2_000_000` before any row is added, and `embed_series_block` re-checks the
blob via `ensure_blob_within_budget`. `moderation_report` is assigned with no check at all:
`version_row.moderation_report = report.to_dict()` (pipeline.py:180), and `node_edit.py`'s
`_merge_moderation_report` rewrites it unchecked too.
WHY: `moderation_report` is precisely the payload whose size is `O(nodes)`. For this book it holds
**>= 1,494 findings**, each carrying a free-text `message` taken verbatim from the review model's
`reason` field, which is bounded only by `_MAX_REVIEW_TOKENS = 1024` (~4 KB) per finding. A
merely verbose reviewer produces a multi-megabyte JSONB write that the guarded columns would have
rejected, and that report is then re-serialized in full on **every** `get_review_queue` /
`get_review_surface` / `edit_node` call. The `blob` guard (526 KB vs a 2 MB ceiling) gives ~4x
headroom, which is comfortable; the unguarded column is the one at risk.
WHERE: src/cyo_adventure/moderation/pipeline.py:180,
src/cyo_adventure/generation/persistence.py:100-102, :129-144,
src/cyo_adventure/api/node_edit.py:301-364,
src/cyo_adventure/moderation/review_provider.py:28, src/cyo_adventure/moderation/pipeline.py:54
FIX: Run `_check_byte_budget(report.to_dict(), field="moderation_report")` before the assignment
in both writers, and truncate `Finding.message` at construction (e.g. 500 chars) so per-node
report growth is bounded by node count alone.

### Book 3 narrows `renown` to min=3, so carried state from book 2 is silently clamped upward and low-renown outcomes are erased [VERIFIED]
WHAT: `startContinuation` seeds carried variables by **name** and clamps carried ints into the
*receiving* book's declared bounds, skipping any type mismatch, with no signal on either. The
actual declared bounds across the chain:
- book 1: `renown` int 0..3 (initial 0)
- book 2: `renown` int 0..5 (initial 2)
- book 3: `renown` int **3..5** (initial 3)
WHY: `renown` is book 3's own reputation gate, and a reader can legitimately finish book 2 with
`renown` 0, 1, or 2 (book 2 starts it at 2 in a 0..5 range). `clamp` then rewrites that to **3**
-- the chain's maximum-reputation floor -- so every low-reputation playthrough of book 2 arrives
at book 3 indistinguishable from a high-reputation one. That is the exact promise a
`carries_state: true` Tier-2 series makes, silently broken, and the erasure happens in the
*client* engine, not on a surface anyone reviews. Two more concrete corruptions in the same
mechanism:
1. Book 2 declares `deep_charts` and `oath_sworn`; book 3 declares neither. `startContinuation`
   iterates `story.variables` (the receiving book's), so those two carried values are **dropped
   without trace**. `oath_sworn` is precisely a book-2 commitment book 3 should honor.
2. Book 3 declares `second_iron` initial **True**, but book 2 declares it initial `False` (earned
   in play). A reader who finishes book 2 without earning it carries `false`, which *overrides*
   book 3's declared premise; a reader who starts at book 3 directly gets `true`. The same 746
   nodes are read under two contradictory premises, and the prose can only be right for one.
Nothing validates any of this: `validator/series.py`'s SR-1..SR-7 check series id, index
contiguity, entry-node existence, the final flag, win-ending presence, and `carries_state`
uniformity -- **there is no rule that compares variable names, types, or bounds across a
state-carrying chain**. And the backend has no continuation logic at all (`grep -n
'continuation\|carried' src/cyo_adventure/player/engine.py src/cyo_adventure/api/reading.py`
returns nothing), so this is client-only with no server-side cross-check.
WHERE: frontend/src/player/engine.ts:119-153 (`startContinuation`), :31-40 (`clamp`), :21-29,
frontend/src/reader/ContinueSeries.tsx:65,
data/series/wyrmreach/book2.spec.json / book3.spec.json (variable blocks),
src/cyo_adventure/validator/series.py:243-273 (SR-6/SR-7 are the only state-carry rules)
FIX: Add an SR rule to `validate_series`: for a `carries_state` chain, every variable declared in
book N must be declared in book N+1 with the same type, and book N+1's `[min,max]` must contain
book N's, else ERROR. Report dropped variables as at least a WARNING. Make `startContinuation`
record a per-variable carry audit (`carried` / `clamped` / `dropped` / `type-mismatch`) into the
reading state so a corrupted carry is visible rather than silent, and surface it on the review
surface for a series book.

### Nothing gates entry into a mid-chain book: book 3 can be assigned and opened cold, and archiving book 2 leaves a hole in the chain the reader hits at runtime [VERIFIED]
WHAT: `/v1/library` returns `series_id` and `book_index` but performs no prerequisite check;
`api/assignments.py` has **zero** references to series (grepped). A guardian can assign
the-ninth-hand (book 3) to a child who has never opened books 1 or 2, and the reader opens it
via the normal `start(story)` path, not `startContinuation`, so it initializes from book 3's
declared initials (`renown: 3`, `iron_key: true`, `second_iron: true`, `knows_compact: true`).
WHY: two distinct runtime holes a 3-book chain exposes that a 2-book chain does not:
1. **Cold mid-chain start.** 746 nodes of prose whose Layer-2 configuration space is anchored on
   book-2 outcomes are read by someone with no book-2 history. The declared initials make it
   *mechanically* valid (the gate passes), which is exactly why nothing catches it: the failure is
   narrative, and the only surface that could catch it is the human review of book 3, which has no
   indication it is book 3 of anything (`ReviewSurfaceView` exposes no series fields at all --
   `api/schemas.py:1382-1392`).
2. **G8 archive punches a hole.** `archive` only flips status; it does not clear
   `current_published_version`, so `publishing/service.py:148-171` deliberately keeps the archived
   book in the chain for SR-2 contiguity. But `get_series_next` requires
   `sibling.status == "published"` and returns `next: null` otherwise
   (api/reading.py:257-259). So archiving book 2 makes the chain *dead-end at book 1* while book 3
   stays fully published, assignable, and readable, with `book_index 3` and a
   `series_entry_node` that expects carried state that can now never be produced. There is no
   check on archive that warns "this book is mid-chain and N later books depend on it", and no
   cascade.
WHERE: src/cyo_adventure/api/reading.py:250-259, src/cyo_adventure/api/assignments.py (no series
logic), src/cyo_adventure/api/library.py:204-223, :391-395,
src/cyo_adventure/publishing/service.py:410-431 (`archive` is unconditional),
src/cyo_adventure/api/schemas.py:1382-1392 (review view carries no series context)
FIX: On `archive`, refuse (or require an explicit override flag) when the book has a published
sibling at a higher `book_index` in the same series, and surface the dependent books in the
error. In `assignments`, when assigning a book with `book_index > 1` in a `carries_state` series,
either require the prior book to be assigned/completed or warn the guardian explicitly. Add
`series_id`/`book_index`/`carries_state` to `ReviewSurfaceView` so the human approver knows they
are approving book 3 of a state-carrying chain.

### The soft-gate auto-repair is structurally impossible at this size: it must emit the whole story but is capped at 32k output tokens [VERIFIED]
WHAT: `attempt_repair` serializes the **entire** story blob into one prompt and instructs the
model to "Return ONLY the full revised story JSON, same schema", bounded by
`_MAX_REPAIR_TOKENS = 32_000`. Measured on the real artifact: compact JSON is **405,742 bytes ~=
101,000 tokens**. The required output is therefore ~3.2x the output cap.
WHY: the repair fires whenever the report has any `FLAG` and no hard `BLOCK`
(pipeline.py:166) -- and with 746 nodes running through two per-node stages whose Stage 1
fail-safe is `FLAG` on any unparsable verdict, at least one FLAG is near-certain. The model
cannot physically return the story, so the output is truncated mid-JSON, `json.loads` raises,
`attempt_repair` returns `None`, and the pipeline proceeds -- after burning a ~101k-token input
call. It is pure waste with a straight face: `_repair_is_adoptable` and
`_repair_preserves_identity` are elaborate protections for an outcome that can never occur on a
book this size. Worse on the Ollama leg: the stream byte ceiling is `max_tokens * 16 = 512,000`
bytes, and the story blob alone is **526,306 bytes**, so a model that *did* try to emit the full
revision trips the ceiling and raises a **transient `ProviderError`** -- which
`import_filled_story` deliberately does not catch (import_story.py:99-105), so the caller's
session rolls back and **the entire ~40-100 minute import is discarded**.
WHERE: src/cyo_adventure/moderation/repair.py:93-108,
src/cyo_adventure/moderation/pipeline.py:55 (`_MAX_REPAIR_TOKENS = 32000`), :166-178,
src/cyo_adventure/generation/providers/ollama.py:268 (`max_bytes = max_tokens * 16`)
FIX: Make repair per-node: re-prompt only the flagged nodes' bodies and splice the revised prose
back into the blob (which also removes the need for the identity/structure backstops). Add a
guard that skips repair entirely, with a recorded finding, when
`len(json.dumps(blob)) / 4 > max_tokens`, so an impossible repair is never attempted.

### The Ollama review leg never sets `num_ctx`, so the two whole-story stages silently judge a truncated fraction of the book [VERIFIED for the missing setting; SUSPECTED for the exact truncation behavior]
WHAT: Stage 3 (coherence) and Stage 4 (engagement) concatenate **every** node's prose into a
single prompt: measured **267,483 chars ~= 67,000 tokens** for this book. The Ollama adapter's
request body sets `options.num_predict` (output budget) but **no `num_ctx`**
(`grep num_ctx src/cyo_adventure/generation/providers/*.py` -> only `num_predict`). Ollama's
default context window is a few thousand tokens unless `num_ctx` is set, and it truncates the
prompt to fit rather than erroring.
WHY: `review_provider = "ollama"` with `review_ollama_model = "qwen2.5:14b"` is a supported
production configuration (core/config.py:527-529). On it, the only two whole-story checks in the
entire pipeline receive a small truncated slice of a 42,085-word book and return a confident
`pass`. Because Ollama truncates rather than failing, there is **no error, no warning, and no
finding** -- the report says the story passed coherence when coherence was never evaluated. This
is the silent-partial-coverage safety hole in its worst form: it looks identical to a clean pass.
If the truncation drops the system-prompt end of the context, the "return ONLY JSON" and
instruction-hierarchy framing go with it, and `_parse_verdict`'s `fail_safe=PASS` for stages 3-4
converts the resulting garbage into another silent pass. I did not run a live Ollama call, hence
SUSPECTED on the precise truncation semantics; the missing `num_ctx` and the 67k-token prompt are
both verified from code and measurement.
WHERE: src/cyo_adventure/moderation/stages.py:298-302 (coherence prompt), :346-350 (engagement),
src/cyo_adventure/generation/providers/ollama.py:169 (`"options": {"num_predict": max_tokens}`),
src/cyo_adventure/core/config.py:527-529
FIX: Send `options.num_ctx` explicitly, computed from the prompt size, and have the adapter
**fail loudly** when the estimated prompt exceeds the model's context rather than letting the
server truncate. Independently, cap the whole-story stages: chunk the story into
context-sized windows and require every window to return a verdict, so "coherence passed" can
never mean "coherence saw 3% of the book".

### THE SAFETY HOLE: one classifier error stops Stage 0 for every remaining node, and the only signal is a single ADVISORY [VERIFIED]
WHAT: `_screen_all_nodes` loops nodes sequentially calling OpenAI Moderation and Google
Perspective **once per node each**. The instant either raises `ClassifierUnavailable`, its
`*_reason` is set and the guard `if openai_key and openai_reason is None` skips that classifier
**for every remaining node**. The docstring states this outright: "is not retried for the
remaining nodes". The entire compensating signal is one whole-story
`Finding(verdict=ADVISORY, category="classifier_degraded", node_id=None)`.
WHY: this is size-dependent and lands squarely on this book. Stage 0 makes **2 x 746 = 1,492
sequential third-party HTTP calls** for one import. Perspective's default per-project quota is on
the order of 1 QPS and OpenAI Moderation rate-limits per minute; a burst of 746 back-to-back calls
is exactly the shape that trips a 429. A 429 at node 50 means **nodes 51-746 (93% of the book, ~39,000
words) are never bright-line screened**, and the resulting report is indistinguishable from a
fully-screened clean one except for a single ADVISORY line sitting among ~3,000 findings on an
unpaginated review page. The bright-line categories Stage 0 exists to catch
(`sexual/minors`, `self-harm/instructions`, `illicit/violent`) are precisely the ones that must
not be sampled. And Stage 0's own short-circuit at pipeline.py:542 (`if report.has_hard_block:
return`) means a Stage-0 block skips the LLM stages entirely -- so the two layers do not back each
other up on the nodes Stage 0 skipped; those nodes still get the LLM safety stage, but the
bright-line net simply is not there for them.
Compounding it: the degraded advisory carries `score=None`, and `admin_surfaces` never hides an
unscored finding, so it does at least reach the admin view -- but as an advisory, not a gate. The
report's `summary.hard_block`/`soft_flag` are both unaffected, so `submit()` and `approve()` both
pass with 93% of the book unscreened by Stage 0.
WHERE: src/cyo_adventure/moderation/classifiers.py:115-131 (`if ... and openai_reason is None`),
:64-75 (`_degraded_finding`, ADVISORY, score=None), :151-158 (docstring stating the behavior),
src/cyo_adventure/moderation/pipeline.py:529-542,
src/cyo_adventure/moderation/thresholds.py:184-205
FIX: Track per-node classifier coverage. If any node was not screened by a configured classifier,
emit a `FLAG` (not ADVISORY) so the story cannot reach `in_review` clean, and record the
unscreened node count and ids in the finding. Add bounded retry with backoff plus a concurrency
limit so a rate limit is absorbed rather than abandoning the rest of the book. At minimum, make
`submit`/`approve` refuse a version whose report declares incomplete Stage-0 coverage.

### Stage 0 adds 1,492 more sequential third-party calls, so one import is ~2,986 network round trips [VERIFIED]
WHAT: Combining the two loops: Stage 0 is 2 calls/node (classifiers.py:115-131) and Stages 1-2 are
2 calls/node (stages.py:197, :248), plus 2 whole-story calls. For 746 nodes that is
**1,492 + 1,494 = 2,986 strictly sequential network round trips** in a single
`import_filled_story` call, inside a single open Postgres transaction.
WHY: sets the real wall-clock and failure-probability floor for the import leg. Even at a
generous 500 ms mean per call it is ~25 minutes; any one of the 2,986 calls raising a
non-`ClassifierUnavailable`, non-`ValidationError` exception (a `ProviderError` from the review
backend, which the pipeline documents as intentionally propagating) discards the whole run. With
~3,000 independent chances to fail and no checkpointing, a successful import of this book is a
coin flip against provider reliability rather than a deterministic operation.
WHERE: src/cyo_adventure/moderation/classifiers.py:115-131,
src/cyo_adventure/moderation/stages.py:197-216, :248-268,
src/cyo_adventure/moderation/pipeline.py:529-575,
src/cyo_adventure/generation/import_story.py:99-105 (documented propagate-and-roll-back contract)
FIX: Same as the concurrency/checkpointing fixes above; additionally make the moderation pipeline
resumable by persisting per-node findings as they are produced, so a retry re-screens only the
nodes without a stored finding.

### The Stage 1 fidelity gate is one ~120,000-token prompt with a 512-token answer, undelimited, and it fails open [VERIFIED]
WHAT: `run_semantic_fidelity_check` builds a **single** prompt containing, for every FILLed node,
the skeleton beat description plus the final prose plus every choice's original->final label pair,
then asks for one whole-story verdict with `_MAX_FIDELITY_TOKENS = 512`. Measured for this book:
all 746 skeleton nodes carry `<<FILL ...>>` beats (171,845 chars) and the fill is 225,812 chars,
plus 1,030 choice-label pairs -> **~480,000 chars ~= 120,000 tokens in one prompt**. Every parse
or contract failure returns `None`, which the caller reads as "pass".
WHY: this is the gate that runs on the `--job` route (`resume_manual_fill` ->
`_finalize_resume` -> `run_stage1_gate`), i.e. the cyo-author skill route these books were
authored through. At 120k tokens the prompt exceeds the context of the default review model on the
Ollama leg outright and sits near the ceiling on frontier models; a 512-token answer is being asked
to adjudicate fidelity across 746 beats and 1,030 labels, which cannot produce anything but a
coin-flip global verdict. And every degradation path is fail-open: non-str, non-JSON, or
`verdict != "flag"` all return `None` -> `violations` empty -> job status `"passed"`. So on this
book the Stage 1 fidelity gate reports a pass whether or not it ran.
Separately, and unlike every prompt in `moderation/stages.py`, this prompt embeds untrusted
generated prose **raw**: `lines.append(f"Prose: {body}")`, with no `<untrusted_passage>` wrapper,
no `_sanitize_delimited` call, and `_FIDELITY_SYSTEM` carries no `_UNTRUSTED_SUFFIX`. The
instruction-hierarchy hardening that stages.py documents as `#CRITICAL: security` is simply absent
here, on a prompt whose entire input is model-generated text.
WHERE: src/cyo_adventure/moderation/fidelity_review.py:226-261 (single prompt, raw `Prose:`),
:49 (`_MAX_FIDELITY_TOKENS = 512`), :31-47 (`_FIDELITY_SYSTEM`, no untrusted suffix),
:246-259 (three fail-open returns),
src/cyo_adventure/generation/import_story.py:453-479 (the caller that maps this to "passed")
FIX: Chunk the fidelity check into bounded node batches and require a verdict per batch, with a
missing/unparseable batch verdict recorded as a violation rather than a pass. Wrap every embedded
beat and prose in `<untrusted_passage>` via `_sanitize_delimited` and append `_UNTRUSTED_SUFFIX`
to `_FIDELITY_SYSTEM`, matching stages.py.

### `carries_state` and the family boundary are also taken from the DB Series row, not the blob, and neither is checked against the import [VERIFIED]
WHAT: Same overwrite mechanism as the `book_index` finding, but with worse consequences.
`embed_series_block` sets `carries_state=series_row.carries_state` (series_link.py:201),
overwriting the `carries_state: true` all three wyrmreach blobs declare. The only production
path that creates a `Series` row is `story_requests/service.py::_create_series`, which derives
`carries_state = age_band not in _EPISODIC_BANDS` from the **series row's own** `age_band`. There
is no CLI or admin endpoint to create a Series row for an offline-authored series at all (only
`scripts/seed_dev_data.py`, `scripts/seed_series_catalog.py`, `scripts/series_e2e_local.py`), so
the `--series-id` an operator passes must come from an in-app story request whose band may not be
the books' band. Nothing compares `Series.age_band` to the blobs' `metadata.age_band`, and
nothing compares `Series.family_id` to the `--family` the books were imported under (no check
constraint on the `Series`/`Storybook` pair either).
WHY: if the Series row's `age_band` is `"3-5"` or `"5-8"`, `carries_state` is `False`, and import
silently rewrites all three 16+ books to `carries_state: false`. SR-7 then **passes** (the chain
is uniformly false), SR-6 passes (16+ is not a young band), so `approve` raises nothing. At
runtime `get_series_next` returns `carries_state: false` (api/reading.py:299) and
`ContinueSeries.tsx:65` therefore omits the carried var state entirely -- the whole
state-carrying campaign degrades to three episodic books, every book-2 outcome discarded, with no
error anywhere in the import, the approval, or the read. The family mismatch is the other half:
a `--series-id` from family A with `--family B` links B's books into A's series with no
complaint, and `_series_chain_docs` then builds a cross-family chain.
WHERE: src/cyo_adventure/generation/series_link.py:196-208,
src/cyo_adventure/story_requests/service.py:432-441,
src/cyo_adventure/db/models.py:243-263 (no cross-table family constraint),
src/cyo_adventure/api/reading.py:299, frontend/src/reader/ContinueSeries.tsx:65,
src/cyo_adventure/validator/series.py:243-273 (SR-6/SR-7 cannot see the mismatch)
FIX: In `embed_series_block`, compare the blob's declared `carries_state` against
`series_row.carries_state` and raise on mismatch instead of overwriting; likewise compare
`series_row.age_band` to `blob.metadata.age_band` and `series_row.family_id` to
`storybook.family_id`. Add a `create-series` admin CLI/endpoint so an offline-authored series does
not have to borrow a UUID from an unrelated story request.

### Addendum to the `--job` / `--series-id` finding: the standalone route also disables the leaf-diversity guard [VERIFIED]
WHAT: `run_leaf_diversity_check` returns `[]` immediately when `version_row.skeleton_slug is None`
(leaf_diversity.py:161-163), and `import_cli` documents that a standalone `--family` import leaves
`skeleton_slug` NULL on purpose (import_cli.py:96-101). `--series-id` only works on that
standalone route.
WHY: so the route that is the *only* way to link a series is also the route on which the
anti-template guard never runs. For three books filled from the same authoring pipeline, template
convergence across books is exactly the defect that guard exists to catch, and it is structurally
unreachable for any series book.
WHERE: src/cyo_adventure/moderation/leaf_diversity.py:161-163,
src/cyo_adventure/generation/import_cli.py:96-101, :104-117
FIX: Same fix as the parent finding (move series linkage into `import_filled_story` so `--job` can
carry it), which restores `skeleton_slug` and the ATG guard for series books.

### `POST /admin/rescreen` runs the whole sweep synchronously in one HTTP request: ~2,700 classifier calls plus ~11 s of event-loop-blocking gate for these three books [VERIFIED]
WHAT: `trigger_rescreen` awaits `rescreen_published_books` inline and returns the full summary in
the response body; its own docstring says "Runs synchronously (see the module docstring for why no
async/enqueue path is offered in this first cut)". The default scope is **every** published book
(`select(Storybook).where(status == published)`, narrowed only if the caller supplies
`storybook_ids`). Per book it runs `run_gate` (measured 3.72 s for the 746-node book) plus
`run_classifiers` over every node -- the same 2-calls-per-node sequential loop as Stage 0.
WHY: with the three wyrmreach books published (305 + 305 + 746 = 1,356 nodes) a single unscoped
rescreen is **~2,712 sequential third-party HTTP calls plus ~11 s of blocking CPU** inside one
request. That exceeds any normal reverse-proxy/ingress read timeout by orders of magnitude, so the
admin gets a 504 while the sweep continues server-side against a request-scoped session that the
disconnected client's unit-of-work may then roll back -- meaning the sweep's `RESCREEN_*` events
and verdicts can be silently discarded after the full provider spend. The `run_gate` calls also
block the event loop, so kid readers stall for ~11 s. And because it reuses `run_classifiers`
verbatim, the "one failure abandons the rest of the nodes" hole above applies here too, with
`require_classifiers` not even passed (defaults False), so an unconfigured classifier does not
even produce the degraded advisory on this path.
WHERE: src/cyo_adventure/api/rescreen.py:121-155,
src/cyo_adventure/moderation/rescreen.py:161-165 (unscoped default), :280 (`run_gate`),
:319-325 (`run_classifiers`, no `require_classifiers`),
src/cyo_adventure/moderation/classifiers.py:115-131
FIX: Enqueue the sweep on RQ and return a job id, streaming/polling the summary; or require an
explicit `storybook_ids` scope and cap the node count per request. Pass
`require_classifiers=settings.environment != "local"` to match the pipeline. Move `run_gate` off
the event loop.

## Checked and fine

- `persist_storybook`'s 2 MB JSONB byte budget: the real blob is 526,306 bytes (405,742 compact),
  so ~4x headroom; the guard runs before any row is added, and `embed_series_block` re-checks.
  No per-node inserts anywhere -- one `Storybook` row plus one `StorybookVersion` row, two
  flushes (generation/persistence.py:104-124).
- `assign_book_index`'s concurrency handling itself is sound: savepoint + unique-constraint retry,
  with a correct non-retry on non-unique `IntegrityError` (series_link.py:94-128). The problem is
  *what* index it picks, not how it picks it safely.
- `validate_series` SR-2 vs the G8 archive: `archive` leaves `current_published_version` set and
  `_series_chain_docs` deliberately includes archived siblings, so archiving book 2 does not break
  chain contiguity for later approvals (publishing/service.py:160-171). That specific 3-book
  hazard is handled.
- `publishing/service.approve`'s no-unmoderated-publish invariant holds at this scale: both
  `submit` and `approve` refuse `moderation_report is None`, and `approve` is the only writer of
  `status="published"` (service.py:86-92, :287-289, :307).
- `buildReadThrough` has no node cap and covers every kept node exactly once across
  reachable/unreachable, including duplicate-id nodes; it ignores choice conditions, which is
  over-inclusive (safe) for a Tier-2 book rather than under-inclusive
  (frontend/src/admin/reviewDiff.ts:172-209).
- `anti_template_verdict` / leaf-diversity is O(nodes) paired, not O(nodes^2); 746 nodes is not a
  cost problem there (src/cyo_adventure/diversity/leaf.py:239+).
- The review surface's corrupt-report isolation is per-row on both the queue and the guardian
  browse listing, so one bad report cannot deny review or browse of every other book
  (approval.py:403-416, assignments.py:426-450).
- `_repair_preserves_identity` / `_repair_is_adoptable` are correct as written (id + tier + node
  count, plus a full gate re-run); they are simply unreachable on a book this size, per the repair
  finding above.
