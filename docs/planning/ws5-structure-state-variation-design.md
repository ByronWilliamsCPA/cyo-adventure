---
schema_type: planning
title: "WS-5 Design: Structure and State Variation within the ADR-011 Grammar"
description: "Phase A design for WS-5: grow distinct trees per cell by mutating
  already-verified skeletons with cheap, deterministic operators (sibling-subtree
  swap, ending re-map within valence, prune/graft within the envelope,
  decisions-per-path variation, Tier-2 state variation via variable retuning and
  condition-gated route rewiring), each mutant re-proven by the unchanged full
  gate plus a stricter WS-5 acceptance harness, packaged as a promotion bundle
  that feeds the WS-8 catalog flywheel behind a human structure-approval step.
  The grammar-based composer is scoped and explicitly deferred."
tags:
  - planning
  - generation
  - validation
  - diversity
status: proposed
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give the reviewer and the follow-up implementer an exact, file-by-file
  design for WS-5: the mutation-operator catalog with per-operator preconditions
  and preserved invariants, the state-variation half as a first-class citizen
  (walk-proven ending coverage and clock re-proof over configurations), the exact
  gate re-validation contract with no novelty exception, the WS-2
  contract-compatibility rules for mutants of parameterized parents, the
  promotion-bundle hand-off to WS-8 via the generalized neutralize transform, the
  ADR-020 candidate this workstream raises now that ADR-019 is settled, and a
  D1-D8 sprint plan ordered cheapest-and-safest first."
