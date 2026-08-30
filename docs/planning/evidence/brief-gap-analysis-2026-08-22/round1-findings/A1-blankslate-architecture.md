# A1: Blank-Slate Architecture for LLM-Generated Children's CYO Books

Written from first principles, without reading this project's planning documents. All numbers are
back-of-envelope and derived below; where I assert a number I show the arithmetic so a reviewer can
attack the assumption rather than the conclusion.

**The three positions everything else follows from:**

1. **Human review time, not tokens, is the dominant unit cost.** A 118,000-word book read end to end
   by a paid reviewer at an effective 150 words/minute costs about **13 hours, roughly $330 fully
   loaded**. The same book generated well costs about **$6 in inference**. Any design that reasons
   only about token spend is optimising the 2% line item. Everything about the architecture should
   be arranged to reduce *human minutes per approved book* while keeping the approval meaningful.
2. **Structure is provable; prose is not. Prove the structure before you buy a single word of prose.**
   Termination, reachability, ending depth, branching cadence, choice divergence, referential
   integrity and state consistency are all decidable by a program on a graph. If you generate prose
   first and discover a structural defect, you throw away the expensive artefact. Generating and
   *proving* the graph before prose is the largest single cost lever after prompt caching, and it
   eliminates an entire bug class permanently rather than testing for it.
3. **The unit of experience is the path, not the node and not the book.** A child reads one path
   (perhaps 15 nodes and 2,600 words) through a 677-node, 118,000-word artefact. Safety, coherence,
   arc and satisfaction are properties of paths. Node-level checking is necessary and cheap but is
   *not* sufficient: two individually-safe nodes compose into an unsafe path, and two individually
   coherent nodes compose into a contradiction. Almost every team building this checks nodes,
   because nodes are what the generator emits.

---

## 1. Full problem decomposition

I split the problem into 31 sub-problems in seven groups, each labelled **[C] compute it**
(deterministic, a program decides, an LLM must never be in the loop), **[J] judge it** (requires a
model or a human, must be calibrated against humans before it can gate anything), or **[R] open
research** (no valid instrument exists today; you can only proxy it and sample humans).

### Group A: Request understanding and budgeting

| # | Sub-problem | Class | Note |
|---|---|---|---|
| A1 | Parse a free-text family request into a structured brief (protagonist, companion, setting, tone, must-haves) | J | Small, cheap, high leverage. Structured output, schema-constrained. |
| A2 | Assign an age band and derive band constraints (vocabulary, sentence length, node length, branching cadence, permitted themes) | C | Band comes from the child profile, not from the request text. Never infer age from prose. |
| A3 | Screen the *request itself* for adversarial or unsafe intent | J | Requests are user input. A guardian can ask for something inappropriate; a compromised account certainly can. |
| A4 | Assign a hard token/word/node budget and a cost ceiling before any generation | C | The ceiling must be an input to generation, not a metric measured afterwards. |
| A5 | Select the design cell (structure archetype x conflict type x POV x tense x tone x ending family) with per-family exposure cooldown | C | Sampling from a combinatorial space with an exclusion set. This is arithmetic, not judgement, and putting an LLM here is the single most common way variety dies. |

### Group B: Structure

| # | Sub-problem | Class | Note |
|---|---|---|---|
| B1 | Every path terminates | C | Free if the graph is acyclic and depth-layered by construction. Do not make it a test. |
| B2 | Every ending reachable, at qualifying depth, from the root | C | BFS/DFS. |
| B3 | No orphan nodes, no dangling choice targets, referential integrity | C | Must be re-checked after *every* mutation including human edits. |
| B4 | Branching cadence fits the band (nodes between choice points, choices per choice point) | C | |
| B5 | Depth distribution: shortest and longest path lengths within band bounds | C | |
| B6 | Subtree balance: no choice leads to 3 nodes while its sibling leads to 300 | C | Kids notice "the wrong choice ends the book". |
| B7 | Choice divergence: the two branches under a choice must differ materially | C **and** J | The compute-it half (distinct state delta, distinct node sets, low subtree overlap) catches most of it. The judge-it half (are the two options *semantically* different promises to the reader) catches the rest. |
| B8 | Minimal path cover: a set of complete paths that touches every node and every edge at least once | C | This is the validation and review unit. Roughly `#endings` paths for a layered DAG. |
| B9 | State model: a typed world-state vector (inventory, relationships, knowledge, injuries, location, time) with deterministic deltas on edges | C | Design decision, not a generated artefact. |
| B10 | Condition/gate correctness: no gate that can never be satisfied, no gate that is always satisfied | C | Reachability under state, computable by symbolic walk. |

### Group C: Prose

| # | Sub-problem | Class | Note |
|---|---|---|---|
| C1 | Per-node prose that hits the brief, the length target and the register | J | |
| C2 | Reading level per band | C for surface metrics, **R** for actual comprehension | Flesch-Kincaid and friends are word-length and sentence-length formulas. They are trivially Goodharted and they are close to invalid on dialogue-heavy children's fiction. See risk 8. |
| C3 | Vocabulary compliance (band word list, banned lexicon, no unglossed rare words) | C | |
| C4 | Voice consistency across 677 nodes | J | Measurable as a proxy (stylometric distance between nodes and the style bible exemplars); the proxy needs calibration. |
| C5 | Continuity: no reference to an item, fact or relationship not established on this path | **C**, if and only if you commit to B9 | This is the big one teams misclassify. With a typed state ledger, "the lantern is mentioned but was never acquired on this path" is a string-and-set check. Without one it is an intractable judgement problem. Commit to the ledger. |
| C6 | Narrative arc across a path: rising tension, a turn, a resolution | J | Judge on the path cover, not on nodes. |
| C7 | The choice text is tempting, honest about what it offers, and not a trick | J | |
| C8 | Endings are satisfying and proportionate to the path invested | J, partly **R** | See section 4. |
| C9 | Fidelity to the family's request ("a girl and a dragon") | J, cheap and highly reliable | |

### Group D: Safety

| # | Sub-problem | Class | Note |
|---|---|---|---|
| D1 | Content-policy violations at node level (violence, sexual content, self-harm, hate, drugs) | J, near-solved | Classifiers are good at this. |
| D2 | Developmental/emotional appropriateness per band | J, and partly **R** | Distinct from D1 and badly under-specified everywhere. A 5-year-old should not be handed a choice whose wrong branch kills their mother. Abandonment, guilt-assignment, body horror, coercion framing, "you failed" endings, unresolved dread: none of these trip a content classifier. |
| D3 | Safety of the *composition*: a path whose nodes are each fine but which reads as escalating dread or as grooming | J on the path cover | Structurally invisible to node classifiers. |
| D4 | Choice-framing safety: prose is fine, the choice puts the child in an unsafe agency position | J | "Do you tell the grown-up, or keep the secret?" is a different object from the paragraph around it. |
| D5 | PII and real-world identifiability leaking from the request into the book | C then J | The request says "a story about my daughter Maya at Oakridge Elementary". |
| D6 | No instructions, no real-world actionable harm, no URLs, no contact affordances | C | Regex-and-list territory. |

### Group E: Variety

| # | Sub-problem | Class | Note |
|---|---|---|---|
| E1 | Structural distance from this family's prior N books (beat sheet, graph shape, ending family) | C | Hash the beat sheet; compare graph shape. |
| E2 | Lexical/semantic distance from prior books | C | Embeddings, n-gram overlap. Necessary but weakly related to perception. |
| E3 | *Perceived* novelty to a specific child after N books | **R** | No valid automated instrument. Must be measured on children. This is the one that decides whether the business works. |
| E4 | Escaping model attractors (every "girl and dragon" prompt produces the lonely-outcast-befriends-misunderstood-dragon story) | C at the plan level | The fix is a forced sample from an explicit design space, not temperature. |

