# Story Plan retrospective: known-defect corpus (WP-1.3)

`known-defects.json` is the pre-registered answer key for the Story Plan retrospective gate G1
(`docs/planning/story-plan-implementation-plan.md`, WP-1.3 and WP-1.5). It is committed before WP-1.4 starts, which is
what freezes it: change it only by a new commit that says why, and never after a WP-1.4 extraction has been scored
against it. WP-1.4's extracting agent must not read this directory.

## What each entry holds

| Field | Meaning |
| --- | --- |
| `id` | Stable id: `KD-LH-*` (Hollow Lighthouse), `KD-RB-*` (Run B plant leaks), `KD-OS-PP-*` (public plant) |
| `source` | The document and section the finding came from, plus other documents that cite it |
| `book` | File, SHA-256, title, node count, and git revision or run label. Re-check the hash before scoring |
| `node`, `other_nodes` | Node ids the finding resolves to in that exact file |
| `defect_class` | One of the seven classes in `defect_classes` (each mapped to the SP rule or assertion it exercises) |
| `severity` | `blocker`, `should-fix`, `leak`, or for the public plant `thin` / `unearned` |
| `trigger` | The variable state or route that exposes it, in words |
| `quotes` | Verbatim sentences; every one is asserted to be a substring of that node's body when the file is generated |
| `witnesses` | A shortest route from the start node as node ids and choice ids, with the final variable state |
| `verification` | What reproduced, what did not, and the method |

## Entries

17 entries: 13 individual entries and 4 public-plant payoff entries.

| Class | Count | Entries |
| --- | ---: | --- |
| `unestablished_fact_on_route` | 7 | B1, B3, B3-follow, B3-honest, S1, S3, S4 |
| `state_contradiction` | 1 | B2 |
| `repeated_reveal` | 1 | S2 |
| `two_backstories` | 1 | BS1 (AL-773, pre-revision book) |
| `plant_leak_unplanted_route` | 2 | KD-RB-L2-OVENS, KD-RB-O1-E05 |
| `cross_payoff_reference` | 1 | KD-RB-L2-BEACON |
| `public_plant` | 4 | KD-OS-PP-* (one unearned, three thin, across two fills) |

By source: the Lighthouse continuity read (`lighthouse-continuity-read.md`) gives 9 entries (B1 to B3, two B3 siblings,
S1 to S4); AL-773 gives 1; section 4.2 of `structural-verification-2026-11-20.md` and its `runs/` and `playthroughs/`
give 7 (three Run B leaks, four public-plant payoffs).

WP-1.3 item 5 (findings from WP-0.4 on the other three books) is empty: WP-0.4 has not run, so
`findings-<slug>.md` files do not exist yet. WP-0.4 findings, when they exist, are added only before WP-1.4 starts.

## Corrections made while verifying

Every entry was re-played with `StoryEngine` (a breadth-first search over `(node, variable state)` with route
constraints) against the cited file rather than trusted from the summary. The full list is `dropped_or_corrected` in
the JSON. The ones that change how G1 should score:

- **B1 to B3 all reproduce.** B1 is state-independent; B2 needs `has_key = true` (the choice is also visible with
  `has_key = false`, where the ending is correct); B3 has an independent name half and boat half.
- **S1:** the journal half does not reproduce and is dropped; the "where Ferris lives" half is kept as weak.
- **S2:** the reveal repeats at most twice on one path, not "several times", and no SP rule covers a repeated
  establishment, so it is not a G1 miss.
- **AL-773 (BS1):** the source says no single path crosses the two backstories. A single path does cross claim set A
  (Ferris did not light it) and claim set B (Ferris built and left it burning); only the claim-bearing endings are never
  co-visited. The answer key is the two claim sets, not that wording.
- **Public plant:** `n04d0` does not show the signature to "every reader"; it is reachable without the plant and it is
  the node the plant leads straight on to. SP-4 still applies.
- **Run B leaks all reproduce.** `e05_0` leaks three facts, not one.

## Scoring notes for WP-1.5

- The exact classes (public plant, cross-payoff reference, two backstories) are `KD-OS-PP-*`, `KD-RB-L2-BEACON` and
  `KD-LH-BS1`.
- The assertion classes are the two `plant_leak_unplanted_route` entries plus the beacon entry (the three Run B leaks)
  and B1 to B3.
- `KD-LH-B3-honest` depends on `KD-LH-B3-follow` (every route in passes the node that first leaks the boat).
- `negative_controls` is empty on purpose: WP-1.3 specifies none. Clean books are WP-3.1 and WP-1.5's job.

## Reproducing

From the repository root, load a book as `Storybook.model_validate(json.load(...))`, build `StoryEngine(story)`, walk
the `witnesses[].choices` ids from `engine.start()`, and compare the final `var_state` with `final_state`. The revised
Lighthouse is `out/the-hollow-lighthouse.filled.json` (blob equals `git show 15b14a1:` and is unchanged since); the
pre-revision book is `git show f3ba310:out/the-hollow-lighthouse.filled.json` (the same blob as `15b14a1^`).
