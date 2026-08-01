---
purpose: >
  Design and architecture review focused on one question: what would make the
  app and its stories more appealing to the children who read them. Grounds
  every finding in shipped code or committed content, separates net-new
  findings from work the registers already track, and respects the standing
  ADR constraints (privacy, social boundary, cover-art scope).
component: frontend, storybook, generation, story_requests, validator, api, skeletons
source: >
  Four parallel review passes (kid-facing frontend, story content pipeline,
  engagement loops and architecture, planning-doc survey) over the repo at
  v0.55.x, 2026-08-01, with spot verification of load-bearing claims.
status: draft
audience: product-owner, engineering
---

# Kid-Appeal Design and Architecture Review (2026-08-01)

## Purpose and method

This review asks one question of the whole system: **would a child pick this app up twice?** It covers
four surfaces in parallel: the kid-facing frontend, the story content pipeline (skeletons, prompts,
personalization, art), the backend engagement loops (progress, notifications, recommendations,
ratings), and the architecture that either enables or blocks iterating on any of the above. Every
finding cites the code or content it rests on. Findings that the planning registers already track are
labeled with their `UW-*` / `AL-*` / debt IDs so this document adds priority and framing, not
duplicate intake rows.

**Summary judgment**: the safety, correctness, and offline architecture are genuinely strong, and the
warm parchment design system, the endings tracker, read-aloud, and the kind error copy are real kid-UX
assets. But the system is currently optimized end to end for *passing the gate*, not for *delight*.
The catalog's kid half is one narrow genre lane, the prompts never ask for fun, most pages offer no
real choice, the child who requests a story is never told it arrived, and the reward for finishing a
20-minute read is three CSS glyphs. Almost all of the highest-leverage fixes are content and
feedback-loop work, not new infrastructure.

---

## 1. What is already strong (do not re-litigate)

- **Design system**: `frontend/design-system/` is a real token system (warm storybook palette, 18px
  base type, dark mode with contrast ratios documented in comments, 44px tap floors, twin
  reduced-motion rules driven by both the OS and a per-profile flag).
- **Kind, kid-first copy**: "Hmm, that PIN didn't work. Give it another try!", the "ask a grown-up"
  escape after 3 wrong PINs, mascot-fronted error and empty states (K12).
- **Reader fundamentals**: go-back undo built explicitly because "kids mis-tap constantly"
  (`frontend/src/reader/Reader.tsx:277`), valence-aware ending celebration, read-aloud with word
  highlighting and a local-voice-only guard for personalized text, dedication overlay.
- **Offline honesty**: IndexedDB shelf with "No internet. These books are ready to read.", versioned
  DB migrations, revocation reconciliation (K10).
- **Architecture enablers**: a pure player kernel with a cross-implementation conformance corpus
  (`schema/conformance/player_traces.json` run by both engines), compile-time API contract parity,
  an append-only event log with a pure notification-composer projection over it, GZip on story blobs.
- **Safety posture**: three-gate publish path, PII egress guard that hard-fails rather than redacts,
  no third-party SDKs in the kid context.

---

## 2. Content appeal: the biggest gap is what the stories are

### 2.1 The under-13 catalog is a single genre lane (net-new, highest content leverage)

The kid-facing catalog is 22 skeletons (bands 3-5, 5-8, 8-11) out of 61. Every 3-5 and 5-8 title is
domestic or nature realism: *The Lost Mitten*, *Puddle Jumping Day*, *The Teddy Bears' Picnic*,
*Baking Day with Grandma Vole*, *The Tide Pool Rescue*, *The School Garden Mystery*. Across all three
kid bands there are **zero** dragons, magic, dinosaurs, space, pirates, superheroes, sports, gentle
spooky, or comedy skeletons; only three touch speculative genre at all.

Meanwhile the diversity vocabulary exists precisely because children ask for those things:
`diversity/similarity_vocab.py:23-37` documents that "none of the 132 curated `metadata.themes` is a
value in the echo map"; kids name concrete subjects (dragon, space, pirate) and the catalog is tagged
with abstract virtues (courage, friendship, community). A child who asks for a dragon story today
gets a tide-pool tree wearing dragon paint, or has their dragon "set aside."

**Recommendation**: make the next skeleton wave (`UW-G13`, 36 planned skeletons) explicitly
genre-quota'd for the kid bands: 4-6 speculative/adventure/comedy skeletons per band before any other
growth. This is authoring work with no schema or pipeline change, and it converts directly into
request-to-story satisfaction. Also note one slot of apparent variety is fake: `13-16/the-sunken-temple`
and `13-16/the-harrowstone-keep` are the same 550-node tree re-skinned (identical ending histograms).

### 2.2 The kid bands got the less immersive point of view (net-new)

`templates/drafting_guide.md:95-112` mandates second person, present tense ("Address the reader as
'you'"). Measured against the 23 filled stories in `out/`: the 13-16/16+ books comply (15-57
"you"-per-1000-words), while the 3-5/5-8/8-11 books are third person with named animal protagonists
(0-6.6). So the children, the readers for whom "YOU are the hero" is the core pitch of a
choose-your-own-adventure, are the ones reading about someone else, and the drafting guide is
violated by the entire kid half of the corpus.

**Recommendation**: decide the POV rule per band, write it into `drafting_guide.md`'s band table, and
enforce it in the fill gate. Either direction is defensible per band; the current state (a guide that
says one thing and a corpus that does another) is not. Note the interaction with 2.6: third-person
kid books are actually the *easier* target for hero-name personalization, because a named protagonist
is a name-shaped hole.

### 2.3 More than half of all pages offer no choice (net-new; extends AL-027)

Measured across all 61 skeletons: 52-61% of non-ending nodes in the kid bands have exactly one
choice (70% at 13-16), and mean branching is ~1.5 everywhere. The interactive promise of the format
is delivered on roughly two of every five pages; the rest are "Continue" taps.
`validator/band_profile.py` floors (`min_decisions` 1-4 per story; breadth floor 8% of nodes) are low
enough to permit an almost linear book. `AL-027` already observes that nothing constrains the
*typical* path; this finding is the per-page version of the same problem.

