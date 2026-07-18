---
schema_type: planning
title: "Exploration: Pathfinder-derived mechanical structure for teen gamebook cells"
description: "Exploratory study of whether Open Game Content mechanics from the Pathfinder
  tabletop RPG (skill checks, a light character sheet, resources, conditions, progression)
  could be mapped onto the existing deterministic Tier-2 Storybook state machine to give the
  13-16 and 16+ gamebook cells more mechanical depth, plus the licensing analysis that gates
  any such use, and a 2026-07-18 comparison recommending CC-BY-4.0 sources (D&D SRD 5.1/5.2,
  Kobold Press Black Flag Reference Document) over Pathfinder's OGL/ORC if reference text is
  ever shipped."
tags:
  - planning
  - exploration
  - generation
  - gamebook
  - licensing
status: exploratory
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Record a future-improvement exploration (not a committed build): the mapping from
  Pathfinder structural elements to the Tier-2 variables/conditions/effects model, the
  deterministic replacement for dice, a minimal single-cell proposal, honest costs, and the
  OGL 1.0a / ORC licensing obligations with a recommendation to obtain legal review before
  any adoption."
component: Strategy
source: "Exploration 2026-07-18 against storybook/models.py, storybook/condition.py,
  storybook/evaluator.py, player/engine.py, validator/walk.py, validator/layer2.py,
  band_profile.py, skeletons/13-16/the-iron-spire-trial.json,
  skeletons/16+/the-tenfold-siege.json, ADR-011, and the story-flexibility plan."
---

# Exploration: Pathfinder-derived mechanical structure for teen gamebook cells

> **Status: EXPLORATORY / FUTURE IMPROVEMENT. This is not a committed build.**
> It is a study for the owner to accept, trim, or reject. Nothing here changes
> schema, validator, player, or catalog. The licensing section is analysis, not
> legal advice; a legal review is a hard gate before any adoption of licensed
> text (section 8).
>
> **Source-system update (2026-07-18):** the section 3-6 mechanical mapping is
> system-agnostic. Section 7.4 now compares D&D SRD 5.1/5.2 and Kobold Press's
> Black Flag Reference Document (both CC-BY-4.0) against Pathfinder's OGL 1.0a /
> ORC, and recommends a CC-BY-4.0 source over ORC or OGL if reference text is
> ever shipped (Option B). CC-BY-4.0 removes almost every compliance obligation
> in section 7.2. The inspiration-only recommendation (Option A) is unchanged.

Serves, if pursued: [K3](capability-register.md) (state and consequence),
[K18](capability-register.md) (ratings/engagement as the success signal). It is
a candidate instrument for the story-flexibility plan's third diversity axis
("state / consequence", `story-flexibility-plan.md` section 4) and for WS-5's
"vary Tier-2 variable semantics and condition-gated routes".

---

## 1. Motivation

The teen gamebook cells (13-16 medium/long gamebook, 16+ medium/long gamebook,
ADR-011 master table) are the app's closest analog to classic Fighting
Fantasy-style gamebooks: gauntlet topology, lethal restart-on-fail, many fail
endings, few wins. Today their mechanical vocabulary is real but thin:

- `the-iron-spire-trial.json` (13-16, medium gamebook, 277 nodes): three
  variables (`standing` 0-2, `grip` 0-3, `token` bool), nine conditional
  choices. The summit resolver already IS a deterministic skill check:
  `standing == 2` opens the honour path, `== 1` the creditable win, `<= 0` the
  unnamed summit.
- `the-tenfold-siege.json` (16+, long gamebook, 677 nodes): `supplies` 0-3,
  `morale` 0-3, `breach` bool; 33 conditional choices, 126 effects. `supplies`
  is already a resource pool drawn down by hard stands and restored on quiet
  nights.

So the target cells are half-way to a mechanics layer already, but each
skeleton invents its idiom from scratch. What is missing is a **shared,
teachable grammar**: what a stat is, what a check is, what degrees of success
look like, how resources drain and recover, how a build made early pays off
late. Tabletop RPGs solved exactly this grammar over decades, and the
Pathfinder rules corpus is the largest openly licensed body of it (Pathfinder
1e under the Open Game License 1.0a; the Pathfinder 2e Remaster under the ORC
License). The question this document explores: **which Pathfinder structural
elements survive translation into a deterministic, replayable, dice-free state
machine, what they cost, and what the licenses actually permit and require.**

Two constraints frame everything:

1. **The player is deterministic and pure** (`player/engine.py`, mirrored by
   the TypeScript player). No RNG exists anywhere in the runtime; state is a
   pure function of the choice path; "Go back" is implemented by replaying the
   recorded path from `start_node` (`frontend/src/player/engine.ts`). Any
   mechanic must resolve from accumulated state, never from a roll.
2. **Everything must pass the existing gate unchanged.** Tier-2 stories run
   the L2 configuration walk (`validator/walk.py`, cap 100,000 configurations,
   L2-12 hard error on cap), plus L2-9 (stateful dead ends), L2-10 (loop
   escape), L2-11 (dead branches), and the L2-13 scale advisory past the
   460-node hand-authoring ceiling. The proposal in section 6 deliberately
   requires zero schema or validator change.

## 2. The machine we are mapping onto (ground truth)

