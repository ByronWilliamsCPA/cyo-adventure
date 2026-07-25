# Wyrmreach: 16+ Gamebook Series Design (Two Books, D&D-Style Campaign)

**Date**: 2026-07-25
**Branch**: `claude/dnd-story-game-series-mqr9zy`
**Scope**: A production 16+ **gamebook** (not prose) story built as a two-book, state-carrying series with
Dungeons-and-Dragons-style party progression across the books, left open for later continuations.

This document is the authoring anchor: it fixes the scale cell, the world bible, the party, the state model, the
graph conventions, and the build/verify commands, so books 3+ can be added the same way.

---

## 1. Scale placement (ADR-011)

Both books occupy the cell **(16+, medium, gamebook)**, single-sourced in `validator/band_profile.py`:

| Constraint | Value | Rule |
| --- | --- | --- |
| Node budget | 300-475 | L1-7 (below min warns, above max errors) |
| Max branch depth | 73 hops | L1-7 |
| Words per node | mean 55-110 advisory, **175 hard max** | PL-19 (mean warns, per-node max errors) |
| Fastest satisfying finish | >= 29 nodes | PL-20 |
| Endings floor | `ceil(0.25 * nodes)` | PL-17 (gamebook breadth: few wins, many fails) |
| Decision-node floor | `ceil(0.08 * nodes)` | PL-17 |
| Content ceiling | violence moderate, scariness intense, peril intense | PL-16 |
| Forbidden endings | none at 16+ (lethal outcomes allowed) | PL-15 |
| Reading level | Flesch-Kincaid 9.0 +/- 2.0 | RL-13 (advisory) |

Why medium and not long: `(16+, long, gamebook)` is 475-750 nodes. Medium is the smallest **scale-classified,
production-eligible** 16+ gamebook cell, which keeps each book a genuine full-length gamebook while leaving the
long cell available for a later book in the same chain. Declaring no `length` at all would drop each book to the
band budget (30-60 nodes), which is not a real book.

Both books are **Tier 2** (stateful), `production_eligible: true`, topology `branch_and_bottleneck`, and share
`series_id: wyrmreach` with `carries_state: true`. Book 2 keeps `is_final: false` so the chain stays open (SR-4
permits a non-final top book).

---

## 2. World bible

**The Wyrmreach** is the frontier north of the Ledger cities: dwarf-cut roads gone to moss, an imperial legion
that never came home, and mining charters nobody can enforce. Two powers matter locally: the **Warden-Marshals**,
who hold a thin line of towers and pay in charter and salt, and the **Ledger houses**, merchant orders whose
field-priests keep debts and souls in the same book.

**The Compact** is the frontier's oldest arrangement, and its worst secret. Under the Deep Road sleeps
**Ashendrel**, a wyrm too large to kill and too old to bargain with honestly. The Compact does not slay it; the
Compact *feeds* it, on a schedule, and keeps it sleeping behind the **Ninefold Door** - nine dwarven key-irons,
nine hands, nine oaths. Everything the party is hired to do in book 1 is somebody else's move in that older game.

**Gallowmere** (book 1) is a wet stockade town on the Barrow Moor where the last legion pay-vault, **Kar Duhn**,
was cut into the rock. The garrison's tax-iron never came out. **The Deep Road** (book 2) is the dwarven trunk
road under the mountains, where the Compact's couriers move by lamp-count and the second key waits.

**Tone**: 16+ grim-practical fantasy adventure. Combat is short, ugly, and consequential; failure is usually
attrition, capture, or a bad bargain, and death is on the table. No gore for its own sake, no cruelty as
spectacle.

---

## 3. The party (progression across books)

The reader is the captain of a small free company, **the Ninth Sword**, hired by commission.

