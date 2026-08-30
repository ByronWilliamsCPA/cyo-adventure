# V7: adversarial validation of the fill-stage cluster

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/tmp/claude-0/-home-user-cyo-adventure/95fe99a0-.../scratchpad/` (including the `v7_econ.py` harness).
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.
>
> **This report's standing correction is also void, and now points backwards.** It corrects the
> fill-stage numbers on the grounds that they were derived from DeepSeek V4 Pro while production ran
> `anthropic/claude-haiku-4.5`. `3ad864a3` (#747, 2026-08-24) set `core/config.py:490` to
> `deepseek/deepseek-v4-pro`, so production now runs the model this report says the figures were
> wrongly derived from.

Target: synthesis section 4.3 and recommendations #2/#3 in
`docs/planning/cyo-brief-gap-analysis-2026-08-22.md`; prior findings C2-* (all), C5-8/9/10/11/14,
C6-1/C6-12.

Everything below was re-derived in this repo. Where I computed a number I ran the project's own
functions against the committed catalog; the scripts are in
`/tmp/claude-0/-home-user-cyo-adventure/95fe99a0-cfc0-5263-8504-f7a4f8df5262/scratchpad/`
(`v7_input.py`, `v7_oneshot.py`, `v7_econ.py`, `v7_cost.py`, `v7_fillrate.py`, `v7_pool.py`).

**Standing correction that reframes the whole cluster.** Every cost, cap and chunking number in
section 4.3 is derived from the DeepSeek V4 Pro run at cap **131,072**, which one-shots every
skeleton in the catalog. Production ships `openrouter_model = "anthropic/claude-haiku-4.5"`
(`core/config.py:459`) whose row in `MODEL_OUTPUT_CAPS` is **64,000**
(`generation/skeleton.py:258`), which chunks **19 of 84** skeletons (I reproduced exactly that
count) and costs roughly a third as much. The review is pricing and diagnosing a configuration
that is not deployed. This is not a quibble: it moves C2-3 from "594k tokens, over the window"
to "2-3 skeletons, 96-109% of the window", and it moves the machine cost from $1.45 to
$0.22/book at the fill stage.

---

## Claim 1 (C2-4): `llm_timeout_seconds = 120` against fills of 469-1874s

**Verdict: mechanism half-confirmed, consequence NOT ESTABLISHED and contradicted by the
project's own latency records. The synthesis's "every large fill times out" is false as written.**

### What is verified

- `llm_timeout_seconds: int = 120` at `src/cyo_adventure/core/config.py:507`. Reaches
  `OpenRouterProvider(timeout_seconds=...)` unchanged via `generation/provider.py:435` and
  `:472` (both `build_openrouter_leg` and `build_anthropic_leg`).
- It is **per HTTP call**, not per book and not per chunk-set:
  `providers/openrouter.py:236` does `async with httpx.AsyncClient(timeout=self._timeout_seconds)`
  around one non-streamed `client.post`. Design intent confirms it:
  `docs/planning/phase-2b-live-provider.md:143`: "120 s per `complete()` call".
- `httpx.TimeoutException` -> `ProviderError(leg_fatal=False)` at
  `providers/openrouter.py:238-245`, i.e. transient, so `run_with_retries`
  (`providers/_base.py:216-291`, `DEFAULT_MAX_RETRIES = 3`, backoff 4s then 8s) retries three
  times, then `FallbackProvider` walks to `openrouter_fallback_model` (Sonnet 4.6) then to the
  Ollama leg (`qwen2.5:14b`). All confirmed at `generation/provider.py:721-734`.

### What refutes the consequence

**The 469-1874s figures are per-BOOK wall clock summed over dozens of calls, not per-call.**
Book 1 (`the-last-cartage`, 632 nodes) recorded `output_tokens: 154,253` against a cap of
131,072, arithmetically impossible in one call. Decomposing it:

| component | calls | evidence |
|---|---:|---|
| fill (one-shot at cap 131,072; `is_fill_feasible` returns True) | 1 | I ran `is_fill_feasible(sk, 131072)` -> True |
| reading-level loop | ~72 | `_BATCH_SIZE = 12` (`reading_level_loop.py:80`), 2 passes (`orchestrator.py:144`), `in_band = 0.155` -> ~534 out-of-band nodes -> 45 + 27 calls |

The filled book on disk is 280,512 chars (~70-80k tokens), that is the fill's output. The
remaining ~75k output and ~155k input tokens are ~72 small reading-level calls of ~1.5k in /
~1.5k out each. **So ~99% of the calls in that book are seconds long. The exposure is one or
two long calls per book, not "every attempt".**

**Two records in this repo show single attempts running far past 120s and returning parsed HTTP
200 bodies through this exact adapter:**

1. `AL-492` (authoring-lessons-log line 572), book 0 failed three attempts in 397.96s. Net of
   the 12s of backoff that is **128.7s per attempt**, and the failure was a real HTTP 200 with
   `finish_reason: 'content_filter'`, not a timeout.
2. `AL-329` (line 409): "the comparison retried Kimi K3 three times at roughly **eleven
   minutes** and 50 cents per attempt", and "the same call issued directly returns HTTP 200 with
   `finish_reason='length'`, `completion_tokens=32000`". A ~660s single attempt that completed.

If a 120s read timeout bounded total generation on this endpoint, neither record could exist.
So one of two things is true, and **the repository cannot distinguish them**: either the
operators' environment sets `CYO_ADVENTURE_LLM_TIMEOUT_SECONDS` above 120 (nothing in
`.env.example`, `.env.staging.example`, the run plan's command at
`deepseek-v4-pro-live-fill-plan-2026-08-20.md:235`, or `report.json` records the timeout, that
absence is itself a finding), or httpx's scalar `timeout=` read deadline does not bound a
non-streamed OpenRouter completion because the endpoint emits early bytes.

**Verdict:** the configuration is wrong on its face and should be fixed, but the synthesis's
claim that this is "billing three retries and a tier downgrade on every large book" and that
"the large end of the catalog is undeliverable in production as configured" is unevidenced.
There is not one recorded production timeout anywhere in the tree. Downgrade from critical to
high, and restate as "the shipped per-call timeout is below the measured single-call fill
latency and the run record does not capture what timeout was actually in force".

---

## Claim 2 (C2-3): chunking bounds output only; ~594k input tokens/book, last batch ~193k, over the context window at cap 32,768

**Verdict: mechanism CONFIRMED, every number WRONG, and the cap cited belongs to a model
production does not run. The real defect is narrower, and worse in a way the finding missed.**

### Mechanism, verified

`orchestrator.py:1188-1189`:
```text
batches = plan_fill_batches(skeleton, max_tokens=ctx.cap)
skeleton_json = json.dumps(skeleton)          # bound ONCE, outside the loop
```
and inside the loop `prose_so_far_json = json.dumps(written_prose(document))` accumulates.
`plan_fill_batches` partitions against the **output** cap; `is_fill_feasible` bounds the
document. There is no input-side screen. All true.

### The numbers

I executed `plan_fill_batches` + `build_fill_subset_prompt` over
`skeletons/16+/the-last-cartage.json`, simulating merges at realistic prose density
(5.3 chars/word, measured off the delivered book), 4 chars/token:

| cap | batches | batch-1 input | last-batch input | total input | one-shot? |
|---:|---:|---:|---:|---:|---|
| 32,768 (`deepseek-chat-v3.1`) | 4 | 104k | 159k | 527k | no |
| **64,000 (shipped Haiku 4.5)** | **2** | **120k** | **154k** | **274k** | **no** |
| 131,072 (the measured run) | 1 | 85k | 85k | 85k | **yes** |

- C2-3's "594k / 193k" is the 32,768 column at ~3.5 chars/token. Same order, but that cap
  belongs to `deepseek/deepseek-chat-v3.1`, which `core/config.py` does not configure and no run
  used. Quoting it as the live case is wrong.
- **The prior agent conflated a completion cap with a context window.** 32,768 is a `max_tokens`
  output ceiling from `MODEL_OUTPUT_CAPS`; the 128k it is compared against is a context window.
  Two different quantities.
- The 8.5:1 input:output multiplier is a 32,768 artifact. On the shipped config it is **2.7:1**
  for the worst book, and **0.85:1** for the 65 skeletons that one-shot.

### The real defect, which is on the shipped configuration

Claude Haiku 4.5's context window is 200,000 tokens (verified via the `claude-api` skill's model
table), and input + `max_tokens` must fit inside it. `_fill_in_batches` requests
`max_tokens=ctx.cap`, the **full 64,000**, on *every* batch regardless of how little that
batch needs (`orchestrator.py:1219`). So the last batch of the largest books asks for
154,145 + 64,000 = **218,145 against a 200,000 window**: an HTTP 400 that
`_raise_for_status` classifies `leg_fatal=True` "invalid or unavailable model"
(`openrouter.py:281-287`), the wrong diagnosis, exactly as C2-3 says.

Scope, measured across all 84 skeletons at the shipped cap:

| delivery rate | skeletons whose last batch + 64,000 exceeds 200k |
|---|---|
| 100% | 3: `the-last-cartage`, `the-tenfold-siege`, `the-harrowstone-keep` |
| 80% | 2: `the-last-cartage`, `the-tenfold-siege` |
| 39% (as measured) | 0 |

**The interaction nobody saw: this defect is a function of the fill rate.** `prose_so_far` grows
with delivered words, so fixing the delivery shortfall (recommendation 5) is what *creates* the
context overflow. At the measured 39% delivery no skeleton overflows; at a healthy 90% two or
three do. The two headline recommendations are adversarial to each other and neither document
says so.

**Severity:** the mechanism is real and on the shipped path, but it hits 2-3 of 84 skeletons,
not "19 of 73 production skeletons" as a cost multiplier. Keep critical only because the failure
mode is a mis-diagnosed dead leg.

---

## Claim 3 (C5-8): the reading-level loop was 46% of a 16+ book's bill for `in_band` 0.155

**Verdict: CONFIRMED, reproducible, and if anything understated. Not an artifact of one book,
it holds on all three measured books.**

C5-8 assumed the fill emitted `expected_output_tokens` = 99,906. It did not: the delivered
document on disk is 280,512 chars, ~70-80k tokens. Using the actual artifact instead of the
full-delivery estimate makes the reading-level residual **larger**. My decomposition, using
measured file sizes and `report.json` costs at $1.91/$3.83:

| book | nodes | in_band | total cost | fill (in/out est) | reading-level residual | share |
|---|---:|---:|---:|---|---:|---:|
| 1 `the-last-cartage` | 632 | 0.155 | $1.0637 | ~85k / ~75k = $0.43 | **$0.63** | **59%** |
| 2 `the-quarry-signal` | 267 | 0.056 | $0.5383 | ~44k / ~47k = $0.26 | **$0.27** | **51%** |
| 3 `the-tin-whistle-map` | 193 | 0.731 | $0.3502 | ~41k / ~36k = $0.22 | **$0.13** | **38%** |

Sample size is 3, not 1, and all three land 38-59%. Independent cross-check: my call-count model
(72 calls for book 1 at `_BATCH_SIZE = 12`, 2 passes) predicts $0.735 against the $0.632
residual, 16% agreement, which is as good as a chars/token proxy gets.

**Caveat that bounds it:** these are reconstructions, not ledger facts. `TokenUsage` has no stage
field (C5-13), so no per-stage attribution exists in principle. And the run record carries
`in_band` only *after* the loop: `ReadingLevelResult` computes `before` and `after`
(`reading_level_loop.py:651`, `:686-695`) but the harness persists neither. **The loop's marginal
benefit is unmeasured anywhere in the tree.** That, not the 46%, is the load-bearing gap.

---

## Claim 4 (C2-1 / C6-1): the 0.6 floor is script-only; the sole backstop is a downgrade the chunked path cannot use

**Verdict: first half CONFIRMED. Second half, as the synthesis paraphrases it, is FALSE.**

Confirmed: `grep -rn "fill_rate\|commissioned_words" src/` finds `generation/skeleton.py` only
(definition, plus `diversity/structure.py` importing `commissioned_words_by_node`). The 0.6
floor lives in `scripts/check_fill_integrity.py`; its only invoker is
`scripts/run_guard_battery.py`. No CI workflow runs it (C6-1 verified).

**But the chunked path does get the fidelity check and the downgrade.** `orchestrator.py:1508-1516`
sets `max_repairs=0 if chunked` and its own comment says why:

> "With the budget at zero the loop still runs the Stage 1 fidelity CHECK, whose own output is a
> short violation list rather than a book, so the authoring gate is not skipped and the outcome's
> `stage1_gate` posture stays truthful (`AL-324`); only the un-emittable repair call is withheld."

`generation/worker.py:1049-1059` and `:1123-1134` pass `settings=_default_settings,
stage1_gate="required"` on both fill paths, arming `fidelity.py`'s `_WORD_COUNT_TOLERANCE = 0.4`
(`fidelity.py:30`). A 39%-delivery book fires on essentially every node and downgrades to
`needs_review`. So the production backstop exists, fires, and is reachable on both paths. What
is true is C2-1's own narrower statement: it **never blocks**, and the ratio itself is computed
nowhere a human or a query can reach. Restate the finding that way; the "chunked path cannot
use it" phrasing is wrong and would send an implementer to the wrong place.

---

## Claim 5 (C2-2): `drafting_guide.md`'s "a tense beat can run three words" licenses the AL-490 shortfall

**Verdict: the text is CONFIRMED verbatim and in the right place. The causal claim is REFUTED by
the project's own control data.**

Text confirmed at `generation/templates/drafting_guide.md:174` ("There is no hard per-node
minimum: a one-line beat is legitimate") and `:187-188` ("Aim for the advisory band as a
story-wide average, not a per-node rule: a tense beat can run three words"). It is embedded in
the **system** block of every fill prompt via `_drafting_guide()` in
`generation/prompts.py:716`. `fill.md:35` softens `words=N` to "Aim for this count; do not
wildly overshoot or undershoot it", overshoot named first. All true.

**The refutation.** I recomputed the fill rate for the W4/W5 vendor pool
(`.worktrees/brief-evidence/out/w4w5-pool/`), nine books, three vendors, run through
`compare_vendors.py` -> `fill_skeleton`, i.e. the same prompt tree with the same licence
sentence in the same system block:

```text
xai-grok-4.6          the-lantern-festival        capped=0.982
xai-grok-4.6          the-night-market            capped=0.940
xai-grok-4.6          the-backyard-treasure-map   capped=0.761
xai-grok-4.6          the-tide-pool-rescue        capped=0.899
anthropic-sonnet-5    the-lantern-festival        capped=0.715
google-gemini-3.1-pro the-lantern-festival        capped=0.887
google-gemini-3.1-pro the-night-market            capped=0.953
google-gemini-3.1-pro the-backyard-treasure-map   capped=0.714
google-gemini-3.1-pro the-tide-pool-rescue        capped=0.879
```

0.714-0.982 under the exact sentence that is supposed to license 0.389-0.529. **The licence
cannot be a sufficient cause of a defect that nine of nine control books, on three vendors, do
not exhibit.** The differentiating variable in the record is the model.

**The honest residual confound, which I will not paper over:** the pool is all 5-8 band,
37-62 nodes; the DeepSeek books are 193-632 nodes. Vendor and scale are confounded in the
*pipeline-filled* set. The large comparators in the 43-pair corpus (`the-harrowstone-keep` 551
nodes at 0.961, `the-ashfall-expedition` 506 nodes at 0.958, `the-drowned-court` 315 nodes at
0.982) are **skill-authored, not pipeline-filled**: `docs/planning/draft-stories-manifest.md`
says the 23 inventory books were authored via the `cyo-author` skill, so they do not close the
confound. AL-490 disproved a monotone scale effect *within* the DeepSeek run
(632->38.9%, 267->52.9%, 193->42.7%) but cannot rule out a threshold between ~112 and ~193 nodes.

**Consequence for the recommendation:** demoting "amend the drafting_guide line" from "the
highest-leverage cheap fix on the board" (C2-2's words) to "free, worth doing, expected effect
unknown and plausibly near zero". Run C2-2's own three-arm experiment (~$3) **before** claiming
an effect, and add a large-book non-DeepSeek arm so the confound closes.

---

## Claim 6 (C2-7): `batch_request` strips conditions/effects, so a reconverging node is written blind to its arrival states

**Verdict: the code fact is CONFIRMED; the consequence is substantially OVERSTATED. Two
independent mitigations the finding did not weigh.**

`chunking.py:303-318` emits per node only `node_id`, `directive` (the body) and
`choices[{id, label}]`. No `condition`, no `effects`, no `target`. Confirmed.

But:

1. **The full skeleton, conditions and effects intact, is in the same prompt.**
   `orchestrator.py:1189` sends `json.dumps(skeleton)` verbatim, rendered under
   `## Full Skeleton (Structure Only)` (`templates/fill_subset.md:115-120`), and the system block
   says "You are seeing the whole skeleton for context". The model is not blind to conditions; it
   is merely not handed them in the work order. The one-shot path likewise sends the whole
   skeleton.
