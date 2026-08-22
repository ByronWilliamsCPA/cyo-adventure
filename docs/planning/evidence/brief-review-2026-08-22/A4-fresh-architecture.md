# A4 fresh-eyes: system architecture (goal-only, no brief access)

# Architecture Review: LLM Book Factory for a Children's CYOA Catalog

Scope assumed from the brief: branching story graphs with choices and multiple endings; age bands 3-5 through 16+; sizes from ~800 words to ~600+ nodes / ~118,000 words; mandatory human approval per book; LLM generation; many books at low, predictable unit cost; perceived variety across repeated family requests.

---

## 0. Framing and binding constraints

1. You are building a factory plus an evidence trail, not individual books. Every book ships as two artifacts: the book (graph + prose + metadata) and the evidence bundle (what was checked, by what, at what version, and who approved).
2. The scarce resource is human reviewer minutes, not tokens. A 118k-word book is ~8-10 hours of naive reading; token cost for the same book is a few dollars. Optimize reviewer-minutes-per-approved-word first; token cost second.
3. "Predictable unit cost" is a tail-control problem: the mean is set by tokens, the variance by retries and review loops. Architecture must bound retries and localize rework.
4. "Not re-skinned" is a measurement problem before it is a generation problem: you need a sameness metric (structural + surface) or you cannot manage the tradeoff between reuse (cost) and variety (perception).
5. Safety is asymmetric: false negatives (unsafe content reaching a child) are catastrophic; false positives (over-rejection) are a cost line. Gate design should be recall-first with human adjudication absorbing precision loss.
6. Nothing a child sees may be generated at read time without having passed the full gate chain; this single invariant shapes personalization, editing, and republication design.

---

## 1. Problem decomposition

### 1.1 Deterministic algorithms should own (constraint satisfaction; anything with a decidable definition)

1. Graph topology: connectivity, reachability of every node, at least one ending reachable from every node, no orphans, no unintended cycles (or only bounded, intentional cycles), depth and branching-factor bounds per band.
2. Ending inventory: count, type mix (triumphant/neutral/setback), and minimum distance-to-ending guarantees per band.
3. State and condition logic: a tiny, decidable condition DSL (boolean flags, bounded counters); satisfiability of every guard along at least one path; no dead choices; no unwinnable/deadlocked states; no condition referencing an unset variable. Symbolic evaluation or exhaustive path walking, never an LLM.
4. Budgets: per-node word ranges, per-book totals, choice counts, ending counts, path-length distribution.
5. Schema validity: the storybook artifact validates against a versioned JSON schema; IDs unique; every choice targets an existing node.
6. Readability mechanics: sentence length caps, syllable/word-frequency stats, grade-level formulas as hard gates per band (formulas as gates, not as optimization targets).
7. Lexicon enforcement: banned words/phrases per band; required-vocabulary coverage for early readers; profanity/URL/PII pattern scans on output.
8. Surface consistency that is string-checkable: character name spelling, tense/POV heuristics (advisory), choice-label formatting.
9. Deduplication: exact hashes, n-gram overlap, embedding near-dup detection vs the catalog and vs the requesting family's shelf; structural isomorphism/fingerprint distance vs the skeleton library.
10. All systems concerns: scheduling, retries, caching, budget accounting, provenance capture.
- Criterion: if a property has a formal definition and a false negative is unacceptable, it must be code. LLMs check only properties you cannot define formally.

### 1.2 LLMs should own (judgment)

11. Premise and plot invention within constraints; motivation, stakes, cause-effect along branches.
12. Prose: voice, tone, humor, pacing, sensory detail, per-band style.
13. Choice text that reads as a genuine, comprehensible dilemma (not "go left / go right" filler).
14. Graded soft judgments as scorers: scariness/emotional intensity, mature-theme detection, stereotype/representation issues, subtle innuendo, coherence/contradiction detection (NLI-style), choice meaningfulness, "sameness feel" vs prior books.
15. Targeted repair: rewriting a flagged node given the critique, beats, and neighbors.
- Criterion: subjective or open-ended language properties; every LLM production is paired with a downstream check (deterministic, model-scored, or human), never trusted bare.

### 1.3 Humans should own

