# Alternatives to the pre-authored skeleton (2026-08-09)

> **Status after measurement (2026-08-09): the program described below is NOT warranted on
> current evidence.** The gating experiment in section 2b has been run. Sibling exposure is
> real and in fact certain, but its drivers are a 3-per-cell catalog and a family-scoped
> anti-repeat window, both bounded engineering fixes, rather than the skeleton architecture.
> The alternatives are retained as a designed option set to revisit if the catalog and
> scoping fixes fail to clear the problem, not as recommended work.
>
> Original status: proposal for testing, not a decision. Owner-requested after the third
> diversity pilot ([skeleton-narrative-redesign-proposal-2026-08-09.md](./skeleton-narrative-redesign-proposal-2026-08-09.md),
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
   `scripts/check_skeleton.py:230-401`, merged to `main` as `4e1a08bc` (2026-08-10). It is
   `--strict`-only, and it carries no rule id in the validator catalog. **It never runs on
   generated stories.** Skeletons are held to a standard generated stories are not.
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
   anti-repetition machinery reads `load_family_history` (`diversity/history.py`), which
   does carry skeleton identity (`skeleton_slug: str | None` at `history.py:60`, populated
   on each `HistoryEntry` at `:210`); the defect is scoping, not missing identity. It is
   family-scoped, filtering on `Storybook.family_id` (`:191`), with a window of 20
   (`_DEFAULT_WINDOW = 20` at `:36`). If that is the only history the selector sees, then a
   household with K children burns the recency window K times faster, degrading protection
   for each child, while simultaneously penalizing skeletons a given child has never read,
   wasting catalog that child could still consume. Both failure modes point the same way:
   **per-reader skeleton history is likely a prerequisite for any catalog-scaling answer,
   and it is a much smaller build than any arm in section 6.**

**This is the measurement that gates the entire program**, and it costs no generation
tokens. It has now been run (`scripts/analyze_sibling_exposure.py`, merged to `main` as
`4e1a08bc`), and the answer is decisive.

### 2b.1 Measured answer

**Exposure is not merely common, it is certain.** All 18 production cells are populated,
but only thinly: 3 or 4 skeletons each (verified through the shipped `candidates_for_cell`
and `band_profile.py:184-203`'s `_PRODUCTION_CELLS`, all 6 bands, min 3, median 3, max 4,
zero empty cells). A child therefore **exhausts a cell by their 4th request in it**, after
which every further story in that cell is, with probability 1, a tree they have already
read. A repeat becomes more likely than not at the 3rd or 4th request:

| Cell (pool) | P(repeat by 2nd) | by 3rd | by 4th | First likely repeat |
| --- | --- | --- | --- | --- |
| 10-13 short (4) | 0.14 | 0.43 | 0.77 | request 4 |
| 10-13 medium (3) | 0.20 | 0.61 | 1.00 | request 3 |
| 3-5 short (3) | 0.20 | 0.61 | 1.00 | request 3 |

This table's figures are a pool-size-only calculation; the household scoping they assume
(single reader versus family-shared history) is not recorded in this document, and at pool
3 the 0.20 second-request figure here does not match the 0.09 single-reader figure quoted
in section 2b.2. See the note there: the two are not reconciled in this document.

Rotating across all three length cells at 10-13 (10 skeletons) buys about two extra
requests, not an order of magnitude, and reaches certainty by request 11.

### 2b.2 The scoping defect is confirmed, and it is the cheaper half of the fix

**No per-child skeleton history exists anywhere in the system.** `Storybook` carries
`family_id` and `personalization_subject_profile_id` and no other profile link
(`db/models.py`), and the only two reads of prior `skeleton_slug`
(`skeleton_match.py:587`, `diversity/history.py`) both filter on `Storybook.family_id`
with a 20-row window. The per-child evidence needed already exists and is unused:
`StoryRequest.profile_id` is indexed, and `StorybookAssignment.child_profile_id` is the
read gate.

The consequences are measurable and entirely attributable to the scoping choice, not to
pool size. At pool 3, P(repeat by the child's 2nd request) is 0.09 for a single-reader
household (the child-scoped baseline, one child, no siblings sharing the window), 0.19 for
a family-scoped two-child household, and 0.29 for a family-scoped three-child household; a
counterfactual child-scoped history with three readers reproduces the single-reader curve
to within noise. **This 0.09/0.19/0.29 family-size progression is not the same figure as
the 0.20 second-request value the section 2b.1 table gives at pool 3; the two are not
reconciled in this document, and the basis of the table's 0.20 (in particular, what
household scoping it assumes) needs to be published before either number is used as a
target.** The 0.09/0.29 pair, not the table's 0.20, is what section 11.2 carries into the
recommended path. The shared 20-row window also hides
**81%** of a child's own band reading in a three-child household at one story per month.
A third leak is unmeasured: `visibility='catalog'` books from another family are readable,
but recency filters on the owning family, so a child can read a catalog story and then be
served a fresh fill of that same skeleton at full weight.

Scoping the anti-repeat history to the requesting child recovers a meaningful share of the
required pool for no new content, but the range is wider than a prior revision of this
document stated: from the pool figures below (19 to 36 skeletons for a single child, or 35
to 46 under today's family scoping), the reduction is **(35-19)/35 = 46% at the N=10
target and (46-36)/46 = 22% at the N=25 target**, that is, 22% to 46%, not 25% to 30%.

### 2b.3 Catalog sizing, and what it costs

Because a skeleton is consumed once per child and reused freely across children (verified:
no global or cross-family anti-repeat exists, and `visibility='catalog'` actively amortizes
one fill across families), required catalog is `tenure x rate` spread across a band's
cells, independent of user count.

| Per-child stories/month | Total catalog required | Have today |
| --- | --- | --- |
| 0.5 | 106 | 57 |
| 1.0 | 204 | 57 |
| 2.0 | 408 | 57 |
| 4.0 | 816 | 57 |

(Corrected 2026-08-09: an earlier revision of this section quoted "about 130 at 0.5, 408
at 1, 816 at 2." Two separate changes produced the table above, not one. The 408 and 816
figures are explained by a one-rate-step shift: they are the correct values for the 2.0 and
4.0 per-month columns, not for 1.0 and 2.0 as the earlier revision implied. The 130-to-106
change at the 0.5 row is a second, independent correction that the rate-step shift does not
explain. **Note also that the table is not linear across its first step while being exactly
linear above it**: 204, 408, and 816 double cleanly at each step from 1.0 upward, but
106 x 2 = 212, not 204, so the 0.5 row is not exactly half the 1.0 row. No mechanism for
that non-linearity is recorded in this document, and none should be assumed; the 0.5
figure's derivation needs to be published before it is used as a catalog target.)

To keep a repeat less likely than not through a child's Nth request in one cell, that cell
needs 19 skeletons at N=10 and 36 at N=25 for a single child, or 35 at N=10 and 46 at N=25
under today's family scoping.

**The number that decides everything here is per-child stories per month, and it is not
measured in this deployment.** That is the one product metric worth instrumenting before
committing to a catalog target.

### 2b.3a Length demand is not flat, and that changes where the catalog goes

Owner correction, 2026-08-09: demand concentrates on **medium length** within a band, with
few requests for short books and few for very long ones. The sizing above assumed flat
demand across a band's length tiers, which is wrong.

**Cells are hard partitions.** `skeleton_matches_cell` treats only a NULL length as a
wildcard, and **0 of the 58 production-eligible skeletons declare a NULL length**
(verified by enumeration). A medium request can never be served by a short or long
skeleton, so shortfalls are additive and surpluses are stranded capital.

**The total does not move; the shortfall and its location do.** A band's requirement is one
child's band-lifetime consumption however it splits, so peaking demand leaves the total
essentially unchanged (106 flat versus 108 to 110 medium-weighted at 0.5/month, the delta
being per-cell ceiling rounding). What rises is the **shortfall, by 23 to 32%** (47 flat
versus 58 to 62 medium-weighted at 0.5/month), because a flat catalog spreads 3 to 4
skeletons per cell against demand that is not flat.

**The binding constraint moves to the medium cell in every band**, and exhaustion arrives
about one request sooner. At 8-11 the probability a child hits a repeat by their 4th
request rises from 0.386 (flat) to 0.647 (strongly medium-weighted). Under both
medium-weighted regimes, **every short and long cell is at or near sufficiency at
0.5/month while every medium cell is short by 5 to 11 skeletons.**

**Build order follows directly: put the first 6 to 12 skeletons of each band's budget
entirely into that band's medium cell.** Against an even three-way split that buys 0.8 to
2.2 additional requests before a repeat, and an even split is never optimal in any band
under either medium-weighted regime. Short and long only earn marginal skeletons past
roughly the 17th to 20th request, once medium is deep enough that its hazard falls below
theirs.

Two defects surfaced alongside this, both independent of catalog size:

1. **Kid auto-approve hardcodes `length=SHORT` for every band**
   (`api/story_requests.py:508`). Adult-initiated requests require an explicit,
   unprefilled length at both entry points, so there is no adult-path default to conflict
   with medium demand; but auto-approved requests, the ones where nobody is choosing, are
   steered into the thin-demand tier. **For the teen bands this is an outright bug:**
   13-16 and 16+ have no short cell by design (ADR-011) and hold no short skeletons, so a
   teen-band child with auto-approve enabled produces an empty candidate list and a 422
   every time.
2. **ADR-011's band-by-length rule is enforced nowhere in the request path.** The approve
   body validates band against *style* only, and both length selectors render all three
   lengths for every band, so a guardian can approve a "long" 3-5 book or a "short" 13-16
   book and hit the same empty-cell failure much later.

The teen bands are also the most expensive per unit of demand served, not the least: the
prose/gamebook split doubles their cell count, so 13-16 needs 15 skeletons in each of
medium/prose and medium/gamebook at 1/month, against 22 for a non-teen band's single
medium cell.

### 2b.4 On band weighting

The owner's expectation was a catalog weighted toward the middle of the age range. The
structural drivers in the code do not by themselves produce that shape: band tenure is 36
months for every band except 3-5 (24), and cell fragmentation is *highest* in the teen
bands, where `_STYLE_AWARE_BANDS` splits prose from gamebook into 4 cells rather than 2 or
3. Two code facts do favor the middle: 8-11 and 10-13 overlap at ages 10 to 11, so a child
there can be served from either band (about 19 skeletons rather than 9 or 10), a supply
cushion no other band pair has; and the teen bands' nominal 13 skeletons are really four
pools of 3 to 4.

So middle-weighting rests entirely on per-child reading *rate* peaking in middle childhood,
which is a product assumption no code or data in this repo expresses. If that assumption
holds, weight the middle. The defensible general rule is to size each band proportional to
`tenure x rate x cells`, which makes measuring the rate per band the prerequisite.

### 2b.5 Verdict

**Replacing the skeleton architecture is not warranted by this evidence.** The exposure is
real and certain, but its causes are a 3-per-cell catalog and a family-scoped 20-row
window. Both are bounded, one-time engineering costs that do not grow with the business,
whereas the alternatives in section 6 are unbounded engineering costs that also forfeit
personalization eligibility and the pre-LLM denylist floor (section 10). The ordered fix
list is: scope anti-repeat history to the child, widen or drop the 20-row window, close the
catalog-visibility leak, instrument per-child reading rate, then buy catalog against the
measured rate.

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
also caller-parameterized: `enforce_grammar` defaults to False, and no caller anywhere in
`src/` passes `enforce_grammar=True`, so **generated stories never run CG-1 through CG-4**;
`worker.py:2326` calling `generate_story` without overriding it is one instance of a default
that holds across the whole runtime path. `4e1a08bc` (merged to `main` 2026-08-10) changed
only the skeleton side of this: `scripts/check_skeleton.py:504` passes
`enforce_grammar=bool(args.strict)`, so CG-1 through CG-4 run against a skeleton only when
`--strict` is passed explicitly, not as an inherent part of promotion. This weakens the
comparison originally drawn here: the asymmetry is opt-in, present only when a promoter
remembers to pass `--strict`, and absent by default on both sides. "The gate guarantees
validity" still cannot carry the full weight of a cross-path comparison, but the reason is
that grammar enforcement is opt-in rather than that one path enforces it unconditionally
and the other does not.

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
though the strict-bar fitness functions in `scripts/check_skeleton.py` (merged to `main` as
`4e1a08bc`; gap 1 in section 2) do need promoting from script to library code before they
can score generated graphs.

**Rater-based** (blind, comparative, using rubrics already written): the six-dimension
craft rubric with a ship verdict; scene-inventory device distinctness; recognition landing
node plus the five-point score.

**Cost**: tokens and wall-clock per book, plus the lowest model tier that passes.

**Pre-registered margins**, anchored to measurements in hand:

| Outcome | Margin | Current skeleton path |
| --- | --- | --- |
| First-pass gate not blocked | 3/3 | 3/3 (met) |
| Strict bar (walk/indegree/depth floors; `4e1a08bc`) | see note | **2 of 61 catalog skeletons pass; 0 of 11 at 10-13** |
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
2026-08-09 across all bands, 0 of 11 at 10-13, using the strict-bar tooling now on `main` as
`4e1a08bc`, run against the shipped catalog; re-verified against merged `main` 2026-08-10,
unchanged). That bar gates *newly drafted* skeletons only when `--strict` is passed; the
catalog is grandfathered (`scripts/check_skeleton.py:62-68`). Promoting it to a blocking
library rule would retire 97% of the catalog, which is a product decision, not a scoring
prerequisite. Separately, "safety flags" must be struck from the bench entirely (SAFE-14 is
a stub, see section 3), and the "portability = passes at Sonnet" row conflicts with this
project's own conclusion that gate-clean is not publishable.

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

## 11. Recommended path for maximum story diversity (2026-08-09)

Synthesis of the three diversity pilots, the model-tier study, the adversarial review, and
the exposure analysis. This supersedes section 9's sequence, which was written before the
exposure measurement.

### 11.1 The two factors

Reader-experienced diversity is a product of two independent probabilities:

> P(this book feels fresh) = 1 - P(the child gets a repeat armature) x P(they recognize it
> given they got one)

Today both terms run to approximately 1. A child exhausts a cell by their 4th request, so
a repeat armature is certain; and when they get one, recognition lands at node 2 to 4 even
with every device margin passing. Pilots 1 to 3 varied devices and prose, which the raters
established is not the driver, so neither term moved. **A path that only deepens the
catalog leaves the second term at 1; a path that only varies the armature leaves the first
term at 1. The recommended path attacks both, ordered by cost.**

### 11.2 Layer 0: scoping (near-free, do first)

Scope anti-repeat history and weighting to the requesting child rather than the family
(`UW-C112`). Family scoping alone triples the second-request repeat rate at three children
(0.287 versus 0.089), and a child-scoped counterfactual reproduces the single-reader curve
to within noise. The data is already indexed. This also recovers 25 to 30% of the required
catalog for no new content. Widen or drop the 20-row window and close the
`visibility='catalog'` recency leak at the same time.

### 11.3 Layer 1: stop mandating the fingerprint (a rule change, not a build)

Both raters named choice-menu semantics as the single strongest recognition channel: the
same options, with the same meanings, in the same order, at every fork. **That sameness is
currently required by the validator.** `choice_grammar.py:120` sets options-per-choice to
the point constraints `(3, 3)` at 8-11 and 10-13 and `(2, 2)` at 3-5, so menus cannot
differ in shape at exactly the bands where readers are sharpest. `templates/drafting_guide.md`
then prescribes the same constants to the model and is spliced into every generation stage,
which is why removing the skeleton does not remove the armature.

Three cheap moves, none of which authors any content:

1. Relax CG-2 from point constraints to ranges (for example `(2, 4)` at 10-13), making menu
   shape a per-story variable rather than a constant. ADR-011 owns the constants, so this
   is an ADR amendment with a cognitive-load rationale to re-argue, not a silent change.
2. Parameterize the drafting guide's structural advice per request instead of shipping one
   fixed grammar to every call, so the shared prompt stops being a fixed armature.
3. Vary scene-function assignment and order across bindings of one skeleton, which attacks
   the "identical function at identical position" finding directly and is the cheapest
   answer to "the skeleton is visible".

### 11.4 Layer 2: catalog depth against the demand curve (bounded capital)

Author against measured demand rather than filling cells evenly: the first 6 to 12
skeletons of each band's budget go entirely to its medium cell (section 2b.3a). Cells are
hard partitions, so this is the only spend that reaches the binding constraint.

### 11.5 Layer 3: mutation as a catalog multiplier, tested and withdrawn (2026-08-09)

**Result, stated up front: the multiplier does not exist.** The experiment in section
11.5.1 found that every bounded mutant tried cleared the structural anti-clone floor by
orders of magnitude too little, and the one mutant that did clear it did so only by
grafting material from a *different* parent skeleton, which is recombination, not
multiplication. A same-book reader verdict landed at reading position 3 on two of the
bounded mutants. **Layer 3 is withdrawn.** Layers 0, 1, and 2 stand, and Layer 2 (catalog
depth) becomes more important rather than less, because there is no cheap structural
substitute for authoring. The reasoning below is retained as **prior reasoning**: it is
what motivated running the experiment, and it explains why cross-skeleton hybridization
(section 11.5.1's "one finding points somewhere real") remains a genuinely open, untested
question even though same-parent mutation does not.

**Prior reasoning, before the experiment (overturned by 11.5.1 below).** The working
hypothesis going in was that this was the largest unexploited lever in the system, because
the machinery already exists: `mutation/` ships five registered operators (M1
sibling-subtree swap, M2 ending remap, M3 prune/graft, M4 vary-decisions, M5 state
variation), an acceptance ladder, and calibrated anti-clone floors. It is used today only
offline, to grow the catalog.

The reasoning was that, applied per request to a matched skeleton, mutation would
**multiply** the effective armature pool rather than add to it: if one parent yielded k
accepted mutants that cleared the anti-clone floors, a 3-skeleton cell would become a
3k-armature cell. At k=5 that would move a child's first likely repeat from request 3 or 4
to beyond request 10, the same outcome as authoring 12 to 15 new skeletons per cell, for a
fraction of the cost. Nothing else in the analysis appeared to offer a multiplier. The
experiment below tested this directly.

### 11.5.1 The experiment

The experiment was run on `the-midnight-museum` (10-13 short prose,
production-eligible, Tier 1). Three accepted mutants, all `accepted/held`:

| Mutant | Chain | Structural distance from parent |
| --- | --- | --- |
| S | M1 sibling-subtree swap | **0.0000** |
| D | M4 insert-decision, reconvergence variant | **0.0038** |
| X | M3 graft from another skeleton, then M4, then M2 | **0.0726** |

The committed anti-clone floor is `TAU_CELL = 0.05`. Hand-authored same-cell
sibling pairs sit at a median of **0.390**, two orders of magnitude above every
bounded mutant.

**Verdict: mutation is not a catalog multiplier.** Shape-preserving operators
are perceptually null by construction (M1 scored exactly 0.0000 on all five swap
pairs tried, including cross-act swaps), and the shape-changing operator reached
only 0.0038, still below the floor. A maximum-length chain using only the
parent's own material reached 0.0064. Applicability was not the constraint:
M4 had 2,201 eligible sites.

**Why**, and this is the general lesson: **every mutant preserves 100% of the
parent's `<<FILL>>` beat directives** (95 of 95 nodes, 95 of 95 beats in all
three mutants). Mutation moves the graph; recognition is driven by scene content
and decision semantics, which live in the beats. Moving edges around authored
content cannot change what the reader recognizes.

A rater pass on two fills of mutants S and D (different bindings, the production
configuration) landed the same-book verdict at **reading position 3, scoring
2.0**, with the structural difference not visible until position 8, five
positions after recognition. The deterministic bench also reported 70.4 shared
grams per 1000 and perceived similarity 0.9970; the caveats below explain why
that figure does not corroborate the verdict independently.

**One finding points somewhere real.** Mutant X was the only one to clear the
floor, and it did so by grafting 32 nodes from a *different* catalog skeleton.
That is recombination across two parents, not multiplication of one. Cross-
skeleton hybridization may be a genuine lever, but it is a different claim,
untested here, and it scales with pairs of existing skeletons rather than
replacing the need for them.

**`structural_distance` was vindicated on this evidence**, contrary to the
hypothesis in section 11.5: `TAU_CELL` rejected exactly the mutants the reader
rejected, and its ordering matched the reader's. Its order-blindness did not
bite because no mutant approached the threshold. That is not a general
exoneration.

**Caveats.** One parent, one rated pair, one pass, and the rating was
author-scored rather than blind (this environment could not spawn an isolated
rater). **The 70.4-shared-grams-per-1000 figure cited above cannot serve as
independent corroboration and the claim that it "will replicate on any parent"
is wrong.** Per `AL-185` and `UW-C120` (both added by this PR), sibling-convergence
measurements are invalid when one author writes both arms of a comparison, because
the number measures the author's de-convergence effort rather than the condition
under test: the same author who filled mutants S and D produced 302 shared grams
per 1000 on a first draft and drove it down to 70.4 only after two deliberate
de-convergence passes. That figure is therefore contaminated by the single-author
confound and carries no evidentiary weight beyond what the author already knew
going in. What the withdrawal verdict actually rests on is different evidence that
does not share this confound: the **structural distances** (0.0000 to 0.0064
against the `TAU_CELL = 0.05` floor), which are computed from the graphs
themselves and do not depend on who wrote the fills, so they should replicate on
any parent; and the single same-book **reader verdict** at reading position 3,
which is n=1 but is not author-scored on the recognition question itself in the
way the grams figure is on the prose-distance question. This parent also sits at
14 decisions on its longest path, which constrained M4's reconvergence targets;
an `open_map` or `sorting_hat` parent may give it more room. None of these
caveats reverses the withdrawal: the structural numbers alone already show every
bounded mutant sitting two orders of magnitude below the anti-clone floor, which
is sufficient on its own to conclude same-parent mutation is not a multiplier;
the point of this caveat is to stop leaning on the contaminated grams figure as
if it were independent confirmation.

**Consequence for the recommended path: Layer 3 is withdrawn.** Layers 0, 1, and
2 stand, and Layer 2 (catalog depth) becomes more important rather than less,
because there is no cheap structural substitute for authoring.

**The original open question, now answered by the experiment above.** M1 and M2 are
shape-preserving by design (M1 "preserves every aggregate shape feature"), so the
question going in was whether a mutant might be structurally distinct by the committed
floors and still read as the same book. Only M4, particularly its `reconvergence`
variant, changes global shape. The experiment this section anticipated is exactly the
one section 11.5.1 ran: fill two mutants of the same parent (S and D) and run the
recognition protocol on the pair. They read as the same book, at reading position 3, so
the floors are measuring something readers do not perceive at these mutation
magnitudes; that is itself the finding, and it also invalidates using
`structural_distance` as a diversity gate at this scale, since that metric is
order-blind and cannot see the position-identity channel the raters named. No further
run of this specific experiment is warranted. The open question that remains is
whether cross-skeleton hybridization (mutant X's path, "one finding points somewhere
real" above) behaves differently; that is untested and would be the next
highest-information test in this area, not a repeat of the same-parent comparison
already run.

### 11.6 What not to do

Replacing the skeleton architecture (sections 5 to 7) is not warranted. The exposure
analysis showed the driver is catalog depth and history scoping, both bounded one-time
costs, and none of the alternatives removes the drafting-guide armature or the CG-2
mandate that Layer 1 addresses for free.

### 11.7 Quality guards as diversity rises

More variety means more surface for defects, so two protections should land alongside:
the fill-vs-contract fact audit (`UW-C107`), since nothing today verifies that prose honors
the obligations the contract declares; and the prose-craft detectors, kept advisory until
validated out of sample (`UW-C111`).

### 11.8 The two numbers that gate all of it

Per-child stories per month, and the real length distribution within a band. Both are
unmeasured, and every catalog target above is a function of them.
