# Audit remediation: recommendation per finding

Written 2026-08-18. Covers every open row from the `AL-458` seven-lane audit (`UW-C279` to
`UW-C285`) plus the earlier open rows it interacts with (`UW-C272` to `UW-C278`). One
recommendation each, sequenced. Where a recommendation rests on a measurement, the measurement is
shown rather than cited.

Three findings resolved already and not repeated here: `UW-C285(a)` (pronoun vocabulary, closed
2026-08-18), PL-25's unit error (`AL-456`), and CG-1's average-versus-maximum error (`AL-455`).

## REVISED 2026-08-18 after adversarial review

An adversarial review (fable subagent, full text in the session scratchpad) attacked the reasoning
below and landed four times. Every claim in this section was re-verified locally before being
accepted. The original text is kept in place with markers rather than rewritten, because the
reasoning that was wrong is the useful part of the record.

**Withdrawn outright:**

1. **The series-handoff table in `UW-C283`.** It was headed "positive endings at ~40%", derived from
   PL-24. PL-24 caps the dominant ending **KIND** at 60 percent; its positive-**VALENCE** floor is
   gamebook-only (5 percent share, count of 3). Nothing implies 40 percent positive. That figure was
   the catalog's authoring habit, not a rule. So the table, the "structurally opposed" conclusion,
   and the gate on authoring at 10-13/long and above are all withdrawn. This is the same
   kind-versus-valence conflation this document recommends fixing elsewhere, committed inside the
   argument for fixing it.
2. **The kind switch on the walk floor (`UW-C284d`).** Verified locally: teen gamebooks carry 2 to 7
   satisfying-KIND endings out of 74 to 209 total (`the-tenfold-siege` 6 of 209,
   `the-ashfall-expedition` 3 of 143). ADR-011 section 5 defines the gamebook as "few wins plus many
   fails", so a kind reading makes the genre's defining shape fail by construction and no new teen
   gamebook could be authored. Worse, the floors were **owner-ruled 2026-08-09** and the ruling's own
   text defines satisfying as "positive- or neutral-valence"; recommending the switch was
   recommending a silent override of a dated ruling without noticing one existed. If the concern
   (161 neutral-valence setbacks counting as satisfying) is worth acting on, the surgical form is
   excluding `(setback, neutral)` only, and it needs the floors re-ratified.
3. **The `TAU_STRUCT` ratchet (`UW-C273`).** `diversity/incell.py` records `TAU_STRUCT` as
   "**documentation only** as of that same amendment" (ADR-020 Amendment 1). The live floor is
   `TAU_CELL`, a fixed 0.05 that cannot fall. Ratcheting a retired quantity is precisely the defect
   class this document's closing line names.
4. **The PL-20 one-way word transfer (`UW-C277`).** PL-25's one-way reading fires only when node
   count AND word count are both out of bounds. The motivating defect is a nine-node, 180-word
   hollow win, and nine clears the cell's floor of seven, so the node test passes and the rule never
   fires. The fix cannot catch its own worked example. Catching it needs a tightening word test with
   grandfathering, which is a different and more expensive recommendation.

**Revised, not withdrawn:**

5. **`UW-C283`'s replacement rule.** Taking ADR section 5's column as STATIC per-cell ranges drops
   scaling the column itself encodes (within `8-11/long` its implied fraction is 0.175 at the bottom
   and 0.167 at the top, so it is a fraction times an envelope). Static ranges would admit a 340-node
   book with 32 endings at a 9.4 percent share, below ADR section 6's own 15 to 22 percent band, so
   the fix would trade a section-5-versus-code conflict for a section-5-versus-section-6 one. **Use
   per-cell fraction PAIRS (a floor fraction and a ceiling fraction per cell) instead**, one step from
   the table already shown. Grandfathering is required either way and was not mentioned: the review
   reports the proposed ceiling failing seven committed books.
