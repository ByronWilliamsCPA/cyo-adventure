# C2. The story fill stage: selection, binding, generation, fidelity/delivery

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/home/user/cyo-adventure/`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.

Component audit of `generation/`, `story_requests/`, and the fill-stage scripts, against the
2026-08-22 research brief sections 1-3, 4.1, 4.5. Everything below is grounded in code read in this
repo plus arithmetic executed against the committed catalog; where a number is computed, the
computation is named so it can be re-run.

Ranked most severe first.

---

## Branch reconciliation (done before finalising)

`git diff --name-status HEAD origin/claude/model-selection-skeleton-dev-78yp7u -- src/ scripts/`
returns exactly two rows, both additions, both skeleton-stage:

```
A	scripts/compare_skeleton_authors.py
A	scripts/modal_kimi_leg.py
```

**`src/` is byte-identical between the two branches, and every fill-stage script exists on both.**
So no finding below is a "this branch is missing the code" artifact, every code claim is class (c)
verified-on-both, and every code locus cited resolves identically in `/home/user/cyo-adventure/`
and in `.worktrees/brief-evidence/`. Spot-checked directly for the three claims where a
doc-vs-code gap would have mattered most: `select_axis`'s unused `exclude` (identical),
`.claude/skills/cyo-author/` carrying no differentiation directive (identical, `diff -rq .claude`
clean), and `provider_order` never reaching `build_provider`'s production legs (identical).

The evidence tree adds `AL-510`..`AL-514` and `UW-C317`..`UW-C320` to the logs. All five lessons
and all four work rows are **skeleton-stage** (recognition-protocol validation, `check_skeleton.py`
cell mode, blind-vs-tool-assisted authoring, the PL-18 message). `AL-490`..`AL-498`, the live fill
run, the primary record of the fill-rate hole, are present and identical on **both** branches, as
are `UW-C307`, `UW-C315`, `UW-C316`, `deepseek-v4-pro-live-fill-plan-2026-08-20.md`,
`vendor-comparison/` and `c302-fill-budget-options.md`. The evidence tree does carry
`skeleton-sourcing-test-plan-2026-08-21.md`, which is cited in C2-14 and C2-9 below.

**Two class-(b) status-honesty findings survive that reconciliation** and are folded into C2-1 and
C2-19: the brief §3.4 presents delivery measurement as part of "Story automated checks" alongside
the story gate, and §3.3 presents the fill as running through pinned, metered, budgeted machinery.
`UW-C307`'s own status line is the authority against the first: *"Still open: whether the
deterministic gate carries the check, which is what keeps this row scheduled."* The register is
honest; the brief's framing is what reads as delivered.

---

## C2-1: the fill-rate floor is a script, and the only production backstop is a downgrade that the chunked path cannot reach

- **Severity**: critical
- **Category**: delivery/fidelity
- **Locus**: `scripts/check_fill_integrity.py:67`; `src/cyo_adventure/generation/orchestrator.py:1517`
  and `:1560-1575`; `src/cyo_adventure/generation/fidelity.py:30`;
  `src/cyo_adventure/validator/policy.py:735`; `scripts/run_guard_battery.py:117`
- **Problem**: `grep -rn "fill_rate\|commissioned_words" src/` finds **no consumer in `src/`**
  outside `skeleton.py`'s own definition. The 0.6 floor lives only in
  `scripts/check_fill_integrity.py`, whose sole invoker is `scripts/run_guard_battery.py`, an
  offline authoring script. The deployed gate (`run_gate(doc, "standard", context="fill_result")`)
  has no fill-rate rule; its only word rules are PL-19's per-node maximum (ERROR) and the
  story-mean advisory (WARNING, `policy.py:735`). `UW-C307` says as much and keeps the row
  scheduled.

  What the audit adds is the shape of the *one* production backstop that does exist, and why it is
  weaker than it looks. On the authoring path `worker.py` calls `fill_skeleton(...,
  settings=_default_settings, stage1_gate="required")`, which arms
  `fidelity.py::word_count_violations` at ±40% per node. A 39%-delivery book would fire that on
  essentially every node, enter the shared repair budget, and, if unfixed, downgrade
  `passed` → `needs_review` with the storybook kept (`orchestrator.py:1560-1575`). That is real,
  but three things blunt it:
  1. It **never blocks**. It relabels a job for admin attention; the book is persisted and
     approvable.
  2. On the chunked path `max_repairs` is hard-set to `0` (`orchestrator.py:1517`), so a large or
     bound book gets the check and no repair at all, the 19-of-73 skeletons that chunk on the
     shipped default are exactly the ones where a re-fill is most expensive and most needed.
  3. The repair it does attempt is catastrophically shaped: `fidelity_repair.md` asks for **the
     whole corrected Storybook JSON**, so 631 flagged nodes on `the-last-cartage` means up to three
     more ~124k-token completions to fix a book that was already paid for once.
- **Why it matters for the goal**: the brief's F2 promises that "every gate is paired with a
  delivery measurement so a hollow pass is visible". In the deployed pipeline the pairing exists
  only as a status label an admin may or may not read, and the number itself, the ratio, the one
  quantity that makes the defect legible, is computed nowhere a human or a query can reach it.
- **Recommendation**: compute the ratio in `worker.py::_run_skeleton_fill` immediately after
  `fill_skeleton` returns (the skeleton is already loaded there, and
  `commissioned_words_by_node` is already importable), persist it on `generation_job`, put it on
  the admin review card next to the in-band percentage (`AL-491`/`UW-C308` require the pair), and
  force `needs_review` below 0.6 independently of the Stage-1 posture, so the chunked path and any
  future ungated caller are covered too. That is a contained change and it settles the measured-in-
  the-pipeline half of `UW-C307` without pre-empting the gate-carriage decision. Separately, give
  the chunked path a repair budget by making fidelity repair **batch-shaped** (re-ask only the
  flagged nodes, in batches) rather than whole-document; see C2-12.
- **How to check I'm right**: `grep -rn "fill_rate\|min_fill_rate\|commissioned_words_by_node" src/`,
  one file. `grep -rn "check_fill_integrity" --include='*.py' .`, one invoker.
  `orchestrator.py:1517` for `max_repairs=0 if chunked`. `fidelity.py:30` for the ±40% tolerance.

---

## C2-2: the fill prompt's own system block licenses the shortfall it asks the model to avoid

- **Severity**: critical
- **Category**: prompt design
- **Locus**: `src/cyo_adventure/generation/templates/drafting_guide.md:174` and `:187-189`;
  `templates/fill.md:35`; `templates/fill_subset.md:38`
- **Problem**: this is the mechanism behind `AL-490`, and it is **not** truncation, chunking, cap
  sizing, or the model quitting. The run's own numbers rule those out: the books parsed, no
  `finish_reason=length` was involved, delivery did not degrade with node count (632 nodes → 38.9%,
  267 → 52.9%, 193 → 42.7%), and delivered length was near-**constant** per book (means 30.7/37.4/
  43.3, sd 5-9) against commissioned ranges of 40-112. A model that quit would taper; a model that
  truncated would fail to parse. A model that settled on a house paragraph length and ignored the
  per-node number produces exactly this signature, including `AL-490`'s anti-correlation on book 3
  (nodes asking 100-124 words returned a mean of 40.7 while nodes asking 75-99 returned 51.5), which
  is what you get when the target is not read at all and longer beats invite terser summary.

  The prompt is why. Every fill prompt (one-shot, subset, bound, bound-subset) embeds
  `drafting_guide.md` verbatim in the **system** block, and that guide's node-length section says:
  *"There is no hard per-node minimum: a one-line beat is legitimate"* and *"Aim for the advisory
  band as a story-wide average, not a per-node rule: a tense beat can run three words."* The user
  block then carries 632 directives each saying `words=N`, softened by `fill.md:35` to *"Aim for
  this count; do not wildly overshoot or undershoot it"*, a preference, with overshoot named first,
  and overshoot is the only direction the gate punishes (PL-19's per-node max is the sole ERROR).
  A model reading both blocks correctly concludes short is safe and long is fatal. No fill prompt
  ever states the book's **total** commissioned word count, so there is no aggregate anchor either.
- **Why it matters for the goal**: this is the highest-leverage cheap fix on the board. The
  programme is paying frontier-prose prices to a model that has been told, in the system block, that
  the number it is billed against is optional.
- **Recommendation**: three edits, in expected-effect order. (a) In `fill.md`/`fill_subset.md`,
  restate `words=N` as a contract with a stated tolerance and consequence: "your prose for this
  passage must land within ±25% of `words`; a passage under that is rejected and rewritten".
  (b) Add a book-level line to the user block: "these N passages commission W words in total; a
  reply delivering under 0.8W is rejected". (c) Scope the guide's no-minimum sentence to skeleton
  *authoring*, where it is true because the author sets `words=`, and remove it from the fill-stage
  system block, or replace it with "the per-node target has already absorbed that judgement; do not
  re-make it".
- **How to check I'm right**: re-run one book from `runs/deepseek-v4-pro-2026-08-20/` under three
  arms, unmodified prompt, guide sentence removed, explicit ±25% contract plus book total, and
  report `check_fill_integrity.py --min-fill-rate 0` on each. Prediction: arm 1 reproduces
  0.39-0.53, arm 3 clears 0.8. Three completions, about $3. `compare_vendors.py` already runs this
  shape.

---

## C2-3: chunked fills bound output and ignore input; the input grows superlinearly and can exceed the context window

- **Severity**: critical
- **Category**: failure mode / cost control
- **Locus**: `src/cyo_adventure/generation/orchestrator.py:1189`, `:1196-1216`;
  `generation/chunking.py:222-276`, `:321-343`; `generation/skeleton.py:449-495`
- **Problem**: `plan_fill_batches` partitions to fit `max_tokens`, which is the **output** cap;
  `is_fill_feasible` bounds the *document*, never the prompt. `_fill_in_batches` computes
  `skeleton_json = json.dumps(skeleton)` **once, from the pristine skeleton** (`orchestrator.py:1189`,
  outside the loop) and re-sends that whole string on every batch, alongside
  `written_prose(document)`, which accumulates monotonically. Executing the real functions against
  the committed catalog:

  | skeleton | cap | batches | batch-1 input | last-batch input | total input | prose out |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | `the-last-cartage` (632 nodes) | 64,000 (shipped haiku) | 2 | ~120k tok | ~176k tok | ~296k tok | ~70k tok |
  | `the-last-cartage` | 32,768 (`deepseek-chat-v3.1`) | 4 | ~104k tok | **~193k tok** | ~594k tok | ~70k tok |
  | `the-tenfold-siege` (677 nodes) | 64,000 | 2 | ~119k tok | ~164k tok | ~282k tok | ~59k tok |

  At the shipped default the last batch sits within ~12% of Haiku's 200k window. At the 32,768 cap
  the last batch is ~193k tokens against that model's 128k window, an HTTP 400, which
  `openrouter.py::_raise_for_status` classifies `leg_fatal=True` as "invalid or unavailable model".
  That is the wrong diagnosis: the leg is fine, the prompt is too big. The leg is marked dead, the
  cascade falls to Sonnet then to a local 14B model, and the real cause never appears anywhere.
  Nothing screens for it, and the relationship is perverse: the **smaller** the output cap, the more
  batches, the **larger** every later prompt. `c302-fill-budget-options.md` correctly establishes
  that `UnpartitionableSkeletonError` is unreachable for any gate-valid skeleton; that analysis is
  entirely output-side and the input side was never asked.
- **Why it matters for the goal**: chunking exists to decouple the catalog from one vendor's output
  ceiling, and it currently re-couples it to an *input* ceiling that tightens as the output ceiling
  falls. It is also a straight cost multiplier, 594k input tokens to buy 70k output tokens, 8.5:1,
  on a path that runs for 19 of 73 production skeletons on the shipped configuration.
- **Recommendation**: (a) Stop re-sending the pristine skeleton. Send a structure-only projection
  (ids, choice ids/targets/conditions, `is_ending`) with bodies elided, plus the directive text for
  *this batch's* nodes only, directives for other batches are dead weight, and prose for written
  nodes is already in `prose_so_far`. (b) Bound `prose_so_far` to a relevance window (see C2-8).
  (c) Add an input-side screen beside `is_fill_feasible` that estimates prompt tokens per planned
  batch against a per-model `MODEL_CONTEXT_WINDOWS` table and re-plans rather than discovering a 400.
  (d) Classify a context-length 400 as a distinct planning failure, not a dead leg.
- **How to check I'm right**: run `plan_fill_batches` + `build_fill_subset_prompt` over
  `skeletons/16+/the-last-cartage.json` at `max_tokens=32768`, printing `len(system)+len(user)` per
  batch; the last exceeds 190k tokens at 4 chars/token. Confirm `skeleton_json` is bound once
  outside the loop at `orchestrator.py:1189`.

---

## C2-4: the production per-call timeout (120s) is an order of magnitude below measured fill latency

- **Severity**: critical
- **Category**: failure mode / cost control
- **Locus**: `src/cyo_adventure/core/config.py:507`; `generation/provider.py:721-735`;
  `providers/_base.py:213-283`; `providers/openrouter.py:238-245`;
  `docs/planning/deepseek-v4-pro-live-fill-plan-2026-08-20.md:321-328`
- **Problem**: `llm_timeout_seconds = 120` is passed straight into `httpx.AsyncClient(timeout=...)`
  for every cloud leg. The live run's three passing fills took **1874s, 687s and 469s**. Every one
  would hit the client timeout in production. `httpx.TimeoutException` is caught in
  `openrouter.py::_attempt` and mapped to `ProviderError(leg_fatal=False)`, *transient*, so
  `run_with_retries` retries 3x with exponential backoff, then `FallbackProvider` fails over to
  `openrouter_fallback_model` (Sonnet 4.6), which times out identically, then to the Ollama leg
  (`qwen2.5:14b`, `config.py:466`). The backend generates the completion whether or not the client
  is still listening, so each timed-out attempt is billed and discarded: up to six billed cloud
  completions of a 632-node book, none ever parsed, before a 14B local model is asked to write a
  16+-band children's book. `generation_job_timeout_seconds = 1800` would then SIGALRM the RQ job
  mid-cascade, leaving a `running` row for the reclaim sweep to force-fail.
- **Why it matters for the goal**: this is a live "one book costs 20x the median" mechanism in the
  shipped configuration that produces no artifact at the end of it, and it means the large end of
  the catalog, the scale the programme cites as its achievement, is undeliverable in production
  as configured.
- **Recommendation**: derive the per-call timeout from the request rather than pinning it, size it
  off `expected_output_tokens(skeleton)` and a measured tokens-per-second floor per leg, with a hard
  ceiling below `generation_job_timeout_seconds`, and raise that job timeout above the worst measured
  fill. Separately, a read timeout on a long generation must not be a plain transient: a retry
  re-buys the identical wall, which is the argument `AL-329` already made for
  `finish_reason=length`. Make it leg-fatal, or retry at most once at a raised timeout.
- **How to check I'm right**: `grep -n "llm_timeout_seconds" src/cyo_adventure/core/config.py
  src/cyo_adventure/generation/provider.py` and confirm the value reaches `build_openrouter_leg`
  unchanged; compare with the latency column at
  `deepseek-v4-pro-live-fill-plan-2026-08-20.md:321`. Then trace `httpx.TimeoutException` at
  `providers/openrouter.py:238-245` to `leg_fatal=False`.

---

## C2-5: no runtime budget exists; cost is measured after the money is gone

- **Severity**: critical
- **Category**: cost control
- **Locus**: `src/cyo_adventure/generation/usage.py:201-252`; `generation/cost.py:46-89`;
  `generation/worker.py:215-264`; `providers/fallback.py:40`
- **Problem**: metering is structurally sound, `MeteredProvider` makes an unmetered call impossible
  on a path that holds one, `ledger_of` documents its outermost-only constraint, and
  `fidelity_gate.py:84-89` threads the ledger into the review provider it builds internally so the
  Stage-1 call is billed. To answer the audit directly: **every call on the worker path is metered,
  cost is attributable per book and per leg (`estimate_run_cost` prices per call, never over run
  totals, precisely because one job mixes models), and retries are counted**, a retried attempt
  records no usage by design (`run_with_retries` returns the successful attempt's duration only),
  which under-counts a billed-but-timed-out attempt (C2-4). Reasoning tokens are collected but
  dropped at aggregation (C2-13).

  What does not exist is any *control*. `estimate_run_cost` is called exactly once, in
  `_stamp_provider_accounting`, **after** the pipeline returns. Nothing consults the ledger mid-run.
  There is no per-book ceiling, no check between repair rounds, no abort. The only bounds on spend
  are structural and generous: `max_repairs=3`, `reading_level_passes=2`,
  `FallbackProvider.max_total_attempts=30`, `MAX_ACTIVE_JOBS_PER_FAMILY=2`. Compose the worst case
  for a 632-node one-shot book: 1 fill + 3 whole-document repairs + up to 4 Stage-1 semantic reviews
  + 2 reading-level passes, each retried 3x transiently across 3 legs. Nothing says "stop at $X".
- **Why it matters for the goal**: "unit economics cap what any one book may cost to produce"
  (brief §1) is a hope, not a control. F7 lists spend guards as a measured lever and §4.5 records a
  mid-grid balance exhaustion; the *harness* gained `--resume`, preflight and credits checks, the
  *product* did not.
- **Recommendation**: add a `BudgetedProvider` wrapper (composes exactly like `MeteredProvider`)
  holding a per-job ceiling derived from `expected_output_tokens` times a configured multiple, that
  raises a distinct `BudgetExceededError` **before** issuing a call whose worst-case cost would
  cross it. Record ceiling and spend on `generation_job` so breaches are queryable, and surface a
  pre-flight estimate at authoring-plan time so an admin sees "about $X" before queuing.
- **How to check I'm right**: `grep -rn "estimate_run_cost" src/`, one caller, `worker.py:261`,
  inside `_stamp_provider_accounting`, whose own docstring places it on the success path and the
  interrupt guard. `grep -rn "budget\|ceiling" src/cyo_adventure/generation/` finds no spend guard.

---

## C2-6: semantic fidelity is one binary verdict per book, capped at 512 tokens, failing open

- **Severity**: high
- **Category**: delivery/fidelity
- **Locus**: `src/cyo_adventure/moderation/fidelity_review.py:51`, `:215-282`;
  `generation/fidelity_gate.py:67-93`; `generation/fidelity.py:79-166`
- **Problem**: answering the audit directly, fidelity is checked **per book**, not per node and not
  per path. `run_semantic_fidelity_check` assembles one prompt containing every originally-FILLed
  node's beat, its full filled prose, and every choice's original and final label, then asks for
  `{"verdict": "pass"|"flag", "notes": "<short>"}` with `max_tokens=512`. For `the-last-cartage`
  that is ~50k words of prose returning a single boolean. Any unparseable, empty, or non-JSON
  response returns `None` = pass (`:266-278`), by explicit design. The pure-code half checks three
  things: leftover directives, structural equality outside `body`/`label`, and word count within
  ±40%. Neither half reads a path, a variable, or an ordering, and **neither is ever given the theme
  brief**: `grep -n "theme_brief" src/cyo_adventure/moderation/fidelity_review.py` is empty. So
  yes: a book can pass fidelity while being incoherent (nothing compares two adjacent passages),
  dull (nothing scores craft), or off-premise (the premise is not an input).
- **Why it matters for the goal**: the brief calls this "the filled book is checked against its
  skeleton's directives before anything else runs". It is checked against three properties of the
  directive and one aggregate opinion. The defects the live run found by hand, beat restatement at
  0.51 content-word overlap, 23 verbatim-duplicate bodies, 605 of 674 labels drawn from three
  strings, "you" in only 12 of 193 nodes of a book whose beats specify second person, are all
  invisible to it, and all are cheap deterministic measurements (`AL-496`/`UW-C313` specifies them).
- **Recommendation**: (a) Split the semantic call per ~30-node batch and ask for a per-node verdict
  list rather than a book verdict; same order of cost, actionable output. (b) Add `AL-496`'s
  deterministic measures to the pure-code half where they cost nothing: duplicate-body count,
  distinct-label ratio, person/POV consistency against the beats' declared person. (c) Reconsider
  fail-open, an unparseable reviewer should mark `needs_review`, not `passed`; the downgrade is
  free and the current behaviour makes a review outage indistinguishable from a clean book.
- **How to check I'm right**: `fidelity_review.py:238-262` (one `blocks` list, one
  `review_provider.complete`) and `:266-278` (three fail-open returns). Confirm `theme_brief`
  appears nowhere in the module.

---

## C2-7: reconvergence is structurally invisible to the fill: conditions and effects are stripped from the work order

- **Severity**: high
- **Category**: coherence
- **Locus**: `src/cyo_adventure/generation/chunking.py:279-318` (`batch_request`);
  `templates/fill.md:72-83`; `generation/fidelity.py:79-122`
- **Problem**: `batch_request` builds each node's work order as `{node_id, directive, choices:
  [{id, label}]}`, and its docstring states the omission as deliberate: *"Targets, conditions, and
  effects are deliberately not included: the model is not asked to reproduce anything it is
  forbidden to change."* That conflates "must not write" with "must not know". A node reachable from
  two prior states, the audit's exact question, is written with no information about which
  variables may be set, what the reader has already done, or which of its own choices are visible in
  which configuration. The one-shot path is only marginally better: the whole skeleton is in the
  prompt so conditions are *present*, but `fill.md`'s only mention of them is in "What you must not
  change", i.e. as fields to copy, never as facts to write consistently with.

  The live run produced the predicted defect and recorded it: `end_fixed_trust1` appending "the
  lamp's last oil burned somewhere your memory will not name yet" to a beat that says nothing about
  the lamp, on a node reachable at `light` 0 through 3. Nothing catches it: `structure_violations`
  compares fields, `word_count_violations` compares lengths, and the semantic reviewer sees one
  node's beat and prose with no state context.
- **Why it matters for the goal**: reconvergence is not incidental to this catalog, it is its shape,
  the prompt's own budget block instructs that "separate branches must RECONVERGE onto shared
  later nodes (a branch-and-bottleneck shape)". A high in-degree node written as if one particular
  path led to it is wrong for every other path, and the reader on the other path is the one who
  notices. This is also the class the tier-2 book was in the vendor grid to find, and it found it.
- **Recommendation**: give each work-order entry a computed **arrival context**: the variable states
  under which the node is reachable (the condition evaluator exists in `storybook/`, and
  `validator/` already computes configuration-aware reachability for PL-20/25/26 per `UW-C292`),
  plus in-degree and the distinct choice labels that arrive there. Add the prompt rule: "this
  passage is reached from N different prior states; it must be true under all of them, assert
  nothing the reader may not have done." Pair it with a deterministic check: for any node with
  in-degree > 1, flag a body making a definite reference to an object or event established only on
  a subset of its inbound paths. That is `AL-495`/`UW-C312`'s outbound CG-4 companion, generalised
  from choice labels to path state.
- **How to check I'm right**: `chunking.py:312-315` builds the choice list as `{"id", "label"}`
  only. `grep -n "condition\|effects" src/cyo_adventure/generation/templates/fill.md` returns only
  the "must not change" list. `grep -n "variables" src/cyo_adventure/generation/fidelity.py` is
  empty except in the frozen-field tuple.

---

## C2-8: cross-chunk coherence rests on an unordered bag of prose plus a duplicated skeleton

- **Severity**: high
- **Category**: coherence
- **Locus**: `src/cyo_adventure/generation/chunking.py:321-343` (`written_prose`), `:143-186`
  (`_narrative_order`); `templates/fill_subset.md:60-69`, `:105-120`
- **Problem**: `written_prose` returns `{node_id: body}` for every already-written node, a dict, in
  document order, with no indication of reading order, depth, path, or which of those passages
  precede the ones being written now. `fill_subset.md` then instructs the model to "Reuse the names,
  places, objects, and vocabulary those passages established". For batch 2 of `the-last-cartage`
  that is 325 passages to scan to answer "what is the lantern called". Batching order is
  breadth-first from `start_node`, which does guarantee ancestors precede descendants, the one real
  coherence property in the design, but that ordering is never surfaced to the model, and the
  invariants that actually need to hold (cast, place names, props, tense, person) are never
  extracted. Meanwhile the prompt also carries the pristine skeleton, so every already-written node
  appears **twice**: once as its `<<FILL>>` directive, once as prose under "Already Written". The
  model receives contradictory framing for the same node in one prompt.
- **Why it matters for the goal**: this is the difference between a book and several stories stapled
  together, and the design's own justification: "Passing back what is already written costs input
  tokens (cheap) rather than output tokens (the constrained resource)", is doing a lot of work for
  a mechanism that enforces nothing. Input tokens are cheap per token and this strategy spends 4-8x
  the output volume on them (C2-3).
- **Recommendation**: replace the raw prose dump with a **story bible** the pipeline maintains across
  batches, a small structured block (cast names with one-line descriptions, place names, named
  props, declared tense and person, plus the last three passages in reading order verbatim) that the
  first batch emits alongside its prose and each later batch extends. Bounded, ordered, cheap, and
  checkable: a deterministic post-pass can assert every proper noun in a later batch appears in the
  bible or is newly declared there. Keep full prose only for this batch's immediate ancestors.
- **How to check I'm right**: `written_prose` returns `dict[str, str]` with no ordering contract
  (`chunking.py:337-343`). Build a batch-2 prompt and grep the user block for one already-written
  node id, it appears in both `{skeleton_with_fill_directives}` and `{prose_so_far}`.

---

## C2-9: the differentiation directive is absent on two production paths, and its anti-repeat feature is dead code

- **Severity**: high
- **Category**: differentiation
- **Locus**: `src/cyo_adventure/generation/prompts.py:480-576`;
  `story_requests/authoring_plan.py:404-414`, `:610`; `generation/variation.py:205-235`;
  `.claude/skills/cyo-author/`
- **Problem**: **assessment of the mechanism first.** It is plausible and carefully built.
  `build_differentiation_directive` emits three things: the drawn craft axis instruction ("Lead with
  sound. Establish each new place by what can be heard there before what can be seen."), an
  escalation paragraph keyed to `tree`/`leaf`/`catalog`, and the titles of prior stories on this
  skeleton with an explicit "you are being told what to differ from, not what those stories said".
  It never carries another child's request text, and the docstring explains why, a genuinely good
  privacy decision. It is threaded into all four prompt variants and into every batch of a chunked
  fill (`_ChunkedFillContext.differentiation_directive`), so it is not confined to the first batch.

  Three gaps:
  1. **The admin skeleton-override path passes `_Differentiation()`** (`authoring_plan.py:414`), so
     `level=None` renders "No similarity context was available for this request. Write it straight."
     An admin overriding the pick is *more* likely to be serving a family that has exhausted the
     cell, not less; this disables the steering precisely where it is most needed. The code comment
     says so plainly ("Override path: no similarity context is computed"), it is a known
     simplification, not an oversight, but the direction is wrong.
  2. **The skill mechanism never sees it.** `grep -rn "differentiation" .claude/skills/cyo-author/`
     is empty on both branches, and `import_story.py::resume_manual_fill` builds none. The
     `awaiting_manual_fill` path is a production prep mechanism (`authoring_plan.py:598`) carrying
     no anti-repetition steering at all.
  3. **`select_axis`'s `exclude` parameter is never passed** (`authoring_plan.py:610`:
     `select_axis(str(request.id))`). The library holds 14 axes and the seed is a UUID, so a
     family's four books have roughly a 40% chance of a repeated craft axis, and the documented
     "avoiding recent ones" behaviour is unreachable in production.
- **What I predict it buys**: the axis instruction is the half most likely to move the number,
  because it changes *sentence construction*, and `AL-498` established that the leak is generic
  connective prose with the nouns already swapped ("home and look at", "who had the key", "the next
  thirty years"). The escalation paragraph and the prior-titles list are noun-level instructions
  attacking a non-noun-level defect. My prediction: the full directive moves 96.3 shared 4-grams
  /1000 by well under half, call it to the 40-70 range, still an order of magnitude over the 4.0
  budget, and the axis alone accounts for most of whatever movement there is. At 24x budget the
  brief is right that the directive "would have to carry an implausible amount of the load".
- **How to measure it cheaply, most of this is already built.** `compare_vendors.py` now takes
  `--differentiation` (per-brief specs rendered through the production
  `build_differentiation_directive`, recorded in report metadata so a directed floor can never be
  quoted as the raw one), and the best-case directed spec for this exact pair is **committed** at
  `docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/shared-skeleton-pair-directed/differentiation.json`
  (level `catalog`, opposed axes `close_interior`/`wide_observational`, sibling title carried). Per
  `UW-C315` the delta run failed only because the 2026-08-20 session's network policy answered 403
  to CONNECT for `openrouter.ai`. So the measurement is **one invocation** where OpenRouter is
  reachable, against the recorded 96.3 baseline. I would extend it to four arms rather than two,
  undirected (the 96.3 baseline), axis only, escalation+titles only, full directive, which is four
  fills at roughly $1.50 total and separates the two halves instead of scoring their sum.
- **Recommendation**: run the four-arm delta before investing further in the block's wording; it is
  the cheapest open question in this component. Independently of the result, close the three
  coverage gaps: compute `similarity_context` on the override path too (the pick and the
  differentiation signal are independent questions), thread the directive into
  `resume_manual_fill`/the skill, and pass the family's recent axis keys as `exclude`.
- **How to check I'm right**: `grep -rn "select_axis(" src/`, one call site, no `exclude`.
  `grep -rn "differentiation" .claude/skills/ src/cyo_adventure/generation/import_story.py`, no
  matches on either branch. `authoring_plan.py:404-414` returns `_Differentiation()` on the override
  branch. `ls docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/shared-skeleton-pair-directed/`
  for the committed spec.

---

## C2-10: the production provider cascade is unpinned, and its fallback legs run under the primary's output cap

- **Severity**: high
- **Category**: provider
- **Locus**: `src/cyo_adventure/generation/provider.py:721-735`, `:397-440`;
  `generation/orchestrator.py:1408-1434`; `providers/openrouter.py:191-195`;
  `providers/fallback.py:72-76`; `vendor-comparison/vendors-deepseek-v4-pro.json::_pinning_rationale`
- **Problem**: the brief says the comparison ran "backend-pinned with fallbacks disabled". Production
  does neither. `build_provider` constructs `FallbackProvider(legs=[haiku-4.5, sonnet-4.6, ollama
  qwen2.5:14b])` with `provider_fallback_enabled=True` by default, and **never passes
  `provider_order`**: `build_openrouter_leg` accepts the pin, but the production call sites at
  `provider.py:723` and `:730` omit it, so `allow_fallbacks: false` is never sent and OpenRouter may
  route `anthropic/claude-haiku-4.5` to any backend serving that alias, at any quantization, at any
  declared output ceiling. The repo states the consequence for a different slug in the strongest
  terms: *"Pinning is a CORRECTNESS requirement for this slug, not reproducibility hygiene ...
  declared output ceilings from 16,384 to 1,048,576 while MODEL_OUTPUT_CAPS records one per-slug
  value."* `UW-C316` carries that as an open decision for the *table*; nobody has asked the same
  question of the production cascade.

  Compounding it: `fill_skeleton` resolves the cap once from `getattr(provider, "model", None)`, and
  `FallbackProvider` declares `name` but **no `model`** (`fallback.py:72-76`), so a cascade falls
  through to `active_fill_model(settings)`, the *primary's* model. Every fallback leg then runs
  under a cap resolved for a different model. `orchestrator.py:1420-1428` registers this as a known
  residual (`UW-C271`) and guesses conservatively rather than resolving it. The last leg is a 14B
  local model writing children's prose at 16+ band.
- **Why it matters for the goal**: an alias silently re-pointed behind the scenes is
  indistinguishable, in this pipeline, from a quality regression the team would spend weeks chasing.
  The brief's §4.4 is a document about not trusting instruments; the production generation path has
  no instrument for "which model actually wrote this book". `TokenUsage` records the leg that
  answered, the right design, but the leg is `openrouter:<slug>`, and the slug is exactly the
  ambiguous thing.
- **Recommendation**: add an `openrouter_provider_order` setting and pass it on every production
  leg, so a substitution becomes a visible 404 rather than a silent quality change. Give
  `FallbackProvider` a `model` property reflecting the *current* leg and resolve the cap per leg
  rather than once per job, closing `UW-C271`. Reconsider the Ollama leg's place in a fill cascade
  (defensible for a health probe, not for a child-facing book) or gate it by band and length.
- **How to check I'm right**: `grep -n "provider_order" src/cyo_adventure/generation/provider.py`,
  declared in `build_openrouter_leg`, never supplied by `build_provider`. `grep -n "def model"
  src/cyo_adventure/generation/providers/fallback.py`, absent. `orchestrator.py:1420-1428` for the
  documented gap.

---

## C2-11: nothing downstream of the adapter reads `finish_reason`, so truncation is diagnosed as malformed JSON

- **Severity**: high
- **Category**: failure mode
- **Locus**: `src/cyo_adventure/generation/usage.py:130-144`; `providers/openrouter.py:346-380`;
  `generation/orchestrator.py:450-479`, `:1218-1236`
- **Problem**: `Completion.finish_reason` was added specifically so a truncation and a dead endpoint
  could be told apart, and its docstring says so. `grep -rn "finish_reason" src/cyo_adventure/
  --include=*.py | grep -v providers/` returns **only comments and the dataclass field**. The
  adapter uses it in one place: `leg_fatal = finish_reason == "length"`, and only inside `if not
  content:`. A truncated but *non-empty* completion (the ordinary case for an under-sized cap, and
  the live one for an unpinned endpoint-spread slug per `AL-479`/`AL-499`) returns as an ordinary
  `Completion`. `_run_one_stage` then fails `json.loads`, returns `_empty_blocked_gate`, and the
  repair loop burns its budget on a document that was never wrong, only cut off. On the chunked path
  the batch is rejected as "produced no usable prose", naming the wrong cause. `AL-492` records the
  same blindness for `content_filter`: the run logged `finish_reason=None` for a prompt the raw API
  answers `content_filter` for, and flattened it to "transient failure persisted".
- **Why it matters for the goal**: §4.5 lists "caps below reasoning overhead" among three dominant
  waste modes and says all three now have countermeasures in the harness. The product pipeline has
  the data for the countermeasure and discards it, and `UW-C309` asks for exactly this surfacing.
- **Recommendation**: thread `finish_reason` out of `_run_one_stage` alongside the gate result. On
  `"length"`, do not repair: record a distinct `truncated_at_cap` outcome, log the resolved cap and
  model, and on the one-shot path retry via the chunked path rather than the repair path. On
  `"content_filter"`, mark the (skeleton, brief) pair rather than retrying at ~130s an attempt.
  Persist the reason in the job report so a cap mis-resolution is queryable.
- **How to check I'm right**: the grep above returns four lines, none of them a read.
  `orchestrator.py:471-479` discards `completion` after reading `.text`.

---

## C2-12: `expected_output_tokens` prices only the prose, so the one-shot path spends ~43% of its budget re-emitting frozen structure

- **Severity**: high
- **Category**: cost control
- **Locus**: `src/cyo_adventure/generation/skeleton.py:340`, `:432-446`, `:449-495`;
  `templates/fill.md:63-83`; `generation/chunking.py:456-547`
- **Problem**: `expected_output_tokens = ceil(sum(words) * 2.0)` counts commissioned prose words and
  nothing else. But the one-shot contract is "the output must be the full Storybook JSON, not a diff
  or patch", so the model must re-emit every node id, choice id, target, condition and effect, every
  ending block, `variables` and `metadata`, all frozen, all already in the prompt. Measured against
  the committed catalog (bodies blanked, `json.dumps(separators=(',',':'))`, ~3 chars/token):

  | skeleton | prose ≈ | structural envelope ≈ | `expected_output_tokens` |
  | --- | ---: | ---: | ---: |
  | `the-last-cartage` | 70k tok | **54k tok** | 99,906 |
  | `the-tenfold-siege` | 59k tok | **46k tok** | 84,466 |
  | `the-mapmakers-island` | 31k tok | 16k tok | 44,210 |

  The 2.0 factor absorbs some of this on prose-heavy books and under-shoots on branch-heavy
  gamebooks, where nodes are short (`the-tenfold-siege` averages 62 commissioned words across 677
  nodes) and per-node JSON overhead is near-constant. The screen's error is therefore *structural*
  and proportional to node count, with the 0.8 `_FEASIBILITY_MARGIN` hiding it. On the money: ~43%
  of the one-shot output tokens on the largest book are billed at the output rate to reproduce bytes
  the pipeline already holds, and the chunked path proves it unnecessary, since `merge_fill_batch`
  reads only `body` and `label` and rebuilds everything else by dict spread.
- **Why it matters for the goal**: this is the cheapest available cost reduction at the fill stage,
  and it retires a defect class the live run recorded, book 1 renaming the storybook `id`
  (`sk_last_cartage` → `sk_last_codex`), book 2 rewriting the top-level `title` and 27 of 36 ending
  titles. A model that never emits those fields cannot corrupt them.
- **Recommendation**: make the batch-shaped reply (`{node_id: {body, choices}}`) the **only** fill
  contract, with batch count 1 where the book fits. That collapses two contracts into one, retiring
  `AL-494`/`UW-C311`'s three-site `ending.title` disagreement as a side effect, since one whitelist
  would then decide it, removes the structural-drift class, cuts one-shot output cost ~40% at the
  large end, and makes a *batch-shaped fidelity repair* possible, which is what would give the
  chunked path back the repair budget C2-1 says it lacks. Then re-derive `_TOKENS_PER_FILL_WORD`
  against the reply shape actually emitted.
- **How to check I'm right**: re-run the arithmetic, load each skeleton, blank every `body`, dump
  compactly, compare to `expected_output_tokens`. Then read `chunking.py:456-547` and confirm every
  non-body field is rebuilt from `document`.

---

## C2-13: reasoning and cache tokens are collected but never aggregated, persisted, or priced

- **Severity**: medium
- **Category**: cost control
- **Locus**: `src/cyo_adventure/generation/usage.py:94-111`, `:246-252`;
  `providers/anthropic.py:182-218`; `providers/openrouter.py:133-140`
- **Problem**: `TokenUsage.reasoning_tokens` exists, is populated by the OpenRouter adapter, and
  carries an excellent docstring explaining why it matters ("cost per delivered book spans 36x
  across legs asked for the identical book while the prose written spans 1.36x", `AL-332`). Then
  `UsageLedger.snapshot()` does not sum it, `UsageTotals` has no field for it, and no column stores
  it. The one figure that explains a 36x cost spread is discarded at the aggregation boundary, and
  recovering it requires the per-call ledger, which is never persisted ("Nothing writes one today",
  `metered.py:26-29`). Separately, the direct-Anthropic adapter reads only
  `usage.input_tokens`/`output_tokens` (`anthropic.py:214-217`), not `cache_creation_input_tokens`
  or `cache_read_input_tokens`, which the Messages API reports separately, excludes from
  `input_tokens`, and bills at different rates. On a design whose whole premise is a large cacheable
  system prefix, those are the tokens that matter, and the direct adapter never sets
  `cache_control` at all, so the prefix is not cached there in the first place. Only the OpenRouter
  leg marks it, and only for `anthropic/`-prefixed slugs.
- **Why it matters for the goal**: per-stage model selection (F4) is a cost decision being made
  against a cost record that omits both the hidden-burn term and the caching term.
- **Recommendation**: add `reasoning_tokens` to `UsageTotals` and to the `generation_job` accounting
  columns; add cache-read/cache-write counts to `TokenUsage` and to `core/pricing`'s rate model; set
  `cache_control` on the system block in the direct-Anthropic adapter. Persist the per-call ledger as
  pipeline events, it already retains calls in order specifically so this is possible.
- **How to check I'm right**: `usage.py:246-252` constructs `UsageTotals` from five sums, none
  reasoning. `grep -rn "cache_creation\|cache_read\|cache_control" src/`, one hit, in
  `providers/openrouter.py`.

---

## C2-14: premise-to-skeleton fit is a 37-tag closed vocabulary that most real premises miss entirely

- **Severity**: medium
- **Category**: matching
- **Locus**: `src/cyo_adventure/generation/skeleton_match.py:385-464`, `:597-676`;
  `diversity/normalize.py::SIMILARITY_TAG_MAP`
- **Problem**: answering the audit's `S-3` question, what the code does today when premise and
  armature fit badly is **nothing**. Fit enters selection as one multiplicative bonus,
  `weight * (1 + containment(request_tags, story_tags))`, both sides from `similarity_signature`, a
  215-key → 37-tag closed map. Executed against real-shaped premises: *"a story about a girl who
  finds a hidden door in her grandmother's attic"* → `frozenset()`; *"a soccer team that discovers a
  magic ball"* → `{'magic'}` (`soccer` is not a key, and there is a `sport` tag it never reaches).
  An empty request signature gives every candidate a bonus of 0.0, collapsing the pick to
  recency-weighted random, the documented intended fallback, but it means that for a large share of
  premises the fit question is not asked at all. Nor is it answered afterwards: no fit score is
  persisted, the fidelity reviewer never sees the brief (C2-6), and `check_fill_fidelity.py`
  measures obligations against a *contract* rather than the child's request, at a self-reported
  precision of 0.167.
- **Why it matters for the goal**: `AL-497` is the symptom. Book 1's mine skeleton reskinned to a
  desert kept the mine's physics, sand ponding upward from a sump like water, a firedamp
  safety-lamp beat in a room full of vellum, because nothing anywhere asks whether the armature
  suits the premise, before or after. `skeleton-sourcing-test-plan-2026-08-21.md` §4 designs the
  right instrument for the *experiment* (forced-choice identification: a blind judge picks which of
  N cell-matched briefs a provenance-stripped book serves, chance-corrected), and E3 makes 2 of 6
  briefs deliberately unservable so the coverage falsifier is decidable, but that instrument is
  marked "to build", and none of it is a production signal.
- **Recommendation**: two separable steps. (a) Cheap and immediate: persist the computed
  `theme_overlap` for the chosen slug on `authoring_metadata`, and warn the admin when it is 0.0 for
  every candidate ("no skeleton in this cell matches this premise's themes; the pick is arbitrary").
  That turns an invisible condition into an admin decision and hands E3's coverage falsifier its
  denominator for free. (b) The real instrument: world-physics coherence is a paraphrase problem, so
  scope it as `AL-497`/`UW-C314` proposes, a *ratio* of skeleton-frequent-and-brief-absent
  vocabulary to brief vocabulary over an open vocabulary, which is deterministic and would have
  caught both books a closed word list missed in opposite directions.
- **How to check I'm right**: run `similarity_signature({"premise": p})` over 20 real request texts
  and count the empties. `select_skeleton_for_cell:660-667`, the bonus is the only fit term, and it
  is multiplicative on a weight that never reaches zero.

---

## C2-15: six of the catalog's reachable cells have no production-eligible skeleton, and the 422 lands after guardian approval

- **Severity**: medium
- **Category**: matching
- **Locus**: `src/cyo_adventure/story_requests/authoring_plan.py:417-423`, `:140-157`;
  `generation/skeleton_match.py:352-382`
- **Problem**: `candidates_for_cell` executed over the committed catalog returns **0** for
  `(3-5, long, prose)`, `(5-8, long, prose)`, `(13-16, short, prose)`, `(13-16, short, gamebook)`,
  `(16+, short, prose)` and `(16+, short, gamebook)`. Cell depth elsewhere is 3-5 skeletons, which
  reproduces `Q-1`'s "a child exhausts a cell by roughly the fourth request" against the current
  catalog. `_length_of` already knows about part of the hole and papers over it for *null* lengths
  ("`medium` for the teen bands ... which have no `short` skeleton on disk"), but an explicitly
  chosen short length at 13-16 still raises `ValidationError("no production-eligible skeleton
  available for band ...")`, and it raises in `build_authoring_plan`, i.e. after the guardian has
  approved the request and an admin is assigning a plan. The child's request was accepted, screened
  and approved; the failure surfaces two steps later, to a different person.
- **Why it matters for the goal**: a product-visible dead end reached by an ordinary combination of
  options the intake offers.
- **Recommendation**: validate cell availability at request-intake time,
  `candidates_for_cell` is a pure filesystem scan with no session dependency, so the intake form can
  simply not offer a length/style whose cell is empty. Separately, either author into the six empty
  cells or remove those combinations from the schema; a cell that cannot be served should not be
  selectable.
- **How to check I'm right**: run `candidates_for_cell(band, length, style)` over the 24 valid cells
  (ADR-011 collapses style to prose below the teen bands) and count the empties. Trace the raise at
  `authoring_plan.py:417-423` back to `api/story_requests.py::create_authoring_plan`.

---

## C2-16: the 0.6 fill-rate floor is calibrated against the tail of known-good fills, not against readability

- **Severity**: medium
- **Category**: delivery/fidelity
- **Locus**: `scripts/check_fill_integrity.py:48-67`; `src/cyo_adventure/generation/fidelity.py:27-30`
- **Problem**: the audit asks what a book at 0.61 reads like. The comment block answers honestly and
  the answer is uncomfortable: the tightest **known-good** committed pair sits at 0.635 and another
  at 0.668, so the floor clears real books by 0.035, not the 0.115 the headline calibration
  suggests, and "a raise above ~0.63 starts rejecting known-good fills". A 0.61 book is therefore
  not a marginal pass, it is inside the same distribution as accepted books, which means the floor
  separates nothing but the extreme. Concretely: uniform 0.61 delivery at 16+ prose is a story mean
  of ~107 words against a 175 target and a 125-230 advisory. PL-19 warns on every such book, PL-23
  reports a declared read time roughly 1.6x the derived one, and `AL-491` says the top bands then
  land 5.6-15.5% of nodes in the FK window because short choppy prose scores low. `AL-495` adds that
  at that density bodies stop staging the objects their own outbound choice labels name. A 0.61 book
  is the `AL-490` failure mode one notch up, and it passes.

  The per-node half is looser still. `_WORD_COUNT_TOLERANCE = 0.4` is self-described as "a generous
  starting tolerance, not calibrated against real fill runs yet", and it is **symmetric**, so a node
  at 61% of target passes, the book-level floor passes, and nothing sees a problem, even though the
  gate punishes over-length hard (PL-19 ERROR) and under-length not at all.
- **Why it matters for the goal**: the floor is a band-aid and the code says so. `UW-C307` treats it
  as the measured-first step, not the answer. Reading `AL-490` as closed would be the wrong reading.
- **Recommendation**: keep 0.6 as a hard floor (it correctly refuses the unpublishable) and add a
  separate, higher **advisory target** (0.85) reported on every book, so the gap between "not
  unpublishable" and "what we commissioned" stays visible. Calibrate the real threshold against
  reading quality rather than against the existing corpus' tail: take committed pairs spanning
  0.63-0.99, have a blind rater rank them, find where the ranking breaks. Make
  `_WORD_COUNT_TOLERANCE` asymmetric (tight under, loose over) to match the gate's own asymmetry.
- **How to check I'm right**: run `check_fill_integrity.py --min-fill-rate 0` over the 48 committed
  `(skeleton, filled)` pairs and plot; confirm two known-good pairs sit under 0.67. `fidelity.py:27-30`
  for the tolerance's own self-assessment.

---

## C2-17: recency weighting never excludes, and counts authoring activity rather than delivery

- **Severity**: medium
- **Category**: matching
- **Locus**: `src/cyo_adventure/generation/skeleton_match.py:552-594`, `:677-729`;
  `story_requests/authoring_plan.py:459-485`
- **Problem**: answering the audit on a heavy re-requesting family: `_weight` is `1/(1+recent_count)`
  and `_blended_weight` is `1/(1+recent_count+3*similar_count)`, both with an explicit never-zero
  floor (decision C-4). In a 4-candidate cell where a family has used one skeleton 3 times for
  similar themes, that slug's weight is 1/13 against 1.0 for a fresh one, about 2.5% of draws.
  Reasonable *while fresh candidates exist*. Once every candidate has been used (the `leaf` level,
  reached by the fourth request per `Q-1` and confirmed by the 3-5 candidates per cell measured in
  C2-15), all weights equalise and the pick is uniform over already-read structures, with the entire
  differentiation burden transferred to a prompt block whose effect is unmeasured (C2-9). The
  system's response to exhaustion is a warning string and a `CELL_SATURATED` event for the flywheel;
  there is no refusal, no deferral, and no "we should write you a new one first".

  Additionally `recent_skeleton_usage` counts **every** `storybook_version` row regardless of status
  (documented as a deliberate product choice at `:709-729`), so three failed or unapproved attempts
  on one skeleton de-weight it as heavily as three delivered books the child actually read. The
  child's *experience* of repetition is not the quantity being measured.
- **Why it matters for the goal**: `S-4` (repeat-reader distinctness) is open, and this is the code
  that decides what a repeat reader gets. The honest description today: after four requests in a
  cell, a family is served a structure they have read before, with a prompt paragraph telling the
  model to try harder.
- **Recommendation**: make the `catalog` escalation actionable rather than advisory, at that level
  either hold the request until the flywheel produces a new skeleton for the cell, or route it to
  the mutation core (ADR-020) for a per-family structural variant, and tell the guardian which is
  happening. Separately, weight on delivered versions (join `Storybook.status`/`approved_by`) for
  recency while keeping the authored count for cost accounting.
- **How to check I'm right**: `skeleton_match.py:552-565` and `:577-594` for the never-zero floor;
  `:709-729` for the unfiltered query and its `#ASSUME` block stating the choice.

---

## C2-18: the checks that would catch the defects the gate cannot see are all manual scripts

- **Severity**: medium
- **Category**: delivery/fidelity
- **Locus**: `scripts/check_sibling_fills.py`, `scripts/check_prose_craft.py`,
  `scripts/check_fill_fidelity.py`, `scripts/run_guard_battery.py:31`
- **Problem**: the fill stage's real quality instruments, sibling 4-gram convergence (the mechanism
  behind the 96.3/1000 finding), prose craft (tense instability, narrator moral tags, told emotion),
  and obligation delivery, all exist, all work, and none is reachable from `generation/`.
  `check_sibling_fills.py` is not even in `run_guard_battery.py`, whose docstring says so under
  "What it deliberately does not run"; `check_prose_craft.py` is in the battery, but the battery is
  an authoring-time script. So the production quality surface for a filled book is: `run_gate`
  (structure/safety/reading level), the Stage-1 fidelity pair (C2-6), the moderation pipeline, and a
  human. `UW-C315` tracks the sibling half explicitly ("wire `check_sibling_fills.py` into the fill
  pipeline as a same-skeleton sibling gate rather than a manual script"); the craft half is
  untracked.
- **Why it matters for the goal**: `AL-170` is the precedent, nine books cleared every gate and a
  blind rater called three unpublishable on defects no gate could see. Those defects now have
  deterministic detectors, and the detectors are not in the path.
- **Recommendation**: run `check_prose_craft`'s measures inline in the Stage-1 pure-code half (they
  are dependency-free string work over a document already in memory; there is no reason for a
  subprocess), reporting as advisories on the job. For siblings, run `check_sibling_fills` against
  the family's prior fills of the *same slug* at publish time, the query is cheap, the set is
  small, and it is the only check that can see the defect the reuse strategy causes by design.
