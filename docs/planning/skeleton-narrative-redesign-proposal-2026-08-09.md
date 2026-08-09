# Skeleton Narrative Redesign: obligation skeletons with a locked spine and a per-request story bible

**Status**: proposal, awaiting owner ruling
**Date**: 2026-08-09
**Owner directive**: "revise the approach so that the skeletons still provide enough structure
for an llm to generate the story but are less prescriptive on the mechanics and story so we
have greater story diversity. The skeletons should help build unique content not prohibit it."
Goal restated by the owner the same day: high-quality LLM-generated stories; few hand-authored.
**Inputs**: three independent deep analyses (format design, pipeline consequences, evidence and
calibration) over the 2026-08-09 review (Parts 5-7), the same-skeleton diversity experiment,
and the live code. This document is the synthesis; the analyses' full detail lives in the
session transcript and the review doc.

---

## 1. The finding that licenses the change

The reasons beats were pinned at sentence level mostly never held. Audited against the live
gate: **no blocking validator rule reads a beat's semantic content**. Young-band safety lives
in `band_profile.py` ending-kind prohibitions, content-flag ceilings, and the band-mandatory
denylist union; the WS-2 design says it in as many words: "the floor is in the validator, not
the data". SAFE-14 is an empty stub. RL-13 skips FILL bodies. Beats even CAUSED a theme-leak
class (un-slotted world facts: snow, item anatomy, "fireflies chirped"). Of nine historical
justifications, two survive: the fidelity gate needs some target, and one human reviews
everything. Both are addressed below.

Meanwhile the measured cost of pinning is severe and inversely proportional to age band: the
beat-to-prose prescription ratio is 0.83 at 3-5 (the skeleton writes four fifths of a toddler
book in outline), 0.40 catalog-wide, and the strict pilot pushed it above 1.0. The most
templated surfaces are the most reader-visible: choice labels are 2x more identical across
fills than prose (0.463 vs 0.228 unigram similarity) and two of three ending titles are
byte-identical because they carry no slot. Real series do the inverse: Maisy, CYOA, and
Fighting Fantasy fix the frame (format, cast register, scale constants, ending counts) and
vary scene, device, and outcome content per volume.

## 2. The design

**Per-node tiers** on the FILL directive, with `open` as the default for new skeletons:

| Tier | Semantics | Use |
| --- | --- | --- |
| `locked` | today's verbatim beat, byte-compatible | safety-critical scenes; the one image a skeleton's identity depends on |
| `locked_outcome` | outcome propositions locked, scene open | endings (highest repeat-salience, lowest drift tolerance) |
| `pool` | authored variant beats under one outcome contract (SQ-11) | nodes wanting authored craft without a single frozen image |
| `open` | node carries OBLIGATIONS, not scenes | everything else |

An `open` node's contract (in a `.narrative.json` sidecar) declares: narrative `function`
(introduce-stakes, plant-clue, raise-cost, payoff), `entry_state` and `establishes`/`forbids`
fact sets, an affect envelope (target affect, forbidden affects), choice action-semantics,
and an `invention` spec naming what the fill may invent and from where. Choice labels become
`intent` declarations (the semantic of the decision, not a verb-frame template); ending
titles are generated under a title contract.

**The story bible**: a small (~40-string) per-request artifact generated at bind time from
the family's request: world, cast with affordance tables, prop affordances, a device
vocabulary (clue channels, obstacle kinds, help modes, containers), motifs, prohibitions.
It is the sole source of concrete world material for `open` nodes, selected once, seeded,
and `unique_within_story`. Crucially it is **slot-shaped and contract-validated**: every
leaf string passes the existing `validate_slot_bindings` machinery (charset, length,
denylist bundles, band-mandatory floor, legacy-lexicon leak), so the untrusted-brief
crossing keeps its deterministic gate. The theme contract is not deleted but promoted: slots
become identity/texture roles constraining bible generation; `default_binding` survives as a
derived view.

