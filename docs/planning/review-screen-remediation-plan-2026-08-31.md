# Review screen remediation plan

> **Status**: Draft for owner approval | **Created**: 2026-08-31 | **Owner rulings**: 2026-08-31
>
> Implementation plan for making the admin story-review surface reviewable. Supersedes nothing; consumes the
> evidence brief in `tmp_cleanup/.tmp-review-screen-evidence.md` and the owner rulings recorded in section 3.

## 1. Problem

Thirteen books have sat in `in_review` for 40 days with zero progress. The measured reason is not reviewer
neglect: the queue asks for roughly **1,360 screens and 481,000 words** of reading, and the largest book
(`The Harrowstone Keep`, ages 13-16) renders a 259,411px page from a 2.5 MB payload in which
**2.5% of the severity badges carry a decision** and the single real hard block sits 102 screens below the fold.

The gate itself is working. The presentation of the gate is what has stalled.

## 2. Measured basis

Two independent censuses. Neither is estimated; re-derive before citing, do not carry forward.

### 2.1 Rendered-page census (production browser, 2026-08-30/31, read-only)

Full 13-book table in `tmp_cleanup/.tmp-review-screen-evidence.md` section 3. Load-bearing rows:

| Book | Band | Page px | Screens | Words | `Advisory` badges | `Flagged` | `Blocked` |
|---|---|---|---|---|---|---|---|
| The Harrowstone Keep | 13-16 | 259,411 | 250 | 87,622 | 595 | 14 | 1 |
| The Drowned Court | 16+ | 162,146 | 156 | 48,343 | 432 | 0 | 0 |
| The Teddy Bears' Picnic | 3-5 | 8,819 | 9 | 2,191 | 5 | 0 | 0 |

`The Drowned Court` is the pure case: 75 screens of `Flagged passages` containing 430 boilerplate advisories
and **zero human-written findings**.

### 2.2 Stored-report census (production database, read-only, 2026-08-31)

All 31 books carrying a moderation report on their latest version. **Zero are unusable**: no report has
`reviewer_independent: false`, none has `coverage_complete: false`, and no report's findings are entirely
pipeline artifacts. The 2026-08-27 re-moderation sweep cleared the coverage gaps that PR #776 fixed, so the
whole corpus is valid calibration input. Four of the five `archived` books predate the `reviewer` field and are
legacy rows; they are excluded from anything that needs reviewer attribution.

**248 findings, 4,120 node-hits** (a node-hit is one entry in a finding's `node_ids`, which is one rendered
passage article on the review page):

| Source | Verdict | Severity | Findings | Node-hits | Share |
|---|---|---|---|---|---|
| `openai` | advisory | low | 100 | 3,780 | 91.7% |
| `perspective` | advisory | low | 50 | 215 | 5.2% |
| `llm_safety` | flag | medium | 50 | 50 | 1.2% |
| `openai` | advisory | medium | 10 | 22 | 0.5% |
| `pipeline` | flag | high | 1 | 16 | 0.4% |
| `llm_safety` | flag | low | 15 | 15 | 0.4% |
| `llm_engagement` | advisory | (null) | 10 | 10 | 0.2% |
| `pipeline` | advisory | (null) | 5 | 5 | 0.1% |
| `llm_safety` | **block** | high | 3 | 3 | 0.07% |
| `pipeline` | **block** | (null) | 2 | 2 | 0.05% |
| `perspective` | advisory / flag | medium / high | 2 | 2 | 0.05% |

Derived quantities that drive this plan:

- **`LOW` + `ADVISORY` is 150 findings and 3,995 node-hits, 97.0% of all fan-out volume, and contains zero
  gating findings.**
- Everything that gates (`block` or `flag`) is **72 findings across 87 node-hits, 2.1%**. This corroborates the
  independently measured 2.5% badge signal-to-noise on `The Harrowstone Keep`.
- **Five `block` findings exist in the entire corpus.** Three from `llm_safety`, two from `pipeline`. The
  `openai` channel, which produces 92% of the volume, has **never once produced a gating verdict**.
- Findings by status: `in_review` 117 on 13 books (9.0 each), `published` 22 on 13 books (1.7 each),
  `archived` 109 on 5 books (21.8 each). The stuck queue and the volume problem are the same books.