component: Strategy
source: "docs/planning/story-flexibility-plan.md section 5 (WS-5, lines 321-330;
  WS-4 saturation signal, lines 250-273; WS-8, lines 338-344), section 6
  (sequencing, lines 364-382), section 7 (safety invariants, lines 384-402),
  section 8 (current state), section 9 (open questions);
  docs/planning/adr/adr-011-story-scale-framework.md (the constraint grammar:
  axes, clocks, master cell table, constants, topologies, per-band allowances,
  series invariant); docs/planning/adr/adr-019-parameterized-skeletons-theme-contracts.md
  (settled: slots, sidecar contracts, fresh-leaf rule, label policy, coexistence);
  docs/planning/capability-register.md (K3 line 112, K13 line 122, K18 line 127);
  code read 2026-07-20: validator/{gate,layer1,layer2,walk,policy,topology,
  band_profile,slots,report,series}.py, moderation/pipeline.py,
  generation/{skeleton,skeleton_catalog,skeleton_match,binding,orchestrator,
  worker}.py, storybook/models.py, diversity/{structure,aggregate,query}.py,
  out/pilot/_neutralize.py, scripts/{parameterize_skeleton,check_skeleton,
  check_theme_contract,run_story_gate}.py, skeletons/** (59 skeletons, 45
  contracts, 12 Tier-2 stateful, 3 MVP seeds)."
---

# WS-5 Design: Structure and State Variation within the ADR-011 Grammar

> **Status: proposed (Phase A).** This document is the input to a supervisor
> sign-off review, mirroring the WS-1, WS-2, and WS-7 Phase A process. Nothing
> here is implemented; section 15 lists the decisions the reviewer must ratify
> before an implementation pass.
>
> **The paragraph that governs everything else:** WS-5 is a *catalog-time*
> workstream, never a request-time one. Mutation operators run offline over the
> git-versioned skeleton library, produce candidate trees that must pass the
> byte-identical full gate plus a stricter WS-5 acceptance harness, and hand a
> promotion bundle to a human structure-approval step (a skeletons/ PR). No
> mutant touches selection, generation, or a child until it has been promoted
> exactly like a hand-authored skeleton. The frozen safety object is the ADR-011
> constraint grammar (plan section 3, lines 120-131); WS-5 varies trees strictly
> inside it and the gate verifies every result. There is no novelty exception
> (plan safety invariant 2, line 391), and a gate failure discards the mutant,
> never weakens the gate (section 7.4).

---

## 1. Objective and scope

WS-5 per the master plan (`story-flexibility-plan.md` section 5, "WS-5:
Structure and state variation within the ADR-011 grammar", lines 321-330): new
and mutated trees plus state variety, for when leaf diversity alone (WS-1/WS-2)
no longer holds uniqueness up: heavy readers, and per-cell libraries large
enough that repeated trees start to show (plan section 1, consequence 2, lines
74-78). Sequencing (section 6, line 374): WS-5 depends only on WS-0 (delivered:
Phase 1 and 2 shipped, including `structural_distance` and effective catalog
size) and feeds WS-8 (the catalog flywheel), which also consumes WS-6. The
demand signal already exists: WS-4's `DifferentiationLevel.CATALOG` escalation
emits the `selection.cell_theme_saturated` log and a non-blocking plan warning
"for the WS-8 catalog flywheel to consume later" (plan lines 266-271); WS-5 is
the mechanism that gives that signal something to do.

**Approach ordering, fixed by the plan (line 327-329):** cheap **mutation
operators on already-verified trees first**; a grammar-based composer is "the
larger second step". This design front-loads the operators (sections 4 and 5)
and scopes the composer as explicitly deferred (section 7).

**Capability served** (register IDs, `capability-register.md`):

- **K3 (primary):** "Choices are consequential: paths genuinely differ, endings
  vary, the story remembers state (items, flags, counters)" (line 112, delivery
  vehicles: Storybook format, Tier 2 state, ADR-011 clocks). WS-5 serves K3 on
  both halves: structural mutation makes paths genuinely differ *between
  stories in a cell*, and state variation makes the same tree *play*
  differently (different resource pressure, different gated routes) rather
  than merely read differently.
- **K13 (gate, not served):** the age-band content guarantee bounds every
  operator; section 10 maps it.
- **K18 (indirect):** more distinct trees per cell protects the rating signal
  from repeat fatigue; no WS-5 code touches ratings.

**Metric (from the plan, line 330):** distinct trees per cell. Operationalized
with WS-0 instruments: the per-cell count of catalog skeletons weighted by
pairwise `diversity.structure.structural_distance` (a mutant that is
near-isomorphic to its parent must not count as a new tree; section 4.6's
anti-clone floor enforces this at promotion), plus the served-side "distinct
trees served per family per 90 days" and effective-catalog-size metrics WS-0
already computes (plan lines 172-178).

**Explicitly in scope:**

- A pure, deterministic mutation-operator framework and five operator families
  (M1-M5, sections 4-5) operating on skeleton shells (FILL directives intact),
  never on filled stories.
- A WS-5 acceptance harness that re-runs the full unchanged gate on every
  mutant and adds stricter, promotion-only checks (ending coverage over the
  configuration walk, clock re-proof over configurations, the anti-clone
  structural floor). Stricter is always allowed; weaker never (section 6).
- Contract compatibility: a mutant of a parameterized parent ships a mutated
  `.contract.json` sidecar that passes the WS-2 acceptance runner (section 4.7).
- The promotion bundle: the machine-readable hand-off artifact WS-8 promotes
  through the generalized neutralize transform behind human structure approval
  (section 9).
- The ADR-020 candidate position (section 8) and the D1-D8 sprint plan
  (section 12).

**Explicitly out of scope:**

- **The grammar-based composer.** Scoped in section 7, deferred with reasons.
- **Any request-time or runtime mutation.** Selection (`skeleton_match.py`),
  the worker, and the fill pipeline are untouched; mutants become ordinary
  catalog skeletons and nothing downstream knows they are mutants.
- **WS-8 automation.** WS-5 delivers the bundle format and one manual
  end-to-end promotion; scheduled/triggered flywheel automation is WS-8.
- **Series books.** Operator precondition: `metadata.series is None`. The
  ADR-011 section-8 single-entry invariant and the separate
  `validator/series.py` meta-validator make series mutation a distinct problem;
  every current catalog skeleton is standalone, so nothing is lost.
- **Cross-band mutation and cell reclassification.** A mutant inherits its
  parent's `(band, length, style)` cell verbatim in v1 (OQ-4).
- **Tier promotion (Tier 1 to Tier 2) as an operator.** Adding state to a
  stateless tree requires authoring new variables, loops, and beats wholesale;
  it is closer to composition than mutation and is deferred with the composer
  (section 5.5).
- **Mutation of filled stories.** The unit of catalog growth is the skeleton
  shell. Mutating published prose would bypass the fill/fidelity machinery and
  create an unreviewable second authoring path.

**Deliverables:** D1-D8, section 12.

## 2. Current state (the exact seams)

### 2.1 The catalog WS-5 mutates

`skeletons/<band>/<slug>.json`, discovered by filesystem scan
(`generation/skeleton_match.py::_production_candidates`, line 111, which skips
`*.contract.json` sidecars at line 135). On disk today: **59 skeletons** (56
production, 3 MVP/test seeds per ADR-011 section 1a), **45 contract sidecars**
(the WS-2 Phase C migration; the 14 without are the 12 Tier-2 stateful
skeletons plus the two contract-less MVP seeds), across all six bands. Every
skeleton is gate-verified at load: `generation/skeleton.py::load_skeleton`
(line 25) runs `run_gate` and raises `ValidationError` on any blocking finding,
so the mutation substrate is by construction a set of trees the gate has
already accepted.

A Tier-2 example that grounds section 5: `skeletons/10-13/the-flooded-quarter.json`
(155 nodes, 28 endings, `open_map`, medium) declares three variables (`water`
int 0-2, `oil` int 0-3, `laden` bool), 16 condition-gated choices (for example
`{'>=': [{'var': 'oil'}, 1]}` on dark-interior routes and
`{'<': [{'var': 'water'}, 2]}` on the hub's last-errand route), and 7 on_enter
effects including `once: true` increments of `water`. Its ending multiset spans
7 `(setback, negative)`, 9 `(discovery, positive)`, 5 `(discovery, neutral)`,
and single-digit others; no `death` or `capture` (band allows both, the author
chose neither).

### 2.2 The gate a mutant must re-pass (entry points, exact)

- **`validator/gate.py::run_gate(data, scale="standard")`** (line 76), the
  single combined entry point: Layer 1 (L1-1 schema, L1-2 references/targets,
  L1-3 reachability, L1-4 termination, L1-5 trap loops, L1-6 variable/tier
  rules, L1-7 node/depth budget against the ADR-011 cell envelope), early
  return on any L1 error; then policy PL-15 (forbidden ending kinds per band),
  PL-16 (content ceilings), PL-17 (ending/decision floors, breadth-scaled for
  scale-classified stories), PL-18 (declared topology must be in
  `validator/topology.py::admissible_topologies` for the graph shape), PL-19
  (per-node word wall, story-mean advisory), PL-20 (fastest-finish arc floor
  over the structural shortest path to a success/completion ending), PL-21
  (offered-cell check), PL-22 (fail-closed on unconfigured band); then Layer 2
  for Tier-2 stories only, over the full configuration walk
  (`validator/walk.py::walk_configurations`, BFS over
  `(node, var_state, once-visit-set)` keys, cap 100 000): L2-9 stateful
  dead-ends, L2-10 loop escape/termination per configuration, L2-11 dead
  conditional branches, L2-12 cap, L2-13 scale advisory; then advisory RL-13
  and the SAFE-14 stub. `blocked` is true on any L1/L2/PL error.
- **`generation/skeleton.py::load_skeleton(path)`**: `run_gate` plus
  raise-on-blocked; the load-time form every mutant file must survive.
- **`scripts/check_skeleton.py`**: the offline wrapper that additionally
  asserts the declared metadata matches a `(band, length, style, topology,
  tier)` brief; used per-mutant in the acceptance harness.
- **For parameterized mutants**: `generation/binding.py::load_contract_for`
  (which enforces that the skeleton's `{SLOT}` token set exactly equals the
  contract's declared slot ids), `validator/slots.py::validate_slot_bindings`
  over the contract's `default_binding` (with the band-mandatory denylist floor
  unioned in regardless of contract content), and
  `binding.py::render_bound_skeleton`'s four fail-closed post-conditions
  (zero residual tokens, `structure_fingerprint` equality, `run_gate` not
  blocked, FILL role/words byte-preserved), all wrapped by
  **`scripts/check_theme_contract.py`**, the WS-2 per-skeleton acceptance
  runner.
- **Downstream, unchanged for every story generated from a mutant**:
  `generation/orchestrator.py::fill_skeleton` (which re-parses and re-runs
  `run_gate` on the filled document inside the bounded repair loop, plus the
  Stage 1 fidelity gate), `moderation/pipeline.py::run_moderation_pipeline`
  (classifier stages, the WS-1 leaf-diversity advisory, the one bounded
  repair), and ADR-005 human approval before publish. WS-5 adds nothing to and
  removes nothing from this chain.

### 2.3 The WS-2 machinery mutants must stay compatible with

ADR-019 (accepted 2026-07-19) fixed the parameterization scheme: slots
(`{[A-Z][A-Z0-9_]*}`) may appear in exactly three surfaces (beats guidance
inside `<<FILL role=... words=... beats='...'>>` bodies, ending titles, choice
labels) and nowhere else; structural fields are never slotted; the contract is
a sidecar (`<slug>.contract.json`) with per-slot deterministic constraints;
dispatch is per skeleton by sidecar presence; leaf prose is always generated
fresh. A skeleton containing `{SLOT}` tokens but lacking a contract fails
closed at load. Consequence for WS-5: a mutant of a parameterized parent that
drops, duplicates, or imports slotted surfaces MUST ship a correspondingly
mutated contract or it is unloadable, which is exactly the fail-closed behavior
we want (section 4.7).

### 2.4 The pilot tooling WS-8 promotion reuses

`out/pilot/_neutralize.py` was the bespoke one-skeleton transform; its
production generalization already exists:
**`scripts/parameterize_skeleton.py`** applies an agent-authored slotting plan
(`beats`/`titles`/`labels` maps) to a pristine skeleton and enforces six
fail-closed checks (coverage, dangling references, role/words byte-preserved,
fingerprint equality, gate not blocked, slot-token grammar). This is the
"neutralize transform" the plan's WS-8 section names (line 342); WS-5's output
must therefore arrive as **a pristine, gate-passing skeleton shell** (plus, for
parameterized parents, a contract), because that is the exact input shape the
transform and the WS-2 migration recipe consume. Section 9 specifies the
bundle.

### 2.5 The measurement instruments (WS-0, delivered)

`diversity/structure.py`: `structure_fingerprint` (leaf-stripped structural
identity; a mutant's fingerprint MUST differ from its parent's, the inverse of
WS-2's render invariant), `structure_features` and
`structural_distance(a, b)` (Canberra mean over numeric shape features plus L1
over ending histograms). `diversity/aggregate.py`:
`effective_catalog_size`. These give WS-5 its acceptance floor (section 4.6)
and its success metric without new instrumentation.

### 2.6 What is missing (the WS-5 gap)

Nothing today can create a new tree except a human (or agent) authoring one
from scratch through the story-inventory process. The cost of a new verified
tree is the cost of authoring ~10-155 nodes of beats guidance plus structure
plus review; that cost is why cells have 5-12 skeletons and why WS-4's CATALOG
escalation currently terminates in a log line. Meanwhile the catalog embodies
sunk, human-reviewed value: 59 verified structures and their beats. Mutation
converts that sunk value into new trees at a fraction of authoring cost, with
the gate re-proving safety mechanically.

## 3. Design principles

1. **Mutate the shell, inside the grammar.** Operators consume and produce
   skeleton shells (FILL directives intact). The ADR-011 grammar (per-band
   topology and primitive allowances, ending kind/valence policy, the three
   clocks, cell envelopes, decisions-per-path 4-8, choices-per-decision 2-3,
   words/node) is the fixed constraint set; operators are transformations whose
   preconditions are stated in grammar terms and whose results are re-proven by
   the gate that enforces the grammar.
2. **Catalog-time, not request-time.** Mutation is an offline authoring
   accelerator. The product surface (selection, generation, publish) sees only
   promoted skeletons.
3. **A mutant is a new first-class tree.** New slug, new file, own contract,
   own PR review, ordinary selection weight. Lineage is recorded for audit and
   metrics (section 9.2) but creates no runtime linkage and no inherited trust:
   a mutant earns catalog membership exactly the way a hand-authored skeleton
   does, plus the stricter WS-5 acceptance.
4. **Discard, never weaken.** A mutant that fails any check is discarded with a
   structured log. No threshold is moved, no baseline updated, no rule
   special-cased. High discard rates tune operator *preconditions* (make the
   operator smarter about what it attempts), never the gate.
5. **Determinism and replayability.** Every operator is a pure function of
   `(parent document, operator parameters, seed)`; the lineage manifest records
   all three, so any promoted mutant can be re-derived and re-verified
   byte-for-byte.
6. **No untrusted input, by construction (OWASP LLM01).** Operator inputs are
   git-versioned catalog files and reviewer-supplied parameters. No request
   text, theme brief, or any child-derived artifact enters WS-5. The one
   demand-side signal (WS-4 saturation) is consumed as a counter per cell,
   never as text. Where an agent authors replacement beats guidance for mutated
   regions (the re-guidance step, section 4.5), it does so from catalog content
   only, and the result re-enters the system solely through the same PR review
   and gate as any hand-authored guidance.

## 4. The mutation-operator catalog

### 4.1 Shared operator framework

New pure package `src/cyo_adventure/mutation/` (no db, no network, no
generation imports beyond `skeleton.load_skeleton` and `diversity.structure`;
mirrors the `storybook/theme_contract.py` layering discipline):

- `ops.py`: the `MutationOp` protocol and registry. Signature sketch:

```python
@dataclass(frozen=True, slots=True)
class MutationResult:
    candidate: dict[str, object]      # the mutated shell, ids/metadata resynced
    reguide: tuple[ReguideItem, ...]  # nodes/choices whose guidance needs re-authoring
    notes: tuple[str, ...]            # operator-specific audit notes

class MutationOp(Protocol):
    op_id: str

    def preconditions(
        self, parent: Mapping[str, object], params: OpParams
    ) -> PreconditionReport: ...

    def apply(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> MutationResult: ...
```

- `subtree.py`: subtree extraction and the self-containment check. A subtree
  `T` rooted at `r` is *self-contained* when every edge into `T` from outside
  lands on `r` and nowhere else (out-edges from `T` to external nodes are
  allowed and recorded as the subtree's reconvergence surface). v1 operators
  that move subtrees additionally require the moved subtree to be *closed*
  (every out-edge stays inside `T`, i.e. every leaf of `T` is an ending) except
  where an operator explicitly says otherwise.

```python
# #CRITICAL: data-integrity: self-containment is the load-bearing precondition
# for every subtree move; a missed external in-edge would leave a dangling or
# duplicated entry point and the moved region would be reachable from a stale
# position. The check must enumerate in-edges over the WHOLE graph, not the
# candidate region.
# #VERIFY: tests/unit/test_mutation_subtree.py property test: for every node r
# in every catalog skeleton, extract_subtree(r) either fails self-containment
# or the returned node set has in-edges only at r (asserted by exhaustive edge
# scan), and the gate on a swap using it is never L1-2/L1-3 blocked.
```

- `identity.py`: deterministic id renaming for grafted/duplicated regions
  (prefix scheme `m<k>_<old_id>` for node, choice, and ending ids; collision
  checked against the host's full id namespace), and metadata resync:
  `ending_count` recomputed from the node list (the schema validator rejects a
  mismatch, `storybook/models.py::_check_ending_count`), `estimated_minutes`
  recomputed from the ADR-011 words/pace anchors, `tier` recomputed from
  variable presence, `topology` re-declared per section 4.8.
- `state_ops.py`: the M5 family (section 5).
- `acceptance.py`: the harness (section 6).
- `bundle.py`: the promotion bundle writer (section 9).
- CLI: `scripts/mutate_skeleton.py <parent.json> --op <id> [--params ...]
  [--seed N] --out-dir out/mutations/` runs preconditions, apply, acceptance,
  and bundle write; exits non-zero (writing nothing promotable) on any failure.

### 4.2 M1: sibling-subtree swap

- **Definition.** Given two decision nodes `d1`, `d2` (distinct, or the same
  node) and choices `c1 in d1.choices`, `c2 in d2.choices` whose targets root
  self-contained subtrees `T1`, `T2` with disjoint node sets, retarget
  `c1.target = root(T2)` and `c2.target = root(T1)`. With `d1 == d2` this
  permutes which sibling action leads to which track; with `d1 != d2` (for
  example, swapping route A's track-2 subtree with route C's track-1 subtree in
  a cave-of-echoes-shaped tree) it produces a genuinely re-paired tree: the
  same materials, a different map.
- **Preconditions.** Self-containment of both subtrees; node-set disjointness;
  `T1`/`T2` closed OR their external out-edges target nodes that remain valid
  from the new position without creating a cycle (operator computes post-swap
  acyclicity when the parent graph is acyclic); post-swap depth within the
  cell's `max_depth` (L1-7); post-swap structural shortest satisfying path
  still at or above the PL-20 floor (pre-computed to avoid wasted gate runs);
  `metadata.series is None`.
- **Preserved by construction.** Node set, node count, ending multiset
  (`(kind, valence)` counts), `ending_count`, every in-degree (each root loses
  one in-edge and gains one), hence the reconvergence count PL-18/the topology
  classifier reads; variables/effects/conditions untouched (M1 on a Tier-2
  parent requires that neither subtree contains effects whose ordering
  relative to the other subtree's conditions matters; v1 simply restricts M1
  to Tier-1 parents and to Tier-2 subtree pairs containing no effects and no
  conditions, with the walk as backstop).
- **May change, gate re-proves.** Depths (L1-7), fastest-finish (PL-20),
  acyclicity (PL-18 admissible set), decision counts per path (operator
  reports against the 4-8 constant).
- **Re-guidance.** The swapped choices' labels and the entry beats of each
  moved subtree describe an approach that has changed context. ADR-019
  Decision 5 makes labels content with a frozen action-semantic; a swap
  changes what the action leads to, so the two labels (or their label
  templates) and the two subtree-root beats are emitted as `reguide` items.
  The bundle is not promotable while any reguide item is unresolved
  (section 4.5).
- **Re-validation.** Full acceptance harness (section 6): `run_gate`, cell
  assertion, anti-clone floor, and (Tier-2) walk checks.

### 4.3 M2: ending re-map within the valence set

- **Definition.** A permutation of ending payloads `(kind, title or title
  template)` over the terminal nodes of one valence class (positive
  terminals permute among themselves, negative among themselves, neutral among
  themselves). Valence stays with the leaf position, because the approach arc
  into a leaf is written (in beats) to feel like the outcome it lands;
  swapping *kind within valence* (a `discovery` leaf becomes the `success`
  leaf and vice versa, a `setback` becomes the cell's `capture` where the band
  allows `capture`) changes which route carries which mechanical outcome
  without inverting any arc's emotional shape. On a parent like
  the-flooded-quarter this re-maps which of the 9 positive discoveries is
  which, and which errand's failure is the one that costs the skiff.
- **Preconditions.** The `(kind, valence)` multiset is invariant (a permutation
  guarantees it, so PL-15/PL-16/PL-17 are unaffected by construction); after
  the re-map, the structural shortest path to a `success`/`completion` ending
  is still at or above the PL-20 floor (moving the satisfying kinds to
  shallower leaves is the one way this operator can break a clock, so the
  operator pre-computes it); ending ids stay with their payloads (uniqueness
  preserved); `metadata.series is None` (a series book's
  successful-completion set is continuity-bearing, ADR-011 section 8).
- **Preserved by construction.** Graph shape entirely (fingerprint changes
  only through ending titles, which are leaf content; therefore M2 alone does
  NOT count as a new tree, see the composition note below); ending multiset;
  all budgets and floors except PL-20.
- **Composition note.** `structure_fingerprint` retains each ending's kind and
  id (it strips only the leaf-prose title), so an M2-only re-map, which permutes
  which terminal position carries which ending kind within a valence class, DOES
  change the fingerprint and therefore PASSES the anti-clone floor's fingerprint
  clause (4.6 clause 1). What rejects an M2-only mutant is the distance clause
  (4.6 clause 2): `structural_distance`'s ending histograms are aggregate and
  position-blind, so a within-valence kind permutation leaves every shape feature
  and every histogram unchanged and the parent distance is ~0. (This was verified
  in the D3/D7 reviews and is the behavior `floors.structural_floor_reason`
  implements.) M2 is therefore a *composition* operator: it rides along with
  M1/M3/M4 to decouple "which route" from "which outcome" in the mutant, which is
  precisely its diversity payoff (the reader who knows the parent cannot transfer
  outcome knowledge to the mutant). Standalone M2 is permitted only for the
  state-composed form in section 5 (where the state signature distance floor
  applies instead).
- **Re-guidance.** The affected leaves' beats and titles (title templates for
  parameterized parents) are reguide items; the approach nodes immediately
  upstream are flagged advisory.
- **Re-validation.** Full harness; PL-20 is the check to watch.

### 4.4 M3: prune/graft within the envelope

- **Prune definition.** Remove a closed, self-contained subtree `T` and the
  single choice edge into it.
- **Prune preconditions.** The parent decision retains at least 1 choice
  (schema) and the story keeps `min_decisions` decision nodes (PL-17);
  post-prune node count stays at or above the cell envelope minimum (L1-7
  treats below-min as WARNING for cell budgets, but WS-5 treats the envelope
  as two-sided and blocking at acceptance: a mutant may not exit the cell it
  declares); post-prune endings stay at or above `min_endings` and the
  breadth-scaled floor, keep at least one `success`/`completion`, and keep the
  ending ratio within the ADR-011 section 6 prose constant (~15-22%) as an
  advisory; the pruned subtree's ending kinds are re-counted into
  `ending_count`.
- **Graft definition.** Attach a copy of a closed, self-contained subtree `T'`
  (from the same skeleton, or from a *donor* skeleton in the same band) under
  a new choice on a decision node `d`, with all ids deterministically renamed
  (`identity.py`), `d` staying within 2-3 choices (the ADR-011 section 6
  constant; the gate does not hard-enforce choices-per-decision, so the
  operator does, per the belt-and-braces rule in section 4.8).
- **Graft preconditions.** Donor band equals host band (so every grafted
  ending kind is band-legal by the donor's own gate history, and beats
  guidance was authored to the same band's content posture); post-graft node
  count within the cell envelope max (L1-7 ERROR above max); depth within
  budget; `once` effects and variables: v1 grafts only variable-free,
  effect-free, condition-free subtrees into any host, and defers stateful
  grafts to the composer (grafting state requires merging variable namespaces
  and re-proving the joint configuration space; the walk would catch errors
  but the authoring semantics are composition, not mutation).
- **Contract merge (parameterized parents/donors).** Slots referenced by the
  grafted region's beats/titles/labels are imported into the host contract
  under renamed ids (`M<k>_<SLOT>`), with their `SlotSpec` constraints copied
  verbatim and `default_binding` entries carried over; pruned regions' slots
  are dropped from the contract if and only if no surviving surface references
  them. `load_contract_for`'s exact-token-set equality makes any error here
  fail closed at load (section 2.3).
- **Preserved by construction.** Everything outside the pruned/grafted region;
  the band's forbidden-kind guarantee (donor same band + PL-15 re-run).
- **Re-guidance.** The new choice's label and the graft root's entry beats
  (the seam where donor content meets host context); prune needs none.
- **Re-validation.** Full harness; L1-7 (both sides), PL-17, PL-20, PL-18 are
  the live checks; `check_theme_contract.py` for the merged contract.

### 4.5 M4: vary decisions-per-path (target 4-8)

- **Definition.** Three sub-operators that move a tree's per-path decision
  count within the ADR-011 section 6 constant (4-8 decisions per playthrough,
  choices 2-3, "length adds breadth, not depth"):
  - **insert-linear**: split an edge with a new linear-passage node (body
    `<<FILL role=passage words=<band mean> beats='...'>>`, one choice to the
    old target). Adds arc substance exactly the way ADR-011 section 4 says
    substance is added ("mandatory linear passages, not extra decisions").
  - **remove-linear**: splice out a 1-choice, effect-free, non-ending node,
    retargeting its in-edges to its successor.
  - **insert-decision**: split an edge with a new 2-3 choice decision node;
    one choice continues to the old target, each extra choice either targets
    an existing downstream node (adding reconvergence: in-degree rises, which
    the operator checks against the band's reconvergence posture and
    `BandProfile.reconvergence_ceiling` where configured) or roots a new
    closed micro-stub ending (which changes the ending multiset and count,
    with PL-15/PL-17 re-checked).
- **Preconditions.** Post-op per-path decision counts within 4-8 (computed
  exactly over the acyclic path set, or over a bounded sample of walk paths
  for cyclic graphs); depth within budget; node count within envelope; for
  insert-decision-with-reconvergence, post-op acyclicity when the parent is
  acyclic and PL-18 admissibility of the declared topology; inserted nodes on
  the shortest satisfying path only ever RAISE the PL-20 measure (safe
  direction), remove-linear can lower it and is pre-checked.
- **Preserved by construction.** All content outside the touched edges;
  variables/state (v1 inserts effect-free nodes only).
- **Re-guidance.** Every inserted node's beats and every inserted choice's
  label are reguide items by definition (they are new).
- **Re-validation.** Full harness.

### 4.6 The anti-clone floor (the structural analog of the ATG)

A mutant that the gate passes can still be worthless: a near-isomorphic copy
of its parent adds a catalog row without adding a distinct tree, the
structural dog-for-cat. Acceptance therefore requires, blocking at promotion:

- `structure_fingerprint(mutant) != structure_fingerprint(parent)` (a pure
  identity check; an M2-only re-map PASSES this clause, because
  `structure_fingerprint` retains ending kind/id and so changes when M2 permutes
  kinds within a valence class, section 4.3), and
- `structural_distance(parent, mutant) >= TAU_STRUCT` (an M2-only mutant is
  rejected HERE, its position-blind histograms leaving the distance ~0, not at
  the fingerprint clause), and
- `min over in-cell catalog skeletons s of structural_distance(s, mutant) >=
  TAU_CELL` (a mutant must not be a clone of ANY existing in-cell tree, not
  just its parent; `TAU_CELL <= TAU_STRUCT`).

`TAU_STRUCT`/`TAU_CELL` are calibrated in D7 against the observed distribution
of pairwise in-cell distances across the existing 59-skeleton catalog
(provisionally the 25th percentile of same-cell hand-authored pairs for
`TAU_STRUCT`; the observed same-cell minimum for `TAU_CELL`), committed as a
versioned baseline next to the WS-0 eval panel, and tunable only by a reviewed
PR. For M5-only mutants the state-signature distance floor substitutes
(section 5.4). This floor is a WS-5 *promotion* bar, not a gate change: it can
only reject, never admit (safety invariant 2 stays intact in both directions).

### 4.7 Contract compatibility summary (WS-2)

| Parent kind | Mutant obligation |
| --- | --- |
| Parameterized (45 today) | Ship a mutated `.contract.json`: surviving slots kept, pruned-only slots dropped, grafted slots imported under renamed ids, `default_binding` complete, `skeleton_slug` updated to the mutant slug, `contract_version` reset to 1 (a new contract for a new tree). Must pass `scripts/check_theme_contract.py` end to end, including `validate_slot_bindings(default_binding)` with the band floor and `render_bound_skeleton`'s four post-conditions. |
| Contract-less Tier-2 (12 today) | Mutant lands contract-less, at parity with its parent (the WS-2 Tier-2 migration has not happened; a WS-5 mutant must not be blocked on it, and must not half-migrate by inventing slots). When WS-2 migrates Tier-2, mutants migrate in the same wave as ordinary skeletons. Ratify as OQ-2. |
| MVP seeds (3 today) | Out of scope as parents: mutating a non-production shell produces a non-production shell and buys no catalog diversity. Operator precondition: `metadata.production_eligible is True`. |

### 4.8 Belt-and-braces: grammar constraints the gate does not hard-enforce

The ADR-011 section 6 constants (decisions/path 4-8, choices/decision 2-3,
setup 2-3 nodes before first choice) and the section 7 per-band
topology/loops/restart allowance table are authored-grammar rules that the
gate only partially enforces (PL-18 checks shape admissibility, not band
allowance; nothing checks choices-per-decision). Every WS-5 operator enforces
them as *preconditions* anyway: a mutant may not exploit a gate gap that a
hand author would not exploit. Whether these should also become deterministic
validator rules (a PL-23 family) is raised as OQ-8, recommended as a follow-up
outside WS-5 (adding gate rules mid-workstream would re-litigate the existing
catalog).

Topology re-declaration rule: after any structural operator, the mutant's
`metadata.topology` must be (a) in `admissible_topologies(mutant graph)`
(PL-18 enforces this) AND (b) in the parent band's ADR-011 section 7 topology
row (operator-enforced). When the parent's declared topology remains
admissible it is kept; otherwise the operator re-declares the admissible value
that is in the band row, or fails the precondition if none is.

## 5. State variation (the M5 family, first-class)

The state half of K3 ("the story remembers state") today varies only across
the 12 hand-authored Tier-2 skeletons. M5 makes one verified stateful tree
play as several: same map, different pressure. All M5 operators require
`metadata.tier == 2` and a band whose ADR-011 section 7 row permits stateful
loops (8-11 optional and up); they never touch ending kinds, valences, or the
ending multiset, so the fail-state policy surface (PL-15/PL-16/PL-17) is
untouched by construction.

### 5.1 M5a: variable semantics and dynamics retune

- **Definition.** Within a declared variable's type: change `initial`,
  `min`/`max` bounds, and the integer literals in the conditions and effects
  that reference it (all within `MAX_ABS_STORY_INT` and the schema's
  type-consistency validators), and rewrite the variable's `description` (and,
  via reguide, the beats that narrate it) to a new semantic. Example on
  the-flooded-quarter: `oil` initial 3 to 2 turns a comfortable lamp budget
  into a rationing problem; raising a gate from `>= 1` to `>= 2` makes one
  route an early-game-only option. Renaming a variable is permitted as pure
  alpha-renaming (declaration + every reference in one pass) and is
  semantically free; it exists so the new `description` reads honestly.
- **What it must NOT do.** Change a variable's type (bool/int), add or remove
  variables (that is 5c territory, deferred), or touch any ending.
- **Diversity payoff.** The reachable configuration space, the set of routes a
  reader can actually take, and which endings are easy versus earned all
  shift; two readers of parent and mutant play different games on one map.

### 5.2 M5b: condition-gated route add/rewire

- **Definition.** Three moves, composable:
  1. **Gate an existing choice**: add a `condition` to a currently
     unconditioned choice (whitelisted operators only, declared variables
     only; the schema and L1-6 enforce both).
  2. **Add a gated route**: add a new choice on an existing decision node
     (within the 2-3 cap), condition-gated, targeting an existing node (a
     shortcut, a secret door). Reconvergence and (for acyclic parents)
     acyclicity checked as in M4; for `open_map`/`loop_and_grow` parents a
     back-edge target is legal (the band's loop allowance is the operator
     precondition).
  3. **Relocate effects**: move an `on_enter` or choice effect to a different
     node/choice, preserving the effect's op/var/value (for example, the
     `once: true` `water` increment fires at the errand's start instead of
     its completion, changing the deadline pressure of the whole quarter).
- **The dead/trap-state obligation (how the walk proves it).** Every M5b move
  can, in principle, strand a configuration. The proof obligations and their
  provers:
  - No configuration with zero visible choices at a non-ending node: **L2-9**
    over `walk_configurations` (the evaluator's fail-closed semantics mean an
    over-strict condition hides a choice, and the walk sees exactly what a
    reader sees, `ConfigKey` including the once-effect visit intersection).
  - Every reachable configuration can still reach an ending: **L2-10**.
  - Every condition ever matters: a gated choice invisible in ALL
    configurations is **L2-11** (a dead branch, blocked).
  - The walk completed (uncapped): **L2-12**; a capped walk is an acceptance
    failure for a mutant even though the gate reports it as its own finding,
    because an unexplored state space is an unproven mutant.
- **Operator-side precondition (cheap, before the gate re-run).** When gating
  a previously unconditioned choice, require either a sibling choice at that
  node that remains unconditioned, or an operator-supplied argument for why
  every reachable var-state at that node satisfies at least one sibling; the
  walk is the authority, the precondition just avoids burning walk time on
  obvious stranding.

### 5.3 The WS-5 acceptance checks the gate does not already make

Two obligations named by the plan's WS-5 intent exceed what L2 proves, and the
acceptance harness (section 6) adds them for Tier-2 mutants, stricter-only:

1. **Ending coverage over configurations.** L1-3 reachability is structural
   (condition-blind), and L2-10/L2-11 do not directly assert that *every*
   ending node occurs in some reachable configuration: an ending whose only
   approaches are all condition-gated could be structurally reachable yet
   config-unreachable without tripping L2-11 (if the gating choices are
   visible elsewhere) in pathological shapes. WS-5 requires: every `is_ending`
   node id appears in `WalkResult.configs`. A retune that silently amputates
   an ending is discarded.

```python
# #CRITICAL: data-integrity: ending coverage must be computed from the SAME
# WalkResult the L2 rules consumed (one walk, one truth); recomputing with a
# different cap or engine version could pass an ending the gate's walk never
# reached.
# #VERIFY: acceptance.py runs walk_configurations once, feeds both the L2
# re-check and the coverage set from that single result;
# tests/unit/test_mutation_acceptance.py pins a fixture where an oil retune
# makes exactly one ending config-unreachable and asserts discard.
```

2. **Clock re-proof over configurations.** PL-20 measures the structural
   shortest satisfying path, ignoring conditions. An M5 mutant could gate the
   short win behind state that cannot exist at that depth, silently inflating
   the real fastest finish (a product regression, not a safety one), or
   conversely a new gated shortcut could undercut the arc floor in *practice*
   while the structural check still passes (a safety-of-experience
   regression). WS-5 computes the walk-derived fastest satisfying finish (the
   minimum config-path node count from the initial configuration to any
   config at a `success`/`completion` node) and requires it to be at or above
   the cell's `min_complete_floor` and finite. Advisory on the high side
   (a much slower real fastest-finish is reported, not blocked).

### 5.4 The state-signature distance floor (anti-no-op)

For an M5-only mutant (graph shape unchanged, so `structural_distance` is ~0
by design), the anti-clone floor of section 4.6 is replaced by a
state-signature distance: a deterministic feature vector over
`(variable (type, initial, min, max) tuples, canonical condition set with
literals, effect op/var/value/once placement, walk statistics: config count,
per-ending config counts, mean visible-choice ratio)`, with a floor
`TAU_STATE` calibrated in D7 from cross-Tier-2-catalog pairs. A cosmetic
retune (oil 3 to 3) or a description-only edit fails the floor and is not a
mutant. Fingerprint inequality is NOT required for M5-only mutants
(`structure_fingerprint` strips nothing state-related, so it will differ on
condition/effect changes anyway via the structural JSON; where it does not,
the signature floor decides).

### 5.5 Deferred within M5

Tier promotion (adding state to a Tier-1 tree), variable addition/removal on
Tier-2 trees, stateful grafts, and gamebook restart-on-fail rewiring
(13-16/16+ lethal restart semantics interact with band policy in ways that
deserve the composer's whole-graph reasoning). Each is admissible under the
grammar; none is cheap; all are listed so the composer inherits a concrete
backlog.

## 6. Gate integration: the re-validation contract

Every mutant, per attempt, runs the following in order; the first failure
discards the mutant (structured `mutation.discarded` log: parent slug and
content hash, op chain, params, seed, failing stage, rule ids). Nothing is
retried by loosening; a discarded mutant may be regenerated only by changing
operator parameters or seed, which produces a different mutant.

| Stage | Entry point (exact) | Proves | On failure |
| --- | --- | --- | --- |
| 0. Preconditions | `mutation/ops.py::MutationOp.preconditions` | Operator-specific grammar preconditions (sections 4-5), including the section 4.8 belt-and-braces constants | discard (cheap, no gate spend) |
| 1. Schema + structure + policy + state | `validator/gate.py::run_gate(candidate)` via `generation/skeleton.py::load_skeleton` semantics (blocked => raise) | L1-1..L1-7, PL-15..PL-22, L2-9..L2-13 for Tier-2: the identical, unchanged gate every hand-authored skeleton passes | discard |
| 2. Cell assertion | `scripts/check_skeleton.py --band --length --style --topology --tier` | Declared metadata equals the inherited parent cell (OQ-4: fixed in v1) | discard |
| 3. WS-5 stricter checks | `mutation/acceptance.py` | Ending coverage + clock re-proof over the single WalkResult (5.3); anti-clone floor `TAU_STRUCT`/`TAU_CELL` or state-signature floor `TAU_STATE` (4.6, 5.4); reguide list resolved (no `reguide` item outstanding) | discard (or hold-for-reguide: the bundle exists but is marked unpromotable) |
| 4. Contract acceptance (parameterized parents only) | `scripts/check_theme_contract.py` (wraps `load_contract_for`, `validate_slot_bindings(default_binding)` incl. the band-mandatory floor, `render_bound_skeleton`'s four post-conditions, bundle-id validity) | The mutated contract is complete, safe, and renderable | discard |
| 5. Sample fill (evidence, not gate) | `orchestrator.fill_skeleton` on the default binding (or free-text default theme for contract-less parents), mock or live provider per environment | One end-to-end gate-passing fill exists; attached to the bundle for the human reviewer (mirrors the pilot's RESULTS.md evidence posture) | discard if the fill's OWN gate blocks structurally; a fidelity-only downgrade is recorded, not blocking (it reflects guidance quality, which the human reviews anyway) |

**No novelty exception (plan safety invariant 2, restated as the blocking
rule):** stages 1, 2, and 4 are byte-identical to what a hand-authored
skeleton and its contract face; stage 3 is strictly additive. No WS-5 code
path may construct a `GateResult`, filter findings, pass a `scale` other than
`"standard"` (skeleton library files are genre-faithful, per
`fill_skeleton`'s existing rule), or mark a blocked candidate promotable.
Post-promotion, stories generated from a mutant run the untouched
fill -> gate -> moderation -> ADR-005 human approval chain (section 2.2), so a
promoted mutant still cannot reach a child except through every existing
control.

```python
# #ASSUME: external-resources: acceptance runs load_skeleton/run_gate on
# files under out/mutations/, cwd-relative like every skeleton tool; the
# harness is invoked from the repository root (same posture as
# skeleton_match._SKELETON_ROOT).
# #VERIFY: scripts/mutate_skeleton.py resolves --out-dir to an absolute path
# at startup and refuses to write inside skeletons/ (promotion is a PR, never
# a script side effect).
```

## 7. The grammar-based composer (explicitly deferred)

The plan names it "the larger second step" (line 329). Scope statement so the
deferral is a decision, not an omission:

**What a composer is.** A generative sampler over the ADR-011 grammar itself:
pick a `(band, length, style)` cell, sample a topology from the band row,
compose flow primitives (branch, bottleneck, linear passage, terminal, loop,
restart-on-fail) into a graph satisfying the cell envelope, the three clocks,
the constants, and the band allowances *by construction*; then author beats
guidance, a slot plan, and a contract for the composed shell.

**What it needs that WS-5 does not build:**

1. A constructive clock solver (satisfy min-to-complete, envelope, ending
   ratio, depth simultaneously; mutation gets this for free by starting from
   a solution).
2. **Beats/arc authoring for every node.** This is the real cost. Mutation
   reuses human-reviewed guidance and touches only seams (the reguide list is
   small); a composer authors ~10-155 nodes of arc-coherent guidance from
   nothing. The gate proves safety and shape, NOT narrative arc quality
   (PL-20 is an anti-cheese floor, not a story-quality proof), so composed
   trees need editorial review at close to hand-authoring depth.
3. Contract synthesis (slot discovery, per-slot constraints, band floors).
4. Evidence of mutation plateau: WS-0 effective-catalog-size and
   distinct-trees-per-cell trends showing operator-derived variety saturating
   in the cells that matter.
5. The ADR-020 promotion bar (section 8) exercised and stable, because a
   composer multiplies exactly the reviewing load that bar governs.

**Why it is not in the first sprint.** The catalog holds 59 verified trees;
five operator families with parameter/seed spaces yield combinatorially many
candidate mutants per cell against a near-term need of "one or two more
genuinely distinct trees in saturated cells." Mutation exploits sunk cost with
small reguide surfaces; composition re-incurs the full authoring cost with an
unproven quality yield. Build the promotion pipeline and the demand loop on
cheap mutants; revisit the composer when D8's metrics show a plateau, as its
own Phase A design (the section 5.5 backlog and this section are its seed).

## 8. ADR position: ADR-019 is settled; WS-5 raises an ADR-020 candidate

**ADR-019 is accepted and covers the parameterization questions.** The plan's
section 9 "ADR-019 candidate" bullet (lines 418-423) is stale:
`docs/planning/adr/adr-019-parameterized-skeletons-theme-contracts.md` was
ratified 2026-07-19 during WS-2 and already decides what that bullet asks:
fixed and parameterized skeletons **coexist** during an incremental,
non-breaking migration with a fully parameterized catalog as the end-state
(Decision 7); the theme contract **lives as a sidecar file**
`skeletons/<band>/<slug>.contract.json`, never embedded in the skeleton and
never in a database table (Decision 2); leaves are generated fresh, never
substituted (Decision 4); labels are content with a frozen action-semantic
(Decision 5). WS-5 consumes those decisions as fixed inputs (sections 2.3 and
4.7) and needs nothing re-opened. D8 updates the stale plan bullet.

**What ADR-019 does not cover, and WS-5 does need ratified:** ADR-019 governs
how *content* varies on a fixed structure. WS-5 changes *structure itself* and
grows the catalog from non-hand-authored sources, which ADR-019 only gestures
at ("the catalog flywheel can promote new trees through the same
neutralize-and-contract machinery", Consequences). The decisions below have no
ratified home; this design proposes them as the **ADR-020 candidate:
"Mutation-derived skeletons and catalog growth"**, to be drafted and ratified
alongside this workstream (D8 prepares the draft; this document does not
create the ADR file). Proposed decision set:

1. **Mutants are first-class catalog citizens.** A promoted mutant is a new
   skeleton: new slug, own contract, ordinary selection weight, no runtime
   linkage to its parent. Trust is earned per tree through the identical gate
   plus the stricter WS-5 acceptance; nothing is inherited.
2. **Provenance is recorded, out of the story document.** `StoryMetadata` is
   `extra="forbid"` and reader-facing; lineage therefore lives in a
   `skeletons/<band>/<slug>.lineage.json` sidecar (parent slug + content
   hash, operator chain with parameters and seeds, acceptance report digest,
   promotion PR), with the catalog scanner's sidecar skip extended from
   `*.contract.json` to a general multi-suffix skip. Mirrors ADR-019
   Decision 2's sidecar reasoning: lineage must version and review atomically
   with the tree it explains.
3. **The gate is identical, plus promotion-only additions.** No novelty
   exception in either direction: mutants pass the byte-identical gate, and
   the WS-5 additions (ending coverage, clock re-proof, anti-clone/state
   floors) are promotion criteria that can only reject. Composed (future) and
   fresh-generated (WS-6) trees inherit the same bar.
4. **Human structure approval is the skeletons/ PR review**, performed by the
   owner or a delegated admin on the promotion bundle's evidence (diagram,
   acceptance transcript, sample fill, lineage). It is deliberately distinct
   from ADR-005 story approval (which continues to gate every published
   story) and from ADR-019's no-new-theme-review posture (unchanged: themes
   still need no human step; *structures* always did need one, this names
   it). No auto-merge for skeleton promotion PRs.
5. **Cell inheritance.** A mutant declares its parent's `(band, length,
   style)` cell; cross-cell derivation is a future ADR amendment, not an
   operator option.
6. **Contract parity.** Mutants of parameterized parents ship contracts
   (section 4.7); mutants of contract-less Tier-2 parents land contract-less
   at parity until the WS-2 Tier-2 migration wave.

**Recommendation:** ratify ADR-020 with this decision set at D8, once D1-D7
have produced at least one end-to-end promoted mutant to serve as the ADR's
evidence exhibit (the same accepted-with-evidence pattern ADR-019 used with
the pilot).

## 9. Feeds WS-8: the promotion hand-off

### 9.1 The flow

WS-8 (plan lines 338-344): "promote any gate-passed, human-approved fresh
(WS-6) or composed (WS-5) tree via the neutralize transform
(`out/pilot/_neutralize.py`) into the parameterized catalog, behind a human
structure-approval step." Concretely, with today's tooling:

1. WS-5 emits a **promotion bundle** (9.2) under
   `out/mutations/<mutant-slug>/`.
2. For a mutant of a parameterized parent, the bundle already contains the
   slotted shell + mutated contract (the operators preserved/merged slots),
   so the neutralize step is already satisfied. For a mutant of a
   contract-less parent that the owner wants parameterized at promotion, the
   WS-2 migration recipe applies as-is: an agent authors a slotting plan,
   `scripts/parameterize_skeleton.py` applies and enforces it, a contract is
   authored, `scripts/check_theme_contract.py` accepts. WS-5's output shape
   (a pristine, gate-passing shell) is exactly that recipe's input, by
   design (section 2.4).
3. A human opens the **promotion PR**: skeleton + contract (+ lineage
   sidecar, per ADR-020 decision 2) into `skeletons/<band>/`, the regenerated
   catalog doc region (`generation/skeleton_catalog.py` +
   `scripts/render_skeleton_diagrams.py`), and the bundle's acceptance
   transcript in the PR body. Review = human structure approval.
4. On merge, the mutant is a catalog skeleton: `candidates_for_cell` finds
   it, WS-4 weighting treats it as fresh (novelty floor intact), and the
   distinct-trees metric moves.

### 9.2 The bundle (the hand-off artifact, machine-readable for WS-8)

```
out/mutations/<mutant-slug>/
  <mutant-slug>.json               # the shell, FILL intact, gate-passing
  <mutant-slug>.contract.json      # parameterized parents only
  <mutant-slug>.lineage.json       # the provenance record (schema below)
  acceptance.json                  # per-stage results of the section 6 table,
                                   # incl. the serialized gate report, walk
                                   # stats, distances vs floors
  reguide.json                     # emitted items + their resolutions
                                   # (author, before/after guidance text)
  sample-fill/                     # stage 5 evidence: filled JSON + its gate
                                   # report (+ fidelity findings, informative)
  diagram.svg                      # via scripts/render_skeleton_diagrams.py
```

`lineage.json` (Pydantic-modeled in `mutation/bundle.py`, versioned):
`lineage_version`, `mutant_slug`, `parent_slug`, `parent_sha256` (of the
parent file at derivation time, so a later parent edit cannot silently
invalidate the record), `donor_slugs` (M3 grafts), `op_chain:
[{op_id, params, seed}]`, `created_at`, `tool_version`, `acceptance_digest`.
WS-8's future automation consumes exactly this bundle; nothing in it is
prose-only.

```python
# #EDGE: data-integrity: a promotion PR could be opened from a stale bundle
# after the parent skeleton changed on main; parent_sha256 mismatch must be
# a hard failure in the (WS-8) promotion tooling and a review-checklist item
# in the manual D8 flow.
# #VERIFY: bundle.py records the hash; the D8 promotion runbook step 1 is
# "re-run scripts/mutate_skeleton.py --verify-bundle", which recomputes and
# compares before any PR is opened.
```

### 9.3 The demand loop (informative, not built here)

WS-4's `selection.cell_theme_saturated` at `DifferentiationLevel.CATALOG` is
the trigger WS-8 will eventually wire to bundle generation for the saturated
cell. WS-5 keeps the interface honest by making the CLI cell-addressable
(`--band --length --style` select parents), consuming the signal as a cell
coordinate only, never as theme text (section 3, principle 6).

## 10. Safety-invariant mapping (plan section 7)

| Invariant | How WS-5 upholds it |
| --- | --- |
| **7.1** Neither a theme nor a leaf can change gate-verified structural properties, the fail-state policy, the reading band, or the ending kind/valence policy; the frozen safety object is the ADR-011 constraint grammar, enforced by the gate on every tree and fill. | WS-5 changes structure deliberately, and 7.1 permits exactly that reading: the frozen object is the *grammar*, not the 59 graphs (plan section 3, lines 120-131). Every operator states which grammar clauses it can perturb and pre-checks them (sections 4-5); the identical gate re-verifies every mutant (section 6, stage 1); the band is inherited verbatim (OQ-4); the ending kind/valence policy is preserved by construction where possible (M1/M5 never touch endings; M2 permutes an invariant multiset; M3 re-counts against PL-15/PL-17) and re-proven by PL-15/16/17 regardless. Themes and leaves still cannot change structure: the WS-2 render invariants are untouched, and mutation is not reachable from any theme or request input. |
| **7.2** Every generated story passes the full `validator/` gate and `moderation/` review before publish. No novelty exception. | Twice over: the mutant shell passes the full gate at acceptance (stage 1) and again at every `load_skeleton`; every story filled from a promoted mutant runs the unchanged fill -> `run_gate` -> `run_moderation_pipeline` -> ADR-005 approval chain (section 2.2). The no-novelty-exception rule is restated as blocking in section 6, and the WS-5 additions are stricter-only. |
| **7.3** Per-band content guarantees (K13) are enforced by the structure + the gate, never by trusting a theme brief; theme freedom is bounded per band, per slot, in the theme contract. | Mutants keep the structural enforcement (PL-15 forbidden kinds, PL-16 ceilings re-run per mutant; M3 grafts are same-band only, so no donor content crosses a band boundary). Mutated contracts cannot weaken the slot-level bound: `validate_slot_bindings` unions the band-mandatory denylist floor irrespective of contract content, and D7 pins a test that a mutated contract with an emptied `forbid` list still fails a floor-violating binding (CR-4). |
| **7.4** Untrusted-input handling (LLM01) covers derived artifacts; fence at every reuse. | WS-5 admits no untrusted input at all: operator inputs are catalog files, parameters, and seeds (section 3, principle 6); the WS-4 demand signal is consumed as a cell counter, never text; re-guidance authoring consumes catalog content only. The one LLM touchpoint, the stage-5 sample fill, uses the default binding/default theme (catalog data) under the existing fenced fill pipeline unchanged. No WS-5 artifact re-enters any prompt except through paths that already fence (the fill's own machinery). |
| **7.5** Novelty floor: selection never fully excludes an eligible option; learning-driven selection keeps an exploration bonus. | WS-5 does not touch `skeleton_match.py`; `_weight`/`_blended_weight`'s nonzero floor is intact, and each promoted mutant enters selection as an unused candidate at weight 1.0 (maximum exploration), which is the mechanism by which new trees actually reach readers. The complementary direction, that a "new tree" be genuinely new, is the anti-clone floor (4.6): WS-5 may not dilute the catalog with clones that would let the metric rise while perceived uniqueness does not. |

## 11. What does not change

- `validator/` and `moderation/`: no rule, threshold, cap, or severity is
  edited. (OQ-8's PL-23 idea is explicitly a separate, later proposal.)
- `generation/`: `skeleton.py`, `orchestrator.py`, `worker.py`, `binding.py`,
  all templates, byte-identical. The one code touch outside `mutation/` and
  `scripts/` is the sidecar-skip generalization in
  `skeleton_match._production_candidates` (D8, behind OQ-1).
- Selection weights, the WS-4 similarity blend, and the novelty floor.
- The WS-2 contract format, the slot validator, the render post-conditions.
- `skeletons/**` on disk: WS-5 writes only under `out/mutations/`; the
  catalog changes exclusively through reviewed promotion PRs.
- ADR-005 human story approval; ADR-019's decisions; the series
  meta-validator (series parents are out of scope).

## 12. Deliverables

Ordered cheapest-and-safest first; each is independently landable and
reviewable.

- **D1. Mutation core** (`src/cyo_adventure/mutation/`: `ops.py`,
  `subtree.py`, `identity.py`): the operator protocol/registry, subtree
  extraction with the self-containment and closedness checks, deterministic
  id renaming, metadata resync (ending_count, estimated_minutes, tier,
  topology re-declaration per 4.8). Pure, no I/O. **Tests:** unit +
  hypothesis property tests over all 59 catalog files (self-containment
  soundness, rename collision-freedom, resync correctness). **Safety
  property:** no D1 utility can emit a document with duplicate ids or a
  metadata/ending mismatch (schema validators are the backstop; D1 tests
  prove the constructive direction).
- **D2. M1 + the acceptance harness + CLI** (`mutation/acceptance.py`,
  `scripts/mutate_skeleton.py`, M1 in `ops.py`): the section 6 stage table
  end to end for Tier-1 parents, minus contract handling and floors
  (stages 0-2 plus reguide tracking); structured discard logging.
  **Tests:** M1 on fixtures + real Tier-1 skeletons; property: gate never
  blocked on accepted output, ending multiset invariant, in-degrees
  invariant; discard path pinned on a seeded cycle-creating swap. **Safety
  property:** the harness cannot mark a `blocked=True` candidate promotable
  (assert against a monkeypatched always-block gate).
- **D3. M2 ending re-map** (composition-only per 4.3): the permutation
  operator, the PL-20 depth precondition, reguide emission for affected
  leaves. **Tests:** multiset invariance property; a permutation moving
  `success` above the floor is discarded pre-gate; composed M1+M2 chain
  produces one lineage `op_chain` of length 2. **Safety property:** PL-15
  can never fire on an M2 output (multiset proof + gate backstop test).
- **D4. M3 prune/graft** (Tier-1, closed subtrees, same-band donors):
  including contract slot drop/merge mechanics (dry, tested against WS-2
  models; full contract acceptance lands in D7). **Tests:** envelope
  two-sided enforcement; PL-17 floors; donor id renaming; a graft pushing
  choices-per-decision past 3 is discarded at stage 0. **Safety property:**
  no cross-band content ingress (donor-band precondition test), and pruning
  can never remove the last satisfying ending.
- **D5. M4 decisions-per-path**: insert-linear, remove-linear,
  insert-decision (reconvergence and micro-stub variants). **Tests:**
  per-path decision counting exact on acyclic fixtures; 4-8 window enforced;
  PL-20 monotonicity claim for insert-linear proven by property test;
  remove-linear below-floor discard. **Safety property:** inserted nodes are
  always effect-free and condition-free in v1 (constructor-enforced).
- **D6. M5 state variation** (`mutation/state_ops.py` + the 5.3 acceptance
  additions): M5a retune, M5b gate/add/relocate, the single-walk ending
  coverage and clock re-proof, the state-signature vector and distance,
  play-feel delta report in `acceptance.json`. **Tests:** on
  the-flooded-quarter fixtures: an `oil` retune that strands one ending is
  discarded by coverage (not by L2); a gated shortcut undercutting the
  walk-derived fastest finish is discarded by the clock re-proof; L2-9/10/11
  regression pins; capped-walk discard; alpha-rename is signature-neutral
  and floor-fails alone. **Safety property:** M5 constructors reject any
  edit to an `ending` block, `kind`, or `valence` at the type level.
- **D7. Floors + contract acceptance integration**: calibrate and commit
  `TAU_STRUCT`/`TAU_CELL`/`TAU_STATE` from the catalog's in-cell pairwise
  distance distributions (a small committed baseline artifact next to the
  WS-0 eval panel, plus the calibration script); wire stage 4
  (`check_theme_contract.py`) into the harness; the CR-4 band-floor pin
  test. **Tests:** floor calibration reproducibility; a fingerprint-equal
  mutant is rejected; a mutated contract with weakened `forbid` lists still
  fails floor-violating bindings. **Safety property:** floors reject-only
  (no code path admits on floor success alone; the gate stages remain
  mandatory).
- **D8. Bundle + first promotion + docs/ADR**: `mutation/bundle.py`
  (lineage/acceptance schemas, `--verify-bundle`), the sample-fill stage,
  diagram generation, the sidecar-skip generalization in
  `skeleton_match._production_candidates` (behind OQ-1's ruling), one manual
  end-to-end promotion of a first mutant via PR (the ADR-020 evidence
  exhibit), catalog doc regen; draft ADR-020 from section 8 for
  ratification; update `story-flexibility-plan.md` (WS-5 status note + fix
  the stale section 9 ADR-019 bullet), `capability-register.md` K3 note, and
  `docs/template_feedback.md` if any template gap surfaces (none identified
  by this design). **Tests:** bundle round-trip, hash-mismatch hard failure,
  scanner skip produces no candidate and no spurious warning. **Safety
  property:** `scripts/mutate_skeleton.py` refuses to write under
  `skeletons/` (promotion is a PR, never a script side effect).

Sizing: D1-D2 are the first implementer unit (framework + one operator +
harness, the "single-operator mutation + gate re-run" cheapest slice); D3-D5
the second (the remaining structural operators); D6 the third (state); D7-D8
the fourth (floors, contracts, promotion, ADR). Each unit lands green on the
standard quality gates before the next starts.

## 13. Testing strategy

Unit (no network, no live DB, offline files only, per the `tests/` suite
posture; note the whole workstream is designed to need neither):

- Property tests (hypothesis) are the backbone, run over the real 59-file
  catalog as the corpus: for every operator, on every applicable parent, with
  seeded rngs: accepted output implies `run_gate(...).blocked is False`,
  declared invariants hold (per-operator invariant tables in sections
  4.2-4.5), and lineage replay (`apply(parent, params, seed)`) is
  byte-deterministic.
- Discard-path coverage: every stage of the section 6 table has at least one
  pinned discarding fixture, including the monkeypatched always-block gate
  (the harness must discard even when the failure is upstream of its own
  logic).
- Walk-based tests reuse `walk_configurations` directly on small stateful
  fixtures (10-20 nodes) so L2 semantics are pinned without 155-node run
  times; the-flooded-quarter runs once per suite as the integration-scale
  case.
- Mutation-testing candidates (mutmut): `subtree.py` self-containment,
  `identity.py` renaming, the acceptance stage ordering.
- Coverage: >= 80% overall, near-100% for `subtree.py`, `identity.py`,
  `acceptance.py` (they are the safety-bearing pure core).
- Quality gates: BasedPyright strict, Ruff, Bandit, pre-commit, signed
  Conventional Commits, no U+2014 anywhere including template and log
  strings.

Integration: the D8 end-to-end (mutate -> accept -> bundle -> verify-bundle ->
promotion-PR dry run on a temp copy of skeletons/) as a nox-runnable script;
the promoted-mutant fill path is covered by the existing worker/orchestrator
suites automatically once the file sits in skeletons/ (no new integration
seam, by design).

## 14. Risks and critical-review items

**CR-1 (blocking). No mutant reaches skeletons/ or selection without full
acceptance plus human PR approval.** Enforced by: the CLI's refusal to write
under `skeletons/`, promotion existing only as a reviewed PR, and no runtime
code path reading `out/mutations/`. WS-8 automation must inherit this as
"automation prepares PRs, humans merge them".

**CR-2 (blocking). Discard-only failure handling; the gate is never touched.**
No WS-5 module imports anything from `validator/` except to *call* it; no
threshold, cap, scale, or severity is configurable from mutation code; floors
are reject-only (D7 safety property).

**CR-3 (blocking). Identity and metadata integrity by construction.** Unique
ids, ending_count/tier/topology resync, contract token-set equality: each has
a constructive check in D1/D4 AND a fail-closed backstop in the schema, gate,
or `load_contract_for`, and tests must cover both directions.

**CR-4 (blocking). A mutated contract can never weaken the band floor.**
`validate_slot_bindings` unions `band_mandatory_bundles` regardless of
contract content; D7 pins the test. Slot merges copy donor constraints
verbatim; slot drops require the surface to be gone.

**CR-5 (blocking, LLM01). No untrusted input enters mutation.** No request
text, brief, premise, or theme-derived artifact is an input to any operator,
precondition, floor, or bundle field; the WS-4 signal is consumed as a cell
coordinate. Grep-style test mirroring WS-1 exit criterion 5: `mutation/`
imports nothing from `story_requests/` and no function accepts a brief.

Risks (non-blocking):

1. **Reguide quality** is the residual editorial surface. Bad seam guidance
   yields awkward fills; bounded by the reguide-resolved promotion
   requirement, the sample-fill evidence, Stage 1 fidelity at fill time, and
   the human structure review. Watch fidelity-flag rates on mutant-derived
   stories vs catalog baseline (WS-0 can slice by slug).
2. **Discard-rate economics.** If most attempted mutants die at the gate or
   floors, the tooling is cheap but the human parameter-picking time is not;
   the structured discard logs exist to tune preconditions. Acceptable
   because zero product risk attaches to a discard.
3. **Floor gaming.** `structural_distance` is a feature-vector metric; an
   operator chain could learn to move features without moving perceived
   structure. Mitigated by the human structure review seeing the diagram, and
   revisitable when WS-0's judge-model phase (Phase 3) can score
   tree-pair distinctness.
4. **Catalog bloat.** Many promoted mutants per cell flatten selection
   weights and increase contract-maintenance surface (ADR-019's "59 contracts"
   cost grows). Governed by promoting on demand (the WS-4 saturation signal)
   rather than on supply.
5. **Tier-2 walk cost.** M5 acceptance re-walks per candidate; the-flooded-
   quarter-scale walks are sub-cap but not free. Bounded by running walks
   once per candidate (single-WalkResult rule) and by M5's operator
   preconditions filtering obvious stranding pre-walk.
6. **Metadata constants drift.** `estimated_minutes` resync uses ADR-011
   pace anchors; if the ADR's numbers are retuned, D1's resync must follow
   (single-source the anchors from `band_profile.py` where they exist).

## 15. Open questions for sign-off

Each with a recommendation; all are ratification items for the supervisor
review, and OQ-6 is the one that becomes a standalone ADR.

- **OQ-1 (lineage placement).** A `skeletons/<band>/<slug>.lineage.json`
  sidecar with a generalized scanner skip (ADR-020 decision 2), or
  bundle/PR-only lineage with no new file class in skeletons/?
  **Recommendation: the sidecar.** Lineage must survive the bundle's
  `out/` lifetime and version atomically with the tree (the same argument
  ADR-019 Decision 2 made for contracts); the scanner change is one suffix
  check plus one test.
- **OQ-2 (contract parity for Tier-2 parents).** May mutants of the 12
  contract-less Tier-2 parents land contract-less (parity), or must WS-5
  block M5 promotion on the WS-2 Tier-2 migration?
  **Recommendation: parity.** Blocking would strand the entire state half of
  the workstream on an unscheduled WS-2 wave; a contract-less mutant is
  exactly as safe as its contract-less parent (same free-text fill path, same
  gate), and both migrate together later.
- **OQ-3 (floor posture and provisional values).** Ratify the anti-clone and
  state-signature floors as blocking-at-promotion with D7 calibration
  (P25-of-in-cell for `TAU_STRUCT`, observed in-cell minimum for `TAU_CELL`),
  versus advisory-first. **Recommendation: blocking.** An advisory floor on a
  metric whose whole purpose is to keep the headline metric honest would let
  the distinct-trees count inflate silently; floors reject-only, so blocking
  carries no safety risk.
- **OQ-4 (cell inheritance).** Fixed parent cell in v1 (this design), or
  permit length-cell changes when prune/graft moves the node count across an
  envelope boundary? **Recommendation: fixed.** Cross-cell derivation changes
  the clocks, floors, and (for teen bands) style semantics all at once;
  revisit as an ADR-020 amendment with evidence.
- **OQ-5 (structure-approval mechanism).** PR review of skeletons/ as the
  human structure-approval step (this design, ADR-020 decision 4), or a new
  in-app admin surface? **Recommendation: PR review for WS-5.** The catalog
  is already git-versioned and PR-reviewed (ADR-019 Decision 2 rationale);
  an in-app surface is WS-8 scope if promotion volume ever warrants it.
- **OQ-6 (ADR-020).** Ratify the section 8 decision set as ADR-020
  "Mutation-derived skeletons and catalog growth" at D8, with the first
  promoted mutant as evidence. **Recommendation: yes**; without it, decisions
  1-6 live only in this workstream doc, which is exactly the
  unrecorded-model failure ADR-011's context section warns about.
- **OQ-7 (operator chains).** Single-operator mutants only, or bounded chains
  (<= 3 ops, recorded in `op_chain`)? **Recommendation: bounded chains**,
  because M2 is composition-only by construction (4.3) and the highest-value
  mutants pair a structural op with an outcome re-map; the lineage schema
  already carries chains, and acceptance runs on the final candidate
  regardless of chain length.
- **OQ-8 (PL-23 family).** Should the ADR-011 section 6 constants and
  section 7 band-allowance table gain deterministic validator rules, so the
  gate enforces what today only authoring discipline (and now WS-5
  preconditions) enforce? **Recommendation: yes, but as its own follow-up
  proposal after WS-5**, because new blocking rules must first be measured
  against the existing 59-file catalog for false positives; WS-5 does not
  depend on it (operators enforce the constraints regardless).
- **OQ-9 (mutation substrate).** Confirm the shell-only rule: operators never
  consume or produce filled stories. **Recommendation: confirm.** Filled-story
  mutation would create a second authoring path that bypasses fill fidelity
  and the ATG, for no diversity gain the shell path does not already provide.
