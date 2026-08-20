# DeepSeek v4 Pro live fill run: 5-sample plan

**Date**: 2026-08-20
**Status**: planned, not yet executed
**Blocks on**: PR #730 merging to `main`
**Predecessor**: PR #730 (`feat(catalog): cover all 18 offered cells at the strict bar`), whose
"Follow-up handoff" names this run as the intended next task
**Branch**: `claude/pr-730-deepseek-testing-3m9c3v`

---

## 1. Why this run exists

PR #730 closed `UW-C302` by giving a bound fill a chunked path, and brought the skeleton catalog
to 20 strict-passing books covering all 18 offered production cells. Both are validated by unit
tests and by the offline strict census. Neither has been validated against a real backend: the
PR's own handoff note records that egress to `openrouter.ai:443` was denied by the authoring
session's network policy, so the live end-to-end fill could not run.

**That constraint no longer holds.** Verified from this session on 2026-08-20:

| Check | Result |
| --- | --- |
| `GET https://openrouter.ai/api/v1/models` | `200` |
| `OPENROUTER_API_KEY` in environment | present |
| `deepseek/deepseek-v4-pro` on OpenRouter | present, 1,048,576 context, 18 endpoints |

So the run is executable. This document is the plan for it.

## 2. What the run must prove, and what it cannot

**In scope.** Five live fills answer four questions that no offline check can:

1. **Does the strict-clean catalog actually fill?** Twenty skeletons pass `--strict` at exit 0.
   Passing the shell gate says the structure is authorable; it does not say a real model will
   emit prose that then passes the gate. This is the PR's single largest untested claim.
2. **Does a shared skeleton yield two genuinely different books?** The cyo-author contract
   forbids noun-substitution (prose that would fit any theme after a find-and-replace is a
   defect). Nothing has tested that contract against a live model on one skeleton with two
   briefs. This is what the "at least two on the same skeleton" requirement buys.
3. **What does a near-cap book actually cost, in tokens and in repairs?** `the-last-cartage`
   needs 99,906 declared output tokens against a feasibility ceiling of 104,857, that is 95.3
   percent of it. The `_FEASIBILITY_MARGIN = 0.8` constant exists because `AL-328` measured a
   leg at 91 percent of its cap and it truncated. The top of the catalog now sits above that
   measurement, with no live datapoint.
4. **Do the new state-aware rules hold on live prose?** `CG-5`, and the state-aware `PL-20`,
   `PL-25`, `PL-26`, were written and tested against committed shells. A tier-2 stateful book
   filled live is the first prose they will grade.

**Explicitly out of scope, and why.** Two production-parity gaps are structural in the chosen
harness and must not be reported as covered:

- **The Stage 1 fidelity gate does not run.** `compare_vendors.py` calls
  `fill_skeleton(..., stage1_gate="skipped")`. The production path (`generation/worker.py`)
  runs it. So this run measures the deterministic gate, not the fidelity gate.
- **The chunked bound path is not reachable.** See finding F1 below; it cannot be exercised
  by any combination of flags on this harness with this model. The `UW-C302` fix therefore
  remains unvalidated live after this run. That is a scope limit, not a defect in the fix.

Both gaps are carried into section 8 as named follow-ups rather than quietly absorbed.

## 3. Pre-flight, in order

### 3.1 Rebase onto merged `main` (blocking)

The 20 strict skeletons, `fill_subset_bound.md`, and the `chunked = not is_fill_feasible(...)`
switch are all on PR #730's head and absent from this branch. Confirmed by inspection: this
branch carries 82 skeletons and no `templates/fill_subset_bound.md`; #730's head carries 102.

Running before the rebase would test the old, broken path and produce a result that reads as a
verdict on the new one.

```bash
git fetch origin main
git rebase origin/main          # after #730 merges
uv sync --all-extras
```

### 3.2 Add the price row for `deepseek/deepseek-v4-pro` (blocking)

`core/pricing.py` has rows for `deepseek/deepseek-v4-flash`,
`~deepseek/deepseek-v4-flash-latest`, and `deepseek/deepseek-v4-flash-0731`. It has **no row
for any v4-pro spelling**. `compare_vendors.py` refuses to start when a leg has no complete
price, which is correct behavior and traces to `AL-348` (twenty generations recorded
`cost: null`). Do not paper over it with `--allow-unpriced`: a run whose whole point includes
per-book economics must be able to price itself.

