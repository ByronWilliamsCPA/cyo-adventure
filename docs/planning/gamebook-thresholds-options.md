# Two threshold decisions: the gamebook endings floor and the configuration ceiling

Written 2026-08-18 for owner ruling on `UW-C291` and `UW-C293`. Every number is measured, and each
row states which command or file produced it.

**Revision note (same day, after adversarial review of the first draft).** Two things in the first
version were wrong, and both were mine:

1. **Decision 2 is withdrawn.** The L2-12 blowup was an artifact of my own converter, not a property
   of the draft. I wrote `"max": 99` on both integer variables; the story's conditions never compare
   either one above 3. Declaring the real bound removes the finding entirely. There is no ceiling
   decision to make.
2. **Decision 1's recommendation changes from E (two tiers) to C (0.12).** The first version rested
   on a single corpus point and did not price the two-tier option against the five other callers of
   `breadth_scaled_floors`. Both corrections are shown below rather than quietly edited out.

## Decision 1: `_ENDINGS_FRACTION["gamebook"]`, currently 0.25

### The evidence

| source | terminal share | provenance | independent of the floor? |
| --- | ---: | --- | --- |
| ADR-011 section 5 assertion | 25-35% | assertion | no, it IS the floor's source |
| 14 committed gamebooks | 27.6% to 33.3%, median 29.8% | measured, `skeletons/` | no, authored under the floor |
| Fighting Fantasy, *Warlock of Firetop Mountain* | ~0.8% (3 of 400) | REPORTED, research note section 4 | yes |
| Project Aon Lone Wolf #1 | **4.9%** (17 of 350) | MEASURED, our 2026-08-02 crawl | yes |
| Story-first gamebook draft, floor not stated | **12.4%** (31 of 250) | measured, this workstream | yes |

The committed catalog agreeing with the ADR is circular: those books were authored while the floor was
in force. Set them aside and three independent points remain, and **they span a factor of fifteen**.
The first version of this document quoted only Lone Wolf and treated 4.9% as *the* corpus value. That
was picking one point from a range and calling it a measurement.

### What makes the points commensurable, and what does not

The two published books are not measuring the quantity our floor measures.

Warlock's 3 and Lone Wolf's 17 both **exclude death by dice**. Both games kill the reader mainly
through a combat or endurance system that resolves outside the section graph, so their graphs carry
only the failures the author chose to make structural. Our format has no dice. Every failure a
diceless gamebook wants must be a terminal node, because there is nowhere else to put it.

So the published shares are a **lower bound on what a diceless book needs**, not a target. Quoting
4.9% at our gate compares a graph that offloads failure to a graph that cannot.

That leaves exactly one commensurable point: the diceless story-first draft, at 12.4%. It is one
observation by one writer, which is thin, but it is thin in the right units.

### A second measurement, which points the same way

Our two styles sit on opposite sides of the corpus and only one of them knows it:

| | our catalog, median | outside corpus | agreement |
| --- | ---: | --- | --- |
| prose | 20.1% (54) | CYOA #53: 19 endings / 115 pages = 16.5%; JHM: median 20 endings over ~90-120 nodes | close |
| gamebook | 29.8% (14) | Lone Wolf 4.9%, Warlock ~0.8% | 6x to 37x apart |

The prose fraction was calibrated against the breadth-form corpus and matches it. The gamebook
fraction was set **above** prose, while the length-form corpus it names sits far **below** prose.
The genre relationship is inverted: time-cave books end often, quest books end rarely. Whatever the
right gamebook number is, it is very unlikely to be the largest number in the table.

### The options

Floors evaluated with `math.ceil(node_count * fraction)`, which is what `breadth_scaled_floors` does.

| # | Option | demands at 250 nodes | Lone Wolf | diceless draft (31/250) | committed 14 |
| --- | --- | ---: | --- | --- | --- |
| A | Keep 0.25 | 63 | FAIL | FAIL, short by 32 | pass |
| B | 0.045, admit the published corpus | 12 | PASS | PASS, 19 spare | pass |
| C | **0.12, admit the diceless draft** | 30 | FAIL | PASS, 1 spare | pass |
| D | Remove the gamebook floor | none | n/a | n/a | n/a |
| E | Two-tier: block below 0.045, advise below 0.25 | 12 or 63 | PASS | PASS, advisory | pass |

Character of each:

- **A** is the status quo and fails the project's own miscalibration test in `band_profile.py`
  ("a threshold that blocks a book the corpus contains is miscalibrated by construction"), though
  see the commensurability caveat above: Lone Wolf is not a book our format could contain.
- **B** admits books that offload failure to a subsystem we do not have. At 500 sections it would
  accept 23 endings. Near-toothless for a diceless format.
- **C** is the only candidate derived from a measurement in our own units. It leaves the draft one
  ending of headroom, which is uncomfortably tight and is an honest cost, not a rounding detail.
- **D** leans on the gamebook positive-ending floor (count 3, share 5%), PL-26 density and the walk
  floor. Loses the long-book-few-endings guard entirely.
- **E** is the option the first version recommended, and it does not survive costing. See below.

