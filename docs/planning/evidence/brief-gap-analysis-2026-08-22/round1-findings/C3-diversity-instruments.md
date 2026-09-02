# C3: Diversity, decision regurgitation, and the measurement instruments

Component audit of brief sections 1-finding-1, F5, F6, 4.3, 4.4. Sources read in full: the
2026-08-22 brief; the 2026-08-10 brief sections 1.1-1.5, 3.7-3.8, 4, 5.1-5.4, 13-16o, 19-26, 28, 31;
`architecture-respecification-2026-08-10.md`; `src/cyo_adventure/diversity/` (leaf, structure,
incell, query, normalize, panel); `moderation/leaf_diversity.py`; `generation/skeleton_match.py`;
`scripts/check_sibling_fills.py`, `check_solution_transfer.py`, `analyze_sibling_exposure.py`;
evidence dirs `d6-contract-sharing`, `d7-stratified-plan`, `d7b-bare-names`, `d7c-binding-notes`,
`recognition-protocol-pilot` (all six rater verdicts), `mutation-per-request-pilot`,
`q3c-premise-mode`, `m4-stake-economics`; register section F (`S-0`..`S-5`); `AL-510`..`AL-514`.

**Retraction up front.** An earlier pass of this audit reported `results.md`, the `S-0`..`S-5`
register rows, `AL-510`..`AL-514`, the skeleton-sourcing test plan, and
`evidence/skeleton-author-vendors/` as missing. That was a checkout artifact on my side. All exist,
were read from `.worktrees/brief-evidence/`, and every finding below is grounded in them. Nothing
here rests on absence.

All numbers below were recomputed from committed artifacts unless marked as quoted.

---

## C3-1: The stratified plan's own flagship artifact fires `S-2`'s pre-registered falsifier, and the programme retired the instrument rather than the hypothesis

- **Severity**: critical
- **Category**: defect definition
- **Locus**: `docs/planning/evidence/recognition-protocol-pilot/verdict_d7b-bare-CD_r1.json`,
  `verdict_d7b-bare-CD_r2.json`; register section F row `S-2` falsifier (b);
  2026-08-22 brief section 4.4; `AL-511`
- **Problem**: The `d7b-bare-names` C/D pair is the artifact F5 rests on: "shared structure, bare
  identifiers, **2.3** shared 4-grams per 1000", below the 3.3 idiom floor, described in 16l as
  "the first artifact in the programme to share a plan and still be indistinguishable". Two
  counterbalanced blind raters read that exact pair on 2026-08-21. Both returned
  `same_adventure: yes`, `first_yes_position: 2`, `distinctness_1_to_5: 1` (the floor of the scale).
  Their stated evidence is not shape. Rater 1: *"Scene 2 repeats Book One's exact three-way opening
  choice (wait patiently for a clue / work the structure with your own hands / ask the old keeper
  who knew the builder), and every scene after maps one-to-one onto the same beats, hub, dial, and
  endings."* Rater 2 names the same three acts independently.

  That is the defect of brief section 1.3 stated verbatim: the same decisions, in the same order.
  Under the worked open-the-door example, "wait / work the structure / ask the keeper" against
  "wait / work the structure / ask the keeper" is row one of the table, "**Defect.** Same decision,
  new paint."

  Register row `S-2` (stratified reuse viability) pre-registered exactly this as its kill test:
  falsifier "(b) both raters land same-adventure at or before position 4 on the most-similar pair.
  Either fires = S2 out." The d7b pair is a two-book instance of S-2's design (one structural
  stratum, independently authored decisional strata, same 26-node armature). Both raters landed at
  position **2**. S-2's falsifier is met on data already in hand.

  The recorded response is that the *instrument* failed. But read the pre-registration: known
  answer 1 (same-armature pairs must fire at or before scene 5) **passed**, on all four verdicts;
  only known answer 2 (the control) failed. The programme discarded an instrument that satisfied
  its positive known-answer, on the strength of its negative control, in the one run whose positive
  verdicts contradict the headline hypothesis. Nothing in `AL-511`, `results.md`, or brief 4.4
  records that the same-armature verdicts are also data about F5, not only calibration.
