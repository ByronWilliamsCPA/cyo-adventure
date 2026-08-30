# A3. Blank-slate economic and operational case: LLM-generated CYO books for children

Author's stance: I have not read this project's planning documents. Everything below is derived
from first principles plus current published LLM pricing. Where I assume a number, it is labelled
**[A-n]** and swept in the sensitivity sections. The conclusions are stated so that they survive
being wrong about price *levels*; what they depend on is price *ratios* and the shape of the cost
curve, both of which are far more stable than levels.

---

## 0. Assumption register (everything downstream depends on these)

### Price assumptions

| ID | Assumption | Value | Confidence |
|----|-----------|-------|-----------|
| A-1 | Frontier tier (Opus-class) input / output | $5.00 / $25.00 per MTok | Med-high |
| A-2 | Workhorse tier (Sonnet-class) input / output | $3.00 / $15.00 per MTok | Med-high |
| A-3 | Cheap tier (Haiku-class) input / output | $1.00 / $5.00 per MTok | Med-high |
| A-4 | Prompt-cache write multiplier | 1.25x input (2.0x for 1h TTL) | Med |
| A-5 | Prompt-cache read multiplier | 0.10x input | Med |
| A-6 | Async batch discount | 0.50x on both input and output | Med |
| A-7 | Image generation (one cover) | $0.035 per image | Low-med |
| A-8 | Tokens per English word, children's prose | 1.35 | High |
| A-9 | Thinking/reasoning tokens as fraction of visible output, creative task at high effort | θ = 0.6 | Low |

**Sensitivity discipline:** every headline number below is repeated at 0.33x, 1x and 3x the assumed
price level. The *ordering* of the findings is invariant under that sweep; only the crossover word
counts move. I flag explicitly where a 3x price world changes a decision rather than just a number.

### Business assumptions

| ID | Assumption | Value |
|----|-----------|-------|
| B-1 | Consumer price | $12.99 / month (variants $9.99, $19.99 swept) |
| B-2 | Channel mix | 60% mobile store, 40% web |
| B-3 | Store take | 15% (small-business / year-2 rate). Year-1 30% swept |
| B-4 | Web payment cost | 2.9% + $0.30 |
| B-5 | Monthly logo churn at steady state | 8% (12% swept) |
| B-6 | Blended paid CAC | $40 |
| B-7 | Mature COGS target as % of net revenue | 30% (50% tolerated pre-scale) |
| B-8 | Non-book COGS per subscriber-month (infra, storage, CDN, support) | $0.55 |
| B-9 | Reviewer fully-loaded cost | $8.00 / paid hour offshore; $28.00 / paid hour onshore |
| B-10 | Reviewer utilisation | 75% (so $10.67 / productive hour offshore) |

---

## 1. Unit economics from the top down

### 1.1 Net revenue per subscriber-month

```text
Store leg : $12.99 x (1 - 0.15)                = $11.04
Web leg   : $12.99 - (0.029 x 12.99 + 0.30)    = $12.31
Blend     : 0.6 x 11.04 + 0.4 x 12.31          = $11.55  net ARPU
```

At the year-1 30% store take the blend is `0.6 x 9.09 + 0.4 x 12.31 = $10.38`. Plan against
$10.38, not $11.55, for the first twelve months of any cohort.

### 1.2 The COGS envelope

```text
Mature (30% COGS)  : 0.30 x 11.55 = $3.47 / sub-month
  less non-book B-8:            - $0.55
  BOOK BUDGET      :              $2.92 / sub-month

Pre-scale (50%)    : 0.50 x 11.55 = $5.78
  less non-book    :            - $0.55
  BOOK BUDGET      :              $5.23 / sub-month
```

### 1.3 Maximum allowable cost per book vs. usage intensity

`ceiling = book budget / books per month`

| Books / child / month | Mature ceiling (30% COGS) | Pre-scale ceiling (50% COGS) |
|---|---|---|
| 1 (dabbler) | **$2.92** | $5.23 |
| 2 | $1.46 | $2.62 |
| 4 (engaged) | **$0.73** | $1.31 |
| 8 | $0.365 | $0.654 |
| 12 (heavy) | **$0.243** | $0.436 |
| 20 | $0.146 | $0.262 |
| 30 (whale) | **$0.097** | $0.174 |

The per-user view is the wrong denominator for planning; the *fleet* view is the right one, but the
fleet view only holds if a per-user cap exists. Assume the usage mix:

```text
50% pull 1/mo, 30% pull 4/mo, 15% pull 12/mo, 5% pull 30/mo
mean = 0.5(1) + 0.3(4) + 0.15(12) + 0.05(30) = 0.5 + 1.2 + 1.8 + 1.5 = 5.0 books/sub/month
FLEET CEILING = $2.92 / 5.0 = $0.58 per book
```

Note the concentration: the 5% of whales generate `1.5/5.0 = 30%` of all book volume. The top 20%
generate `(1.8+1.5)/5.0 = 66%`. **The fleet ceiling of $0.58 is not robust, it is an average over a
heavy-tailed distribution and a single uncapped whale destroys it.** A user pulling 30 books/month
of median size costs `30 x $0.575 = $17.25` against $11.55 of net revenue: they are gross-margin
negative on their own, before any CAC.

**Position 1: a hard per-child monthly book entitlement is not a product nicety, it is the primary
unit-economic control.** Ship it before the first paying user. 8/month on standard, 20 on premium.

### 1.4 LTV, payback, and why cost is front-loaded

```text
B-5 = 8%/mo churn  -> expected life = 1/0.08 = 12.5 months
Gross LTV (net of store) = 12.5 x 11.55 = $144.4
Contribution LTV at 30% COGS = 0.70 x 144.4 = $101.1
LTV / CAC = 101.1 / 40 = 2.53x     Payback = 40 / (11.55 x 0.70) = 4.9 months

At 12%/mo churn: life 8.33 mo, contribution LTV = 0.70 x 96.2 = $67.4, LTV/CAC = 1.69x
```

At 12% churn the business is marginal, and 12% is a realistic number for a kids' subscription app
with seasonal drop-off. **The retention curve, not the token price, is the dominant term in whether
this business exists.** A 4-point churn improvement is worth more than eliminating all token cost.

Now the asymmetry that kills naive models: **consumption is front-loaded, revenue is back-loaded.**
A new family explores. Assume month-1 usage is 2.5x steady state (12.5 books) and a 7-day free
trial at 33% trial-to-paid conversion, with 3 books pulled during trial.

```text
Cost per trial start   = 3 x $0.575               = $1.73
Trial starts per paid  = 1 / 0.33                 = 3.03
Trial burn per acquired subscriber                = $5.24   <-- this is CAC, and nobody books it as CAC
Month-1 post-conversion burn = 12.5 x 0.575       = $7.19
Month-1 net revenue                               = $10.38 (year-1 store take)
Month-1 contribution = 10.38 - 7.19 - 0.55        = $2.64
Effective CAC = $40 media + $5.24 trial burn      = $45.24
Payback = 45.24 / 8.09 steady-state contribution  = 5.6 months
```

**Position 2: free-trial generation is an unbudgeted CAC line and the single most abusable surface
in the product.** Cap trial books at 2, gate the second on account verification, and never let a
trial user request a book above ~8,000 words.

### 1.5 Where the ceiling actually binds

