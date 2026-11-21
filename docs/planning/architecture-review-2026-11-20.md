---
title: "Architecture review of the story-development pipeline"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Independent, read-only review of how the story pipeline is architected, written after two days
  in which each iteration surfaced another structural defect. Diagnoses the missing story-meaning layer,
  ranks higher-level changes with cost and evidence of success, lists what to stop, and proposes a
  sequence that keeps the family test on track. For owner review; not yet ratified."
tags:
  - planning
  - generation
  - architecture
---

# Architecture review: the story-development pipeline

Date: 2026-11-20. Reviewed at commit `096852f`. Read-only: no repo file was changed, no generation was
run, no provider was called. Numbers marked "measured here" come from read-only scripts run for this
review against the committed tree; everything else cites the file it came from.

## Executive summary

The architecture does need to change, but in one place rather than everywhere. The runtime format,
the engine, the Layer 1 and Layer 2 gate, safety moderation and mandatory human approval are sound
and should stay. What is missing is any explicit representation of what a story means.

As built, the pipeline is a shape factory with a prose stage attached. It represents, checks and
versions topology, scale, safety policy, reading level, theme slots and cross-book sameness. It
represents nowhere on the production path who wants what, what the reader knows at each node, what
a choice costs, or what a plant pays off as. That meaning exists only as free text in skeleton
beats, in the model's working memory during one call, and in prose afterwards. Every recent
surprise is a meaning defect surfacing in a system that can only see shape and surface text, which
is why each fix lands as another prompt rule, lint or regex and the next read finds a new variant.

Three changes remove the class: (1) a per-book Story Plan (cast, hidden truth, fact ledger with
per-node requires and establishes, named plant and payoff threads) generated before prose (human-approved for catalog books; revised,
see addendum) and checked structurally; (2) replacing free-text beats with typed directives
compiled from graph plus plan, so the instruction nearest the passage is never one nobody reviewed;
(3) evaluation led by reads (a validated model continuity reader, then child reading trails), with
regex prose detectors demoted to smoke tests. Conditional passage text in the schema is the fourth,
later change.

Stop catalog growth by mutation, cross-book diversity research, retrofit state promotion, strict
remediation of 66 legacy skeletons and small-n prompt experiments. The family test is unaffected:
it runs on hand-revised books, which should be treated as authored books and used as the gold set.

---

## 1. What the architecture optimizes for

### 1.1 Follow the data: where decisions are made

| Stage | Decision made | Input it decides on | Meaning visible to it |
| --- | --- | --- | --- |
| Skeleton authoring | graph, beats, labels, endings | a cell brief rendered from numeric rule sources plus one premise line (`scripts/generate_drafting_brief.py:1-19`, `scripts/compare_skeleton_authors.py:1-9`) | whatever the author held in mind; none persisted except beat text |
| Skeleton acceptance | pass or fail | scale, topology, clocks, choice grammar, endings depth (`scripts/check_skeleton.py --strict`) | none |
| Skeleton match | which skeleton a request gets | cell (band, length, style), recency, theme-tag overlap, weighted random (`generation/skeleton_match.py:709-749`) | theme tags only |
| Binding | slot values | theme contract, denylists (`generation/binding.py`, `*.contract.json`) | nouns only |
| Fill | every sentence the child reads | whole skeleton in one call, about 1,500 words of rules plus a 4,200-word guide (`generation/templates/fill_bound.md`) | beats, one at a time, as free text |
| Stage 1 fidelity | did prose depict the beat | beat text versus prose (`moderation/fidelity_review.py:33-40`), advisory, fails open (`:8-9`) | beat text only |
| Gate | block or pass | L1, PL, L2, CH errors only (`validator/gate.py:39-44`) | none |
| Moderation | hard block on safety; rest soft or advisory | prose (`moderation/stages.py:1-8`) | safety only |
| Human approval | publish | flagged passages and findings (`api/review_surface.py:1-7`) | whatever the approver reads unaided |

The only stage that creates story meaning is the fill, and it does so implicitly, in one pass over
100 to 600 nodes, with no plan it wrote down and nothing downstream that can ask what it intended.

### 1.2 What is explicit and what is implicit

Explicit, typed, checked: node and choice ids, targets, conditions and effects (`storybook/models.py:702-737`);
ending kind and valence; band, length, style, topology, word budgets (ADR-011 is 640 lines and every
section is about size and shape, `docs/planning/adr/adr-011-story-scale-framework.md:30-42`); theme slots
and their denylists; lineage hashes; cross-book similarity.

Implicit only:

- **Characters, their wants and voices.** Nowhere. A contract slot holds a name string.
- **The hidden truth of a mystery.** Nowhere, which is how `the-hollow-lighthouse` told two
  incompatible backstories on disjoint branches (AL-773).
- **What a node may presuppose.** Nowhere on the production path. `validator/continuity.py:29-33`
  records that the purely structural version flags 3,815 of 4,472 nodes and the prose version yields
  3.48 findings per node (`:21`), and concludes it cannot be a rule. That conclusion is correct for a
  system with no fact layer and is the strongest internal evidence that one is needed.
- **What a plant is and what its payoff shows.** A promoted skeleton's variable is named after the
  button that set it (`did_start_beacon_steps`, `skeletons/8-11/the-lantern-keepers-list.json`
  `variables`), and the payoff directive is "show the earlier choice returning"
  (`docs/planning/structural-verification-2026-11-20.md` section 4.2). The object, person or knowledge
  that returns is invented by the fill model each time.
- **The hero's want and the stakes.** A premise line in the brief; not carried per node.

A fact graph with `entry_state`, `establishes` and `forbids` per node does exist, with a merge-closure
checker (`scripts/check_narrative_contract.py:18-22`, NC-1). It covers 2 of 84 skeletons (measured
here: 2 `.narrative.json` sidecars), is read by nothing on the request path, and was designed in
August to increase diversity across books, not coherence within one
(`docs/planning/skeleton-narrative-redesign-proposal-2026-08-09.md:1-10`).

### 1.3 The optimization target, stated plainly

In descending order of how much machinery serves each: safety and well-formedness (blocking);
genre-faithful scale (ADR-011, strict checks, 84 skeletons holding 15,514 nodes, measured here);
cost and vendor portability (chunking exists "for portability, not for feasibility",
`generation/chunking.py:8`); and distinctness between books (the whole SQ-01 to SQ-24 plan, WS-0 to
WS-8, mutation and flywheel, the 4.0 shared-four-gram budget). August produced 682 of the 798 lessons
in the log (measured here) and almost all of that month's research asked "are two books on one
skeleton too alike".

