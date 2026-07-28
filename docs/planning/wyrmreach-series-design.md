# Wyrmreach: 16+ Gamebook Series Design (Three Books, D&D-Style Campaign)

**Date**: 2026-07-25
**Branch**: `claude/dnd-story-game-series-mqr9zy`
**Scope**: A production 16+ **gamebook** (not prose) story built as a state-carrying series with
Dungeons-and-Dragons-style party progression across the books, left open for later continuations. Books 1 and 2
sit in the medium cell; book 3 is deliberately built at the top of the largest cell the matrix allows.

This document is the authoring anchor: it fixes the scale cells, the world bible, the party, the state model, the
graph conventions, and the build/verify commands, so books 4+ can be added the same way.

---

## 1. Scale placement (ADR-011)

Books 1 and 2 occupy **(16+, medium, gamebook)**; book 3 occupies **(16+, long, gamebook)**, which is the
largest cell in the matrix. Both cells are single-sourced in `validator/band_profile.py`:

| Constraint | Books 1-2: medium | Book 3: long | Rule |
| --- | --- | --- | --- |
| Node budget | 300-475 | **475-750** | L1-7 (below min warns, above max errors) |
| Max branch depth | 73 hops | 93 hops | L1-7 |
| Words per node | mean 55-110 advisory, **175 hard max** | same | PL-19 (mean warns, per-node max errors) |
| Fastest satisfying finish | >= 29 nodes | >= 37 nodes | PL-20 |
| Endings floor | `ceil(0.25 * nodes)` | same fraction | PL-17 (gamebook breadth: few wins, many fails) |
| Decision-node floor | `ceil(0.08 * nodes)` | same fraction | PL-17 |
| Content ceiling | violence moderate, scariness intense, peril intense | same | PL-16 |
| Forbidden endings | none at 16+ (lethal outcomes allowed) | same | PL-15 |
| Reading level | Flesch-Kincaid 9.5 +/- 2.5 as declared | same | RL-13 (advisory) |
| Hand-authoring ceiling | n/a | **advisory past 460 nodes** | L2-13 (warning, never blocks) |

Why books 1-2 are medium: medium is the smallest **scale-classified, production-eligible** 16+ gamebook cell,
which keeps each book a genuine full-length gamebook while leaving the long cell available for a later book in
the same chain. Declaring no `length` at all would drop a book to the band budget (30-60 nodes), which is not a
real book.

Why book 3 is long, at 746 of 750 nodes: it is the deliberate ceiling test of the matrix. Past 460 nodes L2-13
fires a permanent advisory saying that the completed Layer-2 configuration walk, not human review, is the sole
correctness guarantee for the story. That warning is the expected and correct output at this scale, not a defect;
it is the only finding book 3 produces.

All three books are **Tier 2** (stateful), `production_eligible: true`, topology `branch_and_bottleneck`, and
share `series_id: wyrmreach` with `carries_state: true`. Book 3 keeps `is_final: false` so the chain stays open
(SR-4 permits a non-final top book).

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

**Kar Ashen** (book 3) is the third door's city, and the reason the Compact has held for nine hundred years.
It is not a ruin and not a cult: it is a working municipality of four thousand people, inside the mountain, at
the top of the **Ninefold Road** up the spine of the Wyrmreach. It has a mint, an aqueduct, a bone registry, a
surgeon, a lamp rota, an arrears auction, and a chapel whose evening office is arithmetic. Every institution in
it is competent, legal by its own charter, and load-bearing for the count that keeps Ashendrel asleep. The
**crown door** at the top of the city is the ninth door with nine sockets, eight of them filled; the ninth hand
is a vacant office with a nine-year term and a start date this spring, and the city is expecting somebody to
take it. Book 3's horror is bureaucratic, not monstrous: nothing in Kar Ashen is hiding, and everything in it
adds up.

**Tone in book 3**: the same grim-practical register, with the pressure moved from danger to complicity. The
company can force any door in the city and still lose, because the thing it is up against is a schedule that
other people depend on.

**Tone**: 16+ grim-practical fantasy adventure. Combat is short, ugly, and consequential; failure is usually
attrition, capture, or a bad bargain, and death is on the table. No gore for its own sake, no cruelty as
spectacle.

---

## 3. The party (progression across books)

The reader is the captain of a small free company, **the Ninth Sword**, hired by commission.

| Companion | Role (D&D analogue) | Arc across the chain |
| --- | --- | --- |
| **Dellach Voss** | Warden-sergeant, poleaxe and shield (fighter) | Book 1: takes the front. Book 2: the oath question splits him from the company. Book 3: he is the one the vacant ninth-hand office actually fits. |
| **Sister Nyre Ostwyn** | Field-priest of the Reckoning (cleric) | Keeps the company's debts and wounds. Book 2: the Compact is a debt she can read. Book 3: her own order is a party to it, and the hearing at Sarnhold is hers. |
| **Kettle** | Fen-born scout, lockwork and traps (rogue) | The only one who has been under Kar Duhn before, and lies about it. Book 3: a mint floor and a shift roll turn his trade into a record. |
| **Ilsabet Crane** | Hedge-thaumaturge, glass-and-salt sigils (wizard) | Recruited in book 1 Act 0; by book 2 she is reading the Door's grammar. Book 3: she reads the crown ledger's tenth column before anybody else does. |

