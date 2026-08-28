---
title: "Validation Rule Catalog"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Define stable rule IDs, failure messages, and pass/fail semantics for every validation gate check."
tags:
  - planning
  - specifications
  - validation
component: Development-Tools
source: "tech-spec.md section 'Validation gate (deterministic, no LLM)'"
---

# Validation Rule Catalog

> **Status**: Accepted | **Version**: 1.4 | **Updated**: 2026-08-27
> **Scope**: All stories (Layer 1, Policy); Tier-2 stories only (Layer 2); all stories
> advisory (RL); fill-result stories only, advisory (PN); all stories always-human (SAFE);
> series chains at publish only (SR)
>
> **v1.4** adds one genuinely new rule rather than closing a registry gap: PN-1
> (advisory proper-noun introduction check) shipped in commit `83ff95da` and is
> documented here for the first time, per this document's own Purpose clause that
> adding a rule ID requires a revision. See the Naming section below.
>
> **v1.3** closes a registry gap rather than adding rules: L2-13, L2-14 and the entire
> SR family (SR-1..SR-7, SR-9) were enforced in code while documented nowhere here, so
> the catalog was not the reference it claims to be. SR-8 is recorded as reserved.

---

## Purpose

Every rule the validator applies gets a stable ID, a description, and a failure-message
template here. Rule IDs are the stable references used in validation reports, repair-stage
prompts, and the known-bad corpus. Adding, removing, or renumbering a rule requires a revision
to this document.

---

## Pass/Fail vs Advisory Semantics