It binds in three different places at three different book scales, and this is the central finding
of the whole analysis:

| Book scale | Binding constraint | Why |
|---|---|---|
| Small (≤2,000 words) | **The human, then the cover art** | Token cost is ~$0.03. Human review at $0.31 and art at $0.10 are 93% of unit cost. |
| Median (5,000–15,000 words) | **Failed attempts** | Tokens and fixed costs are comparable; the retry/rejection multiplier M is the swing factor between $0.42 and $0.90. |
| Large (>50,000 words) | **Tokens, superlinearly** | One 118k-word book costs more than a third of a subscriber-year. Nothing else matters. |

Anyone who optimises token cost for the median product is optimising the wrong third of the bill.
Anyone who ignores token cost for the long tail loses money on individual books at 30x the ceiling.

---

## 2. Token-level cost model

### 2.1 Formulas

Let:

```text
W   = total words in book
N   = number of prose nodes
w   = W/N, average words per node
tau = tokens per word (A-8 = 1.35)
k   = nodes generated per LLM call (chunk size)
C   = ceil(N/k), number of generation calls
S   = stable system prefix tokens (policy + style bible + schema + band profile)
P   = full plan/skeleton serialisation tokens
theta = thinking-token ratio (A-9)
p_in, p_out = per-token prices
```

**Output side (identical under all designs):**

```text
O_prose  = tau * W
O_think  = theta * O_prose
O_total  = (1 + theta) * tau * W                                    ... LINEAR in W
```

**Input side, this is where the design choice lives.**

*(a) Naive full-context re-send.* Every call carries the system prefix, the whole plan, and all
prose generated so far:

```text
I_naive = C*(S + P) + sum_{j=1..C} tau*W*(j-1)/C
        = C*(S + P) + tau*W*(C-1)/2
```

Substituting `C = W/(k*w)`:

```text
I_naive ~ (S+P)*W/(k*w)  +  tau*W^2 / (2*k*w)      <-- QUADRATIC IN W
```

**This is the superlinear term, and it is the only genuinely superlinear term in the system.**
Note `P` itself grows with `N`, so the first term is also quadratic-ish (`C * P ~ W * N`).

*(b) Naive + incremental prompt caching.* The accumulated prose is an append-only prefix, so each
call's prefix is the previous call's prefix plus one block. Every token is written to cache once
and read `(C - position)` times:

```text
I_cached_effective = 1.25*(S + P + tau*W)  +  0.10*[ C*(S+P) + tau*W*(C-1)/2 ]
```

Still quadratic, but with a 0.10 coefficient on the quadratic term, an 8-10x knockdown that buys
you roughly a 3x larger book at the same cost. It does not change the asymptotics.

*(c) Pruned / hierarchical context.* Send the system prefix (cached), a rolling story-state summary
of bounded size `A`, the local subgraph slice `P_loc` (parent + siblings + reachable endings), and
the parent node's verbatim text `F`:

```text
I_pruned = C * (S + P_loc + A + F)      with S cached
         ~ W/(k*w) * const                                          ... LINEAR IN W
```

**Total gross generation cost:**

```text
G = I_eff * p_in + O_total * p_out
```

**Failure multipliers.** With per-chunk validator failure probability `p_v` and an attempt cap `R`:

```text
M_chunk = (1 - p_v^R) / (1 - p_v)          expected attempts per chunk
M_book  = 1 / (1 - p_w)                     wholesale re-plan/regenerate probability p_w
```

**Judging / moderation:**

```text
J = n_passes * [ (tau*W + S_policy) * p_in_judge + O_verdict * p_out_judge ]
```

plus path-walk fidelity checks, which must be sampled: `J_walk = K * (walk_tokens) * p_in`.
**Never let K scale with path count**, see §2.5.

**Total:**

```text
T = G * M_chunk * M_book  +  J * M_judge  +  art  +  human
```

Batch API applies 0.5x to `G` and `J` only.

### 2.2 Instantiation: small end (800 words)

`W=800, N=10, w=80, tau W = 1,080 output tokens. k=10 -> C=1. S=4,000, P=600.`

| Line | Tokens | Sonnet-tier, batch | Opus-tier, interactive |
|---|---|---|---|
| Input | 4,600 | $0.0069 | $0.0230 |
| Output prose | 1,080 | $0.0081 | $0.0270 |
| Thinking (θ=0.6) | 648 | $0.0049 | $0.0162 |
| **G** | | **$0.0199** | **$0.0662** |
| × M (p_v=0.20/R=3, p_w=0.10) = 1.378 | | $0.0274 | $0.0912 |
| Judging (Haiku, 2 passes, batch) | ~8,400 | $0.0030 | $0.0030 |
| Cover art (A-7 + 2 retries) | | $0.1000 | $0.1000 |
| Human review (1.75 min @ $10.67/prod-hr) | | $0.3110 | $0.3110 |
| **TOTAL** | | **$0.44** | **$0.50** |

**Token share of unit cost at the small end: 7%.** Human review: 71%. Cover art: 23%. The model
tier is worth 6 cents. Arguing about Opus-vs-Sonnet here is arguing about 13% of a cost that is
already dominated by two non-token line items.

### 2.3 Instantiation: large end (118,000 words, 677 nodes)

`W=118,000, N=677, w=174. O_prose = 159,300. O_think = 95,580. k=8 -> C=85.`
`S=4,000. P = 60 tok/node x 677 = 40,620.`

**(a) Naive full-context, Opus-tier, interactive:**

```text
I = 85*(4,000+40,620) + 159,300*(85-1)/2
  = 3,792,700 + 6,690,600
  = 10,483,300 input tokens

input  10,483,300 x $5/1M   = $52.42
output   159,300 x $25/1M   =  $3.98
think     95,580 x $25/1M   =  $2.39
                       G    = $58.79     (input = 89% of cost)
```

**(b) Naive + incremental caching, Opus-tier:**

```text
writes  (4,000+40,620+159,300) x 1.25 = 254,900 eq  -> $1.27
reads   10,483,300 x 0.10             = 1,048,330 eq -> $5.24
output + think                                        -> $6.37
                                              G      = $12.88
```

**(c) Pruned context, Sonnet-tier, batch, the design I would ship:**

```text
Per chunk: S 4,000 (cached read) + P_loc 1,200 + state summary A 800 + parent text F 400 = 6,400
Cached leg : 85 x 4,000 x 0.10 = 34,000 eq  + one 4,000 x 1.25 write = 5,000 eq  -> 39,000 eq
Fresh leg  : 85 x 2,400                                                          -> 204,000
I_eff = 243,000

input  243,000 x $1.50/1M (batch)   = $0.365
output 254,880 x $7.50/1M (batch)   = $1.912
                             G      = $2.277
x M = 1.378                         = $3.138
Judging: 2 Haiku full-text passes, batch          = $0.172
         30-walk Sonnet fidelity sample, batch    = $0.158
Cover art                                          = $0.100
Human review                                       = $0.311
                                    TOTAL          = $3.88
```

**Lever ranking on the large book, measured from the $58.79 naive baseline:**

| Lever | Multiplier | Cumulative |
|---|---|---|
| Context pruning (naive → bounded window) | **0.129x (7.8x saving)** | $7.56 |
| Batch API | 0.50x | $3.78 |
| Model tier Opus → Sonnet | 0.66x | $2.49 |
| Prompt caching *within the pruned regime* | ~0.92x | $2.28 |

