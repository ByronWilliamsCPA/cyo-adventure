---
schema_type: planning
title: "Evaluation: choice labels in the structure fingerprint (decision analysis and recommendation)"
description: "Fable evaluation of the open decision recorded in ws0-label-fingerprint-finding.md:
  whether choice labels remain part of structure_fingerprint (option 1), become leaf content
  stripped from the fingerprint and folded into the anti-template guard's leaf distance
  (option 2), or the decision is deferred (option 3). Includes two hybrid designs, empirical
  re-baseline numbers computed over the committed panel, a single recommendation (option 2),
  and a file-by-file implementation outline."
tags:
  - planning
  - diversity
  - generation
status: proposed
owner: core-maintainer
component: Strategy
source: "Fable evaluation 2026-07-18, verified against diversity/{structure,leaf,normalize,
  panel,query,aggregate,lexical,report}.py, tests/data/diversity_panel/ (manifest, baseline,
  all three cave fills), tests/unit/test_diversity_{structure,leaf,panel}.py,
  scripts/{check_fill_integrity,run_story_gate,run_diversity_eval}.py,
  generation/templates/fill.md, generation/{worker,orchestrator}.py, the harrowstone skeleton
  on origin/claude/fable-dnd-series-testing-1eqkom (d075b22), and the WS-0/WS-1 sections of
  ws0-diversity-metrics-design.md, ws0-phase2-harness-design.md, story-flexibility-plan.md.
  Companion to ws0-label-fingerprint-finding.md."
---

# Evaluation: choice labels in the structure fingerprint

## 0. Summary

**Recommendation: option 2, labels become leaves.** Strip `choices[].label` from
`structure_fingerprint`, fold label text into the anti-template guard's per-node leaf
distance, extend entity masking to label text, align `check_fill_integrity.py`, and
re-baseline the panel in the same PR. Empirical verification over the committed panel
(section 5.2) shows every R1 expected verdict survives unchanged with wide margins, so no
threshold retuning is needed. The decisive facts:

1. **Option 1 does not fix the WS-1 gap it appears to fix.** `fill.md` instructs the model
   to rewrite *every* label into final choice text, theme-neutral or not; fingerprint
   equality after two automated production fills is model-luck under option 1, even on a
   theme-neutral skeleton. None of the three committed cave fills went through that path
   (section 2, flag F1), so the 63/63 evidence does not test it.
2. **The semantics are already decided.** `story-flexibility-plan.md` (WS-2 and section 8)
   records: "labels are content with a frozen action-semantic, not frozen strings; the
   pilot froze them, a step back." Option 1 would reverse a recorded decision; option 2
   implements it in the metric layer. Under the leaves-on-a-tree model, the choice edge,
   its target, and its action-semantic are tree; the label *string* the child reads is a
   leaf (section 3).
3. **The cost asymmetry is stark.** Option 2 is a small, mechanical, fully reversible
   change confined to `diversity/`, one standalone script, and one committed baseline.
   No fingerprint is stored in the database, no API surface reads it, and
   `structure_fingerprint` is consumed nowhere outside `diversity/` itself (verified by
   repo-wide search). Option 1's cost is permanent: an authoring rule that fights the
   shipped fill contract forever, a new theme-neutral skeleton to author, and a WS-1 gap
   that stays open.

Option 3's cross-tree harrowstone addition remains a good *independent* panel-growth step
and is folded into the implementation outline, but as a complement, not a substitute for
deciding.

---

## 1. What was verified (facts, all re-checked in code 2026-07-18)

All five facts in `ws0-label-fingerprint-finding.md` reproduce:

| # | Finding-doc fact | Verified against | Result |
|---|---|---|---|
| 1 | `_strip_leaf_content` removes only `title`, node `body`, `ending.title`; labels retained in the fingerprint | `diversity/structure.py:53-93` | Confirmed |
| 2 | ATG requires fingerprint equality, raises `ValidationError` otherwise; measures node bodies only | `diversity/leaf.py:215-256`, `leaf_distance_profile` reads `node.body` only | Confirmed |
| 3 | The automated fill rewrites labels | `generation/templates/fill.md`: "every choice label ... turn into the final choice text ... matching the semantic intent of that choice's original label" | Confirmed |
| 4 | `check_fill_integrity.py` requires labels byte-identical; standalone; not runtime-enforced | Script strips only `body`; nothing under `src/` imports it; no workflow and no nox session runs it; the `validator/` gate never sees the skeleton | Confirmed (and slightly *understated*, see F4) |
| 5 | Cave fills: 63/63 labels byte-identical; harrowstone bakes plot proper nouns into labels | Recomputed: all three cave fills have 64 nodes / 63 choices, labels byte-identical (also implied by their equal fingerprints in `baseline.json`). Harrowstone (`d075b22` on `origin/claude/fable-dnd-series-testing-1eqkom`): 801 choices, 34 distinct sentence-medial capitalized tokens in labels (Bram, Elowen, Harrowstone, Redcloaks, ...) | Confirmed |