OpenAI advisory node-hits by age band: `3-5` 7, `5-8` 6, `8-11` 210, `10-13` 173, `13-16` 1,745, `16+` 1,661.
Published books are entirely younger bands; the stalled queue is skewed old.

### 2.3 Configuration state

- `moderation_threshold` has **zero rows**, so `ThresholdPolicy` (`moderation/thresholds.py:74`) has always
  resolved to its code default `Threshold(min_verdict=FLAG, min_score=None)` (`:70`) in every lane. The
  band-aware mechanism the owner expected exists and has never been populated.
- `admin_noise_floor` is `0.05`, set 2026-07-08 (`ADMIN_NOISE_FLOOR_KEY` `:175`, default `:181`).
- `_ADVISORY_SCORE_FLOOR = 0.01` (`moderation/classifiers.py:87`), applied per node per category at `:527`.
- `moderation_threshold` exists in `supabase/migrations/20260710000000_baseline.sql:119` with age-band and
  score check constraints but **no unique constraint on `(age_band, category)`**, so an idempotent seed needs
  the constraint added first.

## 3. Owner rulings (2026-08-31)

Recorded verbatim in substance, as the authority for scope:

1. Cutoff scores were intended to **scale by age band**; that is not implemented.
2. Low advisories should be **counted and reachable, not in the default detail view**.
3. **A reviewer is not expected to read the whole book.** The job is catching false positives and false
   negatives.
4. **Unresolved findings must not automatically gate a book.** That judgment is the reviewer's.
5. There must be a way to **send a published book back for review**, specifically so that a threshold change
   can force re-review against the updated metrics.
6. **The current threshold numbers are arbitrary and need calibration.**

Ruling 3 is the one that sets the accountability floor for the whole design: the deliverable is a surface for
**adjudicating findings**, not for reading prose. Ruling 4 forbids any new hard gate on finding disposition.
Ruling 3's false-negative half is load-bearing and is the reason section 5.4 exists.

## 4. The finding that reorders the work

The denoising machinery already exists and is bypassed.

`_rank_and_split` (`api/review_surface.py:519`) already routes `LOW` + `ADVISORY` findings into a
`low_advisory_findings` bucket (`:396`), and `ReviewDetailPage.tsx:728-741` already collapses that bucket behind
a `<details>` element. But the fan-out that builds `Flagged passages` runs **earlier**, at `:345`, and never
consults the split:

```python
target_nodes = view.node_ids or ([] if view.node_id is None else [view.node_id])
...
for nid in target_nodes:
    ...
    flagged[nid].append(view)
```

So the same finding is simultaneously collapsed to one line in `Low-priority advisories` and expanded up to 380
times, each time with the passage's full prose, in `Flagged passages` (`ReviewDetailPage.tsx:643`).

**Consequence for sequencing.** Excluding `LOW` + `ADVISORY` from the fan-out removes 97.0% of the volume, needs
no calibration, needs no re-moderation, and works against the 13 stored reports exactly as they are. Threshold
recalibration is strictly slower and currently blocked on data we do not retain. **The presentation fix must
therefore ship first**, which inverts the ordering proposed before this census existed.

## 5. Calibration

Ruling 6 makes this a measurement task. It is not a guess, and it is partly blocked.

### 5.1 What the stored data can and cannot answer

The merge keeps only the **group maximum** score, and there is no raw-classifier-output table anywhere in the
schema. Therefore:

- **The admin display floor is fully derivable from stored data at zero cost.** It is applied to merged findings
  as persisted (`admin_surfaces`, `thresholds.py:184`), which is exactly the granularity the reports retain. Any
  candidate value can be replayed against all 31 reports offline.
- **Stage-0 per-node floors are not derivable from stored data.** They apply per node per category before the
  merge, and sub-floor scores were never persisted. Stored data can only confirm behaviour at or above 0.01.

### 5.2 Correction to an earlier reading of `UW-C378`

`UW-C378` (ratified 2026-08-25) adopted **per-category** floors: a low floor on `self-harm*`, `sexual*`,
`harassment/threatening`, `illicit`, and a higher floor, indicatively 0.10, on `violence` and
`violence/graphic`. `_ADVISORY_SCORE_FLOOR` stays at 0.01 until that lands.

