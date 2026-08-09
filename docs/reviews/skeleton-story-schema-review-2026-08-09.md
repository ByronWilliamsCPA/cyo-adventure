# Skeleton, Story-Requirements, and Schema Review (2026-08-09)

**Purpose**: pre-rebuild gate check. Before authoring new stories and rebuilding skeletons, verify
that the skeleton catalog, the story requirements (budgets, validator rules), and the Storybook
schema are consistent and that previously identified issues are actually fixed.

**Method**: every mechanical check in the repo was executed against the live catalog
(`check_skeleton.py` on all 61 skeletons, `check_theme_contract.py` on all 47 contracts,
`check_incell_clones.py --check`, `render_skeleton_diagrams.py --check`, direct JSON Schema
validation of all skeletons, in-memory regeneration of `schema/storybook.schema.json` from the
Pydantic models), and three parallel document audits compared the requirement docs, the validator
implementation, and the open-issue registers (authoring lessons log, unscheduled work register,
story-structure improvement plan, R1 debt register, diversity errata) against the code and data.

## Verdict

The catalog is **mechanically clean**: every automated gate the project defines passes today.
But "all issues fixed" is **not true**. The requirement *documentation* has drifted from the
enforced budgets in ways that would sabotage a rebuild (an author following the reference doc
would hard-fail the gate at band 3-5), the skeleton check tooling silently discards every
advisory the gate produces, and the issue registers carry a large, explicitly tracked open
backlog that a rebuild should either burn down or consciously defer. The details follow, ordered
by what to trust, what to fix before rebuilding, and what to schedule.

## 1. Mechanical state of the catalog: all green

| Check | Result |
| --- | --- |
| Gate (`check_skeleton.py`, blocking layers incl. PL-19/20/21) | 61/61 pass: 58 production-eligible pass clean; the 3 MVP seeds (`the-lost-mitten`, `the-clocktower-cipher`, `the-sunken-signal`) declare no production cell by design and pass with `--allow-mvp` |
| JSON Schema (`schema/storybook.schema.json`, Draft 2020-12) | 61/61 pass, zero violations |
| Theme contracts (`check_theme_contract.py`, all WS-2 acceptance checks incl. denylist bite, residual theme leaks, slot-set equality) | 47/47 pass |
| Slot/contract pairing | consistent: all 14 contract-less skeletons carry zero `{SLOT}` tokens; every slotted skeleton has a contract |
| In-cell clone audit (`check_incell_clones.py --check`, A8) | passes, with **1 allowlisted breach** (see 3.1) |
| Committed schema vs Pydantic models | regenerated in memory, byte-identical: in sync (enforced by `test_committed_schema_is_current`) |
| Generated catalog region + diagrams (`render_skeleton_diagrams.py --check`) | in sync; diagram set matches the catalog 1:1 in both directions |
| `check_lessons_log.py` | ok (all applied rows carry Refs) |

Catalog shape: 61 skeletons (124 files incl. 47 `.contract.json` + 16 `.lineage.json`), all
`schema_version: "2.0"`, spanning 18 production cells across 6 bands; only the 3 seeds set
`production_eligible: false` and omit `length`/`narrative_style`.

## 2. Fix BEFORE rebuilding skeletons (these will corrupt a rebuild)

### 2.1 The authoring reference's word-budget table is wrong (highest impact)

`.claude/skills/cyo-author/reference/skeleton-format.md` ("Per-band prose targets") disagrees
with the enforced source of truth `validator/band_profile.py::words_per_node_profile`, and with
its own sibling `SKILL.md`, whose table is correct:

| Band/style | Enforced (mean, advisory lo-hi, hard max) | Reference doc says |
| --- | --- | --- |
| 3-5 | 40, 28-55, **max 90** | ~75-100 |
| 5-8 | 70, 50-95, max 155 | ~100 |
| 8-11 | 100, 70-135, max 220 | ~125-150 |
| 10-13 | 100, 70-135, max 220 | ~175 |
| 13-16 prose | 140, 100-185, max 310 | ~225 |
| 13-16 gamebook | 65, 45-90, max 145 | not documented |
| 16+ prose | 175, 125-230, max 385 | ~250 |
| 16+ gamebook | 80, 55-110, max 175 | not documented |

Consequences: a 3-5 node authored to the documented target is a **hard gate failure** (PL-19
per-node wall at 90); every other band's documented target sits above the advisory high; the doc
has no `narrative_style` axis at all, so a 16+ gamebook author targeting 250 words faces a hard
max of 175. The `words=` values baked into the catalog skeletons agree with `band_profile.py`,
so the reference doc is the sole outlier. The same doc's reading-level column is in Lexile,
while every skeleton and RL-13 use `flesch_kincaid` targets (3-5: 1.0 through 16+: 8.0-9.0),
and it collapses bands 3-5/5-8 whose FK targets differ by 1.5 grades.

**Fix**: replace the table with `SKILL.md`'s (which matches the code), add the gamebook rows and
the FK column. Consider a small test that parses both markdown tables and asserts them against
`words_per_node_profile` so this cannot regress (nothing checks doc tables today).

### 2.2 `check_skeleton.py` silently discards every gate WARNING

`generation/skeleton.py::load_skeleton` runs `run_gate` and throws the `ValidationReport` away
unless it blocks. `check_skeleton.py` therefore prints `ok` while advisory findings from PL-19
(story mean), PL-20 (arc ceiling), PL-23, PL-24, PL-25, PL-26, L1-7 (below cell min), L2-13,
and RL-13 are dropped on the floor. `run_story_gate.py` prints every finding at every severity.

**Fix**: during the rebuild, gate skeletons with `scripts/run_story_gate.py` (or
`check_skeleton.py --headroom`), or better, surface the report from `load_skeleton`. Otherwise
the rebuild will re-commit skeletons that carry pacing/density/reading-level warnings nobody saw.

### 2.3 `{SLOT}` grammar and theme contracts are absent from the format reference

`skeleton-format.md` never mentions `{SLOT}` tokens, theme contracts, sidecar files, or ADR-019,
even though nearly every production skeleton uses them and `slotted_surfaces.py` pins the three
legal surfaces (beats, ending titles, choice labels). Only `SKILL.md` step 2c touches it,
procedurally. Personalization slots (ADR-023) and the rendered stop flow (ADR-026, single-choice
nodes concatenated into one rendered stop at 8-11+) are likewise undocumented in both authoring
docs, and ADR-026 changes what a `words=` target *means* on screen.

**Fix**: add a slots/contracts section and an ADR-026 note to `skeleton-format.md` before
authoring new skeletons against it.

### 2.4 The in-cell clone pair is still in the catalog (allowlisted, tracked A9)

`the-harrowstone-keep` vs `the-sunken-temple` (13-16/long/gamebook) sit at structural distance
0.00047 against the 0.05 floor; CI passes only because the pair is allowlisted in
`diversity/incell.py` with a "must shrink to zero" contract. SQ-09(b) already prescribes the
fix: restructure `the-sunken-temple` past `TAU_CELL` and empty the allowlist. A rebuild that
does not do this re-ships a known duplication defect.