### Group F: Human loop

| # | Sub-problem | Class | Note |
|---|---|---|---|
| F1 | Constructing an evidence packet a human can act on in minutes | Engineering | The actual product surface for the reviewer. |
| F2 | Deciding what "approved" attests to, and recording it truthfully | Policy | |
| F3 | Detecting reviewer degradation (rubber-stamping, vigilance decrement) | C, via seeded defects | See section 7. |
| F4 | Re-gating after any human edit | C | |

### Group G: Operations

G1 cost accounting per book and per stage **[C]**; G2 reproducibility (pin model, params, seed, full prompt per node) **[C]**; G3 model-version drift detection **[C]** with **[J]** interpretation; G4 latency and speculative pre-generation **[C]**; G5 retry-tail containment **[C]**; G6 field telemetry back into eval **[C]**.

**The three genuinely unsolved ones, stated plainly:** E3 (perceived novelty), D2/C8 tail (emotional
appropriateness and ending satisfaction for children as a measurable quantity), and C2's deep form
(reading level as comprehension for an individual child). Everything else is engineering. A programme
that pretends these three are solved will ship confident dashboards and lose repeat readers anyway.

---

## 2. Architecture

### The pipeline

```json
                        [BUDGET ENVELOPE: words, nodes, tokens, $ ceiling]
                                       |
 (0) INTAKE ------------------------------------------------- LLM small, sync, <2s
     free text -> structured brief; band from profile; request screening; budget assigned
                                       |
 (1) PLAN --------------------------------------------------- LLM top tier, high effort
     design cell sampled deterministically from the combinatorial space (family cooldown applied)
     -> premise, cast sheet, world facts, theme, beat sheet, typed STATE MODEL, ending set
                                       |
 (2) STRUCTURE SYNTHESIS ------------------------------------ deterministic + small LLM
     layered DAG: nodes -> depth layers, choices wired, state deltas on edges, gates, endings placed
                                       |
 (3) STRUCTURAL PROOF --------------------------------------- PURE CODE, no LLM
     B1-B10. Fails here are cheap. NOTHING proceeds until the graph is provably sound.
                                       |
 (4) NODE BRIEFS -------------------------------------------- LLM mid tier, batched
     per node: purpose, beat, entering state, required facts, forbidden facts, target words, tension
                                       |
 (5) ENDINGS FIRST ------------------------------------------ LLM top tier
     endings carry the emotional payload and are the highest-read-per-word nodes. Write them while
     context is freshest and budget is unspent.
                                       |
 (6) PROSE FILL --------------------------------------------- LLM mid tier, CACHED PREFIX, BATCHED
     node-local. prompt = [frozen prefix: style bible|band profile|world|cast|safety] (cached)
                       + [volatile: node brief|entering state|ancestor digest|sibling divergence]
     per-node deterministic checks fire immediately: length, lexicon, state references, name set
                                       |
 (7) PATH ASSEMBLY & CONTINUITY ----------------------------- CODE for continuity, LLM for arc
     walk the minimal path cover; deterministic state-ledger continuity check on every path;
     LLM path judge for arc, coherence, choice honesty, composed safety
                                       |
 (8) SAFETY GATE -------------------------------------------- cheap classifier all nodes,
     band-specific classifiers; choice-framing classifier; path-level classifier on the cover
                                       |
     [any failure] -> targeted REPAIR with a hard retry budget -> RE-ENTER at the earliest
                      invalidated stage (a structural repair re-enters at (3), not at (8))
                                       |
 (9) EVIDENCE PACKET ---------------------------------------- deterministic assembly
     spine (2-4% of words), all endings, all flagged nodes, random audit sample, metric dashboard,
     novelty diff vs this family's last 5 books, explicit coverage statement
                                       |
(10) HUMAN APPROVAL ---------------------------------------- guardian primary; staff on exception
                                       |
(11) PUBLISH -> child reads -> telemetry (completion, abandonment node, re-read, dwell) -> back to
     the variety sampler and the eval loop
```

### Why each split, specifically

**Why plan is separate from structure, and structure separate from prose.** These three have
completely different cost profiles and completely different failure recovery. The plan is a few
thousand output tokens with enormous leverage: spend the best model here. Structure is nearly free
and fully decidable: fail here, loudly, as often as you like. Prose is 90%+ of the tokens: it must
never be regenerated for a reason that an earlier stage could have caught. If you fuse plan and prose
(one long call that writes the whole book) you get: no budget control, no structural proof, no
caching, no parallelism, no per-node repair, and a 157,000-token output that fails as a unit.

**Why node-local prose with a frozen prefix.** Three reasons, in order of importance. (a) Cost: the
frozen prefix is 80%+ of the input and caching it takes prose from ~$0.018/node to ~$0.007/node at
Sonnet tier, a 2.5x swing. (b) Parallelism and batching: node-local calls are independent given the
brief and the entering state, so the whole fill is embarrassingly parallel and batch-eligible, which
is another 2x. (c) Repairability: a failed node is one node, not a book. The cost is the continuity
risk, which is why B9's state ledger is load-bearing and not optional.

**Why endings first.** Endings are 5-10% of nodes but carry most of the perceived quality, and every
completed read hits exactly one. Generating them last means generating them under budget pressure at
the end of a long run. Generating them first also pins the emotional targets that the middle prose
has to build toward, which measurably reduces the "the ending came out of nowhere" failure.

**Why the judge must not be the generator.** If the same model family, same prompt lineage and same
context judges its own output, its errors and its judgement are correlated: the blind spot in
generation is a blind spot in evaluation. Use a different model family where possible, and at minimum
a judge that is blind to the generation rationale, sees only the artefact, and is prompted from an
independently authored rubric. Expect to have to demonstrate this decorrelation empirically (section
6), not assert it.

**Why path-level judging instead of a second node-level pass.** It is *cheaper* (section 3: about
$0.54 per XL book versus $2.50 for a node-level Sonnet pass) and it catches a class of defect node
judging structurally cannot see. This is a rare case where the better check is also the cheaper one,
which usually means teams have not thought about it.

**Why the human is last and reviews an evidence packet.** The human cannot be a bottleneck in the
middle of a pipeline that runs in batch overnight, and cannot be asked to read 118,000 words. Their
job is to make an accountable decision on a structured artefact, with the raw text one click away.

**Where the human actually sits (the important product decision):** the **guardian is the primary
approver of their own family's book**. They are free, they are the legally correct approver for their
own child, and they have the context (they know their child is scared of dogs). Paid trust-and-safety
staff handle only: (a) any book the machine flagged, (b) a 1-3% random audit sample, (c) 100% of any
book that will be shared beyond the requesting family, (d) 100% of a new band or a new design cell's
first N books. This is the only structure I can find in which the unit economics close (section 3).

### Two lanes, not one

- **Now lane:** short books (band 3-8, under ~8,000 words), synchronous or near-sync, target ready in
  under 3 minutes. A child who asks for a story wants a story.
- **Big lane:** long books, batch API, "ready tomorrow morning", framed as an event.
- **Speculative lane:** given a child's profile and history, pre-generate the next 1-2 books at batch
  prices before they are requested. This is the single best latency *and* cost play simultaneously.
  It is only a good idea if the consumption rate is measured: at a 60% consumption rate the effective
  cost multiplier is 1.67x, which still beats paying 2x for synchronous. Measure it; do not assume it.

---

## 3. Cost model

### Conversions and assumptions