The production census shows the dominant noise clusters are `violence` with group maxima of 0.40 to 0.45
(`13-16` violence low = 1,160 node-hits, maxima 0.400 to 0.452; `16+` = 1,069 node-hits, 0.083 to 0.453). A
first reading of that was that a 0.10 floor "would barely dent them". **That reading conflates two different
questions and understates the effect.** A group whose maximum is 0.45 survives any floor at or below 0.45, so
the *finding* remains visible in the ranked list, which is correct and desirable. But the Stage-0 floor is
applied per node before merging, so raising it strips individual nodes from `node_ids` and therefore shrinks
the **fan-out**, which is the thing that makes the page unreadable. The ratified direction targets precisely the
right category. Its magnitude is unknown and unmeasurable from stored data.

### 5.3 Instrument

`scripts/capture_stage0_baseline.py` (934 lines) scores a corpus against live Perspective and OpenAI classifiers
and freezes the **raw, un-floored** per-category scores to JSON. It is opt-in, never runs in CI, supports
`--dry-run`, and costs real API calls on effectively free tiers. It captures only; it contains no calibration
logic.

One capture exists: `docs/planning/safety/stage0-baseline-2026-08-01.json`, 135 records (120 clean, 14
adversarial, 1 control), self-describing with git commit and corpus SHA. Its adversarial slice covers **4 of 6
age bands**, because the corpus grew to v1.1 with 6-band coverage on 2026-08-23, after the capture. `UW-C378`
already directs that the v1.1 growth be folded in.

`UW-C378`'s own measurement was never scripted. Its "14 pairs" are 14 distinct (adversarial passage, OpenAI
category) combinations scoring at or above 0.01, derived by hand from 13 scored adversarial passages. Nothing
saved backs it, so reproducing it means re-deriving the per-floor computation from the baseline JSON's raw
scores. Do not confuse `scripts/calibrate_mutation_floors.py` with this work; it calibrates skeleton
anti-clone structural distance for catalog mutation and is a name collision only.

### 5.4 The coupling that constrains every floor raise

`UW-C378` measured that of the candidates {0.01, 0.02, 0.05, 0.10}, **only 0.10 clears the clean-noise target,
and it loses 10 of the 14 adversarial pairs.** That loss is a classifier **recall** cost, and under ruling 3 the
reviewer is the party expected to catch what the classifier misses.

**Therefore the false-negative sampling affordance (`RS-A4`) is a prerequisite for shipping any floor raise, not
an independent improvement.** Raising a floor without it moves risk onto a reviewer who has been given no
instrument for the job. Any plan that ships Track B before `RS-A4` is unsafe, and this is the single hardest
constraint in this document.

### 5.5 Calibration tasks

| ID | Task | Cost | Blocked on |
|---|---|---|---|
| `RS-CAL1` | Replay candidate admin display floors against all 31 stored reports; report surfaced-finding and node-hit counts per candidate per band. Offline, no API calls. | free | nothing |
| `RS-CAL2` | Re-derive `UW-C378`'s per-floor advisories-per-node and adversarial-recall table from the 2026-08-01 baseline JSON as a **script**, not by hand, so the number has an oracle. | free | nothing |
| `RS-CAL3` | Fresh capture against adversarial corpus v1.1 for all 6 bands, plus a production-representative clean sample (section 5.6). | API calls | `RS-CAL2` |
| `RS-CAL4` | Choose per-(band, category) floors against the `RS-CAL3` distribution; record the chosen values, the measured noise, and the measured recall loss together. A floor shipped without its recall cost stated is not calibrated. | free | `RS-CAL3` |

### 5.6 Sampling constraint on the clean corpus

The 120 clean records in the existing baseline are sampled prose, not production content, so they do not measure
production noise. `RS-CAL3` must sample real book nodes per band.

```text
# #CRITICAL: security: a personalized book's prose can carry a real child's name, and the
# calibration capture sends prose to third-party classifiers (OpenAI, Perspective).
# #VERIFY: sample only versions whose storybook has personalization_subject_profile_id IS NULL
# and whose version has personalization_eligible = false; assert the filter in the capture
# script's own test, not in the operator's memory.
```

