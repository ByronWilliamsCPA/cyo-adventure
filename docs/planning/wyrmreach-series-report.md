# Wyrmreach: Three-Book 16+ Gamebook Series, Build and Verification Report

**Date**: 2026-07-25
**Branch**: `claude/dnd-story-game-series-mqr9zy`
**Design doc**: [wyrmreach-series-design.md](./wyrmreach-series-design.md)

## 1. What was asked for and what was built

A production 16+ story in the **gamebook** style (not prose), built as a **state-carrying series** with a
Dungeons-and-Dragons-style adventure and party progression across the books, left open for further books.
Books 1 and 2 were the original two-book ask. Book 3 is a follow-up capability test: build one book at the
**longest possible length and largest node count** the system allows.

Books 1-2 occupy the ADR-011 cell **(16+, medium, gamebook)**; book 3 occupies **(16+, long, gamebook)**, the
largest cell in the matrix, at 746 of its 750 permitted nodes. All three are Tier 2 (stateful),
`production_eligible`, topology `branch_and_bottleneck`, series id `wyrmreach`, `carries_state: true`,
`is_final: false` on the top book so the chain stays open.

| Metric | Book 1: The Vault of Nine Iron | Book 2: The Sunless March | Book 3: The Ninth Hand |
| --- | --- | --- | --- |
| Cell | (16+, medium, gamebook) | same | **(16+, long, gamebook)** |
| Spec | `data/series/wyrmreach/book1.*` | `book2.*` | `book3.*` (7 act parts) |
| Skeleton | `skeletons/16+/the-vault-of-nine-iron.json` | `the-sunless-march.json` | `the-ninth-hand.json` |
| Filled | `out/the-vault-of-nine-iron.filled.json` | `the-sunless-march.filled.json` | `the-ninth-hand.filled.json` |
| Nodes | 305 (budget 300-475) | 305 | **746** (budget 475-750) |
| Endings | 105 (PL-17 floor 77) | 105 | 232 (floor 187) |
| Decision nodes | 131 (floor 25) | 131 | 231 (floor 60) |
| Ending mix | 1 completion, 6 success, 2 discovery, 30 setback, 14 capture, 52 death | same shape, reauthored | 1 completion, 6 success, 2 discovery, 64 setback, 41 capture, 118 death |
| Longest path | 71 hops (max 73) | 71 | 74 hops (max 93) |
| Fastest satisfying finish | 29 nodes (PL-20 floor 29) | 29 | 52 nodes (floor 37) |
| Words | 16,995 (mean 55.7/node) | 18,138 (mean 59.5/node) | **42,085** (mean 56.4/node) |
| Reachable configurations | 30,416 (cap 100,000) | 56,739 | 36,781 |
| Variables | vigor, renown, iron_key, knows_compact, door_state | + second_iron, deep_charts, oath_sworn | vigor, renown, iron_key, second_iron, knows_compact, crown_iron, wyrm_pact, door_state |
| Estimated read | 40 minutes | 40 | 90 |
| Gate result | **0 findings** | **0 findings** | **1 finding**: the expected L2-13 scale advisory |

Total authored content across the chain: **1,356 passages, 77,218 words** of prose, plus 1,356 skeleton
beats and roughly 2,100 choice labels.

Book 3 is at the ceiling in every dimension the matrix bounds except depth, which is deliberately low: a
ceiling-scale gamebook needs **breadth**, not length. Rooms hang as parallel chains off an act hub and
reconverge on the act gate, so 746 nodes fit inside 74 hops of the 93 allowed, and a reader's route through
the book is 52 nodes rather than 700.

## 2. The story and the party progression

Book 1 (**Gallowmere / Kar Duhn**): the free company called the Ninth Sword takes a Warden-Marshal's
commission to recover a vanished garrison's tax-iron, and finds the Compact: the frontier's oldest
arrangement, which does not kill the thing under the hill but feeds it on a schedule behind a door held
by nine key-irons. The company can shut the door, keep the count itself, open it, or walk out.

Book 2 (**Rell's Gate / the Deep Road / Hollowmarch**): the company is known now, holds Kar Duhn's ninth
iron, and knows what the doors hold. Sixteen Mile Tower has stopped reporting; the second door lies at
the end of the Deep Road, and the new ninth hand at the courier chapel is Sister Nyre's own brother.

Progression is mechanical as well as narrative:

- **renown** carries (book 2 starts at 2) and buys late-act options a nameless company cannot reach.
- **vigor** is the attrition clock: careless front halves make the back half harder in every book.
- **iron_key** and **knows_compact** carry as leverage; book 2's own acquisitions (`second_iron`,
  `deep_charts`, `oath_sworn`) build on top of them.
