# B2: claim-by-claim verification against the research branch

VERIFIED (terse; ~40 claims reproduced exactly from committed evidence)
- generate_drafting_brief.py reads live from validator/band_profile.py, choice_grammar.py, policy.py, check_skeleton.py.
- check_skeleton.py --strict: layer-1 budgets, walk floor per band, max in-degree cap, depth-qualified endings floor, grammar under strict.
- Rule IDs all exist: PL-18 (policy.py:616-625), PL-29 (634), PL-19/23/24 (1282,1191), PL-25/26 (band_profile.py:117,511), CG-1 (choice_grammar.py:353-394), CG-3 (221).
- TAU_CELL = 0.05 (ws5_floor_baseline.json; mutation/floors.py:65; diversity/incell.py).
- check_graph_structure.py: exactly six deterministic failure classes plus repairability.
- mutate_skeleton.py, parameterize_skeleton.py, bind_theme.py, run_story_gate.py, blind_books.py, judge_books.py, check_prose_craft.py all exist.
- skeleton-promotion.yml re-proves changed skeletons via check_promotion_bundle.py, with derived-artifact and no-auto-merge guards.
- skeleton_match.py: production-eligibility filter, recency-blended weighting, admin override with non-blocking warnings.
- build_differentiation_directive exists, used by the production worker.
- fill_skeleton: chunked fills, per-model caps (MODEL_OUTPUT_CAPS), bounded repair; usage metering response-level.
- fidelity.py stage-1 pure-code gate inside the repair loop.
- check_fill_integrity floor 0.6 calibrated 2026-08-20 so the 0.389-0.529 books fail; check_sibling_fills default budget 4.0/1000; sibling wiring open per UW-C315.
- 38.9-52.9% delivery (AL-490/UW-C307); 96.3/1000 = 24x budget (AL-498/UW-C315, 1,350 shared 4-grams).
- Blind S-1 2/21 recounted from records; 6-round and 10-invocation caps per register.
- 4.2 table per-leg pass counts match e1r3-tools records exactly for both cells.
- 76 of 80 e1 records error "openrouter returned leg-fatal HTTP 402"; 20-45k censored completion tokens per register.
- $1.30 both DeepSeek legs and "90% of spend": test plan lines 507-508 (owner prose).
- Register rows S-0..S-5 exist; S-0 done FAILED validation (control fired both raters at 12 and 41); S-2..S-5 open/blocked.
- D-3 inverted; D-4 positive on taxonomy-free tier only; D-6 confirmed; D-7 13.6; D-7b 2.3/1000 from removing 422 gloss words (13.6 -> 2.3).
- S3/S5/S6/S7/S8/S9 as summarized (08-10 brief); withholding vs instructing (register:688); Q-1 verbatim; Q-3c per evidence.
- Six-question instrument compressed/pinned; fp4 headline one bad book (run-6); "six legs five labs, allow_fallbacks false" per README (but see finding 1 in C2: measured slate was 8 legs/6 labs).
- AL-328, AL-490..503, UW-C306/307/315/316..319 exist and carry what the brief attributes; --resume/preflight/sized caps are real code.
- Moderation V4 Flash correctly labeled owner practice: no deepseek in moderation/ or config (defaults: review_provider "mock", review model anthropic/claude-sonnet-4.6).
- 677-node largest graph at 16+ confirmed; ~800-word 3-5 books plausible (smallest 674-890 commissioned words).

FINDINGS

1. [CRITICAL] [4.1, F4] "Best judged prose" contradicts the cited evidence.
The blind cross-lab judging ranks V4 Pro FIFTH of eight at -0.13, behind sonnet-5 +0.69, grok-4.6 +0.61, gpt-5.6-sol +0.38, sonnet-4.6 +0.14; 08-10 sections 30-31 conclude grok-4.6 is "close to dominant" while V4 Pro "gives up 0.74 of judged quality" for being 4.9x cheaper. No later artifact says V4 Pro won a judged panel; the only "best judged" language in docs/ is about grok. The cost half ("a fifth") matches only the grok comparison. 4.2's product consequence and F4 are built on the quality half.
Recommendation: restate as "cheapest leg within tolerable judged-quality loss" with the actual -0.13/4.9x numbers, or produce and cite the judged run that flipped the ranking.

