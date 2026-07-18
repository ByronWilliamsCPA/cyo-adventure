# Initial story inventory: run status summary

Live status grid for the authoring run defined in
`docs/planning/story-inventory-initial-run.md`. Updated by the supervisor at
wave boundaries and major approvals.

## CURRENT STATUS (2026-07-18): WAVE 5 COMPLETE (36 of 36 approved)

**All 36 new skeletons are designed, independently reviewed, and approved.**
The 14 pre-run stories (below) plus the 36-skeleton catalog expansion are the
full deliverable of the initial inventory run. Nothing has been imported to
the database or published (deferred per ADR-005; see Import / publication).

The wave ran on two designer models. Fable designed briefs #1-#20 (all bands
through 10-13); when Fable hit its usage limit, operator direction ("try with
opus") moved the designer role to Opus for the remaining hard cells (#21-#36:
the 13-16 and 16+ prose pairs and all 8 dagger gamebooks). Opus-designed
skeletons cleared the independent Opus reviews as cleanly as the Fable ones.
Every one of the 36 passed check_skeleton on the designer's first sound build
and cleared its adversarial review; the reviewer-required repairs were all
bounded (grip-description accuracy, a setback->death re-tag, a capture-body
widen, and one title-pool widen), never a structural reject.

## Stories (one per offered age x length combination, prose)

| Band | Length | Story | Author | Status |
| --- | --- | --- | --- | --- |
| 3-5 | short | the-clover-and-the-butterfly | haiku | **APPROVED** (1 cycle) |
| 3-5 | medium | the-teddy-bears-picnic | haiku | **APPROVED** (2 cycles) |
| 5-8 | short | the-lantern-festival | haiku | **APPROVED** (1 cycle) |
| 5-8 | medium | the-backyard-treasure-map | haiku -> opus | **APPROVED** (2 cycles + Opus rewrite + re-review) |
| 8-11 | short | the-cave-of-echoes | sonnet | **APPROVED** (1 cycle) |
| 8-11 | medium | the-sky-ship-stowaway | sonnet | **APPROVED** (1 cycle) |
| 8-11 | long | the-clockwork-menagerie | opus | **APPROVED** (1 cycle) |
| 10-13 | short | the-midnight-museum | sonnet | **APPROVED** (1 cycle) |
| 10-13 | medium | the-hollow-lighthouse | sonnet | **APPROVED** (2 cycles) |
| 10-13 | long | the-mapmakers-island | opus | **APPROVED** (1 cycle) |
| 13-16 | medium | the-signal-in-the-static | sonnet -> opus | **APPROVED** (opus repair + dominator fix) |
| 13-16 | long | the-vanishing-orchard | opus | **APPROVED** (0 cycles) |
| 16+ | medium | the-last-train-north | sonnet -> opus | **APPROVED** (opus repair) |
| 16+ | long | the-salt-archive | opus | **APPROVED** (title fix) |

**14 of 14 APPROVED. Core objective complete.** Waves 1-3 done. Wave 4
(4 optional gamebook variants) not started; Wave 5 skeleton design held on
the Fable outage.

## Wave 5 skeletons (2 new per production cell; 36 total)

**36 of 36 APPROVED** (each with a design report under
`out/reports/skeletons/`):

| Cell | Approved new skeletons |
| --- | --- |
| 3-5 short | the-sleepy-little-star, puddle-jumping-day |
| 3-5 medium | the-big-red-balloon, baking-day-with-grandma-vole |
| 5-8 short | the-school-garden-mystery, the-snow-day-expedition |
| 5-8 medium | the-tide-pool-rescue, the-night-market |
| 8-11 short | the-robot-fair-sabotage, the-locked-carousel |
| 8-11 medium | the-storm-chasers-club, the-river-of-small-boats |
| 8-11 long | the-guild-of-junior-inventors, the-hundred-door-hotel |
| 10-13 short | the-midnight-frequency, the-glass-comet |
| 10-13 medium | the-envoy-of-three-courts, the-flooded-quarter |
| 10-13 long | the-skyrail-heist, the-winter-of-the-wolf-queen |
| 13-16 medium | the-undertow-season, the-conservatory-wars |
| 13-16 medium gamebook | the-iron-spire-trial (gauntlet T2), the-smugglers-cut (b&b) |
| 13-16 long | the-year-of-four-banners, the-hollow-sea |
| 13-16 long gamebook | the-labyrinth-of-glass (gauntlet, LOW), the-serpent-vaults (gauntlet T2, CHALLENGER) |
| 16+ medium | the-third-shift, the-quiet-harbor-protocol |
| 16+ medium gamebook | the-red-meridian-run (gauntlet, LOW), the-cinder-bazaar (b&b T2, CHALLENGER) |
| 16+ long | the-tricameral-city, the-longwinter-station |
| 16+ long gamebook | the-pale-road (gauntlet, LOW), the-tenfold-siege (gauntlet T2, CHALLENGER) |

Pipeline metrics: every approved skeleton (Fable- and Opus-designed alike)
passed check_skeleton on the designer's first sound build and cleared its
independent Opus review; no skeleton was rejected. The catches only an
adversarial reviewer could make were the recap-leak class (tier-1
statelessness), the guild track-isomorphism (replay rhythm), the conservatory
floor/telegraph polish, the pale-road setback-vs-death mislabel, and the two
challenger prose defects (tenfold-siege title recycling, serpent-vaults
capture-body templating).

