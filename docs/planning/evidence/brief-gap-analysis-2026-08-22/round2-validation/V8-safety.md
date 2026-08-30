# V8. Adversarial validation: safety, moderation, and the human approval gate

Validator posture: attack each claim first, confirm only what survives. Where a question
could not be settled at source, it is marked **unsettled**, not dismissed. Every citation is
`path:line` against the working tree at 2026-08-22.

---

## Claim 2 (C4-2 / B2-3): a bright-line BLOCK is reversible; approve never reads `has_hard_block`

> **Correction, 2026-08-30: the two-clicks escape this section confirmed is CLOSED.** Everything
> below is left as the 2026-08-22 record; do not read it as the state of `main`. What changed, all
> verified against `origin/main` on 2026-08-30:
>
> - `approve()` no longer has "the only content-derived guard". `_assert_report_permits_approval`
>   (`publishing/service.py:356` onward) stacks four refusals: `approve_without_moderation`
>   (`:409`), `approve_with_unusable_moderation` (`:422`), `approve_with_incomplete_coverage`
>   (`:444`), and `approve_requires_override_reason` (`:474`). The last is **gate D2 of the ADR-005
>   amendment of 2026-08-25**: an approval over a block or high-severity finding is refused unless
>   the caller supplies a non-whitespace `override_reason`.
> - The frontend row of the refutation table is superseded. `frontend/src/admin/ReviewDetailPage.tsx`
>   now disables Approve while `needsOverride && overrideReason.trim().length < 10`
>   (`:1027-1030`), and renders the `approve_requires_override_reason` rule when the server refuses.
>   The `Hard block` badge is no longer decoration.
> - The audit row is no longer indistinguishable: `events/writer.py`'s `RELEASED` allowlist is
>   `{"visibility", "overridden_block_count", "overridden_high_count"}`.
> - **Unchanged and still true:** the `has_hard_block` symbol is still read only inside
>   `moderation/`; there is still no DB constraint; `submit()` (`service.py:161`) still guards only
>   `moderation_report is None`; `state_machine.py` is still report-blind; and
>   `catalog_publish.py` still reaches `approve()`, which is now why it inherits the fix rather than
>   the hole. The guard is expressed through `severe_finding_counts()`, so the symbol grep this
>   section used as its oracle would still return zero hits in `publishing/` today.

**Verdict as recorded on 2026-08-22: CONFIRMED, and the prior finding UNDERSTATES it.** The escape is shorter and
cheaper than "3 clicks via an API-only submit"; the shortest path is **two clicks in the
shipped admin console**, no scripting.

### Attempted refutations, all of which failed

| Layer I attacked | Result |
|---|---|
| `publishing/state_machine.py` | `LEGAL_TRANSITIONS` (lines 78-88) is a pure `(Status, Action) -> Status` table. It has no access to the report and no hard-block-aware hop. Nothing to refute with. |
| `publishing/service.py::approve` | The only content-derived guard is `if version_row.moderation_report is None` (`service.py:412`), i.e. "was it screened", never "what did it say". `submit` has the identical shape at `service.py:148`. |
| `api/approval.py::approve_storybook` | Raises only on `publish_without_approver` (`approval.py:166-168`), a self-check on its own write. No report read. |
| DB constraint | `grep -rn hard_block supabase/migrations/` returns **nothing** across all migrations (63 when written; re-run against `origin/main` 2026-08-30 over 67 migrations, still nothing). No CHECK, no trigger. |
| Frontend | `frontend/src/admin/ReviewDetailPage.tsx:362` renders a red `Hard block` badge, so the signal is *displayed*. But Approve is gated only on `disabled={surface.status !== 'in_review'}` (lines 711, 720). The badge is decoration; it does not gate. |
| `publishing/catalog_publish.py` | Calls `approve()` rather than writing the column, so it inherits the same hole rather than closing it. |
| Any other reader of the flag | `has_hard_block` is read at exactly 8 sites, **all inside `moderation/`** (`report.py:189,200,207,229`; `pipeline.py:423,447,695,849,943,996,1008`). Zero reads in `publishing/`, `api/`, `db/`, or `frontend/`. |

**No guard exists anywhere in the stack.** The claim stands.

### The exact publishable sequence (shortest form)

The prior finding's route (`needs_revision -> POST /submit -> POST /approve`) is real but
requires a raw API call: the admin console exposes no Submit button (`grep` over
`frontend/src/admin/*.tsx` finds approve/sendback/archive/rescreen only). There is a
strictly better attack that never leaves the UI:

1. A story is routed to `in_review` by the pipeline (clean or soft-flagged):
   `moderation/pipeline.py:447` calls `service.submit`.
2. An admin edits one passage. `api/node_edit.py:126` allows edits in `in_review`.
   The edit re-runs Stage-0 classifiers and Stage-1 safety on the edited node
   (`node_edit.py:645-663`).
