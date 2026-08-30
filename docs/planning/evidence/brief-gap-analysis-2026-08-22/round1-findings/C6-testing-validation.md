# C6: Testing and validation apparatus, component audit

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/home/user/cyo-adventure/.worktrees/brief-evidence/`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.

Scope: the software test suite that keeps the generation framework correct, and the
register/lessons/linkage machinery that keeps its claims honest.

Evidence base for this audit, all re-run here rather than read off documentation:

- **Full unit suite, instrumented.** `tests/unit`, 8,561 passed / 9 skipped in 867s
  (serial, `-p no:randomly`), with `ValidationFinding.__init__` wrapped to record every
  rule id constructed anywhere during the run. This is the definitive answer to "which
  rules can never fire".
- **Reproduction attempt on two experiments.** D-7b (`evidence/d7b-bare-names/`) and
  S-1 tool-assisted (`evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/`),
  both re-run from committed artifacts.
- **Coverage.** Aggregate figures are quoted from `docs/planning/test-coverage-audit-2026-07-09.md`
  (backend 95.69% line / 90.61% branch, branch mode, 111 files). I started a fresh
  per-package run restricted to `generation/`, `validator/`, `moderation/`,
  `story_requests/`, `diversity/`, `publishing/`, `mutation/`, `measurement/`, `flywheel/`
  but did not let it finish inside the time budget, so C6-13 names behaviours rather than
  percentages, which is the more useful output anyway.
- **Adversarial tests against the honesty machinery.** Constructed the specific
  violations `check_lessons_log.py` and `check_work_linkage.py` claim to prevent, with a
  positive control to prove the checkers were live.

**Retraction.** An earlier pass of this audit concluded that the 2026-08-22 brief cited
non-existent artifacts (`S-0`..`S-5`, `AL-510`..`AL-514`, `UW-C317`..`UW-C320`,
`skeleton-sourcing-test-plan-2026-08-21.md`, `evidence/skeleton-author-vendors/`,
`recognition-protocol-pilot/results.md`). That was an artifact of the branch I was given,
which carried the brief without its evidence. **All of them exist** on the full source
branch (`/home/user/cyo-adventure/.worktrees/brief-evidence/`) and every finding below is
stated against that tree. Nothing here rests on absence of an artifact.

**The headline.** This is, on the software side, one of the better-tested codebases of
its kind: 54 of 55 validator rules provably fire, the known-bad corpus pins rule
attribution, the publish state machine is exhaustively tested, and there is an explicit
"rules must fire at their real entry point" test written after three dead rules shipped
green. The failures are not in the unit suite. They are at three seams: (1) the delivery
measurements that answer the programme's own largest measured defect are not on the path
that produces books; (2) the instrument that computes the diversity budget computes a
metric the register retracted; (3) the honesty machinery checks the *shape* of claims,
never their *substance*, and the one document holding every pre-registration is checked
by nothing at all.

---

## C6-1: The delivery floors that answer the hollow-pass defect are not on the production path, and not in CI

- **Severity**: critical
- **Category**: e2e
- **Locus**: `src/cyo_adventure/generation/worker.py:1366`; `scripts/check_fill_integrity.py:67`; `scripts/run_guard_battery.py:117`
- **Problem**: The brief's principle F2 says every gate is paired with a delivery
  measurement "so a hollow pass is visible", and section 3.4 lists
  `check_fill_integrity.py` (fill-rate floor 0.6) and `check_sibling_fills.py` (4-gram
  budget 4.0) as story automated checks. Neither runs on a generated book. The worker's
  post-fill sequence is `fill_skeleton` (with the stage-1 fidelity gate inside its repair
  loop) → `run_gate(final_storybook, "standard", context="fill_result")` →
  `check_sentinel_integrity_at_rest` → persist → `run_moderation_pipeline`. Nothing
  computes delivered-over-commissioned words; `commissioned_words_by_node` exists in
  `generation/skeleton.py:378` and has exactly three importers, none of them in the
  request path. The only caller of `check_fill_integrity.py` anywhere is
  `scripts/run_guard_battery.py`, an offline authoring CLI. Grep of `.github/workflows/`
  for the fifteen `check_*` gate scripts: only `check_skeleton`, `check_theme_contract`
  (skeleton-promotion) and `check_incell_clones` (ci.yml `diversity` job) are CI-wired.
  `check_fill_integrity`, `check_sibling_fills`, `check_prose_craft`,
  `check_reading_level`, `check_graph_structure`, `check_fill_fidelity`,
  `check_branch_obligations`, `check_promise_discharge`, `check_solution_transfer`,
  `check_narrative_contract`, `check_outcome_spread` are wired nowhere.
- **Why it matters for the goal**: `AL-490`/`UW-C307` is the strongest quality result the
  programme has: three books delivered 38.9–52.9% of commissioned words and passed the
  deterministic gate cleanly. The countermeasure was built, calibrated against 48
  committed pairs, and given a blocking exit code, and then left off the path that
  produces books for children. A live run today reproduces the AL-490 defect exactly, and
  the human approver sees a gate-clean book with no signal that half of it is missing.
  The whole F2 claim ("gates are floors; delivery is measured beside them") is true of
  hand-run authoring and false of generation.
- **Recommendation**: Call `commissioned_words_by_node` in `worker.py` immediately after
  `regated = run_gate(...)` and record the story-level fill rate on the outcome report;
  block below 0.6 the way `check_fill_integrity` does, or at minimum downgrade to
  `needs_review` and surface the rate on the admin review surface. Do the same for
  sibling 4-grams once `UW-C315` lands. Add an integration test that drives a
  structurally-perfect, 40%-delivered fill through `run_generation_job` and asserts it
  does not reach `in_review` clean.
- **How to check I'm right**: `grep -n "commissioned_words_by_node\|fill_rate" src/cyo_adventure/generation/worker.py src/cyo_adventure/generation/orchestrator.py`
  returns nothing. `grep -rl "check_fill_integrity" .github/` returns nothing.
  `grep -rn "check_fill_integrity" --include=*.py src/ scripts/` returns only docstring
  references and `run_guard_battery.py:117`.

---

## C6-2: `check_sibling_fills.py` computes the metric the register retracted; the D-7b headline cannot be reproduced from committed tooling

- **Severity**: critical
- **Category**: reproducibility
- **Locus**: `scripts/check_sibling_fills.py:73` (`_leaf_text` → `" ".join(parts)`); `docs/planning/diversity-test-register.md` D-7b row; `docs/planning/authoring-lessons-log.md` AL-267
- **Problem**: I ran the committed instrument on the committed artifacts:

  ```sh
  uv run python scripts/check_sibling_fills.py \
      docs/planning/evidence/d7b-bare-names/filled_C.json \
      docs/planning/evidence/d7b-bare-names/filled_D.json
  → shared 4-grams across 2 fills: 10 (3.2 per 1000 mean leaf words; budget 4.0)
  ```

  **3.2**, which is precisely the figure the register retracted. The D-7b row reads:
  "**2.3 per 1000** ... (Restated 2026-08-11 from '3.2 per 1000 ... at the 3.3 floor', per
  the per-body-unit recount noted on `AL-267`; the earlier figure counted 4-grams
  straddling body boundaries and so put this arm at the floor rather than under it.)"
  `_leaf_text` still joins every body and label into one string, so the script still
  counts boundary-straddling grams. There is no `--per-body` flag (`--help` shows only
  `--max-shared-per-1000` and `--check`). The corrected method is implemented in no
  committed script. `AL-267`'s status is still `open`.
- **Why it matters for the goal**: D-7b is the single diversity design that survived ,
  it is the evidence for framework principle F5 (share the wordless structural stratum,
  generate the decisional layer per book), which is the architecture the programme is
  re-specifying around. A third party who re-runs the committed tool gets 3.2, sees it
  sitting at the 3.3 idiom floor rather than below it, and concludes the arm is
  indistinguishable from noise in the *unfavourable* direction. Worse, the constants have
  drifted apart from the instrument: the 4.0 budget and the 3.3 floor are now quoted in
  the corrected metric's units (AL-267 restated the floor from 3.5 to 3.3 for the same
  reason) while the gate computes the uncorrected one, so the gate is systematically
  ~40% conservative on this corpus and nobody can say by how much on another.
- **Recommendation**: Implement the per-body-unit counting in `check_sibling_fills.py`
  (grams must not cross a body or label boundary), re-derive the budget and the idiom
  floor under it, and add `tests/unit/test_check_sibling_fills.py`, there is none today
 , pinning both the D-7b pair at its published 2.3 and the D-6 `verbatim` arm at its
  published 17.2. Until then, annotate the script's `--help` with the fact that its
  output is not the register's published units.
- **How to check I'm right**: run the command above; read `scripts/check_sibling_fills.py`
  lines 60-96; `ls tests/unit/test_check_sibling_fills.py` (absent); `grep -n "AL-267" docs/planning/authoring-lessons-log.md`
  ends in `| open |`.

---

## C6-3: An experiment can substitute its primary endpoint mid-run and the register has no slot for the new margin

- **Severity**: high
- **Category**: register integrity
- **Locus**: `docs/planning/diversity-test-register.md:1275` (section F contract) and `:1292` (row S-1)
- **Problem**: Section F states the contract plainly: "The margins, floors, and ceilings
  below are the proposer's and are fixed as of this commit; amending one after its
  experiment has produced artifacts voids that experiment's pre-registration and must be
  recorded here as such." S-1's Falsifier column still carries the original: "**Primary
  endpoint only**: repair rounds to strict pass, pooled across cells, permutation test
  over leg assignment, 10,000 permutations, alpha 0.05. Falsifier: no leg pair separates
  at that level; then the model axis is dropped." That endpoint went degenerate (the row
  says so: "primary endpoint degenerate under censoring (p=1.0 reflects the cap, not
  equivalence)"). The tool-assisted condition was then added mid-run, "**Declared
  pre-run additions (2026-08-21, owner-directed)**", with endpoints stated as "strict
  pass/fail plus checker invocations to pass" and **no margin, no falsifier, no analysis
  plan, no alpha**. The row is now `DONE`, its "Final reading" declares the model axis
  separated "cleanly", and it feeds decision rules R3-R7 and the brief's product
  recommendation (fill with V4 Pro, author structure with a tool-assisted Anthropic
  tier). The separation is 3/3 versus 0/3 at n=3 per cell, judged by eye.

  Two further consequences the register does not surface. The **Method column is stale**:
  it still reads "5 legs × 4 cells × 4 replicates = 80 shells" while what ran was 7 legs ×
  2 cells × 3 replicates = 42 shells. A reader who reads Method + Falsifier, which is
  what those columns are for, reads an experiment that never happened; the revision
  exists only as prose buried in a ~4,000-character Status cell. And nothing marks which
  text in a row was written *before* the data and which *after*: pre-registration and
  result share one mutable row in one mutable file.
- **Why it matters for the goal**: F6 ("pre-register everything") is one of the eight
  framework principles, and the programme's credibility rests on it, this is a research
  effort whose entire claim to being more than anecdote is that it names falsifiers in
  advance. The machinery honours that for the endpoint that failed and silently drops it
  for the endpoint that decided. This is not bad faith; the row is unusually candid
  (it even records data contact: "Declared with full data contact stated: 4 completed
  shells' exploratory records were seen, no primary result existed"). It is a missing
  slot in the format.
- **Recommendation**: Split the Falsifier column into `Falsifier (registered)` and
  `Amendments`, where every amendment carries its own date, its own margin, and an
  explicit data-contact statement, the S-1 row already writes all three, it just writes
  them where a reader cannot find them. Make the Method column mandatory-to-update on
  amendment (the row's own contract already requires this). For S-1 specifically, state
  the decision rule the tool-assisted pass counts were judged against, retrospectively
  and labelled as such, so the reader can price it.
- **How to check I'm right**: read `docs/planning/diversity-test-register.md:1275` then
  the S-1 row's Method and Falsifier cells at `:1292`, and compare against
  `docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/records/`
  (42 records, cells A and D only, 7 legs).

---

## C6-4: `applied` is an unchecked escape hatch: I marked a live lesson applied with a fabricated ref and both checkers passed

- **Severity**: high
- **Category**: register integrity
- **Locus**: `scripts/check_lessons_log.py:208`; `scripts/check_work_linkage.py:884` (`_is_open_lesson_row`), `:2207` (`_check_lessons_linkage`)
- **Problem**: The contract, per `CLAUDE.md` and the checker's own docstring, is that
  `applied`/`rejected`/`superseded` "are claims about something having happened and
  require a `Ref` that proves it", and that any lesson *not* in those three statuses must
  be cited by a `UW-C*` row so it has a phase home. Both halves are gameable in one edit.
  `check_lessons_log.py:208` tests `not row["Ref"]`, non-emptiness, nothing more. It
  never resolves the ref to a file, a commit, a PR, or a register row. And
  `_is_open_lesson_row` treats any of the three closed statuses as exempt from the
  linkage requirement, so flipping the status simultaneously satisfies the log checker
  and deletes the row from the scheduling obligation.

  Demonstrated on the live tree. I took `AL-514` (open; the PL-18 topology-trap lesson
  that cost three legs grid points in S-1) and rewrote its last two cells to
  `| applied | fixed it, see the thing |`:

  ```sh
  uv run python scripts/check_lessons_log.py --log <copy>
  → ok: log.md is well formed
       513 lesson(s): accepted=3, applied=241, open=267, rejected=1, superseded=1
  uv run python scripts/check_work_linkage.py --lessons-log <copy>
  → ok: unscheduled-work-register.md satisfies the work-linkage contract
  ```

  Positive control, to prove the linkage checker was live: replacing the register's one
  citation of `AL-511` with a dangling id produced
  `FAIL ... lesson 'AL-511' status is not applied/rejected/superseded and is not cited by
  any row in cluster C`. The checker works exactly as designed; the design has the hole.

  Scale of exposure: 240 of 513 lessons are `applied`. Classifying their refs, 144 name a
  path that resolves, 34 look like a commit/SHA, 5 name a PR or issue, and **57 are prose
  that resolves to nothing checkable**: e.g. `AL-025`'s ref is "this review; leads chased
  manually and closed".
- **Why it matters for the goal**: The lessons log is the mechanism that turns a lesson
  learned once into a change in the tooling instead of folklore. Its value is entirely in
  the `applied` claims being true. A well-meaning author under time pressure has a
  one-cell edit available that both discharges the claim and removes the item from the
  work register's schedule, with two green checkers confirming it. Nobody has to intend
  anything for this to happen; it is the path of least resistance at the end of a long
  authoring run.
- **Recommendation**: Make `Ref` resolvable by construction and check it. Accept a
  repo-relative path that exists, a `#NNN` that `gh api` resolves, a commit SHA that
  `git cat-file -e` resolves, or an explicit `prose:` prefix that the checker counts and
  reports as an unverified claim (so the number is visible rather than hidden). Fail on
  anything else. Backfill the 57 prose refs, or re-open the lessons they close. Second,
  make the status transition auditable: an `applied` row should also require the `UW-C*`
  row that scheduled it to be marked done, so the two registers must agree.