- 1 English word ~ 1.33 tokens.
- Prices used (Anthropic first-party, current at time of writing): Opus 5 $5/$25 per MTok in/out;
  Sonnet 5 $3/$15; Haiku 4.5 $1/$5. Cache read ~0.1x input; cache write ~1.25x input. Batch API 50%.
- Reviewer effective rate for careful review of children's prose: **150 words/minute** (raw reading is
  200-250 wpm; reviewing with judgement and flag-checking is slower). Fully loaded cost $25/hour.
- Four reference books:

| Book | Words | Nodes | Words/node | Out tokens/node | Band |
|---|---|---|---|---|---|
| S | 800 | 12 | 67 | 89 | 3-5 |
| M | 6,000 | 60 | 100 | 133 | 6-8 |
| L | 30,000 | 200 | 150 | 200 | 9-12 |
| XL | 118,000 | 677 | 174 | 232 | 16+ |

- Per-node prompt: frozen prefix **P = 4,000 tokens** (style bible, band profile, world bible, cast
  sheet, safety rules, exemplars); volatile suffix **V = 800 tokens** (node brief, entering state,
  ancestor digest, sibling-divergence constraint).

### Per-node prose cost, XL (232 output tokens)

| Configuration | Arithmetic | $/node |
|---|---|---|
| Opus, no cache, sync | (4,800 x 5 + 232 x 25)/1e6 | **0.0298** |
| Sonnet, no cache, sync | (4,800 x 3 + 232 x 15)/1e6 | **0.0179** |
| Sonnet, cached prefix, sync | (4,000 x 0.3 + 800 x 3 + 232 x 15)/1e6 | **0.0071** |
| Sonnet, cached + batch | above x 0.5 | **0.0035** |
| Haiku, cached + batch | (4,000 x 0.1 + 800 x 1 + 232 x 5)/1e6 x 0.5 | **0.0012** |

Note what the cached row exposes: once the prefix is cached, the **volatile suffix becomes the largest
input line item** ($0.0024 of $0.0071). The ancestor digest is the part that grows with depth. Cap it
hard (a fixed-size state ledger plus a 150-token digest, not a growing summary), or your per-node cost
climbs with depth and your deepest nodes, which are the endings, become the most expensive.

### Whole-book cost, four design points

Retry/repair reserve of 1.2x applied to prose in all designs.

**Design A, "the obvious thing":** one Opus call per node, no caching, synchronous, plan on Opus,
two full node-level Opus judging passes.

**Design B, "sensible":** plan Opus, prose Sonnet with cached prefix, synchronous, one node judge pass.

**Design C, "optimised" (my recommendation for L/XL):** plan split (Opus for the plan core, Sonnet for
the 677 briefs), endings on Opus, prose Sonnet cached + batched, Haiku screen on all nodes, Sonnet
judge on the path cover only.

**Design D, "aggressive" (bands 3-8):** as C but Haiku prose, templated/composited cover, lazy cover
upgrade.

XL (118,000 words, 677 nodes):

| Line | A | B | C |
|---|---|---|---|
| Plan (core + 677 briefs) | 1.94 | 1.94 | 0.95 |
| Endings first (40 x Opus) | - | - | 0.54 |
| Prose fill (677 nodes, x1.2) | 24.20 | 5.75 | 2.88 |
| Node safety screen (Haiku, batch) | - | 0.83 | 0.42 |
| Judging | 8.40 (2 x Opus node pass) | 2.50 (1 x Sonnet node pass) | 0.54 (Sonnet path cover, 40 paths) |
| Repair reserve | included | included | 0.72 |
| Cover art (3 candidates) | 0.09 | 0.09 | 0.09 |
| Infra/storage/queue | 0.10 | 0.10 | 0.10 |
| **Machine total** | **~$34.7** | **~$11.2** | **~$6.24** |
| **Human, full read at 150 wpm** | **$328** | **$328** | **$328** |
| **Human, evidence-packet review (12% coverage, 15 min)** | | | ~~**$6.25**~~ **see note** |

> **The evidence-packet review cost is understated, corrected 2026-08-30.** This row and the
> "XL 15-18 min" estimate in section 7 are not consistent with the reading rate the row above them
> uses, and the error is arithmetic rather than a change in the world, so it is named here rather
> than swapped in.
>
> The full-read row prices 118,000 words at 150 wpm for $328, which implies a loaded rate of
> **$25.02/hour**. At that same 150 wpm, the packet's own coverage statement (11,800 words, 10%)
> takes **79 minutes** and costs **$32.78**; the 12% figure in this row is 14,160 words, **94
> minutes**, and **$39.33**. The claimed 15 minutes implies an effective reading rate of about
> **790 wpm**, which is 5.2x the raw rate, and no amount of "the packet is structured" buys that.
> Even granting a generous 2x structured-packet premium the row is roughly **$16 to $20**, not
> $6.25.
>
> That matters because this row is the whole economic case for evidence-packet review over full
> read: at $6.25 the packet is 1.9% of the full read, at $16-20 it is 5% to 6%, and the machine
> total in the same column is $6.24, so the packet stops being free relative to generation. Recompute
> the unit economics before relying on it, or cut the coverage until the time is achievable at a
> defensible rate.
>
> Separately, the **118,000-word XL baseline this column is built on is not a real book.** The
> generated [catalog census](../../../catalog-census.md) puts the largest committed graph at 677
> nodes commissioning **42,233** words, and the most word-heavy at 632 nodes commissioning **49,953**.
> See [A3-blankslate-economics.md](./A3-blankslate-economics.md), whose stale-baseline note carries
> the same correction. Every absolute dollar figure in this XL column is therefore roughly 2.4x too
> large; the ratios between rows survive, the levels do not.

M (6,000 words, 60 nodes), design C then design D:

| Line | C | D |
|---|---|---|
| Plan core + 60 briefs | 0.21 | 0.10 |
| Endings (6) | 0.07 | 0.03 |
| Prose (60 nodes, cached+batch, x1.2) | 0.20 | 0.08 |
| Node screen (Haiku batch) | 0.035 | 0.035 |
| Path judge (6 paths) | 0.04 | 0.04 |
| Cover | 0.09 | 0.01 (composited/lazy) |
| Infra | 0.05 | 0.02 |
| Repair reserve | 0.05 | 0.03 |
| **Machine total** | **$0.72** | **$0.34** |
| Human full read (40 min) | $16.70 | $16.70 |
| Guardian packet review (6 min, unpaid) | $0 | $0 |
| Paid audit at 2% x 8 min | $0.067 | $0.067 |

S (800 words, 12 nodes), design D: plan $0.06, prose $0.02, screen $0.01, judge $0.02, cover $0.01,
infra $0.02 = **$0.14**. Full human read is 5.3 min = $2.22, which is **16x the machine cost**.

### The four things that actually dominate cost

1. **Human minutes.** At every size, a paid full read costs 5x to 50x the machine cost. Elasticity
   1.0 in words. This is the cost model.
2. **Words per book.** Machine cost is roughly linear in words above the ~$0.15 fixed floor; human
   cost is exactly linear. It is also the one variable you fully control at intake. **Meter it.**
3. **Cache hit rate on the frozen prefix.** 0% to 100% is a 2.5x swing on the prose line, and it fails
   *silently*: a timestamp or an unsorted JSON dump in the prefix takes your cache hit rate to zero
   with no error anywhere. Instrument `cache_read_input_tokens` as a first-class SLO.
4. **Number of full-text automated read-throughs.** Each one costs 0.4x to 1.0x the prose stage.
   Budget: at most one cheap full pass (Haiku node screen) plus one path-cover pass. A team that adds
   "one more validation pass" three times has doubled the cost of the book.