- The canonical completion ending of book 2 (*The Second of Nine*) requires **both** irons and leaves
  two of the Compact's nine counts unkeepable, then names the third door under the spine of the
  Wyrmreach with a date on it. That is the book 3 hook.

Book 3 (**Sarnhold / the Ninefold Road / Kar Ashen**): the third door is not in a ruin. It is at the top
of a working city of four thousand people inside the mountain, with a mint, an aqueduct, a bone registry,
an arrears auction and a chapel whose evening office is arithmetic, all of it legal by its own charter and
all of it load-bearing for the count that keeps Ashendrel asleep. The crown door has nine sockets and eight
irons; the ninth hand is a vacant office with a nine-year term and a start date this spring, and the city
is expecting somebody to take it. The company arrives holding two of the nine irons, which makes it the
only party on the frontier that can fill the vacancy, and therefore the only party the city has a use for.

Book 3's progression is the carried state itself. `iron_key`, `second_iron` and `knows_compact` are read-only
carried gates that open routes nothing else opens; `renown` is floored at its carried value, because a company
that shut two doors cannot become unknown; and the new state (`crown_iron`, `wyrm_pact`, `door_state`) is what
the act 6 endings read. The completion ending, *The Third of Nine*, requires the crown iron **and** the truth of
the Compact, and closes on the crown ledger's tenth column, where somebody has written the six remaining doors
in order with dates against each. The nearest is Sarnhold's own chapel. That is the book 4 hook.

## 3. Verification

All checks were run on this branch; every command is in the design doc section 6.

1. **Single-story gate** (`scripts/run_story_gate.py`, i.e. `validator.gate.run_gate`): books 1 and 2
   return `findings=0 blocked=False safety_flagged=False`. Book 3 returns `findings=1 blocked=False
   safety_flagged=False`, and the one finding is the **L2-13 scale advisory** described in N6 below. All
   three books therefore carry zero errors and zero avoidable warnings, including RL-13 reading level
   across all 1,356 filled nodes and the PL-19 story-mean words-per-node advisory.
2. **Skeleton gate and design brief** (`scripts/check_skeleton.py`): all three skeletons pass with their
   declared cells, `(16+, medium, gamebook)` for books 1-2 and `(16+, long, gamebook)` for book 3,
   topology `branch_and_bottleneck`, tier 2.
3. **Fill integrity** (`scripts/check_fill_integrity.py`): for all three books, only node bodies and
   choice labels differ from the skeleton, no `<<FILL` markers remain, and word stats are inside the band
   envelope (book 3: mean 56.4 words/node over 746 nodes, max 136 against the 175 hard cap).
4. **Cross-book series validator** (`validator.series.validate_series`, SR-1..SR-7): **0 findings** over
   the three-book chain, both as skeletons and as filled books.
5. **Layer-2 configuration walk**: 30,416 reachable configurations for book 1, 56,739 for book 2 and
   36,781 for book 3, all inside the 100,000 cap; the full gate completes in about three seconds for a
   medium book and about ten for book 3.
6. **Player smoke test** (`player.engine.StoryEngine`). Book 2: the story opens with the carried state
   (`iron_key=true`, `knows_compact=true`, `renown=2`), the carried-state-gated choice at `a4_out` is
   visible and playable, and a 35-node playthrough reaches *The Second of Nine* with `second_iron`
   acquired and `door_state=1`. Book 3: the engine opens with `iron_key`, `second_iron` and
   `knows_compact` true and `renown=3`, and a breadth-first drive over the engine's own visible-choice
   filter reaches the completion ending *The Third of Nine* in 52 choices with `crown_iron=true`, plus
   *The Spine Writ* (`renown>=4`), *The Iron Left the Mountain* (`door_state=6`), *Its Own Words, Written
   Down* (`wyrm_pact=true`) and *Into the Strongbox*. Every carried gate and every new gate opens on a
   route a reader can actually play, not merely on one that exists in the graph.

## 4. Notes and findings

### N1 (method): one spec compiles both artifacts

`scripts/build_series_book.py` compiles a compact node spec into **both** the `<<FILL>>` skeleton and
the filled story, so a skeleton and its filled story cannot drift. The spec keeps beats and prose
side by side, and the builder reports the structural budget (dangling targets, PL-17 floors, depth,
fastest satisfying finish, word mean) while authoring, which is what made hitting the depth ceiling and
the PL-20 arc floor a tuning exercise rather than a rewrite.

