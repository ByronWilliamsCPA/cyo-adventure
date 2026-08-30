# B1 review: structural and logical audit of `cyo-generation-research-brief-2026-08-22.md`

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/home/user/cyo-adventure`, `/home/user/cyo-adventure/.worktrees/brief-evidence`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.

**Reviewer scope.** Overarching structure and internal logic, not component detail.

**Revision 2 (issued after a coordinator correction).** The first issue of this review contained a
finding, B1-7, asserting that the brief's load-bearing evidence did not exist. That was wrong. Only the
brief file had been copied onto the analysis branch; its evidence was never copied. The full source
branch is now available and **all of it exists**: the test plan, `evidence/skeleton-author-vendors/`
(291 files across five run directories), `evidence/recognition-protocol-pilot/` with `results.md` and
six rater verdicts, and the `S-`, `AL-510..513` and `UW-C317..320` rows. **B1-7 as originally written is
retracted in full.** It is reissued below as a different finding, on different grounds, at a lower
severity, because reading the real evidence turned up a genuine and more interesting problem.

### Trees used, and what was verified where

| Tree | Ref | Role |
| --- | --- | --- |
| **A: analysis branch** | `/home/user/cyo-adventure`, `6f0d8ce` (`claude/cyo-brief-analysis-jys942`) | brief text only |
| **B: source branch** | `/home/user/cyo-adventure/.worktrees/brief-evidence`, `6fc2b34` (`claude/model-selection-skeleton-dev-78yp7u`) | brief **plus** all cited evidence, register, log, harness |

The brief file is **byte-identical in both trees** (`diff -q` clean), so every textual finding is
unaffected by which tree it was read in. `git diff --name-status HEAD 6fc2b34 -- src/ scripts/ skeletons/`
returns exactly two additions, `scripts/compare_skeleton_authors.py` and `scripts/modal_kimi_leg.py`;
**`src/` and `skeletons/` are identical between the trees**, so every code-based and catalog-based
finding was re-run against tree B and holds unchanged. Each finding below states its verification tree.

Documents read: the 2026-08-10 brief (2,922 lines), `skeleton-sourcing-test-plan-2026-08-21.md` (562
lines), `diversity-test-register.md` (with section F, the S rows), `architecture-respecification-2026-08-10.md`,
`authoring-lessons-log.md` (through `AL-514`), `deepseek-v4-pro-live-fill-plan-2026-08-20.md`,
`vendor-comparison/README.md`, the S-1 run records and `tools-meta.json`, and the running code.

Programme goal held throughout: *a high-quality framework producing cost-effective CYO books for children.*

---

## Where the brief is strong (stated before the criticism, and meant)

1. **The evidence-class banner is real discipline.** Declaring deterministic / model-judged / human-gated
   up front, and mostly naming the class per claim, is better practice than most engineering briefs manage.
2. **Section 1 finding 2 ("a passing gate is not quality") is the best idea in the document.** It is earned
   by a specific, dated, deterministic result (`AL-490`: 38.9-52.9% of commissioned words through a passing
   gate) and correctly generalises into a design rule (F2's floor/delivery pairing).
3. **F6 is an unusually honest principle**, and section 4.4's "does not work" list is the most credible
   passage in the document.
4. **Section 4.5 is genuinely useful cost forensics**: three named waste modes, each with a countermeasure.
5. **Section 3 is concrete and mostly accurate**: it names real files that exist and do what it says.
6. **The S-1 table is faithful to its data.** I recomputed every cell from
   `runs/e1r3-tools-2026-08-21/tools-meta.json` (42 grid points): fable 3/3 and 3/3, opus 3/3 and 3/3,
   sonnet 1/3 and 3/3, haiku 2/3 and 1/3, kimi 2/3 and 3/3, flash 1/3 and 2/3, pro 0/3 and 0/3, summing to
   12 and 15. Every number in the brief's table reproduces. The passes are **harness-verified, not
   self-reported**: each record carries an independent `strict_pass` and `graph_check_exit` from the
   harness's own check of the delivered shell.
7. **The upstream records are markedly more careful than the brief.** The register's `S-1` status column,
   the evidence README, and `AL-510..AL-514` disclose the credit halt, the slate revision, the data contact
   at revision time, the "tier-labeled, not backend-pinned" limit, and the censoring. This matters for the
   findings below: most of what I fault the brief for **is already written down one layer beneath it**. The
   defect is distillation, not concealment.

---

## Answer to question 3, up front: the F1..F8 to pipeline traceability matrix

Every row re-verified against **tree B** (`src/` and `skeletons/` are identical in both trees).

| Principle | Pipeline stage(s) claimed | Mechanism actually present | Verdict |
| --- | --- | --- | --- |
| **F1** split structure / prose | 3.1, 3.2, 3.3, 3.4 | skeletons with `<<FILL>>`, `check_skeleton.py --strict`, `fill_skeleton`, separate story gate | **Implemented.** The one principle fully realised. |
| **F2** gates first, floors not scores | 3.2, 3.4 | gates yes (`validator.gate.run_gate` in `generation/worker.py`). Delivery pairing **no**: `check_fill_integrity.py` is imported by nothing under `src/` (3 comment mentions, 0 imports) and by no workflow; `check_sibling_fills.py` unwired and admitted (`UW-C315`). The **skeleton** gate has no delivery pairing at all. | **Half-implemented; overstated in 3.4.** |
| **F3** checker in the author's loop | 3.1 authoring, 3.2 | True for skeleton authoring. **False for the fill stage**: repair is orchestrator-driven and the story gate runs after, not inside, the author's loop. | **Applied to one of two authoring problems.** |
| **F4** model per stage | 3.3 fill, 3.5 review | Config supports it (`openrouter_model`, `review_openrouter_model`). Shipped values: fill `anthropic/claude-haiku-4.5`, review `anthropic/claude-sonnet-4.6`, `review_provider="mock"`, plus a `FallbackProvider` cascade that silently substitutes. | **Mechanism yes; running system inverts 4.2's recipe.** |
| **F5** reuse structure, generate decisions per book | 3.3 binding | **No mechanism.** `grep -rn choice_semantics src/` = 0; `grep -rni "decisional\|structural stratum" src/` = 0. Production differentiation is `build_differentiation_directive`, a prompt block. | **Not implemented. See B1-1.** |
| **F6** validate instruments, pre-register | (none) | A research-process rule, not a pipeline stage. And 3.5 puts an unvalidated model reviewer in the publish path. | **Unimplemented by construction, contradicted at 3.5.** |
| **F7** engineer the cost | 3.3 | Metering (`generation/usage.py`), sized caps, chunking present. Spend guards, `--resume`, preflight, credits checks are **harness** tooling, not the request path. No per-book cost ceiling in `core/config.py`. | **Partially implemented; guards are offline.** |
| **F8** a human approves | 3.5 | `publishing/` state machine. Real. | **Implemented.** Its review-load criterion is `S-5`, blocked. |

**Mechanisms with no principle** (the reverse direction, which the brief never checks): the `TAU_CELL`
anti-clone distance gate and recency-weighted selection (both enforce *structural* distinctness, which F5
and 4.3 say is not the defect); catalog-time mutation, retained though 4.3 calls shape-preserving operators
perceptual no-ops; the "reader-experience floors" in 3.2, which are the only reader-side commitments in the
whole system; and `check_prose_craft.py`.

---

## B1-1: F5 has no implementing mechanism, and the pipeline's only differentiation lever is one section 4.3 refutes
- **Severity**: critical
- **Category**: traceability
- **Verified against**: tree B (and tree A; `src/` identical in both)
- **Locus**: F5, line 74: "**Reuse structure freely; never reuse decisions; generate the decisional layer
  per book.**" Against 3.3: "Theme contracts bind per-request settings, casts, and props
  (`scripts/bind_theme.py`); the differentiation directive (`build_differentiation_directive`) instructs
  the fill away from sibling books." Against 4.3's refuted list: "instructing independence between authors
  (does nothing; withholding shared material works completely, M-4 series)."
- **Problem**: Three defects stacked.
  (a) **No stage generates a decisional layer.** `grep -rn "choice_semantics" src/cyo_adventure/` returns
  zero on both trees; the term lives only in `scripts/check_*.py` and `evidence/*/build.py`. The per-book
  generation of `choice_semantics`, beats, devices and stakes that F5 and the architecture re-specification
  both require is not in the request path, not in section 3, and not listed in section 5 as missing.
  Section 2 says "Each is load-bearing in the pipeline of section 3"; for F5 that is false.
  (b) **What the pipeline does instead is theme binding**, which is S3, which 4.3 lists as refuted.
  (c) **The residual differentiation mechanism is a prompt instruction**, the one intervention the programme
  has refuted twice and hardest (126.7 against 1.0 shared four-grams per 1000, re-specification section 2.2;
  4.3's own M-4 line). 4.1 concedes the raw undirected floor is 96.3 per 1000 against a 4.0 budget, "24x
  budget", and that "measuring what the directive actually buys is open." A prompt block would have to carry
  24x. The brief files this as an open measurement rather than as a contradiction between its framework and
  its shipping system.
- **Why it matters for the goal**: F5 is the framework's answer to the defect the programme exists to attack.
  If it is unimplemented and the deployed substitute is a refuted lever, every book shipped today is produced
  by an architecture the brief's own evidence section rejects. A reader of section 2 reasonably concludes the
  diversity problem is solved in production. It is not addressed in production.
- **Recommendation**: Add a sixth stage to section 3, "decisional stratum generation", marked **not built**,
  with inputs (structural stratum), outputs (`choice_semantics`, `beat_hint`, bound devices, operation,
  stake) and the gate it must pass (shared-gram check across the family's set). Restate F5 as: "Reuse the
  wordless structural stratum; generate the decisional stratum per book. **The pipeline does not do this yet
  (`S-2`, blocked); theme binding plus a differentiation directive is the interim and its effect is
  unmeasured (`AL-498`).**"
- **How to check I'm right**: `grep -rn "choice_semantics\|decisional" src/cyo_adventure/` in either tree
  (empty); `sed -n '480,520p' src/cyo_adventure/generation/prompts.py`; compare
  `architecture-respecification-2026-08-10.md` section 2's stratum table against section 3 of the brief.

---

## B1-2: 4.2's "Consequence for the product" does not follow from 4.2, and its central term is contradicted by the programme's own quality ranking and by its own test plan
- **Severity**: critical
- **Category**: framework logic / evidential overreach
- **Verified against**: tree B (the source branch adds no new prose-quality evidence for V4 Pro;
  `grep -rn "best judged\|best prose"` on tree B hits only the brief itself)
- **Locus**: 4.2, lines 215-217: "Consequence for the product: fill with V4 Pro, author structure with a
  tool-assisted Anthropic tier, review first-pass with V4 Flash." And F4, line 69: "The best prose model
  measured (DeepSeek V4 Pro)".
- **Problem**: Section 4.2 measured **structure authoring only**. Two of its three product consequences are
  imported from elsewhere and neither survives inspection.
  (a) **"Fill with V4 Pro."** The programme's most complete three-axis comparison (2026-08-10 brief section
  31) ranks `deepseek-v4-pro` **fifth of eight** on judged quality at **-0.13 peers-only**, against
  `anthropic-sonnet-5` +0.69 and `xai-grok-4.6` +0.61, and describes V4 Pro as "4.9x cheaper and gives up
  0.14 of in-band rate and 0.74 of judged quality to get there." That is a cost argument. The new brief
  converts it into "the best judged prose" and builds F4 on it.
  (b) **The programme's own test plan does not make this claim either.** The plan's threats-to-validity
  section states the fill-model policy conditionally: "**if v4 Pro is retained for prose quality despite its
  measured 38.9-52.9% delivery**, the repair-loop policy per fill is pre-registered and fill-rate is carried
  as a covariate on every judged endpoint." That is "retained, adequate, and instrumented", not "best".
  (c) **The live run points the other way and the brief does not say so.** The 2026-08-20 V4 Pro live fill
  recorded, on its three delivered books, in-band rates of **15.5%, 5.6% and 73.1%**; 23 redundant nodes
  across 11 repeated texts with two byte-identical nodes; **674 choices sharing 24 distinct labels, top
  three covering 89.8%**; bodies restating their own `beats=` with nouns swapped at 0.51 mean overlap; and
  incoherent world physics. The brief compresses that run to "surfaced the fill-rate hole".
  (d) **"Review first-pass with V4 Flash"** is sourced in 3.5 to "owner practice, 2026-08" with no artifact
  and no known-answer test, and it sits in the publish path, which F6 forbids.
- **Why it matters for the goal**: the framework's most operational output is a three-model production
  recipe. Two thirds of it is unsupported, and the supported third is the part 4.2 actually measured.
- **Recommendation**: Split the sentence. Keep "author structure with a tool-assisted Anthropic tier
  (evidence: 4.2)". Demote the other two into "model selections we have not earned yet", stating for the
  fill: judged quality rank 5 of 8, cheapest delivering leg, the live-run prose defects, and the plan's own
  conditional retention language. Rewrite F4's opening around the direction the evidence supports: *the
  cheapest adequate prose leg is the worst structure author measured*.
- **How to check I'm right**: `cyo-generation-research-brief-2026-08-10.md` lines 2759-2790;
  `deepseek-v4-pro-live-fill-plan-2026-08-20.md` section 5.2 and its "Prose defects the gate cannot see";
  `skeleton-sourcing-test-plan-2026-08-21.md` section 7, "Fill-model policy (P6, P8)".

---

## B1-3: F3 calls a floor a quality lever, and the regime effect is measured in one cell against a condition the programme's own lesson log says is not production practice
- **Severity**: critical
- **Category**: framework logic / internal tension
- **Verified against**: tree B (`runs/e1r3-2026-08-21/run.json`, `runs/e1r3-tools-2026-08-21/tools-meta.json`,
  `AL-513`)
- **Locus**: F3, lines 64-67: "The single largest **quality lever** we have measured is not model choice but
  authoring regime: blind generate-and-repair produced 2 strict passes in 21 attempts across seven models;
  the same models with permission to run the validator themselves passed 12 of 21 at ages 5-8 and 15 of 21
  at ages 10-13." Against line 46: "Gates are floors; quality lives above them and must be measured
  separately."
- **Problem**: Reading the real run data resolves one of my first-issue objections and replaces it with two
  worse ones.
  (a) **Category error, unchanged and central.** The endpoint is `check_skeleton.py --strict` pass/fail. That
  is a *floor*. F3 calls the lever a **quality** lever. By the brief's own finding 2, floor-clearance says
  nothing about quality; this is the `AL-490` conflation committed one stage upstream. The honest word is
  *yield*.
  (b) **The blind arm is not a regime anyone uses, and the programme knows it.** `AL-513` states it plainly:
  "The production authoring mechanism (cyo-author skill sessions) authors WITH checker access and unlimited
  self-validation, so **this harness regime systematically understates current practice**." The blind arm
  exists because the harness enforces a provider-parity contract that forbids tools. So 2/21 to 12/21 is not
  a lever the programme can pull to improve on where it already is; it is the measured cost of a constraint
  the *experiment* imposed. F3 presents it as the largest discovered improvement available. It is a
  retrospective justification of existing practice, which is a legitimate and useful result, but a different
  one. Note also that the tool-assisted arm caps the author at 10 checker invocations while production is
  "unlimited", so even the treatment arm is a bounded proxy for the thing it vindicates.
  (c) **The regime comparison exists in one cell only.** `runs/e1r3-2026-08-21/run.json` records
  `"cells": ["A"]`, 3 replicates, 7 legs = 21 shells. There is **no blind arm at cell D**. So "2 of 21"
  (blind, cell A) versus "12 of 21" (tools, cell A) is a real comparison, and "15 of 21 at ages 10-13" has
  **no blind counterpart at all**. The sentence's construction ("the same models ... passed 12 of 21 at ages
  5-8 and 15 of 21 at ages 10-13") reads as a two-cell regime effect. It is a one-cell regime effect plus a
  one-cell tools-only yield. *(My first issue speculated the blind denominator might be mismatched at 42.
  It is not. That speculation is withdrawn; the accurate defect is the missing blind cell D.)*
  (d) **Everything is n=3 per cell.** Sonnet 1/3 against Haiku 2/3 in cell A is noise, yet 4.2 draws
  "frontier Anthropic tiers converge fastest and most reliably" and F7 draws a Haiku cost recommendation
  from it. The 0/6 for V4 Pro is the one leg-level claim with enough failures behind it to survive.
- **Why it matters for the goal**: F3 is the principle the brief leans on hardest and the one that justifies
  the current authoring regime and its cost profile. Restated accurately it says "our existing practice is
  the reason our shells pass; a tool-free harness would not work", which is worth knowing and does not
  license "largest quality lever". And describing floor-clearance as quality reintroduces the exact failure
  mode the document opens by naming.
- **Recommendation**: (1) Restate F3 as a **yield/convergence** lever. (2) Add one clause: "the blind arm is
  a harness condition, not production practice (`AL-513`); this measures what the checker-in-loop regime is
  worth, not an improvement over what we do." (3) State that the regime contrast is cell A only and that
  cell D has no blind arm. (4) Give every cell its n. (5) Say what 4.2 does **not** show: nothing here says a
  tool-assisted shell is a *better* shell, only a passing one, and the 10-invocation cap means the tools arm
  understates production too.
- **How to check I'm right**: `python3 -c "import json;print(json.load(open('docs/planning/evidence/skeleton-author-vendors/runs/e1r3-2026-08-21/run.json'))['cells'])"`
  on tree B returns `['A']`; read `AL-513`'s lesson and proposed-change columns in full.

---

## B1-4: 4.3's "refuted" and "confirmed" labels rest on an instrument that failed its validation, and the plan itself now gates that instrument out
- **Severity**: high
- **Category**: evidential overreach / internal tension
- **Verified against**: tree B (`S-0` register row, `evidence/recognition-protocol-pilot/results.md`,
  `AL-511`, plan sections 5 E0 and 7)
- **Locus**: 4.3, line 222: "**Refuted as variety levers**: theme binding and device pools (solved their own
  metrics, **recognition unmoved**, S3/S5/S6); model tier (**recognition identical** at both craft extremes,
  S7) ... multiple obligation contracts over one graph (**recognition landed earlier**, S9)". Against F6,
  line 80: "**Trust no instrument until it survives a known-answer test.**"
- **Problem**: Every refutation in that bullet is measured by recognition. The register's `S-0` row now reads
  "**done, FAILED validation** ... the control fired too (yes at positions 12 and 41, both raters), so the
  instrument is not validated and the blocked-branch consequences apply." The manual predecessor is no better
  off: the 2026-08-10 brief's section 1.4 says the manual protocol "measures detectability of the shared
  armature", which "by 1.3 is not the defect", and that "every number in section 5 is subject to that
  confound"; section 6.4 says "we do not currently have a valid measurement of the thing we care about."
  The test plan then makes this operative: "the recognition protocol is used **only after E0 validates it**",
  and E0 is `S-0`, which failed. So the brief reports as settled refutations the verdicts of an instrument
  its own live plan has gated out of future use.
  The same problem runs the other way in 4.4's "works" list: **provenance-stripped blind judging** is listed
  as working, but no known-answer test for it is named, and the predecessor's section 29 showed the judge
  panel's dialogue criterion returning 3.00 for seven of eight legs while the deterministic measure of the
  same property spread twenty-five-fold. That panel is the instrument behind F4's "best prose model" (B1-2).
- **Why it matters for the goal**: five architectural options are closed off by these refutations. If the
  instrument that closed them is invalid, some are still live and the search space is narrower than the
  evidence licenses. A framework that both preaches instrument validation and quotes an unvalidated
  instrument's verdicts as settled will not be believed on either.
- **Recommendation**: Relabel 4.3's first bullet "**Refuted against the recognition instrument, whose
  validation failed on 2026-08-21 (`S-0`)**", with a clause per row naming what a repaired instrument could
  change. In 4.4's "works" list, state for each entry the known-answer test it survived; blind judging has
  none and belongs in a third class, "used, unvalidated", alongside the V4 Flash reviewer.
- **How to check I'm right**: the `S-0` status column in `diversity-test-register.md` section F; plan section
  7, "Instrument limits"; `evidence/recognition-protocol-pilot/results.md`; `AL-511`.

---

## B1-5: the framework has no reader in it, and the brief drops the predecessor's provenance banner while adding an evidence class that reads as human evidence
- **Severity**: high
- **Category**: completeness gap / communication
- **Verified against**: tree A (brief text) and tree B (plan section 1)
- **Locus**: the evidence-class blockquote, lines 12-14: "**deterministic** ... **model-judged** ...
  **human-gated** (a person approved it)". And F8, line 95.
- **Problem**: The predecessor carries a boxed banner: "**No human and no child has read or rated any
  generated book.** These results are model-based hypotheses about reader response, not reader evidence,"
  with a table row "Human or child reader evidence | **none** | must not be claimed or assumed." The new
  brief drops it, and names its third class **human-gated**. A person approving a book for publication is a
  *control*, not an *instrument*: it produces no score, no comparison, nothing aggregable. Calling it one of
  three evidence classes, in a document that never says no child has read anything, invites exactly the
  misreading the banner was added to prevent.
  Structurally this is why **no principle in F1..F8 concerns the reader**. All eight are producer-side. And
  this is a loss in distillation rather than a programme blind spot: the test plan's section 1 scores every
  arm on five axes, of which **premise fit** ("Does the book reflect what the requesting family actually
  asked for") is one. The framework carries neither the axis nor the reader.
- **Why it matters for the goal**: the goal word is *quality*, and quality in a children's book is a reader
  property. Eight principles that never mention a child are principles for producing artifacts that pass our
  own tests. The predecessor calls this "the load-bearing gap rather than a caveat".
- **Recommendation**: (1) Reinstate the provenance banner verbatim near the top. (2) Rename the third class
  "human-approved (a publication control, not an instrument)", or drop it and state two classes plus "reader
  evidence: none". (3) Add a principle: *no quality claim reaches a product decision without a reader signal;
  the product's own rating, completion and re-read telemetry (`api/ratings.py`, `api/reading_history.py`,
  `api/progress.py`, `api/reading_time.py`) is the cheapest available source and is currently unused as
  evidence.* Guardians are humans the programme does have access to even if children are not recruitable.
- **How to check I'm right**: `sed -n '29,52p' docs/planning/cyo-generation-research-brief-2026-08-10.md`;
  then search the new brief for "child" and observe it never appears as a source of evidence; then read the
  five-axis table in `skeleton-sourcing-test-plan-2026-08-21.md` section 1 and note which axes reached F1..F8.

---

## B1-6: F5 is stated far more strongly than a single pair of books licenses, and drops the predecessor's "necessary and not sufficient"
- **Severity**: high
- **Category**: evidential overreach
- **Verified against**: tree B (`evidence/d7b-bare-names/`, unchanged from tree A; register `S-2`)
- **Locus**: F5, lines 74-77: "**Reuse structure freely** ... without measurable prose convergence (2.3
  shared 4-grams per 1000 ...)".
- **Problem**: The 2.3 figure is **one pair of books**, **seven shared four-grams** over a 3,001.5-word mean.
  One gram either way moves it 0.33. It cannot survive its supporting result being wrong, because it is the
  supporting result. Four upstream qualifications are absent here:
  (a) "the kernel we published as containing no free text still carries **473 words** of it ... more than the
  422 the experiment deleted", so the passing arm does not satisfy the rule it is cited for;
  (b) the retraction: the "62 percent gloss-derived" mechanism "does not reproduce" (five of forty), and the
  replacement mechanism is **convergent elaboration**, meaning "anything that primes two authors identically
  will do this, and an enumerated category primes without being prose at all";
  (c) the re-specification's verdict: "stratification is a necessary first move whose sufficiency is now
  measured and **inadequate**", with the premise channel explicitly unclosed;
  (d) a named unguarded channel: both books drew the cipher form from one five-element category list, so
  "two books collide by chance about one time in five, and the four-gram measure cannot see it by
  construction".
  Section 19 of the predecessor also reports the same pair at **solution transfer 0.467**: "the headline was
  never a distinctness result. It is a convergence result." F5 quotes the convergence number and asserts the
  distinctness conclusion. The register confirms the status: `S-2`, the end-to-end test of exactly this, is
  **blocked**.
- **Why it matters for the goal**: F5 is the cost engine of the framework and authorises sharing armatures
  across every family. The defensible statement is "sharing the wordless stratum is necessary but
  insufficient, with two known open leak channels and one measured pair", which implies a per-family
  shared-gram guard that section 3 does not run.
- **Recommendation**: Restate F5 in three clauses that survive the evidence: *never share sentences; share
  the wordless stratum only under a per-family shared-gram guard; the premise and enumerated-category
  channels are open and unguarded.* Report the 2.3 with its n (one pair, seven grams) inline. Move "reuse
  structure freely" out of the imperative into "reuse is not the defect", which is what 1.3 establishes.
- **How to check I'm right**: `cyo-generation-research-brief-2026-08-10.md` lines 1826-1889, 2219-2260,
  2185-2200; `architecture-respecification-2026-08-10.md` lines 100-110 and 148-158; the `S-2` register row.

---

## B1-7 (REISSUED): the brief's newest evidence is exploratory data from a redesigned arm, promoted to decision authority, in a document whose sixth principle is pre-registration
- **RETRACTION**: the original B1-7 claimed the S-1 evidence, the test plan, the register rows, the lessons
  and the work rows did not exist. **That was an artifact of the analysis branch carrying the brief without
  its evidence. All of it exists on tree B and is retracted in full.** The finding below is a different one,
  found by reading that evidence.
- **Severity**: high
- **Category**: status honesty / evidential overreach
- **Verified against**: tree B (`skeleton-sourcing-test-plan-2026-08-21.md` sections 5 E1 and 7;
  `diversity-test-register.md` `S-1`; `evidence/skeleton-author-vendors/README.md`;
  `runs/e1-2026-08-21/`, `runs/e1r3-2026-08-21/summary.md`, `runs/e1r3-tools-2026-08-21/summary.md`)
- **Locus**: F6, line 80: "Trust no instrument until it survives a known-answer test, and **pre-register
  everything**." Against 4.2's "Consequence for the product" and F3/F4, which are built on the S-1 pass
  counts.
- **Problem**: The S-1 evidence is real, well kept and honestly caveated **in the register**. What the brief
  does with it is the problem, and there are five parts.
  (a) **The pre-registered primary endpoint returned nothing, in both arms.** The plan and the register fix
  "**one pre-registered primary endpoint: repair rounds to strict pass** ... permutation test ... alpha 0.05."
  Blind (`e1r3`) reports "between-leg statistic 2.571, **p = 1.0000**"; tool-assisted (`e1r3-tools`) reports
  "statistic **0.000**, p = 1.0000" because the checker runs happen inside the leg and the harness records
  `repair_rounds: 0` and `mean repair rounds 0.00` for every leg. So the endpoint is degenerate under
  censoring in one arm and structurally unmeasurable in the other. The brief says this for the blind arm and
  not for the tools arm.
  (b) **The endpoints the brief reports are pre-registered as decision-inert.** The plan's E1: "Everything
  else (one-pass yield, walk probability, failure classes ...) is **exploratory**: reported, never triggering
  a decision, because 10 pairwise leg comparisons x 5 endpoints x 4 cells guarantees spurious separation
  somewhere." Plan section 7 repeats it as a committed control: "**Multiplicity discipline**: one
  pre-registered primary endpoint per experiment; everything else is exploratory and **cannot trigger a
  decision rule**." The brief's pass counts are that exploratory yield endpoint, and 4.2 uses them to trigger
  a three-model production decision. The register does the same thing one layer down ("the decision-bearing
  results are the tool-assisted pass counts"), which contradicts its own falsifier column ("All other
  endpoints exploratory, decision-inert") in the same row.
  (c) **The registered experiment never ran.** `runs/e1-2026-08-21/` is the registered 5-leg x 4-cell x 4-
  replicate 80-shell grid; its README says it was "**HALTED on provider credits after 4 of 80 shells**" with
  "No result may be read from this directory's `summary.md`." The reported results come from a post-halt
  redesign: slate 5 legs to 7 (dropping the three paid Western legs, adding four zero-cost Anthropic subagent
  tiers and a Modal Kimi leg), cells 4 to 2, replicates 4 to 3, plus an entirely new tool-assisted condition.
  To the programme's credit the register declares this with data contact stated ("4 completed shells'
  exploratory records were seen, no primary result existed"). **The brief mentions none of it.**
  (d) **A pre-committed validity control is unaddressed.** The plan requires "a **shared repair-loop
  contract** ... applied identically to every leg, **because a per-leg repair harness would be the
  treatment**." In the final slate four legs run as in-harness subagents and three over remote APIs. The
  brief's table does disclose the transports, which is good, and the outcome is not a clean subagent sweep
  (Kimi over Modal beats two Anthropic tiers). But the brief never raises the confound the plan pre-committed
  to avoid, and the register's own limit ("**tier-labeled, not backend-pinned: tier-level conclusions only**")
  does not travel into the brief either.
  (e) **The whole basis is unmerged.** The brief, its evidence, the `S` rows, `AL-510..513`, `UW-C317..320`
  and the S-1 harness are all absent from `origin/main`. That is normal for in-flight work, but the brief
  presents itself as "the current account of the programme" and section 3 as "the system as it actually runs
  today", so a reader on main can reproduce none of it.
- **Why it matters for the goal**: F6 is the principle that makes the rest of the document trustworthy, and
  section 4.2 is the only new evidence in the brief. Promoting decision-inert endpoints from a redesigned arm,
  without disclosing the halt, the redesign or the multiplicity commitment, is the specific failure F6 exists
  to prevent, committed in the same document. It also matters practically: the pre-registered decision rule
  for a null primary endpoint was "the model axis is dropped and downstream arms use the cheapest strict-passing
  leg", which is close to the *opposite* of F4.
- **Recommendation**: In 4.2, add three sentences before the table: the registered run halted at 4 of 80
  shells on credits; the slate, cells and replicates were revised post-halt with data contact declared; and
  the primary endpoint returned p=1.0 in both arms, so **every number below is exploratory and pre-registered
  as decision-inert**. Then either (i) state explicitly that the product consequence is an owner judgement
  taken against the multiplicity rule and say why, or (ii) re-register the pass-count endpoint as primary for
  a confirmatory run and hold the decision until it reports. Carry the register's "tier-labeled, not
  backend-pinned" limit into F4. Resolve the register's internal contradiction between its falsifier column
  and its final reading. Update the evidence README, which documents `smoke`, `smoke2` and `e1` but not
  `e1r3` or `e1r3-tools`, the two runs everything is drawn from.
- **How to check I'm right**: `cat docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/summary.md`
  (statistic 0.000, p=1.0000, mean repair rounds 0.00 for all seven legs); plan section 5 E1's "exploratory"
  paragraph and section 7's "Multiplicity discipline" bullet; the `S-1` status column's "HALTED on provider
  credits" and "Revised pre-result" passages; `ls docs/planning/evidence/skeleton-author-vendors/runs/`
  against the README's three documented runs.

---

## B1-8: F2's delivery pairing is not in the production path, and 3.4 states it as if it were
- **Severity**: high
- **Category**: traceability / status honesty
- **Verified against**: tree B (re-run; identical to tree A, `src/` unchanged between trees)
- **Locus**: F2, line 60: "**every gate is paired with a delivery measurement** (fill rate, word delivery)".
  3.4: "`check_fill_integrity.py` **enforces** a minimum fill rate (0.6 ...)".
- **Problem**: `check_fill_integrity.py` is a standalone script. On tree B, `grep -rn check_fill_integrity src/`
  returns three **comment** references and zero imports; `grep -rn "fill_integrity\|sibling_fills" .github/workflows/`
  returns zero. `generation/worker.py` runs `validator.gate.run_gate` plus the Stage-1 fidelity gate and
  nothing else. So a book generated through the production path today can still deliver 39% of its
  commissioned words and pass, which is the `AL-490` defect F2 exists to close. The sibling-fill check is
  honestly flagged unwired (`UW-C315`); the fill-rate check is not flagged and is given the verb "enforces".
  Separately, F2 says *every* gate is paired, but the skeleton gate has **no** delivery pairing: nothing
  measures whether a passing shell is fillable or well-commissioned, which is the hollow-pass risk one stage
  up, and the risk F3's tool-assisted regime structurally increases.
- **Why it matters for the goal**: F2 is presented as the fix for the document's headline defect. If the fix
  is an offline script, the defect is open in production while the framework reports it closed.
- **Recommendation**: Change 3.4's verb to "measures, offline", and add `check_fill_integrity` to section 5's
  open list beside `UW-C315`, or wire it into `generation/worker.py` alongside the Stage-1 gate. Amend F2 to
  "every gate **must be** paired with a delivery measurement; today one stage has one specified and neither
  of the two is wired." Add the missing skeleton-stage delivery question explicitly.
- **How to check I'm right**: on tree B, `grep -rn "check_fill_integrity" src/` (3 comments, 0 imports);
  `grep -rn "fill_integrity\|sibling_fills" .github/workflows/` (empty);
  `grep -n "run_gate\|stage1" src/cyo_adventure/generation/worker.py`.

---

## B1-9: no principle covers catalog coverage, exhaustion or cold start, and the predecessor's single most consequential constraint is absent from the framework
- **Severity**: high
- **Category**: completeness gap
- **Verified against**: tree B (catalog identical between trees; plan section 1 scope paragraph)
- **Locus**: 4.3's capital facts, line 233 (Q-1, exhaustion by the fourth request). No corresponding
  principle in F1..F8.
- **Problem**: The predecessor's section 22 computed the binding constraint and stated it in the strongest
  terms it uses anywhere: "**A child reading this world gets a repeated puzzle device by their sixth book**,
  whatever architecture produced it. In the youngest band ... the forced repeat arrives at **book two**", and
  "the fix is not architectural: somebody has to write more kinds." Section 25 lists it as the one
  requirement "that no architecture solves". None of F1..F8 mentions device-category vocabulary, catalog
  growth against demand, or cold start. F5 licenses structural reuse for cost while the quantity that
  actually bounds reuse, vocabulary depth, goes unnamed. Two supporting facts are also missing: **2 of 84
  skeletons carry a narrative contract** (counted on both trees), which is the precondition for F5's
  stratified plan being implementable at catalog scale; and the plan's own scope paragraph, which excludes
  **series books** from the sourcing verdict because "structural continuity across books is a designed
  constraint that bespoke-per-request breaks by construction", along with gamebook cells and the 3-5 band.
  None of those three exclusions appears in the brief, so the framework reads as covering the whole catalog
  when its live decision covers prose cells in 5-8 through 16+ only.
- **Why it matters for the goal**: cost-effectiveness at catalog scale is half the goal. Optimising per-book
  cost while ignoring how fast one child exhausts the catalog optimises the wrong denominator. If a child
  hits a repeated device at book six regardless of architecture, F5's reuse economics are bounded by a
  quantity the framework never names.
- **Recommendation**: Add a principle: *the binding constraint on series novelty is the size of the
  enumerated device and premise vocabularies, not the depth of the skeleton catalog; catalog growth is
  measured in vocabulary kinds per band and must exceed a reader's consumption rate.* Give it its two numbers
  (repeat at book 6; book 2 at ages 3-5) and a target. State contract coverage (2 of 84) in 4.3 beside Q-1,
  and carry the plan's scope-of-verdict exclusions into section 2 so the framework's reach is explicit.
- **How to check I'm right**: `sed -n '2261,2290p'` and lines 2386-2400 of the 2026-08-10 brief;
  `skeleton-sourcing-test-plan-2026-08-21.md` section 1, "Scope of the verdict";
  `find skeletons -name '*.narrative.json' | wc -l` (2) against 84 skeletons, identical on both trees.

---

## B1-10: F7's cost evidence comes from a run that produced 4 of 80 shells, and five of seven legs have no cost instrumentation at all
- **Severity**: high
- **Category**: evidential overreach / completeness gap
- **Verified against**: tree B (`runs/e1-2026-08-21/` README and register `S-1`; all record files in
  `e1r3-2026-08-21` and `e1r3-tools-2026-08-21`)
- **Locus**: F7, lines 88-90: "model tier where the regime carries quality (Haiku authored passing hard-band
  shells at zero marginal cost; premium Western legs were 90% of one comparison's bill **for no additional
  passes**)"; and 4.5's "aborted premium-slate comparison".
- **Problem**: The real evidence makes this worse than it looked, on four counts.
  (a) **The comparison whose bill is quoted produced four shells.** `runs/e1-2026-08-21/` is the premium
  slate; its README records 76 of 80 shells lost to HTTP 402 and states "No result may be read from this
  directory's `summary.md`." The premium legs bought no passes because the run died, and most of the spend
  went on two smoke runs that are themselves "excluded from S-1 analysis". Reading "90% of spend for no
  additional passes" as a tier-selection signal is reading a crash as a result.
  (b) **The cost of the arm the conclusions come from was never recorded.** I checked all 42 tool-assisted
  records: **0 of 42 carry `output_tokens`, and 0 of 42 carry a non-zero `latency_s`**. In the blind arm only
  the two OpenRouter legs are instrumented; the four Anthropic subagent legs and the Modal Kimi leg record
  `null` tokens and `0.0` latency in both arms. So the regime whose economics F7 asserts has no token,
  cost or wall-clock accounting for five of its seven legs, and none at all in the treatment arm.
  (c) **"Haiku authored passing hard-band shells" is 1 of 3 at ages 10-13** and 2 of 3 at 5-8: the weakest
  Anthropic leg in the grid. At a 33% pass rate you buy three attempts per shell, which is a cost argument in
  the opposite direction, and the brief does not do that arithmetic. "**Zero marginal cost**" is a
  subscription-accounting artifact of running those legs as subagents, true of the harness and false of any
  production deployment; per (b) it is literally the absence of a measurement, not a measurement of zero.
  (d) **The cost model omits its two largest terms.** F8 mandates human approval of every book and the
  predecessor lists "what review costs" as unanswered; the plan schedules it as E5/`S-5`, which is blocked.
  Failed generations are unpriced too: the live run delivered 3 of 5. Section 1 asserts "unit economics cap
  what any one book may cost to produce" and never gives the cap. The one hard production datapoint is
  $1.064 for a single 16+ book, comparable to the premium legs F7 argues against.
- **Why it matters for the goal**: cost-effectiveness is half the goal, and this is the principle that
  governs it. A cost principle resting on a crashed run's spend, an uninstrumented arm and a billing artifact
  will produce the wrong sourcing decision.
- **Recommendation**: Rewrite F7's second lever as "model tier, **measured within the working regime only**",
  and either cite cost per *passing* shell (attempts x price) or drop the Haiku claim. Replace "zero marginal
  cost" with "not metered" and say so plainly. State that the tool-assisted arm records no tokens or latency
  and make that a build item, since the whole sourcing decision turns on economics. Adopt cost per
  **published** book as the unit of account with three named terms: generation (measured), failed attempts
  (measurable now), human review (blocked on `S-5`). Give the unit-economics cap a number or delete the claim.
- **How to check I'm right**: `head -40 docs/planning/evidence/skeleton-author-vendors/README.md` (the halt);
  and over `runs/e1r3-tools-2026-08-21/records/*.json`, count records with a non-null `output_tokens` (zero
  of 42) and a non-zero `latency_s` (zero of 42).

---

## B1-11: F4 creates an operational surface it does not govern, and the running system contradicts 4.2's product consequence
- **Severity**: medium
- **Category**: internal tension / traceability
- **Verified against**: tree B (`core/config.py` identical between trees; `providers/__init__.py`)
- **Locus**: F4, line 71: "One model choice per book is a category error; the authoring plan needs a model
  per stage."
- **Problem**: F4 multiplies vendors per book and says nothing about the operational cost, in a programme
  whose own failure catalogue is dominated by operations: `AL-328` (a fixed cap converts a verbose model into
  a failing one, fivefold spread), per-endpoint rather than per-slug output ceilings, quantization and
  provider confounds that inverted a headline (run-6), an intermittent content filter on a benign preschool
  premise, a Modal leg that returned 503 all of 2026-08-21, and a credits exhaustion that killed 76 of 80
  shells. None of pinning, version drift, deprecation or fallback appears in F1..F8. Concretely,
  `providers/fallback.py` composes an ordered cascade with cross-leg failover, so in production the model
  that fills a book may not be the one selected, while 4.1's point is that model choice measurably moves
  prose quality; the vendor comparison ran "backend-pinned with fallbacks disabled" and production does the
  opposite, unremarked. And the shipped configuration inverts 4.2's recipe: `openrouter_model =
  "anthropic/claude-haiku-4.5"` for the fill, `review_openrouter_model = "anthropic/claude-sonnet-4.6"`,
  `review_provider = "mock"` by default. Section 3 claims to describe "the system as it actually runs today";
  on its most consequential lever it does not.
- **Why it matters for the goal**: per-stage selection is a real insight, but as stated it is a recipe with
  no operations contract, and the brief's own defect catalogue is mostly operations.
- **Recommendation**: Extend F4: *every stage pins a model and a serving endpoint; every pin has a named
  fallback whose quality delta is measured, not assumed; a pin change is a re-measurement event.* Add one
  line to 3.3 giving the production defaults and whether fallback is enabled, and reconcile them with 4.2's
  consequence or state that the consequence is not yet adopted.
- **How to check I'm right**: on tree B,
  `grep -n "openrouter_model:\|review_openrouter_model:\|review_provider:" src/cyo_adventure/core/config.py`
  (lines 459, 611, 612); `sed -n '1,25p' src/cyo_adventure/generation/providers/__init__.py`.

---

## B1-12: the pipeline gates on structural distinctness, which the framework says is not the defect
- **Severity**: medium
- **Category**: traceability / internal tension
- **Verified against**: tree B (`scripts/check_skeleton.py`, `src/cyo_adventure/diversity/`)
- **Locus**: 3.2: "**Anti-clone**: `structural_distance` against every in-cell tree must clear `TAU_CELL`
  (0.05 ...)". 3.3: "picks with recency weighting so a family sees the least recently used armature".
  Against F5, line 74, and 4.3's refutation of shape-preserving mutation.
- **Problem**: Three production mechanisms spend effort enforcing armature variety while the framework says
  armature variety is not what readers respond to. Either the framework is wrong and structural distinctness
  matters for unstated reasons, or these are cost with no measured return, and the brief does not adjudicate.
  The mutation tool is the sharpest case: 4.3 refutes shape-preserving mutation as a *variety* lever while
  3.1 retains it as a catalog accelerator, so the catalog can be grown with armatures that are, by the
  programme's own finding, perceptually redundant. Meanwhile the genuinely reader-facing floors in 3.2
  (satisfying-ending probability, in-degree cap, depth-qualified endings) are the only reader commitments in
  the system and no principle states them. Note the S-1 records do carry `min_catalog_distance` per shell, so
  the instrument is live and could answer this.
- **Recommendation**: For each of the three, state in section 3 what principle it serves and what it is
  worth, or mark it legacy pending removal. Add a principle covering the reader-experience floors, which are
  the only encoded position the programme holds on what a reading experience must guarantee.
- **How to check I'm right**: `grep -rn "TAU_CELL\|structural_distance" scripts/check_skeleton.py src/cyo_adventure/diversity/`;
  read 3.1's mutation bullet against 4.3's S8 line in the same document.

---

## B1-13: no principle covers failure, rejection, retry or latency, though the programme's own plan scores arms on latency
- **Severity**: medium
- **Category**: completeness gap
- **Verified against**: tree A (brief text), tree B (plan section 1; S-1 records)
- **Locus**: absence in F1..F8 and section 3. 3.4 says only "Blocking findings stop the book; advisories are
  recorded."
- **Problem**: The brief's own most recent live evidence is a 60% success rate: 3 of 5 books delivered, one
  lost to an empty 200 later reclassified as a deterministic content filter on a (skeleton, brief) pair 7 of
  7, and one lost to `content_filter` on "a 3-5 nursery story about a missing pair of yellow wellington
  boots". Latency reached **1,874 seconds** for one book, and the S-1 blind records show 372 to 1,007 seconds
  per censored authoring attempt on the metered legs. Nothing in the framework says what happens next:
  whether the request retries, on what model, at whose cost, what the guardian sees while waiting or after a
  failure, whether a blocked book is repaired or discarded, or what a human rejection at F8 does to the
  request. F8 ends at approval and is silent on rejection, which is the branch that costs money and goodwill.
  As with B1-5 and B1-9, this is a distillation loss rather than a blind spot: the plan's five-axis table
  scores **Economics** as "Tokens, **wall-clock latency in the request path**, repair rounds, amortized
  capital". The axis exists in the programme and not in the framework.
- **Why it matters for the goal**: a guardian's experience of the product is the request-to-book loop, and
  its failure modes are where a real user meets the system. A framework modelling only the happy path cannot
  price the product, since failures are unbilled work.
- **Recommendation**: Add a principle: *every request terminates in a book, an explained refusal, or a
  bounded retry; failure is budgeted, surfaced and measured.* Give section 3 a subsection for it carrying
  three numbers it can already state (delivery rate, retry policy, p50/p95 latency per band). Record the
  benign-premise content-filter result as a named risk.
- **How to check I'm right**: `deepseek-v4-pro-live-fill-plan-2026-08-20.md` section 5.2 and its "two
  failures"; plan section 1's axis table; then search the new brief for "retry", "latency", "reject" (no hits).

---

## B1-14: section 2 claims settled status for principles section 5 shows are blocked, and the census it opens with is stale
- **Severity**: medium
- **Category**: status honesty
- **Verified against**: tree B (register `S-0`, `S-2`; catalog identical between trees)
- **Locus**: line 51: "Each is load-bearing in the pipeline of section 3 and earned by an analysis in section
  4; **none is aspiration**." Against line 265's list of open experiments, and line 31: "the catalog spans 61
  graphs and 11,458 nodes".
- **Problem**: (a) **"Open" understates the status.** F5 is `S-2`'s hypothesis, and the register records
  `S-2` as "**blocked on S-0, S-1**", with `S-0` "**done, FAILED validation**". So the experiment that would
  test the framework's central reuse principle is blocked behind an instrument validation that failed, not
  queued. Section 5 says only that these "are the open experiments, gated on the plan". F8's second sentence
  likewise names its own criterion "a live open question tracked as register row `S-5`", one clause after
  section 2 says none is aspirational. Three of eight principles are, on the brief's own account, partly
  hypotheses, which is normal and must be said in section 2 rather than only in section 5.
  (b) **The census is stale.** Both trees hold **84 skeletons / 15,470 nodes**, not 61 / 11,458. The numbers
  are inherited unchanged from the superseded 2026-08-10 brief, in a document whose purpose is to be the
  current account, and whose immediately preceding merged work (`#730`) was a catalog expansion to cover all
  18 offered cells. The first hard number in the document is 38% low.
- **Recommendation**: Replace "none is aspiration" with a status column on the eight principles: *established
  / provisional / hypothesis under test*, with the register row and its blocked-or-open state for each.
  Regenerate the census at publication time and date it, ideally by script.
- **How to check I'm right**: the `S-0` and `S-2` status columns in `diversity-test-register.md` section F;
  `find skeletons -name '*.json' ! -name '*.contract.json' ! -name '*.lineage.json' ! -name '*.narrative.json' | wc -l`
  plus a node count, on either tree.

---

## B1-15: F6 is a principle of a different kind from the other seven, and the mixing is how B1-4 and B1-7 survived a careful read
- **Severity**: low
- **Category**: framework logic / communication
- **Verified against**: tree A
- **Locus**: F6, line 80.
- **Problem**: F1, F2, F3, F4, F5, F7 and F8 are statements about how the *system* is built. F6 is a
  statement about how the *programme* learns. The traceability matrix makes the mismatch visible: F6 is the
  only principle with no pipeline stage, not because it is unimplemented but because it is not that kind of
  claim. Mixing them means F6 reads as satisfied when the pipeline is silent, which is how an unvalidated
  in-path model reviewer (3.5), unvalidated blind judging (4.4) and a decision taken on decision-inert
  endpoints (B1-7) all coexist with it. The mixing also hides a real question: what is the *system's* version
  of F6? Something like "every automated judgement in the publish path carries a known-answer calibration set
  and is re-calibrated on model change."
- **Recommendation**: Split section 2 into "how the system is built" (F1-F5, F7, F8) and "how the programme
  learns" (F6, plus its missing system-side twin). Two short lists read faster than one mixed one, and the
  split makes the F6-versus-3.5 and F6-versus-4.2 contradictions impossible to miss.
- **How to check I'm right**: run the matrix at the top; F6 is the only row whose "mechanism" cell records a
  category difference rather than a defect.

---

## B1-16: what a new engineer cannot do after reading, and what an outside reviewer attacks first
- **Severity**: low
- **Category**: communication
- **Verified against**: trees A and B
- **Problem**: **A new engineer cannot**, after reading this: (1) locate the stage implementing F5, because
  there is not one (B1-1); (2) learn which model serves which stage in production, because 4.2 and the config
  disagree (B1-11); (3) learn what happens when a fill fails, a gate blocks, or a human rejects (B1-13);
  (4) learn that the S-1 numbers are exploratory and that its registered run halted (B1-7); (5) learn which
  thresholds are current, since only some are given inline (0.6 fill rate, 4.0 grams, `TAU_CELL` 0.05) and
  none is dated; (6) tell the `S-0..S-5` sourcing rows from the `S0..S9` designs, which both appear in
  section 4 of the same document and are distinguished only by a hyphen. *(Correction to the first issue: the
  evidence itself is reachable, on the source branch. The obstacle is that the brief points at it without
  saying it is unmerged.)*
  **A skeptical outside reviewer attacks, in this order**: no child or human has read any generated book and
  the brief never says so (B1-5); the headline model recommendation is contradicted by the programme's own
  quality table and by its own test plan (B1-2); the newest result is exploratory data pre-registered as
  decision-inert, from a run that halted at 4 of 80 shells (B1-7); the central diversity result is one pair
  of books and seven four-grams (B1-6); the per-cell n is 3 (B1-3); the cost claim excludes human review and
  failed generations while the goal says "cost-effective" (B1-10).
  **An investor** attacks something else: the framework optimises production and is silent on demand,
  retention, and whether a family's fourth book is worth requesting (B1-9, B1-5).
- **Recommendation**: Four cheap edits carry most of the value: a status column on F1..F8 (B1-14); a "what is
  not built yet" subsection closing section 3 (F5's stage, the two unwired delivery checks, the failure path);
  the provenance banner restored (B1-5); and a three-sentence provenance paragraph in 4.2 (B1-7). Rename the
  sourcing rows `SS-0..SS-5` to end the collision with `S0..S9`.
- **How to check I'm right**: hand the brief to someone with repository access and ask them to (a) point at
  the code implementing F5 and (b) state whether 4.2's numbers may trigger a decision under the programme's
  own multiplicity rule. Both attempts fail in under ten minutes.

---

## Summary of the four structural answers

1. **Does the framework follow from the evidence?** F1 yes. F2 yes as a rule, no as a description of the
   system. F3 yes in direction, but it reports a floor as quality, is measured in one cell, and its control
   condition is one the programme's own lesson log says understates current practice. F4's structure half is
   sound (0/6 is the one leg-level result with enough failures behind it); its prose half is contradicted by
   the programme's own ranking and by its own test plan. F5 is the weakest link: one pair of books, three
   known open channels, "not sufficient" dropped, and its end-to-end test blocked. F6 is sound and is
   violated three times elsewhere in the same document. F7 rests on a crashed run's spend, an uninstrumented
   arm and a billing artifact. F8 restates ADR-005 and adds a criterion that is blocked. **Principles resting
   on one run, one cell or n=3: F3, F4, F5, and half of F7.**
2. **Is it complete?** Real gaps, and three of them are demonstrably losses in distillation rather than
   programme blind spots, because the live test plan scores arms on axes the framework drops: the reader and
   premise fit (B1-5), catalog and vocabulary exhaustion plus the plan's scope exclusions for series books,
   gamebooks and the 3-5 band (B1-9), and latency plus failure handling (B1-13). Review economics is named
   but blocked (B1-10d). Provider operations is a genuine absence created by F4 itself (B1-11). Longitudinal
   drift is a real but cheaper absence, since the gate is deterministic and re-runnable.
3. **Does the pipeline implement the framework?** See the matrix. Fully: F1, F8. Partially: F2, F3, F4, F7.
   Not at all: F5. Contradicted: F6 (at 3.5). Mechanisms without principles: anti-clone distance, recency
   selection, catalog mutation, craft checks, and the reader-experience floors.
4. **Are the principles mutually consistent?** Four live tensions, all real: F3's gate-pass endpoint against
   F2's "gates are floors" (B1-3, the sharpest); F5's per-book decisional layer against F7's cost engineering
   and F8's review load, none of it priced; F2's floors against gates remaining the only production
   measurement because both delivery checks are unwired (B1-8); F4's per-stage selection against pinning,
   silent fallback substitution and deprecation (B1-11). A fifth, newly visible from the evidence: F6's
   pre-registration rule against 4.2's use of endpoints pre-registered as decision-inert (B1-7).
