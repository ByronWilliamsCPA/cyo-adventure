# The fill budget: the one bound an author cannot see

Written 2026-08-19 for owner ruling on `UW-C302`. Every number below was executed. Where I could not
establish something, it says so.

## What the screen is

`generation/skeleton.py::is_fill_feasible(story, max_tokens)` returns
`expected_output_tokens(story) <= max_tokens * _FEASIBILITY_MARGIN`, and the 0.8 margin is applied
INSIDE the function. `expected_output_tokens` sums the declared `words=` targets and multiplies by
2.0 tokens per word. It has two callers at two different caps, and the docstring is emphatic that
conflating them is the trap:

| caller | cap asked at | what False means |
| --- | --- | --- |
| `skeleton_match._is_feasible` | the model-independent DEFAULT, 131,072 | the skeleton is dropped from generation selection |
| `orchestrator.fill_skeleton` | the RESOLVED per-model cap | fill it in batches instead of one shot |

So the selection screen is **104,857 tokens, or 52,429 declared words**, and a skeleton above it is
silently unselectable. Nothing in `check_skeleton.py --strict --headroom` mentions it. The 16+
gamebook agent found it only because `check_incell_clones.py` emitted `skeleton.fill_infeasible` as
structlog noise, at 97 tokens over, 0.09 percent.

## What it costs at the top of a cell

`words_budget / band words-per-node target` against each cell's declared node ceiling:

| cell | node ceiling | reachable at word target | at the advisory low |
| --- | ---: | ---: | ---: |
| 16+/long/gamebook | 750 | **655** | 953 |
| 16+/long/prose | 345 | **300** | 419 |
| every other cell | | comfortably above its ceiling | |

**Two of eighteen cells cannot reach their own declared node ceiling at their own words-per-node
target. Zero cannot reach it at the advisory low.** So the envelope is honest only if the author
writes about 13 percent under target, which PL-19 permits and never explains. The largest committed
skeleton, `the-last-cartage`, sits at 99,906 tokens, 95.3 percent of the screen, at a 79.0-word mean
against an 80-word target.

## The finding that reframes the whole question

**Chunking makes the selection screen unnecessary for the path it guards, and the screen is at the
same time far too loose for the path it does not guard.**

`generation/chunking.py` partitions a skeleton into batches that each fit the cap. Measured: the
largest single node in the catalog is 250 declared words, 500 tokens, against a batch budget of
26,214 tokens under the smallest configured model cap (32,768). PL-19's hardest per-node maximum is
230 words at 16+, so a node can never approach a batch budget. **`UnpartitionableSkeletonError` is
unreachable for any gate-valid skeleton**, which means no skeleton is "too large for any backend",
which is exactly the premise the selection screen states.

But chunking is disabled for a bound fill: `orchestrator.py:1407` reads

```python
chunked = slot_bindings is None and not is_fill_feasible(skeleton, max_tokens=cap)
```

and `worker.py:1133` passes `slot_bindings=result.bindings` on the production path. A bound fill is
therefore one-shot only, at the RESOLVED cap. On the shipped default model
(`anthropic/claude-haiku-4.5`, ceiling 64,000) that budget is **51,200 tokens, 25,600 declared
words**, less than half the selection screen. Measured against the catalog:

**19 of 82 committed skeletons exceed the bound-fill budget on the shipped model**, including four of
the fourteen authored yesterday. The largest five are `the-last-cartage` (99,906), 
`the-longwinter-station` (87,200), `the-tenfold-siege` (84,466), `the-tricameral-city` (84,352) and
`the-ashfall-expedition` (79,070).

So the screen is calibrated to a cap that matches neither consumer: irrelevant to the chunked path,
and twice as permissive as the bound path it never checks.

**What I could NOT establish**, and it decides how urgent this is: whether `result.bindings` is ever
`None` on the production path. If it never is, chunking never fires in production and those 19 books
are landmines; if it does, they are only landmines for personalized fills. The orchestrator's own
comment asserts chunking "IS live rather than theoretical" at "15 of the 55 production skeletons",
which implies unbound fills do happen, but that comment is stale on its face (the catalog is 82, not
55) so I do not want to lean on it. **Resolve this before choosing between the options below**; it is
a half-hour of reading, and no option is safe to pick without it.

## Two stale claims in the code, found on the way

- `chunking.py`: "the largest skeleton in the catalog needs about 87,200 output tokens". It is now
  99,906.
- `skeleton.py`: "131,072 clears every cell with 20 percent headroom". The largest is now 76.2
  percent of the raw cap, so the 20 percent margin is 4.7 points from binding.

Both drifted because the catalog grew, which is the `UW-C304` pattern in prose rather than in a test.

## The options

| # | Option | Fixes | Cost |
| --- | --- | --- | --- |
| A | Do nothing | nothing | Two cells keep an unreachable ceiling; the 19-book exposure stays unmeasured in production |
| B | **Print fill headroom in `--headroom`** | the invisibility | Trivial; a few lines. Fixes no arithmetic |
| C | Lower the two cells' node ceilings to what the budget allows | the dishonest envelope | Contradicts ADR-011's cell table; buys little, since the advisory low already reaches the ceiling |
| D | Screen at the cap the fill will actually use, per path | the mis-calibration | Selection must know whether the fill will be bound, which it currently does not |
| E | Enable chunking for bound fills | the 19-book exposure at its root | Real work: the subset prompt has no bound-fill variant, and sentinel-wrapped slot values would have to survive a batch merge |
| F | Raise `MAX_FILL_OUTPUT_TOKENS` or drop the 0.8 margin | the selection screen only | Does nothing for the bound path, which is the one that actually fails |

## Recommendation: B now, then resolve the bindings question, then E

**B immediately, and unconditionally.** `check_skeleton.py --headroom` should print expected output
tokens against both budgets, the selection screen and the shipped model's bound-fill budget, the way
it now prints state headroom. It is a few lines, it needs no decision, and it converts the only
invisible budget in the system into a visible one. An author at 95.3 percent of a limit should be
told so by the tool they already run.

**Then answer the bindings question**, because it decides whether E is urgent or merely correct.

**Then E, not D or F.** The 19-book exposure is the real defect: a bound fill of any of them on the
shipped model stops on `finish_reason=length`, and `AL-329` records that a length-stopped completion
is leg-fatal rather than retried, so the job fails deterministically with no prose. D treats the
symptom at selection time by hiding books the pipeline could fill; F raises a ceiling that the
failing path never consults. E removes the asymmetry that created the problem, and the asymmetry is
not principled: it exists because the subset prompt was never given a bound-fill variant, which is a
gap rather than a design.

**Against C**, and this is worth stating because it is the obvious move: the two cells CAN reach their
ceilings at the advisory-low word count, so the envelope is reachable, just not at the target. Lowering
the ceiling would encode a fill-pipeline limit into a story-shape table, where the next reader would
have no way to know why. If B lands, an author sees the trade and picks; that is the better place for
it.

**I have not demonstrated a production failure**, only the arithmetic that implies one. Before E is
scheduled, one bound fill of `the-last-cartage` against the shipped model would turn this from a
measured exposure into a reproduced defect, and that is worth doing first.