2. **Only 15 of 86 skeletons carry any condition or effect at all** (I counted). For
   `the-last-cartage`, the finding's own worked example, the counts are `condition: 0`,
   `effects: 0`. "Guaranteed by construction" is true of 17% of the catalog, not of the catalog.

The defensible residual claim is weaker and still worth acting on: nothing computes the set of
variable states reachable at a node, so the model would have to do graph analysis over a 300k-char
JSON blob to know what a reconverging node may assume. A typed arrival-state ledger on the work
order is the right fix. **Severity: high -> medium.**

---

## Claim 7 (C2-10 / C2-11): cascade unpinned; `FallbackProvider` has no `.model`; `finish_reason` read nowhere

**Verdict: three sub-claims, one confirmed as stated, one confirmed but mis-attributed and
already registered, one confirmed and under-rated.**

- **Unpinned cascade: CONFIRMED as stated.** `build_provider` (`generation/provider.py:721-734`)
  calls `build_openrouter_leg` with no `provider_order` on all three legs; the docstring at
  `:404-411` says so deliberately ("`build_provider` deliberately exposes no way to set it").
  Given `AL-499` (18 endpoints for one slug, ceilings 16,384 to 1,048,576), that is a live
  correctness exposure, not hygiene.

- **`FallbackProvider` has no `.model`: CONFIRMED but mis-attributed.** C5-10 has this right and
  C2-10 does not: **`OpenRouterProvider` and `OllamaProvider` have no `.model` property either**
  (only `name`; `openrouter.py:113`, `ollama.py:163`). `AnthropicProvider` is the only adapter
  that declares one (`anthropic.py:91-92`). So on the shipped OpenRouter backend
  `getattr(provider, "model", None)` returns `None` whether or not the cascade is enabled, and
  the cap always resolves from `active_fill_model(settings)`. Blaming `FallbackProvider` points
  an implementer at the wrong file. Also: the resulting error direction is *conservative*, the
  fallback leg (Sonnet 4.6, ceiling 128,000) runs under Haiku's 64,000, an under-ask, which
  truncates nothing. And `orchestrator.py:1408-1413` already carries an explicit `#ASSUME`
  naming this as "a KNOWN residual gap ... registered as `UW-C271`". This is a known,
  documented, benign-direction gap, not a discovery. **Severity: high -> low.**