A good children's CYOA needs something else first: that inside one book the choices are real, the
world is consistent, people talk, and a failure gives something back. Nothing was measuring that
until an adult read the books on 2026-11-20. The project spent its research budget on a problem a
family meets on its fifth book from one skeleton, and none on the problem every reader meets by the
middle of the first.

### 1.4 What the skeletons actually contain

Reading real shells changes the picture more than any document does.

- `skeletons/8-11/the-clockwork-menagerie.json`: beats describe geography and convergence, not drama.
  `av_conv`: "both ways bring {HERO} to {ROUTE_A_DOOR}". The committed fill dutifully opens "Both ways
  through the aviary brought Nia to the same place at last". The fill did what it was told.
- `skeletons/16+/the-last-train-north.json`: beats are a replicated functional template. `g0a3_1`:
  "a first detail snags her attention". `g0a3_2`: "offers {HERO} two ways to read it; one is direct and
  risks notice, the other is patient". `g0a3_3a`: "yields a hard, specific fact". `g0a2_4`: "both
  readings of {G0A2_CHAR} converge on the same small wrongness". This is a story-shaped loop with the
  story removed; there is no fact for the fact node to yield.
- Catalog-wide (measured here, crude regex): 3,488 merge nodes; 21 of 84 skeletons declare variables,
  six of them promoted on 2026-11-20; 264 conditional choices in total across 15,514 nodes.
- Scale: 13-16 and 16+ shells run to 551, 632 and 677 nodes. No author, human or model, holds the
  meaning of 600 nodes without a ledger, so at that size structure can only be produced by pattern
  replication, and it shows.

---

## 2. Systemic failure modes

Each of the owner's five hypotheses is tested first, then the ones the code adds.

### F1. Meaning has no representation, so it cannot be planned, passed along or checked (root cause)

Confirmed, and it is the parent of most of the others. Symptoms it explains directly: facts in hubs
that only some routes earned (AL-788); two backstories (AL-773); three contradictions an editor's own
replay missed (AL-790); plant leaks into unplanted routes and a payoff that leans on another payoff
(AL-799); a plant whose content everyone already has (AL-800); merge notes that can list which
passages arrive but not what each establishes (`generation/merge_notes.py:52-58`), leaving the model
to guess. Every one of those is a one-line set comparison once facts have ids.

### F2. "Structure authored before and separately from meaning": true, but reframe it

Order is not the defect. Interactive fiction is routinely planned structure-first. The defect is that
**the skeleton beat is one untyped string carrying four different things**: the dramatic event,
narration of the graph ("both ways bring", "every path ends here", "BOTTLENECK"), an enumeration of
the buttons ("can turn toward A1, or toward A2"), and, since 2026-11-20, tool-written operating
instructions ("PLANT SITE: these options are no longer cosmetic", `mutation/state_promotion.py:1014`;
"MERGE: readers reach this scene by more than one route", `:1070`).

That string is also the highest-authority instruction in the system. The fill template says prose
"MUST depict this exact beat" (`generation/templates/fill_bound.md:57`) and Stage 1 exists to check
that it did (`moderation/fidelity_review.py:33-40`). So the verification finding that "a prompt rule
loses to a beat that contradicts it" (AL-797) is not model disobedience. It is the architecture's
stated precedence working as designed, applied to text nobody reviewed for craft. 93 percent of
recaps sit on beats that enumerate options because the beat asked for the enumeration.

### F3. The frozen and generated split is at the wrong joint

Added. The pipeline freezes labels' meaning, beats, fork design and ending placement, and generates
surface prose. The November defects were almost all in the frozen layer: cosmetic forks, skeleton
labels in the wrong person (the new prompt "fixed" labels by rewriting 0 of 174, AL-798), a cautious
choice wired to the setback (AL-772: "a fill cannot repair it"), give-up endings following beats that
end on loss. The hand revisions that worked changed exactly what the pipeline forbids: measured here,
the four revised books add 11 to 15 nodes and 4 variables each relative to their skeletons, with 8 to
10 conditional choices. They are no longer fills of their skeletons (AL-784); they are authored books.
The valuable edit and the permitted edit do not overlap.

### F4. One body string per node forces lowest-common-denominator prose

Added, and I think under-recognized. `Node.body` is a single string (`storybook/models.py:731`) with
no conditional text; the revision recipe states the consequence: "Whatever a body says must be true
on every path that can reach it and in every state" (`.claude/skills/cyo-author/reference/story-agency-revision.md:42-44`).
In a branch-and-bottleneck graph the later a node is, the less it is allowed to say, which is
precisely "opens well and stops behaving like a CYOA by the middle". State can only show through
which buttons appear or through inserted nodes, so payoffs are expensive (a dozen new nodes per book)
and rare (2 to 8 percent of readers on retrofits, AL-783). ADR-001 listed conditional text as a
runtime concern the project would own (`docs/planning/adr/adr-001-story-format-json-storybook.md:74`)
and the schema never got it. Every mature IF format (Ink, ChoiceScript, Twine) leans on it for exactly
this.

### F5. "Constraints spread with no single source of truth": half right

For numeric shape rules a single source already exists and works: briefs are rendered from the
enforcing code (`scripts/generate_drafting_brief.py:1-14`). For craft rules it does not. The "never
tell the reader their route did not matter" rule is restated in 15 files (measured here: four fill
templates, two drafting-guide copies, `merge_notes.py`, `prompts.py`, `fidelity_repair.md`,
`state_promotion.py`, both `agency.py` modules, ADR-011 section 12, the skill, `check_prose_craft.py`),
and the two guide copies differ by 327 diff lines with two sections sync-tested (AL-780).

But consolidation would not have fixed the measured failure. The failure was **precedence**, not
drift: a consistent rule lost to a beat. Rank consolidation below F2, and build it as a compile step
(rule registry in, per-node instruction out) rather than as a tidier document.

### F6. "Validation by pattern-matching prose after the fact": confirmed, with a sharper cause

