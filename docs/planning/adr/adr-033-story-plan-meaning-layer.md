---
title: "ADR-033: A per-book Story Plan as the meaning layer of story generation"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision to give every generated or authored book an explicit Story Plan (cast,
  hidden truth, fact ledger, plant and payoff threads, per-node obligations), to compile typed
  directives from graph plus plan in place of free-text skeleton beats, to freeze shape and
  generate meaning per book, to lead evaluation with reads instead of prose pattern matching, and
  to unpin tier and pattern in the request brief for 8-11 and up."
tags:
  - planning
  - architecture
  - decisions
  - generation
  - evaluation
---

# ADR-033: A per-book Story Plan as the meaning layer of story generation

> **Status**: Accepted (2026-11-21). Ratified by the project owner in session on 2026-11-21 (decision D1 of the
> [implementation plan](../story-plan-implementation-plan.md)). Drafted by an agent from the [architecture
> review of 2026-11-20](../architecture-review-2026-11-20.md) and its short-request addendum, after the owner asked
> for the review to be turned into an implementation plan. Nothing here is tested against a model: the review ran no
> generation. The first evidence gate (Phase 1 of the [implementation plan](../story-plan-implementation-plan.md)) is
> retrospective and costs nothing, and this ADR should be revised or withdrawn if that gate fails.
> **Date**: 2026-11-21
> **Amended**: 2026-11-21 (same day), by owner decision D11 of the [implementation
> plan](../story-plan-implementation-plan.md): Decision 3 and every passage that had the owner approving plans. See the
> amendment note below. The ADR stays Accepted.
> **Amends in part**: [ADR-011](./adr-011-story-scale-framework.md) (section 12 and the role of skeleton beats),
> [ADR-020](./adr-020-mutation-derived-skeletons-and-catalog-growth.md) (catalog growth by mutation is paused, not
> revoked).
> **Constrained by, and does not amend**: [ADR-005](./adr-005-mandatory-human-approval.md) (final approve-and-publish
> is unchanged), [ADR-015](./adr-015-story-request-initiation-and-gating.md) (a child never sees raw model output; no
> requester-facing plan turn is introduced), [ADR-025](./adr-025-additive-storybook-schema-versioning.md) (the
> Storybook schema is not changed by this ADR).
> **Relates to**: [ADR-001](./adr-001-story-format-json-storybook.md),
> [ADR-019](./adr-019-parameterized-skeletons-theme-contracts.md),
> [ADR-023](./adr-023-story-personalization-slots.md), [ADR-030](./adr-030-engagement-correlation-privacy-review.md).

## TL;DR

Every book gets a **Story Plan**: a small JSON document, written before any prose, that states who is in the story and
what they want, the one true answer to the book's question, a ledger of facts with what each node requires and
establishes, and the named threads by which an early choice returns later. The plan is checked structurally (no prose
reading), then compiled together with the graph into one typed instruction per scene. Free-text skeleton beats stop
being the instruction the fill model obeys.

Skeletons are demoted from "a story with the nouns removed" to **shapes**: validated graphs with a function per node
and no story content. Shape is frozen and reused. Meaning, choice labels and threads are generated per book from the
request.

Evaluation is led by reads: exact checks on graph and plan block; a model continuity reader, validated against
hand-labelled defects before it is trusted, reports to the approver; children's reading trails come third. Regex
detectors over prose remain as free smoke tests and are no longer cited as evidence.

The request brief stops pinning every request to Tier 1 and branch-and-bottleneck at 8-11 and up.

Final human approval (ADR-005) is untouched. Plans, for catalog books and on-demand requests alike, are approved by a
**validated plan-review model**, a different model from the one that wrote the plan, after the deterministic checks pass
and screening is clean. The owner reads plans by exception (every reject, every "unsure", and a random sample). No plan,
pitch or other model text is shown to the requesting child.

## Amendment note (2026-11-21, same day): plans are approved by a validated reviewer, not by the owner

The owner approved an amendment the same day the ADR was ratified. As first accepted, Decision 3 had the owner approve
every catalog plan by reading the plan file in a pull request, and approved on-demand plans automatically on the
deterministic checks alone. The amendment changes both:

- **One rule for both paths.** A plan is approved when SP-0 to SP-9 pass (`scripts/check_story_plan.py`), screening is
  clean, **and** the plan-review model passes it. The deterministic checks alone no longer approve an on-demand plan;
  the owner no longer approves a catalog plan as a matter of course.
