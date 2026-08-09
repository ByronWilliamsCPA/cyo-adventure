# Alternatives to the pre-authored skeleton (2026-08-09)

> Status: proposal for testing, not a decision. Owner-requested after the third diversity
> pilot ([skeleton-narrative-redesign-proposal-2026-08-09.md](./skeleton-narrative-redesign-proposal-2026-08-09.md),
> sections 10 to 13) concluded that the residual sameness channels are the skeleton's own
> identity. Grounded in a code survey of the current generation and validation surface;
> file:line citations below are from that survey.

## 1. Why revisit this now

The skeleton exists because of an early finding: given only a story-concept prompt, the
model could not produce acceptable structure and acceptable prose at the same time. The
skeleton removed structure from the model's job so it could spend its whole budget on
prose. That was the right call for the evidence available.

Three things have since changed, and each weakens a premise of that decision.

1. **The original finding was measured against zero-shot, single-call generation.** This
   session repeatedly demonstrated something different: agents with checkers in the loop
   authored a 31-fact narrative contract that passed every NC check first try, authored
   three story bibles that passed the diversity gate first try, and closed a 20.4-to-1.2
   convergence gap in a single tool-feedback revision round with no human repair.
2. **The skeleton is now the binding constraint on quality, not an enabler of it.** Three
   pilots each moved the sameness ceiling one layer down: beats, then contract
   concreteness, then decision grammar. Sibling fills of one skeleton converge to "same
   adventure, new world", and the remaining channels (choice-menu semantics,
   scene-function order) are what the skeleton IS.
3. **Structure work and prose work have different model-tier requirements.** Blind craft
   scores ran 4.9 / 4.0 / 2.2 across frontier, Sonnet, and Haiku while every tier passed
   every structural gate first-pass. Any approach that keeps the two jobs separate can
   serve them with different models, which is what makes OpenRouter substitution
   practical.

## 2. The finding that reframes the question: the skeleton-free path already exists

`generate_story` (`generation/orchestrator.py:635`) is a live, shipped, skeleton-free
pipeline: **Stage A structure, Stage B prose, Stage C bounded repair**, reading no
skeleton. `generation/worker.py:2313-2326` routes to it whenever a job carries
no `skeleton_slug`, and a storybook with `skeleton_slug = NULL` is a first-class database
row (`db/models.py:1399`). The import path does not care where a graph came from
(`generation/import_story.py:110`).

So the real question is not "can we build a skeleton-free approach". It is **"the
skeleton-free path exists and was judged inadequate; what specifically is missing from
it?"** The survey answers that precisely, and the answers are smaller than expected:

1. **It is validated by a much weaker bar than skeletons are.** The strict bar this session
   built (satisfying-walk floors, max-indegree caps, depth-qualified endings) lives in
   `scripts/check_skeleton.py:230-393`, is `--strict`-only, and carries no rule id in the
   validator catalog. **It never runs on generated stories.** Skeletons are held to a
   standard generated stories are not.
2. **Structural targets are bounds, not distributions.** `band_profile.py` gives min/max
   envelopes; the only midpoint anyone picks is `story_requests/brief.py:207`
   (`node_count = round((min_nodes + max_nodes) / 2)`), a one-line heuristic feeding a
   prompt. As the survey put it: the gate will accept a 60-node stick and a 60-node bush
   identically.
3. **Topology is descriptive, not prescriptive.** `validator/topology.py:15` collapses six
   topology labels into three graph-shape classes, each admitting two or more labels, so
   declaring a topology constrains almost nothing. No code anywhere *realizes* a topology.
   The band-vs-topology matrix (`mutation/identity.py:84-121`) is enforced only by the
   offline mutation layer, never by the gate.
4. **It has never had fidelity checking.** `orchestrator.py:749-752` passes `stage1=None`,
   so the "did the model quietly rewrite the structure" assurance that the skeleton path
   gets from diffing against its pre-fill reference simply does not exist here.
5. **There are no per-node word targets at construction time.** The skeleton path carries
   `words=N` inside each FILL directive, which is what PL-19, PL-23, and CG-3 read before
   prose exists. A generated graph has none, so the word envelope, the estimated-minutes
   clock, and the arc floors all become post-hoc rather than plannable.
