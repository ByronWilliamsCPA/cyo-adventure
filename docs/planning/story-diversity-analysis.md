---
schema_type: planning
title: "Story Diversity Analysis: Current-State Audit and Improvement Levers"
description: "An evidence-based audit of what the shipped generation pipeline actually does to keep stories
  feeling unique, measured against the objective in story-flexibility-plan.md. Finds that the diversity
  machinery is built but rarely fires on a realistic request, identifies one structural clone already live in
  the catalog, and proposes nine prioritized levers."
tags:
  - planning
  - generation
  - diversity
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Answer the question 'how do we improve the perceived diversity of generated stories' with
  measurements against the live catalog and the live selection/fill path, rather than restating the
  workstream plan. Companion and successor to story-flexibility-plan.md section 2 (Problem, current-state)."
component: Strategy
source: "Read of generation/skeleton_match.py, story_requests/authoring_plan.py, generation/orchestrator.py,
  generation/templates/fill.md, diversity/{query,normalize,structure,history,leaf}.py,
  moderation/leaf_diversity.py, mutation/floors.py, and a full measurement pass over the 61-file
  skeletons/ library (2026-07-25)."
---

> **Scope.** This is a current-state audit, not a new plan. It assumes
> [story-flexibility-plan.md](story-flexibility-plan.md) as the strategy of record and does not re-propose
> WS-0, WS-1, WS-4, WS-5, WS-7, or WS-8. Everything below is either a measurement of the shipped system or a
> gap those workstreams left open, closed off, or did not anticipate.

---

## 1. Headline

The diversity machinery is real, well-designed, and largely built. The problem is that **on a typical real
request, almost none of it fires.**

Three independent gates each reduce to a no-op under ordinary conditions:

1. `theme_signature` recognizes a **closed vocabulary of 12 theme tags**. Any request outside them yields an
   empty signature, and `jaccard_similarity(frozenset(), frozenset())` returns `0.0`, so two identical
   requests are scored as maximally *dissimilar*. WS-4's escalation ladder never leaves `TREE`.
2. The escalation level that ladder computes **never reaches the fill**. `fill_skeleton` has no parameter for
   it. Selection changes which tree is drawn and nothing else.
3. The anti-template guard is advisory, fail-open, compares against **one** prior fill, and its per-band
   threshold table is empty pending calibration. Nothing today prevents a templated fill from shipping.

So the effective diversity mechanism in production is a single lever: inverse-frequency weighted random
skeleton choice within a cell. Measured below, that lever gives a child a **20% chance that their second
story runs on the same tree as their first.**

Separately, the live catalog already contains one structural clone pair inside a single cell, at a structural
distance of 0.0009 against an anti-clone floor of 0.05, and the project's own fingerprint check cannot see it.

---

## 2. What the catalog actually looks like

Measured over `skeletons/` (61 files, 58 production-eligible), 2026-07-25.

### 2.1 Cell pools are small, and 3 is the mode

Selection is scoped to a `(band, length, style)` cell (`skeleton_match.candidates_for_cell`). Pool sizes:

| Cell | Prod-eligible | Cell | Prod-eligible |
|------|---------------|------|---------------|
| 3-5 / short | 3 | 13-16 / medium / gamebook | 3 |
| 3-5 / medium | 3 | 13-16 / long / prose | 3 |
| 5-8 / short | 3 | 13-16 / long / gamebook | 5 |
| 5-8 / medium | 3 | 16+ / medium / prose | 4 |
| 8-11 / short | 3 | 16+ / medium / gamebook | 3 |
| 8-11 / medium | 3 | 16+ / long / prose | 3 |
| 8-11 / long | 3 | 16+ / long / gamebook | 3 |
| 10-13 / short | 4 | 13-16 / medium / prose | 3 |
| 10-13 / medium | 3 | | |
| 10-13 / long | 3 | | |

