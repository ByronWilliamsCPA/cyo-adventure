# DeepSeek v4 Pro live fill run: 5-sample plan

**Date**: 2026-08-20
**Status**: complete. 3 of 5 passed; both failed legs re-probed (book 0: deterministic
`content_filter` for its (skeleton, brief) pair, 7 of 7; book 4: passed on re-probe), reviews
done, lessons logged as `AL-490`..`AL-498` with register rows `UW-C307`..`UW-C315`
**Blocks on**: nothing; PR #730 merged 2026-08-20 04:15 UTC
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
5. **Are the books any good, and are they diverse?** The deciding question for the approach, and
   the one no deterministic instrument in this repo answers. Addressed by rungs 7 and 8 in
   section 5.1 rather than by the gate.

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

### 3.5 What actually happened at pre-flight (recorded 2026-08-20)

Sections 3.2 and 3.3 above are the plan as written, and the pin they name is **wrong**. It is
left standing rather than rewritten, because the way it was wrong is the useful part.

`coreweave/fp8` was chosen on declared attributes: fp8 rather than fp4, US-hosted, and the
largest declared output ceiling of the slug's 18 endpoints. `compare_vendors.py`'s pre-flight,
one 512-token completion per pin, refused the run with a persistent HTTP 429 and generated
nothing. Probing every candidate directly with `provider.only` plus `allow_fallbacks: false`
found three failure modes behind what presents as one bad slug:

| Result | Endpoints |
| --- | --- |
| `429`, persistent | `coreweave/fp8`, `parasail/fp8`: the only two declaring a 1,048,576 ceiling |
| `404` "no endpoints available matching your guardrail restrictions and data policy" | `alibaba/fp8`, `baidu/fp8`, first-party `deepseek` |
| `200` | `azure/us`, `novita/fp8`, `siliconflow/fp8`, `ionstream/fp4` |

Two lessons, both of which would have cost the next person the same hour:

1. **The most capable endpoints on paper are the two that will not serve this account.** Endpoint
   selection cannot be done from the models endpoint's declared attributes; it has to be probed.
   A 512-token probe per candidate costs cents and is now the documented first step.
2. **Section 3.3's data-residency argument was moot.** It argued against first-party DeepSeek on
   residency grounds; the account's own data policy already blocks that endpoint, along with both
   China-hosted resellers. The policy had made the decision the note presented as a judgement
   call. Checking the policy would have been faster than reasoning about it.

Pinned instead to `azure/us`: reachable, US-hosted, matching the posture the data policy
expresses, and the same reason `vendors.json` pins its OpenAI leg to Azure. Its 384,000 ceiling
is ample against the 131,072 resolved cap, so section 4.2's analysis is unchanged. Two costs
recorded rather than glossed: `quantization` is `unknown`, so this leg is not
quantization-attributable the way an fp8 pin would be; and at $1.91/$3.83 it is the most
expensive reachable option against `novita/fp8` at $1.44/$2.88, which raises the run's estimate
from about $1.03 to about $1.54. On a run of that size, hosting is worth more than the premium.

The price row follows the pin, not the slug default, so the recorded cost is what was actually
paid. **The vendor file and the price row must change together**; both name `novita/fp8` as the
hand-fallback if Azure rate-limits.

## 4. The five samples

### 4.1 The grid

Skeletons pair index-wise with briefs. Slots 1 and 2 are the same skeleton, satisfying the
"at least two use the same skeleton" requirement at the cell where it is most informative.

| # | Skeleton | Cell | Nodes | Declared words | Est. output tok | Why this one |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 0 | `16+/the-last-cartage.json` | 16+ gamebook long | 632 | 49,953 | 99,906 | Largest in the catalog; 95.3% of the feasibility ceiling |
| 1 | `16+/the-last-cartage.json` | 16+ gamebook long | 632 | 49,953 | 99,906 | **Same skeleton, different brief**: the noun-substitution test |
| 2 | `13-16/the-quarry-signal.json` | 13-16 gamebook medium | 267 | 18,888 | 37,776 | The only tier-2 stateful book of the 20; exercises `CG-5` and state-aware `PL-20/25/26` |
| 3 | `8-11/the-tin-whistle-map.json` | 8-11 prose long | 193 | 19,574 | 39,148 | Mid-band prose; the band-envelope and Stage D reading-level path |
| 4 | `3-5/the-last-blue-cup.json` | 3-5 prose short | 17 | 674 | 1,348 | Tightest envelope in the system (40-word mean, 90-word per-node max) |

