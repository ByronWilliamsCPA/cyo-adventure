# CYO Adventure Skeleton Format Reference

Reference for the `<<FILL>>` directive grammar, per-band prose targets, and ending type
conventions used by the `cyo-author` skill.

---

## The `<<FILL>>` directive

A skeleton node's `body` field holds a single `<<FILL>>` directive in place of prose.
The grammar is:

```
<<FILL role=ROLE words=N beats='SHORT INTENT'>>
```

### Attributes

| Attribute | Required | Description |
|-----------|----------|-------------|
| `role` | Yes | The node's narrative role in the story graph. Common values: `setup`, `rising`, `choice`, `climax`, `completion`, `failure`; the vocabulary is currently unvalidated free-form (the catalog uses ~62 tokens) and only the four core values color diagrams. A closed set is proposed (2026-08-09 review, rule L1-9); prefer the common values above. Note `role` is NOT `ending.kind`: `failure` is a role, not a member of the `EndingKind` enum. |
| `words` | Yes | Approximate target word count for this node's prose. Match the band's words/node target (see table below). |
| `beats` | Yes | A short single-quoted phrase describing the narrative event that must occur in this node. The author fulfills the beat while setting up the choices listed on the node. |

### Authoring rule

Replace the entire `<<FILL ...>>` string (including the angle brackets) with finished prose.
No `<<FILL` markers may remain in the output JSON.

### `{SLOT}` tokens and theme contracts (ADR-019)

Parameterized skeletons carry `{SLOT_NAME}` tokens on exactly three surfaces: `beats=`
values, ending `title`s, and choice `label`s (`storybook/slotted_surfaces.py`). A `.contract.json`
sidecar declares the slot set, per-slot denylists, and a `default_binding`; production
binding substitutes request-derived values before fill (`generation/binding.py`,
`scripts/bind_theme.py`). A newly drafted production skeleton is expected to be
parameterized from day one (`scripts/parameterize_skeleton.py`, verified by
`scripts/check_theme_contract.py`); the `legacy_lexicon` rule intentionally rejects
re-binding the original theme's own nouns. Practical grammar note: the `beats='...'`
value is single-quoted and the parser does not escape quotes, so avoid apostrophes inside
beats.

---

## Per-band prose targets

Enforced source of truth: `validator/band_profile.py::words_per_node_profile` (PL-19 blocks a
node past the hard max) and per-skeleton `reading_level` metadata (`flesch_kincaid`, RL-13).
This table mirrors those values; a previous revision of this table carried stale ~2x-higher
Lexile-era numbers that would hard-fail the gate at 3-5 (2026-08-09 review, section 2.1).

Which ending kinds a band FORBIDS is not restated here. The source of record is
`validator/band_profile.py::_PROFILES` (`forbidden_ending_kinds`), enforced as PL-15 at
`Severity.ERROR`. A previous revision of this table's fail-state column said "NO
death/capture" only at 3-5 and 5-8 and gave 8-11 as "failure and entrapment allowed",
which reads as permitting death endings for eight-to-eleven-year-olds by omission; the
code forbids `death` at 8-11 too (`AL-493`, 2026-08-20). The tone column below is
drafting guidance only and carries no policy.

| Band / style | Words/node mean | Advisory range | Hard max | FK target | Tone guidance |
|--------------|-----------------|----------------|----------|-----------|---------------|
| 3-5 | 40 | 28-55 | 90 | 1.0 | Outcomes comic or always-recover |
| 5-8 | 70 | 50-95 | 155 | 2.5 | Try-again or comic outcomes |
| 8-11 | 100 | 70-135 | 220 | 4.5 | Adventure-forward; setbacks and entrapment |
| 10-13 | 100 | 70-135 | 220 | 5.5 | Horror variety and logical failure |
| 13-16 prose | 140 | 100-185 | 310 | 7.0 | Resource-based failure |
| 13-16 gamebook | 65 | 45-90 | 145 | 7.0 | Resource-based failure |
| 16+ prose | 175 | 125-230 | 385 | 8.0-9.0 | Resource-based failure, mature themes |
| 16+ gamebook | 80 | 55-110 | 175 | 8.0-9.0 | Resource-based failure, mature themes |

