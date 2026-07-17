# Initial story inventory: run status summary

Live status grid for the authoring run defined in
`docs/planning/story-inventory-initial-run.md`. Updated by the supervisor at
wave boundaries and major approvals.

## CURRENT HOLD (2026-07-17)

**Fable is unavailable** ("usage credits required"). Per operator direction,
all Wave 5 skeleton **design** work is paused (designs use Fable). The
non-Fable pipeline continues on Opus: story fills, compliance/design reviews,
repairs, and adjudication. Three designers were mid-run when Fable went down
and are PARKED for resume when directed: `the-envoy-of-three-courts` (#17),
`the-midnight-frequency` (#15), `the-flooded-quarter` (#18). Designs #19-#36
not started.

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

**15 of 36 APPROVED** (each with a design report under
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
| 10-13 short | the-glass-comet (+ the-midnight-frequency PARKED) |

Remaining (all PARKED on Fable-down): the-midnight-frequency (#15),
the-envoy-of-three-courts (#17), the-flooded-quarter (#18), and designs
#19-#36 (10-13 long through 16+ long, incl. the 4 dagger-cell challengers).

Pipeline metrics: every approved skeleton passed check_skeleton on the
designer's first run; the two catches only an independent reviewer could
make were the recap-leak class (tier-1 statelessness) and the guild's
track-isomorphism (replay rhythm); every repair converged in one cycle.

## Firsts / pattern-setters established (with recorded rule sets)

- **open_map**: the-school-garden-mystery (recap-only-path-universal-facts rule).
- **sorting_hat**: the-storm-chasers-club (PL-18 pure-tree; informational sort;
  one-canonical-fact-sheet anchors). Guild added: replay-rhythm difference > balance.
- **tier 2 (stateful)**: the-glass-comet (7 tier-2 rules: <=3 vars, exact-partition
  at convergence, unrolled self-terminating retries, early-gated best outcome,
  entry-agnostic state-reflecting beats, <=8-10 clicks, depth headroom).

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
