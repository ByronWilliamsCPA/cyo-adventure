# Two threshold decisions: the gamebook endings floor and the configuration ceiling

Written 2026-08-18 for owner ruling on `UW-C291` and `UW-C293`. Every number was measured, not
recalled; the measuring commands are reproducible from the catalog.

## Decision 1: `_ENDINGS_FRACTION["gamebook"]`, currently 0.25

### The evidence, and the thing that reframes it

| source | terminal share | independent of the floor? |
| --- | ---: | --- |
| ADR-011 section 5 assertion | 25-35% | it IS the floor's source |
| 14 committed gamebook skeletons | 27.6% to 33.3%, median 29.8% | **no**, authored under the floor |
| Project Aon Lone Wolf #1, our own crawl | **4.9%** (17 of 350) | yes |
| Story-first gamebook draft, floor not stated | **12.4%** (31 of 250) | yes |

The committed catalog agreeing with the ADR is close to circular: those books were authored while the
floor was in force. The two independent points are 4.9% and 12.4%, and both are far below it.

**Lowering the floor breaks nothing.** All 14 committed gamebooks pass at every candidate below,
because they all sit above 27%. So this is not a grandfathering question at all: it is purely a
question of what ELSE to admit. That is the opposite of the PL-17 and CG-3 decisions, where the
question was what to break.

**The decisive test is the project's own.** `band_profile.py` already states, about PL-25's window:
*"A threshold that blocks pacing the source corpus calls typical, or that blocks a book the corpus
contains, is miscalibrated by construction."* At 0.25 the floor requires 88 endings of Lone Wolf's
350 sections. It has 17. **The current floor rejects the genre's canonical example by 5x.** The
highest floor that admits it is 0.048.

### The options

| # | Option | Lone Wolf | draft (31/250) | committed 14 | character |
| --- | --- | --- | --- | --- | --- |
| A | Keep 0.25 | FAIL | FAIL (needs 63) | pass | Status quo. Fails the project's own miscalibration test. |
| B | 0.045, admit the corpus | PASS | PASS (needs 12) | pass | Principled but near-toothless; a 500-section gamebook with 23 endings would clear it. |
| C | 0.12, admit the expert draft | FAIL | PASS (needs 30) | pass | Splits the difference; still rejects the canonical book, so it fails the same test as A, just less. |
| D | Remove the gamebook floor | n/a | n/a | n/a | Leans on the gamebook positive-ending floor (count 3, share 5%), PL-26 density and the walk floor. Loses the "long book, few endings" guard entirely. |
| E | **Two-tier: block below 0.045, advise below 0.25** | PASS | PASS, advisory | pass, silent | Keeps the craft signal without rejecting the corpus. Mirrors PL-20 and PL-25, which already grade floor and ceiling in two tiers. |

### Recommendation: E

The 25% figure encodes something true about the genre as this project wants to write it, and the 14
committed gamebooks show authors reach it naturally. But a BLOCKING floor that rejects Lone Wolf is
miscalibrated by the standard the codebase already applies elsewhere, and the one independent expert
draft landed less than half of it.

Two tiers separate the two claims cleanly: *below 4.5% this is not a gamebook* (blocking, corpus
grounded), and *below 25% it is unusually ending-light for the genre* (advisory, craft guidance). It
costs one constant and one severity branch, changes no committed verdict, and unblocks the draft.

If E is judged too clever, **B is the honest fallback** and D the honest minimalist one. A and C
should not ship, because both reject the corpus.

## Decision 2: L2-12's reachable-configuration ceiling, currently 100,000

### The evidence

| measure | value |
| --- | --- |
| Skeletons declaring variables | 14 of 133 |
| **Max variable count in the entire catalog** | **4** |
| Largest catalog `nodes x var-space` bound | 30,856 (`the-harrowstone-keep`) |
| Gamebook draft | 11 variables, exceeded 100,000 |
| What 100,000 permits at 250 nodes | ~400 var-states per node, about **9 independent booleans** |

So the ceiling is not absurd: it permits roughly nine booleans at gamebook scale. The draft wanted
eleven (inventory, a wound track, an alarm level, three trust flags), which is modest for the genre
but past the line. And the catalog's own maximum is 4, so nothing committed is near it.

**The cost of raising it is real and lands in the request path.** L2-12 exists so the state space is
PROVEN rather than sampled, and the walk runs inside the gate. A 10x ceiling is a 10x worst-case gate
latency, on a rule whose whole purpose is to be exhaustive.

### The options

| # | Option | Effect | Cost |
| --- | --- | --- | --- |
| A | Keep 100,000 | Gamebooks capped near 9 booleans | None, but a gamebook must choose between state and validation |
| B | Raise to 1,000,000 | ~12 booleans at 250 nodes | Up to 10x worst-case gate latency; the proof stays a proof |
| C | Style-key it: 100k prose, 1M gamebook | Targets the cost at the genre that needs it | Same latency risk, confined to gamebooks; one more style-keyed table |
| D | Sample above a threshold | Any variable count validates | **Changes L2-12 from a proof to an estimate.** The rule's stated purpose is that an unexplored state space is an unproven mutant; sampling retires that guarantee |
| E | **Publish a per-cell variable budget, keep the ceiling** | An author learns the limit before writing | Cheapest of all; does not raise latency, and does not admit more state |

### Recommendation: E now, C if that proves too tight

E is the charter's first principle applied to a limit rather than a bound: the draft spent 16,000
words before discovering the ceiling, which is a communication failure before it is a calibration
one. Publishing the budget costs nothing and may dissolve the problem, since 9 booleans is a real
budget and the writer did not know it existed.

Hold C in reserve. Prefer it to B because the cost should land on the style that needs the headroom,
and because prose stories declare at most 4 variables today so raising their ceiling buys nothing.

**Do not take D.** L2-12's value is that it is exhaustive; a sampled L2-12 still reports a number but
no longer supports the claim it exists to make, and that is the "gate measuring a different quantity
than it advertises" defect this workstream has now found three times.
