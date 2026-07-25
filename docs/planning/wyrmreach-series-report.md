# Wyrmreach: Two-Book 16+ Gamebook Series, Build and Verification Report

**Date**: 2026-07-25
**Branch**: `claude/dnd-story-game-series-mqr9zy`
**Design doc**: [wyrmreach-series-design.md](./wyrmreach-series-design.md)

## 1. What was asked for and what was built

A production 16+ story in the **gamebook** style (not prose), built as a **two-book, state-carrying
series** with a Dungeons-and-Dragons-style adventure and party progression across the books, left open
for further books.

Both books occupy the ADR-011 scale cell **(16+, medium, gamebook)** and are Tier 2 (stateful),
`production_eligible`, topology `branch_and_bottleneck`, series id `wyrmreach`, `carries_state: true`,
`is_final: false` on the top book so the chain stays open.

| Metric | Book 1: The Vault of Nine Iron | Book 2: The Sunless March |
| --- | --- | --- |
| Spec | `data/series/wyrmreach/book1.*` | `data/series/wyrmreach/book2.*` |
| Skeleton | `skeletons/16+/the-vault-of-nine-iron.json` | `skeletons/16+/the-sunless-march.json` |
| Filled | `out/the-vault-of-nine-iron.filled.json` | `out/the-sunless-march.filled.json` |
| Nodes | 305 (cell budget 300-475) | 305 |
| Endings | 105 (PL-17 floor 77) | 105 |
| Decision nodes | 131 (floor 25) | 131 |
| Ending mix | 1 completion, 6 success, 2 discovery, 30 setback, 14 capture, 52 death | same shape, reauthored |
| Longest path | 71 hops (max 73) | 71 |
| Fastest satisfying finish | 29 nodes (PL-20 floor 29) | 29 |
| Words | 16,995 (mean 55.7/node) | 18,138 (mean 59.5/node) |
| Reachable configurations | 30,416 (cap 100,000) | 56,739 |
| Variables | vigor, renown, iron_key, knows_compact, door_state | + second_iron, deep_charts, oath_sworn |
| Gate result | **0 findings**, blocked=false | **0 findings**, blocked=false |

Total authored content: 610 passages, 35,133 words of prose, plus 610 skeleton beats and roughly 900
choice labels.

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
- **vigor** is the attrition clock: careless front halves make the back half harder in both books.
- **iron_key** and **knows_compact** carry as leverage; book 2's own acquisitions (`second_iron`,
  `deep_charts`, `oath_sworn`) build on top of them.
- The canonical completion ending of book 2 (*The Second of Nine*) requires **both** irons and leaves
  two of the Compact's nine counts unkeepable, then names the third door under the spine of the
  Wyrmreach with a date on it. That is the book 3 hook.

## 3. Verification

All checks were run on this branch; every command is in the design doc section 6.

1. **Single-story gate** (`scripts/run_story_gate.py`, i.e. `validator.gate.run_gate`): both filled
   books return `findings=0 blocked=False safety_flagged=False`. That is zero errors **and** zero
   warnings, including RL-13 reading level across all 610 filled nodes and the PL-19 story-mean
   words-per-node advisory.
2. **Skeleton gate and design brief** (`scripts/check_skeleton.py`): both skeletons pass with the
   declared cell `(16+, medium, gamebook)`, topology `branch_and_bottleneck`, tier 2.
3. **Fill integrity** (`scripts/check_fill_integrity.py`): for both books, only node bodies and choice
   labels differ from the skeleton, no `<<FILL` markers remain, and word stats are inside the band
   envelope.
4. **Cross-book series validator** (`validator.series.validate_series`, SR-1..SR-7): **0 findings** over
   the pair, both as skeletons and as filled books.
5. **Layer-2 configuration walk**: 30,416 reachable configurations for book 1 and 56,739 for book 2,
   both well inside the 100,000 cap; the full gate completes in about three seconds per book.
6. **Player smoke test** (`player.engine.StoryEngine` on the filled book 2): the story opens with the
   carried state (`iron_key=true`, `knows_compact=true`, `renown=2`), the carried-state-gated choice at
   `a4_out` is visible and playable, and a 35-node playthrough reaches the completion ending
   *The Second of Nine* with `second_iron` acquired and `door_state=1`.

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

Getting 610 passages inside a reading-level window was the single largest source of iteration. At a
fixed ~60 words, the same content lands near FK 5 in four short sentences, FK 9-11 in three, and FK 13+
in two. Two consequences worth recording for future authoring runs:

- the practical rule for 16+ gamebook passages is **three sentences per passage**, roughly 20 words
  each;
- a skeleton's FILL beats are single run-on clauses and therefore always produce RL-13 warnings on the
  skeleton (305 per book here). That is expected and harmless, but it means skeleton-stage RL-13 output
  carries no signal at all. A future improvement would be to skip RL-13 for bodies containing a FILL
  marker, the way PL-19 already special-cases them.

These books declare `reading_level` 9.5 +/- 2.5 (Flesch-Kincaid). That is the register the prose
actually holds; every one of the 610 filled nodes lands inside it.

### N4 (environment): commits on this branch are unsigned

The project requires signed commits. In this remote execution environment
`user.signingkey` points at `/home/claude/.ssh/commit_signing_key.pub`, which exists but is **empty**
(0 bytes), so `git commit -S` produces an unsigned commit and `git log --show-signature` reports "No
signature". Existing `main` commits show the same verification failure locally because
`gpg.ssh.allowedSignersFile` is unset. Signing has to happen where a real key is available; the commits
here will need re-signing (or a squash-and-sign) if the branch protection requires it.

### N5 (import path): a series book still cannot be imported with its linkage in one step

Confirming F1 of the 13-16 stress test from the other side: `import_filled_story` has no `--series-id`
option, so importing these two books through `generation.import_cli` would persist them as standalone
stories and require `assign_book_index` + `embed_series_block` to be run separately. No database was
available in this environment, so the import and approve-and-publish legs were not exercised here; the
offline gate, the chain validator and the player engine were.

## 5. Reproduction

```bash
# compile both books from their specs (skeleton + filled)
for b in 1 2; do
  uv run python scripts/build_series_book.py data/series/wyrmreach/book$b.spec.json \
      $(for a in a0 a1 a2 a3 a4; do echo --prose data/series/wyrmreach/book$b.prose.$a.json; done) \
      --skeleton "skeletons/16+/$([ $b = 1 ] && echo the-vault-of-nine-iron || echo the-sunless-march).json" \
      --filled "out/$([ $b = 1 ] && echo the-vault-of-nine-iron || echo the-sunless-march).filled.json"
done

# gate each book, check fill integrity, then validate the chain
uv run python scripts/run_story_gate.py out/the-vault-of-nine-iron.filled.json
uv run python scripts/run_story_gate.py out/the-sunless-march.filled.json
uv run python scripts/check_fill_integrity.py skeletons/16+/the-sunless-march.json \
    out/the-sunless-march.filled.json
uv run python scripts/build_series_book.py --series out/the-vault-of-nine-iron.filled.json \
    out/the-sunless-march.filled.json
```

## 6. Adding book 3

The design doc section 7 has the procedure. In short: copy `book2.spec.json` as the shape reference,
carry `iron_key`, `knows_compact`, `second_iron` and `renown` as read-only initial state, give book 3
its own acquisitions, set `book_index: 3`, and re-run the chain validator over all three filled books.
The third door is already named and dated in book 2's completion ending.