- **How to check I'm right**: reproduce the edit above on a copy of
  `docs/planning/authoring-lessons-log.md` and run both checkers; read
  `scripts/check_lessons_log.py:200-215` and `scripts/check_work_linkage.py:884-905`.

---

## C6-5: The diversity test register, holding every pre-registration and falsifier, is checked by nothing

- **Severity**: high
- **Category**: register integrity
- **Locus**: `.github/workflows/planning-linkage.yml:88-119`; `.pre-commit-config.yaml:345,353`; `docs/planning/diversity-test-register.md`
- **Problem**: The project has built real machinery for document integrity ,
  `check_work_linkage.py` is 2,909 lines and enforces phase vocabularies, cluster
  membership, roadmap/manifest/project-plan status agreement, debt linkage, capability
  linkage, and an SQ namespace map. None of it touches the diversity test register.
  `planning-linkage.yml` runs exactly three checks: `check_work_linkage.py`,
  `check_lessons_log.py`, `check_known_vulnerabilities.py`. Pre-commit adds nothing.
  `grep -rn "diversity-test-register" .github/ .pre-commit-config.yaml scripts/*.py`
  returns one hit, a docstring in `scripts/compare_skeleton_authors.py`.

  So the document that carries every falsifier has no check that a row *has* a falsifier,
  no status vocabulary enforcement (`queued|running|done|blocked|retired`, defined in the
  preamble and applied by hand), no id-uniqueness check, no check that a `done` row is
  reflected in the research brief, a rule the register's own "How to read this" section
  states as binding ("A result recorded here but absent there is half-delivered"). The
  register is 1,287 lines maintained entirely by reviewer diligence over squash-merged
  PRs.
