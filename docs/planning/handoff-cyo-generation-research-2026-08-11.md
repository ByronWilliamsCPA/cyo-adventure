---
purpose: Hand the CYO generation diversity-research round to a review team, separating what merged and is
  citable from what is still open, still contradicted inside the repository, or blocked on something outside
  this workstream
component: docs/planning/cyo-generation-research-brief-2026-08-10.md, docs/planning/evidence/, scripts/ guard
  set, src/cyo_adventure/publishing/service.py, docs/compliance/data-retention-policy.md
source: session 2026-08-11, branch claude/skeleton-story-review-3zy6tq, PRs #682 (closed), #684, #685, #687
---

# Handoff: the generation diversity-research round

Written 2026-08-11, at the point the PRs were handed to a review team. This document exists because the
round's output landed across four pull requests with different fates, and because three of the open items
are things a reader of `main` alone would not find.

Read section 3 first if you are short of time. It is the only section describing work nobody currently owns.

## 1. Where the work is

The round began as **#682**, a single 166-file branch. That PR is **closed, not merged**: it exceeded the
automated reviewer's file limit, so it was split three ways. Its content reached `main` through the splits,
not through itself.

| PR | Scope | State |
| --- | --- | --- |
| #682 | The original combined branch | **Closed**, superseded by the split |
| #684 | Runtime: send-back reason code, report-retention exemption, migration | **Merged** |
| #685 | Research: Part III of the brief, planning documents, guard scripts | **Merged** |
| #687 | Evidence: 120 experiment artifacts plus a ruff exclude | **Open** |

Two further PRs landed in this area after the split and are not mine: **#690**, which withdrew a figure and
re-derived it from the artifacts, and **#683** (accessibility). `main` is at `v0.77.0`.

`claude/skeleton-story-review-3zy6tq`, this branch, was #682's head. Every file on it now exists either on
`main` or on #687's branch, verified by tree comparison, so it was restarted from `main` for this document
rather than carried forward.

### 1.1 #687 specifically

Still open at handoff, head `fbc643d`, 122 files. It carries three commits, and **the second and third are
not mine**: a reviewer added the mkdocs exclusion that keeps the raw artifacts out of the published site,
and corrected `blind-labels/README.md` to report all four kappas rather than the two strongest. Anyone
picking this up should read those two commits rather than the PR description, which predates them.

Its CI is green apart from the container scan, which is section 3.3 below and is not caused by the PR.

## 2. What the round established

The findings are in [the research brief](cyo-generation-research-brief-2026-08-10.md), Part III (sections 19
to 26), with the reviewer answers in [the review response](cyo-review-response-2026-08-11.md). They are not
restated here. Three results are worth knowing before reading anything else, because they change how the
rest should be read:

1. **The premise mode survives changing the model.** Isolated instances independently produced near-identical
   place names and titles, and 10 of 12 generations centre on a beacon object. The limit is stated with the
   claim: three model tiers of one family, so nothing here is established cross-vendor.
2. **The mechanism is convergent elaboration, not copying.** The control found the deleted glosses were not
   copied either, which means an enumerated category can prime two authors identically without being prose
   at all. This is the result that most changes the architecture question.
3. **Nothing in this round is reader evidence.** Every rating and annotation came from a model instance. No
   human and no child has read any generated book, and we cannot recruit in the relevant age bands, so this
   does not resolve by waiting.

## 3. What is open

### 3.1 Two published figures do not reproduce, and carry no caveat

**This is the highest-value open item and it is recorded nowhere on `main`.**

The brief's 16g.1 table publishes 11.4 and 12.9 shared four-grams per 1000 for the two repair conditions,
and `AL-264` repeats them. I could not reproduce either figure at **either** metric scope, bodies-only or
bodies-plus-labels. I ruled out the obvious explanation: the four-gram machinery is byte-identical across
the branch versions involved, so this is not a tooling drift artifact.

I did not resolve it, and the numbers currently stand unqualified. Note what is and is not in doubt: the
**direction** of 16g.1 is supported by the surrounding evidence, and the 16d conclusion that contract
sharing causes convergence does not rest on these two cells. What is in doubt is the two specific rates, and
therefore the claim that "the best lands at 11.4".

Compare the treatment the 62 percent figure received: it was retracted in place, with the re-trace shown.
These two have had no equivalent pass. `UW-C194` is the register row for this area.

### 3.2 The lessons log contradicts the brief on the 62 percent figure

The brief **retracts** the 62 percent gloss attribution at line 1644 and gives the strict re-trace as 5 of
40, which is 12.5 percent. [`AL-282`](authoring-lessons-log.md) still asserts "62 percent of shared grams
tracing to the glosses" as established fact, unqualified, and its status is `open`.

