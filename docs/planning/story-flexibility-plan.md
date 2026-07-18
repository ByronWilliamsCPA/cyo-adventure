---
schema_type: planning
title: "Story Flexibility and Diversity Plan"
description: "Strategy for expanding story diversity beyond the current fixed-skeleton model:
  wire the requester's theme into the fill, parameterize skeleton beats so one structure yields
  many themed stories, add character/tone packs, make selection diversity-aware, compose stories
  from reusable structural modules, and offer a fresh-generation novelty tier, all while preserving
  the gated safety guarantees."
tags:
  - planning
  - architecture
  - generation
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Record the problem, design principle, and phased workstreams for increasing story
  flexibility so the concepts are not lost and each change can be planned and executed with full
  context. Companion to the parameterized-beat pilot under out/pilot/."
component: Strategy
source: "Design discussion 2026-07-18 following the initial story-inventory run; current-state
  exploration of skeletons/, generation/, story_requests/, and the cyo-author skill."
---

> **Status: Active (proposal + pilot underway).** The parameterized-beat pilot
> (Phase 2 proof-of-concept) is built under `out/pilot/`; nothing here is wired
> into the live fill path yet. This document is the design record; the
> architectural decision it implies is an ADR-019 candidate (see Open questions).

---

## 1. Problem

The story pipeline turns a guardian/kid request into a published Storybook by
**filling a pre-authored skeleton** with prose (`generation/`, the `cyo-author`
skill). Each skeleton is a story graph whose node bodies hold
`<<FILL role=... words=... beats='...'>>` directives. The intent was that a
skeleton fixes *structure* and the fill supplies *prose*. In practice the
`beats=` payloads hard-code a **specific, fully-cast story**, not just a shape.

Evidence (from the shipped catalog):

- `the-cave-of-echoes`: "Maya and her dog Biscuit slip into the sea caves under
  the old lighthouse at low tide; three dark openings breathe cool air..."
- `the-night-market`: "Milo and his cousin Ada... a small pangolin curled into a
  ball; her name is Pip... she lost her basket with her wish paper, her golden
  string, and her little candle."

Named characters, named settings, specific props, a fixed beat sequence, and
theme-specific ending titles. Two consequences:

1. **Filling varies prose only.** Two fills of the same skeleton differ in voice,
   word choice, and reading-level tuning, but tell the *same story* with the same
   characters, plot, setting, and endings.
2. **The requester's theme is ignored.** A whole-skill grep found **no use of
   `theme_brief` / premise in the fill**. A kid who asks for "a story about
   dinosaurs" in a given cell receives one of that cell's fixed skeletons,
   reworded, never a dinosaur story.

Net: variety today equals **(number of skeletons per cell) x (prose variation)**.
With 3-4 skeletons per cell, repeated requests recycle the same handful of plots.
This is a direct risk to the engagement and replay goals in
[project-vision.md](project-vision.md) and undercuts capability
[K11](capability-register.md) (express interests and initiate a request in kid
terms) because the expressed interest does not shape the result.

## 2. Why it is built this way (the tradeoff to preserve)

Fixed beats are what make the gated pipeline's guarantees cheap. Because the fill
is a bounded, reviewable task, the deterministic `validator/` gate and
`moderation/` review can be thorough, and the per-band content guarantee
([K13](capability-register.md): no death endings in young bands, etc.) is
provable. Any diversity lever **must keep these guarantees**. The design
principle below is what makes added variety safe.

## 3. Design principle: freeze structure and safety, vary content

Every lever in this plan separates the two axes of a story:

- **Structural axis** (branching shape, choice/ending topology, fail-state
  policy, reading-level band): stays fixed and gate-verified. A theme can never
  change it. This is where safety lives.
- **Content axis** (characters, setting, props, tone, prose): the free surface a
  theme fills in.

The parameterized-beat pilot is the reference implementation: it rewrites beats
and ending titles to `{SLOT}` placeholders while leaving ids, choices, targets,
roles, word budgets, and every ending's `kind`/`valence` byte-identical to the
source, so `check_skeleton` still passes and no theme can introduce (for example)
a death ending in an 8-11 story.

## 4. Two axes of diversity

| Axis | Question | Levers |
|------|----------|--------|
| Thematic | What is the story about? | theme_brief wiring, parameterized beats, character/tone packs |
| Structural | How does it branch? | composable modules, topology variety, fresh generation |

Perceived novelty needs both: re-skinning the same shape helps thematic variety
but two stories in a cell still branch identically until the structural axis
moves too.

## 5. Workstreams (phased)

Ranked by impact x tractability. Each names the capability IDs it serves.

### WS-1: Wire `theme_brief` into the fill (foundation)

- **Goal:** the fill consumes the requester's theme (names, setting, tone) so the
  expressed interest shapes the story. Highest impact; prerequisite for WS-2/3.
- **Approach:** add a theme-binding step to the `cyo-author` skill and the
  automated fill prompt: read `theme_brief` (already carried in the job's
  `authoring_metadata`) plus any skeleton theme contract, resolve a concrete
  "world bible" (protagonist, companion, setting, props), then fill each node
  binding beats to that world. On a fixed (non-parameterized) skeleton the brief
  reskins surface flavor only; on a parameterized skeleton it drives the slots.
- **Safety:** the brief is already screened at intake (`story_requests/`); the
  fill must never let the theme override structure, fail-state policy, or band.
- **Effort:** moderate (skill + prompt change, no schema change). **Serves:**
  [K11](capability-register.md), [K13](capability-register.md).

