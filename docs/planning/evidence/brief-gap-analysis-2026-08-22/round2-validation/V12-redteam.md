# V12: red team of the review itself

Target: `docs/planning/cyo-brief-gap-analysis-2026-08-22.md` (the synthesis), the twelve findings
files, and the review's method. Not the brief. Everything below that says "verified" I ran or read
myself; commands are named so the claim can be attacked.

**Headline.** Criticality inflation runs at **63%** (10 of 16 sampled critical/high findings survive
only at a lower severity; 3 drop two notches). The single most damaging result is that the
synthesis's own flagship finding, 1.1 ("the number is 3.2, not 2.3"), is substantially an artifact
of a tool the programme's register **already records as defective and pending repair** (`UW-C225`).
Recomputed under the scope the programme's own pre-registrations use, the D-7b pair is **2.55 shared
4-grams per 1000**, not 3.2, and the margin against the 3.3 idiom floor is ~0.75, not the "collapsed"
0.1 the synthesis reports. The synthesis states the mechanism correctly in one sentence and then
reasons from the uncorrected number for the rest of the section.

Against that, the review is not a bad review. Its verification discipline is real: all five
"verified"-table rows I spot-checked reproduce exactly, and its two best findings (B3-2, C3-4) are
better than anything I could break.

---

## Systematic biases

### Severity distribution, before any judgement

Across the nine code-grounded files (B and C cohorts), 161 findings:

| severity | count | share |
|---|---:|---:|
| critical | 34 | 21% |
| high | 70 | 43% |
| medium | 48 | 30% |
| low | 9 | 6% |

**65% of all findings are critical or high.** A severity scheme in which two thirds of findings are
in the top two bands is not ranking anything; it is a volume control stuck at maximum. This is the
first-order evidence of inflation, before any individual finding is examined.

### Criticality inflation: 16 findings sampled, 10 downgraded (63%)

I sampled across all nine files, weighted to the ones the synthesis promotes.

| ID | stated | my rating | why |
|---|---|---|---|
| C1-5 | critical | **medium** | The defect is that `--strict` re-emits an escalated finding's own message, which ends "(advisory only)". Its own category field says "authoring ergonomics". No child, no request path, no money, no safety. It is a string-formatting bug in an offline catalog tool. It costs authoring iterations, which is real, and is nowhere near critical. **Two notches.** |
| C1-3 | critical | high | Verified: `_build_graph` gives 144 edges for 348 choices, 0 reconverging nodes. Genuine, exploitable, and an author found it. But it is a catalog-time gate seam, not a production defect, and its consequence is C1-2's, counted separately. |
| C1-2 | critical | high | Verified and then some: 102 of 115 decision nodes in `the-observatory-shift.json` route every choice to one target, and I checked further, **all 102 carry zero `effects` and zero `condition`**, so my attempted rebuttal (that they are Inkle-style state-setting choices) fails outright. The finding is real. It is one book of 84, and it collides with an owner ruling nobody cited (below). |
| C1-1 | critical | **medium** | "The catalog is roughly 76% non-compliant with its own stated standard" is presented as a discovery. `UW-C270` is a dated, script-measured, owner-ruled census of exactly this, re-measured four times (6/64 → 13/68 → 4/70 as the bar moved) and closing with "**DONE 2026-08-19: all 18 offered cells now have a strict-passing member.**" The synthesis's recommendation to "publish the 64-shell remediation backlog" asks for a document that exists and whose owner ruling ("author all 15 cells... repair 5-8/medium rather than replace it") deliberately chose authoring-up over retrofitting legacy shells. **Two notches** as a finding; the underlying `--strict`-in-CI fact survives (see below). |
| C4-2 / B2-3 | critical | high, and misframed | Verified: `api/approval.py` never reads `has_hard_block`. But `api/node_edit.py:666` carries an explicit `#CRITICAL: security:` comment stating this is deliberate, "ADR-005: the human reviewer is the final gate... a fresh block here is persisted and surfaced on the review surface for a human to weigh (approve() does not itself check has_hard_block either)", with a named regression test. ADR-005 itself says automated moderation "gate[s] entry to review; they do not replace the human step". `review_surface.py:130` has an invariant comment ensuring "a bright-line 0.0 BLOCK is never hidden". So this is an accepted design, annotated in three places, not an unnoticed hole. What survives is narrower and still worth fixing: **no attestation that the approver saw the block, and a dual-role adult can self-approve.** |
| C4-5 / C6-8 (SAFE-14) | high | **medium** as safety | `validator/safety.py` self-describes as "Phase-2 placeholder" in line 1; `gate.py` labels it "(Phase-2 stub, always empty)" at lines 33, 39, 98, 99 and 212. Phase 3 delivered the safety layer in `moderation/`, which is where safety lives. Registered twice (`UW-C115`, `UW-C157`: "stop reporting it as measured"). The synthesis's line that "`gate.py` reads as though safety is covered" is **contradicted by the file it cites**, five times. |
| C2-4 | critical | **sustained** | I tried to break this and failed. `llm_timeout_seconds = 120` (config.py:507, verified) against measured fills of 469/687/1874s. My rebuttal was that large books chunk into short calls, but the live-fill plan's own finding F1 records that the largest skeleton needs 99,906 tokens against a 104,857 feasibility ceiling, so **chunking never fires on the current catalog** at the shipped cap. Timeouts are `leg_fatal=False`, so a large fill bills up to six cloud completions and then hands a 16+ children's book to a local 14B model. Best finding in the C cohort. |
| C2-3 | critical | high, and mutually exclusive with C2-4 | The 594k-input / context-window defect requires the chunked path. C2-4's defect requires the one-shot path. On any single configuration only one of them is live, and on the shipped DeepSeek cap it is C2-4. The synthesis lists both as critical and the top-three answer bundles them into one bill. |
| C2-2 | critical | **medium** | The claim is that `drafting_guide.md`'s "no hard per-node minimum: a one-line beat is legitimate" and "a tense beat can run three words" *license* the AL-490 shortfall. Read in place (lines 172-189), those clauses sit inside a paragraph whose thrust is the opposite: "Aim for the advisory band as a story-wide average"; "shorter bodies leave the story feeling sparse". The first clause is a true description of `band_profile.py`. The causal claim is untested, and the rig that would test it, `evidence/w16-fill-guide-ablation/`, is **built and never run** (no `results.md`). **Two notches.** |
| C5-8 | high | sustained, with n=1 caveat | Well argued. The 46% figure is derived by **residual subtraction on one book**: total tokens minus an estimated fill share, attributed wholly to the reading-level loop. Repair attempts, fidelity review and moderation calls also live in that residual. Promoted to a headline in §4.5 and to the user's top-three on n=1. |
| C4-8 | high | sustained | Fair, well-scoped, ~15-line fix. Its one overreach: "the work register records it as delivered", `UW-C264` says "Screen **half** done" and "The judged `imitable_practice` criterion **remains unbuilt**" and is status `unscheduled`, which is not "delivered". |
| C4-3 | critical | high | Real, and already registered as blocking: `UW-C02` (`AL-036`) says "the review surface cannot deliver the human approval ADR-005 requires at 746 nodes (no pagination, virtualization, or per-node state)". Re-discovery, not discovery. |
| B3-2 | critical | **sustained** | The strongest finding in the review. Verified: both `summary.md` files print "Primary endpoint (S-1): ... p = 1.0000 ... Everything below is exploratory." One qualification that cuts against the review's framing: the programme's **own harness prints that banner automatically**. The failure is entirely the brief's omission of it, not a research failure. |
| B3-4 | critical | high | Verified from the leg table (pass 6,3,6,4,3,0,5 against min-catalog-distance 0.066,0.138,0.051,0.083,0.150,0.172,0.063). But the correlation is close to definitional: `TAU_CELL` and the band rules define a narrow admissible region, and the catalog is the set of graphs inside it, so distance-from-catalog and rule-conformity are not independent variables. Note also that the harness **already computes and prints the covariate** B3-4 recommends adding. |
| C3-4 | critical | **sustained** | Excellent. The rival-hypothesis table is the best analytic work in the review and I could not weaken it. |
| C6-4 | high | sustained | Register-integrity escape hatch, demonstrated by execution. See "upgrade" below. |

