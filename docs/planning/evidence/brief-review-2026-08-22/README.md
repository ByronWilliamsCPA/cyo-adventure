# Raw agent reports: multi-agent review of the 2026-08-22 generation research brief

Date: 2026-08-22. These are the thirteen individual agent reports behind the synthesis in
[cyo-generation-research-brief-review-2026-08-22.md](../../cyo-generation-research-brief-review-2026-08-22.md),
which reviewed [cyo-generation-research-brief-2026-08-22.md](../../cyo-generation-research-brief-2026-08-22.md).
The synthesis deduplicates and severity-ranks across these reports; the files here preserve each agent's full
findings, including material that did not make the synthesis.

> **Landed 2026-08-30, and dated.** These are the 2026-08-22 reports as delivered, and they are deliberately
> not annotated: their value is that they record what each agent found on that date. Findings overtaken since
> are marked in the synthesis, not here, and the current disposition of every `R-*` id lives in
> [generation-review-workstream-plan-2026-08-22.md](../../generation-review-workstream-plan-2026-08-22.md).
> The two companion files the review branch also carried, the 2026-08-22 brief and the skeleton-sourcing test
> plan, are not part of this landing: `main` holds both, and its copies carry corrections these reports
> predate, including the R-1 correction this very review produced.

## Method

Three groups. The fresh-eyes group (A) received only the product goal and constraints, with no access to the
brief, its companions, or the repository; each specified the ideal programme from first principles so the diff
against the actual programme exposes blind spots. The structural group (B) read the whole brief and audited it
against the companions and code. The component group (C) went deep on one pipeline area each. All B and C
agents verified claims against the research branch `claude/model-selection-skeleton-dev-78yp7u` at commit
`01b7119` via a read-only worktree, including raw run records under `docs/planning/evidence/`, the diversity
test register, the skeleton sourcing test plan, and production code. No agent ran paid model calls.

## Roster

| File | Group | Mandate | Repo access |
| --- | --- | --- | --- |
| A1-fresh-eval.md | fresh eyes | ideal evaluation and testing methodology | none |
| A2-fresh-cost.md | fresh eyes | ideal cost model and cost-engineering discipline | none |
| A3-fresh-editorial.md | fresh eyes | editorial and QA standard for branching children's books | none |
| A4-fresh-architecture.md | fresh eyes | ideal generation architecture, alternatives-aware | none |
| B1-rigor.md | structural | scientific and statistical rigor of the brief's claims | research branch |
| B2-claim-verification.md | structural | claim-by-claim fact check against artifacts and code | research branch |
| B3-coherence.md | structural | framework coherence and decision-document quality | research branch |
| B4-testing-reproducibility.md | structural | enforcement map, calibrated constants, drift, harness reproducibility | research branch |
| C1-skeleton-stage.md | component | sections 3.1, 3.2, 4.2 and the S-1 experiment | research branch |
| C2-fill-stage.md | component | sections 3.3, 3.4, 4.1 and the vendor comparison | research branch |
| C3-diversity-instruments.md | component | sections 1, 4.3, 4.4 and principles F5/F6 | research branch |
| C4-cost.md | component | section 4.5, principle F7, unit economics | research branch |
| C5-safety-human-gate.md | component | principles F2/F8, sections 3.4/3.5, register row S-5 | research branch |

## Provenance notes

- Each file is the agent's final report as delivered on 2026-08-22. Transport escaping was normalized
  (HTML entities such as escaped angle brackets restored to plain characters) and a one-line provenance
  header was added; A-group files are otherwise verbatim. B- and C-group files are faithful transcriptions
  of the delivered reports with light formatting normalization only; no findings were added, removed,
  or reworded.
- All nine repo-grounded agents (B and C) were interrupted once mid-run by an account usage limit and
  resumed with their context intact; every report is a completed run.
- Numbers in these reports were recomputed by the agents from committed artifacts; the synthesis document
  cross-checked the load-bearing ones across agents. Where two agents state slightly different framings of
  the same recomputation, the synthesis records the reconciled value.
- This directory is excluded from the published docs build (`exclude_docs` in `mkdocs.yml`), like the other
  evidence directories: it is repository evidence, not site content.
