---
schema_type: planning
title: "Story Flexibility and Diversity Plan"
description: "Strategy for maximizing story diversity, defined as: each story must feel like a new
  adventure to the reader. Vary the leaves (the descriptive content along a shared tree of paths and
  decision points) first, add structural and state variety as the library scales, and let the
  deterministic gate keep every variant safe. Corrects an earlier premise: the automated fill
  already themes stories from the requester's brief."
tags:
  - planning
  - architecture
  - generation
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Record the objective (each story feels like a new adventure), the leaves-on-a-tree model,
  diversity metrics, and phased workstreams for maximizing story diversity so the concepts are not
  lost and each change can be planned with full context. Revised 2026-07-18 after an adversarial
  (Fable) review and an owner framing of the objective. Companion to the pilot under out/pilot/."
component: Strategy
source: "Design discussion 2026-07-18 following the initial story-inventory run; owner objective
  framing (leaves on a tree); adversarial review of the first draft; current-state exploration of
  generation/ (fill.md, worker.py, orchestrator.py), story_requests/, skeleton_match.py, validator/,
  and ADR-011."
---

> **Status: Active (revised).** The parameterized-beat pilot (`out/pilot/`) is
> built and proven; nothing beyond it is wired into the live path yet. This
> revision (a) sets the objective from the negative, each story must feel like a
> new adventure, in the academic leaves-on-a-tree frame; (b) corrects the original
> problem statement (the automated fill already consumes the theme brief);
> (c) adds a metrics workstream (WS-0) without which "maximize" is unfalsifiable;
> and (d) adds structure/state variety and a catalog flywheel. Parameterized
> skeletons are an ADR-019 candidate (see Open questions).

---

## 1. Objective: each story must feel like a new adventure

Defined from the negative, the failures we must avoid:

- A reader reads two stories and feels they are **similar**.
- A **dog swapped for a cat** with the rest of the story identical: a surface
  substitution is not a new experience.
- A reader requests **their own** story and it reads like another they requested.

So the objective is perceptual: **minimize the perceived similarity between any
two stories a reader encounters.** With only a handful of stories in a cell some
similarity is inherent; the goal is to hold perceived-uniqueness up as the
library grows so every book is a new adventure.

### The leaves-on-a-tree model (the frame we design to)

From the original research: a story is a **tree** whose branches are the
**paths and decision points**, and whose **leaves** are the story told along
those branches.

- The **tree** (structure) may be **shared** between stories. Two stories can
  follow the same path to the same branch point, and the path back to the main
  line is the same path. Shared structure is acceptable, and inevitable when a
  cell has few skeletons.
