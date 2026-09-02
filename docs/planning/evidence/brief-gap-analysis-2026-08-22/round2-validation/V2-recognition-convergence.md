# V2 adversarial validation: the recognition-protocol control failure

Target: gap-analysis section 1.2 ("The catalog is convergent across different graphs in different
worlds"); prior findings C3-2, C3-3, C3-8.
Question: does the control failure mean the INSTRUMENT is broken (brief's reading) or the CATALOG IS
CONVERGENT (review's reading)?

Everything below was re-derived from committed artifacts. Commands and outputs are inline so each
number can be re-run.

---

## THE CRUX FIRST: how the raters were actually run

**`protocol.py` runs no raters.** It is a prompt builder, a blinding rule, a BFS reading-order
definition, and a verdict validator. There is no model call, no model id, no rater harness anywhere
in the file. So the answer is not in `protocol.py`; it is in `results.md` lines 7-10 and register row
`S-0`, and it is worse than the review assumed and better than the strongest counterargument
assumed.

`results.md` provenance block:

> All six raters are model raters: independent, blind subagent sessions of the serving frontier
> model (session model id `claude-fable-5`), one prompt each, no repo access, no knowledge of arms
> or of the experiment.

Register `S-0` design: *"two counterbalanced raters per pair (rater A reads C then D, rater B reads D
then C)"*. `results.md`'s table column is headed **Order**.

So `r1`/`r2` are **both at once, and fully confounded**:

- **Same model.** One model (`claude-fable-5`), six separate subagent sessions. Not two raters in
  any psychometric sense: same weights, same priors, same failure modes. Agreement between them is a
  *self-consistency* measurement, not independent replication. Correlated error is guaranteed, not
  possible.
- **Different sessions AND different orderings, never separated.** The design varies rater identity
  and presentation order together, so nothing in this data can attribute agreement to either.
- **Worse: they did not rate the same stimulus.** Verified from the verdict files,
  `verdict_ctrl-..._r1.json` has **95** `per_scene` entries, `_r2.json` has **26**. r1 read
  clocktower (26) then museum (95); r2 read museum (95) then clocktower (26). Book Two differs, so
  the "first-yes position" is a different quantity in each. 41-of-95 and 12-of-26 are not two
  readings of one measurement; they are two different tasks that happened to return the same binary
  label.
- **Independence is asserted, not evidenced.** `git log --diff-filter=A` on the pilot directory
  shows only `README.md` + `protocol.py` (2026-08-15) and six verdict JSONs + `results.md`
  (2026-08-21). **No prompts, no transcripts, no session ids were committed.** The blinding and
  isolation claims are unverifiable from the artifact. (`AL-185`/`AL-231` already established that
  this programme has previously had to downgrade a run to "author-scored" for exactly this reason.)

**Net effect on claims 1 and 2:** "both raters agreed" must be restated as *"one model, run twice on
two different orderings of the same two books, returned the same binary label."* That is materially
weaker than the gap analysis implies. It is not worthless, the order manipulation is real and the
verdicts survive `protocol.py validate`, but it cannot carry a claim of independent convergence.

**The important consequence, which cuts the other way:** the convergence finding does **not need the
raters at all**. See claim 2 and "What everyone missed", it is deterministically verifiable from the
committed artifacts, and there it is stronger.

**One further defect nobody has named.** The "sequential commitment" is fictional. It is a
single-prompt protocol (declared in the docstring): the model reads all 95 Book Two scenes, then
writes the `per_scene` array. It never committed at scene 41; it reconstructed post hoc where
recognition "would have" landed. `first_yes_position` is therefore not a measured commitment
position. This matters directly: `results.md`'s repair item 2 (a symmetric position-bounded firing
rule) and register rows `S-2`/`S-4` (falsifiers keyed on "at or before position 4") are all
pre-registered on a quantity the single-prompt design does not measure.

---

## Claim 1: the control pair was 26 vs 95 nodes, different graphs, different worlds, same band; both raters `same_adventure: yes`, distinctness 2/5, first-yes 41 and 12

**Verdict: numbers CONFIRMED; the framing "different graphs, different worlds" is REFUTED as a
known-different property.**
**Severity: high** (the framing is what licenses reading the result as a catalog measurement).

**What I did to break it.** Pulled both books' metadata; traced the clocktower book's provenance
through its contract; read both skeletons' lineage records; then computed `structural_distance`
across every pair in the 10-13 catalog to locate this pair in the catalog's own similarity
distribution.

**Evidence.**

Verified as stated: 26 vs 95 nodes; both `same_adventure: yes`; both `distinctness_1_to_5: 2`;
`first_yes_position` 41 and 12; `per_scene` lengths 95 and 26.

What the framing hides, the two books are near-twins on every catalog axis except world:

| | clocktower (`filled_C`) | museum (`book-s`) |
| --- | --- | --- |
| source skeleton | `the-clocktower-cipher` (via `contract_C.json` `skeleton_slug`) | `the-midnight-museum` |
| age band | 10-13 | 10-13 |
| reading level | FK 5.5 ± 1.5 | FK 5.5 ± 1.5 |
| tier | 1 | 1 |
| topology | `branch_and_bottleneck` | `branch_and_bottleneck` |
| themes | mystery, puzzles, **friendship**, history | mystery, puzzles, **courage**, history |
| content flags | violence none, scariness mild | violence none, scariness mild |

Three of four themes shared, same topology class, same band, same tier, same reading target. And the
mutation pilot's own README names them as **rival candidates for the same match cell**: it selected
`the-midnight-museum` from `candidates_for_cell("10-13","short","prose")` and records
*"`the-clocktower-cipher` was excluded as instructed (off-matrix seed, `production_eligible: false`)"*.
These are two entries considered for one slot.

**The decisive new number.** I computed `structural_distance` for all 105 pairs of 10-13 catalog
skeletons:

```text
n skeletons 15, pairs 105
min 0.064 | p05 0.1239 | median 0.39
6 most similar: 0.0640 lighthouse/museum · 0.0756 flooded-quarter/wolf-queen ·
  0.0802 envoy/skyrail · 0.0831 cartographers/orchard · 0.1094 cinderwick/envoy ·
  0.1239 clocktower-cipher/midnight-museum
=> the control pair ranks 6 of 105, the 5.7th percentile
```

**The negative control was drawn from the extreme similar tail of the catalog's own distribution.**
Five 10-13 pairs are structurally more similar still. Calling that "different graphs, different
worlds" is technically true and materially misleading.

**Where the framing survives:** ancestry is genuinely independent.
`skeletons/10-13/the-clocktower-cipher.lineage.json` reads `origin: "fresh"`, `parent_slug: null`,
`donor_slugs: []`, `op_chain: []`, `generator: "hand-authored:v1"`. There is no graft, no mutation,
no shared parent. So the similarity is **convergence, not descent**, which is the review's point,
arrived at properly. (Caveat: git history is squashed; both skeletons enter in one commit, so
whether they shared an authoring session is unrecoverable. "Independently authored" is a lineage
claim, not a process-independence claim.)

**What the prior review missed.** C3-2 and gap-analysis 1.2 both present "different graphs,
different worlds" as though it establishes a known-different pair. It does not. The pair is at the
5.7th percentile of catalog similarity and shares band, tier, topology, reading level, and 3 of 4
themes. The prior review never located the pair in the distribution it was arguing about, and the
distribution was computable in seconds from committed files.

---

## Claim 2: the raters independently named the same specific causal chain

**Verdict: SUBSTANCE CONFIRMED and strengthened; the word "independently" is REFUTED.**
**Severity: medium** (a correction that makes the underlying claim stronger, not weaker).

**What I did to break it.** Assumed the shared chain was a shared hallucination of one model seeing
one pair of texts twice, and tried to verify the chain against the artifacts with no rater in the
loop, dumping non-ending node ids and ending titles from both books.

**Evidence.** The chain is real and needs no rater:

```text
CLOCKTOWER (26): n_note · n_stairs n_study n_pendulum n_basement · n_clockface ->
                 n_setcorrect / n_setjam · n_backpanel · n_vault
  endings: The Jammed Dial | The Living Workshop | The Settlement's Praise |
           The Study's Archive | Footprints in the Silt

MUSEUM (95):     n_cipher · ci_stars ci_map ci_clock · k_display ->
                 k_display_careful / k_display_force · k_founder · n_vault
  endings: The Jammed Globe | The Hidden Workshop | The Whole Truth |
           Keeper of the Letter | A Secret Among Friends | Caught Red-Handed |
           Under the Pendulum
```

Element for element: cipher node ↔ cipher node; rooms-off-a-hub-teaching-pieces ↔ same; set-exactly
vs force-and-jam ↔ same, down to **"The Jammed Dial" / "The Jammed Globe"**; hidden space behind a
panel ↔ **"The Living Workshop" / "The Hidden Workshop"**; maker's letter in a strongroom ↔
`n_vault` / "Keeper of the Letter"; tell / keep-secret / caught-taking ↔ "The Settlement's Praise" /
"A Secret Among Friends" / "Caught Red-Handed". Both books even carry a pendulum.

So the raters described something true. But "independently" is wrong in the only sense that matters:
one model, two sessions, the same two texts, asked the same question. Convergent free text under
those conditions is the expected output, not corroboration.

**What the prior review missed.** C3-2 rests the convergence claim on the rater free text and
corroborates it by *inspection* as a secondary check. The ordering should be inverted. The
artifact-level evidence is primary, deterministic, and immune to every objection about rater
independence, model identity, prompt leading, or order effects. Stated from the artifacts, the claim
survives the strongest available counterargument intact; stated from the raters, it does not.

---

## Claim 3: `results.md` line 51 concedes the chain is really there

**Verdict: CONFIRMED, verbatim.**
**Severity: n/a.**

Line 51: *"The clocktower book and the museum book do substantially contain that chain."* Lines
52-57 go further than the gap analysis quotes: *"This is the programme's own catalog-convergence
finding (D-6 idiom floor, Q-3c premise mode) appearing inside a 'different graph, different world'
pair. The re-based control may therefore not be a valid negative control at all: within one band,
two catalog-lineage mysteries can genuinely be the same adventure at the decision level."*

The concession is fuller in the source than in either the brief or the gap analysis. `AL-511`
carries it too ("Defect one: a same-band catalog-lineage pair is convergence-bearing"). Nothing was
hidden; it was recorded and then not propagated upward.

---

## Claim 4: the pilot is better read as a positive measurement of catalog convergence than as a failed instrument; the brief understates its own evidence

**Verdict: SPLIT. The "positive measurement" reading is REFUTED as stated. "The brief understates
its evidence" is CONFIRMED, but the understated evidence is deterministic, not perceptual.**
**Severity: high.**

**What I did to break it.** Attacked from three directions: (a) does the instrument discriminate any
pair at all; (b) is the control length-biased; (c) does the convergence conclusion need the pilot.

### (a) The instrument has never once said "different": this is fatal to the claim as stated

All six automated verdicts are `same_adventure: yes`. Going back through the manual history in
`cyo-framework-problem-and-structures-2026-08-10.md` section 5.1 and the register:

| Layer varied | Recognition outcome |
| --- | --- |
| Devices (S5) | same book, unmoved |
| Prose (S6) | same book, unmoved |
| Model tier (S7) | same book, 2.5 at both craft extremes |
| Obligations (S9) | same book, **position 2** (margin was "past position 5") |
| Graph shape / mutants (S8) | same book, position 3 |
| 3-5 pilot / B-plus 10-13 pilot | same book, 2.5 / 2.0, node 2 of 26 |
| **S-0, all six automated verdicts** | **same book, 2 / 2 / 2 / 2 / 12 / 41** |

`grep -i recogni docs/planning/diversity-test-register.md` surfaces no recorded run in which any
rater, manual or automated, returned "different adventure". **Across the entire programme the
recognition instrument has a 100% same-adventure rate on every pair it has ever been shown.**

An instrument with no observed negative has an undefined false-positive rate. A "yes" from it is not
a measurement of anything, it is the only output it has ever produced. You cannot read this "yes"
as a positive measurement of convergence for the same reason you cannot read a thermometer stuck at
100°C as evidence the room is hot. **This is the single strongest argument against claim 4 and the
prior review does not engage it.**

### (b) The control was biased toward firing by construction, in a way results.md missed

`results.md` identifies one asymmetry (position-bounded for known answers, unbounded for the
control). There is a second, and it is bigger: **the firing criterion is a function of Book Two
length.** Under "unbounded, must never fire", a rater gets one chance per Book Two scene and may
never revise. The control's Book Two was **95 scenes** for r1 against **26** for every known-answer
pair, 3.7x more opportunities to fire. Combined with (a), a length-biased unbounded criterion
applied to the longest Book Two in the pilot, on a pair sitting at the 5.7th percentile of catalog
similarity, is close to a guaranteed failure. Note too that the counterbalancing cannot rescue this:
with unequal book sizes the two orderings are not symmetric tasks, so the design has no valid
counterbalance available.

**So yes, choosing this control is an instrument-design failure, and a compound one.** The brief's
reading is right on the mechanism. Three independent design defects (band substitution, length bias,
selection from the similar tail) all point the same way.

### (c) But the brief does understate its evidence: on a different axis

The brief's section 4.4 gives the whole thing one subordinate clause: *"partly because the control
itself carried the catalog's convergent decision structure"*, filed under "Does not work"
(instruments). `grep converg` shows the word appears nowhere else in the brief in connection with
the catalog's own graphs. Sections 1 and 5 carry no catalog-convergence finding at all.

That is an understatement, but the evidence that is being understated is **not the rater verdicts**.
It is this, which I computed and nobody in this programme has:

```text
structural_distance over the four committed FILLED 10-13 books
  0.0640  museum   vs lighthouse
  0.1239  clocktower vs museum
  0.1384  lighthouse vs mapmakers
  0.1405  clocktower vs lighthouse
  0.1793  museum   vs mapmakers
  0.2424  clocktower vs mapmakers
TAU_STRUCT = 0.298321  (ws5_floor_baseline.json: "the cross-tree diversity target
                        for independently authored trees", p25 of 145 same-cell pairs)
```

**Every one of the six pairs of finished, child-ready 10-13 books in this repo is below the
programme's own cross-tree diversity target, by 1.2x to 4.7x.** No rater, no model, no perceptual
claim, no instrument that failed validation. This is the catalog-convergence finding stated in the
one evidence class the brief already trusts (F6: deterministic instruments only), and it is far
stronger than anything the pilot can supply.

**Verdict on claim 4.** Re-filing the pilot as "evidence about the catalog" is the wrong repair,
because the pilot's rater layer cannot bear that weight and the brief is correct to distrust it.
The right repair is to file the *deterministic* catalog result as a finding in section 1, and leave
the pilot exactly where the brief has it. The review reached a correct conclusion (the catalog is
convergent) via the one piece of evidence that cannot support it, while a decisive deterministic
version sat uncomputed in the repo.

**What the prior review missed.** That the instrument has never emitted a negative in the programme's
entire history; that the unbounded criterion is length-biased and the control was the longest Book
Two run; and that the convergence claim had a deterministic proof available at zero cost.

---

## Claim 5: the pair scores 2.2 grams/1000 (below the 3.3 idiom floor), structural distance 0.1239, and passes the anti-template guard at 0.925 with 0/26 flagged; all three surviving instruments call it maximally distinct

**Verdict: REFUTED on two of three sub-claims. The corrected finding is sharper and names a live,
fixable misconfiguration.**
**Severity: critical.**

**What I did to break it.** Ran all three instruments on the control pair myself.

**Evidence, instrument by instrument.**

**1. Shared 4-grams, number CONFIRMED, interpretation weakened.**
```sh
$ uv run python scripts/check_sibling_fills.py \
    docs/planning/evidence/d7-stratified-plan/filled_C.json \
    docs/planning/evidence/mutation-per-request-pilot/book-s-the-midnight-museum.json
shared 4-grams across 2 fills: 12 (2.2 per 1000 mean leaf words; budget 4.0)
menu frames shared by 2+ fills: 0
```
The 12 grams are pure idiom ("one at a time", "for the first time", "the rest of the"). But
*sub-floor is uninformative, not a false negative*: the register's own D-7b row says a below-floor
reading means the arm *"cannot be distinguished from two books sharing nothing but the model and the
age band ... at the measurement's own noise floor"*. The gate passes it, so the **gate** false-
negatives; the **measure** correctly reports "no signal". A metric that measures verbatim overlap is
not wrong to report near-zero verbatim overlap on a pair that shares no wording.

**2. Structural distance, number CONFIRMED, claim FLATLY REFUTED.**
```text
structural_distance(clocktower_C, museum_S) = 0.12393815065501611
ws5_floor_baseline.json / same_cell_structural:
  min 0.000469 | p05 0.154657 | p25 (TAU_STRUCT) 0.298321 | median 0.379906 | n=145
```
**0.1239 is BELOW the 5th percentile of hand-authored same-cell pairs and 2.4x below TAU_STRUCT.**
Structural distance does not call this pair maximally distinct. It calls it **more structurally
similar than roughly 95% of independently authored same-cell pairs**, it *agrees with the raters*.
The only thing that "passes" is `TAU_CELL = 0.05`, which the baseline's own `clamps` field describes
as an **anti-duplication floor** ("it rejects the observed same-cell minimum pair at 0.000469 with
margin"). TAU_STRUCT was demoted to "DOCUMENTATION ONLY" because it mis-applied a sibling-pair
percentile to *mutant parent distance*, a narrow, correct fix, but it remains the baseline's
stated cross-tree target for exactly this kind of pair, and nothing applies it.

This is not an instrument false negative. **It is a threshold misapplication: the programme is
gating cross-tree diversity with a duplicate detector while its own documented cross-tree target
sits unused in the baseline file.** That is a live, cheap, fixable defect, and it is a better finding
than the one claimed.

**3. Anti-template guard, the number does NOT belong to this pair. REFUTED.**
```pycon
>>> anti_template_verdict(clocktower_C, museum_S, ...)
ValidationError: anti_template_verdict requires two fills of the same structure
                 (cross-tree pairs are not comparable node-by-node)

>>> anti_template_verdict(d7b_C, d7b_D, ...)
verdict=PASS_ median_distance=0.9254629629629629 p25=0.8893939393939394
templated_nodes=() node_count=26
```
**0.925 / 0-of-26 is the `d7b-bare-names` C-vs-D pair, not the control pair.** The ATG cannot run on
the control pair at all. C3-3's table has this right, its ATG cell for the control reads
*"undefined (raises on cross-tree pairs)"*, and the error was introduced when gap-analysis 1.2
compressed C3-3's two-column table into one sentence beginning "The same pair". This is a factual
error in the synthesis that a reviewer can catch in one command.

**4. Solution transfer, not run.** C3-3 records it as "not computable" for this pair (needs a
narrative contract). So of the brief's three named surviving instruments (solution transfer, shared
4-grams, structural distance), **only two were run, and the ATG is not one of the three.**

**Corrected statement of the finding.** Not "all three surviving instruments call it maximally
distinct". Rather:

> On a pair two model raters merge: the verbatim-overlap measure correctly reports no signal and the
> gate therefore passes it; structural distance correctly reports the pair as more similar than 95%
> of same-cell pairs, but is gated against an anti-duplication floor 6x below its own documented
> cross-tree target, so it passes too; the anti-template guard cannot run; and solution transfer
> needs an artifact the pair lacks. **One of four is a genuine gate false negative; one is a
> misconfigured threshold; two do not apply.**

**What the prior review missed.** That structural distance is on the raters' side of this argument.
The false-negative framing gave up a working instrument. The actual defect is smaller, more specific,
more embarrassing, and fixable this week.

---

## Claim 6 (C3-8): every instrument is anchored only at the "similar" end, with a re-theme as the known-different anchor

**Verdict: CONFIRMED, and sharpened.**
**Severity: high.**

**What I did to break it.** Read `tests/data/diversity_panel/panel.json` directly, looking for any
genuinely-different anchor.

**Evidence.**
```text
atg_pairs:
  cave-sea    / cave-space            expected: pass
  cave-sea    / cave-dino             expected: pass
  cave-space  / cave-dino             expected: pass
  skyship     / skyship-submarine     expected: pass
  cave-space  / cave-space-swap       expected: fail
  cave-space  / cave-space-identical  expected: fail
```
Exactly as C3-8 states: both `fail` anchors are a copy and a noun swap; all four `pass` anchors are
re-themes of one skeleton. The CI gate's operational definition of "acceptably different" is a
re-theme, which is precisely the artifact class every rater in this programme's history has merged.
Corroborated for the other instruments: TAU_CELL set to reject the observed minimum (bad end only);
the 3.3 gram floor derived from "books sharing nothing but the model and the age band" (a generator
lower bound, not a known-different artifact); solution transfer validated on three constructed
known-bads at 1.000/1.000/0.700 with no known-good; `AL-244` says of the branch-obligation checker,
in the programme's own words, *"it was validated on two known-bad pairs with no known-good example,
so it is a screen rather than an arbiter and its threshold is uncalibrated."*

**Sharpening.** Anchoring asymmetry is the diagnosis; the mechanism has a second half nobody states.
The negative anchor is not merely absent, **it is selected by convenience from whatever happens to
be committed.** `S-0`'s control was chosen because the pre-registered artifacts were lost
(`AL-510`), and the substitute was picked without anyone checking where it sat in the catalog's own
similarity distribution (5.7th percentile of 105 pairs, computable in seconds). An uncalibrated
anchor plus uncontrolled anchor *selection* is why this failed on first contact rather than merely
being weak.

**What the prior review missed.** That the anchor-selection step is itself uncontrolled, and that the
control point of the resulting anchor was cheaply computable and never computed.

---

# Recommendation review

The gap analysis recommends: *"Re-file the pilot in the brief as evidence about the catalog, not only
about the instrument. Build the missing known-different anchor."*

**On the first half: REJECT as written.** The pilot's rater layer is one model run six times with
zero observed negatives across the programme's entire history. It cannot be promoted to a catalog
measurement; doing so would import exactly the evidence-class inflation that F6 exists to prevent,
and would hand a critic the easiest possible rebuttal ("your instrument has never said no"). **What
should be re-filed is the deterministic result**, all six pairs of committed filled 10-13 books
below TAU_STRUCT, as a finding in brief section 1, with the pilot cited as consistent, weak,
corroborating context. Same conclusion, evidence class the brief already accepts, and it survives
every attack in this document.

**On the second half: ACCEPT, and it is cheaper than anyone said.**

## What a valid known-different anchor actually is, concretely

**Tier 1, available today, zero authoring cost. The prior review and `results.md` both say this
artifact does not exist. It does.**

`results.md` unblocking step 1 asks to *"author or recover a true cross-band control (a 5-8 or
W16-style book against a 10-13 clocktower book)"*. C3-2 goes further and says the control *"does not
exist and cannot be found, it has to be manufactured"*.