- **Why it matters for the goal**: This is the document external reviewers would read to
  decide whether the programme's claims are honest. It is also the one with no automated
  floor under it, while three less consequential documents have one. The asymmetry is
  backwards: the register carries claims, the work register carries scheduling.
- **Recommendation**: Write `scripts/check_diversity_register.py` on the existing pattern
  (they share `_split_row`, `_is_separator`, `_find_id_header`), enforcing: unique ids
  matching the section's namespace; status in the declared vocabulary; a non-empty
  Falsifier cell or an explicit `NO FALSIFIER (demonstration)` marker, which the preamble
  already contemplates; and every `done` row's id appearing in the current research brief.
  Wire it into `planning-linkage.yml` beside the other two. This is a day's work against
  a 2,909-line precedent.
- **How to check I'm right**: `grep -rn "diversity-test-register" .github/ .pre-commit-config.yaml`;
  read `.github/workflows/planning-linkage.yml` steps 88-119.

---

## C6-6: No run records the code that produced it, and the S-1 prompt is a live function of the validator

- **Severity**: high
- **Category**: reproducibility
- **Locus**: `docs/planning/evidence/skeleton-author-vendors/runs/e1-2026-08-21/run.json`; `docs/planning/evidence/skeleton-author-vendors/vendors.json`; `scripts/compare_skeleton_authors.py:228` (`_author_prompt`)
- **Problem**: I attempted to establish reproducibility for S-1 concretely. The
  deterministic half **reproduces exactly**: re-running
  `check_skeleton.py --strict --allow-mvp` over all 42 committed tool-assisted shells
  gives 27 passes, matching the register's 12 (cell A) + 15 (cell D) to the shell. That
  is a genuinely good result and better than most of this literature.

  What is not recorded, per run or per attempt:

  - **No code version.** `run.json` carries `started_at`, `mock`, `vendors`, `cells`,
    `replicates`, `max_repair_rounds`, `max_tokens`, and two absolute file paths. No git
    SHA, no harness version, no validator version.
  - **No sampling parameters.** No temperature, no top-p, no seed, anywhere in the
    harness or the records. Every attempt is unreproducible even against the same weights.
  - **No model snapshot.** `vendors.json` pins slug plus provider route
    (`deepseek/deepseek-v4-pro` + `azure/us`), which is better than most, but an
    OpenRouter slug is a mutable pointer; there is no dated snapshot id, so "v4-pro" in
    three months is not the leg that was measured.
  - **No prompt, and the prompt is not stable.** `_author_prompt` composes the user
    message from the generated drafting brief plus the frozen premise. That brief comes
    from `generate_drafting_brief.py`, which the brief document proudly notes is "read
    live from the enforced rule sources (`validator/band_profile.py`,
    `validator/policy.py`, `scripts/check_skeleton.py`), never hand-copied". That
    property is excellent for authoring and fatal for reproduction: **both the prompt and
    the pass bar are functions of current validator code, and neither is snapshotted.**
    `AL-514` proposes changing the PL-18 message and `UW-C306` the brief-side topology
    menu, exactly the two things three legs lost grid points to. Land either and the 42
    shells were asked a different question against a different bar, the recomputed pass
    counts move, and nothing anywhere goes red.
  - **No intermediate outputs.** Only the final shell per grid point is kept; the
    per-round raw completions are gone, so a parse-failure or churn claim cannot be
    re-examined.