2. [HIGH] [1, 4.3] Catalog numbers are stale or wrong: 84 graphs and 15,470 nodes, not 61 and 11,458.
Recounting skeletons/*/ (excluding sidecars) gives 84 shells / 15,470 nodes in both trees. 61/11,458 is copied verbatim from the 08-10 brief; the catalog grew 14 books on 2026-08-19 alone (AL-476); generation/skeleton.py already says "62 production skeletons" as of 2026-08-16. "A 677-node, ~118,000-word graph" is unsupported: the-tenfold-siege's words= directives sum to 42,233 (62.4 words/node); ~118,000 appears to be 677 x the 08-10 brief's ~175 figure, an arithmetic artifact. Q-1's "3-4 skeletons per cell" is stale: production-eligible shells now run 4-10 per covered cell (81 eligible).
Recommendation: recount at publication time (one script run); re-derive the Q-1 exhaustion arithmetic.

3. [HIGH] [F3, 4.2] Tool-assisted ages 5-8 is 12/21, not 14/21, and the 10-13 cell was not "swept".
Records: cell A passes fable 3, opus 3, haiku 2, kimi 2, sonnet 1, v4-flash 1, v4-pro 0 = 12/21; the brief's own table sums to 12, so the document contradicts itself; the error originates in the register's S-1 row, whose "tool-assisted 14/21" headline disagrees with its own breakdown (11/15 + 1 + 0). Cell D not swept: haiku 1/3, v4-pro 0/3, v4-flash 1 pass 1 fail on record (brief says "in flight"). Only fable/opus/sonnet/kimi swept D. F7's "Haiku authored passing hard-band shells" is one shell. The register's S-1 row still ends "Cell D remains open", so the brief's D column (incl. checker-run ranges appearing in no committed record) is ahead of its named register source.
Recommendation: correct to 12/21; name the four legs that swept D; land the register update the D column depends on.

4. [HIGH] [3.4, F2] check_fill_integrity is an offline script, not a pipeline enforcement point.
3.4 lists it as a stage of "the current pipeline", flagging only check_sibling_fills as unwired, implying fill-rate enforcement is wired. It is not: no src/ module, workflow, or pre-commit hook invokes it; UW-C307's status says "Still open: whether the deterministic gate carries the check". The request path enforces only the per-node +-40% tolerance in fidelity.py ("a generous starting tolerance, not calibrated"). F2's "every gate is paired with a delivery measurement" is aspiration for the production path.
Recommendation: state that the floor is currently a manual post-run check, or wire it and close UW-C307.

5. [MEDIUM] [4.5] The per-leg dollar figures have no committed artifact; "deterministic accounting from run records" overstates their class.
Sonnet 5 $4.43 / Gemini $3.52 / GPT-5.6-sol $3.38 appear nowhere in the repo except this brief; e1 records carry token counts and no cost fields (verified programmatically); the evidence README quotes only "$400.92 used of $400.00". The $1.30 and "90%" trace to prose in the test plan section 10 (owner-reported billing). By the brief's own rule these are unclassed. The premium spend did buy one strict pass (Gemini, smoke2, analysis-excluded), so "for no additional passes" needs the exclusion stated.
Recommendation: commit the provider billing export next to the run, or relabel "owner billing records, 2026-08-21".

6. [MEDIUM] [3.2] The anti-clone check is not part of check_skeleton --strict, and TAU_CELL is owner-chosen, not calibrated.
check_skeleton.py contains no structural_distance or TAU code; the check lives in scripts/check_incell_clones.py over diversity/incell.py, and in CI promotion the anti-clone leg is explicitly skipped for hand-authored originals. A hand-authored shell can clear "the authoring bar" as described without ever being distance-checked unless someone runs the separate audit. ws5_floor_baseline.json's own derivation calls tau_cell an "owner-chosen fixed anti-duplication floor"; the calibrated quantity is tau_struct (0.298), documentation-only.
Recommendation: name check_incell_clones.py in the bullet; state the hand-authored-original skip; say "committed", not "calibrated", for 0.05.

7. [MEDIUM] [3.1, 3.5] Cited lesson IDs AL-149, AL-207, AL-226 do not carry the lessons attributed to them.
In the current log, AL-149 is choice-fairness; AL-207 is locked_outcome twists; AL-226 is --strict passing 2 of 61 catalog skeletons. The drift lesson lives at AL-153 (duplicated at AL-199: "both pilot briefs drifted... mis-stated PL-26"); the provenance lessons at AL-274/AL-276 ("Blinding renamed the files and left the provenance inside them", Ref: scripts/blind_books.py). The log evidently renumbered (identical rows at AL-152/AL-198, AL-153/AL-199, AL-179/AL-225; AL-276's cross-reference to "AL-257" also shifted); stale IDs are baked into code docstrings which the brief copied. Facts real; pointers dead.
Recommendation: fix the log's duplicated/renumbered block once, then sweep AL cross-references in scripts and briefs; itself a lessons-log-worthy tooling defect.

8. [LOW] [4.5, F7] "Credits checks" names a guard that does not exist as such.
--resume, preflight micro-completions, and sized caps are real. No code queries a credits/balance endpoint; actual protection is 402 classified leg-fatal so legs die fast and --resume recovers. A preflight pass does not prove the balance covers an 18-shell grid, which is exactly how e1 died 4 shells in.
Recommendation: add a real credits preflight (OpenRouter exposes one) or drop the phrase.

9. [LOW] [3.5, F4] The V4-Flash first-pass-review claim is honestly labeled but evidence-free, and its placement invites over-reading.
Config: review_provider defaults "mock"; the OpenRouter review model default is anthropic/claude-sonnet-4.6; "deepseek" appears nowhere in moderation/ or config. The brief says "owner practice, 2026-08" (accurate), but by F6's standard it is uninstrumented with no artifact ("performs well" against what baseline?).
Recommendation: keep the label; move the sentence out of the pipeline enumeration or mark it non-wired; let the distillation eval produce the number.

10. [LOW] [3.3] Small mechanism overstatements in selection/binding.
"Picks... so a family sees the least recently used armature": skeleton_match implements inverse-frequency weighted RANDOM pick blending recency and theme reuse: favored, not guaranteed. "parameterize_skeleton.py lifts a skeleton into a theme contract": the script applies an agent-authored slotting plan; contract emission is a sibling step (parameterize_promotion.py).
Recommendation: "weights selection toward the least recently used"; "applies a slotting plan (the step that makes a skeleton contract-bindable)".

Strengths
- Near-total artifact traceability: of ~40 checkable claims, the tooling, rule IDs, register rows, UW/AL rows for the 08-20/21 cycle, and the headline numbers (2/21, 38.9-52.9%, 96.3, 2.3 vs 4.0 vs 3.3, 422 words, 76 x HTTP 402) all reproduce exactly.
- Evidence-class discipline is mostly practiced, not just declared: negative results (S-0 failure, D-3 inversion, S8 refutation, fp4 non-effect) are reported against the programme's interests.
- Honest flagging of open wiring (UW-C315) and the weak rater class shows the register, not the narrative, is the source of truth in most places.

Top 3
1. Fix or substantiate the F4/4.1 "best judged prose" claim: cited evidence ranks V4 Pro fifth of eight; the per-stage product recommendation rests on an inversion of the data.
2. Re-measure the catalog paragraph (84 graphs / 15,470 nodes / ~42k-word largest) and the S-1 pass arithmetic (12/21, no D sweep): copied-forward numbers a one-line script would have caught.
3. State plainly that the fill-rate floor and sibling-gram budget are offline scripts today, or wire them into the gate; F2's central anti-hollow-pass claim is not yet true in the request path.