- **The reviewer must be a different model** from the one that wrote the plan.
- **It may not be used until it is validated** against the project's labelled ground truth (the frozen answer key
  `docs/planning/evidence/story-plan-retro/known-defects.json` and the findings files beside it), meeting thresholds
  the owner sets (new owner decision D12 of the implementation plan, decided alongside the continuity-reader thresholds
  of D6). Until then no plan is approved by a model: every plan goes to the owner, and an on-demand plan that has not
  been approved does not reach the fill stage.
- **The owner reviews by exception**: every plan the model rejects or is unsure about, plus a random sample, proposed
  at 1 in 10 (the owner may change the rate), so that drift is noticed.
- **Unchanged**: final approve-and-publish of every book by the owner ([ADR-005](./adr-005-mandatory-human-approval.md));
  nothing generated is shown to a child ([ADR-015](./adr-015-story-request-initiation-and-gating.md)). Plan approval
  is a **quality gate, not the safety gate**: a plan the reviewer passes publishes nothing, shows nothing to a child,
  and is still moderated, validated and read by the owner as a book before any child sees it.

Passages changed: the TL;DR, Decision 1 (where a plan lives, the `pitch` and `provenance` rows), Decision 3 (table and
text), Decision 6 (a pointer), Decision 9 (a new failure case), Consequences, Follow-on work. The cost is a reviewer that
may share the writer's blind spots; the implementation plan's risk table names it, and the different-model rule, the
validation precondition and the exception sample are its mitigations. Nothing in the amendment has been tested against
a model.

## Context

### Problem

The 2026-11-20 editorial read found that catalog books open well and stop behaving like choose-your-own-adventures by
the middle, and that every gate, moderation stage and instrument had passed them. The architecture review traced this
to one cause: the pipeline represents shape, scale, safety, reading level and theme slots explicitly, and represents
story meaning nowhere on the production path. Meaning exists as free text in skeleton beats, in the model's working
memory during one fill call, and in prose afterwards.

Consequences observed in code and data, each cited in the review:

- A node's body cannot be checked for what it presupposes, because nothing records what the reader knows on entry
  (`validator/continuity.py:11-33`).
- The skeleton beat is the highest-authority instruction (`generation/templates/fill_bound.md:57`, enforced by
  `moderation/fidelity_review.py:33-40`) and is unreviewed free text that narrates the graph and enumerates the
  buttons. Prompt rules lose to it (AL-797).
- State added mechanically carries no meaning: variables are named after buttons and payoff links are invented by the
  fill model (AL-783, AL-799, AL-800).
- A child's request is reduced to noun slots in a plot chosen without regard to it. For "a dragon who is afraid of the
  dark" the theme-overlap score is 0.0 for every candidate skeleton in four cells, and the fear has no slot (review
  addendum A.1).
- `story_requests/brief.py:324` and `:328` pin every request to `tier=1` and branch-and-bottleneck, so the
  skeleton-free path produces stateless merged books by construction.
- Detectors keyed on surface phrasing lose recall as soon as a prompt targets them (53 to 16 percent, AL-796).

### Constraints

- **ADR-005**: nothing reaches a child without recorded human approval. Unchanged.
- **ADR-015**: a child cannot trigger generation or see raw model output. The owner considered and rejected showing a
  generated pitch or plan back to the requester for this reason. This ADR introduces no requester-facing model text.
- **ADR-018 and ADR-030**: reading trails are child data. Their use in evaluation stays owner-only and local, under
  ADR-030 Decision 6's egress rule.
- **Untrusted input**: request text is untrusted (OWASP LLM01). Everything a plan derives from it is untrusted-derived
  and must pass the existing slot and classifier floors before it is placed in a prompt as instruction.
- **The family test runs on hand-revised catalog books**, not on generation, and must not be delayed.
- **One approver.** Any new human step is paid for in the owner's time.

### Significance

This changes what the generator is asked to do and what a skeleton is. It is expensive to reverse once shells are
migrated and books carry plans, which is why the first gate is a no-spend retrospective test.

## Decision

### 1. The Story Plan

A Story Plan is one JSON document per book. It is an authoring-side artifact: the reader app never loads it and the
Storybook schema does not reference it.

Contents (schema `plan_version` 0, to be fixed by work package WP-1.1):