- **Why it matters for the goal**: S-1 is the result that changed the product's model
  policy (F4: select models per stage). A conclusion that cannot be re-derived after a
  validator change is a conclusion with an expiry date nobody has written down. The
  programme has already been bitten by exactly this class of drift twice (`AL-149`: hand
  written briefs drifted from the code).
- **Recommendation**: Have the harness write, into every `run.json`: the repo git SHA
  (dirty flag included), the resolved provider model id from the response envelope, the
  sampling parameters actually sent, and a hash of each rendered brief, and commit the
  rendered briefs themselves, one per cell, as run artifacts. That last item is the
  cheapest and highest-value: it converts "reproducible if the validator hasn't moved"
  into "reproducible, full stop". Add a re-verification script that recomputes the pass
  counts from committed shells and fails if they differ from the recorded ones, run in
  the same CI job as the skeleton-promotion prover.
- **How to check I'm right**: `cat docs/planning/evidence/skeleton-author-vendors/runs/e1-2026-08-21/run.json`;
  `grep -n "temperature\|seed\|git\|sha" scripts/compare_skeleton_authors.py` (no hits for
  the first three); read `scripts/compare_skeleton_authors.py:228` and follow
  `brief_markdown` back to `generate_drafting_brief.py`.

---

## C6-7: The decision-bearing S-1 condition and the recognition verdicts are self-reported, with the harness's own instrumentation empty

- **Severity**: high
- **Category**: reproducibility
- **Locus**: `docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/tools-meta.json`; the same run's `records/*.record.json`; `docs/planning/evidence/recognition-protocol-pilot/verdict_*.json`
- **Problem**: The tool-assisted run is the one the decision rests on, and it is the
  least instrumented run in the directory. It has **no `run.json` at all**: no date, no
  cap, no conditions, no model identifiers. For the subagent legs the harness record is
  hollow: `latency_s: 0.0`, `input_tokens: null`, `output_tokens: null`,
  `finish_reasons: []`, `attempts: 1`, `repair_rounds: 0`. The actual endpoint, checker
  invocations to pass, lives in a hand-maintained `tools-meta.json` whose value field is
  literally named `reported`, i.e. a session operator's assertion, not a measurement. The
  legs are tier *labels* run as in-session subagents; the register is honest about this
  ("tier-labeled, not backend-pinned: tier-level conclusions only"), but that means the
  brief's per-leg table in section 4.2 is a table of self-reports against unpinned tiers.

  The recognition pilot has the same shape one level worse. `verdict_*.json` carries
  `per_scene`, `first_yes_position`, `same_adventure`, `distinctness_1_to_5`,
  `strongest_signal`, and **no rater id, no model id, no timestamp, no prompt hash, and
  no identifier for the pair being judged**. Which pair a verdict is about is encoded
  only in its filename; which model produced it is stated only in `results.md` prose
  ("session model id `claude-fable-5`"), with no version, temperature or seed.
  `protocol.py validate` checks internal consistency of the verdict (one entry per scene,
  no yes reverting to no, position agreeing with the array), which is a real and
  well-designed guard, but says nothing about provenance.
- **Why it matters for the goal**: S-0's failure is load-bearing in the negative
  direction: it blocks S-2 and S-4's perceptual confirmations and marks the mutation
  pilot's perceptual claims unconfirmed. That is a correct and admirable call, and it
  currently rests on six JSON files that cannot be attributed to anything. If someone
  later disputes the failure, or wants to re-run after the symmetric firing rule is
  adopted, there is no way to establish what was actually run.
- **Recommendation**: Make `protocol.py validate` require a provenance block (`rater_id`,
  `model_id`, `run_at`, `book_one`/`book_two` paths with content hashes, `prompt_sha256`)
  and refuse a verdict without one; the prompt hash is free because `protocol.py build`
  already renders it. For the subagent legs, either instrument the session (a wrapper that
  counts checker invocations from the tool-call log rather than from a self-report) or
  label the column `self-reported` in the register and the brief, so a reader prices it
  correctly.
- **How to check I'm right**: `ls docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/`
  (no `run.json`); `python3 -c "import json;print(json.load(open('.../records/A__r1__claude-fable-subagent.json.record.json')))"`;
  `python3 -c "import json;print(list(json.load(open('.../verdict_ctrl-clocktower-museum_r1.json'))))"`.

---

## C6-8: 54 of 55 validator rules provably fire; the one that cannot is SAFE-14, and it is the gate's entire safety layer

- **Severity**: high
- **Category**: rule negative-testing
- **Locus**: `src/cyo_adventure/validator/safety.py:41`; `src/cyo_adventure/validator/gate.py` (docstring, "Blocking semantics")
- **Problem**: I answered the "which rules can never fire" question empirically rather
  than by grep, because the project's own `tests/unit/test_rules_can_fire.py` documents
  why grep is the wrong tool: all three previously-dead rules were dead in the *wiring*,
  not the body, and "called directly, each one fires". So I wrapped
  `ValidationFinding.__init__` and ran the whole unit suite (8,561 tests). Result: of the
  55 rule ids referenced in `src/cyo_adventure/validator/`, **54 are constructed at least
  once**. The negative-testing posture is, for a codebase this size, excellent.

  The one that never fires is `SAFE-14`, and it never fires anywhere: `check_safety`
  returns `ValidationReport()` unconditionally with `_ = story`. So
  `GateResult.safety_flagged` is structurally always `False`, and the gate's safety layer
  contributes nothing. The gate docstring is honest about it ("Phase-2 stub, always
  empty"), but the brief's F2 lists "safety classification" among the things "checked by
  code before any model or human judges anything", and that is not what happens: safety
  is entirely `moderation/`, whose Stage 0 is described as a "deterministic classifier
  pre-filter" while actually being two external ML services (OpenAI Moderation +
  Perspective, `moderation/classifiers.py:1`), with a documented Perspective sunset of
  2026-12-31.

  Twelve rules fire from exactly one or two sites, so their thresholds have no
  boundary coverage: CG-5 (1), CH-3a (1), PL-28 (1), SR-2 (1), SR-7 (1), and CH-5, CH-7,
  PL-21, PL-22, SR-1, SR-4, SR-6 (2 each). PL-28 is the MVP/Test-seed firewall, the rule
  standing between a prototyping shell and a child-facing book, and it is constructed
  once in 8,561 tests.