**Recommendation**: add a validator advisory (later, hard rule) capping consecutive single-choice
nodes (e.g. no more than 2 in a row for 8-11 and below) and raise the per-story decision floor.
Cheap, measurable, and it directly changes how the app feels in the hand.

### 2.4 Nothing in the pipeline asks for the story to be fun (net-new)

Across all 10 generation templates and the 270-line drafting guide there are zero occurrences of
humor, funny, silly, joke, laugh, delight, playful, or whimsy. Every word of craft guidance is a
constraint: budgets, depth, FK grade, schema, what not to change. The 10 variation axes
(`generation/variation.py`) are explicitly "not a content lever," and none of them is humor, wonder,
suspense, or surprise. The `.claude/skills/cyo-author` quality bar is entirely mechanical. The
pipeline therefore produces exactly what it optimizes for: safe, on-budget, structurally valid, and
flat.

**Recommendation**: add a positive craft section to `drafting_guide.md` (a memorable recurring image,
a laugh per chapter at the young bands, sensory specificity, a strong last line per ending) and 3-4
new variation axes oriented at humor and wonder. This is prompt work; the deterministic gate is
unaffected.

### 2.5 Every child-initiated request is forced to the smallest, gentlest legal book (net-new)

`story_requests/brief.py` hardcodes, for every child request regardless of what the child asked for:
`tone="gentle"` (line 206), `tier=1` (no state mechanics), `structure_pattern=BRANCH_AND_BOTTLENECK`,
and `target_node_count = band.min_nodes` / `ending_count = band.min_endings` (lines 178-179), the
floor of the band, not its middle. A kid who asks for a scary story, a funny story, or an epic gets
"gentle," the smallest legal book, with the fewest legal endings. Separately, skeleton selection
(`generation/skeleton_match.py::candidates_for_cell`) filters only on `(band, length, style)` and
weights by inverse recency: it is theme-blind, even though `SIMILARITY_TAG_MAP` already maps request
premises and skeleton themes into one comparable space for the differentiation directive.

**Recommendation**: three bounded changes. Derive tone from the request text (screened, banded);
target the middle of the band envelope rather than the floor; score skeleton candidates by theme
similarity to the request so a cave/ocean request draws *The Cave of Echoes* rather than *Baking Day
with Grandma Vole* reskinned. All three sit behind the existing safety gates.

### 2.6 Personalization is built, vocabularied, tested, and wired to exactly one skeleton

Eleven personalization fields, six closed vocabularies, sentinel substitution, a dedication overlay,
an opt-in per-profile flag, and a PII guard all exist. But exactly **one** slot in the entire
skeleton library is declared `kind: "personalizable"` (`skeletons/10-13/the-midnight-museum.contract.json`);
`personalization_values.py:161-164` admits the feature is latent. The corpus being second person at
the teen bands is *why* hero names fail to land there (`DedicationOverlay.tsx:10-14`: 11 of 30
stories never name the hero).

**Constraint to respect**: ADR-023 is Proposed and blocked (Stage A gate fired STOP at 3.3% sentinel
survival; counsel gate `UW-H03`), and K20 stays ❌ until it is Accepted. The recommendation here is
the upstream data work only: declare `personalizable` HERO slots across the other 34 contracts so the
already-shipped ring-1 plumbing has something to bind when ADR-023 unblocks. Do not ship new
child-PII surface ahead of the ADR.

### 2.7 Ending valence is miscoded, which suppresses the celebration kids do earn (net-new)

Sampled from committed fills: `out/the-clover-and-the-butterfly.filled.json` ending `e_bee_setback`
is tagged `valence: "negative"` but its prose ends "But Clover was happy. She went back home."
`out/the-lantern-festival.filled.json` "Oops, Bouncing Berries" is tagged negative for prose that
ends in laughter and "time to try again." `Reader.tsx` keys the star-burst celebration on
`valence !== 'negative'`, so these plainly happy endings render without it. Kid bands carry 9 (3-5),
18 (5-8), and 71 (8-11) negative-tagged endings, many of which are warm try-again beats. Related:
`AL-052` already flags ending-mix skew in 6 filled books, and the teen catalog is 1,846 negative
endings out of 2,229 (one book is 147 deaths out of 150 endings), which combined with 68-70%
single-choice nodes reads as a corridor that kills you at the end.

**Recommendation**: audit and re-tag kid-band ending valences (cheap data pass, immediate UX effect);
fold the teen death-ratio question into the `AL-052` content triage.

### 2.8 The 3-5 band's readability target fights read-aloud quality (net-new)

FK grade 1.0 with a ±1.0 window (tightest of any band) produces the committed style: "Clover is a
little kitten. She sat in a sunny garden. A blue butterfly flew past!" Six consecutive 5-7 word
sentences, with a tense flip. Books at this band are read *to* the child; real picture-book prose
uses longer rhythmic sentences, repetition, and rhyme, which FK penalizes. ADR-011 itself notes 3-5
has no research basis and is product-defined.

**Recommendation**: for 3-5 (and partially 5-8), replace the FK target with a read-aloud-oriented
rubric in the prompt (rhythm, repetition, page-turn hooks) and keep FK as a loose advisory ceiling.

---

## 3. Reader experience: the moment-to-moment feel

### 3.1 Age-band theming is ~90% dead code (net-new)

`design-system/src/band-tokens.css` defines 8 tokens across three tiers; only `--band-reader-text`
(3 consumers) and `--band-reader-leading` (1) are ever read. All four motion tokens, `--band-gap`,
and `--band-tap-min` have zero consumers (verified by grep: no `var(--band-motion-*)` or
`var(--band-tap-min)` anywhere outside the definition file). The 8-11/10-13 "adventurer" tier sets
only motion tokens, so it renders byte-for-byte identically to the neutral teen tier, and the file's
header cites `frontend/src/kid/ageBand.ts`, which does not exist. K1 is marked delivered in the
register with a residual note about `--band-tap-min` only; the real residual is larger.