The project has now proven this limit three times: presupposition by noun phrase (3.48 findings per
node), detectors tuned on five books (AL-766), and `merge_seams` recall falling from 53 to 16 percent
the moment a prompt targeted it (AL-796). The third is Goodhart, not a calibration bug: a detector
keyed on surface phrasing teaches the generator, through the prompt written from its findings, to
vary the phrasing. Repairing its regex buys one more round. A semantic property ("does this passage
assert something not guaranteed on entry") needs a semantic check against an explicit list, which
requires F1's ledger.

Also added here: by principle every quality measure is "a reported statistic, not a gate"
(`validator/consequence.py:23`, `validator/continuity.py:11`, `validator/agency.py:89`). The principle
(AL-337: do not promote a number because it is computable) is right. Its consequence is that "passed"
means safe and well-formed, a fill delivering 60 percent of commissioned words passes
(`generation/orchestrator.py:1530`), and no artifact anywhere means "good". Passing strict does not
either: `the-orchard-signal` passes `--strict` (measured here) and ships 31 meta and 19 second-person
labels; `the-tin-whistle-map` passes with three decisions whose every option is a forbidden ending
(AL-782).

### F7. "Feedback loops end at a lessons log": reject as stated, replace

The log does drive change: 375 of 798 rows are applied. The trouble is what the unit of change is.
By category, 541 rows are tooling or validator and 41 are authoring craft (measured here). A lesson
is recorded as "defect instance, therefore detector or lint or doc line", so the loop feeds the
checking side and reaches the generator only as more prompt text. It is an efficient machine for
producing instruments (about 118 scripts, 261 planning documents, 1.36 million words, measured here)
and it has no step that asks "which layer lacks a representation, such that this whole family
recurs". 418 open rows and an 843-row register are not a backlog; they are evidence that lesson
production outruns any possible consumption.

### F8. "Evaluation without ground truth of reader experience": confirmed

No decision to date has used a child's read. The judge panel is recorded as unvalidated
(`docs/planning/cyo-measurement-workplan-2026-08-12.md` section 0, rule 2). The instrument that found
the November defects was one adult reading books. Reading-trail capture now exists
(`src/cyo_adventure/reading_trail/`, `scripts/report_reading_trail.py`) and has no data yet. Add one
thing: the August NO-GO (`docs/planning/live-structural-round-2026-08-21.md:406-432`) ranked
same-skeleton similarity as defect number one and never mentions whether a book is good to read. The
measurement program was rigorous about the wrong dependent variable.

### F9. Scale before quality

Added. ADR-011 set genre-faithful sizes and the catalog was built to them: 84 shells, 31 fills, 4 books
an editor considers fit, each needing nearly every node rewritten. 66 of 84 shells fail the project's
own strict bar (reproduced here: 18 pass, 66 fail, 2,391 choice-grammar failures), and the mutation
flywheel now cannot produce a promotable child from a stateless parent (AL-795). One-shot fills of
15,000 to 25,000 words deliver 48 to 97 percent of their budget with fill-to-fill swings of 3 to 17
seams on identical input. Breadth was bought before the unit was right, so every unit defect is
multiplied by 84 and every fix is a migration.

### F10. The best path is not the product path

Added. Two authoring mechanisms exist (`story_requests/authoring_plan.py:1-9`): the automated provider
and the human-run skill. The good books came from skill plus editorial rewrite plus an independent
continuity read. The in-app editor cannot add a node, variable or condition (`api/node_edit.py:1-8`),
so the revision that matters has no product route except importing a new edition (AL-769). The human
is positioned at the end, judging 17,000 finished words for safety, where judgment is most expensive
and least able to change the story.

---

## 3. Higher-level changes

### 3.0 Current versus proposed data flow

```text
CURRENT
  cell brief (numbers) + premise line
        |
        v
  SKELETON  graph + free-text beats + labels          <- meaning lives here as prose-in-a-string
        |   (strict shape checks; reused across books; mutated for growth)
        v
  match by cell -> bind nouns -> ONE-SHOT FILL (all nodes, beats outrank rules)
        |
        v
  gate (shape) -> moderation (safety) -> regex advisories -> human (safety, at the end)
        |
        v
  lessons log -> new detector / lint / prompt line


PROPOSED
  request + band
        |
        v
  STORY PLAN (per book)                      <- NEW: the single source of meaning
    cast (want, voice), hidden truth, stakes,
    fact ledger, threads (plant -> payoff), ending gifts
        |            ^
        |            | human approves the one-page plan (cheap, early, high leverage)
        v
  SHAPE (from library or generated)  +  per-node obligations
    graph only: no prose beats            requires / establishes / must-not-assert,
                                          function, choice intents and costs
        |
        |   deterministic plan checks: merge closure, plant exclusivity,
        |   payoff reach, one truth, every ending gives something
        v
  COMPILER: graph + plan + rule registry -> one instruction per scene
        |
        v
  SCENE-BY-SCENE PROSE (each call sees: entry-guaranteed facts, voices, what not to assert)
        |
        v
  gate (shape) -> moderation (safety) -> MODEL CONTINUITY READER against the ledger
        |                                (sampled (node, state) paths)
        v
  human reads 2-3 generated paths, answers a quality question
        |
        v
  reading trails (finish, rewind, choice split, payoff seen) -> plan and shape rules
```

### Ranked change list

Ranking is by defect classes removed per unit of cost, with dependency order respected.

| # | Change | Removes | Cost | Risk |
| --- | --- | --- | --- | --- |
| 1 | Per-book Story Plan with fact ledger and threads, checked structurally | F1, most of F6, AL-773/788/790/799/800 | M | plan quality becomes the new bottleneck |
| 2 | Typed directives compiled from graph plus plan; no free-text graph narration in beats | F2, F5 precedence, AL-797/798 | M | migration of supported shells |
| 3 | Evaluation led by reads: validated continuity reader, path-sampled human read, reading trails | F6, F8 | S to M | reader model must be validated first |
| 4 | Move the human to plan approval (catalog books only; revised, see addendum A.5) and give the final approval a quality question | F10 | S | approver time |
| 5 | Shrink the supported catalog without emptying any cell (revised, see addendum A.5); generate scene by scene | F9 | S | sunk-cost reluctance |
| 6 | Re-cut frozen versus generated: shape frozen, meaning per book (revised: moves to third, see addendum A.5) | F3 | M | reopens diversity question (favourably) |
| 7 | Conditional passage text in the schema | F4 | L | two engines, offline, moderation fan-out |
| 8 | Rule registry rendered into prompts, guide, skill, review surface | F5 drift | S to M | low |
| 9 | Lesson triage by layer; cap instruments | F7 | S | process change |

#### Change 1. A Story Plan per book

**What.** A small JSON artifact stored beside each book, written before any prose:

- `cast`: each with a want, a way of talking, and what they know.
- `truth`: the one canonical answer to the book's question (who lit the lamp and why).
- `facts`: id plus one sentence. Example: `F_kitto_helps: Mrs Kitto agreed to help and is coming`.
- per node: `requires` (must be guaranteed on entry), `establishes`, `must_not_assert` (computed, not
  authored: every fact not guaranteed on entry).
- `threads`: named plant-to-payoff arcs. Each names the variable, the planting choice, the concrete
  thing planted (a person, object or piece of knowledge that no other route yields), each payoff site,
  and what the reader sees there.
- per choice: `intent` and `cost` (what the hero gives up), so a fork with one right answer is visible
  as a fork with one cost.
- per negative ending: `gift` (what it reveals, the laugh, or the reason to retry).

**Checks that become exact** (no prose reading): merge closure, already implemented as NC-1
(`scripts/check_narrative_contract.py:18-22`), promoted from script to validator; plant exclusivity
(the planted fact is established on no route that skips the plant: this is AL-800 as a set test);
payoff reach by the existing configuration walk; payoff independence (a payoff site requires only its
own thread's facts: the Arthur Tremlett defect); single truth (no two nodes establish contradicting
facts: AL-773); every negative ending has a gift. The prose check then shrinks to a well-posed
question per node, "does this passage assert any fact on this short list", which a model answers far
more reliably than a regex and which cannot be gamed by rephrasing.

**Two cautions from the project's own evidence.** The plan must be per book, not per skeleton: shared
contract wording made books converge (AL-208, `docs/planning/architecture-respecification-2026-08-10.md`
section 1), and the fact graph alone does not capture the decision (AL-197), which is why choice
`intent` and `cost` are in the plan rather than left to labels. And the August prototype was built to
vary books; this is a different purpose and should not inherit its diversity budgets.

**Cost.** Schema and checker, about two weeks, much of it lifting the NC checks. A plan-generation
stage with its own repair loop. No reader or runtime change: the plan is authoring-side.
**Breaks or migrates.** Nothing at runtime. Existing books have no plan; back-extract plans only for
the books you intend to keep.
**Evidence it worked.** Before spending on generation: back-extract plans for the four revised books
and the four Run B fills, and confirm the deterministic checks plus the ledger-based read flag the
three known `hollow-lighthouse` contradictions, the three leaks in section 4.2 of the verification
report, and the unearned `did_find_who_wrote` payoff. That is a retrospective test on evidence already
paid for. After: zero route-fact contradictions found by an independent human read across ten new
books.

#### Change 2. Typed directives, compiled

**What.** Replace the `beats='...'` string with fields: `function` (plant, raise cost, reveal, payoff,
breather), `event` (the dramatic content, from the plan for this book), and nothing else authored.
Merge handling, option handling, plant and payoff handling and person are rendered by a compiler from
the graph and the plan into one instruction per scene. Graph narration ("both ways", "every path",
"BOTTLENECK") and option enumeration become unrepresentable rather than linted. Labels are generated
per book from choice `intent` in the declared person and checked at plan time, where a bad label is a
one-line fix, not inherited by every fill.

**Why it is not just the beat lint already proposed.** The lint (verification report, next step 1)
treats 982 merge beats and thousands of labels as text to clean, shell by shell, and leaves the
channel that produced them open. Do the lint for the few shells you keep; make the channel typed for
anything new.

**Cost.** M: directive schema, compiler, collapse four fill templates into one. **Migrates.** Only the
supported subset (change 5). **Evidence.** On `the-clockwork-menagerie` and `the-last-train-north`,
hand-counted seams and recaps against the committed 2026-11-20 baselines (8/8/8 and 17/3/12 seams;
85 to 89 recaps), at ten fills per arm, not three.

#### Change 3. Evaluation led by reads

Three tiers, each with a defined job.

1. **Deterministic, exact, blocking**: graph and plan checks only. Nothing that reads prose blocks.
2. **Model continuity and agency reader**, per sampled `(node, state)` path with the ledger as
   reference. This is the "independent second reader" that found what the editor missed (AL-790),
   made a stage. Validate it before trusting it: you now own a labelled set (four before-and-after
   book pairs, 147 hand-read merge openings, 22 hand-judged plant-payoff pairs). Require it to recover
   the known defects and not flag the revised books. It reports to the approver; it gates only once
   its agreement with human reads is measured.
3. **Reader data**: per decision, the choice split (a 95/5 split is a fork with one right answer),
   rewind-to-here rate, stop-reading nodes, endings reached, replays started, payoffs seen. With four
   children this is qualitative; pair it with a five-question spoken debrief. Its job in the family
   test is to learn which signals are worth keeping, not to prove anything.

Regex prose detectors stay as free smoke tests and stop being cited as evidence for or against a
change. **Cost.** S to M. **Evidence.** The reader's recall on the labelled set; then whether its
flags predict where children stop or rewind.

#### Change 4. Move the human

Approve the one-page plan before prose is bought: is this a story worth telling, is the truth
satisfying, are the forks real dilemmas, does each failure give something. That is ten minutes and it
is where a human's judgment changes the outcome. At final approval, replace "review findings" with
"read these three generated paths, including one through a payoff and one to a setback" and one
required answer: would you hand this to the child. **Cost.** S. **Evidence.** Approver rejections move
from the prose stage to the plan stage; time per approved book falls.

#### Change 5. Shrink the unit and the catalog

Pick the shells the family needs (the 8-11, 10-13 and 13-16 bands; perhaps eight to twelve, at 60 to
150 nodes), mark the rest not production-eligible, and do not remediate them. Park 16+ and the 500 to
677-node gauntlets entirely: no reader in the target family is in that band and no model or human can
hold their meaning. Generate scene by scene (a decision and its arrivals) with the ledger as context
rather than one 100,000-token completion; this also makes repair local and largely removes the
fill-rate floor problem. **Cost.** S for the decision; the chunked path exists and needs the ledger
payload in place of raw prior prose. **Evidence.** Words delivered within 10 percent of commissioned
on every scene; fill-to-fill variance on hand counts collapses.

#### Change 6. Re-cut frozen versus generated

Frozen and reused: shape (topology, depth, bottleneck placement, ending count and valence mix), which
is where the ADR-011 investment is real. Generated per book: the plan, events, labels, threads and
where state is planted, under shape constraints that guarantee payoffs sit on bottlenecks (ADR-011
section 12 item 6). On the skeleton-free question: the August proposal was shelved because sibling
sameness turned out to be a catalog-size effect, a diversity argument. On quality grounds I land on a
hybrid. Fully free structure generation gives up validated shape properties for no demonstrated gain;
fully frozen story skeletons are the cause of F2 and F3. Shape library plus per-book meaning also
dissolves most of the diversity problem as a side effect, because the shared artifact no longer
carries words. **Cost.** M, mostly delivered by changes 1 and 2. **Evidence.** Two books from one
shape and different requests, read blind by an adult: are they recognisably the same story.

#### Change 7. Conditional passage text

Add an additive schema minor (ADR-025): a node body may carry a small number of guarded spans over
declared booleans. A hub can then say one true sentence to the reader who brought the battery without
an inserted node, every planter sees a callback at the next bottleneck rather than 2 to 8 percent, and
"state-neutral merge" stops being the price of convergence. **Cost.** L and it is real: backend engine
and frontend engine must stay equivalent, offline bundles, the validator must walk variants, moderation
and reading level must screen every variant, the editor must show them. Cap it (boolean guards only,
at most three spans per node). **Why it is seventh.** Changes 1 to 6 work with inserted arrival nodes,
as the four revised books show. Do it before public launch, not before the pilot. **Evidence.** Share
of readers who see at least one callback, from reading trails; nodes added per thread falls toward
zero.

#### Change 8. Rule registry

One table: rule id, band scope, author wording, approver wording, checker reference, precedence. The
compiler of change 2 renders it into scene instructions; the same table renders the guide, the skill
reference and the review-surface text. `generate_drafting_brief.py` is the existing proof of the
pattern. **Cost.** S to M. **Evidence.** The 15 restatements become one; the sync test is deleted
because there is nothing to sync.

#### Change 9. Lesson triage by layer

Before a lesson gets a detector, it gets a layer: plan, shape, compiler, prose, evaluation, process.
Three lessons on one layer trigger a representation change, not a fourth detector. One summary row per
run, not one per observation. Bulk-close open rows that propose repairing instruments this review
recommends retiring, citing the superseding decision. **Cost.** S. **Evidence.** Open rows fall; new
rows per run fall by an order of magnitude; the ratio of generator-side to checker-side changes
inverts.

---

## 4. What to stop doing

1. **Catalog growth by mutation and the flywheel** (ADR-020, `mutation/`, `flywheel/`). It multiplies
   shells whose defects are inherited and already collides with the new agency rule (AL-795). The
   largest file in the backend serves a catalog that is not the constraint.
2. **Cross-book diversity research** (shared four-gram budgets, sibling exposure, anti-template
   tuning, label fingerprints, D-series and W-series rounds). Its own measurement found the driver was
   a three-per-cell catalog. Reopen when a real family owns enough books for it to be observable.
3. **Retrofit state promotion across the catalog.** Keep the six pilots as evidence. State named after
   buttons, with payoffs the model must invent and few readers reach, is structure without meaning
   again. Threads belong in the plan.
4. **Strict remediation of the 66 failing shells**, and the grandfather list that tracks it. Choose
   the few to keep; archive the rest.
5. **Repairing regex prose detectors' recall** (`merge_seams` shapes, recap patterns, outcome-naming
   labels, plant-leak keyword scans). Each is a round of an arms race the detector loses.
