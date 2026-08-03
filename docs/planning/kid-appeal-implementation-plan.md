---
title: "Kid-Appeal Implementation Plan"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Wave-sequenced implementation plan executing the owner decisions D1-D20 from the
  kid-appeal design review: catalog unblockers, rendered-stop reader, choice grammar and tone,
  gamification v1, and media, with acceptance criteria and register linkage."
tags:
  - planning
  - roadmap
  - frontend
  - storybook
  - generation
audience: product-owner, engineering
---

# Kid-Appeal Implementation Plan (2026-08-01)

> **Authority**: decisions D1-D20, recorded in
> [design-review-kid-appeal-2026-08-01.md](design-review-kid-appeal-2026-08-01.md) section 8, plus
> the ratified artifacts [ADR-025](adr/adr-025-additive-storybook-schema-versioning.md),
> [ADR-026](adr/adr-026-rendered-stop-flow.md), ADR-011 section 10 (choice grammar),
> [gamification-recommendation-2026-08-01.md](gamification-recommendation-2026-08-01.md), and
> [media-budget-recommendation-2026-08-01.md](media-budget-recommendation-2026-08-01.md).
> **Wave structure approved as D19.** Each wave is separately shippable; waves 2-4 may overlap
> once wave 0 lands. Effort tags are relative (S under a day's focused work, M a few days, L a
> week-plus) and are planning aids, not commitments.

## Decision ledger (one line each; full text in the design review section 8)

| ID | Ruling |
|---|---|
| D1/D10 | Every stop ends in a choice, implemented as rendered-stop flow (ADR-026); graph keeps linear beats |
| D2/D15 | Band-graded choice grammar, ratified as ADR-011 section 10 |
| D3/D11 | Existing catalog grandfathered; a cell retires its grandfathered skeletons once it has 1+ compliant skeleton |
| D4 | Kid notifications are in-app only |
| D5/D18 | Tone axis approved; starting vocabulary per the P-B table, expansion is a future push |
| D6/D12/D16/D17 | Gamification: collection + badges + ring + active reading time; ring varies by band per P-A; ring-1 only |
| D7/D13/D20 | Media as optional format fields; budgets per the media recommendation; SFX-only audio v1 with mute |
| D8/D14 | Second person is the POV standard in all bands; third-person books phase out |
| D9 | Additive-minor schema versioning (ADR-025) |
| D19 | Wave sequencing approved |

## Wave 0: Unblockers (Content workstream, start immediately)

**W0.1 Import and publish the 23 filled books** (`UW-G14`), grandfathered per D11. Run the import
path, take each through the normal admin approve-and-publish gate, assign to the reference
profiles. Feeds the Phase 9 starter-library target (A9). Effort M (mostly review throughput).
*Accept*: catalog count > 0 in production; a kid shelf shows real books.

