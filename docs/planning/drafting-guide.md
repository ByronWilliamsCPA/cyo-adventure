---
title: "Story Drafting Guide"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Practical guide for authoring and generating branching stories that conform to the Storybook format and pass the validation gate."
tags:
  - planning
  - architecture
component: Development-Tools
source: "docs/planning/tech-spec.md sections Authoring Pipeline, Validation Gate, Story DSL; docs/planning/PROJECT-PLAN.md Phase 0 item P0-11"
---

# Story Drafting Guide

> **Status**: Active | **Version**: 0.3 | **Updated**: 2026-11-20

## Purpose

This is the human-maintained planning copy of the drafting guide. The copy the generation
prompts actually render as `{drafting_guide}` (structure, prose, and fill) is
`src/cyo_adventure/generation/templates/drafting_guide.md`. The two have diverged in places (this
copy carries the measured words-per-sentence table; the prompt copy carries the FK targets the gate
grades against), but the **Reader Agency** and **Voice, Tense, and Perspective** sections are kept
word for word identical in both; change them together. It is the practical handbook for a human
author writing stories by hand. Every section maps to a constraint that the validation
gate enforces, so following this guide is the fastest path to a story that passes on the
first attempt.

---

## Reader Agency

A choose-your-own-adventure works only while the reader believes their choices matter. An
editorial read of 31 catalog books (2026-11-20) found books that stop behaving like gamebooks by
the middle while passing every validator rule. These rules apply at every band and stage;
`scripts/check_prose_craft.py` reports each one (definitions in `validator/agency.py`).

- **Merge passages open in the scene** and state only what every inbound route established (not
  where a companion or prop is, not a fact only some routes earned). Never "Whichever way Mira had
  come, every path had led her here"; a route-specific beat belongs in the node before the merge.
- **No option recap.** A decision node ends on the stakes, not "She could X. Or she could Y."
  (At 3-5 and 5-8, one read-aloud question inviting the choice is allowed.)
- **Labels are concrete actions in the book's person**: never a mental act ("Sit with what this
  means"), never graph vocabulary ("hub"), never "you" over third-person prose.
- **Setbacks give something back** (a true glimpse of the mystery, a laugh, what the hero lacked)
  and close on it, never on giving up, going home, or "maybe next time".
- **People talk**, in quotation marks and their own voice, and the hero answers.

**Plants and payoffs** (structure work: skeleton authoring and book revision; a fill writes prose
for the ones the skeleton already declares and never adds or changes them). A book with merge nodes
and no state erases every route at every merge. The fix needs no engine change: declare two to four
`bool` variables, plant one with `effects` on an early choice, and pay it off with a `condition` on
a later choice that both planted and unplanted readers reach. Make the plant a trade-off, not a
free upgrade. Three shapes have worked in the catalog: the **same label, opposite conditions** pair
(one button every reader sees, gated `true` and `false` on the flag, leading to different nodes:
"Run to the bosun." in `the-sky-ship-stowaway`); the **swap pair**, two differently labelled
choices on opposite conditions so each reader sees exactly one of them (the chalk arrows in
`the-midnight-museum`); and the **unlocked option**, one conditional choice beside unconditional
ones. Every node with conditional choices keeps at least one unconditional choice, and a node
holding a payoff choice reads true in both states. The full revision recipe is
`.claude/skills/cyo-author/reference/story-agency-revision.md`.

---

## Node and Depth Budgets

Node count and branch depth are enforced by the Layer-1 graph validator. The old fixed
per-band node-count ranges (for example "8-11 -> 15-30 nodes") are superseded by ADR-011's
story-scale framework: budgets are now a `band x length x style` matrix where length
(short / medium / long) is the primary driver and cells are total-words-driven. Do not
hardcode a node range from memory; the authoritative source is the per-cell envelope in
`validator/band_profile.py`, single-sourced there and described in
[ADR-011](./adr/adr-011-story-scale-framework.md).

- **Bands**: the six supported bands are "3-5", "5-8", "8-11", "10-13", "13-16", "16+".
- **Length x style**: each band crosses `length` (short / medium / long) and `style`
  (prose / gamebook); the resulting cell sets the node-count envelope and depth ceiling.
- **MVP / Test tier**: there is a non-production MVP/Test tier (`production_eligible =
  false`) with compact envelopes for pipeline testing; do not ship its output to readers.

"Node count" is the total number of `Node` records in the story, including all endings.
"Branch depth" is the longest path from `start_node` to any ending node, measured in
hops.

