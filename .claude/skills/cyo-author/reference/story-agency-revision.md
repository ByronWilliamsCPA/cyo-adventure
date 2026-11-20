# Story agency: make the book behave like a choose-your-own-adventure all the way through

This is the recipe that fixed five catalog books on 2026-11-20 (`the-signal-in-the-static`,
`the-midnight-museum`, `the-hollow-lighthouse`, `the-sky-ship-stowaway`, `the-sunken-signal`). It
has two uses:

- **Filling a skeleton** (`SKILL.md` step 3): structure is frozen. Apply the prose rules R1, R2, R4,
  R5, R6 and R7 below, and where the skeleton declares `variables`, write the plants and payoffs it
  already has so the reader feels them (see "Proven callback pattern"). Never add a variable,
  effect, condition, node, or choice during a fill.
- **Revising a filled book** (an editorial pass over `out/<book>.filled.json`): everything below
  applies, including R3, which adds variables, conditions, effects, and nodes under the invariants
  at the end.

The drafting guide's "Reader Agency" section and the fill prompt's "Reader agency" clause state the
same rules for the generation pipeline; this file is the long form with the why and the method.

## The problem this fixes

An editorial read of the catalog found books that open well and then stop honoring the reader's
choices by the middle. Measured across 31 books:

1. **No choice ever comes back.** 28 of 31 books declared no variables, so nothing a reader does
   early can matter later. Every route through a branch-and-bottleneck graph converges on the same
   hub and continues identically.
2. **The narrator says so out loud.** Merge (hub) nodes were written to fit every way in, so 69 of
   them open with lines like "Whichever way Mira had come, every path had led her here at last."
   That tells a child their choice was irrelevant.
3. **Failure is a dead stop.** 198 setback endings end with the hero giving up or going home, often
   only three or four taps in. The curious, risky choice a kid actually wants to tap is punished
   with boredom.
4. **Nobody speaks.** There is almost no dialogue, so companions and antagonists are scenery.
5. **Choices are announced twice and some are not choices.** 462 decision nodes restate their
   options in prose just above the buttons ("She could X. Or she could Y."); 105 labels are meta
   ("Sit with what this means"), leak graph jargon ("hub"), or say "you" over third-person prose;
   some forks have one obviously right answer.

Write for the child. An adult will read every word before approving it.

## How the reader app renders a book (facts you must design around)

- A node is `{id, body, choices[], on_enter[], is_ending, ending}`. `body` is ONE string. There is
  no conditional text inside a body. Whatever a body says must be true on every path that can reach
  it and in every state.
- A choice is `{id, label, target, condition?, effects?}`. `condition` is a JSONLogic object over
  declared variables; a choice whose condition is false is not shown. `effects` mutate variables
  when the choice is taken.
- From 8-11 up, the reader flows consecutive single-choice nodes into one screen: if a node declares
  exactly ONE choice, the next node's body is appended below it and the child never sees a button
  for it. A single-choice node is a paragraph break, not a page turn, so a short route-specific node
  leading into a shared node reads as one continuous passage. A node that declares TWO choices of
  which only one is visible (because of a condition) is NOT flowed; the child sees one button.
- The reader shows no inventory or state. A consequence is felt only through which choices appear
  and what the prose says.

## Proven callback pattern

Reference: `out/the-signal-in-the-static.filled.json`, variable `has_battery`.

```json
"variables": [
  {"name": "has_battery", "type": "bool", "initial": false,
   "description": "Wren packed her grandfather's spare battery."}
],
"metadata": {"tier": 2, "...": "..."}
```

- **Plant.** An early decision offers two appealing options. One carries
  `"effects": [{"op": "set", "var": "has_battery", "value": true}]`. Each option leads to its own
  short single-choice arrival node that acknowledges what the reader just did (two or three
  sentences), and both arrival nodes lead to the node the story originally continued at. In the
  flowed bands the arrival node and the shared node read as one passage.
- **Payoff.** Much later, at the failing power cell, the body is true in both states (it does not
  say the battery is in her pack), and the choice "Splice in Grandpa's spare battery." carries
  `"condition": {"==": [{"var": "has_battery"}, true]}`. The reader who took the battery sees an
  option the other reader never sees. The reader who left it faces only the hard way, and that
  setback ending can say what would have helped, which is the hook to read again.

Three payoff shapes have worked in the catalog; the first two are the strongest:

- **Same label, opposite conditions.** Two choices with the same label, gated `true` and `false` on
  the flag, leading to different nodes. Every reader sees the same button; what happens depends on
  what they did earlier ("Run to the bosun." in `the-sky-ship-stowaway`, flag `told_bosun`).
- **Swap pair (one visible button of two declared).** Two differently labelled choices on opposite
  conditions, so each reader sees exactly one: the planted reader's version leads somewhere the
  other cannot ("Chalk an arrow on every shelf end and go on in the dark." where an unplanted
  reader sees "Go on in the dark, counting shelves by hand.", in `the-midnight-museum`, flag
  `has_chalk`).