```bash
uv run python scripts/refresh_pricing.py --model deepseek/deepseek-v4-pro
# paste the dated entry into core/pricing.py
```

Read live 2026-08-20, the slug's default route prices at $1.44 in / $2.88 out per MTok.
**Caveat, and it is not cosmetic:** `pricing.py` is keyed on `(provider, model)`, so it holds
one price per slug, while OpenRouter serves this slug from 18 endpoints priced from $0.66 to
$1.91 in. Pinning CoreWeave (section 4.2) means the recorded cost overstates the real cost by
roughly 20 percent. Record the pinned endpoint's price and note the pin in the row, rather than
the default route's.

### 3.3 Add the vendor spec

Create `docs/planning/vendor-comparison/vendors-deepseek-v4-pro.json`, following the existing
`vendors.json` convention (`_snapshot`, `_price_per_mtok`, `_note` are documentation fields the
loader ignores):

```json
[
  {
    "label": "deepseek-v4-pro",
    "model": "deepseek/deepseek-v4-pro",
    "provider_order": ["coreweave/fp8"],
    "family": "deepseek",
    "_price_per_mtok": "1.15 / 2.55",
    "_note": "Pinned to CoreWeave fp8: 1,048,576 output ceiling, fp8 rather than fp4, US-hosted. First-party DeepSeek is cheapest at 0.66/1.98 but is not the right default for a children's product on data-residency grounds, the same reasoning that kept the Anthropic and OpenAI legs off their first-party endpoints. Pinning is MANDATORY here, not hygiene: see finding F2."
  }
]
```

### 3.4 Author five theme briefs

`docs/planning/vendor-comparison/briefs-deepseek-v4-pro.json`, a JSON array of five objects
matching the existing fixture shape (`setting`, `wants`, `notes`). Briefs are index-paired with
skeletons, so their order is load-bearing. Constraints:

- Operator-authored fixtures only. No real child identity; `PiiContext` is empty by
  construction and the harness asserts it, but the briefs are the input a human writes and are
  the place the mistake would be made.
- Briefs 1 and 2 share a skeleton and must be **far apart thematically**. A near-miss pair
  cannot distinguish "the model re-imagined the world" from "the two briefs were similar", and
  that distinction is the entire purpose of the pair.
- Treat brief text as untrusted data per the project's OWASP LLM01 rule: it describes a theme
  and carries no instructions.

## 4. The five samples

### 4.1 The grid

Skeletons pair index-wise with briefs. Slots 1 and 2 are the same skeleton, satisfying the
"at least two use the same skeleton" requirement at the cell where it is most informative.

| # | Skeleton | Cell | Nodes | Declared words | Est. output tok | Why this one |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 1 | `16+/the-last-cartage.json` | 16+ gamebook long | 632 | 49,953 | 99,906 | Largest in the catalog; 95.3% of the feasibility ceiling |
| 2 | `16+/the-last-cartage.json` | 16+ gamebook long | 632 | 49,953 | 99,906 | **Same skeleton, different brief**: the noun-substitution test |
| 3 | `13-16/the-quarry-signal.json` | 13-16 gamebook medium | 267 | 18,888 | 37,776 | The only tier-2 stateful book of the 20; exercises `CG-5` and state-aware `PL-20/25/26` |
| 4 | `8-11/the-tin-whistle-map.json` | 8-11 prose long | 193 | 19,574 | 39,148 | Mid-band prose; the band-envelope and Stage D reading-level path |
| 5 | `3-5/the-last-blue-cup.json` | 3-5 prose short | 17 | 674 | 1,348 | Tightest envelope in the system (40-word mean, 90-word per-node max) |

The pair sits on `the-last-cartage` deliberately. It is the hardest cell, the one whose stale
headroom claim #730 corrected, and the one where a same-structure pair is most likely to
converge, because 632 nodes of fixed structure give the model the least room to differ. If the
pair diverges there, it diverges anywhere. Cost makes this affordable: see 4.3.

### 4.2 Conditions