### Why E does not survive costing

`breadth_scaled_floors` returns **one** integer, and six call sites consume it:

| caller | what it does with the number |
| --- | --- |
| `validator/policy.py:383` | PL-17, the gate verdict |
| `story_requests/brief.py:250` | the generation prompt's **"EXACTLY N endings"** instruction |
| `scripts/generate_drafting_brief.py:94` | the number published to human authors |
| `scripts/check_skeleton.py:182,683` | the headroom report an author reads while drafting |
| `mutation/operators.py:1656,1670` | the offline mutation acceptance floor |

Two tiers means each of those five non-gate callers must pick a tier, and the prompt is the one that
breaks. If the prompt takes the blocking tier it instructs a 250-node teen gamebook to write
**exactly 12** endings, and the gate then advises that the result is ending-light: we would be
teaching the number we do not want. If the prompt takes the advisory tier it demands 63, the generated
path never approaches the blocking tier, and the block becomes decorative.

This is the prompt-versus-gate divergence Wave 2 (`UW-C278`, `UW-C279`) was opened to close, and E
reopens it by construction. The first version of this document recommended E without stating that it
has five other callers. That was the error.

If two tiers are wanted anyway, the honest form is a second function and an explicit decision at each
call site, not a severity branch inside one. That is a larger change than the number is worth.

### Recommendation: C (0.12)

Grounds, in order of weight:

1. **Commensurability.** The diceless draft is the only corpus point measuring the quantity the floor
   measures. 0.12 is that point.
2. **Direction of error.** If 0.12 is wrong it is wrong by admitting a slightly ending-light gamebook,
   which the positive-ending floor, PL-26 density and the walk floor still constrain. A is wrong by
   rejecting a competently authored book outright, which is the expensive direction.
3. **Cost.** One constant. Changes no committed verdict (all 14 gamebooks clear 0.12 by at least
   15 points). Keeps one number flowing to all six callers.

**The case against C, stated plainly:** the draft clears it by a single ending, so 0.12 is calibrated
to the edge of an n=1 sample. If the next diceless gamebook lands at 11%, we will be back here. The
defensible reading is that 0.12 is *provisional pending a second diceless data point*, and the
register row should say so rather than pretending one draft settled it.

**If C is rejected**, B is the honest minimum-defensible floor and D the honest minimalist. A should
not ship: it rejects the only book anyone has written in our own format by a factor of two.

## Decision 2: L2-12's reachable-configuration ceiling: WITHDRAWN

There is no decision here. The finding was mine.

My converter emitted this for both integer variables:

```json
{"name": "wounds", "type": "int", "initial": 0, "min": 0, "max": 99}
```

The writer never specified bounds. Measuring what the story's conditions actually compare against:

```
wounds: [1, 2, 3]      seen: [1, 2, 3]      (all nine booleans: [true])
```

No condition tests either integer above 3. The declared range was 25x the used range on each of two
variables, inflating the state space by 625x: 512 x 100 x 100 = 5,120,000 against 512 x 4 x 4 = 8,192.

Re-running the gate with `"max": 3` on both, changing nothing else:

| | blocking findings |
| --- | --- |
| `gamebook.json` (`max: 99`) | L2-12, PL-17, PL-20 |
| `gamebook_bounded.json` (`max: 3`) | PL-17, PL-20 |

L2-12 does not merely pass, it disappears. **The 100,000 ceiling was never exceeded by the story.**
It was exceeded by my declaration of the story.

Worse, the gate's own message named the fix and I did not read it: *"state space too large; reduce
variable count **or tighten bounds**"*. All five options I offered varied the ceiling or the
validation method. None of them was the remedy the error prints. The lesson is not about the ceiling;
it is that I proposed changing a threshold before checking whether the input that tripped it was
correct, which is precisely the "reproduce a register row's claim before acting on it" trap.

Two consequential corrections follow:

- **"9 independent booleans at gamebook scale" was wrong too.** That figure divided the ceiling by
  node count, which conflates a product bound with reachable configurations. The draft declares 11
  variables and its reachable set fits under the ceiling with three orders of magnitude to spare once
  the bounds are honest. The ceiling is not close to binding for realistic gamebook state.
- **The tension I recorded in `AL-468(c)` between state richness and validatability is not
  demonstrated.** It should be marked as not reproduced rather than left standing as a finding.

### The real defect this exposed, and a cheap fix

An author (or a converter) can declare `max: 99` on a variable used as a 0-3 counter and pay a 625x
validation cost for nothing, with no signal until the exhaustive walk blows a ceiling thousands of
nodes later. The gate has the information to say so much earlier.

**Proposed new advisory rule (call it L2-15):** when a declared integer variable's range is more than
4x the widest span of any literal its conditions compare against, warn, naming the variable, the
declared range, and the observed thresholds. On this draft it would have fired on `wounds` and `seen`
before the walk ran and pointed straight at the typo. It is a static scan of the condition tree, so it
costs nothing.

This is the same shape as the charter's first principle: the cheapest fix to a limit is usually to tell
the author about it at the moment they cross it, not to move it.