The pair sits on `the-last-cartage` deliberately. It is the hardest cell, the one whose stale
headroom claim #730 corrected, and the one where a same-structure pair is most likely to
converge, because 632 nodes of fixed structure give the model the least room to differ. If the
pair diverges there, it diverges anywhere. Cost makes this affordable: see 4.3.

### 4.2 Conditions

- **Model**: `deepseek/deepseek-v4-pro`, pinned to `coreweave/fp8`, `allow_fallbacks: false`
  (superseded before execution: pre-flight probes found `coreweave/fp8` persistently 429 and the
  run executed pinned to `azure/us`; see section 3.5)
  (the adapter sends this alongside `provider_order`).
- **Output cap**: leave `--max-tokens` unset. `resolve_output_cap` yields
  `min(131_072, 393_216) = 131_072`; every book in the grid fits. Forcing a cap would make the
  results non-comparable to the shipped configuration, and see F1 for why it would not buy the
  chunked path either.
- **Throttle**: `--throttle 3`.
- **Repairs**: orchestrator default (3).

### 4.3 Expected cost

Superseded pre-flight estimate, kept for the record: it was computed at the original
`coreweave/fp8` price of $1.15 in / $2.55 out per MTok, and the run executed on `azure/us` at
$1.91/$3.83 (see section 3.5), which raised the estimate to about $1.54; the measured figure
in section 5.2 is $1.9943. Input being the skeleton itself:

| # | Input tok | Output tok | First-pass cost |
| --- | ---: | ---: | ---: |
| 0 | ~99,400 | ~99,900 | ~$0.37 |
| 1 | ~99,400 | ~99,900 | ~$0.37 |
| 2 | ~36,400 | ~37,800 | ~$0.14 |
| 3 | ~35,300 | ~39,100 | ~$0.14 |
| 4 | ~2,100 | ~1,300 | ~$0.01 |
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

### 5.1 Quality and diversity review (rungs 7 and 8)

Rungs 1 through 6 are deterministic instruments, and not one of them can say whether a book is
any *good*. `evaluate_books.py` says so about itself: the vendor comparison "deliberately says
nothing about whether a book is any good, and the one quality signal it does carry (a
Flesch-Kincaid grade) is easy to over-read". Since a stated goal of this run is to establish
whether the approach produces **high-quality, diverse** books, the ladder needs two rungs that
read the prose rather than measure it.

| Rung | Reviewer | Question | Output |
| --- | --- | --- | --- |
| 7 | One Fable subagent per book | Is this a good story? Editorial judgement on prose quality, voice, beat delivery, ending earned or asserted, band fit | Per-book editorial review |
| 8 | One Sonnet subagent per book | Does this book meet every stated criterion? Band envelope, structure preserved, no residual directives, fail-state policy, reading level, theme fidelity | Per-book pass or fail against a criteria checklist |

The split is deliberate and the two must not be merged. Rung 8 is a compliance question with
right answers, checkable against the skeleton and the band table; rung 7 is a judgement that has
no ground truth and would be corrupted by being scored on a checklist. Running one reviewer for
both invites the checklist to stand in for taste, which is the failure mode that makes a book
gate-clean and unreadable.

Two constraints on rung 7, both of which shape the prompt:

- **The reviewer must not see the other book of the pair.** Books 0 and 1 share a skeleton, so a
  reviewer holding both would grade divergence rather than quality, which is rung 3's job and is
  already measured deterministically. Per-book reviews stay independent; the pair comparison is
  drawn afterwards from the two reviews plus the sibling-fill number.
- **Books are large.** `the-last-cartage` is 632 nodes; a reviewer cannot read it as a whole and
  should not pretend to. The prompt directs sampling along a reader's actual path (start node,
  one full walk to an ending, plus a spread of endings) rather than skimming everything.