Additional load-bearing facts established for this evaluation:

- **`structure_fingerprint` has zero consumers outside `diversity/`.** No DB column, no
  API schema, no event payload stores it. The only persisted artifact keyed on it is
  `tests/data/diversity_panel/baseline.json` (per-fill `fingerprint` values, R5). A
  fingerprint algorithm change is therefore a one-file re-baseline, explicitly anticipated
  by R5's own wording ("or fingerprint algorithm changed; both demand a deliberate
  `--update-baseline`").
- **No runtime path compares a fill to its skeleton field-by-field.** `fill_skeleton`
  gate-validates the model's full returned JSON (`run_gate`) and runs the Stage 1 beat
  fidelity check, but never diffs ids/targets/conditions/labels against the skeleton
  file. Structural immutability of a fill is contract, not enforcement, under *every*
  option; this evaluation only decides which field is allowed to move.
- **`select_atg_comparison_partner` (the WS-1 pairing entry point) already matches on
  `skeleton_slug`, not fingerprint** (`diversity/query.py:205-231`). The fingerprint
  equality assertion inside `anti_template_verdict` is the second, stricter gate the pair
  must then pass. This is where the WS-1 gap bites: slug-matched production pairs will
  reach an ATG that raises.

## 2. Flags: where the finding doc and shipped docs are imprecise