The validator fails stories that exceed the cell's upper bound. Stories below the lower
bound trigger a warning (not a hard failure), but very short stories rarely satisfy the
`ending_count` minimum of two distinct endings.

**Configuration cap**: for Tier-2 stories, keep the reachable state space below 100,000
configurations. A configuration is a `(node_id, var_state)` pair. To stay safely within
the cap with a 50-node story: use at most 2 boolean variables plus one integer variable
with a range of 0 to 5 (2 x 2 x 6 = 24 variable-state combinations; 50 x 24 = 1,200
reachable configurations, well within the cap). Add variables only when the story
requires them for gating; each new variable multiplies the configuration space.

---

## Branch-and-Bottleneck Structure

The recommended structure pattern for all age bands is `branch_and_bottleneck`. In this
pattern, the story fans out from choice points into distinct branches, then converges back
at bottleneck nodes before fanning out again. This keeps the story manageable for the LLM
and keeps the validator's reachability check tractable.

A bottleneck is a **merge node**: one `body` that every converging branch arrives at. Write it to
be true on every inbound route and to open in the scene, never by telling the reader that their
route did not matter; see Reader Agency above. Plants and payoffs (Tier-2 variables) are what let
an earlier branch still count after the merge.

```text
start
  |
  +-- branch A ----+
  |                 +--> bottleneck 1 --> ...
  +-- branch B ----+
```

**Why bottlenecks matter**: without them, the story becomes a full binary tree that doubles
in nodes at every level. A 6-level tree has 63 nodes; a 10-level tree has 1,023. Bottlenecks
let you write distinctive experiences on each branch while keeping total node count inside
the budget.

Other supported structure patterns (for the concept brief `structure_pattern` field,
`generation/concept.py::StructurePattern`):

- `time_cave`: branches fan out to many distinct endings with little or no reconvergence;
  the oldest and simplest branching shape. Good when you want lots of divergent outcomes.
- `gauntlet`: a mostly linear sequence with a few decision points; suitable for the 8-11
  band where too many choices are overwhelming.
- `loop_and_grow`: the reader may revisit nodes. **The band decides what the loop means, and
  this is the one place the topology's name misleads.** At 8-11 and up it is a growth loop,
  Tier 2, with variables tracking progress across passes. At **3-5 and 5-8 it is a try-again
  loop and nothing accumulates**: the Tier-1 contract forbids variables, so nothing can
  distinguish a reader on their first pass from one on their third. Every hub and every
  ending must read correctly for a reader who took the loop once, twice, or not at all.
  Nothing may be counted ("three rescues"), collected ("the acorn in her pocket"), or
  referred back to as already-met ("her moonbeam"). Three of the six committed
  `loop_and_grow` books broke this, which is what the ADR-011 amendment of 2026-08-15
  responds to. If the story needs accumulation, it needs 8-11 or above. The loop-escape
  check requires that every cycle has an exit path to an ending at every band.
- `quest`: a multi-stage journey where each stage has its own branch-and-bottleneck shape.
  A distinct, requestable pattern; it is not folded into `branch_and_bottleneck`.

`open_map` and `sorting_hat` are `topology` values the validator can classify a finished
graph as (see [story-skeletons.md](../architecture/story-skeletons.md)), but they are not
currently requestable via the concept brief's `structure_pattern` intake field. Do not
conflate the two enums: `structure_pattern` is the author's requested shape at intake time;
`topology` is the validator's post-hoc classification of the shape the graph actually has,
and the two can diverge.

Avoid fully symmetric trees (binary trees where every non-ending node has exactly two
choices): they produce the node-count explosion described above and do not generate well
because the LLM runs out of distinctive beats.

---

## Voice, Tense, and Perspective

**The skeleton's declared person governs.** Every skeleton declares `metadata.narrative_person`
(`"second"` addresses the reader as "you"; `"third"` follows a named protagonist), and a fill
writes every passage in that person, without drifting between the two. When the field is absent,
follow the person the `beats=` directives use. This is the `UW-C328` ruling of 2026-08-21: the
field was backfilled across all 84 skeletons (most of them third person), and
`scripts/check_prose_craft.py` holds each book to the person it declares. A fill never changes a
skeleton's person, in either direction.

Decision D14 (design review section 8, 2026-08-01) makes **second person, present tense** the
standard for newly authored skeletons; a gamebook (`narrative_style: gamebook`) is always second
person, and the schema rejects a third-person gamebook. D14 governs what a new skeleton declares;
it does not license a fill to override a skeleton that declares third person.