### N2 (carried variables): finding F3 of the 13-16 stress test is real and easy to trip

Book 2 was derived from book 1's topology, and the derivation had to rewrite the state model, not copy
it. Every acquisition of a carried variable becomes an unsatisfiable `== false` branch (a hard L2-11
dead-branch error) once that variable initializes true. The fix pattern that worked:

- carried variables are **read-only** in the continuation (`iron_key`, `knows_compact` appear only as
  always-satisfiable carried-state gates);
- the acquisition branch moves to a **new book-local variable** (`second_iron`);
- lore that the continuation already knows sets nothing at all.

A second, less obvious instance of the same class: a gate on a new variable (`deep_charts`) placed
*earlier* in the graph than any node that grants it is also an L2-11 dead branch. The gate at `a1_scout`
only became satisfiable once Act 0 could grant the charts. Recommend the cyo-author reference note this
ordering constraint alongside F3.

### N3 (RL-13 in practice): Flesch-Kincaid is driven by sentence count, not passage length

Getting 1,356 passages inside a reading-level window was the single largest source of iteration. At a
fixed ~60 words, the same content lands near FK 5 in four short sentences, FK 9-11 in three, and FK 13+
in two. Two consequences worth recording for future authoring runs:

- the practical rule for 16+ gamebook passages is **three sentences per passage**, roughly 20 words
  each;
- a skeleton's FILL beats are single run-on clauses and therefore always produce RL-13 warnings on the
  skeleton (one per node: 305 per medium book, 746 for book 3). That is expected and harmless, but it
  means skeleton-stage RL-13 output carries no signal at all. A future improvement would be to skip RL-13
  for bodies containing a FILL marker, the way PL-19 already special-cases them.

N8 below records how the same insight was turned into a mechanical retune at book 3's scale.

These books declare `reading_level` 9.5 +/- 2.5 (Flesch-Kincaid). That is the register the prose
actually holds; every one of the 1,356 filled nodes lands inside it.

### N4 (environment): commits on this branch are unsigned

The project requires signed commits. In this remote execution environment
`user.signingkey` points at `/home/claude/.ssh/commit_signing_key.pub`, which exists but is **empty**
(0 bytes), so `git commit -S` produces an unsigned commit and `git log --show-signature` reports "No
signature". Existing `main` commits show the same verification failure locally because
`gpg.ssh.allowedSignersFile` is unset. Signing has to happen where a real key is available; the commits
here will need re-signing (or a squash-and-sign) if the branch protection requires it.

### N5 (import path): a series book still cannot be imported with its linkage in one step

Confirming F1 of the 13-16 stress test from the other side: `import_filled_story` has no `--series-id`
option, so importing these three books through `generation.import_cli` would persist them as standalone
stories and require `assign_book_index` + `embed_series_block` to be run separately. No database was
available in this environment, so the import and approve-and-publish legs were not exercised here; the
offline gate, the chain validator and the player engine were.

### N6 (scale): L2-13 is the expected output past 460 nodes, and it is the right design