**`out/the-school-garden-mystery.filled.json` is committed in this repo right now**: 35 nodes, band
**5-8**, topology **`open_map`** (not `branch_and_bottleneck`), themes curiosity / kindness / nature
/ problem-solving (disjoint from the clocktower's), 2,543 words, **0 unfilled nodes**. The W16
ablation README confirms `the-school-garden-mystery` is exactly the skeleton the original
pre-registration named; what was lost with the deleted branch (`AL-510`) was the W16 *rooftop-
rethemed variants*, not the base fill.

```text
structural_distance(clocktower_filled, school_garden_filled) = 0.344   (> TAU_STRUCT 0.298)
structural_distance(museum_filled,     school_garden_filled) = 0.3906
```

The pre-registered control is reconstitutable **today** by substituting the base fill for the lost
variant. Cost: one `protocol.py build` + 2 rater runs. Zero authoring, zero generation, zero dollars.
This should have been step zero and it blocks `S-2` and `S-4`.

Honest limit, and C3-2 is right about it: a cross-band anchor only proves the instrument is not
saturated. It does not calibrate it at the operating point, because a child reads within a band. So:

**Tier 2, the anchor that does the real work. Construction, and its true cost.**

Two books over **one existing 26-node armature** (`the-clocktower-cipher`, already contracted and
filled once) in which a human author deliberately varies, per fork, the **act the reader is asked to
perform**, plus a different premise, a different ending economy, and a disjoint scene set. This is
C3-8's proposal and I endorse it, with three additions nobody has made:

1. **Size-match it to the pairs it will anchor.** Because the unbounded firing criterion is a
   function of Book Two length (claim 4b), an anchor of a different size does not anchor anything.
   26 nodes, matching the D-7/D-7b known-answer pairs.
2. **It must be human-authored, and that is the whole cost.** An LLM-authored "known-good" inherits
   the convergence being measured: Q-3c (8 of 10 isolated generations converge on a beacon premise)
   and section 27 (156.35 shared grams/1000 cross-vendor on premise) say the generator cannot be
   trusted to produce the negative anchor for its own convergence. Realistic cost: one human
   authoring pass over ~9,000 words of 10-13 prose against a fixed armature. Days, not hours, and it
   cannot be delegated. That is the honest price of every downstream instrument claim.
3. **Pre-register the anchor's expected verdict before authoring**, not after, otherwise it is
   selected-on-outcome the way `S-0`'s control was.

Payoff, as C3-8 says: one artifact anchors the 4-gram budget, TAU_STRUCT/TAU_CELL, solution transfer,
the CI panel's four `expected_verdict: pass` rows, and the recognition protocol's negative control
simultaneously.

## Is there a cheaper decisive test than E0?

**Yes, two, and the first costs nothing.**

**Test A (zero model calls, minutes, decisive for the catalog question).** The catalog audit in this
document. `structural_distance` over all 105 within-band 10-13 skeleton pairs plus the 6 pairs of
filled books, read against TAU_STRUCT rather than TAU_CELL. It already answers "is the catalog
convergent?" with a deterministic yes and needs no rater, no instrument validation, and no
generation. Extend it with an ending-title/function-sequence overlap across the same 105 pairs and
you have the catalog audit C3-2 asks for, complete, for the price of a script. **This test
discriminates nothing about the instrument, and that is the point: it makes the instrument
unnecessary for this particular question.**

**Test B (6 rater runs, decisive for the instrument question).** Run the frozen protocol on the two
structural extremes of the *existing filled* 10-13 books, plus the cross-band anchor:

| pair | distance | pre-registered expectation |
| --- | --- | --- |
| museum vs hollow-lighthouse | 0.064 (most similar in catalog) | fires early, if it does not, the instrument is broken at the similar end too |
| clocktower vs mapmakers-island | 0.2424 (most distant filled 10-13 pair) | **must not fire**, the within-band discrimination test |
| clocktower vs school-garden (5-8) | 0.344 | **must not fire**, the saturation test |

All five books are committed and filled. Cost: 3 prompt builds, 6 rater runs, no authoring.
Corrected 2026-08-30: the heading of this test read "4 rater runs" against a plan of three pairs at
two rater runs each, which is the 6 the cost line already gives; the sentence also read "All four
books" against a table naming five distinct books (museum, hollow-lighthouse, clocktower,
mapmakers-island, school-garden). Both are counting errors, not scope changes: the planned coverage
is three pairs over five books at six rater runs, and the cost line was right all along. If the
raters fire on *all* of these, the instrument is degenerate and claim 4 collapses completely. If they
separate the 0.2424 pair, the instrument discriminates within band and the control "yes" becomes a
real measurement. **This is the test that actually adjudicates instrument-failure vs catalog-
convergence, and neither the brief nor the review proposed it.** It is a small fraction of E0.