**The shared move library**: catalog-wide named narrative moves with type signatures
("search.empty_but_directional": consumes/establishes/forbids/invents), authored once
(~20-30 moves cover the catalog), referenced by skeletons. This amortizes obligation
authoring below today's per-beat cost and gives the family-scoped guard a cross-skeleton
repetition signal, which is where a reader with three trees per cell actually lives.

**What stays exactly as it is** (the GS1 lesson: free generation fails on countable global
invariants): topology, targets, budgets, depth, `min_complete`, ending kind/valence/count,
content flags, the band-mandatory denylist, reading-level targets, human approval (ADR-005),
and the strict bar. `words=N` becomes a range (`words=lo-hi`); the point target is already
dead letter (the seed's 80/85 vs the band's 28-55 envelope was overridden by every filler).
Structural diversity remains a catalog-time problem (ADR-020 `mutation/`); this change is a
scene-layer program and the ADR must say so to keep the two from being conflated.

**Why not variant pools as the destination**: k authored variants buy k costumes at k times
the authoring cost, exhaust per family, multiply the merge-contradiction surface, and keep
prescription in the skeleton. Pools survive as a tier, not as the program.

## 3. What this fixes by construction

- "Fireflies chirped" and the snow/dew/hot-head divergence become impossible: authored text
  asserts nothing about bible-chosen entities; affordance tables are the only source.
- Merge-node contradictions (8 per large pilot draft, the `hollow-lighthouse` class) become
  a deterministic set-containment check: `entry_state(n)` must be contained in the
  intersection over parents of `entry_state + establishes` (NC-1), plus dead-beat, orphan-
  fact, and reentrant-news checks (NC-2..4). Nothing can check this class today.
- The ATG contradiction dissolves: "differentiate wholesale" vs "depict this exact beat"
  stops being an unsatisfiable pair because the depiction target is gone; the escalation
  ladder selects (excludes served mechanics for this family) rather than only instructs.
- The clue and the reveal can interlock per request (the current format hard-codes the
  punchline to footwear forever), which is mechanics-level divergence inside an identical,
  validated graph.

## 4. Fidelity, safety, and coherence under the new contract

**Fidelity** becomes three layers, deterministic first: (a) obligation checks with no LLM:
`must_mention` slot coverage (promote the existing `_slot_ids_with_body_coverage` warning to
a per-node obligation), `forbid_devices` via the existing `denylisted_bundles` machinery on
filled prose, outcome enums checkable against effects/conditions at Tier-2; (b) structural
fidelity unchanged (`check_fill_integrity`, fingerprint equality); (c) the LLM judge
re-anchored per obligation, returning attributable `{node, unmet, invented}` findings so
repair is targeted, failing CLOSED on the deterministic half (today's judge fails open on
malformed output and repairs against a target the repairer is never shown). The deterministic
surface must widen exactly as much as the depiction target loosens.

**Safety**: the envelope moves from "beats are pre-sanctioned by provenance" to typed,
checkable fields: per-node `forbid_devices` and per-skeleton device kind allowlists become
SAFE-14's first real content, BLOCKING at the gate ahead of moderation; the band-mandatory
floor is applied to filled prose at 3-5/5-8 first (measure false positives on the committed
fills before extending up; the theme-leak 1,771-hits precedent is the caution). Moderation
call count is flat (every node is already screened); what shifts is hit rate, and with
exactly one bounded repair, review load lands on the single human approver. That transfer is
the honest core cost of the program and the reason the deterministic layers above are
prerequisites, not follow-ups.

**Coherence**: per-merge-node entry-invariant lists give the coherence stage per-node
targets; promote coherence review to per-node above an in-degree threshold (data already
computed). The Part 5 mandatory adversarial critique stays mandatory; it is now the only
stage that reads intent semantics.

## 5. Hard prerequisites found in the pipeline (do these before any format work)

1. **The silent fail-open cascade**: every consumer of the FILL directive skips on regex
   non-match (`binding`, `fidelity`, `fidelity_review`, `slotted_surfaces`, plus three
   private regex copies in `mutation/` and `parameterize_skeleton.py`). A format change the
   regex does not match silently disables slot substitution, fidelity, theme-leak scanning,
   and slot-set equality at once, with zero findings. Fix: total parse (unparseable
   `<<FILL` body is a blocking L1 finding), a lockstep test over every consumer, collapse
   the private copies onto `slotted_surfaces.py`.