- **Why it matters for the goal**: A children's product whose validator's safety rule is
  a no-op is fine *if everyone knows*, and the risk is that the framework document says
  otherwise. Separately, a rule that fires once has been shown to be reachable but not to
  discriminate: nothing proves PL-28 accepts a production seed while rejecting an MVP one
  at the boundary.
- **Recommendation**: Either delete SAFE-14 and its seam and let the gate stop claiming a
  safety layer, or implement the deterministic slice that genuinely belongs there
  (bright-line lexical policy per band, which needs no provider) and keep the model
  classifiers in `moderation/` where they are. Update F2 in the brief either way. For the
  twelve thin rules, add one boundary pair each (just-inside/just-outside), this is a
  half-day and it is the cheapest coverage on the board.
- **How to check I'm right**: re-run the instrumentation, wrap
  `ValidationFinding.__init__` in a pytest plugin, run `tests/unit`, and diff the recorded
  key set against `re.findall(r'\b(?:CG|CH|L1|L2|PL|RL|SAFE|SR)-\d+[ab]?\b', ...)` over
  `src/cyo_adventure/validator/*.py`. Read `validator/safety.py` in full (57 lines).

---

## C6-9: The lockstep and rules-can-fire machinery stops at `validator/`; the script-level gates have no rule ids, no catalog, and half have no tests

- **Severity**: high
- **Category**: rule negative-testing
- **Locus**: `tests/unit/test_validator_rules_catalog.py:31` (`_VALIDATOR_DIR`); `tests/unit/test_rules_can_fire.py:24` (scope note)
- **Problem**: Two excellent guards exist and both are scoped to one package.
  `test_validator_rules_catalog.py` scans `src/cyo_adventure/validator/*.py` and fails
  when code and `docs/planning/validator-rules.md` disagree in either direction, this is
  the test that would have caught the whole undocumented SR family. `test_rules_can_fire.py`
  proves rules fire at real entry points, and says so honestly: "Scope is deliberately
  narrow ... It is not a completeness claim over every rule in the gate."

  Neither reaches the script layer, which is where a growing share of the enforced
  quality now lives. `check_fill_integrity`, `check_sibling_fills`, `check_prose_craft`,
  `check_graph_structure` (six named failure classes), `check_narrative_contract`,
  `check_branch_obligations`, `check_promise_discharge`, `check_outcome_spread`,
  `check_solution_transfer`, `check_theme_contract` and `check_skeleton`'s strict-mode
  escalations all emit findings in ad-hoc text formats with **no stable rule ids**, so
  they cannot be catalogued, cannot be referenced from a repair prompt, and cannot be
  lockstep-tested. Test coverage by file: 7 of 15 `check_*` gate scripts have a
  `tests/unit/test_<name>.py`; `check_sibling_fills`, `check_solution_transfer`,
  `check_reading_level`, `check_branch_obligations`, `check_promise_discharge`,
  `check_graph_structure`, `check_fill_fidelity`, `check_incell_clones` have none
  (`check_incell_clones`'s core is covered indirectly via `test_incell_clone_audit.py`;
  the rest are not).
  Mutation testing has the same boundary: `[tool.mutmut] only_mutate` lists
  `storybook`, `validator`, `player`, `publishing`, `moderation`, `events`,
  `story_requests`, `core/exceptions.py`, and **not** `generation/`, `diversity/`,
  `mutation/`, `measurement/`, `flywheel/`, or `scripts/`. It also runs weekly and
  scheduled runs "REPORT the score without gating on it".
- **Why it matters for the goal**: The programme's response to every measured defect has
  been to write a new deterministic check as a script. Each one is therefore load-bearing
  and each one is outside the three mechanisms (catalog lockstep, entry-point firing,
  mutation scoring) that keep the original gate honest. `check_graph_structure`'s six
  failure classes are the exact corpus S-5 will use to decide whether unreviewed shells
  may reach children; nothing proves those six classifiers fire.
- **Recommendation**: Give the script-level checks stable rule ids in the existing
  namespace (a `GS-*` family for graph structure, `FI-*` for fill integrity, and so on),
  emit them through `ValidationFinding`, add them to `validator-rules.md`, and widen
  `_VALIDATOR_DIR` in the catalog test to include `scripts/check_*.py`. That single change
  brings them under all three existing mechanisms at once. Separately, extend
  `only_mutate` to `generation/` and the script gates, and gate the weekly mutation run at
  a threshold for those paths.
- **How to check I'm right**: `sed -n 28,34p tests/unit/test_validator_rules_catalog.py`;
  `sed -n '/\[tool.mutmut\]/,/^also_copy/p' pyproject.toml`; the per-script CI/test table
  is reproducible with a loop over the fifteen script names against `.github/workflows/`
  and `tests/unit/`.

---

## C6-10: The golden corpus pins one bit, not verdicts; the calibration constants have no admit/reject regression

- **Severity**: high
- **Category**: regression corpus
- **Locus**: `tests/unit/test_filled_story_corpus.py:63`; `tests/unit/test_skeleton.py`; `tests/unit/test_corpus_layer2.py`; `scripts/check_fill_integrity.py:67`
- **Problem**: There are three corpora and only one of them pins verdicts.

  1. `tests/fixtures/storybook/invalid/{schema,graph,state}`, 16 known-bad fixtures, each
     asserting *exactly* its intended rule with node/choice attribution. This is a real
     pinned-verdict corpus and it is the right design. It covers schema, L1 graph rules,
     and L2-9..L2-12 only.
  2. `out/*.filled.json` via `test_filled_story_corpus.py`, glob-discovered, asserts
     `not result.blocked`. One bit per book.
  3. `skeletons/` via `test_skeleton.py`, same shape, one bit per shell.

  Nothing pins *which* findings the catalog produces. A validator change that stops a
  policy rule firing across the entire catalog, the CG-4 failure mode, which is exactly
  what `UW-C280` documents happening, leaves every corpus test green, because "not
  blocked" is still true. The advisory findings, which is where PL-19/23/24/25/26 and the
  whole reading-experience layer live, are invisible to the corpus entirely.

  Calibration constants are covered unevenly. `TAU_CELL` is done well: loaded from
  `ws5_floor_baseline.json` ("never a literal"), gated in CI by
  `check_incell_clones.py --check` over the real catalog with a shrink-only allowlist.
  The fill-rate floor is not: `test_check_fill_integrity.py` has 15 tests, two of which
  exercise the rate (a synthetic 40% book fails, a synthetic full book passes). The
  actual calibration *claim*, stated in a careful 20-line comment at
  `check_fill_integrity.py:48-67`, that the floor admits all 48 committed (skeleton,
  filled) pairs with the tightest known-good at 0.635 and that "a raise above ~0.63 starts
  rejecting known-good fills", is asserted by no test. A change to word counting, or a
  new committed fill, moves that margin silently. The 4-gram budget 4.0 and idiom floor
  3.3 have no test at all (see C6-2).