## New topology pattern-setters established this wave

- **gauntlet** (the-red-meridian-run): the first gauntlet in the project.
  Structurally an acyclic DAG with reconvergence (same class as b&b, declared
  gauntlet); a shallow checkpoint spine with restart-on-fail unrolled forward
  (no back-edge), fair-lethality telegraphs, few deep wins / many shallow
  fails. Its 9-rule pattern set (in design-briefs.md) governed the other five
  gauntlets, with a propagation refinement that fixed its one weakness:
  per-checkpoint-specific dread beats (the-labyrinth-of-glass then hit 94/94
  distinct dread beats).
- **tier-2 gauntlet** (the-iron-spire-trial): state-gated survival plus wins
  differentiated by accumulated state, exact-partition at the state gates with
  unconditional companions so no state is choiceless.

## Dagger-cell experiment result (per operator direction)

Each dagger cell paired a low-end skeleton with a ceiling-challenger
targeting the upper envelope, to test ADR-011's ~460-node hand-authoring
ceiling. The three challengers give a clean three-point curve:

| Challenger | Nodes | Distinct titles | Templated bodies | Structural correctness |
| --- | --- | --- | --- | --- |
| the-cinder-bazaar | 453 | 141/141 | ~57% (80/141 death beats) | clean by construction |
| the-serpent-vaults | 530 | 172/172 (after 1 fix) | ~19% | clean by construction |
| the-tenfold-siege | 677 | 209/209 (after title-pool widen) | shared death frame | best-win misgate caught only by the config walk |

**Finding: the ~460 ceiling is a hand-reasoning-safety limit, not a
structural one.** Machine-checkable invariants (acyclicity, exact partition,
reachability, word budgets) scale by construction at every size tested
(306 -> 677) with a builder + the Layer-2 walk. What breaks past ~600 is
correctness-by-hand: tenfold-siege's best win was gated on a state
(supplies==3 at the finale) that is unreachable because the command tradeoff
spends the magazine to hold morale, a defect invisible to inspection and
caught only by walking all 9,832 configs. Content-distinctness does NOT break
structurally (title recycling was an authoring economy, widened to 209/209 as
a bounded fix; and the 530-node book was proportionally CLEANER than the
453-node one). Practical conclusion: past the ceiling, the config-walk gate
becomes mandatory rather than optional.

## Firsts / pattern-setters established (with recorded rule sets)

- **open_map**: the-school-garden-mystery (recap-only-path-universal-facts rule).
- **sorting_hat**: the-storm-chasers-club (PL-18 pure-tree; informational sort;
  one-canonical-fact-sheet anchors). Guild added: replay-rhythm difference > balance.
- **tier 2 (stateful)**: the-glass-comet (7 tier-2 rules: <=3 vars, exact-partition
  at convergence, unrolled self-terminating retries, early-gated best outcome,
  entry-agnostic state-reflecting beats, <=8-10 clicks, depth headroom).
- **tier-2 open_map**: the-flooded-quarter (base-plus-adds relaxation valid only
  while every gated node keeps a verified unconditional companion; monotone
  once-per-spoke progress var for the best outcome; auto-reset inventory at hub
  and muster; arrival-neutral reconvergence). Reaffirmed by undertow-season and
  the-hollow-sea (197 nodes, 15,510 configs).
- **tier-2 branch_and_bottleneck**: the-quiet-harbor-protocol (exact-partition at
  all convergence gates proven by the config walk; best outcome gated exactly at
  one config; dominator-clean high-weight funnel). First stateful b&b of the run.
- **gauntlet** and **tier-2 gauntlet**: see "New topology pattern-setters
  established this wave" below.

## Run-wide process rules (enforced in later prompts)

1. FK tuning varies sentence shape, never uniform shortening; a dedicated
   ending-grammar pass is mandatory (fragments concentrate at endings).
2. Haiku lean-fill: words=N hints are hard targets; PL-19 named in exit criteria.
3. Review the highest-weight convergence node hardest.
4. Fill-time repair rounds must re-validate CROSS-PATH logic, not just the edited node.
5. Bounded reading-level waiver: kill the above-band tail, lift under-band nodes,
   waive the mild residual with justification (used on signal, train).
6. Shelf quotas: 5-8 hub-and-spoke full (2); 8-11 open_map full (2); 8-11
   time_cave tones full (2); next 8-11 short avoids another old-machine reveal.

## Skeleton defects filed against pre-run production skeletons

- `the-hollow-lighthouse` beats at tn_keeper / tn_store_join / tn_store_box
  assume route-specific items; the fill compensates in prose, but the beats
  should be reworded route-neutral in a future skeleton revision.
- `the-signal-in-the-static` beats compound both mystery threads at n_b3 and
  leak "Marin"/logbook/scrap into merge nodes reachable without them; the
  Opus repair compensates in prose; beats should be reworded.

## Import / publication

Deferred per plan section 8 and ADR-005. Deliverables stop at committed
filled JSONs + skeletons + reports; nothing imported to Postgres or published.