### 2.5 Validator rule catalog: one contradiction and several wrong statements

`docs/planning/validator-rules.md` needs a cleanup pass before it is used as the rebuild's rule
reference:

- **SR-8 appears twice, contradictorily**: line 216 documents the real, implemented
  carried-variable rule (`series.py`); line 242 still says "RESERVED, not implemented, claimed
  by open PR #416" (that PR merged 2026-07-28). The whole Series section is duplicated
  (two SR-1..SR-7 tables with different wording, two `Series (SR)` semantics rows with
  different blocking answers). The lockstep test only checks catalog-ids vs code-ids, so it
  cannot see this.
- **SAFE-14 is documented as an implemented moderation pass; it is an empty stub**
  (`safety.py::check_safety` returns an empty report unconditionally; `safety_flagged` is
  structurally always `False`; real moderation lives in `moderation/`, which `run_gate` never
  calls). The catalog nowhere says "stub".
- PL-20's arc-ceiling WARNING is missing from all three advisory lists; line 158 wrongly says
  "PL-19 is advisory" (its per-node wall is a blocking ERROR); CG-1's run cap *falls* 3 to 2
  across bands, not "rising"; the Rule Application Order omits L1-8; PL-19/20/21 have no table
  rows or failure templates; the header still says v1.3 / 2026-07-26 despite the CG and CH
  families landing after.
- **PL-22 ID collision**: two live planning docs (`story-diversity-execution-plan.md`,
  `story-diversity-remediation-plan.md` D14) propose a *new* "PL-22 fail-depth floor";
  PL-22 is already taken (band-profile fail-closed). Rename before anyone implements D14.

### 2.6 Choice-grammar rules are inert in production

CG-1..CG-4 exist, are tested, and are documented, but `run_gate` defaults
`enforce_grammar=False` and **no production caller passes True** (checked: orchestrator,
skeleton loader, both gate scripts, parameterize/seed scripts). A green gate says nothing about
ADR-011 §10. This is known (UW-C24, blocked on the D11 `deprecated` marker), but a rebuild
should at minimum run the gate scripts with grammar enforcement locally so new skeletons do not
bake in violations that become blockers when CG flips on.

### 2.7 Architecture doc contradicts itself about the catalog it sits in

`docs/architecture/story-skeletons.md`: line 113 says "Of the 21 catalogued skeletons, 18 are
production-eligible" (actual: 61 and 58); line 279 says "All three skeletons in this catalog are
currently production_eligible: false" (only the 3 seeds are). Both sentences sit *outside* the
generated region, which is correct and in sync; the hand prose around it has no drift check.
Also stale claims that "non-ending bodies carry a FILL directive" (in `skeleton.py`'s docstring
and this doc): **all 2,865 ending nodes carry FILL directives too**; the code is right, the
prose is wrong. The data dictionary omits `series.*`, `safety_scope`, `tags`, `on_enter`,
`effects`, `condition`, and `accepts_character` rows. The documented `role=` closed set
(4 values + ending subtypes) is fiction: 62 distinct role tokens exist in the catalog and
nothing validates them (`diagram.py` recognizes 4 and silently greys the rest).

**Fix**: move the counts inside the generated markers, correct the two sentences, and either
widen the role docs or narrow the vocabulary during the rebuild (the rebuild is exactly the
moment a role convention could be enforced cheaply).

## 3. Known-open backlog that intersects the rebuild (schedule or consciously defer)

These are tracked issues (lessons log: 61 open of 137; UW-C register: 74 open of 79) that a
skeleton rebuild either fixes for free or trips over:

1. **Unparameterized skeletons** (UW-A29/UW-G01): 14 of 61 skeletons, ~4,305 FILL nodes, have
   no theme contract. If rebuilt skeletons are authored parameterized from the start, this is
   the natural moment to close the gap; the 11 stateful Tier-2 migrations (UW-G02) need the
   series-level binding design first.
2. **Fill feasibility** (AL-046/UW-C07, SQ-02/SQ-03): `fill_skeleton` is one-shot with a 32k
   output-token cap; large skeletons (the 746-node class) need ~101k, and selection has no
   feasibility predicate, so an infeasible skeleton burns retries deterministically. Do not
   rebuild skeletons above the one-shot fill envelope until SQ-03 (act-scoped fill) lands, or
   gate size at authoring time.
3. **Promotion-gate asymmetry** (AL-014/UW-C01/UW-G16): hand-authored shells only pass the
   skeleton-promotion CI because it proves changed files; the `origin.json` authored-bundle
   proof path recommended in story-quality-lessons finding A was never built (0 sidecars
   exist). A large hand-authored rebuild wave goes through exactly this gate; decide the
   proof story first.
4. **Beat-consistency defects filed against live skeletons, unregistered**: `the-hollow-lighthouse`
   (route-specific items assumed in shared beats) and `the-signal-in-the-static` (thread leakage
   into merge nodes reachable without setup). Both are open with no register row; fix during
   rebuild.
5. **Estimated-minutes honesty** (AL-022/UW-C11, owner ruled D27 "two clocks" 2026-08-05):
   the schema field `estimated_minutes_whole_world` is ruled but not added. If the rebuild
   touches skeleton metadata anyway, adding the second clock then avoids a second catalog-wide
   touch. Related advisory-only content drift: 13 of 23 committed fills declare
   `estimated_minutes` more than 25% from the derived clock (AL-052).
6. **Legacy corpus quarantine** (AL-050/UW-C14): the three MVP-seed *fills* still use retired
   `ending.type` and omit `metadata.topology`, held under strict xfail. A rebuild should either
   regenerate or retire them; they are the same three skeletons as the `production_eligible:
   false` seeds.
7. **Stat-gate dead end** (AL-129/UW-C64, status `decision`): a stat-envelope book cannot gate a
   choice on `might >= 2` without a blocking L2-11, because `_check_dead_branches` walks only
   the declared-initial baseline with no `accepts_character` awareness. Any rebuilt skeleton
   that wants ADR-028 stat gates is blocked until this is ruled. Related: an archetype build
   node with in-degree 6 silently disqualifies `sorting_hat` topology (AL-127/UW-C62), and the
   CH family proves envelopes are declared and survivable but never *observable*
   (AL-131/UW-C73).
8. **Typical-path length is unconstrained** (AL-027/SQ-19): PL-20 floors only the fastest
   satisfying path; a book can pass every scale rule and hand the median reader a 90-second
   read. If the rebuild is meant to improve felt length, this validator gap means the gate will
   not measure the improvement.
9. **Open owner gates**: OG2, OG3, OG3b, OG4, OG6 in the story-structure improvement plan are
   unruled; all 24 SQ deliverables are undelivered. SQ-13 (variants across all 58 production
   skeletons, ~11k-23k owner-reviewed beats) dwarfs the rest of the plan; sequencing it against
   the rebuild is an owner call. PL-17's gamebook endings-floor question (UW-M06) is also an
   open owner decision.
10. **End-to-end proof debt** (UW-F20): the skeleton-corpus story-generation test plan has an
    entirely empty results table, 0 skeletons proven end-to-end, and 3 unanswered decisions.
    A rebuild without closing this repeats the same untested-corpus state at larger scale.