2. **The theme axis**: `metadata.themes` is unbindable BY DESIGN (binding's
   fingerprint-unchanged post-condition; metadata is not stripped from the fingerprint).
   Fix via a bindable-metadata allowlist checked outside the fingerprint (no digest
   rotation), not via stripping (which rotates every stored manifest). This one fix moves
   the same-skeleton PS floor from 0.50 to 0.30, worth more than any prose improvement
   measured so far. Refines AL-152's proposed change.
3. **Variant/selection fingerprint persistence**: `storybook_version` has no variant
   column and the family guard cannot be expressed with persisted data. One nullable
   `variant_fingerprint` column, stamped at fill, carried on `HistoryEntry`, consumed as a
   third term in `_blended_weight`. Cheapest single diversity intervention available.
4. **Fill feasibility**: 27 of 58 production skeletons already exceed the 32k one-shot
   output cap (worse than AL-046's framing); every repair is a full re-emission; selection
   has no token predicate. Land the feasibility predicate, and design the act-scoped fill
   loop JOINTLY with the story bible: the bible is exactly the cross-act continuity carrier
   the act-scoped loop needs. One design, two consumers.
5. **Metric honesty, pre-registered**: PS cannot see this program (the beat layer is ~0.06
   of PS; the 0.30 same-tree structural term is a constant). Replace the same-tree constant
   with beat-path/selection similarity, add the deterministic Mechanic Divergence metric
   over selection vectors and bibles, and re-baseline the diversity panel, BEFORE the pilot,
   so success is measured by an instrument that can register it.

Storage ruling folded in from the analyses: narrative contracts and variants live in
SIDECARS (registered in `SIDECAR_SUFFIXES`), never node fields (fingerprint rotation) and
never bare metadata (same); if reproducibility requires a schema change, scope it to one
top-level provenance field with a `FIELD_MINORS` entry per ADR-025.

## 6. The pilot (re-specifies SQ-12)

`the-lost-mitten`, three arms on the SAME three bindings with isolated authors: A = control
(the three existing fills), B = obligation contracts (`open` tier), C = maximally free
(role + words range + choice intents only). Six new fills total. Pre-registered margins:
arm B shows a different device on at least 2 of 3 clue nodes for all pairs and a different
twist mechanism on at least 2 of 3 pairs; the recognition index (rerun of the Part 6
protocol; control = recognition at node 1) must move past the reconvergence node; scale
score at least 2.5 vs control's 1.5. Pre-registered null: PS barely moves (proving the
metric gap on purpose). Promotion criteria, all required: distinctness margins met; zero
band-scope violations (single breach halts); first-try gate pass and repair count not worse
than control; two-rater fidelity agreement at least 90% and not below control (the direct
test of the snow/dew ambiguity risk); zero label-laundering across all endings; and the
existing SQ-12 falsification clause. Arm C locates the far end of the dial: if it breaks
budgets where B does not, the dial is at B and that is the pre-registered result.

## 7. Staged sequence

0. **Ship regardless, now**: prerequisites 1-3 and 5 above; free the two slotless frozen
   ending titles; the reentrancy fix (nodes with descendant back-edges get a derived
   `reentrant` flag and a reentry contract in the fill prompt: the shipped seed re-renders
   its loss-discovery beat on every loop today); honest series framing for same-skeleton
   siblings; family-scoped variant memory.
1. **Pilot** (section 6) with the deterministic fidelity layer (must_mention,
   forbid_devices in SAFE-14) and NC-1..4 prototyped on the pilot skeleton.
2. On pass: tier machinery + narrative contract schema + bible generation co-designed with
   act-scoped fill; migrate the PIPELINE, not the catalog (sidecar-presence dispatch, the
   ADR-019 pattern); new and rebuilt skeletons opt in.
3. Move library extracted from the first ten migrations; rollout rides the ruled
   remove-on-replacement rebuild waves, 3-5/5-8 first (highest prescription ratio, smallest
   trees), teen gamebooks last.