6. **`UW-C280`'s CG-4 fix.** `enforce_grammar` is a single early return gating all four CG rules, so
   the "one flag, low risk, it is a WARNING" framing is wrong: flipping it on the fill path enables
   CG-1, CG-2 and CG-3 there too. The right fix is per-rule enablement. The review measured 375 CG
   findings across eight filled books under the flag flip; I have not re-verified that number.
7. **`UW-C281`'s reading-level argument.** The conclusion (adopt column E) survives; the argument does
   not. Arguing from achievability is circular, since the books were written and repaired to their own
   declarations. There is an external anchor and it was never cited:
   `research/cyoa-research-reconciliation.md` item 4 sets the gate by age band and places core CYOA at
   roughly 500-710L with teen gamebooks at middle-grade prose, which favours E over C at exactly the
   bands where they diverge. Cite the anchor, note E sits slightly above it at 8-11, and route it to
   the owner as a decision rather than presenting it as settled.
8. **The can-it-fire test.** All three dead rules were dead in the WIRING, not the rule bodies. A
   registry-level test invoking each rule directly would have caught none of them, and the M2 floor
   is not in the validator registry at all. The valuable form is entry-point level: a violating
   artifact at each production call path must yield a finding. That is a materially harder spec and
   the "highest leverage" claim should be restated against it.

**One review claim I checked and falsified.** The review states `the-winter-of-the-wolf-queen` and
`the-tricameral-city` "pass `check_skeleton.py --strict` today with zero findings". They do not: 90
and 52 blocking lines respectively, on CG-1 and CG-2. Its underlying point survives and is what
matters, though: no rule floors satisfying-KIND endings, so those books do carry 40 and 42 endings
with only 8 and 7 satisfying-kind, which is the setback-and-discovery remedy already in use without
new architecture.

**Unchanged and unrefuted:** Wave 0 (`UW-C282`), `UW-C285(b)`, `UW-C279`, `UW-C278`, `UW-C284`'s
other three items, `UW-C272`, `UW-C274`, `UW-C276`, `UW-C275`. The review attempted the `UW-C282`
normalization collapse through the orchestrator, import path, `makeFetchStory`, IndexedDB, and the
vitest fixtures and could not make it land, with one narrowing: all 31 filled artifacts do carry
top-level `variables`, so only the `choices` leg is supported by committed evidence.

## The organizing observation

The 14 open items are not 14 problems. They are four, and the sequencing below follows them:

1. **One rule set is not self-consistent.** PL-17 contradicts ADR-011 section 5; PL-20 contradicts
   PL-25's walk floor on what "satisfying" means; PL-29 offers topologies PL-18 forbids. Nothing
   ever asserted the rules agree with each other, so they drifted.
2. **The generator is told things the gate does not enforce, and not told things it does.** The
   ending count, the FK target, and the words-per-stop range are each stated to the model in a
   number the gate disagrees with, or not stated at all.
3. **Three rules cannot fire, and no test noticed.** Nothing asserts a gated rule is capable of
   producing a finding.
4. **Two guards trust data they do not validate**, and both say in their own comments that they do
   not.

## Wave 0: verify before anything else

### `UW-C282` reader crash. **Recommendation: reproduce it today, then one-line fix or close it.**

The data path is confirmed unnormalized end to end. `generation/persistence.py` stores
`stamped = {**params.blob, "id": ...}`, a shallow dict copy with no Pydantic round-trip; the read
route carries **no `response_model`**, so FastAPI returns the raw dict and materializes no defaults;
777 nodes across 28 of 31 filled books omit `choices`. `player/engine.ts` then calls
`node.choices.filter(...)` unguarded, from a `useMemo` that runs on every render including at an
ending.

The only unverified link is whether the reader visibly crashes, and `frontend/node_modules` is
absent here so vitest could not run. **Do not fix this blind.** If it reproduces, the fix is
`node.choices ?? []` and `story.variables ?? []`, matching the same file's existing idiom for
`on_enter` and `effects`. If it does not reproduce, find what normalizes the blob and write the
test that pins it, because nothing in the Python path does.

