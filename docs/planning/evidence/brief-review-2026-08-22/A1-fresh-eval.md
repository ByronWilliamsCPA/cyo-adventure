# A1 fresh-eyes: evaluation and testing methodology (goal-only, no brief or repo access)

# Evaluation and Testing Methodology for LLM-Generated Branching Children's Books

Scope note: "book" means a directed story graph with choices, optional state/conditions, reconvergence, and multiple endings, at scales from ~800 words to 600+ nodes / ~118k words, for age bands 3-5 through 16+. All thresholds below are calibration starting points, and every threshold must be set per band, never globally.

## 1. Foundations (definitions the whole programme depends on)

- Unit hierarchy: node, edge/choice, path (start to ending), junction pair (reconvergent node x inbound predecessor), book, series, batch, catalog, pipeline version. Every metric must declare its unit.
- A book's quality is a distribution over paths, not a scalar. Report min/median/max path scores; gates bind on the worst reachable path, not the average.
- Per-band everything: thresholds, rubrics, structural budgets, safety caps. A single global threshold is a category error.
- Defect taxonomy with severity before any metric: S0 child-safety escape, S1 blocking (contradiction, broken graph, wrong band, unfair gotcha), S2 degrading (clunky prose, weak choices), S3 nit. All gates, judges, and reviewers map findings to it.
- Full lineage per book: generator model + snapshot date, prompt hashes, skeleton ID/version, decoding params, validator/judge versions, human reviewer ID, timestamps. Without this, no later section works.
- Dev/holdout split of requests and skeletons; prompt iteration only ever touches dev. Log every holdout exposure.
- North star for the eval programme itself: escape rate = severity-weighted defects discovered after human approval, per 100 published books. Target S0 = 0, S1 < 1/100.
- Eval must fit unit economics: automated eval compute budget (~10-15% of generation cost) and human review minutes per accepted book are tracked metrics, not afterthoughts.

## 2. Structural soundness of story graphs

**Questions**
- Is the graph well-formed and playable for every possible choice sequence, not just sampled ones?
- Are all nodes and endings reachable, all paths terminating, all cycles intentional with guaranteed exits?
- If the format has flags/items/conditions: is every condition satisfiable and falsifiable on some reachable path; is every state read preceded by a possible write?
- Does the shape match the band's structural budget (arity, depth, reconvergence, ending count, per-path length)?

**Measure**
- Hard validator suite, 100% pass required: single start; no orphan nodes; no dangling choice targets; no unreachable nodes; every path terminates; revisit caps on any declared loop.
- Termination and reachability over graph x state space (exhaustive where feasible; bounded model checking or SAT on conditions where not); the checker must report coverage %, never a bare pass.
- Dead-logic check: unreachable conditional branches = 0; unobtainable items = 0; contradictory flag combinations = 0.
- Ending reachability under multiple play policies (uniform random, always-first, always-last, avoid-repeats): every ending reachable; probability of premature/failure endings under random play within band policy (~0 for 3-5; <=25% for older bands).
- Per-path word counts: every path within band budget (e.g., +/-25% of target); no path below a "rip-off floor"; report path-length distribution, not book total.
- Band structural budget table (illustrative): 3-5: 8-30 nodes, arity 2, depth 3-6, fast reconvergence, 2-4 endings; 6-8: arity 2-3, depth 5-10; 9-12: arity 2-4, depth 8-15; 13+: full scale. Gate on out-of-budget.
- Divergence audit per choice: nodes/words until reconvergence plus state delta; null-choice rate (reconverges in <=1 node with no state or prose consequence) < 10%.
- Coverage read-set: compute a minimal path set covering 100% of edges and 100% of junction pairs; this defines the mandatory review reading budget and is itself a cost metric per book.
- Random-walk fuzzing (e.g., 10k seeded walks): no crashes, no empty choice lists before an ending, no budget violations.
- Differential runtime testing: if more than one engine walks the graph (server, client, offline export, print), replay identical seeded walks on all; divergence = 0.
- Serialization QA: schema validation, ID uniqueness, round-trip stability, encoding checks, per-node render-length limits for the smallest supported screen.
- Re-run the full structural suite after any node/edge edit, human or automated; enforced by tooling.

**Guard**
- "All paths checked" silently meaning "some paths checked" under combinatorial explosion.
- Structural pass masking semantic emptiness (choices that change nothing); only the divergence audit catches this.
- Metrics computed on the skeleton but not the filled book (fills can invalidate effective structure).
- Loops that terminate in theory but trap a real child in practice.
- Choice labels re-pointed at wrong targets after edits.