**Position 3: prune first, batch second, tier third, cache fourth.** Engineering instinct reaches
for model tier first, and model tier is the *weakest* of the four levers by a factor of twelve. It
is weak because output tokens dominate after pruning and the Opus/Sonnet output ratio is only 1.67x.
Caching looks weak here only because pruning already ate its lunch; caching is what rescues you if
you *cannot* prune (e.g. a genre where global continuity genuinely requires the full prior text).

### 2.4 Instantiation: the median book (5,000 words, ~30 nodes)

This is the number that actually governs the P&L.

```text
C = 4. I_eff ~ 16,200. O = 6,750 prose + 4,050 think = 10,800.
Sonnet batch: input $0.024 + output $0.081       G = $0.105
x M 1.378                                          = $0.145
Judging (Haiku batch x2 + short fidelity)          = $0.020
Cover art                                          = $0.100
Human review                                       = $0.311
                                        TOTAL      = $0.575
```

Against a fleet ceiling of **$0.58**. **Zero headroom.** Token cost is 25% of it; the human and the
cover art are 71%. This single line is the strongest argument in the document, and it points at two
interventions that have nothing to do with LLMs:

- Make the cover art earned rather than automatic (§4).
- Make the mandatory human the guardian rather than staff (§6).

Do both and the median book falls to `$0.145 + $0.020 + $0.002 + $0 = $0.167`, giving 3.5x headroom
and turning a knife-edge business into a comfortable one.

### 2.5 The second superlinearity nobody expects: path validation

A branching graph with 677 nodes and branching factor 2–3 has on the order of 400–900 distinct
root-to-ending paths (a balanced binary tree with 677 nodes has ~339 leaves; branching factor 3
raises it). If any LLM check is run *per path*: "is this path coherent end to end?", cost scales
with path count, not node count, and each path carries most of the book's tokens.

```text
Per-path continuity check, 500 paths x ~12,000 tokens x $1.50/1M (Sonnet batch) = $9.00 per book
```

That is 2.4x the entire rest of the large book. And path count grows exponentially with depth for
a fixed branching factor, so this term detonates as the product scales up book length.

**Control:** node-local and edge-local invariants (state variables set/consumed, reachability,
dead ends, unreachable endings, orphan choices, reading-level per node) are all checkable
deterministically in `O(N + E)` CPU for a fraction of a cent. Only *narrative* continuity needs an
LLM, and it needs a **sampled edge-covering walk set**: greedily choose K walks that together cover
every edge at least once. For a graph with E ≈ 1,350 edges and walk length ~15 nodes, K ≈ 90 walks
covers every edge; K = 30 covers the high-traffic subgraph. Fix K by budget, not by topology.

**Position 4: no LLM cost in this system may be allowed to scale with path count. Write that as an
architectural invariant and test it, assert in CI that judge-call count is O(1) in path count.**

### 2.6 Price-level sensitivity

| Scenario | Small book | Median book | Large book | Fleet ceiling $0.58 verdict |
|---|---|---|---|---|
| 0.33x prices | $0.43 | $0.52 | $1.35 | median comfortable, large still 2.3x over |
| **1x (baseline)** | **$0.44** | **$0.575** | **$3.88** | median knife-edge, large 6.7x over |
| 3x prices | $0.50 | $0.86 | $10.83 | median 48% over, large 19x over, long books impossible |

Crossover word count where token cost equals the fixed $0.41 of human+art:

```text
1x prices  : ~14,000 words
3x prices  : ~4,600 words
0.33x      : ~42,000 words
```

**Invariant conclusions across the whole sweep:**
1. Short books are never token-bound. At every price level the human dominates below ~5k words.
2. Long books are always token-bound, and the naive context design is always catastrophic.
3. Context pruning is always the largest single lever, because it changes the exponent, not the
   coefficient. Price changes only move the coefficient.
4. Long books never fit inside a flat consumer subscription at any tested price level.

**What changes at 3x:** at 3x, the median book breaks the ceiling and the business needs either
guardian review or a $17.99 price. At 3x, *nothing* above ~20k words is servable on a flat plan.
That is the only decision the price level actually flips.

---

## 3. Waste modes: every way this pipeline burns money for nothing

For each: the mechanism, the detection signal, and the control. Ordered roughly by expected annual
loss.

