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
- `runs/e1-2026-08-21/`: **the registered S-1 run.** 4 cells x 4 replicates x 5 legs, cap 65536,
  6 repair rounds, conditions in `run.json`; analysis per the register row's pre-registration.

Smoke shells share cell A's replicate-1 premise with the registered run by design (the S-0
allocation rule is frozen); the smokes are excluded from analysis because their run conditions
differ, not because of the premise.

## Layout per run

`run.json` (conditions), `shells/` (final shell per cell x replicate x leg, kept whether or not it
passed), `records/` (one record per shell: attempts, repair rounds, strict pass, tokens, finish
reasons, catalog distances, final-round validator feedback), `summary.json` / `summary.md`
(aggregates plus the pre-registered permutation test on the primary endpoint).
