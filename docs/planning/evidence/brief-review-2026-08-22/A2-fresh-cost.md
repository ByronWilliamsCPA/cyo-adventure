# A2 fresh-eyes: cost model and cost-engineering discipline (goal-only, no brief or repo access)

# Cost Model and Cost-Engineering Discipline for a Human-Gated, LLM-Generated CYOA Book Factory

Fresh-eyes control specification, from first principles only. All dollar figures and ratios below are illustrative placeholders; the discipline requires live price sheets treated as versioned config, never numbers baked into code or memory.

---

## 0. Framing, Units, and Accounting Boundaries

- 0.1 Primary unit: one published book (passed all automated gates AND human approval, readable by a child). Everything else is work-in-progress, scrap, or asset.
- 0.2 Secondary normalizers: cost per 1,000 published words; cost per node; cost per ending path. Needed because catalog spans ~800 words to ~118,000 words (a ~150x size range makes "cost per book" meaningless without classes).
- 0.3 Demand-truth unit: cost per book actually read (and per reading-hour delivered). A published-but-never-opened book is inventory waste; track read-rate of published books.
- 0.4 Two currencies always: tokens (stable, comparable over time) and dollars (computed at call time from a price snapshot, never reconstructed later, because prices change).
- 0.5 Cost classes: age band (3-5, 6-8, 9-12, 13-15, 16+) x size tier (S <2k words, M 2-10k, L 10-40k, XL >40k words or >200 nodes). All targets, dashboards, and alerts are per class; global averages are banned as decision inputs.
- 0.6 Fully-loaded unit cost = direct generation + expected rework + scrap allocation + moderation + human minutes at loaded labor rate + amortized reusable assets + allocated eval/monitoring + infra allocation. Report marginal cost separately; judge levers on fully loaded.
- 0.7 Master funnel formula: for stages s=1..k with post-repair pass yield y_s, expected units entering stage s per published book n_s = 1 / prod(y_j for j >= s). Cost per published book = sum over s of n_s x (c_s + r_s) + Human + Amortization + Overhead, where c_s is stage cost per entrant and r_s is expected repair spend per entrant. This is manufacturing yield accounting (first-pass yield, rolled throughput yield, cost of poor quality); adopt the vocabulary explicitly.
- 0.8 Recipe = {model snapshot ID, prompt version, params (temp, max_tokens, thinking budget), template version, policy version}. Unit costs are keyed by recipe; recipes are promoted like code through CI.
- 0.9 Accounting boundary: production book runs = COGS; template/skeleton building, fine-tune training, eval-set creation, experiments = R&D, amortized into COGS by policy (0.10). Dev laptops, CI, staging generations tagged and excluded from unit economics but tracked in total spend.
- 0.10 Amortization policy: per-use charge for reusable assets (asset cost / expected safe uses), with a write-off trigger when an asset is retired early. Choose the horizon once with finance; revisit quarterly.
- 0.11 Risk-adjusted term: include E[safety incident] = P(incident) x incident cost (legal, churn, app-store removal, brand) as a line justifying moderation and human spend; cost cuts to safety stages must show this term does not rise.
- 0.12 Published-word counting rule: define once whether choice labels, endings text, and metadata count as published words; normalizers are garbage if the denominator is ambiguous.

Questions that must be answered:
- 0.Q1 What is our unit: published, or read? Who owns the unit-cost number (single budget owner per stage)?
- 0.Q2 What is in COGS vs R&D, and what amortization horizon applies to templates, evals, and fine-tunes?
- 0.Q3 What is the target fully-loaded cost per class, and what gross margin does product pricing require it to support (entitlements per subscription tier sized off this)?

Failure modes:
- 0.F1 Unit cost computed only for successful books; scrap silently excluded, so the number is fiction.
- 0.F2 Averages across classes; one XL book distorts the month and nobody can explain variance.
- 0.F3 Two teams computing "cost per book" with different denominators (attempted vs published vs read).

---

## 1. Complete Unit-Economics Model: Every Cost Line

### 1A. Generation tokens, by stage

- 1A.1 Intake/brief normalization: parse and structure the guardian request; small (hundreds of tokens), cheap model.
- 1A.2 Brief screening: moderate the request itself before any spend (inappropriate/doomed/prompt-injection requests blocked preflight); cheap, but it protects everything downstream.
- 1A.3 Planning/outline/authoring plan: high-leverage stage; errors here multiply downstream, so typically the strongest model; tokens modest (2-10k out).
- 1A.4 Structure/graph: either (a) generated per book (expensive, high failure rate on topology) or (b) selected/adapted from a pre-validated skeleton library (near-zero marginal, amortized under 1D). The (b) choice is itself the largest structural cost decision.
- 1A.5 Per-node prose fill: the volume driver. Cost per node = input (system prompt + style guide + band profile + character/world sheet + local graph context + rolling summary) + output (node text). For XL books, input context dominates unless cached; see 1A.7.
- 1A.6 Fixed per-call overhead: every node call carries system/schema/example tokens; many tiny nodes cost more per word than fewer large ones. Track overhead tokens per call; consider multi-node batching per call (continuity risk).
- 1A.7 Context policy for big books: bounded context per node call (e.g., fixed 3-8k: neighbors + hierarchical summaries + fact sheet), so token cost is linear in nodes. Sending "story so far" makes cost quadratic in book length; this single design choice can be a 5-10x swing on the 118k-word book.
- 1A.8 Continuity/consistency passes: cross-node coherence checks or sibling-choice consistency (LLM-based); input-heavy.
- 1A.9 Choice text, endings, and state/condition annotations.
- 1A.10 Metadata: title, blurb, tags, reading-level annotation, teaser.
- 1A.11 Cover art: per-image cost x (1 + retry rate for unsafe/bad images); generate at approval time, not request time, so scrapped books never buy art.
- 1A.12 Optional per-node/scene illustration: policy decision with its own budget per class; per-node art on a 600-node book would dominate total cost; cap explicitly.
- 1A.13 Thinking/reasoning tokens: billed as output on reasoning models and often invisible in naive logging; track separately, cap per stage.
- 1A.14 Structured-output overhead: schema tokens and stricter decoding; small but present on every call.
- 1A.15 Embeddings: per-node embeddings for similarity/diversity/recommendation; small per book, real at catalog scale.
- 1A.16 Personalization/localization variants: each variant multiplies fill and moderation cost; count variants as fractional books.
- 1A.17 Future line to reserve: read-aloud audio (TTS) for young bands would become the dominant per-word cost if added; keep a placeholder line so it is priced before launch, not after.