6. **The shared armature is not removed by removing the skeleton.** `generation/prompts.py:317`
   and `:354` splice the full 407-line `templates/drafting_guide.md` into BOTH Stage A and
   Stage B on every call. That guide prescribes a fan-out-then-converge default and carries
   a per-band choice-grammar table fixing options-per-choice (three, at 10-13). Pilot 2's
   verdict was that "the obligation contract is itself a shared prompt across every fill,
   and anything concrete in it becomes the new frozen armature"; the drafting guide is a
   larger and more concrete shared prompt than any contract, and it mandates by table the
   very decision grammar the raters named as the recognition driver. **Every arm below still
   runs through these prompts, so none of them removes the channel that failed the margin.**
7. **The differentiation machinery is skeleton-only.** `story_requests/authoring_plan.py`
   builds the anti-repetition directive (axis selection, prior titles, prior theme tags)
   inside the `skeleton_fill` branch; `generate_story` takes no differentiation parameter at
   all. The control arm receives anti-repetition help the treatment arms do not, which is an
   arm-level confound in any diversity comparison.

**This makes the cheapest and highest-value experiment obvious, and it is not on the
original list**: run the existing `generate_story` path and score it on the full pilot
bench plus the strict bar. Either it is far closer than believed, or we get an exact,
itemized defect list for a fraction of the cost of building anything. That experiment is
now step 1 in section 8.

## 2b. The exposure question, and why it may retire this program

Owner correction, 2026-08-09: **the unit of exposure is the child, not the family.**
Recognition is a property of one reader's memory. Two children in the same household can
each read a story built from the same skeleton, once each, and neither experiences a
repeat. Any measurement or selector logic scoped to the family is measuring the wrong
thing.

That correction produces the economic asymmetry this whole program should be judged
against:

> **A skeleton is consumable within a child and reusable across children.**

If unique content is effectively one run per skeleton per reader, then the catalog must be
large enough to serve **one child's lifetime consumption inside a band**, and it does not
have to grow with the number of children. Catalog size therefore scales with per-reader
demand, which is bounded by tenure (a child sits in 10-13 for roughly three years) and
reading rate, rather than with business growth. **That makes "build more skeletons" a
bounded, one-time capital cost, and it competes directly with replacing the architecture,
which is an unbounded engineering cost that also forfeits the personalization and
denylist properties recorded in section 10.**

Two consequences follow immediately.

1. **The catalog needs heavy weighting toward the middle bands.** Required skeletons per
   band is a function of tenure in that band and reading rate inside it. The middle of the
   age range carries both the longest independent-reading tenure and the highest volume,
   so a flat per-band catalog is the wrong shape. The current catalog is roughly flat, and
   the production cells at 10-13 hold three to four candidates each.
2. **Family-scoped history is an architectural mismatch, not just a measurement one.** The
   anti-repetition machinery reads `load_family_history` (`diversity/history.py`), which is
   family-scoped with a window of 20 and carries only a theme signature, no skeleton
   identity. If that is the only history the selector sees, then a household with K
   children burns the recency window K times faster, degrading protection for each child,
   while simultaneously penalizing skeletons a given child has never read, wasting catalog
   that child could still consume. Both failure modes point the same way: **per-reader
   skeleton history is likely a prerequisite for any catalog-scaling answer, and it is a
   much smaller build than any arm in section 6.**

**This is the measurement that should gate the entire program**, and it costs no
generation tokens: the per-child repeat curve under the shipping selector, the catalog size
per cell required to push a child's first repeat past their Nth story, and the per-band
weighting that implies. If the answer is that a child hits a repeat on their second or
third story, the recognition finding is a product emergency and the alternatives are
warranted. If the answer is that a bounded catalog build clears it, this document describes
work that should not be funded.

Note also that every recognition score in pilots 1 to 3 came from a rater holding two books
at once and instructed to look for sameness. The product condition is one child, one book,
days apart, with no reference copy. Section 13 of the companion document already measured
that comparative judgments are systematically harsher than isolated ones, and applied that
caution to craft but never to recognition, where it bites harder because recognition is
definitionally comparative. The measured landing nodes are therefore an upper bound on the
defect as experienced.

## 3. What the skeleton actually buys

The skeleton does **not** guarantee validity. The gate does. The gate is agnostic to
story *provenance*: `run_gate` (`validator/gate.py:86`) accepts raw decoded story JSON, no
slug, no path, no lineage; it performs no filesystem I/O; and the skeleton-coupled checkers
(`validator/slots.py`, `sentinel_integrity.py`, `theme_leak.py`) are not called by it.