Book 3's one finding is `L2-13 scale: Tier-2 story 'sk_ninth_hand' has 746 nodes, past the hand-authoring
ceiling of 460; the completed Layer-2 configuration walk is now its sole correctness guarantee`. It is a
WARNING and never blocks. This is worth recording as a *positive* result for the validator design: the
system does not pretend a 746-node stateful gamebook can be reviewed by eye, and it does not refuse to
carry one either. It states plainly which guarantee is load-bearing.

What that means in practice is that at ceiling scale the Layer-2 walk has to be treated as the acceptance
test rather than as a lint pass. Every structural problem found while building book 3 was found by L2-11
(dead branch) or by the builder's own budget report; none of them would have been caught by reading the
spec, because the spec is 746 entries long.

### N7 (method): generate the structure, author the content

A 746-node book cannot be hand-wired entry by entry, and it must not be generated wholesale either, or the
prose is filler. What worked was a two-stage split:

1. **Structure generation.** The room module was formalised into six reusable shapes (`fork`, `monster`,
   `trap`, `social`, `loot`, `lore`, `rest`), each a fixed node count, label count and wiring. Acts are a
   hub plus parallel room chains converging on an act gate, so an act's structure is a list of
   `(shape, room_name)` pairs. This is what kept depth at 74 of 93 while the node count sits at 746.
2. **Content authoring.** Every generated beat, choice label and ending title was then replaced by
   authored content through a patch file keyed by node id, with the patch tool asserting that the label
   count matches the choice count and reporting any placeholder left behind. That assertion caught eleven
   real mismatches (missing leaf labels on `social`/`hub` shapes, `monster` rooms needing a second
   ending, single-choice nodes given two labels) that would otherwise have shipped as generated text.

The lesson: generate wiring, never voice. The failure mode to guard against is a book that gates cleanly
and reads like a table.

### N8 (RL-13 at scale): outliers can be retuned without rewriting a word

Book 3's first full gate returned 212 RL-13 advisories, 152 too low and 60 too high. Because Flesch-Kincaid
is dominated by words per sentence (N3), 185 of them cleared by **restructuring sentence boundaries with the
word content untouched**: join two sentences with `; ` or `, and ` to raise the grade, split one at a
coordinating boundary (`, and ` / `, but ` / `, so ` / `; `) to lower it. A small greedy tool picked the
boundary that landed nearest the declared target and applied it, and its output was reviewed before being
accepted. The remaining 27 were two-sentence passages with no safe split boundary and were rewritten by hand.
Two guards were needed to keep the mechanical edits grammatical:

- when folding a sentence into the one before it, a leading word may only be lower-cased if it is seen in
  lower case somewhere in the corpus and never seen capitalised mid-sentence, otherwise a character name
  that only ever opens a sentence gets silently downcased;
- a split is only safe where both sides are at least eight words and the right side opens with a subject,
  otherwise a comma inside a noun list becomes a sentence fragment.

Final state: zero RL-13 warnings across all 1,356 nodes of the chain.

### N9 (configuration budget): narrow carried integer ranges, or the walk pays for it

The Layer-2 walk enumerates one configuration per reachable (node, variable-state) pair, so at 746 nodes
every value an integer variable can take is a multiplier on the whole walk. Book 3 was authored with
`renown` declared **min 3, max 5** rather than the 0-5 of book 2, and with book 2's `deep_charts` dropped
entirely, because neither state is reachable in a continuation that starts from book 2's win. That single
decision is the difference between 36,781 configurations and a walk that risks the 100,000-configuration
L2-12 cap; it is also the more truthful model, since a company that shut two doors cannot become unknown.
Worth stating as a rule for any future continuation: **declare the range the continuation can reach, not
the range the variable could theoretically hold**.

## 5. Reproduction

```bash
# compile all three books from their specs (skeleton + filled in one pass each)
uv run python scripts/build_series_book.py data/series/wyrmreach/book1.spec.json \
    $(for a in a0 a1 a2 a3 a4; do echo --prose data/series/wyrmreach/book1.prose.$a.json; done) \
    --skeleton skeletons/16+/the-vault-of-nine-iron.json \
    --filled out/the-vault-of-nine-iron.filled.json
uv run python scripts/build_series_book.py data/series/wyrmreach/book2.spec.json \
    $(for a in a0 a1 a2 a3 a4; do echo --prose data/series/wyrmreach/book2.prose.$a.json; done) \
    --skeleton skeletons/16+/the-sunless-march.json \
    --filled out/the-sunless-march.filled.json
uv run python scripts/build_series_book.py data/series/wyrmreach/book3.spec.json \
    $(for a in a0 a1 a2 a3 a4 a5 a6; do echo --prose data/series/wyrmreach/book3.prose.$a.json; done) \
    --skeleton skeletons/16+/the-ninth-hand.json \
    --filled out/the-ninth-hand.filled.json

# gate each book, check fill integrity, then validate the chain
uv run python scripts/run_story_gate.py out/the-vault-of-nine-iron.filled.json
uv run python scripts/run_story_gate.py out/the-sunless-march.filled.json
uv run python scripts/run_story_gate.py out/the-ninth-hand.filled.json
uv run python scripts/check_fill_integrity.py skeletons/16+/the-ninth-hand.json \
    out/the-ninth-hand.filled.json
uv run python scripts/check_skeleton.py skeletons/16+/the-ninth-hand.json \
    --band 16+ --length long --style gamebook --topology branch_and_bottleneck --tier 2
uv run python scripts/build_series_book.py --series out/the-vault-of-nine-iron.filled.json \
    out/the-sunless-march.filled.json out/the-ninth-hand.filled.json
```

## 6. Adding book 4

The design doc section 7 has the procedure. In short: copy `book3.spec.json` as the shape reference, carry
`iron_key`, `second_iron`, `knows_compact` and `renown` as read-only initial state (plus `crown_iron` if
book 4 assumes it was kept), narrow every carried integer range to what the continuation can reach, give
book 4 its own acquisitions, set `book_index: 4`, and re-run the chain validator over all four filled books.
The remaining six doors are already named and dated in book 3's completion ending, with the nearest of them
in Sarnhold's own chapel.
