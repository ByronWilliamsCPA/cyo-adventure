---
title: "Handoff: story-quality technique review and staged experiments"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Hand the 2026-08-15 technique-review session to the next team: what is committed and
  citable, which three pre-registered experiments are staged with zero results, and the exact
  resume runbook, including the two usage-window exhaustions that interrupted the author waves."
tags:
  - planning
  - handoff
  - research
  - quality
component: Research
source: "session 2026-08-15, branch claude/story-quality-techniques-40jyg6"
---

# Handoff: story-quality technique review and staged experiments

> **Date**: 2026-08-15 | **Branch**: `claude/story-quality-techniques-40jyg6`
> Read section 3 first if you are short of time: it is the resume runbook for work that is
> staged, pre-registered, and has produced no results yet.

## 1. What this session was

The owner asked for a comprehensive review of story-generation and testing techniques the
programme has not considered (with prompt A/B testing as the seed question), plus as much
concrete progress (theory, testing structures, test books) as one session could produce. The
session produced one review document, three pre-registered experiment rigs, one validated
measurement instrument, one frozen protocol, four logged lessons, and zero completed fills,
because two consecutive usage windows exhausted mid-wave (section 4).

## 2. What is committed and citable

All on this branch, all pushed:

| Artifact | Where | State |
| --- | --- | --- |
| Technique review (20 candidates, grep-verified; the prompt A/B answer; do-not-re-propose list) | `story-quality-technique-review-2026-08-15.md` | complete |
| D-7c rig: the 16l correction block's named highest-value experiment (delete the 473 binding-note words, keep the 422 glosses), with matched re-baselines of D-7 and D-7b | `evidence/d7c-binding-notes/` | pre-registered, staged, no results |
| W16 rig: fill-prompt guide ablation (FULL 3,517 / NOCRAFT 2,558 / MIN 101 words), the never-run prompt-content axis | `evidence/w16-fill-guide-ablation/` | pre-registered, staged, no results |
| Recognition protocol frozen as code (blinding, breadth-first reading order, sequential commitment, verdict schema) with pre-registered known-answer validation rules | `evidence/recognition-protocol-pilot/` | built, unvalidated (needs the D-7c pairs) |
| Pair scorer: bodies-only shared four-grams at two scopes (legacy concat plus the AL-309 junction-free per-node union), FK, dialogue share, you-density, words-on-target | `evidence/d7c-binding-notes/score_fills.py` (copy in the W16 dir) | **validated**: reproduces the corrected 16l anchors exactly (2.33 and 13.59 per 1000) on the frozen d7/d7b artifacts |
| Catalog baseline: you-density and dialogue share over all 23 committed fills | review doc section 6.4 | complete |
| Lessons `AL-353` through `AL-357`, register rows `UW-C248` through `UW-C252` | lessons log, unscheduled register | validators green |

Findings a reader should not have to re-derive: 14 of 23 committed catalog fills sit in the
design review's third-person you-density range (0 to 6.6 per 1000), including every kid-band
book; dialogue share is 0.000 on 20 of 23; every historical clocktower experiment fill is
third person, which is why D-7c re-baselines rather than comparing against the frozen 13.6 and
2.3 figures across an author-generation change.

## 3. The resume runbook (nobody owns this until someone picks it up)

Everything below is deterministic to restart because every input is committed; nothing depends
on the dead session's scratchpad. **Run at the start of a fresh usage window** and launch
author waves small (see section 4): three authors, then three, is safer than six.

1. **Stage** (skip if re-staging from git): per D-7c arm and side, a directory holding
   `kernel.json` (R-glossed = `evidence/d7-stratified-plan/structural.json`; R-bare =
   `evidence/d7b-bare-names/structural_bare.json`; R-notes =
   `evidence/d7c-binding-notes/kernel_notes.json`), `shell.json`
   (`evidence/obligation-variance/arm{C,D}_shell.json`), and
   `evidence/d7c-binding-notes/AUTHOR_INSTRUCTIONS.md`. For W16: per arm and seat, the
   matching `evidence/w16-fill-guide-ablation/PROMPT_{FULL,NOCRAFT,MIN}.md`.
2. **Delete any partial outputs before launching.** The interrupted waves left four
   `decisional.json` strata with no fills; a resumed author must start clean, because a
   decisional stratum and its fill are one author's coherent work and must not be mixed
   across instances.
3. **Authors** are isolated general-purpose agents, one per directory, told to read exactly
   their input files, follow the instruction file, write `decisional.json` and `filled.json`
   (D-7c) or `filled.json` (W16) in place, and read nothing else. Authors are never told
   there are arms, siblings, or an experiment.
4. **Score**: `score_fills.py --shell <arm shell> --pair <name>=<C>:<D> --out results.json`
   per experiment; `scripts/run_story_gate.py` on every fill (copy into `tmp_cleanup/`
   first, the gate refuses paths outside the repo); `scripts/check_prose_craft.py` over each
   experiment's fills. Evaluate strictly against the pre-registered predictions and
   falsifiers in each directory's `build.py`/`build_variants.py` docstring and README.
5. **Recognition raters**: build prompts with
   `evidence/recognition-protocol-pilot/protocol.py` for the three D-7c C-vs-D pairs plus
   one cross-skeleton control (a D-7c clocktower book against a W16 school-garden book); one
   rater agent per pair writes `verdict.json`; evaluate against the README's known answers.
6. **Freeze**: copy fills and decisionals into the evidence dirs (`R-<arm>/` subdirs for
   D-7c, `<ARM>/S<n>/` for W16), write each `results.md` once and never edit it, update the
   review doc's section 6.5, append lessons from `AL-358` (register from `UW-C253`), run
   `scripts/check_lessons_log.py` and `scripts/check_work_linkage.py`, commit and push.
7. **Report against the falsifiers explicitly**, including if one fired; the D-7c
   re-baseline order check (R-glossed materially above R-bare) decides whether the arm is
   interpretable at all.

## 4. The two interruptions, so the next team plans around them

Twelve parallel frontier authors died at 07:40 UTC on the account's usage reset with zero
output files (`AL-356`). The relaunch of six at 12:19 UTC on the fresh window died the same
way at the next reset, with four decisional strata written and zero fills (`AL-357`): a
window that has already served a day's ordinary use does not hold six concurrent
frontier-effort authors at roughly 50k tokens of context each. The runbook above assumes
waves of three or fewer and a launch at the start of a window, not mid-window.

## 5. Things a reader is likely to get wrong

1. **The pre-registrations are frozen.** Predictions and falsifiers were committed before any
   author ran (commits precede the launches on this branch). Do not soften them to fit
   whatever the fills turn out to say; a fired falsifier is a result.
2. **The four decisional strata on the dead session's scratchpad are not partial results.**
   They are contamination for a resumed run (section 3 step 2) and evidence for nothing.
3. **`check_sibling_fills.py` has no bodies-only flag.** Bodies-only rates in this line of
   work come from the scorer, which imports the script's own gram primitives; the two-scope
   report exists because of the open junction defect `AL-309`.
4. **The review doc's supplier and craft claims cite the brief's own evidence classes.** No
   number produced this session is reader evidence; the provenance banners say so on every
   directory.

## 6. Environment notes

Commits from this remote session are unsigned despite the project's signed-commit rule: the
container holds no usable signing key (the same limitation recorded by the 2026-08-11
handoff). Anything requiring signatures needs re-signing from a machine that holds the key.

## 7. Lessons

This session's lessons are already logged as `AL-353` through `AL-357` with register linkage
`UW-C248` through `UW-C252`; nothing further was held back for this document.