- **Why it matters for the goal**: F5 ("reuse structure freely; never reuse decisions; generate the
  decisional layer per book") is the load-bearing principle of the whole sourcing architecture, and
  the only evidence for it is a wording metric. On the one occasion anything read the books, both
  readers said the decisions repeat. If F5 is false, the catalog-reuse economics that justify a
  skeleton catalog at all collapse, and the programme is spending on skeleton depth to fix a defect
  skeleton depth does not touch.
- **Recommendation**: Stop treating the six S-0 verdicts as instrument calibration only. Re-report
  them as an F5 result with the confound stated: the stratified pair reads as decision-repetitive
  to two blind raters at scene 2. Then either (a) repair the instrument as `AL-511` proposes and
  re-run the *same-armature* leg on fresh stratified pairs before any further stratified spend, or
  (b) if the instrument stays retired, F5 must be downgraded from a framework principle to an
  untested hypothesis in the 08-22 brief, because its only perceptual evidence has been declared
  inadmissible and its remaining evidence (2.3 shared grams) is a wording measure that section 1.3
  says is not the defect.
- **How to check I'm right**: `cat .worktrees/brief-evidence/docs/planning/evidence/recognition-protocol-pilot/verdict_d7b-bare-CD_r{1,2}.json`
  and compare `strongest_signal` against the 2026-08-10 brief section 1.3 worked-example table.
  Then read register section F row `S-2`, falsifier (b), and note that the d7b pair satisfies S-2's
  arm description.

---

## C3-2: The control failure is better evidence of catalog convergence than of instrument failure, and the evidence favours that reading

- **Severity**: critical
- **Category**: rival hypothesis
- **Locus**: `evidence/recognition-protocol-pilot/verdict_ctrl-clocktower-museum_r1.json` and `_r2.json`;
  `results.md`; `AL-511`
- **Problem**: The control was `d7-stratified-plan/filled_C` (26-node clocktower) against
  `mutation-per-request-pilot/book-s-the-midnight-museum` (95-node museum): different graph,
  different world, same band. Both raters called it same-adventure. The two readings:

  **Reading A, instrument failure.** `AL-511` and `results.md` argue this: the pre-registered
  criteria were asymmetric (position-bounded at scene 5 for known answers, unbounded for the
  control), and the re-based control lost the cross-band property of the original. The numbers
  support this half: the control's first-yes positions are **12 and 41** against **2, 2, 2, 2** for
  the same-armature pairs, and its distinctness scores are **2** against **1**. A symmetric
  position-bounded firing rule would have separated all six verdicts correctly. On a continuous
  reading the instrument ordered every pair right; only the binarisation destroyed the signal.

  **Reading B, the catalog is convergent.** The raters' free text is not noise. Rater 2:
  *"rooms off a hub teaching pieces of a cipher, a central mechanism set exactly-or-forced-or-guessed
  that jams when forced, a strongroom with the maker's letter, a hidden workshop behind a secret
  panel, and a caught-taking-the-treasure ending alongside tell-the-town versus keep-it-secret
  endings."* Rater 1 names the same chain independently. Inspection confirms it is real, not
  hallucinated: the museum skeleton carries node ids `n_cipher`, `n_vault`, `k_founder`,
  `k_display_force`, `e_set_jammed_globe`; the clocktower carries `n_note`, `n_clockface`,
  `n_setjam`, `n_backpanel`, `n_vault`, `n_end_secret`, `n_end_keepsake`, `n_end_caught`. Two
  independently authored catalog skeletons, in different cells of the programme's own history,
  converge on the same decision chain and the same three-way ending economy.

  **Which the evidence favours: both, and they are not exclusive, but B is the load-bearing one.**
  A is a specification defect in a threshold and is cheap to fix. B is a fact about the product.
  Three independent lines corroborate B and none of them depend on this run:
  - Q-3c: 8 of 10 isolated generations put a light-or-signal beacon at the centre; two instances at
    one tier invented the same place name (*The Lantern Under/Beneath Marrow Hill*).
  - Brief section 27: cross-vendor, same brief, **156.35 shared 4-grams per 1000, ~120x the
    cross-vendor floor** on premise. Distribution-level, not family-level.
  - Brief section 22: across 105 sibling pairs on a single skeleton, **83 exceed the convergence
    budget**, median 9.2.

  So Reading A explains why the *instrument* said "yes" rather than "yes at 41", and Reading B
  explains why either rater said yes at all. The programme has recorded A as the finding and B as a
  caveat inside A. The correct ordering is the reverse: the control is not a bad control by
  accident, it is a bad control because the catalog does not contain two 10-13 mysteries that are
  decisionally different. `results.md` says exactly this and then does not act on it: *"within one
  band, two catalog-lineage mysteries can genuinely be the same adventure at the decision level."*
- **Why it matters for the goal**: If B is right, the negative control the repair path asks for
  ("author or recover a true cross-band control") does not exist and cannot be *found*, it has to
  be *manufactured*, and manufacturing it is the same problem as producing decisionally-distinct
  books. Repairing the instrument on a cross-band control also makes it blind to exactly the
  within-band convergence that a repeat reader actually meets, because a child does not read across
  bands in one sitting. A cross-band control repairs the instrument by moving it away from the
  operating point.
- **Recommendation**: Adopt the symmetric position-bounded rule (`AL-511` item 2) *and* treat the
  within-band cross-graph pair as a **measured convergence result** rather than a discarded control.
  Report it as: "two independently authored 10-13 catalog skeletons, different graphs and worlds,
  are read as one adventure by two of two blind raters at 2.2 shared 4-grams per 1000." Then run
  that measurement across the catalog: for every within-cell skeleton pair, does the decision chain
  repeat? That is a catalog audit the programme has never done and it is the direct measurement of
  the capital question.
- **How to check I'm right**: run
  `uv run python scripts/check_sibling_fills.py docs/planning/evidence/d7-stratified-plan/filled_C.json docs/planning/evidence/mutation-per-request-pilot/book-s-the-midnight-museum.json`
  (returns 12 shared grams, **2.2 per 1000**, 0 shared menu frames), then read both control verdict
  JSONs. The raters describe a chain the metric scores as cleaner than the generator idiom floor.

---

## C3-3: A book pair can clear every surviving instrument and still be unanimously read as the same adventure: the adversarial example is already committed

- **Severity**: critical
- **Category**: measurement gap
- **Locus**: computed over `evidence/d7b-bare-names/filled_{C,D}.json` and
  `evidence/d7-stratified-plan/filled_C.json` vs `evidence/mutation-per-request-pilot/book-s-the-midnight-museum.json`
- **Problem**: Brief 4.4 lists the surviving instruments as shared-4-gram counting, solution
  transfer, and structural distance. Question 4 asks whether a pair could be maximally
  boring-similar to a child while clearing all three. It does not need constructing; two exist.

  | | d7b-bare C vs D | clocktower_C vs museum_S |
  | --- | --- | --- |
  | shared 4-grams / 1000 (shipped script, label-inclusive) | **3.2** (pass, budget 4.0) | **2.2** (pass; *below* the 3.3 idiom floor) |
  | shared 4-grams / 1000 (body-only, brief's standard scope) | **2.3** (below floor) | not recomputed |
  | shared menu frames | 0 | **0** |
  | `structural_distance` | 0.0 (same tree, gate N/A) | **0.1239** (2.5x `TAU_CELL` 0.05, passes) |
  | anti-template guard (`anti_template_verdict`) | **PASS**, median masked distance **0.925**, p25 0.889, **0 of 26** nodes flagged | undefined (raises on cross-tree pairs) |
  | solution transfer | not computable (needs a narrative contract; see C3-11) | not computable |
  | **two blind counterbalanced raters** | **same adventure, scene 2, distinctness 1/5** | **same adventure, distinctness 2/5** |

  The anti-template guard result is the sharpest. Its own docstring says it "fails a dog-for-cat
  noun swap while passing two genuinely re-authored fills of one skeleton". It scores the d7b pair
  at **0.925** median masked-content-unigram Jaccard distance, near the top of its range, on a
  pair whose readers say every scene maps one-to-one. The guard is not miscalibrated; it is
  measuring lexical form, which is precisely what a competent re-skin varies. Tevet and Berant
  (cited by the programme itself at 3.8) predicted this: automatic metrics move *form* diversity,
  humans estimate *content* diversity. The programme cited the paper and then shipped the metric it
  warns against.

  **Each instrument's false-negative profile:**
  - *Shared 4-grams*: sees only four-consecutive-word identity in bodies (and, as shipped, labels).
    Cannot see "Ask the Warden" vs "Ask the bell-ringer" (brief 19 records eleven of thirty-five
    choices sharing their first content word at zero shared grams); cannot see convergent
    elaboration (brief 21: 28 of 33 removed grams were not copied from the deleted text); cannot see
    a shared category vocabulary (16l correction: five cipher forms, one-in-five collision by
    chance, "the four-gram measure cannot see it by construction"). Its known-answer validation is
    one-sided: calibrated on arms scoring 2.8 / 9.0 / 12.6 / 25, all of which are *bad* anchors.
    The budget 4.0 is inherited and unowned ("the one we did not set: it predates this work"), with
    only 0.7 of headroom over the measured 3.3 floor.
  - *Structural distance*: a feature-vector distance over 11 counts, two ending histograms, and a
    topology flag. `TAU_CELL` = 0.05 sits **below the 5th percentile (0.155)** of the hand-authored
    same-cell distribution (`ws5_floor_baseline.json`: min 0.000469, p05 0.154657, median 0.379906).
    It is a duplicate detector, not a diversity floor, and the baseline's own `clamps` field says so
    ("rejects the observed same-cell minimum pair at 0.000469 with margin"). It sees nothing about
    what happens at a fork.
  - *Solution transfer*: validated only against a battery of three deliberately-constructed
    known-**bads** (1.000, 1.000, 0.700). No known-good anchor exists. Tiers 2-3 classified 2 of 6
    props on an unseen contract. And it needs an artifact 98% of the catalog lacks (C3-11).
- **Why it matters for the goal**: every gate the product ships can be green on a pair that two
  readers call one book. A green battery is currently evidence of nothing about the property the
  programme exists to deliver, and F2's "gates are floors" framing understates it: these are floors
  under a different building.
- **Recommendation**: Publish this table in the brief as the instruments' joint false-negative
  demonstration, using the committed artifacts. Then treat "no instrument we trust separates a pair
  our raters unanimously merge" as the programme's top open problem, ahead of the sourcing
  experiments that are gated on it. Concretely: the cheapest candidate instrument is the one the
  raters keep using unprompted, *aligned-fork act identity*: for each aligned choice position, do
  the two books ask the reader to perform the same act? Both raters produced that comparison by
  hand in one sentence; nothing in the repo computes it.
- **How to check I'm right**: reproduce the table with
  `uv run python scripts/check_sibling_fills.py <pair>` and
  `uv run python -c "from cyo_adventure.diversity.leaf import anti_template_verdict; ..."` on the
  d7b pair; the ATG returns `PASS`, `median 0.925`, `0` flagged nodes.

---

## C3-4: The defect definition is a single-case inference, and the rival hypotheses have not been discriminated

- **Severity**: critical
- **Category**: defect definition
- **Locus**: 2026-08-10 brief sections 1.3, 5.1-5.3; 2026-08-22 brief section 1 finding 1
- **Problem**: The 08-22 brief states as finding 1: "A reader tracks what they were asked to
  decide, not the shape of the tree recording it." Tracing the evidence back, the assertion rests
  on:
  1. **One blind model rater on one pair (S9)**, quoted at 5.1: *"Same three doors, decode the note
     / read the building for a way in / go find the last person who remembers, in the same
     sequence."* One rater, one artifact, no replication of the S9 pair.
  2. **An inference from S8** (5.2): mutation changed the graph, recognition barely moved, mutants
     retained 100% of parent beats, therefore shape is not the fingerprint. This is a valid
     *negative* (shape alone is insufficient) and does not establish the positive (decisions are the
     fingerprint), because S8 held scene identity, beats, premise, world, and act constant too. Any
     of those is an equally good candidate.
  3. **A worked example (1.3's table)**, which is an assertion about what a reader would feel, not
     a measurement. The brief is explicit that no human and no child has read anything in the
     programme.

  Everything after that treats the definition as settled. **Rival hypotheses and their status:**

  | Rival driver of perceived sameness | Discriminated against? | Evidence |
  | --- | --- | --- |
  | **Premise / dramatic question** | **No, and it is positively implicated** | 16g.1: premise carries "as much or more" of the shared-gram trace than `choice_semantics`. Q-3c: 8 of 10 isolated generations converge on a beacon premise. Section 27: 156.35 shared grams/1000 cross-vendor on premise, ~120x floor. Section 24: independent authors reproduced a title word-for-word. Never separated from decisions in any arm. |
  | **Scene identity** (the note-decoding scene) | **No** | 5.2 explicitly names it as the fingerprint, then 1.3 substitutes "decisions" without an arm separating the two. Every S2-S9 design held both constant simultaneously (5.3 table). The d7b shared stratum still names scenes via node ids (`n_note`, `n_setjam`, `n_backpanel`). |
  | **Ending shape / economy** | **No** | Both control raters cite the ending triad (tell-the-town / keep-secret / take-the-treasure) as decisive. It is a property of the ending set, not of any fork. `structural_distance` includes an ending-kind histogram but at 0.3 weight and position-blind. |
  | **Outcome of decisions rather than decisions** | **No** | 13.3: "the stakes at two [forks]"; raters cited stake, not act, at two of three decisive forks. 16k's surviving fragment was *irreversibility*, a consequence property. The treatment arm was never decomposed ("We cannot presently attribute the effect to decision variation alone"). |
  | **Prose voice / craft** | **Partly, negatively** | S7: recognition 2.5 at both craft extremes (4.9 and 2.2). Weak evidence that voice is not the driver. |
  | **Pacing rhythm** | **No** | Never varied in any arm; `structural_distance` proxies it only through mean branching and depth counts. |
  | **Character archetype** | **No** | Q-3c notes "several with an elder keeper"; the control raters cite the founder/maker figure. Never isolated. |
  | **Graph topology** | **Yes, refuted** | S8 (distance 0.0000 mutants, recognition unmoved) plus 16h. This is the one rival the programme genuinely closed. |

  So exactly one rival has been discriminated, and it is the one the programme was trying to *stop*
  believing. The remaining six are live, and two (premise, ending economy) have direct positive
  evidence naming them from the S-0 raters' own free text.
- **Why it matters for the goal**: F5's engineering consequence, share topology and a bare-names
  fact graph, generate `choice_semantics` per book, is derived entirely from the defect definition.
  If the real driver is premise plus ending economy plus scene identity, then generating
  `choice_semantics` per book fixes a channel nobody was reading, at a cost per book, while leaving
  the driver in the shared stratum. The d7b result is exactly what that would look like: the wording
  channel closes to 2.3, and readers still merge the books at scene 2.
- **Recommendation**: Run the decomposition the programme has repeatedly deferred, at the cheapest
  possible scale, as a factorial rather than a bundle. Four two-book arms over one armature, each
  varying exactly one layer against a fixed base: (i) act at each fork, (ii) premise, (iii) ending
  economy, (iv) stake/consequence irreversibility. Score with the *repaired* recognition protocol's
  first-yes position (continuous, not binary). This is the experiment 5.3 identified as "the cell we
  never tested" on 2026-08-10 and it is still untested on 2026-08-22. Until it runs, the 08-22
  brief's finding 1 should be stated as a hypothesis with its single-case provenance visible, not as
  a finding.
- **How to check I'm right**: grep the 08-10 brief for every citation supporting 1.3 and trace each.
  Section 5.1 is the only primary observation; 5.2 and 5.3 are inference from it. Then check the
  5.3 table: "Scene identity and action semantics were held constant from S2 onward, in the eight
  designs the table covers", the same sentence concedes that no arm has ever separated the two.

---

## C3-5: The "wordless structural stratum" carries 473 words, and its non-prose contents are decision-bearing

- **Severity**: high
- **Category**: stratified plan
- **Locus**: `docs/planning/evidence/d7b-bare-names/structural_bare.json`;
  `architecture-respecification-2026-08-10.md` section 2 table
- **Problem**: Question 5 asks what is in the shared stratum that is not truly wordless in effect.
  Measured directly on the artifact (strings of 4+ words):

  - **473 words** of English prose, reproducing the 16l correction figure exactly.
  - **303 of those 473 (64%) are per-node**, in `nodes.<id>.invention.<slot>.note`, across **18 of
    26 nodes**. Only 170 words are global. This *contradicts the published explanation* for why the
    residual is harmless. The 16l correction says: "The glosses were pulled into local context at
    every node establishing or assuming that fact; the binding notes appear once, in a global
    preamble. Whether the operative variable is *what the text describes* or *how often it is
    re-read* is now open." The artifact shows the residual is also mostly per-node, so the
    re-reading distinction does not separate the deleted 422 words from the surviving 473. The arm
    that would settle it (D-7c, "the highest-value single experiment we can currently run",
    2026-08-11) **has still not produced fills**: `evidence/d7c-binding-notes/` contains
    `build.py`, `kernel_notes.json`, `AUTHOR_INSTRUCTIONS.md`, `score_fills.py` and no `R-*/`
    directory and no `results.md`, on this branch, on `origin/main`, and on the evidence branch.
    `AL-510` records why: the fills were authored and lost with a deleted working branch.

  - **The non-prose contents are decisionally load-bearing.** The shared `facts` vocabulary is 32
    identifiers, and they enumerate *decision outcomes*: `test_forced` against `test_passed`,
    `passing_kept_private` against `passing_made_public`, `self_reliance_shown`, `patience_proven`,
    `keeper_offer_earned`, `route_named_by_note`. A shared stratum that declares both branches of a
    moral fork has fixed the fork. The `world_recipe` shares the category vocabulary the brief's own
    section 22 identifies as the binding constraint on series novelty: `cipher_forms` with **5**
    kinds, count 1 per story, which is the axis that "forces a repeated puzzle by book 6".
  - **Node ids are scene identities and they are shared.** `n_note`, `n_keeper`, `n_stairs`,
    `n_clockface`, `n_setcorrect`, `n_setjam`, `n_backpanel`, `n_vault`. Brief 5.2 says a vertex "is
    not an abstract position, it is *the note-decoding scene*... that is the entire fingerprint."
    The stratified plan shares the fingerprint 5.2 names, in the layer it calls wordless.

  The respecification's own claim for safety: "`AL-197` and `AL-212` show it provably does not
  determine the decision", is a claim about the *fact graph* (four options at one fork sharing one
  obligation). It is not a claim about node identity, the fact vocabulary's outcome names, or the
  device category list, all three of which the stratum also carries.
- **Why it matters for the goal**: the stratum boundary is not implementable as specified, because
  the rule that defines it has been restated three times and failed contact with the artifact each
  time (16l: "no free text of any kind" → refuted by 473 words; then "free text attached to the
  fact vocabulary" → the residual is also per-node; then the reviewer's "anything determining what
  the reader does, thinks about, or uses to solve a problem belongs in the per-book layer" → the
  fact names and category lists violate this and are still shared). Every book built on this
  stratum inherits the same cipher-vault-founder-keeper adventure regardless of what the decisional
  layer says, which is what the S-0 raters reported.
- **Recommendation**: (1) Run D-7c or formally withdraw the gloss attribution; it has been the
  named highest-value experiment for eleven days and its artifacts were lost once. (2) Apply the
  reviewer's rule to the *identifiers*, not only the prose: a shared stratum may not name scenes
  (`n_setjam`), may not enumerate decision outcomes (`passing_kept_private` / `passing_made_public`),
  and may not fix a puzzle-device category list. What survives that is topology plus arity plus
  typed slots, which is close to nothing, and that is the honest cost of F5, which should be
  stated rather than discovered. (3) Add a programmatic assertion (16l promised one: "Any future
  claim of the form 'the shared artifact contains no X' is now checked programmatically before it is
  published"), no such check exists in `scripts/`.
- **How to check I'm right**:

  ```sh
  uv run python - <<'EOF'
  import json,re
  s=json.load(open('docs/planning/evidence/d7b-bare-names/structural_bare.json'))
  def walk(o,p=""):
      if isinstance(o,dict):
          for k,v in o.items(): yield from walk(v,f"{p}.{k}")
      elif isinstance(o,list):
          for i,v in enumerate(o): yield from walk(v,f"{p}[{i}]")
      elif isinstance(o,str): yield p,o
  n=g=0
  for p,v in walk(s):
      w=len(v.split())
      if w<4: continue
      (globals().__setitem__('n',n+w) if p.startswith('.nodes.') else globals().__setitem__('g',g+w))
  EOF
  ```

  or simply `python3 -c "import json;print(json.load(open('docs/planning/evidence/d7b-bare-names/structural_bare.json'))['facts'])"`
  and read the outcome-pair names. `ls docs/planning/evidence/d7c-binding-notes/` shows no fills.

---

## C3-6: Almost none of the diversity apparatus runs in the production request path, and what does run is scoped to the wrong unit

- **Severity**: high
- **Category**: production wiring
- **Locus**: `src/cyo_adventure/moderation/leaf_diversity.py`, `diversity/query.py`,
  `diversity/history.py:191`, `generation/skeleton_match.py:719`, `.github/workflows/ci.yml:580`;
  `UW-C315`
- **Problem**: Full inventory of what actually executes when a guardian requests a book.

  | Mechanism | Where it runs | Gates? |
  | --- | --- | --- |
  | Skeleton recency/theme weighting (`select_skeleton_for_cell`) | request path | soft weight only, never excludes |
  | `similarity_context` → `build_differentiation_directive` | request path (`story_requests/authoring_plan.py:435`) | prompt text only; **effect never measured** (C3-15) |
  | Anti-template guard (`anti_template_verdict`) | moderation pipeline (`pipeline.py:389`) | **advisory, fail-open**, never blocks; its own message says "thresholds uncalibrated per band" |
  | `check_sibling_fills.py` (shared 4-grams) | **nowhere**, manual script only | no (`UW-C315`, open) |
  | `check_solution_transfer.py` | **nowhere** | no |
  | `structural_distance` / `TAU_CELL` | **catalog time only** (`ci.yml:580`, `check_incell_clones.py`) | yes, but over skeletons, never over books |
  | `run_diversity_eval.py --check` (panel R1-R6) | CI, offline panel | yes, over 8 fixture fills |
  | `diversity/aggregate.py`, `lexical.py` (Phase 2) | **not implemented**: `diversity/__init__.py` says so explicitly | n/a |
  | `measurement/` (sentinel reinsertion, taxonomy, report) | offline scripts only; no `src/` importer | no |
  | `flywheel/` | offline scripts only (`scripts/flywheel_*.py`) | no |
  | Recognition protocol | experiment only, and unvalidated | no |

  Two compounding defects in what *does* run:

  1. **The ATG is a near-total no-op in production.** `select_atg_comparison_partner` returns a
     partner only when the family's recent history contains a prior fill of the *same skeleton*. But
     `select_skeleton_for_cell` weights *against* recent reuse specifically to avoid that. So the
     one wired convergence guard fires only in the case the selector is designed to prevent, and
     never on the case measured at 96.3 shared grams per 1000 (`AL-498`), which is **cross-family**
     reuse of one skeleton. The guard cannot see cross-family convergence at all: it reads only
     `load_family_history`.
  2. **History is family-scoped where the defect is child-scoped.** `history.py:191` and
     `skeleton_match.py:719` both filter on `Storybook.family_id` over a 20-row window. Brief 1.5:
     "The unit is the child, not the household." `analyze_sibling_exposure.py`'s own docstring
     already records this ("no query anywhere narrows prior `skeleton_slug` to the requesting
     child, even though `story_request.profile_id`, `storybook_assignment` and `reading_state` all
     carry the per-child link"). Measured cost, 2000 trials: in `10-13/short`, P(a child meets a
     repeat by their 3rd request) is **0.275** under the shipped family scope with 2 children versus
     **0.160** child-scoped; with 3 children **0.413** versus **0.152**. The shipped scoping roughly
     **doubles to triples** the per-child repeat rate in a multi-child family, and simultaneously
     steers a child away from skeletons only a sibling read.
  3. **Recency-window burn.** With 2 children reading 1 book/month, only **28%** of a child's
     band-lifetime reading still sits inside the 20-row window; with 3 children at 2/month, **9%**.
     The de-weighting signal is mostly absent exactly when it is most needed.
- **Why it matters for the goal**: the programme's 08-22 brief describes a pipeline in which
  "delivery measurements" and diversity checks sit between the fill and the human. In the deployed
  system, one advisory check that almost never fires is the whole of it. `AL-498` demonstrates a
  published-eligible pair at 24x budget passing the deterministic gate. Shipping without wiring
  means the defect reaches guardians and children, and the human approver has no signal telling them
  the book is a re-skin of one they approved for another family.
- **Recommendation**: In priority order, and all are small: (1) narrow `recent_skeleton_usage` and
  `load_family_history` to `profile_id` when the request carries one, keeping family scope as the
  fallback, the columns already exist; (2) wire `check_sibling_fills.py` into the fill pipeline as
  `UW-C315` proposes, scoped **cross-family** on `skeleton_slug`, not just within a family; (3) give
  the ATG a cross-family partner selector, since that is where the 96.3 lives; (4) decide whether
  the ATG's advisory status is intentional now that its thresholds have been uncalibrated for the
  whole of WS-1.
- **How to check I'm right**: `grep -rn "family_id" src/cyo_adventure/diversity/history.py src/cyo_adventure/generation/skeleton_match.py`;
  `grep -rn "check_sibling_fills\|check_solution_transfer" src/ .github/` (returns only docstring
  mentions); `uv run python scripts/analyze_sibling_exposure.py --section siblings --trials 2000`.

---

## C3-7: The shipped shared-gram checker computes the scope the brief explicitly disowns, and its calibration constants disagree with the brief's

- **Severity**: high
- **Category**: instrument validity
- **Locus**: `scripts/check_sibling_fills.py:63-72` (`_leaf_text`), `:196-210` (`main`),
  `:96-113` (`pairwise_shared_grams`)
- **Problem**: Three defects in the one deterministic instrument the 08-22 brief lists first.

  1. **Wrong scope.** 16l defines the metric it standardises on: "Numerator: distinct word four-grams
     present in both books... **Scope: node bodies only.** Choice labels are excluded, and they have
     to be." The correction block gives the reason: joining bodies to labels "manufactures four-grams
     spanning the join that exist in neither the body nor the label: seven of them in the flattened
     arm alone, including `drop down inside inside`". The shipped `_leaf_text` does exactly the
     disowned thing:

     ```python
     parts.append(str(node.get("body", "")))
     parts.extend(str(c.get("label","")) for c in node.get("choices") or [])
     return " ".join(parts)
     ```

     Every number the script produces is label-inclusive. Verified: the d7b pair returns **3.2**
     from the script against the brief's cited **2.3**, a 39% inflation, and the brief's own
     re-derivation block gives 3.19 label-inclusive and 2.33 body-only for that pair. So the
     production instrument and the published headline are two different measures, and the published
     headline's margin against the 3.3 idiom floor (2.3 < 3.3) **disappears under the shipped
     measure** (3.2 ≈ 3.3). The flagship "below the generator floor" claim is scope-dependent.
  2. **The gate is the diluted aggregate, not the worst pair.** `main()` computes one rate over all
     fills pooled, divided by the mean word count of the whole set. The module's own `#ASSUME` block
     says so: "two fills that converge heavily on their own can still clear the aggregate budget once
     several clean fills are averaged in", and "this helper [`pairwise_shared_grams`] is **not wired
     into main()** and nothing gates on it." A production gate on N sibling books would therefore
     miss the exact worst pair a child is most likely to meet.
  3. **Calibration drift.** The docstring's arms are "obligation 2.8, control 25, free 12.6,
     clocktower 9.0". The 08-10 brief's re-derived table is 2.9 / 11.8 / 13.6 / 17.2 / 2.3 / 3.3 /
     4.0. Neither set can be mapped onto the other, and the script's constants have never been
     updated against the brief's 2026-08-11 re-derivations. A reader calibrating a threshold from
     the CLI `--help` gets numbers the brief has superseded.
- **Why it matters for the goal**: this is the instrument F6 nominates as trustworthy and the one
  `UW-C315` proposes to promote into the fill pipeline. Promoting it as written ships a measure that
  is 39% pessimistic against its own published budget, dilutes across a set, and carries stale
  calibration in its user-facing help.
- **Recommendation**: Add `--scope {body,leaf}` defaulting to `body`, so the shipped default equals
  the published standard. Wire `pairwise_shared_grams` into `--check` with a `--max-pair-per-1000`
  flag and gate on the worst pair as well as the aggregate. Replace the docstring's calibration list
  with the 2026-08-11 re-derived table and cite it.
- **How to check I'm right**: `sed -n '63,72p' scripts/check_sibling_fills.py` shows labels in
  `_leaf_text`; `uv run python scripts/check_sibling_fills.py docs/planning/evidence/d7b-bare-names/filled_{C,D}.json`
  returns 3.2 against the brief's 2.3; `grep -n "not wired into main" scripts/check_sibling_fills.py`.

---

## C3-8: The three instrument failures share one cause: every instrument is anchored only at the "similar" end

- **Severity**: high
- **Category**: instrument validity
- **Locus**: brief 20 ("A battery of known-bad artifacts"); `tests/data/diversity_panel/panel.json`;
  brief 16m; `check_solution_transfer.py` validation section
- **Problem**: Question 2 asks for the common cause of the DecisionSignature inversion, the
  six-question compression, and the recognition-control failure. The proximate causes differ
  (D-3: annotation at a layer that omits the binding; 16m: items constant by construction of the
  design; S-0: an asymmetric firing rule and a contaminated control). The systematic error underneath
  all three is a validation asymmetry the programme stated as a constraint and never treated as a
  defect.

  Brief section 20: *"the only validation available to any new instrument is a deliberately
  constructed known-bad artifact."* Every instrument in the programme is therefore calibrated at
  one end:
  - *Solution transfer*: three constructed known-bads at 1.000 / 1.000 / 0.700. No known-good.
  - *Shared 4-grams*: budget inherited; floor (3.3) measured on books "sharing nothing but the model
    and the age band", which is a *lower bound on the generator*, not an artifact known to read as
    two different adventures.
  - *`TAU_CELL`*: set to reject the observed same-cell minimum (0.000469). Bad end only.
  - *CI diversity panel*: 6 ATG pairs; the two `expected_verdict: fail` cases are
    `cave-space-swap` (a noun swap) and `cave-space-identical` (a copy). The four
    `expected_verdict: pass` cases are re-themed fills of one skeleton (`cave-sea` / `cave-space` /
    `cave-dino`). So the CI gate's "known-different" anchor is **assumed**, and it is assumed to be
    exactly the artifact class the S-0 raters unanimously call one adventure.
  - *Recognition protocol*: known answer 1 (positive) satisfied; known answer 2 (negative) was the
    first negative anchor the programme ever attempted, and it failed on first contact.

  A measure calibrated only at the bad end can be shown to *fire*; it cannot be shown to
  *discriminate*. That is precisely the failure mode of all three retired instruments, and it is why
  each of them looked healthy until an artifact from the other end arrived: DecisionSignature had
  kappa 0.77-1.00 and inverted; the six questions produced stable plausible cells and Q4 sat at 5 in
  12 of 12; the recognition protocol matched manual history on four of four positives and merged the
  first negative it was shown.

  A second, weaker common thread: each instrument's construct is defined at a layer of the
  *architecture's own data model* (the plan, the fork, the armature) rather than at the
  reader-visible surface, so it inherits the architecture's abstraction boundaries, 15 says this
  outright for DecisionSignature ("that abstraction is exactly what discards the property readers
  respond to"), and `protocol.py`'s rater instruction fuses three constructs in one sentence ("the
  same situations in the same order, the same choices meaning the same things, the same shape of
  story"), so a `yes` verdict is un-decomposable.

  **Implication for the surviving instruments**: they carry the identical defect and have not yet
  met the artifact that exposes it, except that they have, and it was not read as such. The
  clocktower/museum control (C3-3) is the missing known-good anchor arriving by accident, and it
  scores *better than the idiom floor* on the surviving metric while reading as one adventure.
- **Why it matters for the goal**: the programme's stated remedy (F6, "trust no instrument until it
  survives a known-answer test") is being applied with only half a known-answer set, so it does not
  do the work it is credited with. Three instruments have already been paid for and discarded on
  this basis; the same money is currently being spent on the fourth.
- **Recommendation**: Make a **known-good artifact** a first-class deliverable, before any further
  instrument work. It must be constructed, not sampled: two books over one armature where a human
  author has deliberately made every fork ask a different act, with a different premise, different
  ending economy, and different scene set. That single artifact is the missing anchor for the
  4-gram budget, solution transfer, structural distance, the CI panel's `expected_verdict: pass`
  rows, and the recognition protocol's negative control simultaneously. It is one authoring job and
  it unblocks five instruments. Add to the panel a rule that no instrument may be cited as
  discriminating until it has separated the constructed known-good from a constructed known-bad.
- **How to check I'm right**: `python3 -c "import json;print(json.load(open('tests/data/diversity_panel/panel.json'))['atg_pairs'])"`,
  every `fail` is a copy or a noun swap; every `pass` is a re-theme. Then read brief section 20's
  first sentence and note that no artifact in the repo is labelled known-good.

---

## C3-9: Q-1's arithmetic holds and is slightly worse in practice; the implied production requirement is 130-334 new skeletons and the only scaling mechanism is a refuted lever

- **Severity**: high
- **Category**: catalog arithmetic
- **Locus**: `skeletons/`; `scripts/analyze_sibling_exposure.py` sections `pools`, `siblings`, `sizing`
- **Problem**: Verified against the live catalog, not the brief's stale figures.

  **Catalog today**: 84 skeleton graphs (plus 47 theme-contract and 2 narrative sidecars), 22 cells,
  **18 populated, 4 empty** (`3-5/long`, `5-8/long`, `13-16/short`, `16+/short`), **13 of 18 thin
  (<5)**, min 3, median 4.0, max 5. The 08-22 brief still says "61 graphs and 11,458 nodes", stale
  by a factor of 1.4 on graphs.

  **Q-1 verified.** The claim: "a child exhausts a cell by roughly the fourth request at 3-4
  skeletons per cell." Simulated through the *real* `select_skeleton_for_cell` with real weighting,
  4000 trials, `10-13/short` (pool 5, the best-stocked cell): P(repeat by request 3) = 0.33,
  by request 4 = **0.62**, by request 5 = 0.88, = 1.00 by request 6. First-likely-repeat N50 = **4**.
  In `3-5/short` (pool 3): N50 = **3**, P(repeat by 3) = 0.61, certain by 4. So Q-1 is right, and it
  is right at the *current* catalog, which is 38% larger than the one it was computed on. Weighting
  never excludes (`1/(1+recent_count)`), so a repeat is possible from request 2 (P = 0.11-0.22).

  **Implied production requirement** (`--section sizing`, one skeleton serves each child once,
  cross-length and cross-style substitution forbidden by cell matching):

  | reading rate | shortfall summed over all six bands |
  | --- | --- |
  | 0.5 books/month | **32** skeletons |
  | 1 book/month | **130** |
  | 2 books/month | **334** |
  | 4 books/month | **742** |

  At 1 book/month, modest for a child who likes the app, the catalog must roughly **triple**, from
  84 to 214, just for one child's band lifetime, before any variety-above-non-repetition is bought.

  **Does the programme have a plan that meets it?** The catalog-growth mechanism is the flywheel
  (`flywheel/`, ADR-020, `scripts/mutate_skeleton.py`, `scripts/flywheel_cycle.py`) and it is
  entirely offline. Its unit of production is a **mutant of an existing parent**. That is S8, which
  the 08-22 brief lists under "refuted as variety levers": "shape-preserving operators are
  perceptual no-ops; the only floor-clearing mutant grafted a second skeleton". The mutation pilot's
  own table: M1 gives `structural_distance` **0.0000** against the parent, retains **95/95** parent
  nodes and **95/95** parent FILL beats byte-identical; M4 gives 0.0038; only the M3-graft chain X
  reaches 0.0726, and it does so by importing a subtree from a *different existing skeleton*, so it
  is recombination of the same 84, not new material. So the mechanism that scales the catalog
  produces exactly the artifact class the programme has refuted as a variety lever, and it is
  bounded by `TAU_CELL` = 0.05, a duplication floor two orders below the hand-authored median
  (0.380).

  The complementary path, S-1's finding that a tool-assisted Anthropic tier authors strict-passing
  shells at zero marginal provider cost (3/3 at 4-6 checker runs), is real and is the best news in
  the programme, but it prices *structure*, and structure is the layer the defect definition says
  is reusable. Nothing in S-1 addresses whether 130 new skeletons would be 130 new *adventures* or
  130 more cipher-vault-founder stories, which C3-2's control result says is the live risk.
- **Why it matters for the goal**: "cost-effective books for children" turns on this number. If the
  requirement is 130-334 new skeletons and the scaling mechanism produces perceptual no-ops, then
  catalog depth is not the lever, and the brief's own 16f conclusion applies: "buying more skeletons
  buys nothing." The programme should know which of the two it is before spending either way.
- **Recommendation**: (1) Update the brief's scale facts to the live catalog (84 graphs, 18
  populated cells, 4 empty), a stale capital fact in a capital argument is dangerous. (2) Fill the
  four empty cells first; a request into `3-5/long` or `13-16/short` has zero candidates today. (3)
  Before committing to any catalog-growth budget, run the audit C3-2 recommends: measure decision-
  chain repetition across the *existing* 18 cells. If within-cell skeletons already read as one
  adventure, tripling the catalog triples the cost and not the variety. (4) State explicitly in
  ADR-020 that mutation is a *coverage* mechanism (filling empty cells, cheap shells) and not a
  variety mechanism, since S8 refuted the latter and the flywheel's documentation does not say so.
- **How to check I'm right**: `uv run python scripts/analyze_sibling_exposure.py --section pools`
  (22 cells, 18 populated, 4 empty, 13 thin, median 4.0); `--section siblings` (N50 = 3-5);
  `--section sizing` (shortfall column). Mutation figures: `sed -n '55,75p' docs/planning/evidence/mutation-per-request-pilot/README.md`.

---

## C3-10: The premise sits in the decisional stratum, and per-book generation demonstrably cannot supply it

- **Severity**: high
- **Category**: stratified plan
- **Locus**: `architecture-respecification-2026-08-10.md` sections 2.1 item 1, 2.2;
  `evidence/q3c-premise-mode/README.md`; 08-10 brief sections 24, 27
- **Problem**: The respecification's amendment 1 moves the premise out of the shared stratum: "A
  structural stratum that is genuinely wordless holds topology, fact *names*, typed slots and
  categories, and no prose at all, the premise included." The mechanism it names for filling the
  decisional stratum is section 2.2: "generate each book's decisional stratum from the structural
  stratum alone, and never from a sibling book", validated by a 127-fold reduction (126.7 → 1.0
  shared grams) from withholding the reference.

  The same section then records the counter-evidence in its own text: *"The author who never saw the
  reference independently chose a clock tower, against a reference set in a clocktower. Withholding
  closes the wording channel completely and the premise channel not at all."* Q-3c replicates:
  8 of 10 isolated generations across three tiers put a beacon at the centre; two instances invented
  *The Lantern Under Marrow Hill* and *The Lantern Beneath Marrow Hill*. Brief section 27 makes it
  distribution-level: same brief, six independent labs, **156.35 shared 4-grams per 1000, ~120x the
  cross-vendor floor**.

  So the stratified plan requires the premise to vary per book, and the only mechanism it specifies
  for generating per-book content provably does not vary it. The respecification acknowledges the
  gap ("section 2.1's point 1 needs a mechanism of its own... a repulsion term over premises is the
  obvious candidate") and no such mechanism exists in the codebase: `grep` for a premise repulsion
  term in `src/` returns nothing; `similarity_context` computes a theme *containment* score against
  a closed vocabulary at threshold 0.34, whose measured distribution over 976 pairs is "median
  0.0000, p90 0.3333", i.e. it fires on the tail, not on archetype convergence.

  The fallback the brief names is curated enumerated allocation: "premise allocation from a curated
  enumerated space stops being one design's feature and becomes a precondition for all of them". But
  that is a human-authored vocabulary, and section 22 prices it: the pilot contract's five cipher
  forms force a repeat by book 6; the youngest band's contract enumerates *one* obstacle kind and
  *one* help mode, forcing a repeat at **book 2**. "The fix is not architectural: somebody has to
  write more kinds."
- **Why it matters for the goal**: F5 is presented as an architecture that buys variety. Its largest
  named channel (premise) is not addressed by the architecture at all, is refractory to every
  generation-side intervention measured, and reduces to a hand-authoring workload the programme has
  not scoped. Every cost estimate for the stratified plan that omits premise-vocabulary authoring is
  an underestimate of unknown size.
- **Recommendation**: Make premise allocation a named, scoped deliverable with a size: how many
  distinct premises per (band, cell) are needed to reach N books without a forced archetype repeat,
  and who writes them. Then either build the repulsion term (score a candidate premise against the
  child's prior premises using the closed vocabulary already in `diversity/normalize.py`, and
  reject rather than merely down-weight) or accept enumerated allocation and price the writing.
  Until one of those exists, the stratified plan's variety claim should carry the premise caveat
  inline in the 08-22 brief's F5, which currently states it without qualification.
- **How to check I'm right**: read `architecture-respecification-2026-08-10.md` section 2.2's last
  paragraph against `evidence/q3c-premise-mode/README.md`; then
  `grep -rn "premise" src/cyo_adventure/diversity/`, nothing repels on premise.

---

## C3-11: Solution transfer, the only measure that reproduced reader orderings, is inapplicable to 98% of the catalog

- **Severity**: medium
- **Category**: instrument validity
- **Locus**: `scripts/check_solution_transfer.py` (usage line requires `<contract.json>` plus two
  `<selection.json>`); `skeletons/*/*.narrative.json`
- **Problem**: The 08-22 brief lists solution transfer first under "Works": "the only computed
  measure that reproduced reader orderings, and only its taxonomy-free tier". Its input is a
  *narrative contract* with a `world_recipe` naming device categories, plus per-book binding
  selections. Counted: **2** narrative contracts exist (`the-clocktower-cipher`, `the-lost-mitten`)
  against **84** skeleton graphs, 2.4%. Of the 47 `.contract.json` theme contracts, **0** carry a
  `world_recipe`; they are slot-binding contracts (`legacy_lexicon`, `default_binding`, `slots`), a
  different artifact. And one of the two narrative-contract skeletons
  (`the-clocktower-cipher`) is `production_eligible: false`.

  16f already priced the gap: "a contract costs roughly 1.7KB per node of hand-authored
  specification, so the catalog's 11,458 nodes represent about 19.5MB of writing that does not
  exist." At the current 84-graph catalog that figure is larger still.

  Two further limits the script itself declares: the chain-category naming is "the single hand-set
  input here, and it is where this measure could be gerrymandered"; and tiers 2-3 "collapsed" on an
  unseen contract, classifying 2 of 6 chain props.
- **Why it matters for the goal**: F6 nominates solution transfer as a surviving instrument and the
  respecification makes it the scoring function for three re-specified architectures (R2-1b step 3,
  R1-1 step 3, R2-4's novelty term). All three are therefore blocked on an artifact class that
  exists for 2 skeletons. This is not visible in the 08-22 brief, which lists solution transfer
  under "Works" without the coverage caveat.
- **Recommendation**: State the coverage in the brief ("computable on 2 of 84 skeletons"). Then
  decide: either narrative contracts become a promotion requirement (and the 19.5MB is scoped as
  work), or solution transfer is downgraded from a programme instrument to an experiment-only
  measure and the three re-specified architectures need a different scoring function.
- **How to check I'm right**: `ls skeletons/*/*.narrative.json` returns 2 files;
  `uv run python -c "import json,glob; print(sum('world_recipe' in json.load(open(p)) for p in glob.glob('skeletons/*/*.contract.json')))"` returns 0.

---

## C3-12: `TAU_CELL` is a duplicate detector sold as a diversity floor, and 20% of `structural_distance` is a self-declared string

- **Severity**: medium
- **Category**: instrument validity
- **Locus**: `src/cyo_adventure/diversity/structure.py:47-50, 397-431`; `docs/planning/ws5_floor_baseline.json`
- **Problem**: Two separate issues in the third surviving instrument.

  1. **The floor is far below the operating distribution.** `ws5_floor_baseline.json` records the
     hand-authored same-cell distribution over 145 pairs: min 0.000469, **p05 0.154657**, p25
     0.298321, median 0.379906, max 0.605791. `TAU_CELL` = **0.05** sits below the 5th percentile.
     It rejects clones and certifies everything else. The 08-22 brief describes it as
     "`structural_distance` against every in-cell tree must clear `TAU_CELL` (0.05, calibrated in
     `ws5_floor_baseline.json`)" under the heading **Anti-clone**, which is accurate, but 4.4 then
     lists "structural distance with calibrated floors" among instruments that *work* for diversity.
     A clone detector is not a diversity instrument. The `TAU_STRUCT` value that *would* be a
     diversity floor (0.298321, the p25) is marked "DOCUMENTATION ONLY... No longer gates mutants",
     and `incell.py` records why: it "would fail 17 of 67 in-cell pairs across 12 of 18 populated
     cells". The catalog cannot meet its own diversity floor, so the floor was retired to a
     duplication floor. That is a real finding and it is not stated anywhere in the 08-22 brief.
  2. **A fifth of the distance is a metadata label.** `_TOPOLOGY_WEIGHT = 0.2`, and
     `topology_term = 0.0 if features_a.topology == features_b.topology else 1.0`, where `topology`
     is `model.metadata.topology.value`, a self-declared string, not computed from the graph. Two
     graphs of identical shape that declare different topologies score 0.2, which is **4x
     `TAU_CELL`**. So the anti-clone gate is passable by editing one metadata field. The 08-22 brief
     notes this obliquely ("with its self-declared topology component split out") but nothing in
     `structural_distance` splits it out; there is no API to request the topology-free distance, and
     `check_incell_clones.py` does not use one.
  3. **The in-cell allowlist has a live entry.** `incell.py::ALLOWLIST` holds
     `the-harrowstone-keep` / `the-sunken-temple`: "every `structure_features` field is identical
     (550 nodes, 152 endings, 801 choices, max_depth 58, same ending-kind and valence histograms,
     same topology) except `n_effects`, 49 vs 48." Two production skeletons in one cell are
     structural twins, permanently, because ADR-011's series-retirement addendum forbids retiring
     either. A child in `13-16/long/gamebook` (pool 5) has a 1-in-10 chance per pair draw of meeting
     that pair.
- **Why it matters for the goal**: the catalog gate that is supposed to keep two books in a cell
  from being the same tree is calibrated below the distribution it polices, is defeatable by a
  metadata edit, and already carries a permanent exemption for a structural-twin pair the child can
  actually be served.
- **Recommendation**: Expose `structural_distance(..., include_topology=False)` and use it in
  `check_incell_clones.py`, since the declared label is not evidence. State plainly in the brief
  that `TAU_STRUCT` (the real diversity floor) fails 17 of 67 in-cell pairs and has been demoted;
  that fact is more informative about the catalog than the passing `TAU_CELL` gate is. Schedule the
  `the-harrowstone-keep` restructure the allowlist entry already specifies.
- **How to check I'm right**: `cat docs/planning/ws5_floor_baseline.json` (p05 0.1547 against
  `tau_cell` 0.05); `sed -n '397,431p' src/cyo_adventure/diversity/structure.py` (topology term);
  `sed -n '59,80p' src/cyo_adventure/diversity/incell.py` (allowlist).

---

## C3-13: Stratified generation is the seventh lever in the same series unless it varies the act, and on present evidence it does not

- **Severity**: medium
- **Category**: defect definition
- **Locus**: 08-10 brief section 5.3 table; 08-22 brief section 4.3; S-0 verdicts
- **Problem**: Question 6 asks what distinguishes stratified generation from the six refuted levers.
  The programme's answer is the 5.3 table: S2-S9 each varied a layer *around* scene identity and
  action semantics, which were "constant by construction"; the stratified plan is different in kind
  because it finally varies `choice_semantics`.

  That is the right criterion, and applied honestly it does **not** clear the stratified plan.
  Extend the 5.3 table with the d7b arm, using its own artifacts:

  | | What it varied | Scene identity | Act offered at each choice |
  | --- | --- | --- | --- |
  | S2-S9 | world, cast, obligations, props, wording, model, edges | fixed | fixed |
  | **D-7b stratified** | premise wording, `choice_semantics` strings, beats, devices | **fixed** (node ids `n_note`, `n_setjam`, `n_backpanel` shared; facts name outcomes) | **fixed in effect**, both raters report the identical three-way opening act |

  The stratified arm varied the *strings*, and 16l says so in its own limitation: "Eleven of
  thirty-five choices share their opening verb across the two books... That is the shared structure
  surfacing at the label layer... Whether a child reads shared opening verbs as repetition is a
  reader question and no measure we have can answer it." Two readers then answered it, at scene 2,
  distinctness 1/5.

  **What would distinguish it in kind**: an arm in which the *act* at each aligned fork differs, and
  where that difference is declared rather than hoped for. The respecification's M-3 re-spec points
  at exactly this ("Add an explicit field to the narrative contract's decisional stratum: for each
  fork option, the **operation** it asks... Authored at contract time... Stop trying to classify.
  **Declare.**"). That field does not exist in any schema in `src/cyo_adventure/storybook/` and M-3
  is recorded as blocked on it.

  **What would make me predict it fails too**: it already has the signature of the previous six.
  (i) It solved its own metric (13.6 → 2.3) and left recognition unmoved, the exact pattern of S5
  ("divergence 0.41 to 0.978; recognition unmoved") and S6 ("shared 4-grams 20.4 to 1.2; recognition
  unmoved"). (ii) Its shared artifact still carries the layer 5.2 identified as the fingerprint.
  (iii) Its untouched channels (premise, idiom floor, category vocabulary) are the three the brief's
  own section 25 lists as "properties every candidate must supply". Three for three.
- **Why it matters for the goal**: the programme has spent ten designs learning that solving a
  proxy does not move the reader. F5 is currently being promoted to framework principle on a proxy
  result, with the only reader-side check declared inadmissible on the strength of a different leg
  of the same run. That is the seventh iteration of the pattern the brief was written to stop.
- **Recommendation**: Do not build on F5 until the declared-operation field (M-3 step 1) exists and
  an arm varies the act at aligned forks. Its falsifier is already written and cheap: "Authors
  cannot agree on the declared operation for a fork at acceptable reliability", testable for one
  annotation round over the two existing narrative contracts, and D-3c already puts the contested
  boundary at kappa 0.719 so it has a live chance of firing. Run the falsifier before the schema
  change, as the respecification itself instructs.
- **How to check I'm right**: put the 5.3 table beside the d7b verdicts' `strongest_signal` fields
  and the 16l "eleven of thirty-five share their opening verb" paragraph.

---

## C3-14: The differentiation directive is the only anti-convergence lever in the request path and its effect has never been measured

- **Severity**: medium
- **Category**: production wiring
- **Locus**: `generation/prompts.py:480` (`build_differentiation_directive`),
  `story_requests/authoring_plan.py:435`, `generation/worker.py:853`; `UW-C315`, `AL-498`
- **Problem**: Of everything in C3-6's table, `build_differentiation_directive` is the only
  mechanism that actively tries to push a book away from its siblings at request time. Its measured
  effect is unknown. `AL-498` measured the *undirected* floor: two fills of `the-tin-whistle-map`
  from deliberately distant briefs at **96.3 shared 4-grams per 1000, 24x budget**, 1,350 shared
  grams, 274 shared menu frames, both books passing the deterministic gate. The lesson's own caveat:
  "`compare_vendors.py` passes no `differentiation_directive`, so this is the RAW undirected floor,
  which is precisely the quantity that directive exists to counter. At 24x budget the directive
  would have to carry an implausible amount of the load."

  `UW-C315`'s 2026-08-20 progress note records that the harness now accepts `--differentiation` and
  a best-case directed spec is committed at
  `runs/deepseek-v4-pro-2026-08-20/shared-skeleton-pair-directed/differentiation.json`, but "the
  delta run itself... could NOT execute from the 2026-08-20 remote session: the environment's
  network policy answers 403 to CONNECT for `openrouter.ai`". Row status: **unscheduled**, phase 4b.

  Independent evidence predicts the directive is near-null. M-4's controlled result (respecification
  2.2, brief 4.3): "instructing independence between authors does nothing; withholding shared
  material works completely", 126.7 shared grams with the reference shown *plus an itemised
  instruction to diverge*, against 1.0 with it withheld. The differentiation directive is an
  instruction to diverge. It is the intervention M-4 refuted, shipped in the request path.
- **Why it matters for the goal**: the product currently ships one lever against sibling convergence,
  it is the lever a controlled experiment in this same programme found to be "close to useless", and
  one blocked API call separates the programme from knowing.
- **Recommendation**: Run the committed delta spec on any network with OpenRouter reachable. It is
  a single `compare_vendors.py` invocation and it decides whether the shipped lever is real. If the
  delta is small, the honest architectural consequence, named in `AL-498`, is a cap on
  cross-family skeleton reuse or a per-family structural mutation, not a bigger prompt block.
- **How to check I'm right**: `grep -n "build_differentiation_directive" src/cyo_adventure/generation/worker.py`;
  read `UW-C315`'s "**Still open:** the delta measurement" clause; compare against respecification
  section 2.2's 126.7-vs-1.0 table.

---

## C3-15: The brief's scale and status facts have drifted from the repository

- **Severity**: low
- **Category**: catalog arithmetic
- **Locus**: 2026-08-22 brief section 1; `skeletons/`; `evidence/d7c-binding-notes/`
- **Problem**: Three checkable facts in the 08-22 brief no longer match the repo.
  - "the catalog spans **61 graphs and 11,458 nodes**", the catalog holds **84** skeleton graphs
    across 22 cells (18 populated). The 61 figure dates from 16f (2026-08-10).
  - Section 3.4 says `check_sibling_fills.py` measures "shared 4-grams against same-skeleton
    siblings (budget 4.0 per 1000)", the shipped script measures the label-inclusive scope the
    brief's own standard excludes (C3-7).
  - Section 4.3 cites D-7b's 2.3 as the stratified result without noting that the D-7c arm which
    would explain it ("the highest-value single experiment we can currently run", 2026-08-11) has
    never produced fills, on any branch, and that its first attempt was lost with a deleted working
    branch (`AL-510`).
- **Why it matters for the goal**: the brief is the artifact external reviewers and future
  instances reason from; three of its checkable numbers are stale in the direction that makes the
  programme look better resourced and further along than it is.
- **Recommendation**: Add a "facts as of" line to section 1 with a command that regenerates the
  catalog counts (`find skeletons -name '*.json' -not -name '*.contract.json' -not -name '*.lineage.json' -not -name '*.narrative.json' | wc -l`),
  and mark D-7c as pending in section 4.3 the way `AL-510`'s own recommendation prescribes.
- **How to check I'm right**: run the count above (84); `ls docs/planning/evidence/d7c-binding-notes/`
  (no `R-*`, no `results.md`); `git ls-tree -r --name-only origin/main | grep d7c` confirms the same
  on main.

---

## Summary of what I would change first

1. Re-read the six S-0 verdicts as an F5 result, not as instrument calibration (C3-1, C3-2).
2. Construct one known-good artifact; it unblocks five instruments at once (C3-8).
3. Narrow the diversity history to `profile_id` and wire `check_sibling_fills.py` cross-family
   (C3-6), both are small and both are shipping defects, not research questions.
4. Fix the shipped 4-gram scope so the production instrument and the published headline agree (C3-7).
5. Run the D-7c arm and the differentiation-directive delta; each is one command and each settles a
   claim the brief currently asserts (C3-5, C3-14).