3. A fresh **BLOCK** is merged into the persisted report (`node_edit.py:674`) and the story
   **stays `in_review`**. This is not incidental, it is a deliberate, commented decision
   (`node_edit.py:664-671`: *"a moderation hard block does NOT reject the write. ADR-005:
   the human reviewer is the final gate… approve() does not itself check has_hard_block
   either"*) and it is **locked in by a passing test**:
   `tests/unit/test_node_edit.py:846 test_moderation_block_persists_and_does_not_reject`,
   which asserts `version_row.moderation_report["summary"]["hard_block"] is True` and
   `story.status == "in_review"`.
4. Admin clicks **Approve** -> Confirm. `service.approve` sees a non-None report and
   publishes.

**Two clicks, in the shipped console, on a book whose persisted report says
`summary.hard_block: true`.** The book is then `published`, assignable, and cacheable
offline.

### The one genuine mitigating fact, and why it does not rescue the design

This is a **documented design position, not an oversight**. ADR-005's success criterion is
*"adversarial briefs are flagged and cannot be **auto**-publish[ed]"*
(`docs/planning/adr/adr-005-mandatory-human-approval.md:167-172`), a claim about the
machine never publishing on its own, which does hold. Nothing in ADR-005 ever claimed a
human cannot publish over a block, and `moderation/pipeline.py:443-447` explicitly forbids
the pipeline from calling approve in either direction.

That defence fails on three counts:

1. **The name lies.** "Bright-line" and "hard block" name a category the system treats as
   absolute: `_OPENAI_BRIGHTLINE` includes `sexual/minors` and `self-harm/instructions`
   (`moderation/classifiers.py:183-193`). No product should let two clicks publish a book
   the machine has labelled `sexual/minors` to a child's library.
2. **The override leaves no distinguishable trace.** `record_event(...EventType.RELEASED)`
   (`service.py:~478`) writes the same row for a clean approval and a block-override. There
   is no field, no reason code, no second signature. An auditor cannot query "which
   published books were released over a hard block" without re-parsing every JSONB report.
3. **`approve()` re-derives the version itself.** `api/approval.py:153` calls
   `_latest_version(...)`; `ApproveBody` (`api/schemas.py:1797-1804`) carries only
   `visibility`. Combined with in-place blob mutation in `node_edit` (no version bump), the
   admin approves *whatever the latest version now is*, not the bytes they read.
4. **A dual-role adult self-approves.** `service.approve` requires `principal.is_admin`
   (`service.py:~377`) but `principal.acting_role(storybook.family_id)` stamps `guardian`
   for own-family review, the "owner-as-admin exception" the code names at
   `service.py:~470`. The four-eyes property is a convention, not an invariant.

**Severity: critical. Highest-priority item in this cluster.**

---

## Claim 1 (C4-1): safety is per-node; path-level and cumulative harm invisible

**Verdict: CONFIRMED at source, but it is a KNOWN AND DOCUMENTED accepted limitation, not
an undiscovered defect. The prior finding's framing needs correction; its severity does not.**

### Confirmed at source

- The batch safety prompt says verbatim *"Judge each passage independently of the others"*
  (`moderation/stages.py:110`).
- Nodes reach the stage as an **unordered flat list of `(id, text)` pairs**
  (`pipeline.py:~965`: `nodes = [(node.id, strip_sentinels(node.body)) for node in story.nodes]`).
  No edges, no choice targets, no path context is ever sent.
- Stages 3 and 4 *do* receive all nodes (`stages.py:125` coherence, `stages.py:143`
  engagement), but coherence judges *consistency* not safety and returns `flag|pass`;
  engagement returns `advisory|pass` and is explicitly *"an advisory review only, not a
  gate."* Neither can emit BLOCK.
- `covering_paths` / `reader_sample_paths` (`validator/paths.py:395`, `:478`) have **zero
  production callers**. The only non-test caller is `scripts/measure_per_path.py:312`, an
  offline measurement script. `validator/gate.py::run_gate` never takes a path set.

### Does moderation operate on whole-book text? (the question that decides severity)

**Partly, and it does not help.** Stage 1 batches `review_batch_size` nodes per call
(default **8**, `core/config.py:657`), so up to 8 node bodies share a prompt. That is
incidental co-location, not path awareness: chunks are cut in `story.nodes` iteration order,
not along choice paths, so a 5-node arc split across a chunk boundary is unaccumulated
exactly as at batch size 1, and the prompt still demands an independent verdict per node.
**Severity is not reduced by batching.**

### The concrete escape (constructed, then checked against the pipeline)

A 5-8 band book. Each node is individually gate-clean against every check that exists:

| Node | Body (individually benign) | Why every existing check passes it |
|---|---|---|
| `n_meet` | A kind grown-up at the park says the protagonist seems lonely and offers to be their special friend. | OpenAI: nothing flagged. Perspective: TOXICITY/THREAT near floor. Stage 1: warm, band-appropriate, `safe`. |
| `n_secret` | "This will be our special secret, grown-ups spoil surprises." Choice: *Keep the secret* / *Tell Mum*. | Secrets-and-surprises is stock 5-8 material. No classifier category matches. No concern slug in `_CONTENT_CONCERNS` fits. |
| `n_gift` | The friend gives a present and asks them not to mention it at home. | Gift-giving. Clean. |
| `n_alone` | They arrange to meet where no one else goes, because it is quieter there. | "Quiet place" is a positive frame in children's prose. Clean. |
| `e_best_friend` | Ending: *"You had the best friend in the whole world, and nobody else ever knew."* `valence: positive`, `kind: friendship`. | PL-15/PL-18 check forbidden ending **kinds**, not the semantics of the reward. `content_flags` record what happens *to* a character; nothing bad happens. |

The assembled path `n_meet -> n_secret -> n_gift -> n_alone -> e_best_friend` is a textbook
grooming escalation, isolation, secrecy, gifts, private meeting, secrecy rewarded as the
good ending.

> **Scope, 2026-08-30. This is a hypothetical threat model, not an executed test.** The paragraph
> below read "Every automated stage in this repository passes it. I traced each stage individually
> and found no exception", which reads as a run result. It is not one: the five nodes above exist
> only in this document, no fixture carries them, and no command or run record is committed that
> would let a reader reproduce the verdict. What was actually done is a **paper trace against the
> committed code and policy tables**, stage by stage, asking of each whether any rule it enforces
> could match. That trace is checkable, because every rule it reasons about is committed
> (`_OPENAI_BRIGHTLINE`, `_CONTENT_CONCERNS`, the PL-15/PL-18 ending kinds, `validator/imitable.py`'s
> caller count), and it is worth acting on. It is not evidence that a generated book carrying this
> arc has ever been passed by the pipeline. **To promote this from threat model to finding**, add
> the five nodes as a committed adversarial fixture and run the real gate over the assembled path,
> recording the verdict. Until then, read every "passes" below as "no committed rule matches", which
> is the claim the trace supports.

Read that way, no automated stage in this repository rejects it, stage by stage:

- Stage 0 classifiers: no `_OPENAI_BRIGHTLINE` category matches; Perspective
  `SEXUALLY_EXPLICIT` is nowhere near 0.8.
- Stage 1 safety: per-node, per the prompt; each node is safe for 5-8 in isolation.
- Stage 3 coherence: the arc is *perfectly coherent*, which is the point, coherence
  actively **rewards** a well-constructed grooming arc.
- `validator/` L1/L2/PL: topology-valid, in-band, positive ending.
- `validator/imitable.py`: dead code (no callers, below).
- The threshold policy is a display filter, not a gate.

The only control is a human reading the assembled path. Which brings the third leg:

### Why the compensating control does not hold

`adversarial-safety-evaluation.md:182` names the control precisely: *"Only the human
approver reading the whole story (ADR-005) stands between this and a child."* But the review
surface renders a **DFS read-through where each node appears exactly once**
(`frontend/src/guardian/storyReadThrough.ts:175-210`). A reader walking a DFS listing does
not experience the sequence `n_meet -> n_secret -> n_gift -> n_alone -> e_best_friend` as a
path, the DFS may interleave sibling branches between them. The compensating control is
not merely expensive (C4's measured 3-8 h at ceiling scale); **it is the wrong presentation
for the class of harm it is the sole control for.** That is the sharpest form of this
finding and neither the prior review nor the safety doc states it.

### Tracking status: DOCUMENTED, ACCEPTED, DATED

`docs/planning/safety/adversarial-safety-evaluation.md` has this as **Class C (aggregate
harm)** and **Finding 4 [Important]**, with an acceptance-threshold row reading *"N/A (known
gap): Documented limitation; the human approver is the control, so this class is not gated
automatically."* It even anticipates the batching objection and rejects it correctly. Its
own recommendation is the one worth quoting back: *"At minimum the guardian console should
present the full playthrough, not only flagged passages."*

**Severity: critical (unchanged). Correction to framing: this is not an oversight; it is a
documented accepted risk whose stated compensating control is unexercisable as built.**

---

## Claim 3 (C4-3): review surface dumps all nodes DFS, no sampling, no path view, no risk ranking; Approve carries no version and no attestation

**Verdict: PARTIALLY REFUTED, one sub-claim is wrong, the rest confirmed.**

| Sub-claim | Verdict | Evidence |
|---|---|---|
| All nodes in DFS order | **Confirmed** | `storyReadThrough.ts:175-210`, explicit DFS from `start_node`, `visited` set, each node once; unreachable nodes appended last. |
| No sampling | **Confirmed** | No sampler anywhere on the review path; `reader_sample_paths` unused. |
| No path view | **Confirmed** | A node reachable by three paths renders once, in whichever branch DFS hit first. |
| **No risk ranking** | **REFUTED** | `api/review_surface.py:226-266`: `_ranking_key` is `(verdict desc, severity desc, node-count desc)` with a stable tiebreak, and `_rank_and_split` splits structural / low-advisory / primary. **Findings are ranked.** The surface also leads with `flagged_passages` (prose joined to findings) before the read-through (`ReviewDetailPage.tsx:70-71, 453-486`). |
| Approve carries no version | **Confirmed** | `ApproveBody` (`api/schemas.py:1797-1804`) holds only `visibility`; `api/approval.py:153` re-derives `_latest_version` server-side. `node_edit` mutates `version_row.blob` in place without a version bump, so the reviewed bytes and the published bytes are not pinned to each other. |
| No attestation | **Confirmed** | No "I read the whole story" affirmation, no coverage assertion, no time-on-page signal, nothing recorded on the `RELEASED` event beyond `visibility`. |

Be precise about what this means: the surface is **flags-first and finding-ranked**, which
is good design for per-node defects and exactly the wrong design for Class-C path harm, it
optimises the reviewer's attention toward the nodes the machine already caught, which are by
construction not the nodes involved in an escape that no stage flags.

---

## Claim 4 (C4-4/5/8): gating taxonomy is adult moderation; six categories uncovered; ADVISORY never gates; SAFE-14 a stub; `imitable.py` has no callers

**Verdict: MOSTLY CONFIRMED, with two corrections. The prior review understated existing
coverage in two categories and overstated it in none.**

### What actually gates (the ground truth)

Only two verdict values gate. `report.has_hard_block` counts `BLOCK`; `has_soft_flag` counts
`FLAG` (`moderation/report.py:189-202`). **`ADVISORY` is structurally incapable of gating**,
confirmed, this is not a policy choice but a property of the two properties that drive
routing.

**Stage 0 BLOCK vocabulary is exactly 8 signals:**
- `_OPENAI_BRIGHTLINE` (`classifiers.py:183-193`), and only when OpenAI's own boolean
  `flagged` is true: `sexual`, `sexual/minors`, `self-harm/instructions`,
  `self-harm/intent`, `illicit/violent`, `hate/threatening`, `harassment/threatening`.
- Perspective `SEXUALLY_EXPLICIT >= 0.8` (`classifiers.py:698`).

**Everything else from both providers is ADVISORY** (`classifiers.py:487-497`, `:704-706`),
so `violence`, `violence/graphic`, `harassment`, `hate`, `illicit`, base `self-harm`,
`TOXICITY`, `SEVERE_TOXICITY`, `THREAT`, `PROFANITY`, `IDENTITY_ATTACK`, `INSULT` are all
recorded and all non-gating.

**Stage 1 BLOCK rubric** (`stages.py:87-92`): sexual content, self-harm instructions,
real-world danger modeled as achievable, cruelty rewarded as the good outcome.
**FLAG:** "too mature for the band". Concern slugs (`stages.py:66-77`):
`real_world_danger, too_mature, frightening_content, cruelty, sexual_content, self_harm,
profanity, other`.

### Fair coverage table for the six claimed gaps

| Claimed gap | Verdict | Precisely what exists |
|---|---|---|
| **Violence intensity** | **Partially covered** (prior review understated) | OpenAI `violence` / `violence/graphic` are *recorded* with severity bands (`_severity_from_score`) but ADVISORY-only. Stage 1 has `frightening_content` + `too_mature` FLAG slugs, which do gate to human review. What is absent is a **band-calibrated intensity scale**, nothing distinguishes 5-8-appropriate peril from 13-16 peril except one model's holistic judgment. |
| **Bullying** | **Partially covered** (prior review understated) | Perspective `INSULT`, `TOXICITY`, `IDENTITY_ATTACK` recorded (advisory). Stage 1's `cruelty` concern exists, and *"cruelty rewarded as the good outcome"* is an explicit BLOCK criterion. Genuinely uncovered: sustained, non-toxic-language social exclusion, and any per-band bullying threshold. |
| **Substance use** | **Effectively uncovered** | OpenAI `illicit` covers drug-related wrongdoing but is **not** in `_OPENAI_BRIGHTLINE` -> advisory. No concern slug; would degrade to `other` or `too_mature`. Nothing gates. |
| **Stereotyping** | **Partially covered, weakest half missing** | `hate/threatening` gates; `hate` and `IDENTITY_ATTACK` are advisory. Benign-but-corrosive stereotyping (gendered competence, ethnic role assignment, disability-as-tragedy) has no category anywhere in the taxonomy. |
| **Grooming** | **Uncovered, twice over** | No category in `_OPENAI_BRIGHTLINE`, `PERSPECTIVE_ATTRIBUTES`, or `_CONTENT_CONCERNS`. And structurally invisible per Claim 1: it is a *path* property. |
| **Imitable instruction** | **Partially covered by prose rubric, dedicated instrument is dead code** | Stage 1's *"real-world danger modeled as achievable"* is a per-node BLOCK criterion, so a single explicitly-instructional node does gate. `validator/imitable.py::screen_for_review` has **zero callers in `src/`** (only `tests/unit/test_imitable.py:17`); the judged `imitable_practice` criterion it exists to route to is unbuilt. |
| **Cover imagery** | See Claim 9. | - |

### SAFE-14

**Confirmed stub.** `validator/safety.py` returns an empty report; `gate.py:212-220` computes
`safety_flagged` honestly over a vocabulary nothing emits, so it is a constant `False`. It
occupies step 9 of the documented rule application order (`gate.py:33`), which is how it came
to be cited as safety evidence.

### Tracking status: PARTIALLY TRACKED

- SAFE-14 stub: **tracked**, `UW-C115`, `UW-C157`, and `UW-C290` (whose REMOVE item is
  "SAFE-14's entry in the live application order while `validator/safety.py` is a stub"; that
  row is marked **done**, so SAFE-14's *misreporting* is closed while the *stub* is not).
- `imitable.py`: **tracked in detail**, `UW-C264` (`AL-397`/`AL-405`) records the exact
  class, the measured incidence (13/167 young-band endings), and states plainly that *"the
  judged `imitable_practice` criterion remains unbuilt."* The dead code is a deliberate
  half-landing, not an oversight.
- Violence intensity / bullying / substance use / stereotyping / grooming as *taxonomy
  gaps*: **no UW row found.** These are untracked.

---

## Claim 5 (C4-9): repair identity check is id+tier+node-count only, so a repair can rewire the graph; neither skeleton fidelity nor the fill-rate floor re-runs

**Verdict: SPLIT, the identity-check description is accurate but the "can rewire the graph"
conclusion is REFUTED for topology; the fidelity half is CONFIRMED.**

### Refuted: an arbitrary rewire does not survive adoption

`_repair_preserves_identity` (`pipeline.py:711-741`) is indeed only `id` + `metadata.tier` +
`len(nodes)`, accurate. But it is **not the only adoption gate**. `_repair_is_adoptable`
(`pipeline.py:744-833`) runs three checks and any one rejects:

1. `run_gate(revised, context="fill_result")`, the **full deterministic validation gate**,
   L1 topology, L2 state-space walk, PL policy, and PL-27 fill-residue
   (`pipeline.py:801`). A repair that orphans a node, breaks reachability, dangles a choice
   target, introduces a forbidden ending kind, or leaves a `<<FILL` directive is discarded.
2. `_repair_preserves_identity`.
3. `check_sentinel_integrity_at_rest`, rejects a dropped, mutated, forged, or relocated
   personalization sentinel (`pipeline.py:812`).

So "a repair can rewire the graph" is **too strong**. What survives is narrower and still
real: **a repair may re-point choice targets to a different but still-valid topology.** Keep
`id`, `tier`, and node count; keep the graph connected, acyclic, every ending reachable, all
policy bounds met, and re-route which choice leads where. Every check listed passes. The
consequence is that the *set of paths* changes while the prose is unchanged, so a
human-reviewed path structure can be silently replaced. Note the compounding effect with
Claim 1: since nothing evaluates paths, a path-structure change is doubly invisible.

Also note the repair fires only when `has_soft_flag and not has_hard_block`
(`pipeline.py:422-425`), and never on published content (`allow_repair=False`,
`pipeline.py:404-419`, well-reasoned and correctly enforced).

### Confirmed: skeleton fidelity does not re-run

`run_stage1_gate` (`generation/fidelity_gate.py:28`), which composes deterministic fidelity
with `run_semantic_fidelity_check`, is called from exactly two sites,
`generation/orchestrator.py:45` and `generation/import_story.py:32`. **It is not called from
`moderation/pipeline.py`.** `run_gate` takes no skeleton argument and cannot perform this
check. So a repaired blob's faithfulness to the commissioned skeleton (beat coverage,
choice-label intent) is never re-proven. **Confirmed.**

### Correction on "fill-rate floor"

There is no artefact named a fill-rate floor (`grep` for `fill_rate|FILL_RATE|fill_floor`
returns nothing). The nearest real check, **PL-27 fill-residue**, *does* re-run, because
adoption passes `context="fill_result"` (`pipeline.py:801`, and `gate.py:15-22` documents
that PL-27 only fires under that posture). This sub-claim is **refuted**; the code comment
at `pipeline.py:799-800` even cites the lesson (`AL-325`) that motivated it.

**Net severity: moderate, down from the prior finding. The graph-rewire risk is narrow but
real; the fidelity gap is confirmed and unmitigated.**

---

## Claim 6 (C4-10): review model is an unallowlisted free string, never persisted, pinned to no dated id

**Verdict: CONFIRMED on all four points.**

- **Unallowlisted.** `AuthoringPlanRequest.review_stage1_model` / `review_stage2_model` are
  bare `str | None` (`api/schemas.py:1239-1240`), no `StringConstraints`, no `min_length`,
  no charset, in a model whose sibling fields all carry constraints.
  `story_requests/authoring_plan.py:273` calls `is_enabled_allowlist_pair` for
  `plan.provider`/`plan.model` **only**; the two review-model fields flow straight into the
  provenance dict at `authoring_plan.py:625-626`.
- **Not persisted with the verdict.** `ModerationReport.to_dict()`
  (`moderation/report.py:208-233`) writes `findings`, `aggregate`, and a `summary` of
  `count / hard_block / soft_flag / repaired / reviewer_independent`. **No model id, no
  provider, no prompt version.** A recorded safety verdict is not attributable to the model
  that made it.
- **No dated pin.** `core/config.py:612-613`: `review_openrouter_model =
  "anthropic/claude-sonnet-4.6"`, `review_ollama_model = "qwen2.5:14b"`. Floating aliases;
  a silent upstream rotation changes the safety gate with no signal.
- **Independence is a string comparison.** `review_provider.py:134`:
  `independent = backend != generator_provider or review_model != generator_model`. Two
  aliases resolving to the same weights read as independent.

The one credit due: `reviewer_independent` **is** persisted in the summary, so the
independence *conclusion* is recorded even though its inputs are not.

**Severity: high. This is the cheapest item in the whole cluster to fix and it undermines
every other safety claim's evidentiary value, you cannot re-run a verdict you cannot
reproduce.**

---

## Claim 7 (C4-11): the threshold flywheel raises `min_verdict` after 5 books at 80% override, converting an over-approving admin into hidden findings

**Verdict: SUBSTANTIALLY REFUTED. The mechanism is real; three of the claim's load-bearing
assumptions are wrong.**

| Claim component | Verdict |
|---|---|
| Gates are 5 decided versions / 0.8 override rate | **Confirmed**: `insights.py:34-35`. |
| It "raises `min_verdict`" | **Refuted, it *suggests*.** `suggest_thresholds` (`insights.py:326-369`) is pure and returns proposals. Its only consumer is `GET /admin/moderation/suggestions` (`api/moderation_dashboard.py:119-136`), whose module docstring reads *"Read-only."* Applying a threshold requires a separate deliberate admin write via `api/moderation_thresholds.py`. **Nothing auto-applies.** |
| It "converts findings into hidden findings" | **Refuted for the reviewer.** `moderation/thresholds.py:1-8`: *"decides which recorded findings SURFACE on guardian- and kid-facing responses… **Admin surfaces never filter.**"* The admin review path uses an independent, opt-in `admin_noise_floor` with a hard guarantee that FLAG/BLOCK/unscored always surface (`api/review_surface.py:118-126`). Findings are hidden from **families**, never from the approving admin. |
| Thresholds affect gating | **Refuted.** `surfaces()` is consumed only by display paths: `api/story_requests.py:204`, `api/assignments.py:536`, `moderation/rescreen.py:216`. It is never consulted in `pipeline.py` routing. |
| Findings are destroyed | **Refuted.** Every finding stays in the persisted JSONB regardless of threshold. |

### What genuinely survives

A narrower, real self-referential loop: `approve` is admin-gated, so the same population
that generates the `released_versions` numerator can act on the suggestion derived from it.
An admin releasing everything drives `override_rate -> 1.0`, producing a proposal to raise
the guardian-facing bar for that `(band, category)`. Accepting it reduces what *guardians*
see, weakening the second pair of eyes. Real, but one manual step, family-facing only, and
findings are never lost.

Note the codebase already caught and defended a *worse* version of this: `insights.py:51-59`
documents 5,048 legacy fail-safe rows that were *"one released book away from a manufactured
FLAG->BLOCK suggestion"*, and the fix (excluding `structural` findings from `override_rate`)
is in place. That is a maintainer already reasoning correctly about exactly this hazard.

**Severity: downgrade from critical to low-moderate. Recommend re-writing this finding
rather than dropping it.**

---

## Claim 8 (C4-15): rescreen skips the LLM safety stage; a fresh BLOCK on a published book leaves it published, assigned, and offline-cached with no alert

**Verdict: CONFIRMED on the mechanism; "with no alert" needs correction; the whole thing is
a documented deliberate decision.**

- **Skips LLM stages: confirmed and deliberate.** `moderation/rescreen.py:12-19`, re-runs
  `run_gate` and Stage-0 classifiers **only**, never `moderation.stages`. Stated rationale:
  the LLM stages judge prose quality, which a band-policy or classifier-threshold edit does
  not change. Defensible for the sweep's stated trigger; it does mean a *review-model*
  improvement can never be applied retroactively to the published catalog.
- **A fresh BLOCK does not unpublish: confirmed and deliberate.** `rescreen.py:29-41` is an
  explicit `#CRITICAL: security` decision citing ADR-005 in both directions, *"a sweep that
  silently archived or hid a book a guardian's child might be mid-story on would be exactly
  the unreviewed, machine-driven content decision ADR-005 exists to prevent."*
  `LEGAL_TRANSITIONS` has no machine-reachable exit from `published`; the only exit is the
  human `archive`. Test-locked: `test_flagged_book_is_not_archived`.
- **Result is not written back to `moderation_report`: confirmed and deliberate**
  (`rescreen.py:44-55`), that column is the historical record of the pass that gated the
  original transitions.
- **"No alert": PARTIALLY REFUTED.** A `pipeline_event` row is written and the verdict
  appears in `RescreenSummary` for the admin who triggered the sweep. What is *absent* is a
  **push**: no notification kind in `notifications/registry.py` corresponds to a rescreen
  block (the vocabulary is `story_ready`, `story_archived`, `request_blocked`,
  `kid_flagged`, `generation_failed`, …). A block found by a sweep nobody re-reads is
  effectively silent.
- **Offline cache: confirmed unchanged**, because status is unchanged (see recall below).

**Severity: high, not because any single decision is wrong, but because the composition of
four individually-defensible decisions is that the system can *know* a published book is
bright-line unsafe and take no action, notify no one asynchronously, and leave it on
children's devices. That composite is nowhere stated as an accepted risk.**

---

## Claim 9 (C4-7): no image-safety classifier for cover art

**Verdict: CONFIRMED literally, but SUBSTANTIALLY MITIGATED. The prior finding omits two
real controls; severity should drop.**

- **No classifier: confirmed, and explicitly acknowledged in code.**
  `covers/service.py:207-218` carries a `#CRITICAL: security` marker: *"An automated
  image-safety classifier (the moderation/ analogue of the story-text gate) does NOT exist
  in this codebase yet and is deliberately out of scope."* It even names its own retirement
  condition. That is exemplary documentation of a gap.
- **Provider-side filtering DOES exist** (the check requested): `covers/provider.py:30-31`,
  *"a safety refusal returns empty candidates."* Gemini applies server-side safety filtering
  and a refusal raises `CoverGenerationError`, marking the job failed. **Caveat and a real
  finding of my own: no `SafetySettings` are passed** on the `generate_content` call
  (`covers/provider.py:36-43` sets only `response_modalities` and `image_config`), so the
  project relies on whatever the provider's default thresholds happen to be, unpinned and
  unversioned, with no record of what filter ran.
- **Prompt-side guardrails exist:** `covers/prompt.py:10-19` scales an art-safety clause by
  content flags, and `prompt.py:111-114` marks the safety rules non-overridable.
- **Human approval is mandatory and structurally enforced:** the H2 fix stops generation at
  `cover_status="pending_review"`; `covers.service.approve_cover` is the sole path to
  `ready`, and every read path that can emit a cover URL gates on `ready`
  (`api/library.py`, `api/recommendations.py`, `api/covers.py`). Storage is additionally
  salted and the bucket private (`covers/storage.py`), after a recorded 2026-07-28 incident
  (`UW-M07`).

So an unsafe cover must pass the provider's own filter, the prompt guardrails, **and** a
human, before it can reach a child. The gap is genuine, one human gate and no second
independent automated layer, versus text's validator + moderation + approval, but it is
not "no control."

**Severity: downgrade from high to moderate. Add the unpinned-`SafetySettings` sub-finding,
which is new and cheap to fix.**

---

# Recommendation review

## R1: Make approval refuse a hard-blocked book

### Where the check must live

**`publishing/service.py::approve`, immediately after the existing
`moderation_report is None` check at line 412.** This is not a preference; it is forced by
the module's own structure:

> **Note, 2026-08-30.** This recommendation was taken, at the location argued for here: the guard
> now lives in `_assert_report_permits_approval`, called by `approve()`, so both privileged callers
> are covered structurally. See the correction under Claim 2 above for the four refusals as
> shipped.

- It is **the sole path in `src/` that sets `status="published"`** (`service.py:6-12`), and
  `catalog_publish.py` reaches it by calling `approve()` rather than writing the column. A
  check here therefore covers both privileged callers structurally, exactly the argument the
  file already makes for the `is_admin` and `moderation_report is None` re-checks.
- The API layer is wrong: `api/approval.py` is one of two callers, and the file's own
  history (Findings 1-2 in the adversarial doc) is a record of what happens when a control
  lives at one route instead of the choke point.
- The state machine is wrong: it is deliberately dependency-free and has no access to a
  version row. Threading a report into it would destroy its one virtue.
- A DB constraint is wrong as the *primary* control (the JSONB shape is a moving target and a
  CHECK over `moderation_report->'summary'->>'hard_block'` would fire on legacy rows written
  before the summary key existed), but see the backstop below.

The signal is already free: `to_dict()` persists `summary.hard_block`
(`report.py:229`), so the check is a plain read with no re-derivation:

```python
# #CRITICAL: security: a bright-line BLOCK must not be publishable by a single
# admin action. ADR-005 makes the human the final gate; it does not make the
# human able to silently overrule the machine's bright lines. Publishing over a
# hard block requires an explicit, recorded, second-person override.
# #VERIFY: test_approve_refuses_hard_blocked_version.
summary = (version_row.moderation_report or {}).get("summary")
if isinstance(summary, dict) and summary.get("hard_block") is True:
    if override is None:
        msg = "cannot approve a version carrying a moderation hard block"
        raise BusinessLogicError(msg, rule="approve_over_hard_block")
    _assert_override_valid(principal, override, version_row)
```

Two structural notes that matter more than the snippet:

1. **Fail closed on a malformed report.** A report whose `summary` is missing or not a dict
   must be treated as *unknown*, and unknown must not publish. Do not write
   `summary.get("hard_block", False)`, that publishes a corrupt row. Derive the answer from
   `findings` as a fallback (`any(f["verdict"] == "block")`) and refuse if neither is
   readable.
2. **Mirror it in `submit`.** `submit` (line 148) currently lets a hard-blocked
   `needs_revision` book re-enter `in_review`, which is what makes the queue lie about what
   is awaiting review. Refusing there too kills the API-only route from the prior finding at
   its source.

### Is there a legitimate override, and how is it recorded?

**Yes, and denying it would be wrong.** Two real cases: (a) a **false positive**, Perspective
`SEXUALLY_EXPLICIT` scored 0.397 on *clean* children's prose in this project's own Stage-0
baseline (`classifiers.py:60-64`), higher than its adversarial maximum of 0.161, so bright-line
false positives are measured, not hypothetical; (b) a **classifier outage or model swap**
producing a spurious block on a book already reviewed. A system with no override invites the
worse workaround of disabling the classifier.

Design the override so it is expensive, attributable, and queryable:

- **A distinct action, not a flag on approve.** `ApproveBody` grows
  `hard_block_override: HardBlockOverride | None`, requiring `acknowledged_finding_ids:
  list[str]` (the specific blocks being overridden, a blanket override is refused; a new
  block appearing after the acknowledgement invalidates it) and `justification: str` with a
  real minimum length.
- **Four eyes, enforced.** The overriding admin must not be the acting persona for that
  family. `principal.acting_role(storybook.family_id)` already computes exactly this
  distinction (`service.py:~470`); require it to return `admin`, not `guardian`. This closes
  the dual-role self-approve leg of Claim 2 for the highest-risk case without disturbing
  ordinary own-family approvals.
- **Its own event type.** `EventType.RELEASED_OVER_HARD_BLOCK`, carrying the finding
  categories (closed vocabulary only: `record_event`'s payload allowlist already forbids
  free text and node ids, and that restriction must be honoured; the justification goes to a
  dedicated column, not the event payload). This makes "which books were published over a
  block" a one-line query instead of a JSONB archaeology exercise.
- **A DB backstop, additively.** A nullable `storybook_version.hard_block_override_id` FK
  plus a deferred CHECK asserting that a published version whose report summary says
  `hard_block` has a non-null override id. Add it *after* backfilling, so legacy rows do not
  trip it. This is the layer that survives a future caller bypassing the service.

### Tests this needs

| Test | Level | Asserts |
|---|---|---|
| `test_approve_refuses_hard_blocked_version` | unit | `BusinessLogicError(rule="approve_over_hard_block")`; status unchanged; no `RELEASED` event written |
| `test_submit_refuses_hard_blocked_version` | unit | the `needs_revision -> in_review` route is closed |
| `test_approve_refuses_when_summary_missing_but_findings_block` | unit | fail-closed on a legacy/partial report |
| `test_approve_refuses_when_report_shape_unreadable` | unit | fail-closed on corruption, not fail-open |
| `test_node_edit_block_then_approve_is_refused` | integration | **the exact 2-click sequence from Claim 2**; this is the regression test that matters |
| `test_override_requires_acknowledged_finding_ids` | unit | blanket override rejected |
| `test_override_invalidated_by_new_block_after_acknowledgement` | unit | TOCTOU on the acknowledgement |
| `test_override_refused_for_own_family_persona` | integration | four-eyes |
| `test_override_writes_released_over_hard_block_event` | integration | exactly one event, PII-free payload |
| `test_catalog_publish_inherits_hard_block_refusal` | unit | the second caller |
| `test_no_publish_over_hard_block` (extend existing `test_no_publish_without_approver`) | integration | drives every endpoint path |
| property test over `moderation_report` shapes | hypothesis | no shape yields publish-without-override |

Also: audit the four offline seed sites the module docstring names (`scripts/seed_staging.py`,
`seed_dev_data.py` ×2, `seed_series_catalog.py`), they write `status="published"` directly and
will bypass this exactly as they bypass the approver invariant today.

---

## R2: Wire path-level evaluation using `covering_paths`

### Is full enumeration intractable? Yes. Is `covering_paths` the right sample? **Yes, and it is far cheaper than assumed.**

I measured this rather than estimating it. Running `covering_paths` over the committed
catalog (`uv run python` against `validator/paths.py`, no cap changes):

| Skeleton | Band | Nodes | Distinct root-to-ending paths | `covering_paths` result | Edge coverage | Wall clock |
|---|---|---|---|---|---|---|
| `the-tenfold-siege` | 16+ | **677** | >10^9 | **271 paths**, mean length 25.6 nodes, max 52 | **1.000, complete** | **1.22 s** |
| `the-cartographers-apprentice` | 10-13 | 254 | 85,753,081 | 289 paths | 1.000, complete | 0.01 s |
| `the-tin-whistle-map` | 8-11 | 193 | 3,324,033 | 297 paths | 1.000, complete | 0.01 s |
| `the-big-cardboard-box` | 3-5 | 44 | 18 | 18 paths | 1.000, complete | 0.00 s |

**The headline is that the answer barely grows with the book.** 677 nodes and 10^9 paths
reduce to **271 readings that together traverse every one of the 767 reachable choice edges**,
computed in about a second. The path count tracks *edge* count, not path count, which is
precisely why `covering_paths` is the right instrument and `reader_sample_paths` is not:
`covering_paths` answers *"is any reading bad"* (the safety question), `reader_sample_paths`
answers *"is the average reading bad"* (`paths.py:20-21, 420-421`).

### Per-book cost (the number requested)

At ceiling scale (677 nodes), the 271 paths carry **6,947 node visits** and **540,770
commissioned words**, a ~10.3x amplification over the book's 42,233 words, because a
bottleneck node is re-read on every path through it.

At ~1.33 tokens/word: **~719K input tokens**, plus ~271 short JSON verdicts ≈ 41K output.

| Configuration | Input | Output | **Per book** |
|---|---|---|---|
| Claude Sonnet 4.6 ($3 / $15 per MTok), synchronous | $2.16 | $0.61 | **≈ $2.77** |
| Sonnet 4.6 via Batch API (50%) | $1.08 | $0.31 | **≈ $1.39** |
| Claude Haiku 4.5 ($1 / $5 per MTok), synchronous | $0.72 | $0.21 | **≈ $0.93** |
| Haiku 4.5 batched | - | - | **≈ $0.46** |

Calibrate against what the existing per-node Stage 1 costs on the same book: 42,233 words at
`review_batch_size=8` is ~85 calls, ~82K input + ~27K output ≈ **$0.66** at Sonnet 4.6. So
**path-level safety is roughly 4x the current Stage-1 spend, not the order-of-magnitude blowup
the "677 nodes" framing implies**, and that is at the single largest book in the catalog. On
the 3-5 band book it is 18 paths and pennies.

Three cost levers if $2.77 is still too much:
- **Endings-weighted subsetting.** The class of harm at issue is what the book *rewards*, and
  `validator/imitable.py`'s measured design decision (endings only, young bands only) is the
  right precedent. Scoring only paths terminating in a positive-valence ending cuts the set
  substantially at ceiling scale.
- **Prompt caching on a shared prefix.** `covering_paths` splices from the shortest route in,
  so many paths share long opening prefixes. Ordering the batch by common prefix and setting
  a `cache_control` breakpoint after it turns repeated openings into ~0.1x reads.
- **Two-tier.** Haiku 4.5 over all 271 paths as a router; escalate only flagged paths to
  Sonnet/Opus. ≈$0.46 batched for full coverage plus a small escalation tail.

### What the stage must actually ask

Do **not** reuse the Stage-1 per-node rubric with the path text concatenated, that reproduces
the existing blind spot at higher cost. The prompt must ask the question the per-node stage
structurally cannot: *"Read this as one continuous reading. Does the sequence establish a
pattern, escalating isolation, secrecy from trusted adults, normalization of a harmful act
across steps, an assembled real-world procedure, or a harmful behaviour rewarded by the
ending, that no single passage would show?"* Verdict `block|flag|pass`, `pattern` from a
closed vocabulary, plus the node ids that carry the arc.

**Integration point:** a new Stage 5 in `_run_all_stages` (`pipeline.py:896+`), after
Stage 1 and behind the same `if report.has_hard_block: return` short-circuit, feeding
`Finding(stage=5, ...)` into the same report so routing, thresholds, and the review surface
all work unchanged. Then make the review surface render **paths, not the DFS list**, a
flagged path shown as its actual reading is what lets the human exercise the compensating
control that Claim 1 shows is currently unexercisable.

**Fail-closed requirement:** if the path stage cannot run (provider down, cap hit,
`complete=False` from a truncated walk), that must be a structural FLAG routing to human
review, exactly as `_INCOMPLETE_COVERAGE_CATEGORY` does for classifier shortfall
(`classifiers.py:80-83`, the existing precedent, and the right one). A truncated path set
silently reported as covered would be a worse failure than not running at all.

---

## R3: Seed known-bad books into the review queue at 3%

### Most of this already exists: build on it, do not rebuild it

The prior finding appears unaware of the **Moderation QA corpus**, which is a substantial
implementation of exactly this idea:

- `docs/planning/safety/moderation-qa-corpus.json`, 6 labeled whole storybooks with
  story-level *and* per-node expected verdicts, deliberately weighted toward **band-borderline
  discrimination pairs** (same content, two bands) with a single bright-line BLOCK case kept
  *"brief and clinical (it exists to be caught, not to be vivid)."*
- `scripts/seed_moderation_qa.py`, seeder with an environment guard.
- `scripts/moderation_qa_scorecard.py`, scores persisted reports against ground truth at both
  levels, exits nonzero on any regression, with pure comparison logic so it is unit-testable.
  It scores negative controls as a **ceiling** ("no finding at or above flag"), correctly,
  because advisories always fire.
- **A containment prefix enforced at the publish choke point.** `_MODERATION_QA_PREFIX =
  "mqa_"` and `_reject_mqa_fixture_outside_staging` (`publishing/service.py:65-101`) refuse to
  approve or publish any `mqa_`-prefixed id outside `staging`, a genuine second, independent
  layer at the sole publish path, with tests both ways.

**The gap is not the corpus. It is that this is a manual staging exercise scoring the
*classifiers*, and the recommendation is about blind-injecting into the *live* queue to score
the *humans*.** Those are different instruments and both are needed. What is missing:

1. **Blind injection into the production review queue at a sampled rate.**
2. **Scoring the reviewer**, not the pipeline: did the human catch it, how long did they
   spend, what did they click.
3. **Path-shaped seeds**, the corpus is passage-oriented and per-node-labeled, so it cannot
   measure Class-C detection at all, which is the class most needing measurement.

### What a good seed looks like

Weighted toward the classes the automated gate provably misses, since seeding a book the
classifiers already catch measures nothing about the human:

| Class | Share | Example | Why |
|---|---|---|---|
| **Class C path harm** | ~50% | The grooming-shaped 5-node arc constructed under Claim 1 | The only control is the human; this is the *only* way to measure whether that control works |
| **Cumulative imitable procedure** | ~20% | One step of a real hazard per node across a branch, each innocuous | Tests assembly detection, `UW-C264`'s open half |
| **Band-mismatch** | ~15% | 13-16-intensity peril in a 5-8 book | Tests band calibration; reuses the corpus's existing discrimination-pair design |
| **Reward inversion** | ~10% | Cruelty or exclusion as the positive-valence ending | Stage 1 has a BLOCK criterion for this; measures whether it fires in practice |
| **Negative controls** | ≥ the sum of the above | Ordinary clean books | Without them the reviewer learns "flagged = seeded" and the instrument dies. **This is the design constraint people skip.** |

Never use graphic content. The corpus's own stated policy, *"a single bright-line BLOCK case
suffices and is kept brief and clinical"*, is correct and must carry over: the seeds live in
a production database and are read by staff.

### Rate

3% is too high for a family-scale catalog. If the queue runs ~30 books/month, 3% is
~1 seed/month, far too sparse to detect a change in reviewer performance, while a rate high
enough to be statistically useful becomes noticeable and self-defeating. **Do not set a rate;
set an interval.** A fixed cadence (e.g. one seed per reviewer per N reviews, ~5-8) gives a
per-reviewer detection rate over a quarter, which is the number that actually matters. Revisit
percentage-based sampling only at public-catalog volume (Phase 9).

### The leak risk, and the safeguard

**The risk is real and is the reason to design this carefully rather than not do it.** A
seeded unsafe book that reaches a child is a worse incident than the miss it was measuring.
Defence in depth, reusing what is already proven:

1. **Containment prefix, extended.** The existing `mqa_` mechanism generalises directly. Use a
   distinct `seed_` prefix and extend `_reject_mqa_fixture_outside_staging` into a general
   `_reject_evaluation_fixture(storybook_id)`, but for production seeds the rule inverts: the
   id must never reach `published` **in any environment**.
2. **Interception at approve, not at assignment.** When a seed is approved, `approve()` must
   raise `BusinessLogicError(rule="evaluation_seed_approved")`, record the outcome
   ("reviewer missed it"), and **never transition status**. The reviewer sees a debrief
   instead of a publish. **The measurement is the attempted approve; the publish must never
   happen.** Placing the interception at the sole publish choke point means no assignment,
   library, or offline path can ever see it, those layers already filter on
   `status == "published"`.
3. **A DB CHECK as backstop.** `CHECK (NOT (id LIKE 'seed\_%' AND status = 'published'))`,
   the layer that survives a code regression.
4. **Never generated, only fixtured.** Seeds come from a reviewed, committed manifest, never
   from the generation pipeline, so a prompt bug can never manufacture one.
5. **Bounded lifetime + reconciliation.** A seed auto-expires; a daily job asserts zero
   published seeds and zero seeds assigned to any profile, and pages on either.
6. **Never seed a real family's queue without the operator knowing.** Blind to the
   *reviewer*, not to the *organisation*.

---

# What everyone missed

Ordered by what I would fix first.

1. **The shortest path to publishing a hard-blocked book is two clicks in the shipped UI, not
   three API calls.** *(Closed 2026-08-30: the ADR-005 amendment of 2026-08-25 refuses that
   approval without a typed override reason, and the console disables Approve until one is
   entered. See the correction under Claim 2. The `node_edit` behaviour this item describes is
   unchanged; what changed is that it no longer ends in a silent publish.)* The `node_edit` route (edit an `in_review` book -> fresh BLOCK persists,
   status untouched, Approve) is shorter, needs no scripting, and is **locked in by a passing
   test** (`tests/unit/test_node_edit.py:846`). Any fix that only closes the
   `needs_revision -> submit` route leaves the easier hole open. This reframes Claim 2 from
   "a gap someone forgot" to "a tested behaviour someone has to decide to change."

2. **The compensating control for Class-C harm is not merely expensive, it is the wrong
   presentation.** `buildReadThrough` (`storyReadThrough.ts:175-210`) is a DFS in which each
   node appears exactly once. A grooming arc is a *sequence*; a DFS listing interleaves
   sibling branches between its steps. Even a reviewer who reads all 42,233 words start to
   finish never sees the arc as a reading. Everyone treats the control as real-but-costly;
   it is structurally incapable of catching the thing it is the sole control for. The
   project's own safety doc points at this in one sentence and the recommendation was never
   picked up.

3. **`covering_paths` at ceiling scale is 271 paths and 1.22 seconds**: I ran it. The
   "677 nodes, >10^9 paths, intractable" framing that has kept path-level safety unbuilt is
   simply wrong about the instrument that already exists in this repo, fully tested, with a
   documented rationale for why enumerate-and-filter was the wrong shape. This is the single
   biggest actionable correction: the blocker was believed to be tractability and it is not.

4. **No recorded safety verdict is attributable to a model.** `to_dict()`
   (`report.py:208-233`) persists no model id, provider, or prompt version, and
   `review_openrouter_model` is a floating alias. Every other finding in this cluster is about
   whether the gate catches things; this one is about whether you could ever *prove* what the
   gate did. It is the cheapest fix here and it is a precondition for the seeded-corpus
   measurement in R3 meaning anything over time.

5. **Recall exists and works; only the trigger is missing.** The prior findings imply there
   is no way to pull a book. There is: `archive()` (`service.py:574`) is the sole
   `published -> archived` hop, writes a `STORYBOOK_ARCHIVED` event, `notifications/registry.py`
   composes it into an **alert-severity guardian notification**, and
   `frontend/src/offline/revocation.ts` reconciles against the shelf response on next fetch
   and deletes the cached book. **Content-hash recall is unnecessary**, the id-based path is
   complete. What is missing is (a) nothing triggers it on a rescreen BLOCK, and (b)
   revocation requires the device to come online, so a plane-mode tablet keeps a recalled book
   indefinitely with no TTL. Recommend a **max-offline-staleness TTL** on cached books,
   that is the real gap, and it is a small change.

6. **`covers/provider.py` passes no `SafetySettings`.** The one control the cover pipeline
   actually leans on (`provider.py:30-31`: "a safety refusal returns empty candidates") is
   an unpinned provider default that can change silently, with no record of which filter ran.
   New finding; not in the prior review.

7. **A `#CRITICAL: security` marker names a test that does not exist under that name.**
   `node_edit.py:672` cites `test_moderation_block_persists_not_rejects`; the actual test is
   `test_moderation_block_persists_and_does_not_reject`. Trivial in itself, but these
   `#VERIFY` markers are load-bearing in this codebase's safety argument, and a stale one on
   a `#CRITICAL` block is exactly the kind of drift a linter should catch. Recommend a check
   that every `#VERIFY` naming a `path::test_name` resolves.

8. **`_ADVISORY_SCORE_FLOOR` is self-documented as wrong and left in place.**
   `classifiers.py:60-71` records that the 2026-08-01 baseline **refutes** the rationale for
   0.01: all 120 clean passages score at or above it, and the clean maximum (0.397) *exceeds*
   the adversarial maximum (0.161). The advisory surface is therefore noise. Advisories never
   gate so nothing unsafe follows, but a reviewer trained on a permanently-noisy advisory
   surface stops reading it, a human-factors failure that compounds every finding above.

9. **The taxonomy gaps have no UW rows.** SAFE-14 (`UW-C115/C157/C290`) and imitable practice
   (`UW-C264`) are tracked in real detail. Violence intensity, bullying, substance use,
   stereotyping, and grooming as *category* gaps are not tracked anywhere I could find. Worth
   opening rows so they have a phase home, per the register's own linkage contract.

## Unsettled

- **Whether a repair can meaningfully re-point choice targets in practice.** I established
  that `run_gate` permits a topology change that preserves node count and validity, so the
  hole is real in principle. I did not construct a working example that a real generator
  would actually emit. Someone should try it against the mock and a live provider before
  sizing the fix.
- **Whether Gemini's default image safety thresholds would refuse the specific failure modes
  that matter here** (a child depicted in a distressing situation; imagery implying the
  grooming arc above). Unknowable from source; needs an empirical run against the provider.
- **Whether any *published* book in the current catalog already carries
  `summary.hard_block: true`.** This is answerable with one query against production and is
  the first thing I would run. If the answer is nonzero, Claim 2 is not a latent defect but a
  live incident.