| Section | Holds | Notes |
| --- | --- | --- |
| `request` | the request text, band, length, style, tone | untrusted text, fenced wherever it is reused |
| `pitch` | hero, want, obstacle, stake, kind of ending | five required fields; the unit the plan reviewer reads first, and the owner on exception or sample |
| `cast` | per character: role, want, voice notes, what they know | names pass the existing slot and PII floors |
| `truth` | the one canonical answer to the book's question | closes the two-backstory class (AL-773) |
| `facts` | id plus one sentence each | the ledger |
| `nodes` | per node: `function`, `event`, `requires`, `establishes` | `must_not_assert` is computed, never authored |
| `choices` | per choice: `intent`, `cost`, optional `plants` | labels are generated from `intent` |
| `threads` | per thread: variable, planting choice, the concrete thing planted, payoff sites, what each payoff shows | replaces button-named variables |
| `endings` | per negative ending: `gift` | what the ending reveals, the laugh, or the reason to retry |
| `provenance` | producer, model, shape id and hash, check results, approver | audit; `approver` records the reviewing model, its verdict and the sample reason, or the owner when the owner decided |

**Where it lives.** For catalog books, a file beside the book: `out/<slug>.plan.json`, committed in the same pull request as
the book, carrying the reviewer's verdict in `provenance`; the owner reads the plan in that pull request only when it was
rejected, unsure or sampled, and reads the book itself at final approval as before. For on-demand books, a JSON column on `StorybookVersion` (`db/models.py:1466`), added
by a Supabase migration, written by the worker and never returned by any kid-surface route.

**Versioning.** `plan_version` is `MAJOR.MINOR`, additive within a major, following the rule ADR-025 set for the
Storybook. A plan names the shape it was built for by id and content hash; a plan whose shape hash no longer matches
is stale and fails its checks.

**Relation to the Storybook.** Variables, effects and conditions in the Storybook are derived from `threads`. Node ids
and choice ids are shared. Nothing else crosses: the Storybook stays a complete, self-sufficient runtime document.

**A plan is per book, never per skeleton.** The project's own measurements show that a contract shared across books
makes them converge in wording (AL-208) and that a fact graph alone does not capture a decision (AL-197). That is why
`intent` and `cost` are in the plan and why plans are not reused.

**Plan-writing conventions (added 2026-11-21, a condition of accepting G1, decision D5; convention 1 clarified 2026-11-22).** Every plan, hand-written or
generated, follows these, because the G1 re-run showed the checks can only see what the plan records:

1. A statement a passage makes about the hero's possessions, knowledge or state, including a negative ("he has no
   ticket"), is recorded as a fact that passage establishes, marked `contradicts` against its opposite. A
   variable-backed state contradicted in a state where it holds is then an SP-3 ERROR. A negative that a later passage
   on the same reading reverses (the hero lacks the cloth, then is given it) is a change of state, not a
   contradiction: it is worded to say when it was true ("has no cloth yet", "has not found the key by the gate") and
   is not marked `contradicts` against the gain, because facts never retract (`AL-874`, chunked trial 2026-11-22).
   `contradicts` is for facts that cannot both hold at any point of one reading.
2. A warning, promise or instruction given in dialogue is its own fact (who told whom), separate from the thing it is
   about, so a later "as she told you" on a route that never heard it is visible (`AL-830`).
3. A choice's `cost` is "none" only when the option truly costs nothing; when its cost is giving up the other options,
   the cost says so.

The WP-2.3 plan template states these, and WP-1.6 measures them on books nobody has planned before. Until WP-1.6
passes, the WP-0.4 second read remains the standing continuity control for catalog books.

### 2. Structural checks on the plan

These block. None reads prose.