16. Final approval (company policy), per-band content policy and thresholds, adjudication of classifier abstain/borderline cases.
17. Authoring or curating the reusable structure library, style bibles, and exemplar nodes; taste calibration via rubrics and golden examples.
18. Incident response, recall decisions, policy changes.
- Criterion: accountability, legal duty, and taste-setting (defining what the machines optimize toward).

### 1.4 Graph construction vs prose writing

19. Hard-separate layers with explicit contracts: structure (topology + state) -> plan (character bible, setting, per-node beat sheet, ending intents) -> prose (per-node text) -> metadata (title, blurb, cover brief). Validate each layer before spending on the next.
- Criterion: cost of a defect grows superlinearly with the stage it is caught at; a topology bug caught pre-prose saves the whole prose spend; a plot bug caught at the plan layer is reviewable in 2k tokens instead of 118k words.
20. Structure is model-free or model-light and reusable across books; prose is per-book and disposable; plans are the cheap human/model review point for story logic.
21. Merge-heavy DAGs are the economic core for big books: word cost scales with node count, perceived breadth scales with path count; diamonds/merges buy many distinct paths per node. Manage merge coherence by writing merge nodes context-neutral or state-conditioned transition lines.
- Criterion: target path-count-to-node-count ratio per band; check merge nodes with an "arrival coherence" model gate.

### 1.5 Where reuse/templating helps vs hurts perceived variety

22. Safe to reuse (below the perception line): topology patterns, pacing curves, state-machine idioms, choice-slot placement, safety envelopes, validator configs, prompt scaffolds, style bibles, condition DSL patterns.
23. Dangerous to reuse (above the line): surface prose, opening lines, character names, choice wording, distinctive plot beats at the same structural positions, settings + cast combinations, titles/blurb phrasing.
24. Locate the perception line empirically: paired-book comparisons by parents/kids ("do these feel like the same book?") correlated against structural fingerprint distance and surface embedding distance; the correlation defines what must vary.
- Criterion for any reuse decision: does blinded panel testing or family complaint data show the reused element is detectable? Detectable => must vary per book.

---

## 2. The approach space (what a fresh architect should evaluate)

### A. Procedural/algorithmic graph generation + LLM prose fill

25. A parameterized sampler (graph grammar, rewrite rules, or CSP solver) emits valid topologies and beat scaffolds by construction; the LLM fills node prose from beat directives.
26. Wins: correctness-by-construction (near-zero structural rejects), tight cost bounds, easy structure-level variety via sampler parameters; strongest for small books (3-8 band) and for high-volume production; also the engine for growing the structure library offline.
27. Loses: beats can feel mechanical if also procedural; a premise that wants an unusual shape fights the sampler; sampler authoring is real engineering.
- Criterion: structural-rejection rate and cost-per-book tail vs approach B; blinded "does this feel authored" panels vs B/D.

### B. LLM-authored graphs checked by validators (generate-and-test)

28. A frontier model emits the whole graph + plan under schema constraints; deterministic validators accept, trigger repair, or reject.
29. Wins: maximum per-book novelty; bespoke requests; large 13+/16+ books where structure should serve the premise; the discovery engine for new structures.
30. Loses: unpredictable retry cost; long-context failure modes at 600 nodes (must generate hierarchically anyway); subtle state-logic bugs; validator whack-a-mole.
- Criterion: first-pass acceptance rate, expected retries, and p95 cost per book vs A/D; novelty (structural distance from library) actually achieved.

### C. Constrained decoding / grammar-constrained generation

31. JSON-schema/CFG/regex constraints during decoding for every structured emission: graphs, plans, classifications, choice-label formats, condition DSL; optional logit masking for banned lexicon or controlled vocabulary in early-reader prose.
32. Wins: eliminates malformed-output retries at near-zero cost; makes small/cheap models viable for structured stages; full control when self-hosting.
33. Loses: does nothing for semantic validity; token-level lexical masking can degrade fluency; provider support is uneven (portability risk).
- Criterion: malformed-output rate before/after; fluency evals with masking on/off. Verdict: orthogonal; adopt for all structured outputs regardless of macro-approach.

### D. Human-authored reusable templates (skeletons) with LLM fill