Secondary but real: batch adoption (2x), model tier for prose (3-12x), repair rate (a 5% to 30% repair
rate is a 1.25x on total), cover art strategy (dominant for S books only, where it can be 60% of cost).

### Amortisation of reusable assets

- **Skeletons / structure templates.** If a skeleton costs $30 to author and validate (human plus
  compute) and is used 500 times, that is $0.06/book. But **skeleton reuse is exactly what destroys
  perceived variety** (section 5), so the naive amortisation argument points the wrong way. Resolve
  the tension by amortising *components*, not whole skeletons: 200 amortised beat modules, ending
  kits and choice archetypes compose into 10^5+ distinct shapes. Amortise the parts; never reuse the
  whole.
- **Style bibles and band profiles.** Authored once per band, used by every book in the band.
  Effectively free per book, and they are the cached prefix, so they pay twice.
- **World/cast assets reused across a family's series.** Reduces cost and *increases* perceived
  continuity (children like recurring characters) while *decreasing* perceived novelty. Position:
  reuse characters, vary structure. Never the reverse.
- **Cover art.** For S/M books this is the largest single line item. Composite from an amortised art
  library keyed to motif and palette; generate the bespoke AI cover **lazily on first open** or as a
  paid upgrade. If 30% of generated books are never opened (measure this; I expect 20-40%), you save
  30% of your cover spend for free.
- **The cached prefix itself** is per-book, so its lifetime is one generation run. With a 5-minute
  TTL a slow run loses the cache mid-book. Use the longer TTL, or pre-warm, and *verify empirically
  whether batch and caching discounts stack in your provider's implementation.* Do not assume 0.5 x
  0.1 = 0.05; measure it. If they do not stack, design C's prose line is wrong by 2x.

### Subscription unit economics

- Price **$14.99/month** family plan (2 children). Payment fees 3% + $0.30 leaves **$14.24 net**.
- Target 70% gross margin: **COGS budget $4.27/month/family**.
- Platform fixed cost per family (auth, storage, app delivery, support amortised): **$1.00**.
- Book production budget: **$3.27/month/family**.
- Paid audit review at 2% sampling, 8-minute structured audit, $25/hr = $3.33 per sampled book =
  **$0.067 per book produced**.

| Books/month/family | Budget per book | M book at design C ($0.72) | M book at design D ($0.34+$0.07) |
|---|---|---|---|
| 4 | $0.82 | fits | fits |
| 8 | $0.41 | **over budget** | fits ($0.41) |
| 12 | $0.27 | over | **over** |
| 20 | $0.16 | over | over |

**Conclusions I would build on:**

- Paid human full-reading of every book is economically impossible at consumer subscription prices, by
  a factor of 20 to 800 depending on book size. This is not a tuning problem. Either the guardian is
  the approver, or the product is priced at $50+/month, or "approved" means something other than
  "read".
- **Meter in words, not books.** The cost driver is words; the price unit must match it. Give each
  child a monthly word allowance (e.g. 30,000 words at $14.99, which is five M books or one L book).
  An unmetered "unlimited books" promise is a promise that a family with a re-requesting 9-year-old
  can consume 20x the median and destroy the cohort margin.
- **XL books cannot be in the all-you-can-eat tier.** True cost with any human touch is $6 to $330.
  Sell them as a separate SKU, a quarterly credit, or a "big book" event.
- Cost per book is dominated by fixed overhead below ~2,000 words. A "story a day for a 4-year-old"
  product is a *fixed-cost* product; optimise plan-stage tokens and cover art, not prose.

---

## 4. Quality: what it means and how to measure it

"Quality" for a kids' CYO book is not one thing. I decompose it into **nine dimensions**, each with a
declared instrument, a declared validity status, and a declared gate/monitor role. The single most
important discipline here: **a metric may only gate if it has been shown to correlate with human
ratings on a held-out set.** Everything else is monitoring, and must be labelled as such in the code.

| # | Dimension | What it means to a reader | Instrument | Class | Gate or monitor |
|---|---|---|---|---|---|
| Q1 | Structural soundness | No dead ends, no unreachable endings, no dangling choices, no branch that ends in 3 nodes | Graph algorithms on the DAG | C, exact | **Hard gate. Zero tolerance, forever.** |
| Q2 | Continuity | Nothing appears that was not established on *this* path; nothing contradicts an established fact | Deterministic walk over the typed state ledger + entity/name set diff | C, high precision | **Hard gate** on ledger violations; LLM check for the residue |
| Q3 | Reading level | The child can decode and comprehend it | Surface: FK/sentence length/syllables/type-token ratio (C). Deep: comprehension (**R**) | Surface valid-ish, deep unmeasured | Surface = **monitor with band bounds**, never a fine-grained optimisation target |
| Q4 | Voice and register consistency | It sounds like one author, and like an author who writes for this age | Stylometric distance to band exemplars (C proxy) + LLM rubric (J) | Proxy needs calibration | Gate on gross outliers only |
| Q5 | Path-level narrative arc | Tension rises, something turns, it resolves | LLM judge on each covering path, 5-point rubric, calibrated | J | Gate at a calibrated threshold |
| Q6 | Choice quality | Choices are meaningful, distinct, honest, and tempting | Divergence metrics (C) + LLM judge on choice pairs (J) | Hybrid | Gate on divergence; monitor on judge score |
| Q7 | Ending satisfaction | The ending feels earned and proportionate | LLM judge (J) + field completion/re-read data (C) | Weak instrument, **R** at the core | Monitor; field data is the real signal |
| Q8 | Request fidelity | The girl and the dragon are both in it and both matter | LLM judge, structured checklist from the brief | J, reliable | **Hard gate** |
| Q9 | Safety | Section 7 | Classifier ensemble, node + choice + path | J | **Hard gate** |

### What is NOT measurable and must be sampled by humans

Be explicit about this list, because a dashboard that omits it implies the coverage is complete.

1. **Whether the book is any good.** No instrument. Sample: a rolling panel of 30-50 books/month rated
   by trained adult raters on the 9-dimension rubric, plus a smaller panel of children.
2. **Whether a child enjoys it.** Proxy with field telemetry (completion, re-read, re-request, dwell),
   validate the proxy against direct child feedback at least quarterly.
3. **Emotional appropriateness at the band boundary.** A book that is fine for a robust 7-year-old and
   frightening for a sensitive one. Only humans, and only with a per-child signal.
4. **Perceived novelty** (section 5). No instrument exists.
5. **"LLM smell"**: the flat, list-like, over-explained, adverb-heavy register that adults detect
   instantly and children may not. Adult raters catch it; automated stylometry catches only some.

### Instrument validation (the part usually skipped)

Every automated metric must go through this before it is allowed to gate:

1. Build a **gold set** of 200 books stratified across band x structure archetype x theme, including
   deliberately weak and deliberately good examples.
2. Have **3 trained raters** score each on the rubric. Compute **Krippendorff's alpha per dimension**.
   Require **alpha >= 0.67** before the ratings are treated as ground truth. If raters cannot agree on
   a dimension, the dimension is ill-defined: fix the rubric, not the model. (I expect Q1/Q2/Q8 to
   pass easily, Q4/Q6 to pass with work, and Q5/Q7 to be the ones that fail and need re-specification.)
3. For each automated metric, report **Spearman rho against the human score on a held-out half**.
   Promote to gate only at **rho >= 0.5** with a documented failure mode. Below that: monitor only,
   and label it in the code as non-gating so nobody quietly promotes it later.
4. **Re-run this whenever the model, prompt or rubric changes.** A judge validated against Sonnet-N
   output is not validated against Sonnet-N+1 output.
5. Track **judge score variance**. A judge whose scores collapse toward a single value (everything
   gets 4.3/5) has stopped carrying information regardless of its mean.