- **Why it matters for the goal**: The gate is the only thing standing between a
  generated book and a human reviewer whose attention is the scarce resource. A silent
  loosening is the failure mode that costs most, because it is invisible by construction
  and only shows up as reviewer fatigue.
- **Recommendation**: Convert the two glob corpora from `assert not blocked` to a pinned
  snapshot: store `sorted(report.rule_ids())` per artifact in a committed
  `tests/fixtures/gate_verdicts.json` and fail on any diff, with an explicit
  `--update-verdicts` regeneration path so the diff is reviewed rather than avoided. This
  catches both loosening and unintended tightening, costs nothing at runtime, and turns
  every future catalog addition into free coverage. Then add the fill-rate calibration
  test: sweep the floor from 0.55 to 0.75 over the 48 committed pairs and assert the
  admit/reject boundary sits where the comment says it does.
- **How to check I'm right**: read `tests/unit/test_filled_story_corpus.py:60-70` (the
  entire assertion is `assert not result.blocked`); `grep -n "0\.6\|fill_rate" tests/unit/test_check_fill_integrity.py`
  shows no test naming the 48-pair corpus.

---

## C6-11: Every LLM path is mocked with hand-written bodies; no contract test ties the mocks to a real provider response

- **Severity**: medium
- **Category**: non-determinism
- **Locus**: `src/cyo_adventure/generation/providers/_base.py:74` (`dig_content`); `src/cyo_adventure/generation/providers/openrouter.py:322` (`_extract_completion`); `tests/unit/test_providers.py:1-13`
- **Problem**: The good news first: there are **no flaky, costly model calls in the PR
  test path**. Every LLM-dependent test is deterministic, `MockProvider(responses=[...])`
  for the orchestrator and worker, `httpx.MockTransport` for the adapters, retry backoff
  set to 0. The live tiers are correctly quarantined: `tests/llm_eval/` skips unless
  credentials are present, `safety-eval.yml` runs weekly and *fails loudly* if credentials
  are absent rather than passing vacuously ("The llm_eval tier would skip every test, so
  this run would report success while measuring nothing"). That is exactly right.

  The gap is that no recorded real response exists anywhere, no VCR, no cassettes, no
  captured payloads. Every mock body is a hand-authored fiction of the provider's schema,
  written from memory of the API. Combined with the deliberately-defensive parsers, the
  failure mode is silent: `dig_content` narrows with `isinstance` at every level and
  returns `None` on any unexpected shape; `_extract_completion` then raises a
  `ProviderError` whose `leg_fatal` is `finish_reason == "length"`. So if OpenRouter
  moves content into a reasoning/content-block array, the direction every provider has
  moved, every response parses as empty, `finish_reason` is `"stop"`, the error is
  classified **transient**, and the harness retries a leg that will never succeed. The
  observable symptom is "the provider is flaky", and the entire unit suite stays green.
  `AL-329` records the programme already paying three attempts at ~$0.50 and eleven
  minutes each for a closely related misclassification.
- **Why it matters for the goal**: F7 is "engineer the cost", and the two most expensive
  measured waste modes were caps below reasoning overhead (`AL-328`) and non-converging
  retry loops. A response-shape change reproduces the second one exactly, and the test
  suite is structurally unable to see it coming.
- **Recommendation**: Add a recorded-response contract fixture per provider: capture one
  real 200 response per adapter (redacted), commit it under
  `tests/fixtures/providers/<name>.response.json`, and assert `dig_content`,
  `dig_usage`, `dig_finish_reason` and `dig_reasoning_tokens` all extract non-`None` from
  it. Then refresh those fixtures from the existing weekly live workflow, one extra step
  in `safety-eval.yml` that re-captures and diffs, so a shape change surfaces as a
  scheduled red run with a diff rather than as production flakiness. Second, make
  "content empty with `finish_reason == 'stop'`" leg-fatal rather than transient: a
  well-formed 200 with no content is a contract violation, not a network blip.
- **How to check I'm right**: `grep -rn "cassette\|vcr\|respx\|httpx_mock" tests/` returns
  nothing; read `_base.py:74-103` and `openrouter.py:322-380`.

---

## C6-12: The one true end-to-end test drives the canned story, not the skeleton-fill path the framework describes

- **Severity**: medium
- **Category**: e2e
- **Locus**: `frontend/e2e-real/full-pipeline-real.spec.ts:22-28`; `tests/integration/test_generation_worker.py:111` (`_filled_skeleton_json_for`)
- **Problem**: An end-to-end test *does* exist, and it is better than expected: request →
  generate → gate → moderate → approve → publish → read, driven through a real RQ worker,
  a real Postgres, the real admin approve UI and the real kid reader, asserting review
  queue membership, `screened == true`, status transitions, and an ending screen. It runs
  nightly (`e2e-real-nightly.yml`, plus a PR smoke tier).

  But it drives the *legacy concept* path. Its own header says so: "The mock generation
  provider ... ignores the submitted brief and always returns the same canned story titled
  'The Forest Path' ... so every assertion below is pinned to that title". `_CANNED_STORY`
  is a 5-node Tier-1 book. Nothing in that run touches `skeleton_match`, theme binding,
  `build_differentiation_directive`, `fill_skeleton`, chunked fill, or the anti-clone
  path, that is, none of section 3.3 of the framework.

  The skeleton path is covered one level down, in
  `tests/integration/test_generation_worker.py`, which drives `fill_skeleton` over real
  catalog skeletons in two bands with a real cross-band override. That is good coverage.
  Its mock, however, returns the skeleton with *every* FILL body replaced by adequate
  prose, the happy path. There is no integration or e2e test in which the fill is
  structurally perfect and materially incomplete, which is the AL-490 shape and the only
  defect the programme has measured at scale.
- **Why it matters for the goal**: The contract that matters, "a request becomes a book
  a guardian can approve, and a hollow one cannot", is asserted for a canned 5-node
  story and for a perfect fill. Neither is the production case.
- **Recommendation**: The cheapest useful addition is not a new e2e; it is one
  integration test. Extend `test_generation_worker.py` with a `MockProvider` whose reply
  fills every body with a single short sentence (structurally valid, ~40% of commissioned
  words), assert the job does not reach a clean `in_review`, and let it fail until C6-1's
  fill-rate wiring lands, that test *is* the specification for C6-1. Second, add a
  skeleton-fill variant of `full-pipeline-real.spec.ts` that goes through the story-request
  intake rather than the bare concept endpoint, so the nightly tier exercises
  `skeleton_match` + binding at least once a day.
- **How to check I'm right**: read `frontend/e2e-real/full-pipeline-real.spec.ts:1-40` and
  `grep -n "CANNED_TITLE" ` in it; read `tests/integration/test_generation_worker.py:111-135`.

---

## C6-13: Untested behaviours in the generation-critical modules, named

- **Severity**: medium
- **Category**: coverage gap
- **Locus**: see per-item loci below
- **Problem**: Coverage percentage is not the answer, and the aggregate is already high:
  the 2026-07-09 audit measured backend 95.69% line / 90.61% branch over 111 files with
  only two critical modules below the declared 90/80 floor (`moderation/classifiers.py`
  80.6/77.3, `moderation/report.py` 89.3/50.0). I went looking for the specific paths the
  task names, and most of them turned out to be **covered**, which is worth stating
  plainly so effort goes where it is needed:

  - **Chunked fill assembly**: 35 tests (`tests/unit/test_chunked_fill.py`): partition
    stability, graph-order batching, merge-cannot-change-the-graph, omitted/invented nodes,
    a batch echoing the FILL directive, fence- and stage-marker injection neutralisation,
    PII abort propagation, and "a skeleton no partition can fill fails without spending".
  - **Repair loops**: `tests/unit/test_orchestrator.py` covers repair exhaustion
    (`attempts == max_repairs` → `needs_review`), no-progress abort before the cap, and
    malformed Stage-B output routed through repair to `needs_review`. `fill_skeleton`'s
    stage-1 fidelity loop has its own set (pass-after-one-fail, exhaustion downgrade with
    the `stage1_fidelity_violations` key, fidelity-aware repair prompt, and the
    required/skipped posture matrix).
  - **Cap/truncation**: `test_fill_output_cap.py`, `test_openrouter_provider_pin.py`
    (both empty-body shapes, `leg_fatal` True for `length` only), `test_providers.py`
    (2,116 lines: transient vs leg-fatal, cross-leg failover, circuit breaker, exhaustion,
    and that a non-`ProviderError` is never swallowed).
  - **Publish state machine illegal transitions**: all 25 (Status × Action) pairs driven
    exhaustively in `test_state_machine.py`, plus the service layer in
    `tests/integration/test_approval_api.py` (409 on illegal hop, double-approve,
    approve-unscreened → 400, submit-without-moderation → 400, full role × action matrix).
  - **Moderation threshold application**: better than I expected. `_severity_from_score`
    is parametrised at every boundary (`floor`, `just_below_medium`, `medium_boundary`,
    `just_below_high`, `high_boundary`, `ceiling`), `test_min_score_exactly_at_floor_surfaces`
    pins the inclusive floor, and `test_threshold_policy_loader.py` pins per-`(age_band,
    category)` row resolution and fall-through to `DEFAULT_THRESHOLD`.

  What is genuinely untested, in priority order:

  1. **Hollow-fill recovery.** No test anywhere drives a structurally-valid, materially
     under-delivered fill through `run_generation_job`, because nothing in that path can
     detect one (C6-1). This is the top gap in the whole component: the programme's
     largest measured defect has no test.
  2. **The cost of a failed chunked fill.** `orchestrator.py:1150` deliberately fails the
     whole fill rather than merging partially, and
     `test_a_batch_that_returns_nothing_fails_the_whole_fill` pins that. Correct design;
     but for a 677-node book the discarded spend is the entire fill, and nothing measures
     or caps it. There is no test that a fill which fails on batch 6 of 7 records what it
     spent, and no persistence of the prose already written, `resume_manual_fill` exists
     for skill-authored fills only, not for the automated chunked path.
  3. **`moderation/report.py` branch coverage.** 50% branch, with
     `Finding.__post_init__` at 40% as of the July audit; this is the object every
     downstream surface reads, and it is the worst-covered branch set in the moderation
     package.
  4. **`safety_flagged` in production.** `test_orchestrator.py` case 8 drives the
     "gate clean but safety_flagged → needs_review" branch with a forced flag, so the code
     is covered, but because SAFE-14 is a permanent stub (C6-8), the flag can never be
     `True` in production. The test therefore proves a route nothing can take.
  5. **`reading_level_loop.py` Stage-D under-delivery.** The module documents "two ways
     Stage D can under-deliver" behind one flag (`reading_level_loop.py:222`); the loop
     has a test module, but the two under-delivery modes are not separately asserted, so a
     consumer cannot distinguish them and no test says it should be able to.
- **Why it matters for the goal**: Items 1 and 2 are the two places where a failure costs
  either a bad book reaching a reviewer or real money, as opposed to raising an exception
  the suite would catch.
- **Recommendation**: Write item 1 first, it doubles as the executable specification for
  the C6-1 wiring, and should be written to fail today. Item 2 is a metering assertion on
  the existing `generation/usage.py` seam, not new machinery. Items 3-5 are ordinary
  backfill.
- **How to check I'm right**: for each item, grep the named test module; e.g.
  `grep -n "resume\|partial" tests/unit/test_chunked_fill.py` finds only the
  total-failure case, and `grep -rn "resume_manual_fill" src/cyo_adventure/generation/worker.py`
  returns nothing.

## C6-14: Refuted results have no re-test trigger, and one of them is explicitly model-dependent

- **Severity**: medium
- **Category**: register integrity
- **Locus**: `docs/planning/authoring-lessons-log.md` AL-267; `docs/planning/diversity-test-register.md` section on refuted levers
- **Problem**: The programme has a healthy list of refuted levers (theme binding, device
  pools, model tier, per-request single-parent mutation, multiple obligation contracts,
  instructed independence) and correctly declines to re-propose them, there is even a
  "do-not-re-propose list" in the technique review. What is missing is the inverse: a
  trigger that re-opens a refutation when its premise changes.

  The clearest case is `AL-267`. Its own proposed change reads: "Record 3.3 as the
  measured floor beside the 4.0 budget wherever the budget is cited, and **re-measure it
  whenever the generation model changes, since it is a property of the model rather than
  of any architecture**." There is no mechanism that notices a generation-model change,
  and the fill model is changing right now, the brief's own conclusion is to move fills
  to DeepSeek V4 Pro. So the idiom floor every diversity result is stated against was
  measured on a model the product is leaving, and nothing will notice. `AL-267` is still
  `open`. The same applies to S-7 (recognition identical at both craft extremes), which is
  a claim about the models that were tested.
- **Why it matters for the goal**: A refutation is only as durable as its premise. The
  register is designed so a result cannot be lost; it has no design for a result going
  stale.
- **Recommendation**: Add a `Premise` column to the register's result rows naming what
  would invalidate the finding (typically: the fill model, the band, the catalog size),
  and a `scripts/check_stale_results.py` that compares the recorded fill model against
  the configured one and fails the Planning Linkage job when a `done` row's premise no
  longer holds. Cheaper interim: when the fill model changes, re-run the two deterministic
  instruments (idiom floor, in-cell clone audit) as part of that PR, and say so in the ADR.
- **How to check I'm right**: `grep -n "AL-267" docs/planning/authoring-lessons-log.md`
  (status `open`, ref `UW-C197`); `grep -rn "re-measure\|remeasure" .github/ scripts/`
  returns nothing.

---

## C6-15: The missing test tier, ranked by value per unit cost

- **Severity**: medium
- **Category**: missing tier
- **Locus**: `docs/planning/safety/adversarial-corpus.json`; `.github/workflows/safety-eval.yml`; `.claude/skills/naive-ux-check/`
- **Problem**: Taking the tiers in the brief's own terms, deterministic, model-judged,
  human-gated, the product has strong deterministic coverage, adequate model-judged
  coverage, and essentially no human-gated coverage above the single approving adult.
  Ranked by value per unit cost:

  1. **Adversarial safety corpus expansion, highest value, lowest cost.** The tier
     *exists* and is well built: `tests/llm_eval/test_adversarial_safety_eval.py` runs the
     corpus against the real classifiers weekly with live credentials and asserts 100%
     human-routing for classes A and B and 100% pre-egress block for class F, and refuses
     to pass vacuously without credentials. It is **13 items**. Classes C, D and E are
     recorded but not gated. Thirteen items is a smoke test, not a corpus. Growing it to
     ~150 costs authoring time and no infrastructure, and it is the only tier that
     directly protects a child.
  2. **Structural-defect corpus for the gate (S-5's prerequisite), high value, low
     cost, already scoped.** S-5 pre-registers "~15-20 shells: six `check_graph_structure`
     failure classes plus AL-227/AL-228-shaped defects" with a 100%/90% catch-rate floor,
     and the register says "corpus buildable now". `scripts/seed_defects.py` exists.
     Building it is deterministic, needs no model spend, and converts C6-9's untested
     classifiers into gated ones.
  3. **Longitudinal production quality monitoring, high value, medium cost.** The
     signals already exist as product features (ratings, flags, reading time, completion,
     `flywheel/`). Nothing aggregates them into a per-book or per-skeleton quality
     time-series with an alert. The cheapest version is a weekly job that recomputes the
     deterministic measures (fill rate, sibling grams, reading level) over the last N
     published books and files an issue on a trend break, the same pattern
     `supabase-backup.yml` and `safety-eval.yml` already use for alerting.
  4. **Canary books, medium value, low cost.** A small set of deliberately-defective
     published-shaped books that must always be caught, run through the gate on every PR.
     This is the golden corpus of C6-10 pointed at the publish path rather than the
     validator, and it is nearly free once C6-10's pinned verdicts exist.
  5. **Human/child comprehension testing, highest value in principle, highest cost, and
     currently absent.** The closest thing is the `naive-ux-check` skill and
     `naive-user-ux-testing-design.md`, which drive a *model* persona through the UI. That
     is a usability probe, not comprehension testing, and no child has been measured. For
     a reading app for children, the untested question is the product's central one: can
     the target reader follow the branch structure and does the prose land at the band.
     A ten-child protocol at two bands would cost more than everything above combined and
     would be worth it before public launch (ADR-008), not before R1.
  6. **A/B on real readers, lowest value now.** The install base is one family. A/B is
     the right instrument at scale and the wrong one at n=1; the register's own Q-1 result
     (a child exhausts a cell by roughly the fourth request) says the sample is
     structurally too small.
- **Why it matters for the goal**: Items 1, 2 and 4 are all cheap, all deterministic, and
  all protect the two things that cannot be recovered after the fact: a child seeing
  unsafe content, and a reviewer's trust in the gate.
- **Recommendation**: Do 1, 2 and 4 in that order before Phase 5; schedule 3 with the
  flywheel work; schedule 5 as a gate on the public launch decision; drop 6 until there
  is a population.
- **How to check I'm right**: `python3 -c "import json;print(len(json.load(open('docs/planning/safety/adversarial-corpus.json'))['items']))"`
  → 13; read `tests/llm_eval/test_adversarial_safety_eval.py:1-27` for the gated/ungated
  class split; `ls .claude/skills/naive-ux-check/` and read its description.

---

## Strengths worth preserving (so a future change does not remove them by accident)

These are unusual and each one exists because a specific defect got through. Removing any
of them would be a regression:

- `tests/unit/test_rules_can_fire.py`, asserts rules fire through **real entry points
  with production flags**, written after three rules were dead in the wiring while every
  direct-call test passed. The docstring explaining why a registry loop "would have caught
  none of them" is the single most valuable page of test documentation in the repo.
- `tests/unit/test_validator_rules_catalog.py`, bidirectional code/catalog lockstep, with
  `RESERVED` / `NO ID EMITTED` as the only two permitted explanations for a documented rule
  with no code.
- `test_the_corpus_is_not_empty` in `test_filled_story_corpus.py`, guards the guard
  against a broken glob passing vacuously. The same instinct appears in
  `safety-eval.yml`'s credential precondition and in `check_incell_clones`'s
  shrink-only allowlist.
- The `diversity` CI job, `run_diversity_eval.py --check` over committed panel fixtures
  plus `check_incell_clones.py --check` over the real catalog against a `TAU_CELL` loaded
  from a committed baseline file, "never a literal".
- `skeleton-promotion.yml`, re-proves every changed shell from scratch, filters no shell
  out of the prover's argv, and blocks auto-merge on the promotion label.
- The `d7b-bare-names/build.py` docstring, which states its prediction and **two**
  falsifiers before any artifact exists, and names which failure would be the interesting
  one. That is the register's contract done properly at file level.
- `recognition-protocol-pilot/results.md`, a failed instrument reported as failed, with
  the tempting post-hoc repair explicitly refused as un-adoptable on seen data. This is
  the behaviour C6-3 is asking the format to make routine rather than exceptional.