- **`finish_reason` read nowhere: CONFIRMED and under-rated.** `grep -rn finish_reason src/`
  returns 20 hits in 6 files; outside `providers/` every one is a comment. `Completion.finish_reason`
  (`usage.py:144`) is set and never consumed. Combined with `AL-479` (the `leg_fatal` branch sits
  inside `if not content:`), a truncated **non-empty** completion is an ordinary completion that
  parses as nothing and spends the whole repair budget. That is the expensive one of the three.

---

## Claim 8 (C5-6): no `cache_control` set, cached tokens never read

**Verdict: the parent's paraphrase is wrong; C5-6's own text is right. And the achievable
saving is ~$0, not 10x.**

`cache_control: {"type": "ephemeral"}` **is** set, on the system block, for every `anthropic/`
model: `providers/openrouter.py:130-139`, which is the shipped fill default. C5-6 says exactly
this. What is absent is the read: `grep -n cache src/cyo_adventure/generation/{usage,cost}.py
src/cyo_adventure/generation/providers/_base.py` returns nothing; `TokenUsage`
(`usage.py:106-111`) has no cached field and `dig_usage` reads only `prompt_tokens` /
`completion_tokens`. So cached tokens are neither priced nor observable. Confirmed.

**Quantifying the opportunity, which nobody did.** Caching is a prefix match, render order
`tools -> system -> messages`. The user block of `fill_subset.md` is ordered
**volatile-first**: `{nodes_to_fill}` (line 103) -> `{prose_so_far}` (112) -> `{skeleton}` (120)
-> `{theme_brief}` (133). So the only stable prefix is the system block: 44,639 chars ~= 11.2k
tokens, out of a 120-154k-token request. Three consequences:

1. **As shipped, caching is worth ~$0.007/book.** Cache write costs 1.25x and read 0.1x, so on a
   2-batch book the 11.2k system block nets +$0.0028 on batch 1 and -$0.0100 on batch 2.
2. **65 of 84 skeletons one-shot on the shipped cap, one call, no second call to hit the cache
   at all.** Caching cannot help the majority of books by construction.
3. **Even after moving the skeleton into the cached prefix** (reorder the user block
   stable-first, or add a breakpoint after `{skeleton_with_fill_directives}`), the stable prefix
   becomes 44,639 + 296,963 chars = ~85.4k tokens, and on `the-last-cartage`'s two batches that
   nets a **$0.055 saving on a $0.347 book (16%)**, write premium $0.0216 against a read saving
   $0.077. Across the mix that is **~$0.007/book**, because only ~13% of books chunk.

Prompt caching is a real but small lever here, and it is dominated by the cheaper fix: stop
re-sending the directive bodies (below). Nothing supports "10x".

---

## The true fill-stage economics, computed here

Model: shipped configuration (`anthropic/claude-haiku-4.5`, list $1.00/$5.00 per MTok, cap
64,000), 90% delivery, output = the whole returned document (structure + prose, which is what
`fill.md` asks back), reading-level loop modelled at `_BATCH_SIZE=12` / 2 passes with a
band-dependent out-of-band fraction. Medians per band across all 84 skeletons:

| band | n | chunked | med nodes | fill in | fill out | $ fill | RL calls | $ RL | **$/book** |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 3-5 | 11 | 0 | 21 | 13,639 | 2,025 | 0.024 | 2 | 0.012 | **0.036** |
| 5-8 | 9 | 0 | 50 | 17,592 | 6,885 | 0.052 | 2 | 0.018 | **0.070** |
| 8-11 | 12 | 0 | 123 | 26,911 | 20,613 | 0.130 | 5 | 0.059 | **0.189** |
| 10-13 | 15 | 1 | 149 | 27,518 | 26,186 | 0.158 | 8 | 0.093 | **0.251** |
| 13-16 | 19 | 6 | 267 | 41,508 | 38,983 | 0.236 | 21 | 0.205 | **0.441** |
| 16+ | 18 | 12 | 244 | 119,973 | 45,461 | 0.347 | 21 | 0.317 | **0.665** |

**40/40/20 mix (3-5 / 8-11 / 16+): fill $0.131 + reading-level $0.092 = $0.223 per book.**

Against the synthesis's $1.45 machine cost: that figure is DeepSeek V4 Pro fill ($0.665/delivered
book measured) plus Sonnet-4.6 moderation ($0.978 estimated). **On the shipped fill backend the
fill stage is $0.22, not $1.45**, and moderation, not the fill, is the machine-cost centre of
gravity. If production really routes to DeepSeek V4 Pro, multiply the fill column by ~2.5.