## 4. Register hygiene findings (bookkeeping, not blocking)

- `ws8-floor-recalibration-proposal.md` still says "PROPOSAL, awaiting owner sign-off" though it
  shipped as ADR-020 Amendment 1 on 2026-07-21 (known, UW-K15).
- UW-G13 (Wave 5) is `unscheduled` though Wave 5 completed 36/36 on 2026-07-18; the row should
  be `done` with its residuals split out.
- AL-120/121/122 are `applied` while their register rows UW-C55/56/57 remain `unscheduled`.
- UW-C01 says "partially closed (PR #532)" while `Status` stays `unscheduled`, and UW-G16
  covers the same finding at status `decision`: two rows, two statuses, one issue.
- Five lessons-log rows (AL-074, AL-102, AL-107, AL-111, AL-116) have unescaped pipes that
  break column alignment for any naive parser; `check_lessons_log.py` does not detect this.
- A cluster of ~10 AL rows (AL-105/107/108/109/112/128/129/132/133/135) describe fixes that
  exist only on the unmerged `feat/persistent-characters*` branches; they are correctly `open`,
  but their prose reads as done.
- `api/schemas.py` still derives `VISIT_SET_MAX_LENGTH` from a hardcoded
  `_MAX_REAL_SKELETON_NODES = 505` while the catalog holds larger skeletons and nothing tests
  the constant against the catalog (AL-024).
- The committed JSON Schema is deliberately weaker than the models (no `schema_version`
  pattern, unconstrained `condition`, no cross-field rules; `schema_export.py` says so), and
  its `schema_version` *default* is "2.1" while all 61 skeletons declare "2.0": legal under
  ADR-025, but a generator seeded from the schema default would emit 2.1 documents.
  `schema/conformance/` has no `accepts_character` case; whether ADR-025 decision 4 requires
  one for minor 1 is an unwritten classification call.
- Stale docstrings inside `validator/` (all listed with line refs in the review transcript):
  `policy.py` claims PL-22 is undocumented and that it runs PL-15..18; `layer1.py` and
  `gate.py` claim pre-CH/L1-8/Layer-2 states. Zero TODO/FIXME markers exist in `validator/`;
  the drift is all in prose.

## 5. Recommended pre-rebuild checklist (condensed)

1. Fix `skeleton-format.md`: word table (copy from `SKILL.md`), gamebook rows, FK reading
   levels, `{SLOT}`/contract section, ADR-026 stop-flow note, role vocabulary decision. (2.1, 2.3, 2.7)
2. Clean `validator-rules.md`: delete the stale SR-8 RESERVED row, merge the duplicate Series
   sections, mark SAFE-14 as a stub, fix the advisory lists and CG-1 direction, add L1-8 to the
   order, bump the header; rename D14's proposed PL-22. (2.5)
3. Make warnings visible in the rebuild loop: use `run_story_gate.py` (and grammar-enforced
   runs) per skeleton, not bare `check_skeleton.py`. (2.2, 2.6)
4. Decide the hand-authored promotion-proof story (origin sidecars or an explicit ruling) before
   the first rebuild PR hits the skeleton-promotion workflow. (3.3)
5. Fold into the rebuild itself: de-clone `the-sunken-temple` (empty the A9 allowlist), fix the
   two beat-consistency skeletons, parameterize the 14 contract-less skeletons, regenerate or
   retire the three legacy MVP fills, respect the one-shot fill envelope until SQ-03. (2.4, 3.1-3.6)
6. Get rulings on the blockers that shape new skeleton design: UW-C64 stat gates, UW-M06
   PL-17 gamebooks, OG2/OG3/OG3b/OG4/OG6. (3.7-3.9)
7. Correct `story-skeletons.md` prose and move live counts inside the generated region. (2.7)

---

## Part 2: Quality improvements for the skeleton rebuild (2026-08-09 follow-up)

Follow-up question: beyond the correctness fixes above, what should change to make the skeletons
*better*? Three probes inform this: a full-gate run in warning-visible mode over all 61 skeletons
(surfacing the advisories `check_skeleton.py` hides), direct structural analysis of the catalog,
and an audit of the quality-focused design docs (kid appeal, reader-path engagement, benchmark
comparison, pathfinder, critical analysis) for recommended-but-unbuilt changes.

## 6. New quantitative findings (this review)

- **40 of 61 skeletons carry at least one hidden gate advisory**: 37 PL-23 clock drifts
  (declared `estimated_minutes` off by 30-125% from the derived fastest-finish clock), 25 PL-24
  ending-mix breaches (7 gamebooks below the 3-distinct-winnable-endings floor), 4 L2-13
  past-hand-authoring-ceiling flags, 2 PL-26 corridor-density flags.
- **A random reader at the teen bands essentially cannot win.** Uniform-random-walk win
  probability (positive-valence ending), by band median: 3-5 100%, 5-8 71%, 8-11 43%,
  10-13 29%, 13-16 **0.3%**, 16+ **1.2%**. Twelve teen gamebooks sit at or below 0.1%;
  negative-valence ending share runs 78-98% (`the-pale-road`: 147 of 150 endings negative).
  Caveats: the walk ignores Tier-2 condition gating (informed readers do better) and counts
  neutral endings as non-wins; gamebook lethality is a declared style. But the spread across
  trees in the same cell is near zero, which is the actual defect (see 7.2).
- **Tier-2 state is largely cosmetic.** Of 14 stateful skeletons, most gate under 5% of choices
  on any variable; the 551-node pair gates 7 of 802 choices (0.9%). Zero variables exist at
  3-5, 5-8, and 8-11. Zero skeletons declare `accepts_character` (the ADR-028 runtime shipped
  with no content behind it).
- **Corridor structure dominates**: 69% of non-ending nodes catalog-wide have exactly one
  choice; 35 of 61 skeletons are over 60% single-choice. ADR-026's stop flow masks this at
  8-11+, but 3-5/5-8 render discrete pages, and the CG rules that would police it are inert.
- **Kid bands have zero genre variety**: all 13 skeletons at 3-5/5-8 are domestic/nature
  realism (baking, mittens, puddles, teddy bears); no dragons, space, dinosaurs, pirates,
  comedy, or gentle-spooky anywhere under 8-11.
- Positive movement not yet reflected in the docs: the ending-valence re-tag (kid-appeal W0.2)
  went further than the plan ledger says: 3-5 and 5-8 now carry **zero** negative endings
  (from 9 and 18); 8-11 is half done (35 remain, 15 of them in
  `the-guild-of-junior-inventors`).

## 7. Ranked quality recommendations

Ordered by expected reader-facing impact. Register/plan IDs given where they exist; items
marked (decision) need an owner ruling first.

1. **Genre-quota the kid-band rebuild wave** (design review §2.1, SQ-23, UW-G13): 4-6
   speculative/adventure/comedy skeletons per kid band before any other catalog growth.
   Authoring only, no schema change, largest felt-variety gain available.