Progression is mechanical, not just narrative: the company's **renown** buys better terms, better intelligence,
and late-act options that a nameless company cannot reach; **vigor** is the attrition clock that makes the
back half of each book harder if the front half was careless; and the **key-iron** plus the **truth of the
Compact** carry forward as the leverage book 2 opens with, then book 3.

By book 3 the carried state is the point rather than the reward: two irons and the truth of the Compact make the
company the only party on the frontier that can take the crown iron, and therefore the only party the city has a
use for.

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

### Book 3: The Ninth Hand (carried + new)

| Variable | Type | Init | Bounds | Meaning |
| --- | --- | --- | --- | --- |
| `vigor` | int | 5 | 0-6 | Reset by the winter at Sarnhold; spent again on the Ninefold Road and inside the city. |
| `renown` | int | 3 | **3-5** | **Carried**: the company that shut two doors. Floor raised to the initial so the carried standing can never be spent below it. |
| `iron_key` | bool | **true** | - | **Carried**: the ninth key-iron of Kar Duhn. |
| `second_iron` | bool | **true** | - | **Carried**: the relay iron of Hollowmarch. |
| `knows_compact` | bool | **true** | - | **Carried**: the company knows what the doors hold. |
| `crown_iron` | bool | false | - | New: the crown iron off the rack in the socket chamber. |
| `wyrm_pact` | bool | false | - | New: terms accepted directly from Ashendrel. |
| `door_state` | int | 0 | 0-6 | New: what the company did to the crown door, which the act 6 endings read. |

`renown` is deliberately declared **min 3, max 5** rather than 0-5. At 746 nodes the Layer-2 walk enumerates one
configuration per reachable (node, variable-state) pair, so every value an integer variable can take multiplies
the walk. Narrowing a carried counter to the range the continuation can actually reach keeps book 3 at 36,781
configurations against the L2-12 cap of 100,000, and it is also the truthful model: a company that shut two
doors does not become unknown.

**Continuity invariant (SR-5)**: every satisfying (`success` / `completion`) ending of book 1 leaves the company
holding the key-iron and the truth, so book 2's declared initials are reachable from any book-1 win. Book 2's
`series_entry_node` is `n_start`: many book-1 wins converge on one book-2 entry. Book 3 repeats the pattern one
level up: its initials are exactly what book 2's completion ending (*The Second of Nine*) leaves behind.

---

## 5. Graph conventions

All books are **acyclic** (so L1-7 branch depth is defined and `branch_and_bottleneck` stays admissible under
PL-18). Books 1-2 run a five-act spine with a hard bottleneck between acts:

```text
n_start -> Act 0 (muster)   -> a0_march   -> Act 1 (approach) -> a1_gate
        -> Act 2 (upper vault) -> a2_stair -> Act 3 (deep)     -> a3_door
        -> Act 4 (the Door)  -> wins + terminal failures
```

Book 3 runs the same shape over seven acts, sized to the long cell (99 / 110 / 108 / 112 / 119 / 122 / 76 nodes):

```text
n_start -> Act 0 (Sarnhold)      -> Act 1 (the Ninefold Road)  -> Act 2 (crown gate and wards)
        -> Act 3 (the counted city) -> Act 4 (the wyrm-road)   -> Act 5 (the socket ring)
        -> Act 6 (the crown door, the escape, the reckoning)   -> wins + terminal failures
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

**Room shapes (book 3)**: at 746 nodes the room module was formalised into six reusable shapes, so the act
structure could be generated and the *content* authored on top of it rather than both at once. Each shape is a
node count plus a label count plus a fixed wiring:

| Shape | Nodes / labels | Wiring |
| --- | --- | --- |
| `fork` | 6 / 8 | Entry offers three approaches; two branch once more; one failure leaf. |
| `monster` | 6 / 8 | Entry, three approaches, two failure leaves (one fatal, one costly). |
| `trap` | 4 / 5 | Entry, two approaches, one failure leaf. |
| `social` | 4 / 5 | Entry, two lines of questioning, one leaf that closes a door socially. |
| `loot` | 4 / 6 | Entry, take / read / leave, one leaf that costs the take. |
| `lore` | 3 / 4 | Entry, two readings, no leaf (reconverges). |
| `rest` | 2 / 3 | Entry, spend time or move on; grants `vigor`. |

Rooms hang as parallel chains off an act hub and reconverge on the act gate, which is what keeps depth at 74 of
93 while the node count is at the top of the cell: breadth, not length, is what a ceiling-scale gamebook needs.

**Ending mix**: 1 `completion` per book (the true close that advances the campaign), a handful of `success`
(wins that do not resolve the door correctly), plus `death`, `capture`, `setback`, and `discovery` leaves.
**Breadth must reconverge, not terminate** (the correction of 2026-07-25, AL-026). Book 3 was first
built with breadth paid for in terminal failure leaves, at the same per-choice termination density as
book 1 (~22.5%). Because it had 2.4x the nodes, that made the *typical* read shorter, not longer:
a median of 5 pages and 302 words of a 42,085-word book, with 7 endings within two taps of the start.
The fix was to convert the 45 shallowest failure leaves into **pass-through nodes**: the authored
failure prose stays, the node costs `vigor` on entry, and the route rejoins the room's continuation.
Median read went to 20 pages and 1,154 words, and the share of endings a reader actually reaches went
from 39% to 56%. The rule for any future ceiling-scale book: a room should more often cost something
and rejoin than end the run, and terminal leaves belong in the endgame acts where lethality is earned.

Note the standing tension: PL-17's endings floor (`ceil(0.25 * nodes)` = 187 here) actively pushes a
gamebook author toward terminal leaves, and book 3 now sits exactly on that floor with no headroom
left. The floor's shape is worth revisiting (AL-026).

Book 3 lands at 187 endings: 1 completion, 6 success, 2 discovery, 51 setback, 34 capture, 93 death. Lethal
endings are allowed at 16+ and are earned by specific, telegraphed choices, never by a coin flip.

---

## 6. Authoring pipeline

The source of truth for each book is a compact node **spec** under `data/series/wyrmreach/`; the committed
skeleton and filled story are both compiled from it, so the two can never drift.

```text
data/series/wyrmreach/book1.spec.json    # metadata, variables, and an `include` list of act parts
data/series/wyrmreach/book1.a0..a4.json  # structure + beats + choice labels + effects, one file per act
data/series/wyrmreach/book1.prose.a0..a4.json   # node id -> finished prose, one file per act
        |
        |  scripts/build_series_book.py
        v