This is not a new data flow (the pipeline already sends this prose to the same classifiers) but it is a new
*selection*, and the selection is where a personalized variant could be picked up by accident.

## 6. Track A: presentation (ships first, no calibration dependency)

### `RS-A1` Stop fanning low advisories into `Flagged passages`

**Where**: `api/review_surface.py:334-360`.

Exclude `LOW` + `ADVISORY` findings from the passage fan-out. They already reach the client through
`low_advisory_findings` and already render collapsed, so no information is lost; the count and the drill-down
both survive. Measured effect on the stored corpus: 3,995 of 4,120 node-hits removed, 0 gating findings removed.

**The existing `#CRITICAL` comment at `:336-344` must be rewritten in the same change.** It currently asserts
that fanning out across `node_ids` is what stops merged prose from "looking clean to the human approver". That
invariant still holds for gating findings and no longer describes low advisories, so leaving the comment as-is
would leave a `#CRITICAL` marker asserting something false about the code beneath it.

**Acceptance**: a test asserting a `LOW`+`ADVISORY` finding appears in `low_advisory_findings` and **not** in
`flagged_passages`, while a `MEDIUM`+`ADVISORY` and every `flag`/`block` finding still fan out across every
`node_id`. **Prove discrimination by mutation**: revert the exclusion and confirm the new test fails. A test
that passes both ways is not evidence.

### `RS-A2` Invert the screen to findings-first

**Where**: `frontend/src/admin/ReviewDetailPage.tsx`, section order at `:642` (`Flagged passages`) and `:698`
(`Ranked findings`).

**Interaction with PR #795** (`fix/cover-approval-placement`, merged 2026-08-31 with one ordering change made
during review). That PR moves the cover-approval block from the foot of the page to just below the moderation
verdict strip, on the same diagnosis as this task: a decision placed below 250 screens of prose is never found.
Two consequences for this task:

- Its DOM-order test asserts that the cover block falls **somewhere between** `.review-summary` and `Full story`,
  plus that it follows the `classifier_degraded` alert. It does not pin the block immediately after the verdict
  strip, so this task can place `Ranked findings` above the cover block and the test still passes. Keep it that
  way; do not tighten those checks into adjacency assertions, because page order is this task's to decide. The
  one ordering the test does pin, safety alert before cover, is settled and must survive this task.
- As opened, PR #795 placed the cover block **above** the `classifier_degraded` `role="alert"` banner, which
  inverted the right priority: a degraded safety classifier outranks a cover approval. That was corrected before
  merge, in the PR's second commit, and the third assertion above is what keeps it corrected. The page order
  is verdict strip, then safety alerts, then cover approval, then findings triage; this task inserts
  `Ranked findings` into the last slot and must not disturb the first three.

Move `Ranked findings` above `Flagged passages`, and make each ranked finding the entry point to its own
affected passages rather than a sibling of a flat list. `Ranked findings` is **conditionally rendered** today and
disappears entirely on the four books whose findings are all low-severity advisories, meaning the most
decision-useful section is absent exactly on the books a reviewer could clear fastest. Render it unconditionally.

Surface `Finding.score` in the ranked row. A reviewer told "advisory, violence, 0.41" can calibrate; one told
"advisory, violence" cannot.

**Must not be lost** (verified good today): the ranked-finding content model (verdict, severity, category,
human-legible reason, `N affected nodes` disclosure, jump link); the pinned bottom action bar with no
swipe-to-approve, per ADR-005; `asPercent` returning `null` rather than `0%` for an absent measurement; the
cause-neutral unusable-report banner that blocks approval; the branch-shape and ending-tone summary; the
read-only labelling on validator findings.

### `RS-A3` One canonical count

**Where**: `StoryStructureSummary.tsx:228` (local `pluralize`), `:374-376`, plus the queue row and header badge.

`The Teddy Bears' Picnic` currently reports `2 advisories` (queue), `4 findings` (header),
"The moderation gate raised no content concerns" (gate summary), `5 flagged` / `5 advisorys` (overview footer,
pluralization bug at `:376`), and renders 5 articles. The gate summary flatly contradicts the section below it.

