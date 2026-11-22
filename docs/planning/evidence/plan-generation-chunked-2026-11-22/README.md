# Chunked plan-writing trial (2026-11-22)

One paid run of chunked Story Plan writing (`fcdd55e` to `72063f9`) on the largest 8-11 retained shape,
`the-lantern-keepers-list` (132 nodes, 314 choices, 3 threads), the request that ran out of room in the single-call
retrial (`../plan-generation-retrial-2026-11-21/`). Sonnet 5.5 via OpenRouter, reasoning effort `low`, Stage 0 skipped
and recorded, owner-approved with a 2 USD cap. Driver: `scripts/smoke_plan_generation.py --only 6 --continue-on-length`.

## Result

| Measure | Single-call retrial | Chunked trial |
| --- | --- | --- |
| Outcome | cut off at 32,000 output tokens, no plan | plan written, stitched and loaded; `failed_checks` on 1 ERROR |
| Calls | 1 plan call (truncated) | pitch, spine, 4 scenes, 2 scene repairs |
| Output tokens | 32,000 (11,071 reasoning) | 40,778 over 8 calls (3,074 reasoning); no call reached `max_tokens` |
| Cost, time | 0.35 USD | 0.59 USD, about 4 minutes |
| Facts, passages with no fact | none | 79 facts; 0 of 108 passages empty |
| Distinct intents, costs | none | 243 and 223 of 314 choices |

The first stitched plan had one ERROR. Both repairs of the owning scene (S2) came back naming a fact the scene had not
declared (`cloth_pocketed`), so they failed to load and the repair budget ran out.

## What it shows

- **Chunked writing works on a real model.** Every part fitted, nothing was cut off, and the stitched plan is dense (one
  SP-D warning: 27 percent of decision choices reuse a cost across destinations, against a 25 percent threshold).
- **Scene repairs need a local check.** A scene that references a fact it neither uses from the ledger nor proposes in
  `new_facts` should be caught and re-asked before stitching, instead of costing a repair at load.
- **Convention 1 collides with monotone facts.** The remaining ERROR is SP-3: `wren_has_no_cloth` (at two hubs) and
  `wren_has_polish_cloth` (later on the same reading). The hero lacks a thing and then gets it; convention 1 asks for the
  lack to be recorded with `contradicts`, and facts never retract, so a legitimate change of state reads as a
  contradiction.
- The driver's per-attempt replay (`attempt_findings`) assumes single-call plans and reports chunked parts as unloadable
  sections; it is an artefact of the driver, not of the generator. `final_checks` is authoritative.