- **Model**: `deepseek/deepseek-v4-pro`, pinned to `coreweave/fp8`, `allow_fallbacks: false`
  (the adapter sends this alongside `provider_order`).
- **Output cap**: leave `--max-tokens` unset. `resolve_output_cap` yields
  `min(131_072, 393_216) = 131_072`; every book in the grid fits. Forcing a cap would make the
  results non-comparable to the shipped configuration, and see F1 for why it would not buy the
  chunked path either.
- **Throttle**: `--throttle 3`.
- **Repairs**: orchestrator default (3).

### 4.3 Expected cost

At the pinned endpoint's $1.15 in / $2.55 out per MTok, input being the skeleton itself:

| # | Input tok | Output tok | First-pass cost |
| --- | ---: | ---: | ---: |
| 1 | ~99,400 | ~99,900 | ~$0.37 |
| 2 | ~99,400 | ~99,900 | ~$0.37 |
| 3 | ~36,400 | ~37,800 | ~$0.14 |
| 4 | ~35,300 | ~39,100 | ~$0.14 |
| 5 | ~2,100 | ~1,300 | ~$0.01 |
| | | | **~$1.03** |

Worst case, every book taking all three repairs, is roughly four times that: about **$4**. Cost
is not a constraint on this run and should not shape its design. Record the measured figure
against this estimate; a large miss is itself a finding, since `UsageLedger` bills repairs to
the book that caused them.

### 4.4 Command

```bash
uv run python scripts/compare_vendors.py \
  --skeleton skeletons/16+/the-last-cartage.json \
  --skeleton skeletons/16+/the-last-cartage.json \
  --skeleton skeletons/13-16/the-quarry-signal.json \
  --skeleton skeletons/8-11/the-tin-whistle-map.json \
  --skeleton skeletons/3-5/the-last-blue-cup.json \
  --briefs docs/planning/vendor-comparison/briefs-deepseek-v4-pro.json \
  --vendors docs/planning/vendor-comparison/vendors-deepseek-v4-pro.json \
  --throttle 3 \
  --out docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20
```

Rehearse first with `--mock --vendors <same file>`, which exercises the analysis path at zero
cost and, by passing the real vendor file, rehearses the actual leg count and family layout
rather than a generic stand-in.

**Single-vendor caveat.** `compare_vendors.py` exists to contrast vendors; with one leg its
cross-vendor and same-family buckets are empty by construction and its headline comparison is
undefined. That is expected and is not a failed run. What is used here is its per-book
machinery: provider pinning, the per-book `UsageLedger`, book persistence, the journal, and the
near-cap heuristic. Read `report.json`'s per-book records, not its summary.

## 5. Assessment ladder

Run in this order; each rung answers something the one above cannot.

| Rung | Instrument | Question | Bar |
| --- | --- | --- | --- |
| 1 | `scripts/run_story_gate.py <book>` | Does the filled book pass the deterministic gate? | Exit 0, all five |
| 2 | `scripts/check_fill_integrity.py <skeleton> <book>` | Structure preserved, no `<<FILL>>` left, word stats in band | Clean, all five |
| 3 | `scripts/check_sibling_fills.py <book1> <book2> --check` | **Did the shared skeleton produce two books, or one book twice?** | Default 4.0 shared 4-grams per 1000 leaf words |
| 4 | `scripts/check_prose_craft.py <books...> --check` | Prose defects the gate cannot see | Script defaults |
| 5 | `scripts/evaluate_books.py` | Compliance and prose-character scoring | Recorded, not gated |
| 6 | `report.json` per-book | Cost, attempts, latency, near-cap flag, `fill_completeness` | Compared against 4.3 |

Rung 3 is the run's centerpiece and the reason for the same-skeleton pair. Its budget is
calibrated: the first pilot's obligation arm scores 2.8 per 1000, its control arm 25, its free
arm 12.6. A same-skeleton pair is a **shared-structure** figure and is not the 3.3 quantity the
sibling-fill guard calibrates against, so report it as its own measurement and do not compare it
to that floor.

Rung 1 deserves one warning. A gate failure here is ambiguous between "the model wrote bad
prose" and "the shell gate accepted a skeleton whose fill cannot pass". Separating those needs
the finding read against the skeleton, not just recorded.

