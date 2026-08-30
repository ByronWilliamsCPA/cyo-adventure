# Evidence: gap analysis of the 2026-08-22 generation research brief

Raw reports behind
[cyo-brief-gap-analysis-2026-08-22.md](../../cyo-brief-gap-analysis-2026-08-22.md). Preserved as
written, including the parts the synthesis retracted, because the retractions are the most
instructive output of the exercise. The only edits made when these were landed on `main` are
additive and dated: the correction notices described in the next section, the `AL-*` renumbering it
records, and the removal of em-dash characters, which this repository does not permit.

## Supersession and reproducibility, 2026-08-30

**Read
[the gap analysis's supersession notice](../../cyo-brief-gap-analysis-2026-08-22.md#supersession-notice-2026-08-30)
before citing anything in this directory.** These reports were written on 2026-08-22 and `main` has
moved 45 commits since. Summarised here because it changes how several files below should be read:

- **`V7-fill-stage.md`'s standing correction is void and now points backwards.** `3ad864a3` (#747,
  2026-08-24) made `deepseek/deepseek-v4-pro` the production fill model, which is the exact model V7
  says the figures were wrongly derived from.
- **`V4-economics.md` is superseded** by #784's [unit-cost-model.md](../../unit-cost-model.md).
- **Catalog arithmetic** is settled by [catalog-census.md](../../catalog-census.md) (#740): 84
  shells, 15,470 nodes, 81 declaring production-eligible, 74 reachable in an offered cell, 18 offered
  cells all covered. Any "86 shells" figure here is wrong.
- **`V9-testing-register.md`'s testing-ladder findings** must be re-read against `6cc33aa5` (#780).
- **`V1-f5-d7b.md`'s "no committed script implements a body-only gram scope" is false on `main`**;
  three committed callers do. Its null control stands.
- **`V11-framework-pipeline.md`'s dead second sweep is fixed** on `main`.
- **The PR sweep's OPEN states are stale**: #729, #736 and #737 all merged on 2026-08-22.
- **Lesson citations were renumbered.** `51895145` (#736) inserted a row, so `AL-509`..`AL-513` as
  cited on the source branch are `AL-510`..`AL-514` on `main`. Citations here have been corrected;
  the one `AL-509` in `S5-733-737.md` that refers to the vendor-label lesson is correct as written.

**Reproducibility.** Fourteen of these reports state figures computed by harnesses that were never
committed (`scratchpad/validation/v5_stats.py`, `v7_econ.py`, `v3run.py`, `scratchpad/canon/`, and
others) and cite paths under `/home/user/` and `/tmp/claude-0/` that do not exist in this
repository. **Every figure resting on those harnesses is unreproducible from this branch.** Each
affected file carries its own notice naming the paths it depends on. This is the same failure mode
`AL-510` and `UW-C317` record, and that `B3-evidence-methodology.md` criticises, so it is disclosed
rather than left implicit.

## How to read these

**`round1-findings/` is NOT reliable on its own.** It was produced under an instruction to find
gaps, which inflated severity and produced several claims that did not survive checking. The red
team measured **63% criticality inflation** and **40% of findings framed as absences**, of which at
least 24 restate an existing `UW` row, owner ruling, or in-code self-label.

**Always read a round-1 finding against its round-2 validator** before acting on it. The correction
log in the synthesis (section 2) is the authoritative reconciliation.

## Round 1: findings (12 reviewers, 161 findings)

Three cohorts, deliberately asymmetric.

| File | Remit | Note |
|---|---|---|
| `A1-blankslate-architecture.md` | first-principles architecture, unit economics, risk | 68-item checklist |
| `A2-blankslate-quality.md` | children's publishing and narrative craft | 63-item checklist |
| `A3-blankslate-economics.md` | LLM product economics and operations | 60-item checklist |
| `B1-framework-coherence.md` | F1-F8 logic, completeness, traceability | |
| `B2-pipeline-architecture.md` | seams, failure handling, scale, observability | |
| `B3-evidence-methodology.md` | power, confounds, pre-registration, instruments | |
| `C1-skeleton-stage.md` | skeleton rules, thresholds, catalog economics | |
| `C2-fill-stage.md` | selection, binding, fill, delivery | |
| `C3-diversity-instruments.md` | decision regurgitation, instrument validity | |
| `C4-safety-human.md` | moderation, review surface, approval | |
| `C5-cost-model-selection.md` | cost engineering, per-stage model selection | |
| `C6-testing-validation.md` | test apparatus, register integrity | |

The A cohort was barred from reading `docs/planning/`, so its 191 requirements are uncontaminated
by programme history. **Caveat established by the red team: they are one model sampled three times
on supplied premises, so treat them as a checklist, not as independent corroboration.**

## Round 2: validation (12 validators)

Each was told to refute before confirming, and to stress-test the recommendation for blast radius
and omissions.

| File | Validates | Headline outcome |
|---|---|---|
| `V1-f5-d7b.md` | F5's flagship D-7b result | 2.3 reproduces body-only; built the missing floor control (3.3 is the 80th percentile of the null) |
| `V2-recognition-convergence.md` | the recognition control failure | raters are one model in two sessions on two different-length stimuli; the control was a bad known-different anchor |
| `V3-strict-cosmetic-choice.md` | the strict bar and cosmetic choice | cosmetic choice is 1.71% concentrated in one shell; `--strict` collapses selection 74 to 20 |
| `V4-economics.md` | the unit economics | corrected all-in $1.51 / $5.70 / $24.52; the $10/70% denominator was invented |
| `V5-s1-model-selection.md` | the S-1 experiment | Spearman replicates exactly but is confounded with node count; found cross-vendor convergence instead |
| `V6-unwired-detectors.md` | the "detector gates nothing" pattern | 7 cases reduce to 2 plus an unrun registry; `AL-305` already states the rule |
| `V7-fill-stage.md` | fill-stage cost and quality fixes | 120s timeout is per call, not per book; recoverable is $0.05-0.08/book |
| `V8-safety.md` | safety and human approval | hard-block publish confirmed at 2 clicks and deliberate (**closed on `main` 2026-08-25 by the ADR-005 amendment; see the correction inside V8**); measured path-level cost |
| `V9-testing-register.md` | testing and honesty machinery | found the post-hoc pre-registration edit (`bf7cad1`); recount 4 not 57 |
| `V10-skeleton-internals.md` | thresholds, canon, catalog arithmetic | census settled at 74; the canon mostly passes; 97% of strict findings are CG-1/2/3 |
| `V11-framework-pipeline.md` | framework and pipeline seams | the tool-assisted regime does exist as code |
| `V12-redteam.md` | the review itself | 63% criticality inflation; steelman; what the review never opened |

## What is not here

Neither round opened the frontend (436 files), the player and offline path, series continuity,
personalization, the cover-art pipeline, onboarding, or the failure experience for a family. The
review declared "the reader is absent" from the framework while `reader-path-engagement-design.md`
and `check_prose_craft.py --max-moral-tags` both exist.