One condition that must be reported alongside rung 7's findings: `compare_vendors.py` passes no
`differentiation_directive`, so it defaults to empty. That block is the pipeline's trusted
instruction for exactly the case where a family already owns another story on the same skeleton.
The pair therefore measures the **raw convergence floor the directive exists to counter**, not
production behavior. That makes it the right baseline and the wrong number to quote as what a
reader would receive.

## 5.2 Results (run of 2026-08-20)

### Outcome

| # | Skeleton | Band | Status | FK | In band | Latency | Cost |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: |
| 0 | the-last-cartage | 16+ gb | **error** (transient empty 200) | - | - | 398s | unmetered |
| 1 | the-last-cartage | 16+ gb | passed | 6.67 | 15.5% | 1874s | $1.064 |
| 2 | the-quarry-signal | 13-16 gb | passed | 3.86 | 5.6% | 687s | $0.538 |
| 3 | the-tin-whistle-map | 8-11 prose | passed | 4.01 | **73.1%** | 469s | $0.350 |
| 4 | the-last-blue-cup | 3-5 prose | **error** (`content_filter`) | - | - | 48s | $0.042 |

Three of five passed. Harness cost $1.9943 against an OpenRouter-measured $2.0396,
so the accounting is accurate to about two percent.

### The root cause: the `words=` directive is not honored

Every passing book delivered 39 to 53 percent of its commissioned words, and none had a
single node over its PL-19 per-node maximum.

| Book | Nodes | Commissioned | Delivered | Ratio | Story mean vs advisory | Below floor |
| ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 1 | 632 | 49,953 | 19,423 | 38.9% | 30.7 vs 55-110 | 631/632 |
| 2 | 267 | 18,888 | 9,997 | 52.9% | 37.4 vs 45-90 | 245/267 |
| 3 | 193 | 19,574 | 8,353 | 42.7% | 43.3 vs 70-135 | 191/193 |

Per-node correlation between commissioned and delivered words is 0.527, -0.027 and
-0.405. Book 3 is the sharpest: nodes commissioning 100-124 words returned a mean
of 40.7 while nodes commissioning 75-99 returned 51.5, so there the directive is
anti-correlated rather than merely ignored. Delivered length is near-constant per
book (means 30.7, 37.4, 43.3; sd 5 to 9) against commissioned ranges of 40 to 112.
An initial hypothesis that delivery degrades with node count is **disproven**:
632 nodes gave 38.9 percent, 267 gave 52.9, 193 gave 42.7.

### That one cause explains the reading-level split

Short choppy prose lands at low Flesch-Kincaid, so the low band conforms by
accident and the high bands cannot. Book 3 (8-11, target near 4.5) reached 73.1
percent of nodes in band; book 2 (13-16, target 7.0) got 5.6 percent and book 1
(16+, target 9.0) 15.5 percent. **The higher the band, the worse the same defect
reads.** This is a single defect with a band-dependent symptom, not three
problems.

### The gate measured all of it and blocked on none

Book 1's gate run: `findings=456 blocked=False`, exit 0, zero repair attempts.
447 `RL-13`, 7 `CG-4`, 1 `PL-23`, 1 `PL-19`. `PL-19` named the shortfall exactly,
"story-mean 30.7 words/node is outside the band '16+' gamebook advisory 55-110",
and `PL-23` caught the consequence, a declared 16-minute read against a derived 6.
Both are WARNING severity by design: `per_node_max` is an ERROR for every story
while the story-mean advisory is not, and `band_profile.py` states the reasoning,
"There is no hard per-node minimum: a one-line beat is legitimate." Defensible per
node; it composes into a book-level shortfall nothing blocks on.

### Structural drift on fields the contract freezes

Node-level structure was perfect on every book: zero nodes differing outside
prose. Top-level identity fields drifted anyway, differently each time.

- Book 1 changed the story `id`, `sk_last_cartage` to `sk_last_codex`. `id` is
  explicitly frozen by `fill.md` and import and skeleton-matching key on it.