Fourteen of eighteen cells hold exactly three trees. A child who reads four stories at one length and band
**must** see a tree twice; it is arithmetic, not a tuning problem.

### 2.2 The repeat rate that implies

Monte Carlo over the shipped `select_skeleton_for_cell` (20,000 trials, 6 sequential requests per trial):

| Cell size | Signal | P(story 2 reuses story 1's tree) | P(consecutive pair reuses) | Distinct trees over 6 |
|-----------|--------|----------------------------------|----------------------------|------------------------|
| 3 | recency only (today's real path) | **20.1%** | 24.7% | 2.95 / 3 |
| 3 | + theme similarity (WS-4 active) | 9.2% | 19.7% | 3.00 / 3 |
| 4 | recency only | 13.9% | 16.7% | 3.71 / 4 |
| 5 | recency only | 11.1% | 12.8% | 4.21 / 5 |

WS-4's similarity blend roughly halves the immediate-repeat rate, which is exactly what it was built to do.
But per section 3.1 it only engages for the 12 in-vocabulary themes, so the top row is the live behavior for
most requests.

### 2.3 Topology variety within a cell is a genuine strength

Every kid-band cell holds three *different* topologies, drawn from `time_cave`, `open_map`, `loop_and_grow`,
`branch_and_bottleneck`, and `sorting_hat`. Minimum in-cell structural distance is 0.20 to 0.49 in every cell
except the two flagged in section 3.2. Whoever authored the catalog varied structure deliberately and it
worked. This is worth protecting as the catalog grows by automation.

### 2.4 But "how it plays" barely varies in the gamebook cells

`structure_features().valence_hist` (negative share is the dominant component in these cells):

| Cell | Negative-ending share per candidate |
|------|--------------------------------------|
| 13-16 / long / gamebook | 0.95, 0.97, 0.78, 0.95, 0.97 |
| 13-16 / medium / gamebook | 0.96, 0.96, 0.91 |
| 16+ / long / gamebook | 0.98, 0.98, 0.98 |
| 16+ / medium / gamebook | 0.85, 0.93, 0.97 |
| 8-11 / medium | 0.08, 0.55, 0.24 |
| 3-5 / short | 0.00, 0.43, 0.00 |

The kid bands spread; the gamebook cells do not. In `16+ / long / gamebook` every tree ends badly on 98% of
paths. Topology differs, prose differs, and the reader's experience is still "this is another maze where I
die." Outcome mix is a first-class perceived-diversity axis, it is already computed in `structure_features`,
and selection ignores it entirely.

Decision density is similarly wide (`decision_ratio` spans 0.13 to 0.99 across the catalog) and similarly
unused by selection. In `the-skyrail-heist`, 168 of 246 nodes offer exactly one choice, so the handful of real
decision points carry the entire felt-agency load, which amplifies any sense of "same decisions again."

---

## 3. Defects and gaps found

### 3.1 `theme_signature` has a 12-tag closed vocabulary, and empty means "dissimilar"

**Severity: high. This is the single highest-leverage fix in this document.**

`diversity/normalize.py::theme_signature` maps a premise to tags via `_THEME_TAG_MAP`: 67 keys collapsing to
**12 distinct tags** (`castle, cave, dinosaur, dragon, fire, forest, knight, magic, ocean, pirate, robot,
space`). A premise matching none of them returns `frozenset()`. Measured:

```
'a dragon who lost his fire'                         -> {dragon, fire}
'dragon story please'                                -> {dragon}
'a story about my hamster escaping the cage'          -> frozenset()
'a girl who builds a submarine out of bottle caps'   -> frozenset()
'soccer championship with my best friend'            -> frozenset()
'a haunted violin in my grandmothers attic'          -> frozenset()
```

The tag map handles its own examples well: the two dragon briefs score Jaccard 0.5, clearing `tau_theme`
0.35. The failure is coverage. The map encodes a fantasy/sci-fi trope list, while real requests are about
pets, sports, family, school, music, and inventions.

Two compounding consequences:

- `jaccard_similarity(frozenset(), frozenset()) == 0.0`. An unrecognized theme is not treated as *unknown*,
  it is affirmatively scored as maximally dissimilar to every prior story, including a byte-identical prior
  request. So `similar_count_per_slug` stays all-zero, `_blended_weight` collapses to `_weight`, and WS-4 is
  inert.
- `cell_theme_saturation` stays 0.0, so `recommendation` is always `TREE`. No saturation warning, no
  `selection.cell_theme_saturated` log, and no `CELL_SATURATED` trigger for the WS-8 flywheel. The entire
  escalation ladder and the catalog-growth trigger that depends on it are dark for out-of-vocabulary themes.

**Fix.** Replace the closed tag map with an open-vocabulary signature: content-token Jaccard after the
existing stopword and entity masking, with the tag map retained as a synonym-collapsing layer on top (so
"dragon"/"wyvern" still merge) rather than as the gate. Keep `metadata.themes` as trusted signal. Separately,
make empty-versus-empty return a distinct "unknown" rather than `0.0`, and have `score_history` treat unknown
as *conservative* (assume similarity) rather than as dissimilar, so the failure mode is over-diversifying
instead of silently disabling.

### 3.2 A structural clone is live in the catalog, and the fingerprint check cannot see it

**Severity: high.**

`skeletons/13-16/the-sunken-temple.json` and `skeletons/13-16/the-harrowstone-keep.json` are the same tree:

- Same cell: both `13-16 / long / gamebook`, both `production_eligible: true`.
- 550 nodes, 152 endings, 801 choices, `max_depth` 58, 4 variables, 7 conditions, 49 effects: identical.
- Identical ending-kind and valence multisets (`{setback: 54, death: 17, capture: 77, completion: 1,
  success: 3}` on both).
- `structural_distance(...)` = **0.00095**, against a `TAU_CELL` anti-clone floor of **0.05** in
  `mutation/floors.py`. Fifty times below the bar.
- Node ids and beat text differ (1 of 550 bodies matches), so it reads as a re-guided variant of the same
  graph, consistent with the WS-5 re-guidance flow.

Two distinct problems:

1. **`structure_fingerprint` returns different values for the pair**, because `_strip_leaf_content` strips
   titles, bodies, and choice labels but retains node `id`s. Any clone with renamed nodes is invisible to
   every equality-based check built on it. `structural_distance` catches it correctly at 0.0009; the
   fingerprint does not. Anywhere clone detection is the goal, the fingerprint is the wrong instrument.
2. **`TAU_CELL` is enforced only on mutation-derived promotion candidates**, never on the catalog as it
   stands. A hand-authored or hand-merged skeleton enters `skeletons/` through PR review with no in-cell
   distance check, which is how this pair shipped.

The reader-facing effect is worse than a plain repeat. WS-4, told to prefer a different slug, will happily
move a family from one of these to the other and record that it delivered tree-level differentiation, while
the child replays the identical 550-node decision graph with the identical 145-negative ending layout. The
cell nominally holds five trees; it holds four.

`13-16 / medium / gamebook` is also worth a look: minimum in-cell distance 0.091, under 2x the floor.

**Fix.** Add a CI audit that computes pairwise `structural_distance` across every production-eligible
skeleton in each cell and fails below `TAU_CELL`, so the floor applies to the whole catalog and not only to
automated candidates. Then resolve the existing pair: retire one, mutate one past the floor, or re-cell it.
Independently, either extend `structure_fingerprint` to canonicalize node ids by graph position, or document
it as an identity check that is explicitly not a clone check and route clone questions to
`structural_distance`.

### 3.3 The escalation level never reaches the fill

**Severity: high.** WS-4's stated approach includes raising "a needs-leaf-differentiation signal to the fill
when the cell is saturated for this theme." That half is not built.

`orchestrator.fill_skeleton(skeleton, theme_brief, provider, pii, *, max_repairs, settings,
review_stage1_model, prep_model, slot_bindings)` accepts no similarity context, no `DifferentiationLevel`, and
no reference to the reader's prior stories. Tracing `DifferentiationLevel` outside `diversity/` confirms it
reaches exactly three places: a non-blocking warning in `authoring_plan.py`, an info log, and the WS-8
flywheel trigger. The fill prompt is a pure function of `(skeleton, brief, bindings)`.

So when the ladder does escalate to `LEAF` (the case where the tree *must* repeat and prose is the only
remaining lever), the generation step behaves identically to an unsaturated first-ever request. The one moment
the system knows it needs to try harder is the one moment nothing changes.

**Fix.** Thread `DifferentiationLevel` and the top-k `StoryNeighbor` entries into `fill_skeleton`, and add a
conditional block to `fill.md` for the escalated case: an explicit avoid-list of the prior fills' titles,
settings, cast archetypes, and imagery on this same tree, plus a directive to change tone, cast relationships,
and pacing rather than only surface nouns. The neighbor data is derived from untrusted premises, so it must be
fenced at reuse per safety invariant 4.

### 3.4 The frozen beat armature caps how different two leaves can be

**Severity: medium-high. Not addressed by any current workstream.**

WS-1 correctly identifies leaf diversity as the primary lever and WS-1/D2 strengthened `fill.md` to demand
genuine re-imagining. But the beat text itself is frozen. Each node body carries
`<<FILL role=R words=N beats='...'>>`, and `fill.md` requires the prose to "depict this exact beat, the same
events and outcome," with the Stage 1 fidelity gate enforcing it. The beats are byte-identical across every
fill of a skeleton forever.

Because the skeletons are already slot-parameterized, the armature is visible in the beat text itself:

```
the-cave-of-echoes / la_fork:
  'the way splits into two tracks: on one side {A1_SIGN} catches the light,
   on the other {A2_SIGN} deepens into a warning...'
```

Every fill of this tree, for every theme, contains a two-way split where one branch looks inviting and the
other looks like a warning, at the same depth, with the same word budget, in the same role sequence. The
`{SLOT}` values and the prose change. The scene does not.

This sets a hard ceiling on the anti-template guard. The ATG measures masked prose distance between two fills,
but both fills are rendering an identical event at an identical beat. Push `fill.md` harder and it collides
with the fidelity gate; the two constraints are in direct tension, and fidelity wins because it is the
blocking one.

**Fix.** Vary the armature, not just the prose. Two options, in increasing cost:

- **Alternate beat phrasings.** Author two or three interchangeable beat variants per node that share the
  same *outcome contract* (same successor state, same choice semantics) but differ in the scene that delivers
  it. Selection picks a variant set per fill. The fidelity gate keeps working unchanged: it checks the fill
  against whichever variant was issued.
- **Beat re-voicing as a pipeline stage.** A bounded pre-fill step that rewrites the beat line for the theme
  under the outcome contract, with the rewritten beat becoming the fidelity target. Higher ceiling, but it
  moves a safety-relevant artifact into generated territory and needs its own gate.

Either way the change is to make `beats` a *contract* the pipeline checks rather than a *string* the pipeline
freezes. That is a distinct axis from WS-2's slot contracts, which bound the reskin without touching the
beat.

### 3.5 Diversity is family-scoped; perceived similarity is per-reader

**Severity: medium.**

`HistoryEntry` carries `storybook_id`, `version`, `skeleton_slug`, `theme_sig`, `created_at`. There is no
`profile_id` anywhere in `diversity/`, and `load_family_history` / `recent_skeleton_usage` both scope to
`family_id` with a 20-row window. The plan acknowledges the target is "primarily per reader/family"; the
implementation is family-only.

Consequences in a multi-child family:

- The 20-row window is shared. With three children it gives each roughly seven stories of protection instead
  of twenty, and each child's own repeats are diluted by siblings' history.
- A skeleton is de-weighted for a child because a *sibling* used it, even though this reader never saw it,
  spending scarce pool diversity on a repeat that would not have been perceived.
- The ATG comparison partner can be a sibling's fill. Comparing against a story this reader never read is the
  wrong pairwise test for a per-reader guard.

The window has a second interaction worth flagging: it counts every `storybook_version` row, so retries and
re-authored versions consume slots. `skeleton_match` documents this as deliberate, and it is defensible for
authoring-activity accounting, but combined with the hard cap of 20 it means a family that re-authors heavily
has a much shorter effective memory than one that does not.

**Fix.** Add optional `profile_id` scoping to `load_family_history` and `recent_skeleton_usage`, and prefer
per-profile history for the ATG partner and for weighting, falling back to family when the profile has too
little history. Consider counting distinct storybooks rather than versions for the recency window, or raising
the cap to compensate.

### 3.6 The anti-template guard compares against only one prior fill

**Severity: medium.**

`select_atg_comparison_partner` returns `max(same_tree, key=created_at)`: the single most recent prior fill of
the same skeleton. A family's third fill of a tree is compared only against the second. If fill 3 closely
matches fill 1 while fill 2 was genuinely different, the guard passes at full marks. Templating that recurs
with a gap is invisible.

Combined with the guard being advisory, fail-open, and running on an empty per-band threshold table
(`_thresholds_for_band` returns the section-3.2 defaults for every band, per its own comment "empty until
calibrated"), nothing currently stops a templated fill from reaching a guardian.

**Fix.** Compare against the *k* most recent same-tree fills, or against the nearest by theme signature, and
take the minimum distance as the verdict input. Then calibrate the per-band thresholds and decide the promotion
from advisory to blocking, which WS-1 already tracks as open.

### 3.7 Selection ignores the feature vector it already computes

**Severity: medium.**

`structure_features` yields `topology`, `decision_ratio`, `valence_hist`, `ending_kind_hist`, `max_depth`,
`reconvergence_ratio`, and more. Selection consumes none of it. Both weighting signals key on
`skeleton_slug`: `recent_usage[slug]` and `similar_count_per_slug[slug]`.

Everything a reader would describe as "these feel the same" that is not prose lives in that vector: two
gauntlets in a row, two 98%-negative ending mixes in a row, two corridor-heavy trees with four real decisions
each. Section 3.2's clone pair is the extreme case, where slug-keyed accounting counts a repeat as a change.

**Fix.** Extend the weight to de-weight a candidate by its `structural_distance` and `valence_hist` proximity
to the reader's recent stories, not only by slug identity. The novelty floor (safety invariant 5) is preserved
by construction since the existing `1/(1+...)` form never reaches zero. This also makes the clone pair
self-correcting: the second of two near-identical trees is de-weighted like a repeat because it is one.

### 3.8 Nothing varies per-request in the generation call itself

**Severity: low-medium, cheap to fix.**

No `temperature`, `top_p`, or seed appears anywhere in `generation/providers/*.py` or `provider.py`, so every
call takes the provider default. More importantly, there is no deliberate variation input: the fill prompt is
determined by `(skeleton, brief, slot_bindings)`. Two similar briefs on the same tree get two similar prompts
and, at default sampling, two similar fills. The ATG then measures the resulting similarity after the fact
instead of the pipeline having tried to avoid it.

**Fix.** Cheapest available diversity: pass an explicit per-request variation directive into the fill, drawn
from an authored axis library (narrative distance, tonal register, sensory emphasis, pacing, whose point of
view the scene favors). Unlike raising temperature, this varies the *dimension* of variation rather than the
noise level, and it does not trade against reading-level stability, which the WS-0 lexical guards watch.

### 3.9 Three skeletons are silently unreachable

**Severity: low.** Three files carry `length: None` and `production_eligible: false`
(`10-13`, `16+`, `3-5`, one each). They are correctly excluded, but they are also 5% of the library sitting
idle in cells that hold only three trees. Worth confirming each is deliberately retired rather than
mis-tagged.

---

## 4. Prioritized recommendations

Ordered by perceived-diversity gain per unit of effort. Items 1 through 4 are the ones that change what a
child experiences this quarter.

| # | Change | Addresses | Effort | Why this order |
|---|--------|-----------|--------|----------------|
| 1 | Open-vocabulary `theme_signature`; unknown is not "dissimilar" | 3.1 | S | Turns WS-4, the saturation warning, and the WS-8 trigger on for the majority of real requests. Everything downstream of similarity is currently dark. |
| 2 | In-cell `structural_distance` audit in CI at `TAU_CELL`; resolve the clone pair | 3.2 | S | One cell is a tree short right now, and selection reports the swap as differentiation. Cheap, and it protects the catalog as automation grows it. |
| 3 | Thread `DifferentiationLevel` + neighbors into `fill_skeleton` and `fill.md` | 3.3 | M | Completes WS-4's other half. Without it, escalation is a log line. |
| 4 | Per-request variation directive from an authored axis library | 3.8 | S | Cheapest real leaf-diversity gain, orthogonal to reading level. |
| 5 | Feature-vector-aware selection weighting | 3.7, 2.4 | M | Uses metrics already computed; makes near-clones and identical outcome mixes self-correcting. |
| 6 | `profile_id` scoping for history, weighting, and the ATG partner | 3.5 | M | Aligns the signal with the per-reader phenomenon it models. |
| 7 | ATG against the k nearest same-tree fills, then calibrate thresholds | 3.6 | M | Closes the gap-recurrence blind spot; prerequisite for making the guard blocking. |
| 8 | Alternate beat phrasings sharing an outcome contract | 3.4 | L | Highest ceiling on leaf diversity, and the only item that lifts the cap the frozen armature imposes. Needs a design doc and probably an ADR. |
| 9 | Grow the small cells, and audit the three excluded skeletons | 2.1, 3.9 | L | Pool size is the root arithmetic constraint. WS-8 already owns the automated path; this is the reminder that 3-per-cell is the number to beat. |

Two framing notes for whoever picks this up:

- **Items 1 and 2 are prerequisites for trusting any diversity metric.** Until the similarity signal covers
  real requests and the catalog is clone-free, the WS-0 dashboard reports on a system whose diversity
  machinery is mostly inert, and its numbers will look better than the reader's experience.
- **Item 8 is the real ceiling.** Items 1 through 7 make the existing levers work as designed. But with three
  trees per cell and a frozen beat armature, a heavy reader eventually meets the same scene sequence no matter
  how well selection and prose variation perform. Lifting that requires either many more trees (WS-8's bet) or
  a variable armature (item 8), and item 8 is far cheaper per unit of diversity gained.

---

## 5. What is working, and should not be disturbed

Stated explicitly so a future change does not trade it away:

- **Deliberate topology variety per cell** (section 2.3). Every kid-band cell holds three distinct
  topologies at healthy structural distance. Automated catalog growth must preserve this, which is what the
  section 3.2 CI audit is for.
- **The safety architecture is genuinely orthogonal to diversity.** Freezing the ADR-011 constraint grammar
  rather than the graphs means every lever above can be pulled without touching the gate. None of the nine
  recommendations requires a safety exception, and none should be granted one.
- **The novelty floor.** `1/(1 + ...)` never reaches zero, so no eligible tree is ever fully excluded. Every
  weighting change proposed here keeps that form.
- **Fail-closed binding.** `generation/binding.py` raises rather than falling back to `default_binding` on a
  malformed slot response. That matters for diversity as well as safety: a silent fallback would ship the
  shipped default story, which is the most visible possible repeat.
