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
   measured so far. Refines AL-156's proposed change.
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
2. The UW-C89 calibration rulings (review Part 8) interact: `words=lo-hi` ranges and the
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
deterministic checks (UW-C85..C83), so the review side automates the same way.

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

---

## 10. Pilot results (2026-08-09, executed same day)

The section-6 pilot ran end to end: the narrative contract for `the-lost-mitten` (committed,
NC-checked), three validated bibles, seeded device selections, and six new fills (three arm
B, three arm C) by isolated authors against the three control fills. All nine fills pass
`check_fill_integrity` first try; all pass the full gate with no blocking findings, no
safety flags, and advisory counts at or below control. The NC layer caught two real errors
before any prose existed (a contract omission and a homograph denylist hit on "wound around
a bough"), and the selection-vector fingerprint separates arm B's fills while collapsing the
beat-identical control to one fingerprint, proving the family-guard key discriminates.

### Scores

| Measure | A (control) | B (obligations+bible) | C (free) |
| --- | --- | --- | --- |
| PS mean (pre-registered null: barely moves) | 0.597 | 0.562 | 0.560 |
| Recognition node (kid test) | node 2 | node 6 (past hub, margin met on rated pair) | node 7 |
| One-story-to-three scale (control 1.5) | 1.5 | 2.5 | 3.0 |
| Twist called at the setup node? | yes, confidently | yes (retcon unpredicted) | no |
| Clue-device distinctness (pairwise, 0-3) | 0 | 2 (a-c pair FAILED at 1/3) | 3 |
| Twist-mechanism distinctness | 0 | 0 (mechanism locked) | 2 |
| Label distinctness | 0 | 2 (best) | 1 (regressed to template, 3 verbatim collisions with control) |

Arm B **failed both pre-registered distinctness margins**; arm C passed both. But the causes
are precisely attributable, and neither says "abandon obligations":

1. **B's clue failure is a bible-input failure, not a format failure**: bibles a and c were
   authored with near-identical device kinds (flattened grass vs parted clover; yarn strand
   vs wool wisp), so the a-c pair collapsed to noun-swap. The fix is the proposal's own
   Mechanic Divergence metric applied AT BIBLE GENERATION across bindings, with a wider
   device-kind taxonomy to draw from.
2. **B's twist failure is by construction**: `locked_outcome` pinned the reveal mechanism
   (never-lost-in-carried-container), so all three twists shared it. The contract's own
   `premise.resolution_space` already lists three mechanisms; the fix is selecting the
   ending MECHANISM per request from the resolution space (a selection-vector entry) while
   the tier keeps kind/valence/affect locked. Arm C demonstrated the value: its one
   mechanism-changed twist (third-party recovery) was the only unpredicted twist in the
   pilot.
3. **C's win carries the disqualifier the proposal predicted**: the three free authors
   independently converged on a shared attractor set (false-clue retcon 3/3, nudge-and-catch
   retrieval 3/3, cozy-container "napping" reveal 3/3, near-verbatim "boing boing" 2/3),
   regressed the label surface to the control's template including three verbatim label
   collisions, and held safety by prompt alone. Free invention diversifies pairwise while
   converging on attractors, is unsteerable per family, and offers nothing deterministic to
   check. Pairwise margins cannot see attractor convergence; a sibling-convergence check
   (device appearing in 2+ sibling fills) must complement them.
4. **Residual recognition leaks are ritual phrases** in labels and dialogue ("Team time",
   "One, two, three, reach it together", "boing boing"): a checkable n-gram-overlap class
   against sibling fills, not a format problem.

### Ruling recommendation

The dial lands at **B-plus**: obligations + bible for coherence, safety, steerability, and
checkability (every one of which the pilot confirmed: first-pass fidelity, zero safety
findings, NC catching errors pre-prose, discriminating fingerprints), amended with the
freedom C proved valuable, delivered through validated machinery rather than trust:

1. Bible generation enforces cross-binding device-kind diversity (MD at bind time, wider
   taxonomy per device category).
2. Ending mechanism selected per request from the contract's `resolution_space`;
   `locked_outcome` locks kind/valence/affect only.
3. A sibling-convergence check and a ritual-phrase n-gram check join the drafting-loop
   audits (complementing, not replacing, the pairwise margins).
4. Everything else in the proposal stands as piloted.

Re-run the same three-arm protocol once amendments 1-3 exist; the pre-registered margins
stay the same, and arm B-plus must pass what arm B failed. Measured gaps to close in that
rerun: two-rater fidelity agreement (this pilot used single raters) and the RL-13 FK drift
at 3-5 observed in all arms including control.

---

## 11. Higher-difficulty pilot: the-clocktower-cipher at 10-13 (2026-08-09)

Owner-directed second pilot after the B-plus amendments landed: the amendments were built
(`check_bible_diversity.py` with MD and near-noun-swap detection; NC-7 selection validation
with per-request ending mechanisms; `check_sibling_fills.py` shared-gram detection), then
exercised end to end on a 26-node, 8-ending, mixed-valence 10-13 mystery with a 6-way and a
4-way merge. The pipeline was fully agentic: an agent authored the 31-fact narrative
contract (first-run NC pass, zero warnings, including an elegant per-room re-establishment
of the cipher hint that makes the 4-way merge honest on every path); an agent authored three
themes (harbor observatory, carousel pavilion, river lock-house) through bind_theme, NC, and
the MD gate, all first-run green at MD 0.410 per pair; selections rotated a distinct
mechanism per ending per binding; three isolated fills all passed integrity and the full
gate first try with zero safety flags at 3.1-3.2k words each.

### What held up

- **Coherence, safety, cost, and checkability scale.** First-pass integrity 3/3, no
  blocking findings, no safety flags, advisory profile equal to the band's norm, at 2.4x
  the node count and a recognition-capable band. The agent-authored contract and the
  agent-authored themes both passed their gates without human repair.
- **Amendment 1 worked where it could bite**: the cipher FORM, the one device category with
  full kind freedom, scored 3/3 distinct across all pairs (phonetic substitution vs ordinal
  lookup vs modular arithmetic), the pilot's standout.
- **Amendment 2 worked**: the per-request ending-mechanism margin (>= 5 of 8 different)
  passed for all three pairs (5/8, 7/8, 6/8), and the recognition rater independently
  reported the mechanism variation at e_hero/e_timeout/e_secret as the pair's genuinely
  felt differences.
- **Amendment 3 worked as an instrument**: the sibling-gram check surfaced the exact
  verbatim leaks the raters then confirmed.

### What failed, and why

The clue-analog distinctness margin failed for all pairs (1/3), and the recognition score
came in at 2.0 (verdict at node 2), below the 3-5 pilot's 2.5. The causes are one layer
deeper than the first pilot's, and they are all the same shape: **the obligation contract is
itself a shared prompt across every fill of a skeleton, and anything concrete in it becomes
the new frozen armature.**

1. **Scene devices frozen in contract prose**: the room hint-carriers, the seize-then-
   lubricate remedy, the comic noise-trap safeguard, and the preserved-workshop loft were
   effectively written INTO constraints and forced kinds, so all three books share a single
   scene-device inventory under rotated props (carriers 0-2 of 4 different per pair; remedy
   and loft identical in all three).
2. **Contract-forced kinds consume the MD budget invisibly**: the theme agent measured that
   `kind_must_be` specs freeze most category multisets, leaving MD headroom of ~0.07 over
   the tau; MD passed while the frozen-kind categories stayed frozen.
3. **Contract vocabulary seeds convergent imagery and sentences**: "stepped out for tea
   thirty years ago" verbatim in two books, "Knowing when not to is a skill" in all three,
   ten-plus cross-book phrase templates, cedar smells and ledges recurring; isolated
   authors given the same contract text converge on its phrasing.
4. **The reader surfaces the contract cannot vary are the strongest recognition channels at
   this band**: same-order same-function choice menus landed the same-book verdict at node
   2, and five of eight ending titles are unslotted and therefore byte-identical across
   books.
5. **The gram budget does not scale**: 95 shared 4-grams at 3.1k words against a budget
   calibrated at 500 words; the check needs length normalization.

### The next amendment set (contract hygiene)

1. Obligation strings must be device-abstract: every recurring set-piece (remedy,
   safeguard, cache type, loft furnishing) becomes an invention slot drawing from a bible
   category with real kind freedom; constraints and hints may not name concrete devices or
   imagery. A review rule now; the sibling-gram check catches leakage downstream.
2. `check_bible_diversity` reports per-category forced-vs-free kind headroom so authors and
   generators see where diversity is actually possible; world recipes minimize
   `kind_must_be` to what safety genuinely requires.
3. All ending titles generated under the title contract (none unslotted); selection-time
   check that a title's named props sit on the path that reaches it.
4. A label-surface diversity directive (menus may not share verb frames across sibling
   fills) plus the length-normalized sibling-gram check wired into the fill loop.
5. Band-scaled diversity budgets: recognition capability rises with age; the distinctness
   margins and gram budgets must tighten with band, not stay constant.

### Verdict

The architecture survives the harder cell: safety, coherence, first-pass yield, agentic
authoring, and the two amended mechanisms all held or passed. The sameness ceiling has
moved from the beat layer (pilot 1) into the contract's own concreteness (pilot 2), which
is progress of the intended kind: each iteration relocates the bottleneck into a smaller,
more checkable artifact. The contract-hygiene amendments above are cheaper than the
B-plus set was, and the third pilot should re-run this same cell after they land, with the
same margins plus a menu-surface margin.

## 12. Third pilot: same cell after contract hygiene (2026-08-09)

Re-run of the-clocktower-cipher at 10-13 with the section 11 amendment set fully applied.
Tooling landed first: `--allow-title-rewrite` now treats the storybook title and every
ending title as leaf content; `check_bible_diversity --contract` reports per-category
forced-vs-free kind headroom; `check_sibling_fills` uses a length-normalized budget
(4.0 shared grams per 1000 mean leaf words) plus a menu-frame overlap report; NC-7
validates a per-binding `label_style` and NC-8 warns on unslotted titles. An agent then
rewrote the contract device-abstract (five quotable set pieces became invention slots;
`kind_must_be` reduced to the single safety-meaningful case, the trusted-escort branch;
per-ending title contracts; five label styles) and re-authored the three bibles into the
widened headroom.

### Deterministic results

- **MD moved from 0.41 to 0.90-0.92 per pair** under the same tau (0.34). The headroom
  report shows every multi-entry category with >= 2 free kinds; the pre-hygiene report had
  the three clue-adjacent categories at 0 free entries.
- **Selections**: constrained-first derivation with arm rotation produced 16 devices and
  8 mechanisms per arm, zero mechanism collisions across arms, three distinct cipher forms
  (symbol substitution, pictogram code, clock arithmetic), NC-7 green including
  `label_style`.
- **Fills**: three isolated authors, first-pass integrity 3/3 with full title rewrite
  (three book titles, 24 ending titles, zero frozen-title reuse, zero cross-arm title
  collisions), full gate 3/3 not blocked with zero safety flags, mean 113-132 words/node.
- **Menu frames: 0 shared across all pairs** (pilot 2: the same-book verdict landed on a
  menu). The per-binding label styles closed the menu channel at the deterministic level.
- **Sibling grams: first pass FAILED at 20.4/1000**, worse than pilot 2's 9.0. The trace
  split the causes in two: (a) three residual concrete fact strings (`rooms_mapped` named
  the spiral stair and pendulum ledge; `cipher_decoded` said "substitution" despite the
  freed cipher-form slot; `vault_contents_known` enumerated slot-supplied contents), fixed
  in the contract; and (b) a genuinely new channel: **same-model idiom convergence**.
  "A door stood ajar on a room that smelled of...", "had only stepped out for tea", "the
  climb was shorter than it looked" appear in no input file, yet all three isolated
  authors produced them at the same beats. Device abstraction cannot prevent the sampler
  defaulting to the same staging idiom for the same obligation.
- **The tool-feedback loop closed the gap in one round**: each author received the
  deterministic gram list, rewrote only their own colliding sentences in their binding's
  voice (24-26 sentences each), and the re-run scored **1.2/1000 against the 4.0 budget**
  (4 x2 grams remain, all generic), menu frames still 0, integrity and gate still green.
  This is the production shape: the checker gates, the author revises, no human in the
  loop.
- **PS null held**: 0.541-0.551 per pair (leaf 0.083-0.094; structural and theme pinned
  at 1.0 by design). Leaf similarity is at the noise floor for same-band prose.

### Rater results

**Scene inventory: every pre-registered margin passed on every pair**, and the pilot-2
failure mode (duplicated hint-carrier device kinds) is gone. Cipher form 3/3 distinct
(glyph substitution vs punched-card ordinal lookup vs modular moon arithmetic); room
carriers 11 of 12 pairwise comparisons distinct; remedies 3/3 distinct; ending mechanisms
6/8, 6/8, 8/8 against the 5/8 floor; label voices scored 3.0 ("three coherent,
non-interchangeable label voices, not template rewording"); menu surface distinct on all
pairs with one marginal verb-spine parallel at the a-b hub. The device layer, which failed
in pilot 2, is solved.

**Recognition: margin failed, with real movement.** The same-book verdict moved from node
2 (pre-hygiene) to node 4 on both rated paths, and the pair score moved 2.0 to 2.5, but
the pre-registered bar was "past the node-5 hub or not at all". The a-c pair regressed to
node 2 on a near-paraphrased three-plans opening. The rater's attribution matches the
scene rater's residuals from the other side:

1. **Choice-menu semantics are the book's fingerprint.** Every fork offers the same
   options with the same meanings in the same order (decode / walk the walls / ask the
   keeper; enter now / story first; share / keep / grab). Label styling varied the voice;
   the contract's `choice_semantics` locks the meaning, and a 10-13 reader recognizes
   meaning through any styling.
2. **Scene-function identity in fixed order.** Each node performs the identical function
   at the identical position; the rater's phrasing: "the skeleton is fine; the skeleton
   is visible."
3. **Idiom families survive below the 4-gram floor.** All five watched staging idioms
   (doors ajar, stepped-out-for-tea, short climb, corkscrew stairs, service ladders)
   reappeared in all three books in paraphrased forms the token check cannot see
   ("corkscrewed" a-c, the "come back by daylight, and knock" closing beat 3/3, the
   "language they were learning" thesis sentence). The revision round defeated the
   metric more thoroughly than the phenomenon.
4. **Beat-identical emotional payoffs.** e_hero lands the same arc in both books
   (artifact to town authority, crowd, dead maker's machine runs again, honorary status);
   the mechanism rotation varied the how, not the felt shape.

### Verdict

The contract-hygiene amendments did what they were designed to do: the device layer is
distinct on every margin, the menu-frame and frozen-title channels are closed at the
deterministic level, and the fill loop (gate, revise on tool feedback, re-gate) worked
in one round with no human repair. The sameness ceiling moved again, out of the prose
and device layers into the two things a single skeleton-plus-contract cannot vary by
construction: the decision grammar (choice semantics, scene functions, their order) and
the model's own staging idiom priors. Three consecutive pilots have now each relocated
the bottleneck one layer down: beats (pilot 1), contract concreteness (pilot 2), decision
grammar and idiom priors (pilot 3).

The honest conclusion for the catalog rebuild: **sibling fills of one skeleton converge
to "same adventure, new world", and no amount of downstream hygiene changes that,
because the remaining channels are the skeleton's identity itself.** That reframes the
product question rather than the tooling question: bindings of one skeleton are a
series format (and read well as one; the recognition rater judged the formula GOOD at
this band when framed as a series), while true different-book diversity comes from
different skeletons, which is what the catalog rebuild is for. Two cheaper mitigations
remain open if same-skeleton distance is still wanted: per-fork semantics pools rotated
at selection time (the mechanism treatment applied to decisions), and an idiom-family
check below the 4-gram floor. Both are registered; neither blocks the rebuild.

## 13. Model-tier study: which model can fill a contract? (2026-08-09)

Owner question: the fill model is the dominant recurring cost in the pipeline, so the
minimum success threshold per model tier matters. Haiku would be preferred on cost;
Sonnet is the expected practical floor. The third pilot's inputs (hygiene-passed
contract, three bibles, three selections, three bound skeletons) were held fixed and the
fill step was re-run twice more, once with Haiku 4.5 and once with Sonnet, three isolated
authors each, identical prompts. With the frontier run that is nine books from one
skeleton: three tiers x three bindings.

### First pass, before any revision

| Measure | Haiku 4.5 | Sonnet | Frontier |
| --- | --- | --- | --- |
| Fill integrity (structure frozen, markers gone, word band) | 3/3 | 3/3 | 3/3 |
| Full validator gate, blocked | 0/3 | 0/3 | 0/3 |
| Safety flags | 0 | 0 | 0 |
| Title contract compliance | clean | 1 cross-arm collision | clean |
| Sibling shared grams per 1000 (budget 4.0) | 8.5 | 29.7 | 20.4 |
| Menu frames shared | 0 | 0 | 0 |
| Wall clock per book | 2-4 min | 6-7 min | 7-9 min |

**Every tier clears every hard gate on the first pass.** Structure, markers, word bands,
topology, safety: none of it separates the tiers. The deterministic floor for *validity*
is already met at Haiku, which is the single most important result here, because it means
the gate is doing its job independent of author strength.

The tiers separate on two softer axes:

- **Reading-level control (RL-13 advisories, target FK 5.5 +/- 1.5).** Sonnet 67 flagged
  nodes, mean FK 9.17, with 65 of 67 ABOVE 7.0 and none below 4.0: a systematic upward
  drift, writing toward adult prose for a 10-13 band. Haiku 30 flagged, mean FK 5.89,
  scattered 17 high and 13 low: centered on target but less controlled. Frontier 35
  flagged, mean 7.34, leaning high. Sonnet's failure mode is overwriting; Haiku's is
  inconsistency.
- **Convergence, and it is not monotonic in capability.** Sonnet was the MOST convergent
  tier (29.7 per 1000), Haiku the least (8.5). Each tier converges its own way: Haiku's
  top shared grams were near-verbatim quotations of contract strings ("they reseal the
  vault exactly as found", the "not a punishment" framing), i.e. weak paraphrase of the
  spec; Sonnet's were stock staging idioms ("ajar on a room stacked with", "miniature
  version of the", "still be there tomorrow"), i.e. strong genre priors. Capability buys
  better prose, not less sameness.

### After one tool-feedback revision round

Each author received its own tier's shared-gram list and rewrote only its colliding
sentences (the same loop used in section 12).

| Measure | Haiku 4.5 | Sonnet | Frontier |
| --- | --- | --- | --- |
| Sibling shared grams per 1000 | **0.6** | **1.3** | **1.2** |
| Integrity / gate / titles | GREEN | GREEN | GREEN |

**All three tiers pass the full battery after one round, and Haiku scores best on the
gram metric.** Haiku executed the revision instruction correctly, though its edits skew
toward word-swaps over image changes ("We climb the service ladder" became "We ascend
using the service ladder"), which satisfies an n-gram check without changing the picture;
that is a caution about relying on the metric alone, not a failure of the round.

### Cross-model convergence

| Triple composition | Shared grams per 1000, pre-revision | Post-revision |
| --- | --- | --- |
| Same model, three bindings | 8.5 / 20.4 / 29.7 (mean 19.5) | 0.6 / 1.2 / 1.3 |
| Mixed model, three bindings (one per slot) | 3.5 / 4.7 / 6.8 (mean 5.0) | 2.2 / 3.5 / 5.5 |
| Three models, ONE binding (identical inputs) | 14.1 / 14.7 / 27.4 | 12.0 / 12.4 / 26.1 |

Read these carefully; the honest comparison is the pre-revision row, where neither
condition has been optimized. There, **mixing models across sibling bindings cuts
convergence about fourfold** (19.5 to 5.0 per 1000): different models default to
different staging idioms, so assigning different fill models to sibling bindings is a
real, nearly free diversity lever. After revision the ordering flips, because the
revision round optimizes exactly the same-model metric it was given; the correct
conclusion is that **revision is a stronger lever than model mixing, and model mixing is
valuable where a revision round is not affordable** (or as a second, independent lever
stacked on top of it).

The third row is a different measurement: three models given the identical binding still
share 12-26 grams per 1000 after revision. Same setting, same characters, same assigned
devices produce convergent prose regardless of who writes it, which is the section 12
finding restated from a new angle: the inputs, not the author, dominate. The clearest
single illustration is titling. Given identical selections, Sonnet and the frontier model
independently produced "The Unfinished Mirror" (identical) and "Footprints in the Silt" /
"Footprints in Silt" for the same endings, with no shared context.

### Prose quality: the axis that actually separates the tiers

A blind rater compared all nine books author-to-author WITHIN each binding (same setting,
same obligations, so differences are pure craft), not knowing which model wrote which.

| Dimension (1-5) | Frontier | Sonnet | Haiku 4.5 |
| --- | --- | --- | --- |
| Sentence craft | 5 | 4 | 2 |
| Imagery and concretion | 5 | 4 | 2 |
| Character | 4.5 | 4 | 2 |
| Emotional truth | 5 | 4 | 2 |
| Voice consistency and range | 5 | 3.5 | 2.5 |
| Age fit | 5 | 4.5 | 2.5 |
| **Mean** | **4.9** | **4.0** | **2.2** |
| **Ship test** | **ship as-is** | **ship with light edit** | **DO NOT PUBLISH** |

The margin frontier-to-Sonnet is narrow-to-moderate; Sonnet-to-Haiku is wide, and not
close at any node. Mean sentence length tracks the tiers exactly (frontier 13.3-16.4
words, Sonnet 17.7-19.9, Haiku 11.1-12.5), and so does range: the frontier books read as
three different registers (maritime-brisk, fairground-warm, river-vernacular), Sonnet as
one good groove across three books, Haiku as one flat expository register.

Haiku's disqualifying defects, none of which any existing check sees:

1. **Tense instability**, including breaks inside a single paragraph in two of three books
   ("But then the gears bound... Tom's heart sinks. But Sef takes a breath").
2. **The puzzle does not exist.** A cipher mystery whose central mechanic is stated rather
   than performed: "the digits spell out language", "all the clues they've gathered
   resolve here". The frontier books do the arithmetic on the page ("Nine onto eleven
   made twenty; round again, eight").
3. **Narrator moral tags at nearly every ending** ("it taught them what matters more than
   objects", "sometimes the prize is not taking something, but giving something back"),
   the single most condescending move available at this band.

### The architectural finding: obligations are declared, proved coherent, and never verified

The recognition rater found a continuity defect in a Haiku book: `n_open` decodes the
cipher outright, and `n_note`, the node whose entire purpose is that decode, then presents
the same sentence as a fresh discovery. The "solve the cipher" branch delivers nothing.

The contract explicitly forbids this. `n_open` declares
`forbids: [inside_access, cipher_decoded, keeper_met]`. The fill violated a declared
obligation and passed every gate, because **the NC checks run before prose exists**: they
prove the contract's obligations are mutually coherent, and nothing afterwards proves the
FILL honors them. Layer 1 and Layer 2 check topology, safety, reading level, and band
profile; `check_fill_integrity` checks that structure was not mutated. No check reads a
node's prose and asks whether it established a fact the contract forbids there.

This is the highest-value result of the model-tier study, and it is not really about
models: it is a hole in the gate that a stronger author happened to be papering over.
Weaker authors violate semantic obligations more often, so the hole becomes load-bearing
exactly when a cheaper model is introduced. A fill-vs-contract fact audit (does this node
establish anything in its `forbids` set; does it establish everything in its
`establishes` set) is the missing layer, and unlike the diversity work it needs a
semantic judgment per node rather than a token metric, so it belongs to the automated
review panel of section 9 rather than to the deterministic gate.

### Diversity is model-independent

The Haiku tier scored **2.5** on the recognition scale, identical to the frontier tier's
2.5, with recognition landing at node 5 on one path and node 3 on the other (margin
failed, same as the frontier run). Its rater independently named the same primary driver
as the frontier rater did in different words: the keeper-plus-maker pair and the
four-exit hub menu, i.e. decision grammar and fixed scene functions.

**Model tier does not move sameness; it moves prose quality.** Diversity is a property of
the skeleton and contract, prose is a property of the author, and they are close to
orthogonal. That is a useful separation: it means the catalog work (more skeletons,
varied branch arity) and the model-cost decision are independent choices.

One caution on how quality was measured. The comparative rater (nine books side by side)
scored Haiku 2.2 and called it a rewrite; the isolated rater (three books, no reference)
scored the same books 3.0 and called it "one editing pass". **Absolute quality judgments
are more forgiving than comparative ones**, which is a direct restatement of this
project's single-reviewer problem: a reviewer holding one story approves what a
side-by-side comparison would reject. Review surfaces should show a sibling for contrast.

### Recommendation

- **Sonnet is the practical floor for the fill step**, as expected. It ships with a light
  copyedit pass: break the 25-35 word sentences at hazard nodes, cut the "not X exactly,
  closer to Y" tic, and remove two or three narrator-names-the-emotion closers. Its one
  systematic flaw, upward reading-level drift (mean FK 9.17, 65 of 67 advisories above
  band), is correctable by a prompt directive and is worth adding before any Sonnet
  production run.
- **Haiku is not viable for the fill step today**, on prose quality and on obligation
  violations, not on gate compliance. It is viable for cheaper roles in the same
  pipeline: it passed integrity, safety, and topology on every book, executed a
  tool-feedback revision round correctly, and produced the LOWEST sibling convergence of
  any tier. Candidate Haiku roles: selection derivation, mechanical revision rounds
  against a deterministic finding list, and first-pass triage.
- **Mix models across sibling bindings** where a revision round is not affordable: it cuts
  convergence roughly fourfold for free.
- **Do not treat gate-clean as publishable.** All nine books cleared the full gate; three
  of them should not ship. Until the fill-vs-contract audit exists, gate-clean means
  valid, not good.