### 1B. Retries and repair loops

- 1B.1 Transport retries: timeouts, 429s, 5xx; you often still pay input tokens for truncated/failed streams; count billed-but-useless tokens.
- 1B.2 Format retries: JSON/schema parse failures; should trend to ~0 with constrained decoding.
- 1B.3 Content repair: targeted node regeneration after validator/moderation failure; cost = repair prompt (failure feedback + local context) + new output + mandatory re-validation + re-moderation of the changed node and its neighbors. The re-screen cost of repaired content is the most commonly forgotten line.
- 1B.4 Escalation retries: retry-on-bigger-model after cheap model fails; ladder must be explicit (cheap -> cheap+feedback -> mid -> flagship), never instant flagship.
- 1B.5 Oscillation waste: fix A breaks B breaks A; bounded by iteration caps (see 5).
- 1B.6 Best-of-N sampling where used (e.g., planning): N x stage cost plus judge cost; a deliberate quality buy, itemized.
- 1B.7 Duplicate work from queue redelivery: at-least-once queues re-run jobs; idempotency keys or content-addressed memoization prevent double billing.

### 1C. Scrap from failed quality gates

- 1C.1 Node scrap: nodes abandoned after max repair iterations; cost of all attempts charged to the book.
- 1C.2 Book scrap (automated): books killed by validator/moderation hard-fails; full sunk cost allocated across the class's published books (scrap multiplier = 1/RTY).
- 1C.3 Book scrap (human): human reviewer rejects; the most expensive scrap (it consumed everything including human minutes); Pareto its causes weekly.
- 1C.4 Demand scrap: guardian rejects the delivered book (didn't match intent); driven by brief quality; track separately from quality scrap because the fix is intake UX, not models.
- 1C.5 Kill-early savings: an early-abort predictor (validator failure density or moderation flags in the first N nodes) moves scrap left where it is cheap; measure "scrap cost per scrapped book" trending down.
- 1C.6 Inventory scrap: pre-built catalog books never read; carrying cost = full unit cost with zero reads.

### 1D. Reusable-asset amortization

- 1D.1 Skeleton/template library: authoring + mutation + calibration + validation cost, amortized per use; each template has a max safe use count per band per period (diversity constraint), so amortization denominators are bounded, not infinite.
- 1D.2 Template lineage: a template mutated from another inherits chained cost; track lineage so the library's true cost is known.
- 1D.3 Prompt/style-guide engineering time (labor) per band.
- 1D.4 Character/world bibles for series: series books share them; expect marginal series book 20-40% cheaper; track series vs standalone unit cost separately.
- 1D.5 Golden eval sets and labeled data: creation and refresh cost.
- 1D.6 Fine-tuned/distilled model training runs plus hosted-model minimums (some providers bill hourly for hosting a fine-tune even when idle).
- 1D.7 Review tooling and pipeline software development: amortized or expensed by policy; do not silently exclude.
- 1D.8 The data flywheel as an asset: human edits and rejection reasons are free labeled data; mining them into prompt fixes/fine-tune data reduces future cost; assign this asset a value so review is not seen as pure cost.

### 1E. Evaluation and monitoring overhead

- 1E.1 Regression eval runs: every recipe change (model, prompt, params, template, policy) re-runs golden sets; token cost per run x change frequency; commonly reaches 10-30% of total LLM spend, so budget it explicitly.
- 1E.2 LLM-judge spend inside evals.
- 1E.3 Weekly canary generations against fixed inputs per provider/model to detect silent model drift.
- 1E.4 Continuous production QA: re-moderate a random x% of published books monthly; drift detection on gate scores.
- 1E.5 Human calibration labeling for eval sets and threshold tuning.
- 1E.6 Eval memoization: fingerprint (recipe + input) and reuse cached results; no-op changes must not re-buy the whole eval.
- 1E.7 Observability infra: raw-output retention (full transcripts including retries; XL books with retries are tens of MB), log pipeline, dashboards; cheap per book, real at scale; tiered retention policy.
- 1E.8 CI/e2e tests that hit live LLM APIs: a classic silent leak; use recorded fixtures; live-API tests only in a tagged, capped budget.

### 1F. Moderation model spend

- 1F.1 Per-node safety classification: input ~= full node text per classifier; multiple axes (violence, fear, age-fit, tone) as one call or several; per-book cost scales with words.
- 1F.2 Whole-book/arc-level passes: themes and cumulative intensity that node-level checks miss.
- 1F.3 Ensemble/second-opinion on borderline scores: uncertainty-band routing; only ~5-15% of content should reach the expensive tier.
- 1F.4 Fidelity review: does prose match the approved plan and band profile (LLM-based).
- 1F.5 Metadata and cover-art moderation: titles, blurbs, and images also face children; frequently forgotten.
- 1F.6 Rescreen events: policy version change or moderation-model upgrade forces catalog re-screening; cost = catalog size x per-book moderation; requires delta/incremental screening design (content-addressed, per-node policy version tags) or it becomes a recurring six-figure surprise.
- 1F.7 False-positive cost: over-blocking safe content forces rewrites; FP rate is a cost metric (target FP <5-10% at gate), distinct from the FN safety metric (near-zero tolerance, policy-set).
- 1F.8 Appeals/second-look flow: human or model re-adjudication of contested blocks.

### 1G. Human review minutes

- 1G.1 Review minutes per book = f(words, nodes, endings, band risk, flags raised); priced at loaded rate (salary + overhead + management + tooling).
- 1G.2 Sampling policy for XL books: full read is 5-8 hours at review pace and is not viable; policy: 100% of endings, 100% of risk-flagged nodes, full spine path, random k% of remaining nodes with stated confidence; store the achieved coverage per book as audit evidence.
- 1G.3 Change-aware re-review: after an edit, review only the diff + neighbor nodes, not the book.
- 1G.4 Editor fix time: humans repairing nodes directly (sometimes cheaper than another model loop); track minutes and count the edit as labeled data (1D.8).
- 1G.5 Escalation/second review on borderline books.
- 1G.6 Reviewer QA: 5-10% double-review for inter-rater reliability; seeded known-bad decoy books to measure catch rate; both are real minutes.
- 1G.7 Recruiting, training, calibration sessions; 4-8 week ramp per reviewer.
- 1G.8 Reviewer well-being: exposure to disturbing generation failures; rotation and support affect capacity and attrition cost.
- 1G.9 Guardian-side approval time is free to you but not to conversion: measure guardian approval friction as a product metric.

### 1H. Infrastructure

- 1H.1 Queue/workers, DB, cache, storage, CDN for published assets; image storage and optimization.
- 1H.2 Self-hosted GPU serving if used: $/GPU-hour / utilization; cold starts on serverless GPU; idle reserved capacity.
- 1H.3 Vector/ANN index for similarity and diversity checks.
- 1H.4 Third-party platform fees (auth/backend), monitoring, error tracking.
- 1H.5 Egress, backups, raw-output storage tiers.
- 1H.6 Allocation rule: infra allocated per book by driver (tokens for GPU, GB for storage), or held as a per-book flat overhead if small (<5% of unit cost).

### 1I. Demand-side and lifecycle costs

- 1I.1 Version 2+ of a book: edits, re-moderation, re-approval, re-publish; lifetime cost per book accumulates; report "cost to date" per book, not just birth cost.
- 1I.2 Per-guardian request quotas/entitlements: demand-side cost control; a request-spamming account burns real money; product tier defines N books/month.
- 1I.3 Expedited lane: rush requests forfeit batch discounts; price or ration them.
- 1I.4 Sales/demo/sample books tagged separately.

Questions that must be answered (Section 1):
- 1.Q1 What fraction of unit cost is tokens vs moderation vs human vs amortization vs infra, per class? (Expect human to dominate S-tier young bands; tokens and human to co-dominate XL.)
- 1.Q2 What is the scrap multiplier per class and its top 3 causes?
- 1.Q3 What is the token spend ratio (all tokens consumed, all stages/attempts, divided by tokens in the published text)?
- 1.Q4 Where is the human-vs-token cost crossover as book size grows?
- 1.Q5 What does a repaired node really cost end-to-end, including re-screening?

Measurements that must exist (metric, rough target):
- 1.M1 Fully-loaded cost per published book, per class; illustrative maturity targets: S-tier low single-digit dollars ex-human; XL dominated by review; set real targets after 60 days of data.
- 1.M2 Token spend ratio: <40x early, <15x mature.
- 1.M3 First-pass yield per gate: validator >90%, moderation >95%, human approval >95% mature.
- 1.M4 Rolled throughput yield (all automated gates): >75% early, >90% mature.
- 1.M5 Mean repair iterations <1.3; hard cap 3; oscillation incidents ~0.
- 1.M6 Waste share (spend on never-published output / total spend): <25% mature.
- 1.M7 Review minutes per book by tier: S 5-10, M 15-30, L 45-90, XL 90-180 with sampled coverage; coverage recorded per book.
- 1.M8 Cache hit rate on fill-stage input tokens: >70%.
- 1.M9 Cover-art retries per accepted cover: <1.5.
- 1.M10 Eval spend as % of total LLM spend: known and budgeted (10-30% band).
- 1.M11 Read-rate of published books within 60 days: per-class floor; kill pre-build lines below it.

Failure modes (Section 1):
- 1.F1 Repair loops re-screened for free on paper because nobody metered re-moderation.
- 1.F2 Context growth makes XL books superlinear; discovered on the invoice.
- 1.F3 Amortization denominators assume infinite template reuse; diversity limits make true per-use cost 3-5x higher.
- 1.F4 Human minutes untracked because reviewers are salaried, so the largest line is invisible.
- 1.F5 Thinking tokens, image spend, embeddings, and eval spend each individually "too small to track" until together they are 30% of the bill.

---

## 2. Computing and Tracking Cost per Published Book (by Band and Length)

- 2.1 Telemetry event, one row per model call: {timestamp, correlation/book ID, stage, node ID, attempt #, retry reason, provider, model snapshot, recipe version, input tokens (cached vs uncached split), output tokens (thinking split), latency, price snapshot ID, computed cost, environment tag, outcome}.
- 2.2 Append-only cost ledger; idempotent writes (queue redelivery must not double-count); cost computed at call time from an effective-dated price table.
- 2.3 Book cost record: lifetime accumulator across attempts, versions, re-screens; plus human-minute entries from the review tool (start/stop or task-timer, not self-report).
- 2.4 Roll-ups: per book, per class (band x size), per stage, per recipe, per template, per provider/model, per cause-of-waste; weekly and monthly grain.
- 2.5 Pre-quote estimator: before generation, estimate cost from the skeleton (nodes x expected tokens x price, plus expected repair overhead by class history); used for preflight caps (5.2) and capacity planning; track estimator error (target: within 20% at P50, within 50% at P90).
- 2.6 Distribution reporting: median and P90 unit cost per class; P90/median <2.5 is the predictability target (the brief demands predictable unit cost, so dispersion is a first-class metric, not just the mean).
- 2.7 Big-book linearity check: plot cost per node vs book size; slope should be flat; a rising slope means context leakage (1A.7) and is an alertable regression.
- 2.8 Band overlays: same size tier compared across bands isolates band-driven costs (3-5: near-zero tokens, max safety/human cost share; 16+: max tokens and moderation ambiguity).
- 2.9 Variance decomposition: month-over-month unit cost delta explained by (price changes) + (mix shift across classes) + (yield changes) + (recipe changes) + (unexplained); unexplained >10% triggers investigation.
- 2.10 Reconciliation: internal ledger vs provider invoices monthly; variance <3%; gaps mean untracked calls, misconfig, or a leaked key.
- 2.11 Rituals: weekly 30-minute cost review (per-class trends, top 10 most expensive books with narratives, waste Pareto); monthly deep review with finance; cost postmortem after any anomaly, filed like an incident.
- 2.12 Cost regression alerting: any book exceeding 2x its class median mid-flight pauses for triage; any class median moving >15% week over week without a planned change alerts.
- 2.13 Staging/dev/eval spend tracked under separate keys and tags so production unit economics stay clean, but total org spend is still reviewed.

Questions:
- 2.Q1 Can we answer "why was this specific book expensive" in under 5 minutes from the ledger?
- 2.Q2 Can we produce the exact spend of any recipe version, to support promote/rollback decisions?
- 2.Q3 Does the estimator error narrow over time per class?

Measurements:
- 2.M1 Attribution coverage: >99% of provider-billed tokens carry a book ID or an explicit non-book tag.
- 2.M2 Reconciliation variance <3%; time-to-explain any variance <5 business days.
- 2.M3 P90/median unit cost per class <2.5; week-over-week unit cost variance <10% excluding planned changes.
- 2.M4 Monthly spend forecast error <15%.

Failure modes:
- 2.F1 Costs reconstructed later at current prices, corrupting history.
- 2.F2 Cached vs uncached input not split, hiding cache regressions.
- 2.F3 Dashboard drift: the dashboard is trusted but disagrees with the invoice; meta-monitor it.
- 2.F4 Human minutes self-reported and fictional.
- 2.F5 The one 118k-word book each month makes every global chart useless because classes were not enforced.

---

## 3. Cost-Reduction Levers (Mechanism, Expected Magnitude, Risk, Guard)

Token and call level:
- 3.1 Prompt caching (stable prefix: system + style guide + band profile + world sheet; variable suffix per node): 50-90% off cached input on hits; risk low; guard: cache-hit-rate alarm, TTL vs queue latency (batch jobs slower than TTL silently lose hits), prompt ordered stable-first.
- 3.2 Batch/async APIs for the whole offline pipeline: typically ~50% off; risk: 24h-class turnaround, so SLA and expedited lane must be designed; guard: queue windows, rush lane at full price.
- 3.3 Bounded context per node (summaries + neighbors, never whole-story): converts quadratic to linear on XL books, up to 5-10x on the largest; risk: continuity errors; guard: continuity checker pass and human spot checks on long-range references.
- 3.4 Constrained decoding/structured outputs: kills 2-10% parse-retry waste; risk near zero.
- 3.5 max_tokens and stop sequences per stage; thinking-budget caps on reasoning models: caps tail blowups (repetition loops); risk: truncation, guard with truncation detection and retry.
- 3.6 Prompt diet: prune few-shot examples and accreted instructions quarterly ("prompt creep" review): 10-30% input; risk: quality dip; guard: eval before/after, input-tokens-per-node trend alarm.
- 3.7 Multi-node batching per call for tiny-node books: cuts per-call fixed overhead 2-4x on S-tier; risk: cross-node bleed; guard: per-node validation still runs.

Pipeline level:
- 3.8 Gate ordering, cheapest first: deterministic validator (CPU, ~free) before LLM moderation before human; savings proportional to early-fail rate; risk none; guard: keep gates independent so ordering stays valid.
- 3.9 Targeted node repair instead of whole-book regeneration: 5-20x cheaper per fix; risk: local fix breaks global coherence; guard: neighbor re-moderation and continuity check after repair.
- 3.10 Early-abort predictor (kill doomed books after first N nodes): recovers most of scrap's downstream cost; risk: false kills discard good books; guard: measure kill precision >90% before automating.
- 3.11 Delta re-screening (content-hash nodes; on repair or policy change, re-moderate only changed/affected nodes + neighbors): 5-20x on rescreen events; risk: contextual meaning shifts; guard: whole-book pass still sampled.
- 3.12 Escalation ladder for retries (never instant flagship fallback): 2-5x on retry spend; risk: added latency; guard: ladder depth cap.
- 3.13 Generate cover art after human approval: saves art cost x scrap rate; risk: publish latency; guard: parallelize with final review.
- 3.14 Memoized generation cache keyed by (recipe + input): reruns, CI, and eval reuse identical outputs free; risk: staleness across recipe bumps; guard: recipe in the key.

Model level:
- 3.15 Right-size model per stage per band (flagship for planning, small for 3-5 band prose, mid for 9-12+): 3-20x on the swapped stage; risk: quality regression, possibly deferred (human minutes rise); guard: Section 4 methodology, judged on fully-loaded cost.
- 3.16 Draft-with-small, polish-with-large (or plan-with-large, write-with-small): 40-70% of prose spend; risk medium; guard: champion/challenger eval.
- 3.17 Moderation cascade: cheap screener on 100%, expensive model only on uncertainty band, human on the residue: 60-90% of moderation spend; risk: safety FN, the one place cost must not lead; guard: gold-set non-inferiority with near-zero severe-FN bar plus ongoing human sampling.
- 3.18 Best-of-N with a cheap judge only where leverage is highest (planning, endings): buys quality at known cost; risk: judge bias; guard: periodic human agreement check on the judge.
- 3.19 Fine-tune/distill the fill stage at volume: 2-10x inference plus higher FPY; risk: upfront cost, maintenance, forced retrain on base deprecation, hosted-minimum fees; guard: breakeven math (training + ops) / (per-book savings x monthly volume) < 6-9 months before committing.
- 3.20 Self-host open models for high-volume low-risk stages (drafting young bands, moderation pre-screen only as a first pass): 5-20x at >40-60% sustained utilization; risk: quality, ops burden, license terms, and never as the sole safety gate; guard: Section 6.9 economics done honestly with labor included.

Asset and demand level:
- 3.21 Skeleton/template reuse with per-template use caps: removes structure generation and raises validator FPY; 20-40% of generation cost; risk: catalog sameness; guard: similarity metrics, novelty budget, standing template-production budget line.
- 3.22 Series economics (shared bibles, recurring casts): 20-40% cheaper marginal series book; risk: series lock-in of defects; guard: series-level review sampling.
- 3.23 Intake quality (structured briefs, examples, guardrail prompts to the guardian): cuts demand scrap 30-50%; risk: intake friction; guard: brief completeness score correlated with rejection rate.
- 3.24 Human-review throughput tooling (risk-ranked queue, diff review, path-coverage optimizer, checklists, TTS skim): 2-5x reviewer throughput, the biggest lever at scale; risk: sampling misses; guard: decoy catch rate and double-review QA hold while minutes fall.

Commercial level:
- 3.25 Committed-use/enterprise discounts: 10-40%; risk: overcommit on a falling-price curve, lock-in; guard: commit only to P25-forecast baseload, short terms.
- 3.26 Provider arbitrage among eval-qualified models per stage: 10-50% opportunistic; risk: churn cost, subtle quality drift; guard: only route among recipes that passed the same eval bar.
- 3.27 SLA credits and incident refunds: claim them; risk: none; guard: incident-tagged spend report per provider.

Failure modes (Section 3):
- 3.F1 Stage-local savings that raise total cost (cheaper model doubles repair and human minutes); every lever is judged on fully-loaded unit cost.
- 3.F2 Stacking levers without isolation; run one change per class at a time or attribute via recipe versioning.
- 3.F3 Cache assumed on but silently off after a prompt reorder; input spend doubles quietly.
- 3.F4 Cost lever shipped without an eval gate "because it is just infra".

---

## 4. Cost-Quality Tradeoff Methodology (When Is Cheaper Good Enough, Per Stage)

- 4.1 Stage criticality map: rank stages by error amplification. Planning/structure errors propagate to every node (use best models, spend for quality); per-node prose errors are local (cheapest viable); moderation is safety-critical (cost never leads); metadata is low stakes (cheapest).
- 4.2 Per-stage, per-band quality definition, measurable offline: gate pass rates, validator error density, band-fit score, human approval rate, human edit distance, and downstream reader engagement (completion, re-reads) as the slow ground truth.
- 4.3 Golden sets per band per stage: 200-500 items, human-labeled, refreshed quarterly, held out from all prompts and fine-tunes (contamination check on every training/data change).
- 4.4 Decision rule for a cheaper model: adopt if (a) safety metrics non-inferior with margin (one-sided test; severe-class FN upper confidence bound below the policy bar), (b) effective fully-loaded cost per published book actually falls after counting FPY change, added repairs, and human minutes, (c) no counter-metric regression (4.8). A model 5x cheaper per call that halves FPY usually loses.
- 4.5 Promotion pipeline: offline eval -> shadow run on x% of real briefs (generate but do not publish; compare gates and blind human ratings) -> canary cohort (publish small %, watch approval rate and guardian rejections) -> full rollout; automatic rollback thresholds predeclared.
- 4.6 Champion/challenger standing infrastructure: any stage can host a challenger recipe at any time; results append to a scoreboard of $/published-book vs quality per recipe.
- 4.7 Re-eval triggers (mandatory): provider model version change, price change that alters routing, prompt/template/params change, moderation policy change, and calendar (monthly) even with no changes, to catch silent drift.
- 4.8 Counter-metrics against Goodharting: gates are optimizable; keep periodic blind human panels (style, delight, age-voice) and reader engagement as metrics the pipeline cannot see or optimize directly.
- 4.9 Per-band bars: 3-5 band: linguistic bar low (small models fine), safety bar maximal; 16+: writing-quality bar high (mid/flagship), moderation ambiguity high (more escalation budget).
- 4.10 Judge governance: LLM judges are themselves recipes; calibrate against human labels quarterly; judge drift invalidates eval history.
- 4.11 Sample-size honesty: detecting a 5pp FPY change needs hundreds of items; forbid model swaps justified on 20 anecdotes.
- 4.12 Quality floor definition owned by editorial, not engineering: human approval rate >=95%, guardian rejection <=x%, complaint rate ~0; a lever that dents the floor reverts regardless of savings.

Failure modes:
- 4.F1 Eval-set leakage into prompts or fine-tunes: gates green, production rots.
- 4.F2 Non-inferiority tested on the mean while the tail (worst 5% of nodes) is what hurts children; evaluate tails.
- 4.F3 One global bar across bands: over-spending on 3-5 prose, under-spending on 16+.
- 4.F4 Quality regressions detected only via human reviewers, silently converting model savings into review minutes.

---

## 5. Budget Guardrails and Failure-Spend Controls

Caps hierarchy (all enforced in code, all alert before they bite):
- 5.1 Per-call: max_tokens, thinking budget, timeout.
- 5.2 Per-node: max generation attempts (2-3), max repair iterations (3), then human triage or scrap.
- 5.3 Per-book: dollar/token budget by class (e.g., 3x class median) checked continuously; breach pauses the book into triage, never silent retry.
- 5.4 Per-stage daily budget; per-provider-key daily/weekly caps with 50/80/100% alerts; org emergency ceiling (e.g., 3x monthly plan pro-rated) that hard-stops and requires human re-arm.
- 5.5 Concurrency caps sized so worst-case burn per hour is bounded (workers x max tokens x price = known ceiling).

Preflight checks (before any book, stricter for XL):
- 5.6 Cost pre-quote vs remaining class budget; skeleton validity pre-check (never buy prose for a broken graph); brief passed screening; recipe pinned and eval-passed; price table fresh; provider health green; cache warm; 3-node dry run sane before committing 600 nodes.

Runaway detection (auto-pause plus page):
- 5.7 Same node re-attempted >N; per-book spend rate above class envelope; repair oscillation detected by content-hash cycling; output token count per call outside envelope (repetition loop); queue depth x est. cost exceeding remaining daily budget; retry rate spike during provider incidents (circuit breaker with exponential backoff, or a retry storm on a backlog multiplies the incident's cost).

Kill switches:
- 5.8 Per-provider, per-model, per-stage, and global pipeline pause; one command, idempotent, tested in a quarterly drill.
- 5.9 Checkpoint/resume: pausing must not lose in-flight work; node fills are idempotent and content-addressed so resume never re-buys completed nodes (a kill switch that forces full restarts doubles incident cost).

Isolation and hygiene:
- 5.10 Separate keys/projects per environment (prod/staging/dev/eval/CI) and ideally per stage; a runaway experiment cannot drain prod.
- 5.11 Scoped keys, rotation, spend alerts as leaked-key detection; anomalous geography/latency on a key alerts.
- 5.12 Price/config tripwires: billed unit price inferred from invoice vs config mismatch alerts (catches silent repricing and the classic mistyped model ID that is 30x the intended price).
- 5.13 Waste ledger: all failure spend categorized (transport, schema, gate-fail, human-reject, abandoned, duplicate) with weekly Pareto; target waste <25% of LLM spend mature.
- 5.14 Every anomaly gets a cost postmortem with a named prevention item, same discipline as outages.

Measurements:
- 5.M1 Time-to-detect anomalous burn: <15 minutes (burn-rate alarms, not daily rollups).
- 5.M2 % of spend covered by a cap at every level of the hierarchy: 100%.
- 5.M3 Kill-switch drill: quarterly, with measured stop latency and zero lost work.
- 5.M4 Duplicate-billing rate from redelivery: ~0 (idempotency verified).

Failure modes:
- 5.F1 Caps exist but only alert humans who are asleep; caps must enforce.
- 5.F2 Book-level cap absent, so one pathological XL book eats the day's budget in repairs.
- 5.F3 Global kill switch known to work only in theory; first real use loses a day of in-flight generation.
- 5.F4 CI, demos, and developer curiosity riding on the production key.

---

## 6. Provider Strategy

Pricing volatility:
- 6.1 Prices are versioned, effective-dated config; every cost event stores the snapshot used; quarterly repricing review with sensitivity analysis (input +50%? output +50%? cache discount removed?), noting input-heavy stages (moderation) and output-heavy stages (drafting) respond differently because output tokens usually price 3-5x input.
- 6.2 Watch price-structure changes, not just levels: cache write premiums, batch discount terms, long-context surcharge tiers (avoid context sizes that cross a price cliff), per-image and per-request fees, thinking-token billing semantics.

Model deprecation and drift:
- 6.3 Assume 6-18 month model lifetimes; maintain a deprecation calendar; contracts should require >=6 months notice.
- 6.4 Pin snapshot IDs; one book is generated end-to-end on one recipe (mixed-version books are undebuggable); migrations are planned projects with eval runs, budget, and a calendar reserve of 1-2 forced migrations per year.
- 6.5 Silent drift canaries: weekly fixed-input generations per model; alert on output distribution shift even when the version string is unchanged.

Multi-provider:
- 6.6 Per-stage routing table with at least 2 eval-qualified providers for every critical stage; "qualified" means passed the same golden-set bar within margin, including the safety floor; a fallback that fails the safety floor means the pipeline pauses instead of failing over.
- 6.7 Fallback is tested monthly (game day: force-route 5% of traffic); untested fallback is fiction.
- 6.8 Aggregators (unified-billing brokers): faster multi-model access and one invoice vs added margin, opaque rate limits, and an extra data processor; for children's content every hop needs no-training, bounded retention, and a signed DPA, which is a hard gate before any price comparison. Provider data terms (COPPA-adjacent) shrink the eligible list first; price ranks second.

Self-hosting economics:
- 6.9 Honest formula: $/1M tokens = (GPU $/hr / (tokens per hour at achieved batch throughput)) / utilization + amortized ops labor + eval/quality delta cost. Breakeven usually requires sustained utilization >40-60% and a stage tolerant of open-weights quality; batch pipelines suit self-host (no latency SLA); include patching, weights licensing for commercial use, GPU supply risk, and the cost of falling behind frontier quality.
- 6.10 Serverless per-second GPU vs reserved: serverless wins at spiky/low utilization despite cold starts; reserved wins at sustained load; recompute the crossover quarterly.
- 6.11 Hybrid default: buy frontier for planning and final moderation; consider self-host only for drafting and first-pass screening at volume, never as the sole safety gate.

Subscription vs metered accounting:
- 6.12 Flat-rate capacity (seat subscriptions, reserved capacity, promos, free tiers) has zero visible marginal cost, which distorts every lever comparison; convert all capacity to effective $/1M tokens at actual utilization before comparing.
- 6.13 Shadow list-price accounting: meter subsidized usage at list price in a shadow column so unit economics survive the promo ending or the subscription being repriced or capped; track "subsidized token share" of total (know your exposure).
- 6.14 Consumer subscriptions' ToS commonly forbid production automation; routing pipeline load through them is a compliance and continuity risk, not a saving.
- 6.15 Reserved/committed tiers: commit to P25-forecast baseload only; model overage behavior and true-up terms; underutilized commitments are negative savings.
- 6.16 Internal/unmetered research clusters get an internal transfer price for the same reason.

Comparability and contracts:
- 6.17 Tokenizers differ 10-25% for identical text across providers; images and audio bill differently; compare providers on $/published-book and $/1k published words, never on tokens.
- 6.18 Contract asks: deprecation notice, price protection windows, rate-limit and uptime SLAs with credits, no-training and retention clauses, region pinning, capacity reservations at scale.
- 6.19 Concentration metric: % of monthly spend on the single largest provider; >70% triggers a diversification review.

Failure modes:
- 6.F1 Fallback provider silently below the safety bar; an outage becomes a safety incident.
- 6.F2 "Latest" model aliases in prod; provider swaps the pointer and both cost and content change overnight.
- 6.F3 Cross-provider comparisons on per-token price ignoring tokenizer and yield differences.
- 6.F4 A promo-subsidized stage becomes load-bearing; repricing doubles unit cost in one week with no plan.
- 6.F5 Provider chosen on price before data-processing terms; unwindable compliance exposure with children's data.

---

## 7. Scale Projections: 10x and 100x Books per Month

Scaling shape:
- 7.1 Linear-ish with volume: generation tokens, moderation tokens, image spend, storage.
- 7.2 Sublinear: eval and monitoring (fixed cost spread thinner), template amortization (until diversity caps bind), negotiated unit prices (discount tiers).
- 7.3 Superlinear risks: human review (hiring lag and coordination), catalog similarity checking (O(n^2) if naive; needs embedding ANN), incident blast radius, rescreen events (catalog size x per-book cost).

At 10x:
- 7.4 Provider rate limits and quotas become binding before budget does: negotiate tiers, shard keys, schedule batch windows (generate overnight), smooth the queue.
- 7.5 Human review moves from "everyone reads everything" to risk-tiered sampled review with tooling (3.24); reviewer throughput becomes an SLO (e.g., 95% of books reviewed within 3 business days) and hiring pipeline (4-8 week ramp) becomes a standing function.
- 7.6 Template library strain: diversity caps force a standing template-production budget (the catalog-growth loop is now a permanent cost line, not a project).
- 7.7 Blast radius: a bad recipe deploy burns 10x cash before detection; staged rollouts and canary cohorts sized as % of daily volume become mandatory.
- 7.8 Fine-tuning breakeven arrives for the fill stage; commit-tier discounts (10-30%) kick in.
- 7.9 Cost telemetry volume forces pre-aggregation; raw transcripts move to tiered retention.

At 100x:
- 7.10 Human approval is the wall, by policy design (a human approves every book; that is non-negotiable, so the lever is minutes per approval, never approvals). FTE math must be explicit: reviewers needed = books/mo x avg minutes / (reviewer productive minutes/mo, ~6h/day x 21 days). Example: 5,000 books/mo x 20 min = 1,667 hours = ~14 FTE plus QA and management.
- 7.11 Review becomes an operations org: band-specialized reviewers, shift coverage, QA-of-review (5-10% double review), decoy program, calibration cadence, attrition planning, well-being rotation; consider vetted overflow vendors with in-house QA, acknowledging the child-safety quality risk of outsourcing.
- 7.12 Reviewer incentive design: piece-rate pay incentivizes rubber-stamping; pay hourly with throughput bands plus QA scores.
- 7.13 Self-host flips for high-volume stages; dedicated capacity contracts; multi-region active-active for critical stages because a provider outage is now a guardian-facing SLA breach; a buffer inventory of pre-approved books smooths outages (inventory as insurance, costed as such).
- 7.14 Policy-change rescreens are now major projects: incremental screening infrastructure (per-node content hash + policy version) must already exist; retrofitting it at 100x is a rewrite.
- 7.15 Governance: budget owner per stage, unit-cost OKRs, showback/chargeback to product lines, automated invoice reconciliation, audit-grade evidence per book (who approved, what coverage they achieved, minutes) for regulators of children's content.
- 7.16 Fine-tuned model fleet management: retrain cadence tied to base-model deprecations becomes its own budget line.
- 7.17 Demand-side: entitlements and pricing must reflect true unit cost by class or growth manufactures losses at scale.

Questions:
- 7.Q1 At current review minutes per class, at what monthly volume does the review team saturate, and what is the hiring lead time vs growth curve?
- 7.Q2 Which cost lines are superlinear today (test empirically by regressing cost vs volume), and what removes the superlinearity?
- 7.Q3 What volume triggers each commercial step-change (commit tier, fine-tune, self-host, dedicated capacity)? Pre-compute the trigger points.

Measurements:
- 7.M1 Review capacity utilization: 70-85% (higher means queue latency blowups; lower means overstaffing).
- 7.M2 Review queue latency SLO adherence: >95%.
- 7.M3 Seeded-defect catch rate: >95%; inter-rater kappa: >0.75; approval decision-time distribution monitored for too-fast (rubber-stamp) tails.
- 7.M4 Minutes per approval trend: down and to the right while catch rate holds; this pair is the master scale metric.
- 7.M5 Provider concentration and quota headroom: >=2x current daily peak available.

Failure modes:
- 7.F1 Growth plan assumes review scales like software; it scales like staffing.
- 7.F2 Throughput pressure quietly degrades review depth with no catch-rate instrumentation to notice.
- 7.F3 Template library exhaustion at 10x produces a same-y catalog and guardian churn before anyone measures similarity.
- 7.F4 The first catalog-wide rescreen (policy or model change) arrives unbudgeted and stalls publishing for a month.

---

## The 10 Mistakes Teams Most Often Make Here

1. Optimizing per-call price instead of fully-loaded cost per published (and read) book. The fix: every decision is scored on the funnel formula, including yield, repairs, human minutes, and scrap.
2. Ignoring yield when swapping models. A model 5x cheaper per token that drops first-pass yield and adds review minutes costs more; comparisons must be end-to-end, on golden sets plus shadow runs.
3. No attribution. Spend not tagged by book/stage/attempt/recipe means "why was July expensive" is unanswerable; the append-only cost ledger with price snapshots is the non-negotiable foundation.
4. Letting context grow with book size. Whole-story-so-far prompting makes the 118k-word book quadratically expensive; bounded per-node context plus prompt caching keeps cost linear, and cache hit rate must be alarmed.
5. Treating human review as free and elastic. It is the dominant line at scale and the hard bottleneck by policy; without minutes tracking, sampling design, decoys, and hiring math, the model is missing its biggest term.
6. Shipping without failure-spend controls. Retry storms, repair oscillation, a mistyped 30x-price model ID: without per-book caps, burn-rate alarms, idempotency, and tested kill switches with checkpoint/resume, the first alarm is the invoice.
7. Comparing subsidized capacity to metered price. Flat-rate subscriptions, promos, and free tiers look like savings until they are capped, repriced, or ToS-blocked; meter everything at effective and shadow list price.
8. Hardcoding prices and floating model versions. Unpinned "latest" aliases and in-code prices mean providers silently change both your cost and your content; pin snapshots, version price tables, canary for drift, and keep a deprecation calendar.
9. Cost-cutting the safety gate on vibes. Cheaper moderation is adopted only through non-inferiority on gold sets with near-zero severe-miss bounds plus ongoing human sampling; one incident in a children's product erases years of token savings (the E[incident] term belongs in the model).
10. Mishandling amortization and reuse. Templates, evals, and fine-tunes either never charged to books (unit cost fake-low) or amortized over impossible reuse counts (diversity caps bound template use), and catalog rescreens on policy change never budgeted; reusable assets need per-use charges, use caps, and a refresh budget line.