> You push open the heavy door. The corridor stretches ahead, lit by a single lantern
> hanging from the ceiling. To your left, a narrow staircase leads upward. To your right,
> water drips from a stone alcove.

Rules, all bands:

- **Second person**: address the reader as "you", never "the protagonist" or a character name,
  in present tense throughout, including memories ("you remember the day you first...").
- **Third person**: follow the named protagonist in one tense for the whole book (past or
  present; the prose-craft check fails a book told in both). "You" appears only inside dialogue.
- Choice labels use the imperative or a description of the action ("Open the door" or
  "Go left toward the staircase"), not a question. In a third-person book a label is a neutral
  imperative with no "you" or "your" ("Steady the lantern", not "Steady yourself").
- Endings state what happens, do not ask what the reader wants to do next. Ending nodes
  have `is_ending: true` and zero choices.

**At 3-5**, the prose is read aloud by an adult, not decoded silently by the child. A new 3-5
skeleton should declare second person so "you" addresses the child directly (design review sections
2.2 and 2.6); an existing third-person 3-5 skeleton is still filled in third person.

---

## Age-Band Reading Levels

The `reading_level_target` field in the concept brief sets the Flesch-Kincaid grade target.
The validator checks against this target with the `tolerance` defined in the story metadata
(advisory warning only; the parent makes the final call).

The `words/sentence` and `syllables/word` columns are **measured**, not aspirational: they are the
mean and interquartile range over every committed node that actually lands inside its band under
the corrected syllable counter (`AL-399`), 4,173 nodes across 31 books. Write to those numbers and
the grade follows. The reference book is the highest in-band book in that band; opening it and
matching its sentence shape is the fastest route to band, and is what four independent drafting
agents each discovered for themselves before it was written down (`AL-392`).

| Age band | FK target | words/sentence | syllables/word | Reference book | Guidance |
|----------|-----------|----------------|----------------|----------------|----------|
| 3-5 | 0.0 to 1.5 | **5.7** (5.0-6.3) | 1.21 | `the-clover-and-the-butterfly` | Read-aloud cadence, repetition, concrete nouns. Minimal abstraction. |
| 5-8 | 1.5 to 3.0 | **7.8** (6.9-8.7) | 1.27 | `the-snow-day-expedition` | Simple vocabulary with gentle stretch words explained in context. |
| 8-11 | 3.0 to 4.5 | **12.7** (11.0-14.4) | 1.29 | `the-sky-ship-stowaway` | One idea per sentence. Concrete imagery. |
| 10-13 | 5.0 to 7.0 | **14.1** (12.7-15.4) | 1.30 | `the-midnight-museum` | Unfamiliar words are fine where context carries them. |
| 13-16 | 7.0 to 9.5 | **18.4** (16.6-20.2) | 1.30 | `the-sunspire-ascent` | Figurative language, irony, and ambiguous outcomes are age-appropriate. |
| 16+ | 9.5 to 12.0 | **21.0** (19.3-23.2) | 1.37 | `the-drowned-court` | Adult-YA register. Complex syntax and layered themes are acceptable. |

**Sentence length carries the band; vocabulary barely moves.** Across the whole range, mean
words-per-sentence goes 5.7 to 21.0 while mean syllables-per-word goes only 1.21 to 1.37. Put
those through the formula and sentence length accounts for about three quarters of the grade
spread from 3-5 to 16+. A 3-5 book and a 16+ book are built from words of nearly the same
difficulty; what separates them is how many of those words are asked to arrive at once. So when a
node scores high, split its sentences first and reach for shorter words second.

**Dialogue lowers the measured grade.** Flesch-Kincaid counts every short spoken line as a
sentence, so a scene of quick exchanges can score under the band floor (RL-13) even when the prose
suits the age: the first dialogue draft of `the-hollow-lighthouse` put 43 of 161 nodes out of band
this way. Keep the speech and join a speaker's short lines into one fuller sentence ("Wait, the
lamp should be green, not white," Ada said, already climbing.) rather than stacking "Wait." "Look."
"Green." At 10-13 that means roughly 13 to 16 words per sentence across a passage that carries
dialogue.

**Draft, then measure, then repair.** Prose written to a stated FK target lands out of band
essentially every time: all eight books drafted on 2026-08-14 did, one at 57 of 57 nodes with
individual grades of 7 to 12 against a target of 2.5, and all eight reached `in_band` 1.00 only
after a measured repair pass. Treat that pass as part of drafting rather than as a failure. Score
with the checker's own function, never by eye:

```python
from cyo_adventure.validator.reading_level import score_body

grade = score_body(node_body)  # None for <20 words or an unfilled <<FILL>> directive
```