- **Unlocked option.** One conditional choice beside unconditional ones.

Rules learned from the pilots and the validator:

- Set `metadata.tier` to `2` once the book declares any variable. Keep 3-5 and 5-8 at Tier 1.
- The first decision (a node with two or more choices) must not be the first node: rule PL-25
  requires at least one node of story before it. Put a plant after the opening node, not on it.
- Variables: `bool` only, lower snake case, with a `description`. Keep the count small (two to
  four).
- A node with conditional choices always keeps at least one unconditional choice, so no reader is
  stranded.
- Plant and payoff must be on a common path: the payoff node must be reachable by a reader who took
  the plant AND by one who did not. Check this by playing both.
- Plants are trade-offs, not free upgrades: taking the battery means leaving something else, or
  costs time, or two options are mutually exclusive plants that pay off in different places.
- Best payoffs: (a) convert an existing continuity error into a real consequence (the battery was
  mentioned at the payoff node but never picked up anywhere), (b) make an existing short setback
  avoidable by something the reader could have done earlier, and have that setback's text hint at
  it, (c) let a companion the reader helped or trusted earlier show up and change a later scene,
  (d) unlock an ending or a short scene only that reader gets. A revision may add roughly two to
  six nodes per callback; it may not delete existing nodes or endings.

Verify state by playing, with the project's own engine:

```python
import json
from pathlib import Path

from cyo_adventure.player.engine import StoryEngine
from cyo_adventure.storybook.models import Storybook

book = Storybook.model_validate(json.loads(Path("out/<book>.filled.json").read_text()))
engine = StoryEngine(book)
state = engine.start()
state = engine.choose(state, "<choice id>")  # repeat along a path
print(state.current_node, [c.label for c in engine.visible_choices(state)])
```

## What to change, in priority order

**R1. Merge nodes open in scene.** For every node with two or more distinct inbound nodes: the body
starts in the moment (a sensory fact, an action, a line of speech) and presupposes only what is
true on EVERY inbound path. Delete every sentence that acknowledges alternative routes
("whichever", "however she got here", "all three threads", "no matter which", "wherever the trail
led"). Do not state where a companion or prop is, or a fact, that only some inbound routes earned.
If the arrival deserves a route-specific beat, put it in the inbound node (or, in a revision, add a
short single-choice arrival node per route, which flows from 8-11 up). Then re-read every inbound
node followed by the merge node as one passage and fix anything that jars. The pipeline's fill
prompt now lists each merge with its inbound node ids; for a manual fill, get the same list from
`validator.agency.inbound_sources`.

**R2. Continuity along real paths.** Play the book. Anything a node asserts (an object in hand, a
person already met, a fact already learned, a place already visited) must be true on every path
that reaches it. The gate's PN-1 warnings list names introduced only on a branch a reader can skip;
treat each as a lead and fix the real ones. Watch for two branches that no single path crosses
telling incompatible backstories: each path reads as coherent, and only a reader who replays meets
the contradiction.

**R3. Callbacks (revision only).** Add two or three real callbacks using the pattern above (one or
two for a short book). At least one must change which ENDING a reader can reach. Record each as
plant node, payoff node, variable.

**R4. Setbacks give something back.** Every negative ending, especially every one reachable within
three decisions and every one that ends with the hero leaving or giving up, must do at least one
of: reveal something true and intriguing about the mystery, land a real laugh, or hand the reader a
concrete reason to try again (what she glimpsed, what she lacked, the door she did not try). Close
on the glimpsed thing, not on "next time". No ending calls itself boring or summarizes instead of
dramatizes. Keep each ending's `kind` and `valence`. Where a setback follows from one obviously
reckless tap, make the outcome fair and the moment vivid, not a scolding. Where the skeleton itself
punishes the cautious choice beside a sibling that succeeds by an imitable risk, flag it; a fill
cannot repair a moral the structure carries.

**R5. People talk.** In every scene where another character is present, let them speak in their
own voice, in double quotation marks, with what they want showing. Give the hero lines too. Aim for
spoken lines in at least a quarter of the nodes where a second character is on stage, and for every
companion or antagonist to have a recognisable way of talking. A spoken line has to do work
(reveal, refuse, tempt, joke). A solitary hero can still have voices: a radio, a journal read
aloud, a recording, the hero talking to an animal or to herself.

Dialogue drives Flesch-Kincaid DOWN: each short spoken line counts as a sentence, so a run of
quick exchanges lands under the band floor (RL-13) even when the prose is right for the age. The
first dialogue draft of `the-hollow-lighthouse` put 43 of 161 nodes out of band this way. Join a
speaker's short lines into one fuller sentence ("Wait, the lamp should be green, not white," Ada
said, already climbing.) and target roughly 13 to 16 words per sentence at 10-13.

**R6. Choice hygiene.**