**W0.2 Ending-valence re-tag audit.** Script lists every negative-valence ending with its prose
for human re-tag, kid bands first (9 + 18 + 71 endings at 3-5/5-8/8-11), teen bands folded into
the `AL-052` content triage. Republished versions ride the normal approval gate. Effort S tooling
+ M review. *Accept*: the star-burst celebration fires on warm try-again endings; badge 7 ("Brave
Reader", wave 3) can trust valence.

**W0.3 Completion response carries the moment.** `POST /completions` returns
`{is_new, found, total}`; `EndingsProgress` renders from the response instead of a racing second
fetch. Files: `api/reading.py::record_completion`, `api/schemas.py`,
`frontend/src/reader/EndingsProgress.tsx`, regenerated client (contract job). Effort S.
*Accept*: reaching a new ending never under-reports; `is_new` distinguishes first finds.

**W0.4 Request-to-storybook link.** New nullable `story_request.resulting_storybook_id` set at
publish; honest status flip on the kid request card; delete the `isLikelyPublished` substring
guess. Migration pays the four-artifact tax (SQL, RLS, cascade, deletion drill). Effort M.
*Accept*: an ordinary one-off request flips to "it's on your shelf" when the book is assigned.

## Wave 1: Reader, stops and loop closure (Phase 4b)

**W1.1 Stop-composition layer** per ADR-026: implemented identically in `player/engine.py` and
`frontend/src/player/engine.ts`, with `schema/conformance/` cases for flow across effects, flow
into endings, loop-back edges inside a run, condition-gated single choices, and back-by-stop.
Memoize the flowed run so `AL-030`'s replay cost does not triple. Bands 8-11+ get flowed prose;
3-5/5-8 keep discrete pages. Effort L (the corpus is most of it). *Accept*: conformance suite
green in both engines; no "Continue" button renders at 8-11+; go-back rewinds one stop.

**W1.2 Route-relative progress** (`AL-029`): per-stop progress display replaces corpus-coverage
percent; aria labels match. Effort S-M, lands with W1.1 since stop counting defines the
denominator. *Accept*: a median read no longer shows 1% then snaps to 100%.

**W1.3 Celebration upgrade.** NEW-ending moment and "you found them all" from W0.3's response;
`AL-028` milestone framing for large-M books with `EndingsProgress` and `EndingsBadge` sharing
one threshold. Effort S-M. *Accept*: first-find, repeat-find, and final-find each render
distinctly; no book shows "1 of 232".

**W1.4 Close the request loop for the kid** (D4: in-app only). Kid-scoped story-ready projection
over `pipeline_event` (`BOOK_ASSIGNED`) using the notifications composer pattern with a child
role gate; profile-picker "new story ready!" pill via a bulk per-profile status endpoint; surface
the stored K19 reflect-back on the request card ("We heard: a dragon who loves pancakes!").
Corrects the `user-journeys.md` pill claim (design review section 6 item 1) either way. Effort M.
*Accept*: from a child's seat, request -> reflect-back -> "being written" -> "on your shelf" is
honest end to end; the picker announces the arrival.

## Wave 2: Content, grammar and tone (Content workstream)

**W2.1 Grammar enforcement for new content** (ADR-011 section 10). Validator rules: choiceless-run
caps for the discrete-page bands (2-3 at 3-5, 2 at 5-8), options-per-choice bounds, per-stop word
guidance at flowed bands; staged advisory first, hard at skeleton promotion once the first
compliant wave exists. Fill-gate check: every choice acknowledged in the immediately following
prose. Effort M. *Accept*: a non-compliant new skeleton is refused at promotion; a fill lacking
acknowledgments is flagged with the offending node ids.

**W2.2 Tone and request defaults.** Tone derivation from screened request text per the D18 table
(default `gentle`, never widening the band's safety envelope); `story_requests/brief.py` unforced:
tone from request, size targeting mid-band instead of `min_nodes`, ending count scaling;
theme-aware skeleton selection scoring `SIMILARITY_TAG_MAP` overlap between request and skeleton
metadata. Effort M. *Accept*: a "funny" request at 8-11 produces a funny-toned brief and a
mid-band book; a cave request draws the cave skeleton over the baking one when both fit the cell.

**W2.3 POV and craft.** Second-person rule in the fill gate for all bands (D14); drafting-guide
rewrite: POV per band table corrected, a craft-for-delight section (recurring image, a laugh per
chapter at young bands, sensory specificity, strong last lines), 3-4 humor/wonder variation axes
added to `generation/variation.py`. Effort S-M. *Accept*: a new fill in third person fails the
gate; the guide and the corpus finally agree.

**W2.4 Genre wave under the new grammar.** Re-scope `UW-G13`'s 36 skeletons with the under-13
genre quota (4-6 speculative/adventure/comedy per kid band: dragons, space, dinosaurs, pirates,
gentle-spooky per tone table, comedy); retire the `the-harrowstone-keep` duplicate or re-derive
it. Deprecation mechanics per D11: a `deprecated` marker plus selection-layer exclusion armed per
cell when the first compliant skeleton lands. Effort L (authoring-heavy, ongoing). *Accept*: each
kid-band cell gains at least one compliant, genre-fresh skeleton; grandfathered selection stops
per cell as that happens.

**W2.5 Scaffold interactions (3-5).** Small design + ADR-025 schema minor for predict/point/answer
beats on choiceless pages; prompt support in the fill templates. Effort M. *Accept*: a 3-5
skeleton can declare scaffold beats and the reader renders them; comprehension-first per the
research appendix.

## Wave 3: Engagement (Phase 4b/4c)

**W3.1 Progress projection.** Kid-scoped `GET /v1/me/progress` computing badges 1-8/10/11,
gallery, and finished-shelf state on read from `Completion`/`Rating`/`pipeline_event` (pure
composer pattern; zero new tables); badge seen-state in IndexedDB. Effort M. *Accept*: badge and
collection state correct against a fixture family with no schema migration.

**W3.2 Gallery and ribbons UI.** Endings Gallery (found cards, silhouetted unfound), Finished /
"Every path walked!" ribbons, badge case off the kid nav, unlock toasts at the ending screen;
profile picker stays number-free (anti-leaderboard line). Effort M.

**W3.3 Active reading time.** Client accumulator (90s idle window, visibility-gated, read-aloud
counts as active), per-day buckets in IndexedDB, idempotent flush to `POST /v1/me/reading-time`,
new `reading_activity_day` table (the one four-artifact migration of this wave), guardian summary
gains minutes/day and days/week. Kids see days, never minutes. Effort M-L. *Accept*: offline
reading accrues and syncs once; deltas are clamped; deletion drill covers the table.

**W3.4 Weekly ring** with the D17 per-band defaults (off at 3-5; goals 2/2/3/3/4/4; teen self-set
within guardian cap; selectable goal capped at 6). Guardian per-profile toggles (ring, badges,
time-capture pause). No reminders anywhere. Effort M. *Accept*: an unfilled week ends with
nothing; a filled ring celebrates once; toggles behave per the recommendation's section 4 table.

**W3.5 Trailing badges.** Badge 9 ("Wish Come True") once W0.4 is live; badge 12 ("Forty Days of
Stories") once W3.3 accrues. Effort S.

## Wave 4: Media (new ADR + pilot)

**W4.1 Illustration ADR and 3-5 pilot.** New ADR amending ADR-017's scope for per-node art at
3-5 (per-scene at 5-8 next), with the automated image-moderation precondition ADR-017 names for
beyond-per-item-review volume; schema minor for optional node image fields (ADR-025); pipeline
reuses the covers path (metadata-only prompts, R2, human gate) with a 1536px/150KB optimize
profile per D20. Pilot: the seven 3-5 skeletons. Effort L. *Accept*: a pilot book renders art on
every page offline within the 8MB budget; no image bypasses moderation + human review.

**W4.2 UI sound effects.** App-bundled SFX (<0.5MB service-worker precache): page turn, choice
tap, ending chime; mute control in the reader chrome (D7), per-profile persisted; respects
`reduce_motion` families' expectations (quiet by default when reduce_motion is set). Effort S-M.

**W4.3 Offline budget enforcement and polish.** `navigator.storage.estimate()` gate before
downloads, 250MB default / 500MB hard cap with own oldest-unpinned eviction (D20);
Add-to-Home-Screen gating of the offline-library promise on iOS (extends ADR-002); PWA manifest
colors corrected to the parchment palette. Effort M.

## Wave M: Measure (owner-gated)

The naive-user session with real children (`UW-M02`, the `.claude/skills/naive-ux-check` prompts)
runs once wave 1 is testable and **before** the request-page reshape (`UW-I01`) and the gated
reader-UX items (`UW-I02`) ship. It additionally validates: the grammar's felt pacing at each
band, the ring framing ("goal" versus "chore"), and the scaffold-interaction concept at 3-5.
Findings route to `docs/qa/naive-ux-reports/` and become wave-2/3 adjustments.

## Plan defaults adopted (owner may veto any of these)

1. **Badge visibility**: family-visible within ring 1, as the gamification recommendation
   proposes (consistent with rating chips). No per-profile privacy toggle in v1.
2. **`reading_activity_day` retention**: day-grain buckets retained 12 months, then rolled into
   running totals (lifetime days-read survives); entered into the ADR-018 counsel bundle and the
   privacy model's data classification.
3. **SFX default**: sound on with a one-tap mute in the reader chrome; guardian per-profile off
   switch; quiet default for profiles with `reduce_motion` set.
4. **Weekly goal cap**: 6 days selectable maximum at every band (one guaranteed free day).

## Cross-cutting engineering rules (apply to every wave)

- **Contract**: any backend route/model change regenerates and commits the frontend client in the
  same change (`contract` CI job).
- **Conformance**: any runtime-visible player behavior lands with corpus entries in
  `schema/conformance/` covering both engines (ADR-025 rule 4, ADR-026 rule 5); personalization
  and series-carry corpus gaps (design review 5.3) are paid down with W1.1.
- **Migrations**: every new child-linked table pays the four-artifact tax (SQL + RLS + cascade +
  deletion drill). This plan contains exactly two: W0.4 and W3.3.
- **Schema**: all format additions ride ADR-025 minors; deploy code before authoring content at
  the new minor.
- **Register linkage**: this plan is the phase home for `AL-022` (dual clocks, fold into W1.2/3),
  `AL-027`/`AL-028`/`AL-029`/`AL-030` (waves 1-2), `AL-052` (W0.2), `UW-G13`/`UW-G14` (W2.4/W0.1),
  `UW-I07`/`UW-I08` (W1.4 and the mascot set alongside W3.2), `UW-D04` (error differentiation,
  opportunistic in wave 1), and `UW-M02` (wave M). Update the register rows' phase homes when this
  plan is adopted into the roadmap.
- **Docs**: wave 1 lands the design-review section 6 corrections (user-journeys pill claim, K1
  band-token residual, K19 status resolution); the K19 row resolves via W1.4 shipping the
  reflect-back.

## Out of scope for this plan (explicitly)

Personalization slots beyond the contract-slot data work (blocked on ADR-023 and counsel,
`UW-H03`); recommendation-to-request one-tap for unassigned books (design review Q-item F3, still
an owner decision); ring-2/ring-3 anything for gamification (permanently, per D12); recorded
narration (a future opt-in add-on per the media recommendation); tone vocabulary expansion (D18's
future push); PWA push in any form (D4).