34. Humans author/curate a library of parameterized skeletons: topology + state + beat directives + slot constraints + safety envelope; the LLM instantiates theme, cast, setting, and prose.
35. Wins: highest quality floor, most predictable cost, fastest human review (reviewer already knows the skeleton and its risk profile), pre-vetted safety envelope; the right backbone for 3-12 volume production.
36. Loses: upfront library cost; sameness risk if the library is thin or beats leak into surface text; off-library bespoke requests still need B.
- Criterion: amortized skeleton authoring cost per instantiation at projected volume; sameness complaint rate vs library size; reviewer minutes per book vs B.

### E. Hybrid human + LLM authoring (economics)

37. Humans produce high-leverage, amortized artifacts (skeletons, style bibles, exemplars, rubric definitions) and do targeted repair; LLMs produce per-book volume.
38. Economics sketch: a skeleton at 2-5 author-days amortized over 50-500 instantiations is cents-to-dollars per book; full human authoring only competes for flagship titles or bootstrapping a new band; human repair beats regeneration only when localized and rare.
- Criterion: crossover chart of (author/reviewer hourly cost x minutes) vs (token cost x retries) per book size class; recompute quarterly as model prices fall.

### F. Retrieval or remix over a corpus

39. Retrieve approved books/fragments as style exemplars per band, beat inspiration, or direct scene recombination; also "more like this one" requests.
40. Wins: style anchoring (few-shot exemplars raise prose floor cheaply), house-voice consistency, fast sequels.
41. Loses: direct surface remix is the fastest route to detectable sameness and to echoing copyrighted text; retrieval must feed conditioning, never verbatim reuse.
- Criterion: prose eval uplift from exemplar conditioning vs zero-shot; n-gram overlap of outputs against the corpus (enforce a ceiling).

### G. Fine-tuned or distilled small models per stage (evaluate even if not asked)

42. Once volume and stable rubrics exist, distill frontier behavior for prose fill and classifiers onto cheap/self-hosted models.
- Criterion: eval parity within tolerance at a large cost reduction; monthly volume above the amortization threshold for training + maintenance; privacy benefit if self-hosted.

### H. Multi-agent generate/critique/revise loops

43. Useful only where single-pass quality sits just under a gate and blind resampling wastes tokens.
- Criterion: pass-rate uplift per marginal token vs simple resample and vs targeted repair; if not clearly better, skip the complexity.

### Recommended composite (and why)

44. D is the production backbone (per-band skeleton library); A is the offline skeleton factory (procedural mutation/sampling of new skeletons through the same validators); B handles bespoke/large books and proposes novel skeletons; C applies everywhere structured; F supplies style exemplars only; E is the operating model; G arrives at scale.
- Criterion for the composite and all future re-weighting: minimize (tokens + reviewer minutes) per approved, non-duplicative word at a fixed quality bar, measured on a standing eval set and live gate metrics.

---

## 3. Pipeline stages and gate design

### 3.1 Stage list (with loops)

45. Intake: normalize the guardian request into a schema'd brief (band, themes, length class, personalization params, constraints).
46. Request screening gate BEFORE any generation: request-level safety (disallowed themes for band), IP/trademark screening (no "Elsa from Frozen"), feasibility, band fit. Rules + cheap classifier.
47. Variety pre-check: compare brief against the family's shelf and recent catalog (theme embedding + planned-structure recency) to steer selection away from repeats.
48. Structure acquisition: select a skeleton (D), sample one (A), or LLM-propose (B) for bespoke; record which path was taken.
49. Structural gate (deterministic): topology, state logic, budgets, band profile conformance.
50. Planning: character bible, setting sheet, per-node beat sheet, ending intents, title/blurb brief; schema-constrained generation.
51. Plan gate: deterministic (slot coverage, name lists, lexicon scan of beats) + model critique (age fit, coherence, stereotype scan); optional quick human skim only for first-use skeletons or bespoke structures.
52. Prose fill: per-node or per-arc generation in topological order, conditioned on beats + ancestor summaries + style exemplars; parallelize across siblings/branches.
53. Per-node gates at generation time: schema, length, readability, lexicon, name consistency; retry locally with bounded attempts.
54. Whole-book deterministic gate: re-run all structural checks on the final artifact, cross-node string consistency, catalog dedup, n-gram overlap ceiling vs corpus.
55. Model gate battery: safety classifiers (multi-label, per-band thresholds, ensemble for diverse failure modes, abstain band routes to human), reading-level scorer, contradiction/coherence scorer, merge-arrival coherence, choice-quality scorer, sameness scorer vs family shelf, representation audit.
56. Automated repair loop: targeted node rewrites for localized failures; recompute only affected gates; bounded budget; else escalate to human triage or park.
57. Human review and approval: risk-ranked surface (see 3.4); approve / per-node reject (loops to 56) / edit in place (edits re-run deterministic + model gates; humans introduce defects too).
58. Publish: freeze artifact, hash and sign, assign version, record approval over the hash, distribute (including offline caches).
59. Post-publish: reader/guardian flag button, engagement telemetry, periodic policy re-screen; recall path with tombstones that propagate to offline copies on next sync.