Derive every count from one function. State the denominator in the label: distinct findings and affected
passages are different numbers and both are legitimate, but they must be named.

**Acceptance**: a rendered-DOM test, not a source grep. Prettier-wrapped prose defeats source greps, and a
zero result for both a claim and its negation means the probe is broken.

### `RS-A4` False-negative sampling affordance (**prerequisite for Track B**)

Ruling 3 says the reviewer hunts false negatives, and nothing on the screen supports that. Reading 250 screens
is not sampling; it is the failure mode.

Provide a bounded, structured sample: N passages drawn across the branch shape (not sequential), weighted toward
regions with **no** findings, with the band's content expectations shown alongside. The reviewer's question
becomes "did the gate miss anything here", answerable in a known number of screens.

This is the task that makes a floor raise defensible. It is sized as a Track A item because it needs no
calibration input, but it gates Track B.

### `RS-A5` Local per-finding triage

Per-finding disposition with no server round-trip and **no gating effect** (ruling 4): mark a finding reviewed,
so a reviewer 60 findings in can see where they are. Client-local state only, scoped to the book and version.

Deliberately not persisted server-side in this track: there is **no stable finding id**, and
`api/remoderate.py:778` overwrites `version_row.moderation_report` wholesale, so any server-side disposition
would be silently orphaned by the next re-moderation. Server-side triage is `RS-D1`.

### `RS-A6` Edit-path context

**Where**: the `Edit passage` dialog.

It currently offers a bare `<textarea>` plus one `<input>` per choice label, with no finding text, no reason, no
band target, no neighbouring passages, no diff. Show the finding that caused the edit, its reason, and the band
target. A reviewer should never be asked to rewrite prose without being shown what is wrong with it.

### `RS-A7` Queue triage

**Where**: `AdminConsolePage.tsx`.

The queue row shows title, band, `Waiting N days ago`, and a count badge. Nothing says **what** the block is. To
learn that Harrowstone's hard block is one cistern passage, a reviewer must load 2.5 MB and render 10,895 DOM
nodes. Put the top finding's category and reason on the row, and sort by decision weight rather than age.

## 7. Track B: calibrated band-aware floors

**Gated on `RS-CAL4` and on `RS-A4` shipping.**

### `RS-B1` Filter after classification; do not thread the band down

Two designs were assessed. Threading `age_band` into Stage-0 classification touches roughly **7 call sites
across 4 files** (`classifiers.py`'s `run_classifiers`, `_screen_all_nodes`, `_run_openai`, `_openai_finding`,
plus `pipeline.py`, `node_edit.py`, `rescreen.py`), and `story_requests/screening.py` has **no `age_band`
available at all**, being pre-story intake text. Filtering after creation touches essentially one file.

Adopt **filter after classification** via the existing `ThresholdPolicy`, which is already keyed
`(age_band, category)` and therefore satisfies both `UW-C378`'s ratified per-category direction and ruling 1's
band-awareness in one mechanism. Two consumers already call `ThresholdPolicy.surfaces(age_band=..., ...)` on raw
Stage-0 findings: `moderation/rescreen.py:664-676` and `api/review_surface.py:949`. No new plumbing.

Note for the record that threading is *possible*, not blocked: `age_band` is available before the classifier
call (`pipeline.py:1173` validates the story, `:1210` calls the classifier, `:1224` reads the band), and
`_screen_all_nodes` is a plain sequential loop with no `asyncio.gather`, so the reordering would be safe. It is
rejected on cost and on `screening.py` having no band, not on feasibility.

Raw scores stay in the persisted report either way, so the stored report and what a given reader sees can
diverge. They already do, by existing design, between the admin and guardian lanes.

### `RS-B2` Seed `moderation_threshold`, with a unique constraint first

The table has no unique constraint on `(age_band, category)`, so add one before an idempotent
`INSERT ... ON CONFLICT DO NOTHING` seed. Copy the pattern in
`supabase/migrations/20260721230000_seed_provider_model_allowlist.sql`.

```text
# #CRITICAL: data integrity: a conditional migration guard exits 0 having done nothing when its
# subject is ABSENT, not only when already applied, and editing an applied migration is inert
# because Supabase tracks by version.
# #VERIFY: assert post-seed row count against the expected (band, category) product in a test that
# runs against a freshly migrated schema, not against a developer's existing database.
```