It is **not**, however, agnostic to skeleton *format*, and an earlier draft of this
document overstated that. `validator/policy.py:67-74`, `choice_grammar.py:81-86`, and
`reading_level.py:51-56` each carry a local copy of the `<<FILL ... words=N>>` grammar:
PL-19 and PL-23 read a skeleton's *declared* word target where they read a generated
story's *actual* words, and RL-13 skips FILL bodies outright. The comment at
`policy.py:71` documents an avoided *import*, not an avoided dependency. Gate strictness is
also caller-parameterized: `enforce_grammar` defaults to False and `worker.py:2326` calls
`generate_story` without overriding it, so **generated stories never run CG-1 through
CG-4** while the skeleton promotion path opts in. Two of the gate's knobs are set
differently for the two paths being compared, so "the gate guarantees validity" cannot
carry the full weight of a cross-path comparison.

One invariant listed below is weaker than it appears: `validator/safety.py:41` is a
Phase-2 stub returning an empty report unconditionally, so SAFE-14 cannot produce a
finding and every "zero safety flags" result in pilots 1 to 3 and the model-tier study
carries no information. The real deterministic pre-LLM denylist floor on untrusted
brief-derived material is `validator/slots.py`, whose only caller is the theme-binding
path, which means it runs for skeleton fills only. A skeleton-free story has no pre-LLM
denylist gate, only the post-hoc moderation pipeline.

What the skeleton actually provides is threefold:

- **Cognitive offload.** The model never holds a 26-node graph in its head.
- **Amortized human verification.** One reviewed artifact serves many books.
- **Predictable envelope.** Node count, depth, and clock are known before generation.

Only the first is a capability claim, and it is the one the evidence puts in doubt. The
second is a cost optimization rather than a safety property, because ADR-005 requires
human approval of every finished story however it was built. The third is recoverable:
`mutation/identity.py:535 resync_metadata` already derives `ending_count`, `tier`,
`estimated_minutes`, and `topology` from a freshly built graph.

**So the question is: what else can take structure off the model's plate, or make the
model able to carry it.**

## 4. Invariants every alternative must preserve

All are already enforced by code that does not care about skeletons:

- The deterministic gate (Layer 1, policy, Layer 2, character, reading level, choice
  grammar), unblocked, zero safety flags.
- Band profile budgets: node counts, depth, word envelopes, ending economy, arc floors.
- The safety envelope and the moderation pipeline.
- Mandatory human approval before publication (ADR-005).
- Reachability, termination, no trap loops, valid ending kinds and valences, condition and
  effect coherence.

## 5. Taxonomy: five ways to stop asking one call to do both jobs

| Strategy | Structure comes from | When it is fixed |
| --- | --- | --- |
| **Pre-commit** (current skeleton path) | human-authored catalog | before the request |
| **Sequence** (current `generate_story`) | a dedicated generation stage | per request, before prose |
| **Externalize** | a deterministic program | per request, before prose |
| **Iterate** | model plus gate feedback | during prose |
| **Invert** | a parse of linear prose | after prose |

Note that the first two cells are both already implemented. The alternatives below either
strengthen the Sequence cell or occupy the three empty ones.

## 6. The alternatives

### A1. Harden the existing Stage A (Sequence, incremental)

**Mechanism.** Keep `generate_story` and fix the five specific defects in section 2:
promote the strict-bar fitness functions from `scripts/` into library code and apply them
to Stage A output; give Stage A a structural target *distribution* rather than a midpoint;
add per-node word targets at construction; add a Stage A-to-Stage B fidelity diff (the
same assurance the skeleton path gets, using Stage A's own output as the reference, which
costs nothing because the artifact already exists).

**What it fixes.** Unknown, and an earlier draft of this document was wrong to claim it
fixes sibling recognition entirely. Removing the skeleton moves the shared authoring prior
into `drafting_guide.md` (gap 6), which prescribes the same decision grammar the pilots
identified. It reuses a pipeline already wired and routed in production, but on the
diversity axis it is the largest change in the set rather than the smallest, because it
must also build a differentiation path, a fidelity reference, per-node word targets, and a
structural target distribution.