**Inflation rate: 10 of 16 (63%).** Two-notch drops: C1-5, C1-1, C2-2 (19%).

### Absence-as-defect

**64 of 161 finding titles (40%)** are framed as an absence: "no X", "nothing does Y", "X is
never called", "unbuilt", "unmeasured", "unwired".

Of the ones I traced to the repository's own tracking, **at least 24 findings (15% of the total,
38% of the absence-framed set) restate something already registered, phased, owner-ruled, or
self-labelled in code**:

| finding(s) | already recorded as |
|---|---|
| C5-3, B2-4, B1-8, C6-1 (`check_fill_integrity` not in production) | `UW-C307`, phase **4b**, whose own text ends "**Still open:** whether the deterministic gate carries the check" |
| C3-6, C2-18, C3-14 (`check_sibling_fills` unwired) | `UW-C315`, phase 4b, **and disclosed in the brief itself**, §3.4: "production wiring of this check is open work, `UW-C315`" |
| C4-5, C6-8, B2-12 (SAFE-14) | `UW-C115`, `UW-C157`, plus five in-code "(Phase-2 stub, always empty)" labels |
| C4-8 (`imitable.py` no callers) | `UW-C264`, deliberately staged: the judged criterion "must not arbitrate before W7 shows it detects a seeded unmitigated-hazard arm", i.e. **the programme applying its own F6** |
| C1-2, B2-17 (false choice) | `UW-C86`, `UW-C128`, and `UW-C181` (owner ruling, below) |
| C1-4 (PL-18/PL-29 undeclarable) | `UW-C272` |
| C1-1, C1-11 (strict non-compliance) | `UW-C270` |
| C4-3, B2-9 (review surface) | `UW-C02` / `AL-036`, already marked blocking |
| C3-7, C6-2 (gram scope) | `UW-C225`, the register **already names the joined-string artifact and the fix** |
| C4-7 (cover art unscreened) | roadmap M5: "H2 is half closed... only the automated image classifier is missing" |
| all commerce economics (C5-1/2/12, A3) | `UW-N01`, phase **8**: "No payment-processing or entitlement-ledger implementation exists in this repository today" |