| Id | Check | Closes |
| --- | --- | --- |
| SP-1 | coverage: every node and choice of the shape has a plan entry and the reverse (G1 revision, 2026-11-21: only a node or choice coverage gap stops SP-2 to SP-8; a thread error excludes that thread from SP-4 to SP-6 and the other rules still run, AL-821) | drift |
| SP-2 | merge closure: every fact a node `requires` is guaranteed on every route into it (the NC-1 fixpoint in `scripts/check_narrative_contract.py:18-22`, moved into the package) | route-fact contradictions (AL-788, AL-790) |
| SP-3 | single truth: no two nodes establish facts marked as contradicting, and every `truth` fact is established on at least one route (G1 revision, 2026-11-21: unchanged; a test pins that a negation asserted where its opposite was planted is an ERROR, and plans record such negations at the asserting node, AL-822) | two backstories (AL-773) |
| SP-4 | plant exclusivity: the fact a thread plants is established on no route that skips the planting choice (G1 revision, 2026-11-21: "the fact a thread plants" is the declared `plant` plus any other fact the planting edge makes known, from the choice or a target only planted readers reach, that a payoff relies on, so the rule does not depend on which half of a two-part plant is named, AL-817; reported only where a payoff site is still reachable without the plant, so an ending is never reported, AL-818) | public plants (AL-800) |
| SP-5 | payoff reach: each payoff site is reachable both with and without the plant, measured by the existing configuration walk | cosmetic payoffs (AL-783) |
| SP-6 | payoff independence: a payoff site requires only facts guaranteed on entry plus its own thread's | cross-payoff references (AL-799) |
| SP-7 | every negative ending has a `gift` | give-up endings |
| SP-8 | every decision has at least two choices with different `cost` (G1 revision, 2026-11-21: a shared cost of "none", where no option gives anything up, is an ERROR; a shared real cost, the symmetric opportunity cost of a hub, is a WARNING, AL-819) | forks with one right answer |
| SP-9 | text floors: every plan string passes the slot charset, denylist and band floors already used for bindings (`validator/slots.py`); length is capped per field, 120 for slot-like strings, 240 for fact text and node events, 600 for `truth.statement` (amended 2026-11-21: record prose is longer than a slot value; G1 revision, 2026-11-21: SP-9 alone reads the bare word "wound" in a winding context, not introduced as the injury noun or verb, as the past of "wind", leaving `validator/slots.py` and every other term unchanged, AL-811) | untrusted-derived text in prompts |

Prose is then compared with the plan by one narrow question per node, "does this passage assert any fact on this
list", answered by the continuity reader of Decision 6.

### 3. Who produces a plan, and how it is approved (amended 2026-11-21)

| | Catalog book | On-demand request |
| --- | --- | --- |
| Pitch | written or picked by the owner (initiation, not approval) | generated; the first pitch that passes its checks is used |
| Plan | generated from the pitch, or hand-written | generated from the pitch |
| Plan approval | **validated plan-review model**, after SP-0 to SP-9 pass and screening is clean | the same |
| Owner reads the plan | when the model rejects it or is unsure, and for a random sample | the same |
| A plan that fails or is not passed | routed to the owner as `needs_review` | routed to the admin queue as `needs_review`; the job does not reach fill |
| Requester sees | nothing generated | nothing generated |
| Final approve-and-publish | owner (ADR-005) | owner (ADR-005) |

**The approval rule.** A plan is approved when all three hold: the deterministic checks pass, screening is clean, and
the plan-review model passes it. The reviewer reads the plan, the shape it is built for and the fenced request text. It
returns one of `pass`, `reject` or `unsure`, with reasons that name plan entries and never quote story text. Anything
other than a clean `pass` goes to the owner, including a reviewer error, a malformed answer, an unavailable provider and
two runs that disagree. The reviewer fails closed.

**Independence.** The reviewer must be a different model from the one that wrote the plan, compared by recorded model
id in `provenance`, and enforced in code: a plan whose writer and reviewer match is not approved. For a hand-written
plan the writer is a person or the agent that wrote it, and any validated reviewer model may be used.

**Validation before use.** The reviewer may not approve any plan until it has been validated against the labelled
ground truth: the frozen answer key `docs/planning/evidence/story-plan-retro/known-defects.json` and the findings files
in that directory, with clean plans as negatives, split once into a tuning half and a held-out half by book. The owner
sets the thresholds on the held-out half (decision D12, decided with the continuity-reader thresholds of D6). The
validation covers a named pairing of writer model, reviewer model and prompt; changing any of the three voids it until
the pairing is revalidated. Authority is per defect class: a class the labelled set does not contain (a dull or generic
plan, a plan that does not serve the request) has no measured recall, so the reviewer's verdict on it is advisory and
those classes are covered by the owner's sample until labelled data exists. Until validation passes, every plan goes to
the owner.

**Review by exception.** The owner reads every plan the model rejects or is unsure about, and a random sample of the
plans it passed, proposed at 1 in 10. The draw is seeded from the plan's content hash so it can be audited, and the
rate is the owner's to change. The sample exists to notice drift: if the owner overturns more than the D12 limit of
sampled passes, the reviewer is suspended, every plan goes to the owner, and the pairing is revalidated.

**What this is not.** Plan approval is a quality gate. It is not the safety gate: moderation, the validator, ADR-005's
approve-and-publish and ADR-015's rule that a child never sees model output are unchanged and do not depend on the
reviewer. A reviewer that passes a bad plan costs a wasted fill and, at worst, a book the owner then rejects.