**Do not chase irregular past-tense verbs.** Earlier guidance to prefer `went` over `walked` was
an artefact of a counting bug, not a craft truth: the old counter scored every regular `-ed` past
one syllable too high, so the swap looked like it bought something. Measured over ten
regular/irregular pairs, it saved 10 syllables under the broken counter and 1 under the corrected
one (`AL-399`). Choose the verb that says what happened.

> **The targets themselves are under review.** The per-book `metadata.reading_level.target` values
> were set while the counter was biased about a quarter of a grade high, so the corrected counter
> reads the whole committed corpus roughly 0.27 grades lower than it used to. The targets have
> deliberately not been shifted to compensate, since that would bake the bug into the spec, but
> until they are re-derived (`UW-C259`, `AL-400`) a 3-5 or 5-8 in-band figure is provisional, and
> the generation repair loop may push young-band prose slightly harder than the prose already
> approved.

Node body length scales with the band and with the ADR-011 length / style cell. The
authoritative per-node envelope is the `_WORDS_PER_NODE` table in
`validator/band_profile.py`; do not hardcode from memory. As a story-mean advisory band
per that table, aim for roughly 28-55 words per node at 3-5, 50-95 at 5-8, 70-135 at both
8-11 and 10-13, 100-185 at 13-16, and 125-230 at 16+ (prose; gamebook nodes run shorter).
Each cell also sets a hard per-node maximum well above these advisory bands. Longer bodies
push the FK grade up and slow the reading experience; shorter bodies leave the story
feeling sparse.

---

## Tier-2 Variables and Conditions

The schema does not gate Tier-2 by age band: `metadata.tier` is any of 1 or 2, and the
only hard rule is that a Tier-1 story must not declare variables (`tier 1 stories must not
declare variables`). As an authoring guideline, reserve state-tracking (Tier-2) for the
bands where a reader can follow persistent state: the 8-11, 10-13, 13-16, and 16+ bands.
Keep the youngest bands (3-5 and 5-8) at Tier-1. Use variables sparingly at any band;
every variable multiplies the state space (see the configuration cap below).

**Variable rules**:

- Declare all variables in the `variables` block at the top of the story. Every variable
  must have a `name` (snake_case), a `type` (`bool` or `int`), an `initial` value, and a
  `description`.
- For `int` variables, always set `min` and `max`. The validator rejects any story where
  a reachable transition could push the variable past its bounds.
- Use booleans for flags ("has_lantern", "met_the_elder"). Use small integers for
  counters that matter ("courage", "supplies", "keys_found") with a range of 0 to 5 or
  0 to 3.
- v1 supports only `bool` and `int` variables. String and enum state are out of scope
  for v1; model categorical choices as a set of boolean flags instead.

**Condition rules** (the JSONLogic shape, restricted to 10 operators):

```json
// "you have the lantern"
{ "==": [ { "var": "has_lantern" }, true ] }

// "courage is at least 3 and you do not have the curse"
{ "and": [
  { ">=": [ { "var": "courage" }, 3 ] },
  { "!": { "var": "has_curse" } }
] }
```

Permitted operators: `var`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `and`, `or`, `!`.

Excluded (the validator rejects these): arithmetic (`+`, `-`, `*`, `/`, `%`), `in`,
string operators (`cat`, `substr`), array reductions, and `if`/ternary.

A choice whose condition is `false` is hidden from the reader entirely, not shown as
greyed out. Do not write conditions that you expect to be false for most readers;
a conditional choice that no reachable configuration can expose is flagged as a dead
branch by the Layer-2 validator.

**Effect rules**:

- Effects use `op: "set"`, `op: "inc"`, or `op: "dec"`.
- Place effects on choices (when a choice is made) or on node `on_enter` (when a node
  is entered). Use `on_enter` for "you arrive and find something"; use choice effects for
  "you take the action and gain something."
- Use `once: true` on `on_enter` effects that should apply only on the first visit:
  "you find the lantern" should not re-grant the lantern on every re-entry to the cellar
  node.
- Do not stack many effects on a single node or choice; the state explosion makes the
  story harder to repair.

---

## Endings

Every story must have at least two distinct endings. The validator counts endings as nodes
with `is_ending: true` and checks that `ending_count` in the metadata matches the actual
count of ending nodes.

Each ending node requires an `ending` block:

```json
{
  "id": "ending_sunrise",
  "valence": "positive",
  "kind": "success",
  "title": "The sunrise ending"
}
```