| Category | Behaviour | Blocks publish? |
|----------|-----------|-----------------|
| Layer 1 (L1) | Pass/fail | Yes |
| Policy (PL) | Pass/fail (PL-19 story-mean, PL-23, PL-24, PL-26 and PL-25's ceiling short of its hard limit are advisory) | Yes |
| Layer 2 (L2) | Pass/fail | Yes (Tier-2 only) |
| Reading Level (RL) | Advisory | No (warns only) |
| Choice Grammar (CG) | Advisory, and opt-in | No (warns only, and emits nothing at all by default) |
| Naming (PN) | Advisory, fill-result only | No (warns only, and never runs under the `"skeleton"` context) |
| Series (SR) | Pass/fail | Yes (blocks publish of a chain) |
| Safety (SAFE) | Always human-routed | Yes (routes to human review, not auto-rejected) |
| Series (SR) | Pass/fail | Yes, at publish only (cross-book; not part of `run_gate`) |

Layer 1, Policy, and Layer 2 are hard gates, run in that order (`validator/gate.py::run_gate`):
any failure fails the generation job (it lands in `failed`, not `passed`), so the story never
advances to `in_review`. The Policy layer's advisory exceptions are PL-19's story-mean
words-per-node sub-check (its per-node word-cap sub-check is still blocking), PL-23, PL-24,
all of PL-26, and PL-25's ceiling short of its hard limit. The reading-level
check warns and logs but does not block. A safety hit routes the generation job to
`needs_review` for mandatory human review; the validator does not auto-reject, but no
auto-publish path exists when the flag is set.

**Layer 2 applies to Tier-2 stories only.** Running Layer 2 on a Tier-1 story (which carries
no variables and has deterministic visibility for all choices) is a no-op and must not produce
false failures.

**The Series (SR) family sits outside `run_gate` by necessity.** Every other family validates one
story in isolation; SR validates a *chain*, so it takes `Sequence[Storybook]`
(`validator/series.py::validate_series`) and runs at publish time from
`publishing/service.py`, which raises `BusinessLogicError(rule="series_validation")` on any SR
error. A single story therefore cannot be SR-checked at generation time, and a book that passes
L1/PL/L2 can still be refused at publish because of the chain it joins.

---

## Layer 1: Graph Rules (All Stories)

Layer 1 runs first, on every story. Layer 2 does not run if Layer 1 fails, because the graph
must be sound before a state-space walk is meaningful.

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| L1-1 | 1 | **Schema conformance**: the Storybook JSON must validate against `schema/storybook.schema.json`. | `L1-1 schema: document does not conform to Storybook schema v{schema_version}: {validation_errors}` |
| L1-2 | 1 | **Reference integrity**: `start_node` must exist in `nodes`; every `choice.target` must be an existing node id; all node ids must be unique; all choice ids must be unique within the story; every `ending.id` must be unique within the story. | `L1-2 ref: {ref_type} '{target}' not found or not unique in story '{story_id}' (referenced from {source})` |
| L1-3 | 1 | **Reachability**: BFS from `start_node` must reach every node. Nodes unreachable from `start_node` are errors, not warnings. | `L1-3 reach: node '{node_id}' is unreachable from start_node '{start_node}' in story '{story_id}'` |
| L1-4 | 1 | **Termination (graph)**: every non-ending node must have at least one choice; every node must have at least one path to an ending node; every ending node must have zero choices and a complete `ending` block. | `L1-4 term: node '{node_id}' {reason} in story '{story_id}' (no path to any ending / missing ending block / non-ending node has zero choices)` |
| L1-5 | 1 | **No trap loops (graph)**: every strongly connected component must have at least one exit edge leading toward an ending. A SCC with no exit is a trap loop. | `L1-5 trap: strongly connected component containing node '{node_id}' has no exit edge in story '{story_id}' (nodes in SCC: {scc_nodes})` |
| L1-6 | 1 | **Condition and effect consistency**: conditions must use only whitelisted operators; every variable referenced in a condition or effect must be declared in `variables`; comparisons must agree in type with the declared variable type; no reachable transition may push an `int` variable past its declared `min` or `max`. | `L1-6 logic: {issue_type} in story '{story_id}' at {location}: {detail} (var='{var}', declared_type={declared_type}, bound={bound}, attempted={attempted})` |
| L1-7 | 1 | **Length budget**: node count must be within the (band x length x style) cell budget single-sourced in `validator/band_profile.py` (band-based per [ADR-011](./adr/adr-011-story-scale-framework.md), not tier-based); branch depth must be within bounds; `metadata.ending_count` must equal the count of distinct ending nodes found in `nodes`. | `L1-7 budget: {budget_type} out of range in story '{story_id}': {actual} (allowed {min}..{max})` |
| L1-8 | 1 | **Field-minor floor** (ADR-025 decision 3): a document that uses a field introduced at schema minor N must declare a `schema_version` whose minor is at least N. Presence of the key is the trigger, not its value: an explicit `null` counts as use and fires the floor, but an absent key does not. Enforces the converse of ADR-025's stamping clause, so an under-declared document fails the gate rather than being silently admitted. The field-to-minor registry is `storybook/field_minors.py`. | `L1-8 schema: field '{field}' was introduced at schema minor {minor}, but this document declares '{declared}'; stamp it at least {major}.{minor}` |

---

## Layer 2: State-Space Rules (Tier-2 Stories Only)

Layer 2 performs a configuration walk. A **configuration** is `(node_id, var_state)`. The walk
starts at `(start_node, initial_var_state)`, computes visible choices using the canonical
condition evaluator, applies effects per the Runtime Semantics transition order, and explores
the closure of reachable configurations. The default configuration cap is 100,000 (see L2-12).

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| L2-8 | 2 | **Configuration walk**: the walk starts at `(start_node, initial_var_state)` and explores every configuration reachable via valid transitions using the canonical evaluator and transition order. If the walk cannot be completed (malformed condition returns non-boolean), the story fails. **NO ID EMITTED** (recorded 2026-07-26): this row describes the walk *mechanism*, and no code path reports `L2-8` as a finding. The failure it names is unreachable rather than unimplemented: `gate.py::run_gate` early-returns on any Layer-1 ERROR, L1-6 already validates the operator whitelist and condition/variable types, and `validator/walk.py` has no raise path, so a non-boolean condition cannot survive to break the walk. Kept because it defines the configuration semantics every other L2 rule is stated against; compare PL-22, also a backstop rather than a normal-path rule. | `L2-8 walk: configuration walk failed at node '{node_id}' with var_state {var_state}: {reason}` |
| L2-9 | 2 | **Stateful dead-end**: any reachable non-ending configuration with zero visible choices is a dead end. A reader in this state cannot proceed. | `L2-9 dead: node '{node_id}' with var_state {var_state} is a stateful dead end (no visible choices, not an ending) in story '{story_id}'` |
| L2-10 | 2 | **Stateful termination and loop escape**: every reachable configuration must have at least one path to an ending configuration. Every reachable cycle must have at least one configuration in the cycle with a visible choice leading out of the cycle toward an ending. | `L2-10 escape: configuration ('{node_id}', {var_state}) has no path to any ending in story '{story_id}' (cycle with no escape / dead configuration chain)` |
| L2-11 | 2 | **Conditional usefulness**: a conditional choice (one with a non-trivial `condition`) that is invisible in every reachable configuration is flagged as a dead branch. This is a warning elevated to a failure: a condition that is never satisfiable is either a generator bug or a story logic error. | `L2-11 dead-branch: choice '{choice_id}' on node '{node_id}' is never visible in any reachable configuration in story '{story_id}' (condition always false)` |
| L2-12 | 2 | **Configuration cap**: if the reachable configuration set exceeds the ceiling (default 100,000), the walk aborts immediately and the story fails. This prevents unbounded validator runtime on pathological stories. | `L2-12 cap: reachable configuration set exceeded the ceiling of {cap} configurations in story '{story_id}' (state space too large; reduce variable count or tighten bounds)` |
| L2-13 | 2 | **Hand-authoring scale advisory**: a Tier-2 story past the hand-authoring node ceiling (`layer2.HAND_AUTHORING_NODE_CEILING`, 460) is past the size a human reviewer can meaningfully check by eye, so the completed Layer-2 configuration walk becomes its sole correctness guarantee. WARNING only: it never blocks, and it is the expected output for a procedurally-generated or series-scale book (the ADR-011 cells marked `dagger`). Its presence means the walk must be treated as the acceptance test rather than a lint pass. | `L2-13 scale: Tier-2 story '{story_id}' has {nodes} nodes, past the hand-authoring ceiling of {ceiling}; the completed Layer-2 configuration walk is now its sole correctness guarantee (hand-review insufficient at this scale)` |
| L2-14 | 2 | **No all-fatal decision** (added 2026-07-26, A14, per the owner ruling "no decision should only have fatal node options; at least one needs to allow advancing or loop back"). No reachable configuration offering two or more visible choices may have every one of them arrive at a forbidden ending with no further choice on the way. Stated over the **reader-visible decision unit**, not the node: a node-scoped reading is trivially satisfied by splitting an all-fatal decision into single-choice corridors that each end fatally, which passes the rule and still shows a child a page with one button that kills them, so the check follows single-successor corridors forward. Forbidden endings are band-scoped: negative valence at 3-5/5-8/8-11/10-13, and `kind == death` at 13-16/16+. `capture` is deliberately NOT fatal at the teen bands, since a survivable capture is the signature ending of the espionage stories there and forbidding it would have rewritten four authored climaxes. | `L2-14 no-way-out: node '{node_id}' with var_state {var_state} offers {option_count} visible choices and every one of them reaches a forbidden ending with no further choice on the way, in story '{story_id}' (a reader must never be shown a decision where every option is fatal; at least one option must let them advance or loop back)` |
| L2-15 | 2 | **Over-declared integer range** (added 2026-08-18, `UW-C294`, owner-approved). A declared int variable whose range is more than 4x the values its conditions can distinguish. The distinguishable span runs from the declared floor to the highest literal any condition tests it against, so a counter declared `0..6` and tested at `>= 3` distinguishes four values and passes; one declared `0..99` and tested at 1, 2 and 3 distinguishes four and does not. WARNING only, and it never blocks: a wide range is a cost the author may knowingly accept, values above the highest threshold are not strictly inert (`inc`/`dec` are order-dependent, so a saturating counter is not a clamped one), and a series continuation's receiving range must contain its sender's (`AL-038`). A variable no condition compares against an int literal is skipped rather than reported. **Runs BEFORE the walk**, unlike every other L2 rule: it is the early warning for the commonest cause of an L2-12 cap, and L2-12 returns immediately on a capped walk, so emitting it afterwards would silence it in exactly the case it exists for. Grounding: the first story-first gamebook declared two counters `0..99` against thresholds of at most 3, a 625x inflation of the configuration space that surfaced only as an L2-12 breach 16,000 words later. `AL-008` recorded this on 2026-07-25 and proposed a prose rule; no check was built and it was re-learned 24 days on. Silent on all 68 committed skeletons. | `L2-15 range: variable '{name}' is declared {min}..{max} ({declared} values) but the highest value any condition tests it against is {highest}, so only {exercised} of them can change a choice's visibility; the declared range multiplies the configuration space L2-12 must enumerate by {multiple}x in story '{story_id}' (advisory only; tighten the bounds to what the story tests, unless the headroom is deliberate)` |

---

## Reading Level (Advisory, All Stories)

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| RL-13 | Advisory | **Reading level**: Flesch-Kincaid grade for each node `body` is compared to `metadata.reading_level.target +/- tolerance`. Any node outside the tolerance range generates a warning. This check warns and logs; it never hard-fails, because FK scores are noisy at passage length and the parent makes the final call. The grade comes from a **vendored** implementation (`validator/reading_level.py::_flesch_kincaid_grade`), not from textstat, which is not a dependency: the formula needs only word/sentence/syllable counts, so vendoring avoids a heavy NLP dependency tree for a check that never blocks, and keeps scores version-stable. Two nodes are skipped silently: a body under `_MIN_WORDS_FOR_FK` (20) words, where FK is statistically unreliable, and an unfilled skeleton body carrying a `<<FILL` directive, which is a directive rather than prose (PL-19 skips the same marker). | `RL-13 level: node '{node_id}' FK grade {actual:.1f} outside target {target} +/- {tolerance} in story '{story_id}' (advisory only)` |

---

## Choice Grammar (Advisory and Opt-In, All Stories)

ADR-011 section 10's choice-grammar rules, implemented in `validator/choice_grammar.py` and
merged by `gate.py::run_gate` as step 6. Two things make this family unlike every other one in
this catalog, and both are load-bearing when reading a report:

1. **Every CG rule is WARNING severity.** No CG finding ever sets `blocked`, exactly like RL-13.
2. **No CG rule runs at all unless `run_gate` is called with `enforce_grammar=True`, and no
   production caller passes it.** The default is `False` and only `tests/unit/test_choice_grammar.py`
   overrides it, so on `main` today these rules emit nothing on any real story. That is deliberate
   D3/D11 grandfathering: the committed corpus predates the grammar and would light up wholesale.
   The flag flips when the D11 `deprecated` per-skeleton marker lands (W2.4), at which point the
   gate can enforce for unmarked (new) skeletons and skip marked ones. Tracked as `UW-C24`. Until
   then, a green gate says nothing whatsoever about choice grammar, and a reviewer must not read
   one as evidence that ADR-011 section 10 is satisfied.

The rows are catalogued anyway, and are covered by the same
`tests/unit/test_validator_rules_catalog.py` lockstep guard as every other family, because an
inert rule that later becomes enforced is exactly the case where an undocumented id does the most
damage: the flip would turn on four rules nobody had written down.

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| CG-1 | Advisory (opt-in) | **Choiceless-run cap**: caps consecutive single-choice, non-ending nodes per band (3 at 3-5, rising per `_DISCRETE_RUN_CAP`, and a flat `_FLOWED_RUN_CAP` of 6 for the flowed bands 8-11 and up). At a flowed band the message also reports the composed stop's word count against the words-per-stop ceiling, since that is what the cap is really a proxy for. **This is a derived backstop, not the ADR rule.** ADR-011 section 10 states its flowed-band rule over *stops* ("1, prefer 0" at 8-11, "0-1" above), and stop-level adjacency needs ADR-026 `compose_stop` boundaries, which nothing in the validator computes; CG-1 counts nodes instead. Tracked as `UW-C23`. | `CG-1 grammar: node '{head_id}' starts a run of {length} consecutive single-choice nodes in band '{band}' (cap {cap}) in story '{story_id}' (advisory only, new-content grammar per ADR-011 section 10){detail}` |
| CG-2 | Advisory (opt-in) | **Options per choice**: bounds how many choices one decision node may offer, per band (`_OPTIONS_BOUNDS`). Scoped to decision nodes, so a single-choice node is out of scope by construction (that shape is CG-1's). A band with no configured bounds is skipped rather than defaulted. | `CG-2 grammar: node '{node_id}' offers {count} choices, outside band '{band}' bounds [{lo}, {hi}] in story '{story_id}' (advisory only, new-content grammar per ADR-011 section 10)` |
| CG-3 | Advisory (opt-in) | **Words per composed stop**: sums the bodies of a whole flowed run plus the branch or ending node it flows into, and compares the total to the band's `_WORDS_PER_STOP_CEILING`. Where PL-19 bounds a single node, this bounds what a reader actually sees on one screen at a flowed band. Skips a run whose word count cannot be determined and a trivial single-node run with no terminal, which PL-19 already covers. | `CG-3 grammar: composed stop starting at node '{head_id}' totals ~{words} words, above band '{band}' words-per-stop ceiling {ceiling} in story '{story_id}' (advisory only; stop nodes: {member_ids})` |
| CG-4 | Advisory (opt-in) | **Choice acknowledgment**: a heuristic proxy for section 10's "every choice is acknowledged in the immediately following prose" rule. Flags a decision-child whose opening sentence shares no content word (post-stopword) with the label of the choice that reaches it. Explicitly lossy: paraphrase and pronoun reference both trip it, which is why it can never be more than advisory. Skips an unfilled `<<FILL` body and any comparison where either side tokenizes to zero content words. | `CG-4 grammar: node '{target_id}' (reached via choice '{choice_id}' labeled {label!r} from node '{node_id}') has no content-word overlap between its opening sentence and the choice label in story '{story_id}' (advisory heuristic; may be a false positive, see module docstring)` |
| CG-5 | Advisory (opt-in) | **Visible-run cap** (added 2026-08-18, `UW-C297`, owner-approved): the longest chain of consecutive configurations offering the reader exactly ONE option must not exceed the band's choiceless-run cap, the same `run_cap_for_band` value CG-1 applies. Measured over the configuration graph, so it counts what the reader sees rather than what the node declares. CG-1 reads `len(node.choices)` and never reads `choice.condition`, so a corridor held open by conditions is invisible to it: `the-cinder-bazaar` walks a reader through **ten** consecutive one-option stops that CG-1 scores as a longest run of 3, because three nodes inside the chain declare 4, 4 and 2 choices. Runs only for a story that conditions something, since an unconditioned story's visible graph is its declared graph; skips a capped walk, since a corridor found in a fragment of the state space is not proof of one in the story. **Defers to CG-1 whenever CG-1 already fires** (declared run over the cap): what this rule adds is a corridor CG-1 cannot see at all, and a second finding under a second id would be noise. Deliberately NOT a repair of CG-1 or CG-2: 40 catalog nodes show one option in some configuration and nearly all are an ordinary closed gate, which is what conditions are for, so grading those would fire on the feature; and CG-1's choiceless *share* has no well-defined reading in configuration space, where one node appears once per reachable state of it. WARNING only, and ADVISORY rather than blocking because all four skeletons authored to the strict bar declare zero conditions and so cannot test the bound. **Flip condition**: becomes blocking once one conditioned book is authored to the strict bar and passes it deliberately. Fires on 2 of 68 committed skeletons. | `CG-5 grammar: a reader can walk {visible} consecutive stops offering one option, above band '{band}'s run cap {cap}, in story '{story_id}'. CG-1 sees a longest run of {declared} because it counts declared choices and this corridor is held open by conditions: {node_chain} (advisory only; the nodes in the middle of the chain may declare several choices each)` |
| CG-6 | Advisory (opt-in) | **Outbound staging** (added 2026-08-21, `UW-C312`, the outbound companion to CG-4): flags a decision node offering a choice whose label shares no content word (post-stopword) with the node's OWN body, i.e. the prose never stages what the choice promises; CG-4 is strictly inbound (does the arriving node acknowledge the choice just taken), so nothing asked this question before. Calibration (2026-08-21, over 39 committed known-good fills and the live one-shot books): known-good books dangle a median 3.7 percent of their labels (max 33 percent, terse gamebook labels), the under-delivered live books 65 to 85 percent, and one book that over-delivered its commission still dangled 73 percent, so the defect is model behavior rather than only a fill-rate symptom. Same lossiness caveat as CG-4 (token overlap is a weak proxy in both directions; a human makes the real call), hence WARNING and advisory. Skips a node whose body still carries a `<<FILL` directive, and any comparison where either side tokenizes to zero content words. Runs behind `is_fill_result` beside CG-4, not behind `enforce_grammar`. | `CG-6 grammar: node '{node_id}' offers choice '{choice_id}' labeled {label!r} but its own body shares no content word with the label in story '{story_id}': the prose never stages what the choice promises (advisory heuristic; may be a false positive, see module docstring)` |

---

## Naming (Advisory, Fill-Result Only, All Stories)

Implemented in `validator/naming.py`; wired into `validator/gate.py::run_gate`
immediately after the CG family and before SAFE-14. That position is step 9 in
`run_gate`'s own docstring, which numbers the two validator layers separately, and
step 7 in the Rule Application Order below, which groups them; the position is the
durable statement and the two numbers describe the same slot in different lists. Unlike the CG family, PN-1 is not
gated behind `enforce_grammar`: it runs whenever `run_gate` is called with
`context="fill_result"`, and does not run at all under the default `"skeleton"` context,
because a catalog skeleton's node bodies are `<<FILL ...>>` directives by construction and
there is no prose yet for the rule to read.

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| PN-1 | Advisory (fill-result only) | **Proper-noun introduction**: a proper noun (name of a companion, sibling, secondary character, town, etc.) must be introduced, on every path a reader can take to it, before or at the node where it is first named. "Introduced" means one of four contiguous patterns: a determiner-anchored pre-modifier ("her dog Biscuit"), an appositive ("Tock, her tiny wind-up mouse"), a copular gloss ("Biscuit is her dog"), or an address-term title ("Marshal Hedda"). Path-sensitivity is via `validator/continuity.py::dominating_nodes`: a gloss on one optional branch does not cover a reader who took another. Exempts the protagonist (read from the `HERO` sentinel, not inferred from frequency, because the known defect this rule was built for is 100% frequency across the book: see the module docstring), a self-glossing head noun the book writes in lowercase at least twice (one incidental use does not exempt, because a single miscased occurrence of the name itself would otherwise disable the rule for that name), an address term standing alone, calendar terms and interjections, and ALL-CAPS tokens. **This is a WARNING and never blocks**, on the same terms as CG-4 and CG-6: token-level naming is a heuristic and a human makes the real call. Two scope boundaries are deliberate and pinned by tests: the rule reads node bodies only and never choice labels; and a story whose surviving-names by prose-volume product exceeds the scan budget is skipped with an explicit `NOT CHECKED` WARNING rather than reported clean. Built to close the definite-noun-phrase check `validator/continuity.py` documents as unbuildable at 3.48 findings per node; proper nouns are a decidable subset (capitalization-marked, enumerable per book) where the general form is entailment. | `PN-1 naming: '{name}' is named at node '{node_id}' but the story never introduces it, so a reader meets the name with no idea who or what it is ({n} node(s) affected in story '{story_id}'; advisory heuristic, see module docstring)`, or `PN-1 naming: '{name}' is named at node '{node_id}' but it is introduced only on a branch a reader can skip ({branches}), so a reader meets the name with no idea who or what it is ({n} node(s) affected in story '{story_id}'; advisory heuristic, see module docstring)` |

---

## Safety (Always Human-Routed, All Stories)

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| SAFE-14 | Safety | **NOT IMPLEMENTED IN THE GATE** (`validator/safety.py` is a stub returning an empty report; the live screening is `moderation/pipeline.py`, outside the gate). Specified behaviour: **safety moderation**: moderation runs over all `body` and `label` text against the age-band policy. Any hit flags the specific nodes and forces mandatory human review. A safety flag does not auto-reject the story; it routes the generation job to `needs_review` (not `passed`), so the story cannot reach `published` until a global admin clears or escalates the flag. No auto-publish path exists when a SAFE-14 flag is set. | `SAFE-14 safety: node '{node_id}' flagged by moderation for age band '{age_band}' in story '{story_id}': {flag_detail} (requires human review)` |

---

## Policy Gate (Age-Band, All Stories)

Runs after Layer 1 passes and the Storybook parses, on the typed model plus the choice
graph (`validator/policy.py`). Most findings are ERROR-severity and blocking; PL-19 is
advisory (WARNING). PL-15..PL-18 are defined below; PL-19 (words-per-node), PL-20
(fastest-finish arc floor), and PL-21 (off-matrix rejection) are specified in
[ADR-011](./adr/adr-011-story-scale-framework.md) rather than duplicated here. PL-22
(band profile not configured, fail closed) is a runtime invariant rather than an
age-safety rule in its own right; it is defined below.

**Two axes, easily confused.** PL-17 measures *breadth*: how many decision and ending
nodes exist anywhere in the graph. PL-20, PL-25 and PL-26 measure *depth along a walk*:
how far the reader travels to finish, how soon they first steer, and how often they
steer after that. A story can satisfy every breadth floor while walking the reader down
a corridor, because a corridor with a wide branching bulge at the end still counts
plenty of decision nodes. That gap is what the depth rules close.

**Path-length rules grade in two tiers on purpose.** A *floor* violation (PL-20: too
short to be a story) is a correctness failure and blocks. A *ceiling* violation (PL-20's
long arc, PL-25's buried first choice) is a craft failure and warns, because the ERROR
tier means unpublishable and a narrow ceiling overshoot is not. PL-25 keeps one blocking
tier past `band_profile.ARC_CEILING_MULTIPLE` times the band ceiling, where the shape has
left the observed genre rather than merely run slow.

PL-25 and PL-26 are calibrated against Adams, Beckelhymer and Marr, "Choose Your Own
Adventure: An Analysis of Interactive Gamebooks Using Graph Theory," *Journal of
Humanistic Mathematics* 9(2), 2019 ([DOI 10.5642/jhummath.201902.05](https://doi.org/10.5642/jhummath.201902.05)),
which measured the original CYOA paperback corpus. The node-to-page equivalence that
lets those page measurements govern our node counts is not an assumption: ADR-011's
independently derived `_MIN_COMPLETE[("10-13", "short", "prose")]` is 11, matching the
paper's measured 11-page shortest playthrough exactly. Measurements and the calibration
invariants that guard them live in `validator/band_profile.py`.

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| PL-15 | Policy | **Ending-kind policy**: no ending whose `kind` is in the band's `forbidden_ending_kinds` (the no-death / no-capture rule). | `PL-15 policy: ending kind '{kind}' is forbidden for band '{age_band}' in story '{story_id}'` |
| PL-16 | Policy | **Content ceiling**: each `metadata.content_flags` value must not exceed the band's `content_ceiling` for that flag (ordered-enum comparison). | `PL-16 policy: {flag} '{level}' exceeds band '{age_band}' ceiling '{ceiling}' in story '{story_id}'` |
| PL-17 | Policy | **Floors**: distinct endings must meet `min_endings`; decision nodes (non-ending nodes with >= 2 choices) must meet `min_decisions`, both possibly scaled and counted from the graph. | `PL-17 floor: {n} ending(s)/decision node(s) below {scope} minimum {min} in story '{story_id}'` |
| PL-18 | Policy | **Topology verify**: declared `metadata.topology` must be admissible for the class inferred from graph metrics (networkx classifier). | `PL-18 topology: declared '{topology}' is not admissible for the graph (admissible: {admissible}) in story '{story_id}'` |
| PL-22 | Policy | **Band profile fail-closed**: added 2026-07-16 per the owner ruling (fail closed). When a story's age band has no configured `BandProfile` (`validator/band_profile.py::profile_for` returns `None`), the gate emits this single blocking finding and returns immediately instead of silently skipping PL-15/16/17 for that band. Unreachable through any valid, enum-constrained `age_band` today (a lockstep test pins the `AgeBand` enum against the configured profiles), so this is a runtime backstop, not a normal-path rule. See `validator/policy.py::validate_policy` and `tests/unit/test_policy.py::test_validate_policy_fails_closed_when_profile_is_none`. | `PL-22 policy: band profile not configured for band '{age_band}' in story '{story_id}'; refusing to validate age safety` |
| PL-23 | Policy | **Declared read time**: `metadata.estimated_minutes` is ADR-011 section 4's *fastest-finish* clock, the words on the shortest satisfying path divided by the band's `band_profile.reading_pace_wpm` anchor. A declared value differing from the derived one by more than 25% warns. Advisory: a rounded or deliberately padded editorial figure is legitimate, but the field is what a child sees when choosing a book, so a large mismatch is a broken promise. Skipped when the fastest-finish path is under `_MIN_PATH_WORDS_FOR_CLOCK` (200) words, where the derived clock is noise. Enforced at **both** contexts `run_gate` accepts, skeleton and fill result, with no code difference between them: node word counts come from `policy.node_word_count`, which reads a `<<FILL ... words=N ...>>` directive's declared `N` for an unfilled skeleton node and the real word count for filled prose. A skeleton can therefore already declare a clock its own word hints cannot satisfy before a single word of prose exists (AL-391). Measuring that directly (AL-395, `UW-C261`) found the catalog's breaches run in both directions and need different remedies, so `validator/policy.py::read_time_drift` adds a direction-aware measurement (reusing this same rule's `words_on_shortest_satisfying_path` search rather than a second implementation) and `scripts/check_skeleton.py` prints its result unconditionally (no `--headroom`/`--strict` needed) as `skeleton clock: PL-23 estimated_minutes {declared} is {UNDER\|OVER}-DECLARED vs ...`. This is a read-only report alongside the finding below; it does not change PL-23's severity, message, or applicability. | `PL-23 clock: declared estimated_minutes {declared} differs from the derived fastest-finish clock {derived} min ({words} words on the shortest satisfying path at {wpm} wpm) by {drift} in story '{story_id}' (advisory only)` |
| PL-24 | Policy | **Ending mix**: two advisory shape checks over the ending set, which PL-15 (forbidden kinds) and PL-17 (ending count) do not cover. (a) No single `ending.kind` may exceed 60% of endings. (b) A winnability floor that is **style-aware**: prose must have at least 10% positive-valence endings, while a gamebook must have at least `max(3, ceil(5% of endings))` distinct positive-valence endings (ruled 2026-08-09, review Part 4 R1; previously an absolute 3, which a 200-ending book could clear with the same 2-3 wins as a 30-ending one). The gamebook rule is a scaled count, not a raw share, because a share floor calibrated against the committed corpus would flag every gamebook (all sit at 2-5% positive against prose's 15-70%); that spread is ADR-011 section 5's declared 'few wins and many fails' shape, not nine defects. | `PL-24 mix: ending kind '{kind}' is {n} of {total} endings ({share}), above the {ceiling} share ceiling in story '{story_id}' (advisory only)` |
| PL-25 | Policy | **Depth to first decision**: nodes on the shortest path from `start_node` up to and including the first node offering >= 2 choices must sit inside the band's `band_profile.first_decision_window`. Past the ceiling WARNS; past `ARC_CEILING_MULTIPLE` x ceiling is an ERROR. Under the floor is an ERROR in one tier: a story opening on its own first choice gives the reader no situation to choose about, and unlike a too-long prologue there is no degree of it that reads as merely slow. The drafting guide states the same constraint from the other side (max choiceless stops in a row is at least 1 in every band). Introduced as a WARNING because 20 committed skeletons predated the rule; escalated once those were fixed and the catalog swept clean (AL-086). Applies to every story with a configured band, scale-classified or not, because a buried first choice is a band-level pacing defect rather than a scale one. A story with no decision node at all is left to PL-17, which already floors decision count. Anchored on JHM 2019 Table 4 (pages to first decision: median 4, range 2-8.25). | `PL-25 opening: first decision is {depth} node(s) in, past the band '{age_band}' ceiling {ceiling}[ and its hard limit {hard}] in story '{story_id}'` (past ceiling: WARNING, or ERROR when also past the hard limit); `PL-25 opening: first decision is {depth} node(s) in, under the band '{age_band}' floor {floor} in story '{story_id}'` (under floor: ERROR, blocking) |
| PL-26 | Policy | **Decision density on the fastest finish** (advisory): nodes per decision along the fastest satisfying finish must not exceed `band_profile.nodes_per_decision_ceiling`. PL-20 and PL-26 measure the same *minimum node count* but deliberately do not read the same walk. Equally short paths all share a length, so PL-20's tiers are indifferent to which one is picked; they can differ in decision count, so PL-26 reads `policy._fewest_decision_shortest_path`, the equally fast walk carrying the FEWEST decisions, i.e. the worst density among them. That is forced by the rule being a ceiling: it must fire when *any* equally fast walk is a corridor. Sharing PL-20's arbitrary tie-break instead made the verdict flip on node renaming alone, mismeasuring 19 of 58 eligible catalog skeletons (AL-094). A **ceiling only**, deliberately: the rule guards the corridor, a story that satisfies every PL-17 breadth floor while walking the reader past few or no choices. It does not bound density from below, because a shortest path is biased toward decision nodes by construction (out-degree >= 2 makes a node likelier to sit on a fast route) while JHM's 3.28 was measured corpus-wide, so comparing them on the low side compares different quantities. A genuine 'choice gauntlet' guard would have to measure whole-graph density; see AL-084 / UW-C28. The ceiling is keyed by `narrative_style`, following the `_ENDINGS_FRACTION` and `_WORDS_PER_NODE` precedent: prose admits up to 6.0 nodes per decision (above the JHM 3.28 mean with room), a gamebook up to 4.0, because a numbered-section gamebook ends nearly every section in a choice by genre convention and judging it against a prose bar would let a real gamebook corridor pass. A fastest finish offering no decision at all also warns. Requires a declared `length` and `production_eligible`, so it is skipped for unclassified stories. | `PL-26 density: fastest finish averages {density} node(s) per decision ({n} decision(s) over {total} nodes), over the {ceiling} advisory ceiling in story '{story_id}'` |
| PL-27 | Policy | **Fill-result residue** (added 2026-08-13, AL-325; extended to choice labels 2026-08-17, AL-430): no node body **and no choice label** of a document validated as a *fill result* may still hold a `<<FILL ...>>` directive. The label half matters because the chunked fill writes labels as well as bodies, and a label is reader-visible button text: with only the body checked, a reply that echoed its own directive back under `choices` produced a book that cleared this gate unblocked with a raw directive rendered on a button. Runs only under `run_gate(..., context="fill_result")`; under the default `"skeleton"` posture it does not run at all, because a catalog skeleton is directives by construction and every other checker's tolerance for them is correct there. This is the gate's only floor against a book that was never written: `choice_grammar` skips a directive body, `sentinel_integrity` documents the same tolerance, and `reading_level.measure_book` returns `None` for one, so four locally-correct abstentions aggregate to a clean verdict on an empty book. Ordered before the rest of the policy layer so the first finding on an unwritten book names the cause rather than a downstream word-count or reading-level symptom. | `PL-27 policy: node '{node_id}' of story '{story_id}' was validated as a fill result but its body still holds a '<<FILL' directive, so the node was never written`, and `PL-27 policy: choice '{choice_id}' of node '{node_id}' in story '{story_id}' was validated as a fill result but its label still holds a '<<FILL' directive, so the choice text was never written` |
| PL-28 | Policy | **MVP firewall** (added 2026-08-16): a document validated as a *fill result* may not declare `metadata.production_eligible = false`. ADR-011 section 1a creates a below-Short **MVP/Test tier** for cheap prototyping shells, and its Consequences require the tier be firewalled from production: a seed "must never be selectable for a child-facing story. The selection layer, not just the validator, has to enforce the exclusion." The selection layer does: `generation/skeleton_match.py::_production_candidates` drops any skeleton with the flag unset, so the automated request path cannot pick a seed. The **manual** path had no such guard, so a seed filled by hand and imported through `generation/import_cli` reached the store, publishing and a child's library with nothing reading the flag. The flag also makes the gate *more* permissive, because `layer1` budgets an MVP story against the loosest cell, so a seed was both easier to validate and unblocked to publish. Context-gated exactly like PL-27: silent under the `"skeleton"` posture, where a seed is a legitimate catalog object that `check_skeleton.py --allow-mvp` exists to inspect. | `PL-28 policy: story '{story_id}' declares production_eligible=false (the ADR-011 MVP/Test tier) and so may not be imported as a child-facing book; MVP seeds are prototyping shells and are budgeted against the loosest cell` |
| PL-29 | Policy | **Band topology row** (added 2026-08-16): the declared `metadata.topology` must appear in the band's ADR-011 section 7 row. Independent of PL-18 and both must hold: PL-18 asks whether the label fits the graph's *shape*, PL-29 asks whether the band may use that label at all. `branch_and_bottleneck` is a well-formed shape that 3-5 and 5-8 may not declare (they allow `loop_and_grow`/`time_cave`, plus `open_map` at 5-8); it first becomes legal at 8-11. The table lived only in `mutation/identity.py`, so the offline mutation core enforced the row and the gate authors actually run did not: three skeletons drafted 2026-08-16 declared `branch_and_bottleneck` at the young bands, passed `check_skeleton --strict` clean, and failed only when the mutation operators ran over them. The table now lives in `validator/topology.py`, which both layers already import, so one definition serves both. Every committed skeleton satisfies its row, so the rule blocks nothing that exists. | `PL-29 topology: band '{band}' may not declare '{topology}' (allowed: [...]) in story '{story_id}'` |

---

## Series (Cross-Book Chain, Series Stories Only)

Runs over a whole chain rather than one story (`validator/series.py::validate_series`), so it is
invoked by the publishing path (`publishing/service.py`) and by the offline chain checker, not by
`run_gate`. A chain is the set of books sharing one `series_id`.

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| SR-1 | Series | **Series identity**: every book in the chain must declare `metadata.series`, and all books must share one `series_id`. | `SR-1 series: book '{book_id}' declares no series metadata` / `SR-1 series: chain spans multiple series ids {ids}` |
| SR-2 | Series | **Index contiguity**: `book_index` values must form a contiguous `1..N` with no repeats. Note this checks contiguity only, not that indices reflect narrative order. | `SR-2 series: book_index values {indices} are not a contiguous 1..N` |
| SR-3 | Series | **Entry node**: a declared `series_entry_node` must exist in the book's nodes, and any book above index 1 must declare one. | `SR-3 series: book '{book_id}' declares series_entry_node '{node}' which does not exist` |
| SR-4 | Series | **Final flag**: a book below the highest index must not be `is_final`. A non-final top book is permitted, which is how a chain stays open for later books. | `SR-4 series: book {index} '{book_id}' is marked final but is not the highest index` |
| SR-5 | Series | **Continuity**: each non-final book must have a satisfying (win) ending, and the next book must declare an entry node, so the chain's declared initial state is reachable from a win. | `SR-5 series: non-final book {index} has no satisfying ending` |
| SR-6 | Series | **Episodic bands**: a young-band or Tier-1 book is episodic and must not carry state. | `SR-6 series: book '{book_id}' is a young or Tier-1 story and must not declare carries_state` |
| SR-7 | Series | **Carry uniformity**: every book in a chain must agree on `carries_state`; a chain cannot be half stateful. | `SR-7 series: chain disagrees on carries_state` |
| SR-8 | Series | **Carried-variable integrity** (added 2026-07-25): on a `carries_state` chain, a variable declared by book N must survive into book N+1. The client seeds a continuation by variable **name** and clamps carried ints into the *receiving* book's bounds, silently, so a narrower receiving range rewrites every outcome outside it (ERROR: data loss), a changed type makes the carried value be skipped entirely (ERROR), and a variable the receiver does not declare is dropped without trace (WARNING, since a closed storyline is a legitimate authorial choice). | `SR-8 carry: '{var}' is [{lo},{hi}] in book {n} but [{lo2},{hi2}] in book {n2} '{book_id}'; the receiving range must contain the sending range or the client clamps carried outcomes away` |
| SR-9 | Series | **A satisfying exit must leave the next book winnable** (added 2026-07-26, B3). For a `carries_state` chain, every distinct variable state at a satisfying ending of book N is carried into book N+1 under the WS-G G3 rules (name match, type match, int clamp), and book N+1 must still work from there. Closes the gap SR-5 and Layer 2 both leave open: SR-5 tests ending existence and never traces state across the join, and Layer 2 only ever walks from `start_node` with the declared initials, so the state a continuation reader actually arrives with is outside every other rule's view. Two distinct failures are reported. (a) **The receiving book stops being sound**: its Layer-2 rules are re-run seeded from the carried entry, and any ERROR not also raised from its own declared initials is a cross-book defect. (b) **The continuation is unwinnable**: no satisfying ending is reachable from the carried entry, so a reader wins book N into a dead campaign. Entry states are sampled up to `MAX_ENTRY_STATES` (64, `validator/series.py`); exceeding that, or a capped walk, is reported as a truncated check rather than silently passed. **The receiver is walked from its own `series_entry_node`, not its `start_node`** (`UW-C296`, 2026-08-18): the reader enters there, and seeding the walk at `start_node` validated a path nobody takes. An entry node absent from the story falls back to `start_node`, matching the client. | `SR-9 series: book {index} '{book_id}' can be completed with carried state {carried}, but entering book {next_index} '{next_id}' with that state raises Layer-2 errors it does not raise from its own declared initials: {new_errors} (an acquisition branch for a carried variable must be redesigned, not copied)` / `... leaves no satisfying ending reachable (the reader wins book {index} into an unwinnable continuation)` / `SR-9 series: book {index} '{book_id}' has more than {max} distinct satisfying exit states or capped its walk, so the continuation handoff into '{next_id}' was checked over a truncated sample` |
| SR-10 | Series | **Prose reuse across the chain** (added 2026-08-23, `AL-564`). No two books of a series may share a contiguous passage of more than `SERIES_MAX_SHARED_RUN_WORDS` (15) words, nor have more than `SERIES_MAX_SHARED_RUN_COVERAGE` (2%) of a book sitting inside shared passages of 15+ words. Measured on run LENGTH, not on total overlap, because a series is the one relationship where sharing wording can be deliberate: a repeated refrain is short by construction and cannot reach either bound, so the rule permits one with no declaration, allowlist, or authoring step, while a reused paragraph fails. Closes the gap every other prose comparison leaves: the anti-template guard and the sibling-gram advisory both select their partner by same skeleton within the same family (`select_atg_comparison_partner`), so a chain of different skeletons is unreachable by both, and SR-1..SR-9 compare ids, entry nodes, carried variables and reachability while never comparing a word of prose. Calibration (2026-08-23, all 465 pairs of the committed corpus, recomputed by `tests/unit/test_series.py::test_the_fifteen_word_bound_sits_in_an_empty_gap_in_the_corpus`): the 464 non-series pairs run 2 to 8 shared words (3 at 2, 103 at 3, 120 at 4, 155 at 5, 69 at 6, 13 at 7, 1 at 8), every one at 0% coverage; the brass-lantern pair `the-harrowstone-keep` / `the-sunken-temple` shares a 98-word run across 246 passages of 15+ words, 18.6% of book 2 (the same 6,691 covered words are 16.8% of book 1's 39,935 and 18.6% of book 2's 35,920; `RunProfile.coverage` reports the worse-affected side, so 18.6% is what the 2% bound sees). Choice labels are excluded, since a shared skeleton supplies them identically (`AL-563`). | `SR-10 series: books '{a}' and '{b}' reuse prose; longest shared passage {n} words (limit 15), {pct} of a book inside shared passages of 15+ words (limit 2%). A repeated refrain is fine and cannot reach these bounds; rewrite the shared passages instead` |

**Remaining gap** (AL-038): SR-8 now covers the declaration side, but nothing yet records *which*
carried values were clamped or dropped at read time. A per-variable carry audit in
``startContinuation`` would make a corrupted carry visible to a reviewer rather than only detectable
from the declarations, and the continuation offer is still not gated on reaching a satisfying ending,
so a reader who loses book N can still be handed book N+1.

---

> **Note on SR-8 and this section.** Until 2026-08-18 this document carried the Series rules
> TWICE, and the two SR-8 rows contradicted each other: one documented the implemented rule with
> the message template the code emits, the other called the id RESERVED and told readers not to
> reuse it. SR-8 is implemented, and the 8-11 series validation on that date showed it firing
> three distinct ways: a receiver narrowing a carried int below the sender's reachable range
> (ERROR), a receiver dropping a carried variable (WARNING), and a receiver changing a carried
> variable's type (ERROR). The duplicate section and its reserved row are removed; SR-9 was only
> in the removed copy and has been folded into the table above (`UW-C298`).

## Character Envelope (Participating Books Only)

Rules proving that a book declaring `accepts_character` is safe across exactly the states a seeded reader can
arrive in. Enforced by `validator/character.py`; specified in
[ADR-028](./adr/adr-028-persistent-reader-characters.md) decision 5. Like the `SR` family these prove a
cross-artifact handoff rather than a within-story property. All are ERROR severity and all set `blocked`.

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| CH-1 | Character | **Vocabulary and declaration**: every `accepts_character` name is in the canonical vocabulary and is declared in `variables` with a matching type. | `CH-1 character: accepts_character declares '{name}', which is not in the canonical vocabulary {names}` / `CH-1 character: accepts_character declares '{name}' but the story declares no variable of that name` / `CH-1 character: '{name}' is declared as {actual} but the canonical vocabulary defines it as {expected}` |
| CH-2 | Character | **Range equality**: each envelope range equals the declared variable's `min`/`max`. Equality, not containment: G3's runtime clamp is to declared bounds, so a narrower envelope would silently admit states the validator never walked. A variable with absent `min`/`max` cannot equal a bound at all, so an opted-in variable must declare both. | `CH-2 character: accepts_character range for '{name}' is {a}-{b} but the variable declares {c}-{d}; they must be equal` / `CH-2 character: '{name}' is in accepts_character but declares no min/max bounds; an opted-in variable must declare bounds equal to its envelope range {a}-{b}` |
| CH-3a | Character | **Union dead branch**: a conditional choice must be visible in at least one configuration across the baseline walk (declared initials) and a walk from every `accepts_character` entry state, taken together. Union-quantified rather than per-state, unlike CH-3b: a choice invisible in one entry state but visible in another, or at baseline, is legitimately state-gated, not dead. Tier-2 only (mirrors Layer 2's own tier gate); walks once per entry state plus once for the baseline. | `CH-3a character: choice '{choice_id}' on node '{node_id}' is never visible in the baseline walk or in any of the {n} accepts_character entry states, in story '{story_id}'` |
| CH-3b | Character | **Per-state regression**: an `accepts_character` entry state must not raise an L2-9 (stateful dead end), L2-10 (loop escape), or L2-14 (all-forbidden decision) that the book's own baseline walk (declared initials) does not already raise. Per-state, unlike CH-3a: whether a configuration is a dead end, cannot escape, or offers only forbidden outcomes is a property of the variable state it is reached in. The baseline diff is keyed on rule id, node id, choice id, and message (message embeds `var_state`), deliberately wider than SR-9's shared `rule_id\|node_id` signature: none of L2-9/L2-10/L2-14 ever set `choice_id`, so without the message two dead ends on the same node at two different entry states would collapse into one signature and mask the second as "already known". Tier-2 only. | `CH-3b character: accepts_character entry state {state} raises {rule_id}, which this book's own baseline walk does not: {message}` |
| CH-4 | Character | **Satisfying-ending reachability**: every `accepts_character` entry state must still be able to reach a satisfying ending. Reuses SR-9's own reachability test (`satisfying_ending_reachable`) rather than a second implementation, so "the reader can still win" cannot drift between the series-continuation case and the character-envelope case. Tier-2 only. | `CH-4 character: accepts_character entry state {state} cannot reach any satisfying ending, in story '{story_id}'` |
| CH-5 | Character | **Envelope size**: the envelope admits no more entry states than `MAX_ENTRY_STATES` (64, `validator/series.py`). An ERROR rather than SR-9's truncate-and-warn, because an envelope is declared rather than emergent. | `CH-5 character: accepts_character admits {n} entry states, above the {cap} cap; narrow a range or declare fewer variables` |
| CH-6 | Character | **Namespace reservation, both directions**: a canonical variable name may be declared only by a book that opted in *and* covered it in the envelope. The opt-out half rejects a book that declares no `accepts_character` but still declares a canonical name (G3 carry is name-match, so a book that never opted in can still be seeded). The opt-in half rejects an opted-in book that declares a canonical-named variable its envelope omits: CH-1 only ever walks envelope -> variable, so this converse direction (variable -> envelope) needs its own check, or an uncovered canonical variable would still be seeded by G3 over states this book's Layer 2 walk never proved. | `CH-6 character: '{name}' is a reserved canonical character variable, but this story declares no accepts_character envelope; rename the variable or opt in` (opt-out half) / `CH-6 character: '{name}' is a reserved canonical character variable declared by this story, but accepts_character does not cover it; add it to the envelope or rename the variable` (opt-in half) |
| CH-7 | Character | **Series exclusivity**: a book declaring `accepts_character` is not a non-first book of a `carries_state` series. Two independent sources of carried state in one book is unproved in v1. | `CH-7 character: book {index} of state-carrying series '{series_id}' may not also declare accepts_character` |
| CH-8 | Character | **Build-node cost pre-flight**: a book whose base closure exceeds `cap / arity` configurations cannot host an archetype build node. `arity` is always `len(ARCHETYPE_ROSTER)` (6), the canonical vocabulary's real-archetype count; it is never derived from the envelope's declared span, because that span is attacker-influenced (a declared `1..6` span still names all six archetypes but would read as arity 5 if the span's own width were trusted). Measured at 6.00x for a six-way node, so the threshold is exactly 16,666 configurations: `100_000 // 6`, floor division against the 100,000 walk cap. Fails here with a named cause rather than as an opaque L2-12 cap ERROR. Fires on any book whose envelope declares an `archetype` span at all, including a carrier-only later book in a series that never sets `archetype` itself and pays no real build-node cost; that is a deliberate over-approximation, not a claim the book actually contains a build node. | `CH-8 character: a {arity}-way build node needs a base closure at or under {threshold} configurations, which this book exceeds; it cannot host the archetype build-node idiom` |

---

## Rule Application Order

The validator applies rules in this order:

1. L1-1 through L1-7 (graph; all stories). Stop if any L1 rule fails.
2. PL-15 through PL-21, the PL-22 fail-closed guard, and PL-23 through PL-26
   (age-policy gate; all stories). PL-19's story-mean sub-check, PL-23,
   PL-24, PL-26 and PL-25's ceiling short of its hard limit are advisory;
   the rest block, including PL-25's floor. PL-22
   fires only when the band has no configured profile, in which case it is the sole
   finding and PL-15..PL-21 do not run. PL-25 runs for any story with a configured
   band; PL-20 and PL-26 additionally require a declared `length` and
   `production_eligible`, so an unclassified story is measured on breadth only.
3. L2-8 through L2-15 (state-space; Tier-2 only). Stop if any L2 rule fails; L2-13 is a
   non-blocking scale advisory and never stops the run.
4. CH-1, CH-2, CH-3a, CH-3b, CH-4, CH-5, CH-6, CH-7, CH-8 (character envelope; ADR-028,
   participating books only). CH-3a, CH-3b, and CH-4 walk the story once per
   `accepts_character` entry state plus once for the baseline, and run only for
   Tier-2 stories; see `validator/character.py`. CH-8 runs one further baseline
   walk, unconditioned by tier or the CH-3a/CH-3b/CH-4 envelope-size gate above,
   but only when the envelope declares an `archetype` span; it catches a build
   node that would multiply that walk past the cap before L2-12 does, using a
   fixed vocabulary-derived arity rather than the declared span's own width.
5. RL-13 (advisory; all stories). Log warnings; continue.
6. CG-1 through CG-6 (advisory; all stories): CG-1, CG-2, CG-3 and CG-5 run **only
   when `run_gate` is called with `enforce_grammar=True`**, which no production
   caller does today; CG-4 and CG-6 run when the gate marks the story a fill
   result (`is_fill_result`). Log warnings; continue.
7. PN-1 (advisory; fill-result only): runs only when `run_gate` is called with
   `context="fill_result"`, and not at all under the default `"skeleton"` context.
   Flags a proper noun a reader can reach before the prose introduces it. Log
   warnings; continue.
8. SAFE-14 (moderation; all stories). Flag nodes; block auto-publish if flagged.
   **NOT IMPLEMENTED IN THE GATE.** `validator/safety.py::check_safety` is a Phase-2 stub
   that returns an empty report for every story, so this step cannot produce a finding and
   listing it here as a live step read as coverage the gate does not have (`UW-C292`). The
   safety coverage that does exist runs OUTSIDE the gate, in `moderation/pipeline.py`,
   which screens every node body and routes a story to `needs_review`. Keep this entry so
   the intended order survives, but do not count it when reasoning about what the gate
   enforces today.
9. SR-1 through SR-9 (series chain; series stories only) run **later and elsewhere**, at
   publish time over the whole chain rather than inside `run_gate` over one story. A book
   can clear steps 1-7 at generation time and still be refused at publish by an SR error.

Stopping at the first Layer-1 failure is allowed for efficiency; all Layer-1 failures may also
be collected in a single pass before reporting, which is preferred for repair-stage prompts
(Stage C needs all failing node ids, not just the first).

---

## Failure Report Format

Each failure in a validation report carries:

```json
{
  "rule_id": "L1-6",
  "severity": "error",
  "story_id": "...",
  "node_id": "n_cave",
  "choice_id": "c_lantern_door",
  "message": "L1-6 logic: condition in story 'dungeon-escape' at choice 'c_lantern_door': operator 'if' is not whitelisted (var='courage', declared_type=int)"
}
```

The repair-stage prompt (Stage C) receives the array of failure objects and instructs the model
to address only the flagged node ids and rule violations, changing nothing else.

---

## Related Documents

- [Tech Spec: Validation Gate](./tech-spec.md#validation-gate-deterministic-no-llm)
- [Story Runtime Semantics v1](./runtime-semantics.md)
- [Condition Evaluator Specification](./condition-evaluator-spec.md)
- [Configuration Cap Worked Example](./configuration-cap.md)
- [ADR-006: In-house condition evaluator](./adr/adr-006-conditions-inhouse-evaluator.md)