- Book 2 changed the top-level `title`, and 27 of its 36 `ending.title` values.
- Book 4's probe emitted the correct `id`, so this is sporadic drift, not a
  systematic transform.

`check_fill_integrity.py` catches all of it and exits 1, correctly.

**`ending.title` is genuinely ambiguous and three sites disagree.** `fill.md`
freezes only "``id`` on ... any ending block", and `SKILL.md` lists ending titles
alongside bodies and choice labels as slot-bearing theme content, both of which
make a reskin legitimate. But `chunking.py`'s `merge_fill_batch` whitelists only
`body` and choice `label` and explicitly refuses `ending`, and
`check_fill_integrity.py` compares endings too. So a book that legally reskins its
ending titles one-shot **cannot be produced by the chunked path**, which since
`UW-C302` is the degraded path for large and bound fills. The two paths produce
contractually different books. This is the same shape as the four-site FK-target
disagreement ruled on 2026-08-18 and wants the same treatment: one site of record.

`schema_version` differs 2.0 to 2.1 on every book, but the model emits 2.0 and
`Storybook.schema_version` defaults to 2.1, so that is a pipeline stamp and not a
finding. It does mean the integrity check's structure FAIL fires on every filled
book, so its verdict is uninformative until you read which field moved.

### Prose defects the gate cannot see

- **Bodies restate their own `beats=` directive with nouns swapped** rather than
  dramatising it. On book 2, mean content-word overlap between beat and body is
  0.51, with 34 percent of nodes at 0.60 or above and one ending at 1.00.
- **Verbatim duplicate prose.** Book 2 has 23 redundant nodes across 11 repeated
  texts, five of them appearing four times each; `d6_n0` and `d15_n0` are
  byte-identical.
- **Choice labels collapse.** Book 2 has 674 choices and 24 distinct labels; the
  top three account for 605, or 89.8 percent.
- **Incoherent world physics.** Book 1 keeps the mine's hydraulics: sand ponding
  upward from a sump like water, and a firedamp safety-lamp beat about flame
  telling you late, in a building full of vellum. Book 2 keeps quarry apparatus on
  a lava field and pairs hazards with instructions that do not fit them, "soft,
  warm mud ... Test every rung before you put your weight on it".
- **Prose asserting state it cannot know.** Book 2's `end_fixed_trust1` appends
  "the lamp's last oil burned somewhere your memory will not name yet" to a beat
  that says nothing about the lamp, on a node reachable at `light` 0 through 3.
  The gate passed it. This is the defect the tier-2 book was in the grid to find.

### Diversity is good, and the number is not quotable

Within-vendor shared four-grams came in at mean 0.64 and max 1.34 per 1000 leaf
words, far inside the 4.0 budget. But the three surviving pairs share neither
skeleton nor band, while the 3.3 calibration is for pairs sharing a band, so this
is not comparable to that floor. The shared-skeleton pair the run was designed
around did not happen, because book 0 was the leg that failed.

### The two failures (initial diagnosis; book 0's verdict is superseded below)

- **Book 0**, three attempts each returning HTTP 200 with an empty body,
  `finish_reason=None`, about 130s apiece. Not a size limit: book 1 emitted the
  same 632-node skeleton at the same cap on the same pin. Probes confirmed that
  large input, a large `max_tokens`, and both together all succeed. Called
  transient here; "Corrections established after the first write-up" below
  overturns this to a deterministic (skeleton, brief) content filter, 7 of 7.
- **Book 4**, `finish_reason='content_filter'` on a 3-5 nursery story about a
  missing pair of yellow wellington boots, after 3,227 billed output tokens. A
  content filter firing on the most innocuous book in the grid matters for a
  children's product. **Correction:** an earlier commit message called a
  `content_filter` stop deterministic and said the provider wrongly classified it
  transient. Re-probing the identical prompt returned a complete valid book,
  "The Last Yellow Welly", at `finish_reason=stop`. So the stop is NOT
  deterministic and the transient classification is defensible. What remains is
  that a benign preschool premise trips the filter at all, intermittently.

### Corrections established after the first write-up