### 3.2 Gate ordering principles (why order matters for cost)

60. Order gates by ascending check cost and descending expected rejection mass: schema -> topology/state -> budgets/lexicon/readability -> model scorers -> human. Expected cost = sum over gates of P(reaching gate) x gate cost; put big rejecters early and cheap.
61. Never spend prose tokens on a structure that can fail a free check; never spend human minutes on a book a $0.01 classifier would flag; never call a frontier model on a request rules would reject.
62. Request-level gates dominate ROI: rejecting a bad request costs cents; a bad finished book costs dollars plus reviewer attention plus cycle time.
63. Deterministic checks are cheap to re-run: re-run the full deterministic battery at every artifact mutation (after repair, after human edit) as defense in depth.
64. The human gate is last, singular, and protected: everything upstream exists to make "approve" fast and "reject" rare.
65. Instrument every gate with pass rate, unit cost, latency, and escape rate (defects caught later that it should have caught); reorder and retune from this table quarterly.
- Criterion for placing any new check: marginal expected-cost reduction vs added latency/complexity, computed from measured pass rates.

### 3.3 Assigning checks to tiers

66. Deterministic tier: everything in 1.1. Model tier: everything in 1.2 item 14, always emitting score + rationale with thresholds in config. Human tier: final approval, abstain-band adjudication, new-skeleton signoff, threshold-setting reviews.
67. Verify tier assignment empirically with a seeded-defect corpus (deliberately corrupted books: unsafe lines, contradictions, dead ends, wrong reading level) and measure each gate's recall on its defect classes; re-run on every validator/classifier change.
- Criterion: cheapest tier whose false-negative rate on seeded defects meets the bar for that defect class.

### 3.4 The human gate at scale (the hard problem nobody budgets)

68. Face the math: "a human approves every book" is trivial at 800 words and impossible-as-full-read at 118k words. Decide the policy interpretation explicitly and write it down: (a) full read (possibly split across reviewers by subtree), (b) structured review: full read of plan + flagged nodes + risk-ranked sampled paths achieving X% node coverage, (c) tiered by band and risk score.
- Criterion: post-publish defect escape rate per review mode measured via seeded defects and live flags; pick the cheapest mode meeting the escape-rate bar; larger/older-band books can tolerate (b), 3-5 band likely warrants near-full read.
69. Review surface: plan summary first, graph visualization, flagged nodes ranked by risk, per-gate evidence inline, diff vs skeleton baseline and vs prior version, path-coverage tracker, one-click per-node reject-with-reason feeding repair.
70. Support per-node rejection, not whole-book bounce; measure reviewer minutes per approved book and per approved kiloword as first-class KPIs.
71. Reviewer quality program: rubric training, inter-rater reliability checks, periodic double-review samples, drift calibration sessions.
72. Republication rule: define which changes reset approval (any child-visible text change does; metadata may not); re-review effort proportional to diff.

---

## 4. Model selection policy per stage