| Companion | Role (D&D analogue) | Arc across the chain |
| --- | --- | --- |
| **Dellach Voss** | Warden-sergeant, poleaxe and shield (fighter) | Book 1: takes the front. Book 2: the oath question splits him from the company. |
| **Sister Nyre Ostwyn** | Field-priest of the Reckoning (cleric) | Keeps the company's debts and wounds. Book 2: the Compact is a debt she can read. |
| **Kettle** | Fen-born scout, lockwork and traps (rogue) | The only one who has been under Kar Duhn before, and lies about it. |
| **Ilsabet Crane** | Hedge-thaumaturge, glass-and-salt sigils (wizard) | Recruited in book 1 Act 0; by book 2 she is reading the Door's grammar. |

Progression is mechanical, not just narrative: the company's **renown** buys better terms, better intelligence,
and late-act options that a nameless company cannot reach; **vigor** is the attrition clock that makes the
back half of each book harder if the front half was careless; and the **key-iron** plus the **truth of the
Compact** carry forward as the leverage book 2 opens with.

---

## 4. State model

### Book 1: The Vault of Nine Iron

| Variable | Type | Init | Bounds | Meaning |
| --- | --- | --- | --- | --- |
| `vigor` | int | 5 | 0-6 | Company condition. Hard fights, wounds, and forced marches spend it; rest and Nyre restore it. |
| `renown` | int | 0 | 0-3 | Standing with the Warden-Marshal and the Ledger. Earned by keeping terms. |
| `iron_key` | bool | false | - | The ninth key-iron, lifted from Kar Duhn's pay-hall. |
| `knows_compact` | bool | false | - | The party has read enough to know what the Door actually holds. |

### Book 2: The Sunless March (carried + new)

| Variable | Type | Init | Bounds | Meaning |
| --- | --- | --- | --- | --- |
| `vigor` | int | 5 | 0-6 | Reset by the winter at Gallowmere; spent again on the Deep Road. |
| `renown` | int | 2 | 0-5 | **Carried**: the company that closed Kar Duhn starts known. |
| `iron_key` | bool | **true** | - | **Carried**: the ninth key-iron is in the company's hands from page one. |
| `knows_compact` | bool | **true** | - | **Carried**: book 2 opens already knowing what it is walking toward. |
| `deep_charts` | bool | false | - | New: the dwarven route charts for the lower march. |
| `oath_sworn` | bool | false | - | New: the company swore to the Warden of the Deep Road. |

**Carried-variable rule (finding F3 of the 13-16 stress test)**: a carried variable initializes `true`, so any
condition of the form `<carried_var> == false` is unsatisfiable and a hard **L2-11** dead-branch error. Book 2
therefore contains **no acquisition branch and no `!iron_key` / `!knows_compact` condition**; carried state is
only ever read as already held (a carried-state *gate*), and the `set` effects that acquired it in book 1 are
dropped. Every new acquisition in book 2 is a book-local variable (`deep_charts`, `oath_sworn`).

**Continuity invariant (SR-5)**: every satisfying (`success` / `completion`) ending of book 1 leaves the company
holding the key-iron and the truth, so book 2's declared initials are reachable from any book-1 win. Book 2's
`series_entry_node` is `n_start`: many book-1 wins converge on one book-2 entry.

---

## 5. Graph conventions

Both books are **acyclic** (so L1-7 branch depth is defined and `branch_and_bottleneck` stays admissible under
PL-18) and run a five-act spine with a hard bottleneck between acts:

```text
n_start -> Act 0 (muster)   -> a0_march   -> Act 1 (approach) -> a1_gate
        -> Act 2 (upper vault) -> a2_stair -> Act 3 (deep)     -> a3_door
        -> Act 4 (the Door)  -> wins + terminal failures
```

| Prefix | Meaning |
| --- | --- |
| `n_start` | The opening passage (the only node with no in-edges). |
| `a0_`..`a4_` | Act spine and act rooms, in order. |
| `w0_`..`w9_` | Optional interludes: side rooms, rests, lore, market, shrine. Reconverge to the spine. |
| `e_` | Ending nodes. Ending id is `end_<node_id>`. |
| `c_<node>_<n>` | Choice ids, generated by the builder. |

