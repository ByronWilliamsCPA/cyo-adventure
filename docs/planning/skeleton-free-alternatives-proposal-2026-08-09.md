# Alternatives to the pre-authored skeleton (2026-08-09)

> Status: proposal for testing, not a decision. Owner-requested after the third diversity
> pilot ([skeleton-narrative-redesign-proposal-2026-08-09.md](./skeleton-narrative-redesign-proposal-2026-08-09.md),
> sections 10 to 13) concluded that the residual sameness channels are the skeleton's own
> identity.

## 1. Why revisit this now

The skeleton exists because of an early finding: given only a story-concept prompt, the
model could not produce acceptable structure and acceptable prose at the same time. The
skeleton removed structure from the model's job so it could spend its whole budget on
prose. That was the right call for the evidence available.

Three things have since changed, and each of them weakens a premise of that decision.

1. **The original finding was measured against zero-shot, single-call generation.** This
   session repeatedly demonstrated something different: agents with checkers in the loop
   authored a 31-fact narrative contract that passed every NC check first try, authored
   three story bibles that passed the diversity gate first try, and closed a 20.4-to-1.2
   convergence gap in a single tool-feedback revision round with no human repair. The
   founding constraint was measured on a system we no longer run.
2. **The skeleton is now the binding constraint on quality, not an enabler of it.** Three
   pilots each moved the sameness ceiling one layer down: beats, then contract
   concreteness, then decision grammar. The final verdict was that sibling fills of one
   skeleton converge to "same adventure, new world" and no downstream hygiene changes
   that, because the remaining channels (choice-menu semantics, scene-function order) are
   what the skeleton IS.
3. **Structure work and prose work have different model-tier requirements.** The model-tier
   study found blind craft scores of 4.9 / 4.0 / 2.2 across frontier, Sonnet, and Haiku,
   while every tier passed every structural gate first-pass. Mechanical and structural
   work is cheap-model-viable; prose is not. Any approach that keeps those two jobs
   separate can serve them with different models, which is what makes OpenRouter
   substitution practical.

## 2. The reframing: what the skeleton actually buys

It is worth being precise, because the replacement question depends on it.

The skeleton does **not** guarantee validity. The gate does. `run_gate` validates a
Storybook: topology, safety, reading level, band profile, ending economy. It does not ask
where the graph came from. A story assembled by any means at all is checked by exactly
the same rules, so the safety and quality floor is not what is at stake here.

What the skeleton actually provides is threefold:

- **Cognitive offload.** The model never has to hold a 26-node graph in its head.
- **Amortized human verification.** One reviewed artifact serves many books.
- **Predictable envelope.** Node count, depth, and estimated minutes are known in advance.

Only the first is a capability claim, and it is the one the evidence above puts in doubt.
The second is a cost optimization rather than a safety property, because ADR-005 requires
human approval of every finished story regardless of how it was built. The third is
recoverable by construction in several of the alternatives below.

**So the question is not "what replaces the skeleton's guarantees" but "what else can take
structure off the model's plate, or make the model able to carry it."**

## 3. Invariants: what every alternative must preserve

No alternative is allowed to weaken these, and all of them are already enforced by code
that does not care about skeletons:

- The deterministic gate (Layer 1 and Layer 2), unblocked, with zero safety flags.
- Band profile budgets: node count, word budgets, reading-level target, ending economy.
- The safety envelope and the moderation pipeline.
- Mandatory human approval before publication (ADR-005).
- Structural integrity of the finished artifact: reachability, no dead ends, valid ending
  kinds and valences, condition/effect coherence.

Everything above the gate is negotiable. That is the design space.

## 4. Taxonomy: five ways to stop asking one call to do both jobs

| Strategy | Structure comes from | When it is fixed |
| --- | --- | --- |
| **Pre-commit** (current) | human-authored catalog | before the request |
| **Sequence** | a dedicated generation stage | per request, before prose |
| **Externalize** | a deterministic program | per request, before prose |
| **Iterate** | model plus gate feedback | during prose |
| **Invert** | a parse of linear prose | after prose |

The six alternatives below occupy these cells. They are not mutually exclusive; the
strongest combinations are noted in section 6.

## 5. The alternatives

### A1. Per-request generated skeleton (Sequence)

**Mechanism.** Replace the catalog lookup with a generation stage that authors a skeleton
plus narrative contract for this request only, validated by `check_skeleton --strict` and
the NC checks before any prose is written. Everything downstream is unchanged.

**What it fixes.** Sibling recognition, completely: no two stories share an armature, so
the channel that failed the recognition margin twice cannot exist. It also retires the
catalog rebuild work.