The `id` is stable across prose edits and is the anchor for the ending tracker (Phase 4b).
Use a slug that describes the outcome, not a number ("ending_escape", "ending_captured",
"ending_befriended"), so it remains meaningful after the prose changes.

Each ending is typed on two axes, and both are required (the `ending` block forbids extra
fields, so a single `type` field is rejected). `valence` is how the ending feels:
`positive`, `neutral`, or `negative`. `kind` is what mechanically happened, a closed set:
`success`, `setback`, `death`, `capture`, `completion`, or `discovery`. The age-band policy
gate (PL-15) rejects any ending `kind` forbidden for the band, so pick a `kind` appropriate
to the reader; the two axes together give the reviewer a quick read on each outcome.

---

## Concept Brief Field List

The concept brief is the structured input to Stage A. All fields are passed to the
generation prompt as `{concept_brief}`. Fields marked with `?` are optional.

| Field | Type | Description |
|-------|------|-------------|
| `title?` | string | Working title (optional; the LLM may propose one) |
| `premise` | string | One-paragraph description of the situation and stakes |
| `protagonist` | object | `name` (fictional), `age` (fictional), `role` (description) |
| `point_of_view` | enum | `"second_person"` (default and required for v1) |
| `age_band` | enum | one of `"3-5"`, `"5-8"`, `"8-11"`, `"10-13"`, `"13-16"`, `"16+"` |
| `reading_level_target` | object | `{ "scheme": "flesch_kincaid_grade", "target": 4.0, "tolerance": 0.5 }` |
| `tier` | int | `1` (branching only) or `2` (state-tracking) |
| `tone` | string | e.g. "adventurous", "gentle mystery", "tense survival" |
| `themes_allowed` | string[] | e.g. `["friendship", "courage", "nature"]` |
| `content_nogo` | string[] | e.g. `["graphic violence", "romantic content"]` |
| `target_node_count` | int | Target total node count (see budgets above) |
| `ending_count` | int | Number of distinct endings (minimum 2) |
| `structure_pattern` | enum | `time_cave`, `gauntlet`, `branch_and_bottleneck`, `loop_and_grow`, `open_map`, `sorting_hat` |
| `desired_variables[]?` | object[] | For Tier 2: each has `name`, `type`, `initial`, `min?`, `max?`, `description` |
| `special_constraints[]?` | string[] | Freeform constraints for the LLM; length-limited; no real PII |

`protagonist.name` must be a fictional name, not the name of any real child. The backend
validates this field does not match any `child_profile.display_name` before dispatching to
the provider.

---

## Common Validation Failures and How to Avoid Them

| Failure | Rule | Avoidance |
|---------|------|-----------|
| Orphan node | Reachability: BFS from start does not reach the node | Every node must be the `target` of at least one choice from a reachable node |
| Dead end | Stateful dead-end: a reachable configuration has zero visible choices | Ensure at least one choice is visible (its condition is true) at every reachable non-ending state |
| Dangling target | Reference integrity: `choice.target` names a node that does not exist | Do not generate or edit `target` values before the node list is finalized |
| Bound overflow | Condition consistency: a reachable `inc`/`dec` would exceed `min`/`max` | Set `max` and `min` conservatively; avoid incrementing a counter in a loop without a cap check |
| Configuration cap | State space exceeds 100,000 reachable configurations | Reduce variables; narrow integer ranges; use `branch_and_bottleneck` to converge |
| Dead branch | Conditional usefulness: a conditional choice is unreachable from any configuration | Remove the condition or redesign the variable assignments so the condition can be satisfied |
| No path to ending | Stateful termination: a reachable configuration has no path to any ending | Ensure every cycle has an exit; avoid conditions that permanently block the only exit choice |

---

## Related Documents

- [Tech Spec: Authoring Pipeline](./tech-spec.md#authoring-pipeline-staged-generation)
- [Tech Spec: Validation Gate](./tech-spec.md#validation-gate-deterministic-no-llm)
- [Tech Spec: Story Runtime Semantics](./tech-spec.md#story-runtime-semantics-v1)
- [Stage A Structure Prompt](./stage-prompts/structure.md)
- [Stage B Prose Prompt](./stage-prompts/prose.md)
- [Stage C Repair Prompt](./stage-prompts/repair.md)
- [ADR-001: JSON Storybook format](./adr/adr-001-story-format-json-storybook.md)
- [ADR-006: Conditions in-house evaluator](./adr/adr-006-conditions-inhouse-evaluator.md)
- [ADR-011: Story-scale framework (band x length x style)](./adr/adr-011-story-scale-framework.md)
