---
title: "Review-model distillation plan: a small, pinned, self-hosted judge, earned per criterion"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Design the work to distil the validated part of the review panel into a fine-tuned open-weight
  model, with pre-registered decision rules per phase and every expensive artifact frozen for re-distillation."
tags:
  - planning
  - research
  - measurement
  - distillation
component: Research
source: "cyo-measurement-workplan-2026-08-12.md sections 7.7 and 7.8; AL-367 through AL-385; UW-C236, UW-C239, UW-C254 through UW-C258"
---

# Review-model distillation plan

> **Date**: 2026-08-14
> **Derived from**: [measurement workplan](./cyo-measurement-workplan-2026-08-12.md) sections 7.7 to 7.8,
> [authoring lessons log](./authoring-lessons-log.md) `AL-367` to `AL-385`,
> [unscheduled work register](./unscheduled-work-register.md) `UW-C236`, `UW-C239`, `UW-C254` to `UW-C258`
> **Status**: draft, pending owner sign-off. Register rows are added on sign-off, not before.
> **Serves**: `A11` (structural and prose quality tooling across the corpus). The distilled judge is a
> *measurement instrument* for the research and authoring harness. It does not touch `A6` (the admin's recorded
> approval remains the only path from generated content to a child, ADR-005) and it does not replace any part of
> `S7`'s moderation pipeline. Nothing in this plan changes what a child can be shown.

## 0. What is being distilled, and why the answer is not "the panel"

The review agent under discussion is the blind judge panel in `scripts/judge_books.py`: seven anchored 1-to-5
criteria (`_CRITERIA`), scored by three frontier models, used by the measurement programme to rank books and by
W7 to validate itself. Distillation here means training a small open-weight model to reproduce the *validated
subset* of that instrument, self-hosted, pinned, at temperature 0.

Three findings from the 2026-08-14 W7 close define the target, and each narrows it:

1. **The unit is the criterion, not the panel.** Five criteria support a ranking, one is untested, one is
   under-powered (workplan 7.7.6, `AL-385`). A student trained to imitate "the panel" would imitate the broken
   parts with the same fidelity as the working ones. Every phase below is therefore per criterion.
2. **The instrument supports within-book delta comparisons, not absolute scoring.** With the drifting judge
   excluded, only `imagery` (+0.82), `ending_quality` (+0.73), `engagement` (+0.65) and `choice_quality`
   (+0.63) clear the 0.60 weighted-kappa floor on absolute scores between the two stable judges; `age_fit`
   sits at +0.51 even while detecting its defect 6 of 6 (replay of `out/w7/verdicts.json` with
   `--exclude-judge judge-gemini-3.1`, 2026-08-14). The student is therefore trained and validated **for the
   delta use**: ordering two versions of a book on one criterion. Absolute calibration is out of scope until a
   consumer needs it, and no claim in this plan may quietly widen into one.
3. **The strongest argument for distillation is determinism, not cost.** One frontier judge drifts 0.64 mean
   and 2.00 max on unchanged control books between runs, against a 0.5 detection margin; the two stable judges
   drift 0.14, and excluding the drifter cut every noise floor 2x to 6x (workplan 7.7.6, `AL-380`, `AL-381`,
   `UW-C258`). A pinned-weights local judge decoded greedily at temperature 0 removes run-to-run drift as a
   *class* of noise. Cost is real but secondary: 129 frontier scorings cost about $2.60 (workplan 7.7.5), so
   the panel is not expensive; it is unstable, unpinnable, and subject to other people's routing. The floating
   `~vendor/model-latest` aliases move across both checkpoint and serving provider without notice
   (`judge-panels/open-weight-candidates.json`), and this account's own data policy can silently remove a
   judge's serving stack (`AL-384`). A measuring instrument whose identity is not under our control cannot
   support a longitudinal quality claim, and every instrument in the current panel has that property.

**Relation to the earlier deferral.** The workplan's section 5 deferred "fine-tuning anything on the Thinking
Machines credit" because every proposed use trained on an unvalidated instrument, and because the credit
cannot touch the generation model (no DeepSeek-V4 in the Tinker catalogue; verified 2026-08-12). Both reasons
have now expired for *this* use and only this use: W7 has validated the instrument per criterion, so training
on its keeps is no longer laundering a saturated score into weights; and a judge, unlike a generator, is
exactly the "different, smaller companion model" the deferral said nothing then needed. The deferral's warning
is retained as this plan's trap 1.

### 0.1 The evidence base, verified

The figures below were re-derived on 2026-08-14 from the frozen artifact, not quoted from memory:

```bash
uv run python scripts/w7_battery.py --replay out/w7/verdicts.json --exclude-judge judge-gemini-3.1
```