The synthesis's §2 ("the detector is built, and it gates nothing") is the sharpest instance. Of its
seven rows, **three are staged deliberately and one is disclosed in the brief under review**. Two of
the seven: `imitable.py` and `check_sibling_fills`, are unwired *because F6 says do not gate on an
instrument that has not survived a known-answer test. The review's own §5 demands exactly that
discipline* ("Instrument validation as a gate on gating") and then §2 penalises the programme for
practising it.

### Ignoring the product's actual stage

The system is R1-alpha: live internally since 2026-07-05, one homelab deployment, `UW-F17` at 10 of
38 live-checklist steps, commerce not started (Phase 8), no pricing decision in the repo.

Premature material, quantified:

- **A3 §6.3 in full**: FTE tables at 10k / 100k / **1M** subscribers, "a 1,215-person operation",
  cost as a share of net revenue at 100k subs. There are no subscribers.
- **A3's assumption register**: $12.99/mo price, 8% monthly churn, $40 blended CAC, 60/40 store
  mix. None of these is a project decision. The repo's only recorded offer design (`UW-N01`,
  external comparison) is **$9.99 for 2 credits/month**.
- **The synthesis's own §1.4 headline** compounds it: "$10 subscription at 70% target margin",
  "3 books per child per month", "the shipped 10-book quota". The $10 and the 70% are invented; the
  10 is `default_monthly_story_quota: int = Field(default=10)` in `core/config.py:931`, a
  per-family-overridable **development default**, not a commercial entitlement. Multiplying an
  invented price by a config default yields the "13 to 28x" figure that anchors the section.
- **A3's "impossibility result"** rests on 118,000 words. The real maximum is 49,953 commissioned
  words (`skeletons/16+/the-last-cartage.json`, 632 nodes: I recomputed across all 84 shells), and
  delivered words are 39-53% of commissioned. So the "impossible by a factor of 100-380" is more
  like 40-160 on commissioned words and lower still on delivered. The synthesis concedes the 2.8x
  error in §3 and then leaves §1.4's magnitude claim standing on it.

Roughly **20 of A3's 60 requirements and the whole magnitude of headline 1.4** are conditioned on a
scale and a commercial structure that do not exist. The *direction* of 1.4 (human review dominates)
survives; the *multiplier* does not.

### Double counting

The synthesis says convergence "is weighted heavily". Four uses of **[convergent]**; here is what
each is worth.

1. **A1/A2/A3 are not three reviewers.** They are three draws from one model on one prompt with a
   coordinator-supplied constraint set. §5's "reached independently by all three blank-slate
   reviewers **[convergent]**" (seeded known-bad books) is **n=1 sampled three times**, not n=3.
   Worse, A1 and A3 have *overlapping* remits (both economics), so the §1.4 "Both blank-slate cost
   reviewers concluded..." is two draws on one question.
2. **The premise generates the conclusion.** Cohort A was "given the product goal and its
   constraints". If those constraints included "a human approves every book" and "long branching
   books", then "human review dominates cost" and "the review surface must be O(1)" are
   *entailments of the brief*, not independent discoveries. Three of the four [convergent] tags
   (path-level safety, human-review economics, seeded known-bad books) fall out of the supplied
   premises for any competent reviewer. Only **C2-7/A1 on continuity as a compute-it-with-a-state-
   ledger problem** is a genuinely non-obvious agreement, and it is the one the synthesis makes
   least of.
3. **Same-file agreement is duplication, not corroboration.** "C4-2 / B2-3 (critical). ... Two
   reviewers found this independently." Both read the same ~20 lines of `api/approval.py`. Reading
   one file twice is not two observations.
4. **The systemic pattern is constructed from the double count.** §2's "seven separate cases" cites
   11 finding IDs across 6 files; several are the same underlying fact (`check_fill_integrity` is
   cited as C5-3 + B2-4 + B1-8 + C6-1). Counting one gap four times and then calling the count a
   "single strongest cross-cutting theme" is circular.

**Net: the convergence claims are worth roughly one quarter of what the synthesis prices them at.**

### Anchoring on the loudest number

| headline claim | actual n |
|---|---|
| "3.2, not 2.3" | 1 pair, 1 tool run, tool has a registered defect (`UW-C225`) |
| "the catalog is convergent across different graphs in different worlds" | 1 control pair, 2 raters, single-model in-family panel |
| "89% of that book's decisions are typographic" | 1 book of 84 |
| "$5.95 per book, 76% human" | 1 reconstruction, 0 measured books, 0 measured reviews, invented price |
| "the reading-level loop was 46% of the bill" | 1 book, by residual subtraction |
| "Spearman -0.982, p=0.0016" | 7 legs x 6 shells, 2 cells, one run |
| "3.0 to 8.3 hours per book" | modelled from word counts; no review was timed |
| "1,874s against a 1,800s RQ timeout" | 1 book |
| "38.9-52.9% delivery" | 3 books, all selected on having passed |
| "the largest measured quality lever" (F3, attacked as confounded) | 21 vs 21 attempts, one cell in the blind arm |

Nine of the ten load-bearing numbers in the review are n≤3. That is not a criticism of the
*programme* (it is an early-stage research programme and says so); it is a criticism of a review
that adopts those numbers as decision-grade when attacking, and calls them underpowered when
defending.

---

## Steelman of the brief

Written as the authors would write it. Where the rebuttal succeeds, I say so.

### Against 1.1: "F5's flagship evidence does not reproduce"