## 6. Findings from planning

Five things surfaced while building this plan that are worth recording independently of the run.

### F1. The chunked bound path cannot be exercised by this run, and `--max-tokens` will not help

`fill_skeleton` derives its own cap for the chunking decision from the **provider's model**:

```python
cap = resolve_output_cap(resolved_model)          # provider.model outranks settings
chunked = not is_fill_feasible(skeleton, max_tokens=cap)
```

For v4-pro that is `min(131_072, 393_216) = 131_072`, and the largest skeleton in the catalog
needs 99,906 tokens against the 104,857 feasibility ceiling. So **chunking never fires on this
model for any committed skeleton**.

`compare_vendors.py`'s `--max-tokens` does not change that. It installs a `_CapOverrideProvider`
that forces the cap on the outbound request and explicitly discards the orchestrator's value.
The orchestrator still resolves `cap` from the model and still concludes one-shot is feasible.
So `--max-tokens 30000` produces **truncation, not chunking**: exactly the `UW-C302` failure
mode, reintroduced by the flag intended to probe it.

Compounding it, `compare_vendors.py` passes no `slot_bindings` to `fill_skeleton`, so it fills
raw skeletons and never takes the bound path at all. And all 20 of #730's strict skeletons are
**plain**; the 7 bound-and-over-cap skeletons that motivated `UW-C302` (`the-skyrail-heist`,
`the-year-of-four-banners`, `the-third-shift`, `the-salt-archive`, `the-tricameral-city`,
`the-ashfall-expedition`, `the-pale-road`) are all in the older catalog.

Conclusion: validating `fill_subset_bound.md` live needs a different driver. Carried to 8.1.

### F2. `MODEL_OUTPUT_CAPS` is keyed by slug, but the real output ceiling is per-endpoint

This is the sharpest finding, and it is a live latent defect rather than an observation.
`MODEL_OUTPUT_CAPS` records `"deepseek/deepseek-v4-pro": 393_216`. OpenRouter's endpoints for
that one slug, read 2026-08-20, report output ceilings spanning **two orders of magnitude**:

| Endpoint | max output tokens |
| --- | ---: |
| DeepInfra | 16,384 |
| Venice | 32,768 |
| BaseTen | 262,144 |
| DeepSeek, StreamLake, Azure | 384,000 |
| Ionstream, Alibaba, Novita, SiliconFlow, AtlasCloud, Baidu | 393,216 |
| CoreWeave, Parasail | 1,048,576 |
| DigitalOcean, GMICloud, Together, Fireworks | not declared |

An unpinned request can be routed to DeepInfra at 16,384 while the cap table says 393,216 and
`resolve_output_cap` returns 131,072. `is_fill_feasible` then returns True for every skeleton in
the catalog, the request asks for eight times what the endpoint will emit, and the completion
truncates non-empty. Per #730's own correction to `MODEL_OUTPUT_CAPS`, a non-empty truncation is
not leg-fatal: `openrouter.py` sets `leg_fatal` inside `if not content:`. So it parses as nothing
and burns the whole repair budget, on every retry.