skeletons/16+/the-vault-of-nine-iron.json   (bodies are <<FILL role=.. words=.. beats='..'>>)
out/the-vault-of-nine-iron.filled.json      (bodies are prose)
```

The spec's `include` list resolves relative to the spec file, and `--prose` is repeatable and merged in order, so
a book is authored one act at a time and compiled as a whole. Book 3 is seven act parts and seven prose parts.

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

**Never use `once`.** The Layer-2 walk's configuration key includes the set of visited nodes that carry a `once`
effect, so a single `once` effect multiplies the config space by two and does it again for every additional one.
In an acyclic graph `once` is redundant anyway, because no node is entered twice on a path.

### Reading level

All three books declare `reading_level` Flesch-Kincaid **9.5 +/- 2.5**, and every filled node lands inside it.
Flesch-Kincaid is dominated by words per sentence, so at a fixed ~60 words the same content scores near FK 5 in
four or five sentences, FK 9-11 in three, and FK 13+ in two. The practical authoring rule is **three sentences
per passage, roughly 20 words each**. An outlier can be retuned without rewriting a word: join two sentences with
`; ` or `, and ` to raise the grade, split one at a coordinating boundary to lower it.

### Commands

```bash
# structural report while authoring (dangling targets, floors, depth, shortest win, word mean)
uv run python scripts/build_series_book.py data/series/wyrmreach/book1.spec.json --check

# compile the skeleton and the filled story in one pass (the skeleton stays the FILL form)
uv run python scripts/build_series_book.py data/series/wyrmreach/book3.spec.json \
    $(for a in a0 a1 a2 a3 a4 a5 a6; do echo --prose data/series/wyrmreach/book3.prose.$a.json; done) \
    --skeleton skeletons/16+/the-ninth-hand.json --filled out/the-ninth-hand.filled.json

# gate each artifact, then the chain
uv run python scripts/check_skeleton.py skeletons/16+/the-ninth-hand.json \
    --band 16+ --length long --style gamebook --topology branch_and_bottleneck --tier 2
uv run python scripts/run_story_gate.py out/the-ninth-hand.filled.json
uv run python scripts/check_fill_integrity.py skeletons/16+/the-ninth-hand.json \
    out/the-ninth-hand.filled.json
uv run python scripts/build_series_book.py --series out/the-vault-of-nine-iron.filled.json \
    out/the-sunless-march.filled.json out/the-ninth-hand.filled.json
```

---

## 7. Adding book 4

1. Copy `book3.spec.json` as the shape reference (or `book2.spec.json` for a medium-cell book) and write
   `book4.spec.json` with new content and its own `include` list of act parts.
2. Carried variables initialize to book 3's win state (`iron_key`, `second_iron`, `knows_compact`, `renown`, plus
   `crown_iron` if book 4 assumes the crown iron was kept). Read them only as held; never gate on `== false`, and
   never place a gate on a new variable earlier in the graph than the first node that grants it: both are hard
   L2-11 dead branches.
3. Narrow every carried integer variable's declared range to what the continuation can actually reach, or the
   Layer-2 walk will spend its 100,000-configuration budget on states no reader can be in.
4. Set `series.book_index: 4`, `series_entry_node: n_start`, and set `is_final: true` only if book 4 closes the
   chain (`is_final: true` is legal only on the top-index book, SR-4).
5. Re-run the chain validator over all four filled books.

The next hook is already written: book 3's completion ending (*The Third of Nine*) names the six remaining doors
in order with dates against each, and puts the nearest of them in Sarnhold's own chapel.
