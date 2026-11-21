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
per-node requires and establishes, named plant and payoff threads) generated and human-approved
before prose, and checked structurally; (2) replacing free-text beats with typed directives
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
| 4 | Move the human to plan approval and give the final approval a quality question | F10 | S | approver time |
| 5 | Shrink the supported catalog; generate scene by scene | F9 | S | sunk-cost reluctance |
| 6 | Re-cut frozen versus generated: shape frozen, meaning per book | F3 | M | reopens diversity question (favourably) |
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
8. **The reading-level repair loop as a default stage.** It optimizes a formula that penalises
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