**Recommendation**: either consume the tokens (the two animation files even carry comments explaining
they routed around them) or delete the dead tiers and correct K1's register note. A 9-year-old's and
a 15-year-old's reader currently differ only in font size.

### 3.2 The reader drops the book's identity at the door (net-new)

`Storybook.title` is never referenced anywhere under `frontend/src/reader/`, and `cover_url` is used
only by `BookCard`. The illustrated cover a kid tapped vanishes the instant the book opens: no cover
on the opening passage, no title in the chrome, no cover on the ending screen (whose heading falls
back to a bare "The End"). Showing the cover as a title page and again at the ending is pure frontend
work with data already in hand, and it makes every generated cover earn twice.

### 3.3 The core interaction has almost no feedback (net-new)

Tapping a choice, the single most repeated act in the app, produces a 120ms background-color change
on touch devices (the `translateX` affordance is hover-only, and hover never fires on tablets).
There is no transition between passages (new text replaces old; only the scroll is smoothed), no
sound, no haptic, and the whole app owns 10 `@keyframes`, two of which are duplicate mascot bobs.
A page-turn or fade transition, a satisfying press state, and an optional soft page sound (respecting
`reduce_motion` and a mute) are small, self-contained wins. Related bug: every choice renders with
`aria-pressed="false"` because `ChoiceButton` defaults `selected=false` and the reader never passes
it, exposing plain buttons as unpressed toggles to screen readers.

### 3.4 The payoff for finishing is thin, and the app cannot tell a new ending from a re-run

The entire reward for a 20-30 minute read is three star glyphs and a mascot bob. The server knows
whether a completion is new (`api/reading.py::record_completion` dedupes on the PK) and discards that
fact; the frontend then re-fetches counts in a race that can under-report the ending just reached
(`EndingsProgress.tsx` documents it, and the persona audit lists it). There is no "you found a NEW
ending!", no "you found them all!" moment, and the `Ending` model carries no metadata to celebrate
with: no rarity, no secret flag, no badge, nothing beyond `{id, valence, kind, title}`.