**What it risks.** We have observed convergence at every layer we have measured, so
**expect Stage A to have its own structural priors**: three generated graphs may rhyme the
way three bibles did. This must be measured with `diversity/structure.py`'s
`structural_distance`, not assumed.

**Model tier.** Structure authoring is the job an agent already did first-pass green in
this session. Needs testing at Sonnet and below.

**Build cost.** Smallest in the set. Mostly promoting existing script code to library code
and rule-ising its thresholds.

### A2. Structural grammar sampler (Externalize)

**Mechanism.** A deterministic program constructs a graph satisfying band-profile budgets
*by construction*: sample topology class, node count, per-node arity, merge points, depth,
and ending economy from ranges the validator already encodes. No LLM in structure at all.

**What it fixes.** Structural failure goes to approximately zero. Variety is unbounded, and
critically **arity and order vary per story**, which is exactly the fix the recognition
rater proposed when it observed that readers compare menus rather than prose. Structure
costs no model tokens.

**What it risks.** Valid is not the same as good: a sampler will emit graphs that satisfy
every budget and that no author would design. The survey sharpens this: because
`admissible_topologies` recognizes only three shape classes, and nothing realizes a
topology, "sample a topology" has no implementation to lean on and the narrative-shape
priors are the whole job, not a tuning pass.

**Model tier.** Lowest of any alternative; the model only writes prose. **Best OpenRouter
portability by a wide margin.**

