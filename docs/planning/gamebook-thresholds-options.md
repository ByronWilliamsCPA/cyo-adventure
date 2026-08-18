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

## Decision 2: L2-12's reachable-configuration ceiling, currently 100,000

**Twice-corrected. Read the correction before the options.** The first version of this document said
the draft blew the ceiling and offered five ways to move it. The first correction said the finding
was entirely my converter's and withdrew the decision. **The second correction is that the withdrawal
over-corrected**, and the number I withdrew it on was wrong in the same way as the number I withdrew.

### What is actually true

My converter did emit this for both integer variables:

```json
{"name": "wounds", "type": "int", "initial": 0, "min": 0, "max": 99}
```

The writer never specified bounds, and the story's conditions compare `wounds` and `seen` against
`[1, 2, 3]` and nothing higher. So the declared range was 25x the used range on each of two
variables. Re-running the gate with `"max": 3` and changing nothing else:

| | blocking findings |
| --- | --- |
| `gamebook.json` (`max: 99`) | L2-12, PL-17, PL-20 |
| `gamebook_bounded.json` (`max: 3`) | PL-17, PL-20 |

L2-12 does not merely pass, it disappears. **The claim "a gamebook using ordinary state exceeds the
ceiling" is false.**

But then I wrote that the bounded story fits "with three orders of magnitude to spare", from
`512 x 4 x 4 = 8,192`. That is the *variable* product bound. A configuration is `(node, var_state,
once-visit-set)`, so the node count multiplies in, and reachability decides the rest. Measured, not
derived:

| | configurations |
| --- | ---: |
| variable product bound (2^9 x 4 x 4) | 8,192 |
| product bound x 250 nodes | 2,048,000 |
| **actually reachable** | **99,423** |
| the ceiling | 100,000 |

**The bounded draft fits by 577 configurations, 0.58%.** One more boolean roughly doubles the
reachable set and puts it at ~199,000, over the ceiling.

Two consequences, and neither is what either earlier version said:

- `AL-468(c)`'s tension between state richness and validatability **is real**. It was simply never
  demonstrated by the failure that was offered as its evidence, which was a typo.
- Reachable configurations are **4.9%** of the `nodes x var-space` product here. A budget derived
  from the product bound over-predicts by a factor of ~20, so any variable budget we publish has to
  be measured on real stories, not multiplied out. That cuts against the "just publish the budget"
  option below more than it supports it.

### The cost of raising the ceiling, measured

This is the number the first version guessed at ("up to 10x worst-case gate latency") and it is worth
having exactly, because it decides the question:

| step, on the 99,423-configuration draft | time |
| --- | ---: |
| `walk_configurations` | 4.2s |
| `config_dag` projection (`UW-C292`) | 0.6s |
| `validate_policy` end to end | 7.7s |

And the gate walks the state space **twice** for a story with conditions: once in Layer 2, once in the
policy layer now that PL-20 is state-aware. A 1,000,000 ceiling therefore does not cost "up to 10x
latency" in the abstract; it costs roughly **40 seconds per walk, 80 seconds per gate run**, on the
rule whose entire value is that it is exhaustive.

### The options

| # | Option | Effect | Cost |
| --- | --- | --- | --- |
| A | Keep 100,000 | Gamebook state capped near 11 variables at 250 nodes | None. The draft passes with 0.58% to spare, and the next one that wants one more flag does not |
| B | Raise to 1,000,000 | ~1 more boolean per doubling, ~3 more | ~40s per walk, ~80s per gate run. Not viable in the request path |
| C | Style-key it: 100k prose, 1M gamebook | Same headroom, confined to the style that needs it | Same 80s, confined to gamebooks. Still not viable |
| D | Sample above a threshold | Any variable count validates | **Retires the proof.** An unexplored state space is an unproven story; a sampled L2-12 reports a number that no longer supports the claim it exists to make |
| E | **Keep 100,000, publish a measured budget, and warn on over-declared ranges** | An author learns the limit before writing, and a typo costs a warning instead of 16,000 words | One static check plus a table. Does not raise the ceiling: an author who genuinely needs 12 variables at 250 nodes still cannot have them |

### Recommendation: E, with the limitation stated rather than hidden

The latency measurement rules out B and C: an 80-second exhaustive walk in the gate's request path is
not a trade this project should make for three more booleans. D is off the table for the reason it
was always off the table.

That leaves A and E, and E is A plus the two things that would have saved this draft:

1. **Publish the measured variable budget per cell.** Measured, not multiplied: the 250-node gamebook
   with 9 booleans and two 0-3 counters reaches 99,423 configurations, so "about 11 variables of this
   shape at this scale" is the honest budget. It has to come from walking real stories, because the
   product bound over-predicts by 20x.
2. **Add L2-15 (advisory): warn when a declared integer range exceeds 4x the widest span of any
   literal its conditions compare against**, naming the variable, the declared range and the observed
   thresholds. It is a static scan of the condition tree, it fires before the walk runs, and on this
   draft it would have pointed straight at `wounds` and `seen`. The gate's own L2-12 message already
   says "reduce variable count **or tighten bounds**"; L2-15 says it early and says which variable.

**What E does not fix, stated plainly:** a gamebook author who wants a twelfth variable is still
told no, and the honest reason is that we cannot prove the state space in acceptable time, not that
twelve variables is bad craft. If that becomes a real constraint on real books, the question to
reopen is not the ceiling but whether L2-12 can be made incremental, which is a design question and
not a threshold one.

### The lesson under this, which outlives the decision

`AL-008` recorded exactly this on 2026-07-25: *"declare a carried integer variable's range as what
the continuation can actually reach, not what the variable could theoretically hold"*, against this
same 100,000 cap. Its proposed change was a corrected prose rule. No check was ever built, so 24 days
later the log's own maintainer made the identical mistake. **A lesson whose proposed change is prose
is not yet a lesson learned**, and L2-15 is the check `AL-008` should have produced.

The second-order lesson is about this document. I quoted a derived bound as a measurement twice, in
opposite directions: once to claim the ceiling was too low, once to claim it had orders of magnitude
of headroom. Both times the derived number was available instantly and the measured one took a
30-second script. The rule this earns: **a threshold document may not quote a bound it did not
execute.**