**The rebuttal succeeds on two of three sub-claims, and it is the strongest defence available.**

The programme's pre-registrations compute shared 4-grams **per unit, bodies only**, the
`w16-fill-guide-ablation` design says so verbatim ("shared four-grams per 1000, bodies only,
per-node gramming"). The shipped `check_sibling_fills.py` grams a joined string, an artifact the
register **already documents and schedules a fix for**: `UW-C225` (`AL-309`) says "The convergence
metric grams a joined string, so four-grams spanning a body/label boundary are counted as shared
prose... Compute grams per unit and union the sets."

Re-running the tool reproduces the synthesis exactly (10 grams, 3.2/1000, 2 menu frames). Then I
tested the grams. Of the 10:

- `stay and read the` and `to the basement the` appear in **neither** book C's bodies nor its
  labels, they only exist across a body/label seam. Pure artifact.
- `stay and read the` and `just guess and see` are a **label** in book D against a **body** in
  book C, cross-unit matches per-unit gramming drops.

Recomputing under per-unit scope: **8 shared 4-gram types, 2.55 per 1000.** The margin against the
3.3 idiom floor is **0.75**, not 0.1. So:

1. "The number is 3.2, not 2.3", **rebutted.** The 3.2 is the known-defective scope. 2.55 is
   within noise of the published 2.3 (the exact residual is the leaf-word denominator, which is
   worth pinning, and that is the real recommendation here).
2. "The margin collapses", **rebutted**, since it is a corollary of (1).
3. "The pair shares decisions. F5's evidence violates F5", **overreach.** The two shared menu
   frames are `turn back` and `stay read`, out of 35 choice positions (5.7%), and they are the two
   most generic verbs in the form. Two shared opening-word pairs do not establish that the same
   *decision* was offered; they establish idiom, which is what the idiom floor exists to price.

What the brief cannot rebut, and what the synthesis buried: **the recognition verdicts on the same
pair.** I read them. Both raters: `first_yes_position: 2`, `distinctness_1_to_5: 1`,
`same_adventure: yes`, and the strongest-signal fields name *identical decisions*, not idiom,
"Scene 2 repeats Book One's exact three-way opening choice (wait patiently for a clue / work the
structure with your own hands / ask the old keeper who knew the builder), and every scene after maps
one-to-one onto the same beats, hub, dial, and endings." That is F5's flagship artifact failing on
the criterion F5 is about, and it is devastating. **The synthesis led with the gram count (an
artifact) and filed the verdicts under "Separately".** It anchored on the wrong number and thereby
*weakened* a case it could have made overwhelmingly.

### Against 1.2: "the catalog is convergent"

**Partly succeeds.** The synthesis says "Both readings can be stated; only one is currently
stated." That is false of the evidence document it quotes one sentence earlier.
`recognition-protocol-pilot/results.md` states the catalog-convergence reading explicitly, at
length, and goes further than the synthesis credits: "**The re-based control may therefore not be a
valid negative control at all**: within one band, two catalog-lineage mysteries can genuinely be the
same adventure at the decision level. The original pre-registered control crossed band and world
into a school-garden book precisely to avoid this, and it was the artifact we did not have."

So the criticism is of the brief's one-line summary, not of the programme's analysis. That is a
real documentation defect and worth fixing. It is not the intellectual failure the section's
rhetoric ("read the pilot the other way") implies.

Where the rebuttal fails: the synthesis is right that this is the programme's most direct positive
measurement of its target defect, and right that the brief files it under "instruments that do not
work". Re-filing it is correct. n is still 1 pair, 2 raters, one model family.

### Against 1.3: "the authoring bar is enforced nowhere, and cosmetic choice passes"

**Half succeeds; the half that fails is the cheapest real win in the review.**

- `--strict` in `check_promotion_bundle.py`: **the rebuttal fails.** I verified it independently.
  Zero callers anywhere pass `--strict`; every hit in the tree is a docstring, argparse, comment or
  an unrelated tool; `skeleton_argv = [str(shell_path)]` plus `--allow-mvp` only. There is no
  `strict=True` code path either. This is a genuine, verified, ~1-line gap.
- "76% non-compliant, publish the 64-shell backlog": **rebutted.** `UW-C270` is that census and that
  backlog, re-measured four times against a moving bar, with an owner ruling to author up to the bar
  per cell rather than retrofit legacy shells, closing "DONE 2026-08-19: all 18 offered cells now
  have a strict-passing member." The grandfathering is a decision, not an oversight.
- "Promote `consequence.py` from library to gate": **the review never engaged the ruling that
  already decided this.** `UW-C181` (`AL-249`): "RETIRED, no work to schedule. Both raters reported
  that most forks reconverge with no differing consequence and proposed a per-book illusory-choice
  gate; **the owner ruled that loop-back exploration is a convention of the form rather than a
  flaw**, on the tabletop analogy that sweeping every room is the play." Twelve reviewers and a
  synthesis recommend, as "the cheapest large win on the board", the exact gate an owner considered
  and rejected with a stated rationale, and none of them cites the row.

  This rebuttal does *not* fully dispose of the finding. `UW-C181` is about reconvergent forks; the
  observatory case is stronger, three differently-worded labels to one target with **zero effects
  and zero conditions**, verified, in 102 of 115 decision nodes. That is not "sweeping every room",
  it is a menu with one item. The correct action is **reopen `UW-C181` with this evidence and get a
  fresh ruling**, not ship a gate over a standing one.