6. **Prompt-wording experiments at three fills per arm.** The verification run was careful and says
   itself that it cannot separate effects from variance. Do not buy more of that design.
7. **Vendor and model comparisons** until the plan layer exists; model differences are currently
   smaller than same-model run-to-run spread.
8. **(Withdrawn, see addendum A.5.) The reading-level repair loop as a default stage.** It optimizes a formula that penalises
   dialogue (AL-771, AL-785), the thing the books most lack. Fix the measure (strip speech, guard
   abbreviations), keep it advisory, and stop rewriting prose toward it automatically.
9. **Mandatory per-observation lesson rows with register linkage.** This is a governance rule in
   `CLAUDE.md` and only the owner can change it; the recommendation is change 9.
10. **Writing new planning documents for decisions already documented.** The August proposals contain
    most of change 1. The gap was never design.

---

## 5. Sequencing

### Now, through the family test (no generation needed)

- Treat the hand-revised books as authored books. Stop trying to keep them in parity with their
  skeletons (AL-784); record that they have none.
- For each book going to the children: write its plan by hand (cast, truth, facts, threads; a page),
  then have a second reader, human or model, do the full `(node, state)` continuity read against it.
  This fixes what AL-790 found and produces the first gold plans.
- Add one or two more revised books if a band is uncovered. Use the existing recipe; it works.
- Instrument the test: confirm reading trails are recording, write the debrief questions, decide in
  advance what you will look at (finish rate, rewinds, choice splits, replays, payoffs seen).