**Book 0 is a deterministic content filter, not a transient failure.** A direct
probe of brief 0 against `the-last-cartage` returns `finish_reason:
'content_filter'` with zero content. Counting the three attempts in the run, three
in the re-run (397.59s against 397.96s, near-identical) and the probe, that is
**seven consistent failures**. The earlier reading, that the failure was transient
because book 1 succeeded on the same skeleton, drew the boundary in the wrong
place: the failure belongs to the (skeleton, brief) PAIR. Brief 0 describes
venting a generation ship's agricultural ring and not leaving a living thing
behind, against a 632-node gamebook whose endings include mass death.

So `content_filter` is sometimes deterministic and sometimes not: book 0 fails
7 of 7, book 4 failed three times and then passed. Neither of the two earlier
absolute claims about it was right. The operational consequence is that a brief
can be permanently unfillable against a given skeleton with no signal saying so,
and the harness reports it as a generic transient failure.

**`ending.title` is not the only field in dispute; the band fail-state policy is
too, and that one is about child safety.** `SKILL.md` instructs authors to obey
"no death endings for 3-5 / 5-8". `band_profile.py` disagrees:

| Band | `forbidden_ending_kinds` |
| --- | --- |
| 3-5, 5-8 | capture, death |
| 8-11 | **death** |
| 10-13, 13-16, 16+ | none |

**8-11 forbids death endings and the authoring skill does not say so.** An author
drafting to the skill would believe they are permitted for eight-to-eleven year
olds. Nothing shipped here, since book 3 has zero death endings, but this is the
fourth self-disagreement found in this contract after the four-site FK targets and
the three-site `ending.title` ambiguity, and it is the only one with a safety
dimension. `band_profile.py` is the source of record; `SKILL.md` should cite it
rather than restate it.

**Every book mutated something frozen or ambiguous, and a different thing each
time.** Adding book 3 to the tally: `metadata.themes` changed "music" to
"navigation". `fill.md` freezes `metadata` explicitly. This one is insidious
because it looks helpful, the reskin genuinely has no music in it, but it is a
field the model was told not to touch.

| Book | Frozen or ambiguous field mutated |
| ---: | --- |
| 1 | `id` (frozen) |
| 2 | `title`, 27 of 36 `ending.title` (ambiguous) |
| 3 | `title`, 15 of 35 `ending.title`, **`metadata.themes` (frozen)** |

### An unfilled rule gap: nothing checks that a body stages its OUTBOUND choices

Book 3's `ok_house` offers "Take the canal cap to somebody who knew it" while its
body never mentions a cap; the cap is introduced in a sibling node a reader may
never visit. Another node offers "Split the cut with Sam" where Sam appears only
on an unvisited branch. This is a direct consequence of the word shortfall: the
frozen labels assume a body that stages those objects, and a 43-word fill does
not.

`CG-4` looks like the rule for this and is not. It flags "a decision-child whose
opening sentence shares no content word with its choice label that leads to it",
which is strictly **inbound**: does the arriving node echo the choice just taken.
It did fire on `ok_house`, but for the inbound choice, and nothing in the gate asks
whether a node's prose introduces what its outbound choices promise. Proposed:
an outbound companion to `CG-4`. The defect is reader-visible and a fill this
short produces it systematically.

### A caution on the beats-overlap metric

Book 3 has HIGHER beat-restatement overlap than book 2 (mean 0.668 against 0.51;
67.9 percent of nodes at 0.60 or above against 34 percent) and reads considerably
better. So overlap-with-beats does not order books by quality and should not be
used as a quality proxy. What separated them was elsewhere: book 3 has zero
duplicate bodies and 191 distinct labels across 466 choices, against book 2's 23
redundant nodes and three strings covering 89.8 percent of its choices.

Book 3's own distinguishing defect is not measured by any of these: **"you"
appears in only 12 of its 193 nodes**, against 41 percent in book 1 and 69 percent
in book 2, whose skeleton beats specify second person explicitly. Six nodes drift
into "we". The protagonist is absent from their own story, and no rule looks for
that.

### Method note: two reviewers, and the disagreement was informative

