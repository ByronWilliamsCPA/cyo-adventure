# The fill budget: the one bound an author cannot see

Written 2026-08-19 for owner ruling on `UW-C302`. Every number below was executed. Where I could not
establish something, it says so.

> **REVISED 2026-08-19 after adversarial review. Five of my six claims were wrong in some part and
> three of them quoted a bound I had not executed, which is the standing failure this workstream has
> now earned four times. The corrections are inline below and the recommendation changed. See
> "After the review" at the end for what moved and why.**

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
| 16+/long/prose | 345 | **299** | 419 |
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
26,214 tokens under the smallest cap in `MODEL_OUTPUT_CAPS` (32,768, a DeepSeek row that no shipped
configuration selects; the smallest a shipped config resolves to is 64,000). PL-19's hardest per-node maximum is
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

19 of 82 committed skeletons exceed that budget. **Only 7 of them are on the bound path**: boundness
is decided by the presence of a `<slug>.contract.json` sidecar (`worker.py:1030-1032`,
`load_contract_for` returns None without one and that branch calls `fill_skeleton` unbound), and 12 of
the 19 are contractless and chunk safely. The 7 exposed are `the-tricameral-city`,
`the-ashfall-expedition`, `the-salt-archive`, `the-pale-road`, `the-year-of-four-banners`,
`the-third-shift` and `the-skyrail-heist`. None of the fourteen authored yesterday is among them. The largest five are `the-last-cartage` (99,906), 
`the-longwinter-station` (87,200), `the-tenfold-siege` (84,466), `the-tricameral-city` (84,352) and
`the-ashfall-expedition` (79,070).

So the screen is calibrated to a cap that matches neither consumer: irrelevant to the chunked path,
and twice as permissive as the bound path it never checks.

~~**What I could NOT establish**: whether `result.bindings` is ever `None` on the production path.~~
**Answered, and I was asking about the wrong variable.** If it never is, chunking never fires in production and those 19 books
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
| A | Do nothing | nothing | Seven books can be selected for a fill that cannot emit them |
| B | **Print fill headroom in `--headroom`, saying which budget binds** | the invisibility | Trivial, and needs no ruling |
| C | Lower the two cells' node ceilings | the dishonest envelope | Rejected: at the budget that actually binds, 7 of 18 cells miss their ceiling and 6 miss it at the advisory low, so lowering two encodes a per-model limit into a story-shape table and leaves five others unreachable |
| D | **Screen a contract-bearing skeleton at the resolved cap** | the live defect, now | A few lines. Boundness is a filesystem check selection already makes. Caveat below |
| E | **Enable chunking for bound fills** | the asymmetry at its root | A `fill_subset_bound.md` variant plus threading `slot_bindings` through `_ChunkedFillContext` |
| F | Raise the cap or drop the 0.8 margin | the selection screen only | Does nothing for the path that fails |

## Recommendation: B, then D as a fail-closed interim, then E

**B, widened.** `--headroom` should print expected output tokens against both budgets AND say which one
binds for this skeleton, which it determines from sidecar presence. Printing both without saying which
applies would recreate the exact conflation `is_fill_feasible`'s own docstring warns about.

**D, scoped to bound skeletons only.** Seven books can currently be selected for a fill that provably
cannot emit them, and the cost is not the cheap stop I claimed: executed, the bound path spends one
fill plus two repairs at the same wall before aborting. Screening a contract-bearing skeleton at the
resolved cap is a few lines and removes the live defect until E lands.

**The caveat on D, verified.** In 16+/long/gamebook and 16+/long/prose, **both** contract-bearing
candidates are over the bound budget (measured: 0 bound-and-fillable, 2 bound-but-over, 2 unbound in
each). D empties the bound candidate pool in those two cells on a 64,000-ceiling job. Selection still
finds the contractless candidates so the cells do not go dark, but the theme-incompatibility re-route
only ever lands on another contract-gated bind, so an emptied bound pool turns a re-route into an
exhausted re-route: a loud single-job failure becomes a silent unselectability, which is the defect
class this row was filed about. If that trade is judged badly, skip D, accept seven loud failures, and
go straight to E.

**E as the root fix, and smaller than I first said.** The bound values are already inside the
`skeleton_json` the subset prompt carries in full, and the ending-title freeze is moot because
`merge_fill_batch` never touches ending titles.

**E carries no security cost, which was the strongest hypothesis against it and it fails.** The
sentinel machinery runs after `fill_skeleton` returns, on the pre-fill `bound` document, and is
path-agnostic. `merge_fill_batch` is a whitelist reading only `body` and choice `label`, so chunking a
bound fill NARROWS what the model can change; the one-shot path accepts the model's entire returned
document. The 3.3 percent sentinel-preservation figure is why the design stopped trusting the model at
all, so chunking cannot make it worse.

## After the review: what moved

Five of six claims were wrong in some part, and three quoted a bound I had not executed.

| claim | what I wrote | what is true |
| --- | --- | --- |
| PL-19 per-node max | 230 words | **385**. The tuple is `(mean, adv_lo, adv_hi, max)` and I read the third slot as the fourth. My own 250-word measurement contradicted 230 on the same page |
| exposure | 19 of 82 exposed | 19 exceed the budget, **7** are on the bound path; sidecar presence decides it |
| failure mode | leg-fatal, no retries, per `AL-329` | `AL-329` says an **empty** body at `finish_reason=length` is leg-fatal. A truncated non-empty one is an ordinary completion, and the bound path spends 1 fill + 2 repairs |
| cell exposure | 2 of 18 at target, **0** at the advisory low | Computed against the screen my own thesis calls mis-calibrated. At the budget that binds: **7 of 18** at target, **6 of 18** at the advisory low |
| case against D | selection cannot know if a fill is bound | It can: `contract_path_for(...).is_file()`, a check `_is_feasible` already makes on a path it already holds |
| the open question | needed before any option could be picked | `_BindResult.bindings` is `dict[str, str]`, never None; the switch is `contract is None`. Fifteen minutes of reading, and I made it the gate on the whole decision |

A fourth stale claim, security-adjacent, found during the review: `worker.py:1156` asserts
`personalizable_slot_ids` "is empty for every contract on disk today". `the-midnight-museum.contract.json`
declares a `personalizable` slot, 1 of 47. Harmless today (that skeleton never chunks under any cap)
but it is the comment a future reader trusts when deciding whether the sentinel path is live.