Everything else on this list is calibration. This is the only item that could be failing a reader
right now.

## Wave 1: safety, and rules that cannot fire

### `UW-C285(b)` the denylist floor trusts the contract's own band. **Recommendation: stop reading `contract.age_band` entirely.**

Key the band-mandatory floor on `story.metadata.age_band`, which is validated by PL-21/PL-22 and by
the schema, and make `load_contract_for` assert the contract's band MATCHES the story's rather than
supplying it. Two lines, no decision, removes the trust rather than adding a check to it. The
current `#CRITICAL: security` comment claims "nothing in contract data can remove or shrink it";
retyping a committed 3-5 contract to `16+` empties the floor, binds "a deadly poisoned blade" with
zero violations, and the CI gate exits 0 with all seven checks PASS. Do this in the same batch as
Wave 0.

### `UW-C280` three rules that cannot fire. **Recommendation: fix all three, but ship the test first.**

The individual fixes are small and none needs a decision:

- **CG-4** skips `<<FILL` bodies while only skeleton callers enable grammar checks. Run it on the
  fill-result path (`enforce_grammar=True` on the post-fill `run_gate`), which is the context it was
  designed for and the only one where "does the prose acknowledge the choice" is answerable. Low
  risk: it is a WARNING.
- **The M2 anti-clone floor** falls between a structural check that defers to the state floor and a
  state floor that returns early for Tier-1. `check_promotion_bundle.py` already catches these with
  a stricter fingerprint predicate; hoist that predicate into `acceptance.py` so one definition of
  "shape unchanged" serves both sites.
- **The R4 theme gate** scores `jaccard(theme_signature)` where production scores
  `containment(similarity_signature)`. Change the panel to call the production function. One import.

**The test is the real deliverable, and it is the highest-leverage single item on this list.** A
parametrized test over the rule registry, each rule paired with a minimal known-violating fixture,
asserting a finding comes back. Three rules were dead and the suite was green. Note the
personalization slots already have this property by accident, which is why closing `pronoun_set`
tripped three separate guards on the way in; the validator rules have nothing equivalent.

## Wave 2: stop telling the generator the wrong number

### `UW-C279` prompt ending count. **Recommendation: derive from the cell, and pin it with a rendered-prompt test.**

`brief.py` computes `ending_count` from the band envelope while PL-17 floors from the cell envelope,
so the prompt says "produce EXACTLY 4 ending node(s) ... Not more, not fewer" where the gate needs
24. Point `brief.py` at the same cell envelope. Then add the test that actually prevents the class:
render the prompt for all 18 cells and assert every number it states satisfies the gate that will
judge the result. Sequence this AFTER the `UW-C283` decision below, so the brief inherits whatever
the floor becomes rather than being fixed twice.

### `UW-C281` reading level. **Recommendation: `band_profile.py` becomes the single source; adopt the numbers the catalog already achieves, not the aspirational ones.**

Four tables claim the role and one of them says so in its own text. Put the per-band table in
`band_profile.py`, where every other per-band policy lives and which the validator already reads,
then derive the rest: `brief.py` reads it, the injected drafting guide renders its numbers from it
rather than restating them in prose, the frontend gets it from the API, the planning guide cites it.

**On which numbers win: adopt column E (what the catalog declares), not column C (what the prompt
says).** E is empirically achievable, demonstrated by 31 books; C is not, with four of five 13-16
books falling below C's own floor. Adopting C would put most of the existing catalog out of band
overnight in exchange for numbers nothing has hit. Full comparison in
`reading-level-source-table.md`.

Keep the per-story declared target, defaulted from the band table, and add a test that every
committed skeleton's declaration sits inside its band's range. That keeps authoring latitude and
kills the drift.