- Freeze: mutation, flywheel, promotion rollout, strict remediation, diversity work, paid prompt runs.

### Before any more books are generated

1. Story Plan schema v0 and its deterministic checks (change 1), validated retrospectively against the
   known defects in the revised books and the 2026-11-20 evidence folder. If the checks do not catch
   the known contradictions and leaks, stop and rethink before building further.
2. Typed directives and the compiler for the supported shells only (change 2).
3. The continuity reader, validated on the labelled set (change 3, tier 2).
4. Plan approval step for the human (change 4).
5. The supported-shell decision and scene-by-scene generation (change 5).

Then one pilot: three shapes, plan-first, ten books, compared by hand count and blind adult read with
the committed baselines. Pre-register the kill criterion: if an independent read still finds a
route-fact contradiction in more than two of ten books, or blind readers do not prefer the new books
to the old fills of the same shells, the plan layer is not sufficient and the next question is the
fill model and the unit size, not more rules.

### Can wait

- Conditional text (change 7): after the pilot, before public launch.
- Rule registry (change 8) beyond what the compiler needs.
- Structural editing or supersede-edition in the app (UW-M14).
- Generating shapes rather than selecting them.
- Diversity, reopened with reader data.
- 3-5 and 5-8: these bands mostly behave (trees and loops, few merges, read aloud); leave them alone.