Sequencing: A first (free, and may make B unnecessary for the catalog claim), then B, then Tier-2
authoring only if B shows the instrument is worth repairing.

## What should be done that nobody proposed

1. **Fix the threshold, not the instrument.** Apply TAU_STRUCT (0.298321) as the cross-tree diversity
   target it is documented to be, alongside TAU_CELL as the anti-duplication floor. Today a pair at
   the 5.7th percentile of catalog similarity is green. One constant, one gate, immediate effect.
2. **Add the catalog-convergence audit as a standing check**, not a one-off: every new skeleton
   scored against every in-cell sibling on `structural_distance` at admission, reported against
   TAU_STRUCT. `scripts/analyze_sibling_exposure.py` already walks this data.
3. **Stop pre-registering falsifiers on `first_yes_position` until it is measured.** The single-prompt
   design reconstructs it post hoc. `S-2` and `S-4` both key falsifiers on "at or before position 4",
   a quantity the protocol does not measure. Either move to a genuine multi-turn reveal (one call
   per scene; expensive but real) or re-specify the falsifiers on the binary verdict plus
   distinctness only.
4. **Commit the rater prompts and transcripts.** Six verdicts were committed with no prompt, no
   transcript, no session id. Blinding and independence are currently unverifiable assertions in a
   directory whose entire purpose is instrument validation. `AL-185`/`AL-231` already forced this
   programme to downgrade a run to "author-scored" for the same reason; the lesson did not transfer.