Running an editorial reviewer and a compliance validator separately paid for
itself twice. The validator caught the `id` mutation, which the editorial pass had
no reason to look for. The editorial pass caught the incoherent physics, which
every mechanical check scored as fine.

Where they disagreed, the mechanical verdict was wrong both times, and for the
same reason. On book 2 the validator scored theme fidelity PASS having counted
quarry 0, pit 0, stone 4, rail 3, tower 0; the quarry actually survives as
stope 16, cribbing 14, timber 17, catwalk 18, rung 18, which the editorial pass
found by reading. On book 1 the editorial pass overstated the opposite case,
citing dune 1 and desert 0 while missing sand 220 and scriptorium 104. **A
mechanical noun-substitution check is only as good as its hand-picked word list**,
and the honest reading of book 1 is that surface nouns were reskinned densely
while the source theme's apparatus and physics were retained wholesale.

## 5.3 Router comparison (2026-08-20): the shortfall is the prompt, not the model

Built to break the five-fill run's two structural confounds: one endpoint, one
model. Same skeleton (`the-tin-whistle-map`, 193 nodes, 19,574 commissioned
words) and the same two briefs that produced the 96.3 sibling floor in 5.2, so
the only things that move are the model and the endpoint serving it.
`docs/planning/vendor-comparison/briefs-router-comparison.json` is byte-identical to
`docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/shared-skeleton-pair/briefs.json`,
which is what makes the DeepSeek column below a matched control rather than a
different measurement.

Artifacts: `docs/planning/vendor-comparison/runs/router-comparison-2026-08-20/report.json`,
`books.jsonl`, `books/anthropic-sonnet-5__0{0,1}.json`,
`sibling-fill-check-sonnet.txt`, and the run config
`docs/planning/vendor-comparison/vendors-router-comparison-2026-08-20.json`.

| Metric | DeepSeek @ `azure/us` | DeepSeek @ `novita/fp8` | Sonnet 5 @ `bedrock` | GLM-5 @ `z-ai` | Budget |
| --- | ---: | ---: | ---: | ---: | ---: |
| Books passed (of 2) | **2** | 0 | **2** | 0 | - |
| Delivery ratio | **42.9-65.2%** | n/a | 40.9-45.2% | n/a | 100% |
| In-band nodes | **75.1-77.2%** | n/a | 60.1-64.2% | n/a | - |
| Sibling 4-grams per 1000 | **96.3** | n/a | 326.3 | n/a | 4.0 |
| Cost per book | $0.371 | $0.242 (1 of 2 metered) | $3.498 | $0.380 | - |
| Latency per book | **690s** | 1,712s | 2,519s | 1,594s | - |

The DeepSeek column is the shared-skeleton pair from 5.2 (`brief_index` 0 and 1
of `shared-skeleton-pair/report.json`), which is the matched control. An earlier
draft of this section sourced its in-band, cost and latency cells from the
five-fill run's single tin-whistle book (`brief_index` 3: 73.1%, $0.35, 469s)
instead. That book answers a different brief and is not comparable to the Sonnet
pair; the figures above replace it.

### The decisive result: model selection will not fix the word shortfall

Sonnet 5 delivered **40.9 and 45.2 percent** of commissioned words, a mean of
**43.1 percent**. On identical inputs DeepSeek delivered **65.2 and 42.9
percent**, a mean of **54.0 percent**. Both fall far short of the `words=`
directive, and the Sonnet leg bought its shortfall at 9.4 times the cost per book
and 3.7 times the latency.
**The shortfall is a property of the prompt, not of the model**: two independent
frontier models from different labs both under-deliver by a wide margin, so
there is no model to switch to that closes the gap.

Note what this does *not* say. DeepSeek delivered about 25 percent more words
than Sonnet on the same skeleton and briefs (21,150 against 16,855 across the two
books), so the two are not tied; the point is that the better of the two still
misses the directive by 46 percent.

That settles `UW-C307`'s direction and removes an option from the fix list before
anyone spends a sprint on it: switching the fill model buys nothing that closes
the delivery gap. The fill-rate gate is correctly aimed as a detector, but the
remedy has to be prompt-side.

### Sibling convergence is WORSE on the stronger model