| # | Waste mode | Mechanism | Detection signal | Control |
|---|---|---|---|---|
| 1 | **Non-convergent repair loop** | Chunk fails validator; regenerate with the same model, same prompt, same failure; fails again. Geometric spend with no convergence. | Attempts-per-chunk histogram tail; *the same validator error code repeating on the same node across attempts*. That repetition is the signature, a different error each time is progress, the same error is a loop. | Hard cap R=2 LLM repairs. Attempt 3 must change *strategy*, not re-roll: escalate a tier, switch to a targeted rewrite prompt, or delete-and-replan the node. Per-book hard spend ceiling that kills the job and surfaces it as a product-level failure, not a silent retry. |
| 2 | **Wholesale late rejection** | The book is fully generated, then the safety gate rejects the *premise*, which was knowable for $0.002 before a single prose token was spent. | Ratio of cost-per-generated-book to cost-per-*published*-book. If it exceeds 1.3 you are paying for books nobody will ever read. | Order gates by (cost to run) ascending and (rejection probability) descending. Premise screen → plan screen → chunk-1 screen → full generation. Fail on chunk 1, never on chunk 85. |
| 3 | **Superlinear context re-send** | §2.1(a). The default naive implementation. | Input-token share of spend > 50% on any multi-chunk job; `cache_read_input_tokens == 0`. | §2.1(c) pruning, plus incremental caching. Alarm when input tokens per book exceed `4 x output tokens`. |
| 4 | **Truncation at the completion cap** | `stop_reason == "max_tokens"`. You paid for every generated token, and if the recovery path restarts the chunk you pay for them again. | `max_tokens` stop-reason rate; p99 output tokens as a fraction of the cap. | Alarm at >1%. Size chunks so p95 output ≤ 40% of the cap. Recover by *continuation* (feed the partial back and ask for the remainder), never by restart, restart discards paid output. Stream anything with a large cap so an HTTP timeout does not silently bill-and-discard. |
| 5 | **Reasoning burn on refusals** | A premise trips a safety classifier. The model thinks at length and then declines. You are billed for the thinking on a zero-value response. Then a blind retry does it again, and a retry of an identical prompt on an identical model refuses with near-certainty. | Refusal stop-reason rate and its category distribution; thinking tokens on refused calls. | Cheap pre-screen of the premise before any expensive call. On refusal, **never retry the same prompt on the same model**, either route to an explicit fallback model or fail the request back to the family with a rewrite suggestion. Count fallback invocations as a first-class metric; a fallback to a pricier model is correct behaviour but must be visible. |
| 6 | **Unparseable structured output** | The model returns prose around the JSON, or subtly invalid escaping; the parser throws; the orchestrator retries. | JSON parse-failure rate per stage. | Use provider-native strict structured output / strict tool schemas so this rate goes to ~0. Parse tool inputs with a real JSON parser, never string matching. **Never build a regex JSON-repair retry loop**, it converts a 1% failure into a 1% infinite-cost failure. |
| 7 | **Budget overrun with nobody watching** | A bug, a retry storm, or an abusive user runs spend at 50x baseline overnight and the first signal is the monthly invoice. | Spend-per-hour vs. trailing-7-day same-hour baseline. | Ceilings enforced *before* the API call and at four scopes: per job, per user per day, per tenant per day, global per day. A reconciled-after-the-fact budget is not a budget. One documented kill switch that stops all generation without a deploy. |
| 8 | **Provider balance exhaustion mid-run** | Credits run out at chunk 60 of 85. Every completed chunk is lost if the job is not checkpointed. | Balance expressed in *days of current burn*, not dollars. | Alarm at <14 days, page at <5. Checkpoint every completed chunk to durable storage so resume never re-pays. Test the resume path, an untested resume is a fiction. |
| 9 | **Silent fallback to a costlier model** | A routing layer, a provider-side fallback, or a config default silently serves a pricier model. Quality looks fine; margin quietly halves. | Assert `response.model == requested model` on every call; per-model spend-mix drift week over week. | Fail the call (or at minimum emit a high-severity event) on mismatch. Price every model in code so the cost record is computed from the *served* model, never the requested one. |
| 10 | **Cache invalidation by a volatile prefix** | A timestamp, a UUID, an unsorted dict serialisation, or a tool list built from a set, anywhere above the last cache breakpoint, silently invalidates the whole prefix. Cost quietly rises 3-8x on long books with no error anywhere. | `cache_read_input_tokens == 0` across repeated same-prefix requests. | Freeze the prefix. A CI test that builds the request twice in the same process and asserts the prefix bytes are identical. This test costs an hour to write and has caught this bug in every system I have seen it added to. |
| 11 | **Regenerating what could have been reused** | Re-deriving skeletons, re-moderating unchanged node text, re-screening an unchanged premise. | Reuse hit rate on skeletons and on content-hash-keyed moderation verdicts. | Content-hash-keyed verdict store. **Key must include the policy version and the age band** (§4). |
| 12 | **Duplicate execution from at-least-once queue delivery** | Worker dies after generating, before acking. The job runs again, in full. | Same idempotency key producing two completed books. | Idempotency key on job creation; a completed-chunk store consulted before every call. |
| 13 | **Zombie jobs** | A family cancels, churns, or deletes a request mid-generation and the worker grinds on for another 40 minutes. | Books completed against cancelled/deleted accounts. | Cancellation check between every chunk. Free and effective. |
| 14 | **Thinking budget on mechanical stages** | High reasoning effort applied to tagging, formatting, schema-filling. Thinking tokens billed at output rates for zero benefit. | Thinking-token share of output *per stage*. | Low effort on mechanical stages, high only on plot coherence and safety adjudication. A per-stage effort setting is a two-line change worth 10-20% of output spend. |
| 15 | **Speculative pre-generation nobody opens** | Pre-generating "you might like this" books to hide latency. If 40% are never opened, 40% of that spend is pure loss. | Published-but-never-opened rate at 14 days. | Cap lookahead at 1 book, and only for children with ≥3 opens in the last 14 days. Kill the feature if never-opened >25%. |
| 16 | **Paying to generate content the diversity gate will reject** | Anti-template similarity check runs at the end and rejects a book for being too close to an existing one. | Diversity-rejection rate, and the distribution of *where* in the pipeline rejections occur. | Run the similarity check against the *plan*, before prose generation. A plan is ~2% of the tokens and carries almost all of the structural similarity signal. |

**Waste-mode arithmetic worth internalising:** the retry multiplier is brutally nonlinear.

| p_v (chunk failure) | R=2 | R=3 | R=5 | Uncapped |
|---|---|---|---|---|
| 0.10 | 1.10 | 1.11 | 1.11 | 1.11 |
| 0.20 | 1.20 | 1.24 | 1.25 | 1.25 |
| 0.35 | 1.35 | 1.47 | 1.53 | 1.54 |
| 0.50 | 1.50 | 1.75 | 1.94 | 2.00 |
| 0.65 | 1.65 | 2.20 | 2.62 | 2.86 |

At p_v = 0.65 an uncapped retry policy triples your generation bill. **The cap is worth more than
the model discount.** And note that R=2 vs uncapped differs by only 6% at p_v=0.20 but by 42% at
p_v=0.65, the cap is cheap insurance that costs almost nothing when things are healthy.

---

## 4. Amortization and reuse

### 4.1 The general break-even

An artifact costing `K` to produce once and reused `R` times, versus a marginal alternative costing
`m` each time, breaks even at `R* = K / m`.

| Artifact | K (produce once) | m (per-book alternative) | R* break-even | Realistic R | Verdict |
|---|---|---|---|---|---|
| Story skeleton (topology + node plan, human-curated) | $12 | $0.15 (LLM plans fresh) | **80 books** | 200–2,000 | Strongly positive |
| Skeleton *mutation* (derive variant from a parent) | $0.40 | $0.15 | 2.7 books | 20–100 | Positive |
| System prefix / style bible / policy (cached) | write 1.25x | read 1.0x | **1.28 reads** | C-1 per book | Always positive |
| Series character/world bible | $2.00 | $0.06 (re-derive per book) | 33 books | 5–15 per series | **Negative for short series**, only worth it at ≥33 books, i.e. a genuinely long-running series |
| Cover-art style plate (composited, not generated) | $3.00 | $0.100 | **30 books** | thousands | Strongly positive |
| Moderation verdict on unchanged node text | ~$0 | $0.005/node | immediate | high in series/edits | Positive |
| Reading-level calibration per age band | $50 | n/a (deterministic) | n/a | n/a | Do it once |

**The cover-art number deserves emphasis.** At $0.10 per book and a median unit cost of $0.575,
bespoke AI cover art is 17% of COGS for an asset the child looks at for two seconds. A composited
cover, a reused illustrated plate keyed on (genre × age band × palette) with typeset title and a
small generated focal element, costs ~$0.002 and is visually indistinguishable at thumbnail size.
Break-even at 30 books; you will do millions.

**Position 5: bespoke per-book AI cover art is a luxury good. Make it earned, generate it on the
child's second open of a book, or make it a premium-tier feature.** If 25% of books are never
opened, lazy generation alone saves 25% of art spend for zero product change.

### 4.2 What is safe to reuse

- **Story topology / skeleton graphs**, provided a mutation operator perturbs them. Structure is not
  what a reader perceives as "the same book"; prose is.
- **System prompts, style bibles, safety policy, output schema, age-band profiles.** These *must* be
  byte-stable anyway for caching to work, so stability is doubly load-bearing.
- **Deterministic validator artifacts** (reading-level tables, banned-term lists, grammar rules).
- **Moderation verdicts keyed on `hash(node_text) + policy_version + age_band`.** All three key
  components are mandatory (see below).
- **Cover-art style plates and typography systems.**
- **Character and world bibles within a single series for a single child.**
- **The plan-level similarity index**, reuse the embedding index, not the content.

### 4.3 What silently destroys the product if reused

This list matters more than the previous one, because every item on it fails *silently*, the system
reports success and the damage surfaces weeks later through a parent, a review, or a lawyer.