### `RS-B3` Keep the admin lane on `admin_surfaces()`

**This resolves the open design question and reverses the tentative preference for retiring the flat floor.**

`admin_surfaces()` guarantees it never hides a `FLAG` or `BLOCK` finding (including a bright-line `BLOCK`
carrying score 0.0) and never hides an unscored finding. `ThresholdPolicy.surfaces()` makes **no such
guarantee**, and its default is `min_verdict=FLAG`. Substituting it into the admin lane while
`moderation_threshold` holds zero rows would **hide every advisory finding admin-wide**, which is a
fail-dangerous change disguised as a refactor.

So: keep `admin_surfaces()` as the admin lane's mechanism and its never-hide guarantees intact, and make only
its **score** band-aware by sourcing `min_score` from `ThresholdPolicy` with the flat `admin_noise_floor`
retained as a global override. That keeps one emergency dial and adds band awareness without inheriting a
`min_verdict` default that hides decisions.

### `RS-B4` Re-moderate the 13 `in_review` books

`scripts/remoderate_books.py` already does this for `in_review`. Run it after `RS-CAL4` lands so the queue is
scored against calibrated floors rather than arbitrary ones. Record before-and-after node-hit counts per book;
that is the evidence the calibration worked.

### `RS-B5` Tests pinned to the current global scalar

Any signature change to `run_classifiers` breaks these regardless of design, so they must be updated in the same
change: `test_capture_stage0_baseline.py::test_artifact_records_the_stage0_thresholds` (asserts the literal
constant) and six cases in `test_moderation_classifiers.py` (`test_openai_near_zero_score_yields_no_finding`,
`test_openai_elevated_score_yields_advisory`, `test_openai_score_at_floor_yields_advisory`,
`test_openai_mixed_scores_filter_per_category`, `test_openai_flagged_non_brightline_bypasses_floor`,
`test_openai_brightline_below_floor_still_blocks`).

## 8. Track C: recall a published book

Ruling 5. Send-back decomposes into four capabilities; three already work.

| Capability | State |
|---|---|
| Re-moderate an `in_review` book | works (`scripts/remoderate_books.py`) |
| Re-moderate a `published` book | works; reports only, never rewrites published prose |
| See which published books came back blocked | **documented gap** (`api/remoderate.py` docstring) |
| Move a published book back to the human gate | **impossible**; needs a new action |

### `RS-C1` Add a `RECALL` transition

**Where**: `publishing/state_machine.py:80-88`. `LEGAL_TRANSITIONS` currently admits exactly one exit from
`PUBLISHED`, which is `ARCHIVE`, and `ARCHIVED` is absorbing.

Add `(Status.PUBLISHED, Action.RECALL): Status.IN_REVIEW`.

**Blast radius traced, and it is cheap.** Every kid-facing content read already gates on `status == "published"`
independently of the assignment row: `api/library.py:494-505` filters the shelf query on
`Storybook.status == _PUBLISHED`, and `:660-670` returns 404 to non-admins when `book.status != _PUBLISHED`.
`archive()` (`publishing/service.py:773-776`) does nothing but flip status and rely on exactly that. So recall
needs no new revocation machinery, and **assignment rows survive**, which is what makes recall recoverable in a
way archive is not.

Two consequences to state in the endpoint's own docstring rather than discover later:

- A `catalog`-visibility book recalls from **every** family, because visibility is ANDed with status.
- An **already-synced offline copy cannot be reached.** There is no push channel;
  `frontend/src/offline/revocation.ts` reconciles only on the next successful `/v1/library` fetch. This is
  pre-existing and shared with `archive`, so recall does not introduce it, but it means **neither recall nor
  archive is an incident-response tool** and neither should be documented as one.

`REMODERATABLE_STATUSES` (`api/remoderate.py:291`) is pinned against `LEGAL_TRANSITIONS` by an admission rule
(both `SUBMIT` and `AUTO_REJECT` absent for that status). Adding a `PUBLISHED` hop does not change
`published`'s membership, but the pin's test must be re-run to confirm rather than assumed, and
`_allow_repair_for` (`:232`, `#CRITICAL: security`) must be checked against the new arrival path into
`in_review`.