**What it risks.** The strict-bar pass rate per request is unknown. More importantly, and
this is the non-obvious risk: **we have observed convergence at every layer we have
measured, so the skeleton generator will have its own structural priors.** Three generated
skeletons may rhyme with each other the way three bibles did. This must be measured, not
assumed, with a structural-distance metric rather than the prose metrics we already have.

**Model tier.** Structure authoring is the job an agent already did first-pass green here.
Needs re-testing at Sonnet and below.

**Build cost.** Small to moderate: a generation stage, plus wiring the strict bar into the
request path.

### A2. Structural grammar sampler (Externalize)

**Mechanism.** A deterministic program constructs a graph that satisfies band-profile
budgets *by construction*: sample a topology class, node count, per-node arity, merge
points, depth, and ending economy from the numeric ranges the validator already encodes.
No LLM participates in structure at all. The model receives a valid graph and writes
prose.

**What it fixes.** Structural failure rate goes to approximately zero, because invalid
graphs are never generated. Structural variety is unbounded, and critically the *arity and
order* vary per story, which is precisely the fix the recognition rater proposed when it
observed that readers compare menus rather than prose. Cost drops, because structure
consumes no model tokens.

**What it risks.** The classic procedural-generation failure: valid is not the same as
good. A sampler will happily emit graphs that satisfy every budget and that no author
would ever design. Making the sampled shapes *narratively* plausible is the real work, and
it is more than parameter tuning.

**Model tier.** The lowest requirement of any alternative, since the model only writes
prose. **Best OpenRouter portability by a wide margin**, and for that reason alone this
alternative deserves testing even if it is not the eventual winner.

**Build cost.** Moderate for the sampler; the hard part is the narrative-shape priors. The
offline `mutation/` module (ADR-020) may already supply usable structural operators.

### A3. Gate-in-the-loop free growth (Iterate)

**Mechanism.** No pre-committed structure at all. An agent grows the storybook
incrementally with the validator and checkers as live tools, running the gate after each
addition and repairing on failure, terminating when the gate is clean and the band budget
is met.

**What it fixes.** It tests the founding assumption directly, which no other arm does.
Structure follows the story rather than the story being poured into structure, giving
maximum expressiveness.

**What it risks.** Cost and non-termination are the obvious ones. The subtler risk is
degenerate optimization: an agent whose fitness function is the gate will find shapes that
pass the gate without being good stories, which is the same lesson the revision round
taught in miniature when Haiku satisfied an n-gram check with word swaps.

**Model tier.** Highest of any alternative, and therefore the worst portability. Our data
shows Haiku can execute a *bounded* revision instruction; that is not evidence it can run
open-ended structural growth.

**Value.** Highest information content. Even if it loses on cost, it either retires the
founding constraint or gives us its current, accurate shape.

**Build cost.** Moderate: the checkers all exist; this is a loop harness plus termination
criteria.

### A4. Spine-then-branch (Sequence, narrative-first)

**Mechanism.** Pass 1: the model writes a linear story, its strongest and most universal
mode. Pass 2: identify the genuine decision points in *that* story and fork them. Pass 3:
write the divergent consequences. Pass 4: gate and repair to fit the band envelope.

**What it fixes.** This is **the only alternative that attacks the recognition finding at
its named root cause.** Both raters, independently, identified choice-menu semantics as
the fingerprint: the same options with the same meanings in the same order at every fork.
When the choices are derived from a specific story rather than from a reused graph, the
menus differ because the stories differ. It also directly addresses the "the skeleton is
visible" critique, since scene functions are no longer assigned to fixed positions.

**What it risks.** Hitting the exact node and ending-economy budgets is genuinely hard when
structure emerges from narrative; expect to need a fitting or repair pass, and expect some
briefs to fork poorly. Branch explosion needs an explicit control.

**Model tier.** Moderate. Linear narrative is the most universal LLM capability, so
portability should be good.

**Build cost.** Moderate: a fork-identification stage plus budget-fitting repair.

### A5. Prose-first extraction (Invert)

**Mechanism.** The model writes a branching narrative in a lightweight authoring markup
(headed sections with explicit choice links, in the spirit of Twine or Ink), and a
deterministic parser converts it into Storybook JSON, which the gate then validates.

**What it fixes.** It removes the entire JSON-structure burden from the model. This
matters more than it sounds: emitting a well-formed 26-node graph with correct ids,
targets, conditions, and effects is exactly the kind of task mid-tier models fail at, and
it is unrelated to whether they can write good children's prose. Writing marked-up prose
is dramatically easier than emitting the JSON.

**What it risks.** Parse failures and invalid link graphs; needs a strict parser paired
with a forgiving repair path.

**Model tier.** Low. **Probably the best fit for cheap OpenRouter models**, and it is
orthogonal to the other alternatives, so it can be combined with any of them.