Do not hand-copy these numbers into a drafting brief: generate the full per-cell constraint
set with `uv run python scripts/generate_drafting_brief.py <band> <length> <style>`, which
reads the enforced sources live (hand-copied briefs drifted twice during the 2026-08-09
strict pilot, AL-149).

---

## The strict bar for newly drafted skeletons (ruled 2026-08-09)

A NEWLY DRAFTED skeleton must pass `uv run python scripts/check_skeleton.py <path> --strict
--headroom` (the grandfathered catalog is exempt until removed). Beyond the standard gate,
strict blocks on: any advisory from PL-19 (story mean), PL-23 (clock), PL-24 (ending mix),
PL-25 (first decision), PL-26 (corridor density), or L1-7 (below cell min); the CG-1..CG-3
choice grammar (`enforce_grammar=True`; options-per-decision bounds, single-choice run caps,
and words-per-stop ceilings where a single-choice chain composes into one stop WITH the node
it flows into); the band's random-walk satisfying-outcome floor; a per-band max in-degree cap
on `branch_and_bottleneck`/`gauntlet`/`sorting_hat`/`time_cave` (`open_map` and
`loop_and_grow` are exempt: hub re-entry is their design); and a depth-qualified endings
floor (an ending counts toward the breadth floor only at BFS depth >= a third of the cell's
arc floor). Two terms both read "satisfying" and differ: PL-20's arc floor counts
success/completion KINDS; the walk floor counts positive-or-neutral VALENCE. Before any
promotion PR, also run the catalog audits with the candidate placed in its target cell
(`check_incell_clones.py`, `check_outcome_spread.py`) and expect an adversarial content
review; a strict-clean draft is necessary, not sufficient (all three 2026-08-09 pilot drafts
passed strict and failed review). The authoritative constants live in
`scripts/check_skeleton.py` and `validator/band_profile.py`; the brief generator above emits
them per cell.

---

## Ending types

An ending is typed on two required axes (the `Ending` model is `extra="forbid"`,
so no other fields, and there is no `ending.type`):

`ending.kind` (what mechanically happened, a closed set, `EndingKind`):

| Value | When to use |
|-------|-------------|
| `completion` | A successful ending that advances the series arc (the reader "wins" and the story world moves forward). |
| `success` | A satisfying win that does not advance the series arc. |
| `discovery` | The reader uncovers or learns something; outcome-neutral rather than a clear win or loss. |
| `setback` | A non-lethal bad outcome: the protagonist fails, retreats, or is otherwise set back, but survives. Allowed at 8-11 and above. |
| `capture` | A non-lethal entrapment outcome (caught, held, trapped). Allowed at 8-11 and above. |
| `death` | A lethal outcome. **Allowed only where the band's fail-state policy permits it**, which is `validator/band_profile.py::_PROFILES` (`forbidden_ending_kinds`) and not this table: as of 2026-08-20 it is forbidden at 3-5, 5-8 AND 8-11. Read the source, not a restatement (`AL-493`). |

`ending.valence` (how it feels, independent of what happened, `Valence`):
`positive`, `neutral`, or `negative`.

Every ending also carries `ending.id` and `ending.title` (both non-empty
strings). The pre-schema single free-string `type` maps onto the two axes:
old `good` -> `kind: success` / `valence: positive`; old `neutral` ->
`kind: discovery` (or `setback`) / `valence: neutral`; old `failure` ->
`kind: setback` or `capture` / `valence: negative`.

## Character envelope (`accepts_character`)

A skeleton opts into the persistent reader character (ADR-028) by declaring an
`accepts_character` field on the story. Absence means the book accepts no character at all;
this is enforced, not assumed (`CH-6` reserves the four canonical variable names below so an
opted-out book cannot be seeded by an accidental name collision). The envelope is a mapping
from canonical variable name to the inclusive range the book proves itself safe across:

```json
"accepts_character": {
  "might": { "min": 0, "max": 2 },
  "wits":  { "min": 0, "max": 2 },
  "nerve": { "min": 0, "max": 2 }
}
```