| Criterion | Defect | Detected | Median delta | Noise floor | Teacher-pair kappa (absolute) | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `imagery` | `imagery_flat` | 6/6 | -2.00 | 0.24 | +0.82 | KEEP |
| `age_fit` | `reading_level_up` | 6/6 | -1.75 | 0.35 | +0.51 | KEEP (delta use only) |
| `ending_quality` | `ending_truncated` | 6/6 | -1.25 | 0.12 | +0.73 | KEEP |
| `choice_quality` | `false_choice` | 5/5 | -1.00 | 0.24 | +0.63 | KEEP |
| `engagement` | `premise_duplicate` | 4/6 | -0.50 | 0.12 | +0.65 | KEEP, marginal |
| `voice` | none valid | - | - | 0.35 | +0.58 | UNTESTED (`AL-382`) |
| `dialogue` | `dialogue_flat` | 1/2 | -0.75 | 0.00 | +0.49 | under-powered, confounded |

W4 independently flags `dialogue` at cell spread 0.00 and flags nothing else (workplan 7.8); two instruments
on different corpora corroborate (`AL-385`).

## 1. How an item earns its place

The three admission constraints of the measurement workplan apply unchanged: every item carries a decision
rule written before it runs and able to return "drop"; no rule may appeal to the *student* until the student
has passed its own battery (the same discipline that blocked ranking claims on W7); and no measure is promoted
to a gate for being computable (`AL-337` by inheritance).

Four operating rules are inherited from this fortnight's lessons and bind every item below:

- **Every paid step runs under a `single_run` lock and never retries on absent output** (`UW-C254`, `AL-375`).
- **Every artifact this plan produces is written to a tracked path by default** (`UW-C257`, `AL-379`). The cost
  that matters is not what a run cost to produce but what it would cost to reproduce.
- **No cost column prints a dollar figure from an unpriced estimate**; until `UW-C239` closes, spend is
  measured against the provider balance and the tables say so (`AL-374`).
- **Every availability claim about a candidate model comes from `probe_callable`**, an actual call classified
  as ok / data-policy / no-endpoints / unknown-slug, never from a catalogue listing (`AL-383`, `AL-384`).
  Floating aliases are disqualified as instruments outright; only dated checkpoints enter any slate.

## 2. Tiering: which criteria are distilled, which are not, and why