- **F1 (material).** The finding's fact 5 offers the 63/63 cave labels as evidence that
  "theme-neutral-label skeletons" keep the same-tree precondition intact. But none of the
  three cave fills was produced by the automated `fill.md` path: `panel.json` provenance
  shows `cave-sea` came from the manual initial-inventory run (label-freezing by the
  `check_fill_integrity` convention) and `cave-space`/`cave-dino` from the pilot
  parameterization, which froze labels by design (the plan calls that freeze "a step
  back"). The 63/63 result therefore demonstrates *label-preserving fill paths*, not
  theme-neutral-label robustness under production fills. `fill.md` instructs a label
  rewrite unconditionally; a model may echo a theme-neutral label byte-for-byte, but
  nothing makes it. Option 1's premise is weaker than the finding presents it, and
  option 1's text does not state that the WS-1 gap remains open under it. It does.
- **F2 (doc rot to fix in the same PR).** `structure.py::structure_fingerprint`'s
  docstring claims "Two fills of one skeleton hash equal by construction (the fill
  contract forbids touching anything but bodies)". False for the shipped automated fill
  contract, which mandates label rewrites. Same claim in
  `ws0-diversity-metrics-design.md` section 2.4 ("the fill contract forbids touching
  anything but bodies; `check_fill_integrity` enforces it").
- **F3 (minor).** The finding calls label immutability "a manual/CI convention". It is
  manual only: no CI workflow, nox session, or skill hook runs `check_fill_integrity.py`
  (verified across `.github/workflows/` and `noxfile.py`).
- **F4 (minor).** `ws0-diversity-metrics-design.md`'s terminology block cross-references
  the fingerprint as "section 3.6"; it is defined in section 2.4.

None of these flags changes the shape of the decision; F1 changes its weight, decisively
against option 1.

## 3. The model question: is a choice label tree or leaf?

The leaves-on-a-tree objective (`story-flexibility-plan.md` section 1): minimize
perceived similarity; the **tree** is the paths and decision points and may be shared;
the **leaves** are the per-point descriptions and must genuinely differ.

A choice has four aspects. They do not all fall on the same side:

| Aspect | Model side | Why |
|---|---|---|
| The edge (`choice.id`, `target`) | Tree | It *is* the decision point and path |
| `condition` / `effects` | Tree | Routing and state semantics |
| The label's action-semantic ("go left at the fork", "trust the stranger") | Tree | It defines what the decision *is*; `fill.md` freezes it ("matching the semantic intent of that choice's original label") |
| The label's surface string ("Follow the humming echo to the left." vs "Drift left along the humming service duct.") | Leaf | It is prose the child reads, rewritten per theme by the shipped fill, exactly like a body sentence |

So the answer *does* depend on whether the label encodes routing semantics vs surface
prose, and the codebase has already split the two: semantics frozen (a Stage-1-style
fidelity concern), surface free (a fill concern). The fingerprint is a byte-level hash;
it cannot hold the semantic and release the surface. It must pick a side for the whole
string, and the string is surface. The design doc itself set the precedent with the
identical argument for titles: "titles are excluded from the fingerprint because the
pilot's parameterized skeleton rewrites ending titles per theme; titles are leaves."
Substitute "labels" and "the automated fill" and the sentence is this decision.

The residual worry, "if labels leave the fingerprint, a fill could silently change what a
choice *means*", is real but is not the fingerprint's job. Nothing compares ids, targets,
or conditions to the skeleton at runtime either (section 1); semantic label fidelity
belongs with the Stage 1 beat check (a WS-1/WS-2 item: extend the fidelity reviewer's
per-node beat comparison to per-choice label intent), not with a byte hash that the
shipped fill contract guarantees to break.

## 4. Option analysis

### 4.1 Option 1: labels stay structure

Keep the fingerprint as-is; add a "theme-neutral choice labels" skeleton-authoring rule;
retire the panel monoculture with a theme-neutral non-cave skeleton filled under two
themes; harrowstone is cross-tree only.

**Code impact.** None to shipped metrics (that is its advertised virtue). New skeleton
plus two fills authored, panel/baseline grown. To actually make the precondition hold on
the live path, however, one of two *additional* changes is unavoidable, and the option's
framing hides this:

- (a) change `fill.md` to forbid label rewrites (freeze labels), reverting the recorded
  WS-2 position and re-flattening labels into template text a reader sees verbatim across
  every theme of a skeleton, or
- (b) add runtime enforcement (a skeleton-vs-fill label diff in the worker) plus a repair
  path for the near-certain violations, spending `max_repairs` budget on byte-echoing
  labels.

**Process impact.** Panel growth constrained forever: every same-tree candidate skeleton
must pass a theme-neutrality review of every label; harrowstone-class skeletons (801
labels, 34 proper-noun tokens) are permanently same-tree-ineligible. The supervisor's
mandated `branch_and_bottleneck` follow-up panel skeleton inherits the constraint.
WS-1's `select_atg_comparison_partner` flow stays broken on real production fills unless
(a) or (b) above also ships. The WS-8 flywheel (promote gate-passed fresh trees into the
parameterized catalog) inherits a label-authoring rule that fights `fill.md`.

**Risk / reversibility / fidelity.** Low mechanical risk, high strategic cost. Reversible
in code (nothing changed) but not in authored content: skeletons written under the
neutrality rule carry blander labels permanently. Fidelity to the objective is poor:
it protects the metric's convenience by flattening reader-facing prose, i.e. it trades
away leaf diversity (the primary lever) to keep a hash stable. Kids read labels; 63
identical "Follow the humming echo to the left." strings across a sea cave, a space
station, and a dino dig is itself a small perceived-similarity leak the current metric
cannot even see.

### 4.2 Option 2: labels become leaves (recommended)

Strip `label` in `_strip_leaf_content`; fold label text into the ATG leaf distance and
entity masking; align `check_fill_integrity`; re-baseline.

**Code impact** (exact; see section 6 for the full outline):

- `diversity/structure.py::_strip_leaf_content`: pop `label` from every choice dict
  (choices sit under each node's `choices` list; fields per `storybook/models.py::Choice`
  are `id`, `label`, `target`, `condition`, `effects`; only `label` is stripped).
  `structure_fingerprint` docstring corrected (F2). No signature changes.
  `structural_distance` is otherwise untouched: `structure_features` never reads labels,
  so graded distances and the R5 cross-tree invariant are unaffected; only the
  fingerprint-equality short-circuit widens to label-variant same-tree pairs, which is
  exactly the intended semantics ("same tree").
- `diversity/normalize.py::extract_entities`: scan choice labels as well as bodies for
  medial-caps tokens (one line: extend the `bodies` list with labels). Without this, a
  label-level noun swap ("the Gull and Lantern" to "the Crab and Candle") would read as
  genuine relabeling; with it, the dog-for-cat detector covers labels the same way it
  covers bodies.
- `diversity/leaf.py::leaf_distance_profile`: per-node leaf text becomes
  `node.body + " " + " ".join(choice labels in order)` for masking, `d_uni`, and `d_big`.
  `word_count_a/b` stay body-only (they mirror the band word-count envelope, a body
  concept; document this). `anti_template_verdict` unchanged except docstrings: its
  precondition is now genuinely "same tree" rather than "same tree and same label bytes".
- `diversity/aggregate.py::_whole_story_token_counts`: pool label tokens too, so the
  cross-tree cosine branch sees the same leaf definition (small, symmetric; PS is
  trend-only and never gated, so this is cheap now and confusing to retrofit later).
- `diversity/lexical.py`: deliberately unchanged. The lexical guard protects prose
  variety within one fill against the band envelope; labels are functional micro-copy,
  formulaic by design, and folding them in would dilute `distinct_2` with imperative
  boilerplate. Document the exclusion in the module docstring. (Baseline `distinct_*`
  values still shift slightly because the shared entity set from `extract_entities`
  grows; the re-baseline absorbs it.)
- `scripts/check_fill_integrity.py::_strip_bodies`: also pop `choices[].label` before
  the byte-compare (rename to `_strip_leaf_fields`); update the failure message. The
  `<<FILL` marker scan already covers the whole raw JSON, so rewritten labels containing
  markers are already caught. The manual `cyo-author` path is unaffected in practice
  (leaving skeleton labels untouched still passes); the script simply stops rejecting the
  behavior the automated contract requires.
- **Panel and baseline.** All seven fills' fingerprints change (the canonical payload
  loses a key, so every hash moves even where labels were never rewritten): R5 fires
  against the old baseline by design, forcing the deliberate same-PR
  `--update-baseline`. Deltas beyond fingerprints: the five ATG pairs' distance stats
  and `templated_node_count` inputs, same-tree `ps_pairs` entries, `rar_sequence`
  (PS-derived), and small `fills.distinct_*` shifts from the entity-set growth.
  `struct_pairs` and `brief_pairs` are unchanged. `panel.json` (the human contract,
  R1/R4) is untouched: section 5.2 verifies every expected verdict holds. Byte-stability
  is preserved: the writer is still `json.dumps(payload, sort_keys=True, indent=2)` over
  6-decimal rounded floats.