From a one-line request the plan stage infers the hero, want, obstacle and change; takes band, length and style from
the profile and the guardian as today; uses the default protagonist only when the request names no one; and invents
everything else from material the plan itself declares. It asks nothing back. The existing K19 interpretation surface
keeps its template-only wording.

### 4. Typed directives, compiled

The `beats='...'` string is replaced, for retained shells and all new ones, by typed fields. A shape authors only
`role`, `words` and `function`. The event comes from the plan. Merge handling, option handling, plant and payoff
handling, narrative person and the craft rules are rendered by a compiler from graph plus plan into one instruction
per scene. Graph narration and option enumeration become unrepresentable instead of being linted.

Stage 1 fidelity keeps its job with a new target: did the prose depict the planned `event` and assert nothing in
`must_not_assert`.

### 5. Shape frozen, meaning generated

Frozen and reused: topology, depth, bottleneck placement, ending count and valence mix, node functions, word budgets.
Generated per book: plan, events, choice labels, threads and where state is planted, under shape constraints that keep
payoffs on bottlenecks (ADR-011 section 12 item 6).

Fills run scene by scene (a decision node with its single-choice arrivals) with the ledger slice as context, not as
one whole-book completion. Skeleton fill as built stays selectable until the pilot shows plan-first is not worse.

### 6. Evaluation led by reads

1. **Exact and blocking**: Layer 1, Layer 2, policy, and SP-1 to SP-9.
2. **Model continuity reader**: per sampled `(node, state)` path, against the ledger. Advisory until its agreement
   with human reads is measured on a labelled set fixed in advance. It never blocks on its own before that. The plan reviewer of Decision 3 is a separate stage with its own validation.
3. **Reader data**: reading trails (finish, rewind, choice split, payoffs seen), owner-only.

`validator/agency.py` and `scripts/check_prose_craft.py` are kept as smoke tests. Their counts are not evidence for or
against a change, and their advisories on the review surface are labelled as such.

At final approval the approver is shown three generated paths (one through a payoff, one to a setback) and answers one
recorded quality question. This adds a field to the approval record and changes nothing about who approves or what
approval permits.

### 7. Brief unpinning

For 8-11 and up, `brief_from_request` stops fixing `tier=1` and `structure_pattern`. Tier and pattern come from the
shape and the plan. 3-5 and 5-8 stay Tier 1.

### 8. What this ADR pauses

Catalog growth by mutation and the flywheel (ADR-020), retrofit state promotion beyond the six pilots, strict
remediation of the legacy shells, and cross-book diversity work are paused until the pilot reports. They are not
removed. The reading-level repair loop stays.

### 9. What would make this ADR wrong

- The Phase 1 retrospective test fails: plans extracted blind from the revised books and the 2026-11-20 fills do not
  let SP-1 to SP-9 and a ledger-based read find the defects already known.
- The pilot shows plan-first books are not preferred to fills of the same shells in blind reads, or contradictions
  persist in more than two of ten books.
- The short-request panel shows lower delivery or no gain in request fidelity.
- The plan reviewer cannot be validated against the labelled set, or is suspended by the exception sample more than
  once. Plan approval then stays with the owner, which is the amendment's fallback and is stricter than the
  ratified text; the rest of the ADR is unaffected.

In the first case the ADR is revised once and re-tested, then withdrawn if it fails again. In the others plan-first is
kept for catalog books only, or not at all, as the pre-registered criteria in the implementation plan state.

## Options Considered

### Option 1: Story Plan plus compiled directives on reusable shapes (chosen)

Addresses the cause. Reuses the validated shapes, the gate, the configuration walk and the August narrative-contract
checker. Cost is a new stage and a migration of the retained shells. Risk: a weak plan yields a coherent, dull book;
the difficulty moves to a page a person, or a validated reviewer, can judge.

### Option 2: Status quo plus more detectors, lints and prompt rules

Cheapest per step and what the last two days did. Rejected: the verification run showed prompt rules lose to beats, a
targeted detector's recall collapsed, and each fix is per shell across 84 shells. It cannot make a continuity or
plant-exclusivity property checkable, because the fact it would check against does not exist.

### Option 3: Skeleton-free generation (structure invented per request)

The path exists (`generate_story`). It carries the request whole. Rejected as the primary route for now: it gives up
validated shape properties, it was never held to the strict bar skeletons are, and its August evaluation answered a
diversity question, not a quality one. It remains the natural later step once shapes can be generated under the same
checks; unpinning the brief (Decision 7) removes its built-in statelessness in the meantime.