### Ranked recoverable saving, my arithmetic

| # | lever | $/book at 40/40/20 | $ on a 16+ book | confidence |
|--:|---|--:|--:|---|
| 1 | Reading-level: 1 pass instead of 2 at 13-16/16+ | **0.032** | **0.160** | high (call count is deterministic) |
| 2 | Reading-level: skip entirely at 13-16/16+ | 0.063 | 0.317 | high on cost, unknown on quality |
| 3 | Prune the re-sent skeleton to a structure-only projection | **0.010** | **0.076** | high, measured: 296,963 -> 145,287 chars, 37.9k tokens saved per send, x2 sends |
| 4 | Prompt caching, after reordering the user block stable-first | 0.007 | 0.055 | medium (5-min TTL vs multi-minute batches) |
| 5 | `_BATCH_SIZE` 12 -> 40 | 0.004 | 0.013 | high, and this is a **latency** lever (3.3x fewer serial round-trips), not a cost lever |
| 6 | Per-batch `max_tokens` sizing | 0.000 | 0.000 | removes the 200k-window 400 on 2-3 skeletons |
| | **realistic total (1+3+4+5)** | **~$0.053** | **~$0.30** | |
| | **aggressive total (2+3+4+5)** | **~$0.084** | **~$0.46** | |

**Answer to the brief: $0.05-0.08 per book is recoverable in the fill stage, 24-38% of a
$0.223 fill-stage bill, and 3-6% of the synthesis's claimed $1.45 machine cost.** Eliminating
the entire fill stage would recover $0.22, i.e. 15% of $1.45. **The fill stage is not where the
money is.** Section 1.4 already says the constraint is human review; section 4.3's
recommendations optimise a term that is 15% of a term that is 24% of the all-in cost. That is
the single most important thing this validation has to say about recommendation ranking.

---

# Recommendation review

## R1. Raise `llm_timeout_seconds` and stop classing fill timeouts as transient

**What breaks if done naively: it makes things strictly worse.**

`generation_job_timeout_seconds = 1800` (`core/config.py:404`) is passed as RQ's `job_timeout`
(`generation/queue.py:154`). Today a hung fill dies at 120s, cascades, and the job either
finishes or fails inside the RQ budget. Raise the LLM timeout to, say, 900s without touching the
job timeout and the same book instead consumes 900s + backoff + a Sonnet leg + an Ollama leg,
gets SIGALRMed at 1800s mid-cascade, and `requeue_stranded_jobs` deliberately does **not**
re-enqueue (`queue.py:237`), so the family loses a quota slot and the spend is booked with no
artifact. You have converted a cheap failure into an expensive one.

**The correct combined change, in order:**

1. **Cap the serial budget before raising any timeout.** Reading-level at `_BATCH_SIZE=12` and
   2 passes is ~72 sequential round-trips on a 632-node book, the dominant term in the 1874s.
   `_BATCH_SIZE` 12 -> 40 plus 1 pass at high bands takes that to ~11 calls. Do this first; it
   buys ~1000s of headroom for free.
2. **Derive the per-call timeout from the request**, as C2-4 says: `t = expected_output_tokens /
   tps_floor + overhead`, floored at 120s, ceilinged so that `sum(planned call ceilings) <
   generation_job_timeout_seconds`. Add a test asserting that invariant, otherwise the two
   settings drift apart again.
3. **Raise `generation_job_timeout_seconds` to ~3600s** and accept the consequence: worker
   occupancy for a 16+ book goes to an hour. At the shipped worker count that is a throughput
   ceiling of N books/hour and a queue-depth risk; size the pool, or route 13-16/16+ to a
   dedicated queue.
4. **Do not make a fill timeout plainly leg-fatal.** A genuine network blip would then kill the
   primary and drop a 16+ children's book onto Sonnet (3x, C5-11) or onto `qwen2.5:14b`. Retry
   **once** at 1.5x the timeout, then leg-fatal. That is the `AL-329` argument applied correctly.
5. **Record the timeout, retry count and reading-level pass setting in the run metadata.** The
   whole of claim 1 is unresolvable today because `report.json` records the cap, the pin, the
   cost and the latency, and not the timeout.

**Prerequisite that changes the whole recommendation:** see "What everyone missed" #1, switch
the adapter to streaming and the question dissolves.

## R2. Cap the reading-level loop

**What breaks if done naively: you cannot price the trade, because the loop's benefit is
unmeasured.** `ReadingLevelResult` carries `before`, `after`, `nodes_revised`, `passes` and
`discarded_for_gate` (`reading_level_loop.py:628-643`), `_with_reading_level` puts them in
`report["reading_level"]` (`orchestrator.py:717`), and the run record persists none of it. Every
`in_band` figure in the review is post-loop. **Step zero is not a cap; it is persisting
`before`/`after`/`calls` on `generation_job`.** Anyone who caps first is guessing.