Not every criterion should be distilled, and pretending otherwise would rebuild the panel's weaknesses in
weights, where they are harder to see (workplan section 5's own warning). Assignment, from the W7 and W4
evidence:

### Tier D: deterministic, never distilled

Properties with a deterministic measure that has **passed its own sensitivity check** stay deterministic, per
the narrowed `UW-C236` remedy and the `AL-367` rule that "deterministic" is not a synonym for "correct":

| Property | Instrument | Sensitivity evidence |
| --- | --- | --- |
| Narrative tense stability | `check_prose_craft.py` tense checker | `AL-369`; `tense_break` unmapped from the judge per `AL-382` |
| Dialogue presence and share | `validator/dialogue.py` | rebuilt and span-tested after `AL-367`/`AL-368`; one detector behind all four callers |
| Reading level | `validator/reading_level.py` | W2 keep, path-scoped, with the concentration effect demonstrated |
| Fork structure (false choices, reconvergence) | `validator/consequence.py` (W3) | keep as reported statistic, discriminates on the catalogue |
| Premise convergence | shared four-gram measure | calibrated against the 3.3 idiom floor |

A student judge is never trained on these properties and never asked about them; asking it would be preferring
the more expensive, less checkable instrument, which inverts the house rule.

### Tier 1: distillation targets

`imagery`, `ending_quality`, `age_fit`. All three detect 6 of 6 with medians 3x to 10x their noise floors and
survived a change of run (workplan 7.7.5, 7.7.6). `age_fit` carries a stated restriction: its teacher-pair
absolute agreement is +0.51, below floor, so it is distilled **for delta use only** and no absolute `age_fit`
claim may be made by the student or its consumers.

### Tier 2: conditional targets

- `choice_quality` (5/5, -1.00 against 0.24). Conditional because it half-overlaps Tier D: the *structural*
  half of "do the branch points matter" is W3's, deterministic and already kept. What the judge adds is the
  semantic half, options that are cosmetic restatements of each other while pointing at different nodes, which
  no graph measure sees. The student inherits only the semantic half, and RD5 must show the teacher signal for
  it survives on arms whose structure W3 calls clean.
- `engagement` (4/6, -0.50 against 0.12). Marginal by the workplan's own reading; distilled only if RD5's
  teacher-consistency gate passes, and flagged as the first criterion to drop if data volume binds.

### Tier 3: no trustworthy teacher signal; excluded from distillation

- `voice`: UNTESTED. Its only arm was a wrong hypothesis (`AL-382`); no valid defect mapping exists. Distilling
  it would distil an unvalidated signal. Precondition, not scheduled here: design a voice-targeting seed
  (e.g. swapping the protagonist's reactions across characters), validate it through W7, then revisit.
- `dialogue`: under-powered at n=2 with the one miss explained by the rubric's own narration-led anchor
  (`AL-382`), and flagged saturated by W4 twice (`AL-385`, `UW-C236`). Preconditions: reword the rubric so
  "legitimately narration-led" and "had its dialogue removed" are distinguishable, and get dialogue-bearing
  books into the battery (the corpus carries 17 of 23 with dialogue since the detector was fixed, so this is
  now a fixture choice rather than a corpus gap). Until both land, the criterion has no signal to distil.

**Pre-registered consequence of the tiering.** The student ships with a declared observation set, wired into
the W6 blind-spot manifest mechanism: the criteria it does not score are listed as unobserved, exactly as the
four qualitative age dimensions are today. A student that silently answers on `voice` or `dialogue` fails RD7
regardless of its other results.

## 3. Artifact preservation: the re-distillation contract

This section is a requirement, not an appendix. The governing fact is `AL-379`: the loss of one untracked
directory (`out/vendor-comparison/`) has now degraded four separate measurement items, and the 84-verdict pool
it held is unreproducible at any price because the judges that produced it will not exist at those checkpoints
again. Distillation multiplies that exposure: a student model is a function of its teacher verdicts, its
corpus, its rubric version, its splits and its hyperparameters, and losing any one of them means the next
distillation (new base model, revised rubric, grown corpus) starts from zero instead of from a diff.

**The test the layout has to pass**: a fresh checkout, with no access to any frontier model that has since
retired, must be able to (a) regenerate every derived artifact bit-identically from the frozen ones, and
(b) train and evaluate a *new* student against the *same* labels, splits and battery, so that "better than the
last student" is a measurement rather than a vibe.

### 3.1 Layout

All tracked, following the `out/w7/` precedent (its corpus, paid rewrites and verdicts are already in git;
only the regenerable `arms/` is ignored):

```text
out/distillation/
  MANIFEST.json      # the root: content hashes and generator commits for everything below; the one file a
                     # re-distillation starts from. CI-checked: a hash mismatch or dangling reference fails.
  corpus/            # frozen copies of every book any pair references, at the exact bytes judged. IMMUTABLE.
  rewrites/          # the paid generation rewrites (harden/, flatten/) per book, full strength. IMMUTABLE:
                     # these are the raw material every ladder is blended from, already paid for once.
  arms/              # REGENERABLE: mechanical seeds and blends, derivable from corpus/ + rewrites/ + the
                     # seeder at the pinned commit recorded in MANIFEST. Stored anyway (cheap), but audited
                     # by regeneration, never edited.
  pairs/             # the labelled pair and ladder corpus, JSONL. One row per ordered pair:
                     # {pair_id, criterion, band, unit: book|path|node, a_ref, b_ref (hashes into corpus/
                     # arms/), relation, severity_rung, provenance: seeded|teacher_ranked|natural,
                     # generator_commit, split}. IMMUTABLE once a training run has consumed it; corrections
                     # append a superseding row, never rewrite.
  teacher/           # teacher verdicts, raw and per judge, never only pooled (AL-381): scores, notes, model
                     # slug, checkpoint/date, provider actually served (from response metadata, not the
                     # request), prompt_version, rubric_version, repeat index. IMMUTABLE and irreplaceable:
                     # a retired checkpoint's opinion cannot be re-bought at any price.
  rubric/            # versioned rubric and prompt templates: _CRITERIA text, _system_for template, _prompt
                     # shape, band-phrase logic, each version content-addressed. Needed because a one-word
                     # prompt change makes pools non-comparable (the "5 to 8" hardcoding cost us exactly
                     # this; judge_books.py item 5). IMMUTABLE per version.
  splits/            # train/validation/test membership BY BOOK (never by arm: every arm of a book shares
                     # its book's split), plus the generating rule: RNG seed, stratification by band and
                     # node count. IMMUTABLE. The six W7 battery books are assigned test forever (3.4).
  holdout/           # the naturally-occurring failure set: books or nodes a human sent back at review, with
                     # the send-back reason. Never enters any train or validation set, ever. The only data
                     # not produced by our own seeder, hence the only check on trap 2. IMMUTABLE, append-only.
  eval/              # per evaluation run: the verdicts file, harness commit, exact replay command, panel or
                     # student identity. Every number this plan ever reports must be replayable from here at
                     # zero cost, the way section 0.1's table was replayed from out/w7/verdicts.json.
  training/          # per training run: base model id AND weights revision hash, tokenizer hash,
                     # hyperparameters, data manifest hash, training-code commit, loss curves, and the
                     # adapter weights themselves (LoRA adapters are megabytes and are committed; any
                     # full-weight artifact goes to the R2 bucket with its hash and retrieval path recorded
                     # here, following the supabase-backup marker discipline).
```

### 3.2 What must be immutable versus what may be regenerated

| Class | Members | Why re-distillation dies without it |
| --- | --- | --- |
| Immutable, irreplaceable | `teacher/`, `holdout/` | teacher checkpoints retire (the 84-verdict pool is the proof); human send-backs cannot be re-elicited |
| Immutable, expensive | `rewrites/`, `corpus/` | a *re-generated* rewrite is different text, silently changing every ladder built on it |
| Immutable, identity-bearing | `rubric/`, `splits/`, `pairs/`, `eval/` | free to recreate *differently*, which is the failure: new splits or a reworded rubric is a new experiment in the old one's name |
| Regenerable | `arms/`, blends, derived statistics | deterministic functions of immutable inputs at a pinned commit; MANIFEST records the function, CI re-derives and compares |

### 3.3 Enforcement

- `MANIFEST.json` is checked in CI the way the lessons log is: hashes verified, references resolved, and any
  file under an IMMUTABLE directory whose hash changed fails the build.
- Mutation test, in the W6 style: delete one rewrite file locally and the manifest check must fail; regenerate
  one arm with a modified seeder and the regeneration audit must fail. If either can be made to pass, the
  manifest is a false assurance and gets fixed before anything else runs.
- Every harness this plan adds takes `--scratch` to write elsewhere; the default is the tracked store. This
  inverts today's default, per `UW-C257`.

### 3.4 The battery books are test data forever

The six W7 corpus books (`the-lost-mitten`, `the-clover-and-the-butterfly`, `the-teddy-bears-picnic`,
`the-lantern-festival`, `the-backyard-treasure-map`, `the-cave-of-echoes`), their paid rewrites and their
43-arm battery are already tracked under `out/w7/`. They are assigned to the test split permanently and no
student may train on them or on any arm or ladder derived from them. This costs us their already-paid rewrites
as training data, and buys the only thing worth more: an acceptance battery whose frontier baselines are
already measured (section 0.1) and which no student has ever seen.

## 4. Data budget: what the generator can actually yield, said plainly

**The corpus.** 23 filled books are committed at `out/*.filled.json`, spanning 3-5 (3 books), 5-8 (2), 8-11
(3), 10-13 (4), 13-16 (6), 16+ (5), from 11 to 551 nodes (counted 2026-08-14 from the tracked files). Not all
pass: two are pre-schema-v2 and blocked by L1-7 branch depth after mechanical migration (`AL-372`), and the
usable count under `fill_result` context is roughly 20 to 21, with the exact census a Phase 0 deliverable
(RD2). Six of those are the frozen battery (3.4), leaving **about 14 books for training and validation**, and
their band spread is bottom-light: the youngest bands are concentrated in the battery, so training data skews
8-11 through 16+ while the acceptance battery spans 3-5 through 10-13. That asymmetry is stated here so nobody
discovers it as a finding later.

**Yield per book.** The seeder plus blenders are a known-answer generator with three multipliers:

- *Arms*: control plus up to 7 defect arms per book (5 mechanical, free; 2 generation-seeded at measured
  $0.85 for 224 calls over the six small battery books, so the 14 larger training books are estimated at
  $5 to $15; estimate, priced against the provider balance per `AL-374`).
- *Ladders*: `blend_to_grade` and `blend_to_density` compose arbitrary severities from one paid rewrite at
  zero marginal cost (`--reblend` calls no provider; `AL-373`). Three rungs each (+1/+2/+3 grades; keep
  0.7/0.4/0.2 density) triple the reading-level and imagery arms for free. The mechanical seeds are
  parameterisable the same way (tense share, endings truncated, forks repointed), giving 2 to 3 rungs each.
- *Units below the book*: `rewrites/` holds per-node (original, hardened) and (original, flattened) body
  pairs, roughly 213 to 224 nodes per seed type on the battery corpus alone, and W1's `path_bodies` can cut
  book arms into path-scoped units for the prose criteria. These are auxiliary signal only; `choice_quality`
  and `ending_quality` are meaningless below the book, and the `AL-342` rule applies: any per-unit measure
  needs its threshold re-derived at the new denominator.

**The arithmetic, as an estimate.** 14 books x 4 target criteria x ~3 rungs gives roughly 170 seeded ordered
ladder pairs at book scope; teacher-ranked cross-book pairs (pairs of different books whose teacher delta on a
criterion exceeds that criterion's noise floor) add up to 91 same-criterion pairs per criterion before
filtering, perhaps a third usable; node- and path-scoped auxiliary pairs add several hundred more for
`imagery` and `age_fit`. Order of magnitude: **500 to 1,500 usable ordered pairs**, concentrated in two
criteria.

**Is that enough?** For the stated target, a LoRA adapter on a small instruction-tuned base, learning a
*pairwise ordinal* task per criterion, it is plausibly sufficient: the task is narrow, the base model already
reads, and the label is an ordering rather than a calibration. For anything more, it is not: absolute-scale
calibration, band-general claims, or criteria beyond the top three would need the corpus the flywheel is
supposed to grow. This plan does not assume the favourable answer; RD6 carries a pre-registered learning-curve
rule that halts training and says "grow the corpus first" the moment the data, rather than the method, is the
binding constraint. Growing the corpus means generating books, which is the expensive half of this programme
(wall clock estimated at roughly ten minutes per book from the vendor-comparison runs, plus gate attrition),
and pretending pairs are free would hide that behind the seeder.

## 5. The traps, and where each is caught

**Trap 1: distilling the teacher's blind spots.** A student imitates its teacher's misses as faithfully as its
hits, and a preference model fitted to a saturated criterion launders the saturation into weights where it is
far harder to detect than in a score column (workplan section 5). Caught by: the tiering (section 2), which
admits only criteria with two-instrument evidence; the blind-spot declaration (the student names what it does
not observe, W6 mechanism); and the `holdout/` set, the only labels our seeder did not write.

**Trap 2: learning "this text was tampered with" rather than the property.** The arms are not single-defect
documents (`AL-377`, `UW-C255`): `reading_level_up` genuinely moves voice and imagery, `premise_duplicate`
genuinely moves engagement, and every mechanical seed has a mechanical signature a model could learn instead
of the property. Caught by: severity ladders, because a tamper detector fires equally at every rung while a
property judge must order them (RD7's monotonicity gate); provenance mixing, because teacher-ranked natural
pairs and human send-backs carry no seeder signature; and the holdout sign-agreement gate, where a student
that aces seeded arms and fails natural pairs is convicted of learning the seeder.

**Trap 3: band conditioning.** The rubric is band-parameterised and the corpus spans 3-5 to 16+; the panel ran
off-prompt on a hardcoded band for its whole first pool (judge_books.py item 5). A student can satisfy every
in-band metric while ignoring its band input entirely, because band correlates with style in this corpus.
Caught by: band recorded on every pair; the RD7 band-swap probe (the same text judged under its own band and
an adjacent one must move `age_fit` in the direction the rubric implies); and the scope rule that adoption
claims extend only to bands the acceptance battery covers (3-5 through 10-13 today; extending to 13-16 means
seeding arms on a held-out older book, `the-thornwood-trial` being the named candidate, with its roughly 27k
input tokens per scoring priced in).

**Trap 4: quantisation effects within noise.** Self-hosting means quantising, and run-6 nearly published a
22-point "quantisation effect" that was one book's discarded repair (`AL-349`). Caught by: RD8's rule that a
quantised build is adopted only if every per-criterion verdict is unchanged and the noise floor moves at most
0.1, with any single-book regression checked against the drop-worst column (`UW-C246`) before being attributed
to quantisation.

**Trap 5: teacher selection and pinning.** A panel mean hides a bad member (`AL-381`). The teacher is the two
stable judges, `judge-gpt-5.6` and `judge-grok-4.6` (drift 0.14 against the drifter's 0.64 mean and 2.00 max),
recorded per judge so the membership decision stays revisable. Every teacher verdict pins model, checkpoint
date, and the provider that actually served the call; a verdict whose serving metadata is missing does not
enter `teacher/`.

**Trap 6: availability and identity of the base model.** Callable, real-but-unserved, blocked-by-our-own-policy
and unknown-slug are four different states with four different remedies (`AL-383`, `AL-384`), and a floating
alias is none of them and worse than all of them. Caught by: `probe_callable` pre-flight on every slate before
any paid pass; dated checkpoints only; and for the eventual student base, a further requirement the API checks
cannot see: **weights downloadable under a licence permitting local fine-tuning and self-hosted commercial
use, pinned by revision hash before training starts.** The data policy that blocks some serving stacks is a
standing constraint correct for a children's product; candidates it blocks are dropped, and the policy is
never relaxed for a measurement convenience.

## 6. The work

Ordered cheapest-first; the free and deterministic items run before anything paid, and Phase 1 exists to make
Phase 3 unnecessary. Costs are money plus wall clock; dollar figures are measured where cited, estimates where
marked, and always read against the provider balance until `UW-C239` closes.

### Phase 0: free and deterministic

#### RD1. The frozen store and its manifest

**Infrastructure, not a candidate.** Everything else writes into it.

*Build.* The section 3 layout, the manifest writer, the CI hash check, and the migration of the existing
`out/w7/` artifacts (corpus, rewrites, verdicts, replay commands) into it as the first frozen generation.

*Test.* The two mutation tests of 3.3: a deleted rewrite and a modified-seeder regeneration must each fail
the check. A clean checkout must rebuild `arms/` bit-identically from `corpus/` + `rewrites/` + the pinned
commit.

*Decision rule.* Infrastructure ships without a keep/drop rule, but with the W6 discipline: **if the manifest
cannot be made drift-proof against the mutation tests, it is demoted to a documentation-only inventory and
this plan's reproducibility claims are weakened in writing**, because a manifest that lies converts an unknown
gap into a false assurance.

*Cost.* Zero spend, one to two days.

#### RD2. Corpus census and frozen splits

*Build.* Run the gate over every committed filled book under `fill_result` context; record pass/fail and
reason per book; assign train/validation/test by book, stratified by band and node count, seeded; the six
battery books are pre-assigned test (3.4). Freeze into `splits/`.

*Test.* Re-running the assignment with the recorded seed reproduces the membership exactly; no book appears
in two splits; no arm's split differs from its book's.

*Decision rule.* **If fewer than 12 gate-passing non-battery books exist, Phase 3 is blocked** and the plan's
next action is corpus growth, not training; bands with zero test-split books are named in the manifest and
excluded from every adoption claim. This rule can return "stop before spending" and that is its point.

*Cost.* Zero spend, half a day.

#### RD3. The ladder generator

*Build.* Extend `seed_defects.py` and the `w7_battery.py` blenders to emit graded severities per defect (three
rungs for the two blended seeds; parameterised strengths for the mechanical ones) plus the `pairs/` manifest
rows, provenance and split included. Deterministic; consumes existing `rewrites/` where they exist. The
non-landing rule is inherited: a rung whose seed did not land is withheld and named, reducing n rather than
manufacturing a zero (`AL-370`).

*Test.* On the tracked `out/w7/harden/` rewrites, every emitted ladder's rungs are confirmed strictly ordered
by the defect's own deterministic verifier (`verify` at each rung), and the pair manifest round-trips: each
row's `a_ref`/`b_ref` resolve and the claimed severity ordering matches the verifier's.

*Decision rule.* **Keep ladders as graded training data iff at least 90 percent of generated ladders verify
strictly ordered rungs; below that, ladders collapse to their strongest rung and training proceeds on binary
pairs only**, because an unordered ladder teaches the ordering task noise. Applies per defect type, so one
badly-behaved seed does not take the others' gradations with it.

*Cost.* Zero spend for the code and the battery-corpus dry run, two to three days.

### Phase 1: the cheap paid pass that could end the plan

#### RD4. Zero-shot open-weight battery

Do not assume the answer is "train a model". `w7_battery.py --panel` was built for exactly this (its
`load_panel` docstring says so): run each candidate in
[`judge-panels/open-weight-candidates.json`](./judge-panels/open-weight-candidates.json) as a one-judge panel
over the frozen 43-arm battery, twice, plus a repeated pass over the six controls for a drift measurement.

*Build.* A slate pre-flight via `probe_callable` (trap 6), then per candidate: two full battery passes and the
control repeats, written to `eval/` with full identity metadata. The floating `deepseek-flash-latest` alias
runs beside its pinned `deepseek-flash-0731` twin precisely to measure whether the float matters, per the
slate's own note; only the pinned entry is eligible for adoption.

*Test.* The replay of each candidate's verdicts reproduces its table; the frontier teacher-pair baselines for
comparison are the section 0.1 figures, replayed not retyped.

*Decision rule, pre-registered in full.*

- **Adopt a zero-shot candidate outright, and skip Phase 3, iff** on the frozen battery it (a) matches the
  teacher pair's KEEP set on every Tier 1 criterion with median deltas clearing the same per-criterion noise
  floors, and (b) shows repeat drift on unchanged controls of at most 0.25 mean per criterion, half the
  detection margin. Fine-tuning a model that already does the job is spend without a question attached.
- **Drop a candidate from all further consideration iff** it detects at or below 0.5 on every Tier 1
  criterion in both passes.
- **If `glm-5`, the slate's capacity ceiling, also detects at or below 0.5 on every Tier 1 criterion**,
  record that zero-shot open-weight judging fails on this task at this scale, and Phase 3 may proceed only
  with RD6's learning-curve guard armed, because the remaining hypothesis is that fine-tuning closes what
  scale did not, and that hypothesis now carries the burden of proof.

*Cost.* Estimate under $5: roughly 8 slate entries x 2 passes x 43 arms plus control repeats, at the slate's
listed $0.08 to $0.95 per MTok input on books of 663 to 4,906 words. Wall clock: an evening. (The prior
measured anchor: 129 frontier scorings cost about $2.60; these models are 10x to 100x cheaper per token.)

### Phase 2: labels

#### RD5. Teacher label pass over the training corpus

*Build.* Generation rewrites (harden and flatten) for the ~14 training books, then RD3 ladders over them, then
the teacher pair (`judge-gpt-5.6`, `judge-grok-4.6`, gemini-3.1 excluded per trap 5) scores every unit **at
least twice** (`UW-C258`: an instrument run once cannot distinguish its noise from its signal), per judge
recorded, into `teacher/`. Teacher-ranked cross-book pairs are then derived: same criterion, teacher delta
beyond that criterion's noise floor, both repeats agreeing on sign.

*Test.* Every teacher verdict carries complete identity metadata or is rejected at write time; ladder rungs
withheld by RD3 have no teacher rows; the pair-derivation is a pure function of `teacher/` and reproduces
bit-identically.

*Decision rule.* **A criterion's labels enter training iff the teacher pair (a) orders that criterion's
ladder rungs correctly on at least 80 percent of ladders and (b) shows repeat drift on that criterion at or
under 0.25.** A criterion failing either has no signal worth distilling, whatever W7 said about its
detection: detection at one severity is not the same claim as a usable ordering, and a teacher that cannot
order its own rungs would teach the student its confusion. Such a criterion moves to Tier 3 and its
frontier-pair scoring continues unchanged.

*Cost.* Estimate $40 to $120: the rewrites at $5 to $15 (scaled from the measured $0.85 over six small
books), then roughly 250 units x 2 judges x 2 repeats = 1,000 scorings, where the per-scoring anchor of about
$0.02 (7.7.5) understates the large books, some of which run to hundreds of nodes. Wall clock: one to two
days including verification. This is the plan's largest spend, and it is also the purchase of the permanent
`teacher/` asset that every future re-distillation reuses for free.

### Phase 3: the student

#### RD6. Training

*Build.* LoRA fine-tuning of the RD4-surviving candidate base (or, absent a survivor, the cheapest catalogued
base: the Tinker catalogue's Qwen3-8B at $0.44/MTok, verified 2026-08-12 in the workplan's deferred table,
with DeepSeek-V3.1 at $3.718/MTok as the larger fallback). Task format: given the criterion's rubric text, the
band, and two texts, output which is worse on that criterion and a coarse margin bucket. One adapter per
criterion or a shared adapter with per-criterion heads; that choice is an experiment inside RD6, decided on
validation pairs, never on the battery. Tokenizer, hyperparameters, data hash and code commit frozen into
`training/` per run.

*Test.* Reproducibility first: the same manifest, seed and hyperparameters retrain to validation metrics
within run-to-run tolerance on the training stack before any result is read. The acceptance battery is not
touched during training; it is scored once per frozen candidate student, and that look is logged in `eval/`.

*Decision rule (the learning-curve guard).* Train at 50, 75 and 100 percent of pairs. **If validation
pairwise accuracy at 100 percent exceeds accuracy at 75 percent by more than 2 points, data is the binding
constraint: stop, record it, and route the next dollar to corpus growth rather than to hyperparameters.**
This is the honest answer to section 4's volume question, decided by measurement instead of optimism.

*Cost.* Estimate $5 to $30 on the Tinker credit at catalogued rates for tens of millions of training tokens,
or homelab GPU time under ADR-004 at zero marginal spend; days of wall clock either way.

#### RD7. Acceptance, which is W7

The battery already exists, its frontier baselines are measured, and its books were never trained on. "As
good as the teacher" is therefore quantitative, per criterion, against section 0.1.

*Build.* Run the frozen student as a one-judge panel over the 43 arms (one command, existing harness), plus
three probes the frontier run never needed: repeat determinism (the full battery scored twice on the serving
stack that will host it), the band-swap probe (trap 3), and the natural-holdout comparison.

*Decision rule, per criterion, all five gates required.* **Adopt the student for a criterion iff:**

1. detection rate on the criterion's defect arms is at least the teacher pair's (section 0.1 column 3);
2. median delta is within one teacher noise floor of the teacher's median;
3. repeat drift on unchanged controls is at most 0.1 at temperature 0 on the hosting stack, and any nonzero
   drift is explained (batching nondeterminism, kernel choice) before adoption rather than after;
4. held-out ladder rungs are ordered correctly on at least 80 percent of ladders (the anti-tamper gate:
   a seeder-signature detector cannot order severities);
5. on `holdout/` natural pairs whose teacher delta exceeds the noise floor, sign agreement with the teacher
   is at least 80 percent (the second anti-tamper gate: text no seeder touched).

**One revision cycle is permitted per criterion; a criterion failing twice is not shipped and stays with the
frontier pair.** Additionally, `age_fit` adoption requires the band-swap probe: on at least 8 of 10 probe
texts, judging under a younger band than the text's own must lower `age_fit`. And a student that emits scores
for `voice` or `dialogue` at all fails the run (section 2's declared-observation rule).

*Cost.* Zero marginal spend once self-hosted; the point of the exercise. Wall clock: hours.

#### RD8. Quantisation and serving

*Build.* The deployment builds (fp16 reference, then the quantised candidates) on the homelab target, each
put through the full RD7 battery.

*Decision rule.* **Adopt a quantised build iff every RD7 per-criterion verdict is unchanged and the control
noise floor moves by at most 0.1.** A regression concentrated in one book is checked with the drop-worst
column (`UW-C246`) and per-book deltas before being attributed to quantisation; `AL-349` is the reason this
sentence exists.

*Cost.* Zero spend, GPU hours.

### Phase 4: adoption

#### RD9. Shadow membership, then the swap

*Build.* The student joins evaluation runs as a shadow: scored beside the frontier pair, never averaged in
(`AL-381`: membership is an evidence decision, and a mean hides a member). One full evaluation cycle of
parallel scoring, written to `eval/`.

*Decision rule.* **Replace the frontier pair for within-book delta comparisons iff, over the shadow cycle,
per-criterion quadratic-weighted kappa between the student's deltas and the teacher pair's deltas is at least
0.60 on every adopted criterion** (the house floor, Landis and Koch 1977, with marginals printed beside every
figure per `UW-C256`). The frontier pair is retained for unadopted criteria, and the battery is re-run against
the student on every rubric change and quarterly regardless, which self-hosting makes free; an instrument that
is only ever validated once is on its way to being the panel this plan replaces.

*Cost.* One shadow cycle at frontier prices, roughly the cost of the evaluation it shadows (measured anchor:
$2.60 per 129 scorings).

## 7. Kill criteria: what would mean distillation is the wrong answer

Written before any of it runs, so a thin result cannot be renegotiated into a pivot:

1. **No trustworthy teacher.** RD5's ordering gate fails on every Tier 1 criterion. Then there is nothing to
   distil, from anyone, and the next dollar goes to W12's human read, which is the programme's referee for
   exactly this situation.
2. **Capacity is not the gap and training does not close it.** `glm-5` fails zero-shot (RD4) *and* the
   fine-tuned student fails RD7 on every criterion after its revision cycle. Stop; record that the task
   exceeds small open-weight models on this data; the fallback is the frontier teacher pair with repeat
   scorings, which is stable (drift 0.14), already validated, and costs about $2.60 per full battery pass.
   Cost was never the binding constraint, so this fallback is a good outcome, not a defeat.
3. **Data volume binds.** RD6's learning-curve rule fires and corpus growth is not scheduled. The plan parks,
   openly, rather than squeezing more epochs out of the same 500 pairs and calling the memorisation a student.
4. **The student learned the seeder.** RD7 gates 4 or 5 fail while gates 1 to 3 pass: strong on seeded arms,
   wrong on natural text. Retraining with a higher share of teacher-ranked and holdout-adjacent pairs is the
   one permitted response; a second conviction kills the criterion, and a conviction on all criteria kills
   the plan, because it means our labelled-data generator cannot teach the property, only its own signature.
5. **Determinism does not survive serving.** RD7 gate 3 cannot be met on any available stack. The strongest
   argument for the whole project (section 0, point 3) is gone; what remains (pinning, sovereignty, cost) is
   re-argued to the owner from scratch rather than inherited.
6. **The battery stops being trustworthy.** If a future finding invalidates W7's arms (the way `AL-382`
   invalidated the voice arm), every adoption resting on it is suspended until the battery is repaired and
   re-baselined, because the acceptance test is load-bearing for every rule above it.

## 8. Sequencing summary

```text
Phase 0 (free):     RD1 store+manifest -> RD2 census+splits -> RD3 ladder generator
Phase 1 (~$5):      RD4 zero-shot slate  == can terminate the plan (adopt) or arm the burden-of-proof guard
Phase 2 (~$40-120): RD5 teacher labels   == can demote criteria to Tier 3; buys the permanent teacher/ asset
Phase 3 (~$5-30):   RD6 train -> RD7 accept (W7, five gates) -> RD8 quantise
Phase 4 (~$3):      RD9 shadow cycle -> swap for delta use, frontier retained elsewhere
```

The outcome we should be least surprised by, and pre-commit to accepting: **RD4 or RD5 ends the plan early.**
Either a zero-shot open-weight judge is already adequate for the three strong criteria, in which case training
was never needed, or the teacher cannot order its own severity ladders, in which case there was nothing to
distil and the honest product of this plan is the frozen store, the ladders, and a documented negative. Both
are cheaper than discovering the same thing after Phase 3, and a plan that could not produce them would be a
build order wearing a plan's clothes.

## 9. Register and log linkage

On owner sign-off, this plan's items get `UW-C*` rows in the unscheduled work register; the rows cite this
document and the lessons that shaped it (`AL-367` to `AL-385`). Lessons produced by *running* any phase go to
the authoring lessons log per the standing requirement, with the store's `eval/` entries as their `Ref`s. The
`docs/planning/judge-panels/` slate and `out/w7/` artifacts are this plan's inputs and are already tracked;
nothing here is permitted to depend on an untracked path, which is the one-sentence version of `UW-C257` and
the reason section 3 comes before section 6.