Sonnet's two books on one skeleton scored **326.3 shared four-grams per 1000 leaf
words against a 4.0 budget**: 3,800 shared grams and 466 shared menu frames,
against DeepSeek's 1,350 and 274. That is 3.4 times DeepSeek's convergence and 81
times budget. So `AL-498` is not a DeepSeek defect, it is worse on the better
model, and no vendor rotation addresses it.

This particular comparison is a hand synthesis across two separate `report.json`
files, not a single tool output. `compare_vendors.py` computed only the
`within_vendor` cell for `anthropic-sonnet-5`; every cross-vendor cell in this
run's report is `0.0` and its `verdict` field reads
`not measured: need both within-vendor and cross-vendor pairs`, because the two
non-Anthropic legs produced no books to pair against. Do not read 326.3 against
96.3 as something the tool emitted.

### Only one of three legs could complete a fill at all

Both failing legs died the same way, on `finish_reason=length` with the output
budget consumed before any usable content came back. The metered reasoning splits
are DeepSeek on Novita 8,608 on its first book, and GLM-5 58,924 then 108,775.
Novita's second book is **unmetered**: its `output_tokens`, `reasoning_tokens`
and `cost` are all `null`, with `cost_unavailable_reason` recorded as "no
provider call was metered for this book". The "131,072 of them on reasoning"
figure for that book exists only inside the provider's error *string*, and that
string is not a reliable channel: it reports 8,192 reasoning tokens for both GLM
books where the metered fields say 58,924 and 108,775, understating them by 7x
and 13x. What was observed for that book is that the budget was exhausted and
nothing usable returned; the reasoning split is unmeasured.

Sonnet reasons heavily too (164,388 of 303,996 output tokens on book 0) and still
delivered, so reasoning is not disqualifying by itself; spending the whole budget
on it is. `is_fill_feasible` derives its estimate from `words=` directives and
therefore models content tokens only, so it is blind to this by construction.

### The counterintuitive conclusion

**DeepSeek v4 Pro on `azure/us` is the best leg tested**, on delivery ratio,
reading-level conformance, sibling diversity, cost and latency simultaneously.
The run was designed expecting to find that DeepSeek was the weak link. It is the
strongest of the three, and the defects the five-fill run attributed to it are
properties of the prompt and the skeleton-reuse strategy.

### Cost of this comparison

Harness reported $7.9979 over 5 priced books, 1 of 6 unmetered. OpenRouter's own
accounting puts the session at $11.4431 total. The gap is the unattributed
failed-leg spend: the three metered failures billed $1.0022 between them
(DeepSeek/Novita 41,038 output tokens; GLM-5 99,606 and 157,966), and the fourth
failure, Novita's second book, billed an unrecorded amount over 2,904 seconds.

### Two caveats on the artifacts

- `excluded_incomplete` is `[]` in this run's report while four books were in
  fact incomplete, so that field is not a usable exclusion record here.
- This report predates the `differentiation_directives` key that later reports
  carry, so a diff against a newer run will show that field missing rather than
  null.

### Lessons from this leg

Two lessons come out of 5.3: the prompt-not-model finding above, and the sibling
convergence result. Both are held for a single later consolidation pass so their
ids are assigned once, in sequence, against the current maxima of the lessons log
and the register. Until that lands, this section is their record.

## 6. Findings from planning

Five things surfaced while building this plan that are worth recording independently of the run.

### F1. The chunked bound path cannot be exercised by this run, and `--max-tokens` will not help

`fill_skeleton` derives its own cap for the chunking decision from the **provider's model**:

```python
cap = resolve_output_cap(resolved_model)  # provider.model outranks settings
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
- Register rows for any section 8 open item the owner rules in scope; the row is the
  completion record, per the register's linkage contract

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

**Post-run addendum (2026-08-20)**: the run executed, and the paragraph above now describes
only the pre-run plan. Nine lessons are logged as `AL-490` through `AL-498` in
`docs/planning/authoring-lessons-log.md`, each cited by its register row `UW-C307` through
`UW-C315` in `docs/planning/unscheduled-work-register.md`.