73. Routing table (stage -> model id, params, fallback chain, budget) lives in versioned config, not code; changes are change-managed like code.
74. Default shape: frontier model for structure synthesis (B), planning, and hard repair; mid-tier for prose fill; small/cheap for classification, extraction, summarization, choice polish; dedicated embedding model for dedup/retrieval/similarity; self-hosted/local for privacy-sensitive passes and as a cost floor; batch-tier pricing for all non-interactive generation (kids never wait synchronously; the product is async with notification).
75. Per-stage standing evals with frozen datasets: plan quality rubric, per-band prose rubric (LLM-judge anchored, human-audited), classifier ROC on labeled safety data, structure-proposal acceptance rate.
76. Champion/challenger: every candidate model runs in shadow on N live books; promote on quality parity + cost/latency win; never swap a safety scorer without recalibrating thresholds (scores are not comparable across models).
77. Judge maintenance: LLM-as-judge drifts too; audit judge-human agreement quarterly and on any judge model change.
78. Determinism: temperature 0 and fixed seeds for scorers/extractors; record temperature/seed for all creative calls.
79. Provider hygiene: allowlist, no-training-on-our-data terms, deprecation-watch alerts, pinned snapshots where offered, regional/data-residency constraints for any call carrying user data.
80. Cost governance: per-book token budget by size class and band, enforced by the router; alerting on budget breach; monthly cost-per-approved-book and cost-per-active-family dashboards.
- Criterion for any routing change: eval delta + cost per approved book on shadow traffic; never vibes, never "the new model is obviously better".

---

## 5. Observability and provenance (per-book record)

Record append-only, keyed by book id + attempt id, retained per policy:

81. Inputs: raw request text, normalized brief, requester id, target profile band, personalization params, request-screening verdicts.
82. Structure lineage: skeleton id + version, or sampler seed + params, or B-proposal transcript; structural fingerprint of the final graph.
83. Plans: character bible, beat sheets, ending intents, with prompt template ids + versions and variable bindings.
84. Every LLM call: template id + version, rendered-prompt hash, model id/snapshot, params, seed, raw response (retain raw outputs; storage is cheap relative to re-debugging and audits), token counts, latency, cost, retry index.
85. Every gate execution: validator/classifier version, threshold-config version, input artifact hash, verdict, scores, rationales, duration.
86. Repairs: node ids, trigger, before/after diffs, attempts consumed.
87. Human trail: reviewer id, time spent, per-node decisions, edits as diffs, approval signature bound to the final artifact hash (this is the legal record of the approval duty).
88. Final artifact: content hash, schema version, published version id; a lineage DAG connecting every item above; correlation id threaded through all queue jobs and logs.
89. Aggregates: gate pass/escape rates, cost percentiles by band/size, reviewer minutes, sameness trend, post-publish flag rate sliced by skeleton, prompt version, and model version (your regression detector).
90. Reproducibility stance: bit-exact replay across provider model updates is impossible; target "explainable replay" (every input and output stored, pinned snapshots where offered) and say so in the audit story.
- Criterion: any post-publish incident is answerable from the record alone ("what produced this sentence, which gates saw it, at what versions, who approved") without rerunning anything.

---

## 6. Failure recovery, retries, partial-work resumption

91. Model generation as a durable, resumable workflow: a DAG of idempotent steps over content-addressed intermediate artifacts; a crash resumes at the last completed step, never restarts the book.
92. Node-level task granularity for prose: each node fill is an independent retryable task (inputs: beats + ancestor summaries + style pack), so one bad node never invalidates 599 good ones.
93. Idempotency keys per (book, stage, node, attempt); at-least-once queues made safe by content addressing; dead-letter queue with reason codes and a daily triage report.
94. Retry taxonomy with distinct policies: transient (timeout/429) -> backoff + provider failover; malformed -> constrained decoding first, then bounded resample; semantic gate failure -> targeted repair with critique, max K attempts, then park for human triage.
95. Per-book circuit breaker on tokens and wall clock; breach parks the book with state intact rather than burning silently. This is what makes unit cost predictable at p95, not just at the mean.
96. Poison detection: the same node failing across models/prompts indicts the beat or skeleton, not the sampler luck; route to skeleton QA instead of infinite retries.
97. Safety-stage failover discipline: never silently fall back to an un-evaluated model for a safety scorer; degrade to queue-and-wait instead.
98. Dependency-aware invalidation: after a human edit or node repair, regenerate only the affected subtree/summaries and re-run only impacted gates.
99. Hierarchical generation for big books: book plan -> arc plans -> node fills with summaries as the interface; never one giant call; wavefront-parallelize sibling branches; watch long-horizon style drift with periodic style scoring against band exemplars.
100. Chaos-test the factory: kill workers mid-book, inject provider outages, verify zero lost work and correct resumption.
- Criterion: p95/p50 cost ratio per book size class, zero lost-work incidents, and mean books-parked-per-week trending down.

---