**Room module** (the repeated gamebook unit, 3-5 nodes deep): a room entry node offers 2-4 approaches
(force / care / cleverness / avoidance); each approach is a short passage that may spend or grant state, may
branch once more, and may end in a failure leaf; survivors reconverge on the room's exit node, which leads to
the next room. Failure leaves are what carry the gamebook's 25% terminal fraction.

**Ending mix per book** (~80 endings): 1 `completion` (the true close that advances the campaign), 3-4 `success`
(wins that do not open the Door correctly), plus `death`, `capture`, `setback`, and `discovery` leaves. Lethal
endings are allowed at 16+ and are earned by specific, telegraphed choices, never by a coin flip.

---

## 6. Authoring pipeline

The source of truth for each book is a compact node **spec** under `data/series/wyrmreach/`; the committed
skeleton and filled story are both compiled from it, so the two can never drift.

```text
data/series/wyrmreach/book1.spec.json    # structure + beats + choice labels + effects
data/series/wyrmreach/book1.prose.json   # node id -> finished prose
        |
        |  scripts/build_series_book.py
        v
skeletons/16+/the-vault-of-nine-iron.json   (bodies are <<FILL role=.. words=.. beats='..'>>)
out/the-vault-of-nine-iron.filled.json      (bodies are prose)
```

Spec node shorthand (expanded by the builder):

| Key | Meaning |
| --- | --- |
| `i` | node id |
| `r` | role (`setup`, `rising`, `choice`, `climax`, `completion`, `failure`, ...) |
| `w` | words target for the FILL directive |
| `b` | beats (the narrative intent the prose must fulfill) |
| `c` | choices: `[label, target]`, `[label, target, condition]`, `[label, target, condition, effects]` |
| `e` | ending: `"kind\|valence\|Title"` |
| `x` | `on_enter` effects |
| `s` | `safety_scope` hints (`peril`, `scary_imagery`, `conflict`, `sad_moment`) |

Condition shorthand: `iron_key` (held), `!iron_key` (not held), `vigor>=3`, `renown>=2`, joined with `&` / `|`.
Effect shorthand: `vigor-1`, `vigor+1`, `renown+1`, `iron_key=true`, comma-separated; a trailing `!` marks an
`on_enter` effect as `once`.

### Commands

```bash
# structural report while authoring (dangling targets, floors, depth, shortest win, word mean)
uv run python scripts/build_series_book.py data/series/wyrmreach/book1.spec.json --check

# compile the skeleton, then the filled story
uv run python scripts/build_series_book.py data/series/wyrmreach/book1.spec.json \
    --skeleton skeletons/16+/the-vault-of-nine-iron.json
uv run python scripts/build_series_book.py data/series/wyrmreach/book1.spec.json \
    --prose data/series/wyrmreach/book1.prose.json --filled out/the-vault-of-nine-iron.filled.json

# gate each artifact, then the chain
uv run python scripts/check_skeleton.py skeletons/16+/the-vault-of-nine-iron.json \
    --band 16+ --length medium --style gamebook --topology branch_and_bottleneck --tier 2
uv run python scripts/run_story_gate.py out/the-vault-of-nine-iron.filled.json
uv run python scripts/build_series_book.py --series out/the-vault-of-nine-iron.filled.json \
    out/the-sunless-march.filled.json
```

---

## 7. Adding book 3

1. Copy `book2.spec.json` as the shape reference and write `book3.spec.json` with new content.
2. Carried variables initialize to book 2's win state (`iron_key`, `knows_compact`, `renown`, plus whichever of
   `deep_charts` / `oath_sworn` book 2's wins guarantee). Read them only as held; never gate on `== false`.
3. Set `series.book_index: 3`, `series_entry_node: n_start`, and clear `is_final` on book 2 only if book 3 closes
   the chain (`is_final: true` is legal only on the top-index book, SR-4).
4. Re-run the chain validator over all three filled books.