- **How to check I'm right**: `grep -rn "check_prose_craft\|check_sibling_fills" src/`, nothing.
  `scripts/run_guard_battery.py:31` names what it omits.

---

## C2-19: the brief presents script-only and comparison-only machinery as the running pipeline

- **Severity**: medium
- **Category**: delivery/fidelity (status honesty)
- **Locus**: brief §3.3, §3.4, §4.1 against `src/cyo_adventure/generation/`;
  `docs/planning/unscheduled-work-register.md::UW-C307`, `UW-C315`, `UW-C316`
- **Problem**: this is the class-(b) residue after branch reconciliation, nothing here is missing
  code on another branch; it is a framing gap between the brief and the deployed pipeline. Three
  specific reads:
  1. §3.4 lists delivery measurement under "**Story automated checks**", between the Stage-1
     fidelity gate and the story gate: "`check_fill_integrity.py` enforces a minimum fill rate
     (0.6...)". A reader takes that as a stage of the pipeline. It is a CLI with one offline
     invoker (C2-1). `UW-C307`'s own status line is the correct statement: *"Still open: whether the
     deterministic gate carries the check."* §3.4 does flag the sibling check's wiring as open
     (`UW-C315`), the fill-rate floor gets no equivalent caveat, and it is the more load-bearing of
     the two.
  2. §3.3 says "Every call is metered ... cost accounting is response-level where the provider
     reports it." True and well-built, but adjacent in a section describing production, it reads as
     cost *control*. There is none at runtime (C2-5).
  3. §4.1 describes the vendor comparison as "backend-pinned with fallbacks disabled", correct for
     the comparison and the right methodology, but production is neither pinned nor fallback-free
     (C2-10), and no line says so. The brief's own §4.1 caveat about `AL-498` being "the RAW
     undirected floor" is exactly the right instinct applied to a different claim; the pinning claim
     needs the same.