**The right cap, on the evidence available:**

- **13-16 and 16+: one pass, plus an absolute call cap of `ceil(nodes/12)`.** Two passes ended at
  `in_band` 0.056 and 0.155. A loop whose acceptance is strictly monotone (its own comment,
  `:678-682`) cannot have a second pass worth more than its first, so the bounded downside of
  dropping pass 2 is a fraction of 5.6-15.5 points. The upside is $0.16-0.20 and ~35 round-trips.
- **10-13 and below: leave at 2 passes.** The 8-11 book reached 0.731; the loop lands there.
- **`_BATCH_SIZE` 12 -> 40 everywhere.** The batch output is 12 rewritten bodies (~1.2k tokens)
  against caps of 64,000: the batch is 50x smaller than it needs to be. Note this is worth
  ~$0.013 on a 16+ book, not the "3.3x cost cut" C5-8 implies, the token volume is bodies, and
  bodies do not shrink. It is a **latency** fix, and latency is what the RQ timeout binds on.
- **The real question C5-8 asks and nobody answered:** whether the loop should run at all at 16+.
  `AL-491` establishes that FK conformance at high bands is dominated by the fill-rate defect, so
  the loop is currently paying to simplify prose that is already too short. Fix the fill rate
  first, then re-measure, then decide. Do not delete the loop on the strength of a number
  produced by a broken fill.

## R3. Add caching / pruning

**What breaks if done naively:**

- **Reordering the user block for caching has a security consequence.** `_neutralize_fence` is
  applied to `prose_so_far`, `nodes_to_fill`, `skeleton` and `theme_brief` because model-written
  prose descended from an untrusted brief sits inside an untrusted fence
  (`prompts.py:705-713`). Moving the skeleton and brief *before* the prose changes which content
  is inside which fence. Re-derive the fence layout, and keep
  `test_the_subset_prompt_neutralizes_a_literal_fence_terminator` green.
- **A 5-minute cache TTL against multi-minute batches.** Batch 1 of a 16+ book takes minutes; the
  ephemeral cache default is 5 minutes. Either use `ttl: "1h"` or expect misses, in which case
  you have paid the 1.25x write premium for nothing. This is why the naive version can be
  *cost-negative*.
- **Pruning is the better lever and is safe.** A structure-only projection (ids, choice
  ids/targets/conditions/effects, `is_ending`) is **145,287 chars against 296,963**, the
  directive bodies alone are 40.9% of the skeleton and are dead weight on every batch that is not
  writing them. That is 37.9k tokens saved per send, ~76k per book, ~$0.076 on a 16+ chunked
  book, and it is the change that also pulls the last batch back under the 200k window.
  Do this one first and caching becomes optional.
- **Do not prune the conditions/effects out** while doing this, see claim 6. Prune bodies, keep
  the graph.

## R4. Wire the delivery floor

**"This will start rejecting books" is not supported. I recomputed the whole corpus.**

Across every committed (skeleton, filled) pair I could resolve, 43 pairs from `out/`,
`tests/data/diversity_panel/fills/`, `out/pilot/`, `out/w7/`, `out/distillation/`, the
per-node-capped fill rate distribution is:

```text
floor 0.50 :  0/43 fail
floor 0.60 :  0/43 fail        <- the proposed floor
floor 0.65 :  1/43 fail
floor 0.70 :  3/43 fail
```

tightest known-good = 0.634 (`the-sky-ship-stowaway.deep-sea-submarine`), next 0.660
(`the-lantern-festival` x2), then a clean gap to 0.783. **This exactly reproduces C2-16 and
`check_fill_integrity.py`'s own calibration comment, independently.** The three DeepSeek books
(0.389-0.529) fail. So wiring 0.6 rejects **none** of the currently-good corpus and catches the
known-bad.

**Is 0.6 the right threshold?** It sits in a genuine gap in the distribution, which is the right
property, but the margin over the tightest good book is 0.034 and the calibration set is 43
books of which only ~12 came through the production fill path. So:

- **Ship it as a `needs_review` downgrade, not a block.** A false positive then costs an admin
  glance; a false block costs a lost book and a burned quota slot. C2-1's recommendation
  (compute in `worker.py::_run_skeleton_fill`, persist on `generation_job`, show on the review
  card beside in-band per `AL-491`) is right and is the whole of what should ship this week.
- **Record the ratio unconditionally, for every book, from day one.** Then revisit the threshold
  after 20 production books rather than after 43 mostly-hand-authored ones.
- **Do not put it in the deterministic gate yet.** `UW-C307`'s open question is gate carriage,
  and a 0.034 margin is not enough to make a blocking rule out of.

## R5. Amend the `drafting_guide` line

Proposed replacement for `drafting_guide.md:174` and `:187-188`:

> There is no fixed per-node minimum in the validator: the hard error is the per-node
> **maximum**.
>
> **When you are authoring a skeleton**, that freedom is yours. Set `words=` on each node to
> whatever the beat needs, from a three-word cliff to the per-node max, and let the story-level
> mean land inside the advisory band.
>
> **When you are filling a skeleton**, that judgement has already been made and is written into
> each node's `words=` target. Treat it as a commission, not a suggestion: land within +/-25% of
> it in both directions. A reply whose passages total under 80% of the book's commissioned words
> is rejected and re-run, however well each individual passage reads.

And in `fill.md:35` / `fill_subset.md:38`, replace "Aim for this count; do not wildly overshoot
or undershoot it" with "Your prose for this passage must land within +/-25% of `words`", plus a
book-level line in the user block stating the total commissioned words.

**Does removing the licence cause padding? Yes, and that is a real risk, so three things must
ship with it or the change is a net quality loss:**

1. **Keep the band two-sided.** Today only overshoot is gated (PL-19's per-node max is the sole
   ERROR). A one-sided floor converts a thinness defect into a padding defect and the gate will
   not see it.
2. **At 3-5 and 5-8 the floor must stay advisory.** A hard word floor fights the reading-level
   target directly: longer sentences push FK up, and `drafting_guide.md` says so on the same
   page. Two hard constraints pulling opposite ways at the bands where the window is tightest is
   how you get a book that satisfies neither.
3. **Instrument padding before you create the incentive.** `AL-496` already proposes
   duplicate-body and label-diversity counters (book 2 had 23 redundant nodes, 2 byte-identical
   bodies, and 3 strings covering 89.8% of choice labels). Padding shows up as repetition before
   it shows up as word count. Score those in C2-2's three-arm experiment alongside the fill rate,
   or you will trade a measured defect for an unmeasured one.

And given claim 5's refutation: **run the experiment first, or at least concurrently, and do not
book an expected saving against this change.**

---

# What everyone missed

1. **Nobody proposed streaming, which is the actual fix for claim 1.** Every provider call is a
   non-streamed `client.post` (`openrouter.py:230-236`; same shape in `anthropic.py`,
   `ollama.py`, `modal.py`). Under streaming, an httpx read timeout bounds the inter-chunk gap
   rather than total generation, so a 900s completion survives a 120s read deadline with no
   config change at all. It is also Anthropic's documented requirement for large `max_tokens`
   (the SDK requires streaming above ~64k). Twelve reviewers debated the timeout value; none
   questioned the transport.

2. **Every batch asks for the full model cap.** `orchestrator.py:1219` sends
   `max_tokens=ctx.cap` (64,000) on every chunk, even one that needs 30k. That single value is
   what puts `the-last-cartage`'s and `the-tenfold-siege`'s last batch over Haiku's 200k window
   (154,145 + 64,000 = 218,145). Sizing `max_tokens` off the batch's own
   `expected_output_tokens` is a one-line change that deletes the failure mode C2-3 spends a
   critical finding on, and costs nothing.

3. **The two headline recommendations are adversarial.** `prose_so_far` grows with delivered
   words. At the measured 39% delivery, zero skeletons overflow Haiku's context window; at a
   healthy 90%, two or three do. Fixing the fill rate (R5) is what turns C2-3 from latent into
   live. Neither document notices. Sequence matters: prune the skeleton (R3) **before** shipping
   the delivery floor (R4/R5).

4. **No run artifact records the configuration under which it ran.** `report.json` captures
   skeletons, vendors, pins, cap, cost, latency, and not `llm_timeout_seconds`, not
   `max_retries`, not `reading_level_passes`, not `max_repairs`. This is precisely why claim 1
   cannot be settled from the evidence tree, and it will recur on every future run. One dict in
   `compare_vendors.py::main` fixes it permanently.

5. **The loop's `before` measurement exists and is thrown away.** `ReadingLevelResult.before` is
   computed at `reading_level_loop.py:651` and never persisted. Half the review's cost argument
   turns on "the loop bought 0.155", and nobody can say what it bought, because the counterfactual
   was measured and discarded.

6. **Every cost figure in the review prices a configuration that is not deployed.** DeepSeek V4
   Pro at cap 131,072 one-shots every skeleton in the catalog; shipped Haiku 4.5 at 64,000 chunks
   19 of 84 and costs about a third as much. The chunking findings and the cost findings are
   therefore describing two mutually exclusive worlds, and section 4.3 mixes them in the same
   paragraph.

7. **The fill stage is 15% of the machine cost and the machine cost is 24% of the all-in.**
   Recommendations #2 and #3 are the review's "top COST recommendations" and their combined
   realistic yield is **$0.05/book against a $5.95 all-in**, i.e. under 1%. They are worth doing
   because they are cheap and because two of them fix correctness defects, not because they move
   the economics. Presenting them as the top cost recommendations mis-ranks the backlog; section
   1.4 of the same document already says why.