### The defect corpus (the other part usually skipped)

A gate that passes everything is indistinguishable from a working gate when the input is clean. So
build a **negative suite**: 200+ books with hand-injected defects, at least 15 per class, covering:
dangling choice target, unreachable ending, ending below qualifying depth, cycle introduced, continuity
break (item used before acquired), contradicted fact, name drift, off-band vocabulary, sentence-length
blowout, two choices with identical outcome, a subtree stub, an unearned ending, a soft-safety
violation per band-harm category, a request-fidelity miss, PII leak. **Requirement: >= 95% detection
per class, with the specific defect localised, not just "book failed".** This suite is regression-run
on every validator change and every model change. Most teams never build it, and consequently have no
evidence their gate works.

---

## 5. The variety / repeat-reader problem

The framing that matters: a family will consume 50 to 300 books over a few years. The question is not
"is book 2 different from book 1" but "**does book 40 feel like a new book to a child who has read 39**".

### The mechanisms, ranked by predicted perceptual effect

**Tier 1: works, large effect.** These change what the child remembers about the story.

1. **Story shape / structural archetype.** Quest, mystery, heist, rescue, escape, contest, mystery-box,
   slice-of-life-with-a-problem, trickster, journey-home, siege, transformation. Plot shape is the
   thing children actually remember and recount. Changing it is the highest-yield variety lever by a
   wide margin.
2. **Problem type and stakes.** Is the obstacle a person, a place, a rule, a lack, a secret, a
   misunderstanding, time, or the protagonist themselves? Kids feel the difference between "beat the
   villain" and "figure out what the note means" even when the setting is identical.
3. **The agency model: what the choices are *about*.** Choices about *where to go*, versus *who to
   trust*, versus *what to say*, versus *what to keep or give up*, versus *what to believe*. This is
   the CYO-specific variety axis and it is almost always neglected because it is a property of the
   choice design, not the prose.
4. **Ending taxonomy.** Triumphant, bittersweet, transformative, homecoming, open, comic reversal,
   quiet. A catalogue where 80% of endings are "and they were friends after all" will feel identical
   at book 10 no matter how the prose varies.
5. **Narrative voice, POV and tense.** Second-person present (the CYO default), first-person past,
   third-limited, an unreliable narrator, an in-world framing device (a logbook, a letter, a talking
   map). Very cheap, and immediately perceptible.

**Tier 2: works, moderate effect.**

6. Tone register: funny, spooky-safe, cosy, adventurous, wistful.
7. Cast configuration: solo, duo, ensemble, with-an-adult, with-an-antagonist-who-becomes-an-ally.
8. Structural texture: node length rhythm, choice cadence, whether some branches converge.
9. Recurring characters *across* books with genuinely different plots (raises satisfaction and does not
   damage novelty as long as tier 1 varies).

**Tier 3: perceptual no-ops. Do not spend engineering effort here and do not put them on a dashboard.**

10. **Renaming characters and places.** Zero effect. A child who read "Mira and the dragon Ember" and
    then "Nia and the dragon Cinder" has read the same book.
11. **Setting reskin over an identical beat sheet.** Space station instead of forest, same story.
    Detectable by adults instantly and by kids within a few books. This is the most common failure
    because it is the easiest thing to vary and it *scores well on lexical diversity metrics*.
12. **Sampling temperature, top-p, "be more creative" instructions.** These change wording, not shape.
13. **Vocabulary diversification.** Changes the embedding, not the experience.
14. **Paraphrase-level rewriting for "freshness".** Pure cost, no effect.
15. **Raising a structural entropy metric that no reader perceives.** If you can raise the metric
    without a human noticing anything, you have built a Goodhart machine.

### The two failure modes that will actually bite

**(a) Model attractors.** Ask any frontier LLM for "a story about a girl and a dragon" 50 times and
you will get the lonely-misunderstood-outcast-befriends-the-feared-creature story approximately 50
times, in 50 different vocabularies. This is not fixed by temperature, by "be original", or by
few-shot examples (few-shot narrows rather than widens). It is fixed **at the plan stage, by
construction**: define an explicit combinatorial design space (archetype x problem type x agency model
x ending family x voice x tone = e.g. 12 x 8 x 5 x 7 x 5 x 5 = 84,000 cells), sample a cell
*deterministically in code* with a per-family exclusion set, and pass the cell to the model as a hard
constraint it must satisfy. The LLM's job is to make the cell good, not to choose it.

**(b) Finite skeleton catalogue.** If you have 40 skeletons and a family reads 100 books, they see
each shape 2.5 times, and shape is the most perceptible thing. Any fixed catalogue is a countdown to
a plateau. Mitigations, in order of preference: compositional skeletons assembled from amortised beat
modules at request time; procedural mutation of catalogue skeletons with a validated novelty floor;
per-family exposure tracking with a cooldown of at least 20 books per archetype. **Instrument the
plateau directly**: for each family, compute the beat-sheet distance from book N to its nearest prior
book, and alarm when the rolling median stops falling.

### How to know any of this works

You cannot validate perceived novelty with cosine distance. The only valid design:

- Give a panel of children 8-12 books over several weeks under two arms (compositional design-space
  sampling vs. catalogue reuse). Primary endpoint declared in advance: **the child's rating of "have
  you read a story like this before?" on book 8**, plus **completion rate of book 8**.
- Secondary: parent's independent "does this feel like a new book" rating. Parents notice repetition
  far sooner than children, and parents cancel subscriptions.
- Then, and only then, find which cheap automated metric predicts that human judgement, and use *that*
  metric as the production monitor. Not before.

---

## 6. Testing and evaluation strategy

### Five layers, each answering a different question

**Layer 1: property tests on the structural core (does the code do what it claims).** Generate random
graphs and random mutations with Hypothesis-style property testing; assert the invariants
(termination, reachability, ending depth, referential integrity, state consistency, path-cover
completeness) hold or are correctly reported as violated. This layer should have close to exhaustive
coverage because it is the only fully decidable part of the system, and it is where a bug reaches a
child silently.

**Layer 2: the defect corpus (does the gate catch what it claims).** Section 4. >=95% detection per
defect class, with localisation. Run on every validator or model change. Report per-class recall, not
an aggregate.

**Layer 3: golden-set evaluation with instrument validation (do the metrics mean anything).**
Section 4. Krippendorff alpha for the rubric, Spearman rho for each metric, promotion rules, re-run on
every model change. **Also validate the judge against itself**: run the judge twice on the same book at
temperature 0 and at temperature default and report score stability; a judge with a test-retest
correlation below 0.8 cannot support a gate threshold.

**Layer 4: canary regeneration (has the world moved under us).** Keep 25 frozen requests. Regenerate
them weekly under pinned prompts and pinned model IDs, and diff the full metric vector. Any provider
change, any prompt change, any library change shows here first. This is the only defence against the
"our quality dropped three weeks ago and nobody knows why" failure, which is inevitable in a system
whose core dependency ships new behaviour behind a stable name.

**Layer 5: field experiments (does it work on children).** Randomised, pre-registered, with declared
primary endpoints. The field metrics that matter, in priority order:

1. **Completion rate**: did the child reach an ending. The single best quality signal you will ever
   have.
2. **Abandonment-depth histogram**: at which node depth do children stop. A spike at depth 2-3 means
   the opening fails. A spike just before endings means the middle drags. This histogram is more
   informative than any offline metric and is nearly free to collect.
3. **Re-request rate and inter-request interval.** The business metric.
4. **Re-read rate** and **branch-exploration rate** (does the child go back and take the other path):
   the CYO-specific engagement signal.