### `RS-C2` Published-books-with-a-fresh-verdict surface

The gap the `remoderate.py` docstring already names as "a real gap and a real feature". Needed for ruling 5 to
be usable: after a threshold change, an admin must be able to see which published books now carry a block
without opening each one. Pairs with `RS-C1`; a recall action with no way to find recall candidates is inert.

### `RS-C3` Orphaned pending cover approvals

The same structural gap as `RS-C2`, discovered while reviewing PR #795, and already live in production.

Cover state on the latest version of all 31 books, measured 2026-08-31:

| Status | `none` | `failed` | `pending_review`, URL present, 0 approvals |
|---|---|---|---|
| `in_review` (13) | 12 | 1 | **0** |
| `published` (13) | 9 | 2 | **2** |
| `archived` (5) | 4 | 0 | **1** |

Two consequences, and the second is the one that matters:

- **The cover block renders nothing for any book in the review queue.** Zero of the 13 `in_review` books have a
  cover in `pending_review`. Repositioning it improves the discoverability of something that never appears there,
  which is why PR #795 is low-urgency rather than wrong.
- **Two published, readable books have an unapproved cover.** Only `cover_status == "ready"` reaches a child's
  library card (`covers/service.py::approve_cover`, `#CRITICAL`), so those two books show kids no cover while an
  approval waits that nothing surfaces. The admin queue lists only `in_review`, so no placement change inside
  `/admin/review/:id` can help: nobody opens that page for a published book.

Fold into `RS-C2`'s surface rather than building a second one. The generalisation worth stating in that
surface's design: **any decision attached to a book the queue no longer lists is invisible**, whether it is a
fresh moderation block or a pending cover, and the fix is one list of outstanding decisions across all
statuses, not per-decision placement tuning.

## 9. Sequencing

```text
RS-A1 ──► RS-A2 ──► RS-A3 ──┐
                            ├──► RS-A5, RS-A6, RS-A7   (independent, any order)
RS-A4 ──────────────────────┘
   │
   │  (RS-A4 is a hard prerequisite: section 5.4)
   ▼
RS-CAL1, RS-CAL2 ──► RS-CAL3 ──► RS-CAL4 ──► RS-B1, RS-B2, RS-B3 ──► RS-B4

RS-C1 ──► RS-C2        (independent of A and B; do not ship RS-C1 without RS-C2)
```

`RS-A1` alone is measured to remove 97.0% of the volume. If only one thing ships, ship that.

Track C is independent but internally ordered: recall without a candidate-finding surface gives an owner a
button and no way to know when to press it.

## 10. Open decisions for the owner

1. **Does `RS-A5` stay client-local, or is server-side per-finding triage (`RS-D1`) in scope?** Server-side needs
   a stable `finding_id` in the report schema plus a decision about what happens to dispositions when
   `remoderate.py:778` rewrites the report. Recommendation: client-local now, `RS-D1` as a separate register row.
2. **How large is the `RS-A4` sample?** A defensible answer needs the false-negative rate, which nothing
   currently measures. Recommendation: start at a fixed 15 passages per book, and treat the number as
   provisional until `RS-CAL3` gives a basis.
3. **Do the 5 `archived` books get re-moderated?** They hold 109 of the 248 findings and four lack reviewer
   attribution. Archive is absorbing, so they cannot re-enter review without `RS-C1`. Recommendation: leave them;
   they are not reader-facing.

## 11. Linkage obligations

Per project `CLAUDE.md`:

- Every task above needs a `UW-C*` row in `docs/planning/unscheduled-work-register.md` or a phase home in
  `roadmap.md` before implementation starts. `RS-B1` through `RS-B4` extend the existing `UW-C378`, which is
  already ratified; they should cite it rather than duplicate it.
- Any lesson this work produces goes to `docs/planning/authoring-lessons-log.md`, validated by
  `uv run python scripts/check_lessons_log.py`. `AL-625` is `UW-C378`'s existing lesson and is the precedent.
- New feature proposals must cite the capability-register IDs they serve
  (`docs/planning/capability-register.md`). Track C in particular changes an admin capability and needs one.