2. **Vary the outcome economy across trees within each gamebook cell** (SQ-21): one 2-win
   gauntlet, one 5-6-win graded-setback tree, one capture-dominant shape per cell, so the
   fail-kind mix (the variable that keys satisfying-path mass) differs between the trees a
   reader alternates across. Finish the 8-11 valence re-tag; fold the teen bands into the
   AL-052 triage. (decision: B1 teen death-ratio policy; PL-24's thresholds were deliberately
   calibrated not to flag the current corpus, so the rule exists but the policy question is
   unruled.)
3. **Make state observable.** Raise gated-choice density in rebuilt Tier-2 skeletons so
   declared variables visibly shape the read (target well above the current 1-5%), and pilot
   one ADR-028 `accepts_character` skeleton at 13-16 medium gamebook (SQ-22 ruled GO).
   Hard blocker first: UW-C64 (L2-11 walks only the declared-initial baseline, so stat-gated
   choices block; status `decision`).
4. **Alternate beat variants** (SQ-11..SQ-14, UW-G12): 2-3 interchangeable beat variants per
   node under a shared outcome contract, selected per fill. This is the frozen-armature fix
   and the prerequisite for ever making the anti-template guard blocking. Needs the SQ-11 ADR
   (gate OG3, unruled).
5. **Constrain the typical path, not just the fastest one** (AL-027, SQ-19): a median-walk
   advisory per cell, plus the PL-17 reshape so the endings floor stops rewarding shallow
   terminal failure leaves (UW-M06, decision). The Wyrmreach book-3 evidence: converting 45
   shallow failure leaves to pass-throughs moved the median read from 5 to 20 pages.
6. **Arm the choice grammar for new skeletons** (UW-C24, blocked on the D11 `deprecated`
   marker; amend D11 with a two-compliant-trees floor per SQ-17 before arming). Run
   grammar-enforced gates locally on every rebuilt skeleton now, so nothing new grandfathers
   in; measure §10 compliance over rendered stops, never nodes (UW-C23).
7. **Honest clocks and celebration metadata**: add the ruled-but-unbuilt
   `estimated_minutes_whole_world` field (D27/AL-022) and fix the 37 PL-23 clock drifts during
   the rebuild; decide B4 (ending rarity / `is_secret` metadata) so the shipped endings
   gallery has something to celebrate, and B5 (a whitelisted `visited(node_id)` predicate) for
   honest hub/open-map design.
8. **Authoring-path parity quick wins** (SQ-04..06, A15/A16): pass `exclude=` and per-job
   seeding to `select_axis` (today a rejected fill re-runs the same axis), make PL-19 report
   distance-from-target instead of band membership, vary the cover-art style clause by band
   (16+ gamebooks currently get "warm, whimsical children's book art"), and surface gate
   warnings in the authoring loop (section 2.2).
9. **Measurement before trust** (SQ-15): add per-path experience metrics (decision cadence
   over stops, corridor ratio, outcome-mix entropy over sampled walks, median-walk depth,
   agency density) to `structure_features` and wire them into selection; current metrics are
   graph-layer and position-blind, and the diversity dashboard peaks under uniform rotation,
   exactly the failure mode it should detect.
10. **Process gates that shape the rebuild itself**: decide the hand-authored promotion proof
    (origin sidecars, B7/UW-G16) before the first rebuild PR; respect the one-shot fill
    envelope until SQ-03 (act-scoped fill) lands; scaffold-interaction affordance at 3-5
    (predict/point/answer beats, needs an ADR-025 minor) instead of forcing plot choices the
    research says hurt pre-readers.

## 8. Sequencing traps (repeated across three docs; keep them)

1. Do not flip the anti-template guard to blocking before beat variants exist; the
   differentiation directive and the depict-this-exact-beat fidelity contract are opposed
   instructions, and blocking first yields retry loops, not diversity.
2. Do not grow the catalog under the current single-model, single-prompt batch process as the
   primary diversity fix; it deepens family resemblance and multiplies slotting/variant debt.
3. Do not read graph-level metrics as reader experience until SQ-15 lands.

Already landed, do not re-schedule: PL-23/24/25/26, CG-1..4 (built, inert), RL-13 FILL-skip,
L2-11 cause hints, `--headroom`, ADR-026 stop flow, humor/wonder variation axes, D14
second-person voice guidance (fill-gate enforcement still missing), the 3-5/5-8 valence
re-tag, ADR-028 runtime + CH rules.

---

## Part 3: Proposed rule set for newly drafted skeletons (2026-08-09 follow-up)

Which *rules* should exist before drafting new skeletons? Principle: grandfather the current
catalog, but hold every newly drafted skeleton to a stricter bar via a `strict`/new-skeleton
mode, so quality is enforced at authoring time instead of discovered at review. Free rule IDs:
the PL family is used through PL-26 (and the D14 plans' proposed second "PL-22" must be renamed,
see 2.5), so new policy rules start at **PL-27**; CG is used through CG-4, CH through CH-8,
L2 through L2-14. Catalog-level (cross-skeleton) checks do not fit the per-story gate and
should live beside the in-cell clone audit; they are marked (cell) below.

### 9.1 Escalate existing advisories to blocking, for new skeletons only

These rules exist, fire on 40 of 61 current skeletons, and are ignored. For newly drafted
skeletons run the gate in a strict mode where they block:

| Rule | Today | New-skeleton mode |
| --- | --- | --- |
| PL-23 clock drift | advisory, 37 breaches | **moot by construction**: derive and stamp `estimated_minutes` at authoring time (`recompute_estimated_minutes` already exists); block on drift so a hand-edit cannot re-break it |
| PL-24 kind-share ceiling + winnability floor | advisory, calibrated below the corpus | block; raise the winnability floor from absolute 3 to `max(3, ceil(0.05 * endings))` pending the B1 ruling, so a 200-ending book cannot pass with 2 wins |
| PL-25 first-decision window, PL-26 corridor density | advisory | block |
| PL-19 story-mean words/node | advisory, reports band membership only | block outside the advisory band **and** report distance from the cell target (story-quality finding D) |
| CG-1..CG-4 choice grammar | built, inert | run with `enforce_grammar=True` for every new skeleton now, without waiting for the D11 `deprecated` marker; measure over rendered stops (UW-C23) |
| L1-7 below-cell-min | warning, silently dropped | visible always (fix `load_skeleton` discarding the report, section 2.2) |

### 9.2 New deterministic rules worth building (ranked)

1. **PL-27 random-walk outcome floor.** Uniform-random-walk probability of a satisfying
   (positive or neutral) ending must clear a band-scaled floor. Cheap to compute (value
   iteration handles loop topologies; this review computed it for all 61 in seconds).
   Suggested starting floors, to be owner-calibrated: 3-5 >= 60%, 5-8 >= 40%, 8-11 >= 25%,
   10-13 >= 15%, teen prose >= 10%, teen gamebook >= 2%. Today's teen gamebooks sit at
   0.0-0.3%; even a 2% floor forces the graded-setback structure the critical analysis asks
   for without banning lethal style.
2. **PL-28 median-walk depth floor** (AL-027/SQ-19). The median uniform-walk read must reach a
   fraction of `min_complete` (suggest >= 50%). Kills the pass-every-rule, 5-page-median shape
   that PL-20 cannot see. Pair with the PL-17 reshape (UW-M06) so the endings floor stops
   rewarding shallow failure leaves.