5. **Guardian rejection rate and guardian edit rate**: a direct, free, continuous human evaluation of
   your output, delivered by people who care. Instrument it as a first-class metric from day one.
6. Choice dwell time: long dwell = a genuinely hard choice (good) or a confusing one (bad). Requires
   disambiguation, so treat as a monitor.

### What I would pre-register

For every experiment, before any data is collected, write down: the hypothesis in one sentence; the
**single** primary endpoint; the arms and the randomisation unit (**family, not book, and not child**,
because siblings talk and books-within-family are correlated); the sample size from a power
calculation with a stated minimum detectable effect; the analysis (test, covariates, exclusions); the
stopping rule; and what result would make you abandon the approach.

The three experiments I would pre-register first:

1. **Variety** (section 5): compositional sampling vs. catalogue reuse, primary endpoint = child's
   "have you read a story like this before?" on book 8. MDE 0.5 points on a 5-point scale.
2. **Model tier for prose**: Sonnet vs. Haiku at each band, primary endpoint = completion rate. If
   Haiku is non-inferior at bands 3-8 (my prediction: it is, at those bands, given a strong plan and
   brief), that is a 3x cost reduction on the biggest line item and it decides the pricing tier.
3. **Review depth**: full read vs. evidence-packet review, primary endpoint = **seeded-defect catch
   rate**, secondary = reviewer minutes/book. This experiment determines whether the entire business
   model is viable and should be run in month one, on synthetic books, before there are customers.

### The evaluation failure to guard against explicitly

**Eval theatre**: 40 metrics, a beautiful dashboard, and no demonstrated relationship between any of
them and whether a child finishes a book. Test for it directly: once you have 3 months of field data,
regress 30-day child retention on your offline quality score. If the relationship is not significant,
your entire eval stack is decorative and you should delete most of it and rebuild around completion
rate. Schedule this analysis in advance so it cannot be quietly skipped.

---

## 7. Safety and the human in the loop

### Three distinct safety problems, routinely conflated

**S1. Content policy.** Violence, sexual content, self-harm, hate, substances, profanity. Classifiers
handle this well. It is the least of your problems and it is the one that gets all the attention
because it is the one with off-the-shelf tooling.

**S2. Developmental and emotional appropriateness, per band.** This is where the first parent
complaint comes from, and it will not have tripped a single content classifier. The hazard catalogue
that needs to be written explicitly, with worked examples per band:

- Guilt assignment: a choice whose "wrong" branch causes harm to a loved one, framed as the child's
  fault.
- Abandonment and caregiver loss, especially unresolved.
- Body horror, transformation without consent, being trapped or unable to move or speak.
- Coercion framing, secrets from trusted adults, "don't tell anyone" as a positive story beat.
- Unresolved dread: an ending that leaves a threat alive and unaddressed.
- "You failed" endings that terminate the child's agency punitively.
- Death handled without scaffolding at bands where it should not appear at all.
- Realistic peril mapped onto the child's actual life (school, home, a car, a pool).

Off-the-shelf classifiers are trained on adult harm taxonomies and will not flag most of these.
**Build a band-specific classifier per band, with band-specific thresholds, not one global one.** The
rules for a 4-year-old and a 15-year-old are not the same rules at different strictness; they are
different rules.

**S3. Composition and framing, the CYO-specific hazard.** Safety is a property of paths and of
choices, not of nodes. Two safe nodes compose into an unsafe sequence. A safe paragraph with an unsafe
choice attached is an unsafe node. And the sheer combinatorics mean that a child can walk a path no
human and no judge has ever looked at. This is the structural safety problem of the medium and it is
the one I would expect a team inside the problem to under-weight, because the generator emits nodes,
the storage schema stores nodes, the review UI shows nodes, and so the checking is done on nodes.

**Countermeasure**: define coverage explicitly and enforce it. Every published node must be covered by
at least one path-level judgement. Every choice pair must be covered by a choice-framing check. Track
and publish the metric **"fraction of reachable nodes never seen in any path-level evaluation"**;
require it to be zero at publish time. If you cannot get it to zero, you have not shipped a safe book;
you have shipped a book that was safe on the paths you looked at.

### What the human actually reviews

Reading 118,000 words is not on the table (13 hours, $330). The honest design is a **coverage
contract**: the evidence packet states what was read and what was machine-attested, the human signs
that specific statement, and the record stores it.

Evidence packet contents, in the order the reviewer sees them:

1. **The spine**: the highest-probability path plus a 200-word synopsis; roughly 2-4% of total words.
2. **All endings, in full.** They are 5-10% of nodes and carry most of the risk and most of the payoff.
3. **All flagged nodes, in full**, with the flag reason shown *after* the reviewer's own reaction is
   recorded, not before (anchoring; see below).
4. **A random audit sample** of 5% of unflagged nodes, chosen with a seed recorded in the packet.
5. **The metric dashboard** with structural proofs (pass/fail, with the specific property named).
6. **A novelty diff** against this family's last 5 books: which design cell, which archetype, which
   endings, and the beat-sheet distance.
7. **A coverage statement**: "you will read approximately 11,800 of 118,000 words (10%), covering 100%
   of endings, 100% of flagged nodes, and a 5% random sample of the rest."

Estimated review times: ~~**S 2 min, M 6 min, L 10 min, XL 15-18 min.**~~ The reviewer's effective rate is
higher than raw reading because most of the packet is structured.