- **Why it matters for the goal**: the brief is explicitly the account "of the system as it actually
  runs today" and is the document a reader uses to decide where to spend next. Three of the four
  countermeasures a reader would credit to the fill stage, a delivery floor, spend control, and
  provider attribution, are one register row short of existing.
- **Recommendation**: in §3.4, mark the fill-rate floor the way the sibling check is marked ("a
  script over a skeleton in hand; pipeline carriage is open work, `UW-C307`"). In §3.3, separate
  "metered" from "budgeted" and say the second does not exist. In §4.1, add one clause noting that
  production runs an unpinned cascade, so the comparison's conditions are not the serving
  conditions. All three are one sentence each and none weakens the document's argument.
- **How to check I'm right**: read `UW-C307`'s and `UW-C315`'s status text next to §3.4's sentence;
  `grep -rn "fill_rate" src/` and `grep -n "provider_order" src/cyo_adventure/generation/provider.py`.

---

## Cross-cutting note on the brief's largest-book figure

The brief (§1, §3.1) describes "a 677-node, ~118,000-word graph at 16+". Measured against the
committed catalog, `skeletons/16+/the-tenfold-siege.json` has 677 nodes commissioning **42,233**
words, and the largest book by commissioned words is `the-last-cartage` at **49,953**. The 118,000
figure traces to `cyo-framework-problem-and-structures-2026-08-10.md:56-57`, which multiplied 677
nodes by a band *prose* word target, but that skeleton is `narrative_style: gamebook` with 209
endings, averaging 62 words per node, and gamebook targets are less than half prose targets. The
catalog has also grown since (84 non-sidecar skeletons, 15,470 nodes, 1,426,348 commissioned words,
against the quoted 61 and 11,458). Not a fill-stage defect, but the largest-book figure is quoted in
cost and feasibility arguments and is 2.4x high, wrong in the reassuring direction, since it makes
every derived per-book cost bound look conservative when it is not.