1. **Prose across families.** The entire value proposition is "a book for *my* child about *their*
   premise." Two families receiving substantially similar prose is a product-integrity failure that
   is trivially discoverable (parents talk; screenshots travel) and unrecoverable in reputation
   terms. Structural reuse yes; lexical reuse never. Enforce with a similarity gate on n-gram and
   embedding distance against the published corpus, with a hard reject threshold.
2. **The same skeleton to the same child.** The child notices shape long before an adult does: "it's
   the one where you pick the cave again." Per-child skeleton cooldown of at least 20 books, plus a
   per-child structural-diversity metric.
3. **Moderation verdicts across age bands.** Content that is fine at 13+ is not fine at 3-5. A cache
   key without the band silently promotes teen content into a preschool book. This is the highest-
   severity silent-reuse failure in the system.
4. **Moderation verdicts across policy versions.** You tighten the policy; every previously-approved
   node is now grandfathered under the old rules and never re-evaluated. The key must include the
   policy version, and a policy bump must invalidate and force re-screening of the affected corpus.
   Budget for that re-screen, it is a real cost of every policy change.
5. **Human approval across content versions.** If a single node's text changed, the human's approval
   of the previous version is void. Approval must be bound to a content hash of the exact published
   artifact. Anything else means "approved" is a lie and your primary safety control is decorative.
6. **Cover art across books.** Duplicate covers are the most visible possible quality tell.
7. **A child's personalisation context across children in the same family.** Sibling bleed (the
   younger child's book referencing the elder's private details) is a privacy incident, not a bug.

---

## 5. Model portfolio strategy

### 5.1 Per-stage selection

The right tier at each stage is determined by three things, in this order:

1. **Reasoning density per token.** A stage that emits 200 tokens of high-consequence judgment
   (structural plan, safety adjudication) should be on the best model available, the absolute
   dollar cost is trivial and the downstream leverage is enormous. A stage that emits 160,000
   tokens of prose is the opposite.
2. **Cost of a false negative.** Safety classification's false negatives are unbounded in cost.
   Prose-quality false negatives cost one mildly disappointing book.
3. **Whether the task is well-specified.** Well-specified tasks (classification against a written
   policy, schema filling, tagging) degrade gracefully down-tier. Open-ended tasks (maintaining
   plot coherence across 677 nodes) fall off a cliff.

| Stage | Token profile | Recommended tier | Rationale |
|---|---|---|---|
| Premise screening | tiny in, tiny out | Cheap (Haiku-class) or a trained classifier | High volume, well-specified, ~$0.001/call |
| Skeleton selection / mutation / structural plan | small in, small out | **Frontier (Opus-class), high effort** | Highest reasoning leverage per token in the whole system. Costs ~$0.05, determines the quality of $2 of downstream prose. |
| Prose drafting | large in and out | **Workhorse (Sonnet-class), batch** | 85–95% of all tokens. This is the only stage where tier choice moves the P&L. |
| Prose drafting, ages 3–5 | very simple output | Cheap tier, evaluated | Highly constrained vocabulary and sentence length; test whether the cheap tier passes the reading-level gate at the same rate. If it does, take the 3x saving. |
| Continuity / fidelity judging | large in, small out | Workhorse | Cheap tier is too weak at adversarial continuity checking; this is a false economy |
| Safety classification | large in, small out | **Two models from different families, voting** | Correlated failure is the entire risk. A second opinion at cheap-tier prices is $0.16 on a long book. |
| Repair | medium | **One tier above whatever failed** | Retrying at the same tier is the definition of a non-convergent loop |

### 5.2 One model, or a portfolio?

Single-model advantages are real and usually undersold: one prompt-tuning surface, one caching
prefix, one rate-limit pool, one quality baseline, one deprecation exposure, one set of evals.

Portfolio advantage on the median book: prose is ~90% of tokens, so moving prose from frontier to
workhorse saves `0.90 x (1 - 0.60) = 36%` of token cost, which is 25% of unit cost, so ~9% of
unit cost. Moving classification down-tier saves another 2-3%.

**Position 6: start with one workhorse-tier model for everything, and split out exactly two stages,
structural planning *up* to frontier, and classification *down* to cheap.** Those two are where
the tier/task mismatch is largest and where the evidence is easiest to gather. Do not build a
six-model portfolio before you have per-stage quality telemetry; each additional model is another
prompt to re-tune on every migration, another deprecation clock, another rate-limit pool, and
another source of quality variance you cannot attribute.

### 5.3 Vendor lock: what it actually is

The lock is **not** the API shape. Swapping SDKs is a week. The lock is:

1. **Prompt fitting.** Every prompt has been iterated against one model's quirks. Moving models
   means re-tuning every prompt, and you will not know which prompts degraded without evals.
2. **The eval baseline itself.** Your quality bar is implicitly defined as "what our current model
   does." Without an *absolute* baseline you cannot tell a model regression from a prompt regression.
3. **Gate calibration.** Reading-level thresholds, similarity thresholds and moderation thresholds
   have all been tuned against one generator's output distribution. A new generator shifts the
   distribution and your gates start rejecting good books or passing bad ones.

**Controls:**
- A **narrow** provider interface: messages in, validated structured object out. No provider-specific
  concept (thinking config, cache breakpoints, tool schema dialect, fallback semantics) may leak
  into business logic. Provider-specific optimisation lives in the adapter and nowhere else.
- Keep a **second provider wired and smoke-tested weekly at ~0% traffic**. An untested fallback is
  not a fallback; it is a comforting story. The weekly smoke test is the only thing that makes it real.
- A **golden set**: 150–300 frozen `(premise, age band, skeleton, seed)` tuples with human-adjudicated
  pass/fail and 1–5 quality scores. It is the absolute baseline that makes every other diagnosis
  possible.

### 5.4 Pinning vs. drift

**Pin to exact model identifiers, never to aliases or "latest".**

| | Cost of pinning | Cost of drift |
|---|---|---|
| Nature | Known, scheduled, one-time per migration | Unknown, unscheduled, continuous |
| You miss | Price cuts, quality improvements, new features | Nothing |
| You get | A retirement deadline and a big-bang migration | A model that changes under you |
| Failure mode | Migration crunch on someone else's timetable | Quality silently degrades, **the gates still pass**, children read worse books, and you learn from a parent rather than a dashboard |

Drift is strictly worse, because its failure mode is *invisible to your controls*. A gate calibrated
to the old distribution will happily pass the new one. **Pin, and pay the migration tax on a schedule
you choose.**

**How to make migration continuous instead of an event, the shadow lane.** Run 1–2% of production
requests through the candidate model in parallel: generate both, publish the incumbent's, and diff
(a) the gate verdicts, (b) the golden-set scores, (c) token cost, (d) refusal rate. Cost is 2% of
token spend, ~$0.01 per subscriber-month. It converts every model migration from a two-week fire
drill into a dashboard you have been watching for a month. It is the single highest-ROI piece of
infrastructure in this entire list.

**Detecting silent server-side change on a pinned model** (which does happen, serving stacks,
safety layers, and tokenizers get updated): re-run the golden set weekly against the pinned model
and alarm on any >2σ move in aggregate score or any flip in a safety-gate verdict. Without this you
have no instrument at all for the failure mode "the model changed and nothing errored."

---

## 6. The human bottleneck

### 6.1 The impossibility result

Start with the physical constraint. Adult careful-reading speed for child-appropriate prose with
safety attention is ~200–250 wpm.