- **Tests.** Existing suites survive (verified empirically for the verdict-bearing
  assertions, section 5.2): `test_anti_template_guard_pilot_fills_score_as_different`'s
  `median >= 0.60 / p25 >= 0.45` margins hold; the noun-swap and identical-pair FAIL
  tests hold; `test_main_check_returns_zero_on_committed_tree` passes once the new
  baseline is committed. Required updates and additions are listed in section 6.

**Process impact.** Panel growth is unconstrained by label style: harrowstone-class
skeletons become same-tree eligible, so the mandated `branch_and_bottleneck` panel
skeleton and any future gamebook fixture can carry theme-specific labels. WS-1's flow
becomes well-defined on real production fills: slug-matched partner, label-free
fingerprint equality as the precondition, and any remaining mismatch is a true positive
(the fill touched ids/targets/conditions/metadata, a contract violation worth flagging).
Recommend WS-1 treat the ATG's `ValidationError` as a "structure drifted, needs_review"
finding rather than an exception path. The flywheel and WS-2 parameterization inherit a
consistent rule: labels are leaves everywhere (fingerprint, ATG, fill contract, integrity
script), with the action-semantic guarded by Stage-1-style fidelity, not byte equality.

**Risk / reversibility / fidelity.** The mechanical risk is the re-baseline itself, and
it is bounded: one committed JSON file, regenerated by the existing tool, reviewed under
the existing authority split (R1/R4 expectations cannot be blessed by the rewrite).
The measured verdict margins (section 5.2) leave the R1 contract untouched, so the
change cannot silently weaken the guard. Fully reversible: re-add the key to
`_strip_leaf_content`, revert the two-line folds, re-baseline again; no data migration
in either direction. Fidelity to the model is exact: shared tree (edges, targets,
conditions, semantics via beats), differing leaves (bodies, titles, labels), and the ATG
now *measures* label diversity instead of being broken by it.