5. **Size-match every recognition pair, or bound the criterion.** As long as "must never fire" is
   unbounded, longer Book Twos fail by construction. Either fix Book Two length across a validation
   set, or normalize the criterion by scene count. This defect is independent of the band substitution
   and is not recorded anywhere.
6. **Retire "counterbalanced two raters" as a description of same-model runs.** Use "one model, two
   orderings" in `results.md`, the README, and the register. It is the honest label and it changes how
   every downstream reader weighs the result.

---

# What everyone missed

1. **The pre-registered cross-band control was never lost.**
   `out/the-school-garden-mystery.filled.json`, 35 nodes, band 5-8, `open_map` topology, fully
   filled, committed, is the exact skeleton the original pre-registration named. `AL-510`,
   `results.md` step 1, and C3-2's "it cannot be found, it must be manufactured" are all wrong about
   availability: what was lost was the W16 *retheme variants*, not the base fill. `S-2` and `S-4`
   have been sitting blocked on an artifact that is in the repo.

2. **The control pair is the 6th most similar of 105 pairs in its own catalog (5.7th percentile).**
   Nobody computed where the negative control sat in the distribution it was supposed to anchor. Five
   catalog pairs are more similar still, the most similar being lighthouse/museum at 0.064, barely
   above the anti-duplication floor. Both the brief's reading and the review's reading are argued
   without this number, and it is the number that settles the "was it a bad control" question:
   emphatically yes, and for a reason neither party identified.