### Option 4: Per-skeleton narrative contracts (the August proposal as designed)

Contains most of the plan's fields. Rejected in its shared form: one contract across books measurably converges them,
and it was aimed at diversity. This ADR takes its checker and its fact model and makes the artifact per book.

### Option 5: Human-authored catalog only, no generation

Works for the family test and is how the four good books were made. Rejected as the product direction: it abandons
request-driven stories, which the vision and ADR-015 commit to.

## Consequences

### Positive

- Continuity, plant and payoff properties become exact set checks.
- The request's want and obstacle have somewhere to live.
- A validated reviewer screens a page before prose is bought, the owner reads the exceptions and a sample, and the
  owner reads three paths after.
- Scene-level retries replace whole-book loss.
- The shared artifact carries no words, which removes the main cross-book sameness channel as a side effect.

### Trade-offs

- A reviewer model may share the writer's blind spots, and the labelled set holds only the defect classes already
  found, so it can pass a plan the owner would reject. Mitigations: a different model, validation before use, the
  exception sample, and fail-closed handling. The cost is owner time on exceptions and the sample, which D12 bounds.

- A new stage with its own failure modes, cost and latency. Input tokens rise; the review's estimate of two to four
  times is untested and is measured in WP-2.6.
- More model invention per book, and a new untrusted-derived text surface (plan strings) that must be floored and
  screened.
- Retained shells must be converted; the rest of the catalog is left as it is and stays selectable on the old path.
- Hand-revised books have no shape. They are authored books with hand-written plans.

### Technical debt

- Two fill paths coexist until the pilot decides.
- `mutation/` and `flywheel/` stay in the tree unused while paused.
- Conditional passage text is deferred, so payoffs still need inserted arrival nodes.

## Follow-on work

Every item is a work package in the [implementation plan](../story-plan-implementation-plan.md). The register rows
below are **proposed**: they are listed in that plan's Appendix B for the orchestrator to add, because the agent
drafting this ADR was not permitted to edit the register. This ADR must not merge to `main` until those rows exist.

- **`UW-A64`** (`done` 2026-11-21): owner ratification of this ADR.
- **`UW-G28`** (`done` 2026-11-21): freeze actions and register dispositions (WP-0.1).
- **`UW-G29`** (proposed): hand-written plans and second-reader pass for the family-test books (WP-0.3, WP-0.4).
- **`UW-G30`** (proposed): Story Plan schema, checks and the retrospective gate (WP-1.1 to WP-1.5).
- **`UW-G31`** (proposed): brief unpinning (WP-2.1).
- **`UW-G32`** (proposed): retained shapes and typed directives (WP-2.2, WP-2.5).
- **`UW-G33`** (proposed): plan generation, persistence and approval (WP-2.3, WP-2.4); WP-2.4 now waits on the
  validated plan reviewer (amendment of 2026-11-21).
- **`UW-G34`** (proposed): scene-by-scene fill (WP-2.6).
- **`UW-G35`** (proposed): continuity reader with its validation set (WP-3.1, WP-3.2).
- **`UW-G43`** (amendment of 2026-11-21): the plan reviewer, its validation and its exception sampling (WP-3.7).
- **`UW-G36`** (proposed): request-fidelity measure and short-request panel (WP-0.2, WP-3.3, WP-4.1, WP-4.2).
- **`UW-G37`** (proposed): approver path sampling and quality question (WP-3.5).
- **`UW-G38`** (proposed): ten-book pilot and decision report (WP-4.3, WP-4.4).
- **`UW-G39`** (proposed, `blocked` on the pilot): conditional passage text, rule registry, lesson triage.

Existing rows this ADR is expected to supersede or re-scope are listed in the plan's Appendix B with the evidence each
needs.

## Note on the documentation nav

Not added to the `mkdocs.yml` nav, for the reason ADR-030 and ADR-031 record: that list stops at ADR-011 and the
directory is navigated through [`adr/README.md`](./README.md), which carries the index row.

## Related

- [Architecture review, 2026-11-20](../architecture-review-2026-11-20.md)
- [Structural verification, 2026-11-20](../structural-verification-2026-11-20.md)
- [Story Plan implementation plan](../story-plan-implementation-plan.md)
- [Skeleton narrative redesign proposal, 2026-08-09](../skeleton-narrative-redesign-proposal-2026-08-09.md)
- [Skeleton-free alternatives proposal, 2026-08-09](../skeleton-free-alternatives-proposal-2026-08-09.md)