### Against 1.4: "the economics do not close"

**Direction survives; magnitude does not.**

Concede immediately: human review dominates, there is no cost-per-book number (`C5-1`), there is no
runtime spend cap (`C5-2`, verified, `_MAX_COST_USD` is a `Decimal("999999.999999")` overflow
clamp in `generation/cost.py:43`), and `TokenUsage` has no stage field. Those are real, unregistered
gaps and among the review's best work.

Reject the multiplier. "Over by 4 to 8.5x... and 13 to 28x" is: an invented $10 price, an invented
70% margin, an invented 3-books/month, and a development config default read as a commercial quota,
multiplied against a per-book cost that is itself a reconstruction from one book. The repo's own
recorded offer shape is $9.99 for **2** credits/month, and commerce is Phase 8 with nothing built.
Meanwhile the review's own §3 concedes the review-hour input is 2.8x pessimistic and does not
propagate the correction into §1.4.

And the "impossibility result" is not new to the programme. It is why `UW-C02`/`AL-036` marked the
review surface blocking against ADR-005 in the first place.

### Against 1.5: "the ranking may be measuring catalog conformity"

**Partly succeeds, on a ground the review did not consider.**

`min catalog distance` is distance to the nearest existing shell. `TAU_CELL` plus the band rules
define a narrow admissible region, and the catalog is by construction the set of graphs inside it.
So a model producing high-distance graphs is producing graphs that are likely *outside the
admissible region*, the correlation is near-definitional, not evidence that the pass bar rewards
imitation of *the catalog specifically*.

But the rebuttal is double-edged and the second edge is worse for the programme: if pass and
catalog-similarity are near-identical, then **the strict bar is itself a conformity bar**, and that
is a more serious problem than a biased model ranking. Neither B3-4 nor the synthesis says this.

Also: the harness **already emits the covariate** in `summary.md`. The recommended re-analysis is a
spreadsheet, not a study, which makes it cheaper than presented and means the programme was not
blind to the variable, it instrumented it.

### The meta-question: did this review read honesty as weakness?

**Yes, in three specific places, and it did so while explicitly disclaiming the error in its own
tone note.**

1. §2 penalises the programme for *not* gating unvalidated instruments, which is F6, the
   principle §5 demands more of.
2. §1.2 says "only one [reading] is currently stated" when the cited artifact states both, at
   length, and self-critiques harder than the review does.
3. B3-2's force comes from a banner the programme's **own tooling prints automatically on every
   run**. The correct finding is "the brief drops a label its harness generates"; the review renders
   it as "F6 is violated inside the document that states F6".

The pattern: the review repeatedly slides between "the brief is wrong" and "the programme is
wrong". The tone note promises exactly this distinction and §1 and §2 do not keep it.

---

## What the review missed

Measured by grepping all twelve findings files. Zero substantive hits for: IndexedDB, offline sync,
personalization, onboarding, internationalization, accessibility, WCAG, screen reader, dyslexia,
read-aloud/TTS, illustration, audio, competitor, market.

**1. The reader-facing product does not appear at all, while the review's headline is "the reader
is absent".** 436 files under `frontend/src`; two findings files mention `frontend/` at all, 10 hits
total. Untouched: `player/` (1,038 backend lines plus the client mirror), the offline/IndexedDB
reading path, `progress/` (686), `notifications/` (1,215), `characters/` (292), `covers/` (1,149).
The review declares the child's experience the framework's central blind spot and then never opens
the code where the child's experience lives. **This is the largest omission.**

**2. `docs/planning/reader-path-engagement-design.md` exists and nobody cites it.** Status
`proposed`, dated 2026-07-25, and its stated goal is verbatim the synthesis's §5 demand: "Which
passages do readers stop at, which endings has nobody ever reached, which choices does nobody
take" and "What makes a reader keep going". It is privacy-constrained against ADR-018 and the
capability register. The synthesis writes "**There is no loop from what children actually read back
into generation**" and files it under "the framework's blind spots as seen by people who could not
be anchored by its history". The loop is unbuilt: I confirmed nothing in `generation/`,
`flywheel/` or `story_requests/` reads ratings or reading outcomes. But it is designed, scoped and
written down, and calling it a blind spot is false.

**3. Reader telemetry and reader feedback already exist and are reported as absent.**
`api/reading_history.py` (endings reached, per-book history, weekly days-read),
`api/reading_time.py`, `api/progress.py`, `api/ratings.py`, and `api/flags.py`, the last being a
**kid-facing structured feedback channel (K15) that feeds the admin moderation queue directly**. The
blank-slate cohort's requirements (completion rate, abandonment depth, re-read rate, guardian
rejection rates) are substantially *computable from data the system already stores*. The review's
structural error: **the 191 blank-slate requirements were diffed against the brief, not against the
repository**, and the synthesis then labels the residue "the framework's blind spots".

**4. §5 contains at least one outright factual error.** "no moral-lesson coda (A2-34)" is listed
under "**Craft rules that are computable and unbuilt**". `scripts/check_prose_craft.py` has
`--max-moral-tags` and a documented "Narrator moral tags" rule, and the brief names it in §3.4. Same
for the tense rules A2 asks for. Nobody checked the blank-slate list against the scripts.