**Build cost.** Moderate for the sampler; the priors are the hard part. Reusable
scaffolding exists (`mutation/subtree.py` predicates, `identity.resync_metadata`,
`mutation/acceptance.py`'s stage ladder), but the survey is blunt that `mutation/` is a
perturbation engine, not a generator: M1 and M2 are shape-preserving by design, M3 grafts
from donor skeletons, and only M4 mints nodes, one edge-split at a time, so it can never
produce novel global topology.

### A3. Gate-in-the-loop free growth (Iterate)

**Mechanism.** No pre-committed structure. An agent grows the storybook incrementally with
the validator and checkers as live tools, gating after each addition and repairing on
failure.

**What it fixes.** Tests the founding assumption directly. Structure follows story rather
than story being poured into structure.

**What it risks.** Cost and non-termination, plus degenerate optimization: an agent whose
fitness function is the gate will find shapes that pass without being good stories, the
same lesson the revision round taught in miniature when Haiku satisfied an n-gram check
with word swaps. **A hard architectural constraint the survey surfaced:** the production
provider protocol (`generation/provider.py:255`) is a single `complete(system, prompt,
max_tokens) -> str` method with no tool use, no structured output, no streaming. A3
therefore cannot run through the production abstraction at all without extending it; it
can only run as an out-of-band agent harness like the ones used in this session.

**Model tier.** Highest; worst portability.

**Value.** Highest information content: it retires or accurately re-measures the founding
constraint.

### A4. Spine-then-branch (Sequence, narrative-first)

**Mechanism.** Pass 1: the model writes a linear story, its strongest and most universal
mode. Pass 2: identify genuine decision points in *that* story and fork them. Pass 3:
write the divergent consequences. Pass 4: gate and repair to fit the envelope.

**What it fixes.** **The only alternative that attacks the recognition finding at its named
root cause.** Both raters independently identified choice-menu semantics as the
fingerprint: the same options, with the same meanings, in the same order, at every fork.
When choices derive from a specific story rather than a reused graph, menus differ because
the stories differ. It also answers the "the skeleton is visible" critique, since scene
functions are no longer pinned to fixed positions.

**What it risks.** Hitting exact node and ending-economy budgets is hard when structure
emerges from narrative; expect a fitting or repair pass, and expect some briefs to fork
poorly. Branch explosion needs explicit control.

**Model tier.** Moderate; linear narrative is the most universal LLM capability, so
portability should be good.

**Build cost.** Moderate: a fork-identification stage plus budget-fitting repair.

### A5. Prose-first extraction (Invert)

**Mechanism.** The model writes a branching narrative in lightweight authoring markup
(headed sections with explicit choice links, in the spirit of Twine or Ink); a
deterministic parser converts it to Storybook JSON; the gate validates.

**What it fixes.** Removes the entire JSON-emission burden. Emitting a well-formed 26-node
graph with correct ids, targets, conditions, and effects is exactly what mid-tier models
fail at, and it is unrelated to whether they write good children's prose.

**What it risks.** Parse failures and invalid link graphs; needs a strict parser with a
forgiving repair path.

**Model tier.** Low. **Probably the best fit for cheap OpenRouter models**, and orthogonal
to the others, so it composes with any of them.

**Build cost.** Moderate: markup spec, parser, repair. High reuse value regardless of which
structural approach wins.

### A6. Structure-as-attractor repair (Iterate, post-hoc)

**Mechanism.** Generate freely, then let a deterministic repair stage snap the graph toward
validity (add a missing ending, merge a dead end, prune over-arity) rather than rejecting
the artifact.

**What it fixes.** Makes failure cheap, which is what makes weak models viable.

**What it risks.** Prose-graph divergence: a repaired edge whose prose no longer matches
it. Repairs must be prose-aware or must trigger re-fill of the nodes they touch.

**Build cost.** Moderate; note that Stage C already implements a bounded repair loop with
no-progress detection (`orchestrator.py:242`), so this is an extension rather than a new
mechanism.

### Controls

- **A0. Current skeleton path.** The baseline, with pilot measurements already in hand.
- **A0b. Current plus per-binding arity and order variation.** Not skeleton-free; included
  as a *diagnostic*. It isolates whether varying branch arity and scene order alone moves
  the recognition landing node. If it does, A1 and A2 gain a lot of value; if it does not,
  the driver is scene-function order and A4 becomes the only real fix.

## 7. Combinations worth testing as single arms

- **A2 + A5** (program builds the graph, model writes marked-up prose, parser assembles):
  the strongest portability pair and the natural candidate for cheap OpenRouter models.
- **A4 + A6** (spine-then-branch with repair fitting): the strongest narrative-coherence
  pair, and the one most likely to beat the recognition margin.

## 8. The bake-off

The measurement bench already exists, which is why this is testable now.

**Deterministic**: fill integrity where applicable; full gate (blocked, safety flags,
findings mix); reading-level distribution; band-profile compliance; sibling shared grams
per 1000 and menu-frame overlap; title compliance; PS, leaf similarity, Mechanic
Divergence.

**Structural variety**: `diversity/structure.py` already provides `structure_fingerprint`,
`structure_features`, and `structural_distance` as public library code. This corrects an
earlier draft of this document, which claimed a new instrument was required; it is not,
though the strict-bar fitness functions in `scripts/check_skeleton.py` do need promoting to
library code (gap 3 in section 2) before they can score generated graphs.

**Rater-based** (blind, comparative, using rubrics already written): the six-dimension
craft rubric with a ship verdict; scene-inventory device distinctness; recognition landing
node plus the five-point score.

**Cost**: tokens and wall-clock per book, plus the lowest model tier that passes.

**Pre-registered margins**, anchored to measurements in hand:

| Outcome | Margin | Current skeleton path |
| --- | --- | --- |
| First-pass gate not blocked | 3/3 | 3/3 (met) |
| Strict bar (walk floors, indegree caps, depth-qualified endings) | see note | **2 of 61 catalog skeletons pass; 0 of 11 at 10-13** |
| Blind craft mean | >= 4.0 (the shipping bar) | 4.9 frontier, 4.0 Sonnet |
| Recognition landing | past the hub node, or no landing | FAILED twice (node 2, node 4) |
| Sibling grams per 1000 | <= 4.0 after at most one revision round | 1.2 (met) |
| Cost per book | <= 2x current | baseline |
| Portability | passes at Sonnet | passes at Sonnet |

Recognition is the margin that matters: it is the only one the current approach fails, and
an alternative that matches everywhere else while still failing recognition has bought
nothing.

**Two margin rows are known defective and must be rebuilt before use.** The strict-bar row
cannot be a pass/fail margin when the shipped catalog meets it 2 times in 61 (measured
2026-08-09 across all bands, 0 of 11 at 10-13). That bar gates *newly drafted* skeletons
only; the catalog is grandfathered (`scripts/check_skeleton.py:63-66`). Promoting it to a
blocking library rule would retire 97% of the catalog, which is a product decision, not a
scoring prerequisite. Separately, "safety flags" must be struck from the bench entirely
(SAFE-14 is a stub, see section 3), and the "portability = passes at Sonnet" row conflicts
with this project's own conclusion that gate-clean is not publishable.

**The baseline anchors are also weaker than stated.** Every number in the right-hand column
comes from pilots run on `the-clocktower-cipher`, which is the catalog's single
`(10-13, None, None)` row, is not production-eligible, and is therefore never served to a
child by `skeleton_match`. Because it declares no length and no narrative style it is not
scale-classified, so it is held to band-level budgets rather than the ADR-011 cell budgets
every production 10-13 skeleton faces. Re-baseline on a production-eligible 10-13 skeleton
before pre-registering anything.

**Design**: same request brief across arms, three stories per arm, band 10-13 (where
readers are sharpest and the current approach is weakest), raters blind to arm.

## 9. Recommended sequence, cheapest information first

0. **Compute per-child sibling exposure and the catalog sizing curve** (section 2b). Zero
   generation cost, and it can retire the program outright: if a bounded catalog build
   keeps a child's first repeat beyond their realistic consumption inside a band, no arm
   here is warranted.
0b. **Two-rater reliability on the nine books already in hand.** Also zero generation cost.
   The same arm already produced a node-2 verdict on one pair and a node-4 verdict on
   another, so within-arm spread currently equals the effect size the bake-off is trying to
   detect. Until inter-rater agreement is known, the primary endpoint is unmeasurable and
   every downstream comparison is noise.
0c. **The ceiling control: two fills of two different production-eligible 10-13
   skeletons.** If two entirely different hand-authored skeletons still land recognition at
   or before the hub, then the endpoint is measuring band, rater priors, and the drafting
   guide rather than structure, and no arm can pass the margin by construction.
0d. **The drafting-guide ablation.** Strip the per-band choice-grammar table and the
   fan-out-then-converge section from `drafting_guide.md`, re-run three fills of the pilot
   inputs, re-rate recognition. Three fills, no new code. If recognition moves, the driver
   lives in the prompt and A1, A2, A4, A5, and A6 all inherit it unchanged, invalidating
   five arms at once. If it does not move, the structural framing is vindicated.
1. **Score the existing `generate_story` path** on the full bench. Note that this is
   confounded until 0d resolves (shared drafting guide) and until the differentiation gap
   (gap 7) is closed, so its result is not interpretable in the direction this document
   wants without those.
2. **A0b, the arity diagnostic.** Smallest new experiment; makes every other result
   interpretable.
3. **Promote the strict-bar fitness functions to library code** and give them rule ids.
   Required before any generated structure can be scored honestly, and it closes the
   standing inconsistency that skeletons are held to a bar generated stories are not.
4. **A5, prose-first extraction.** Reusable by every other arm and the most direct answer
   to the OpenRouter substitution goal, so its value does not depend on winning.
5. **A2 and A4 in parallel.** The two strongest candidates on different axes: A2 for
   portability and cost, A4 for beating the recognition margin.
6. **A3 last.** Most expensive, blocked on extending the provider protocol, and its job is
   to retire or re-measure the founding assumption rather than to win the bake-off.

## 10. What would be lost, stated honestly

Dropping the catalog gives up amortized human verification of structure, a small auditable
set of artifacts, and a known length envelope before generation begins. The first is
mitigated by ADR-005's mandatory human approval of every story; the second is a real loss
in reviewability that per-request validation only partly replaces; the third is recovered
by `resync_metadata`.

Two costs are larger than they first appear and belong in any decision:

- **Personalization is skeleton-coupled today.** The slot-and-sentinel system is
  contract-sidecar driven (`generation/binding.py`, `storybook/sentinels.py`,
  `validator/slots.py`, `validator/sentinel_integrity.py`), and `personalization_eligible`
  is computed from the sentinel manifest at import (`import_story.py:188`). A
  skeleton-free story is `personalization_eligible = False` by construction unless an
  equivalent slot-declaration mechanism is built. This is a product regression, not a
  pipeline detail.
- **Anti-clone diversity baselines are catalog-rebased.** `mutation/floors.py` measures
  candidates against the in-cell committed catalog, and `skeleton_match._blended_weight`
  does anti-repetition at selection time. With no catalog the reference set becomes the
  corpus of previously generated stories; `diversity/history.py` and `diversity/query.py`
  already query the database, so this is a rebase rather than a build.

Finally, the catalog remains the right answer for one case the alternatives do not serve:
a deliberately marketed series, where a shared armature is a feature the reader is buying
on purpose rather than a defect discovered on night two.