3. **PL-29 fail-depth floor** (the D14 proposal, renamed; PL-22 is taken). `death`/`capture`
   terminals must sit at >= 33% of `min_complete` depth. Directly kills two-taps-to-death.
4. **PL-30 state-observability floor for Tier-2.** Every declared variable must (a) be written
   by some reachable effect and (b) gate at least one choice, `on_enter`, or ending; and the
   skeleton's gated-choice density must clear a floor (suggest >= 5% of choices; the current
   Tier-2 median is ~3%, the worst 0.9%). Complements AL-131's proposed CH rule for
   envelope-invariant gates (a gate whose outcome is identical across the whole declared
   envelope is dead weight and should flag).
5. **L1-9 role vocabulary.** Close the `role=` namespace: define the canonical enum (the
   catalog's live tokens suggest ~12-15 real roles), validate against it, and make
   `diagram.py` color them. 62 free-form tokens today; a closed set makes beats reviewable
   and diagrams legible.
6. **PL-31 merge-node beat self-containment.** The route-consistency defect class
   (`the-hollow-lighthouse`, `the-signal-in-the-static`): a node reachable from multiple
   routes must not name a `{SLOT}` or proper-noun entity that only some inbound paths
   introduce. Deterministic first cut: for each merge node (indegree >= 2), every slot token
   in its beats must appear on all inbound paths or in the node itself. Heuristic, so ship as
   WARNING; it would have caught both filed defects.
7. **Topology classifier fix, not a new rule** (UW-C62): exempt archetype build nodes from the
   indegree>=2 disqualifier so `sorting_hat` skeletons with a 6-way build node classify
   correctly.

### 9.3 Cell-level rules (catalog audits, promotion-time)

1. **(cell) Outcome-economy spread** (SQ-21): a new tree's ending signature (win count,
   fail-kind mix, negative share) must differ from every existing tree in its cell by a
   minimum delta, exactly as the clone audit enforces structural distance. Prevents adding a
   third 2-win/98%-death maze to a cell that has two.
2. **(cell) Clone floor for hand-authored shells**: fix `check_promotion_bundle.py`'s
   early-return on missing lineage so in-cell distance is proven for every new shell,
   hand-authored or mutated (AL-044/UW-C06); and require the A9 allowlist to shrink, never
   grow.
3. **(cell) Genre/theme spread at the kid bands**: at 3-5/5-8, a new skeleton's theme tags
   must not increase the majority-genre share of its band above a ceiling (say 60%). Today
   the realism share is 100%; a soft cell-level rule makes the genre quota durable instead of
   a one-time authoring push.

### 9.4 Process rules (no code, effective immediately)

1. New skeletons are drafted **parameterized from day 1**: contract sidecar required, slot
   tokens present, `check_theme_contract.py` green, HERO slot declared `personalizable`.
2. Metadata completeness: `length`, `narrative_style`, `topology`, `tier`, stamped
   `estimated_minutes` (and `estimated_minutes_whole_world` once the D27 field exists); no
   new MVP-style cell-less skeletons.
3. Gate every draft with `run_story_gate.py` (warnings visible) plus grammar-enforced runs;
   `check_skeleton.py` alone is insufficient until it surfaces the report.
4. Decide the hand-authored promotion proof (origin sidecars, B7/UW-G16) before the first
   rebuild PR.
5. Stay inside the one-shot fill envelope (~32k output tokens) until SQ-03 lands, and record
   the envelope check in the promotion PR.

### 9.5 Needs an owner ruling before the corresponding rule can bite