## 3. Choice, agency, and ending design

**Questions**
- Are choices meaningful, decodable at band level, informative about stakes without spoiling?
- Are negative outcomes foreshadowed (fair) or gotchas? Is failure recoverable per band policy?
- What behavior does the ending structure reward (the graph's hidden curriculum)?
- Is there enough early divergence and second-read novelty?

**Measure**
- Choice-label readability: labels are the highest-stakes text (a child who cannot decode labels cannot play); 100% of labels strictly within band level.
- Label-outcome calibration: judges (validated against kids) predict outcome valence from label; target partial predictability (~60-80%), not 100% (no agency) nor chance (gotcha machine).
- Fake-choice rate < 10%; dominated-choice check (one option obviously strictly better) flagged unless didactic.
- Foreshadowing gate: every failure/negative ending has a detectable warning on its path; 100% for bands <= 8.
- Ending portfolio per band: count, valence mix (3-5: all reassuring; 6-8: gentle setbacks allowed; 13+: tragedy allowed), reachability weights; best ending not gated behind antisocial play.
- Incentive-matrix audit: classify each choice prosocial/neutral/antisocial and each ending's valence; publish the matrix per book; gate: antisocial choices must not systematically yield the best outcomes for bands <= 12.
- Second-read novelty: under an "avoid previous picks" replay policy, % new nodes on read two (>=40% for 9+, lower for 3-5); first divergence within the first 2-3 nodes.
- Choice-position audit: outcome quality uncorrelated with display position (kids strongly favor the top option); randomize order or balance deliberately.
- Memory-burden check: when a payoff depends on an event more than N nodes back, younger bands require an in-text reminder; count violations.

**Guard**
- Enticing labels that mislead about the destination (label-node fidelity check).
- All roads lead to one ending: book-scale illusion of choice.
- Every curious choice punished: teaching risk-aversion by accident.
- Novelty metrics gamed with trivial variant nodes.

## 4. Prose quality

**Questions**
- Is prose mechanically clean, natural read aloud, vivid, consistent in voice/tense/person, and free of LLM tells?
- Does craft hold at the worst node and on rare paths, not just on the likely path?
- How does it compare against human-authored children's books, not just other LLM output?

**Measure**
- Mechanical error rate < 0.5 per 1000 words; 0 errors in choice labels, first node, and ending nodes.
- LLM-tell lexicon (versioned: "tapestry", "little did you know", "shivers down your spine", moralizing codas): hits per 1000 words below threshold; lexicon refreshed per model generation.
- Cross-node repetition: duplicated n-grams and repeated node-opening patterns (not every node "You walk into...") below threshold, excluding declared refrains.
- Lexical richness (MTLD/TTR) and sentence-length variance within band norms; tense/person/POV consistency checks = 0 violations.
- Anchored 1-5 rubric per dimension (clarity, vividness, dialogue, pacing, voice, read-aloud rhythm) scored over the coverage read-set: median >= 4, no node < 3 on clarity.
- Blinded pairwise win-rate vs a matched human-written baseline corpus per band; target >= 40-50% or a stated accepted gap, tracked over time.
- Read-aloud test (human or TTS): stumbles per 100 words below threshold; mandatory for 3-5.
- Character voice: sampled dialogue distinguishable by character and stable across paths.
- Emotional-arc check per path: flatness score; rising action and resolution present on every path, including short failure paths.
- Importance-sample rare paths for prose judging (weight by inverse reach probability): quality-effort concentration on the golden path is the default failure.

**Guard**
- Judge fluency/verbosity bias rewarding empty polish; use pairwise comparisons and required evidence quotes.
- Per-node scoring missing book-level monotony; require whole-path reads.
- Banned-word enforcement producing thesaurus-itis; measure naturalness, not just tell-avoidance.
- One house style across all books (also a diversity failure; see section 6).

## 5. Age fit and reading level

**Questions**
- Can the band decode it (independent reading) or follow it (read-aloud), and which mode is the target?
- Are themes and emotional load bearable for the band; is interest level matched, not just reading level?
- Is difficulty consistent per node and per path, not just on the book average?

**Measure**
- Readability ensemble (Flesch-Kincaid, Dale-Chall, Spache for early bands, plus an ML leveler trained on leveled children's corpora): book in band, every node within band tolerance, labels strictly in band.
- Vocabulary: % tokens above band age-of-acquisition/frequency norms < 2-5%; stretch words budgeted (<=1 per 200 words) and context-inferable; decodability against phonics-stage lists for 5-7 independent readers.
- Syntax caps: max embedding depth, passive rate, sentence-length p95 per band.
- Theme/maturity matrix gate: abstraction, irony, romance, moral ambiguity, peril intensity classified per band; hard gate on over-band themes.
- Interest-level check separate from reading level: plot judged age-attractive (12-year-old plot in 6-year-old prose fails, and the reverse).
- Expert placement test: blinded teachers/librarians assign bands from excerpts; >= 80% exact match, errors only to adjacent bands.
- Kid ground truth (section 10): >= 70-80% on causal comprehension questions for band-fit books.
- Per-path difficulty variance: max path-level minus book-level gap thresholded; no hidden hard path.
- Locale/dialect consistency check (US vs UK vocabulary and spelling).

**Guard**
- Formula gaming: short sentences about hard concepts score "easy"; formulas never gate alone.
- Book averages hiding one spike node (the node the parent screenshots).
- Conflating listening comprehension with reading level for read-aloud bands.
- Ignoring band straddlers; verify tolerance to +/-1 band.

## 6. Cross-book diversity

**Questions**
- Operational definition first: two books are "the same re-skinned" when a blinded reader of both says "same story, names swapped"; every automated metric must calibrate to that human judgment.
- Diverse for whom: the whole catalog, a band-topic slice, or the sequence one specific child receives?
- Which axes: graph/skeleton shape, beat sequence, tropes, setting, cast archetypes, emotional arc, ending pattern, prose fingerprint, names, choice texture.

**Measure**
- Human calibration study: panel labels book pairs same/similar/distinct; fit automated thresholds to >= 90% agreement with panel; refresh yearly and per model change.
- Embedding similarity at three granularities (synopsis, beat sequence, node prose); flagged-pair rate in catalog < 1% above calibrated threshold.
- Structural fingerprints: skeleton reuse caps per band-topic slice; graph-motif histogram distance; beat-taxonomy sequence alignment.
- Role-mapping detector (entity-role embeddings) to catch dragon-to-pirate re-skins that topic embeddings call "different".
- Surface reuse: distinctive-phrase and character-name reuse across books below threshold; no shared signature sentences; self-plagiarism scan across the catalog.
- Per-child sequence gate: no two books assigned to one child above the pair threshold; recommendations are diversity-constrained, and this is measured on delivered sequences, not the generation pool.
- Same-request spread: submit an identical request N=10 times; require distinct outputs (pairwise distinctness distribution reported).
- Catalog coverage in the other direction: entropy/coverage over themes, settings, protagonist demographics, emotional registers per band; gap report drives commissioning.
- One-line pitch collision test: auto-pitch every book; near-duplicate pitches route to human pair review.
- Kid-level probe in playtests: false-familiarity rate ("I already read this one") on books they have not read.

**Guard**
- Topic embeddings passing structural clones and structure metrics passing prose clones; multi-axis or nothing.
- Penalizing intentional series similarity; exempt declared series, then separately test within-series freshness.
- Diversity pushed until coherence and quality drop; always publish the diversity-quality frontier, never diversity alone.
- Thresholds calibrated on adult similarity perception only; validate at least once against kids.

## 7. Safety

**Questions**
- Is every path (not node) within band policy for fear, violence, loss, romance, substances, weapons, bullying?
- Second-person risk: what does the text make "you" do, and is any act dangerously imitable (knives, fire, water, roads, eating found things, hiding from caregivers, meeting strangers)?
- Does any content pattern-match grooming normalization (secrets from parents, adult-child "don't tell" framing)?
- Can guardian-supplied request text or personalization inject unsafe content or instructions?
- Legal exposure: trademarked characters, plagiarism, real people, health/safety misinformation?
- What does the incentive structure teach (section 3 matrix), and what stereotypes does the book carry?

**Measure**
- Category classifier ensemble with band-specific operating points; validated FN ~0 on critical categories against a maintained red-team corpus; FP < 5-10% on known-good books to protect reviewer throughput.
- Path-cumulative scoring: peak and summed fear/peril per path with per-band caps; a chase sustained over six mild nodes is not six mild events.
- Imitability audit: extract every physical act performed by the protagonist; classify imitable-dangerous; zero tolerance <= 8, consequence-framing required 9+. This category exists in no off-the-shelf taxonomy; build it.
- Grooming-pattern screen (secrecy from caregivers, isolating adult attention): zero tolerance all bands.
- Choice-surface safety: offered choices are content even when not taken ("steal the medicine" as an option is a decision surface); classify labels, not just outcomes.
- Personalization fuzzing: adversarial names/interests/profile fields through generation; injection success = 0; child PII appears only as intended first-name usage.
- Prompt-injection red team on the request path (embedded instructions, roleplay coercion, encodings): 100% neutralized.
- IP/plagiarism: >= 8-gram overlap vs published children's corpora and own catalog (minus stock phrases) = 0; protected-character/trademark name list = 0 hits.
- Representation: per-book stereotype screen (checklist + judge) and catalog-level distribution of protagonist gender/culture/ability vs stated targets.
- Standing red-team suite per category, refreshed quarterly, plus a mutation of every historical escape; gate: 100% of critical seeds caught before human review; hold out part of the suite from prompt iteration.
- Post-publication: flag rate per 1000 reads trended per pipeline version; every S0/S1 flag triggers incident review naming the gate that should have caught it.
- Recall drill quarterly: pull a published book from all surfaces, including offline/downloaded copies, within SLA.

**Guard**
- Adult-content taxonomies mis-scoring children's genre staples (villains, peril, mild scares) in both directions; calibrate on children's literature and kid-normed fear data (section 10).
- Overblocking to blandness: track excitement/vitality of approved books quarterly next to safety FP rate.
- Node-level scanning missing cumulative dread and cross-node meaning shifts.
- Safety validated only on the current model's failure distribution; full red-team rerun on any model change.
- Reviewer rubber-stamping (see section 15); static red-team set memorized by prompt iteration.

## 8. Coherence across reconverging paths

**Questions**
- After a merge, does shared text contradict any inbound branch: items, injuries, companions, knowledge, location, time, promises, emotional state, alive/dead?
- Does shared text stay specific and natural for every inbound path, instead of lowest-common-denominator mush?
- After any edit to one node, do all paths through it still hold?

**Measure**
- Fact ledgers per path (entities, possessions, injuries, relationships, time-of-day, knowledge, promises); at each junction, test node text against every inbound ledger via NLI/judge: hard contradictions = 0, soft awkwardness < 2 per book.
- Junction pair audit: enumerate (reconvergent node x immediate predecessor) pairs; 100% judged in sequence; coverage-set pairs read by a human; blocking contradictions = 0.
- Full-path reads over the coverage read-set (all edges + all junction pairs, section 2); per-path coherence rubric >= 4/5.
- State-prose parity: every prose-asserted state change has a matching flag and vice versa ("you use the rope you found" with no rope acquisition = automatic S1).
- Referent hygiene: no pronouns or definite references in shared nodes whose antecedents exist only on some branches; automated resolution check.
- Temporal/spatial lint: day-night monotonic per path unless narrated; location transitions checked against a scene adjacency map.
- Junction specificity score: junction-node concreteness must not sit significantly below non-junction nodes (detects vague convergence writing).
- Long-range checks: ledgers persist over the whole path so a node-3 setup contradicted at node 40 is caught, not just adjacent-node conflicts.
- Edit regression: any node edit auto-triggers re-validation of all paths and junction pairs through it; tooling-enforced, never memory-enforced.

**Guard**
- Golden-path-only review; contradictions live on rare paths, which is why edge and junction-pair coverage is mandatory.
- Lossy ledger extraction missing the contradicting detail; validate extraction itself on seeded contradictions.
- Whack-a-mole: fixing one inbound path breaking another; junction fixes re-test all pairs.
- Fact-only checking that ignores emotional continuity (the friend who betrayed you is chummy after the merge).

## 9. Reader experience

**Questions**
- Do kids finish, return, re-read, and choose deliberately? Where do they stall, quit, or get confused?
- Do kids attribute outcomes to their choices (agency), and are endings satisfying wherever reached?
- Do choices produce paralysis, random tapping, or engagement, by band?

**Measure**
- Telemetry per band: completion rate (calibrate; ~>= 70%), abandon-point heatmaps by node, dwell time vs node word count (anomalies localize confusion), session length vs attention norms, 7-day return, re-read rate, endings explored per reader.
- Choice behavior: per-node pick entropy (near-zero on many nodes = dominated options or label failure), decision latency by band (instant = tapping, very long = paralysis), measured position bias.
- Kid-appropriate in-app instruments: again-again ("read another like it?") as primary, smileyometer secondary (expect ceiling effects under 7; use comparatively only).
- Agency attribution probe in playtests: "why did the story end that way?"; majority choice-attribution by 6-8.
- Frustration audit: unfair-end complaints, backtrack loops, restarts-without-finishing per book.
- Guardian-side (3-5 especially): co-read enjoyment, "would assign another" as revealed preference, complaint rate; kept separate from kid measures.
- Comparative anchor: engagement of generated books vs a small set of human-authored branching books in-product; parity target.
- Signal validation: each telemetry signal's meaning verified once against observed sessions before anyone acts on it.

**Guard**
- Novelty inflation: measure at weeks 3-6; exclude each family's first session (app-onboarding confound).
- Optimizing completion into blandness (Goodhart); pair engagement with craft panel and excitement scores.
- Cross-band aggregation hiding a failing band; always stratify.
- Beta-population skew (employee kids, bookish early adopters); recruit for range or weight.

## 10. Real children versus proxies

**Questions**
- Which constructs are only valid from kids: fun, humor, fear threshold, comprehension, choice-label understanding, agency feeling, stamina, re-read pull, usability?
- Which proxies are acceptable, at what measured fidelity, for everything else?

**Measure**
- Evaluation ladder with calibrated proxies: automated -> LLM judge -> adult experts -> guardian proxy -> moderated kid playtests -> in-product telemetry; each tier's agreement with the tier above is a tracked number; retire any proxy whose correlation with kid truth is weak (r < ~0.4) for its construct.
- Standing family panel: 20-60 families spanning bands, reading levels, demographics, neurodiverse readers; rolling weekly sessions (4-6 kids) beat rare big studies; rotate ~25% quarterly against professional-tester drift; re-band kids as they age.
- Methods by age: 3-5 observed guardian co-reading, affect coding, pointing tasks; 6-8 again-again, picture-supported comprehension, brief think-aloud; 9-12 think-aloud, retell, diaries; 13-16 standard UX interviews (guard social desirability).
- Comprehension protocol: structured retell + 3-5 causal questions + one branch-awareness question ("what if you had picked X?"); these scores are the ground truth that validates readability instruments.
- Fear calibration study: kids and guardians rate graded scary excerpts; build per-band norms; map automated safety thresholds to kid-normed data, not adult guesses.
- Adult-kid correlation audit: measure how well experts/parents predict kid fun, humor, scariness; publish internally where adults are unreliable and stop using them there.
- Ethics: guardian consent + child assent, session caps, right to stop, kids only ever see human-approved books (experimental variation happens inside the approved space), data minimization, no kid free-text into third-party LLMs, internal IRB-style review for new protocols.
- Ecological validity: prefer at-home reading with telemetry + diary; lab only for think-aloud/usability.
- LLM "kid simulators": hypothesis generators and test-case finders only; never gates; outputs labeled unvalidated.

**Guard**
- Adults over-sanitizing (kids enjoy mild fear) and under-detecting boredom; both directions verified empirically.
- Acquiescence and pleasing-the-adult bias; prefer behavioral and forced-choice instruments over verbal reports.
- Blending guardian and kid ratings into one number (different constructs).
- Sibling contamination and panel staleness; randomize and recruit at family level.
- One big study amortized forever while the pipeline changes weekly.

## 11. Judge design (human panels and LLM judges)

**Questions**
- Which decisions may an LLM judge gate alone, which need humans, which need both?
- How is every judge blinded, calibrated, agreement-monitored, versioned, and drift-watched?

**Measure (human panels)**
- Role-matched recruitment: editors for craft, teachers/librarians for band fit, child-development/trust-and-safety for safety, parents for family-values fit, kids for fun.
- Anchored rubrics with exemplar excerpts at every score point; onboarding calibration, qualification test, quarterly recalibration.
- Blinding: condition, model identity, pipeline version, and hypothesis hidden; randomized item order; A/B positions counterbalanced.
- Reliability instrumentation: duplicate items (intra-rater), overlapping assignments (inter-rater weighted kappa >= 0.7 on gating dimensions, >= 0.6 provisional), gold attention checks, fatigue caps (<= 90 min), drift dashboards.
- Aggregation: >= 2 raters per gating item plus adjudication; pairwise forced choice + Bradley-Terry for pipeline comparisons (more sensitive than Likert); report full score distributions, since bimodal love/hate is signal, not noise.

**Measure (LLM judges)**
- Dimension-decomposed prompts with structured output and mandatory quoted evidence spans; no single holistic score.
- Bias controls: A/B position swap with required consistency, length-controlled comparisons, judge model family different from generator family (self-preference), no metadata that leaks the hypothesis.
- Determinism: temperature 0/fixed seeds or k=3-5 median; pinned model snapshot; all raw judgments stored.
- Trust boundary: an LLM judge may hard-gate only dimensions where its agreement with the human golden set reaches human-level kappa (>= 0.7) and stays there on weekly canaries; otherwise it is advisory/routing only.
- Cascade design (cheap screener -> strong judge -> human): measure end-to-end FN of the cascade, not per-stage stats.
- Canary monitoring: fixed canary books re-judged weekly; shifts beyond control limits freeze judge-gated decisions (catches silent upstream model updates).
- Contamination guards: judge never sees generation rationale, skeleton annotations, or intended answers; account for human-authored comparison books existing in judge pretraining.

**Guard**
- Same-family judge blessing its sibling generator.
- Rubric authored solely by the prompt author (shared blind spots); outside review of rubrics.
- Human panel as decoration: agreement never actually computed; disagreements silently averaged away.
- Likert score compression making everything a 4; use pairwise when sensitivity matters.

## 12. Validating the measurement instruments themselves

**Questions**
- For each instrument: what construct does it measure, against what ground truth, on what distribution, with what known exploits, and when does its validity expire?

**Measure**
- Golden sets per instrument: stratified across bands, topics, and the full quality range including deliberately bad and borderline items; independent double human labels + adjudication; >= 50-100 items per decision boundary; written labeling guide.
- Agreement/discrimination stats: kappa or Krippendorff alpha vs human truth (>= 0.6-0.7 to gate), PR-AUC and confusion matrices for classifiers, operating points chosen on held-out data, calibration curves with ECE reported.
- Criterion validity: proxy vs downstream truth (readability score vs measured kid comprehension; engagement proxy vs observed completion; diversity metric vs human same-book labels); the correlation is tracked, not assumed.
- Convergent/discriminant validity: metrics of the same construct correlate; unrelated metrics do not (mini multitrait-multimethod matrix).
- Seeded-defect testing of the eval (mutation testing the gates): maintain a defect-injection library (dangling edge, junction contradiction, over-band vocabulary, imitable-dangerous act, cliche flood, re-skinned clone); every gate catches >= 95% of its target class and fires on <= 5% of clean controls; rerun on every validator change.
- Gameability audit: adversarially optimize text against each metric (short-sentence trick, synonym laundering, tell-word avoidance); document exploits and add counter-checks.
- Stability: same book judged k times; judge SD must be under half the smallest delta used in decisions, else average more samples.
- Transfer revalidation: every new generator model shifts the failure distribution; golden sets get refreshed and instruments re-validated; each instrument carries an expiry date.
- Shadow mode: every new gate runs non-blocking 2-4 weeks; compare would-block decisions against human outcomes before arming.
- Gate ROI: periodic ablation of each gate's unique catch rate vs cost and FP burden; retire freeloaders; track per-gate overturn/appeal rate (> 20% overturns = recalibrate).

**Guard**
- Circular validation (judge validated against labels produced by the same or sibling model).
- Threshold chosen on the same data it is reported on (leakage).
- Validation only near the pass boundary (range restriction) or only on clean data.
- Corpus-level validity misused for per-book gating (ecological fallacy).
- Imbalanced-class kappa misread; per-class agreement required.

## 13. Statistical rigor for small-n experiments

**Measure / practice**
- Pre-registration for every experiment, even as a one-page internal doc: hypothesis, exactly one primary metric, MDE, n with power calculation, exclusion rules, analysis method, stopping rule, and the decision each outcome triggers; deviations logged. Telemetry analyses also pre-declare metrics (no HARKing on dashboards).
- Unit discipline: the child (usually the family) is the unit; randomize at family level (siblings contaminate); nodes, sessions, and books within a child are repeated measures, never independent n.
- Power rules of thumb: within-subject d=0.8 at 80% power needs ~15 pairs; between-subject ~26 per arm; smaller effects need far more; if the panel cannot power the MDE, run large-n judge proxies first and use kids only to confirm large effects.
- Prefer within-subject counterbalanced designs (each child reads both variants; Latin-square order; matched or randomized topics; washout between sessions); beware carryover (variant A changes expectations for B).
- Censoring: distinguish observed abandonment (an event) from not-yet-finished at cutoff (censored); use survival analysis (Kaplan-Meier, log-rank, Cox) for completion/abandonment; never naive completion % over an incomplete window; adjust for length-biased censoring (long books censor more).
- Attrition: report it, test for differential attrition between arms (a variant that drives dropouts can look better), analyze intention-to-treat.
- Small-n inference: permutation/exact tests and bootstrap CIs over asymptotics; Bayesian posteriors with ROPE for go/no-go at tiny n; always effect size + CI, never bare p; every null result reported with its MDE.
- Clustering: mixed models with random effects for child, family, book, skeleton, topic; report ICC and design effect; cluster-robust errors at minimum.
- Multiplicity: one primary metric; Holm/BH for the secondary dashboard; exploratory findings labeled exploratory.
- Sequential looks only under alpha-spending or Bayesian sequential rules; no ad-hoc peeking.
- Confound checklist per study: age, reading skill (short fluency pre-test as covariate), topic preference, novelty (>= 3 weeks), order, device, guardian involvement, time-of-day, first-session onboarding.
- Regression-to-mean guard when iterating on the worst books: re-measure untouched control books over the same period.
- Simpson's guard: pre-registered band-stratified analysis; never pool bands without checking per-band signs.
- Judge-based experiments get the same discipline: paired per-request deltas, request-level clustering, CIs.

**Guard**
- Pseudo-replication (nodes/sessions counted as n) is the single most common error.
- Survivorship (finishers-only analysis).
- Underpowered nulls read as "no difference".
- Metric shopping across 30 dashboard metrics after the fact.

## 14. Regression testing as models and prompts change

**Measure / practice**
- Change one class at a time: never change generator and judge in the same release; full lineage (section 1) makes attribution possible.
- Frozen benchmark: fixed request set spanning bands x topics x difficulty, plus every historical escape as a permanent regression case ("no bug fixed without a test that would have caught it"); versioned; composition re-synced to the live request mix quarterly.
- Two tiers: smoke suite on every prompt/config change (structural validators + cheap judges on ~20-50 books, minutes); full suite nightly/weekly (hundreds of books, full cascade, cost/latency report).
- Paired comparisons: same request through old and new pipeline; per-request deltas with CIs; non-inferiority gates per dimension (safety FN: zero tolerance; craft: within stated margin; cost: within budget); no dimension silently traded away.
- Judge-change crosswalk: when a judge changes, re-score a fixed human-labeled archival anchor set under both judges and publish the mapping; human labels are the invariant star across years.
- Pipeline variance as a metric: same request k times; report quality variance; a pipeline whose variance widens fails even at equal mean (predictable unit cost requires predictable quality).
- Shadow and staged rollout: new pipeline shadows real requests; blinded human old-vs-new comparisons; canary one band, then widen; rollback rehearsed.
- Production drift watch: fixed probe requests regenerated weekly through the live pipeline; control charts (CUSUM) alarm without any deploy (catches silent upstream API updates); pin model snapshots wherever the provider allows.
- Catalog back-scan: improved validators re-scan the published catalog; explicit policy for re-review/recall thresholds on old books.
- Holdout hygiene: holdout touched only at release gates; exposures logged; holdout refreshed periodically because holdout burn is real.
- Quality, cost, and latency reported together per release: cost per accepted book including rejects, retries, and human minutes; p50/p90.

**Guard**
- Benchmark overfitting through repeated iteration.
- Aggregate parity hiding mix shift (easy topics improved, hard ones degraded); always slice by band, topic, length, skeleton.
- Judge drift booked as generator regression, or masking one.
- Cross-time comparisons with unpinned decoding params or silently updated APIs.

## 15. Production monitoring, escapes, and testing the human gate itself

- Escape-rate north star reported monthly with a severity Pareto; every S0/S1 escape gets a blameless postmortem answering "which gate should have caught this" and ships a new seeded defect + regression case.
- Reader-facing feedback instrumented: parent flags, kid dislike taps, support tickets; triage SLAs; flag rate per 1000 reads trended per pipeline version.
- The human-approval gate is a measured instrument: seeded defects injected into the review queue (catch rate >= 90-95% for S0/S1), inter-reviewer agreement sampling, time-per-book floor alarms (rubber-stamp detection), fatigue and drift dashboards, periodic recalibration.
- Review depth is risk-scored (deeper coverage-set reads for risky books) above a guaranteed minimum human read for every book; the risk model is validated like any other instrument.
- Appeals loop: false rejects contested; per-gate overturn rate tracked; > 20% triggers recalibration (protects yield and trust in gates).
- Reviewer disagreements mined as instrument-improvement data, not discarded.

## 16. Cost, yield, and gate economics (the eval must serve unit cost)

- Yield: % of generation attempts surviving all gates to human approval, per band; step-change alarms; falling yield is a cost blowup in disguise.
- Regeneration loops per accepted book (p50/p90) capped and reported; runaway retry loops are a silent budget leak.
- Human minutes per accepted book by band; coverage read-set size (section 2) drives this, so structural choices (reconvergence rate) have measurable review-cost consequences.
- Cost per accepted book (LLM + eval compute + human time): predictability target p90 <= ~2x median.
- Gate ordering: cheap high-catch gates first; maintain the cumulative catch vs cumulative cost curve; re-order quarterly.
- Words generated vs words a reader experiences per read: branching multiplies cost per experienced word; budget this ratio per band.

## 17. Special surfaces most programmes forget

**Personalization (if names/interests are injected)**
- Mad-libs test: strip personalization tokens; if nothing else changes, personalization is cosmetic; state the intended bar and measure weaving depth.
- Fuzz unusual names (apostrophes, diacritics, very long, ambiguous gender): 0 grammar/pronoun/rendering breaks.
- Profile constraints honored (known fears, exclusions): seeded-profile tests, 0 violations.

**Series and recurring characters**
- Series canon ledger (traits, relationships, world rules); cross-book contradiction checks at series scope: 0 hard canon breaks.
- Character voice drift measured across books; intended progression distinguished from drift by the series plan.
- Out-of-order readability per policy; recap quality checked.

**Covers/illustrations (if AI art)**
- Cover-book fidelity (cover depicts entities actually in the book), age-appropriate imagery gate, uncanny/artifact screen, series style consistency, alt-text quality; human approval explicitly includes the cover.

**Audio/TTS read-aloud (if present)**
- Pronunciation lexicon for invented names; stumble rate; screen-reader operability of the choice UI.

**Localization and accessibility**
- Dialect consistency; on translation, all evals re-run per language (readability formulas do not port across languages, nor do thresholds).
- Dyslexia-friendly rendering checks; text fits smallest and largest supported screens.

## 18. Governance and ethics of the eval programme

- Metric registry: every metric has an owner, definition, unit, threshold, validation status and expiry date; dashboards read only from the registry (no orphan metrics).
- Change control: gates and thresholds change via reviewed proposal with evidence, never a config hotfix.
- Incentive separation: at least one reviewer of eval design does not own generation-quality goals.
- Kid data ethics in measurement: minimization, aggregation, retention limits, consent boundaries honored in analysis, no child data to third-party services without scrubbing.
- Written blind-spot statements: every gate documents what it is known NOT to catch, so gaps are chosen, not discovered.

## The 10 mistakes teams most often make here

1. Path-blindness: evaluating nodes in isolation and never reading full paths, so contradictions at junctions, cumulative dread, and rare-path defects ship while every node-level check passes.
2. Trusting unvalidated judges: LLM judges gating without a human golden set, agreement stats, position/length-bias controls, or family separation from the generator; human panels without blinding or measured kappa.
3. Goodharting proxies: optimizing readability formulas, tell-word counts, or completion rate until the proxy detaches from the construct, yielding gamed scores and bland books.
4. Averaging away the tails: reporting book or corpus means when the incident lives in the worst path, the spike node, one failing band, or a bimodal love/hate split.
5. Letting adults guess for kids: using experts and parents for fun, humor, and fear thresholds without ever measuring adult-kid correlation, over-sanitizing and under-detecting boredom.
6. Statistical malpractice at small n: pseudo-replication (nodes/sessions as n), sibling contamination, no pre-registration, peeking, ignoring censoring and attrition, and reading underpowered nulls as "no difference".
7. Burning the benchmark: iterating prompts against the holdout until it is a training set, so the eval flatters the current pipeline and fresh data brings surprises.
8. Confounded change management: changing model, prompts, and judges together with no lineage metadata, so regressions cannot be attributed and judge drift masquerades as quality change.
9. Scoping safety as generic text classification: missing second-person imitability, path-cumulative intensity, grooming patterns, the incentive structure of endings, personalization/injection attacks, and IP exposure.
10. Never testing the tests: no seeded-defect (mutation) testing of gates or human reviewers, no canary monitoring for judge drift, no escape-rate feedback loop, no revalidation after model changes; the eval rots silently while everyone still trusts it.