```text
118,000 words / 250 wpm = 472 minutes = 7.87 hours per book
  at $28/hr onshore  = $220 per book
  at $8/hr offshore  =  $63 per book
```

Against a fleet ceiling of $0.58. **Full human reading of a long book is not expensive; it is
impossible by a factor of 100–380.** Even the 800-word book at 250 wpm is 3.2 minutes = $0.57
onshore, already the entire fleet budget for one book.

**Consequence, and it is a hard architectural constraint, not a preference: the reviewer cannot read
the book. The review surface must be O(1) in book size, not O(W).**

### 6.2 What the human can afford to do

Model review time as:

```text
T_review = t_fixed + n_flags * t_flag
```

- `t_fixed` = 45s: premise, declared age band, blurb, cover, ending list, the automated gate summary.
- `t_flag` = 20s: one machine-surfaced excerpt with its surrounding two sentences and the reason.
- Target `n_flags ≤ 3`.

```text
T_review = 45 + 3(20) = 105 s = 1.75 min
Cost at $8/hr paid, 75% utilisation ($10.67/productive hr) = $0.311
Cost at $28/hr paid, 75% utilisation ($37.33/productive hr) = $1.089
```

| Books/child/month | Ceiling | Offshore review $0.311 | Onshore review $1.089 |
|---|---|---|---|
| 1 | $2.92 | 11% of ceiling | 37% |
| 4 | $0.73 | 43% | **149%, infeasible** |
| 12 | $0.243 | **128%, infeasible** | 448% |
| Fleet avg 5.0 | $0.58 | 54% | 188% |

**Position 7: onshore staff review is viable only at ≤1 book per subscriber per month, which is not
a product anyone will pay $12.99 for. Offshore review at ≤2 minutes/book consumes half the entire
unit-cost budget. Neither is a business.**

### 6.3 Throughput and the 10x question

At 1.75 min/book and 75% utilisation, one reviewer handles `0.75 x 60 / 1.75 = 25.7 books/hour`,
`206 books/8-hour shift`, `~4,120 books/FTE-month` (160 productive... i.e. 160 paid hours x 0.75 x
25.7... let me state it cleanly: 160 paid hours x 0.75 = 120 productive hours x 34.3 books/productive-hour
= 4,114 books/FTE-month).

| Scale | Books/month | Review-all FTE | Risk-routed FTE (19.25%) | Guardian-primary + 3% audit FTE |
|---|---|---|---|---|
| 10k subs | 50,000 | 12 | 2.3 | 0.4 |
| 100k subs | 500,000 | **122** | 23 | 3.7 |
| 1M subs | 5,000,000 | **1,215** | 234 | **36** |

Cost as a share of net revenue at 100k subs (net revenue $1.155M/month):

```text
Review-all offshore : 122 FTE x $8/hr x 160 hr = $156,160/mo = 13.5% of net revenue
Risk-routed         : 23 FTE                    =  $29,440/mo =  2.5%
Guardian + audit    : 3.7 FTE                   =   $4,736/mo =  0.4%
```

Review-all at 13.5% of net revenue consumes 45% of the entire COGS budget for a task that produces
no product. At 1M subscribers it is a 1,215-person operation, which nobody is going to build, staff,
train, quality-manage, or supervise for child-safety-critical work.

**"Risk-routed"** = human sees a book only if (a) any automated gate flagged anything, (b) it is one
of the family's first three books, or (c) it fell into a 5% random audit of otherwise-clean books.
At an 85% clean-pass rate: `0.15 + 0.05(0.85) = 19.25%` of volume.

**Position 8, the structural resolution.** "Mandatory human approval before a child reads it" is
satisfiable at scale in exactly one configuration: **the mandatory human is the guardian, and staff
review is the risk-triggered second line.** This is not a cost dodge, it is a better product:

- The guardian's marginal cost is zero and their attention is already engaged.
- The guardian has context no reviewer has, this child's fears, this family's values, what happened
  at school last week. They are a *better* reviewer for the 90% of judgments that are about fit
  rather than safety.
- It converts an operational liability into a trust feature you can put on the pricing page.
- The staff line then handles only what the guardian cannot: policy-level safety, cross-family
  pattern detection, and audit.

The costs of this choice must be stated honestly: it adds friction between "I want a book" and "I am
reading a book"; it makes the guardian a bottleneck for the child's experience; and it will produce
rubber-stamping unless the approval surface is genuinely fast and genuinely informative. Measure
guardian time-to-approve and guardian rejection rate. **If the guardian rejection rate is under 2%,
they are rubber-stamping and you no longer have a safety control, you have a consent-capture UI.**

### 6.4 The review-quality risk when you compress time, and it is worse than it looks

Compressing review time does not degrade detection linearly. Two effects compound:

**(a) The prevalence effect.** In signal-detection terms, when the base rate of true positives is
very low, human detection collapses far below what training predicts. Radiology and airport-screening
literature is consistent on this: at ~1% prevalence, miss rates roughly double versus ~50% prevalence.
If 1 in 500 generated books contains a genuine safety problem, a reviewer who has seen 400 clean
books in a row is not meaningfully looking any more, regardless of how many minutes you give them.

**(b) Vigilance decrement.** Sustained-attention performance degrades measurably within 20–35 minutes
of monotonous discrimination work. A reviewer four hours into a shift of near-identical children's
book excerpts is a different instrument than the same reviewer at minute five.

**Both effects are mitigated by the same intervention: salt the queue.** Inject known-bad synthetic
books at ~3% of review volume, drawn from a maintained corpus of realistic near-miss failures.

```text
Cost: 3% more review volume = 3% of review cost = $0.009/book at offshore rates
Buys: (i) a perceptible base rate, restoring detection sensitivity
      (ii) a continuous, per-reviewer measurement of actual catch rate
      (iii) an objective basis for retraining or removing a reviewer
```

Set the bar at 80% catch rate on seeded items; below that, the reviewer is retrained or rotated.
Without seeding you have **no measurement whatsoever** of whether your primary safety control works.
You have a process, a headcount, and an audit trail, but no evidence.

**Position 9: an unmeasured human review gate is worse than no gate, because it converts an unknown
risk into a documented certification of safety.** If you cannot measure reviewer sensitivity, stop
claiming human review in your marketing and your privacy policy, because that claim is a liability.

**The two-sided override-rate test.** Track "books the human rejected or edited *after* all automated
gates passed" as a percentage:

- **Below 2%:** either the automated gates are already sufficient (in which case stop paying for the
  human) or the human is not actually reviewing (in which case the gate is theatre). Investigate,
  do not celebrate.
- **Above 15%:** the automated gates are broken and you are using expensive human attention as a
  primary filter rather than a backstop. Fix the gates.
- **2–15%:** healthy. The human is catching a real residue.

This single metric is the honest answer to "is our human review real?"

### 6.5 What automation must deliver to keep the human affordable

In priority order:

1. **A constant-time review surface.** Never present the book. Present: premise, band, structural
   summary (node count, ending count, longest path, tone arc), the full ending list, the cover, and
   the ranked flag excerpts. Reading the book must be *possible* (one click) but never *required*.
2. **A calibrated flag budget.** Target ≤3 flags/book. A gate that flags 30 excerpts has not helped
   the reviewer, it has moved the reading task and added a UI.