## 7. Versioning (prompts, models, templates, thresholds)

101. Version everything that affects output: prompt templates (semver + content hash), routing table, skeletons, validator code, classifier models, threshold sets, banned lexicons, band profiles, artifact schema. Every book records the exact tuple.
102. Thresholds are calibrated artifacts, not knobs: each threshold stores its calibration dataset id, ROC/PR curves, chosen operating point, approver, and date; recalibrate on scorer-model change or drift alarm; forbid hand edits without a recorded calibration run.
103. Change management: every prompt/model/threshold change runs shadow/canary (frozen eval set + N live books in parallel) before fleet rollout; one change at a time or factorial bookkeeping so regressions attribute to a single change id.
104. In-flight policy: books in progress finish on pinned versions; new versions apply to new books; explicit migration re-validates.
105. Published books are immutable; any edit creates version N+1 with re-approval per the diff rules; version history retained for audit and for readers mid-book.
106. Catalog re-screening: when policy, lexicons, or safety classifiers materially change, re-run model gates across the published catalog; human re-review only new flags; record the sweep as an event.
107. Rollback: routing table and threshold sets revert atomically to last-known-good; rehearse it.
- Criterion: any two books diffable by configuration tuple; any quality/safety regression attributable to one change id within a day.

---

## 8. Catalog growth strategy (structures per band)

108. Define "structure" as topology + pacing + choice pattern + state usage, independent of theme. Perceived variety = structures x themes x casts x settings x voices; sameness complaints localize to the thinnest axis, so measure each axis separately.
109. Sizing heuristic to start (then calibrate): a weekly-requesting family sees ~50 books/year; to keep near-in-time structural repeats unnoticeable, launch with ~10-15 structures per band, grow to ~30-50 at maturity, weighted by band demand. Trust measurement over the heuristic.
110. Band-shaped profiles: 3-5: ~8-20 nodes, 2-way choices, shallow depth, no failure endings, no state; 6-8: ~20-60 nodes, light state; 9-12: ~60-150 nodes, real state and consequences; 13-16+: ~150-600 nodes, failure endings, delayed consequences, larger casts. Encode as validated band profiles, not folklore.
111. Growth engine, three sources: (a) offline procedural mutation/crossover of existing skeletons through the full validator battery; (b) LLM-proposed novel skeletons admitted only above a structural-novelty distance from the library; (c) promotion of successful bespoke (path-B) books into parameterized skeletons.
112. Growth rate driven by signals, not calendar: repeat-request rate per family, sameness complaints, structure-usage concentration (Gini) per band; grow whichever band's concentration is highest.
113. Assignment policy at request time: per-family structure rotation with recency penalties so no family sees near-identical structure within K consecutive books; same for theme and cast archetypes.
114. Per-skeleton health dashboard: instantiation count, gate pass rate, reviewer minutes, engagement (completion, alternate-path re-reads), flag rate, mean sameness score of its offspring.
115. Retirement/rest policy: rest a structure when its offspring cluster too densely in similarity space, or engagement decays across instantiations, or flag rate rises; archive with provenance, never delete; consider seasonal rotation back in.
- Criterion throughout: measured sameness (structural fingerprint distance + surface embedding distance + paired human panels + complaint rate), not intuition, drives library size, growth, and retirement.

---

## 9. Personalization hooks without safety or privacy regressions