| Construct | What exists today | Hard limits |
| --- | --- | --- |
| `variables` | Declared per story; `bool` or `int` only; ints may carry `min`/`max`, runtime-clamped | Tier 2 only; every int literal bounded by `MAX_ABS_STORY_INT` (1e9) |
| `on_enter` / choice `effects` | `set`, `inc`, `dec`; `inc`/`dec` deltas non-negative ints; `once: true` fires on first node entry only | Type-checked against declarations at schema parse |
| Choice `condition` | JSONLogic subset: `var`, `== != < <= > >=`, `and`/`or` (n-ary), `!`; total evaluator, fails closed | **No arithmetic**, no `in`, no ternary; ordering on ints only; depth cap 50 |
| Choice visibility | Condition false = choice hidden (not greyed out) | The reader never sees an unpassable check as a button |
| Endings | `kind` (success/setback/death/capture/completion/discovery) x `valence` | Per-band policy: death legal from 13-16 up; content ceilings via `band_profile.py` |
| Topology | gauntlet (the gamebook shape), branch_and_bottleneck, open_map, sorting_hat, etc. | Per-band allowances (ADR-011 section 7) |
| L2 walk | BFS over `(node, var_state, once-visit set)` | 100k config cap (L2-12 error); L2-13 advisory past 460 nodes |
| Series | `carries_state: true` exports declared state to the next book's single entry node | Linear chain, v1; each book passes its own gate |

Two DSL consequences that shape every mapping below:

- **No arithmetic in conditions** means there is no "roll + modifier vs DC".
  A DC is a literal int compared against one variable (`{">=": [{"var":
  "might"}, 2]}`). A "combined" check is an `and`/`or` of per-variable
  thresholds. A derived total (Pathfinder's ability modifier + proficiency)
  must either not exist or be maintained as its own variable by paired
  effects. This is a feature for legibility: every check is readable as "do I
  have enough X".
- **Hidden-when-false visibility** means checks are authored as *resolver
  nodes* whose outgoing choices partition the reachable state space, exactly
  the pattern `sheer_resolve` and `summit_gate` already use in the Iron Spire
  Trial. The reader is routed by what they have become, and the gate proves
  the partition is total (L2-9) and every band is live (L2-11).

## 3. Mapping table: Pathfinder element to CYO Tier-2 construct

"Walk cost" is the multiplicative pressure on the L2 config cap; section 6.4
does the arithmetic.

| Pathfinder element | Deterministic CYO mapping | Constructs used | Topology fit | Walk cost | Verdict |
| --- | --- | --- | --- | --- | --- |
| Ability scores / skills | A **light character sheet**: 2-4 small ints (range 0-3), built early and trained by choices | `variables` (int, min/max), `set`/`inc` effects | Any; creation via an early sorting-hat-style branch inside a gauntlet | The dominant cost; each stat multiplies the state product | **Adopt, hard-capped small** |
| Skill check vs DC | **Resolver node**: mutually exclusive threshold conditions route to outcome nodes; DC is the literal | choice `condition` with `>=`/`<=` | gauntlet checkpoints; branch_and_bottleneck gate nodes | Zero (reads state, adds none) | **Adopt; already proven in Iron Spire** |
| Degrees of success (PF2e crit/success/fail/crit-fail) | 3-4 **threshold bands** on one stat (`>= DC+1` best, `== DC` clean, `DC-1` scrape w/ cost, `<= DC-2` fail) | Same as above plus small effects on the scrape band | Same | Zero to tiny | **Adopt; the single best import** |
| Hit points / resource pools | Bounded int drained by `dec` on hard beats, restored by `inc` at rest beats; a 0-pool state routes to failure via conditions | int var 0-3, effects, condition-gated failure route | gauntlet (Tenfold Siege `supplies` is this today) | One 4-value var = x4 product | **Adopt, one pool max per story** |
| Conditions (frightened, wounded, marked) | Bool flags set by hazard `on_enter`, cleared by remedy choices; gate later options | bool vars, `set` effects, `==` conditions | Any | x2 per flag | **Adopt sparingly (1-2 flags)** |
| Feats / items / boons | Bool gear flags gating visible options ("only with the rope") ; Iron Spire's `token` is exactly this | bool vars, condition-visible choices | Any | x2 per flag | **Adopt (existing pattern, named)** |
| Character creation (ancestry/class/background) | One early **background choice** node; each option `set`s a stat package and maybe a gear flag; later checks make the build matter | 2-3 choices, `set` effects | First decision after the setup nodes | None beyond the sheet itself | **Adopt; this is what makes builds real** |
| Hero points / rerolls | A spendable `resolve` int: a salvage choice on a failed band, visible only if `resolve >= 1`, with `dec resolve 1` | int var 0-2, condition + effect | Failure bands of checks | x3 product | **Adopt as the reroll replacement** |
| Encounter / combat rounds | A 2-4 node **exchange**: each round a tactical choice, damage as `dec`, escape/victory conditions on the pool and flags. NOT a simulation: no enemy HP ledger, no action economy | Nodes + the one pool | gauntlet segments | Costs nodes, little state | **Adopt as structure, reject as simulation** |
| Exploration mode | open_map hub with key-flag gating | Existing topology + bool flags | open_map (13-16 allows it) | Flags as above | Neutral; already possible |
| Leveling / progression across books | Series `carries_state: true`: the sheet exports to book N+1, whose creation node is replaced by a recap that `inc`s one stat | Series metadata (ADR-011 section 8) | Series meta-skeleton | Per-book walks stay independent | **Adopt later (Phase C)** |
| Initiative, action economy, spell lists, full inventories, currency, XP math | No mapping that survives the DSL (needs arithmetic, large ranges, or per-item state) | n/a | n/a | Blowup | **Reject** |

The four highest-value imports, in order: **(1) degrees-of-success threshold
checks, (2) the light character sheet + background choice (builds), (3) one
bounded resource pool with a fail route, (4) the spendable `resolve` salvage
mechanic.** Everything else is either already idiomatic (gear flags) or not
worth its cost.

## 4. The dice problem, resolved

Pathfinder resolves uncertainty with a d20. The CYO runtime has no RNG, must
replay byte-identically (the TS player and the L2 walk both re-derive state
from the path), and offers a "Go back" undo that recomputes state by replaying
the recorded path. Three properties any resolution mechanic must keep:
**deterministic** (state is a pure function of choices), **fair** (both
outcomes of every check are genuinely reachable, and the reader can understand
why they got theirs), and **undo-compatible** (Go back must not become a
reroll button).

### 4.1 The doctrine: your build is the roll

A d20 check "succeeds if d20 + modifier >= DC". The deterministic translation
keeps the DC and the modifier and deletes the die: **a check succeeds iff the
accumulated stat meets the threshold.** The randomness of the die is replaced
by the *variance the reader authored themselves*: which background they chose,
which training beats they took, what they spent earlier. Two readers reach the
Flood Gate with different `wits` because they lived different stories, not
because the universe flipped a coin.

Degrees of success map PF2e's four-tier outcome onto threshold bands over the
small int range:

| PF2e outcome | Deterministic band (DC = 2 on a 0-3 stat) | Typical routing |
| --- | --- | --- |
| Critical success | `stat >= 3` | Clean pass plus a boon (`set` a flag) |
| Success | `stat == 2` | Clean pass |
| Failure (salvageable) | `stat <= 1 and resolve >= 1` | Scrape through at a cost (`dec resolve 1`) |
| Critical failure | `stat <= 1 and resolve <= 0` | The gauntlet's fail route (setback/death per band policy) |

### 4.2 Why this is fair, and provably so

- **Both outcomes reachable, by the gate, not by promise.** L2-11 already
  fails any story where a conditional choice is never visible in any
  reachable configuration. Author every outcome band as a conditional choice
  and the existing validator mechanically proves that some path through the
  story reaches each band. A check nobody can pass, or nobody can fail, is a
  gate failure today, no new rule needed.
- **No hollow-win cheese.** The `min-to-complete` arc floor and the gauntlet's
  ending mix (ADR-011) still bound the shape; a build cannot shortcut past
  the arc.
- **Legible to a teen.** The sheet is 2-4 named quantities with range 0-3.
  The resolver's choice labels state the fiction of the outcome ("Your
  training holds; the mechanism yields"), the pattern Iron Spire already
  uses, so the reader never needs to see numbers to understand the causality.
  Surfacing the sheet in the reader UI is optional polish, not a
  prerequisite.

### 4.3 Why Go back stays safe

Because there is nothing to reroll. Undo replays the path prefix; the
recomputed state is identical every time, so backing up and re-choosing the
*same* choice reproduces the same outcome exactly. Backing up and choosing
*differently* is not save-scumming, it is the product's intended affordance
(mis-tap recovery, K3) and is equivalent to having lived a different story.
Deterministic checks are the only resolution scheme with this property for
free.

### 4.4 Alternatives considered and rejected

- **Pseudo-random from a path hash** (deterministic "dice" seeded by the
  choice history): replayable, but illegible (the reader cannot know why they
  failed), and Go back plus a different intermediate choice becomes a
  literal reroll exploit, which teaches exactly the wrong lesson. Rejected.
- **Server-side RNG recorded into reading state:** breaks the pure
  replay-from-path model the TS player, the offline sync, and the L2 walk all
  depend on; the walk could no longer enumerate the state space. Rejected.
- **Reader-facing "pick a card" pseudo-choice:** fake agency, and still
  effectively a die. Rejected.

## 5. Worked example: one check with a light sheet (13-16 medium gamebook)

Everything below is expressible in the current schema (`schema_version 2.0`)
with zero code change. Cell: 13-16, medium, gamebook (envelope 245-370 nodes,
min-to-complete 24, gauntlet).

### 5.1 The sheet (five declarations)

```json
"variables": [
  {"name": "might",   "type": "int",  "initial": 1, "min": 0, "max": 3,
   "description": "Trained strength. Set by background, +1 at most one training beat. Reachable {1,2,3}. Gates the Flood Gate forcing line and the final holdfast."},
  {"name": "wits",    "type": "int",  "initial": 1, "min": 0, "max": 3,
   "description": "Trained cleverness. Set by background, +1 at most one training beat. Reachable {1,2,3}. Gates the Flood Gate mechanism bands."},
  {"name": "resolve", "type": "int",  "initial": 1, "min": 0, "max": 2,
   "description": "Spendable nerve. Background may grant +1; spent (-1) to salvage a failed band. Never restored. Reachable {0,1,2}."},
  {"name": "rope",    "type": "bool", "initial": false,
   "description": "Courier's climbing line. Gates one optional bypass on the cistern descent."},
  {"name": "marked",  "type": "bool", "initial": false,
   "description": "Whether the wardens noted your face at the gate. Set on the loud Flood Gate outcomes; changes the final approach."}
]
```

### 5.2 Creation: the background choice (one node, three builds)

```json
{
  "id": "muster_choice",
  "body": "<<FILL role=choice words=70 beats='the three trades that raised you, each a different way through what is coming'>>",
  "choices": [
    {"id": "c_bg_forge",   "label": "You were raised at the forge.",
     "target": "gate_approach",
     "effects": [{"op": "set", "var": "might", "value": 2}]},
    {"id": "c_bg_archive", "label": "You were raised in the archive.",
     "target": "gate_approach",
     "effects": [{"op": "set", "var": "wits", "value": 2}]},
    {"id": "c_bg_courier", "label": "You ran the courier roads.",
     "target": "gate_approach",
     "effects": [{"op": "set", "var": "rope", "value": true},
                  {"op": "set", "var": "resolve", "value": 2}]}
  ]
}
```

### 5.3 The check: a resolver node with degree bands

Approach node (unconditional tactical choice, effects on the gamble line):

```json
{
  "id": "flood_gate",
  "body": "<<FILL role=rising words=85 beats='the flood gate mechanism, jammed and waiting; work it out, force it, or take the loud way'>>",
  "choices": [
    {"id": "c_fg_mechanism", "label": "Work the counterweight mechanism.",
     "target": "flood_gate_wits"},
    {"id": "c_fg_force",     "label": "Put your shoulder to the sluice bar.",
     "target": "flood_gate_might"},
    {"id": "c_fg_loud",      "label": "Break the inspection hatch and climb through.",
     "target": "gate_beyond_loud",
     "effects": [{"op": "set", "var": "marked", "value": true}]}
  ]
}
```

The wits resolver, four bands, mutually exclusive and jointly total over the
reachable range:

```json
{
  "id": "flood_gate_wits",
  "body": "<<FILL role=choice words=72 beats='hands on the counterweight, everything you know about machines against the jam; how it goes turns on what you carried up to this moment'>>",
  "choices": [
    {"id": "c_fgw_crit", "label": "You read the mechanism like a page; it opens without a sound, and you pocket the warden's dropped seal.",
     "target": "gate_beyond_clean",
     "condition": {">=": [{"var": "wits"}, 3]},
     "effects": [{"op": "set", "var": "rope", "value": true}]},
    {"id": "c_fgw_pass", "label": "Your training holds; the counterweight yields.",
     "target": "gate_beyond_clean",
     "condition": {"==": [{"var": "wits"}, 2]}},
    {"id": "c_fgw_dig",  "label": "You are out of your depth, but you refuse to be; you wrench it through on nerve alone.",
     "target": "gate_beyond_loud",
     "condition": {"and": [{"<=": [{"var": "wits"}, 1]},
                            {">=": [{"var": "resolve"}, 1]}]},
     "effects": [{"op": "dec", "var": "resolve", "value": 1},
                  {"op": "set", "var": "marked", "value": true}]},
    {"id": "c_fgw_fail", "label": "The counterweight slips; the alarm chain sings.",
     "target": "fgw_fail_c0",
     "condition": {"and": [{"<=": [{"var": "wits"}, 1]},
                            {"<=": [{"var": "resolve"}, 0]}]}}
  ]
}
```

`fgw_fail_c0` heads a short fail chain ending in a `setback` or, deeper in the
gauntlet, `death` (legal at 13-16, restart-on-fail per ADR-011).

### 5.4 Why the existing gate passes it unchanged

- **Schema (L1):** every construct above already exists; conditions use only
  whitelisted operators against declared variables; effects are type-correct;
  `inc`/`dec` deltas are non-negative; int literals are far under the 1e9 cap.
- **L2-9 (no stateful dead end):** the four bands partition every reachable
  `(wits, resolve)` combination: wits is in {1,2,3} by construction and the
  two low-wits bands split on `resolve >= 1` vs `<= 0`, which is total over
  ints. If an author writes a leaky partition, L2-9 fails the story at the
  gate instead of stranding a reader. The gate is the safety net for exactly
  this authoring mistake.
- **L2-11 (every band live):** the crit band requires `wits == 3`, reachable
  via archive background (`wits = 2`) plus the one training beat (`inc wits
  1`); the dig band requires low wits with resolve, reachable via forge
  background taking the mechanism line; and so on. If any band were
  unreachable, L2-11 fails the story. Fairness is machine-checked.
- **L2-10 (loop escape):** the gauntlet is forward-only here; no new risk.
- **Policy:** ending kinds, content ceilings, min-to-complete, words/node all
  unaffected; this layer adds routing, not content classes.

### 5.5 State-space arithmetic against the L2-12 cap

The walk cap is 100,000 configurations of `(node, var_state, once-set)`.
Worst-case config count is bounded by `nodes x product(range sizes) x
once-set combinations`. This sheet uses no `once` effects, so:

- Declared product: `might` 4 x `wits` 4 x `resolve` 3 x `rope` 2 x
  `marked` 2 = **192** combinations.
- 13-16 medium gamebook ceiling of 370 nodes: worst case 370 x 192 =
  71,040 < 100,000. **Under the cap even in the absolute worst case.**
- Reality is far below worst case, because of two design rules this layer
  imposes: **monotone stats** (stats only rise, `resolve` only falls, so
  ordered combinations dominate) and **phase locality** (a gauntlet node is
  reachable only with the combinations its path prefix can produce; the
  documented "Reachable {1,2,3}" style in the descriptions, copied from Iron
  Spire, is the authoring contract). Iron Spire's declared product is 32 over
  277 nodes and walks trivially; Tenfold Siege's is 32 over 677 nodes.

Budget rule of thumb for authors: **declared product <= cap /
max-cell-nodes.** For 13-16 medium gamebook that is 100,000 / 370, about 270;
for 16+ long gamebook (475-750 nodes) it is about 133, so the big cell gets a
smaller sheet (e.g. drop one bool, or use 0-2 stat ranges) or leans harder on
monotonicity. L2-13 (past 460 nodes the walk is the sole correctness
guarantee) is not a problem here; it is the argument FOR this design: the
walk, not hand review, is what proves a 600-node stat-gated gauntlet correct,
and this layer stays inside what the walk can exhaust.

## 6. What it buys, what it costs, where it is not worth it

### 6.1 Buys

- **Meaningful builds.** Today a gamebook path differs by route; with a
  sheet, it differs by *identity*: the archivist and the forge apprentice
  survive different checks, see different boons, and reach different wins.
  Direct fuel for the K3 axis and the flexibility plan's replay goals; the
  same tree replays differently per build, which is leaf-and-state diversity
  without new nodes.
- **Consequence with memory.** Spending `resolve` at the Flood Gate is felt
  at the summit. Tenfold Siege proves teens' skeletons can carry this; the
  layer makes it a repeatable grammar instead of a bespoke invention.
- **A teachable authoring idiom.** The fill pipeline and the `cyo-author`
  skill can be taught one pattern (background node, training beats, resolver
  bands, one pool) instead of re-deriving state semantics per skeleton, which
  should *reduce* per-skeleton authoring ambiguity for the teen cells.
- **Series progression for free.** The sheet is exactly the "declared state"
  ADR-011 section 8 already carries across books; a campaign where book two
  starts from your book-one build requires no new machinery.

### 6.2 Costs

- **Authoring burden is real.** Resolver bands must partition reachable
  ranges; training beats must make every band reachable; descriptions must
  document reachable sets. The gate catches mistakes, but each catch is a
  failed generation or a repair cycle (the shared `max_repairs=3` budget).
  Skeleton authoring for these cells gets harder before it gets easier.
- **State-space pressure is permanent.** The sheet must stay tiny (roughly
  <= 5 variables, ranges <= 0-3) forever; every future "just one more stat"
  fights the L2-12 cap. Section 5.5's budget rule needs to live in the
  authoring docs or it will be rediscovered by gate failures.
- **Fill-model complexity.** The prose fill must respect band labels that
  encode outcome fiction ("your reserve holds") without contradicting them.
  This is already true for Iron Spire, so it is an extension of an existing
  obligation, not a new class of risk, but more checks means more chances for
  fidelity-review friction.
- **Moderation surface, slightly.** Resource death ("your strength gives
  out") is a new *flavor* of the already-allowed lethal fail, not a new
  content class; content ceilings and kind/valence policy are untouched. The
  real watch item is that "builds" must never encode anything a safety
  reviewer would read as stats over real-child attributes; stats are
  in-fiction competencies only.

### 6.3 Where it is NOT worth it

- **Any band below 13-16.** Tier-2 loops only begin at 8-11 and the cognitive
  load of a sheet is wrong for the younger bands; their state belongs in
  single-purpose flags (the lantern, the mitten), as today.
- **Prose cells, including teen prose.** Prose cells sell narrative, not
  mastery; a visible mechanics layer would fight the register. At most, a
  single quiet flag or two, as now.
- **Short lengths and the MVP tier.** A build needs runway to pay off;
  min-to-complete 24+ is the floor where checks earn their nodes.
- **Full RPG simulation.** Combat rounds with enemy HP, action economy,
  inventories, currency, XP tables: each is either inexpressible without
  arithmetic in conditions or a state-space bomb, and none of it is what a
  reading app is for. The value is a *thin* layer: builds, checks, one pool,
  a few flags. If a future need seems to demand more than that, the correct
  response is to question the need, not to extend the DSL first.

## 7. Licensing analysis (gates everything; read before any adoption)

**Framing: nothing in this document's proposal copies Pathfinder text.** The
mechanics above are re-expressed from scratch in this project's own schema and
idiom. That matters because of a threshold point: under US copyright doctrine,
game *rules and mechanics as such* (systems, procedures, methods) are
generally not copyrightable; the protectable material is their *expression*
(rule text, stat blocks, names, lore, art). "Generally" is doing work in that
sentence; the mechanic/expression boundary is fact-specific and this is not
legal advice. But it frames the options: a license is needed when we *copy or
closely adapt Paizo's expression*, not when we build threshold checks and
resource pools that any gamebook since 1982 has used.

### 7.1 Which license covers what

| Corpus | License | Status |
| --- | --- | --- |
| Pathfinder 1e (and pre-Remaster 2e) rules content designated as Open Game Content | **Open Game License 1.0a** (Wizards of the Coast, 2000) | In force; see the deauthorization caveat below |
| Pathfinder 2e **Remaster** (Player Core, GM Core, Monster Core era, 2023+) licensed material | **ORC License** (2023, drafted by Azora Law with Paizo and other publishers) | Current; Paizo's going-forward license |
| Golarion setting, named characters/deities/iconics, proper nouns, art, trade dress | **Neither.** OGL "Product Identity" / ORC "Reserved Material" | Never usable without a separate deal |
| The word "Pathfinder", logos | Trademark | Not licensed by OGL or ORC; no use that implies compatibility or endorsement |
| Paizo Community Use Policy | Non-commercial fan license | **Not applicable**; this is a commercial product |

### 7.2 OGL 1.0a: what it permits and obliges

Permits: copying, modifying, and distributing material the publisher
designated as **Open Game Content** (for PF1e, broadly the mechanics text of
the core rules as published in the PRD), in a commercial work.

Obliges, for any shipped product containing OGC (all section numbers refer to
the OGL 1.0a text):

- **Include the complete license text** with every copy of the OGC
  distributed (Section 10). In an app, that means a licenses/notices surface,
  and arguably every generated story containing OGC is a distribution.
- **Maintain the Section 15 COPYRIGHT NOTICE chain**: reproduce the exact
  Section 15 entries of every upstream work drawn from (the WotC SRD entry,
  Paizo's PF1e entries, any intermediate third-party work) and add our own.
- **Clearly designate which portions of our work are OGC** (Section 8). For
  a generated-content app this is genuinely awkward: the OGC/non-OGC boundary
  would have to be drawn through generated story JSON.
- **Never use Product Identity** (Section 7) and **never indicate
  compatibility** with a trademark (no "Pathfinder-compatible") absent a
  separate license; Paizo's old PF1e compatibility license program is
  discontinued for practical purposes and was never a fit for this product.

Risk note, stated plainly without overclaiming: in January 2023 Wizards of
the Coast attempted to "deauthorize" OGL 1.0a for a successor license, then
retreated under community pressure and released the D&D 5.1 SRD under CC BY
4.0 instead. Whether OGL 1.0a is irrevocable was never adjudicated. The
practical industry read is that 1.0a survives, but a kids' product with a
compliance-heavy posture should prefer instruments without that cloud (ORC,
CC BY, or no license dependence at all).

### 7.3 ORC License: what it permits and obliges

The ORC License (Open RPG Creative) is the 2023 successor instrument Paizo
uses for the PF2e Remaster. As drafted it is perpetual and irrevocable by its
terms and separates:

- **Licensed Material**: the mechanical content (rules, procedures,
  processes, systems) the licensor releases; usable commercially, modifiable,
  redistributable.
- **Reserved Material**: lore, setting, characters, story, art, trade dress;
  the Product Identity analog; never licensed.

Obligations for a shipped product using ORC Licensed Material:

- **Include the ORC Notice** with the required attribution block,
  reproducing upstream attribution exactly as instructed by each upstream
  work (the ORC's analog of the Section 15 chain).
- **Sharealike on mechanics**: mechanical content derived from Licensed
  Material is itself licensed forward under ORC. For this app that would mean
  our check/sheet mechanics, *if derived from ORC material*, become ORC
  Licensed Material; our prose, setting, and product remain ours (they are
  expression/Reserved-analog, not mechanics).
- **No implied endorsement or compatibility claims**; trademarks stay out.

ORC is cleaner than OGL 1.0a for us on every axis: no deauthorization cloud,
a crisper mechanics/expression split, and a notice obligation that is easier
to satisfy in an app (one notices screen) than OGL's designate-the-OGC
requirement is against generated JSON.

### 7.4 CC-BY-4.0 alternatives (the licensing simplification): D&D SRD 5.1/5.2 and the Black Flag Reference Document

The OGL/ORC analysis above is the picture *if Pathfinder is the source corpus*.
It is not the only 5e-lineage option, and two alternatives collapse most of
section 7.2's compliance burden because they are available under **Creative
Commons Attribution 4.0 (CC-BY-4.0)**: a general-purpose, irrevocable,
attribution-only license with **no sharealike and no game-specific machinery**.

- **D&D System Reference Document 5.1 and 5.2.** Wizards of the Coast placed
  SRD 5.1 under CC-BY-4.0 in January 2023 and released SRD 5.2 (the 2024-rules
  SRD) under CC-BY-4.0 on 22 April 2025. A CC grant, once made, cannot be
  revoked; WotC has stated all future SRDs will be CC-BY-4.0 only. This is the
  same publisher whose 2023 OGL-deauthorization attempt created the cloud
  section 7.2 warns about, but that cloud is an OGL-1.0a problem: the CC-BY
  grant is a separate, one-way, irrevocable instrument and is not exposed to it.
- **Black Flag Reference Document (BFRD), Kobold Press.** The reference document
  behind *Tales of the Valiant*, **dual-licensed under BOTH the ORC License and
  CC-BY-4.0**. It is built on the CC-released 5e SRD and adds original mechanics
  (talents, lineages, and the *Luck* and *Doom* metacurrencies) plus GM
  material. Taking it under its CC-BY path gives the SRD's attribution-only
  simplicity while adding mechanics that fit the deterministic model unusually
  well (below).

Comparison for THIS product (a commercial, LLM-generated, children's reading
app), lightest to heaviest on licensing weight:

| Source corpus | License to use | Sharealike | Revocation cloud | Per-copy license text | Mark OGC in generated JSON | Attribution surface |
| --- | --- | --- | --- | --- | --- | --- |
| **D&D SRD 5.1 / 5.2** | CC-BY-4.0 | none | none (irrevocable grant) | not required | not required | one attribution string on a notices screen |
| **BFRD (CC-BY path)** | CC-BY-4.0 | none | none | not required | not required | one attribution string (+ the WotC SRD credit it inherits) |
| **BFRD (ORC path)** | ORC | mechanics sharealike | none | ORC Notice required | not required | ORC Notice block |
| **Pathfinder 2e Remaster** | ORC | mechanics sharealike | none | ORC Notice required | not required | ORC Notice block |
| **Pathfinder 1e** | OGL 1.0a | via the license | **yes (unadjudicated)** | **required each distribution** | **required, awkward vs per-story JSON** | Section 15 chain |

The decisive column is CC-BY-4.0 versus everything else. Under CC-BY-4.0 the
section 7.2 problems do not arise at all: no obligation to ship license text
with every copy, no Section 15 chain to maintain and extend, no requirement to
mark which spans of generated story JSON are open content, and no sharealike
forcing our derived mechanics open. The whole obligation reduces to a single
attribution string on a notices screen. For an app that ships thousands of
generated stories, that difference is the entire decision.

**A mechanical-fit bonus, not only a licensing one.** Two of the alternatives
are *better conceptual sources* for the dice-free design in sections 4-5,
independent of licensing:

- **5e's math is flatter than Pathfinder's.** PF2e adds character level to
  proficiency, so its checks scale with two large moving numbers; the section
  4.1 "your build is the roll" translation must discard that scaling to fit the
  no-arithmetic DSL and the 0-3 stat range. 5e's "ability modifier +
  proficiency vs DC" is already close to one small quantity against a threshold,
  so SRD 5.1/5.2 maps onto the resolver-band model with less distortion.
- **BFRD's Luck and Doom are already resource clocks.** *Luck* is a spendable
  metacurrency (the section 5 `resolve` salvage mechanic almost verbatim) and
  *Doom* is a rising countdown (a monotone drained pool with a fail route).
  Both are dice-free by nature: pools you spend and fill, not rolls. If any
  source system were designed for a deterministic gamebook, it is the one that
  already states its tension as spendable pools.

None of this changes the section 3-6 mapping, which is deliberately generic
(threshold checks, a small sheet, one pool, a spend-to-salvage token are
gamebook primitives older than any of these systems). It changes only *which
corpus we would cite and attribute if we ever ship actual text* (Option B), and
it makes the licensing cost of doing so far lower than the OGL/ORC analysis
above implied.

### 7.5 What we would actually take, under any option

Only generic, re-themed mechanics: threshold checks, degrees of success, a
small ability/skill sheet, resource pools, conditions-as-flags, backgrounds,
staged progression. **Never**: Golarion or any Paizo setting element, named
monsters/characters/deities, spell or feat *text*, stat blocks, art, or the
Pathfinder name anywhere user-facing or store-facing. Additionally, because
story prose is LLM-generated: **no Paizo text or Paizo-distinctive names may
ever enter a generation prompt** (fill, repair, covers). A "write this like
Pathfinder" prompt is both a quality and a licensing hazard; the mechanics
layer lives in our skeleton JSON, and prompts stay Paizo-free. This belongs in
the WS-2 theme-contract constraints if the proposal proceeds.

### 7.6 Recommendation (licensing)

- **Option A (still recommended for the section 5 proposal as written):
  inspiration-only, no license adoption.** Build the layer as original
  expression of unprotectable generic mechanics; adopt no license; carry no
  notice obligations; reference no source system in product, marketing, or
  prompts. The proposal copies no text, so it needs nothing more. Residual risk
  is the fact-specific mechanic/expression line, which is exactly what the legal
  review below is for. Which system inspired the grammar does not matter if we
  take none of its text.
- **Option B (only if we later ship actual reference text, e.g. condition
  definitions or a stat block as authoring reference): prefer CC-BY-4.0
  material, specifically D&D SRD 5.1/5.2 or the BFRD under its CC-BY path.**
  This supersedes the earlier "ORC-licensed PF2e Remaster only" fallback:
  CC-BY-4.0 is strictly lighter than ORC for this product (no sharealike on our
  derived mechanics, no ORC Notice, one attribution string) and dramatically
  lighter than OGL 1.0a. Do **not** adopt OGL 1.0a material at all (the
  deauthorization cloud plus the per-distribution license-text and
  OGC-designation obligations are a poor fit for generated JSON in a kids' app).
  Between the two CC-BY sources, prefer the **SRD** for the flattest mechanics
  and the largest, most-attributed ecosystem; consider the **BFRD** only when we
  specifically want Luck/Doom-style pools, and take it under **CC-BY, not ORC**,
  to avoid the sharealike.
- **Trademark hygiene, unchanged and applying to every option:** never use
  "Dungeons & Dragons", "D&D", "Pathfinder", "Tales of the Valiant", the
  BFRD/ORC/system logos, or any "compatible with" claim in product, store
  listings, or generation prompts. CC-BY licenses the *text*, never the marks;
  attribution is a plain-text credit, not a logo or a compatibility badge.
- **The prompt-hygiene rule from section 7.5 is more important here, not less:**
  even CC-BY text must never enter a generation prompt as "write this like
  <system>", both to keep distinctive expression out of generated output and to
  keep the attribution boundary clean. Mechanics live in skeleton JSON; prompts
  stay system-name-free.
- **In all cases: legal review remains a hard gate.** Before any code, catalog,
  or prompt work leaning on this document, counsel should confirm (1) the
  inspiration-only position and the mechanic/expression boundary for the
  specific sheet/check design (Option A), (2) the exact CC-BY-4.0 attribution
  string and where it must appear for an app that distributes generated
  derivatives (Option B), (3) trademark hygiene, and (4) any children's-category
  store-policy wrinkle for RPG-mechanic content (COPPA posture and store
  policies do not change the IP analysis, but counsel should confirm no
  wrinkle). CC-BY materially shrinks the compliance surface; it does not remove
  the need for the review.

## 8. Phased decision path

Deliberately gated so the owner can stop after any phase with value banked.

- **Phase 0: decide and de-risk (no build).** Owner reads this document;
  legal review of section 7 (Option A posture). Exit: go/no-go on Phase 1,
  and a recorded ADR-0xx ("deterministic check layer for teen gamebook
  cells") if go. Cost: small.
- **Phase 1: one pilot skeleton, zero code.** Hand-author (or `cyo-author`)
  one 13-16 medium gamebook skeleton using the section 5 grammar: 3 ints + 2
  bools, one background node, two training beats, 5-7 resolver checks, one
  pool. It must pass the existing gate untouched; the walk report and config
  count are the pilot's primary artifact. Exit criteria: gate passes with
  zero validator changes; config count comfortably under cap (< 25% of it);
  fill produces band-consistent prose without elevated repair burden.
- **Phase 2: make it a grammar.** Authoring doc for the idiom (budget rule,
  partition rule, reachable-set documentation convention); teach
  `generation/templates/fill.md` and the `cyo-author` skill the resolver-band
  idiom; add 2-3 more skeletons across 13-16 and 16+ gamebook cells;
  optionally an advisory validator lint (a WARNING that a resolver node's
  bands do not cover the declared range, cheaper to catch at L1 than as an
  L2-9). Exit: teen gamebook cells have build-bearing variety measurable by
  the WS-0 metrics (distinct outcomes per tree per family).
- **Phase 3: progression and surface.** Series carry (`carries_state`) so a
  two-book campaign keeps the sheet; optional reader-UI sheet display
  (frontend only; the state already exists in `ReadingState`). Exit: one
  two-book series passes the series meta-validator with stat carry.

**Decision criteria to pursue past Phase 1** (measure, do not vibe):

1. Engagement: replay rate and K18 ratings on the pilot vs matched
   non-sheeted gamebooks in the same cell.
2. Cost: authoring hours and repair-cycle count for the pilot vs a
   comparable existing skeleton (Iron Spire is the baseline).
3. Gate behavior: config counts, walk times, and any L2 findings across
   pilot iterations; if authors keep tripping L2-9/L2-11, the grammar is too
   sharp and needs the Phase 2 lint before more content.
4. Safety: zero new moderation findings attributable to the mechanics layer.

## 9. Honest bottom line

The surprising finding of this exploration is how little needs to be
imported: the Storybook Tier-2 model already contains a complete,
deterministic, gate-verified RPG substrate, and the best teen skeletons
already use fragments of it. The real contribution of any of these systems is
not rules text (we should take none, Option A) but a **coherent grammar** worth
borrowing at the level of ideas: degrees of success, builds that matter,
spendable resolve, one honest resource clock. That grammar fits inside the
existing schema, evaluator, player, walk cap, and band policy without touching
any of them, and the L2 gate turns out to be the fairness proof the dice-free
design needs. A late finding (section 7.4) reframes the sourcing: this grammar
is equally available from D&D SRD 5.1/5.2 and Kobold Press's Black Flag
Reference Document, both under CC-BY-4.0, which are materially simpler licenses
than Pathfinder's OGL 1.0a or ORC. If text is ever shipped (Option B), a CC-BY
source is preferred; and 5e's flatter math and the BFRD's spendable Luck/Doom
pools fit the deterministic model more naturally than Pathfinder's level-scaled
checks, so the alternatives win on both licensing and mechanical fit. The costs are concentrated in authoring discipline and a permanent
small-sheet constraint, and the value is concentrated in exactly two cells
(13-16 gamebook, 16+ gamebook). Recommended: pursue Phase 0 and the one-cell
Phase 1 pilot; do not extend below 13-16, into prose, or toward simulation.

---

*Exploratory / future improvement, not a committed build. Licensing analysis
herein is not legal advice; obtain legal review per section 7.6 before any
adoption.*