- The **leaves** (the description of each point, "how they describe point A and
  point B") must be **genuinely different** between stories. This is where
  perceived uniqueness is made.

Three consequences for strategy:

1. **Leaf diversity is the primary lever.** Most of the perceived-uniqueness
   load, per pair of stories, is carried by genuinely re-authored leaf content,
   not by new structures. The dog-for-cat failure is a leaf that collapsed into a
   variable substitution; the fix is a genuinely re-imagined leaf on the same
   branch, not a new tree.
2. **Structural variety is the scaling lever.** Shared trees are fine at small
   scale, but as a family reads more and as the per-cell library grows, repeated
   trees start to show. Structural variety (new trees, mutated trees) is what
   keeps uniqueness up at scale; it complements leaf diversity rather than
   replacing it.
3. **Reuse is unavoidable, so differentiation escalates with similarity
   pressure.** We cannot give every request its own tree. The operating model is:
   as similar content accumulates for a reader, escalate, a **different tree**
   first (the second dragon), then **harder leaf/element variation** on a reused
   tree (the tenth dragon), then **grow the catalog**. This is why selection
   (WS-4) must consume the similarity metric (WS-0), not just recency.

This rebalances the adversarial review, which pushed structural variety as the
ceiling: correct at scale, but leaf diversity is the first and largest lever.

## 2. Problem (current-state)

1. **The automated fill already themes the story from the requester's brief.**
   `generation/templates/fill.md` tells the model to "adapt the world, character
   names, and surface theme to match the child's story request," rewrite every
   choice `label`, and preserve only the beats/structure; the child's text is
   fenced as `UNTRUSTED_USER_INPUT`. `worker.py::_run_skeleton_fill` reads
   `authoring["theme_brief"]`; `orchestrator.fill_skeleton` builds the prompt with
   it; `brief.py` sets `premise = request.request_text`. (An earlier draft wrongly
   said the theme is ignored; that grep was of the manual `cyo-author` skill, the
   one path that genuinely has no theme step.)
2. **But the leaves may be varying too little.** The reskin changes names and
   surface, and the same skeleton is reused (selection recency is on the slug
   only, `skeleton_match.py`). Nothing measures whether two fills of one tree are
   *genuinely* different leaves or just a dog-for-cat swap.

The real gaps:

- **No measurement of perceived similarity.** "Maximize diversity" has no metric
  and no eval loop, so "optimal" is unfalsifiable. This is the top gap.
- **Leaf variation is unverified and possibly shallow.** The Stage 1 fidelity
  gate (`moderation/fidelity_review.py`) checks beat/word fidelity, not whether
  two fills of the same skeleton read as different adventures, and not whether the
  requested theme was genuinely woven in vs surface-swapped.
- **Skill-path parity.** The manual `cyo-author` skill has no theme step.
- **Only the thematic axis moves, shallowly.** Structural and state/consequence
  variety ([K3](capability-register.md)) are untouched; the thematic axis itself
  is at risk of the dog-for-cat failure.
- **Selection recycles trees.** Recency is slug-only; topology/tone/theme are not
  de-weighted.

## 3. Design principle: freeze the safety *constraints*, vary within them

Safety does not require freezing the ~50 hand-authored graphs in `skeletons/`. It
requires freezing the **properties** the gate verifies: the ADR-011 per-band
topology/primitive allowances, the ending kind/valence policy, the three clocks,
the cell envelopes, the reading band. The validator (`topology.py`, `walk.py`,
`policy.py`, `band_profile.py`, the L2 config walk, the L2-13 scale advisory)
checks the properties of a graph, not its identity. The frozen safety object is
the **ADR-011 constraint grammar**; any leaf content or any structure, sampled,
mutated, or composed, is legitimate once it passes the same gate. Leaves vary
freely within band + safety; trees vary within the grammar; the gate verifies
every result.

## 4. Three axes of diversity (leaf-first)

| Axis | Question | Primary? | Levers |
|------|----------|----------|--------|
| **Leaf / content** | Does each point read as a new experience? | **Primary** | genuine per-node re-authoring (not slot substitution); theme binding (shipped, needs verification); anti-template guard |
| Structural | How does it branch? | Scaling | mutation of verified trees, grammar-based composition, fresh-generation feed, catalog flywheel |
| State / consequence | How does it play? | Scaling | Tier-2 variable semantics, condition-gated routes, ending-set variation within band policy ([K3](capability-register.md)) |

The anti-pattern that spans all three: a **template**, where the tree and the
leaf skeleton are fixed and only proper nouns change (dog for cat). The metric
in WS-0 must detect and fail it.

## 5. Workstreams (prioritized)

### WS-0: Diversity metrics + eval harness (do first)

> **Status (2026-07-18): Phase 1 and Phase 2 delivered.** Phase 1 shipped the
> `diversity/` package core (`normalize`, `structure`, `leaf` incl. the
> anti-template guard, `report`, `history`, `query`). Phase 2 shipped
> `aggregate` (ECS, PS, RAR), the `lexical` guards, the committed eval panel
> and baseline, `scripts/run_diversity_eval.py`, the `diversity_eval` nox
> session, and the per-PR CI regression gate (rules R1-R6); see
> [ws0-phase2-harness-design.md](ws0-phase2-harness-design.md) for the exact
> spec. Phase 3 (judge-model calibration) is implemented behind
> `--with-judge` but not yet run (needs a live, non-mock provider); WS-1's
> per-band threshold calibration remains open. WS-4's consumption of the
> request-time query is delivered (see the WS-4 section below).

- **Goal:** measure perceived similarity per cell and per family so every claim
  below is testable and regressions are caught.
- **Headline metric:** **perceived-similarity / repeat-adventure rate**, the
  probability that a reader's next story feels like one they have read. Proxied
  by a judge-model "do these read as different adventures?" score, validated
  against [K18](capability-register.md) ratings over time.
- **The anti-template guard (most important):** for two fills of the **same
  skeleton**, normalize proper nouns and measure leaf-level content overlap
  (per-node embedding + lexical distance). Low distance after noun-normalization =
  the dog-for-cat failure = a hard regression, even if the theme labels differ.
- **Supporting metrics.** *Leaf:* per-node pairwise distance across fills of one
  tree (the direct leaf-diversity signal). *Structural:* topology entropy;
  pairwise structural distance (node/ending/branching/depth features); distinct
  trees served per family per 90 days. *Thematic:* proper-noun overlap between a
  family's consecutive stories (~0); theme-incorporation rate. *Lexical guard:*
  self-BLEU / distinct-n, cross-checked with RL-13 so variety never buys
  reading-level drift. *Aggregate:* effective catalog size (exp entropy of served
  (tree, leaf-set) pairs).
- **Request-time query (the interface WS-4 consumes).** Beyond post-hoc metrics,
  WS-0 must expose a selection-time signal: given an incoming `(theme, cell,
  reader/family history)`, return which of the reader's existing stories are most
  similar and how *saturated* the cell is for that theme. This is what lets WS-4
  decide "different tree" vs "harder leaf differentiation." It reuses the same
  distance functions as the metrics, over the reader's `storybook_version`
  history.
- **Harness.** A `nox` session runs a fixed (skeleton x theme-brief) panel,
  including the same skeleton x multiple briefs, through `fill_skeleton` +
  `run_story_gate`, emits the suite, and a CI guard fails on drops. Per-family
  metrics from `storybook_version` history.
- **Serves:** every workstream (their success metrics live here); directly gates
  WS-4.

### WS-1: Leaf-diversity verification + theme parity (re-scoped)

- **Goal:** confirm two fills of one tree are genuinely different leaves (not
  templates), that the requested theme is woven in, and bring the skill path to
  parity. The automated theme wiring is shipped; the gap is verification and
  genuine leaf variation.
- **Approach:** add the anti-template guard (WS-0) as a check alongside Stage 1;
  strengthen the fill instruction to re-imagine each leaf for the theme, not
  substitute nouns; add a theme step to the `cyo-author` `SKILL.md` (the brief is
  already in `authoring_metadata`). **Metric:** anti-template guard passes;
  theme-incorporation > 90%.
- **Serves:** [K11](capability-register.md), [K13](capability-register.md).
- **Precondition note (2026-07-18, WS-0 labels-are-leaves decision):** choice
  labels are leaf content, stripped from `structure_fingerprint` and folded into
  the ATG's leaf distance
  (`docs/planning/ws0-label-fingerprint-evaluation.md`). The ATG's same-tree
  precondition is now genuinely label-free: `select_atg_comparison_partner`'s
  slug-matched pairs no longer raise `ValidationError` merely because the
  automated fill rewrote choice labels per theme (the shipped `fill.md`
  contract). This removes the only nominal byte-level check that a fill did
  not change what a choice *means*; per-choice label-intent fidelity (does the
  rewritten label still match the frozen action-semantic of the original
  choice?) is a Stage 1 fidelity-reviewer extension, not a fingerprint concern.
  Per the evaluation's supervisor sign-off (section 8), that extension was a
  **hard prerequisite** on wiring the ATG into the production pipeline.
- **Delivered (2026-07-18): the label-intent prerequisite.**
  `run_semantic_fidelity_check` (`moderation/fidelity_review.py`) now sends each
  choice's original and final label alongside the beat/prose pairs in the same
  aggregate review call, and the reviewer flags a fill when a rewritten label
  changes what the decision means (an inverted "go left" -> "go right", or
  "trust the stranger" -> "attack the stranger"). It runs even for a node whose
  body was not a FILL directive but whose choice label was reskinned. This
  restores, on exactly the artifacts production creates, the semantic guarantee
  the removed byte-level label check only nominally provided; it stays advisory
  (fails open), one signal among several, consistent with the reviewer's
  existing design. The sign-off prerequisite is satisfied.
- **Delivered (2026-07-19): the WS-1 body (D1/D2/D3).** Per the sprint design in
  [ws1-leaf-diversity-sprint-design.md](ws1-leaf-diversity-sprint-design.md)
  (Fable-designed, Opus-signed-off section 10): **D1** wires the anti-template
  guard into `moderation/pipeline.py::run_moderation_pipeline` as an advisory,
  fail-open check (new `moderation/leaf_diversity.py`, new
  `diversity/history.py::load_version_blob`). It loads the family's most recent
  prior fill of the same skeleton, excludes the just-persisted draft from its own
  history (the load-bearing self-exclusion: the uncommitted draft is visible to
  the same-transaction query and would otherwise self-select and FAIL at distance
  ~0), and on an ATG `FAIL` emits per-node soft-`FLAG` findings that ride the one
  existing bounded repair, then routes to the human guardian. It never blocks,
  auto-rejects, or publishes; a `SQLAlchemyError` from its two reads propagates to
  the worker rollback/retry rather than being swallowed. **D2** strengthens
  `generation/templates/fill.md` to require genuine per-node re-imagining (the
  find-and-replace-survivable-prose test) rather than noun substitution, with the
  safety/structure "must not change" block and the untrusted-input fence held
  byte-identical. **D3** adds a theme step (2b) to `cyo-author/SKILL.md` for
  skill-path parity, stating the same re-imagine contract and fencing the brief as
  untrusted data. Still open (unchanged): per-band ATG threshold calibration (the
  guard stays advisory until then) and brief-passing into the guard.

### WS-4: Similarity-driven, escalating selection (consumes WS-0)

> **Status (2026-07-18): request-time consumption delivered.**
> `generation/skeleton_match.py::select_skeleton_for_cell` takes an optional
> `similar_usage` map and blends it with recency via
> `weight = 1 / (1 + recent + 3*similar)`: a similar-theme reuse of a tree is
> de-weighted like 3 plain recent uses. The `3` penalty is a starting
> heuristic, not calibrated data; it is tunable once WS-0 metrics accumulate
> (mirrors the `_HARD_BANDS`-style heuristics elsewhere in
> `story_requests/authoring_plan.py`). The `_weight` novelty floor is
> preserved: no candidate is ever fully excluded.
> `story_requests/authoring_plan.py::_resolve_skeleton_fill`'s auto-pick path
> (never the admin override path) calls
> `diversity.query.similarity_context` and threads
> `similar_count_per_slug` into the pick. When the cell escalates to
> `DifferentiationLevel.LEAF` or `CATALOG`, the plan result carries a
> non-blocking warning and an `selection.cell_theme_saturated` info log
> (band + level), for the WS-8 catalog flywheel to consume later. `CATALOG`
> only warns and logs here; it does **not** grow the catalog itself, that
> auto-growth is WS-8's job, not WS-4's. A `family_id=None` (admin/catalog)
> request is unaffected: `similarity_context` returns an empty history, every
> similar count is 0, and no warning appears, exactly the pre-WS-4 behavior.
> Still open: the leaf/element differentiation push itself (WS-1/WS-2/WS-5)
> and any per-band tuning of the `3` penalty.

- **Depends on WS-0.** Selection is driven by the perceived-similarity metric, so
  WS-0 comes first; WS-4 is the first thing that consumes it.
- **Premise: reuse is unavoidable.** We cannot author a unique tree per request;
  with K skeletons per cell and unbounded requests, trees repeat by construction.
  The job is to *manage* reuse so no reader feels the repeat, not to eliminate it.
- **Mechanism, escalate differentiation with similarity pressure.** On a new
  request, measure how much similar content the reader (and family) already has in
  that cell, applying the WS-0 metric to the request's theme against prior
  stories:
  - **Low pressure (a second dragon story):** differentiate at the *tree* level,
    prioritize a **different skeleton** in the cell. A fresh tree alone makes it a
    new adventure.
  - **High pressure (the tenth dragon story, the cell's skeletons exhausted for
    this theme):** the trees are used up, so escalate to *leaf/element*
    differentiation, push harder on tone, cast and relationships, setting
    sub-elements, pacing, and ending mix (WS-1/WS-2 leaf variety, WS-5 state and
    ending variation) to keep it fresh on a necessarily-reused tree.
  - **Saturated even there:** grow the tree catalog (WS-5 mutation, WS-8 flywheel).
- **Approach:** extend `skeleton_match.py` from slug-recency to a similarity-aware
  pick, de-weight a skeleton by its structural + thematic proximity to what the
  reader already has (not raw recency alone), and raise a
  "needs-leaf-differentiation" signal to the fill when the cell is saturated for
  this theme. Keep the `_weight` novelty floor.
- **Scope:** primarily per reader/family (the UX concern is a reader's own
  repeats); the same metric can also inform library-level diversity.
- **Serves:** [K3](capability-register.md), engagement. **Metric:** perceived
  similarity between a reader's consecutive same-theme stories, down.

### WS-2: Parameterize the catalog for safe, auditable leaves (absorbs "packs")

- **Goal:** make leaf variation *auditable* and its safety enforceable per band,
  **without** turning the fill into slot substitution.
- **Approach:** generalize the pilot: a per-skeleton theme contract declaring
  what may vary (world, cast, props, tone) with per-band/per-slot safety
  constraints, plus character/tone packs as slot-value libraries. Crucially, the
  contract **bounds and audits** the reskin; the leaf prose is still **generated
  fresh per node** (as `fill.md` does today), never filled by lookup, or it
  becomes the dog-for-cat template WS-0 is built to fail. Reconcile the label
  policy with `fill.md` (labels are content with a frozen action-semantic, not
  frozen strings; the pilot froze them, a step back). Payoffs: measurable
  incorporation, crisper Stage 1 fidelity (fewer reskin false-positives that burn
  the shared `max_repairs=3` budget), per-slot safety.
- **Serves:** [K3](capability-register.md), [K11](capability-register.md),
  [K13](capability-register.md). **Metric:** anti-template distance up; Stage 1
  false-positive rate down.

### WS-5: Structure and state variation within the ADR-011 grammar (scaling)

- **Goal:** new and mutated trees + state variety, for when leaf diversity alone
  no longer holds uniqueness up (heavy readers, larger per-cell libraries).
- **Approach:** cheap **mutation operators** on verified trees first (sibling
  subtree swap; re-map which reconvergent leaf carries which ending within the
  valence set; prune/graft within the envelope; vary decisions-per-path in 4-8;
  **vary Tier-2 variable semantics and condition-gated routes**). Every mutant
  re-runs the full gate. A grammar-based composer is the larger second step.
- **Serves:** [K3](capability-register.md). **Metric:** distinct trees per cell.

### WS-6: Harden `fresh_generation` as the flywheel feed

- **Goal:** bespoke plots and a supply of new verified trees. Output persists via
  WS-8 rather than being consumed once. Strictest gating (weakest safety posture).
- **Serves:** [K11](capability-register.md); gated by [K13](capability-register.md).

### WS-8: Catalog flywheel (highest ceiling)

- **Goal:** grow the tree catalog with usage, not authoring budget.
- **Approach:** promote any gate-passed, human-approved fresh (WS-6) or composed
  (WS-5) tree via the neutralize transform (`out/pilot/_neutralize.py`) into the
  parameterized catalog, behind a human structure-approval step.
- **Serves:** [K3](capability-register.md). **Metric:** net new trees per month.

### WS-7: Request interpretation and expectation-setting (delivers K19)

- **Goal:** reflect the request back before generation, what is built in vs set
  aside and why, and provide the rejection path for a theme a tree cannot carry.
- **Approach:** interpret `premise` into structured intent with a disposition per
  element; persist and return it in kid language and guardian detail. Consumes
  WS-2's contract for precise dispositions and per-skeleton theme-compatibility.
- **Delivers:** [K19](capability-register.md) (design record). **Also serves:**
  [K11](capability-register.md), [K12](capability-register.md); gated by
  [K13](capability-register.md).

## 6. Sequencing

```
WS-0 (metrics; defines "feels like a new adventure")
   |
   +--> WS-4 (similarity-driven, escalating selection)   consumes WS-0; first action
   +--> WS-1 (leaf-diversity verification + theme parity)   proves leaves differ
          |
          +--> WS-2 (auditable parameterized leaves; reconcile labels)
                 +--> WS-7 (request interpretation)
   +--> WS-5 (structure/state variation)  --feeds--> WS-8 (catalog flywheel) <-- WS-6
```

The operating model is a differentiation ladder driven by similarity pressure:
WS-0 defines "feels like a new adventure"; WS-4 reads it per request and picks a
**different tree** while trees remain, then calls for **harder leaf/element
variation** (WS-1/WS-2/WS-5) once a cell is saturated for a theme; WS-5/WS-8 raise
the structural ceiling when even that saturates. WS-0 is therefore a hard
prerequisite for WS-4, not parallel to it.

## 7. Safety invariants (hold across all workstreams)

1. Neither a theme nor a leaf can change the gate-verified structural properties,
   the fail-state policy, the reading band, or the ending kind/valence policy. The
   frozen safety object is the ADR-011 constraint grammar, enforced by the gate on
   **every** tree and every fill.
2. Every generated story passes the full `validator/` gate and `moderation/`
   review before publish. No novelty exception.
3. Per-band content guarantees ([K13](capability-register.md)) are enforced by the
   structure + the gate, never by trusting the theme brief. Theme freedom is
   bounded per band, per slot, in the theme contract (WS-2), not left open.
4. Untrusted-input handling (OWASP LLM01) covers **derived** artifacts: a
   theme-derived world bible and the WS-7 reflected interpretation re-enter other
   prompts (cover-art in `covers/`, repair, the kid-facing echo) and must be
   fenced at every reuse, not only at intake.
5. **Novelty floor.** Selection never fully excludes an eligible option (the
   `_weight` nonzero floor). A rating- or learning-driven selector (WS-4) may set
   a quality floor but must keep an exploration/novelty bonus, so optimizing
   [K18](capability-register.md) ratings can never homogenize the catalog.

## 8. Current state

- **Pilot built and proven** (`out/pilot/`): one parameterized skeleton filled for
  two new themes (space station, dino dig), both gate-passing and non-lethal. It
  demonstrated a **structured, auditable** binding.
- **Pilot cautions, now WS-2 requirements:** (a) it froze `choices[].label`, but
  `fill.md` rewrites labels, labels are content; (b) a slot contract must bound
  and audit the reskin, not become a fill-in-the-blank template, or it produces
  the dog-for-cat failure WS-0 fails.
- **Next:** WS-0 (define and measure "new adventure") is the true first step;
  WS-4 and WS-1 are the cheapest immediate wins.

## 9. Open questions / ADR candidates

- **ADR-019 candidate:** "Parameterized skeletons and theme-driven fills." Ratify
  the parameterization scheme, the theme-contract format (per-band/per-slot safety
  constraints, per-skeleton theme-compatibility), the label policy, and the rule
  that leaves are generated fresh (not substituted), before migrating the catalog.
- Do fixed and parameterized skeletons coexist, or is parameterization the target
  end-state? Where does the theme contract live?
- WS-8 promotion bar: what human approval gates a new tree into the catalog, and
  how is its safety re-proven at promotion?
- How much theme freedom is safe per band without a human theme-review step (a
  WS-2 blocker, not an afterthought)?