Separately and independently of which table wins: `reading_level_cap` is documented as a ceiling
that "can only ever tighten" and is used as a window CENTRE, so a guardian cap of 2.0 admits FK
3.00. Make the cap clamp the upper bound (`target = min(band_target, cap)`, upper bound
`min(target + tolerance, cap)`). This one is a straightforward bug in a guardian-facing promise.

Finally, `scripts/check_reading_level.py` must read the band or its guard-battery row must stop
claiming it does. Recommend the former.

### `UW-C278` the stop range is not in the brief. **Recommendation: state it, cheapest item on the list.**

Median scene length across four story-first drafts is 246, 439, 400, 279 words at 5-8, 8-11, 10-13,
13-16: no trend. The model does not infer the band's words-per-stop range, so put it in the
authoring brief and the skeleton brief. No decision, no risk.

## Wave 3: the calibration decisions

### `UW-C283` + the endings balance. **PARTLY WITHDRAWN, see revision 1 and 5 above. The series table below is unsound and the replacement rule should use per-cell fraction pairs, not static ranges.**

The measurement that settles it. PL-17 applies a flat 0.15 to node count; the ADR's own per-cell
numbers imply a fraction that is not constant and cannot be reproduced by any single value:

| | implied endings fraction |
| --- | --- |
| 5-8/short (highest) | 0.207 |
| 10-13/long (lowest) | 0.141 |
| PL-17's flat value | 0.150 |

A curve running 0.13 to 0.21 is not a typo in one cell, it is the wrong shape of rule. Three of 14
prose cells conflict at the top of their node range (3-5/medium, 10-13/medium, 10-13/long: the ADR
allows 48 endings at 340 nodes, PL-17 demands 51). Implementing the ADR's table directly resolves
the contradiction by construction and, more importantly, **supplies the ceiling the owner's balance
requires and no rule currently has.** Keep a fraction only for the four gamebook cells, where the
ADR says "many fails" and gives no numbers.

That handles three of the four stated concerns. The fourth needs its own rule:

- *too few endings forces reconvergence* -> the ADR floor
- *too many endings makes paths individual* -> the ADR ceiling, new
- *too many unsuccessful endings and the reader cannot find the positive one* -> **already covered**
  by the strict walk floor (`satisfying_walk_probability`), which measures exactly this. Do not
  build a second rule for it; do settle the kind-versus-valence question below, since that rule's
  answer depends on it.
- *in a series, all positive endings converge to one start point* -> **no rule expresses this, and
  it is the one that actually bites.**

At PL-24's 60 percent dominant-kind ceiling, the implied handoff cost is:

| cell | ADR endings | positive endings at ~40% | start states book 2 must absorb |
| --- | --- | --- | --- |
| 8-11/short | 12-18 | 5-7 | 5-7 |
| 10-13/long | 32-48 | 13-19 | 13-19 |
| 16+/long | 36-60 | 14-24 | 14-24 |

Thirteen to nineteen start states is not a handoff anyone can author. **So the series constraint and
a node-scaled endings floor are structurally opposed at the long cells, and no choice of fraction
fixes it.** Recommendation: make series eligibility a declared cell-level property. A
series-eligible book takes a positive-ending CEILING (3 to 5, one per intended book-2 opening) and a
correspondingly lower total-endings floor, making the difference up in setback and discovery
endings, which need no start state. A standalone book keeps the ADR range. This is the one item here
that is genuinely an architecture decision rather than a calibration, and it should be decided
before any authoring at 10-13/long or above.

### `UW-C277` remaining unit errors. **PL-20 HALF WITHDRAWN, see revision 4 above. PL-26 and the `_MIN_COMPLETE` comment fix stand.**

- **PL-20** counts nodes where its budget is words: rewriting only the `words=` hints on a nine-node
  path to 20 each leaves the gate clean at 180 words, less prose than the two-node hollow win the
  ADR says the floor forbids. Apply the same one-way word-equivalent reading PL-25 now uses, so no
  passing story starts failing.