---

## 6. Limits of this review

- No generation was run, so nothing here is tested against a model. The retrospective validation in
  section 5 is designed to be the cheapest possible first test for that reason.
- Counts marked "measured here" use my own scripts: merge nodes by distinct inbound sources (the
  `merge_notes.py` definition); the "merge-language beats" figure of 982 is a crude regex that also
  matches the tool-written "MERGE:" prefix on promoted shells and should be read as an order of
  magnitude. The strict tally (18 pass, 66 fail) is a straight run of `check_skeleton.py --strict` on
  all 84 shells; outputs are in this folder as `strict_*.txt`.
- I read the August research selectively. Where I say it optimized diversity, that is from the SQ
  plan, the narrative redesign and skeleton-free proposals, the respecification note, the measurement
  workplan and the NO-GO section; a document I did not open may qualify it.
- The Story Plan moves difficulty rather than deleting it: a weak plan yields a coherent dull book.
  That is the right place for the difficulty to sit, because a plan is a page a person can judge, but
  it is a bet, and the pilot's kill criterion exists because it could lose.

---

## Addendum: generating from a short request

Added 2026-11-21 at the owner's request, reviewed at commit `b1b78fa`. Same rules as the review:
code read-only, no generation, no provider call. "Measured here" means a pure function from the
repo was called locally with the example string; nothing was sent anywhere.

The owner's question: do the changes already merged, or the changes this review recommends, reduce
the product's ability to make a good new story from a child's one-line request or a guardian's short
brief? Short answer: the merged changes are close to neutral for that path. Three of my
recommendations as first written would have hurt it and are revised below (section A.5). The larger
finding is that the short-request path as built already discards most of what the request says, so
the baseline being protected is lower than it looks.

### A.1 The short-request path as built

Worked example throughout: a child at 8-11 types "a story about a dragon who is afraid of the dark".

| Step | Code | What happens to the request |
| --- | --- | --- |
| Kid submit | `api/schemas.py:971-973`, `:984-997` | A kid can send `request_text` (1 to 500 characters), plus an optional proposed series title or an anchor book. Nothing else. Band, length and style are stamped from the profile. |
| Guardian or admin authored | `api/schemas.py:1013-1025`, `:1051-1065` | The same 500-character text plus `age_band`, `length`, `narrative_style`, optional target child, series or anchor. No field for a hero, a setting, a wish or an ending. A guardian's "short brief" carries no more story than a child's line. |
| Screening | `story_requests/screening.py:1-9` | PII guard and Stage 0 classifiers. Blocks or passes. Text unchanged. |
| Approval | `story_requests/service.py:301-320`, `:456-466` | Guardian click, or auto-approve inside a pre-authorized envelope. Confirms band, length, style. Builds a concept; no job yet. |
| Brief | `story_requests/brief.py:315-338` | `premise` is the raw text. Everything else is defaulted: protagonist name `"Explorer"` (`:95`, `:318`), age from the band, a default role; `tier=1` always (`:324`); `structure_pattern` always branch-and-bottleneck (`:328`); node count the midpoint of the band range (`:250`). |
| Tone | `story_requests/tone.py:227-241` | Keyword lookup. Measured here: the dragon line yields `gentle` at every band. "Afraid of the dark" is not a recognised signal. |
| Anchor | `story_requests/anchoring.py:114`, `:294` | Only for a continuation: prior title, hero names, variable names, ending excerpts. |
| Authoring plan | `story_requests/authoring_plan.py:1-9` | **An admin** picks method (`skeleton_fill` or `fresh_generation`), mechanism and model. A human step that exists today on every request. |
| Skeleton match | `generation/skeleton_match.py:360`, `:415-434`, `:709-749` | Candidates are the production shells in the cell. Weighting uses family recency and a theme-tag overlap bonus. Measured here: the dragon line reduces to the tag set `{dragon}`, and every candidate in the 8-11 short, 8-11 medium, 10-13 short and 10-13 medium cells scores 0.0. So the pick is uniform random among `the-cave-of-echoes`, `the-half-hour-call`, `the-locked-carousel` and `the-robot-fair-sabotage`. |
| Bind (47 of 84 shells have a contract) | `generation/templates/interpret_bind.md`, `generation/binding.py:10-15` | A model maps the request onto the shell's noun slots and lists the request's elements with the slot each landed in, or `null`. Substitution touches beats, labels and ending titles only. |
| Interpretation | `story_requests/interpretation.py:243-247` | What did not fit is recorded for the child and guardian as `structure_fixed` ("endings, topology and fail-states are structural, not requestable") or `not_this_story_kind` ("no slot carried it"). The system already tells the family, in a designed surface, that it dropped part of the request. |
| Unbound fill (37 shells) | `generation/templates/fill.md` | The whole brief JSON, including the `"Explorer"` protagonist, goes in as the theme brief (`authoring_plan.py:669`), with the instruction to re-imagine while "preserving every beat exactly". |
| Fill | `generation/orchestrator.py:1516`, `:1790-1798` | One call. Prose "MUST depict this exact beat". |
| Fresh generation (no skeleton) | `generation/worker.py:2541`, `generation/prompts.py:366-422` | Stage A invents structure from the brief, then prose. Carries the premise whole. But the brief fixes `tier=1`, Tier 1 cannot declare variables (L1-6), and the budget block instructs branches to "RECONVERGE onto shared later nodes". So this path produces stateless merged books by construction: the exact defect ADR-011 section 12 was written against, on the one path that rule does not cover. |
| Gate, moderation, approval | as section 1.1 | Shape, safety, then a human. None asks "is this the story that was requested". |

What survives of "a dragon who is afraid of the dark" on the skeleton path: a dragon, as the value
of the HERO slot, in the plot of (say) `the-robot-fair-sabotage`. The fear, which is the story the
child asked for (a want, an obstacle and an implied change), has no slot and is reported back as
"cannot carry". On an uncontracted shell the model receives a dragon premise, a protagonist named
Explorer and a frozen plot, and resolves the conflict however it likes. The request side and the
catalog side also barely share a vocabulary: 9 of 22 subject tags appear on no story
(`docs/planning/story-diversity-plan-v2.md:279`).

So the as-built product does not generate a story from a prompt. It reskins one of three to six
pre-written plots chosen without regard to the prompt, or it free-generates a book that cannot carry
consequences. This matters for the owner's question because "do not reduce the ability" has a low
bar to clear, and because the right goal is to raise it.

