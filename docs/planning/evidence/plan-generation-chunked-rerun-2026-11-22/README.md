# Chunked plan-writing re-trial (2026-11-22)

A second paid run of chunked Story Plan writing on `the-lantern-keepers-list`, after two changes made in response to
the first trial (`../plan-generation-chunked-2026-11-22/`): convention 1 reworded so a reversed negative is worded with
its time and not marked `contradicts` (`AL-874`), and a pre-stitch check that asks a scene once about facts it names
but never declared (`AL-873`). Sonnet 5.5 via OpenRouter, reasoning effort `low`, Stage 0 skipped and recorded, repair
budget 2, cap 2 USD, owner-approved. Driver: `scripts/smoke_plan_generation.py --only 6 --continue-on-length`.

## Result

| Measure | First trial | Re-trial |
| --- | --- | --- |
| Outcome | `failed_checks`: 1 SP-3 ERROR, repair failed to load | `failed_checks`: 6 SP-2 ERRORs, plan loads |
| Calls | 8 | 9 (pitch, spine, 4 scenes, 1 re-ask, 2 scene repairs) |
| Cost, time | 0.59 USD, about 4 minutes | 0.70 USD, about 4 minutes |
| Facts, empty passages | 79; 0 of 108 | 87; 0 of 108 |
| Load errors at the end | 1 (undeclared fact in the repaired scene) | none |

## What it shows

- **The re-ask earned its call.** The repair of the last scene (S4) named 35 facts that nothing declared. In the first
  trial the same behaviour became load errors and used the repair budget; here one extra call fixed all 35 before the
  stitch (`plan:6:reask=S4:undeclared=35`).
- **The SP-3 ERROR did not recur.** The three SP-3 findings left are WARNINGS (facts on routes no single reading
  crosses). This run does not isolate the convention rewording from the scene rewrite, so it is evidence, not proof.
- **A repair regressed the plan.** The first stitch had 1 ERROR. Re-writing S4 to fix it left 13 (`plan:7:errors=13`),
  and re-writing S2 brought that to 6, at which point the budget of 2 was spent. The scene prompts ask the writer to
  change only what a finding names, but the writer re-answers the whole scene, and a whole-scene answer re-decides every
  `requires`. The 6 that remain are SP-2: later passages require facts (for example `sheet_music_dust`) that some
  routes into them never established.
- The driver's per-attempt replay still treats each scene answer as a whole plan (`AL-875`); `final_checks` and
  `stage_log` are authoritative.