### 4.3 Option 3: defer (harrowstone as cross-tree only)

**Code impact.** None to metrics. Panel gains a 13-16 harrowstone fill as a cross-tree
entry and struct/PS pairs (and the first non-8-11 gated band entry, useful regardless).

**Process impact.** The monoculture persists: every gating same-tree pair stays on one
skeleton, one topology, one band. WS-1 is the *next* workstream and its core check is
same-tree; deferral means WS-1 either stalls on this exact decision (made later, under
schedule pressure, after more fixtures and possibly stored artifacts have accreted on the
current fingerprint) or ships wired to a precondition known to be false on the live path.
The decision does not get cheaper with time; it gets more expensive with every new
fingerprint consumer.

**Risk / reversibility / fidelity.** Zero immediate risk, maximum retained strategic
risk. The finding doc itself frames option 3 correctly as an interim step, not an
answer.

### 4.4 Hybrid A: proper-noun-masked labels stay in the fingerprint (rejected)

Hash labels after entity masking, so "semantically identical routing survives a reskin
while genuine relabels don't."

Rejected on two grounds. First, it defends against the wrong transformation: the shipped
fill contract mandates *rephrasing* ("turn into the final choice text ... 5-12 words"),
not noun substitution. "Go straight into the Gull and Lantern." reskinned for space
becomes "Head into the dockside canteen.", and no noun mask makes those hash equal; the
precondition breaks for exactly the production fills that matter, which is the status
quo with extra steps. Second, it poisons the fingerprint's contract: masking depends on
`extract_entities` (heuristic, brief-dependent, version-sensitive), so a supposedly
structural identity hash would change when the masking heuristic improves or when a
brief travels differently, producing R5 churn and destroying the "same bytes in, same
hash out, forever" property a baseline-pinned identity needs. A fingerprint must depend
on nothing that is allowed to get smarter.

### 4.5 Hybrid B: "same tree" by `skeleton_slug` or graph shape (collapses into option 2)

Matching the ATG precondition on graph shape (everything except prose) *is* the
option 2 fingerprint; there is no separate design there. Matching on `skeleton_slug`
alone is strictly weaker: the slug is provenance metadata (absent for
`fresh_generation`), and two fills of *different structural versions* of one slug would
be declared same-tree while `leaf_distance_profile` silently compared only the
intersecting node ids, shrinking `node_count` without any signal that the trees
diverged. Keep slug where it already is (partner *selection* in
`select_atg_comparison_partner`) and keep a structural equality assertion as the
*precondition*; option 2 makes that assertion the right one.

## 5. Empirical verification

### 5.1 Harrowstone label census

`git show d075b22:skeletons/13-16/the-harrowstone-keep.json`: 550 nodes, 801 choices,
34 distinct sentence-medial capitalized tokens across labels (Aldous, Barrowmere, Bram,
Elowen, Finch, Harrowstone, Hedda, Malverin, Pell, Redcloaks, Redtooth, Sable, Tallow,
Vessk, ...). Any faithful reskin rewrites a large fraction of the 801 labels; under
option 1 this skeleton can never carry a same-tree pair.

### 5.2 Option-2 distances over the committed panel (prototype run, 2026-07-18)

Recomputed all five gating ATG pairs with the option 2 leaf definition (per-node text =
body + choice labels, medial-caps masking over both; brief-declared entities omitted in
the prototype, which only makes these numbers *conservative*):

| Pair | Shipped median / p25 | Option 2 median / p25 | Flagged nodes | Expected verdict | Holds? |
|---|---|---|---|---|---|
| cave-sea~cave-space | 0.848 / 0.815 | 0.822 / 0.786 | 0 | pass | Yes (pass floor 0.60 / 0.45) |
| cave-sea~cave-dino | 0.793 / 0.760 | 0.783 / 0.732 | 0 | pass | Yes |
| cave-space~cave-dino | 0.824 / 0.792 | 0.802 / 0.761 | 0 | pass | Yes |
| cave-space~swap | 0.069 / 0.037 | 0.064 / 0.036 | 64 | fail | Yes (fail ceiling 0.40 / 0.30) |
| cave-space~identical | 0.000 / 0.000 | 0.000 / 0.000 | 64 | fail | Yes |