**Kid versus guardian.** The only differences are who confirms band, length and style, and whether
approval is a separate step. Neither can express more story than 500 characters of free text, and
no stage parses that text into story elements other than nouns for slots.

**What the August NO-GO measured.** (`docs/planning/live-structural-round-2026-08-21.md:406-432`.)
Same-skeleton similarity; mid-band fill rate (44 to 63 percent of commissioned words); contract
drift in titles and frozen fields; a fifth to two-fifths of (skeleton, brief) pairs returning
nothing on benign briefs; chunked-path readiness. It did not measure whether a delivered book
contained what was asked, or whether it was good. Delivery rate is the one figure there that bears
directly on a child's request, and it is the first thing any change must not worsen.

**Latency today.** There is no interactive path. A request passes a guardian (or an envelope), an
admin authoring plan, a multi-minute fill (one 16+ book took 2,810 seconds in August), moderation
and a human approval. Any latency argument below is relative to that, not to "instant".

### A.2 Merged changes of the last two days, rated for this path

| Change | Rating | Mechanism |
| --- | --- | --- |
| Reader-agency prompt rules and per-merge notes (`6d37b8e`, `687e9cd`) | Helps, modestly | Measured in the verification run on native briefs: no `needs_review` in the new arm against three in the old, higher fill rate (0.72 against 0.60; 0.81 against 0.68), fewer seams on one of two shells. The rules sit in the drafting guide, so they reach fresh generation too. They do nothing for carrying the request, and lose wherever the shell's beat contradicts them. Not tested on reskinned briefs. |
| Declared person governs (`687e9cd`) | Helps | Removes a contradiction (guide said second person; 59 of 84 shells are third) that the model resolved arbitrarily on every fill. |
| Approver advisories (`c690f95`) | Neutral for generation; slight risk at approval | Nothing generated changes. The approver now sees seam and label counts, but seam recall fell to about 16 percent on new-prompt fills, so a clean advisory on an on-demand book is weak evidence and should not read as a pass. |
| ADR-011 section 12 and `--strict-agency` on promotion (`c3a48f3`, `88638ce`, `7e2d62e`) | Neutral for matching today; slows shape growth; exposes a gap | The existing catalog is grandfathered, so no request loses a candidate. Growth slows: a mutant of a stateless 8-11+ parent is now rejected (AL-795). That costs the short-request path little, because matching is by cell and the request's content scored 0.0 against every candidate anyway, and mutants keep 100 percent of the parent's beats (AL-229). The gap: the rule binds new skeletons only, while `brief.py:324` pins every request to Tier 1, so fresh generation keeps producing what the rule forbids. |
| State-promotion tool and the six pilots (`aa50c49`, `01cc03d`, `f42e93b`) | Unknown, leaning hurts for reskins until tested | Five of the six promoted shells have no contract and no slots (measured here), and the tool writes native-theme literals into directives and variable descriptions ("Start at the Beacon Steps", "Say you are staying with Mamgu"). On the one contracted pilot the descriptions are de-slotted strings ("the route l zone, where matriarch keeps the desk"). A dragon request filled onto these gets more native text to overcome, and plants whose content must be reinvented in a new theme. The run that validated promotion used native themes only and says so. |
| M3 donor change | Not found | I find no such commit on this branch at `b1b78fa`; AL-795 proposes it. If built, it would restore mutant promotability and be neutral for a single request for the reason above. |
| Edition import (`d28e008`) | Neutral | Catalog delivery only. |
| Reader changes and reading-trail capture (`fe51b37`, `ee15a5b`, `098de0d`) | Neutral now; helps later | No effect on generation. The trail is the only planned source of evidence that an on-demand book was read to the end, so it is a precondition for A.4's measures. |
| The four hand-revised books | Neutral, with one caution | They no longer match their shells (AL-784), so the on-demand path filling `the-hollow-lighthouse` shell still produces the old stateless book. Good catalog books do not improve generation. |

Net: nothing merged makes a short request worse in a way I can show. The promotion pilots are the
one item to test under a reskin before they are relied on for requests.

### A.3 My recommendations, rated for this path

| # | Recommendation | Rating as first written | Mechanism, honestly |
| --- | --- | --- | --- |
| 1 | Story Plan per book | Helps most, and adds one new fragility | It is the first place the request's want, fear and change can be represented at all; today they are dropped at bind. The fragility: more is invented from a thin input, and a weak plan gives a coherent, dull book. Mitigated by A.4's expansion rules; not eliminated. |
| 2 | Typed directives | Helps if 1 exists; hurts without it | A skeleton beat supplies a ready event per node. Typed directives make the plan stage invent roughly 60 to 150 events per book that a shell used to hand over. That is more model work and a new safety surface: plan events are model text nobody has read. They must pass the same classifiers and band envelope before prose is bought. |
| 3 | Evaluation led by reads | Helps | Adds the missing measure (was the request carried). No generation cost. |
| 4 | Human plan approval before prose | **Hurts as written** | A third human step in front of every child request, on top of guardian approval and the admin authoring plan, with the owner as the only approver. Revised in A.5. |
| 5 | Smaller catalog | **Hurts as written, if applied to eligibility** | Requests match by cell. Cells hold three to six shells (measured here: 75 production-eligible across 18 cells). Marking shells ineligible before change 6 would leave some cells with one plot, so two requests from one child would return the same story. Revised in A.5. |
| 5 | Scene-by-scene generation | Mixed: helps delivery, costs input tokens | Output tokens are unchanged. Input repeats per scene (instruction, ledger slice, voices), so I estimate total input at two to four times a one-shot fill before prompt caching; at the 0.30 to 0.76 USD per fill measured on 2026-11-20 that is on the order of one to two dollars a book. This is an estimate, not a measurement. Wall-clock can fall, not rise: once the ledger fixes the facts, scenes on different branches do not depend on each other's prose and can run in parallel. Delivery should improve, since a failed scene is retried alone and a 40 percent total-loss rate per pair becomes a per-scene retry. |
| 6 | Shape frozen, meaning per book | Helps most for this path | This is the change that turns "reskin a plot" into "write this request's story on a proven shape". It also makes catalog size a question of shapes per cell, not themes per cell. |
| 7 | Conditional text | Neutral | Later; no effect on expanding a request. |
| 8 | Rule registry | Neutral to helps | Shorter, per-scene instructions. |
| 9 | Lesson triage | Neutral | Process. |
| Stop 1 | Freeze mutation and flywheel | Neutral | Mutants carry the parent's beats; a request cannot tell them apart from the parent. |
| Stop 8 | Drop the reading-level repair loop as a default | **Hurts** | For a child's request, reading fit is the first thing a guardian notices, and AL-292 is clear that the loop is what gets nodes in band (84 percent against 11). Withdrawn in A.5. |