### WS-2: Parameterize the skeleton catalog

- **Goal:** one structure generates many themed stories. Diversity becomes
  (#skeletons per cell) x (#themes) instead of a fixed plot count.
- **Approach:** generalize the pilot (`out/pilot/`): neutralize beats to slots +
  a per-skeleton theme contract declaring slots and their safety constraints.
  Migrate incrementally (one skeleton per cell first), keeping fixed skeletons
  alongside during transition. Structural identity to the source is verified by
  diffing everything except beat/title text.
- **Safety:** fail-state policy and ending kinds/valences stay baked into the
  fixed structure; slots parameterize content only. `check_skeleton` and the full
  gate must pass for every theme binding.
- **Effort:** high (per-skeleton authoring, plus WS-1). **Serves:**
  [K3](capability-register.md), [K11](capability-register.md),
  [K13](capability-register.md).

### WS-3: Character, setting, and tone packs

- **Goal:** orthogonal variety knobs the theme binding draws from.
- **Approach:** formalize the ad-hoc tone notes already in some beats
  (`the-night-market`: "warm and twinkly, never spooky") into an explicit,
  band-bounded tone knob (cozy / eerie / comedic / adventurous), plus a curated
  library of protagonist archetypes and companions.
- **Effort:** low-moderate. **Serves:** [K11](capability-register.md),
  [K13](capability-register.md).

### WS-4: Diversity-aware selection

- **Goal:** stop serving the same thing; a family's library spans structures and
  tones, not three mysteries.
- **Approach:** extend the existing recency-weighted matcher
  (`generation/skeleton_match.py`, already de-weights recently used skeletons per
  family) to also de-weight recently used **themes, topologies, and endings**,
  with a per-family novelty budget.
- **Effort:** moderate (builds on existing recency infra). **Serves:**
  [K3](capability-register.md), engagement metrics in
  [project-vision.md](project-vision.md).

### WS-5: Composable structural modules ("beat-bank")

- **Goal:** structural novelty, not just re-skins. Two stories in a cell can
  differ in shape.
- **Approach:** build a library of reusable structural modules (a sort, an
  explore-and-choose track, a bottleneck reveal, a gauntlet checkpoint) that a
  generator composes into a fresh graph per request. Productionizes the
  generator-script pattern used to build `the-cinderwick-exchange`, and can reuse
  the catalog region primitives (`skeleton_catalog.build_catalog_region` /
  `splice_region`). Every composed graph runs the full gate, including the L2
  config walk and the new L2-13 scale advisory.
- **Effort:** high (new subsystem). Highest ceiling. **Serves:**
  [K3](capability-register.md).

### WS-6: `fresh_generation` novelty tier

- **Goal:** maximum variety for requests where a bespoke plot matters more than
  structural guarantees.
- **Approach:** tune and harden the existing no-skeleton, fully-LLM-authored path
  (already present in the pipeline as an alternative to `skeleton_fill`), with
  stricter gating and moderation because there is no pre-verified structure.
- **Effort:** moderate-high (mostly gating/moderation tuning). **Serves:**
  [K11](capability-register.md); gated by [K13](capability-register.md).

## 6. Sequencing

```
WS-1 (theme_brief wiring)  ->  WS-2 (parameterize catalog)  ->  WS-3 (packs)
        |                              |
        +--> WS-4 (diversity-aware selection) can start in parallel after WS-1
        +--> WS-5 (structural modules) is an independent, larger bet
        +--> WS-6 (fresh-generation tier) is independent; useful as a novelty escape hatch
```

WS-1 is the unlock: it is cheap, it independently raises perceived variety on
today's fixed catalog, and WS-2/3 have little payoff without it. WS-4 protects
the gains. WS-5 and WS-6 are larger, independent bets for structural novelty.

## 7. Safety invariants (hold across all workstreams)

1. A theme can never change structure, choice/ending topology, fail-state policy,
   or reading-level band. Content axis only.
2. Every generated story (any theme, any composition) passes the full
   `validator/` gate and `moderation/` review before publish. No exceptions for
   novelty.
3. Per-band content guarantees ([K13](capability-register.md)) are enforced by
   the fixed structure, not by trusting the theme_brief.
4. The theme_brief is untrusted requester input (OWASP LLM01): screened at intake
   and never allowed to inject instructions or override the gate.

## 8. Current state

- **Pilot built** (`out/pilot/`, committed): `the-cave-of-echoes.parameterized.json`
  (64 nodes, structurally identical to the source, passes `check_skeleton`, no
  theme can introduce a death), a 73-slot theme contract, three worked bindings
  (sea caves / derelict space station / fossil-canyon dig), and the reproducible
  neutralize transform.
- **Next:** the end-to-end proof, fill the parameterized skeleton for two distinct
  themes and run both through `run_story_gate.py` to demonstrate one structure ->
  multiple gate-passing stories. This exercises a manual stand-in for WS-1's
  theme binding.

## 9. Open questions / ADR candidates

- **ADR-019 candidate:** "Parameterized skeletons and theme-driven fills."
  Ratify the parameterization scheme, the theme-contract format, and how
  `theme_brief` binds to slots, before migrating the catalog (WS-2).
- Do fixed and parameterized skeletons coexist permanently, or is parameterization
  the target end-state for the whole catalog?
- Where does the theme contract live: in skeleton `metadata`, a sibling file, or
  a new field? (The pilot uses a sibling `.theme-contract.md` for now.)
- How much theme freedom is safe per band without a human-in-the-loop theme
  review step in addition to intake screening?