116. Tier 0, preferences: themes, interests, difficulty, favorite animals; parameterizes the brief; no PII in any prompt; safe by default.
117. Tier 1, identity-lite via approved slots: child name/pronouns substituted into an approved book at render time through pre-declared slots with validated value constraints (charset, length, lexicon); deterministic renderer, no LLM at read time; human approval covers the slotted template, so approval survives personalization.
- Criterion for slot eligibility: can any allowed value change meaning, safety, or emotional register of the sentence? If yes, it is not a slot.
118. Tier 2, bespoke books using personal details: full pipeline including human approval, no shortcuts; pseudonymize child identifiers before any third-party LLM call and re-substitute after, or run those passes on self-hosted models.
119. Privacy boundary rules (children's-privacy regimes: COPPA/GDPR-K posture): no child PII to providers without contractual controls and guardian consent; data minimization; retention limits on personalization inputs; contractual and technical no-training-on-our-data; per-provider allowlist of what may cross the boundary.
120. Safety rules specific to personalization: name-in-peril policy per band (the named child must not be placed in distressing roles for young bands); banned combinations (child name x scene types); adversarial-name regression tests (names that form unfortunate sentences, injection attempts via the name field).
121. Behavior-driven personalization (recommendations, difficulty adaptation): prefer selecting among approved books and approved band profiles over mutating text; aggregate or on-device processing for reading telemetry; any model input derived from child behavior passes the same privacy boundary.
122. Provenance: personalization params recorded like any input; rendered variants derivable from (approved artifact + params) rather than stored per child where avoidable.
- Criterion for any proposed personalization feature: does it (a) invalidate human approval, (b) move child PII across a trust boundary, or (c) create per-child text no human reviewed? Any yes forces redesign or full-pipeline treatment.

---

## 10. Cross-cutting requirements (compact)

123. Content policy taxonomy per band, written down: violence/peril intensity, fear/horror, romance bounds, loss/grief handling, moralizing tone limits, representation goals; classifiers and reviewers score against the same named taxonomy.
124. Prompt injection: guardian free text is untrusted input; quote it as data in templates, screen it at intake, keep generation models tool-less, and rely on output gates that do not trust the input; no URLs, contact info, or instructions in child-visible text (deterministic scan).
125. IP hygiene: trademark/character screening at request and output; n-gram overlap ceiling vs known corpora to avoid memorized text.
126. Choice quality semantics: define and score "meaningful choice" (visible stakes, distinct consequences, age-comprehensible wording); telemetry check: distribution of choices taken (a 95/5 split flags a fake choice).
127. Endings policy per band: young bands get only warm endings; older bands get consequence endings with bounded harshness; validator enforces mix.
128. Series/sequels: persistent character bibles and continuity ledgers as first-class, versioned artifacts; continuity checks become cross-book gates.
129. Cover art/illustrations, if in scope: separate generation lane with its own safety gates (image classifiers + human), bound into the same evidence bundle.
130. Localization later: treat language as a band-profile dimension; translation is generation and passes the full gate chain, not a string swap.
131. Quality evaluation program: golden book set per band, rubric-anchored judging with human audit, seeded-defect recall runs on every pipeline change, quarterly blinded panels with real families; engagement telemetry (completion, re-reads, abandonment nodes) as the lagging outcome metric.
132. Economics dashboard: cost per approved book split into tokens, retries, review minutes, amortized structure authoring; the split tells you what to optimize next.

---

## The 10 mistakes teams most often make here

1. One monolithic LLM call per book: no layer separation, so every defect costs a full regeneration, cost variance explodes, and nothing is reviewable before the whole spend.
2. Letting the LLM own graph validity: topology and state bugs discovered after prose spend (or by a child hitting a dead end), instead of deterministic structure-first validation or construction-by-sampler.
3. Under-investing in the human gate: treating mandatory approval as a rubber stamp with no review tooling, then discovering reviewer minutes, not tokens, are the real unit cost and the real bottleneck; never deciding what "review" means for a 118k-word book.
4. Misjudging the reuse/perception line: either paying bespoke-generation cost for structure that no reader can perceive, or reusing surface text/beats and getting caught by the third family request; never measuring sameness at all.
5. Unversioned prompts, models, and thresholds: hand-tweaked knobs with no calibration record, so regressions cannot be attributed and the audit trail for approvals has holes.
6. Unbounded retry loops and whole-book rework: no per-book budget breaker, no node-level repair, so p95 cost is many times p50 and "low, predictable unit cost" quietly dies.
7. Safety gating only at the end, with one classifier and one global threshold: expensive late rejects, no per-band operating points, no ensemble or abstain-to-human band, and no seeded-defect measurement of what the gates actually catch.
8. Swapping models without recalibration or shadow evals: scorer scores silently shift meaning, prose style drifts, and the team attributes the change to luck.
9. Personalization bolted on after launch that bypasses the gates: render-time LLM text no human approved, or child names/PII flowing to third-party providers, converting a delight feature into a safety and compliance incident.
10. No provenance or raw-output retention: debugging by re-running a nondeterministic pipeline, unanswerable audits ("who approved this sentence and what did the classifiers say"), and no way to trace a live incident to the prompt, model, or template version that caused it.