*Corrected 2026-08-30: the XL figure is not achievable at the reading rate this report prices
elsewhere. The coverage statement immediately above commits the reviewer to 11,800 words, which is
**79 minutes at the 150 wpm** used in section 6's cost table, not 15-18. A structured packet does
buy some premium over raw prose, but 15 minutes implies ~790 wpm, a 5.2x premium, which is not
credible. Treat the whole S/M/L/XL ladder as unvalidated: it was never measured against a real
packet, and the XL rung is the one the economics depend on. The smaller rungs are the same shape
(M's 6,000-word book is 40 minutes of raw reading), so the understatement is not confined to XL.*

### Who the human is

- **Guardian: primary approver for their own family's book.** Correct in law, correct in product
  (they know their child), and free. This is what makes the economics close.
- **Paid trust-and-safety reviewer** on: every machine-flagged book; a 1-3% random audit; 100% of any
  book shared beyond the requesting family; 100% of the first N books in any new band, new design cell
  or new model version. This is the ratchet: whenever anything changes, the sampling rate goes to 100%
  and decays back down as evidence accumulates.
- **Never**: an unbounded queue of paid reviewers reading everything. That is a $330-per-XL-book
  business.

### The failure modes of human review, and the countermeasures

1. **Rubber-stamping.** The base rate of real problems will be 1-3%. A reviewer's rational prior
   becomes "approve", and after 200 clean books their expected value of careful reading approaches
   zero. **Countermeasure: seeded defects.** Inject a known-bad book into the review queue at ~5%
   rate, with a defect calibrated to the class you care about. Measure per-reviewer catch rate.
   Below 80%, that reviewer is not reviewing. This is the only real instrument for review quality and
   almost nobody builds it. It also applies to guardians, in a gentler form: seed a mild,
   clearly-labelled-after-the-fact issue occasionally and measure whether guardians catch it, so you
   know whether guardian approval is a real control or a click.
2. **Vigilance decrement.** Sustained-attention performance degrades measurably after 20-30 minutes.
   Cap paid review sessions; interleave book sizes; do not queue 12 XL books to one reviewer.
3. **Anchoring on the machine verdict.** If the packet says "safety: PASS" at the top, the reviewer
   finds nothing. Show the human the content first, capture their judgement, *then* reveal the machine
   verdict. For the audit sample specifically, run **blind**.
4. **Non-independence of the two checks.** If the human's attention is directed only where the machine
   flagged, the human adds nothing on the machine's blind spots, which is the entire point of having
   a human. The random unflagged sample exists precisely to measure the machine's blind spot; protect
   it and report on it separately.
5. **Approval fatigue on the guardian side.** Books pile up unapproved and the child never gets a
   story. Leading indicator: median request-to-approved lag, and the fraction of books unapproved at
   72 hours. If that fraction exceeds ~20%, the review burden is too high and the packet must shrink
   (or the product is now "the app that makes me do homework").
6. **Edits invalidate attestations.** Any human edit to a node voids every machine claim about that
   node and about every path through it. **All edits re-enter the gate at the earliest invalidated
   stage.** A guardian who fixes a typo should not silently bypass the safety classifier; a guardian
   who rewrites a paragraph definitely should not.
7. **Semantic drift of "approved".** Record what was attested, not "approved": the coverage statement,
   the seed, the packet version, the model versions, the reviewer identity, the time spent. Both
   product honesty and any future regulatory conversation depend on that record existing.

### Scaling arithmetic

At 10,000 families x 8 books/month = 80,000 books/month. At a 3% flag rate plus a 2% audit = 4,000
paid reviews/month. At 8 minutes each = 533 hours = **3.3 FTE**. That is affordable. At a 15% flag
rate it is ~~16 FTE~~ **11.3 FTE** and the margin is gone.

*Corrected 2026-08-30, wrong when written: 15% flag plus the same 2% audit is 17% of 80,000 =*
*13,600 reviews, 1,813 hours, and 11.3 FTE at the 160 hours per FTE-month this paragraph's own 3.3*
*already uses. The 16 came from scaling 3.3 by 15/3, which treats the 2% audit as if it scaled with*
*the flag rate; it does not, it is a constant. The conclusion is unchanged in direction (the flag*
*rate is the business-critical metric) but the slope is 3.4x from 5% to 17%, not 5x, so a flag-rate*
*budget set from the 16 figure is set against a number 41% too high.* **The flag rate is therefore a business-critical metric, not
a quality metric**, and reducing false positives in the safety gate has direct P&L impact. Track
precision of the flag, not just recall, and make the flag-rate budget explicit (I would set 5% as the
alarm threshold).

---

## 8. Top 15 risks, ranked, with leading indicators

Ranked by expected damage x probability. "Leading indicator" means something you can watch *before*
the damage, not the damage itself.

| # | Risk | Why it kills or degrades | Leading indicator (watch from week 1) |
|---|---|---|---|
| 1 | **Human review cost exceeds the entire subscription margin** | 5x-50x the machine cost at every book size; no amount of token optimisation touches it | Median reviewer minutes/book x books/family/month x loaded rate, plotted against ARPU x target margin, weekly. Also: fraction of books requiring paid review. |
| 2 | **Perceived-variety plateau: books converge to a small set of felt shapes; repeat readers churn around book 10-20** | This is the product thesis. If book 40 feels like book 4, there is no subscription | Per-family beat-sheet distance from book N to nearest prior book: alarm when the rolling median stops falling. Completion rate as a function of book index within family: alarm on any downward slope. |
| 3 | **Rubber-stamping: human approval becomes a click** | The safety control silently stops existing while the compliance story stays intact | Seeded-defect catch rate per reviewer and per guardian cohort. Time-per-book distribution collapsing to a spike at the UI minimum. Approval rate above 99%. |
| 4 | **A safety incident on a path nobody ever read** | Combinatorial coverage gap; the single most likely route to a real incident | Fraction of reachable nodes not covered by any path-level evaluation (must be 0 at publish). Fraction of *child-reached* nodes with zero prior human or judge coverage. |
| 5 | **LLM judges are uncalibrated and the gates pass junk** | Every quality claim in the system rests on them | Judge-vs-human Spearman rho on the rolling gold set (alarm below 0.5). Judge score variance collapse. Judge test-retest correlation below 0.8. |
| 6 | **Model-version drift silently shifts quality and safety** | Your baseline is tied to a model that will change or be retired; nothing errors | Weekly canary regeneration of 25 frozen requests, full metric-vector diff. Provider deprecation notices. Budget 3 weeks of eval re-validation per model migration and put it in the plan. |
| 7 | **Cost blowup from silent cache invalidation or an added validation pass** | 2.5x to 5x cost with no error anywhere; discovered on the invoice | `cache_read_input_tokens / total_input_tokens` per run. Cost per 1,000 published words, per stage, per book size, tracked daily. Count of full-text LLM passes per book as a hard-coded budget with a build-time assertion. |
| 8 | **Reading level is Goodharted** | The model writes short choppy sentences with easy words that are still conceptually inaccessible; FK says pass, the child cannot follow it | FK-on-target rate high while human "too hard" rate stays high. Early abandonment (depth 1-3) concentrated in a band. Divergence between surface metric and rater comprehension judgement. |
| 9 | **Structural repair reintroduces structural defects** | A repair that prunes a node leaves a dangling choice; a published book with a dead end is an unrecoverable trust event | Post-repair validator failure rate. Any structural defect found in a *published* book (this number must be exactly zero, ever; treat one occurrence as a Sev1). Whether the repair path re-runs the full validator or a subset. |
| 10 | **Latency kills the moment** | A 5-year-old asking for a story will not wait 20 minutes, and the parent will not re-ask | p50/p95 request-to-ready by band. Fraction of generated books never opened. Request abandonment during the wait. |
| 11 | **The retry tail blows the cost ceiling on a small fraction of books** | Unbounded regeneration is the classic LLM-pipeline cost bug; the mean looks fine and p99 is 40x | Cost distribution p99/p50 ratio per book size. Count of books exceeding their assigned budget cap. Retry counts per stage. |
| 12 | **Guardian approval friction: books pile up unapproved** | The child never gets the story; the parent experiences the product as chores | Median request-to-approved lag; fraction unapproved at 72 hours; fraction of families with zero approvals in 14 days. |
| 13 | **Children's-privacy and data exposure** | Request text contains real names, schools, family details; generated books contain them; regulatory exposure and a trust event | PII detection rate in request text; consent completion rate; retention/deletion audit pass; whether request text is ever included in prompts sent to third parties without a data agreement covering children's data. |
| 14 | **Provider dependency**: price change, rate limits, capacity, or a policy change on children's content | Your entire COGS is one vendor's price list; a 2x price move or a ToS change is existential | Single-provider share of spend; 429 rate and headroom vs. peak; contractual notice period; whether a second provider has ever generated a book that passed the gate (run this quarterly, not when you need it). |
| 15 | **Eval theatre: many metrics, none predictive of retention** | You optimise confidently in the wrong direction for a year | Pre-scheduled regression of 30-day child retention on the offline quality score at month 3. Number of gating metrics with a demonstrated rho >= 0.5 (if that number is small, say so out loud). |

Three near-misses that did not make the list but would on a longer one: **cover art cost dominating
small books** (fixable, and lucrative to fix); **sibling contamination** in experiments randomised at
the child rather than the family level; and **the "choice illusion" complaint** (two choices leading
to the same paragraph), which is a compute-it check that teams often route to an LLM judge and
therefore catch inconsistently.

---

## Checklist: what a complete framework must contain

Each item is phrased so a reviewer can answer yes or no by looking at the system.

1. Every book has a machine-checkable proof, run before any prose is generated, that the story graph is acyclic (or has a proven monotone progress measure) so that termination is structural rather than tested.
2. Every book has a machine-checkable proof that every ending is reachable from the root, at or above the band's qualifying depth.
3. Every book has a machine-checkable proof of referential integrity: no dangling choice target, no orphan node, no node unreachable from the root.
4. The structural validator is re-run in full after every mutation, repair, or human edit, and this is enforced in code rather than by convention.
5. Branching cadence, choices-per-node, and depth distribution are checked against explicit per-band numeric bounds that are stored as data, not embedded in prompts.
6. Subtree balance is checked, so no choice leads to a branch an order of magnitude shorter than its sibling.
7. A typed world-state model (inventory, relationships, knowledge, location, time, injuries) exists per book, with deterministic state deltas attached to edges.
8. A deterministic continuity checker walks each covering path and flags any reference to an entity, item, or fact not established on that path, and any contradiction of an established fact.
9. Choice divergence is checked deterministically: each choice at a choice point must produce a distinct state delta or a materially disjoint subtree.
10. A minimal path cover is computed for every book, such that every node and every edge lies on at least one complete covering path, and this cover is the unit for path-level evaluation.
11. The metric "fraction of reachable nodes not covered by any path-level evaluation" is computed and is zero at publish time.
12. Structure is generated and proven before any prose tokens are purchased, and the pipeline physically cannot reach the prose stage with an unproven graph.
13. Endings are generated before mid-story prose and at a higher model tier than mid-story prose.
14. Per-node prose prompts are split into a frozen cacheable prefix and a bounded volatile suffix, and the volatile suffix has a hard token cap that does not grow with node depth.
15. Prompt-cache effectiveness is instrumented as an SLO (cache-read tokens as a fraction of input tokens) with an alarm, not inferred from the invoice.
16. Whether batch and cache discounts stack on the chosen provider has been measured empirically and the cost model cites the measurement, not an assumption.
17. Every book is assigned a hard word, node, token and dollar budget at intake, and generation aborts rather than exceeding it.
18. Retry and repair budgets are bounded per stage with a defined give-up behaviour, and the p99/p50 cost ratio per book size is tracked.
19. Cost is accounted per stage per book and reported as cost per 1,000 published words, broken down by band.
20. The number of full-text automated read-throughs per book is a declared constant with a build-time or runtime assertion preventing silent growth.
21. The product is metered in words (or an equivalent unit proportional to cost), not in an unbounded book count.
22. Books at the top of the size range (tens of thousands of words and up) are priced or rationed separately from the base subscription tier.
23. Cover art generation is amortised or deferred (composited from a library, or generated lazily on first open), with the fraction of never-opened books measured.
24. A per-book design cell is sampled deterministically in code from an explicit combinatorial design space (archetype x problem type x agency model x ending family x voice x tone), and passed to the model as a constraint rather than chosen by the model.
25. The design space has at least 10^4 cells and its size is documented.
26. Per-family exposure to archetypes, ending families and design cells is tracked, with an enforced cooldown of at least 20 books per archetype.
27. Story structure is composed from amortised components at request time rather than drawn from a fixed catalogue of whole skeletons; if a catalogue exists, its per-family reuse interval is measured and alarmed.
28. Beat-sheet distance from book N to the family's nearest prior book is computed and monitored for a plateau.
29. No variety mechanism is credited in planning or dashboards without evidence it is perceptible to a reader (name changes, setting reskins, temperature and vocabulary diversity are explicitly excluded).
30. Perceived novelty has been measured at least once with actual children over a sequence of 8 or more books, with a pre-registered primary endpoint.
31. Reading level is checked against band bounds as a monitor, and is explicitly not used as a fine-grained optimisation target for generation.
32. Vocabulary compliance against a per-band word list and a banned lexicon is a deterministic check.
33. Request fidelity (the requested elements are present and material) is a hard gate with a structured checklist derived from the parsed brief.
34. A safety taxonomy exists that is separate from generic content policy and enumerates developmental and emotional harms (guilt assignment, abandonment, coercion framing, unresolved dread, punitive failure endings, body horror) with worked examples per band.
35. Safety classification is band-specific: different rules per band, not one rule at different thresholds.
36. Choice framing is safety-checked as its own object, separately from the prose of the node containing it.
37. Path-level (composed) safety is checked on the full path cover, not only node by node.
38. The free-text request itself is screened for adversarial or inappropriate intent before generation.
39. PII in the request and in generated prose is detected and handled, with a documented policy for real names, schools and locations.
40. Every automated quality metric is labelled in code as either gating or monitoring, and the gating set is closed.
41. A gold set of at least 150-200 books, stratified across band, archetype and theme, exists and is rated by at least three trained human raters.
42. Inter-rater reliability (Krippendorff's alpha or equivalent) is computed per rubric dimension, and a dimension with alpha below 0.67 is re-specified rather than used.
43. Every gating metric has a documented Spearman correlation against human ratings on a held-out set, at or above a declared threshold.
44. Judge test-retest stability is measured, and a judge below the declared stability threshold cannot support a gate.
45. Judge score variance is monitored for collapse.
46. The judging model or prompt lineage is deliberately decorrelated from the generating model, and the decorrelation is demonstrated empirically rather than asserted.
47. A defect corpus exists with at least 15 hand-injected examples per defect class, spanning structural, continuity, level, choice, ending, safety and fidelity defects.
48. Defect-corpus detection recall is reported per class (target 95%+) with the defect localised, and is re-run on every validator or model change.
49. A weekly canary regeneration of a frozen request set runs, with a full metric-vector diff, to detect provider or prompt drift.
50. Model IDs, prompt versions, sampling parameters and seeds are pinned and recorded per node, so any book can be reproduced and any regression bisected.
51. Field telemetry captures completion rate, abandonment depth histogram, re-read rate, branch-exploration rate, and inter-request interval.
52. Guardian rejection rate and guardian edit rate are captured and treated as first-class quality metrics.
53. A pre-scheduled analysis regresses child retention on the offline quality score, so eval theatre is detected rather than assumed away.
54. Experiments are randomised at the family level, pre-registered with a single primary endpoint, a power calculation, and a stopping rule.
55. The human reviewer is shown a structured evidence packet (spine, all endings, all flagged nodes, a seeded random sample, metric dashboard, novelty diff) rather than raw full text.
56. The evidence packet contains an explicit coverage statement of what fraction of the book the reviewer will actually read, and the approval record stores that statement.
57. Review time per book by size is measured, and target review times (single-digit minutes for typical books) are treated as a hard product constraint.
58. The machine verdict is revealed after the reviewer's own judgement is recorded, and the random audit sample is reviewed blind.
59. Seeded known-bad books are injected into the review queue at a measured rate, and per-reviewer catch rate is tracked with a threshold below which the reviewer is retrained or removed.
60. The guardian is the primary approver for their own family's book, and paid review is restricted to flagged books, an audit sample, shared books, and the first N books after any material change.
61. The paid-review flag rate has a declared budget with an alarm threshold, because it is a P&L variable, and flag precision is tracked alongside recall.
62. Any human edit re-enters the validation and safety gate at the earliest invalidated stage; no edit path can bypass the gate.
63. The approval record stores what was attested (coverage, seed, packet version, model versions, reviewer, elapsed time), not merely that approval occurred.
64. Median request-to-approved lag and the fraction of books unapproved after 72 hours are monitored as approval-fatigue indicators.
65. Latency is measured as p50/p95 request-to-ready per band, with separate fast and batch lanes, and the fraction of generated books never opened is tracked.
66. If speculative pre-generation is used, its consumption rate is measured and the effective cost multiplier is reported.
67. A second inference provider has produced at least one book that passed the full gate, verified on a recurring schedule, so provider dependency is a tested fallback rather than a plan.
68. The cost model is maintained as a live artefact per band, with actuals compared against the model monthly, and the human-labour line is included in it.