This is the `AL-428` defect ("a missing row on a configured model means the clamp silently does
nothing") in a dimension the table's own design cannot express: the row is not missing, it is
*right for some endpoints and wrong by 24x for others*. The table's documented contract, that
values are "transcribed from the OpenRouter models endpoint", is satisfied by transcribing the
slug's headline number, which is the maximum across endpoints rather than a guarantee.

Two consequences:

1. **For this run**: provider pinning is a correctness requirement, not reproducibility hygiene.
   Stated as such in 3.3.
2. **Beyond it**: any `generation_provider="openrouter"` deployment that does not pin is exposed.
   Worth checking whether the production path pins at all. Carried to 8.2.

### F3. The dated slug has no cap row and declares no ceiling

`deepseek/deepseek-v4-pro-0813` exists on OpenRouter, is absent from `MODEL_OUTPUT_CAPS`, and
reports `max_completion_tokens: null`. It therefore takes the permissive fallback to the full
131,072 default. This is precisely the "dated-model-id trap" #730's comment names; the trap is
still open for this model family. Configuring the dated id, which is the natural thing to do for
reproducibility, silently disables the clamp.

### F4. Three stale-claim corrections in #730 have a fourth sibling

PR #730 corrected `chunking.py`'s largest-skeleton figure to 99,906 tokens, attributing it to
`the-last-cartage`. Confirmed independently here: 632 nodes, 49,953 declared words, 99,906
tokens at 2.0 tokens per fill word. The 4.7 percent headroom against `MAX_FILL_OUTPUT_TOKENS`
is real. Worth noting that this margin is now **thinner than the 20 percent
`_FEASIBILITY_MARGIN` encodes**, so the largest book in the catalog passes the feasibility
screen at 95.3 percent of its ceiling, in the region `AL-328` measured a truncation at (91
percent). #730 flagged raising the constant as a live question; this run will produce the first
live datapoint bearing on it, which is an argument for keeping `the-last-cartage` in the grid.

### F5. `compare_vendors.py` skips the Stage 1 fidelity gate unconditionally

`stage1_gate="skipped"` is hardcoded at the call site, with no flag. For a vendor comparison
that is defensible: the fidelity gate would add cost and variance to a measurement about prose
idiom. For an end-to-end validation it is a real parity gap, and the harness gives no way to
close it. Carried to 8.1.

## 7. Deliverables

- `docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/report.json` plus `books/`
- A results section appended to this document: the assessment ladder's six rungs, measured cost
  against section 4.3, and the sibling-fill number with its interpretation
- Lessons appended to `docs/planning/authoring-lessons-log.md` (see section 9)
- Register rows for anything from section 8 that the owner rules in

## 8. Open items for the owner

### 8.1 How to validate the `UW-C302` fix live (recommend: option B)

Per F1 and F5, the chunked bound path and the Stage 1 gate are both unreachable on this harness.
Three ways forward:

- **A. Accept the gap.** The fix has unit coverage and `test_a_bound_skeleton_over_a_models_cap_is_still_a_candidate`.
  Cheapest; leaves the path that #730 identifies as having failed on seven committed skeletons
  with no live datapoint.
- **B. Add two flags to `compare_vendors.py`** (`--stage1-gate`, and bound-fill support that
  reads a `.contract.json` sidecar and passes `slot_bindings`), then run a sixth fill against one
  of the seven exposed skeletons on a low-cap model such as `deepseek/deepseek-v3.2` (65,536,
  giving a 52,429-token budget) so chunking genuinely fires. **Recommended**: small, reuses the
  metered and persisted harness, and produces the missing datapoint rather than arguing about it.
- **C. Drive the worker path directly.** Highest parity, highest setup cost (Redis, RQ, a
  `StoryRequest` row). Right eventually, disproportionate for one datapoint.

### 8.2 Does the production path pin its OpenRouter endpoint? (F2)

Needs checking against `generation/providers/openrouter.py` and `core/config.py`. If it does
not, the exposure in F2 is live in production and the remedy is a decision between pinning and
making `MODEL_OUTPUT_CAPS` endpoint-aware. Recommend filing a `UW-C*` row once established;
this plan does not assume the answer.

### 8.3 Carried forward from #730, unchanged by this run

- The two 16+/long cells still cannot reach their declared node ceiling at the band word target
  (655 against 750; 300 against 345). An owner call between lowering the ceilings and stating
  that the top of those envelopes needs a below-target word mean (`UW-C302`).
- `L1-7`'s branch-depth finding reports a bare graph-wide scalar with no path and no node
  (`UW-C306`).

## 9. Lessons log

The project rule is that an authoring run appends its lessons to
`docs/planning/authoring-lessons-log.md`, and that a lesson not yet `applied`, `rejected`, or
`superseded` must also be cited by a `UW-C*` row in the unscheduled work register.

**No log entries are appended by this plan**, deliberately. This is planning, not a run: the log
is validated by `check_lessons_log.py` and cross-checked by `check_work_linkage.py`, and filing
open lessons now would create register obligations for findings the owner has not yet ruled on.
F1 through F5 are staged in section 6 and become log rows, with their register rows, when the
run executes and its outcome is known. F2 is the one that will qualify regardless of the run's
result; it is a defect in the shipped configuration, not a lesson about authoring.