### A.4 Design adjustments for the short-request path

**1. Expand the request into the plan in two small steps, not one.**

- *Pitch.* From the request, band and tone, generate two or three one-paragraph pitches, each
  stating the hero, the want, the obstacle, what is at risk, and the kind of ending. For the dragon
  line: a dragon whose cave has gone dark and who must fetch a light alone; a dragon who hides the
  fear from friends on a night flight; a dragon who learns what lives in the dark is as scared as
  she is. Each pitch is checked deterministically for required fields and screened like any text.
- *Plan.* The chosen pitch is expanded against a shape into cast, truth, facts, threads and node
  obligations, then checked (merge closure, plant exclusivity, payoff reach, one truth, ending gifts).

**2. What is inferred, what defaults, what is asked.**

| Item | Rule |
| --- | --- |
| Hero | Inferred from the request. `"Explorer"` is used only when the request names no one. A real child's name is still blocked by the PII guard; "me and my sister" becomes a fictional pair, as today. |
| Want, obstacle, change | Inferred. This is the part of the request the current path drops; a pitch with none of the three is rejected and regenerated. |
| Tone | Inferred by the pitch model inside the band's cap table, replacing the keyword lookup, with `tone.py`'s ladder kept as the ceiling. |
| Band, length, style | From the profile and the guardian, as now. |
| Tier and pattern | From the shape, not pinned in the brief. Remove `tier=1` and the fixed pattern at `brief.py:324` and `:328` for 8-11 and up. This is a small, separable fix and it also closes the fresh-generation gap. |
| Everything unstated | Invented, but only from material the plan declares, so it is consistent. |
| Asked back | At most one thing, and it is a choice, not a question: show the pitches and let the child tap one. That suits a product about choosing, costs one tap, and gives the request a second sentence of signal. If nobody picks within the approval window, take the first. Never ask a child an open question. |

**3. Catalog book versus on-demand request.**

| Step | Catalog book | On-demand request |
| --- | --- | --- |
| Pitch | Owner writes or picks | Generated; child may pick; guardian sees the chosen pitch on the approval screen they already use |
| Plan approval | Human, required | Automatic when all deterministic plan checks pass and screening is clean; routed to a human only on failure. No new human step. |
| Shape | Chosen deliberately | Matched by cell and by the plan's needs (number of threads, bottleneck positions), not by theme tags |
| Prose | Scene by scene | Same |
| Continuity read | Model reader plus second human | Model reader only, reported to the approver |
| Final approval | Human (ADR-005) | Human (ADR-005), unchanged, with the pitch shown beside the book so "is this what was asked" can be answered at a glance |
| Admin authoring plan | Not needed | Becomes a default policy with an override, not a per-request click |

The existing interpretation surface (K19) becomes more truthful under this design: instead of
listing what was set aside, it shows the pitch.

**4. Keep the current path as the fallback until the new one beats it.** Skeleton fill stays
selectable in the authoring plan. Plan-first replaces it per band only after A.4.5 passes.

**5. Evidence: a fixed short-request panel.**

- *Panel.* The 16 requests already committed as `PREMISE_PANEL`
  (`scripts/measure_theme_coverage.py:53-70`), plus the dragon line and three two-sentence guardian
  briefs, at 8-11 and 10-13: 40 jobs per arm.
- *Arms.* (a) current skeleton fill, (b) current fresh generation, (c) plan-first. Run (a) and (b)
  once, now, before anything else changes: the baseline does not exist yet and every later claim
  depends on it. Cost at measured rates is roughly 15 to 30 USD per arm.
- *Measures.* Delivery (a book came out; share of commissioned words). Request fidelity: for each
  request, a fixed list of its elements written in advance (dragon; afraid; the dark; some change by
  the end), scored present or absent by a blind adult reader on one sampled path, plus a single
  question, "is this the story that was asked for", from 1 to 5. Agency and continuity by the hand
  counts and the continuity reader of change 3. Cost and wall-clock per book. Approver minutes.
- *Kill criterion, fixed in advance.* Plan-first replaces skeleton fill for on-demand requests only
  if all hold: delivery rate not lower than arm (a); request fidelity higher on at least two thirds
  of requests; blind paired preference for plan-first on at least two thirds of pairs; cost no more
  than three times arm (a). If fidelity rises but delivery falls, keep skeleton fill for requests
  and use plan-first for catalog books only. If neither fidelity nor preference moves, the plan
  layer does not help thin prompts and the next lever is the pitch step or the model, not more
  structure.

### A.5 What this changes in the review

Marked "revised" where the text above was edited.

1. **Change 4, revised.** Human plan approval is required for catalog books only. For on-demand
   requests the plan is approved automatically when deterministic checks pass. ADR-005 final
   approval is untouched.
2. **Change 5, revised.** "Shrink the catalog" means stop remediating and stop growing legacy
   shells. It does not mean removing production eligibility from any cell that would be left with
   fewer than two shapes, and no shell should be made ineligible for on-demand matching until
   change 6 is in place.
3. **Change 6 moves up**, from sixth to third, ahead of the human-role and catalog changes. For
   the short-request path it is the change that matters most, and changes 4 and 5 are only safe
   after it.
4. **Stop item 8, withdrawn.** Keep the reading-level loop. Fix what it measures (strip speech,
   guard abbreviations) so it stops fighting dialogue.
5. **Two additions to "before any more books are generated"**: run the short-request baseline
   (A.4.5, arms a and b); and unpin `tier=1` and the fixed pattern in `brief.py` for 8-11 and up.
6. **One addition to "stop"**: do not rely on the six promoted shells for reskinned requests until
   one reskinned fill of each has been read. Their directives carry native-theme literals.

Nothing else in the ranking changes. The diagnosis in section 2 is reinforced: the short-request
path is where the missing meaning layer costs the most, because there the request is the meaning,
and it is discarded at the first step that could have used it.