UW-M06 (PL-17 on gamebooks), B1 (teen death-ratio policy / PL-24 thresholds), UW-C64 (L2-11
envelope awareness, blocks any stat-gated skeleton), OG3 (beat-variant ADR), B2/UW-G17
(per-band reconvergence targets; a max-indegree advisory could land now, corpus mean max
indegree is 7.79 against the research's 1.5), B4 (`is_secret`/rarity metadata).

---

## Part 4: Recommendations on the four open rulings (2026-08-09 follow-up)

Requested recommendations on the four decisions that shape the rebuild. Each is a
recommendation to the owner, not a ruling; the register rows stay open until ruled.

> **RULED 2026-08-09 (owner)**: R1, R2, and R3 are accepted as written below. R4 is accepted
> with one amendment: the reconvergence constraint is a **hard gate**, not an advisory. The
> owner's stated plan is to remove all non-conforming skeletons and build a new catalog set;
> a robust, high-quality skeleton set is the long-term priority. Implementation status:
> R1's walk floors are ratified in `check_skeleton.py --strict`, PL-24's winnability floor
> now scales as `max(3, ceil(5% of endings))` in `validator/policy.py`, and the cell-level
> outcome-spread audit exists as `scripts/check_outcome_spread.py` (3 breaches at tau 0.10
> in the current catalog, headed by the clone pair at distance 0.0000). R2's depth-qualified
> endings floor and R4's topology-aware max in-degree cap are hard failures in
> `check_skeleton.py --strict` (caps 4/4/6/6/8/8 by band on `branch_and_bottleneck`,
> `gauntlet`, `sorting_hat`, `time_cave`; `open_map` and `loop_and_grow` are exempt because
> hub re-entry is those topologies working as designed, with catalog hub medians of 9 and 5).
> The strict checks stay out of the production gate until the grandfathered catalog is
> removed, at which point they should be promoted into `validator/` with proper rule ids so
> the bar can never regress. R3 (L2-11 envelope awareness plus the AL-131 observability
> companion) is ruled and scheduled for implementation before the ADR-028 pilot skeleton.

### Strict-bar conformance census (2026-08-09, post-ruling)

`check_skeleton.py --strict --allow-mvp` over all 61 catalog skeletons: **2 pass, 59 fail**
(`3-5/puddle-jumping-day`, `3-5/the-big-red-balloon` are the survivors). Failure drivers,
counted per skeleton (most fail on several):

| Driver | Skeletons | Note |
| --- | --- | --- |
| CG-2 options-per-choice bounds | 57 | the grammar was inert since landing, so nothing ever conformed |
| CG-3 words-per-stop ceiling | 48 | same cause |
| PL-23 clock drift | 37 | known from Part 2 |
| PL-24 ending mix | 21 | includes the newly scaled winnability floor |
| Random-walk outcome floor | 11 | concentrated in the teen gamebooks |
| CG-1 choiceless-run cap | 10 | |
| Reconvergence in-degree cap | 7 | the mega-funnels, headed by the clone pair at 31 |
| Depth-qualified endings floor | 2 | |
| PL-26 corridor density | 2 | |

Reading the census: the dominant driver is the choice grammar, which has never been
enforced anywhere, so the catalog predates its own bar; this is the UW-C24 flip cost made
visible, and it grew monotonically while the family sat inert. The strict bar as ruled
therefore implies a near-total rebuild (59 removals), which matches the owner's stated
plan.

**Removal sequencing recommendation**: do not delete the 59 in one pass. The catalog is
live product surface (selection serves it, published books anchor to it, fixtures and the
WS-2 bound trees reference specific slugs), so an empty cell is an outage for that cell's
requests. Remove-on-replacement instead: rebuild cell by cell to the strict bar, land each
replacement wave through the skeleton-promotion gate with its removals in the same PR, and
keep every cell non-empty throughout. Retire the three MVP seeds and the three legacy
quarantined fills in the first wave that touches their bands. Promote the strict checks
into `validator/` (with catalog rule ids) only after the last grandfathered skeleton is
gone.

### R1. Teen death-ratio policy (B1, sets PL-24/walk-floor thresholds)

**Recommend: keep lethal gamebooks legal; regulate the experienced economy, not the census.**
A raw death-count ceiling would ban the genre (real gamebooks are death-heavy and the
corpus was authored to that style). Instead adopt three complementary constraints: (a) the
random-walk satisfying-outcome floor at 2% for teen gamebooks (now live in
`check_skeleton.py --strict`, pending this calibration ruling); (b) PL-24's winnability
floor scaled to `max(3, 5% of endings)` instead of the absolute 3 that the corpus was
calibrated to clear; (c) the cell-level outcome-spread audit (9.3.1), so each gamebook cell
holds at least one graded-setback tree alongside the punishing ones. Rationale: the defect
the data shows is not "too many deaths" but "every tree in the cell has the same 2-wins
shape and a random reader wins with p < 0.003"; the walk floor and the spread rule target
exactly that while leaving a deliberately brutal tree legal in a cell that also offers
mercy. Pair with the fail-depth floor (9.2.3) so the deaths that remain are earned.

### R2. PL-17 endings floor on gamebooks (UW-M06)

**Recommend: keep PL-17 for gamebooks, but count only depth-qualified endings.** Do not
exempt gamebooks (the floor protects real breadth), and do not keep the current form (the
AL-026 evidence shows it actively rewards minting shallow terminal failure leaves: the
746-node book satisfied its floor with 7 endings within two taps of the start). Change the
floor's counting rule: an ending counts toward PL-17 only if its depth is at least the
fail-depth floor (33% of `min_complete`, the same threshold as 9.2.3). This preserves the
breadth incentive, deletes the shallow-leaf incentive, and needs no new threshold. Existing
catalog books that lean on shallow leaves are grandfathered the same way as every other
strict-mode rule.

### R3. L2-11 envelope awareness (UW-C64, blocks stat-gated skeletons)

**Recommend: rule now, implement before the ADR-028 pilot skeleton.** Make
`_check_dead_branches` walk the declared `accepts_character` entry states in addition to
the declared-initial baseline, and flag a branch dead only when it is dead under EVERY
admissible entry state; cost is bounded because CH-8 already caps the configuration space
and `validator/character.py` already performs the per-state walk this needs. Add the
AL-131 companion at the same time: a gate whose truth is invariant across the whole
declared envelope is dead weight and should flag (this is the observability rule the
withdrawn pilots both needed). Without this ruling the SQ-22 GO is unexecutable: no
stat-envelope skeleton can gate a choice on a stat without a blocking L2-11, so the pilot
would be forced into the XOR workaround that AL-129 documents as the wrong shape.

### R4. Per-band reconvergence targets (B2/UW-G17)

**Recommend: advisory now, no hard gate; amend ADR-011 only after measured data.** The
research anchor is contested (the corpus refutes the JHM leaf-reconvergence model: 54 of
61 skeletons have every ending at indegree 1, and reconvergence concentrates at internal
bottlenecks), so a magnitude gate would be calibrated against a model the catalog does not
follow. Land two cheap things now: a per-band max-indegree WARNING (suggest flag above 4
at 3-5/5-8, above 6 at 8-11/10-13, above 8 at the teen bands; corpus mean max indegree is
7.79) so extreme funnels surface during drafting, and `reconvergence_ratio` plus agency
density in the SQ-15 per-path metrics so selection can see the felt effect. Defer the real
target to after the naive-user session (UW-M02) answers whether children detect
reconvergence on replay; that is the only measurement that can justify a blocking number.
Retire or populate `BandProfile.reconvergence_ceiling` as part of the same amendment; a
declared-but-unset field that only the mutation engine reads misleads (AL-082).

---

## Part 5: Strict-bar drafting pilot with adversarial review (2026-08-09 follow-up)

Owner-directed pilot: three cells, one attempted strict-compliant draft each, then an
independent adversarial critique of every draft. Purpose: prove or refute that the ruled bar
is drafttable, and harvest lessons before the rebuild wave. Drafts and generators live in the
session scratchpad (`strict-pilot/`); they are pilot evidence, not catalog candidates, and all
three were rejected on review (below), so none is committed.

### Results

| Cell | Draft | Gate result | Adversarial verdict |
| --- | --- | --- | --- |
| 3-5 / short / prose (time_cave, space theme) | "The Baby Star Goes Home", 15 nodes, 4 endings | strict PASS, first checker run, walk 100% | **REJECT** |
| 10-13 / medium / prose (branch_and_bottleneck) | "The Storm Courier's Run", 184 nodes, 64 endings | strict PASS, zero findings any severity, walk 38.2% | **REJECT** |
| 13-16 / medium / gamebook (gauntlet) | "The Window on Cerridane Spire", 251 nodes, 67 endings | strict PASS, zero findings, walk 25.6%, P(win) 0.5%, all deaths telegraphed | **REJECT** |

Two headline facts coexist and are both load-bearing:

1. **The ruled bar is drafttable, including the hardest cell.** The teen gamebook landed the
   "few wins but fair" economy the rulings demand (25.6% satisfying, 0.5% outright wins,
   deaths behind telegraphed recklessness), and the outcome-spread and clone audits both pass
   it with real margin against its cell-mates. The drafters' shared method: replicate the
   strict rule set inside a small structural generator and author beats as data; both
   large-cell drafters independently concluded a hand-author cannot hold the coupled global
   constraints at 180+ nodes, so the rebuild should ship that harness as a first-class
   authoring aid rather than expect ad-hoc copies.
2. **Strict-clean does not mean approvable.** All three drafts passed with zero findings; all
   three failed adversarial review on defects the gate cannot see.

### Convergent defect classes (found independently in 2-3 drafts each)

1. **Label laundering.** The outcome gates read kind/valence tags, not outcomes. The 3-5
   draft's four endings narrate one identical scene under four tag combinations; the 10-13
   draft tags mission success neutral and failures discovery; the 13-16 draft has 16
   everyone-survives rescues tagged negative-setback and 12 abandonments tagged neutral. The
   headline economies that passed PL-24, the walk floor, and the spread audit are tag
   artifacts in all three.
2. **Choice-position fate bias.** In the 10-13 draft the third option leads to an ending 77%
   of the time (position 1: never); in the 13-16 draft always-pick-option-1 walks straight to
   the best ending with zero risk. Generators order options safe-first unless forced not to;
   a pattern-spotting reader solves the book without reading it.
3. **Funnel laundering and consequence-free choices.** Staged merges satisfy the in-degree
   cap's letter while collapsing 98 ancestors into one node; 25 decision nodes in the 10-13
   draft have sibling choices with byte-identical reachable-ending sets; the 13-16 draft's 8
   soft decisions are 24 flavor-only choices. The cap constrains the diagram, not the
   experience.
4. **Merge-node beat contradictions at scale.** 8 hard upstream-vs-beat contradictions in
   each large draft (endings narrating scenes from choices the reader declined, characters
   known only on other routes, gear appearing from nowhere, a beat hedging "whichever
   stranger you trusted" because the generator knew its parents disagreed). This is the
   known beat-consistency defect class (`the-hollow-lighthouse`) reproduced systematically
   by generation.
5. **Quota-shaped design.** The endings-fraction floor makes terminal leaves the cheapest
   padding (64 endings against a floor of 28); terminal-discovery endings punish the genre's
   core verb on a coin-flip; composed stops emitted at 148-150 of the 150-word cap leave
   zero fill headroom; a declared storm-clock premise has no structural clock, so merged
   paths break the timeline arithmetically.

### What this ruling means for the rebuild workflow

The drafting loop for wave 1 must be: generated brief from `band_profile.py` (the pilot's own
briefs drifted from code twice), structural harness draft, `check_skeleton.py --strict`, the
catalog audits run with the candidate placed in its target cell (`check_incell_clones.py`,
`check_outcome_spread.py`), and a mandatory adversarial critique stage before any promotion
PR. Strict must additionally gate parameterization (a slotless `production_eligible` shell
currently exits 0 and would take the legacy free-text fill path in matching). The
next-generation checks the critiques specify, in priority order: tag-vs-beat honesty audit,
positional fate-bias check with seeded option shuffling, sibling reachable-ending-overlap and
k-hop funnel metrics, merge-node beat-presupposition linting, and a near-cap headroom
warning. Lessons AL-142 through AL-150 carry these with proposed changes and register homes.

---

## Part 6: Same-skeleton diversity experiment (2026-08-09 follow-up)

Owner question: do skeletons define story content or just routes, and how similar are stories
generated from one skeleton? Method: the smallest catalog skeleton (`the-lost-mitten`, 11
nodes, 16 contract slots) was bound to three maximally different themes simulating three
family requests (raccoon kit / orange knit cap / autumn park; otter pup / yellow sunhat /
beach; baby dragon / green scarf / clover meadow), then filled by three isolated authors with
no shared context. All three fills passed `check_fill_integrity.py` first try. Similarity was
measured with the project's own WS-0 instruments plus an independent qualitative evaluation.

### Answer to the first question

Skeletons define the story, not the routes. Every node body is a `<<FILL>>` directive whose
`beats=` fixes the scene at sentence granularity ("a single {ITEM_COLOR} thread is caught on
a twig pointing toward the {MEETING_PLACE}"); the theme contract's 16 slots are all nouns.
The fill authors control register, sound-play, and sensory texture, nothing else. The pilot
drafts in Part 5 have the same property, and the 3-5 pilot critique found its beats were
effectively finished prose.

### Quantitative result

Pairwise `perceived_similarity` (PS = 0.5 leaf + 0.3 structural + 0.2 theme; repeat
threshold 0.70): 0.602, 0.600, 0.591. All three pairs read "distinct" by the metric, but the
decomposition shows why that is fragile: leaf similarity is 0.18-0.20 (the prose is close to
maximally different for identical beats; body trigram Jaccard 0.026-0.029), while structural
similarity is 1.0 by construction and theme similarity is 1.0 because binding never re-themes
`metadata.themes` (all three books carry `['friendship', 'winter', 'problem-solving']`,
including "winter" on the beach book). A same-skeleton pair therefore has a PS floor of 0.50
before a word of prose exists; best-case theming and independent authorship bought 0.09-0.10
of the 0.20 gap to the repeat line. Fill quality is not the bottleneck; slot granularity is.

### Qualitative result

Verdict: **one story, three costumes** (1.5 on a 5-point scale toward "three real stories").
The invariant layer is total beyond nouns: the same three search strategies in the same order
with near-identical labels, the same three clue mechanics (footprints, heard-it-by-the-water,
thread-on-a-twig, with "But wait!" opening the clue in all three), the same sensory triad at
the reconvergence, the same wobbly-tower gag, the same footwear punchline ("tumbled out and
rolled across the floor" string-identical in two books), two of three ending titles
string-identical. The kid test: a 4-year-old recognizes the story at the first choice menu of
book two and calls the twist before it lands; that is tolerable and even pleasant at 3-5
(prediction is mastery) IF framed as a series, but as three distinctly-titled books it is a
trust problem for the paying parent ("the generator has one story"). Craft in all three fills
was genuinely independent and good; it changes how sentences sound, not what happens.

### Defects the experiment surfaced

1. **Binding leaves `metadata.themes` stale**: "winter" ships on a beach book. This is
   kid/guardian-facing metadata, it feeds the PS theme axis (pinning 0.20 of similarity),
   and it feeds matching.
2. **Beats encode un-slotted world facts** (snow, a cold *hand* implying a hand-worn item,
   helpers who *chirp*), and the fill contract's reskin-the-setting rule is ambiguous: the
   three authors resolved the same conflict three ways (imported snow into autumn; reskinned
   snow to dew; inverted cold-hand to hot-head for a sunhat). One binding produced "fireflies
   chirped", a world-consistency defect no gate catches.
3. **A lexical similarity gate passes beat-identical triples** (trigram Jaccard 0.03 while
   beat overlap is 100%). The family-scoped anti-repeat guard needs a structural signal
   (skeleton id + beat-variant fingerprint), not prose similarity.
4. The seed's `words=80/85` directives contradict the current 3-5 envelope (mean 28-55):
   stale pre-recalibration targets on an MVP seed, resolved by both fillers in favor of the
   band envelope.

### What to change in the skeleton approach

The skeleton layer itself (topology, validation, safety, budgets) is not the problem and
should stay. The **beat layer must become variable**, which is exactly SQ-11/OG3 (beat
variants), now with direct experimental evidence:

1. **Variant beat pools on high-salience nodes** (minimum viable: the three clue mechanics,
   the twist ending, the helper gag): 3-6 interchangeable beats per pooled node sharing an
   outcome contract, drawn per binding. Moves the verdict from ~1.5 to ~2.5 ("recognizably
   siblings, each with its own trick") at roughly 2-3x beat-authoring cost on 4 of 11 nodes,
   with zero topology/validator/player changes.
2. **Family-scoped variant memory** in the request-time guard: never serve the same
   skeleton+variant fingerprint twice to one family. Cheapest single intervention; pure
   policy; ship regardless.
3. **Honest series framing** in the product for same-skeleton siblings (covers, titles,
   "another Momo adventure"): converts the sameness kids tolerate into a feature and removes
   the parent-trust failure at zero authoring cost.
4. For true "three real stories": structurally distinct siblings via the `mutation/` engine
   (ADR-020), which exists for exactly this, at catalog-time curation cost.

Lessons AL-151..AL-153 (UW-C88..UW-C90) carry the defects and proposals.

---

## Part 7: The hand-authoring constraint, in detail (2026-08-09 follow-up)

Owner asked to revisit the pilot finding that hand-authors cannot hit the strict bar at
scale. Precisely what was found, and the options.

### What the constraint is

Both large-cell pilot drafters, working independently, concluded that no hand-author
produces a strict-passing 140+ node skeleton in reasonable iterations, because the strict
bar is a set of GLOBAL, mutually coupled invariants rather than local rules:

- CG-2: every decision node needs an exact option count ((3,3) at 8-13), across 100+
  decisions;
- CG-3: a node's word budget is entangled with its successors (single-choice chains
  compose into stops with a shared ceiling), so editing one node re-opens its neighbors;
- the endings floor scales with node count, so adding ANY node can demand another ending,
  which shifts PL-24's kind shares;
- depth-qualified endings: every counted ending needs BFS depth at least a third of the
  arc floor;
- the in-degree cap must hold at every merge, counting parallel edges;
- the story words mean must land in the advisory band while individual nodes are being
  bent for CG-3;
- PL-23's clock, the walk-outcome floor, and PL-26's density are whole-graph computations.

Any local edit ripples globally: this is a constraint-satisfaction problem wearing a
writing problem's clothes. Empirical anchors: `the-hollow-lighthouse`, a carefully
hand-authored catalog skeleton, fails strict on 20 CG-3 findings alone; the only one-shot
strict passes ever produced (the two large pilot drafts) came from generators that embedded
the whole rule set; and the 15-node 3-5 pilot WAS hand-written and passed first try. The
feasibility boundary is scale: roughly 25 nodes and below is comfortably hand-draftable,
140+ is not.

### What the constraint is NOT

It does not remove human authorship of content. The pilot's working division of labor keeps
world, beats, choice labels, per-branch strategy, and outcome design fully hand-authored as
data; a ~100-line structural harness owns the arithmetic (node counts, stop composition,
depths, in-degrees, clocks). It also does not interact with promotion provenance: a
harness-assisted skeleton is still "hand-authored" for the origin-proof question (B7/UW-G16).
Related but distinct: L2-13's 460-node ceiling is about hand-REVIEW (past it, the Layer-2
walk is the sole correctness guarantee), and binds generator output equally.

### Options, with a recommendation

1. **Accept and institutionalize** (recommended default): ship the pilot harness as a
   first-class authoring tool (UW-C80); "hand-authoring" means authoring the creative layer.
2. **Relax the couplings** (UW-C85 calibration review): CG-2 widened to (2,3), a CG-3
   terminal-node exemption, endings floor keyed to outcome identities. This meaningfully
   widens the hand-feasible envelope at small/medium cells and reduces template pressure for
   everyone, but 245-node gamebook cells remain generator territory under any plausible
   calibration.
3. **Live incremental linting** (editor/watch mode over `check_skeleton --strict`): reduces
   the cost of each iteration rather than the number of coupled constraints; cheap, worth
   having, insufficient alone at scale.
4. **Reserve the pure-hand path for the small cells** (3-5, 5-8), where it demonstrably
   works and where craft density matters most per node.

Recommendation: 1 + 4 now, with 2 decided in the UW-C85 calibration review before wave 1.

---

## Part 8: UW-C85 calibration review, expanded scope (2026-08-09 follow-up)

Owner directed implementation of the hand-authoring recommendations and asked whether other
adjustments belong in the UW-C85 calibration revision. Framing principle for every item,
per the owner's steer that the goal is high-quality LLM-GENERATED stories with few
hand-authored ones: a constraint earns its place by improving the reader's experience, not
by being satisfiable; a constraint that merely forces authoring-agent contortions (harness
tricks, padding, tag gymnastics) without a reader-visible payoff is a defect. The original
six UW-C85 items plus six additions surfaced by the pilot, the critiques, and the diversity
experiment:

| # | Constraint | Problem | Recommendation |
| --- | --- | --- | --- |
| 1 | CG-2 exact (3,3) at 8-11/10-13 | Bans the binary dilemma; forces a third strategy at every one of 100+ decisions, the origin of template pressure | Widen to (2,3); adopt |
| 2 | CG-3 stop ceiling vs word means | Ceiling equals ~2-3 nodes at the band mean; corridors near-illegal; pilot stops emitted at 148-150 of 150 | Exempt ending-terminal stops from composition (a scroll INTO an ending has no decision fatigue to protect); keep for decision-terminal stops; adopt |
| 3 | Gamebook endings fraction 0.25 | Terminal leaves become the only legal padding; 67 distinct endings was the largest single authoring cost | Lower toward 0.20; adopt |
| 4 | PL-26 gamebook ceiling 4.0 | Unmotivated by its own comment, strict-blocking, forces the soft-decision fan idiom | Keep strict-only; re-anchor from the rebuilt corpus after wave 1 (interim 5.0 acceptable) |
| 5 | PL-24 kind-share 60% at small n | Quantizes harshly at <= 4 endings; silently raises the kid-cell endings floor (a 3-ending book needs all-distinct kinds) | Exempt totals <= 4 from the share ceiling; adopt |
| 6 | Cap headroom discipline | Zero-headroom drafts are unfillable in practice | Generators target <= 90% of any hard cap; strict warns at >= 98%; adopt (new check) |
| 7 | PL-23's 200-word no-op floor | Two similar small skeletons silently get different effective rule sets; the author is never told which regime applies | Drop the no-op floor (the derived clock now prints unconditionally), or print the regime; adopt drop |
| 8 | Depth-qualified endings, zero shallow allowance | Bans the telegraphed page-2 gotcha outright rather than discounting it; the 13-16 pilot needed a pre-ending linker trick | Allow one shallow ending per book exempt from qualification; adopt |
| 9 | In-degree cap counts parallel edges | A 3-option soft-decision fan spends 3 of the cap on arrival; drafters chain continues through each other, creating the runs item 2 penalizes | Count distinct predecessor NODES for the cap; leave funnel INTENT to UW-C82's k-hop and sibling-consequence metrics |
| 10 | Kid-band walk floors (60/40%) | Measure almost nothing at 3-5 (band policy already forces ~100%) | Keep as cheap backstops; no change |
| 11 | CG-1 run cap 6 at gamebook cells | Dead letter: CG-3 makes runs of 2-6 unusable anyway | Leave until stop-based measurement (UW-C23) lands; no change |
| 12 | PL-25 window vs ADR-011's "2-3 node" prose | Code anchors on JHM 2019 (windows to 9-10 nodes); the ADR text was never annotated as superseded | Annotate ADR-011 section 6; keep the code values |

Items 1-3, 5-9 change what compliant skeletons look like and should be ruled before rebuild
wave 1; items 4, 10-12 are documentation or post-wave recalibration. Also implemented with
this revision (the hand-authoring recommendations, re-scoped for LLM authoring per the
owner's steer): `scripts/generate_drafting_brief.py` emits the full per-cell constraint set
from the enforced sources (AL-149 applied; hand-copied briefs drifted twice during the
pilot), and `skeleton-format.md` now carries the corrected word table, the strict-bar
section, and the `{SLOT}`/contract grammar. The pure-hand drafting path receives no further
tooling investment; the strict-bar reference and brief generator serve the LLM authoring
agents that are the catalog's actual production path.