**Build cost.** Moderate: a markup spec, a parser, and repair. High reuse value regardless
of which structural approach wins, which makes it a good early investment.

### A6. Structure-as-attractor repair (Iterate, post-hoc)

**Mechanism.** Generate freely, then let a deterministic repair stage snap the graph toward
validity (add a missing ending, merge a dead end, prune over-arity) rather than rejecting
the whole artifact.

**What it fixes.** It makes failure cheap, which is what makes weak models viable at all.

**What it risks.** Prose-graph divergence: a repaired edge whose prose no longer matches
it. Repairs must either be prose-aware or must trigger a re-fill of the nodes they touch.

**Model tier.** Enables low tiers; that is its purpose.

**Build cost.** Moderate; `mutation/`'s operators may supply much of the machinery.

### Controls

- **A0. Current approach** (catalog skeleton, contract, bible, selection). The baseline all
  arms are scored against, with measurements already in hand.
- **A0b. Current plus per-binding arity and order variation.** Not skeleton-free, and
  included as a *diagnostic* rather than an alternative: it isolates whether varying branch
  arity and scene order alone moves the recognition landing node. This is the cheapest
  experiment in the set and it makes every other result interpretable. If arity variation
  moves recognition, A1 and A2 become much more attractive; if it does not, the driver is
  scene-function order and A4 becomes the only real fix.

## 6. Combinations worth testing as single arms

- **A2 + A5** (program builds the graph, model writes marked-up prose, parser assembles):
  the strongest portability pair, and the natural candidate for cheap OpenRouter models.
- **A4 + A6** (spine-then-branch with repair fitting): the strongest narrative-coherence
  pair, and the one most likely to beat the recognition margin.

## 7. The bake-off

The measurement apparatus already exists, which is the main reason this is testable now.
Every arm is scored on the same bench used for pilots 1 to 3.

**Deterministic**: fill integrity; full gate (blocked, safety flags, findings mix);
reading-level distribution; band-profile compliance; sibling shared grams per 1000 and
menu-frame overlap; title compliance; PS, leaf similarity, and Mechanic Divergence.

**Rater-based** (blind, comparative, using the rubrics already written): the six-dimension
craft rubric with a ship verdict; scene-inventory device distinctness; recognition landing
node plus the five-point score.

**New instrument required**: a **structural-distance metric** across stories produced by
the same approach (topology signature, arity sequence, graph edit distance). Every
diversity metric we have measures prose or devices within a fixed graph. Once arms differ
in structure, structural variety becomes a first-class outcome and nothing currently
measures it. Build this before the bake-off, not during.

**Cost**: tokens and wall-clock per book, plus the lowest model tier that passes each arm.

**Pre-registered margins**, anchored to measurements already in hand:

| Outcome | Margin | Current approach |
| --- | --- | --- |
| First-pass gate not blocked | 3/3 | 3/3 (met) |
| Blind craft mean | >= 4.0 (the shipping bar) | 4.9 frontier, 4.0 Sonnet |
| Recognition landing | past the hub node, or no landing | FAILED twice (node 2, node 4) |
| Sibling grams per 1000 | <= 4.0 after at most one revision round | 1.2 (met) |
| Cost per book | <= 2x current | baseline |
| Portability | passes at Sonnet | passes at Sonnet |

Recognition is the margin that matters. It is the only one the current approach fails, and
an alternative that merely matches the others while still failing recognition has bought
nothing.

**Design**: same request brief across arms, three stories per arm, band 10-13 (the
band where readers are sharpest and the current approach is weakest), raters blind to arm.

## 8. Recommended sequence, cheapest information first

1. **A0b, the arity diagnostic.** Smallest experiment in the set; makes everything else
   interpretable.
2. **A5, prose-first extraction.** Reusable by every other arm and the most direct answer
   to the OpenRouter substitution goal, so its value does not depend on winning.
3. **The structural-distance metric.** Required before A1, A2, or A3 can be scored
   honestly.
4. **A2 and A4 in parallel.** The two strongest candidates, on different axes: A2 for
   portability and cost, A4 for beating the recognition margin.
5. **A3 last.** Most expensive, and its job is to retire or confirm the founding
   assumption rather than to win the bake-off.

## 9. What would be lost, stated honestly

Dropping the catalog gives up amortized human verification of structure, a small and
auditable set of artifacts, and a known length envelope before generation starts. The
first is mitigated by ADR-005's mandatory human approval of every story; the second is a
real loss in reviewability that per-request validation only partly replaces; the third is
recoverable by construction in A2 and by repair in A4 and A6.

The catalog also remains the correct answer for one case the alternatives do not serve:
a deliberately marketed series, where a shared armature is a feature the reader is buying
on purpose rather than a defect discovered on night two.
