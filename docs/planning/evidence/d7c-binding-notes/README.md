# D-7c: the binding-notes arm, with matched re-baselines

> **Provenance.** Every fill and every number in this directory is model-generated and
> model-measured. No human and no child has read any of it. Deterministic gram counts are the
> strong evidence class here; everything else is a guard.

Run 2026-08-15 on branch `claude/story-quality-techniques-40jyg6`. This is the third arm the
16l correction block in
[the research brief](../../cyo-generation-research-brief-2026-08-10.md) names as "the
highest-value single experiment we can currently run": delete the non-gloss free text (the 473
words of binding notes, invention notes, title constraints, and the affect ceiling) while
keeping the 32 fact glosses (422 words) that D-7b deleted.

## Why re-baselines

The D-7 (glossed, 13.6 shared four-grams per 1000) and D-7b (bare names, 2.3) fills were
authored by a different model generation in a different session. A third arm compared against
those frozen numbers would confound text-class with author-generation. So this run re-authors
all three kernels with the same author model (the session's own frontier model, isolated
subagent instances), the same fixed instruction file, the same two shells, single-pass fills,
no revision round:

| arm | kernel | glosses | binding-note text |
| --- | --- | --- | --- |
| R-glossed | `../d7-stratified-plan/structural.json` | present | present |
| R-bare | `../d7b-bare-names/structural_bare.json` | deleted | present |
| R-notes | `kernel_notes.json` (built here) | present | deleted |

`build.py` constructs `kernel_notes.json` and reports the exact deletion: 497 words removed
(16l counted 473; the difference is counting method, since every `note` key under
`world_recipe` is stripped here, and the two counts were made by different hands). Glosses are
verified byte-identical to D-7's.

## Pre-registered prediction and falsifiers

Written before any author ran; see `build.py`'s docstring for the full statements.

- **Prediction**: R-notes lands at or above the midpoint of R-glossed and R-bare (the section
  21 trace supports gloss-driven convergent elaboration).
- **Falsifier 1**: R-notes at or below 1.5x R-bare means the gloss attribution is wrong and
  the 16l restated rule needs re-deriving.
- **Falsifier 2**: if the re-baselines do not reproduce the historical order (R-glossed
  materially above R-bare), no cell is interpretable against the 13.6 / 2.3 anchors and the
  run reports as a failed cross-generation replication of 16l instead.

## Protocol deviations from D-7/D-7b, declared up front

1. **Author model.** New generation (this session's model), hence the re-baselines.
2. **Bindings.** The original arms drew on per-arm bibles; armC's bible lived in a session
   scratchpad and is lost. Both sides here receive their shell only (the shell's bound choice
   labels are declared authoritative for the world; proper nouns otherwise invented by the
   author). Symmetric across sides and identical across arms, so arm contrasts are unaffected.
3. **Instruction file.** `AUTHOR_INSTRUCTIONS.md`, reconstructed from the artifact formats
   (decisional stratum shape, shell fill directives). Byte-identical across all six authors;
   the manipulated variable enters only through the kernel file.
4. **Authors were not told** there are arms, siblings, or an experiment. Each saw exactly
   three files: kernel, shell, instructions.

## Files

- `build.py`, `kernel_notes.json`: the arm construction, deterministic.
- `AUTHOR_INSTRUCTIONS.md`: the fixed instruction file all six authors received.
- `R-<arm>/decisional_{C,D}.json`, `R-<arm>/filled_{C,D}.json`: the six authored books.
- `results.md`: measurements, written after the fills and never edited thereafter.
