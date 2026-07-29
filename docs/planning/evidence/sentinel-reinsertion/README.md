# Sentinel measurement evidence (ADR-023 Stage R)

Durable copies of the aggregate reports behind the G1 stop verdict and the
G1-R gate decision. They exist because the runs that produced them live under
`results/`, which is gitignored (`.gitignore:301`): the plan documents cited
run ids that no reviewer, and no future reader of this repo, could open.

Only the AGGREGATES are committed. Where a run was invoked with `--save-fills`,
its `fills/` directory holds the raw LLM output for 30 stories; that stays
untracked, both for size and because this repo does not need a copy of
generated children's prose to justify a gate. The aggregates hold counts and
rates only.

Reproduce a run with the recipe in
[story-personalization-execution-plan.md](../../story-personalization-execution-plan.md)
Task A1, then re-analyze saved fills offline with
`scripts/prototype_sentinel_reinsertion.py <run-dir>`.

| File | Run | Instrument | What it is |
| --- | --- | --- | --- |
| `20260728T205008Z-g1-stop-survival.*` | `20260728T205008Z` | survival | The evidence that FIRED G1: first-attempt clean-pass 3.3% (1/30) on the production fill route, far below the ~80% floor, which is what sent the design to the re-insertion approach. Its failure taxonomy (1738 dropped, 207 forged, 111 migrated) is the case for a transform rather than a stricter prompt. |
| `20260729T010024Z-reinsertion-dev.*` | `20260729T010024Z` | re-insertion | The prototype run the matcher was developed against. Cited wherever the plans quote "dev fills" coverage (HERO 42.4%, FOUNDER 94.6%, CHAPERONE 63.9%). Not gate evidence: the matcher had seen this data. |
| `20260729T042510Z-g1r-confirmatory.*` | `20260729T042510Z` | re-insertion | The G1-R exit evidence: 30 fresh, unseen fills through the production route. `verify_manifest_ok` 30/30 (100%), which is the gate requirement. Also the second run of the pair that showed per-slot coverage swinging materially between runs (AL-061). |
| `20260729T054004Z-vocative-nudge-rejected.*` | `20260729T054004Z` | re-insertion | The rejected vocative-nudge experiment: HERO coverage fell to 4.9% against a 26.8-42.4% baseline, because the nudge's rationale clause was executed as an instruction (AL-062). The template edit was reverted and never committed. |

The `.md` and `.json` for each run are the same numbers in two shapes. The
re-insertion reports come from `render_markdown` / `render_json` in
`src/cyo_adventure/measurement/reinsertion.py`; the survival report comes from
the same two function names in `src/cyo_adventure/measurement/report.py`. The
two instruments read
the same fills but answer different questions, so their rates are not
comparable: survival asks whether the model left a sentinel intact, re-insertion
asks whether the transform can put one back.

## Reading the three rates

They are not redundant, and only one of them is the gate:

- **Verify-manifest pass rate** is the gate metric. It proves the reinserted
  document is self-consistent with its own derived manifest, which is a
  transform-correctness signal. Required at 100%.
- **Round-trip integrity-check pass rate** is bound-skeleton-relative: it
  proves a clean re-insertion restores the exact token multiset the ORIGINAL
  pre-fill skeleton declared. It is a fill-quality signal and is legitimately
  below 100% whenever a model simply never used a slot's value.
- **Strip-all-then-reinsert clean rate** requires every expected token in
  every node, so it is dominated by the same fill-quality effect and reads
  low even on a run where the transform was flawless.

Per-slot coverage is a property of each LLM fill, not of the code, which is
why the exit record states cross-run ranges rather than point values.