Both are on `main` right now. A reader landing on the lessons log gets the retracted number with no
indication it was withdrawn. `AL-282`'s substantive lesson, that 422 words of prose moved convergence from
12.9 to 3.2, is unaffected by the retraction and should survive; only the attribution clause needs the
correction. Its register row is `UW-C212`.

Note that 3.2 and 12.9 are themselves the figures in question under 3.1, so these two items should be worked
together rather than separately.

### 3.3 The container scan blocks any PR touching dependency files

`Container Security Scan / Container Vulnerability Scan (Trivy)` fails repository-wide, not on #687. I
verified this rather than inferring it: dispatched against `main` at `fa897a6`, with none of #687's files
present, it failed identically (run `31504938160`).

Every run passed until roughly 05:28 UTC on 2026-08-11 and failed on every branch from roughly 14:41 onward,
including branches unrelated to this work. In the job log the image builds and Trivy runs to completion; the
job dies seconds after it fetches its vulnerability database. That shape is a newly published `CRITICAL` or
`HIGH` advisory tripping `fail-on-vulnerabilities: true`, not a build break.

It blocks **any** PR that touches `pyproject.toml`, `uv.lock`, or `Dockerfile`, because those are the
workflow's path filters. #687 trips it only because it adds a five-line ruff `exclude`.

I deliberately did not add a `.trivyignore` entry to clear #687. Suppressing a repository-wide security
signal from inside a documentation PR would hide it. Someone needs the CVE from that run's scan output and a
real decision.

### 3.4 The retention policy and the shipped code disagree

#684 added a migration exempting **reviewed** generation jobs from the 30-day report purge, on the reasoning
that a report a human has acted on is evidence of that decision.

`publishing/service.py::approve` still nulls `GenerationJob.report` unconditionally at publish time
(`src/cyo_adventure/publishing/service.py`, the UPDATE at roughly line 444). So the exemption is defeated on
the approve path: the pg_cron job will now spare a reviewed report, and `approve()` deletes it anyway.

Separately, [the data-retention policy](../compliance/data-retention-policy.md) still describes the
`generation_job.report` rule as "30 days, or immediately on publish, whichever comes first" and marks it
**Enforced**. That row describes behaviour the migration has partly changed.

This was recorded on #684 and the owner queued the PR anyway, which is their call and is not being
re-litigated here. It is listed because the resulting inconsistency is now on `main` and needs a retention
decision touching [ADR-007](adr/adr-007-raw-output-retention.md), not a code fix chosen by whoever reads the
file next.

### 3.5 Two smaller items from the #684 review

- `send_back` takes an unvalidated `str` for the reason code. Fixing it properly needs a shared domain module
  so `publishing` does not have to import from `api`.
- The `pipeline_event` index should be created with `CREATE INDEX CONCURRENTLY` to avoid locking the table on
  a populated database.

## 4. Things a reader is likely to get wrong

Four claims that look like findings and are not.

1. **Shared world, cast and graph shape are the series contract, not defects.** The whole metric exists to
   catch decision repetition across books. A reviewer measuring surface similarity will rediscover the
   series premise and report it as convergence. The owner has ruled on this; the ruling was later softened,
   so treat it as a live position rather than settled.
2. **The pre-revision drafts in the evidence tree are deliberate.** Several directories carry both a `_pre`
   and a final fill. They are the same book before and after repair, not sibling books. Any all-pairs
   analysis must exclude them or it reports roughly 950 per 1000 convergence, which means nothing.
3. **Solution-transfer tiers are exclusive, strongest wins.** Operation transfer is therefore non-monotone
   with badness: an identical binding scores operation 0.000. I misread this once and reported a pair as the
   worst we hold; the known-bad battery caught it on first use.
4. **The evidence artifacts are frozen on purpose.** If a guard changes and a figure moves, the correct
   response is a new experiment directory, not an edit to an existing one. That is what #687's ruff exclude
   protects.

## 5. Environment note

Commits produced in the remote session that did this work are **unsigned**, despite `commit.gpgsign=true`,
because the configured SSH signing key is not usable in that container. This violates the project's
signed-commit rule. It applies to this document's commit and to #687's first commit; anything that must be
signed needs re-signing from a machine that holds the key.

## 6. No authoring lesson from this session

The lessons-log requirement covers story authoring runs: a new story or series book, a skeleton promotion, a
fill pass, or a validator change made in service of authoring. Writing this handoff is none of those, so
nothing was appended. The round's own lessons are already in the log as `AL-282` through `AL-295`.