Genuine pairs dip by 0.010-0.026 in median (identical labels add shared tokens), FAIL
pairs stay pinned at the floor. Margins to the PASS thresholds remain 0.18+ on median
and 0.28+ on p25. Conclusion: option 2 needs a re-baseline (R2 floors, R5 fingerprints)
but **no threshold or expected-verdict changes**, and the R1 human contract is untouched.

## 6. Recommended implementation outline (option 2)

One PR, branch `feat/ws0-labels-are-leaves` (or `fix/` if the owner prefers framing it
as the WS-1 precondition repair). Order matters only in that the baseline regeneration
comes after all code changes.

1. **`src/cyo_adventure/diversity/structure.py`**
   - `_strip_leaf_content`: inside the node loop, iterate `node.get("choices")` and
     `pop("label", None)` on each choice dict. Update the function docstring ("title,
     body, ending title, and choice labels").
   - `structure_fingerprint` docstring: replace the false "the fill contract forbids
     touching anything but bodies" rationale (F2) with: labels are leaf prose the
     automated fill rewrites per theme; two fills of one skeleton hash equal provided
     the fill touches only bodies and labels, which is the shipped `fill.md` contract.
2. **`src/cyo_adventure/diversity/normalize.py`**
   - `extract_entities`: build the scan list from node bodies plus every choice label.
     Docstring notes labels are leaf text for masking purposes.
3. **`src/cyo_adventure/diversity/leaf.py`**
   - `leaf_distance_profile`: replace the `bodies_a`/`bodies_b` maps with per-node leaf
     text maps (`body` + labels in choice order, space-joined) feeding `mask_tokens`,
     `d_uni`, `d_big`. Keep `word_count_a/b` on the body alone; document why.
   - Docstrings on `NodeLeafDistance`/`LeafDistanceProfile`/`anti_template_verdict`
     updated ("leaf text (body plus choice labels)").
4. **`src/cyo_adventure/diversity/aggregate.py`**
   - `_whole_story_token_counts`: update counts from each node's body plus its labels,
     keeping the cross-tree cosine on the same leaf definition.
5. **`scripts/check_fill_integrity.py`**
   - `_strip_bodies` becomes `_strip_leaf_fields`: pop `body` and each choice's
     `label`. Failure message: "differs from skeleton outside node bodies and choice
     labels (ids, choices, targets, endings, variables, or metadata)". Module docstring
     updated to state the aligned convention (labels are leaf content; their
     action-semantic is checked by Stage 1 fidelity, not byte equality).
6. **Tests**
   - `tests/unit/test_diversity_structure.py`: extend
     `test_fingerprint_ignores_titles_and_bodies` to also rewrite every choice label
     (rename accordingly); add
     `test_fingerprint_equal_for_label_rewritten_fill_of_same_skeleton` (load a cave
     fill, rewrite all labels, fingerprints equal; a rewritten `target` still changes
     the fingerprint).
   - `tests/unit/test_diversity_leaf.py`: add
     `test_anti_template_guard_scores_label_rewritten_pair_without_raising` (label-only
     rewrite of the space fill vs the original: no `ValidationError`; verdict FAIL,
     since identical bodies dominate, which is the correct reading of "only the labels
     changed"); add a label-noun-swap case asserting masked label entities contribute
     ~zero distance (extend `_NOUN_SWAPS` application to labels for the variant).
   - `tests/unit/test_diversity_panel.py`: unchanged in logic; it recomputes live values
     and reads the committed baseline, so it passes once step 7 lands. Doctored-baseline
     R-rule tests are unaffected.
   - Optional but cheap: a first test file for `scripts/check_fill_integrity.py`
     (label-rewritten fill passes the structure check; a rewritten `target` fails).
7. **Re-baseline (same PR, after 1-6)**
   - `uv run python scripts/run_diversity_eval.py --update-baseline`; commit
     `tests/data/diversity_panel/baseline.json`. Review the printed deltas against the
     section 5.2 table (all seven fingerprints move; five ATG entries shift by <= ~0.03;
     `struct_pairs` and `brief_pairs` byte-identical). `panel.json` is not touched.
   - Run `test_main_update_baseline_writes_byte_stable_file` locally to confirm byte
     stability held through the change.
8. **Docs (same PR)**
   - `ws0-diversity-metrics-design.md` section 2.4: amend the fingerprint definition
     (labels excluded; correct the F2 claim; fix the F4 "section 3.6" cross-reference).
   - `ws0-phase2-harness-design.md` section 7 risk 1: note the monoculture retirement
     path no longer requires theme-neutral labels.
   - `story-flexibility-plan.md`: WS-1 note that the ATG precondition is now label-free
     and that label action-semantic fidelity is a Stage 1 extension item for WS-1/WS-2.
   - `ws0-label-fingerprint-finding.md`: status `open` to `resolved`, pointing here.
9. **Green bar**: `uv run ruff check .`, `uv run ruff format --check .`,
   `uv run basedpyright src/ tests/`, `uv run pytest` (coverage >= 80%),
   `uv run python scripts/run_diversity_eval.py --check` exiting 0.

**Follow-ups (tracked, not in this PR):**

- Grow the panel: harrowstone cross-tree entry (option 3's safe step, now also a future
  same-tree candidate once a second reskin fill exists), and the supervisor-mandated
  `branch_and_bottleneck` 8-11 same-tree pair, now free of any label-style constraint.
- WS-1: extend the Stage 1 fidelity check to per-choice label intent (the semantic half
  of the label that stays frozen), and handle the ATG `ValidationError` as a
  structure-drift review flag on production pairs.

## 7. The strongest counter-argument, stated fairly

Option 1's best case: *the fingerprint is the only structural identity the system has,
and labels are the only reader-visible text in it; removing them means a fill could ship
801 rewritten labels and the diversity layer would call the two stories "the same tree"
with no independent check that the decisions still mean the same thing.* That concern is
legitimate, but it indicts the wrong mechanism: byte equality never verified meaning (it
cannot tell a typo fix from an inverted choice), no runtime path enforces it today, and
the shipped fill contract already guarantees the bytes diverge. The semantic guarantee
the counter-argument wants is Stage 1's per-beat fidelity check extended to labels,
which works on exactly the artifacts production creates, rather than a hash equality
that production is instructed to break. Keeping labels in the fingerprint buys no
enforcement, forfeits same-tree measurement on the live path, and taxes every future
skeleton's prose. The counter-argument is a good requirement and a bad veto.

---

## 8. Supervisor sign-off (Opus oversight, 2026-07-18)

**Accepted: option 2.** I independently re-ran the section 5.2 load-bearing claim over the
committed panel using the shipped `anti_template_verdict` (folding each node's choice
labels into its body text, which leaves the fingerprint untouched and reuses the exact
shipped distance path). The numbers reproduce to the digit: `cave-sea~cave-space` moves
from median 0.848 / p25 0.815 to **0.822 / 0.786**, delta **-0.026**, still far above the
0.60 / 0.45 PASS floor. The recommendation does not rest on trust; it rests on a number I
reproduced.

Three points I am ratifying or adjusting:

1. **The F1 correction is the crux and it is correct.** None of the three cave fills went
   through the automated `fill.md` path, so the 63/63 evidence never tested production
   label rewrites; option 1 fixes only curated fixtures and leaves the WS-1 gap open. This
   flips my own finding doc's weighting, and I accept the flip.
2. **The WS-1 label-intent fidelity follow-up is REQUIRED, not optional.** Option 2 removes
   the only nominal byte-level check that a fill did not change what a choice *means*. The
   evaluation is right that byte equality never actually verified meaning and nothing
   enforces it at runtime today, so we lose nothing real now. But WS-1 must not wire the
   ATG into the production pipeline until the Stage 1 fidelity reviewer is extended to
   per-choice label intent. I am elevating section 6's second follow-up from "tracked" to
   a hard prerequisite on WS-1's production wiring, and it should be filed as such the day
   the option 2 PR merges.
3. **Fold in option 3 concurrently.** The harrowstone cross-tree panel entry is a free,
   independent win (first non-8-11 gated band, second topology) and should ride the same
   implementation wave, alongside the still-owed `branch_and_bottleneck` same-tree pair,
   which option 2 now unblocks without any label-neutrality constraint.

The re-baseline is safe under the existing authority split: `--update-baseline` cannot
bless an R1/R4 verdict flip (those live in `panel.json`, untouched), and the measured
margins leave every expected verdict intact. Proceed to implementation per the section 6
outline.