- Cut the end-of-node recap of the options. The last sentences of a decision node raise the stakes
  or sharpen the moment, then stop. The buttons state the options. (At 3-5 and 5-8 one read-aloud
  question inviting the choice is allowed; a per-band ruling is pending, `AL-767`.)
- Every label is a concrete action the hero takes, in the book's person: over third-person prose a
  neutral imperative ("Steady the lantern", never "Steady yourself"; no "you" or "your"). Replace
  meta labels ("Sit with what this means", "Decide how to dig deeper") with what she actually does.
  Remove graph jargon ("hub").
- No fork with one obviously right answer. Rewrite "do it well" versus "do it badly" as two
  defensible approaches with different risks and different appeal.
- The first sentence of the node a choice leads to shows that choice happening (the gate's CG-4
  advisory flags targets that share no content word with the label).
- Cosmetic forks (both options rejoin at the next node with nothing changed) are prime plant sites
  in a revision: give one option an effect that pays off later, or make the two arrivals genuinely
  different.

**R7. Prose.** Cut padding and filler intensifiers ("never once, not a single time", "the very",
"right now, this very moment", "whole", "simply", "actually"). Prefer the concrete noun and the
active verb. Keep the book's declared person (`metadata.narrative_person`) and one tense. Keep
sentences inside the band's reading level (do not increase the number of RL-13 warnings). No
moralizing, no narrator telling the reader what the hero learned.

## Invariants for a revision

- Edit only the one book file. Keep the top-level `id`, `title`, `schema_version`, `start_node`,
  `metadata.age_band`, and every existing node id, choice id, and ending id. Do not delete nodes,
  choices, or endings. You may add nodes, choices, endings, variables, conditions, and effects, and
  you may retarget an existing choice only when a new arrival node is inserted in front of its old
  target.
- New ids follow the book's existing naming style. Choice ids are unique across the book.
- Keep `metadata.ending_count` equal to the real number of ending nodes, and if the gate's PL-23
  advisory says the declared `estimated_minutes` is off, set it to the derived value.
- Content safety: nothing more frightening, violent, or perilous than the book already is for its
  band; do not make a dangerous real-world act look attractive or easy to imitate (entering sealed
  or flooding spaces, climbing unsecured heights, handling mains electricity, going off alone with a
  stranger). No real brand names, no real people, no romance, no profanity.
- Never use the em-dash character (U+2014). Write the file back with
  `json.dump(doc, fh, indent=2, ensure_ascii=True)` plus a trailing newline. Before the first edit,
  confirm that a load-and-dump round trip leaves `git diff` empty; if it does not, stop and find out
  why.
- The offline gate passes: `uv run python scripts/run_story_gate.py out/<book>.filled.json` exits
  0, and `cyo_adventure.validator.gate.run_fill_gate(doc).blocked` is `False` (the importer's
  posture). No new ERROR findings. Compare warning counts by rule before and after: RL-13 must not
  rise; CG-4, CG-6, and PN-1 should fall.
- A revised book reaches an environment that already holds its first edition only as a new edition
  (`import_catalog` with `--only` and `--edition`, `AL-769`).

## Method

1. Record the baseline with three commands:

   ```bash
   uv run python scripts/run_story_gate.py out/<book>.filled.json
   uv run python scripts/check_prose_craft.py out/<book>.filled.json --json
   uv run python scripts/measure_consequence.py out/<book>.filled.json
   ```

2. Read the book by playing it before changing anything: at least six complete playthroughs that
   between them cover every major route and every merge, reading the prose in the order a child
   would. Reading the node array in file order is not reading the story. Note every seam, break,
   flat ending, and silent scene with its node id.
3. Write a short edit plan outside the repo (your scratch directory): the callbacks, the merge
   nodes to rewrite, the endings to rework, the scenes that get dialogue.
4. Make the edits with a script kept outside the repo (load, modify by node id, dump), so every
   change is deliberate and reproducible. Work in passes and run the gate after each pass.
5. Replay every path you touched, in both states of every variable, start to ending. Then play
   three paths you did NOT deliberately touch, to catch collateral breaks.
6. Record the after numbers with the same three commands. Hold the precise agency checks at zero:

   ```bash
   uv run python scripts/check_prose_craft.py out/<book>.filled.json --check \
       --max-merge-seams 0 --max-meta-labels 0 --max-jargon-labels 0 \
       --max-second-person-labels 0
   ```

   `measure_consequence.py` can call a fork false that is true under another reachable
   configuration (`AL-770`); confirm a "false" fork on a planted path by playing it before acting on
   the number.
7. Log what the run taught you (`SKILL.md` step 7).

## What good looks like

A reader who took the battery gets a moment, eighty nodes later, where the story hands them
something only they earned. A reader who walked into the storm gets an ending that makes them say
"oh, so THAT is what the keeper was hiding" and tap "Try a different choice". Nobody is told that
every path led here. The people in the story have voices. The last sentence before the buttons
makes the choice harder, not clearer.