**Recommendation**: have `POST /completions` return `{is_new, found, total}` and render from the
response (fixes the race and enables the NEW-ending moment in one change); add optional
`rarity`/`is_secret` to the ending block when the schema-evolution work in §5.1 lands; then an
endings-gallery screen becomes the natural collection surface. Interacts with `AL-028` (the "found 1
of 232" inversion at large M): milestone framing should be designed once for both surfaces.

### 3.5 Identity and polish gaps a kid notices (net-new, batchable)

- **Fonts**: system faces only (Georgia + Segoe UI); no display face for "Who's reading?", no
  dyslexia-friendly option, in an app that invests heavily in early readers.
- **Kid-controlled personalization**: a kid cannot pick their avatar (intentional, #65), but also
  cannot pick an accent color or shelf name; `tokens.css:70-74` already reserves berry/gold "for
  upcoming kid-surface accents." A per-profile accent is one token indirection away and carries no
  privacy surface.
- **PWA manifest**: `theme_color: '#1d3557'` / `background_color: '#f1faee'` are leftover
  template values matching nothing in the parchment palette, so the installed app's splash and
  status bar are cold navy/mint around a warm app.
- **Mascot**: one static pose does five jobs (error, empty, loading, welcome, celebration);
  `Mascot.tsx` self-describes as placeholder pending the curated set (`UW-I08`). Even three poses
  (happy, oops, sleepy) would change the feel.
- **Landing page**: the kid door is a 30px outline icon plus the words "Kids / Start reading"; a
  pre-reader has to parse text to find their way in.
- **Reader chrome**: six control clusters sit above the story on a phone, plus the floating theme
  toggle; `reader.css:20-23` concedes it outgrows a phone row. An auto-hiding chrome (reappear on
  tap) would give the story the screen.
- **Copy tone is single-band**: exactly one copy set spans ages 6-16; "ask a grown-up" appears in
  6+ places and is right at 6, patronizing at 15. `data-age-band` is already on the shell; copy can
  branch on it.

### 3.6 Progress and time signals mislead (tracked: AL-022, AL-028, AL-029)

Already filed and worth elevating as a set, because all three lie to the kid at the exact moments
that drive replay: the progress bar measures corpus coverage so a median read shows 1% then snaps to
100% (`AL-029`); a 42,000-word book advertises "14 min" because `estimated_minutes` is the
fastest-finish clock (`AL-022`); and the endings tracker inverts into discouragement at large M
("1 of 232 found", dot row silently dropped above 10) (`AL-028`). These three plus §3.4 form one
coherent "honest, motivating progress" work package.

---

## 4. Engagement loops: the app never talks back to the kid

### 4.1 The kid is never told their story arrived (highest single engagement fix)

Both notification surfaces are hard-gated guardian-only (`api/notifications.py:199,417`); the
composer for `BOOK_ASSIGNED` writes "...is ready on {child}'s shelf" and delivers it to the parent.
On the kid side, `RequestStory.tsx::isLikelyPublished` guesses published status by substring-matching
`proposed_series_title` against shelf titles; its own `#ASSUME` block records that there is no
backend field linking a request to the storybook it produced, so every ordinary one-off request reads
"being written" forever, even after the book is on the shelf (persona audit 1A). The profile-picker
"new story ready!" pill is documented as shipped in `user-journeys.md` and is not built
(`ProfilePickerPage.tsx:64`; persona audit 2B). K19's reflect-back is persisted server-side but the
kid UI shows none of it (persona audit 2A, register status contested).

The child does the asking (K11 shipped), waits through three human gates of unbounded duration, and
receives nothing at any step. For a kid, this is the difference between magic ("I wished for a story
and it appeared!") and a void.

**Recommendation** (mostly already on the tier-3 agenda; this review ranks it first among engagement
work): add `story_request.resulting_storybook_id` at publish time; flip request status honestly;
surface the K19 reflect-back ("We heard: a dragon who loves pancakes!"); build the picker pill via a
bulk status endpoint; and add a kid-scoped projection of `BOOK_ASSIGNED` over the existing event
substrate. The notification architecture (pure composers over an append-only log, SSE transport
already running) makes the kid feed a role gate plus a second composer table, not new plumbing.

### 4.2 No cross-book progress exists for the kid, and the data is already computed (net-new)

Per-book "3 of 7 endings" is the ceiling of kid-visible progress. Books finished, total endings
found, and last activity are already aggregated in `GET /families/me/reading-summary`, which
explicitly 403s a child token (`reading_history.py:418`, correctly, as a guardian rollup). A
kid-scoped variant ("You've finished 5 books and found 22 endings!") is nearly free and is the
foundation for any collection mechanic. Streaks, badges, and stickers have zero code, zero schema,
and zero event types today, but `Completion.found_at` plus the event log are sufficient substrate to
compute them retroactively without new writes. Any such feature must stay first-party and
anonymized-analytics-free per ADR-018; nothing about a local reading streak conflicts with that.

### 4.3 Paths are received and destroyed (tracked: reader-path-engagement-design, UW-C10)

The client sends the full path on every save and the server overwrites it
(`api/reading.py::_apply_body`). No re-read count, no "you took a different path this time," no
furthest-point marker, and on the authoring side `AL-019` stands: no reader outcome ever reaches an
author. `docs/planning/reader-path-engagement-design.md` is a complete, privacy-reviewed design for
exactly this and is unbuilt, blocked on four owner decisions. This review's contribution is
priority: the same table that powers author analytics powers kid-facing replay features ("try a
different path" hints), so it pays twice.

### 4.4 Ratings and flags are dead ends from the kid's seat (partially tracked: U6)

A rating produces one CSS pulse, cannot be cleared (U6), is captured on the shelf rather than at the
ending screen (the moment of peak feeling), and feeds only siblings' chips, never anything the rater
sees. A kid's "this scared me" flag (K15) returns a reassuring toast and then nothing, ever. Small
closures: allow clearing a rating; offer the star row on the ending screen too; when a flag is
resolved, let the kid's next session show "a grown-up looked at this. Thank you for telling us."
(This stays inside ADR-016: it is system feedback to the same child, not a social channel.)

### 4.5 Recommendations cannot recommend anything new (net-new, needs an owner decision)

`_visible_books` intersects candidates with the caller's own assigned shelf, so a chip can only
decorate a book the kid already has; for a single-child family with no connections the endpoint
returns `[]` permanently. The signal is exclusively "sibling rated ≥ 4." Ring 3 is unbuilt (S12,
post-launch). If discovery-by-recommendation is wanted sooner, the bounded option that respects
ADR-015/ADR-016 is: let a ring-1/ring-2 recommendation surface an *unassigned but published* book to
the kid as a request-one-tap ("Cousin Maya loved The Cave of Echoes. Ask for it?"), which routes
through the guardian consent gate exactly like any other request. Structured data only; no free
text; the three-ring boundary is untouched.

---

## 5. Architecture: what blocks or enables the above

### 5.1 The storybook format is closed for extension, and this sits in front of every rich-media idea

Every model in `storybook/models.py` is `extra="forbid"` (10 occurrences), the JSON schema sets
`additionalProperties: false` throughout, and `Storybook._check_schema_version` requires exact
equality with `SCHEMA_VERSION = "2.0"`. Bumping to "2.1" to add `Node.image_url` would reject every
already-published blob; adding a field without bumping hard-fails old backends. There is no
additive-minor rule, no extension bag, no blob migration path. The one mitigation: the frontend TS
types are structurally open, so cached offline blobs and old clients tolerate unknown fields; the
strictness is entirely server-side.

**Recommendation**: before any per-node art, audio, or ending-metadata feature, land a small format
policy: minor versions are additive-optional, the server accepts `2.x` within a declared range, and
the JSON-schema validator gets per-minor variants. This is a prerequisite ADR-sized decision, and it
unblocks §3.4, §5.2, and any future rich-media work at once.

### 5.2 In-story illustration needs a new ADR, and the young bands are the bounded place to start

ADR-017 explicitly scopes art to one cover per version and says revisiting per-passage illustration
requires a new ADR; K8's residual (pre-reader picture support beyond covers) is open and unowned. The
covers pipeline already proves the org can produce child-safe, styled, textless art with a human
gate. A 3-5 band book is 11-32 nodes and 3-5 estimated minutes: illustrating one image per node (or
per bottleneck scene) is a bounded cost, and ADR-018's constraints are already handled by the cover
path (metadata-only prompts, no child PII to the image provider). ADR-017's own amendment clause
must be honored: at per-node volume, per-item human review stops scaling, so an automated
image-moderation pass becomes a precondition. Recommendation: write the ADR now, pilot on the seven
3-5 skeletons, keep the field optional per §5.1 so nothing else moves.

### 5.3 Player duplication tax on every runtime-visible feature

Engine, evaluator, and personalization each exist twice (plus `replay.py` a third traversal); the
conformance corpus covers engine and conditions but not personalization or series-carry, which are
held in sync by prose comments. Any new runtime behavior (a conditional image, an SFX trigger, ending
rarity) must be written twice and needs a corpus entry or it silently drifts. Recommendation: extend
`schema/conformance/` to personalization and series-carry before adding new runtime features, and
treat "corpus entry included" as review policy for player changes.

### 5.4 Smaller frictions, noted not urgent

- The assignment gate is the third manual adult action before a kid sees a book; an approved,
  published story that nobody assigned is invisible. A default-assign-on-publish option per profile
  (guardian-controlled) would remove the most forgettable step. (Interacts with `A9` starter
  library: 12 curated stories, 4 per band, so a new child never sees an empty shelf; that item is
  already planned for Phase 9 and the empty-catalog reality of `UW-G14` makes both moot until
  import/publish happens.)
- `GET /library` is unpaginated and `api/schemas.py` is a 2,516-line hot file; new kid surfaces are
  cheap to write but land in high-contention modules.
- New child-linked tables carry the known four-artifact tax (SQL migration, RLS policy, cascade,
  deletion-drill test); `reader-path-engagement-design.md` already itemizes it.

---

## 6. Documentation corrections found during review

1. `docs/architecture/user-journeys.md` (Act 5 and the shipped/planned table) claims the
   profile-picker book-status pill is shipped; `ProfilePickerPage.tsx:64` documents it as deferred.
   The doc is wrong and should be corrected or the pill built (§4.1).
2. K1's capability-register note lists only `--band-tap-min` as residual; per §3.1 the entire motion
   and gap tier of band tokens is unconsumed and the referenced `ageBand.ts` does not exist.
3. K19 is marked delivered; the kid UI shows none of it (already on the persona-audit tier-3 agenda
   as "ship it or downgrade").
4. `13-16/the-sunken-temple` and `13-16/the-harrowstone-keep` are structurally identical; the
   catalog counts should treat them as one tree until one is re-derived.
5. ADR-011 cites `docs/planning/research/` as the home of its empirical basis (JHM 2019 and the
   four-source reconciliation); that directory does not exist in the repo. The underlying data is
   unrecoverable from the repository as committed; fix the citation or commit the research notes
   (found 2026-08-01 during the D1 research review, section 8).

---

## 7. Ranked recommendations

Ordered by expected impact on kid appeal per unit of effort. "Tracked" means an existing register row
already covers it and this review adds priority; "new" means no register row exists yet.

| # | Recommendation | Section | Status | Effort |
|---|---|---|---|---|
| 1 | Import and publish the 23 filled books; empty catalog blocks everything | 5.4 | tracked `UW-G14` | S |
| 2 | Close the request loop: `resulting_storybook_id`, honest status, K19 reflect-back surfaced, picker pill, kid-scoped "story ready" event | 4.1 | partially tracked (persona tier-3) | M |
| 3 | Genre-quota the next skeleton wave: dragons, space, dinosaurs, pirates, comedy for under-13 | 2.1 | new (shapes `UW-G13`) | M |
| 4 | Fix the celebration path: completion response returns `is_new`, NEW-ending moment, valence re-tag audit, milestone framing with AL-028 | 3.4, 2.7 | new + tracked `AL-028` | S-M |
| 5 | Unforce child-request defaults (tone, mid-band size, ending scaling) and make skeleton selection theme-aware | 2.5 | new | S-M |
| 6 | Add craft-for-delight guidance and humor/wonder variation axes to the prompts | 2.4 | new | S |
| 7 | Choice-tap and page-transition feedback; `aria-pressed` fix; auto-hiding reader chrome | 3.3, 3.5 | new | S-M |
| 8 | Validator rule against consecutive single-choice nodes; raise decision floors | 2.3 | new (extends `AL-027`) | S |
| 9 | Kid-scoped cross-book progress endpoint; groundwork for streaks/badges on the event log | 4.2 | new | M |
| 10 | Format-evolution policy ADR (additive minor versions), then in-story illustration ADR piloted on the 3-5 band | 5.1, 5.2 | new (K8 residual) | M-L |
| 11 | Consume or delete the band-token tiers; per-kid accent color from the reserved berry/gold tokens | 3.1, 3.5 | new | S |
| 12 | Reader shows title and cover (title page + ending screen) | 3.2 | new | S |
| 13 | Honest progress package: route-relative bar, dual read-time clocks | 3.6 | tracked `AL-029`, `AL-022` | M |
| 14 | Declare `personalizable` HERO slots across the remaining 34 contracts (data-only, behind the ADR-023 block) | 2.6 | tracked (ADR-023 prereq) | S |
| 15 | Rating clearable + offered at the ending screen; flag resolution acknowledgment to the kid | 4.4 | partially tracked `U6` | S |
| 16 | Read-aloud-first prose rubric for the 3-5 band in place of tight FK targeting | 2.8 | new | S |
| 17 | Mascot pose set, kid-forward landing door, PWA manifest colors, display font | 3.5 | partially tracked `UW-I08` | S-M |
| 18 | Recommendation-to-request one-tap for unassigned published books (owner decision; stays inside ADR-015/016) | 4.5 | new, decision | M |
| 19 | Conformance corpus for personalization and series-carry before new runtime features | 5.3 | new | S |
| 20 | Run the naive-user session with real children; it gates UW-I01/UW-I02 and would validate most of the above | (all) | tracked `UW-M02` | owner |

Constraints honored throughout: ADR-016 (no free text, no discovery, no feed mechanics), ADR-017
(per-passage art requires a new ADR; image moderation precondition at volume), ADR-018 (no child PII
to providers, no third-party SDKs in the kid context, parental gate), ADR-023 (personalization
blocked pending re-plan and counsel; only its upstream data work is recommended), ADR-014 (kid
bundle must not import Supabase; new kid surfaces ride the child-session principal).

---

## 8. Owner decisions and open questions (2026-08-01)

### Decision D1 (owner, 2026-08-01): every non-terminal node must offer a choice

The owner's ruling on finding 2.3: all non-ending nodes should present a choice, not a "Continue"
tap. Measured impact against the committed catalog:

- 5,873 of 8,573 non-ending nodes (69%) currently have exactly one choice.
- **0 of 61 skeletons comply** as authored.
- Single-choice nodes cluster in short runs: of 3,241 runs, 39% are length 1 and 43% length 2
  (max 13). They are scene-splits, almost certainly produced by ADR-011's per-node word ceilings
  (e.g. 90 words/node at 3-5), not deliberate corridors.

Consequence: D1 cannot be a retroactive hard rule without voiding the catalog; it needs the
calibration questions A1-A5 below answered, and it likely requires an ADR-011 amendment on the
words-per-node side (whichever way A4 lands).

### Decisions recorded 2026-08-01 (second round, answering the sheet below)

| ID | Decision (owner, 2026-08-01) | Answers |
|---|---|---|
| D2 | Choice depth varies by band: lower bands may use flavor choices (reconverging targets, no real consequences); older bands require more consequential, distinct-target choices with fewer flavor choices. Loop-back routes are allowed. | A1, A5 |
| D3 | Existing 61 skeletons are grandfathered for now but must be phased out; new content meets the choice rule. Deprecation mechanics open (Q3 below). | A2, A3 |
| D4 | "Your story is ready" reaches the kid in-app only; no web/PWA push channel. | C1 |
| D5 | A tone axis is approved for child requests; the per-band tone vocabulary still needs definition (Q4 below). | C3 |
| D6 | Gamification is in scope, and broadly: collection mechanics, badges, and streaks are all included. | D2 (gamification) |
| D7 | Media (art, audio) ship as optional built-in format fields; budgets are set by balancing Supabase free storage and R2 capacity against reasonable offline download sizes. Any sound feature requires a mute control. | E1, E2 |
| D8 | POV (second person, "you are the hero") is to be available in all bands. | E3 |
| D9 | The additive-minor format-evolution policy is approved: ratified as [ADR-025](adr/adr-025-additive-storybook-schema-versioning.md) (Accepted 2026-08-01). | F1 |

### Research review: D1 versus ADR-011 (2026-08-01)

The owner asked how the initial research handles choice-per-node versus words-per-node. Findings:

1. **ADR-011 locks constants that conflict with D1 as literally stated.** Section 6 fixes
   "decisions per path ~4-8 (length adds breadth, not depth; do not inflate); choices per decision
   2-3; setup before first choice ~2-3 nodes," and section 4 mandates that fastest-finish substance
   "is added with mandatory **linear passages**, not extra decisions." The linear passage (1 to 1)
   is a first-class flow primitive in section 7. The empirical anchor is JHM 2019: 40 classic
   printed CYOA books (ages 9-12), ~5 decisions per playthrough, substance carried between
   decisions by linear pages.
2. **The conflict is presentational, which suggests the reconciliation.** In a printed book a
   linear passage is continuous prose the reader flows through; our app renders each linear node as
   a discrete screen ending in a "Continue" tap, which is what makes 69% of stops choiceless. The
   graph shape matches the researched genre; the node-equals-screen rendering does not match the
   researched reading experience. The candidate reconciliation is therefore: keep linear beats in
   the graph (preserving ADR-011's researched constants and the words-per-node ceilings), and make
   the renderer flow consecutive single-choice nodes into one scrollable passage so that **every
   stop a child makes ends in a choice**, which satisfies D1's intent. D2's band grading then
   applies to the choices themselves, not to a per-node quota.
3. **The research base is print-only and 9-12-only.** JHM 2019 measured printed books for ages
   9-12; 3-5 and 16+ are explicitly product-defined, and no source addresses digital tap pacing,
   flavor-choice tolerance by age, or screen-length norms. A dedicated external research pass on
   digital choice pacing for children was dispatched 2026-08-01; its findings will be appended to
   this document and should inform the per-band grammar (Q2) before ADR-011 is amended.
4. **Broken citation found**: ADR-011 cites `docs/planning/research/` as the home of the empirical
   basis; that directory does not exist in the repo. The nearest on-topic documents are
   `cyoa-book-benchmark-comparison.md` and `pathfinder-structure-exploration.md`, neither of which
   contains the JHM 2019 data. Either the research files were never committed or the path is stale;
   this needs correcting in ADR-011 (added to section 6 as item 5).

### Remaining decisions before an implementation plan can be built

- **Q1. Ratify the D1 reconciliation.** Adopt render-time flow of linear passages (every stop ends
  in a choice; graph keeps linear beats; ADR-011 constants stand) versus amend ADR-011 to require
  choices on every node (voids the researched shape, changes generation budgets). Recommended:
  render-time flow, pending the external research findings. Whichever way, this is a new ADR
  (player semantics change) plus conformance-corpus work.
- **Q2. Approve the per-band choice grammar numbers** implementing D2. A concrete,
  validator-expressible table needs owner sign-off, for each band: options per choice (2-3 per
  research), allowed flavor-choice share, required consequential-choice count (Tier-2 gated at
  which bands), loop-back allowance, and (if Q1 lands on render-flow) max words per rendered stop.
  The dispatched research pass feeds this; a draft table belongs in the implementation plan.
- **Q3. Deprecation mechanics for the grandfathered catalog** (D3): marker (`production_eligible`
  flip versus a new `deprecated` flag with a reason), effect (excluded from new generation and new
  assignment while already-published books stay readable), and the retirement trigger (per cell,
  once N compliant skeletons exist, or a date). Also: are the 23 committed fills imported under
  grandfather status (`UW-G14`), or held to the new rule?
- **Q4. The tone vocabulary per band** (D5). Proposal to approve or edit: gentle / funny /
  exciting at every band; add "a little spooky" from 8-11; add "scary" and "sad" from 13-16.
  Screening still caps tone by the band's content-flag ceilings regardless of request.
- **Q5. Gamification shape** (D6). (a) Streak definition: consecutive calendar days versus
  reading-days-per-week with grace, and whether a lapsed streak resets visibly (pressure) or
  quietly. (b) Badge taxonomy seed set (first book, every ending in a book, N books, first
  request, series complete). (c) Surfaces: library, profile picker, both. (d) Guardian per-profile
  off-switch for streaks? (e) Compliance check: engagement mechanics in a child-directed app get
  App Store Kids Category and COPPA scrutiny; fold into the ADR-018 counsel bundle (`UW-M03`).
  All data stays first-party per ADR-018; new tables carry the standing four-artifact tax.
- **Q6. Media budgets** (D7). Numbers to set: per-book offline download ceiling per band
  (reference points: story blobs are ~100-400KB gzipped; covers are 800px WebP at a ~256KB
  ceiling; a fully-illustrated 3-5 book at 10-23 nodes and ~500px art lands roughly 1-3MB).
  Whether UI sounds ship app-bundled (no storage cost, one-time download) versus per-story audio
  (R2 storage and per-book size); mute scope (global toggle versus per-profile persisted, and
  default on or off). Current storage facts: covers live on Cloudflare R2 (S3 API); Supabase holds
  Postgres only, so media budget planning is primarily an R2 and download-size question, not a
  Supabase one.
- **Q7. POV operationalization** (D8). "Available in all bands" needs one of: (a) second person
  becomes the rule everywhere (drafting guide as written, kid-band corpus is out of spec and gets
  refilled or phased out with D3), or (b) a per-story `pov` field (second or third person) with a
  band default, letting both exist. (b) requires a schema minor (now cheap via ADR-025) and
  fill-gate enforcement of consistency. Owner intent reads as (a)-leaning ("I wanted POV available
  in all bands"); confirm, and decide the existing-fills remedy.
- **Q8. Sequencing.** Which of the above land in the Content workstream versus Phase 4b, and
  whether the naive-user session (`UW-M02`) runs before the request-page and choice-grammar
  changes ship, per the standing gate in `handoff-s5-reader-ux-remaining-2026-07-26.md`.

### Research appendix: digital choice pacing for children (2026-08-01)

External research pass (web sources; evidence graded strong = peer-reviewed and measured, pract =
practitioner heuristic). Full sourcing sits in the findings below; the headline items:

1. **Flavor choices work, if and only if the next line acknowledges them.** Fendt, Harrison, Ware,
   Cardona-Rivera and Roberts (ICIDS 2012, "Achieving the Illusion of Agency") found no significant
   difference in felt agency between a truly branching story and a linear story whose choices got
   immediate textual acknowledgment; choices with no feedback underperformed. This is the strongest
   single result behind D2's flavor-choice allowance, and it adds a requirement: the fill gate
   should require choice acknowledgment in the following passage. (strong)
2. **The act of choosing motivates children independent of consequence, with diminishing returns.**
   Patall, Cooper and Robinson (Psychological Bulletin 2008, 41-study meta-analysis): choice
   enhances intrinsic motivation and effort, strongest at 2-4 successive choices per session, and
   more options per choice raises cognitive cost. Few options, frequent-but-bounded choices.
   (strong)
3. **For pre-readers, interaction competes with comprehension.** Takacs, Swart and Bus (Review of
   Educational Research 2015, 43 studies, ages ~2-12): story-incongruent interactive features hurt
   comprehension via cognitive load, worst for the youngest. Peebles, Bonus and Mares (Computers in
   Human Behavior 2018): preschool comprehension gains came from scaffolding interactions
   (questions, predictions), not from plot agency. Implication: at 3-5, "a choice on every page"
   should relax to "a story-congruent interaction on most pages," with short continue-runs
   acceptable. (strong)
4. **Delayed, state-gated consequences reliably land from about age 8-9.** The causal-comprehension
   literature (Frontiers in Psychology 2014 review; Trabasso et al.) puts adult-like narrative
   causal processing at ~9; before ~6, consequence-tracking barely exists, so consequences must be
   immediate and visible. This calibrates D2's consequence gradient. (strong)
5. **The winning print-to-digital adaptation kept linear beats in the graph and removed them from
   the surface.** inkle's Sorcery!/80 Days re-authored long gamebook passages into short beats with
   frequent low-consequence, immediately-acknowledged choices; the ink language's gather syntax
   exists precisely so a graph keeps linear structure while the rendered surface flows and nearly
   every stop ends in a choice. Tin Man Games' faithful page-per-section ports served nostalgic
   adults, and their own lead conceded the format needed more. Netflix's user-tested cadence for
   lean-back interactive titles is a decision every 3-5 minutes, binary options, with reconvergence
   framed diegetically. (pract, strong track record)
6. **Explicit answer to Q1's fork**: the evidence favors render-time flow (merge linear beats into
   scrolling prose so every stop ends in a choice) for 8-11 and up, and a modified hybrid at 3-5
   and 5-8 (discrete pages, choice on a regular cadence rather than every page, scaffold
   interactions between). No source supports force-branching every node, and Patall 2008 predicts
   diminishing returns from doing so. This confirms the section 8.3 reconciliation and keeps
   ADR-011's researched constants intact.
7. **Named evidence gaps**: no measured study of choice frequency in children's reading apps
   specifically, none on whether children detect reconvergence on replay, none on tap versus
   scroll for early readers. The per-band numbers below are triangulated calibrations, not
   measured optima; the naive-user session (`UW-M02`) is the project's chance to measure some of
   this directly.

Key sources: Fendt et al. 2012 (ciigar.csc.ncsu.edu/files/bib/Fendt2012-IllusionOfAgency.pdf);
Patall, Cooper and Robinson 2008 (Psychological Bulletin 134(2)); Takacs, Swart and Bus 2015
(RER 85(4)); Peebles, Bonus and Mares 2018 (CHB 85); Kolhoff and Nack, ICIDS 2019; Reed,
"50 Years of Text Games" on 80 Days (if50.substack.com/p/2014-80-days); Humfrey, "Open sourcing
ink" (gamedeveloper.com); Ingold GDC 2015/2017; Variety 2018 on Netflix cadence; children's
publishing word-count norms (Kole; Cioffi).

### Draft per-band choice grammar (proposal for Q2, awaiting owner sign-off)

"Stop" means a rendered page the child lands on, after Q1's render-flow merge where that applies.
Words per stop follow children's publishing norms and stay compatible with ADR-011's per-node caps
once linear beats merge.

| Band | Presentation | Choice cadence | Max choiceless stops in a row | Flavor vs consequential | Options per choice | Words per stop |
|---|---|---|---|---|---|---|
| 3-5 | discrete pages | choice every 2nd-4th stop; scaffold interaction (predict, point, answer) on other pages | 2-3 | ~90/10; consequences immediate and visible on the next page; reconvergence free | 2 | 10-40 |
| 5-8 | discrete pages | choice every 1st-2nd stop | 2 | ~70/30; same-scene payoff; every pick acknowledged in the next line | 2-3 | 30-70 |
| 8-11 | flowed prose | every stop ends in a choice | 1, prefer 0 | ~50/50; state-gated consequences begin, always with a visible "noticed" cue | 3 | 60-135 |
| 10-13 | flowed prose | every stop ends in a choice | 0-1 | ~40/60; delayed and cross-scene consequences expected; distinct targets | 3 | 80-150 |
| 13-16 | flowed prose | every stop ends in a choice | 0-1 | ~30/70; consequence foreshadowed (foreseeability was the measured weak point in Bandersnatch) | 3-4 | 100-200 |
| 16+ | flowed prose | every stop ends in a choice | 0-1 | ~30/70, gamebook style may push higher lethality per ADR-011 | 3-4 | 100-230 |

Cross-cutting rules (all bands): every choice acknowledged in the immediately following prose
(fill-gate rule); options few, choices bounded; every interaction story-congruent, none decorative;
from 8-11 up, design for replay detection of reconvergence (differing acknowledgment lines,
visible state). New concept introduced by the research that needs its own owner call, folded into
Q2: **scaffold interactions** at 3-5 (predict/answer beats that are not plot forks) are what the
evidence actually supports on choiceless pages; they are a new node affordance and would need a
schema minor (cheap under ADR-025) and prompt support.

The original question sheet (first round) is preserved below for the record; struck items were
answered by the decisions table above.

**A. Calibrating D1 (choice density)**

- **A1. What counts as "a choice"?** (a) 2+ options with any targets, which permits flavor choices
  that reconverge immediately; (b) 2+ options with distinct targets; (c) 2+ options where at least
  one has a downstream consequence (flag set or different subtree). Suggested: (b) at 8-11 and up,
  (a) allowed at 3-5/5-8.
- **A2. Enforcement point and severity.** Hard failure at skeleton promotion for new content, with
  advisory-only on the existing catalog until A3 is decided? Or hard everywhere on a deadline?
- **A3. What happens to the 61 existing skeletons and 23 fills?** Options: (1) authoring-time merge
  of single-choice chains into their predecessor node (colliding with word caps, see A4); (2)
  player render-time merge: the engine walks through single-choice nodes and renders one scrollable
  passage until the next real choice, so "Continue" disappears with zero content changes (both
  engines plus the conformance corpus must change, and node-count-based progress semantics shift);
  (3) a mutation-pipeline pass that adds real branches; (4) grandfather the catalog. Suggested:
  (2) as the fast win, plus the hard rule for new content; revisit (3) per skeleton over time.
- **A4. Which rule gives way: choice-per-node or words-per-node?** If every node must branch, then
  either per-node word ceilings rise (or a node body may span multiple rendered screens with the
  cap becoming per-screen advisory), or stories get denser branching and ADR-011's
  nodes-from-words arithmetic changes. Either way ADR-011 needs an amendment; which side?
- **A5. Does D1 apply fully to the 3-5 band,** where reading is adult-mediated and picture-book
  pacing is partly linear by convention? (Only 69 single-choice nodes exist at 3-5, so full
  compliance is cheap if wanted.)

**B. Content and genre**

- **B1.** Rank the genre wave for under-13 skeletons: dragons/magic, space, dinosaurs, pirates,
  gentle-spooky, comedy, sports, superheroes, mystery. Any to exclude on principle?
- **B2.** Which growth path gets investment first: fixing hand-authoring promotion (`UW-C01`,
  currently nothing passes), harvesting the mutation pipeline, or an LLM structure pass?
- **B3.** Target ending-valence mix for teen books (currently 83% negative at 13-16/16+; one book
  is 147 deaths of 150 endings). A ratio ceiling per book, or leave gamebook-lethal as a style?

**C. Request loop and defaults**

- **C1.** Where may "your story is ready" reach the kid: in-app only (picker pill, library banner,
  request-card flip), or is PWA push on the table (new ADR-018 privacy surface)?
- **C2.** Reflect-back voice: show the stored K19 interpretation verbatim, or invest in
  LLM-authored kid-facing prose (`OQ-5` / `UW-I07`)?
- **C3.** Define the tone vocabulary a child may request per band (does "a little spooky" exist at
  8-11? is "funny" available everywhere?). Tone can only leave "gentle" once the allowed set is
  named.
- **C4.** Story size on request: auto mid-band, or kid-selectable short/long?

**D. Celebration and gamification**

- **D2. The gamification ceiling.** Which mechanics are in-bounds for this product: collection
  (endings gallery, finished shelf) vs achievement badges vs streaks? Streaks are a re-engagement
  pressure mechanic some families explicitly reject; this is a values call, not an engineering one.
- **D3.** Ending rarity/secret markers: authored in skeleton metadata (stable, band-reviewable) or
  derived from reading data? Suggested: authored.
- **D4.** Large-book denominator (`AL-028`): curated signature endings (the author names ~5-9
  headline endings as the kid-visible set) vs milestone framing ("3 new endings found")?

**E. Art, audio, and voice**

- **E1.** In-story illustration: pilot now (per-node at 3-5 only, or per-bottleneck-scene at
  3-5/5-8) or post-launch? At that volume ADR-017's amendment clause triggers: is the automated
  image-moderation precondition acceptable? What is the art budget per book?
- **E2.** Sound: none, soft UI sounds (page turn, choice tap, ending chime; muted by default or
  not), or ambient audio? Read-aloud is already slated as a subscription feature post-launch; does
  browser TTS stay free?
- **E3.** POV per band: second person everywhere (the drafting guide as written) or third person at
  3-5/5-8 with second person from 8-11 up? This decision gates both the corpus fix (2.2) and where
  hero-name personalization can land (2.6).

**F. Sequencing and process**

- **F1.** Approve the additive-minor format-evolution policy (server accepts a declared `2.x`
  range; minor versions are additive-optional)? It sequences before ending metadata, images, and
  sound cues.
- **F2.** May the personalization contract-slot data work proceed now, while ADR-023 remains
  blocked on counsel, on the understanding nothing ships until the ADR is Accepted?
- **F3.** May a ring-1/ring-2 recommendation surface an unassigned published book to a kid as a
  one-tap "ask for it" request (routing through the normal guardian consent gate)?
- **F4.** When can the naive-user session with real children run (`UW-M02`)? It gates the
  request-page reshape and two reader-UX items, and would pressure-test most of the choices above.