3. **Precision on flags above recall.** A reviewer who dismisses nine false flags in a row stops
   reading the tenth. Flag precision is a first-class metric; alarm below 40%.
4. **Deterministic pre-clearance of everything checkable.** Reading level, banned terms, structural
   integrity, name/PII leakage, ending reachability, tone consistency, all deterministic, all free,
   all resolved before a human sees anything.
5. **One-click reject with a structured reason** that feeds back into gate tuning. A rejection that
   produces no training signal is a wasted purchase of expert judgment.

---

## 7. Operational failure modes and the runbook

| Failure mode | Leading indicator (before impact) | Mitigation | Decision rule |
|---|---|---|---|
| **Provider outage** | Error rate on the primary provider rising above 2% over 5 min; latency p99 doubling | Circuit-break to the secondary provider after 3 consecutive failures. Queue depth absorbs it, generation is async by design, and *that is the main reason to keep it async*. | Auto-failover at 5% error over 5 min. Human decides when to fail *back*, never automatic, flapping between providers is worse than either. |
| **Rate limits** | Token-bucket headroom below 20%; 429 rate above 0.5% | Global token-bucket shaper in front of the provider, sized below the actual limit. Priority lanes: interactive repair > new-subscriber first book > standard queue > pre-generation. Shed the lowest lane first. | Shed pre-generation at 80% utilisation; shed standard queue at 95%; never shed a new subscriber's first book, that is the activation moment. |
| **Cost spike** | Spend-per-hour >3x the trailing-7-day same-hour baseline | Four-scope pre-call ceilings (§3.7). Auto-throttle at 3x, auto-halt at 10x. | Auto-halt is a *page*, not an email. A cost spike is either a bug or an attack, and both need a human inside 15 minutes. |
| **Model regression that degrades quality without failing gates** | **This is the dangerous one, by construction it has no in-band signal.** Out-of-band indicators: weekly golden-set score drift >2σ; guardian rejection rate rising; child completion rate falling; average nodes-read-per-book falling | Weekly pinned-model golden-set run. Shadow lane on the candidate model. Gate thresholds re-validated whenever the generator changes. | Any >2σ golden-set move or any safety-gate verdict flip halts promotion of that model and opens an investigation. Do not ship through it. |
| **Safety escape reaching a child** | Guardian rejection rate rising in a specific band or theme; flag precision falling; a cluster of similar near-misses in the audit sample | Pre-written incident runbook: (1) identify the exact content hash and every child who reached it, (2) unpublish by hash across the whole corpus, (3) notify affected guardians *first*, before any public statement, (4) freeze generation in the affected band, (5) root-cause to a specific gate and a specific model version, (6) add the case to the seeded-bad corpus. | **Any confirmed escape in the 3–8 band halts generation for that band immediately.** Do not debate it in the moment; decide it now, in writing, while nobody is panicking. |
| **Queue backlog** | Queue depth in *hours of work at current drain rate*, not in job count | Autoscale generation workers; shed pre-generation; degrade long books to a scheduled slot. **Human review is the queue that cannot autoscale**, it is capacity-planned weeks ahead. | Alarm at 4h, page at 12h. If review backlog exceeds 24h, stop accepting new long-book requests before the reader-facing experience degrades. |
| **Reviewer capacity shortfall** | Review queue depth trending up over 3 consecutive days; seeded-bad catch rate falling (fatigue) | Pre-negotiated surge capacity with the BPO. Route the overflow to guardians rather than compressing staff time. | **Never compress review time to clear a backlog.** That trades a visible operational problem for an invisible safety problem. Slow the intake instead. |
| **Prompt-cache collapse** | `cache_read_input_tokens` → 0 on multi-chunk jobs; input-token cost per book jumping 3–8x | The CI prefix-stability test (§3.10) catches this before deploy; the runtime alarm catches config-driven cases. | Alarm at cache hit rate <60% on multi-chunk jobs. Treat as a P2, it is a silent 3-8x cost multiplier on your most expensive books. |
| **Provider silently changes tokenizer or serving stack** | Tokens-per-word drifting on a fixed corpus; cost per published book rising with no volume change | Track tokens-per-word on a frozen 10k-word reference text, weekly. | Any >5% move triggers a re-baseline of chunk sizing and `max_tokens` headroom. |
| **Diversity collapse (catalog homogenisation)** | Mean pairwise similarity across recently published books trending up; per-child structural repeat rate rising | Similarity gate at plan stage; skeleton cooldown per child; mutation-operator entropy monitoring | Alarm when p95 pairwise similarity crosses the reject threshold minus one standard deviation, i.e. alarm *before* the gate starts rejecting, not after. |

---

## 8. The metrics dashboard: the 12 numbers, with thresholds

Instrumented and alarming *before* scaling past ~1,000 paying families. Not twelve dashboards,
twelve numbers on one screen.

| # | Metric | Definition | Warn | Page |
|---|---|---|---|---|
| 1 | **Cost per published book** | Total LLM + image + review spend / books published, 7-day trailing, p50 / p90 / p99 | p50 > $0.45 or p90 > $1.00 | p99 > $5.00 |
| 2 | **Generation waste ratio** | Spend on books never published / total generation spend | > 25% | > 40% |
| 3 | **COGS per active subscriber-month** | All variable cost / active subs | > 25% of net ARPU | > 40% of net ARPU |
| 4 | **Books per active child per month** | p50 and p99 | p99 > 20 | p99 > 30, or any single account > 50 |
| 5 | **First-pass gate yield** | Books published with zero repair / books generated | < 60% | < 40% |
| 6 | **Repair attempts per chunk** | Mean and p99 | mean > 1.5 | p99 ≥ R (cap being hit routinely) |
| 7 | **Human review queue depth** | Hours of work at current drain rate | > 4h | > 12h |
| 8 | **Human override rate** | Books rejected/edited by a human *after* all automated gates passed | outside 2–15% | < 1% (gate is theatre) |
| 9 | **Seeded-bad catch rate** | Fraction of injected known-bad books caught, per reviewer and fleet-wide | fleet < 85% | fleet < 75%, or any reviewer < 60% |
| 10 | **Safety escapes** | Confirmed post-publication safety findings per 10k books read | any confirmed finding | any confirmed finding in the 3–8 band → **halt that band** |
| 11 | **Prompt cache hit rate** | cache_read / (cache_read + uncached input), multi-chunk jobs only | < 60% | < 20% |
| 12 | **Golden-set score + gate-verdict drift** | Weekly re-run against the pinned model; aggregate quality score and per-gate verdict distribution | any > 2σ move | any safety-gate verdict flip |

**Supporting instrumentation**, not in the twelve, but I would not run without them:

- `stop_reason` distribution: `max_tokens` rate (warn > 1%), `refusal` rate (warn > 2%).
- Served-model mismatch count (any non-zero is a page).
- Provider balance in days-of-current-burn (warn < 14, page < 5).
- p95 time from request to first readable book, for a *new* subscriber specifically (activation).
- Flag precision: fraction of human-reviewed flags the human agreed with (warn < 40%).

**On alarm design:** every threshold above should be expressed against a trailing baseline, not an
absolute, wherever the underlying quantity has a natural trend. An absolute threshold on a growing
business either fires constantly or never fires at all.

---

## 9. Summary of positions taken