- **PL-26**'s ceiling is one flat 6.0 nodes-per-decision against a "3.28 pages between decisions"
  anchor, which spans 240 words at 3-5 to 1050 at 16+ and inverts the ordering on the real corpus.
  Re-derive per band through `_WORDS_PER_NODE`.
- **`_MIN_COMPLETE` needs no change**: the suspicion that it held page counts was refuted, its
  values reproduce the ADR's own fastest-finish minutes column across all 18 cells. Fix the
  `band_profile.py` comment that mis-cites them as JHM page counts.
- Record the unit each threshold is stated in, in `validator-rules.md`, so the next threshold cannot
  be adopted without naming its unit.

### `UW-C284` topology. **Recommendation: fix three, and grandfather the fourth.**

- **`gauntlet`**: fix the classifier, not the ADR. The ADR describes a real published form (the
  deadly gamebook gauntlet, spine plus fail-branches plus restart) and the code cannot express it;
  built as specified it classifies as `sorting_hat`/`time_cave` and blocks at 13-16 gamebook.
- **PL-29 dropping the ADR's length and style qualifiers**: add them to the key. Small.
- **Cyclic branch depth unchecked** (19 skeletons, one carrying a real 87-hop path against a cap of
  43): condense the strongly connected components and take the longest path on the condensation.
  Well defined on a cyclic graph and cheap; today the check returns `None` and emits nothing.
- **Two definitions of "satisfying"**: **WITHDRAWN, see revision 2 above.** Original text: pick **kind**, aligning the walk floor to PL-20 rather than
  the reverse. Kind describes what happened; valence describes tone, and 161 neutral-valence
  SETBACKS currently count as satisfying outcomes. **This tightens the bar**: 19 of 68 skeletons
  clear the walk floor only on the broader reading, so it needs the CG family's grandfathering
  treatment, not a silent switch. Settle this before `UW-C283`'s walk-floor reliance above.

## Wave 4: housekeeping, no decisions

- **`UW-C272`** PL-29 offers unbuildable topologies in 15 of 18 cells. Narrow the rows to the
  reachable set per cell. The durable fix is the test: assert the intersection of PL-18-admissible
  and PL-29-permitted is non-empty for every offered cell.
- **`UW-C273`** **WITHDRAWN, see revision 3 above: the quantity is retired.** Original text: `TAU_STRUCT` can fall as skeletons are added. **Ratchet it.** A floor that the
  authoring meant to strengthen the catalog can lower is not a floor. Cheap, and the alternative
  reading (a falling floor tracks a more varied catalog) does not survive the fact that it fell
  three times in one authoring session.
- **`UW-C274`** self-dating census artifact, and the post-bottleneck coherence lint. Both small,
  both already cost a real defect each. Schedule.
- **`UW-C276`** CG-3: treat a decision or ending node with no preceding run as a stop of one, and
  add the two missing bands from ADR-011 section 10's own numbers. Will fire on committed content,
  so grandfather like the rest of the CG family.
- **`UW-C275`** largely superseded by `AL-453` and `AL-457`: convergence is not the craft conflict
  it was thought to be. The live remainder is whether 5-8 joins the flowed bands, which is an
  ADR-026 amendment rather than a code change.

## Suggested order

Wave 0 and Wave 1 are a single batch and should go first: one is a possible live crash, one is a
safety floor defeated by unvalidated data, and one is three dead rules. Wave 2 next, because every
generation currently runs against wrong numbers. Wave 3 is the thinking, and `UW-C283`'s series
decision gates authoring at 10-13/long and above. Wave 4 whenever.

The single highest-leverage item across all four waves is the can-it-fire test in Wave 1. Three
rules were dead, one gate measured a retired quantity, and one guard was defeated by its own input,
all with a green suite.