**5. The one experiment that would settle C2-2 is built and unrun.**
`evidence/w16-fill-guide-ablation/` has the full rig, three guide variants, six prompts, a scoring
script, pre-registered questions, and **no `results.md`**. The review makes a causal claim about
the drafting guide (C2-2, critical, promoted to the top-three answer) without noticing that its
falsifier is sitting one command away.

**6. Series and multi-book continuity.** `validator/series.py` exists, the register has series rows,
the external offer design sells "series continuity", and 18 mentions across twelve files are all
incidental. A child's second book in a series is the hardest continuity problem the product has and
nobody looked.

**7. Whether skeleton+fill is the right product bet.** Both blank-slate architects propose
plan-stage combinatorial sampling instead (A1-24..28), and the synthesis files it under §7 as
"unresolved". Nobody costed the alternative, nobody looked at what Inkle-style state-first
authoring would do to the review surface (which is the binding constraint), and no reviewer asked
whether a smaller catalog of *deeper* books beats a larger catalog of shallow ones. For a review
whose top economic finding is "review cost is O(book size)", the product question "make the books
shorter" is never asked.

**8. What happens to a family whose book fails.** B2-8 touches it in one line ("a rejection is paid
for by the family, and nothing tells them"). The live run delivered 3 of 5 books and hit a content
filter on a preschool premise. Nobody looked at `story_requests/` failure UX, retry, or refund of
quota.

**9. Accessibility of generated content.** The project targets WCAG 2.1 AA (ADR-029) and has a CI
gate for it. Nothing in 161 findings asks whether *generated prose* is accessible: reading-level
conformance is measured, but not dyslexia-friendly formatting, read-aloud compatibility, or whether
a screen-reader user can navigate a branching book. `in_band 0.155` on a 16+ book is an
accessibility finding as much as a craft one and is only ever discussed as cost.

---

## Synthesis audit

### Spot-check of the "verified" table (§3)

I re-ran or re-read seven rows. **All seven reproduce.** This is genuinely good and should be said
plainly.

| row | my result |
|---|---|
| `the-observatory-shift.json` 115 decision nodes, 102 single-target | ✅ exact, and stronger: all 102 have zero `effects` and zero `condition` |
| `--strict` callers: zero | ✅ exact; also no `strict=True` code path |
| `check_promotion_bundle.py:322` passes only `--allow-mvp` | ✅ exact |
| `validator/safety.py` Phase-2 stub called from `gate.py:213` | ✅ exact (line 213 in my tree) |
| `imitable.py` zero importers outside its unit test | ✅ exact |
| `covering_paths` only external caller `scripts/measure_per_path.py` | ✅ exact |
| `_MAX_COST_USD` is a `Decimal("999999.999999")` clamp | ✅ exact (`generation/cost.py:43`) |
| D-7b shared 4-grams = 3.2 + 2 menu frames | ✅ the tool prints exactly that, **but see below** |
| largest book 42,233 / catalog max 49,953 at 632 nodes | ✅ 49,953 at `the-last-cartage.json`, 632 nodes, over 84 shells |

### Claims stronger than their evidence

1. **§1.1's headline is the review's own worst instance of the defect it accuses the brief of.** It
   reports a number from a tool whose scope error is registered as `UW-C225`, states the mechanism
   ("counts boundary-straddling grams, which the published figure excludes"), and then builds three
   escalating consequences on the uncorrected figure, including "statistically indistinguishable
   from generator idiom". Corrected: 2.55/1000, margin 0.75. **The section's own §3 verification
   discipline was not applied to its own headline.**
2. **"The evidence for F5 violates F5"** rests on 2 of 35 choice positions sharing the opening words
   `turn back` and `stay read`.
3. **"`gate.py` reads as though safety is covered"** is contradicted by `gate.py` at five lines.
4. **"only one [reading] is currently stated"** is contradicted by `results.md`, which the same
   section quotes.
5. **"$5.95 per book... over by 4 to 8.5x... 13 to 28x"**, every multiplicand is invented or a
   config default, and the section's own §3 correction (2.8x) is not propagated into it.
6. **"the framework's blind spots"** for the §5 list, when at least one item is built
   (`--max-moral-tags`), several are designed (`reader-path-engagement-design.md`), and several are
   computable from shipped telemetry.

### Editorialising beyond what the reviewer said

- C4-8's own text says `UW-C264` records the screen as "half done"; the synthesis §2 renders the row
  as a flat "wired to nothing" with no mention that the judged criterion is **deliberately withheld
  pending validation**, the programme obeying F6.
- C1-1 reports the census; the synthesis adds "The catalog is roughly 76% non-compliant with its own
  stated standard" and "publish the 64-shell remediation backlog", neither of which acknowledges
  `UW-C270`'s owner ruling or its DONE line.
- B3-2 says the *brief* omits a disclosure the harness prints; the synthesis promotes it to "F6 is
  violated inside the document that states F6".
- §1.3's "This is the cheapest large win on the board" is the synthesis's own ranking judgement,
  applied to a recommendation (`consequence.py` as gate) that contradicts a standing owner ruling
  the synthesis does not know about.

### Do the recommendations follow?

Mostly yes, with three that do not:

- **§8.4 "Make `api/approval.py` refuse to publish a book whose moderation report carries a hard
  block."** This **reverses an accepted ADR-005 design**, the classifier becomes a blocking gate
  rather than an advisor to the irreplaceable human, and the synthesis never says so, never cites
  ADR-005's own reasoning, and never mentions the `#CRITICAL` comment stating the decision. It is
  presented as "one conditional closes a three-click bypass". It may well be the right change. It is
  an ADR amendment, not a conditional.
- **§8.7 "promote `consequence.py` to a gate"**, see `UW-C181`.
- **§8.3 "publish the remediation backlog for the 64 non-compliant shells"**, it is published
  (`UW-C270`).

### Is the §8 ranking defensible?

Partly. Items 4, 5, 9, 10 and 12 are well-placed. Item 1 (reconcile the gram scopes) is ranked #1
"cheap and decisive" but is a **tooling repair already registered as `UW-C225`**, and once done it
*confirms* the brief's number rather than overturning it, so it is cheap and **not** decisive. Item
2 (run solution transfer on D-7b) is correctly identified as the cheapest test that could overturn
F5 and is ranked below a repair that cannot. And the single most decisive already-committed evidence
against F5, the two D-7b recognition verdicts at distinctness 1/5 with raters naming an identical
three-way opening choice, **is not an item in §8 at all.**

---

## The top-three ranking

Stated: (1) gate cosmetic choice and enforce `--strict`; (2) fix the fill call configuration
(reading-level loop at 46%, timeout/retry cascade, uncached 594k input); (3) wire the delivery floor
and remove the `drafting_guide` line. Runner-up: path-level evaluation.

**My verdict: one of the three survives intact, one is half right, one should not be in the list.**

- **(1) is half right.** Passing `--strict` in `check_promotion_bundle.py` is verified, ~1 line, and
  genuinely unguarded, keep it, but sequence it after `UW-C272`/PL-18-PL-29 or the bar is
  unsatisfiable at 3-5 and 5-8. "Gate cosmetic choice" should not ship: it contradicts `UW-C181`, a
  standing owner ruling nobody in the review cites. Reopening that ruling with the 102/115 evidence
  is the right move and is a decision, not a build.
- **(2) is three items that are not simultaneously true.** Chunking never fires on the current
  catalog at the shipped cap (live-fill plan F1: 99,906 vs 104,857 tokens), so the 594k chunked-input
  problem and the 120s one-shot timeout problem are alternatives on any given configuration. The 46%
  reading-level figure is n=1 by residual subtraction, not instrumentation. **The timeout is the
  real one, and it is the only item in the whole stated top-three I could not break.**
- **(3) should not be there.** The delivery floor is `UW-C307`, phase 4b, whose own text names the
  exact open question ("whether the deterministic gate carries the check"), it is scheduled work,
  not a discovery. The `drafting_guide` line is a causal claim with no ablation, read out of a
  paragraph whose plain instruction is the opposite, and the rig that would test it is built and
  unrun.

### The top three I would give instead

1. **Read the D-7b recognition verdicts into the F5 decision, today.** Both raters,
   `first_yes_position: 2`, `distinctness: 1/5`, naming an identical three-way opening choice and
   one-to-one scene mapping including the identical crossroads and dial test, on F5's own flagship
   artifact. Cost: zero, the JSONs are committed. This is the programme's own pre-registered
   falsifier firing on its keystone principle, it outranks every gram count, and **it appears
   nowhere in the synthesis's ranked actions.**
2. **Raise `llm_timeout_seconds` above the measured fill distribution and stop classifying fill
   timeouts as transient.** Verified in the shipped configuration; bills up to six cloud completions
   and then downgrades a 16+ children's book to a local 14B model, invisibly, because the output
   still parses. The only hard, live, unregistered production defect in the review that survived my
   attempt to break it.
3. **Fix `check_sibling_fills.py`'s gram scope (`UW-C225`) and restate every published figure under
   one named scope.** This is what actually produced the "3.2 vs 2.3" dispute. Until the shipped tool
   computes the scope the pre-registrations use, no number in §4.3 can be reproduced or compared in
   either direction, including the numbers the review used to attack the brief. Pair it with C3-8's
   missing known-different anchor, without which no instrument has a calibrated far end.

**Runner-up:** pass `--strict` in `check_promotion_bundle.py`, after `UW-C272`.

**Not the runner-up: path-level evaluation.** It is a substantial build (C4-1) whose output is an
instrument nobody has validated, and the programme's own F6, which the review's §5 demands *more*
of, says do not gate on that. Building it before E0/known-answer validation would be the review
recommending precisely the discipline failure it spends §5 condemning.

---

## Findings I would downgrade or withdraw

| ID | from | to | reason |
|---|---|---|---|
| **C1-5** | critical | medium | Message-string formatting in an offline authoring tool; its own category is "authoring ergonomics". |
| **C2-2** | critical | medium | Causal claim ("licenses the shortfall") untested, clauses read against the paragraph's plain instruction, and the ablation rig for it is built and unrun. |
| **C1-1** | critical | medium | `UW-C270` is the census, the owner ruling and the remediation programme, closing "all 18 offered cells now have a strict-passing member". The `--strict`-in-CI half survives; the "76% non-compliant" framing does not. |
| **C4-2 / B2-3** | critical | high, reframed | Behaviour verified but by design under ADR-005, annotated `#CRITICAL` in `node_edit.py`, with `review_surface.py` guaranteeing the BLOCK is never hidden. Reframe to: *no attestation, and a dual-role adult can self-approve*. |
| **C4-5** | high | medium | Self-labelled a Phase-2 stub at five sites; registered twice; safety moved to `moderation/` by design. |
| **C4-3** | critical | high | Real, but a re-discovery of `UW-C02`/`AL-036`, already marked blocking. |
| **B3-4 / synthesis §1.5** | critical | high | The correlation is near-definitional given `TAU_CELL` and the band rules; the covariate is already printed by the harness. |
| **C2-3** | critical | high | Requires the chunked path, which does not fire on the current catalog at the shipped cap; not simultaneously live with C2-4. |
| **C1-3** | critical | high | Catalog-time gate seam; its reader-facing consequence is C1-2, counted separately. |
| **C1-2** | critical | high | Verified and real, but one book of 84 and it collides with `UW-C181`. |
| **Synthesis §1.1, sub-claims 1-3** | headline | **withdraw as stated** | 3.2 is the registered-defective scope; per-unit gives 2.55; the margin is 0.75 not 0.1; "shares decisions" is 2 of 35 generic verb frames. Replace the section with the recognition verdicts, which make the case far better. |
| **Synthesis §1.4 magnitude** | "4 to 28x" | **withdraw the multiplier** | Invented price, invented margin, invented cadence, config default read as commercial quota, and the section's own 2.8x correction not propagated. Keep the direction. |
| **Synthesis §2** | "seven separate cases" | **~four** | Three rows are deliberate F6 staging or brief-disclosed; the count is inflated by citing one gap under four finding IDs. |
| **Synthesis §5 "Craft rules... unbuilt"** | - | **correct the list** | A2-34 (no moral-lesson coda) is built (`--max-moral-tags`); the tense rules are built; the list was never checked against `scripts/`. |
| **All A3 §6.3 scale findings** | - | **defer** | 10k/100k/1M subscriber FTE tables against a system with no commerce and no subscribers. |

## Findings I would upgrade

| ID | from | to | reason |
|---|---|---|---|
| **B3-1 / C3-1 (D-7b recognition verdicts)** | supporting evidence, "Separately" | **the review's single most important finding** | Both raters, first-yes at scene 2, distinctness 1/5, naming an identical three-way opening choice and one-to-one scene mapping. It is the programme's own pre-registered falsifier firing on F5's flagship artifact, it needs no instrument repair, and it is not in the ranked actions at all. |
| **C6-4 (register integrity)** | high | **critical, with a concrete instance the review missed** | I found a live one: `UW-C290` is marked "**DONE**, verified against the tree 2026-08-18", and one of its four REMOVE items was "SAFE-14's entry in the live application order while `validator/safety.py` is a stub". The call is still at `gate.py:213` and still in the docstring's numbered order at `gate.py:33`. So a row is marked done against a change that did not land, exactly C6-4's mechanism, demonstrated on real data rather than a fabricated ref. This also makes `UW-C270`'s and `UW-C264`'s status lines load-bearing and unverified. |
| **C5-1 / C5-2 / C5-13 (no cost-per-book, no spend cap, no stage attribution)** | high/medium | **high, and genuinely unregistered** | These are the cost findings with **no** UW row (I grepped: zero hits for spend cap, cost-per-book, budget cap, `TokenUsage`). Unlike most of §1.4, they do not depend on an invented price. They are the review's best economic work and are buried under the multiplier that is wrong. |
| **C3-8 (every instrument anchored only at the "similar" end)** | high | **critical** | This is the common cause of all three instrument failures *and* of the 3.2-vs-2.3 dispute *and* of the recognition control's invalidity, which `results.md` itself identifies. It is the root of §1.1, §1.2 and §7's open question, and it is filed as a supporting bullet in §4.1. |
| **B2-23 (F3's tool-assisted regime exists as code nowhere)** | high | **critical** | The brief's single largest measured quality lever is a practice, not a mechanism. It cannot be run reproducibly, cannot be scaled, and cannot be handed to anyone. Every §4.2 conclusion and the entire F4 model recommendation depend on a regime with no implementation. This is a bigger structural problem than any of the five headlines. |

---

## Verdict on the review as a whole

It is a good review with a bad headline. The verification discipline in §3 is real and reproduced
perfectly on every row I re-ran. B3-2, C3-4, C2-4, C6-4, B2-23 and the cost-instrumentation cluster
are findings a programme should want. The retraction of the four absence-based findings after the
evidence worktree arrived is exactly right and honestly disclosed.

Its failures are systematic and they all point the same way: **it was told to be adversarial and it
optimised for that.** 65% of findings in the top two severity bands. 40% of findings framed as
absences, at least 15% of them restating rows the register already carries. Three uses of
[convergent] that are entailments of a supplied premise, and a blank-slate "cohort" that is one
model sampled three times. A §1.4 magnitude built from four invented numbers. And a §1.1 headline
that reports a figure from a tool the register already flags as defective, states the defect, and
reasons from the figure anyway, while the far stronger evidence for the same conclusion sits
unranked in the same evidence directory.

The programme's honesty was, in several places, read as weakness: it was penalised for not gating
unvalidated instruments (F6), for a disclosure banner its own harness prints, and for a
self-critique the review then claimed it had not made.