1. A hard per-child monthly book entitlement is the primary unit-economic control. Ship it first.
2. Free-trial generation is unbudgeted CAC (~$5.24 per acquired subscriber) and the most abusable
   surface in the product.
3. Optimisation order is: prune context → batch → tier the model → cache. Model tier is the weakest
   of the four by 12x, and it is the one engineers reach for first.
4. No LLM cost may scale with path count. Make it an architectural invariant with a CI test.
5. Bespoke per-book AI cover art is a luxury; at 17% of median COGS it should be earned or premium.
6. Start with one workhorse model; split out exactly two stages (planning up, classification down).
7. Onshore staff review is not viable above 1 book/subscriber/month at any tested price level.
8. The mandatory human must be the guardian; staff review is the risk-triggered second line. This is
   the only configuration that satisfies the stated requirement at scale.
9. An unmeasured human review gate is worse than no gate, it converts unknown risk into a documented
   certification. Seed the queue with known-bad books at 3% or stop claiming human review.
10. Pin models; drift is strictly worse than pinning because its failure mode is invisible to your
    controls. Run a 1–2% shadow lane so migration is a dashboard, not a fire drill.
11. Long books (>50k words) do not fit in a flat consumer subscription at any tested price level.
    Make them an entitlement (1/quarter standard, 1/month premium) or à la carte. Never uncapped.
12. Retention is a larger term in viability than token price. A 4-point churn improvement beats
    eliminating 100% of token cost.

---

## Checklist: economic and operational requirements

1. Is a target net-ARPU figure documented, computed after store take and payment processing, with a separate year-1 (30% store take) and year-2+ (15%) figure?
2. Is a maximum allowable cost per book documented as a number, derived from net ARPU, a COGS target percentage, and an assumed books-per-subscriber-month?
3. Is the books-per-subscriber-month distribution measured (not assumed), with p50 and p99 reported separately?
4. Is there a hard, enforced per-child monthly book entitlement that blocks generation when exceeded?
5. Is there a separate, lower entitlement for users in a free trial or unverified account state?
6. Is trial-period generation spend attributed to CAC in the financial model rather than to COGS?
7. Is cost-per-book recorded per book at publication time, broken out into generation, judging, image, and human-review components?
8. Is the input-context design bounded (does per-call input size stay constant as book length grows), verified by a test that generates a long book and asserts input tokens grow linearly, not quadratically, in word count?
9. Does every LLM call that could be served asynchronously actually use the batch/async discount tier?
10. Is a per-stage model tier configured, with at least planning separated upward and classification separated downward from the default tier?
11. Is a per-stage reasoning-effort setting configured, with mechanical stages set to low effort?
12. Is `stop_reason` recorded on every LLM call and aggregated, with the `max_tokens` rate alarmed above 1% and the `refusal` rate above 2%?
13. Is the truncation recovery path a continuation rather than a restart of the chunk?
14. Is there a hard cap on LLM repair attempts per chunk, and does exceeding it change strategy rather than re-roll the same prompt?
15. Is there a hard per-book spend ceiling enforced before each call that kills the job and surfaces a product-level failure?
16. Are spend ceilings enforced before the API call at all four scopes: per job, per user per day, per tenant per day, and global per day?
17. Is there a documented, tested kill switch that halts all generation without requiring a deploy?
18. Is provider balance monitored in days-of-current-burn, alarming below 14 days and paging below 5?
19. Are completed generation chunks checkpointed to durable storage, and has the resume-from-checkpoint path been tested end to end?
20. Is `response.model` asserted equal to the requested model on every call, with any mismatch raising a high-severity event?
21. Is cost computed from the served model rather than the requested model?
22. Is there a CI test that builds the same request twice and asserts the cacheable prefix is byte-identical?
23. Is prompt-cache hit rate monitored on multi-chunk jobs, alarming below 60%?
24. Are all structured outputs produced via provider-native strict schema enforcement rather than parsed-and-retried free text?
25. Is the premise screened by a cheap gate before any prose generation tokens are spent?
26. Is the plan-level diversity/similarity check run before prose generation rather than after?
27. Are the gates ordered so that cheap, high-rejection-probability checks run before expensive ones?
28. Is the ratio of cost-per-generated-book to cost-per-published-book tracked, alarming above 1.3?
29. Is the count of LLM judge calls provably independent of the number of root-to-ending paths, asserted by a test?
30. Are node-local and edge-local structural invariants checked deterministically rather than by an LLM?
31. Are LLM continuity checks run on a bounded, edge-covering sample of walks with a fixed K?
32. Is every moderation verdict cache key composed of content hash, policy version, AND age band?
33. Does a policy-version bump invalidate affected cached verdicts and force re-screening, with that re-screen cost budgeted?
34. Is human approval bound to a content hash of the exact published artifact, so any content change voids prior approval?
35. Is there a similarity gate that blocks publication of prose substantially similar to any existing published book in the corpus?
36. Is there a per-child skeleton cooldown preventing structural repetition within a defined window?
37. Is sibling personalisation context isolated so one child's private details cannot appear in another child's book?
38. Is the human review surface constant-time in book length (does not require reading the book)?
39. Is there a target flag budget per book, with flag count per book measured and alarmed above it?
40. Is flag precision (fraction of flags the human agreed with) measured and alarmed below 40%?
41. Is the human override rate measured, with alarms on BOTH ends of the 2–15% band?
42. Are known-bad synthetic books seeded into the review queue at a measured rate of at least 3%?
43. Is per-reviewer catch rate on seeded items measured, with a documented threshold for retraining or rotation?
44. Is human review time per book measured (p50 and p90) rather than assumed?
45. Is review queue depth expressed in hours of work at current drain rate, alarming at 4h and paging at 12h?
46. Is there a written policy forbidding compression of review time as a backlog remedy?
47. Is a frozen golden set of at least 150 premise/band/skeleton tuples with human-adjudicated outcomes maintained in version control?
48. Is the golden set re-run weekly against the pinned production model, with a >2σ drift alarm?
49. Are all models pinned to exact identifiers, with no aliases or "latest" references anywhere in production configuration?
50. Is a shadow lane running 1–2% of traffic against a candidate model, diffing gate verdicts and quality scores?
51. Is a secondary provider wired and smoke-tested at least weekly, even at zero production traffic?
52. Is provider-specific logic confined to an adapter layer, with a test asserting no provider concept appears in business logic?
53. Is tokens-per-word tracked against a frozen reference text weekly to detect tokenizer or serving-stack changes?
54. Is there a written, rehearsed safety-escape runbook covering identification by content hash, corpus-wide unpublish, guardian notification ordering, band freeze, and root-cause attribution to a model version?
55. Is there a pre-committed written rule that any confirmed safety escape in the youngest age band halts generation for that band?
56. Is provider failover automatic on a defined error-rate threshold, with fail-back requiring human authorisation?
57. Are generation requests prioritised into lanes, with pre-generation shed first and new-subscriber first books never shed?
58. Is monthly logo churn measured per cohort, and is the unit-economic model re-run whenever it moves by more than 2 points?
59. Is contribution margin per cohort tracked for at least the first three months, given that consumption is front-loaded and revenue is not?
60. Are all twelve dashboard metrics in §8 instrumented, with thresholds configured and at least one alarm having fired and been acknowledged in a test?