Declare an envelope only when the skeleton actually wants a returning reader's character
seeded into it. Once declared, every name in the envelope must also be declared in
`variables` with the identical `min`/`max` (`CH-2` requires equality, not containment, because
the runtime clamp is to the *declared* bounds; a narrower envelope would let the runtime
silently admit a state the validator never walked). Never widen or narrow the envelope
relative to the variable's declared bounds, and never add a canonical name to `variables`
without also covering it in the envelope (`CH-6`'s opt-in half rejects that combination).
`CH-1` does not: it only ever walks envelope -> variable, proving each envelope name is
declared, so a canonical variable the envelope omits is invisible to it. `CH-6` is the only
rule covering that direction (`validator/character.py::_check_ch6_uncovered_canonical_names`).

### Canonical vocabulary

| Name | Type | Range | Declared by | Meaning |
|---|---|---|---|---|
| `archetype` | int | 0-6 | prose cells | `0` means not yet chosen; `1`-`6` are the six archetypes in roster order (`scout`, `guardian`, `trickster`, `scholar`, `healer`, `wildheart`). Gates flavour and prose colour only, never a difficulty check. |
| `might` | int | 0-2 | gamebook cells | Trained force |
| `wits` | int | 0-2 | gamebook cells | Trained cleverness |
| `nerve` | int | 0-2 | gamebook cells | Trained composure |

### Why `archetype` and the stats never appear in the same envelope

This is not an arbitrary style rule, and it is not a hard prohibition enforced by a single
CH-* check either: an author who declares both would most often hit `CH-5`'s 64-state envelope
cap before anything else, since `archetype`'s 7 states crossed with all three stats' 27 states
is 189, well over the limit. The real reason is architectural, from ADR-028 decision 2: in a
mechanics-driven gamebook, **the stat spread already is the archetype** (a Scout is `wits 2 /
nerve 1 / might 0`). Declaring a separate `archetype` variable there would carry redundant
identity information with no mechanism keeping it in sync with the stats. `archetype` earns
its keep only in prose cells, which have no stats to infer identity from in the first place.
So a gamebook skeleton declares `might`/`wits`/`nerve`; a prose skeleton declares `archetype`;
no skeleton declares both.

### The archetype build node

A first-time reader has no character yet, so a participating prose skeleton declares
`archetype: 0` as its own initial value ("not yet chosen") and keeps an in-story **build
node** that sets `archetype` to 1-6 along different paths. This is what lets a returning
reader (seeded with `archetype` already 1-6) and a first-time reader (seeded with `archetype
== 0`) share the same graph.

The build node's own choices must be gated on `archetype == 0`. A **gate node** precedes it
and routes a returning reader (`archetype != 0`) past it. A skeleton that always routes
through the build node is non-conforming: a returning reader would land on a page where every
choice reads as already-resolved and is hidden, which is a runtime break (a zero-choice page),
not merely a validator artifact, and it also raises `L2-9`/`L2-10` at the gate. Never author a
build node without a preceding bypass.

### What CH-8 requires

Declaring `archetype` in the envelope commits the skeleton to hosting that build node (an
`archetype`-gated skeleton with no build node leaves the variable permanently 0, which makes
every archetype-gated flavour branch unreachable and fails `L2-11` before any CH-* rule even
runs). Because the build node sets `archetype` to one of six real values along different
paths, every downstream node forks six ways, multiplying the baseline walk instead of leaving
it constant. `CH-8` pre-flights this cost: a skeleton whose own base closure (its
declared-initials configuration count) exceeds 16,666 configurations (`100_000 // 6`, the
walk cap divided by the six-way branching factor) cannot host the idiom and fails with a named
cause instead of an opaque `L2-12` cap error. Keep a build-node skeleton's non-character graph
small; `CH-8` fires on any skeleton whose envelope declares `archetype` at all, even a
carrier-only later series book that never itself sets the variable, so this is a pre-flight
gate on the declaration, not proof that a given skeleton's own graph actually contains the
node.

### The stat-gate wall: never gate a choice directly on a stat threshold

**Read this before drafting a single node of a `might`/`wits`/`nerve` skeleton.** It is the first
blocking error a stat-envelope author hits, it fires on the most natural thing you would write, and
nothing in the gate output points at the envelope as the cause.

A stat is seeded and never set in-book (that immutability is exactly what keeps the 27-state walk
cheap). So a choice conditioned directly on a stat threshold, `might >= 2`, is **unconditionally
unreachable in the skeleton's own baseline configuration** whenever the skeleton's declared initial
sits on the other side of the threshold, and `L2-11` errors it out as a dead branch before any CH-*
rule runs. `validator/layer2.py::_check_dead_branches` walks only the single declared-initial
baseline with **zero `accepts_character` awareness**, so it cannot see that the envelope proves the
branch reachable at other entry states. `CH-3a`'s union-quantified walk does not rescue you either:
`L2-11` is raised on the baseline walk independently, before the union is taken.

The archetype build node above is *not* the fix here. That idiom works because `archetype` is set
in-story; a stat book deliberately has no mutating node, and adding one would forfeit the cost
property that makes the envelope affordable.

The working authoring-only pattern is a **`resolve` pairing**:

1. Add an ordinary, non-canonical boolean variable (`resolve` or similar). It is not in the envelope
   and not in the canonical vocabulary, so `CH-6` is untroubled.
2. Immediately before the gate, put an unconditioned binary player choice that sets `resolve` either
   way. Both settings must be reachable by ordinary play.
3. XOR-combine `resolve` with the stat threshold on the gated choice, rather than testing the stat
   alone.

At the fixed baseline value of the stat, the pair collapses to depend only on `resolve`, so both
branches are reachable through ordinary play and `L2-11` is satisfied. At other envelope states the
condition still genuinely differentiates on the stat, which is what `CH-3a`, `CH-3b`, and `CH-4`
need. Measured cost: zero added configurations per walk.

**Know what you are buying.** This is a workaround, not a mechanism, and the limitation it leaves
behind is real rather than cosmetic. Because the gate must be preceded by a free player choice that
can flip the outcome, **the reader cannot perceive their stat deciding anything**. The stat stops
being a character trait the reader feels and becomes a hidden modifier behind a coin flip they just
made themselves. A whole book built this way reads as scaffolding: every station is mechanically
identical and no choice visibly turns on who the character is. A 13-16 pilot was drafted on exactly
this pattern in 2026-08 and withdrawn for that reason. Use the pattern for a small number of
genuinely stat-flavoured moments; do not plan a book whose spine depends on it. Whether
`_check_dead_branches` should become envelope-aware, which would remove the need for the workaround
entirely, is an open validator question tracked as `UW-C64` in
`docs/planning/unscheduled-work-register.md`.

### What the envelope costs at gate time

`CH-3a`, `CH-3b`, and `CH-4` each re-walk Layer 2 once per distinct entry state the envelope
admits (plus once more for the skeleton's own declared initial), because those rules prove a
property across every state a seeded reader can actually arrive in, not just the skeleton's
default state. Cost therefore scales with how many states the envelope admits: an
`archetype`-only envelope is 7 states; the canonical three-stat envelope above is 3 x 3 x 3 =
27 states. On the largest catalog skeleton at the time this was measured
(`skeletons/16+/the-longwinter-station.json`, 248 nodes, 51,241 base configurations), the gate
took 0.77s with no envelope declared and 49.58s with the canonical 27-state envelope, a
roughly 64x multiplier (recorded in `docs/planning/unscheduled-work-register.md` rows UW-A47
and UW-A48). This cost is per gate run, not per read, and it does not by itself make a
skeleton invalid: `CH-5`'s 64-state cap is the hard ceiling, and a skeleton under that cap is
still admissible however slow it is to gate. But it is a real, mechanism-driven cost, not a
fixed constant, so a narrower envelope (fewer canonical names, narrower ranges) keeps a
character-enabled skeleton's gate runs fast in the same way a narrower state space keeps any
Tier-2 skeleton's gate runs fast.

#### Pre-flight arithmetic: do this before drafting prose

The mechanism above gives you a number you can compute from the skeleton's shape alone, in the same
spirit as `CH-8`'s check. The unit of cost is the **config-walk**:

```text
envelope config-walks = base configurations x envelope states
envelope gate seconds ~= envelope config-walks x 3.5e-5
whole-gate seconds    ~= envelope gate seconds + the skeleton's own no-envelope gate time
```

Count **envelope states only**, not envelope states plus one. The skeleton's own declared-initial
walk happens whether or not an envelope is declared, so it belongs in the second term of the third
line, not inside the multiplier. Folding it in double-counts a walk you were already paying for and
puts the arithmetic out of step with the measurement below.

`3.5e-5` seconds per config-walk is the measured constant on the large graphs where this actually
bites: `the-longwinter-station`'s 51,241 base configurations across the 27-state stat envelope is
51,241 x 27 = 1,383,507 config-walks, and the envelope's share of the gate run is 48.8s of the
49.58s total (the remaining 0.77s is that baseline walk). 1,383,507 x 3.5e-5 = 48.4s, which is the
measurement the constant is fitted to. It holds across measurements spanning three orders of
magnitude, from a few hundred config-walks to 1.38M. Small graphs come in under it because fixed
overhead dominates and there are fewer nodes to revisit per walk, so treating `3.5e-5` as flat is
**conservative**: the estimate is an upper bound for a small skeleton, and accurate for a large one.

#### There is no gate-run time budget, so this is a reference point, not a limit

**No per-run gate budget has been set for this project.** Nothing in the roadmap, CI config, or any
ADR states a wall-clock ceiling a `run_gate` call must come in under, and an earlier revision of
this section asserted one ("roughly 12s") that never existed. Do not reintroduce a budget number
without a source.

What does exist is a measurement, and it is the only honest anchor: `run_gate` on
`skeletons/16+/the-longwinter-station.json` (248 nodes, 51,241 base configurations) takes **0.77s
with no envelope and 49.58s with the canonical 27-state `might`/`wits`/`nerve` envelope**, recorded
in `docs/planning/unscheduled-work-register.md` rows `UW-A47` and `UW-A48`. That is the slowest gate
run anyone has measured on this catalog. Compare your own skeleton against it:

| Envelope | States | Base configurations that reach the measured anchor | Estimated gate seconds at the 100,000-configuration walk cap |
|---|---|---|---|
| `archetype` only | 7 | ~198,000, above the walk cap, so unreachable | ~25s |
| One stat, 0-2 | 3 | ~461,000, above the walk cap, so unreachable | ~11s |
| Two stats, 0-2 | 9 | ~154,000, above the walk cap, so unreachable | ~32s |
| Canonical three stats, 0-2 | 27 | 51,241, which is the measurement itself | ~95s |

Read the table this way. Column 3 divides the measured 1,383,507 config-walks by the envelope's
state count, so it answers "how big would my skeleton have to be to hurt as much as the worst one
we have measured?". For every envelope except the canonical three-stat one the answer is "bigger
than the 100,000-configuration walk cap allows", which is why the three-stat envelope is the only
shape that has produced a slow gate run in practice. Column 4 runs the arithmetic the other way, at
the largest skeleton the walk cap admits, and shows the canonical envelope can reach roughly twice
the measured worst case while still being perfectly admissible.

Two things to note before you use either column. This is **latency**, not admissibility: `CH-5`'s
64-state cap and the 100,000-configuration walk cap are the hard limits, and a slow skeleton under
both still gates and still publishes. And it interacts with `CH-8`: an `archetype` envelope also
multiplies base configurations six ways at the build node, so run `CH-8`'s 16,666 check first and
this arithmetic against the post-build-node count.

## Series continuations: carried variables (Tier-2)

When a book is book 2+ of a `carries_state=true` series, any variable acquired in
an earlier book **initializes true in this book**, carried in from the sibling's
final state. This inverts acquisition branches: a branch that in book 1 gated on
"you do not have it yet" (`has_lantern == false`) is now unsatisfiable in book 2,
because `has_lantern` starts true. An unsatisfiable conditional branch is a hard
`L2-11` dead-branch error at the gate.

Do not copy book 1's acquisition branches into a continuation. Redesign them:

- Flip the condition into an always-satisfiable **carried-state gate** that reads
  the variable as already held (`has_lantern == true`), e.g. "you still have the
  lantern from before, so ...".
- Drop the now-redundant `set` effects that acquired the variable (it is already
  set on entry).

Only the acquisition branch of a carried variable needs this treatment; branches
that consume or check an already-held variable are unaffected. A quick check: any
condition of the form `<carried_var> == false` in a continuation book is almost
certainly a dead branch and must be redesigned, not copied.