4. Then and only then: re-calibrate leaf thresholds and arm the ATG (the recorded
   sequencing trap: loosen, measure, arm; never arm first).

## 8. Open decisions for the owner

1. Adopt the tiered obligation format as the target (this proposal), with pools as a tier
   rather than the program. The alternative sequencing (pools first as a full stage) costs
   more authoring and defers the diversity mechanism; the pilot's arm structure answers the
   dial question empirically either way.
2. The UW-C85 calibration rulings (review Part 8) interact: `words=lo-hi` ranges and the
   CG-3 posture should be ruled with this proposal so the new format is calibrated once.
3. Accept the review-load transfer: deterministic checks widen, but the single human
   approver sees more flagged inventions at first. The pilot measures review minutes per
   book; a budget for that number is an owner call.
4. An ADR should record: scene diversity is a request-time program (this design); structural
   diversity remains catalog-time (ADR-020); and the PS metric change with its
   re-baselining.

---

## 9. Addendum (2026-08-09, owner steer): the automation end-state

Owner framing: the single human reviewer is the structural constraint the project exists to
overcome, and the question is whether this proposal is STILL overly prescriptive given LLM
capability, provided automated review holds the line.

Assessment: yes, in one specific place. The proposal treats the graph as a curated,
human-promoted asset and loosens only the scene layer. That rested on GS1 ("free generation
fails on budgets"), and the strict pilot made GS1 obsolete in a precise way: GS1 was a
ZERO-SHOT failure. With the deterministic gate in the drafting loop, LLM agents one-shot
passed 184- and 251-node skeletons with zero findings in the hardest cells. Tool-in-the-loop
agentic generation holds global invariants that zero-shot generation cannot; the structure
floor is therefore set by the automated review surface, not by LLM capability. The pilot's
adversarial critics were also LLMs, and their findings are largely convertible into
deterministic checks (UW-C81..C83), so the review side automates the same way.

**End-state**: the skeleton becomes a generated, verified artifact. The fixed layer shrinks
to what encodes child-development policy rather than story content: cell contracts (budgets,
grammar, outcome economy, walk floors, safety floors), the deterministic gate suite (strict,
audits, NC-1..4, the consequence and honesty checks), closed vocabularies (device kinds,
fact grammar, move library), and ADR-005's approval points. Graphs, obligations, bibles, and
prose are all drafted by authoring agents and proven by the pipeline: generated brief,
architect agent with the structural harness, strict gate plus in-cell audits, an AUTOMATED
adversarial panel (the pilot's critic rubrics productionized), then promotion. This also
dissolves the last diversity ceiling: the PS structural 0.30 moves only with different
graphs, and agentic generation makes new graphs cheap, turning each cell from three frozen
trees into a growing population (the ADR-020 flywheel with authoring agents in the mutation
engine's role).

**The human bottleneck, decomposed**: guardian approval is per-family and distributed by
construction (a feature, not a bottleneck). The singleton admin's role shrinks from catching
to sampling: one promotion decision per generated skeleton, spot audits at a rate tuned to
measured automated-panel precision, moderation escalations only. Promotion criterion for the
panel itself: its approve/reject decisions must agree with human spot-checks at an
owner-set rate before the human steps back.

**The one non-negotiable prerequisite**: SAFE-14's device floors and the band-mandatory
denylist land as BLOCKING gate content before graphs go agentic. Generated structure plus
generated scenes means provenance-based safety is fully gone; the floor must live entirely
in the validator, which the evidence analysis showed is where it always really was.

**Sequencing consequence**: the staged plan in section 7 is unchanged as the path; this
addendum changes the declared destination. Stage 2's "migrate the pipeline, not the catalog"
now reads: the rebuild waves are executed by authoring agents through the full automated
gauntlet, the automated adversarial panel is built during stage 1 (it is the pilot's critic
prompts plus the pre-registered rubrics), and the move library plus NC checks are the
architect agent's guardrails rather than aids to a human author. The catalog rebuild and the
automation end-state become the same program.