3. **Structural distance already caught this pair, and was read against the wrong constant.**
   0.1239 is below the same-cell p05 (0.154657) and 2.4x below TAU_STRUCT (0.298321). The instrument
   agreed with the raters. The programme gates cross-tree diversity with `TAU_CELL = 0.05`, a
   duplicate detector, while its own documented cross-tree target sits unused in
   `ws5_floor_baseline.json`. The review reported this as a false negative and thereby discarded a
   working instrument and a one-line fix.

4. **The catalog-convergence claim has a deterministic proof, and it was never run.** All six pairs
   of committed *filled* 10-13 books fall below TAU_STRUCT (0.064 to 0.2424 against 0.298). Every
   pair involving the 5-8 book clears it (0.344 to 0.4639). This says what the review wanted to say,
   in the evidence class the brief already trusts, with no rater, no model, and no failed instrument.
   Selection nuance worth stating honestly: the four filled 10-13 books are a *biased* sample, the
   ones that got filled are all `branch_and_bottleneck` mysteries. That bias is itself the finding:
   the subset of the catalog that actually reaches children is its most convergent subset.

5. **The recognition instrument has never returned "different", not once, in any run, manual or
   automated, in the programme's entire history.** S5, S6, S7, S8, S9, both pilots, all six S-0
   verdicts: 100% same-adventure. This is the fact that decides between the two readings, and neither
   the brief, `results.md`, `AL-511`, nor the prior review states it. It refutes the review's
   "positive measurement" framing outright, and it also means the brief's repair plan is
   under-specified: repairing the firing *rule* does nothing for an instrument whose negative class
   is empty.

6. **"Sequential commitment" is fictional, and two open pre-registrations depend on it.** The
   single-prompt design lets the model read all 95 scenes before writing the verdict for scene 1;
   `first_yes_position` is a post-hoc reconstruction, not a commitment. `results.md`'s own repair
   item 2 and the falsifiers in `S-2` and `S-4` are all keyed on that unmeasured quantity. The
   docstring declares the approximation honestly; nothing downstream honours the declaration.

7. **The unbounded control criterion is length-biased.** "Must never fire" gives one chance per Book
   Two scene. The control's Book Two was 95 scenes; every known-answer Book Two was 26. The control
   had 3.7x more chances to fail, and with unequal book sizes the counterbalanced design has no valid
   symmetric form at all. `results.md` found the position-bound asymmetry and stopped one step short
   of this.
