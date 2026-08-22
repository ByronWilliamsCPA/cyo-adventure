# Skeleton-author vendor comparison (register row S-1, plan E1)

Evidence directory for the cross-vendor skeleton-authoring screen run by
`scripts/compare_skeleton_authors.py`. Register row `S-1` in the
[diversity test register](../../diversity-test-register.md) section F carries the pre-registered
primary endpoint and falsifier; the harness docstring carries the shared repair-loop contract.

## Runs

- `runs/smoke-2026-08-21/`: **harness validation, excluded from S-1 analysis.** One shell per leg,
  cell A (5-8 short, premise PA-1), cap 32768, without `--allow-mvp`. It found two harness defects,
  fixed in the harness before any registered spend: (1) cell mode without `--allow-mvp` fails every
  shell's correct `production_eligible: false` declaration, so the pass bar was unreachable for
  every leg; all four completing legs repaired down to 1-2 genuine residual findings and could
  never pass. (2) The 32k completion cap kills reasoning-heavy legs: v4 Flash spent all 32,767
  tokens on hidden reasoning and returned no content (the AL-328 shape), and Sonnet 5 truncated
  twice, costing two rounds to parse failures. Exploratory observations that motivated no change:
  residual findings differed by leg (branch-depth overshoot for v4 Pro, CG-1 choice cadence for
  GPT-5.6, PL-23 clock over-declaration for Gemini 3.1 and Sonnet 5), and every completing leg's
  shell coerced and scored against the in-cell catalog (min structural distance 0.056-0.161).
- `runs/smoke2-2026-08-21/`: **harness validation, excluded from S-1 analysis.** Same single-shell
  grid re-run after both fixes (cap 65536, `--allow-mvp`), to confirm the pass bar is reachable
  before the registered 80-shell run. Result: the bar is reachable (Gemini 3.1 Pro passed at 2
  repair rounds; v4 Flash completed under the raised cap), and the four cap-limited legs ended on
  genuine, distinct findings (PL-18 topology admissibility for Sonnet 5 and GPT-5.6; an L1-2
  dangling ref plus L1-7 ending-count overshoot for v4 Pro; an integer-type schema miss for
  Flash). Design consequence, fixed before the registered run: a round cap of 4 censors most
  legs at the cap and starves the primary endpoint of range, so the registered run uses 6.
- `runs/e1-2026-08-21/`: **the registered S-1 run, HALTED on provider credits after 4 of 80
  shells.** 4 cells x 4 replicates x 5 legs, cap 65536, 6 repair rounds, conditions in `run.json`.
  76 shells failed with OpenRouter HTTP 402: the account's prepaid credits were exhausted
  ($400.92 used of $400.00 at the time of the run; the balance was nearly spent before this
  session, and the two smokes tipped it). No result may be read from this directory's
  `summary.md`: the 4 completed shells (2 v4 Pro, 1 v4 Flash, 1 GPT-5.6, all cell A) are kept and
  the permutation test over them is meaningless. When credits are restored, resume with the same
  conditions and out-dir: `uv run python scripts/compare_skeleton_authors.py --replicates 4
  --max-repair-rounds 6 --concurrency 5 --resume --out-dir
  docs/planning/evidence/skeleton-author-vendors/runs/e1-2026-08-21`. The `--resume` flag keeps
  cleanly completed shells and re-authors only errored or missing grid points.
- `runs/e1r3-2026-08-21/`: **the descoped S-1 blind-condition run (plan section 10), counted in
  S-1.** Cell A only, 3 replicates x 7 legs = 21 shells, blind stateless repair, cap 65536, 6
  repair rounds. Legs: deepseek-v4-pro and deepseek-v4-flash over OpenRouter (pinned backends),
  moonshot-kimi-k3-modal via `scripts/modal_kimi_leg.py`, and four Claude-subagent legs (fable,
  opus, sonnet, haiku) driven through `--emit-prompts` / `--score-shell`. Result: 2 of 21 passed
  the strict bar (one sonnet-subagent shell, one v4-flash shell); the pre-registered permutation
  test on repair rounds is uninformative because nearly every leg is censored at the cap
  (register row S-1, lesson `AL-513`).
- `runs/e1r3-tools-2026-08-21/`: **the S-1 tool-assisted condition, counted in S-1.** Cells A and
  D, 3 replicates x 7 legs = 42 grid points, same legs as `e1r3-2026-08-21`, cap 65536, and a cap
  of 10 checker invocations per point instead of the blind round cap: the author sees the
  checker's full output each iteration (subagent legs run the checker themselves; API legs get it
  relayed verbatim by the tools driver). Result: 27 of 42 passed (cell A 12/21, cell D 15/21).
  Reading caveat: `summary.md`'s `mean repair rounds 0.00` and `first-pass clean` columns are an
  artifact of the drivers scoring only each point's FINAL draft through `--score-shell` (one
  record per point), not measured iteration counts; the real per-point checker counts for this
  run are in `tools-meta.json`, not in the record files (later tools runs also get per-point
  `.tools-counts.json` sidecars from the driver).

Smoke shells share cell A's replicate-1 premise with the registered run by design (the S-0
allocation rule is frozen); the smokes are excluded from analysis because their run conditions
differ, not because of the premise.

## Layout per run

`run.json` (conditions), `shells/` (final shell per cell x replicate x leg, kept whether or not it
passed), `records/` (one record per shell: attempts, repair rounds, strict pass, tokens, finish
reasons, catalog distances, final-round validator feedback), `summary.json` / `summary.md`
(aggregates plus the pre-registered permutation test on the primary endpoint).

`run.json` caveat: only `compare_skeleton_authors.py run()` writes it, and it records only that
invocation's vendors/cells/replicates with `started_at` stamped at invocation (a `--resume`
re-invocation restamps it). Subagent legs driven through `--emit-prompts`/`--score-shell` and
`modal_kimi_leg.py` contribute records but not `run.json`, so a mixed run's `run.json`
under-describes the directory: `e1r3-2026-08-21/run.json` lists the 2 DeepSeek vendors for a
directory holding 7 legs, and `e1r3-tools-2026-08-21/run.json` is a hand-reconstructed conditions
file (it says so in its `authored` field). The record files, not `run.json`, are the per-point
ground truth.
